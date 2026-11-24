# Distinguishing Local Logout, Token Revocation, and External Identity Provider Logout

## Lesson Objectives

In a Spring Security application, the word **"logout"** can refer to three completely different actions:

1. **Local logout:** terminating the session and Authentication of the **current application**.
2. **Token revocation:** instructing the issuing system or verification store to make an **access token, refresh token, or long-lived credential** no longer usable.
3. **External identity provider logout (federated / Identity Provider logout):** terminating the **SSO session at the OpenID Provider or Identity Provider**, sometimes coordinating logout notifications to other applications.

These three actions can happen together, yet **none of them automatically implies the other two**. A simple-looking "Log out" button in the UI may require a multi-step, multi-system, multi-credential workflow.

After this lesson, you will be able to:

- Explain the responsibility boundaries of **Spring Security LogoutFilter**, **OAuth 2.0 revocation endpoint**, **OIDC RP-Initiated Logout / Back-Channel Logout**, and **SAML Single Logout (SLO)**.
- Explain why deleting `JSESSIONID` does not automatically revoke access tokens, and why revoking a refresh token does not necessarily stop an existing JWT access token from being accepted immediately.
- Configure standard **local logout** in Spring Boot Servlet and verify it with Java 17+ / curl.
- Integrate **OIDC RP-Initiated Logout** using `OidcClientInitiatedLogoutSuccessHandler` when a supporting OIDC Provider is present.
- Write a Java 17 client sending an **RFC 7009 token revocation request** to an Authorization Server, while understanding the limits of HTTP 200.
- Design proper test scenarios for "log out on this device", "log out all devices", and "log out of SSO".

**Scope:** Spring Security **Servlet** (Spring Boot / Spring MVC) and OAuth 2.0, OpenID Connect 1.0, SAML 2.0 standards. In WebFlux, filter classes, sessions, and configuration APIs differ. The local logout example runs without an IdP; OIDC/revocation examples **require a real provider** for end-to-end testing.

## 1. Drawing the Boundaries of Each System

A system using SSO typically has at least four state layers:

~~~text
                        Browser
                     /      |       \
                    v       v        v
             App Cookie  IdP Cookie  Access/Refresh token
                    |       |        |
                    v       v        v
           +--------------+  +-------------------+
           | Application A|  | Identity Provider |
           | HttpSession  |  | (OP / IdP)         |
           | SecurityCtx  |  | SSO session        |
           +--------------+  +-------------------+
                    |                   |
                    v                   v
             Resource API          Token service
                /                      |
               v                       v
        Token validator          Revocation store
~~~

**Facts to remember:**

- **App session** and **IdP session** usually use cookies on **different domains**, issued by two separate parties.
- **OAuth access token** is a credential to access APIs; it does not necessarily have a one-to-one link with the browser's HttpSession.
- **Refresh token** lets a client obtain new access tokens; stopping new token issuance and stopping acceptance of old tokens are two separate problems.
- **OpenID Connect ID token** attests to the login event and carries user info. It is **not** an access token for calling APIs, nor is it a logout command.
- Applications A and B can both log in from the same IdP while keeping **two separate local sessions**. Destroying A does not mean B automatically disappears.
- Deleting cookies in the current browser does not delete stolen cookie copies, does not destroy all server sessions, and does not invoke the revocation endpoint.

Before writing logout logic, answer clearly: **log out what, where, on which devices, how fast, and with what guarantee?**

## 2. Comparison Table of the Three Operations

| Criterion | Local logout | Token revocation | Logout at IdP |
| --- | --- | --- | --- |
| **Where it runs** | Application / Relying Party (RP) | Authorization Server or issuer's token store | OpenID Provider / SAML Identity Provider |
| **Primary target** | HttpSession, SecurityContext, app cookies | Refresh token, access token, or credential to revoke | Provider's SSO login session |
| **Typical mechanism** | `POST /logout`, `LogoutFilter` | OAuth RFC 7009 `POST /revoke` or provider API | OIDC `end_session_endpoint`, back-channel/front-channel; SAML SLO |
| **Requires a browser?** | Usually yes for browser apps, optional for APIs | No; client/backend can call directly | RP-Initiated usually redirects browser; back-channel is server-to-server |
| **Affects other apps?** | Not by default | Depends on apps sharing the revoked token/grant | Depends on IdP capabilities and each RP's SLO support |
| **Affects unexpired access JWT?** | Not by default | May not be immediate if resource server verifies JWT offline | Not by default |
| **Affects refresh token?** | Not by default | Yes if requested and supported by server | Depends on IdP/authorization server policy |
| **Can log out all devices?** | Requires destroying all sessions for the user | Requires revoking all related grants/refresh tokens per policy | Depends on IdP session scope, SLO, and each app's sessions |

Do not use a `"logout=true"` flag in the UI as proof that every token/session everywhere has been revoked.

## 3. Local Logout in Spring Security Servlet

### 3.1. What Does LogoutFilter Do?

When an app uses standard Spring Security Servlet, the framework supports the `/logout` endpoint. With CSRF enabled, **GET /logout** usually displays a confirmation page; **POST /logout** with a valid CSRF token executes logout.

Standard `LogoutHandler`s perform tasks such as:

- **SecurityContextLogoutHandler:** invalidates HttpSession as configured, removes SecurityContext from holder/repository.
- **RememberMeServices:** cleans up the remember-me cookie and, if using persistent remember-me, can delete server-side remember-me tokens.
- **CsrfLogoutHandler:** deletes the saved CSRF token on logout.
- **LogoutSuccessEventPublishingLogoutHandler:** publishes a logout event.
- **LogoutSuccessHandler:** decides the response/redirect after cleanup, such as redirecting to `/login?logout` or returning HTTP 204.

Diagram:

~~~text
POST /logout + valid CSRF
       |
       v
    LogoutFilter
       |
       +--> invalidate HttpSession (if configured)
       +--> clear SecurityContext
       +--> cleanup remember-me
       +--> cleanup CSRF / publish event
       |
       v
    LogoutSuccessHandler
       |
       +--> HTTP 302 to a public page
         OR HTTP 204 for API
~~~

### 3.2. What Does Local Logout NOT Do?

If only local logout is configured:

- Does not automatically call the **OAuth token revocation endpoint** at the Authorization Server.
- Does not automatically destroy the **SSO session cookie at the IdP**.
- Does not automatically destroy HttpSessions of **application B** or other sessions of application A on other devices.
- Does not automatically invalidate copied JWT access tokens across every API.
- Does not automatically revoke refresh tokens stored by a backend client, unless the app implements custom logic or provider integration.
- Does not guarantee all browser cookies are deleted if domain/path settings mismatch.

**Very common scenario:** the user clicks "Log out" in A, A's session is destroyed; they click "Log in" again and are routed through the IdP which still holds an SSO session, so the IdP logs them back into A **without asking for a password**. That is not necessarily a local logout bug: you never asked the IdP to log out.

### 3.3. Use POST and CSRF Instead of Logout via GET

A GET logout endpoint is easily triggered by images, links, prefetching, or external pages. In cookie-based browser apps, keep CSRF protection and use **POST /logout**.

Do not disable CSRF globally just to "make logout work". If the app is a stateless API with Bearer tokens explicitly sent in headers, the threat model can differ; always decide based on how the client sends credentials, not merely on a "REST" label.

### 3.4. Where Can Writing Your Own Logout Controller Go Wrong?

If you only do:

~~~java
// Illustrative snippet NOT sufficient to replace LogoutFilter.
SecurityContextHolder.clearContext();
return ResponseEntity.noContent().build();
~~~

You have only cleared the context for the current request, while HttpSession, SecurityContextRepository, cookies, remember-me, and other handlers may remain untouched. In Spring Security 6, use **`http.logout(...)`** or invoke the proper LogoutHandlers for a clear reason; do not merely clear a ThreadLocal and claim a complete logout.

## 4. Runnable Example: Local Logout with Spring Boot + Java 17

This example intentionally **has no OAuth or IdP**. It demonstrates proper local logout so you can compare it with the federated flows in later sections.

### 4.1. Gradle Project

Requires Java 17+ and a Spring Boot-compatible Gradle wrapper. Create:

~~~text
local-logout-demo/
  settings.gradle
  build.gradle
  src/main/java/example/logout/LocalLogoutApplication.java
~~~

**settings.gradle**:

~~~groovy
rootProject.name = 'local-logout-demo'
~~~

**build.gradle**:

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.5.8'
    id 'io.spring.dependency-management' version '1.1.7'
}

repositories {
    mavenCentral()
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-security'
}
~~~

### 4.2. Complete Java Code

Create **src/main/java/example/logout/LocalLogoutApplication.java**:

~~~java
package example.logout;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.http.HttpStatus;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.http.SessionCreationPolicy;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.crypto.factory.PasswordEncoderFactories;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.security.web.authentication.logout.HttpStatusReturningLogoutSuccessHandler;
import org.springframework.security.web.csrf.CsrfToken;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@SpringBootApplication
public class LocalLogoutApplication {

    public static void main(String[] args) {
        SpringApplication.run(LocalLogoutApplication.class, args);
    }

    @Bean
    PasswordEncoder passwordEncoder() {
        return PasswordEncoderFactories.createDelegatingPasswordEncoder();
    }

    @Bean
    UserDetailsService users(PasswordEncoder encoder) {
        return new InMemoryUserDetailsManager(
            User.withUsername("demo")
                .password(encoder.encode("change-me"))
                .roles("USER")
                .build()
        );
    }

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http)
            throws Exception {
        http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/csrf").permitAll()
                .anyRequest().authenticated()
            )
            .sessionManagement(session -> session
                .sessionCreationPolicy(SessionCreationPolicy.IF_REQUIRED)
            )
            .formLogin(Customizer.withDefaults())
            .logout(logout -> logout
                .invalidateHttpSession(true)
                .clearAuthentication(true)
                .logoutSuccessHandler(
                    new HttpStatusReturningLogoutSuccessHandler(
                        HttpStatus.NO_CONTENT
                    )
                )
            );
        return http.build();
    }

    @RestController
    public static class Api {

        public record CsrfInfo(String headerName, String token) {}
        public record MeInfo(String username) {}

        @GetMapping("/csrf")
        public CsrfInfo csrf(CsrfToken token) {
            return new CsrfInfo(
                token.getHeaderName(), token.getToken()
            );
        }

        @GetMapping("/me")
        public MeInfo me(Authentication authentication) {
            return new MeInfo(authentication.getName());
        }
    }
}
~~~

**Reasons for the configuration:**

- **IF_REQUIRED:** Spring Security creates a session when needed; form login can persist Authentication into HttpSession.
- **formLogin:** uses the standard authentication mechanism without writing a custom login controller, so you do not need to manually handle all `SecurityContextRepository.saveContext(...)` steps.
- **logout:** invalidates the session and clears Authentication; returns **204 No Content** for easy API usage. This is **local** handling, with no code calling an IdP or revoking OAuth tokens.
- **/csrf:** supplies a CSRF token for clients testing form POSTs; no need to disable CSRF.
- **demo/change-me:** learning account; production uses a proper user store and password policy.

The example does not enable `oauth2Login()`, has no `OAuth2AuthorizedClientService`, and has no access/refresh tokens, so nothing can be concluded about token revocation from this demo.

### 4.3. Running and Testing Local Logout

In the project directory:

~~~bash
./gradlew bootRun
~~~

On Windows PowerShell:

~~~powershell
.\gradlew.bat bootRun
~~~

The app runs by default at **http://localhost:8080**. The following commands use **Bash/WSL/Git Bash, curl, and Python 3**.

**Step 1 — fetch CSRF token and session cookie:**

