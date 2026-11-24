# Service Provider-Initiated and Identity Provider-Initiated SAML 2.0 Logout

## 1. Why Is Logout in Federation Different from Ordinary Application Logout?

With SAML 2.0, a user can simultaneously have an **application session at the Service Provider (SP)** and a **centralized login session at the Identity Provider (IdP)**. If they only delete cookies/sessions of one application, the IdP session may remain. When accessing the application again, the browser may immediately perform SSO without prompting for credentials again. Conversely, an IdP wanting to end system-wide login must send signals to the participating SPs. The protocol mechanism for this is called **SAML 2.0 Single Logout (SLO)**.

Two SLO initiation directions:

- **Service Provider-initiated (SP-initiated, RP-initiated):** the user requests logout at the Spring Security application. The SP clears the local session, emits a `<samlp:LogoutRequest>` to the IdP, and may receive a confirming `<samlp:LogoutResponse>`.
- **Identity Provider-initiated (IdP-initiated, AP-initiated):** the IdP initiates a logout request, sending a `<samlp:LogoutRequest>` to the SP. The SP verifies the request, terminates the matching application session, and sends a `<samlp:LogoutResponse>` back to the IdP.

In Spring Security, documentation often uses **RP** (*Relying Party*) for SP, and **AP** (*Asserting Party*) for IdP. This article uses SP/IdP, though you should recognize both terms when reading the API.

### Learning Objectives

After this lesson, you will be able to:

1. Distinguish **local logout**, **SP-initiated SLO**, **IdP-initiated SLO**, and the idea of "logging out of all applications".
2. Read `LogoutRequest`, `LogoutResponse`, `Issuer`, `NameID`, `SessionIndex`, `InResponseTo`, `Status`, and `RelayState` accurately.
3. Diagram and explain the HTTP/browser flows for both directions, identifying the **initiator**, the **signature verifier**, and **when the SP session is destroyed**.
4. Enable Spring Security SAML SLO using `.saml2Logout(... )` along with `RelyingPartyRegistration`, IdP metadata, and signing credentials.
5. Distinguish the entry point `POST /logout` from the callback `POST /logout/saml2/slo` (the default configuration in Spring documentation).
6. Design choices for **application-only logout** and **federation logout** using separate endpoints.
7. Understand guarantee limits: a successful SLO Response does not by itself confirm that every system, device, and session has been destroyed.
8. Investigate common SLO issues: IdP missing `SingleLogoutService`, wrong certificates, missing NameID/SessionIndex, SameSite cookies, expired requests, and unreturned responses.
9. Stay safe against forged logout, session fixation, replay, XML signature wrapping, open redirects, and PII in logs.
10. Test reproducibly using a simple Java 17 scenario, HTTP tests, and IdP/SP logs.

**Technical context:** Spring Boot 3.x, Spring Security 6.x or 7.x **Servlet/MVC**, Java 17 or later, and the `spring-security-saml2-service-provider` module. Always cross-check the documentation for your exact running version. The domains `app.example.org` and `idp.example.org` in this lesson are illustrative only.

## 2. Three Login Session Layers to Distinguish

| Layer | Where State Is Held | Example | Who Has Direct Authority to Destroy It? |
| --- | --- | --- | --- |
| **SP local session** | Application HttpSession/SecurityContext/cookie | `JSESSIONID` for `app.example.org` | The SP application managing that session |
| **IdP SSO session** | Identity provider cookie/session | SSO session at `idp.example.org` | The IdP per its own policy |
| **Other SPs** | Separate sessions/cookies of other apps | HR, CRM, portal, reporting | Each respective SP |

### Local Logout

Local logout typically performs actions such as:
- Invalidating the HTTP session or clearing SecurityContext per Spring Security configuration.
- Deleting related cookies/remember-me tokens if the application's logout handler is configured to handle them.
- Redirecting the browser to the logout success page.

Local logout **does not by default send a SAML LogoutRequest to the IdP**. The user can return to the application and immediately SSO again if the IdP session remains.

### Federation Logout (SLO)

SLO is **a protocol conversation** between the SP and the IdP. With SLO, parties exchange signed/verified messages and can coordinate logging out participating SPs sequentially. However:
- It must be **supported and configured by both IdP and SP**.
- The scope of ending other sessions depends on IdP topology, SAML session state, product policy, and each SP's outcome.
- It can partially fail or lack a callback.
- It does not mean terminating **every browser session, device, OAuth token, JWT, or any application not participating in SAML SLO**.

Therefore two different messages are appropriate: **"Logged out of this application"** and **"Federated logout process completed per verified result"**. Do not display "logged out of all devices" when you only have evidence of SP local logout.

## 3. What Are SAML LogoutRequest and LogoutResponse?

SAML 2.0 defines dedicated protocol messages for logout, independent of `AuthnRequest` and login `Response`.

### 3.1 LogoutRequest

A `LogoutRequest` is used to request terminating sessions associated with a principal. Notable elements:

| Field/Element | Purpose |
| --- | --- |
| `LogoutRequest@ID` | Identifies the request to correlate callbacks and prevent replay |
| `LogoutRequest@IssueInstant` | Issuance timestamp |
| `LogoutRequest@Destination` | Expected SLO endpoint of the recipient |
| `LogoutRequest@NotOnOrAfter` | Validity limit if provided by the sender |
| `<Issuer>` | Entity ID of the initiating party |
| `<NameID>`, `<BaseID>`, or `<EncryptedID>` | Principal identifier per SAML, not necessarily an email |
| `<SessionIndex>` (optional, may be multiple) | Binds the SAML session to log out per contract/protocol |
| `<ds:Signature>` or binding signature | Enables the recipient to verify source/integrity when applicable |

Example of an SP issuing a request (XML illustrating structure, **unsigned**, not a message for production use):

~~~xml
<samlp:LogoutRequest
    xmlns:samlp="urn:oasis:names:tc:SAML:2.0:protocol"
    xmlns:saml="urn:oasis:names:tc:SAML:2.0:assertion"
    ID="_sp-logout-001"
    Version="2.0"
    IssueInstant="2026-11-07T03:00:00Z"
    Destination="https://idp.example.org/saml/slo">
  <saml:Issuer>https://app.example.org/saml/sp</saml:Issuer>
  <saml:NameID Format="urn:oasis:names:tc:SAML:2.0:nameid-format:persistent">
    opaque-principal-123
  </saml:NameID>
  <samlp:SessionIndex>_session-idp-456</samlp:SessionIndex>
</samlp:LogoutRequest>
~~~

From the example, the **LogoutRequest** ID and SessionIndex are two distinct values. Nor does NameID have to be a Spring username or email address; an IdP may use an opaque, transient, or persistent identifier along with appropriate qualifiers.

### 3.2 LogoutResponse

`LogoutResponse` is the reply to a LogoutRequest, typically containing:

- `LogoutResponse@ID`: ID of the response.
- `LogoutResponse@InResponseTo`: ID of the request being answered.
- `Issuer`: party issuing the response.
- `Status/StatusCode`: SAML outcome, e.g., `Success` or an error/partial logout code.
- Signature and source/destination binding checks per trust policy.

Example of an IdP replying to an SP-initiated LogoutRequest:

~~~xml
<samlp:LogoutResponse
    xmlns:samlp="urn:oasis:names:tc:SAML:2.0:protocol"
    xmlns:saml="urn:oasis:names:tc:SAML:2.0:assertion"
    ID="_idp-logout-response-002"
    Version="2.0"
    IssueInstant="2026-11-07T03:00:02Z"
    InResponseTo="_sp-logout-001"
    Destination="https://app.example.org/logout/saml2/slo">
  <saml:Issuer>https://idp.example.org/issuer</saml:Issuer>
  <samlp:Status>
    <samlp:StatusCode
        Value="urn:oasis:names:tc:SAML:2.0:status:Success"/>
  </samlp:Status>
</samlp:LogoutResponse>
~~~

This is also only an **unsigned** illustration and cannot be treated as a trustworthy response. In real integration, the recipient must verify the signature per binding/profile, issuer, destination, InResponseTo, timestamps, and status—never concluding a transaction merely because the XML contains the word "Success".

