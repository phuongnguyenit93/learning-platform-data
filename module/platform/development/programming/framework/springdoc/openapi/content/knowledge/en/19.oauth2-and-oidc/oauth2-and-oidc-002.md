# Authorization Code and UI Tool PKCE Support

Swagger UI can let users log in via OAuth 2.0 or OpenID Connect (OIDC), and then use the access token to call APIs directly in the browser. For a browser-based UI tool, the appropriate model is **Authorization Code Flow combined with Proof Key for Code Exchange (PKCE)**. PKCE helps protect the authorization code if the code is intercepted or stolen during redirection.

In Spring Boot, springdoc-openapi generates the OpenAPI specification from controllers and configures Swagger UI. For the login flow to work, three parts need to coordinate:

1. **OpenAPI security scheme** describing the authorization URL, token URL, and scopes of the Authorization Code Flow.
2. **Swagger UI** configured with client ID, redirect URL, and PKCE enabled.
3. **Authorization Server / OpenID Provider** registering the right public client, redirect URI, scopes, and enforcing PKCE verification.

Declaring the flow in OpenAPI alone does not enable PKCE and does not turn the application into an Authorization Server. The API still needs to verify the access token on the server side, typically with Spring Security Resource Server.

## 1. Authorization Code Flow suited for UI tools

OAuth 2.0 Authorization Code Flow has two main phases:

- The browser redirects the user to the Authorization Server to log in and grant consent.
- The client receives an authorization code via the redirect URI, then exchanges the code for a token at the token endpoint.

Swagger UI runs in the browser, so it cannot safely keep a static client secret. A client deployed in the browser is a **public client**. When using Authorization Code Flow, a public client must use PKCE according to OAuth 2.0 Security Best Current Practice.

PKCE adds a short-lived random secret for each login attempt. The client generates:

- **code_verifier**: a high-entropy random string kept only on the client for the current transaction.
- **code_challenge**: a value derived from the verifier to send to the Authorization Server.
- **code_challenge_method**: the transformation method for the verifier; S256 should be used.

With S256:

~~~text
code_challenge =
  BASE64URL-ENCODE(SHA256(ASCII(code_verifier)))
~~~

The Authorization Server stores the challenge alongside the authorization code. When the client exchanges the code for a token, it sends the verifier. The server recomputes the challenge from the verifier and compares it with the stored value. If they do not match, the token endpoint refuses to issue a token.

An attacker might see the authorization code, but cannot exchange it for a token without the corresponding verifier. PKCE therefore mitigates authorization code interception and injection risks.

## 2. Login flow from Swagger UI

Typical workflow:

~~~mermaid
sequenceDiagram
    actor User as User
    participant UI as Swagger UI
    participant AS as Authorization Server
    participant API as Spring Boot API

    User->>UI: Select Authorize
    UI->>UI: Generate code_verifier and S256 code_challenge
    UI->>AS: Redirect /authorize with response_type=code, state, challenge
    AS->>User: Log in and request consent
    User->>AS: Authenticate and approve
    AS-->>UI: Redirect URI with authorization code and state
    UI->>AS: POST /token with code and code_verifier
    AS->>AS: Recompute challenge and verify PKCE
    AS-->>UI: Access token (and ID token if OIDC)
    UI->>API: API request with Bearer access token
    API->>API: Verify signature, issuer, audience, expiry, and permissions
    API-->>UI: API response
~~~

Step-by-step details:

1. The user clicks **Authorize** in Swagger UI.
2. Swagger UI generates a random verifier, computes the challenge using SHA-256, and stores the verifier for the current transaction.
3. Swagger UI redirects the browser to the authorization endpoint with parameters such as **response_type=code**, **client_id**, **redirect_uri**, **scope**, **state**, **code_challenge**, and **code_challenge_method=S256**.
4. The user logs in at the Authorization Server and approves the requested scopes.
5. The Authorization Server redirects back to the registered redirect URI, including the authorization code and state.
6. Swagger UI validates state, then sends a token request with the authorization code and code_verifier.
7. The Authorization Server verifies that the verifier matches the stored challenge, checks other conditions, and returns tokens.
8. Swagger UI uses the access token in the Authorization: Bearer header when calling protected operations.

