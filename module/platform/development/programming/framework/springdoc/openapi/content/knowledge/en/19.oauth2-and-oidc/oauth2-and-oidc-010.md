# Limitations of Storing a Client Secret in Browser-Based Applications

A browser-based application cannot keep a value secret if JavaScript must read it to perform authentication. Frontend source code, bundled configuration, build-time environment variables, and data sent to the browser can all be inspected by users. Therefore, an SPA or pure JavaScript application running in the browser is considered a **public client** in OAuth 2.0; the client cannot securely prove that it holds a private client secret.

When describing OAuth2/OIDC with springdoc-openapi, this limitation must be reflected accurately in the security scheme and Swagger UI configuration. Browser applications should use Authorization Code with PKCE. If the system requires a confidential client or needs to keep access tokens/refresh tokens on the server side, a backend-for-frontend (BFF) can be placed as an intermediary. Client secrets must only be stored and used in a controlled backend environment.

## 1. What is a client secret used for?

In OAuth 2.0, a client is an application requesting access to resources. The authorization server can issue a client identifier (client_id) and, for confidential clients, client authentication credentials such as a client_secret.

These two values serve different purposes:

| Value | Role | Can be public? |
|---|---|---|
| client_id | Identifier of the application registered with the authorization server | Usually yes; not a password |
| client_secret | Proof authenticating the client to the authorization server | No; must be kept confidential |

client_id typically appears in authorization requests so the authorization server knows which application is requesting login. It does not prove that the request sender is a trusted application.

client_secret is a client credential. With a confidential client, the backend can use it when calling the token endpoint, for instance via HTTP Basic or a client authentication method supported by the authorization server. If the secret is exposed, anyone can impersonate the client in flows where that secret is accepted.

Do not confuse client secret with access token, refresh token, ID token, or API key. They are different types of credentials with different intended audiences and lifecycles.

## 2. Why can't the browser keep a client secret?

The browser must receive the JavaScript code and data needed to run the application. Users control their own browser environment, so they can inspect everything the application downloads and sends.

A client secret embedded in an application can be found via:

- JavaScript bundles after build, even when code is minified.
- Source maps published alongside the frontend.
- Environment variables substituted into code during the build process.
- Request bodies, headers, or network traces when the application sends the secret.
- Developer Tools, debuggers, browser extensions, or user-controlled proxies.
- Runtime memory when JavaScript reads the secret to construct requests.
- Frontend logs, error reports, HAR files, or telemetry recording request data.

Minifying, obfuscating, encrypting strings in the bundle, or renaming variables does not keep a secret confidential. If the application has to decrypt or use the value in the browser, anyone controlling the browser can observe that operation.

### 2.1. Frontend environment variables are not a secret store

On the backend, environment variables can pass sensitive configuration into the server process. On the frontend, variables used at build time usually become part of the static files sent to the browser.

Examples of common conventions:

| Frontend Tool | Common Public Variable Prefix |
|---|---|
| Vite | VITE_ |
| Create React App | REACT_APP_ |
| Next.js client bundle | NEXT_PUBLIC_ |
| Nuxt public runtime config | runtimeConfig.public |

Exact prefix names depend on the tool and version, yet the principle stays the same: any value placed into the client bundle must be treated as public.

Insecure example:

~~~javascript
const clientSecret = import.meta.env.VITE_OAUTH_CLIENT_SECRET;

await fetch("https://id.example.com/oauth2/token", {
  method: "POST",
  headers: {
    "Content-Type": "application/x-www-form-urlencoded"
  },
  body: new URLSearchParams({
    grant_type: "client_credentials",
    client_id: import.meta.env.VITE_OAUTH_CLIENT_ID,
    client_secret: clientSecret
  })
});
~~~

The secret in the example above gets bundled or appears in requests from the browser. Naming the variable SECRET, storing it in a .env.production file, or hiding it from the UI does not change this risk.

## 3. Public client and confidential client

OAuth 2.0 distinguishes clients based on their ability to keep credentials confidential in the deployment environment.

