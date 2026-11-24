# Limitations of SLO When Users Have Multiple Applications, Devices, or Sessions

**SAML 2.0 Single Logout (SLO)** is a logout coordination mechanism between an Identity Provider (IdP/Asserting Party) and Service Providers (SP/Relying Party) participating in a federated login context. SLO helps terminate related sessions, yet **is not a "log out of every application, browser, device, and token" button with guaranteed outcomes**.

When a user simultaneously uses Portal, HRM, and CRM across desktop, phone, and another browser, multiple independent session layers can exist. A `LogoutRequest` typically ties to a **NameID** and may specify a **SessionIndex** for one IdP session context. An SLO flow can complete at the IdP while sessions still remain at non-participating SPs, on other devices, in OAuth/OIDC apps, or in tabs that did not receive notifications properly.

**Most important message:** clearly distinguish **"logging out of the current application"**, **"SLO for participants sharing an IdP session"**, and **"revoking all sessions/tokens of an account across all devices"**. These are three different goals in protocol, observability, assurance level, and system design. This lesson belongs to **Spring Security – federation → SAML2 Logout**, focusing on limitations, Spring Security configuration, testing, and operational measures.

## 1. What Is SLO and What Problem Does It Solve?

In **SAML Web Browser SSO**, a user can access App A and App B after authenticating once at the IdP. Each application still establishes its own **local session** to protect subsequent requests. When logging out of one application, clearing only that app's cookie/HttpSession can leave the IdP session and App B alive.

SLO adds protocol messages to coordinate ending sessions:

| Element | Role |
| --- | --- |
| `samlp:LogoutRequest` | Requests terminating SAML sessions for the relevant subject/SessionIndex |
| `samlp:LogoutResponse` | Replies with the processing result of the logout request |
| `saml:NameID` | Identifies the subject in the federation per agreed format/scope |
| `samlp:SessionIndex` | Specifies one or more SAML sessions to terminate per profile rules |
| `SingleLogoutService` in metadata | Endpoint/binding supported by the partner to receive logout messages |
| XML signature or binding signature | Enables verifying the message came from the trusted partner |

SLO is an **optional** feature in the SAML ecosystem; not every IdP/SP supports it or supports every binding. Both parties supporting **SAML SSO** does not imply they also support **SAML SLO**.

**SLO does not issue arbitrary delete-cookie commands across all websites.** Cookies belong to distinct domains and server-side sessions belong to each application's own control. SLO relies on each participant receiving, verifying, and executing valid requests.

## 2. Three State Layers to Distinguish

A user can simultaneously hold the following types of state:

| Layer | Example | Who Controls It? | Does SLO Manage It Directly? |
| --- | --- | --- | --- |
| **IdP SSO session** | Cookie/session at `login.example.test` | IdP | IdP can end sessions within the logout scope |
| **SP local web session** | `JSESSIONID`, Spring SecurityContext at Portal | Each SP | SP must perform local logout upon receiving a valid message |
| **Additional SP app state** | Redis session, remember-me token, WebSocket, backend state | SP | Not auto-deleted unless logout handlers/design handle it |
| **Other apps' sessions** | HRM, CRM, Wiki | Each participant | Only when receiving and handling SLO properly |
| **Sessions on other devices** | Phone, separate browser, private window | IdP and each SP | Not by default under the same SessionIndex/context |
| **API access token/JWT** | Bearer token issued to mobile/API | Authorization server/resource server | SAML SLO does not auto-revoke standalone JWTs |
| **OAuth/OIDC refresh token** | App session refresh token | Authorization server | Needs dedicated revocation/expiration/back-channel |
| **Client cache/offline data** | LocalStorage, service worker cache, downloaded app data | Browser/app | Not auto-cleared by SLO |

Logout outcomes should be reported by layer—for example **"Logged out of Portal"** and **"Sent federated logout request; some applications may still remain open"**—instead of asserting **"You have been logged out of all devices"** without evidence.

## 3. RP-Initiated and AP-Initiated SLO

### 3.1. RP-Initiated: Request Sent from App to IdP

The user clicks Log Out in Portal (SP). If Portal is configured to participate in SLO, Spring Security executes local logout and builds a **signed LogoutRequest** to the IdP. The IdP verifies the request, handles its session, and may propagate logout to other SPs sharing the session. Then the IdP may send a **LogoutResponse** back.

~~~text
Browser             Portal/SP             IdP               HRM/SP
   |                   |                   |                    |
   | POST /logout      |                   |                    |
   +------------------>|                   |                    |
   |               Local logout            |                    |
   |                   |---- LogoutRequest>|                    |
   |                   |                   |-- LogoutRequest -->|
   |                   |                   |             Local logout?
   |                   |                   |<-- LogoutResponse--|
   |                   |<-- LogoutResponse-|                    |
   |<-- outcome -------|                   |                    |
~~~

**Limitation:** HRM is logged out only if the IdP knows it is a participant of the **matching context**, HRM's SLO is registered/permitted, the request reaches HRM, and HRM executes it properly. If the browser closes, network drops, or one side rejects, the logout chain can stop partway.

### 3.2. AP-Initiated: IdP Requests Application Logout

The IdP can proactively send a **LogoutRequest** to Portal when the user clicks Sign out at the IdP or when IdP policy ends the session. Portal must verify the message (right issuer/registration, signature, timestamps, destination, replay, and matching conditions), destroy the related local session, and return a **LogoutResponse**.

~~~text
IdP                  Browser                 Portal/SP
 |                      |                        |
 |---- LogoutRequest -->|---- LogoutRequest ---->|
 |                      |             verify + local logout
 |<--- LogoutResponse --|<--- LogoutResponse ----|
 |                      |                        |
~~~

