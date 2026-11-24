# Local Logout Does Not Automatically Revoke Every Token or External Identity Provider Session

> **Module:** Spring Security - fundamentals  
> **Group:** Login and Logout  
> **Core message:** An application's `POST /logout` can clear login state **within that application**, yet it does not by default revoke access tokens, refresh tokens, ID tokens, SSO sessions at an Identity Provider (IdP), or sessions in other applications.

## 1. Lesson objectives

After this lesson you should be able to understand and explain:

- Why after logging out of a Spring Boot application, logging back in can happen very quickly without asking for a password if the IdP still holds an SSO session.
- Why `SecurityContext`, `HttpSession`, application session cookies, IdP cookies, access tokens, and refresh tokens **are not one single object**.
- What Spring Security's `LogoutFilter` handles and where its boundary of responsibility ends.
- The differences between **local logout**, **OpenID Connect RP-Initiated Logout**, **OAuth 2.0 token revocation**, and **cross-application logout** (front-channel/back-channel).
- Why an already-issued JWT access token can still be accepted by a Resource Server after the application's browser session is deleted.
- How to build a Java 17+/Spring Security app and test demonstrating that local logout **does not automatically call** external token systems.
- How to design logout policies and tests matching requirements for "this device only," "this application," "all applications," or "all devices."

## 2. A single user can hold multiple distinct login states

Consider this common architecture:

~~~text
                      Browser
                /                 \
               v                   v
      Spring Boot App (RP)    Identity Provider (OP/IdP)
         App cookie             SSO login cookie
         HttpSession            Session at IdP
         SecurityContext        OAuth2/OIDC Authorization Server
               |                      |
               |     issues token     |
               +<---------------------+
               |
               v
          Resource Server
       Validates access token

States/credentials have independent lifecycles.
~~~

Within one user session, all of the following components can coexist:

| Component | Who typically manages it? | What is it used for? |
| --- | --- | --- |
| Application session cookie, such as `JSESSIONID` or `SESSION` | Application / Spring Session | Carries the ID to look up the **application's** `HttpSession` |
| `HttpSession` and `SecurityContext` | Spring Security + Servlet/Spring Session | Remembers the user's `Authentication` across requests to the application |
| IdP login cookie | External identity system | Remembers that the user authenticated at the IdP, enabling SSO |
| **ID token** (OIDC) | Issued by IdP, consumed by OIDC client | Attests login/identity information for the client under OIDC |
| **Access token** (OAuth 2.0) | Issued by Authorization Server | Lets a client call APIs/Resource Servers within granted scopes/lifetime |
| **Refresh token** | Issued by Authorization Server | Lets a client obtain new access tokens per policy |
| App B's session | App B | Can be independent of App A's session even with the same IdP |

This is why the phrase "log out" is **not specific enough** for security design. You must answer: log out **from where**, **from which devices**, **revoke which credentials**, and **what propagation to other systems** is required?

## 3. What does Spring Security Servlet's default `POST /logout` do?

For applications using form login and sessions, Spring Security provides `LogoutFilter`. When CSRF protection is enabled, a state-changing logout is handled by default via **HTTP POST** to `/logout` with a valid CSRF token. `GET /logout` may show a confirmation page supporting POST.

Common configuration example:

~~~java
// DSL snippet inside SecurityFilterChain configuration.
http
    .authorizeHttpRequests(auth -> auth
        .requestMatchers("/public").permitAll()
        .anyRequest().authenticated()
    )
    .formLogin(Customizer.withDefaults())
    .logout(Customizer.withDefaults());
~~~

When logout runs under the proper default configuration, `LogoutHandler`s can:

1. Invalidate the application's `HttpSession` (`SecurityContextLogoutHandler`).
2. Clear `SecurityContextHolderStrategy` and the application's security context persistence.
3. Delete related remember-me authentication/tokens if configured.
4. Clear the corresponding CSRF token (`CsrfLogoutHandler`).
5. Publish `LogoutSuccessEvent` and run `LogoutSuccessHandler`, typically redirecting to `/login?logout`.

**Those operations do NOT mean:**

- Deleting the IdP's login cookie on another domain.
- Sending a revocation request to the OAuth 2.0 Authorization Server.
- Canceling every refresh token or access token issued for the same account.
- Logging out another application that maintains its own session.
- Removing tokens on another device or in another mobile app.
- Causing a Resource Server to automatically stop accepting unexpired JWTs.