| Characteristic | Public client | Confidential client |
|---|---|---|
| Typical environment | SPA, mobile app, desktop app distributed to users | Web backend, BFF, service running on controlled servers |
| Can keep a client secret? | No | Yes, when stored and operated properly |
| Common mechanism | Authorization Code + PKCE | Authorization Code, Client Credentials, or appropriate flow |
| Where credentials live | Embed no secret; may use public client ID | Secret manager, vault, or protected server configuration |
| Level of control | Users control the runtime and can inspect code | Operators control servers and access permissions |

A web application with a frontend and backend must be distinguished by component. The JavaScript frontend is a public client. The backend can be a confidential client if credentials stay strictly on the server and the server can authenticate to the authorization server.

Registering an application as a confidential client does not make the frontend safe to hold a secret. The client type must reflect where credentials are actually used.

## 4. Do not use Client Credentials directly from the browser

Client Credentials is for applications calling APIs using the application's own identity, without an end user involved. This flow normally requires the client to authenticate to the token endpoint using a client secret, private key, or another client authentication method.

The browser cannot keep those credentials safe. If an SPA calls the token endpoint with a client secret, anyone authorized to run the app can extract the secret and use it outside the application.

Insecure flow:

~~~text
Browser SPA
   |
   | client_id + client_secret
   v
Authorization Server
   |
   | access token
   v
Resource API
~~~

Appropriate flow for service-to-service:

~~~text
Browser                 Backend / BFF             Authorization Server
   |                           |                            |
   |-- request user action --->|                            |
   |                           |-- client authentication -->|
   |                           |<-- access token -----------|
   |                           |                            |
   |                           |-- call protected API -----> Resource API
   |<-- application response --|                            |
~~~

The backend holds the client credentials, requests an access token, and calls the resource API. The browser only communicates with the backend via a login session or application-designed mechanism.

## 5. Authorization Code with PKCE for browser applications

For an SPA that needs to log users in and call APIs directly from the browser, the standard choice is Authorization Code with Proof Key for Code Exchange (PKCE). Public clients do not need a client secret in this flow.

PKCE generates a pair of values for each authorization request:

- code_verifier: high-entropy random string temporarily kept by the client.
- code_challenge: value derived from the verifier, usually using the S256 method.

The client sends the code challenge in the authorization request. When exchanging the authorization code for a token, the client sends the code verifier. The authorization server verifies whether the verifier matches the original challenge. Another party that only steals the authorization code will lack the verifier to exchange it for a token.

High-level flow:

~~~text
Browser SPA                 Authorization Server             Resource API
    |                                |                              |
    |-- authorize + code_challenge ->|                              |
    |<-- login / consent ------------|                              |
    |<-- authorization code ---------|                              |
    |                                |                              |
    |-- code + code_verifier ------->|                              |
    |<-- access token ---------------|                              |
    |                                                               |
    |---------------- access token ------------------------------->|
    |<--------------- protected resource --------------------------|
~~~

Implementation requirements:

1. Register the client as a public client.
2. Use Authorization Code flow and enable PKCE with S256.
3. Register exact redirect URIs, avoiding broad wildcards.
4. Generate code_verifier using a cryptographically secure random number generator.
5. Use state to bind the authorization response to the initiated request.
6. With OIDC, use nonce and verify the ID token per OIDC rules.
7. Never send a client secret from the browser.
8. Send the access token to the resource API with the right audience and scopes.

PKCE protects the authorization code exchange process. It does not stop malicious code running in the page from stealing tokens after login, does not replace XSS protection, and does not turn an SPA into a confidential client.

## 6. Configuring OAuth2 in OpenAPI for a public client

OpenAPI describes the authorization flows and scopes supported by the API. For browser applications, you can describe Authorization Code flow without declaring a client secret.

Annotation example in springdoc:

~~~java
import io.swagger.v3.oas.annotations.enums.SecuritySchemeType;
import io.swagger.v3.oas.annotations.security.OAuthFlow;
import io.swagger.v3.oas.annotations.security.OAuthFlows;
import io.swagger.v3.oas.annotations.security.OAuthScope;
import io.swagger.v3.oas.annotations.security.SecurityScheme;
import org.springframework.context.annotation.Configuration;

