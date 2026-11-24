# Distinguishing Local Logout from Federated Single Logout in SAML 2.0

> **Topic:** Spring Security – federation · **Group:** SAML2 Logout. This lesson explains the boundary between **local logout** at a single Service Provider and **SAML 2.0 Single Logout (SLO)** across the federation relationship, how Spring Security Servlet handles both flows, NameID/SessionIndex fields, required metadata and certificates, limitations of "logout everywhere", how to test, and troubleshooting.

## 1. Why Is "Logout" an Architectural Decision?

A user logs in to **application A** (Spring Security Service Provider, SP A) through an **Identity Provider (IdP)** and simultaneously accesses **application B** (SP B) with the same IdP. At that point, three different sessions may exist:

- **Local session at SP A:** usually tied to HttpSession/cookie, Spring SecurityContext, and the Authentication created from the SAML Assertion.
- **SSO session at the IdP:** allows the IdP to authenticate the user for a certain period, even after one SP has cleared its own session.
- **Local session at SP B:** owned by SP B, with its own cookie, TTL, and session repository.

If A only clears its own session, the IdP and B **may still remain logged in**. When returning to A, the browser goes to the IdP and the IdP may issue a new SAMLResponse without asking the user to re-enter a password. Therefore, users easily think "I logged out yet it automatically logged me back in".

Conversely, **SAML Single Logout** is a **cooperative protocol**, in which SPs and the IdP send `LogoutRequest`/`LogoutResponse` messages to attempt to close related sessions. SLO is not a mechanism for JavaScript to delete cookies of every domain and does not by default revoke all JWT/API tokens or all sessions on other devices.

**Remember:**
- **Local logout = ending the Authentication/session only in the current SP application.**
- **Federated Single Logout = requesting the participants in the SAML relationship to close their corresponding sessions; the outcome depends on each party's processing capability and response status.**

A good product should clearly state whether the user is **"Logging out of this application"** or **"Logging out of the federated SSO session"**.

## 2. Terminology and Session Objects

| Term | Practical Definition |
|---|---|
| **Service Provider (SP/Relying Party)** | A Java Spring Security application authenticating via an Assertion from an IdP |
| **Identity Provider (IdP/Asserting Party)** | The system authenticating users and coordinating SSO/SLO if supported |
| **Local Logout** | Runs logout handlers and terminates the SP's session/SecurityContext |
| **SAML 2.0 Single Logout (SLO)** | Protocol requesting termination of related SAML sessions |
| **RP-initiated SLO** | SP-initiated; sends a LogoutRequest to the IdP |
| **AP-initiated SLO** | IdP-initiated; sends a LogoutRequest to the SP |
| **`LogoutRequest`** | Logout message containing Issuer, ID, NameID, SessionIndex, and protocol fields |
| **`LogoutResponse`** | Response result containing StatusCode and usually InResponseTo |
| **`NameID`** | Subject identifier used by the IdP in the SAML Assertion and logout |
| **`SessionIndex`** | SAML session index in AuthnStatement, which can be used to select the session to log out |
| **`InResponseTo`** | References the ID of the LogoutRequest that the LogoutResponse is answering |
| **`RelayState`** | Binding parameter used to preserve state/correlation, not an automatically trusted URL |
| **`SingleLogoutService`** | Endpoint/binding published in SAML metadata |
| **`PartialLogout`** | Status indicating the process could not terminate all participants |
| **`RelyingPartyRegistration`** | Registration of SP↔IdP trust, SLO endpoints, and credentials in Spring Security |

**Important:** `SessionIndex` is **not** the application's `JSESSIONID` or `HttpSession.getId()`. `LogoutRequest.ID` is also not SessionIndex. They serve different responsibilities; mixing them up causes logging out the wrong user or failing to correlate responses.

## 3. Comparison Table: Local Logout vs. SAML SLO

| Criterion | Local Logout | Federated SAML Single Logout |
|---|---|---|
| Initiation point | Logout button in one SP | SP or IdP per the SLO profile |
| SAML messages | Not required | LogoutRequest and LogoutResponse |
| Current session at SP | Usually invalidated | Invalidated as part of the process |
| IdP SSO session | Usually **preserved** | IdP is requested to terminate the matching session |
| Session at other SPs | Usually **preserved** | May be notified by the IdP and requested to close |
| Depends on IdP SLO support? | No | Yes |
| Requires SAML signing credential? | Not specifically for local logout | Usually required for signed requests/responses |
| Requires NameID/SessionIndex? | Not specifically for local logout | Yes, to identify the subject/session |
| Has SLO status confirmation? | No | May have Success/PartialLogout/failure/no response |
| Depends on browser and multiple endpoints | Less | Yes; especially front-channel Redirect/POST |
| Silent re-login via IdP | Can happen | Less likely if the IdP session actually ended |
| Revokes all access tokens/JWTs? | Not automatically | Also not automatically |
| Clears sessions on other devices? | No | Not guaranteed by default |
| Accurate UI message | "Logged out of this application" | "Federated logout confirmed/in progress/incomplete", depending on result |

The word **"Single"** in Single Logout refers to **a coordinated process** within a federation, not a cryptographic promise that every application, every browser, and every token has been invalidated.

## 4. How Does Local Logout Work in Spring Security Servlet?

### 4.1. What Happens on POST /logout?

In a Spring Security Servlet application, with standard logout configuration and CSRF enabled, an authorized `POST /logout` typically:

1. Invokes the filter chain's `LogoutHandler` instances.
2. Invalidates the current HttpSession, per the default configuration for session-based authentication.
3. Clears or empties the `SecurityContext` and Authentication associated with the session.
4. Handles the CSRF token and other logout handlers.
5. Invokes the `LogoutSuccessHandler` or redirects to the success URL (for example `/login?logout`).

Common components include `SecurityContextLogoutHandler`, which handles session invalidation/clearing authentication. If the application uses custom cookies, remember-me, or its own tokens, specialized logout handlers may be needed; **clearing SecurityContext does not automatically revoke all out-of-session tokens**.

