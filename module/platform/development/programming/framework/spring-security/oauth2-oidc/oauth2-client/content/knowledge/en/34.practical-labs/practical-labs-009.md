# 34.9. OIDC Logout and Revoking Authorized Client Data

## 1. Practice Problem

A Spring Boot application acts as an **OAuth2/OIDC Client**. Users sign in through an OpenID Provider (OP) via Authorization Code Flow; Spring Security maintains the session and stores an <code>OAuth2AuthorizedClient</code> holding access/refresh tokens to call APIs.

The user clicks **Sign out**, and the Portal stops showing their profile. However:

- Clicking sign in again lets the OP log the user right back in without asking for a password.
- The JDBC token store still retains the user's <code>OAuth2AuthorizedClient</code>.
- A scheduled job can still load the refresh token and call APIs.
- Deleting the local authorized client still leaves the refresh token accepted by the OP.
- The user holds two provider registrations; logout cleans up only one record.
- `oidcLogin()` tests pass green yet never exercise real logout flows.

This is not necessarily a single bug. **Local logout**, **OP SSO logout**, **authorized-client storage cleanup**, and **token revocation** each have distinct meanings and scopes.

> **Goal:** Build Servlet logout with CSRF protection, authorized-client cleanup scoped to the right principal, optional RP-Initiated Logout at the OP, and sufficient tests to prove each layer of behavior. Never use production accounts or tokens for practice.

## 2. Target Outcomes

After this lab, you will be able to:

1. Distinguish <code>SecurityContext</code>, HTTP sessions, OP SSO sessions, <code>OAuth2AuthorizedClient</code>, and authorization grants.
2. Use Spring Security's `LogoutFilter` to handle `POST /logout` with CSRF.
3. Configure <code>OidcClientInitiatedLogoutSuccessHandler</code> when the OP supports RP-Initiated Logout.
4. Remove authorized clients via <code>OAuth2AuthorizedClientService</code> using trusted registration IDs and principal names.
5. Determine when data resides in an HTTP-session-backed <code>OAuth2AuthorizedClientRepository</code> vs. a service store.
6. Distinguish local removal from **OAuth2 Token Revocation (RFC 7009)**.
7. Manage <code>post_logout_redirect_uri</code>, OIDC <code>id_token_hint</code>, and OP logout metadata.
8. Test multiple registrations, user switching, cluster sessions, and refresh-token rotation.
9. Write unit, MockMvc, and integration tests along with a troubleshooting checklist.
10. Choose failure policies, telemetry, and credential-protection controls.

## 3. Technology and Scope

Examples target **Java 17, Spring Boot 3.x, Spring Security 6.x, Spring MVC/Servlet**. For Spring Security 7.x or other OPs, check the exact version's APIs because logout configuration and test support may differ.

| Component | Role |
|---|---|
| Spring Boot Web | HTTP endpoints / sessions |
| Spring Security OAuth2 Client | OIDC Login, authorized-client management |
| Test OpenID Provider | Authorization Code and OP SSO logout |
| OAuth2AuthorizedClientService | Store keyed by registration ID + principal name |
| OAuth2AuthorizedClientRepository | Store/delegation per Servlet request |
| MockMvc + Spring Security Test | Tests CSRF/session/logout/redirects |
| Browser tests | Verifies OP SSO cookies and callback redirects |
| JDBC/Redis test store | Verifies persistence and clustering |

In this lab, the login registration is <code>company</code>. An optional second registration named <code>partner</code> helps test multi-integration cleanup.

## 4. Five State Layers of a Login

| Artifact | Storage Location | Cleaned Up by Local Logout by Default? |
|---|---|---|
| <code>SecurityContext</code> | Request/session repository | Usually yes |
| Portal HTTP session | Servlet container / Spring Session | Usually invalidated |
| <code>OAuth2AuthorizedClient</code> | Session, memory service, JDBC, Redis, custom | **Depends on storage and cleanup** |
| OP SSO session | Cookie/session at OP | **No** |
| OP grant / token validity | Authorization Server | **No** |

### 4.1. `SecurityContext` and `HttpSession`

After OIDC Login:

~~~text
Authentication: OAuth2AuthenticationToken
Principal:      OidcUser
Registration:   company
Session:        authenticated browser session
~~~

Spring Security local logout invalidates the HTTP session, clears <code>SecurityContext</code>, and redirects to the post-logout page. This stops the browser from accessing protected routes with the old session.

### 4.2. Authorized Client Is a Separate Credential Store

<code>OAuth2AuthorizedClient</code> binds:

~~~text
ClientRegistration
Principal name
OAuth2AccessToken
OAuth2RefreshToken (optional)
~~~

If the store is JDBC or Redis, invalidating the HTTP session does not automatically delete that record. Background jobs can still load the token without an explicit cleanup policy.

### 4.3. OP SSO Session Does Not Belong to the Portal

~~~text
portal.example.org  → browser cookie managed by Portal
sso.example.org     → SSO cookie managed by OP
~~~

Clearing the Portal session does not delete cookies on the OP domain. Thus subsequent logins may succeed without re-entering a password.

### 4.4. Issued Tokens Do Not Self-Invalidate

A JWT access token can remain accepted by Resource Servers until its <code>exp</code> time or until a revocation/denylist mechanism takes effect. Deleting the local token store **does not notify** Resource Servers to reject already-issued tokens.

### 4.5. Local Token Removal Differs from Remote Revocation

~~~text
removeAuthorizedClient(...)
    → deletes the record held by the Portal

POST revocation_endpoint token=... (if supported by OP)
    → asks OP to revoke token/grant per RFC 7009 and policy
~~~

Never combine both operations into a false claim of "completely revoked".

## 5. Multi-Layer Logout Flow Diagram

~~~mermaid
sequenceDiagram
    autonumber
    actor U as User
    participant B as Browser
    participant RP as Portal /logout
    participant Store as AuthorizedClientService
    participant OP as OpenID Provider
    U->>B: Click Sign out
    B->>RP: POST /logout + CSRF + session cookie
    RP->>RP: Identify authenticated principal
    RP->>Store: Clean up authorized-client records per policy
    Store-->>RP: Local cleanup result
    RP->>RP: Clear SecurityContext / invalidate session
    RP-->>B: Redirect to OP end_session_endpoint
    B->>OP: RP-Initiated Logout request
    OP->>OP: Terminate OP SSO session per policy
    OP-->>B: Redirect to post_logout_redirect_uri
    B->>RP: GET /logged-out
    RP-->>B: Public logged-out page
~~~

**Ordering note:** Spring Security's `LogoutFilter` invokes <code>LogoutHandler</code>s and then <code>LogoutSuccessHandler</code>. Ordering between built-in and custom handlers affects operations that depend on the session. This lab cleans up the **service-backed store** using the <code>Authentication</code> passed to the handler, without relying on the session remaining alive after invalidation.

### 5.1. Another Layer: Token Revocation

If revoking the refresh token at the OP is required:

~~~text
Load current authorized client
→ optional server-to-server RFC 7009 revocation
→ remove local record
→ local logout
→ optional RP-Initiated Logout
~~~

Ordering, timeouts, retries, and failure policies must be designed per product; there is no automatic distributed atomic transaction.

## 6. Lab Setup

### 6.1. Dependencies

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-security'
    implementation 'org.springframework.boot:spring-boot-starter-oauth2-client'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-test'
}
~~~

When switching to JDBC storage, add Spring JDBC and the matching database driver. When using Redis/Spring Session, add project-managed dependencies. Do not add a database solely to run cleanup unit tests.

### 6.2. `application.yml`

~~~yaml
spring:
  security:
    oauth2:
      client:
        registration:
          company:
            provider: company
            client-id: portal-it
            client-secret: ${TEST_OIDC_CLIENT_SECRET}
            client-authentication-method: client_secret_basic
            authorization-grant-type: authorization_code
            redirect-uri: "{baseUrl}/login/oauth2/code/{registrationId}"
            scope: [openid, profile, email]
        provider:
          company:
            issuer-uri: https://sso.test.example/realms/company
~~~

This is an example for a **test OP**, not a live pre-existing issuer or client. You need a test OP, test account, exact registered callback URLs, and appropriate HTTPS/trust setup. Client secrets come from a test secret store; never use production secrets.

### 6.3. Login Callback

If the Portal's public URL is:

~~~text
https://portal.test.example
~~~

the OP must register:

~~~text
https://portal.test.example/login/oauth2/code/company
~~~

### 6.4. Post-Logout Redirect

A public landing page:

~~~text
https://portal.test.example/logged-out
~~~

may need to be allowlisted at the OP **separately from the login callback**. Never use arbitrary browser parameters to construct <code>post_logout_redirect_uri</code>.

## 7. OIDC RP-Initiated Logout

If supported by the OP, OIDC Discovery metadata may contain:

~~~json
{
  "issuer": "https://sso.test.example/realms/company",
  "end_session_endpoint": "https://sso.test.example/realms/company/protocol/openid-connect/logout"
}
~~~

This is illustrative JSON; the actual path depends on the provider. Never guess <code>end_session_endpoint</code> or confuse it with the Token Revocation Endpoint.

### 7.1. Common Parameters

~~~text
id_token_hint
post_logout_redirect_uri
state (logout state, if used)
client_id (per OP/profile)
~~~

<code>id_token_hint</code> is an ID Token that can contain PII and authentication metadata. Never log the full browser redirect URL to the OP when it includes <code>id_token_hint</code>. Whether the OP terminates its session, prompts for account selection, or redirects after logout depends on provider policy.

### 7.2. Login Callback Differs from Logout Endpoint

~~~text
Authorization initiation: /oauth2/authorization/company
Login callback:            /login/oauth2/code/company
Portal logout action:      POST /logout
OP logout:                 end_session_endpoint
Portal landing page:       /logged-out
~~~

Never configure the same route to serve all of these roles.

### 7.3. Spring Security Handler

In the Servlet stack:

~~~java
org.springframework.security.oauth2.client.oidc.web.logout
    .OidcClientInitiatedLogoutSuccessHandler
~~~

The handler uses <code>ClientRegistrationRepository</code>, OP metadata, and the `Authentication` holding an <code>OidcUser</code> to construct the redirect to the OP when applicable.

### 7.4. OP Logout and Local Logout Are Not Coupled Atomically

If the browser does not follow the redirect, the OP is unreachable, or the OP lacks an end-session endpoint, **local logout may have completed** while the OP SSO session remains active. Tests and telemetry must track these two outcomes separately.

