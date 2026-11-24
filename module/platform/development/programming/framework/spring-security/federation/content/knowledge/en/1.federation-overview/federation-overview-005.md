# Application Sessions, IdP Sessions, and the Single Sign-On (SSO) Experience

In a federated login system, a user can sign in to application A and then open application B without re-entering their password. This experience is called **Single Sign-On (SSO)**. However, **SSO does not mean applications share one session**: each application maintains its own session, while the Identity Provider (IdP) manages the IdP's own authentication session.

This lesson applies to **Spring Security Servlet** with **Spring Boot 3.x / Spring Security 6.x, Java 17+, OpenID Connect (OIDC)** examples. The distinction between sessions also applies across many other web platforms.

## 1. Three Layers to Distinguish

| Concept | Owner | What Does the Browser Send? | Role |
| --- | --- | --- | --- |
| **Application session (local/RP session)** | Each application A, B | Session cookie of that application's domain, commonly **JSESSIONID** | Holds `Authentication`/`SecurityContext` and local login state. |
| **IdP session (IdP/OP session)** | Identity Provider | Login cookie belonging to the IdP domain, name determined by the IdP | Helps the IdP know the user authenticated previously when the browser returns. |
| **SSO** | Coordinated experience across redirects to the IdP | Browser can send the IdP cookie when on the IdP domain | B can complete a new login flow without the user re-entering credentials. |

A **Relying Party (RP)** is an application receiving authentication results from an IdP; an **OpenID Provider (OP)** is the IdP's OIDC role. A and B can trust the same OP while still having separate cookies, session IDs, timeouts, authorization rules, and logout operations. The browser does not send A's cookie to B if their domains differ; nor does the IdP cookie become A's or B's session cookie.

Three common misconceptions: "same IdP means shared JSESSIONID", "SSO means same access token", and "logging out of one app automatically logs out the whole system". None of these is guaranteed simply by enabling OIDC login.

### Distinguishing Sessions from OIDC/OAuth2 Tokens

- **Session ID** is a secret identifier helping the application server look up session state; a common cookie name is `JSESSIONID`, though it can be changed.
- **ID token** is an OIDC result describing identity for a specific client; issuer, audience, expiration, nonce, and protocol conditions must be verified.
- **Access token** is issued for accessing APIs/resources according to its audience/scope; it is not an application session cookie and does not by itself create SSO.
- **Refresh token** (when issued) helps request new access tokens per policy; having a refresh token does not prove the IdP cookie is still valid.

IdP sessions, local sessions, and tokens all have different lifecycles. An expired ID token does not automatically delete an already-created local session; an active local session does not prove the IdP session still exists. How Spring stores authorized clients/tokens depends on the repository/service and architecture: never assume every token always lives in `HttpSession`.

## 2. Federated Login Flow Across Two Applications

Suppose A and B are two web applications trusting the same IdP I; each application has a valid OIDC client registration and redirect URI.

1. The user accesses a protected page of **A** without an A session. Spring Security starts **oauth2Login()**, redirecting the browser to I's authorization endpoint.
2. The browser arrives at **domain I**, carrying the IdP cookie if present. When there is no IdP session or policy requires it, I displays login/MFA and then maintains the IdP session per its configuration.
3. I redirects the browser back to A's callback with an authorization code. A checks **state** and exchanges the code for tokens via a server-to-server channel; the OIDC result is validated per protocol (including ID token, issuer, audience, nonce when applicable). **PKCE** helps protect the authorization code flow, is especially necessary for public clients, and is recommended in suitable configurations.
4. A creates `Authentication` in `SecurityContext` and, following the default **stateful** model of a Servlet application, maintains a local session; the browser receives A's session cookie.
5. The user opens a protected page in **B**. Because B cannot read A's cookie/session, B still creates a **new OIDC request** and redirects to I.
6. The browser goes to domain I with the existing IdP cookie. If I accepts the active session and does not require re-authentication, I completes the authorization flow for B without showing a password prompt.
7. B validates the result and creates an **independent B session**. The user perceives "single sign-on", while the system has one IdP session and two distinct local sessions.

