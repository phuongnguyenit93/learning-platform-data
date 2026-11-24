# Distinguishing Local Logout, Identity Provider Logout, and Token Revocation

> **Scope:** Spring Security 6 on the **Servlet stack**, Spring Boot 3.x, Java 17+. Three activities are often lumped together under “logout” yet mean different things: **local logout** terminates the authentication session at the application; **IdP logout** targets the Single Sign-On (SSO) session at the identity provider / OpenID Provider; **token revocation** revokes OAuth2 credentials under the Authorization Server's (AS) policy. This lesson clearly distinguishes their scope, mechanisms, APIs, impact on sessions/cookies/tokens, runnable Java examples, and testing.

## 1. Three Logout Scopes: Why Clicking One Button Isn't Enough

A user may simultaneously hold the following states:

- An `HttpSession` at **Application A** storing `SecurityContext` / `Authentication`. The browser carries a session cookie like `JSESSIONID`.
- An **IdP/OpenID Provider SSO cookie** on a separate origin; when Application A or B redirects to the IdP login page, that cookie can enable SSO without prompting for a password again.
- An **OAuth2 access token** for calling APIs/resource servers; a **refresh token** to obtain new access tokens; an **ID token** informing the RP about the OIDC authentication event.
- A **remember-me cookie** on Application A that can restore authentication after the regular session expires.
- A **different `HttpSession` on Application B**, which also uses that IdP while keeping its own local session.

Deleting the session at A **does not automatically delete** the SSO cookie at the IdP, does not destroy session B, and does not strip the signature or expire an already-issued JWT access token.

```text
Browser / Client
    |
    +--> App A: JSESSIONID -> HttpSession -> SecurityContext
    |        |
    |        +-- Local logout: invalidate session, clear context
    |
    +--> IdP: SSO cookie -> login session at OP
    |        |
    |        +-- IdP logout: end SSO per OP protocol/support
    |
    +--> API: Authorization: Bearer <access-token>
             |
             +-- Token revocation: AS updates token/grant state
                 (effect at RS depends on token type/validation method)
```

**Rule:** define the exact goal before coding. “Log out of this app,” “log out of the SSO account,” “log out of all devices,” and “revoke refresh tokens” are distinct business requirements.

| Mechanism | Primary state altered | Who handles it? | What is not automatically guaranteed |
| --- | --- | --- | --- |
| **Local logout** | `SecurityContext`, `HttpSession`, app cookies, and local logout handlers | Spring Security in the application | Does not terminate IdP SSO or revoke OAuth2 tokens |
| **IdP/OP logout** | SSO session at the identity provider | IdP/OpenID Provider, optionally initiated by the RP | Does not guarantee every RP destroyed its local session; does not guarantee issued JWTs immediately stop working |
| **Token revocation** | Token/grant state at the Authorization Server | AS, upon an authorized client's request | Does not delete `JSESSIONID`, SSO cookies, or RPs' local sessions |

## 2. Local Logout: What Does Spring Security Do to the App Session?

In Servlet apps using form login, Spring Security provides `LogoutFilter` and `LogoutHandler`s. Upon receiving a matching logout request, it can:

1. Clear the current `Authentication`/`SecurityContext`;
2. Invalidate `HttpSession` per policy;
3. Clean up remember-me cookies and persistent remember-me tokens when configured;
4. Request deletion of application cookies and run additional registered handlers;
5. Return a redirect or response via `LogoutSuccessHandler`.

```text
POST /logout + session cookie + valid CSRF
    |
    v
LogoutFilter
    |
    +--> SecurityContextLogoutHandler
    |       clearAuthentication / clear SecurityContext
    |       invalidate HttpSession if enabled
    |
    +--> RememberMeServices logout (if integrated)
    +--> Cookie clearing / custom LogoutHandler (if configured)
    |
    v
LogoutSuccessHandler -> 302 /logged-out or matching response
```

### 2.1. Do Not Only Clear `SecurityContextHolder`

`SecurityContextHolder` holds the current request/thread's context. A controller manually calling:

```java
SecurityContextHolder.clearContext();
```

**does not guarantee the session was invalidated**. If the context remains stored in `HttpSessionSecurityContextRepository`, the next request can reload authentication. Therefore, prefer `http.logout(...)` and standard handlers.

Illustrative snippet when a custom handler must be invoked:

```java
SecurityContextLogoutHandler handler = new SecurityContextLogoutHandler();
handler.setInvalidateHttpSession(true);
handler.setClearAuthentication(true);
handler.logout(request, response, authentication);
```

This is a fragment inside code that already has `request`/`response`/`authentication`, not a standalone class. Do not invoke the handler redundantly if Spring Security's `LogoutFilter` already performs that work.

### 2.2. Cookie Deletion and Server-Side Invalidation Differ

Deleting `JSESSIONID` in the browser only removes the client's copy of the **session identifier**; if the old session remains alive on the server, anyone who captured the old ID can still use it. Local logout must ensure **the old session ID no longer grants access**.

Conversely, server-side session invalidation is the mechanism that blocks the old ID even if the browser sends that ID one more time. `deleteCookies("JSESSIONID")` assists browser cleanup, yet cookie path/domain and containers can affect proper deletion.

### 2.3. CSRF with Logout

When CSRF protection is enabled, standard form-based logout is **`POST /logout` with a CSRF token**. `GET /logout` may display a Spring Security-generated confirmation page, yet should not trigger automatic logout side effects. If logout is allowed via unprotected GET, another website could force the user's browser to log out (*logout CSRF*).

Never disable CSRF just to run `curl -X POST /logout` without a token. Instead, supply a valid token and test the actual behavior.

### 2.4. Remember-Me: Why Logging Out Auto-Logs Back In

If an app uses long-lived remember-me cookies, destroying only `HttpSession` may leave the remember-me cookie valid. On a fresh request lacking a context, `RememberMeAuthenticationFilter` can restore identity and the user appears logged in again.

When using `http.rememberMe(...)`, integrate the corresponding logout handlers to delete cookies/revoke persistent tokens per policy. With `PersistentTokenRepository.removeUserTokens(username)`, deleting by username by default can affect **multiple devices**, unlike “log out only this device.” Never assume scope without inspecting the actual repository/handler.

## 3. With OIDC Login: Two Independent Sessions

An app using `oauth2Login()` can sign in via an OpenID Provider (OP). The authorization code flow occurs at the IdP, and then the app creates a **local authentication/session**. Meanwhile, the OP maintains the browser's **SSO session**.

```text
Browser                App A (Relying Party)          Identity Provider
   |                           |                           |
   | GET /private              |                           |
   |-------------------------->|                           |
   |<---- redirect to IdP -----|                           |
   |---------------------- SSO login page ---------------->|
   |<----- authorization code / redirect -------------------|
   |------ callback ---------->|                           |
   |                           |-- exchange code/token ---->|
   |                           |<----- ID/access tokens ----|
   |<----- JSESSIONID ---------|                           |
   |                           |                     SSO cookie may remain
```

When App A only invalidates `JSESSIONID`, it **cannot directly delete cookies belonging to the IdP's domain**. Returning to A's login may immediately re-authenticate the user via the active SSO session at the IdP. This is not necessarily a bug in local logout.

**Three artifacts to distinguish:**

- **ID token:** OIDC asserts authentication details to the RP; not an access token for calling APIs.
- **Access token:** used at resource servers with granted scopes/audiences.
- **Refresh token:** used by the client at the AS to obtain new access tokens; not an HTTP session cookie.

Clearing the local app session also does not automatically erase these tokens if they remain in client-side or server-side storage.

## 4. Logging Out of the IdP/OpenID Provider: RP-Initiated Logout

OIDC supports the **RP-Initiated Logout** model when the provider implements the corresponding endpoint. The RP asks the OP to terminate the SSO session, typically via a browser redirect to `end_session_endpoint` from metadata.

