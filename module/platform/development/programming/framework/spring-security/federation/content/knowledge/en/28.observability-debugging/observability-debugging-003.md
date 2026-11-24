# Reading SAMLRequest, SAMLResponse, and Metadata in a Test Environment

> **Module:** Spring Security – federation. **Parent topic:** Observability and debugging. This Knowledge article guides inspecting a **SAML 2.0 Web Browser SSO** flow in a test environment by capturing the right HTTP binding, decoding `SAMLRequest` / `SAMLResponse`, reading XML/metadata, comparing identifiers and security conditions, and cross-checking against Spring Security Service Provider (SP) and Identity Provider (IdP) configuration. **Being able to decode XML does not mean the signature is valid, the certificate is trusted, the Assertion is still valid, or the user is allowed to log in.** All operations must use synthetic data or test accounts, avoiding online decoding tools not approved by the organization.

## 1. Learning Objectives

After this lesson, you will be able to:

1. Distinguish **SP/Relying Party** from **IdP/Asserting Party**, `AuthnRequest`, `Response`, `Assertion`, `Issuer`, `NameID`, `RelayState`, metadata, and ACS.
2. Use Developer Tools or HTTP traces in a lab to locate the exact `SAMLRequest`, `SAMLResponse`, `RelayState`, `SigAlg`, `Signature`, `SAMLart`, URL, method, and content type.
3. Decode the **HTTP-Redirect binding** in the exact required order: take the raw query parameter → URL-decode once → Base64-decode → decompress **raw DEFLATE** (RFC 1951, not gzip/zlib wrapper).
4. Decode the **HTTP-POST binding**: browser submits an `application/x-www-form-urlencoded` form, parameter value is form-decoded → Base64-decoded into XML; **do not auto-DEFLATE** like Redirect.
5. Understand that the **HTTP-Artifact binding** carries a `SAMLart` reference rather than the full XML on the front channel; SOAP ArtifactResolve/ArtifactResponse must be investigated on a trusted back channel.
6. Read `AuthnRequest`: `ID`, `IssueInstant`, `Destination`, `Issuer`, `AssertionConsumerServiceURL`/Index, `ProtocolBinding`, `NameIDPolicy`, `RequestedAuthnContext`, `ForceAuthn`/`IsPassive`.
7. Read `Response`/`Assertion`: `InResponseTo`, `Destination`, `StatusCode`, `Issuer`, `AudienceRestriction`, `SubjectConfirmationData Recipient/InResponseTo/NotOnOrAfter`, `Conditions NotBefore/NotOnOrAfter`, `AuthnStatement`, `AuthnContextClassRef`, attributes, and `NameID`.
8. Read **IdP/SP metadata**: `entityID`, `IDPSSODescriptor`/`SPSSODescriptor`, `KeyDescriptor`, `SingleSignOnService`, `AssertionConsumerService`, `SingleLogoutService`, `validUntil`/`cacheDuration`, and binding URLs.
9. Distinguish an **XML signature** (`ds:Signature`, canonicalization/reference/digest/signature) from an **HTTP-Redirect query signature** (`SigAlg`/`Signature` over URL-encoded parameters in the exact order).
10. Never confuse **signature presence** with **valid signature and trusted signer**; know when `EncryptedAssertion` cannot be read because the SP private key is required.
11. Use a **standalone Java 17** program that accepts local files only, enforces size limits, blocks DOCTYPE/external entities, reads selected diagnostic fields, and prints deterministic stdout.
12. See how to enable `saml2Login`, `saml2Metadata`, identify Spring Security endpoints, provision a test IdP certificate, and reconcile `RelyingPartyRegistration`.
13. Build a matching matrix for **Request ↔ Response ↔ IdP metadata ↔ SP metadata ↔ Spring configuration** and trace errors in signature, issuer, audience, destination, recipient, session correlation, time skew, NameID, and metadata rollover.
14. Organize safe tooling/traces: do not log raw SAML XML containing PII, do not upload HARs/tokens to random websites, and do not disable signature validation to "debug".
15. Establish negative tests, a QA checklist, and a runbook to catch misconfigurations before deploying to production.

**Scope:** SAML 2.0 HTTP-Redirect/POST/Artifact bindings, Spring Security Service Provider Servlet stack, Java 17+, XML/X.509 trust. The `.example.test` domain, XML objects, and certificates in this article are illustrative synthetic data. Only `SamlLabInspector.java` is a standalone pure-Java program; Spring snippets require a Spring Boot/Security project and a test IdP. Any data collected from a real organization must comply with security/retention policies.

## 2. Overview of a SAML2 SP-Initiated Login Flow

~~~text
Browser                  SP Spring Security                IdP
   |                            |                            |
   | GET /private               |                            |
   |--------------------------->|                            |
   | 302 /saml2/authenticate/lab|                            |
   |<---------------------------|                            |
   | GET /saml2/authenticate/lab|                            |
   |--------------------------->|                            |
   |   SAML AuthnRequest created + request state             |
   |<---- 302 IdP SSO endpoint, SAMLRequest, RelayState ----|
   |                            |                            |
   | GET IdP /sso?SAMLRequest=...&RelayState=...             |
   |-------------------------------------------------------->|
   |                            |  IdP validates AuthnRequest|
   |                            |  IdP authenticates user    |
   |<----------- HTML form (SAMLResponse, RelayState) -------|
   |                            |                            |
   | POST /login/saml2/sso/lab  |                            |
   |--------------------------->|                            |
   |                            | decode + verify signature  |
   |                            | issuer, audience, recipient|
   |                            | response/request correlation|
   |                            | Conditions, Subject, status|
   |                            | map local identity/roles   |
   |<------------ local SP session / redirected success ------|
~~~

**Traces to collect:**
- SP → IdP requests are usually **HTTP-Redirect `SAMLRequest`**, though they can also be **HTTP-POST `SAMLRequest`** depending on binding configuration.
- IdP → SP ACS responses are usually **HTTP-POST `SAMLResponse`** Base64-encoded inside a form.
- Some profiles use **HTTP-Artifact**: the front channel carries only `SAMLart`, and the response/assertion is resolved via back-channel SOAP.
- `RelayState` helps correlate request/response/saved state in some implementations; it is not proof of user identity or a signature itself.
- **Only after actual validation** does Spring Security issue `Saml2Authentication` and save `SecurityContext`/local session.

### 2.1. Default URLs in Spring Security

In common `saml2Login`/`saml2Metadata` configurations (paths may be customized):

| Role | Sample Path | Purpose |
| --- | --- | --- |
| Start login | `GET /saml2/authenticate/{registrationId}` | Create/send AuthnRequest to the corresponding IdP. |
| Alternate initiation form | `GET /saml2/authenticate?registrationId=lab` | Route by registration depending on version/configuration support. |
| ACS receiving Response | `POST /login/saml2/sso/{registrationId}` | Receive `SAMLResponse` and invoke the Spring/OpenSAML validator. |
| ACS without registrationId in path | `POST /login/saml2/sso` | May resolve RP from stored authentication request/issuer per configuration. |
| SP metadata | `GET /saml2/metadata` | Metadata published for configured RP registrations. |
| Specific SP metadata | `GET /saml2/metadata/{registrationId}` | Information for one RP. |
| SP metadata alias | `GET /saml2/service-provider-metadata/{registrationId}` | Path supported by Spring. |

**Important:** `registrationId=lab` is an **internal configuration key**, not the SP or IdP `entityID`, and not an IdP trust anchor that can be inferred from the URL alone. Do not assume all Spring Security 6.x/7.x versions share identical implementation classes/providers (OpenSAML 4/5 differ by version). Verify your application's actual dependency versions. Spring Security documentation describes the corresponding endpoints and filters.

## 3. Capturing Packets in Browser DevTools Without Leaking Data

### 3.1. Preparing an Isolated Test Session

1. Use a **sandbox** IdP and staging SP with synthetic accounts, never production accounts.
2. Clear IdP/SP sessions in a test browser profile or use a fresh profile to start from a deterministic state.
3. Open Developer Tools → **Network**, enable **Preserve log** to retain requests as the browser redirects across multiple origins.
4. Run only a single `SP-initiated` flow; record timestamp, SP hostname, `registrationId`, and user/test case ID.
5. Filter requests by `saml2/authenticate`, IdP SSO URL, and `login/saml2/sso`.
6. Inspect **HTTP Method**, `Location`, query parameters, form data, response status, and cookie scope; **do not copy full cookies/tokens**.
7. If you need to save a payload for lab decoding, store it in a local file with restricted ACLs, use a synthetic test user, and delete it when finished.
8. When filing bug reports, **redact `NameID`, email, attributes, XML signature values, RelayState, session cookies, and SAMLResponse**; send only diagnostic fields needed or use secure attachments per policy.

**Never paste HAR/SAMLResponse into random online decoder websites.** A signed SAML Assertion can contain personal identifiers, groups/roles, session data, and sensitive attributes. A screenshot of the Network panel can also expose `Authorization`, cookies, `RelayState`, and full URLs.

### 3.2. Recognizing Which Requests to Inspect

| Indicator | Binding/Meaning | How to Process |
| --- | --- | --- |
| 302 Location to IdP with `SAMLRequest=...` | HTTP-Redirect AuthnRequest. | URL-decode → Base64 → raw DEFLATE. |
| HTML form sent to IdP with hidden `SAMLRequest` | HTTP-POST AuthnRequest. | Form-decode → Base64 → XML. |
| HTML form sent to SP ACS with `SAMLResponse` | HTTP-POST Response. | Form-decode → Base64 → XML. |
| Location/form with `SAMLart` | Artifact binding. | Cannot obtain full Assertion from artifact alone; needs ArtifactResolve/Response on back channel. |
| `SigAlg` + `Signature` in raw query | HTTP-Redirect query signature. | Verify over the properly URL-encoded string; decoding XML is insufficient. |
| `ds:Signature` in XML | XML Digital Signature. | Trust/crypto validation via SAML library, not merely seeing the tag. |
| `RelayState` | Application/request correlation. | Do not use directly as an account ID or arbitrary redirect URL. |

