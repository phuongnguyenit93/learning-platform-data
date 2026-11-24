# SSO, ACS, SLO Endpoints, and Bindings in SAML 2.0 Metadata

In a **SAML 2.0 federation** system, the application receiving login results is the **Service Provider (SP/Relying Party)**, while the system authenticating users is the **Identity Provider (IdP/Asserting Party)**. Neither side guesses the other's paths: they exchange **metadata XML** to learn the partner's identifier, endpoints, bindings, certificates, and supported capabilities.

**Distinguish the three endpoint types right away:**

| Metadata element | Which side owns it? | Which messages does it receive? | Function |
| --- | --- | --- | --- |
| `SingleSignOnService` (**SSO**) | **IdP**; inside `IDPSSODescriptor`. | SP sends `AuthnRequest` to the IdP. | Starts user authentication. |
| `AssertionConsumerService` (**ACS**) | **SP**; inside `SPSSODescriptor`. | IdP sends SAML `Response` containing an assertion. | SP verifies the login result and establishes a session if valid. |
| `SingleLogoutService` (**SLO**) | Can exist on both **IdP and SP**. | `LogoutRequest` and `LogoutResponse`. | Coordinates terminating federated login sessions. |

**Primary direction:** SP sends the login request to **IdP SSO** → IdP returns the result to **SP ACS**. During federated logout, the initiating party sends a message to the **receiving party's SLO endpoint**. Each endpoint declares a `Binding` to specify *how the message is transported*; `Binding` is not a URL or a login permission.

## 1. What Is Inside Metadata?

A metadata file typically contains `<md:EntityDescriptor>` with an `entityID` and one or more role descriptors. An aggregate file may contain `<md:EntitiesDescriptor>` wrapping multiple entities. Relevant elements:

~~~text
IdP metadata
EntityDescriptor  @entityID = IDP_ENTITY_ID
└── IDPSSODescriptor
    ├── KeyDescriptor                 published signing/encryption keys
    ├── SingleLogoutService           IdP SLO if supported
    ├── NameIDFormat                  name identifier formats if published
    └── SingleSignOnService           one or more IdP SSO endpoints

SP metadata
EntityDescriptor  @entityID = SP_ENTITY_ID
└── SPSSODescriptor
    ├── KeyDescriptor                 SP keys if present
    ├── SingleLogoutService           SP SLO if supported
    ├── NameIDFormat                  supported NameID formats
    └── AssertionConsumerService      one or more SP ACS endpoints
~~~

Real metadata may also include `validUntil`, `cacheDuration`, `AuthnRequestsSigned`, `WantAuthnRequestsSigned`, `WantAssertionsSigned`, `ArtifactResolutionService`, and extensions. **`entityID` is a logical identifier**, which can take a URL or URN form; it is **not necessarily a reachable URL**. Separate clearly:

- **SP entityID**: the value the IdP uses to identify the SP/audience, e.g. `urn:example:sp:portal`.
- **IdP entityID**: the identity of the trusted SAML issuer, e.g. `urn:example:idp:corporate`.
- **Metadata URL**: where the XML document is fetched to configure/sync settings, e.g. `https://idp.example.org/metadata`.
- **SSO/ACS/SLO Location**: the addresses where messages are exchanged during actual login/logout.

Using the metadata URL as the SSO URL, or using the ACS URL as the SP entityID without intentionally configuring it that way, will break integration even though all strings look like URLs.

## 2. IdP Metadata: SingleSignOnService

This XML example **illustrates endpoints** while omitting keys, metadata signature, and other deployment attributes:

~~~xml
<md:EntityDescriptor
    xmlns:md="urn:oasis:names:tc:SAML:2.0:metadata"
    entityID="urn:example:idp:corporate">
  <md:IDPSSODescriptor
      protocolSupportEnumeration="urn:oasis:names:tc:SAML:2.0:protocol">

    <md:SingleLogoutService
        Binding="urn:oasis:names:tc:SAML:2.0:bindings:HTTP-Redirect"
        Location="https://idp.example.org/saml/slo"/>

    <md:SingleSignOnService
        Binding="urn:oasis:names:tc:SAML:2.0:bindings:HTTP-Redirect"
        Location="https://idp.example.org/saml/sso/redirect"/>

    <md:SingleSignOnService
        Binding="urn:oasis:names:tc:SAML:2.0:bindings:HTTP-POST"
        Location="https://idp.example.org/saml/sso/post"/>
  </md:IDPSSODescriptor>
