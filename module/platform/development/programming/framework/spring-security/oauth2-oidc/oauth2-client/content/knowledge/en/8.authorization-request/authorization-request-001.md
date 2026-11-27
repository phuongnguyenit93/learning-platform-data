# 8.1. `OAuth2AuthorizationRequest` and Parameters Sent to the Provider

## 1. What Is `OAuth2AuthorizationRequest`?

In a **Spring Security OAuth 2.0/OIDC Client** application, the first step of the **Authorization Code** flow is usually sending the browser to the **Authorization Endpoint** of the Authorization Server (provider). This redirect URL carries parameters so the provider knows **which application is requesting authorization**, **what permissions the user needs to grant**, and **where the result should be returned**.

Spring Security models that request with the class:

~~~java
org.springframework.security.oauth2.core.endpoint.OAuth2AuthorizationRequest
~~~

`OAuth2AuthorizationRequest` is **an object describing an authorization request**. It contains the data needed to build the URL sent to the provider, and it can also carry **application-internal** information needed for subsequent steps. In the Authorization Code flow, this object is typically created when the browser accesses:

~~~http
GET /oauth2/authorization/corporate HTTP/1.1
Host: portal.example.com
~~~

Then Spring Security constructs the authorization request and returns a redirect response:

~~~http
HTTP/1.1 302 Found
Location: https://idp.example.com/oauth2/authorize?response_type=code&client_id=portal-web&...
~~~

The `OAuth2AuthorizationRequest` class is **not** the HTTP request used to exchange an authorization code for a token. Exchanging the code for an access token happens **after the callback**, typically as an HTTP POST from the backend to the **Token Endpoint**, with different parameters and security rules.

Four related concepts should be clearly understood:

| Component | Main Responsibility |
| --- | --- |
| `ClientRegistration` | **Static** configuration of an OAuth2 client: client ID, grant type, scopes, provider endpoints, redirect URI template |
| `OAuth2AuthorizationRequest` | Represents **one authorization initiation**: authorization URL, `state`, expanded redirect URI, additional parameters, and internal metadata |
| `OAuth2AuthorizationResponse` | Represents the result from the Authorization Endpoint, such as `code` or an error returned by the provider |
| `OAuth2AuthorizedClient` | Represents an authorized client, containing an access token and possibly a refresh token; used at a later stage |

**Key takeaway:** `ClientRegistration` describes *how the application is registered with the provider*; `OAuth2AuthorizationRequest` describes *one specific authorization request*.

## 2. Where Does the Authorization Request Fit in the OAuth2/OIDC Flow?

An OIDC Authorization Code flow typically includes:

~~~mermaid
sequenceDiagram
    actor Browser as Browser
    participant App as Spring Security OAuth2 Client
    participant Store as AuthorizationRequestRepository
    participant IdP as OIDC Provider

    Browser->>App: GET /oauth2/authorization/corporate
    App->>App: Look up ClientRegistration, create OAuth2AuthorizationRequest
    App->>Store: Save request bound to session/state
    App-->>Browser: 302 Location: Authorization Endpoint + parameters
    Browser->>IdP: GET /authorize?response_type=code&...
    IdP->>Browser: Authenticate user, ask for consent (if needed)
    IdP-->>Browser: 302 redirect_uri?code=...&state=...
    Browser->>App: GET callback?code=...&state=...
    App->>Store: Load/remove saved authorization request
    App->>App: Verify state and related information
    App->>IdP: POST Token Endpoint: code + client authentication + code_verifier (with PKCE)
    IdP-->>App: Access token, ID Token (OIDC), ...
    App-->>Browser: Complete login/application session
~~~

The browser actually **goes to the Authorization Endpoint**. It does not send `client_secret` itself to the provider and does not directly perform the token exchange in a backend web app.

On the Servlet side, Spring Security has common components:

- `OAuth2AuthorizationRequestRedirectFilter`: detects requests to initiate authorization and redirects the browser to the provider URL.
- `OAuth2AuthorizationRequestResolver`: resolves `registrationId` and creates the corresponding `OAuth2AuthorizationRequest`; the default implementation is `DefaultOAuth2AuthorizationRequestResolver`.
- `AuthorizationRequestRepository<OAuth2AuthorizationRequest>`: stores and retrieves the authorization request between redirect and callback; the common default implementation is `HttpSessionOAuth2AuthorizationRequestRepository`.
- `OAuth2LoginAuthenticationFilter`: handles the callback in the OAuth2 Login flow; coordinates verifying stored data and performing the corresponding authentication.

In WebFlux there is a corresponding set of reactive APIs, such as `OAuth2AuthorizationRequestRedirectWebFilter`, `ServerOAuth2AuthorizationRequestResolver`, `DefaultServerOAuth2AuthorizationRequestResolver`, and `ServerAuthorizationRequestRepository<OAuth2AuthorizationRequest>`. Class names and extension points must match **Servlet/WebFlux** and the Spring Security version the project is using.

## 3. Key Properties of `OAuth2AuthorizationRequest`

This class provides data such as:

| Property/Getter | Meaning | Usually Appears in URL Sent to Provider? |
| --- | --- | --- |
| `getAuthorizationUri()` | Authorization Endpoint URL receiving the request | It is the **target address** of the redirect |
| `getAuthorizationGrantType()` | Related grant type, usually `authorization_code` | Not required to appear as a separate parameter |
| `getResponseType()` | Requested response type, usually `code` | Yes: `response_type=code` |
| `getClientId()` | OAuth2 client identifier | Yes: `client_id` |
| `getRedirectUri()` | Specific callback URI to which the provider redirects | Usually yes: `redirect_uri` |
| `getScopes()` | Set of requested scopes | Can be present: `scope=openid profile...` |
| `getState()` | Value linking request/response to prevent forgery | Yes: `state` |
| `getAdditionalParameters()` | Extension parameters for the Authorization Endpoint | Yes, for entries configured to be emitted in the URL |
| `getAttributes()` | **Internal** data for Spring Security/the application | **Not automatically** sent as query parameters |
| `getAuthorizationRequestUri()` | Final URI used for redirection | This is the complete URL after assembly/encoding |

The getters above are the key accessors of the object. Field names in `OAuth2AuthorizationRequest` do not always match protocol parameter names 100%; Spring Security must map and **URL-encode** values before issuing the redirect.

For example, `attributes` can hold transaction-supporting data such as the registration ID or PKCE code verifier. In contrast, `additionalParameters` is intended for extension parameters that the Authorization Server needs to receive at the Authorization Endpoint. **Do not move secrets from `attributes` into `additionalParameters` just to "make them visible to the provider."**

### 3.1. `authorizationUri` vs. `authorizationRequestUri`

These two names are very easy to confuse:

- **`authorizationUri`:** the Authorization Endpoint address declared by the provider, for example `https://idp.example.com/oauth2/authorize`.
- **`authorizationRequestUri`:** the complete URL including the endpoint and query string such as `response_type`, `client_id`, `state`, `code_challenge`, and additional parameters.

When using Spring Security defaults, let the framework build and encode the final URI. If building the URL manually, handle query parameters properly and avoid **double-encoding**, which corrupts `state` or alters `redirect_uri`.

## 4. Core Parameters Sent to the Provider

A common Authorization Code/OIDC example:

~~~text
https://idp.example.com/oauth2/authorize
  ?response_type=code
  &client_id=portal-web
  &redirect_uri=https%3A%2F%2Fportal.example.com%2Flogin%2Foauth2%2Fcode%2Fcorporate
  &scope=openid%20profile%20email
  &state=RANDOM_UNPREDICTABLE_VALUE
  &code_challenge=E9Melhoa2OwvFrEMTJguCHaoeK1t8URWbuGJSstw-cM
  &code_challenge_method=S256
  &nonce=RANDOM_OIDC_NONCE
~~~

The lines above are wrapped for readability; in reality, the value in HTTP `Location` is normally **a single URL**. This is an example explaining structure, not `state`/`nonce` values that can be reused in production.

| Parameter | Standard/Context | Meaning | Notes |
| --- | --- | --- | --- |
| `response_type=code` | OAuth 2.0 Authorization Code | Requests the provider to return an authorization code after user consent | The value `code` corresponds to this grant |
| `client_id` | OAuth 2.0 | Tells the provider which application is requesting authorization | **Not a secret**; may appear in the URL |
| `redirect_uri` | OAuth 2.0 | Address where the provider sends the browser back after authorization | Must match a URI allowed by the provider; strictly validated |
| `scope` | OAuth 2.0/OIDC | Permissions/scopes requested by the client | Space-delimited list of scopes per the standard |
| `state` | OAuth 2.0 | Links the authorization response with the created request | Must be random, unpredictable, and stored for verification on callback |
| `code_challenge` | PKCE (RFC 7636) | Derived value from the code verifier | Sent on the **authorization request** |
| `code_challenge_method=S256` | PKCE | Specifies the algorithm used to derive the challenge | `S256` is preferred over `plain` |
| `nonce` | OpenID Connect | Binds the ID Token to the authentication request and helps mitigate replay | OIDC-specific; does not replace `state` |

In Authorization Code, `response_type` is typically `code`, while `authorization-grant-type` in the registration is also `authorization_code`. These are two different representations: one is a **protocol parameter at the Authorization Endpoint**, and the other is a **client configuration grant type**.

### 4.1. `client_id` and `redirect_uri`

`client_id` is issued to the application by the provider and identifies the client registration requesting authorization. Do not send `client_secret` on a browser redirect: secrets belong to client authentication at the Token Endpoint or another client authentication method.

`redirect_uri` has three points requiring special attention:

1. It must point to a callback that the browser **can reach**. For example, a public portal over HTTPS must use that public URL, not an internal container hostname.
2. The provider must validate it against registered URIs according to its policy. It is best to register **exact URIs** rather than broad wildcards.
3. If the request sends `redirect_uri`, the token exchange must also use the matching value as required by the authorization code flow; any mismatch can cause `invalid_grant`.

With Spring Security OAuth2 Login Servlet, the default callback is usually:

~~~text
{baseUrl}/login/oauth2/code/{registrationId}
~~~

For example, with `registrationId=corporate` and browser base URL `https://portal.example.com`, the redirect URI is:

~~~text
https://portal.example.com/login/oauth2/code/corporate
~~~

When the app sits behind a reverse proxy, configure forwarded headers or declare the public redirect URI properly; do not let untrusted host headers control the registered URI.

### 4.2. `scope` and Differences Between OAuth2/OIDC

Scopes are values defined or standardized by the provider. For example:

~~~text
scope=openid profile email
~~~

- `openid` signals an authentication request under **OpenID Connect**.
- `profile` and `email` are common OIDC scopes; actual data depends on the IdP, consent, and claim release policy.
- `offline_access` has OIDC semantics related to requesting offline access; how refresh tokens are issued, consent requirements, and specific support depend on the provider.
- Business scopes such as `orders.read` or `report.read` depend on the Resource Server and Authorization Server policy.

