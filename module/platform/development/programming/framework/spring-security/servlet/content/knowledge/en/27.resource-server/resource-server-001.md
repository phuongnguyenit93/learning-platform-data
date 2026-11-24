# Role of Resource Server and Distinguishing It from OAuth2 Login Applications in Spring Security Servlet

## 1. Goal: Two Easily Confused Roles

In a system using OAuth 2.0, an application can act as a **Resource Server**, an **OAuth2 Client**, or both at the same time. When someone says “an application uses OAuth2,” you must ask whether it is **protecting an API that receives access tokens** or **logging users in through an identity provider**. These are two different responsibilities using different Spring Security components and HTTP flows.

A **Resource Server** exposes protected resources such as a JSON API, inspects the **access token** sent by the client, verifies that the token can be trusted, and decides whether the client is authorized to access it. An **OAuth2/OIDC Login application** is typically an **OAuth2 Client**: it redirects the browser to an Authorization Server, receives an authorization code, exchanges the code for tokens, and establishes a login session for the user in the application.

| Question | OAuth2 Resource Server | OAuth2/OIDC Login Application |
| --- | --- | --- |
| OAuth2 role | **Resource Server**, owner of the protected API | **OAuth2 Client**, representing the application that needs user login |
| Incoming request | **GET /api/orders** with **Authorization: Bearer ...** | **GET /dashboard**, **GET /oauth2/authorization/provider**, login callback |
| Authenticated by? | A valid access token from the right issuer and for the right API | Authorization Code flow with the provider; OIDC uses ID token/claims to verify identity |
| When unauthenticated | API typically returns **401** and **WWW-Authenticate: Bearer** | Browser is typically **302 redirected** to the login provider |
| Statefulness | Pure Bearer REST APIs are usually **stateless** | Traditional web applications usually create an **HttpSession** and cookie |
| Principal in Spring Security | Usually **Jwt** in **JwtAuthenticationToken**, or OAuth2AuthenticatedPrincipal if opaque | Usually **OAuth2User** / **OidcUser** in **OAuth2AuthenticationToken** |
| Primary configuration | **http.oauth2ResourceServer(...)** | **http.oauth2Login(...)** |
| Permission data | Scopes, claims, and authorities verified and mapped to API permissions | User identity/claims and authorities; tokens may be used to call other APIs |
| Responsible for issuing tokens? | **No**; primarily receives and verifies tokens | **Not necessarily**; the client requests tokens from the Authorization Server |

**Key takeaway:** A Resource Server does not automatically become an OAuth2 Login application just because both involve access tokens. Conversely, enabling **oauth2Login()** for a web UI does not automatically configure an API to accept Bearer JWTs.

## 2. The Four OAuth2 Roles and a Realistic Example

An architecture may consist of:

- **Resource Owner:** the user who owns the data being accessed.
- **OAuth2 Client:** a web app, mobile app, or service that wants to access resources on behalf of a user or a machine identity.
- **Authorization Server (AS):** issues access tokens after authentication/authorization via an appropriate grant. It may support OpenID Connect (OIDC) to provide login identity information.
- **Resource Server (RS):** an API that receives tokens and serves resources when the token is valid and has sufficient permissions.

Example:

~~~text
                            +-------------------------------+
                            | Authorization Server / IdP    |
                            | issues access tokens          |
                            +---------------+---------------+
                                            |
                                        access token
                                            |
+-------------------------+                 v
| Frontend / OAuth2 Client| -- Bearer --> [Orders API]
| or a backend client     |             [Resource Server]
+-------------------------+                    |
                                               v
                                            database
~~~

The Authorization Server and Resource Server may be managed by two different teams or systems. The Resource Server **trusts specific configured issuers and keys/introspection contracts**, but does not implicitly trust every JWT sent to it.

One application can perform multiple roles across different requests. For example, a web portal acts as an OAuth2 Client for login, then uses the acquired access token to call an Orders API acting as a Resource Server. The web portal **does not need to accept Bearer tokens** for its UI pages simply because it calls an API with a Bearer token on the backend.

