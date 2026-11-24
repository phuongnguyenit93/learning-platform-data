# Legacy or Deprecated Flows Must Be Identified Separately

## 1. Why identify legacy OAuth2/OIDC flows separately?

OAuth 2.0 and OpenID Connect (OIDC) provide multiple authorization and authentication flows. Some flows were designed for older application contexts, when browsers, mobile apps, and token storage differed from today. Security recommendations have evolved; continuing to use a legacy flow can expose credentials, put tokens in the front channel, or make it difficult for applications to support MFA and federated login.

In the Springdoc OpenAPI module, documentation must accurately describe how clients obtain tokens and call APIs. When an application still supports a legacy flow for compatibility reasons, the documentation should clearly identify that flow as legacy, state its limitations, and point out alternatives. Do not place legacy flows alongside modern flows as if they shared the same level of recommendation.

Distinguish three statuses:

- **No longer recommended for new applications**: should not be chosen when designing new integrations; requires a migration plan if currently in use.
- **Legacy but still present for compatibility**: may need to be documented so existing clients continue operating; must be labeled and limited in scope.
- **Still appropriate for a specific use case**: should not be called obsolete merely because it differs from the common user login flow.

This article classifies common OAuth2/OIDC flows, explains their risks, and shows how to identify them in Springdoc OpenAPI documentation.

## 2. Quick classification of flows

| Flow | Current status and scope | Recommended action |
|---|---|---|
| OAuth2 Implicit Grant | No longer recommended; OAuth 2.0 Security BCP specifies not using it for new applications | Migrate to Authorization Code with PKCE |
| Resource Owner Password Credentials (ROPC/Password Grant) | No longer recommended; do not use in new designs | Migrate to Authorization Code with PKCE or an appropriate flow by client type |
| Authorization Code without PKCE | Legacy implementation pattern, especially risky for public clients | Add PKCE, preferring the S256 method |
| OIDC Implicit Flow | Legacy flow; tokens are returned via the front channel | Use OIDC Authorization Code Flow with PKCE |
| OIDC Hybrid Flow | Still defined in OIDC Core but less suitable for most modern applications | Prefer Authorization Code Flow with PKCE unless special requirements apply |
| Client Credentials | Still appropriate for machine-to-machine communication, does not represent user login | Continue using when a client service needs to access a resource server |
| Device Authorization Grant | Still appropriate for input-constrained devices or devices without a full browser | Use when the device context fits |

Implicit and ROPC are the two flows that must be most clearly identified as no longer recommended. OIDC Hybrid should be described carefully: OIDC Core still defines this flow, so do not claim it has been removed from the standard; however, for most new applications, Authorization Code Flow combined with PKCE is usually the simpler and safer choice.

## 3. OAuth2 Implicit Grant: legacy flow to replace

Implicit Grant was designed for browser-based applications where clients could not securely store a client secret and previously lacked a suitable authorization code exchange model. The authorization server returned the access token directly to the client's redirect URI instead of returning an authorization code for the client to exchange at the token endpoint.

An illustrative request looks like:

~~~http
GET /authorize?
  response_type=token&
  client_id=browser-client&
  redirect_uri=https%3A%2F%2Fapp.example.com%2Fcallback&
  scope=products.read&
  state=random-state
~~~

In the redirect response, the access token can be returned in the URL fragment. The browser does not send the fragment in HTTP requests to the target server, but JavaScript on the redirect-receiving page can read the token. This puts the token in the front channel and increases risk exposure from malicious scripts, XSS, browser extensions, or URL handling bugs.

Key issues:

- The access token is issued directly via the authorization endpoint.
- The client has no code exchange step at the token endpoint.
- Protections based on code exchange are difficult to apply.
- The token is delivered into the browser environment, where malicious JavaScript can read it.
- This flow is no longer an appropriate choice for modern SPAs.

According to OAuth 2.0 Security Best Current Practice (RFC 9700), the implicit grant should not be used. For new applications, use Authorization Code Grant with PKCE.