You must not assume that deleting the HttpSession deletes the browser cookie immediately. The `JSESSIONID` cookie may remain in the browser while referencing an invalidated session; the application can configure appropriate cookie cleanup. Do not confuse "the cookie is still visible" with "the session is still alive".

### 4.2. Local Logout Diagram

~~~text
Browser                      Spring SP A                    IdP             SP B
   |                            |                           |               |
   | POST /logout + CSRF        |                           |               |
   +--------------------------->|                           |               |
   |                            | Invalidate HttpSession    |               |
   |                            | Clear SecurityContext     |               |
   |<---- /signed-out ----------+                           |               |
   |                                                        |               |
   |            No SAML LogoutRequest sent to IdP           |               |
   |            IdP session / SP B session may remain alive |               |
~~~

If the browser subsequently accesses a page requiring Authentication at SP A, SP A may redirect to the IdP and receive a new Assertion using the **still-alive SSO session**. This is why local logout does not satisfy a "log out of all applications" requirement.

### 4.3. When Is Local Logout Appropriate?

- The user only wants to exit the current application without disrupting other systems.
- The IdP does not support SAML SLO or the system has not yet verified stable SLO.
- Organizational policy intentionally separates "leaving the application" from "ending the entire SSO session".
- The application handles its own business session and the user needs to keep sessions on other sites.
- There is a separate button asking the user to confirm if they want to terminate federated sessions.

**Limitation:** If the computer is shared or the security requirement is to end the IdP session, local logout alone is insufficient. You need to evaluate SLO, IdP logout/session revocation, account/session policies, and device management.

## 5. Single Logout Has Two Initiation Directions

Spring Security supports SAML 2.0 SLO in **Servlet Service Provider** applications, covering both **RP-initiated** and **AP-initiated** flows according to the documentation.

### 5.1. RP-initiated: The User Starts Logout at the SP

Overview flow:

~~~text
Browser                  Spring SP A                     IdP                 SP B
  |                          |                          |                   |
  | POST /saml2/logout       |                          |                   |
  +------------------------->|                          |                   |
  |                          | Clear A local session    |                   |
  |                          | Create/signed            |                   |
  |                          | LogoutRequest            |                   |
  |<----- Redirect / form ---+                          |                   |
  +------------------------------- LogoutRequest ------>|                   |
  |                                                     | Verify request    |
  |                                                     | End IdP session   |
  |                                                     +-- LogoutRequest ->|
  |                                                     |                   | Verify/clear
  |                                                     |<-- LogoutResponse-+
  |<-------------------- LogoutResponse -----------------+                   |
  +--- POST /logout/saml2/slo --> SP A                                      |
  |                                  Verify signature, status, correlation  |
  |<----------------------------- Final page (if callback is valid) --------+
~~~

According to the Spring Security documentation, when SLO **is enabled with default configuration**, a `POST /logout` can **trigger RP-initiated SLO**: the SP runs the logout handlers and then creates a SAML LogoutRequest and redirects to the IdP. This differs from configuring only regular logout.

**Therefore:** To provide both **local** and **federated logout**, use **two separate endpoints**, as shown in the configuration in section 9.

### 5.2. AP-initiated: The IdP Requests SP Logout

~~~text
IdP / Browser                   Spring SP A
    |                                 |
    +----- signed LogoutRequest ----->|
    |                                 | Verify issuer/signature
    |                                 | Validate destination,
    |                                 | NameID/SessionIndex, replay
    |                                 | Invalidate matching local session
    |                                 | Create signed LogoutResponse
    |<----------- LogoutResponse -----+
    |
    +----- IdP coordinates to other SPs if any
~~~

The SP receives an IdP-initiated LogoutRequest at the SLO endpoint, validating it thoroughly before deleting the matching session. After the SP returns a LogoutResponse, **the browser is under the IdP's control**, so you cannot assume the SP's redirect success page will be the final page the user sees.

**Implementation note:** Some providers use HTTP-Redirect for SLO, some use HTTP-POST, and back-channel SOAP may exist. Not all IdPs/SPs support the same bindings; you must check metadata and partner documentation. Spring Security Servlet SLO is a specific feature and does not automatically support every profile/binding in the standard.

## 6. What Does a LogoutRequest Contain?

Simplified XML sample **to illustrate fields**, without real signatures/sufficient metadata, so **do not use it as a production SAML message**:

~~~xml
<samlp:LogoutRequest
    xmlns:samlp="urn:oasis:names:tc:SAML:2.0:protocol"
    xmlns:saml="urn:oasis:names:tc:SAML:2.0:assertion"
    ID="_logout_request_001"
    Version="2.0"
    IssueInstant="2026-11-07T04:00:00Z"
    Destination="https://idp.example.org/saml/slo">
  <saml:Issuer>https://portal.example.org/saml/sp</saml:Issuer>
  <saml:NameID
      Format="urn:oasis:names:tc:SAML:2.0:nameid-format:persistent">
    stable-subject-id
  </saml:NameID>
  <samlp:SessionIndex>_session_100</samlp:SessionIndex>
</samlp:LogoutRequest>
~~~

Elements to understand:

| Field | Meaning |
|---|---|
| `ID` | Message identifier to correlate LogoutResponse and prevent reuse/replay |
| `IssueInstant` | Timestamp when the request was issued |
| `Issuer` | EntityID of the requesting party (SP or IdP) |
| `Destination` | Registered SLO endpoint of the receiving party |
| `NameID` | SAML identity whose session is to be closed, with appropriate format/qualifiers |
| `SessionIndex` | One or more corresponding SAML session indexes |
| `Reason` | Logout reason if used by the sender |
| `NotOnOrAfter` | Processing expiration limit if included |
| Signature / integrity protection | Proves the requester and protects against message tampering per binding/profile |

**NameID must match the logged-in session.** If the IdP issues a persistent/opaque NameID, but the SP customizes the principal into an email or employee code and then uses the wrong identifier for logout, the IdP may fail to match the session. For session participants, the SAML SLO profile has requirements on using SessionIndex; consult the actual profile rather than sending arbitrarily.