@Configuration
@SecurityScheme(
    name = "browserOAuth",
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
                    description = "Create orders."
                )
            }
        )
    )
)
public class BrowserOAuthConfiguration {
}
~~~

The scheme describes flow, URLs, and scopes. OpenAPI does not need and should not contain a client secret. client_id is a public value Swagger UI may need to initiate the authorization flow; secrets must not be placed in documentation.

If the API supports OIDC, you can additionally describe an openIdConnect scheme pointing to the discovery document. Declaring an OIDC scheme does not make the ID token a token for calling APIs; the resource server still must receive and verify an access token.

## 7. Configuring Swagger UI securely with PKCE

Swagger UI runs in the browser, so it is also a public client. If integrators need to use the Authorize button to test APIs via Authorization Code flow, configure the client ID and enable PKCE:

~~~yaml
springdoc:
  swagger-ui:
    oauth:
      client-id: store-swagger-ui
      use-pkce-with-authorization-code-grant: true
~~~

store-swagger-ui is the public client ID registered with the authorization server. Swagger UI's redirect URI must be registered accurately. Depending on context path and deployment config, the callback usually sits at swagger-ui/oauth2-redirect.html.

Do not add a client-secret property to Swagger UI configuration for browser applications. Also do not invoke Swagger UI's OAuth initializer with a clientSecret containing a real credential. Configuration is downloaded to the browser and can be read by users.

Insecure configuration example:

~~~yaml
springdoc:
  swagger-ui:
    oauth:
      client-id: store-swagger-ui
      client-secret: do-not-put-a-real-secret-here
~~~

Even if the value is substituted from a server environment variable at startup, if Springdoc outputs it into the JavaScript config sent to the browser, the secret is still exposed. There is no workaround via renaming properties or encrypting the secret in the config file.

For Swagger UI, verify:

- The client is registered as a public client if running directly in the browser.
- Authorization Code flow is properly declared.
- PKCE is enabled and the authorization server accepts S256.
- Redirect URI matches the registered URI exactly.
- Only the client ID and necessary scopes appear in the browser.
- No client secret appears in configuration, source maps, bundles, or network requests.

## 8. When should you use a Backend-for-Frontend (BFF)?

A BFF is a backend designed specifically to serve a frontend. The browser sends requests to the BFF; the BFF manages the OAuth session and performs calls to the authorization server or resource APIs server-side.

Architecture:

~~~text
Browser
   |
   | session cookie
   v
BFF (confidential client)
   |             \
   |              \ client authentication
   |               v
   |        Authorization Server
   |               |
   |<-------------- access / refresh token (server-side)
   |
   | bearer access token
   v
Resource API
~~~

A BFF is useful when:

- You do not want access tokens or refresh tokens to appear in JavaScript.
- Confidential client authentication is required.
- You want centralized management of refresh tokens, sessions, logout, and token revocation.
- You want the browser to hold only a login session cookie.
- You want to restrict which APIs the frontend can call through a backend layer.

In the BFF model, the session cookie should typically have appropriate HttpOnly, Secure, and SameSite attributes. Because the browser sends cookies automatically, the BFF needs CSRF defenses, such as checking Origin/Referer, using CSRF tokens where needed, and restricting state-changing methods.

A BFF reduces token exposure to JavaScript, but does not eliminate all XSS risks. Malicious scripts can still issue requests on behalf of the user within an open session. Combine with Content Security Policy, output encoding, dependency controls, and session protection.

## 9. Storing client secrets on the backend

If the backend is a confidential client, the secret must be loaded from a protected configuration source at runtime. You can use the platform's secret manager, a vault, or an equivalent credential management mechanism.

Server-side Spring Boot configuration example:

~~~yaml
spring:
  security:
    oauth2:
      client:
        registration:
          partner:
            client-id: store-bff
            client-secret: ${OAUTH_PARTNER_CLIENT_SECRET}
            authorization-grant-type: authorization_code
            redirect-uri: "{baseUrl}/login/oauth2/code/{registrationId}"
            scope:
              - openid
              - profile
              - products.read
        provider:
          partner:
            issuer-uri: https://id.example.com
~~~