**state** binds the authorization request to the callback and helps protect the transaction against forged requests. With OIDC, the client can also use **nonce** to bind the ID token to the login attempt. PKCE, state, and nonce have related purposes, but do not completely replace one another.

## 3. PKCE with S256 and Authorization Server requirements

PKCE has two commonly mentioned methods:

| Method | Calculation | Assessment |
| --- | --- | --- |
| **plain** | code_challenge equals code_verifier | Only for legacy compatibility environments where S256 is unsupported |
| **S256** | SHA-256 followed by Base64URL encoding | Recommended; avoids exposing the verifier in the authorization request |

Clients capable of S256 must choose S256. RFC 9700 requires Authorization Servers to support PKCE and verify code_verifier when the authorization request included code_challenge. Servers must also prevent downgrade attacks, refusing to accept a verifier in a token request if the corresponding authorization request had no challenge.

When configuring the Authorization Server, you should:

- Enable the Authorization Code grant type.
- Mark Swagger UI as a public client if the client runs entirely in the browser.
- Enforce PKCE and prefer the S256 method.
- Register the exact redirect URI.
- Configure the scopes allowed for the client.
- Do not require a client secret for a public client.
- Set a short lifetime for the authorization code and ensure single-use enforcement.

Some Authorization Servers advertise PKCE support in metadata, such as the **code_challenge_methods_supported** field. If metadata is not published, verify via provider configuration or deployment documentation.

## 4. Declaring Authorization Code Flow in OpenAPI

OpenAPI describes OAuth 2.0 using a Security Scheme Object with **type: oauth2**. For Authorization Code Flow, declare **flows.authorizationCode**, **authorizationUrl**, **tokenUrl**, and scopes.

Example:

~~~yaml
openapi: 3.1.0
info:
  title: Shop API
  version: 1.0.0

components:
  securitySchemes:
    shopOAuth:
      type: oauth2
      description: Log in via Authorization Code Flow with PKCE.
      flows:
        authorizationCode:
          authorizationUrl: https://identity.example.com/oauth2/authorize
          tokenUrl: https://identity.example.com/oauth2/token
          scopes:
            openid: Authenticate user with OpenID Connect
            profile: Read basic profile information
            orders.read: Read orders
            orders.write: Create and update orders

paths:
  /api/orders:
    get:
      summary: List orders
      security:
        - shopOAuth:
            - orders.read
      responses:
        '200':
          description: List of orders
        '401':
          description: Unauthenticated or invalid access token
        '403':
          description: Token lacks required scope
~~~

In this example:

- **authorizationUrl** is the endpoint where users are redirected to log in and grant consent.
- **tokenUrl** is the endpoint that receives the authorization code and returns tokens.
- **scopes** lists permissions that the Authorization Server can grant.
- **security** on the operation specifies the scopes needed to call the API.

If an operation does not require authentication, you can set **security: []** on that operation to override document-level security requirements. Do not add scopes just to make the Authorize button appear; scopes must reflect the actual permissions of the API.

OpenAPI describes the flow type and OAuth endpoints. **OpenAPI has no standard field to enable PKCE or require code_challenge_method=S256.** Enabling PKCE in Swagger UI is a UI tool configuration; requiring and verifying PKCE is the responsibility of the Authorization Server.

## 5. Declaring the security scheme with Swagger annotations

Springdoc reads OpenAPI annotations from controllers and configuration. You can declare an OAuth2 Security Scheme on a configuration class:

~~~java
import io.swagger.v3.oas.annotations.enums.SecuritySchemeType;
import io.swagger.v3.oas.annotations.security.OAuthFlow;
import io.swagger.v3.oas.annotations.security.OAuthFlows;
import io.swagger.v3.oas.annotations.security.OAuthScope;
import io.swagger.v3.oas.annotations.security.SecurityScheme;
import org.springframework.context.annotation.Configuration;

@Configuration
@SecurityScheme(
    name = "shopOAuth",
    type = SecuritySchemeType.OAUTH2,
    flows = @OAuthFlows(
        authorizationCode = @OAuthFlow(
            authorizationUrl =
                "https://identity.example.com/oauth2/authorize",
            tokenUrl =
                "https://identity.example.com/oauth2/token",
            scopes = {
                @OAuthScope(
                    name = "openid",
                    description = "Authenticate user with OIDC"
                ),
                @OAuthScope(
                    name = "profile",
                    description = "Read profile information"
                ),
                @OAuthScope(
                    name = "orders.read",
                    description = "Read orders"
                ),
                @OAuthScope(
                    name = "orders.write",
                    description = "Create and update orders"
                )
            }
        )
    )
)
class OpenApiOAuthConfiguration {}
~~~

Attach the security requirement to an operation:

~~~java
import io.swagger.v3.oas.annotations.security.SecurityRequirement;
import java.util.List;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api/orders")
class OrderController {

    private final OrderService orderService;

    OrderController(OrderService orderService) {
        this.orderService = orderService;
    }

    @GetMapping
    @SecurityRequirement(
        name = "shopOAuth",
        scopes = {"orders.read"}
    )
    List<OrderView> findOrders() {
        return orderService.findOrders();
    }
}
~~~

The name **shopOAuth** in SecurityRequirement must match the scheme name exactly. Scopes in the requirement must be declared in the OAuth Flow Object. Annotations only generate metadata; Spring Security or an API gateway still must enforce authentication and authorization.

## 6. Enabling PKCE in springdoc and Swagger UI

Springdoc provides Swagger UI configuration properties. For Authorization Code Flow, enable the **usePkceWithAuthorizationCodeGrant** property.

Example in application.yml:

~~~yaml
springdoc:
  swagger-ui:
    oauth2-redirect-url: https://docs.example.com/swagger-ui/oauth2-redirect.html
    oauth:
      client-id: shop-swagger-ui-public
      scopes:
        - openid
        - profile
        - orders.read
      use-pkce-with-authorization-code-grant: true
    persist-authorization: false
~~~

Or application.properties:

~~~properties
springdoc.swagger-ui.oauth2-redirect-url=https://docs.example.com/swagger-ui/oauth2-redirect.html
springdoc.swagger-ui.oauth.client-id=shop-swagger-ui-public
springdoc.swagger-ui.oauth.scopes=openid,profile,orders.read
springdoc.swagger-ui.oauth.use-pkce-with-authorization-code-grant=true
springdoc.swagger-ui.persist-authorization=false
~~~

Meaning:

| Property | Role |
| --- | --- |
| **oauth2-redirect-url** | URL receiving the redirect after user authentication |
| **oauth.client-id** | Client ID registered for Swagger UI |
| **oauth.scopes** | Initial scopes selected in the UI |
| **oauth.use-pkce-with-authorization-code-grant** | Enables generating code verifier and challenge for Authorization Code Flow |
| **persist-authorization** | Determines whether authorization state is persisted across browser reloads/close-reopen |

The Springdoc UI Properties Reference notes that **usePkceWithAuthorizationCodeGrant** applies only to Authorization Code Flow and defaults to **false**. Therefore, enable it explicitly instead of assuming Swagger UI uses PKCE automatically.

Do not configure **springdoc.swagger-ui.oauth.client-secret** for a browser-based client in production. A client secret embedded in JavaScript or configuration downloaded by the browser is no longer secret. PKCE is a mechanism to protect the authorization code; it does not turn the browser into a confidential client.

