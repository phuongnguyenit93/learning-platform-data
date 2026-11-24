# LogoutRequest, LogoutResponse, and Message Correlation in SAML 2.0

**Module:** Spring Security – federation  
**Parent topic:** SAML2 Logout  
**Scope:** SAML 2.0 Single Logout (SLO), Spring Boot 3.x applications, Spring Security 6.x, Java 17+.

## 1. Why Is SAML Single Logout Needed?

**Single Sign-On (SSO)** allows a person to log in at an Identity Provider (IdP) and access multiple Service Providers (SPs) without re-entering credentials. However, each SP can maintain its own **HttpSession/SecurityContext**; logging out of one application does not automatically terminate all remaining sessions.

**Single Logout (SLO)** is a coordinated process between the identity issuer (**IdP**, often called *Asserting Party – AP* in Spring Security) and the identity-consuming application (**SP/Relying Party – RP**) to request terminating SAML sessions.

SLO revolves around **two distinct messages**:

- **samlp:LogoutRequest:** the initiator asks the other party to end sessions belonging to a SAML identity; may include **SessionIndex** to narrow which session to log out.
- **samlp:LogoutResponse:** the recipient returns the processing outcome of the LogoutRequest, containing **Status** and, for a reply to a request, **InResponseTo** pointing back to the **LogoutRequest's ID**.

SLO has two initiation directions:

1. **SP/RP-initiated SLO:** the user clicks logout at the application; the SP sends a LogoutRequest to the IdP; the IdP may ask other SPs to log out, then returns a LogoutResponse to the originating SP.
2. **IdP/AP-initiated SLO:** the user logs out at the IdP or another SP triggers IdP orchestration; the IdP sends a LogoutRequest to the SP; the SP validates the request, clears the matching session, and returns a LogoutResponse to the IdP.

**Essential rule:** SAML LogoutRequest/LogoutResponse are **not the same** as AuthnRequest/SAML login Response. A logout message does not authenticate a user to create a new session. Valid signatures, Issuer, Destination, correlation, NameID/SessionIndex, and Status must be evaluated according to each message's exact role.

## 2. Distinguishing LogoutRequest, LogoutResponse, and SAML Login Response

| Message | Who Issues It? | Meaning | Correlation Field |
| --- | --- | --- | --- |
| **AuthnRequest** | SP when starting SSO | Asks the IdP to authenticate the user | **AuthnRequest.ID** |
| **samlp:Response** containing Assertion | IdP when completing SSO | Evidence of authentication | **Response.InResponseTo = AuthnRequest.ID** in SP-initiated login |
| **samlp:LogoutRequest** | SP **or** IdP | Requests ending a SAML login session | **LogoutRequest.ID**, NameID, SessionIndex |
| **samlp:LogoutResponse** | Recipient of LogoutRequest | Reports outcome of handling the logout request | **LogoutResponse.InResponseTo = LogoutRequest.ID**; Status |

Common pitfall: in the HTTP-POST binding, the **form field** can be **SAMLRequest** or **SAMLResponse**. The **SAMLResponse** form field contains **LogoutResponse** XML when calling the SLO endpoint, whereas it contains authentication **Response** XML when calling the ACS endpoint. Sharing the same HTTP field name does not give the two messages the same semantics.

A typical transaction:

~~~text
LogoutRequest.ID                 = _logout_req_123
LogoutResponse.ID                = _logout_resp_456
LogoutResponse.InResponseTo      = _logout_req_123
LogoutResponse.Status.StatusCode = Success
~~~

**Do not compare LogoutResponse.ID with LogoutRequest.ID.** LogoutResponse has an independent ID; **InResponseTo** is the reference to the emitted request. **Status=Success** must also not be concluded merely from InResponseTo matching: signature, Issuer, Destination, and policy rules still must pass.

## 3. LogoutRequest Structure: What Information Must the Recipient Verify?

Sample **XML for reading structure**, signature omitted, not a complete request for production use:

~~~xml
<samlp:LogoutRequest
    xmlns:samlp="urn:oasis:names:tc:SAML:2.0:protocol"
    xmlns:saml="urn:oasis:names:tc:SAML:2.0:assertion"
    ID="_logout_req_123"
    Version="2.0"
    IssueInstant="2026-11-07T08:00:00Z"
    Destination="https://idp.example.org/saml/logout"
    Reason="urn:oasis:names:tc:SAML:2.0:logout:user">
  <saml:Issuer>https://portal.example.org/saml/sp</saml:Issuer>
  <saml:NameID
      Format="urn:oasis:names:tc:SAML:2.0:nameid-format:persistent"
  >employee-847</saml:NameID>
  <samlp:SessionIndex>session-index-abc</samlp:SessionIndex>
</samlp:LogoutRequest>
~~~

### 3.1. Key Fields

| Field | Meaning | Processing Rule |
| --- | --- | --- |
| **ID** | Unique identifier of the LogoutRequest | Used to match **LogoutResponse.InResponseTo** and prevent reuse per policy |
| **Version** | Protocol version, usually **2.0** | Reject unsupported versions |
| **IssueInstant** | Issuance timestamp | Check reasonableness, clock skew, and acceptance window per policy |
| **Destination** | Intended message-receiving endpoint | Must match the trusted SLO endpoint and configured binding |
| **Issuer** | EntityID of the party requesting logout | Must be an approved SAML partner; do not take self-declared domains from XML as trust |
| **NameID** | SAML subject to log out | Must match identity/session per federation relationship requirements |
| **SessionIndex** | SAML session index, may be multiple; **optional in schema** | Helps identify the session to end; not JSESSIONID |
| **Reason** | Reason for requesting logout | Informational; does not replace verification/trust |
| **NotOnOrAfter** | Time after which the request is no longer accepted if used | Do not treat as browser session timeout |

