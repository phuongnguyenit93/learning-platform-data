# redirect_uri Mismatch and post_logout_redirect_uri Errors

Two common URI errors when integrating OAuth 2.0 and OpenID Connect are the Authorization Server rejecting the callback after the user logs in, or the user logging out without being redirected back to the application. Both usually stem from the URI sent in the request not matching the URI registered for the client. However, the two parameters serve different stages and are validated against two separate registered lists.

In the **SPRING_SECURITY_OAUTH2_OIDC_AUTHORIZATION_SERVER** module, we manage clients, consent, authorization codes, tokens, and OIDC endpoints. This lesson belongs to the **Troubleshooting** chapter and focuses on diagnosing the root cause of **redirect_uri mismatch** in the Authorization Code flow and **post_logout_redirect_uri** in RP-Initiated Logout. The goal is to identify which URI is being sent, which URI is registered, and which component introduces the discrepancy.

## 1. Distinguishing the Two URIs and When They Are Checked

**redirect_uri** is the callback the Authorization Server uses to return the authorization response to the client after the user completes authorization. It appears in the authorization request and is usually sent again when the client exchanges the authorization code at the token endpoint. The authorization code is bound to the client and the redirect URI used in the flow.

**post_logout_redirect_uri** is the address to which the OpenID Provider (OP) may redirect the browser after completing RP-Initiated Logout. This URI is sent to the OIDC logout endpoint along with session/client identification info, typically id_token_hint and optionally state. The URI must be in the registered post-logout redirect URI list for the client.

| Parameter | Flow | Validating Endpoint | Registered List |
|---|---|---|---|
| **redirect_uri** | OAuth 2.0 Authorization Code | Authorization endpoint and token endpoint | RegisteredClient redirect URIs |
| **post_logout_redirect_uri** | OpenID Connect RP-Initiated Logout | OIDC logout endpoint | RegisteredClient post-logout redirect URIs |

These two lists are independent. Registering a login callback does not automatically allow using the same address after logout. Similarly, adding a URI to the post-logout list will not fix a callback error when exchanging an authorization code.

Authorization Code flow:

~~~mermaid
sequenceDiagram
    participant B as Browser / Client
    participant AS as Authorization Server
    B->>AS: /oauth2/authorize with redirect_uri
    AS->>AS: Match URI against registered client
    AS-->>B: Redirect to callback with code and state
    B->>AS: /oauth2/token with code and redirect_uri
    AS->>AS: Validate code, client, and redirect_uri
    AS-->>B: Access token (and other tokens if issued)
~~~

RP-Initiated Logout flow:

~~~mermaid
sequenceDiagram
    participant B as Browser
    participant RP as Relying Party
    participant OP as OpenID Provider
    B->>RP: Log out of application
    RP->>OP: end_session_endpoint with id_token_hint and post_logout_redirect_uri
    OP->>OP: Validate session and registered URI
    OP-->>B: Redirect to post-logout URI with state if valid
~~~

## 2. Identifying the Exact Registered URI

In Spring Authorization Server, login callbacks and post-logout callbacks are declared separately on RegisteredClient. The following example registers a local web application with Authorization Code and OIDC:

~~~java
RegisteredClient webClient = RegisteredClient
        .withId("web-client-id")
        .clientId("web-client")
        .clientSecret(passwordEncoder.encode("local-client-secret"))
        .clientAuthenticationMethod(ClientAuthenticationMethod.CLIENT_SECRET_BASIC)
        .authorizationGrantType(AuthorizationGrantType.AUTHORIZATION_CODE)
        .redirectUri("http://127.0.0.1:8080/login/oauth2/code/web-client")
        .postLogoutRedirectUri("http://127.0.0.1:8080/")
        .scope(OidcScopes.OPENID)
        .scope(OidcScopes.PROFILE)
        .clientSettings(ClientSettings.builder()
                .requireAuthorizationConsent(true)
                .requireProofKey(true)
                .build())
        .build();
~~~