## 3. Flow 1: Client Calling a Resource Server

Suppose a client already holds a valid access token issued by an Authorization Server. When calling the API:

~~~http
GET /api/invoices HTTP/1.1
Host: api.example.com
Authorization: Bearer eyJ...token...
~~~

What happens inside Spring Security Servlet:

~~~text
1. Request arrives at the API
    |
2. BearerTokenAuthenticationFilter extracts the bearer token from the request
    |
3. AuthenticationManager uses JwtAuthenticationProvider
   (JWT) or OpaqueTokenAuthenticationProvider (opaque)
    |
4. Validates the token: signature/issuer/expiration,
   or introspection depending on type and configuration
    |
5. Maps scopes/claims -> Authentication + GrantedAuthority
    |
6. AuthorizationFilter checks permissions on the endpoint
    |
7. Controller executes and returns data
~~~

If **no token is present** or **the token is invalid**, a protected endpoint typically returns **401 Unauthorized**. If the token authenticates successfully but **lacks sufficient authority/scope** for the resource, it typically returns **403 Forbidden**. Exception handlers and configuration choices can change response details, but you should not turn a Bearer API into a browser login redirect unless specifically required.

An example JWT access token might contain these claims:

~~~json
{
  "iss": "https://idp.example.com/realms/training",
  "sub": "user-123",
  "aud": ["orders-api"],
  "scope": "invoices.read invoices.write",
  "exp": 1893456000
}
~~~

This is an **illustrative payload**; readable JSON alone **does not prove the token is trustworthy**. The Resource Server must verify the signature or introspection result, expiration, issuer, and critical constraints such as the audience matching the API. **sub** is the subject, which can be a user or a service account; it is not automatically a user logged in via a browser.

## 4. Flow 2: Web Application Logging In with OAuth2/OIDC

A web application using **oauth2Login()** follows a typical flow:

~~~text
User opens /dashboard
       |
       v
Web app (OAuth2 Client) has no login session yet
       |
       +-- 302 redirect to the IdP's Authorization Endpoint
                   |
                   v
         User logs in / consents at the IdP
                   |
                   +-- Redirect back to redirect_uri with authorization code
                                       |
                                       v
                    Web app verifies state and exchanges code for tokens
                                       |
                                       v
                    Creates Authentication for the user, stores SecurityContext
                    in session per application configuration
                                       |
                                       v
                    Browser continues to /dashboard with session cookie
~~~

The login application is the **client** in the authorization code flow. With **OIDC**, the **openid** scope requests an additional identity layer; the application verifies the ID token and obtains an **OidcUser**. **OAuth2** is an authorization framework; **OIDC** adds a standard identity authentication layer. Therefore, you should not refer to every access token as an “ID token.”

A logged-in page in a web app can use a **session cookie** for requests to the web app itself. The web app can use **OAuth2AuthorizedClient** to manage access tokens when calling downstream APIs. The **web app's session cookie** and the **Bearer access token sent to an API** are two different credentials, with different lifecycles and protection responsibilities.

**Do not hand-write the authorization code exchange callback when Spring Security already provides oauth2Login().** Clear client registration and security chain configuration ensures state verification, login callbacks, and token handling go through framework-supported mechanisms. Depending on the client/public client setup, PKCE is an important mechanism; OIDC also includes nonce and ID token validation.

## 5. Distinguishing Access Tokens, ID Tokens, Refresh Tokens, and Cookies

| Credential Carrier | Intended For? | Purpose | Should NOT Be Used To... |
| --- | --- | --- | --- |
| **Access token** | Resource Server/API matching the audience | Request access to resources | Replace an ID token to prove a user logged in to a client |
| **ID token (OIDC)** | OAuth2/OIDC Client matching client_id | Let the client verify the authentication event and user identity | Act as a Bearer access token for an API unless the API is specifically designed/authorized for it |
| **Refresh token** | OAuth2 Client issued the refresh token | Request a new access token per AS policy | Be sent to a Resource Server as an API call token |
| **Session cookie** | Web app managing sessions | Look up the server-side login session | Assume it can replace a Bearer token for a standalone API |
| **Authorization code** | OAuth2 Client at the redirect URI | Exchange for tokens in the code flow | Be sent directly to an API to fetch resources |