`LogoutFilter` runs inside **the current application's security filter chain**. It has no authority to control cookies across all domains and does not automatically know about every token issued by external systems.

### Logout CSRF should not be skipped

~~~html
<!-- Illustrative form for server-rendered app. CSRF value must
     be populated by the template engine from the real request; never hardcode. -->
<form method="post" action="/logout">
  <input type="hidden" name="_csrf" value="TOKEN_FROM_SERVER">
  <button type="submit">Sign out</button>
</form>
~~~

The HTML above is an explanatory sample, **not a complete production form**: token values and parameter names may be rendered differently by your framework. Do not arbitrarily turn logout into GET or disable CSRF app-wide just to make a button work. Browsers can also suffer *logout CSRF* attacks if the endpoint is not properly protected.

## 4. Three scenarios that must be clearly distinguished

### Scenario A — Plain Spring Boot form login with only an application session

~~~text
Browser -> App /login -> App session authenticated
Browser -> POST /logout -> App invalidates session
Browser -> /private -> requires logging in again
~~~

If there is no IdP, local logout may suffice for "log out of this application." Still, if there is a remember-me cookie, tokens for another API, or sessions on other devices, each part needs its own policy.

### Scenario B — Application using OAuth2/OIDC Login with an SSO IdP

~~~text
1. Browser visits App A -> no local session yet.
2. App A redirects to IdP.
3. User enters password at IdP; IdP creates SSO session cookie.
4. App A receives OIDC result, creates local session.
5. User submits POST /logout on App A.
6. App A deletes local session. IdP session cookie may still remain.
7. User revisits App A -> redirected to IdP -> IdP still has SSO session.
8. IdP may authenticate immediately without prompting for password.
9. App A creates a new local session.
~~~

A user says, "I just logged out, yet when I clicked login I wasn't asked for a password." That **does not prove** `LogoutFilter` failed. Local logout may have succeeded, while **the session at the IdP remained alive**; seamless SSO is the designed behavior.

### Scenario C — API using Bearer access tokens

~~~text
Client holds access token (JWT or opaque)
    |
    +-- Call API X: Authorization: Bearer <token>
    |
    +-- Delete local app session / cookie
    |
    +-- Old token may still be within its validity period
    |
    +-- Call API X again with the exact same old token
          |
          v
      Resource Server validates token per its own policy
~~~

A JWT-based Resource Server typically checks signature, issuer, `exp`/`nbf` timestamps, and configured validations. Deleting the browser session in an OAuth2 client **does not automatically broadcast a token revocation signal** to all Resource Servers.

**Note:** If the Resource Server uses token introspection or a denylist updated on revocation, results can differ. Token revocation behavior depends on actual architecture, never on guessing from the label "JWT" or "logout succeeded."

## 5. Boundary matrix: which action affects which credential?

| Action | Local app session | SSO session at IdP | Issued access token | Refresh token | App B with its own session |
| --- | --- | --- | --- | --- | --- |
| Default `POST /logout` on App A | Usually invalidated | Not automatically | Not automatically | Not automatically | Not automatically |
| Deleting App A session cookie in browser | Browser loses App A ID; server session not necessarily destroyed | No | No | No | No |
| OIDC RP-Initiated Logout from App A | Can be combined with local logout | Asks IdP to process logout | Not guaranteed to revoke all | Not guaranteed to revoke all | Depends on IdP and propagation mechanism |
| OAuth2 token revocation | Does not automatically change local session | Does not automatically delete SSO cookie | Depends on token, server policy, and checking mechanism | Revoked token can lose ability to refresh | Not automatically |
| Global logout / "log out all devices" | Scope must be defined | Must coordinate with IdP | Needs dedicated token policy | Needs dedicated token policy | Must coordinate across RPs |

**Read the table as "no automatic guarantee,"** not as a claim that specific IdP products lack features. A provider may offer dedicated logout, session-management, token-revocation, and global-sign-out APIs; how they affect each token must be verified against that provider's official documentation.

## 6. Runnable Java 17+ demo: local logout does not delete tokens in an external store

To visualize the **scope of effect**, the following Spring Boot example has two components:

- Real local form login/`HttpSession` managed by Spring Security.
- An `ExternalTokenRegistry` bean **simulating an external token system** so tests can verify it remains unchanged on local logout. This is only a *test double*; it is not an IdP, does not validate JWTs itself, and is not a production-usable token store.

Goal: test that local logout clears the local session without automatically calling `revoke(...)` on an independent system. With a real IdP, replace the simulator with controlled standard communication mechanisms.

**Example versions:** JDK 17+, Spring Boot 3.3.5, Spring Security 6.x, Gradle 8.x.

### 6.1. Project structure

~~~text
logout-boundary-demo/
├── settings.gradle
├── build.gradle
└── src/
    ├── main/java/demo/logoutboundary/
    │   ├── LogoutBoundaryApplication.java
    │   ├── SecurityConfig.java
    │   ├── DemoController.java
    │   └── ExternalTokenRegistry.java
    └── test/java/demo/logoutboundary/
        └── LocalLogoutTest.java
~~~

File `settings.gradle`:

~~~groovy
rootProject.name = 'logout-boundary-demo'
~~~

File `build.gradle`:

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.5'
    id 'io.spring.dependency-management' version '1.1.6'
}

group = 'demo'
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
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-security'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
~~~

The Spring Boot BOM manages Spring dependency versions. No OAuth2 client dependency is needed in the **plain form login** demo; the OIDC section later shows an independent extension.

### 6.2. Main application

File `src/main/java/demo/logoutboundary/LogoutBoundaryApplication.java`:

~~~java
package demo.logoutboundary;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class LogoutBoundaryApplication {
    public static void main(String[] args) {
        SpringApplication.run(LogoutBoundaryApplication.class, args);
    }
}
~~~

### 6.3. Spring Security configuration

File `src/main/java/demo/logoutboundary/SecurityConfig.java`:

~~~java
package demo.logoutboundary;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
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
    SecurityFilterChain securityFilterChain(HttpSecurity http)
            throws Exception {
        return http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/public").permitAll()
                .anyRequest().authenticated()
            )
            .formLogin(Customizer.withDefaults())
            .logout(Customizer.withDefaults())
            .build();
    }

    @Bean
    PasswordEncoder passwordEncoder() {
        return new BCryptPasswordEncoder();
    }

    @Bean
    UserDetailsService users(PasswordEncoder encoder) {
        UserDetails alice = User.withUsername("alice")
            .password(encoder.encode("demo-pass"))
            .roles("USER")
            .build();
        return new InMemoryUserDetailsManager(alice);
    }
}
~~~

The configuration keeps default CSRF enabled. `POST /logout` with a valid CSRF token operates on **the application's local session**. No line sends an HTTP request to an Authorization Server or revokes remote tokens.

### 6.4. Endpoint requiring local authentication

File `src/main/java/demo/logoutboundary/DemoController.java`:

~~~java
package demo.logoutboundary;

import org.springframework.security.core.Authentication;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class DemoController {

    @GetMapping("/public")
    public String publicPage() {
        return "public";
    }

    @GetMapping("/private")
    public String privatePage(Authentication authentication) {
        return "hello " + authentication.getName();
    }
}
~~~

### 6.5. Simulator for external token state

File `src/main/java/demo/logoutboundary/ExternalTokenRegistry.java`:

~~~java
package demo.logoutboundary;

import java.util.Set;
import java.util.concurrent.ConcurrentHashMap;
import org.springframework.stereotype.Component;

@Component
public class ExternalTokenRegistry {

    private final Set<String> activeTokens =
        ConcurrentHashMap.newKeySet();

    public ExternalTokenRegistry() {
        // Mock token, for test use only.
        activeTokens.add("demo-external-token");
    }

    public boolean isActive(String token) {
        return activeTokens.contains(token);
    }

    public void revoke(String token) {
        activeTokens.remove(token);
    }
}
~~~

This is **not** a real OAuth2 Authorization Server. It simulates having a credential store independent of the application session. Spring Security local logout knows nothing about this bean and does not automatically call `revoke()`.

### 6.6. MockMvc test defending the exact boundary

File `src/test/java/demo/logoutboundary/LocalLogoutTest.java`:

~~~java
package demo.logoutboundary;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.mock.web.MockHttpSession;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.MvcResult;

import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertTrue;
import static org.springframework.security.test.web.servlet.request
    .SecurityMockMvcRequestPostProcessors.csrf;
