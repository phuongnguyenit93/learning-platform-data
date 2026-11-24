# Handling IdPs Without SLO Support, Partial Failures, and Timeouts

> **Module:** Spring Security – federation. **Parent topic:** SAML2 Logout. This lesson guides building a safe logout policy for a Service Provider (SP) application when the Identity Provider (IdP) does not support Single Logout (SLO), only some services perform logout, or the browser does not receive a LogoutResponse within the expected window.

## 1. Learning Objectives

After this lesson, you will be able to:

1. Distinguish **local logout**, **SP/RP-initiated SLO**, and **IdP/AP-initiated SLO**.
2. Determine SLO capability from `SingleLogoutService` in trusted metadata, while verifying bindings and signing credentials.
3. Design a local-only fallback when the IdP only supports SSO, never promising that all sessions at the IdP/other apps disappeared.
4. Understand `Success`, `PartialLogout`, `Requester`, `Responder`, invalid-signature responses, and completely missing responses.
5. Explain why `PartialLogout` can be a **second-level status beneath top-level Success**, yet other SPs may still remain logged in.
6. Design timeouts **without relying on the assumption that the browser will return** after redirecting to the IdP.
7. Separate `POST /logout` and `POST /saml2/logout` in Spring Security, keeping `/logout/saml2/slo` for the SAML filter.
8. Run a standalone Java 17 state machine illustration and build a Spring Boot 3.3 example with local-only and opt-in SLO modes.
9. Ensure signature, issuer, destination, `InResponseTo`, `RelayState`, session scope, and anti-replay are never bypassed during error handling.
10. Plan tests for errors, delays, multi-IdP, and distributed sessions; write messages matching the exact level of confirmation.

**Scope:** This lesson covers **Spring Security Servlet SAML2 Service Provider**. For Spring Security/OpenSAML versions other than 6.3 or specialized IdPs, consult Javadoc/metadata and test in practice. SAML SLO does not automatically mean logging out every device or any application outside the federation.

## 2. One Logout Button, Three Different Outcomes

Suppose a Partner A employee is logged in to Orders Portal (SP A) and Reports Portal (SP B), and also holds an authentication cookie at the IdP.

| Session Layer | Who Owns It? | How Does Local Logout at Orders Affect It? |
| --- | --- | --- |
| HTTP session at Orders Portal | SP A | Can be reliably destroyed when the local request is processed. |
| IdP SSO cookie/session | IdP | SP A cannot directly delete cookies on the IdP domain. |
| HTTP session at Reports Portal | SP B | Not automatically deleted by SP A's local logout. |
| Sessions on other browsers/devices | Respective parties | Front-channel SLO does not automatically guarantee global device revocation. |

**Outcome 1 — Local-only:** Orders Portal deletes its local session. The IdP may still hold a session, so when reopening a protected page at Orders, the user may immediately SSO back in. This reflects the difference between a local session and an IdP session, not necessarily a bug.

**Outcome 2 — IdP reports SLO success:** Orders Portal logged out locally and sent a SAML `LogoutRequest`; the IdP processed it and returned a valid `LogoutResponse`. The SP can report **the IdP confirmed processing**, yet still should not promise that devices outside the SAML federation logged out.

**Outcome 3 — Partial or unknown:** The IdP could not reach Reports Portal and returned `PartialLogout`; or the browser never returned to the SP with `LogoutResponse`. The SP knows for certain only that the local session was destroyed, while external session state **is not fully confirmed**.

Safe policy is storing and displaying the **level of evidence**, rather than collapsing every case into one `isLoggedOut=true` boolean.

## 3. Three Logout Flows and Who Has Authority to End Sessions

### 3.1. Local Logout

~~~text
Browser                   Orders SP                 IdP           Reports SP
  |                          |                      |                |
  |--- POST /logout -------->|                      |                |
  |                          | invalidate session   |                |
  |                          | clear authentication |                |
  |<-- /signed-out ----------|                      |                |
  |                          |    DOES NOT CONTACT IdP / Reports     |
~~~

Local logout is the right default when the IdP **does not provide SLO**. It sends no SAML LogoutRequest and does not wait on IdP networking before destroying the SP session.

The completion page should be `permitAll` and **must not automatically redirect to a protected page**; otherwise a live IdP session could immediately SSO back in, making users think logout failed.

### 3.2. RP/SP-Initiated SLO

~~~text
Browser           Orders SP                  Partner IdP             Reports SP
   |                   |                         |                       |
   |-- POST SLO ------>|                         |                       |
   |                   | local logout            |                       |
   |<-- browser action-|                         |                       |
   |-------------------- LogoutRequest --------->|                       |
   |                   |                         |-- LogoutRequest ----->|
   |                   |                         |<-- LogoutResponse ----|
   |<-------------------- LogoutResponse --------|                       |
   |-- SLO callback -->| verify response         |                       |
   |<-- result --------|                         |                       |
~~~

Spring Security runs local `LogoutHandler` instances first, then `Saml2RelyingPartyInitiatedLogoutSuccessHandler` builds and sends a `LogoutRequest` to the IdP. If the IdP returns a `LogoutResponse`, `Saml2LogoutResponseFilter` processes and verifies it via the validator.

**Key point:** after handing the browser off to the IdP, the SP **loses control of navigation**. The IdP may never send the browser back, or one participant may stall the logout flow.

### 3.3. AP/IdP-Initiated SLO

~~~text
Partner IdP           Browser/transport           Orders SP
    |                         |                        |
    |---- signed LogoutRequest ----------------------->|
    |                         |                 verify request
    |                         |                 logout target session
    |<--------------------------- LogoutResponse ------|
~~~

The IdP proactively sends a `LogoutRequest` to the SP; the SP must verify origin/target and the exact specified session **before cleanup**. Never accept an arbitrary HTTP POST parameter named `SAMLRequest` as authority to delete someone else's session.

