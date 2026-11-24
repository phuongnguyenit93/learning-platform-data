# Checking AudienceRestriction and SubjectConfirmation Recipient in SAML2

> **Topic:** Spring Security – federation. **Knowledge track:** SAML2 Verification. This lesson presents two independent constraints that must be understood together when a Service Provider (SP/Relying Party) receives a SAML Response from an Identity Provider (IdP/Asserting Party): **`<AudienceRestriction>` in Assertion Conditions** and **`Recipient` of bearer `<SubjectConfirmationData>`**. The primary scope is SAML 2.0 Web Browser SSO with Java 17+/Spring Security applications.

## 1. Learning Outcomes and Problem Statement

After studying this lesson, you will be able to:

1. State accurately that **AudienceRestriction restricts who may use the assertion**, whereas **Recipient specifies the ACS endpoint permitted to receive the bearer assertion**.
2. Distinguish **SP entityID**, **Assertion Consumer Service (ACS) URL**, `Response/@Destination`, `Issuer`, and `InResponseTo`; know which value must be compared against which.
3. Explain why an assertion with a **valid signature** yet wrong `Audience` or `Recipient` must be rejected.
4. Read SAML XML structure to recognize `Conditions`, `AudienceRestriction`, `SubjectConfirmation`, and `SubjectConfirmationData`; understand time, correlation, and replay constraints.
5. Know how to manage SP entityID/ACS/certificates via `RelyingPartyRegistration` in Spring Security, including behind an HTTPS reverse proxy.
6. Build **happy-path and fail-closed** tests for wrong audience, wrong recipient, wrong timestamp, response sent to another SP/tenant, and mismatched request ID.
7. Avoid common mistakes: using the ACS URL as audience, using the IdP entityID as audience, checking only hostname, modifying signed XML and drawing conclusions from a signature error, or dropping validation to work around proxy issues.

**Key takeaway:** There are three independent questions that must be answered accurately: **"Who issued it?"** (issuer + trusted signing key), **"Which application was it issued for?"** (`AudienceRestriction`), and **"Where may the bearer assertion be delivered?"** (`SubjectConfirmationData Recipient`). The IdP's signature **does not replace** the latter two checks.

## 2. Example System and Identifiers

Suppose there is one IdP and two separate web applications, each having registered a SAML integration with the IdP:

| Component | Illustrative identifier/path | Role |
| --- | --- | --- |
| **IdP** | `https://idp.example.org/issuer` | IdP `entityID`; asserts issuing source |
| **SP A** | `https://pay.example.org/saml2/service-provider-metadata/pay` | SP A `entityID`, logical identifier of the receiving application |
| **SP A's ACS** | `https://pay.example.org/login/saml2/sso/pay` | Actual URL to which the browser POSTs SP A's `SAMLResponse` |
| **SP B** | `https://hr.example.org/saml2/service-provider-metadata/hr` | SP B `entityID`, **distinct from** SP A |
| **SP B's ACS** | `https://hr.example.org/login/saml2/sso/hr` | SP B's ACS URL, **distinct from** SP A |
| **SP A's internal Spring registrationId** | `pay` | Lookup key for a `RelyingPartyRegistration`, **not entityID** |
| **SP B's internal Spring registrationId** | `hr` | Lookup key for another registration |

In your environment, `entityID` may be a URN such as `urn:company:application:pay`, **not necessarily a GET-able URL**. By default in many Spring setups, entityID is generated from `{baseUrl}/saml2/service-provider-metadata/{registrationId}`, yet it can be customized independently of the ACS. Therefore **never infer Audience from ACS or vice versa**.

### 2.1. Where Are the Two Verified Fields Located?

```text
SAML Response (browser POSTs to SP A ACS)
  |
  +-- Response/@Destination = https://pay.example.org/login/saml2/sso/pay
  +-- Response/Issuer       = https://idp.example.org/issuer
  |
  +-- Assertion (signed by IdP or nested inside signed Response)
       |
       +-- Assertion/Issuer = https://idp.example.org/issuer
       |
       +-- Subject
       |    +-- SubjectConfirmation Method="...:bearer"
       |          +-- SubjectConfirmationData
       |                Recipient    = https://pay.example.org/login/saml2/sso/pay
       |                InResponseTo = _request-123
       |                NotOnOrAfter = ... (subject confirmation expiration time)
       |
       +-- Conditions
            +-- AudienceRestriction
                  +-- Audience = https://pay.example.org/saml2/service-provider-metadata/pay
```

**Note:** `Response/@Destination` and `SubjectConfirmationData/@Recipient` are usually both the **ACS URL** in browser SSO, whereas `Audience` is the **SP entityID**, which often differs from the ACS URL. They are separate constraints and should not be collapsed into a single comparison.

### 2.2. Verification Flow

```text
(1) User visits /private on SP A
        |
(2) SP A generates AuthnRequest, stores ID _request-123 and corresponding state
        |
(3) Browser goes to IdP, user authenticates
        |
(4) IdP issues Response and Assertion for SP A
        |    Issuer            = IdP entityID
        |    Audience          = SP A entityID
        |    Recipient         = SP A ACS
        |    InResponseTo      = _request-123
        |    Validity          = still valid
        |
(5) Browser POSTs SAMLResponse to SP A ACS
        |
(6) Spring Security/OpenSAML verifies signature, issuer,
    destination, conditions, subject confirmation,
    correlation, timestamps, and applicable rules
        |
      VALID? ------- No ------> REJECT, do not create Authentication
        |
       Yes
        v
(7) Create Authentication/session at SP A; proceed with business authorization
```

If the same response is forwarded to SP B's ACS, **SP B must reject it** because the audience is intended for SP A and/or recipient/destination is not intended for SP B, even though both SPs trust the same IdP.

## 3. `AudienceRestriction`: "Which SP Is This Assertion For?"

### 3.1. Structure and Purpose

In SAML 2.0, an `Assertion`'s `Conditions` may contain one or more `AudienceRestriction` elements, and each `AudienceRestriction` contains `Audience` elements. In the Web Browser SSO bearer profile, the used assertion must have an audience restriction matching the SP. Example:

```xml
<saml:Conditions xmlns:saml="urn:oasis:names:tc:SAML:2.0:assertion"
                 NotBefore="2030-03-10T10:00:00Z"
                 NotOnOrAfter="2030-03-10T10:05:00Z">
  <saml:AudienceRestriction>
    <saml:Audience>https://pay.example.org/saml2/service-provider-metadata/pay</saml:Audience>
  </saml:AudienceRestriction>
</saml:Conditions>
```

Explanation:

- `Audience` does not describe "which user" or "which permission group"; it describes **who is permitted to consume the assertion**.
- The SP matches against **its own entityID**, registered and approved by the IdP, rather than taking an arbitrary `Host` header or tenant name self-declared by the request.
- Do not use loose string matching like `startsWith("https://pay.example.org")`, `contains("pay")`, or stripping the path. A single domain can serve multiple distinct SPs/entityIDs.
- Do not accept an audience carrying the **IdP entityID** merely because the IdP is the issuer: `Issuer` and `Audience` have different roles.
- A valid audience **does not allow** the assertion to become a bearer token for calling an arbitrary OAuth Resource Server/API. SAML browser SSO has its own criteria and endpoints.

### 3.2. OR/AND Rules When Multiple AudienceRestrictions Exist

Per SAML 2.0 and errata: **multiple `Audience` elements inside the same `AudienceRestriction` have an OR relationship**, whereas **multiple independent `AudienceRestriction` elements in the same assertion have an AND relationship** (every condition must be satisfied).

Example 1 — OR within one condition:

```xml
<saml:AudienceRestriction xmlns:saml="urn:oasis:names:tc:SAML:2.0:assertion">
  <saml:Audience>urn:example:sp:pay</saml:Audience>
  <saml:Audience>urn:example:sp:billing</saml:Audience>
</saml:AudienceRestriction>
```

If the SP entityID is `urn:example:sp:pay`, this condition passes. If the SP entityID is `urn:example:sp:hr`, this condition fails.

Example 2 — AND across two conditions:

```xml
<saml:Conditions xmlns:saml="urn:oasis:names:tc:SAML:2.0:assertion">
  <saml:AudienceRestriction>
    <saml:Audience>urn:example:sp:pay</saml:Audience>
    <saml:Audience>urn:example:sp:billing</saml:Audience>
  </saml:AudienceRestriction>
  <saml:AudienceRestriction>
    <saml:Audience>urn:example:sp:pay</saml:Audience>
  </saml:AudienceRestriction>
</saml:Conditions>
```

For SP `urn:example:sp:pay`, both conditions pass. For SP `urn:example:sp:billing`, the first condition passes yet the second fails, so **the entire audience restriction fails**. A validator that collects all audiences from every condition into one flat set and checks "contains entityID" would produce a false positive.

**Safe practice:** Let the SAML library validate conditions with proper semantics. Do not write a custom String/regex parser that grabs the first `Audience` or any matching element while ignoring other conditions.

### 3.3. What If `AudienceRestriction` Is Missing?

In the Web Browser SSO bearer profile, a bearer assertion must contain an `AudienceRestriction` holding the SP identifier. Thus, when integrating browser SSO, an assertion missing an audience restriction is a **configuration/issuance error to reject**, not an excuse to "skip because the IdP signed it". In other SAML profiles, assertion usage rules may differ; do not arbitrarily generalize from browser SSO to all cases.

If the IdP issues the wrong audience, fix the **SP Entity ID / Audience URI / Relying Party Identifier configuration at the IdP** to match the published entityID rather than changing the SP entityID to match an arbitrary assertion or removing the audience validator.

## 4. `SubjectConfirmationData Recipient`: "To Which ACS May This Bearer Assertion Be Delivered?"

### 4.1. Bearer SubjectConfirmation and Binding Data

In browser SSO, a bearer assertion must have a `SubjectConfirmation` with:

```text
Method="urn:oasis:names:tc:SAML:2.0:cm:bearer"
```

Inside, `SubjectConfirmationData` specifies the conditions under which an SP is allowed to **confirm that the bearer of the assertion is indeed the subject asserted by the IdP**. Example:

```xml
<saml:Subject xmlns:saml="urn:oasis:names:tc:SAML:2.0:assertion">
  <saml:NameID>user-42</saml:NameID>
  <saml:SubjectConfirmation
      Method="urn:oasis:names:tc:SAML:2.0:cm:bearer">
    <saml:SubjectConfirmationData
        Recipient="https://pay.example.org/login/saml2/sso/pay"
        InResponseTo="_request-123"
        NotOnOrAfter="2030-03-10T10:04:00Z"/>
  </saml:SubjectConfirmation>
</saml:Subject>
```

In the Web Browser SSO bearer profile:

- **`Recipient` must point to the exact ACS URL to which the SAML Response was delivered**, for example `https://pay.example.org/login/saml2/sso/pay`.
- **`NotOnOrAfter`** sets the expiration timestamp of bearer confirmation, a constraint separate from `Conditions` timing. Once reached, confirmation is no longer valid (subject to policy-permitted clock skew).
- **`InResponseTo`** when the response answers an `AuthnRequest` must match the ID of the request initiated and tracked by the SP. For unsolicited/IdP-initiated SSO per profile, this constraint must be absent; the receiver must have an explicit policy on whether unsolicited flows are accepted.
- **`Address`**, if sent by the IdP, can restrict the browser's IP address; understand NAT/proxy limitations and validation behavior per profile. Do not treat it as a replacement for Recipient/audience.
- For **bearer Web Browser SSO**, `SubjectConfirmationData` must not use `NotBefore` per profile; distinguish this from a valid `Conditions/NotBefore` in the assertion.
- There may be **multiple** `SubjectConfirmation` elements. The SP must find at least one valid bearer confirmation per profile and independently verify its conditions; never combine part of confirmation A with part of confirmation B into an "imaginary" confirmation.

