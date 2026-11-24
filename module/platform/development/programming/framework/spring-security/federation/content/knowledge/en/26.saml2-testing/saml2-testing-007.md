# Testing Audience, Recipient, Destination, and InResponseTo Mismatches in Spring Security SAML 2.0

## 1. Learning Objectives and Scope

In **SAML 2.0 Web Browser Single Sign-On**, a Service Provider (SP)—or **Relying Party (RP)** in Spring Security—receives a `samlp:Response` carrying one or more `saml:Assertion` elements from an Identity Provider (IdP). Even when the **XML signature verifies with a trusted certificate**, the SP must still confirm **who the response is actually intended for, which endpoint it was sent to, and which `AuthnRequest` it answers**.

Four checks frequently determine the security of a SAML login:

1. **Audience:** `saml:Conditions/saml:AudienceRestriction/saml:Audience` must allow the **configured SP Entity ID**; never substitute an email, `registrationId`, or arbitrary hostname.
2. **Recipient:** `saml:SubjectConfirmationData/@Recipient` on a **valid bearer `SubjectConfirmation`** must point to the **SP's ACS endpoint** per the agreed profile; never consume an assertion intended for another endpoint.
3. **Destination:** `samlp:Response/@Destination` must identify the **target receiving the SAML Response** per binding/profile and deployment policy. For Web Browser SSO ACS, this is typically the **actual public ACS URL**.
4. **`InResponseTo`:** for **SP-initiated SSO**, `Response/@InResponseTo` and `SubjectConfirmationData/@InResponseTo` must match the **saved `AuthnRequest` ID** and belong to the right **browser/login transaction**.

This topic belongs to **SAML2 Testing**. It focuses on **negative/integration security testing**, not on bypassing validators when an IdP sends mismatched values.

After this lesson, you will be able to:

- Pinpoint each field's exact location in XML, distinguishing fields on **Response / Assertion / SubjectConfirmationData**.
- Build an expected-values table from `RelyingPartyRegistration` and the ingress/proxy environment.
- Write tests varying **Audience, Recipient, Destination, Response `InResponseTo`, and Bearer `InResponseTo`** one by one.
- Keep fixtures **validly signed** to prove failures come from **policy validation** rather than broken XML signatures.
- Test edge cases: missing fields, multiple `AudienceRestriction` elements, multiple `SubjectConfirmation` elements, HTTP↔HTTPS, host aliases, port/path differences, cross-tenant SPs, mismatched IDs, different browser sessions, and response replay.
- Use **Spring Security SAML 2.0 / OpenSAML** with default validators, understanding why validators should not be stripped out just to "make SSO work."
- Assert security outcomes: **no `Authentication` created, no stale session/roles masking failures, no unauthorized session created**, regardless of whether the HTTP failure handler returns 401, 302, or 403.
- Run a **standalone Java 17** program modeling binding rules and 24 deterministic test cases, while understanding this model is **not a SAML cryptographic implementation**.

**Testing principle:** *A validly signed SAML Response targeting the wrong audience or wrong transaction must still be rejected.* Never conclude "Audience/Recipient/… checks work" merely by editing signed XML and seeing login fail with **signature invalid**.

## 2. Freezing a Fixed Reference Set for Tests

Example test application:

| Component | Example value | Meaning |
| --- | --- | --- |
| Spring `registrationId` | `corp` | Internal key selecting the relying party config |
| **SP Entity ID** | `https://portal.example.test/saml2/metadata/corp` | Expected **Audience** |
| Public **ACS URL** | `https://portal.example.test/login/saml2/sso/corp` | Expected **Recipient/Destination** when the ACS receives Web Browser SSO POST |
| **IdP Entity ID** | `https://idp.example.test/metadata` | Issuer trusted by the SP |
| Test browser session | `browser-A` | Binds the pending `AuthnRequest` |
| `AuthnRequest` ID | `_req_a` | Exact value generated and saved by the SP |
| Response ID | `resp-_req_a` | Example unique response ID |
| Assertion ID | `assert-_req_a` | Example unique assertion ID |
| Test current time | `2026-01-01T12:00:00Z` | Fixed reference for lifetime tests |
| Bearer expiry | `2026-01-01T12:05:00Z` | Valid `NotOnOrAfter` for baseline |

**These URLs and IDs are synthetic test-environment data**, not real live servers. An SP Entity ID **does not have to be a GET-reachable URL**, even though many products look like metadata URLs. `registrationId=corp` **is neither the SP Entity ID** nor the IdP issuer.

### 2.1. Why Must Expected Values Be Frozen?

If a test creates a bad assertion and simultaneously modifies SP config to see if it logs in, you changed **two variables at once** and failed to test a real binding regression.

Before running:

1. Record the RP/IdP metadata in the test environment.
2. Record the fully resolved `RelyingPartyRegistration.getEntityId()` / equivalent value.
3. Record the resolved `assertionConsumerServiceLocation` including public scheme/host/port/path.
4. Record the trusted **IdP issuer** and the test IdP's signing certificate.
5. Capture request ID `_req_a` from an **actual SP-initiated `AuthnRequest`**.
6. Know which browser/session holds the `AuthnRequest` repository entry.
7. Fix timestamps and clock skew via a clock/test harness where supported.
8. Ensure the baseline fixture is signed by the **test IdP key** whose certificate is **registered in the test RP**, never a production key.

**Test each field by changing one field at a time**, except in tests explicitly designed for multi-field combinations.

## 3. SAML Response and Where Each Field Appears

An abbreviated structure **illustrating XML locations only—unsigned and not a login-capable fixture**:

~~~xml
<samlp:Response
    xmlns:samlp="urn:oasis:names:tc:SAML:2.0:protocol"
    xmlns:saml="urn:oasis:names:tc:SAML:2.0:assertion"
    ID="resp-_req_a"
    Version="2.0"
    IssueInstant="2026-01-01T12:00:00Z"
    Destination="https://portal.example.test/login/saml2/sso/corp"
    InResponseTo="_req_a">
  <saml:Issuer>https://idp.example.test/metadata</saml:Issuer>
  <samlp:Status>
    <samlp:StatusCode
        Value="urn:oasis:names:tc:SAML:2.0:status:Success"/>
  </samlp:Status>

  <saml:Assertion
      ID="assert-_req_a"
      Version="2.0"
      IssueInstant="2026-01-01T12:00:00Z">
    <saml:Issuer>https://idp.example.test/metadata</saml:Issuer>

    <saml:Subject>
      <saml:NameID>alice@example.test</saml:NameID>
      <saml:SubjectConfirmation
          Method="urn:oasis:names:tc:SAML:2.0:cm:bearer">
        <saml:SubjectConfirmationData
            Recipient="https://portal.example.test/login/saml2/sso/corp"
            InResponseTo="_req_a"
            NotOnOrAfter="2026-01-01T12:05:00Z"/>
      </saml:SubjectConfirmation>
    </saml:Subject>

    <saml:Conditions
        NotBefore="2026-01-01T11:59:00Z"
        NotOnOrAfter="2026-01-01T12:05:00Z">
      <saml:AudienceRestriction>
        <saml:Audience>
          https://portal.example.test/saml2/metadata/corp
        </saml:Audience>
      </saml:AudienceRestriction>
    </saml:Conditions>
    <saml:AuthnStatement
        AuthnInstant="2026-01-01T11:59:55Z"/>
  </saml:Assertion>
</samlp:Response>
~~~

Values are chosen for illustration and do not suffice for a valid SAML Response: signature/`KeyInfo`, canonicalization, status/encoding/binding, `AuthnContext`, Subject/Assertion profile constraints, and other fields/formats must still be valid in real fixtures.

**Do not copy this XML, Base64-encode it, and expect login to work.** You need a real test fixture built by an IdP/test signer with valid XMLDSig and a trusted certificate.

### 3.1. Data Hierarchy Diagram

~~~text
Response
  @ID
  @Destination                  -> right ACS endpoint
  @InResponseTo                 -> RP's AuthnRequest ID
  Issuer                        -> right registered IdP
  Status
  Assertion
    @ID
    Issuer                      -> right issuer/profile
    Subject
      NameID
      SubjectConfirmation Method="bearer"
        SubjectConfirmationData
          @Recipient             -> right ACS recipient
          @InResponseTo          -> AuthnRequest ID
          @NotOnOrAfter          -> still valid
    Conditions
      AudienceRestriction
        Audience                 -> right SP Entity ID
    AuthnStatement
~~~

**Response `Destination` and `SubjectConfirmationData` `Recipient` may share the same URL in Web Browser SSO, yet they are two distinct fields with different checks at two different layers.** Tests must mutate each field independently.

## 4. Audience: Which SP Is This Assertion For?

In SAML Core, `AudienceRestriction` is a condition restricting which relying parties may consume the assertion. In the example:

~~~xml
<saml:AudienceRestriction>
  <saml:Audience>
    https://portal.example.test/saml2/metadata/corp
  </saml:Audience>
</saml:AudienceRestriction>
~~~

**The value compared is the configured SP Entity ID**, not:

- `registrationId` such as `corp`;
- the IdP's URL;
- the login page URL;
- an API path like `/reports`;
- the `Recipient`/ACS URL (unless `entityId` happened to be configured equal to ACS);
- a generic hostname;
- the user's email NameID.

### 4.1. Negative Test: Another SP's Audience

A cryptographically valid fixture containing:

~~~xml
<saml:Audience>
  https://other.example.test/saml2/metadata/other
</saml:Audience>
~~~

Expected: the assertion **must not be accepted as an `Authentication`** at Portal, even though issuer and signature are valid.

**Do not alter Audience after signing**; change Audience **before re-signing with the test key** so execution reaches `AudienceRestriction` validation. If edited after signing, the error is usually an invalid signature, failing to prove Audience is checked.

### 4.2. Multiple Audiences in One AudienceRestriction

SAML Core allows multiple `Audience` elements inside a single restriction. Standard semantics: **at least one matching `Audience`** within **one** `AudienceRestriction`.

Example:

~~~xml
<saml:AudienceRestriction>
  <saml:Audience>
    https://portal.example.test/saml2/metadata/corp
  </saml:Audience>
  <saml:Audience>
    https://other.example.test/sp
  </saml:Audience>
</saml:AudienceRestriction>
~~~

Such an assertion is **not invalid on its own** simply for listing another Audience, provided the SP's Entity ID is in the allowed set and all other conditions pass. Tests must not enforce a false rule that "every Audience must equal the current entityId" when SAML profiles allow multiple audiences.

Conversely, multiple **`AudienceRestriction`** elements apply conjunctively: if any restriction omits the current SP, the assertion **fails to satisfy** the conditions set.

~~~xml
<saml:Conditions>
  <saml:AudienceRestriction>
    <saml:Audience>https://portal.example.test/saml2/metadata/corp</saml:Audience>
  </saml:AudienceRestriction>
  <saml:AudienceRestriction>
    <saml:Audience>https://other.example.test/sp</saml:Audience>
  </saml:AudienceRestriction>
</saml:Conditions>
~~~

**Expected:** reject. Never write a flawed test claiming that having one valid Audience in any restriction lets the remaining restrictions be skipped.

### 4.3. Audience Variants to Test

| Case | Value | Expected |
| --- | --- | --- |
| Baseline | Exact `RP Entity ID` | PASS if whole response is valid |
| Other SP | `https://other.example.test/sp` | FAIL |
| Missing restriction when profile requires | No `AudienceRestriction` | FAIL per test security policy |
| Empty restriction | No `Audience` | FAIL |
| Different path | `.../metadata/corp2` | FAIL |
| Different scheme | `http://portal...` instead of HTTPS | FAIL |
| Different casing | URI identity differs from registered value | FAIL unless exact identity matches |
| Extra trailing slash | `.../corp/` | FAIL unless registered as entityId |
| Prefix attack | `.../corp.evil.example` | FAIL |
| Same restriction has valid + another value | Contains valid RP entityId | Do not reject merely for extra value |
| Two restrictions, one lacks RP | Every restriction must match | FAIL |
| SP EntityId of another tenant | `.../metadata/tenant-b` | FAIL |

**Compare Audience by exact entity identity—never use `startsWith(...)`, `contains("portal")`, or `endsWith("corp")`.** Avoid arbitrary normalization that collapses two distinct entity identifiers into one.

## 5. Recipient: Which ACS Receives This Bearer Subject?

`Recipient` lives inside:

~~~xml
<saml:Subject>
  <saml:SubjectConfirmation
      Method="urn:oasis:names:tc:SAML:2.0:cm:bearer">
    <saml:SubjectConfirmationData
        Recipient="https://portal.example.test/login/saml2/sso/corp"
        InResponseTo="_req_a"
        NotOnOrAfter="2026-01-01T12:05:00Z"/>
  </saml:SubjectConfirmation>
</saml:Subject>
~~~

In the **SAML Web Browser SSO bearer profile**, `Recipient` binds the **ACS endpoint to which the bearer assertion is presented**. SAML Core marks the attribute optional in the general schema, but the **Web Browser SSO bearer profile** imposes stricter requirements. Therefore, never infer from the XML Schema that `Recipient` can be omitted and the assertion still used to log in.

### 5.1. Wrong Recipient While Signature Remains Valid

For example, change to:

~~~xml
Recipient="https://other.example.test/saml/acs"
~~~

Response `Destination` and `Audience` still match Portal, yet bearer recipient is wrong.

**Expected:** no valid bearer `SubjectConfirmation` for Portal → **FAIL authentication**. Never accept it just because "the response POSTed to the right URL" or "Audience matched" when **`Recipient` does not match the ACS**.

### 5.2. URL Comparison Traps

| Difference | Why it matters |
| --- | --- |
| `https://portal.example.test/login/saml2/sso/corp/` | Trailing slash differs from ACS |
| `https://portal.example.test/login/saml2/sso/corp2` | Different registration/path |
| `http://portal.example.test/...` | HTTP downgrade alters URI/transport |
| `https://portal.example.test:8443/...` | Port differs from public ACS |
| `https://portal.example.test.evil.test/...` | Host prefix attack |
| `https://portal.example.test/login/saml2/sso/corp?x=1` | Query differs from registered endpoint |
| `https://other.example.test/login/saml2/sso/corp` | Different host/tenant |
| Empty or missing `Recipient` | Fails bearer profile |

At an ingress or load balancer, the **internal URL** might be `http://app-node:8080`, while the **public ACS** is `https://portal.example.test/login/saml2/sso/corp`. Configure trusted forwarded headers and `RelyingPartyRegistration.assertionConsumerServiceLocation` to match the public URL. **Never disable Recipient validation** just to work around a host/scheme mismatch.

### 5.3. Multiple SubjectConfirmations: Do Not Reject Wrongly

An assertion may contain **multiple `SubjectConfirmation` elements**. Under SAML Web Browser SSO, if **at least one bearer confirmation fully satisfies the profile**, subject confirmation can succeed (assuming all other assertion requirements hold).

For instance, if one confirmation has the wrong `Recipient` and a second confirmation has valid `Recipient`/`InResponseTo`/timing, it does **not automatically fail** solely because the first confirmation failed. Your test suite needs:

- When **all confirmations have wrong `Recipient`**: FAIL.
- When **at least one bearer confirmation is completely valid**: PASS **provided all other checks pass**.
- Never combine a valid `Recipient` from confirmation A with a valid `InResponseTo` from confirmation B to fabricate a non-existent "composite confirmation." **The same single confirmation** must satisfy all conditions.

A common buggy check writes: `any recipient == expected` **AND** `any InResponseTo == expected`. That can pass using **two different confirmations**, creating a bypass risk. Correct logic: `any confirmation where recipient AND requestId AND time AND method all valid`.

## 6. Destination: Which Endpoint Received the Response?

`Destination` sits on the **Response**:

~~~xml
<samlp:Response
    Destination="https://portal.example.test/login/saml2/sso/corp"
    InResponseTo="_req_a">
~~~

It constrains **where the message is delivered** per profile/binding and SP configuration. Do not confuse it with the `Destination` on an **`AuthnRequest`** sent **from SP to IdP**: those two messages travel in opposite directions with different targets.

**In this test article**, the ACS policy is: **Response `Destination` is mandatory and must equal the exact public ACS URI**. The fact that the SAML XML schema allows `Destination` to be omitted in certain non-binding contexts **does not permit the application to skip destination checks**. Tests must enforce the policy/binding agreed upon with the IdP.

### 6.1. Wrong Destination with Valid Recipient

Example:

~~~text
Response Destination:
  https://other.example.test/saml/acs

Assertion SubjectConfirmationData Recipient:
  https://portal.example.test/login/saml2/sso/corp
~~~

Expected: **FAIL**. A valid `Recipient` cannot excuse a wrong `Destination`.

### 6.2. Valid Destination with Wrong Recipient

Example:

~~~text
Response Destination:
  https://portal.example.test/login/saml2/sso/corp

Bearer Recipient:
  https://other.example.test/saml/acs
~~~

Expected: **FAIL**. A valid `Destination` cannot excuse a wrong `Recipient`.

### 6.3. Missing Destination

Some profiles or binding rules vary based on whether the message is signed and protocol policy. Do not claim "every SAML Response missing `Destination` violates XML schema." However, under a **Web Browser SSO ACS policy requiring `Destination`**, omitting this field must **FAIL**.

If the current app accepts Responses missing `Destination` by default in some profile/library version, that is a security decision requiring explicit review and dedicated tests—**never rewrite the expected result to PASS simply because framework defaults currently pass**. Verify OASIS Profile requirements, IdP contract, signatures, and compliance/security policies, then configure additional checks when required.

### 6.4. Do Not Compare Raw Internally Assembled Servlet URLs Alone

In a reverse-proxy environment:

~~~text
Browser -> https://portal.example.test/login/saml2/sso/corp
                  |
                  v
Ingress: terminate TLS, forward trusted headers
                  |
                  v
App node -> http://app-node:8080/login/saml2/sso/corp
~~~