Once the SP sends `LogoutResponse` back to the IdP, browser navigation control remains with the IdP/transport. `AP-initiated` also does not automatically guarantee every participant succeeded.

## 4. Conditions for an IdP to Actually Support SLO

An IdP with `SingleSignOnService` and no `SingleLogoutService` can still perform SAML2 login normally.

Metadata XML fragment **supporting SSO only**:

~~~xml
<md:IDPSSODescriptor
    xmlns:md="urn:oasis:names:tc:SAML:2.0:metadata"
    protocolSupportEnumeration="urn:oasis:names:tc:SAML:2.0:protocol">
    <md:SingleSignOnService
        Binding="urn:oasis:names:tc:SAML:2.0:bindings:HTTP-Redirect"
        Location="https://idp.partner.example/sso"/>
</md:IDPSSODescriptor>
~~~

XML fragment with SLO:

~~~xml
<md:IDPSSODescriptor
    xmlns:md="urn:oasis:names:tc:SAML:2.0:metadata"
    protocolSupportEnumeration="urn:oasis:names:tc:SAML:2.0:protocol">
    <md:SingleLogoutService
        Binding="urn:oasis:names:tc:SAML:2.0:bindings:HTTP-Redirect"
        Location="https://idp.partner.example/slo"
        ResponseLocation="https://idp.partner.example/slo/response"/>
</md:IDPSSODescriptor>
~~~

This is **illustrative XML**, not real signed or registered metadata. In real integration, metadata must come from a **trusted source** with contract-compliant issuer and credentials.

### 4.1. Capability Checklist Before Enabling SLO

| Question | If Not Met |
| --- | --- |
| Valid `SingleLogoutService` in IdP metadata? | Use local logout only; do not guess a `/slo` URL. |
| Does IdP permit SP/RP-initiated logout? | Do not enable RP-initiated flow yourself. |
| Can IdP send AP-initiated LogoutRequest per agreed profile? | Do not advertise AP-initiated capability. |
| Compatible POST/Redirect binding and right response endpoint? | Fix IdP and SP configurations. |
| Does SP have a signing key/certificate trusted by IdP? | Cannot emit compliant signed LogoutRequests yet. |
| Does SP have a public SLO URL with right host/scheme/HTTPS and metadata? | Cannot receive callbacks properly yet. |
| Does IdP return LogoutResponse and which Status codes does it support? | Define error/fallback handling and test interoperability. |
| Do other SPs participate in SLO properly? | Cannot promise federated logout everywhere. |
| Are monitoring and PartialLogout/timeout handling in place? | Should not describe SLO as guaranteed completion. |

**Having a metadata element does not prove the system is ready.** You must test signatures, NameID/SessionIndex, callbacks, SessionIndex semantics, and real IdP behavior.

## 5. IdP Without SLO Support: Safe Local-Only

Implementation rules:

1. Destroy the local session and clear `SecurityContext`/Authentication through Spring Security logout handlers.
2. Never send `LogoutRequest` to a guessed URL; never use an SSO URL as an SLO URL.
3. Never promise IdP cookies or other SP sessions were deleted.
4. The logout page must be `permitAll` and must not automatically start a new login flow.
5. On shared machines, instruct users to log out directly at the IdP/linked applications and follow organizational device security measures.
6. Never let the browser pass an arbitrary `redirectUri` to finish logout; prevent open redirects.
7. Repeating an already-handled local logout must never grant privileges or restore a session.
8. If all-device logout is required, coordinate **session revocation** at each system/IdP; front-channel SAML SLO is insufficient on its own to guarantee everything.

**Appropriate UX message:**

> "You have logged out of this application. Your login sessions at the identity provider and other applications may still remain active. On a shared computer, please log out of related services per your organization's guidelines."

Do not display: "Logged out of all applications and devices" if the SP lacks evidence.

### 5.1. Why Can SSO Happen Again After Local Logout?

~~~text
T0: Orders SP holds session A; IdP holds session I.
T1: Local logout at Orders: A is destroyed; I is untouched.
T2: Browser requests GET /orders/private.
T3: SP sees no session A -> initiates SAML AuthnRequest.
T4: IdP sees session I -> may issue SAMLResponse without asking for password.
T5: SP creates new session B.
~~~

This sequence **does not prove local logout failed**. Distinguish it from a real bug such as session A not being destroyed, a local cookie remaining valid against policy, or an authorization cache not being cleared.

### 5.2. Local-Only Differs from Auto-Fallback After SLO Failure

When you know **in advance** that the IdP lacks SLO, choose local logout intentionally. When SLO **has already started** and then hits a timeout, the local session is usually already destroyed; you cannot silently switch the browser to another flow and conclude the IdP processed it. Record `TIMEOUT_UNKNOWN`, never quietly label it `SUCCESS`.

## 6. PartialLogout per OASIS: An Incomplete Outcome

### 6.1. Status Code Hierarchy

SAML2 Core, section 3.7.3.2, distinguishes the logout status of the **session authority** from whether **session participants** confirmed. When the session authority ends its own session while one or more participants fail to confirm, `LogoutResponse` may contain:

~~~xml
<samlp:LogoutResponse
    xmlns:samlp="urn:oasis:names:tc:SAML:2.0:protocol"
    xmlns:saml="urn:oasis:names:tc:SAML:2.0:assertion"
    ID="_logout-resp-2"
    Version="2.0"
    IssueInstant="2030-05-01T10:00:20Z"
    InResponseTo="_logout-req-1"
    Destination="https://orders.example/logout/saml2/slo">

    <saml:Issuer>https://idp.partner.example/saml</saml:Issuer>
    <samlp:Status>
        <samlp:StatusCode
            Value="urn:oasis:names:tc:SAML:2.0:status:Success">
            <samlp:StatusCode
                Value="urn:oasis:names:tc:SAML:2.0:status:PartialLogout"/>
        </samlp:StatusCode>
    </samlp:Status>
