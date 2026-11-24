# Authorization Code Flow, Redirect URI, and Callback in Spring Security WebFlux

## Objective

This lesson belongs to the **OAuth2/OIDC Login** section of the **Spring Security - reactive** module. When a user selects “Sign in with an identity provider”, the WebFlux application must not collect that provider's password itself. Instead, the browser is redirected to the Authorization Server/OpenID Provider, the user signs in there, and then the provider **redirects the browser back to the client's callback** along with an authorization code. Spring Security exchanges the code over a server-to-server connection, verifies the result, and establishes a login session for the application.

After this lesson, you will be able to:

1. Distinguish OAuth 2.0 Authorization Code Grant from OpenID Connect (OIDC) Login.
2. Identify the exact **client initiation URL** `/oauth2/authorization/{registrationId}`, **IdP Authorization Endpoint**, and **client callback** `/login/oauth2/code/{registrationId}`.
3. Explain the role of `redirect_uri`, `client_id`, `scope`, `state`, `nonce`, and PKCE `code_verifier`/`code_challenge`.
4. Point out which steps run in the browser and which run **between two servers**.
5. Distinguish authorization codes, access tokens, ID tokens, refresh tokens, client secrets, and WebSession cookies.
6. Understand how Spring Security WebFlux uses `ReactiveClientRegistrationRepository`, `OAuth2AuthorizationRequestRedirectWebFilter`, `OAuth2LoginAuthenticationWebFilter`, `WebSessionOAuth2ServerAuthorizationRequestRepository`, `ServerSecurityContextRepository`, and `ReactiveSecurityContextHolder`.
7. Run a **Java 17+, Spring Boot 3.3.13, Gradle, WebFlux** example with a local Keycloak OIDC instance.
8. Customize the callback properly using `authenticationMatcher(...)` **and** `redirect-uri`, while registering the exact URI at the provider.
9. Handle reverse proxy/HTTPS, multi-instance setups, and lost session/state errors when the callback returns.
10. Test success cases, missing state, wrong redirect URI, expired/replayed codes, and token/issuer errors.
11. Distinguish HTTP-layer `mockOidcLogin()` tests from real E2E code-exchange tests.
12. Apply baseline security requirements: HTTPS, session cookies, secret management, PKCE, token validation, CSRF, and never logging tokens/codes.

**Key takeaway:** An OAuth2 Login callback **is not a GET controller you write yourself to receive the code**. In Spring Security reactive, the callback is processed inside the security WebFilter chain, using pending request data in the session to verify `state` and perform the token exchange.

## 1. OAuth 2.0 and OIDC: Same Flow Shape, Different Purpose

**OAuth 2.0** is an authorization framework allowing a client to access protected resources within permitted scopes. **OpenID Connect 1.0** builds on top of OAuth2 to authenticate end-user identity using a protocol with an ID Token.

| Component | OAuth2 Authorization Code | OIDC Authorization Code |
| --- | --- | --- |
| Purpose | Grants resource access permissions | Grants permissions and authenticates the user |
| Authorization request | `response_type=code` | `response_type=code` + `openid` scope |
| Authorization response | Code + state | Code + state |
| Token endpoint | Access token, sometimes refresh token | Access token + **ID Token** (per OIDC), optional refresh token |
| User identity | Not standardized with an ID Token | Verifies `id_token` with `iss`/`aud`/signature/time/`nonce` when used |
| Principal in Spring Security | Typically `OAuth2User` | Typically `OidcUser` |
| API access | Access token sent to a valid resource server | **Still** uses access token; never use ID token as an API bearer token |

The `openid` scope is the key signal indicating the client is requesting OIDC. Having `profile` or `email` scopes does not guarantee every claim is provided or verified by the provider; inspect the actual profile/claims and the IdP's policy.

### Roles in the Example

| Role | Example | Duty |
| --- | --- | --- |
| Resource Owner / End User | User `alice` | Signs in at the IdP |
| User Agent | Chrome/Firefox | Executes redirects; stores cookies |
| OAuth2 Client / OIDC Relying Party | Spring Boot WebFlux `localhost:8080` | Initiates login, receives callback, exchanges code for tokens, creates SecurityContext |
| Authorization Server / OpenID Provider | Keycloak `localhost:9090` | Authenticates, issues codes/tokens, provides issuer/JWK |
| Resource Server | An API accepting Bearer tokens (optional in this lab) | Validates access tokens before allowing API calls |
| Spring Security reactive | `SecurityWebFilterChain` | Protects HTTP routes, handles start/callback, saves/loads sessions |

Do not confuse `spring-boot-starter-oauth2-client` with `spring-boot-starter-oauth2-resource-server`. This lesson uses **OAuth2 Client** for login. The WebFlux app itself does not issue access tokens or ID tokens.

## 2. Authorization Code Flow Diagram

```text
Browser                   WebFlux Client                  Keycloak OP
                         localhost:8080                  localhost:9090
   |                          |                                |
1. | GET /oauth2/authorization/keycloak                        |
   |------------------------->|                                |
   |                          | Create state, pending request  |
   |                          | save in WebSession             |
2. |<-------- 302 Location: http://localhost:9090/.../auth?... |
   |                          |                                |
3. | GET authorize?response_type=code&state=S... -------------->|
   |                          |                                |
4. |<---------- Login/consent form at Keycloak ----------------|
5. |------------- user logs in at Keycloak ------------------->|
   |                          |                                |
6. |<------------ 302 Location: http://localhost:8080/.../code |
   |                               /keycloak?code=C&state=S     |
7. | GET /login/oauth2/code/keycloak?code=C&state=S             |
   |------------------------->|                                |
   |                          | Restore pending request        |
   |                          | Match state/session            |
8. |                          | POST /protocol/.../token ------>|
   |                          | code, redirect_uri, client auth |
   |                          | (+ code_verifier if PKCE)      |
9. |                          |<--- access_token, id_token ----|
   |                          | Validate ID Token + OidcUser    |
   |                          | Save SecurityContext/session    |
10.|<-------------------- 302 to saved request / home page ----|
11.| GET /me + session cookie --------------------------------->|
12.|<--------------------- 200 authenticated principal --------|
```

Steps 1, 3, 5, 7, and 11 are **browser navigation/requests**. Step 8 is a **back-channel HTTP request from the Spring Client to the token endpoint**, not a JavaScript `fetch` carrying a client secret. The redirect callback carries `code` and `state`, **not** raw ID tokens/access tokens in the query string of a standard Authorization Code Flow.

### 2.1. Starting Login: Client URL

By default, Spring Security WebFlux accepts:

```text
GET /oauth2/authorization/{registrationId}
```

For example `GET http://localhost:8080/oauth2/authorization/keycloak`. `registrationId` is the `ClientRegistration` ID you configured in Spring, **not necessarily equal to the `client_id` issued by Keycloak**. This request is handled by `OAuth2AuthorizationRequestRedirectWebFilter`, which calls `DefaultServerOAuth2AuthorizationRequestResolver` to construct the authorization request and redirect the browser to the IdP.

