# Service Provider and Identity Provider Entity IDs in SAML 2.0

## 1. Purpose and Context

In **SAML 2.0 federation**, a business application usually acts as a **Service Provider (SP)**: the application needs to know which identity provider to trust. The centralized login system acts as the **Identity Provider (IdP)**: it needs to know which application is requesting login and is permitted to receive authentication results.

SAML identifies each party with an **Entity ID**. The two Entity IDs are part of the trust contract between SP and IdP. When declared incorrectly, the configuration may look valid and the user may even log in successfully at the IdP, yet the SP still cannot accept the SAML Response or the IdP does not recognize the AuthnRequest.

This lesson explains:

- What SP and IdP Entity IDs are, how they differ, and why exact values must be used.
- Where Entity IDs appear in **SAML metadata, AuthnRequest, Response, and Assertion**.
- How to distinguish an Entity ID from an **ACS URL, SSO URL, metadata URL, registrationId, and NameID**.
- How to cross-check configurations on both sides in Spring Security SAML 2.0.
- Trust boundaries, misconfiguration scenarios, principles for changing Entity IDs, and how to test.

Examples throughout use the `example.test` domain and hypothetical URNs for learning structure; they do not represent a live provider.

## 2. What Is an Entity ID?

An **Entity ID** is the identifier of a **SAML entity** (a participating party in the federation), expressed via the `entityID` attribute on the `<EntityDescriptor>` metadata element. Its value is a URI, such as:

```text
SP Entity ID  = urn:example:shop:orders:sp
IdP Entity ID = https://idp.example.test/saml/issuer
```

In the example:

- `urn:example:shop:orders:sp` represents the **orders application** when participating in SAML as an SP.
- `https://idp.example.test/saml/issuer` represents the **identity server** when issuing SAML messages or assertions.
- **The two values are not two names for the same object**. Each role must be declared properly.

An Entity ID is a **logical identifier**. It is not automatically an HTTP address that a browser must call. A URL-shaped Entity ID might not even be reachable via a browser; a `urn:` URI is certainly not a web endpoint. The actual service endpoints that send/receive SAML messages are declared **separately** in metadata using `Location` and corresponding bindings.

Because it is a contractual identifier, the SP and IdP must agree on the **exact Entity ID string**. Differences such as a trailing `/`, path, letter case, scheme, or tenant can cause the two sides to treat them as different identities. Do not arbitrarily `trim`, lowercase, strip slashes, or rewrite an Entity ID used by the partner.

### 2.1. The Questions Entity IDs Answer

| Question | Related identifier | Who checks? |
| --- | --- | --- |
| “Which SP application sent this AuthnRequest?” | **SP Entity ID** in `AuthnRequest/Issuer` | IdP, matching against registered applications |
| “Which IdP issued this SAML Response/Assertion?” | **IdP Entity ID** in `Response/Issuer` and/or `Assertion/Issuer` per protocol structure | SP, matching against trusted IdPs |
| “Which SP is this Assertion intended for?” | **SP Entity ID** in `AudienceRestriction/Audience` | SP, checking audience |
| “To which address must the login result be sent?” | SP's **ACS URL** | IdP uses it to send; SP checks recipient/destination |
| “Who is the logged-in user?” | `NameID` and/or verified assertion attributes | SP and business systems |
| “Where can the IdP receive requests?” | IdP's **SSO endpoint URL** | SP uses it to send requests |

**Entity ID identifies a system; NameID identifies a subject inside an assertion.** Do not use an SP Entity ID or IdP Entity ID as a user ID or as a substitute for user account linking.

## 3. Metadata: Where Entity IDs and the Technical Contract Are Published

SAML metadata is an XML document allowing two systems to describe roles, endpoints, bindings, key/certificate material, and protocol options. The starting point is usually:

```xml
<md:EntityDescriptor
    xmlns:md="urn:oasis:names:tc:SAML:2.0:metadata"
    entityID="urn:example:shop:orders:sp">
    ...
</md:EntityDescriptor>
```

The **`entityID`** attribute here is the entity's identifier, while `<SPSSODescriptor>` or `<IDPSSODescriptor>` represents the SAML SSO role. Do not confuse `entityID` with the `ID` attribute of an XML element: the `ID` attribute (when present) is an XML identifier, usually used for document references/signatures, **not the SP/IdP Entity ID**.

### 3.1. SP Metadata Example

```xml
<md:EntityDescriptor
    xmlns:md="urn:oasis:names:tc:SAML:2.0:metadata"
    entityID="urn:example:shop:orders:sp">
  <md:SPSSODescriptor
      protocolSupportEnumeration="urn:oasis:names:tc:SAML:2.0:protocol"
      WantAssertionsSigned="true">
    <md:AssertionConsumerService
        index="0"
        isDefault="true"
        Binding="urn:oasis:names:tc:SAML:2.0:bindings:HTTP-POST"
        Location="https://shop.example.test/login/saml2/sso/corp"/>
  </md:SPSSODescriptor>
</md:EntityDescriptor>
```

