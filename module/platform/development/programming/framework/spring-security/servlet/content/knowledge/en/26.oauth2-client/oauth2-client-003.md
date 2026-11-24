# Authorization Code, `state`, PKCE, and `nonce` in OAuth2 Client — Spring Security Servlet

## 1. Objectives and context

In a **Spring Security Servlet** application, an OAuth2 Client allows a user to initiate login or authorization via an Authorization Server (identity provider), receive an **authorization code** through the browser, and then use a back-channel call to exchange the code for tokens. With OpenID Connect (OIDC), this flow can also receive an **ID Token** for authenticating the user's identity.

Three easily confused values in the flow are:

- **`state`**: binds the *authorization response* to the request initiated by the client, mitigating CSRF/callback confusion.
- **PKCE** (`code_verifier`, `code_challenge`): binds the *authorization code* to the client instance that initiated the request, making a stolen code harder to exchange for tokens.
- **`nonce`**: in **OIDC**, binds the **ID Token** to the corresponding authentication request, helping detect replayed or swapped ID Tokens; it does not apply by default to plain OAuth2 flows without OIDC.

This article focuses on **Authorization Code** in server-side applications using **Spring Boot 3.x, Spring Security 6.x, Java 17+, Spring MVC/Servlet**. Example Identity Provider (IdP) URLs/issuers are illustrative addresses; to run end-to-end login, you must replace them with a real IdP and register the exact client/redirect URI.

First, it is important to distinguish two purposes:

| Purpose | Standard/model | Key outcome |
| --- | --- | --- |
| Let an application access resources on behalf of a user | OAuth 2.0 Authorization Code | Access token (possibly with refresh token), granted permission scopes |
| Log in and authenticate a user's identity | OpenID Connect on OAuth 2.0 | ID Token alongside other tokens; verified identity information |
| Backend API validating Bearer tokens from calling clients | OAuth2 Resource Server | Validates the received token; a different responsibility from OAuth2 Client |

**An access token is not an ID Token**: an access token has the audience/usage context of a resource server; do not infer identity by decoding an access token yourself. An ID Token is used by the client to confirm OIDC login; do not send an ID Token as an access token to an API.

## 2. Actors, endpoints, and transmitted data

The Authorization Code flow involves four roles:

1. **Resource Owner / user** using a browser.
2. **User-Agent / browser** following redirects.
3. **OAuth2 Client / Spring Security application** initiating the authorization request, keeping correlation data in the session, and calling the token endpoint server-side.
4. **Authorization Server / IdP** authenticating the user, obtaining consent when needed, and issuing codes and tokens; the Resource Server is the party receiving the access token when an API is called.

Example URLs (replace according to your IdP and deployment):

```text
Spring application:       https://app.example.test
Start OAuth2 login:       GET /oauth2/authorization/learning-idp
Authorization endpoint:   https://idp.example.test/oauth2/authorize
Callback received by Spring: GET /login/oauth2/code/learning-idp
Token endpoint:           https://idp.example.test/oauth2/token
```

`learning-idp` is a **registrationId** in Spring Security, not a standard parameter that the IdP is required to know. The initiation and callback URLs above are **common defaults** of Spring Security OAuth2 Login Servlet; they can be customized, in which case matching configuration must be updated on both the client and the IdP.

### 2.1. End-to-end sequence

```mermaid
sequenceDiagram
    participant B as Browser
    participant C as Spring OAuth2 Client
    participant A as Authorization Server / IdP

    B->>C: GET /oauth2/authorization/learning-idp
    C->>C: Generate state, PKCE verifier/challenge; nonce if OIDC
    C->>C: Save authorization request in session
    C-->>B: 302 to authorization endpoint (state, challenge, nonce)
    B->>A: GET /authorize
    A->>B: Login / consent (if needed)
    A-->>B: 302 to redirect_uri?code=...&state=...
    B->>C: GET /login/oauth2/code/learning-idp?code=...&state=...
    C->>C: Look up saved request; match state
    C->>A: POST /token (code, redirect_uri, code_verifier)
    A->>A: Verify code, client, redirect_uri, PKCE
    A-->>C: access_token; id_token if OIDC
    C->>C: Verify token; nonce in ID Token if sent
    C-->>B: Login session and post-success redirect
```

No step requires frontend JavaScript to **hold `client_secret` or `code_verifier`** in this server-side model. The browser sees the authorization request and the callback containing the code; the token exchange happens server-to-server. HTTPS and log/referrer controls remain important because authorization codes and tokens are sensitive data.

