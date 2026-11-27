# Registering Native Applications with Appropriate Redirect URIs and PKCE

> **Chapter: Application Integration.** This lesson belongs to the **SPRING_SECURITY_OAUTH2_OIDC_AUTHORIZATION_SERVER** module, guiding how to design, configure, secure, test, and operate an OAuth 2.0/OpenID Connect Authorization Server with Spring Security and Spring Authorization Server in Spring Boot. This lesson focuses on registering mobile/desktop native apps as public clients, choosing platform-appropriate redirect URIs, and enforcing the Authorization Code Flow combined with PKCE.

## 1. Native Apps Are Public Clients

A native app is an application installed on a user's device, such as Android, iOS, macOS, Windows, Linux, or a hybrid application packaged as an app. The application can call the Authorization Server and Resource Server directly, yet any secret packaged inside the binary can be extracted.

Therefore, a native app is normally a **public OAuth client**:

- Has a `client_id` so the Authorization Server can identify the registration.
- Has no trustworthy `client_secret`. A secret embedded in an APK, IPA, desktop executable, or client configuration can be extracted by a user or attacker.
- Uses Authorization Code Grant combined with Proof Key for Code Exchange (PKCE).
- Opens the sign-in page using an external user-agent, typically the system browser or a secure browser tab.
- Receives the authorization response via a registered redirect URI.
- Stores tokens using the operating system's secure storage mechanisms.

`client_id` identifies the application, but does not prove that the binary making the request is an authentic build. PKCE protects the authorization code from being intercepted and exchanged by another app; it does not turn a public client into a confidential client.

### 1.1. Components in a Sign-In Flow

| Component | Role |
|---|---|
| Native app | Public OAuth2/OIDC client on the device |
| Authorization Server | Authenticates user, validates client/redirect/scope/PKCE, and issues codes/tokens |
| External user-agent | System browser or secure browser tab for user sign-in |
| Operating system URI dispatcher | Routes the redirect response to the app that registered the URI |
| Resource Server | Verifies the access token and enforces API authorization |
| PKCE verifier | Random secret held solely by the app during the current transaction |
| Redirect URI | Address receiving the authorization response after the user completes sign-in |

## 2. Choosing Redirect URIs by Platform

The redirect URI is a critical part of client registration. The Authorization Server must only redirect authorization responses to a URI registered by the client that passes request validation.

RFC 8252 describes three suitable redirect URI types for native apps:

| Type | Example | Suitable Platform | Recommendation |
|---|---|---|---|
| Claimed HTTPS URI | `https://app.example.com/oauth2/callback` | Android App Links, iOS Universal Links | Preferred when the platform supports verifying app-domain association |
| Private-use URI scheme | `com.example.mobile:/oauth2redirect/issuer-a` | Android/iOS and desktop | Use a scheme based on an organization-owned domain in reverse-domain order |
| Loopback IP URI | `http://127.0.0.1:51004/oauth2/callback` | Desktop apps able to open a local listener | Use loopback IP literal and dynamic port; do not use localhost |

### 2.1. Claimed HTTPS URI

Example:

~~~text
https://app.example.com/oauth2/callback
~~~

The operating system can verify that the app is authorized to handle URLs belonging to this domain:

- Android uses Android App Links and a Digital Asset Links file hosted on the domain.
- Apple platforms use Universal Links and an apple-app-site-association file, combined with the Associated Domains entitlement.
- The domain must be controlled by the organization and the association configuration must point to the exact package/bundle identifier.

RFC 8252 recommends that native apps prefer claimed HTTPS redirects whenever possible because the OS binds the domain to a verified application. Even when the redirect URI is HTTPS, the app remains a public client and must still use PKCE.

Do not register an HTTPS callback as a confidential web client simply because the URI has a domain. The client type must be recorded explicitly in the registration and appropriate public-client policies must be applied.

### 2.2. Private-Use URI Scheme

Example:

~~~text
com.example.mobile:/oauth2redirect/authorization-server
~~~

The scheme should be formed from an organization-owned domain in reverse order. If the organization owns example.com, the scheme com.example.mobile establishes clear ownership compared to a generic scheme like myapp.

