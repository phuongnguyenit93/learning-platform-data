# Testing SP-Initiated SSO from AuthnRequest to Application Session

**Module:** Spring Security – federation → SAML2 Testing.

**Objective:** Test end-to-end **SP-initiated SAML 2.0 Web Browser SSO** in a Java/Spring Security application—starting from an unauthenticated request to the application (Service Provider / Relying Party), generating an `AuthnRequest`, going through the IdP / Asserting Party, receiving `SAMLResponse` at the Assertion Consumer Service (ACS), verifying the assertion, creating an `Authentication`, persisting the application session, and accessing a protected resource. Do not stop at "correct HTTP 302" or "IdP login page appeared"; a passing test must prove **the user was authenticated by a valid assertion and the session genuinely works on subsequent requests**.

**QA principle:** clearly separate **protocol validation** (signature, Issuer, Audience, Destination, `InResponseTo`, `SubjectConfirmation`, time/replay), **authentication/session persistence** (Spring `SecurityContext`, session cookie, session fixation), and **business authorization** (roles, tenant, account, resource). These three do not substitute for one another.

This article uses **Spring Security 7.x / Spring Boot 4.x and Java 17+** examples per current contracts. For Spring Security 6.x, the overall structure is similar, but APIs, OpenSAML, and configuration must be checked against your actual BOM/runtime. The `example.test` domains and test certificates are illustrative only. Spring config snippets are **integration fragments** requiring a real sandbox IdP/metadata/credentials; the standalone Java 17 program in the hands-on section runs independently and only models invariants—**it does not create or accept real SAML assertions**.

## 1. Components and Data to Observe

A typical test model:

| Component | Illustrative value | Role |
| --- | --- | --- |
| Application SP | `https://portal.example.test` | Spring Security web app |
| SP EntityID | `https://portal.example.test/saml/sp` | Relying Party identifier trusted by the IdP |
| Registration ID | `corp` | Spring `RelyingPartyRegistration` config key |
| Protected resource | `/reports` | Requires login |
| AuthnRequest endpoint | `/saml2/authenticate/corp` | Initiates SP-initiated login |
| IdP EntityID / Issuer | `https://idp.example.test/metadata` | Trusted Asserting Party |
| IdP SSO Service | `https://idp.example.test/sso` | Receives `AuthnRequest` |
| ACS | `https://portal.example.test/login/saml2/sso/corp` | Receives `SAMLResponse` via browser POST |
| Test user | `user-17` | Sandbox test subject |
| App user | `U-100` | Internal account after verified mapping |
| Browser session | `JSESSIONID` or app-configured session ID | Stores pre/post-login state per architecture |
| SAML trust | IdP signing certificate + SP signing/decryption credentials as required | Prevents spoofing/tampering of SAML messages |

**Do not confuse** `Registration ID` (`corp`) with `SP EntityID` or `IdP EntityID`. `registrationId` is a local config key. The `Issuer` of an `AuthnRequest` must be the SP EntityID; the `Issuer` of a Response/Assertion must match the trusted IdP. `Audience` in an assertion must usually match the SP EntityID; `Recipient`/`Destination` must point to the right ACS.

### 1.1. Testing Both "Outbound" and "Inbound"

- **Outbound:** an unauthenticated browser is redirected to the right IdP; the `AuthnRequest` is valid with an `ID` and `IssueInstant`, appropriate `Destination`/`Issuer`/`AssertionConsumerServiceURL` or ACS index, correct binding, and a request signature if required by the IdP.
- **At the IdP:** a test account is authenticated, the IdP recognizes the right SP registration, and issues a Response and assertion per contract.
- **Inbound:** the browser POSTs `SAMLResponse` and `RelayState` to the ACS; Spring resolves the `RelyingPartyRegistration` and pending request; signature/conditions/subject are verified.
- **Afterward:** Spring creates `Saml2Authentication`/principal, maps the internal user, and persists the session/`SecurityContext`; a subsequent request to `/reports` with the session cookie is allowed access, while a different browser session remains unauthenticated.

**Do not substitute an OIDC `code` or CAS `ticket` for `SAMLResponse`.** This is a SAML Web Browser SSO flow, not OAuth Authorization Code or CAS Login.

## 2. Standard SP-Initiated SSO Flow

```mermaid
sequenceDiagram
    actor User as User's browser
    participant SP as Spring Security SP
    participant Store as AuthnRequest Repository / Session
    participant IdP as SAML2 Identity Provider
    participant App as App user/authorization
    User->>SP: GET /reports (no session)
    SP-->>User: 302 /saml2/authenticate/corp
    User->>SP: GET /saml2/authenticate/corp
    SP->>Store: Save AuthnRequest ID, RelayState, session, IdP
    SP-->>User: 302 to IdP SSO + SAMLRequest + RelayState
    User->>IdP: GET SSO URL with AuthnRequest
    IdP->>IdP: Validate SP, request, signature/policy
    IdP->>IdP: Authenticate test user
    IdP-->>User: HTML form POST SAMLResponse to SP ACS
    User->>SP: POST /login/saml2/sso/corp
    SP->>Store: Resolve pending AuthnRequest and correlation
    SP->>SP: Validate signature/issuer/audience/recipient/time/replay
    SP->>App: Map NameID/attributes -> internal user, roles
    App-->>SP: U-100 + authorities
    SP->>SP: Create Authentication; persist SecurityContext/session
    SP-->>User: Redirect to safe route /reports
    User->>SP: GET /reports with session cookie
    SP->>SP: Load SecurityContext from session
    SP->>App: Authorize U-100 to view reports
    App-->>SP: ALLOW
    SP-->>User: 200 HTML/JSON for U-100
```

This diagram shows the typical **Redirect binding for AuthnRequest and POST binding for Response**; Spring/IdP may choose POST for `AuthnRequest` or another binding per metadata. Therefore, "correct flow" must follow the **negotiated/configured binding**, never hard-coding that all `AuthnRequest` exchanges are HTTP GET.

### 2.1. Events in Logs/Traces

| Step | Measurable event | PASS evidence |
| --- | --- | --- |
| 0 | Anonymous request to protected resource | No user `Authentication`; route protected |
| 1 | Redirect to authentication entry point | Right SP registration/IdP, no open redirect |
| 2 | `AuthnRequest` generated | Unique `ID`, exact `Issuer`/`Destination`/ACS |
| 3 | Request stored | Pending request bound to original browser/session |
| 4 | IdP receives request | IdP accepts SP metadata/signing policy |
| 5 | User authenticates | Sandbox IdP authenticates valid test user |
| 6 | ACS receives `SAMLResponse` | Correct HTTP binding, no tokens leaked in logs |
| 7 | Response validation | Signature/trust/issuer/audience/time/correlation PASS |
| 8 | Principal mapping | External NameID/Issuer maps to internal `U-100` |
| 9 | Spring authentication completed | `Saml2Authentication.isAuthenticated()` is true |
| 10 | Session persisted | `SecurityContext` remains on a **subsequent request** |
| 11 | Authorization | User `U-100` accesses permitted resource; unauthorized user denied |
| 12 | Session ended | Logout/expiry forces re-authentication on protected routes |

**End-to-end testing must prove steps 7–11.** A `SAMLResponse` with `StatusCode=Success` is insufficient; the mere presence of a `JSESSIONID` cookie is also insufficient because a session can be created before login simply to store the `AuthnRequest`.

## 3. Preparing an Actually Testable IdP/SP Environment

### 3.1. Choosing a Sandbox/Fixture IdP

You can use:
- A dedicated SAML2-capable IdP realm/sandbox, such as a Keycloak test realm, an organizational test IdP instance, or an approved SAML test provider.
- An SP registration isolated from production with dedicated signing/verification certificates.
- Test users with zero production privileges and no overlap with real accounts.
- HTTPS or localhost/loopback permitted by test contract; never disable TLS verification in integration tests against a hosted IdP.
- Fixed or pinned metadata per test policy; never let tests fetch metadata/JWKS from a URL chosen by request parameters.
- Synchronized NTP/clocks across nodes; test time skew with **dedicated fixtures**, never by adjusting a production domain controller.

**Do not use a production IdP to issue real assertions** and paste `SAMLResponse` payloads into CI logs. Assertions often contain NameID/email/groups and have short lifetimes. Test fixtures need **test-dedicated keys/certificates**, never production keys.

### 3.2. SP Metadata / ACS / EntityID Must Match

Cross-check between SP and IdP:
1. The SP EntityID declared by the app matches the `Audience` the IdP will issue.
2. The ACS URL registered at the IdP matches the URL the Response is posted to, including scheme, host, port, context path, and registration ID per contract.
3. The IdP SSO endpoint/EntityID in the SP registration matches metadata.
4. The verification certificate is the IdP's trusted key; if the IdP rolls over certificates, test both overlap and rotation.
5. The SP signing certificate/private key is valid when the IdP requires signed `AuthnRequest` payloads; test failure with a wrong key.
6. If assertion encryption is enabled, provide real test SP decryption credentials.
7. Reverse proxies must preserve public scheme/host and callback path; avoid letting metadata emit `http://backend:8080` as the ACS.
8. If the IdP selects the ACS by index rather than URL, verify metadata mapping properly without requiring both URL and index simultaneously.
9. `RelyingPartyRegistration` may be resolved from a pending `AuthnRequest`/`registrationId`/Issuer; tests must not let an untrusted issuer select arbitrary configs.
10. Restrict callbacks/ACS to supported bindings only; never let another endpoint bypass the SAML validator.