**Subtlety:** `Recipient` is not a generic "domain whitelist". `https://pay.example.org/login/saml2/sso/pay` differs from `https://pay.example.org/other`, from `http://pay.example.org/login/saml2/sso/pay`, and from another tenant's ACS. Checking only hostname or path prefix will miss misdirected deliveries.

### 4.2. What Is Recipient Matched Against?

Do not match `Recipient` against:

- IdP `entityID`.
- `AudienceRestriction/Audience`.
- SP's login initiation URL `/saml2/authenticate/{registrationId}` (where AuthnRequest **starts**).
- SP's metadata URL `/saml2/metadata/{registrationId}`, unless the app accidentally uses a non-standard ACS config overlapping that URL (discouraged).
- Unverified `Referer`/`Origin` headers or raw `Host` from the browser.

Match against the **actual/registered ACS URL** served by the SP for that exact RP registration and SAML Response route. In Spring Security, the corresponding concept is `RelyingPartyRegistration.getAssertionConsumerServiceLocation()` after resolving the deployment URL value, used by the provider/validator.

With multiple valid ACSs/bindings, selecting which ACS received the response must bind to the registration, binding, and IdP contract; do not "allow if Recipient matches any URL anywhere in the system". Each tenant/SP must be restricted to its own approved ACSs.

### 4.3. Why Must Both Audience and Recipient Be Checked?

A multi-SP system sharing an IdP faces **cross-service assertion replay**: an attacker tries to forward a SAMLResponse issued for SP A to SP B. Checking only the IdP signature still passes cryptographically. Checking only Audience can still allow routing errors to the wrong ACS of the same SP/tenant or misrouting. Checking only Recipient could miss assertions not intended for the application's own entityID.

The right conclusion must be the **AND of independent properties**, not choosing "Audience **or** Recipient".

## 5. Four Easily Confused Fields: Issuer, Audience, Destination, Recipient

| SAML field | Location | Value expected by SP A | Security question |
| --- | --- | --- | --- |
| **Issuer** | `Response/Issuer` and `Assertion/Issuer` | `https://idp.example.org/issuer`, belonging to configured IdP | From which issuer does the evidence originate? |
| **Audience** | `Assertion/Conditions/AudienceRestriction/Audience` | `https://pay.example.org/saml2/service-provider-metadata/pay` | For which SP entityID is this Assertion issued? |
| **Destination** | `Response/@Destination` | `https://pay.example.org/login/saml2/sso/pay` | To which address was the entire SAML Response directed? |
| **Recipient** | `Assertion/Subject/SubjectConfirmation/SubjectConfirmationData/@Recipient` | `https://pay.example.org/login/saml2/sso/pay` | At which ACS URL may the bearer assertion be confirmed? |
| **InResponseTo** | `Response/@InResponseTo` and `SubjectConfirmationData/@InResponseTo` when applicable | `_request-123` issued and stored | Is this the reply to the current session's AuthnRequest? |
| **NotOnOrAfter** | `Conditions` and `SubjectConfirmationData` (two separate locations) | In the future relative to receipt time within skew policy | Are the Assertion and bearer confirmation still valid? |

**Issuer is the issuing party**, **Audience is the SP identifier**, **Destination and Recipient are ACS URLs**. In typical cases Destination and Recipient match, yet their matching does not make either check redundant: they apply at different message and subject-confirmation layers.

**XML signature warning:** Extracting a field from XML whose signature has not been verified, then matching the string accurately, does not prove the IdP actually asserted that field. You must verify a valid signature **covering the exact assertion/response content the application consumes**, avoiding XML signature wrapping and wrong-element selection. Spring Security integrates OpenSAML to handle this; never Base64-decode to XML yourself and trust fields merely because they look right.

## 6. Composite SAML Response Structure for Learning Cross-Checks

The snippet below is **illustrative material, NOT a valid SAMLResponse for logging in**: it omits `ds:Signature`, full attribute/protocol elements, and trusted credentials. Its purpose is to show where each field resides.

```xml
<samlp:Response
    xmlns:samlp="urn:oasis:names:tc:SAML:2.0:protocol"
    xmlns:saml="urn:oasis:names:tc:SAML:2.0:assertion"
    ID="_response-10"
    Version="2.0"
    IssueInstant="2030-03-10T10:00:00Z"
    InResponseTo="_request-123"
    Destination="https://pay.example.org/login/saml2/sso/pay">
  <saml:Issuer>https://idp.example.org/issuer</saml:Issuer>
  <samlp:Status>
    <samlp:StatusCode
        Value="urn:oasis:names:tc:SAML:2.0:status:Success"/>
  </samlp:Status>
  <saml:Assertion
      ID="_assertion-20"
      Version="2.0"
      IssueInstant="2030-03-10T10:00:00Z">
    <saml:Issuer>https://idp.example.org/issuer</saml:Issuer>
    <saml:Subject>
      <saml:NameID>user-42</saml:NameID>
      <saml:SubjectConfirmation
          Method="urn:oasis:names:tc:SAML:2.0:cm:bearer">
        <saml:SubjectConfirmationData
            Recipient="https://pay.example.org/login/saml2/sso/pay"
            InResponseTo="_request-123"
            NotOnOrAfter="2030-03-10T10:04:00Z"/>
      </saml:SubjectConfirmation>
    </saml:Subject>
    <saml:Conditions
        NotBefore="2030-03-10T09:59:00Z"
        NotOnOrAfter="2030-03-10T10:05:00Z">
      <saml:AudienceRestriction>
        <saml:Audience>https://pay.example.org/saml2/service-provider-metadata/pay</saml:Audience>
      </saml:AudienceRestriction>
    </saml:Conditions>
    <saml:AuthnStatement
        AuthnInstant="2030-03-10T10:00:00Z"/>
  </saml:Assertion>
</samlp:Response>
```

Using the illustrative values above at `2030-03-10T10:01:00Z`, assuming IdP/signing key/state/correlation are all valid and other conditions pass, the two primary matches are:

```text
expectedAudience =
  "https://pay.example.org/saml2/service-provider-metadata/pay"
actualAudience =
  "https://pay.example.org/saml2/service-provider-metadata/pay"
=> match

expectedACS =
  "https://pay.example.org/login/saml2/sso/pay"
actualRecipient =
  "https://pay.example.org/login/saml2/sso/pay"
=> match

actualDestination =
  "https://pay.example.org/login/saml2/sso/pay"
=> matches ACS

actualInResponseTo = "_request-123"
=> matches saved AuthnRequest ID
```

Do not submit the XML snippet above to an ACS to test login: it lacks a signature and required elements; Spring must reject it. To verify **specifically audience/recipient**, you need an assertion **validly signed by a test IdP**, changing only the target claim/URL and re-signing.

## 7. What Does Spring Security Verify and Where?

### 7.1. Default Processing Path

In Spring Security SAML2 Servlet Web SSO:

1. `Saml2WebSsoAuthenticationRequestFilter` initiates `AuthnRequest` at the corresponding URL, e.g. `/saml2/authenticate/pay`, and saves correlation per configuration.
2. Browser authenticates at the IdP and POSTs `SAMLResponse` to ACS `/login/saml2/sso/pay`.
3. `Saml2WebSsoAuthenticationFilter` processes the request, creates `Saml2AuthenticationToken`, and resolves `RelyingPartyRegistration`.
4. The OpenSAML-based authentication provider verifies signatures, issuer, destination, assertion conditions (including audience restriction), subject confirmation, and applicable rules. Any validation failure fails authentication.
5. Only upon successful authentication are `SecurityContext`/session established; controllers and business authorization proceed.

OpenSAML provider class names and customization APIs can differ across Spring Security 6.x, 7.x, and dependency setups; consult documentation for the **exact version in use**. This lesson does not replace default validators with custom-written logic: SAML verification is a critical security function best handled by the framework and OpenSAML per standards.

### 7.2. Configuring SP entityID and ACS in Spring Boot

Assuming Java 17+, a compatible Spring Boot servlet stack, the `spring-security-saml2-service-provider` dependency, and an approved test IdP. File `src/main/resources/application.yml`:

```yaml
spring:
  security:
    saml2:
      relyingparty:
        registration:
          pay:
            entity-id: "https://pay.example.org/saml2/service-provider-metadata/pay"
            assertion-consumer-service-location: "https://pay.example.org/login/saml2/sso/pay"
            assertingparty:
              entity-id: "https://idp.example.org/issuer"
              verification:
                credentials:
                  - certificate-location: "classpath:saml/idp-signing.crt"
              singlesignon:
                url: "https://idp.example.org/saml/sso"
                sign-request: false
```

**Security explanation:**

- `registration.pay` creates the internal identifier key `pay`.
- `entity-id` is the **SP entityID**. The IdP must issue `AudienceRestriction/Audience` matching this value.
- `assertion-consumer-service-location` is the **HTTPS ACS address**. The IdP must send `SAMLResponse` here and set `SubjectConfirmationData Recipient`/`Response Destination` accordingly.
- `assertingparty.entity-id` is the **IdP entityID**; do not put it into `Audience` of an assertion meant for the SP.
- `verification.credentials.certificate-location` supplies the **IdP's public certificate** to verify SAML signatures; the file must be a real vetted certificate from the IdP, not a certificate crafted by copying from a user-submitted assertion.
- `singlesignon.url` is the IdP endpoint that **receives AuthnRequest**, not the SP's ACS.
- `sign-request: false` only illustrates a test IdP allowing unsigned AuthnRequests. When a partner requires signing, use SP signing credentials and proper signing config; do not weaken signing policy to sidestep audience/recipient errors.

**`example.org` domains are illustrative addresses**; to run for real you must substitute your test IdP, SP FQDN, certificate, and registered ACS. Running this exact config on `localhost` without matching DNS/TLS will fail; that is an environment/registration issue, not a reason to disable audience validation.

### 7.3. Enabling the Proper Filter Chain

File `src/main/java/com/example/saml/SamlSecurityConfig.java`:

```java
package com.example.saml;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class SamlSecurityConfig {

    @Bean
    SecurityFilterChain web(HttpSecurity http) throws Exception {
        return http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers(HttpMethod.GET,
                    "/", "/login", "/error",
                    "/saml2/authenticate/**",
                    "/saml2/metadata",
                    "/saml2/metadata/**",
                    "/saml2/service-provider-metadata/**").permitAll()
                .requestMatchers(HttpMethod.POST,
                    "/login/saml2/sso",
                    "/login/saml2/sso/**").permitAll()
                .requestMatchers("/admin/**").hasRole("ADMIN")
                .anyRequest().authenticated())
            .saml2Login(Customizer.withDefaults())
            .saml2Metadata(Customizer.withDefaults())
            .build();
    }
}
```

This is a **Spring Boot project class with relevant dependencies**, not a standalone Java program runnable via `javac` without Maven/Gradle and an application context. `saml2Login` ensures the ACS passes through the SAML filter, while `saml2Metadata` publishes SP metadata per configuration.

`permitAll` for POST ACS only lets a **sessionless** browser deliver the response to the filter; it **does not bypass** signature, AudienceRestriction, or Recipient checks. Do not use `web.ignoring("/login/saml2/sso/**")` or write a controller that Base64-decodes `SAMLResponse` to create a session. If the app has multiple `SecurityFilterChain` beans, ensure the ACS is actually handled by the SAML chain.

The integration library typically configures a **narrow CSRF exception for the SAML ACS**; do not disable CSRF across the entire web application to fix a 403 error. For web apps using session cookies, business POST endpoints must remain CSRF-protected.

### 7.4. Using SP Metadata Itself as the Reference Source

When `saml2Metadata` is enabled, inspect the SP metadata served at the corresponding endpoint, for example:

```text
https://pay.example.org/saml2/metadata/pay
```

In the SP metadata XML, inspect `EntityDescriptor/@entityID` and `SPSSODescriptor/AssertionConsumerService/@Location`. Then match them exactly against the **Entity ID/Audience URI** and **ACS URL/Reply URL** registered at the IdP.