JWT is a **token format** that can be used for either an access token or an ID token; the label “JWT” **does not tell you which kind of token it is**. A token with a valid signature whose **audience is not intended for the API** must still be rejected according to Resource Server policy. An API must not trust email/role/claims simply because they appear in an unverified payload.

A Resource Server does not need to handle login forms or exchange authorization codes. It may be called by a service using the client credentials flow, a mobile application, a browser SPA using an appropriate flow, or a web server that has logged in a user. **The Authorization Server grants permissions; the Resource Server enforces those permissions on actual resources**.

## 6. Spring Security Servlet: Configuring a JWT Resource Server

In a **Spring Boot 3.4.5**, **Java 17**, and **Spring Security 6** project, protecting an API that accepts Bearer JWTs requires the **spring-boot-starter-oauth2-resource-server** module. The example below configures a stateless API with scope-based authorization and no login redirect behavior.

Maven structure:

~~~text
resource-server-demo/
├── pom.xml
└── src/
    ├── main/
    │   ├── java/demo/resource/ResourceServerApplication.java
    │   └── resources/application.yml
    └── test/java/demo/resource/ResourceServerApplicationTests.java
~~~

**pom.xml**:

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.4.5</version>
        <relativePath/>
    </parent>
    <groupId>demo</groupId>
    <artifactId>resource-server-demo</artifactId>
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

**src/main/resources/application.yml**:

~~~yaml
spring:
  security:
    oauth2:
      resourceserver:
        jwt:
          issuer-uri: https://idp.example.com/realms/training
~~~

**Replace issuer-uri with the real issuer URI of a trusted IdP before starting to verify real tokens.** The **example.com** value is illustrative only and is not a live token provider. Configuring **issuer-uri** lets Spring Security use the issuer's metadata to locate public keys/JWKs and validate the issuer; reachability and metadata lookup timing depend on version/configuration. Do not enable fake token verification in real deployments.

**src/main/java/demo/resource/ResourceServerApplication.java**:

~~~java
package demo.resource;

import java.util.List;
import java.util.Map;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.annotation.web.configurers.AbstractHttpConfigurer;
import org.springframework.security.config.http.SessionCreationPolicy;
import org.springframework.security.core.annotation.AuthenticationPrincipal;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@SpringBootApplication
public class ResourceServerApplication {
    public static void main(String[] args) {
        SpringApplication.run(ResourceServerApplication.class, args);
    }
}

@Configuration
class ApiSecurityConfiguration {
    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http)
            throws Exception {
        return http
                .authorizeHttpRequests(auth -> auth
                        .requestMatchers(HttpMethod.GET, "/api/invoices")
                            .hasAuthority("SCOPE_invoices.read")
                        .anyRequest().denyAll())
                .oauth2ResourceServer(oauth2 ->
                        oauth2.jwt(Customizer.withDefaults()))
                .sessionManagement(session -> session
                        .sessionCreationPolicy(SessionCreationPolicy.STATELESS))
                .csrf(AbstractHttpConfigurer::disable)
                .build();
    }
}

@RestController
class InvoiceController {
    @GetMapping("/api/invoices")
    Map<String, Object> invoices(@AuthenticationPrincipal Jwt jwt) {
        return Map.of(
                "owner", jwt.getSubject(),
                "items", List.of("INV-001"));
    }
}
~~~

**Explanation of choices in the code:**

