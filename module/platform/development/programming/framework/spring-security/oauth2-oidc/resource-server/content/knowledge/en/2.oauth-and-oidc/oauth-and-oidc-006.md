# OIDC Login Differs from Authenticating a Bearer Request at the Resource Server

A Spring Security application can act as an **OAuth 2.0 Client to log users in with OpenID Connect (OIDC)**, act as an **OAuth 2.0 Resource Server to protect APIs with Bearer Access Tokens**, or perform both roles. Both functions may trust the same Identity Provider (IdP), yet they answer **two different questions**:

- **OIDC Login:** "Who is the user who just logged in, and how does the web application maintain their login session?"
- **Bearer authentication at the Resource Server:** "Which Access Token does the current HTTP request carry, is that token valid for this API, and does it have sufficient permissions to perform the operation?"

Confusing the two questions leads to sending an ID Token to an API, expecting an API to redirect to a login page, or assuming one OIDC login automatically authenticates all Bearer requests.

## 1. Context: OAuth 2.0, OIDC, and the roles

**OAuth 2.0** is an authorization framework: a client receives an Access Token to call protected resources. **OpenID Connect** adds an identity authentication layer on top of OAuth 2.0, notably an **ID Token** for the client to verify the user's identity.

| Component | Responsibility |
| --- | --- |
| End User | The user logging in or using the application. |
| OAuth 2.0 / OIDC Client | Application requesting login, participating in the authorization code flow, receiving tokens, and establishing a login session for the user. |
| Authorization Server / OpenID Provider | Authenticates users, issues authorization codes, Access Tokens, and (in OIDC) ID Tokens. |
| Resource Server | API receiving Access Tokens and returning data only when the token and access permissions satisfy policy. |

An IdP such as Keycloak can simultaneously act as an OpenID Provider and an OAuth 2.0 Authorization Server. That **does not** collapse the login application and the API into the same role.

Example: an order management website logs employees in via OIDC; a mobile app or delivery service calls the orders API with a Bearer Access Token. The website needs to know who is logged in. The API needs to evaluate the token on **every request**.

## 2. Direct comparison of the two mechanisms

| Aspect | OIDC Login in a web application | Bearer authentication at a Resource Server |
| --- | --- | --- |
| Starting point | Browser navigates to a page requiring login. | Client sends an HTTP request to a protected API. |
| How credentials are carried | Browser redirect, authorization code, OIDC tokens; afterwards typically a session cookie. | **Authorization: Bearer ACCESS_TOKEN** header on each request. |
| Token used for its proper purpose | **ID Token** lets the client verify user identity; Access Token can be used to call APIs. | **Access Token** intended for that API; never substitute an ID Token. |
| Direct authentication target | User logging in with the OpenID Provider; client processes the OIDC result. | Current request carrying an Access Token issued by the Authorization Server. |
| Exchange style | Uses redirects and callbacks; usually via a browser. | API typically returns HTTP 401/403 rather than orchestrating an interactive login loop. |
| Statefulness | Web backend usually stores Authentication in an HTTP session. | Bearer API is usually stateless; every request presents its token. |
| Spring Security | **oauth2Login()**, **OAuth2LoginAuthenticationFilter**, **OidcUser**. | **oauth2ResourceServer()**, **BearerTokenAuthenticationFilter**, **JwtAuthenticationToken** or opaque token validation. |
| Access control | Web access may rely on the login session's principal/roles. | API access relies on scopes/authorities and resource-specific policies. |

**Both involve "authentication," but at two different layers:** OIDC Login establishes user identity for a client; the Resource Server checks authorization to use a designated API via an Access Token.

## 3. Flow A — User logs in with OIDC

Suppose the Spring Boot web application has registration ID **oidc-web**.