`entityID` is for Audience, while `AssertionConsumerService Location` is for Recipient/Destination. Do not merely look at a provider UI field labeled "URL" and pick the wrong one: each vendor UI names fields differently. Record both values in integration docs and re-verify after every URL, proxy, or tenant change.

## 8. Why Do Reverse Proxies and Multi-Environment Setups Cause Errors Easily?

### 8.1. Wrong `{baseUrl}` When TLS Terminates at a Gateway

For example, the browser uses:

```text
https://pay.example.org/login/saml2/sso/pay
```

Yet Spring Boot runs behind an ingress at an internal address:

```text
http://pay-service:8080/login/saml2/sso/pay
```

If Spring-generated metadata/ACS derives from the wrong scheme/host/port, it can emit a `Recipient`/`Destination` that mismatches the public URL. Fix this **in canonical URL and reverse proxy configuration**, not by editing signed XML or disabling Recipient checks.

Control steps:

1. Publish a stable SP entityID and an HTTPS ACS URL with the right FQDN.
2. Configure the ingress/proxy to pass accurate host/proto info, strip client-supplied forwarded headers, and allow the backend to trust only approved proxies. With Spring Boot, check how `server.forward-headers-strategy` matches your topology.
3. You can set `entity-id` and `assertion-consumer-service-location` explicitly as in the example so they do not drift from request origin; still ensure actual routing delivers POSTs to the right ACS/filter.
4. Inspect metadata **after deployment**, not just the local YAML file.
5. Do not perform raw comparisons against `request.getRequestURL()` if the backend request was rewritten or carries a spoofed Host. The validator must rely on approved RP/ACS config and a trusted request context.
6. If the IdP issues a response to an internal HTTP URL instead of public HTTPS, fix the IdP/ACS config. **Never** add the HTTP URL to allowed recipients just to "make it work".

### 8.2. Errors from Slashes, Ports, or Paths

These strings may look similar yet are **not equivalent** for protocol/registration:

```text
https://pay.example.org/login/saml2/sso/pay
https://pay.example.org/login/saml2/sso/pay/
https://pay.example.org:8443/login/saml2/sso/pay
https://pay.example.org/saml2/sso/pay
http://pay.example.org/login/saml2/sso/pay
```

Do not manually `trim`, lowercase the entire URL (including path), drop slashes, strip ports, or rewrite schemes during SAML verification. URL strings must conform to metadata, message values, and the validator's matching rules per profile and policy. Behind a reverse proxy, fix the **authoritative configuration source** so all parties stay consistent.

### 8.3. Multi-Tenant / Multiple Registrations

If an application hosts multiple tenants and each tenant has its own RP entityID:

- Each tenant's `registrationId` must resolve to the exact right `RelyingPartyRegistration`.
- Tenant A's SP entityID and ACS must never automatically become valid audiences/recipients for tenant B.
- Never determine token trust purely from a query parameter, raw `Host`, or unverified SAML `Issuer`.
- Before authenticating, the SP must securely resolve the registration using the framework's mechanism, then **bind audience, recipient, IdP issuer, and certificate checks to that registration**.
- If tenants share an ACS path, you need a trusted tenant/registration resolution mechanism with matching audience/correlation scoping; never accept a SAMLResponse from another tenant merely because the ACS hostname matches.
- An IdP may issue an assertion listing multiple `Audience` values, yet the receiver must not assume that grants cross-tenant authorization. Tenant boundaries and authorizations still must be enforced separately.

**Warning scenario:** A user from SP A forwards a `SAMLResponse` to SP B, both trusting the same IdP certificate. If SP B only runs `verifySignature` and creates a session from `NameID`, that is a critical vulnerability. `AudienceRestriction` and `Recipient` are two mandatory layers preventing cross-target acceptance.

## 9. Time, InResponseTo, and Replay: Cannot Be Separated from Recipient

### 9.1. Two Independent Validity Windows

`Conditions/@NotBefore` and `Conditions/@NotOnOrAfter` bound the validity **of the assertion**. Meanwhile, `SubjectConfirmationData/@NotOnOrAfter` bounds when the **bearer subject may be confirmed**. An assertion not yet expired under `Conditions` can still be unacceptable if SubjectConfirmationData has expired.

Example:

```text
Conditions:
  NotBefore       = 10:00:00 UTC
  NotOnOrAfter    = 10:10:00 UTC

SubjectConfirmationData:
  Recipient       = https://pay.example.org/login/saml2/sso/pay
  NotOnOrAfter    = 10:03:00 UTC

SP receives at   = 10:04:00 UTC
=> Conditions is still valid, BUT bearer confirmation has expired
=> Must not use this subject confirmation
```

Clock drift between IdP/SP can make a freshly issued request look "expired" or "not yet valid". Synchronize NTP across IdP, SP, and reverse proxy. Clock-skew allowance must be small and policy-governed, not a substitute for fixing clocks or dropping `NotOnOrAfter` checks.

### 9.2. `InResponseTo` and Limits on IdP-Initiated SSO

In SP-initiated SSO, the IdP replies to the initiated AuthnRequest. `InResponseTo` on the response and bearer confirmation (when applicable) must bind to a still-valid request ID stored by the SP. If the ID mismatches or the request was already consumed, reject; **a valid Recipient does not compensate for a wrong InResponseTo**.

With IdP-initiated (unsolicited) SSO, the profile has no AuthnRequest to correlate; handling policies differ and protecting against login CSRF/replay is harder. Enable only if required and risk-assessed; never disable `InResponseTo` checks across all flows to fix session-induced SSO errors. If a response claims to be unsolicited yet carries an `InResponseTo` violating profile rules, handle per profile rather than silently ignoring it.

### 9.3. Replay Cache

A short-lived bearer assertion can still be replayed by someone who obtains the SAMLResponse (if able to bypass other controls). The SP must track Message ID/Assertion ID, request state, and replay protection per profile/implementation. Never store raw assertions in logs, never expose ACS over HTTP; use HTTPS, protect session cookies, and ensure single-use state is consistent across cluster nodes.