## 3. Step 1: Creating the authorization request

The user clicks a login button going to `GET /oauth2/authorization/learning-idp`. Spring Security selects the corresponding `ClientRegistration` and builds an authorization request. With code flow + PKCE + OIDC, the URL going to the IdP typically includes these fields:

```http
GET /oauth2/authorize?
  response_type=code&
  client_id=learning-client&
  redirect_uri=https%3A%2F%2Fapp.example.test%2Flogin%2Foauth2%2Fcode%2Flearning-idp&
  scope=openid%20profile&
  state=<random-state>&
  code_challenge=<base64url-sha256-verifier>&
  code_challenge_method=S256&
  nonce=<random-oidc-nonce> HTTP/1.1
Host: idp.example.test
```

*The snippet above is wrapped across lines for readability, not a literal HTTP request to copy and run.* In a real URL, query parameters are properly URL-encoded. `state`, challenge, and nonce are distinct strings; for example, do not use the literal `<random-state>` as a real value.

Meaning of each field:

- `response_type=code`: the client requests an authorization code instead of a token returned directly on the front channel.
- `client_id`: client ID registered with the IdP; **not a secret**.
- `redirect_uri`: callback URI that must match what is registered at the Authorization Server. Do not take this value from an untrusted URL and forward it arbitrarily.
- `scope`: requested permissions/claim groups. Having `openid` makes this an OIDC request; for example, `profile` adds profile info depending on IdP policy.
- `state`: unpredictable string generated and stored by the client to match against the response.
- `code_challenge` + `code_challenge_method=S256`: PKCE proof derived from `code_verifier`. **Never send `code_verifier` in the authorization URL**.
- `nonce`: **OIDC** parameter; when used, it must be stored and verified against the ID Token's `nonce` claim. Plain OAuth2 flows do not request an ID Token and therefore do not apply the OIDC nonce verification step.

Spring Security Servlet usually stores the **authorization request and correlation data** in `HttpSessionOAuth2AuthorizationRequestRepository`. Consequently, the browser must preserve the exact session cookie until the callback. A stateless design without sessions must build another secure repository/state mechanism; do not remove state storage and expect the callback to still work.

## 4. Step 2: IdP authenticates and redirects back to the client

After the user logs in and consents if required, the Authorization Server creates a **short-lived, single-use authorization code**, then redirects the browser to the registered URI with code and state:

```http
HTTP/1.1 302 Found
Location: https://app.example.test/login/oauth2/code/learning-idp?code=<one-time-code>&state=<same-state>
```

The client must verify that the callback matches an authorization request it initiated: same session, matching `state`, matching IdP/client registration, and stored details. **Never** exchange a code without a valid correlation state for tokens just to "try and see if it works."

If the user denies consent or an error occurs, the callback may carry `error` and `state` instead of `code`; this is a failure branch that must be handled and logged safely. An IdP redirect does not prove a code is valid until the client completes verification and token exchange.

**Why must `state` be stored on the server?** If the client merely reads `state` from the query and compares it against a value sent in the callback itself, the check is meaningless. The value must be generated beforehand, bound to the transaction, and kept where an attacker cannot manipulate it.

## 5. Step 3: Back-channel token exchange and PKCE

Once the callback is valid, the client sends the authorization code to the **token endpoint** over a server-to-server channel, along with the `code_verifier` kept from the initiation step:

```http
POST /oauth2/token HTTP/1.1
Host: idp.example.test
Content-Type: application/x-www-form-urlencoded

grant_type=authorization_code&code=<one-time-code>&redirect_uri=https%3A%2F%2Fapp.example.test%2Flogin%2Foauth2%2Fcode%2Flearning-idp&code_verifier=<original-verifier>
```

This HTTP snippet illustrates the essential parameters; a **confidential client** must also authenticate to the token endpoint according to its configured `client-authentication-method`, such as HTTP Basic or `private_key_jwt`. Public clients without a secret must rely on appropriate mechanisms including PKCE. Never place `client_secret` in URLs, browsers, or shared documents.

The Authorization Server must match the code against the client/redirect URI and, when the authorization request included PKCE, verify:

```text
BASE64URL-ENCODE(SHA256(ASCII(code_verifier))) == stored code_challenge
```