## 8. CSRF and `LogoutFilter`

With browser sessions, logout is a security-state-changing action. Use **POST with CSRF protection**:

~~~text
POST /logout
Cookie: session...
CSRF: token per active repository
~~~

### 8.1. Form

~~~html
<form th:action="@{/logout}" method="post">
  <input type="hidden"
         th:name="${_csrf.parameterName}"
         th:value="${_csrf.token}">
  <button type="submit">Sign out</button>
</form>
~~~

Spring MVC/Thymeleaf may auto-inject the CSRF hidden input via `RequestDataValueProcessor`; the snippet shows how to render the token explicitly from the template. Never hardcode tokens and never disable CSRF app-wide just to make `POST /logout` return 200/302.

### 8.2. Why Not Use `GET /logout`?

A side-effecting GET link:

~~~text
https://portal.example.org/logout?user=alice
~~~

can be triggered by crawlers or third-party pages. Never read <code>user=alice</code> from a query parameter to delete authorized clients; always use the server-side authenticated principal.

### 8.3. What Does Local Logout Typically Do?

Spring Security can:

- Invalidate the HTTP session.
- Clear `SecurityContext`/`Authentication`.
- Run custom logout handlers.
- Finish with the logout success handler.

It **does not by default** call an RFC 7009 revocation endpoint or wipe all JDBC authorized-client records.

## 9. `OAuth2AuthorizedClientService`: The Key Interface

~~~java
org.springframework.security.oauth2.client.OAuth2AuthorizedClientService
~~~

Signatures:

~~~java
OAuth2AuthorizedClient loadAuthorizedClient(
    String clientRegistrationId, String principalName);

void saveAuthorizedClient(
    OAuth2AuthorizedClient authorizedClient,
    Authentication principal);

void removeAuthorizedClient(
    String clientRegistrationId, String principalName);
~~~

### 9.1. Where Does `principalName` Come From?

With OIDC Login:

~~~java
OAuth2AuthenticationToken oauth = ...;
String registrationId = oauth.getAuthorizedClientRegistrationId();
String principalName = oauth.getName();
~~~

<code>getName()</code> must match the exact key used by the authorized-client service when saving. It may be the OIDC subject or an application-configured name attribute—**never assume it is email**.

### 9.2. Deleting the Local Record

~~~java
service.removeAuthorizedClient("company", principalName);
~~~

This deletes the entry from the service implementation. It does not automatically revoke access/refresh tokens at the Authorization Server.

### 9.3. `OAuth2AuthorizedClientRepository` vs. Service

The repository API is bound to Servlet requests:

~~~java
OAuth2AuthorizedClient loadAuthorizedClient(
    String registrationId,
    Authentication authentication,
    HttpServletRequest request);

void removeAuthorizedClient(
    String registrationId,
    Authentication authentication,
    HttpServletRequest request,
    HttpServletResponse response);
~~~

A repository may store data in the session or delegate to a service. If data lives solely in the session, session invalidation removes it. If data lives in JDBC or a separate service, invalidating the session is not enough.

### 9.4. Source of Truth

Example architecture:

~~~text
AuthenticatedPrincipalOAuth2AuthorizedClientRepository
      |
      v
OAuth2AuthorizedClientService
      |
      v
JDBC or InMemory store
~~~

Before writing logout cleanup, identify which store your application uses to **save, load, and refresh** authorized clients. Do not assume Spring Security uses JDBC by default unless you configured the service bean.

## 10. `LogoutHandler` Removing Authorized Clients by Principal

We build a <code>LogoutHandler</code> that cleans up service-backed data for the **authenticated** principal across server-configured registration IDs.

~~~java
package example.security;

import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;
import java.util.List;
import java.util.Objects;

import org.springframework.security.core.Authentication;
import org.springframework.security.oauth2.client.OAuth2AuthorizedClientService;
import org.springframework.security.oauth2.client.authentication.OAuth2AuthenticationToken;
import org.springframework.security.web.authentication.logout.LogoutHandler;

public final class AuthorizedClientCleanupLogoutHandler
        implements LogoutHandler {

    private final OAuth2AuthorizedClientService service;
    private final List<String> registrationIds;

    public AuthorizedClientCleanupLogoutHandler(
            OAuth2AuthorizedClientService service,
            List<String> registrationIds) {
        this.service = Objects.requireNonNull(service);
        this.registrationIds = List.copyOf(registrationIds);
    }

    @Override
    public void logout(
            HttpServletRequest request,
            HttpServletResponse response,
            Authentication authentication) {

        if (!(authentication instanceof OAuth2AuthenticationToken oauth)) {
            return;
        }

        // Identity taken from verified Authentication.
        String principalName = oauth.getName();

        for (String registrationId : registrationIds) {
            service.removeAuthorizedClient(
                registrationId, principalName);
        }
    }
}
~~~

### 10.1. Why Not Use a Request Parameter?

Wrong:

~~~java
String principalName = request.getParameter("user");
service.removeAuthorizedClient("company", principalName);
~~~

An attacker could pass another username to wipe someone else's credentials. Always take the principal from the verified <code>Authentication</code> and enforce ownership/authorization policies.

### 10.2. Where Does the Registration List Come From?

In this lab:

~~~java
List.of("company", "partner")
~~~

This list belongs to trusted application configuration/registries, never taken directly from <code>?registrationId=...</code>. A user may authorize multiple clients; depending on policy, Portal logout may delete all of them, whereas **disconnecting Partner** removes only the <code>partner</code> registration while keeping the Portal session active.

### 10.3. Removing Only the Active Registration

If policy cleans up only the login provider:

~~~java
String registrationId =
    oauth.getAuthorizedClientRegistrationId();

service.removeAuthorizedClient(
    registrationId, oauth.getName());
~~~

That is not full cleanup when a user holds multiple authorized clients. Never claim "all connections removed" when deleting only one registration.

### 10.4. Do Not Depend on the Session Staying Alive

Spring Security may already have run <code>SecurityContextLogoutHandler</code> to invalidate the HTTP session before a custom handler runs, depending on handler ordering. This example cleans up **OAuth2AuthorizedClientService** using the passed-in <code>Authentication</code>, without reading the session after invalidation.

With <code>HttpSessionOAuth2AuthorizedClientRepository</code>, session invalidation generally clears session-owned records; if explicit removal or remote revocation needs the session token, enforce handler ordering to **load before invalidating**.

### 10.5. If Storage Cleanup Fails

- Never claim remote tokens were revoked.
- Per security policy, local logout must still terminate the session properly.
- Record cleanup outcome metrics/audits without raw credentials.
- Use a safe retryable cleanup task with TTL and ownership controls if durability is required.
- Never block the browser indefinitely on a JDBC/Redis outage.

Never swallow errors and report "everything revoked". Local logout, local-store cleanup, and OP revocation are distinct outcomes.

## 11. Service-Backed Storage in the Lab

### 11.1. InMemory Service for Demos

~~~java
package example.security;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.oauth2.client.OAuth2AuthorizedClientService;
import org.springframework.security.oauth2.client.InMemoryOAuth2AuthorizedClientService;
import org.springframework.security.oauth2.client.registration.ClientRegistrationRepository;
import org.springframework.security.oauth2.client.web.AuthenticatedPrincipalOAuth2AuthorizedClientRepository;
import org.springframework.security.oauth2.client.web.OAuth2AuthorizedClientRepository;

@Configuration
public class AuthorizedClientStoreConfig {

    @Bean
    OAuth2AuthorizedClientService authorizedClientService(
            ClientRegistrationRepository registrations) {
        return new InMemoryOAuth2AuthorizedClientService(
            registrations);
    }

    @Bean
    OAuth2AuthorizedClientRepository authorizedClientRepository(
            OAuth2AuthorizedClientService service) {
        return new AuthenticatedPrincipalOAuth2AuthorizedClientRepository(
            service);
    }
}
~~~

<code>AuthenticatedPrincipalOAuth2AuthorizedClientRepository</code> delegates to the service for authenticated principals per implementation; unauthenticated principals follow different storage semantics. This is an illustrative lab setup, not a one-size-fits-all production config.

### 11.2. In-Memory Is Not a Shared Cluster Store

~~~text
Pod A memory store != Pod B memory store
~~~

Deleting a token on Pod B does not delete tokens held inside Process A. In multi-instance production, use shared persistence with proper cleanup and concurrency handling.

### 11.3. `JdbcOAuth2AuthorizedClientService`

Replacement bean when using Spring JDBC:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.jdbc.core.JdbcOperations;
import org.springframework.security.oauth2.client.JdbcOAuth2AuthorizedClientService;
import org.springframework.security.oauth2.client.OAuth2AuthorizedClientService;
import org.springframework.security.oauth2.client.registration.ClientRegistrationRepository;

@Bean
OAuth2AuthorizedClientService authorizedClientService(
        JdbcOperations jdbc,
        ClientRegistrationRepository registrations) {
    return new JdbcOAuth2AuthorizedClientService(
        jdbc, registrations);
}
~~~

Do not declare both JDBC and InMemory beans with the same name in one context; pick one implementation or manage qualifiers per architecture. Schema migrations must match your Spring Security version. Token storage needs encryption, restricted DB access, and retention policies.

### 11.4. JDBC Deletion Is Not Revocation

Deleting a database row stops the Portal from loading those credentials again. The OP and Resource Server maintain independent token lifecycles. To revoke remote tokens, use RFC 7009 or a provider-supported mechanism.

## 12. `SecurityFilterChain`: Local Cleanup + OIDC `LogoutSuccessHandler`

~~~java
package example.security;

import java.util.List;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.oauth2.client.OAuth2AuthorizedClientService;
import org.springframework.security.oauth2.client.oidc.web.logout.OidcClientInitiatedLogoutSuccessHandler;
import org.springframework.security.oauth2.client.registration.ClientRegistrationRepository;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.security.web.authentication.logout.LogoutHandler;

@Configuration
public class PortalSecurityConfig {

    @Bean
    LogoutHandler authorizedClientCleanup(
            OAuth2AuthorizedClientService service) {
        return new AuthorizedClientCleanupLogoutHandler(
            service, List.of("company", "partner"));
    }