~~~text
Browser                    Spring Web (OIDC Client)             OpenID Provider
    | GET /profile                    |                              |
    |-------------------------------->|                              |
    | 302: login required             |                              |
    |<--------------------------------|                              |
    | GET /oauth2/authorization/oidc-web                            |
    |-------------------------------->|                              |
    | 302 to authorization endpoint   |                              |
    |<--------------------------------|                              |
    |----------------------------------------------> /authorize     |
    |                          Log in, consent (if needed)           |
    |<---------------------------------------------- code + state   |
    | GET /login/oauth2/code/oidc-web?code=...&state=...            |
    |-------------------------------->|                              |
    |                                 | POST /token (exchange code)  |
    |                                 |----------------------------->|
    |                                 |<-----------------------------|
    |                                 | ID Token + Access Token      |
    |                                 | Validate OIDC, build OidcUser|
    | Set-Cookie: session, redirect   |                              |
    |<--------------------------------|                              |
    | GET /profile + session cookie   |                              |
    |-------------------------------->|                              |
    | User profile page               |                              |
    |<--------------------------------|                              |
~~~

Key steps to understand:

1. **The client proactively initiates login.** Spring Security redirects the browser to the OpenID Provider's authorization endpoint. The Authorization Code Flow is the appropriate flow for backend web applications.
2. **The provider authenticates the user.** Upon completion, the provider redirects back to the client's callback with an authorization code and `state` parameter. The client verifies `state` before proceeding.
3. **The client exchanges the code for tokens.** The request to the token endpoint occurs as appropriate for the client type. With OIDC, the response includes an ID Token; an Access Token is also typically issued.
4. **The client validates the OIDC result.** ID Token validation checks signature, issuer, audience, expiration, and flow constraints such as `nonce` when applicable. This is login proof for the **requesting client**.
5. **The application creates an Authentication for the user.** In Spring Security Servlet, the OIDC session principal is typically **OidcUser**; the web application's SecurityContext is usually persisted via an HTTP session.
6. **Subsequent web requests use the login session.** The browser sends the session cookie; the backend restores the logged-in Authentication. The browser does not resend the ID Token on every page load.

Common default paths:

- Initiate login: **/oauth2/authorization/{registrationId}**.
- Callback receiving code: **/login/oauth2/code/{registrationId}**.

Both paths belong to **OAuth 2.0 Client Login**. A Resource Server does not need these endpoints to validate Bearer tokens.

### What does the ID Token represent?

A JWT ID Token might carry illustrative claims like:

~~~json
{
  "iss": "https://idp.example.test/realms/training",
  "sub": "user-123",
  "aud": "web-client",
  "exp": 1790000000,
  "email": "user@example.test"
}
~~~

The value **aud = web-client** states that the ID Token was issued for the OIDC Client with that client ID. The ID Token's primary purpose is to inform the client of the user's authentication. It **does not automatically grant permission** to call the orders API.

Note: the JSON above illustrates only the payload, not a complete signed JWT; it cannot be used as a real credential.

## 4. Flow B — Resource Server authenticates a Bearer request

Suppose a client has been issued an Access Token with permission to read orders by the Authorization Server. It sends:

~~~http
GET /api/orders HTTP/1.1
Host: orders.example.test
Authorization: Bearer eyJ...access-token...
~~~

Resource Server flow:

~~~text
API Client                         Spring Resource Server        Authorization Server
    | GET /api/orders                    |                            |
    | Authorization: Bearer ...          |                            |
    |----------------------------------->|                            |
    |                                    | Read Bearer token          |
    |                                    | Verify JWT signature with  |
    |                                    | public key from JWK Set    |
    |                                    | (or introspection if       |
    |                                    | Access Token is opaque)    |
    |                                    |                            |
    |                                    | Check iss, exp, nbf, aud   |
    |                                    | and scopes per config      |
    |                                    |                            |
    |                                    | Create Authentication,     |
    |                                    | check endpoint permissions |
    |<-----------------------------------|                            |
    | 200, 401, or 403                   |                            |
~~~

With a **JWT Access Token**, the API can verify the signature using public keys from the JWK Set, inspect claims, and enforce authorization locally. There is no need to call a user authentication endpoint or exchange an authorization code on **every request**. The Resource Server can fetch and refresh JWKs via the issuer's metadata per configuration.

With an **opaque Access Token** (a token string that cannot be decoded locally as a JWT), the Resource Server typically calls the Authorization Server's **token introspection endpoint** to determine token status and attributes. This is simply a different Resource Server configuration option; it does not mean OIDC Login must be enabled.

Typical Spring Security outcomes:

- For JWT: **JwtAuthenticationToken**, where the principal is usually a **Jwt** object and the default principal name usually comes from **sub**.
- For opaque tokens: Authentication uses the attributes returned by introspection.
- For a standard scope **orders.read** in the **scope** or **scp** claim, Spring Security normally maps it to authority **SCOPE_orders.read**.

A Resource Server can validate tokens issued on behalf of a **user** or via the **client credentials** flow for machine-to-machine services. Thus a valid Bearer request **does not necessarily** involve an interactive logged-in user.

### Conditions for a token to fit the API

To accept a token, validation must match the design of the Authorization Server and API:

1. **Signature / verification source:** JWT signed by a key belonging to a trusted issuer using an approved algorithm; or opaque token confirmed via trusted introspection.
2. **Timestamps:** Token is still valid, evaluating claims such as `exp` and `nbf`.
3. **Issuer (iss):** Matches the Authorization Server trusted by the API.
4. **Audience (aud):** Token was issued for this specific API, e.g. **orders-api**. This is a critical check that must be configured explicitly.
5. **Permissions:** Scopes or authorities permitting the specific action, such as **orders.read** for GET /api/orders.
6. **Additional policies:** Tenant, organization, resource owner, or other claims if required by the business domain.

**Note on default configuration:** when enabling a JWT Resource Server with only an issuer URI, Spring Security checks signature, expiration, and issuer, and maps scopes. The API must **add audience validation** matching its own API; never assume every valid JWT from the same issuer is suitable.

## 5. ID Token and Access Token cannot swap roles

| Attribute | ID Token | Access Token |
| --- | --- | --- |
| Primary purpose | Confirms identity/end-user authentication for the OIDC Client. | Permits access to protected resources. |
| Intended recipient | Relying Party / OIDC Client. | The Resource Server targeted by the token. |
| Key claims | iss, sub, aud = client ID, exp; optionally auth_time, nonce, acr... | issuer, API audience, lifetime, scope/permissions; structure depends on profile and issuer. |
| Format | JWT per OIDC. | Can be JWT or opaque string. |
| Proper usage | Validated by the client during login. | Sent by the client in **Authorization: Bearer** when calling APIs. |

Example JWT Access Token issued for the API:

~~~json
{
  "iss": "https://idp.example.test/realms/training",
  "sub": "user-123",
  "aud": ["orders-api"],
  "scope": "orders.read orders.write",
  "exp": 1790000000
}
~~~

Two tokens can share the same **iss**, **sub**, and be signed with a valid key, yet have **different audiences and meanings**. A carelessly configured API might accidentally accept an ID Token if it only checks signature, issuer, and expiration. That is a token separation vulnerability that must be prevented via audience and token-profile validation—not by assuming the framework automatically distinguishes every kind of JWT.

Some typical misconceptions:

- **"Once OIDC login finishes, the API can be called directly."** Not sufficient: the API needs an **Access Token with the right audience and scope**, or a session mechanism explicitly designed for that backend.
- **"An ID Token is a signed JWT, so the API can accept it."** Wrong purpose: an ID Token usually has the OIDC Client as its audience, not the API.
- **"Every Access Token can be decoded as a JWT."** False: Access Tokens may be opaque, in which case the Resource Server needs introspection or an appropriate verification mechanism.
- **"Having the `openid` scope means permission to read business data."** False: **openid** invokes OIDC and ID Token handling; reading orders requires a business scope such as **orders.read**.
- **"Bearer means there is a user session."** False: the token may belong to a service account, and each request is authenticated independently.

## 6. Spring Boot: configuring both roles in the same application