### 3.3 RelayState in SLO

When a binding/flow uses `RelayState`, it is a parameter **outside the XML**, sent alongside `SAMLRequest` or `SAMLResponse` in the query/form. For HTTP Redirect/POST, SAML constrains it to a short value (80 bytes per the standard) and echoes the received RelayState back unchanged. The SP can use it to resume/correlate the logout transaction. **Never put private keys, session tokens, usernames, sensitive data, or external redirect URLs into RelayState.**

In Spring Security, an issued `LogoutRequest` can be stored in the session/repository to correlate `RelayState` and `InResponseTo` of the LogoutResponse. If state is lost, callback verification may fail even if the IdP already performed logout.

## 4. SP-Initiated SLO: Who Initiates and Who Ends?

This is the scenario where a user is in the Spring application and clicks the **"Log out"** button intending to end federated login.

~~~mermaid
sequenceDiagram
    participant B as Browser
    participant SP as Spring Security SP
    participant I as IdP
    B->>SP: POST /logout (+ CSRF)
    SP->>SP: LogoutHandlers clear SecurityContext / HttpSession
    SP->>SP: Create and sign LogoutRequest (ID, Issuer, NameID)
    SP-->>B: Page/form/redirect forwarding SAMLRequest to IdP
    B->>I: LogoutRequest to SingleLogoutService
    I->>I: Verify request, handle IdP session / coordinate other SPs
    alt IdP sends callback
        I-->>B: Form/redirect carrying LogoutResponse
        B->>SP: POST /logout/saml2/slo with SAMLResponse
        SP->>SP: Verify response + InResponseTo + RelayState + Status
        SP-->>B: Redirect to logout success page
    else IdP does not return callback
        I-->>B: IdP's own completion page/flow
        Note over SP,B: SP local session already destroyed
    end
~~~

In Spring Security per modern documentation, this sequence typically starts with **`POST /logout`** when the principal is a `Saml2AuthenticatedPrincipal` and SLO is enabled on the registration. Spring will:

1. Run `LogoutHandler` instances to destroy authentication state at the SP.
2. Use `Saml2RelyingPartyInitiatedLogoutSuccessHandler` and `Saml2LogoutRequestResolver` to build/sign/serialize the LogoutRequest.
3. Direct the browser to the **IdP's SingleLogoutService** using the configured/negotiated binding.
4. If the IdP returns a LogoutResponse, `Saml2LogoutResponseFilter` and the validator verify the callback.
5. If the callback is valid, proceed to the configured post-logout success page, commonly e.g. `/login?logout`.

**Ordering worth remembering:** the SP **has already ended the local session before receiving** the LogoutResponse. A failed or missing callback **does not mean** the SP should recreate the old session. At the same time, you cannot claim the IdP and all other SPs logged out merely because the SP session was destroyed.

### 4.1 What the SP Knows for Certain vs. What Is Only Expected

| Event | Can the SP Know from Local Evidence? |
| --- | --- |
| LogoutHandler invalidated the SP session | **Yes**, if local logging/testing proves it |
| SP created and sent LogoutRequest | **Yes**, from the request resolver and HTTP trace |
| IdP received the request | Only with HTTP/audit or appropriate acknowledgment |
| IdP destroyed the SSO session | Requires result/audit/policy, cannot be inferred from SP session |
| All other SPs logged out | **No**, not from a single SP's response alone |
| Browser can return to the success page | Depends on callback/IdP control/redirect policy |

When no LogoutResponse arrives from the IdP, describe the federation state as **unconfirmed**; never reverse local logout or allow access to protected resources due to a missing callback.

## 5. IdP-Initiated SLO: The IdP Proactively Requests the SP to End the Session

The second scenario happens when a user logs out at the IdP portal or an IdP policy terminates the SSO session. The IdP may send LogoutRequests to the SPs it has recorded as participating in the federation session.

~~~mermaid
sequenceDiagram
    participant B as Browser
    participant I as IdP
    participant SP as Spring Security SP
    B->>I: Log out from IdP portal or IdP initiates SLO
    I->>I: Identify participating sessions/SPs per policy
    I-->>B: Signed LogoutRequest targeting SP SLO
    B->>SP: POST /logout/saml2/slo with SAMLRequest
    SP->>SP: Verify signature, issuer, Destination, NameID / session
    alt Valid LogoutRequest matching session found
        SP->>SP: LogoutHandlers destroy SP session
        SP->>SP: Create and sign LogoutResponse
        SP-->>B: SAMLResponse sent back to IdP SLO endpoint
        B->>I: POST LogoutResponse
        I->>I: Verify and continue orchestration
    else Invalid request
        SP-->>B: Reject/HTTP 400 or handle error per config
    end
~~~

In Spring Security documentation, this part is handled by **`Saml2LogoutRequestFilter`**. When the IdP sends `SAMLRequest` to the SLO endpoint:

1. The SP locates the trusted registration matching the IdP rather than blindly accepting any browser-supplied issuer.
2. `Saml2LogoutRequestValidator` checks the constraints enforced by the framework/profile.
3. If the request is valid, the SP invokes LogoutHandlers to destroy the local session and clean up state.
4. `Saml2LogoutResponseResolver` builds/signs the `LogoutResponse` back to the IdP.
5. The browser forwards the response to the IdP; **the IdP usually decides the final navigation step**, not the SP.

**Different from SP-initiated logout:** no user clicked the `/logout` button at the SP. The request enters the SP through the endpoint receiving **protocol messages from the IdP**.

### 5.1 Why Must LogoutRequest Be Verified Before Destroying the Session?

Because a LogoutRequest can cause **loss of login session**, a forged request can create a **logout CSRF/denial-of-service** attack:

~~~text
Attacker → POST /logout/saml2/slo
           crafted or tampered SAMLRequest
           requesting logout of another user
~~~

If the SP accepts and deletes sessions based solely on username/NameID, an attacker can force logouts or disrupt other users. You must:
- Verify the **signature** against the IdP verification credentials and binding.
- Verify `Issuer` matches the approved IdP registration.
- Verify `Destination` matches the SP's public SLO endpoint.
- Check validity window and replay protection appropriately.
- Bind `NameID`/`SessionIndex` to the exact authorized session/user within allowed scope.
- Never use raw XML body data to destroy all sessions of an account without a secure, verified design.

**SessionIndex** is a SAML session identifier provided by the IdP in `AuthnStatement` during the login flow; it is not `JSESSIONID`. An IdP/application may have multiple SAML sessions for the same subject. When designing multi-session logout, understand the scope of each `SessionIndex` and IdP policy rather than assuming one NameID suffices to destroy all devices.

## 6. Quick Comparison of Both SLO Directions

| Criterion | SP-Initiated SLO | IdP-Initiated SLO |
| --- | --- | --- |
| Who starts? | User/application at the SP | IdP after logout/policy at the identity portal |
| HTTP trigger in Spring | Usually `POST /logout` with authenticated user | `POST /logout/saml2/slo` carrying `SAMLRequest` |
| Party creating `LogoutRequest` | SP | IdP |
| Party validating request | IdP | SP |
| Party sending `LogoutResponse` | IdP | SP |
| Who validates LogoutResponse? | SP | IdP |
| When SP clears session | Before sending outbound logout request in Spring flow | After receiving request and validating it |
| Final navigation | SP can redirect upon valid response; without callback depends on IdP/browser | IdP controls browser after SP returns response |
| Notable failures | Missing callback, lost logout-request repository, IdP rejects logout | Invalid inbound signature, NameID/session mismatch, cookie missing, wrong SLO URL |
| Automatically guarantees all SPs log out? | No | No |

**The word "initiated" refers to which party sends the first request**, not which party renders the final page or which holds a local session.

## 7. What SAML Metadata Is Needed to Enable Single Logout?

Both parties must agree on the **SLO endpoint** and **binding** in metadata. An IdP may support SSO login very well yet **not publish `SingleLogoutService`**, meaning you cannot assume SLO is supported.

Example excerpt of **IdP metadata**:

~~~xml
<md:IDPSSODescriptor
    xmlns:md="urn:oasis:names:tc:SAML:2.0:metadata"
    protocolSupportEnumeration="urn:oasis:names:tc:SAML:2.0:protocol">
  <md:SingleLogoutService
      Binding="urn:oasis:names:tc:SAML:2.0:bindings:HTTP-POST"
      Location="https://idp.example.org/saml/slo"/>
  <md:SingleSignOnService
      Binding="urn:oasis:names:tc:SAML:2.0:bindings:HTTP-Redirect"
      Location="https://idp.example.org/saml/sso"/>
</md:IDPSSODescriptor>
~~~

Example excerpt of **SP metadata**:

~~~xml
<md:SPSSODescriptor
    xmlns:md="urn:oasis:names:tc:SAML:2.0:metadata"
    protocolSupportEnumeration="urn:oasis:names:tc:SAML:2.0:protocol">
  <md:SingleLogoutService
      Binding="urn:oasis:names:tc:SAML:2.0:bindings:HTTP-POST"
      Location="https://app.example.org/logout/saml2/slo"
      ResponseLocation="https://app.example.org/logout/saml2/slo"/>
  <md:AssertionConsumerService
      Binding="urn:oasis:names:tc:SAML:2.0:bindings:HTTP-POST"
      Location="https://app.example.org/login/saml2/sso/corp"
      index="0" isDefault="true"/>
</md:SPSSODescriptor>
~~~

These are **excerpts explaining structure**, not complete metadata because entity descriptors, certs, and deployment conditions are omitted. In complete metadata:
- `SingleSignOnService`: IdP endpoint receiving AuthnRequest for **login**.
- `AssertionConsumerService`: SP endpoint receiving **login SAMLResponse**.
- `SingleLogoutService`: endpoint handling **LogoutRequest/LogoutResponse**.
- `Location` is the request endpoint; `ResponseLocation` can specify a separate response location if the profile/binding supports it. Never assume the two URLs are always identical.
- `Binding` indicates whether SAML messages travel over HTTP-POST, HTTP-Redirect, or another mutually supported binding.

**Do not confuse ACS `/login/saml2/sso/corp` with SLO `/logout/saml2/slo`.** If a LogoutRequest is sent to the ACS, Spring may fail to find a matching filter or reject the payload because the message type is wrong.

### SLO Can Use Redirect or POST, but Do Not Guess

OASIS defines HTTP-Redirect and HTTP-POST bindings for applicable SAML messages. Spring Security SLO documentation guides configuring the **IdP to sign and POST LogoutRequest/LogoutResponse to `/logout/saml2/slo`** to match the default example interaction. Changing bindings/GET endpoints must align with the Spring Security version, endpoint filters, metadata, and IdP signing conventions. **SAML login supporting Redirect AuthnRequest does not mean SLO Response over Redirect is preconfigured out of the box.**

## 8. Signatures, Certificates, and Two Critical State Types

### 8.1 SP Signing Credential and IdP Verification Credential

To sign LogoutRequest/LogoutResponse, the SP needs a **private signing key and public X.509 certificate**. To verify IdP-signed SAML messages, the SP needs the **IdP's trusted public signing certificate** from approved metadata or configuration.

| Message | Signing Party | Verifying Party | Material Needed by Verifier |
| --- | --- | --- | --- |
| SP → IdP LogoutRequest | SP | IdP | SP public signing certificate |
| IdP → SP LogoutResponse | IdP | SP | IdP public signing certificate |
| IdP → SP LogoutRequest | IdP | SP | IdP public signing certificate |
| SP → IdP LogoutResponse | SP | IdP | SP public signing certificate |

The SLO signing key is not the IdP TLS certificate unless the provider genuinely manages the same key and policy permits it. **Never request the IdP's private key to be placed on the SP.**

### 8.2 Request Repository When SP-Initiated

If the SP sends a LogoutRequest and clears the local session, it still must **remember the request ID/RelayState to match the callback**. Spring Security provides `Saml2LogoutRequestRepository` to hold `LogoutRequest` state. Per documentation, the request is stored in the session by default to verify `RelayState` and `InResponseTo`.

Sensitive points:
- Clearing the local authenticated session and saving the pending callback transaction must be handled consistently by the framework per version/config. Do not manually wipe all intermediate state before the request repository finishes saving.
- When running multiple instances, ensure the logout callback can find the required state (session store/sticky session or an appropriately implemented repository).
- Never rely on RelayState alone as proof of a valid LogoutResponse; you need signature, issuer, destination, InResponseTo, status, and TTL.
- Do not allow an old response to be replayed to complete another transaction.

### 8.3 NameID and SessionIndex Determine Logout Scope

During SAML login, the IdP may issue `AuthnStatement SessionIndex="...">` and `Subject/NameID`. During logout:
- **NameID** is typically the SAML identifier the IdP uses to refer to the subject. It may differ from display name/email.
- **SessionIndex** can specify the relevant IdP/SP session. One principal may have multiple sessions; if multiple SessionIndexes exist, logout scoping must follow the standard and IdP contract.
- A logout request **without SessionIndex** must not arbitrarily be assumed to mean "all accounts/all devices"; understand the semantics and session-handling limits in your deployment.
- When customizing `Saml2AuthenticatedPrincipal` or NameID mapping, ensure the value used when generating LogoutRequest is accepted by the IdP; do not substitute an email from the application database into NameID if the IdP issued a different opaque identifier.

## 9. Spring Boot 3.x Configuration: Enabling SAML Single Logout

Spring Security SLO documentation highlights three key conditions:
1. The IdP supports SAML SLO and its metadata includes `SingleLogoutService`.
2. The IdP is configured to send signed `LogoutRequest` and signed `LogoutResponse` messages to the SP's appropriate SLO endpoint.
3. The SP has an X.509/PKCS#8 signing key to sign messages sent by the SP.

### 9.1 Build Dependencies

In an existing Spring Boot Servlet project, **Gradle Groovy DSL** snippet:

~~~groovy
repositories {
    mavenCentral()
    maven {
        url = uri("https://build.shibboleth.net/maven/releases/")
    }
}

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-security'
    implementation 'org.springframework.security:spring-security-saml2-service-provider'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}
~~~

This is a **snippet** inside a project already configured with the Boot plugin/BOM/version, not a complete build file. Place Shibboleth releases under repository management per policy if internal mirrors require it; do not pin an OpenSAML version conflicting with the Spring Security BOM. For Maven, use the corresponding SAML SP dependency per Spring Boot dependency management.

### 9.2 Boot application.yml

File `src/main/resources/application.yml`:

~~~yaml
spring:
  security:
    saml2:
      relyingparty:
        registration:
          corp:
            signing:
              credentials:
                - private-key-location: "file:/run/secrets/saml/sp-signing.key"
                  certificate-location: "file:/run/secrets/saml/sp-signing.crt"
            singlelogout:
              url: "{baseUrl}/logout/saml2/slo"
            assertingparty:
              metadata-uri: "classpath:saml/corp-idp.xml"
~~~

Explanation:
- `corp` is the local registration ID, not automatically the same as the IdP entity ID.
- `assertingparty.metadata-uri` points to **real, vetted IdP metadata**. The file at `src/main/resources/saml/corp-idp.xml` must publish a valid `SingleLogoutService`.
- `signing.credentials` are the **SP's private key/certificate**, not the IdP's private key.
- `singlelogout.url` publishes the SP's public SLO URL; `{baseUrl}` takes the resolved public base URL via Spring/proxy configuration.
- The key paths use `/run/secrets/saml/...` **inside containers** to avoid packaging private keys into the JAR or source control.
- For IdPs requiring additional SLO response bindings/endpoints or specific signing policies, adjust according to metadata, product capabilities, and Boot/Spring Security version.
- Do not mix a custom `RelyingPartyRegistrationRepository` bean with Boot auto-configuration for the same registration without understanding precedence.

**Configuration in this lesson alone does not create a real federation.** You need a test IdP, public SP entity ID/ACS, trusted metadata, a cookie/session strategy, and matching signing policies.

### 9.3 SecurityFilterChain Enabling Login and Logout