    @Bean
    SecurityFilterChain portalChain(
            HttpSecurity http,
            ClientRegistrationRepository registrations,
            LogoutHandler authorizedClientCleanup)
            throws Exception {

        var oidcLogout =
            new OidcClientInitiatedLogoutSuccessHandler(
                registrations);

        oidcLogout.setPostLogoutRedirectUri(
            "{baseUrl}/logged-out");

        http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers(
                    "/", "/login", "/logged-out",
                    "/error", "/assets/**").permitAll()
                .anyRequest().authenticated())
            .oauth2Login(Customizer.withDefaults())
            .csrf(Customizer.withDefaults())
            .logout(logout -> logout
                .logoutUrl("/logout")
                .addLogoutHandler(authorizedClientCleanup)
                .logoutSuccessHandler(oidcLogout));

        return http.build();
    }
}
~~~

### 12.1. Two Extension Points, Two Responsibilities

~~~text
LogoutHandler:
    AuthorizedClientCleanupLogoutHandler
    → removes local service-backed data

LogoutSuccessHandler:
    OidcClientInitiatedLogoutSuccessHandler
    → redirects browser to OP end_session_endpoint
~~~

Never use a login `AuthenticationSuccessHandler` as a logout handler. Those operations belong to separate lifecycles.

### 12.2. `POST /logout` Without CSRF Returns HTTP 403

When CSRF is enabled and the request lacks a token, Spring Security blocks it before `LogoutFilter`. That is proper security behavior. In MockMvc, test valid logout with <code>.with(csrf())</code> and add a negative test without CSRF.

### 12.3. When the OP Does Not Support End-Session

If the provider has no <code>end_session_endpoint</code> or the principal is not OIDC, the logout success handler falls back per Spring Security version/configuration. Never interpret a local redirect as "OP SSO terminated".

### 12.4. Multiple `SecurityFilterChain`s

Ensure `POST /logout` is handled by the chain containing the cleanup handler, the OAuth2 Login callback stays on the right chain, and <code>/logged-out</code> is `permitAll`. A misconfigured matcher can return a 302 logout redirect without ever running cleanup.

## 13. Public Logged-Out Page

~~~java
package example.web;

import org.springframework.stereotype.Controller;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.ResponseBody;

@Controller
public class LogoutPageController {

    @GetMapping("/logged-out")
    @ResponseBody
    String loggedOut() {
        return "You have signed out of the Portal.";
    }
}
~~~

This page is public and must not auto-trigger OIDC login, avoiding redirect loops. UX should state "Signed out of Portal" first; claim OP logout succeeded only if the provider flow actually completed and can be verified.

If clicking Login after local logout immediately logs back in via OP SSO, that **does not prove** local logout failed; the OP SSO session may still be active.

## 14. RFC 7009: Token Revocation Is Not OIDC Logout

OAuth2 Token Revocation (RFC 7009) defines an endpoint allowing a Client to ask the Authorization Server to revoke a token. Depending on the provider, discovery metadata may advertise <code>revocation_endpoint</code>.

### 14.1. Illustrative HTTP Request

~~~http
POST /oauth2/revoke HTTP/1.1
Host: sso.test.example
Content-Type: application/x-www-form-urlencoded
Authorization: Basic BASE64_TEST_CLIENT_CREDENTIALS

token=REFRESH_TOKEN_PLACEHOLDER&token_type_hint=refresh_token
~~~

This is only a protocol sample. The actual revocation endpoint, client authentication, and token must come from **trusted OP configuration**; never put production credentials into tutorials, query strings, or logs.

### 14.2. Never Use an Arbitrary Revocation URL

Wrong:

~~~text
POST /disconnect?revokeUrl=https://attacker.example
~~~

and POSTing the refresh token to a browser-supplied URL. That creates **SSRF and credential exfiltration** vulnerabilities. The revocation URL must come from allowlisted provider metadata/config, never untrusted requests.

### 14.3. Client Authentication

A Confidential Client authenticates at the revocation endpoint using the method permitted by the OP (such as `client_secret_basic` or `private_key_jwt`). Never hardcode `Authorization: Basic` for all OPs when a client uses a different authentication method.

### 14.4. `token_type_hint`

Common values:

~~~text
refresh_token
access_token
~~~

<code>token_type_hint</code> is a processing hint for the server, not a restriction forcing the OP to check only that token type.

### 14.5. HTTP 200 Does Not Prove "The Token Existed"

Per RFC 7009, a revocation endpoint may return success even if the token does not exist or is already invalid, preventing token-probing attacks.

Likewise, HTTP 200 does not guarantee that every Resource Server immediately rejects self-contained access tokens previously issued by the OP.

### 14.6. Refresh vs. Access Token Revocation

A refresh token can still mint new access tokens even after old access tokens expire. For logout/consent revocation policies, handle the **refresh token or authorization grant** first. Some OPs also revoke associated access tokens or the whole grant, though there is no universal default guarantee of "every token on every device invalidated instantaneously".

### 14.7. JWT Resource Servers May Still Accept Old Tokens

~~~text
Access token issued at 10:00
Token expires at 10:15
Portal logout at 10:02
~~~

If a Resource Server only verifies signature and expiry on a self-contained JWT, it can continue accepting the old token until 10:15 even after the Portal deletes its local record. Immediate global invalidation requires OP revocation awareness, introspection/denylists/session versioning, or short token lifetimes.

## 15. Ordering Token Revocation and Local Storage Removal

If remote revocation needs the refresh token, read the token **before** deleting the local copy.

### 15.1. Reference Workflow

~~~text
1. Identify verified principal + allowed registration IDs.
2. Load OAuth2AuthorizedClient from trusted token store.
3. If OP supports RFC 7009, call revocation endpoint with bounded timeout.
4. Record normalized remote revocation outcome.
5. Delete local authorized-client record.
6. Terminate SecurityContext and HTTP session.
7. Optionally redirect browser to OP end_session_endpoint per policy.
~~~

This is an **application workflow to design**, not a single built-in Spring Security class running the whole sequence.

### 15.2. Risks of Remote Revocation Inside `LogoutHandler`

<code>LogoutHandler</code> executes synchronously during the logout HTTP request. Calling the OP with unbounded waits can hang user requests during OP outages.

Options:

- Set strict connect and read timeouts.
- Bound retries; never retry one token forever.
- Ensure local logout completes per security policy even if the OP is unreachable.
- If guaranteed remote revocation is mandatory, enqueue a secure retryable task with expiry, visibility, and ownership controls.
- Report accurate status without claiming all steps succeeded without evidence.

### 15.3. If You Remove Locally Before Revoking

~~~text
service.removeAuthorizedClient(...)
→ no refresh token left to send for revocation
~~~

When reliable remote revocation is required, capture the needed token first and keep it minimally in memory or in a protected encrypted retry task. Never write raw tokens to logs, unencrypted queues, or bug-report attachments.

### 15.4. Remote Timeouts Mean Uncertain Outcomes

The OP may have processed the revocation request even if the response was lost. Retries may be permitted per RFC 7009 semantics, subject to rate limits, bounded backoff, and provider contracts. Never perform refresh-grant retries while executing revocation.

## 16. Logging Out One Provider or All Providers?

Suppose a user signed into Company and connected Partner API:

~~~text
company  | principal-123 | access A1 | refresh R1
partner  | principal-123 | access A2 | refresh R2
analytics| principal-123 | access A3 | refresh R3
~~~

### 16.1. Full Portal Logout

Under a policy of "Sign out of Portal and remove all Portal-held connections":

~~~text
remove company / principal-123
remove partner / principal-123
remove analytics / principal-123
invalidate Portal session
initiate OP logout if supported
~~~

Do not overlook registrations the user previously authorized if policy requires full cleanup. The <code>OAuth2AuthorizedClientService</code> interface has no standard method to list all registrations for a principal; maintain a trusted registry or custom lookup if registrations are dynamic.

### 16.2. Disconnecting Partner

While the user stays authenticated via Company, "Disconnect Partner" should:

~~~text
remove/revoke partner authorized client
keep Company login session
keep unrelated registrations unless policy says otherwise
~~~

This is an **account management operation**, not a full logout; use POST with CSRF, ownership checks, and a dedicated handler/service.

### 16.3. Same Email Does Not Prove Same Identity

Two issuers may issue tokens for the same email or even the same <code>sub</code> string. In custom storage, scope identity keys with issuer/provider/tenant context:

~~~text
(issuer, subject, registrationId)
~~~

In the default service API, keys use <code>registrationId</code> + <code>principalName</code>. If custom principal name mapping collides, tokens risk cross-user/tenant reuse or accidental deletion.

## 17. Single-Device vs. Multi-Device Logout

<code>OAuth2AuthorizedClientService</code> is typically keyed by:

~~~text
registrationId + principalName
~~~

Multiple browser sessions for the same user can share a single authorized-client record under that storage model.

| User Intent | Required Action |
|---|---|
| Log out Browser A | Invalidate Session A |
| Remove Portal-stored user credentials | Remove service-backed authorized clients |
| Disconnect one API provider | Remove/revoke that registration |
| End OP SSO on current browser | RP-Initiated Logout |
| Log out all devices | Global session registry / OP sessions / grant policy |

### 17.1. Shared Records Affect Remaining Devices

If A and B share <code>company/principal-123</code>, logging out on A and removing the record leaves B with an active session `Authentication` but no token to call downstream APIs. That is a **policy decision** to test intentionally, not always a bug.

### 17.2. What If Tokens Should Be Stored Per-Device?

You need a custom token store key/model bound to device/session, along with a consistent authorized-client manager/repository and cleanup ownership logic. Never swap <code>principalName</code> to a session ID when saving while still loading by subject elsewhere.

### 17.3. "Log Out All Devices" Requires Multiple Systems Coordinating

You cannot infer from a single <code>removeAuthorizedClient</code> call that all device sessions terminated. Account for the Portal's session registry, OP SSO/session management, refresh grants, and active JWT access tokens on Resource Servers.

## 18. Session-Backed `OAuth2AuthorizedClientRepository`

When an app uses <code>HttpSessionOAuth2AuthorizedClientRepository</code>, authorized-client data resides in the HTTP session and disappears when the session is invalidated.

### 18.1. Clearing the Session Cookie Differs from Invalidating the Server Session

Simply returning:

~~~http
Set-Cookie: JSESSIONID=; Max-Age=0
~~~

does not prove the server-side session was invalidated and resources cleaned up. Use Spring Security's logout infrastructure and verify server state.

### 18.2. Never Load Session Tokens After Invalidation

~~~text
SecurityContextLogoutHandler invalidates HttpSession
    ↓
Session-backed authorized client no longer available
    ↓
Custom handler tries repository.loadAuthorizedClient(...)
    ↓
May return null because prior session is gone
~~~