## 7. Standalone Swagger UI configuration with initOAuth

If the application embeds Swagger UI directly instead of using the page served by springdoc, you can call **initOAuth** after creating the Swagger UI instance:

~~~javascript
const ui = SwaggerUIBundle({
    url: "/v3/api-docs",
    dom_id: "#swagger-ui",
    oauth2RedirectUrl:
        "https://docs.example.com/swagger-ui/oauth2-redirect.html"
});

ui.initOAuth({
    clientId: "shop-swagger-ui-public",
    scopes: "openid profile orders.read",
    usePkceWithAuthorizationCodeGrant: true
});
~~~

**oauth2RedirectUrl** is a Swagger UI instance-level configuration; **usePkceWithAuthorizationCodeGrant** is an OAuth option passed into **initOAuth**. Do not put PKCE options in the OpenAPI Security Scheme because they are not standard fields of the specification.

When using springdoc, prefer configuring via application properties/yaml so springdoc passes the values to Swagger UI. Only use **initOAuth** directly when you manage the Swagger UI page or bundle yourself.

## 8. Registering the exact redirect URI

The redirect URI is the address where Swagger UI receives the authorization response. With springdoc's default configuration, the path is typically:

~~~text
/swagger-ui/oauth2-redirect.html
~~~

In production deployments, configure the full URL that the browser actually accesses, for example:

~~~text
https://docs.example.com/swagger-ui/oauth2-redirect.html
~~~

Register this exact URI in the client configuration at the Authorization Server. The URI sent in the authorization request must match the registered URI according to the provider's exact matching rules and OAuth security best practices.

Check the following cases:

- Application runs behind a reverse proxy.
- There is a context path such as /shop.
- Swagger UI path is changed using **springdoc.swagger-ui.path**.
- TLS terminates at a load balancer or ingress.
- The documentation domain differs from the API domain.

If the external URL is **https://docs.example.com/shop/swagger-ui/oauth2-redirect.html**, both the Swagger UI configuration and the registered redirect URI must use this external address. Do not register a localhost URI and ship that client to production.

## 9. Configuring the Authorization Server for a public client

In the Identity Provider, create a dedicated client for Swagger UI. Names and UI settings vary by provider, but the properties should be equivalent to:

| Property | Suggested Value |
| --- | --- |
| Client ID | **shop-swagger-ui-public** |
| Client type | Public |
| Grant type | Authorization Code |
| PKCE | Required |
| PKCE method | S256 |
| Client secret | Not used for public browser clients |
| Redirect URI | Exact **oauth2-redirect.html** URL |
| Allowed scopes | **openid**, **profile**, **orders.read** |
| Token endpoint | HTTPS |

Do not enable Implicit Flow just to make Swagger UI login easier. Authorization Code with PKCE is the more appropriate choice for a public client running in a browser.

If the Authorization Server has a "require PKCE" option, enable it. Enabling PKCE only on the Swagger UI side while the server still accepts code exchanges without a verifier defeats the protection.

If the system uses OIDC, check the discovery document at the well-known endpoint to verify the issuer, authorization endpoint, token endpoint, and PKCE support. Do not guess endpoints from a realm or tenant name.

## 10. Distinguishing OAuth2 and OpenID Connect

OAuth 2.0 focuses on **delegated resource access authorization**. OpenID Connect adds an identity authentication layer on top of OAuth 2.0.

| Concept | Purpose |
| --- | --- |
| Access token | Allows the client to call a resource server according to granted permissions |
| ID token | Carries user authentication information for the OIDC client |
| **openid** scope | Triggers an OIDC request |
| **profile** scope | Requests certain user profile claims |
| API scopes like **orders.read** | Access permissions for order resources |
| PKCE | Binds the authorization code to the client that initiated the transaction |
| OIDC nonce | Binds the ID token to a specific authentication request |