Syntax note: after the scheme there is only **a single slash /** before the path. Do not change it to com.example.mobile://oauth2redirect/..., because that forms a URI with an authority rather than the private-use URI scheme format described by RFC 8252.

Multiple apps on the same device can register the same custom scheme. A rogue app could attempt to intercept the authorization code before the legitimate app. PKCE prevents an intercepted code from being exchanged for tokens if the rogue app lacks the original transaction's verifier. Even so, claimed HTTPS typically provides stronger app identity binding.

### 2.3. Loopback IP Redirect for Desktop

Desktop apps can open an HTTP listener bound strictly to the loopback interface and ask the operating system for an ephemeral port:

~~~text
http://127.0.0.1:51004/oauth2/callback
http://[::1]:61023/oauth2/callback
~~~

Operational rules:

- Bind the listener on 127.0.0.1 or ::1; never bind 0.0.0.0 or a LAN interface address.
- Open the listener before launching the browser authorization request.
- Use a port allocated by the OS; never assume a fixed port is always free.
- The Authorization Server must allow arbitrary ports for loopback IP redirect URIs while still validating the registered scheme, IP literal, and path exactly.
- Close the listener immediately after receiving a valid response or when the transaction expires.
- Prefer supporting both IPv4 and IPv6 when the platform permits.

RFC 8252 discourages http://localhost:.... Using an IP literal avoids DNS resolution and prevents the listener from inadvertently accepting traffic from other interfaces.

## 3. Registering a Native App in Spring Authorization Server

Each native app requires a RegisteredClient configured as a public client. Example registration for a mobile app:

~~~java
import java.time.Duration;
import java.util.UUID;

import org.springframework.security.oauth2.core.AuthorizationGrantType;
import org.springframework.security.oauth2.core.ClientAuthenticationMethod;
import org.springframework.security.oauth2.core.oidc.OidcScopes;
import org.springframework.security.oauth2.server.authorization.client.RegisteredClient;
import org.springframework.security.oauth2.server.authorization.settings.ClientSettings;
import org.springframework.security.oauth2.server.authorization.settings.TokenSettings;

RegisteredClient nativeMobile = RegisteredClient
        .withId(UUID.randomUUID().toString())
        .clientId("mobile-native")
        .clientName("Example Mobile App")
        .clientAuthenticationMethod(ClientAuthenticationMethod.NONE)
        .authorizationGrantType(AuthorizationGrantType.AUTHORIZATION_CODE)
        .redirectUri("https://app.example.com/oauth2/callback")
        .redirectUri("com.example.mobile:/oauth2redirect/authorization-server")
        .scope(OidcScopes.OPENID)
        .scope(OidcScopes.PROFILE)
        .scope("orders.read")
        .clientSettings(ClientSettings.builder()
                .requireProofKey(true)
                .requireAuthorizationConsent(true)
                .build())
        .tokenSettings(TokenSettings.builder()
                .accessTokenTimeToLive(Duration.ofMinutes(5))
                .build())
        .build();
~~~

Explanation:

- ClientAuthenticationMethod.NONE specifies that the client does not use a shared secret at the token endpoint.
- Register only AuthorizationGrantType.AUTHORIZATION_CODE for interactive user sign-in.
- redirectUri(...) contains only the app's specific callbacks.
- OidcScopes.OPENID requests an OIDC Authentication Request and ID Token.
- requireProofKey(true) requires PKCE for the Authorization Code Flow.
- requireAuthorizationConsent(true) requires consent per client policy; this can be adjusted to fit the organization's trust model and UX.
- A short access token TTL narrows the window for abuse if a device is lost or a token is exposed.

This example shows a registration using claimed HTTPS and a private-use scheme. For desktop loopback, register the controlled base URIs, for example:

~~~java
.redirectUri("http://127.0.0.1/oauth2/callback")
.redirectUri("http://[::1]/oauth2/callback")
~~~

Then configure a redirect validator for loopback ports as shown in section 5. Do not add a client secret to a native app registration and do not embed secrets in the app binary.

### 3.1. One Registration per App/Platform/Environment

Separate registrations can be created for:

- Android production and Android staging.
- iOS production and iOS staging.
- Desktop apps by operating system or release channel when callbacks or policies differ.

Separating registrations lets you constrain redirect URIs, scopes, consent policies, and lifecycles for each app. If sharing one client_id across platforms, ensure every redirect URI genuinely belongs to the same client product and shares the same security policy. Never add a test app's callback to a production registration merely for debugging convenience.

### 3.2. Persisting RegisteredClient Durably

RegisteredClientRepository manages registrations and is used by the Authorization Server for client authentication, authorization grant processing, and other protocol flows. InMemoryRegisteredClientRepository suits development/testing; production should use persistent storage such as JdbcRegisteredClientRepository or a fitting system implementation.

Native app registrations are security configuration. Changes to redirect URIs, scopes, or client settings must be access-controlled, audited, and reviewed; do not open public Dynamic Client Registration just so apps can declare arbitrary callbacks.

## 4. Authorization Code Flow Combined with PKCE

Native apps must use the Authorization Code Flow combined with PKCE. Do not use the Implicit Grant to receive access tokens directly on redirects, and do not use Resource Owner Password Credentials to collect user usernames/passwords inside the app.

Overall flow:

~~~mermaid
sequenceDiagram
    autonumber
    participant App as Native App
    participant OS as Browser / OS
    participant AS as Authorization Server
    participant API as Resource Server

    App->>App: Generate state, nonce and code_verifier
    App->>App: code_challenge = BASE64URL(SHA256(code_verifier))
    App->>OS: Open external browser with authorization request
    OS->>AS: /oauth2/authorize with redirect_uri and PKCE challenge
    AS->>OS: Login and consent UI
    OS-->>AS: User authenticates and approves
    AS-->>OS: Redirect with authorization code and state
    OS-->>App: OS dispatches callback URI to native app
    App->>App: Verify state and callback URI
    App->>AS: POST /oauth2/token with code_verifier
    AS->>AS: Verify code, client, redirect URI and PKCE
    AS-->>App: Access token and optional OIDC ID Token
    App->>API: API request with access token
    API-->>App: Protected resource response
~~~

### 4.1. Generating code_verifier and code_challenge

For each authorization transaction, the app generates a random, independent code_verifier. Per RFC 7636, the verifier is between 43 and 128 characters from the unreserved set; it is recommended to generate 32 random bytes with a cryptographic random generator and Base64URL-encode without padding.

With the S256 method:

~~~text
code_challenge =
    BASE64URL-ENCODE(SHA256(ASCII(code_verifier)))
~~~

The client sends code_challenge and code_challenge_method=S256 in the authorization request. The client keeps code_verifier in the app and sends it only in the token request after receiving the authorization code.

Do not use plain when the app supports S256. Never reuse verifiers across transactions, and never store verifiers in logs, analytics, the clipboard, or URLs.

### 4.2. State and Nonce

- state is a random, unpredictable value binding the callback to the pending authorization transaction. The app must reject responses missing state or with a mismatched state.
- For OIDC, nonce binds the ID Token to the Authentication Request. The app must verify nonce in the ID Token if nonce was sent.
- Store state, nonce, code_verifier, redirect URI, and issuer in a TTL-bounded transaction object. Clear the transaction once completed or failed.
- When an app supports multiple Authorization Servers, use a distinct redirect URI per issuer/provider and verify that the received callback URI matches the URI sent in the transaction.

Do not store only a single global currentState or currentVerifier variable shared across logins; concurrent login flows can overwrite each other's data.

## 5. Spring Authorization Server: Redirect URI Validation

Spring Authorization Server 1.5.8 uses OAuth2AuthorizationCodeRequestAuthenticationValidator by default to validate redirect_uri and scope. Default redirect URI matching is an exact string match.

This works well for claimed HTTPS and private-use schemes when the client sends the exact registered URI. However, desktop native apps using loopback ephemeral ports require extra handling: RFC 8252 requires the Authorization Server to allow any port on a loopback IP URI while keeping all other URI components intact.

**Do not solve this with wildcard hosts/paths.** Ignore the port only when both the registered URI and the requested URI are HTTP loopback IP literals; scheme, host, path, and all other components must still match.

### 5.1. Configuring a Validator for the Authorization Code Endpoint

Spring Authorization Server allows replacing the validator via OAuth2AuthorizationCodeRequestAuthenticationProvider.setAuthenticationValidator(). The example below preserves the default scope validator and replaces redirect validation with a policy supporting dynamic loopback ports.

~~~java
import java.net.URI;
import java.util.List;
import java.util.Objects;
import java.util.function.Consumer;

import org.springframework.security.authentication.AuthenticationProvider;
import org.springframework.security.oauth2.core.OAuth2Error;
import org.springframework.security.oauth2.core.OAuth2ErrorCodes;
import org.springframework.security.oauth2.server.authorization.authentication.OAuth2AuthorizationCodeRequestAuthenticationContext;
import org.springframework.security.oauth2.server.authorization.authentication.OAuth2AuthorizationCodeRequestAuthenticationException;
import org.springframework.security.oauth2.server.authorization.authentication.OAuth2AuthorizationCodeRequestAuthenticationProvider;
import org.springframework.security.oauth2.server.authorization.authentication.OAuth2AuthorizationCodeRequestAuthenticationValidator;
import org.springframework.security.oauth2.server.authorization.client.RegisteredClient;

private static Consumer<List<AuthenticationProvider>>
        configureNativeRedirectUriValidation() {

    return providers -> providers.forEach(provider -> {
        if (provider instanceof OAuth2AuthorizationCodeRequestAuthenticationProvider codeProvider) {
            Consumer<OAuth2AuthorizationCodeRequestAuthenticationContext> validator =
                    new NativeRedirectUriValidator()
                            .andThen(OAuth2AuthorizationCodeRequestAuthenticationValidator.DEFAULT_SCOPE_VALIDATOR);

            codeProvider.setAuthenticationValidator(validator);
        }
    });
}

static final class NativeRedirectUriValidator
        implements Consumer<OAuth2AuthorizationCodeRequestAuthenticationContext> {

    @Override
    public void accept(
            OAuth2AuthorizationCodeRequestAuthenticationContext context) {

        RegisteredClient client = context.getRegisteredClient();
        String requested = context.getAuthentication().getRedirectUri();

        boolean exactMatch = client.getRedirectUris().contains(requested);
        boolean loopbackPortMatch = !exactMatch
                && client.getRedirectUris().stream()
                .anyMatch(registered -> matchesLoopbackExceptPort(registered, requested));

        if (!exactMatch && !loopbackPortMatch) {
            OAuth2Error error = new OAuth2Error(OAuth2ErrorCodes.INVALID_REQUEST);
            throw new OAuth2AuthorizationCodeRequestAuthenticationException(error, null);
        }
    }

    private static boolean matchesLoopbackExceptPort(
            String registeredValue,
            String requestedValue) {

        if (requestedValue == null) {
            return false;
        }

        try {
            URI registered = URI.create(registeredValue);
            URI requested = URI.create(requestedValue);

            return isLoopbackBase(registered)
                    && isLoopbackRequest(requested)
                    && registered.getPort() == -1
                    && requested.getPort() >= 1
                    && requested.getPort() <= 65535
                    && registered.getHost().equalsIgnoreCase(requested.getHost())
                    && Objects.equals(registered.getRawPath(), requested.getRawPath())
                    && registered.getRawUserInfo() == null
                    && requested.getRawUserInfo() == null
                    && registered.getRawQuery() == null
                    && requested.getRawQuery() == null
                    && registered.getRawFragment() == null
                    && requested.getRawFragment() == null;
        }
        catch (IllegalArgumentException ex) {
            return false;
        }
    }

    private static boolean isLoopbackBase(URI uri) {
        return "http".equalsIgnoreCase(uri.getScheme())
                && isLoopbackIpLiteral(uri.getHost())
                && uri.getPort() == -1
                && uri.getRawUserInfo() == null
                && uri.getRawQuery() == null
                && uri.getRawFragment() == null
                && uri.getRawPath() != null
                && !uri.getRawPath().isEmpty();
    }

    private static boolean isLoopbackRequest(URI uri) {
        return "http".equalsIgnoreCase(uri.getScheme())
                && isLoopbackIpLiteral(uri.getHost())
                && uri.getPort() >= 1
                && uri.getPort() <= 65535
                && uri.getRawUserInfo() == null
                && uri.getRawQuery() == null
                && uri.getRawFragment() == null
                && uri.getRawPath() != null
                && !uri.getRawPath().isEmpty();
    }

    private static boolean isLoopbackIpLiteral(String host) {
        return "127.0.0.1".equals(host)
                || "::1".equals(host)
                || "[::1]".equals(host);
    }
}
~~~

This validator enforces a specific policy:

- The registered URI must be an HTTP loopback IP literal without port, user-info, query, or fragment.
- The requested URI must use the exact IP literal and path, differing only in a valid dynamic port.
- localhost, arbitrary hostnames, LAN IPs, wildcard hosts, different paths, or queries/fragments are rejected by the dynamic-port branch.
- Exact matches continue to be accepted for fully registered redirect URIs.

`requireProofKey(true)` forces requests to supply a PKCE challenge and token requests to supply a verifier. Native clients must use `code_challenge_method=S256`. If organizational policy requires the Authorization Server to reject `plain` as well, add a `code_challenge_method` check in the authentication validator and apply the same rule to PAR; never infer the method solely from the length or content of the challenge.

This is an example validator for the Authorization Code endpoint. If the deployment enables Pushed Authorization Requests (PAR), apply the same redirect URI policy to OAuth2PushedAuthorizationRequestAuthenticationProvider; do not let PAR and the authorization endpoint enforce two different rules.

### 5.2. Wiring the Validator into SecurityFilterChain

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.core.annotation.Order;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.oauth2.server.authorization.config.annotation.web.configurers.OAuth2AuthorizationServerConfigurer;
import org.springframework.security.web.SecurityFilterChain;

@Bean
@Order(1)
SecurityFilterChain authorizationServerSecurityFilterChain(HttpSecurity http)
        throws Exception {

    OAuth2AuthorizationServerConfigurer authorizationServer =
            OAuth2AuthorizationServerConfigurer.authorizationServer();

    http.securityMatcher(authorizationServer.getEndpointsMatcher())
            .with(authorizationServer, server -> server
                    .oidc(Customizer.withDefaults())
                    .authorizationEndpoint(endpoint ->
                            endpoint.authenticationProviders(
                                    configureNativeRedirectUriValidation())))
            .authorizeHttpRequests(authorize ->
                    authorize.anyRequest().authenticated());

    return http.build();
}
~~~

This example focuses on where to attach the validator; the application still needs to configure a user authentication filter chain, RegisteredClientRepository, authorization service, consent service, signing keys, and other required Authorization Server components.

## 6. Authorization Request and Token Request

### 6.1. Authorization Request

Example OIDC Authorization Code Request from a native app:

~~~http
GET /oauth2/authorize?response_type=code&client_id=mobile-native&redirect_uri=com.example.mobile%3A%2Foauth2redirect%2Fauthorization-server&scope=openid%20profile%20orders.read&state=STATE_RANDOM&nonce=NONCE_RANDOM&code_challenge=PKCE_S256_CHALLENGE&code_challenge_method=S256 HTTP/1.1
Host: login.example.vn
~~~

The Authorization Server verifies:

1. client_id exists and the registration is a public client.
2. response_type=code and the grant type is allowed.
3. redirect_uri matches the registration per the redirect policy.
4. scope is within the set of scopes the client is permitted to request.
5. A PKCE challenge is present because the client requires a proof key.
6. User authentication, consent, and authorization policies complete before issuing a code.

### 6.2. Authorization Response

After the user authenticates and consents successfully:

~~~http
HTTP/1.1 302 Found
Location: com.example.mobile:/oauth2redirect/authorization-server?code=AUTH_CODE_REDACTED&state=STATE_RANDOM
~~~

The operating system passes the URI to the native app. The app must verify:

- The callback URI matches the URI stored in the authorization transaction.
- state matches the pending value.
- The response does not contain an OAuth error; if it does, treat it as a failed transaction.
- The transaction has not expired and has not already been processed.

Do not exchange the authorization code if state is wrong or the callback arrived via a URI other than the one initiated.

### 6.3. Token Request

The native public client exchanges the code via a token request, sending client_id, redirect URI, and code_verifier; do not send a client secret:

~~~http
POST /oauth2/token HTTP/1.1
Host: login.example.vn
Content-Type: application/x-www-form-urlencoded

grant_type=authorization_code&client_id=mobile-native&code=AUTH_CODE_REDACTED&redirect_uri=com.example.mobile%3A%2Foauth2redirect%2Fauthorization-server&code_verifier=PKCE_VERIFIER_REDACTED
~~~

The Authorization Server verifies that the code is valid, belongs to the right client/redirect URI, has not been used, and that the verifier derives the stored challenge. If the verifier is wrong, the token endpoint must reject the request.

For a public client, client_id identifies the registration; it does not replace PKCE and does not prove that the app binary is a confidential client.

## 7. Configuring Callbacks on Android, iOS, and Desktop

### 7.1. Android App Links

For claimed HTTPS redirects, the manifest can declare an intent filter:

~~~xml
<intent-filter android:autoVerify="true">
    <action android:name="android.intent.action.VIEW" />
    <category android:name="android.intent.category.DEFAULT" />
    <category android:name="android.intent.category.BROWSABLE" />
    <data
        android:scheme="https"
        android:host="app.example.com"
        android:path="/oauth2/callback" />
</intent-filter>
~~~

The domain must publish Digital Asset Links to verify the application's package name and signing certificate fingerprint. Declaring the intent filter alone is not enough to prove domain ownership.

If using a private-use scheme, declare a dedicated scheme based on a reverse-domain name and validate the callback URI in the AppAuth response handler. Avoid registering a generic scheme such as myapp whenever possible.

### 7.2. iOS Universal Links

For claimed HTTPS URIs:

- Add the Associated Domains entitlement, e.g., applinks:app.example.com.
- Host the apple-app-site-association file on the domain over HTTPS.
- Declare the exact Team ID, Bundle ID, and allowed callback paths.
- Handle the Universal Link in the app delegate or scene delegate, then pass the URI to the corresponding authorization session.

If using a custom scheme, declare URL Types in Info.plist. Custom schemes still carry collision risk; PKCE and state remain mandatory.

### 7.3. Desktop Loopback

Desktop apps should:

1. Bind an HTTP listener on a loopback IP literal with port 0 so the OS assigns an open port.
2. Read the actual bound port from the listener and build the corresponding redirect URI.
3. Generate state, code_verifier, code_challenge, and save the transaction.
4. Open the system browser to the Authorization Server.
5. Receive the callback, validate path/state/transaction, exchange the code, and close the listener.
6. Time out and close the listener if the user cancels or the flow does not complete.

Never expose the callback listener on the LAN. Never keep the listener running indefinitely just waiting for OAuth redirects.

## 8. OIDC Validation and Storing Tokens on the Device

If the native app uses OIDC via the openid scope, the app must process the ID Token according to OIDC Core. At a minimum, verify:

- Signature using the discovered/trusted issuer's JWK Set.
- iss matches the configured issuer exactly.
- aud contains the native app's client ID; validate azp when applicable.
- exp has not passed and issuance time is reasonable.
- nonce matches the transaction if the Authorization Request sent a nonce.
- Additional claims such as auth_time, acr, or amr if the application requires specific authentication properties.

Do not merely Base64-decode the ID Token and trust the payload. The ID Token provides authentication information for the client; when calling APIs, the app sends an access token matching the audience/scopes accepted by the Resource Server.

### 8.1. Storing Tokens Safely

- Prefer keeping access tokens in memory and persist longer only when necessary.
- If credentials must survive app restarts, use Android Keystore or Apple Keychain with appropriate access controls.
- Never store tokens in plaintext SharedPreferences/UserDefaults, log files, crash reports, or analytics.
- Never write authorization codes, verifiers, ID Tokens, or refresh tokens to logs.
- Clear credentials on logout, account unlink, user deprovisioning, or device revocation per policy.
- Use TLS for all endpoints except the local loopback callback.

### 8.2. Refresh Tokens with Public Clients in Spring Authorization Server

Spring Authorization Server 1.5.8 guides public clients via PKCE and explicitly notes that the server does not issue refresh tokens to public clients. Therefore, do not assume the sample native client registration above will receive a refresh token simply because the app is mobile or desktop.

If the product requires long-lived sessions, explicitly define the session policy and re-authentication experience. If a confidential component is needed to hold refresh tokens, consider a Backend-for-Frontend (BFF) or an appropriate server-side architecture. Never embed a client secret into a native app to try to obtain refresh tokens.

## 9. Common Redirect URI Registration Mistakes

| Mistake | Risk | Mitigation |
| --- | --- | --- |
| Using wildcard redirect URIs | Codes may be sent to unintended callbacks | Register specific URIs and enforce exact match |
| Using generic custom schemes | Another app can hijack the callback | Use reverse-domain schemes and PKCE |
| Using localhost for desktop loopback | DNS/interface resolution may behave unexpectedly | Use 127.0.0.1 or [::1] |
| Server strictly exact-matches loopback port | App cannot use ephemeral ports | Install a narrow validator per RFC 8252 |
| Validator ignores host/path too | Can open up open redirects or code leakage | Ignore only the port on loopback IP literals |
| Embedding client secret in binary | Secret can be extracted | Register as public client with none |
| Using embedded WebView for login | App can read credentials/cookies and alter login UI | Open an external user-agent |
| Missing PKCE | Authorization code can be intercepted and exchanged by another app | Enforce PKCE S256 |
| Not checking state | Callback can be bound to a different transaction | Match random per-transaction state |
| Using the same redirect URI for multiple issuers | Increases authorization server mix-up risk | Use distinct paths per issuer |
| Not checking received callback URI | Response may arrive via a redirect differing from transaction | Store and match the sent URI |
| Using access token as ID Token | Token confusion and audience errors | Separate purposes and validation per token |

## 10. Testing Native Client Registration and PKCE

| # | Scenario | Expected Result |
|---|---|---|
| 1 | Native app registered with ClientAuthenticationMethod.NONE | Registration is treated as a public client |
| 2 | Native app sends a dummy client secret | Server does not treat embedded secret as confidential-client proof |
| 3 | Authorization Code request with PKCE S256 | Request succeeds if other validations pass |
| 4 | Client omits code_challenge | Rejected because client requires a proof key |
| 5 | Client sends wrong verifier when exchanging code | Token endpoint rejects |
| 6 | Client uses code_challenge_method=plain | Rejected if native app policy allows only S256 |
| 7 | Verifier shorter than 43 characters | Client test refuses to construct request; server tests PKCE validation |
| 8 | Verifier longer than 128 characters | Client test refuses to construct request; server rejects invalid value |
| 9 | Authorization response missing state | Native app rejects callback |
| 10 | State does not match pending transaction | Native app rejects callback |
| 11 | Callback URI differs from sent URI | Native app rejects response |
| 12 | Exact registered claimed HTTPS redirect | Redirects to valid app association |
| 13 | HTTPS redirect with different path | Authorization Server rejects |
| 14 | Valid reverse-domain private scheme | OS dispatches callback to app |
| 15 | Private scheme without dots | Registration policy rejects |
| 16 | Custom scheme also registered by another app | PKCE prevents app without verifier from exchanging code |
| 17 | Loopback IPv4 uses random port | Accepted if loopback port validator is configured |
| 18 | Loopback IPv6 uses random port | Accepted if validator supports ::1 |
| 19 | Loopback request uses localhost | Rejected per IP-literal-only policy |
| 20 | Loopback request uses LAN IP | Rejected |
| 21 | Loopback request alters path | Rejected |
| 22 | Loopback request adds user-info/query/fragment | Rejected per illustrative validator |
| 23 | Loopback request uses port 0 or out-of-range port | Rejected |
| 24 | URI has non-HTTP scheme in loopback branch | Rejected |
| 25 | Request uses unregistered redirect URI | Rejected with invalid_request |
| 26 | Client requests unregistered scope | Rejected with invalid_scope |
| 27 | OIDC request missing openid scope | Not processed as an OIDC Authentication Request |
| 28 | ID Token has wrong issuer | Native OIDC client rejects |
| 29 | ID Token audience does not contain client ID | Native OIDC client rejects |
| 30 | ID Token nonce mismatch | Native OIDC client rejects |
| 31 | Using embedded WebView for login | Security review flags RFC 8252 non-compliance |
| 32 | Callback listener binds 0.0.0.0 | Security test fails |
| 33 | Listener not closed after callback | Lifecycle test fails |
| 34 | Two authorization transactions run concurrently | State/verifier do not overwrite each other |
| 35 | Same app signs in with two issuers | Redirect URIs and transactions are separated per issuer |
| 36 | App logout | Local tokens/sessions are cleared per policy |
| 37 | App deprovisioned/revoked | API rejects token per revocation/expiry policy |
| 38 | Token/secret written to logs | Secret scanning or log assertions catch it |

### 10.1. Testing the Custom Loopback Validator

For the custom validator, write unit tests for each URI pair:

| Registered URI | Requested URI | Result |
|---|---|---|
| `http://127.0.0.1/oauth2/callback` | `http://127.0.0.1:51004/oauth2/callback` | Accept |
| `http://[::1]/oauth2/callback` | `http://[::1]:61023/oauth2/callback` | Accept |
| `http://127.0.0.1/oauth2/callback` | `http://127.0.0.1:51004/other` | Reject |
| `http://127.0.0.1/oauth2/callback` | `http://localhost:51004/oauth2/callback` | Reject |
| `http://127.0.0.1/oauth2/callback` | `http://192.168.1.10:51004/oauth2/callback` | Reject |
| `http://127.0.0.1/oauth2/callback` | `https://127.0.0.1:51004/oauth2/callback` | Reject |
| `http://127.0.0.1/oauth2/callback` | `http://127.0.0.1:51004/oauth2/callback?next=evil` | Reject |
| `http://127.0.0.1/oauth2/callback` | `http://127.0.0.1:0/oauth2/callback` | Reject |

Beyond unit tests, add integration tests for the Authorization Endpoint and Token Endpoint to verify that the exact same redirect URI is bound to the authorization code and token exchange.

## 11. Troubleshooting and Production Checklist

| Symptom | Possible Cause | Resolution |
|---|---|---|
| invalid_client | Client authentication method mismatches public registration | Use none; do not send a secret |
| invalid_request at authorization endpoint | Redirect URI mismatch or missing required parameter | Check registration, state, PKCE, and URI |
| invalid_grant at token endpoint | Code expired/already used, wrong redirect URI, or wrong verifier | Inspect transaction and send exact verifier |
| Dynamic loopback callback port rejected | SAS default exact match | Configure validator ignoring port only for loopback IP literals |
| HTTPS callback opens website instead of app | App association misconfigured | Check Digital Asset Links/Universal Links |
| Custom scheme opens wrong app | Scheme collision | Use reverse-domain scheme; prefer claimed HTTPS |
| Callback reaches app but transaction missing | State/session store lost or single global variable used | Use TTL-bounded transaction store supporting multiple flows |
| ID Token validation fails | Wrong issuer/JWK/audience/nonce | Check OIDC Discovery and transaction |
| Server does not issue refresh token | SAS public client policy | Design re-authentication or BFF; do not embed secrets |
| Token leaked via logs | Debug logging or callback logging | Redact queries/tokens and lower sensitive log levels |

### 11.1. Production Checklist

- [ ] Native app is registered as a public client with authentication method none.
- [ ] No client secret exists in source code, binary, mobile resources, or app configuration.
- [ ] Authorization Code Grant is used for interactive user login.
- [ ] PKCE is required in the client registration.
- [ ] Native client generates high-entropy verifiers and uses S256.
- [ ] An external user-agent is used for login; no embedded WebView is used.
- [ ] Redirect URI is chosen per platform: claimed HTTPS, reverse-domain private scheme, or loopback IP.
- [ ] Redirect URI has a specific path and is fully registered.
- [ ] Loopback binds only 127.0.0.1/::1, uses a dynamic port, and closes the listener after the flow.
- [ ] If supporting dynamic loopback ports, the validator ignores only the port and preserves all remaining URI components.
- [ ] If using PAR, the same redirect validation policy is enforced on the PAR endpoint.
- [ ] State, nonce, verifier, issuer, and redirect URI are stored per transaction.
- [ ] Callback validates state, URI, and errors before exchanging the code.
- [ ] Token endpoint receives the matching code_verifier; no client secret is sent.
- [ ] OIDC client validates signature, issuer, audience, expiry, and nonce.
- [ ] Access tokens are stored in memory or OS secure storage as needed.
- [ ] Tokens, codes, verifiers, and secrets never appear in logs/analytics/crash reports.
- [ ] Authorization Server refresh token behavior is verified in practice; never assume public clients receive refresh tokens.
- [ ] Tests cover callback collision, redirect mismatch, PKCE failure, multi-issuer, and concurrent logins.

**Self-Assessment Questions**

1. Why is a native app registered as a public client?
2. Why does a client secret embedded in a binary fail to prove client identity?
3. How does the Authorization Code Flow combined with PKCE protect native apps from code interception?
4. What are the three redirect URI types in RFC 8252?
5. Why are claimed HTTPS URIs preferred when supported by the platform?
6. Why should a private-use scheme be based on a reverse-domain name with only a single slash after the scheme?
7. Why does desktop loopback use an IP literal instead of localhost?
8. Why must the Authorization Server allow any port for loopback IP redirects?
9. Why does Spring Authorization Server 1.5.8 need a custom redirect validator for loopback ephemeral ports?
10. Which URI components must a loopback validator keep identical?
11. How do ClientAuthenticationMethod.NONE and requireProofKey(true) solve two different problems?
12. Why should Implicit Grant or embedded WebViews not be used for native login?
13. How do state, nonce, and code_verifier differ in role?
14. What must a native app verify before sending a code to the token endpoint?
15. Why are access tokens and ID Tokens not interchangeable?
16. Why should a Spring Authorization Server 1.5.8 public client not be assumed to receive a refresh token?
17. When an app supports multiple issuers, what should be done to reduce authorization server mix-up risk?

## References

- [RFC 8252 — OAuth 2.0 for Native Apps](https://www.rfc-editor.org/rfc/rfc8252.html): external user-agent, claimed HTTPS/private-use/loopback redirects, public client registration, and client authentication.
- [RFC 7636 — Proof Key for Code Exchange by OAuth Public Clients](https://www.rfc-editor.org/rfc/rfc7636.html): code verifier, S256 challenge, and token exchange.
- [RFC 9700 — Best Current Practice for OAuth 2.0 Security](https://www.rfc-editor.org/rfc/rfc9700.html): PKCE, redirect URIs, and protecting OAuth clients/authorization servers.
- [Spring Authorization Server 1.5.8 — How-to: Authenticate using a Single Page Application with PKCE](https://docs.spring.io/spring-authorization-server/reference/guides/how-to-pkce.html): public client, ClientAuthenticationMethod.NONE, requireProofKey, and token flow; the guide also notes refresh token restrictions for public clients.
- [Spring Authorization Server 1.5.8 — Protocol Endpoints](https://docs.spring.io/spring-authorization-server/reference/protocol-endpoints.html): authorization request validation, default redirect URI validation, and setAuthenticationValidator().
- [Spring Authorization Server 1.5.8 — Core Model / Components](https://docs.spring.io/spring-authorization-server/reference/core-model-components.html): RegisteredClient, redirect URI, client authentication method, scopes, and ClientSettings.
- [Android Developers — Verify Android App Links](https://developer.android.com/training/app-links/verify-android-applinks): verifying domain association for HTTPS app links.
- [Apple Developer — Supporting Associated Domains](https://developer.apple.com/documentation/xcode/supporting-associated-domains): configuring Universal Links and domain association.
- [AppAuth for Android](https://github.com/openid/AppAuth-Android) and [AppAuth for iOS](https://github.com/openid/AppAuth-iOS): native libraries supporting Authorization Code Flow, external user-agent, and PKCE.