A public client can use ClientAuthenticationMethod.NONE and omit the client secret. The key point here is that the login callback is added via **redirectUri(...)**, while the post-logout address is added via **postLogoutRedirectUri(...)**. Check the API of your project's Spring Authorization Server version if the builder differs; do not replace the two properties with a shared list.

If the client has multiple valid callbacks, call redirectUri multiple times. If it has multiple post-logout addresses, call postLogoutRedirectUri multiple times. Register only addresses actually controlled by the application:

~~~java
RegisteredClient webClient = RegisteredClient.withId("web-client-id")
        .clientId("web-client")
        .clientSecret(passwordEncoder.encode("local-client-secret"))
        .clientAuthenticationMethod(ClientAuthenticationMethod.CLIENT_SECRET_BASIC)
        .authorizationGrantType(AuthorizationGrantType.AUTHORIZATION_CODE)
        .redirectUri("https://app.example.com/login/oauth2/code/web-client")
        .redirectUri("https://app.example.com/oauth/callback")
        .postLogoutRedirectUri("https://app.example.com/")
        .postLogoutRedirectUri("https://app.example.com/signed-out")
        .scope(OidcScopes.OPENID)
        .build();
~~~

In a JDBC setup, these URIs are stored alongside the RegisteredClient. If you change Java configuration while the application reads clients from the database, the database values are what actually govern request handling. Inspect the exact client record in the data store using an appropriately authorized admin tool; do not assume a configuration bean overwrote an existing record.

Do not use wildcards such as **https://*.example.com/** or permit arbitrary URIs sent by requests. The redirect URI is a security boundary: if an attacker can control where the Authorization Server sends the authorization response, the authorization code can be diverted to an untrusted endpoint.

## 3. Checking redirect_uri in the Authorization Code Flow

With a Spring Security OAuth2 Client web application, the default callback typically takes the form:

~~~text
{baseUrl}/login/oauth2/code/{registrationId}
~~~

For example, when the application runs at **http://127.0.0.1:8080** and the registration ID is **web-client**, the URI sent is typically:

~~~text
http://127.0.0.1:8080/login/oauth2/code/web-client
~~~

Register this exact value in the Authorization Server. The client configuration can specify the redirect URI explicitly:

~~~yaml
spring:
  security:
    oauth2:
      client:
        registration:
          web-client:
            provider: local-authorization-server
            client-id: web-client
            client-secret: ${WEB_CLIENT_SECRET}
            client-authentication-method: client_secret_basic
            authorization-grant-type: authorization_code
            redirect-uri: "{baseUrl}/login/oauth2/code/{registrationId}"
            scope:
              - openid
              - profile
        provider:
          local-authorization-server:
            issuer-uri: https://identity.example.com
~~~

In YAML, the **{baseUrl}** placeholder is replaced by Spring Security OAuth2 Client with the request's base URL. If the application sits behind a reverse proxy, the base URL the application sees may differ from the URL the user sees. For example, the proxy terminates external TLS over HTTPS and forwards to the application over HTTP; if forwarded headers are not handled properly, the client may build a callback starting with **http://** instead of **https://**.

Compare the following items in exact order:

1. The **redirect-uri** value in ClientRegistration or the URL constructed by the public client.
2. The actual **redirect_uri** parameter in the request to the authorization endpoint.
3. The URI in the RegisteredClient redirect URIs list used by the Authorization Server.
4. The **redirect_uri** parameter in the code exchange request at the token endpoint.
5. The URI bound to the authorization code stored by the server.

The values must match according to the Authorization Server's rules. Under OAuth 2.0, redirect URI matching is normally an exact string comparison against registered URIs. Do not assume the server will normalize URIs that appear browser-equivalent.

RFC 8252 includes a narrow exception for native apps using loopback IP literals such as **127.0.0.1** or **[::1]**: the port may vary based on the listener port assigned by the OS. This exception applies to native app loopback redirect URIs, not as a general rule for web clients, and does not allow hostname wildcards. When using Spring Authorization Server, verify whether your version and validator implementation support this exception before relying on dynamic ports.