`scope` is only a **request**. The provider may reject, restrict, or return a different set of granted scopes. The application must not assume that simply sending `scope=orders.admin` means the access token definitely has that permission.

### 4.3. `state` Links Request and Response

`state` is an unpredictable value generated by the client before redirecting. The provider returns `state` in the callback so the client can match it against the saved authorization request.

~~~text
Client creates state = st_abc...          →     /authorize?...&state=st_abc...
Provider redirects to callback                  /login/oauth2/code/corporate?code=...&state=st_abc...
Client loads saved request, compares      →     state must match
~~~

`state` protects against **CSRF in the authorization flow**, and is an essential element for binding the callback to a valid initiated request. The value must have sufficient entropy, be hard to guess, and follow the proper lifecycle. Do not build `state` solely from a username, email, timestamp, or exposed session ID.

If you need to remember "which page the user wanted to return to after login", the application should keep that information in server/session storage or use a protected mechanism with strict validation policies. **Do not turn `state` into an arbitrary redirect URL controlled by external users**, as this can create an open redirect vulnerability or leak data.

## 5. PKCE: `code_challenge` Is Sent, `code_verifier` Must Be Kept

**Proof Key for Code Exchange (PKCE)** adds a mechanism to bind the authorization code to the party that initiated the flow. With `S256`:

~~~text
code_verifier  = high-entropy random value, 43–128 valid characters
code_challenge = BASE64URL-ENCODE(SHA256(ASCII(code_verifier)))
~~~

Example verification values from RFC 7636:

~~~text
code_verifier:
dBjftJeZ4CVP-mB92K27uhbUJU1p1r_wW1gFWFOEjXk

code_challenge:
E9Melhoa2OwvFrEMTJguCHaoeK1t8URWbuGJSstw-cM

code_challenge_method:
S256
~~~

In the **authorization request**, the client sends `code_challenge` and `code_challenge_method`. After receiving the authorization code, the client sends **`code_verifier` to the Token Endpoint**. The provider computes the challenge from the verifier itself and compares it with the value associated with the code.

~~~mermaid
sequenceDiagram
    participant C as OAuth2 Client
    participant AS as Authorization Server
    C->>C: Generate random code_verifier
    C->>C: Compute code_challenge = S256(verifier)
    C->>AS: Authorization request: code_challenge + method=S256
    AS-->>C: Callback: authorization code (+ state)
    C->>AS: Token request: code + code_verifier
    AS->>AS: Recompute challenge and compare
    AS-->>C: Tokens if all conditions are valid
~~~

**Do not send `code_verifier` through the browser URL**. Spring Security can keep it in `attributes` of `OAuth2AuthorizationRequest` or in flow-associated data that the token request component can retrieve. Only `code_challenge` goes into `additionalParameters` and appears on the authorization URL.

PKCE is especially important for public clients such as native/mobile apps and SPAs, and is also recommended for confidential clients when supported by the provider. It **does not replace** `state` checks, `redirect_uri` validation, client authentication, or ID Token verification.

In modern versions of Spring Security, `DefaultOAuth2AuthorizationRequestResolver` enables PKCE automatically in certain client configurations, such as clients recognized as public (client authentication method `none`). PKCE can also be enabled intentionally for other clients via a customizer when the provider supports it; do not assume every registration/version already has PKCE enabled just because authorization code is used.

## 6. OIDC `nonce` and Additional Login Parameters

When `scope` includes `openid` and the provider supports OIDC, `nonce` is a client-generated value used to bind an authentication request to the **ID Token**. The provider includes `nonce` in the corresponding ID Token, allowing the client to verify that the token belongs to the expected login attempt per the flow's requirements.

| Value | Where It Appears | Where It Is Checked | Purpose |
| --- | --- | --- | --- |
| `state` | Authorization Request and authorization response callback | Client matches callback against saved request | Binds redirect/callback, prevents CSRF in authorization flow |
| `nonce` | Authorization Request and `nonce` claim in ID Token | OIDC client validates ID Token per flow requirements | Binds ID Token to authentication request, mitigates replay |
| `code_challenge` | Authorization Request | Authorization Server compares with verifier when exchanging code | Binds authorization code to initiating client |
| `code_verifier` | Token Request (not in authorization URL) | Authorization Server | Proves the party exchanging the code possesses the verifier |

**Do not confuse these values.** All of them are typically random data, but they serve different authentication/authorization layers.

### 6.1. Common Standard OIDC Parameters

| Parameter | Meaning | Examples/Notes |
| --- | --- | --- |
| `prompt` | Requests how the provider interacts with the user | `login`, `consent`, `select_account`, `none` (per OIDC and provider capabilities) |
| `login_hint` | Login identity hint | Usually email or username; **not proof of authentication** |
| `max_age` | Maximum elapsed time since last authentication, in seconds | `max_age=0` may request fresh authentication |
| `acr_values` | Desired authentication level or method | Specific values agreed upon by the system/IdP |
| `ui_locales` | Preferred user interface languages | `vi en` |
| `claims` | Requests specific claims, possibly as an encoded JSON structure | URL length and provider support must be considered |
| `id_token_hint` | Previous ID Token used as a hint in some flows | Do not arbitrarily put sensitive tokens into URLs if unnecessary |

A request might look like:

~~~text
...&prompt=select_account&login_hint=alice%40example.com&ui_locales=vi%20en
~~~

These parameters can alter login behavior, affect user experience, or expose identity information in URLs/history/logs. Send only **genuinely needed data**, and do not directly trust a `login_hint` taken from uncontrolled input to determine identity.

