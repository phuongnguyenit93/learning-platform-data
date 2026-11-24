# Configuring the OAuth Client in Swagger UI

Swagger UI can initiate an OAuth 2.0 flow so users can log in and grant consent before trying out API calls. When using springdoc-openapi, the OAuth flow description is declared in the OpenAPI specification, while client settings for the UI are configured via `springdoc.swagger-ui.oauth` properties. These two parts work together: OpenAPI tells Swagger UI the authorization server, token endpoint, and scopes; the client configuration provides the client ID, redirect URL, and how to execute the authorization flow.

For a UI running in the browser, the appropriate choice for new applications is usually Authorization Code Flow combined with PKCE. Swagger UI is a browser-side application, so it cannot keep a client secret embedded in JavaScript configuration or sent to the browser confidential. Register Swagger UI as a public client, configure the exact redirect URI at the identity provider, and enable PKCE.

## 1. Distinguishing OAuth configuration in OpenAPI from Swagger UI's OAuth client

There are two separate configuration layers:

| Layer | Where Declared | Role |
| --- | --- | --- |
| OAuth Security Scheme | `components.securitySchemes` in OpenAPI | Declares flow, authorization URL, token URL, and scopes supported by the API |
| OAuth Security Requirement | `security` at API or operation level | Indicates which scheme and scopes an operation requires |
| Swagger UI OAuth client | `springdoc.swagger-ui.oauth` or `ui.initOAuth(...)` | Provides client ID, initially selected scopes, and PKCE options for the UI |
| OAuth redirect URL | `springdoc.swagger-ui.oauth2-redirect-url` | Callback address where the authorization server returns the browser after user consent |

For example: OpenAPI may declare `authorizationUrl` as `https://identity.example.com/oauth2/authorize` and `tokenUrl` as `https://identity.example.com/oauth2/token`. Swagger UI uses the client ID registered at the identity provider, redirects the user to the authorization endpoint, and receives the callback at the registered redirect URI.

Swagger UI's `clientId` must match the client registration at the identity provider. It is not the client ID of the API resource server, nor is it the Security Scheme name in OpenAPI. The scheme name is the key operations use to reference it; the client ID is the UI application's identity when requesting tokens.

## 2. Declaring Authorization Code Flow in OpenAPI

Before configuring the UI, describe the OAuth flow accurately in the specification. Example order management API using Authorization Code Flow:

~~~yaml
components:
  securitySchemes:
    ordersOAuth:
      type: oauth2
      flows:
        authorizationCode:
          authorizationUrl: https://identity.example.com/oauth2/authorize
          tokenUrl: https://identity.example.com/oauth2/token
          scopes:
            openid: Authenticate user identity
            profile: Read basic profile information
            orders:read: Read orders
            orders:write: Create and update orders

paths:
  /api/orders:
    get:
      security:
        - ordersOAuth:
            - orders:read
      responses:
        '200':
          description: List of orders
~~~

Important fields:

- `type: oauth2` indicates the scheme uses OAuth 2.0.
- `flows.authorizationCode` selects Authorization Code Flow.
- `authorizationUrl` is the endpoint to initiate login and consent.
- `tokenUrl` is the endpoint to exchange an authorization code for an access token.
- `scopes` lists published API permissions.
- `security` on the operation requires the scopes the client must have to call the operation.

Addresses in the example are placeholders. Replace them with actual endpoints provided by your identity provider. Do not guess URLs if the provider uses dedicated tenants, realms, or paths. OAuth endpoints must use HTTPS in deployment environments.

You can declare the same structure using annotations:

~~~java
import org.springframework.context.annotation.Configuration;

import io.swagger.v3.oas.annotations.enums.SecuritySchemeType;
import io.swagger.v3.oas.annotations.security.OAuthFlow;
import io.swagger.v3.oas.annotations.security.OAuthFlows;
import io.swagger.v3.oas.annotations.security.OAuthScope;
import io.swagger.v3.oas.annotations.security.SecurityScheme;

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
                    name = "orders:read",
                    description = "Read orders"
                ),
                @OAuthScope(
                    name = "orders:write",
                    description = "Create and update orders"
                )
            }
        )
    )
)
public class OAuthApiDocumentationConfiguration {
}
~~~

