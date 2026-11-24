# Boundaries Between Swagger UI, Authorization Server, and Resource Server

Swagger UI, Authorization Server, and Resource Server may appear together in an API testing workflow, yet they perform distinct roles. Swagger UI is a documentation interface and HTTP client running in the browser. The Authorization Server authenticates users or clients and issues tokens per OAuth2/OIDC. The Resource Server protects resources, validates access tokens, and decides whether a request has sufficient permissions.

springdoc-openapi helps describe authentication mechanisms in the OpenAPI contract so Swagger UI knows how to initiate the authorization flow and send credentials when calling APIs. This description does not turn Swagger UI into a token-issuing server, nor does it replace authentication and authorization at the Resource Server.

## 1. Three roles in a workflow

| Component | Primary Responsibility | What It Does Not Handle |
|---|---|---|
| Swagger UI | Renders OpenAPI, lets users choose operations, enter parameters, and send requests from the browser | Does not issue tokens, does not verify token signatures, and does not decide access permissions |
| Authorization Server (AS) | Authenticates users/clients, handles consent when needed, and issues and manages access tokens | Does not execute business logic of the protected API |
| Resource Server (RS) | Receives requests, validates access tokens, checks audience/scopes/authorities, and protects resources | Does not issue access tokens to clients in its role as resource server |

A single product may provide both an Authorization Server and a Resource Server, yet these remain two separate logical roles. For example, an identity platform may issue tokens while a Spring Boot application only receives tokens and protects order endpoints.

Swagger UI may be served from the Spring Boot application itself or from a separate documentation host. Deployment location does not change its role: the UI remains an OAuth2 client helping users test the API.

## 2. Overall flow when using Swagger UI with OAuth2

With Authorization Code flow and PKCE, the browser typically executes these steps:

~~~mermaid
sequenceDiagram
    participant U as User
    participant UI as Swagger UI (browser client)
    participant AS as Authorization Server
    participant RS as Resource Server

    U->>UI: Select operation and Authorize
    UI->>AS: Navigate to authorization endpoint
    AS->>U: Log in and consent if needed
    U->>AS: Complete authentication
    AS-->>UI: Redirect back to callback with authorization code
    UI->>AS: Exchange code + PKCE verifier for token
    AS-->>UI: Access token (and ID token if using OIDC)
    UI->>RS: Call API with Authorization: Bearer access_token
    RS->>RS: Verify token and permissions
    RS-->>UI: HTTP response
    UI-->>U: Display request and response
~~~

The key point is that there are two calls to two different roles:

1. Swagger UI interacts with the Authorization Server to obtain a token.
2. Swagger UI sends the access token to the Resource Server to invoke the operation.

If the token endpoint fails, the business request may never even reach the Resource Server. If a token is obtained but the API returns 401 or 403, inspect the Resource Server and the token's permissions.

## 3. Authorization Server is responsible for issuing tokens

The Authorization Server manages the OAuth2/OIDC flow. In Authorization Code flow, it typically:

- Authenticates users via the organization's login mechanism.
- Checks client ID, redirect URI, and authorization request parameters.
- Displays consent if policy requires user approval of permissions.
- Issues short-lived, single-use authorization codes.
- Exchanges valid codes for access tokens, possibly accompanied by refresh tokens or ID tokens depending on the flow.
- Publishes metadata, signing keys, or an introspection endpoint as configured.

Swagger UI does not perform these steps. It redirects the browser to the authorization endpoint, receives the callback, and exchanges the code per OAuth2 client configuration. Password verification, MFA, sessions, consent, client registration, and token issuance belong to the Authorization Server.

URLs such as authorization endpoint, token endpoint, and issuer must come from the real identity environment. Documentation examples may use illustrative hostnames, but never confuse them with the API application's endpoints.

## 4. Resource Server is responsible for protecting the API

The Resource Server receives requests containing an access token, typically via the header:

~~~http
Authorization: Bearer eyJ...access-token
~~~

For JWT access tokens, the Resource Server must verify the signature using trusted keys, issuer, expiration, and other token conditions per policy. The API also needs to verify audience to ensure the token was issued for the right resource server. Audience validation may require an additional validator depending on framework configuration.

For opaque access tokens, the Resource Server typically calls the Authorization Server's introspection endpoint to verify that the token is still active and retrieve permission info. Whether using JWTs or opaque tokens, the final decision belongs to the Resource Server.

Once the token is valid, the application must also check resource access permissions:

- Does the caller have the required scope such as <code>orders:read</code>?
- Does the caller have the appropriate authority or role?
- Is the caller permitted to access this specific record or tenant?
- Do business rules allow the action at the current time?

A valid token does not mean every action is permitted. This is why a request can receive <code>403 Forbidden</code> even after the user logged in successfully.

## 5. Swagger UI is an OAuth2 client in the browser

