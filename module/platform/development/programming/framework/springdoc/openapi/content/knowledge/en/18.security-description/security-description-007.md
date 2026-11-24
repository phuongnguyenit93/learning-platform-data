# OAuth2 and OpenID Connect as Contract-Described Mechanisms

Modern APIs often require clients to prove access permissions before reading or modifying data. OAuth 2.0 provides an authorization framework for clients to obtain an access token and send that token to a resource server. OpenID Connect (OIDC) adds a user identity authentication layer on top of OAuth 2.0, allowing clients to receive information about the signed-in user.

In OpenAPI documentation, springdoc-openapi can describe these mechanisms using security schemes and security requirements. The documentation states which authentication types the API accepts, which authorization flows are supported, and which scopes an operation requires. Swagger UI can use that information to assist testing requests through an identity provider.

The OpenAPI contract describes how clients interact with the API. It does not issue tokens, validate JWT signatures, enforce permissions, or configure Spring Security. Those parts must be implemented in the authorization server and resource server.

## 1. What problems do OAuth2 and OpenID Connect solve?

OAuth 2.0 is an authorization framework. Rather than sharing user passwords with every application, a client requests access permission through an authorization server and receives an access token. The client sends the token to the API; the resource server validates the token and decides whether the request is permitted.

OIDC builds on OAuth 2.0 to standardize user authentication. OIDC defines the ID token along with endpoints and discovery metadata so clients know the user's identity and how to interact with the OpenID Provider.

| Component | Role |
|---|---|
| Resource owner | User or entity with authority over the resource |
| Client | Application requesting access permissions |
| Authorization server | Authenticates, issues authorization codes and tokens |
| Resource server | API protecting data, validates access tokens |
| OpenID Provider (OP) | Identity provider implementing OIDC |
| Access token | Token sent by client to API to prove access permission |
| ID token | OIDC token containing user authentication information, intended for the client |

A system can use the same provider for both the authorization server and the OpenID Provider. However, the roles of access tokens and ID tokens remain distinct.

## 2. Distinguishing OAuth2 from OIDC

OAuth2 answers the question: **which resources is the client permitted to access?** OIDC additionally answers the question: **who is the signed-in user?**

| Criterion | OAuth 2.0 | OpenID Connect |
|---|---|---|
| Primary purpose | Authorize access to resources | Authenticate user identity on top of OAuth 2.0 |
| Typical tokens | Access token | ID token and access token |
| Example scopes | products.read, orders.write | openid, profile, email, and API scopes |
| Metadata | Provider-specific OAuth endpoints and configuration | Standardized discovery document |
| API token usage | Typically receives access token | Resource server still uses access token |
| Client login | Can authorize without knowing user identity | Can obtain identity via ID token and UserInfo |

Do not send an ID token to an API as if it were an access token. An ID token is issued for the client and carries the client's audience; an access token is issued for the resource server to check access rights. The API must validate access tokens according to the authorization server's policy.

OIDC does not replace OAuth2. An OIDC client still uses OAuth2 flows to obtain tokens while requesting the openid scope to activate OpenID Connect semantics.

## 3. Access token, ID token, and scope

### 3.1. Access token

An access token represents the permissions granted to the client. APIs typically receive tokens via the HTTP Authorization header:

~~~http
GET /api/v1/products
Authorization: Bearer eyJhbGciOi...
~~~

The resource server validates the token according to the agreed format and policy. For JWTs, checks typically include signature, issuer (iss), audience (aud), lifetime (exp, nbf), and required authorization claims. If the token is opaque, the resource server may need an introspection endpoint rather than decoding the JWT itself.

Do not place real tokens in OpenAPI examples, logs, or documentation. Use masked illustrative strings or dummy examples.

### 3.2. ID token

An ID token is proof of identity authentication issued by an OpenID Provider to a client. An ID token typically contains claims such as:

- iss: issuer that issued the token.
- sub: subject identifier at the issuer.
- aud: client the token is intended for.
- exp: expiration time.
- iat: issuance time.
- nonce: value binding the login request to the response, when the flow uses a nonce.

