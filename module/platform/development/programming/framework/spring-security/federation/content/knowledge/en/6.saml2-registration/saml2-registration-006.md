# Configuring SSO Endpoint, Binding, and AuthnRequest Signing Requirements in SAML 2.0

> **Context:** Spring Security – federation → SAML2 Registration. This lesson guides you through identifying the **right IdP SSO endpoint**, **the right HTTP binding to send AuthnRequest**, **the right signing requirement and SP key pair**, and then aligning them with the **ACS endpoint receiving SAMLResponse** in Spring Security. All URLs and certificates in the examples belong to a simulated environment.

## 1. Objectives and Real-World Problem

When configuring a Spring Boot application as a **SAML Service Provider (SP)**, several URLs and certificates are typically declared. Three questions are easily confused:

1. **Where should `AuthnRequest` be sent?** → To the **SingleSignOnService** (SSO endpoint) published by the **Identity Provider (IdP)**.
2. **How should it be sent?** → The HTTP-Redirect or HTTP-POST binding supported by the IdP and selected by the SP. The two bindings have **different** encoding and signature representations.
3. **Does the IdP require the SP to sign `AuthnRequest`?** → Read the registration policy/metadata and configure the **SP's private signing key** along with the public certificate trusted by the IdP. Do not mistakenly use the certificate meant for verifying **the IdP's SAMLResponse**.

A related question in the opposite direction is **where does the IdP send the login result?** → To the **Assertion Consumer Service (ACS)** published by the **SP**; usually HTTP-POST carrying `SAMLResponse`.

Expected outcome of this lesson: you can explain which fields belong to the IdP vs. the SP, apply corresponding YAML and `SecurityFilterChain` configs, inspect in-flight requests to confirm binding/signature, and troubleshoot common failures without disabling security checks.

## 2. Proper Naming: Login Initiation Endpoint, SSO Service, and ACS

These concepts are closely related yet have **different owners and transmission directions**:

| Component | Owner | Caller | Purpose | Simulated Example |
| --- | --- | --- | --- | --- |
| SP login initiation endpoint | SP / Spring Security | Browser | Creates `AuthnRequest` for the chosen registration | `https://portal.example.org/saml2/authenticate/corp` |
| IdP `SingleSignOnService Location` | IdP | Browser redirected by SP | Receives `AuthnRequest` and authenticates the user | `https://login.example.org/saml/sso/redirect` |
| SP `AssertionConsumerService Location` (ACS) | SP | Browser carrying result from IdP | Receives `SAMLResponse`, validates it, and creates SP session | `https://portal.example.org/login/saml2/sso/corp` |
| SP `entityID` | SP | Embedded in `Issuer`/metadata | Logical identifier of SP; not necessarily an HTTP-serving URL | `https://portal.example.org/saml2/service-provider-metadata/corp` |
| IdP `entityID` | IdP | Used in trust/Issuer | Logical identifier of IdP; not implicitly the SSO URL | `https://login.example.org/saml/metadata` |
| IdP metadata URL or file | IdP operator | SP admin/config init process | Provides entityID, SSO services, signing certificates, flags | `https://login.example.org/saml/metadata.xml` |
| SP metadata endpoint | SP | IdP admin/service during onboarding | Publishes entityID, ACS, supported bindings, signing certificate | `https://portal.example.org/saml2/service-provider-metadata/corp` |

**Mandatory distinctions:**

- The SP's `/saml2/authenticate/corp` **is not** the IdP's SSO endpoint. The browser accesses this path so Spring Security creates the request and redirects to the IdP.
- The IdP's `https://login.example.org/saml/sso/redirect` **is not** the SP ACS. It receives `AuthnRequest`, not `SAMLResponse`.
- `entityID` is not synonymous with an endpoint. It is a trust identifier, even though many implementations use endpoint-like URLs.
- The signature on **AuthnRequest** and the signature on **Response/Assertion** protect two different messages and are **signed by two different parties**; they require different credentials.

## 3. SP-Initiated Web SSO Diagram and Trust Boundaries

Assume a registration named `corp`, where the IdP supports HTTP-Redirect for requests and the ACS uses HTTP-POST for responses:

```text
Browser               Spring Security SP                  SAML IdP
   |                         |                                 |
   | GET /private            |                                 |
   |------------------------>|                                 |
   | 302 /saml2/authenticate/corp                              |
   |<------------------------|                                 |
   | GET /saml2/authenticate/corp                              |
   |------------------------>|                                 |
   |                         | create AuthnRequest (ID, Issuer,|
   |                         | Destination, ACS, timestamp)    |
   |                         | sign per SP/IdP policy          |
   |                         | store request for InResponseTo  |
   | 302 Location: IdP SSO + SAMLRequest + SigAlg + Signature  |
   |<------------------------|                                 |
   | GET /saml/sso/redirect?SAMLRequest=...&SigAlg=...         |
   |---------------------------------------------------------->|
   |                         |                    IdP verifies |
   |                         |                    req/binding  |
   |                         |                    & auths user |
   | HTML form POST SAMLResponse -> SP ACS                     |
   |<----------------------------------------------------------|
   | POST /login/saml2/sso/corp                                |
   |------------------------>|                                 |
   |                         | verify SAMLResponse/assertion   |
   |                         | issuer, signature, audience,    |
   |                         | ACS, time, InResponseTo ...     |
   | Set-Cookie + 302 /private                                 |
   |<------------------------|                                 |
   | GET /private (cookie)   |                                 |
   |------------------------>| check session + authorization   |
```

The diagram illustrates **HTTP-Redirect request + HTTP-POST response**; not every deployment uses this pair. An IdP may support POST for `AuthnRequest`; response binding is a **separate** protocol choice supported by SP/IdP and advertised in ACS metadata.

**Trust boundary:** `SAMLRequest` created by the SP is carried to the IdP by the browser. The IdP does not trust request contents merely because the XML is valid; if policy requires signing, the IdP must verify the signature using the **registered SP public key**. Similarly, `SAMLResponse` POSTed by the browser back to the SP must be validated by the SP against the **configured IdP trust**, never using a key sent by an untrusted caller.

## 4. Reading IdP Metadata to Choose the SSO Endpoint

### 4.1. `SingleSignOnService` Has Binding and Location

IdP metadata can declare **multiple** `SingleSignOnService` entries with the same function but different bindings. Example fragment:

```xml
<md:IDPSSODescriptor
    xmlns:md="urn:oasis:names:tc:SAML:2.0:metadata"
    protocolSupportEnumeration="urn:oasis:names:tc:SAML:2.0:protocol"
    WantAuthnRequestsSigned="true">
    <md:SingleSignOnService
        Binding="urn:oasis:names:tc:SAML:2.0:bindings:HTTP-Redirect"
        Location="https://login.example.org/saml/sso/redirect"/>
    <md:SingleSignOnService
        Binding="urn:oasis:names:tc:SAML:2.0:bindings:HTTP-POST"
        Location="https://login.example.org/saml/sso/post"/>
</md:IDPSSODescriptor>
```