### 3.3. Should You Use HAR?

HAR is very helpful for redirect loops, but can contain **cookies, query strings, authorization codes, POST bodies, and personal data**. Only export when organizational policy permits and use controlled storage. Redact data before sharing, delete temporary copies after analysis, set TTLs, and restrict access. Never enable verbose logging of `SAMLResponse` in production in exchange for a trace.

## 4. HTTP-Redirect: Decoding SAMLRequest Accurately

An HTTP-Redirect binding looks like:

~~~text
GET https://idp.example.test/sso?
  SAMLRequest=<url-encoded-base64-raw-deflate>
  &RelayState=<url-encoded-opaque-state>
  &SigAlg=<url-encoded-algorithm-uri>
  &Signature=<url-encoded-base64-signature>
~~~

This is schematic; the actual URL is on one line and may not carry every parameter.

### 4.1. Mandatory Decoding Order

1. Extract the **unmodified `SAMLRequest` value** from the raw query. If you need to verify the query signature, keep the original **encoded substrings** intact.
2. **URL-decode exactly once** on the parameter value, including `%2B`/`%2F`/`%3D` and `+` according to the appropriate form/query encoding rules.
3. Use a Base64 decoder to obtain the compressed bytes.
4. **Raw DEFLATE** per RFC 1951, i.e., Java `new Inflater(true)`; do not use `GZIPInputStream`.
5. Parse XML safely with a namespace-aware parser; enforce size limits and disable DTD/external entities.
6. Inspect the `AuthnRequest` root, `ID`, `IssueInstant`, `Destination`, `Issuer`, ACS URL, and NameID/AuthnContext policy.
7. Record diagnostic details; do not write raw XML/NameID to external logging tools.

~~~text
raw URL query
    |
    +--> preserve original URL-encoded SAMLRequest, RelayState, SigAlg
    |    for signature checking (if present)
    |
    +--> percent decode exactly once
    |
    +--> Base64 decode
    |
    +--> raw DEFLATE (nowrap=true)
    |
    +--> XML parser with external entities disabled
    |
    +--> diagnostic summary (NOT authentication verdict)
~~~

**Common mistake:** using default `Inflater(false)` with a zlib wrapper, causing decompression to fail; or copying a string from DevTools that was already URL-decoded and decoding it a second time. If you get `Illegal base64 character` or `incorrect header check`, check binding and encoding state first rather than rushing to alter IdP secrets/certificates.

### 4.2. Redirect Signatures Differ from XML Signatures

For HTTP-Redirect binding, per OASIS Bindings, the query signature (when present) signs **the exact** ordered string:

~~~text
SAMLRequest=<original-url-encoded-value>&RelayState=<original-url-encoded-value>&SigAlg=<original-url-encoded-value>
~~~

If `RelayState` is absent, omit **the entire** `RelayState=...&`. For a Redirect `SAMLResponse`, replace the first key with `SAMLResponse`. The `Signature` parameter carries the URL-encoded Base64 signature and is **not part of the signed content**.

- Signature verification must run over the **octets of the properly formatted encoded string** using a **configured trusted public key** for the partner; do not include arbitrary other parameters in the signed string.
- Decoding XML, re-serializing it, and verifying an XML signature **is not HTTP-Redirect signature verification**.
- Seeing `Signature`/`SigAlg` proves the sender supplied values, **not that the signature is valid or the signer is trusted**.
- Do not accept `SigAlg` from the request without algorithm allowlisting/trust policy approval. The SAML library must protect against weak algorithms, invalid signatures, and `RelayState` tampering.
- Only load inflated XML into a safe viewer; "not seeing `ds:Signature`" on a Redirect AuthnRequest **does not automatically prove the request is unsigned**, because the signature may be in the query `Signature`.

**Never hand-roll XMLSig/RedirectSig verifiers for production.** Use Spring Security/OpenSAML and certificate trust configured for the right partner.

### 4.3. Fields to Read from AuthnRequest

**Synthetic, unsigned XML** example to illustrate structure:

~~~xml
<samlp:AuthnRequest
    xmlns:samlp="urn:oasis:names:tc:SAML:2.0:protocol"
    xmlns:saml="urn:oasis:names:tc:SAML:2.0:assertion"
    ID="_req-lab-17"
    Version="2.0"
    IssueInstant="2026-11-07T02:30:00Z"
    Destination="https://idp.example.test/sso"
    AssertionConsumerServiceURL="https://sp.example.test/login/saml2/sso/lab"
    ProtocolBinding="urn:oasis:names:tc:SAML:2.0:bindings:HTTP-POST">
  <saml:Issuer>https://sp.example.test/saml2/service-provider-metadata/lab</saml:Issuer>
  <samlp:NameIDPolicy
      Format="urn:oasis:names:tc:SAML:2.0:nameid-format:persistent"
      AllowCreate="true"/>
  <samlp:RequestedAuthnContext Comparison="minimum">
    <saml:AuthnContextClassRef>urn:example:authn:workforce-mfa</saml:AuthnContextClassRef>
  </samlp:RequestedAuthnContext>
</samlp:AuthnRequest>
~~~

`urn:example:authn:workforce-mfa` is an organization-defined **example profile**, not automatically an AuthnContextClassRef recognized by every IdP. Exact agreement between SP and IdP is required.

| Field | Compare Against |
| --- | --- |
| `ID` | `Response.InResponseTo` or `SubjectConfirmationData.InResponseTo` per profile and request repository. |
| `IssueInstant` | UTC clock, allowed skew, SP/IdP request lifetime. |
| `Destination` | IdP SingleSignOnService URL matching metadata/binding. |
| `Issuer` | **SP entityID**, not an arbitrary hostname or registrationId. |
| `AssertionConsumerServiceURL` | SP's **public HTTPS ACS**; does the IdP allowlist/match metadata? |
| `AssertionConsumerServiceIndex` | If using an index from metadata, IdP looks up that index instead of a literal URL. |
| `ProtocolBinding` | Binding the SP wants the IdP to use for returning Response, usually HTTP-POST. |
| `NameIDPolicy.Format` | Agreed persistent/transient/email format; do not force an IdP to issue an unsupported type. |
| `RequestedAuthnContext` | Requested assurance/context policy; do not assume merely requesting means the IdP satisfied it. |
| `ForceAuthn` / `IsPassive` | Whether reauthentication or non-interactive UI is requested; appears only when configured. |

### 4.4. A Redirect Loop Does Not Equal a Base64 Error

If the browser keeps bouncing back to the IdP, compare:
- Is the SP generating a new `AuthnRequest` each time or retrying the same ID?
- Is the IdP rejecting `Destination`/`ACS`/`Issuer`/`NameIDPolicy`/signature?
- Does the SP cookie holding `AbstractSaml2AuthenticationRequest` in session disappear after redirect?
- Does the user have an IdP session that fails AuthnContext/ForceAuthn requirements?
- Is the Spring ACS POST hitting the wrong `SecurityFilterChain` or blocked by custom CSRF rules?
- Are domain/HTTPS/proxy settings making `{baseUrl}` wrong so the IdP POSTs to a different host?

**An absent SAMLResponse** differs from **a present SAMLResponse whose validation fails**. Pinpoint the exact break before changing trust settings.

## 5. HTTP-POST: Reading SAMLResponse Sent to ACS

The SAML HTTP-POST binding submits a form, typically containing:

~~~html
<form method="post" action="https://sp.example.test/login/saml2/sso/lab">
  <input type="hidden" name="SAMLResponse" value="BASE64_OF_XML"/>
  <input type="hidden" name="RelayState" value="OPAQUE_STATE"/>
</form>
~~~

The browser sends `application/x-www-form-urlencoded`. In the Network panel, the tool may display the form-decoded value. When `SAMLResponse` is in the form:
1. Take the **Base64 value after one form-decode**; do not URL-decode it again.
2. Base64-decode into UTF-8 XML bytes; **normally not DEFLATE-compressed**.
3. Parse XML safely without processing DTD/external entities.
4. Inspect root `samlp:Response`, `Issuer`, `Destination`, `InResponseTo`, `StatusCode`, `Assertion`/`EncryptedAssertion`.
5. Note whether an XML signature exists on `Response` or `Assertion`, **but do not infer crypto/trust validation from its presence**.
6. Cross-check against metadata and `RelyingPartyRegistration` for the right IdP/ACS.
7. Use the real Spring/OpenSAML provider to evaluate signature, Conditions, SubjectConfirmation, and identity mapping.

**Watch out for `+` in Base64:** in a raw form body, `+` means space under form encoding; Base64 containing plus signs gets form-encoded as `%2B`. If you copy an already-decoded string and call `URLDecoder` again, `+` can turn into spaces and corrupt the payload. The Java tool below accepts **already form-decoded Base64**, and does not URL-decode it a second time.

### 5.1. Redacted Response Example

~~~xml
<samlp:Response
    xmlns:samlp="urn:oasis:names:tc:SAML:2.0:protocol"
    xmlns:saml="urn:oasis:names:tc:SAML:2.0:assertion"
    ID="_response-lab-17"
    Version="2.0"
    IssueInstant="2026-11-07T02:30:12Z"
    Destination="https://sp.example.test/login/saml2/sso/lab"
    InResponseTo="_req-lab-17">
  <saml:Issuer>https://idp.example.test/entity</saml:Issuer>
  <samlp:Status>
    <samlp:StatusCode Value="urn:oasis:names:tc:SAML:2.0:status:Success"/>
  </samlp:Status>
  <!-- Signed Assertion omitted in this schematic example. -->
</samlp:Response>
~~~

**This is an XML skeleton for reading fields, NOT a valid SAML Response that can log in.** It intentionally omits the signed Assertion/Subject/Conditions/trust certificate. Real ACS tests must use a signed fixture and validator; never mock a provider to "always succeed" and declare signature QA PASS.