The client must verify the ID token per OIDC, including signature, issuer, audience, and time checks; for requests with a nonce, the nonce must be matched. APIs should not use ID tokens in place of access tokens simply because both may be JWTs.

### 3.3. Scope

Scopes restrict granted permissions. Examples:

| Scope | Business meaning |
|---|---|
| products.read | Read product list and details |
| products.write | Create or update products |
| orders.read | Read orders |
| orders.write | Create or modify orders |
| openid | Request OIDC authentication semantics |
| profile | Request standard profile claims |
| email | Request email information per OIDC |

Scopes are strings agreed upon between the authorization server and the API. Scope names are case-sensitive under OAuth rules; keep names consistent across token issuance configuration, permission checks, and OpenAPI documentation.

## 4. Commonly used OAuth2 flows

OAuth 2.0 has several grant types, though not every flow fits modern applications.

| Flow | Use case | Characteristics |
|---|---|---|
| Authorization Code + PKCE | Web apps, SPAs, mobile apps, or interactive clients | User logs in at authorization server; client exchanges code for token |
| Client Credentials | Service-to-service communication | Client authenticates using application identity, not representing an end user |
| Device Authorization | Devices with limited input interfaces | Device displays code for user to complete authentication on another device |
| Refresh token | Request a new access token when the old token expires | Subsequent token issuance mechanism, not an independent flow in OpenAPI |

OpenAPI OAuth2 flows define standard fields implicit, password, clientCredentials, and authorizationCode. Device Authorization has no dedicated flow field in OpenAPI's OAuth2 model; if the API uses this flow, document how to obtain tokens in the integration guide.

The Implicit flow is no longer recommended for new applications. Resource Owner Password Credentials (password grant) should not be used either; modern OAuth security guidance recommends Authorization Code with PKCE for interactive clients. Do not include the password flow in new contracts merely because annotations or OpenAPI can still represent it.

## 5. Authorization Code with PKCE

This is the typical choice for applications with user login, especially SPAs and mobile apps. PKCE adds a mechanism proving that the client exchanging the authorization code is the same client that initiated the request, reducing the risk of code interception and reuse.

Conceptual flow:

~~~text
Client                 Authorization Server             Resource API
  |                              |                            |
  |-- authorize + code_challenge>|                            |
  |<-- user authenticates -------|                            |
  |<-- authorization code -------|                            |
  |                              |                            |
  |-- code + code_verifier ----->|                            |
  |<-- access token / ID token --|                            |
  |                                                           |
  |---------------- access token ---------------------------->|
  |<--------------- protected API response ------------------|
~~~

Points to align on:

- Authorization URL is the endpoint where the client redirects users for authorization.
- Token URL is the endpoint where the client exchanges the authorization code for tokens.
- Redirect URI must be registered accurately with the authorization server.
- The client generates a random code_verifier and sends the corresponding code_challenge in the authorization request.
- The token request sends back code_verifier for the authorization server to verify.
- With OIDC, the client requests the openid scope; profile or email can also be requested if needed.

PKCE is a requirement of the flow and client/authorization server configuration. An OpenAPI OAuth2 flow describes the authorization URL, token URL, and scopes, but has no dedicated standard property to mark code_challenge_method=S256. State the PKCE requirement clearly in the integration description and configure Swagger UI accordingly.

## 6. Client Credentials for service-to-service

Client Credentials fits when a service calls an API using the application's own identity, with no interactive user:

~~~text
Backend Service                Authorization Server           Resource API
      |                                  |                          |
      |-- client authentication ------->|                          |
      |<-- access token ----------------|                          |
      |                                                             |
      |---------------- access token ------------------------------>|
      |<--------------- API response -------------------------------|
~~~

The client authenticates using a registered mechanism, such as a client secret or private key. Never embed a client secret in browser or mobile applications because users can extract it. For production workloads, consider stronger client authentication mechanisms according to your authorization server's capabilities.

Client Credentials tokens typically represent the application, so granted permissions should be bound to the corresponding service account, client, or policy. Do not assume this token carries an end-user identity.