An operation can require specific scopes:

~~~java
import java.util.List;

import io.swagger.v3.oas.annotations.Operation;
import io.swagger.v3.oas.annotations.security.SecurityRequirement;
import org.springframework.web.bind.annotation.GetMapping;

@GetMapping("/api/orders")
@Operation(
    summary = "List orders",
    security = @SecurityRequirement(
        name = "ordersOAuth",
        scopes = {"orders:read"}
    )
)
public List<OrderResponse> findAll() {
    return orderService.findAll();
}
~~~

The name `ordersOAuth` in the requirement must match the scheme name. Scopes in the requirement must be declared in the corresponding flow and match the scopes issued by the authorization server.

## 3. Registering Swagger UI as an OAuth public client

Swagger UI runs via JavaScript in the user's browser. Any client configuration downloaded by the browser can be inspected via Developer Tools, source maps, Network responses, or page memory. Therefore, treat Swagger UI as a public client.

When creating a client registration at the identity provider, you typically need to declare:

| Registration Field | Value to Specify |
| --- | --- |
| Client type | Public client or SPA/public application per the provider's terminology |
| Grant type | Authorization Code |
| PKCE | Required or enabled for the client |
| Client ID | A public identifier dedicated to Swagger UI |
| Redirect URI | Exact callback URL of Swagger UI |
| Allowed scopes | Scopes the UI needs to request, e.g., `openid`, `profile`, `orders:read` |
| Allowed web origins | Origin of the documentation page if the identity provider requires CORS configuration for browser flows |

Do not register Swagger UI as a confidential client just so you can embed a client secret into application.yml. A client secret placed in server configuration is output by springdoc into the UI configuration and sent to the browser; users can extract that value. Java source code or environment variables do not keep a secret confidential once its value has been emitted to the client.

If organizational policy mandates a confidential client secret, place the OAuth client on the backend via the Backend for Frontend (BFF) pattern or an appropriate server-side component. The browser works with the BFF session; the secret stays on the server and is not sent to Swagger UI.

## 4. Determining the redirect URI

After the user logs in and grants consent, the authorization server redirects the browser back to the application's redirect URI. Swagger UI provides its own callback page; springdoc's default is:

~~~text
/swagger-ui/oauth2-redirect.html
~~~

If documentation is served at:

~~~text
https://docs.example.com/swagger-ui.html
~~~

the public redirect URI typically takes the form:

~~~text
https://docs.example.com/swagger-ui/oauth2-redirect.html
~~~

Register this exact URI at the identity provider. Scheme, hostname, port, context path, and path must match the URL the browser actually uses. Many providers perform exact redirect URI matching and reject URIs that differ by even a trailing slash or a prefix.

You can configure the redirect URL explicitly in application.yml:

~~~yaml
springdoc:
  swagger-ui:
    oauth2-redirect-url: https://docs.example.com/swagger-ui/oauth2-redirect.html
~~~

If the application runs under a `/store` context path, or a reverse proxy publishes documentation under another prefix, the redirect URI must include that public prefix. Do not register an internal URL like `http://localhost:8080/...` for production if external users do not access the application at that address.

## 5. Configuring client ID and PKCE in application.yml

With springdoc-openapi, Swagger UI OAuth options reside under the `springdoc.swagger-ui.oauth` prefix. Example Authorization Code Flow configuration for a public client:

~~~yaml
springdoc:
  swagger-ui:
    oauth2-redirect-url: https://docs.example.com/swagger-ui/oauth2-redirect.html
    oauth:
      client-id: swagger-ui-public
      app-name: Store API Documentation
      scopes:
        - openid
        - profile
        - orders:read
      use-pkce-with-authorization-code-grant: true
    persist-authorization: false
~~~

Meaning:

- `client-id` is the public client ID registered at the identity provider.
- `app-name` is the application name displayed in the authorization dialog.
- `scopes` are pre-selected scopes in the Authorize UI.
- `use-pkce-with-authorization-code-grant` enables PKCE for Authorization Code Flow.
- `persist-authorization: false` preserves the default behavior of not persisting credentials across page reloads or browser restarts.
- `oauth2-redirect-url` is Swagger UI's callback URL.

Swagger UI properties are supported by springdoc as Spring Boot properties. The same configuration can be used in application.properties:

~~~properties
springdoc.swagger-ui.oauth2-redirect-url=https://docs.example.com/swagger-ui/oauth2-redirect.html
springdoc.swagger-ui.oauth.client-id=swagger-ui-public
springdoc.swagger-ui.oauth.app-name=Store API Documentation
springdoc.swagger-ui.oauth.scopes=openid,profile,orders:read
springdoc.swagger-ui.oauth.use-pkce-with-authorization-code-grant=true
springdoc.swagger-ui.persist-authorization=false
~~~

Configuration names in YAML use kebab-case per Spring Boot relaxed binding. If your IDE does not recognize a property or the springdoc version in use differs, check the Configuration Properties of the exact dependency version.

## 6. How does PKCE work?

PKCE (Proof Key for Code Exchange) adds proof that the client must present when exchanging an authorization code for a token. It helps mitigate the risk of another party intercepting an authorization code and using it to obtain tokens.

In Authorization Code Flow with PKCE, the high-level steps are:

1. Swagger UI generates a random string called `code_verifier`.
2. The UI computes `code_challenge` from the verifier, typically using the `S256` method.
3. The browser redirects to the authorization endpoint with `response_type=code`, `client_id`, `redirect_uri`, `state`, scopes, and code challenge.
4. The user logs in and grants consent at the identity provider.
5. The identity provider redirects the browser back to the redirect URI along with the authorization code and state.
6. Swagger UI verifies state, then sends the authorization code along with `code_verifier` to the token endpoint.
7. The identity provider checks whether the verifier matches the original challenge before issuing tokens.

When enabled:

~~~yaml
springdoc:
  swagger-ui:
    oauth:
      use-pkce-with-authorization-code-grant: true
~~~

Swagger UI handles generating and sending PKCE values in supported flows. Do not manually append code challenge or verifier as query parameters. Verify that the authorization server configuration allows PKCE and accepts the `S256` method.

PKCE does not replace a client secret, and a client secret does not replace PKCE. For browser-based Swagger UI, use public client + PKCE instead of trying to hide a secret in the frontend. Swagger UI documentation also notes that the PKCE option does not hide the client secret field.

## 7. Selecting scopes in Swagger UI

Scopes are described in two places:

- In the OpenAPI flow, `scopes` defines the scopes published by the API.
- In Swagger UI configuration, `springdoc.swagger-ui.oauth.scopes` specifies scopes pre-selected in the UI.

Example OpenAPI declaration:

~~~yaml
flows:
  authorizationCode:
    authorizationUrl: https://identity.example.com/oauth2/authorize
    tokenUrl: https://identity.example.com/oauth2/token
    scopes:
      orders:read: Read orders
      orders:write: Create and update orders
~~~

Swagger UI can pre-select:

~~~yaml
springdoc:
  swagger-ui:
    oauth:
      scopes:
        - orders:read
~~~

The read-orders operation requires `orders:read`:

~~~yaml
security:
  - ordersOAuth:
      - orders:read
~~~

Pre-selected scopes do not automatically grant permissions to users. The identity provider decides which scopes are granted based on client registration, consent, user, and its policies. The API resource server must validate access tokens and corresponding permissions when requests arrive.

If the user selects additional scopes in the Authorize dialog, ensure those scopes exist in the OpenAPI flow, client registration, and identity provider policies. Do not request broader scopes than necessary; use least privilege for the operation being tested.

## 8. Configuring scope separator and additional parameters

Swagger UI supports `scopeSeparator` to determine how scopes are joined when sending authorization requests. The default is a space, URL-encoded as `%20`. Usually there is no need to change this value if the identity provider supports standard OAuth formatting.