```text
User chooses "Log out of SSO"
    |
    v
POST /logout at RP (valid CSRF)
    |
    +--> LogoutFilter/LogoutHandlers clean local session
    |
    v
OidcClientInitiatedLogoutSuccessHandler
    |
    +--> look up matching OIDC ClientRegistration / metadata
    +--> build redirect to OP end_session_endpoint
    |
    v
Browser -> OP processes SSO logout
    |
    +--> OP may prompt for confirmation / check id_token_hint
    |
    v
OP -> allowlisted post_logout_redirect_uri
```

Common OIDC parameters:

- `id_token_hint`: ID token supplied by the RP to hint the user/session/client to the OP.
- `post_logout_redirect_uri`: where the OP may send the user back; typically must be pre-registered/allowlisted.
- `state`: correlation value between request and redirect, when used by the flow/provider.

**Never guess** the logout endpoint by concatenating `issuer + "/logout"`: different IdPs have different endpoints/metadata/requirements. Also never accept arbitrary redirect URIs from query strings if they could introduce an **open redirect**.

### 4.1. Is RP-Initiated Logout Global Logout?

No. At least three related mechanisms exist:

| Mechanism | Flow | Purpose |
| --- | --- | --- |
| **RP-Initiated Logout** | RP requests OP logout | Terminates SSO session at OP per OP's capabilities |
| **Front-Channel Logout** | OP coordinates notifications through the browser to RPs | Participating RPs can clear local sessions per protocol |
| **Back-Channel Logout** | OP sends server-to-server logout notifications to RPs | RP validates the notification and revokes matching sessions |

There is no automatic rule that every application sharing an IdP receives logout notifications. If Application B still holds an `HttpSession` without supporting front/back-channel logout, B may keep accepting requests even after OP SSO ends.

**“Log out of all applications” is an end-to-end SLO integration requirement**, not the default behavior of a single `http.logout()` call.

## 5. How Does Spring Security Configure OIDC Logout?

In a Spring Boot Servlet project, include the dependencies:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-security'
    implementation 'org.springframework.boot:spring-boot-starter-oauth2-client'
}
```

This is a snippet inside `build.gradle`; project plugins and repositories are needed. Java configuration example:

```java
package demo;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.oauth2.client.oidc.web.logout.OidcClientInitiatedLogoutSuccessHandler;
import org.springframework.security.oauth2.client.registration.ClientRegistrationRepository;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class OidcLogoutConfig {

    @Bean
    OidcClientInitiatedLogoutSuccessHandler oidcLogoutSuccessHandler(
            ClientRegistrationRepository registrations) {

        OidcClientInitiatedLogoutSuccessHandler handler =
                new OidcClientInitiatedLogoutSuccessHandler(registrations);
        handler.setPostLogoutRedirectUri("{baseUrl}/");
        return handler;
    }

    @Bean
    SecurityFilterChain securityFilterChain(
            HttpSecurity http,
            OidcClientInitiatedLogoutSuccessHandler oidcLogout)
            throws Exception {

        http.authorizeHttpRequests(auth -> auth
                .requestMatchers("/").permitAll()
                .anyRequest().authenticated());

        http.oauth2Login(Customizer.withDefaults());

        http.logout(logout -> logout
                .logoutSuccessHandler(oidcLogout));

        return http.build();
    }
}
```

`OidcClientInitiatedLogoutSuccessHandler` looks up provider metadata via `ClientRegistrationRepository` and builds the redirect when the OP supports it. `{baseUrl}` is a Spring-resolved placeholder for building the application's post-logout URI, not a URL taken freely from user input.

Illustrative `application.yml` (**for illustration only**, not a live IdP):

```yaml
spring:
  security:
    oauth2:
      client:
        registration:
          corp:
            client-id: replace-with-client-id
            client-secret: from-secure-secret-manager
            scope: openid, profile
        provider:
          corp:
            issuer-uri: https://idp.example.com/realms/example
