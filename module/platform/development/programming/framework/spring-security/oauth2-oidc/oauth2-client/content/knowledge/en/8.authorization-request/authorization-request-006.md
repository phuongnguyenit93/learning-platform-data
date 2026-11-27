# 8.6. Adding `nonce` for OIDC Requests

In the **OpenID Connect (OIDC) Authorization Code Flow**, a Spring Security application redirects the browser to the OpenID Provider (OP), receives an **authorization code** when the browser returns, exchanges the code for tokens, and validates the **ID Token** before logging the user in. An ID Token that is valid in signature and expiration does not by itself prove that the token belongs to **the exact pending login attempt**.

The **`nonce`** parameter solves a key part of this problem: the OIDC Client generates a unique value for the authorization request, sends it to the OP, and then requires the received **ID Token** to carry the corresponding value. When the client successfully validates this binding alongside other OIDC checks, the risk of reusing or substituting ID Tokens across authentication attempts is reduced.

This lesson covers how to **add, preserve, and verify `nonce`** in **Spring Boot 3.x / Spring Security 6.x with Servlet and `oauth2Login()`**, including both using the default resolver and customizing the authorization request. Notably, **Spring Security already supports `nonce` for OIDC login**: standard configurations typically do not require writing custom nonce generation code.

## 1. Where Does `nonce` Fit in the OIDC Flow?

A login flow can be illustrated as follows:

```mermaid
sequenceDiagram
    autonumber
    actor B as Browser
    participant C as Spring Security OIDC Client
    participant OP as OpenID Provider
    B->>C: GET /oauth2/authorization/academy
    Note over C: Create authorization request<br/>generate nonce and store context
    C-->>B: 302 to OP /authorize?...&nonce=N
    B->>OP: GET /authorize?...&nonce=N
    OP->>OP: Authenticate user
    OP-->>B: Redirect to callback with code and state
    B->>C: GET /login/oauth2/code/academy?code=...&state=...
    Note over C: Look up saved authorization request<br/>check response/request correlation
    C->>OP: POST /token (authorization code)
    OP-->>C: access_token + id_token
    Note over C: Validate ID Token and nonce<br/>against saved context
    C-->>B: Login succeeds; create/save Authentication
```

`nonce` appears in the **authorization request sent to the OP** and as a **claim in the ID Token**. It typically **does not appear as a callback parameter** in the Authorization Code Flow; the callback primarily carries `code` and `state`. In a server-side application, the Spring backend verifies `nonce` after exchanging the code and receiving the ID Token.

Abbreviated authorization request example:

```http
GET /authorize?response_type=code
    &client_id=academy-web
    &redirect_uri=https%3A%2F%2Fapp.example.com%2Flogin%2Foauth2%2Fcode%2Facademy
    &scope=openid%20profile
    &state=STATE_7b...
    &nonce=NONCE_b9... HTTP/1.1
Host: idp.example.com
```

The ID Token response, *with its payload decoded for illustration*, might contain:

```json
{
  "iss": "https://idp.example.com/realms/academy",
  "sub": "user-481",
  "aud": "academy-web",
  "iat": 1794800000,
  "exp": 1794800600,
  "nonce": "NONCE_b9..."
}
```

Values like `NONCE_b9...` are placeholders: in a real deployment you must use an unpredictable random string and follow Spring Security's nonce handling. Being able to decode a JWT payload does not establish authenticity; you must **verify the signature and claims** before trusting it.

## 2. What Does `nonce` Protect Against—and What Doesn't It?

### 2.1. Replay and ID Token Substitution Risks

Consider two login attempts:

- Attempt A uses nonce `N_A`; the client expects an ID Token with a nonce corresponding to `N_A`.
- Attempt B uses nonce `N_B`; the OP issues an ID Token for attempt B.

If attempt B's token were somehow fed into attempt A's verification step, the signature and `iss` might still be completely valid because both tokens were issued by the same OP. **A different nonce signals that token B was not created for request A.** The client must reject that token when the nonce does not match.

Note: `nonce` protects one binding of the authentication flow; it is **not a universal anti-replay mechanism across every layer**. If an attacker compromises an entire session/context and token, or bypasses verification logic, `nonce` alone cannot prevent all consequences.

### 2.2. Distinguishing `state`, `nonce`, and PKCE

Three values commonly coexist in the Authorization Code Flow:

| Characteristic | `state` | `nonce` | PKCE |
| --- | --- | --- | --- |
| Value sent by client in authorization request | `state` | `nonce` | `code_challenge` and `code_challenge_method` |
| Where the value is returned/checked | Callback carries `state`; client compares with saved request | ID Token carries `nonce` claim; client validates | Token request carries `code_verifier`; OP validates |
| Primary threat | Authorization response injected into wrong flow, login CSRF | ID Token not belonging to current authentication attempt, replay/substitution | Intercepted authorization code exchanged for tokens |
| Who performs the main check | OAuth2/OIDC Client | OIDC Client | Authorization Server |
| Can it replace an access token? | No | No | No |

An OIDC request can contain all three:

```text
GET /authorize
  ?response_type=code
  &client_id=academy-web
  &scope=openid%20profile
  &state=RANDOM_STATE
  &nonce=RANDOM_NONCE
  &code_challenge=CHALLENGE_S256
  &code_challenge_method=S256
```