This example shows an MVC application with a **/profile** page using OIDC Login and an **/api/** API accepting Bearer JWTs. Each area is assigned to its own **SecurityFilterChain** to make request handling explicit.

### 6.1. Dependencies

Gradle example (Groovy DSL, in a Spring Boot project with dependency management plugins configured):

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-security'
    implementation 'org.springframework.boot:spring-boot-starter-oauth2-client'
    implementation 'org.springframework.boot:spring-boot-starter-oauth2-resource-server'
}
~~~

The **oauth2-client** starter serves the login flow; the **oauth2-resource-server** starter serves Bearer authentication. Both are needed when a single backend performs both roles.

### 6.2. application.yml

~~~yaml
spring:
  security:
    oauth2:
      client:
        registration:
          oidc-web:
            provider: example-idp
            client-id: ${OIDC_WEB_CLIENT_ID}
            client-secret: ${OIDC_WEB_CLIENT_SECRET}
            authorization-grant-type: authorization_code
            scope:
              - openid
              - profile
              - email
        provider:
          example-idp:
            issuer-uri: https://idp.example.test/realms/training
      resourceserver:
        jwt:
          issuer-uri: https://idp.example.test/realms/training
          audiences:
            - orders-api
~~~

This is an **illustrative** configuration: replace issuer, client registration, audience, and environment variables with your system's real values. The client's **issuer-uri** enables OIDC metadata discovery; the Resource Server's issuer identifies the trusted JWT issuer. They may match yet serve **two independent processing pipelines**.

The **audiences** field (on Spring Boot versions supporting this property) requires JWTs used for the Resource Server to contain **orders-api** in **aud**. If your project uses another version or needs complex rules, configure a **JwtDecoder** with a custom **OAuth2TokenValidator** as shown in section 6.4.

### 6.3. Two path-scoped SecurityFilterChains

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.annotation.Order;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.annotation.web.configurers.AbstractHttpConfigurer;
import org.springframework.security.config.http.SessionCreationPolicy;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class SecurityConfig {

    @Bean
    @Order(1)
    SecurityFilterChain apiChain(HttpSecurity http) throws Exception {
        http
            .securityMatcher("/api/**")
            .csrf(AbstractHttpConfigurer::disable)
            .sessionManagement(session ->
                session.sessionCreationPolicy(SessionCreationPolicy.STATELESS))
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/api/public/**").permitAll()
                .requestMatchers("/api/orders/**").hasAuthority("SCOPE_orders.read")
                .anyRequest().authenticated())
            .oauth2ResourceServer(oauth2 ->
                oauth2.jwt(Customizer.withDefaults()));

        return http.build();
    }

    @Bean
    @Order(2)
    SecurityFilterChain browserChain(HttpSecurity http) throws Exception {
        http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/", "/error").permitAll()
                .anyRequest().authenticated())
            .oauth2Login(Customizer.withDefaults());

        return http.build();
    }
}
~~~

**Why split the filter chains?**

- Requests to **/api/** match the highest-priority chain, using Bearer JWT and **STATELESS** sessions. The API does not need browser redirects to log in; requests without a valid token trigger the Resource Server's error handling.
- Web requests such as **/profile** match the remaining chain, using **oauth2Login()** with browser redirects, callbacks, and sessions.
- Disable **CSRF** only in pure Bearer APIs where clients explicitly send an Authorization header. For web endpoints using session cookies, keep default CSRF protection; actual application depends on endpoints and threat model.
- **CORS** is a separate mechanism for browsers calling cross-origin APIs; enabling oauth2Login or oauth2ResourceServer does not handle CORS automatically.

Request matchers must accurately reflect your real application's URLs and permissions. In this example, every endpoint under **/api/orders/** requires the read scope; real applications should distinguish **GET** from **POST/PUT/DELETE** to apply distinct read/write scopes.

### 6.4. Validating audience with JwtDecoder when customization is needed

If you do not use the **audiences** property or want full control over validation policy, define a decoder with validators. Use **only one deliberate source of audience configuration** to avoid mismatched configs.

~~~java
import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.oauth2.core.OAuth2Error;
import org.springframework.security.oauth2.core.OAuth2TokenValidator;
import org.springframework.security.oauth2.core.OAuth2TokenValidatorResult;
import org.springframework.security.oauth2.core.DelegatingOAuth2TokenValidator;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.security.oauth2.jwt.JwtDecoder;
import org.springframework.security.oauth2.jwt.JwtValidators;
import org.springframework.security.oauth2.jwt.NimbusJwtDecoder;

@Configuration
public class JwtValidationConfig {