How to read it:

- `EntityDescriptor/@entityID`: **SP Entity ID** = `urn:example:shop:orders:sp`.
- `SPSSODescriptor`: declares that the entity has the Service Provider role.
- `AssertionConsumerService/@Location`: **ACS URL**, receiving SAML Responses from the IdP over the declared binding.
- `Binding=...HTTP-POST`: how the browser delivers the message to the ACS; not the Entity ID.
- `WantAssertionsSigned=true`: states that the SP wants assertions signed. Actual acceptance policy must be configured and verified accordingly.

This is a **minimal metadata snippet to distinguish fields**. Production documents may require `KeyDescriptor`, certificates, additional elements, metadata signatures, and partner-specific conditions. Do not use a minimal snippet as a complete secure federation configuration.

### 3.2. IdP Metadata Example

```xml
<md:EntityDescriptor
    xmlns:md="urn:oasis:names:tc:SAML:2.0:metadata"
    entityID="https://idp.example.test/saml/issuer">
  <md:IDPSSODescriptor
      protocolSupportEnumeration="urn:oasis:names:tc:SAML:2.0:protocol">
    <md:SingleSignOnService
        Binding="urn:oasis:names:tc:SAML:2.0:bindings:HTTP-Redirect"
        Location="https://idp.example.test/saml/sso"/>
  </md:IDPSSODescriptor>
</md:EntityDescriptor>
```

How to read it:

- `EntityDescriptor/@entityID`: **IdP Entity ID** = `https://idp.example.test/saml/issuer`.
- `IDPSSODescriptor`: declares that the IdP supports SAML SSO.
- `SingleSignOnService/@Location`: **SSO endpoint**, where the SP redirects or sends `AuthnRequest` per the binding.
- The metadata address the SP uses to download the XML might be `https://idp.example.test/saml/metadata` — a third URL that **does not have to match** the IdP Entity ID.

The example omits the IdP certificate for clarity. In a real configuration, the SP must hold **trusted verification keys/certificates** to verify response/assertion signatures per policy. An XML document containing the expected `entityID` **does not prove** that the XML or message is trustworthy.

### 3.3. How Does a Metadata URL Differ from an Entity ID?

| Field | Example | Purpose |
| --- | --- | --- |
| SP Entity ID | `urn:example:shop:orders:sp` | Identifies the SP in the federation |
| IdP Entity ID | `https://idp.example.test/saml/issuer` | Identifies the IdP in the federation |
| SP metadata URL | `https://shop.example.test/saml2/metadata/corp` | Where the IdP/partner can fetch the SP description |
| IdP metadata URL | `https://idp.example.test/saml/metadata` | Where the SP can fetch the IdP description |
| SP ACS URL | `https://shop.example.test/login/saml2/sso/corp` | Where the browser POSTs the SAML Response |
| IdP SSO URL | `https://idp.example.test/saml/sso` | Where `AuthnRequest` is sent per binding |
| SP SLO / IdP SLO URL | Depends on Single Logout config | Where `LogoutRequest`/`LogoutResponse` are exchanged |

One metadata URL may publish metadata for multiple entities, or one entity may be published at multiple URLs. Therefore, **do not infer an Entity ID solely from the metadata download path**.

## 4. Entity ID in the SAML 2.0 Web Browser SSO Flow

Suppose the orders application is the SP and the corporate IdP is the authentication system.

```text
Browser            SP: shop.example.test              IdP: idp.example.test
    |                        |                                  |
    | GET /orders            |                                  |
    |----------------------->|                                  |
    |                        | AuthnRequest (Issuer = SP ID)    |
    |                        |--------------------------------->|
    |                        |                                  | authenticate user
    |                        |                                  |
    |                        | Response / Assertion             |
    |                        | Issuer = IdP ID                  |
    |                        | Audience = SP ID                 |
    |<----------------------------------------------------------|
    | POST SAMLResponse to ACS                                  |
    |----------------------->|                                  |
    |                        | check trust, signature, audience,|
    |                        | destination, time, context       |
    |                        |--> create Authentication if valid|
    |<-----------------------|                                  |
```

The diagram only illustrates handoffs through the browser; it does not depict every intermediate HTTP redirect/POST.

### Step 1 — The SP Selects the Federation Configuration

When SAML login is needed, Spring Security selects a **`RelyingPartyRegistration`**, which pairs an SP with an IdP. Each registration has an internal `registrationId` for lookup.

A registration in Spring Security might look like:

```text
registrationId = corp
SP entityId    = urn:example:shop:orders:sp
SP ACS         = https://shop.example.test/login/saml2/sso/corp
IdP entityId   = https://idp.example.test/saml/issuer
IdP SSO        = https://idp.example.test/saml/sso
```