Do not confuse this with the token endpoint or callback. A simple HTML link like this is enough to start:

```html
<a href="/oauth2/authorization/keycloak">
  Sign in with Keycloak
</a>
```

Never manually construct URLs containing a static `state` or a client secret in the frontend.

### 2.2. Authorization Endpoint: IdP URL

In the Keycloak realm `learning` example:

```text
http://localhost:9090/realms/learning/protocol/openid-connect/auth
```

The browser is redirected there with:

```http
GET /realms/learning/protocol/openid-connect/auth?
  response_type=code
  &client_id=webflux-login
  &redirect_uri=http%3A%2F%2Flocalhost%3A8080%2Flogin%2Foauth2%2Fcode%2Fkeycloak
  &scope=openid%20profile%20email
  &state=<random>
  [&nonce=<nonce-if-present>]
  [&code_challenge=<pkce>&code_challenge_method=S256]
```

This is a **line-wrapped conceptual representation**, not a URL to copy verbatim into a browser. Actual parameters depend on the client/provider/version and PKCE configuration. It is normal for the browser to see `client_id`/`state`/`redirect_uri`. `client_secret` **must never** appear in the authorize URL.

### 2.3. Callback: Spring Client URL

Default:

```text
{baseUrl}/login/oauth2/code/{registrationId}
```

For the demo:

```text
http://localhost:8080/login/oauth2/code/keycloak
```

After the user signs in, Keycloak returns:

```http
HTTP/1.1 302 Found
Location: http://localhost:8080/login/oauth2/code/keycloak?code=C&state=S
```

Spring Security's `OAuth2LoginAuthenticationWebFilter` receives the callback, loads the request stored in WebSession, and compares `state`. You do not need to define `@GetMapping("/login/oauth2/code/keycloak")`, and you **should not** exchange the code for tokens yourself in a business controller. Doing it manually makes it easy to omit `state`, PKCE, `nonce`, ID Token verification, and proper error handling.

### 2.4. Token Endpoint: Server-Side Connection

Keycloak token endpoint:

```text
POST http://localhost:9090/realms/learning/protocol/openid-connect/token
```

Primary payload:

```http
grant_type=authorization_code
&code=C
&redirect_uri=http%3A%2F%2Flocalhost%3A8080%2Flogin%2Foauth2%2Fcode%2Fkeycloak
[&code_verifier=<if PKCE is enabled>]
```

For a **confidential client**, the token endpoint also requires client authentication such as `client_secret_basic`. The Spring Security OAuth2 client sends this request from the backend, receives the response, and processes the ID Token without letting the user agent hold the client secret. The authorization code must be **short-lived and single-use**; replaying a code is rejected by the token endpoint.

## 3. Easily Confused URIs

| Path | Owned By | Purpose |
| --- | --- | --- |
| `/login` | Spring Client | Default login/IdP chooser page when generated by the framework |
| `/oauth2/authorization/keycloak` | Spring Client | Starts the authorization flow |
| `/realms/learning/protocol/openid-connect/auth` | Keycloak | Authorization endpoint, login/consent |
| `/login/oauth2/code/keycloak` | Spring Client | Callback receiving code/state |
| `/realms/learning/protocol/openid-connect/token` | Keycloak | Back-channel code exchange |
| `/me` | Spring Client controller | Views the principal after login |
| `/logout` | Spring Client | Local logout per configuration (distinct from OIDC OP logout) |

**Authorization endpoint != callback URL.** **Callback URL != login page.** **Token endpoint != an endpoint the browser should call directly.** Having `login` in the path name does not turn the callback into a form-login POST.

## 4. Important Security Parameters

### 4.1. client_id Differs from registrationId

```yaml
spring:
  security:
    oauth2:
      client:
        registration:
          keycloak:                    # registrationId
            client-id: webflux-login   # IdP's client_id
```

The initiation link uses `keycloak`, while the IdP receives `client_id=webflux-login`. When debugging a registration 404, check the Spring key rather than arbitrarily changing the Client ID in Keycloak.

### 4.2. redirect_uri: Three Places Must Agree

A valid redirect URI must match **simultaneously**:

1. `spring.security.oauth2.client.registration.keycloak.redirect-uri` on the Client.
2. `authenticationMatcher` of the WebFlux OAuth2 Login filter handling the callback.
3. **Valid Redirect URIs** in the client configuration inside Keycloak.

By default, all three use:

```text
http://localhost:8080/login/oauth2/code/keycloak
```

Every detail matters: `http` differs from `https`; `localhost` differs from `127.0.0.1`; port `8080` differs from `8443`; `/login/oauth2/code` differs from `/login/oauth2/callback`. Never configure broad wildcard redirects like `https://*.example.com/*` just to avoid `invalid_redirect_uri`.

**Never turn an unvalidated `returnTo`/`next` parameter into a `redirect_uri` or success URL**: that creates an open redirect that can leak codes/tokens or send users to phishing sites.

### 4.3. state: Binding the Response to the Initiated Request

`state` is an unpredictable string generated by the Client in the authorization request. When the callback returns, Spring Security looks up the saved pending `OAuth2AuthorizationRequest` and compares `state`.

```text
GET /oauth2/authorization/keycloak
   -> generate state S1
   -> save pending request S1 in WebSession
   -> redirect to IdP with state S1

GET /login/oauth2/code/keycloak?code=C1&state=S1
   -> retrieve pending request from the same WebSession
   -> compare state
   -> only if valid, exchange code C1

If state differs / no pending request -> DENY login.
```

`state` defends against **login CSRF** and callback injection. Never replace `state` with a constant string, and never disable validation when hitting session errors. A callback bearing a “seemingly valid” authorization code that **is not bound to this browser's request** must never be treated as a secure login session.

### 4.4. WebSession Stores the Pending Authorization Request

In the reactive stack, the default `ServerAuthorizationRequestRepository` is `WebSessionOAuth2ServerAuthorizationRequestRepository`. The browser typically receives the Spring Client's session cookie when starting OAuth login; when the IdP redirects back, the browser must send that cookie so the Client can locate the saved `state` request.

**If the cookie is lost**, you may see `authorization_request_not_found` even though the IdP authenticated the user successfully. Causes include:

- Mixing `localhost` and `127.0.0.1`, or changing hostname/scheme between start and finish.
- `SameSite=Strict` cookies blocking cross-site navigations back to the Client.
- Session expiration, logout, or clearing while the user was at the IdP.
- Callback hitting a pod without a shared WebSession from the pod that created the pending request.
- Redis/Session store outage, or incompatible serializer/namespace.
- Multiple concurrent login flows or another tab overwriting/changing the pending request depending on repository/version behavior.

**Never use a CORS wildcard to fix cookie/session errors.** The OAuth callback is a top-level navigation; CORS does not control whether the browser is allowed to redirect back to the callback.

### 4.5. PKCE Is Not state