### 3.3. Dependencies and Spring Config (Orientation Fragment)

For a Spring Boot Servlet application using Spring Security SAML2, typical modules are:

```xml
<!-- Dependency fragment: requires matching Boot parent/BOM. -->
<dependencies>
  <dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-webmvc</artifactId>
  </dependency>
  <dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-security</artifactId>
  </dependency>
  <dependency>
    <groupId>org.springframework.security</groupId>
    <artifactId>spring-security-saml2-service-provider</artifactId>
  </dependency>
  <dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-test</artifactId>
    <scope>test</scope>
  </dependency>
  <dependency>
    <groupId>org.springframework.security</groupId>
    <artifactId>spring-security-test</artifactId>
    <scope>test</scope>
  </dependency>
</dependencies>
```

Spring SAML2 uses OpenSAML; some releases require the Shibboleth releases Maven repository for dependencies. Follow the BOM/version/repository for the **exact Spring Security release** you are running instead of mixing OpenSAML 4 and 5. On Spring Boot 3.x, web starter/dependency names may differ from Boot 4.x, so align with the BOM rather than copying XML blindly across versions.

Example IdP config **describing the contract**—a real test certificate must be supplied:

```yaml
spring:
  security:
    saml2:
      relyingparty:
        registration:
          corp:
            entity-id: https://portal.example.test/saml/sp
            acs:
              location: https://portal.example.test/login/saml2/sso/corp
            assertingparty:
              entity-id: https://idp.example.test/metadata
              verification:
                credentials:
                  - certificate-location: classpath:idp-test.crt
              singlesignon:
                url: https://idp.example.test/sso
                sign-request: false

server:
  servlet:
    session:
      cookie:
        secure: true
        http-only: true
```

**Explanation and limitations:**
- `corp` is the `registrationId` used to open `/saml2/authenticate/corp`.
- `entity-id` under relying-party is the **SP EntityID**, distinct from the IdP issuer under `assertingparty.entity-id`.
- `acs.location` is the public callback; some Spring Boot releases use a different property shape or require a custom `RelyingPartyRegistration` builder; **check the configuration metadata of your exact Boot release before applying**.
- `sign-request=false` is acceptable only if the test IdP **does not require** signing. If the IdP requires signed `AuthnRequest` messages, configure the SP signing key/cert; do not disable signing to avoid testing it.
- `idp-test.crt` is a signing verification certificate approved by the test trust store, never loaded from an unverified request/Response.
- This YAML omits app main/controllers, the peer IdP metadata registration, DNS/cert infrastructure, and CA trust: **do not treat it as a standalone runnable application**.
- Real applications should define how IdP metadata and signing/decryption credentials/rotation are managed instead of hard-coding test environments.

### 3.4. SecurityFilterChain and Protected Endpoint

```java
package com.example.samltest;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class SamlSecurityConfiguration {
    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http)
            throws Exception {
        http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/", "/error").permitAll()
                .requestMatchers("/reports/**").authenticated()
                .anyRequest().authenticated())
            .saml2Login(Customizer.withDefaults());
        return http.build();
    }
}
```

This is a **Spring configuration fragment**; it needs a Spring Boot app and a real `RelyingPartyRegistration`. When an unauthenticated browser visits `/reports`, Spring must initiate SAML login/redirect to the IdP. With multiple registrations, Spring may show a login picker; for stable E2E, tests can directly open `/saml2/authenticate/corp`. Never make SAML/ACS endpoints `permitAll` in a way that disables SAML filters; Spring's filter must process the callback **before** authorization logic.

## 4. Step 1 – Anonymous Request Must Lead to SP-Initiated Login

**Input:**

```http
GET /reports HTTP/1.1
Host: portal.example.test
Cookie: (no app login session yet)
```

**Expected:**
- The protected route returns no user-specific content when unauthenticated.
- Spring's entry point starts the SAML flow: redirecting to `/saml2/authenticate/corp` or a login picker page depending on the number of registrations.
- After hitting `/saml2/authenticate/corp`, the request goes to the **registered IdP SSO URL**.
- No username/authenticated session appears in the backend merely because an `HttpSession` exists to hold handshake state.
- When testing `/saml2/authenticate/corp` directly, the outcome depends on configured binding: Redirect binding returns 3xx to the IdP; POST binding may return an auto-submitting HTML form.
- Never use raw query parameters like `?idp=https://evil.example` to choose an issuer/SSO destination.

**QA criterion:** compare the actual IdP SSO hostname against metadata/registration, rather than comparing the entire `Location` byte-for-byte because `SAMLRequest` contains ID, `IssueInstant`, and `RelayState` that change on every run.

### 4.1. Distinguishing HTTP 302 Redirect from Successful Authentication

```text
GET /reports                     → 302 /saml2/authenticate/corp (possible)
GET /saml2/authenticate/corp     → 302 https://idp.example.test/sso?SAMLRequest=...
GET https://idp.example.test/sso → IdP login page
```

**This is only the starting point.** A test checking only 302 **does not prove**:
- That the IdP accepts the SP EntityID/signature.
- That the IdP issues an assertion for the right user.
- That the SP verifies the response.
- That Spring persists an authenticated `SecurityContext`.
- That the app maps and authorizes the principal.

At least one E2E test must use a `SAMLResponse` genuinely signed by the test IdP.

## 5. Step 2 – Inspecting the Generated AuthnRequest

Structural XML example (abbreviated, not a full signed production request):

```xml
<samlp:AuthnRequest
    xmlns:samlp="urn:oasis:names:tc:SAML:2.0:protocol"
    xmlns:saml="urn:oasis:names:tc:SAML:2.0:assertion"
    ID="_request_123"
    Version="2.0"
    IssueInstant="2026-11-07T03:00:00Z"
    Destination="https://idp.example.test/sso"
    AssertionConsumerServiceURL=
        "https://portal.example.test/login/saml2/sso/corp"
    ProtocolBinding=
        "urn:oasis:names:tc:SAML:2.0:bindings:HTTP-POST">
  <saml:Issuer>https://portal.example.test/saml/sp</saml:Issuer>
</samlp:AuthnRequest>
```

This is **structural XML for reading comprehension**; attribute formatting and `AuthnRequest` signing policy may differ in real environments. Never copy `ID="_request_123"` as a fixed value when issuing real `AuthnRequest` messages.

### 5.1. Fields That Must Be Verified

| Field | Expected | Failure when wrong |
| --- | --- | --- |
| `ID` | Present, unique/hard-to-guess per protocol, saved pending | Undefined replay/correlation |
| `Version` | SAML 2.0 | Profile mismatch |
| `IssueInstant` | Reasonable timestamp per clock policy | Stale request/clock skew |
| `Issuer` | SP EntityID registered at the IdP | IdP rejects SP |
| `Destination` | SSO endpoint confirmed by IdP signing/metadata | Wrong destination/open redirect |
| `AssertionConsumerServiceURL` or ACS index | Matches registered ACS contract | IdP posts Response to wrong endpoint |
| `ProtocolBinding` | Desired Response binding (usually HTTP-POST) | IdP issues incompatible binding |
| `NameIDPolicy` if used | Format/`AllowCreate` per agreement | Principal mapping fails |
| `RequestedAuthnContext` if used | Required assurance/MFA supported by IdP | AuthnContext mismatch |
| `ForceAuthn` if used | Intentionally forces IdP re-authentication | Unexpected UX/step-up |
| `IsPassive` if used | Non-interactive response per policy | IdP needs interactive login, must fail |
| Request signature | Signed/algorithm/certificate per IdP policy | IdP rejects or weakens security |
| `RelayState` | Opaque, short, session-correlated | Login fixation/open redirect |

**Do not assume every field is always present.** For instance, a request may use an ACS index or URL; `NameIDPolicy`/`RequestedAuthnContext` are optional. Tests must verify the **contract agreed upon with the IdP**, rather than hard-coding every item as mandatory.

### 5.2. Decoding the Right Binding When Analyzing Network Traces

For **HTTP Redirect Binding**:
1. Browser receives `Location` containing `SAMLRequest=<URL-encoded base64>`.
2. URL-decode the **query parameter**.
3. Base64-decode `SAMLRequest`.
4. Decompress **raw DEFLATE** per SAML Redirect binding (not GZIP).
5. Parse XML safely: forbid external entities/DTDs, bound input size.
6. If `SigAlg`/`Signature` are present, verify the signature **over canonical query string bytes** per binding; do not treat the presence/absence of an XML `<ds:Signature>` as the entire Redirect binding signature logic.