## 7. Declaring an OAuth2 Security Scheme in OpenAPI

In OpenAPI, OAuth2 is described using a security scheme with type oauth2. Each flow declares endpoints and supported scopes. Springdoc can generate this model from Swagger annotations:

~~~java
import io.swagger.v3.oas.annotations.security.OAuthFlow;
import io.swagger.v3.oas.annotations.security.OAuthFlows;
import io.swagger.v3.oas.annotations.security.OAuthScope;
import io.swagger.v3.oas.annotations.security.SecurityScheme;
import io.swagger.v3.oas.annotations.enums.SecuritySchemeType;
import org.springframework.context.annotation.Configuration;

@Configuration
@SecurityScheme(
    name = "oauth2",
    type = SecuritySchemeType.OAUTH2,
    flows = @OAuthFlows(
        authorizationCode = @OAuthFlow(
            authorizationUrl = "https://id.example.com/oauth2/authorize",
            tokenUrl = "https://id.example.com/oauth2/token",
            scopes = {
                @OAuthScope(
                    name = "products.read",
                    description = "Read product information."
                ),
                @OAuthScope(
                    name = "orders.write",
                    description = "Create and update orders."
                )
            }
        )
    )
)
public class OAuth2OpenApiConfiguration {
}
~~~

The URL values in the example are illustrative addresses. Replace them with the official endpoints of your authorization server. The name oauth2 is the scheme's identifier key in OpenAPI; security requirements must reference this exact name.

If the application only uses Client Credentials, declare the corresponding flow:

~~~java
@SecurityScheme(
    name = "serviceOAuth",
    type = SecuritySchemeType.OAUTH2,
    flows = @OAuthFlows(
        clientCredentials = @OAuthFlow(
            tokenUrl = "https://id.example.com/oauth2/token",
            scopes = {
                @OAuthScope(
                    name = "products.read",
                    description = "Read product data."
                )
            }
        )
    )
)
~~~

Do not declare flows that the system does not actually support. If the authorization server supports multiple flows, only document the flows clients are permitted to use for that API.

## 8. Declaring an OpenID Connect Security Scheme

OpenAPI has a dedicated security scheme for OpenID Connect with type openIdConnect. This scheme points to the OpenID Provider's discovery document:

~~~java
import io.swagger.v3.oas.annotations.enums.SecuritySchemeType;
import io.swagger.v3.oas.annotations.security.SecurityScheme;
import org.springframework.context.annotation.Configuration;

@Configuration
@SecurityScheme(
    name = "oidc",
    type = SecuritySchemeType.OPENIDCONNECT,
    openIdConnectUrl =
        "https://id.example.com/.well-known/openid-configuration"
)
public class OidcOpenApiConfiguration {
}
~~~

openIdConnectUrl must point to the OpenID Provider Configuration Document, usually at the path /.well-known/openid-configuration. This discovery document contains metadata such as issuer, authorization endpoint, token endpoint, UserInfo endpoint, and JWKS URI. Do not use the JWKS URI directly in place of the discovery URL.

The discovery document helps clients learn the provider's endpoints and capabilities. It does not replace token verification at the API. The resource server must still validate access tokens against issuer, audience, signature, and required claims.

## 9. Choosing an OAuth2 scheme or an OpenID Connect scheme?

If the API needs to explicitly describe individual OAuth2 flows and scopes, type oauth2 is the direct choice. If the contract wants to reference the provider's OIDC discovery configuration, you can use type openIdConnect.

| Need | Suitable security scheme |
|---|---|
| Publish authorization code, token URL, and specific scopes | OAuth2 |
| Publish client credentials and scopes | OAuth2 |
| Reference OIDC discovery document | OpenID Connect |
| Only use Bearer JWT without describing OAuth flows | HTTP Bearer |

There is no need to declare multiple schemes simultaneously for the same mechanism if doing so makes clients think they must choose between non-existent options. Choose the representation that accurately reflects how clients obtain tokens and how the API validates them.

An API can use OAuth2 to document access permissions and OIDC for client sign-in. Still, the ID token remains for the client; the API protects resources using access tokens.

