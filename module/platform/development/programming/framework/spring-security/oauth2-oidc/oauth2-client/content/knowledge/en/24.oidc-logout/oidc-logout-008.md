# 24.8. Integrating Back-Channel Logout by Stack and Supported Version

## 1. The Problem: User Logs Out of the OpenID Provider, Yet the Application Session Remains

A Spring Boot application uses Spring Security OAuth 2.0/OIDC Client to log in via an OpenID Provider (OP). After login, the app creates an HTTP session and stores the user's <code>Authentication</code>. The user may close the tab, switch browsers, or log out from another application sharing the same OP.

If the user logs out of the OP, **the session in the Client application does not automatically disappear in all cases**. The Client's HTTP session and the OP's SSO session are two independent states. A Client only knows the user logged out at the OP if there is an appropriate synchronization/notification mechanism.

Example:

~~~text
09:00 User logs into Portal A via OP.
09:05 User logs into Portal B, still via OP.
09:30 User logs out at Portal B and OP ends the SSO session.
09:31 Portal A still holds SecurityContext in its HTTP session.
~~~

If Portal A does not participate in an OP-notified logout mechanism, subsequent requests to Portal A may still be authenticated using Portal A's session cookie.

**OpenID Connect Back-Channel Logout** addresses notifications in the reverse direction:

~~~text
OpenID Provider → direct HTTP POST to Relying Party / OIDC Client
~~~

The OP sends a signed **Logout Token** to the registered endpoint. The Client validates the token, locates its sessions identified by <code>sid</code> or <code>sub</code>, and terminates the matching sessions.

> **Core idea:** Back-Channel Logout is a **server-to-server** notification from OP to Client. It does not require an open browser or browser session cookies attached to the logout request. Because of that, the Client must maintain a **reliable mapping between OP sessions and internal sessions** to locate the exact sessions to destroy.

In Spring Security, this mechanism is supported with dedicated components for **Servlet** and **Reactive WebFlux**. Configuration APIs, handlers, session registries, and some endpoint details also depend on the **Spring Security version** in use.

## 2. Lesson Objectives

After this lesson, you will be able to:

1. Distinguish local logout, RP-Initiated Logout, Front-Channel Logout, and Back-Channel Logout.
2. Understand the contents and validation rules of an OIDC Logout Token under Back-Channel Logout 1.0.
3. Configure the Back-Channel Logout endpoint in **Servlet `SecurityFilterChain`** and **WebFlux `SecurityWebFilterChain`** when supported by your version.
4. Identify key changes from Spring Security **6.2**, **6.2.x**, **6.5**, and **7.x**; never copy APIs across versions without verification.
5. Register the exact <code>backchannel_logout_uri</code> and choose between <code>sid</code> or <code>sub</code> mechanisms with the OP.
6. Distinguish <code>HttpSession</code>/<code>WebSession</code>, session cookies, <code>OidcSessionRegistry</code>, and <code>OAuth2AuthorizedClientService</code>.
7. Design back-channel logout when running **multiple instances**, using Spring Session Redis or a distributed session store.
8. Avoid confusing Client session invalidation with revoking access/refresh tokens at the Authorization Server.
9. Test valid tokens, bad signatures, wrong audience, missing <code>sid</code>/<code>sub</code>, replay, multi-tenant, and network errors.

## 3. Distinguishing Four Forms of Logout

In an OIDC application, the phrase "logged out" can refer to four very different actions.

| Mechanism | Who Initiates? | Transport Channel | Typical Effect |
|---|---|---|---|
| **Local Logout** | User/browser at Client | Browser → Client | Destroys internal HTTP session/`SecurityContext` |
| **RP-Initiated Logout** | Client/Relying Party | Browser redirect or POST to OP | Asks OP to end SSO session; may return to Client |
| **Front-Channel Logout** | OP | Via browser/user agent | OP has browser hit logout endpoints of Clients |
| **Back-Channel Logout** | OP | **Server-to-server HTTP** | OP sends Logout Token so Client invalidates matching sessions |

### 3.1. Local Logout

For example, the browser sends:

~~~http
POST /logout HTTP/1.1
Host: portal.example.org
Cookie: JSESSIONID=SESSION_ID_PLACEHOLDER
~~~

Spring Security can clear `SecurityContext` and invalidate the local HTTP session. **This does not automatically terminate the SSO session at the OP**.

### 3.2. RP-Initiated Logout

The application can redirect the browser to the OP's <code>end_session_endpoint</code>, e.g., using <code>OidcClientInitiatedLogoutSuccessHandler</code> in Servlet or <code>OidcClientInitiatedServerLogoutSuccessHandler</code> in WebFlux.

This is a **Client asking OP to log out** flow, not the OP proactively calling the Client's Back-Channel Logout endpoint.

### 3.3. Front-Channel Logout

The OP relies on the browser to deliver messages to Clients. This mechanism can depend on the browser staying open, cookie policies, iframe/cross-site restrictions, and how Front-Channel Logout is configured.

### 3.4. Back-Channel Logout

The OP sends directly:

~~~http
POST /logout/connect/back-channel/company HTTP/1.1
Host: portal.example.org
Content-Type: application/x-www-form-urlencoded

logout_token=SIGNED_LOGOUT_TOKEN_PLACEHOLDER
~~~

There are no browser cookies in this request. That is why Spring Security needs a mapping between the OP's **Logout Token** and internal **Client sessions**, rather than reading cookies from the OP's incoming request.

**Back-Channel Logout is not an OAuth2 Refresh Token Grant**, not an authorization request, and not an HTTP <code>DELETE</code> to a Resource Server.

## 4. Participating Parties and States

A system has:

~~~text
Browser / End-User
    |
    | session cookie
    v
Portal / Relying Party (RP)
    |                 |
    | HTTP Session    | OAuth2AuthorizedClient
    | SecurityContext | access/refresh tokens
    v                 v
Session Store       Token Store
    ^
    |
    | OIDC Provider session ↔ Client session mapping
    |
OidcSessionRegistry
    ^
    |
    | Logout Token via HTTP POST
    |
OpenID Provider (OP)
~~~

### 4.1. Four Identifiers Not to Equate

| Identifier | Who Creates/Manages? | Example | Role |
|---|---|---|---|
| <code>iss</code> | OpenID Provider | <code>https://idp.example.org/realms/company</code> | Identifies trusted issuer |
| <code>sub</code> | OP | <code>user-123</code> | End-User subject scoped to issuer |
| <code>sid</code> | OP | <code>op-session-7f...</code> | OP session identifier for logout correlation |
| Client HTTP session ID | Portal/Spring Session | <code>app-session-9d...</code> | RP's internal session identifier |

<code>sid</code> **does not necessarily equal** <code>JSESSIONID</code>, <code>SESSION</code> cookie value, or a Redis key ID. They are two separate session spaces.

### 4.2. `OAuth2AuthorizedClient` Is Not the HTTP Session

<code>OAuth2AuthorizedClient</code> holds tokens issued for a registration/principal. After Back-Channel Logout, the internal session may be invalidated while the access token remains unexpired at the Resource Server or the token store still retains the record.

Therefore, decide **separately** on authorized client cleanup, refresh token revocation, and access blocking policies. Never treat session invalidation as revoking all access tokens.

## 5. Check Your Spring Security Version Before Writing Code

Do not see <code>OidcLogoutConfigurer</code> in documentation for a newer version and paste it into an older project without verifying actual dependencies.

### 5.1. Key Support Milestones

| Spring Security Line | Back-Channel Logout in Client | Implementation Notes |
|---|---|---|
| **Before 6.2**, e.g., 6.1 | No built-in Back-Channel Logout DSL as in newer docs | Consider upgrading or implementing spec-compliant custom classes with full security testing |
| **6.2.x** | Introduces <code>oidcLogout(...).backChannel(...)</code> DSL for Servlet and Reactive | Default APIs/handlers/endpoints may differ from 6.5/7.x; check exact patch version |
| **6.2.4+** | Adds <code>logoutUri(...)</code> API in Back-Channel Logout configurer | URI used for internal session logout operation; does not replace registering public endpoint at OP |
| **6.5.x** | Servlet/Reactive guides and handlers/registries for customizing session logout | Watch <code>JSESSIONID</code> vs Spring Session <code>SESSION</code> cookie carefully |
| **7.x** | Continues DSL, dedicated OIDC Logout guides for Servlet and Reactive | Do not assume all 6.x constructors/imports stay identical; prefer docs for exact minor version |