    @Bean
    JwtDecoder jwtDecoder(
            @Value("${spring.security.oauth2.resourceserver.jwt.issuer-uri}")
            String issuer) {

        NimbusJwtDecoder decoder =
            NimbusJwtDecoder.withIssuerLocation(issuer).build();

        OAuth2TokenValidator<Jwt> audienceValidator = jwt ->
            jwt.getAudience().contains("orders-api")
                ? OAuth2TokenValidatorResult.success()
                : OAuth2TokenValidatorResult.failure(
                    new OAuth2Error(
                        "invalid_token", "Token is not for orders-api", null));

        decoder.setJwtValidator(new DelegatingOAuth2TokenValidator<>(
            JwtValidators.createDefaultWithIssuer(issuer),
            audienceValidator));

        return decoder;
    }
}
~~~

**JwtValidators.createDefaultWithIssuer** preserves the default issuer and timestamp rules; **audienceValidator** adds the target API check. Production systems may also need to validate token profiles, client/tenant claims, and fine-grained permissions per the Authorization Server's contract. Never decode a JWT payload while bypassing signature and validators.

### 6.5. Two endpoints demonstrating different principals

~~~java
import java.util.Map;
import org.springframework.security.core.annotation.AuthenticationPrincipal;
import org.springframework.security.oauth2.core.oidc.user.OidcUser;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class IdentityController {

    @GetMapping("/profile")
    Map<String, String> webProfile(@AuthenticationPrincipal OidcUser user) {
        return Map.of("loginSubject", user.getSubject());
    }

    @GetMapping("/api/whoami")
    Map<String, String> apiIdentity(@AuthenticationPrincipal Jwt jwt) {
        return Map.of("tokenSubject", jwt.getSubject());
    }

    @GetMapping("/api/orders/list")
    Map<String, String> orders() {
        return Map.of("result", "sample orders");
    }
}
~~~

In this configuration, **/profile** uses the OIDC login principal. **/api/whoami** uses the **Jwt** principal from the Bearer request; **/api/orders/list** requires the **SCOPE_orders.read** authority. These are illustrative endpoints for observing the security flow, not production data APIs.

If clients call **/api/whoami** with an opaque token, the principal will not be a **Jwt**; the controller must accept **Authentication** or **OAuth2AuthenticatedPrincipal** matching the opaque-token configuration.

## 7. Testing HTTP behavior and distinguishing errors

Once the IdP, client, and API are configured properly, observe these cases:

| Request / scenario | Expected behavior | Why |
| --- | --- | --- |
| Browser GET **/profile** when not logged in | 302 to login page or authorization endpoint (depending on config) | This is OIDC Client Login with browser redirects. |
| Browser completes OIDC then GET **/profile** with session cookie | 200 with OidcUser data | The application maintains a login session. |
| GET **/api/orders/list** without Bearer token | 401 Unauthorized, typically with WWW-Authenticate: Bearer | The API requires Bearer authentication. |
| API receives token with bad signature, expired, wrong issuer, or wrong audience | 401 Unauthorized | Authentication fails. |
| API receives valid Access Token lacking **orders.read** | 403 Forbidden | Authenticated, but lacks the required authority. |
| API receives valid Access Token, right audience, and **orders.read** | 200, if the endpoint succeeds | Passed both authentication and authorization. |
| Sending an ID Token whose audience is only **web-client** to an API requiring **orders-api** | 401 Unauthorized | Fails audience condition; not an Access Token intended for the API. |

Test commands (replace placeholder with a real Access Token issued by the Authorization Server):

~~~bash
curl -i http://localhost:8080/api/orders/list

curl -i -H "Authorization: Bearer YOUR_ACCESS_TOKEN" http://localhost:8080/api/whoami

curl -i -H "Authorization: Bearer YOUR_ACCESS_TOKEN" http://localhost:8080/api/orders/list
~~~

In a browser, open **http://localhost:8080/profile** and log in via the IdP. To start the OIDC flow directly, open **http://localhost:8080/oauth2/authorization/oidc-web**. The callback URL must be registered accurately with the IdP, such as **http://localhost:8080/login/oauth2/code/oidc-web** in an allowed development environment.

Never assume **403** just because a token was missing: missing/invalid tokens belong to the **authentication** step and normally produce **401**; only when a token is valid yet lacks permissions does it belong to **authorization** and normally produce **403**.

## 8. Which architectures combine both approaches?

### Architecture A: Server-rendered web, session cookie

The browser performs OIDC login against the web backend. Spring Security stores Authentication in the session. The browser accesses pages using a cookie; the backend can use the client's stored Access Token to call downstream APIs via **OAuth2AuthorizedClient**, under appropriate token policies. The browser itself never needs to handle raw tokens.