Simple diagram:

~~~text
Browser ── protected page ──> A
Browser <── OIDC redirect ─── A
Browser ── OIDC request ────> IdP ── may require login/MFA
Browser <── code/redirect ─── IdP
A ── exchange code, verify token ──> IdP
A ── create session A ──> Browser

Browser ── protected page ──> B
Browser <── OIDC redirect ─── B
Browser ── IdP cookie ──────> IdP ── may reuse existing IdP session
Browser <── code/redirect ─── IdP
B ── exchange code, verify token ──> IdP
B ── create session B ──> Browser
~~~

**B asks the IdP to authenticate the user, not A for A's session.** The IdP session makes the second authentication easier; the RP must still create and control its own session.

### When Does the IdP Still Prompt for a Password?

SSO depends on a valid IdP session, the same browser profile holding the IdP cookie, login policy, MFA/consent requirements, the authentication assurance level, and OIDC parameters. **`prompt=login`** or **`max_age`** can force re-authentication even if the IdP has a session. Incognito windows, different browsers, or different devices normally do not share the original profile's IdP cookie.

Do not confuse SSO via **top-level redirects** with **silent authentication in an iframe**: third-party cookies inside iframes are often subject to additional browser/security restrictions. You cannot promise "never seeing an IdP screen" in every case.

## 3. Application Sessions and IdP Sessions Expire Independently

| State | What Usually Happens |
| --- | --- |
| A session alive, IdP session alive | New requests to A are served via the local session without needing to visit the IdP. |
| A session expired, IdP session alive | A redirects to the IdP; the IdP may authenticate without asking for a password, and A creates a new session. |
| A session alive, IdP session expired | A usually keeps serving requests until the local session expires or additional invalidation/checks occur. |
| Both A session and IdP session expired | The next access to a protected resource usually requires signing in again at the IdP. |
| User logs out locally at A, B session alive | B usually stays logged in; the IdP session may still exist. |
| User logs out at IdP, A/B local sessions alive | A/B usually do not destroy their sessions automatically without Single Logout or a session-sync mechanism. |

Example: A uses a **20-minute inactivity** timeout, while the IdP allows an **8-hour** SSO session. After 30 minutes of inactivity in A, reopening A may redirect to the IdP. If the IdP session is still valid, the user does not enter a password; however, A may have just **created a new session**, not revived the old A session.

Distinguish **idle timeout** (expiration due to inactivity) from **absolute lifetime** (maximum total duration). "Remember me", MFA policies, and refresh tokens can change the experience, but they do not merge sessions into a single entity. Local sessions and IdP sessions can be destroyed independently at different times.

## 4. How Does Spring Security Manage Local Sessions?

In stateful **Spring Security Servlet**, the security filter chain restores `SecurityContext` for requests matching a local session; `Authentication` describes the authenticated principal. **`oauth2Login()`** handles sign-in via OAuth2/OIDC, while `SecurityContextRepository` and the session policy decide how local state is stored across requests.

- Cookie `JSESSIONID` is the common default name for a Servlet session; the application can change the cookie name and policy. Cookies belong to their respective domain/path and are not used to share sessions across independent RPs.
- Spring Security supports **session fixation** protection upon stateful login; session ID rotation depends on configuration and the servlet container.
- **`SessionCreationPolicy.STATELESS`** follows a different model, typically used for Resource Server APIs checking a Bearer token on every request. Do not assume a stateless API has the web session behavior described above.
- **OAuth2 Login** and **OAuth2 Resource Server** are two different roles. An application can use both if needed, but an API access token does not replace an IdP session.

### Runnable Example with Spring Boot 3.3.5 + Java 17

Prerequisites: an OpenID Provider supporting discovery; register a **confidential web client** named **demo**, obtain the client ID/secret, and allow redirect URI **http://localhost:8080/login/oauth2/code/demo**. Replace the sample **issuer-uri** with your OP's real issuer. Place the files under the following package directories.