With PKCE `S256`, `code_verifier` is a random string from the URL-safe character set (RFC 7636 requires 43–128 valid characters). `code_challenge` in the initial request is the hashed and base64url-encoded result **without padding**. Do not pick a short, predictable `code_verifier`, or reuse a single verifier across multiple transactions.

Another request that only steals the authorization code **without the right verifier** cannot exchange the code for tokens if the Authorization Server implements PKCE properly. PKCE does not replace state checking on the callback, does not replace client authentication for confidential clients, and does not eliminate verification of redirect URI, tokens, TLS, or user permissions.

### 5.1. Standalone Java 17+ PKCE demo

The following **`PkceExample.java`** file uses only the Java standard library. It verifies the public RFC 7636 test vector and generates a new verifier from 32 bytes via `SecureRandom` (256 bits of entropy):

```java
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.security.SecureRandom;
import java.util.Base64;

public class PkceExample {
    static String challengeS256(String verifier) throws Exception {
        byte[] digest = MessageDigest.getInstance("SHA-256")
            .digest(verifier.getBytes(StandardCharsets.US_ASCII));
        return Base64.getUrlEncoder()
            .withoutPadding()
            .encodeToString(digest);
    }

    static String newVerifier() {
        byte[] random = new byte[32];
        new SecureRandom().nextBytes(random);
        return Base64.getUrlEncoder()
            .withoutPadding()
            .encodeToString(random);
    }

    public static void main(String[] args) throws Exception {
        String rfcVerifier =
            "dBjftJeZ4CVP-mB92K27uhbUJU1p1r_wW1gFWFOEjXk";
        String rfcChallenge =
            "E9Melhoa2OwvFrEMTJguCHaoeK1t8URWbuGJSstw-cM";
        System.out.println("RFC 7636 matches: "
            + challengeS256(rfcVerifier).equals(rfcChallenge));

        String verifier = newVerifier();
        System.out.println("Verifier length: " + verifier.length());
        System.out.println("Challenge length: "
            + challengeS256(verifier).length());
    }
}
```

Compile and run:

```bash
javac PkceExample.java
java PkceExample
```

Exact stdout (the random strings are not printed):

```text
RFC 7636 matches: true
Verifier length: 43
Challenge length: 43
```

32 bytes base64url-encoded without padding always produces 43 characters, so the output length is deterministic; **the actual verifier/challenge values change on every run**. This is a PKCE algorithm demo, not a full OAuth2 Client. When using Spring Security, let the framework generate and store the verifier; never hard-code a test vector as a user's verifier.

## 6. `state`, PKCE, and `nonce`: three distinct verification targets

| Component | Where is it generated/stored? | Which requests carry it? | Where is it verified? | Primary protection |
| --- | --- | --- | --- | --- |
| `state` | Client generates randomly, keeps with authorization request in session/correlation store | Authorization request and callback | Client compares callback state against saved transaction | Prevents unsolicited callback/login CSRF and transaction mix-ups |
| PKCE verifier/challenge | Client generates `code_verifier`, keeps secret; sends `code_challenge=S256(verifier)` | Challenge in authorization request; verifier only in token request | Authorization Server checks verifier matching the code | Mitigates exchanging a stolen code for tokens |
| OIDC `nonce` | OIDC client generates, stores in transaction | Nonce in authentication request; value bound in ID Token | Client checks ID Token nonce when request had nonce | Prevents ID Token replay/substitution in a login transaction |

### 6.1. Distinct security questions

- **`state`** answers: "Does this callback belong to the authorization request that this client/session just initiated?"
- **PKCE** answers: "Does the party exchanging the code possess the code verifier committed to when requesting the code?"
- **OIDC `nonce`** answers: "Does the returned ID Token match the authentication request that carried this nonce?"

For example, a successful PKCE check does not by itself prove the response arrived at the right browser session. Conversely, a valid `state` does not prevent an exposed authorization code from being exchanged for tokens if the Authorization Server lacks PKCE. Use **both state and PKCE** when appropriate, as each mitigates a different risk.

### 6.2. When is nonce needed?

**Plain OAuth2** (scope without `openid`, aiming to access APIs) does not receive a standard OIDC ID Token, so there is no nonce claim in an ID Token to verify. Do not confuse nonce with a form CSRF token or with OAuth2 `state`.