When calling APIs, Swagger UI normally sends the **access token** in the Bearer header. Do not send the ID token in place of the access token just because both are JWTs. The Resource Server needs to check audience, issuer, signature, expiration, and appropriate permissions.

If you only need OAuth2 to obtain permission to call APIs, you might not need the **openid** scope. If you want to log in and display user identity in an OIDC flow, add **openid** and required scopes according to your Identity Provider configuration.

## 11. Token endpoint and CORS

The authorization endpoint is normally opened by navigating the browser to the login page. The token endpoint, however, is called by Swagger UI via a JavaScript request after receiving the authorization code. If the token endpoint is on a different origin from the Swagger UI page, the Authorization Server must allow the documentation origin via CORS.

Check:

- **Access-Control-Allow-Origin** matches the Swagger UI origin.
- The token endpoint allows the POST method.
- Headers and content type sent by Swagger UI are accepted.
- Token responses include appropriate CORS headers so JavaScript can read them.
- Wildcard origins are not used when requests include credentials as required by configuration.

Not every CORS error comes from the Spring Boot API. An API request might succeed, or the code exchange step at the token endpoint might be blocked by the browser. When that happens, open the Network panel and determine whether the failing request is /token or a resource server endpoint.

If Swagger UI and the API are served from the same origin, API calls do not require CORS. However, the token endpoint may still be on a different origin, so check CORS configuration separately at the Identity Provider.

## 12. Spring Boot Resource Server verifying access tokens

Swagger UI is only an OAuth client used to obtain tokens. The Spring Boot API still has to verify access tokens before processing requests. For JWTs, Spring Security Resource Server can use an issuer URI to discover metadata and verification keys:

~~~yaml
spring:
  security:
    oauth2:
      resourceserver:
        jwt:
          issuer-uri: https://identity.example.com/
~~~

The issuer URI must match the **iss** claim in the access token and the Authorization Server configuration. The application also needs to verify the audience if the system issues tokens for multiple resource servers.

Minimal security filter chain configuration example:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
class ApiSecurityConfiguration {

    @Bean
    SecurityFilterChain apiSecurity(HttpSecurity http) throws Exception {
        return http
            .authorizeHttpRequests(authorize -> authorize
                .requestMatchers("/v3/api-docs/**", "/swagger-ui/**")
                    .permitAll()
                .requestMatchers(HttpMethod.GET, "/api/orders/**")
                    .hasAuthority("SCOPE_orders.read")
                .requestMatchers(HttpMethod.POST, "/api/orders/**")
                    .hasAuthority("SCOPE_orders.write")
                .anyRequest()
                    .authenticated()
            )
            .oauth2ResourceServer(resourceServer ->
                resourceServer.jwt(Customizer.withDefaults())
            )
            .build();
    }
}
~~~

The example uses the **SCOPE_orders.read** authority to illustrate Spring Security's common scope mapping. Actual configuration must align with the provider's scope/scp claim, audience, and authorization rules. Do not leave the entire API open simply because Swagger UI has an Authorize button.