~~~bash
csrf=$(curl -fsS -c cookies.txt \
  http://localhost:8080/csrf \
  | python3 -c 'import sys,json; print(json.load(sys.stdin)["token"])')
test -n "$csrf"
~~~

**Step 2 — form login with cookie and CSRF token:**

~~~bash
curl -i -b cookies.txt -c cookies.txt \
  -H "X-CSRF-TOKEN: $csrf" \
  --data-urlencode "username=demo" \
  --data-urlencode "password=change-me" \
  http://localhost:8080/login
~~~

The result is typically a **302 redirect** after successful login. Spring Security may rotate the session ID to protect against session fixation; the cookie jar is updated if the server returns Set-Cookie.

**Step 3 — use the new session to access a protected endpoint:**

~~~bash
curl -sS -b cookies.txt http://localhost:8080/me
# {"username":"demo"}
~~~

This is **Authentication from this application's session**, not an IdP session.

**Step 4 — fetch a fresh CSRF token (the old token may be rotated after login):**

~~~bash
csrf=$(curl -fsS -b cookies.txt -c cookies.txt \
  http://localhost:8080/csrf \
  | python3 -c 'import sys,json; print(json.load(sys.stdin)["token"])')
~~~

**Step 5 — POST logout using the same session:**

~~~bash
curl -i -b cookies.txt -c cookies.txt \
  -H "X-CSRF-TOKEN: $csrf" \
  -X POST http://localhost:8080/logout
# HTTP/1.1 204 (expected status line)
~~~

**Step 6 — try reusing the old cookie:**

~~~bash
curl -i -b cookies.txt http://localhost:8080/me
# Typically 302 to /login, because Authentication is gone
~~~

Do not rigidly expect 401 in a **formLogin** example: with a form entry point, anonymous requests are usually redirected to `/login`. The 204 code on the logout step is explicitly configured; detailed headers depend on the Servlet container.

**What was proved:** the local session is destroyed and subsequent requests are no longer locally logged in. **What was not proved:** that OAuth/SSO/other application tokens were revoked.

## 5. Token Revocation Under OAuth 2.0 RFC 7009

### 5.1. What Is a Revocation Endpoint?

OAuth 2.0 Token Revocation (RFC 7009) specifies that a client can send an **HTTP POST** to the **Authorization Server**'s revocation endpoint to notify it that a token should no longer be used.

Conceptual request:

~~~http
POST /oauth2/revoke HTTP/1.1
Host: authorization-server.example
Content-Type: application/x-www-form-urlencoded
Authorization: Basic <encoded client credentials>

token=<token-value>&token_type_hint=refresh_token
~~~

The path `/oauth2/revoke` is only an example; the **real address is published by the Authorization Server**. Never guess an IdP's revocation URL. For a confidential client, client authentication typically uses client ID/secret, `private_key_jwt`, mTLS, or another server-supported mechanism.

Common parameters:

- **token:** the token value to revoke; send over an HTTPS connection.
- **token_type_hint:** hint about the token type, typically `refresh_token` or `access_token`; it is only a **hint** and does not guarantee the issuer searches only that type.
- **client authentication:** ensures the client is authorized to request revocation of tokens belonging to the corresponding authorization grant/client.

**RFC 7009 requires support for revoking refresh tokens and recommends supporting access tokens**, under conditions and policies that vary by issuer.

### 5.2. What Does HTTP 200 from Revocation Mean?

This is easily misunderstood: RFC 7009 specifies that **the success response is still HTTP 200 even if the submitted token was already invalid or not found**. This prevents probing whether a token exists.

Therefore:

- HTTP 200 means **the revocation request was processed by the server per the protocol**, not proof that the token ever existed.
- Never log raw tokens or print tokens into frontend responses.
- After HTTP 200, the client must **stop using that token**, delete local stored copies safely, and update local state.
- Do not infer that every access token issued from the same grant stops working immediately; that depends on Authorization Server capabilities and policy.

### 5.3. Refresh Tokens and Access Tokens Behave Differently When Revoked

**Refresh token:** once revoked, the client generally cannot exchange it for new access tokens; the server may also revoke the entire token family/authorization grant.

**Opaque access token:** an API can query an introspection endpoint (RFC 7662) or shared server store; once revoked, the system can return `active=false` on the next check, subject to caching and sync delay.

**Self-contained JWT access token:** many Resource Servers verify JWTs offline via signature, issuer, audience, and `exp`. Without introspection/denylist/security epoch or server-side state checks, **a properly signed JWT can still be accepted until expiration**, even after the refresh token is revoked.

Table:

| Credential | What usually changes on revocation? | Things to watch |
| --- | --- | --- |
| **Refresh token** | Can no longer obtain new access tokens | Token family, rotation, session grant, issuer policy |
| **Opaque access token** | Can be reported inactive by introspection/store | Introspection cache and propagation latency |
| **JWT access token** | Not necessarily rejected immediately by offline-checking APIs | Short TTL, denylist, token version, or introspection per requirements |
| **ID token** | Not an OAuth access token; not a standard revocation target for "logout" | IdP session and RP session handled separately |
| **Local HttpSession cookie** | Not automatically destroyed when revoking OAuth tokens | Requires corresponding local logout/SessionRegistry |

**Design tip:** if a requirement demands "cut off access within seconds", a 60-minute JWT checked offline will not satisfy it solely by revoking the refresh token. Choose token lifetimes, cache TTLs, back-channel revocation/denylists, and acceptable latency upfront in the architecture.

### 5.4. Where Are Tokens Stored and Who May Revoke Them?

A BFF/server-side OAuth client app typically stores the Authorized Client on the server, tied to the user session. An SPA may use a BFF pattern or dedicated flow within public-client limits. Storage choice depends on the OAuth threat model; never put a client secret in browser JavaScript.

With Spring Security OAuth2 Client:

- **OAuth2AuthorizedClientService** or **OAuth2AuthorizedClientRepository** holds the client's access/refresh token details.
- Calling `removeAuthorizedClient(registrationId, principalName)` **deletes local Authorized Client data**; it is not an OAuth RFC 7009 request to the provider.
- To revoke at the AS, make a **separate HTTP request** to the proper endpoint with appropriate client authentication, or use a provider-supplied SDK/API.
- After revoking, clean up local storage to prevent token reuse, without inverting the order or swallowing errors in a way that falsely reports "revoked".

## 6. Java 17 Example: Sending an RFC 7009 Request to an Authorization Server

This is a **standalone Java SE program**, using no Spring libraries. It succeeds only when you already have an Authorization Server supporting RFC 7009, the right endpoint, client credentials, and token. This example **does not issue tokens or mock an issuer**.

Create **RevokeOAuthToken.java**:

~~~java
import java.net.URI;
import java.net.URLEncoder;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.nio.charset.StandardCharsets;
import java.util.Base64;

public final class RevokeOAuthToken {

    private RevokeOAuthToken() {
    }

    private static String required(String key) {
        String value = System.getenv(key);
        if (value == null || value.isBlank()) {
            throw new IllegalArgumentException(
                "Missing environment variable: " + key
            );
        }
        return value;
    }

    private static String encode(String value) {
        return URLEncoder.encode(
            value, StandardCharsets.UTF_8
        );
    }

    public static void main(String[] args) throws Exception {
        URI endpoint = URI.create(required("REVOCATION_ENDPOINT"));
        if (!"https".equalsIgnoreCase(endpoint.getScheme())) {
            throw new IllegalArgumentException(
                "Revocation endpoint must use HTTPS"
            );
        }

        String clientId = required("OAUTH_CLIENT_ID");
        String clientSecret = required("OAUTH_CLIENT_SECRET");
        String token = required("TOKEN_TO_REVOKE");

        // OAuth client password credentials via HTTP Basic.
        String basicPair = encode(clientId) + ":" + encode(clientSecret);
        String basic = Base64.getEncoder().encodeToString(
            basicPair.getBytes(StandardCharsets.UTF_8)
        );

        String body = "token=" + encode(token)
            + "&token_type_hint=refresh_token";

        HttpRequest request = HttpRequest.newBuilder(endpoint)
            .header("Content-Type",
                "application/x-www-form-urlencoded")
            .header("Authorization", "Basic " + basic)
            .POST(HttpRequest.BodyPublishers.ofString(body))
            .build();

        HttpClient client = HttpClient.newHttpClient();
        HttpResponse<Void> response = client.send(
            request, HttpResponse.BodyHandlers.discarding()
        );

        if (response.statusCode() == 200) {
            System.out.println("Revocation request accepted");
        } else {
            System.out.println(
                "Revocation request failed; HTTP "
                    + response.statusCode()
            );
        }
    }
}
~~~

Compile/run with JDK 17+:

~~~bash
javac RevokeOAuthToken.java
java RevokeOAuthToken
~~~

Set the environment variables **REVOCATION_ENDPOINT**, **OAUTH_CLIENT_ID**, **OAUTH_CLIENT_SECRET**, and **TOKEN_TO_REVOKE** before running. Never paste real token/client secret values into documentation, source code, shell history, or CI logs.

If the provider supports `client_secret_basic` and processes it successfully, expected stdout is:

~~~text
Revocation request accepted
~~~

If the issuer returns an error status, the program prints only the HTTP code, never secrets. **The program does not claim the API has immediately stopped accepting the token**; that requires a separate check.

**Sample limitations:**

- Uses `token_type_hint=refresh_token`; when revoking an access token, adjust the hint accordingly.
- RFC 6749 allows client authentication other than Basic; use the exact mechanism required by the issuer. Never use Basic with a public client lacking a secret.
- Do not enable infinite retries. On timeout, you do not know whether the server processed the request; clients need safe/idempotent retry design and status observation.
- Never use unencrypted HTTP endpoints in production. Never pass tokens in URLs/query strings.
- HTTP 200 does not prove an access JWT is rejected; send a request to the Resource Server and observe expiration/revocation behavior per policy.

## 7. External Identity Provider Logout: OpenID Connect

### 7.1. Who Are RP and OP?

- **RP (Relying Party):** the application using federated login, e.g., website A.
- **OP (OpenID Provider):** the system authenticating users and holding the SSO session (e.g., an enterprise identity server).
- **Session at RP:** browser session with website A; not identical to the session at the OP.
- **Session at OP:** session allowing the user to log into multiple RPs without re-entering credentials.

**Successful OIDC login does not imply OIDC logout is configured.** `oauth2Login()` lets the app log in via a provider, whereas coordinating logout requires a separate mechanism.

### 7.2. Local-Only Logout When Using OIDC

~~~text
Browser -> POST /logout at RP A
            |
            +--> A destroys HttpSession A
            +--> A deletes A's cookies
            |
            v
       IdP SSO cookie still remains
            |
            v
Browser -> /oauth2/authorization/<registrationId>
            |
            +--> redirects to OP
            +--> OP sees SSO session is still valid
            +--> user can log back into A without a password
~~~

This is the valid outcome of local logout. If the product requires "signing out of the SSO account too", an action at the OP is required, not only at A.

### 7.3. OIDC RP-Initiated Logout (Client-Initiated)

The **OpenID Connect RP-Initiated Logout 1.0** standard allows the RP to redirect the user agent to the **end_session_endpoint** published by the OP, typically obtained from Discovery metadata.

Flow:

~~~text
User clicks "Log out"
       |
       v
RP A runs local logout
       |
       +--> LogoutSuccessHandler creates redirect to OP
       |       - OP's end_session_endpoint
       |       - optional id_token_hint
       |       - optional post_logout_redirect_uri
       |
       v
Browser reaches OP logout endpoint
       |
       v
OP applies SSO session termination policy
       |
       +--> May ask for user confirmation
       +--> May notify other RPs of logout
       |
       v