**This is a metadata fragment explaining structure**, not a standalone deployable metadata file: entityID, a trusted metadata distribution mechanism, and IdP/SP certificate details are still needed per real configuration. Key takeaways:

- `Binding` is the URI specifying **how `AuthnRequest` is transported to that endpoint**. In the example, the IdP advertises two options.
- `Location` is the **target IdP URL** for the corresponding binding. Never replace the Redirect endpoint with the POST endpoint unless advertised/approved by the IdP.
- `WantAuthnRequestsSigned="true"` is the **IdP's expected policy**: the IdP wants the SP to sign authentication requests. Enforcement details vary by vendor, but when configuring the contract treat this as a requirement to fulfill.
- Metadata usually also contains `KeyDescriptor` so the SP can verify SAMLResponse/assertion signatures issued by the IdP, plus logout services. Do not mistake `SingleLogoutService` for `SingleSignOnService`.

**How to choose an endpoint:** fetch metadata from a verified source, locate the approved IdP entityID, select a `SingleSignOnService` mutually supported by Spring Security/IdP for the desired binding, and test actual behavior. Do not infer binding from path suffixes like `/redirect` or `/post`; the authoritative source is the `Binding` attribute/contract, not the URL name.

### 4.2. What Must Accompany Metadata?

At minimum, confirm:

1. Exact **IdP entityID** and owning organization.
2. Exact **SSO Location and Binding** (there are often separate sandbox/production environments).
3. Request signing policy: `WantAuthnRequestsSigned` in metadata **and** actual IdP enforcement; sometimes the app configuration inside the IdP requires stricter rules than metadata advertises.
4. Trusted **IdP signing certificate** set so the SP can verify responses/assertions.
5. Contract for **SP entityID, ACS Location/Binding, and SP signing certificate** registered on the IdP side.
6. Certificate rotation and metadata update process: who approves, when old keys start/stop being trusted, and pre-production testing steps.

**Never trust arbitrary metadata from browser requests.** Letting external users supply a metadata URL/certificate in a query parameter to create a new registration allows them to influence the SP's trust anchors. Trusting an IdP must be an independent configuration/admin decision.

### 4.3. SP Metadata: ACS and Publishing Signing Capability

On the SP side, a metadata fragment might look like:

```xml
<md:SPSSODescriptor
    xmlns:md="urn:oasis:names:tc:SAML:2.0:metadata"
    protocolSupportEnumeration="urn:oasis:names:tc:SAML:2.0:protocol"
    AuthnRequestsSigned="true"
    WantAssertionsSigned="true">
    <md:AssertionConsumerService
        index="0"
        isDefault="true"
        Binding="urn:oasis:names:tc:SAML:2.0:bindings:HTTP-POST"
        Location="https://portal.example.org/login/saml2/sso/corp"/>
</md:SPSSODescriptor>
```

This fragment is also trimmed for explanation, omitting `EntityDescriptor`/`KeyDescriptor` and not representing complete production metadata.

- `AuthnRequestsSigned` on **SPSSODescriptor** advertises that **the SP signs AuthnRequests**.
- `WantAuthnRequestsSigned` on **IDPSSODescriptor** advertises that **the IdP wants the SP to sign AuthnRequests**. These are **two attributes on two sides**; avoid mixing them up.
- `WantAssertionsSigned` means **the SP expects the IdP to sign SAML Assertions**. It is not equivalent to `AuthnRequestsSigned` or the AuthnRequest signing policy; SAML Response/Assertion validation still requires separate configuration and testing.
- `AssertionConsumerService.Binding` describes the binding for **SAMLResponse returning to the SP ACS**. It does not force `AuthnRequest` to use POST.
- When the SP signs requests, metadata must publish the matching **SP public signing certificate** so the IdP can verify them. **The SP's private signing key never belongs in metadata**.

## 5. Binding: How AuthnRequest Is Transported

**Binding** is the convention for representing SAML messages over HTTP, including HTTP method, encoding, and signature placement. Two common bindings are `urn:oasis:names:tc:SAML:2.0:bindings:HTTP-Redirect` and `urn:oasis:names:tc:SAML:2.0:bindings:HTTP-POST`.

### 5.1. HTTP-Redirect Binding (SP → IdP)

For `AuthnRequest` over Redirect binding:

1. The SP constructs `<samlp:AuthnRequest>` XML containing ID, IssueInstant, Issuer, and destination info.
2. The XML is **compressed with raw DEFLATE**, Base64-encoded, and URL-encoded into the `SAMLRequest` query parameter per the binding specification.
3. The browser receives HTTP `302/303 Location` pointing to the IdP's `SingleSignOnService Location`, carrying `SAMLRequest`.
4. If signing the request under **Redirect binding**, the SP appends `SigAlg` and `Signature` to the **query string**. The signed payload is the concatenated parameter string **in canonical order and encoding**, not the raw XML or full URL.
5. The IdP decodes/decompresses and verifies the signature per binding/policy before accepting the request.

Important parameter names:

| Parameter | Role |
| --- | --- |
| `SAMLRequest` | Encoded AuthnRequest for transport |
| `RelayState` | State used to correlate flows/indicate return target per application rules; optional |
| `SigAlg` | Signature algorithm URI, e.g., RSA-SHA256 URI |
| `Signature` | Signature over the prescribed parameter string |

Format of the string to sign when `RelayState` is present:

```text
SAMLRequest=<URL-encoded value>&RelayState=<URL-encoded value>&SigAlg=<URL-encoded value>
```

When `RelayState` is absent, the string to sign consists only of `SAMLRequest` and `SigAlg` in that order. `Signature` is the encoded signature output; **never include `Signature` itself in the data being signed**. `<URL-encoded value>` above is syntax notation describing the format, not a literal transmittable value.

**Common mistakes:**

- Using HTTP Redirect yet checking inside AuthnRequest XML for `<ds:Signature>` and concluding "unsigned". Under Redirect binding, **the signature resides in the query parameters**.
- Running Base64 decode directly and parsing XML while skipping DEFLATE inflation, causing invalid XML errors.
- Manually assembling `SigAlg` and `Signature` with non-standard encoding or wrong parameter order, causing IdP verification failure.
- Treating HTTPS as a substitute for AuthnRequest signing: TLS protects transport, but does not authenticate the message under the IdP's trust policy.

**URL length note:** Redirect binding puts the payload in the URL, where proxies/browsers enforce varying length limits. Typical AuthnRequests are relatively small, but if large requests must be sent or required by a specific IdP, consider POST binding per policy rather than trimming XML or weakening validation.

### 5.2. HTTP-POST Binding (SP → IdP)

With POST binding:

1. The SP constructs `AuthnRequest` XML.
2. If the request must be signed, under POST binding the signature is **typically an XML Digital Signature** inside the XML message, verified per XML Signature/SAML profile.
3. The XML (signed if applicable) is Base64-encoded into the `SAMLRequest` form field in a POST form targeted at the IdP's `SingleSignOnService Location`.
4. The browser submits the POST form to the IdP. `RelayState` can be another form field.
5. The IdP decodes and verifies the XML signature using the registered SP certificate.

HTML diagram **illustrating the mechanism**, not to be used to hand-craft production requests:

```html
<form method="post" action="https://login.example.org/saml/sso/post">
  <input type="hidden" name="SAMLRequest"
         value="PHNhbWxwOkF1dGhuUmVxdWVzdA==">
  <input type="hidden" name="RelayState" value="opaque-state-7"/>
  <button type="submit">Continue SSO</button>
</form>
```

The `SAMLRequest` value above is **mock data**, not a signed, complete, or usable AuthnRequest for login. Spring Security generates and encodes the form per binding; do not put signature creation/modification logic into custom HTML controllers.

### 5.3. Comparing Redirect and POST

| Criterion | HTTP-Redirect | HTTP-POST |
| --- | --- | --- |
| Browser → IdP method | GET after redirect | POST of an HTML form |
| Where request lives | `SAMLRequest` query parameter | `SAMLRequest` form field |
| Core encoding | Raw DEFLATE → Base64 → URL encoding | Base64 of XML |
| Typical request signature | `SigAlg` and `Signature` in query string | `<ds:Signature>` inside XML before Base64 |
| Common pitfalls | Wrong URI-encoding, wrong signing data order, URL length | XML signature/reference, form POST/Content Security Policy |
| Relation to response | Governs **request** to IdP only | Also governs **request** to IdP only |
| Forces ACS response to POST? | No | No |

**Important:** The binding for **AuthnRequest** and for **SAMLResponse** are two independent choices. A common setup: Redirect AuthnRequest from SP to IdP, then POST SAMLResponse from IdP to SP. Never change `acs.binding` to Redirect just because `singlesignon.binding=REDIRECT`.

### 5.4. Other Bindings

SAML also defines HTTP-Artifact, SOAP/back-channel, and other profiles/bindings. They have separate exchange mechanics and library support; never assume any SSO endpoint works simply by changing an enum to `ARTIFACT` or `SOAP`. For standard Servlet Spring Security `saml2Login`, verify the exact bindings supported by your application version and IdP metadata.

## 6. Which AuthnRequest Fields Relate to Routing and Signing?

Illustrative XML **without signature** so learners can read the structure first:

```xml
<samlp:AuthnRequest
    xmlns:samlp="urn:oasis:names:tc:SAML:2.0:protocol"
    xmlns:saml="urn:oasis:names:tc:SAML:2.0:assertion"
    ID="_req-20261107-a1"
    Version="2.0"
    IssueInstant="2026-11-07T03:10:00Z"
    Destination="https://login.example.org/saml/sso/redirect"
    AssertionConsumerServiceURL="https://portal.example.org/login/saml2/sso/corp"
    ProtocolBinding="urn:oasis:names:tc:SAML:2.0:bindings:HTTP-POST">
    <saml:Issuer>https://portal.example.org/saml2/service-provider-metadata/corp</saml:Issuer>
    <samlp:NameIDPolicy
        Format="urn:oasis:names:tc:SAML:1.1:nameid-format:unspecified"
        AllowCreate="true"/>
</samlp:AuthnRequest>
```

| Field | Meaning | Common Mistakes |
| --- | --- | --- |
| `ID` | Unique request identifier; IdP may echo it in `InResponseTo` | Reusing IDs or failing to store request for correlation |
| `Version` | Protocol version, typically `2.0` | Changing version improperly |
| `IssueInstant` | Timestamp when AuthnRequest was created | Excessive clock skew; IdP rejects stale/future requests |
| `Destination` | **IdP SSO endpoint** URL the request is sent to | Putting the ACS URL into Destination |
| `Issuer` | **SP entityID**; who is sending the AuthnRequest | Entering the IdP entityID |
| `AssertionConsumerServiceURL` | **SP ACS** where the IdP should send the response | Wrong host/HTTPS/path/trailing slash, mismatching metadata |
| `ProtocolBinding` | Binding **at which the SP expects SAMLResponse at the ACS** | Mistaking it for the request binding sent to the IdP |
| `AssertionConsumerServiceIndex` | Index of an ACS registered in SP metadata, alternative to ACS URL | Sending an index absent from metadata |
| `NameIDPolicy` | Requested NameID format/creation allowance per IdP capability | Forcing an unsupported format |
| `ForceAuthn` | Requests re-authentication if applicable | Setting true unconditionally causing unnecessary re-login prompts |
| `IsPassive` | Restricts interactive authentication when requested | Using without understanding that the IdP may reject the request |

Fields to emphasize:

- **`ProtocolBinding=HTTP-POST` does not conflict with sending AuthnRequest via Redirect**, because this field describes the *response* binding.
- `Destination` and `Issuer` are completely different: Destination is the **IdP** URL, Issuer is the **SP** logical identifier.
- `AssertionConsumerServiceURL` in the request must be trusted by the IdP as a valid ACS for the SP; it must not force the IdP to send assertions to an arbitrary browser-supplied URL.
- Do not send both `AssertionConsumerServiceIndex` and `AssertionConsumerServiceURL` simultaneously if the profile/spec treats them as mutually exclusive; follow metadata and IdP behavior.
- `RelayState` **is not inside AuthnRequest XML** in common HTTP bindings; it is an external parameter/field alongside the message that must be generated and bound securely.
- `InResponseTo` is an attribute on the response/subject confirmation linking back to the prior request, **not an attribute on the original AuthnRequest**.

### 6.1. What Does the SP Emit and What Must the IdP Verify?

When the IdP requires signed requests, the IdP must verify at least:

1. The request belongs to a **registered SP**; `Issuer` matches the SP entityID.
2. The signature is valid for the binding actually used, verified with the trusted **SP signing public certificate**.
3. `Destination`/SSO endpoint matches, the request is not expired per IdP policy, and ID/replay controls apply if configured.
4. `AssertionConsumerServiceURL` or `AssertionConsumerServiceIndex` is in the registered ACS list; the response binding is supported.
5. Fields such as NameIDPolicy/ForceAuthn/RequestedAuthnContext (if present) are handled per IdP policy.

In the reverse direction, the SP must verify the response/assertion using the IdP's signing key and `Issuer`/`Audience`/`Recipient`/`Destination`/time/`InResponseTo`/anti-replay per policy. **An IdP verifying a signed AuthnRequest does not exempt validation on the response side.**

## 7. AuthnRequest Signing Policy: Who Requires, Who Signs, Who Verifies?

### 7.1. Three Easily Confused Concepts