</samlp:LogoutResponse>
~~~

**Example intentionally omits a real XML Signature** for structural learning only; never feed it into an SLO endpoint for real login/logout.

- **Top-level Success:** the IdP/session authority reports having handled **its own** session per SAML Core.
- **Second-level PartialLogout:** could not confirm that all session participants ended their sessions.
- The local SP in an RP-initiated flow may already have destroyed its session earlier; `PartialLogout` does not mean the local session survived.
- Never collapse `Success + PartialLogout` into a single "GLOBAL SUCCESS" label.

### 6.2. Comparing Response Outcomes

| SAML LogoutResponse | What Can Be Concluded After Verification? | What Must Not Be Concluded |
| --- | --- | --- |
| Top-level `Success`, no partial | IdP reports logout handled within SAML scope. | Every device and non-federated app logged out. |
| Top-level `Success` + nested `PartialLogout` | IdP reports its own session ended; some SPs were not confirmed. | All SPs logged out successfully. |
| `Requester` | Request rejected/invalid per IdP processing. | IdP definitely logged out. |
| `Responder` | IdP encountered a processing error. | Response can be pretended to have succeeded. |
| Response with invalid signature/issuer/destination | Status content cannot be trusted. | Trusting `Success` because XML contains that string. |
| No response | No confirmation from IdP. | Remote logout definitely succeeded **or** failed. |

Spring Security documentation includes `Saml2LogoutResponseValidator` to process LogoutResponses, yet **do not assume every version automatically maps nested `PartialLogout` to the business UI outcome you want**. Add integration tests/extension points for interpretation while never bypassing built-in validators.

### 6.3. Categories of Partial Failures

- IdP calls SP B while SP B is under maintenance or hits a network error.
- A participant does not support the SAML Logout binding being used.
- Browser is blocked by privacy settings, SameSite/cookies, or chained redirects.
- IdP ended its session without receiving final confirmation from every SP.
- An SP processed logout, yet its response was lost on the return hop.
- A participant ended the session in the current browser while a session on another device remains (beyond what SAML SLO evidences).

**On PartialLogout:** keep local logout in effect, display a scoped notice, log/emit metrics, and guide the user to log out directly from applications that may still be signed in. Never infinitely spam LogoutRequests to force a `Success` status.

## 7. Timeout Is Not Proof That Remote Logout Failed

### 7.1. Browser Front-Channel

~~~text
SP: POST /saml2/logout
    -> invalidate local session
    -> create/sign LogoutRequest
    -> browser goes to IdP SLO endpoint
    -> IdP may contact other SPs
    -> browser closes / network loss / callback never arrives
    -> SP does not get LogoutResponse
~~~

Accurate result: **LOCAL SESSION ENDED** (if cleanup finished) and **IdP/others UNKNOWN**.

An HTTP connection timeout on a `RestTemplate` or database pool cannot force a browser to submit a callback after leaving the SP. Distinguish **network/server timeouts** from the **SLO response-correlation deadline**.

### 7.2. Multiple Timeout Clocks

| Marker | Meaning | Do Not Confuse With |
| --- | --- | --- |
| HTTP server/client timeout | Time limit on a single request or connection. | Deadline for the browser to return from the IdP. |
| Browser navigation/visibility | Browser may close the tab or block redirects. | A confirmed remote logout failure event. |
| SLO attempt deadline | How long the SP waits for confirmation of a LogoutRequest ID. | Actual IdP session lifetime. |
| `LogoutRequest.NotOnOrAfter` when applicable | Request processing deadline per SAML profile. | Local HTTP session expiry. |
| SP session timeout | Application session lifetime. | LogoutResponse correlation state lifetime. |
| IdP SSO session timeout | Controlled by the IdP. | Local access limits after revocation. |

For example, the SP might choose a **60-second deadline** to transition state from PENDING to `TIMEOUT_UNKNOWN`. This is **only an illustrative policy value**, not a SAML/Spring default. If a valid response arrives late, you can audit the late-response event per policy; never revive the session or overwrite state misleadingly.

### 7.3. When Using SOAP/Back-Channel

If a federation uses SLO over SOAP, outbound HTTP clients genuinely need connect/read timeouts, retry budgets, circuit breakers, and failure policies. That is a different flow from front-channel. Never use backend timeouts as a claim that every browser-routed `LogoutRequest` reached participants.

When the network fails, sessions may remain at the IdP or elsewhere. An uncertain SLO outcome is normal and must be reflected in the outcome state.

## 8. State Decision Flow and Evidence

~~~text
USER_REQUESTED_LOGOUT
          |
          v
LOCAL_SESSION_ENDED
          |
          +-- IdP no SLO ----------> LOCAL_ONLY
          |
          +-- SLO enabled ---------> SLO_REQUESTED
                                      |
                                      +--> verified Success -> IDP_REPORTED_SUCCESS
                                      |
                                      +--> verified Partial -> PARTIAL_LOGOUT
                                      |
                                      +--> verified error   -> PROTOCOL_FAILURE
                                      |
                                      +--> invalid response -> INVALID_RESPONSE
                                      |
                                      +--> no response
                                                |
                                                +-- before deadline -> PENDING
                                                +-- after deadline  -> TIMEOUT_UNKNOWN
~~~

In RP-initiated SLO, **never restore the old local session** just because LogoutResponse failed or timed out. If the user wants to log back in, they must go through a fresh authentication flow.

### 8.1. Correlation Data

A diagnostic record might include:

~~~text
attempt_id              internal random ID
registration_id         verified RP-IdP configuration
idp_entity_id           trusted issuer
logout_request_id       SAML LogoutRequest ID
sent_at                 start timestamp
local_logout_at         local session destruction timestamp
deadline_at             response wait cutoff
outcome                 PENDING | PARTIAL | TIMEOUT_UNKNOWN | ...
response_id             if present
response_validated      boolean
top_status/nested_status only after verification
~~~

Never store raw `SAMLRequest`/`SAMLResponse`, NameID, SessionIndex, cookies, or private keys in default operational logs. If needed for investigation, protect data under dedicated retention/access policies.

Spring Security uses `Saml2LogoutRequestRepository` to maintain data needed to correlate `RelayState` and `InResponseTo` for LogoutResponse. When replacing the default repository or running multi-node, verify correlation survives session invalidation and load balancers; never replace the library with an ad-hoc map lacking concurrency safety.

### 8.2. Checks That Must Never Be Skipped

1. Select the exact `RelyingPartyRegistration`/IdP from the authenticated context; never trust a client-supplied issuer.
2. Verify the XML signature with a trusted certificate over the actually signed element.
3. Check `Issuer`, `Destination`, binding, version/timestamps per profile.
4. For RP-initiated, match `InResponseTo`/`RelayState` against a real, unused LogoutRequest.
5. Prevent replay/duplicate IDs; never let an old response complete a new attempt.
6. AP-initiated requests must target the right user/session/tenant per `NameID`/`SessionIndex` and policy.
7. Read status and conclude success/partial only **after** verification steps.
8. Local session logout success does not depend on whatever remote status arrives later.

Never parse XML manually with XPath outside the provider and treat the first `//StatusCode` as a trusted status; nor disable CSRF globally just because the IdP callback lacks a form CSRF token.

## 9. Java 17: Standalone State Machine

A standalone program demonstrating how to turn **evidence already verified by the SAML provider** into a business outcome. The program **does not** parse SAML XML or verify signatures; it only classifies outcomes.

### 9.1. File LogoutOutcomeDemo.java

~~~java
public class LogoutOutcomeDemo {

    enum Evidence {
        NONE,
        VERIFIED_SUCCESS,
        VERIFIED_PARTIAL,
        VERIFIED_ERROR,
        INVALID_RESPONSE
    }

    enum Outcome {
        LOCAL_ONLY,
        PENDING,
        IDP_REPORTED_SUCCESS,
        PARTIAL_LOGOUT,
        TIMEOUT_UNKNOWN,
        PROTOCOL_FAILURE,
        INVALID_RESPONSE
    }

    static Outcome decide(
            boolean localEnded,
            boolean sloSupported,
            Evidence evidence,
            boolean deadlinePassed) {

        if (!localEnded) {
            throw new IllegalArgumentException(
                "Local session must end before classifying");
        }

        if (!sloSupported) {
            return Outcome.LOCAL_ONLY;
        }

        return switch (evidence) {
            case VERIFIED_SUCCESS -> Outcome.IDP_REPORTED_SUCCESS;
            case VERIFIED_PARTIAL -> Outcome.PARTIAL_LOGOUT;
            case VERIFIED_ERROR -> Outcome.PROTOCOL_FAILURE;
            case INVALID_RESPONSE -> Outcome.INVALID_RESPONSE;
            case NONE -> deadlinePassed
                ? Outcome.TIMEOUT_UNKNOWN
                : Outcome.PENDING;
        };
    }

    public static void main(String[] args) {
        System.out.println("unsupported=" +
            decide(true, false, Evidence.NONE, false));
        System.out.println("pending=" +
            decide(true, true, Evidence.NONE, false));
        System.out.println("success=" +
            decide(true, true, Evidence.VERIFIED_SUCCESS, false));
        System.out.println("partial=" +
            decide(true, true, Evidence.VERIFIED_PARTIAL, false));
        System.out.println("timeout=" +
            decide(true, true, Evidence.NONE, true));
        System.out.println("error=" +
            decide(true, true, Evidence.VERIFIED_ERROR, false));
        System.out.println("invalid=" +
            decide(true, true, Evidence.INVALID_RESPONSE, false));
    }
}
~~~

### 9.2. Command and Stdout

With JDK 17+:

~~~bash
javac --release 17 LogoutOutcomeDemo.java
java LogoutOutcomeDemo
~~~

**Exact stdout:**

~~~text
unsupported=LOCAL_ONLY
pending=PENDING
success=IDP_REPORTED_SUCCESS
partial=PARTIAL_LOGOUT
timeout=TIMEOUT_UNKNOWN
error=PROTOCOL_FAILURE
invalid=INVALID_RESPONSE
~~~

- No SLO -> local logout is confirmed; IdP and other SPs lack evidence.
- PENDING -> request sent, no response yet, deadline not yet passed.
- `IDP_REPORTED_SUCCESS` -> **IdP reported** processing succeeded; does not claim all devices.
- `PARTIAL_LOGOUT` -> not all participants confirmed.
- `TIMEOUT_UNKNOWN` -> no evidence whether the IdP succeeded or failed.
- `INVALID_RESPONSE` -> unverified status is not used.
- The example assumes `localEnded=true`; if local logout fails, handle the local error separately rather than guessing a remote outcome.

**Code scope:** this simulates business classification after validation. Never copy `Evidence.VERIFIED_SUCCESS` from an unverified HTTP request; production grants this evidence only from a trusted SAML validator.

## 10. Spring Security: Distinguishing Two Endpoints and the Callback

Spring Security provides:

| Endpoint / Component | Function |
| --- | --- |
| `POST /logout` | Default local logout; clears session/authentication via `LogoutHandler`. |
| `POST /saml2/logout` | **Custom endpoint name in example** to trigger RP-initiated SLO. |
| `POST /logout/saml2/slo` | Default SAML message endpoint receiving LogoutRequest/LogoutResponse from IdP. |
| `Saml2RelyingPartyInitiatedLogoutSuccessHandler` | Emits LogoutRequest after running local logout. |
| `Saml2LogoutRequestFilter` | Verifies and handles IdP-initiated LogoutRequest. |
| `Saml2LogoutResponseFilter` | Verifies LogoutResponse for the RP-initiated flow. |
| `Saml2LogoutRequestRepository` | Stores correlation state to match responses. |
| `Saml2LogoutRequestValidator`, `Saml2LogoutResponseValidator` | SAML logout message validators per framework/version. |

**Do not confuse** `/login/saml2/sso/{registrationId}` (login ACS), `/logout/saml2/slo` (SP SLO callback), and `/saml2/logout` (user-triggered SLO action in this lesson).

Spring Security documentation illustrates separating the two endpoints:

~~~java
http
    .logout(logout -> logout.logoutUrl("/logout"))
    .saml2Logout(saml -> saml.logoutUrl("/saml2/logout"));
~~~

Thus `POST /logout` performs local logout only; `POST /saml2/logout` sends SLO if the IdP/registration supports it. **Never enable `saml2Logout` merely because the IdP supports login.** Profile and registration must match the contract.

## 11. Illustrative Spring Boot 3.3 / Java 17 Application

### 11.1. Structure

~~~text
saml-safe-logout/
├── settings.gradle
├── build.gradle
└── src/main/
    ├── java/com/example/samllogout/
    │   ├── SamlSafeLogoutApplication.java
    │   ├── SecurityConfig.java
    │   └── PageController.java
    └── resources/
        ├── application.yml
        └── templates/
            ├── home.html
            └── signed-out.html
~~~

`settings.gradle`:

~~~groovy
rootProject.name = 'saml-safe-logout'
~~~

`build.gradle`:

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.13'
    id 'io.spring.dependency-management' version '1.1.6'
}

group = 'com.example'
version = '0.0.1-SNAPSHOT'

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

repositories {
    mavenCentral()
    maven { url 'https://build.shibboleth.net/maven/releases/' }
}

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-thymeleaf'
    implementation 'org.springframework.boot:spring-boot-starter-security'
    implementation 'org.springframework.security:spring-security-saml2-service-provider'
}
~~~

### 11.2. Main Class

`src/main/java/com/example/samllogout/SamlSafeLogoutApplication.java`:

~~~java
package com.example.samllogout;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class SamlSafeLogoutApplication {
    public static void main(String[] args) {
        SpringApplication.run(SamlSafeLogoutApplication.class, args);
    }
}
~~~

### 11.3. application.yml and Opt-In Profile

`src/main/resources/application.yml`:

~~~yaml
spring:
  security:
    saml2:
      relyingparty:
        registration:
          partner-a:
            assertingparty:
              metadata-uri: ${PARTNER_A_IDP_METADATA_URI}

app:
  saml:
    slo-enabled: false

---
spring:
  config:
    activate:
      on-profile: slo
  security:
    saml2:
      relyingparty:
        registration:
          partner-a:
            signing:
              credentials:
                - private-key-location: "file:${SP_SAML_SIGNING_KEY}"
                  certificate-location: "file:${SP_SAML_SIGNING_CERT}"
            singlelogout:
              url: "{baseUrl}/logout/saml2/slo"
              binding: POST

app:
  saml:
    slo-enabled: true
~~~

- Default **local-only** mode requires no SLO service.
- The `slo` profile is used **only after** the IdP publishes a compatible `SingleLogoutService` and both sides finalize bindings, signatures, and SP SLO URL.
- Metadata URI must be a trusted source; SP signing key/certificate must be provisioned via secrets/files on the host, never committed to Git.
- `singlelogout.url` describes the **SP callback SLO URL**, not the IdP endpoint. The IdP SLO endpoint comes from trusted metadata.
- `{baseUrl}` is a Spring URI template, while `${...}` is a Spring placeholder resolved from the environment.
- Having an SLO profile does not prove it works properly; test callbacks and valid responses.

### 11.4. SecurityConfig.java

`src/main/java/com/example/samllogout/SecurityConfig.java`:

~~~java
package com.example.samllogout;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class SecurityConfig {

    @Bean
    SecurityFilterChain securityFilterChain(
            HttpSecurity http,
            @Value("${app.saml.slo-enabled:false}") boolean sloEnabled)
            throws Exception {

        http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/", "/signed-out", "/error").permitAll()
                .anyRequest().authenticated()
            )
            .saml2Login(Customizer.withDefaults())
            .logout(logout -> logout
                .logoutUrl("/logout")
                .logoutSuccessUrl("/signed-out")
                .invalidateHttpSession(true)
                .clearAuthentication(true)
            );

        if (sloEnabled) {
            http.saml2Logout(saml -> saml.logoutUrl("/saml2/logout"));
        }

        return http.build();
    }
}
~~~

**Exact scope:** when `sloEnabled=false`, the code does not enable SLO while keeping local logout. When `true`, Spring SAML filters support SLO requests alongside the registration configuration.

Never disable CSRF globally; never create an MVC Controller for `/logout/saml2/slo` because SAML filters must process real callbacks. If the IdP uses another binding or endpoint, configure both SP and IdP synchronously per documentation for your exact version.

### 11.5. PageController.java

`src/main/java/com/example/samllogout/PageController.java`:

~~~java
package com.example.samllogout;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Controller;
import org.springframework.ui.Model;
import org.springframework.web.bind.annotation.GetMapping;

@Controller
public class PageController {

    private final boolean sloEnabled;

    public PageController(
            @Value("${app.saml.slo-enabled:false}") boolean sloEnabled) {
        this.sloEnabled = sloEnabled;
    }

    @GetMapping("/")
    public String home(Model model) {
        model.addAttribute("sloEnabled", sloEnabled);
        return "home";
    }