For **HTTP POST Binding** of `AuthnRequest` (if configured):
1. Browser receives an auto-submitting HTML form.
2. `SAMLRequest` is Base64 of XML, normally **without raw DEFLATE** unlike Redirect binding.
3. Signature is represented per contract/binding (e.g., embedded XMLDSig).
4. Do not blindly apply inflate to all bindings.

**Never paste real `SAMLRequest`/`SAMLResponse` payloads into public decoders.** Use an approved internal tool capable of inspecting ID/Issuer/Destination without saving private credentials or PII into telemetry.

### 5.3. Redirect Binding Signatures Must Be Checked Separately

Example parameters:

```text
SAMLRequest=<URL-ENCODED-BASE64-DEFATE>
RelayState=<OPAQUE-ID>
SigAlg=<ALGORITHM-URI>
Signature=<BASE64-SIGNATURE>
```

When signed over Redirect binding, the signature covers canonical ordered query parameters per SAML Bindings; the validator needs exact encoding/order and the trusted SP verification certificate. Parsing the XML and checking "content looks right" is not enough.

**Test expectation:** if the IdP requires signed `AuthnRequest` payloads and the SP sends an unsigned or badly signed request, the sandbox IdP must reject it. If the contract permits unsigned requests, tests may omit `Signature`, though Response/Assertion verification at the SP remains mandatory.

## 6. Step 3 – AuthnRequest Repository, RelayState, and Original Browser Session

Spring Security uses `Saml2WebSsoAuthenticationRequestFilter` to create `AuthnRequest` and persist it via `Saml2AuthenticationRequestRepository`. Per Spring Security 7.1 documentation, the default repository is `HttpSessionSaml2AuthenticationRequestRepository`, storing `AbstractSaml2AuthenticationRequest` in `HttpSession`.

**Why must the repository be tested?** When the IdP returns a Response, the SP needs to know:
- **Which request ID** the Response answers (`InResponseTo`).
- **Which IdP** and SP registration the request was issued for.
- Which browser/session initiated the login.
- What `RelayState` belonged to that handshake.
- Whether the request has already been consumed.
- Whether the request expired or switched login context.

If `AuthnRequest` is fetched solely by `InResponseTo` or `RelayState` from a shared cache **without binding to the initiating browser**, an attacker can perform **login fixation/login CSRF**: forcing a SAML Response from their own session into a victim's session. Spring docs specifically highlight the fixation-protection benefit of a **session-bound repository**.

### 6.1. Session Correlation Cases

| Test | Context | Expected |
| --- | --- | --- |
| Matching session | Browser A starts login; A receives Response | Accept after SAML validation |
| Wrong session | A starts, browser B submits A's Response/`RelayState` | Reject; do not log B in as A's identity |
| Wrong request ID | Response `InResponseTo` differs from pending ID | Reject |
| Tampered `RelayState` | Response carries unexpected value | Reject or safe failure; never redirect to raw `RelayState` |
| Replay | Second callback reusing same Response ID/Assertion ID | Reject; do not create a new session |
| Expired request TTL | IdP responds after timeout | Reject / restart flow intentionally |
| Two parallel tabs | A initiates twice | Policy/repository handles cleanly; never cross-bind Request A to Response B |
| Different node/pod | Start on pod1, ACS on pod2 | Shared session/state works or sticky session verified |
| Session rotated before callback | Cookie/session ID changed | State transfer/correlation per design, no mismatch |
| Session dropped mid-flow | Cookie omitted or store lost | Fail closed; never fall back to unsecured lookup |
| Different IdP | `AuthnRequest` IdP A, Response IdP B | Reject |
| Different ACS | Request ACS `corp`, POST to `partner` | Reject or resolve exact registration from trusted context |

### 6.2. `CacheSaml2AuthenticationRequestRepository` Across Multiple Nodes

Spring Security provides `CacheSaml2AuthenticationRequestRepository` to store requests keyed by `RelayState` in a distributed cache. This can help when `SameSite` cookies or cluster topologies make session repositories difficult. **However, this does not mean browser binding can be dropped.** You must still enforce browser correlation, TTL, one-time request consumption, and access controls. A cache mapping `RelayState → AuthnRequest` that any client can look up can introduce login fixation.

In a cluster, verify:
- `JSESSIONID` or session cookie is readable by other pods via Spring Session/shared store if using sessions.
- The request repository shares the right backend, TTL, and atomic consume semantics.
- Clocks/NTP across nodes, valid certificates, and configs are identical.
- No duplicate IDs are emitted due to a flawed random generator.
- `InResponseTo`/`RelayState` do not leak user PII or redirect URLs.
- Missing-cookie/third-party context failures are handled safely, never by "enabling unsolicited SSO" as a workaround.

### 6.3. SameSite Cookies and HTTP POST from the IdP

IdPs normally use **cross-site POST Binding** back to the ACS. Modern browsers may **omit `SameSite=Lax` cookies on cross-site POSTs** by default; `SameSite=Strict` is even stricter. This can cause the SP to **fail to find the pending `AuthnRequest` in `HttpSession`** even when the `SAMLResponse` signature is valid.

How to handle:
1. Check browser network traces to confirm whether the ACS request carries the matching session cookie (do not publish raw cookies).
2. Verify actual browser `SameSite` behavior; **do not rely on temporary browser exceptions**.
3. When cross-site POST cookies are required, `SameSite=None; Secure` may be used per organizational threat model/cookie policy with mandatory HTTPS; test CSRF on all other endpoints.
4. Consider an appropriate repository/flow if you do not want to relax `SameSite` app-wide; **never drop request correlation** to bypass the error.
5. Never disable CSRF across all app endpoints just because the ACS must receive a form POST from the IdP; rely on the framework's SAML CSRF handling for the callback per profile.

**A session cookie appearing before login is normal** when the SP stores `AuthnRequest`. The test criterion is the post-authentication `SecurityContext` and prior unauthenticated state—not simply "whether a cookie exists."

## 7. Step 4 – IdP Authenticates and Issues SAMLResponse

A sandbox IdP with matching metadata and SP registration validates the `AuthnRequest`, authenticates the user per IdP policy, and posts a `SAMLResponse` to the ACS. The SP verifies **the message and identity** before creating a session.

### 7.1. Sample Response for Structural Reading (Not for Authentication)

```xml
<samlp:Response
    xmlns:samlp="urn:oasis:names:tc:SAML:2.0:protocol"
    xmlns:saml="urn:oasis:names:tc:SAML:2.0:assertion"
    ID="_resp_456"
    Version="2.0"
    IssueInstant="2026-11-07T03:00:10Z"
    Destination="https://portal.example.test/login/saml2/sso/corp"
    InResponseTo="_request_123">
  <saml:Issuer>https://idp.example.test/metadata</saml:Issuer>
  <samlp:Status>
    <samlp:StatusCode Value="urn:oasis:names:tc:SAML:2.0:status:Success"/>
  </samlp:Status>
  <saml:Assertion ID="_assertion_789"
                  Version="2.0"
                  IssueInstant="2026-11-07T03:00:10Z">
    <saml:Issuer>https://idp.example.test/metadata</saml:Issuer>
    <saml:Subject>
      <saml:NameID>user-17</saml:NameID>
      <saml:SubjectConfirmation
          Method="urn:oasis:names:tc:SAML:2.0:cm:bearer">
        <saml:SubjectConfirmationData
            Recipient="https://portal.example.test/login/saml2/sso/corp"
            InResponseTo="_request_123"
            NotOnOrAfter="2026-11-07T03:05:10Z"/>
      </saml:SubjectConfirmation>
    </saml:Subject>
    <saml:Conditions NotBefore="2026-11-07T02:59:10Z"
                     NotOnOrAfter="2026-11-07T03:05:10Z">
      <saml:AudienceRestriction>
        <saml:Audience>https://portal.example.test/saml/sp</saml:Audience>
      </saml:AudienceRestriction>
    </saml:Conditions>
    <!-- AuthnStatement and XML Signature intentionally omitted. -->
  </saml:Assertion>
</samlp:Response>
```

**Important:** the XML above is **not a valid `SAMLResponse` for login**: it omits `AuthnStatement`/signature and other profile elements. Never use this string as a PASS fixture. A PASS fixture must be generated by the sandbox IdP and **signed with the test private key**, while the SP trusts only the test public certificate from registration.

### 7.2. SAMLResponse Checks at the ACS