A SAML signature over **HTTP-Redirect** can be placed in query binding parameters `Signature`/`SigAlg`, not necessarily as an XMLDSig element like HTTP-POST. Do not treat an XML sample lacking ds:Signature as a trusted request.

## 7. LogoutResponse: Which Results Can Be Trusted?

Simplified XML sample, without real signatures:

~~~xml
<samlp:LogoutResponse
    xmlns:samlp="urn:oasis:names:tc:SAML:2.0:protocol"
    xmlns:saml="urn:oasis:names:tc:SAML:2.0:assertion"
    ID="_logout_response_001"
    Version="2.0"
    IssueInstant="2026-11-07T04:00:03Z"
    InResponseTo="_logout_request_001"
    Destination="https://portal.example.org/logout/saml2/slo">
  <saml:Issuer>https://idp.example.org/entity</saml:Issuer>
  <samlp:Status>
    <samlp:StatusCode
        Value="urn:oasis:names:tc:SAML:2.0:status:Success"/>
  </samlp:Status>
</samlp:LogoutResponse>
~~~

Required checks at the SP:

1. The response is issued by a **trusted IdP** with appropriate signature/binding integrity protection.
2. `Issuer` matches the registration's IdP party.
3. `Destination` matches the public SLO endpoint.
4. `InResponseTo` matches the `LogoutRequest.ID` still stored by the SP for the corresponding flow.
5. `RelayState` is verified/matched when required by the binding/policy.
6. `StatusCode` is genuinely valid and part of a verified result.
7. Replay, expiration, duplicate IDs, and state are checked per profile, without reusing callbacks.

**You cannot trust a LogoutResponse just because the string `Success` appears in the XML**; the browser can send any payload. Signature, trust, correlation, and status outcome must go together.

### 7.1. SLO Statuses and Honest Result Reporting

| What Happened | What We Can Conclude | What We Should Not Conclude |
|---|---|---|
| Spring invalidated the local session | The current SP is logged out | The IdP and other SPs are logged out |
| Browser was redirected to the IdP SLO URL | Message transfer has been initiated | The IdP processed it successfully |
| Valid LogoutResponse with Status=Success | The IdP reported the applicable flow succeeded | All devices/non-SAML tokens have been revoked |
| `PartialLogout` received | Part of the federation could not confirm completion | "Logged out of all applications" |
| No LogoutResponse received | Federation outcome is unknown | The IdP definitely did not log out |
| Response has invalid signature/InResponseTo | Result cannot be considered trustworthy | Success just because HTTP 200 was returned |
| SP B is offline/lacks SLO | No guarantee B ended the session | SLO always clears every cookie |

A Status Success response is a protocol result **within the scope of supported IdP/participants**, not proof regarding API keys, sessions on other devices, or non-SAML services.

## 8. Why SLO Does Not Guarantee Logging Out Everywhere: Specific Reasons

### 8.1. Federation Only Coordinates Participating SPs

The IdP needs to know which SPs have related sessions and be able to send LogoutRequests to them. An SP that does not implement SLO or cannot receive callbacks may still keep its local session. The IdP cannot directly delete cookies of another SP's domain due to browser same-origin/cookie scoping restrictions.

### 8.2. Front-Channel Can Be Interrupted

When SLO uses browser redirect/POST, the following factors can prevent the flow from completing:

- The browser closes the tab, loses network connectivity, or the user navigates away mid-flow.
- `SameSite`, `Secure` cookies, cross-site POST, or browser privacy restrictions.
- A reverse proxy changes scheme/hostname/path causing a `Destination` mismatch.
- SP/IdP have different session timeouts, causing session state to expire early.
- Another SP experiences temporary downtime or returns an error.
- Long logout chains cause timeouts or PartialLogout.

Back-channel via SOAP, if supported by partners, has different characteristics, but also depends on reachability/network trust and implementation support. Do not assume Spring by default supports every SLO binding listed in the standard.

### 8.3. Multiple Browsers and Multiple Devices

One NameID can be bound to multiple SAML SessionIndexes and multiple different HttpSessions. A logout request only takes effect according to the matched subject/session, IdP policy, and the SP's ability to locate corresponding sessions. Logging out from laptop A **does not necessarily** revoke the session on phone B or another browser profile. If "log out all devices" is required, you must design dedicated server-side session invalidation/IdP session revocation.

### 8.4. JWT, OAuth/OIDC, and API Keys Are Out of Scope

An application may use SAML for web login and then issue its own JWT/access tokens for a SPA/API. A SAML LogoutRequest **does not automatically revoke issued JWTs**, refresh tokens, API keys, or OIDC sessions in other systems. TTL, revocation lists, session versioning, introspection, or provider-specific logout APIs are needed depending on the architecture.

**Practice:** In UX and runbooks, specify exactly "which sessions/tokens logout affects" instead of merely writing "global logout".

## 9. Spring Security Configuration: Separating Local Logout and SLO

### 9.1. When Only Local Logout Is Needed

The following Java snippet is a **method fragment** in a Spring Boot Servlet configuration class and requires corresponding imports:

~~~java
@Bean
SecurityFilterChain filterChain(HttpSecurity http) throws Exception {
    return http
        .authorizeHttpRequests(auth -> auth
            .requestMatchers("/", "/signed-out", "/error").permitAll()
            .anyRequest().authenticated())
        .saml2Login(Customizer.withDefaults())
        .logout(logout -> logout
            .logoutUrl("/logout")
            .logoutSuccessUrl("/signed-out"))
        .build();
}
~~~

If SAML SLO is **not** enabled, `POST /logout` only performs local logout via handlers. A protected page accessed afterward may send the browser back to the IdP and SSO again because the IdP session still exists.

### 9.2. Prerequisites for Enabling Federated SLO

Spring Security documentation requires the following conditions:

1. The IdP genuinely supports SAML SLO and its metadata includes `SingleLogoutService`.
2. The SP publishes an SLO callback, typically `{baseUrl}/logout/saml2/slo` per registration.
3. The SP has a **PKCS#8 private signing key + X.509 certificate** to create signed LogoutRequests/LogoutResponses.
4. The IdP trusts the SP public signing cert; the SP trusts the IdP signing verification cert.
5. Both sides agree on the binding and public endpoint URL.
6. The security filter chain enables `saml2Logout` and the registration has an SLO location.
7. Session, NameID, SessionIndex, and LogoutRequest repository/RelayState are properly aligned.