The 6.2 milestone and <code>logoutUri</code> from 6.2.4 are reflected in the Spring Security Java API. Merely **having the DSL classes** does not guarantee your provider, session registry, internal logout handler, and cookie configuration work properly together.

### 5.2. Spring Boot Version Is Not the Spring Security Version

Spring Boot manages the Spring Security version via dependency management. Saying "Boot 3.x" is not enough to conclude all Spring Security 6.5 APIs exist. Saying "Boot 4.x" does not mean snippets from 6.2.x copy verbatim.

Verify the **actual Spring Security version** resolved in your build dependencies, then open the API/reference docs for that exact version.

### 5.3. Why Split by Servlet and Reactive?

| Item | Servlet | Reactive WebFlux |
|---|---|---|
| Security builder | <code>HttpSecurity</code> | <code>ServerHttpSecurity</code> |
| Security chain | <code>SecurityFilterChain</code> | <code>SecurityWebFilterChain</code> |
| Session | <code>HttpSession</code> | <code>WebSession</code> |
| OP/RP mapping registry | <code>OidcSessionRegistry</code> | <code>ReactiveOidcSessionRegistry</code> |
| Dedicated handler | <code>OidcBackChannelLogoutHandler</code> | <code>OidcBackChannelServerLogoutHandler</code> |
| Event on Servlet session destroy | Can use <code>HttpSessionEventPublisher</code> | Dedicated reactive lifecycle/session repository |
| Back-channel config | <code>http.oidcLogout(...)</code> | <code>http.oidcLogout(...)</code> on reactive builder |

The DSL names look similar, yet handlers/interfaces **are not interchangeable**. Never pass a Servlet handler into a reactive chain or use <code>HttpSession</code> directly in WebFlux.

## 6. OpenID Provider Prerequisites Before Enabling Back-Channel Logout

### 6.1. OP Must Support the Feature

OIDC Discovery metadata may publish:

~~~json
{
  "issuer": "https://idp.example.org/realms/company",
  "backchannel_logout_supported": true,
  "backchannel_logout_session_supported": true
}
~~~

Explanation:

- <code>backchannel_logout_supported=true</code>: OP announces Back-Channel Logout capability.
- <code>backchannel_logout_session_supported=true</code>: OP can send the <code>sid</code> claim for session correlation; OP can also include <code>sid</code> in ID Tokens.

If metadata omits this, never assume the provider supports it. Support may depend on tenant, realm, Client registration, or OP settings.

### 6.2. Client Must Register `backchannel_logout_uri`

A Client registration may need metadata:

~~~json
{
  "client_id": "portal-web",
  "backchannel_logout_uri":
    "https://portal.example.org/logout/connect/back-channel/company",
  "backchannel_logout_session_required": false
}
~~~

<code>backchannel_logout_uri</code> is the address **the OP can call via server-to-server HTTP**—not the authorization code redirect URI:

~~~text
Authorization Code callback:
    https://portal.example.org/login/oauth2/code/company

Back-Channel Logout endpoint:
    https://portal.example.org/logout/connect/back-channel/company
~~~

**Both endpoints must be registered for their exact purposes.** Substituting the callback for the logout endpoint or vice versa breaks the flow and can introduce security risks.

### 6.3. Is `sid` Required?

<code>backchannel_logout_session_required</code> lets the Client tell the OP that Logout Tokens must contain <code>sid</code> if required.

| Policy | Consequence |
|---|---|
| <code>true</code> | Accepts only OP session ID mechanism if provider/config supports it; suited for per-session logout |
| <code>false</code> | Can handle Logout Tokens without `sid`, using <code>iss + sub</code> to log out all matching user sessions for the Client |

Do not enable <code>session_required=true</code> if the OP does not issue <code>sid</code> and then expect every browser session to be handled automatically. Check provider capabilities and the actual contract.

### 6.4. Endpoint Must Be Reachable from the OP

The OP usually runs on different infrastructure from the application. If the RP only exists on <code>localhost</code>, private DNS unresolvable from the OP, or behind an inbound firewall blocking traffic, the OP cannot deliver requests.

Production typically requires HTTPS, public DNS or agreed private connectivity, valid TLS certificates, and gateway/proxy routes that do not mistakenly block form POSTs.

If the OP supports dynamic endpoint registration, SSRF protection **on the OP side** is essential when calling registered URIs. The RP should also restrict ingress and monitor traffic, while **never using source IP as the sole authentication mechanism**.

## 7. OIDC Logout Token: A JWT with a Dedicated Purpose

A Logout Token is a JWT created and signed by the OP to announce a **logout** event. It is **not**:

- An ID Token proving authentication for a new login.
- An access token for calling a Resource Server.
- A refresh token of an `OAuth2AuthorizedClient`.
- An authorization code.
- A browser CSRF token.

An illustrative payload per OIDC Back-Channel Logout 1.0 might look like:

~~~json
{
  "iss": "https://idp.example.org/realms/company",
  "aud": "portal-web",
  "iat": 1794800000,
  "exp": 1794800120,
  "jti": "logout-event-8d74b6",
  "sub": "user-123",
  "sid": "op-session-7f3d4a",
  "events": {
    "http://schemas.openid.net/event/backchannel-logout": {}
  }
}
~~~

This JSON is illustrative only, not a valid unsigned JWT. A header might use:

~~~json
{
  "alg": "RS256",
  "typ": "logout+jwt",
  "kid": "op-key-2026"
}
~~~

Under OIDC Back-Channel Logout 1.0 **incorporating errata set 1**, <code>exp</code> is a mandatory claim. Older docs/libraries based on the 2022 final edition may show a different list; when checking compatibility, verify the **spec edition and OP/Spring Security behavior** rather than dropping expiration checks.

### 7.1. Claim Table

| Claim | Role | Checks to Perform |
|---|---|---|
| <code>iss</code> | OP's issuer | Must match trusted issuer configured for Client |
| <code>aud</code> | Audience (OIDC Client/RP) | Must contain Client ID registered for the matching registration |
| <code>iat</code> | Issued-at time | Validate per time and clock skew policy |
| <code>exp</code> | Expiration time | Token must not be expired; mandatory per errata set 1 |
| <code>jti</code> | JWT identifier | Event ID supporting replay prevention/idempotency |
| <code>events</code> | Marks this as a logout event | Must contain exact key for back-channel logout |
| <code>sub</code> | End-User subject | Used to find subject's sessions per issuer/client |
| <code>sid</code> | OP session identifier | Used to find matching RP session(s) |
| <code>nonce</code> | **Must be absent** | Must reject if present |

<code>sub</code> and <code>sid</code> **may each be omitted individually**, but a Logout Token **must contain at least one of the two**.

### 7.2. `events` Must Contain the Exact Event URI

Valid structure:

~~~json
{
  "events": {
    "http://schemas.openid.net/event/backchannel-logout": {}
  }
}
~~~

Notice the URI starts with **<code>http://</code>** per specification—it is not an HTTP request URL called by the app and must not be changed to <code>https://</code>.

Without this event, never treat a JWT as a Logout Token simply because it has <code>iss</code>, <code>sub</code>, and a valid signature.

### 7.3. Why Is `nonce` Prohibited?

An OIDC ID Token may contain <code>nonce</code> to bind an authentication response to a login request. Logout Tokens **forbid** the <code>nonce</code> claim to reduce the risk of a logout JWT being mistaken for a login ID Token.

This is a key part of preventing **cross-JWT confusion**. Never design a decoder that "accepts any OP JWT with a valid signature" and share it between login and logout.

### 7.4. `sid` Differs from the Application's Session ID

If the OP sends:

~~~json
{
  "sid": "op-session-7f3d4a"
}
~~~

that is an OP session ID. Spring Security must rely on the **mapping saved at login** to locate the corresponding Client HTTP session ID, rather than calling:

~~~text
invalidateHttpSession("op-session-7f3d4a")
~~~

unless the app built a verified mapping; never treat an OP `sid` as a browser-submitted session cookie value.

## 8. Back-Channel Logout HTTP Request and Response

The specification uses **POST** with content type:

~~~http
Content-Type: application/x-www-form-urlencoded
~~~

The form body contains:

~~~text
logout_token=<signed JWT issued by OP>
~~~

Descriptive example:

~~~http
POST /logout/connect/back-channel/company HTTP/1.1
Host: portal.example.org
Content-Type: application/x-www-form-urlencoded

logout_token=HEADER.PAYLOAD.SIGNATURE
~~~