**Limitation:** "IdP sent it" does not prove the SP received it. If the request travels front-channel yet the browser fails to load the endpoint or lacks the right cookie, the exact SP session to destroy may not be found. Spring Security provides SAML logout filters/validators, yet does not inherently have authority to delete all other sessions of the same account across devices.

### 3.3. Local-Only Logout

If the user only calls the local logout endpoint, Spring may delete the Portal session **without sending a LogoutRequest to the IdP**. Re-logging into Portal right afterward can happen almost instantaneously because the IdP SSO cookie persists; this is not proof of broken logout code, but the consequence of SP-only logout scope.

## 4. Why Do Multiple Applications Make SLO Completion Uncertain?

An IdP may know Portal and HRM as two **session participants**, yet in practice they do not necessarily both support SLO. For example:

| Application | Login Mechanism | Logout Mechanism | When Portal Initiates SLO |
| --- | --- | --- | --- |
| Portal | SAML SSO | SAML SLO and local session | Portal can destroy its current session |
| HRM | SAML SSO | Properly configured SAML SLO | IdP can ask HRM to destroy related session |
| CRM | SAML SSO | Local logout only | IdP may have no way to coordinate ending CRM |
| BI | OIDC Login | Separate OIDC logout | Does not automatically receive SAML LogoutRequest |
| API | OAuth2 JWT | Token TTL/revocation | SAML SLO does not invalidate JWTs automatically |

**Sharing one IdP does not mean all applications share one session store.** In real systems, apps can live across different domains, platforms, protocols, and operational owners.

OASIS describes SLO as a mechanism to log out of participants near-simultaneously, while noting browser-based flows can be interrupted by users so **there is no absolute guarantee every participant was visited**. Products must therefore distinguish **SLO initiated**, **SLO answered by IdP**, **SPs confirming completion**, and **actual evidence across all sessions**.

### A Common Scenario

A user opens Portal and HRM in the same browser. Portal receives `LogoutResponse` from the IdP and displays "Logged out". If HRM was offline when the IdP forwarded the request, HRM's local session may still persist. Seeing "Success" in one protocol step **is not independent proof** that every session in every app was destroyed. The IdP may reply with **`PartialLogout`** when it could not deliver messages to all participants.

## 5. Multiple Devices: Same Account Does Not Mean Same IdP Session

Suppose a user works across three environments:

~~~text
Account: user@example.test
     |
     +-- Laptop / Chrome -- IdP session S1
     |        +-- Portal session P1
     |        +-- HRM session H1
     |
     +-- Laptop / Firefox -- IdP session S2
     |        +-- Portal session P2
     |
     +-- Phone -- IdP session S3
              +-- Portal session P3
              +-- Mobile API refresh token R3
~~~

When Chrome on the laptop initiates SLO, **S1** may be the session requested to close. **S2** and **S3** are separate IdP sessions and may fall outside S1's LogoutRequest scope; Portal sessions **P2**, **P3**, and refresh token **R3** are not automatically revoked.

The outcome depends on the IdP vendor: some IdPs offer a dedicated **logout all devices/sessions** capability that can ask downstream apps to end related sessions; others only end the current session. You cannot infer from the name "Single Logout" that the IdP always performs account-wide logout.

**Security point:** for "lock compromised account" or "employee offboarding" requirements, running SAML SLO alone is **insufficient** to guarantee all devices are blocked. You need policies to revoke all IdP sessions, SP sessions, refresh tokens/API credentials, and enforce backend authorization checks.

## 6. Multiple Tabs and Windows in the Same Browser

Two tabs on the same origin usually share the session cookie. If Portal deletes the server-side HttpSession, requests from the other tab will no longer have a valid session, even though that tab's UI still displays previously rendered data. This means:

- **New server-side accesses** must be denied or redirected to login once the session expires.
- **Already-rendered data** in the old tab does not vanish merely because the server destroyed the session.
- **Frontend state** in memory, localStorage, IndexedDB, or caches may remain unless the app actively clears it.
- **WebSockets/SSE** may remain open unless closing channels is tied to session invalidation.

Good UX can use cross-tab signaling like `BroadcastChannel` or storage events (frontend) to refresh UI promptly when one tab logs out. Yet those signals **only assist UI** and do not replace server-side session and authorization checks.

If the browser is closed or blocks cookies during an SLO flow, front-channel propagation can stop. Do not treat **no LogoutResponse callback** as proof that all sessions were destroyed or untouched; distinguish local state from federated state.

## 7. SessionIndex: Session Scope, Not a Command to Wipe All Devices

In SAML, an `AuthnStatement` may include `SessionIndex`; IdP and SP use it to correlate SSO sessions. A `LogoutRequest` typically carries `NameID` and one or more `SessionIndex` values to identify which sessions to terminate.

~~~xml
<samlp:LogoutRequest
    xmlns:samlp="urn:oasis:names:tc:SAML:2.0:protocol"
    xmlns:saml="urn:oasis:names:tc:SAML:2.0:assertion"
    ID="_logout-unique-id"
    Version="2.0"
    IssueInstant="2026-11-07T10:30:00Z"
    Destination="https://idp.example.test/slo">
  <saml:Issuer>https://portal.example.test/saml/sp</saml:Issuer>
  <saml:NameID>subject-example</saml:NameID>
  <samlp:SessionIndex>session-s1</samlp:SessionIndex>
</samlp:LogoutRequest>
~~~

**This is an illustrative XML fragment**, lacking digital signatures/binding encoding and not a usable LogoutRequest in production. `subject-example` and `session-s1` are sample values, not real user data.

Things to distinguish:

1. **NameID** ties to a subject in one federation relationship, not necessarily an email or global user ID.
2. **SessionIndex** relates to a session between subject and session authority; it is not `JSESSIONID`, a universal device UUID, or an API token ID.
3. **SP-initiated SLO under Web Browser SSO Profile** must supply a SessionIndex matching the received AuthnStatement. OASIS Errata E38 clarifies this rule. In **Core LogoutRequest** the element is optional, yet the applicable profile may mandate it.
4. **When a session authority/IdP initiates logout**, it may omit SessionIndex to instruct terminating all applicable sessions of the subject per profile. Exact scope still depends on subject identification and SP/IdP implementation.
5. One user can have multiple SessionIndexes across authentications, browsers, devices, or application contexts; never use a single index to conclude all sessions were revoked.
6. If the SP only knows one `HttpSession` in the current browser, it may lack a registry to locate and destroy all other `HttpSession` instances matching that subject/SessionIndex.

**Never take SessionIndex from a user-supplied URL** to destroy someone else's session. Only use data from verified assertions and validated SLO messages, scoped by issuer/registration.

## 8. Front-Channel and Back-Channel: Different Limits

SAML supports multiple bindings/flows for delivering logout messages. Two main concepts:

| Channel | How It Works | Benefits | Limitations |
| --- | --- | --- | --- |
| **Front-channel** | Browser hops across SLO endpoints via Redirect/POST | SP can see the current browser's session cookies | Closed tab, JS/CSP, cookies/SameSite, browser privacy, timeouts can interrupt |
| **Back-channel** | Server-to-server, e.g., SOAP profile per spec/vendor support | Does not depend on browser navigation chain after sending | SP must find the exact server session; backend/network/firewalls/compatibility, not available everywhere |
| **Provider-specific logout API** | IdP/SP uses proprietary API to revoke sessions | Can target devices/accounts per vendor capability | Not standard SAML SLO; needs dedicated integration, permissions, and auditing |

**Front-channel cannot delete another domain's cookies at will.** It requires the real browser to visit each domain/endpoint. `SameSite` cookies or third-party cookie settings affect which requests carry cookies. Some IdPs use iframes to coordinate; whether that works depends on browser policies and app configuration.

**Back-channel is not a silver bullet:** if the SP only ties session IDs to browser cookies and maintains no **(issuer, subject, SessionIndex) → session IDs** mapping, a server-to-server LogoutRequest may fail to locate the right local sessions. Never wipe every session sharing an email without checking subject and scope.

Spring Security 6.5 provides SAML2 SLO support over HTTP POST/Redirect in its documented default configuration. Do not assume that API automatically includes server-to-server SOAP orchestration for every profile or account-wide session revocation.

## 9. SLO Depends on Each Partner's Support and Metadata

For two parties to coordinate SLO, metadata must publish the right endpoints and bindings:

- **IdP metadata:** `IDPSSODescriptor` contains `SingleLogoutService` for LogoutRequests/LogoutResponses sent to the IdP.
- **SP metadata:** `SPSSODescriptor` contains `SingleLogoutService` so the IdP can send LogoutRequests to the SP.
- **SP signing credentials:** public cert trusted by the IdP, private key protected by the SP to sign messages when required.
- **IdP verification credentials:** SP uses the exact IdP certificates to verify LogoutRequests/Responses.
- **EntityIDs and URLs:** issuer, destination, response location, and base URL must match agreement.
- **Timestamp and replay policy:** stale or duplicate-ID messages are rejected.
- **Compatible binding:** Redirect/POST require proper signing/encoding and delivery.

For instance, if an IdP **does not publish `SingleLogoutService`** or lacks SLO support, enabling `.saml2Logout()` on the SP **does not make the IdP support it**. Check vendor docs, real metadata, and run integration tests. Some systems only support logging out the IdP session without propagating to all SPs; that is a different feature scope from full SLO.

**Never fix issues by** disabling XML signature verification on LogoutRequest/LogoutResponse, accepting any Issuer, or redirecting to a browser-chosen logout URL.

## 10. Spring Security: Components Involved in SLO

In a Servlet application, know these classes/configurations:

| Component | Role |
| --- | --- |
| `HttpSecurity.saml2Logout(...)` | Enables RP-initiated and AP-initiated SAML2 Logout per configuration |
| `RelyingPartyRegistration` | Holds SP/IdP entities, SLO endpoints, signing and verification credentials |
| `Saml2RelyingPartyInitiatedLogoutSuccessHandler` | Initiates the SP-started logout flow |
| `Saml2LogoutRequestResolver` | Builds, signs, and packages LogoutRequest |
| `Saml2LogoutRequestRepository` | Stores emitted requests to correlate LogoutResponse/RelayState/InResponseTo |
| `Saml2LogoutRequestFilter` | Handles and validates IdP requests (AP-initiated) |
| `Saml2LogoutResponseFilter` | Handles and validates logout responses from the IdP |
| `Saml2LogoutRequestValidator` | Validates logout requests per message and registration |
| `Saml2LogoutResponseValidator` | Validates logout responses |
| `LogoutHandler` | Performs local cleanup such as invalidating session/SecurityContext |
| `SecurityContextRepository` | Saves/reads security context of the local web session |

**These are components for an SP to participate in the protocol, not a global service managing sessions across all applications.** If simultaneous revocation across a cluster or all devices is needed, the SP needs a session registry, storage, and additional policies.

### RP-Initiated Behavior

Per Spring Security 6.5 docs, when SAML SLO is properly configured, a POST logout by a SAML-authenticated user can:

1. Run logout handlers to destroy the local session.
2. Generate a signed LogoutRequest to the IdP per registration.
3. Wait for/receive LogoutResponse if the IdP returns.
4. Validate LogoutResponse, correlation, and handle final navigation.