| Check | Expected PASS | Negative test |
| --- | --- | --- |
| HTTP binding/endpoint | `POST` to exact ACS with form field `SAMLResponse` | POST to unregistered path |
| Encoding/parser | Valid Base64/XML, parser hardened against XXE/DTD | Malformed Base64/XML, entity expansion |
| SAML Version/Status | 2.0 and success per profile | Unsupported version / Status != Success |
| Message signature/trust | Response or assertion signed **with valid structure/profile** by trusted IdP key | Strip signature, mutate bytes, forged key |
| Issuer | Matches trusted IdP entityID | Response from another issuer |
| Destination | Matches public ACS | Destination pointing to another host/path |
| AudienceRestriction | Matches SP EntityID | Assertion issued for another SP |
| SubjectConfirmation | Bearer; `Recipient`/`NotOnOrAfter`/`InResponseTo` match | Wrong recipient, expired |
| `InResponseTo` | Matches pending `AuthnRequest` and right browser/session | Mismatch/unrequested response |
| Time | `NotBefore`/`NotOnOrAfter`, optional small clock skew | Future/expired assertion |
| Replay | Unused Response/Assertion IDs, one-time response handling | Re-POST duplicate message |
| `AuthnStatement` | Valid subject authentication per profile | Missing/wrong assurance |
| NameID/attributes | Subject type/namespace and mapping policy match | Empty email/NameID or different tenant |
| Signature wrapping | App consumes **exact signed assertion** | Signed benign assertion + unsigned attacker assertion |
| `EncryptedAssertion` if used | Valid SP decryption credential, valid signature | Wrong decryption key / altered ciphertext |
| Certificate rotation | Trust set matches approved IdP metadata | Untrusted cert or expired rotation window |

**Never assert `StatusCode=Success` alone**, as a sender's Status can be forged without proper message signature/trust. **Never check SAML XML with regex alone**; use a SAML/OpenSAML library that enforces XML Signature Reference validation and signature-wrapping defenses.

### 7.3. Signatures May Sit on Response or Assertion

Spring Security 7.x (OpenSAML5 integration per docs) validates signed SAML Responses or assertions according to profile and `RelyingPartyRegistration`. **Not every IdP is required to sign both** if the contract allows signing on either the Response or Assertion appropriately. However:
- Never accept an unsigned message/assertion unprotected by a valid signature per profile.
- If the Response is signed, an inner assertion is trusted only when genuinely covered by the signature and safely parsed.
- If the Assertion is signed, never read user data from an unsigned sibling/element.
- Verify key trust from metadata/config, never treating an arbitrary embedded certificate inside the message as authoritative.
- If enterprise policy requires both Response and Assertion signed, write tests enforcing stricter policy than defaults.
- Reject broken certificates/algorithms and SHA-1 signing that fail security baselines.

### 7.4. Clock Skew Is Not a Way to Bypass Validation

Spring/OpenSAML support configuring clock skew on validators/providers. Skew must stay small per security policy—never set it to "1 day" just to keep expired fixtures working. Test:
- Assertion with `NotBefore` in the future beyond skew → reject.
- Assertion past `NotOnOrAfter` → reject.
- IdP/SP clock drift within approved tolerance → may pass.
- VM/container NTP sync; display timezone is not clock drift.

With old static fixtures, **do not** freeze timestamps at `2026-11-07` and expect tests to PASS forever. The sandbox IdP should issue assertions near current time; unit tests for time validation can use an injected/mock clock or fixture generator, kept distinct from real E2E tests.

## 8. Step 5 – From Assertion to Spring Authentication

When the ACS is processed by Spring Security:

```text
POST /login/saml2/sso/corp
  ↓
Saml2WebSsoAuthenticationFilter
  ↓
Saml2AuthenticationTokenConverter
  ↓
AuthenticationManager
  ↓
OpenSaml5AuthenticationProvider (in Spring Security 7.x)
  ↓
Verify SAMLResponse/Assertion, decrypt if needed,
check issuer/audience/destination/conditions...
  ↓
Saml2Authentication with Saml2AuthenticatedPrincipal
  ↓
Application account mapping, authorities
  ↓
SecurityContext and session persistence
```

Spring Security docs describe `Saml2AuthenticatedPrincipal` for accessing `NameID` and `attributes`; some versions grant `ROLE_USER` via the default provider converter. **`ROLE_USER` does not imply `ROLE_ADMIN`**; if business logic needs roles, the app must map groups/tenants from a trusted issuer and check resource permissions.

### 8.1. Controller Reading the Authenticated Principal

```java
package com.example.samltest;

import java.util.Map;
import org.springframework.security.core.annotation.AuthenticationPrincipal;
import org.springframework.security.saml2.provider.service.authentication
        .Saml2AuthenticatedPrincipal;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class WhoAmIController {
    @GetMapping("/whoami")
    public Map<String, String> whoami(
            @AuthenticationPrincipal Saml2AuthenticatedPrincipal principal) {
        return Map.of("name", principal.getName(),
                "auth", "saml2");
    }
}
```

**Controller snippet inside a Spring Boot app**, not standalone JDK runnable. Use in sandbox or production only when business policy permits returning the principal name; never expose all SAML attributes/tokens as they may contain PII/group details. When mapping `user-17` to `U-100`, use the verified `IdP issuer + stable NameID/attribute contract` and application user repository; never map solely by unverified email.

### 8.2. Sessions Are Separate Evidence That Must Be Tested

After ACS succeeds, verify:
1. Spring `Authentication` has the SAML authenticated type/semantics and principal matching the test IdP.
2. The request's `SecurityContext` was persisted via `SecurityContextRepository`/session strategy per framework version.
3. The browser holds the session cookie with `Secure`, `HttpOnly`, `SameSite` per web threat model, with exact domain/path/expiration.
4. A **new request** `GET /whoami` or `GET /reports` **does not resend `SAMLResponse`**, carrying only the valid session cookie.
5. The new request resolves the right authenticated principal without triggering an IdP redirect loop.
6. A separate browser without that cookie/same-origin session does not inherit this login.
7. Session fixation protection is active: the session ID may rotate per Spring's session strategy upon successful authentication. Never hard-code that a cookie may only appear for the first time **after** login.
8. An invalidated/expired session loses `Authentication`; protected resources become inaccessible.
9. If the app is stateless by custom config, **do not assume** an `HttpSession` exists as outlined here; adjust test design to match architecture or fix config.
10. If production uses Spring Session Redis/JDBC, test across pods/instances rather than a single JVM.

**True PASS indicator:** the SAML Response is verified and a subsequent independent request retrieves the authenticated principal **for the same internal user/tenant**, while an anonymous/fresh browser is blocked.

### 8.3. Session Fixation and Authentication Source

Spring Security enforces session fixation protection via session authentication strategies. In Spring Security 6/7, authentication mechanisms invoke the strategy directly (do not configure based on Spring Security 5 `SessionManagementFilter` assumptions). Tests should compare **pre-login and post-login** state:
- If an `HttpSession` already existed to store `AuthnRequest`, its session ID **may be rotated** per policy; changing to a new session ID does not break `AuthnRequest` correlation because auth has already completed.
- A pre-login session fixed by an attacker must never become the shared authenticated session.
- Post-login requests must use the new/current cookie, not the invalidated cookie.
- User logout or idle timeout must clear `SecurityContext`.
- Never treat the presence of an IdP SSO cookie as proof the app still holds a local session, or vice versa.

## 9. Step 6 – Returning to the Protected Resource and Checking Business Authorization

Once the SP creates `Authentication`, the app may redirect to the saved request `/reports` or a local success URL. Verify:
- Redirects go only to **safe internal routes**, never using raw `RelayState` as `Location`.
- `GET /reports` uses the authenticated session and returns data permitted for the test user; if the user lacks a role/resource permission, return `403`, **even when SAML login is valid**.
- Never create an internal admin role solely because the IdP sent `groups=["admin"]` without a mapping policy.
- If IdP B emits the same NameID as IdP A, identity keys must include the issuer namespace.
- When the app is multi-tenant, SAML attributes must map to tenant authority; never let tenant B read A's data.
- Second and third requests prove session persistence rather than a transient `SecurityContextHolder` living only during the ACS request.
- If the app provisions local accounts JIT, test account status/uniqueness and prevent auto-merging by email.

### 9.1. Verifying `Authentication` and Business Session

| Layer | Good assertion example | Unsafe/insufficient assertion |
| --- | --- | --- |
| Protocol | Signature + issuer + audience + `InResponseTo` + replay valid | `SAMLResponse` contains `Success` |
| Identity | `issuer + persistent subject` maps to `U-100` | Email match only |
| Spring Authentication | Right principal and authorities, `authenticated` is true | Controller sets `isLoggedIn=true` itself |
| Session | Subsequent request with same cookie is authenticated | Only seeing `Set-Cookie` |
| Authorization | `U-100` has exact report read permission | `ROLE_USER` automatically views all reports |
| Logout | Invalidated session forces subsequent request to re-auth | Browser displays "signed out" |
| Multi-user | A and B maintain identity isolation | Same browser tab caches username |

## 10. Structuring a Test Suite with Real Evidentiary Power

A trustworthy test suite needs at least four layers:

### Layer A – Static/Config Tests

- SP entityId, ACS, IdP entityId, SSO URL, bindings, credentials/metadata.
- Application public URL and proxy forwarded headers.
- Certificate/private key/trust rotation per profile; never hard-code production keys.
- User/tenant attribute mapping config and default session policy.
- Startup fails if registration is invalid/missing or trust anchors are absent.
- Custom `AuthnRequest` resolver and request repository exist and operate properly.

### Layer B – Spring MockMvc: Entrypoint/Filter Wiring