**OIDC Authorization Code** (scope includes `openid` and OIDC-compliant IdP) returns an ID Token. Per OIDC Core, the `nonce` parameter **is not strictly mandatory in every Authorization Code request**, but when the client sends a nonce, the returned ID Token must contain a matching nonce and the client must verify it. Some other OIDC flows have stricter nonce rules. In a Spring Security OIDC login app, let the framework manage nonce by default if applicable, and preserve validation if customizing requests or token processing.

A nonce must be randomly generated, bound to the **exact login transaction**, and not reused as a fixed application-wide value. Do not substitute `state` for `nonce` and do not compare it against an access token. Beyond `nonce`, the ID Token still needs verification of **signature (or equivalent protection), issuer, audience, expiration**, and related constraints like `azp` when applicable. Spring Security OIDC login provides standard validators; do not omit them when writing custom flows.

## 7. Configuring Spring Security Servlet for Authorization Code + PKCE

The following example illustrates **OIDC login** via Authorization Code on server-side Spring Boot. It uses the framework's `state`/authorization-request repository and **explicitly enables PKCE S256** via `OAuth2AuthorizationRequestCustomizers.withPkce()`.

### 7.1. Dependencies and client registration

In a Spring Boot 3.x, Java 17+ project created with Spring Initializr, add the following Gradle Groovy dependencies; plugins, versions, and dependency management belong to the root project:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-security'
    implementation 'org.springframework.boot:spring-boot-starter-oauth2-client'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-test'
}
```

Sample **`src/main/resources/application.yml`**:

```yaml
spring:
  security:
    oauth2:
      client:
        registration:
          learning-idp:
            provider: learning-idp
            client-id: ${OAUTH_CLIENT_ID}
            client-secret: ${OAUTH_CLIENT_SECRET}
            client-authentication-method: client_secret_basic
            authorization-grant-type: authorization_code
            redirect-uri: "{baseUrl}/login/oauth2/code/{registrationId}"
            scope:
              - openid
              - profile
        provider:
          learning-idp:
            issuer-uri: https://idp.example.test/realms/learning
```

**You must replace `issuer-uri` with an OIDC issuer that has a working discovery endpoint**, set `OAUTH_CLIENT_ID` and `OAUTH_CLIENT_SECRET` via your environment's secret manager/env vars, and register the callback matching the real URI at the IdP (e.g. `http://localhost:8080/login/oauth2/code/learning-idp` when testing locally if permitted by the IdP). This is a **confidential server-side client** configuration using a client secret; public clients must not copy this approach verbatim. `issuer-uri` allows Spring to fetch endpoints and verification keys from the IdP's OIDC metadata.

`scope: openid, profile` makes the login flow use OIDC and yield an ID Token. If you switch to plain OAuth2 (without `openid`), you cannot assume the controller receives an `OidcUser`, nor will there be a nonce/ID Token.

### 7.2. Main class

File **`src/main/java/com/example/oauthflow/OAuthFlowApplication.java`**:

```java
package com.example.oauthflow;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class OAuthFlowApplication {
    public static void main(String[] args) {
        SpringApplication.run(OAuthFlowApplication.class, args);
    }
}
```

### 7.3. SecurityFilterChain and PKCE

File **`src/main/java/com/example/oauthflow/SecurityConfig.java`**:

```java
package com.example.oauthflow;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.oauth2.client.registration.ClientRegistrationRepository;
import org.springframework.security.oauth2.client.web.DefaultOAuth2AuthorizationRequestResolver;
import org.springframework.security.oauth2.client.web.OAuth2AuthorizationRequestCustomizers;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class SecurityConfig {
    @Bean
    SecurityFilterChain securityFilterChain(
            HttpSecurity http,
            ClientRegistrationRepository registrations) throws Exception {

        DefaultOAuth2AuthorizationRequestResolver resolver =
            new DefaultOAuth2AuthorizationRequestResolver(
                registrations, "/oauth2/authorization");

        // Also enable PKCE for the confidential client in this example.
        resolver.setAuthorizationRequestCustomizer(
            OAuth2AuthorizationRequestCustomizers.withPkce());

        http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/", "/error").permitAll()
                .anyRequest().authenticated()
            )
            .oauth2Login(login -> login
                .authorizationEndpoint(endpoint ->
                    endpoint.authorizationRequestResolver(resolver)
                )
            );

        return http.build();
    }
}
```