Common misconception: **the local session may already be destroyed before the IdP finishes propagating logout to other apps**. A browser interrupted after step 1 may still be logged out of Portal while federation-wide SLO remained incomplete.

### AP-Initiated Behavior

When the IdP sends a LogoutRequest to the right endpoint, Spring validates the request and destroys the local session in the handled request context, then generates a LogoutResponse. For "log out all devices", verify whether the app's repository/session mapping can actually find and delete **all other sessions**—never infer that merely because the filter returned Success.

## 11. Example SAML2 SLO Configuration in Spring Boot 3 / Spring Security 6.x

Example for **Spring Boot 3.x, Spring Security 6.x, Java 17+, Servlet MVC**. Configuration code does not run standalone with `javac` alone; it requires the Spring Security SAML service provider dependency, real IdP metadata, real SP key/cert, and the SP registered at the IdP.

File `src/main/resources/application.yml`:

~~~yaml
spring:
  security:
    saml2:
      relyingparty:
        registration:
          corp:
            assertingparty:
              metadata-uri: "classpath:saml/corp-idp-metadata.xml"
            signing:
              credentials:
                - private-key-location: "classpath:keys/sp-signing.key"
                  certificate-location: "classpath:keys/sp-signing.crt"
            singlelogout:
              url: "{baseUrl}/logout/saml2/slo"
~~~

**Mandatory prerequisites before use:**

1. `corp-idp-metadata.xml` must belong to a trusted IdP and contain a `SingleLogoutService` endpoint with compatible binding, plus signature verification keys. This must be real metadata; never fabricate empty certificates.
2. SP signs LogoutRequest/LogoutResponse using its own private key/certificate; IdP must know the SP's public certificate. Spring Security docs specify PKCS#8 keys and X.509 certificates.
3. SP Entity ID, SLO URL, public HTTPS scheme/host, and proxy forwarding must match metadata registered at the IdP.
4. Signing requirements on both sides, NameID/SessionIndex, and response bindings must be tested.
5. Example domains or URLs in this lesson are not live systems to access.

File `src/main/java/com/example/security/SamlSecurityConfig.java`:

~~~java
package com.example.security;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class SamlSecurityConfig {

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http)
            throws Exception {
        return http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/", "/healthz").permitAll()
                .anyRequest().authenticated())
            .saml2Login(Customizer.withDefaults())
            .saml2Logout(Customizer.withDefaults())
            .build();
    }
}
~~~

**`.saml2Logout(Customizer.withDefaults())` enables SLO handling in the application**, without guaranteeing the IdP and other SPs support it or succeeded. When this configuration works with SAML login, Spring Security 6.5 documents the RP-initiated trigger endpoint as typically **POST `/logout`**, while the default AP-initiated and LogoutResponse endpoint is **`/logout/saml2/slo`**.

**CSRF:** for browsers using Spring Security logout, trigger via POST with CSRF protection as configured. Never turn sensitive logout into a GET from an arbitrary link just for convenience, especially when the app uses local sessions and cross-site links. SAML message flows have their own validation/signatures and do not replace user-endpoint protection policies.

## 12. Separating Local Logout and SAML SLO with Two Endpoints

Sometimes UX must let users **log out of Portal while keeping the IdP session**—e.g., when leaving a shared computer—while another action requests **federated logout**.

With Spring Security 6.5, two separate endpoints can be configured:

~~~java
@Bean
SecurityFilterChain securityFilterChain(HttpSecurity http)
        throws Exception {
    return http
        .authorizeHttpRequests(auth -> auth
            .anyRequest().authenticated())
        .saml2Login(Customizer.withDefaults())
        .logout(logout -> logout
            .logoutUrl("/logout/local"))
        .saml2Logout(saml -> saml
            .logoutUrl("/logout/saml2"))
        .build();
}
~~~

**This replaces the bean method in the previous section** rather than adding a second SecurityFilterChain with overlapping scope. Keep imports and config class from section 11. Once full SAML SLO registration is present:

| Request | Purpose | Expectation |
| --- | --- | --- |
| POST `/logout/local` | Log out of Portal | Destroys local SP session; does not ask IdP to propagate SLO |
| POST `/logout/saml2` | Initiate RP-initiated SLO | Destroys local session; sends LogoutRequest to IdP |
| POST `/logout/saml2/slo` with SAMLRequest | IdP sends AP-initiated logout | Verifies request, cleans local session, and replies |
| POST `/logout/saml2/slo` with SAMLResponse | IdP replies to RP-initiated logout | Verifies response and finishes flow |

Ensure these URLs do not collide with app endpoints or CSRF policies, and SP metadata publishes the exact SLO endpoint if you change the request/response path.

**Never promise local-only logout prevents immediate re-login.** A live IdP cookie can still trigger automatic SSO.

## 13. LogoutResponse, Success, and PartialLogout

Never equate `LogoutResponse` with proof that "all applications closed". Verify:

1. LogoutResponse truly came from the right IdP/registration with a valid signature and valid endpoint.
2. `InResponseTo` matches the sent LogoutRequest, without forgery/replay.
3. `StatusCode` and sub-statuses are interpreted per SAML/profile/vendor.
4. Portal itself destroyed its local session.
5. Whether there is evidence the IdP propagated to participants and received replies.
6. Out-of-scope applications/devices are not misrepresented as logged out.

SAML defines **`urn:oasis:names:tc:SAML:2.0:status:PartialLogout`** to indicate the session authority **could not propagate logout to all participants**. The status may appear as a sub-status beneath the top-level status depending on message/vendor. UI must not report "Logged out everywhere" when receiving `PartialLogout`.