No browser cookie or <code>Authorization: Bearer <access_token></code> is needed to prove the logout request. **The proof of the logout event is the signed and validated Logout Token**.

### 8.1. Processing Sequence at the RP

1. Route the request to the Back-Channel Logout handler for the matching OIDC Client registration.
2. Parse the <code>logout_token</code> form parameter with size limits.
3. Verify the signature with the trusted OP's key and validate JWT header/claims.
4. Check <code>iss</code>, <code>aud</code>, <code>iat</code>, <code>exp</code>, <code>jti</code>, <code>events</code>, <code>sid</code>/<code>sub</code>, and absence of <code>nonce</code>.
5. Locate Client HTTP sessions mapped to the OP session/subject for the exact issuer/audience.
6. Invalidate matching sessions via Spring Security/framework mechanisms.
7. Clean up registry mappings and execute token/application state cleanup per policy.
8. Return an appropriate HTTP response without exposing unnecessary session/user details.

### 8.2. Response Status and Retries

Per spec, when a Logout Token is invalid, the RP must **reject** it; HTTP <code>400 Bad Request</code> is the standard validation failure status. On success, the RP returns a success response per contract.

If a transient connection error or RP outage occurs, the OP may retry per policy. Retries **must not cause the app to recreate sessions or accidentally destroy unrelated sessions**.

A robust implementation typically needs:

- Idempotent duplicate handling.
- Replay prevention by <code>(iss, aud, jti)</code> when policy requires.
- Request size and rate limits.
- Monitoring without logging raw Logout Tokens.
- No specific details like "this user has three sessions" returned to callers.

## 9. Overall Flow When the OP Initiates Logout

~~~mermaid
sequenceDiagram
    autonumber
    participant Browser as End-User Browser
    participant RP as Spring Security OIDC Client
    participant Session as Session Store
    participant Registry as OIDC Session Registry
    participant OP as OpenID Provider

    Browser->>RP: OIDC Login callback
    RP->>OP: Authorization Code token exchange
    OP-->>RP: ID Token with iss/sub/(sid)
    RP->>Session: Save SecurityContext and HTTP session
    RP->>Registry: Save mapping issuer/client/sub/sid ↔ RP session
    RP-->>Browser: Session cookie

    Note over OP: Later OP terminates SSO session
    OP->>RP: POST /logout/connect/back-channel/company, logout_token
    RP->>RP: Validate signature, issuer, audience, events, timestamps, jti
    RP->>Registry: Find session(s) by sid or sub
    Registry-->>RP: Matching client session identifiers
    RP->>Session: Invalidate selected sessions
    RP->>Registry: Remove logged-out session mappings
    RP-->>OP: HTTP success response

    Browser->>RP: Subsequent request with old cookie
    RP-->>Browser: No longer authenticated; requires login
~~~

**There is no browser redirect during the step where the OP sends the Logout Token.** That is the key advantage of Back-Channel Logout when tabs are closed or browsers block iframe/front-channel notifications.

## 10. Servlet Configuration: Spring Security Back-Channel Logout DSL

Below illustrates the APIs in Spring Security versions providing the corresponding DSL and handlers, especially **6.5/7.x** guides. Check your project's exact minor version before copying classes/constructors.

### 10.1. Dependencies for Servlet OIDC Client

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-security'
    implementation 'org.springframework.boot:spring-boot-starter-oauth2-client'
}
~~~

### 10.2. `ClientRegistration` with `issuer-uri`

~~~yaml
spring:
  security:
    oauth2:
      client:
        registration:
          company:
            provider: company
            client-id: portal-web
            client-secret: ${PORTAL_CLIENT_SECRET}
            authorization-grant-type: authorization_code
            client-authentication-method: client_secret_basic
            redirect-uri: "{baseUrl}/login/oauth2/code/{registrationId}"
            scope:
              - openid
              - profile
        provider:
          company:
            issuer-uri: https://idp.example.org/realms/company
~~~

**There is no automatic property named <code>backchannel-logout-enabled</code> in the configuration above.** Registering the URI at the OP and enabling the Spring Security DSL are two separate actions.

<code>openid</code> makes this an OIDC login. If an app only configures an OAuth2 Resource Server JWT **without OIDC Login**, the OIDC Client Back-Channel Logout DSL does not automatically build correlated sessions to log out.

### 10.3. Enabling Back-Channel Logout on `SecurityFilterChain`

~~~java
package example.security;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.security.web.session.HttpSessionEventPublisher;

@Configuration
public class OidcLogoutSecurityConfig {

    @Bean
    SecurityFilterChain filterChain(HttpSecurity http) throws Exception {
        http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/", "/error").permitAll()
                .anyRequest().authenticated())
            .oauth2Login(Customizer.withDefaults())
            .oidcLogout(oidc -> oidc
                .backChannel(Customizer.withDefaults()));

        return http.build();
    }

    @Bean
    HttpSessionEventPublisher sessionEventPublisher() {
        return new HttpSessionEventPublisher();
    }
}
~~~

This example shows:

1. <code>oauth2Login()</code> handles browser OIDC Login.
2. <code>oidcLogout(...).backChannel(...)</code> enables the Back-Channel Logout DSL.
3. <code>HttpSessionEventPublisher</code> allows Spring Security to receive HTTP session destruction events and clean up session entries in the registry appropriately.

**In newer guides**, you may add an <code>OidcBackChannelLogoutHandler</code> bean as shown in Section 10.4 to execute per-session logout as recommended in the documentation. Do not copy every snippet variant and accidentally register two handlers of the same type.

### 10.4. Handler for Versions Exposing the Corresponding API

Per Spring Security docs in versions with <code>OidcBackChannelLogoutHandler</code>:

~~~java
@Bean
OidcBackChannelLogoutHandler oidcLogoutHandler() {
    return new OidcBackChannelLogoutHandler();
}
~~~

The class above is a **Servlet handler**, not a Reactive handler. In real projects, use imports matching your Spring Security version.

When registering this handler via the supported mechanism, Spring Security uses it to perform per-session logout instead of requiring manual integration with <code>/logout</code> CSRF tokens as in older setups.

If your version lacks that class/constructor, **never create a class with the same name or rename classes by guessing**. Consult the API docs for your exact version or upgrade to one with clear support.

### 10.5. Default Back-Channel Endpoint

With registration ID <code>company</code>, the endpoint is typically:

~~~text
/logout/connect/back-channel/company
~~~

OP registers the full URL:

~~~text
https://portal.example.org/logout/connect/back-channel/company
~~~

Do not write a POST controller on the same path bypassing Spring Security filters to parse JWTs manually. When using the DSL, let the framework handle signature/claims validation and session invalidation as designed.

## 11. Why Does the Back-Channel Endpoint Not Require Browser Authentication?

The OP calls the endpoint via **server-to-server POST**, with no user logged into an HTTP session.

Therefore, a rule like:

~~~java
.anyRequest().authenticated()
~~~

must not turn Back-Channel Logout into an endpoint callable only by a logged-in browser. When the DSL is properly configured and the request matches the filter, Spring Security handles the logout protocol specially.