- Anonymous `GET /reports` returns no protected data.
- `GET /saml2/authenticate/corp` generates `AuthnRequest` and responds with the right **binding**: 3xx `Location` containing `SAMLRequest` (Redirect) or HTML form POST (POST binding).
- Request is persisted in session/repository.
- Multiple registrations pick only the right IdP with no open redirect.
- SAML ACS is not hijacked by a custom controller bypassing validators.
- Auth success/failure handlers are invoked in the right places.

**Limitation:** MockMvc without an IdP signing fixtures **does not prove** Response signature/subject/session end-to-end. `@WithMockUser`/`with(user(...))` only injects a mock `Authentication` into the request—**it does not simulate SAML Web SSO**.

### Layer C – Protocol-Integrated Tests

- Run a sandbox IdP or test IdP service with a **test signing private key**.
- SP trusts only the registered test IdP signing cert.
- Issue a real `AuthnRequest` over HTTP, IdP parses it, logs in test user, and issues a genuinely signed Response.
- SP validates the Response at the ACS, checking replay/mismatch/expiration/crypto failures.
- Run negative fixtures generated from a dedicated test issuer/key with intentionally invalid fields.
- Verify the provider/error path creates no session when Response is invalid.
- Exercise certificate rotation, signed/unsigned response policies, and encryption if enabled.
- Never bypass the OpenSAML provider with a mock returning an authenticated token to fake E2E.

### Layer D – Browser E2E

- Real browser handles cookies/redirects across IdP HTML login POST and ACS.
- Use a fresh context before login and a separate context to verify isolation.
- Verify `SameSite`, `Secure`, `Domain`, `Path`, reverse proxy, and redirect chains.
- Check subsequent post-login requests resolve the right internal user/roles.
- Logout/session expiration revokes access; distinguish IdP SSO from local session.
- Test headless/full browsers, site isolation, multiple tabs, session renewal, and cluster failover.
- Test IdP downtime, stale metadata, expired certs, and minor time drift in sandbox.
- **Never dump `SAMLResponse`/tokens/cookies into CI artifacts**; redact Playwright/browser logs.

**Definition of Done:** evidence from Layers B + C + D for the happy path; protocol/session/authorization negative tests executed, never relying on mock users as E2E.

## 11. MockMvc: Testing AuthnRequest Generation (Not Faking E2E)

A JUnit/Spring Boot test using MockMvc to test the Start SAML endpoint, assuming **test registration `corp` is configured with Redirect binding**:

```java
package com.example.samltest;

import static org.junit.jupiter.api.Assertions.assertTrue;
import static org.springframework.test.web.servlet.request
        .MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result
        .MockMvcResultMatchers.header;
import static org.springframework.test.web.servlet.result
        .MockMvcResultMatchers.status;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet
        .AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.HttpHeaders;
import org.springframework.test.web.servlet.MockMvc;

@SpringBootTest
@AutoConfigureMockMvc
class SamlAuthnRequestStartTest {
    @Autowired
    MockMvc mvc;

    @Test
    void startsSamlWithRedirectBinding() throws Exception {
        var result = mvc.perform(
                    get("/saml2/authenticate/corp").secure(true))
                .andExpect(status().is3xxRedirection())
                .andExpect(header().exists(HttpHeaders.LOCATION))
                .andReturn();

        String location =
                result.getResponse().getHeader(HttpHeaders.LOCATION);
        assertTrue(location.startsWith(
                "https://idp.example.test/sso"));
        assertTrue(location.contains("SAMLRequest="));
    }
}
```

**Limitations and version note:** this code is a test snippet inside a Spring Boot project with real registration, test dependencies, and HTTP Redirect binding. If Boot 4 or test plugins move auto-configuration test annotation packages, adjust the `AutoConfigureMockMvc` import per BOM. If the IdP requires signed `AuthnRequest` payloads, the SP needs signing credentials in test; if using POST binding, assert the HTML form instead of `3xx Location`. Do not conclude the signature is valid just because `Location` contains `SAMLRequest=`: decode the XML, verify fields, and test the IdP accepting the signed request separately.

### 11.1. Why Not Assert `redirectedUrl("https://idp...SAMLRequest=<literal>")`?

`AuthnRequest` ID, `IssueInstant`, `RelayState`, and `Signature` change per request. Byte-exact comparison of a dynamic URL is flaky and tempts teams into hard-coding IDs dangerously. Instead:
- Parse the URI: verify IdP SSO origin is allowlisted, exact path matches, and no open redirect exists.
- Parse query parameters with a URL-aware parser.
- Decode `SAMLRequest` according to binding.
- Assert XML structure/Issuer/Destination/ACS/ID/Version.
- Verify the signature when required by policy using the test IdP verifier.
- Correlate the request repository with recorded test ID/`RelayState`.

**Never write regex to validate XML signatures.** Use OpenSAML/a SAML verifier with metadata trust.

### 11.2. MockMvc for ACS: Never Pass an Unsigned `<Response>` as a PASS Case

A useless test:

```java
// ANTI-PATTERN: test bypass, does not prove SAML validation.
mvc.perform(get("/reports").with(
    org.springframework.security.test.web.servlet.request
        .SecurityMockMvcRequestPostProcessors.user("user-17")))
    .andExpect(status().isOk());
```

This test only proves the endpoint handles a **mock authenticated user**; it does not run the IdP, `AuthnRequest`, ACS, signature verification, `InResponseTo`, or session persistence.

Similarly, calling:

```text
POST /login/saml2/sso/corp
SAMLResponse=base64("<Response Status=Success.../>")
```

is not a happy-path fixture. You must use a **real signed response** from the test IdP bound to a pending `AuthnRequest` and test browser session. For invalid fixtures, failure status may redirect to login or an error handler rather than returning HTTP 401: assert **no `Authentication` created / no protected data returned**, rather than hard-coding HTTP 401 for every failure.

## 12. Browser-Executed E2E Test Script

Below is a **test plan** implementable with Playwright/Selenium or manually in a sandbox, without production credentials.

### 12.1. Preparation

- Start the test IdP realm; user `user-17` holds groups/report permissions per policy.
- SP runs on public HTTPS `https://portal.example.test`, with test EntityID/ACS registered.
- Fresh browser context A, clean of cookies/app sessions.
- Fresh browser context B, completely isolated from A.
- Enable network tracing **with redaction** of `SAMLRequest`/`SAMLResponse`/SessionID and `Authorization`.
- Synchronize clocks; IdP signing certificate and SP verification key match.
- Enable audit event IDs: request started / response verified / login succeeded / session persisted / authorization decision.

### 12.2. Steps and Expected Results

**Step 1 — Anonymous access:** A opens `/reports`. Expect no protected content returned. If a login picker appears, choose `corp`. **No authenticated app user exists yet**.

**Step 2 — Start AuthnRequest:** A visits `/saml2/authenticate/corp`. Expect Redirect or POST to a valid IdP endpoint. Capture request ID/`RelayState` into **safe test memory** for correlation without printing raw credentials.

**Step 3 — Verify request contract:** Decode `SAMLRequest`. Check `Issuer=SP EntityID`, `Destination=IdP SSO`, `AssertionConsumerServiceURL`/index match, `Version=2.0`, unique ID, recent timestamp, and request signature if required by the IdP.

**Step 4 — IdP login:** A logs in as the test user at the IdP. If the user already has an IdP SSO session, the IdP may skip the password prompt; the test must still verify the response subject/assurance. To test fresh login, use an isolated IdP browser context and `ForceAuthn` policy.

**Step 5 — ACS POST:** Browser A posts `SAMLResponse` to `/login/saml2/sso/corp` with `RelayState`. Expect **matching browser cookie/session** so the SP can look up the pending request. If `SameSite` blocks the cookie, the test must fail on correlation rather than falling back to unsolicited login.

**Step 6 — SAML validation:** SP verifies the signed assertion/response. Audit logs omit the token yet confirm trusted IdP, Request ID correlation, accepted subject, and exact ACS/audience.

**Step 7 — App identity:** Spring principal is `Saml2Authentication`; the app resolver maps `(IdP, NameID) → U-100`. Verify user is `ACTIVE` with correct tenant/roles; no email auto-merge.

**Step 8 — Session:** Browser A receives/updates its session cookie after authentication. Open `GET /whoami`/`/reports` on a new request. Expect authenticated user `U-100` without returning to the IdP. If session fixation protection rotates the session ID, the browser uses the new cookie.

**Step 9 — Isolation:** Browser B opens `/reports` without A's cookies. Expect login initiation/denial and zero access to `U-100`'s resources. Never reuse the same test `BrowserContext` when proving isolation.

**Step 10 — Authorization:** A views an authorized report. Try `/admin` or another tenant's report; expect 403/deny—**never equate SAML login success with universal authorization**.

**Step 11 — Replay:** Take a **previously used** `SAMLResponse` from the internal test harness (not public logs) and re-POST it in the same or a new session inside the test environment. Expect failure / no new authenticated session; log event `REPLAY_DETECTED` if emitted.

