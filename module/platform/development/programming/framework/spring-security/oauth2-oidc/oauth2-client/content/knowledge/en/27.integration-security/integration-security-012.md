# 27.12. Distinguishing User Authentication, Client Authorization, and API Protection

## Lesson Objectives

In **Spring Security OAuth 2.0 / OpenID Connect (OIDC) Client**, three security responsibilities are often grouped together under the umbrella term "OAuth login":

1. **User Authentication**: Who is logging into the application, and by whom were they authenticated?
2. **OAuth2 Client Authorization**: Has the Authorization Server granted the application an access token to access an API with specific permissions/scopes?
3. **API Protection (Resource Server Security)**: Should the API accept the access token and permit the operation on a specific resource?

These three activities can occur sequentially in a single user experience, but they are **not synonymous**. An OIDC ID token is not an access token for calling APIs; holding an access token does not mean every API must accept it; and client credentials can issue a token to a service without any End-User logging in.

This lesson analyzes the boundaries between the **Browser**, **Spring Security OAuth2/OIDC Client**, **Authorization Server/OpenID Provider**, **Resource Server**, and the business authorization layer.

After this lesson, you will be able to:

- Distinguish the roles of End-User, Resource Owner, Client, Authorization Server, Relying Party, and Resource Server.
- Understand the distinct responsibilities of `oauth2Login()`, `oauth2Client()`, and `oauth2ResourceServer()`.
- Use ID tokens, access tokens, refresh tokens, authorization codes, and session cookies properly.
- Explain why a successful OIDC Login does not guarantee a token valid for the Orders API.
- Integrate a Portal using session/cookies with an Orders API using Bearer access tokens.
- Configure Spring Security Resource Server to validate issuer, audience, signature, expiry, and scope.
- Combine `SCOPE_*` with tenant, owner, and domain policies.
- Distinguish `authorization_code`, `refresh_token`, and `client_credentials` along with their distinct contexts.
- Understand Token Relay, Token Exchange, BFF, and direct API calls from an SPA.
- Design 401/403 handling, CSRF/CORS, logout, session/refresh behavior, and token security.
- Write tests proving that authentication, token authorization, and API authorization are enforced independently.

## 1. Scenario: Alice Opens the Orders Portal

Suppose the system consists of:

- **Alice** using a browser.
- **Employee Portal** built with Spring Boot, Spring Security, and OIDC Client.
- **Company OpenID Provider** acting as both End-User authenticator and OAuth2 token issuer.
- **Orders API**, an OAuth2 Resource Server.
- **Orders Database** storing orders across multiple users and tenants.

~~~mermaid
flowchart LR
    A["Alice / Browser"] -->|"Portal session cookie"| P["Employee Portal"]
    P -->|"OIDC Authorization Code"| OP["OpenID Provider / AS"]
    OP -->|"ID token, access token"| P
    P -->|"Bearer access token"| API["Orders API"]
    API -->|"Tenant + owner checks"| DB["Orders database"]
    API -->|"Orders data"| P
    P --> A
~~~

A single "View orders" experience requires three answers:

| Question | Responsible party | Evidence |
|---|---|---|
| Who is Alice? | OP authenticates; Portal validates the OIDC response | ID token, issuer/subject, local Authentication |
| Does the Portal have a token to call the Orders API? | AS issues token; OAuth2 Client manages it | `OAuth2AuthorizedClient`, access token, scope |
| Is Alice allowed to view order 123? | Orders API and domain service | Valid token, API scope, tenant/owner policy |

**The fact that Alice can log into the Portal does not grant her permission to view every order.**

### 1.1. Each Party Protects a Boundary

~~~text
OpenID Provider:
  Authenticates Alice, issues ID token.

Authorization Server:
  Issues access token/refresh token to the OAuth client.

Employee Portal (OAuth2/OIDC Client):
  Handles browser login, manages authorized clients,
  uses access tokens to call APIs.

Orders API (Resource Server):
  Verifies incoming request access tokens,
  enforces endpoint/method authorization.

Orders domain:
  Checks order owner, tenant, and business rules.
~~~

A single Identity Provider product can play both OP and AS roles. Even within the same product, **authentication** and **token authorization** remain separate responsibilities.

## 2. User Authentication with OIDC

**Authentication** answers "Who is logging in?". In OIDC, the application relies on an OP to authenticate the user through an authentication flow.

### 2.1. Authorization Code Flow

~~~mermaid
sequenceDiagram
    autonumber
    actor Alice
    participant Browser
    participant Portal as Portal / OIDC Client
    participant OP as OpenID Provider
    Alice->>Browser: Open /dashboard
    Browser->>Portal: Unauthenticated request
    Portal-->>Browser: Redirect to authorization endpoint
    Browser->>OP: OIDC Authorization Request
    OP->>OP: Login/MFA/consent per policy
    OP-->>Browser: Callback code + state
    Browser->>Portal: Callback
    Portal->>OP: Exchange code at token endpoint
    OP-->>Portal: Token response
    Portal->>Portal: Validate ID token, create Authentication
    Portal-->>Browser: Session cookie and dashboard
~~~

Spring Security OAuth2 Login handles the authorization request, state correlation, callback, token exchange, and OIDC validation according to your application configuration.

### 2.2. ID Token Intended for the Relying Party

Example claims in an ID token:

~~~json
{
  "iss": "https://id.company.example",
  "sub": "alice-123",
  "aud": "employee-portal",
  "exp": 1795000000,
  "iat": 1794999700,
  "auth_time": 1794999600
}
~~~

This is illustrative data, not a real credential.

- `iss`: issuing OP.
- `sub`: subject scoped to the issuer.
- `aud`: the client/Relying Party the ID token was issued for.
- `exp`: expiration timestamp.
- `auth_time`: authentication timestamp when requested or required by profile.

**An ID token is issued to the Portal to verify authentication**, not issued by default for the Orders API.

### 2.3. Principal in the Portal

After OIDC Login, Spring Security typically produces:

~~~text
OAuth2AuthenticationToken
  principal: OidcUser
  authorizedClientRegistrationId: corporate
  authorities: ...
~~~

A Servlet controller can retrieve the user:

~~~java
import org.springframework.security.core.annotation.AuthenticationPrincipal;
import org.springframework.security.oauth2.core.oidc.user.OidcUser;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class ProfileController {

    @GetMapping("/me")
    Profile me(@AuthenticationPrincipal OidcUser user) {
        return new Profile(
                user.getIdToken().getIssuer().toString(),
                user.getIdToken().getSubject());
    }

    record Profile(String issuer, String subject) {}
}
~~~