**An ID Token/OAuth Access Token cannot substitute for SAML assertion verification:** goals and protection models differ. An OAuth2 Resource Server checks issuer/audience of an access token for APIs; a SAML2 SP checks issuer, AudienceRestriction, Recipient, Destination, subject confirmation, and correlation per SAML.

## 10. Standalone Java 17 Example to Understand Matching Rules

The following example **only demonstrates conditional logic assuming the info was already parsed, signature-verified, and message-identified by a trusted SAML validator**. It **does not parse XML, check signatures, or perform real SAML validation** and must strictly **never replace Spring Security/OpenSAML in production**.

File `SamlBoundaryDemo.java`, runnable on JDK 17+ without external libraries:

```java
import java.time.Instant;
import java.util.List;
import java.util.Set;

public class SamlBoundaryDemo {

    record BearerConfirmation(
            String recipient,
            Instant notOnOrAfter,
            String inResponseTo) { }

    // Assume each Set represents one AudienceRestriction;
    // Sets in the List are multiple independent restrictions.
    static boolean matchesForLearning(
            List<Set<String>> audienceRestrictions,
            List<BearerConfirmation> bearerConfirmations,
            String expectedEntityId,
            String expectedAcs,
            String expectedRequestId,
            Instant receivedAt) {

        // Browser SSO: must have at least one audience restriction.
        boolean audienceValid = !audienceRestrictions.isEmpty()
            && audienceRestrictions.stream()
                .allMatch(group -> group.contains(expectedEntityId));

        // Each bearer confirmation must satisfy ALL constraints.
        boolean subjectValid = bearerConfirmations.stream()
            .anyMatch(confirmation ->
                expectedAcs.equals(confirmation.recipient())
                && receivedAt.isBefore(confirmation.notOnOrAfter())
                && expectedRequestId.equals(confirmation.inResponseTo()));

        return audienceValid && subjectValid;
    }

    public static void main(String[] args) {
        String entityId = "urn:example:sp:pay";
        String acs = "https://pay.example.org/login/saml2/sso/pay";
        String requestId = "_request-123";
        Instant now = Instant.parse("2030-03-10T10:01:00Z");

        List<Set<String>> validAudience =
            List.of(Set.of(entityId, "urn:example:sp:billing"),
                    Set.of(entityId));

        List<BearerConfirmation> validBearer =
            List.of(new BearerConfirmation(
                acs, now.plusSeconds(60), requestId));

        System.out.println("valid=" + matchesForLearning(
            validAudience, validBearer,
            entityId, acs, requestId, now));

        System.out.println("wrongSecondAudience=" + matchesForLearning(
            List.of(Set.of(entityId),
                    Set.of("urn:example:sp:hr")),
            validBearer, entityId, acs, requestId, now));

        System.out.println("wrongRecipient=" + matchesForLearning(
            validAudience,
            List.of(new BearerConfirmation(
                "https://hr.example.org/login/saml2/sso/hr",
                now.plusSeconds(60), requestId)),
            entityId, acs, requestId, now));

        System.out.println("expiredBearer=" + matchesForLearning(
            validAudience,
            List.of(new BearerConfirmation(
                acs, now.minusSeconds(1), requestId)),
            entityId, acs, requestId, now));

        System.out.println("wrongRequestId=" + matchesForLearning(
            validAudience,
            List.of(new BearerConfirmation(
                acs, now.plusSeconds(60), "_other-request")),
            entityId, acs, requestId, now));
    }
}
```

Compile and run:

```bash
javac --release 17 SamlBoundaryDemo.java
java SamlBoundaryDemo
```

Deterministic stdout (independent of machine clock because `now` is fixed):

```text
valid=true
wrongSecondAudience=false
wrongRecipient=false
expiredBearer=false
wrongRequestId=false
```

**What it accurately models:** `Audience` elements inside one `AudienceRestriction` use OR, multiple restrictions use AND; properties of a bearer confirmation must hold together; multiple confirmations (filtered by valid Method) can succeed if one confirmation meets all conditions. **What the example intentionally omits:** XML Signature, canonicalization, `Issuer`, `Response Destination`, `Conditions NotBefore/NotOnOrAfter`, replay, trust keys, SAML processing profiles, metadata refresh, and extensions. Thus `true` only means **this small logic exercise passed**, not that a SAMLResponse was authenticated.

## 11. Writing Diagnostic Integration Tests

To genuinely test Audience/Recipient, set up a **test IdP with a registered signing cert** and configure an HTTPS test SP with fixed entityID/ACS. Change **assertion-issuance settings on the test IdP** to create negative cases, or use SAML fixtures re-signed with **test keys trusted by the SP under test**. Never take a validly signed SAMLResponse and edit the raw XML string: the signature will break first, so the test only proves "signature invalid" rather than proving the Audience/Recipient validator works.

### 11.1. Mandatory Test Matrix