`code_verifier` must be kept on the client for use at the token endpoint; never send the verifier on the front channel. A valid `state` does not permit skipping `nonce`, and a valid `nonce` does not replace PKCE or ID Token signature verification.

### 2.3. Does OIDC Require Sending `nonce`?

According to **OpenID Connect Core**, whether `nonce` is required depends on the response type/flow. For a pure **Authorization Code Flow** (response type `code`), the `nonce` parameter is **optional at the protocol level**; for certain flows returning tokens directly on the front channel, `nonce` is conditionally required by the specification.

However, **once the client sends `nonce`**, the OP must reflect the matching value in the ID Token and **the client must verify** that claim per OIDC rules. Since the practical goal is building a robust OIDC Client application, using `nonce` for the code flow is a sensible defense-in-depth measure.

Do not interpret "optional for the code flow" as "it is fine to accept any ID Token without tying it to the authentication session."

## 3. Properties of a Properly Generated `nonce`

A `nonce` is a string used to bind *a single authentication request* to its ID Token. It has these properties:

1. **Unpredictable:** use a cryptographically secure random generator (`SecureRandom` or the framework's secure mechanism), never timestamps, usernames, or counters.
2. **Fresh per request:** each OAuth2/OIDC login initiation has its own nonce; never reuse a fixed value application-wide or user-wide.
3. **Bound to request context:** the client stores the required value/representation in a trusted location to retrieve when the callback is processed.
4. **Short-lived:** pending callback data must expire and be cleaned up after completion or failure according to the repository mechanism.
5. **No sensitive business data:** never embed emails, client secrets, passwords, or access tokens in a nonce.
6. **Not an independent credential:** the browser can observe the nonce in the authorization redirect, so never treat a nonce as an authorization token.

Example of generating a URL-safe string to **understand the principle**:

```java
import java.security.SecureRandom;
import java.util.Base64;

public final class NonceGeneratorExample {
    private static final SecureRandom RANDOM = new SecureRandom();

    private NonceGeneratorExample() {}

    public static String newRandomNonce() {
        byte[] randomBytes = new byte[32];
        RANDOM.nextBytes(randomBytes);
        return Base64.getUrlEncoder()
                .withoutPadding()
                .encodeToString(randomBytes);
    }
}
```

Each call generates 32 random bytes encoded in unpadded Base64URL, typically 43 characters long. This is an **illustration of randomness**, not a reason to override Spring Security's built-in nonce handling. In an application using `oauth2Login()`, let Spring generate/store the nonce and verify it using the same convention.

### 3.1. Does `nonce` Need to Be Kept Secret Like a Client Secret?

No. In the Authorization Code Flow, `nonce` is sent in the authorization request URL to the OP and can be seen in the browser Network tab. It must be **unpredictable** so it cannot easily be precomputed for another authentication attempt, but it is not a long-lived secret like a client secret or refresh token.

Security comes from the **combination**: securely generated nonce, binding to the pending request, an ID Token signed by a trusted OP, and thorough validation by the client. Still, do not log nonces indiscriminately just because they are not long-lived credentials; login URLs can also carry other sensitive parameters.

## 4. Nonce Handling Flow in Spring Security Servlet

In a standard OAuth2 Login configuration, the participating components are:

| Spring Security Component | Responsibility Regarding `nonce` |
| --- | --- |
| `ClientRegistration` | Defines client, provider, and scopes. The `openid` scope activates OIDC login context. |
| `DefaultOAuth2AuthorizationRequestResolver` | Builds the authorization request; for OIDC, the framework supports adding `nonce` and related data. |
| `OAuth2AuthorizationRequest` | Holds parameters sent to the OP and internal attributes used to restore the request. |
| `OAuth2AuthorizationRequestRedirectFilter` | Calls the resolver, saves the authorization request, and redirects the browser to the OP. |
| `AuthorizationRequestRepository<OAuth2AuthorizationRequest>` | Stores the pending request awaiting callback, including correlation data needed for verification. |
| `HttpSessionOAuth2AuthorizationRequestRepository` | Common default repository in Servlet apps, storing authorization requests in the HTTP session. |
| `OAuth2LoginAuthenticationFilter` | Receives the callback, retrieves the authorization request, and delegates authentication to the manager/provider. |
| `OidcAuthorizationCodeAuthenticationProvider` | Handles the OIDC Authorization Code Flow and coordinates ID Token validation, including `nonce` when used. |
| `OidcUserService` | Builds the OIDC principal after relevant authentication data has been verified. |

### 4.1. When Does Spring Add `nonce` Automatically?

In common Spring Security OAuth2 Login setups, a **client registration with the `openid` scope** is treated as an OIDC request. The default resolver supports generating a `nonce` for OIDC authorization requests; the application usually does not need to declare a property like `nonce: true` in `application.yml`.

Registration example:

```yaml
spring:
  security:
    oauth2:
      client:
        registration:
          academy:
            provider: academy-oidc
            client-id: ${OIDC_CLIENT_ID}
            client-secret: ${OIDC_CLIENT_SECRET}
            authorization-grant-type: authorization_code
            scope:
              - openid
              - profile
            redirect-uri: "{baseUrl}/login/oauth2/code/{registrationId}"
        provider:
          academy-oidc:
            issuer-uri: ${OIDC_ISSUER_URI}
```

What to look for is that the authorization redirect contains `scope=openid...` and the `nonce` parameter. When using the default resolver, Spring Security takes care of retaining the nonce data needed for post-callback verification.

**Do not assume `nonce` is enabled merely because you manually appended `openid` to a URL.** If an application uses a custom `OAuth2AuthorizationRequestResolver` or builds authorization requests manually, custom code can accidentally bypass default handling.

### 4.2. Wire Nonce vs. Nonce in Attributes

An `OAuth2AuthorizationRequest` has two notable areas:

- **`additionalParameters`**: extra parameters included in the authorization request sent to the OP, such as the `nonce` parameter.
- **`attributes`**: internal auxiliary data attached to the request, not necessarily sent verbatim through the browser; used to retain data for callback verification.

In some Spring Security implementations, **the internally stored nonce representation differs from the nonce value sent on the wire**: for example, generating an original random string and using a hashed representation for the outgoing parameter; ID Token verification must apply **the exact matching convention**. That explains why manually putting a `nonce` into `additionalParameters` without updating internal context can cause failures, even if you see `nonce` appear in the browser.

**Safe rule:** never assume `attributes.get("nonce")` always equals the URL's `nonce` parameter byte-for-byte across all versions. Let the framework create and verify them through the same mechanism; whenever you must intervene, rely on the exact APIs and version in use.

### 4.3. `nonce` Passes Through `AuthorizationRequestRepository`

Before sending the redirect, Spring saves the authorization request in the repository. In the Servlet model, the HTTP session is the usual choice:

```text
Browser                                  Spring application
   |                                             |
   | GET /oauth2/authorization/academy           |
   |-------------------------------------------->|
   |                                             | Creates:
   |                                             |  - state
   |                                             |  - nonce data
   |                                             |  - PKCE data (if enabled)
   |                                             | Saves OAuth2AuthorizationRequest
   |<--------------------------------------------|
   | 302 to OP + session cookie                  |
   |                                             |
   | ... Browser authenticates at OP ...         |
   |                                             |
   | GET /login/oauth2/code/academy?code=&state= |
   | Cookie: JSESSIONID                           |
   |-------------------------------------------->|
   |                                             | Restores request
   |                                             | Passes data to OIDC provider
   |                                             | Validates ID Token/nonce
```

If the browser does not send back the matching session cookie or the session no longer holds the saved data, the application can fail **before reaching nonce verification**. You cannot recover the nonce by grabbing any value from the callback URL, because a normal code flow callback does not carry back the client-sent nonce.

For multi-instance applications, the session sharing or routing strategy must ensure the callback can locate the original request. For cross-site redirect callbacks, review `SameSite`, `Secure`, cookie domain/path, HTTPS, and reverse proxy configuration.

## 5. Minimal OIDC Client Configuration to Get `nonce`

### 5.1. Dependencies

Maven example with Spring Boot dependency management:

```xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-web</artifactId>
</dependency>
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-oauth2-client</artifactId>
</dependency>
```

With Gradle:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-oauth2-client'
}
```

### 5.2. Equivalent `application.properties`

If the project uses properties instead of YAML:

```properties
spring.security.oauth2.client.registration.academy.provider=academy-oidc
spring.security.oauth2.client.registration.academy.client-id=${OIDC_CLIENT_ID}
spring.security.oauth2.client.registration.academy.client-secret=${OIDC_CLIENT_SECRET}
spring.security.oauth2.client.registration.academy.authorization-grant-type=authorization_code
spring.security.oauth2.client.registration.academy.scope=openid,profile
spring.security.oauth2.client.registration.academy.redirect-uri={baseUrl}/login/oauth2/code/{registrationId}
spring.security.oauth2.client.provider.academy-oidc.issuer-uri=${OIDC_ISSUER_URI}
```

You only need **one of the two** equivalent configuration files—do not copy both with overlapping values. `OIDC_CLIENT_SECRET` should come from the environment or a secret manager. The issuer must be the real issuer published by the OP; the `idp.example.com` domain below is illustrative only:

```text
OIDC_CLIENT_ID=academy-web
OIDC_CLIENT_SECRET=<client-secret-value>
OIDC_ISSUER_URI=https://idp.example.com/realms/academy
```

At the OP, the corresponding callback must be allowed, for example:

```text
http://localhost:8080/login/oauth2/code/academy
```

Local development may use loopback HTTP per OP policy; production requires a properly configured HTTPS public URL.

### 5.3. `SecurityFilterChain`

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class SecurityConfig {

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http)
            throws Exception {

        http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/", "/error", "/assets/**").permitAll()
                .anyRequest().authenticated()
            )
            .oauth2Login(Customizer.withDefaults());

        return http.build();
    }
}
```