This example assumes the endpoint only supports OIDC Login. In an app supporting form login, OAuth2-only Login, or Bearer auth, the principal type can vary; do not blindly cast everything to `OidcUser`.

### 2.4. The Portal's Browser Session

A traditional Portal may store `SecurityContext` in `HttpSession`. The browser sends a cookie to the Portal on subsequent requests.

~~~http
GET /orders HTTP/1.1
Host: portal.example.com
Cookie: SESSION=...
~~~

The cookie proves the browser holds a session at the **Portal**. It does not automatically become a valid OAuth access token for the Orders API.

### 2.5. Valid Login Does Not Mean Sufficient Permissions

Alice can be authenticated accurately by the OP yet still:

- Not belong to the selected tenant.
- Lack the role to approve orders.
- Lack the required API scope.
- Have had her membership revoked after login.
- Not own the requested order.

Authentication is a prerequisite in many workflows, **not a substitute for authorization**.

## 3. OAuth2 Client Authorization: Acquiring Tokens to Call APIs

OAuth2 Client Authorization governs whether a client is permitted to obtain and use an access token for a Resource Server under an AS grant and policy.

### 3.1. `ClientRegistration` vs. `OAuth2AuthorizedClient`

~~~text
ClientRegistration:
  registrationId = corporate
  clientId = employee-portal
  grantType = authorization_code
  scopes = openid profile orders.read

OAuth2AuthorizedClient:
  registration = corporate
  principalName = alice-123
  accessToken = A1
  refreshToken = R1 (if issued by AS)
~~~

`ClientRegistration` is the static client configuration. `OAuth2AuthorizedClient` is the granted token state issued by the AS, typically bound to a registration and a principal.

### 3.2. Managers and Providers

In Servlet:

~~~text
OAuth2AuthorizedClientManager
  -> OAuth2AuthorizedClientProvider
  -> ClientRegistrationRepository
  -> OAuth2AuthorizedClientRepository / Service
~~~

In WebFlux:

~~~text
ReactiveOAuth2AuthorizedClientManager
  -> ReactiveOAuth2AuthorizedClientProvider
  -> ReactiveClientRegistrationRepository
  -> ServerOAuth2AuthorizedClientRepository / Reactive Service
~~~

The manager coordinates existing tokens, refreshes, or new token requests per grant. Invoking the manager **does not necessarily issue a new token endpoint request every time**.

### 3.3. Grants and Contexts

| Grant | Common context | Does every token request authenticate an End-User on the spot? |
|---|---|---|
| `authorization_code` | Browser/user interacts with AS | Flow includes authentication/consent per AS policy |
| `refresh_token` | Client exchanges refresh token for a new access token | Does not create fresh user authentication |
| `client_credentials` | Service-to-service | No End-User authentication |
| Token Exchange | Client exchanges one token for another per AS policy | Depends on source token and AS profile |

### 3.4. Consent Does Not Replace Per-Object Permissions

Alice consenting to `orders.read` for the Portal lets the AS issue an access token for the Orders API.

Whether Alice can read **order 123** remains a decision made by the Orders API and domain policy.

## 4. API Protection: Resource Server

The Orders API receives an incoming request:

~~~http
GET /api/orders/123 HTTP/1.1
Host: orders-api.example.com
Authorization: Bearer ACCESS_TOKEN_VALUE
~~~

The Resource Server is responsible for validating the token and enforcing authorization.

### 4.1. Necessary Verification Layers

1. Request includes credentials matching the API's authentication scheme.
2. Valid JWT signature or valid opaque token introspection.
3. Issuer matches an AS trusted by the API.
4. Token is not expired, and `nbf`/time claims (if present) are valid.
5. Audience/resource targets this API.
6. Scopes/authorities suffice for the endpoint/method.
7. The user/service is authorized for the specific tenant and object.
8. Additional policies such as resource state, rate limits, or network boundaries if required.

**A valid JWT signature does not guarantee the user has permission on individual records.**

### 4.2. Principal at the API vs. Principal at the Portal

Portal OIDC Login usually creates an `OAuth2AuthenticationToken` holding an `OidcUser`.

Orders API, upon verifying a JWT access token, usually creates a `JwtAuthenticationToken` with JWT claims and mapped authorities.

~~~text
Portal SecurityContext:
  OAuth2AuthenticationToken
  principal = OidcUser

Orders API SecurityContext:
  JwtAuthenticationToken
  principal = Jwt
  authorities = SCOPE_orders.read
~~~

Do not serialize the Portal's `SecurityContext` over the wire and treat it as proof of authentication at the Resource Server.

### 4.3. Three Authorization Layers

| Layer | Examples | Responsibility |
|---|---|---|
| Token validity | Issuer, signature, expiry, audience | Resource Server security layer |
| Coarse-grained | `SCOPE_orders.read` | Request/method authorization |
| Fine-grained | Owner, tenant, order status | Business service/database |

## 5. Direct Comparison

| Aspect | OIDC User Authentication | OAuth2 Client Authorization | Resource Server / API Protection |
|---|---|---|---|
| Question | Who is logging in? | What token was granted to the client? | What is the request allowed to do? |
| Roles | OP + RP | AS + Client | Resource Server |
| Primary output | Authenticated principal/session | Access token/authorized client | Allow/deny request |
| Relevant credential | ID token | Access/refresh token | Access token |
| Spring Security DSL | `oauth2Login()` | `oauth2Client()` | `oauth2ResourceServer()` |
| Object | `OidcUser` | `OAuth2AuthorizedClient` | `JwtAuthenticationToken` |
| Verifies owner? | Insufficient | Insufficient | Required in domain |
| Refresh token | Does not prove fresh MFA | Can support refreshing | Resource Server does not accept refresh tokens |
| Can operate without a user? | No for user OIDC Login | Yes, with `client_credentials` | Yes, API can accept service tokens |

## 6. Using the Right Token for the Right Recipient

| Token/value | Purpose | Intended recipient |
|---|---|---|
| Authorization code | Exchange for tokens in Authorization Code flow | AS token endpoint |
| ID token | Attest End-User authentication to RP | OIDC Client/Relying Party |
| Access token | Access protected APIs | Resource Server matching audience |
| Refresh token | Obtain a new access token | AS token endpoint |
| Session cookie | Identify browser session at Portal | Portal |
| Client secret | Authenticate a confidential client | AS token endpoint during client authentication |

### 6.1. An ID Token Is Not an API Bearer Token

Example ID token:

~~~json
{
  "iss": "https://id.company.example",
  "sub": "alice-123",
  "aud": "employee-portal"
}
~~~