PKCE uses a client-side secret `code_verifier` and a transformed `code_challenge`:

```text
code_verifier (random string)
      |
      +-- SHA-256 + base64url --> code_challenge
      |                           sent in authorization request
      |
      +-------------------------> code_verifier
                                  sent during token exchange
```

The Authorization Server verifies the verifier against the challenge before exchanging the code for tokens. As a result, a code intercepted in transit is difficult for anyone else to redeem without the verifier.

**Spring Security 6.x** supports PKCE for public clients. PKCE is automatically used when `ClientRegistration` has `client-authentication-method=none`, no client secret, or `ClientRegistration.clientSettings.requireProofKey=true`. For confidential clients using a secret like in this demo, **do not assume PKCE is always enabled by default**: inspect the actual authorization request and configure provider/client settings if PKCE is required.

PKCE adds protection for the code; it **does not** replace `state` correlation, proper client authentication, redirect URI validation, or OIDC ID Token verification.

### 4.6. nonce and the OIDC ID Token

OIDC `nonce` (when sent) binds the ID Token to the authentication request and mitigates replay. The ID Token must have its signature verified via JWK/allowed algorithms, along with `iss`, `aud`, `exp`/timestamps, matching `nonce` when applicable, and other standard conditions.

Never write code like “`Base64.decode(jwt.payload)` and trust the role field” as authentication. Spring Security OIDC login includes token verification components; never disable signature/issuer validation to bypass Keycloak configuration errors.

### 4.7. Code, Tokens, and Session Are Different

| Type | Purpose | Where It Should Be Used |
| --- | --- | --- |
| Authorization code | Single-use exchange for tokens | Callback → back-channel token request |
| Access token | Access protected resources with matching audience/scope | HTTP `Authorization: Bearer` to Resource Server |
| ID Token | Proves OIDC authentication to the Client | Client verifies identity; never use in place of access token |
| Refresh token | Requests a new access token when issued | Secure server/token store, per refresh policy |
| Client secret | Authenticates a confidential OAuth Client | Server/secret manager; never put in the browser |
| `SESSION` cookie | Identifies the Spring Client's WebSession | Held by the browser to load pending request/context |
| Spring `SecurityContext` | User's authentication at the Client | WebSession + Reactor Context |

The browser callback temporarily exposes `code` in the URL; **do not log/raw-trace the callback query**, and do not send it to analytics or third-party links. Never treat a code like a reusable password.

## 5. How Does Spring Security WebFlux Implement the Flow?

Key components:

| Class/Interface | Role |
| --- | --- |
| `ReactiveClientRegistrationRepository` | Boot creates registrations from `spring.security.oauth2.client.*` |
| `ClientRegistration` | Client metadata: client ID/secret, grant, redirect, scopes, provider endpoints |
| `DefaultServerOAuth2AuthorizationRequestResolver` | Builds the authorization request from the start URL and registration ID |
| `OAuth2AuthorizationRequestRedirectWebFilter` | Redirects the browser to the Authorization Endpoint |
| `WebSessionOAuth2ServerAuthorizationRequestRepository` | Stores pending requests/state in WebSession |
| `OAuth2LoginAuthenticationWebFilter` | Processes the code/state callback; authenticates OAuth2/OIDC |
| `OidcReactiveOAuth2UserService` | Processes OIDC user identity/UserInfo per configuration |
| `ReactiveOAuth2AccessTokenResponseClient` | Back-channel token exchange for OAuth2 code grant |
| `ServerSecurityContextRepository` | Saves/loads SecurityContext across requests |
| `ReactiveSecurityContextHolder` | Retrieves Authentication from Reactor Context |
| `OAuth2AuthenticationToken`/`OidcUser` | Authentication/principal after successful callback |
| `ServerOAuth2AuthorizedClientRepository` | Manages authorized clients and tokens when calling APIs |

Two-stage storage diagram:

```text
Before callback:
  /oauth2/authorization/keycloak
       -> WebSession stores OAuth2AuthorizationRequest + state

After successful callback:
  /login/oauth2/code/keycloak
       -> Authentication/OidcUser
       -> ServerSecurityContextRepository saves context
       -> browser continues using session cookie for /me
```

In WebFlux, request authentication resides in **Reactor Context**, not Servlet `ThreadLocal`. When reading the principal in a reactive service, use `ReactiveSecurityContextHolder.getContext()` or an appropriate argument resolver, avoiding `block()`.

## 6. Complete Java 17+, Spring Boot 3.3.13, and Keycloak Example

The project runs the Spring Client at `http://localhost:8080` and Keycloak at `http://localhost:9090`. This example is a local lab, **not** intended for public deployment over HTTP or with sample passwords.

### 6.1. Directory Structure

```text
webflux-oidc-code-flow/
  settings.gradle
  build.gradle
  src/
    main/
      java/example/OidcCodeFlowApplication.java
      resources/application.yml
    test/
      java/example/OidcCodeFlowApplicationTests.java
```

### 6.2. settings.gradle

```groovy
rootProject.name = 'webflux-oidc-code-flow'
```

### 6.3. build.gradle

```groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.13'
    id 'io.spring.dependency-management' version '1.1.7'
}

group = 'example'
version = '0.0.1-SNAPSHOT'

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-webflux'
    implementation 'org.springframework.boot:spring-boot-starter-security'
    implementation 'org.springframework.boot:spring-boot-starter-oauth2-client'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
```

Use the Spring Boot BOM to manage Spring Security, WebFlux, OIDC, and Reactor. **Do not add `spring-boot-starter-web`** when targeting WebFlux. Never copy `HttpSecurity`/Servlet `OAuth2LoginAuthenticationFilter` configuration into reactive `ServerHttpSecurity`.

### 6.4. application.yml

Create `src/main/resources/application.yml`:

```yaml
server:
  port: 8080

spring:
  security:
    oauth2:
      client:
        registration:
          keycloak:
            provider: keycloak
            client-id: webflux-login
            client-secret: ${OIDC_CLIENT_SECRET}
            client-authentication-method: client_secret_basic
            authorization-grant-type: authorization_code
            redirect-uri: "{baseUrl}/login/oauth2/code/{registrationId}"
            scope:
              - openid
              - profile
              - email
        provider:
          keycloak:
            issuer-uri: http://localhost:9090/realms/learning
```

Details:

- `registration.keycloak` ⇒ `registrationId=keycloak`, not the client ID.
- `client-id=webflux-login` must match the Keycloak client.
- `client-secret` comes from **environment variable `OIDC_CLIENT_SECRET`**, never committed to Git or embedded in JavaScript.
- `client_secret_basic` authenticates the Client at the **token endpoint**, unrelated to user passwords.
- `authorization_code` requests an authorization code grant.
- `openid` instructs Spring Security to use OIDC Login handling instead of only a generic OAuth2 user.
- `redirect-uri` uses the default template; `{baseUrl}` relies on the URL seen by the server after forwarded-header handling.
- `issuer-uri` lets Boot/Spring Security perform OIDC discovery to obtain authorization/token/JWK endpoints and the issuer. The IdP must be ready when Spring builds the registration; start Keycloak first.

