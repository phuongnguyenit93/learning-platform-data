# Building a Public Client Using PKCE and a Service Client Using Client Credentials

In an OAuth 2.0 system, browser applications and backend services differ in their ability to keep secrets. A browser application is a **public client**: users can inspect JavaScript code and any configuration delivered to the browser, so it cannot protect a long-lived client secret. A backend service is a **confidential client**: it can keep a secret in a server-side secret store and authenticate with the Authorization Server.

This lab builds both client types with Spring Authorization Server. The public client uses the Authorization Code grant combined with Proof Key for Code Exchange (PKCE) to log users in and request scopes. The service client uses the Client Credentials grant to obtain access tokens for service-to-service backend calls. The two clients are registered separately with only the required grant types and scopes.

This lesson belongs to the **SPRING_SECURITY_OAUTH2_OIDC_AUTHORIZATION_SERVER** module, where we design and operate an Authorization Server covering client management, consent, token issuance, PKCE, refresh tokens, endpoint protection, signing keys, and security flow testing. The **Practical Labs** chapter combines these components into a runnable, testable flow.

## 1. Expected Outcomes and Lab Diagram

Upon completion, you will be able to:

- Register a public client with no client secret, requiring PKCE with the S256 method.
- Complete the Authorization Code flow, verify state at the callback, and exchange the code using the matching code verifier.
- Register a confidential client with client authentication using a client secret via HTTP Basic.
- Issue an access token via Client Credentials and call a protected resource endpoint.
- Verify scopes, redirect URIs, and invalid request cases.

The lab uses three local processes:

| Component | Address | Role |
|---|---|---|
| Spring Authorization Server | http://127.0.0.1:9000 | Login, consent, authorization endpoint, and token endpoint |
| Public client application | http://127.0.0.1:8081 | Runs in the browser, receives the authorization code at the callback |
| Resource Server | http://127.0.0.1:8082 | Exposes the orders API protected by access tokens |

These addresses are for a development machine. In real deployments, use HTTPS, registered hostnames, and exact redirect URIs. The Authorization Server needs working user authentication, a consent page, security filter chains, and signing keys before running the lab. The issuer must be consistent across metadata, JWTs, and Resource Server configuration.

## 2. Registering Both Clients in Spring Authorization Server

Create two RegisteredClients with minimal configuration. The public client only uses Authorization Code, has no secret, and requires PKCE. The service client only uses Client Credentials, authenticating with a client secret via HTTP Basic:

~~~java
@Configuration
public class LabClientConfiguration {

    @Bean
    PasswordEncoder clientPasswordEncoder() {
        return PasswordEncoderFactories.createDelegatingPasswordEncoder();
    }

    @Bean
    RegisteredClientRepository registeredClientRepository(
            PasswordEncoder clientPasswordEncoder) {

        RegisteredClient browserClient = RegisteredClient
                .withId("browser-public-client-id")
                .clientId("browser-public-client")
                .clientAuthenticationMethod(ClientAuthenticationMethod.NONE)
                .authorizationGrantType(AuthorizationGrantType.AUTHORIZATION_CODE)
                .redirectUri("http://127.0.0.1:8081/callback")
                .scope("orders.read")
                .clientSettings(ClientSettings.builder()
                        .requireProofKey(true)
                        .requireAuthorizationConsent(true)
                        .build())
                .tokenSettings(TokenSettings.builder()
                        .accessTokenTimeToLive(Duration.ofMinutes(5))
                        .build())
                .build();

        RegisteredClient serviceClient = RegisteredClient
                .withId("orders-service-client-id")
                .clientId("orders-service")
                .clientSecret(clientPasswordEncoder.encode("local-service-secret"))
                .clientAuthenticationMethod(ClientAuthenticationMethod.CLIENT_SECRET_BASIC)
                .authorizationGrantType(AuthorizationGrantType.CLIENT_CREDENTIALS)
                .scope("orders.read")
                .scope("orders.write")
                .tokenSettings(TokenSettings.builder()
                        .accessTokenTimeToLive(Duration.ofMinutes(5))
                        .build())
                .build();

        return new InMemoryRegisteredClientRepository(browserClient, serviceClient);
    }
}
~~~

The types in the example belong to Spring Security OAuth2 Authorization Server, Spring Security Crypto, and Java Time packages. Add the corresponding imports for the Spring Authorization Server version you are using. If the application already has a PasswordEncoder bean, reuse the existing bean instead of declaring a second one.