import static org.springframework.test.web.servlet.request
    .MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request
    .MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result
    .MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result
    .MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class LocalLogoutTest {

    @Autowired
    MockMvc mvc;

    @Autowired
    ExternalTokenRegistry external;

    @Test
    void localLogoutDoesNotRevokeExternalToken() throws Exception {
        // Log in using real Spring Security form login.
        MvcResult login = mvc.perform(
                post("/login").with(csrf())
                    .param("username", "alice")
                    .param("password", "demo-pass"))
            .andExpect(status().is3xxRedirection())
            .andReturn();

        MockHttpSession session =
            (MockHttpSession) login.getRequest().getSession(false);

        assertNotNull(session);

        // Session is authenticated and allows access to /private.
        mvc.perform(get("/private").session(session))
            .andExpect(status().isOk())
            .andExpect(content().string("hello alice"));

        // The "external" token store still holds the mock token.
        assertTrue(external.isActive("demo-external-token"));

        // Valid logout invalidates the local session.
        mvc.perform(post("/logout")
                .session(session)
                .with(csrf()))
            .andExpect(status().is3xxRedirection());

        assertTrue(session.isInvalid());

        // New request without a local session must log in again.
        mvc.perform(get("/private"))
            .andExpect(status().is3xxRedirection());

        // Token in the independent registry is NOT automatically revoked.
        assertTrue(external.isActive("demo-external-token"));

        // Only with an explicit revoke action does the registry change.
        external.revoke("demo-external-token");
        assertFalse(external.isActive("demo-external-token"));
    }
}
~~~

### 6.7. Running and interpreting the results

From the project root, with JDK 17+ and Gradle 8.x:

~~~bash
gradle test
~~~

**Expected result:** the single test `localLogoutDoesNotRevokeExternalToken` passes. This is an **expectation from the sample code**, not an execution recorded in this lesson.

The test's evidence consists of four independent assertions (covering the three phases):

| Check | Expectation |
| --- | --- |
| Form login then call `/private` with that session | HTTP 200, body `hello alice` |
| `POST /logout`, then call `/private` with a new request | Redirect to login; old session invalid |
| `external.isActive("demo-external-token")` right after local logout | Still `true` |
| Only when calling `external.revoke(...)` | Turns `false` |

**Important limitation:** The mock token in the test is not wired into an HTTP auth filter. The test proves the **responsibility boundary** rather than verifying what a specific real IdP will do. To prove end-to-end behavior in production, test real access/refresh tokens and IdP sessions before and after logout using the methods supported by your provider.

## 7. OIDC RP-Initiated Logout: asking the IdP to log out via browser