### 6.2. Provider Extension Parameters vs. Standard Parameters

Some providers have proprietary parameters. For example:

- `access_type=offline` and certain variants of `prompt` appear in Google OAuth/OIDC-specific guides.
- `audience` may be required by some providers to specify the target API, though it is **not a general required parameter of RFC 6749**.
- `resource` is standardized by **RFC 8707 Resource Indicators for OAuth 2.0**, used when the Authorization Server supports explicitly specifying the intended Resource Server.
- `request` and `request_uri` relate to advanced profiles such as JWT-Secured Authorization Request (JAR) or Pushed Authorization Requests (PAR) if implemented by both provider and client.

Do not blindly copy query string examples from one provider to another. Unsupported extensions may be ignored or rejected. In particular, sending `resource`/`audience` does not guarantee a token will be issued for the desired API if the provider does not understand it, the client lacks permission, or policy disallows it.

## 7. What Data Must Never Be Put on the Authorization URL?

The Authorization URL passes through the browser and can appear in browser history, reverse proxy logs, ingress logs, observability tools, or certain referrer-related contexts. Sensitive values should not be sent as arbitrary query parameters.

| Data | Proper Typical Location | Reason |
| --- | --- | --- |
| `client_id` | Authorization Request | Public identifier of the client |
| `client_secret` | Token Endpoint/client authentication per supported grant | Client secret; must not be exposed via browser |
| `code_challenge` | Authorization Request | Derived value designed to be public |
| `code_verifier` | Token Request; kept internal until code exchange | If the verifier leaks, PKCE protection is compromised |
| `state` | Authorization Request + callback, verified client-side | Use a random value; do not embed secret information |
| `nonce` | Authorization Request + ID Token | Use a random value; do not embed secrets |
| Access token/refresh token | Token Response and protected client storage | Do not embed in authorization URL |
| ID Token | OIDC Token Response (in Authorization Code flow) | Do not use as `access_token` or put in URL unnecessarily |
| User password | Provider's login UI, protected by provider design | OAuth2 client does not need the password just to build an authorization request |

The **Authorization Code** after callback is also a sensitive short-lived value; the backend must exchange it through the appropriate channel, use it once, and avoid logging it.

## 8. Spring Boot Configuration Example and Default Authorization Request

Suppose a Servlet web application wants to allow login through an internal OIDC Provider. Typical Gradle dependencies:

~~~gradle
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-security'
    implementation 'org.springframework.boot:spring-boot-starter-oauth2-client'
}
~~~

`application.yml`:

~~~yaml
spring:
  security:
    oauth2:
      client:
        registration:
          corporate:
            provider: corporate-oidc
            client-id: ${CORPORATE_CLIENT_ID}
            client-secret: ${CORPORATE_CLIENT_SECRET}
            authorization-grant-type: authorization_code
            client-authentication-method: client_secret_basic
            redirect-uri: "{baseUrl}/login/oauth2/code/{registrationId}"
            scope:
              - openid
              - profile
              - email
        provider:
          corporate-oidc:
            issuer-uri: https://idp.example.com/realms/employees
~~~

`SecurityFilterChain`:

~~~java
@Configuration
class SecurityConfig {

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http) throws Exception {
        http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/", "/assets/**").permitAll()
                .anyRequest().authenticated()
            )
            .oauth2Login(Customizer.withDefaults());

        return http.build();
    }
}
~~~

Types and annotations are imported from the corresponding Spring Boot, Spring Framework, and Spring Security packages; `import` statements are omitted in the example.

When `/oauth2/authorization/corporate` is accessed:

1. Spring Security looks up `ClientRegistration` by `registrationId=corporate`.
2. The resolver finds the **Authorization Endpoint** via the provider metadata of `corporate-oidc`.
3. The resolver creates `OAuth2AuthorizationRequest`, including `client_id`, `response_type=code`, expanded `redirect_uri`, scope, state, and appropriate additional security parameters.
4. The repository stores information needed for the callback; in common default Servlet configurations, data is kept via **HTTP session**.
5. The browser is redirected to the IdP.
6. After the provider returns the callback, Spring Security uses the stored data to continue authentication and exchange the code for tokens.

`issuer-uri` only helps determine metadata and trust information about the provider; it **does not automatically change authorization request behavior** into a different grant.

### 8.1. Understanding the Complete Sent URI

The following URI example has been **percent-encoded** for the required values:

~~~http
HTTP/1.1 302 Found
Location: https://idp.example.com/realms/employees/protocol/openid-connect/auth?response_type=code&client_id=portal-web&scope=openid%20profile%20email&state=ObfAc2WvD4c8&redirect_uri=https%3A%2F%2Fportal.example.com%2Flogin%2Foauth2%2Fcode%2Fcorporate&code_challenge=E9Melhoa2OwvFrEMTJguCHaoeK1t8URWbuGJSstw-cM&code_challenge_method=S256
~~~

This URL is illustrative, not an exhaustive description of every parameter that every version/provider will necessarily emit. In particular, `nonce` may be added in an OIDC flow depending on provider/version/configuration; parameter ordering does not matter to protocol semantics.

**Do not test the application by comparing the entire `Location` string against a fixed string**: `state`, PKCE challenge, and nonce must change across flows, and query parameter order may also change.

## 9. Building `OAuth2AuthorizationRequest` Manually with Builder

You can build a request manually to understand this class's data model:

~~~java
OAuth2AuthorizationRequest createRequest(
        String randomState,
        String publicRedirectUri) {

    return OAuth2AuthorizationRequest.authorizationCode()
        .authorizationUri("https://idp.example.com/oauth2/authorize")
        .clientId("portal-web")
        .redirectUri(publicRedirectUri)
        .scopes(Set.of("openid", "profile"))
        .state(randomState)
        .additionalParameters(params -> {
            params.put("prompt", "select_account");
            params.put("ui_locales", "vi en");
        })
        .attributes(attrs -> {
            attrs.put("internalFlowName", "staff-login");
        })
        .build();
}
~~~

Parts in the example:

- `authorizationCode()` selects the authorization request form with `response_type=code`.
- `authorizationUri(...)` selects the **target endpoint**.
- `clientId(...)` and `redirectUri(...)` specify the client and callback.
- `scopes(...)` specifies the requested scopes.
- `state(...)` accepts a value **securely randomly generated** by the caller; never use a fixed string for all requests.
- `additionalParameters(...)` adds `prompt`/`ui_locales` that the provider can accept.
- `attributes(...)` keeps `internalFlowName` for internal use, **not automatically encoded into the authorization URL**.

This snippet focuses on data structure and does not yet generate/store `code_verifier`, `nonce`, or complete callback logic. **In real applications, customize Spring Security's default resolver** to leverage built-in state, PKCE, nonce, and authorization request storage rather than rebuilding the entire authentication flow.

### 9.1. Reading the Request After Building It

~~~java
OAuth2AuthorizationRequest request =
    createRequest(secureRandomState, publicRedirectUri);

String targetUrl = request.getAuthorizationRequestUri();
Map<String, Object> extra = request.getAdditionalParameters();
Map<String, Object> internal = request.getAttributes();
String state = request.getState();
~~~

The statements above show:
- `targetUrl` is the appropriate value to use as the redirect target.
- `extra` describes the parameters emitted to the provider (as Spring constructs the URI).
- `internal` is used on the **client** side and is not sent to the provider by default.
- `state` serves both the request and callback matching.

Do not log the entire request object in production: `attributes` may contain data that needs protection such as the PKCE code verifier, while the URI contains `state` and sometimes personal information in `login_hint`.

## 10. Customizing Authorization Requests with `OAuth2AuthorizationRequestResolver` (Servlet)

When you want to add a valid provider parameter such as `prompt=select_account`, you can attach a customizer to `DefaultOAuth2AuthorizationRequestResolver`:

~~~java
@Configuration
class OAuth2LoginCustomization {

    @Bean
    SecurityFilterChain securityFilterChain(
            HttpSecurity http,
            ClientRegistrationRepository registrations) throws Exception {

        var resolver = new DefaultOAuth2AuthorizationRequestResolver(
            registrations, "/oauth2/authorization");

        resolver.setAuthorizationRequestCustomizer(builder -> {
            builder.additionalParameters(parameters ->
                parameters.put("prompt", "select_account"));
        });

        http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/").permitAll()
                .anyRequest().authenticated()
            )
            .oauth2Login(oauth2 -> oauth2
                .authorizationEndpoint(endpoint -> endpoint
                    .authorizationRequestResolver(resolver)
                )
            );

        return http.build();
    }
}
~~~

Here:
- `DefaultOAuth2AuthorizationRequestResolver` still handles looking up `ClientRegistration` and preparing essential fields.
- The customizer **adds** an OIDC parameter supported by the provider.
- Configuration inside `oauth2Login(...).authorizationEndpoint(...)` binds the new resolver to the login flow.
- The browser continues to use the `/oauth2/authorization/{registrationId}` initiation path.

Additional parameters must be supported by the provider. `prompt=select_account` is a useful OIDC option for some providers; specific behavior may vary by provider. If parameters need to be added per registration, the resolver may require logic keyed to the corresponding provider.

### 10.1. How to Enable PKCE Intentionally

When the Authorization Server supports PKCE and you want to apply it explicitly for an authorization code client, Spring Security provides a customizer:

~~~java
var resolver = new DefaultOAuth2AuthorizationRequestResolver(
    registrations, "/oauth2/authorization");

resolver.setAuthorizationRequestCustomizer(builder -> {
    OAuth2AuthorizationRequestCustomizers.withPkce().accept(builder);

    builder.additionalParameters(params -> {
        params.put("prompt", "select_account");
    });
});
~~~

`OAuth2AuthorizationRequestCustomizers.withPkce()` adds PKCE data according to Spring Security's contract: challenge/method for the authorization URL and the verifier to retain for the token request. Calling `withPkce()` is meaningful when **the provider supports PKCE**; for some public clients, Spring Security already enables PKCE by default.

If a customizer also modifies framework-managed values (such as `state`, `redirect_uri`, `nonce`, or PKCE values), you must fully understand the impact on the callback and token exchange. A safe practice is to **only add necessary business parameters** while leaving default security checks intact.

### 10.2. Adding Dynamic `login_hint`: Which Data Sources Are Trusted?

For example, a user selects their organization account email before logging in. That email can be placed in `login_hint`, but it must be treated strictly as a **UI hint**. Do not assume the provider has authenticated the user based on this parameter.

A complete custom resolver might:
1. Read a hint value accepted by the application according to policy.
2. Validate format and length limits.
3. Add it only for allowed registrations and providers that support it.
4. Avoid putting sensitive information in the URL if unnecessary.
5. Preserve state, nonce, PKCE, and redirect URI managed by Spring Security.

If per-request logic based on `HttpServletRequest` is needed, you can implement a wrapper around `OAuth2AuthorizationRequestResolver` and delegate core request construction to the default resolver. Pay attention to both `resolve(HttpServletRequest)` and `resolve(HttpServletRequest, String registrationId)` methods to preserve proper Spring Security behavior in both cases.

## 11. Storing the Request Between Redirect and Callback

An Authorization Request is not just a URL. The application also needs to keep corresponding data to restore context when the browser returns to the callback.

### 11.1. Servlet: `AuthorizationRequestRepository`

Spring Security Servlet contract:

~~~java
AuthorizationRequestRepository<OAuth2AuthorizationRequest>
~~~

Common implementation:

~~~java
HttpSessionOAuth2AuthorizationRequestRepository
~~~

The repository is responsible for saving, loading, and removing the authorization request according to its lifecycle. For session-based web applications, `JSESSIONID` or an equivalent session cookie maintains the link between the browser and the server-side HTTP session.

Operational considerations:

- **Save the request before redirecting:** when the provider redirects back, the backend must be able to reload the created request.
- **Bind the callback:** `state` on the callback is matched against the pending request.
- **Short-lived data:** the request should be removed after processing to prevent reuse on other callbacks.
- **Session and SameSite:** cookie configuration, domain, Secure, SameSite, and reverse proxies can affect whether the callback brings back the appropriate session.
- **Multi-instance applications:** if sessions live in each instance's memory, appropriate coordination/shared session storage or consistent infrastructure configuration is needed; do not rely on load balancer luck.
- **Do not store all data in `state` on the URL:** keep trusted data server-side whenever possible.

Example of changing the request initiation base URI:

~~~java
http.oauth2Login(oauth2 -> oauth2
    .authorizationEndpoint(endpoint -> endpoint
        .baseUri("/sso/authorization")
    )
);
~~~

When changing the base URI, the login initiation link typically changes to `/sso/authorization/corporate`. **This is not the callback URI**; the callback is still governed by `redirectionEndpoint` and the provider registration. If you change the callback, you must adjust it consistently across Spring Security, the client's `redirect-uri`, and the Authorization Server.

### 11.2. WebFlux: Reactive Repository and Resolver

With WebFlux, the concepts are similar, but **APIs accept/return `ServerWebExchange` and `Mono`**:

| Servlet/MVC | Reactive/WebFlux |
| --- | --- |
| `ClientRegistrationRepository` | `ReactiveClientRegistrationRepository` |
| `OAuth2AuthorizationRequestResolver` | `ServerOAuth2AuthorizationRequestResolver` |
| `DefaultOAuth2AuthorizationRequestResolver` | `DefaultServerOAuth2AuthorizationRequestResolver` |
| `AuthorizationRequestRepository<OAuth2AuthorizationRequest>` | `ServerAuthorizationRequestRepository<OAuth2AuthorizationRequest>` |
| `HttpSessionOAuth2AuthorizationRequestRepository` | `WebSessionOAuth2ServerAuthorizationRequestRepository` |
| `SecurityFilterChain` / `HttpSecurity` | `SecurityWebFilterChain` / `ServerHttpSecurity` |

Basic configuration example:

~~~java
@Configuration
@EnableWebFluxSecurity
class ReactiveLoginSecurity {

    @Bean
    SecurityWebFilterChain webFluxSecurity(ServerHttpSecurity http) {
        return http
            .authorizeExchange(auth -> auth
                .pathMatchers("/").permitAll()
                .anyExchange().authenticated()
            )
            .oauth2Login(Customizer.withDefaults())
            .build();
    }
}
~~~

Spring Security WebFlux uses the corresponding resolver and repository to resolve the authorization request and manage context between redirect and callback. When a parameter needs to be customized in WebFlux, use the **server/reactive resolver** of the current Spring Security version; do not inject Servlet's `HttpServletRequest` or `DefaultOAuth2AuthorizationRequestResolver` into a Netty/WebFlux flow.

If an application uses both Login and OAuth2 Client to call APIs, do not confuse storage for an **in-progress authorization request** with storage for an **authorized client after tokens have been obtained**. The two have different lifecycles and responsibilities.

## 12. Interaction Between Redirect Request and Token Request

A common mistake is modifying the authorization request while forgetting the code exchange step. The two HTTP requests have different parameter sets:

| Parameter/Data | Authorization Endpoint (via browser) | Token Endpoint (backend, after callback) |
| --- | --- | --- |
| `client_id` | Usually present | May be present, depending on client authentication method |
| `client_secret` | **No** | May be used if confidential client and specified by provider |
| `response_type=code` | **Yes** | No |
| `grant_type=authorization_code` | No | **Yes** |
| `redirect_uri` | Usually present | Present when required by protocol/provider; must match the initial request |
| `state` | **Yes** | Usually not a token request parameter |
| `code_challenge`, `code_challenge_method` | **Yes when using PKCE** | No |
| `code_verifier` | **No** | **Yes when using PKCE** |
| `code` | Not yet present | **Yes**, obtained from callback |
| `scope` | Usually present | Typically not repeated when exchanging authorization code |
| Access token/ID Token | Not yet present in Authorization Code request | Returned in token response if issued successfully |

Diagram:

~~~text
(1) GET /authorize?response_type=code&client_id=...&state=...&code_challenge=...
                  |
                  v
(2) GET /login/oauth2/code/corporate?code=...&state=...
                  |
                  v
(3) POST /token
    grant_type=authorization_code
    code=...
    redirect_uri=...
    code_verifier=...                (if using PKCE)
    + client authentication          (if applicable)
                  |
                  v
(4) Token response → Authentication / OAuth2AuthorizedClient
~~~

The provider may return:

~~~http
HTTP/1.1 302 Found
Location: https://portal.example.com/login/oauth2/code/corporate?error=access_denied&state=...
~~~

When `error` is present, it is an **error authorization response**. The application must handle the callback safely, verify state/flow according to the protocol, and avoid displaying error content that contains secret information.

## 13. Extending per Provider: Compatibility and Security

Before adding a parameter, answer three questions:

1. **Standard or provider-specific?** `prompt` is an OIDC parameter; `audience` is provider-dependent; `resource` is defined in RFC 8707 if supported by the server.
2. **What is the value and where does it come from?** If it is user data, could it leak in URLs/logs? If taken from a browser query parameter, has it been constrained and validated?
3. **Does the provider accept it?** Check discovery metadata, documentation, or IdP configuration; some servers immediately reject unsupported parameters.

Important security considerations:

- **Do not let clients arbitrarily override the Authorization Endpoint** via a request-supplied URL; this easily leads to SSRF, open redirect, or sending login credentials to a fake provider.
- **Do not disable or bypass state validation** when needing to store business data; use session-bound storage or a separate properly protected mechanism.
- **Do not hardcode PKCE code verifier, nonce, or state** for easier testing; every flow must have suitable, unpredictable values.
- **Do not put bearer tokens, refresh tokens, client secrets, passwords, or unnecessary PII into URLs**.
- **Do not treat scope, audience, or login_hint as proof of authentication**; actual results must be verified at the callback, token response, and Resource Server.
- **Do not use OAuth2 Login as an Authorization Server**; the APIs above describe the client role.
- **Do not replace URI validation with broad wildcard redirect allowances**; the registration and IdP must agree on exact callbacks.
- **Do not build auth logic solely on seeing `code` in the callback**; state, PKCE, client/issuer, token validation, and other standard steps must still be verified.

If complex requests with many claims cause the URL to exceed length limits, consider **PAR (RFC 9126)** or **JAR (RFC 9101)** if supported by the Authorization Server and client library. Simply adding `request_uri` to `additionalParameters` cannot be considered a full PAR implementation: PAR requires a separate push-request step before redirecting.

## 14. Observing and Troubleshooting Authorization Requests

### 14.1. Observing Redirects with an HTTP Client

In development, you can inspect the response **without automatically following redirects**:

~~~bash
curl -i --max-redirs 0 \
  http://localhost:8080/oauth2/authorization/corporate
~~~

Expect an HTTP 302 with `Location` pointing to the provider's Authorization Endpoint. Real-world output depends on whether the application requires HTTPS, session cookies, or other protections.

Note: `state`, `nonce`, `code_challenge`, and session cookies are security-flow-related data. Collect/share only appropriately masked or truncated details; do not push full Authorization URLs into public logs or tickets.

### 14.2. Common Error Table

| Symptom | Possible Cause | What to Check |
| --- | --- | --- |
| `/oauth2/authorization/corporate` does not redirect | Wrong `registrationId`, missing registration, changed base URI, security chain does not enable login | Check `ClientRegistration`, endpoint matcher, and `oauth2Login()` |
| Provider reports `invalid_request` | Missing/invalid `response_type`, `redirect_uri`, scope, or extension parameter | Inspect provider metadata and actual parameters after URL-encoding |
| Provider reports `invalid_client` | Wrong `client_id` or client not permitted for the corresponding flow | Check registration and client configuration at the IdP |
| Provider reports `invalid_scope` | Scope not permitted or malformed | Compare requested scopes against provider policy |
| `redirect_uri_mismatch` | Callback differs from URI registered at provider | Verify exact URI, HTTPS, forwarded headers, and reverse proxy |
| Callback reports error about `state` | Original request/session lost, state mismatch, or tampered | Check session cookie, request repository, multi-instance setup, and callback |
| Authorization succeeds but token exchange fails | Code already used/expired, wrong client auth, wrong PKCE verifier, or redirect URI mismatch | Check token request per flow and secret-masked logs |
| OIDC ID Token validation fails | Issuer/audience/nonce/signature/time mismatch | Check issuer metadata, system clock, JWKS, and flow mapping |
| Browser returns to HTTP/internal hostname | App behind proxy infers `{baseUrl}` incorrectly | Configure trusted forwarded headers or fixed public redirect URI |
| Provider ignores `prompt`/`login_hint` | Provider does not support it or has its own policy | Check provider documentation; do not assume extensions are honored |
| Very long URL or `414 URI Too Long` | Many scopes/claims/custom parameters | Reduce data in URL or use an appropriate standard mechanism if supported by provider |
| Sends OAuth2 request but app fails to save session | Cookie/SameSite/session storage or security proxy misconfiguration | Inspect `Set-Cookie`, `Cookie` on callback, and repository |

**Diagnose in order:** verify the browser is redirected to the **correct Authorization Endpoint**, the URL has the expected parameters, the provider accepts the request, the browser returns to the callback with state/code, and the backend retrieves the saved authorization request before moving to token exchange.

### 14.3. Selective Logging

Log only operational fields such as registration ID, endpoint hostname, processing step, internal correlation ID, and sanitized error codes. Avoid logging:

- `client_secret`, authorization code, `code_verifier`, access/refresh tokens, ID Token.
- Full values of `state`, `nonce`, session cookies.
- `login_hint`, `claims`, or other user information when unnecessary.

When debugging is required, use time-limited logs and sensitive-data masking tools. Enabling "TRACE for all HTTP traffic" can leak credentials if uncontrolled.

## 15. Case Studies

### Scenario 1 — Requiring Users to Re-Select Their Account on Every Login

**Requirement:** An OIDC application wants to ask the provider to show an account chooser.

**Approach:** Keep the default resolver and add `prompt=select_account` via `additionalParameters`, after confirming the provider supports it. Do not manually alter `state`, PKCE, or `redirect_uri`.

### Scenario 2 — An API Requires Scope `reports.read`

**Requirement:** The application logs employees in and then calls the Reports API.

**Approach:** Configure/request scope `reports.read` if permitted by the Authorization Server. After the callback, the OAuth2 Client uses the **issued access token** to call the API; the Reports API acting as a **Resource Server** verifies the token and actual permissions. Simply having `scope` on the authorization URL does not prove the token was granted that permission.

### Scenario 3 — OAuth2 Callback Has `code` but Reports "authorization_request_not_found"

**Requirement:** In a multi-instance system, the browser logged in at the IdP successfully, but the callback fails.

**Approach:** Check where the authorization request was stored and whether the callback hits the same session/instance or a shared session store. Also check cookies, SameSite, domain, path, ingress, and state. Do not solve this by bypassing state checking.

### Scenario 4 — Wanting to Send PKCE Verifier in the Authorization URL So the Provider "Can Read It Immediately"

**Requirement:** An implementer plans to put `code_verifier` into `additionalParameters`.

**Approach:** Do not do this. Send only `code_challenge` + `code_challenge_method` in the authorization request; **`code_verifier` must be retained and sent at the Token Endpoint** for the provider to verify.

### Scenario 5 — Employee Needs a Fresh Login Despite Active SSO Session

**Requirement:** A business operation requires recent re-authentication before performing a transaction.

**Approach:** Consider OIDC `prompt=login` and/or `max_age` according to authentication assurance requirements, while verifying the actual authentication result and relevant claims in the ID Token. Providers may have specific capabilities or policies; a single query parameter does not replace business-level assurance checks.

## 16. Review Questions

**1. How does `OAuth2AuthorizationRequest` differ from `ClientRegistration`?**

`ClientRegistration` is the client registration configuration, whereas `OAuth2AuthorizationRequest` is the authorization request for one specific redirect, including state, final URI, and flow metadata.

**2. How do `additionalParameters` and `attributes` differ?**

`additionalParameters` are parameters added to the authorization URL as Spring constructs the request. `attributes` are **client-internal** data not automatically sent to the provider, such as data needed for subsequent steps.

**3. Should `code_verifier` be sent to the Authorization Endpoint?**

No. Send `code_challenge` and method `S256`; keep the verifier to send to the Token Endpoint after receiving the code.

**4. Do `state` and `nonce` replace each other?**

No. `state` binds the callback to the authorization request; `nonce` binds the ID Token to the OIDC authentication request. They serve distinct purposes.

**5. Is `prompt=login` a mandatory OAuth2 parameter for every provider?**

No. It is an OIDC/provider-capability parameter, not a required parameter for every OAuth2 authorization request.

**6. Why can changing `redirect-uri` cause login to fail?**

Because the provider checks the redirect URI against the registration; the token exchange and client steps also rely on a callback consistent with the initial authorization request.

**7. If only `code` is present on the callback, can the user be logged in immediately?**

No. You must validate the flow via state and related constraints, exchange the code at the Token Endpoint, then validate the token/ID Token and build the Authentication properly.

## 17. Official References

- [Spring Security — OAuth 2.0 Login (Servlet)](https://docs.spring.io/spring-security/reference/servlet/oauth2/login/index.html)
- [Spring Security — OAuth 2.0 Login Advanced Configuration (Servlet)](https://docs.spring.io/spring-security/reference/servlet/oauth2/login/advanced.html)
- [Spring Security — OAuth 2.0 Client (Servlet)](https://docs.spring.io/spring-security/reference/servlet/oauth2/client/index.html)
- [Spring Security — OAuth 2.0 Login (Reactive)](https://docs.spring.io/spring-security/reference/reactive/oauth2/login/index.html)
- [Spring Security API — OAuth2AuthorizationRequest](https://docs.spring.io/spring-security/site/docs/current/api/org/springframework/security/oauth2/core/endpoint/OAuth2AuthorizationRequest.html)
- [Spring Security API — DefaultOAuth2AuthorizationRequestResolver](https://docs.spring.io/spring-security/site/docs/current/api/org/springframework/security/oauth2/client/web/DefaultOAuth2AuthorizationRequestResolver.html)
- [RFC 6749 — The OAuth 2.0 Authorization Framework](https://www.rfc-editor.org/rfc/rfc6749)
- [RFC 7636 — Proof Key for Code Exchange by OAuth Public Clients](https://www.rfc-editor.org/rfc/rfc7636)
- [RFC 8707 — Resource Indicators for OAuth 2.0](https://www.rfc-editor.org/rfc/rfc8707)
- [RFC 9126 — OAuth 2.0 Pushed Authorization Requests (PAR)](https://www.rfc-editor.org/rfc/rfc9126)
- [OpenID Connect Core 1.0 — Authentication Request](https://openid.net/specs/openid-connect-core-1_0.html)

**Remember:** `OAuth2AuthorizationRequest` determines **which authorization URL the provider receives for a specific authorization attempt**. Values such as `client_id`, `response_type`, `scope`, `state`, `code_challenge`, and OIDC `nonce` each have distinct roles. Use Spring Security's resolver and repository to properly manage requests, state, and PKCE; add parameters according to the provider contract, and always keep token-flow secrets on the client side.