Small discrepancies that commonly cause errors:

| Discrepancy | Example |
|---|---|
| Hostname | **localhost** and **127.0.0.1** |
| Scheme | **http** and **https** |
| Port | **8080** and **8443** |
| Path | **/callback** and **/login/oauth2/code/web-client** |
| Trailing slash | **/callback** and **/callback/** |
| Context path | **/app/callback** and **/callback** |
| Case sensitivity | **/Callback** and **/callback** |
| Query string | URI with and without **?tenant=demo** |
| Encoding | Characters percent-encoded once or twice |

Do not strip trailing slashes, change hostnames, or decode and re-encode URIs to force two values to match. Choose one canonical URI and use that exact value across the client, server configuration, and deployment environment.

### Checking the Token Request

After the Authorization Server redirects the browser back to the callback, the client exchanges the authorization code at the token endpoint. If the authorization request sent redirect_uri, the token request must resend the exact same value:

~~~http
POST /oauth2/token HTTP/1.1
Host: identity.example.com
Content-Type: application/x-www-form-urlencoded
Authorization: Basic <client-credentials>

grant_type=authorization_code&
code=<authorization-code>&
redirect_uri=https%3A%2F%2Fapp.example.com%2Flogin%2Foauth2%2Fcode%2Fweb-client
~~~

If the URI in the token request differs from the URI used in the authorization request, the Authorization Server must reject the code exchange. Depending on where the mismatch occurs, the error may surface at the authorization endpoint or the token endpoint. At the token endpoint, the error is usually represented by the OAuth error **invalid_grant** because the authorization code is invalid for the current request. Do not work around this by omitting redirect_uri from the token request if that parameter was used in the authorization request.

## 4. Checking post_logout_redirect_uri in OIDC Logout

RP-Initiated Logout starts from the Relying Party (RP), typically a web application. The RP directs the browser to the OpenID Provider's **end_session_endpoint**. This endpoint is published in the OpenID Provider Configuration when the provider supports logout.

A logout request typically includes these parameters:

| Parameter | Purpose |
|---|---|
| **id_token_hint** | The ID Token issued to the RP, helping the OP identify the associated session and client |
| **post_logout_redirect_uri** | The address the user will return to after the OP processes logout |
| **state** | Value generated by the RP to correlate the response after logout |
| **client_id** | May be used in some cases to identify the RP depending on OP support |

When post_logout_redirect_uri is present, the OP verifies that the URI belongs to the post-logout URI list registered for the corresponding client. The URI must be a valid absolute address with no fragment. If the URI is unregistered or a valid client cannot be identified, the OP must not redirect the browser to an arbitrary address supplied by the request.

With Spring Authorization Server, the OIDC logout endpoint must be enabled in the Authorization Server configuration. Example using the configuration API of versions supporting the logout endpoint:

~~~java
http.with(authorizationServerConfigurer, authorizationServer ->
        authorizationServer.oidc(oidc ->
                oidc.logoutEndpoint(Customizer.withDefaults())
        )
);
~~~

Check your project's endpoint configuration and library version if the DSL API differs. The OIDC logout endpoint is not enabled merely because a client registered the **openid** scope; the endpoint and its logout handling components must be configured.

### Configuring the RP in Spring Security

Spring Security provides **OidcClientInitiatedLogoutSuccessHandler** to build the logout request from the provider's metadata and the login session's ID Token:

~~~java
@Bean
LogoutSuccessHandler oidcLogoutSuccessHandler(
        ClientRegistrationRepository clientRegistrationRepository) {

    OidcClientInitiatedLogoutSuccessHandler handler =
            new OidcClientInitiatedLogoutSuccessHandler(
                    clientRegistrationRepository);

    handler.setPostLogoutRedirectUri("{baseUrl}");
    return handler;
}
~~~

Attach the handler to the logout configuration:

~~~java
http.logout(logout -> logout
        .logoutSuccessHandler(oidcLogoutSuccessHandler)
);
~~~