If remote revocation is required for a session-backed token, design an ordered capture/revoke step before session invalidation. Cleaning up service-backed tokens after default logout is a different case.

### 18.3. Manually Invalidating the Session in a Controller Skips Security Hooks

Do not replace `LogoutFilter` with:

~~~java
request.getSession().invalidate();
return "redirect:/logged-out";
~~~

because it can bypass CSRF checks, `SecurityContext` cleanup, custom token cleanup, and RP-Initiated Logout.

## 19. Logout vs. Refresh Token Rotation Races

Suppose two Portal nodes share access to persisted authorized clients:

~~~mermaid
sequenceDiagram
    autonumber
    participant A as Node A /logout
    participant B as Node B background refresh
    participant DB as Shared token store
    participant OP as OP Token Endpoint
    A->>DB: Read A0/R0
    B->>DB: Read A0/R0
    B->>OP: Refresh R0
    OP-->>B: Access A1, refresh R1
    A->>DB: Delete authorized client for logout
    B->>DB: Save A1/R1 after deletion?
    Note over DB: Risk of token resurrection after logout
~~~

### 19.1. Is Deleting the Token Once Enough?

Not necessarily. If a background job holds stale state and writes a new token after logout completes, the record can **resurrect** even though initial logout cleanup succeeded.

### 19.2. Designing Against Token Resurrection

Architectural safeguards depending on requirements:

1. Mark the grant/user authorization revoked using a **generation/version/tombstone** with TTL or retention policy.
2. Stop/suspend background jobs using that grant.
3. Re-check grant status right before saving a refreshed token.
4. Use atomic conditional updates / compare-and-set.
5. Coordinate per-key refreshes and logouts.
6. Remotely revoke the refresh token/grant if supported by the provider.
7. Invalidate caches by version and never repopulate records from stale caches.

This is a concurrency problem **not solved automatically by Spring Security** simply by registering a logout handler.

### 19.3. Tombstones Need a Lifecycle

Do not retain token-revocation tombstones indefinitely without a retention/expiry policy. Conversely, purging tombstones too early lets slow jobs recreate the record. Balance maximum job duration, queue retries, and authorization lifetimes.

### 19.4. DB and OP Operations Are Not Atomically Transactional

Deleting a JDBC row and calling OP revocation involve two separate systems. There is no built-in distributed transaction:

~~~text
DB delete succeeds, OP revoke fails
OP revoke succeeds, DB delete fails
Network timeout, outcome unknown
~~~

Design idempotent cleanup, bounded retries, and observable partial failures.

## 20. OP-Initiated OIDC Logout and Back-Channel Logout

In addition to Portal-initiated logout, the OP can initiate logout toward Relying Parties.

### 20.1. RP-Initiated Logout

~~~text
Portal browser user → OP end_session_endpoint
~~~

Configured via <code>OidcClientInitiatedLogoutSuccessHandler</code>.

### 20.2. Front-Channel Logout

The OP notifies the RP via browser navigation/iframe per specification. Browser cookie policies, third-party cookie restrictions, and session mappings can affect reliability.

### 20.3. Back-Channel Logout

The OP posts a **signed Logout Token** to the RP's back-channel endpoint; the RP must verify issuer, audience, signature, event markers, <code>sid</code>/<code>sub</code>, and other requirements per the OIDC Back-Channel Logout spec.

Spring Security supports OIDC back-channel logout in compatible versions; check your version's reference for DSL/configuration and session registry integration. Never assume configuring RP-Initiated Logout automatically enables back-channel logout.

### 20.4. Does Receiving OP Logout Clean `OAuth2AuthorizedClientService`?

Depends on application wiring and mapping. An OP logout notification that terminates Portal sessions may **not** delete persistent tokens unless the application connects lifecycle cleanup explicitly.

When needed, tie back-channel logout events to server-side authorized-client cleanup using verified issuer/subject/session mappings. Never take <code>sub</code> from unsigned JSON to delete token records.

### 20.5. Never Accept Forged Logout Requests

An attacker sending:

~~~http
POST /logout/back-channel
Content-Type: application/json

{"sub":"victim"}
~~~

is not a valid OIDC Back-Channel Logout. Verify the signed Logout Token and client/audience/issuer/session bindings per protocol. Never let unverified external callers terminate someone else's session or tokens via an unverified <code>sub</code>.

## 21. Redirects, Cookies, and Deployment Environments

### 21.1. `post_logout_redirect_uri` Must Be Exact

~~~text
local:
  http://localhost:8080/logged-out

staging:
  https://portal.staging.example.org/logged-out

production:
  https://portal.example.org/logged-out
~~~

The OP must allow the URI per environment policy. Avoid sharing the same production client registration across local and staging when separate clients and credentials can be used.

### 21.2. HTTPS Proxies Can Break `{baseUrl}`

If the browser visits:

~~~text
https://portal.example.org
~~~

while Spring Boot sees:

~~~text
http://portal-service:8080
~~~

the logout handler can generate the wrong post-logout redirect URL. Use trusted forwarded headers or explicit external base URL mapping. Edge proxies must strip/overwrite spoofed <code>Forwarded</code>/<code>X-Forwarded-*</code> headers rather than trusting arbitrary browser hostnames.

### 21.3. Cookie Scope of OP vs. Portal

<code>Secure</code>, <code>HttpOnly</code>, <code>SameSite</code>, Domain, and Path on Portal cookies govern only the Portal session. The OP SSO cookie belongs to the OP domain; the browser logout redirect must actually reach the OP if the OP needs to clear its session.

### 21.4. One Public URL Serving Multiple Tenants

If logout expands <code>{baseUrl}</code> while the Portal serves multiple tenants/hostnames, enforce a trusted host allowlist and tenant mapping. Never accept arbitrary <code>post_logout_redirect_uri</code> values from the browser due to open-redirect and cross-tenant risks.

## 22. Unit Testing: Cleaning Up the Right Principal and Registrations

The goal of this unit test is to prove <code>AuthorizedClientCleanupLogoutHandler</code> deletes the right records from <code>OAuth2AuthorizedClientService</code> without needing a test OP.

### 22.1. Creating Two Registrations and Three Authorized Clients

JUnit 5 example:

~~~java
package example.security;

import java.time.Instant;
import java.util.List;
import java.util.Map;

import org.junit.jupiter.api.Test;
import org.springframework.mock.web.MockHttpServletRequest;
import org.springframework.mock.web.MockHttpServletResponse;
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import org.springframework.security.oauth2.client.InMemoryOAuth2AuthorizedClientService;
import org.springframework.security.oauth2.client.OAuth2AuthorizedClient;
import org.springframework.security.oauth2.client.authentication.OAuth2AuthenticationToken;
import org.springframework.security.oauth2.client.registration.ClientRegistration;
import org.springframework.security.oauth2.client.registration.InMemoryClientRegistrationRepository;
import org.springframework.security.oauth2.core.AuthorizationGrantType;
import org.springframework.security.oauth2.core.ClientAuthenticationMethod;
import org.springframework.security.oauth2.core.OAuth2AccessToken;
import org.springframework.security.oauth2.core.OAuth2RefreshToken;
import org.springframework.security.oauth2.core.user.DefaultOAuth2User;

import static org.junit.jupiter.api.Assertions.*;

class AuthorizedClientCleanupLogoutHandlerTest {

    private ClientRegistration registration(String id) {
        return ClientRegistration.withRegistrationId(id)
            .clientId("portal-test-" + id)
            .clientSecret("test-only")
            .clientAuthenticationMethod(
                ClientAuthenticationMethod.CLIENT_SECRET_BASIC)
            .authorizationGrantType(
                AuthorizationGrantType.AUTHORIZATION_CODE)
            .redirectUri(
                "{baseUrl}/login/oauth2/code/{registrationId}")
            .authorizationUri("https://op.example.test/authorize")
            .tokenUri("https://op.example.test/token")
            .jwkSetUri("https://op.example.test/jwks")
            .scope("openid")
            .clientName(id)
            .build();
    }

    private OAuth2AuthenticationToken auth(
            String subject,
            String registrationId) {
        var user = new DefaultOAuth2User(
            List.of(new SimpleGrantedAuthority("ROLE_USER")),
            Map.of("sub", subject),
            "sub");
        return new OAuth2AuthenticationToken(
            user, user.getAuthorities(), registrationId);
    }

    private OAuth2AuthorizedClient authorizedClient(
            ClientRegistration registration,
            String subject) {

        Instant now = Instant.parse("2026-11-16T10:00:00Z");

        var access = new OAuth2AccessToken(
            OAuth2AccessToken.TokenType.BEARER,
            "access-" + registration.getRegistrationId()
                + "-" + subject,
            now, now.plusSeconds(600));

        var refresh = new OAuth2RefreshToken(
            "refresh-" + registration.getRegistrationId()
                + "-" + subject,
            now);

        return new OAuth2AuthorizedClient(
            registration, subject, access, refresh);
    }

    @Test
    void removesAliceClientsButPreservesBob() {
        var company = registration("company");
        var partner = registration("partner");

        var registrations =
            new InMemoryClientRegistrationRepository(
                company, partner);
        var service =
            new InMemoryOAuth2AuthorizedClientService(
                registrations);

        var alice = auth("alice", "company");
        var bob = auth("bob", "company");

        service.saveAuthorizedClient(
            authorizedClient(company, "alice"), alice);
        service.saveAuthorizedClient(
            authorizedClient(partner, "alice"), alice);
        service.saveAuthorizedClient(
            authorizedClient(company, "bob"), bob);

        assertNotNull(service.loadAuthorizedClient(
            "company", "alice"));
        assertNotNull(service.loadAuthorizedClient(
            "partner", "alice"));
        assertNotNull(service.loadAuthorizedClient(
            "company", "bob"));

        var handler = new AuthorizedClientCleanupLogoutHandler(
            service, List.of("company", "partner"));

        handler.logout(
            new MockHttpServletRequest(),
            new MockHttpServletResponse(),
            alice);

        assertNull(service.loadAuthorizedClient(
            "company", "alice"));
        assertNull(service.loadAuthorizedClient(
            "partner", "alice"));
        assertNotNull(service.loadAuthorizedClient(
            "company", "bob"));
    }
}
~~~

### 22.2. What Does This Test Prove?

1. Authorized clients are stored by registration ID + principal name.
2. The handler reads the principal from <code>OAuth2AuthenticationToken</code>, not query parameters.
3. Both of Alice's registrations are cleaned up.
4. Bob's record remains untouched.