**Note:** Simply calling `.saml2Logout(...)` in code is insufficient if the registration and IdP metadata lack SLO support. Conversely, merely importing metadata containing SingleLogoutService does not automatically activate SLO if the DSL/filter is not enabled.

### 9.3. Illustrative Spring Boot YAML

Example for the `corporate` registration; URLs and certificates are **illustrative** and must be replaced with configurations verified by both sides:

~~~yaml
spring:
  security:
    saml2:
      relyingparty:
        registration:
          corporate:
            entity-id: "https://portal.example.org/saml/sp"
            signing:
              credentials:
                - private-key-location: "file:/run/secrets/saml/sp-signing.key"
                  certificate-location: "file:/run/secrets/saml/sp-signing.crt"
            singlelogout:
              url: "{baseUrl}/logout/saml2/slo"
            assertingparty:
              metadata-uri: "https://idp.example.org/saml/metadata"
~~~

`signing.credentials`: the SP holds the private key and cert, and the IdP receives the public cert to verify LogoutRequests/LogoutResponses. `singlelogout.url`: the **protocol callback** where the SP receives LogoutRequests/LogoutResponses, distinct from the user-trigger endpoint. `assertingparty.metadata-uri`: trusted IdP information, including the SLO service + IdP signing verification credentials.

Property names may vary across Spring Boot/Spring Security versions; always check `Saml2RelyingPartyProperties` and the documentation for the running version. If the IdP provides metadata that does not publish SLO or only supports Redirect binding, compatibility must be checked; do not improvise endpoints/Signers or disable validation to bypass configuration.

### 9.4. Two Separate Endpoints: This Is the Key Configuration

Per the **Separating Local Logout from SAML 2.0 Logout** section of Spring Security:

~~~java
http
    .logout(logout -> logout.logoutUrl("/logout"))
    .saml2Logout(saml2 -> saml2.logoutUrl("/saml2/logout"));
~~~

Behavior when a valid registration/IdP is present:

| HTTP request | Behavior |
|---|---|
| **`POST /logout`** | Local logout only; does not emit a SAML LogoutRequest |
| **`POST /saml2/logout`** | RP-initiated SLO: local logout and emits a LogoutRequest |
| **`POST /logout/saml2/slo`** with `SAMLRequest` | AP-initiated SLO callback from the IdP |
| **`POST /logout/saml2/slo`** with `SAMLResponse` | RP-initiated SLO LogoutResponse callback |

**Very easy to confuse:** Without separating URLs, Spring Security with SLO enabled may use `POST /logout` to initiate federated logout. Therefore, do not infer behavior solely from endpoint names; you must read the actual DSL and registration.

### 9.5. Java Spring Boot Servlet: A Complete Class

The following example is for a Spring Boot project with Spring MVC, Security, and the SAML2 SP module already configured with an IdP. This is a Java class with complete imports, but **does not run standalone with `javac`** when Spring libraries are absent.

File `src/main/java/com/example/sso/LogoutModesApplication.java`:

~~~java
package com.example.sso;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@SpringBootApplication
@RestController
public class LogoutModesApplication {

    public static void main(String[] args) {
        SpringApplication.run(LogoutModesApplication.class, args);
    }

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http)
            throws Exception {
        return http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/", "/signed-out", "/error").permitAll()
                .anyRequest().authenticated())
            .saml2Login(Customizer.withDefaults())
            .logout(logout -> logout
                .logoutUrl("/logout")
                .logoutSuccessUrl("/signed-out"))
            .saml2Logout(saml2 -> saml2
                .logoutUrl("/saml2/logout"))
            .build();
    }

    @GetMapping("/")
    String home() {
        return "SAML SP ready";
    }

    @GetMapping("/private")
    String privatePage() {
        return "Authenticated";
    }

    @GetMapping("/signed-out")
    String signedOut() {
        return "Local session ended";
    }
}
~~~

With a Maven project having Maven Wrapper and required configuration:

~~~bash
./mvnw spring-boot:run
~~~

When the server starts, `GET /` returns body `SAML SP ready` and `GET /signed-out` returns `Local session ended`. For `/private`, a successful SAML login is required. Federated SLO involves multiple network hops, certificates, and browser-specific behavior, so **there is no fixed stdout or redirect endpoint** that can be guaranteed without running against a real IdP.

The code above only defines the user-trigger URLs; the SLO protocol callback is handled by Spring Security filters. **Do not write another controller on the same `/logout/saml2/slo` path** unless you have a specific filter ordering design.

### 9.6. Maven Dependencies

The following snippet belongs **inside `<dependencies>` of a Spring Boot project that already has a BOM or parent**, not a complete pom.xml:

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

Choose consistent versions via the Spring Boot BOM and Spring Security/OpenSAML documentation; depending on the version/build, a corresponding OpenSAML repository may be required. The `saml2Logout()` feature in this lesson is **Servlet**, and cannot be copied verbatim to WebFlux `ServerHttpSecurity`.

### 9.7. UI with Two Logout Buttons

Thymeleaf template example, **not static HTML to be used directly without a template engine**:

~~~html
<form th:action="@{/logout}" method="post">
  <button type="submit">Log out of this application</button>
</form>
<form th:action="@{/saml2/logout}" method="post">
  <button type="submit">Log out of federated SSO session</button>
</form>
~~~

With Spring MVC/Thymeleaf/Spring Security integration, ensure that **the CSRF token is rendered and submitted properly** in each POST (template integrations usually add a CSRF hidden input). If using a SPA or another template engine, you must send the token issued by Spring Security according to policy; do not disable CSRF site-wide just to make the logout button work.

**Do not use GET to perform state-changing logout.** Spring Security may render a confirmation page on GET `/logout`, but the actual operation is normally a CSRF-protected POST.

## 10. Metadata and Certificates: Registration Steps Cannot Be Skipped