The OAUTH_PARTNER_CLIENT_SECRET placeholder is resolved inside the backend process. Do not place configuration files containing secrets in the static frontend directory, do not copy those values into bundles, and do not expose an endpoint returning full configuration to the browser.

In production:

- Grant secret read permissions only to workloads that need them.
- Never commit secrets to Git, Docker images, or frontend artifacts.
- Never write secrets to logs, exceptions, traces, or publicly accessible Actuator endpoints.
- Maintain a credential rotation and revocation process.
- Use separate credentials per environment and per application.
- Restrict client permissions to required scopes and policies.

Backend environment variables can be one way to inject secrets, provided process read permissions, crash dumps, and operational systems are protected. Dedicated secret managers are usually more suitable for production systems.

## 10. Tokens in the browser: choosing a storage model

Client secrets are not the only thing needing protection. Access tokens and refresh tokens are also credentials that can be abused if stolen.

| Location | Readable by JavaScript? | Primary Risk |
|---|---|---|
| In-memory application variable | Yes | XSS can read or use the token while the app is running |
| localStorage | Yes | Token persists across sessions and same-origin scripts can read it |
| sessionStorage | Yes | Same-origin scripts can read it; data typically persists for the tab session |
| IndexedDB | Yes | Same-origin scripts can read stored data |
| HttpOnly Cookie | Not directly readable by JavaScript | Browser sends cookie automatically; requires CSRF handling and proper cookie flags |
| Server-side / BFF token store | Browser has no direct access | Must protect the backend, sessions, and communication channels |

For SPAs calling APIs directly, shorten token lifetimes in the browser and prefer keeping access tokens in memory when architecture allows. Avoid storing long-lived refresh tokens in localStorage. If the authorization server supports refresh tokens for public clients, apply rotation or sender-constrained token policies and detect reuse of rotated tokens.

No browser-side storage makes a token completely safe against XSS executing in the application's origin. The goal is to reduce theft opportunities, shorten abuse windows, and limit token permissions.

## 11. Protecting the application from XSS and CSRF

XSS allows malicious code to run in the application's origin. Once present, scripts can read JavaScript-accessible data, call APIs on the user's behalf, and manipulate the UI. PKCE cannot prevent this type of attack after a session has been established.

Key measures:

- Escape or encode untrusted data appropriately for the display context.
- Avoid passing untrusted strings into innerHTML or code-execution APIs.
- Enforce a strict Content Security Policy, avoiding unsafe-inline and unsafe-eval when possible.
- Restrict third-party scripts and audit frontend dependencies.
- Consider Trusted Types where supported by browser platforms and applications.
- Never store secrets or tokens in frontend logs, URLs, or query parameters.
- Use HTTPS for the entire login flow and all APIs.

CSRF primarily needs consideration when the browser automatically attaches credentials, especially session cookies. A BFF should validate request origins and use appropriate CSRF mechanisms. SameSite configuration helps mitigate risk, yet should not be treated as the sole defense for every deployment model.

## 12. Comparing direct SPA vs BFF

Either architecture can be valid depending on requirements:

| Criterion | SPA + Authorization Code + PKCE | BFF + confidential client |
|---|---|---|
| Client secret | Not used | Kept on backend |
| Where access token is received | Browser | Backend |
| Browser calls resource API | Directly, with access token | Typically calls BFF |
| Refresh token management | Must be carefully designed for public clients | Can be retained server-side |
| CSRF | Depends on credentials and how requests are sent | Needs attention because session cookies are sent automatically |
| Infrastructure | Fewer backend components | Requires operating BFF and sessions |
| Best suited for | Standalone SPAs, APIs for public clients | Apps needing server-side token/credential retention |

Choose direct SPA when a public client with PKCE works and browser-managed tokens are acceptable. Choose BFF when a confidential client is required, tokens must stay out of JavaScript, or session and token management needs centralization.

## 13. Describing BFF and public clients in the OpenAPI contract

OpenAPI should reflect the credentials that clients actually use to call the API.

For an SPA calling the resource API directly, you can describe OAuth2 Authorization Code:

~~~yaml
components:
  securitySchemes:
    browserOAuth:
      type: oauth2
      flows:
        authorizationCode:
          authorizationUrl: https://id.example.com/oauth2/authorize
          tokenUrl: https://id.example.com/oauth2/token
          scopes:
            products.read: Read products.
paths:
  /api/v1/products:
    get:
      security:
        - browserOAuth:
            - products.read
      responses:
        '200':
          description: Product list.
~~~

Do not add client_secret to components, securitySchemes, extensions, or request examples. OpenAPI describes flows and scopes; client-specific credentials are managed per client registration environment.

For a BFF using session cookies, browser-facing documentation can describe cookie/session authentication via an appropriate security scheme or document the session mechanism at the API level. Confidential client authentication between the BFF and authorization server is server-to-server communication, typically not a credential the browser needs to know.

## 14. Configurations to avoid in springdoc and Swagger UI

The following configurations risk exposing credentials if sent to the browser:

~~~yaml
springdoc:
  swagger-ui:
    oauth:
      client-id: store-swagger-ui
      client-secret: do-not-put-a-real-secret-here
~~~

Do not use client-secret in Swagger UI when the UI runs in the browser. Similarly, avoid the following practices:

- Injecting a secret into @Value and assigning it to Swagger UI's JavaScript config.
- Placing secrets in index.html, application.js, or frontend JSON files.
- Using a customizer to add secrets to OpenAPI extensions or descriptions.
- Returning secrets from the backend via a frontend config endpoint.
- Placing secrets in VITE_, REACT_APP_, NEXT_PUBLIC_, or equivalent variables.
- Recording secrets in curl examples, public Postman collections, or HAR files.

If Swagger UI needs login to test APIs, register a dedicated public client for Swagger UI, enable Authorization Code + PKCE, and restrict the redirect URI. If a confidential client is required, place the token acquisition flow in a controlled backend.

## 15. CORS does not make a client secret safe

CORS governs whether the browser allows JavaScript to read responses from another origin. It does not turn credentials embedded in the frontend into secrets.

Even if the authorization server allows only one specific origin via CORS, users can still inspect the bundle and read the secret. They can also send requests from a non-browser tool once they have extracted the credential.

CORS should be configured to permit the exact origins, methods, and headers the application needs. Do not use CORS as a client authentication mechanism or a means of protecting client secrets.

## 16. What if a secret has already been put into the frontend?

Once a client secret has appeared in a bundle, public repository, source map, or browser request, treat that credential as compromised.

Remediation steps:

1. Revoke or rotate the secret at the authorization server.
2. Issue a new credential to a valid backend or confidential client.
3. Remove the secret from frontend source and build configuration.
4. Check bundles, source maps, artifacts, CDN caches, logs, and monitoring systems to determine leak scope.
5. Inspect authorization server logs for abnormal activity if any.
6. Audit Git history and pipelines to prevent the secret from reappearing.
7. Update release processes and automated secret scanning.

Removing the secret from a new commit does not invalidate the old credential. Revoke or rotate at the credential issuer first, then clean up copies and archive history according to organizational policy.

## 17. Configuration examples for both models

### 17.1. SPA public client using PKCE

Register the client on the authorization server:

~~~text
Client type: Public
Grant: Authorization Code
PKCE: Required (S256)
Client ID: store-spa
Client secret: Not issued
Redirect URI: https://app.example.com/auth/callback
Allowed scopes: openid, profile, products.read
~~~

Frontend uses only the client ID:

~~~javascript
const oauthConfig = {
  clientId: "store-spa",
  authorizationUrl: "https://id.example.com/oauth2/authorize",
  tokenUrl: "https://id.example.com/oauth2/token",
  redirectUri: "https://app.example.com/auth/callback",
  scopes: ["openid", "profile", "products.read"]
};
~~~

Browser-side OIDC/OAuth2 libraries should generate verifier, challenge, state, and nonce per specification. Do not hand-roll randomness with Math.random() or handle tokens manually when a trusted library provides standard flows.

### 17.2. BFF confidential client

Register the backend application:

~~~text
Client type: Confidential
Grant: Authorization Code
Client ID: store-bff
Client secret: Stored in server-side secret manager
Redirect URI: https://app.example.com/login/oauth2/code/partner
~~~