### 5.2. Response Inspection Order

| Level | Field | Meaning When Debugging |
| --- | --- | --- |
| Response | `ID` | Identifier for replay prevention/audit correlation depending on implementation. |
| Response | `InResponseTo` | Correlates AuthnRequest if SP-initiated; unsolicited/IdP-initiated has separate policy. |
| Response | `Destination` | Actual recipient SP ACS URL. |
| Response | `Issuer` | Trusted IdP entity ID. |
| Response | `StatusCode` | Success or protocol error; a Response can still be valid XML while login fails. |
| Response/Assertion | `ds:Signature` | Requires XML signature verification against trusted cert/Reference, not just tag presence. |
| Assertion | `Issuer` | IdP issuing the assertion; may match or differ from Response Issuer per profile, must be checked by validator. |
| Assertion | `ID`, `IssueInstant` | Assertion identity and issuance time. |
| Assertion | `Subject/NameID` | Identifier per contract; do not assume it is email or local user ID. |
| SubjectConfirmationData | `Recipient` | Valid ACS endpoint receiving the assertion. |
| SubjectConfirmationData | `InResponseTo` | Request correlation (especially for bearer subject confirmation). |
| SubjectConfirmationData | `NotOnOrAfter` | Deadline for accepting subject confirmation. |
| Conditions | `NotBefore`, `NotOnOrAfter` | Assertion validity window, possibly with policy skew. |
| AudienceRestriction | `Audience` | **SP entityID** permitted to consume the assertion, not merely a similar domain. |
| AuthnStatement | `AuthnInstant`, `SessionIndex` | IdP authentication time/session reference, useful for SLO/freshness. |
| AuthnContextClassRef | `AuthnContext` | Authentication method/assurance level asserted by IdP, must map per policy. |
| AttributeStatement | Name/NameFormat/values | Claims can be multi-valued and sensitive; never auto-grant admin. |

### 5.3. Handling Error Responses

For instance, if the IdP returns a non-Success `StatusCode`, it may indicate:
- `Requester` or `Responder`;
- `AuthnFailed`;
- `NoAuthnContext`;
- `InvalidNameIDPolicy` or an IdP implementation/profile-specific error.

Read the code/subcode and IdP audit in sandbox; it does not always mean a signature error or disabled account. Do not swap certificates when Status clearly states that the requested AuthnContext was not satisfied.

### 5.4. EncryptedAssertion

When a Response contains `saml:EncryptedAssertion`, the decoder sees only `EncryptedData/EncryptedKey` XML; **it cannot** read the subject/attributes without the configured SP decryption private key. Never ask the IdP to disable encryption just to debug in production, and never export private keys to personal machines or online decryption websites. Use a test SP key in sandbox, the OpenSAML library, and redacted audits.

## 6. HTTP-Artifact and Other Bindings

HTTP-Artifact typically appears as:

~~~text
GET https://sp.example.test/acs?SAMLart=<encoded-artifact>&RelayState=...
~~~

`SAMLart` is a **reference**, not normal Base64 XML. The IdP/SP must perform `ArtifactResolve` / `ArtifactResponse` over a back channel, usually SOAP, to retrieve the SAML protocol message. Decoding the artifact alone into bytes cannot yield the full Assertion.

Proper testing:
- identify the right ArtifactResolutionService endpoint/binding from metadata;
- check TLS/mTLS or SOAP message signing/trust per profile;
- check single-use/TTL of the artifact and service binding;
- trace the server-side resolver; **do not** send private keys or SOAP data to online analyzers;
- distinguish a browser front-channel error from a resolver back-channel DNS/TLS outage.

**Do not apply the Redirect raw-DEFLATE formula to `SAMLart`.** Likewise, SAML SOAP binding, PAOS/ECP, and logout bindings need separate pipelines; never assume every `SAMLRequest` is DEFLATE-compressed.

## 7. Reading IdP Metadata and SP Metadata

Metadata is a **contract describing published endpoints/keys/roles**; **it is not itself a trust anchor** unless the metadata file has been verified by source, signature, or administrative channel.

### 7.1. EntityDescriptor and EntitiesDescriptor

~~~xml
<md:EntityDescriptor
    xmlns:md="urn:oasis:names:tc:SAML:2.0:metadata"
    entityID="https://idp.example.test/entity"
    validUntil="2026-12-01T00:00:00Z">
  <md:IDPSSODescriptor
      protocolSupportEnumeration="urn:oasis:names:tc:SAML:2.0:protocol">
    <md:KeyDescriptor use="signing">
      <!-- KeyInfo/X509Certificate would be here. -->
    </md:KeyDescriptor>
    <md:SingleSignOnService
        Binding="urn:oasis:names:tc:SAML:2.0:bindings:HTTP-Redirect"
        Location="https://idp.example.test/sso"/>
  </md:IDPSSODescriptor>
</md:EntityDescriptor>
~~~

This is a **metadata skeleton**; an empty `KeyDescriptor` is not a valid credential to place into RP config. Real metadata needs the public key certificate belonging to an approved IdP.

An `EntitiesDescriptor` can wrap multiple `EntityDescriptor` elements; never guess the first entity or share one signing certificate across all entities. Metadata may have an XML signature at the root; seeing `ds:Signature` **does not prove** the signer is trusted. You need an external trust anchor, pinned certificate/fingerprint, or federation metadata-signing contract.

### 7.2. IdP Metadata Elements

| Element/attribute | Meaning | Check |
| --- | --- | --- |
| `EntityDescriptor.entityID` | SAML IdP identifier. | Exact match with Response/Assertion `Issuer` per profile. |
| `IDPSSODescriptor.protocolSupportEnumeration` | Supported protocols. | Includes SAML 2.0 protocol. |
| `SingleSignOnService.Binding` | Bindings accepted by IdP. | Redirect/POST matches SP. |
| `SingleSignOnService.Location` | AuthnRequest Destination. | Right host/path, TLS/allowlist. |
| `KeyDescriptor use="signing"` | Public certificate(s) verifying IdP signatures. | Trusted key, rotation policy. |
| `KeyDescriptor use="encryption"` | Public key for encryption per role/model. | Do not confuse signer verify key with SP decrypt key. |
| `SingleLogoutService` | Logout endpoint and binding. | Do not assume SLO is enabled/working automatically. |
| `NameIDFormat` | NameID formats advertised by IdP. | Compatible with RequestedNameIDPolicy. |
| `validUntil` | Metadata expiration timestamp in scope. | Cache refresh/expiry policy. |
| `cacheDuration` | Metadata cache duration hint. | Not when the certificate itself expires. |

### 7.3. SP Metadata Elements

| Element/attribute | Meaning | Check |
| --- | --- | --- |
| `EntityDescriptor.entityID` | SP entityID. | Matches `AuthnRequest.Issuer` and `Assertion.Audience`. |
| `SPSSODescriptor.AuthnRequestsSigned` | SP/IdP policy on signing requests. | Right signing key/binding signature when required. |
| `SPSSODescriptor.WantAssertionsSigned` | Policy on Assertion signatures. | Verify actual profile/signature, not just the attribute. |
| `AssertionConsumerService.Binding` | Binding receiving Response. | HTTP-POST/Artifact matches. |
| `AssertionConsumerService.Location` | Public ACS URL receiving Response. | Matches Response `Destination` and Subject `Recipient`. |
| `AssertionConsumerService.index` | ACS endpoint index. | Matches index in AuthnRequest if used. |
| `KeyDescriptor use="signing"` | SP public signing cert. | IdP verifies SP requests/logout per agreement. |
| `KeyDescriptor use="encryption"` | SP public encryption key for IdP to encrypt Assertions. | SP must have the matching private key to decrypt. |
| `SingleLogoutService` | SP SLO endpoint. | Test LogoutRequest/Response separately. |
| `validUntil`/`cacheDuration` | Metadata validity/cache if present. | Do not confuse with X.509 validity. |

**Do not infer solely from `KeyDescriptor` that the entire system automatically runs PKIX/CRL/OCSP or automatically trusts metadata keys**. Spring Security commonly uses explicit-key credentials configured on the RP registration; trust management, certificate expiry/revocation checks, metadata signature validation, refresh, and rollover require dedicated configuration/testing policies. Having a public certificate inside metadata does not prove the signer is trusted, and metadata expiration differs from X.509 certificate expiration.

### 7.4. Detecting Wrong SP Metadata Caused by a Reverse Proxy

For example, the real external URL is `https://sp.example.test`, while the Spring app runs at `http://internal-service:8080`. If forwarded headers are not managed, SP metadata may emit:

~~~text
Wrong:
  entityID: http://internal-service:8080/saml2/service-provider-metadata/lab
  ACS:      http://internal-service:8080/login/saml2/sso/lab

Expected:
  entityID: https://sp.example.test/saml2/service-provider-metadata/lab
  ACS:      https://sp.example.test/login/saml2/sso/lab
~~~

The IdP may reject the AuthnRequest, or return a Response whose `Destination`/`Recipient` fails SP expectations. The fix is a **correct trusted public base URL / forwarded header strategy** and updated metadata/registration at the IdP; **never disable Destination/Recipient validation**.

### 7.5. Fetching Metadata Safely

You can download metadata from a staging endpoint whose source is verified, for example:

~~~bash
# Sandbox only. Do not use -k / --insecure when TLS is not verified.
curl --fail --silent --show-error \
  --output sp-metadata.xml \
  https://sp.example.test/saml2/metadata/lab
~~~

Never automatically ingest content from an arbitrary URL into a production trust store. Even when metadata is fetched over HTTPS, you must verify the **source** and metadata verification policy. XML signatures, signed federation metadata, or pinned trust anchors may be contractually required. If there are multiple `EntityDescriptor`s, select the exact `entityID`/role rather than picking arbitrarily.

## 8. Spring Security: Configuring the SP for Lab Observability

### 8.1. Minimal Dependencies and Configuration