**It does not prove** that the browser session was invalidated, that the OP SSO session ended, or that refresh tokens were revoked at the OP. Those require separate tests.

### 22.3. Why Use `DefaultOAuth2User` in an OIDC Test?

This test only verifies that the handler accepts <code>OAuth2AuthenticationToken</code> and extracts the principal name; it does not validate OIDC ID Tokens. An <code>OAuth2AuthenticationToken</code> wrapping <code>DefaultOAuth2User</code> is enough to test cleanup logic. To test the OIDC logout success handler, supply an **<code>OidcUser</code> with a valid ID Token** or run full OP integration tests.

### 22.4. Testing Null Authentication

~~~java
@Test
void nullAuthenticationDoesNotDeleteAnyRecord() {
    // Prepare service with Alice's record as in the test above.
    handler.logout(
        new MockHttpServletRequest(),
        new MockHttpServletResponse(),
        null);

    // Assert Alice's record still exists.
}
~~~

This is an **assertion skeleton** requiring initialized <code>handler</code>/<code>service</code> fixtures from the previous test. Also test non-OAuth `Authentication` types to ensure anonymous or local-auth logouts do not trigger unintended deletions.

### 22.5. Testing Nonexistent Registrations

A registration list containing an ID absent from the store might turn removal into a no-op or behave differently in custom implementations. Define clear policies for invalid registration config and test startup/cleanup behavior rather than accepting unvalidated dynamic lists.

## 23. MockMvc: `POST /logout` with CSRF

To test Spring Security's `LogoutFilter`, **keep security filters enabled** in MockMvc.

### 23.1. Integration Test Skeleton

~~~java
package example.security;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.csrf;
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.oidcLogin;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class PortalLogoutMvcIT {

    @Autowired
    MockMvc mockMvc;

    @Test
    void rejectsLogoutWithoutCsrf() throws Exception {
        mockMvc.perform(
                post("/logout").with(oidcLogin()))
            .andExpect(status().isForbidden());
    }

    @Test
    void acceptsLogoutWithCsrf() throws Exception {
        mockMvc.perform(
                post("/logout")
                    .with(oidcLogin())
                    .with(csrf()))
            .andExpect(status().is3xxRedirection());
    }
}
~~~

**This is an integration test skeleton needing a valid Spring context**: `ClientRegistrationRepository`/OP metadata must be supplied via test configuration. <code>oidcLogin()</code> uses a mock test registration that may not match your app's registration; with <code>OidcClientInitiatedLogoutSuccessHandler</code>, redirecting to the OP depends on `ClientRegistration`/Issuer/discovery setup. Never hardcode an OP logout URL expectation here without providing the matching registration and `OidcUser`.

### 23.2. What Does `oidcLogin()` Verify?

In MockMvc:

~~~java
.with(oidcLogin())
~~~

injects an OIDC-style authenticated principal into the request to exercise `LogoutFilter`/CSRF and handler behavior. It **does not run Authorization Code login through an OP**, nor does it prove the OP SSO cookie was cleared.

### 23.3. `@WithMockUser` Is Not Equivalent to OIDC Login

~~~java
@WithMockUser(username = "alice")
~~~

creates a mock authentication that is not an <code>OAuth2AuthenticationToken</code>. Because the handler in Section 10 checks for `OAuth2AuthenticationToken`, a test with <code>@WithMockUser</code> may return a logout redirect without ever executing the authorized-client cleanup path.

### 23.4. Do Not Disable Filters

Avoid:

~~~java
@AutoConfigureMockMvc(addFilters = false)
~~~

for this test. Disabling filters removes the real <code>CsrfFilter</code> and <code>LogoutFilter</code> you are trying to verify.

### 23.5. Verifying Access After Logout

After a real logout, a browser request to a protected route **with no remaining authenticated session** must be challenged for login/authorization.

Do not pass <code>.with(oidcLogin())</code> on the **post-logout request**, which re-injects a mock `Authentication` and invalidates the test:

~~~java
// Wrong way to test that a user is logged out:
mockMvc.perform(get("/private").with(oidcLogin()));
~~~

Instead, track the actual session/cookie lifecycle across the test, or send a genuine anonymous request to verify the protected route is blocked.

## 24. Unit Testing the OIDC `LogoutSuccessHandler`

<code>OidcClientInitiatedLogoutSuccessHandler</code> builds the OP redirect based on the authenticated OIDC principal and provider metadata.

### 24.1. Minimum Required Setup

1. A <code>ClientRegistration</code> for registration <code>company</code>.
2. Provider metadata containing a test <code>end_session_endpoint</code> URL.
3. An <code>OidcUser</code> with a test ID Token and matching issuer/client context.
4. An <code>OAuth2AuthenticationToken</code> wrapping that principal and registration.
5. A <code>MockHttpServletRequest</code> with appropriate public HTTPS origin/forwarded context.
6. A <code>MockHttpServletResponse</code> to inspect <code>Location</code>.

### 24.2. Appropriate Assertions

~~~text
status = 302
Location host = trusted OP host
Location path = OP end_session_endpoint
post_logout_redirect_uri = registered Portal HTTPS URL
id_token_hint present when applicable
~~~

**Never print the full `Location` URL containing an ID Token** into CI logs. For debugging, parse the query parameters and assert only presence, host, and scrubbed targets.

### 24.3. Fallback Branches

Also test:

- Null authentication.
- Principal is not an <code>OidcUser</code>.
- Missing `ClientRegistration`.
- OP does not advertise <code>end_session_endpoint</code>.
- Post-logout URI cannot be built or falls outside the allowlist.

Verify expected fallback behavior against your **exact Spring Security version** rather than assuming it always lands on <code>/logged-out</code> or always calls the OP.

## 25. Browser E2E with a Test OP

To prove the OP SSO session actually ended, a real browser must follow the OP logout redirect.

### 25.1. Baseline Test

~~~text
Given:
    Keycloak/OP test realm available
    Portal registration company configured
    Test user alice.test enabled
    Browser context fresh

When:
    Browser starts /oauth2/authorization/company
    User signs in at OP
    Portal shows authenticated profile
    User POSTs /logout with CSRF
    Browser follows OP end_session_endpoint
    OP returns registered post_logout_redirect_uri

Then:
    Portal no longer has authenticated local session
    Local authorized-client service record is absent
    Browser reaches public logged-out page
    OP SSO behavior matches logout contract
~~~

### 25.2. Why Not Just Check `/logged-out`?

An app could redirect straight to <code>/logged-out</code> without ever contacting the OP. Seeing the post-logout page does not prove the OP SSO cookie was cleared.

### 25.3. Verifying OP SSO Properly

To verify OP logout, test that re-initiating login in the same browser context **does not silently reuse an OP session** when OP logout policy requires termination. Some providers support <code>prompt=none</code> to check whether an active OP session exists; verify conditions and behavior against provider docs.

Never use <code>prompt=login</code> as proof the OP session ended, because that parameter forces a login prompt even when an active session still exists.

### 25.4. Browser Artifacts

Screenshots, HAR files, and traces can capture cookies, authorization codes, <code>state</code>, ID Token hints, and PII. Redact them, restrict retention and access, and never post raw logout `Location` headers in public CI logs.

## 26. Integration Testing Token Revocation

If the OP supports RFC 7009:

1. Log in/authorize a test account and retrieve its authorized client from the test store.
2. Call the trusted revocation endpoint for the refresh token per provider contract.
3. Delete the local token record.
4. Attempt to use the old refresh token in an **isolated test environment**.
5. Verify the OP rejects the token/grant per policy.
6. Verify Resource Server behavior on the old access token per token format and revocation strategy.

### 26.1. Never Test Revocation with Production Tokens

Never copy live tokens from browser DevTools or production databases into Postman. Use dedicated test OPs, test clients, and test users with cleanup lifecycles.

### 26.2. Interpreting Results Accurately

HTTP 200 from the revocation endpoint does not prove the token previously existed. Add token/grant behavioral assertions where observable; never assume a stale self-contained JWT is rejected immediately if the RS only verifies offline.

### 26.3. Fault Injection

Simulate:

~~~text
revocation endpoint HTTP 503
network timeout after OP processes request
unsupported revocation endpoint
invalid_client
storage delete failure
~~~

Define the expected policy for each case: whether local logout still completes, whether a cleanup retry task is scheduled, what the UI displays, and which metrics increment. Never allow infinite retries or raw tokens sitting in queues.

## 27. Integration Testing Logout vs. Refresh Concurrency

With a two-node scenario:

~~~text
Initial DB state: company/alice A0/R0 version=7
Node A: starts logout, intends deletion
Node B: begins refresh R0
OP: issues A1/R1
Node B: attempts save version=8
~~~

### 27.1. Scenarios to Assert

1. If logout commits first, a subsequent refresh save **must not resurrect** the token record against policy.
2. If refresh commits first, logout must observe the new version and clean it up accordingly.
3. Unconditional deletes from one node must never wipe state belonging to another principal.
4. Tokens are encrypted in storage and never leak into logs.
5. Distributed locks, transactions, and versioning have bounded timeouts and failure paths.

### 27.2. `InMemory` Services Are Insufficient for Race Testing

A per-JVM `InMemory` service cannot simulate transactions or locks of a JDBC/Redis cluster. Use a shared test database, fault injection, and concurrency barriers in integration tests.

### 27.3. Idempotency Challenges

If a browser submits `POST /logout` twice, cleanup must remain safe when the record is already gone. When remote revocation is involved, define policies for unknown outcomes and retry limits. Never implement fallback logic that recreates an authorized client just because removal returned null.

## 28. Testing Back-Channel Logout

When the app supports OIDC Back-Channel Logout:

~~~text
OP sends signed Logout Token
    ↓
RP validates signature, iss, aud, events, sid/sub and other claims
    ↓
RP maps to local sessions
    ↓
RP terminates affected local sessions
    ↓
Application optionally cleans related persisted authorized clients
~~~

### 28.1. Critical Negative Tests

- Unsigned Logout Token.
- Signature fails verification against trusted OP keys.
- Wrong issuer.
- Wrong audience.
- Wrong `events` claim.
- Wrong <code>sid/sub</code> mapping.
- Replayed Logout Token per provider/session policy.
- Expired or invalid temporal claims where applicable.

Never accept unsigned JSON like <code>{"sub":"alice"}</code> and delete sessions/tokens. Never disable validation just to simplify generating test Logout Tokens.

### 28.2. Differs from Remote Token Revocation