The application must know its registered **public ACS endpoint**, rather than taking internal `request.getRequestURL()` literally and concluding the IdP sent to the wrong target. Design:

- Configure a fixed or consistently resolvable `assertionConsumerServiceLocation`.
- Ensure only **trusted** ingress proxies may supply `Forwarded` / `X-Forwarded-*`; block client spoofing.
- Never allow arbitrary host/scheme/path values to be accepted via an attacker-supplied `Host` header.
- Run integration tests through a real LB/proxy setup, not only local port 8080.
- Use exact matching against the registered ACS/URI, never `startsWith`.

## 7. InResponseTo: Binding the Response to the Initiated AuthnRequest

**SP-initiated SSO**:

~~~text
Browser A
  -> SP /saml2/authenticate/corp
  -> create <AuthnRequest ID="_req_a" ...>
  -> save (requestId=_req_a, browserSession=A, registrationId=corp,
          relayState, timestamp, expected IdP)
  -> redirect/POST AuthnRequest to IdP

IdP
  -> <Response InResponseTo="_req_a">
       <SubjectConfirmationData InResponseTo="_req_a" .../>
     </Response>
  -> browser POSTs SAMLResponse to ACS

SP
  -> load request from browser A's repository
  -> compare Response InResponseTo and bearer InResponseTo against ID _req_a
  -> check issuer/signature/destination/audience/recipient/time...
  -> authenticate user and manage one-time use/replay
~~~

Two distinct fields:

1. **`Response/@InResponseTo`**: protocol-level correlation to the `AuthnRequest`.
2. **`SubjectConfirmationData/@InResponseTo`**: binds subject bearer confirmation to the `AuthnRequest` in Web Browser SSO.

**Never check only one field** while ignoring the other. Modern Spring Security uses **`ResponseValidator`** for Response-level checks and **`BearerSubjectConfirmationValidator`** / assertion validation for bearer-level checks. Tests must mutate each field independently to detect whether either layer is bypassed.

### 7.1. Negative Test: Wrong Response InResponseTo

~~~xml
<samlp:Response InResponseTo="_req_other">
~~~

While browser A holds pending request `_req_a`, bearer `InResponseTo` remains `_req_a`.

Expected: **FAIL**. Never trust only the bearer ID or assume the valid assertion signature suffices.

### 7.2. Negative Test: Wrong Bearer InResponseTo

~~~xml
<saml:SubjectConfirmationData
    Recipient="https://portal.example.test/login/saml2/sso/corp"
    InResponseTo="_req_other"
    NotOnOrAfter="2026-01-01T12:05:00Z"/>
~~~

Response `InResponseTo` remains `_req_a`.

Expected: if **no other valid bearer confirmation exists**, **FAIL**. Never trust only the Response-level ID.

### 7.3. Missing Pending AuthnRequest or Wrong Browser

Cases that must be rejected under an **SP-initiated-only policy**:

- `InResponseTo` equals `_req_a`, yet `HttpSession` A **holds no such pending request**.
- Browser B submits browser A's response—even with `InResponseTo=_req_a`—copied by an attacker.
- The request was already consumed successfully, and the old response is re-POSTed.
- Request belongs to `corp`, yet callback resolves to another tenant/provider `registrationId`.
- Pending request expired past TTL or was invalidated on logout/account switch.
- Browser A uses another transaction's state/`RelayState` for a global lookup.
- `InResponseTo` is missing/blank in a flow where the SP just issued an `AuthnRequest`.
- Response-level and bearer-level `InResponseTo` **differ** without a consistent profile justification.

Spring Security uses `HttpSessionSaml2AuthenticationRequestRepository` to store requests in `HttpSession` by default in current releases. This gives **natural browser binding**, which a global cache looking up requests solely by `RelayState` or `InResponseTo` does not automatically provide. If replacing the repository with Redis/cache, enforce **browser-session binding, TTL, atomic consume, and issuer/registration association**.

### 7.4. IdP-Initiated / Unsolicited SSO Is a Separate Case

In IdP-initiated SSO deployments, users click an application tile at the IdP and the IdP POSTs a response that does not reference an SP-generated `AuthnRequest`.

**Not every missing `InResponseTo` is invalid across every SAML deployment.** However:

- If app policy is **SP-initiated-only**, missing request/`InResponseTo` → **FAIL**.
- If **IdP-initiated** is intentionally enabled, enforce a dedicated profile/policy, IdP registration allowlist, signature, issuer, audience, recipient, destination, timing, assertion replay protection, and session/account-switch safeguards.
- Never automatically "fall back to unsolicited" simply because `InResponseTo` mismatched.
- Under Web Browser SSO unsolicited profile, never fabricate a dummy `InResponseTo` to mimic an `AuthnRequest`.
- Never treat `RelayState` as proof this browser initiated the transaction unless backed by a properly designed and tested session-bound mechanism.
- Even a valid IdP response for **Mallory's account** must not silently replace Alice's session without an approved account-switch policy.

In this article's tests, **the baseline is SP-initiated-only** and any unsolicited response must be rejected.

## 8. Signature Requirements: Avoid Misdirected Negative Tests

### 8.1. Why Editing Raw XML and Re-Encoding Base64 Is Insufficient

XMLDSig protects the signed XML portions. If you:

1. Take a valid SAML Response from the test IdP;
2. Edit `<saml:Audience>` or `@Recipient`, `@Destination`, `@InResponseTo`;
3. Keep `ds:Signature` unchanged;
4. Base64-encode again and POST to ACS;

then the validator may reject **due to invalid XML signature/digest**, without ever testing Audience/Recipient/Destination/`InResponseTo`. That creates false confidence in security coverage.

### 8.2. Building Proper Fixtures

Use a **test-only IdP/signing key** and a library known to handle SAML signing properly:

~~~text
A. Generate baseline from test IdP
   - registered test IdP issuer
   - valid Response/Assertion signature as configured
   - valid timing/NameID/AuthnStatement
   - expected audience, recipient, destination, InResponseTo
   - pending AuthnRequest for the browser

B. Clone fixture object BEFORE signing
   - change EXACTLY ONE tested field

C. Serialize, canonicalize and sign again with TEST IdP signing credential
   - preserve proper signed element and XMLDSig Reference
   - retain trusted test certificate in RP

D. POST re-signed fixture to actual Spring ACS
   - same browser HttpSession/AuthnRequest repository where appropriate

E. Assert:
   - SAML protocol/security validation rejects the named field
   - NO new Saml2Authentication/authorized session
   - NO success handler/business protected content
   - reason/evidence indicates expected validation condition
~~~

**Never use production signing keys, never commit real private keys, and never fake signatures by flipping a boolean in an integration test.** With self-signed test certs, configure trust **strictly in the test RP**, isolated from production trust stores.

### 8.3. Signature Placement Also Matters

SAML allows signatures on `Response`, `Assertion`, or both per metadata/profile. Changing `Destination` breaks the signature if `Response` is signed, yet **does not necessarily** break the `Assertion` signature if only `Assertion` is signed. Therefore, never rely solely on signature failures.

Tests should cover at least:

- **Signed Response** configured like the real IdP, wrong `Destination` with **Response re-signed**.
- **Signed Assertion** configured like the real IdP, wrong Audience/Recipient/confirmation `InResponseTo` with **Assertion re-signed**.
- If production permits both modes, add **signature placement variants** confirming validation always runs.
- Test unsigned/wrong cert/wrapping/duplicate IDs separately; do not conflate with the four binding validations.
- For encrypted assertions, decrypt cleanly before validating; never corrupt ciphertext post-encryption and call it an Audience test.

### 8.4. Inspect Validation Causes, Not Just HTTP Status

An evidentiary negative test must answer:

- Did the fixture reach **`ResponseValidator`/`AssertionValidator`**?
- Did the XML signature pass at the expected stage rather than failing early?
- Which exact field differed from the expected value?
- Did `AuthenticationManager` throw/return the right failure?
- Was a new browser `SecurityContext` created?
- If the browser held a prior session, is the test reading the **old `Authentication`** and mistaking it for login success?
- Was the error code/trace recorded **without exposing the raw `SAMLResponse`**?

An HTTP failure handler may redirect `302 /login?error`; failures do not always return 401/403. **Checking authenticated/session state matters more than a single status code.**

## 9. Which Spring Security Validator Checks Which Field?

In modern Spring Security SAML 2.0 (7.x documentation):

~~~text
Saml2WebSsoAuthenticationRequestFilter
  -> create AuthnRequest
  -> Saml2AuthenticationRequestRepository (default HttpSession)

Browser + IdP
  -> POST SAMLResponse + RelayState to ACS

Saml2WebSsoAuthenticationFilter
  -> Saml2AuthenticationTokenConverter
  -> AuthenticationManager
  -> OpenSaml5AuthenticationProvider
       -> validate trusted signatures / decryption as configured
       -> ResponseValidator
            IssuerValidator
            DestinationValidator
            InResponseToValidator / response request correlation
       -> AssertionValidator
            AudienceRestrictionValidator
            BearerSubjectConfirmationValidator
            Conditions / timing / restrictions
       -> convert to Saml2Authentication