</md:EntityDescriptor>
~~~

Here, `SingleSignOnService/@Location` is **the address where the IdP receives `AuthnRequest` from the SP**. `Binding` indicates whether the SP must send the request via HTTP-Redirect or HTTP-POST. Having **two SSO endpoints** simply means the IdP advertises two choices: the SP must pick a supported **Binding + Location pair** and not mix the binding from one entry with the URL from another.

`SingleLogoutService` here is the **IdP's SLO**; it does not substitute for `SingleSignOnService`, even if some products place both on the same HTTP path.

In an SP-initiated SSO flow, the SP creates an `AuthnRequest`, stores transaction state in the initiating browser's session/correlation store, and redirects the browser to the chosen **IdP SSO Location**. Visiting this IdP endpoint only starts the process; **no SAML Response has been verified by the application yet**.

## 3. SP Metadata: AssertionConsumerService

The SP publishes endpoints for the IdP to return results using `AssertionConsumerService` (ACS). An example:

~~~xml
<md:EntityDescriptor
    xmlns:md="urn:oasis:names:tc:SAML:2.0:metadata"
    entityID="urn:example:sp:portal">
  <md:SPSSODescriptor
      protocolSupportEnumeration="urn:oasis:names:tc:SAML:2.0:protocol">

    <md:SingleLogoutService
        Binding="urn:oasis:names:tc:SAML:2.0:bindings:HTTP-POST"
        Location="https://sp.example.org/logout/saml2/slo"/>

    <md:AssertionConsumerService
        Binding="urn:oasis:names:tc:SAML:2.0:bindings:HTTP-POST"
        Location="https://sp.example.org/login/saml2/sso/corporate"
        index="0"
        isDefault="true"/>

    <md:AssertionConsumerService
        Binding="urn:oasis:names:tc:SAML:2.0:bindings:HTTP-POST"
        Location="https://sp.example.org/saml/acs/partner"
        index="1"/>
  </md:SPSSODescriptor>
</md:EntityDescriptor>
~~~

**Field definitions on ACS:**

| Attribute | Meaning |
| --- | --- |
| `Binding` | How **the IdP sends the Response to the ACS**; HTTP-POST is common in Web Browser SSO. |
| `Location` | The concrete URL where **the SP actually has a handler receiving the SAML Response**. |
| `index` | Endpoint index in the ACS list; a **required** attribute of `AssertionConsumerService`. |
| `isDefault` | Identifies the default endpoint per metadata/profile rules when appropriate. |
| `ResponseLocation` | Optional attribute on endpoint types; not needed to express a typical Web SSO ACS. |

If the SP registers multiple ACS endpoints, `AuthnRequest` can propose an `AssertionConsumerServiceIndex` or an ACS address per protocol rules; the IdP must verify it against the **trusted SP registration and metadata**. Never take an arbitrary ACS URL sent by the browser to send a SAML Response containing sensitive information out to it.

Typically, the IdP generates an HTML form whose `action` points to the ACS, and the browser POSTs the `SAMLResponse` field (Base64-encoded XML). The SP must parse it and verify **signature, issuer, destination, recipient, audience, validity timestamps, correlation, and replay** before establishing a session. The ACS is **not** an endpoint for the SP to send `AuthnRequest` to the IdP.

### 3.1. `entityID` and ACS URL Are Different

Suppose the IdP is configured with:

~~~text
SP Identifier / Audience: urn:example:sp:portal
Reply URL / ACS:        https://sp.example.org/login/saml2/sso/corporate
Response binding:       HTTP-POST
~~~

The Assertion has an `AudienceRestriction` referencing the **SP entityID**, whereas `Response@Destination` and bearer `SubjectConfirmationData@Recipient` must match the **ACS URL** per profile and configuration. Valid signatures and audience **cannot substitute for** verifying the exact ACS/recipient. These are two distinct types of constraints.

## 4. What Is a SAML Binding?