Per SAML Core, a LogoutRequest contains one of the subject identifiers **BaseID, NameID, or EncryptedID** and **may** contain multiple **SessionIndex** elements. The sample XML uses NameID for readability. Some IdPs support/require SessionIndex while others do not; check each IdP's contract.

**SessionIndex ≠ HttpSession ID.** SessionIndex originates from the **IdP's AuthnStatement/SAML session**, whereas **JSESSIONID/SESSION** is the HTTP session identifier managed by the SP. Never put JSESSIONID into SessionIndex, and never guess NameID=email.

### 3.2. Integrity and Provenance

A request with valid XML that is not signed/verified per the agreed profile and binding **is not safe enough to destroy a session**. When the IdP sends a LogoutRequest to the SP, the SP must verify the signature using the **IdP's trusted verification certificate**; when the SP sends a request to the IdP, it uses the **SP signing private key** per registered metadata/policy.

**Session protection:** accepting a LogoutRequest from any source based solely on NameID allows an attacker to attempt logging out other users (logout CSRF/DoS). Signature + Issuer + target subject/session + time + correlation checks must be applied independently.

## 4. LogoutResponse Structure: Which Request Does It Answer, and What Is the Outcome?

Example **LogoutResponse** sent by the IdP to the SP after the SP emitted the LogoutRequest in section 3:

~~~xml
<samlp:LogoutResponse
    xmlns:samlp="urn:oasis:names:tc:SAML:2.0:protocol"
    xmlns:saml="urn:oasis:names:tc:SAML:2.0:assertion"
    ID="_logout_resp_456"
    Version="2.0"
    IssueInstant="2026-11-07T08:01:00Z"
    Destination="https://portal.example.org/logout/saml2/slo"
    InResponseTo="_logout_req_123">
  <saml:Issuer>https://idp.example.org/saml</saml:Issuer>
  <samlp:Status>
    <samlp:StatusCode
        Value="urn:oasis:names:tc:SAML:2.0:status:Success"/>
  </samlp:Status>
</samlp:LogoutResponse>
~~~

**This is illustrative XML without a signature**; never use it as a "logout succeeded" fixture in production.

### 4.1. Correlation Conditions

For a transaction that emitted **LogoutRequest.ID = _logout_req_123**, the recipient of the LogoutResponse must:

1. Look up the stored **pending LogoutRequest** for the transaction and right partner.
2. Compare **LogoutResponse.InResponseTo = LogoutRequest.ID**.
3. Verify the replying Issuer is the corresponding IdP/SP, Destination is its own SLO response endpoint, and the signature is valid.
4. Check timestamps, binding, Status, and replay/single-use.
5. Close the pending state per policy and report the actual result to the user/monitoring.

**InResponseTo alone does not prove logout completed.** It only answers "which request does this response belong to?". **Status** and the other verification conditions determine whether the message can be accepted as the transaction outcome.

### 4.2. Important SAML Statuses

- **urn:oasis:names:tc:SAML:2.0:status:Success:** the responder reports success per its semantics.
- **urn:oasis:names:tc:SAML:2.0:status:Responder:** error on the response-processing side, potentially accompanied by a nested StatusCode/StatusMessage.
- **urn:oasis:names:tc:SAML:2.0:status:Requester:** request rejected due to an issue from the sender side.
- **urn:oasis:names:tc:SAML:2.0:status:PartialLogout:** only a subset of sessions/partners were logged out during global orchestration; **do not treat as the entire system being fully logged out**.
- **StatusMessage:** depending on the IdP, may describe the error; never render sensitive messages to public UIs.

In a multi-SP system, even when the IdP returns **Success**, the application still needs to understand the scope committed by the partner. SLO is a browser/network-coordinated process, not an ACID transaction across all SP sessions; network interruptions, closed tabs, an IdP lacking a binding, or an unresponsive third SP can leave the outcome incomplete.

## 5. RP/SP-Initiated SLO Flow: Sequence A → B → A

When a user logs out of an SP (e.g., a portal app):

~~~text
Browser                 Spring Security SP                     SAML IdP
   |                            |                                 |
   | POST /logout (+ CSRF)      |                                 |
   |--------------------------->| LogoutHandler cleans SP session |
   |                            | Saml2RelyingPartyInitiated...   |
   |                            | creates LogoutRequest ID=_L1    |
   |                            | signs & saves pending request   |
   |<---------------------------| redirect/POST to IdP ---------->|
   |                            |                                 | Verify
   |                            |                                 | NameID/SessionIndex
   |                            |                                 | Logout IdP & other SPs
   |                            |<--------------------------------|
   | POST /logout/saml2/slo     |                                 |
   | SAMLResponse:              |                                 |
   | LogoutResponse             |                                 |
   | InResponseTo=_L1           |                                 |
   |--------------------------->| Saml2LogoutResponseFilter       |
   |                            | verify + correlation + status   |
   |<---------------------------| landing page if valid           |
~~~

### Step 1 – User Requests Logout at the SP

Normally the browser sends **POST /logout** with a valid CSRF token. Spring Security invokes **LogoutHandler** to destroy/release application state: **SecurityContext**, session, and related local state. Then **Saml2RelyingPartyInitiatedLogoutSuccessHandler** initiates SLO when **saml2Logout()** is configured properly.

**This does not mean the SP must wait for the IdP's reply before deleting the local session.** Spring Security can invalidate the local session **before** receiving the SLO response. If the IdP loses connectivity afterward, the user is usually already logged out of the SP while potentially still holding an IdP or other SP session.

### Step 2 – SP Creates and Saves the LogoutRequest

**Saml2LogoutRequestResolver** builds the XML using the registration tied to **Saml2AuthenticatedPrincipal**, SP entityID, IdP SingleLogoutService endpoint, and SP signing credentials. The SP saves pending request details via **Saml2LogoutRequestRepository** so it can later verify **RelayState** and **LogoutResponse.InResponseTo** when the IdP replies.

