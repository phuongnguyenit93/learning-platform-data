# What Parts of the OAuth2/OIDC Login Flow Do `state`, PKCE, and `nonce` Protect?

## 1. Scope and Direct Answer

In the **OAuth 2.0 Authorization Code Flow** and **OpenID Connect (OIDC) Authorization Code Flow**, the browser travels from the application (OAuth client / OIDC Relying Party) to the Authorization Server/OpenID Provider, then returns to the application via a callback. The three values `state`, PKCE, and `nonce` appear together, yet are checked at three different links in the chain.

| Mechanism | What Does It Prove? | Value Sent at Start | When and by Whom Is It Checked? | Primary Risk Mitigated |
| --- | --- | --- | --- | --- |
| **`state`** | The authorization response belongs to the **transaction initiated by this exact browser/session** | Random `state` in the URL to the authorization endpoint | **Client** receives the callback and matches returned state against the stored transaction | Login CSRF, session swapping, and callbacks not belonging to a pending login |
| **PKCE** | The party exchanging the authorization code knows the **per-initiation secret** | `code_challenge` + `code_challenge_method=S256`; keeps `code_verifier` secret | **Authorization Server** receives the token request and checks the verifier against the code's challenge | Authorization-code interception, injection/substitution, and misuse |
| **OIDC `nonce`** | The ID Token truly belongs to the **pending OIDC authentication request** | `nonce` in the authentication request | **OIDC client** verifies the `nonce` claim of the ID Token after validating the token | ID Token replay/substitution, binding the token to a specific login attempt |

The three mechanisms have **overlapping coverage**: RFC 9700 confirms that PKCE can protect against CSRF when supported by the server and properly bound by the client to the transaction/browser; OIDC nonce can also help mitigate CSRF and code injection under specific conditions. Therefore, do not memorize them as three completely isolated walls. For debugging, however: checking the **callback** → think `state`; checking **exchanging code for tokens** → think PKCE; checking the **ID Token** → think `nonce`.

**OAuth 2.0** is primarily about *authorization* (delegated access). **OIDC** adds the *user authentication* layer, including the `openid` scope and ID Token. Do not conclude who logged in merely by decoding an access token or calling it an ID Token.

## 2. Full Flow and Where Values Are Stored

This example uses only the Authorization Code Flow, with a backend client protecting sessions and transactions server-side; the `example.test` domain URLs are illustrative.

```text
Browser                  App (OAuth/OIDC Client)                 OpenID Provider / AS
   |                             |                                     |
   | GET /oauth2/authorization/demo                                    |
   |---------------------------->|                                     |
   |                             | generate state=S                    |
   |                             | generate verifier=V                 |
   |                             | challenge=C=S256(V)                 |
   |                             | generate nonce=N if OIDC            |
   |                             | store {S,V,N,issuer,expires}        |
   |                             | bind to this browser session        |
   |<------ 302 /authorize?state=S&code_challenge=C&nonce=N ------------|
   |                             |                                     |
   | Browser follows redirect ---------------------------------------->|
   |                             |          authenticate user          |
   |<---------------------- 302 callback?code=K&state=S ----------------|
   |                             |                                     |
   | GET /login/oauth2/code/demo?code=K&state=S                        |
   |---------------------------->|                                     |
   |                             | 1. compare S with expected state    |
   |                             | 2. check transaction is still valid |
   |                             |                                     |
   |                             | POST /token: code=K, verifier=V     |
   |                             |------------------------------------>|
   |                             |           S256(V) must equal C      |
   |                             |<----- access_token, id_token -------|
   |                             |                                     |
   |                             | 3. verify ID Token: signature,      |
   |                             |    iss, aud, exp, matching nonce    |
   |                             | 4. create local session if valid    |
   |<---------------- 302 to application page --------------------------|
```

Temporary transaction record, **not** JSON sent to the provider:

```json
{
  "state": "random-for-login-1",
  "codeVerifier": "private-random-verifier",
  "expectedNonce": "random-for-login-1",
  "issuer": "https://idp.example.test",
  "redirectUri": "https://app.example.test/login/oauth2/code/demo",
  "expiresAt": "short-lived-expiry",
  "consumed": false
}
```

For server-side web clients, keep the expected state, nonce, and verifier in the server session/transaction store bound to the browser. For SPAs/mobile apps, the storage differs, yet you **must not leak the verifier** or share a single transaction across different users/browsers. Use short lifetimes, single-use consumption, and handling for concurrent callbacks.

## 3. `state`: Preventing Login CSRF and Binding the Authorization Response to the Session

### 3.1. Without Checking `state`

An attacker logged into their own account can obtain an authorization response for the attacker's account and trick the victim's browser into visiting that callback. If the application sees `code` and automatically signs the user in, the victim's browser may become bound to **an account controlled by the attacker**. The victim inadvertently enters data into the attacker's account; this is **login CSRF/session swapping**.

Suppose the victim's browser started a flow with `state=S_victim`. The client stores `S_victim` for that session. A callback with `state=S_attacker` captured by the attacker from another browser will be rejected **right at the client**, even though the accompanying authorization code is legitimately valid at the provider.

### 3.2. Doing It Correctly

1. At the start of each login, generate an unpredictable random state (e.g., 32 bytes from a CSPRNG, Base64URL-encoded without padding); never use timestamps or usernames.
2. Store the expected state **with the user agent's session** along with the authorization request data (issuer, redirect URI, client registration, PKCE verifier, and nonce if applicable).
3. When the callback arrives, locate the current browser's pending transaction; compare the returned state against the expected value. Mismatched, missing, expired, or already used → reject.
4. Mark/remove the transaction after processing per the **single-use** principle. If two callbacks arrive simultaneously, ensure only one can succeed.
5. If `state` also carries a “return to /orders” path, protect that data from tampering; allow redirects only to trusted destinations. Never blindly redirect to a URL inside `state`.
6. Protect the session cookie (HTTPS, HttpOnly, Secure, appropriate SameSite), configure callbacks and reverse proxies properly, and avoid putting state/codes into sensitive logs.

**Insufficient:** checking merely that “the `state` parameter is non-empty” or comparing it against a value **just supplied by the callback itself** without a copy saved from initiation. What matters most is binding to the transaction initiated by the **exact same browser**.

### 3.3. Does `state` Protect a Stolen Authorization Code?

State protects the link between the request and callback at the **OAuth client**. The token endpoint generally does not receive `state`, so `state` **does not prove ownership of the authorization code** if a third party intercepts the code. PKCE directly protects that stage.

Per **RFC 9700**, a client may rely on PKCE for CSRF protection if it is certain the server supports/enforces PKCE and the transaction is properly bound to the user agent; in that case, `state` is not an absolute requirement for every flow. In standard Spring Security applications, keep the default `state` alongside PKCE so callback management stays clear and safe.

## 4. PKCE: Protecting the Exchange of the Authorization Code for Tokens

PKCE (Proof Key for Code Exchange, **RFC 7636**) is designed so that an observed or injected authorization code **is not enough** to obtain tokens. Every time an authorization request starts, a secret random `code_verifier` is generated; the authorization request sends only a **one-way transformation** of it.

### 4.1. The S256 Algorithm

Per RFC 7636:

- `code_verifier` has 43–128 ASCII characters from `A–Z a–z 0–9 - . _ ~`. Generating **32 CSPRNG bytes** and Base64URL-encoding without padding yields a **43-character** string with roughly 256 bits of entropy.
- Exact calculation:

  `code_challenge = BASE64URL_NO_PADDING(SHA256(ASCII(code_verifier)))`