**Step 12 — Logout:** A POSTs logout per CSRF policy; session is invalidated. Afterward, `/reports` no longer uses the local session. If the browser's IdP SSO session remains active, reopening may immediately SSO again; tests distinguish **local logout vs. IdP SLO**.

### 12.3. Artifacts to Retain After Testing

Retain only:
- Hashed/redacted correlation IDs.
- Test registration name and issuer config ID (not secrets).
- Verified request ID/response ID as hashed audit identifiers if needed.
- HTTP statuses, redirect origins, and cookie attribute flags (not raw cookie values).
- Timings: request start, ACS success, session established, protected resource.
- Assertion validation pass/fail reason codes **without exposing NameID/PII**.
- Login/success/logout UI screenshots with personal data masked.
- Versions of Spring Security/OpenSAML/test IdP + public certificate fingerprint.

**Never retain** raw `SAMLResponse` payloads, private keys, session cookies, service secrets, or full browser HARs containing credentials outside controlled secret storage.

## 13. Java 17 Runnable Demo: Checking Correlation and Sessions

A real SAML E2E test must use OpenSAML + signed fixtures + an IdP. However, before connecting an IdP, you can learn **the core invariants** via a standalone Java 17 program:

1. A response is accepted only when a matching pending `InResponseTo` request exists.
2. `RelayState` and the original browser session must match.
3. Issuer, Audience, and Destination must match.
4. Signature validity is a prerequisite (modeled via a boolean test input—**no XMLDSig verification**).
5. The response is unexpired and its ID has not already been consumed (replay).
6. Only after passing do we establish an authenticated app session so subsequent requests can read identity.

File `SamlSpInitiatedFlowDemo.java`:

```java
import java.time.Instant;
import java.util.HashMap;
import java.util.HashSet;
import java.util.Map;
import java.util.Set;

public class SamlSpInitiatedFlowDemo {
    static final String ISSUER = "https://idp.example.test/metadata";
    static final String AUDIENCE = "https://portal.example.test/saml/sp";
    static final String ACS =
            "https://portal.example.test/login/saml2/sso/corp";

    record Pending(
            String requestId, String relayState,
            String browserSession, Instant expiresAt) {}

    record Response(
            String responseId, String inResponseTo,
            String relayState, String issuer,
            String audience, String destination,
            String subject, Instant notOnOrAfter,
            boolean signatureVerified) {}

    static final class MiniServiceProvider {
        private final Map<String, Pending> pending = new HashMap<>();
        private final Set<String> usedResponseIds = new HashSet<>();
        private final Map<String, String> authenticated = new HashMap<>();

        void begin(Pending request) {
            pending.put(request.requestId(), request);
        }

        boolean accept(
                String browserSession,
                Response response,
                Instant now) {
            if (response == null || !response.signatureVerified()) {
                return false;
            }
            Pending request = pending.get(response.inResponseTo());
            if (request == null
                    || usedResponseIds.contains(response.responseId())
                    || !request.browserSession().equals(browserSession)
                    || !request.relayState().equals(response.relayState())
                    || !ISSUER.equals(response.issuer())
                    || !AUDIENCE.equals(response.audience())
                    || !ACS.equals(response.destination())
                    || response.subject() == null
                    || response.subject().isBlank()
                    || !now.isBefore(request.expiresAt())
                    || !now.isBefore(response.notOnOrAfter())) {
                return false;
            }
            pending.remove(response.inResponseTo());
            usedResponseIds.add(response.responseId());
            authenticated.put(browserSession, response.subject());
            return true;
        }

        String principal(String browserSession) {
            return authenticated.get(browserSession);
        }
    }

    static Response validResponse(String id, Pending request) {
        return new Response(
                id, request.requestId(), request.relayState(),
                ISSUER, AUDIENCE, ACS, "user-17",
                Instant.parse("2026-11-07T03:05:00Z"), true);
    }

    public static void main(String[] args) {
        MiniServiceProvider sp = new MiniServiceProvider();
        Instant now = Instant.parse("2026-11-07T03:00:00Z");

        Pending first = new Pending(
                "_request_A", "opaque-relay-A", "session-A",
                Instant.parse("2026-11-07T03:04:00Z"));
        sp.begin(first);
        Response signed = validResponse("_response_1", first);

        System.out.println("Anonymous before SSO: "
                + (sp.principal("session-A") == null));
        System.out.println("Valid response accepted: "
                + sp.accept("session-A", signed, now));
        System.out.println("Application principal: "
                + sp.principal("session-A"));
        System.out.println("Replay rejected: "
                + !sp.accept("session-A", signed, now));
        System.out.println("Another browser stays anonymous: "
                + (sp.principal("session-B") == null));

        Pending second = new Pending(
                "_request_B", "opaque-relay-B", "session-B",
                Instant.parse("2026-11-07T03:04:00Z"));
        sp.begin(second);
        Response secondResponse = validResponse("_response_2", second);

        System.out.println("Wrong browser rejected: "
                + !sp.accept("session-A", secondResponse, now));

        Response wrongAudience = new Response(
                "_response_3", second.requestId(),
                second.relayState(), ISSUER,
                "https://other-sp.example.test", ACS,
                "user-17",
                Instant.parse("2026-11-07T03:05:00Z"), true);
        System.out.println("Wrong audience rejected: "
                + !sp.accept("session-B", wrongAudience, now));

        System.out.println("Correct browser accepted: "
                + sp.accept("session-B", secondResponse, now));
        System.out.println("Session-B principal: "
                + sp.principal("session-B"));

        Pending third = new Pending(
                "_request_C", "opaque-relay-C", "session-C",
                Instant.parse("2026-11-07T02:59:59Z"));
        sp.begin(third);
        System.out.println("Expired pending request rejected: "
                + !sp.accept("session-C",
                        validResponse("_response_4", third), now));
    }
}
```

Run:

```bash
javac SamlSpInitiatedFlowDemo.java
java SamlSpInitiatedFlowDemo
```

**Exact stdout:**

```text
Anonymous before SSO: true
Valid response accepted: true
Application principal: user-17
Replay rejected: true
Another browser stays anonymous: true
Wrong browser rejected: true
Wrong audience rejected: true
Correct browser accepted: true
Session-B principal: user-17
Expired pending request rejected: true
```

**Important limitations:**
- `signatureVerified` is an assumed boolean with **no XMLDSig cryptography**. A real application must never accept such a boolean from a browser/JSON payload to make auth decisions.
- The program does not generate SAML XML, check full Issuer/`AttributeStatement`/`SubjectConfirmation`/`NameID` formats, validate certificates/trust, defend against XML signature wrapping, or perform SAML/HTTP bindings.
- `HashMap`/`HashSet` are not thread-safe and lack multi-node/durable TTL/replay stores. Production requires sessions/repositories/caches with locking or atomic operations per threat model.
- `session-A` is a simulated string; real HTTP sessions involve cookies, `SameSite`, session fixation rotation, CSRF, and `SecurityContextRepository`.
- Time is fixed so stdout is deterministic. Never use this timestamp as a PASS SAML fixture in production.
- Its sole purpose is demonstrating "**matching `AuthnRequest` + verified Response ⇒ authenticated app session**" and basic negative assertions. Real protocol testing must use signed IdP Responses per `RelyingPartyRegistration`.
- An authenticated session in the demo only holds `user-17`; real application accounts require tenant/role mapping and authorization.

## 14. Detailed Negative Test Matrix