Additional query parameters can be configured if the provider has specific requirements:

~~~yaml
springdoc:
  swagger-ui:
    oauth:
      scope-separator: " "
      additional-query-string-params:
        audience: https://api.example.com
~~~

`additional-query-string-params` appends parameters to the authorization URL and token URL per Swagger UI's mechanism. Use it only for public parameters required by the identity provider, containing no passwords, client secrets, API keys, or tokens. Avoid using it to bypass standard OAuth configuration or put sensitive data into URLs.

If you need different parameters between the authorization request and token request, or need complex logic, check the capabilities of your identity provider and current Swagger UI. You may need to configure the OAuth client on the backend rather than stuffing all logic into UI configuration.

## 9. When to use HTTP Basic at the token endpoint?

Some authorization servers require clients to authenticate at the token endpoint using HTTP Basic when exchanging an authorization code. Swagger UI provides an option:

~~~yaml
springdoc:
  swagger-ui:
    oauth:
      use-basic-authentication-with-access-code-grant: true
~~~

This option instructs Swagger UI to send client credentials via HTTP Basic in the token request per the supported mechanism. Enable it only when the identity provider's contract requires that authentication method and the client fits the deployment model.

With Swagger UI running directly in the browser, do not use this option to send a production client secret embedded in the UI. If the token endpoint requires a confidential client secret, move the code exchange flow to a backend/BFF. With public client + PKCE, normally no client secret is sent.

Do not confuse client HTTP Basic at the token endpoint with Basic Authentication of an API resource. These serve two different purposes: one authenticates the OAuth client to the authorization server; the other protects requests to the API.

## 10. Do not place a client secret in production

springdoc has the property `springdoc.swagger-ui.oauth.client-secret` and Swagger UI has the `clientSecret` option. Swagger UI documentation explicitly warns against using this property in production because it exposes security credentials; its purpose is solely for development and testing environments.

Do not configure as follows in production:

~~~yaml
springdoc:
  swagger-ui:
    oauth:
      client-id: confidential-client
      client-secret: do-not-put-a-real-secret-here
~~~

Even if the value is read from an environment variable, for example:

~~~yaml
client-secret: <environment variable OAUTH_CLIENT_SECRET>
~~~

the secret is still emitted into the configuration received by the browser. Environment variables only change how the application retrieves the value; they do not protect the secret once sent to the client.

For a Swagger UI public client:

- Use a public client ID.
- Enable Authorization Code + PKCE.
- Do not declare a client secret.
- Restrict redirect URIs and scopes at the identity provider.
- Publish documentation only to appropriate users and protect the docs page if needed.

For confidential clients:

- Store the client secret in a secret manager or server-side vault.
- Perform code-for-token exchange on the backend/BFF.
- Never return secrets or high-privilege tokens into public configuration JavaScript.

## 11. OAuth redirects and CORS in deployment

The OAuth flow runs through the browser, so multiple origins must be checked:

| Component | Example | Role |
| --- | --- | --- |
| Swagger UI | `https://docs.example.com` | Where the user interacts |
| Authorization endpoint | `https://identity.example.com/oauth2/authorize` | Login and consent via browser redirect |
| Token endpoint | `https://identity.example.com/oauth2/token` | Receives authorization code and PKCE verifier to issue tokens |
| API resource server | `https://api.example.com` | Receives test requests from Swagger UI |

The authorization endpoint is normally accessed via browser navigation. The token endpoint is called by Swagger UI from JavaScript, so if it has a different origin from Swagger UI, the identity provider must allow CORS from the documentation origin. The API resource server also needs separate CORS if hosted on a different origin.

These are three distinct access paths. Configuring CORS for the API does not automatically allow the browser to call the token endpoint; identity provider CORS also does not automatically allow Swagger UI to call the API.

If Swagger UI sits behind a reverse proxy, verify that the redirect URI is the public HTTPS address seen by the browser. Do not use internal backend addresses or container ports in the redirect URI registered with the identity provider.

