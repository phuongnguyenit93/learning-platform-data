# 34.7. WebFlux Application with OIDC Login and Downstream Calls

## Practice Objectives

This lab builds a complete example of **Spring Security OAuth 2.0 / OpenID Connect (OIDC) Client on WebFlux**: users sign into a Reactive Portal via an OpenID Provider, the Portal manages the OAuth2 authorized client, and then `WebClient` sends the access token to a downstream Orders API protected as a Resource Server.

Expected outcomes:

- Portal at `http://localhost:8080` uses **WebFlux + OIDC Login**.
- Orders API at `http://localhost:8081` uses **WebFlux + JWT Resource Server**.
- The OpenID Provider/Authorization Server (OP/AS) is a standalone system configured in a local or test environment.
- The browser holds the Portal's session cookie; **never receives refresh tokens in JSON**.
- Portal uses `ReactiveOAuth2AuthorizedClientManager` and `ServerOAuth2AuthorizedClientExchangeFilterFunction` to obtain and attach the access token when calling the API.
- Orders API validates token signature, issuer, expiry, audience, and the `orders.read` scope.
- Missing authentication, wrong audience, missing scope, and wrong-host errors are handled safely.
- All downstream HTTP work is composed with `Mono`/`Flux`, never calling `block()` in the request path.

After finishing, you can extend this to Redis-backed sessions, multi-tenant access control, token refresh, and reactive integration tests.

> **Important:** The ID token authenticates the user to the Portal; the access token authorizes calls to the Orders API. The two tokens are not interchangeable. Configuring OIDC Login does not automatically turn the Portal into a Resource Server, and the API cannot trust the Portal's session cookie.

---

## 1. Architecture to Build

~~~mermaid
flowchart LR
    B["Alice / Browser"] -->|"Portal cookie"| P["Reactive Portal :8080"]
    P -->|"OIDC Code exchange, refresh"| OP["OpenID Provider / AS"]
    OP -->|"ID + access token"| P
    P -->|"Bearer access token"| API["Orders API :8081"]
    API -->|"JWT validation / JWKS"| OP
    API -->|"Owner + tenant policy"| DB["Orders database"]
    API -->|"Orders JSON"| P
    P -->|"JSON / HTML"| B
~~~

### 1.1. Three Security Boundaries

| Boundary | Primary Credential | Verifier |
|---|---|---|
| Browser → Portal | Session cookie | Portal |
| Portal → OP token endpoint | Authorization code/refresh token, client authentication | AS |
| Portal → Orders API | OAuth access token | Orders API Resource Server |

A web session cookie has no validity at the Orders API. An ID token whose audience is the OIDC Relying Party is not an API Bearer token.

### 1.2. Why Choose BFF?

The Portal operates as a **Backend for Frontend**: the browser interacts with the Portal via cookies, the backend holds access/refresh tokens, and `WebClient` calls the API. As a result, the browser never needs to store raw refresh tokens in `localStorage`.

A BFF design must still protect CSRF, XSS, cookies, session fixation, server-side token stores, redirects, and destination hosts.

### 1.3. Responsibilities That Must Stay Separate

- **OIDC Authentication**: OP authenticates Alice; Portal gets an `OidcUser`.
- **OAuth2 Client Authorization**: AS issues an access token for the right resource/scope; Portal gets an `OAuth2AuthorizedClient`.
- **API Authorization**: Orders API verifies the token and per-order permissions.

A successful OIDC login does not mean Alice is permitted to view every order.

## 2. Environment Preparation

You need a JDK compatible with Spring Boot 3.x / Spring Framework 6.x, Maven or Gradle, and an OpenID Connect-compatible OP (e.g., running locally or in staging).

At the OP, configure a **confidential client**:

~~~text
Issuer URI:       https://id.example.test/realms/demo
Client ID:        reactive-portal
Client Secret:    <test-secret>
Authorization:    authorization_code
Redirect URI:     http://localhost:8080/login/oauth2/code/corporate
Requested scopes: openid profile orders.read
API audience:     orders-api
Test user:        alice-123
~~~

These URLs are placeholders. When running for real, replace them with real issuers/endpoints and ensure **both the Portal and Orders API can reach the issuer and JWKS**.

### 2.1. Scope Alone Does Not Guarantee Audience

Many OPs do not automatically issue an access token with `aud=orders-api` simply because the client requests `orders.read`. You may need to register an API resource, audience mapper, or authorization policy at the OP.

### 2.2. Proper Sample Token

A JWT access token for the Orders API might look like:

~~~json
{
  "iss": "https://id.example.test/realms/demo",
  "sub": "alice-123",
  "aud": ["orders-api"],
  "scope": "orders.read",
  "exp": 1795000000
}
~~~

Illustrative claims, not a real JWT. Access tokens may also be opaque; in that case, switch Resource Server validation to introspection.

### 2.3. Never Commit Client Secrets

Store `OIDC_CLIENT_SECRET` in a secret store or server environment variables. Never put client secrets into source code, frontend bundles, or Git.

## 3. Structure of the Two Applications

~~~text
reactive-oidc-lab/
├── portal/
│   ├── pom.xml
│   └── src/main/
│       ├── java/com/example/portal/
│       │   ├── PortalApplication.java
│       │   ├── PortalSecurityConfig.java
│       │   ├── PortalOAuthClientConfig.java
│       │   ├── OrdersGateway.java
│       │   └── PortalController.java
│       └── resources/application.yml
└── orders-api/
    ├── pom.xml
    └── src/main/
        ├── java/com/example/orders/
        │   ├── OrdersApiApplication.java
        │   ├── ApiSecurityConfig.java
        │   ├── JwtAudienceConfig.java
        │   └── OrdersController.java
        └── resources/application.yml
~~~

Each app has its own `@SpringBootApplication` and process. Never share `SecurityContext` or `WebSession` between the Portal and the Resource Server.

## 4. Creating the Portal: Dependencies

In the Portal's Spring Boot Maven project:

~~~xml
<dependencies>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-webflux</artifactId>
    </dependency>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-oauth2-client</artifactId>
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
~~~

Use the Boot BOM to manage versions. For WebFlux, do not add the Servlet MVC starter if your goal is a pure reactive web application.

### 4.1. What Does `webflux` Provide?

Reactor's `Mono` and `Flux`, `WebClient`, and reactive HTTP handling. Spring Security uses `SecurityWebFilterChain` instead of Servlet `SecurityFilterChain`.

### 4.2. `oauth2-client` vs. `oauth2-resource-server`

The Portal needs the OAuth2 Client starter to log in and call APIs. The Orders API needs the Resource Server starter to verify incoming Bearer tokens.

## 5. Configuring the Portal OIDC Client

`portal/src/main/resources/application.yml`:

~~~yaml
server:
  port: 8080

spring:
  security:
    oauth2:
      client:
        registration:
          corporate:
            provider: company-op
            client-id: ${OIDC_CLIENT_ID}
            client-secret: ${OIDC_CLIENT_SECRET}
            client-authentication-method: client_secret_basic
            authorization-grant-type: authorization_code
            redirect-uri: "{baseUrl}/login/oauth2/code/{registrationId}"
            scope:
              - openid
              - profile
              - orders.read
        provider:
          company-op:
            issuer-uri: ${OIDC_ISSUER_URI}

app:
  orders-api:
    base-url: ${ORDERS_API_BASE_URL:http://localhost:8081}
~~~

### 5.1. Registration ID Is `corporate`

It appears in both the authorization initiation and callback routes:

~~~text
/oauth2/authorization/corporate
/login/oauth2/code/corporate
~~~

### 5.2. `openid` Requests OIDC

When the OIDC flow succeeds, Spring Security validates the ID token and builds an `OidcUser`. The `profile` scope provides profile claims if permitted by the OP.

### 5.3. `orders.read` Is an OAuth Scope

This scope only requests token permissions; Orders API must still verify the token's scope, audience, issuer, and domain permissions.

### 5.4. Exact Callback at the OP

The OP must allowlist redirect URI `http://localhost:8080/login/oauth2/code/corporate` in local development. Production must use the exact public HTTPS origin.

### 5.5. Reverse Proxy

If TLS terminates at an ingress, configure trusted forwarded headers and the right base URL. Never let the Internet supply arbitrary forwarded headers to alter redirect URIs.

## 6. `PortalApplication`

~~~java
package com.example.portal;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class PortalApplication {
    public static void main(String[] args) {
        SpringApplication.run(PortalApplication.class, args);
    }
}
~~~

Run the application with Maven/Gradle per project setup. Ensure `OIDC_ISSUER_URI` points to an issuer with valid discovery metadata and JWKS.

## 7. Reactive `SecurityWebFilterChain`

~~~java
package com.example.portal;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.web.server.SecurityWebFilterChain;

@Configuration
public class PortalSecurityConfig {

    @Bean
    SecurityWebFilterChain portalSecurity(
            ServerHttpSecurity http) {

        return http
                .authorizeExchange(auth -> auth
                        .pathMatchers("/", "/login", "/error")
                        .permitAll()
                        .anyExchange().authenticated())
                .oauth2Login(Customizer.withDefaults())
                .oauth2Client(Customizer.withDefaults())
                .build();
    }
}
~~~

### 7.1. `oauth2Login()`

Handles browser redirects, state/callback correlation, code exchange, ID token validation, and creating the Portal's `Authentication`.

### 7.2. `oauth2Client()`

Enables OAuth2 authorized-client infrastructure for outbound API calls. It does not protect the Orders API on its own.

### 7.3. `authorizeExchange(...)`

WebFlux uses `authorizeExchange` instead of Servlet `authorizeHttpRequests`.

### 7.4. Keep CSRF Enabled for the Portal

The Portal uses browser cookies. Do not disable CSRF globally just because OAuth2 is used; state-changing POST/PUT/DELETE endpoints need CSRF protection by design.

### 7.5. Authentication Differs from Domain Authorization

`authenticated()` does not prove Alice is allowed to access every tenant or order. Fine-grained permissions belong to the API/domain service.

## 8. Starting OIDC Login

Open:

~~~text
http://localhost:8080/oauth2/authorization/corporate
~~~

Sequence of events:

1. Portal creates an Authorization Request with `state` and OIDC parameters.
2. Browser redirects to the OP.
3. OP authenticates Alice and asks for consent if required by policy.
4. OP redirects back to Portal with `code` and `state`.
5. Spring Security matches the pending authorization request.
6. Portal exchanges the code at the token endpoint.
7. Spring Security validates the ID token and creates `Authentication`.
8. Session and authorized-client state are saved per configuration.

Never take an authorization code from the browser and send it manually to another API. Never disable state/nonce/PKCE validation when callbacks fail.

## 9. Reading the OIDC Principal

Create a controller that exposes only minimal identity:

~~~java
package com.example.portal;

import org.springframework.security.core.annotation
        .AuthenticationPrincipal;
import org.springframework.security.oauth2.core.oidc.user.OidcUser;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;
import reactor.core.publisher.Mono;

@RestController
public class MeController {

    @GetMapping("/me")
    Mono<MeView> me(
            @AuthenticationPrincipal OidcUser user) {

        return Mono.just(new MeView(
                user.getIdToken().getIssuer().toString(),
                user.getIdToken().getSubject(),
                user.getFullName()));
    }

    record MeView(
            String issuer, String subject, String displayName) {}
}
~~~

### 9.1. OIDC Authentication

`OAuth2AuthenticationToken` normally holds an `OidcUser` principal along with the registration ID. `OidcUser` contains the ID token and optionally UserInfo claims.

### 9.2. Subject Is Not Globally Unique

OIDC `sub` is scoped to its `iss`. Multi-OP systems must use `issuer + subject` or a verified internal identity mapping.

### 9.3. Never Serialize Raw OIDC Objects

Never return `OidcUser`, ID tokens, access tokens, or refresh tokens directly in browser JSON. Return a DTO containing only the claims actually needed by the UI.

### 9.4. Display Name May Be Missing

Never rely on email or display name as an authorization identity key.

## 10. `OidcUser` vs. `OAuth2AuthorizedClient`

~~~text
OAuth2AuthenticationToken
  principal = OidcUser
  authenticated = true
  registrationId = corporate

OAuth2AuthorizedClient
  clientRegistration = corporate
  principalName = Alice
  accessToken = A1
  refreshToken = R1 (if issued by AS)
~~~

| Token / Credential | Role | Destination |
|---|---|---|
| ID token | Tells Portal that OP authenticated Alice | Relying Party / Portal |
| Access token | Authorizes calls to protected resources | Orders API matching audience |
| Refresh token | Requests a new access token | AS token endpoint |
| Session cookie | Identifies browser's Portal session | Portal |
| Client secret | Confidential client authentication | AS token endpoint |

**Never use `user.getIdToken().getTokenValue()` as the Bearer token sent to Orders API.** The access token comes from `OAuth2AuthorizedClient`.

## 11. Reactive `OAuth2AuthorizedClientManager`

Create the manager to look up the current authorized client and refresh it when needed.

~~~java
package com.example.portal;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.oauth2.client
        .ReactiveOAuth2AuthorizedClientManager;
import org.springframework.security.oauth2.client
        .ReactiveOAuth2AuthorizedClientProviderBuilder;
import org.springframework.security.oauth2.client.registration
        .ReactiveClientRegistrationRepository;
import org.springframework.security.oauth2.client.web
        .DefaultReactiveOAuth2AuthorizedClientManager;
import org.springframework.security.oauth2.client.web.server
        .ServerOAuth2AuthorizedClientRepository;

@Configuration
public class PortalOAuthClientConfig {

    @Bean
    ReactiveOAuth2AuthorizedClientManager authorizedClientManager(
            ReactiveClientRegistrationRepository registrations,
            ServerOAuth2AuthorizedClientRepository authorizedClients) {

        var provider =
                ReactiveOAuth2AuthorizedClientProviderBuilder.builder()
                        .authorizationCode()
                        .refreshToken()
                        .build();

        var manager =
                new DefaultReactiveOAuth2AuthorizedClientManager(
                        registrations, authorizedClients);

        manager.setAuthorizedClientProvider(provider);
        return manager;
    }
}
~~~

### 11.1. Reactive Contract

`ReactiveOAuth2AuthorizedClientManager.authorize(...)` returns `Mono<OAuth2AuthorizedClient>`. It does not force the application to call `block()` to wait for the access token.

### 11.2. Provider Chain

`authorizationCode()` supports interactive login authorizations, while `refreshToken()` handles expired or expiring access tokens when a valid refresh token is present.

### 11.3. Store Must Be Keyed by the Right Principal

Authorized clients are stored per registration/user/session. Never store one static singleton access token for all users.

### 11.4. Across Multiple Pods

`WebSession`, pending state, and authorized-client storage require shared persistence or appropriate sticky routing. Never disable OAuth state validation to fix callbacks landing on another Pod.

### 11.5. Background Jobs

Services running outside a web exchange should use `AuthorizedClientServiceReactiveOAuth2AuthorizedClientManager` matching their version rather than a manager tied to `ServerWebExchange`.

## 12. `WebClient` with the OAuth2 Filter

~~~java
package com.example.portal;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.oauth2.client
        .ReactiveOAuth2AuthorizedClientManager;
import org.springframework.security.oauth2.client.web.reactive.function.client
        .ServerOAuth2AuthorizedClientExchangeFilterFunction;
import org.springframework.web.reactive.function.client.WebClient;

@Configuration
public class OrdersWebClientConfig {

    @Bean
    WebClient ordersApiWebClient(
            ReactiveOAuth2AuthorizedClientManager manager,
            @Value("${app.orders-api.base-url}") String apiBaseUrl) {

        var oauth2 =
                new ServerOAuth2AuthorizedClientExchangeFilterFunction(
                        manager);

        return WebClient.builder()
                .baseUrl(apiBaseUrl)
                .filter(oauth2)
                .build();
    }
}
~~~

### 12.1. What Does the OAuth2 Exchange Filter Do?

When an outbound request carries an `OAuth2AuthorizedClient` in its attributes, the filter adds the access token header:

~~~http
Authorization: Bearer ACCESS_TOKEN_VALUE
~~~

### 12.2. Keep the URL Fixed

The base URL comes from trusted backend configuration. Never let callers supply arbitrary hosts and attach Bearer tokens.

### 12.3. Do Not Enable Default Token Forwarding for Every Request

Pass an explicit authorized client per request. If the filter automatically attaches the default principal to every host, tokens can leak to unintended outbound URLs.

### 12.4. The API Still Validates the Token Independently

Having an `Authorization` header does not guarantee the token is valid for the Orders API.

## 13. `OrdersGateway`: Authorize and Call the API

~~~java
package com.example.portal;

import java.util.List;
import org.springframework.http.HttpStatus;
import org.springframework.security.core.Authentication;
import org.springframework.security.oauth2.client.OAuth2AuthorizeRequest;
import org.springframework.security.oauth2.client
        .ReactiveOAuth2AuthorizedClientManager;
import org.springframework.security.oauth2.client.web.reactive.function.client
        .ServerOAuth2AuthorizedClientExchangeFilterFunction;
import org.springframework.stereotype.Component;
import org.springframework.web.reactive.function.client.WebClient;
import org.springframework.web.server.ResponseStatusException;
import org.springframework.web.server.ServerWebExchange;
import reactor.core.publisher.Mono;

@Component
public class OrdersGateway {

    private final WebClient ordersWebClient;
    private final ReactiveOAuth2AuthorizedClientManager manager;

    public OrdersGateway(
            WebClient ordersApiWebClient,
            ReactiveOAuth2AuthorizedClientManager manager) {
        this.ordersWebClient = ordersApiWebClient;
        this.manager = manager;
    }

    public Mono<List<OrderView>> list(
            Authentication authentication,
            ServerWebExchange exchange) {

        OAuth2AuthorizeRequest request =
                OAuth2AuthorizeRequest
                        .withClientRegistrationId("corporate")
                        .principal(authentication)
                        .attribute(
                                ServerWebExchange.class.getName(),
                                exchange)
                        .build();

        return manager.authorize(request)
                .switchIfEmpty(Mono.error(
                        new ResponseStatusException(
                                HttpStatus.UNAUTHORIZED,
                                "OAuth client authorization required")))
                .flatMap(authorized ->
                        ordersWebClient.get()
                                .uri("/api/orders")
                                .attributes(
                                        ServerOAuth2AuthorizedClientExchangeFilterFunction
                                                .oauth2AuthorizedClient(
                                                        authorized))
                                .retrieve()
                                .bodyToFlux(OrderView.class)
                                .collectList());
    }

    public record OrderView(String id, String status) {}
}
~~~

### 13.1. Why Is `Authentication` Needed?

The manager needs the current principal to look up the authorized client belonging to that user.

### 13.2. Why Pass `ServerWebExchange`?

The WebFlux manager/repository needs the web request/session context to load and save the authorized client.

### 13.3. `switchIfEmpty`

If the manager cannot authorize and returns an empty publisher, the application handles it explicitly rather than dereferencing null.

### 13.4. `oauth2AuthorizedClient(authorized)`

This is the request attribute for the OAuth2 filter. The filter extracts the **access token** from the authorized client, never the ID token.

### 13.5. Never Call `block()`

`OrdersGateway.list()` returns `Mono<List<OrderView>>`. WebFlux manages subscription; never block the event loop waiting for `WebClient`.

### 13.6. Never Call Hosts from User Input

`.uri("/api/orders")` is a relative path under the trusted base URL. Accepting `?url=https://attacker.example` and forwarding tokens creates SSRF and token exfiltration vulnerabilities.

## 14. `PortalController` for the Browser

~~~java
package com.example.portal;

import java.util.List;
import org.springframework.security.core.Authentication;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.server.ServerWebExchange;
import reactor.core.publisher.Mono;

@RestController
public class PortalController {

    private final OrdersGateway gateway;

    public PortalController(OrdersGateway gateway) {
        this.gateway = gateway;
    }

    @GetMapping("/orders")
    Mono<List<OrdersGateway.OrderView>> orders(
            Authentication authentication,
            ServerWebExchange exchange) {

        return gateway.list(authentication, exchange);
    }
}
~~~

### 14.1. Browser Sends Only the Cookie

~~~http
GET /orders HTTP/1.1
Host: localhost:8080
Cookie: SESSION=...
~~~

The Portal translates this into a server-side API request with a Bearer access token. The browser must never be allowed to ask the Portal for raw access tokens.

### 14.2. `Authentication` Differs from Principal Name

`Authentication.getName()` is not necessarily an email. Never use email as a security key when the OP provides an immutable subject.

### 14.3. Never Store `Authentication` in a Singleton Field

Reactive requests serve many users concurrently. Pass `Authentication` through the reactive context or method parameters, never in a `currentUser` field on a singleton bean.

## 15. Alternative: `@RegisteredOAuth2AuthorizedClient`

In Spring Security versions supporting WebFlux controller argument resolution, you can inject the authorized client directly:

~~~java
@GetMapping("/orders/alternative")
Mono<List<OrdersGateway.OrderView>> alternative(
        @RegisteredOAuth2AuthorizedClient("corporate")
        OAuth2AuthorizedClient client) {

    return ordersWebClient.get()
            .uri("/api/orders")
            .attributes(
                    ServerOAuth2AuthorizedClientExchangeFilterFunction
                            .oauth2AuthorizedClient(client))
            .retrieve()
            .bodyToFlux(OrdersGateway.OrderView.class)
            .collectList();
}
~~~

This illustrative method belongs inside a controller with `ordersWebClient` injected. Imports: `org.springframework.security.oauth2.client.annotation.RegisteredOAuth2AuthorizedClient` and `org.springframework.security.oauth2.client.OAuth2AuthorizedClient`.

### 15.1. When to Choose the Annotation?

When the controller simply needs the authorized client for the active login registration. For complex token lifecycle, refresh, or error policies, calling the manager explicitly offers finer control and easier testing.

### 15.2. Do Not Treat the Annotation as Proof of Proper Refresh

Test the authorized-client repository, manager, and token endpoint independently to verify refresh, rotation, and persistence.

## 16. Orders API Dependencies

`orders-api/pom.xml`:

~~~xml
<dependencies>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-webflux</artifactId>
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
~~~

### 16.1. The API Is a Resource Server

Orders API does not perform OIDC browser login. It receives access tokens from the Portal and verifies incoming Bearer authentication.

### 16.2. Never Use the Portal Session

Orders API does not trust Portal cookies or accept serialized `SecurityContext` objects over the network.

## 17. Orders API Configuration

`orders-api/src/main/resources/application.yml`:

~~~yaml
server:
  port: 8081

spring:
  security:
    oauth2:
      resourceserver:
        jwt:
          issuer-uri: ${OIDC_ISSUER_URI}

app:
  security:
    required-audience: orders-api
~~~

`app.security.required-audience` is a **custom property** read by the validator in the next section. Spring Security does not automatically enforce audience merely because a custom property exists.

## 18. Orders API `SecurityWebFilterChain`

~~~java
package com.example.orders;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.web.server.SecurityWebFilterChain;
import org.springframework.security.web.server.context
        .NoOpServerSecurityContextRepository;

@Configuration
public class ApiSecurityConfig {

    @Bean
    SecurityWebFilterChain apiSecurity(ServerHttpSecurity http) {

        return http
                .csrf(ServerHttpSecurity.CsrfSpec::disable)
                .securityContextRepository(
                        NoOpServerSecurityContextRepository
                                .getInstance())
                .authorizeExchange(auth -> auth
                        .pathMatchers(
                                HttpMethod.GET, "/api/orders")
                        .hasAuthority("SCOPE_orders.read")
                        .anyExchange().denyAll())
                .oauth2ResourceServer(oauth2 -> oauth2
                        .jwt(Customizer.withDefaults()))
                .build();
    }
}
~~~

### 18.1. Why Does the API Disable CSRF?

This example is a **bearer-only API** that does not rely on browser cookies or sessions for authentication. Therefore, CSRF token checks can be disabled here. Never copy this into the session-cookie-based Portal.

### 18.2. `SCOPE_orders.read`

Spring Security JWT Resource Server maps `scope` or `scp` claims into authorities prefixed with `SCOPE_`. If the OP emits a different claim format, configure a converter per contract.

### 18.3. Stateless Security Context

`NoOpServerSecurityContextRepository` prevents storing API `Authentication` in a web session. The API verifies the Bearer token on every incoming request.

### 18.4. API Needs Object-Level Authorization

Scopes are coarse-grained permissions. In production, verify tenant/owner and domain rules for each order.

## 19. JWT Audience Validation

A JWT signed by the right issuer but issued for the Billing API must be rejected by the Orders API.

~~~java
package com.example.orders;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.oauth2.core.DelegatingOAuth2TokenValidator;
import org.springframework.security.oauth2.core.OAuth2Error;
import org.springframework.security.oauth2.core.OAuth2TokenValidator;
import org.springframework.security.oauth2.core.OAuth2TokenValidatorResult;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.security.oauth2.jwt.JwtValidators;
import org.springframework.security.oauth2.jwt.NimbusReactiveJwtDecoder;
import org.springframework.security.oauth2.jwt.ReactiveJwtDecoder;

@Configuration
public class JwtAudienceConfig {

    @Bean
    ReactiveJwtDecoder jwtDecoder(
            @Value("${spring.security.oauth2.resourceserver.jwt.issuer-uri}")
            String issuer,
            @Value("${app.security.required-audience}")
            String audience) {

        NimbusReactiveJwtDecoder decoder =
                NimbusReactiveJwtDecoder
                        .withIssuerLocation(issuer)
                        .build();

        OAuth2TokenValidator<Jwt> audienceValidator = jwt -> {
            if (jwt.getAudience().contains(audience)) {
                return OAuth2TokenValidatorResult.success();
            }
            return OAuth2TokenValidatorResult.failure(
                    new OAuth2Error(
                            "invalid_token",
                            "Orders API audience required",
                            null));
        };

        decoder.setJwtValidator(
                new DelegatingOAuth2TokenValidator<>(
                        JwtValidators.createDefaultWithIssuer(issuer),
                        audienceValidator));

        return decoder;
    }
}
~~~

### 19.1. What the Decoder Validates

Using the trusted issuer/JWKS, the decoder verifies the signature and standard validity claims via validators. The custom audience validator requires the token to target the Orders API.

### 19.2. ID Tokens Are Unsuitable

An OIDC ID token usually has `aud=reactive-portal`. The API requires an access token with `aud=orders-api`; thus an ID token must never be accepted in place of an access token.

### 19.3. Scope Alone Is Not Enough

Beyond audience, the security chain requires `SCOPE_orders.read`. If a JWT only carries `profile`, the request receives 403 even when token authentication succeeds.

### 19.4. Never Trust Arbitrary JWKS URLs

Issuer and JWKS locations must come from trusted configuration, never from a browser-supplied host.

## 20. Orders API Controller

~~~java
package com.example.orders;

import org.springframework.security.core.annotation.AuthenticationPrincipal;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;
import reactor.core.publisher.Flux;

@RestController
@RequestMapping("/api/orders")
public class OrdersController {

    @GetMapping
    Flux<OrderView> list(@AuthenticationPrincipal Jwt jwt) {

        return Flux.just(
                new OrderView(
                        "demo-" + jwt.getSubject() + "-001",
                        "READY"),
                new OrderView(
                        "demo-" + jwt.getSubject() + "-002",
                        "PROCESSING"));
    }

    record OrderView(String id, String status) {}
}
~~~

### 20.1. Demo Data Only

This example fabricates orders from the validated JWT subject rather than querying a production repository. In real systems, query data scoped to the verified tenant/user and enforce owner permissions.

### 20.2. Service Tokens vs. Human Users

If the API also accepts `client_credentials`, `sub` may identify a client/service rather than a human user. Enforce an appropriate authorization policy.

### 20.3. Never Echo Raw Tokens

JSON responses must contain only business data, never echoing the `Authorization` header or raw JWT.

## 21. `OrdersApiApplication`

~~~java
package com.example.orders;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class OrdersApiApplication {
    public static void main(String[] args) {
        SpringApplication.run(OrdersApiApplication.class, args);
    }
}
~~~

The API listens on port 8081 per YAML.

## 22. Running End-to-End in Order

1. **Prepare OP:** create confidential client, user Alice, redirect URI, and audience/scope for Orders API.
2. **Set environment variables:** `OIDC_ISSUER_URI`, `OIDC_CLIENT_ID`, `OIDC_CLIENT_SECRET`, `ORDERS_API_BASE_URL`.
3. **Start Orders API:** port 8081; ensure JWKS/issuer are reachable.
4. **Start Portal:** port 8080.
5. **Open `/oauth2/authorization/corporate`:** complete login at the OP.
6. **Open `/me`:** inspect the issuer/subject of the authenticated OIDC principal.
7. **Open `/orders`:** Portal uses the access token and `WebClient` to call Orders API.
8. **Verify failure cases:** test tokens lacking audience or scope using a fake OP or test JWTs.

### 22.1. Example Environment Variables

~~~powershell
$env:OIDC_ISSUER_URI = "https://id.example.test/realms/demo"
$env:OIDC_CLIENT_ID = "reactive-portal"
$env:OIDC_CLIENT_SECRET = "<test-secret>"
$env:ORDERS_API_BASE_URL = "http://localhost:8081"
~~~

Replace placeholders with a real local or staging OP. Never use production credentials for practice labs.

### 22.2. Login Does Not Necessarily Land Directly on `/orders`

After login, Spring Security may redirect to a saved request or default success URL. Once the session is active, request `/orders` to verify downstream calls.

### 22.3. Portal Session Cookie

The browser sends the session cookie to `localhost:8080`. The Portal never forwards that cookie as a Bearer token to the API.

### 22.4. When the API Returns 401

Check audience, issuer, signature, expiry, and whether the Portal attached the access token; never disable validation just to get 200.

## 23. Sequence Diagram

~~~mermaid
sequenceDiagram
    autonumber
    actor User
    participant Browser
    participant Portal as Reactive Portal
    participant OP as OIDC Provider
    participant API as Orders API

    User->>Browser: Open /orders
    Browser->>Portal: GET /orders (anonymous)
    Portal-->>Browser: Redirect OP
    Browser->>OP: Authorization request
    OP->>OP: User authentication/consent
    OP-->>Browser: Redirect code + state
    Browser->>Portal: Callback with session
    Portal->>Portal: Correlate state
    Portal->>OP: Exchange code
    OP-->>Portal: ID token + access token
    Portal->>Portal: Validate ID token, store Authentication
    Portal-->>Browser: Browser session + redirect
    Browser->>Portal: GET /orders + cookie
    Portal->>Portal: Load/refresh authorized client
    Portal->>API: GET /api/orders + Bearer access token
    API->>API: Verify issuer, aud, exp, scope
    API-->>Portal: Orders JSON
    Portal-->>Browser: Orders JSON
~~~

### 23.1. Token Exchange Differs from Browser Redirects

The browser goes to the authorization endpoint; the backend calls the token endpoint. Each step uses a separate HTTP client and security boundary.

### 23.2. Independent Resource Server Authentication

Orders API does not need `OidcUser` from the Portal. It builds `Authentication` directly from the validated access token.

## 24. Reactor Context and Avoiding Blocking

### 24.1. Do Not Rely on ThreadLocal `SecurityContextHolder` Like Servlet

Reactive Spring Security uses `ReactiveSecurityContextHolder` and Reactor Context. Execution threads can switch across operators and schedulers.

### 24.2. Reading Reactive `Authentication`

~~~java
ReactiveSecurityContextHolder.getContext()
        .map(context -> context.getAuthentication())
~~~

Import `org.springframework.security.core.context.ReactiveSecurityContextHolder`.

### 24.3. Never Call `block()`

Wrong:

~~~java
List<OrderView> orders = ordersWebClient.get()
        .uri("/api/orders")
        .retrieve()
        .bodyToFlux(OrderView.class)
        .collectList()
        .block();
~~~

`block()` on a WebFlux request path stalls the event loop. Return `Mono<List<OrderView>>` so the pipeline can be subscribed, cancelled, and managed naturally.

### 24.4. Never Manually `subscribe()` and Return Early

Wrong:

~~~java
ordersWebClient.get()
        .uri("/api/orders")
        .retrieve()
        .bodyToMono(String.class)
        .subscribe();

return Mono.just("done");
~~~

This bypasses backpressure, error propagation, and request lifecycle management. Compose reactive publishers instead.

### 24.5. Bound Concurrency

When batching many downstream calls, use bounded `flatMap(..., concurrency)` and a configured connection pool; non-blocking I/O does not give HTTP services infinite capacity.

## 25. Refresh Token Lifecycle

When a user logs in, the OP may return:

~~~text
Access token A1, expiresAt 11:00
Refresh token R1 (if issued by OP)
~~~

### 25.1. Token Still Valid

The manager reuses `A1` rather than sending a refresh grant every time the user reads orders.

### 25.2. Token Near Expiration

The refresh provider uses `R1` to request `A2`; if the AS rotates refresh tokens, it also returns `R2`, which must be persisted.

### 25.3. No Refresh Token

The OP may omit `R1` depending on policy. If `A1` expires and the manager cannot refresh, initiate a re-authorization/login flow per policy.

### 25.4. Refresh Does Not Prove Fresh MFA

A refresh token grant is not a new interactive user authentication. If an operation requires step-up authentication, trigger an OIDC authentication request per OP policy.

### 25.5. Rotation Races

If two Pods refresh `R1` simultaneously, one request can hit `invalid_grant` or trigger reuse detection. Implement single-flight locking, version/CAS checks, and shared storage strategies.

### 25.6. Timeouts Do Not Prove the AS Did Not Rotate

If the refresh response is lost after the AS already issued `R2`, blindly retrying `R1` will fail. Never attach generic retry interceptors to token POST requests.

## 26. 401, 403, and Downstream Errors

By default, `WebClient.retrieve()` errors on 4xx/5xx responses. A BFF should map errors safely rather than forwarding raw downstream bodies or headers to the browser.

| Status | Common Cause | Resolution |
|---|---|---|
| 401 API | Missing/invalid Bearer access token | Check signature, issuer, audience, expiry |
| 403 API | Missing scope or tenant/owner permission | Check API authorization |
| 429 API | Quota/rate limit | Bounded backoff per operation |
| 503 API | Service unavailable | Fail fast/circuit breaker; retry only when safe |

### 26.1. Example Mapping 401/403

Replace the `retrieve()` section in `OrdersGateway` with:

~~~java
.retrieve()
.onStatus(
        code -> code.value() == 401,
        response -> Mono.just(
                new ResponseStatusException(
                        HttpStatus.BAD_GATEWAY,
                        "Orders API rejected access token")))
.onStatus(
        code -> code.value() == 403,
        response -> Mono.just(
                new ResponseStatusException(
                        HttpStatus.FORBIDDEN,
                        "Orders access denied")))
.bodyToFlux(OrderView.class)
.collectList();
~~~

### 26.2. Do Not Retry 401 Infinitely

A token with the wrong audience or issuer will keep getting rejected even after refreshing. Bound retry and re-authorization policies.

### 26.3. WebClient Authorization Failure Handler

If an API `invalid_token` error should evict a stale authorized client, configure the corresponding failure handler/manager integration. Do not assume every OAuth2 filter configuration removes records automatically.

### 26.4. POST Requires Idempotency

If you later add order creation, retrying after a timeout can create duplicate orders. Use idempotency keys or proper contracts rather than generic retries on every POST.

## 27. CSRF, CORS, and Cookies

### 27.1. Portal Uses Browser Sessions So It Needs CSRF Protection

Browsers send cookies automatically. State-changing POST/PUT/DELETE endpoints must enforce CSRF protection per Portal policy. Never disable CSRF just because users log in via OIDC.

### 27.2. Bearer-Only APIs Have a Different Threat Model

The Orders API in this lab reads `Authorization` headers rather than cookies/sessions, so the API chain can disable CSRF. If the API ever accepts cookies later, re-evaluate immediately.

### 27.3. CORS Is Not Authentication

The browser calls the Portal on the same origin; the Portal calls Orders API server-to-server without browser CORS.

If an SPA calls the API directly from another origin, CORS is needed alongside full Bearer token validation.

### 27.4. Cookie Hardening

Production needs HTTPS, `Secure`, `HttpOnly`, `SameSite` matched to the login flow, session lifetimes, CSRF tokens, session fixation protection, and trusted forwarded headers.

### 27.5. Multi-Instance Sessions

If the browser lands on a different Pod after the login callback, you need a shared `WebSession`/authorization request store or sticky routing. Never disable OAuth state correlation.

## 28. Preventing Access Token Leaks

### 28.1. Never Proxy Arbitrary URLs

An endpoint such as:

~~~text
GET /proxy?url=https://attacker.example
~~~

must never automatically attach access tokens to arbitrary destinations.

### 28.2. Redirect Handling

The HTTP client must avoid forwarding `Authorization` headers to cross-origin hosts outside an allowlist. Consider disabling redirects on token-bearing requests or validating destinations explicitly.

### 28.3. Never Return `OAuth2AuthorizedClient` to the Browser

An authorized client can contain refresh tokens. Return only business DTOs.

### 28.4. Never Log Secrets

Never log raw access tokens, refresh tokens, ID tokens, client secrets, authorization codes, code verifiers, or session cookies.

### 28.5. Production HTTPS

Plain HTTP on `localhost` is only for isolated local labs; production requires HTTPS, trusted certificates, and egress controls.

## 29. `WebTestClient`: Testing OIDC Controllers

Reactive tests use `WebTestClient` and `mockOidcLogin()` from Spring Security Test.

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.reactive.WebFluxTest;
import org.springframework.test.web.reactive.server.WebTestClient;

import static org.springframework.security.test.web.reactive.server
        .SecurityMockServerConfigurers.mockOidcLogin;

@WebFluxTest(MeController.class)
class MeControllerTest {

    @Autowired
    WebTestClient client;

    @Test
    void readsOidcSubject() {

        client.mutateWith(
                        mockOidcLogin()
                                .idToken(token -> token
                                        .claim("sub", "alice-123")))
                .get()
                .uri("/me")
                .exchange()
                .expectStatus().isOk()
                .expectBody()
                .jsonPath("$.subject")
                .isEqualTo("alice-123");
    }
}
~~~

### 29.1. Testing `SecurityWebFilterChain`

`@WebFluxTest` is a slice; if custom production security rules are under test, import the right security config and provide beans/mocks for controller dependencies.

### 29.2. `mockOidcLogin()` Does Not Run Real Callbacks

The helper injects a mock authenticated OIDC principal into the request. It does not call an OP or validate JWT signatures, `state`, `nonce`, or PKCE.

### 29.3. Anonymous Negative Test

Send a request without mock login; assert the redirect or challenge expected by the test security chain's entry point.

### 29.4. Testing CSRF

For session-backed POSTs, add reactive `csrf()` tests and assert that missing-token requests are denied.

## 30. `WebTestClient`: Testing API Authorization

Resource Server APIs use `mockJwt()` instead of `mockOidcLogin()`:

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.reactive.WebFluxTest;
import org.springframework.context.annotation.Import;
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import org.springframework.test.web.reactive.server.WebTestClient;

import static org.springframework.security.test.web.reactive.server
        .SecurityMockServerConfigurers.mockJwt;

@WebFluxTest(OrdersController.class)
@Import(ApiSecurityConfig.class)
class OrdersApiTest {

    @Autowired
    WebTestClient client;

    @Test
    void allowsReadScope() {

        client.mutateWith(mockJwt()
                        .jwt(jwt -> jwt.subject("alice-123"))
                        .authorities(
                                new SimpleGrantedAuthority(
                                        "SCOPE_orders.read")))
                .get()
                .uri("/api/orders")
                .exchange()
                .expectStatus().isOk();
    }

    @Test
    void rejectsMissingScope() {

        client.mutateWith(mockJwt()
                        .jwt(jwt -> jwt.subject("alice-123"))
                        .authorities(
                                new SimpleGrantedAuthority(
                                        "SCOPE_profile")))
                .get()
                .uri("/api/orders")
                .exchange()
                .expectStatus().isForbidden();
    }
}
~~~

### 30.1. `mockJwt()` Does Not Verify Real Signatures

It simulates an authenticated JWT principal to test endpoint rules. Test `ReactiveJwtDecoder` separately with test JWKS/signed JWTs and invalid issuer/audience cases.

### 30.2. JWT Negative Matrix

| Input | Expected |
|---|---|
| No Bearer token | 401 |
| Invalid signature | 401 |
| Wrong issuer | 401 |
| Expired JWT | 401 |
| `aud=billing-api` | 401 |
| Right audience, missing `orders.read` | 403 |
| Valid scope, another user's resource | 403/404 per domain |
| Right audience, scope, and owner | 200 |

### 30.3. Testing Real Owner/Tenant Checks

If a controller returns mock data, object-level authorization is not yet proven. Once backed by a real repository, test that principal Alice cannot read Bob's orders.

## 31. Testing Bearer Forwarding Against a Fake Orders API

To prove `WebClient` actually sends the access token, use a fake HTTP server (WireMock/`MockWebServer`) rather than merely mocking `OrdersGateway`.

Test plan:

1. Build a fake `OAuth2AuthorizedClient` containing access token `test-A1`.
2. Configure the test reactive manager to return this authorized client.
3. Point `ORDERS_API_BASE_URL` at the fake server on a random port.
4. Send `GET /orders` to the Portal with an appropriate authentication.
5. Fake server records `GET /api/orders`.
6. Assert header `Authorization: Bearer test-A1`.
7. Assert no ID token or refresh token appears in the request.
8. Fake server returns JSON.
9. Assert Portal returns the expected DTO.
10. Have the fake API return 401/403 to verify error handling.

### 31.1. Fake Token Values Only

Never pull tokens from production logs or live browser sessions.

### 31.2. Destination Assertions Matter

If the URL targets the wrong host, the test must fail. Never merely assert Portal returns 200 while `WebClient` is completely mocked out.

### 31.3. Never Infer Refresh Behavior from a Mock Principal

`mockOidcLogin()` does not prove the manager refreshed tokens or persisted `R2`. Test the manager/provider/store components separately.

## 32. Integration Testing the Real OIDC Flow

Use a fake OP exposing:

~~~text
/.well-known/openid-configuration
/authorize
/token
/jwks
/userinfo (if used by flow)
~~~

### 32.1. Happy Path

- Initiate `/oauth2/authorization/corporate`.
- Extract `state`/`nonce` from the redirect.
- Deliver the `code` + `state` callback in the same session.
- Fake OP returns a valid token response.
- ID token is signed with test keys/JWKS; issuer, audience, and nonce match.
- Portal creates `Authentication` and stores the authorized client.

### 32.2. Denied Consent

A callback with `error=access_denied` must not establish a login session.

### 32.3. Wrong State

A callback whose `state` mismatches the pending request must be rejected before calling the token endpoint.

### 32.4. Invalid ID Token

Invalid signature, issuer, audience, expiry, or nonce must be rejected.

### 32.5. Duplicate Callback

Already-consumed codes and states must not be accepted as a new authorization. The AS must enforce single-use authorization codes.

### 32.6. Network Failure

Token/JWKS/UserInfo timeouts must fail closed without creating an unverified `Authentication`.

## 33. Refresh Tests and Concurrency

### 33.1. `A1` Still Valid

Manager reuses `A1`; the fake AS token endpoint call count should be zero when only valid cached tokens are used.

### 33.2. `A1` Near Expiry

Fake AS returns `A2`/`R2` on `R1` refresh; assert both the manager result and authorized-client store hold `A2`/`R2`.

### 33.3. No Refresh Token

If the OP did not issue `R1` and `A1` expired, the manager cannot mint a new authorization code on its own. Trigger UI/re-authorization per policy.

### 33.4. `invalid_grant`

Handle stale tokens and re-authorization via the failure handler policy. Never retry failed grants infinitely.

### 33.5. Concurrent Refresh

Two requests using `R1` concurrently can trigger a rotation race. Test single-flight/version/CAS when multiple Pods share a store.

### 33.6. Never Refresh to Fix a 403 Scope Error

Scope, owner, or tenant denials will not disappear after refreshing a token.

## 34. Opaque Access Tokens

If the AS issues **opaque access tokens**, Orders API cannot use the JWT decoder from Sections 18–19. Switch to opaque introspection:

~~~yaml
spring:
  security:
    oauth2:
      resourceserver:
        opaque-token:
          introspection-uri: ${OIDC_INTROSPECTION_URI}
          client-id: ${API_INTROSPECTION_CLIENT_ID}
          client-secret: ${API_INTROSPECTION_CLIENT_SECRET}
~~~

and in the Resource Server DSL:

~~~java
.oauth2ResourceServer(oauth2 -> oauth2
        .opaqueToken(Customizer.withDefaults()))
~~~

### 34.1. Introspection Still Needs Authority Mapping

If the AS returns scopes in a non-standard format, configure an opaque token introspector/converter. `active=true` does not replace owner/tenant checks.

### 34.2. Access Token Format Is Independent of ID Token Format

An OIDC ID token is a JWT, whereas an OAuth access token **does not have to be** a JWT.

## 35. Multi-Tenant Domain Authorization

A user might be an admin in tenant Acme while only a viewer in tenant Globex.

~~~text
Issuer = company-op
Subject = alice-123
Acme: ORDER_ADMIN
Globex: ORDER_VIEWER
~~~

### 35.1. API Scopes Are Coarse-Grained

`orders.read` is only an API-level permission. Queries and domain services must still verify tenant and owner.

### 35.2. Never Trust Caller-Declared Tenant IDs

If a client sends `?tenant=globex`, the API must check verified membership/policies rather than trusting the parameter directly as the sole condition.

### 35.3. Caches Must Be Tenant-Aware

Cache keys built solely from `sub` or order ID can leak data across tenants; key caches by identity, tenant, and authorization context.

### 35.4. Service Identities

Client credentials tokens have no human user. The API must distinguish service-level authorization from user-delegated access.

## 36. Deployment and Operations

### 36.1. Session Persistence

With multiple Portal Pods, authorization request state and `WebSession` must survive across the callback. Use a shared reactive session store or sticky routing per design.

### 36.2. Provider Timeouts

Token endpoints, UserInfo, and JWKS/discovery each use their own network clients and timeouts. Never assume one `WebClient` bean controls all of them.

### 36.3. Connection Pools and Backpressure

Reactor Netty connection pools must bound max connections and pending acquires; non-blocking I/O does not make provider capacity infinite.

### 36.4. Retry Grants Cautiously

Single-use authorization codes and rotating refresh tokens are unsafe to blindly retry via POST after an unknown outcome.

### 36.5. Observability

Track login success/failure, callback latency, refresh errors, Orders API 401/403/5xx, pool saturation, and trace correlation. Never log raw tokens.

### 36.6. Secrets and Egress

Keep client secrets in a secret store; enforce production HTTPS and egress allowlists for the OP and Orders API. Never follow redirects to arbitrary destinations while carrying tokens.

## 37. Troubleshooting

| Symptom | Possible Cause | Check |
|---|---|---|
| Portal does not redirect to login | Chain/matcher misconfigured | `oauth2Login()` |
| Callback 404 | Wrong Redirect URI | OP/client config |
| Callback state mismatch | Lost session / different Pod | `WebSession`/state repository |
| Login fails on issuer | Issuer metadata mismatch | OP issuer |
| Login fails on nonce | OIDC nonce mismatch | Request vs. ID token |
| `/me` has null `OidcUser` | Auth is not OIDC Login | Principal type |
| `/orders` 401 at Portal | Missing auth / authorized client | Session + manager |
| API 401 | Missing Bearer / wrong issuer / audience / expiry | JWT decoder |
| API 403 | Missing scope / owner / tenant | API authorization |
| Scope right, audience wrong | AS did not issue token for API | Audience mapper |
| API receives ID token | Wrong token type | Authorized client usage |
| Refresh never runs | No `R1` / missing provider | Reactive manager |
| Refresh `invalid_grant` | Rotation / revocation | Store / concurrency |
| `.block()` errors on event loop | Blocking reactive pipeline | Return `Mono`/`Flux` |
| `WebClient` leaks token | Dynamic URL / redirect | Allowlists, filters |
| `WebSession` lost when scaling | No shared state | Session persistence |
| CSRF 403 on POST | Missing token | CSRF configuration |
| CORS error | Browser calling API directly | BFF vs. SPA |
| `mockJwt()` green, real JWT 401 | Cryptographic decoder untested | Test with JWKS |
| `mockOidcLogin()` green, callback fails | Mock bypasses full login | Fake OP flow |

## 38. Extended Exercises

### A. View Identity

Build `GET /me` returning issuer and subject, without returning the raw ID token.

### B. Require Login Before Reading Orders

Ensure anonymous `GET /orders` enters the login flow.

### C. Bearer Forwarding

Use a fake Orders API to verify the `Authorization: Bearer test-A1` header.

### D. Wrong Audience

Verify tokens with `aud=billing-api` are rejected by the API.

### E. Missing Scope

Verify tokens with the right audience but lacking `orders.read` receive 403.

### F. Refresh Rotation

Fake AS rotates `R1` → `A2`/`R2`; assert the manager/store persists the new tokens.

### G. Tenant Isolation

Verify Alice in Acme cannot view Globex orders.

### H. CSRF

Add a Portal POST endpoint and test with and without a CSRF token.

### I. Wrong Host

Test dynamic URL user input; verify the Portal never forwards tokens to unknown hosts.

### J. Concurrent Refresh

Send two concurrent requests using `R1`; apply single-flight/CAS and verify `R2` is never lost.

## 39. Self-Check Questions

**1. Which security chain does WebFlux use?** `SecurityWebFilterChain`.

**2. Which scope enables OIDC?** `openid`.

**3. What is the standard login initiation path?** `/oauth2/authorization/{registrationId}`.

**4. What is the standard OIDC callback path?** `/login/oauth2/code/{registrationId}`.

**5. What is the typical OIDC principal after login?** `OidcUser` inside `OAuth2AuthenticationToken`.

**6. Where does the API access token come from?** `OAuth2AuthorizedClient.getAccessToken()`.

**7. Should the ID token be sent as an API Bearer token?** No, under standard contracts.

**8. What type does the reactive manager return?** `Mono<OAuth2AuthorizedClient>`.

**9. What does the `WebClient` OAuth2 filter do?** Attaches the Bearer access token from the authorized client.

**10. Why is `ServerWebExchange` needed?** So the manager/repository has the request/session context.

**11. What must the Resource Server validate?** Signature, issuer, expiry, audience, scope, and domain permissions.

**12. What should happen on a wrong audience?** The API rejects the token.

**13. Can opaque access tokens be used?** Yes, via introspection.

**14. Should you call `block()` in a WebFlux controller?** No.

**15. Do session-backed Portal POSTs need CSRF?** Yes, per threat model.

**16. Does `mockOidcLogin()` test real callbacks?** No.

**17. Does `mockJwt()` verify JWT signatures?** No.

**18. What does a multi-Pod Portal need?** Shared `WebSession`/state/authorized-client persistence or sticky routing.

**19. Why not forward tokens to arbitrary URLs?** Risk of token leaks and SSRF.

**20. What must refresh rotation persist?** Both `A2` and `R2` when issued by the AS.

## Key Takeaways

- **The Reactive Portal uses `oauth2Login()` for OIDC authentication and `oauth2Client()` for outbound authorized clients**. Orders API uses `oauth2ResourceServer()` independently.
- **The browser sends a session cookie to the Portal; the Portal sends a Bearer access token to the API**. ID tokens and access tokens are never interchangeable.
- **`ReactiveOAuth2AuthorizedClientManager` finds, reuses, and refreshes authorized clients per registration and principal**, while the `WebClient` OAuth2 filter attaches the access token.
- **Orders API must verify signatures, issuers, expiry, audience, scopes, and domain authorization**; a successful login does not grant access to all orders.
- **Reactor Context differs from Servlet `ThreadLocal`**. Never call `block()` or `subscribe()` arbitrarily in the request path.
- **A BFF must still enforce CSRF protection and session security**, while a bearer-only API has its own threat model.
- **`mockOidcLogin()` and `mockJwt()` test post-authentication behavior** and never replace fake OP/JWKS integration tests for real callbacks and JWT validation.
- **Refresh token rotation, 401/403, concurrency, and token storage require dedicated tests**, never infinite retries.
- **Never log tokens, return credentials to the browser, or attach Bearer tokens to arbitrary hosts**.