A binding specifies how a SAML message is sent over a transport protocol. It is represented by a standard URI, not simply the words `GET` or `POST`.

| Binding | Standard URI | Typical usage | Limitations / things to remember |
| --- | --- | --- | --- |
| **HTTP-Redirect** | `urn:oasis:names:tc:SAML:2.0:bindings:HTTP-Redirect` | SP sends `AuthnRequest` to IdP SSO; SLO may also use it. | SAML payload is encoded in the query string (typically DEFLATE → Base64 → URL encode); URL length limits, signatures follow Redirect binding rules. |
| **HTTP-POST** | `urn:oasis:names:tc:SAML:2.0:bindings:HTTP-POST` | IdP sends `Response` to SP ACS; also usable for AuthnRequest or SLO if both support it. | Form POST carrying Base64 `SAMLRequest` or `SAMLResponse`, typically verifying XML Signature per profile/policy. |
| **HTTP-Artifact** | `urn:oasis:names:tc:SAML:2.0:bindings:HTTP-Artifact` | Browser carries an artifact; the receiver retrieves the full message over a back channel. | Requires artifact resolution with configured endpoint/back-channel, usually SOAP; changing the Binding URI alone is not enough to enable it. |
| **SOAP** | `urn:oasis:names:tc:SAML:2.0:bindings:SOAP` | Artifact resolution or back-channel profiles. | Direct server-to-server messaging, not browser redirects. |

A **metadata role** can advertise multiple endpoints supporting multiple bindings. Only binding/endpoint combinations implemented by both SP and IdP should be selected. HTTP-Redirect signatures are protected via a binding mechanism different from XML Signatures in HTTP-POST messages; use a library parser/validator instead of verifying manually by Base64-decoding.

### 4.1. The Two SSO Legs Can Have Different Bindings

~~~text
Step 1: SP ---- AuthnRequest via HTTP-Redirect ----> IdP SSO
             chosen from the IdP's SingleSignOnService

Step 2: IdP ---- SAML Response via HTTP-POST ------> SP ACS
             chosen from the SP's AssertionConsumerService
~~~

This combination is **very common and valid**. The IdP SSO `Binding` applies to **requests sent to the IdP**, while the SP ACS `Binding` applies to **responses sent back to the SP**. Therefore, a "mismatch" error must not be inferred simply because one side uses Redirect and the other uses POST.

### 4.2. `AuthnRequest@ProtocolBinding` Specifies the Response Binding

In `AuthnRequest`, `ProtocolBinding` (if present) indicates **the binding the SP wants to use to receive the SAML Response**, not the binding used to transport the `AuthnRequest` itself.

~~~xml
<samlp:AuthnRequest
    xmlns:samlp="urn:oasis:names:tc:SAML:2.0:protocol"
    ID="_request-7a"
    Version="2.0"
    IssueInstant="2026-11-07T03:00:00Z"
    Destination="https://idp.example.org/saml/sso/redirect"
    AssertionConsumerServiceIndex="0"
    ProtocolBinding="urn:oasis:names:tc:SAML:2.0:bindings:HTTP-POST"/>
~~~

This example states: the request goes to the IdP SSO Redirect endpoint, while the response is expected via **POST binding to ACS index 0**. This is a snippet illustrating attributes, **not a complete AuthnRequest**, because it lacks Issuer, signature protection state, and other profile-required parts.

**`RelayState` is neither a binding nor an endpoint.** It carries transaction-related state accompanying the SAML message. In SP-initiated SSO, the RP/SP must verify that the response belongs to **the exact initiating request and browser session**; `RelayState` or `InResponseTo` from the callback is insufficient without matching against securely stored state.

## 5. SingleLogoutService: SLO Exists in Both Directions

Unlike SSO/ACS, which have primarily one-way roles, `SingleLogoutService` can appear in **both IDPSSODescriptor and SPSSODescriptor**, because either the IdP or the SP may have to **receive** a `LogoutRequest` or `LogoutResponse`.

Example:

~~~xml
<!-- SingleLogoutService inside IDPSSODescriptor -->
<md:SingleLogoutService
    xmlns:md="urn:oasis:names:tc:SAML:2.0:metadata"
    Binding="urn:oasis:names:tc:SAML:2.0:bindings:HTTP-Redirect"
    Location="https://idp.example.org/saml/slo"/>