## 10. Requiring scopes per operation

Declaring a security scheme only defines the authentication mechanism. To specify which operation needs which scopes, you must add a security requirement.

Example of a read-only product operation:

~~~java
import io.swagger.v3.oas.annotations.Operation;
import io.swagger.v3.oas.annotations.security.SecurityRequirement;
import org.springframework.web.bind.annotation.GetMapping;

@GetMapping("/api/v1/products")
@Operation(
    summary = "List products",
    security = @SecurityRequirement(
        name = "oauth2",
        scopes = {"products.read"}
    )
)
public List<ProductResponse> listProducts() {
    return productService.findAll();
}
~~~

Example of an operation creating an order:

~~~java
@PostMapping("/api/v1/orders")
@Operation(
    summary = "Create an order",
    security = @SecurityRequirement(
        name = "oauth2",
        scopes = {"orders.write"}
    )
)
public OrderResponse createOrder(
        @RequestBody CreateOrderRequest request) {
    return orderService.create(request);
}
~~~

Scope names in the requirement must exist in the OAuth2 scheme's flow. Undeclared or misspelled scopes can make the documentation misleading and some tools may emit warnings.

With an OIDC scheme, requirements can also list OIDC scopes such as openid or profile if those are scopes the client must request. OIDC scopes serve identity requests; business API scopes still must be agreed upon by the authorization server and resource server.

## 11. Document-wide and per-operation security requirements

You can place a security requirement at the document level to apply by default to every operation. In annotations, this can be declared via @OpenAPIDefinition:

~~~java
import io.swagger.v3.oas.annotations.OpenAPIDefinition;
import io.swagger.v3.oas.annotations.security.SecurityRequirement;

@OpenAPIDefinition(
    security = {
        @SecurityRequirement(
            name = "oauth2",
            scopes = {"products.read"}
        )
    }
)
public class ApiOpenApiDefinition {
}
~~~

Global requirements fit when every operation in the document shares the same protection policy. If an API has both public and protected endpoints, document security per operation to avoid misapplication.

In OpenAPI, operation-level security requirements override document-level requirements. A security array with multiple objects expresses alternative options (OR); multiple schemes within the same object express conditions that must be satisfied simultaneously (AND). Understanding these semantics is necessary when an operation accepts either OAuth2 or an API key, or requires multiple mechanisms at once.

If a public endpoint resides in a document with global security, OpenAPI expresses the exception using an empty security requirement on that operation. Check the final JSON to ensure annotations or customizers produced the empty security array properly.

## 12. Describing OAuth2 and OIDC in OpenAPI YAML

The condensed specification below illustrates both scheme types:

~~~yaml
openapi: 3.0.3
info:
  title: Store API
  version: 1.0.0
components:
  securitySchemes:
    oauth2:
      type: oauth2
      flows:
        authorizationCode:
          authorizationUrl: https://id.example.com/oauth2/authorize
          tokenUrl: https://id.example.com/oauth2/token
          scopes:
            products.read: Read product information.
            orders.write: Create and update orders.
    oidc:
      type: openIdConnect
      openIdConnectUrl: https://id.example.com/.well-known/openid-configuration
paths:
  /api/v1/products:
    get:
      summary: List products
      security:
        - oauth2:
            - products.read
      responses:
        '200':
          description: Product list.
  /api/v1/profile:
    get:
      summary: Get current user profile
      security:
        - oidc:
            - openid
            - profile
      responses:
        '200':
          description: User profile.
~~~

This is an example of document structure. When using an OIDC scheme, clients need to reference the exact discovery document. When using OAuth2, flows must reflect the authorization server's actual flows. Never copy sample URLs into a production environment.

## 13. Configuring Swagger UI for Authorization Code and PKCE

Swagger UI can initiate an OAuth authorization flow so integrators can test the API. With Authorization Code + PKCE, configure the client ID and enable PKCE:

~~~yaml
springdoc:
  swagger-ui:
    oauth:
      client-id: store-swagger-ui
      use-pkce-with-authorization-code-grant: true
~~~