**Implementation subtlety:** even though the local login session may have been invalidated, the SLO framework must preserve correlation info in an appropriately managed repository/session to verify the reply. Do not delete the pending request yourself or replace the logout success handler in a way that leaves LogoutResponse with nothing to match against.

### Step 3 – IdP Processes and Orchestrates

The IdP verifies the request came from the approved SP, checks NameID/SessionIndex, and ends its session per policy. If the IdP knows other SPs share the same SSO session, it can send a **new LogoutRequest** to each SP.

**Intermediate LogoutRequests have their own IDs**, not reusing the originating SP's LogoutRequest.ID. Other SPs return **LogoutResponse** to the IdP with **InResponseTo** pointing to the IdP's request meant for that specific SP.

### Step 4 – IdP Returns LogoutResponse to the Originating SP

Finally, if the browser/IdP completes the flow and returns a response:

- **Saml2LogoutResponseFilter** receives **SAMLResponse** at the SLO endpoint.
- The filter deserializes/verifies **LogoutResponse** via **Saml2LogoutResponseValidator**.
- Correlation and Status are processed; if valid, it can redirect to the logout completion page, typically **/login?logout** per configuration.
- If the response is invalid, Spring Security typically returns an error (e.g., **HTTP 400**) instead of declaring global logout successful.

**The browser might not return to the SP.** For instance, the user closes the tab at the IdP, the IdP stays on an interstitial page, a third party times out, or bindings are incompatible. Applications must have UX distinguishing **"ended session at this application"** from **"confirmed logout across the entire ecosystem"**.

## 6. IdP/AP-Initiated SLO Flow: B → A → B

When a user logs out at the IdP or the IdP receives a logout request from another SP:

~~~text
IdP/AP                         Browser                       Spring SP
  |                                |                              |
  | Create LogoutRequest ID=_I9    |                              |
  | Issuer=IdP, NameID, Index      |                              |
  |--------------------------------> POST /logout/saml2/slo ------>|
  |                                |                         Saml2LogoutRequestFilter
  |                                |                         validate sig/issuer/target
  |                                |                         LogoutHandler cleans session
  |<-------------------------------- response sent via browser <---|
  |  LogoutResponse                |                              |
  |  InResponseTo=_I9              |                              |
  |  Status=Success/Error          |                              |
~~~

### What Happens at the SP?

1. The SP receives **SAMLRequest** containing **samlp:LogoutRequest** at the SLO endpoint.
2. **Saml2LogoutRequestFilter** parses it and uses **Saml2LogoutRequestValidator** to verify signature, Issuer, Destination, identity/session, and applicable conditions.
3. If valid, logout handlers terminate the matching local session and SecurityContext.
4. **Saml2LogoutResponseResolver** creates a **new LogoutResponse** issued by the SP.
5. The SP returns it via the configured binding to the IdP's **SingleLogoutService response location**; the response typically has **InResponseTo = the IdP's LogoutRequest.ID** and an appropriate Status.

**Do not initiate a second LogoutRequest to reply directly to a LogoutRequest.** The standard reply message is **LogoutResponse**, not AuthnRequest and not a SAML assertion.

### What Differs from SP-Initiated?

| Criterion | SP/RP-Initiated | IdP/AP-Initiated |
| --- | --- | --- |
| Where the user first chooses logout | SP | IdP or another SP |
| Party creating the first LogoutRequest of the SP–IdP transaction | SP | IdP |
| Party issuing the LogoutResponse in that pair | IdP | SP |
| Filter handling the **inbound message at the SP** | Saml2LogoutResponseFilter | Saml2LogoutRequestFilter |
| Where SP-emitted pending request is stored | Saml2LogoutRequestRepository | No pending SP request for a fresh IdP-sent request |
| InResponseTo relationship | IdP response → SP request.ID | SP response → IdP request.ID |
| Local logout at SP | Usually before going to IdP | After verifying the IdP request is valid |
| Whether SP controls the final page | Yes if IdP returns browser | IdP steers browser after SP returns response |

**Do not assume every IdP-sent LogoutRequest targets the right user:** bind identity/SessionIndex to a session the SP is authorized to destroy and verify signature/Issuer from the right IdP. Never approve a request just because the XML contains a NameID that looks like a user.

## 7. Relationship Between Messages When Multiple SPs Exist

Suppose a user's SSO session has three open applications: **portal-SP**, **reports-SP**, and **billing-SP**.

~~~text
portal-SP                         IdP                        reports-SP
   |                               |                               |
   | LogoutRequest ID=_P1          |                               |
   |------------------------------>|                               |
   |                               | LogoutRequest ID=_I1          |
   |                               |------------------------------>|
   |                               |<------------------------------|
   |                               | LogoutResponse                |
   |                               | InResponseTo=_I1              |
   |                               |                               |
   |<------------------------------|                               |
   | LogoutResponse                |                               |
   | InResponseTo=_P1              |                               |
~~~

A similar branch can occur with billing-SP, using a different request ID such as **_I2**.

**There is no single shared InResponseTo for all responses across the entire cascade.** Each LogoutResponse references **the direct request it is answering**:

- reports-SP replies to IdP: **InResponseTo=_I1**.
- billing-SP replies to IdP: **InResponseTo=_I2**.
- IdP replies to portal-SP: **InResponseTo=_P1**.

This is why a multi-SP audit system should record **request ID + issuer/recipient + correlation state**, rather than only generic text like "logout request completed".

### PartialLogout and Per-SP Failures

If reports-SP logs out successfully while billing-SP is offline, the IdP may report an error status or **PartialLogout** depending on implementation. The originating SP must interpret the returned status accurately: the portal session may have been deleted, yet there is no guarantee all billing/reports sessions ended too.