| Scenario | What May Be Asserted |
| --- | --- |
| Local SP session invalidated | User logged out of the current Portal session |
| LogoutRequest sent to IdP | SLO request initiated; other SP outcomes unverified |
| Successful LogoutResponse | IdP replied with valid protocol response; further check scope and participant status |
| PartialLogout | Some participant could not complete; disclose limit/suggest closing other apps |
| Timeout/no response received | Incomplete confirmation; remote state unknown |
| Browser closed after local logout | Local session may have ended; propagation completion uncertain |
| API token still valid | Cannot claim token revoked |

A common product bug is showing "Logged out of all devices successfully" right after a user clicks logout at one SP. That claim **exceeds the evidence**.

## 14. Network Drops, Closed Tabs, Cookies, and Browser Policies

SLO can fail for mundane reasons:

- Browser redirects to the IdP and the user closes the tab.
- Network drops or the IdP SLO endpoint returns 5xx.
- An SP is under maintenance, times out, or a reverse proxy fails to forward the request.
- Session cookie is withheld in cross-site context due to `SameSite`, third-party-cookie policies, or iframe embedding.
- Security headers, CSP, or JavaScript configuration interferes with SLO form POST/Redirect.
- Domain/certificate/ACS/SLO URL changed while metadata on both sides fell out of sync.
- Browser logged out in tab A while tab B still shows stale rendered data.
- Logout request hits the app before session index/association was stored or after the local session expired.

**Never "fix" errors by** disabling XML signature verification, accepting any issuer, trusting logout URLs from query strings, or skipping `InResponseTo`.

Design with **finite timeouts**, per-phase observability, honest outcome messaging, and safe continuation paths for users. Services handling admin privileges/sensitive PII should treat logout failures per risk policy rather than relying solely on UI.

## 15. Multi-Node Backend Sessions and Multiple Devices

If Portal runs on multiple nodes with sessions in Redis/Spring Session or a custom store, destroying `HttpSession` in a normal request targets only the identified session. To revoke **all local sessions** of a subject, the app needs a mechanism to:

- Identify **issuer/registrationId + stable subject ID** (and SessionIndex if needed), avoiding merging accounts solely by email.
- Enumerate **server-side session IDs** matching the target revocation scope.
- Execute invalidation synchronously across nodes or the centralized session store.
- Record which sessions were revoked/not found/errored.
- Verify subsequent requests with old cookies receive 401/302/403 per policy.
- Prevent eventually consistent listeners/caches from retaining old `Authentication` with sensitive privileges.
- Enforce TTL/anti-replay, avoiding acting on unverified logout messages.

Spring Security has session management and concurrent session control, yet **does not by default map every `SessionIndex` from every IdP to all devices and perform account-wide revocation**. That requires dedicated architecture and testing; when using Spring Session, verify session lookup by principal and your system's custom SAML identifiers.

**Wrong:** `LogoutRequest NameID = an@example.test` → delete every session with that email across all tenants. **Right:** verify issuer/NameID format/NameQualifier and verified scope, tenant mapping, SessionIndex/policy, and only then decide which sessions are authorized for deletion.

## 16. Token Types Outside the SAML Session

An app may use SAML for web login and later issue other credential types:

| Credential | Does SLO Auto-Invalidate It? | Supplemental Measure |
| --- | --- | --- |
| SP session cookie | Only if SP invalidates the matching session | Logout handler/central session store |
| HTTP remember-me token | Not guaranteed | Revoke remember-me token/cookie per policy |
| Self-contained JWT access token | Not by default; stays valid until `exp` | Short TTL, denylist/revocation check when needed |
| Opaque access token | Not automatically | Introspection/revocation at authorization server |
| OAuth2 refresh token | Not automatically | Revoke refresh tokens/token family |
| Mobile long-lived session | Not automatically | Backend device-session registry and remote logout |
| Connected WebSocket | Not guaranteed | Close/re-auth channels bound to revoked session |
| Service-to-service token | Outside user SAML SLO scope | Independent credential lifecycle |
| Offline cache | No | Clear per client security policy; not a server credential |

**Specifically:** deleting the IdP cookie only prevents reusing that IdP SSO session. It does not invalidate an API-issued JWT if the resource server only checks signature and `exp` without consulting revocation state. Test **whether APIs remain callable after logout** instead of guessing.

SAML SLO is not OIDC Front-Channel Logout, Back-Channel Logout, or OAuth Token Revocation. In multi-protocol systems, build a holistic logout plan per layer rather than treating one SAML LogoutResponse as proof for everything.

## 17. Designing True "Log Out of All Devices"

When business requirements call for **logout-all-devices**, design usually requires multiple layers:

1. **IdP:** use API/admin capabilities to revoke all IdP sessions of the account within permitted scope.
2. **SP application:** locate and destroy all local sessions of the internal account via backend session registry.
3. **Other SPs:** request coordination via SLO or supported admin/server-side revocation, collecting acknowledgments.
4. **OAuth/OIDC:** revoke refresh tokens, active grants, and apply policies for access tokens.
5. **Mobile apps:** destroy device sessions and server-side refresh token families.
6. **Unreachable sessions:** keep lifetimes short and block new requests via backend session version/revocation epoch.
7. **Audit:** record each scope, session type, and succeeded/unknown/failed result.
8. **UX:** tell users which sessions exited and where manual action is needed, without overclaiming.

**"Session version" example:** each account has a server-managed `sessionVersion` or `revokedBefore`. On logout-all, increment the version/update the timestamp, and every sensitive request checks whether the current session/token was issued before the revocation cutoff. Consistency, race conditions, clocks, TTL, caching, and JWT specifics must be designed accurately; this is an **app-built supplemental mechanism**, not something SAML SLO provides on its own.

If legal/security requirements demand instant revocation of all access, evaluate cache/edge/microservice propagation latency. Real-time global revocation cannot be guaranteed by a single browser redirect.