### 6.5. Starting Local Keycloak

Requires Docker installed. On Linux/macOS:

```bash
docker run --rm --name keycloak-oidc-lab \
  -p 127.0.0.1:9090:8080 \
  -e KC_BOOTSTRAP_ADMIN_USERNAME=admin \
  -e KC_BOOTSTRAP_ADMIN_PASSWORD=admin \
  quay.io/keycloak/keycloak:26.8.2 \
  start-dev --hostname=http://localhost:9090
```

Host port `9090` differs from Spring Boot's `8080`; the container's internal port remains `8080`. In Windows PowerShell, enter the Docker command **on a single line** unless using PowerShell's line-continuation syntax.

**Lab only:** `start-dev`, `admin/admin`, and HTTP are unsuitable for production. Bind Redis/Keycloak/etc. only to localhost in labs; in real deployments, require HTTPS, strong credentials, Keycloak production mode, database/HA, and backups.

Open the Admin Console:

```text
http://localhost:9090/admin/
```

Log in with the demo admin credentials. Containers with `--rm` are deleted when stopped; dev Keycloak data may be lost. For longer-running study environments, configure a dedicated volume/test DB and reset policy.

### 6.6. Creating Realm, Client, and User

In the Keycloak Admin Console:

1. Create a realm named **`learning`**.
2. Switch to the `learning` realm and open **Clients → Create client**.
3. Choose **OpenID Connect**, Client ID **`webflux-login`**.
4. Enable **Client authentication** (confidential client).
5. Enable **Standard flow** to support Authorization Code Grant. There is no need to enable Direct Access Grants/password grant.
6. Set **Valid Redirect URIs** to the exact value:

```text
http://localhost:8080/login/oauth2/code/keycloak
```

7. You can set Home URL to `http://localhost:8080/`. **You do not need `Web origins: *`** for the OP to redirect the browser: the callback is a navigation, not a JavaScript CORS fetch.
8. Retrieve the Client secret on the **Credentials** tab according to assigned permissions, and pass it to the backend via `OIDC_CLIENT_SECRET`.
9. Open **Users**, create user `alice`, and set password **`learn`** in the lab. Choose non-temporary if you do not want to be forced to change the password on first login.
10. Verify the realm in the URL is `learning`, not the `master` admin realm.

Open OIDC discovery:

```text
http://localhost:9090/realms/learning/.well-known/openid-configuration
```

Or:

```bash
curl -fsS http://localhost:9090/realms/learning/.well-known/openid-configuration
```

The `issuer` field must be `http://localhost:9090/realms/learning`. If it shows a different host/port, fix Keycloak's hostname/network first; **do not disable issuer validation**.

### 6.7. Spring Boot Java Application

Create `src/main/java/example/OidcCodeFlowApplication.java`:

```java
package example;

import java.util.Map;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.http.MediaType;
import org.springframework.security.config.annotation.web.reactive.EnableWebFluxSecurity;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.context.ReactiveSecurityContextHolder;
import org.springframework.security.core.context.SecurityContext;
import org.springframework.security.oauth2.core.oidc.user.OidcUser;
import org.springframework.security.web.server.SecurityWebFilterChain;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;
import reactor.core.publisher.Mono;

import static org.springframework.security.config.Customizer.withDefaults;

@SpringBootApplication
@EnableWebFluxSecurity
@RestController
public class OidcCodeFlowApplication {

    public static void main(String[] args) {
        SpringApplication.run(OidcCodeFlowApplication.class, args);
    }

    @GetMapping(value = "/", produces = MediaType.TEXT_HTML_VALUE)
    public String home() {
        return """
            <!doctype html>
            <html lang="en">
            <head><meta charset="utf-8"><title>OIDC Code Flow</title></head>
            <body>
              <h1>Spring Security WebFlux OAuth2/OIDC Login</h1>
              <p><a href="/oauth2/authorization/keycloak">
                Sign in with Keycloak
              </a></p>
              <p><a href="/me">View logged-in identity</a></p>
            </body>
            </html>
            """;
    }

    @GetMapping("/public/ping")
    public Map<String, String> ping() {
        return Map.of("message", "PONG");
    }

    @GetMapping("/me")
    public Mono<Map<String, String>> me() {
        return ReactiveSecurityContextHolder.getContext()
                .map(SecurityContext::getAuthentication)
                .map(this::safeProfile);
    }

    private Map<String, String> safeProfile(Authentication auth) {
        String type = auth.getPrincipal() instanceof OidcUser
                ? "oidc" : "other";

        // Do not expose ID Token, access token, or session ID.
        return Map.of(
                "name", auth.getName(),
                "principalType", type);
    }

    @Bean
    SecurityWebFilterChain security(ServerHttpSecurity http) {
        return http
                .authorizeExchange(exchanges -> exchanges
                        .pathMatchers("/", "/public/**").permitAll()
                        .anyExchange().authenticated())
                .oauth2Login(withDefaults())
                .build();
    }
}
```

**Why is this code sufficient for Authorization Code/OIDC Login?**

- `ServerHttpSecurity.oauth2Login(withDefaults())` registers the OAuth2 login filters in the reactive `SecurityWebFilterChain`.
- `ReactiveClientRegistrationRepository` is created by Spring Boot from `application.yml`.
- The link on the home page calls the default start URL; the framework generates `state` and saves the pending authorization request.
- No callback controller is needed; Spring Security's filter intercepts `/login/oauth2/code/keycloak` and performs the token exchange.
- When OIDC login succeeds, the principal is `OidcUser`; `/me` reads Authentication from `ReactiveSecurityContextHolder` (Reactor Context), not Servlet ThreadLocal.
- `auth.getName()` is typically the configured subject/claim, **not automatically the display username `"alice"`**.
- The demo returns only two safe fields. Never return access tokens, ID tokens, client secrets, raw profile claims, or the WebSession ID.
- `/me` requires authentication; unauthenticated requests typically redirect to the login page/entry point configured by Spring Security.
- CSRF remains enabled by default. Do not add `csrf.disable()` just to make OAuth2 login work; logout and state-changing operations must still evaluate CSRF.
- The application defines no `UserDetailsService`/passwords; **Keycloak** authenticates the user.

### 6.8. Running Spring Boot

After Keycloak has the realm, client, and user created, set the secret.

Linux/macOS:

```bash
export OIDC_CLIENT_SECRET='your-real-keycloak-client-secret'
gradle bootRun
```

Windows PowerShell:

```powershell
$env:OIDC_CLIENT_SECRET = "your-real-keycloak-client-secret"
gradle bootRun
```

Replace the placeholder string with the real client secret in your lab; never commit secrets or paste them into tickets/chat. If you have a Gradle Wrapper, use `./gradlew bootRun` / `gradlew.bat bootRun`. If Spring Boot runs in a separate container, `localhost` inside the container means something different from the host; use DNS/networking consistent with the issuer and public redirect URL rather than blindly copying local config.