The Orders API must not accept an ID token as an access token. Its audience and token semantics belong to the RP.

### 6.2. Access Tokens Can Be Opaque

OAuth2 does not require access tokens to be JWTs. An AS can issue opaque tokens.

- JWT access token: API verifies signature/JWKS/issuer/timestamps/audience.
- Opaque access token: API typically calls an introspection endpoint per the AS contract.

Merely Base64-decoding a JWT payload is not signature verification.

### 6.3. Refresh Tokens Do Not Go to the Resource Server

The client sends refresh tokens to the AS token endpoint. Never send them to the Orders API to "prove the token is about to expire."

### 6.4. Session Cookies Do Not Work Automatically at Standalone APIs

The Orders API may have zero knowledge of the Portal's session cookie. If an API accepts Bearer tokens, it must verify Bearer tokens under its own policy.

## 7. BFF Architecture: Browser Uses Cookies, Portal Calls APIs

With **Backend for Frontend (BFF)**, the browser uses a session cookie with the Portal; OAuth tokens stay on the backend.

~~~mermaid
flowchart LR
    B["Browser"] -->|"Session cookie"| P["Portal BFF"]
    P -->|"OIDC Login"| AS["OpenID Provider"]
    AS -->|"Tokens"| P
    P -->|"Bearer access token"| O["Orders API"]
    O --> D["Orders DB"]
~~~

Benefits:

- The browser does not need to store raw refresh tokens in `localStorage`.
- The Portal controls outbound API destinations.
- The client can manage token refreshes server-side.

Still, a BFF requires:

- Session cookie protection.
- CSRF protection for state-changing browser requests.
- Protection against XSS, clickjacking, and session fixation.
- Never logging tokens.
- API authorization at the Resource Server.

### 7.1. Browser Request

~~~http
GET /orders HTTP/1.1
Host: portal.example.com
Cookie: SESSION=...
~~~

### 7.2. Portal Outbound Request

~~~http
GET /api/orders HTTP/1.1
Host: orders-api.example.com
Authorization: Bearer ACCESS_TOKEN_VALUE
~~~

These represent two distinct credential boundaries and should not be conflated.

## 8. Configuring the Portal as an OIDC Client

A Spring Boot Servlet project can use:

~~~xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-web</artifactId>
</dependency>
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-oauth2-client</artifactId>
</dependency>
~~~

`application.yml`:

~~~yaml
spring:
  security:
    oauth2:
      client:
        registration:
          corporate:
            provider: company-op
            client-id: ${PORTAL_OIDC_CLIENT_ID}
            client-secret: ${PORTAL_OIDC_CLIENT_SECRET}
            client-authentication-method: client_secret_basic
            authorization-grant-type: authorization_code
            redirect-uri: "{baseUrl}/login/oauth2/code/{registrationId}"
            scope:
              - openid
              - profile
              - orders.read
        provider:
          company-op:
            issuer-uri: https://id.company.example
~~~

The OP must actually issue an access token suitable for the Orders API. Merely requesting scope `orders.read` **does not automatically guarantee the right audience**.

### 8.1. Portal SecurityFilterChain

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class PortalSecurityConfiguration {

    @Bean
    SecurityFilterChain portalSecurity(HttpSecurity http)
            throws Exception {

        return http
                .authorizeHttpRequests(auth -> auth
                        .requestMatchers(
                                "/", "/login", "/error", "/css/**")
                        .permitAll()
                        .anyRequest().authenticated())
                .oauth2Login(Customizer.withDefaults())
                .oauth2Client(Customizer.withDefaults())
                .build();
    }
}
~~~

- `oauth2Login()` creates browser authentication/sessions via the OP.
- `oauth2Client()` enables authorized client/token usage.
- `authenticated()` requires Authentication for protected Portal routes.
- This example does not disable CSRF for the session-based UI.

### 8.2. The Portal Does Not Automatically Become an API Resource Server

The configuration above does not enable the Portal to accept incoming Bearer JWT requests. To protect Bearer APIs, configure a Resource Server appropriately.

## 9. Portal Calling the Orders API with an Access Token

In modern Spring Boot/Spring Framework, a Servlet Portal can use `RestClient` (Spring Framework 6.1+) with an authorized client:

~~~java
import org.springframework.security.oauth2.client.OAuth2AuthorizedClient;
import org.springframework.security.oauth2.client.annotation
        .RegisteredOAuth2AuthorizedClient;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.client.RestClient;

@RestController
public class OrdersPortalController {

    private final RestClient ordersApi;

    public OrdersPortalController(RestClient.Builder builder) {
        this.ordersApi = builder
                .baseUrl("https://orders-api.example.com")
                .build();
    }

    @GetMapping("/orders")
    String orders(
            @RegisteredOAuth2AuthorizedClient("corporate")
            OAuth2AuthorizedClient client) {

        return ordersApi.get()
                .uri("/api/orders")
                .headers(headers -> headers.setBearerAuth(
                        client.getAccessToken().getTokenValue()))
                .retrieve()
                .body(String.class);
    }
}
~~~

This example assumes `corporate` already holds an authorized client with an access token valid for the API. When the token expires, refreshing/token lifecycle depends on your authorized client manager/provider and project configuration.

### 9.1. Wrong: Using the ID Token

~~~java
String wrongToken =
        oidcUser.getIdToken().getTokenValue();

headers.setBearerAuth(wrongToken);
~~~

The ID token is for the Portal, not an API access token.

### 9.2. The Right Token Type Still Needs the Right Audience

~~~java
String accessToken =
        client.getAccessToken().getTokenValue();

headers.setBearerAuth(accessToken);
~~~

The API still must verify that this token was issued by the AS **for the Orders API** and carries the required permissions.

### 9.3. Do Not Return Raw Tokens to the Browser

The controller should return business data or errors, never serialize `OAuth2AuthorizedClient` with its refresh token as JSON.

### 9.4. Never Attach a Bearer Token to an Arbitrary URL

An endpoint like:

~~~text
GET /proxy?url=https://attacker.example.net
~~~

where the backend attaches an access token to a user-chosen URL can leak credentials. Use dedicated HTTP clients per API, allowlist host/scheme/port, and control redirects.

## 10. Orders API as a Resource Server

Maven dependencies for the **Orders API**:

~~~xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-web</artifactId>
</dependency>
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-oauth2-resource-server</artifactId>
</dependency>
~~~

Configuration:

~~~yaml
spring:
  security:
    oauth2:
      resourceserver:
        jwt:
          issuer-uri: https://id.company.example

app:
  security:
    required-audience: orders-api
~~~