- **oauth2ResourceServer(...jwt(...))** enables Bearer JWT processing. There is no **oauth2Login()**, so the API does not create login redirect flows.
- **requestMatchers(...).hasAuthority("SCOPE_invoices.read")** requires a specific scope to read invoices. By default, Spring Security can map **scope** or **scp** in a JWT to a GrantedAuthority prefixed with **SCOPE_**. If the issuer uses another claim, you must configure a custom converter.
- **@AuthenticationPrincipal Jwt jwt** obtains the token already authenticated by Spring Security before the controller executes. Never manually parse the Authorization string and read unverified claims.
- **SessionCreationPolicy.STATELESS** chooses a model that does not rely on HttpSession to store SecurityContext state for the Bearer API.
- **csrf(...disable())** is used **only because this example receives tokens via an Authorization header explicitly attached by the client and does not use session/cookies for authentication**. If the API also uses cookies or supports browser login on the same chain, CSRF must be re-evaluated—do not blindly copy-paste disabling CSRF.
- **anyRequest().denyAll()** ensures new endpoints are not accidentally exposed publicly. That final rule is a conservative choice for this lesson; not every API must deny all other paths.

This is a complete Java Resource Server example. To run **end-to-end with real tokens**, you must configure a reachable issuer, appropriate verification keys, and a token containing **scope invoices.read** intended for the API. Writing a fake token on the command line does not make that token valid.

### 6.1. Testing with curl After Configuring a Real IdP

In the project directory:

~~~bash
mvn spring-boot:run
~~~

Once the API is running and configured with a real issuer:

~~~bash
# Without a token: typically HTTP 401.
curl -i http://localhost:8080/api/invoices

# Replace VALID_ACCESS_TOKEN with a real access token issued by the IdP.
curl -i http://localhost:8080/api/invoices \
  -H "Authorization: Bearer VALID_ACCESS_TOKEN"
~~~

If the token is valid, has the right issuer, is unexpired, and carries the **invoices.read** scope, an example response is:

~~~json
{"items":["INV-001"],"owner":"alice"}
~~~

JSON key ordering is not guaranteed. **alice** here is merely an illustrative subject; in practice it depends on the token's **sub** claim. If the token is valid but lacks the scope, the response is typically **403**. For an invalid signature or expired token, it is typically **401**. When testing against a real issuer, you also need to verify the audience matching the API: the Java example does not declare a custom audience validator because the audience and specific values must come from the IdP/API contract.

## 7. Testing the API Without Depending on an External IdP

**spring-security-test** provides **jwt()** to simulate a JWT Authentication at the MVC layer. To avoid calling the IdP's discovery endpoint in tests, use **@MockitoBean** for **JwtDecoder** in Spring Boot 3.4.x / Spring Framework 6.2. This test proves the **401/403/200 rules and scope enforcement**, but does not replace real signature and issuer testing.

**src/test/java/demo/resource/ResourceServerApplicationTests.java**:

~~~java
package demo.resource;

import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.jwt;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import org.springframework.security.oauth2.jwt.JwtDecoder;
import org.springframework.test.context.bean.override.mockito.MockitoBean;
import org.springframework.test.web.servlet.MockMvc;

@SpringBootTest
@AutoConfigureMockMvc
class ResourceServerApplicationTests {
    @Autowired
    MockMvc mvc;

    @MockitoBean
    JwtDecoder jwtDecoder;

    @Test
    void noTokenReturns401() throws Exception {
        mvc.perform(get("/api/invoices"))
                .andExpect(status().isUnauthorized());
    }

    @Test
    void validIdentityWithoutRequiredScopeReturns403()
            throws Exception {
        mvc.perform(get("/api/invoices")
                        .with(jwt().jwt(token -> token.subject("alice"))
                                .authorities(new SimpleGrantedAuthority(
                                        "SCOPE_other.read"))))
                .andExpect(status().isForbidden());
    }

    @Test
    void requiredScopeAllowsRequest() throws Exception {
        mvc.perform(get("/api/invoices")
                        .with(jwt().jwt(token -> token.subject("alice"))
                                .authorities(new SimpleGrantedAuthority(
                                        "SCOPE_invoices.read"))))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.owner").value("alice"))
                .andExpect(jsonPath("$.items[0]").value("INV-001"));
    }

    @Test
    void otherEndpointIsDeniedEvenWithValidIdentity()
            throws Exception {
        mvc.perform(get("/api/unknown")
                        .with(jwt().authorities(new SimpleGrantedAuthority(
                                "SCOPE_invoices.read"))))
                .andExpect(status().isForbidden());
    }
}
~~~