The **{baseUrl}** value is expanded from the application request. If the application has a context path or runs behind a proxy, verify that the expanded URL matches the URI in RegisteredClient. In a multi-host environment, do not rely on arbitrary Host headers from the client to construct the redirect URI; explicitly configure trusted proxies and allowed hosts.

ClientRegistration must have appropriate OIDC provider information, typically via **issuer-uri** and discovery metadata. The metadata must provide **end_session_endpoint** if the RP uses this automatic handler. Check the issuer, discovery document, and logout endpoint in use; do not assemble a logout URL from an unverified hostname.

## 5. Diagnosing by Symptom

| Symptom | Likely Cause | How to Check |
|---|---|---|
| Authorization endpoint reports invalid redirect URI | Unregistered callback or different scheme/host/port/path | Compare the authorize request against RegisteredClient redirect URIs |
| Login succeeds, but code exchange returns invalid_grant | redirect_uri in token request differs from authorization request; expired or used code | Compare both requests and authorization timestamp/ID, without logging raw code |
| Fails only behind a reverse proxy | Application constructs base URL from internal scheme/host | Check forwarded headers, proxy configuration, and generated URI |
| Works locally, fails in production | Different hostname, TLS termination, context path, or port | Compare per-environment config and actual callback |
| Logout completes without returning to application | Unregistered post_logout_redirect_uri or wrong URI | Compare logout request against post-logout redirect URIs |
| Logout endpoint reports missing or invalid id_token_hint | RP did not send the OIDC session ID Token or session was lost | Check OIDC authentication and logout handler |
| Logout succeeds, but state is not processed | RP did not retain state or callback did not verify state | Check state generated, sent, and received back |
| One client logs out properly, another does not | Each client has its own post-logout URI list | Check the exact RegisteredClient identified by ID Token/client_id |

### Reverse Proxy and Forwarded Headers

A common setup is:

~~~text
Browser -- HTTPS --> Reverse proxy -- HTTP --> Spring application
~~~

If the Spring application only sees an internal HTTP connection, **{baseUrl}** may expand to HTTP. To handle this properly, the proxy must send appropriate forwarding headers such as **Forwarded** or **X-Forwarded-Proto**, **X-Forwarded-Host**, and **X-Forwarded-Port**. The application should trust these headers only when requests arrive from a trusted proxy.

With Spring Boot, you can configure the forwarded headers strategy according to your version:

~~~yaml
server:
  forward-headers-strategy: framework
~~~

Do not trust forwarded headers from all request sources when the application can be reached directly from untrusted networks. Verify whether the proxy overwrites headers sent by the user and accept traffic only from controlled proxies.

## 6. Step-by-Step Remediation Workflow

**Step 1: Identify the failing request type.** Determine whether the error happens at the authorization endpoint, token endpoint, or OIDC logout endpoint. Record the endpoint, normalized client ID, environment, and error category. Do not record authorization codes, access tokens, refresh tokens, ID Tokens, or client secrets.

**Step 2: Capture the actual URI from the request.** In browser developer tools or masked logs, inspect the redirect_uri or post_logout_redirect_uri parameter. Also inspect the value after decoding the URL once to understand what the server receives. Do not alter encoding arbitrarily before comparing.

**Step 3: Identify the actual client selected.** Check client_id in the authorization request, client authentication at the token endpoint, and the client identified from id_token_hint in the logout flow. With a JDBC repository, confirm which RegisteredClient record the application is reading.

**Step 4: Compare against the right list.** For login, compare redirect_uri against redirectUris. For logout, compare post_logout_redirect_uri against postLogoutRedirectUris. Do not add a URI to both lists just to make the request pass; determine which flow the URI serves.

**Step 5: Verify the external URL outside the proxy.** Compare the scheme, host, port, and context path used by the browser against the URL the application derives from the request. Check forwarded headers and proxy configuration.

**Step 6: Re-check the authorization code or logout session.** For token exchange, verify the code has not expired, has not been used, and was issued to the right client. For logout, verify the RP still has an appropriate ID Token for id_token_hint and the OP can identify the client.