**LogoutResponse=Success from one branch** only states the outcome of that branch per the responder; it is not a permanent receipt for all SPs when network/protocol limitations exist.

## 8. NameID and SessionIndex: Identifying Which Session to Delete

### NameID

A SAML LogoutRequest can specify the identity to terminate using **NameID** (or BaseID/EncryptedID). NameID has a format and sometimes NameQualifier/SPNameQualifier. Never automatically convert NameID into an email to search sessions; many IdPs use opaque/persistent or transient strings for NameID.

**Do not rely solely on NameID** to wipe unrelated application sessions, especially in multi-tenant or multi-IdP setups. Verified issuer/trust and reliable session boundaries are required.

### SessionIndex

The IdP can attach **SessionIndex** in **AuthnStatement** when the user logs in. During logout, SessionIndex indicates a specific SAML session to terminate. A user may have multiple sessions/devices, so SessionIndex helps narrow the blast radius.

- **SessionIndex** is an identifier in the SAML/IdP context; it is **not** JSESSIONID, a Redis key, or an OAuth session ID.
- A LogoutRequest may **omit SessionIndex**, or contain multiple values; actual policy depends on the IdP and profile.
- If the SP wants to destroy a set of sessions by SessionIndex, there must be a governed mapping from **(issuer, NameID/subject, SessionIndex)** to local sessions.
- An SP storing only the current HttpSession may be insufficient for remote global logout across devices without a session registry/store.
- Processing outcomes depend on whether real sessions are still active or expired; applications should return statuses matching behavior/contract rather than pretending a session was found when none existed.

### Different Lifetimes and Deadlines

- **IssueInstant** and **LogoutRequest NotOnOrAfter** serve to check message freshness.
- **SAML Assertion NotOnOrAfter** governs assertion conditions at login, **not LogoutRequest expiration**.
- **HttpSession timeout** is the SP's idle session timeout.
- **IdP SSO session timeout** is managed by the IdP; expiration of the IdP session does not necessarily terminate all already-created SP sessions immediately.
- **LogoutRequest/Response IDs** should be treated as unique and replay-protected within the required window.

## 9. RelayState, Bindings, and Endpoints: How Do Messages Travel?

### 9.1. HTTP-POST and HTTP-Redirect

SAML 2.0 supports different bindings. For common browser SLO flows:

| Binding | HTTP Form | Things to Watch |
| --- | --- | --- |
| **HTTP-POST** | Form POST containing encoded **SAMLRequest** or **SAMLResponse** | May use XML Signature on the message, depending on profile/configuration |
| **HTTP-Redirect** | Query string containing SAMLRequest/SAMLResponse, RelayState, and binding signature when signed | Must verify signature over exact query/binding data, not just base64-decoded XML |
| **SOAP/Back-channel** | Server-to-server messages in certain profiles | Differs from browser session/cookie flows; Spring Security Servlet SLO samples focus on browser |

**Do not conclude that every IdP supports POST and Redirect simultaneously.** Read the **SingleLogoutService Binding/Location/ResponseLocation** section in IdP metadata and verify against Spring Security/version/IdP contract.

### 9.2. Default Spring Security URLs

With **Spring Security 6.5 Servlet SAML2 SLO**, typically:

- **POST /logout**: authenticated user at the SP triggers **SP-initiated** logout, with a CSRF token if CSRF is enabled.
- **POST /logout/saml2/slo** containing **SAMLRequest**: IdP-initiated LogoutRequest entering the SP.
- **POST /logout/saml2/slo** containing **SAMLResponse**: IdP sends LogoutResponse for an SP-initiated LogoutRequest.

The default SLO endpoint normally **does not need {registrationId}**, because the request can identify the registration via the principal or stored message/transaction. With multiple IdPs, selecting the registration must use a trusted mechanism rather than an arbitrary query parameter.

**Do not confuse /logout/saml2/slo with /login/saml2/sso/{registrationId}.** ACS handles login SAML Responses; the SLO endpoint handles LogoutRequests/LogoutResponses.

### 9.3. What Is RelayState Used For?

**RelayState** is HTTP-binding state data. In SP-initiated SLO, the repository can store the LogoutRequest with RelayState and use it to look up/match the request when the LogoutResponse arrives.

**RelayState is not a digital signature**, does not prove identity on its own, and should never be turned directly into a client-controlled redirect URL. A good RelayState value in custom flows is unpredictable, has a TTL, is bound to the transaction/session, and is single-use. Every LogoutResponse must tie back to the right LogoutRequest **and right IdP/registration**, not merely match a RelayState string.

## 10. Spring Security 6: Related Filters and Repositories

Spring Security provides standard mechanisms without requiring applications to write controllers parsing logout XML manually:

| Component | Role |
| --- | --- |
| **saml2Logout()** | Enables SAML Single Logout support in SecurityFilterChain |
| **Saml2RelyingPartyInitiatedLogoutSuccessHandler** | Handles post-local-logout step, initiating SP-initiated LogoutRequest |
| **Saml2LogoutRequestResolver** | Creates/signs/serializes LogoutRequest per registration/session |
| **Saml2LogoutRequestRepository** | Stores SP-emitted requests to correlate RelayState and LogoutResponse.InResponseTo |
| **Saml2LogoutResponseFilter** | Receives/validates LogoutResponse returned for SP-initiated SLO |
| **Saml2LogoutResponseValidator** | Validates SLO response messages (signature/issuer/destination/status and other constraints) |
| **Saml2LogoutRequestFilter** | Receives IdP-initiated LogoutRequest at the SP |
| **Saml2LogoutRequestValidator** | Validates LogoutRequest from the IdP before ending the local session |
| **Saml2LogoutResponseResolver** | Creates LogoutResponse back to the IdP for an AP-initiated LogoutRequest |
| **RelyingPartyRegistration** | Holds SP/IdP config, SLO endpoints, signing/verification credentials |
| **LogoutHandler** | Clears SecurityContext/HttpSession and local resources per policy |

