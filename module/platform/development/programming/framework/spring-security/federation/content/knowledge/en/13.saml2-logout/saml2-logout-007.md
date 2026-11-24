# Storing Logout Requests and Verifying Response InResponseTo in Spring Security SAML 2.0

## 1. Goal and Security Problem

In **Spring Security – federation**, the Java application typically acts as the **Service Provider (SP / Relying Party)** while the centralized authentication system acts as the **Identity Provider (IdP / Asserting Party)**. When a user logs out, the application may not only clear its local session, but also initiate **SAML 2.0 Single Logout (SLO)** to ask the IdP to close the SSO session and handle related sessions.

In **SP-initiated Single Logout**, the SP emits a **LogoutRequest**, redirects the browser to the IdP, and later may receive a **LogoutResponse**. These are two separate HTTP requests that may traverse proxies, browsers, load balancers, and different nodes. In between, the local authenticated session may already have been destroyed.

Core question:

**How do we know a LogoutResponse truly answers the exact LogoutRequest previously emitted by the SP, in the right browser flow, and from the right IdP?**

To solve this, the SP must:

1. **Store the pending LogoutRequest** when creating the request, before handing control to the browser to visit the IdP.
2. Upon receiving a response, verify that **LogoutResponse.InResponseTo matches the stored LogoutRequest.ID**.
3. Also verify **RelayState, registration/IdP, signature, Destination, Status, expiration, browser context, and anti-replay**.
4. **Consume/delete the state once** upon completion per policy, never keeping pending requests indefinitely.

This lesson belongs to the **SAML2 Logout** group, aimed at Spring Security SAML 2.0 Servlet implementers. The focus is state lifecycle, using **Saml2LogoutRequestRepository**, cluster storage strategies, and verifying **InResponseTo** without bypassing SAML authentication checks.

**Note:** checking InResponseTo is only one protocol constraint. It is **not a cryptographic signature**, and a matching ID string does not turn a response forged by a stranger into a trustworthy one.

## 2. Distinguishing Three Logout Types

| Flow | Initiator | Messages on the Wire | State to Retain |
| --- | --- | --- | --- |
| **Local logout** | User at SP | No SAML LogoutRequest/LogoutResponse | No pending SLO |
| **SP/RP-initiated SLO** | **SP** | SP sends LogoutRequest; IdP may return LogoutResponse | **SP must remember its emitted request** |
| **IdP/AP-initiated SLO** | **IdP** | IdP sends LogoutRequest; SP returns LogoutResponse | IdP is responsible for correlating against its request |

### 2.1. SP-Initiated SLO: Main Flow of This Lesson

~~~text
Browser                       App SP                         IdP
   |                            |                            |
   | POST /logout               |                            |
   |--------------------------->|                            |
   |                            | LogoutHandler clears local |
   |                            | authenticated session      |
   |                            |                            |
   |                            | Create LogoutRequest       |
   |                            | ID = _logout_001           |
   |                            | RelayState = state-abc     |
   |                            | SAVE pending request       |
   |                            |                            |
   |<---------------------------| Redirect/POST SAMLRequest  |
   |-------------------------------------------------------->|
   |                            |                            | verify request,
   |                            |                            | process SLO
   |<--------------------------------------------------------|
   |   SAMLResponse containing LogoutResponse InResponseTo=_logout_001
   |--------------------------->|                            |
   |                            | LOAD pending               |
   |                            | verify signature, issuer,  |
   |                            | InResponseTo, RelayState,  |
   |                            | Destination, Status        |
   |                            | consume/cleanup state      |
   |<---------------------------| accurate SLO outcome       |
~~~

**Easy-to-miss detail:** by the time LogoutResponse arrives, the old Authentication and local session may already be invalidated. Therefore you must not design checks assuming the user is still logged in. Spring Security has a dedicated mechanism to **store the request in the session for RelayState and InResponseTo**.

Per Spring Security docs, for an applicable SAML principal, **`POST /logout`** can trigger RP-initiated SLO. The framework runs logout handlers to invalidate the local session, creates and sends LogoutRequest to the IdP's SingleLogoutService. If LogoutResponse returns, the framework continues verifying and completing the callback. The IdP may **not return a response** due to network errors, closed browser, or configuration; never assume every local logout proves federation-wide SLO succeeded.

### 2.2. IdP-Initiated SLO: Do Not Look Up an SP Pending Request

In the opposite direction:

~~~text
IdP -> SP: LogoutRequest.ID = _idp_request_9
SP: verify signature/issuer/request, handle local session per policy
SP -> IdP: LogoutResponse.InResponseTo = _idp_request_9
~~~

The SP is **replying to a request from the IdP**, not awaiting a LogoutResponse for an SP-created request. Thus the SP must not mistakenly apply "must find pending SP LogoutRequest" logic to **IdP-initiated** flows. When the IdP receives the SP's LogoutResponse, the IdP is responsible for matching InResponseTo against the request the IdP sent.

## 3. How Do InResponseTo, ID, RelayState, and SessionIndex Differ?

| Field | Where It Appears | Purpose |
| --- | --- | --- |
| **LogoutRequest.ID** | ID attribute on LogoutRequest | Unique ID of the request created by SP |
| **LogoutResponse.ID** | ID attribute on LogoutResponse | Separate ID of the reply message |
| **LogoutResponse.InResponseTo** | InResponseTo attribute on LogoutResponse | Points to the **LogoutRequest.ID** being answered |
| **RelayState** | Parameter in HTTP binding outside XML | Carries correlation state/browser flow through IdP |
| **SessionIndex** | Usually inside LogoutRequest | Identifies a SAML session to terminate |
| **NameID** | Inside LogoutRequest | Identifies the principal to log out in SAML |
| **registrationId** | In Spring Security repository | Local key of the SP–IdP pair |
| **SP/IdP entityId** | Metadata, Issuer element | Logical identifier of the two systems |