### Architecture B: SPA / mobile + API Resource Server

The frontend runs the authorization code flow with PKCE according to its design, receives an **Access Token**, and sends it in the Authorization header when calling the backend API. The backend only needs **oauth2ResourceServer()** to process those API requests. The frontend may also run an OIDC Login flow, but frontend login state **does not replace** backend verification of the Access Token.

### Architecture C: Backend for Frontend (BFF)

The browser communicates with the BFF via session cookies; the BFF performs OIDC Login and manages tokens server-side. The BFF forwards needed calls to Resource Servers using appropriate Access Tokens. Distinguish both legs:

- **Browser → BFF:** login session cookie, with appropriate CSRF protection.
- **BFF → Resource Server:** Bearer Access Token and permission checks at the API.

### Architecture D: Service-to-service

A service uses the **client_credentials** grant to obtain an Access Token for itself and calls an API. The Resource Server accepts the Bearer token as usual; there is no user login, ID Token, or browser session in this path.

## 9. Configuration pitfalls and implementation principles

1. **Confusing the ID Token's audience with the API's audience.** Request Access Tokens issued for the right resource/audience, and validate audience at the Resource Server.
2. **Trusting any JWT from the same issuer.** A valid signature is not enough to establish that a token is meant for every app or every API.
3. **Using the wrong filter for an endpoint.** If an API is only meant for clients sending Bearer tokens, configuring **oauth2Login()** alone can cause redirects and HTML responses instead of proper 401 API responses.
4. **Accidentally mixing session login into APIs.** Use path matchers and scoped SecurityFilterChains; if APIs are stateless, apply the appropriate session policy.
5. **Disabling CSRF globally because of Bearer APIs.** Cookie-based web routes remain vulnerable to CSRF; evaluate CSRF per authentication surface.
6. **Using inconsistent role/scope conventions.** Resource Server maps scopes to **SCOPE_**-prefixed authorities by default; custom roles from claims like `realm_access` or `roles` must be explicitly converted.
7. **Confusing 401 with 403.** Unauthenticated or invalid token → 401; valid token lacking permission → 403.
8. **Putting tokens in URLs or logs.** Protect tokens as secrets, use HTTPS, avoid query strings and full token logging; exposed Bearer tokens can be replayed.
9. **Forgetting token lifetime and refresh.** Clients manage refresh tokens per Authorization Server policy; a Resource Server normally **does not** use a refresh token to fix an expired Access Token request.
10. **Assuming JWT Access Tokens always have fixed claims.** Check your Authorization Server's documentation: scope claim names, audiences, permissions, token format, tenant model, and token profiles can differ.

## 10. How to choose the right mechanism

When designing an endpoint, ask in order:

1. **Is this a web page serving users in a browser?** Does it need interactive login and a session? Then **OIDC Login / oauth2Login()** is the right fit.
2. **Is this an API called with Authorization: Bearer?** Then **Resource Server / oauth2ResourceServer()** must validate the Access Token on every request.
3. **Do both endpoint types exist in the same application?** Use clearly scoped paths and SecurityFilterChains, or split them into separate services.
4. **Who consumes the token and whom was it issued for?** ID Tokens belong to the OIDC Client; Access Tokens must match the Resource Server, scopes, and data policies.

**Remember:** OIDC Login authenticates user identity **for the client** and typically builds a login session; Bearer authentication authenticates **API requests** with an Access Token. Sharing an IdP or sharing the JWT format does not merge the two mechanisms into one.

## References

- [Spring Security — OAuth 2.0 and OIDC: role overview](https://docs.spring.io/spring-security/reference/servlet/oauth2/index.html).
- [Spring Security — OAuth 2.0 Login](https://docs.spring.io/spring-security/reference/servlet/oauth2/login/core.html).
- [Spring Security — OAuth 2.0 Resource Server with JWT and token validation](https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/jwt.html).
- [OpenID Connect Core 1.0](https://openid.net/specs/openid-connect-core-1_0.html).
- [RFC 6750 — OAuth 2.0 Bearer Token Usage](https://www.rfc-editor.org/rfc/rfc6750).