```

Running E2E requires registering a real client, login redirect URI, post-logout redirect URI at the IdP, appropriate client authentication, and a provider exposing `end_session_endpoint`. Do not treat this fragment as a **standalone project runnable without an IdP**.

### What Needs Testing?

1. Valid `POST /logout` removes authentication from the local session.
2. The handler sends the browser to the **exact OP** for the logged-in user.
3. `post_logout_redirect_uri` is allowlisted and rejects open redirects.
4. The OP terminates SSO per actual policy, or the UI states clearly if the OP lacks support.
5. Other RPs receive/process logout notifications if the product promises SLO.
6. Multi-tenant/multiple registrations never redirect to the wrong IdP.
7. If the IdP is unreachable, the RP still clears the local session and never claims “global logout succeeded” without proof.
8. Never expose ID tokens or token hints in application logs or analytics systems.

## 6. Token Revocation per OAuth2 RFC 7009

**Token revocation** means asking the **Authorization Server** to disallow further use of a token under the AS's policy. RFC 7009 defines the token revocation endpoint; support for revoking access and refresh tokens depends on the AS/provider.

### 6.1. Deleting Client Tokens DIFFERS from Revoking at the AS

- **Remove local token:** the app deletes access/refresh tokens from its local cache or repository. The AS may have no idea.
- **Revoke at AS:** an authorized client sends an HTTP request to the AS's revocation endpoint; the AS updates token/grant state per contract.
- **RS rejects token:** depends on whether the resource server checks revocation status (opaque introspection/denylist/online validation) or only verifies JWT signatures offline.

```text
Client storage: access_token T, refresh_token R
    |
    +--> delete local T/R copy: affects client storage only
    |
    +--> RFC7009 revoke(R) at AS:
    |       R can no longer mint new tokens per policy
    |       already-issued T may not yet be expired
    |
    +--> revoke(T) at AS:
            effective when RS checks or has matching revocation data
```

### 6.2. Token Revocation Request

HTTP example (**illustrative endpoint only**):

```http
POST /oauth2/revoke HTTP/1.1
Host: idp.example.com
Content-Type: application/x-www-form-urlencoded
Authorization: Basic <base64(client-id:client-secret)>

token=<refresh-token>&token_type_hint=refresh_token
```

`token` carries the token to revoke; `token_type_hint` (if supported) can be `refresh_token` or `access_token`. Client authentication depends on the AS, e.g., `client_secret_basic` or another method. Not every public client has a client secret.

Shell command (**template only, do not run placeholders verbatim**):

```bash
curl --request POST \
  'https://idp.example.com/oauth2/revoke' \
  --user "$CLIENT_ID:$CLIENT_SECRET" \
  --data-urlencode "token=$REFRESH_TOKEN" \
  --data-urlencode 'token_type_hint=refresh_token'
```

Never paste real secrets into docs or shell history; use proper secret management, HTTPS, and log redaction.

### 6.3. What Does HTTP 200 from Revocation Mean?

To avoid probing whether a token exists, a revocation endpoint may return success even when a token is already invalid or not found. Therefore, **HTTP 200 does not prove the token previously existed** and does not prove every resource server rejects the associated access token.

Testing must include **attempting a refresh** and **calling an API with the old access token** within the real architecture, not just asserting the revocation request's status code.

### 6.4. Why Might an Old Access JWT Keep Working?

A self-contained JWT carries a signature and `exp`. Resource servers may verify signature, `iss`, `aud`, `exp`, and authorities **offline** without querying the AS per request. An RFC 7009 call does not magically alter the bytes/signature of an already-issued access JWT.

Options to bound post-logout validity:

- **Short TTL** access tokens, with protected, rotated, and revocable refresh tokens.
- Reference/opaque tokens with **introspection** if the RS must know live active state; manage caching carefully.
- Denylists keyed by `jti` or token ID synchronized to resource servers, with TTLs lasting until JWT expiry.
- Depending on the AS, revoking related grants/sessions or handling back-channel logout.
- Signing-key rotation only for controlled emergencies—it has wide blast radius, not a per-user logout solution.

**Do not claim** revoking a refresh token makes every access token get rejected immediately. Behavior depends on the AS, token type, and RS validation mechanism.

### 6.5. An ID Token Is Not an Access Token

In OIDC, an **ID token** provides authentication information to the RP and can be used as `id_token_hint` during RP-initiated logout. It is **not** an access token for calling APIs and is not automatically a target of every token revocation endpoint. Never substitute an ID token for an access token in an HTTP `Authorization` header.

## 7. `OAuth2AuthorizedClientService` Only Manages Local Storage

In Spring Security OAuth2 Client, `OAuth2AuthorizedClient` can hold access and refresh tokens bound to a `ClientRegistration` and principal. Removing the local record might look like:

```java
// Fragment inside a service holding the corresponding variables and dependencies.
authorizedClientService.removeAuthorizedClient(
        clientRegistrationId, principalName);