Back-channel logout is a protocol for the **OP to tell the RP to end sessions**. It is not the same as a Client POSTing a refresh token to an RFC 7009 endpoint. Any extra token cleanup must be designed explicitly into the architecture.

### 28.3. Session Registry in a Cluster

When sessions span multiple nodes, the RP needs a shared session registry/store or distributed mechanism to locate sessions by <code>sid</code>/<code>sub</code>. Terminating only an in-memory session on whichever node received the webhook misses sessions on other nodes.

## 29. Extra Practice: Disconnecting a Provider Without Logging Out of the Portal

In many products, users can **disconnect an API provider** while staying logged into the Portal. This is a different operation from `POST /logout`.

### 29.1. Endpoint with Ownership Checks

~~~java
package example.web;

import java.util.Set;

import org.springframework.http.ResponseEntity;
import org.springframework.http.HttpStatus;
import org.springframework.security.core.Authentication;
import org.springframework.security.oauth2.client.OAuth2AuthorizedClientService;
import org.springframework.security.oauth2.client.authentication.OAuth2AuthenticationToken;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.server.ResponseStatusException;

@RestController
public class DisconnectController {

    private static final Set<String> DISCONNECTABLE =
        Set.of("partner", "analytics");

    private final OAuth2AuthorizedClientService service;

    public DisconnectController(
            OAuth2AuthorizedClientService service) {
        this.service = service;
    }

    @PostMapping("/connections/{registrationId}/disconnect")
    ResponseEntity<Void> disconnect(
            @PathVariable String registrationId,
            Authentication authentication) {

        if (!(authentication instanceof OAuth2AuthenticationToken oauth)) {
            throw new ResponseStatusException(
                HttpStatus.UNAUTHORIZED);
        }

        if (!DISCONNECTABLE.contains(registrationId)) {
            throw new ResponseStatusException(
                HttpStatus.NOT_FOUND);
        }

        // If remote revocation is required, load the token and
        // execute a controlled workflow before local removal.
        service.removeAuthorizedClient(
            registrationId, oauth.getName());

        return ResponseEntity.noContent().build();
    }
}
~~~

**Limitation:** This code performs **local removal only**. If business rules require revoking the grant at the OP, add the revocation workflow from Sections 14–15. Protect this endpoint with CSRF for browser sessions, plus method security/tenant ownership checks in multi-tenant apps or delegated administration.

### 29.2. Why Use an Allowlist?

If a user calls <code>/connections/company/disconnect</code>, do not allow severing the active login identity when the UI only intends to disconnect downstream providers. An explicit allowlist prevents corrupting auth state.

### 29.3. Multiple Providers Sharing an Email

If Partner and Company use separate issuers, enforce connection ownership via trusted principal mappings. Never let a browser-supplied email invoke <code>removeAuthorizedClient</code> on another principal.

### 29.4. Concurrent Background Jobs

Before disconnecting, stop background jobs using that registration or make them check revoked/version status. Otherwise a running job can re-save a record after removal while refreshing with a stale token.

## 30. Troubleshooting by Symptom

| Symptom | Likely Cause | Check / Fix |
|---|---|---|
| `POST /logout` returns 403 | Missing CSRF token | Inspect `CsrfFilter`, form/headers |
| `GET /logout` does not log out | CSRF-enabled logout requires POST; may show confirmation page | Use POST + CSRF |
| Logout returns 302 yet user still accesses private page | Session not cleared or test re-injected mock auth | `SecurityFilterChain`, session cookies, test setup |
| Local logout works, OP auto-logs right back in | OP SSO session still active | RP-Initiated Logout / `end_session_endpoint` |
| No redirect to OP logout | Principal not `OidcUser`, missing OP metadata, handler wiring | `Authentication`/`ClientRegistration`/Discovery |
| OP rejects `post_logout_redirect_uri` | URI not allowlisted / wrong hostname | Exact registered URI, HTTPS, forwarded headers |
| Redirect goes to `http://internal:8080` | Wrong public base URL / proxy metadata | Trusted `Forwarded` headers and ingress |
| `/logged-out` prompts for login | Route not `permitAll` | Authorization rules |
| JDBC still holds refresh token | Logout only invalidated HTTP session | Verify service-backed cleanup |
| Cleanup ran yet record still present | Wrong `principalName`/`registrationId`/store | Compare keys used for save/load/remove |
| Deleting Alice drops Bob's token | Broken user key / tenant isolation | Verified `Authentication` + key design |
| User logs out of Company, Partner token remains | Only removed active registration | Full logout vs. disconnect policy |
| Session cleared before loading token to revoke | Session-backed repo already invalidated | Load/capture before invalidation |
| OP revocation returns HTTP 200 yet JWT still works | Self-contained JWT/RS does not check revocation | Token TTL / RS revocation awareness |
| OP revocation returns 503/timeout | Provider/network outage | Bounded retries and partial outcomes |
| Token reappears after logout | Background refresh saved stale state | Versioning/tombstones/coordination |
| Logout fails only on Node B | Divergent local store/session config | Shared DB/Spring Session/instance diagnostics |
| MockMvc passes yet OP cookie stays | `oidcLogin` mock skips browser OP logout | Browser E2E |
| Back-channel logout misses JDBC tokens | Session cleanup not wired to service store | Verified logout event + cleanup integration |
| Browser switches accounts yet keeps old token | Account switch skipped cleanup/partitioning | Principal keys, cache invalidation |
| Local logout does not delete cookie | Wrong cookie path/domain or custom cookie | Session invalidation, `Set-Cookie`, browser checks |
| Logout loop returning to Portal | `/logged-out` protected or auto-login triggered | Anonymous landing page |
| OP session ends on one device only | OP policy / session-scoped logout | Global logout requirements |

### 30.1. Diagnostic Flowchart

~~~mermaid
flowchart TD
    A["User clicks Logout"] --> B{"POST /logout has CSRF and hits right chain?"}
    B -->|No| C["Fix form, CSRF, matchers, cookies"]
    B -->|Yes| D{"Local session/SecurityContext cleared?"}
    D -->|No| E["LogoutFilter, handlers, session repo"]
    D -->|Yes| F{"Authorized client record still in store?"}
    F -->|Yes| G["Verify storage source of truth, principal key, cleanup"]
    F -->|No| H{"Remote token revocation required?"}
    H -->|Yes| I["RFC7009 endpoint, response, failure/retry policy"]
    H -->|No| J{"OP SSO logout required?"}
    I --> J
    J -->|Yes| K["end_session_endpoint and browser redirects"]
    J -->|No| L["Local logout outcome verified"]
    K --> M["Verify OP SSO behavior and post_logout_redirect_uri"]
~~~

### 30.2. Never Extrapolate from a Single HTTP Status

An HTTP 302 from the Portal may just be a local logout redirect, not proof the OP processed logout. HTTP 200 from RFC 7009 does not prove all access tokens are immediately invalid across Resource Servers. HTTP 204 from a disconnect endpoint only confirms the app ran its local contract.

## 31. Logs, Metrics, and Audits Without Leaking Credentials

### 31.1. Recommended Events

~~~text
event=portal_logout_requested
providerAlias=company
logoutScope=current_session
correlationId=example

event=authorized_client_cleanup
providerAlias=partner
operation=remove
outcome=success
correlationId=example

event=oidc_rp_initiated_logout_redirect
providerAlias=company
outcome=redirect_created
correlationId=example

event=oauth2_revocation_requested
providerAlias=partner
tokenKind=refresh_token
outcome=timeout
correlationId=example
~~~

Never log:

~~~text
access_token
refresh_token
id_token
id_token_hint
client_secret
authorization_code
code_verifier
real state / nonce
session cookie
raw OP error_description
~~~

### 31.2. Suggested Metrics

| Custom Metric | Meaning |
|---|---|
| <code>portal_logout_total{provider,scope,result}</code> | Local logout events |
| <code>authorized_client_cleanup_total{provider,result}</code> | Local removal outcomes |
| <code>oauth2_revocation_total{provider,token_kind,result}</code> | Remote revocation request outcomes |
| <code>oauth2_revocation_latency_seconds{provider}</code> | Latency calling OP |
| <code>oidc_logout_redirect_total{provider,result}</code> | Portal generated OP logout redirect |
| <code>authorized_client_resurrection_detected_total{provider}</code> | Guard caught stale refresh save after logout |
| <code>backchannel_logout_total{provider,result}</code> | Verified OP logout notifications |

These are **proposed custom metric names to instrument**, not metrics emitted automatically by Spring Security.

### 31.3. What Never to Put in Labels

Never use emails, raw subjects, full token hashes, refresh token IDs, session IDs, or correlation IDs as unbounded-cardinality metric labels. Correlation IDs belong in restricted logs/traces under retention and access policies.

### 31.4. Redirect-to-OP Does Not Prove OP Completion

The metric <code>oidc_logout_redirect_total</code> only shows the Portal issued a redirect. Never name it <code>op_logout_success_total</code> without a trustworthy signal/contract from the OP confirming session termination.

## 32. Test Matrix for This Lab

| ID | Scenario | Test Type | Expected Outcome |
|---|---|---|---|
| LOG-01 | Logout without CSRF | MockMvc | HTTP 403 |
| LOG-02 | Logout with CSRF | MockMvc | `LogoutFilter` runs |
| LOG-03 | Anonymous logout | MockMvc/unit | Deletes no user's tokens |
| LOG-04 | OAuth2 user Alice logout | Unit | Deletes Alice/company |
| LOG-05 | Alice has Company + Partner | Unit | Deletes per policy |
| LOG-06 | Bob also has authorized client | Unit | Preserves Bob |
| LOG-07 | Unknown registration | Unit | No-op/handled per policy |
| LOG-08 | Service store unavailable | Fault injection | Local logout + cleanup failure handling |
| LOG-09 | HTTP session-backed tokens | Integration | Session invalidation semantics |
| LOG-10 | JDBC persistent authorized clients | Integration | Record removed |
| LOG-11 | OP lacks `end_session_endpoint` | Integration | Proper fallback |
| LOG-12 | OP supports RP-Initiated Logout | Browser E2E | Browser completes OP logout |
| LOG-13 | Wrong `post_logout_redirect_uri` | OP integration | Rejected by OP |
| LOG-14 | Local logout with OP SSO cookie intact | Browser E2E | Re-login may auto-SSO |
| LOG-15 | OP logout succeeds | Browser E2E | Session behaves per OP |
| LOG-16 | RFC 7009 refresh-token revocation | OP integration | Remote revocation policy |
| LOG-17 | Revocation endpoint unknown token | Protocol test | Never infers token existed |
| LOG-18 | Revocation HTTP 503 | Fault injection | Bounded failure/retry |
| LOG-19 | Revocation timeout unknown outcome | Fault injection | Never reports false success |
| LOG-20 | Access JWT valid after local deletion | Resource Server | Per token acceptance policy |
| LOG-21 | Logout concurrent with refresh | Multi-node | No token resurrection |
| LOG-22 | Two devices, same principal | Integration | Proper logout scoping |
| LOG-23 | Account switch Alice → Bob | Integration | Never reuses Alice's tokens |
| LOG-24 | Disconnect Partner | Controller/service | Company session stays logged in |
| LOG-25 | Valid Back-Channel Logout Token | OIDC integration | Correct sessions terminated |
| LOG-26 | Forged Back-Channel Logout Token | OIDC integration | Rejected |
| LOG-27 | Logout on public hostname via proxy | Browser/ingress | Exact HTTPS redirect URI |
| LOG-28 | `/logged-out` anonymous route | MockMvc | No login loop |