- Send `code_challenge` and `code_challenge_method=S256` in the browser **authorization request**.
- Keep `code_verifier` in the client transaction; after a valid callback, send it in **POST /token over TLS** along with the code, redirect URI, and required client details.
- The Authorization Server stores the challenge bound to the **issued authorization code**. Upon code exchange, the server computes `S256(verifier)` and compares; if they do not match, it must refuse to issue tokens.

**S256** is the modern choice. Using `plain` means the challenge equals the verifier itself, weakening protection if an attacker reads the authorization request. Never choose `plain` for new flows.

### 4.2. Stolen Code Scenario

Code `K` is issued for challenge `C=S256(V)`. An attacker steals `K` without knowing `V`. Sending `K` with `V2` → `S256(V2)≠C` → token endpoint rejects it. The legitimate client holds `V` and can exchange `K` once other checks (client, redirect URI, expiry, one-time code) pass.

PKCE does not encrypt the authorization code and **does not protect an access token stolen after issuance**. If an attacker captures both `K` and `V`, PKCE can no longer stop them from using them; hence you still need HTTPS, no log leakage, valid redirect URIs, and session/client runtime protection.

### 4.3. Public and Confidential Clients

- **Public clients** such as native apps and SPAs cannot keep a long-lived client secret. RFC 9700 requires public clients to use PKCE for authorization codes.
- **Confidential web clients** with a server-protected client secret are still **recommended** to use PKCE to prevent code injection/misuse. Client authentication does not fully replace binding **one code to one initiation**.
- The Authorization Server must enforce PKCE whenever a challenge is sent and prevent downgrade attacks (e.g., never ignore the challenge to accept a wrong verifier). Simply seeing `code_challenge` in Network tools is **not enough** to prove the server checks it properly.

PKCE can also provide CSRF protection per RFC 9700, provided the provider truly enforces it and the client has secure transaction binding. However, PKCE does not validate ID Tokens on its own or enforce user business permissions.

## 5. `nonce`: Binding the ID Token to the OIDC Authentication Attempt

### 5.1. A Validly Signed ID Token Might Not Belong to This Login

An OIDC client sends a random nonce in the authentication request; the provider echoes it in the **nonce claim inside the ID Token**. When the ID Token arrives, the client verifies signature/issuer/audience/timestamps and matches the nonce claim against the expected nonce saved at initiation.

```json
{
  "iss": "https://idp.example.test",
  "sub": "user-123",
  "aud": "web-client",
  "iat": 1769999400,
  "exp": 1770000000,
  "nonce": "nonce-of-this-transaction"
}
```

This JSON is only an **illustrative payload**, not a trustworthy JWT. Never accept it just because the JSON has the right nonce: signature, algorithm, key, issuer, audience, expiration, and required claims must all be valid.

If an attacker replays an ID Token from an earlier login (nonce `N1`) into a transaction expecting nonce `N2`, checking `N1≠N2` lets the client **reject ID Token replay/substitution**. Nonce must have high entropy, be bound to the session and transaction, and be single-use.

### 5.2. Distinguishing `nonce` from `state`

`state` on the **authorization callback** primarily links the authorization response to the initiation attempt. `nonce` inside the **ID Token** links the user authentication proof to the OIDC authentication request. Do not use `nonce` to replace JWT signature checks, and do not treat `state` as if it were a provider-signed nonce inside the ID Token.

Some libraries store the raw random value while placing a **hash of that value** into the authorization request as the nonce; the validator must follow the library's convention when comparing. Do not manually alter the nonce with custom code that breaks the link between the request and the ID Token. Spring Security OAuth2 Login has its own internal nonce generation when a registration includes the `openid` scope.

### 5.3. OIDC Core Rules and Common Pitfalls

Per **OpenID Connect Core 1.0**, `nonce` is **OPTIONAL** in the **OIDC Authorization Code Flow**; if the client sends a nonce, the provider must include the matching claim in the ID Token and the client must check it. In the **OIDC Implicit Flow**, `nonce` is **REQUIRED**; certain Hybrid Flow variants also require it. Thus, claiming “nonce is mandatory in every OIDC flow” is false.