**pom.xml**

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.3.5</version>
        <relativePath/>
    </parent>
    <groupId>com.example</groupId>
    <artifactId>federation-demo</artifactId>
    <version>0.0.1-SNAPSHOT</version>
    <properties>
        <java.version>17</java.version>
    </properties>
    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-web</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-security</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-oauth2-client</artifactId>
        </dependency>
    </dependencies>
    <build>
        <plugins>
            <plugin>
                <groupId>org.springframework.boot</groupId>
                <artifactId>spring-boot-maven-plugin</artifactId>
            </plugin>
        </plugins>
    </build>
</project>
~~~

**src/main/resources/application.yml**

~~~yaml
spring:
  security:
    oauth2:
      client:
        registration:
          demo:
            provider: demo
            client-id: ${OIDC_CLIENT_ID}
            client-secret: ${OIDC_CLIENT_SECRET}
            scope:
              - openid
              - profile
              - email
        provider:
          demo:
            issuer-uri: https://idp.example.com/realms/demo
server:
  servlet:
    session:
      timeout: 30m
~~~

**src/main/java/com/example/federation/FederationDemoApplication.java**

~~~java
package com.example.federation;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class FederationDemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(FederationDemoApplication.class, args);
    }
}
~~~

**src/main/java/com/example/federation/SecurityConfig.java**

~~~java
package com.example.federation;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class SecurityConfig {
    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http) throws Exception {
        http.authorizeHttpRequests(auth -> auth
                    .requestMatchers("/").permitAll()
                    .anyRequest().authenticated())
            .oauth2Login(Customizer.withDefaults());
        return http.build();
    }
}
~~~

**src/main/java/com/example/federation/DemoController.java**

~~~java
package com.example.federation;

import org.springframework.security.core.annotation.AuthenticationPrincipal;
import org.springframework.security.oauth2.core.oidc.user.OidcUser;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class DemoController {
    @GetMapping("/")
    public String publicPage() {
        return "Trang cong khai";
    }

    @GetMapping("/me")
    public String me(@AuthenticationPrincipal OidcUser user) {
        return "Hello, " + user.getSubject();
    }
}
~~~

Set the two environment variables **OIDC_CLIENT_ID** and **OIDC_CLIENT_SECRET** from the registered application, configure a real issuer, and run:

~~~bash
mvn spring-boot:run
~~~

- **GET http://localhost:8080/** returns the exact text **Trang cong khai**.
- **GET http://localhost:8080/me** without a session redirects into the OIDC flow; after login, the endpoint returns a string of the form **Hello, <subject provided by OP>**. The subject depends on the account, so a fixed output cannot be given.
- Spring Security uses the login entry point **/oauth2/authorization/demo** and callback **/login/oauth2/code/demo** by default. Sign-in can only complete with a valid IdP/registration.

The Java snippets form a complete application that compiles once dependencies are downloaded; the sample issuer address must be replaced with a real OP. Localhost HTTP is for testing; production must use HTTPS/secure cookies. Do not commit client secrets to source control.

### Why Does the Application Still Need a Session After the Callback?

The OIDC callback proves the user was authenticated by the IdP when the flow completed. To avoid redirecting through the full OIDC flow on every web request, the application typically holds `Authentication` in a local session. The application itself decides the lifetime, access limits, and how to invalidate its session. When deploying multiple instances, you need an architecture ensuring any instance handling a request can locate the session (for example, shared session storage with Spring Session) or an appropriate routing strategy.

## 5. App Logout, IdP Logout, and Single Logout

### Local Logout

In the basic configuration above, Spring Security performs **local logout**: clearing authentication state and invalidating `HttpSession` as configured. With CSRF enabled by default, logout is typically submitted via **POST /logout** with a valid CSRF token; `GET /logout` may show a confirmation page. **Do not use GET as a state-changing request**, and do not disable CSRF just to make logout easier to call.