The Client ID must be registered at the authorization server. Swagger UI's redirect URI must also be registered accurately; the default URI typically sits under swagger-ui/oauth2-redirect.html, though it can vary by context path or UI configuration.

Do not configure a client secret in Swagger UI for SPAs or browser applications. JavaScript code and configuration are sent to the browser, so secrets cannot be kept confidential. If a client secret is needed, use a confidential client running on a backend and design an appropriate flow.

Other Swagger UI settings can be provided via springdoc.swagger-ui.oauth, though property names and behaviors should be verified against your installed springdoc version. Only expose the client ID and information permitted to appear on the browser side.

## 14. Configuring Swagger UI for Client Credentials

Swagger UI supports entering OAuth2 details to obtain tokens according to the documented flow. However, Client Credentials typically requires client authentication. If a client secret is entered into a browser-based interface, the secret is exposed to users and can be extracted.

For documentation aimed at partners or technical staff, Swagger UI can be used to inspect flows and scopes. Executing Client Credentials should use a tool or backend capable of protecting credentials. Do not enable client secrets on a public Swagger UI page.

If your organization uses private_key_jwt, mutual TLS, or another client authentication mechanism, document that requirement clearly in the integration guide because basic OAuth2 flow configuration cannot express every authorization server implementation detail.

## 15. Connection to Spring Security Resource Server

Spring Security Resource Server is the component enforcing endpoint protection via bearer tokens. A common JWT configuration uses an issuer URI:

~~~yaml
spring:
  security:
    oauth2:
      resourceserver:
        jwt:
          issuer-uri: https://id.example.com
~~~

Spring Security can use issuer metadata to locate verification keys and validate the issuer. The application still needs to define audience, scopes, roles, and authorization conditions matching the system.

Example checking scopes in authorization configuration:

~~~java
http.authorizeHttpRequests(authorize -> authorize
    .requestMatchers(HttpMethod.GET, "/api/v1/products/**")
        .hasAuthority("SCOPE_products.read")
    .requestMatchers(HttpMethod.POST, "/api/v1/orders/**")
        .hasAuthority("SCOPE_orders.write")
    .anyRequest().authenticated()
);
~~~

With a JWT resource server, Spring Security typically maps scopes to authorities prefixed with SCOPE_. The rules above are examples only; configure authentication, CSRF, CORS, sessions, and other matchers per application.

OpenAPI metadata and Spring Security configuration must match. If the documentation says an operation needs orders.write while runtime only checks orders.read, clients receive a wrong contract. Conversely, if runtime requires a scope that the documentation does not describe, integrators will struggle to call the API properly.

## 16. Discovery, issuer, and JWKS

OIDC Discovery provides metadata to clients. A discovery document typically publishes:

- issuer: OpenID Provider identifier.
- authorization_endpoint: where authorization requests start.
- token_endpoint: where codes are exchanged for tokens.
- userinfo_endpoint: endpoint retrieving user information.
- jwks_uri: where to fetch the JSON Web Key Set to verify token signatures.
- scopes_supported: scopes supported by the provider.
- response_types_supported and grant_types_supported: supported response and grant types.

The resource server uses issuer metadata or equivalent configuration to locate public keys at the JWKS URI. When keys are rotated, the token verification library needs to refresh JWKS using an appropriate mechanism.

The issuer in configuration must match the token's iss claim per provider policy. Do not verify signatures alone; a JWT with a valid signature issued by an untrusted issuer or intended for a different audience must still be rejected.

OpenAPI's openIdConnectUrl points to the discovery document. OAuth2's authorizationUrl and tokenUrl point directly to their respective endpoints. These two URL types serve different roles.

## 17. Distinguishing scope, role, and claim

Scopes typically describe permissions granted to a client under the OAuth contract. Roles typically represent business roles of a user or service. Claims are attributes carried within a token.

Example access token payload:

~~~json
{
  "iss": "https://id.example.com",
  "sub": "user-123",
  "aud": ["store-api"],
  "scope": "products.read orders.write",
  "roles": ["ORDER_MANAGER"],
  "exp": 1920000000
}
~~~