Spring Security documentation explains that **the LogoutRequest sent by the SP is stored in the session** to match RelayState and LogoutResponse's InResponseTo. When swapping the repository for cluster support, correlation and single-use semantics must be preserved.

**Custom validators must never skip default verification steps.** To add custom request/response validation policies, delegate to the version-appropriate Spring/OpenSAML validator first and then add custom checks. Never treat Status=Success or valid Issuer text as equivalent to signature verification.

## 11. Spring Boot 3 + Spring Security 6 Example: Enabling SLO in the Right Place

The example uses **Spring Boot 3.x compatible with Spring Security 6.x**, Java 17+, Servlet MVC. Running end-to-end requires a **real IdP with SingleLogoutService in metadata**, an SP properly registered with entityID/SLO URL, an SP **PKCS#8** private key, and a matching X.509 signing certificate. Domains using **example.org** are illustrative, not public services for testing.

### 11.1. Maven Dependencies

In a Maven project with Spring Boot parent/BOM, add:

~~~xml
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
    <groupId>org.springframework.security</groupId>
    <artifactId>spring-security-saml2-service-provider</artifactId>
  </dependency>
</dependencies>
~~~

OpenSAML/transitive artifacts should use versions managed by Spring Security/Boot; never arbitrarily mix legacy Spring SAML Extension with modern **saml2Logout()** configuration.

### 11.2. application.yml

**src/main/resources/application.yml**:

~~~yaml
spring:
  security:
    saml2:
      relyingparty:
        registration:
          company:
            assertingparty:
              metadata-uri: https://idp.example.org/metadata
            signing:
              credentials:
                - private-key-location: file:/run/secrets/sp-signing-pkcs8.pem
                  certificate-location: file:/run/secrets/sp-signing-cert.pem
            singlelogout:
              url: "{baseUrl}/logout/saml2/slo"

server:
  servlet:
    session:
      timeout: 30m
~~~

**Explanation:**

- **registration.company** creates a RelyingPartyRegistration with registrationId=company.
- **assertingparty.metadata-uri** specifies the controlled source of IdP metadata, which must have **SingleLogoutService** to use SLO; IdP metadata also publishes the verification certificate.
- **signing.credentials** loads the SP private key/certificate to sign LogoutRequests/LogoutResponses. The private key must be securely managed by the SP, never committed to Git or distributed to SPA/browser clients.
- **singlelogout.url** is the SP endpoint receiving SLO requests/responses and must be published/registered accurately at the IdP.
- **session.timeout** is the local session idle timeout, not a default rule for completing global SLO.

**Warning:** This configuration **illustrates property shape only**. It will not start if IdP metadata does not exist, certificates/keys cannot be read, metadata lacks SLO capability, or the application is not registered at the IdP. In production, load keys from a secret manager/keystore or trusted key management mechanism, and configure HTTPS and public URLs accurately.

### 11.3. Java Application

**src/main/java/com/example/slo/SloApplication.java**:

~~~java
package com.example.slo;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class SloApplication {
    public static void main(String[] args) {
        SpringApplication.run(SloApplication.class, args);
    }
}
~~~

### 11.4. SecurityFilterChain.java

**src/main/java/com/example/slo/SamlSecurityConfig.java**:

~~~java
package com.example.slo;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class SamlSecurityConfig {

    @Bean
    SecurityFilterChain webSecurity(HttpSecurity http) throws Exception {
        http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/", "/error").permitAll()
                .anyRequest().authenticated())
            .saml2Login(Customizer.withDefaults())
            .saml2Logout(Customizer.withDefaults());

        return http.build();
    }
}
~~~

**saml2Login()** enables SAML2 login. **saml2Logout()** enables RP- and AP-initiated SLO. The two methods do not replace each other: for a user to have a SAML session at the SP to log out from, a valid login must happen first.

**No need to manually configure LogoutRequest/LogoutResponse XML in a controller**: Spring Security's filters/resolvers/validators execute the protocol. **Do not disable CSRF application-wide** to make POST `/logout` work; the Logout button form must submit a valid CSRF token.

### 11.5. Controller to Inspect Local Session State

**src/main/java/com/example/slo/SloController.java**:

~~~java
package com.example.slo;

import java.util.Map;
import org.springframework.security.core.annotation.AuthenticationPrincipal;
import org.springframework.security.saml2.provider.service.authentication.Saml2AuthenticatedPrincipal;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class SloController {

    @GetMapping("/")
    public String home() {
        return "SAML SLO example ready";
    }

    @GetMapping("/me")
    public Map<String, String> whoAmI(
            @AuthenticationPrincipal Saml2AuthenticatedPrincipal user) {
        return Map.of(
            "subject", user.getName(),
            "registrationId", user.getRelyingPartyRegistrationId());
    }
}
~~~

This is a controller in a **SAML-login-only** example. If an application allows multiple authentication mechanisms, handle the case where the principal is not a Saml2AuthenticatedPrincipal. In production, do not unconditionally return sensitive NameID/attributes; this endpoint is for learning/testing only.

### 11.6. Running and Testing Properly

In a valid Maven project with JDK 17+:

~~~bash
mvn spring-boot:run
~~~

If the application starts with real metadata/credentials, public endpoint:

~~~bash
curl -i http://localhost:8080/
~~~

Body from controller:

~~~text
SAML SLO example ready
~~~

To test SLO, **complete a real SAML login first** through the configured IdP. Then send **POST /logout** from the browser **with a real CSRF token and session cookie** to initiate RP-initiated SLO. Testing a POST without a token and interpreting HTTP 403 as a SAML error is not recommended.