`required-audience` is a **custom application property** used in the illustrative validator below.

### 10.1. Bearer-Only SecurityFilterChain

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.method.configuration
        .EnableMethodSecurity;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.http.SessionCreationPolicy;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
@EnableMethodSecurity
public class OrdersApiSecurityConfiguration {

    @Bean
    SecurityFilterChain apiSecurity(HttpSecurity http)
            throws Exception {

        return http
                .csrf(csrf -> csrf.disable())
                .sessionManagement(session -> session
                        .sessionCreationPolicy(
                                SessionCreationPolicy.STATELESS))
                .authorizeHttpRequests(auth -> auth
                        .requestMatchers("/actuator/health").permitAll()
                        .requestMatchers(
                                HttpMethod.GET, "/api/orders/**")
                        .hasAuthority("SCOPE_orders.read")
                        .requestMatchers(
                                HttpMethod.POST, "/api/orders/**")
                        .hasAuthority("SCOPE_orders.write")
                        .anyRequest().denyAll())
                .oauth2ResourceServer(oauth2 -> oauth2
                        .jwt(Customizer.withDefaults()))
                .build();
    }
}
~~~

### 10.2. Why Does This Example Disable CSRF?

This API example is designed to **accept only a Bearer Authorization header, without cookies/sessions for authentication**. In that model, disabling CSRF tokens for the API is appropriate.

**Do not copy `csrf.disable()` into a Portal using session cookies or a mixed API.** Whenever the browser sends ambient credentials automatically, re-evaluate CSRF.

### 10.3. `STATELESS` Does Not Skip Authentication

Spring Security still validates the Bearer token on every request, populates Authentication, and enforces authorization. Stateless simply stops using `HttpSession` to store `SecurityContext` for API requests under that chain.

### 10.4. `SCOPE_*` Comes from Scope Mapping

An access token JWT may contain:

~~~json
{
  "iss": "https://id.company.example",
  "sub": "alice-123",
  "aud": ["orders-api"],
  "scope": "orders.read orders.write"
}
~~~

The default `JwtGrantedAuthoritiesConverter` may map this to:

~~~text
SCOPE_orders.read
SCOPE_orders.write
~~~

If the AS uses a different claim name or format, configure an appropriate converter. Do not assume every `roles` claim automatically turns into `ROLE_*`.

## 11. JWT Audience Validation

Suppose the Billing API and Orders API both trust the same issuer:

~~~text
https://id.company.example
~~~

A token:

~~~json
{
  "iss": "https://id.company.example",
  "aud": ["billing-api"],
  "scope": "billing.read"
}
~~~

has a valid signature, yet is **not intended for the Orders API**.

### 11.1. Adding an Audience Validator

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
public class JwtValidationConfiguration {

    @Bean
    JwtDecoder jwtDecoder(
            @Value("${spring.security.oauth2.resourceserver.jwt.issuer-uri}")
            String issuer,
            @Value("${app.security.required-audience}")
            String requiredAudience) {

        NimbusJwtDecoder decoder =
                NimbusJwtDecoder.withIssuerLocation(issuer).build();

        OAuth2TokenValidator<Jwt> audience = jwt -> {
            if (jwt.getAudience().contains(requiredAudience)) {
                return OAuth2TokenValidatorResult.success();
            }
            OAuth2Error error = new OAuth2Error(
                    "invalid_token",
                    "Orders API audience is required",
                    null);
            return OAuth2TokenValidatorResult.failure(error);
        };

        decoder.setJwtValidator(
                new DelegatingOAuth2TokenValidator<>(
                        JwtValidators.createDefaultWithIssuer(issuer),
                        audience));

        return decoder;
    }
}
~~~

This illustrative pattern adds audience validation alongside issuer and default JWT checks. JWK/trust configuration must be protected; never take arbitrary issuer or JWKS URLs from browser requests.

### 11.2. ID Token Audience Differs from Access Token Audience

An OIDC ID token's `aud` is normally the Portal's client ID. An access token's `aud` normally identifies the Resource Server per the AS token profile.

Do not make the Orders API accept tokens solely because their audience matches the Portal's client ID unless the AS/API contract explicitly mandates it.

### 11.3. Tokens with Multiple Audiences

A token may carry a list in `aud`. The API checks its own required audience and any additional conditions, rather than blindly trusting every JWT signed by the issuer.

### 11.4. Valid Signature Is Not Authorization

`JwtDecoder` checks the signature and basic claim validity. Authorization rules and method checks still must enforce scopes and domain permissions afterward.

## 12. Opaque Access Tokens and Introspection

If the AS issues opaque access tokens, the Resource Server cannot parse them locally like JWTs.

Example Spring Security configuration:

~~~yaml
spring:
  security:
    oauth2:
      resourceserver:
        opaque-token:
          introspection-uri: https://id.company.example/oauth2/introspect
          client-id: ${ORDERS_INTROSPECTION_CLIENT_ID}
          client-secret: ${ORDERS_INTROSPECTION_CLIENT_SECRET}
~~~

Requirements:

- The AS provides a compatible introspection endpoint.
- The Orders API has client credentials authorized to introspect tokens.
- The `active` flag and returned claims are evaluated per policy.
- The API still checks audience/scope where supported by metadata and contract.
- Owner/tenant authorization remains in the domain service.

### 12.1. Introspection Does Not Replace Owner Checks

The AS may return `active=true`, yet Alice still may not be allowed to view order 123.

### 12.2. Caching and Revocation

If caching introspection responses, weigh revocation freshness against token lifetime. Caching too long can allow a revoked token to remain accepted for an extended window.

## 13. Scope Is Not Enough to Read Every Resource

Suppose Alice holds an access token with `orders.read` and calls:

~~~http
GET /api/orders/123 HTTP/1.1
Authorization: Bearer <ACCESS_TOKEN>
~~~

The Orders API must verify that order 123 belongs to Alice's tenant and that Alice is permitted to read it.

### 13.1. Tenant/Owner Authorization

Service example:

~~~java
import java.util.Optional;
import org.springframework.stereotype.Service;

@Service
public class OrderQueryService {

    private final OrderRepository repository;

    public OrderQueryService(OrderRepository repository) {
        this.repository = repository;
    }

    public Optional<Order> findVisible(
            String verifiedTenantId,
            String verifiedUserId,
            String orderId) {

        return repository
                .findByTenantIdAndId(
                        verifiedTenantId, orderId)
                .filter(order ->
                        order.ownerUserId()
                                .equals(verifiedUserId));
    }
}
~~~