**`corp` is neither the SP Entity ID nor the IdP Entity ID.** It is a configuration/route key helping Spring Security choose the registration. The SP Entity ID remains `urn:example:shop:orders:sp`.

### Step 2 — The SP Issues `AuthnRequest`

The SP constructs a `<samlp:AuthnRequest>` message; example of relevant fields:

```xml
<samlp:AuthnRequest
    xmlns:samlp="urn:oasis:names:tc:SAML:2.0:protocol"
    xmlns:saml="urn:oasis:names:tc:SAML:2.0:assertion"
    ID="_req_001"
    Version="2.0"
    IssueInstant="2026-01-01T10:00:00Z"
    Destination="https://idp.example.test/saml/sso"
    AssertionConsumerServiceURL="https://shop.example.test/login/saml2/sso/corp">
  <saml:Issuer>urn:example:shop:orders:sp</saml:Issuer>
</samlp:AuthnRequest>
```

This XML **illustrates identifier fields, not a signed/complete request**. In the real protocol, the SP/IdP must also check binding, `AuthnRequest` signature if required, timestamps, security requirements, and consistency with metadata.

- `Issuer` of **AuthnRequest** usually contains the **SP Entity ID**.
- `Destination` is the **IdP SSO endpoint**, not the IdP Entity ID.
- `AssertionConsumerServiceURL` is where the SP wants to receive the Response; the IdP only sends to a registered/trusted ACS and must not allow arbitrary URLs.
- `ID` of `AuthnRequest` is the unique code for **one request** to correlate the Response, distinct from the Entity ID.

### Step 3 — The IdP Verifies the SP and Logs In the User

The IdP matches `Issuer` against the SP registered in its trust configuration; verifies ACS URL/binding, signature requirements, client policy, and anti-spoofing rules. Then the IdP authenticates the user according to its policy (potentially using MFA or an SSO session).

A properly configured IdP **does not** send SAML assertions to an arbitrary ACS specified by the request. A user/attacker cannot pick a new SP Entity ID or ACS simply by modifying the message.

### Step 4 — The IdP Issues the SAML Response/Assertion

The following XML fragment illustrates the identifier relationships:

```xml
<samlp:Response
    xmlns:samlp="urn:oasis:names:tc:SAML:2.0:protocol"
    xmlns:saml="urn:oasis:names:tc:SAML:2.0:assertion"
    ID="_resp_001"
    Version="2.0"
    IssueInstant="2026-01-01T10:00:05Z"
    InResponseTo="_req_001"
    Destination="https://shop.example.test/login/saml2/sso/corp">
  <saml:Issuer>https://idp.example.test/saml/issuer</saml:Issuer>
  <saml:Assertion ID="_assertion_001"
                  Version="2.0"
                  IssueInstant="2026-01-01T10:00:05Z">
    <saml:Issuer>https://idp.example.test/saml/issuer</saml:Issuer>
    <saml:Conditions>
      <saml:AudienceRestriction>
        <saml:Audience>urn:example:shop:orders:sp</saml:Audience>
      </saml:AudienceRestriction>
    </saml:Conditions>
  </saml:Assertion>
</samlp:Response>
```

This is **truncated XML to show where `Issuer` and `Audience` sit**, intentionally omitting signatures, Subject, SubjectConfirmation, Status, and real time constraints. It is **not** a complete or safe SAML Response to send to an ACS.

In a complete response:

- `Response/Issuer` and `Assertion/Issuer` usually specify the **IdP Entity ID**; they must be checked against structure, policy, and actual signatures.
- The assertion's `AudienceRestriction/Audience` targets the **SP Entity ID**. That is one constraint preventing an assertion intended for SP A from being used at SP B.
- `Response/@Destination` is the SP's **ACS URL**; `SubjectConfirmationData/@Recipient` in bearer confirmation must also match the valid receiving location.
- `InResponseTo` links the Response/SubjectConfirmationData to the prior `AuthnRequest` in an SP-initiated flow. If IdP-initiated/unsolicited login is supported, separate policies and verification mechanisms must be defined carefully.
- Signatures, time conditions, `InResponseTo`, `Recipient`, `Destination`, `SubjectConfirmation`, `Audience`, and anti-replay policies **all matter**. Matching Entity IDs alone is **not sufficient** to accept a response.

### Step 5 — The SP Verifies and Creates the Application Session

Spring Security SAML 2.0 uses the registration configuration and framework/OpenSAML SAML processing to validate the response according to configuration. If valid, it creates an `Authentication` for the application. Afterward, the business system decides what permissions that person has.

Every Entity ID check must sit inside the **full SAML verification pipeline**. Do not write a custom servlet that parses XML, compares `Issuer`, and grants login while skipping signature or assertion condition checks.

## 5. Trust Boundaries Between the Two Entity IDs

### 5.1. The IdP Verifies the SP's Identity