<!-- SingleLogoutService inside SPSSODescriptor -->
<md:SingleLogoutService
    xmlns:md="urn:oasis:names:tc:SAML:2.0:metadata"
    Binding="urn:oasis:names:tc:SAML:2.0:bindings:HTTP-POST"
    Location="https://sp.example.org/logout/saml2/slo"/>
~~~

**`Location`** specifies the message destination for the logout service. An SLO endpoint can add **`ResponseLocation`** to receive **responses** at a URL different from the destination receiving **requests**. If `ResponseLocation` is absent, related responses can be handled at `Location` per metadata rules. It is not a fallback URL for load balancing.

### 5.1. SP-Initiated SLO

1. The user sends a logout request to the SP; the SP identifies the relevant session and IdP.
2. The SP creates and signs/protects a `LogoutRequest` per binding/profile requirements and sends it to the **IdP SingleLogoutService**.
3. The IdP verifies, processes logout, and returns a `LogoutResponse` to the appropriate **SP SingleLogoutService**.
4. The SP verifies the response (which may carry `InResponseTo`) and completes the logout flow/browser response per policy.

### 5.2. IdP-Initiated SLO

1. The IdP sends a `LogoutRequest` to the **SP SingleLogoutService** over a supported binding.
2. The SP verifies issuer/signature, `Destination`, NameID/SessionIndex when present, and locates and terminates the associated session.
3. The SP issues a `LogoutResponse` to the appropriate **IdP SingleLogoutService**.

**SLO differs from local logout:** merely clearing the SP session cookie does not log out sessions at the IdP or other SPs. Conversely, sending an SLO request does not guarantee every application logged out successfully: some may not support it, networks may fail, or partial logout may be returned. The system must have policies for error handling, timeouts, and auditing.

In Spring Security, the SLO receiving endpoint is not the ACS. Routing a LogoutResponse to `/login/saml2/sso/...` causes the SP to misprocess the message type or reject it.

## 6. Common Mapping Table When Configuring Partners

Admin UIs of different IdPs use varying terminology. Map based on **sender / receiver**, avoiding guesswork from the phrase "SSO URL":

| Label in configuration screen | Where does the value come from? |
| --- | --- |
| **IdP Sign-in URL / IdP SSO URL** | `IDPSSODescriptor/SingleSignOnService/@Location` for the corresponding binding. |
| **IdP Issuer / Entity ID** | IdP's `EntityDescriptor/@entityID`. |
| **SP Identifier / Audience URI / SP Entity ID** | SP's `EntityDescriptor/@entityID`. |
| **Reply URL / Assertion Consumer URL / ACS URL** | `SPSSODescriptor/AssertionConsumerService/@Location`. |
| **Response Binding / ACS Binding** | `AssertionConsumerService/@Binding`, usually HTTP-POST. |
| **IdP Logout URL** | `IDPSSODescriptor/SingleLogoutService/@Location` or ResponseLocation when appropriate. |
| **SP Logout Callback URL** | `SPSSODescriptor/SingleLogoutService/@Location` or ResponseLocation if configured. |
| **Certificate verifying IdP signatures** | IdP's `KeyDescriptor` from metadata **for which trust has been established**. |
| **Metadata URL** | Endpoint serving the provider's XML metadata, **not the SSO execution endpoint**. |

Example of a federation link:

~~~text
SP entity ID:           urn:example:sp:portal
IdP entity ID:          urn:example:idp:corporate
IdP SSO (Redirect):     https://idp.example.org/saml/sso/redirect
SP ACS (POST):          https://sp.example.org/login/saml2/sso/corporate
IdP SLO (Redirect):     https://idp.example.org/saml/slo
SP SLO (POST):          https://sp.example.org/logout/saml2/slo
~~~

In this scenario, the SP sends AuthnRequest via Redirect to **IdP SSO**, and the IdP POSTs Response back to **SP ACS**. When the SP initiates federated logout, it can send LogoutRequest via Redirect to **IdP SLO**, then receive LogoutResponse at **SP SLO** using bindings supported by both sides. Keep **endpoints** and **message transport bindings** distinct to configure correctly.

## 7. SAML Endpoints in Spring Security Servlet