The public client uses ClientAuthenticationMethod.NONE. This value means the client does not authenticate with a secret at the token endpoint; PKCE protects the authorization code exchange by binding the code to a verifier held only by the initiating client. The public client must still send client_id so the server identifies the client registration. The redirect URI must match the registered URI exactly.

The service client uses ClientAuthenticationMethod.CLIENT_SECRET_BASIC. The secret is encoded with PasswordEncoder before being stored in RegisteredClient. The secret value in the example is for a local lab only; real environments must obtain secrets from a secret manager or protected environment variables.

The example uses InMemoryRegisteredClientRepository to spin up the lab quickly. When running multiple instances or needing to persist clients across restarts, replace it with JdbcRegisteredClientRepository and a dedicated datasource. Do not register both a production repository and an in-memory repository without clear ordering in the same context.

The Authorization Server also needs an issuer configuration matching the lab address:

~~~java
@Bean
AuthorizationServerSettings authorizationServerSettings() {
    return AuthorizationServerSettings.builder()
            .issuer("http://127.0.0.1:9000")
            .build();
}
~~~

Ensure a signing key/JWKSource is configured to sign JWT access tokens and that the JWKS endpoint only publishes public keys. The Authorization Server's endpoints, filter chains, and login page must be enabled according to the application structure. The public client will be redirected to the login page when the user has no active authentication session; consent is displayed if the client requires consent.

## 3. Running Authorization Code with PKCE for the Public Client

PKCE generates a pair of values for each authorization attempt:

- **code_verifier** is a random string generated by the public client and retained until the code is exchanged.
- **code_challenge** is the SHA-256 transformation of the verifier, sent in the authorization request.

With the S256 method, the Authorization Server stores the challenge alongside the authorization code. When the client exchanges the code, the server recomputes the challenge from the submitted verifier and compares them. Anyone who intercepts only the authorization code cannot exchange it without the corresponding verifier.

In the public client page, generate the verifier, challenge, and state using the Web Crypto API. The following example can run in a browser application served on localhost:

~~~javascript
const randomHex = (size = 32) =>
  Array.from(crypto.getRandomValues(new Uint8Array(size)),
    value => value.toString(16).padStart(2, "0")).join("");

const codeVerifier = randomHex(32);
const state = randomHex(16);

const digest = await crypto.subtle.digest(
  "SHA-256",
  new TextEncoder().encode(codeVerifier)
);

const codeChallenge = btoa(
  String.fromCharCode(...new Uint8Array(digest))
)
  .replaceAll("+", "-")
  .replaceAll("/", "_")
  .replaceAll("=", "");

sessionStorage.setItem("pkce_verifier", codeVerifier);
sessionStorage.setItem("oauth_state", state);

const authorizationUrl = new URL(
  "http://127.0.0.1:9000/oauth2/authorize"
);
authorizationUrl.search = new URLSearchParams({
  response_type: "code",
  client_id: "browser-public-client",
  redirect_uri: "http://127.0.0.1:8081/callback",
  scope: "orders.read",
  state,
  code_challenge: codeChallenge,
  code_challenge_method: "S256"
}).toString();

window.location.assign(authorizationUrl);
~~~

Each time you start an authorization flow, generate a new verifier and state. Store the verifier and state in the tab's session for use at the callback. Do not log the verifier or put it in URLs, analytics, or anywhere it could be sent to third parties. Use HTTPS in production; the Web Crypto API requires a secure context, and browsers treat localhost as a secure context for development.

The Authorization Server will prompt the user to log in if there is no active session. After the user approves the orders.read scope, the server redirects the browser back to the callback with the authorization code and state. The callback must verify state before exchanging the code:

~~~javascript
const callbackUrl = new URL(window.location.href);
const authorizationCode = callbackUrl.searchParams.get("code");
const returnedState = callbackUrl.searchParams.get("state");
const expectedState = sessionStorage.getItem("oauth_state");
const codeVerifier = sessionStorage.getItem("pkce_verifier");

if (!authorizationCode || !returnedState || returnedState !== expectedState) {
  throw new Error("Authorization response state is invalid");
}

if (!codeVerifier) {
  throw new Error("PKCE verifier is missing");
}

const tokenResponse = await fetch(
  "http://127.0.0.1:9000/oauth2/token",
  {
    method: "POST",
    headers: {
      "Content-Type": "application/x-www-form-urlencoded"
    },
    body: new URLSearchParams({
      grant_type: "authorization_code",
      client_id: "browser-public-client",
      code: authorizationCode,
      redirect_uri: "http://127.0.0.1:8081/callback",
      code_verifier: codeVerifier
    })
  }
);