`DefaultOAuth2AuthorizationRequestResolver` builds the authorization URL, including `state` and required attributes; the PKCE customizer generates the **code challenge** and keeps the **verifier** in the authorization request for use during token exchange. In many Spring Security versions, PKCE may be enabled by default for public clients with `ClientAuthenticationMethod.NONE`; the config above explicitly enables it **for the confidential client as well**.

`oauth2Login()` attaches the login authorization-code flow to the Servlet filter chain. When you need to use the access token to call other APIs on the user's behalf, look into OAuth2 Authorized Client (`OAuth2AuthorizedClientManager`, `oauth2Client`) and an appropriate token storage mechanism; that is a separate concern, not a reason to grab tokens from callback query parameters yourself.

**Do not write your own controller handling `/login/oauth2/code/learning-idp`** in this setup: Spring Security's `OAuth2LoginAuthenticationFilter` processes the callback, verifies the authorization request/state, and executes the exchange/authentication. Do not expose a public GET callback with a custom handler that bypasses the default validations.

### 7.4. Test login page

File **`src/main/java/com/example/oauthflow/MeController.java`**:

```java
package com.example.oauthflow;

import java.util.Map;

import org.springframework.http.MediaType;
import org.springframework.security.core.annotation.AuthenticationPrincipal;
import org.springframework.security.oauth2.core.oidc.user.OidcUser;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class MeController {
    @GetMapping(value = "/", produces = MediaType.TEXT_HTML_VALUE)
    String home() {
        return """
            <!doctype html>
            <html lang="en">
            <head><meta charset="utf-8"><title>OIDC Login Demo</title></head>
            <body>
                <h1>OIDC Login Demo</h1>
                <a href="/oauth2/authorization/learning-idp">
                    Sign in via Identity Provider
                </a>
            </body>
            </html>
            """;
    }

    @GetMapping("/me")
    Map<String, String> me(@AuthenticationPrincipal OidcUser user) {
        return Map.of("subject", user.getSubject());
    }
}
```

`/` is accessible when unauthenticated; the link sends the browser to the login-initiating filter. `/me` requires authentication and in an **OIDC configuration** returns the user's `sub` (subject identifier) without exposing tokens in the response. For an OAuth2 provider that does not support OIDC, use the appropriate principal type instead of forcing `OidcUser`.

Run from the project's Gradle Wrapper:

```bash
./gradlew bootRun
```

On Windows PowerShell, use `.\gradlew.bat bootRun`. Only run end-to-end after configuring a **real IdP, redirect URI, and valid environment variables**. With the dummy issuer `idp.example.test`, there is no real login session and no login stdout is guaranteed.

### 7.5. Observing points in the flow

In DevTools → Network (Preserve log), start at `/oauth2/authorization/learning-idp`:

1. Inspect the app's 302 response. The IdP URL must include `response_type=code`, `client_id`, `redirect_uri`, `state`; after enabling PKCE, you should see `code_challenge_method=S256` and `code_challenge`. With OIDC and the appropriate request handler, `nonce` may also appear.
2. Authenticate at the IdP; the browser receives the callback with `code` and `state` (or `error` on failure). Verify the callback state matches the initiating request, and do not copy this value into another session.
3. Token exchange normally runs on the **server**, so browser DevTools does not show the `code_verifier` sent to the token endpoint. Do not move the verifier to client-side JavaScript just because you "cannot see it."
4. When successful, the browser holds an app session and `/me` returns the corresponding OIDC subject. When failing, read Spring Security logs (with sensitive data filtered) and IdP logs rather than printing codes, tokens, or secrets into logs.

Most OAuth2 redirects happen via **top-level GET**. If using another callback mode such as OIDC `response_mode=form_post`, carefully review cookie `SameSite` and CSRF on the callback endpoint: a cross-site POST may omit session cookies when `SameSite=Lax`. Do not loosen cookie policies blindly; analyze how the IdP delivers callbacks and the HTTPS path.

## 8. Token exchange, session, and security behind a proxy

### 8.1. Default Spring Security responsibilities

For OAuth2 Login Servlet, the core components are:

| Component | Role |
| --- | --- |
| `OAuth2AuthorizationRequestRedirectFilter` | Handles the initiation request and redirects the browser to the Authorization Server |
| `DefaultOAuth2AuthorizationRequestResolver` | Builds the authorization request from `ClientRegistration`, state, and custom parameters |
| `HttpSessionOAuth2AuthorizationRequestRepository` | By default retains the authorization request between redirect and callback to verify correlation |
| `OAuth2LoginAuthenticationFilter` | Receives the callback, retrieves the saved authorization request, and starts authentication |
| `OAuth2AccessTokenResponseClient` and corresponding provider | Exchanges the code for tokens per client/provider configuration |
| Spring Security OIDC provider/validator | Validates the ID Token, including nonce when included in the authentication request |