## 4. Resource Owner Password Credentials Grant (ROPC)

ROPC, also called Password Grant, allows a client to collect the user's username and password directly and send them to the token endpoint in exchange for a token.

Legacy request example:

~~~http
POST /oauth/token
Content-Type: application/x-www-form-urlencoded

grant_type=password&
username=alice&
password=user-password&
client_id=legacy-client&
scope=products.read
~~~

This flow exposes the user's password directly to the client application. It weakens the authorization server's security boundary and complicates modern login mechanisms.

Limitations:

- The client must collect and process user passwords.
- Difficult to integrate MFA, passkeys, federated login, and interactive authentication policies.
- Users must trust the client application with their credentials.
- Applications can inadvertently store or log passwords.
- Switching identity providers or enforcing new login policies becomes harder.
- Does not fit the authorization model where the authorization server controls login interaction.

OAuth 2.0 Security BCP (RFC 9700) states that Resource Owner Password Credentials Grant must not be used. Do not implement ROPC for new clients and do not continue promoting it as a standard login method.

If a legacy system still needs support, restrict it to existing clients, mark it as legacy in documentation, schedule deprecation, and migrate users to Authorization Code Flow with PKCE. Do not replace ROPC by sending username/password through another custom endpoint; that merely shifts the risk elsewhere.

## 5. Authorization Code without PKCE: legacy setup needing upgrade

Authorization Code Flow remains the right flow for many types of applications. However, a legacy implementation may use authorization codes without Proof Key for Code Exchange (PKCE).

PKCE adds a pair of values:

- **code_verifier**: a temporary secret random string generated by the client and kept for the transaction session.
- **code_challenge**: a value derived from the verifier, sent in the authorization request.
- **code_challenge_method**: the derivation method; S256 should be used.

The client sends the challenge when requesting authorization. When exchanging the code at the token endpoint, the client sends the verifier. The authorization server verifies that the verifier matches the previously received challenge. If the authorization code is intercepted or stolen, another party lacking the verifier cannot easily exchange the code for a token.

Example authorization request:

~~~http
GET /authorize?
  response_type=code&
  client_id=web-client&
  redirect_uri=https%3A%2F%2Fapp.example.com%2Fcallback&
  scope=openid%20profile%20products.read&
  state=random-state&
  code_challenge=BASE64URL_SHA256_CHALLENGE&
  code_challenge_method=S256
~~~

When exchanging the code:

~~~http
POST /token
Content-Type: application/x-www-form-urlencoded

grant_type=authorization_code&
code=AUTHORIZATION_CODE&
redirect_uri=https%3A%2F%2Fapp.example.com%2Fcallback&
client_id=web-client&
code_verifier=ORIGINAL_RANDOM_VERIFIER
~~~

Public clients must use PKCE. For confidential clients, PKCE is also recommended to strengthen authorization code protection. Do not treat having a client secret as a reason to skip PKCE.

## 6. OIDC Implicit Flow and Hybrid Flow

OIDC extends OAuth2 to provide identity authentication information. In addition to an access token, OIDC can return an ID Token for the client to verify that the user has logged in. OIDC Core defines Authorization Code Flow, Implicit Flow, and Hybrid Flow.

**OIDC Implicit Flow** returns an ID Token and/or access token via the front channel. This is a legacy model with risks similar to OAuth2 Implicit Grant. For new applications, prefer OIDC Authorization Code Flow with PKCE.

**OIDC Hybrid Flow** combines responses from the authorization endpoint with code exchange at the token endpoint. Depending on the response type, the client can receive a code together with one or more tokens in the front channel. This flow is still defined by OIDC Core, but increases complexity and is not the default choice for most modern applications.

Do not lump both concepts under a single "removed" label:

- OIDC Implicit Flow is a legacy option that should be replaced in new applications.
- OIDC Hybrid Flow remains in the OIDC standard, but should only be retained when there is a specific architectural requirement and risks have been evaluated.