    @GetMapping("/signed-out")
    public String signedOut() {
        return "signed-out";
    }
}
~~~

`sloEnabled` is only an **administrative configuration flag** for one IdP; it is not a runtime check that all participants log out. For multi-IdP, a single global flag is insufficient.

### 11.6. home.html

`src/main/resources/templates/home.html`:

~~~html
<!DOCTYPE html>
<html lang="en" xmlns:th="http://www.thymeleaf.org">
<head>
    <meta charset="UTF-8"/>
    <title>Logout</title>
</head>
<body>
<h1>Manage login session</h1>
<p>
    Exiting this application does not necessarily end your session at the IdP
    or linked applications.
</p>

<form th:action="@{/logout}" method="post">
    <input type="hidden"
           th:name="${_csrf.parameterName}"
           th:value="${_csrf.token}"/>
    <button type="submit">Log out of application</button>
</form>

<div th:if="${sloEnabled}">
    <p>
        The IdP has been configured by administrators to support SAML SLO.
        Some applications may still not confirm logout.
    </p>
    <form th:action="@{/saml2/logout}" method="post">
        <input type="hidden"
               th:name="${_csrf.parameterName}"
               th:value="${_csrf.token}"/>
        <button type="submit">Request federated logout</button>
    </form>
</div>
</body>
</html>
~~~

The form uses `POST` and the CSRF token provided by Spring/Thymeleaf. Never switch to side-effecting `GET` logout. Never accept `sloEnabled` from the browser to decide features or IdP endpoints.

### 11.7. signed-out.html

`src/main/resources/templates/signed-out.html`:

~~~html
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8"/>
    <title>Logged out</title>
</head>
<body>
<h1>Logged out of application</h1>
<p>
    Your session in this application has ended. Sessions at the IdP and
    other applications may still remain active.
</p>
<p>
    If using a shared computer, log out of related services
    according to your organization's guidelines.
</p>
</body>
</html>
~~~

This page confirms **local logout** and does not replace a verified SLO status. When RP-initiated SLO has redirected the browser to the IdP, the final page may not be controlled by the SP.

### 11.8. Running and Practical Limits

With Java 17 and an appropriate Gradle wrapper:

~~~bash
./gradlew bootRun
~~~

Opt-in SLO mode, only after the IdP supports it and supplies suitable keys/certs:

~~~bash
./gradlew bootRun --args='--spring.profiles.active=slo'
~~~

On Windows PowerShell you can use `.\gradlew.bat`. `PARTNER_A_IDP_METADATA_URI`, `SP_SAML_SIGNING_KEY`, and `SP_SAML_SIGNING_CERT` must be **real** values. Without a registered IdP or metadata, the app cannot demonstrate successful login/SLO and may fail to start due to missing configuration.

Observed behavior: default mode renders only the local form; the `slo` profile adds the SLO-initiating form. Local logout redirects to the `permitAll` signed-out page. SLO logout may send the browser to the IdP and **has no fixed final page**.

**Sample limitations:** the code above does not include an outcome store, timeout monitor, or translation of `PartialLogout` into a UX page. This lesson provides the state machine in sections 8–9 to design those additional layers for production; do not assume adding `.saml2Logout(...)` automatically handles partial/timeout UX.

## 12. Multi-IdP: Choose Capability per Registration, Not One Global Button

An SP may trust:

~~~text
registration_id  metadata_has_slo  flow_tested  policy_enabled
partner-a        true              true         true
partner-b        false             false        false
partner-c        true              false        false
~~~

Partner A is allowed to display the SLO option; B and C stay local-only until contracts and test results exist. **Never borrow A's SLO endpoint or signing certificate to send logout for B.**

- Obtain the registration from the verified `Authentication`/`Saml2AuthenticatedPrincipal`, not an untrusted request parameter.
- IdPs A and B may emit identical NameID/SessionIndex strings from two different sources; never delete the wrong tenant's session.
- `SingleLogoutService` details must come from the exact IdP's trusted metadata.
- If an IdP supports only one direction (RP-initiated or AP-initiated), document capability explicitly per direction.
- When callbacks land on another node, ensure correlation repository or shared session storage works properly.
- Do not expect IdP-initiated requests to hit the right session if the app searches only by raw NameID without checking SessionIndex/issuer.

`saml2Logout()` enables capability on the filter chain, yet `RelyingPartyRegistration` still needs SLO support. A global toggle like section 11's example **does not replace** per-partner feature policy in a multi-tenant application.

## 13. Handling Error Logout Responses Without Relaxing Security

### 13.1. Verified Success, Partial, Error, and Invalid Differ

Apply outcomes only after verification:
- **Verified Success:** IdP reported success within SAML scope.
- **Verified Partial:** top-level Success with nested PartialLogout.
- **Verified Error:** top-level Requester/Responder or other valid error code.
- **Invalid Response:** signature, Issuer, Destination, InResponseTo, or trust failed.
- **No Response:** undetermined; upon deadline becomes `TIMEOUT_UNKNOWN`.

If Spring's default validator does not expose nested status the way your UI needs, use an extension point supported by your version while still **delegating to the default validator** so checks are never dropped. Never use raw untrusted XML in a controller to mark `SUCCESS`.

### 13.2. Avoid Blind Retries

A LogoutRequest carries an ID and correlation data. Resending an old request ID or firing dozens of new requests when the browser fails to return can cause replay errors, mixed responses, and corrupt audits. If retries are needed, design them as **controlled new attempts** with fresh request IDs/correlation per profile, bounded retry count, respecting session state, and noting the IdP may already have executed logout earlier.

Do not loop `LogoutRequest` until seeing `Success` just to mask another participant lacking SLO support.

### 13.3. Never Restore the Old Local Session

An SLO error after successful local logout cannot be fixed by restoring the old `SecurityContext`/`JSESSIONID`. If the user needs to continue, a new session must pass fresh authentication/authorization. Even if a very late response arrives with `Status=Success`, never re-grant privileges.