These tests cover distinct layers. Never replace a browser OP logout test with <code>oidcLogin()</code>, or use a local removal unit test to claim a JWT access token is globally revoked.

## 33. Step-by-Step Practice Checklist

### Phase A — Environment

1. Set up a test OP realm, user <code>alice.test</code>, and client <code>portal-it</code>.
2. Register the exact login callback and post-logout redirect URI.
3. Verify whether OP Discovery exposes <code>end_session_endpoint</code>.
4. Check for <code>revocation_endpoint</code> if testing remote revocation.
5. Configure the Spring Boot Servlet OAuth2 Client with test session/cookie settings.
6. Ensure test data, client secrets, and signing keys are non-production.

### Phase B — Local Logout

1. Create a `POST /logout` form with a CSRF token.
2. Configure <code>LogoutFilter</code> via <code>http.logout(...)</code>.
3. Create the public <code>/logged-out</code> landing route.
4. Confirm `SecurityContext` is cleared and the HTTP session is invalidated.
5. Test that protected requests after logout require authentication.
6. Test that logout without CSRF is rejected.

### Phase C — Authorized-Client Cleanup

1. Identify the service/repository actually in use.
2. Verify registration ID keys and verified principal names.
3. Add the custom `LogoutHandler` for service-backed data.
4. Decide whether policy removes the current registration or all connections.
5. Test Alice/Bob and multiple registrations.
6. With JDBC/Redis, verify persistence and session invalidation remain distinct.

### Phase D — OIDC SSO Logout

1. Configure <code>OidcClientInitiatedLogoutSuccessHandler</code>.
2. Set a safe post-logout redirect URL.
3. Sign in via browser through the test OP.
4. Submit the logout POST form.
5. Verify the browser redirects to the OP end-session endpoint.
6. Observe OP session behavior when logging in again in the same browser context.
7. Test behavior when a provider does not support logout.

### Phase E — Optional Token Revocation

1. Decide which tokens/grants require remote revocation.
2. Use only the trusted provider revocation endpoint.
3. Capture the token before local deletion.
4. Send the RFC 7009 request with proper client authentication.
5. Record the normalized outcome and remove the local record per policy.
6. Test unknown tokens, timeouts, 503, `invalid_client`, and partial failures.
7. Test token acceptance at the Resource Server per token format and policy.

### Phase F — Production Hardening

1. Enforce HTTPS, exact redirect URIs, and trusted forwarded headers.
2. Use shared sessions and a shared authorized-client store in clusters.
3. Prevent post-logout refresh resurrection using versioning/coordination as needed.
4. Define per-device vs. all-device logout behavior clearly.
5. Never log tokens, ID Token hints, authorization codes, or session cookies.
6. Configure bounded timeouts/retries, metrics, and audits.
7. Write incident runbooks and staging E2E smoke tests.

## 34. Common Design Mistakes

### 34.1. Clearing Only `SecurityContext` and Claiming Tokens Are Revoked

Wrong because persistent authorized-client records and issued tokens have independent lifecycles.

### 34.2. Calling Only the OP Logout Endpoint and Skipping Local Session Cleanup

Ending the OP SSO session does not automatically invalidate the Portal's local session. The Portal must still execute local logout.

### 34.3. Deleting Tokens by Email from a Query Parameter

Wrong because users can spoof query parameters and email is not a verified storage ownership key.

### 34.4. Calling Remove After the Session Token Is Gone

With a session-backed repository, enforce handler ordering if remote revocation needs the access/refresh token before invalidation.

### 34.5. Using a `client_credentials` Token to "Simulate" User Logout

The Client Credentials grant represents a service identity, not an OIDC browser user session. Never use it for RP-Initiated Logout or to delete delegated user grants.

### 34.6. Enabling `GET /logout` and Disabling CSRF

Browser logout is a state-changing action; use POST with CSRF protection.

### 34.7. Hardcoding External `post_logout_redirect_uri`

The OP may reject it or the app may introduce an open redirect. Use only registered, trusted HTTPS destinations for the active environment.

### 34.8. Accepting Unsigned JSON as Back-Channel Logout

OIDC Back-Channel Logout requires a verified Logout Token with security claims; unsigned JSON proves nothing about OP origin.

### 34.9. Holding Refresh Tokens in an Unencrypted Retry Queue

Retryable cleanup jobs containing secrets require encryption, access controls, expiry/retention, and auditing.

### 34.10. Ignoring Token Resurrection

Background refreshes can re-save tokens after local deletion. Use versioning, tombstones, and coordination per architecture.

## 35. Production Hardening: When Local Cleanup Fails

<code>AuthorizedClientCleanupLogoutHandler</code> in Section 10 is intentionally simple to clarify the service API. In production, <code>removeAuthorizedClient</code> can throw runtime exceptions if JDBC or Redis is unavailable.

### 35.1. Do Not Let Cleanup Exceptions Block Local Logout

A practical policy can be:

~~~text
Local session must end even if persisted cleanup fails
    → local logout = complete
    → cleanup status = failed/pending
    → secure retry if required
    → never claim remote revocation completed without evidence
~~~

This is a security/business decision—not every product must choose the exact same trade-off. When mandatory remote revocation must finish first, design failure UX accordingly.

### 35.2. Production Handlers Should Avoid Throwing Out of the Logout Lifecycle

A controlled implementation:

~~~java
for (String registrationId : registrationIds) {
    try {
        service.removeAuthorizedClient(
            registrationId, principalName);
        // Publish sanitized cleanup success event.
    } catch (RuntimeException cleanupFailure) {
        // Publish normalized failure category and provider alias.
        // Enqueue bounded, secure retry if business policy requires.
        // Do not leak raw tokens or credentials to logs.
        // Keep local logout progressing according to security policy.
    }
}
~~~

With framework <code>LogoutHandler</code>s, avoid throwing exceptions that abort the rest of the logout chain. At the same time, never swallow errors silently: emit audits/metrics and run reconciliation for dangling token records.

### 35.3. Retry Cleanup Can Delete a Newer Grant by Mistake

~~~text
T0: user logout, old authorized client version=7
T1: cleanup retry scheduled
T2: user logs in again, new authorized client version=8
T3: old cleanup retry runs
~~~

An unconditional <code>removeAuthorizedClient(registrationId, principalName)</code> at T3 can delete **version 8** instead of the stale record. For delayed cleanup, tie the cleanup intent to the old grant's generation/version/record ID or a tombstone policy so newer grants stay intact.

### 35.4. OP and Database Are Not in One ACID Transaction

~~~text
DB removal succeeds, OP revoke fails
OP revoke succeeds, DB removal fails
Network timeout, outcome unknown
~~~

Handle partial outcomes and recovery explicitly; never assume a database transaction wraps an HTTP revocation call at the OP.

### 35.5. Re-Logging In While Cleanup Is Still Running

Tests should verify:

- New grants are not deleted by stale cleanup tasks.
- Stale refresh jobs never save revoked tokens after logout.
- New sessions never inherit authorized clients from another session or tenant.
- Metrics accurately reflect pending/failed cleanup.

## 36. Self-Practice Exercises

### Exercise 1 — Does Local Logout Clear the OP SSO Cookie?

User logs out of the Portal and clicks Login; the OP logs them right back in without asking for a password.

**Answer:** Not necessarily a bug in local logout. The OP cookie/session may still exist; use RP-Initiated Logout when policy requires ending OP SSO.

### Exercise 2 — Does Local Removal Revoke the Remote Token?

~~~java
service.removeAuthorizedClient("company", principalName);
~~~

**Answer:** It deletes only the authorized client record in the local service, without calling an RFC 7009 endpoint.

### Exercise 3 — Why Does Logout Need CSRF?

**Answer:** It is a state-changing browser action; POST with CSRF prevents unwanted cross-site logout requests.

### Exercise 4 — MockMvc Returns HTTP 403

~~~java
mockMvc.perform(post("/logout").with(oidcLogin()));
~~~

**Answer:** With CSRF enabled, a POST lacking a token is blocked. Add <code>.with(csrf())</code> for valid tests.

### Exercise 5 — Does `@WithMockUser` Test `OAuth2AuthenticationToken` Cleanup?

**Answer:** Not reliably. The handler in Section 10 checks for <code>OAuth2AuthenticationToken</code>; <code>@WithMockUser</code> produces a different `Authentication` type, skipping the cleanup branch.

### Exercise 6 — Deleting Bob by Mistake

An endpoint uses <code>request.getParameter("user")</code> as the principal name, and Alice sends <code>user=bob</code>.

**Answer:** Ownership vulnerability. Always take the verified `Authentication` server-side, never a browser-supplied username.

### Exercise 7 — Removing Company While Partner Remains

Alice has authorized clients for both Company and Partner; the handler removes only Company.

**Answer:** Sufficient if policy is "current registration only", insufficient if the product promises full cleanup. Define explicit policy and tests.

### Exercise 8 — Is `principalName` Always Equal to Email?

**Answer:** No. The key must match how the authorized client was saved; it may be an OIDC subject or custom name and must avoid cross-issuer/tenant collisions.

### Exercise 9 — Does HTTP Session Invalidation Delete JDBC Tokens?

**Answer:** Not automatically. JDBC service-backed token records persist independently of HTTP sessions unless explicitly cleaned up.

### Exercise 10 — Is `end_session_endpoint` the Revocation Endpoint?

**Answer:** No. OIDC end-session handles OP SSO logout; RFC 7009 revocation handles token/grant revocation.