Observed steps:

1. Network shows POST `/logout` at the SP with valid CSRF.
2. The SP creates a **LogoutRequest with its own ID**, signs it, and directs the browser to the IdP SLO endpoint.
3. The IdP validates it, performs logout, and may send LogoutRequests to other SPs.
4. The IdP sends a **LogoutResponse** to **/logout/saml2/slo** with InResponseTo pointing to the SP-created request's ID.
5. The SP validates it and redirects to the result page depending on Status and configuration.
6. Reopen **/me**: if the SP local session has ended, re-authentication at the SP is required. If the IdP still has an SSO session because SLO did not complete, the user may be logged in quickly via a new SAML round.

**There is no fixed stdout for LogoutRequest/LogoutResponse XML** because ID, IssueInstant, signature, endpoint, NameID, and SessionIndex all depend on the real session. Never copy a production user's Base64 SAMLResponse string into public debugging tools.

## 12. Separating Local Logout and Single Logout in Spring Security

### Local Logout Only

If configuring regular **.logout()** without enabling `saml2Logout()` for the registration, POST `/logout` can:

- clear the SP's SecurityContext;
- invalidate the HttpSession;
- run internal logout handlers;
- redirect to the logout success URL.

It **does not send a LogoutRequest to the IdP**. Thus the IdP may still retain the SSO session; a user revisiting the SP may be issued a new SAMLResponse without entering a password.

### True SLO

When SLO is properly configured, the SP builds a **LogoutRequest**, the IdP validates and processes it, and depending on the flow returns a **LogoutResponse**. These are protocol messages, not merely deleting cookies.

To separate the path for **local logout** from **SP-initiated SLO**, Spring Security supports configuring it as follows, as a replacement snippet in the same SecurityFilterChain:

~~~java
http
    .logout(logout -> logout.logoutUrl("/logout"))
    .saml2Logout(saml -> saml.logoutUrl("/saml2/logout"));
~~~

This is a **fragment**, not a standalone Java class. In that configuration **POST /logout** deletes the local session while **POST /saml2/logout** initiates SLO per policy. Both paths must have proper CSRF protection; never use a plain GET link in place of a state-changing logout action.

### Do Not Misinterpret Outcomes

- **SP local session deleted** does not mean all other SPs deleted theirs.
- **Matching LogoutResponse.InResponseTo** does not mean Status=Success.
- **Status=Success** from one branch does not prove every browser, device, or node ended if the deployment does not track those sessions.
- **LogoutRequest sent** does not mean the IdP received and executed it.
- **Browser closing the tab mid-flow** can interrupt the SLO cascade; supplemental UI, monitoring, and session policies are needed.
- **Single Logout** differs from **OIDC RP-initiated Logout**, OAuth token revocation, and HTTP session invalidation; never use an OIDC logout endpoint as a SAML SLO endpoint.

## 13. Runnable Java 17: Simulating Request/Response Correlation and Replay Protection

The sample below **does not parse SAML XML and does not verify signatures**; it only simulates the rules:
**(1)** LogoutResponse.InResponseTo matches pending LogoutRequest.ID; **(2)** Issuer is the expected party; **(3)** single-use processing only; **(4)** only Status=Success yields a successful illustrative transaction outcome.

**File: LogoutMessageCorrelation.java**

~~~java
import java.util.Map;
import java.util.concurrent.ConcurrentHashMap;

public final class LogoutMessageCorrelation {

    record Pending(String id, String expectedIssuer) { }

    record Reply(
        String id,
        String inResponseTo,
        String issuer,
        String status) { }

    private final Map<String, Pending> pending =
        new ConcurrentHashMap<>();

    void save(Pending request) {
        pending.put(request.id(), request);
    }

    boolean complete(Reply response) {
        if (response == null || response.inResponseTo() == null) {
            return false;
        }

        Pending request = pending.get(response.inResponseTo());

        if (request == null
                || !request.expectedIssuer().equals(response.issuer())
                || !"Success".equals(response.status())) {
            return false;
        }

        return pending.remove(request.id(), request);
    }

    public static void main(String[] args) {
        LogoutMessageCorrelation flow = new LogoutMessageCorrelation();
        flow.save(new Pending("_LOUT_1", "trusted-idp"));

        System.out.println("wrongRequest=" + flow.complete(
            new Reply("_R_1", "_OTHER", "trusted-idp", "Success")));
        System.out.println("wrongIssuer=" + flow.complete(
            new Reply("_R_2", "_LOUT_1", "other-idp", "Success")));
        System.out.println("success=" + flow.complete(
            new Reply("_R_3", "_LOUT_1", "trusted-idp", "Success")));
        System.out.println("replay=" + flow.complete(
            new Reply("_R_3", "_LOUT_1", "trusted-idp", "Success")));

        flow.save(new Pending("_LOUT_2", "trusted-idp"));
        System.out.println("partialSuccess=" + flow.complete(
            new Reply("_R_4", "_LOUT_2", "trusted-idp", "PartialLogout")));
    }
}
~~~

Compile/run with JDK 17+:

~~~bash
javac LogoutMessageCorrelation.java
java LogoutMessageCorrelation
~~~

**Deterministic stdout:**

~~~text
wrongRequest=false
wrongIssuer=false
success=true
replay=false
partialSuccess=false
~~~

Explanation:

- **wrongRequest:** response references a request not in the repository.
- **wrongIssuer:** InResponseTo matches, but the reply came from an unexpected party.
- **success:** illustrative correlation and Status are both valid; the pending request is consumed via **remove(key, expected)**.
- **replay:** the request was already consumed, so the old response cannot complete again.
- **partialSuccess:** full logout completion cannot be concluded from PartialLogout alone.