File `src/main/java/com/example/federation/SamlSloSecurityConfig.java`:

~~~java
package com.example.federation;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class SamlSloSecurityConfig {

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http) throws Exception {
        return http
                .authorizeHttpRequests(auth -> auth
                        .requestMatchers("/", "/public/**", "/error", "/login").permitAll()
                        .anyRequest().authenticated())
                .saml2Login(Customizer.withDefaults())
                .saml2Logout(Customizer.withDefaults())
                .build();
    }
}
~~~

This is **configuration code inside a Spring Boot project**, not a standalone Java program runnable with `javac SamlSloSecurityConfig.java` without dependencies. The class is scanned by Spring in the application context. There is no fixed stdout; results depend on real IdP metadata, browser, and certificates.

**Role of `.saml2Logout(Customizer.withDefaults())`:** installs SLO handling capability for the SP. A registration still needs `singleLogoutServiceLocation` or the corresponding property. Simply calling the DSL without the required SLO service/signing keys **does not guarantee SLO works**.

### 9.4 Logout Form from the Browser

With default configuration and CSRF protection enabled, a form in an application page can use the Spring MVC/Thymeleaf template engine:

~~~html
<form th:action="@{/logout}" method="post">
  <button type="submit">Federated logout</button>
</form>
~~~

This snippet must be processed by **Thymeleaf in Spring MVC**, not served as a plain static HTML file. When Spring Security CSRF is integrated properly, the framework/template handles sending the required token. Manually issuing a POST without a CSRF token will receive HTTP 403 **before** the logout filter runs SLO. Do not switch to GET `/logout` to "avoid CSRF" because logout is a state-changing action that needs protection against logout CSRF.

For clients without a template engine, obtain the CSRF token via the mechanism validly exposed by the app and send it in the form/header per policy. Do not disable CSRF application-wide.

## 10. Alternative: Building RelyingPartyRegistration Programmatically in Java

If a project does not use Boot SAML properties, Spring Security allows building the repository programmatically from IdP metadata.

The following **configuration fragment** goes in a project `@Configuration`, where `signingPrivateKey`/`signingCertificate` have already been loaded securely (e.g., via a secret manager/KeyStore, or an appropriate Spring Resource helper):

~~~java
Saml2X509Credential signing =
        Saml2X509Credential.signing(signingPrivateKey, signingCertificate);

RelyingPartyRegistration registration = RelyingPartyRegistrations
        .fromMetadataLocation("classpath:saml/corp-idp.xml")
        .registrationId("corp")
        .singleLogoutServiceLocation("{baseUrl}/logout/saml2/slo")
        .signingX509Credentials(credentials -> credentials.add(signing))
        .build();

RelyingPartyRegistrationRepository repository =
        new InMemoryRelyingPartyRegistrationRepository(registration);
~~~

Required class/import names:
- `org.springframework.security.saml2.core.Saml2X509Credential`.
- `org.springframework.security.saml2.provider.service.registration.RelyingPartyRegistrations`.
- `RelyingPartyRegistration` and `RelyingPartyRegistrationRepository` in the same registration package.
- `InMemoryRelyingPartyRegistrationRepository` for a configuration snapshot.

This is not a complete standalone Java snippet; the key/cert variables must be defined. A full configuration requires valid public entity ID/ACS, IdP metadata, key pair, filter chain, and binding settings matching the IdP. Spring Security 6/7 have differences in OpenSAML implementation; **do not mix classes/versions** arbitrarily.

### Questions to Verify When Initializing from Metadata

- Does the IdP metadata contain `SingleLogoutService`?
- To which `Location` does the IdP send SLO requests?
- Where does the IdP expect to receive LogoutResponse if `ResponseLocation` differs?
- Does the SP metadata imported by the IdP have the exact SLO URL, with the right HTTPS scheme/host/port?
- Does the IdP publish its **public signing certificate**, and does the SP trust that certificate?
- Has the SP signing key/cert been approved by the IdP?
- Does the Spring session have the same NameID/SessionIndex that the IdP used during SSO login?

If IdP metadata is loaded via an HTTPS URL at startup, account for IdP endpoint unavailability: **do not assume every SLO reads metadata fresh over the browser**. Registration/cache lifecycles depend on implementation; if the IdP changes its SLO endpoint or signing cert, a refresh/redeploy may be required.

## 11. Spring Security Endpoint Table: Do Not Confuse Three Roles

| Purpose | HTTP Endpoint per Spring Docs | Payload | Notes |
| --- | --- | --- | --- |
| Initiate logout at SP | `POST /logout` | App-managed form POST/CSRF | SP-initiated SLO when SAML principal and config apply |
| IdP requests SP logout | `POST /logout/saml2/slo` | `SAMLRequest` containing LogoutRequest | AP-initiated; SP verifies then clears local session |
| IdP replies to SP LogoutRequest | `POST /logout/saml2/slo` | `SAMLResponse` containing LogoutResponse | RP-initiated callback; SP verifies request correlation |
| SP initiates SAML login | `GET /saml2/authenticate/corp` | Generates AuthnRequest | **Not logout** |
| SP receives login Response | `POST /login/saml2/sso/corp` | `SAMLResponse` containing login Response | **ACS, not SLO** |

Spring uses the same `/logout/saml2/slo` for both **LogoutRequest and LogoutResponse**, distinguishing messages by form parameter and corresponding filter. By default, the SLO URL **does not necessarily include `{registrationId}`** because the framework uses context/transaction state to identify the registration. An SLO endpoint can be customized in the DSL/registration, provided IdP metadata is updated simultaneously.

### Related Spring Security Classes

| Class/Interface | Role |
| --- | --- |
| `Saml2RelyingPartyInitiatedLogoutSuccessHandler` | After local logout, creates the outbound SLO path from the SP |
| `Saml2LogoutRequestResolver` | Creates, signs/serializes outbound LogoutRequest |
| `Saml2LogoutRequestFilter` | Receives inbound IdP-initiated LogoutRequest |
| `Saml2LogoutRequestValidator` | Validates requests sent by the IdP to the SP |
| `Saml2LogoutResponseResolver` | Creates LogoutResponse when the SP replies to the IdP |
| `Saml2LogoutResponseFilter` | Receives LogoutResponse callback from the IdP |
| `Saml2LogoutResponseValidator` | Validates inbound LogoutResponse |
| `Saml2LogoutRequestRepository` | Stores/correlates SP-issued logout requests |
| `LogoutHandler` | Cleans up SecurityContext, session, and configured local state |

These classes describe **Spring Security Servlet SAML SLO**. Do not apply them verbatim to WebFlux, Spring Security SAML Extension 1.x, or other IdP products. OpenSAML provider classes are named OpenSaml4/OpenSaml5 depending on version; do not import blindly.

## 12. Separating Local Logout and SAML Logout with Two Endpoints

An application sometimes wants to give users two clear choices:

- "Log out of **this application**": destroys the local session, **does not send** an IdP LogoutRequest.
- "Log out of **federated SSO session**": starts SP-initiated SLO.

Spring Security allows configuring two separate URLs per the documentation:

~~~java
package com.example.federation;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class DistinctLogoutConfig {

    @Bean
    SecurityFilterChain filterChain(HttpSecurity http) throws Exception {
        return http
                .authorizeHttpRequests(auth -> auth
                        .requestMatchers("/", "/public/**", "/login", "/error").permitAll()
                        .anyRequest().authenticated())
                .saml2Login(saml -> {})
                .logout(logout -> logout.logoutUrl("/logout"))
                .saml2Logout(saml -> saml.logoutUrl("/saml2/logout"))
                .build();
    }
}
~~~

This is an **alternative option**; **do not** register this `SecurityFilterChain` bean alongside another bean with overlapping matchers arbitrarily. Place it in a Boot project with matching metadata/IdP/signing credentials and SecurityFilterChain.

With this configuration:
- `POST /logout` → local logout.
- `POST /saml2/logout` → initiates SAML 2.0 SLO per registration.
- The inbound SLO endpoint such as `/logout/saml2/slo` still handles protocol messages, not an application logout button.