```

`OAuth2AuthorizedClientService.removeAuthorizedClient(...)` **does not by default** call an RFC 7009 revocation endpoint. `OAuth2AuthorizedClientRepository.removeAuthorizedClient(...)` likewise belongs to request/principal-scoped local storage and does not prove the AS revoked the token.

A flow needing both local logout **and** remote revocation must explicitly:

1. Identify the authorized client genuinely belonging to the current principal—never trust arbitrary tokens/registrations from query strings.
2. Retrieve the refresh token from **server-side storage** before deleting it; never send the value to the frontend.
3. Call the right AS revocation endpoint with proper client authentication, timeouts, and error handling.
4. Remove the local authorized client and invalidate the session/cookies per policy.
5. If OIDC SSO logout applies, perform the browser redirect to the OP per contract.
6. Record partial success/timeouts and design retries/incident processes as needed.

This is an **architectural workflow**, not a single method on `http.logout()`. If remote revocation fails, still ensure the user does not keep a privileged local session just because of a network error; at the same time, the UI must not claim “all tokens revoked” when revocation did not complete.

### Does a Resource Server Automatically Revoke JWTs?

An app configuring only `http.oauth2ResourceServer(oauth2 -> oauth2.jwt(...))` is a **resource server**. It does not become an Authorization Server and cannot strip the signature or expire an externally issued access JWT. Coordinate with the AS or apply denylists/introspection per your security architecture.

Calling `SecurityContextHolder.clearContext()` on a stateless request does not prevent the client from resending a valid JWT on the next request.

## 8. Runnable Spring Boot Project: Verifying Local Logout

This Java 17 / Spring Boot **3.3.5** / Spring Security 6 / Gradle 8.5 example demonstrates **one exact scope**: application form login/session and local logout. There is no external IdP or OAuth2 Authorization Server, so the tests will **not** pretend to prove SSO logout or token revocation.

### 8.1. Project Structure

```text
local-logout-demo/
  settings.gradle
  build.gradle
  src/main/java/demo/
    DemoApplication.java
    SecurityConfig.java
    DemoController.java
  src/test/java/demo/
    LocalLogoutTest.java
```

File `settings.gradle`:

```groovy
rootProject.name = 'local-logout-demo'
```

File `build.gradle`:

```groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.5'
    id 'io.spring.dependency-management' version '1.1.6'
}

group = 'demo'
version = '1.0.0'

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-security'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
```

### 8.2. Main Application

`src/main/java/demo/DemoApplication.java`:

```java
package demo;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class DemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(DemoApplication.class, args);
    }
}
```

### 8.3. `SecurityConfig`

`src/main/java/demo/SecurityConfig.java`:

```java
package demo;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class SecurityConfig {

    @Bean
    PasswordEncoder passwordEncoder() {
        return new BCryptPasswordEncoder();
    }

    @Bean
    UserDetailsService users(PasswordEncoder encoder) {
        UserDetails learner = User.withUsername("learner")
                .password(encoder.encode("study123"))
                .roles("USER")
                .build();
        return new InMemoryUserDetailsManager(learner);
    }

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http)
            throws Exception {

        http.authorizeHttpRequests(auth -> auth
                .requestMatchers("/", "/logged-out").permitAll()
                .anyRequest().authenticated());

        http.formLogin(form -> form
                .defaultSuccessUrl("/me", true)
                .permitAll());

        http.logout(logout -> logout
                .logoutUrl("/logout")
                .logoutSuccessUrl("/logged-out")
                .invalidateHttpSession(true)
                .clearAuthentication(true)
                .deleteCookies("JSESSIONID"));

        // CSRF remains enabled. POST logout and login require a CSRF token.
        return http.build();
    }
}
```

The configuration does not use `csrf.disable()` and does not hand-write a logout endpoint. Spring Security's `LogoutFilter` is wired into the filter chain; after logout, the session is invalidated and local `Authentication` is cleared.

`deleteCookies("JSESSIONID")` helps the browser drop the cookie, yet security still requires that the old session ID is no longer accepted by the server. With custom cookie names/paths/domains, tune the cookie-clearing policy for your environment. The demo password is BCrypt-hashed; never hard-code production accounts.

### 8.4. `DemoController`

`src/main/java/demo/DemoController.java`:

```java
package demo;