**Step 7: Re-run both passing and failing cases.** Verify that the registered URI is accepted, a URI differing by a single character is rejected, redirects never go to a host outside the allowlist, and state is validated on the client side.

## 7. Example Testing Valid and Invalid URIs

You can verify metadata and RegisteredClient in an integration test, then send requests through the real endpoints. For the login callback, use the exact registered URI:

~~~java
String registeredCallback =
        "https://app.example.com/login/oauth2/code/web-client";

RegisteredClient client = RegisteredClient.withId("web-client-id")
        .clientId("web-client")
        .clientAuthenticationMethod(ClientAuthenticationMethod.NONE)
        .authorizationGrantType(AuthorizationGrantType.AUTHORIZATION_CODE)
        .redirectUri(registeredCallback)
        .postLogoutRedirectUri("https://app.example.com/")
        .scope(OidcScopes.OPENID)
        .build();

assertThat(client.getRedirectUris()).contains(registeredCallback);
assertThat(client.getPostLogoutRedirectUris())
        .contains("https://app.example.com/");
~~~

These assertions verify the fixture data. Integration tests should send authorization and logout requests through the real filter chain to prove the endpoints enforce the policy.

Your test matrix should cover at least these cases:

| Test Case | Expected Result |
|---|---|
| redirect_uri matches registered callback exactly | Authorization request proceeds |
| redirect_uri differs in port or path | Request is safely rejected |
| redirect_uri has a different hostname even pointing to localhost | Request is rejected |
| Token request resends the exact redirect_uri used | Authorization code can be exchanged if other conditions hold |
| Token request alters one character in redirect_uri | Code exchange is rejected |
| post_logout_redirect_uri is in the client's list | OP can redirect after successful logout |
| post_logout_redirect_uri is unregistered | OP refuses to redirect to that URI |
| Logout URI contains a fragment | URI violating the rules is not accepted |
| state is sent in the logout request | RP verifies the exact state upon receiving response |

Do not assert only the status code. Also check the Location header on redirects and ensure the target hostname belongs to the allowlist. When a URI is invalid, the Authorization Server must never respond by redirecting to an unverified URI.

## 8. Fixes That Introduce Risk

- Do not use wildcards or prefix matching for redirect URIs.
- Do not automatically add a URI taken from a request to RegisteredClient upon detecting a mismatch.
- Do not skip redirect_uri validation at the token endpoint to avoid invalid_grant.
- Do not reuse login redirect URIs as post-logout redirect URIs without explicitly registering them in the corresponding list.
- Do not trust arbitrary Forwarded or X-Forwarded headers from the Internet.
- Do not log authorization codes, ID Tokens, access tokens, refresh tokens, or client secrets during investigation.
- Do not redirect users to arbitrary URIs when the logout endpoint cannot authenticate the client.

If the application needs multiple hostnames per environment, manage each approved URI explicitly in client configuration or data. Each environment should have explicit callback and post-logout URIs rather than an inference rule derived from the request.

## 9. Completion Checklist

- Login callback is registered via redirectUri and matches the exact URI sent by the client.
- Token request resends the exact redirect_uri used to issue the authorization code.
- Post-logout callback is registered separately via postLogoutRedirectUri.
- OIDC logout endpoint is enabled and the RP obtains the right end_session_endpoint from provider metadata.
- RP sends a valid id_token_hint and retains state to validate the response.
- Base URL behind a reverse proxy has the right scheme, host, port, and context path.
- Forwarded headers are trusted only from configured proxies.
- Invalid URIs are rejected without redirecting to arbitrary hosts.
- Integration tests cover login callbacks, token exchange, and logout redirects.
- Logs and metrics contain no codes, tokens, secrets, or sensitive session data.

When handled according to the right flow and registered list, redirect_uri mismatch and post_logout_redirect_uri failures can be isolated quickly while keeping OAuth 2.0 and OpenID Connect security checks intact.