Spring Security provides `RelyingPartyRegistration` holding SP configuration and IdP metadata. Servlet applications use `saml2Login` to create AuthnRequests/receive Responses, `saml2Metadata` to publish SP metadata, and `saml2Logout` when SLO coordination is needed.

| Common Spring Security path | Function |
| --- | --- |
| `/saml2/authenticate/{registrationId}` | **SP trigger point**: generates/sends AuthnRequest to IdP SSO. Not an SP `SingleSignOnService`. |
| `/login/saml2/sso/{registrationId}` | **SP ACS**: receives `SAMLResponse` and authenticates. |
| `/logout/saml2/slo` | **SP SLO** when enabled: receives LogoutRequest/LogoutResponse. |
| `/saml2/metadata` | **Publishes SP metadata**; not an endpoint for login/logout. |
| `/saml2/metadata/{registrationId}` | Publishes metadata for a specific registration; also has the variant `/saml2/service-provider-metadata/{registrationId}`. |
| `POST /logout` | Logout request from the application; can initiate SLO **if** enabled and supported by the registration. |

These paths are **defaults/variants in current Spring Security Servlet documentation**; they may differ with custom configuration or across versions. The actual SAML Response handler and the published `AssertionConsumerService.Location` **must remain consistent**.

### 7.1. Configuring IdP Metadata and SP SLO

Example `application.yml` in a **Spring Boot application** with `spring-security-saml2-service-provider`:

~~~yaml
spring:
  security:
    saml2:
      relyingparty:
        registration:
          corporate:
            assertingparty:
              metadata-uri: https://idp.example.org/metadata
            signing:
              credentials:
                - private-key-location: classpath:credentials/sp-signing.key
                  certificate-location: classpath:credentials/sp-signing.crt
            singlelogout:
              url: "{baseUrl}/logout/saml2/slo"
~~~

The example assumes the system **already has** a valid private key, X.509 certificate, IdP metadata, and SLO support. The files under `credentials/` are illustrative paths for a deployed application; no secret material is supplied in this lesson. When you only need initial SSO and the IdP does not support SLO, do not declare SLO/signing as if it were already operational.

### 7.2. Configuring `SecurityFilterChain`

File `src/main/java/example/federation/SamlEndpointsSecurityConfig.java`:

~~~java
package example.federation;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class SamlEndpointsSecurityConfig {

    @Bean
    SecurityFilterChain filterChain(HttpSecurity http) throws Exception {
        http.authorizeHttpRequests(auth -> auth
                .requestMatchers("/public/**", "/error").permitAll()
                .anyRequest().authenticated())
            .saml2Login(Customizer.withDefaults())
            .saml2Metadata(Customizer.withDefaults())
            .saml2Logout(Customizer.withDefaults());
        return http.build();
    }
}
~~~

This is a **Spring Security configuration inside a Spring Boot project** and **cannot be compiled standalone with `javac`** without Spring libraries and a real registration. `saml2Login` handles SSO, `saml2Metadata` enables publishing SP metadata, and `saml2Logout` enables SLO when supported by the registration and IdP. Do not build a custom servlet controller receiving SAML XML that bypasses framework validation.

Important runtime components:

- `Saml2WebSsoAuthenticationRequestFilter`: handles the initiation endpoint, builds/sends `AuthnRequest` based on IdP SSO configuration.
- `Saml2AuthenticationRequestRepository`: stores pending requests and correlation state (defaults to HttpSession in common setups).
- `Saml2WebSsoAuthenticationFilter` along with the authentication provider: processes responses at the ACS, verifying before creating a session.
- `Saml2MetadataFilter`/`saml2Metadata` configuration: serves SP metadata XML.
- SAML logout filters/resolvers: process `LogoutRequest` and `LogoutResponse` per registration and configured keys/trust.

**If customizing `loginProcessingUrl`**, you must also update `assertionConsumerServiceLocation` in `RelyingPartyRegistration` or the corresponding config, then re-register metadata/ACS at the IdP. If changing the SLO path, update both the runtime handler **and** the SP's `SingleLogoutService.Location`; never change just one side.

### 7.3. Hostnames and Reverse Proxies