Backend receives the secret from runtime configuration:

~~~yaml
app:
  oauth:
    client-id: store-bff
    client-secret: ${OAUTH_BFF_CLIENT_SECRET}
~~~

The frontend receives only the session cookie issued by the BFF. Do not return client-secret, access tokens, or refresh tokens to JavaScript. Cookies must be configured with HttpOnly, Secure, SameSite, and lifetimes suited to the session model.

The URLs and client IDs in both examples are illustrative. In deployment, register the exact redirect URIs, origins, and scopes per the actual authorization server.

## 18. Checking OpenAPI docs and frontend configuration

After starting the application, inspect the documentation generated by springdoc:

~~~bash
curl -s http://localhost:8080/v3/api-docs
~~~

Check:

- Security scheme uses type oauth2 and flow authorizationCode for public browser clients.
- Authorization URL, token URL, and scopes match authorization server configuration.
- No client secret appears in OpenAPI JSON/YAML, extensions, or descriptions.
- Security requirements attach the right scopes to each operation.
- Swagger UI has only a public client ID and PKCE enabled.
- Swagger UI's redirect URI is registered accurately.
- No secret appears in static bundles, source maps, or browser requests.

Inspect the built frontend bundle by searching for known sensitive variable names or values. String searching is only one check layer; also inspect source maps, downloaded runtime config, and requests in the Network panel.

Check the backend:

- Client secret is read only by authorized backend processes.
- Secret does not appear in logs, exceptions, or configuration endpoints.
- Tokens are stored and handled per BFF policy.
- Session cookies have appropriate protective attributes.
- CSRF is handled if the browser sends cookies automatically.
- Credentials have rotation and revocation procedures.

## 19. Common mistakes

| Mistake | Consequence | Fix |
|---|---|---|
| Embedding client secret in JavaScript | Users can extract it and impersonate the client | Use a public client with PKCE or a BFF |
| Putting secret in frontend environment variables | Value gets packaged into the client bundle | Place secrets only in backend environments |
| Using Client Credentials from an SPA | Client authentication credentials are exposed | Move this flow to a backend/service |
| Assuming minify or obfuscate protects secrets | Secret can still be found at runtime | Never distribute secrets to the browser |
| Enabling PKCE while still sending client secret | Still exposes credentials unnecessarily | Register a public client and remove the secret |
| Storing long-lived refresh tokens in localStorage | XSS can steal tokens and maintain access | Use a BFF or appropriate public-client token policies |
| Relying on CORS to protect secrets | CORS does not stop users from reading bundles | Protect credentials via server-side architecture |
| Using ID token to call resource APIs | Token may have wrong audience and purpose | Use access tokens intended for APIs |
| Only deleting secret from Git without rotating | Old credentials can still be abused | Revoke/rotate first, then clean copies |
| Configuring client secret for Swagger UI | Secret is sent to the browser | Use client ID + PKCE for Swagger UI |

## 20. Takeaways

- Browser SPAs are public clients because users can inspect code and runtime state.
- client_id is normally public; client_secret must be kept in a controlled server environment.
- Frontend environment variables and .env files used at build time are not secret stores.
- Never use Client Credentials directly from the browser.
- Authorization Code + PKCE is the right choice for public browser clients.
- PKCE protects authorization code exchange; it does not replace XSS prevention.
- A BFF can keep client secrets, access tokens, and refresh tokens server-side.
- HttpOnly, Secure, SameSite cookies must be paired with proper session and CSRF design.
- Swagger UI runs in the browser, so it must not be configured with a client secret.
- CORS, minification, and obfuscation do not turn a public secret into a confidential one.
- If a secret has been exposed, revoke or rotate the credential; deleting it from bundles or Git is not enough.
- OpenAPI describes flows and scopes, while the backend/authorization server enforces authentication and authorization.

When designing OAuth2/OIDC for browser-based applications, treat the frontend as a public client and do not give it a client secret. Use Authorization Code with PKCE when the browser calls APIs directly; use a BFF when a confidential client is required or tokens must remain on the server. Springdoc-openapi and Swagger UI documentation must accurately reflect that architecture without publishing sensitive credentials.