~~~groovy
// build.gradle (fragment in a Spring Boot 3.x project).
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-security'
    implementation 'org.springframework.security:spring-security-saml2-service-provider'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-test'
}

// Some OpenSAML/Shibboleth artifacts require a dedicated
// repository depending on actual dependency/version, for example:
// maven { url 'https://build.shibboleth.net/maven/releases/' }
~~~

Example `application.yml` for an **approved test IdP**:

~~~yaml
spring:
  security:
    saml2:
      relyingparty:
        registration:
          lab:
            entity-id: "{baseUrl}/saml2/service-provider-metadata/{registrationId}"
            acs:
              location: "{baseUrl}/login/saml2/sso/{registrationId}"
            assertingparty:
              entity-id: "https://idp.example.test/entity"
              singlesignon:
                url: "https://idp.example.test/sso"
                sign-request: false
              verification:
                credentials:
                  - certificate-location: "classpath:lab-idp-signing.crt"
~~~

**You must provide a real `lab-idp-signing.crt` file from a trusted test IdP**, never grab an arbitrary certificate self-declared inside a Response. `sign-request:false` here only illustrates **when a sandbox IdP allows unsigned AuthnRequests**; in systems requiring signed requests, configure SP credentials and policy properly rather than disabling signing to ease debugging. Never use this snippet as an unverified production configuration.

### 8.2. Enabling Metadata Endpoints and the SAML2 Login Filter

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
class SamlLabSecurityConfig {

    @Bean
    SecurityFilterChain chain(HttpSecurity http) throws Exception {
        return http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/health", "/error").permitAll()
                .anyRequest().authenticated()
            )
            .saml2Login(Customizer.withDefaults())
            .saml2Metadata(Customizer.withDefaults())
            .build();
    }
}
~~~

Spring Security can publish metadata at `/saml2/metadata` and `/saml2/metadata/{registrationId}` when `saml2Metadata` is enabled. That endpoint serves **public metadata**, excluding private keys, though you must still distinguish SP from IdP entity IDs and avoid sending wrong links.

### 8.3. Where Requests and Responses Flow

| Spring component | Responsibility | Debug symptom |
| --- | --- | --- |
| `Saml2WebSsoAuthenticationRequestFilter` | Handles initiate URL, creates/sends AuthnRequest. | 404/302 wrong SSO URL, missing `SAMLRequest`. |
| `Saml2AuthenticationRequestRepository` (implementation depends on version) | Stores request state to correlate response. | `InResponseTo` not found, lost HttpSession. |
| `Saml2WebSsoAuthenticationFilter` | Intercepts ACS `SAMLResponse`. | Response POST hits wrong chain, 401/403/redirect loop. |
| `Saml2AuthenticationToken` | Carries SAMLResponse and RP registration to manager. | Resolves wrong registration/certificate. |
| OpenSAML-backed authentication provider | Decodes/validates signature, issuer, audience, expiry, subject confirmation. | Crypto/trust/Conditions fail. |
| `Saml2Authentication` / `Saml2AuthenticatedPrincipal` | Authentication/principal after SAML is verified. | Principal succeeds but local role/tenant is wrong. |
| `RelyingPartyRegistrationRepository` | Holds SP/IdP metadata/credentials from trusted source. | Missing/wrong registration, stale IdP certificate. |

**Never** replace the provider with an "accept all XML" implementation just to read SAMLResponse. Offline decoding only aids analysis; authentication is decided by the real filter/provider and trust configuration.

### 8.4. Controlled Debug Logging

In an **isolated sandbox**, you can temporarily raise log levels:

~~~yaml
logging:
  level:
    org.springframework.security: DEBUG
    org.springframework.security.saml2: DEBUG
~~~

Depending on implementation, debug output may expose principals/attributes or session details. **Never leave TRACE enabled indefinitely in production**, and never log raw SAMLResponse/NameID/cookies/tokens. Enforce data filtering, retention, and log access controls. If an issue does not require raw token debugging, use correlation IDs, event reason classes, and timestamps.

### 8.5. When Multiple IdPs Exist

Two registrations:

~~~text
registrationId=lab-corp  -> IdP entityID A; verify cert A; ACS A
registrationId=lab-partner -> IdP entityID B; verify cert B; ACS B
~~~

Never use an attacker-supplied `Issuer` to dynamically load an arbitrary certificate from the Response itself. RP resolution and credential lookup must rely on **trusted registrations**, allowlists, and stored request state; handling IdP-initiated flows requires especially strict policy when there is no prior request ID.

## 9. Java 17: Safe, Bounded Decoding Tool

Tool goals:
- **Read local files only**, never fetch URLs or send payloads over the network.
- Accept `redirect-file` (containing a raw query with `SAMLRequest`), `post-file` (containing only the already form-decoded Base64 value of `SAMLResponse`), `metadata-file` (XML metadata), or `selftest`.
- Never print `NameID`, email, assertions, attributes, RelayState, cookies, private keys, or raw XML.
- Limit input file size and inflated XML size to prevent unbounded decompression bombs.
- Block DOCTYPE, external entities, XInclude, and external schema fetching in JAXP.
- Print only **root type, ID, Issuer, Destination, KeyDescriptor count, and whether a Signature element is present**.
- **Does not** verify XMLSig, RedirectSig, metadata trust, NotBefore/NotOnOrAfter, or replay; **must never** be used to authorize users.

### 9.1. `SamlLabInspector.java`

~~~java
import java.io.ByteArrayInputStream;
import java.io.ByteArrayOutputStream;
import java.io.IOException;
import java.net.URLDecoder;
import java.net.URLEncoder;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.Base64;
import java.util.zip.Deflater;
import java.util.zip.DeflaterOutputStream;
import java.util.zip.Inflater;
import java.util.zip.InflaterInputStream;

import javax.xml.XMLConstants;
import javax.xml.parsers.DocumentBuilder;
import javax.xml.parsers.DocumentBuilderFactory;

import org.w3c.dom.Document;
import org.w3c.dom.Element;
import org.w3c.dom.Node;
import org.w3c.dom.NodeList;
import org.xml.sax.SAXException;
import org.xml.sax.helpers.DefaultHandler;

public final class SamlLabInspector {
    private static final int MAX_FILE = 2_000_000;
    private static final int MAX_XML = 1_000_000;

    private static final String PROTOCOL =
        "urn:oasis:names:tc:SAML:2.0:protocol";
    private static final String ASSERTION =
        "urn:oasis:names:tc:SAML:2.0:assertion";
    private static final String METADATA =
        "urn:oasis:names:tc:SAML:2.0:metadata";
    private static final String DSIG =
        "http://www.w3.org/2000/09/xmldsig#";

    private SamlLabInspector() {}

    private static byte[] readLimited(Path path) throws IOException {
        if (Files.size(path) > MAX_FILE) {
            throw new IOException("Input file exceeds limit");
        }
        byte[] bytes = Files.readAllBytes(path);
        if (bytes.length > MAX_FILE) {
            throw new IOException("Input file exceeds limit");
        }
        return bytes;
    }

    // Expects the RAW query without a leading URL/path.
    private static String getRawQueryValue(
            String rawQuery, String wanted) {
        String q = rawQuery.strip();
        if (q.startsWith("?")) {
            q = q.substring(1);
        }
        for (String part : q.split("&", -1)) {
            int equal = part.indexOf('=');
            if (equal < 0) {
                continue;
            }
            if (part.substring(0, equal).equals(wanted)) {
                return URLDecoder.decode(
                    part.substring(equal + 1),
                    StandardCharsets.UTF_8
                );
            }
        }
        return null;
    }

    private static byte[] decodePostBase64(String base64) {
        // post-file contains the Base64 FIELD VALUE already
        // form-decoded once by the browser/devtools.
        // Do not call URLDecoder again on this value.
        String clean = base64.replaceAll("\\s+", "");
        byte[] bytes = Base64.getDecoder().decode(clean);
        if (bytes.length > MAX_XML) {
            throw new IllegalArgumentException(
                "Decoded XML exceeds limit");
        }
        return bytes;
    }

    private static byte[] inflateRaw(byte[] compressed)
            throws IOException {
        Inflater inflater = new Inflater(true);
        try (InflaterInputStream in =
                 new InflaterInputStream(
                     new ByteArrayInputStream(compressed),
                     inflater);
             ByteArrayOutputStream out =
                 new ByteArrayOutputStream()) {
            byte[] buf = new byte[4096];
            int n;
            while ((n = in.read(buf)) != -1) {
                if (out.size() + n > MAX_XML) {
                    throw new IOException("Inflated XML exceeds limit");
                }
                out.write(buf, 0, n);
            }
            return out.toByteArray();
        } finally {
            inflater.end();
        }
    }

    private static byte[] decodeRedirectQuery(String rawQuery)
            throws IOException {
        String value = getRawQueryValue(
            rawQuery, "SAMLRequest");
        if (value == null) {
            value = getRawQueryValue(rawQuery, "SAMLResponse");
        }
        if (value == null) {
            throw new IllegalArgumentException(
                "Expected SAMLRequest or SAMLResponse in raw query");
        }
        byte[] compressed = Base64.getDecoder().decode(
            value.replaceAll("\\s+", ""));
        if (compressed.length > MAX_FILE) {
            throw new IOException("Compressed input exceeds limit");
        }
        return inflateRaw(compressed);
    }