### 10.1. IdP Metadata Needs to Contain SingleLogoutService

Illustrative XML format, **incomplete without signatures/certificates**:

~~~xml
<md:EntityDescriptor
    xmlns:md="urn:oasis:names:tc:SAML:2.0:metadata"
    entityID="https://idp.example.org/entity">
  <md:IDPSSODescriptor
      protocolSupportEnumeration="urn:oasis:names:tc:SAML:2.0:protocol">
    <md:SingleLogoutService
        Binding="urn:oasis:names:tc:SAML:2.0:bindings:HTTP-POST"
        Location="https://idp.example.org/saml/slo"/>
  </md:IDPSSODescriptor>
</md:EntityDescriptor>
~~~

The indication that an IdP supports SLO is `SingleLogoutService` in metadata, though you must still verify **binding, Location, signing cert, issuer, and SP registration**. Do not guess the SLO URL from the Login URL; nor should you take the trust key directly from a browser-sent SAMLRequest.

### 10.2. SP Metadata Also Needs the SLO Callback

The SP can publish in `SPSSODescriptor` a `SingleLogoutService` with a Location such as `https://portal.example.org/logout/saml2/slo` and an appropriate Binding. The IdP must be updated to send LogoutRequests/LogoutResponses to the exact public URL. If ingress changes hostname/path, metadata and IdP config must be synchronized.

Three different URLs:
- `/logout`: **local** button under the separated-endpoints configuration.
- `/saml2/logout`: button to **initiate** SLO at the SP.
- `/logout/saml2/slo`: **protocol callback** handling SAMLRequest/SAMLResponse.

### 10.3. Role of Signing Keys

| Message | Private Signing Key | Recipient Public Certificate |
|---|---|---|
| SP → IdP LogoutRequest | Held by SP | IdP trusts SP cert |
| IdP → SP LogoutRequest | Held by IdP | SP trusts IdP cert |
| SP → IdP LogoutResponse | Held by SP | IdP trusts SP cert |
| IdP → SP LogoutResponse | Held by IdP | SP trusts IdP cert |

What is called a "SAML signing cert" is **not automatically the website's TLS certificate**. With HTTP-Redirect, the signature may be in URL query parameters; with HTTP-POST it may be XMLDSig. Always use a verifier matching the binding, trusted metadata, and policy; never automatically trust `ds:KeyInfo` sent by the client.

**Key rollover:** If the IdP rotates its signing certificate before the SP updates trust, incoming LogoutRequests/LogoutResponses will fail. If the SP rotates its signing certificate before the IdP receives the new public cert, the IdP will reject requests. Plan for overlap, testing, and synchronized rotation.

## 11. Security Validation When Receiving LogoutRequest/LogoutResponse

### 11.1. AP-initiated LogoutRequest: Must Validate Before Deleting Session

If an attacker crafts a LogoutRequest XML containing someone else's NameID and POSTs it to the SLO callback, the SP **must not delete the victim's session** just because the Request looks like SAML. It must:

1. Resolve the correct IdP/registration by endpoint and inspected message.
2. Verify signature/binding integrity with the IdP's trusted public key.
3. Verify `Issuer`, `Destination`, timestamps, and ID/replay policy.
4. Match **NameID, Format, and SessionIndex** against the actually related session, rather than matching loosely by email.
5. Invalidate the targeted session only after validation passes.
6. Create a response with signature/status per profile if required by the protocol.
7. Log errors by category without logging raw XML/PII/public cookies.

**Do not disable signature validation** to "make SLO work" when IdP metadata/certificates are wrong. In Spring Security 7, migration docs note improved error `LogoutResponse` handling for invalid LogoutRequests; regression-test response handling after upgrading.

### 11.2. RP-initiated LogoutResponse: Correlate with the Sent Request

LogoutResponse must be correlated with the LogoutRequest created by the SP, typically via:
- `InResponseTo` matching the pending request ID.
- Valid `RelayState`/binding state.
- Matching IdP signer/issuer.
- Destination matching the callback.
- Verified StatusCode that has not been replayed.

Spring Security provides `Saml2LogoutRequestRepository` to store request correlation; by default in the documentation it is tied to the session. Because the local session may be invalidated before the Response returns, you must use a framework-supported mechanism; if using a custom Redis/DB request store, handle TTL, single-use consumption, and tenant context to avoid storing state indefinitely or mixing up users.

**Never treat `StatusCode=Success` in a browser-submitted payload as proof of success before verifying signature/trust/correlation.**

## 12. CSRF and Cookies: Two Different POST Directions

### 12.1. User POSTs Logout at the SP

Local `POST /logout` and SP-triggered `POST /saml2/logout` are state-changing operations requested by the user's browser. They should apply CSRF protection managed by Spring Security. Do not create a GET logout just to avoid tokens, as that creates a risk of **logout CSRF** or forced logout.

### 12.2. IdP Sends SAML POST to the SLO Callback

An incoming IdP LogoutRequest typically does not carry the application form's CSRF token. It is a **SAML protocol callback** authenticated by signature/trust/conditions. Depending on the Spring Security version configuration, the SLO filter and CSRF matcher are specifically integrated. If CSRF exceptions must be configured, restrict them strictly to the SLO callback, not disabling CSRF for business POSTs.

### 12.3. Cross-Site Browser State

During redirects/POSTs from the IdP back to the SP, the browser may enforce:
- Cookie `SameSite`, `Secure`, domain/path attributes.
- TLS termination at a proxy making the public HTTPS URL differ from internal HTTP.
- Third-party-cookie restrictions, iframe restrictions.
- Session affinity in a cluster, and whether the request repository shares state.
- Callback arriving at a different node, or an expired session.

Do not "fix" a missing `InResponseTo` by dropping correlation validation; fix cookie/session/request repository and endpoint configuration instead.

## 13. NameID, SessionIndex, and Logging Out the Right Session

### 13.1. NameID Is Not Always an Email

An Assertion may carry:
- `persistent NameID`: stable identifier per federation.
- `transient NameID`: short-lived, valid only in a specific context.
- `emailAddress`: email that may change or be reused.
- `unspecified`: IdP/SP contract defines format/meaning.