`OrderRepository` and `Order` are illustrative domain abstractions. `verifiedTenantId` and `verifiedUserId` must come from a validated identity/authorization context, never from a request body or query parameter supplied by the caller and blindly trusted.

### 13.2. Method Security

The example below uses an application-implemented `orderAccess` bean:

~~~java
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.stereotype.Service;

@Service
public class OrderReadService {

    @PreAuthorize(
            "hasAuthority('SCOPE_orders.read')"
            + " and @orderAccess.canRead(authentication, #orderId)")
    public Order getOrder(String orderId) {
        throw new UnsupportedOperationException(
                "Domain implementation omitted");
    }
}
~~~

`@EnableMethodSecurity` must be enabled properly, and `orderAccess.canRead` must verify tenant/owner/resource rules without leaking data.

### 13.3. IDOR/BOLA

An attacker can alter the order ID in the URL. Checking only the bearer token and scope will not prevent reading someone else's object. This is why APIs need Broken Object Level Authorization (BOLA) protection.

### 13.4. Return Data Only After Checking

Do not load all data across every tenant and filter only on the frontend. Queries should enforce tenant/owner predicates in the service/database layer by design.

## 14. Scopes, Roles, Groups, and Domain Permissions Differ

| Data | Source | Meaning |
|---|---|---|
| `scope=orders.read` | AS issuing access token | Token-level permission scope |
| `SCOPE_orders.read` | Spring token-to-authority mapping | Authority inside the API `SecurityContext` |
| `groups=[finance]` | OP/Identity Directory | Identity/group per provider |
| `ROLE_ORDER_ADMIN` | Application mapping | Internal role permission |
| Tenant membership | SaaS membership service | Which tenant the user belongs to |
| Resource owner | Database | Which objects the user may access |

### 14.1. Do Not Automatically Map Every Group to Admin

A group named `admins` at OP A is not automatically equivalent to `ROLE_ADMIN` in the Orders API. Enforce explicit trust and mapping scoped by issuer, tenant, and policy.

### 14.2. Scopes Are Coarse-Grained

Scopes are usually a necessary condition for an endpoint, but do not express full per-object permissions. Domain authorization may inspect roles, attributes, tenant, and owner.

### 14.3. Portal Authorities Do Not Travel Automatically Over HTTP Requests

The Portal holds an `Authentication` in its session. The API constructs its own `Authentication` from the Bearer access token. Never serialize Portal authorities and trust them at the API without a carefully designed security contract.

## 15. `client_credentials`: Service Identity, Not End-User

A background job uses client credentials to call the Reporting API.

~~~yaml
spring:
  security:
    oauth2:
      client:
        registration:
          reporting:
            provider: company-as
            client-id: ${REPORTING_CLIENT_ID}
            client-secret: ${REPORTING_CLIENT_SECRET}
            client-authentication-method: client_secret_basic
            authorization-grant-type: client_credentials
            scope:
              - reports.read
        provider:
          company-as:
            token-uri: https://id.company.example/oauth2/token
~~~

The resulting token represents the **OAuth client/service**. Neither an OIDC user nor an ID token is required to exist.

### 15.1. `sub` Is Not Necessarily a Human User

Under `client_credentials`, some AS implementations place the client identity in `sub` or `client_id`. The API must understand its token profile and not assume every `sub` represents a human user.

### 15.2. Never Use a Service Token to Bypass User Permissions

If the Portal uses a broad-privilege service token to call an API on Alice's behalf while skipping checks on whether Alice can access the object, a confused deputy / privilege escalation vulnerability occurs.

### 15.3. User-Delegated vs. Service-Level Actions

| Context | What must be verified? |
|---|---|
| Alice views an order | User identity, scope, tenant, owner |
| Scheduled reporting job | Service identity, allowed tenant/data scope, service policy |
| Admin acting on behalf of user | Delegation, auditing, least privilege, domain policy |

Do not interchange tokens across these three contexts.

## 16. Token Relay, Token Exchange, and Client Credentials

Three distinct patterns:

### 16.1. Token Relay

A Gateway/BFF forwards the received access token to a target API **only if that token is authorized for use at that API**.

Never relay a token with `aud=gateway` to the Orders API merely because the gateway validated it.

### 16.2. Token Exchange

A client submits a subject token to obtain a new token from the AS, potentially scoped specifically to a downstream API or actor per policy.

Token Exchange requires AS support and authorization for both client and subject. Never exchange tokens to escalate privileges beyond allowed policy.

### 16.3. Client Credentials

A client requests a service token using its own identity. That token is not Alice's delegated identity.

### 16.4. Comparison

| Pattern | Token sent to API | User context |
|---|---|---|
| Token Relay | Existing token already issued for the API | Depends on the token |
| Token Exchange | New token from AS scoped for downstream | Per subject/actor semantics |
| Client Credentials | Service access token | No End-User by default |

## 17. Direct API Calls from an SPA

A Single Page Application can use Authorization Code + PKCE to acquire an access token and call an API directly from the browser.

~~~mermaid
flowchart LR
    SPA["Browser SPA"] -->|"Authorization Code + PKCE"| OP["OP / AS"]
    SPA -->|"Bearer access token"| API["Orders API"]
    API --> DB["Orders database"]
~~~

### 17.1. An SPA Is a Public Client

JavaScript executing in the browser cannot keep a client secret confidential the way a backend can. Never hardcode an OAuth client secret in a frontend bundle.

### 17.2. Browser Tokens Require Their Own Threat Model

Evaluate XSS, CSP, token storage, lifetimes, refresh token rotation, cross-tab behavior, and logout.

Never treat `localStorage` or `sessionStorage` as completely safe storage for Bearer tokens.

### 17.3. PKCE Does Not Replace API Validation

PKCE protects the Authorization Code flow. The Resource Server still must validate the Bearer token, audience, scope, and owner.

### 17.4. CORS Is Not Authentication

CORS governs whether a browser may read a cross-origin response. It does not verify JWTs, grant user permissions, or stop non-browser clients from sending HTTP requests.

## 18. Three Spring Security DSLs with Different Jobs

~~~java
http.oauth2Login(...);
http.oauth2Client(...);
http.oauth2ResourceServer(...);
~~~

### 18.1. `oauth2Login()`

- Browser redirects to the AS/OP.
- Callback, state, and code exchange.
- OIDC ID token validation.
- Creates local Authentication/session.

Does not replace Resource Server authorization.

### 18.2. `oauth2Client()`

- Authorized clients and token management.
- Grant provider chains.
- Uses access tokens for outbound API calls.
- Refreshes or reauthorizes when appropriate.

Does not decide whether Alice can view order 123.