### 6.9. Running the End-to-End Flow in a Browser

1. Open `http://localhost:8080/`.
2. Open DevTools → Network and enable Preserve log.
3. Click **Sign in with Keycloak**; observe `GET /oauth2/authorization/keycloak`.
4. The start request returns 302 to `http://localhost:9090/realms/learning/protocol/openid-connect/auth` with `response_type=code`, `client_id=webflux-login`, `redirect_uri`, `state`, and scopes including `openid`.
5. Sign in to the Keycloak `learning` realm with `alice` / `learn`.
6. Keycloak redirects the browser back to `/login/oauth2/code/keycloak?code=...&state=...` on `localhost:8080`.
7. The Spring Client exchanges the code for tokens over the back-channel. The browser will not show the token endpoint POST in the Network tab because the call happens **from the backend**.
8. After the callback, Spring Security redirects according to the saved request/success handler.
9. Open `http://localhost:8080/me` in the same browser profile. Expected JSON response:

```json
{
  "name": "<subject-from-IdP>",
  "principalType": "oidc"
}
```

The `name` value is the principal ID per Keycloak/Spring Security, usually not the literal username `alice`. This is an **expected** result, not a log from a live run on the learner's machine.

10. Open a new Incognito window and go to `/me`: without the Client's session cookie, it restarts the login flow.
11. Clear the client cookie and visit `/me`: it may log back in very quickly if Keycloak still holds an SSO cookie; **an SSO session is distinct from the local client session**.
12. If the callback fails, never copy query strings containing code/state into shared logs. Use redacted diagnostics and the steps in section 11.

## 7. Testing with WebTestClient

There are **two levels**:

- **Spring filter/handler-level tests:** verify public routes, 302 authorization initiation, and authenticated principals via mocks.
- **E2E browser + IdP:** verify the user entering a password at Keycloak, real callback code/state, token exchange/JWK/ID Token validation, and session persistence.

`mockOidcLogin()` focuses on testing authorization/controllers **without proving** the IdP actually issues valid tokens. Never conflate the two types of results.

### 7.1. Creating the Test Class

Create `src/test/java/example/OidcCodeFlowApplicationTests.java`:

```java
package example;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.reactive.AutoConfigureWebTestClient;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.HttpHeaders;
import org.springframework.test.web.reactive.server.WebTestClient;

import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertTrue;
import static org.springframework.security.test.web.reactive.server
        .SecurityMockServerConfigurers.mockOidcLogin;

@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.MOCK)
@AutoConfigureWebTestClient
class OidcCodeFlowApplicationTests {

    @Autowired
    WebTestClient client;

    @Test
    void publicPingIsAvailableWithoutLogin() {
        client.get().uri("/public/ping")
                .exchange()
                .expectStatus().isOk()
                .expectBody()
                .jsonPath("$.message").isEqualTo("PONG");
    }

    @Test
    void anonymousProtectedEndpointRedirectsToLogin() {
        client.get().uri("/me")
                .exchange()
                .expectStatus().is3xxRedirection()
                .expectHeader().exists(HttpHeaders.LOCATION);
    }

    @Test
    void authorizationStartRedirectsWithStateAndCodeFlow() {
        var result = client.get()
                .uri("/oauth2/authorization/keycloak")
                .exchange()
                .expectStatus().is3xxRedirection()
                .returnResult(Void.class);

        String location = result.getResponseHeaders()
                .getFirst(HttpHeaders.LOCATION);

        assertNotNull(location);
        assertTrue(location.contains(
                "/realms/learning/protocol/openid-connect/auth"));
        assertTrue(location.contains("response_type=code"));
        assertTrue(location.contains("client_id=webflux-login"));
        assertTrue(location.contains("state="));
        assertTrue(location.contains("redirect_uri="));
    }

    @Test
    void mockOidcPrincipalCanReadMe() {
        client.mutateWith(mockOidcLogin())
                .get().uri("/me")
                .exchange()
                .expectStatus().isOk()
                .expectBody()
                .jsonPath("$.principalType").isEqualTo("oidc");
    }
}
```

Run when Keycloak already has the realm/client and a working discovery endpoint, because `issuer-uri` is used by Spring Boot when building the registration:

```bash
gradle test
```

**Verifying the right scope:**

- `@SpringBootTest(webEnvironment=MOCK)` + `@AutoConfigureWebTestClient` lets you test the WebFlux security chain inside the application context without a live HTTP port.
- `mockOidcLogin()` supplies a mocked OIDC Authentication to `/me`; it **does not call Keycloak**, nor does it verify codes, token exchange, or JWT signatures.
- The authorization-initiation test verifies the redirect to Keycloak, `state`, `response_type=code`, and the presence of `redirect_uri`. Because the test runs in a mock server context, `baseUrl` in the redirect URL may not be literally port `8080`; use a real browser to verify the public redirect URI.
- Do not test the callback with `code=fake` and expect a single fixed status everywhere; the failure handler may redirect to `/login?error` or respond differently depending on config/version. The **security criterion** is that no authenticated `SecurityContext` exists when `state`/`code` is invalid.

### 7.2. E2E Tests with a Real IdP

| Test | Action | Secure Outcome |
| --- | --- | --- |
| Happy path | Browser logs in at Keycloak and returns to client | `/me` 200, proper principal |
| Callback without state | Call callback with no pending request/state | Not authenticated |
| State mismatch | Callback with different state than saved | Rejected |
| Code replay | Reuse a code already exchanged for tokens | Rejected (single-use) |
| Expired code | Wait past IdP expiration | No login created |
| Wrong client secret | Token endpoint receives invalid auth | `invalid_client`, no secret leaked |
| Redirect mismatch | Wrong port/path configured at IdP | IdP rejects URI |
| Wrong ID token issuer/signature | Test IdP stub or misconfigured trust | Token validation fails closed |
| User denies consent | OP returns `error=access_denied` | Login fails, no context issued |
| Expired session | Pending request lost before callback | Not authenticated |
| Callback hits pod B | Start on A, callback hits B | Succeeds only when pending WebSession is shared |
| HTTPS reverse proxy | Public app URL HTTPS, upstream HTTP | Callback uses exact public scheme/host |

Tests with invalid tokens/codes should run in a test environment with dummy data; never log raw credentials or tokens. When using a test-container IdP, provision the realm/client/test user before the Spring context initializes.

## 8. Customizing the Callback Path in WebFlux

Default:

```text
/login/oauth2/code/{registrationId}
```

Suppose you want:

```text
/login/oauth2/callback/{registrationId}
```

**All three components must be updated:**

### 8.1. Matcher in the Reactive Security Chain

Replace `.oauth2Login(withDefaults())` with:

```java
.oauth2Login(oauth2 -> oauth2
    .authenticationMatcher(
        new PathPatternParserServerWebExchangeMatcher(
            "/login/oauth2/callback/{registrationId}")))
```

Import:

```java
import org.springframework.security.web.server.util.matcher.PathPatternParserServerWebExchangeMatcher;
```

This is a **fragment to substitute into the class in section 6**, not a standalone runnable class. The API here is **WebFlux's `ServerHttpSecurity.oauth2Login(...).authenticationMatcher(...)`**. Do not copy Servlet's `HttpSecurity.oauth2Login().redirectionEndpoint().baseUri(...)` API into reactive code.

### 8.2. Client Registration Redirect URI

Update the existing property to:

```yaml
spring:
  security:
    oauth2:
      client:
        registration:
          keycloak:
            redirect-uri: "{baseUrl}/login/oauth2/callback/{registrationId}"
```

This is a YAML fragment illustrating a single property. **Edit/merge** it into the existing `application.yml` rather than pasting the whole block and creating duplicate keys.

### 8.3. Keycloak Valid Redirect URIs

For the lab, register:

```text
http://localhost:8080/login/oauth2/callback/keycloak
```

Do not keep `/login/oauth2/code/keycloak` and expect the OP to send callbacks to the new path. When deploying over public HTTPS, register the corresponding public URI.

### 8.4. Customizing the Authorization Initiation URL Is Separate

Changing the start URL `/oauth2/authorization/keycloak` to `/login/oauth2/authorization/keycloak` requires customizing `ServerOAuth2AuthorizationRequestResolver`/`ServerWebExchangeMatcher` and updating the login link. It **does not automatically change the callback**. Keep these two concerns separate to avoid 404s/redirect loops.

## 9. Reverse Proxy, HTTPS, and baseUrl

Typical production topology:

```text
Browser: https://app.example.test
       |
       v
Ingress / TLS termination
       |
       v
WebFlux upstream: http://app:8080
```

With the `{baseUrl}` template, if the app is not given the proper public host/scheme, it may wrongly generate:

```text
http://app:8080/login/oauth2/code/keycloak
```

whereas Keycloak only permits:

```text
https://app.example.test/login/oauth2/code/keycloak
```

This is a proxy/base URL configuration error, **not** a role or CORS error.

### 9.1. Forwarded Headers in Spring Boot

Boot WebFlux can use:

```yaml
server:
  forward-headers-strategy: framework
```

Spring Framework processes `Forwarded`/`X-Forwarded-*` headers via `ForwardedHeaderTransformer` in the reactive stack. **Enable this only behind a trusted reverse proxy**: the ingress must strip/overwrite forwarded headers forged by external Internet clients, and the upstream application must be isolated so it cannot receive spoofed headers directly.

Some deployments prefer `server.forward-headers-strategy=native` when the web server supports it cleanly; consult Boot documentation and test in reality. Never set a flag and assume `redirect_uri` is right without checking the URL in browser DevTools Network.

### 9.2. Fixed Redirect URI

If there is only a single public origin, you can use:

```yaml
spring:
  security:
    oauth2:
      client:
        registration:
          keycloak:
            redirect-uri: "https://app.example.test/login/oauth2/code/keycloak"
```

This avoids wrong base URLs but requires separate configs for staging/dev; never hardcode production URLs across all environments. Maintain an exact allowlist at the IdP without opening broad wildcards.

### 9.3. Things That Must Align

- Public scheme HTTPS/HTTP.
- Public hostname; `localhost` differs from `127.0.0.1`.
- Public port; default `443` differs from `8443`.
- Context path/reverse proxy prefix.
- Callback path and registration ID.
- IdP issuer hostname/port; `iss` in the ID Token must match the registered issuer.
- Cookie domain/path/SameSite/Secure when the browser returns from the IdP.

**When an IdP publishes an internal issuer different from the public one** (e.g., ID Token `iss=http://keycloak:8080/realms/...` while the client configures a public HTTPS URL), fix Keycloak's canonical hostname/networking; **never skip issuer validation**.

## 10. Sessions, Multiple Nodes, SameSite, and Login State

Spring Security stores the pending authorization request in `WebSession`. When the browser returns to the callback, the **client's session cookie** must resolve to the same session.

```text
Node A: GET /oauth2/authorization/keycloak
  -> pending request with state S in WebSession I
  -> browser receives Cookie SESSION=I

IdP redirect callback
  -> GET /login/oauth2/code/keycloak?code=C&state=S
  -> browser sends Cookie SESSION=I

Node A/B:
  -> load WebSession I
  -> look up pending request state S
  -> match and process C
```

### 10.1. If the Callback Hits a Different Node

If `WebSession` lives only in each process's RAM:

```text
Start on node A -> pending session exists only on A
Callback hits node B -> B does not see state -> login fails
```

**Reactive Spring Session Redis** can provide a `ReactiveSessionRepository` sharing `WebSession` across nodes, including both pending authorization requests and security contexts. All nodes must share the same Redis, namespace, serializer, secrets/config, session TTL, and cookie policy. Sticky sessions reduce node hopping but do not survive node failures.

**Never work around this by disabling `state` or putting codes into arbitrary query parameters.**

### 10.2. SameSite Cookies

An OAuth redirect is a top-level navigation; a `SameSite=Lax` cookie under normal conditions can be sent when the browser returns to the client via GET. `SameSite=Strict` may prevent the cookie from being sent on cross-site navigations; `SameSite=None; Secure` requires HTTPS and introduces different CSRF considerations to review. Browser privacy settings can also have an effect.

Never treat `Access-Control-Allow-Origin` as a switch to allow callback cookies: **CORS does not govern top-level OAuth navigations**. Never enable a CORS wildcard on the token endpoint so the browser can send a client secret; a confidential client should exchange codes on the backend.

### 10.3. Session Fixation and Local Logout

After login, the session ID may change due to session-fixation protection; when testing, always keep the **latest cookie**. Never rely on the pre-login session ID.

Application local logout does not necessarily clear the Keycloak SSO session. Returning to the IdP may log the user back in automatically. **OIDC RP-Initiated Logout** is a separate flow requiring dedicated configuration at both RP and OP. Revoking access/refresh tokens is also distinct from deleting the `WebSession`.

With Spring Security cookie-backed browser login, `POST /logout` requires a CSRF token. Never disable CSRF just because OIDC is used.

## 11. Diagnosing Authorization Code and Callback Errors

### 11.1. `invalid_redirect_uri` / `redirect_uri_mismatch`

The IdP rejected the callback sent by the client in the authorization request. Compare:

- The request's `redirect_uri` in browser Network (URL-decoded).
- `registration.keycloak.redirect-uri` in Spring.
- The default or custom reactive callback matcher.
- **Valid Redirect URIs** on the right realm/client in the IdP.
- Scheme, hostname, port, prefix/trailing slash, and proxy headers.

**Fix the exact URI** rather than opening wildcards or disabling redirect checks.

### 11.2. `authorization_request_not_found`

Spring Security could not find a pending authorization request:

- The `SESSION` cookie was not sent back on the callback;
- The session expired or was newly initialized;
- The callback hit a node not sharing sessions;
- Concurrent login flows overwrote/lost the pending state;
- Different origin/host between initiation and callback;
- Redis session store failure;
- The request was already consumed or the callback was replayed.

Fix the session/cookie/Redis/host issue; **never disable state validation**.

### 11.3. `invalid_grant`

The token endpoint rejected the code because it expired, was already used, had the wrong client/`redirect_uri`, failed PKCE verifier check, or violated an IdP policy. Do not retry the same code with `curl` to “fix” it; codes are single-use. Start a fresh login flow.

### 11.4. `invalid_client`

Wrong Client ID/secret, auth method mismatch, wrong realm, secret rotated without updating the backend, or confidential/public mode mismatch. Never disable client authentication for a confidential client to bypass the error; synchronize the ClientRegistration and credentials.

### 11.5. State Mismatch

When the browser returns a `state` differing from the saved request, Spring must reject it. Never turn this failure into a fresh login assuming the user “already authenticated at Keycloak”. Check cookies, multiple tabs, session stores, callback reuse, and security chains.

### 11.6. Callback 404

`redirect-uri` may have been changed while `authenticationMatcher` stayed on the default, or the request hit a different security chain. Ensure both `/oauth2/authorization/{registrationId}` and `/login/oauth2/code/{registrationId}` are handled by the chain with OAuth2 login enabled.

### 11.7. Redirect Loop

When the session fails to save Authentication or the callback fails, `/me` can redirect to login endlessly. Check:
- Were a valid code and state actually received?
- Did the token endpoint call succeed?
- Did ID Token verification pass?
- Was the SecurityContext saved to the session?
- Did the browser send the cookie on the post-login request?
- Is the user logged in, yet blocked by an authorization rule on `/me`?

### 11.8. Issuer Mismatch or Invalid JWT Signature

`issuer-uri` has the wrong host/port/realm, Keycloak returns an issuer different from the canonical URL, or JWK keys rotated/misconfigured. Inspect the discovery document and ID Token metadata in **redacted** logs; never disable signature or issuer validation.

### 11.9. Provider Returns `error=access_denied`

The user declined consent, IdP policy denied access, or authentication failed. The OP may redirect to the callback with `error=access_denied&state=...`; Spring treats this as an authentication failure. Never treat it as a valid code and never render raw `error_description` on error pages.

### 11.10. CORS Error at the Token Endpoint

If frontend JavaScript calls the token endpoint directly with a client secret, that is **not** the confidential server-side OAuth2 Login covered in this lesson. Client secrets must never be placed in the browser. For public-client SPAs, use Authorization Code + PKCE with proper token/CORS/storage design per standard; never paste a backend secret into JS to work around CORS.

### 11.11. Multiple SecurityWebFilterChains

`WebFilterChainProxy` selects only the first chain matching the request. If authorization start matches chain A and the callback hits chain B without OAuth2 login enabled, the flow breaks. Check `@Order`/`securityMatcher`/`authorizeExchange` and gateway rewrites across start, callback, and business routes.

### 11.12. HTTP Status Is Not the Whole Truth

OAuth errors often surface as a **302 redirect to a login error page** rather than 400/401/403. When testing, verify:

- Is there an `Authentication` after the flow?
- Is a SecurityContext loaded on `GET /me`?
- Did real token exchange/ID token validation occur?
- Are the session cookie and state correlation working?
- Are there any leaks of codes/tokens in URLs or logs?

## 12. Authorization After OIDC Login

OIDC login verifies identity; it **does not automatically grant `ROLE_ADMIN`** or permission to read someone else's documents.

An `OidcUser` may contain `sub`, `preferred_username`, `email`, and other claims depending on the provider. `email` may be absent or unverified; `preferred_username` can change. For critical business logic, key users by **issuer + subject** or map to an immutable internal user ID.

Spring Security OAuth2 login can assign authorities such as `OIDC_USER` and `SCOPE_*` per provider/mapping. Never treat every OIDC subject as `ROLE_USER`/`ROLE_ADMIN` unless explicitly configured.

If the app needs to enforce:

- Users can view only their own orders;
- A tenant A admin cannot access tenant B;
- A service allows only users with matching scopes/roles;

then after login, use `ReactiveAuthorizationManager` and reactive method/service authorization reading permissions/ownership from a trusted source. Never take roles from a query/header or a client-editable field.

**ID Tokens are for the RP**, not access tokens for every API; to call a Resource Server, use an access token with the right audience/scope and an appropriate `OAuth2AuthorizedClient`/WebClient setup.

## 13. Logging, Cookies, and Production Security

### 13.1. Do Not Log Secrets

Never include any of the following in app logs, reverse-proxy access logs, analytics, or public distributed traces:

- `code=...`, `code_verifier`;
- `client_secret`;
- raw access/ID/refresh tokens;
- session cookie IDs;
- raw `state`/`nonce`;
- complete callback query strings;
- credentials or entire `SecurityContext` objects.

You may record `registrationId`, non-sensitive issuer, event stage, error code, HTTP status, latency, and redacted/sanitized correlation IDs.

### 13.2. Baseline Requirements

1. **HTTPS** for the public Client/IdP and token endpoint; never use HTTP outside local labs.
2. **Exact redirect URI allowlist**, no broad wildcards or open redirects.
3. **Fail-closed state correlation**; never bypass callbacks missing a pending request.
4. **PKCE** for public clients; evaluate enabling it for confidential clients per IdP/current best practices.
5. **Client secrets** stored strictly on the backend/secret store, with controlled rotation.
6. **ID Token validation**: signature, issuer, audience, expiry, and nonce per OIDC.
7. **Cookies** with Secure/HttpOnly/SameSite/Path/Domain fitting the flow and reasonable timeouts.
8. **Shared session storage** when scaling across multiple nodes; both pending requests and authenticated contexts must persist.
9. **Proxy trust**: forwarded headers controlled by ingress; never trust headers supplied by Internet clients.
10. **Role mapping** from trusted sources with authorization enforced in services.
11. **CSRF** on cookie-authenticated browser state-changing requests; OIDC does not replace CSRF.
12. **Logout**: distinguish local logout, OP SSO logout, and token revocation.
13. **Multi-environment**: separate issuers, redirect URIs, and secrets across dev/staging/prod.
14. **Regression tests**: start URL, callback, state, PKCE, cookies, ID tokens, and HTTPS/public URLs.
15. **Metrics**: provider latency, token exchange errors, callback failures, lost session state, and user login failures.
16. **Never use lab sample secrets** like `admin/admin` or `alice/learn` in production.

## 14. Layer-by-Layer QA Practices