Run:

~~~bash
mvn test
~~~

In the tests, **jwt()** attaches a JWT principal and authorities to the test request; it **does not verify an actual signature**. Thus, the four tests above verify authorization rules and the controller; logic for selecting JWKs, issuer, expiration, and audience requires **integration tests with a real decoder and real tokens or properly signed fixtures**.

### When Is Additional Testing Needed?

- **JWT validation:** tokens with invalid signatures, wrong issuer, expired, before **nbf**, wrong audience, and key rotation.
- **Authority mapping:** a real JWT with **scope: "invoices.read"** must be converted to **SCOPE_invoices.read**; non-standard claims require an explicit converter.
- **Authorization:** two users with the same scope do not necessarily share permission to view every invoice; data ownership must be checked at the service layer.
- **Backend/network:** timeouts when fetching metadata/JWK, JWK caching, rollover, clock skew, and security logs not leaking access tokens.
- **HTTP:** status 401, 403, **WWW-Authenticate**, CORS in browsers, and whether gateways forward the Authorization header intact.

Do not treat results from **.with(jwt())** as proof that production JWT verification succeeds.

## 8. What If the Access Token Is an Opaque Token?

Not every access token is a JWT. With an **opaque token**, the token may be a string that the API cannot decode into claims locally. The Resource Server typically calls the Authorization Server's **token introspection endpoint** (or an equivalent configured mechanism) to learn whether the token is active and retrieve permission information.

Example basic configuration for OAuth2 Resource Server opaque tokens:

~~~yaml
spring:
  security:
    oauth2:
      resourceserver:
        opaque-token:
          introspection-uri: https://idp.example.com/oauth2/introspect
          client-id: resource-api
          client-secret: replace-with-real-secret
~~~

This is illustrative syntax and must be replaced with real endpoints/credentials; **never commit secrets to the repository**. When using opaque tokens instead of JWT, the filter chain must enable the corresponding opaque mechanism:

~~~java
// Replacement configuration for the oauth2ResourceServer(...) section in the example.
http.oauth2ResourceServer(oauth2 ->
        oauth2.opaqueToken(Customizer.withDefaults()));
~~~

**Do not enable both JWT and opaque without a clear design for classifying tokens.** With introspection, AS latency/availability and caching can affect the API. With JWT, many checks can run locally against fetched/cached JWKs, though immediate revocation is harder without additional mechanisms. This decision belongs to your organization's token architecture, not something the Resource Server guesses from token string length.

## 9. Spring Security Servlet: Configuring an OAuth2/OIDC Login Application

If the application is a website where users log in through an IdP, the dependency to use is **spring-boot-starter-oauth2-client**, replacing or supplementing the resource-server starter depending on the role. Typical web login configuration:

~~~java
@Bean
SecurityFilterChain webSecurity(HttpSecurity http) throws Exception {
    return http
            .authorizeHttpRequests(auth -> auth
                    .requestMatchers("/", "/assets/**").permitAll()
                    .anyRequest().authenticated())
            .oauth2Login(Customizer.withDefaults())
            .build();
}
~~~

**The snippet above is an OAuth2 Client configuration excerpt**—do not paste it directly into the API's SecurityFilterChain file from section 6. It only runs when the OAuth2 client dependency, client registration, and an IdP supporting the appropriate flow are present.

Example client registration for OIDC:

~~~yaml
spring:
  security:
    oauth2:
      client:
        registration:
          course-idp:
            provider: course-idp
            client-id: web-ui-client
            client-secret: replace-with-real-secret
            authorization-grant-type: authorization_code
            scope: openid,profile
        provider:
          course-idp:
            issuer-uri: https://idp.example.com/realms/training
~~~

Values are placeholders; supply secrets via a secret manager or environment variables in real environments. The web app redirects users to the provider's login endpoint, handles the callback (usually **/login/oauth2/code/{registrationId}**), creates an Authentication for the user, and maintains a session per configuration. **oauth2Login()** handles user login; it does not prove that an API is protected by Bearer JWTs.