**UX must be clear:** if a user logs out locally and clicks login again, the IdP session may immediately SSO them back in. That **does not prove local logout failed**. If security policy requires the IdP session to end too, valid SLO or an appropriate IdP mechanism is required.

## 13. Does IdP-Initiated SLO Always Delete All Sessions of a User?

No. You must distinguish **one browser session** handled by Spring from **the system-wide set of sessions**.

Suppose a user has:
- Browser A on laptop, session SP-A1.
- Browser B on laptop, session SP-A2.
- Browser C on phone, session SP-A3.
- Another IdP session on a VM.
- An application that does not support SAML SLO.

A `LogoutRequest` arriving on browser A tells the SP about the session associated with that browser, but **provides no automatic guarantee that the application destroyed A2, A3, or any other sessions**. If business requirements demand "global logout", you need:
1. IdP and each SP supporting session identification/lookup capabilities;
2. a subject + SessionIndex scope contract;
3. a designed/authorized server-side session registry/revocation mechanism;
4. forgery protection, authorization, auditing, retry, and idempotency;
5. verification that sessions were actually destroyed.

**Do not write code that takes a NameID and wipes all sessions sharing an email on an arbitrary request.** That is a major DoS attack surface without strict validation/trust. Front-channel SAML SLO in one browser cannot replace full session governance across all devices and technologies.

## 14. SessionIndex: A Practical Example of Identity Confusion

During SAML login, the IdP may return:

~~~xml
<saml:AuthnStatement
    xmlns:saml="urn:oasis:names:tc:SAML:2.0:assertion"
    AuthnInstant="2026-11-07T02:30:00Z"
    SessionIndex="_idp-session-001">
</saml:AuthnStatement>
~~~

Later, when the IdP wants to end this session, it may issue a LogoutRequest containing:

~~~xml
<samlp:SessionIndex
    xmlns:samlp="urn:oasis:names:tc:SAML:2.0:protocol"
    >_idp-session-001</samlp:SessionIndex>
~~~

**Things that are different:**
- SAML `SessionIndex` is not the servlet container's HTTP session ID.
- `AuthnRequest@ID` is not the SAML SessionIndex.
- `LogoutRequest@ID` only identifies the logout transaction.
- `LogoutResponse@InResponseTo` points to the **LogoutRequest ID**, not SessionIndex.
- `NameID` may be an opaque principal provided by the IdP; never alter its format/qualifier and expect the IdP to accept it.

**An application might not receive SessionIndex or store enough information** if the IdP/registration/framework profile does not provide it. In that case, do not fabricate session values to make SLO look complete; verify actual integration capabilities.

## 15. What Happens If the IdP Does Not Return a LogoutResponse?

Per Spring documentation, in an SP-initiated flow, the IdP may **not** redirect/form-submit a callback back to the SP. Reasons include:
- The IdP displays its own completion page.
- The IdP reports partial logout or an error in its own UI.
- The browser is closed before returning.
- Cookies, SameSite, CSP, WAF, proxies, or network block it.
- The IdP and SP disagree on response destination/binding.
- The IdP has not configured Reply/ResponseLocation accurately.

In that case:
- The SP local session may already have been invalidated.
- Spring does not receive a callback to check Status/response correlation.
- There is no proof of logout at the IdP/all other SPs.
- The user may remain on the IdP page; the app cannot control browser UX.
- The system needs metrics/logs for the condition "SP local logout done; federation outcome unknown".

**Do not restore an authenticated SecurityContext** merely because the IdP did not respond. Never mark "global logout success" without evidence.

If the IdP returns a response whose signature, issuer, Destination, InResponseTo, or Status is invalid, the SP must handle failure/HTTP 400 per framework/profile. **Do not skip validation** just to reach a success page.

## 16. PartialLogout and Inconsistent Outcomes

SAML Core has a `PartialLogout` status code describing a logout that succeeded only partially. It is typically represented as an appropriate subcode (for example when top-level reflects an error/responder), depending on how the IdP implements it. An IdP may encounter another SP that fails to respond or cannot terminate sessions on some components.

Therefore, distinguish carefully:

| Observation | What Can Be Concluded |
| --- | --- |
| SP invalidated the user's HttpSession | Local SP logout was executed |
| IdP returned a `Success` LogoutResponse verified by SP | The IdP **reported** processing the request successfully in the protocol, within policy scope |
| IdP reported `PartialLogout` | Part of the federation did not finish logging out; check IdP logs/session coverage |
| No callback received | Federated logout outcome cannot be confirmed |
| HTTP 200 when loading an IdP page | Only an HTTP result; not a SAML StatusCode |
| User can still SSO into SP after local logout | The IdP session may remain; check federation session |
| User can still access other tokens/APIs after SLO | SAML SLO does not automatically revoke OAuth/JWT/API tokens |

**Avoid assuming** "Success = all devices and applications are logged out". SAML Status is information reported by a responder in one conversation; system-wide assurance depends on which sessions the IdP knows about and can destroy, along with actual mechanisms.

## 17. Testing Logout Redirects in the Browser

### Test 1 — Successful SP-Initiated

1. Log in to the SP using a test IdP and ensure the application session is active.
2. In DevTools enable **Network → Preserve log**; use only authorized test data.
3. Submit the POST logout form with a valid CSRF token.
4. Verify Spring invalidated the SP session and protected routes are no longer accessible with the old session.
5. Observe the browser redirecting to the IdP SingleLogoutService with `SAMLRequest` containing a LogoutRequest, not an AuthnRequest.
6. Verify the IdP processes the signed LogoutRequest per issuer/key/policy.
7. If the IdP returns a `SAMLResponse` LogoutResponse to the SP, inspect `InResponseTo` and status with safe test tools.
8. Observe Spring verifying the callback and redirecting to the logout success page.
9. Try reopening a protected route; if the IdP still has a session, SSO may occur again—distinguish whether that is an IdP SLO failure or local-only logout.

**Expected:** evidence of local session destruction, signed/accepted SLO message, and verified callback if present.

### Test 2 — Successful IdP-Initiated

1. Log in to the SP via the test IdP.
2. Go to the IdP and initiate logout using the IdP's SLO-enabled feature.
3. Confirm the IdP actually **emits a LogoutRequest to the SP**, rather than only clearing IdP cookies.
4. The browser POSTs `SAMLRequest` to `/logout/saml2/slo`.
5. Spring verifies signature, issuer, destination, and NameID/session via the validator.
6. The SP invalidates the session and returns a signed LogoutResponse to the IdP.
7. Access a protected SP route again to verify the old session is gone.
8. Observe the IdP continuing to log out other SPs or displaying the result, depending on policy.

**Expected:** forged/bad-signature requests do not delete sessions, while valid requests clean up the appropriate SP session.

### Test 3 — Separate Local Logout

1. Log in to the SP from the IdP; record the SP session (without exposing cookies).
2. `POST /logout` using the two-endpoint configuration in section 12.
3. Confirm **no** LogoutRequest is sent to the IdP.
4. Open a fresh SP login; while the IdP session remains alive, the IdP may SSO back in non-interactively.
5. Do not call this a local logout bug; this is the intentional difference.

### Test 4 — Federation Partial / No Callback

1. In the test IdP, simulate a participating SP failing or not responding to SLO.
2. Check whether the IdP emits `PartialLogout` or its own status; do not guess.
3. Simulate closing the browser before the SP callback.
4. Confirm the SP local session is still destroyed.
5. Record an unconfirmed federated logout metric and UX fallback, without recreating the session.

## 18. Negative and Security Testing