If the application customizes the principal into `employeeCode` or email while the IdP expects LogoutRequests using a persistent NameID, a custom resolver reading `Authentication.getName()` directly may send the wrong identifier and the IdP will fail to identify the session.

### 13.2. SessionIndex Differs from HTTP Session

| ID | Managing Party | Meaning |
|---|---|---|
| `JSESSIONID/HttpSession ID` | SP web container | Local web session |
| `Authentication` | Spring Security SP | Authentication context and authorities |
| `NameID` | SAML/IdP | Federated subject |
| `SessionIndex` | SAML AuthnStatement/IdP | Session known by the IdP and usable for SLO |
| `LogoutRequest.ID` | SAML sender | LogoutResponse correlation |
| `RelayState` | HTTP binding | Restores verified context |

One user can have multiple SessionIndexes. **Do not call `getSessionIndexes().get(0)` if the list is empty**, and do not assume one SessionIndex means "all devices". If the SP must invalidate multiple HttpSessions, design a session registry or store supporting lookup of the exact related sessions and test it in practice.

### 13.3. Spring Security 6.x vs. 7.x

- In Spring Security 6.x APIs, `Saml2AuthenticatedPrincipal` typically carries `getName()`, `getRelyingPartyRegistrationId()`, and `getSessionIndexes()`.
- In Spring Security 7.x, migration documentation notes that Assertion details are decoupled from the principal to support SLO with custom principals; `Saml2AssertionAuthentication`/`Saml2ResponseAssertionAccessor` are preferred in the default flow.
- Custom SLO resolvers that previously cast `Saml2AuthenticatedPrincipal` directly may need updates when upgrading versions.
- Test actual NameID/SessionIndex from the IdP and generated LogoutRequests, rather than merely checking compilation.

Do not mix legacy Spring SAML Extension samples with modern Spring Security.

## 14. SLO Components in Spring Security

| Component | Responsibility |
|---|---|
| `Saml2RelyingPartyInitiatedLogoutSuccessHandler` | Starts RP-SLO after local logout handlers run |
| `Saml2LogoutRequestResolver` | Creates, signs, and serializes LogoutRequest |
| `Saml2LogoutRequestRepository` | Stores state to correlate InResponseTo/RelayState |
| `Saml2LogoutRequestFilter` | Receives/validates AP-initiated LogoutRequest |
| `Saml2LogoutRequestValidator` | Validates issuer, signature, destination, principal/policy |
| `Saml2LogoutResponseResolver` | Creates, signs, and serializes LogoutResponse |
| `Saml2LogoutResponseFilter` | Receives LogoutResponse for RP-SLO |
| `Saml2LogoutResponseValidator` | Validates response signature/issuer/status/correlation |
| `RelyingPartyRegistrationRepository` | Stores metadata/trust/endpoints/signing creds |

Filters can be customized via the DSL, for example the callback URL:

~~~java
http.saml2Logout(saml2 -> saml2
    .logoutRequest(req -> req.logoutUrl("/SLOService.saml2"))
    .logoutResponse(resp -> resp.logoutUrl("/SLOService.saml2"))
);
~~~

**Method fragment only**, does not compile standalone. When changing the callback, you must also update SP metadata, `RelyingPartyRegistration`, and the IdP-stored Logout URL. Changing only the filter path will result in 404 or Destination mismatch.

Custom request repository example:

~~~java
http.saml2Logout(saml2 -> saml2
    .logoutRequest(req -> req
        .logoutRequestRepository(myRepository))
);
~~~

You must provide a `myRepository` object that actually implements the repository interface for the right Spring Security version. The repository must not be just an in-memory Map on a single node if callbacks can reach another node.

## 15. Standalone Java 17: Simulating Certainty Levels

This program **does not sign/parse SAML**; it simulates how outcomes are presented based on **the level externally verified**. The goal is to avoid saying "logged out everywhere" when only local session deletion is known.

File `LogoutScopeDemo.java`:

~~~java
public class LogoutScopeDemo {

    enum Mode { LOCAL, FEDERATED }
    enum Response { SUCCESS, PARTIAL, MISSING }

    static String describe(Mode mode, Response response) {
        if (mode == Mode.LOCAL) {
            return "LOCAL_DONE: only this SP session";
        }
        return switch (response) {
            case SUCCESS ->
                "SLO_REPORTED_SUCCESS: verify protocol scope";
            case PARTIAL ->
                "SLO_PARTIAL: some sessions may remain";
            case MISSING ->
                "SLO_UNKNOWN: only local logout is known";
        };
    }

    public static void main(String[] args) {
        System.out.println(describe(Mode.LOCAL, Response.MISSING));
        System.out.println(describe(Mode.FEDERATED, Response.SUCCESS));
        System.out.println(describe(Mode.FEDERATED, Response.PARTIAL));
        System.out.println(describe(Mode.FEDERATED, Response.MISSING));
    }
}
~~~

Run with JDK 17+:

~~~bash
javac LogoutScopeDemo.java
java LogoutScopeDemo
~~~

Exact stdout:

~~~text
LOCAL_DONE: only this SP session
SLO_REPORTED_SUCCESS: verify protocol scope
SLO_PARTIAL: some sessions may remain
SLO_UNKNOWN: only local logout is known
~~~

**Explanation:**
1. Local mode always concludes only that the SP session has ended; no LogoutResponse is needed.
2. SUCCESS is only an SLO status **reported by a trusted party**. The program assumes the enum has already passed real SAML validation, rather than verifying signatures itself.
3. PARTIAL indicates not all participants completed.
4. MISSING means final confirmation is absent; the IdP may or may not have processed it.
5. Do not restore an invalidated SP session just because LogoutResponse is missing; handle UX and logging appropriately.

**Limitation:** In production, do not trust an enum from an unverified query/HTTP client. Data must come from the Spring Security/OpenSAML SLO validator + request correlation.

## 16. Integration Practice: Testing an IdP and Two SPs

### 16.1. Environment