## 14. Evidence-Based UX and Messaging

| Outcome | Suggested Message |
| --- | --- |
| `LOCAL_ONLY` | "Logged out of this application. Your sessions at the IdP and other applications may still remain active." |
| `PENDING` | "Ended session in this application. Waiting for federated logout confirmation." |
| `IDP_REPORTED_SUCCESS` | "IdP reported SLO processed successfully within the federation scope." |
| `PARTIAL_LOGOUT` | "Logged out of this application, but the IdP could not confirm all linked services logged out." |
| `TIMEOUT_UNKNOWN` | "Logged out of this application. No confirmation received from the IdP." |
| `PROTOCOL_FAILURE` | "Logged out of this application. Federated logout request encountered an error." |
| `INVALID_RESPONSE` | "Logged out of this application. The SLO response could not be verified." |

Avoid wording like "exited the entire system" after a response lacking `PartialLogout` when lacking evidence about applications/devices outside the federation.

The post-logout page must be `permitAll` and make no automatic calls to protected APIs to avoid auto-SSO loops. If the browser stalls during IdP fan-out, guide users to check other services and log out manually per shared-machine policy.

## 15. Monitoring and Operational Actions

### 15.1. Recommended Metrics (Not Default Metrics)

~~~text
saml_slo_attempt_total{registration_id,mode}
saml_slo_response_total{registration_id,outcome}
saml_slo_partial_total{registration_id}
saml_slo_timeout_total{registration_id}
saml_slo_invalid_response_total{registration_id,reason_class}
saml_slo_local_only_total{registration_id}
saml_slo_pending_age_seconds{registration_id}
~~~

Labels must not contain NameID, email, raw SessionIndex, or request payloads due to PII and high-cardinality risks. Record approved `attemptId`/`registrationId`, local logout timestamp, request ID, deadline, validation outcome, and error reason at appropriate detail.

### 15.2. Symptoms and Diagnostic Directions

| Symptom | Likely Fault | Action |
| --- | --- | --- |
| IdP lacks SingleLogoutService | SLO unsupported or wrong metadata. | Local-only; renegotiate contract. |
| SLO timeouts spike | IdP outage, blocked callback, session state lost on another node. | Inspect browser/network/IdP and correlation repository. |
| PartialLogout increases | Some peer SPs slow/unresponsive. | Coordinate with IdP and SPs; never rewrite status to success. |
| LogoutResponse invalid signature | Wrong cert/trust, rotation, forgery. | Inspect signing certs, issuer, and registration. |
| Requester error | Invalid LogoutRequest or missing profile data. | Inspect NameID, SessionIndex, binding, signature. |
| Logout followed by immediate SSO | Live IdP session or wrong page redirect. | Verify local vs. IdP difference and permitAll signed-out page. |
| Callback arrives but InResponseTo not found | Request repository on wrong node or expiry/replay. | Shared store and regression tests; never drop correlation. |

## 16. SLO Test Suite

| ID | Scenario | Expectation |
| --- | --- | --- |
| S01 | IdP does not publish SingleLogoutService. | Do not enable SLO; local logout only. |
| S02 | Metadata has SLO but partner not yet tested. | Do not advertise global logout yet. |
| S03 | Local POST logout with valid CSRF. | Local session destroyed; signed-out permitAll. |
| S04 | After local logout, IdP cookie remains. | Re-SSO possible; UX does not claim IdP logged out. |
| S05 | RP-initiated sends valid LogoutRequest, IdP returns Success. | Local session ended + verified IdP report. |
| S06 | IdP returns Success with nested PartialLogout. | Outcome PARTIAL; never turn into global success. |
| S07 | IdP returns Requester or Responder. | Local logout stands; outcome `PROTOCOL_FAILURE`. |
| S08 | LogoutResponse bad signature/issuer. | Reject status; outcome `INVALID_RESPONSE`. |
| S09 | Wrong InResponseTo/RelayState. | Reject; do not cross-match attempts. |
| S10 | Browser closes tab, never returns. | After deadline becomes `TIMEOUT_UNKNOWN`. |
| S11 | Valid response arrives after deadline. | Clear late-response policy; never restore session. |
| S12 | Two concurrent logout requests. | Never mix request IDs, state, or callbacks. |
| S13 | IdP sends valid LogoutRequest. | SP deletes exact session per profile, returns LogoutResponse. |
| S14 | Forged/untrusted IdP-initiated request. | Rejected; no arbitrary session deletion. |
| S15 | Multi-IdP: A supports SLO, B does not. | A uses SLO flow; B stays local-only. |
| S16 | Two IdPs emit same NameID/SessionIndex. | Never mix tenants/sessions/issuers. |
| S17 | SP local logout then SLO error. | Never restore old Authentication. |
| S18 | LogoutResponse returns to another node. | Correlation works or fails closed; no false success. |
| S19 | IdP signing certificate rotates. | Verify via updated trusted metadata; never disable signatures. |
| S20 | SP signing cert not trusted by IdP. | IdP may reject request; local logout remains effective. |
| S21 | Backend network timeout. | Distinguish from browser callback timeout. |
| S22 | User revoked while SLO is in flight. | Never re-grant access due to late response. |
| S23 | SLO endpoint has wrong host/path behind reverse proxy. | Fix metadata/URL; never redirect arbitrarily. |
| S24 | Signed-out page automatically calls protected API. | Test catches and fixes auto-SSO loop. |

Tests S06–S12 and S18 **are not automatically satisfied by section 11's sample code**. You need a state store, status extraction, and correlation policy suited to your framework version before production deployment.

## 17. Runbook for Common Incidents