## 18. Standalone Java 17: Simulating SLO Scope Across Multiple Sessions

The following example **compiles/runs with JDK 17+** using no external libraries. It illustrates a policy decision: SLO initiated for IdP session **S1** can target participants that joined S1; sessions from **S2** and apps lacking SLO support remain out of scope. A participant may receive a request yet fail processing.

Create file **SloCoverageDemo.java**:

~~~java
import java.util.List;

public class SloCoverageDemo {

    record LocalSession(
            String app,
            String device,
            String idpSession,
            boolean sloParticipant,
            boolean deliverySucceeded) {}

    static String result(LocalSession local, String targetIdpSession) {
        if (!local.idpSession().equals(targetIdpSession)) {
            return "OUT_OF_SCOPE";
        }
        if (!local.sloParticipant()) {
            return "NOT_PARTICIPANT";
        }
        if (!local.deliverySucceeded()) {
            return "PENDING_OR_FAILED";
        }
        return "CLOSED";
    }

    public static void main(String[] args) {
        List<LocalSession> sessions = List.of(
            new LocalSession("Portal", "Laptop-Chrome", "S1", true, true),
            new LocalSession("HRM", "Laptop-Chrome", "S1", true, false),
            new LocalSession("CRM", "Laptop-Chrome", "S1", false, true),
            new LocalSession("Portal", "Mobile", "S2", true, true)
        );

        for (LocalSession session : sessions) {
            System.out.println(session.app() + " / " + session.device()
                    + ": " + result(session, "S1"));
        }
    }
}
~~~

Compile and run commands:

~~~bash
javac SloCoverageDemo.java
java SloCoverageDemo
~~~

**Exact stdout:**

~~~text
Portal / Laptop-Chrome: CLOSED
HRM / Laptop-Chrome: PENDING_OR_FAILED
CRM / Laptop-Chrome: NOT_PARTICIPANT
Portal / Mobile: OUT_OF_SCOPE
~~~

Interpretation:

- **Portal/Laptop-Chrome:** same IdP session S1, participated in SLO, and received the request successfully.
- **HRM/Laptop-Chrome:** belongs to S1 and supports SLO, yet the request did not complete; cannot assert logged out.
- **CRM/Laptop-Chrome:** does not participate in SLO, so S1 SLO does not auto-log out CRM.
- **Portal/Mobile:** belongs to S2; a LogoutRequest for S1 does not automatically revoke this session.

**This model only illustrates scoping logic**; it does not parse XML, verify signatures, use real NameID/SessionIndex, or delete any sessions. In real systems, `deliverySucceeded` is not enough: you must know the SP actually invalidated the session per protocol and policy. Never take S1/S2 strings from unverified client parameters or treat the demo's `CLOSED` as production proof.

## 19. Designing Unmisleading User Experience

On the logout page, products should clearly separate three choices (when actually supported by the platform):

| Choice | Purpose | Scope-Accurate Message |
| --- | --- | --- |
| **Log out of app** | Destroys current Portal session | "Logged out of Portal in this browser." |
| **SAML federated logout** | Asks IdP to propagate logout to participants of current session | "Requested logout of linked applications. Some applications may not have completed." |
| **Log out all devices** | Executes account-wide backend session/token revocation | Report complete only with sufficient evidence from each system |

If the IdP returns `PartialLogout` or an SP fails to respond:

- State clearly whether **Portal exited**.
- Inform that **other apps/devices may still be logged in**.
- Guide closing and manually logging out of non-participating or unresponsive apps.
- If the user is handling a lost device or suspected account compromise, direct them to the organization's all-sessions/tokens revocation workflow.
- Never display account names, SessionIndex, NameID, or unnecessary sensitive data on error pages.

Note that browser-routed SLO requests/responses may hand navigation to the IdP; Spring Security cannot always control which page renders after AP-initiated logout.

## 20. Runbook When SLO Completes Only Partially

### A. User Reports "Logged Out of Portal, Yet HRM Is Still Open"

1. Verify Portal actually destroyed the corresponding browser's local session.
2. Confirm whether the user triggered **local logout** or **RP-initiated SLO**.
3. Verify HRM and IdP metadata both have the right `SingleLogoutService`.
4. Verify HRM joined the IdP session named by SessionIndex.
5. Verify the IdP sent LogoutRequest to HRM, checking binding, timing, issuer, and destination.
6. Verify HRM received, verified, and invalidated the right local session; check cookie/session mapping errors.
7. If unresolved, guide direct logout in HRM and log the incident.
8. Never switch to skipping signature checks or accepting arbitrary SessionIndexes.

### B. Browser Closed Mid-Flow

1. Record **local logout** and **SLO propagation** states separately.
2. If the local session was destroyed, verify new requests to Portal force re-authentication.
3. Never conclude the IdP or SPs logged out without a response.
4. Query IdP/participant telemetry by correlation ID and time window.
5. If risk is high, execute supplemental server-side revocation per policy.

### C. User Requests Logging Out All Devices

1. Verify the requester and authorized account/tenant scope.
2. Invoke **all IdP sessions** revocation if supported by the IdP.
3. Revoke sessions across org-managed applications via session stores/services.
4. Revoke refresh tokens/authorized grants and apply access token policies.
5. Verify access from other devices with old cookies/tokens is truly rejected.
6. Record systems that lack support or did not respond; never claim "everywhere" when exceptions remain.
7. Monitor whether the user can log back in via any unrevoked session.

### D. IdP Returns PartialLogout

1. Verify the response was validated and `InResponseTo` matches.
2. Identify which participant was unreachable or returned no response.
3. Check network errors, front-channel cookies, endpoints, and metadata.
4. Never retry aggressively or infinitely; apply rate limits/backoff and prevent replay.
5. Consider manual logout instructions or backend-assisted remediation.
6. Separate **local logout PASS** from **federated propagation PARTIAL** in audits.