| Scenario | Condition to Prove |
| --- | --- |
| IdP-initiated `LogoutRequest` unsigned or bad signature | SP does not let an untrusted sender destroy sessions |
| Request has issuer not matching registration | Reject / do not destroy another partner's session |
| Request contains NameID/SessionIndex not belonging to session | Do not destroy wrong user/session |
| Destination points to different host/path | Reject message meant for another target |
| Expired request or replayed ID | Do not re-execute causing policy-violating side effects |
| SP-initiated LogoutResponse has InResponseTo differing from request | Do not treat callback as confirming pending transaction |
| Unsigned LogoutResponse / wrong cert | Do not treat success status as trustworthy |
| Cross-site browser POST missing session cookie | Classify correlation/cookie failure; do not drop validation |
| POST logout missing CSRF token | Browser cannot force user logout via forged request |
| IdP does not publish SLO metadata | SP does not equate SSO login with SLO; explicit config/fallback |
| Proxy sets wrong scheme/host | Fix SLO Destination/ResponseLocation from public base URL |
| Two tabs log out nearly simultaneously | State repository does not confuse request ID/RelayState; idempotent flow |
| Multi-node / another SP pod receives callback | Repository/session state can be looked up or fails safely |
| IdP failure when logging out SP-A then SP-B | Report partial/unverified clearly; do not claim all SPs logged out |

**Only perform signature forgery, replay, and session-mismatch tests in an authorized lab/test IdP**; never tamper with real messages in production or test against real users.

## 19. SameSite Cookies and Session Issues in Front-Channel SLO

The browser may POST from the IdP to the SP in a **cross-site** request. An SP cookie set with `SameSite=Lax` is normally not sent on ordinary cross-site POSTs; `SameSite=Strict` is even more restrictive. This can prevent the SP from finding the active login session when receiving an IdP-initiated LogoutRequest, or prevent matching callback state in SP-initiated logout.

When diagnosing, distinguish:
- **SP session intentionally destroyed** during SP-initiated flow.
- **Session missing because the cookie was not sent by the browser** during IdP-initiated flow.
- **Logout request repository** holding transaction ID/RelayState for the callback.
- **IdP session** residing on the IdP domain, not an SP cookie.

Steps:
1. Inspect the SP's `Set-Cookie` and `Cookie` headers on the SLO POST request using browser tests.
2. Check `SameSite`, `Secure`, `Domain`, `Path`, proxy HTTPS, and browser policy.
3. Verify the session store in multi-replica environments.
4. If using `SameSite=None; Secure` for cross-site requirements by design, evaluate CSRF/logout forgery/session fixation independently.
5. Never allow forged LogoutRequests just to "work around missing cookies".
6. For iframes/third-party cookies, check browser blocking policies; `SAML POST binding` does not automatically bypass them.

**Do not use CORS headers to fix SLO form POST errors.** Top-level HTML form navigation differs from cross-origin `fetch()`. An HTTP 403 may come from CSRF, an endpoint filter, or protocol validation; classify it via logs.

## 20. Differences Between Browser, SLO, and Back-Channel

SAML Web Browser SLO usually uses **front-channel**:
- The IdP or SP creates a SAML message;
- The browser carries the message to the other side via redirect or form POST;
- The browser continues carrying responses/hopping across SPs.

If the browser closes the window, blocks cookies, blocks auto-post scripts, or the user switches tabs, a federated logout chain can be interrupted.

**Back-channel logout** is the idea of server-to-server exchange over another endpoint/method such as SOAP depending on profile/capability; not every Spring Security SAML SLO API supports all bindings/profiles out of the box. Do not assume having OpenSAML on the classpath means the SP provides SOAP Single Logout, Artifact, or automatically revokes all JWT tokens. Choose an architecture matching the requirement.

### Why Doesn't Logging Out of App A Immediately Log Out App B?

Because when SP-A deletes its local session, SP-B still keeps its own session. Only when the IdP orchestrates SLO with SP-B, or the applications have a dedicated configured server-side session revocation mechanism, does B get a chance to destroy its session. If B does not participate in SLO or does not receive the message, B's session may remain.

### Why Doesn't Logging Out from the IdP Immediately Change an Open SP Screen?

Without a browser request to the SP, the SP may continue displaying the previously rendered page in an open tab. Immediate UI updates depend on frontend session checks, polling, SSE/WebSocket, or navigation; **the SLO protocol does not instantaneously turn every open tab into a logged-out screen**. New requests to protected resources must enforce session/authentication checks per policy.

## 21. Standalone Java 17: Simulating Ordered Logout Decisions

To understand the difference between **"destroy local before waiting for IdP reply"** and **"verify IdP request before destroying local"**, this program uses only JDK 17 and runs standalone. It simulates state, **does not parse SAML XML**, does not cryptographically sign/verify, does not destroy a real HttpSession, and does not represent every IdP variant.

File `SamlLogoutDecisionDemo.java`:

~~~java
public final class SamlLogoutDecisionDemo {

    record Result(String local, String federation, String response) {
    }

    static Result spInitiated(boolean idpResponseVerified) {
        // Spring SP-initiated: local logout happens before external reply.
        String federation = idpResponseVerified ? "CONFIRMED" : "UNKNOWN";
        return new Result("LOGGED_OUT", federation, "NOT_APPLICABLE");
    }

    static Result idpInitiated(
            boolean requestSignatureValid,
            boolean matchingSession) {

        if (!requestSignatureValid || !matchingSession) {
            return new Result("ACTIVE", "UNKNOWN", "REJECTED");
        }
        // Only a verified IdP request for this session is accepted.
        return new Result("LOGGED_OUT", "REQUESTED", "SENT");
    }

    public static void main(String[] args) {
        Result a = spInitiated(true);
        Result b = spInitiated(false);
        Result c = idpInitiated(false, true);
        Result d = idpInitiated(true, true);

        System.out.println("SP verified: local=" + a.local()
                + ", federation=" + a.federation());
        System.out.println("SP no callback: local=" + b.local()
                + ", federation=" + b.federation());
        System.out.println("IdP invalid: response=" + c.response()
                + ", local=" + c.local());
        System.out.println("IdP valid: response=" + d.response()
                + ", local=" + d.local());
    }
}
~~~

Compile/run with JDK 17+:

~~~bash
javac SamlLogoutDecisionDemo.java
java SamlLogoutDecisionDemo
~~~

**Exact** stdout:

~~~text
SP verified: local=LOGGED_OUT, federation=CONFIRMED
SP no callback: local=LOGGED_OUT, federation=UNKNOWN
IdP invalid: response=REJECTED, local=ACTIVE
IdP valid: response=SENT, local=LOGGED_OUT
~~~

Explanation:
- Both SP-initiated branches mark local logout before knowing whether the IdP returns a valid response.
- The IdP-initiated branch rejects forged requests and therefore **does not destroy the local session**.
- Only an IdP request simulated as "signature valid + matching session" proceeds to local cleanup and LogoutResponse.
- The `idpResponseVerified=true` parameter is an **input assumption**, not proof of logout across all SPs.
- In production, additionally validate issuer, destination, validity window, binding/XML signature, session index, replay, metadata trust, TLS, and browser/session state. Never treat two booleans from this example as a production SAML verifier.

## 22. IdP-Initiated Principle: Checking Only the Signature Is Not Enough

A SAML LogoutRequest with a valid signature that **does not match the principal/session** can still cause a serious error if the SP logs out the wrong user.

At minimum, check:
1. **Trust anchor/registration:** the request was issued by the IdP federated with this SP, not another IdP.
2. **Issuer:** entity ID matches the registration.
3. **Destination:** public URL, context path, and binding/endpoint match.
4. **Signature:** the signature belongs to the right message/query binding and trusted key.
5. **Subject:** NameID/format/qualifier matches the SAML user in the relevant session; do not merely compare arbitrarily normalized usernames/emails.
6. **SessionIndex:** if present, use its proper meaning and scope; do not treat the index as an HTTP cookie.
7. **Liveness:** IssueInstant/NotOnOrAfter if present, clock skew, request ID replay.
8. **User-session binding:** identify which local session is authorized to be destroyed; never globally destroy sessions by an unverified NameID.
9. **Response:** create the appropriate LogoutResponse/status only after verifying the request.
10. **Audit:** record events without placing raw NameID/Assertion or signed XML in public logs.

Per Spring documentation, `Saml2LogoutRequestValidator` is responsible for validating inputs at the SLO endpoint. If application policy requires additional validation, customize via the version's extension point, **preferring to delegate to the default validator and then add extra checks**, never replacing it with a no-op validator.

## 23. Distinguishing Protocol Errors from Local Verification Errors