**A — IdP does not support SLO:** Disable opt-in SLO on the registration and keep local logout. Provide instructions for manually logging out of the IdP/other apps. Never build an SLO endpoint by guessing URLs.

**B — PartialLogout:** Verify the response, classify as PARTIAL, keep the local session destroyed, ask the IdP which participant failed to confirm, and alert on spikes. Never retry infinitely.

**C — No response/timeout:** Wait up to the bounded deadline, mark `TIMEOUT_UNKNOWN`, and investigate browser/network/reverse proxy/IdP/`LogoutRequestRepository`. Never assume the IdP definitely logged out or definitely did not.

**D — Invalid LogoutResponse:** Reject status, record PII-free signature/issuer/correlation error category, and fix trust/config. Never drop SAML validators.

**E — Immediate re-SSO:** Verify the local session was truly destroyed; if so, confirm the IdP session remains valid and the signed-out page does not redirect to a protected path. Never treat every fast SSO as a logout bug.

## 18. Self-Assessment Questions

**1. IdP has SSO but no SLO—which approach should be used?**  
Safe local logout, clearly stating that IdP/other applications may still remain logged in.

**2. Do `Success + PartialLogout` contradict each other?**  
No. Top-level status belongs to the session authority; second-level indicates some participants did not confirm.

**3. Does receiving no LogoutResponse after 60 seconds mean IdP logout failed?**  
No, it only means unconfirmed; `TIMEOUT_UNKNOWN` is the accurate label.

**4. If the SP already destroyed the local session, can an error response recreate the old session?**  
No. Logging back in requires fresh authentication.

**5. Why must browser-submitted Status XML never be trusted before verification?**  
Because unverified Status can be forged; signature/issuer/correlation checks are mandatory.

**6. An IdP-initiated LogoutRequest lacks a CSRF token—should CSRF be disabled globally?**  
No. Use profile-compliant SAML filters and validators; keep CSRF for local actions.

**7. What is `LogoutRequestRepository` used for?**  
Retaining data to correlate LogoutResponse via ID/RelayState and prevent mix-ups/replay.

**8. Can a matching SessionIndex be used to log out a session at another IdP?**  
No. Sessions must be scoped within the exact issuer/registration trust boundary.

**9. After SLO Success, can we claim all devices are logged out?**  
No; only state that the IdP reported an outcome within SAML scope.

**10. Why must the local post-logout page be `permitAll`?**  
To avoid auto-triggering SAML login again while the IdP still holds an SSO cookie.

## 19. Implementation Checklist

- [ ] Local logout works independently of IdP availability.
- [ ] Capability check comes from trusted metadata per registration.
- [ ] Never enable `saml2Logout` for an IdP without valid SLO.
- [ ] SP signing key/cert and SLO callback are registered at the IdP.
- [ ] `POST /logout` and `POST /saml2/logout` are clearly separated.
- [ ] Callback `/logout/saml2/slo` is handled by framework filters, with no custom parsing controller.
- [ ] Signature, Issuer, Destination, InResponseTo, RelayState, session scope, and replay are verified.
- [ ] `PENDING`/`PARTIAL`/`TIMEOUT_UNKNOWN` are never promoted to `SUCCESS` without evidence.
- [ ] Local sessions are never restored on remote SLO errors.
- [ ] CSRF remains active for local forms; SAML callbacks use dedicated filters.
- [ ] Browser callback deadlines and backend connection timeouts are distinguished.
- [ ] Multi-node has proper correlation state, and cross-node callbacks are tested.
- [ ] Multi-IdP/tenants never share or mix certificates, endpoints, or SessionIndexes.
- [ ] Signed-out page is `permitAll` and never auto-calls protected APIs.
- [ ] Metrics/alerts/runbooks exist without exposing NameID, raw responses, or private keys.
- [ ] Tested at least S01–S24 per system scope.
- [ ] Consulted docs for the exact Spring Security/OpenSAML version in use.

## Takeaways

> **Local logout is what the SP can confirm; IdP SLO is a protocol request requiring evidence.** IdP lacks SLO → local-only. IdP returns `PartialLogout` → not all SPs confirmed. No LogoutResponse due to timeout → **unknown**, not success. Keep SAML constraints intact, never restore destroyed sessions, and never promise more than what is verified.

### Official References

- [Spring Security – Performing Single Logout](https://docs.spring.io/spring-security/reference/servlet/saml2/logout.html): RP/AP-initiated SLO, local vs. SLO endpoints, LogoutRequestRepository, filters/validators, and callbacks.
- [Spring Security – Handling Logouts](https://docs.spring.io/spring-security/reference/servlet/authentication/logout.html): LogoutFilter, session invalidation, CSRF, and logout success.
- [Spring Security – SAML 2.0 Login Overview](https://docs.spring.io/spring-security/reference/servlet/saml2/login/overview.html): RelyingPartyRegistration and endpoints.
- [OASIS – SAML V2.0 Core](https://docs.oasis-open.org/security/saml/v2.0/saml-core-2.0-os.pdf), section 3.7.3.2: PartialLogout as a second-level status when session participants do not confirm.
- [OASIS – SAML V2.0 Profiles](https://docs.oasis-open.org/security/saml/v2.0/saml-profiles-2.0-os.pdf): Single Logout Profile, bindings, and session handling.
- [OASIS – SAML V2.0 Technical Overview](https://docs.oasis-open.org/security/saml/Post2.0/sstc-saml-tech-overview-2.0.html), section 5.3: federated logout across multiple SPs.
- [OASIS – Metadata for SAML V2.0](https://docs.oasis-open.org/security/saml/v2.0/saml-metadata-2.0-os.pdf): SingleLogoutService, Binding, Location, and ResponseLocation.
- [Spring Boot 3.3 – Security and SAML2](https://docs.spring.io/spring-boot/3.3/reference/web/spring-security.html): Relying-party registration, credentials, and singlelogout properties.