In some applications, /v3/api-docs/** or /swagger-ui/** also need to be protected by separate authentication. This decision depends on whether the documentation is public or contains internal information; permitAll is not mandatory.

## 13. Access token, scopes, and security requirements

OpenAPI uses the Security Requirement Object to describe the scopes needed for each operation. Example:

~~~yaml
paths:
  /api/orders:
    get:
      security:
        - shopOAuth:
            - orders.read
    post:
      security:
        - shopOAuth:
            - orders.write
~~~

Swagger UI uses the security scheme to render the Authorize button and selectable scopes. When the user grants authorization, Swagger UI obtains a token via the declared flow. When clicking Try it out, the UI sends the access token to the operation.

Scopes in OpenAPI must match the scopes that the Authorization Server actually issues. If the documentation requires **orders.read** but the token only contains **profile**, the API may return 403 even though the token has a valid signature and expiration.

Distinguish:

- **401 Unauthorized:** missing token, invalid token, expired token, or cannot be verified.
- **403 Forbidden:** valid token but lacks required permissions/scopes.

## 14. Persisting authorization in Swagger UI

Springdoc has the property **springdoc.swagger-ui.persist-authorization**. The default is **false**. When enabled, authorization data is kept across page refreshes or browser close/reopen according to Swagger UI's storage mechanism.

Enable persistence only when there is a clear need and the usage environment has been evaluated. On shared machines, lab computers, or public computers, keeping tokens increases the risk that someone else continues using the authenticated session. In internal documentation, instruct users to log out or clear authorization after testing.

Never include real access tokens, refresh tokens, client secrets, or real account credentials in:

- committed application.yml.
- static JavaScript or public Swagger UI configuration.
- OpenAPI examples.
- screenshots or CI logs.

PKCE protects the authorization code. It does not prevent XSS from reading tokens in use by the application, does not replace HTTPS, and does not itself solve secure token storage in the browser.

## 15. Testing Authorization Code and PKCE

### Checking OpenAPI JSON

Start the application and download the specification:

~~~bash
curl -sS http://localhost:8080/v3/api-docs -o openapi.json
~~~

Check the security scheme:

~~~bash
jq '.components.securitySchemes.shopOAuth' openapi.json
~~~

Expected results:

- **type** is **oauth2**.
- **flows.authorizationCode** exists.
- **authorizationUrl** and **tokenUrl** match the Identity Provider.
- Scopes have appropriate names and descriptions.
- Operations have corresponding security requirements and scopes.

### Checking Swagger UI configuration

Open the Swagger UI page, click Authorize, and verify:

1. Client ID is the registered public client.
2. Redirect URI is the exact external URL the browser is using.
3. Initial scopes contain the required scopes.
4. Authorization request has **response_type=code**.
5. **code_challenge** and **code_challenge_method=S256** are present.
6. **code_verifier** is not in the authorization URL.

### Checking the token request

After logging in, inspect the request to the token endpoint:

- Contains **grant_type=authorization_code**.
- Contains the authorization code.
- Contains **redirect_uri** matching the authorization request's URI.
- Contains the public client's **client_id**.
- Contains **code_verifier**.
- Does not send a client secret for a public client.

The Authorization Server must recompute the challenge from the verifier and return tokens only if it matches the challenge stored with the code.

### Checking API requests

After a token is issued:

- API request includes **Authorization: Bearer ...**.
- Access token has the right issuer and audience.
- Token is not expired.
- Scope/authority satisfies the operation.
- API returns 200 when authorized, 401 when token is invalid, and 403 when permissions are missing.

## 16. Common errors

**Authorize button does not use PKCE.** Verify the flow is **authorizationCode**, **use-pkce-with-authorization-code-grant** is enabled, and the Swagger UI version supports this option. The PKCE option does not apply to Implicit or Client Credentials Flow.

**Authorization Server reports PKCE required but token request lacks verifier.** Check that Swagger UI is using the right Authorization Code Flow and the PKCE setting is passed to **initOAuth**. Do not only check the OpenAPI YAML file because YAML does not enable PKCE.

**Token endpoint returns invalid_grant or code_verifier mismatch.** Check whether the client kept the exact verifier for the current transaction, the authorization code is not expired/reused, and the Authorization Server stored the challenge properly with the code.

**Authorization Server reports redirect_uri mismatch.** Compare exact scheme, host, port, path, and trailing slash across springdoc configuration, authorization request, and client registration.

**Swagger UI returns to an error page after login.** Check if **oauth2-redirect.html** is reachable, whether the reverse proxy preserves context path, and whether the external URL configuration is correct.

**Login succeeds but API returns 401.** Check whether Swagger UI is sending the access token or ID token, and whether the token has the right audience/issuer, valid signature, and is not expired.

**API returns 403.** The token may be valid but missing scopes. Cross-check scopes in OpenAPI, scopes selected in Swagger UI, scopes issued by the Authorization Server, and Spring Security authority mapping.

**Token endpoint is blocked by CORS.** Check Swagger UI's origin in the Authorization Server's CORS configuration. Distinguish /token requests from requests to the resource server.

**PKCE is enabled but client secret is still configured in application.yml.** Remove the client secret from production browser configuration. PKCE does not make a secret safe once exposed publicly.

**Swagger UI keeps tokens after refresh.** Check **persist-authorization**. Disable it if authentication state does not need to survive reloads.

**Using Implicit Flow because it is easier to configure.** Switch to Authorization Code with PKCE for public clients and confirm the Authorization Server supports S256.

## 17. Implementation checklist

- [ ] Declare an OAuth2 Security Scheme with **authorizationCode**.
- [ ] Use exact HTTPS authorization URL and token URL.
- [ ] Declare scopes and attach security requirements to operations.
- [ ] Register Swagger UI as a public client when the client runs in the browser.
- [ ] Enable Authorization Code grant and require PKCE on the Authorization Server.
- [ ] Use PKCE method S256.
- [ ] Enable **springdoc.swagger-ui.oauth.use-pkce-with-authorization-code-grant=true**.
- [ ] Configure **client-id** but do not put a client secret in production browser config.
- [ ] Register a redirect URI matching the external URL exactly.
- [ ] Configure CORS for the token endpoint if on a different origin.
- [ ] Check state and nonce if using OIDC.
- [ ] Use the access token for APIs and verify tokens in Spring Security Resource Server.
- [ ] Check issuer, audience, expiry, and scopes.
- [ ] Keep **persist-authorization** disabled if persisting tokens is unnecessary.
- [ ] Inspect authorization, token, and API requests in Developer Tools.

## 18. Conclusion

Authorization Code Flow combined with PKCE is the right choice for browser-based Swagger UI because the client cannot keep a client secret confidential. OpenAPI describes the flow, endpoints, and scopes; springdoc passes OAuth configuration to Swagger UI; Swagger UI generates the verifier/challenge and performs the code exchange; the Authorization Server enforces S256 verification before issuing tokens. The Spring Boot API still must verify access tokens and permissions on the server side. When redirect URI, client registration, PKCE, CORS, and scopes are configured consistently, users can log in within Swagger UI and test APIs in accordance with the security contract.

## 19. References

- [Springdoc — Swagger UI Properties Reference](https://springdoc.org/ui-properties.html): properties **oauth.clientId**, **oauth.scopes**, **oauth.usePkceWithAuthorizationCodeGrant**, **oauth2RedirectUrl**, and **persistAuthorization**.
- [Swagger UI — OAuth 2.0 Configuration](https://swagger.io/docs/open-source-tools/swagger-ui/usage/oauth2/): configuring **initOAuth** and **usePkceWithAuthorizationCodeGrant**.
- [Swagger UI — Configuration](https://swagger.io/docs/open-source-tools/swagger-ui/usage/configuration/): configuring Swagger UI's redirect URL.
- [OpenAPI Specification 3.1.2 — Security Scheme Object](https://spec.openapis.org/oas/v3.1.2.html#security-scheme-object): describing OAuth2 and Authorization Code Flow in OpenAPI.
- [RFC 7636 — Proof Key for Code Exchange by OAuth Public Clients](https://www.rfc-editor.org/rfc/rfc7636.html): generating and verifying code verifier/challenge.
- [RFC 9700 — Best Current Practice for OAuth 2.0 Security](https://www.rfc-editor.org/rfc/rfc9700.html): requiring PKCE for public clients and recommending S256.
- [OpenID Connect Core 1.0](https://openid.net/specs/openid-connect-core-1_0.html): openid scope, ID token, and nonce.
- [Spring Security — OAuth 2.0 Resource Server JWT](https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/jwt.html): verifying JWT access tokens at the API.