| Attribute / Config | Which Side | Interpretation |
| --- | --- | --- |
| `IDPSSODescriptor WantAuthnRequestsSigned` | **IdP** metadata | IdP **expects the SP to sign AuthnRequests** |
| `SPSSODescriptor AuthnRequestsSigned` | **SP** metadata | SP **advertises that it signs AuthnRequests** |
| `RelyingPartyRegistration` signing credentials | **SP** config | Holds private key/certificate so the SP actually **creates signatures** |

Do not treat a flag in metadata as proof that "a signature is present". Only a wire-level request carrying the binding's signature proves the SP actually signed. Furthermore, **the IdP must know and trust the corresponding SP certificate in advance**; a certificate in metadata is exchanged data whose source trust must still be governed.

### 7.2. Signing On/Off Matrix and Consequences

| IdP Requires Signing? | SP Configured to Sign? | SP Has Valid Signing Key? | Outcome / Assessment |
| --- | --- | --- | --- |
| Yes | Yes | Yes | Matches policy, but test algorithm, certificate, and binding |
| Yes | No | No/Yes | IdP must reject if enforcing policy; enable signing |
| Yes | Yes | No | SP cannot sign properly; config or runtime error |
| No | Yes | Yes | Can be valid; SP may opt to sign for higher assurance if IdP supports it |
| No | No | No | Can work if both agree, but assess request injection/registration risks before deploying |
| Unclear | Any | Any | Not ready for production; inspect metadata, vendor docs, and IdP app config |

**Right mindset:** "signing not required" is a **policy decision**, not a default workaround when hitting errors. With some IdPs, **the SP can proactively sign** even if the IdP says it is optional; actual behavior depends on flags and how Spring Security handles them in your version.

### 7.3. Two Key Sets That Must Never Be Swapped

```text
SP signs AuthnRequest:
  SP private signing key  --signs-->     AuthnRequest
  SP signing certificate  --published--> IdP uses to verify request

IdP signs SAMLResponse / Assertion:
  IdP private signing key --signs-->     Response/Assertion
  IdP signing certificate --published--> SP uses to verify response
```

In Spring Boot, there are consequently two distinct property groups:

- `registration.corp.signing.credentials`: **SP's private key + certificate** to sign requests or SP-configured outbound messages.
- `registration.corp.assertingparty.verification.credentials`: **IdP's public certificate** for the SP to verify messages/assertions signed by the IdP.

**Never use the IdP verification certificate as the SP's private signing key.** A public certificate alone cannot sign; signing requires the matching private key. If the SP holds a key to sign `AuthnRequest`, that secret must be protected by secret management, file permissions, auditing, and rotation procedures. Never commit private keys to Git.

### 7.4. Algorithms and Signature Types

- For HTTP-Redirect, the signature goes in `SigAlg`/`Signature` of the **URL query**, computed over the parameter string per the SAML binding.
- For HTTP-POST, AuthnRequest signing typically uses **XML Digital Signature** attached to the XML message.
- RSA-SHA256 is a common choice; the actual algorithm must be compatible with IdP policy, JCA/OpenSAML, and the certificate. Avoid allowing SHA-1 or weak algorithms just to "get past an error".
- SP signing keys/certificates can be rotated on schedule: the IdP must know the new public key before the SP starts signing with the new private key; ensure controlled transition and rollback.
- Metadata describes supported/preferred signing algorithms when provided by the IdP; never alter the `SigAlg` URI in the request while actually signing with a different algorithm.

**Important on wire-level verification:** A signed Redirect request will not contain `<ds:Signature>` inside the XML yet is still valid. A signed POST XML request containing `<ds:Signature>` must have its references/canonicalization validated properly; merely seeing a `Signature` tag does not prove validity.

## 8. Spring Boot Config: Signed Redirect AuthnRequest

Example targeting **Spring Boot 3.x / Spring Security 6.x**. Filenames and URLs here describe a simulated environment. To run in reality, supply valid keys/certificates, configure the corresponding SP application on the IdP, and confirm the active property version.

### 8.1. Illustrative `application.yml`

```yaml
spring:
  security:
    saml2:
      relyingparty:
        registration:
          corp:
            entity-id: "{baseUrl}/saml2/service-provider-metadata/{registrationId}"
            acs:
              location: "{baseUrl}/login/saml2/sso/{registrationId}"
              binding: POST
            signing:
              credentials:
                - private-key-location: "file:/run/secrets/sp-signing.key"
                  certificate-location: "file:/run/config/sp-signing.crt"
            assertingparty:
              entity-id: "https://login.example.org/saml/metadata"
              verification:
                credentials:
                  - certificate-location: "file:/run/config/idp-signing.crt"
              singlesignon:
                url: "https://login.example.org/saml/sso/redirect"
                binding: REDIRECT
                sign-request: true
```

Data-path explanation:

| Property | Exact Meaning | Data Source Owner |
| --- | --- | --- |
| `registration.corp` | Internal Registration ID for Spring to choose IdP/SP config | SP |
| `entity-id` | SP entityID (Issuer in AuthnRequest) | Registered jointly by SP and IdP |
| `acs.location` | SP ACS to receive responses | SP, must be trusted by IdP |
| `acs.binding=POST` | Binding of response to ACS, independent of request binding | SP and IdP |
| `signing.credentials[*].private-key-location` | **SP private key** for request signatures | SP secret store |
| `signing.credentials[*].certificate-location` | Matching public certificate for SP signing key | SP, provided to IdP |
| `assertingparty.entity-id` | Trusted IdP entityID | IdP metadata/registration |
| `assertingparty.verification.credentials[*]` | IdP **public signing cert** to verify response/assertion | Trusted IdP metadata |
| `assertingparty.singlesignon.url` | **IdP target receiving AuthnRequest** | IdP metadata |
| `assertingparty.singlesignon.binding=REDIRECT` | Request binding sent from SP to IdP | IdP metadata + SP |
| `assertingparty.singlesignon.sign-request=true` | Expectation to sign AuthnRequest per registration config | SP/IdP policy |

**Do not confuse "certificate-location" between signing and verification.** The complete relationship is: the SP's private signing key must match the SP certificate registered at the IdP; the IdP's public certificate must match the Response/Assertion signature and issuer trusted by the SP.

`{baseUrl}` and `{registrationId}` are **standard Spring Security placeholders in URI patterns**, distinct from lesson placeholders. `{baseUrl}` resolves from the request's public scheme/host/port; behind a reverse proxy, forwarded headers must be configured properly to produce an accurate absolute ACS.

### 8.2. Spring Security Configuration Class