Local logout from A **does not force** the IdP or B to end their sessions. Reopening A immediately after local logout can cause A to redirect to the IdP and automatically sign back in because the IdP cookie is still present. This is not necessarily a logout bug; A may have logged out properly while SSO puts the user into a new A session.

### RP-Initiated Logout at the OP

If the OP supports the OIDC **end_session_endpoint**, the RP can redirect the browser to that endpoint after logout to request ending the IdP session. With Spring Security Servlet, you can replace **the entire** `SecurityConfig` in the example with:

~~~java
package com.example.federation;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.oauth2.client.oidc.web.logout.OidcClientInitiatedLogoutSuccessHandler;
import org.springframework.security.oauth2.client.registration.ClientRegistrationRepository;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class SecurityConfig {
    @Bean
    SecurityFilterChain securityFilterChain(
            HttpSecurity http,
            ClientRegistrationRepository registrations) throws Exception {

        var oidcLogout = new OidcClientInitiatedLogoutSuccessHandler(registrations);
        oidcLogout.setPostLogoutRedirectUri("{baseUrl}/");

        http.authorizeHttpRequests(auth -> auth
                    .requestMatchers("/").permitAll()
                    .anyRequest().authenticated())
            .oauth2Login(Customizer.withDefaults())
            .logout(logout -> logout.logoutSuccessHandler(oidcLogout));
        return http.build();
    }
}
~~~

Use only **one** of the two `SecurityConfig` classes; do not declare the same bean twice. The OP must advertise and support the logout endpoint and accept the appropriate client/redirect URI. This handler coordinates logout at the OP when supported; ending the IdP session **still does not guarantee** that local sessions in all other RPs vanish immediately.

### Single Logout (SLO) Is a Separate Feature

- **Front-channel logout:** notification via browser navigation or iframes between the IdP and RPs; depends on browser behavior, cookies, and each party's implementation.
- **Back-channel logout:** the IdP sends a server-to-server logout message; the RP verifies the message and maps the subject/session identifier to destroy the right local session. Depends on OP, RP, and framework version support.
- **Token revocation:** revoking tokens does not automatically delete every `HttpSession`. An API may reject a token while a UI application still has an active local session.
- **Different devices:** logging out of one browser session does not mean logging out across all devices.

A business requirement to "Log out of all applications immediately" must specify which systems participate, acceptable latency, and how sessions are synchronized/destroyed; **`oauth2Login()` alone does not satisfy that requirement**.

## 6. Security and Operational Points

**Session lifetimes:** design separate idle timeouts and absolute lifetimes for apps and the IdP. A long app session can preserve access after the IdP expires; a short app session paired with a long IdP session often causes fast login redirects that create new local sessions.

**Cookies and HTTPS:** scope Domain/Path properly, set **Secure** when using HTTPS, **HttpOnly**, and **SameSite** appropriate to the flow. The IdP controls the IdP cookie; applications neither read nor directly share that cookie. Behind a reverse proxy, forwarded headers, scheme/host, and cookies must be accurate so redirect URIs/callbacks stay reliable. Do not log session IDs, authorization codes, or tokens.

**OIDC verification:** enforce `state`, `nonce`, ID token, issuer, audience, redirect URI, and PKCE per protocol/configuration. Never skip signature verification or trust browser-supplied data. Restrict redirect URIs at the IdP to an allow-list.

**CSRF:** apps relying on local cookies still need CSRF protection for state-changing actions. OIDC login has its own `state` mechanism, which does not replace CSRF protection for internal forms/actions.

**Authorization:** SSO only resolves user authentication. A and B must still check authorization separately for URLs/actions and not treat a granted scope/claim as unconditional access.

**MFA/step-up:** the IdP can force MFA or re-authentication via `prompt`/`max_age`/`acr`/`auth_time` when business rules require it. A user holding a local session does not prove they recently re-authenticated strongly enough for high-risk actions.

**Permission changes / account locking:** `Authentication` or roles/claims in a local session can become stale after the IdP changes account status. Consider session lifetimes, per-request permission lookups, session revocation, or SLO depending on security requirements.