| Test case | Validly signed SAML input from test IdP | What SP must do |
| --- | --- | --- |
| **Happy path** | Audience = SP entityID, Recipient = ACS, Destination = ACS, right request ID, valid times | Log in, create Authentication/session for right SP |
| **Audience for wrong SP** | Audience = `urn:example:sp:hr` while SP entityID = `urn:example:sp:pay` | **Reject**, create no session |
| **Audience confused with ACS URL** | Audience = `https://pay.example.org/login/saml2/sso/pay` while SP entityID differs | Reject; fix claim at IdP instead of altering validator |
| **Audience with two options in one condition** | One `AudienceRestriction` containing SP entityID and another entityID | Condition can pass for SP if all other checks pass |
| **Two independent AudienceRestrictions, only one matches** | Restriction A contains SP entityID, restriction B does not | Reject due to AND across restrictions |
| **Missing AudienceRestriction** | Bearer assertion in Web Browser SSO has no audience condition | Reject |
| **Recipient sent to SP B** | Recipient = SP B's ACS, all other fields still for SP A | Reject |
| **Recipient differs only in slash/port/scheme** | Recipient diverges from active ACS URL | Reject; do not ignore URL mismatch |
| **Wrong Destination but right Recipient** | Response Destination does not match ACS URL | Reject per message destination validation |
| **Right Recipient but wrong Audience** | One constraint passes, one fails | Reject: the two layers are ANDed |
| **Right Audience but wrong Recipient** | Reverse of above case | Reject |
| **Expired bearer** | SubjectConfirmationData NotOnOrAfter passed, Conditions still valid | Reject if no other valid confirmation exists |
| **Expired Conditions** | Conditions NotOnOrAfter passed, bearer still valid | Reject |
| **Wrong InResponseTo** | Re-signed; ID mismatches pending AuthnRequest | Reject |
| **Replay same Assertion ID/Response** | Re-submit already consumed response where replay protection applies | Reject per policy, create no new session |
| **Wrong IdP signing key** | Assertion signed by another source, even if Audience/Recipient match | Reject before trusting claims |
| **Multiple confirmations** | One invalid confirmation, one bearer confirmation meeting all conditions | Handle per profile/validator rules: confirm only if an **independent** confirmation is completely valid |
| **Tenant A vs tenant B** | SP A entityID, tenant B's ACS or vice versa | Reject, no cross-tenant session |
| **Proxy publishes wrong host in metadata** | IdP issues to HTTP/internal ACS instead of public HTTPS | Reject; fix SP metadata/IdP config/trusted proxy |

**Testing order:** Change only **one** variable at a time on the test IdP; keep issuer, signing, time window, request correlation, and routing valid to isolate the cause. If you alter multiple variables at once, a failure does not prove which validator rejected it.

### 11.2. Inspecting Responses Over the Network Without Leaking Data

Using browser DevTools Network in a test environment:

1. Visit a protected SP URL and let Spring generate `AuthnRequest`.
2. Confirm the browser reaches the right registration's IdP; after login, POST `SAMLResponse` to the right HTTPS ACS.
3. Check **endpoint path, HTTP method, status/redirect, and cookie behavior**; do not copy raw `SAMLResponse`, `RelayState`, cookies, or private keys into issue trackers.
4. If login succeeds, confirm `SecurityContext` holds `Saml2Authentication` for the right SP and business endpoints remain authorized.
5. For negative cases, confirm **no authenticated session is created** (even with an HTTP 302 to login); do not inspect HTTP status alone.
6. Enable controlled debug logging in test with sensitive data masked; cross-check audience, subject confirmation, recipient, issuer, destination, or request correlation errors.
7. Test behavior across two tabs/browser sessions, clustered sessions, and IdP-initiated flows (if supported). This catches cases where `InResponseTo` binds to the wrong state.

**Never log raw `SAMLResponse` or Assertion XML in production:** XML may contain NameID, email, HR attributes, session info, and other personal data. Logs should retain issuer/registrationId, correlation code, error category, timestamp, and outcome, without secrets.

## 12. Real-World Troubleshooting

| Symptom | Likely cause | How to verify/fix |
| --- | --- | --- |
| `AudienceRestriction` mismatch | IdP set wrong SP identifier, used ACS as audience, staging/prod entityID mix-up | Compare SP metadata `EntityDescriptor/@entityID` against IdP's Audience URI/Relying Party Identifier |
| `Recipient` mismatch | IdP registered ACS with wrong scheme/host/path/port, reverse proxy rewrite, multi-tenant | Compare SP metadata ACS, actual browser POST URL, and `SubjectConfirmationData/@Recipient` in a valid test fixture |
| Audience matches yet Recipient fails | Assertion has right SP audience yet delivered to another ACS | Do not remove Recipient validator; fix ACS/binding/IdP |
| Recipient matches yet Audience fails | IdP issued claims for another SP/entityID | Do not remove AudienceRestriction validator; fix issuer registration |
| `Destination` mismatch | Response/@Destination points to another endpoint or SP received via alias | Fix canonical ACS and configuration on both sides; do not edit signed XML |
| "Assertion has expired" right at login | IdP/SP clock drift, expired `Conditions` or `SubjectConfirmationData` | Sync NTP/UTC, compare each time window, check reasonable clock skew |
| `InResponseTo` mismatch | Lost HttpSession, SP did not save request, session affinity/SameSite, wrong tab/tenant | Check request repository, HTTPS/SameSite cookies, cluster session, and binding |
| Valid signature yet SP still errors | Audience, Recipient, Destination, Issuer, time, replay, or other policy failed | Inspect validator error type instead of disabling other checks |
| "Hostname-only" check passes | Custom validator compares prefix/host instead of exact ID/ACS | Remove custom acceptance logic, use SAML library and regression tests |
| Localhost SSO works yet production fails | `{baseUrl}`/proxy headers, different public entityID or ACS | Fix canonical URLs, configure forwarded headers from trusted proxies only, and inspect live SP metadata |
| Receives another tenant's response | Repository resolves wrong registration, multiple SPs share cert/ACS | Bind registration with issuer + audience + recipient + request correlation for the right tenant |
| Login fails after certificate/metadata change | IdP/SP hold stale trust keys, unsynchronized issuer/entityID/ACS changes | Execute planned rollover, review metadata diff, never drop signature validation |
| ACS POST blocked with 403 CSRF | Filter chain/ACS URL altered, CSRF exception mismatch | Check SAML chain and ACS matcher; do not disable CSRF site-wide |

**Prioritized diagnostic workflow:**

```text
1. Did SAMLResponse reach the right HTTPS ACS and right SecurityFilterChain?
2. Is the IdP configured with trusted entityID/signing certificate?
3. Does the signature protect the exact processed message/assertion?
4. Does Assertion/Conditions/AudienceRestriction contain the SP entityID?
5. Does Bearer SubjectConfirmationData/Recipient match the receiving ACS?
6. Does Response/Destination match ACS? Does InResponseTo match the request?
7. Are Conditions and bearer expiration still valid? Was ID replayed?
8. After authentication, are session and business authorization correct?
```

## 13. Assumptions That Must Never Reach Production