## 21. Common Errors and Causes

| Symptom | Possible Cause | Where to Check |
| --- | --- | --- |
| Log out of Portal then re-login without password | Local-only logout; IdP session persists | Check exact endpoint called and IdP cookie |
| Logged out of App A, App B stays logged in | B lacks SLO, request failed, or separate session | Check participants, LogoutRequest, and B's local session |
| Only the current device is affected | SLO targeted that device's IdP SessionIndex | Do not call it account-wide logout; add remote revocation |
| IdP says logged out, SP keeps session | SP missed request / lacks session mapping | Check binding, cookies, session registry, and logs |
| `LogoutResponse` never reaches Portal | Browser closed, IdP did not redirect, timeout | Separate local/remote state; never auto-report all-logout |
| `PartialLogout` | One or more participants failed to process | Identify failing participant; guide user |
| SAML logout returns 400 | Bad signature/issuer/destination/status/correlation | Compare metadata, keys, `InResponseTo`, and validation |
| SLO endpoint returns 404 | Wrong URL or DSL not enabled | Check `saml2Logout` and SingleLogoutService |
| POST logout returns 403 | Wrong CSRF token/config on local user-triggered request | Use POST with valid CSRF; never disable app-wide protection |
| Multiple IdPs, logout sent to wrong IdP | Wrong registration selected | Compare principal/issuer/registration; never use client URL |
| JWT app still calls API after SLO | Unexpired JWT with no revocation | Design revocation/introspection/TTL |
| Old tab still shows UI | SPA cache/local state persists | Clear UI state and enforce server API checks |
| One node keeps session after logout | Unsynchronized session storage/replication | Check distributed sessions and invalidation |
| Two user sessions share email, wrong person logged out | Account matching not anchored on stable issuer/subject | Bind issuer/NameID/tenant/SessionIndex |
| An SP does not support vendor IdP SLO | Incompatible profile/binding | Read metadata, IdP docs, and run end-to-end tests |

**Incident security note:** never resolve errors by dropping signature verification, disabling replay protection, trusting arbitrary `NameID` values, or bulk-deleting other users' sessions by email. Logout failures must be detected and handled within the **exact scope**.

## 22. Practical Testing Matrix

Organizations should test at least these scenarios using real browsers and a test IdP with trusted metadata/keys:

| Test | Context | Expectation |
| --- | --- | --- |
| 01 | One SP, one browser, RP-initiated SLO | Local session destroyed, valid messages, IdP responds appropriately |
| 02 | Two SPs sharing one IdP session, both support SLO | Both matching local sessions destroyed if propagation completes |
| 03 | Second SP does not support SLO | Never claim "logged out of all applications" |
| 04 | Two different browsers with different IdP sessions | Logging out S1 does not assume S2 is revoked |
| 05 | Mobile API refresh token still active | Verify whether token still works or was revoked separately |
| 06 | Browser closed right after sending LogoutRequest | Local logout and remote SLO states stay separate |
| 07 | IdP SLO endpoint returns 503 | App handles timeout/response safely |
| 08 | Peer SP offline or returns 500 | PartialLogout/unknown accurately reflected |
| 09 | Valid IdP-initiated LogoutRequest | SP destroys right session and returns appropriate response |
| 10 | IdP-initiated LogoutRequest with bad signature | Rejected; prevents stranger from destroying sessions |
| 11 | Forged or replayed LogoutResponse | Rejected per signature and InResponseTo |
| 12 | SessionIndex mismatch | Does not destroy wrong session/tenant |
| 13 | Different SameSite/cookie policies | Catch browser-dependent failures without bypassing trust |
| 14 | Multiple servers/regions | Consistent session invalidation |
| 15 | Two different IdPs | SLO affects only the matching federation link |
| 16 | Open old tab and call API after SLO | New requests cannot use destroyed session |
| 17 | SP has WebSocket or remember-me | Secondary credentials cleaned/revoked per policy |
| 18 | SP and IdP rotate SLO signing certificates | New Requests/Responses verify with right key |
| 19 | Reverse proxy with external HTTPS host | Destination/Issuer/SLO URL match metadata |
| 20 | "Logout all devices" via dedicated backend | All local sessions/tokens in scope verified revoked |

Tests that merely check for a "Signed out" page **are insufficient**. Test post-logout requests, inspect session stores/token introspection, and check telemetry per participant.

## 23. Monitoring, Auditing, and Clear Outcome Definitions

To avoid hiding SLO failures, record outcomes independently:

- **Local session invalidated:** true/false, session scope, timestamp.
- **SLO initiated:** true/false; verified IdP entityID and registrationId.
- **LogoutRequest signed/dispatched:** true/false; binding and endpoint.
- **LogoutResponse verified:** success/failure/timeout/unknown.
- **Status code:** Success, PartialLogout, or other spec-defined error.
- **Participant outcome:** completed/failed/unsupported/unknown when reliable data exists.
- **Account-wide revocation:** outcome of dedicated mechanism, never merged with SLO.
- **Post-logout access:** are requests using old sessions/tokens rejected?
- **Correlation:** request ID, timestamps, issuer, and PII-free security trail.

Metric names such as `saml_slo_local_logout_total`, `saml_slo_partial_total`, `saml_slo_timeout_total`, and `saml_slo_request_validation_failures_total` are **suggestions to implement yourself**, not defaults provided by Spring Security.

**Never log** full SAML LogoutRequest/LogoutResponse payloads containing NameID, SessionIndex, or private keys. For monitoring, use correlation IDs and properly redacted/masked identifiers with log protection policies.