- A test IdP supporting SAML login, RP-initiated, and AP-initiated SLO over the appropriate bindings.
- SP A is a Spring MVC/Security application with both logout modes enabled.
- SP B uses the same IdP, with its SLO endpoint configured if testing the full federation.
- A test user with an agreed NameID Format/SessionIndex.
- Two separate browser profiles able to inspect HTTP sessions.
- Access to view logs/metadata without dumping raw PII into shared logs.

### 16.2. Positive Tests

| Case | Action | Expected Outcome |
|---|---|---|
| P1 Local | Log in to A/B, POST `/logout` at A | A's session ends; B/IdP are not implicitly affected |
| P2 SSO re-entry | Open a protected route of A after P1 | Can SSO again if the IdP session remains |
| P3 RP-SLO | POST `/saml2/logout` at A | A logs out locally and sends signed LogoutRequest to IdP |
| P4 IdP fan-out | IdP receives valid request | IdP coordinates logout to SP B as supported |
| P5 Peer response | SP B receives LogoutRequest | SP B verifies, closes matching session, returns LogoutResponse |
| P6 SP callback | A receives LogoutResponse | Verifies signature, issuer, InResponseTo, status |
| P7 AP-SLO | Click logout at IdP | A receives/verifies LogoutRequest, closes session, returns LogoutResponse |
| P8 Cluster | Callback returns to another node | Correlation/state remains valid if the app supports it |
| P9 Multiple sessions | User has different browsers/devices | Observe accurately which session scope is actually closed |
| P10 Browser flow | Run with real SameSite/HTTPS/proxy | No state lost due to misconfigured cookies/binding |

### 16.3. Negative Tests

| Case | Fault Test | Expected Outcome |
|---|---|---|
| N1 | IdP lacks SLO support or SingleLogoutService | Do not claim SLO succeeded |
| N2 | SP signs with private key not matching IdP-trusted cert | IdP rejects request |
| N3 | IdP LogoutRequest has forged signature | SP rejects, does not delete wrong session |
| N4 | IdP Issuer/tenant differs from registration | SP rejects |
| N5 | Destination does not match SLO endpoint | SP rejects |
| N6 | NameID/SessionIndex mismatch | Do not log out wrong user/session |
| N7 | Replay old LogoutRequest | Do not re-process against policy |
| N8 | LogoutResponse Status=Success but invalid signature | Do not confirm success |
| N9 | LogoutResponse InResponseTo does not match request | Do not confirm success |
| N10 | SP B offline | Partial/Unknown, do not claim global completion |
| N11 | Browser closed mid-RP-SLO | SP A local done; global status unknown |
| N12 | POST local logout missing CSRF token | Blocked per CSRF policy |
| N13 | GET /logout performs state change | Should not be allowed |
| N14 | IdP rotates signing cert not yet trusted by SP | Fails safely |
| N15 | Logout request repository loses state on another node | Correlation fails; fix store/session |
| N16 | JWT/API token still valid after SLO | Recognize it has a separate lifecycle |
| N17 | IdP only supports Redirect, SP misconfigured for POST | Fix binding, do not disable validation |
| N18 | SP B does not participate in SLO and retains session | Report federation limitation accurately |

Do not rely solely on `MockMvc` with a mocked Authentication to conclude full SLO works. Unit tests for local logout are necessary, but SLO must be tested against a **test IdP and real signed LogoutRequests/LogoutResponses**, error messages, and session correlation.

## 17. Layered Troubleshooting

| Symptom | Possible Cause | How to Check/Fix |
|---|---|---|
| Local logout then immediate SSO | IdP session remains | Check if a LogoutRequest is actually sent; is the goal local only or SLO? |
| POST /saml2/logout only deletes session | Incomplete DSL/per-registration SLO | Check `saml2Logout`, metadata, signing credential |
| IdP rejects LogoutRequest | Wrong signature, NameID, SessionIndex, or Destination | Check signing public cert trusted by IdP, profile/binding |
| Spring rejects IdP LogoutRequest | IdP cert, issuer, destination, session mismatch | Check validator, metadata, and trust |
| 404 SLO callback | IdP sends to wrong URL or filter not enabled | Check `/logout/saml2/slo` / custom URL and ingress |
| Callback response HTTP 400 | Invalid signature/issuer/InResponseTo/status | Check LogoutResponseValidator, request repository |
| LogoutResponse never returns | Browser/network/IdP callback failure | Distinguish local done from global unknown |
| SP A logged out, SP B remains | B offline, unsupported, partial logout | Check IdP logs and B's SLO endpoint |
| 403 when user POSTs /logout | Missing CSRF token | Check form POST/Thymeleaf or SPA CSRF integration |
| Logout succeeds on machine A, machine B remains | Multi-device sessions outside same logout scope | Design IdP/session invalidation for the target goal |
| SLO fails behind proxy | External HTTPS URL differs from internal HTTP URL | Trusted forwarded headers, Recipient/Destination |
| Request correlation lost in cluster | Session/request state not shared | Spring Session or custom repository with TTL |
| Login works, SLO fails | SLO uses separate profile/endpoints/credentials | Do not take SSO success as proof SLO is ready |
| Custom principal breaks IdP NameID recognition | Used local user ID/email instead of original NameID | Check assertion accessor and version-appropriate SLO resolver |
| SLO completes but API still callable | Out-of-HttpSession tokens not revoked | TTL/revocation for API tokens |
| Changing IdP signing key breaks SLO | SP trust not updated with new cert | Metadata rotation plan + validation |

Diagnose in order: **logout mode → actual HTTP endpoint → local session → IdP SLO metadata/binding → SAML signing/trust → LogoutRequest → peer fan-out → LogoutResponse/correlation → session/token scopes**.

Do not fix issues by disabling signature validation, allowing any issuer, or deleting all user sessions when the subject cannot be identified.

## 18. Designing Honest UX and Messaging

### 18.1. Two Purpose-Built Buttons

**"Log out of this application"**:
- POST local logout.
- Does not ask the IdP to end SSO.
- Message: "Ended session in this application. Other applications may still be logged in."
- If returning to the app, automatic login may occur.