    private static Document parseXml(byte[] xml)
            throws Exception {
        if (xml.length > MAX_XML) {
            throw new IOException("XML exceeds limit");
        }
        DocumentBuilderFactory factory =
            DocumentBuilderFactory.newInstance();
        factory.setNamespaceAware(true);
        factory.setFeature(
            XMLConstants.FEATURE_SECURE_PROCESSING, true);
        factory.setFeature(
            "http://apache.org/xml/features/disallow-doctype-decl",
            true);
        factory.setFeature(
            "http://xml.org/sax/features/external-general-entities",
            false);
        factory.setFeature(
            "http://xml.org/sax/features/external-parameter-entities",
            false);
        factory.setFeature(
            "http://apache.org/xml/features/nonvalidating/load-external-dtd",
            false);
        factory.setXIncludeAware(false);
        factory.setExpandEntityReferences(false);
        factory.setAttribute(
            XMLConstants.ACCESS_EXTERNAL_DTD, "");
        factory.setAttribute(
            XMLConstants.ACCESS_EXTERNAL_SCHEMA, "");

        DocumentBuilder builder = factory.newDocumentBuilder();
        builder.setErrorHandler(new DefaultHandler());
        Document document = builder.parse(
            new ByteArrayInputStream(xml));
        return document;
    }

    private static String directIssuer(Element root) {
        NodeList nodes = root.getChildNodes();
        for (int i = 0; i < nodes.getLength(); i++) {
            Node node = nodes.item(i);
            if (node instanceof Element e
                    && ASSERTION.equals(e.getNamespaceURI())
                    && "Issuer".equals(e.getLocalName())) {
                return e.getTextContent().strip();
            }
        }
        return "-";
    }

    private static String summary(byte[] xml)
            throws Exception {
        Document document = parseXml(xml);
        Element root = document.getDocumentElement();
        String kind = root.getLocalName();
        String namespace = root.getNamespaceURI();

        if (METADATA.equals(namespace)
                && ("EntityDescriptor".equals(kind)
                  || "EntitiesDescriptor".equals(kind))) {
            int idps = root.getElementsByTagNameNS(
                METADATA, "IDPSSODescriptor").getLength();
            int sps = root.getElementsByTagNameNS(
                METADATA, "SPSSODescriptor").getLength();
            int keys = root.getElementsByTagNameNS(
                METADATA, "KeyDescriptor").getLength();
            return "kind=" + kind
                + "; entityID=" + root.getAttribute("entityID")
                + "; idpDescriptors=" + idps
                + "; spDescriptors=" + sps
                + "; keyDescriptors=" + keys;
        }

        if (!PROTOCOL.equals(namespace)) {
            throw new IllegalArgumentException(
                "Unexpected XML namespace/root");
        }

        boolean signatureElement =
            root.getElementsByTagNameNS(
                DSIG, "Signature").getLength() > 0;

        return "kind=" + kind
            + "; id=" + root.getAttribute("ID")
            + "; issuer=" + directIssuer(root)
            + "; destination=" + root.getAttribute("Destination")
            + "; xmlSignatureElement=" + signatureElement;
    }

    private static byte[] deflateRaw(byte[] xml)
            throws IOException {
        Deflater deflater = new Deflater(
            Deflater.DEFAULT_COMPRESSION, true);
        try (ByteArrayOutputStream output =
                 new ByteArrayOutputStream();
             DeflaterOutputStream stream =
                 new DeflaterOutputStream(output, deflater)) {
            stream.write(xml);
            stream.finish();
            return output.toByteArray();
        } finally {
            deflater.end();
        }
    }

    private static void selftest() throws Exception {
        String auth = """
            <samlp:AuthnRequest
              xmlns:samlp="urn:oasis:names:tc:SAML:2.0:protocol"
              xmlns:saml="urn:oasis:names:tc:SAML:2.0:assertion"
              ID="_req-test"
              Destination="https://idp.example.test/sso">
              <saml:Issuer>https://sp.example.test/metadata</saml:Issuer>
            </samlp:AuthnRequest>
            """;
        String response = """
            <samlp:Response
              xmlns:samlp="urn:oasis:names:tc:SAML:2.0:protocol"
              xmlns:saml="urn:oasis:names:tc:SAML:2.0:assertion"
              ID="_res-test"
              Destination="https://sp.example.test/acs">
              <saml:Issuer>https://idp.example.test/entity</saml:Issuer>
            </samlp:Response>
            """;
        String metadata = """
            <md:EntityDescriptor
              xmlns:md="urn:oasis:names:tc:SAML:2.0:metadata"
              entityID="https://idp.example.test/entity">
              <md:IDPSSODescriptor
                protocolSupportEnumeration="urn:oasis:names:tc:SAML:2.0:protocol">
                <md:SingleSignOnService
                  Binding="urn:oasis:names:tc:SAML:2.0:bindings:HTTP-Redirect"
                  Location="https://idp.example.test/sso"/>
              </md:IDPSSODescriptor>
            </md:EntityDescriptor>
            """;

        byte[] compressed = deflateRaw(
            auth.getBytes(StandardCharsets.UTF_8));
        String query = "SAMLRequest=" + URLEncoder.encode(
            Base64.getEncoder().encodeToString(compressed),
            StandardCharsets.UTF_8);

        System.out.println("redirect: " +
            summary(decodeRedirectQuery(query)));
        System.out.println("post: " +
            summary(decodePostBase64(
                Base64.getEncoder().encodeToString(
                    response.getBytes(StandardCharsets.UTF_8)))));
        System.out.println("metadata: " +
            summary(metadata.getBytes(StandardCharsets.UTF_8)));

        String dangerous = """
            <!DOCTYPE a [<!ENTITY x SYSTEM "file:///etc/passwd">]>
            <a>&x;</a>
            """;
        try {
            parseXml(dangerous.getBytes(StandardCharsets.UTF_8));
            throw new IllegalStateException(
                "DOCTYPE unexpectedly accepted");
        } catch (SAXException expected) {
            System.out.println("doctype=REJECTED");
        }
    }

    public static void main(String[] args)
            throws Exception {
        if (args.length == 1 && "selftest".equals(args[0])) {
            selftest();
            return;
        }
        if (args.length != 2) {
            System.err.println(
                "Usage: selftest | redirect-file file"
                + " | post-file file | metadata-file file");
            System.exit(2);
        }
        byte[] input = readLimited(Path.of(args[1]));
        byte[] xml = switch (args[0]) {
            case "redirect-file" -> decodeRedirectQuery(
                new String(input, StandardCharsets.UTF_8));
            case "post-file" -> decodePostBase64(
                new String(input, StandardCharsets.UTF_8));
            case "metadata-file" -> input;
            default -> throw new IllegalArgumentException(
                "Unknown mode");
        };
        System.out.println(summary(xml));
    }
}
~~~

### 9.2. Compiling and Running with JDK 17

~~~bash
javac --release 17 SamlLabInspector.java
java SamlLabInspector selftest
~~~

**Exact stdout of `selftest`:**

~~~text
redirect: kind=AuthnRequest; id=_req-test; issuer=https://sp.example.test/metadata; destination=https://idp.example.test/sso; xmlSignatureElement=false
post: kind=Response; id=_res-test; issuer=https://idp.example.test/entity; destination=https://sp.example.test/acs; xmlSignatureElement=false
metadata: kind=EntityDescriptor; entityID=https://idp.example.test/entity; idpDescriptors=1; spDescriptors=0; keyDescriptors=0
doctype=REJECTED
~~~

The sample `AuthnRequest` and `Response` in selftest are **intentionally unsigned**, the Response has no Assertion/Conditions, and the metadata contains no signing key. They only test the **decoder/parser**, and are not valid SAML login fixtures. If submitted to a real ACS, the provider must reject them per validation policy.

### 9.3. Using the Tool with Protected Files

~~~bash
# File query.txt contains ONLY the raw query string starting with SAMLRequest=...
java SamlLabInspector redirect-file query.txt

# File saml-response.b64 contains ONLY the Base64 FIELD VALUE
# of SAMLResponse after exactly one form-decode.
java SamlLabInspector post-file saml-response.b64

# File idp-metadata.xml is sandbox XML metadata downloaded
# from a trusted IdP metadata source.
java SamlLabInspector metadata-file idp-metadata.xml
~~~

- The program does not log raw XML, yet the input files **can still contain PII/sensitive SAML data**. Store them temporarily on a secure QA machine, avoid committing them, encrypt/apply lifecycle controls as needed, and delete when finished.
- `query.txt` must contain the **raw query without `https://...?...`**. If DevTools already decoded parameters, recognize that state so you do not URL-decode twice. With `+` and `%2B`, one wrong step corrupts Base64.
- `saml-response.b64` must contain the **Base64 of the field value**, not the raw form body string `SAMLResponse=...&RelayState=...`.
- For `SAMLart`, do not use any of the modes above expecting to obtain an Assertion.
- For `EncryptedAssertion`, the tool only reports the outer elements; it does not decrypt contents.
- `xmlSignatureElement=true` only states that the parser found a `ds:Signature` element somewhere under the root; it **does not** verify Reference/digest/algorithm/trust. For Redirect, there may be **no XML Signature while still having a query signature**; the tool does not verify `SigAlg`/`Signature`.
- An `EntityDescriptor` having a `KeyDescriptor` does not mean the metadata signer/key is verified.
- The 2 MB file / 1 MB inflated XML limits are **lab-chosen limits to reduce risk**, not SAML specification limits. Real IdPs may emit larger XML; only raise limits after a risk review.

### 9.4. Why Not Print NameID/Attributes?

SAML assertions can contain emails, names, employee IDs, groups, permissions, HR status, or identifying data. By default, a debugging tool should:
- display only root, synthetic-style IDs, trusted issuer/destination, and descriptor counts;
- indicate whether a Signature tag is present **without claiming the signature passed**;
- never print full `AttributeStatement`, `NameID`, XML signature values, or `KeyInfo/X509Certificate`;
- if attribute mapping must be investigated, use redacted logs or synthetic test data containing no PII;
- never store raw HTTP bodies in public CI logs/screenshots/artifacts.

## 10. Cross-Checking Request, Response, and Metadata: One Table