When OpenAPI describes an OAuth2 scheme, Swagger UI can render the Authorize button and launch the flows it supports. In Authorization Code flow, Swagger UI uses the redirect callback to receive the code, then exchanges the code for a token.

Swagger UI is not an Authorization Server:

- Does not store user passwords for authentication.
- Does not generate authorization codes or access tokens.
- Does not manage client registrations or consent.
- Does not verify signatures and issuers of access tokens like a Resource Server.

Swagger UI is also not a Resource Server:

- Does not protect business endpoints.
- Does not check permissions on data.
- Does not replace the Spring Security filter chain.
- Cannot guarantee a request is rejected if the server is misconfigured.

The UI only holds and sends credentials according to its configuration. The server receiving requests must validate tokens itself.

## 6. Describing the OAuth2 flow in OpenAPI

With springdoc-openapi, register schemes and flows using annotations. Example:

~~~java
import io.swagger.v3.oas.annotations.enums.SecuritySchemeType;
import io.swagger.v3.oas.annotations.security.OAuthFlow;
import io.swagger.v3.oas.annotations.security.OAuthFlows;
import io.swagger.v3.oas.annotations.security.OAuthScope;
import io.swagger.v3.oas.annotations.security.SecurityScheme;
import org.springframework.context.annotation.Configuration;

@Configuration
@SecurityScheme(
    name = "ordersOAuth",
    type = SecuritySchemeType.OAUTH2,
    flows = @OAuthFlows(
        authorizationCode = @OAuthFlow(
            authorizationUrl = "https://identity.example.com/oauth2/authorize",
            tokenUrl = "https://identity.example.com/oauth2/token",
            scopes = {
                @OAuthScope(
                    name = "openid",
                    description = "Request OpenID Connect authentication"
                ),
                @OAuthScope(
                    name = "profile",
                    description = "Read basic user profile claims"
                ),
                @OAuthScope(
                    name = "orders:read",
                    description = "Read orders"
                ),
                @OAuthScope(
                    name = "orders:write",
                    description = "Create and update orders"
                )
            }
        )
    ),
    description = "Log in via the organization's Authorization Server"
)
class OAuthDocumentation {
}
~~~

The scheme name <code>ordersOAuth</code> is used to reference it from operations. The authorization URL and token URL belong to the Authorization Server, not the Resource Server. Hostnames in the example must be replaced with the actual addresses of the deployment environment.

The two scopes <code>openid</code> and <code>profile</code> are declared so the example can use OIDC with Authorization Code flow. Scopes <code>orders:read</code> and <code>orders:write</code> are API access permissions defined by the system.

Attach the requirement to an operation:

~~~java
import io.swagger.v3.oas.annotations.security.SecurityRequirement;
import java.util.List;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
class OrderController {

    @GetMapping("/api/orders")
    @SecurityRequirement(
        name = "ordersOAuth",
        scopes = {"orders:read"}
    )
    List<OrderResponse> listOrders() {
        // Return list of orders
        return List.of();
    }
}
~~~

The requirement tells Swagger UI that the operation needs scope <code>orders:read</code>. It does not grant that scope to the user; the Authorization Server decides granted scopes, while the Resource Server enforces scopes when requests arrive.

## 7. Configuring Swagger UI for Authorization Code + PKCE

Swagger UI running in the browser is a public client. JavaScript code and configuration are sent to the browser, so a client secret cannot be kept confidential. With Authorization Code flow for a browser client, enable PKCE and register the exact redirect URI at the Authorization Server.

Example springdoc configuration in <code>application.yml</code>:

~~~yaml
springdoc:
  swagger-ui:
    oauth2-redirect-url: https://docs.example.com/swagger-ui/oauth2-redirect.html
    oauth:
      client-id: swagger-ui
      use-pkce-with-authorization-code-grant: true
      scopes:
        - openid
        - profile
        - orders:read
~~~

External configuration property names use kebab-case; camelCase can be used per Spring Boot binding support. The redirect address must match the exact URI registered for the client at the Authorization Server, including scheme, host, port, path, and trailing slash if any.

If the UI is served at a custom path or behind a reverse proxy, check the actual callback URL. Do not assume the redirect URI is always the default path if the application changed <code>springdoc.swagger-ui.path</code>.

Never put a client secret in <code>application.yml</code> sent to the browser, in JavaScript configuration, or in frontend source code. For public clients, use client ID and PKCE. If a flow requires a confidential client secret, execute it on the backend or an appropriate tool capable of keeping secrets, rather than embedding secrets in Swagger UI.

## 8. Which boundaries do Redirect URI, PKCE, and CORS belong to?

These configurations are often mixed up:

| Configuration | Responsible Component | Purpose |
|---|---|---|
| Redirect URI registration | Authorization Server and OAuth2 client | Allow only registered callbacks |
| PKCE | OAuth2 client and Authorization Server | Bind the authorization code to the client that initiated the request |
| Token endpoint CORS | Authorization Server | Allow the browser to send cross-origin token requests if required by the flow |
| API CORS | Resource Server | Allow the browser to read responses from a different-origin API |

PKCE uses code verifier and code challenge to reduce the risk of an authorization code being stolen and exchanged for tokens by another client. Swagger UI generates the verifier and sends the challenge in the authorization request; when exchanging the code, it sends the matching verifier. Prefer challenge method <code>S256</code> per Authorization Server configuration and capability.

The authorization endpoint is normally opened via browser navigation, not XHR. The token endpoint is normally called from the browser to exchange the code, so if on a different origin, the Authorization Server needs a CORS policy for Swagger UI's origin. After obtaining a token, cross-origin API requests also require the Resource Server to allow the origin, methods, and headers like <code>Authorization</code>.

Do not arbitrarily enable wildcard origins with credentials in production. Allow the exact origin of the documentation page and only necessary methods/headers.

## 9. OIDC: ID token and access token serve different purposes

OpenID Connect adds an identity layer on top of OAuth2. When using OIDC, the Authorization Server/Identity Provider can return:

- **ID token**: contains authentication information about the user and is issued to the OIDC client. The ID token's audience is typically the client ID.
- **Access token**: credential for the client to call the Resource Server. Audience and scopes must match the protected API.

Do not use an ID token in place of an access token when calling APIs unless the system's contract specifically designs for it and the Resource Server is explicitly configured to accept that token type. Normally, Swagger UI sends the access token in the Bearer header; the Resource Server verifies tokens intended for itself.

Example OIDC Discovery scheme in OpenAPI:

~~~java
import io.swagger.v3.oas.annotations.enums.SecuritySchemeType;
import io.swagger.v3.oas.annotations.security.SecurityScheme;

@SecurityScheme(
    name = "companyOidc",
    type = SecuritySchemeType.OPENIDCONNECT,
    openIdConnectUrl =
        "https://identity.example.com/.well-known/openid-configuration",
    description = "Organization's OpenID Connect discovery"
)
class OidcDocumentation {
}
~~~

The discovery URL describes the OpenID Provider's metadata. It is not a business endpoint of the Resource Server. The level of direct interactive OpenID Connect support in Swagger UI depends on the UI version and how the scheme is described; for typical OAuth2 API testing flows, OAuth2 Authorization Code + PKCE configuration is usually used to obtain an access token.

## 10. Resource Server in Spring Boot

For JWT access tokens, Spring Security can configure the application in the OAuth2 Resource Server role. Basic example:

~~~xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-oauth2-resource-server</artifactId>
</dependency>
~~~

~~~yaml
spring:
  security:
    oauth2:
      resourceserver:
        jwt:
          issuer-uri: https://identity.example.com/issuer
~~~

The Issuer URI helps the Resource Server discover metadata and public keys to verify JWTs as configured. The application still must define appropriate audience, scope, and business permission policies. Do not assume declaring only the issuer checks all API-specific conditions.

Example restricting an operation by scope:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
class ResourceServerSecurity {

    @Bean
    SecurityFilterChain apiSecurity(HttpSecurity http) throws Exception {
        return http
            .authorizeHttpRequests(authorize -> authorize
                .requestMatchers("/api/orders/**")
                    .hasAuthority("SCOPE_orders:read")
                .anyRequest().authenticated()
            )
            .oauth2ResourceServer(oauth2 ->
                oauth2.jwt(Customizer.withDefaults())
            )
            .build();
    }
}
~~~

Spring Security normally maps scopes in JWTs to authorities prefixed with <code>SCOPE_</code>. For example, scope <code>orders:read</code> becomes <code>SCOPE_orders:read</code>. If tokens use custom claims or a different permission structure, configure an appropriate converter.

The example above only illustrates endpoint-level scope checks. For per-order operations, the application must also check whether the user has permission on that specific order.

## 11. JWT and opaque tokens: how does the Resource Server verify them?

| Access Token Type | How the Resource Server Checks It | Characteristics |
|---|---|---|
| JWT | Verifies signature and claims using trusted keys | Can be verified locally after fetching keys; requires handling key rotation and claim policies |
| Opaque token | Calls the Authorization Server's introspection endpoint | AS returns token status and metadata; requests depend on introspection connectivity |

Swagger UI does not need to decode or verify tokens to send requests. It passes the access token issued by the Authorization Server to the Resource Server. The Resource Server is the component that verifies the token.

Do not conclude a JWT is valid simply because it has three dot-separated parts or its payload can be decoded. JWT contents can be read, yet signature and claims still require verification. Similarly, an opaque token should not be treated as a random string that the application can validate with arbitrary custom logic.