**"Log out of linked applications"**:
- POST RP-initiated SLO.
- Clears local session and asks the IdP to coordinate.
- Reports full SLO success only according to **verified response/policy scope**.
- Has clearly explained PartialLogout/Unknown/Failure branches.

### 18.2. Public Computers, Kiosks, and Log Out All Devices

If the risk is the next person using a shared computer, do not rely solely on local logout. You may need to close the IdP SSO session and clear the browser context, as well as manage sessions/devices per policy. **Closing a tab does not automatically delete login cookies**, and SAML SLO does not guarantee tokens on a phone have been revoked. High-compliance applications need a logout/revocation strategy broader than the SAML protocol.

## 19. Operations and Deployment Runbook

### Before Enabling SLO

1. Confirm the IdP supports SingleLogoutService and specific bindings.
2. Finalize the SP public SLO callback, metadata, NameID format, and SessionIndex policy.
3. Configure SP signing private key / public certificate and IdP verification signing keys.
4. Configure `.saml2Logout()` and per-registration SLO location; test two endpoints if separation is needed.
5. Verify CSRF for user-triggered logout and trust/signature for IdP-triggered callbacks.
6. Verify SessionIndex/NameID are not altered when customizing the principal.
7. Test IdP SLO responses + error statuses, browser/cookies/cluster.
8. Alert on timeouts/PartialLogout and log with correlation without exposing PII.
9. Prepare key/metadata rotation and safe rollback plans.
10. Finalize user documentation: local vs. linked logout, unknown scope.

### When an Incident Occurs

- **Prioritize keeping the local session invalidated**; do not "re-log in" on behalf of the user.
- Accurately report that global SLO cannot be confirmed if LogoutResponse is missing/invalid.
- Verify SAML issuer/destination/trusted cert before broadening permissions.
- Check IdP logs and participating SPs, not just SP A logs.
- Do not return raw SAML messages containing NameID/PII to users on error pages.
- During a major outage, you may temporarily fall back to clearly described local logout; **never silently display it as a successful SLO**.

## 20. Review Questions

1. **Does local logout delete the IdP SSO session?** Not by default.
2. **Why does SSO still happen when returning to the app after local logout?** The IdP cookie/session is still alive and can issue a new Assertion.
3. **Does SLO delete SP B's cookies directly from SP A?** No; SP B must participate or another mechanism is required.
4. **How do RP-initiated and AP-initiated differ?** RP starts at the SP; AP starts from the IdP sending a LogoutRequest.
5. **What fields does a LogoutRequest contain?** Issuer, ID, Destination, NameID, SessionIndex, and integrity protection per binding/profile.
6. **What must be checked on a LogoutResponse?** Trusted signature/issuer, Destination, InResponseTo, StatusCode, replay/correlation.
7. **Is SessionIndex the same as JSESSIONID?** No.
8. **With default saml2Logout enabled, what can POST /logout do?** RP-initiated SLO, not just local logout.
9. **How do you separate local and federated logout?** Use `.logout(l -> l.logoutUrl("/logout"))` together with `.saml2Logout(s -> s.logoutUrl("/saml2/logout"))` and proper registration/certs.
10. **What endpoint is `/logout/saml2/slo`?** The protocol callback from the IdP, not a button clicked by the user.
11. **Can logout be sent via GET for simplicity?** No; state-changing logout requires CSRF protection.
12. **Is an unverified LogoutResponse with Status=Success trustworthy?** No.
13. **What does PartialLogout mean?** Could not confirm that all participants completed.
14. **Does a missing LogoutResponse mean the IdP definitely did not log out?** No; the final status is unknown.
15. **Does SLO revoke all API tokens/JWTs?** Not automatically.
16. **Does rotating the IdP signing certificate affect SLO?** Yes, if the SP has not updated its trusted verification keys.
17. **What must be checked when running multiple nodes?** Session store, request repository, correlation/replay, and invalidation.
18. **Why can login work while SLO fails?** SLO requires separate endpoints, bindings, signing creds, and metadata.
19. **Should all HttpSessions with the same email be deleted when receiving a LogoutRequest?** No; you must verify and match issuer+NameID+SessionIndex accurately.
20. **How should success be reported?** Only within the scope of verified SLO messages and actually terminated participants, without claiming all devices/tokens are invalidated.

## 21. Official Documentation

- Spring Security – Performing Single Logout: https://docs.spring.io/spring-security/reference/servlet/saml2/logout.html
- Spring Security – Handling Logout (Servlet): https://docs.spring.io/spring-security/reference/servlet/authentication/logout.html
- Spring Security – SAML 2.0 Login Overview: https://docs.spring.io/spring-security/reference/servlet/saml2/login/overview.html
- Spring Security – SAML 2.0 Migrations (SLO error response, assertion accessor): https://docs.spring.io/spring-security/reference/migration/servlet/saml2.html
- Spring Security – CSRF Protection (Servlet): https://docs.spring.io/spring-security/reference/servlet/exploits/csrf.html
- Spring Security – Session Management: https://docs.spring.io/spring-security/reference/servlet/authentication/session-management.html
- OASIS – SAML 2.0 Profiles, Single Logout Profile: https://docs.oasis-open.org/security/saml/v2.0/saml-profiles-2.0-os.pdf
- OASIS – SAML Core, LogoutRequest/LogoutResponse and StatusCode: https://docs.oasis-open.org/security/saml/v2.0/saml-core-2.0-os.pdf
- OASIS – SAML Technical Overview (multiple SPs): https://docs.oasis-open.org/security/saml/Post2.0/sstc-saml-tech-overview-2.0.html
- OWASP – SAML Security Cheat Sheet: https://cheatsheetseries.owasp.org/cheatsheets/SAML_Security_Cheat_Sheet

**Summary:** Local logout only invalidates the current SP's session; the IdP session and other SPs may remain alive. SAML Single Logout attempts to terminate federated SSO sessions using verified LogoutRequests/LogoutResponses. In Spring Security, when **two separate purposes** are needed, use **two different endpoints** for local and RP-initiated SLO, along with full metadata/signing certs and IdP support. Do not equate "clicked the logout button" with "the entire federation and every token have been invalidated".