**Server clusters:** when managing local sessions on the server, multiple instances must share access to session data or use appropriate routing. Do not blame the IdP when A loses a session between two requests due to load balancer/session store issues.

## 7. Verification Scenario with A, B, and a Browser

Register two OIDC clients A and B sharing one IdP, each with its own redirect URI; open DevTools to inspect Network and cookies per origin.

1. **Fresh browser profile:** visit A. Observe the redirect through the IdP, enter credentials, and see the browser receive A's local cookie after the callback.
2. **Open B in the same profile:** B still redirects to the IdP. If the IdP cookie applies, the user does not re-enter a password; the browser receives a local cookie for B distinct from A.
3. **Expire A's session while keeping the IdP session:** access A again; observe a redirect round-trip and a new A session, usually without re-entering a password.
4. **Log out of A locally:** send `POST /logout` with a valid CSRF token; B usually remains logged in. If revisiting A immediately signs back in, check whether the IdP session is still alive.
5. **Log out of the IdP:** verify whether a new flow to the IdP prompts for a password again. At the same time observe A with its active local session: A may keep working if no SLO mechanism is configured.
6. **Incognito profile:** normally lacks the previous profile's IdP cookie; do not assume users get SSO across profiles or devices.
7. **Updated auth policy:** test `prompt=login`/`max_age` or IdP MFA requirements to see why an "already SSO" user can still be prompted to re-authenticate.

Inspect **Network** for authorization redirects/callbacks/status codes and **Application/Storage → Cookies** for each domain. Never share cookie values, tokens, codes, or client secrets in logs, screenshots, or tickets.

### Troubleshooting Scenarios

| Symptom | What to Check |
| --- | --- |
| Logged out of A then revisited A and signed right back in without password | Did A destroy the local session? Is the IdP cookie still alive? Was RP-initiated logout actually used? |
| Logged in to A, yet B still asks for password | Do A and B share the same IdP/tenant? Is the IdP session alive? Are there different `prompt`/`max_age`/MFA/consent rules, browser profiles, or cookie policies? |
| Logged out of IdP, yet A still works | A's local session is independent; have SLO/back-channel logout and session mapping been implemented? |
| Redirect loop or state mismatch | Was A's cookie lost between redirect and callback? Are HTTPS, `SameSite`, reverse proxy, load balancer, redirect URI, and clocks correct? |
| Invalid issuer, audience, or `redirect_uri` | Do discovery issuer, client registration, and actual redirect URI match exactly? |
| API still accepts Bearer token after browser logout | Is the token still unexpired? Does the API check revocation/introspection or only signature + `exp`? Does browser logout cover API tokens? |

## 8. Self-Check Questions

**1. A still has a local session, while the IdP session expired. Does A immediately reject the user?**  
Not by default. A may continue accepting the local session until it expires/is invalidated or additional checks run.

**2. B does not know A's JSESSIONID, so why does the user not re-enter a password at B?**  
B asks the IdP to authenticate via a new flow. At the IdP domain, the browser sends the IdP session cookie, allowing the IdP to recognize the prior sign-in if policy permits.

**3. When POST /logout at A succeeds, does B log out too?**  
Usually no. Local logout, IdP session logout, and multi-RP Single Logout are operations with different scopes.

**4. Is sharing an access token across applications considered SSO?**  
No. Access tokens have specific audiences/scopes/purposes; OIDC SSO is the experience provided by re-authenticating through the IdP and the IdP session.

## 9. Key Takeaways

- **A single user can have multiple independent application sessions and one IdP session assisting sign-in for each application.**
- **SSO is the experience of avoiding credential re-entry when the IdP permits, not sharing JSESSIONID.**
- **Application session expiration, IdP session expiration, and token expiration are three separate events.**
- **Local logout, RP-initiated logout, and Single Logout must be chosen, configured, and tested according to the desired scope.**
- Spring Security provides **`oauth2Login()`**, while the application remains responsible for sessions, authorization, CSRF, cookies, logout, and access permissions.