**Never write logic like this:**

```java
// Illustrative anti-pattern; strictly never use as a SAML validator.
if (xml.contains("pay.example.org")) {
    loginUser();
}
```

It skips signature/issuer checks, fails to distinguish Audience/Recipient/Destination, and is vulnerable to XML signature wrapping and strings appearing in unauthorized elements. Also reject requests like "turn off AudienceRestriction validator so SSO works", "drop Recipient because IdP doesn't send it", or "add every URL under the same domain to accepted recipients".

Validator changes must be made **only for an assessed special profile requirement**, still protecting mandatory SAML constraints and backed by full negative/positive test suites. When integrating a misconfigured IdP, prioritize fixing it accurately at the IdP/registration/metadata; never lower SP security.

## 14. Practice Questions and Answers

**Q1.** An assertion signed by a trusted IdP has `AudienceRestriction` containing SP A's entityID, yet the browser POSTs to SP B's ACS. Should SP B accept it because the signature is valid?

**Answer:** **No**. The signature only verifies origin/integrity; the assertion is not intended for SP B. Audience and Recipient/Destination must match SP B/SP B's ACS along with the other checks.

**Q2.** The IdP sends `Audience` as `https://pay.example.org/login/saml2/sso/pay` while the SP `entityID` is `https://pay.example.org/saml2/service-provider-metadata/pay`. Both URLs share the same host; is this valid?

**Answer:** **No** with this configuration. Audience must match the **SP entityID**, not the ACS URL. Fix the Audience/Entity ID registered at the IdP.

**Q3.** There are two `AudienceRestriction` elements: the first contains `urn:sp:pay`, and the second contains only `urn:sp:hr`. The SP entityID is `urn:sp:pay`. Does it pass?

**Answer:** No. Audience elements inside one restriction are ORed, yet multiple restrictions are ANDed. The second restriction does not match, so it fails.

**Q4.** `Conditions/NotOnOrAfter` has 5 minutes left, yet `SubjectConfirmationData/NotOnOrAfter` expired 1 minute ago. Recipient matches; should login be allowed?

**Answer:** An expired subject confirmation cannot be used; unless another valid confirmation exists per profile, it must be rejected. Check both independent bounds and synchronize clocks.

**Q5.** An SP behind a proxy sees an internal HTTP URL, while the IdP issues a public HTTPS Recipient. Should you drop the Recipient check or fix the proxy/config?

**Answer:** Fix the canonical HTTPS ACS, metadata, host/proto forwarding from trusted proxies, and IdP registration. Never drop Recipient/Destination validation.

**Q6.** You alter one character in `Audience` of a signed SAMLResponse and re-POST it; Spring reports "invalid signature". Does this prove the audience validator rejected it?

**Answer:** No. Once the signature is broken, audience validation is not isolated. Use a test IdP to issue/register a wrong audience and **validly re-sign** with a test key trusted by the SP, or use integration fixtures built by a proper SAML test harness.

## 15. Acceptance Checklist

- [ ] SP entityID and HTTPS ACS are explicitly declared, appearing identically in SP metadata and IdP registration.
- [ ] IdP `entityID` and public signing certificate are verified from a trusted source.
- [ ] `AudienceRestriction` contains the SP entityID following OR within one restriction / AND across multiple restrictions.
- [ ] Bearer `SubjectConfirmationData Recipient` matches the ACS of the registration and incoming message; never match only host/path prefix.
- [ ] `Response Destination`, `InResponseTo` (when applicable), `Conditions`, bearer expiry, signature, and replay are verified independently.
- [ ] Do not accept assertions from another SP/tenant solely because the IdP is shared.
- [ ] Never write a custom XML validator or remove audience/recipient checks in Spring Security.
- [ ] Reverse proxy/forwarded headers/HTTPS host are trusted and consistently configured; live metadata has been inspected.
- [ ] Negative tests are **validly** issued/signed to isolate audience/recipient rather than merely breaking signatures by editing raw XML.
- [ ] Clock skew, session correlation, multiple bearer confirmations, multiple restrictions, and SAMLResponse replay have been tested.
- [ ] Logs never store raw assertions, sensitive NameIDs, session cookies, or private keys.

**Conclusion:** `AudienceRestriction` answers **"Which SP entityID is the Assertion for?"**; `SubjectConfirmationData Recipient` answers **"At which ACS URL may this bearer assertion be confirmed?"**. In browser SSO, both must match, alongside signature/issuer, `Response Destination`, timestamps, `InResponseTo`, and anti-replay. With Spring Security, the right solution is configuring RP `entityId`/`assertionConsumerServiceLocation` consistently with the IdP and letting OpenSAML validate fully, **never lowering verification to mask configuration errors**.

## 16. Official References

- [OASIS SAML 2.0 Core — Assertions and Protocols](https://docs.oasis-open.org/security/saml/v2.0/saml-core-2.0-os.pdf): `Conditions`, `AudienceRestriction`, `SubjectConfirmation`, `SubjectConfirmationData`.
- [OASIS SAML 2.0 Profiles](https://docs.oasis-open.org/security/saml/v2.0/saml-profiles-2.0-os.pdf): Web Browser SSO bearer confirmation, `Recipient`, `NotOnOrAfter`, `InResponseTo`.
- [OASIS SAML Errata 05](https://docs.oasis-open.org/security/saml/v2.0/errata05/os/saml-v2.0-errata05-os.html): clarifies OR/AND semantics of `AudienceRestriction` and bearer profile requirements.
- [Spring Security — SAML 2.0 Login Overview](https://docs.spring.io/spring-security/reference/servlet/saml2/login/overview.html): `RelyingPartyRegistration`, ACS, and OpenSAML flow verifying assertion conditions.
- [Spring Security — SAML 2.0 Metadata](https://docs.spring.io/spring-security/reference/servlet/saml2/metadata.html): publishing SP metadata to cross-check `entityID`/ACS.
- [Spring Security — Authorization](https://docs.spring.io/spring-security/reference/servlet/authorization/authorize-http-requests.html): protecting business paths after authentication.