## 12. Standalone Swagger UI configuration with initOAuth

If not using springdoc to serve Swagger UI, you can configure OAuth after initializing Swagger UI:

~~~javascript
const ui = SwaggerUIBundle({
  dom_id: "#swagger-ui",
  url: "https://api.example.com/v3/api-docs",
  oauth2RedirectUrl: "https://docs.example.com/swagger-ui/oauth2-redirect.html"
});

ui.initOAuth({
  clientId: "swagger-ui-public",
  appName: "Store API Documentation",
  scopes: ["openid", "profile", "orders:read"],
  usePkceWithAuthorizationCodeGrant: true
});
~~~

`initOAuth` is a Swagger UI instance method called after creating the instance with `SwaggerUIBundle`. The properties correspond to springdoc configuration:

| Swagger UI `initOAuth` | springdoc property |
| --- | --- |
| `clientId` | `springdoc.swagger-ui.oauth.client-id` |
| `appName` | `springdoc.swagger-ui.oauth.app-name` |
| `scopes` | `springdoc.swagger-ui.oauth.scopes` |
| `scopeSeparator` | `springdoc.swagger-ui.oauth.scope-separator` |
| `usePkceWithAuthorizationCodeGrant` | `springdoc.swagger-ui.oauth.use-pkce-with-authorization-code-grant` |
| `useBasicAuthenticationWithAccessCodeGrant` | `springdoc.swagger-ui.oauth.use-basic-authentication-with-access-code-grant` |

Do not configure conflicting values in both places simultaneously. With springdoc, manage values in application.yml/application.properties for easier profile and environment control. With standalone Swagger UI, configure via initOAuth after initializing the UI.

## 13. Persisting authentication state in the browser

Swagger UI has a `persistAuthorization` option. It defaults to false; when enabled, authentication data is kept across page reloads or browser close/reopen according to Swagger UI's storage mechanism.

In springdoc:

~~~yaml
springdoc:
  swagger-ui:
    persist-authorization: false
~~~

Enable state persistence only when there is a clear need and the environment is suitable. On shared machines, lab computers, or public computers, keeping tokens increases the risk of the next user reusing the authenticated session. Tokens stored in the browser can also be accessed by malicious JavaScript running on the same origin.

After testing, users should click Logout/Authorize to clear credentials from the UI and close the login session per identity provider policy. Clearing Swagger UI state does not necessarily revoke the access token at the authorization server; if revocation is required, use the provider's revoke or logout mechanism.

## 14. Testing workflow for the OAuth client in Swagger UI

Follow this order to pinpoint root causes when authorization fails:

1. Open OpenAPI JSON at `/v3/api-docs` and confirm the scheme has `type: oauth2`, exact `authorizationUrl`, `tokenUrl`, flow, and scopes.
2. Check that operations have Security Requirements referencing the right scheme name and scopes.
3. Check client registration: public client, authorization code grant, PKCE, and redirect URI.
4. Open Swagger UI and inspect the actual callback endpoint used by the UI.
5. Click Authorize, select the right scopes, and confirm the browser redirects to the identity provider.
6. Log in, grant consent, and observe the browser returning to the redirect URI.
7. Confirm token exchange succeeds; if it fails, check the token endpoint request, CORS, redirect URI, code verifier, and client registration.
8. Select an operation to test, click Try it out, and confirm the request sends the access token properly.
9. Call the endpoint with a valid token, a token missing scopes, and no token to verify resource server responses.
10. After testing, clear Authorize state and close the session if needed.

When inspecting Network traffic, never copy or share access tokens, refresh tokens, authorization codes, cookies, or client secrets into public tickets/logs. Mask sensitive values and retain only header names, URLs, status codes, and non-secret error details.

## 15. Common errors and resolutions