With this configuration, the browser can start login at:

```text
http://localhost:8080/oauth2/authorization/academy
```

When the request passes through the standard resolver, Spring automatically builds the OIDC authorization request with the required parameters. **You do not need to write a controller** for `/login/oauth2/code/academy` or manually append a nonce to the callback response.

## 6. Verifying That `nonce` Appears in the Authorization Request

### 6.1. Observing the Front Channel in a Browser

In a development environment:

1. Open Developer Tools → **Network**, and enable **Preserve log** to keep redirects.
2. Visit `http://localhost:8080/oauth2/authorization/academy`.
3. Locate the `302` response from the application and inspect the `Location` header pointing to the OP's authorization endpoint.
4. Open the URL or corresponding request and read the query parameters.
5. Confirm `scope` includes `openid` and that a `nonce` parameter is present in the authorization request.

Example parameters to look for (illustrative values):

```text
response_type=code
client_id=academy-web
redirect_uri=http://localhost:8080/login/oauth2/code/academy
scope=openid profile
state=5c92...
nonce=ad21...
```

If PKCE is enabled, you will also see:

```text
code_challenge_method=S256
code_challenge=<challenge>
```

Note that **`state` and `nonce` must be distinct in role**; never force them to be equal just for easier logging. Also do not assume every client uses the exact same nonce format when the framework may transform the value before sending it.