RFC 9700 further recognizes that nonce, with additional conditions, can protect confidential OIDC clients against certain forms of code injection/CSRF. PKCE remains the direct, standard way to prove ownership of the **code** at the token endpoint, so use **Authorization Code + PKCE + OIDC token validation**, and nonce when present.

Plain OAuth 2.0 does not produce an OIDC ID Token or nonce by default. Do not arbitrarily add a parameter named `nonce` to an OAuth2 request and assume there will be an ID Token to validate.

## 6. HTTP Trace: Which Value Appears in Which Request?

Strings in `<...>` are placeholders; this is a sequence illustration, **not** an HTTP exchange with real tokens.

**Step 1 — initiate login at the application:**

```http
GET /oauth2/authorization/demo HTTP/1.1
Host: app.example.test
Cookie: JSESSIONID=<browser-session-id>
```

The application generates `S`, `V`, `C=S256(V)`, `N`, saves pending transaction data, and returns a redirect to the IdP:

```http
HTTP/1.1 302 Found
Location: https://idp.example.test/authorize?response_type=code&client_id=web-client&redirect_uri=https%3A%2F%2Fapp.example.test%2Flogin%2Foauth2%2Fcode%2Fdemo&scope=openid%20profile&state=<random-state>&code_challenge=<s256-challenge>&code_challenge_method=S256&nonce=<random-nonce>
```

The Authorization URL contains `state`, `code_challenge`, and `nonce`; it **must never contain `code_verifier` or the client secret**.

**Step 2 — user signs in at the IdP and the browser returns to the callback:**

```http
GET /login/oauth2/code/demo?code=<authorization-code>&state=<same-state> HTTP/1.1
Host: app.example.test
Cookie: JSESSIONID=<browser-session-id>
```

Here, the **client** checks `state` against the pending transaction before proceeding. If the callback returns `error=access_denied` or `state` is wrong/expired/already used, a successful login session must not be created.

**Step 3 — client backend calls the token endpoint:**

```http
POST /token HTTP/1.1
Host: idp.example.test
Content-Type: application/x-www-form-urlencoded

grant_type=authorization_code&code=<authorization-code>&redirect_uri=https%3A%2F%2Fapp.example.test%2Flogin%2Foauth2%2Fcode%2Fdemo&client_id=web-client&code_verifier=<original-code-verifier>
```

If the client is confidential, add the registered **client authentication** over the back channel (e.g., HTTP Basic over TLS); never pass the client secret through browser URLs. The Authorization Server verifies the verifier against the code's challenge and checks client/redirect URI/code expiry/one-time semantics.

**Step 4 — OIDC client receives the ID Token:**

```text
Verify ID Token signature + trusted algorithm/key
Verify iss, aud, exp, iat, and required claims per flow
Compare nonce claim with the transaction's expected nonce
Verify callback/token belong to the initiated provider and client
Create app session; invalidate/consume pending transaction
```

If `nonce` mismatches, the client must reject the ID Token; never fall back to an unverified token payload or create a principal from an access token.

## 7. Attack Scenarios and the Right Defenses