This is an illustrative payload, not a usable token. products.read and orders.write are scopes; ORDER_MANAGER is a role; sub and aud are standard or token-context claims.

OpenAPI OAuth2 security requirements are well suited for describing scopes. If the API also checks custom roles or claims, describe those business conditions in description or supplementary security documentation. Do not try to express every internal policy as an OAuth scope if the authorization server does not issue those scopes.

## 18. Common errors when describing OAuth2/OIDC

| Error | Consequence | Fix |
|---|---|---|
| Using an ID token to call resource APIs | Token audience or purpose does not match | Send access token to resource server |
| Declaring only a security scheme without adding requirements | Operations do not clearly show authentication requirements | Attach security requirements at document or operation level |
| Requirement references wrong scheme name | Documentation cannot link the authentication mechanism | Use exact matching name as SecurityScheme name |
| Scope in requirement does not exist in flow | Documentation and authorization server are out of sync | Synchronize scope lists |
| Using password grant for new applications | Increases risk of exposing user credentials | Use Authorization Code + PKCE |
| Enabling PKCE in Swagger UI without registering redirect URI | Authorization server rejects callback | Register exact redirect URI |
| Placing client secret in browser | Secret can be extracted by users | Use public client with PKCE or confidential backend |
| Using JWKS URL as openIdConnectUrl | Clients cannot retrieve discovery metadata | Use OpenID Provider Configuration URL |
| Thinking OpenAPI security replaces Spring Security | Runtime endpoints may still be unprotected | Configure and test Resource Server |
| Checking only JWT signature | Tokens with wrong issuer or audience can still be accepted | Verify issuer, audience, lifetime, and policy |
| Describing an OAuth flow unsupported by provider | Swagger UI builds invalid requests | Publish only flows actually permitted |

## 19. Checking documentation and security behavior

After running the application, open the OpenAPI document:

~~~bash
curl -s http://localhost:8080/v3/api-docs
~~~

Verify:

1. components.securitySchemes has an OAuth2 or OpenID Connect scheme of the right type.
2. OAuth2 flows have appropriate authorization URL, token URL, and scopes.
3. OIDC scheme points to the discovery document, not mistakenly to JWKS.
4. Each operation has accurate security requirements and scopes.
5. Public operations do not accidentally receive security requirements.
6. Swagger UI uses properly configured client ID, PKCE, and redirect URI.
7. Documentation contains no client secrets, access tokens, or sensitive data.

Next, test at runtime:

- Missing token: protected endpoints must reject the request.
- Wrong signature, issuer, or audience: resource server must reject.
- Expired token: request must be rejected.
- Token missing required scope: API must return an appropriate authorization error.
- Token with sufficient scopes: client is allowed to execute the operation.
- Public endpoints: work according to the published public policy.

Documentation testing and runtime testing are separate tasks. Both must pass for the OAuth2/OIDC contract to reflect the system accurately.

## 20. Takeaways

- OAuth2 is an authorization framework; OIDC adds user identity authentication.
- Access tokens are for resource APIs; ID tokens are for OIDC clients.
- Scopes describe granted permissions and can be declared in OAuth2 security schemes.
- Authorization Code + PKCE fits interactive clients; Client Credentials fits service-to-service.
- Do not use Implicit or Resource Owner Password Credentials for new designs.
- OpenAPI describes OAuth2 with type oauth2 and flows; OIDC uses type openIdConnect with a discovery URL.
- Security schemes define the mechanism; security requirements attach the mechanism and scopes to operations.
- Swagger UI can assist authorization flows, but must never contain client secrets for public clients.
- openIdConnectUrl is the discovery document; jwks_uri is the address of token verification keys.
- OpenAPI does not configure the authorization server or Spring Security Resource Server.
- Always reconcile scopes, issuer, audience, token validation, and runtime policies with the documentation.

When describing OAuth2 and OpenID Connect with springdoc-openapi, publish the exact flows, endpoints, scopes, and security requirements that clients need to use. Distinguish access tokens from ID tokens, protect client credentials, and verify both the generated documentation and Spring Security behavior so the integration contract is reliable.