const tokenResult = await tokenResponse.json();
if (!tokenResponse.ok) {
  throw new Error(tokenResult.error || "Token exchange failed");
}

sessionStorage.removeItem("pkce_verifier");
sessionStorage.removeItem("oauth_state");
// Keep the access token in application memory and use it according to the granted scopes.
~~~

The public client does not send an Authorization header containing a client secret. The request sends client_id to identify the client, the authorization code, the redirect URI, and the code verifier. The redirect URI during code exchange must match both the URI sent in the authorization request and the registered URI. An authorization code can only be used once and is short-lived.

Because the browser calls the token endpoint on a different origin, the Authorization Server's CORS configuration must explicitly allowlist the public client's origin, for example http://127.0.0.1:8081, and allow the required methods and headers. CORS only permits the browser to make the request; PKCE and state protect the authorization flow. Do not use CORS as a substitute for PKCE. Do not allow wildcard origins with credentials in a real configuration.

After obtaining the access token, the public client can call the API with the orders.read scope:

~~~javascript
const apiResponse = await fetch(
  "http://127.0.0.1:8082/api/orders",
  {
    headers: {
      Authorization: "Bearer " + tokenResult.access_token
    }
  }
);
~~~

The Resource Server must verify the JWT signature, issuer, expiration, and scopes. With Spring Resource Server, you can configure the issuer URI to match the Authorization Server:

~~~yaml
spring:
  security:
    oauth2:
      resourceserver:
        jwt:
          issuer-uri: http://127.0.0.1:9000
~~~

Example endpoint allowing only the orders.read scope:

~~~java
@RestController
@RequestMapping("/api/orders")
class OrderController {

    @GetMapping
    @PreAuthorize("hasAuthority('SCOPE_orders.read')")
    List<String> listOrders() {
        return List.of("order-1001", "order-1002");
    }
}
~~~

The Resource Server application must enable method security if using @PreAuthorize. You can replace it with authorization rules in SecurityFilterChain if your project manages permissions at the HTTP layer.

## 4. Obtaining an Access Token for the Service Client via Client Credentials

The service client runs in the backend, so it can hold a client secret. With the registered configuration, the client sends a POST to the token endpoint, authenticates via HTTP Basic, and requests the orders.read scope:

~~~bash
curl --user "orders-service:local-service-secret" \
  --header "Content-Type: application/x-www-form-urlencoded" \
  --data-urlencode "grant_type=client_credentials" \
  --data-urlencode "scope=orders.read" \
  http://127.0.0.1:9000/oauth2/token
~~~

A successful response looks like:

~~~json
{
  "access_token": "<signed-access-token>",
  "token_type": "Bearer",
  "expires_in": 300,
  "scope": "orders.read"
}
~~~

The token value in the example has been replaced with a placeholder. Client Credentials does not require a browser, redirect URI, authorization code, state, PKCE, or user consent. The client authenticates its application identity with a client secret and receives only registered permissions.

Use the access token to call the Resource Server:

~~~bash
curl --header "Authorization: Bearer <ACCESS_TOKEN>" \
  http://127.0.0.1:8082/api/orders
~~~

To integrate the service client in a Spring application, you can use OAuth2 Client support to automatically obtain and manage access tokens. Example configuration:

~~~yaml
spring:
  security:
    oauth2:
      client:
        registration:
          orders-service:
            provider: local-authorization-server
            client-id: orders-service
            client-secret: ${ORDERS_SERVICE_CLIENT_SECRET}
            client-authentication-method: client_secret_basic
            authorization-grant-type: client_credentials
            scope:
              - orders.read
        provider:
          local-authorization-server:
            token-uri: http://127.0.0.1:9000/oauth2/token
~~~

The ORDERS_SERVICE_CLIENT_SECRET variable must be supplied by the service runtime environment or a secret manager. Do not bundle secrets into frontend bundles, mobile apps, repositories, or shared images.

You can create an OAuth2AuthorizedClientManager so the service obtains tokens by registration:

~~~java
@Bean
OAuth2AuthorizedClientManager authorizedClientManager(
        ClientRegistrationRepository registrations,
        OAuth2AuthorizedClientService authorizedClientService) {

    OAuth2AuthorizedClientProvider provider =
            OAuth2AuthorizedClientProviderBuilder.builder()
                    .clientCredentials()
                    .build();

    AuthorizedClientServiceOAuth2AuthorizedClientManager manager =
            new AuthorizedClientServiceOAuth2AuthorizedClientManager(
                    registrations, authorizedClientService);
    manager.setAuthorizedClientProvider(provider);
    return manager;
}
~~~