| Symptom | Possible Cause | Resolution |
| --- | --- | --- |
| Authorize button lacks OAuth scheme | OpenAPI missing Security Scheme or wrong type/flows | Check components.securitySchemes in /v3/api-docs |
| Authorization server returns invalid_client | Wrong Client ID, unsuitable client type, or server expects different client auth | Cross-check client registration; use public client for Swagger UI and do not embed secrets |
| Reports redirect_uri_mismatch | Sent Redirect URI differs from registered URI | Check oauth2-redirect-url, context path, HTTPS, and public URL |
| Login succeeds but token exchange fails with CORS error | Token endpoint does not allow Swagger UI origin | Configure CORS on the identity provider for the docs origin |
| Reports invalid_grant on code exchange | Code expired/already used, redirect URI or PKCE verifier mismatch | Retry a fresh flow, check redirect URI, and enable PKCE consistently |
| Scope missing from dialog | Scope not declared in OpenAPI or scopes config | Synchronize scopes across flow, UI, client registration, and authorization server |
| Token received but API returns 403 | Token lacks scope/role or API enforces different permission | Check token claims and resource server authorization policy |
| Swagger UI sends request without Bearer token | Operation does not reference right Security Requirement or scheme name mismatches | Check operation security and component name |
| Callback returns 404 | Redirect URI has wrong path or proxy does not serve callback file | Check /swagger-ui/oauth2-redirect.html on public URL |
| PKCE is not sent | Option not enabled or flow is not Authorization Code | Enable use-pkce-with-authorization-code-grant and check flow |
| Secret appears in browser | client-secret configured in Swagger UI | Remove secret from client config; use public client + PKCE or BFF |
| Another user can still use old token | persistAuthorization enabled or IdP session still active | Disable persistence on shared machines, clear authorization, and logout/revoke per policy |

## 16. Implementation checklist

- [ ] OpenAPI accurately declares Authorization Code Flow, authorization URL, token URL, and scopes.
- [ ] Operations reference the right Security Scheme and require appropriate scopes.
- [ ] Swagger UI is registered as a public client when running directly in the browser.
- [ ] Client registration enables Authorization Code and PKCE with method S256.
- [ ] Client ID matches registration.
- [ ] Public redirect URI matches the registered URI exactly.
- [ ] Configured use-pkce-with-authorization-code-grant: true.
- [ ] No client secret configured in production Swagger UI.
- [ ] CORS for token endpoint and API configured for required origins.
- [ ] Scopes restricted according to least privilege.
- [ ] persist-authorization evaluated based on environment and devices.
- [ ] Tested authorization, token exchange, Try it out, and API access permissions.
- [ ] Logs and test screenshots contain no tokens or credentials.

## 17. Official references

- [Swagger UI — OAuth 2.0 Configuration](https://swagger.io/docs/open-source-tools/swagger-ui/usage/oauth2/) — initOAuth, client ID, client secret, scopes, PKCE, and HTTP Basic at the token endpoint.
- [Swagger UI — Configuration](https://swagger.io/docs/open-source-tools/swagger-ui/usage/configuration/) — oauth2RedirectUrl, Swagger UI configuration, and instance methods.
- [springdoc-openapi Configuration Properties](https://springdoc.org/properties.html) — properties springdoc.swagger-ui.oauth.*, oauth2RedirectUrl, persistAuthorization, and Swagger UI config in Spring Boot.
- [springdoc-openapi Features v2](https://springdoc.org/v2/features.html) — declaring Swagger UI properties via Spring Boot properties.
- [RFC 7636 — Proof Key for Code Exchange by OAuth Public Clients](https://www.rfc-editor.org/rfc/rfc7636.html) — PKCE mechanism, code verifier, code challenge, and S256 method.
- [RFC 9700 — Best Current Practice for OAuth 2.0 Security](https://www.rfc-editor.org/rfc/rfc9700.html) — current OAuth 2.0 security recommendations.

To configure the OAuth client in Swagger UI, synchronize three parts: flow and scopes in OpenAPI, client registration and redirect URI at the identity provider, and client ID and PKCE in the UI configuration. With browser-based Swagger UI, public client + Authorization Code + PKCE enables testing APIs without exposing a production client secret to the frontend.