Example:

~~~text
LogoutRequest.ID              = _logout_001
LogoutResponse.ID             = _response_987
LogoutResponse.InResponseTo   = _logout_001
RelayState                    = state-abc
SessionIndex                  = _saml_session_24
~~~

Specifically **InResponseTo** must match the stored request ID. Do not confuse LogoutResponse.ID, SessionIndex, or NameID with LogoutRequest.ID. Both sides sharing the same SAML NameID also does not prove this is the response to **one specific request**.

### 3.1. Why Is InResponseTo Important?

Suppose two logout attempts are initiated:

~~~text
Pending A: LogoutRequest.ID = _A
Pending B: LogoutRequest.ID = _B

Response 1: InResponseTo = _A       -> can match only A
Response 2: InResponseTo = _B       -> can match only B
Response X: InResponseTo = _unknown -> no pending state, must reject
~~~

If you allow a LogoutResponse lacking InResponseTo or missing pending state to still confirm success, the system risks **accepting an out-of-flow or replayed response**. The goal is preserving continuity of the SAML exchange, not merely verifying that some IdP signed some XML.

### 3.2. Why Must RelayState Still Be Checked?

RelayState is typically an **opaque token** to restore browser context. It travels with SAMLRequest and returns with SAMLResponse, yet **lives outside the XML**. In HTTP-Redirect binding, when query signing is used, RelayState is part of the signed input per binding rules. In HTTP-POST binding with XML Signature, the XML signature does not automatically cover the RelayState form parameter; it must be verified via the SP's correlation mechanism.

**InResponseTo answers "which message is being replied to", while RelayState answers "which browser flow".** These two conditions complement each other. A valid RelayState does not replace signature or InResponseTo; a valid InResponseTo also does not prove RelayState was untampered.

Never use RelayState as an arbitrary redirect URL or tenant/IdP selector. Use **an unpredictable random string containing no personal data or secrets**, bound to SP-stored context.

## 4. SAML LogoutRequest Structure

Example illustrating fields relevant to storing state:

~~~xml
<samlp:LogoutRequest
    xmlns:samlp="urn:oasis:names:tc:SAML:2.0:protocol"
    xmlns:saml="urn:oasis:names:tc:SAML:2.0:assertion"
    ID="_logout_001"
    Version="2.0"
    IssueInstant="2026-01-01T10:00:00Z"
    Destination="https://idp.example.test/saml/slo">
    <saml:Issuer>urn:example:portal:sp</saml:Issuer>
    <saml:NameID>user-42</saml:NameID>
    <samlp:SessionIndex>_saml_session_24</samlp:SessionIndex>
</samlp:LogoutRequest>
~~~

**This is simplified XML to teach the concept, not a fully signed LogoutRequest.** In real protocol usage, the message must be built, signed/encoded per binding by Spring Security/OpenSAML, and may contain additional fields.

Points to note:

- Request **ID** is used for correlation; it must be unique and unpredictable. Spring Security includes ID generation for LogoutRequest.
- **IssueInstant** supports age/freshness policy, though it is not storage TTL by itself; the repository needs an independent timeout.
- **Issuer** is typically the SP Entity ID so the IdP can locate trust config.
- **Destination** is the IdP's registered SingleLogoutService URL.
- **NameID/SessionIndex** identify the person/session at the IdP, not replacing the request ID.
- **Signature** per binding requires the SP private key and SP public certificate trusted by the IdP; a matching request ID does not replace signature authentication.

## 5. LogoutResponse Structure and InResponseTo Placement

Example IdP reply:

~~~xml
<samlp:LogoutResponse
    xmlns:samlp="urn:oasis:names:tc:SAML:2.0:protocol"
    xmlns:saml="urn:oasis:names:tc:SAML:2.0:assertion"
    ID="_response_987"
    Version="2.0"
    IssueInstant="2026-01-01T10:00:05Z"
    InResponseTo="_logout_001"
    Destination="https://portal.example.test/logout/saml2/slo">
    <saml:Issuer>https://idp.example.test/issuer</saml:Issuer>
    <samlp:Status>
        <samlp:StatusCode
            Value="urn:oasis:names:tc:SAML:2.0:status:Success"/>
    </samlp:Status>
</samlp:LogoutResponse>
~~~

**Do not use this example as a safe message**: XML is simplified and omits the signature. In real systems, the IdP signs the response per config/binding, and the SP verifies against the exact IdP certificate.

Correlation rule:

~~~text
Request.ID                 = _logout_001
Response.InResponseTo      = _logout_001   -> matches request
Response.ID                = _response_987 -> new ID of response
~~~

Matching InResponseTo only proves **ID relationship in data**, which is not enough to conclude the IdP actually emitted the reply. The SP must still check signature, issuer, destination, RelayState, freshness, registration, and Status.

### 5.1. StatusCode Is Also a Required Condition

| StatusCode | Meaning | How to Handle |
| --- | --- | --- |
| **Success** | IdP reports successful processing per profile | Confirm SLO completed only if the response passed full validation |
| **PartialLogout** | Not all downstream sessions were processed | Do not claim all systems logged out |
| **Requester** | Error on the requester's side | Classify and record error; do not claim SLO succeeded |
| **Responder** | Error on the responder's side | Classify error and apply support/retry policy |

**The local session may already be closed from when the SP sent LogoutRequest**, even if the IdP returns an error or no response. Express honestly the state of "logged out of application" vs. "completed single logout".