import org.springframework.security.core.Authentication;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class DemoController {

    @GetMapping("/")
    public String home() {
        return "public";
    }

    @GetMapping("/me")
    public String me(Authentication authentication) {
        return authentication.getName();
    }

    @GetMapping("/logged-out")
    public String loggedOut() {
        return "logged-out";
    }
}
```

### 8.5. `MockMvc`: Session Before and After Logout

`src/test/java/demo/LocalLogoutTest.java`:

```java
package demo;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.mock.web.MockHttpSession;
import org.springframework.test.web.servlet.MockMvc;

import static org.junit.jupiter.api.Assertions.assertTrue;
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.csrf;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.redirectedUrl;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class LocalLogoutTest {

    @Autowired
    MockMvc mvc;

    private MockHttpSession login() throws Exception {
        MockHttpSession session = new MockHttpSession();

        mvc.perform(post("/login")
                        .session(session)
                        .with(csrf())
                        .param("username", "learner")
                        .param("password", "study123"))
                .andExpect(status().is3xxRedirection());

        return session;
    }

    @Test
    void publicEndpointIsAvailable() throws Exception {
        mvc.perform(get("/"))
                .andExpect(status().isOk())
                .andExpect(content().string("public"));
    }

    @Test
    void anonymousRequestRequiresLogin() throws Exception {
        mvc.perform(get("/me"))
                .andExpect(status().is3xxRedirection());
    }

    @Test
    void loggedInSessionAccessesProtectedEndpoint() throws Exception {
        MockHttpSession session = login();
        mvc.perform(get("/me").session(session))
                .andExpect(status().isOk())
                .andExpect(content().string("learner"));
    }

    @Test
    void logoutRequiresCsrfAndInvalidatesSession() throws Exception {
        MockHttpSession session = login();

        mvc.perform(post("/logout").session(session))
                .andExpect(status().isForbidden());

        // Missing CSRF: logout has not occurred.
        mvc.perform(get("/me").session(session))
                .andExpect(status().isOk())
                .andExpect(content().string("learner"));

        mvc.perform(post("/logout")
                        .session(session)
                        .with(csrf()))
                .andExpect(status().is3xxRedirection())
                .andExpect(redirectedUrl("/logged-out"));

        assertTrue(session.isInvalid());

        // New request carries no valid session.
        mvc.perform(get("/me"))
                .andExpect(status().is3xxRedirection());

        mvc.perform(get("/logged-out"))
                .andExpect(status().isOk())
                .andExpect(content().string("logged-out"));
    }
}
```

**Expected result:** 4 tests PASS per the demo dependencies/config. The tests perform real form login via `MockMvc` rather than `@WithMockUser`, because that annotation pre-populates `Authentication` and defeats testing the session lifecycle. `MockHttpSession.isInvalid()` verifies the session was invalidated; then a new request avoids reusing the invalidated session object.

### 8.6. Running and Observing

With JDK 17+ and compatible Gradle:

```bash
gradle test
gradle bootRun
```

If a Gradle Wrapper exists: use `./gradlew test`/`./gradlew bootRun` (macOS/Linux) or `.\gradlew.bat test`/`.\gradlew.bat bootRun` (Windows).

In a browser at `http://localhost:8080`:

1. `GET /me` while not logged in → redirects to the login page.
2. Log in as `learner` / `study123` → `GET /me` returns `learner`.
3. Visit `/logout` and submit POST via the confirmation form with CSRF token; do not use arbitrary GET logout.
4. After logout, `/logged-out` returns `logged-out`, and a fresh `/me` request requires authentication again.
5. Never expose real session cookies in screenshots/logs.

HTTP localhost is for practice only. Production requires HTTPS, appropriate `Secure`, `HttpOnly`, and `SameSite` cookies, session timeouts/revocation, and CSRF policies.

**Limitation:** this program does not call an OP `end_session_endpoint` and does not call an OAuth2 revocation endpoint. Testing SSO/token revocation requires integrating a real IdP/AS/RS or test doubles with explicit contracts.

## 9. Combining Local Logout, OP Logout, and Token Revocation in a Product

If an app combines a local session, OIDC login, and refresh tokens in server-side `OAuth2AuthorizedClientService`, a “complete logout” flow may require orchestration:

```text
POST /logout + CSRF
    |
    +--> identify user/client/authorized-client from trusted server state
    |
    +--> save details needed to safely invoke revocation/OP logout
    |
    +--> invalidate local session + clear Authentication/remember-me
    |
    +--> call RFC7009 revoke refresh token (if policy needs and AS supports)
    |        |
    |        +--> track success/error/timeout without leaking secrets
    |
    +--> redirect browser to OP end_session_endpoint if supported
    |
    +--> post-logout redirect back to app
    |
    +--> UI accurately communicates the scope completed
```

Exact ordering depends on framework hooks and your threat model. Specifically, if `OidcUser` or `id_token_hint` is needed, extract trusted details from `Authentication` **before it is cleared** or rely on the authentication parameter passed to standard handlers. Never take token hints from untrusted client input.

If remote revocation or OP logout fails, **do not keep a privileged local session alive** solely due to a network failure. At the same time, never say “logged out on all devices” when only local session destruction is certain; record partial failures and handle them per policy.

### 9.1. “Log Out This Device”

Usually requires invalidating the current session, clearing this device's remember-me credential (if architecture supports per-device scope), clearing local token caches, and potentially revoking refresh tokens tied to this device. Does not necessarily terminate IdP SSO or sessions on other devices.

### 9.2. “Log Out of SSO”

Requires OP logout if supported alongside destroying the current RP's local session. Other RPs are affected only when front/back-channel logout or an equivalent centralized mechanism exists. Access JWTs may remain valid without RS revocation checks.

### 9.3. “Log Out All Devices”

Requires identifying all sessions, remember-me series, and OAuth2 grants/tokens of the user, coordinating revocation across systems, and having the IdP terminate sessions per provider policy. A default `POST /logout` on App A **cannot** automatically invalidate App B's `HttpSession`.

## 10. Troubleshooting: Logged Out Yet Still Able to Use the System

| Symptom | Possible explanation | What to check |
| --- | --- | --- |
| `GET /me` redirects to `/login` after logout | Local logout cleared session authentication | Old session ID has no privileges; CSRF/handlers correct |
| OIDC logs back in without a password | IdP SSO session remains | Is RP-Initiated Logout implemented? Does OP support it? |
| App B stays authenticated | App B holds its own local session | Are front/back-channel logout, session mapping, and tests present? |
| API still accepts old Bearer JWT | JWT is verified offline and unexpired | TTL, denylist, introspection, AS policy |
| Refresh token still mints new tokens | Grant/token not revoked at the right AS | RFC 7009 request, client authentication, refresh test |
| Browser auto-logs back in | Remember-me cookie/token remains | `LogoutHandler`/repository cleanup |
| `POST /logout` returns 403 | Missing CSRF token | Keep CSRF, send valid token |
| GET logout changes no state | CSRF protects logout via POST | Use form POST or API with proper CSRF |
| `removeAuthorizedClient` called yet JWT still works | Only cleared local storage | Revocation/RS validation are separate mechanisms |
| Revocation returns HTTP 200 yet RS still accepts token | HTTP 200 does not prove RS knows about revocation | Test old token against real API; check token type |
| IdP logout URL fails or doesn't redirect back | Endpoint/URI not allowlisted | Inspect metadata, client registration, provider support |
| Local logout succeeds yet remote backend times out | Partial failure | Local fails closed; telemetry/retries and honest UI |