| Scenario | How the Attacker Executes It | Primary Defense Layer | Expected Result |
| --- | --- | --- | --- |
| **Login CSRF** | Sends a callback `code` from the attacker's account to the victim's browser | state/session binding at the OAuth client; PKCE/nonce can assist per spec | No matching pending transaction → rejected |
| **Code interception** | Captures authorization code `K` in transit on the redirect without the verifier | PKCE at the Authorization Server token endpoint | Cannot exchange `K` for tokens |
| **Code injection** | Swaps a code from one transaction into another transaction's callback | state binding + PKCE/nonce depending on attack variant | Code fails verifier check or token fails transaction check |
| **ID Token replay** | Replays an old ID Token carrying nonce `N1` during a new login `N2` | ID Token `nonce` check after standard verification | ID Token rejected |
| **Forged JWT** | Crafts a fake JWT with the expected nonce but invalid signature/issuer | JWT/OIDC signature + issuer/audience validation | Rejected; valid nonce never makes a forged token valid |
| **Authorization-server mix-up** | Swaps authorization responses between providers A and B | Checking issuer/provider matching the transaction | Response/token from wrong provider rejected |
| **Callback replay** | Submits the same state/code multiple times | Single-use transaction and one-time code on the server | Repeat attempts rejected |
| **Post-login token theft** | Steals access token/`JSESSIONID` after issuance | Separate token/session security | These three values do not replace token/cookie protection |

In clients supporting **multiple providers**, prevent mix-up via issuer identification (e.g., authorization response `iss` per RFC 9207, checking ID Token `iss` in OIDC, or dedicated redirect URIs where appropriate). Do not assume `state`, PKCE, and `nonce` **automatically** solve every provider-selection bug.

## 8. Security Boundaries Not to Misunderstand

- `state` is not an automatic CSRF token for **every post-login POST/DELETE request**. Web applications using session cookies still need business-action CSRF protection per Spring Security policy.
- PKCE does not replace HTTPS, client authentication (for confidential clients), exact redirect URIs, code expiration controls, issuer checks, or one-time codes.
- Nonce does not replace verifying JWT signatures, issuer, audience, timestamps, algorithm allowlists, or UserInfo/protocol claims per OIDC Core.
- None of the three protect an **already stolen** access token, nor do they address XSS, session fixation, logout, or application authorization.
- Do not trust redirect URIs to arbitrary domains or attacker-supplied `returnUrl` parameters just because `state` is valid. Allowlist targets to prevent open redirects.
- Never log codes, verifiers, tokens, or session cookies in access logs or public traces. Since `state` and `nonce` can be visible in authorization URLs, security relies on **transaction binding and nonce randomness**, not treating URLs as secret storage.
- Never use `code_challenge_method=plain` in new designs. Never hardcode `state`/`nonce`/`code_verifier` or reuse them across logins.
- With multiple browser tabs, transaction storage needs an explicit policy: a repository config might hold only one authorization request; out-of-order callbacks may properly be rejected rather than pairing the wrong verifier/nonce.

## 9. Spring Security 6.x and Spring Boot 3.x (Servlet OAuth2 Login)

### 9.1. Dependencies and Registration

This example uses **Spring MVC** with Java 17+, Spring Boot 3.x, and no WebFlux APIs. In a project with the Boot plugin/dependency management configured, add:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-security'
    implementation 'org.springframework.boot:spring-boot-starter-oauth2-client'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-test'
}
```

Sample `src/main/resources/application.yml`:

```yaml
spring:
  security:
    oauth2:
      client:
        registration:
          demo:
            provider: corporate
            client-id: REPLACE_WITH_REGISTERED_CLIENT_ID
            client-secret: REPLACE_FROM_SECRET_STORE
            authorization-grant-type: authorization_code
            redirect-uri: "{baseUrl}/login/oauth2/code/{registrationId}"
            scope:
              - openid
              - profile
        provider:
          corporate:
            issuer-uri: https://idp.example.test