## 6. What Does Spring Security Use to Store LogoutRequest?

Spring Security Servlet SAML2 has these primary components:

| Component | Job |
| --- | --- |
| **Saml2LogoutRequestResolver** | Creates, signs, and serializes LogoutRequest per Authentication/registration |
| **Saml2RelyingPartyInitiatedLogoutSuccessHandler** | Starts RP-initiated SLO, sends request to IdP, and saves pending state |
| **Saml2LogoutRequestRepository** | Interface to save, load, and remove pending Saml2LogoutRequest across HTTP requests |
| **HttpSessionLogoutRequestRepository** | Repository implementation backed by HttpSession |
| **Saml2LogoutResponseFilter** | Receives SAMLResponse at the SLO endpoint and hands it off for processing |
| **Saml2LogoutResponseValidator** | Validates response per policy and correlated request info |
| **RelyingPartyRegistrationRepository** | Provides SP–IdP config, certificates, endpoints, bindings |

Spring Security's **Performing Single Logout** guide states explicitly: when the app sends a LogoutRequest, **values are stored in the session to check RelayState and InResponseTo** on the returned LogoutResponse. To store elsewhere, provide a custom implementation via the **`logoutRequestRepository`** DSL.

### 6.1. Saml2LogoutRequestRepository Contract

Methods per modern Spring Security Javadoc, shown here with simplified signatures to illustrate purpose:

~~~java
Saml2LogoutRequest loadLogoutRequest(
    HttpServletRequest request);

void saveLogoutRequest(
    Saml2LogoutRequest logoutRequest,
    HttpServletRequest request,
    HttpServletResponse response);

Saml2LogoutRequest removeLogoutRequest(
    HttpServletRequest request,
    HttpServletResponse response);
~~~

Notes:

- These are **API signature excerpts**, not a standalone Java file or an interface you must redeclare.
- Modern versions use **`jakarta.servlet.http`**; return methods may carry nullable annotations, and **`saveLogoutRequest(null, ...)`** means deletion per contract.
- **save** stores the created request for the subsequent SLO flow.
- **load** returns the pending request by HTTP context for the validator to compare.
- **remove** retrieves and deletes state per repository semantics to prevent reuse after processing.
- Never interpret "load succeeded" as "response verified"; you must still verify signature/issuer/InResponseTo and all related conditions.

### 6.2. Distinguishing Logout Repository from Login Repository

| Repository | Used For | Corresponding IDs |
| --- | --- | --- |
| **Saml2LogoutRequestRepository** | **SLO** LogoutRequest/LogoutResponse | LogoutRequest.ID and LogoutResponse.InResponseTo |
| **Saml2AuthenticationRequestRepository** | **SSO login** AuthnRequest/Response | AuthnRequest.ID and Response.InResponseTo |

Never use **HttpSessionSaml2AuthenticationRequestRepository** in place of **HttpSessionLogoutRequestRepository**. Both state types have request IDs and correlation, yet **differ in protocol, lifecycle, API, and security filters**.

## 7. Spring Boot SLO Configuration Example

Minimal example for a Spring Boot 3.x/Spring Security SAML2 Servlet application with an IdP supporting Single Logout. Check exact property names in your deployed version.

File **src/main/resources/application.yml**:

~~~yaml
spring:
  security:
    saml2:
      relyingparty:
        registration:
          corp:
            entity-id: "urn:example:portal:sp"
            signing:
              credentials:
                - private-key-location: "file:/run/secrets/saml/sp-sign.key"
                  certificate-location: "file:/etc/saml/sp-sign.crt"
            singlelogout:
              url: "{baseUrl}/logout/saml2/slo"
            assertingparty:
              metadata-uri: "file:/etc/saml/idp-metadata.xml"
~~~

Explanation:

1. **corp** is the registrationId used to look up the right SP–IdP pair.
2. **entity-id** is the SP's identifier in SAML, distinct from a LogoutRequest ID.
3. **signing.credentials** loads the SP private key/certificate to sign LogoutRequests/LogoutResponses when required by profile. The IdP needs the SP's registered public certificate.
4. **singlelogout.url** is the SP's public SLO endpoint. The default path is typically **/logout/saml2/slo** and can be reconfigured.
5. **assertingparty.metadata-uri** imports IdP metadata to discover SingleLogoutService, binding, and verification certificate; the metadata source must have an appropriate trust policy.
6. Sample files must actually be provisioned. Never store private keys in source control or assume a metadata path proves the IdP is valid.

**Prerequisites before enabling SLO:** IdP metadata has **SingleLogoutService**; SP has registered the right SLO URL/certificate at the IdP; binding and signing match. Successful SSO login **does not mean** SLO will work automatically.

## 8. Java SecurityFilterChain: Using Spring's Repository

File **SecurityConfig.java** in a Spring Boot application with SAML2 dependencies:

~~~java
package com.example.portal;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.saml2.provider.service.web.authentication.logout.HttpSessionLogoutRequestRepository;
import org.springframework.security.saml2.provider.service.web.authentication.logout.Saml2LogoutRequestRepository;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class SecurityConfig {
    @Bean
    Saml2LogoutRequestRepository logoutRequestRepository() {
        return new HttpSessionLogoutRequestRepository();
    }

    @Bean
    SecurityFilterChain securityFilterChain(
            HttpSecurity http,
            Saml2LogoutRequestRepository logoutRequestRepository)
            throws Exception {
        http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/public/**").permitAll()
                .anyRequest().authenticated())
            .saml2Login(Customizer.withDefaults())
            .saml2Logout(saml2 -> saml2
                .logoutRequest(req -> req
                    .logoutRequestRepository(logoutRequestRepository)));
        return http.build();
    }
}
~~~

This is a **Spring class** and cannot compile with plain JDK without Spring Boot/Spring Security and an IdP registration. Its purpose is demonstrating the **`logoutRequestRepository`** API, not reproducing an entire project.

**If no custom storage is needed**, you can typically use **`saml2Logout(Customizer.withDefaults())`** and let Spring Security manage the default repository. When providing a bean as shown, ensure the filter chain **actually receives the right repository**.

Do not write a custom logout controller that merely inspects InResponseTo and redirects to a success page. Spring Security/OpenSAML SAML2 filters must handle parsing/signatures/validation.

### 8.1. Endpoints to Know

Per common Spring Security SLO:

~~~text
POST /logout
    -> RP-initiated logout by SAML-authenticated user

POST /logout/saml2/slo + SAMLRequest
    -> IdP-initiated LogoutRequest arriving at SP

POST /logout/saml2/slo + SAMLResponse
    -> LogoutResponse from IdP for SP-emitted request
~~~

The IdP may use **HTTP-Redirect binding** (GET), depending on product/config and supported profile; endpoints can be changed via the DSL. Never assume every IdP uses POST, and never disable **CSRF application-wide** to fix a single SLO callback error.

## 9. What Data Should Be Stored in Pending Logout State?

At the API level, Spring stores a **`Saml2LogoutRequest`** object. When designing a custom repository, conceptual data may include:

~~~text
PendingLogout:
  requestId            = _logout_001
  registrationId       = corp
  expectedIdpEntityId  = https://idp.example.test/issuer
  relayState           = opaque-relay-7
  spEntityId           = urn:example:portal:sp
  expectedResponseUrl  = https://portal.example.test/logout/saml2/slo
  browserFlowBinding   = opaque-browser-context
  createdAt            = 2026-01-01T10:00:00Z
  expiresAt            = 2026-01-01T10:03:00Z
  status               = pending
~~~

This model **does not mean Spring's `Saml2LogoutRequest` object contains every individual field**. The repository may store the serialized object plus other metadata recovered from registration/request context. What matters is that when the Response returns, the SP recovers the **right request** for the validator to verify.

Specifically:

- **requestId** must come from the emitted LogoutRequest, never accepted from a browser claim as already existing.
- **registrationId** ties to a trust configuration; do not confuse with IdP Entity ID.
- **RelayState** carries browser context and can help locate pending state.
- **expectedIdpEntityId** helps bind the right issuer, yet the issuer still requires a trusted signature.
- **createdAt/expiresAt** bound the state lifetime window. Three minutes in the example is only an **illustrative TTL**, not a SAML constant.
- **Saml2LogoutRequest** may carry XML/NameID/SessionIndex; storage must enforce appropriate access/retention limits and never print payloads to public logs.

## 10. LogoutResponse Validation Workflow

From a security standpoint, receiving a LogoutResponse must simultaneously satisfy:

1. **Received over a valid SLO endpoint/binding**, enforcing request size and XML parsing limits.
2. **Locate the right registration/trust context** from configuration and pending request. If an unverified response field must be used for lookup, that field is **only a hint**, with no authority to decide trust.
3. **Verify the IdP signature** per HTTP-Redirect/HTTP-POST profile and the IdP certificate provisioned/imported from a trusted source.
4. Response **Issuer** matches the expected IdP Entity ID.
5. **Load the pending LogoutRequest** belonging to the right browser/flow context and registration.
6. **LogoutResponse.InResponseTo** must match the stored **LogoutRequest.ID**. If no pending request exists or the ID differs, reject.
7. **RelayState**, if present, must match the stored state and obey binding semantics.
8. **Destination** matches the SP's public SLO response endpoint, and timestamps/Version/Status meet policy.
9. **Anti-replay:** never accept the same response successfully multiple times; pending requests must not be consumed more than once.
10. **Handle StatusCode honestly:** distinguish Success, PartialLogout, Requester, and Responder.
11. **Delete or update state** after validation per transaction policy and clean up expired states.
12. **Never recreate Authentication** from LogoutResponse; it is a logout reply, not a login token.

This is a **list of logical requirements**. Spring Security may perform lookups before signature verification to select the certificate and state; that is safe when unverified data is treated strictly as an **untrusted hint**. Never write a new XML signature algorithm just to reorder these steps.

### 10.1. Anti-Pattern: Checking Only InResponseTo

~~~java
// NOT SAFE: missing signature, issuer, destination, status...
if (response.getInResponseTo().equals(pendingId)) {
    return "logout successful";
}
~~~

An attacker can craft XML containing the same InResponseTo string. Skipping signatures and trust boundaries leaves the SP unable to tell who created the response. **InResponseTo is correlation, not authentication.**

### 10.2. Semantically Correct Condition Pattern

~~~text
responseValidatedBySamlLibrary
AND pendingRequestFoundForCorrectBrowserFlow
AND response.InResponseTo == pendingRequest.ID
AND relayStateMatchesIfUsed
AND registrationAndIdpIssuerMatch
AND destinationAndFreshnessValid
AND responseNotReplayed
AND statusPolicySatisfied
    => consume pending once, then report SLO outcome
~~~

This is **pseudocode**, not a Spring Security API. Several conditions already live inside the framework's validator implementations depending on version. Never drop the default validator and replace it with a few Java comparisons.

## 11. Redis, JDBC, and Clusters: When to Use a Custom Repository?

A multi-instance application can hit:

~~~text
User -> Node A: LogoutRequest saved in Node A's local session/memory
IdP  -> Node B: LogoutResponse arrives at Node B
Node B: pending not found -> InResponseTo cannot be verified
~~~

Sensible solutions:

- If already using **Spring Session sharing HttpSession via Redis/JDBC** with compatible cookies/browser bindings, **`HttpSessionLogoutRequestRepository` can still work**.
- If the app is stateless or wants to manage pending state separately, provide a **custom `Saml2LogoutRequestRepository`** backed by Redis/database with TTL and atomic consume.
- Session affinity can help in some topologies, though it does not fully solve restarts/failover. Ensure clean behavior when state is lost.

**Do not write a custom Redis repository solely because you have multiple nodes** if HttpSession is already safely distributed. Nor should you use a **static HashMap without TTL** for production state: it is not shared across nodes, is lost on restart, and lacks memory/replay controls.

### 11.1. Contract a Custom Repository Must Uphold

~~~text
saveLogoutRequest(logoutRequest, httpRequest, httpResponse):
    identify requestId, registrationId, relayState
    bind to trusted browser flow / session context
    store with finite TTL and explicit namespace
    never silently overwrite another state

loadLogoutRequest(httpRequest):
    find state by context/opaque correlation handle
    return only request belonging to the right flow and registration
    never trust issuer/ID/KeyInfo in an unverified response

removeLogoutRequest(httpRequest, httpResponse):
    delete state matching request and context
    prevent reuse and races across workers
    provide separate cleanup for expired entries
~~~

This is **API pseudocode**, not a runnable Redis implementation. The actual interface contract only receives `HttpServletRequest`/`HttpServletResponse`, so extracting the correlation handle must align with the framework's SAML filters and browser callbacks.

### 11.2. Do Not Use Unverified InResponseTo as Access to the Store

An internal index might use the request ID:

~~~text
slo:pending:corp:_logout_001
~~~

However, if the server accepts any InResponseTo in the body and searches the entire cross-tenant pending store, an attacker can send forged requests to probe IDs, cause resource exhaustion, or trigger cross-browser confusion.

Required:

- Namespace by trusted tenant/application/registration.
- Dedicated browser-flow/session binding or opaque RelayState with sufficient entropy.
- Short TTL per policy and cap on pending entries.
- Read-only hint-based lookup until signature and other conditions pass.
- Atomic state transition **pending -> completed**, preventing repeated responses from succeeding.
- Restrict read/write permissions on state, encrypt storage when needed, and never log serialized SAML requests containing user identifiers.

### 11.3. When Should State Be Deleted?

- After a **verified and processed** response per policy: consume once.
- After TTL: clean up expired state.
- When SLO is canceled via administrative workflow: cancel cleanly and audit if needed.

**Do not delete pending state immediately when an unverified response arrives**, because an attacker could send a spoofed response to wipe out the real request, causing a denial of service. At the same time, never let state live forever merely because a callback never arrived.

## 12. Session Invalidation, SameSite, and Cookies

The SLO lifecycle differs from an ordinary web form:

1. A **logged-in** user clicks logout at the SP.
2. The SP may **destroy the local authenticated session** before sending LogoutRequest.
3. The pending LogoutRequest must remain retrievable for the returning callback.
4. The browser navigates **cross-site** from SP to IdP and back.
5. The callback may be a **cross-site POST** or Redirect, with different cookie behaviors.

### 12.1. Why Can loadLogoutRequest Return Null?

- The browser dropped the cookie identifying the pending flow.
- The cookie has **`SameSite=Lax`** and a cross-site POST callback does not carry the cookie in that situation.
- The session was deleted by a custom logout handler after state was saved.
- The response hit another node when sessions are not shared.
- Pending state expired or was overwritten by a second logout request.
- SLO URL, scheme, domain, or reverse proxy was misconfigured.

**Never fix this by dropping the InResponseTo check.** Inspect browser Network logs, `Set-Cookie`/SameSite/Secure, SAML callbacks, session store, and session creation/destruction order.

### 12.2. SameSite Cookies and CSRF

When cross-site POST is required, cookie configuration may need **`SameSite=None; Secure`** or an equivalent out-of-session correlation mechanism per policy and browser behavior. However:

- Never set `SameSite=None` system-wide without evaluating CSRF, third-party cookies, and all endpoints.
- Never disable CSRF for all application POSTs just to accept SLO.
- The SAML SLO endpoint is a special protocol case requiring strict message verification and correlation.
- RelayState/cookies do not replace IdP signatures.
- Check public HTTPS paths behind TLS termination, accepting forwarded headers only from trusted proxies.

If the SLO callback uses Redirect/GET, cookie behavior may differ from POST, so **test the actual binding** rather than extrapolating from a single browser test.

## 13. Replay, Multiple Tabs, and Race Conditions

### 13.1. One Response Sent Twice

Suppose request A is pending. Valid response A arrives, SP verifies and completes it. Then the exact same response is submitted again. If state was consumed once, the second attempt must be rejected because no pending request remains.

A distributed store should use atomic **compare-and-delete** or **pending -> completed** transitions, rather than two nodes reading pending state and both reporting success. Completed records can be cleaned up after the replay-prevention window per policy.

### 13.2. Two Tabs Logging Out Simultaneously

~~~text
Tab A: LogoutRequest.ID = _A, RelayState = state-A
Tab B: LogoutRequest.ID = _B, RelayState = state-B
~~~

A repository storing only **one pending request per session** may have request B overwrite A. When response A returns, the matching request is gone and must be rejected. That may be an acceptable limitation, provided it is **tested and accurately messaged**.

If the application must support concurrent logout flows, use a state model storing **multiple requests by ID + flow binding + TTL** instead of overwriting a single `"pendingLogout"` key.

### 13.3. Late-Arriving Response

If pending state has expired, even with a valid response signature, the SP must not recreate pending state from InResponseTo or pick "the latest request". Return an error/message that federation-wide SLO could not be confirmed, clean up stale state per policy, and investigate why the IdP took too long.

### 13.4. Error Status Returned After Local Logout

The SP may already have exited the local session before the IdP returns **`PartialLogout`**, **`Requester`**, or **`Responder`**. In that case report accurately: **the application session ended, but logout across all linked SPs could not be confirmed**. Never restore an exited session from a failed response.

## 14. Standalone Java 17: Storing Pending State and Checking Correlation

The following program runs with **JDK 17 or later**, without Spring. It simulates a simple repository and these cases:

- InResponseTo must point to the exact pending request ID.
- RelayState, registration, IdP issuer, and browser-flow binding must match.
- Responses not verified by the SAML library are rejected.
- Pending requests must be within a three-minute TTL.
- Valid responses are consumed once using **`ConcurrentHashMap.remove(key, value)`**.

**Limitation:** this is only a correlation model. The boolean **`verifiedSamlResponse`** must be understood as **the result of Spring Security/OpenSAML already verifying signatures and protocol**, never a value from HTTP query/body. The program **does not parse LogoutResponse XML, verify XMLDSig/Redirect signatures, StatusCode, Destination, or Subject**. It is not a production `Saml2LogoutRequestRepository` implementation.

File **LogoutCorrelationDemo.java**:

~~~java
import java.time.Duration;
import java.time.Instant;
import java.util.Map;
import java.util.concurrent.ConcurrentHashMap;

public class LogoutCorrelationDemo {
    record Pending(String requestId, String registrationId,
            String expectedIdpIssuer, String relayState,
            String browserFlowId, Instant createdAt) {}

    record Reply(String inResponseTo, String registrationId,
            String actualIdpIssuer, String relayState,
            String browserFlowId, boolean verifiedSamlResponse) {}

    static final class PendingStore {
        private final Map<String, Pending> entries = new ConcurrentHashMap<>();
        private final Duration ttl = Duration.ofMinutes(3);

        void save(Pending request) {
            if (entries.putIfAbsent(request.requestId(), request) != null) {
                throw new IllegalStateException("Duplicate request ID");
            }
        }

        boolean complete(Reply reply, Instant now) {
            // In production, "verifiedSamlResponse" MUST come from
            // Spring Security/OpenSAML signature and protocol validation.
            if (!reply.verifiedSamlResponse()) return false;

            Pending expected = entries.get(reply.inResponseTo());
            if (expected == null) return false;
            if (now.isBefore(expected.createdAt())
                    || !now.isBefore(expected.createdAt().plus(ttl))) {
                return false;
            }
            if (!expected.registrationId().equals(reply.registrationId())
                    || !expected.expectedIdpIssuer().equals(reply.actualIdpIssuer())
                    || !expected.relayState().equals(reply.relayState())
                    || !expected.browserFlowId().equals(reply.browserFlowId())) {
                return false;
            }
            return entries.remove(expected.requestId(), expected);
        }
    }

    public static void main(String[] args) {
        Instant started = Instant.parse("2026-01-01T10:00:00Z");
        Instant now = started.plusSeconds(30);
        PendingStore store = new PendingStore();
        store.save(new Pending("_logout_001", "corp",
            "https://idp.example.test/issuer", "relay-abc",
            "browser-7", started));

        Reply valid = new Reply("_logout_001", "corp",
            "https://idp.example.test/issuer", "relay-abc",
            "browser-7", true);

        System.out.println("wrongInResponseTo=" + store.complete(
            new Reply("_other", "corp",
                "https://idp.example.test/issuer", "relay-abc",
                "browser-7", true), now));
        System.out.println("wrongRelayState=" + store.complete(
            new Reply("_logout_001", "corp",
                "https://idp.example.test/issuer", "changed",
                "browser-7", true), now));
        System.out.println("wrongBrowserFlow=" + store.complete(
            new Reply("_logout_001", "corp",
                "https://idp.example.test/issuer", "relay-abc",
                "browser-other", true), now));
        System.out.println("wrongIdpIssuer=" + store.complete(
            new Reply("_logout_001", "corp",
                "https://other.example.test/issuer", "relay-abc",
                "browser-7", true), now));
        System.out.println("untrustedResponse=" + store.complete(
            new Reply("_logout_001", "corp",
                "https://idp.example.test/issuer", "relay-abc",
                "browser-7", false), now));
        System.out.println("accepted=" + store.complete(valid, now));
        System.out.println("replayed=" + store.complete(valid, now));

        store.save(new Pending("_logout_old", "corp",
            "https://idp.example.test/issuer", "relay-old",
            "browser-7", started));
        System.out.println("expired=" + store.complete(
            new Reply("_logout_old", "corp",
                "https://idp.example.test/issuer", "relay-old",
                "browser-7", true), started.plusSeconds(181)));
    }
}
~~~

Run:

~~~bash
javac --release 17 LogoutCorrelationDemo.java
java LogoutCorrelationDemo
~~~

**Exact stdout**:

~~~text
wrongInResponseTo=false
wrongRelayState=false
wrongBrowserFlow=false
wrongIdpIssuer=false
untrustedResponse=false
accepted=true
replayed=false
expired=false
~~~

Explanation:

- **wrongInResponseTo=false:** no matching LogoutRequest ID exists.
- **wrongRelayState=false:** state was altered even though request ID matched.
- **wrongBrowserFlow=false:** pending request does not belong to the right browser context.
- **wrongIdpIssuer=false:** do not accept another IdP's response in this flow.
- **untrustedResponse=false:** without passing SAML validation, do not process as success.
- **accepted=true:** in this demo, all conditions match and state is consumed.
- **replayed=false:** the same reply cannot be processed a second time.
- **expired=false:** more than three minutes after saving the request, the flow is no longer valid.

This is **one Map inside one JVM**, not a distributed store, with no automatic TTL cleanup and no XML handling. For implementation, use Spring Security's **`Saml2LogoutRequestRepository`** and a store/validator with proper lifecycle.

## 15. Testing Matrix

| Test Case | Data | Outcome |
| --- | --- | --- |
| Standard SP SLO | Request ID=_A saved; IdP signs Response InResponseTo=_A | Full validation, consume pending |
| Wrong InResponseTo | Pending _A while Response points to _B | Reject |
| Missing InResponseTo | Response does not reference a request in SP-initiated flow | Reject per profile |
| Response.ID differs from Request.ID | Response.ID=_R, InResponseTo=_A | Correlation can still be valid |
| No pending state | Request TTL expired or session lost | Fail closed |
| Wrong RelayState | Matching ID, different RelayState | Reject |
| Wrong browser flow | Response on browser B instead of A | Do not consume pending A |
| Wrong registration | IdP A response processed under B's config | Reject |
| Bad IdP signature | XML has matching InResponseTo but unknown signer | Reject |
| Wrong Issuer | Response arrives from another IdP | Reject |
| Wrong Destination | Response sent to wrong SP SLO URL | Reject |
| Replay | Same Response re-submitted after consumption | Reject |
| Two-node race | Two nodes receive the same Response | Only one transitions to completed |
| PartialLogout | Partial status only | Do not report all sessions exited |
| Responder/Requester | IdP reports error | Classify; do not report SLO success |
| Browser closed | No Response returns | State expires; local logout may already be done |
| Cross-site POST | Session cookie blocked by SameSite policy | Fix cookie/binding; do not drop InResponseTo |
| Cluster | State on node A, callback hits node B | Shared store or fail safely |
| Redis failure | Cannot read pending state | Do not accept Response automatically |
| Two tabs log out | Pending A/B near-simultaneously | Behavior defined and tested |
| IdP-initiated | IdP sends LogoutRequest | SP validates request, returns InResponseTo matching IdP's ID |
| Local-only | No LogoutRequest emitted | Do not expect LogoutResponse |
| Malicious SAML XML | DTD, external reference, oversized XML | Block/limit parsing |
| Guessable ID attack | Guessing IDs to target InResponseTo | Signature and flow binding must reject |

**Beyond Java unit tests, test the real flow with a test IdP** and browser network inspection, as bugs often surface only via session cookies, SLO bindings, proxies, or IdPs failing to round-trip RelayState.

## 16. Common Errors and Diagnosis

| Error | Possible Cause | Remediation |
| --- | --- | --- |
| **loadLogoutRequest = null** | Session destroyed, cookie not sent, TTL expired, different replica | Check session lifecycle, SameSite, Redis/Spring Session |
| **InResponseTo mismatch** | IdP answered wrong request, multiple tabs overwrote, different flow | Compare pending ID and response InResponseTo |
| **RelayState mismatch** | IdP did not echo, proxy/query encoding bug, different browser | Compare stored state and binding |
| **Invalid signature** | Wrong IdP cert/metadata, signed for wrong binding | Verify certificate and algorithm; never disable validator |
| **Invalid issuer** | Wrong registration selected | Cross-check IdP entityId and trust config |
| **Destination invalid** | SLO URL/proxy host differs from public URL | Inspect metadata and reverse proxy |
| **No SAML LogoutRequest** | Principal not SAML, SLO disabled, IdP does not publish SLO | Check SAML principal/DSL/SingleLogoutService |
| **Fails only on POST** | SameSite cookie blocks cross-site callback | Test Secure/SameSite cookies and browser |
| **Fails only in cluster** | Pending stored locally on another node | Use Spring Session/distributed store |
| **Old request still accepted** | Missing cleanup/single-use consume | TTL and atomic delete |
| **IdP reports PartialLogout** | Some downstream SPs failed to process logout | Report accurately, audit |
| **Not logged out everywhere despite local success** | IdP SLO timed out/unsupported | Distinguish local logout from federated SLO |

### 16.1. Collecting Logs Without Exposing Data

Logs can include **request ID**, registrationId, IdP Entity ID, send/receive timestamps, TTL, validation error code, and correlation outcome at policy-appropriate detail. Never write full SAMLRequest/Response, NameID, SessionIndex, cookies, tokens, or RelayState containing sensitive data into production logs.

### 16.2. Unsafe "Workarounds"

- Dropping InResponseTo checks because "sessions get lost in the cluster".
- Falling back to the most recent request when pending lookup returns nothing.
- Accepting unsigned LogoutResponses if RelayState appears to match.
- Using InResponseTo from unverified XML to read across another tenant's pending store.
- Deleting state immediately upon receiving a spoofed response, causing DoS to real SLO.
- Disabling CSRF on all endpoints just to accept the callback.
- Binding user or tenant privileges to a user-supplied RelayState URL.

Fix the right layer: **storage/cookie/cluster**, **binding/IdP config**, or **signature/correlation validation**.

## 17. Deployment Checklist

- [ ] Clearly distinguished local logout, RP-initiated SLO, and AP-initiated SLO.
- [ ] IdP has SingleLogoutService with the right SLO endpoint and binding.
- [ ] SP has signing credentials, IdP verification credentials, and matching metadata trust.
- [ ] When RP initiates SLO, **LogoutRequest is stored before sending**.
- [ ] Request ID is unique, never confused with LogoutResponse.ID or SessionIndex.
- [ ] LogoutResponse.InResponseTo is compared against the exact pending LogoutRequest.ID.
- [ ] RelayState and browser-flow context are protected and matched after callback.
- [ ] Signature, issuer, Destination, timestamps, Status, and replay checks are never skipped.
- [ ] Pending state has TTL, capacity limits, cleanup, and one-time consumption.
- [ ] Custom repository adheres to Spring Security's load/save/remove contract.
- [ ] After local logout, SLO pending state remains retrievable as designed.
- [ ] Cross-site POST/Redirect tested with SameSite, Secure cookies, and HTTPS.
- [ ] Cluster A/B uses shared sessions or distributed repository; never a local Map in production.
- [ ] Unverified responses never select tenants, IdP keys, or request stores.
- [ ] Error policy defined for IdP timeouts, PartialLogout, or missing responses.
- [ ] Negative tests exist: missing/wrong InResponseTo, replay, wrong RelayState, wrong issuer, invalid signature, expiry.
- [ ] IdP-initiated LogoutRequests are verified and answered using the IdP's request ID.
- [ ] Logs never expose NameID/SessionIndex/SAML payloads/cookies or private keys.

## 18. Self-Check Questions

**1. Why must LogoutRequest be saved when the SP has already logged out locally?**

Because the IdP's LogoutResponse may arrive after local Authentication has been cleared. Pending request provides the original ID and context to check InResponseTo/RelayState.

**2. Must LogoutResponse.ID match LogoutRequest.ID?**

No. LogoutResponse has its own ID. **InResponseTo** is what references the original LogoutRequest ID.

**3. What if InResponseTo matches, yet the IdP signature is invalid?**

It must be rejected. IDs can be forged; the response's origin must be authenticated via signature and trust configuration.

**4. Can RelayState replace InResponseTo?**

No. RelayState holds browser state; InResponseTo binds at the SAML message level. Both are needed per the designed flow.

**5. Where does Spring Security store SLO requests by default?**

Spring Security documents storing them in the **session**, via **`HttpSessionLogoutRequestRepository`**, with the option to replace via **`Saml2LogoutRequestRepository`**.

**6. If Spring Session already uses Redis, is a custom Redis repository required?**

Not necessarily if HttpSession is shared properly and browser callbacks still carry the needed cookie. Test in practice.

**7. A response arrives at another node and state is missing; can it be accepted because the issuer is right?**

No. Losing pending state means correlation cannot be proven in an SP-initiated flow; fail closed and fix storage.

**8. In IdP-initiated SLO, what does InResponseTo on the SP's LogoutResponse point to?**

It points to the **ID of the LogoutRequest the IdP just sent**, not an earlier SP-initiated request.

**9. Does PartialLogout with matching InResponseTo mean federation-wide logout succeeded?**

No. StatusCode indicates part of the federation did not complete; displayed outcomes must be accurate.

**10. Should pending state be consumed immediately upon receiving a response before signature validation?**

No. That could let an attacker wipe out state with forged responses. Validation, atomic completion, and TTL cleanup are required.

**11. Why might a cross-site POST SLO callback miss the session?**

The session cookie may be blocked by SameSite/third-party cookie policies or the session may have been deleted. Check cookies, binding, and storage—do not drop correlation.

**12. What if the user closes the browser and the IdP never returns a response?**

Pending request expires/cleans up. The local session may have ended, yet never claim federation SLO completed without a verified response.

## 19. Authoritative References

- Spring Security, **Performing Single Logout**, RP/AP-initiated SLO and storing LogoutRequest to check RelayState/InResponseTo: https://docs.spring.io/spring-security/reference/servlet/saml2/logout.html
- Spring Security Javadoc, **Saml2LogoutRequestRepository** and load/save/remove methods: https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/saml2/provider/service/web/authentication/logout/Saml2LogoutRequestRepository.html
- Spring Security Javadoc, **HttpSessionLogoutRequestRepository**, storing SLO requests in HttpSession: https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/saml2/provider/service/web/authentication/logout/HttpSessionLogoutRequestRepository.html
- Spring Security Javadoc, **Saml2LogoutRequest**, ID, RelayState, and registration: https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/saml2/provider/service/web/authentication/logout/Saml2LogoutRequest.html
- Spring Security, **SAML 2.0 Login Overview**, distinguishing SSO AuthnRequest from SLO LogoutRequest: https://docs.spring.io/spring-security/reference/servlet/saml2/login/overview.html
- OASIS, **SAML 2.0 Technical Overview**, Single Logout Profile section: https://docs.oasis-open.org/security/saml/Post2.0/sstc-saml-tech-overview-2.0.html
- OASIS, **SAML V2.0 Profiles**, Single Logout Profile specification: https://docs.oasis-open.org/security/saml/v2.0/saml-profiles-2.0-os.pdf
- OASIS, **SAML V2.0 Bindings**, HTTP-Redirect/POST and RelayState: https://docs.oasis-open.org/security/saml/v2.0/saml-bindings-2.0-os.pdf
- Microsoft Entra ID, **Single Sign-Out SAML Protocol**, LogoutResponse InResponseTo example: https://learn.microsoft.com/en-us/entra/identity-platform/single-sign-out-saml-protocol

**Remember:** in **SP-initiated SAML2 Single Logout**, the SP **stores LogoutRequest.ID before going to the IdP** and processes LogoutResponse only when **InResponseTo matches a pending request in the right flow**. Spring Security provides **`Saml2LogoutRequestRepository`**, backed by HttpSession by default, to recover state and match InResponseTo/RelayState. Even so, correlation is only one layer: **IdP signature, issuer, destination, timestamps, StatusCode, TTL, browser/session binding, and anti-replay** must all be guaranteed before concluding SLO succeeded.