Never enable logging of `Authorization`, cookies, session IDs, refresh tokens, or ID tokens while debugging; those are reusable credentials. Trace via secret-free event IDs, metrics, and correlation IDs.

## 11. Security and E2E Testing Checklist

- **Scope:** product labels clearly distinguish local/IdP/token/global logout.
- **Local session:** `HttpSession` invalidated; `SecurityContext` is not reloaded from old cookies.
- **Cookies:** deletion matches path/domain and flags; server-side invalidation is the primary ground truth.
- **CSRF:** POST logout without token is blocked; with token it succeeds.
- **Remember-me:** no unintended auto-login against policy from remaining cookies.
- **OIDC:** OP `end_session_endpoint` supported, post-logout redirect allowlisted, matching client/issuer.
- **SLO:** if promising global SSO, other RPs receive/verify front/back-channel logout notifications.
- **OAuth2 client local cache:** remove authorized-client records per policy; do not confuse with remote revocation.
- **Refresh tokens:** send authenticated revocation requests to the AS when needed; test that refreshing fails.
- **Access tokens:** verify whether the RS handles revocation or JWTs have suitably short TTLs.
- **ID tokens:** never use them to call APIs or assume they are revoked like access tokens.
- **Logout-all:** session registries, remembered devices, and grants have real revocation mechanisms.
- **Remote errors:** timeouts/retries/partial successes are observed, and local sessions always fail safely.
- **Security:** TLS, CSRF, cookie security, secret storage, avoiding open redirects and tokens in logs.
- **Multiple `SecurityFilterChain`s:** verify the logout endpoint belongs to the right chain/registration.
- **Outcomes:** do not assert only status 302; inspect each state on its owning system.

## 12. Self-Check Questions

1. **Does local logout delete the IdP's cookies?** No. An RP cannot directly delete cookies belonging to the OP's origin.
2. **Why can OIDC still log in without a password after logout?** The local session may be gone while the OP's SSO session remains valid.
3. **Does RP-Initiated Logout automatically log out other RPs?** Not guaranteed; the OP and participating RPs must support the corresponding mechanisms.
4. **Does `removeAuthorizedClient` call RFC 7009?** Not by default; it removes the authorized-client record on the application side.
5. **Does revoking a refresh token make already-issued JWT access tokens fail immediately?** Never assume so.
6. **What is an ID token?** An OIDC token telling the RP about authentication, not a bearer access token for calling APIs directly.
7. **Why can a revocation endpoint return 200 for a nonexistent token?** To avoid leaking token existence; status alone does not prove RS synchronization.
8. **Is deleting `JSESSIONID` on the frontend enough for logout?** No; server-side session/authentication must be invalidated.
9. **Can remember-me auto-log a user back in?** Yes, if only the session is deleted while a remember-me cookie/token remains valid.
10. **Why does POST logout need CSRF?** Browsers automatically attach cookies, so cross-origin triggers can cause unwanted side effects.
11. **Does an OAuth2 Resource Server automatically revoke an IdP's JWTs?** No; dedicated AS/RS policies are needed.
12. **What does logging out all devices require?** Revoking all relevant sessions/tokens/grants, not just a single local `HttpSession`.

**Key takeaway:** **Local logout** ends the application's session and `SecurityContext`; **IdP logout** targets the SSO session at the OpenID Provider per supported protocol; **OAuth2 token revocation** alters token usability at the AS without automatically invalidating every live access JWT. These are **three separate contracts** that must be implemented, observed, and tested independently. When combining them, ensure local sessions fail closed, never leak credentials, and report results accurately within scope.