```

This is an **illustrative configuration**; login will not run until you supply real issuer/client ID/secret values, register the redirect URI at the IdP, and configure HTTPS/proxy properly. Place the client secret in a secret manager or environment variable in real deployments; never store it in Git. `scope=openid` is the OIDC trigger: the OpenID Provider issues an ID Token, and the application must validate it.

### 9.2. Enabling PKCE Even for Confidential Clients

Create `src/main/java/com/example/demo/OAuthLoginConfig.java`:

```java
package com.example.demo;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.oauth2.client.registration.ClientRegistrationRepository;
import org.springframework.security.oauth2.client.web.DefaultOAuth2AuthorizationRequestResolver;
import org.springframework.security.oauth2.client.web.OAuth2AuthorizationRequestCustomizers;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class OAuthLoginConfig {

    @Bean
    SecurityFilterChain securityFilterChain(
            HttpSecurity http,
            ClientRegistrationRepository clientRegistrations) throws Exception {

        var resolver = new DefaultOAuth2AuthorizationRequestResolver(
                clientRegistrations, "/oauth2/authorization");

        // PKCE S256 is needed even when the backend holds a client secret.
        // Spring still generates state; the openid scope also enables the OIDC nonce.
        resolver.setAuthorizationRequestCustomizer(
                OAuth2AuthorizationRequestCustomizers.withPkce());

        return http
                .authorizeHttpRequests(authorize -> authorize
                        .requestMatchers("/", "/error").permitAll()
                        .anyRequest().authenticated())
                .oauth2Login(oauth2 -> oauth2
                        .authorizationEndpoint(endpoint -> endpoint
                                .authorizationRequestResolver(resolver)))
                .build();
    }
}
```

In Spring Security, `DefaultOAuth2AuthorizationRequestResolver` generates `state`, and when scopes include `openid`, also applies the OIDC `nonce`. `OAuth2AuthorizationRequestCustomizers.withPkce()` adds the challenge to the authorization request; the verifier is kept in the **authorization request's attributes** for token exchange. The library automatically matches `state` against the stored authorization request and validates the OIDC ID Token. If you write a custom resolver or authorization request repository, do not drop that transaction data.

Spring Security enables PKCE automatically for public clients (client authentication method `none`) or when `ClientSettings.requireProofKey=true`. The customizer snippet above shows intentionally **applying PKCE to confidential clients as well**, aligning with RFC 9700 recommendations. For legacy providers that do not support PKCE, verify provider support before deploying.

### 9.3. Reading the Authenticated Identity

In a project that already has `@SpringBootApplication`, add a controller (OIDC only) at `src/main/java/com/example/demo/MeController.java`:

```java
package com.example.demo;

import java.util.Map;
import org.springframework.security.core.annotation.AuthenticationPrincipal;
import org.springframework.security.oauth2.core.oidc.user.OidcUser;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class MeController {

    @GetMapping("/me")
    public Map<String, String> me(@AuthenticationPrincipal OidcUser user) {
        return Map.of("subject", user.getSubject());
    }
}
```

Create an authenticated session only after Spring OAuth2 Login completes the callback, token exchange, and OIDC validation. If the registration is plain OAuth 2.0 (without `openid`), the principal may be an `OAuth2User` rather than an `OidcUser`. This code **does not** validate JWTs itself; the library handles that while completing the OIDC flow.

Open `/oauth2/authorization/demo` to start. In Developer Tools → Network, the 302 `Location` response must include `state` and (with PKCE enabled) `code_challenge_method=S256` and `code_challenge`; if `openid` scope is present, it will also include `nonce`. There **must not** be a `code_verifier` or client secret in `Location`.

## 10. Standalone Java 17: Demonstrating the PKCE Formula and Comparing state/nonce

Save the code below into `LoginProofDemo.java`; with Java 17+ you can compile and run it without Spring. The program simulates generating values and demonstrates the **S256** formula; it does not perform OAuth itself, cannot replace the client–server flow, and **does not** validate JWTs.

```java
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.security.NoSuchAlgorithmException;
import java.security.SecureRandom;
import java.util.Base64;

public class LoginProofDemo {

    private static final SecureRandom RANDOM = new SecureRandom();

    record Pending(
            String state,
            String verifier,
            String challenge,
            String nonce) {}

    static String randomToken() {
        byte[] bytes = new byte[32]; // 256-bit entropy
        RANDOM.nextBytes(bytes);
        return Base64.getUrlEncoder().withoutPadding()
                .encodeToString(bytes);
    }