Browser may be redirected back to RP A per registered URI
~~~

**Parameters to understand:**

- **end_session_endpoint:** the OP URL dedicated to logout; never infer it from the token endpoint.
- **id_token_hint:** the ID token issued by the OP, helping the OP identify the user/session for the logout request. Do not substitute an access token.
- **post_logout_redirect_uri:** the return address to the RP; must match the allowlist/registered URIs at the OP. Never read an arbitrary URI from a user query parameter and redirect to it, to prevent open redirects.
- **state:** per spec/implementation, helps the RP correlate the response with the logout request; configure and validate appropriately.

**Do not promise the OP always logs out every RP.** RP-Initiated Logout asks the OP to terminate its session per policy and may trigger federated notifications, yet impact on A/B depends on whether OP/RPs support front-channel/back-channel SLO and can receive notifications.

### 7.4. Spring Security: OidcClientInitiatedLogoutSuccessHandler

When a Spring Boot app has configured a valid **OAuth2/OIDC client registration**, you can use this handler:

~~~java
// Configuration snippet integrated into an app with OIDC ClientRegistration.
@Bean
LogoutSuccessHandler oidcLogoutSuccessHandler(
        ClientRegistrationRepository registrations) {

    OidcClientInitiatedLogoutSuccessHandler handler =
        new OidcClientInitiatedLogoutSuccessHandler(registrations);

    handler.setPostLogoutRedirectUri("{baseUrl}/signed-out");
    return handler;
}

@Bean
SecurityFilterChain oidcSecurityFilterChain(
        HttpSecurity http,
        LogoutSuccessHandler oidcLogoutSuccessHandler)
        throws Exception {

    http
        .authorizeHttpRequests(auth -> auth
            .requestMatchers("/signed-out").permitAll()
            .anyRequest().authenticated()
        )
        .oauth2Login(Customizer.withDefaults())
        .logout(logout -> logout
            .logoutSuccessHandler(oidcLogoutSuccessHandler)
        );

    return http.build();
}
~~~

This is an **excerpt configuration**: it requires a `@Configuration` or `@SpringBootApplication` class, imports for `@Bean`, `LogoutSuccessHandler`, `OidcClientInitiatedLogoutSuccessHandler`, `ClientRegistrationRepository`, `SecurityFilterChain`, `Customizer`, `HttpSecurity`, the `spring-boot-starter-oauth2-client` dependency, a client registration with valid issuer URI/credentials, and a public `GET /signed-out` endpoint.

When supported, the handler uses existing OIDC information and provider discovery to build the redirect to the logout endpoint. **If the provider does not publish `end_session_endpoint` or the session is not OIDC, the handler cannot guarantee full IdP logout**. Test against a real provider, not just verifying that the Spring context starts.

To avoid duplicate Bean configurations, **do not copy a second SecurityFilterChain verbatim** into an app with another chain without understanding `securityMatcher`/chain ordering. The local demo in section 4 and the OIDC snippet are **two different configuration contexts**.

### 7.5. OIDC Back-Channel Logout: OP Proactively Notifies the RP

The user does not always click logout inside app A. They may log out at the OP or have their account revoked; the OP can notify RPs via **OIDC Back-Channel Logout**.

Flow:

~~~text
OP: user logs out / account session ended
          |
          v
OP signs Logout Token (JWT with claims per spec)
          |
          v
Server-to-server POST to RP logout endpoint
          |
          v
RP verifies signature, iss, aud, iat, jti, events, sid/sub
          |
          v
RP looks up local session matching sid or subject and issuer
          |
          v
RP destroys the corresponding sessions
~~~

**A Logout Token is not a regular access token or ID token.** Per spec, it carries an `events` claim identifying the back-channel logout event; you must verify issuer, audience, signature, timestamps, session/subject, replay protection, and ensure **no `nonce` is present**.

- If the token contains **`sid`**, the RP can locate the session associated with that specific OP session.
- If `sid` is absent but **`sub`** is present, the RP typically must consider terminating sessions for that subject within the issuer/audience scope.
- The token must be thoroughly validated; never accept a self-declared JSON `sub` as a session-destruction command.

Spring Security Servlet supports `oidcLogout().backChannel(...)` and a default endpoint pattern `/logout/connect/back-channel/{registrationId}` when configured. Wire provider metadata/callback URLs, session mapping, and handlers accurately for your framework version.

**Important note in multi-node apps:** OIDC session mappings held locally on node A may not exist on node B. With Spring Session and multiple pods, consider a shared **`OidcSessionRegistry`**, event lifecycles, and session cookies. Spring Security docs note the back-channel handler defaults to cookie name `JSESSIONID`, while Spring Session typically uses `SESSION`; when combining them, configure `setSessionCookieName("SESSION")` and test the entire path for your running version.

### 7.6. How Does Front-Channel Logout Differ from Back-Channel?

| Technique | Delivery channel | Advantages | Limitations |
| --- | --- | --- | --- |
| **RP-Initiated Logout** | Browser redirect from RP to OP | Natural when user clicks logout in RP | OP and RPs must support it for federated effect |
| **Front-Channel Logout** | Logout notice via browser, iframe/redirect | Can synchronize multiple RPs through the user agent | Impacted by third-party cookies, tracker blocking, CSP, closed browser |
| **Back-Channel Logout** | OP calls RP server directly | Does not depend on open iframes/browsers | Requires secure endpoint, Logout Token validation, session mapping, retry/event handling |

**Core truth:** "Logging out of the IdP" and "all apps ending their sessions" are two separate requirements. When the IdP session is destroyed yet RP B never receives/processes the notification, RP B can keep granting access based on its unexpired local session.

## 8. SAML 2.0 Single Logout (SLO)

For **SAML 2.0**, the equivalent concept coordinating logout between Service Provider (SP/RP) and Identity Provider (IdP) is typically **Single Logout**:

- **SP-initiated SLO:** the app sends a properly signed `saml2:LogoutRequest` to the IdP and receives a `LogoutResponse`.
- **IdP-initiated SLO:** the IdP sends a `LogoutRequest` to the app; the app verifies the message and terminates the local session.
- Metadata, signing certificates, bindings, endpoints, and name/session identifiers must be configured compatibly with the IdP.

Spring Security Servlet supports `saml2Logout()` when `saml2Login()`, `RelyingPartyRegistration`, metadata, signing credentials, and matching SLO endpoints are configured.

~~~java
// Illustration: only effective when SAML is fully configured.
http
    .saml2Login(Customizer.withDefaults())
    .saml2Logout(Customizer.withDefaults());
~~~

This is **not** OIDC logout: SAML and OIDC use different protocols, messages, session identifiers, and validation. Do not write a manual redirect to an IdP URL and treat it as valid SAML SLO; messages must conform to SAML, including signatures when required by the IdP.

Spring Security also allows **separate local logout** and **separate SAML RP-initiated logout**, such as using `POST /logout` strictly to clear the local session and another endpoint to initiate SLO. UI design should explain both options clearly if a product offers both.

## 9. Three Types of "Logout" Commonly Requested by Users

### 9.1. "Log Out of This Application"

**Goal:** the user cannot reuse the current browser session in application A.

Typical steps:

1. POST `/logout` with valid CSRF if the browser uses cookies.
2. LogoutFilter destroys local HttpSession/context and cleans up remember-me if present.
3. Delete session cookies/corresponding client storage.
4. Navigate to a public page; verify calling protected endpoints with the old cookie fails.

**Do not claim:** API access tokens were revoked; IdP SSO session ended; other devices were logged out.

### 9.2. "Log Out All Devices for This Account"

**Goal:** invalidate **all existing system-managed access methods** for the user, not only the current session.

Usually requires:

- Listing/destroying all HttpSessions by principal if stateful, using a shared session store/index.
- Deleting the user's persistent remember-me tokens.
- Revoking refresh tokens/token families and revocable access tokens from the managed issuer.
- If using offline JWTs, designing a security version/denylist or accepting latency until `exp` per SLA.
- If API keys/personal access tokens exist, deciding whether to revoke them as well.
- If requirements span external SSO, coordinating with the IdP and RPs; you cannot unilaterally destroy sessions on another domain/issuer without supported protocols/permissions.
- Recording audits and notifying the user, without letting logs contain tokens/cookies.

**There is no single default Spring Security call** that guarantees all the above tasks.

### 9.3. "Log Out of the SSO Account / Identity System"

**Goal:** close the session at the IdP, prevent the browser from automatically re-identifying via the old SSO session, and coordinate RP logout where supported.

Common approaches:

- OIDC RP-Initiated Logout redirecting the user agent to `end_session_endpoint`.
- OIDC Back-Channel Logout handling requests sent by the OP to the RP.
- SAML Single Logout per SP/IdP configuration.
- Providers not supporting standards may offer proprietary logout APIs. Read provider docs rather than guessing endpoints or scopes.

**Limitation:** even once the IdP session has ended, an already-issued valid access JWT can still access APIs until expiration if the API lacks a revocation mechanism. Another RP not participating in SLO may also retain its local session.

## 10. Orchestration Rules and Step Ordering

For a UI offering "Log out of application" and "Log out everywhere", model **per-system requests + results**, rather than calling one endpoint and always returning success.

General workflow example:

~~~text
User selects logout type
        |
        +--> Local-only
        |      |
        |      +--> local LogoutFilter / cookie cleanup
        |      +--> return local result
        |
        +--> Global / security-sensitive logout
               |
               +--> verify user and authorization to execute
               +--> revoke refresh/access tokens in scope
               +--> invalidate relevant local sessions/remember-me
               +--> request OP/IdP logout per supported protocol
               +--> track status/timeout/retry of external step
               +--> only claim scopes that ACTUALLY completed
~~~

### 10.1. No Atomic Transaction Across Systems

A database transaction in application A **cannot** atomically wrap the IdP deleting SSO cookies, the Authorization Server revoking refresh tokens, and Resource Servers rejecting all offline JWTs.

Therefore:

- Define **minimum mandatory actions**, prioritized by security safety and UX messaging.
- Handle per-step errors: a token revocation timeout may leave a window where tokens remain valid.
- Use bounded retries, idempotency, and auditing to avoid "false success".
- When a user loses a device or compromise is suspected, prioritize blocking reusable credentials on the server/issuer; merely deleting cookies on the active device is insufficient.
- Do not store plaintext tokens in retry queues/logs; if needed, use encrypted storage, TTLs, and secure processes.
- Do not call external logout URLs from JavaScript using an unvalidated user-supplied URL, to prevent open redirects/SSRF.

### 10.2. Deleting Local Tokens Does Not Equal Revoking at the Issuer

With `OAuth2AuthorizedClientService`:

~~~java
// Illustrative example, after performing revocation policy at the issuer:
authorizedClientService.removeAuthorizedClient(
    registrationId, principalName
);
~~~

This deletes app-side Authorized Client details and **does not call RFC 7009**. To revoke, send a request to the revocation endpoint with proper client authentication. In systems with multiple client grants, specify clearly which tokens must be revoked and whether the whole token family is required.

### 10.3. Do Not Equate OIDC Login with OAuth Access Tokens

A website using `oauth2Login()` can have:

- Local HttpSession (where Spring Security stored Authentication).
- ID token representing identity.
- Access token for calling UserInfo/resource APIs.
- Refresh token (if issued and stored by the client).
- SSO cookie at the OpenID Provider.

A logout button may affect **one, two, or several** of these components. Document the product's policy clearly and test each component, instead of assuming `logout()` always revokes every token issued by the IdP.

## 11. Three-Layer Test Matrix