| Case | Input/action | Outcome to prove |
| --- | --- | --- |
| Anonymous protected route | GET `/reports` without session | Returns no user data; initiates login |
| Correct `AuthnRequest` | SP selects `corp` | Issuer, Destination, ACS, unique ID valid |
| Wrong IdP registration | URL `corp` but partner IdP | Does not send request to untrusted IdP |
| Malformed `AuthnRequest` | Bad Base64/Deflate/XML | Test IdP rejects |
| Missing `AuthnRequest` ID | XML lacks ID | Treated as invalid flow |
| Duplicated `AuthnRequest` ID | Send two requests with same ID | Detected; does not overwrite/hijack state |
| Signed request required | IdP requires signature, SP sends unsigned | Reject |
| Wrong SP signing credential | Signature with unregistered RSA key | IdP rejects |
| Wrong Destination SSO | Wrong IdP address | IdP rejects / SP refuses to send |
| Wrong ACS | Response sent to unregistered host/path | SP rejects |
| Wrong SP EntityID | Mismatched Audience | Reject |
| External `RelayState` URL | `https://evil.example` | Never redirect to raw value |
| Tampered `RelayState` | Non-existent opaque ID | Reject / correlation fails |
| Cross-session `RelayState` | Browser A starts, B POSTs | Reject |
| Missing session cookie | ACS POST without original session | Fail closed |
| `SameSite` blocks cookie | Cross-site POST | Detects missing cookie; never bypasses correlation |
| Expired pending request | Wait past TTL | Reject / restart flow |
| Two tabs | Start A/B and deliver responses out of order | No cross-mapping |
| Cross-pod | Start on pod1, callback on pod2 | PASS if shared state works; deny if correlation lost |
| Wrong `InResponseTo` | Response answers a different request | Reject |
| Missing `InResponseTo` on SP flow | Unsolicited response | Reject under SP-initiated-only policy |
| Wrong response issuer | IdP B metadata, expected A | Reject |
| Wrong assertion issuer | Nested issuer mismatch | Reject |
| Tampered signed XML | Edit NameID/attribute after signing | Reject signature |
| Unsigned response/assertion | No signature protecting assertion | Reject |
| Unknown signing certificate | Token signed with attacker key | Reject |
| Weak signature algorithm | Disallowed SHA-1 per policy | Reject |
| XML signature wrapping | Attacker assertion alongside signed assertion | Reject |
| External entities/DTD | XXE payload in XML | Safely reject |
| Empty/malformed Base64 | Unparseable `SAMLResponse` | Not authenticated |
| SAML Status failure | Responder/AuthnFailed/NoAuthnContext | No login |
| Future `NotBefore` | Assertion not yet valid | Reject outside skew |
| Expired `NotOnOrAfter` | Expired assertion | Reject |
| Wrong `SubjectConfirmation` Recipient | Different ACS | Reject |
| Wrong `SubjectConfirmation` `InResponseTo` | Does not match request | Reject |
| Missing `AuthnStatement` | Assertion lacks profile-required authn | Reject |
| Replay same Response ID | Re-POST after success | Reject |
| Replay same Assertion ID | Re-sign another response wrapping reused assertion | Reject per replay policy |
| Wrong audience | Assertion meant for SP B sent to SP A | Reject |
| `EncryptedAssertion` wrong key | SP cannot decrypt | Reject |
| Certificate rotation | IdP rotates cert per approved metadata | PASS during overlap, FAIL for untrusted cert |
| Signature downgrade | Verification disabled in test | Test suite must FAIL |
| SP clock skew | KDC/IdP skewed 10 minutes | Reject if outside tolerance |
| Inactive user | IdP auth succeeds, local account disabled | App rejects/denies |
| Same email different issuer | IdP A/B share email | Never auto-merge user |
| Group claim `admin` from untrusted IdP | Ordinary user | Does not grant `ROLE_ADMIN` |
| User lacks report permission | SAML login succeeds | `403` at resource |
| Missing `SecurityContext` persistence | ACS request passes, GET `/reports` redirects to login | Integration test FAILS |
| Session fixation | Attacker-known pre-login session ID | Cannot hijack post-login session |
| Session isolation | Browser B lacks A's cookie | B cannot access A's data |
| CSRF bypass elsewhere | App CSRF disabled for SAML ACS POST | Security test FAILS |
| Local logout | Valid POST logout | Session loses auth; protected route demands login |
| Remaining IdP SSO session | After local logout | Do not confuse SSO re-login with failed logout |
| Post-login open redirect | `RelayState`/next is external URL | `Location` must stay on safe local origin |
| Proxy header spoof | `X-Forwarded-Host: attacker` | ACS/base URL must not switch to attacker |
| High-volume malicious callbacks | Random `SAMLResponse` spam | Resource limits, no auth, safe observability |
| Untrusted log exposure | Trace contains `SAMLResponse`/cookie/private key | Security audit FAILS |

### 14.1. SAML Protocol Test ≠ Business E2E Test

If a user lacks permission to view `/reports` while the `SAMLResponse` is valid, you can observe:
- Authentication PASS;
- Session PASS;
- Business authorization FAIL with 403.

That is **not automatically a SAML failure**. To evaluate from `AuthnRequest` to session, use a `/whoami` route guarded by `authenticated()` alongside separate business routes checking roles/tenants. Report results by layer so operations teams know exactly where to fix issues.

### 14.2. Response Failures Are Not Always HTTP 401

Spring Security failure handlers may redirect to login/error or return 4xx depending on custom configuration. A test should not fail merely because an invalid SAML payload returns 302 instead of 401; instead assert:
- Invalid Response **creates no `Authentication`**.
- No authenticated `SecurityContext` is persisted.
- No protected content is returned.
- Errors are logged safely without leaking tokens.
- Never fall back to another IdP or accept an unsigned assertion on "retry."

## 15. Multi-IdP, Multi-Tenant, and Registration Resolution

A system with `corp` and `partner` registrations can issue distinct `AuthnRequest` flows:

```text
/saml2/authenticate/corp
/saml2/authenticate/partner
```

Tests must separate:
- `corp` uses SP EntityID/ACS per contract with IdP `corp`, while `partner` uses IdP `partner`; even if sharing an SP EntityID, trust mappings must still distinguish issuers.
- `RelyingPartyRegistration` is resolved via trusted pending request/`registrationId`/Issuer, never treating an unverified raw `Issuer` as grounds to accept a cert outside the trust store.
- A Response from IdP B cannot fulfill a pending request for IdP A.
- NameID `user-17` at two IdPs does not represent the same app user by default; identity namespaces must include the IdP authority.
- Tenant-specific ACS/audience/roles are tested; never "mix tenants" through `RelayState`.
- Multi-tab flows can cause overlapping request states; test exact repository semantics for your version.
- Even when an IdP signs properly, app business authorization can still deny based on tenant.

### 15.1. Can One Registration Have Multiple ACS Endpoints/Mappings?

SAML metadata can advertise multiple ACS endpoints/indexes and bindings. A Spring app may use custom `RelyingPartyRegistration` or routing logic. Tests must confirm:
- Which ACS URL/index the request selects.
- Which URL the IdP sends the Response to.
- `Destination`/`Recipient` match the exact accepted endpoint.
- Tenant A cannot submit a Response to tenant B's ACS merely because both share a domain.
- Reverse proxies do not alter public `baseUrl`/port/`Host` inside the response.
- Bindings are requested/enforced per metadata without falling back to unregistered URLs.

## 16. Handling Failures by Stage, Without Weakening Security

| Symptom | Common failure layer | Priority diagnosis |
| --- | --- | --- |
| Anonymous `/reports` returns 200 without login | Wrong authorization/filter chain | `SecurityFilterChain` and matchers |
| `/saml2/authenticate/corp` missing | Wrong registration/login entry point | Registration ID, login page/picker |
| Does not redirect to IdP | Missing signing key/metadata/SSO endpoint | SAML request filter, IdP registration |
| IdP says "unknown SP" | Wrong SP EntityID | IdP-registered SP EntityID/Issuer |
| IdP says "invalid ACS" | Wrong public callback URL | ACS URL/index, reverse proxy |
| IdP says "invalid signature" | Wrong SP request signing key/algorithm | Trust/cert, Redirect binding bytes |
| `AuthnRequest` has malformed `SAMLRequest` | Wrong binding decode | URL decode + Base64 + raw Deflate |
| `SAMLResponse` hits ACS but login fails | Signature/Issuer/Audience/Time/Request mapping | Redacted provider diagnostics |
| `InResponseTo` mismatch | Lost request repository/session or wrong flow | Pending request ID, session correlation |
| Missing `RelayState` | IdP did not echo or callback mismatch | Binding/IdP config, opaque state |
| Session cookie missing on ACS POST | `SameSite` cross-site POST, domain/path, TLS | Browser network trace cookie flags |
| Request hits session on another node | Non-shared `HttpSession`/repository | Spring Session/shared store/ingress routing |
| Invalid IdP cert | Metadata/rotation trust set | Cert fingerprint and test lifecycle |
| Time expired or not yet valid | NTP drift, stale fixture | Issuer/recipient windows, test clock |
| POST ACS 403 CSRF | Missing CSRF exemption for SAML endpoint | SAML filter config; do not disable all CSRF |
| Authentication PASS, GET `/reports` redirects to login | `SecurityContext` not persisted, cookie not set/sent | Session repository, cookie, session strategy |
| Authentication PASS, GET `/reports` 403 | Business RBAC/tenant mismatch | App user mapping, authorities |
| Endless login loop | Cookie/`SameSite`, success handler, or saved request | Redirect chain, session persistence |
| Wrong user after login | NameID/issuer mapping, parallel tabs, fixation | Identity namespace, original browser binding |
| Browser B accesses user A | Session isolation/cookie leak | Test contexts, Session IDs |
| Logout only clears local session | IdP SSO remains active | Design SAML SLO separately; not a default bug |
| Fails only behind load balancer | Proxy Host/Proto, pod configs/keys | Public base URL, forwarded trust, shared state |
| Passes in MockMvc but fails in browser | Mock lacks cookies/cross-site/IdP | E2E browser network trace |
| Cert rotation breaks tests | Key overlap/metadata sync | Pinning/rollover/expiry management |

**Never "fix" by** disabling signature validation, dropping `InResponseTo`, accepting arbitrary unsolicited assertions, raising clock skew to several hours, enabling `permitAll()` app-wide, disabling CSRF globally, or setting `RelayState` to a raw URL. Those merely turn integration bugs into SSO vulnerabilities.

## 17. QA Runbook for a Complete Test Run