| Claim to Verify | AuthnRequest | SAMLResponse/Assertion | Metadata/Config |
| --- | --- | --- | --- |
| SP entity ID | `Issuer` in AuthnRequest | `AudienceRestriction/Audience` | `SP EntityDescriptor.entityID`. |
| IdP entity ID | `Destination` is SSO endpoint, not entityID | `Response/Assertion.Issuer` | `IdP EntityDescriptor.entityID`. |
| Public ACS URL | `AssertionConsumerServiceURL`/index | `Destination` and `SubjectConfirmationData.Recipient` | `SP AssertionConsumerService.Location` and RP registration. |
| Request correlation | `ID` | `InResponseTo` (Response/SubjectConfirmationData) | Stored AuthnRequest repository/session. |
| Response binding | `ProtocolBinding` if SP specifies | HTTP POST/Artifact route | `SP ACS.Binding`. |
| IdP SSO binding/URL | Request sent to `Destination` | N/A | `IdP SingleSignOnService Binding/Location`. |
| NameID | `NameIDPolicy.Format` | `Subject/NameID.Format` and value | `IdP NameIDFormat` + identity contract. |
| Assurance | `RequestedAuthnContext`/ForceAuthn | `AuthnContextClassRef`/AuthnInstant | IdP/SP policy contract. |
| Signature trust | Redirect `SigAlg/Signature` or POST XMLSig | XML `ds:Signature` on Response/Assertion | Approved signing credential(s), signed metadata trust. |
| Time window | `IssueInstant` | `Conditions`/`SubjectConfirmationData` | Clock skew/cert and metadata validity policies. |
| Session logout | Request/Response context | `AuthnStatement.SessionIndex` | `SingleLogoutService` binding/URLs, state mapping. |

### 10.1. Example Failure: "Destination Matches but Audience Is Wrong"

~~~text
AuthnRequest Issuer:
  https://sp.example.test/metadata/appA

SAMLResponse Destination:
  https://sp.example.test/login/saml2/sso/appA

Assertion Audience:
  https://sp.example.test/metadata/appB  (WRONG)
~~~

A SAMLResponse might POST to the right ACS A while the Assertion was actually issued for SP B. **Never** allow A to log in merely because Destination matches and the IdP signature is valid. Audience must match **SP entityID A**.

### 10.2. Example Failure: "Same NameID Across Different IdPs"

~~~text
IdP-A entityID: https://idp-a.example.test/entity
NameID: user-17

IdP-B entityID: https://idp-b.example.test/entity
NameID: user-17
~~~

Two identical NameID strings **do not** prove the same local account. Linking keys require source/issuer/SP scope, or trusted immutable directory identity mapping. Never auto-map by `email` or bare NameID value alone.

### 10.3. Example Failure: "InResponseTo Mismatch"

~~~text
SP stored AuthnRequest ID: _req-100
Response.InResponseTo:      _req-200
SubjectConfirmationData:   _req-200
~~~

Possible causes:
- lost HttpSession between redirect and ACS POST;
- different browser/replay, expired request repository entry;
- concurrent logins in the same browser altering state depending on implementation;
- inconsistent reverse proxy load balancing/session store;
- attacker-crafted response.

**Do not disable `InResponseTo` validation to make tests pass** when an SP-initiated flow is required; analyze stored request state and the IdP response production contract. For IdP-initiated/unsolicited SSO, dedicated policy must protect against replay/wrong recipient/audience and must not unconditionally accept any response.

### 10.4. Example Failure: "Right Signing Cert, Yet Cannot Read EncryptedAssertion"

- The IdP signing verification cert verifies IdP signatures.
- The SP decryption private key decrypts Assertions that the IdP encrypted with the SP encryption public key.
- The SP signing private key signs AuthnRequests/logout if required.

These three roles are **distinct** even if some deployments reuse a keypair across roles. Never send the decryption private key to the IdP or an online decoder; never replace the IdP verify key with an SP key.

## 11. XML Signature: What Is Visible vs. What Must Be Verified

### 11.1. Having `ds:Signature` Is Not Enough

XML may contain:

~~~xml
<ds:Signature xmlns:ds="http://www.w3.org/2000/09/xmldsig#">
  <ds:SignedInfo>
    <!-- CanonicalizationMethod, SignatureMethod, Reference ... -->
  </ds:SignedInfo>
  <ds:SignatureValue>...</ds:SignatureValue>
  <ds:KeyInfo>...</ds:KeyInfo>
</ds:Signature>
~~~

An XML parser only tells you the tag exists. Accepting authentication requires checking:
1. **Signature Cryptography**: digest/reference/canonicalization/signature are valid over the right element/protocol profile.
2. **Trust**: the signer certificate/public key belongs to a verified RP registration/metadata source; do not auto-trust `KeyInfo` inside the payload.
3. **Signed element consumption**: the application consumes **the exact Assertion/Response verified by the validator**, preventing XML Signature Wrapping.
4. **Protocol Conditions**: right issuer, audience, recipient, InResponseTo, time window, SubjectConfirmation, and replay policy.
5. **Local account**: valid SAML identity link and local permission/tenant checks.

A valid Response may sign the Response or the Assertion per profile/trust configuration, yet "any signature anywhere" is not enough. Use the Spring/OpenSAML provider and corresponding policies; never write custom XPath to grab the first NameID before determining the signed subtree.

### 11.2. Metadata Certificates and Certificate Validity

- `KeyDescriptor` contains public keys/certs by role; it is **not a private key**.
- Metadata itself can be signed; a metadata signature differs from a SAML Assertion signature.
- Metadata `validUntil`, X.509 certificate `NotAfter`, and assertion `Conditions NotOnOrAfter` are **three separate expiration windows**.
- Explicit-key verification based on trust config does not mean every path automatically checks PKIX chains/CRL/OCSP; certificate expiry/revocation checks must be confirmed separately per policy/implementation.
- During an IdP certificate rollover, an approved key overlap period may be needed; **do not** swap certs immediately just because a Response carries an unfamiliar KeyInfo.
- Never treat metadata downloaded from a new URL as a trust source without checking domain/source/signature/certificate pinning.

### 11.3. Verifying HTTP-Redirect Signatures Over Exact Octets

Some tools decode SAMLRequest and then rebuild the query with differently percent-encoded values. Two URLs can decode to identical XML while having **different octets**, causing query signature verification to fail. When investigating:
- preserve the original raw query per policy and avoid rewriting `+`/`%20`/`%2B`;
- use the canonical parameter string order specified by OASIS;
- cross-check `SigAlg`/verification credential from SP metadata;
- never test a signature by merely checking whether a `Signature` string exists.

## 12. Troubleshooting by Symptom

### 12.1. IdP Reports "Invalid request" Immediately Upon Receiving AuthnRequest

Check `Issuer=SP entityID`, `Destination=IdP SSO URL`, AuthnRequest ID/IssueInstant, whether `AssertionConsumerServiceURL` is in the IdP allowlist, NameIDPolicy/AuthnContext policy, binding, signed request requirement, and SigAlg/key. If the request uses Redirect, verify raw-DEFLATE and query signature; do not use a POST XMLSig validator to verify it.

### 12.2. Browser Never POSTs SAMLResponse to ACS

Could it be IdP authentication failure, missing IdP session, user canceling login, wrong ACS URL, or network/proxy/CORS? A browser top-level form POST **is not an AJAX fetch**, so do not blame CORS by default. Check IdP status/error logs, HTML form action, browser navigation, TLS certificate, and response status.

### 12.3. ACS Receives POST and Returns 401/403/Redirect Loop

Check:
- Does `Saml2WebSsoAuthenticationFilter` match the right URL/HTTP method/registrationId?
- Is the request intercepted by a different API/stateless `SecurityFilterChain` or custom CSRF rule?
- Does `RelyingPartyRegistrationRepository` hold the right IdP cert/Issuer?
- Did signature/trust/audience/recipient/conditions/response correlation fail?
- Was the session cookie/state lost due to SameSite cross-site POST, load balancer, or reverse proxy?
- A failure handler returning 302 to login is valid HTTP behavior, **not proof that SAML validation passed**.

### 12.4. `Response.Status` Is Not Success

Read StatusCode/SubStatus and IdP audit. `NoAuthnContext`, `InvalidNameIDPolicy`, or `AuthnFailed` each require different remediation. Do not swap certificates when traces show the IdP rejected AuthnContext.

### 12.5. "Signature element present" Yet Validation Fails

Check:
- whether signing is on Response or Assertion, and what the trust agreement requires;
- whether the SP holds an old IdP cert or a newly rolled-over cert not yet updated;
- signing with an untrusted key, reference/digest mismatch, or altered XML;
- differing Redirect query canonicalization, or altered RelayState;
- broken XML parser wrapping/hardening or namespace conflicts;
- whether a certificate from another metadata source is valid and trusted.

Never bypass signature checks or trust a cert embedded inside the Response because the XML looks plausibly signed.

### 12.6. "NotBefore" or "NotOnOrAfter" Fails

Compare UTC clocks on IdP/SP, timezones, and NTP; inspect assertion timestamps, SubjectConfirmation, and request/response TTLs separately. Clock skew allowances must follow policy, not be increased unboundedly. Metadata expiry/X.509 validity **do not replace** assertion Conditions.

### 12.7. "Audience", "Recipient", and "Destination" Mismatch

- `Audience` must match the SP entityID;
- `Recipient` and `Destination` normally relate to the public ACS URL;
- `AuthnRequest.Issuer` is the SP entityID;
- `Response/Assertion.Issuer` is the IdP entityID;
- Incorrect `{baseUrl}` from an HTTP backend + HTTPS frontend is a frequent cause.

Never "fix" by string-replacing assertion XML and feeding it to login; that breaks signatures and hides config bugs.

### 12.8. "NameID Wrong Format" or App Extracts Wrong Email

The IdP may be issuing persistent/transient/emailAddress NameIDs per agreement, or attributes may be multi-valued. `NameID` is not automatically a local user ID; SAML `AttributeStatement` has `Name`/`NameFormat`/values requiring approved mapping. A valid signature never automatically grants an admin role.

### 12.9. ArtifactResolve Fails