SecurityContextRepository / authorization
~~~

**Class names/validation paths may differ between Spring Security 6.x/OpenSAML 4 and Spring Security 7.x/OpenSAML 5.** Spring 7.x docs explicitly describe `OpenSaml5AuthenticationProvider` and `ResponseValidator`/`AssertionValidator`.

Spring Security docs state:

- `OpenSaml5AuthenticationProvider` checks **`Issuer`** and **`Destination`** in Response validation.
- `Response#InResponseTo` has a dedicated validator; it can be lost if configuring a **replacement `ResponseValidator` that omits that step**.
- Default Assertion validation includes **`AudienceRestriction`** and **`SubjectConfirmation`**, where bearer confirmation enforces `Recipient`/`InResponseTo`.
- Custom validation should **preserve defaults** and compose additional checks. **Never replace the entire validator with an incomplete subset.**

### 9.1. Configuring the Test App with Safe Defaults

Spring Boot 3.x/4.x and Spring Security Servlet example; check version alignment in your real project:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-security'
    implementation 'org.springframework.security:spring-security-saml2-service-provider'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-test'
}
~~~

Java configuration:

~~~java
package com.example.portal.security;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class Saml2SecurityConfig {
    @Bean
    SecurityFilterChain filterChain(HttpSecurity http) throws Exception {
        http
            .authorizeHttpRequests(authorize -> authorize
                .requestMatchers("/", "/error", "/public/**").permitAll()
                .anyRequest().authenticated())
            .saml2Login(Customizer.withDefaults());
        return http.build();
    }
}
~~~

This is a **Spring integration snippet**, not a standalone Java class runnable with `javac` alone. It requires `RelyingPartyRegistrationRepository` and IdP metadata, trusted certificates, matching ACS callback, and test sessions. If overriding `AuthenticationManager` or `OpenSaml5AuthenticationProvider`, confirm default validators remain applied.

Illustrative Boot config (synthetic metadata URL):

~~~yaml
spring:
  security:
    saml2:
      relyingparty:
        registration:
          corp:
            entity-id: "https://portal.example.test/saml2/metadata/corp"
            assertion-consumer-service-location: "https://portal.example.test/login/saml2/sso/corp"
            assertingparty:
              metadata-uri: "https://idp.example.test/metadata"
~~~

**Never use real production endpoints/certificates for mutation testing.** Match Boot properties to the paired Spring Security version; extra parameters may be needed for metadata/certificates/bindings/SSL. Public URIs and `registrationId` must match the test's ACS requests.

### 9.2. Do Not Accidentally Drop InResponseToValidator

Spring docs show you can replace `ResponseValidator` and choose a subset like `Destination` and `Issuer`. That is a **customization hook**, yet dropping `InResponseToValidator` from an SP-initiated flow without an equivalent replacement can open the door to unrequested responses.

Right approach:

~~~text
Use default Spring/OpenSAML validators
  + additional project-specific validation
  + additional logging/metrics (redacted)

Do NOT:
  replace defaults with only signature + issuer
  skip AudienceRestriction to accept "legacy IdP"
  skip BearerSubjectConfirmation to fix Recipient errors
  skip Response InResponseTo due to lost HttpSession
  skip Destination due to reverse-proxy host mismatch
~~~

When customizing, use an API that **keeps defaults** (Spring docs describe `ResponseValidator.withDefaults(customValidator)`), and re-run the entire negative suite. Never equate calling a getter like `response.getDestination()` with enforcing a real policy validator.

### 9.3. Trusted Proxy and Public ACS

Spring Security docs support `{baseUrl}`, `{registrationId}`, `{baseScheme}`, `{baseHost}`, `{basePort}` placeholders in SP entityId/ACS; they resolve per deployment/config.

If a gateway translates `https://portal.example.test` to `http://internal:8080`:

- Use a stable public ACS in metadata/registration.
- Trust forwarded headers only from authorized reverse proxies; never let clients dictate public URLs via `Host`.
- Test wrong `Destination` against the **public URI** per policy, not a guessed internal URL.
- Update IdP metadata/ACS configs under change management when changing hostname/scheme/path—**never drop `Recipient`/`Destination` validation**.

## 10. Test Fixture Matrix: One Variable Changed Per Case

Assume baseline `RP`, `ACS`, `IDP`, `_req_a`, and `browser-A` from section 2:

| ID | Field mutated | Re-signed fixture | Expected |
| --- | --- | --- | --- |
| T00 | Unchanged | Complete baseline | PASS; creates authenticated session |
| T01 | Audience = `https://other.example.test/sp` | Signature valid | **FAIL** |
| T02 | `AudienceRestriction` missing per policy | Signature valid | **FAIL** |
| T03 | `AudienceRestriction` empty | Signature valid | **FAIL** |
| T04 | Audience has SP entityId + another audience in same restriction | Signature valid | PASS if all other conditions pass |
| T05 | Two `AudienceRestriction`s; restriction 2 lacks SP | Signature valid | **FAIL** |
| T06 | Audience wrong path/tenant | Signature valid | **FAIL** |
| T07 | Audience prefix lookalike | Signature valid | **FAIL** |
| T08 | Recipient = another SP's ACS | Signature valid | **FAIL** |
| T09 | Recipient = valid ACS + `/evil` | Signature valid | **FAIL** |
| T10 | Recipient missing | Signature valid | **FAIL** |
| T11 | Recipient valid but `NotOnOrAfter` expired | Signature valid | **FAIL** |
| T12 | Two bearer confirmations, one fully valid | Signature valid | PASS per profile if all other checks pass |
| T13 | Two bearer confirmations, each satisfies only half | Signature valid | **FAIL** |
| T14 | Destination = another RP's ACS | Signature valid | **FAIL** |
| T15 | Destination = HTTP instead of HTTPS | Signature valid | **FAIL** |
| T16 | Destination missing under strict ACS policy | Signature valid | **FAIL** |
| T17 | Destination valid but Recipient wrong | Signature valid | **FAIL** |
| T18 | Recipient valid but Destination wrong | Signature valid | **FAIL** |
| T19 | Response `InResponseTo` = `_req_other` | Signature valid | **FAIL** |
| T20 | Response `InResponseTo` = null | Signature valid | **FAIL** in SP-initiated-only |
| T21 | Bearer `InResponseTo` = `_req_other` | Signature valid | **FAIL** unless another valid confirmation exists |
| T22 | Response `InResponseTo` and Bearer `InResponseTo` differ | Signature valid | **FAIL** |
| T23 | Request ID exists but belongs to browser B | Signature valid | **FAIL** on browser A |
| T24 | Pending `AuthnRequest` no longer exists | Signature valid | **FAIL** |
| T25 | `AuthnRequest` already consumed/used | Signature valid | **FAIL** replay |
| T26 | Wrong issuer/certificate | Vary as independent test | **FAIL**; do not confuse with field tests |
| T27 | Replay previous Assertion/Response ID | Signature valid | **FAIL** |
| T28 | `RegistrationId` of another SP with same IdP | Signature valid | **FAIL** if audience/ACS/request binding mismatches |
| T29 | Clock skew beyond policy | Signature valid | **FAIL** |
| T30 | Signed `SAMLResponse` mutated post-signing | Signature invalid | **FAIL** due to signature; DO NOT count as proof for T01–T22 |
| T31 | IdP-initiated unsolicited response | Signature valid | **FAIL** under SP-initiated-only |
| T32 | `RelayState` tampered/open redirect | Per fixture policy | **FAIL** if breaking correlation/redirect allowlist |
| T33 | Unregistered ACS alias/case/trailing slash URL | Signature valid | **FAIL** when not matching expected ACS |
| T34 | Same NameID in another tenant | Signature valid | **FAIL** if issuer/audience/registration mismatches |
| T35 | Old session cookie with another browser's response | Signature valid | **FAIL**; no account confusion |

**Each test should state clearly whether it evaluates Response, Assertion, or bearer confirmation**, and a response counts as PASS only after both **protocol validation** and **local session policy** complete.

## 11. How to Set Up a Real Integration Test

An end-to-end test through the Spring Security `FilterChain` should:

1. Create a dedicated **test IdP key pair and X.509 certificate**, stored in test secrets or controlled fixtures; configure the test RP to trust that certificate.
2. Configure `RelyingPartyRegistration` with exact `entityId`, `assertionConsumerServiceLocation`, IdP issuer, and trusted verification certificate.
3. Initiate an **SP-initiated `AuthnRequest`** via `GET /saml2/authenticate/corp` in a browser/`MockHttpSession`.
4. Extract the actual **`AuthnRequest` ID/`RelayState`** from the test harness/repository.
5. Use an OpenSAML/test IdP helper to build a **signed Response** with Assertion and bearer `SubjectConfirmation` matching baseline.
6. POST the response using the right binding and content type—typically `SAMLResponse=Base64(UTF-8 XML)` and `RelayState` if present—to ACS `/login/saml2/sso/corp` with the **matching session/browser**.
7. Assert baseline PASS: creates `Saml2Authentication` with the right external identity and local authorities.
8. Create mutations **before re-signing**, keeping all other fields at baseline; POST each fixture with **fresh request/session/response IDs**.
9. Assert each negative: **no login success, no new authenticated session, no protected content returned**.
10. Test separately with a browser holding an older login; a rejected response must not create a **new `Authentication`**. Never infer from `isAuthenticated()` on the **old session** that the negative response logged in.
11. Test across multiple browsers, two IdPs/tenants, multiple replicas, or Redis if the repository is non-local.
12. Collect reason codes/validator categories in redacted test logs without logging full XML/assertions/tokens.