**Before running**
1. Record Java/Spring Security/Boot/OpenSAML/test IdP versions and trust metadata fingerprint.
2. Confirm exact SP EntityID, IdP EntityID, registered ACS URL, and bindings per contract.
3. Enable HTTPS, verify public host/forwarded headers, and prepare test user/roles/tenant.
4. Prepare isolated browser contexts, secret-safe capture, and current test IdP signing key.
5. Ensure clocks/NTP and session/cache settings support cross-site POST.
6. Define expected local success route, protected route, and logout policy.

**Execution**
1. Anonymous GET to protected route → login initiated.
2. `AuthnRequest` generated → check ID, Issuer, Destination, ACS, and Request signature if needed.
3. Pending `AuthnRequest` persisted server-side, bound to session/`RelayState`.
4. Sandbox IdP authenticates test user and issues signed `SAMLResponse`.
5. Browser POSTs ACS with matching session/`RelayState`.
6. SP checks XML signature/trust, issuer, audience, destination, subject/time, and `InResponseTo`.
7. App maps principal → user/tenant/roles; `SecurityContext`/session saved.
8. Browser sends a new request with current cookie; accesses protected resource without hitting IdP again.
9. Fresh browser has no access; unauthorized resources return 403; logout/expiry terminates session.
10. Run matrix negative tests, especially replay, wrong audience, wrong session, unsigned response, wrong signing cert, and open redirect.

**After running**
1. Record PASS/FAIL per stage, never just a single "SSO works" label.
2. Ensure audit logs hold no SAML assertions/tokens/cookies; verify full observability across SP and IdP.
3. Clean up test users/credentials/sensitive fixtures per retention policy.
4. Document any findings around `SameSite`, sessions, certificate rollover, delegated IdP trust, cluster routing, and versions.
5. If code/config changes, re-run full browser E2E—not just MockMvc unit tests.

## 18. Definition of Done and Minimum Evaluation

| Criterion | Passing evidence |
| --- | --- |
| Real SP-initiated | Starts at `/reports` or `/saml2/authenticate/corp`; SP creates `AuthnRequest` |
| Valid Request | Issuer, ID, Destination, ACS, binding, and signing match contract |
| Correlation | `InResponseTo`/`RelayState` match original request/browser session |
| Verified IdP | Accepts only signed Response/Assertion from trusted test IdP cert |
| Valid Conditions | Audience/Recipient/`NotBefore`/`NotOnOrAfter` and replay checks pass |
| Authentication | Spring `Saml2Authentication` created from verified assertion |
| Identity mapping | `Issuer + stable subject` resolves to exact app account/tenant |
| Session persistence | **Subsequent** request in same browser stays authenticated |
| Browser isolation | Separate browser does not share authenticated session |
| Authorization | Permitted on authorized resources only; no implicit admin |
| Logout/expiry | Terminated session forces protected routes to re-authenticate |
| Negative tests | Fake/tampered/replayed/out-of-session responses are rejected |
| Safe diagnostics | No raw `SAMLResponse`/cookies/keys logged |
| Cluster/browser behavior | `SameSite`/ACS POST/shared request store verified |

**The suite achieves "SP-initiated SSO end-to-end" only when handshake, SAML verification, and authenticated application session are all proven.** If you only have `@WithMockUser` tests, only ID Token/JWT tests, or only observe the `AuthnRequest` redirect, record the actual scope as **unit/filter wiring**, not E2E.

## 19. Self-Check Questions

**Q1. How do you prove a flow is SP-initiated SSO rather than IdP-initiated?**  
There must be a prior SP-issued `AuthnRequest` with a saved pending request; the Response carries matching `InResponseTo` and valid browser/session correlation. An unsolicited `SAMLResponse` from the IdP without a pending request does not satisfy SP-initiated criteria.

**Q2. Is a 302 to the IdP enough to mark a test PASS?**  
No. It only proves the endpoint emits a request; it does not prove the IdP signed a Response or that Spring established a session.

**Q3. Can a Response with `Status=Success` and a valid `NameID` but no signature log a user in?**  
Not under a secure profile. The SP must verify signature/trust and conditions via the SAML provider; parsing XML solely for `NameID` is a bypass.

**Q4. Should the same `RelayState` from a different browser be accepted?**  
No. Correlation must bind to the original browser/session and pending request; trusting a shared `RelayState` alone enables login fixation.

**Q5. Why might a successful ACS POST still fail to persist a session?**  
Cross-site POST cookies can be dropped by `SameSite`, the callback may hit a different session, or `SecurityContext` may fail to persist. Verify with a subsequent request using the active cookie.

**Q6. Why can `JSESSIONID` appear before a user logs in?**  
The SP may use `HttpSession` to store `AuthnRequest` and `RelayState`. Session presence ≠ authenticated application session.

**Q7. Does a `@WithMockUser` test run the OpenSAML signature verifier?**  
No. It builds a mock `SecurityContext` for authorization/controller logic only; it is not a protocol integration test.

**Q8. If the assertion is valid but the user gets 403, is that a SAML failure?**  
Not necessarily. Authentication/session may PASS while resource authorization DENIES based on role/tenant.

**Q9. What is the risk of disabling signature verification in tests to get a fake positive response?**  
An unsigned/tampered assertion could impersonate any user, leading to account takeover. Test suites must fail if signature/issuer/audience checks are bypassed.

**Q10. Why test full browsers and clusters instead of only JVM MockMvc?**  
Because browser `SameSite` cookies, cross-site POSTs, reverse proxy public ACS URLs, redirect chains, and cross-node request/session stores are not fully modeled by unit mocks.

## 20. Official References

1. [Spring Security – SAML 2.0 Login Overview](https://docs.spring.io/spring-security/reference/servlet/saml2/login/overview.html): filter chain, `AuthnRequest`, `SAMLResponse`, OpenSAML provider, `RelyingPartyRegistration`, default endpoint patterns.
2. [Spring Security – Producing SAML2 AuthnRequests](https://docs.spring.io/spring-security/reference/servlet/saml2/login/authentication-requests.html): request filter, Redirect/POST, signed requests, `HttpSessionSaml2AuthenticationRequestRepository`, and cache repository/session-fixation warning.
3. [Spring Security – Authenticating SAML2 Responses](https://docs.spring.io/spring-security/reference/servlet/saml2/login/authentication.html): `Saml2AuthenticationTokenConverter`, `OpenSaml5AuthenticationProvider`, Response/Assertion validation, principal mapping, and clock skew.
4. [Spring Security – SAML2 Login](https://docs.spring.io/spring-security/reference/servlet/saml2/login/): SAML Web Browser SSO Profile and sample links.
5. [Spring Security – Spring MVC Test Integration](https://docs.spring.io/spring-security/reference/servlet/test/mockmvc/): MockMvc integration and tests with the Security filter chain.
6. [Spring Security – Running a Test as a User](https://docs.spring.io/spring-security/reference/servlet/test/mockmvc/authentication.html): `@WithMockUser`/mock processors only create fake users and do not replace SAML verification.
7. [Spring Security – Authentication Persistence and Session Management](https://docs.spring.io/spring-security/reference/servlet/authentication/session-management.html): `SecurityContext`/session persistence, Spring Security 6+ session strategy.
8. [OWASP SAML Security Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/SAML_Security_Cheat_Sheet.html): verify issuer/audience/recipient/time, XML signature wrapping/replay, `RelayState`/open redirect.
9. [OASIS SAML 2.0 Core](https://docs.oasis-open.org/security/saml/v2.0/saml-core-2.0-os.pdf): `AuthnRequest`, Response, Assertion, Conditions, `SubjectConfirmation`, and signatures.
10. [OASIS SAML 2.0 Bindings](https://docs.oasis-open.org/security/saml/v2.0/saml-bindings-2.0-os.pdf): HTTP Redirect/POST binding, DEFLATE/Base64, `RelayState`.
11. [OASIS SAML 2.0 Profiles](https://docs.oasis-open.org/security/saml/v2.0/saml-profiles-2.0-os.pdf): Web Browser SSO Profile, SP-initiated login, `InResponseTo`, bearer confirmation.
12. [OWASP Session Management Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Session_Management_Cheat_Sheet.html): cookies, fixation, expiration, and logout.
13. [OWASP Cross-Site Request Forgery Prevention Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Cross-Site_Request_Forgery_Prevention_Cheat_Sheet.html): CSRF handling with form POSTs/cookies.
14. [OWASP SAML Security – Testing considerations](https://cheatsheetseries.owasp.org/cheatsheets/SAML_Security_Cheat_Sheet.html#validate-security-countermeasures): negative assertions, replay, and validation defenses.

**Conclusion:** testing **SP-initiated SSO** goes far beyond a `302` to the IdP or a `SAMLResponse` containing "Success". A complete test must verify **SP-issued `AuthnRequest` → pending request/session/`RelayState` → signed IdP `SAMLResponse` → strict SAML validation and `InResponseTo` → Spring `Authentication` → authenticated session remaining valid on subsequent requests → proper business authorization**. With Spring Security, keep SAML filters/repositories intact, never bypass the OpenSAML verifier, and test browser `SameSite`, clustering, and session fixation in a production-like environment.