If only `SAMLart` is present, check the SOAP ArtifactResolutionService URL, network/TLS, SAML artifact single-use/expiry, IdP back-channel credentials, and resolver logs. Do not debug with the Redirect inflater.

## 13. Test Matrix: Right Binding, Right Fields, Right Trust

| ID | Case | Expectation |
| --- | --- | --- |
| D01 | SP builds HTTP-Redirect SAMLRequest with proper binding. | URL-decode/Base64/raw-DEFLATE yields AuthnRequest XML. |
| D02 | Choosing `Inflater(false)` for raw DEFLATE. | Decode failure recognized, fixed with the right inflater. |
| D03 | Calling URLDecoder twice on `SAMLRequest`. | Test catches corrupted payload/mismatch vs raw query. |
| D04 | Raw form POST Base64 containing `+` decoded twice. | Reject/warn; do not turn `+` into space. |
| D05 | POST `SAMLResponse` valid Base64 XML without DEFLATE. | Decodes and parses safely. |
| D06 | POST `SAMLRequest` to IdP. | Base64 XML; no raw inflater. |
| D07 | GET/POST containing `SAMLart`. | Recognizes Artifact binding, does not assume XML. |
| D08 | Redirect with SigAlg/Signature. | Verifies query signature over exact encoded octets/trust. |
| D09 | Redirect with `Signature` that is invalid. | Validator rejects, not merely checking parameter presence. |
| D10 | POST XML with `ds:Signature` from untrusted key. | Validator rejects. |
| D11 | XML containing DOCTYPE/external entity. | Inspector parser rejects. |
| D12 | Oversized compressed XML (zip bomb). | Inspector enforces inflated byte limit. |
| D13 | Unsigned Response from test IdP. | Spring ACS rejects per signing policy. |
| D14 | Response signed with valid trusted test cert. | Authentication provider can accept if all conditions are valid. |
| D15 | Signed Assertion with wrong Audience. | Reject. |
| D16 | Response Destination has wrong public ACS. | Reject. |
| D17 | SubjectConfirmationData Recipient wrong. | Reject. |
| D18 | Response InResponseTo differs from AuthnRequest ID. | Reject SP-initiated per policy. |
| D19 | Missing request state/session. | Clear test failure; do not disable correlation. |
| D20 | Assertion Conditions not yet valid. | Reject beyond allowed clock skew. |
| D21 | Expired Assertion/SubjectConfirmation. | Reject. |
| D22 | Non-Success SAML Response status. | Do not create authenticated session. |
| D23 | Replayed Assertion ID/Response ID. | Replay prevented per implementation/policy. |
| D24 | EncryptedAssertion missing SP decrypt key. | Decryption fails; do not disable production encryption. |
| D25 | Multiple assertions, signature wrapping payload. | Validator consumes only signed/approved data. |
| D26 | NameIDPolicy requests persistent, IdP only supports transient. | Protocol/negotiation error; do not auto-map email. |
| D27 | AuthnContext requirement not met. | IdP error/step-up per policy. |
| D28 | IdP metadata entityID differs from Response Issuer. | Reject/review trust config. |
| D29 | SP metadata entityID differs from Assertion Audience. | Reject/correct metadata. |
| D30 | SP public HTTPS ACS differs from runtime {baseUrl}. | Test detects proxy/callback mismatch. |
| D31 | Wrong IdP SingleSignOnService Location. | AuthnRequest goes to wrong URL or IdP rejects. |
| D32 | SP ACS Binding differs from IdP Response binding. | Test detects binding mismatch. |
| D33 | Metadata has expired validUntil. | Refresh/trust policy avoids blindly using stale metadata. |
| D34 | X.509 signing cert rollover not yet configured. | Reject/alert; require approved overlap plan. |
| D35 | Metadata has KeyDescriptor from unverified source. | Do not auto-trust. |
| D36 | Signature embedded KeyInfo contains attacker cert. | Never use as trust anchor. |
| D37 | Duplicate SAML Request ID across concurrent logins. | Test detects ID generation/session correlation risk. |
| D38 | Tampered RelayState/open redirect. | Reject/tamper protection per binding/profile. |
| D39 | IdP entityID in multi-tenant RP resolved wrongly. | Must not map to wrong registration/account. |
| D40 | Same NameID from two IdPs. | Must not auto-link local user by bare NameID/email. |
| D41 | CSRF policy unexpectedly blocks cross-site ACS POST. | Fix filter matcher/protocol config, do not disable CSRF app-wide. |
| D42 | Browser SameSite drops request cookie on ACS. | Analyze cookie/session, test in real browser. |
| D43 | Metadata endpoint /saml2/metadata/lab returns valid EntityDescriptor. | SP metadata has right entityID/ACS/cert for test setup. |
| D44 | Inspector detects xmlSignatureElement=true. | Reports tag presence only; never reports signature pass. |
| D45 | Inspector selftest receives unsigned synthetic Response. | Parser reads fields; real ACS validation must fail if sent. |
| D46 | IdP signs Assertion with new cert during overlap period. | Trust only when cert is approved/rotation staged. |
| D47 | HAR contains raw SAMLResponse/cookies. | Privacy QA fail, redact/encrypt/restrict. |
| D48 | Capture packets on production account and paste to online decoder. | QA fail, switch to sandbox/local tool. |
| D49 | Browser only has SAMLart, no Assertion visible. | Inspect ArtifactResolve/Response in trusted server logs. |
| D50 | Disable signature/issuer/audience validation to make tests green. | Security QA fail, unacceptable. |
| D51 | SP sends AuthnRequest via POST but tool tries raw-DEFLATE. | Binding detection fails, fix pipeline. |
| D52 | Metadata EntityDescriptor contains both signing/encryption roles. | Properly distinguish trust/verifying/decrypting credentials. |

### 13.1. Lab A — Measuring a SAML2 Flow

1. Staging SP/IdP have trusted credentials, fresh browser.
2. Capture Network and find HTTP-Redirect `SAMLRequest` → verify raw DEFLATE decode, `Issuer`, `Destination`, ACS.
3. Log in test user, find HTTP-POST `SAMLResponse` → Base64 decode to XML.
4. Compare `AuthnRequest.ID` with `InResponseTo`, `SP entityID` with `Audience`, IdP `entityID` with Response/Assertion Issuer.
5. Verify a signed Response fixture using the real Spring/OpenSAML provider.
6. Never upload HAR/token/Assertion to external tools.

### 13.2. Lab B — Metadata and Rollover

1. Fetch SP metadata from `/saml2/metadata/lab` in sandbox.
2. Fetch IdP metadata from an approved source.
3. Compare `entityID`, SSO/ACS URLs, Binding, signing/encryption KeyDescriptor, `validUntil`/`cacheDuration`.
4. Simulate a test signing cert rollover with an overlap window and negative untrusted signer.
5. Verify metadata refresh/pinning per policy rather than trusting KeyInfo inside payloads.

### 13.3. Lab C — Negative SAML Responses

Generate signed synthetic fixtures with the test IdP key:
- valid SP-initiated response with matching `InResponseTo`;
- wrong audience and wrong recipient;
- expired/not-yet-valid conditions;
- untrusted signing key/invalid digest;
- response replay and EncryptedAssertion decryption failure;
- wrong NameID/attribute mapping, disabled local account.

**Do not** test the security provider using `MockMvc.with(authentication(new Saml2Authentication(...)))` because that intentionally bypasses signature/conditions validation.

## 14. Additional Inspection Tools and Their Limits

### 14.1. Browser SAML Viewer Extensions

Extensions exist that display SAML messages directly in Network. Before using one:
- check the extension source/code/permissions and ensure organizational approval;
- use only in a sandbox browser holding no production sessions;
- verify the extension sends no data to external servers;
- never rely on a "signature present" icon as a cryptographic trust verdict;
- never enable a third-party extension with access to all sites in your primary work browser.

### 14.2. `xmllint` and Pretty-Printing

A pretty-printer helps read XML **after decoding**, but XML from an IdP is untrusted input. Disable network access/external entities, bound input sizes, and never use a default XML parser on untrusted documents in production. Moreover, **reformatting XML can break signature semantics/canonicalization** if used for verification; pretty-printing is for display only, never as input bytes for signatures.

### 14.3. OpenSSL/Certificate Inspection

For an IdP certificate fixture that was properly provisioned and managed, you can view subject/serial/dates/fingerprint:

~~~bash
openssl x509 -in lab-idp-signing.crt -noout \
  -subject -issuer -dates -serial -fingerprint -sha256
~~~

This is a **descriptive inspection of a public certificate**, not SAML signature verification. If the certificate in metadata is Base64 DER inside `ds:X509Certificate`, extract/format it into valid PEM in sandbox before running OpenSSL; never copy private keys. A fingerprint matching a cert sent by the IdP **is not sufficient** if the source of the fingerprint was not approved by an admin.

### 14.4. Testing Signed Responses with Spring/OpenSAML

Only an integration test running through `Saml2WebSsoAuthenticationFilter` with a test `RelyingPartyRegistration`/trust credentials and a properly signed SAMLResponse fixture actually tests:
- signature trust, issuer, audience, destination, conditions;
- request/session correlation, bearer SubjectConfirmation;
- local user identity/role mapping;
- authenticated session after callback;
- negative responses not creating sessions.

Mocking `AuthenticationManager` or injecting a pre-built `Saml2Authentication` is a **post-authentication test**, not an XML security test.

## 15. Safe Runbook for SAML Login Failures