When an application uses **OpenID Connect Login** and the IdP supports [RP-Initiated Logout 1.0](https://openid.net/specs/openid-connect-rpinitiated-1_0.html), the application (*Relying Party / RP*) can redirect the browser to the IdP's logout endpoint (*OpenID Provider / OP*).

~~~text
Browser logged into both App A and IdP
           |
           v
POST /logout on App A
           |
           v
App A local session invalidated
           |
           v
LogoutSuccessHandler redirects browser
  to IdP end_session_endpoint
  with id_token_hint / post_logout_redirect_uri as appropriate
           |
           v
IdP processes logout request per policy
           |
           v
Browser may return to registered URL
~~~

This is **a request to the IdP**, not absolute power that immediately invalidates every application or token. The IdP may prompt for confirmation, have cross-app limits, and issued tokens still have their own lifecycles.

### Spring Security supports `OidcClientInitiatedLogoutSuccessHandler`

Illustrative configuration snippet *replacing* `SecurityConfig` in section 6's demo, intended for an app that already has OAuth2/OIDC client registrations and uses `oauth2Login()`:

~~~java
// Integration snippet, not a standalone Java class.
@Bean
SecurityFilterChain oidcSecurityFilterChain(
        HttpSecurity http,
        ClientRegistrationRepository clients) throws Exception {

    OidcClientInitiatedLogoutSuccessHandler oidcLogout =
        new OidcClientInitiatedLogoutSuccessHandler(clients);

    oidcLogout.setPostLogoutRedirectUri("{baseUrl}/logged-out");

    return http
        .authorizeHttpRequests(auth -> auth
            .requestMatchers("/", "/logged-out").permitAll()
            .anyRequest().authenticated()
        )
        .oauth2Login(Customizer.withDefaults())
        .logout(logout -> logout.logoutSuccessHandler(oidcLogout))
        .build();
}
~~~

Key types:

- `OidcClientInitiatedLogoutSuccessHandler` in `org.springframework.security.oauth2.client.oidc.web.logout`.
- `ClientRegistrationRepository` in `org.springframework.security.oauth2.client.registration`.
- `SecurityFilterChain`, `HttpSecurity`, `Customizer`, and `@Bean` use familiar Spring Security/Spring packages.

To use this snippet, add `spring-boot-starter-oauth2-client`, register an OIDC client, and configure the appropriate issuer/client ID/secret; the IdP must support `end_session_endpoint` or equivalent metadata. **Do not combine two SecurityFilterChain beans for the same requests without designing ordering/scoping.** This is a replacement configuration, not an add-on to the plain form-login demo.

`{baseUrl}/logged-out` is a template URI resolved by Spring Security from the request; the post-logout URL must be pre-registered/allowed by the IdP. Never take an arbitrary client-supplied redirect URL as the post-logout destination.

### Standard OIDC parameters

| Parameter | Meaning |
| --- | --- |
| `end_session_endpoint` | Logout URL published by the IdP in discovery metadata |
| `id_token_hint` | Previously issued ID token so the IdP can identify the associated login/session (recommended) |
| `post_logout_redirect_uri` | Where the browser may return after the IdP processes logout; must be registered/allowed |
| `state` | Opaque value for the RP to correlate upon return, if the flow uses it |
| `client_id` | Can help identify the client in certain cases supported by the specification |

Never build a "logout URL" by concatenating tokens/URIs manually while bypassing state validation and redirect allowlists. In particular, ID tokens are sensitive data; handle them via library-supported mechanisms, minimizing logging and exposure in analytics/history.

### Does RP-Initiated Logout guarantee global logout?

No. RP-Initiated Logout notifies the OP of a logout request from the RP. Synchronizing logout across apps B/C may require **OIDC Front-Channel Logout** or **Back-Channel Logout**, and each RP must support handling those signals. Issued tokens may still remain valid under access/refresh token policies and resource-server validation. Keep **SSO session logout** separate from **token revocation**.

## 8. OAuth 2.0 Token Revocation: a separate mechanism

[OAuth 2.0 Token Revocation (RFC 7009)](https://www.rfc-editor.org/rfc/rfc7009) defines an endpoint for a client to ask the Authorization Server to invalidate tokens that are no longer needed.

Conceptual example of a refresh-token revocation request:

~~~http
POST /oauth2/revoke HTTP/1.1
Host: idp.example.test
Content-Type: application/x-www-form-urlencoded
Authorization: Basic <client-authentication>

token=<refresh-token>&token_type_hint=refresh_token
~~~

**This is illustrative HTTP**, not a fixed endpoint present on every IdP and not real credentials. URL, client authentication, token types, rate limits, scopes, and policies must follow your Authorization Server's discovery/documentation.

### How does revoking a refresh token differ from revoking an access token?

- **Refresh token:** If successfully revoked, the client can no longer use that refresh token to request new access tokens. Effects on related access/refresh tokens depend on the Authorization Server's policy.
- **Access token:** Some servers support direct revocation. With opaque tokens and introspection, a Resource Server can see `active=false` after revocation (subject to caching/latency).
- **Self-contained JWT access token:** A Resource Server that only verifies signatures/claims locally usually **does not know** a token was revoked at the Authorization Server before `exp`, unless there is a denylist, introspection, status-update events, key rotation, or an additional mechanism.

RFC 7009 mandates support for revoking refresh tokens; support for access tokens is recommended depending on the server. Policies for revoking linked tokens depend on the Authorization Server. Even an HTTP 200 response from the revocation endpoint is not proof that an old JWT is immediately rejected at every Resource Server.

**Do not confuse these two statements:**

> "The refresh token can no longer be used to obtain new tokens."  
> "Every previously issued access token is immediately rejected by APIs."

The first statement can be true while the second remains false until the access token expires or an early-rejection mechanism takes effect.

### The client must know where tokens live

A Spring OAuth2 Client may store `OAuth2AuthorizedClient` (access token, and refresh token if granted) in an `OAuth2AuthorizedClientService` or repository. Removing the local authorized client/tokens from storage stops the app from reusing them, yet **does not automatically send a revocation request** to the IdP. Conversely, calling the revocation endpoint is a separate interaction with the token-issuing server. The two steps have different responsibilities.

If an application does not hold a refresh token, it cannot arbitrarily revoke another device's refresh token either. "Log out all devices" usually requires dedicated IdP admin/session-management APIs and permissions.

## 9. JWT Resource Server: why can old tokens still work?

Suppose a client holds a JWT access token with 10 minutes remaining. When the client sends:

~~~http
GET /api/orders HTTP/1.1
Host: api.example.test
Authorization: Bearer <jwt-access-token>
~~~

The Resource Server can use Spring Security `oauth2ResourceServer().jwt()` and `JwtDecoder` to verify signature, issuer, expiry, not-before, and configured policies.

~~~text
At t0: Authorization Server issues JWT, exp = t0 + 10 min
At t1: User logs out of Spring MVC client
At t2: Old client or holder of JWT sends request to API
At t2: If JWT is still valid and API does not check revocation,
       Resource Server can still accept the request
At t3: JWT expires -> rejected by exp validation
~~~

To support fast revocation requirements:

1. Use short-lived access tokens paired with appropriate refresh token rotation/revocation.
2. For opaque tokens, consider token introspection and suitable cache policies.
3. For JWTs, if immediate rejection is required, design a denylist or API-side issuance/session state check, trading off performance and availability.
4. During signing-key compromise or severe incidents, key rotation and incident response have their own role; do not treat rotating keys as a normal logout operation.
5. Define the maximum acceptable propagation/caching delay, then test old tokens after each kind of logout.

**Never disable JWT signature/expiry validation**, and never equate "deleting the token from localStorage" with server-side revocation: a stolen copy of the token can still be used until it is no longer accepted.

## 10. Front-channel and back-channel logout for multi-RP SSO systems

When the same user logs into App A, App B, and App C through one IdP, multiple sessions exist in parallel:

~~~text
                 Identity Provider
               /          |         \
              v           v          v
            App A        App B      App C
          session A    session B  session C
~~~

If the user logs out on App A:

- Local logout affects only session A.
- RP-Initiated Logout can ask the IdP to end the SSO session.
- The IdP can send logout notifications to App B/C if cross-app logout is supported and those RPs integrate it.
- Front-channel relies on the browser and cookie/cross-site/browser behaviors, so it may not be 100% reliable.
- Back-channel uses server-to-server notifications (logout tokens or standard/system messages) so RPs invalidate matching sessions; it requires message authentication, replay protection, and accurate session mapping.

**Back-channel logout does not automatically revoke every access token:** if APIs use self-validated JWTs, a separate revocation/introspection policy is needed.

If the security requirement is "revoke all access for a locked account within seconds," browser logout alone is insufficient. Integrate IdP, APIs, and session/token state to meet the defined SLA.

## 11. Defining the right scope for product requirements

A single "Logout" button label can hide four different intents:

| Intent | Desired scope | Technical prerequisites |
| --- | --- | --- |
| Log out of **App A in this tab/browser** | Clear session A and related local credentials | Spring Security logout; clear cookie/session; test A |
| Log out of **App A on all devices** | Destroy all of the user's sessions in App A | Session registry/index/store and API to invalidate multiple sessions |
| Log out of **the SSO IdP** | End the session at the IdP per provider policy | OIDC RP-Initiated Logout or equivalent vendor API |
| Log out of **all apps and revoke tokens** | Invalidate sessions A/B/C and refresh/access tokens in defined scope | IdP propagation + token revocation + resource-server strategy + tests |

The design must answer:

- Do you need to revoke **one refresh token**, a token family, all tokens for the account, or all app sessions?
- How long can propagation to Resource Servers take?
- Should the user be told "local logout succeeded, but SSO logout failed" or should logout fail when the IdP errors?
- Are other devices active, or does the user have multiple browser profiles?
- Does the IdP support OIDC RP-Initiated Logout, front-/back-channel logout, and token revocation for this client type?
- Should "Logout all" require higher privilege/reauthentication than "Logout this session"?

**Never claim "signed out everywhere" when the app only invalidated the local session.** Use UI messaging that accurately reflects the guarantee actually achieved.

## 12. Handling errors when the IdP or revocation endpoint is unavailable

A logout flow can partially fail:

~~~text
User clicks logout
    |
    v
Application invalidates local session successfully
    |
    v
Send logout/revoke request to IdP
    |
    +-- Success -> update state per actual guarantees
    |
    +-- Timeout / 5xx / network error
          |
          v
    Local session should still be handled safely
    Record state "remote logout unconfirmed"
    Retry or handle per policy
    Do not falsely report "all devices signed out"
~~~

Depending on the workflow, you can run local cleanup first or coordinate with the remote step. Avoid depending on IdP availability so tightly that a remote timeout leaves the local session intact while the user thinks they logged out.

If retrying revocation, respect provider constraints, token lifetimes, client authentication, and idempotency semantics. Never log raw access/refresh tokens in error messages. Monitoring should record correlation IDs, appropriately pseudonymized user/session references, token types, provider, timestamp, and outcome without exposing secrets.

## 13. End-to-end testing: beyond merely seeing the login page

**Local logout tests** verify behavior inside App A: the session is no longer authenticated, protected routes are blocked, remember-me is handled properly, and CSRF/cookie settings are valid.

**SSO logout tests** must use a real IdP test realm/sandbox. Reusing the same browser profile:

1. Log into App A through the IdP.
2. Verify cookies/session on App A and SSO session on the IdP.
3. Log out of App A using the local-only mechanism.
4. Try logging into App A again, noting whether credentials are prompted. If the SSO session remains, login may complete rapidly without a password.
5. Enable/integrate RP-Initiated Logout and test again; verify the browser actually hits `end_session_endpoint`, the IdP processes it, and it redirects back to the registered URI.
6. If App B exists, check whether session B is invalidated per the IdP's promise and front-/back-channel integration.
7. Use an access token issued **before logout** against the Resource Server in the test environment; observe how long it stays valid.
8. Try an old refresh token after revocation; it must not issue new access tokens once that token is successfully revoked and propagation finishes.
9. Test IdP unavailable, timeout, or revocation 5xx; measure local cleanup and user-facing messaging explicitly.

### Acceptance matrix

| Scenario | Test step | Expected outcome per policy |
| --- | --- | --- |
| Local logout App A | Call protected route with old A cookie | No longer authenticated on App A |
| IdP SSO not logged out | Try logging into App A again from IdP-logged browser | May re-authenticate without password; **must not be treated as a local logout bug** |
| OIDC RP logout | Browser hits end-session endpoint and returns to RP | Follows provider flow, no open redirect |
| Old JWT access token | Resend token before `exp` | Accepted/rejected per published revocation policy |
| Old refresh token | Use after revocation | Rejected once revocation takes effect |
| App B with independent session | Visit App B after App A logout | Follows front-/back-channel or session-revocation design, not guesswork |
| Global logout | Try other devices and APIs | Every component in promised scope stops granting access |
| IdP/revoke timeout | Log out while IdP fails | Local state and notice reflect truth, no false global success |
| CSRF/logout | Try POST without CSRF token in session app | Rejected per CSRF configuration |

**A test that only sees a redirect to login is insufficient** to prove the SSO session, refresh token, or old JWT is dead. Test each credential directly against the system that accepts that credential.

## 14. Common mistakes

| Mistake | Why it is wrong | Fix |
| --- | --- | --- |
| Treating `POST /logout` as global sign-out | It handles local security state by default | Distinguish local/IdP/token/session logout |
| Deleting App A's cookie thinking IdP's cookie is deleted | Cookies are scoped by domain/path/security model | Use the IdP's OIDC/logout API |
| Deleting refresh tokens only in the client database | Issuing server may still accept issued copies | Call the revocation endpoint per policy |
| Revoking refresh tokens and assuming JWT access tokens died | Offline JWT Resource Servers may trust tokens until `exp` | Short TTL, introspection/denylist, or revocation strategy |
| Using `GET /logout` without CSRF | Invites logout CSRF or diverges from default behavior | Use POST + valid CSRF token per framework |
| Logging raw tokens/session IDs | Credentials can leak and be replayed | Mask/redact secrets, minimal audit metadata |
| Testing only App A, ignoring App B | Misses still-active cross-app sessions | Test multi-RP/browser/device |
| Reporting "signed out everywhere" during IdP timeout | UI promises exceed reality | Return truthful status and retry workflow |
| Assuming `clearAuthentication(true)` wipes all tokens | Only affects local security context | Separate token revocation and IdP session logout |
| Building `post_logout_redirect_uri` from user input | Risk of redirecting to untrusted domains | Use registered/allowlisted redirect URIs |
| Lacking policy for locked accounts or revoked roles | Old sessions/tokens may continue working | Session invalidation + token strategy + API enforcement |

## 15. Self-check questions

**Question 1.** A user logs out of App A, clicks Login again, and gets right back in without a password. Did Spring Security fail to delete the session?

**Answer:** Not necessarily. `LogoutFilter` may have deleted the local session; however, the SSO session at the IdP is still active, so the IdP re-authenticates and App A creates a new session.

**Question 2.** Does deleting the `JSESSIONID` cookie revoke a JWT that the client sent in `Authorization: Bearer`?

**Answer:** Not automatically. Cookies and JWT access tokens are different credentials checked at different points.

**Question 3.** Does successfully revoking a refresh token prove previously issued JWT access tokens can no longer call APIs?

**Answer:** No. A Resource Server validating JWTs on its own can keep accepting them until `exp` unless an early-rejection mechanism is present.

**Question 4.** What is `OidcClientInitiatedLogoutSuccessHandler` for?

**Answer:** It helps a Spring Security OAuth2/OIDC client redirect the browser to the OpenID Provider's logout endpoint under RP-Initiated Logout when supported by the provider/configuration; it is not an auto-revocation mechanism for all tokens.

**Question 5.** A local logout test sees `/private` redirect to login. Can we report "all devices signed out"?

**Answer:** No. You must verify all sessions, devices, RPs, and tokens within the promised scope.

**Question 6.** When the IdP times out during logout, what should be conveyed to the user?

**Answer:** Report the true state: local logout may have completed, while remote/global logout is unconfirmed; never claim all sessions/tokens were revoked without proof.

## 16. Deployment checklist

- [ ] Product clearly distinguishes **logout this app**, **logout IdP**, and **logout all devices**.
- [ ] Local session is invalidated; SecurityContext, remember-me, CSRF, and cookies are handled as needed.
- [ ] Logout endpoint uses POST/CSRF for stateful browser apps where applicable.
- [ ] OIDC RP-Initiated Logout is enabled only when supported by the provider with registered redirect URIs.
- [ ] Access/refresh token revocation is integrated **separately**, matching the IdP's endpoint/credential/token policy.
- [ ] Resource Servers have clear policies for accepting/rejecting revoked tokens; JWT local validation and propagation delays are understood.
- [ ] Related apps support and test front-/back-channel logout if SSO/global logout is promised.
- [ ] Tokens, session IDs, ID tokens, and client secrets never leak in uncontrolled logs/URLs.
- [ ] When IdP or revocation fails, UI and audit accurately reflect each step's outcome.
- [ ] Integration tests exist after logout reusing **old cookies, old refresh tokens, and old access tokens** against their respective systems.

## 17. Summary and official documentation

**Local logout has local scope.** Spring Security can invalidate local sessions and SecurityContext, yet does not automatically delete SSO cookies at an IdP or revoke all OAuth2/OIDC tokens. To expand scope, integrate the right mechanisms: OIDC RP-Initiated Logout for IdP sessions, front-/back-channel logout for related RPs, OAuth2 Token Revocation for tokens, and a Resource Server strategy to reject old credentials within your SLA.

References:

- [Spring Security — Handling Logouts](https://docs.spring.io/spring-security/reference/servlet/authentication/logout.html)
- [Spring Security — OAuth2 Login Logout](https://docs.spring.io/spring-security/reference/servlet/oauth2/login/logout.html)
- [Spring Security — OAuth2 Resource Server JWT](https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/jwt.html)
- [OpenID Connect — RP-Initiated Logout 1.0](https://openid.net/specs/openid-connect-rpinitiated-1_0.html)
- [RFC 7009 — OAuth 2.0 Token Revocation](https://www.rfc-editor.org/rfc/rfc7009)
- [RFC 7662 — OAuth 2.0 Token Introspection](https://www.rfc-editor.org/rfc/rfc7662)