### 11.1. MockMvc Skeleton: POSTing to the Real ACS

This snippet **is only an integration-test fragment** and does not create signed responses itself; `signedSamlResponseXml` must be built and re-signed by a fixture helper **before POSTing**:

~~~java
String encoded = Base64.getEncoder().encodeToString(
    signedSamlResponseXml.getBytes(StandardCharsets.UTF_8));

MvcResult result = mockMvc.perform(
    post("/login/saml2/sso/corp")
        .session(browserSessionWithAuthnRequest)
        .contentType(MediaType.APPLICATION_FORM_URLENCODED)
        .param("SAMLResponse", encoded)
        .param("RelayState", relayStateFromRequest))
    .andReturn();

// Assert security outcome via session/Authentication and login handler.
// Failure status may be 302, 401, or another configured response.
// Do NOT assert "403" as the only acceptable negative outcome.
~~~

**Imports** (Spring Security Test/MockMvc dependencies required):

~~~java
import java.nio.charset.StandardCharsets;
import java.util.Base64;
import org.springframework.http.MediaType;
import org.springframework.test.web.servlet.MvcResult;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
~~~

You may need Spring test annotations/config to wire `mockMvc`, `MockHttpSession`, and the fake trusted test IdP. When the ACS is exempted from `CsrfFilter` by Spring Security's filter setup, ensure **only the exact ACS URL** has the exemption; never `csrf.disable()` app-wide.

**Never use `SecurityMockMvcRequestPostProcessors.saml2Login()` as proof of validation**: a test post-processor can construct a valid mock `Saml2Authentication` **bypassing XML/SAML signatures/`ResponseValidator`/`AssertionValidator`**. It is useful for post-login authorization tests, but **does not prove** Audience/Recipient/Destination/`InResponseTo` mismatches are rejected.

### 11.2. Preserving the Expected Request in Negative Tests

A common test-harness bug:

~~~text
Test A:
  uses _req_a, POSTs negative fixture
Test B:
  reuses _req_a, POSTs another fixture
  but request repo entry was already removed or session changed
Test B fails due to missing request, not wrong Recipient.
~~~

Solution: **each test creates a fresh session and `AuthnRequest`**, fresh response/assertion IDs, an explicit test clock, or a controlled fixture repository reset for test isolation. Never share mutable state across tests creating order-dependent outcomes.

### 11.3. Distinguishing Failure Stages

Test observability can categorize outcomes:

~~~text
SIGNATURE_INVALID
ISSUER_MISMATCH
DESTINATION_MISMATCH
IN_RESPONSE_TO_MISMATCH
AUDIENCE_MISMATCH
RECIPIENT_MISMATCH
BEARER_EXPIRED
AUTHN_REQUEST_MISSING
BROWSER_SESSION_MISMATCH
ASSERTION_REPLAY
LOCAL_USER_DISABLED
~~~

These are **team-defined category names**, not mandatory standard error codes always emitted by Spring. Exception classes/messages change across Spring/OpenSAML versions; assert **security outcomes** and, if instrumented, stable reason categories rather than coupling to exact exception string wording.

## 12. Standalone Java 17: Binding Model and Negative Tests

The following program **runs on JDK 17+** without Spring/OpenSAML/KDC/IdP/network. It models these rules:

- The SAML Response has passed a **mocked trusted signature verifier**.
- Valid IdP issuer, Destination, pending `AuthnRequest`, and browser binding.
- Assertion has the right issuer and satisfies **all** `AudienceRestriction` elements; **OR within a restriction**, **AND across restrictions**.
- **At least one bearer `SubjectConfirmation`** simultaneously satisfies `Recipient`, `InResponseTo`, and `NotOnOrAfter`.
- Response IDs and Assertion IDs are single-use; the pending request is consumed on success.
- Wrong/missing Audience, Recipient, Destination, Response/Bearer `InResponseTo`, wrong issuer/signature, wrong browser, expired bearer, and replay are all rejected.

**Security limitation:** `signatureVerified` is a **trusted mock outcome from a test verifier**, **not a boolean taken from SAML XML, client HTTP headers, or JSON**. This program **does not verify XMLDSig, certificate trust, XML parsing, schemas, encryption, full clock-skew policies, assertion conditions/NameID/subject confirmation methods, multi-node replay, or XSW**. It **must not be used as a production SAML `AuthenticationProvider`**. For real testing, use OpenSAML/Spring Security test RP and signed fixtures as in section 11.

File **Saml2BindingNegativeTestDemo.java**:

~~~java
import java.time.Duration;
import java.time.Instant;
import java.util.HashMap;
import java.util.HashSet;
import java.util.List;
import java.util.Map;
import java.util.Set;

public class Saml2BindingNegativeTestDemo {
    static final String RP = "https://portal.example.test/saml2/metadata/corp";
    static final String ACS = "https://portal.example.test/login/saml2/sso/corp";
    static final String IDP = "https://idp.example.test/metadata";
    static final Instant NOW = Instant.parse("2026-01-01T12:00:00Z");

    record Pending(String requestId, String browserId) {}
    record Bearer(String recipient, String inResponseTo,
                  Instant notOnOrAfter) {}
    record Assertion(String id, String issuer,
                     List<Set<String>> audienceRestrictions,
                     List<Bearer> bearerConfirmations) {}
    record Response(String id, String issuer, String destination,
                    String inResponseTo, boolean signatureVerified,
                    Assertion assertion) {}

    static final class Policy {
        final Map<String, Pending> requests = new HashMap<>();
        final Set<String> usedResponses = new HashSet<>();
        final Set<String> usedAssertions = new HashSet<>();

        void start(String requestId, String browserId) {
            requests.put(requestId, new Pending(requestId, browserId));
        }

        boolean validate(String browserId, Response r) {
            // signatureVerified is the output of a TRUSTED MOCK verifier.
            // Never accept it from SAML XML, HTTP params or user input.
            if (r == null || !r.signatureVerified()
                    || !IDP.equals(r.issuer())
                    || !ACS.equals(r.destination())
                    || r.id() == null || r.id().isBlank()
                    || r.inResponseTo() == null) return false;
            Pending pending = requests.get(r.inResponseTo());
            if (pending == null || !pending.browserId().equals(browserId))
                return false;
            Assertion a = r.assertion();
            if (a == null || a.id() == null || a.id().isBlank()
                    || !IDP.equals(a.issuer())
                    || a.audienceRestrictions() == null
                    || a.audienceRestrictions().isEmpty()) return false;

            // OR within one AudienceRestriction, AND across restrictions.
            for (Set<String> restriction : a.audienceRestrictions()) {
                if (restriction == null || !restriction.contains(RP))
                    return false;
            }
            if (a.bearerConfirmations() == null
                    || a.bearerConfirmations().isEmpty()) return false;
            boolean hasValidBearer = false;
            for (Bearer confirmation : a.bearerConfirmations()) {
                if (confirmation != null
                        && ACS.equals(confirmation.recipient())
                        && pending.requestId().equals(
                            confirmation.inResponseTo())
                        && confirmation.notOnOrAfter() != null
                        && NOW.isBefore(confirmation.notOnOrAfter())) {
                    hasValidBearer = true;
                    break;
                }
            }
            if (!hasValidBearer
                    || usedResponses.contains(r.id())
                    || usedAssertions.contains(a.id())) return false;
            // Simplified single-process consume; not cluster-safe/atomic.
            if (!requests.remove(pending.requestId(), pending)) return false;
            usedResponses.add(r.id());
            usedAssertions.add(a.id());
            return true;
        }
    }

    static Response base(String requestId) {
        return new Response("resp-" + requestId, IDP, ACS, requestId, true,
            new Assertion("assert-" + requestId, IDP,
                List.of(Set.of(RP)),
                List.of(new Bearer(ACS, requestId,
                    NOW.plus(Duration.ofMinutes(5))))));
    }

    static Response withAssertion(Response r, Assertion a) {
        return new Response(r.id(), r.issuer(), r.destination(),
            r.inResponseTo(), r.signatureVerified(), a);
    }
    static Response withBearer(Response r, Bearer b) {
        Assertion a = r.assertion();
        return withAssertion(r, new Assertion(a.id(), a.issuer(),
            a.audienceRestrictions(), List.of(b)));
    }
    static Response withAudience(Response r,
            List<Set<String>> restrictions) {
        Assertion a = r.assertion();
        return withAssertion(r, new Assertion(a.id(), a.issuer(),
            restrictions, a.bearerConfirmations()));
    }
    static void check(String label, boolean passes) {
        System.out.println(label + "=" + passes);
    }