| Symptom | Is It "IdP Logout Failed"? | Check |
| --- | --- | --- |
| Spring lacks SLO because IdP metadata misses `SingleLogoutService` | Incomplete federation configuration | Metadata, IdP policy, and SP SLO registration |
| `POST /logout` immediately returns 403 | Not necessarily | CSRF token, security filter chain, and session |
| Spring emits LogoutRequest but IdP rejects signature | IdP reports SP request invalid | SP signing key/cert, IdP trust, binding |
| IdP receives LogoutRequest but sends no callback | Unconfirmed | IdP audit/UX/response endpoint, browser, proxy |
| `LogoutResponse` to SP has error status | IdP reports error/partial | Trusted StatusCode, other SP coordination |
| Spring rejects LogoutResponse due to wrong InResponseTo | SP/local correlation error or forged message | LogoutRequestRepository, session, RelayState, replay |
| IdP-initiated request has bad signature | SP rejects properly | IdP signing cert/metadata, request tampering |
| IdP-initiated request valid but wrong NameID | SP must avoid wrong deletion | Identity mapping, qualifier, session binding |
| SLO POST sends no cookie | Browser/session state issue | SameSite/Secure, domain, cross-site form |
| User logs out locally then immediately SSOs again | May be normal | IdP session remained due to local-only logout |
| One app retains session after SLO | Incomplete federation coverage | Whether SP participates in SLO, timeout, IdP orchestration |
| GET goes to ACS instead of SLO | Endpoint routing error | SLO Location/ResponseLocation, binding, firewall |
| HTTP 200 on IdP page | Insufficient | Actual SAML status and IdP session |
| API token still works after SAML SLO | Separate token system not revoked | Token/session revocation at application layer |

**Never use a single HTTP status to judge all of SLO.** SAML status lives in `LogoutResponse/StatusCode`; local Spring errors may involve signature, issuer, message parsing, or session/correlation; business/token issues typically lie outside SAML.

### An Evidence-Based Incident Report Template

~~~text
Scenario: RP-initiated SAML Single Logout
SP registration: corp
Local logout: completed (session invalidated)
SAML LogoutRequest: sent (ID recorded securely)
IdP callback: not observed
Federation result: unknown / not verified
Next investigation:
  - IdP SLO event log
  - SingleLogoutService binding and ResponseLocation
  - Browser SAML form/redirect and cookies
  - SP request repository correlation
~~~

This is a **PII-free** ticket template, not stdout emitted by Spring. Do not print raw LogoutRequests, real NameIDs, RelayState, cookies, private keys, or IdP user identifiers into shared logs.

## 24. Common Reasons SLO Fails to Work

### 24.1 saml2Logout Not Enabled

If only `.saml2Login(... )` is configured without SLO DSL/registration, logout is typically local-only. Add proper SLO configuration, ensuring IdP support, signing credentials, and endpoints exist. Do not label UI text "SSO logout" when the backend does not support federation.

### 24.2 Missing SingleLogoutService

IdP metadata having `SingleSignOnService` does not guarantee it has `SingleLogoutService`. Coordinate with the IdP; do not guess the SLO URL from the login URL or invent a matching path arbitrarily.

### 24.3 Invalid SP Signing Credential

The SP signs LogoutRequests/LogoutResponses with its private key, and the IdP must hold the matching SP public cert. If keys/certs mismatch or IdP metadata was not updated after rotation, the IdP will reject. Never export the SP private key to the IdP to "fix" the error.

### 24.4 Stale IdP Verification Certificate

The SP uses the IdP's public signing cert to verify inbound requests/responses. If the IdP rotates SAML signing keys while the SP still trusts an old snapshot, signatures fail. Update verified metadata, maintain an overlap/rotation window per policy, and check all replicas.

### 24.5 NameID Differs from Login

The IdP may use persistent/transient NameIDs with specific qualifiers/formats. If the SP logs out using an application username incompatible with the NameID the IdP attached to the session, the IdP may fail to locate the session. Use the exact SAML identity per protocol/contract; avoid arbitrary mapping.

### 24.6 Lost Cookie or State

IdP-initiated POST arrives at the SP without the browser sending the session cookie, or an SP-initiated callback lands on another pod, causing request state/session mismatch. Inspect SameSite, session store, and repository before altering protocol validation.

### 24.7 Wrong SLO URL Due to Proxy

For example, the SP advertises `http://internal:8080/logout/saml2/slo` while the IdP calls `https://app.example.org/logout/saml2/slo`. Destination validation or routing fails. Configure the public base URL and trust forwarded headers only from trusted proxies; update IdP metadata.

### 24.8 Browser Fails to Complete Frontend Chain

An SLO flow requires the browser to carry multiple POSTs/Redirects. If the browser closes the tab, blocks scripts, or IdP/third-party policies interfere, the flow may not finish. Do not call this "login assertion invalid" when a logout transaction simply has no response.

## 25. Security Scenario: User Logs Out of the App Yet Remains Logged In

A common support scenario:

1. User opens application A and logs in through the IdP.
2. User clicks logout; application A destroys the HttpSession.
3. User clicks "Return to A".
4. A redirects the browser to the IdP; the IdP cookie is still present.
5. The IdP returns a new SAMLResponse, and A creates a new session.
6. User says "logout does not work".

**Correct analysis:**
- If that button only performs local logout, **re-SSO** behavior is completely expected.
- If the button is advertised as federation logout, you must prove A sent a LogoutRequest, the IdP received/completed SLO, and the corresponding IdP session was destroyed; otherwise it is a configuration/SLO-coverage bug.
- A cannot delete the IdP's HttpOnly cookie on another domain via JavaScript; the browser security model forbids it.
- If SLO only destroys the IdP session in browser A, never promise that all devices are logged out.

**UX suggestion:** clearly display options "Log out of this application only" and "Log out of centralized login session" if the business needs to distinguish them, while accurately describing practical limits based on federation capability.

## 26. Security Scenario: IdP Issues a Logout Request for the Wrong Session

An IdP with multiple sessions/users may issue a LogoutRequest carrying a NameID/SessionIndex that does not match the SP browser session currently open. A naive implementation might:
- Check only the IdP signature and always destroy whatever session is in the browser;
- Or look up all sessions by email from NameID and mass-destroy them;
- Or omit request ID/replay protection.

Better design:
1. Ensure the issuer and request signature match the trusted IdP.
2. Enforce NameID/SessionIndex conditions per profile and implementation.
3. Do not log out unrelated accounts/tenants.
4. Use a session registry **only if the architecture genuinely requires it**, protecting the exact request scope.
5. If no matching session is found, handle via an explicit response/error policy; never assume system-wide success.
6. Write audit logs with a correlation ID without exposing NameIDs and session keys.

**Spring Security provides suitable filters/validators to handle SLO**, but if business requirements demand logging out all sessions/devices, that is an additional capability to design and test, not something `saml2Logout()` creates automatically.

## 27. Operations Checklist in Kubernetes and Multi-Node Environments

- [ ] Every pod has identical IdP metadata/trust and appropriate SP signing keys during rollout.
- [ ] Public SP entity ID, ACS, and SLO URLs are consistent across nodes.
- [ ] Logout callbacks reaching another node can locate request state via session/Redis cache/sticky session as configured.
- [ ] TTL, replay protection, and cleanup exist for logout transaction state.
- [ ] Cookie SameSite/Secure supports cross-site SAML POST while retaining CSRF/login/logout forgery protection.
- [ ] Private keys are never stored in container images or source repositories.
- [ ] When rotating IdP signing certs, update verified metadata/verification credentials and prevent version skew across pods.
- [ ] When rotating SP signing certs, ensure the IdP receives the new public cert before the SP signs with the new key.
- [ ] SLO statuses and metrics distinguish local / remote reported / verified / unknown / partial.
- [ ] The SLO endpoint is handled only by proper filters/validation; never add an open controller allowing arbitrary POSTs to destroy sessions.
- [ ] Never trigger global session revocation from an untrusted NameID.
- [ ] IdP outages/timeouts never cause the application to recreate a locally logged-out session.