| Scenario | Check local session | Check token | Check IdP/SSO |
| --- | --- | --- | --- |
| Local logout only at A | Old cookie cannot restore A | Not revoked by default | OP session may remain |
| Local logout then log back in via OIDC | A no longer has old session | Do not conclude from redirect alone | If OP SSO remains, may log back in without password |
| Revoke refresh token | Local session may remain | Cannot obtain new access tokens with that refresh token | OP session may remain |
| Revoke opaque access token | Local session may remain | Introspection turns inactive after propagation | Not affected by default |
| Revoke refresh token while access JWT is alive | Local session independent | JWT may stay valid until exp with offline validation | OP session independent |
| RP-Initiated OIDC logout | A can clean up locally per design | Does not automatically revoke all OAuth tokens | OP performs logout per policy |
| OP sends back-channel logout | RP destroys session matching sid/sub after validation | Does not automatically revoke access tokens | OP session ended/ending |
| SAML SLO succeeds | SP handles session per message | Does not replace OAuth revocation | IdP/SP coordinate per SLO |
| Security-mandated logout all devices | All local sessions destroyed for the user | Tokens revoked within scope | Only if IdP supports and coordinated |
| Lost connection to IdP during logout | A may have logged out locally | Token state may be uncertain | Do not claim OP logged out |

### 11.1. Testing Local Logout with MockMvc

With Spring Security Test, verify:

- Without a CSRF token, `POST /logout` is rejected per browser/cookie config.
- Successful login creates a session; valid `POST /logout` clears Authentication.
- Subsequent request carrying only the old session cookie gets redirected/401 per entry point.
- Remember-me is cleaned up according to the configured service type.

Intentional test snippet, requiring configured test context:

~~~java
// Illustrative code in a test with MockMvc and csrf().
mockMvc.perform(post("/logout").with(csrf()))
       .andExpect(status().isNoContent());
~~~

If there is no Authentication yet, the handler can still return a status; therefore **checking only 204 does not prove a real session was destroyed**. Tests must create an authenticated session beforehand and verify a subsequent request.

### 11.2. Testing Token Revocation

Use a test Authorization Server supporting RFC 7009:

1. Issue access/refresh tokens to the client.
2. Call a protected API successfully with the access token.
3. Revoke the refresh token.
4. Use the old refresh token to request a new access token: **fails**.
5. Check the old access token at the Resource Server under real policy: it may stay valid until `exp` if verified offline as a JWT.
6. If near-real-time revocation is required, measure delay from revocation to rejection instead of claiming "instantaneous".
7. Repeat revoking an already invalid token: a 200 response can still conform to the protocol.

### 11.3. Testing Federated OIDC Logout

With two Relying Parties A/B and a test OP:

1. Log into A and B using the same OP; establish sessions in both.
2. Perform **local-only logout in A**, confirm B still works and OP SSO may remain.
3. Initiate RP-Initiated Logout from A, verify the browser redirects to the right **`end_session_endpoint`**; `post_logout_redirect_uri` matches a registered URI.
4. Verify the OP session ended per policy; a new OIDC login prompts for authentication or produces the expected result.
5. If the OP supports back-channel, verify B receives and validates the **Logout Token**, then destroys sessions matching sid/sub.
6. Send a Logout Token with bad signature, wrong issuer/audience, or expired/replayed: **must not destroy sessions**.
7. Test in a multi-pod environment: verify session mapping, cookie names, registry, and shared stores stay consistent.

**An HTTP 302 to the IdP does not prove the IdP logged out successfully.** Inspect the full flow and SSO state.

### 11.4. Testing SAML Single Logout

Use a test SAML IdP/RP with matching metadata, signing credentials, and SLO endpoints:

- SP sends a valid `LogoutRequest`, IdP returns a valid `LogoutResponse`, and local session terminates.
- IdP-initiated SLO is genuinely verified and processed by the SP.
- Messages with bad signatures/issuers/destinations are rejected.
- Do not claim every RP logged out if an RP does not support or never received SLO.

## 12. Common Mistakes and How to Fix Them

### 12.1. "JSESSIONID was deleted, so the JWT is definitely invalid"

**False.** A JWT access token is a separate credential. APIs checking signatures/`exp` offline can still accept the JWT until expiration. Revocation/denylist/introspection or short token TTL design is needed.

### 12.2. "RFC 7009 succeeded, so all OIDC sessions are logged out"

**False.** Revocation handles tokens/grants per server policy; the IdP browser SSO session is separate state. An appropriate OIDC logout mechanism is required to close the session at the OP.

### 12.3. "Logging out of the IdP immediately logs out all other apps"

**Not guaranteed.** RPs must receive and process SLO notifications, or enforce re-authentication per policy; browser front-channel can be blocked, back-channel can fail, and an RP may keep its own local session.

### 12.4. "Clearing OAuth2AuthorizedClientService revokes tokens at the provider"

**False.** That operation cleans the client's local token store. A dedicated revocation request or provider API is required.

### 12.5. "GET /logout can be used for convenience"

**Not recommended for cookie-based browser apps.** Use POST and CSRF to prevent logouts triggered by external pages/prefetching. GET may serve as the default logout confirmation page when CSRF is enabled.

### 12.6. "Must write a custom /logout controller and call clearContext"

**Unnecessary for standard flows.** Use LogoutFilter and LogoutHandler/LogoutSuccessHandler provided by Spring Security. `clearContext()` alone does not destroy HttpSession/remember-me/repository.

### 12.7. "Logout success redirect allows arbitrary user-supplied URLs"

**Open redirect risk.** When configuring `post_logout_redirect_uri`, use registered/allowlisted URIs. Never take an unvalidated `next` parameter to redirect to arbitrary domains.

### 12.8. "A Logout Token from OP only needs a valid sub"

**False.** Back-channel Logout Tokens must have signature, issuer, audience, claims, logout event, timestamps, replay protection, and sid/sub verified per spec. Never accept a self-declared username JSON request to destroy sessions.

### 12.9. "JWT access tokens can be revoked immediately at every Resource Server with no extra mechanism"