    public static void main(String[] args) {
        Policy policy = new Policy();
        policy.start("_req_a", "browser-A");
        Response good = base("_req_a");

        check("wrongAudienceRejected", !policy.validate("browser-A",
            withAudience(good, List.of(Set.of(
                "https://evil.example.test/sp")))));
        check("missingAudienceRejected", !policy.validate("browser-A",
            withAudience(good, List.of())));
        check("oneWrongRestrictionRejected", !policy.validate("browser-A",
            withAudience(good, List.of(Set.of(RP),
                Set.of("https://other.example.test/sp")))));
        check("wrongRecipientRejected", !policy.validate("browser-A",
            withBearer(good, new Bearer(
                "https://other.example.test/acs", "_req_a",
                NOW.plusSeconds(300)))));
        check("recipientPrefixTrickRejected", !policy.validate("browser-A",
            withBearer(good, new Bearer(
                ACS + "/evil", "_req_a", NOW.plusSeconds(300)))));
        check("missingRecipientRejected", !policy.validate("browser-A",
            withBearer(good, new Bearer(
                null, "_req_a", NOW.plusSeconds(300)))));
        check("wrongDestinationRejected", !policy.validate("browser-A",
            new Response(good.id(), good.issuer(),
                "https://other.example.test/acs", good.inResponseTo(),
                true, good.assertion())));
        check("httpDowngradeRejected", !policy.validate("browser-A",
            new Response(good.id(), good.issuer(),
                "http://portal.example.test/login/saml2/sso/corp",
                good.inResponseTo(), true, good.assertion())));
        check("missingDestinationRejected", !policy.validate("browser-A",
            new Response(good.id(), good.issuer(), null,
                good.inResponseTo(), true, good.assertion())));
        check("wrongResponseInResponseToRejected",
            !policy.validate("browser-A",
                new Response(good.id(), good.issuer(),
                    good.destination(), "_req_other",
                    true, good.assertion())));
        check("missingResponseInResponseToRejected",
            !policy.validate("browser-A",
                new Response(good.id(), good.issuer(),
                    good.destination(), null,
                    true, good.assertion())));
        check("wrongBearerInResponseToRejected", !policy.validate("browser-A",
            withBearer(good, new Bearer(ACS, "_req_other",
                NOW.plusSeconds(300)))));
        check("expiredBearerRejected", !policy.validate("browser-A",
            withBearer(good, new Bearer(ACS, "_req_a",
                NOW.minusSeconds(1)))));
        check("wrongIssuerRejected", !policy.validate("browser-A",
            new Response(good.id(), "https://fake-idp.example.test",
                good.destination(), good.inResponseTo(), true,
                good.assertion())));
        check("untrustedSignatureRejected", !policy.validate("browser-A",
            new Response(good.id(), good.issuer(),
                good.destination(), good.inResponseTo(), false,
                good.assertion())));
        check("crossBrowserRejected",
            !policy.validate("browser-B", good));
        check("unsignedDoesNotConsumeRequest",
            policy.requests.containsKey("_req_a"));

        check("validBaselineAccepted",
            policy.validate("browser-A", good));
        check("sameResponseReplayRejected",
            !policy.validate("browser-A", good));
        check("requestConsumedAfterSuccess",
            !policy.requests.containsKey("_req_a"));

        policy.start("_req_b", "browser-B");
        Response goodB = base("_req_b");
        check("alternativeAllowedAudienceAccepted",
            policy.validate("browser-B",
                withAudience(goodB, List.of(Set.of(
                    RP, "https://alias.example.test/sp")))));

        policy.start("_req_c", "browser-C");
        Response goodC = base("_req_c");
        Bearer invalid = new Bearer("https://bad.example.test/acs",
            "_req_c", NOW.plusSeconds(300));
        Assertion a = goodC.assertion();
        Assertion withTwo = new Assertion(a.id(), a.issuer(),
            a.audienceRestrictions(), List.of(invalid,
                new Bearer(ACS, "_req_c", NOW.plusSeconds(300))));
        check("oneValidBearerAmongTwoAccepted",
            policy.validate("browser-C",
                withAssertion(goodC, withTwo)));

        policy.start("_req_d", "browser-D");
        Response goodD = base("_req_d");
        check("missingRequestRejected",
            !policy.validate("browser-D",
                new Response("resp-unknown", goodD.issuer(), ACS,
                    "_req_unknown", true, goodD.assertion())));
        check("laterUnsolicitedResponseRejected",
            !policy.validate("browser-X", base("_req_nobody")));
    }
}
~~~

Run:

~~~bash
javac --release 17 Saml2BindingNegativeTestDemo.java
java Saml2BindingNegativeTestDemo
~~~

**Exact stdout after compiling/running on JDK 17:**

~~~text
wrongAudienceRejected=true
missingAudienceRejected=true
oneWrongRestrictionRejected=true
wrongRecipientRejected=true
recipientPrefixTrickRejected=true
missingRecipientRejected=true
wrongDestinationRejected=true
httpDowngradeRejected=true
missingDestinationRejected=true
wrongResponseInResponseToRejected=true
missingResponseInResponseToRejected=true
wrongBearerInResponseToRejected=true
expiredBearerRejected=true
wrongIssuerRejected=true
untrustedSignatureRejected=true
crossBrowserRejected=true
unsignedDoesNotConsumeRequest=true
validBaselineAccepted=true
sameResponseReplayRejected=true
requestConsumedAfterSuccess=true
alternativeAllowedAudienceAccepted=true
oneValidBearerAmongTwoAccepted=true
missingRequestRejected=true
laterUnsolicitedResponseRejected=true
~~~

### 12.1. Interpreting the Output

- `wrongAudienceRejected` and `oneWrongRestrictionRejected`: do not accept assertions for the wrong SP; multiple restrictions follow exact logical semantics.
- `wrongRecipientRejected`, `recipientPrefixTrickRejected`, and `missingRecipientRejected`: bearer confirmation must match the public ACS, rejecting path prefixes or missing recipients.
- `wrongDestinationRejected`, `httpDowngradeRejected`, `missingDestinationRejected`: Response must target the exact ACS under strict policy.
- `wrongResponseInResponseToRejected` and `wrongBearerInResponseToRejected`: both request-binding levels are enforced independently.
- `crossBrowserRejected`: browser B cannot consume an `AuthnRequest` held by browser A.
- `unsignedDoesNotConsumeRequest`: a rejected input in the demo does not delete browser A's pending request.
- `validBaselineAccepted`: a complete response satisfying all conditions is accepted.
- `sameResponseReplayRejected` and `requestConsumedAfterSuccess`: a consumed request cannot be reused.
- `alternativeAllowedAudienceAccepted`: one restriction listing the SP entityId alongside another audience still satisfies conditions and is not falsely rejected.
- `oneValidBearerAmongTwoAccepted`: one fully valid bearer confirmation among two suffices for subject confirmation.
- `missingRequestRejected` and `laterUnsolicitedResponseRejected`: an SP-initiated-only policy rejects responses lacking a prior request.

**Distinction:** this is a **logic model** using simulated post-crypto booleans, and does not prove real OpenSAML handles XMLDSig/Conditions/SubjectConfirmation. Production tests must use XML fixtures signed **after** mutating fields and run through the real `OpenSaml5AuthenticationProvider`.

## 13. Commonly Missed Edge Cases

### 13.1. Valid Response Destination, Different HTTP ACS Request

If Response `Destination` = `https://portal.example.test/login/saml2/sso/corp`, yet an attacker POSTs to a different app endpoint routed through the same filter, the server must match **destination against ACS policy and the actual receiving endpoint**. Never build a catch-all endpoint accepting any signed `SAMLResponse` for any tenant while skipping registration/ACS mapping.

### 13.2. Valid Recipient, Bearer Confirmation for Another Request

Even when `Recipient` matches the ACS, a `SubjectConfirmationData/@InResponseTo` of `_req_other` does not belong to `AuthnRequest` `_req_a`. This is a replay/login-injection case needing its own negative test.

### 13.3. Replaying IDs Across Multiple Browsers

A consumed Response ID/Assertion ID must never be accepted again through another browser. Storing replay state only in a local `HttpSession` may fail if the same signed assertion is POSTed across multiple nodes. For assertion profiles requiring replay protection, use a shared policy/cache with an appropriate TTL.

### 13.4. Multiple Assertions in One Response

Never pick "the first assertion with a valid Audience" and ignore other unverified sections. Every assertion used to build `Authentication` must have valid issuer/signature/conditions/subject confirmation; identities and attributes across assertions must never be mixed outside profile rules.

### 13.5. Signed Response vs. Signed Assertion

An RP may receive Response-signed, Assertion-signed, or both per IdP contract. Tests verify the **exact protected element** and inspect signature placement/trust. If only the Response is signed while an assertion is unsigned inside, never trust a "foreign" assertion outside the signed scope. If the Assertion is signed individually, changing Response `Destination` still requires Response-level validation. XML signature wrapping is a distinct test and must not be merged into field-mismatch tests.