## 12. Common errors by boundary

**Cannot open login page after clicking Authorize.** Check authorization URL, client registration, redirect URI, HTTPS, and OAuth2 flow configuration in OpenAPI.

**Authorization Server reports invalid redirect URI.** Compare the URI Swagger UI actually uses with the registered URI; check context path, reverse proxy, and trailing slash.

**Token endpoint blocked by CORS.** Check the Authorization Server's CORS policy for Swagger UI's origin. Resource Server CORS cannot fix errors at the token endpoint.

**Swagger UI receives token but API returns 401.** Check whether Swagger UI sends the access token or ID token, Bearer header, signature, issuer, expiry, audience, and the Resource Server's decoder/introspection configuration.

**API returns 403.** The token may be valid but lacking scopes, roles, or resource permissions. Cross-check scopes in the token, OpenAPI requirements, and backend authorization rules.

**Swagger UI sends request but browser cannot read response.** Check Resource Server CORS, especially preflight and the <code>Authorization</code> header. The request may have reached the server while the browser blocked JavaScript from reading the response.

**Putting a client secret in Swagger UI configuration.** Frontend configuration is sent to the browser, so users can view the secret. Use a public client with PKCE or move confidential client flows to the backend.

**Documentation declares scopes but backend does not check them.** <code>@SecurityRequirement</code> only describes the contract. Resource Server configuration and authorization rules must enforce real permissions.

**Protecting Swagger UI while exposing OpenAPI JSON.** If policy requires documentation to be private, protect the UI page, JSON/YAML, and documentation endpoints under the same policy.

## 13. How to investigate a failed request

Follow this order to pinpoint where the request stops:

1. **Authorize did not complete:** check redirect, login, consent, authorization code, and token endpoint at the Authorization Server.
2. **Did not receive access token:** inspect code exchange errors, PKCE verifier, client ID, redirect URI, and token endpoint CORS.
3. **Have token but cannot send API request:** check server URL, request URL, Authorization header, and Resource Server CORS.
4. **API returns 401:** check token type, signature, issuer, expiry, audience, and introspection status.
5. **API returns 403:** check scope, role, authority, tenant, and resource permissions.
6. **API returns 2xx but wrong data:** check business logic, response schema, and returned data.

When logging or sharing errors, never include access tokens, refresh tokens, authorization codes, session cookies, or client secrets in documents. Redact credentials and personal information before sending logs or screenshots.

## 14. Review checklist before publishing an API testing flow

- [ ] OpenAPI accurately declares the OAuth2 flow and scopes.
- [ ] Authorization URL and token URL point to the right environment's Authorization Server.
- [ ] Swagger UI is registered as an appropriate public client and uses Authorization Code + PKCE.
- [ ] Redirect URI matches the client configuration at the Authorization Server exactly.
- [ ] No client secret is embedded in frontend or Swagger UI.
- [ ] Token endpoint CORS allows the exact documentation origin if needed.
- [ ] Swagger UI sends the access token to the Resource Server via the Bearer header.
- [ ] Resource Server verifies signature/status, issuer, expiration, and audience per policy.
- [ ] Scopes/authorities in the token are checked at the endpoint and business layers.
- [ ] Resource Server CORS allows the right origin and headers if the UI is on a different origin.
- [ ] OpenAPI documentation and Swagger UI are protected per publication policy.
- [ ] Tested separately for missing token, expired token, wrong audience, and missing scope scenarios.

## References

- [OpenAPI Specification – OAuth Flows Object](https://spec.openapis.org/oas/latest.html#oauth-flows-object): describing OAuth2 flows in OpenAPI.
- [Swagger UI – OAuth 2.0 Configuration](https://swagger.io/docs/open-source-tools/swagger-ui/usage/oauth2/): configuring OAuth2, redirect URL, and PKCE for Swagger UI.
- [OAuth 2.0 Security Best Current Practice (RFC 9700)](https://www.rfc-editor.org/rfc/rfc9700): current OAuth2 security guidance.
- [OAuth 2.0 Authorization Framework (RFC 6749)](https://www.rfc-editor.org/rfc/rfc6749): roles of client, authorization server, resource owner, and resource server.
- [Proof Key for Code Exchange (RFC 7636)](https://www.rfc-editor.org/rfc/rfc7636): PKCE mechanism.
- [OpenID Connect Core](https://openid.net/specs/openid-connect-core-1_0.html): ID token, access token, and OIDC authentication flows.
- [Spring Security – OAuth2 Resource Server JWT](https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/jwt.html): verifying JWT access tokens in Resource Server.
- [Spring Security – OAuth2 Resource Server Opaque Token](https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/opaque-token.html): introspection with opaque tokens.
- [springdoc-openapi](https://springdoc.org/): integrating OpenAPI and Swagger UI with Spring Boot.