1. **Identify the exact flow:** SP-initiated or IdP-initiated; Redirect, POST, or Artifact binding; which registrationId/source IdP.
2. **Reproduce in sandbox** with a synthetic user, accurate UTC/NTP clock, proxy, and clean browser session.
3. **Capture minimal trace** via Network Preserve log; record method/URL/status and parameter names without exposing payloads.
4. **Decode locally per binding:** Redirect raw DEFLATE, POST Base64 XML, Artifact back-channel.
5. **Compare XML fields:** request ID, Issuers, Destination, ACS, Response Status, Audience, Recipient, Conditions, NameIDPolicy/AuthnContext.
6. **Compare trusted metadata:** entity IDs, SSO/ACS endpoints/bindings, signing verification certificate, validity/cache.
7. **Run the real validator:** inspect the Spring/OpenSAML authentication failure category; never infer signature pass from an XML parser.
8. **Check state:** session cookie/SameSite, stored AuthnRequest, InResponseTo, Load Balancer/Redis, clock skew.
9. **Isolate configuration fix:** URI/proxy/certificate rollover/NameIDPolicy/AuthnContext or trust policy; never disable crypto validation.
10. **Regression test** with valid/invalid SAML fixtures (D01–D52), and verify local account/tenant authorization.
11. **Restore log levels** to safe defaults, redact/delete raw traces, and rotate credentials if any were accidentally exposed.
12. **Document findings:** root cause, impact, verified fix, owner, rollout/rollback, and follow-up tests.

### 15.1. Redacted Report Template

~~~text
scenario=SAML_SP_INITIATED_REDIRECT_POST
registration=lab
binding_request=HTTP-Redirect
binding_response=HTTP-POST
sp_entity_id_match=PASS
idp_issuer_match=PASS
acs_destination_match=FAIL
audience_match=PASS
in_response_to_match=PASS
signature_validation=NOT_EVALUATED_BY_INSPECTOR
provider_validation=FAIL_DESTINATION
raw_payload_shared=false
action=FIX_TRUSTED_PUBLIC_BASE_URL_AND_UPDATE_IDP_ACS
~~~

Never conclude `signature_validation=PASS` just because `ds:Signature` is in the XML or metadata contains a cert. If you only parsed it, write `NOT_EVALUATED`.

### 15.2. Metrics and Observability

Proposed metrics (**not** emitted automatically by Spring by default):

~~~text
saml_authnrequest_created_total{registration,binding}
saml_authnrequest_failed_total{registration,reason_class}
saml_response_received_total{registration,binding}
saml_response_validation_failed_total{registration,reason_class}
saml_response_authenticated_total{registration}
saml_request_correlation_failed_total{registration}
saml_metadata_refresh_total{registration,result}
saml_metadata_key_rollover_total{registration,result}
saml_assertion_decryption_failed_total{registration}
saml_replay_rejected_total{registration}
~~~

Labels must never include username, NameID, email, raw SAMLResponse ID, session IDs, cookies, X509Certificate, or RelayState; avoid PII and high cardinality. Use opaque test correlation IDs and access-controlled logs.

## 16. Misconceptions to Eliminate

| Misconception | Why It Is Wrong | Correction |
| --- | --- | --- |
| "Base64 SAMLRequest always decodes straight to XML." | Redirect binding also uses raw DEFLATE. | Detect binding before decoding. |
| "POST SAMLResponse is also DEFLATEd." | POST binding normally Base64-encodes XML directly. | Form-decode → Base64 → XML. |
| "Seeing Signature means login is secure." | Crypto/trust/Conditions have not been verified yet. | Use the real provider. |
| "No ds:Signature in Redirect AuthnRequest means unsigned." | `SigAlg/Signature` may be in the URL query. | Verify query signature per spec. |
| "Metadata has a certificate so it is trusted." | Metadata can be spoofed or key untrusted. | Trusted source/signature/pinning. |
| "Metadata validUntil is the cert expiration." | Metadata and X.509 have two separate expirations. | Track separately. |
| "Issuer is the IdP SSO endpoint URL." | IdP entityID may differ from the SSO URL. | Compare against metadata entityID. |
| "Audience is the ACS URL." | Audience is usually the SP entityID, distinct from Recipient/ACS. | Match the right fields. |
| "Matching Response Destination is enough." | Assertion Audience/Recipient/signature/time can still be wrong. | Validate everything. |
| "Unsolicited Response needs no security." | Missing request correlation raises replay/mix-up risk. | Dedicated policy with strict checks. |
| "Browser decoder must be able to read EncryptedAssertion." | Requires the SP decryption private key. | Use test SP key in sandbox. |
| "SAMLart is Base64 SAMLResponse." | Artifact is a reference, not XML. | Inspect SOAP Artifact Resolution. |
| "NameID=email so match local user by email." | Email can change/be reassigned, cross-IdP collision. | Trusted scoped account linking. |
| "MockMvc auth fixture passes => signed Response passes." | Fixture bypasses ACS signature validation. | Signed fixture integration test. |
| "Disable signature validation to debug." | Removes trust boundary and masks the real bug. | Fix key/metadata/clock/ACS. |
| "Just log raw SAMLResponse and delete later." | Easy to leak PII/credentials into backup retention. | Minimal/redacted evidence. |

## 17. Pre-QA Sign-Off Checklist

- [ ] Staging/test users and IdP used; no sensitive production data captured.
- [ ] SP-initiated/IdP-initiated and HTTP-Redirect/POST/Artifact bindings clearly identified.
- [ ] Raw encoded query stored only when truly needed for signature debugging, in secure test storage.
- [ ] HTTP-Redirect: URL-decode once → Base64 → raw DEFLATE; no gzip/zlib wrapper.
- [ ] HTTP-POST: form-decode once → Base64 XML; no inflate.
- [ ] HTTP-Artifact: understood that SAMLart requires SOAP back-channel resolution.
- [ ] XML parser blocks DTD/external entities/XXE and enforces input/decompression limits.
- [ ] Signed Redirect query distinguished from XML `ds:Signature`.
- [ ] Signature pass never claimed merely from `Signature` parameter or XML element presence.
- [ ] `AuthnRequest Issuer`, Destination, ACS, RequestedAuthnContext, and ID reconciled.
- [ ] `Response Status`, Issuer, InResponseTo, and Destination reconciled.
- [ ] `Assertion Audience`, Conditions, SubjectConfirmation Recipient/InResponseTo/expiry, and signature verified by provider.
- [ ] IdP metadata entityID, SSO Location/Binding, KeyDescriptors, and validUntil checked.
- [ ] SP metadata entityID, public HTTPS ACS, signing/encryption roles, and bindings match.
- [ ] Metadata trust source/signature/pinning and rollover policies verified.
- [ ] SAML XML signature verification uses trusted IdP public keys; unverified KeyInfo not trusted.
- [ ] InResponseTo/replay/clock skew limits not disabled to make failing tests pass.
- [ ] Metadata expiry, X.509 expiry, and assertion time Conditions distinguished.
- [ ] EncryptedAssertion decrypted only using a managed SP private key in sandbox.
- [ ] Spring Security SAML filter chain has right endpoints, RP registration/cert, and session state.
- [ ] Local account/roles/tenant continue to be checked after authentication.
- [ ] Tests D01–D52 or equivalent coverage include numerous negative crypto/protocol cases.
- [ ] Logs/HAR/fixtures redacted, TTL-bounded, and not uploaded to online decoders.
- [ ] After debugging, verbose logging disabled and security controls preserved.

## Takeaway

> **Reading SAML is an observability task, not authentication.** For **HTTP-Redirect**, decode `SAMLRequest` via **URL decode → Base64 → raw DEFLATE**; for **HTTP-POST**, decode `SAMLResponse` via **form decode → Base64 XML**. Then reconcile **Request/Response/Assertion against IdP/SP metadata**, while secure login conclusions must rest on **signature/trust validation, time, issuer/audience/recipient, InResponseTo/replay, and local authorization** enforced by Spring Security/OpenSAML. Use test data only and never disseminate SAML payloads containing personal identifiers.

### Official References

- [OASIS — SAML 2.0 Bindings](https://docs.oasis-open.org/security/saml/v2.0/saml-bindings-2.0-os.pdf): HTTP-Redirect raw DEFLATE, Base64, URL encoding, SigAlg/Signature, POST, and Artifact.
- [OASIS — SAML 2.0 Core](https://docs.oasis-open.org/security/saml/v2.0/saml-core-2.0-os.pdf): AuthnRequest, Response, Assertion, Conditions, NameID, SubjectConfirmation, Audience.
- [OASIS — SAML 2.0 Metadata](https://docs.oasis-open.org/security/saml/v2.0/saml-metadata-2.0-os.pdf): EntityDescriptor/IDPSSODescriptor/SPSSODescriptor/KeyDescriptor/validUntil.
- [OASIS — SAML 2.0 Profiles](https://docs.oasis-open.org/security/saml/v2.0/saml-profiles-2.0-os.pdf): Web Browser SSO, unsolicited/IdP-initiated, SubjectConfirmation.
- [Spring Security — SAML 2.0 Login Overview](https://docs.spring.io/spring-security/reference/servlet/saml2/login/overview.html): SP/RP, AuthnRequest filter, ACS filter, provider validation, RP registration.
- [Spring Security — Producing AuthnRequests](https://docs.spring.io/spring-security/reference/servlet/saml2/login/authentication-requests.html): initiate endpoint, encoded Redirect request, and request repository.
- [Spring Security — Authenticating SAML Responses](https://docs.spring.io/spring-security/reference/servlet/saml2/login/authentication.html): Saml2Authentication, principal/attributes, response processing.
- [Spring Security — SAML 2.0 Metadata](https://docs.spring.io/spring-security/reference/servlet/saml2/metadata.html): `saml2Metadata` DSL, metadata endpoints, RP registration.
- [Spring Security — Servlet Security Architecture](https://docs.spring.io/spring-security/reference/servlet/architecture.html): SecurityFilterChain/FilterChainProxy ordering.
- [RFC 1951 — DEFLATE Compressed Data Format](https://www.rfc-editor.org/rfc/rfc1951.html): raw DEFLATE data model.
- [OWASP — XML External Entity Prevention Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/XML_External_Entity_Prevention_Cheat_Sheet.html): secure JAXP parser configuration.
- [OWASP — SAML Security Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/SAML_Security_Cheat_Sheet.html): signature wrapping, issuer/trust, replay, validation.