**Warning:** The logic above **does not replace** SAML LogoutResponseValidator. It does not check signatures, XML schema, bindings, Destination, timestamps, RelayState, session binding, certificate rotation, or multi-SP state. Only call a completion method after a trusted validator has verified the entire message; real Spring Security applications should use standard `saml2Logout()`.

## 14. Replay Protection and Transaction Correlation

### 14.1. Why Store LogoutRequest?

Suppose an attacker saves a validly signed LogoutResponse from an earlier transaction. If the SP accepts the response again merely because the signature is valid, it could display "logout succeeded" for a non-existent transaction, corrupting audit/flows and potentially causing session confusion.

How to handle:

1. When the **SP emits a LogoutRequest**, store request ID, IdP/registration, binding, RelayState, issuance time, expiration, and minimal data needed for verification.
2. When the **LogoutResponse returns**, verify signature/issuer/destination and match **InResponseTo** against the exact pending request.
3. **Consume** the pending request once, preventing concurrency/replay issues per repository capabilities.
4. Implement a TTL/cache and cleanup strategy for requests that never receive a response (user closes tab, IdP times out).
5. Across multiple nodes, the pending request repository must be shared/synchronized with appropriate atomic operations.
6. Report SLO success only when both correlation and accepted status conditions are met.

### 14.2. For IdP-Initiated Requests

The SP did not previously emit a LogoutRequest to match against. Instead, the SP **verifies the inbound LogoutRequest**, issuer/registration, target session, and replay ID of the IdP-issued request. After performing logout, the SP creates **LogoutResponse.InResponseTo = that exact LogoutRequest.ID**.

Do not insert IdP-initiated requests into the pending request repository meant for SP-emitted requests indiscriminately. Each direction has different traffic and initiators.

### 14.3. Mistakes When Using RelayState

- Treating RelayState as a username or authentication proof.
- Letting the browser specify a post-logout redirect URL without an allowlist.
- Looking up requests by RelayState while skipping issuer/binding/ID checks.
- Storing pending requests in a global cache without transaction/session binding and TTL.
- Failing to remove requests after consumption.
- Losing the repository when the local session is invalidated between sending LogoutRequest and receiving LogoutResponse.

For a custom implementation, understand **Spring's request-storage lifecycle** before swapping to Redis/DB caching, and never assume every distributed storage option is security-equivalent to HttpSession.

## 15. Common Operational Errors

| Symptom | Possible Cause | How to Handle |
| --- | --- | --- |
| Logged out at SP, IdP still logged in | Local logout only; SLO not enabled or IdP unsupported | Verify `saml2Logout()`, `SingleLogoutService` metadata, signing credentials |
| Clicking logout returns 403 | Missing CSRF token on POST `/logout` or wrong security matcher | Check form/session/CSRF; do not disable CSRF site-wide |
| IdP rejects LogoutRequest | SP signing key/certificate untrusted; wrong Issuer/NameID/SessionIndex | Cross-check SP metadata, IdP registration, and policy |
| SP receives LogoutResponse but returns 400 | Signature, issuer, destination, status, or InResponseTo failed | Inspect sanitized validation errors, cross-check pending request |
| LogoutResponse.InResponseTo mismatch | Response belongs to another request or pending repository lost | Check ID, RelayState, node/session, latency, callback path |
| AP-initiated LogoutRequest rejected | Wrong signature/Issuer/Destination; user/session mismatch | Check IdP metadata, SLO endpoint, and session correlation |
| Session reappears quickly after logout | Local logout succeeded but IdP session remains | Check IdP SLO and peer SP states; do not rely solely on UI |
| One SP logged out, another SP stays active | IdP orchestration failed, third SP offline, browser stopped | Handle PartialLogout, timeout policy, user warning |
| SessionIndex mismatch | Session mapping lost/altered; IdP issued different value | Check IdP/NameID/SessionIndex contract and session registry |
| SLO endpoint 404/405 | Wrong binding/method or endpoint missing from SecurityFilterChain | Check `/logout/saml2/slo`, SingleLogoutService, and DSL |
| Valid signature but wrong Issuer | Trust confusion between company/partner IdPs | Bind registration/issuer and certificate to the exact partner |
| After returning LogoutResponse, browser never returns to SP | AP-initiated flow controlled by IdP; browser leaves SP | Do not assume SP success handler will render a landing page |
| Callback after local session invalidation cannot find request | Custom repository/logout handler deleted pending state too | Use request storage compatible with the standard SLO lifecycle |
| Multiple nodes: one node logs out while other nodes stay active | Local-only sessions, unsynchronized logout | Spring Session/shared store, session registry, revocation policy |
| Reverse proxy causes Destination mismatch | Public scheme/host/port differs from internal | Fix forwarded headers via trusted proxy, public SLO URL, and metadata |

In real logs, never dump **SAMLRequest**, **SAMLResponse**, XML containing NameID/SessionIndex, signing private keys, cookies/session IDs, or other personal data. Log redacted correlation ID, registrationId, and validation status.

## 16. Essential Test Cases

### 16.1. SP-Initiated

1. User has a valid SAML login; **POST /logout** with valid CSRF → local session invalidated, SP emits signed LogoutRequest.
2. LogoutRequest has **SP Issuer, IdP SLO Destination**, unique ID, and NameID/SessionIndex matching IdP capability.
3. IdP LogoutResponse has **matching InResponseTo**, valid signature, and Status=Success → flow completes per configuration.
4. **Wrong InResponseTo**, even if the rest of the message is signed → must be rejected.
5. **Wrong Issuer/certificate** despite matching InResponseTo → rejected.
6. **Status=PartialLogout/Responder/Requester** → do not display "all applications logged out successfully".
7. **Replaying LogoutResponse** after consumption → rejected/not processed twice.
8. Browser closes tab after SP deletes session but before IdP responds → SP stays locally logged out; global status is not promised.
9. IdP lacks SingleLogoutService in metadata → configuration cannot silently assume complete SLO.
10. New SP signing key while IdP certificate is not yet updated → detected/recovered via rotation plan.