The SP might run internally at `http://localhost:8080` while users access `https://sp.example.org`. If metadata outputs `http://localhost:8080/login/saml2/sso/corporate`, the IdP will send responses to an externally unreachable address or the validator will detect a `Destination`/`Recipient` mismatch. Configure the public `{baseUrl}`, trust forwarded headers only from appropriate proxies, and **inspect the published SP metadata** to confirm entity ID, ACS, and SLO all use the public host/scheme/context path.

When the IdP sends a SAML Response via cross-site HTTP-POST, the browser's session cookie may be affected by `SameSite`. Address this using proper session/correlation mechanisms and cookie configuration, **never by disabling `InResponseTo` checks** just to let callbacks pass.

## 8. Metadata Publishes Capabilities, Not Self-Established Trust

Metadata can contain `KeyDescriptor` with signing/encryption keys, endpoints, bindings, and metadata expiration. However, **being able to parse XML does not mean the partner is permitted to be trusted**.

During deployment you must:

1. Accept IdP metadata only from an **authorized and authenticated administrative source**; verify the metadata signature with a trusted trust anchor if applicable. Do not treat a certificate inside unverified XML as proof to trust that same XML.
2. `Response`/`Assertion` verification keys must come from registered partners, checking key usage and **certificate rotation** plans; manage `validUntil`, `cacheDuration`, and refresh timing properly.
3. Never use an `entityID`, `Location`, or ACS URL received from an unverified request to automatically create a new SAML registration.
4. Verify the XML signature on the right element, issuer, `Destination`, `Recipient`, audience, `Conditions` (including timestamps), `SubjectConfirmation`, and replay protection; use a trusted SAML library.
5. For SP-initiated SSO, `InResponseTo` must point to an `AuthnRequest` stored in the **initiating browser session/transaction**, not rely solely on `RelayState` from the callback.
6. If allowing IdP-initiated SSO without a prior AuthnRequest, apply a **dedicated policy**; never silently fall back a failed SP-initiated transaction into unsolicited mode to bypass constraints.
7. For SLO, verify issuer/signature/destination, NameID/SessionIndex, and matching request-response state; do not log out the wrong session.
8. Never disable validators to "fix" endpoint configuration errors. Fix the mismatched metadata, keys, bindings, or runtime handlers.

Metadata only helps establish **addresses and trust relationships**; after login, access to APIs, resources, tenants, and records is still enforced by the SP/API authorization layer.

## 9. Common Integration Errors and Verification Methods

| Symptom | Possible Cause | Appropriate Check |
| --- | --- | --- |
| SP sends `AuthnRequest` to the SP's own URL. | Confusing `AssertionConsumerService.Location` with IdP `SingleSignOnService.Location`. | Trace where the request is sent; it must be **IdP SSO**. |
| IdP reports "ACS mismatch" or "Reply URL invalid". | ACS does not match IdP metadata/registration, wrong scheme/hostname/port/path. | Compare ACS Location, IdP config, and public URL behind proxy. |
| IdP accepts Redirect request but POST callback returns 404/405. | SP runtime lacks an ACS handler or does not accept the published binding/method. | Check SP `AssertionConsumerService.Binding/Location` and actual route. |
| Login fails because "SSO Redirect differs from ACS POST". | Conflating the bindings of the two legs. | Redirect applies to SP→IdP, POST applies to IdP→SP; having different bindings is valid. |
| `AudienceRestriction` fails. | SP entityID does not match assertion audience. | Read SP `EntityDescriptor/@entityID`; do not compare audience with ACS URL. |
| `Destination`/`Recipient` mismatch. | IdP returns to the wrong ACS URL or proxy alters the public URL. | Match SAML Response/SubjectConfirmationData against the published ACS. |
| Pending `AuthnRequest` not found / `InResponseTo` mismatch. | Lost session/cookie, changed transaction, callback in wrong browser. | Check correlation, SameSite cookies, TTL, multi-instance storage. |
| `POST /logout` succeeds yet IdP remains logged in. | Local logout only, missing SLO metadata/keys/feature. | Inspect both IdP and SP SLO endpoints, `saml2Logout`, and registration signing credentials. |
| `LogoutResponse` sent to ACS. | Confusing the SP's SLO endpoint with the ACS endpoint. | Check the receiver's `SingleLogoutService.Location/ResponseLocation`. |
| Response/XML is signed yet SP still rejects it. | Wrong audience, issuer, timestamp, recipient, binding, or `InResponseTo`. | Check each validator without bypassing signature/correlation checks. |
| Mass login failures after certificate rotation. | Metadata/trusted keys not updated on time. | Manage refresh, certificates in `KeyDescriptor`, and safe rollover. |
| Metadata emits `localhost` URLs. | SP generates metadata from internal scheme/host behind a proxy. | Configure external base URL and forwarded headers, re-export XML and verify. |