## 28. Q&A Set for SP-Initiated and IdP-Initiated SLO

**Q1.** A user is in the SP, clicks logout, and the SP sends a LogoutRequest to the IdP. Which flow is this?

**Answer:** **SP-initiated (RP-initiated) SLO**. The party creating the first LogoutRequest is the SP. If the IdP returns a LogoutResponse, the SP validates the callback.

**Q2.** The IdP sends a signed LogoutRequest to the SP's `/logout/saml2/slo`. Which party creates the LogoutResponse?

**Answer:** The SP, after verifying the LogoutRequest, destroying the matching local session, and building/signing a LogoutResponse back to the IdP. This is **IdP-initiated (AP-initiated)**.

**Q3.** A user logs out at the SP and sees the IdP screen, but no LogoutResponse callback returns to the SP. Must the SP restore the old session?

**Answer:** **No.** SP local logout has already happened; the federation result is unconfirmed. Never recreate a session just because a callback is missing.

**Q4.** An SLO LogoutResponse has `InResponseTo="_a"` while the LogoutRequest in the repository has ID `_b`. Should a Success status be treated as valid?

**Answer:** No. Correlation is wrong; it must be handled by the validator and must not mark an unrelated transaction successful.

**Q5.** An IdP-initiated LogoutRequest has an invalid signature but contains a NameID matching a currently logged-in user. May the session be deleted?

**Answer:** No. NameID does not replace signature/issuer/trust; forged requests must be rejected.

**Q6.** A user completes local logout, reopens the app, and gets SSO immediately. Does that prove logout failed?

**Answer:** No. The IdP session remained, allowing a new SP session to be created. Determine whether it was local logout or SLO, then verify the IdP flow.

**Q7.** A LogoutRequest contains SessionIndex. Can it be treated as `JSESSIONID` to look up the session?

**Answer:** No. SessionIndex is a SAML identifier provided by the IdP; the servlet session ID is a separate SP mechanism.

**Q8.** After a successful SLO, other API/JWT tokens still work. Is this immediately a SAML bug?

**Answer:** Not necessarily. SAML SLO does not automatically revoke tokens of all other mechanisms. Separate token revocation/session governance must be designed per requirement.

**Q9.** IdP metadata has only SingleSignOnService and no SingleLogoutService. Does the SP already support SAML logout?

**Answer:** There is no evidence of SLO; the IdP must publish/configure SLO and the SP must register the SLO URL, signing, and verification properly. Login SSO does not prove logout SSO.

**Q10.** Why does the browser returning HTTP 200 on an IdP page not prove LogoutResponse status Success?

**Answer:** HTTP status and SAML StatusCode are two different layers. You must observe an actual LogoutResponse emitted and verified by the SP/IdP per the flow.

**Q11.** In Spring Security, why is a GET to `/logout` normally insufficient to trigger SLO?

**Answer:** Under CSRF configuration and default Spring logout, logout mutates state and is therefore triggered by a **POST with valid CSRF**, not an unconditional GET.

**Q12.** A valid IdP-initiated LogoutRequest was processed by the SP, yet the final browser page is shown by the IdP. Is this an SP success handler bug?

**Answer:** No. After the SP emits the LogoutResponse, **the IdP controls the rest of the browser flow** in this direction.

**Q13.** An older SP cannot receive SLO and the IdP reports PartialLogout. The current SP has already destroyed its local session. Can we display "logout completed on all applications"?

**Answer:** No. This is a **partial federation logout**; report the exact scope and guidance for applications that did not log out.

**Q14.** When deploying two endpoints for local and SAML logout, which URL receives inbound protocol messages from the IdP?

**Answer:** Typically still `/logout/saml2/slo`; `/logout` or `/saml2/logout` are the **SP-side logout trigger buttons**, depending on the DSL.

**Q15.** A SAML logout request has a valid signature, yet specifies a NameID/SessionIndex not belonging to the current session's principal. Can the session be destroyed because the IdP is a trusted partner?

**Answer:** Do not destroy the wrong session. Principal/session matching rules of the validator and contract flow must be enforced; a trusted key is a necessary condition, **not the sole sufficient condition**.

## 29. SAML Single Logout Completion Checklist

- [ ] Clearly distinguish business requirements for **local logout**, **SP-initiated SLO**, **IdP-initiated SLO**, and multi-device "global logout".
- [ ] IdP metadata verified to contain `SingleLogoutService` with matching binding/URL.
- [ ] SP registration publishes the right public `singlelogout.url` and the IdP has imported SP metadata.
- [ ] SP signing private key and X.509 cert configured properly; IdP holds SP's public cert for verification.
- [ ] SP holds trusted IdP public signing certificates to verify inbound requests/responses.
- [ ] `.saml2Logout(... )` enabled on the right Servlet SecurityFilterChain.
- [ ] If using default SLO, users submit a valid `POST /logout`; CSRF is not disabled application-wide.
- [ ] If separate local logout is needed, configure two meaningful trigger endpoints with unambiguous UX.
- [ ] Distinguish `SAMLRequest` / `SAMLResponse` payloads at `/logout/saml2/slo`.
- [ ] Inbound LogoutRequest is checked for signature/issuer/destination/NameID/session/timestamps/replay before local cleanup.
- [ ] LogoutResponse callback validates signature/issuer/status/InResponseTo/RelayState.
- [ ] Plan exists for SameSite cookies, session state, and multi-node request repository.
- [ ] Tested SP-initiated/IdP-initiated, invalid signature, missing callback, partial logout, and user re-SSO.
- [ ] Metrics/audit distinguish local completed from federation confirmed/partial/unknown.
- [ ] Never claim all sessions/devices/tokens are destroyed without corresponding revocation capability.
- [ ] Logs/HARs exclude raw LogoutRequest/LogoutResponse, real NameID, RelayState, cookies, and private keys.
- [ ] Rollback plan exists when IdP metadata, certificates, or SLO URLs change.

## 30. Takeaways

**SP-initiated:** user requests logout at SP → Spring clears local session → SP sends **LogoutRequest** → IdP processes and may return **LogoutResponse** to SP.  
**IdP-initiated:** IdP sends **LogoutRequest** → SP **verifies first** → SP deletes matching session → SP sends **LogoutResponse** to IdP.

In both directions, **the party issuing the LogoutRequest is the initiator**, and **SAML Single Logout is a cooperative protocol**, not an automatic promise across every browser, application, device, and access token. Trust policies, metadata, keys, callbacks, browser sessions, and federated logout scope must all be verified independently.

### Official Documentation

1. Spring Security — *Performing Single Logout* (Spring Security 7.x, both SLO directions, endpoints, filters, validation, repository): https://docs.spring.io/spring-security/reference/servlet/saml2/logout.html
2. Spring Security 6.5 — *Performing Single Logout*: https://docs.spring.io/spring-security/reference/6.5/servlet/saml2/logout.html
3. Spring Security — *Logging Out* (Servlet logout/CSRF): https://docs.spring.io/spring-security/reference/servlet/authentication/logout.html
4. Spring Security — *SAML 2.0 Login Overview* (differences between login vs. logout): https://docs.spring.io/spring-security/reference/servlet/saml2/login/overview.html
5. Spring Security API — *Saml2LogoutRequestRepository* (storing request/correlation): https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/saml2/provider/service/web/authentication/logout/Saml2LogoutRequestRepository.html
6. OASIS — *SAML V2.0 Core*, LogoutRequest/LogoutResponse, Status, SessionIndex sections: https://docs.oasis-open.org/security/saml/v2.0/saml-core-2.0-os.pdf
7. OASIS — *SAML V2.0 Profiles*, Single Logout Profile: https://docs.oasis-open.org/security/saml/v2.0/saml-profiles-2.0-os.pdf
8. OASIS — *SAML V2.0 Bindings* (HTTP Redirect/POST and RelayState): https://docs.oasis-open.org/security/saml/v2.0/saml-bindings-2.0-os.pdf
9. OASIS — *SAML V2.0 Metadata*, SingleLogoutService: https://docs.oasis-open.org/security/saml/v2.0/saml-metadata-2.0-os.pdf