For the web app to call another API with an access token, you can configure **oauth2Client()**, an **OAuth2AuthorizedClientManager**, or a corresponding authorized client management mechanism. That is an **outbound** flow from client to resource server, not a Bearer authentication filter for the web UI itself.

## 10. Can an App Be Both an OAuth2 Client and a Resource Server at the Same Time?

**Yes.** A web application can:

1. Use **oauth2Login()** for UI routes, logging users in and creating a session.
2. Use **oauth2ResourceServer()** for **/api/** to accept Bearer access tokens from other clients.
3. Use **oauth2Client()** when calling downstream APIs with appropriate tokens.

When combining them, the common design is **multiple SecurityFilterChain beans**, applied with explicit scopes and ordering. Illustrative configuration outline (not a complete file with all registrations/decoders declared):

~~~java
@Bean
@Order(1)
SecurityFilterChain apiChain(HttpSecurity http) throws Exception {
    return http.securityMatcher("/api/**")
            .authorizeHttpRequests(auth -> auth
                    .anyRequest().authenticated())
            .oauth2ResourceServer(oauth2 ->
                    oauth2.jwt(Customizer.withDefaults()))
            .sessionManagement(session -> session
                    .sessionCreationPolicy(SessionCreationPolicy.STATELESS))
            .csrf(AbstractHttpConfigurer::disable)
            .build();
}

@Bean
@Order(2)
SecurityFilterChain webChain(HttpSecurity http) throws Exception {
    return http.authorizeHttpRequests(auth -> auth
                    .anyRequest().authenticated())
            .oauth2Login(Customizer.withDefaults())
            .build();
}
~~~

You must add imports such as **@Order**, **Customizer**, **SessionCreationPolicy**, **AbstractHttpConfigurer**, and actual client registration/issuer configuration. Every chain must be tested with the right URLs: **/api/** must go through Bearer auth, while UI pages can redirect to login. The API authorization rule in this example only requires authenticated to illustrate chain selection; production must check specific scopes/permissions.

**Warning when using multiple chains:** Spring Security selects the first chain whose **securityMatcher** matches, rather than merging all chains. If a broad chain comes before **/api/**, API requests may fall into login redirects or wrong authorization rules. Test 401/403 for the API and 302 for the web UI separately.

**CSRF differs by model:** web app forms and browser sessions generally still require CSRF protection. An API that accepts only Bearer headers and uses no cookie auth may consider disabling CSRF on the API chain. Do not disable CSRF globally when a hybrid application still uses session cookies for state-changing endpoints.

## 11. JWT Validation and Permission Boundaries of a Resource Server

A Resource Server trusts a token **only after** verifying all applicable conditions:

| Item | What Must Be Done? |
| --- | --- |
| Signature and algorithm | Verify the signature using a trusted key and allowed algorithm; avoid accepting “alg=none” or disallowed algorithms |
| Issuer (**iss**) | Match against the trusted configured/registered issuer |
| Timestamps (**exp**, **nbf**) | Reject expired or not-yet-valid tokens within reasonable clock/clock skew bounds |
| Audience (**aud**) | Verify the token **is intended for this API**; configure a validator if the API requires a specific audience |
| Subject (**sub**) | Associate identity; do not assume sub is an email or a permission |
| Scopes/permissions | Map issuer claims to authorities; enforce permissions per endpoint and actual resource |
| Key rotation | Track key ID, JWK, and cache TTL; test safe key rotation |
| Token revocation | Self-validated JWTs have revocation lag depending on design; use short expiry or extra mechanisms if required by business rules |
| Logging/transport | Use HTTPS; never put Bearer tokens in URLs, query strings, logs, public traces, or shared caches |

**Spring Security cannot guess the right audience for every API by default.** When using issuer-uri, default validation handles standard checks like issuer and expiration, but business-specific audience rules must be declared and tested appropriately. A valid token intended for **payments-api** must not be accepted by **invoices-api**, even when issued by the same AS.

JWT roles/scopes also do not replace object-level authorization. Holding **SCOPE_invoices.read** does not mean a caller can read invoices of **every account**. Controllers/services must still enforce resource ownership or resource-level policies.

**Not every API has to use the same authorities claim.** By default Spring Security maps **scope/scp** to **SCOPE_...**; if the issuer uses **roles**, **realm_access**, or a custom claim, configure a **JwtAuthenticationConverter** and verify it with dedicated tests. Never permit all requests simply because a JWT is “validly signed.”

## 12. Common Pitfalls and How to Tell Them Apart When Debugging

| Symptom | Check |
| --- | --- |
| Calling an API without a token returns **302** to login | The request may be matching an **oauth2Login()** chain instead of the resource-server chain |
| Calling an API returns **401** | Missing/malformed Bearer header, invalid issuer/JWK/signature/expiry, or unrecognized token |
| API returns **403** even though the token is valid | Missing scope/authority or authorization rule denied access; also check CSRF if cookies are used |
| JWT looks “decodable” yet still returns 401 | Base64 decoding is not signature validation; check iss/aud/exp/algorithm/JWK |
| Web login succeeds yet the API returns 401 | The web app has a session cookie, but the API expects an access token with the right audience in Authorization |
| Sending an ID token to the API as an access token | Wrong purpose/audience; obtain an **access token** intended for the API |
| Client holds an access token yet the web page still redirects | The web chain has no login session; an outbound access token does not establish a web session |
| Changing authorities in a JWT test passes, yet production still returns 403 | **.with(jwt())** tests do not prove the real converter works; test claim mapping explicitly |
| API works with curl yet fails with CORS in a browser | Browser CORS is independent of token validation; inspect preflight/allowed headers |
| Session cookie works yet web POST returns 403 | Check the CSRF token and web session; do not use CORS as a substitute for CSRF |
| Token expires and the API returns 401 | The client must request a new token via its grant flow; the Resource Server does not refresh tokens for clients |
| Issuer unreachable / JWK error | Check discovery/JWK URL, proxy, TLS, key rotation, token-redacted logs, and load timing |

**Ordered debugging approach:** confirm the request hits the right SecurityFilterChain → check whether the request carries a Bearer header or a cookie → determine whether it is Resource Server or OAuth2 Login → if API, check issuer/token validation → inspect authorities/scope/audience → finally check resource-level permissions and applicable CORS/CSRF policies. Do not misdiagnose and “fix” it by enabling both login modes on a single chain without a clear contract.

## 13. Self-Check

1. A mobile app holds an access token and calls GET **/api/invoices**. What role does the Spring app serving this endpoint play? **Resource Server**.
2. A Spring web app redirects users to an IdP, receives an authorization code, and creates a session. What is that app's primary OAuth2 role? **OAuth2 Client**, with **OAuth2 Login**.
3. Are **ID tokens** and **access tokens** interchangeable? **No**; they have different audiences and purposes.
4. Should an OAuth2 Resource Server redirect users to a login page? **Normally no**; a Bearer API returns 401 when a token is missing.
5. What does a valid JWT lacking **SCOPE_invoices.read** normally receive? **403**, when the endpoint requires that scope.
6. An API uses session cookies and receives browser POST requests. Can CSRF be disabled just because Resource Server is enabled? **Not by default**; you must analyze credentials automatically sent by browsers.
7. How can a web app both serve a login UI and expose an API for mobile clients? **Two SecurityFilterChain beans** with explicit matchers and order, tested separately.
8. Why might a properly signed token still be denied access to an API? Because it may have the **wrong issuer, wrong audience, be expired, or lack required permissions**.

**Remember:** An **OAuth2 Resource Server** receives and verifies a request's **access token** to protect an API; an **OAuth2/OIDC Login application** uses the **authorization code flow** to log users in and usually maintains a web session. The Authorization Server issues tokens; the Client requests tokens; the Resource Server enforces permissions. When designing Spring Security Servlet applications, pick the right role, token type, SecurityFilterChain, and validate audience/scope per API.