The flow can differ when replacing the authentication filter, using a custom authorization request repository, or using a custom token response client. When customizing, you must preserve the properties that **state is saved beforehand and checked once**, the verifier matches the code challenge, and the ID Token is verified.

### 8.2. HTTP session and cookies

A common real-world error is that the browser returns to the callback, but Spring cannot find the saved authorization request. This often happens when:

- The session cookie (`JSESSIONID`) is not sent back to the same application origin due to `SameSite`, `Secure`, Domain, Path, or HTTP/HTTPS mismatch.
- Redirecting to a different hostname than the hostname that created the session.
- The app runs across multiple instances without shared sessions, or the load balancer switches nodes and sessions only exist locally.
- The session expired/was invalidated while the user was logging in at the IdP.
- Setting `SessionCreationPolicy.STATELESS` or a custom repository that drops correlation data storage.
- Two authorization requests are initiated, and the older tab/flow is overwritten in a design that only stores one pending request.

In Spring Security, a callback missing its transaction can appear as `authorization_request_not_found`. **Do not "fix" it by skipping state matching**. Inspect the session cookie, storage, and redirect flow. For two simultaneous login tabs, you may need a repository design storing multiple pending authorization requests keyed by state, depending on product requirements.

### 8.3. Reverse proxy and callback URI

For an app behind Nginx/Ingress, `{baseUrl}` in `redirect-uri` must resolve to the real public URL, **not `http://internal-service:8080/...`**. When the app relies on forwarded headers (`Forwarded`, `X-Forwarded-Proto`, `X-Forwarded-Host`), configure the proxy and Spring to **trust forwarded headers only from trusted proxies**. One option in Spring Boot is `server.forward-headers-strategy=framework` when the infrastructure has a proper trust boundary; double-check the generated URI before registering it at the IdP.

Redirect URI mismatch errors often occur due to differences in HTTP↔HTTPS, host, port, context path, or proxy path rewrites. Compare `redirect_uri` in the authorization request with the value registered at the IdP and the value sent in the token request. Never try to work around this with an open redirect or an unchecked wildcard callback.

## 9. Common errors and diagnostics table

| Symptom | Root cause to verify | Proper fix |
| --- | --- | --- |
| Fails immediately when opening `/oauth2/authorization/{registrationId}` | Wrong `registrationId`, missing `ClientRegistration`, unreachable issuer metadata | Match YAML registration/provider ID and discovery endpoint |
| IdP reports `invalid_redirect_uri` or redirect mismatch | Callback host/scheme/port/path does not match registration | Align `redirect_uri` across Spring, proxy, and IdP |
| Callback has `code` but reports `authorization_request_not_found` | Lost session/authorization request, state from different session, cookie blocked | Check session cookie, SameSite, shared session, host, and repository |
| Callback `state` differs from initiated state | Swapped/confused flow, replaced session, or different pending request | Reject callback and find root cause; never accept caller-forged state |
| Token endpoint returns `invalid_grant` | Expired/reused code, mismatched redirect URI, different client, or wrong PKCE verifier | Safely inspect IdP logs, check code/verifier/callback belong to the same transaction |
| Authorization URL lacks `code_challenge` | PKCE not enabled for the current client type/chain | Check resolver on the right chain, `withPkce()`, provider S256 support |
| Challenge present, but token exchange lacks verifier | Request repository or custom token client dropped the PKCE attribute | Preserve verifier from auth request to token request; inspect custom code |
| Authorization Server returns ID Token with mismatched nonce | ID Token belongs to another transaction, buggy provider, or custom code dropped nonce | Reject ID Token, check correlation; never disable validator |
| No `nonce`/ID Token seen | Using plain OAuth2, `openid` scope not requested, or IdP lacks OIDC support | Clarify whether OIDC login or plain OAuth2 authorization is needed |
| `invalid_client` from token endpoint | Wrong client secret, mismatched authentication method, wrong client/IdP ID | Fix server-side credentials and auth method; never move secret to frontend |
| `/me` does not have an OIDC principal | Registration did not request `openid`, login not via OIDC, or wrong mapping | Check scope and principal type; do not cast blindly |
| Cookie-based flow fails through proxy | Wrong scheme, inaccurate forwarded headers, SameSite, or TLS | Compare public URL, `Set-Cookie`, `Cookie`, proxy headers, and actual callback |
| Newly logged-in user gets 403 on POST | Application CSRF protection still applies | Send the session's CSRF token; OAuth2 `state` is not a form-CSRF token |
| Two concurrent login tabs break callback | Session repository stores only one pending request or request gets overwritten | Check actual behavior and design storage keyed by state if multi-transaction is needed |
| Tokens/secrets appear in logs | Excessive query/header/body logging in app/proxy | Reduce logging, redact sensitive fields, and rotate credentials per procedure |