### 13.6. RelayState Is Not an Independent Source of Trust

`RelayState` carries/references request state or return locations; never treat that string alone as proof this browser initiated the transaction. If `CacheSaml2AuthenticationRequestRepository` looks up globally by `RelayState`, add browser binding/one-time consumption. Never redirect to an external URL merely because `RelayState` contains a URI.

### 13.7. Valid Request, Locked Local User

After all SAML validation passes, still check mapping from external identity to local user/tenant/roles. A valid assertion for Alice does not grant Alice access to finance or admin APIs.

## 14. Error Reporting Policy and SecurityContext

In integration tests, mismatches must never create an **Authenticated `Saml2Authentication`** for that callback.

**However, distinguish carefully:**

- Browser **anonymous** before callback: after a negative response it must **stay anonymous**.
- Browser already holding **Alice's** session: a negative response for Mallory must not switch it to Mallory; the app may keep Alice or clear the session per policy, yet the test must prove **no new login occurred**.
- SAML filter failure handlers may redirect 302 or return 401; never hard-code one fixed status if app policy does not mandate it.
- Never invoke controllers directly or inject a fake `SecurityContext` in tests and claim the **OpenSAML validator** rejected the field.
- Never assert only that `/private` returns 200 on an old session: it may return 200 due to an **existing `Authentication`**, even though the new callback actually failed.
- If a custom authentication converter/validator fails open and creates `ROLE_USER` from `NameID` before validating signatures/conditions, that is a critical vulnerability.

A solid assertion block looks like:

~~~text
Given browser state before callback:
  oldSessionUser = none OR alice
  pendingRequestId = _req_a
When:
  POST signed mutated SAMLResponse
Then:
  negative test did NOT create new authenticated identity
  success handler not invoked
  no new privilege/tenant assignment
  protected endpoint not reachable as asserted attacker identity
  response/assertion replay not accepted
  reason category matches target mismatch if instrumented
~~~

## 15. Troubleshooting Common Failures

| Symptom | Likely cause | Resolution |
| --- | --- | --- |
| Audience mismatch | IdP sends ACS URL instead of SP entityId, or wrong tenant | Compare RP entityId/metadata and IdP audience config |
| Recipient mismatch | IdP sends to old ACS/alias/path | Sync ACS URL in IdP metadata and RP registration |
| Destination mismatch | Public HTTPS vs. internal HTTP behind reverse proxy | Fix public base URL and trusted forwarded headers |
| `InResponseTo` mismatch | Missing/different pending `AuthnRequest`, wrong browser | Check `HttpSessionSaml2AuthenticationRequestRepository`/`RelayState` |
| XML-editing test always fails | Broken XMLDSig signature | Re-sign fixture before POSTing |
| `InResponseTo` test fails with no session | `SameSite` cookie dropped on SAML POST | Design proper `SameSite`/ACS binding; do not drop correlation |
| Test passes on machine A, fails on B | Local request repo, replicas do not share session | Spring Session/Redis or properly designed sticky sessions |
| Callback hits wrong registration | IdP issuer, tenant, ACS route unlinked | Check `RelyingPartyRegistration` resolver and `registrationId` |
| Wrong Recipient still passes | Bearer `SubjectConfirmation` validator disabled/misconfigured | Restore default validator, add regression test |
| Wrong Audience still passes | `AudienceRestrictionValidator` removed | Restore default assertion conditions validation |
| Wrong Destination still passes | `DestinationValidator` dropped | Restore default response validation |
| Wrong Response `InResponseTo` passes | Custom `ResponseValidator` omits `InResponseToValidator` | Use defaults + extensions, check SP-init policy |
| Wrong Bearer `InResponseTo` passes | `BearerSubjectConfirmationValidator` dropped or picked wrong confirmation | Test per-bearer all-fields binding |
| Fails only when SAML encrypted | Decryption/key/ordering differs in fixture | Check encrypted assertion flow and signature validation stage |
| App login succeeds yet user lacks roles | Local user mapping/authorization | Separate SAML validation from local roles |
| Login fails yet `/private` still returns 200 | Stale `SecurityContext`/`HttpSession` remains | Assert new `Authentication`, not HTTP status alone |
| IdP-initiated response lacks request | Unsolicited flow | Separate policy; do not mix SP-init rules |
| IdP cert rollover breaks everything | Signing certificate mismatch | Update metadata trust via trusted channel; do not disable signatures |
| Receiver mismatch across hostnames | Inconsistent CNAME/ingress canonicalization | Pin public ACS, test exact paths |
| Authentication accepted twice | Missing replay cache/one-time request consume | Implement state/cache and multi-node tests |
| Mismatch on only one node | Divergent host, proxy, config, or session store | Inspect node, metadata, session storage, and source of truth |

### 15.1. Runbook for Debugging at the Right Layer

1. **From redacted logs**, identify `registrationId` and expected entityId/ACS/issuer.
2. Check whether the test created a **fresh `AuthnRequest`** in the right browser session before each response.
3. Verify the fixture signature (test key) passed; otherwise you have **no coverage** of the mutated field.
4. Compare Audience against the SP Entity ID, not the ACS.
5. Compare `Recipient` on bearer `SubjectConfirmationData` against the public ACS.
6. Compare `Destination` on `Response` against the receiving endpoint per policy/profile.
7. Compare Response/Bearer `InResponseTo` against the `AuthnRequest` ID and request repository/browser binding.
8. Check timing/clock skew, replay state, and issuer/certificate.
9. Check browser `SameSite` cookies and ingress forwarded headers.
10. Assert the exact **Auth outcome and new session**; never let an existing session mask results.
11. On mismatch, fix metadata/configuration/test fixtures; **never disable validators**.
12. Retain regression tests and monitor rejection categories.

## 16. What Should Be Tested at Unit, Integration, or End-to-End Level?

| Level | Goal | Example |
| --- | --- | --- |
| **Domain policy unit test** | Verify exact field-binding logic | Java 17 mock in section 12 |
| **Custom validator unit test** | Test extensions if genuinely present | OpenSAML objects validated/trusted per helper |
| **Spring Security integration** | Run real filter/provider/signature/issuer/conditions | MockMvc POST signed fixture to ACS |
| **Browser + test IdP E2E** | Test `SameSite`, `RelayState`, redirects, session correlation | Browser A/B, multi-tab, IdP POST, login failure |
| **Ingress/proxy environment** | Verify public ACS/Destination and forwarded headers | Public HTTPS → internal HTTP, host aliases |
| **Security regression** | Prevent accidental validator removal/weakening | Wrong Audience/Recipient/Destination/`InResponseTo` stay rejected |

**Both positive baselines and negative controls are mandatory.** If every response fails because of a wrong keytab/IdP/certificate, the test suite may look "green" because negative assertions always pass while SAML login is actually broken. The positive test must PASS under the exact same configuration.

## 17. Anti-Patterns to Avoid

1. **"Valid signature means login succeeds."** False: you still need Audience, Recipient, Destination, `InResponseTo`, time, issuer, and replay checks.
2. **"Audience is the ACS URL."** False whenever SP Entity ID differs from ACS.
3. **"Destination and Recipient are identical so checking one is enough."** False: two fields at two different layers.
4. **"Valid Response `InResponseTo` is enough."** False if bearer confirmation `InResponseTo` is wrong.
5. **"One bearer has the right Recipient and another has the right `InResponseTo`, so pass."** False: a single bearer must satisfy all conditions.
6. **"Every Audience in one restriction must equal SP."** False under multi-audience semantics within one restriction.
7. **"A SAML Response without a pending `AuthnRequest` is always malformed XML."** False: IdP-initiated profiles exist, though they may be **forbidden by app policy**.
8. **"Drop `InResponseToValidator` to fix `SameSite` cookies."** False: weakens correlation/login fixation defenses.
9. **"Drop `DestinationValidator` to work behind a reverse proxy."** False: fix public URL/metadata and forwarded header trust.
10. **"A test that mutates a character in signed XML and gets rejected is enough."** False: it may fail signature verification without testing the field.
11. **"Using `spring-security-test` `saml2Login()` tests XML."** False: test auth post-processors can bypass XML validation.
12. **"Assert only HTTP 401."** Insufficient: failure handlers may 302, or an old `SecurityContext` may remain.
13. **"Check Request ID without browser binding."** Insufficient: an attacker's response can be looked up from a global cache.
14. **"Use `startsWith`/`endsWith` to compare entity IDs."** Prefix/lookalike host/path risk.
15. **"Enable all unsolicited responses because the IdP portal needs an app tile."** No: require an allowlist, separate policy, and account-switch protections.
16. **"Let the test IdP use the production certificate for easier integration."** Unnecessary and dangerous; isolate test environments.

## 18. Pre-Production Completion Checklist