The SP sends a request with `Issuer=SP Entity ID`. The IdP uses that identifier to look up the registered configuration: ACS allowlist, request signing requirements, SP certificate, and login policies. If `Issuer` does not exist or does not belong to an allowed partner, the IdP must reject or avoid applying another SP's trust configuration.

This prevents a rogue SP from impersonating another application and tricking the IdP into sending assertions to an attacker's endpoint.

### 5.2. The SP Verifies the IdP's Identity and Intended Recipient

Upon receiving a Response, the SP must verify it comes from a registered IdP and carries a **valid signature under a trusted key**. `Issuer=IdP Entity ID` is the logical identity indicator; the certificate/signature provides cryptographic proof. Both must match the trust configuration.

Next, the SP must verify that the assertion is **intended for this SP**, via audience and other constraints. Do not accept an assertion merely because the user exists at some IdP. A token for another application may carry the same NameID yet must not be accepted at this SP.

### 5.3. Why Can't You Rely on Entity ID Alone?

An Entity ID is a public string readable from metadata or messages. An attacker can write the exact same string in forged XML. **A matching string does not prove identity**. Actual trust also depends on:

1. IdP metadata/configuration sourced and verified by administrators.
2. Verification certificates/keys bound to the right IdP.
3. Message/assertion signatures verified per policy.
4. `Issuer`, `Audience`, ACS, `Destination`, `Recipient`, expiration, correlation, and anti-replay checks.
5. User permissions checked subsequently at the business layer.

Do not accept metadata from a URL supplied by an arbitrary request and immediately trust certificates inside that metadata; doing so allows an attacker to mint a “trusted IdP” for the same Entity ID.

## 6. Distinguishing Entity ID from Related Identifiers

| Attribute | Bound to | Meaning | Can it equal Entity ID? |
| --- | --- | --- | --- |
| SP Entity ID | SP | Identifier of the service participating in federation | Is the SP's own identifier |
| IdP Entity ID | IdP | Identifier of the server issuing SAML assertions | Is the IdP's own identifier |
| `registrationId` in Spring | An RP–AP configuration pair | Selects local config, appears in many default URLs | May match string-wise by admin choice, but **is not the same concept** |
| SP metadata URL | Server serving XML metadata | Location to download SP description | May share a URL-style entityID, but not required |
| IdP metadata URL | Server serving XML metadata | Location to download IdP description | May differ from IdP entityID |
| ACS URL | SP | Endpoint receiving SAML Responses | Should be treated as a separate field; can change while Entity ID stays fixed |
| SSO URL | IdP | Endpoint receiving `AuthnRequest` | Not the IdP Entity ID |
| SLO URL | SP or IdP | Endpoint exchanging Single Logout messages | Not an Entity ID |
| `NameID` | User in assertion | Subject identity per format/qualifier | Not a system Entity ID |
| `AuthnRequest/@ID` | One login request instance | Correlates request/response and prevents replay | Not an Entity ID |
| X.509 certificate | Signing/verifying key of SP/IdP | Cryptographic trust for messages/metadata | Not an Entity ID; key rotation can keep Entity ID unchanged |

For example, “`https://shop.example.test/saml2/metadata/corp` is the Entity ID” is true **only if the SP actually configured its Entity ID to that exact value**; it cannot be deduced simply because that URL serves metadata.

## 7. Configuration with Spring Security and Spring Boot

Spring Security Servlet supports an application acting as a **SAML 2.0 Relying Party/Service Provider**. Inside a `RelyingPartyRegistration`:

- **The relying party side** holds `entityId` (SP), `assertionConsumerServiceLocation`, and signing/decryption credentials if used.
- **The asserting party side** holds `entityId` (IdP), SSO/SLO endpoints, and verification credentials/metadata.
- `registrationId` is a **local identifier for the configuration pair**, such as `corp` or `partner-a`; it is distinct from both Entity IDs.

### 7.1. Sample `application.yml`

Example for Spring Boot 3.x / Spring Security 6.x with appropriate SAML2 properties:

File `src/main/resources/application.yml`:

```yaml
spring:
  security:
    saml2:
      relyingparty:
        registration:
          corp:
            entity-id: "urn:example:shop:orders:sp"
            acs:
              location: "{baseUrl}/login/saml2/sso/{registrationId}"
            assertingparty:
              metadata-uri: "https://idp.example.test/saml/metadata"
```

Exact explanation:

- `corp` is the **registrationId**, used to select this configuration.
- `entity-id` under `registration.corp` is the **SP Entity ID**. The IdP must register the application with the exact string `urn:example:shop:orders:sp`.
- `acs.location` is the SP's **assertion receiving address**. When `baseUrl=https://shop.example.test`, it resolves to `https://shop.example.test/login/saml2/sso/corp`.
- `assertingparty.metadata-uri` is the **location to fetch IdP metadata**, not the IdP Entity ID. Spring reads the IdP Entity ID from `EntityDescriptor/@entityID` in the trusted metadata.
- In real deployments, the IdP needs to publish certificates and proper endpoints. If the IdP requires signed `AuthnRequest`s or encrypted assertions, corresponding signing/decryption credentials must be configured. This snippet **only shows Entity ID/metadata/ACS mapping**; it does not by itself prove all IdP security requirements are satisfied.