### 18.3. `oauth2ResourceServer()`

- Validates incoming Bearer tokens for the API.
- JWT or opaque token verification.
- Populates Authentication inside the API.
- Pairs with authorization rules.

Does not perform browser login or hold client refresh tokens on its own.

### 18.4. Can One Application Use All Three?

Yes, provided security boundaries are clearly defined. A monolith serving both a web UI and Bearer APIs typically needs separate filter chains or explicit matcher configurations.

## 19. Separating the Browser Chain and Bearer API Chain

Example Servlet configuration for a hybrid application:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.annotation.Order;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.http.SessionCreationPolicy;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class HybridSecurityConfiguration {

    @Bean
    @Order(1)
    SecurityFilterChain apiChain(HttpSecurity http)
            throws Exception {

        return http
                .securityMatcher("/api/**")
                .sessionManagement(session -> session
                        .sessionCreationPolicy(
                                SessionCreationPolicy.STATELESS))
                .csrf(csrf -> csrf.disable())
                .authorizeHttpRequests(auth -> auth
                        .anyRequest().authenticated())
                .oauth2ResourceServer(oauth2 -> oauth2
                        .jwt(Customizer.withDefaults()))
                .build();
    }

    @Bean
    @Order(2)
    SecurityFilterChain browserChain(HttpSecurity http)
            throws Exception {

        return http
                .authorizeHttpRequests(auth -> auth
                        .requestMatchers("/", "/login", "/error")
                        .permitAll()
                        .anyRequest().authenticated())
                .oauth2Login(Customizer.withDefaults())
                .oauth2Client(Customizer.withDefaults())
                .build();
    }
}
~~~

### 19.1. Scope of the Example

`apiChain` assumes `/api/**` accepts only Bearer tokens and never cookies for authentication. In production, add scope/method/owner rules, error handling, actuator/CORS rules, and verify matcher ordering.

### 19.2. Do Not Let the API Redirect to the OP

A bearer-only API should normally return a 401/403 JSON/API response rather than redirecting browsers to the OP login page when a token is missing.

### 19.3. Do Not Assume Every Path Hits the Intended Chain

Integration tests must verify that `/api/**` does not accidentally accept session cookies and that browser pages retain CSRF protection.

## 20. 401 vs. 403

### 20.1. 401 Unauthorized

Usually means the request lacks **valid credentials** for the protected API:

- Missing Bearer token.
- Token expired.
- Wrong signature/issuer/audience.
- Inactive opaque token.
- Unsupported token format.

### 20.2. 403 Forbidden

Usually means the request was authenticated, yet **lacks permission**:

- Missing `orders.write` scope.
- Alice is not the owner.
- User does not belong to the tenant.
- Service client is not authorized for the action.
- Business rule denies the operation.

### 20.3. Do Not Refresh Indefinitely

If an API returns 401, diagnose why. Refreshing can resolve an expired access token when the refresh token is still valid, but it will not fix a wrong issuer or audience.

A 403 will not normally disappear after refreshing either, because scopes and ownership usually remain unchanged.

### 20.4. Retrying Side-Effecting Calls

For a payment or order-creation `POST`, a timed-out request may already have succeeded. Never auto-retry endlessly after refresh without an idempotency policy.

## 21. Token Lifetimes, Sessions, and Logout

The separate lifecycles:

~~~text
Portal session:
  Alice's SecurityContext / Authentication

Access token:
  Independent expiry and revocation policy

Refresh token:
  Independent expiry, rotation, and invalid_grant policy

OP SSO session:
  OpenID Provider policy
~~~

### 21.1. Active Session, Expired Access Token

Alice is still logged into the Portal, yet A1 has expired. The OAuth client can refresh A1 using R1 if one was issued.

### 21.2. Refresh Does Not Mean Reauthentication

A refresh token grant does not prove the user just entered a password or MFA. If step-up authentication is needed, initiate an OIDC authentication request/policy and validate the relevant claims.

### 21.3. Local Logout Differs from Revocation

Logging out of the Portal may clear the session while an unexpired access token remains accepted by the AS/Resource Server per policy. If `OAuth2AuthorizedClient` is persisted in a service store outside the session, local logout might not even delete that record.

### 21.4. OP SSO Logout

RP-Initiated Logout depends on OP support. Logging out of the Portal does not automatically terminate all OP SSO sessions.

## 22. Protecting Tokens and Outbound Integrations

### 22.1. Never Log Tokens

Avoid logging:

~~~text
Authorization: Bearer ...
access_token
refresh_token
id_token
authorization_code
code_verifier
client_secret
session_cookie
serialized authorized client
~~~

Log safe metadata per policy:

~~~text
registrationId=corporate
resource=orders
result=DENIED
reason=INSUFFICIENT_SCOPE
correlationId=...
~~~

### 22.2. HTTPS and Token Destinations

Use HTTPS for token endpoints, APIs, and sensitive connections. Never pass tokens in URL query strings, as URLs appear in browser history and server logs.

### 22.3. Never Send Bearer Tokens to Arbitrary Dynamic URLs

`RestClient`/`WebClient` instances attaching tokens must target only the exact Resource Server host. Restrict redirects and never forward the `Authorization` header to foreign hosts.

### 22.4. Secrets Match Client Type

Backend confidential clients can use client secrets, mTLS, or `private_key_jwt` per the AS. Browser public clients must never rely on secrets hardcoded in JavaScript.

### 22.5. Rotation and Concurrency

If the AS rotates refresh token R1 → R2, two concurrent requests using R1 can trigger `invalid_grant` or reuse detection. Storage and managers need a concurrency strategy and must never overwrite R2 with stale R1.

## 23. Multi-Tenant API Protection

An OIDC-authenticated user may hold different memberships in different tenants:

~~~text
Alice:
  Acme -> ORDER_ADMIN
  Globex -> ORDER_VIEWER
~~~

The Orders API must verify both tenant and owner for every resource.

### 23.1. Issuer + Subject

OIDC `sub` is unique only within its issuer. When multiple OPs exist, key identity mappings on `iss` + `sub` or a trusted local user ID.

### 23.2. A Tenant Claim Is Not Automatically an Internal Tenant

A `tid` claim may follow OP-specific semantics. Never assume it matches your SaaS tenant ID without verifying mapping and semantics.

### 23.3. Service Tokens in Multi-Tenant Environments

A service token can have broad scopes. The API must constrain which tenants a service may touch; never treat `client_credentials` as a blanket license to read all tenants' data.

### 23.4. Caches and Databases Must Be Tenant-Aware Too