### Testing SSO and SLO Flows

1. **Normal SSO:** user visits SP → sends AuthnRequest to exact IdP SSO binding/location → IdP POSTs Response to exact SP ACS → valid session.
2. **Unsupported binding:** IdP configured for HTTP-Redirect only, while SP tries to POST AuthnRequest. Expected: configuration/login error; do not automatically send to another unregistered endpoint.
3. **Wrong ACS:** IdP POSTs to an old or wrong URL. Expected: no session created, diagnose partner/proxy configuration.
4. **Wrong audience/destination:** assertion intended for another entityID or URL. Expected: rejected even if signature is valid.
5. **Replayed/wrong-session Response:** `InResponseTo` mismatches or response is replayed. Expected: rejected, never bypass correlation.
6. **SP-initiated and IdP-initiated SLO:** both directions must use the right SLO `Location`/`ResponseLocation`, binding, signature, and matching session; also handle errors/partial logout.
7. **Key rotation/metadata expiry:** after updating trusted metadata, transactions still verify properly, and unknown keys from callbacks are never accepted.

### Self-Check Questions

- **Which URL does the IdP need to send the SAML Response?** SP `AssertionConsumerService.Location`, with the agreed binding.
- **Which URL does the SP need to send AuthnRequest?** IdP `SingleSignOnService.Location`, using that entry's binding.
- **If IdP SSO uses HTTP-Redirect, can ACS use HTTP-POST?** Yes; the two legs are independent.
- **In `AuthnRequest`, which leg does `ProtocolBinding=HTTP-POST` refer to?** The binding the IdP uses to return **Response to the ACS**.
- **Why do both IdP and SP have SLO endpoints?** Because either side may need to receive LogoutRequest/LogoutResponse.
- **Is `ResponseLocation` on SLO a fallback path?** No; it separates the response destination from the request destination when provided.
- **Can the Metadata URL be used as the ACS URL?** No; the metadata URL serves configuration XML, whereas the ACS receives actual SAML responses.

## 10. Key Takeaways

- **SSO = IdP receives login requests**, **ACS = SP receives login results**, **SLO = party receiving logout messages**.
- **Binding + Location** must travel together and belong to the right role in metadata.
- **Entity ID**, metadata URL, ACS, SSO, and SLO are identifiers/addresses with **distinct responsibilities**.
- **SSO request binding** and **ACS response binding** can differ.
- **Spring Security** provides filters for AuthnRequest, ACS, SLO, and publishing metadata, but metadata must match **the runtime handler and configured partner**.
- **Valid signatures, correct endpoints, proper correlation, and valid timestamps** are all required for a secure login.

## References

- [Spring Security — SAML 2.0 Login Overview](https://docs.spring.io/spring-security/reference/servlet/saml2/login/overview.html)
- [Spring Security — SAML 2.0 Metadata](https://docs.spring.io/spring-security/reference/servlet/saml2/metadata.html)
- [Spring Security — SAML AuthnRequest](https://docs.spring.io/spring-security/reference/servlet/saml2/login/authentication-requests.html)
- [Spring Security — Authenticating SAML Responses](https://docs.spring.io/spring-security/reference/servlet/saml2/login/authentication.html)
- [Spring Security — Single Logout](https://docs.spring.io/spring-security/reference/servlet/saml2/logout.html)
- [OASIS SAML V2.0 Core](https://docs.oasis-open.org/security/saml/v2.0/saml-core-2.0-os.pdf)
- [OASIS SAML V2.0 Errata 05 — ResponseLocation](https://docs.oasis-open.org/security/saml/v2.0/errata05/csd01/saml-v2.0-errata05-csd01.html)