When using multiple <code>SecurityFilterChain</code> beans, the endpoint must fall into the chain with <code>oauth2Login()</code> and the Back-Channel Logout filter. An earlier API chain matching <code>/**</code> and requiring a Bearer token can cause the OP to receive 401 before the logout filter runs.

### 11.1. Example of Misconfigured Chain Ordering

~~~text
@Order(1) API chain: matches "/**", oauth2ResourceServer(jwt)
@Order(2) Web chain: oauth2Login + oidcLogout.backChannel

POST /logout/connect/back-channel/company
    → hits API chain
    → Bearer auth required
    → OP gets 401
~~~

Fix: restrict the API chain to <code>/api/**</code> or an explicit matcher, and keep <code>/oauth2/authorization/**</code>, <code>/login/oauth2/code/**</code>, and <code>/logout/connect/back-channel/**</code> in the web chain with OIDC Client support.

### 11.2. Do Not Disable CSRF App-Wide

Back-Channel Logout is not a browser POST using a session cookie, so it must be handled as a **protocol endpoint verified by a Logout Token**, not an arbitrary user logout command.

Do not fix a 403 at this endpoint with:

~~~java
.csrf(csrf -> csrf.disable()) // whole web app
~~~

That weakens cookie-authenticated forms and routes. Use the framework's Back-Channel Logout handler/DSL and configure CSRF intentionally per version docs.

## 12. Servlet: `OidcSessionRegistry` and Session Mapping

Spring Security uses <code>OidcSessionRegistry</code> to link ID Token and OP session metadata to Client HTTP sessions.

Conceptual data example:

~~~text
Client registration: company
Issuer:              https://idp.example.org/realms/company
Client ID:           portal-web
Subject:             user-123
OP sid:              op-session-7f3d4a
Client session ID:   app-session-9d2b
~~~

When receiving a Logout Token:

- If <code>sid</code> is present, Spring Security finds Client sessions matching that OP session ID.
- If only <code>sub</code> is present, Spring Security finds all sessions of that user for the matching Client/issuer.
- Audience and registration boundaries prevent destroying sessions belonging to another OIDC Client.

### 12.1. `sid`-Based vs `sub`-Based Logout

| Logout Token | Intended Meaning | Session Scope |
|---|---|---|
| <code>sid=op-session-A</code> | Log out a specific OP session | RP sessions correlated with OP sid A |
| <code>sub=user-123</code>, no sid | Log out End-User | All RP sessions matching <code>iss + sub + aud/client</code> |
| Both <code>sid</code> and <code>sub</code> | Can verify subject and target exact session | Per `sid` semantics and consistency validation policy |
| Neither sid nor sub | Invalid Logout Token | Must reject |

If a user has two browser sessions under two different OP `sid` values, `sid`-based logout affects only one group, whereas `sub`-only logout can affect both.

### 12.2. Registry Is Not the `HttpSession` Store

<code>OidcSessionRegistry</code> holds the **mapping** to locate sessions, while <code>HttpSession</code>/Spring Session holds the **session state**.

~~~text
OidcSessionRegistry:
    (issuer, client, sub/sid) → HTTP session id(s)

Spring Session Redis:
    HTTP session id → SecurityContext and session attributes
~~~

Both systems must work together. If Spring Session already uses Redis yet the OIDC registry remains in-memory, Node B can read HTTP sessions yet **has no mapping** to know which session to delete when the OP sends a Logout Token to B.

## 13. Multi-Instance: Share Both Sessions and the OIDC Registry

Suppose:

~~~text
Instance A:
    User logs in, session S123
    OidcSessionRegistry(A): sid X → S123

Instance B:
    OidcSessionRegistry(B): empty

Redis Spring Session:
    session S123 exists
~~~

OP sends Logout Token for `sid` X to **B**. B verifies the signature fine, yet B's registry does not know `sid` X maps to S123; the session stays alive in Redis.

This is a **missing shared OIDC session mapping** bug, not a JWT signature or session store bug.

### 13.1. Default Registry Typically Resides in Memory

Per Spring Security guides, the default registry may store OP session ↔ RP session links **in memory**. When scaling out, consider a centrally stored custom registry.

In Servlet, you can implement the <code>OidcSessionRegistry</code> interface with Spring Data/Redis/JDBC per your API version; typical operations include:

~~~java
void saveSessionInformation(OidcSessionInformation info);

OidcSessionInformation removeSessionInformation(
    String clientSessionId);

Iterable<OidcSessionInformation> removeSessionInformation(
    OidcLogoutToken token);
~~~

These are illustrative signatures matching documentation editions, not a complete copy-paste implementation.

### 13.2. Conceptual Schema for a Shared Registry

A mapping store might represent:

~~~text
client_session_id
registration_id
issuer
client_id / audience
subject
provider_sid
created_at
session_expires_at
~~~

Index the keys used for lookups:

~~~text
(issuer, client_id, provider_sid)
(issuer, client_id, subject)
(client_session_id)
~~~

**Never index/store solely by subject** because two issuers/clients can share the same subject string. Never store solely by `sid` because `sid` is opaque and only guaranteed unique within an issuer's context.

### 13.3. Atomicity and Retries

The OP may resend a Logout Token after an earlier timeout. A registry implementation should handle:

- Idempotent removal when the session is already destroyed.
- Lookups/deletions scoped to exact issuer/audience boundaries.
- Preventing stale mappings from reappearing after logout.
- Retention limits matching session TTL.
- Concurrency among logout, session expiry, and fresh logins.
- Never killing a brand-new login session because an old <code>jti</code> was replayed outside policy.

There is no standard distributed transaction across the OP and the RP's Redis/DB, so design recovery for when a logout event arrives while storage is temporarily disconnected.

## 14. Servlet: `JSESSIONID` vs Spring Session `SESSION` Cookie

This is a common misconfiguration when switching from container sessions to Spring Session.

Per Spring Security guides, default session logout handling typically uses cookie name <code>JSESSIONID</code> to bind the chosen session to the logout operation.

However, Spring Session may default to the **<code>SESSION</code>** cookie. When cookie names mismatch, internal logout may fail to locate the target session.

### 14.1. Customizing the Cookie Name on the Handler

In versions with the matching constructor and setter:

~~~java
@Bean
OidcBackChannelLogoutHandler oidcLogoutHandler(
    OidcSessionRegistry oidcSessionRegistry) {

    OidcBackChannelLogoutHandler handler =
        new OidcBackChannelLogoutHandler(oidcSessionRegistry);

    handler.setSessionCookieName("SESSION");
    return handler;
}
~~~

This is an **alternative replacement** for the default handler in Section 10.4—do not define two handler beans just to test.

**Confirm the actual cookie name** from Spring Session config and browser behavior; <code>SESSION</code> is a common example, not an immutable constant across every app.

### 14.2. Do Not Assume Changing the Cookie Name Alone Is Enough

For logout to work across multiple nodes, you also need:

1. A shared session store.
2. Shared OIDC session registry mappings.
3. Matching handler/cookie name.
4. OP requests reaching the right chain endpoint.
5. Proper Logout Token validation.
6. Session cleanup and failure handling.

Without a shared registry, changing <code>JSESSIONID</code> to <code>SESSION</code> still will not tell Node B which session maps to the OP's `sid`.

### 14.3. Never Send User Session Cookies to the OP

Back-Channel requests from OP to RP **do not need browser session cookies**. The internal handler using a session cookie to target/invalidate a session is a mechanism **internal to the RP**, not a sign that the Client should send browser cookies to the OP.

Never expose browser session cookies or CSRF tokens in the back-channel endpoint's response.

## 15. Customizing `logoutUri`: Distinguishing the OP-Called Endpoint from the Internal Endpoint

In versions supporting <code>backChannel().logoutUri(...)</code>, this configures the address Spring Security uses to **execute the logout operation against the session** per implementation/version.

Illustrative example:

~~~java
http
    .oidcLogout(oidc -> oidc
        .backChannel(backChannel -> backChannel
            .logoutUri(
                "http://localhost:9000/logout/connect/back-channel/{registrationId}")));
~~~

**Important notes:**

- <code>logoutUri(...)</code> is not automatically registering the public endpoint with the OP.
- The public <code>backchannel_logout_uri</code> must be configured at the OP per deployment.
- The internal URI must genuinely be reachable from the RP process and route to the right logout handler.
- If internal host/port behind a proxy/ingress differs from the public URL, config must reflect the real network topology.
- Never build the internal logout URI from untrusted <code>Host</code> or forwarded headers controlled by callers.

6.2.x and newer releases can differ in default internal logout URI/handler behavior. **Do not force defaults from 7.x docs onto 6.2.0**, especially around CSRF/session invalidation on the internal endpoint.

In versions lacking the specialized handler, mechanisms requiring CSRF tokens sent to local <code>/logout</code> can be complex and tied to the session repository. Prefer framework-documented integration over disabling CSRF globally.

## 16. Reactive WebFlux Configuration

In WebFlux, the protocol is identical, yet uses reactive security filters and a reactive OIDC registry.

### 16.1. Dependencies

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-webflux'
    implementation 'org.springframework.boot:spring-boot-starter-security'
    implementation 'org.springframework.boot:spring-boot-starter-oauth2-client'
}
~~~

If the app is meant to run Reactive WebFlux, do not inadvertently add <code>spring-boot-starter-web</code>. When both MVC and WebFlux are on the classpath, Spring Boot usually picks Servlet/MVC, so your <code>SecurityWebFilterChain</code> configuration may not apply as expected.

### 16.2. `SecurityWebFilterChain` with `oidcLogout`

~~~java
package example.security;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.reactive.EnableWebFluxSecurity;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.web.server.SecurityWebFilterChain;

@Configuration
@EnableWebFluxSecurity
public class ReactiveOidcLogoutSecurityConfig {

    @Bean
    SecurityWebFilterChain securityWebFilterChain(ServerHttpSecurity http) {
        return http
            .authorizeExchange(exchanges -> exchanges
                .pathMatchers("/", "/error").permitAll()
                .anyExchange().authenticated())
            .oauth2Login(Customizer.withDefaults())
            .oidcLogout(oidc -> oidc
                .backChannel(Customizer.withDefaults()))
            .build();
    }
}
~~~

Changes compared to Servlet:

- <code>ServerHttpSecurity</code> replaces <code>HttpSecurity</code>.
- <code>SecurityWebFilterChain</code> replaces <code>SecurityFilterChain</code>.
- Session is <code>WebSession</code>.
- Security context flows through Reactor Context rather than relying on Servlet request threads.
- Registry uses the reactive type.

### 16.3. Reactive Back-Channel Handler

Per supported documentation versions:

~~~java
@Bean
OidcBackChannelServerLogoutHandler oidcLogoutHandler() {
    return new OidcBackChannelServerLogoutHandler();
}
~~~

When using Spring Session with a non-default cookie name:

~~~java
@Bean
OidcBackChannelServerLogoutHandler oidcLogoutHandler(
    ReactiveOidcSessionRegistry sessionRegistry) {

    OidcBackChannelServerLogoutHandler handler =
        new OidcBackChannelServerLogoutHandler(sessionRegistry);

    handler.setSessionCookieName("SESSION");
    return handler;
}
~~~

These two snippets are **mutually exclusive alternatives**—never declare both beans at once. Import classes from the exact package/version. If your Spring Security version lacks the matching class or constructor, use that version's real API or upgrade.

### 16.4. Reactive Registry Is Not the Servlet Registry

Reactive type:

~~~text
ReactiveOidcSessionRegistry
    saveSessionInformation(...)
    removeSessionInformation(clientSessionId)
    removeSessionInformation(logoutToken)
~~~

These methods mirror Servlet's work yet return reactive publishers such as <code>Mono</code>/<code>Flux</code> per API version.

Never implement a reactive registry with JDBC/Redis calls **blocking directly on the Netty event loop**, or call <code>.block()</code> inside a request handler. Use a reactive-compatible store or isolate blocking I/O in a controlled manner.

### 16.5. Multi-Instance WebFlux

Two nodes using Spring Session Redis for <code>WebSession</code> with an in-memory <code>ReactiveOidcSessionRegistry</code> fail the same way as Servlet:

~~~text
Login on A → A knows OP sid ↔ WebSession S123
Logout Token hits B → B lacks mapping
Redis still keeps WebSession S123
~~~

For cluster-wide logout, deploy both a shared reactive registry and a shared `WebSession` store. Also verify the session cookie name in the handler.

## 17. Session Registry and Token Store: Two Distinct Responsibilities

Suppose after Back-Channel Logout:

~~~text
Session Registry:
    deletes mapping (iss, aud, sid) → session S123

Spring Session:
    invalidates session S123

OAuth2AuthorizedClientService:
    may still retain (company, user-123) → A0/R0
~~~

This is not necessarily a Back-Channel Logout handler bug. The token store has its own lifecycle.

### 17.1. Possible Cleanup Policies

| Policy | When Appropriate | What to Consider |
|---|---|---|
| Invalidate session only | App manages tokens per session and session data is cleaned properly | Tokens in a separate service may remain |
| Delete authorized client by principal | Tokens need not persist after logout; one principal has one authorization state | May affect other active sessions |
| Delete per session/device | Need exact per-session logout across independent devices | Storage key design must support per-session scoping |
| Revoke refresh token at OP | Must prevent minting new access tokens after logout | OP needs token revocation endpoint/policy |
| Revoke/block access token | App requires near-instant API blocking | Self-contained JWTs remain valid if API checks only signature/exp |

**Back-Channel Logout does not automatically guarantee issued access tokens are revoked across all Resource Servers.**

### 17.2. Single-Session Logout vs Multiple Sessions for One Principal

If a Logout Token carries `sid` A, one specific session may need termination. Yet default <code>OAuth2AuthorizedClientService</code> typically keys by <code>(registrationId, principalName)</code>, which may be **one token record shared across multiple sessions**.

Deleting the entire record by principal when logging out one `sid` can break remaining sessions; keeping it may retain refresh tokens after logout. Decide explicitly between **session-scoped** vs **principal-scoped authorization** and design storage/cleanup accordingly.

### 17.3. Never Use a Logout Token as an Access Token

A Logout Token has the OIDC Client as audience and a logout event; it is not a Bearer access token for the Reports API. A Resource Server must never accept a Logout Token simply because it bears a valid OP signature.

Conversely, never let an access token with the same <code>sub</code> call the logout endpoint as a session termination command; the endpoint must enforce the full Logout Token profile.

## 18. Logout Lifecycle Across Multiple Issuers or Multiple `ClientRegistration`s

A portal might configure:

~~~text
registrationId=company-a, clientId=portal-a, issuer=https://op-a.example.org
registrationId=company-b, clientId=portal-b, issuer=https://op-b.example.org
~~~

OP A sends a Logout Token for <code>portal-a</code>. **Never** destroy a session simply because the same <code>sub=user-123</code> exists under OP B.

Correlation keys must rely on trusted values:

~~~text
issuer + audience/client + sid

or:

issuer + audience/client + subject
~~~

### 18.1. `registrationId` in the URL Is Not Enough Proof

The path:

~~~text
/logout/connect/back-channel/company-a
~~~

only helps the framework pick the matching `ClientRegistration`/validator. It **does not prove** the token came from OP A. An attacker can POST to that URL; signature and claims must still be verified.

### 18.2. Tokens with Multiple Audiences

OIDC JWT <code>aud</code> can be a string or an array of audiences per profile. The application must verify that the matching registration's Client ID appears in `aud` and enforce relevant rules as needed—never use arbitrary <code>aud</code> values to target sessions of other Clients.

### 18.3. Never Look Up Sessions by Email

An email can change or collide across systems. In OIDC, the pair <code>(iss, sub)</code> is a far more reliable identity key. Never log out all sessions by an email stated in an unverified JWT or request body.

## 19. Securing the Back-Channel Logout Endpoint

### 19.1. Verifying Signatures and Algorithms

When receiving a JWT:

- Trust only public signing keys of the registered issuer.
- Verify signatures using permitted algorithms; never accept <code>alg=none</code>.
- Look up <code>kid</code> in the JWK Set fetched from the trusted endpoint.
- Never fetch keys from attacker-supplied URLs via <code>jku</code>/<code>x5u</code> in token headers.
- Verify <code>iss</code>, <code>aud</code>, timestamps, and logout event.
- Distinguish Logout Tokens from ID Tokens/access tokens.

Never write code that Base64-decodes a JWT and reads <code>sub</code> without verifying the signature. An attacker could craft <code>sub=admin</code> to force mass logouts if the endpoint accepts unverified tokens.

### 19.2. Replay and `jti`

<code>jti</code> is the Logout Token's unique identifier. A replay defense can store:

~~~text
(issuer, audience, jti) → seenUntil=exp
~~~

with bounded TTL and appropriate multi-instance storage.

Per spec, checking previously seen <code>jti</code> values is an **optional** check, yet applications with strict replay requirements should design it explicitly.

Do not track `jti` solely in a per-node in-memory variable and consider that distributed replay protection. Every node must enforce it consistently when policy requires.

Repeated logout events can be handled idempotently (if the session is already gone, do not touch other sessions); verify HTTP response policies for duplicates with the OP to prevent retry loops.

### 19.3. Protecting Against Request Floods

The back-channel endpoint may be callable repeatedly, both by valid OPs and untrusted sources. Apply:

- Rate limits and bounded input sizes.
- HTTP timeouts for verification/JWKS lookups/session stores.
- Standard HTTPS/TLS connections.
- Sanitized metadata logging.
- Alerts on spikes in signature failures or bad requests.
- Disallow arbitrary JSON bodies replacing form <code>logout_token</code> outside agreed profiles.

IP allowlists or mTLS between OP and RP can **add** defense-in-depth if integration allows, yet never replace signature/claims validation.

### 19.4. Never Expose a "Log Out Any User" Endpoint

A controller like:

~~~java
@PostMapping("/admin/logout-user")
void logout(@RequestParam String subject) {
    // Find and delete all sessions of the caller-supplied subject
}
~~~

is not an OIDC Back-Channel Logout implementation. It lacks issuer/audience/event/signature validation and opens denial-of-service or business-logic session hijacking risks.

If you genuinely must hand-write an endpoint because your version lacks support, enforce the **full validation specification**, identity partitioning, replay prevention where required, and a safe session registry.

## 20. HTTP Sessions, CSRF, and Cookies: Easily Confused Boundaries

### 20.1. Browsers Do Not Trigger Back-Channel Logout Directly

A browser might know the URL:

~~~text
https://portal.example.org/logout/connect/back-channel/company
~~~

yet simply POSTing a self-crafted <code>logout_token</code> string will not qualify for logout. The token must be signed by the trusted OP with valid claims.

Thus never use browser session cookies to authenticate OP back-channel calls. Browser cookies will not accompany server-to-server requests.

### 20.2. CSRF Is Still Needed for Browser Routes

A Servlet or WebFlux app logging in with session cookies still has browser POST/PUT/DELETE endpoints requiring CSRF protection. Never disable CSRF globally just to make Back-Channel Logout work.

If an older back-channel handler version needs an internal POST to <code>/logout</code> with cookies/CSRF tokens, configure per that version's docs or upgrade to a newer handler supporting the clean pattern. Never skip token/logout checks for coding convenience.

### 20.3. `SameSite` Does Not Govern OP POSTs to RP

Cookie `SameSite` controls whether browsers send cookies on cross-site requests. Since the OP sends back-channel POSTs directly, it **does not depend on browser cookies**. Still, session cookie/CSRF configuration remains relevant for internal logout performed by Spring Security depending on implementation.

### 20.4. Session Event Cleanup

In Servlet, <code>HttpSessionEventPublisher</code> ensures the registry is notified when sessions are invalidated/expired by the servlet container lifecycle. With Spring Session Redis, verify event propagation/expiry behavior in the session store and compatibility with your Spring Security version.

If a session already expired while the registry still holds a mapping, the OP might send logout for a nonexistent session. Cleanup should be idempotent with an appropriate TTL and never recreate expired sessions.

## 21. Multi-Instance Deployment Architecture

Example architecture:

~~~text
                       OpenID Provider
                              |
                    POST logout_token JWT
                              |
                       Load Balancer
                         /       \
                  Instance A   Instance B
                   (Servlet)    (Servlet)
                       |          |
             Shared OidcSessionRegistry (Redis/DB)
                       |          |
                Shared Spring Session Store
                       |          |
             Optional Authorized Client Store
~~~

A login on A must write a mapping discoverable by B. When the OP sends a Logout Token to B, B must:

1. Validate the Logout Token against the right issuer/client.
2. Locate session(s) from the shared registry.
3. Invalidate the session in the shared store.
4. Delete logged-out mappings.
5. Apply token cleanup per policy.

### 21.1. Redis Sessions Do Not Equal a Shared `OidcSessionRegistry`

This is a critical deployment pitfall:

~~~text
Spring Session Redis: enabled
OidcSessionRegistry: default in-memory on each node
~~~

Login and callbacks work across all nodes, yet a logout token hitting another node cannot find the mapping to destroy the session.

In multi-instance systems, evaluate a custom shared registry and verify storage atomicity/TTL. Never test only login and declare Back-Channel Logout working in a cluster.

### 21.2. Rolling Deployments

When Instance A runs v1 and B runs v2, ensure:

- Compatible session serialization formats.
- Compatible OIDC session registry schemas.
- Consistent registration IDs and issuer/client IDs.
- Compatible handler cookie names and internal `logoutUri`.
- No unexpected token validation shifts across minor versions.
- No loss of OP `sid` ↔ RP session mappings during rollouts.

If a custom registry is unversioned, a rolling upgrade can leave B unable to read mappings written by A, causing silent logout failures.

### 21.3. When the Session Store Loses Connectivity

If a valid Logout Token arrives during a Redis/DB session store outage, the application must never pretend session invalidation succeeded.

Define an explicit policy:

- Return an appropriate transient error so the OP can retry per contract.
- Record status/alerts if using a queue/reliable event store.
- Never expose sensitive user/session details in responses.
- Ensure retries do not create new sessions or delete wrong data.
- Bound retries and add reconciliation if the OP does not retry.

There is no automatic "exactly-once logout" between OP and RP. Design **at-least-once delivery + idempotent handling** when high fault tolerance is required.

## 22. OP and Spring Security Configurations Must Align

Deployment checklist:

| Side | Configuration That Must Align |
|---|---|
| OP | <code>backchannel_logout_supported</code> and real capability |
| OP | Registered RP <code>backchannel_logout_uri</code> |
| OP | Whether <code>sid</code> is sent, matching Client <code>backchannel_logout_session_required</code> |
| RP | Correct registration ID in endpoint path |
| RP | Correct Issuer, Client ID/audience, and JWK verification |
| RP | <code>oidcLogout().backChannel()</code> DSL matching stack/version |
| RP | Appropriate handler and exact cookie name |
| RP | Session mapping registry exists and is shared as needed |
| RP | HTTP session/`WebSession` store operational |
| RP | Token storage and cleanup/revocation per policy |
| Network | OP can actually reach URI with valid TLS and proxy routing |

### 22.1. Registering the Client at the OP Does Not Configure the Framework

Declaring <code>backchannel_logout_uri</code> at the OP does not add filters in Spring Security. You must enable the feature on the RP and ensure proper endpoint routing.

### 22.2. Enabling the DSL at the RP Does Not Register with the OP

Conversely, enabling <code>oidcLogout(...).backChannel(...)</code> does not make every OP automatically call the endpoint. The OP must support it and know the exact URI.

### 22.3. Testing with Real Events

Logging in at the Client, logging out at the OP/another app, and observing subsequent requests to the Client is far more meaningful end-to-end verification than merely checking an endpoint returns 200 on a request lacking a valid JWT.

## 23. Testing Back-Channel Logout

### 23.1. Minimum Protocol Tests Required

| Scenario | Expectation |
|---|---|
| Logout Token validly signed by OP, matching issuer/audience | Terminates matching session |
| Logout Token missing signature or bad signature | Reject |
| JWT using <code>alg=none</code> | Reject |
| Wrong <code>iss</code> | Reject |
| <code>aud</code> missing exact Client ID | Reject |
| Missing/wrong event URI in <code>events</code> | Reject |
| Contains <code>nonce</code> | Reject |
| Missing both <code>sub</code> and <code>sid</code> | Reject |
| Expired token | Reject |
| Duplicate <code>jti</code> | Per designed replay/idempotency policy |
| <code>sid</code> of Session X | Does not accidentally kill Session Y |
| <code>sub</code> only | Terminates matching subject sessions within issuer/client scope |
| Valid token for Client A sent to Client B endpoint | Does not kill B's sessions |
| Repeated request after session already ended | Idempotent, does not recreate session |
| OP POST hits a different node from login node | Still kills session when registry/store are shared |
| Redis/DB outage | Never reports false success; safe error/retry handling |

### 23.2. Do Not Confuse "Mock OIDC Login" with Testing Logout Tokens

Spring Security Test can simulate an authenticated <code>OidcUser</code> via <code>mockOidcLogin()</code> (Reactive) or mock OAuth2/OIDC login per stack. Those tests are useful for authorization rules, yet **do not test**:

- Whether the OP signs Logout Tokens properly.
- Whether the Logout Token decoder validates issuer/audience/events/nonce.
- Whether the session registry holds accurate mappings.
- Whether the back-channel handler invalidates sessions on another node.

For back-channel tests, use **dedicated test OP/key material** and issue JWTs properly signed per profile—never just drop <code>sub</code> into a dummy string and expect the framework to accept it.

### 23.3. Two-Node Integration Scenario

1. Start Instances A and B with compatible versions/configs.
2. Use a Redis shared session store.
3. Use a shared <code>OidcSessionRegistry</code> or reactive counterpart.
4. Log a user in on A; confirm the Client session is created by checking safe metadata.
5. Send a valid Logout Token from the test OP to the endpoint **on B**.
6. Verify subsequent requests with the old cookie are no longer authenticated.
7. Verify other sessions with different <code>sid</code> values stay active under `sid`-based logout policy.
8. Repeat the logout request to verify idempotency.
9. Test the endpoint when the cookie name is <code>SESSION</code> rather than <code>JSESSIONID</code>.
10. Inspect post-logout token/registry records per retention policy.

### 23.4. Manual HTTP Tests Only Matter with Real Tokens from a Test OP

Example request:

~~~bash
curl --request POST \
  --url 'https://portal.example.org/logout/connect/back-channel/company' \
  --header 'Content-Type: application/x-www-form-urlencoded' \
  --data-urlencode 'logout_token=SIGNED_LOGOUT_TOKEN_FROM_TEST_OP'
~~~

The placeholder string above **is not a valid JWT**, so rejecting it is expected behavior. Testing success requires an OP/test fixture signing Logout Tokens with a key matching the issuer trusted by the RP.

Never use production private keys to build test fixtures in unauthorized environments. Never paste production Logout Tokens into public JWT decoder websites or shared console logs.

## 24. Troubleshooting by Symptom

| Symptom | Possible Cause | Resolution |
|---|---|---|
| OP never calls endpoint | URI unregistered, feature disabled, OP unsupported | Check metadata and Client settings |
| OP reports URI unreachable | DNS, firewall, TLS, reverse proxy | Check network/TLS/ingress |
| Endpoint 404 | Wrong path/registration ID, DSL disabled, chain mismatch | Check URL and stack/version |
| Endpoint 401 | API chain demands Bearer token, Back-Channel filter bypassed | Select right `SecurityFilterChain` |
| Endpoint 403 | CSRF or internal logout handler/cookie mismatch | Check version DSL/handler; do not disable CSRF globally |
| Logout Token returns 400 | Bad signature/issuer/audience/exp/events/nonce/sub/sid | Validate against spec and OP metadata |
| OP logs out yet Client session stays alive | Registry lacks mapping or session store cannot destroy | Check registry/session lookup |
| Only logs out on Node A | In-memory registry on A | Share OIDC session registry |
| HTTP session in Redis yet logout has no effect | Only sessions shared, OIDC registry still local | Configure shared registry as well |
| Handler cannot find session | Cookie name <code>JSESSIONID</code> vs <code>SESSION</code> | Configure exact <code>setSessionCookieName</code> |
| Logging out `sid` A affects another user/session | Wrong registry key missing issuer/audience/sid | Fix multi-tenant mapping and validation |
| Logout without `sid` drops all user sessions | Likely `sub`-based logout semantics | Verify policy and OP `sid` support |
| Session invalidated yet API accepts access token | Token/Resource Server has separate lifecycle | Check revoke/expiry/introspection and token cleanup |
| Errors during rolling deploy | Incompatible serializer/registry schema | Check versions and migrations |
| Duplicate logouts after timeout | OP retries / RP handling not idempotent | Replay/idempotency policy |
| Missing <code>OidcBackChannelLogoutHandler</code> class | Project uses different Spring Security version than docs | Check dependencies and exact docs |
| Reactive bean/type mismatch | Using Servlet handler in WebFlux | Use reactive handler/registry |
| Token with `nonce` was accepted | Validator missing Logout Token checks | Fix validator; `nonce` is prohibited |

### 24.1. Recommended Investigation Flow

~~~text
User logs out at OP
   |
   v
Does OP support Back-Channel Logout and have RP URI registered?
   |-- No --> Enable/register OP capability
   |
   v
Did OP send POST to RP and did network deliver it?
   |-- No --> DNS/TLS/firewall/ingress
   |
   v
Did POST hit the right Spring Security chain and endpoint?
   |-- No --> Matcher/order/version/URI
   |
   v
Was the Logout Token JWT validated?
   |-- No --> iss/aud/alg/exp/iat/events/sub/sid/nonce
   |
   v
Did OidcSessionRegistry find the Client session?
   |-- No --> Shared registry/mapping/TTL/tenant
   |
   v
Was HttpSession/WebSession invalidated?
   |-- No --> Handler/cookie name/session store/CSRF
   |
   v
Are subsequent requests still authenticated?
   |-- Yes --> Session restore, cache, alternate auth path
   |
   v
Do token cleanup and revocation follow policy?
~~~

## 25. Operations, Observability, and Reliability Controls

### 25.1. Recommended Metrics

| Metric / Log Field | Meaning |
|---|---|
| <code>oidc_backchannel_request_total</code> | Requests from OP to endpoint |
| <code>oidc_backchannel_validation_failure_total{reason}</code> | Signature, issuer, audience, event, expiry failures, etc. |
| <code>oidc_backchannel_session_match_count</code> | Sessions matched by `sid`/`sub` |
| <code>oidc_backchannel_session_invalidate_total</code> | Sessions invalidated |
| <code>oidc_backchannel_registry_lookup_latency</code> | Shared registry latency |
| <code>oidc_backchannel_session_store_failure_total</code> | Redis/DB/session repository errors |
| <code>oidc_backchannel_duplicate_jti_total</code> | Duplicate events when replay cache exists |
| <code>oidc_backchannel_response_status_total</code> | Track statuses returned to OP |
| <code>oidc_backchannel_unknown_registration_total</code> | Requests with nonexistent registration IDs |

Never put raw <code>logout_token</code>, session cookies, unsanitized <code>sub</code>, access/refresh tokens, or private keys into logs/metrics. Avoid using raw principals or <code>jti</code> as high-cardinality metric labels.

### 25.2. Correlation

You may record:

~~~text
registrationId=company
issuerAlias=company-idp
logoutTokenValidation=success
eventKind=backchannel-logout
sessionMatchCount=1
sessionInvalidation=success
processingMillis=47
requestCorrelationId=...
~~~

Never log full JWT payloads just to see <code>sid</code>; use an internal hashed/truncated identifier per policy if investigation truly needs it.

### 25.3. Bounded Retries and OP Responses

If the RP receives a valid Logout Token yet cannot write to the shared session store, define clear retry/queue and failure-response policies. If the OP does not retry, add stale-session reconciliation or bounded session TTLs.

Avoid designing a logout request that processes unbounded numbers of sessions without time limits, risking exhaustion when a subject holds many sessions.

## 26. When Your Version or OP Does Not Support Back-Channel Logout

Never promise this feature is available in **every Spring Security version** or **every OpenID Provider**.

### 26.1. If Spring Security Is Older Than 6.2

Three options:

1. **Upgrade Spring Security/Spring Boot** to a supported line providing the Back-Channel Logout API; review migration and compatibility.
2. If upgrading is impossible, **implement per the OIDC Back-Channel Logout spec** with a JWT-validating endpoint, trust anchors, registry, and session invalidation under strict security testing.
3. Use **RP-Initiated Logout, short session TTLs, and reauthentication policies** when they satisfy the use case; accept they are not fully equivalent to OP-initiated Back-Channel Logout.

Never use a public <code>GET /logout?sub=...</code> as a workaround.

### 26.2. If the OP Does Not Support Back-Channel

The app cannot invent reliable OP→RP notifications purely through Spring Security changes. Coordinate with the OP vendor or evaluate alternatives:

- RP-Initiated Logout when users log out at the app itself.
- Front-Channel Logout if supported by the OP, accounting for browser limitations.
- Short session lifetimes and reauthentication for sensitive actions.
- A proprietary security event mechanism **officially provided, verified, and contract-tested** by the OP system.

Do not treat polling <code>UserInfo</code> or repeatedly attempting refresh tokens as a full substitute for Back-Channel Logout.

### 26.3. What If You Only Need Token Revocation Without Session Logout?

Token Revocation (RFC 7009) is a distinct capability. You can revoke a refresh token without OIDC Back-Channel Logout; conversely, you can receive Back-Channel Logout and invalidate a browser session while already-issued access tokens survive until expiration.

Define the product objective clearly: **preventing reuse of the portal session**, **preventing refresh tokens from minting new access tokens**, or **preventing Resource Servers from accepting access tokens immediately**. Each objective has its own technical layer and policy.

## 27. Practice Exercises

### Exercise 1 — Distinguishing Two Logout Directions

A browser in Portal A clicks "Log Out," and Portal A redirects to <code>end_session_endpoint</code>.

**Question:** Is this Back-Channel Logout?

**Answer:** No. This is RP-Initiated Logout. Back-Channel Logout occurs when the OP proactively sends an HTTP POST Logout Token to the RP/Client.

### Exercise 2 — User Closes the Browser Tab

The user already closed Portal A's tab and then logged out of the OP via Portal B.

**Question:** Does Back-Channel Logout require Portal A's tab to remain open?

**Answer:** No. The OP sends a server-to-server notification, so it can still ask Portal A to invalidate the session if the endpoint and session mapping remain valid.

### Exercise 3 — `sub` and `sid`

The OP sends a Logout Token with <code>sid=op-sid-1</code>; the user has two mapped sessions <code>op-sid-1</code> and <code>op-sid-2</code>.

**Question:** Should both be destroyed?

**Answer:** With `sid`-based logout, destroy only Client sessions correlated to that exact `sid` within the issuer/audience scope. Never expand arbitrarily to another `sid`.

### Exercise 4 — Logout Token Without `sid`

A Logout Token has <code>iss</code>, <code>aud</code>, <code>sub=user-123</code>, yet no <code>sid</code>.

**Question:** What is the effect?

**Answer:** When permitted by Client/OP policy and the token is valid, log out all Client sessions of the End-User identified by <code>iss + sub</code> within the matching audience/registration, not just one browser session.

### Exercise 5 — `nonce` in a Logout Token

A properly signed token containing a <code>nonce</code> claim arrives at the back-channel endpoint.

**Question:** Should it be accepted?

**Answer:** No. Logout Tokens must not contain <code>nonce</code> per the OIDC Back-Channel Logout spec.

### Exercise 6 — Wrong Audience

A token is validly signed by OP A, yet <code>aud=another-client</code>; the endpoint is <code>/logout/connect/back-channel/company</code> with Client ID <code>portal-web</code>.

**Question:** Should the user be logged out?

**Answer:** No. The JWT is not meant for this Client. The registration ID in the URL path does not replace audience verification.

### Exercise 7 — Redis Sessions with a Local Registry

Instance A handles login and stores the OIDC registry in memory; HTTP sessions are shared in Redis. The OP sends a Logout Token to B.

**Question:** What can happen?

**Answer:** B can verify the token yet has no idea which Client session ID the OP's `sid`/`sub` points to. A shared OIDC session registry is required, not only shared HTTP sessions.

### Exercise 8 — `JSESSIONID` vs `SESSION` Cookie

The app switches to Spring Session and browsers use the <code>SESSION</code> cookie, yet the OIDC session logout handler still assumes the cookie is <code>JSESSIONID</code>.

**Question:** What should be checked?

**Answer:** Check the handler's session cookie name, use <code>setSessionCookieName("SESSION")</code> where the version provides that API, and verify shared session/registry and internal logout routing.

### Exercise 9 — Logging the JWT

The operations team wants to log the entire Logout Token and cookies to investigate 400 errors.

**Question:** Is that safe?

**Answer:** No. These are sensitive credentials/security event data. Log only sanitized metadata, error codes, and correlation IDs; never log raw JWTs or cookies.

### Exercise 10 — Session Destroyed Yet API Accepts Access Token

Back-Channel Logout succeeds and Portal's browser session is invalidated. The Resource Server still accepts an unexpired JWT access token.

**Question:** Does that mean Back-Channel Logout failed?

**Answer:** Not necessarily. Session invalidation and access token revocation are two independent mechanisms. Dedicated revocation/introspection/short-lived token policies or API authorization checks are needed for immediate blocking.

### Exercise 11 — Wrong Stack

A WebFlux project uses <code>SecurityWebFilterChain</code>, yet the developer injected Servlet's <code>OidcBackChannelLogoutHandler</code>.

**Question:** How to fix?

**Answer:** Use the reactive handler <code>OidcBackChannelServerLogoutHandler</code> and <code>ReactiveOidcSessionRegistry</code> per your API version instead of mixing Servlet and Reactive components.

### Exercise 12 — Version Analysis

A project runs Spring Security 6.1 and a developer copies:

~~~java
http.oidcLogout(oidc -> oidc.backChannel(
    Customizer.withDefaults()));
~~~

**Question:** Why might it fail to compile?

**Answer:** The built-in Back-Channel Logout DSL was introduced in Spring Security 6.2. Check your active version, upgrade, or implement the protocol compatibly rather than copying newer APIs onto an older classpath.

### Exercise 13 — Full Integration Across Two Replicas

Design:

1. An OIDC `ClientRegistration` with trusted issuer/client ID.
2. OP Back-Channel Logout enabled and public <code>backchannel_logout_uri</code> registered.
3. `SecurityFilterChain` or `SecurityWebFilterChain` with <code>oauth2Login()</code> and version-accurate <code>oidcLogout().backChannel()</code> DSL.
4. Handler matching stack and cookie name.
5. Shared session store alongside shared <code>OidcSessionRegistry</code> or reactive counterpart.
6. Session mapping partitioned by issuer/audience/subject/sid.
7. Full JWT validation and <code>jti</code>/replay policy.
8. Token cleanup/revocation per product requirements.
9. HTTP response/retry/idempotency behavior for the OP.
10. Cross-node callback tests with OP Logout Tokens hitting a different node.

Explain what happens when the OP sends a valid token during a Redis outage, and why processing cannot be reported as successful while the session stays active.

## 28. Summary

- OIDC **Back-Channel Logout** enables an **OpenID Provider to proactively send a JWT Logout Token** to the Client via HTTP POST, independent of open browser tabs.
- The Logout Token must be validated against the **exact logout profile**, including signature, issuer, audience, timestamps, event URI, <code>sid</code>/<code>sub</code>, and **no `nonce`**. <code>exp</code> is mandatory under the spec incorporating errata set 1.
- Back-Channel Logout passes <code>logout_token</code> in the form body—not an access token, ID Token, or refresh token.
- Spring Security provides the <code>oidcLogout(...).backChannel(...)</code> DSL in **Servlet and Reactive starting from 6.2**, though handlers and internal logout URLs can vary across patch/minor versions.
- Servlet uses <code>OidcSessionRegistry</code>/<code>OidcBackChannelLogoutHandler</code>; WebFlux uses <code>ReactiveOidcSessionRegistry</code>/<code>OidcBackChannelServerLogoutHandler</code> in supported versions.
- The default endpoint is typically <code>/logout/connect/back-channel/{registrationId}</code>, yet **the OP must register the public URI** and be able to reach it.
- When a Logout Token carries <code>sid</code>, log out by OP session; when only <code>sub</code> is present, log out all matching Client sessions for that subject within the issuer/audience scope.
- **Spring Session Redis does not automatically synchronize the OIDC session registry if the registry remains in-memory.** Multi-instance deployments must share both the session store and OP↔RP session mappings.
- Check <code>JSESSIONID</code> vs <code>SESSION</code> cookie names when using Spring Session; the handler must know the exact session cookie to invalidate sessions.
- Never disable CSRF app-wide or allow logout by unverified <code>sub</code>. Pay attention to multiple `SecurityFilterChain`s, issuer/audience boundaries, and replays.
- Back-Channel Logout **does not automatically revoke access/refresh tokens** at the Authorization Server or Resource Server. Session cleanup, authorized-client storage, and token revocation policies must be designed separately.
- Real tests must cover **valid/invalid JWTs**, right/wrong clients, multiple sessions, multiple nodes, session store outages, and rollback/retention; working login does not prove logout works.

### References

- **OpenID Connect Back-Channel Logout 1.0 incorporating errata set 1** — defines Logout Tokens, metadata, HTTP POST, and JWT validation: https://openid.net/specs/openid-connect-backchannel-1_0.html
- **OpenID Connect Back-Channel Logout 1.0 final (2022)** — pre-errata edition; note claim differences when comparing older docs: https://openid.net/specs/openid-connect-backchannel-1_0-final.html
- **Spring Security Reference — OIDC Logout, Servlet** — Back-Channel Logout DSL, `OidcSessionRegistry`, handler, and cookie name: https://docs.spring.io/spring-security/reference/servlet/oauth2/login/logout.html
- **Spring Security Reference — OIDC Logout, Reactive** — `ServerHttpSecurity`, `ReactiveOidcSessionRegistry`, reactive handler: https://docs.spring.io/spring-security/reference/reactive/oauth2/login/logout.html
- **Spring Security API — `OidcLogoutConfigurer.BackChannelLogoutConfigurer`** — verify availability and version of <code>logoutUri</code>: https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/config/annotation/web/configurers/oauth2/client/OidcLogoutConfigurer.BackChannelLogoutConfigurer.html
- **Spring Security Reference — Session Management and Logout** — HTTP session invalidation and logout handlers.
- **Spring Session Reference — Redis HTTP Session/WebSession** — sharing sessions across multiple instances.
- **OpenID Connect Core 1.0** — ID Token, <code>iss</code>, <code>sub</code>, <code>sid</code> in related profiles.
- **OpenID Connect RP-Initiated Logout 1.0** — Client-initiated logout mechanism, distinct from Back-Channel Logout.
- **RFC 7009 — OAuth 2.0 Token Revocation** — token revocation, not equivalent to local session destruction.
- **RFC 7519 — JSON Web Token (JWT)** and **RFC 8417 — Security Event Token** — JWT claims and security event semantics.