A cache key containing only user ID or order ID can return another tenant's data. Use tenant-aware queries and cache keys and verify object ownership.

## 24. API Gateways and Forwarded Identity

A gateway may verify the access token at the edge and forward the request to internal APIs.

### 24.1. Backends Still Need a Trust Boundary

Questions to answer:

- Does the backend verify the token itself?
- Can only the gateway reach the backend via mTLS/private network?
- Does the gateway strip/replace caller-supplied identity headers?
- Where does the backend verify tenant and resource ownership?

### 24.2. Never Trust `X-User-Id` from the Internet

If the Orders API trusts a header like:

~~~http
X-User-Id: admin
~~~

and an attacker can supply that header directly, authentication is bypassed. Forwarded identity must arrive over a well-protected trust contract, never from an untrusted client.

### 24.3. Gateways Rarely Know Per-Order Permissions

Even when a gateway verifies `orders.read`, the domain service still needs to check order, tenant, and owner permissions.

## 25. Reactive/WebFlux

The same three responsibilities apply in the Reactive stack.

| Servlet | WebFlux |
|---|---|
| `HttpSecurity.oauth2Login()` | `ServerHttpSecurity.oauth2Login()` |
| `HttpSecurity.oauth2Client()` | `ServerHttpSecurity.oauth2Client()` |
| `HttpSecurity.oauth2ResourceServer()` | `ServerHttpSecurity.oauth2ResourceServer()` |
| `OAuth2AuthorizedClientManager` | `ReactiveOAuth2AuthorizedClientManager` |
| `HttpSession` | `WebSession` |
| `SecurityContextHolder` (typically ThreadLocal) | `ReactiveSecurityContextHolder` / Reactor Context |

### 25.1. Reactive API Chain

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.web.server.SecurityWebFilterChain;

@Configuration
public class ReactiveOrdersApiSecurityConfig {

    @Bean
    SecurityWebFilterChain apiSecurity(ServerHttpSecurity http) {
        return http
                .csrf(ServerHttpSecurity.CsrfSpec::disable)
                .authorizeExchange(auth -> auth
                        .pathMatchers(HttpMethod.GET, "/api/orders/**")
                        .hasAuthority("SCOPE_orders.read")
                        .anyExchange().denyAll())
                .oauth2ResourceServer(oauth2 -> oauth2
                        .jwt(Customizer.withDefaults()))
                .build();
    }
}
~~~

This example is a Bearer-only API; do not copy CSRF disable to apps using browser cookies.

### 25.2. Reactive Managers Return `Mono`

~~~java
Mono<OAuth2AuthorizedClient> result =
        reactiveAuthorizedClientManager.authorize(request);
~~~

Compose with `flatMap`/`map`; never call `block()` or fire-and-forget `subscribe()` on the request path.

### 25.3. Do Not Rely on Servlet ThreadLocal Principals in Reactor

In WebFlux, access Authentication via `ReactiveSecurityContextHolder`. Do not assume ThreadLocal context propagates across every reactive operator or scheduler.

### 25.4. API Authorization Remains Separate from Domain Logic

A reactive Resource Server still needs issuer/audience/scope validation and tenant-aware ownership checks just like Servlet.

## 26. Testing Each Layer Independently

### 26.1. OIDC Authentication Tests

- Correct OIDC authorization redirect/callback.
- Mismatched `state` → rejected.
- Invalid ID token signature/issuer/audience → rejected.
- Nonce/PKCE enforced per policy.
- Correct `OidcUser` issuer/subject.
- Unauthenticated protected Portal page → login challenge/redirect.

### 26.2. OAuth Client Tests

- Correct registration ID, grant, and scopes.
- Authorized client holds an access token for the right Resource Server.
- Valid cached tokens can be reused.
- Refreshes occur when needed and R1 is valid.
- `invalid_grant` follows failure policy.
- `client_credentials` never impersonates a user.
- Tokens are never sent to wrong hosts/redirects.
- ID tokens are never sent instead of access tokens.

### 26.3. Resource Server Tests

| Token/request | Expected outcome |
|---|---|
| Missing Bearer token | 401 on protected endpoint |
| Invalid JWT signature | 401 |
| Wrong JWT issuer | 401 |
| Expired JWT | 401 |
| JWT audience is `billing-api` | 401 at Orders API |
| Valid token, missing scope | 403 |
| Valid token and scope, Alice's order | 200 if policy permits |
| Valid token and scope, Bob's order | 403 or 404 per API policy |
| Valid token, different tenant | 403 or 404 |
| Service token on user-only endpoint | Rejected |
| Portal ID token used as Bearer | Rejected |

### 26.4. CSRF Tests for BFF

For Portals using cookie-based sessions, verify that state-changing POST/PUT/DELETE requests require proper CSRF protection.

### 26.5. AS/API Integration Tests

Use mock OP/AS doubles or test environments. Never embed production tokens in unit tests or logs, and never disable validations just to make tests pass.

## 27. Troubleshooting

| Symptom | Likely cause | Investigation path |
|---|---|---|
| Portal logs in, API returns 401 | Wrong token issuer/audience/expiry | Access token / API validators |
| Portal logs in, API returns 403 | Missing scope or object permission | API rules / domain authorization |
| Portal sends ID token as Bearer | Confused authentication token with API token | `OidcUser` vs. `AuthorizedClient` |
| API returns HTML login page | API hits browser login chain | `SecurityFilterChain` matchers |
| CORS error | Origin/preflight configuration | CORS rules; do not confuse with token verification |
| API accepts Billing JWT | Missing audience validation | `JwtDecoder` validators |
| Missing `SCOPE_orders.read` | Claim converter mismatch | JWT `scope`/`scp` mapping |
| Service token lacks user ID | `client_credentials` semantics | Service authorization |
| Refresh fails | Missing R1 or `invalid_grant` | OAuth client provider/store |
| Logged out, yet token still calls API | Local logout vs. revocation | AS/RS policy |
| Browser POST rejected by CSRF | Unprotected session cookie or missing CSRF token | CSRF policy |
| Token appears in logs | Overly broad logging/interceptors | Redaction and incident response |
| API checks token only, not owner | BOLA/IDOR | Domain-level checks |
| Tenant A sees Tenant B data | Cache/repository lacks tenant filter | Tenant isolation |
| Forged gateway identity header | Untrusted forwarded headers | Gateway trust contract |

## 28. Common Misconceptions

**"Successful OIDC Login means the user is allowed to call every API."**

False. Portal authentication differs from API authorization; access tokens must match the target API and resource.

**"An ID token is also a JWT, so it works as a Bearer token."**