**Incorrect when validators are purely offline.** You need a denylist, security epoch, token version, introspection/cache, or short lifetimes to meet near-real-time requirements.

### 12.10. "With multiple pods, a local SSO session registry is enough"

**Not guaranteed.** The OP logout notification may land on a different pod; share session/sid/sub mappings and repositories as required by the logout mechanism. With Spring Session's `SESSION` cookie, verify compatibility with the OIDC back-channel handler expecting `JSESSIONID` by default.

### 12.11. "HTTP 200 from revocation proves the token previously existed"

**False.** RFC 7009 intentionally returns 200 even for invalid/missing tokens to prevent token fishing.

### 12.12. "Logging out all devices only requires deleting the current device's cookie"

**False.** You cannot delete cookies in another browser via a response to the current browser. You must revoke sessions/tokens **server-side** or rely on supported protocols at each issuer/RP.

## 13. Real-System Logout Design Checklist

Before finalizing product requirements, answer these questions:

- Does the user want **local**, **token revocation**, **SSO**, or **all devices**? Does the UI explain the scope?
- Does the system use **HttpSession**, remember-me, OAuth access/refresh tokens, ID tokens, SAML sessions, API keys, or a combination?
- Who owns the state to revoke: the app, resource server, authorization server, IdP, or a third party?
- For refresh tokens, is calling **RFC 7009** permitted? What is the token family/rotation policy?
- For JWT access tokens, what are the maximum lifetime and acceptable revocation latency?
- Is invalidating **all HttpSessions** of the same user across other nodes required? Is there a shared session registry/index?
- Does the OIDC OP support **`end_session_endpoint`**, back-channel/front-channel? Are redirect URIs registered?
- If using Spring Session, what is the cookie name and is OIDC logout session mapping compatible/shared across the cluster?
- Does the SAML IdP support SLO, and do metadata, signing, and endpoints match?
- When the IdP/revocation endpoint fails or times out, what does the UI show? Are there retries/audits and an **incomplete** state?
- Are cookies, tokens, client secrets, and Logout Tokens protected in transit/storage/logs?
- Do tests prove the **expected outcome in each system**, rather than asserting only HTTP 204/302?

**Summary principle:** never say "logged out everywhere" just because the app cleared SecurityContext. A proper logout flow defines **revocation scope**, **state ownership**, and **completion evidence** across every participating system.

## 14. Self-Check Questions

**Question 1.** A user logs out of app A with `POST /logout`, then clicks login and is immediately let in by the IdP. What happened?

**Answer:** A performed local logout, yet the SSO session at the IdP may still be alive. OIDC RP-Initiated Logout or an appropriate IdP mechanism is needed to close the SSO session.

**Question 2.** The backend successfully revokes a refresh token; an unexpired JWT access token can still call the API. Is this definitely a revocation bug?

**Answer:** No. A Resource Server verifying JWTs offline can keep accepting it until `exp` unless an additional denylist/revocation check exists.

**Question 3.** Does `OAuth2AuthorizedClientService.removeAuthorizedClient(...)` send an RFC 7009 request?

**Answer:** No. It deletes the authorized-client record inside the app. A separate call to the revocation endpoint is needed if the issuer must revoke the token.

**Question 4.** Does HTTP 200 from the revoke endpoint prove the token was active beforehand?

**Answer:** No. RFC 7009 returns 200 even when the token is invalid or non-existent.

**Question 5.** When RP A logs out locally, does RP B automatically log out?

**Answer:** Not by default. B holds its own session; only with SLO or an appropriate policy/notification can B's session be destroyed.

**Question 6.** In OIDC, is an ID token an access token to revoke or a substitute for a `Logout Token`?

**Answer:** No. An ID token attests login, an access token grants API access, and a Logout Token has its own claims contract for back-channel logout.

**Question 7.** Why must the backend verify `iss`, `aud`, signature, and `sid/sub` of a Logout Token?

**Answer:** Because it is a security-sensitive session-destruction request; trusting a self-declared payload would let attackers forge logout commands or destroy the wrong sessions.

**Question 8.** An app uses Spring Session's `SESSION` cookie with an OIDC back-channel handler assuming `JSESSIONID`. What should be done?

**Answer:** Configure the handler/session mapping to match the cookie name and test thoroughly on your running Spring Security version, especially across multiple pods.

**Question 9.** To "log out all devices", is revoking refresh tokens alone sufficient?

**Answer:** Not necessarily. You need invalidation of local HttpSessions, remember-me tokens, access tokens per the real architecture, and possibly the SSO session at the IdP if scope covers it.

**Question 10.** When token revocation or IdP logout times out while the local session was already destroyed, what should be reported?

**Answer:** You can confirm the **local logout** scope completed while stating that the token/SSO revocation step could not be confirmed; never report logged out everywhere without proof.

## Official Documentation

- [Spring Security 6.5 — Handling Logouts (Servlet)](https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/logout.html)
- [Spring Security — OIDC Logout for Servlet](https://docs.spring.io/spring-security/reference/servlet/oauth2/login/logout.html)
- [Spring Security 6.5 — OidcClientInitiatedLogoutSuccessHandler API](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/oauth2/client/oidc/web/logout/OidcClientInitiatedLogoutSuccessHandler.html)
- [Spring Security 6.5 — SAML 2.0 Single Logout](https://docs.spring.io/spring-security/reference/6.5/servlet/saml2/logout.html)
- [RFC 7009 — OAuth 2.0 Token Revocation](https://www.rfc-editor.org/rfc/rfc7009)
- [RFC 7662 — OAuth 2.0 Token Introspection](https://www.rfc-editor.org/rfc/rfc7662)
- [OpenID Connect RP-Initiated Logout 1.0](https://openid.net/specs/openid-connect-rpinitiated-1_0-final.html)
- [OpenID Connect Back-Channel Logout 1.0](https://openid.net/specs/openid-connect-backchannel-1_0-final.html)