Some errors from IdPs do not share the same HTTP status codes across providers. Distinguish **authorization endpoint errors (via browser)** from **token endpoint errors (server-to-server)** before drawing conclusions.

## 10. Layered security testing

### 10.1. Testing the PKCE algorithm

Run `PkceExample.java` from Section 5.1. The RFC 7636 test vector must match, and a newly generated verifier must have a valid length; do not use that fixed value as a production credential. In a real system, when the authorization request has `code_challenge`, the token endpoint must reject the code if `code_verifier` fails to prove the matching challenge.

### 10.2. Testing authorization redirect

With a test IdP and a real client registration:

- Open the authorization endpoint via Spring; confirm there is a **random state** and a **PKCE S256 challenge**.
- For OIDC login with nonce, verify the request carries nonce per framework configuration; do not assume nonce in plain OAuth2 API authorization.
- A successful callback must use the same browser session, the right `state`, and the right code.
- A callback with missing/wrong state, a reused code, or an expired callback must fail.
- A token exchange with the wrong verifier must be rejected by the Authorization Server.
- If the OIDC request sent a nonce, a returned ID Token with a wrong or missing nonce must be rejected by the client.
- Ensure signature/issuer/audience/expiration checks on the ID Token, and verify post-login permissions/roles separately.

**No need to try forging callbacks in production.** Edge cases should be tested against a local IdP/test environment with managed test transactions and logs that mask sensitive data. Test both security filters and real IdP behavior; a test that only inspects the redirect URL does not prove token validation works.

### 10.3. Browser and server expectations

Browser Network sees the redirect to the IdP, the callback carrying code/state, the app's session cookie, and the redirect to the success page. It **should not see** the token request containing `code_verifier` or `client_secret` in the standard server-side model. Server/IdP logs can trace HTTP milestones and redacted error codes without logging raw codes/tokens/verifiers/secrets.

When deploying, ensure:

1. **HTTPS** for real endpoints; redirect URIs are strictly allowlisted.
2. `state` is randomly generated, saved, and verified bound to the session/transaction; never ignore an invalid callback.
3. **PKCE S256** uses a verifier with sufficient entropy and sends the verifier only when exchanging the code.
4. **OIDC nonce** when the request has a nonce: verify ID Token nonce, signature, `iss`, `aud`, `exp`, and related constraints.
5. Client credentials live in a secret store/server; token storage/rotation/revocation and access permissions are properly designed.
6. Session cookies, SameSite, proxy forwarded headers, load balancing, and session timeouts do not lose correlation state.
7. Separate OAuth2/OIDC login from app form CSRF and API resource-server validation.

## 11. Mental model for a single transaction

```text
Authorization request:
    state = S
    code_verifier = V                 (stored securely at client)
    code_challenge = BASE64URL(SHA256(V))
    nonce = N                         (only when OIDC transaction uses nonce)

Browser to IdP:
    response_type=code, state=S, code_challenge=..., method=S256, nonce=N

Browser callback:
    code=CODE, state=S                -> Client must compare state and session

Client to token endpoint:
    grant_type=authorization_code, code=CODE, code_verifier=V
    (+ client authentication when confidential client)

Client receives token:
    Verify token response; if OIDC sent nonce N, ID Token must contain
    matching nonce N, and must pass all other ID Token checks.
```

**Practical takeaway:** In Spring Security Servlet, let filters/the framework manage Authorization Code correlation, use **state** to confirm the callback belongs to the right transaction, use **PKCE S256** to bind the code to the verifier, and use **nonce when an OIDC ID Token is involved** to confirm the token belongs to the login request. All three complement each other and do not replace session protection, redirect URI validation, token validation, authorization, or application CSRF.