False. It carries the semantics and audience of the OIDC Relying Party.

**"`oauth2Login()` automatically protects all Bearer APIs."**

False. Resource Servers need their own configuration and authorization rules.

**"`oauth2ResourceServer()` opens a browser login flow."**

False. It verifies incoming Bearer tokens.

**"`oauth2Client()` checks order ownership."**

False. It helps the client obtain, manage, and use tokens.

**"A valid JWT signature means access is authorized."**

False. You also need issuer, audience, lifetime, scope, and domain authorization.

**"Scope `orders.read` allows reading every order."**

False. Owner and tenant checks are still required.

**"Client Credentials always involves a logged-in user."**

False. It typically represents a service/client.

**"CORS protects an API from all cross-origin callers."**

False. CORS is a browser response-reading policy, not a substitute for authentication.

**"The Portal's session automatically authenticates requests at the Orders API."**

False by default. The Orders API has its own credential and trust boundary.

**"A successful refresh token call proves the user just completed MFA."**

False.

**"Logging out of the Portal revokes the access token at the AS."**

False.

## 29. Practical Scenarios

### A. Portal Login Succeeds, Orders API Returns 401

The Portal sends an ID token with `aud=employee-portal` instead of an access token issued for the Orders API.

**Resolution:** Use an access token from `OAuth2AuthorizedClient` with the proper audience and scope; the API validates the token.

### B. Token Is Valid, Yet the API Returns 403

Alice has `orders.read`, but requests Bob's order.

**Resolution:** Domain authorization rejects due to owner/tenant mismatch. Refreshing will not fix it.

### C. Job Without an End-User

A reporting job runs every hour.

**Resolution:** Use `client_credentials`, service identity, and service authorization; never fabricate a fake `OidcUser`.

### D. API Returns a Login Page Redirect

A mobile API client omits its Bearer token and receives a 302 to HTML.

**Resolution:** Separate the bearer-only API chain and return 401 per the API contract.

### E. Access Token Expired, Portal Session Still Alive

The Portal holds an active Authentication, yet A1 has expired.

**Resolution:** The OAuth client can refresh with a valid R1, or trigger fresh authorization if needed. Do not substitute the ID token.

### F. Wrong Audience

The Orders API receives a validly signed JWT with `aud=billing-api`.

**Resolution:** Add/enforce audience validation and reject it.

### G. Mixed Tenant Roles

Alice is admin in Acme and viewer in Globex.

**Resolution:** Evaluate roles and resource checks under the active tenant; never reuse Acme's admin role inside Globex.

### H. BFF Disables CSRF Because "We Use OAuth2"

The browser submits a `POST` to the Portal using a cookie.

**Resolution:** Keep CSRF protection enabled because the cookie is an ambient credential.

### I. Gateway Verified the Token, Backend Trusts Any Header

The backend accepts `X-User-Id` straight from the Internet.

**Resolution:** Enforce the gateway/backend trust boundary, strip/overwrite headers, and enforce domain permissions.

### J. Overprivileged Service Token Used on Alice's Behalf

The Portal uses a service token to fetch all orders without checking user permissions.

**Resolution:** Apply user delegation, least privilege, object-level authorization, and proper auditing.

## 30. Self-Check Questions

**1. What question does OIDC user authentication answer?**

Who the OP authenticated and who is logged into the RP.

**2. What question does OAuth2 Client Authorization answer?**

Which scopes and Resource Servers the AS granted the client an access token for.

**3. What question does a Resource Server answer?**

Whether an incoming request holds valid credentials and sufficient permissions for the resource.

**4. Should an ID token be sent as a Bearer access token to an API?**

No, not in standard OAuth2 Resource Server architecture.

**5. Does the Portal's session cookie automatically authenticate at the Orders API?**

No, unless the API explicitly participates in a deliberately designed shared session trust mechanism.

**6. What is `OAuth2AuthorizedClient`?**

The OAuth access/refresh token state bound to a `ClientRegistration` and a principal.

**7. What is `oauth2Login()` used for?**

Handling browser OAuth2/OIDC Login and creating a local Authentication.

**8. What is `oauth2Client()` used for?**

Authorizing, managing, and using access tokens for outbound calls.

**9. What is `oauth2ResourceServer()` used for?**

Authenticating incoming Bearer tokens on an API.

**10. Is a valid JWT signature enough for authorization?**

No. You still need issuer, audience, lifetime, scope, and owner/tenant authorization.

**11. Does `SCOPE_orders.read` grant access to every order?**

No.

**12. Does Client Credentials include an End-User login?**

Not required, and typically absent.

**13. Are Token Relay and Token Exchange the same?**

No. Relay forwards an existing valid token; Exchange requests a new token from the AS.

**14. Can CORS replace JWT validation?**

No.

**15. Do a bearer-only API and a cookie-based Portal share the same CSRF threat model?**

No. Cookie-based browser sessions require CSRF protection; Bearer-header-only APIs differ.

**16. Does a refresh token prove MFA just happened?**

No.

**17. How do 401 and 403 differ?**

401 usually means missing or invalid credentials; 403 usually means insufficient permissions.

**18. Does logging out of the Portal revoke access tokens at the AS automatically?**

No.

**19. Why validate audience?**

So an API rejects tokens issued for another API or client.

**20. Why do you still need tenant/owner checks when scopes exist?**

Scopes do not express permissions on individual objects.

## Summary

- **OIDC authenticates users**, **OAuth2 Client manages authorization to use access tokens**, and **Resource Server validates tokens and enforces API permissions**. These three responsibilities are related but never interchangeable.
- **ID tokens belong to the OIDC Relying Party, access tokens belong to the Resource Server, and refresh tokens belong to the AS token endpoint**. Never interchange them.
- **`oauth2Login()`, `oauth2Client()`, and `oauth2ResourceServer()` serve distinct purposes** in Spring Security.
- **APIs must verify issuer, audience, expiry, scopes, and domain permissions**; a valid JWT signature alone never grants access to arbitrary objects.
- **Client Credentials represents a service identity**, with no user by default. Never use broad service tokens to bypass End-User permissions.
- **Scopes never replace ownership or tenant checks**; the Resource Server and business layer must enforce authorization on specific resources.
- **Session cookies and Bearer tokens carry different trust, CSRF, and error semantics**. Separate web UI and Bearer API boundaries where needed.
- **Token Relay, Token Exchange, refresh, and logout are distinct mechanisms**; never escalate privileges or treat refresh as reauthentication.
- **Never log tokens or send Bearer tokens to arbitrary hosts**; use HTTPS, dedicated HTTP clients, destination allowlists, and negative tests.