If receiving tokens from the front channel is not required, Authorization Code Flow with PKCE is usually simpler and ensures tokens are returned via the token endpoint.

## 7. OAuth2 and OIDC are not the same concept

OAuth2 is an authorization framework. It allows clients to obtain access tokens to access a resource server within granted permissions.

OpenID Connect is an identity layer built on top of OAuth2. OIDC adds components such as:

- **ID Token**: a JWT containing authentication claims about the user and login session.
- **UserInfo Endpoint**: an endpoint providing user claims according to granted permissions.
- **openid scope**: required scope for an authorization request to become an OIDC authentication request.
- **Discovery**: metadata about authorization endpoint, token endpoint, JWKS URI, and other capabilities.
- **JWKS**: public keys used to verify token signatures.

Distinguish:

| Token | Purpose | Where Used |
|---|---|---|
| Access Token | Grants access to an API/resource server | Sent to APIs using Bearer or appropriate token binding |
| ID Token | Tells the client the authentication result and user identity | OIDC client verifies issuer, audience, signature, nonce, and expiration |
| Refresh Token | Requests a new access token when allowed by the authorization server | Client sends to the token endpoint; never sent to resource APIs |

Resource servers should not accept an ID Token in place of an Access Token. The ID Token is issued for the OIDC client; the access token is used to access APIs. Token audience and intended usage checks must match the token type.

## 8. Preferred flow: Authorization Code with PKCE

For SPAs, native apps, and many web applications, the appropriate choice is typically Authorization Code Flow with PKCE.

Main steps:

1. Client generates state, nonce if using OIDC, and a random code_verifier.
2. Client computes code_challenge using S256.
3. Client redirects the browser to the authorization endpoint.
4. User logs in and grants consent at the authorization server.
5. Authorization server redirects back to the client with the authorization code and state.
6. Client verifies state.
7. Client sends code along with code_verifier to the token endpoint.
8. Authorization server verifies PKCE and returns tokens.
9. With OIDC, client verifies the ID Token, including issuer, audience, signature, expiration, and nonce.
10. Client uses the access token to call the resource API.

PKCE does not replace state. State protects the redirect flow against CSRF and binds the response to the transaction initiated by the client. With OIDC, nonce binds the ID Token to the authentication request and helps prevent replay in the corresponding context.

Use S256 instead of the plain method. The verifier must be generated with sufficient randomness, used only for the corresponding transaction, and never logged.

## 9. Flows still appropriate in the right context

Not every flow other than Authorization Code is obsolete.

**Client Credentials Grant** fits machine-to-machine communication when a service client accesses an API using its own client identity, with no user logged in. The client authenticates with the authorization server using an appropriate method such as a protected client secret, private_key_jwt, or mTLS depending on the platform.

Client Credentials does not represent user login and is not an OIDC login flow. Do not use it to simulate a user identity if the system requires per-user permissions.

**Device Authorization Grant** fits devices with constrained input or without a full browser, such as TVs or specialized appliances. The device displays a code, and the user uses another device to authenticate and grant consent. This is a distinct standardized flow, not a variant of ROPC.

**Refresh Token** is a grant type at the token endpoint to request a new token while the refresh token remains valid. It is not an initial login flow. Clients must comply with the authorization server's rotation or sender-constrained refresh token policy and handle reuse detection.

## 10. Choosing a replacement flow by client type

| Client type or need | Appropriate choice |
|---|---|
| SPA running in the browser | Authorization Code + PKCE |
| Mobile/native app | Authorization Code + PKCE via external user-agent/browser |
| Web app with backend | Authorization Code; use PKCE for added protection |
| Service calling service, no user | Client Credentials |
| Device with limited keyboard or browser | Device Authorization Grant |
| App needing login and OIDC identity | OIDC Authorization Code + PKCE |
| App currently using Implicit | Plan migration to Authorization Code + PKCE |
| App currently using ROPC | Migrate to an interactive authorization flow at the authorization server |