| Layer | Tool | What to Verify |
| --- | --- | --- |
| Client registration | Spring configuration + discovery URL | client ID, issuer, endpoints, redirect-uri |
| Authorization redirect | Browser Network / HTTP 302 | `response_type=code`, `client_id`, `state`, `redirect_uri` |
| IdP | Keycloak Admin + test user | realm/client/standard flow/valid redirects |
| Callback | Browser Network | `code`/`state` hit exact Spring path without 404 |
| Token exchange | Redacted backend metrics/logs | exchange succeeds without exposing secrets |
| OIDC verification | Integration test + IdP | ID token issuer/audience/signature/nonce valid |
| WebSession | Browser cookies/Redis metrics | pending state and SecurityContext survive redirects |
| Controller | `GET /me` | `principalType` `oidc`, no tokens leaked |
| Security negative | Fake state/replayed code/fake issuer | not authenticated |
| Reverse proxy | Staging HTTPS | public `redirect_uri` right; cookies right |
| Multi-node scale | Start node A → callback node B | valid shared state or fail-closed error |

**`curl` only inspects redirect headers**; it does not execute full IdP login with cookies, CSRF, consent, and callbacks. A browser or user-agent-driving test framework is generally required for E2E.

## 15. Self-Check Questions

**1. Which Spring WebFlux URL starts OAuth2 login?**  
`/oauth2/authorization/{registrationId}`, for example `/oauth2/authorization/keycloak`.

**2. Where is the default callback in Spring Security reactive?**  
`/login/oauth2/code/{registrationId}`, for example `/login/oauth2/code/keycloak`.

**3. Is `/oauth2/authorization/keycloak` a Keycloak URL?**  
No. It is a **Client** endpoint used to build and redirect the authorization request to the OP.

**4. The IdP redirects to the callback with `code` and `state`; should the client process the code in a custom controller?**  
No. `OAuth2LoginAuthenticationWebFilter` handles the callback; writing it yourself risks skipping security checks.

**5. Is `client_id` always equal to `registrationId`?**  
No. This lesson uses `client_id` `webflux-login` and `registrationId` `keycloak`.

**6. Why is `state` important?**  
It binds the callback to the authorization request initiated from the same session, helping prevent login CSRF/callback injection.

**7. How does PKCE differ from `state`?**  
PKCE binds the code exchange to `code_verifier`; `state` binds the authorization response to the request.

**8. For a confidential client, does Spring Security always enable PKCE automatically?**  
Do not assume so. Auto-PKCE applies clearly to eligible public clients or when `requireProofKey` is enabled; inspect the provider/request when PKCE is required.

**9. What does the `openid` scope do?**  
Requests OIDC authentication and an ID Token, enabling Spring Security to handle OIDC-specific login.

**10. Can an authorization code be used to call APIs long-term like an access token?**  
No. The code is short-lived and single-use to obtain tokens; the access token is for calling a Resource Server with matching audience/scope.

**11. Does the browser see the token endpoint POST?**  
In a server-side confidential client, the token POST is a backend request, not a browser JavaScript fetch.

**12. Why does the callback report `authorization_request_not_found` even when IdP login succeeded?**  
Usually because the pending request/state in `WebSession` is gone or the cookie/session could not be loaded properly.

**13. Where must changes be made to customize the callback path?**  
Reactive `oauth2Login().authenticationMatcher(...)`, `ClientRegistration.redirectUri`, and Valid Redirect URIs at the IdP.

**14. Why doesn't a CORS wildcard fix an OAuth callback?**  
Callbacks are top-level browser redirects; CORS governs JavaScript reading cross-origin responses, not callbacks/sessions.

**15. How should an HTTPS reverse proxy causing a wrong `redirect_uri` be fixed?**  
Fix forwarded headers/trust boundaries or use an environment-specific fixed public `redirect-uri`; never open wildcards.

**16. Two pods of the same app: login starts on A, callback hits B, and state disappears. Why?**  
The pending authorization request lives in node A's session; you need reactive Spring Session Redis/shared state or equivalent HA architecture.

**17. Does `mockOidcLogin()` prove Keycloak issued a valid ID Token?**  
No. It mocks an OIDC Authentication; E2E/browser+OP tests are needed to verify exchange and validation.

**18. Does successful OIDC login mean the user has `ROLE_ADMIN`?**  
No. Authorization/roles/tenant ownership must be mapped and enforced separately.

**19. Does local logout always end the SSO session at Keycloak?**  
No. OIDC provider logout and token revocation require separate mechanisms.

**20. Can you paste a client secret or authorization code into an issue while debugging?**  
No. Use only redacted logs/traces, restricted access, and dummy data when reproducing issues.

**Remember:** The Authorization Code Flow in WebFlux follows **start URL → IdP authorize/login → callback code+state → back-channel token exchange → OIDC principal + session**. The callback address must align across the Client Registration, WebFlux authentication matcher, and IdP allowlist. Flow security depends on **`state`, proper PKCE, issuer/ID Token validation, HTTPS, server-side client secrets, and stable cookies/WebSession** — not merely receiving an HTTP 302.

## Official Documentation

- [Spring Security — Reactive OAuth2 Login Core](https://docs.spring.io/spring-security/reference/reactive/oauth2/login/core.html): `ClientRegistration`, `oauth2Login`, and default redirect URI.
- [Spring Security — Reactive OAuth2 Login Advanced](https://docs.spring.io/spring-security/reference/reactive/oauth2/login/advanced.html): custom `authenticationMatcher` callback, OAuth2 Login Page, OIDC user service.
- [Spring Security — Reactive OAuth2 Authorization Code](https://docs.spring.io/spring-security/reference/reactive/oauth2/client/authorization-grants.html): authorization initiation, state repository, and PKCE.
- [Spring Security — OAuth2 WebFlux](https://docs.spring.io/spring-security/reference/reactive/oauth2/): OAuth2 Client vs. Resource Server, OIDC endpoints, and token types.
- [Spring Security — Testing Reactive OAuth2/OIDC](https://docs.spring.io/spring-security/reference/reactive/test/web/oauth2.html): `mockOidcLogin()` and testing model.
- [Spring Boot 3.3 — OAuth2 Clients](https://docs.spring.io/spring-boot/3.3/reference/web/spring-security.html): client/provider properties, reactive registration.
- [Spring Boot 3.3 — Behind a Proxy](https://docs.spring.io/spring-boot/3.3/how-to/webserver.html): `server.forward-headers-strategy`.
- [Keycloak — Docker Getting Started](https://www.keycloak.org/getting-started/getting-started-docker): start-dev/realm/client/user.
- [Keycloak — Server Administration](https://www.keycloak.org/docs/latest/server_admin/): OIDC clients and valid redirect URIs.
- [OAuth 2.0 Authorization Framework — RFC 6749](https://www.rfc-editor.org/rfc/rfc6749): authorization code, redirect URI, token exchange.
- [PKCE — RFC 7636](https://www.rfc-editor.org/rfc/rfc7636): `code_challenge` and `code_verifier`.
- [OAuth 2.0 Security Best Current Practice — RFC 9700](https://www.rfc-editor.org/rfc/rfc9700): OAuth2 security.
- [OpenID Connect Core 1.0](https://openid.net/specs/openid-connect-core-1_0.html): ID Token, nonce, issuer, audience, and code flow.