Depending on the Spring Boot version, the structure/availability of some properties may differ; check the **configuration metadata of the running version** rather than copying config from a different framework generation. These examples target **modern Spring Security**, not the legacy Spring Security SAML Extension project which used different beans and paths.

### 7.2. `SecurityFilterChain` Exposing SAML Metadata

File `SecurityConfig.java` in the application package (e.g. `com.example.shop`), illustrating servlet configuration:

```java
package com.example.shop;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class SecurityConfig {

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http)
            throws Exception {
        http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/", "/public/**").permitAll()
                .anyRequest().authenticated())
            .saml2Login(Customizer.withDefaults())
            .saml2Metadata(Customizer.withDefaults());

        return http.build();
    }
}
```

This is **a class inside a Spring Boot project**, not a program runnable directly with plain JDK `javac`. The project needs web/security dependencies and `org.springframework.security:spring-security-saml2-service-provider`, a repository to resolve OpenSAML if required by the build environment, as well as properly configured registrations/certificates/IdP.

With the `saml2Metadata` DSL, Spring Security can publish metadata for registrations at default URLs such as:

```text
/saml2/metadata
/saml2/metadata/{registrationId}
/saml2/service-provider-metadata/{registrationId}
```

Actual endpoints and presentation can vary with Spring Security configuration. The IdP should import the SP metadata or the same verified set of **SP Entity ID + ACS URL + certificate**. If there is a reverse proxy/TLS termination, ensure the exported metadata reflects the **public** host, scheme, port, and path; do not publish an `http://localhost:8080/...` ACS to an external IdP.

### 7.3. Retrieving Entity IDs for Cross-Checking

In an application with `RelyingPartyRegistrationRepository`, you can inspect a specific registration's configuration, for example:

```java
RelyingPartyRegistration registration =
    repository.findByRegistrationId("corp");

String spEntityId = registration.getEntityId();
String idpEntityId =
    registration.getAssertingPartyMetadata().getEntityId();

String acs = registration.getAssertionConsumerServiceLocation();
```

The snippet above is only an **API usage excerpt inside a method that already has a `repository` variable**, not a standalone Java file. Method/API names can change across Spring Security versions; read the Javadoc for your exact version. Match these two Entity IDs against the partner's metadata/registration and ensure `acs` is accurate.

**Do not edit `registrationId` to “patch” a wrong IdP Entity ID.** If the IdP changes its `entityID`, update the asserting-party metadata/trust configuration properly and coordinate verification rather than renaming a local label and hoping validation passes.

## 8. Standalone Java 17 Example: Checking the Entity ID Pair Against the Contract

This snippet only simulates **comparing identifier strings already extracted from a trusted message**, to clarify the difference between issuer and audience. It **does not parse, decrypt, verify signatures, or accept real SAML Responses**. In a real system, SAML authentication must use Spring Security/OpenSAML and full protocol constraints.

File `EntityIdContractDemo.java`:

```java
import java.util.Objects;

public class EntityIdContractDemo {

    record FederationPair(String spEntityId, String idpEntityId) {
        FederationPair {
            Objects.requireNonNull(spEntityId);
            Objects.requireNonNull(idpEntityId);
        }
    }

    static boolean matchesPartyIds(
            FederationPair configured,
            String responseIssuer,
            String assertionAudience) {
        return configured.idpEntityId().equals(responseIssuer)
                && configured.spEntityId().equals(assertionAudience);
    }

    public static void main(String[] args) {
        FederationPair pair = new FederationPair(
                "urn:example:shop:orders:sp",
                "https://idp.example.test/saml/issuer"
        );

        System.out.println("expected=" + matchesPartyIds(
                pair,
                "https://idp.example.test/saml/issuer",
                "urn:example:shop:orders:sp"
        ));

        System.out.println("wrongIssuer=" + matchesPartyIds(
                pair,
                "https://other-idp.example.test/saml/issuer",
                "urn:example:shop:orders:sp"
        ));

        System.out.println("wrongAudience=" + matchesPartyIds(
                pair,
                "https://idp.example.test/saml/issuer",
                "urn:example:shop:payroll:sp"
        ));

        System.out.println("trailingSlash=" + matchesPartyIds(
                pair,
                "https://idp.example.test/saml/issuer/",
                "urn:example:shop:orders:sp"
        ));
    }
}
```

Compile and run with JDK 17+:

```bash
javac EntityIdContractDemo.java
java EntityIdContractDemo
```

Exact stdout:

```text
expected=true
wrongIssuer=false
wrongAudience=false
trailingSlash=false
```

Explanation:

- `expected=true` when the issuer's IdP Entity ID and the SP Entity ID in audience both match configuration.
- `wrongIssuer=false`: the message declares an issuer different from the registered provider.
- `wrongAudience=false`: the assertion is intended for a different SP, even though the IdP is right.
- `trailingSlash=false`: `/issuer` and `/issuer/` are two distinct strings in identifier comparison.

**Scope warning for the example:** these `equals` calls only illustrate **identifier label** relationships; they do not prove the origin of the supplied values. Only after SAML passes signature, time conditions, Destination/Recipient, SubjectConfirmation, InResponseTo, anti-replay, and matching registration checks can an authenticated session be created. Do not use `matchesPartyIds` as a standalone SAML validator.

## 9. One SP Connected to Multiple IdPs: Managing Entity Pairs

An application may allow company A employees and partner B users to log in from two different IdPs. Spring Security stores **one registration per SP–IdP relationship**.

Example:

| registrationId | SP Entity ID | IdP Entity ID | ACS |
| --- | --- | --- | --- |
| `employee` | `urn:example:shop:orders:sp` | `https://idp-a.example.test/saml` | `https://shop.example.test/login/saml2/sso/employee` |
| `partner` | `urn:example:shop:orders:sp` | `https://idp-b.example.test/issuer` | `https://shop.example.test/login/saml2/sso/partner` |

**Reusing the same SP Entity ID across multiple IdPs** is a valid option if each IdP is registered with the exact SP entity/ACS/binding and the application separates trust configurations cleanly. In organizations requiring a distinct SP identity per partner or per environment, the SP Entity ID can also vary by registration. There is no universal rule that **one `registrationId` must map to a globally unique SP Entity ID**.

Safety rules:

1. Manage each pair by **IdP Entity ID, certificate, endpoints, SP Entity ID, and ACS**. Do not assume “same hostname” means the same IdP.
2. Select `RelyingPartyRegistration` through Spring Security's supported mechanisms, and verify the response against the selected registration's trust config.
3. Do not let an attacker send an arbitrary `Issuer` and trigger the SP to fetch new metadata and trust the attacker's certificate.
4. Do not accept an assertion from IdP A under B's configuration/certificate just because both register the same application.
5. If multiple SP applications share a domain, **audience, ACS, and registration identifiers** must be distinct enough that an assertion for one application is never accepted by another.
6. If using an intermediary identity broker, the SP normally trusts the configured **broker's Entity ID**. The upstream IdP's Entity ID is part of a separate trust relationship between broker and upstream, not something inferred blindly from the assertion received at the SP.

## 10. Entity IDs Across Multiple Environments and Reverse Proxies

A common mistake is building/deploying to different environments without managing Entity IDs, metadata, and endpoints consistently:

```text
DEV SP Entity ID  = urn:example:shop:dev:sp
UAT SP Entity ID  = urn:example:shop:uat:sp
PROD SP Entity ID = urn:example:shop:prod:sp
```

Each environment should have explicit trust configuration and public URLs, especially when the IdP assigns different permissions/ACS/certificates. Organizations do not have to follow the exact pattern above, but they need a scheme preventing dev/prod mix-ups and cross-environment logins.

**Proxy error example:**

```text
User opens            https://shop.example.test
Proxy forwards to     http://orders-service:8080
Spring generates ACS  http://orders-service:8080/login/saml2/sso/corp
IdP registered ACS    https://shop.example.test/login/saml2/sso/corp
```

In that case, the IdP may reject the `AuthnRequest` because the ACS is not on the allowlist; or the SAML Response arrives at the public endpoint, yet the SP checks Destination/Recipient and sees a mismatch.

How to handle it:

- Configure the reverse proxy to send `Forwarded` or `X-Forwarded-*` **from trusted proxies**, and configure Spring Boot/Spring Security to construct URLs from controlled header sources.
- Inspect the SP metadata content **at the public address**: `entityID`, ACS `Location`, binding, and certificate.
- Cross-check the record imported at the IdP to avoid domain, path, slash, or port mismatches.
- If choosing a `urn:` SP Entity ID, the entity ID can remain stable when the host changes, **yet the ACS must still be updated** if the receiving address changes. If the Entity ID uses `{baseUrl}`, changing the public base URL can simultaneously change the Entity ID.
- Do not allow forwarded headers from the public Internet to directly dictate trust URLs if the backend can be reached bypassing the proxy; block direct bypass paths to the backend and configure trusted proxies.

## 11. Rotating Keys, Changing Endpoints, or Changing Entity IDs

Three operational changes have very different impact levels:

| Change | What stays the same? | What needs coordination |
| --- | --- | --- |
| IdP certificate rotation | Entity ID usually **stays the same** | SP imports/refreshes verification keys from a trusted metadata source, with overlap period if policy permits |
| IdP SSO endpoint change | Entity ID can **stay the same** | SP updates endpoint/binding from verified metadata |
| SP ACS URL change | SP Entity ID can **stay the same** | IdP updates SP allowlist/metadata; SP configures routes and Destination/Recipient |
| SP Entity ID change | SP identifier **changes** | IdP registers/updates the SP, audience mapping, and trust; test flow before cutover |
| IdP Entity ID change | IdP identifier **changes** | SP updates asserting-party metadata/trust and tests Issuer; may affect user linking |
| Local `registrationId` change | Entity IDs may remain unchanged | Update login URL, ACS containing `{registrationId}`, and related metadata/IdP settings |

**Changing an Entity ID is not a cosmetic screen-label edit.** When the SP Entity ID changes, the IdP may treat it as a **brand-new SP application**; SAML Audience, AuthnRequest Issuer, SP metadata, and IdP-side certificate/ACS configuration must all align. When the IdP Entity ID changes, the SP must never bypass issuer validation just to “let logins through.”

Recommended procedure:

1. Snapshot the approved configuration: both Entity IDs, metadata, ACS/SSO, certificates, and profiles/bindings.
2. Classify the change as **entity identity**, **endpoint**, or **key material** — do not conflate the three.
3. Prepare the new configuration on both SP and IdP with a controlled cutover plan.
4. Test SP-initiated login; if IdP-initiated login is used, test separately and verify correlation/replay policy.
5. Verify issuer, audience, recipient, destination, signature, session, and business permissions.
6. Monitor errors and retire old configurations/keys on schedule; do not leave legacy trust active indefinitely.

## 12. Common Errors, Symptoms, and Fixes

| Symptom | Possible cause | Right check |
| --- | --- | --- |
| IdP reports unrecognized application | `AuthnRequest/Issuer` does not match registered SP Entity ID | Compare SP Entity ID in IdP-managed metadata with request Issuer |
| IdP rejects ACS | `AssertionConsumerServiceURL` is not in the allowlist | Check registered ACS, binding, scheme, port, path |
| SP reports invalid issuer | IdP Entity ID in assertion/response differs from configuration | Compare IdP metadata `entityID` with actual verified issuer |
| SP reports invalid audience | Assertion Audience is another Entity ID | Compare `AudienceRestriction/Audience` with active SP Entity ID |
| SP reports invalid Destination/Recipient | ACS or proxy URL mismatch | Compare destination/recipient, public URL, and metadata |
| SP cannot find registration | Wrong `registrationId` or registration lookup logic | Check `/saml2/authenticate/{registrationId}` URL and repository/registration |
| Invalid signature despite matching Entity ID | Mismatched certificate/algorithm/signing key, stale metadata, or tampered signature | Check trust certificate, rotation, and signature policy |
| IdP login succeeds but SP rejects | Assertion failed one of the SP's checks | Inspect the exact error **category**: issuer, audience, signature, recipient, time, correlation |
| Fails only in production behind reverse proxy | `{baseUrl}`/ACS built from internal host/scheme | Compare public metadata and trusted proxy config |
| Cannot connect after changing `entityID` | Partner has not updated metadata/trust | Coordinate updates on both sides and test cutover flow |
| Multiple IdPs, A's token processed as B | Wrong registration selection or trust mapping | Isolate issuer, verification credentials, and registration; verify strictly |
| Duplicate usernames | Colliding `NameID` across IdPs | This is a **user identity** problem, not solved by changing SP Entity ID |

Do not disable signature, issuer, or audience verification to work around configuration errors. Removing a critical check can turn a login failure into a vulnerability that accepts assertions not meant for the application.

## 13. Testing the Entity ID Contract Systematically

Tests should verify:

| Test case | Input | Expected result |
| --- | --- | --- |
| Valid login | AuthnRequest Issuer is SP ID; Response/Assertion from registered IdP; Audience is SP ID | After **all** validations, create login session |
| Wrong SP ID | Request Issuer does not match SP registered at IdP | IdP rejects or refuses to apply the SP's trust |
| Wrong IdP ID | Response/Assertion has another IdP's issuer | SP rejects |
| Wrong Audience | Assertion is intended for another SP | SP rejects |
| Missing/invalid signature | Issuer and Audience are right, but signature is invalid | SP rejects |
| Wrong ACS | Response Destination/Recipient does not match valid endpoint | SP rejects |
| Replayed response | Same Response/Assertion resubmitted after use | Blocked by replay/correlation policy |
| Expired | Assertion outside valid NotBefore/NotOnOrAfter | SP rejects |
| Different trailing `/` | Entity ID with or without slash | Enforce exact contract value, do not auto-normalize |
| Changed proxy hostname | Public URL differs from internal URL | SP metadata and ACS reflect trusted public URL |
| Two IdPs | A and B have different entityID/certificates | Response from A is not accepted as B |
| Certificate change | Entity ID unchanged, new signing key valid | Accept new key only after trust update per policy |
| SP ID change | New Audience, new SP metadata/IdP registration | Works after sync; rejects assertions for old ID once retired |