- [ ] SP Entity ID, ACS URL, IdP Entity ID, and `registrationId` are precisely defined.
- [ ] Audience, Recipient, Destination, and both `InResponseTo` fields are clearly distinguished.
- [ ] A valid signed baseline response **PASSES** through the real Spring Security SAML filter.
- [ ] Wrong Audience test with **valid signature** → FAIL.
- [ ] Missing/empty `AudienceRestriction` test per policy → FAIL.
- [ ] Multiple Audiences within one restriction tested with OR semantics.
- [ ] Multiple `AudienceRestriction` elements tested with AND semantics.
- [ ] Wrong Recipient, missing Recipient, and URL prefix/path/HTTPS mismatch tests → FAIL.
- [ ] Multiple bearer confirmations tested: PASS only if **one confirmation** satisfies all conditions.
- [ ] Wrong Destination (different host/path/scheme) test → FAIL.
- [ ] Missing Destination test under strict ACS policy → FAIL.
- [ ] Valid Destination with wrong Recipient and vice versa → FAIL.
- [ ] Wrong/missing Response `InResponseTo` in SP-initiated flow → FAIL.
- [ ] Wrong/missing Bearer `InResponseTo` in SP-initiated flow → FAIL.
- [ ] Different browser session with matching request ID → FAIL.
- [ ] Missing/replayed/expired `AuthnRequest` → FAIL.
- [ ] SAML Response/Assertion ID replay → FAIL.
- [ ] IdP issuer/certificate trust tested independently → FAIL.
- [ ] Time conditions/bearer `NotOnOrAfter` and clock skew tested → FAIL outside window.
- [ ] SP-init-only policy tested to reject unsolicited responses.
- [ ] If IdP-init is enabled: dedicated policy, full assertion checks, and silent account-switch protection exist.
- [ ] `OpenSaml5AuthenticationProvider` (or version-matching provider) still runs default response/assertion validators.
- [ ] No custom validator accidentally omits `InResponseTo`/Audience/Recipient/Destination.
- [ ] Tested through **MockMvc real ACS**, not solely post-processors building fake `Saml2Authentication`.
- [ ] Signed fixtures **mutate fields before re-signing** with the test IdP key.
- [ ] Test keys/certificates have zero overlap with production secrets.
- [ ] Callbacks create no new `SecurityContext`/user session when negative tests fail.
- [ ] Old session `Authentication` is never confused with a new callback outcome.
- [ ] Public ACS, metadata, and trusted ingress forwarding align in config.
- [ ] `SameSite` cookies/bindings work across cross-site SAML POSTs.
- [ ] Multiple tabs/nodes have proper request repositories and replay caches.
- [ ] Session fixation, account switching, and local authorization are protected.
- [ ] Logs record categorized failure reasons without printing raw `SAMLResponse`, NameIDs, assertions, cookies, or signing keys.
- [ ] Automated regression tests run whenever updating Spring Security/OpenSAML/IdP metadata.

## 19. Self-Check Questions

**1. What value must Audience be compared against?**

The registered **SP Entity ID**, not automatically the ACS URL or `registrationId`.

**2. At which layer does Recipient appear?**

Inside bearer `SubjectConfirmationData` under `Assertion/Subject`, not directly as a Response attribute.

**3. At which layer does Destination appear?**

Attribute `samlp:Response/@Destination`, identifying the message target per binding/profile.

**4. For SP-initiated SSO, where is `InResponseTo` checked?**

At both Response-level and bearer `SubjectConfirmationData`-level; they must correlate with the saved `AuthnRequest` ID in the exact browser transaction.

**5. Can a validly signed SAML Response with Audience for tenant B log in at tenant A?**

No, if the assertion does not satisfy SP A's `AudienceRestriction`. A signature does not override audience policy.

**6. If editing Audience after the IdP signed causes login to fail, does that prove `AudienceValidator` ran?**

No. The error may be an invalid XML signature. Mutate before **re-signing** the fixture and verify the validation stage.

**7. Why can't a valid Destination compensate for a wrong Recipient?**

Because the Response was delivered to the right endpoint, yet the bearer assertion **was not meant for that endpoint**; both constraints are independent.

**8. If one `AudienceRestriction` contains two audiences and one matches the SP, does it always fail?**

No. Within a single restriction, conditions are met if **at least one audience matches**. With multiple restrictions, each restriction must be satisfied.

**9. If two bearer confirmations exist—one with the right Recipient and one with the right `InResponseTo`, neither having both—does it pass?**

No. **One** confirmation must satisfy all its conditions simultaneously.

**10. Why must tests changing `InResponseTo` on the Response be separate from tests changing Bearer `InResponseTo`?**

Because those are **two validator layers**. Dropping either one could allow an invalid response through.

**11. Can looking up an `AuthnRequest` by `InResponseTo` in a global cache be considered safe on its own?**

Insufficient. You must know the request was initiated by **this browser/session**, for the right IdP/registration, and has not been consumed.

**12. Is an IdP-initiated SAML response lacking `InResponseTo` always invalid?**

Not necessarily if the deployment **permits unsolicited SSO**. Under an **SP-initiated-only policy**, however, it must be rejected.

**13. What failure can `SameSite=Lax` cause?**

The RP cookie is often omitted on cross-site SAML ACS POSTs, causing the SP to lose the session's `AuthnRequest`; fix cookies/binding rather than dropping correlation.

**14. Can an unauthenticated negative test assert only `status=401`?**

Insufficient. The failure handler may redirect 302; verify no new `Authentication` or new access is granted.

**15. Why is a positive baseline mandatory?**

If a wrong IdP certificate/test setup makes **every fixture fail**, negative tests will false-PASS without actually exercising the four fields.

**16. Should `AudienceRestrictionValidator`/Recipient validation be removed if a legacy IdP sends the wrong field?**

No. Fix IdP metadata/ACS/issuer/conditions or design a security-reviewed migration plan; dropping validators introduces token substitution risks.

**17. Must an SP Entity ID necessarily be an ACS URL?**

No. Entity ID identifies the SP; the ACS URL receives `SAMLResponse`. They may be completely different URIs.

**18. If a user already holds Alice's session and a SAML callback is rejected, why might the next request still return 200?**

The browser may still hold **Alice's old `Authentication`**. Negative tests must verify **no new login occurred**, never mistaking an old session's 200 for SAML validation passing.

## 20. References

- OASIS, **SAML 2.0 Core**, `AudienceRestriction`, `SubjectConfirmationData`, `Response Destination`, `InResponseTo`, Conditions: https://docs.oasis-open.org/security/saml/v2.0/saml-core-2.0-os.pdf
- OASIS, **SAML 2.0 Profiles**, Web Browser SSO, bearer Recipient, `InResponseTo`, solicited/unsolicited: https://docs.oasis-open.org/security/saml/v2.0/saml-profiles-2.0-os.pdf
- OASIS, **SAML 2.0 Approved Errata**, clarifications on bearer Recipient/`InResponseTo`/Audience and lifetimes: https://docs.oasis-open.org/security/saml/v2.0/sstc-saml-errata-2.0-cd-04.html
- Spring Security, **SAML 2.0 Login Overview**, `AuthnRequest`/Response flow, filter chain, relying party/ACS: https://docs.spring.io/spring-security/reference/servlet/saml2/login/overview.html
- Spring Security, **Authenticating SAML Responses**, `OpenSaml5AuthenticationProvider`, `ResponseValidator`, `AssertionValidator`: https://docs.spring.io/spring-security/reference/servlet/saml2/login/authentication.html
- Spring Security, **Producing AuthnRequests**, `Saml2AuthenticationRequestRepository`, `HttpSessionSaml2AuthenticationRequestRepository`, and login fixation warning with global caches: https://docs.spring.io/spring-security/reference/servlet/saml2/login/authentication-requests.html
- Spring Security, **SAML 2.0 Relying Party Metadata**, SP entityID, ACS URL, IdP metadata: https://docs.spring.io/spring-security/reference/servlet/saml2/metadata.html
- Spring Security, **Testing Servlet Security**, distinguishing security test post-processors from end-to-end protocol validation: https://docs.spring.io/spring-security/reference/servlet/test/index.html
- Spring Security, **Session Management**, `SecurityContextRepository`, session fixation, Spring Session: https://docs.spring.io/spring-security/reference/servlet/authentication/session-management.html
- OWASP, **SAML Security Cheat Sheet**, XML signatures, recipient/audience/response correlation, and replay defenses: https://cheatsheetseries.owasp.org/cheatsheets/SAML_Security_Cheat_Sheet.html
- OWASP, **Testing for SAML**, security testing notes: https://owasp.org/www-project-web-security-testing-guide/

**Conclusion:** SAML 2.0 testing does not stop at a valid signature. **Audience** binds the assertion to the right **SP Entity ID**; **Recipient** binds bearer confirmation to the right **ACS**; **Destination** binds the **Response** to the receiving endpoint; **`InResponseTo`** binds Response and bearer confirmation to the **`AuthnRequest` created by the SP for this browser**. For tests to hold value, generate **signed negative fixtures** (mutating fields **before** re-signing), run them through the **real Spring Security SAML filter/provider**, assert no new `Authentication`/session is created, and keep default validators intact. An invalid field never becomes "valid" simply because the application found a `NameID` or the IdP's signature still checked out.