### 6.2. The Token Request Will Not Appear in the Browser

After the OP redirects the callback back to the application:

```text
GET /login/oauth2/code/academy?code=...&state=...
```

only then does the Spring backend call the Token Endpoint. The ID Token is usually returned on the **back channel**. Therefore, the browser's Network tab can show you the outgoing `nonce`, but **cannot directly show the ID Token payload received by the backend**, unless the app intentionally exposes tokens in a response—which is discouraged.

When verifying in development, inspect the login outcome and **credential-redacted** error logs. Avoid copying raw callback URLs (with `code`), session cookies, access/refresh tokens, or ID Tokens into public tickets.

## 7. If You Need Custom Parameters, Keep the Default `nonce`

Many real-world OIDC provider requirements are not about replacing `nonce`, but adding `prompt`, `login_hint`, `max_age`, or provider-specific parameters to the **authorization request**. In such cases, start from `DefaultOAuth2AuthorizationRequestResolver` and keep Spring's `nonce` rules intact.

Example adding `prompt=login` (asking the OP to consider re-authentication as supported by the OP):

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.oauth2.client.registration.ClientRegistrationRepository;
import org.springframework.security.oauth2.client.web.DefaultOAuth2AuthorizationRequestResolver;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class AuthorizationRequestConfig {

    @Bean
    SecurityFilterChain securityFilterChain(
            HttpSecurity http,
            ClientRegistrationRepository clientRegistrations)
            throws Exception {

        var resolver = new DefaultOAuth2AuthorizationRequestResolver(
                clientRegistrations,
                "/oauth2/authorization");

        resolver.setAuthorizationRequestCustomizer(builder ->
                builder.additionalParameters(parameters ->
                        parameters.put("prompt", "login")));

        http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/", "/error", "/assets/**").permitAll()
                .anyRequest().authenticated()
            )
            .oauth2Login(oauth2 -> oauth2
                .authorizationEndpoint(endpoint -> endpoint
                    .authorizationRequestResolver(resolver)));

        return http.build();
    }
}
```

This is an **alternative** to the `SecurityFilterChain` bean in the previous section; do not add both beans with the same default matcher in one application.

Why does this example relate to `nonce`? Because the standard resolver still handles the OIDC authorization request and its corresponding nonce data; the customizer merely adds another parameter. **You do not need to regenerate or overwrite `nonce` manually** just to add `prompt`. If adding another customizer for PKCE, preserve prior customizations and use supported APIs rather than building a brand-new request from scratch without context.

### 7.1. When You Must Wrap `OAuth2AuthorizationRequestResolver`

If your use case requires altering parameters per request (such as conditionally selecting an OP or a username hint), you can write a decorator around the standard resolver. The principle is:

```text
delegate.resolve(request)
         |
         v
Existing OAuth2AuthorizationRequest
  - state and correlation info
  - OIDC nonce and related attributes
  - PKCE if enabled
         |
         v
OAuth2AuthorizationRequest.from(original)
  - add/modify only needed business parameters
  - keep nonce, state, and PKCE data intact
         |
         v
Save to AuthorizationRequestRepository as before
```

Skeleton decorator example (business conditions omitted to focus on the mechanism):

```java
import jakarta.servlet.http.HttpServletRequest;
import org.springframework.security.oauth2.core.endpoint.OAuth2AuthorizationRequest;
import org.springframework.security.oauth2.client.web.OAuth2AuthorizationRequestResolver;

public final class PromptRequestResolver
        implements OAuth2AuthorizationRequestResolver {

    private final OAuth2AuthorizationRequestResolver delegate;

    public PromptRequestResolver(OAuth2AuthorizationRequestResolver delegate) {
        this.delegate = delegate;
    }

    @Override
    public OAuth2AuthorizationRequest resolve(HttpServletRequest request) {
        return withPrompt(delegate.resolve(request));
    }

    @Override
    public OAuth2AuthorizationRequest resolve(
            HttpServletRequest request,
            String clientRegistrationId) {
        return withPrompt(delegate.resolve(request, clientRegistrationId));
    }

    private OAuth2AuthorizationRequest withPrompt(
            OAuth2AuthorizationRequest original) {

        if (original == null) {
            return null;
        }

        return OAuth2AuthorizationRequest.from(original)
                .additionalParameters(params ->
                        params.put("prompt", "login"))
                .build();
    }
}
```

To use the decorator, configure `authorizationRequestResolver(new PromptRequestResolver(defaultResolver))` in `oauth2Login().authorizationEndpoint(...)`. This code uses `OAuth2AuthorizationRequest.from(original)` to preserve the existing request; if you construct a completely new authorization request yourself, you must preserve the redirect URI, state, nonce, PKCE, and registration metadata in full.

This is **an example of keeping `nonce` when adding parameters**, not advice forcing every project to write a custom resolver. For simple needs, a direct customizer as in section 7 is enough.

## 8. When You Truly Need to Generate `nonce` Manually

There are rare integration scenarios: a client not using the standard resolver, needing to build an authorization request outside the `oauth2Login()` path, or writing a Spring Security extension. In that case, adding `nonce` manually has four mandatory steps:

1. Generate a fresh nonce from a secure random source for **every** authorization request.
2. Put the outgoing nonce value into the **authorization request parameters** sent to the OP.
3. Save the correlation data in protected client context so it can be retrieved on callback.
4. After token exchange, verify the **`nonce` claim in the ID Token** against the exact value/representation the client sent, and reject the token if it mismatches or is missing when a nonce was sent.

```text
Client initiates login
    |
    +--> generate random nonce
    +--> prepare value to put in authorization URL
    +--> store nonce context for the flow
    |
    v
OP receives nonce at /authorize
    |
    +--> issues ID Token with matching nonce claim
    |
    v
Client receives ID Token after /token
    |
    +--> verify signature, iss, aud, exp ...
    +--> retrieve saved nonce data from current flow
    +--> check nonce claim
    |
    +--> mismatch/missing => reject login
    +--> valid + other checks valid => proceed to Authentication
```

**Do not simply add `parameters.put("nonce", random)`** in a completely custom resolver and assume Spring will remember that value for verification. Depending on how the OIDC verifier reads data, failing to store internal nonce state in the expected structure can cause verification to fail—or worse, silently drop the binding check.

### 8.1. Relationship Between Raw Nonce, Nonce Hash, and ID Token Claim

OIDC defines the logical relationship: **the ID Token's `nonce` claim must correspond to the `nonce` parameter in the authorization request**. OIDC itself does not mandate whether the client builds the parameter from raw random bytes or from a SHA-256 hash of a separate random string; that is a client implementation choice as long as the outgoing value is verified consistently.

Some Spring Security implementations use a convention similar to:

```text
rawNonce = secureRandom()
wireNonce = BASE64URL(SHA256(ASCII(rawNonce)))

Authorization request adds:
  nonce = wireNonce

Client temporary context stores:
  rawNonce

When ID Token is received:
  nonce claim must correspond to wireNonce
  and must be verified using the same convention
```

This describes a **possible implementation convention**, not a required API in every Spring Security release. Do not use this example to replace the default verifier without checking the exact source/APIs of your version.

If you must intervene due to a provider requirement, ensure **the outgoing value, stored value, and verification logic in the OIDC AuthenticationProvider are consistent**; avoid "quick fixes" that disable nonce validation when errors occur.

### 8.2. Do Not Turn `nonce` into Browser-Modifiable Data

A common design flaw:

```text
Browser redirect contains nonce=N_A
Callback contains code=...
Server reads nonce from an arbitrary query parameter sent by the browser
Server compares ID Token nonce against the value just submitted by the browser
```

If the server trusts a value supplied by the browser at callback without linking it to the saved authorization request, an adversary can alter the reference value as well. **The expected value must come from trusted state created at the start of the flow**, not arbitrarily accepted from the client at the end of the flow.

## 9. `nonce`, ID Token, and Other Mandatory Verification Steps

Even when `nonce` matches, the client must still validate the ID Token in full.

| Check | Why It Is Needed |
| --- | --- |
| Signature and algorithm | Ensures token contents were issued by a party holding a trusted signing key, using an allowed algorithm. |
| `iss` | Token must come from the exact OP configured for the authorization request. |
| `aud` | Token must be intended for the exact OAuth2 Client (`client_id`); check `azp` if applicable. |
| `exp` and appropriate time checks | Token must still be valid. |
| `nonce` | If the request sent a nonce, the ID Token must carry the value corresponding to that authentication attempt. |
| `auth_time`, `acr`, and required claims | Checked when business/protocol rules require specific freshness or authentication assurance levels. |

### 9.1. Why Not Parse the JWT Yourself and Check One Claim?

An error-prone example:

```java
// ILLUSTRATION OF WRONG APPROACH - DO NOT USE
String claimNonce = decodeJwtWithoutVerifyingSignature(idToken)
        .getClaim("nonce");
if (expectedNonce.equals(claimNonce)) {
    // Cannot conclude that the user is authenticated.
}
```

If you only Base64URL-decode the payload and read `nonce`, the client has not verified the signature or issuer. An attacker can craft a JWT string with any `nonce` claim without a valid OP signature. Therefore, **nonce validation must take place inside trusted ID Token verification**, never in place of it.

### 9.2. ID Token vs. Access Token

- **ID Token** lets the OIDC Client verify the authentication event and user identity; `nonce` belongs to this layer.
- **Access token** is used to access resource servers/APIs according to API policy. It may be a JWT or an opaque token.
- **Authorization code** is a temporary credential in the callback exchanged for tokens.
- **Session cookie** maintains the logged-in session with the Spring application.

Never read a `nonce` claim from an access token to decide whether a user logged in via OIDC. Never send an ID Token as a Bearer access token to an API just because the ID Token has a valid signature.

## 10. When Does `nonce` Get Lost or Mismatched?

### 10.1. Failure Because the Authorization Request Could Not Be Restored

A common case is when the browser returns with valid `code`/`state`, yet Spring cannot find the temporary authorization request. Then **no trusted nonce data remains** to compare against, and the flow must abort.

Possible causes include:

- The `JSESSIONID` session cookie was not sent back after redirect;
- The browser applied a `SameSite` policy incompatible with the response mode;
- The session expired while the user took a long time logging in;
- The app runs multiple instances without shared sessions;
- A reverse proxy produced a callback with a different hostname/scheme;
- A custom `AuthorizationRequestRepository` failed to store or restore required attributes;
- A newer authorization request overwrote an earlier one across concurrent tabs/flows.

Do not work around this by **generating a new nonce at callback**: a new nonce is not the nonce of the request sent to the OP.

### 10.2. Failure Because a Custom Resolver Overwrote `nonce`

Suppose the standard resolver generated a nonce, but a customizer wrote:

```java
// Only to illustrate a possible error; do not apply:
builder.additionalParameters(parameters ->
        parameters.put("nonce", "fixed-value-for-testing"));
```

Then the OP may echo `fixed-value-for-testing` in the ID Token, while the nonce context stored by Spring still tracks a different value. The result can be a **nonce mismatch**—or a security vulnerability if custom code also disables verification.

Another mistake is cloning the request by **copying only the URL**:

```text
Old request:
  authorizationUri + state + nonce + attributes + PKCE context

Wrong custom request:
  authorizationUri + state + nonce URL
  (loses internal attributes and PKCE context)
```

The right approach is to use the supported builder/copy mechanism or a customizer on the standard resolver. Never treat a URL string as a "copy" of `OAuth2AuthorizationRequest`.

### 10.3. Failure Because the OP Did Not Include `nonce` in the ID Token

If the authorization request included a `nonce` parameter, yet the returned ID Token lacks the corresponding claim, authentication must fail per OIDC rules. Check:

- What `nonce` parameter the authorization request URL actually sent;
- Which OP/realm/client was actually used;
- Whether the provider supports the proper OIDC flow and response type;
- Whether the received token is genuinely the ID Token from the current flow;
- Whether any middleware/proxy or customizer altered the authorization request.

Never add an "ignore nonce" flag to ID Token validation logic to bypass errors from a misconfigured OP.

### 10.4. Failure Due to Multiple Browser Tabs or Multiple Login Clicks

A user might start two logins:

```text
Tab A: state=S_A, nonce=N_A
Tab B: state=S_B, nonce=N_B
```

If the repository holds only **one** pending authorization request per session, request B can overwrite A. When A's callback arrives, Spring cannot find `S_A` and its corresponding `N_A` context. Your design must decide whether to support concurrency; if so, the repository must store requests distinctly, bound their lifetimes, and consume each safely.

Never share the same nonce between A and B to avoid multi-tab errors. Doing so defeats the purpose of binding a nonce to each individual authentication attempt.

## 11. Symptom-Based Diagnostic Table

| Symptom | Layer to Investigate First | How to Address |
| --- | --- | --- |
| Authorization redirect has no `nonce` | Registration/resolver | Does scope include `openid`? Is a custom resolver replacing the default? |
| Callback reports authorization request not found | Session/repository | Did the browser send the cookie? Are session timeout, multi-instance, `SameSite`, and callback host right? |
| Callback fails due to `state` | Authorization response correlation | Compare initiated flow with callback; avoid parallel logins or lost saved requests. |
| Token endpoint rejects with `invalid_grant` | Code exchange/PKCE | Check single-use code, redirect URI, client ID, and PKCE verifier; not yet an ID Token nonce error. |
| ID Token rejected due to nonce mismatch | OIDC ID Token validation | Compare actual authorization request, internal nonce context, OP, and customizer. |
| ID Token rejected due to `iss`/`aud` | Issuer/client registration | Confirm issuer metadata, client ID, and correct OP/tenant. |
| ID Token signature fails | JWKS/signature | Check signing keys, `kid`, CA/TLS, and allowed algorithms. |
| Login works locally, fails in production | Proxy/cookie/session | HTTPS, trusted forwarded headers, external redirect URI, `Secure`/`SameSite` cookies. |
| Login succeeds, but next request prompts for login | `SecurityContext`/session | Check context persistence, cookies, and session store. |
| After login, API returns `401` | Access token / Resource Server | Check token intended for the API, scope, audience, and API validation; nonce does not solve this. |

Exact error codes and exceptions depend on the Spring Security version, OAuth2 provider, and failure handler in use. An ID Token validation error may be wrapped in a generic exception; never build business logic on a hardcoded error message string.

## 12. Hands-On: Observing a Secure Flow

The goal of this exercise is to observe `nonce` at the right stage and confirm Spring establishes an OIDC login session after the OP verifies the user.

### Preparation

- A Spring Boot app with `spring-boot-starter-oauth2-client` and `oauth2Login()` on the security chain.
- An OP supporting OIDC Discovery with the proper redirect URI registered.
- The `openid` scope granted to the registration.
- `OIDC_CLIENT_ID`, `OIDC_CLIENT_SECRET`, and `OIDC_ISSUER_URI` populated with real values from a test environment.

### Execution

1. Open a fresh browser profile/private window and Developer Tools → Network.
2. Visit `/oauth2/authorization/academy`.
3. Observe the redirect to the OP and note the **presence** of `state`, `nonce`, and other OIDC parameters. Do not save raw nonces or tokens into reports.
4. Sign in with a test account at the OP. The browser returns to the callback carrying code/state.
5. If authentication succeeds, the app redirects the browser to the previously requested page or success URL; visit a protected endpoint to confirm the session.
6. Log out of the application, start a new flow, and observe a **new nonce**. Even if the OP still holds an SSO session and returns faster, the client should still create fresh login context.
7. If the app customizes the resolver, repeat the flow to confirm the `nonce` parameter is preserved on the authorization redirect and the callback completes.

### Illustrative Controller Reading the OIDC Principal

```java
import java.util.Map;
import org.springframework.security.core.annotation.AuthenticationPrincipal;
import org.springframework.security.oauth2.core.oidc.user.OidcUser;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class ProfileController {

    @GetMapping("/profile")
    public Map<String, String> profile(
            @AuthenticationPrincipal OidcUser user) {

        return Map.of(
            "subject", user.getSubject(),
            "displayName",
            user.getFullName() == null ? "(not provided)" : user.getFullName()
        );
    }
}
```

The controller does not check `nonce` itself, because **OIDC validation must finish before the principal is accepted**. The example assumes the endpoint is only for OIDC-authenticated users; if the app supports other login mechanisms, handle principal types appropriately.

## 13. Customization Pitfalls That Easily Go Wrong

### 13.1. Using a Fixed `nonce` for Easier Testing

```text
nonce = "123456"
```

A fixed value destroys the ability to distinguish authentication attempts. Use a fresh unpredictable nonce for every authorization request. Tests may swap the random source for a controlled component in test scope, but production must never use a fixed value.

### 13.2. Using a Username or Timestamp as `nonce`

```text
nonce = "alice-2026-11-16-09-00"
```

This information is predictable, can leak user data, and fails the goal of `nonce`. Use a CSPRNG instead of concatenating predictable human data.

### 13.3. Reading `nonce` from the Callback URL and Accepting It

In the Authorization Code Flow, the callback usually carries only `code` and `state`. If custom code reads a `nonce` query parameter on the callback and uses it as the expected nonce, that value can be altered by the browser or a third party. **The expected nonce must come from the saved request**, not a fresh parameter sent at the end of the flow.

### 13.4. Skipping Nonce Validation Because the ID Token "Already Has a Signature"

The signature proves the token was not tampered with externally and was signed by a trusted key; `nonce` proves the token belongs to the current authentication request. Both checks serve different purposes. When the request included a nonce, the corresponding claim must be verified.

### 13.5. Adding `nonce` Without Saving the Authorization Request

Putting `nonce` on the authorization redirect is only **half** of the feature. If the request repository does not store the correlation context, the client has no trusted expected nonce after callback. With Spring Security, keep the repository mechanism and the attributes generated by the resolver.

### 13.6. Merging `state` and `nonce` into a Single Variable

Technically both can be random values, yet **their semantics and verification points differ**. Never use a customizer to force them to be identical or assume that checking `state` automatically satisfies `nonce` verification. Keep the framework's separate management.

### 13.7. Disabling CSRF Application-Wide Because OIDC Callback Fails

`state`, `nonce`, and PKCE are OAuth2/OIDC flow protections; a Servlet application's CSRF token protects session-cookie-authenticated state-changing requests. Never disable `csrf()` broadly just to make the callback work; analyze the HTTP method, cookie policy, callback matcher, and authorization request storage instead.

## 14. Extension Considerations

### 14.1. Multiple OpenID Providers

If an application allows sign-in via `academy` and `corporate`, each authorization request must be bound to the **exact `ClientRegistration`/issuer**. `nonce` helps link an ID Token to a login request, but does not replace checking `iss`, `aud`, and mix-up mitigations across multiple OPs.

For instance, the same `sub` string from two different issuers does not necessarily refer to the same person. When mapping accounts, typically use the `(issuer, subject)` pair rather than trusting `sub` or `email` alone.

### 14.2. OIDC Logout and Re-Login

Logging out of the Spring session does not necessarily clear the OP's SSO cookie. The next login may not prompt for a password, yet it is still **a new authorization request** and must carry fresh correlation data. `nonce` does not log out of the OP or revoke access/refresh tokens.

OIDC RP-Initiated Logout, when supported, is a separate mechanism and may require additional configuration.

### 14.3. Requests Carrying `prompt=none`

An application may ask the OP to authenticate silently with `prompt=none` if an SSO session already exists. Even without a login screen, it is still a fresh authorization request; `nonce` must still be managed independently and matched against the resulting ID Token. If the OP cannot satisfy it, it may return an OAuth2/OIDC error instead of a code.

### 14.4. `max_age` and `auth_time`

When business logic needs to ensure the user authenticated recently, you can add `max_age` to the authorization request and check `auth_time` in the ID Token per OIDC requirements. These parameters/claims play a **different role from `nonce`**: `nonce` binds the token to the request, whereas `max_age` relates to authentication recency.

### 14.5. Multiple Instances and Distributed Sessions

If the authorization request and nonce live in a single JVM's HTTP session, a callback routed to another instance may fail to restore the request. Depending on architecture, use sticky sessions or Spring Session with a distributed store. Protect and bound the lifetime of session data since it holds sensitive protocol context.

## 15. Self-Check Questions

**Q1 — Nonce on callback.** After the user logs in at the OP, the callback only has `code` and `state`. Did the OP forget to return `nonce`?

> No. In the Authorization Code Flow, `nonce` is sent in the authorization request and reflected in the **ID Token** received in the token response, not required as a callback query parameter.

**Q2 — Already using `state`, do we still need `nonce`?** The client verified `state` successfully, then receives an ID Token whose `nonce` differs from the sent request.

> Reject the ID Token. `state` protects authorization response binding; `nonce` protects ID Token binding to the authentication attempt.

**Q3 — Valid ID Token signature but wrong `nonce`.** Can the application just log a warning and allow login since the token hasn't expired?

> No. When the client sent a nonce, a mismatch violates OIDC binding requirements; a login session must not be established from that token.

**Q4 — Do you need to write a custom nonce generator to use `oauth2Login()`?**

> Usually no. With a standard OIDC registration and the default resolver, Spring Security supports `nonce`. Configure the `openid` scope properly, keep the default resolver/repository/token validation intact, and observe a request to confirm behavior.

**Q5 — Custom resolver drops `nonce`.** You replace the standard resolver with custom code building a login URL from `client_id`, `scope`, and `redirect_uri`. Login then fails ID Token validation.

> The custom resolver likely omitted required nonce/state/PKCE data. Extend the standard resolver and preserve `OAuth2AuthorizationRequest` and its attributes instead of constructing a context-free URL.

**Q6 — Generating a new `nonce` at callback time.** Why shouldn't you generate a nonce when receiving the code?

> The OP already received a nonce **earlier** in the authorization request; a newly generated nonce is unrelated to the token issued for the initial request. It is not an authentic reference value.

**Q7 — `nonce` and access tokens.** Should `nonce` be sent instead of `Authorization: Bearer <access_token>` when calling an API?

> No. `nonce` is an OIDC login binding; APIs normally require an access token matching the issuer, audience, scopes, and resource server policy.

## 16. Remembering the Nonce Addition Flow

```text
ClientRegistration with scope openid
          |
          v
DefaultOAuth2AuthorizationRequestResolver
  - builds OIDC authorization request
  - generates and adds nonce per framework convention
  - retains needed info in request attributes
          |
          v
AuthorizationRequestRepository saves request
          |
          v
Browser redirects to OP
  - authorization request contains nonce
          |
          v
OP issues ID Token with matching nonce
          |
          v
OAuth2LoginAuthenticationFilter receives callback
  - restores authorization request
          |
          v
OIDC AuthenticationProvider validates ID Token
  - signature / issuer / audience / time
  - nonce against saved request
          |
          v
Creates OidcUser, OAuth2AuthenticationToken
and saves SecurityContext per configuration
```

In a Servlet application using Spring Security, the most reliable starting point is **configuring an OIDC Client with the `openid` scope and using the default resolver**. If you need to add parameters to the authorization request, extend the standard resolver to preserve the nonce mechanism. If you genuinely must generate `nonce` manually, synchronize **the value sent to the OP, the data stored on the client, and ID Token validation**—never simply add a query parameter and skip verification.

### References

- [OpenID Connect Core 1.0 — Authentication Request and ID Token](https://openid.net/specs/openid-connect-core-1_0.html).
- [OpenID Connect Core 1.0 — ID Token Validation](https://openid.net/specs/openid-connect-core-1_0.html#IDTokenValidation).
- [Spring Security Reference — OAuth 2.0 Login](https://docs.spring.io/spring-security/reference/servlet/oauth2/login/index.html).
- [Spring Security Reference — Advanced OAuth 2.0 Login Configuration](https://docs.spring.io/spring-security/reference/servlet/oauth2/login/advanced.html).
- [Spring Security API — DefaultOAuth2AuthorizationRequestResolver](https://docs.spring.io/spring-security/site/docs/current/api/org/springframework/security/oauth2/client/web/DefaultOAuth2AuthorizationRequestResolver.html).
- [Spring Security API — OAuth2AuthorizationRequest](https://docs.spring.io/spring-security/site/docs/current/api/org/springframework/security/oauth2/core/endpoint/OAuth2AuthorizationRequest.html).
- [Spring Security API — OidcAuthorizationCodeAuthenticationProvider](https://docs.spring.io/spring-security/site/docs/current/api/org/springframework/security/oauth2/client/oidc/authentication/OidcAuthorizationCodeAuthenticationProvider.html).
- [RFC 6749 — OAuth 2.0 Authorization Framework](https://www.rfc-editor.org/rfc/rfc6749).
- [RFC 9700 — OAuth 2.0 Security Best Current Practice](https://www.rfc-editor.org/rfc/rfc9700).