For native apps, do not embed a fixed client secret in the app installed on devices because users can extract it. Treat native apps as public clients and use PKCE.

For SPAs, any value in the JavaScript bundle or browser storage can be observed by users or scripts on the same origin. Do not place long-lived client secrets in the frontend.

## 11. Describing Authorization Code Flow in Springdoc

Springdoc reads Swagger Core annotations to describe OAuth2 security schemes. Example:

~~~java
@Configuration
@SecurityScheme(
    name = "oauth2AuthCode",
    type = SecuritySchemeType.OAUTH2,
    flows = @OAuthFlows(
        authorizationCode = @OAuthFlow(
            authorizationUrl = "https://id.example.com/oauth2/authorize",
            tokenUrl = "https://id.example.com/oauth2/token",
            scopes = {
                @OAuthScope(
                    name = "openid",
                    description = "Authenticate user with OpenID Connect"
                ),
                @OAuthScope(
                    name = "profile",
                    description = "Read basic profile information"
                ),
                @OAuthScope(
                    name = "products.read",
                    description = "Read product list and details"
                )
            }
        )
    )
)
public class OpenApiSecurityConfiguration {
}
~~~

The Security Scheme above describes the authorization endpoint, token endpoint, and scopes. To make an operation require the scheme:

~~~java
@GetMapping("/api/products")
@Operation(
    summary = "Product list",
    security = @SecurityRequirement(name = "oauth2AuthCode")
)
public List<ProductResponse> findAll() {
    return productService.findAll();
}
~~~

The scheme name in Security Requirement must match the name declared in @SecurityScheme. Scopes declared in the OAuth Flow inform documentation and Swagger UI of the permissions clients can request.

OpenAPI describes flows and scopes, but does not implement an authorization server. URLs must point to the actual identity provider and be properly configured for the environment.

## 12. Describing OpenID Connect Discovery in Springdoc

If the identity provider provides an OpenID Provider Configuration, you can describe it using a Security Scheme of type openIdConnect:

~~~java
@Configuration
@SecurityScheme(
    name = "openId",
    type = SecuritySchemeType.OPENIDCONNECT,
    openIdConnectUrl =
        "https://id.example.com/.well-known/openid-configuration"
)
public class OpenIdConnectConfiguration {
}
~~~

The OpenID Connect Discovery document provides metadata such as issuer, authorization_endpoint, token_endpoint, jwks_uri, userinfo_endpoint, and supported algorithms.

A Security Scheme of type openIdConnect references the discovery URL. It does not automatically verify ID Tokens and does not configure the Spring Security resource server. The application still must configure issuer, audience, and the appropriate JWT verification mechanism.

With OIDC, the client must verify the ID Token per OIDC Core. The resource server must verify the access token according to the format and policy published by the authorization server.

## 13. Configuring Swagger UI to use PKCE

When using Authorization Code Flow for Swagger UI, PKCE can be enabled using the corresponding Swagger UI property. Example application.yml in Springdoc versions supporting this property:

~~~yaml
springdoc:
  swagger-ui:
    oauth:
      client-id: swagger-ui-public-client
      use-pkce-with-authorization-code-grant: true
~~~

This property tells Swagger UI to use PKCE when performing Authorization Code Grant. The authorization server must also support PKCE and have matching client/redirect URI settings.

Do not put a long-lived client secret into Swagger UI when the page is served to browsers or external users. JavaScript code and browser configuration can be inspected. For public clients, use client ID and PKCE; if confidential client authentication is needed, perform it on a backend confidential client.

Property names and configuration mappings can vary across Springdoc/Swagger UI versions. Check the configuration supported by your project's dependencies and verify that actual authorization requests include code_challenge and code_challenge_method=S256.

## 14. How to identify legacy flows separately in documentation