### Exercise 11 — Revocation Returns HTTP 200

**Answer:** HTTP 200 does not prove the token ever existed or that all Resource Servers immediately invalidated existing access JWTs.

### Exercise 12 — Self-Contained JWT After Logout

JWT expires at 10:15, Portal logout occurs at 10:02, and the Resource Server checks only signature and expiry.

**Answer:** The old JWT may still be accepted by the RS until 10:15 without dynamic revocation checks.

### Exercise 13 — OP Lacks `end_session_endpoint`

**Answer:** Local logout can still succeed, while OP SSO logout cannot be claimed. Provide appropriate fallbacks and accurate UX.

### Exercise 14 — Redirect URI Rejected by OP

<code>post_logout_redirect_uri</code> has the wrong HTTPS host.

**Answer:** Check the exact URI registered at the OP, trusted forwarded headers, and <code>{baseUrl}</code> expansion.

### Exercise 15 — Browser Does Not Follow OP Redirect

User leaves the Portal but closes the tab before the browser reaches the OP end-session endpoint.

**Answer:** The local session may have ended while the OP session persists. Use browser E2E tests and accurate UX rather than claiming OP logout completed based on a Portal 302.

### Exercise 16 — Session-Backed Repository

Tokens live solely in `HttpSession`. A custom handler runs after session invalidation and fails to load the refresh token for revocation.

**Answer:** For remote revocation, capture the token prior to invalidation using explicit handler ordering; local cleanup alone can rely on session invalidation per repository semantics.

### Exercise 17 — Token Resurrection

Node B saves `A1`/`R1` after Node A deleted the authorized-client record during logout.

**Answer:** Use grant generations/tombstones, status re-checks, CAS, and coordination to prevent stale refresh saves from recreating deleted tokens.

### Exercise 18 — Retry Cleanup Deletes a New Token

User logs out and logs back in; a delayed cleanup task from the old session runs late.

**Answer:** Never unconditionally delete the current record; bind cleanup intents to the old grant's generation/version so newer grants are preserved.

### Exercise 19 — Single-Device Logout

Browsers A and B for the same principal share one service record.

**Answer:** Deleting the shared record when A logs out impacts B. Define per-device vs. per-principal policies intentionally; session invalidation and service cleanup operate at different scopes.

### Exercise 20 — Disconnecting Partner

User stays logged into Company but wants to disconnect Partner.

**Answer:** Use a CSRF-protected POST disconnect endpoint with allowlisted registrations and verified ownership, without invalidating the Portal session. Remotely revoke if supported by policy/provider.

### Exercise 21 — Forged Back-Channel Logout Token

An attacker POSTs unsigned JSON with <code>sub=alice</code> to the back-channel endpoint.

**Answer:** Reject it. Verify the signed Logout Token, <code>iss</code>, <code>aud</code>, <code>events</code>, <code>sid/sub</code>, and all OIDC profile requirements.

### Exercise 22 — Remote Revocation Timeout

The Portal sends a refresh token revocation request and receives no response.

**Answer:** Outcome is uncertain. Use bounded retries/reconciliation, telemetry, and local logout policy; never claim remote revocation succeeded.

### Exercise 23 — Does OP Logout Equal Global Logout?

**Answer:** Not by default. Check OP session scope, Portal global session registry, token/grant policies, and behavior across other devices.

### Exercise 24 — Does `oidcLogin()` Prove OP SSO Logout?

**Answer:** No. <code>oidcLogin()</code> mocks a principal in request tests and performs no browser/OP session termination.

### Exercise 25 — End-to-End Logout Test Lab

Setup:

~~~text
Test Keycloak/OP
Spring Boot OAuth2/OIDC Client
Service-backed JDBC authorized-client store
POST /logout + CSRF
OidcClientInitiatedLogoutSuccessHandler
~~~

**Requirement:** Log in Alice; verify the authorized-client record is persisted; log out; verify the local session is invalidated and the record is cleaned up; verify the browser completes OP logout and returns to <code>/logged-out</code>. Never rely solely on HTTP 302 status.

### Exercise 26 — Negative Tests

Write tests for:

~~~text
Missing CSRF
Wrong principal
Wrong registration
OP lacks end_session_endpoint
Revocation HTTP 503
JDBC unavailable
Forged Back-Channel Logout Token
~~~

**Expected answer:** For each test, document the expected local session state, token store state, OP outcome, and log redaction.

### Exercise 27 — Multi-Registration Policy Design

User holds Company, Partner, and Analytics. UI offers three actions: log out current device, disconnect Partner, and log out of Portal removing all delegated clients.

**Hint:** Build a state-transition table for each action covering Portal session, `OAuth2AuthorizedClientService`, OP SSO, and remote token/grant state. Never use a single handler for every action when cleanup scopes differ.

### Exercise 28 — Comprehensive Integration Exercise

1. Stand up a dedicated test OP and client without production credentials.
2. Configure Authorization Code/OIDC Login.
3. Use a service-backed authorized-client store.
4. Implement <code>AuthorizedClientCleanupLogoutHandler</code>.
5. Build a `POST /logout` form with CSRF.
6. Wire <code>OidcClientInitiatedLogoutSuccessHandler</code>.
7. Register the exact post-logout redirect URI at the OP.
8. Expose the public <code>/logged-out</code> endpoint.
9. Unit-test deleting Alice/company and Alice/partner while preserving Bob.
10. MockMvc-test that missing CSRF returns 403 and valid logout succeeds.
11. Browser E2E-test real OP SSO logout.
12. Optionally RFC 7009 revocation-test with a test-only refresh token.
13. Test that an Access JWT may remain valid after local deletion per Resource Server policy.
14. Test two-device logout policies.
15. Test logout vs. refresh races on a shared store.
16. Test that cleanup retries do not delete newer re-authorizations.
17. Test that forged Back-Channel Logout Tokens are rejected.
18. Verify logs contain no tokens, session cookies, or ID Token hints.
19. Write a runbook for OP revocation/logout endpoint outages.
20. Record evidence for every logout scope.

**Synthesis question:** Have you independently proven all four outcomes: **local session ended**, **local authorized-client records removed accurately**, **OP SSO session terminated per provider policy**, and **remote tokens/grants revoked per Authorization Server contract**?

## 37. Summary

- **Local logout**, **OIDC RP-Initiated Logout**, **authorized-client cleanup**, and **RFC 7009 revocation** are four distinct mechanisms.
- Local logout clears <code>SecurityContext</code> and the HTTP session. Clearing local sessions does not automatically delete tokens in JDBC/Redis, OP SSO sessions, or issued access tokens.
- <code>OAuth2AuthorizedClientService</code> deletes by <code>registrationId</code> and <code>principalName</code>; the principal must come from verified server-side identity, never browser input.
- <code>OAuth2AuthorizedClientRepository</code> can be session-backed or service-backed; know your source of truth for save, load, refresh, and removal.
- Custom <code>LogoutHandler</code>s handle local cleanup. <code>OidcClientInitiatedLogoutSuccessHandler</code> initiates the OP end-session redirect when supported by the provider.
- Browser logout should use **POST + CSRF**, and <code>/logged-out</code> must be public to prevent redirect loops.
- <code>post_logout_redirect_uri</code> must be allowlisted exactly per environment using a trusted public HTTPS base URL.
- OIDC OP logout does not imply local storage cleanup; RFC 7009 token revocation does not imply OP SSO logout.
- Revocation HTTP 200 neither proves a token existed nor guarantees every Resource Server immediately invalidates JWTs.
- Full logout and disconnecting a single provider have different scopes; with multiple devices, shared service-backed records need explicit ownership and cleanup policies.
- Refresh-token rotation and background jobs can cause **token resurrection** after logout. Delayed cleanup retries can also delete newer authorized clients. Use versioning, tombstones, conditional writes, and coordination as needed.
- OIDC Back-Channel Logout requires a **signed Logout Token** and verified issuer/audience/session mapping; never accept unsigned JSON to terminate sessions.
- Production `LogoutHandler`s should avoid throwing exceptions that block local logout, emit safe metrics, and use reliable cleanup reconciliation.
- Unit tests verify service cleanup; MockMvc verifies CSRF/`LogoutFilter`; browser tests verify OP SSO behavior; revocation tests verify OP token/grant contracts. No single test type replaces the others.
- Logs and metrics should record only normalized outcomes and safe provider aliases/correlation IDs—never raw access/refresh/ID Tokens, <code>id_token_hint</code>, authorization codes, client secrets, or session cookies.

### References

- **Spring Security Reference — Servlet Authentication Logout:** `LogoutFilter`, `LogoutHandler`, `LogoutSuccessHandler`, and CSRF logout.
- **Spring Security Reference — OAuth2 Login (Servlet):** `ClientRegistration`, `Authentication`, and OIDC User.
- **Spring Security Reference — OAuth2 Client:** `OAuth2AuthorizedClientService`, `OAuth2AuthorizedClientRepository`, and authorized-client persistence.
- **Spring Security Java API — `OidcClientInitiatedLogoutSuccessHandler`:** RP-Initiated Logout and post-logout redirect URIs.
- **Spring Security Java API — `InMemoryOAuth2AuthorizedClientService` / `JdbcOAuth2AuthorizedClientService`:** local storage implementations.
- **Spring Security Test Reference — MockMvc:** `oidcLogin()`, `oauth2Login()`, `csrf()`, and logout testing.
- **OpenID Connect RP-Initiated Logout 1.0:** `end_session_endpoint`, `id_token_hint`, `post_logout_redirect_uri`, and logout state.
- **OpenID Connect Back-Channel Logout 1.0:** Logout Token, issuer/audience/events/`sid`/`sub`, and OP-initiated session termination.
- **OpenID Connect Core 1.0:** ID Token, authenticated principal, issuer/subject, and session semantics.
- **RFC 6749 — The OAuth 2.0 Authorization Framework:** authorization grants, access and refresh tokens.
- **RFC 7009 — OAuth 2.0 Token Revocation:** revocation endpoint, `token_type_hint`, and response semantics.
- **RFC 9700 — Best Current Practice for OAuth 2.0 Security:** refresh-token rotation, token replay, and credential handling.
- **OWASP Cross-Site Request Forgery Prevention Cheat Sheet:** logout and browser state-changing requests.
- **OWASP Session Management Cheat Sheet:** session invalidation, cookies, and session lifecycle.
- **OWASP Logging Cheat Sheet:** keeping credentials, tokens, session secrets, and PII out of logs.