When needing to call the API, create an OAuth2AuthorizeRequest with registration ID orders-service and a principal representing the service. The manager retrieves an access token or requests a new one when the current token is no longer valid under policy. With Client Credentials, the application fetches a new token via client authentication; no refresh token is used.

## 5. Verifying Both Flows in Action

Follow this order to pinpoint whether an error lies in client registration, the authorization flow, or the resource server:

1. Start the Authorization Server on port 9000 and verify the issuer/metadata and JWKS endpoints work.
2. Start the Resource Server on port 8082 and verify the API requires a bearer token.
3. Run the public client on port 8081. Generate a PKCE verifier/challenge, redirect the browser to the authorization endpoint, log in, and approve orders.read.
4. At the callback, verify state and then exchange the authorization code using the code verifier. Verify the response contains an access token and the orders.read scope.
5. Call GET /api/orders with the received access token. The Resource Server must verify the JWT and permit the corresponding scope.
6. Send a Client Credentials request using orders-service. Verify the token endpoint returns an access token with the orders.read scope.
7. Use the service client's access token to call the API. Try requesting orders.write if the API has a corresponding endpoint to verify permissions are restricted by scope.

If the Resource Server does not accept the token, check the issuer, signing key/JWKS, system clock, audience (if the application requires a specific audience), and scope-to-authority mapping. If the token was signed with a new key while the Resource Server still caches old JWKS, check JWKS refresh capability and cache duration.

## 6. Testing Rejection Cases

| Client/Flow | Action | Outcome to Verify |
|---|---|---|
| Public client | Omit code_challenge | Authorization request is rejected because the client requires PKCE |
| Public client | Use wrong code_verifier | Token endpoint rejects code exchange, typically invalid_grant |
| Public client | Send redirect_uri different from registered URI | Authorization or token request is rejected |
| Public client | Callback receives mismatched state | Client halts processing before exchanging the code |
| Public client | Reuse an authorization code | Token endpoint rejects the already consumed code |
| Service client | Send wrong client secret | Client authentication fails with invalid_client |
| Service client | Request an unregistered scope | Token endpoint rejects scope, typically invalid_scope |
| Service client | Call an API requiring a scope absent from the token | Resource Server returns 403 |
| Both | Send an expired token or invalid signature | Resource Server rejects the bearer token |

When testing PKCE, verify the server only accepts the S256 method according to client policy. Do not just check that the code_challenge field is present; prove that a valid verifier is accepted and a wrong verifier is rejected. For state, comparing the callback value is the client's responsibility; the Authorization Server does not replace this check.

## 7. Operational Differences Between the Two Clients

A public client has no secret to protect, so it relies on PKCE, state, exact redirect URIs, short access token lifetimes, and safe token storage in the browser. Avoid storing long-lived access tokens in localStorage if the application model faces risks of same-origin script reads. Protect the application against XSS and only transmit tokens over HTTPS.

A service client must keep its secret on the backend. Use separate secrets for each service, rotate them when needed, and limit scopes to the service's responsibilities. Do not include secrets in logs or exception messages. If the system supports stronger client authentication methods such as private_key_jwt or mutual TLS, they can be applied for environments requiring higher assurance.

Do not use Client Credentials to represent an individual user's actions. If business logic requires user permissions and identity, use the Authorization Code flow or an appropriate delegation mechanism. Conversely, do not force service-to-service calls to open a user login page when only application identity is needed.

## 8. Lab Completion Checklist

- Public client has client authentication method NONE and contains no client secret.
- Public client is only granted the Authorization Code grant and enforces PKCE S256.
- State is randomly generated, stored per session, and compared at the callback.
- Redirect URI matches exactly across client registration, authorization request, and token request.
- Authorization code is exchanged once using the matching code verifier.
- Service client uses CLIENT_SECRET_BASIC and the Client Credentials grant.
- Service client secret is encoded when stored and kept outside frontend code and repositories.
- Both clients only have the necessary scopes; Resource Server checks the corresponding authorities.
- CORS uses an allowlist for browser origins and is not treated as a substitute for PKCE.
- Token endpoint, issuer, signing keys, and Resource Server share matching trusted configuration.
- Negative test cases for PKCE, state, redirect URI, secret, scope, and expired tokens are all verified.

After this lab, you have two OAuth 2.0 integration patterns tailored to two execution environments: a public client protecting authorization codes with PKCE and a service client authenticating with a backend secret. Both receive scope-bounded access tokens verified by the Resource Server before granting data access.