OpenAPI OAuthFlows still has properties for implicit, password, clientCredentials, and authorizationCode to describe existing documentation. The fact that OpenAPI can still represent a flow does not mean that flow is still recommended.

If you must document a legacy system, you should:

- Use a scheme name that clearly indicates legacy, such as legacyPassword.
- Include LEGACY or NOT RECOMMENDED in the description.
- Specify which clients are still allowed to use it and migration conditions.
- Do not make the legacy flow the default example for new clients.
- Publish Authorization Code + PKCE as the replacement integration path.
- Include a support deadline or end-of-life date if decided.

Example describing Password Grant solely to maintain compatibility documentation:

~~~java
@SecurityScheme(
    name = "legacyPassword",
    type = SecuritySchemeType.OAUTH2,
    description =
        "LEGACY: Only for legacy clients undergoing migration. " +
        "Do not use for new integrations; migrate to Authorization Code + PKCE.",
    flows = @OAuthFlows(
        password = @OAuthFlow(
            tokenUrl = "https://id.example.com/oauth2/token",
            scopes = {
                @OAuthScope(
                    name = "products.read",
                    description = "Read products"
                )
            }
        )
    )
)
~~~

This is documentation for an existing system, not a guide to implementing a new ROPC flow. Do not create a new client just as an example to test this flow.

In OpenAPI 3.0 and 3.1, the Security Scheme Object has no common standard property to mark an individual OAuth flow as deprecated. You can use description and vendor extensions such as x-deprecated to convey status to internal tooling, though extensions are not understood by all Swagger UIs or client generators. Do not confuse the Operation Object's deprecated property with a flow's status.

## 15. Marking legacy flows with vendor extensions

If you want documentation validation systems to recognize legacy schemes, you can add vendor extensions using OpenApiCustomizer:

~~~java
@Bean
public OpenApiCustomizer markLegacyOAuthScheme() {
    return openApi -> {
        if (openApi.getComponents() == null ||
            openApi.getComponents().getSecuritySchemes() == null) {
            return;
        }

        var legacy = openApi.getComponents()
            .getSecuritySchemes()
            .get("legacyPassword");

        if (legacy != null) {
            legacy.addExtension("x-deprecated", true);
            legacy.addExtension(
                "x-migration-target",
                "oauth2AuthCode"
            );
            legacy.setDescription(
                "LEGACY: Retained only for existing clients. " +
                "Migrate to Authorization Code + PKCE."
            );
        }
    };
}
~~~

Extensions x-deprecated and x-migration-target are organization-specific metadata, not standard required OpenAPI fields. They can be used in lint rules, reports, or developer portals to filter legacy flows.

If you want to mark an entire operation as no longer recommended, you can use @Operation(deprecated = true) on the corresponding endpoint. This attribute marks the operation, not an individual grant type in the Security Scheme. Mark an operation deprecated only when that endpoint or operation contract itself is being replaced.

## 16. Do not label still-appropriate flows as legacy

Some configurations may look different from Authorization Code yet still have valid purposes:

- Client Credentials is for workload/service identity.
- Device Authorization is for devices with limited input capabilities.
- Refresh Token is used to maintain sessions per authorization server policy.
- Authorization Code + PKCE is the standard choice for user-facing clients.
- OIDC Authorization Code + PKCE is the right choice when clients need identity authentication.

Do not mark Client Credentials as deprecated just because it has no user login page. It solves a different problem: a service authenticating itself to access a resource.

Similarly, Device Authorization is not an outdated version of Password Grant. It lets users complete login on another device without the client collecting passwords.

Proper classification helps clients choose flows based on application nature rather than name or old habits.

## 17. Verifying flows described in OpenAPI

After configuring Springdoc, fetch the OpenAPI JSON:

~~~http
GET /v3/api-docs
~~~

Check the following items:

1. Security Scheme has the right type, oauth2 or openIdConnect.
2. Authorization URL and token URL point to the right identity provider.
3. Scopes have accurate names and descriptions.
4. Operations require the right Security Requirement.
5. Public operations do not inherit security unintentionally.
6. Authorization Code Flow is clearly documented when using PKCE.
7. Swagger UI sends appropriate code_challenge and code_challenge_method.
8. OIDC discovery URL points to metadata of the right issuer.
9. No client secrets or real tokens are included in the document.
10. Legacy flows have distinct descriptions and identifying extensions if the organization uses that convention.
11. Legacy flows are not presented as the default choice for new integrations.
12. Access Token and ID Token are described with their proper purposes.

The OpenAPI document only verifies contract content. To test the actual flow, test against the identity provider in an appropriate environment and verify redirect URI, PKCE, state, nonce, issuer, audience, signature, and token lifetime.

## 18. Migration roadmap from legacy flows

A migration plan can follow these steps:

1. List clients currently using Implicit, ROPC, or Authorization Code without PKCE.
2. Identify whether each client is an SPA, native app, web backend, or service-to-service.
3. Choose the replacement flow appropriate to the client type.
4. Register a new client or update configuration at the identity provider.
5. Configure redirect URI, scopes, and PKCE S256.
6. Update Springdoc Security Scheme and Swagger UI.
7. Test login, consent, refresh, logout, and token revocation.
8. Run in parallel during the transition period if policy allows.
9. Monitor clients still using the legacy flow.
10. Announce the deprecation deadline and remove the legacy flow once no clients depend on it.

Do not turn off a legacy flow immediately when documentation is updated if production clients still depend on it without a migration plan. Conversely, do not let legacy flows remain indefinitely without an owner, deadline, and tracking mechanism.

## 19. Common mistakes when classifying OAuth2/OIDC

| Symptom | Cause to check |
|---|---|
| Swagger UI suggests Implicit for a new SPA | Documentation still keeps the legacy flow as the default option |
| Client sends username/password to token endpoint | Using ROPC instead of an interactive authorization flow |
| Stolen Authorization Code can be exchanged for a token | PKCE not enabled or verifier check misconfigured |
| Using client secret in JavaScript | Confusing a public client with a confidential client |
| API accepts ID Token as access token | Confusing OIDC token purposes |
| Labeling Hybrid as removed from the standard | Confusing "less suitable" with "removed" |
| Client Credentials used for user login | Wrong flow and wrong principal type selected |
| Device flow treated as legacy | Confusing constrained-device flow with ROPC |
| OpenAPI has scheme but backend is unprotected | Only security documentation added without configuring resource server |
| Swagger UI does not send PKCE | PKCE option not enabled or IdP does not support it |
| Legacy flow lacks notes | Scheme lacks description or identifying extension |
| Documentation lists wrong token endpoint | Authorization/token URLs copied from wrong IdP environment |

## 20. Principles for documenting OAuth2/OIDC

When writing Springdoc documentation for OAuth2 and OIDC:

1. Identify Implicit Grant and ROPC separately as flows no longer recommended.
2. Treat Authorization Code without PKCE as a legacy setup needing upgrade, especially for public clients.
3. Do not claim OIDC Hybrid was removed from the standard; describe its status accurately and why it is less often chosen.
4. Prefer Authorization Code + PKCE for applications with users.
5. Use Client Credentials for machine-to-machine communication, not user login.
6. Use Device Authorization for devices with limited interaction.
7. Distinguish access token, ID token, and refresh token.
8. Use description and vendor extensions to mark legacy flows that still must be documented.
9. Do not put client secrets or real tokens in public Swagger UI.
10. Verify the OpenAPI document alongside the actual authorization workflow.

OpenAPI can still describe legacy OAuth flows to preserve compatibility, but documentation must help readers recognize their status and risks. By separating legacy flows, promoting Authorization Code with PKCE as the modern integration path, and clearly distinguishing OAuth2 from OIDC, Springdoc documentation helps clients choose appropriate authentication mechanisms rather than copying outdated configurations.