Create `SamlSpSecurityConfiguration.java` in the source set of a Spring Boot application with Spring Security and the SAML2 Service Provider dependency:

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class SamlSpSecurityConfiguration {

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http) throws Exception {
        http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/public/**").permitAll()
                .anyRequest().authenticated())
            .saml2Login(Customizer.withDefaults());

        return http.build();
    }
}
```

This is a **complete Spring class**, yet **not a standalone Java program runnable with `java SamlSpSecurityConfiguration`**. Running it requires a Spring Boot application, SAML2 dependency, and real credentials/config. `saml2Login()` installs the filter chain for SAML Web SSO; the class itself neither contains private keys nor verifies the IdP's HTTP Redirect signature directly. Spring Security/OpenSAML manages request creation and response verification per registration.

When navigating to:

```text
GET https://portal.example.org/saml2/authenticate/corp
```

Spring Security selects registration `corp`, creates `AuthnRequest`, sends it to `https://login.example.org/saml/sso/redirect` over HTTP-Redirect, and signs per policy/credentials. After login, the IdP POSTs `SAMLResponse` to the SP's ACS URL, and Spring Security verifies it before creating `Authentication`.

**Version note:** SAML configuration APIs evolve across Spring Security releases. Check the Javadoc/Reference for your deployed version, especially builder APIs and property aliases like `sso-url`/`singlesignon.url`. Always inspect **actual requests** and deployed metadata rather than inferring solely from YAML.

### 8.3. Switching to POST Binding for AuthnRequest

If IdP metadata/contract requires sending AuthnRequest via POST, change the **request binding portion** to:

```yaml
spring:
  security:
    saml2:
      relyingparty:
        registration:
          corp:
            assertingparty:
              singlesignon:
                url: "https://login.example.org/saml/sso/post"
                binding: POST
                sign-request: true
```

This is a **corresponding override fragment**, not a complete application config; keep the SP signing/IdP verification/ACS/entityID entries from the earlier example. After changing, the browser must send an HTML POST carrying `SAMLRequest` to the IdP POST URL; request signing must match **POST/XML Signature**. **Do not change `acs.binding` out of habit:** responses can still POST back to the SP as before.

### 8.4. When the IdP Allows Unsigned Requests

Only when **IdP metadata/policy has confirmed** that requests may be unsigned can the SP use:

```yaml
spring:
  security:
    saml2:
      relyingparty:
        registration:
          corp:
            assertingparty:
              singlesignon:
                sign-request: false
```

This snippet is a **policy override fragment**, not a complete application configuration. If the SP is already configured to **proactively sign AuthnRequests** (e.g., via builder flag `authnRequestsSigned(true)`), requests may still be signed even when optional for the IdP. Only assert "unsigned" after inspecting emitted wire data and actual behavior in the running version.

The rationale for disabling signing must be documented in the threat model and IdP/SP contract. Never disable signing to mask private key issues, certificate mismatches, wrong endpoints, or weak algorithms.

## 9. Configuration via Metadata and Java Builder

Spring Security represents each SP–IdP pair with `RelyingPartyRegistration`, stored in `RelyingPartyRegistrationRepository` (e.g., `InMemoryRelyingPartyRegistrationRepository`). One registration encapsulates:

- **Relying party/SP:** `registrationId`, SP `entityId`, ACS location/binding, signing credentials, and decryption credentials if used.
- **Asserting party/IdP:** IdP `entityId`, SSO service location/binding, `wantAuthnRequestsSigned`, verification credentials, and signing algorithms.

### 9.1. Trusted Metadata Source

Use IdP metadata vetted by administrators. Example Java fragment in Spring Security 6.x using the `RelyingPartyRegistrations` API:

```java
import org.springframework.security.saml2.provider.service.registration.RelyingPartyRegistration;
import org.springframework.security.saml2.provider.service.registration.RelyingPartyRegistrations;

// Fragment inside a @Bean or configuration method.
// Source metadata has already been verified by an administrator.
RelyingPartyRegistration registration =
        RelyingPartyRegistrations
            .fromMetadataLocation("classpath:corp-idp-metadata.xml")
            .registrationId("corp")
            .build();
```

This is a **fragment**, not a standalone Java class. It reads IdP details from a controlled metadata file; the application still must register SP entityID/ACS/certificate, add **SP signing credentials** if requests are signed, and set policies required by the IdP.

### 9.2. Adjusting Request Binding and Signing Requirements

On builder APIs appropriate for Spring Security versions supporting `assertingPartyMetadata(...)`, you can specify:

```java
import org.springframework.security.saml2.provider.service.registration.RelyingPartyRegistration;
import org.springframework.security.saml2.provider.service.registration.RelyingPartyRegistrations;
import org.springframework.security.saml2.provider.service.registration.Saml2MessageBinding;

// Fragment of a registration bean (not a standalone runnable program).
RelyingPartyRegistration registration =
        RelyingPartyRegistrations
            .fromMetadataLocation("classpath:corp-idp-metadata.xml")
            .registrationId("corp")
            .assertingPartyMetadata(party -> party
                .singleSignOnServiceBinding(Saml2MessageBinding.POST)
                .wantAuthnRequestsSigned(true))
            .build();
```

Verify that **the metadata actually contains an SSO POST endpoint**; changing the binding while keeping the Redirect SSO URL can cause the IdP to reject it as unsupported. The builder example above does not yet add an SP signing key, so when enabling signed requests provide `signingX509Credentials` on the registration (or equivalent YAML config). In older 6.x versions, the builder method may be `assertingPartyDetails(...)` instead of `assertingPartyMetadata(...)`; check version docs before copying.

**Do not confuse `wantAuthnRequestsSigned(true)` and `authnRequestsSigned(true)`:** one is IdP-side policy, the other expresses SP-side request signing. Spring Security uses them to decide whether to sign based on settings. If uncertain of the effective state, inspect the resolved configuration and wire-level request.

## 10. Verifying Endpoints and Bindings After Deployment

A plausible-looking YAML config can still fail due to reverse proxies, stale metadata, or signature formatting. Verify using a **test IdP** and protected browser/devtools/traces, without using sensitive production accounts.

### 10.1. Step-by-Step Verification Sequence

**Step 1 — confirm SP registration initializes:**

- The Spring Boot app starts and has a `RelyingPartyRegistrationRepository` bean containing `registrationId=corp`.
- SP `entityId`/ACS match the IdP-registered values exactly. `https://portal.example.org` differs from `http://localhost:8080` and can differ due to reverse proxies.
- The SP signing key is readable by the process, uses the right format, and its certificate is trusted by the IdP.

**Step 2 — trigger login:**

```text
GET /saml2/authenticate/corp
```

- With Redirect binding, observe HTTP `302/303` to **IdP SSO Redirect Location**; query contains `SAMLRequest`, and if signed, `SigAlg` and `Signature` per binding.
- With POST binding, observe HTML auto-submit/form POST to **IdP SSO POST Location**; form contains `SAMLRequest` and optionally `RelayState`; signed requests must carry a proper XML Signature when decoded in a **test environment**.
- Whether signed or not, request `Issuer` must be SP entityID, `Destination` must be the IdP endpoint, and `AssertionConsumerServiceURL` must be the ACS.

**Step 3 — IdP validates the request:**

- IdP selects the matching SP registration by Issuer/metadata.
- IdP checks signature if required, algorithm, certificate, ACS URL, request ID/IssueInstant, and login policy.
- If the IdP reports an invalid signature, **check binding/signature placement, key, and URI encoding first**; never set `sign-request` to false as a temporary fix.

**Step 4 — verify the response:**

- Browser POSTs `SAMLResponse` to the registered SP ACS.
- Spring Security validates the IdP's signature, issuer, audience, recipient, validity window, and request correlation/`InResponseTo` when present.
- Only then does it create `Authentication` and a session, redirecting to the originally requested resource.

### 10.2. Observing Signed Requests by Binding Without Leaking Credentials

| Binding | Indicators of Signed AuthnRequest | Proper Verification Method |
| --- | --- | --- |
| Redirect | URL has `SAMLRequest`, `SigAlg`, and `Signature`; XML may lack `ds:Signature` | Use a SAML-test verifier supporting Redirect binding and the registered SP public certificate |
| POST | Base64 `SAMLRequest` form field; decoded XML contains XML Signature when signed | Use an XML/SAML validator checking references/canonicalization and the SP cert |
| Response at ACS | `SAMLResponse` form field, typically at POST ACS | SP validates using the configured **IdP verification certificate** |

**Logging note:** `SAMLRequest` can contain tenant/system identifiers and protocol metadata. `SAMLResponse` can carry assertions and highly sensitive personal data. Never log raw payloads, secret `RelayState`, cookies, or private keys in production; use redacted test traces with short retention and restricted access.

### 10.3. Inspecting Requests with Tools When Needed

- For Redirect binding, basic decoding order: URL decode → Base64 decode → raw DEFLATE inflate to read XML. **Signature verification must run over the canonical URL-encoded parameter string**, not the inflated XML.
- For POST binding, Base64-decode the form field to read XML. XML Signature verification must use a trusted SAML/XML signature library; simple DOM parsing only helps observation and establishes no trust.
- When inspecting XML, verify `Issuer`/`Destination`/`AssertionConsumerServiceURL`/`ProtocolBinding`. Never edit values inside a signed request and expect the signature to remain valid.

## 11. Common Deployment Pitfalls

| Symptom | Primary Possibility | Verified Resolution |
| --- | --- | --- |
| IdP reports "Unknown SP", "Issuer not found" | SP `Issuer/entityID` differs from IdP registration | Compare **SP entityID**; never use the SSO endpoint as Issuer |
| IdP reports "Unknown destination" | `Destination` mismatches SSO `Location` or wrong endpoint/binding | Read metadata, select exact Binding/Location |
| IdP reports "Invalid binding" | Sent POST to Redirect endpoint or vice versa | Check request method + metadata + config |
| IdP demands "signed AuthnRequest" | `WantAuthnRequestsSigned`/policy true while SP did not sign | Configure SP signing key, IdP-side public cert, sign-request |
| Redirect has `SAMLRequest` without `Signature`/`SigAlg` | Request unsigned or signing policy disabled | Check resolved registration and signing requirement |
| Missing `<ds:Signature>` in Redirect XML | Signature is in the **query string** | Verify with a Redirect binding verifier |
| POST XML has `ds:Signature` yet IdP rejects | Wrong XML signature/reference/canonicalization/key | Verify right key/alg/profile; use OpenSAML |
| Unsupported SigAlg | Mismatch with IdP's algorithm list | Pick RSA-SHA256 or a contract-approved algorithm |
| IdP certificate used in SP signing credentials | Swapped key direction | SP signs with SP private key; IdP cert is only for SP response verification |
| SP private key unreadable or cert/key mismatch | Secret mount/format/permission error | Check path, PKCS#8/cert format, and file permissions |
| `AssertionConsumerServiceURL` uses HTTP/localhost | Reverse proxy not forwarding trusted headers | Configure public baseUrl, trusted proxy headers, ACS metadata |
| IdP reports ACS URL mismatch | SP ACS differs from registered URL: scheme, host, port, path, slash | Compare exact request URL and IdP metadata |
| IdP login succeeds yet callback 404s | Wrong ACS path or filter does not match request | Confirm `/login/saml2/sso/{registrationId}` and SecurityFilterChain |
| Callback POST cannot find `AuthnRequest` | Lost session/state, SameSite cookie, load balancer | Check session repository, POST binding, cookies, proxy, replication |
| SP rejects `SAMLResponse` with invalid signature | SP uses wrong IdP verification certificate or tampered response | Confirm IdP metadata/key rollover; **never disable verification** |
| Multi-IdP logs into wrong organization | Wrong `registrationId` / tenant registration selected | Bind login context and issuer to the exact IdP |
| Metadata right on dev, wrong in prod | Stale metadata cache, unsynced certificate rollover | Check source and refresh timing; run rollover procedure |
| SSO enters redirect loop | Blocked cookies/session, ACS mismatch, IdP policy error | Check both request and response, session state, and redirect chain |

### 11.1. 401/403/404 Mismatches and SAML Failures

HTTP `404` at the ACS usually means wrong routing/filter URL; `401`/no principal created can indicate an authentication failure, though Spring Security can also redirect to a login page or error handler instead of returning 401 depending on config. `403` may stem from CSRF/authorization or other policies. **Never guess the cause from HTTP status alone**: inspect filter chain, reason codes, redacted logs, and related traces.

### 11.2. SameSite Impact on SAML POST

In a flow with a Redirect request followed by a **cross-site POST response from the IdP to the ACS**, an SP cookie set to `SameSite=Lax` or `Strict` may **not be sent by the browser** on POST. The default `HttpSessionSaml2AuthenticationRequestRepository` may then fail to find the stored request/state to correlate `InResponseTo`.

What to do:

- Check `SameSite`/`Secure` cookie attributes in a real browser and confirm whether POST ACS sends the session cookie.
- Pick a suitable session/correlation strategy (e.g., cookies permitted on cross-site POST via `SameSite=None; Secure` in appropriate environments) while mitigating CSRF risks on other endpoints.
- If moving state caching outside the session, assess **login fixation/session confusion** risks: looking up via RelayState or InResponseTo **does not by itself prove** the current browser initiated the login. Maintain strong binding to transaction/tenant/session and anti-replay.
- Never disable CSRF across the entire application just to let POST ACS pass; Spring Security provides dedicated handling for SAML callbacks.

## 12. Security and Operational Boundaries

### 12.1. HTTPS Is Necessary but Does Not Replace Signatures

- TLS protects the transport channel from browser to IdP/SP against eavesdropping or tampering in transit.
- Signed AuthnRequest lets the IdP verify **the request genuinely came from the registered SP**, per IdP policy.
- Signed Response/Assertion lets the SP verify **login proof issued by the trusted IdP**. Signing in one direction does not substitute for the other.
- RelayState must be bound to the login transaction with controlled redirects; it is neither a signature on the assertion nor permission to redirect to arbitrary hosts.
- `InResponseTo` alongside request state and issuer/audience/recipient/time validation helps defend against login injection and replay. Evaluate ID-based anti-replay across multi-node SPs.

### 12.2. Reverse Proxies and Public URLs

If Spring Boot runs at `http://10.0.0.5:8080` behind a public HTTPS ingress, the IdP must see `https://portal.example.org` in SP ACS/Issuer where applicable. Common mismatch:

```text
External request: https://portal.example.org/saml2/authenticate/corp
Internal app:     http://10.0.0.5:8080/saml2/authenticate/corp

Incorrect generated ACS:
  http://10.0.0.5:8080/login/saml2/sso/corp

Expected public ACS:
  https://portal.example.org/login/saml2/sso/corp
```

Configure Spring Boot forwarded-header handling and proxies to trust `Forwarded`/`X-Forwarded-*` headers only from **trusted ingress**, never headers sent by external Internet clients. If request host/scheme can be controlled by clients, the SP can generate wrong ACS/URLs or suffer redirect/callback confusion.

Set `entityId`/ACS to match public deployment and verify live SP metadata after deploying. Never "fix" it by asking the IdP to skip `Recipient`/`Destination` validation.

### 12.3. Key and Certificate Management

- Protect the SP signing private key with file permissions, secret stores, container mounts, access control, and auditing; never log or commit it.
- Maintain a certificate/key rotation schedule; the IdP should support an agreed overlap period to avoid downtime.
- Distinguish the **SP certificate for request signing** from the **IdP certificate for response verification**; name files/secrets clearly by role.
- Monitor alerts when the IdP signing key changes or metadata updates unexpectedly; accept metadata only from trusted sources.
- Use supported, sufficiently strong signing algorithms; never accept "verify with any key inside XML `KeyInfo`" instead of certificate/issuer pinning.

## 13. Java 17+ Practice: Modeling Endpoint/Binding/Signing Policy Checks

To understand **configuration rules** before real SAML integration, the plain Java program below simulates checking HTTPS URI, IdP signature requirement, SP signing toggle, and SP signing key presence. It **does not create, sign, or validate SAML XML**. Phrases `query Signature` and `XML Signature` merely describe signature placement per binding.

Create `SamlRequestPolicyDemo.java`:

```java
public class SamlRequestPolicyDemo {

    enum Binding { REDIRECT, POST }

    record Settings(
            String idpSsoUrl,
            Binding requestBinding,
            boolean idpRequiresSignature,
            boolean spSigns,
            boolean hasSpSigningKey) {}

    static String inspect(Settings settings) {
        if (!settings.idpSsoUrl().startsWith("https://")) {
            return "reject: insecure SSO URL";
        }
        if (settings.idpRequiresSignature() && !settings.spSigns()) {
            return "reject: IdP requires signed request";
        }
        if (settings.spSigns() && !settings.hasSpSigningKey()) {
            return "reject: SP signing key missing";
        }
        if (!settings.spSigns()) {
            return "accept: unsigned request by policy";
        }
        return settings.requestBinding() == Binding.REDIRECT
                ? "accept: signed Redirect (query Signature)"
                : "accept: signed POST (XML Signature)";
    }

    public static void main(String[] args) {
        Settings redirect = new Settings(
                "https://login.example.org/sso/redirect",
                Binding.REDIRECT, true, true, true);
        Settings post = new Settings(
                "https://login.example.org/sso/post",
                Binding.POST, true, true, true);
        Settings unsigned = new Settings(
                "https://login.example.org/sso/redirect",
                Binding.REDIRECT, true, false, false);
        Settings noKey = new Settings(
                "https://login.example.org/sso/redirect",
                Binding.REDIRECT, true, true, false);

        System.out.println("Redirect: " + inspect(redirect));
        System.out.println("POST: " + inspect(post));
        System.out.println("Unsigned: " + inspect(unsigned));
        System.out.println("No key: " + inspect(noKey));
    }
}
```

Run on JDK 17 or later:

```bash
javac SamlRequestPolicyDemo.java
java SamlRequestPolicyDemo
```

Exact stdout output:

```text
Redirect: accept: signed Redirect (query Signature)
POST: accept: signed POST (XML Signature)
Unsigned: reject: IdP requires signed request
No key: reject: SP signing key missing
```

**Understanding the demo's limits:**

- The code checks only minimal **signing policy logic**, without checking whether URIs exist in real metadata, certificates, algorithms, `Issuer`/`Destination`, request replay, or XML signatures.
- Both `Redirect` and `POST` are validly signed in the **simulated model**, yet their signature locations differ.
- `Unsigned` fails because IdP policy requires signing; `No key` fails because the SP private key is missing.
- If the IdP does **not** require signing and the SP intentionally does not sign, the program can return `accept: unsigned request by policy`; that speaks only to the simulated policy and **does not claim every SSO system should accept unsigned requests**.
- In real integration, let Spring Security/OpenSAML construct requests and signatures; never turn `inspect()` into a validation filter or substitute it for the framework.

## 14. Negative Integration Testing and Acceptance Criteria

Set up a **test** IdP and at least two configuration profiles to prove the system responds properly to bindings and signatures.

| Case | Expectation |
| --- | --- |
| Registration `corp` with Redirect and signing enabled, valid key | Spring builds signed Redirect AuthnRequest; IdP receives and verifies it |
| Replace IdP SSO URL with a URL not in metadata | Blocked by IdP/system policy; never silently trusts new endpoint |
| Configured Redirect binding yet sending POST to Redirect endpoint | IdP rejects or unsupported; fix endpoint/binding config |
| Remove SP signing private key when IdP mandates signing | Startup/request signing fails; never produces a fake signed request |
| SP signs with a key/certificate not trusted by IdP | IdP rejects signature |
| Modify one byte in signed Redirect query | IdP rejects signature, even if XML parses cleanly |
| Change `SigAlg` while keeping old signature | IdP rejects signature |
| Enable HTTP-POST signed request | IdP verifies XML Signature, does not require query `SigAlg`/`Signature` |
| Inspecting Redirect XML and seeing no `ds:Signature` | Do not conclude unsigned; inspect query string per binding |
| Wrong SP `Issuer/entityID` | IdP rejects unknown SP or registration mismatch |
| Wrong ACS URL or HTTP behind reverse proxy | IdP rejects ACS/Recipient, or SP rejects response; fix public URL |
| Request `ProtocolBinding`=POST, request binding=REDIRECT | Valid if both IdP/SP support it: Redirect request, POST response |
| Trying to use IdP verification cert as SP signing credential | Lacks matching private key; signing fails or IdP rejects |
| Switching `registrationId` to another IdP/tenant | SP picks the right config; rejects SAMLResponse with wrong issuer/tenant |
| Invalid Response/Assertion signature | SP rejects login, even if AuthnRequest was signed |
| POST ACS missing session correlation | SP rejects or runs safely designed fallback flow; never skips validation |
| SP signing key rotated on schedule | IdP knows new cert before SP switches; signed requests accepted during rollout |
| SP metadata publishes ACS/binding and signing cert | Matches IdP-registered config and live requests |

### 14.1. How to Write a Useful Integration Test

A test should explicitly state:

- **Given:** IdP metadata/trust source, SP entityID, ACS, request/response bindings, signed/unsigned policy, test signing key and certificate.
- **When:** invoking `/saml2/authenticate/corp` or submitting callbacks with/without valid responses in the test environment.
- **Then:** Redirect uses `SAMLRequest`/`SigAlg`/`Signature` per binding; POST uses form POST/XML Signature per policy; IdP/SP accept only matching keys, issuers, URLs, and state; any mismatched field is rejected.

Never write real assertions, cookies, or private keys into CI logs. Store only synthetic test fixtures, and redact payloads after debugging.

### 14.2. Pre-Production Review Checklist

- [ ] SSO `Location` comes from **trusted** IdP metadata; request binding matches a supported `SingleSignOnService.Binding`.
- [ ] SP `entityID`, ACS Location/Binding, and registration ID are aligned with the IdP.
- [ ] IdP `WantAuthnRequestsSigned` and SP `AuthnRequestsSigned` are understood on the **right sides**; signing contract is explicit.
- [ ] When signing is required, SP has private signing key + matching certificate; IdP trusts SP's public certificate; algorithms are mutually approved.
- [ ] When Redirect is signed, requests carry compliant `SigAlg`/`Signature` query parameters; when POST is signed, XML Signature is generated/verified properly.
- [ ] AuthnRequest `ProtocolBinding` describes the **response binding**, not confused with request binding.
- [ ] SP validates responses/Assertions with the IdP verification certificate and full issuer/audience/recipient/time/request correlation checks.
- [ ] Public HTTPS URLs work accurately through reverse proxies; trusted forwarded headers and SameSite cookies are verified in browsers.
- [ ] No exposure of SAMLResponses, cookies, sensitive RelayState, or SP private keys in logs/telemetry/repositories.
- [ ] Key rotation, metadata updates, failure alerts, and negative tests are implemented.
- [ ] Changes to bindings, ACS, and signing policies are tested end-to-end against a test IdP before production.

## 15. Review Questions

**Q1.** How do the IdP's `SingleSignOnService` and the SP's `AssertionConsumerService` differ?  
**Answer:** The **IdP's** SSO service **receives AuthnRequests**; the **SP's** ACS **receives SAMLResponses**. They have separate owners, URLs, and bindings.

**Q2.** Can Redirect be used to send AuthnRequest even if `ProtocolBinding` in the request is HTTP-POST?  
**Answer:** Yes. `ProtocolBinding` specifies **the binding at which the SP wants to receive the response**; the request binding is chosen via IdP `SingleSignOnService` and SP config.

**Q3.** Why might a Redirect-signed AuthnRequest lack `<ds:Signature>` in the XML?  
**Answer:** Under SAML HTTP-Redirect binding, the signature is placed into `SigAlg` and `Signature` query parameters. It must be verified per binding rules.

**Q4.** IdP metadata says `WantAuthnRequestsSigned=true`, and the SP lacks a private signing key: what is wrong?  
**Answer:** The SP cannot generate the required signature; configure the SP key/cert and register the matching public cert at the IdP rather than disabling policy to suppress errors.

**Q5.** Is it valid to use the IdP signing certificate in the SP's `signing.credentials` section?  
**Answer:** No. `signing.credentials` requires the **SP's private key** and matching public certificate. The IdP signing certificate belongs in `assertingparty.verification.credentials` to verify responses/assertions.

**Q6.** Does enabling signed AuthnRequests exempt the SP from validating SAMLResponse?  
**Answer:** No. Request signing covers SP→IdP; response/assertion verification covers IdP→SP. The SP still needs signature/issuer/audience/recipient/time/request correlation and proper anti-replay checks.

**Q7.** The IdP reports "ACS URL mismatch" and the SP emits `http://localhost:8080/login/saml2/sso/corp` in production. Where do you fix it?  
**Answer:** Fix the public base URL/ACS and trusted forwarded headers on the reverse proxy/Spring Boot, then align SP metadata and IdP config. Never disable Recipient/Destination checks.

**Q8.** When is setting `sign-request=false` appropriate?  
**Answer:** Only when the IdP supports/permits unsigned requests and your system's security policy decides so; verify live outbound requests and consistent RP/IdP configuration.

## Standard References

- [OASIS SAML 2.0 Core](https://docs.oasis-open.org/security/saml/v2.0/saml-core-2.0-os.pdf) – `AuthnRequest`, `Issuer`, `Destination`, `AssertionConsumerServiceURL`, `ProtocolBinding`, and semantics.
- [OASIS SAML 2.0 Bindings](https://docs.oasis-open.org/security/saml/v2.0/saml-bindings-2.0-os.pdf) – HTTP-Redirect/POST transport, encoding, signature placement, and `RelayState`.
- [OASIS SAML 2.0 Metadata](https://docs.oasis-open.org/security/saml/v2.0/saml-metadata-2.0-os.pdf) – `IDPSSODescriptor`, `SPSSODescriptor`, `SingleSignOnService`, `AssertionConsumerService`, `WantAuthnRequestsSigned`.
- [OASIS SAML 2.0 Technical Overview](https://docs.oasis-open.org/security/saml/Post2.0/sstc-saml-tech-overview-2.0.html) – SP-initiated Redirect/POST flow and trust concepts.
- [Spring Security: Producing AuthnRequests](https://docs.spring.io/spring-security/reference/servlet/saml2/login/authentication-requests.html) – request endpoints, repository/state, POST/Redirect bindings, and signing policy.
- [Spring Security: SAML 2.0 Login Overview](https://docs.spring.io/spring-security/reference/servlet/saml2/login/overview.html) – `saml2Login()`, `RelyingPartyRegistration`, credentials, ACS, and metadata.
- [Spring Boot: SAML 2.0 Relying Party](https://docs.spring.io/spring-boot/3.4/reference/web/spring-security.html) – `spring.security.saml2.relyingparty.registration` configuration.
- [OWASP SAML Security Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/SAML_Security_Cheat_Sheet) – requirements for signature, issuer, audience, destination, and replay validation.
- [Microsoft Entra ID: SAML protocol](https://learn.microsoft.com/azure/active-directory/develop/single-sign-on-saml-protocol) – real-world example of Redirect AuthnRequest and POST Response.

**Remember:** the SSO endpoint is **where the IdP receives AuthnRequest**, the ACS is **where the SP receives SAMLResponse**, the request binding determines how `AuthnRequest` is transported and signed, and signing requirements must be fulfilled using the **SP's private key** alongside the public certificate trusted by the IdP. Choosing the right endpoint, binding, Issuer, ACS, and keys enables a secure SSO flow while preserving all response checks on the Spring Security side.