### 16.2. IdP-Initiated

1. IdP sends signed **SAMLRequest** to SP SLO endpoint; SP verifies and logs out the matching session, returning LogoutResponse.
2. SP's LogoutResponse must have **InResponseTo = the IdP's LogoutRequest.ID**, not the login AuthnRequest.ID.
3. Request with non-matching/cross-tenant **NameID** → do not destroy wrong session.
4. Request with different **SessionIndex** → handle per profile and policy; do not confuse with JSESSIONID.
5. Request from non-allowlisted **IdP** → reject even if XML is validly self-signed.
6. Replaying already-processed LogoutRequest → do not destroy additional out-of-scope sessions.
7. No local session or already logged out → respond with status per contract without impersonating a user.
8. Cross-site POST callback drops cookie → check SameSite and session binding; do not bypass signature/authorization.
9. Multiple sessions across nodes/devices → verify single-session vs. multi-session logout policy, session store, and registry.
10. IdP sends request with a binding the SP does not support → error handled explicitly and tested for interoperability.

### 16.3. Operational Reliability

- Test **HTTP-POST vs. Redirect binding** per IdP-supported config; do not guess they behave identically.
- Cross-check public SLO URL, SP metadata, Issuer, and Destination through the reverse proxy.
- Test network failures between SP sending request and IdP sending response.
- Test UX when SP local logout succeeded while global logout remains unconfirmed.
- Verify session revocation across **multiple app instances**, not just the request-handling node.
- Test certificate rollover (old/new verification certificates) and trust expiration.
- Monitor counts of **SLO requests**, **SLO successes**, **validation failures**, **PartialLogout**, timeouts, and orphaned pending requests.

## 17. Production Deployment Checklist

- [ ] Real IdP genuinely supports **SAML Single Logout**, metadata has SingleLogoutService, and binding is compatible.
- [ ] SP has valid **signing private key/certificate** trusted by the IdP; SP trusts approved IdP signing cert.
- [ ] **saml2Login()** and **saml2Logout()** enabled in the right SecurityFilterChain for browsers.
- [ ] **/logout/saml2/slo** URL, SingleLogoutService, SP entityID, and reverse proxy public scheme/host align.
- [ ] Distinguish **SP-initiated** and **IdP-initiated**; whichever party issues LogoutRequest, the other returns LogoutResponse.
- [ ] **LogoutResponse.InResponseTo** matches the corresponding **LogoutRequest.ID**, not LogoutResponse.ID or AuthnRequest.ID.
- [ ] Verify signature, Issuer, Destination, binding, timestamps, and Status; match NameID/SessionIndex per contract.
- [ ] SP saves/consumes pending LogoutRequest properly; RelayState is controlled and replay is rejected.
- [ ] **SessionIndex** is not confused with HttpSession ID; session registry/shared store exists if multi-session logout is required.
- [ ] If the IdP coordinates multiple SPs, understand **PartialLogout** and global limits of returned statuses.
- [ ] Never relax validation to "fix" mismatches or cookie/metadata errors.
- [ ] POST `/logout` has CSRF protection; no GET logout shortcuts or open arbitrary redirects.
- [ ] Local logout and global SLO have distinct UX/auditing; never claim global success without evidence.
- [ ] Policies exist for timeouts, rollback, credential rotation, multiple IdPs/tenants, and network outages.
- [ ] Tested wrong InResponseTo, wrong issuer, wrong session, replay, partial status, IdP outage, proxy, and multi-node.
- [ ] Never log raw SAML XML, NameID/SessionIndex/cookies/private keys, or sensitive data.

**Closing takeaway:** A **LogoutRequest** always has an ID to identify which request is being executed. **LogoutResponse.InResponseTo** must point to the **ID of the direct LogoutRequest it is answering**, while carrying a **Status** reflecting the outcome. SAML Single Logout can be initiated by the **SP** or the **IdP**; in both cases, signature, issuer, destination, target session, and correlation are essential. Spring Security provides **`saml2Logout()`** and dedicated filters/resolvers/validators, but applications must still respect the limits when logout spans multiple SPs and networks.

## 18. References

- [Spring Security 6.5 – Performing Single Logout](https://docs.spring.io/spring-security/reference/6.5/servlet/saml2/logout.html): RP/AP-initiated SLO, filters, endpoints, resolvers, request repository, signing, and validation.
- [Spring Security 6.5 – SAML2 Login Overview](https://docs.spring.io/spring-security/reference/6.5/servlet/saml2/login/overview.html): RelyingPartyRegistration, SAML principal, and login flow prior to logout.
- [Spring Security 6.5 – SAML2 Metadata](https://docs.spring.io/spring-security/reference/6.5/servlet/saml2/metadata.html): SP/IdP metadata and endpoint details.
- [OASIS – SAML 2.0 Core Specification](https://docs.oasis-open.org/security/saml/v2.0/saml-core-2.0-os.pdf): LogoutRequestType, LogoutResponse, status codes, NameID, and SessionIndex.
- [OASIS – SAML 2.0 Profiles Specification](https://docs.oasis-open.org/security/saml/v2.0/saml-profiles-2.0-os.pdf): Web Browser Single Logout Profile, request/response requirements, and bindings.
- [OASIS – SAML Technical Overview (HTML)](https://docs.oasis-open.org/security/saml/Post2.0/sstc-saml-tech-overview-2.0.html): SP-initiated logout flow across multiple SPs.
- [Microsoft identity platform – SAML Single Sign-Out Protocol](https://learn.microsoft.com/en-us/entra/identity-platform/single-sign-out-saml-protocol): LogoutRequest/LogoutResponse and InResponseTo examples.