    static String s256(String verifier) {
        try {
            byte[] hash = MessageDigest.getInstance("SHA-256")
                    .digest(verifier.getBytes(StandardCharsets.US_ASCII));
            return Base64.getUrlEncoder().withoutPadding()
                    .encodeToString(hash);
        } catch (NoSuchAlgorithmException e) {
            throw new IllegalStateException("No SHA-256", e);
        }
    }

    static boolean same(String expected, String actual) {
        return MessageDigest.isEqual(
                expected.getBytes(StandardCharsets.US_ASCII),
                actual.getBytes(StandardCharsets.US_ASCII));
    }

    static Pending startLogin() {
        String verifier = randomToken();
        return new Pending(
                randomToken(), verifier, s256(verifier), randomToken());
    }

    public static void main(String[] args) {
        Pending p = startLogin();

        System.out.println("verifierLength=" + p.verifier().length());
        System.out.println("challengeLength=" + p.challenge().length());

        System.out.println("pkceCorrect=" +
                same(s256(p.verifier()), p.challenge()));
        System.out.println("pkceWrong=" +
                same(s256("x" + p.verifier()), p.challenge()));

        System.out.println("stateMatches=" + same(p.state(), p.state()));
        System.out.println("oldNonceMatches=" +
                same("old-nonce", p.nonce()));
    }
}
```

Run:

```bash
javac LoginProofDemo.java
java LoginProofDemo
```

Exact output:

```text
verifierLength=43
challengeLength=43
pkceCorrect=true
pkceWrong=false
stateMatches=true
oldNonceMatches=false
```

Unpadded Base64URL encoding of 32 bytes produces exactly 43 characters; S256 SHA-256 yields a 32-byte hash, so the challenge is also 43 characters. `pkceWrong=false` proves another verifier cannot satisfy the challenge. The state/nonce comparisons here are illustrative only: in real applications, fetch expected values from the **exact browser's transaction** and compare `nonce` only after **full ID Token validation**. Never print real secrets/verifiers to logs.

## 11. Integration Test Plan Against a Real Provider or Mock OP

Run the cases below in a test environment configured with an OIDC Client + OP. To test `nonce` in isolation, the mock OP must issue an ID Token with a **valid signature and matching issuer/audience**, then intentionally alter **only the nonce claim**; if the JWT signature is already broken, the test only exercises signature validation.

| Test | Action | Expected Result |
| --- | --- | --- |
| Happy path | Login, valid callback state, valid verifier, valid ID Token nonce | App session created; `GET /me` succeeds |
| Callback with wrong state | Tamper with `state` on callback | Client rejects; code is not accepted for login |
| Uninitiated callback | Paste callback URL into a fresh browser with no pending transaction | Client rejects |
| Replay state/code | Invoke callback twice after the transaction is consumed | Second attempt fails; authorization code is also one-time |
| Wrong PKCE verifier | Mock request/token endpoint using verifier `V2` not matching challenge `C` | Provider rejects (typically `invalid_grant`), no tokens issued |
| Missing challenge/downgrade | Test omitting challenge or choosing an unaccepted method | Flow requiring PKCE must not silently succeed |
| ID Token with wrong nonce | Mock OP issues validly signed token with nonce `N2` instead of expected `N1` | OIDC client rejects |
| ID Token missing nonce after nonce was sent | Mock OP omits `nonce` claim | Client rejects |
| ID Token has right nonce but wrong signature/iss/aud | Keep nonce valid, break other claims/signature | Client rejects |
| Two browsers/tabs | Initiate separate transactions, swap callback order | Must not mismatch state/nonce/verifier; rejects expired transactions |
| Provider mix-up | Start at A, return response/token from B | Client does not create a session |
| Missing cookie after login | Another browser calls `/me` | Application requires login again |

When testing a failure, identify the **failing layer**: `state` at the OAuth client, verifier at the authorization server token endpoint, `nonce` at the OIDC client ID Token validator. Inspect Network and safe logs using only error codes and correlation IDs; never log codes, verifiers, or tokens.

## 12. Common Errors and How to Diagnose Them

| Symptom | Common Cause | Right Check |
| --- | --- | --- |
| `authorization_request_not_found`, state mismatch | Session cookie missing on callback, transaction overwritten, stale callback, reverse proxy issue | Check session cookie, callback URL, transaction repository, TTL |
| PKCE `invalid_grant` | Wrong verifier, expired/reused code, redirect URI/client mismatch | Check token endpoint error without logging real values |
| Challenge sent yet wrong verifier still succeeds | Authorization Server not enforcing PKCE or vulnerable to downgrade | Run negative test with wrong verifier; verify server/provider config |
| Nonce mismatch | Token from another transaction, nonce altered by custom resolver, lost pending session | Compare post-validation ID Token against stored authorization request |
| Nonce absent | `scope` lacks `openid` or plain OAuth2 | Check OIDC registration; do not fabricate nonce in the client |
| Login succeeds yet ID Token is invalid | App decodes JWT without checking signature, issuer/audience/time | Use standard OIDC client; remove any bypass |
| Two login tabs break the earlier tab | Store keeps only one pending request or overwrites transactions | Design repository for multi-tab needs; never reuse verifiers |
| Open redirect after login | Blindly trusting URL in `state`/`returnUrl` | Allowlist return destinations; use relative paths |
| Disabling app-wide CSRF because `state` exists | Confusing login CSRF with business-action CSRF | Keep CSRF protection for cookie-authenticated requests where needed |
| Fixed nonce per user | Nonce lacks transaction freshness | Generate randomly for every login attempt |

## 13. Checklist and Self-Check Questions

- **state:** sufficiently strong random value, stored per session/browser, matched on callback against an active, unexpired, single-use transaction.
- **PKCE:** generate verifier with sufficient entropy (43–128 characters); use S256; keep verifier secret until the token request; server verifies the exact challenge bound to the code.
- **nonce:** when using OIDC and sending nonce, the client compares the nonce claim from the **validated** ID Token against the pending transaction; never accept old tokens.
- **Independent checks:** verify issuer, audience, signature, expiration, exact redirect URI, client authentication, TLS transport, session security, and authorization.
- **Empirical test:** intentionally break `state`, verifier, and `nonce` one by one to verify each error is rejected **at the right layer**.

If you must remember a single chain: **callback to client checks `state` → Authorization Server code exchange checks PKCE verifier → OIDC client receiving ID Token checks `nonce` and claim/token validation**. This accurately answers “what parts do the three mechanisms protect?” and gives a verifiable debugging path on real traces.

### Primary References

- [RFC 6749 — OAuth 2.0](https://www.rfc-editor.org/rfc/rfc6749)
- [RFC 7636 — Proof Key for Code Exchange](https://www.rfc-editor.org/rfc/rfc7636)
- [RFC 9700 — OAuth 2.0 Security Best Current Practice](https://www.rfc-editor.org/rfc/rfc9700)
- [RFC 9207 — Authorization Server Issuer Identification](https://www.rfc-editor.org/rfc/rfc9207)
- [OpenID Connect Core 1.0 — Authentication Request, nonce, ID Token Validation](https://openid.net/specs/openid-connect-core-1_0.html)
- [Spring Security — OAuth2 Client Authorization Grants](https://docs.spring.io/spring-security/reference/servlet/oauth2/client/authorization-grants.html)
- [Spring Security API — DefaultOAuth2AuthorizationRequestResolver](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/oauth2/client/web/DefaultOAuth2AuthorizationRequestResolver.html)
- [Spring Security API — OAuth2AuthorizationRequestCustomizers.withPkce()](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/oauth2/client/web/OAuth2AuthorizationRequestCustomizers.html)