A good dashboard separates **local logout rate**, **SLO protocol success rate**, **partial/unknown propagation**, and **token/session revocation rate**, avoiding collapsing everything into one green "Logout Success" tile.

## 24. Self-Assessment Questions

**1. Does SAML SLO guarantee logging out of all applications and all devices?**  
No. It coordinates session participants within SAML SLO scope; flows can be interrupted, some apps do not participate, or other IdP sessions exist.

**2. If Portal destroys the local HttpSession and the IdP does not respond, is Portal logged out?**  
Portal may be logged out; however, there is insufficient evidence to assert other applications logged out.

**3. Is `SessionIndex` the same as `JSESSIONID` or an account ID?**  
No. It pertains to the SAML session managed by the session authority and must be scoped by issuer/subject/registration.

**4. Does an SP LogoutRequest for SessionIndex S1 definitely destroy S2 on a phone?**  
No. S2 may be a separate IdP session; an account-wide mechanism is needed to revoke all devices.

**5. Does an app using only OIDC/JWT automatically receive SAML LogoutRequests?**  
No. Logout/revocation must match that app's protocol and capabilities.

**6. Why does front-channel SLO easily fail to complete?**  
It depends on the browser visiting endpoints, cookies, JS/CSP, networking, and users not interrupting the flow mid-way.

**7. What does `PartialLogout` indicate?**  
The session authority could not propagate logout to all participants; absolute completion must not be reported.

**8. Is logging out of Portal and immediately logging back in definitely a bug?**  
No. If only local logout ran while the IdP SSO session remains alive, re-login can be automatic.

**9. Is enabling `.saml2Logout(withDefaults())` enough for all apps outside Portal to log out together?**  
No. You need IdP SLO support, metadata, keys, endpoints/bindings, and other SPs participating and succeeding.

**10. Where must all sessions be revoked when a user's account is locked?**  
Beyond SAML SLO, enforce lockout at the IdP, destroy local SP sessions, revoke tokens, and enforce current backend authorization.

## 25. Production Deployment Checklist

- [ ] Clearly define whether the feature is **local logout**, **SAML SLO**, or **logout-all-devices**.
- [ ] Verify IdP supports SLO, metadata has `SingleLogoutService`, and binding matches.
- [ ] SP has signing credentials and IdP verification credentials for LogoutRequest/Response.
- [ ] `RelyingPartyRegistration` contains consistent SLO URL, entity IDs, and public URLs.
- [ ] Enable `saml2Logout` and separate local/SAML endpoints if UX requires.
- [ ] Use POST and CSRF properly on user-triggered logout; never skip SAML signature checks.
- [ ] Verify LogoutRequest/Response: issuer, signature, destination, replay, InResponseTo, and status.
- [ ] Preserve NameID + SessionIndex + IdP registration binding to avoid cross-tenant deletion.
- [ ] Know which SPs/IdPs participate in SLO and which lack support; never promise full global logout.
- [ ] Test multiple tabs, browsers, phones, IdP sessions, and distinct SP sessions.
- [ ] Have a mechanism to destroy all local sessions via session registry when account-wide is required.
- [ ] Plan revocation for OAuth/OIDC refresh tokens, JWT/API credentials, and mobile sessions.
- [ ] Test reverse proxies, cookies, SameSite, CSP, timeouts, and users closing tabs.
- [ ] Display PartialLogout/unknown honestly without concluding everything logged out.
- [ ] Have per-phase telemetry, statuses, participants, and post-logout access verification.
- [ ] Protect PII/NameID/SessionIndex in logs, audits, and UI.
- [ ] Maintain an emergency runbook for lost devices/compromised accounts not relying on a single browser redirect.

## 26. Conclusion

**SAML Single Logout solves only part of the federated logout problem, not a guarantee of revoking every session system-wide.** Across multiple applications, only participants that support SLO and actually receive/process valid messages can terminate their corresponding sessions. Across multiple browsers or devices, `SessionIndex` and IdP sessions may differ so logging out one session does not by default cover the entire account. Across OAuth/OIDC/mobile/APIs, other tokens and sessions require dedicated revocation mechanisms.

In Spring Security, `saml2Logout` provides endpoints to receive and emit LogoutRequests/Responses alongside local logout. Building a safe feature requires verifying messages per the exact IdP/registration, managing sessions server-side, separating **local/remote/partial** state, testing disconnects, and communicating real limits to users. **Never trade away SAML integrity or promise global logout if the system cannot verify it.**

### Official References

- Spring Security 6.5 — Performing Single Logout: https://docs.spring.io/spring-security/reference/6.5/servlet/saml2/logout.html
- Spring Security — Performing Single Logout (current release docs): https://docs.spring.io/spring-security/reference/servlet/saml2/logout.html
- Spring Security — Handling Logouts: https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/logout.html
- Spring Security — Authentication Persistence and Session Management: https://docs.spring.io/spring-security/reference/servlet/authentication/session-management.html
- OASIS — SAML V2.0 Technical Overview, Section 5.3: https://docs.oasis-open.org/security/saml/Post2.0/sstc-saml-tech-overview-2.0.html
- OASIS — SAML 2.0 Profiles, Single Logout Profile 4.4: https://docs.oasis-open.org/security/saml/v2.0/saml-profiles-2.0-os.pdf
- OASIS — SAML 2.0 Core, LogoutRequest/LogoutResponse/PartialLogout: https://docs.oasis-open.org/security/saml/v2.0/saml-core-2.0-os.pdf
- OASIS — SAML Version 2.0 Errata 05, E38 SessionIndex: https://docs.oasis-open.org/security/saml/v2.0/sstc-saml-approved-errata-2.0.html
- Okta — Configure Single Logout (vendor-specific device/session scope example): https://developer.okta.com/docs/guides/single-logout/saml2/main/