Testing **negative cases** is just as important as “happy-path login”: rejecting an assertion with a wrong issuer/audience proves the trust boundary works. You can run integration tests with a test IdP and SAML test harness; do not treat truncated XML in this lesson as valid token samples.

## 14. Deployment Checklist with a SAML Partner

- [ ] Document the approved SP Entity ID, exact down to trailing `/`, scheme, path, and casing.
- [ ] Document the IdP Entity ID from trusted metadata; do not guess it from the SSO URL or vendor name.
- [ ] Confirm `registrationId` in Spring Security is only a config label; know the exact SP/IdP `entityId` of each registration.
- [ ] Cross-check SP metadata `EntityDescriptor/@entityID` against `AuthnRequest/Issuer`.
- [ ] Cross-check IdP metadata `EntityDescriptor/@entityID` against `Response/Issuer` / `Assertion/Issuer` per protocol requirements.
- [ ] Cross-check `AudienceRestriction/Audience` against SP Entity ID; never substitute ACS URL.
- [ ] Cross-check ACS, SSO, SLO URLs and bindings; verify public addresses behind reverse proxies.
- [ ] Establish trusted certificates/metadata and safe signature policies; maintain a rotation procedure.
- [ ] Verify response/assertion validation covers issuer, audience, destination, recipient, time, subject confirmation, and InResponseTo/anti-replay per supported profile.
- [ ] Test IdP-initiated flows separately if needed; do not assume every unsolicited response is acceptable.
- [ ] Separate dev/UAT/prod and per-IdP configurations; document who owns Entity ID changes.
- [ ] Log SAML failures at a level sufficient for troubleshooting; do not dump raw SAMLResponses containing sensitive data into production logs.
- [ ] After successful authentication, business systems must continue checking user mapping, account status, tenant, and permissions.

## 15. Self-Check Questions

**1. Is the SP Entity ID the URL that receives the SAML Response?** No. The receiving URL is the **ACS URL**. An SP Entity ID may be URL-shaped or URN-shaped, but it serves as the SP's logical identifier.

**2. In `AuthnRequest`, whose `Issuer` is it usually?** It is the **SP Entity ID**. `Destination` is the **IdP's SSO endpoint**.

**3. When an SP receives an assertion, what must the Audience value match?** Under SAML Web Browser SSO, it must match the **SP Entity ID** of the active registration, alongside all other validation checks.

**4. Is `https://idp.example.test/saml/metadata` always the IdP Entity ID?** No. That may simply be the metadata download URL. Read `EntityDescriptor/@entityID` to find the IdP Entity ID.

**5. If the IdP rotates its certificate without changing its Entity ID, must the SP change its SP Entity ID?** Usually no. The SP needs to update/refresh the trust key, verify signatures, and coordinate rotation; Entity ID is a logical identifier independent of key material.

**6. Why can a Response with matching issuer and audience still be dangerous?** Because an attacker can forge strings. The SP must still verify trusted signatures, recipient/destination, expiration, request correlation, subject confirmation, and anti-replay.

**7. Can `registrationId=corp` in Spring be used as the IdP's issuer?** Not by default. That is a local key. The IdP Entity ID must come from trusted asserting-party metadata/configuration.

**8. Can the SP Entity ID be used as a user ID?** No. It identifies the SP system; verified SAML `NameID`/subject attributes map user identity according to the IdP contract.

## References

- Spring Security, **SAML 2.0 Login Overview**, organizing `RelyingPartyRegistration`, default Entity ID and ACS values: https://docs.spring.io/spring-security/reference/servlet/saml2/login/overview.html
- Spring Security, **SAML 2.0 Metadata**, reading IdP metadata and publishing SP metadata: https://docs.spring.io/spring-security/reference/servlet/saml2/metadata.html
- Spring Security, **Authenticating SAML Responses**, verifying responses and configuring authentication: https://docs.spring.io/spring-security/reference/servlet/saml2/login/authentication.html
- Spring Security, **Producing AuthnRequests**, configuring request signing: https://docs.spring.io/spring-security/reference/servlet/saml2/login/authentication-requests.html
- Spring Boot 3.5, **SAML 2.0 Relying Party** properties: https://docs.spring.io/spring-boot/3.5/reference/web/spring-security.html
- OASIS, **SAML 2.0 Metadata Specification**, `EntityDescriptor`, `IDPSSODescriptor`, `SPSSODescriptor`: https://docs.oasis-open.org/security/saml/v2.0/saml-metadata-2.0-os.pdf

**Remember:** in SAML 2.0, the **SP Entity ID** identifies the application requesting login and the intended target of the assertion; the **IdP Entity ID** identifies the trusted issuer. An Entity ID is not an ACS/SSO/metadata URL or a NameID. Secure federation requires **both Entity IDs plus certificates, endpoints, audience, and all SAML verification checks to be right**, before letting the application create a session and enforce business permissions.