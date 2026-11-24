# Choosing HTTP-Redirect or HTTP-POST for AuthnRequest Based on Partner Capabilities

> **Topic:** Spring Security – federation. **Group:** AuthnRequest Customization. This article explains how a Service Provider (SP/Relying Party) chooses **SAML 2.0 HTTP-Redirect Binding** or **HTTP-POST Binding** when sending `<samlp:AuthnRequest>` to an Identity Provider (IdP/Asserting Party), how to check the IdP's actual capabilities, configure Spring Security, and verify the working flow with browser evidence.

## 1. Why Must You Choose the Right Binding?

When an unauthenticated user accesses a protected resource, the SP initiates SAML login with an **AuthnRequest**. This message contains attributes such as `ID`, `IssueInstant`, `Destination`, `AssertionConsumerServiceURL` when configured, `Issuer`, and authentication options. The message must reach the right **SingleSignOnService (SSO)** supported by the IdP.

**SAML binding** defines how the message is transported over HTTP. For AuthnRequest in Web Browser SSO, the two common bindings are:

- **HTTP-Redirect:** Spring places the message into the query string of the SSO URL and responds with a redirect so the **browser performs a GET** to the IdP.
- **HTTP-POST:** Spring renders an HTML page containing a form with a hidden input carrying the message and has the **browser perform a POST** to the IdP.

Both can be valid choices. However, a partner may enable only one type, have **different** SSO URLs for each binding, or require a signature in the format matching that binding. Merely changing `GET` to `POST` in a controller or changing the URL arbitrarily will not satisfy the SAML specification.

**The decision must be based on IdP metadata and verified testing with the partner**, not on endpoint naming preferences. Spring Security's default is typically to generate AuthnRequest via **HTTP-Redirect**; when the IdP requires HTTP-POST, the SP must configure the corresponding binding.

## 2. Do Not Confuse the AuthnRequest Binding with the SAMLResponse Binding

Common SSO flow:

```text
Browser           Spring SP / RP                       SAML IdP
   |                    |                                  |
   | GET /private       |                                  |
   |------------------->|                                  |
   |    302 to login/authenticate                          |
   |<-------------------|                                  |
   | GET /saml2/authenticate/partner                       |
   |------------------->|                                  |
   |                    | Create AuthnRequest, save correlation
   |                    |                                  |
   |==== OPTION A: HTTP-Redirect ==========================|
   |<--- 302 Location: IdP/SSO?SAMLRequest=...&RelayState=...|
   |------------------------ GET IdP/SSO ------------------->|
   |                    |                                  |
   |==== OPTION B: HTTP-POST ==============================|
   |<--- HTML form with hidden SAMLRequest and RelayState ---|
   |----------------------- POST IdP/SSO ------------------->|
   |                    |                                  |
   |            IdP authenticates user                     |
   |<---------------- SAMLResponse form -------------------|
   | POST /login/saml2/sso/partner                         |
   |------------------->| Verify response, create session  |
   |<---- redirect -----|                                  |
   | GET /private       |                                  |
   |------------------->|                                  |
   |<--- 200 -----------|                                  |
```

Only **one** of options A/B is used to send a given AuthnRequest. Afterward, the IdP usually returns the **SAMLResponse via HTTP-POST** to the SP's **Assertion Consumer Service (ACS)**, such as `/login/saml2/sso/partner`.

**Key point to remember:** HTTP-Redirect **for AuthnRequest** is completely compatible with HTTP-POST **for SAMLResponse**. The bindings for the two directions are chosen **independently based on what both sides support**. Do not enable POST for the request just because the response is POSTed to the ACS; do not change the ACS configuration when you only want to change how the AuthnRequest is sent.

The SAML 2.0 protocol also has HTTP-Artifact Binding. This article focuses on the two choices commonly used in Spring SP configurations—Redirect and POST—without treating them as an exhaustive list of all possible SAML bindings.

## 3. HTTP-Redirect Binding Mechanism

### 3.1. Packaging Steps

For standard HTTP-Redirect Binding:

1. The SP constructs the `<samlp:AuthnRequest>` XML per SAML 2.0, including a unique `ID` and current `IssueInstant`.
2. The XML is compressed using **raw DEFLATE** per the binding rules, then Base64-encoded and URL-encoded into the `SAMLRequest` parameter.
3. If correlation state exists, the `RelayState` value is carried in the query string, containing only values conforming to size limits and security policy.
4. If signing the AuthnRequest over Redirect is required, the SP prepares `SigAlg` and `Signature` according to the **binding's signature rules over URL-encoded query parameters**, not merely signing the XML as in POST.
5. The SP responds with an appropriate HTTP 302/303 to send the browser to the IdP's `SingleSignOnService` URL.
6. The browser performs a GET to the target URL; the IdP decodes and validates the request/binding/signature and performs authentication.

Illustrative request shape (real `SAMLRequest` values are very long and vary per session):

```http
GET /saml/sso/redirect?SAMLRequest=...&RelayState=...&SigAlg=...&Signature=... HTTP/1.1
Host: idp.partner.example
```

`SigAlg` and `Signature` appear when the request is signed under HTTP-Redirect Binding; they are **not always present**. When unsigned, ensure the IdP's policy truly accepts unsigned requests. A URL containing these parameters is **not an access token** for calling APIs.

### 3.2. Pros and Cons to Evaluate

**Advantages:** Simple and widespread; the browser only follows a redirect with no JavaScript auto-submit required; many IdPs provide a Redirect endpoint as the default option; easy to inspect in DevTools via status 302, `Location`, and GET requests.

**Limitations:** Compressed/Base64/URL-encoded XML can still be long, especially with complex `RequestedAuthnContext`, `Scoping`, or `Extensions`. Long URLs may be rejected by browsers, proxies, ingress, WAF, CDN, or the IdP due to request-line/query-string limits; **there is no single character threshold valid across all infrastructure**. URL parameters also risk appearing in browser history, proxy logs, tracing, and other URL logs. Use TLS, minimize logging, and avoid placing PII/secrets in RelayState.

**Signatures:** When the IdP requires a signed AuthnRequest, the SP must have a registered private signing key. With Redirect Binding, signature verification typically relies on the query string constructed exactly per rules from `SAMLRequest`, `RelayState` (if present), and `SigAlg`. If a gateway rewrites/query-normalizes a signed URL, the IdP may reject it because the signature is no longer valid.

## 4. HTTP-POST Binding Mechanism

### 4.1. Packaging Steps

When using HTTP-POST Binding:

1. The SP constructs the `<samlp:AuthnRequest>` XML and stores correlation data for this login attempt.
2. If the request must be signed, the signature is typically an **XML Digital Signature** attached to the SAML message, with profile-appropriate canonicalization/transforms. This mechanism differs from Redirect Binding's query signature.
3. The message XML is Base64-encoded and placed in a hidden `SAMLRequest` field inside an HTML form.
4. The SP returns an HTML form page whose `action` points to the **SingleSignOnService Location for POST**. The browser submits the form via POST, usually automatically via JavaScript.
5. The IdP receives the `application/x-www-form-urlencoded` body, decodes and validates the AuthnRequest, proceeds with authentication, and returns the SAMLResponse per the agreed binding.

HTML shape illustrating the structure (**not a real payload to send to an IdP**):

```html
<form method="post" action="https://idp.partner.example/saml/sso/post">
  <input type="hidden" name="SAMLRequest" value="BASE64_SAML_REQUEST">
  <input type="hidden" name="RelayState" value="OPAQUE_CORRELATION_VALUE">
  <button type="submit">Continue to sign in</button>
</form>
```

In practice, the framework generates valid values and an auto-submitting form per its implementation. Do not copy this illustrative HTML into a controller to send real requests: manual serialization/encoding/signing is very error-prone, bypasses the request repository, or leaks data.

### 4.2. Pros and Cons to Evaluate

**Advantages:** The message is not placed in the query URL, so it avoids URL length limits and is less likely to be recorded in logs that only capture request URLs. POST is suitable when AuthnRequests are large or when the partner supports/expects an XML signature under HTTP-POST Binding.

**Limitations:** The browser must submit a form, typically using HTML/JavaScript auto-submit; CSP policies, script-blocking extensions, proxy-rewritten HTML pages, or IdP infrastructure blocking POST can cause failures. Data **still passes through the browser** and can be observed in the network panel, so POST does not make the content secret; HTTPS remains mandatory. If the IdP only has a Redirect endpoint, sending a form POST there will be rejected.

**Signatures:** With traditional POST Binding, the IdP expects a SAML XML Signature if a signed AuthnRequest is required. Do not take a `Signature` string from a Redirect query, put it into a form, and expect the IdP to accept it. Some products have other signature modes/extensions; you must agree on the exact binding, algorithm, and verification method per the actual profile.

## 5. Comparison Table to Choose Properly

| Criterion | HTTP-Redirect for AuthnRequest | HTTP-POST for AuthnRequest |
| --- | --- | --- |
| Browser sends to IdP via | **GET** after HTTP 302/303 from SP | **POST** from SP's HTML form |
| Location of `SAMLRequest` | Query string on IdP URL | Hidden form field in body |
| Typical encoding | XML → raw DEFLATE → Base64 → URL encoding | XML → Base64, without applying the same DEFLATE pipeline as Redirect |
| `RelayState` | Query parameter | Form field |
| Request signature per binding | `SigAlg`/`Signature` over normalized query per specification | XML Signature inside the message when signed |
| Request length | Subject to URL/request-line limits of intermediate hops | Less affected by URL limits, still subject to browser/proxy/IdP body limits |
| Runtime observation | 302 Location and GET containing `SAMLRequest` | HTML form and POST containing `SAMLRequest` |
| Exposure in URL logs | Higher, since data is in the URL | Lower for URL logs; risk remains in body/debug tools |
| Requirement at IdP | Endpoint in metadata with Redirect binding | Endpoint in metadata with POST binding |
| Baseline security posture | Not inherently less secure with signing, TLS, and proper validation | Not inherently more secure just because it is POST |
| Common use cases | Standard SSO flows, moderate-size AuthnRequest | Partner accepts only POST, requires XML signature, large requests |
| SP side after authentication | Receives SAMLResponse at ACS, usually HTTP-POST | **Also** receives SAMLResponse at ACS, usually HTTP-POST |

**Terminology note:** “HTTP redirect” in this context may mean (a) an HTTP 302/303 response, or (b) **SAML HTTP-Redirect Binding** including message encoding/signing rules; do not conflate the two concepts. Likewise, an arbitrary HTTP POST is not automatically a compliant **SAML HTTP-POST Binding**.

## 6. Source of Truth for Knowing Which Binding a Partner Supports

### 6.1. Reading `SingleSignOnService` Accurately in IdP Metadata

IdP metadata typically has one or more `SingleSignOnService` elements inside `IDPSSODescriptor`:

```xml
<md:IDPSSODescriptor
    xmlns:md="urn:oasis:names:tc:SAML:2.0:metadata"
    protocolSupportEnumeration="urn:oasis:names:tc:SAML:2.0:protocol">
  <md:SingleSignOnService
      Binding="urn:oasis:names:tc:SAML:2.0:bindings:HTTP-Redirect"
      Location="https://idp.partner.example/saml/sso/redirect"/>
  <md:SingleSignOnService
      Binding="urn:oasis:names:tc:SAML:2.0:bindings:HTTP-POST"
      Location="https://idp.partner.example/saml/sso/post"/>
</md:IDPSSODescriptor>
```

This is an **illustrative metadata snippet**, not a complete SAML metadata file: it lacks `EntityDescriptor`, `entityID`, X.509 certificates, and signatures. Do not import this structurally incomplete XML into Spring as a real registration.

Information to extract from real metadata:

- `EntityDescriptor/@entityID`: agreed logical identifier of the IdP; not necessarily equal to the SSO URL.
- `IDPSSODescriptor/SingleSignOnService/@Binding`: exact URN, such as `urn:oasis:names:tc:SAML:2.0:bindings:HTTP-Redirect` or `...:HTTP-POST`.
- `SingleSignOnService/@Location`: actual URL for **that binding**, typically HTTPS.
- `WantAuthnRequestsSigned` (if present) along with partner-provided policy: does the IdP require the SP to sign requests?
- Signing algorithms/certificates, `Issuer` requirements, `NameIDPolicy`, `RequestedAuthnContext`, and extensions if validated by the IdP.

If the IdP declares both bindings, do not guess which endpoint defaults to your use case: check integration guides, the contract, SP signing capabilities, and test with the IdP. Some IdPs share a single URL for POST/Redirect, while others use two distinct URLs. **Do not send POST to a Redirect URL merely because the hostname matches.**

### 6.2. Where Does Trusted Metadata Come From?

Obtain IdP metadata through an administratively approved channel or use a verified file. Verify the agreed `entityID` and signing certificate; if metadata signatures are used, verify them against an independent trust anchor. Do not accept an arbitrary metadata URL from a tenant and have the backend fetch it automatically. An HTTP redirect during backend metadata fetching is **different from SAML HTTP-Redirect Binding** and can create SSRF risks if URLs/egress are uncontrolled.

Archive the approved metadata to compare and pinpoint the exact `Binding` + `Location` when a partner updates endpoints. If old metadata contained POST but a new IdP version disabled POST, coordinate the change, re-test, and deploy with the partner; do not silently “fall back” to another binding without approval.

## 7. Decision Process Based on Partner Capabilities

Follow these steps in order:

1. **Collect IdP metadata** from a trusted source; confirm the exact IdP `entityID` and signing certificate.
2. List all `SingleSignOnService` entries, each as **Binding + Location**. If the IdP declares only Redirect, choose Redirect; if it declares only POST, choose POST when supported by your Spring version.
3. If both are supported, prefer Redirect for compact AuthnRequests and broad compatibility; consider POST when requests are large, the IdP mandates it, or POST signing fits that environment better.
4. Clarify **whether the IdP requires signed AuthnRequests**, which algorithms, and which SP certificate the partner has registered; this can determine binding feasibility.
5. Lock the binding and **the target SSO URL for that same binding** in `RelyingPartyRegistration`/Spring Boot. Do not let the browser/client choose the binding via an untrusted query parameter.
6. Run an end-to-end browser flow and verify results in DevTools: method, target URL, `SAMLRequest` location, properly formatted signature, IdP acceptance, ACS receiving SAMLResponse, and SP establishing a session.
7. Before production, test through actual ingress/WAF/proxy, checking URL/request size, CSP, cookies/RelayState, TLS, and IdP metadata lifecycle updates.

A decision record should be documented in deployment docs:

| Attribute | Example Decision |
| --- | --- |
| `registrationId` | `partner` |
| IdP issuer | `https://idp.partner.example/entity` |
| AuthnRequest binding | `HTTP-POST` |
| SSO URL for this binding | `https://idp.partner.example/saml/sso/post` |
| Signed requests | Yes, SP certificate registered with IdP |
| Response binding/ACS | IdP sends SAMLResponse via POST to `https://sp.example.org/login/saml2/sso/partner` |
| Test path | Browser login, inspect POST body/response/session and wrong-binding cases |
| Change owners | SP integration team + IdP point of contact |

## 8. Spring Boot Configuration by Binding

**Shared assumptions:** Servlet Spring Boot + Spring Security SAML2 application; a real test IdP exists, and SP entityID, ACS URL/certificates are registered with the partner. The `*.example` domains below are illustrative; replace them with approved values and supply real certificates. The snippets are **two alternative options**—do not copy both to conflict over the same `registrationId`.

### 8.1. HTTP-Redirect Option

File `application.yml`:

```yaml
spring:
  security:
    saml2:
      relyingparty:
        registration:
          partner:
            assertingparty:
              entity-id: https://idp.partner.example/entity
              verification:
                credentials:
                  - certificate-location: classpath:saml/idp-signing.crt
              singlesignon:
                url: https://idp.partner.example/saml/sso/redirect
                binding: REDIRECT
                sign-request: false
```

**Meaning:** When the user initiates `/saml2/authenticate/partner`, the SP creates an AuthnRequest and directs the browser to GET the Redirect endpoint. The `sign-request: false` sample **applies only when the test IdP genuinely accepts unsigned AuthnRequests**. Do not disable request signing if the IdP or federation agreement requires signing. The `idp-signing.crt` certificate is used by the SP to **verify signatures from the IdP**; it is not the key for the SP to sign requests.

If the IdP requires signed AuthnRequests, you must declare the **SP** signing key/certificate and enable `sign-request: true`; see the configuration example in section 8.3.

### 8.2. HTTP-POST Option

File `application.yml`, applied to the same registration in an **alternative** configuration:

```yaml
spring:
  security:
    saml2:
      relyingparty:
        registration:
          partner:
            assertingparty:
              entity-id: https://idp.partner.example/entity
              verification:
                credentials:
                  - certificate-location: classpath:saml/idp-signing.crt
              singlesignon:
                url: https://idp.partner.example/saml/sso/post
                binding: POST
                sign-request: false
```

**Meaning:** Setting `singlesignon.binding: POST` selects HTTP-POST Binding to send the AuthnRequest to the declared `url`. Spring can render a form page for the browser to POST `SAMLRequest` to the IdP. Choosing `POST` does not change the ACS callback (still typically `/login/saml2/sso/partner`) and does not change SAMLResponse verification configuration.

If the IdP mandates signing, switch to `sign-request: true` with **SP signing credentials** and ensure the IdP has stored the SP signing certificate. The signature corresponding to POST Binding must be verified as an XML signature, not a Redirect query signature.

### 8.3. When the IdP Requires a Signed AuthnRequest

Separate example for signed POST; files/certificates **must actually exist, belong to the SP, and be managed secretly**:

```yaml
spring:
  security:
    saml2:
      relyingparty:
        registration:
          partner:
            signing:
              credentials:
                - private-key-location: file:/run/secrets/sp-signing.key
                  certificate-location: file:/run/secrets/sp-signing.crt
            assertingparty:
              entity-id: https://idp.partner.example/entity
              verification:
                credentials:
                  - certificate-location: classpath:saml/idp-signing.crt
              singlesignon:
                url: https://idp.partner.example/saml/sso/post
                binding: POST
                sign-request: true
```

In a live environment, adjust secret paths to your topology, use HTTPS, grant minimal read permissions on the private key, and register the **public SP signing certificate** with the IdP. The `sign-request` parameter controls **whether AuthnRequest signing is requested**, whereas asserting party `verification.credentials` are used to verify **IdP-signed SAMLResponse/Assertion**. The two certificate sets serve different purposes.

If converting this example to a signed Redirect request, change both `binding: REDIRECT` and `url` to the Redirect endpoint published by the IdP, keeping the registered SP signing key. Spring will apply the signing rules of the corresponding binding. **Do not generate query `Signature` or XML signatures manually in a controller**.

**Version compatibility:** The properties `spring.security.saml2.relyingparty.registration.*.assertingparty.singlesignon.binding` and `sign-request` are mapped by Spring Boot from `Saml2RelyingPartyProperties`. Check your running Spring Boot/Spring Security version to use the exact package and API; an alternative Java configuration is below.

## 9. Configuring `RelyingPartyRegistration` Directly in Java

If the project manages registrations in Java, Spring Security allows setting the binding via `Saml2MessageBinding`. The example here starts from a **verified IdP metadata file**, then explicitly selects the partner's POST endpoint.

File `src/main/java/com/example/saml/PartnerSamlConfig.java`:

```java
package com.example.saml;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.saml2.provider.service.registration.InMemoryRelyingPartyRegistrationRepository;
import org.springframework.security.saml2.provider.service.registration.RelyingPartyRegistration;
import org.springframework.security.saml2.provider.service.registration.RelyingPartyRegistrationRepository;
import org.springframework.security.saml2.provider.service.registration.RelyingPartyRegistrations;
import org.springframework.security.saml2.provider.service.registration.Saml2MessageBinding;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class PartnerSamlConfig {

    @Bean
    RelyingPartyRegistrationRepository relyingParties() {
        RelyingPartyRegistration partner =
            RelyingPartyRegistrations
                .fromMetadataLocation("classpath:saml/idp-approved.xml")
                .registrationId("partner")
                .assertingPartyMetadata(party -> party
                    .singleSignOnServiceLocation(
                        "https://idp.partner.example/saml/sso/post")
                    .singleSignOnServiceBinding(Saml2MessageBinding.POST))
                .build();

        return new InMemoryRelyingPartyRegistrationRepository(partner);
    }

    @Bean
    SecurityFilterChain web(HttpSecurity http) throws Exception {
        return http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/", "/error",
                    "/saml2/authenticate/**").permitAll()
                .anyRequest().authenticated())
            .saml2Login(Customizer.withDefaults())
            .build();
    }
}
```

**How to read this sample properly:**

- `fromMetadataLocation("classpath:saml/idp-approved.xml")` reads **approved** metadata, not a user-supplied URL. The file must be real SAML metadata with valid `entityID`, signing certificates, and endpoints; it **cannot be constructed solely from the short illustrative XML in this article**.
- `.singleSignOnServiceBinding(Saml2MessageBinding.POST)` selects POST for the AuthnRequest. `singleSignOnServiceLocation(...)` is specified explicitly so you do not accidentally use a **Redirect URL** taken from metadata while changing the binding to POST.
- Ensure the IdP metadata/contract genuinely declares POST support at that URL. Do not invent an imaginary POST endpoint.
- The `SecurityFilterChain` bean enables `saml2Login`. `saml2Login` wires in the filters that generate AuthnRequests and handle SAMLResponses, so you do not write custom AuthnRequest/ACS controllers.
- This Java snippet **does not declare separate SP signing credentials**: it only applies when the IdP permits unsigned AuthnRequests or when another part of the registration configuration provides the appropriate credentials. For partners requiring signatures, add `signingX509Credentials` and signing policy to the registration, or use the complete YAML in section 8.3.

**Build requirements:** This is a Spring Boot application class using Java 17+ and Spring Web, Spring Security, and `spring-security-saml2-service-provider` dependencies. It is not a standalone Java program run with plain `javac`. If the metadata on the classpath is missing or invalid, the application context may fail to start. Do not simultaneously register this bean and another conflicting repository bean for the same registrationId.

To switch back to Redirect when the partner requests it, replace `Saml2MessageBinding.POST` with `Saml2MessageBinding.REDIRECT` **and** update the location to the corresponding Redirect endpoint. You do not need to change the default `/saml2/authenticate/partner` endpoint merely because the IdP-side binding changed.

## 10. Parts of `saml2Login` Unchanged by Binding Selection

### 10.1. SP-Side SSO Initiation URL

Spring Security uses `Saml2WebSsoAuthenticationRequestFilter` to receive AuthnRequest initiation requests, commonly:

- `GET /saml2/authenticate/{registrationId}`, such as `/saml2/authenticate/partner`.
- Query variant `/saml2/authenticate?registrationId=partner` in supported versions.

This is the **endpoint on the SP called by the browser to start SSO**. Afterward, the SP chooses Redirect or POST to send the AuthnRequest to the **IdP SSO endpoint**; setting HTTP method POST on `/saml2/authenticate/partner` does not turn the outgoing binding into HTTP-POST.

### 10.2. ACS Is Where SAMLResponse Is Received

The common ACS is `POST /login/saml2/sso/{registrationId}`, processed by `Saml2WebSsoAuthenticationFilter`. It must accept browser requests **before an SP session exists**, but the SAMLResponse is trusted only after checking signature, issuer, `AudienceRestriction`, `Destination`, `Recipient`, `InResponseTo` (when applicable), time conditions, and replay protection.

Configuring `permitAll` for protocol URLs does not bypass the authentication filter. Do not use `web.ignoring("/login/saml2/sso/**")` or write a custom controller receiving Base64 assertions.

### 10.3. Storing AuthnRequest and RelayState

Spring Security by default includes `HttpSessionSaml2AuthenticationRequestRepository` to store pending AuthnRequests in the SP session. Whether outbound is Redirect or POST, the SP must still correlate the IdP's response with the initiated request to prevent login injection/replay and retain the right registrationId.

`RelayState` should be an opaque/integrity-protected value per the binding and application; do not automatically redirect to an arbitrary URL simply because a `RelayState` string appears in the request. With HTTP-Redirect Binding, RelayState can participate in the query signature; with POST Binding, ensure proper correlation/session mechanisms. Do not write RelayState or full SAML payloads to public logs.

### 10.4. Cookies/Sessions and the Browser

If the browser returns to the ACS via a **cross-site** POST, `SameSite` cookie policy can affect whether the browser sends the session cookie back to the SP to locate the saved AuthnRequest. Test Secure/HttpOnly cookies, SameSite, HTTPS, Session ID, and session affinity/distributed sessions in a real environment. Lost correlation errors are usually unrelated to whether the AuthnRequest itself used Redirect or POST. Do not disable `InResponseTo` checks to mask cookie/session issues.

## 11. How to Verify the Binding Using Browser DevTools and Safe Logging

### 11.1. Verifying a Redirect Flow

1. Open the DevTools Network tab and enable preserve log if needed, using a test user.
2. Visit `https://sp.example.org/saml2/authenticate/partner` (or a protected page that triggers login).
3. Inspect the SP's response: usually **302/303** with `Location` pointing to the approved **IdP Redirect SSO URL**.
4. Inspect the browser's next request to the IdP: method **GET**, query containing `SAMLRequest` and possibly `RelayState`; when signed per Redirect Binding, `SigAlg`/`Signature` are present.
5. Verify the IdP accepts the request; after login, the browser POSTs `SAMLResponse` to the ACS and the SP establishes a session.
6. If a proxy/WAF returns `414 URI Too Long`, `400`, or truncates the query, check URL limits rather than hastily removing signatures or altering SAML messages arbitrarily.

Record in test reports only: method, approved URL host/path, HTTP status code, presence/absence of `SAMLRequest`/`Signature`, IdP result, and callback. **Do not attach raw SAMLRequest/SAMLResponse, RelayState, cookies, or secret keys** to public tickets.

### 11.2. Verifying a POST Flow

1. Keep the same test IdP registration and switch to POST per the agreed configuration.
2. Browser calls the AuthnRequest initiation endpoint on the SP.
3. The SP's response is usually an **HTML form** (possibly auto-submitted via script) with `method="post"`, `action` matching the **IdP POST SSO URL**, hidden `SAMLRequest`, and possibly `RelayState`.
4. The browser sends **POST** to the IdP; observe the appropriate form content-type and confirm the IdP accepts it.
5. The IdP completes login and sends SAMLResponse to the **SP's ACS**; an authenticated session is created.
6. Test the browser when JavaScript/CSP is restricted, under realistic proxy/WAF policies, since form POSTs can be affected by frontend policies.

If you see the HTML form but **no POST goes out to the IdP**, check CSP, auto-submit, extensions, and script errors before suspecting signing certificates. If the POST reaches the IdP and is rejected, check Binding/Location and the XML signature.

### 11.3. Acceptance Matrix

| Scenario | What Must Be Verified |
| --- | --- |
| IdP publishes only Redirect; SP chooses Redirect | Browser GETs the right IdP URL, AuthnRequest valid, IdP logs in, ACS receives SAMLResponse |
| IdP publishes only POST; SP chooses POST | Browser POSTs form to the right URL, IdP accepts, ACS completes session |
| IdP supports both; SP chooses one | Only the configured binding appears on initiation; SSO still succeeds |
| SP chooses POST but points to Redirect URL | IdP rejects or errors; fix with **matching binding and matching Location**, do not disable verification |
| SP chooses Redirect but IdP endpoint accepts only POST | Login rejected; inspect metadata and update configuration |
| IdP requires signing, SP has no signing credentials | AuthnRequest rejected; configure SP private key/certificate and sign per binding |
| Signed Redirect has query reordered/re-encoded by proxy | Signature check may fail; preserve the signed query verbatim per spec |
| Signed POST has invalid XML signature | IdP rejects; verify canonicalization/signature and certificate, do not switch to unsigned just to pass |
| AuthnRequest has many extensions, URL too long | Consider POST if IdP supports it; check WAF, ingress, and size limits |
| Logged in, but ACS reports missing request correlation | Check session/SameSite/RelayState; do not disable replay protection |
| Metadata changes binding/SSO URL | Must go through approval, registration update, and re-testing; do not rely on old URLs |
| SAMLResponse has wrong issuer/audience/signature | SP must still reject at ACS, **regardless** of outbound binding |

**Separate the three acceptance layers:** (1) SP produces AuthnRequest with the right binding, (2) IdP accepts and returns a response, (3) SP verifies the SAMLResponse and enforces authorization. Succeeding at layer 1 is insufficient to prove SSO or identity protection is working properly.

## 12. Common Errors and How to Resolve Them

| Symptom | Possible Cause | Resolution |
| --- | --- | --- |
| IdP returns `Unsupported binding`, `Invalid request`, or 400 | Unsupported binding, POST sent to Redirect endpoint or vice versa | Compare `SingleSignOnService Binding + Location` in metadata and align both |
| Spring returns 302 to IdP despite wanting POST | Registration still uses Redirect, another repository bean selected, or config not loaded | Check effective binding value, registrationId/repository, observe Network |
| Spring returns POST form but IdP does not receive it | IdP has not enabled POST, wrong URL, CSP/JS blocking auto-submit | Check metadata/IdP product and browser Network |
| IdP reports signed AuthnRequest required | `sign-request` mismatches contract, SP lacks signing credential | Register SP certificate, supply private key, configure signing properly |
| IdP reports signature invalid on Redirect | Query parameter encoding/signature altered by proxy or wrong key/algorithm | Check SigAlg/Signature, certificate/algorithm, preserve URL verbatim |
| IdP reports signature invalid on POST | Wrong XML signature/canonicalization/certificate or IdP expects another binding | Confirm XML signature and Binding; do not use query signature for form POST |
| `414 Request-URI Too Long` | Redirect AuthnRequest too long for browser/proxy/WAF | Trim request or switch to POST if partner supports it; check all hops |
| After login, ACS rejects `InResponseTo` | Lost session/RelayState/correlation, SameSite cookie, or cluster session issue | Restore session/correlation, check cookies and sticky/distributed sessions |
| IdP POST to ACS returns 403 CSRF | Custom ACS URL does not match CSRF exception | Check SAML filter matcher, CSRF exemption **only** for ACS; do not disable CSRF globally |
| IdP requires `ForceAuthn` or `RequestedAuthnContext` | Needs AuthnRequest XML content customization; not a binding error | Use version-appropriate AuthnRequest/OpenSAML customization API, check IdP policy |
| IdP/ACS URL generated with HTTP/internal host | Misconfigured reverse proxy/forwarded headers or `{baseUrl}` | Use canonical HTTPS host and trusted proxy; check metadata and IdP registration |
| Two IdPs, user lands on wrong IdP | Wrong `registrationId` selected or repository has overlapping registrations | Bind each partner to a distinct registration and explicit `/saml2/authenticate/{registrationId}` link |
| Switched to POST, yet SAMLResponse is still POST | Normal: outbound and inbound bindings are independent | Do not alter ACS/response binding unless requested by partner |
| Disabling `sign-request` makes login succeed | May be downgrading IdP/test policy; does not prove security | Restore contract-mandated signing and fix certificate/algorithm |

## 13. Pre-Production Security and Compatibility Checks

- **Select the right partner:** fixed `registrationId`, approved IdP entityID, HTTPS SSO Location, and verified corresponding binding.
- **Sign AuthnRequest when required:** SP private key protected; public certificate registered with IdP; verify proper signature format for the binding, allowed algorithms, and certificate rollover.
- **Verify responses independently:** Spring SP verifies SAMLResponse/Assertion, issuer, audience, recipient, destination, timestamps, replay, and correlation. Never accept an assertion merely because the request used the right binding.
- **Prevent information leakage:** do not put PII/secrets in `RelayState`, limit logging of URLs/queries/bodies containing SAMLRequest, and do not store raw assertions in logs. Use HTTPS on both ends.
- **Infrastructure:** reverse proxy/WAF supports appropriate URL and form body sizes without rewriting signed parameters; CSP permits framework-generated form POSTs; IdP endpoints are reachable at the right host.
- **Sessions:** Secure/HttpOnly/SameSite cookies compatible with SAML POST callbacks; session correlation works across cluster nodes; protection against session fixation and replay.
- **Authorization:** after SAML login, app user permissions are enforced by the SP from verified claims/internal sources. A valid login must not grant access to `/admin/**` by default.
- **Changes:** IdP metadata updates and binding changes must undergo review and testing; maintain rollback plans when partners change endpoints/certificates.
- **Fail closed:** if the IdP does not support the selected binding, reject login and report a diagnosable error; never strip signatures, drop TLS, disable assertion validation, or select targets from browser-supplied URLs.

### Practice Questions

**1. A partner publishes both HTTP-Redirect and HTTP-POST, but our AuthnRequest exceeds the proxy's URL length limit.** How should you handle this?

Verify why the URL is long, check POST support/SSO Location in IdP metadata, and confirm with the partner. If supported, switch to **HTTP-POST for AuthnRequest** at the corresponding endpoint, configure matching signing, and test end-to-end. Do not arbitrarily raise URL limits while bypassing WAF/security policy.

**2. The SP sends AuthnRequest via Redirect; the IdP returns SAMLResponse via POST. Is this a binding misconfiguration?**

No. This **Redirect (request) + POST (response)** pair is very common and valid. Check the two directions independently: outbound to the IdP's SingleSignOnService; inbound to the SP's ACS.

**3. The IdP requires a Signed AuthnRequest and accepts only HTTP-POST. Can we just set `binding: POST` and `sign-request: false`?**

No. You must supply an **SP signing credential**, enable signed requests as required, and let the framework produce an XML signature matching POST binding. Register the SP public certificate with the IdP and test the signature.

**4. Is enabling `saml2Login` and changing `/saml2/authenticate/partner` to accept POST enough?**

No. That endpoint is the **initiation point on the SP**. The actual binding used to send the message to the IdP is determined in `RelyingPartyRegistration`/`assertingparty.singlesignon.binding`; the target `Location` must also match.

**5. Switch to POST to “hide SAMLRequest from the browser.” Is that statement accurate?**

No. With HTTP-POST Binding, the browser still receives the HTML form and submits the Base64-encoded SAMLRequest. POST helps avoid certain long-URL issues and query-log exposure, but does not replace HTTPS, digital signatures, PII controls, or validation.

## 14. Lesson Completion Checklist

- [ ] Have verified IdP metadata explicitly showing `entityID` and all `SingleSignOnService Binding + Location` entries.
- [ ] Know whether the partner accepts **HTTP-Redirect**, **HTTP-POST**, or both; confirmed AuthnRequest signing requirements.
- [ ] Selected the binding based on partner capability and infrastructure size/constraints; not based on the SAMLResponse binding.
- [ ] Configured `singlesignon.binding`, `url`, `sign-request`, and credentials accurately per registration.
- [ ] Verified SP entityID, HTTPS ACS, IdP verification certificate, and SP signing certificate/private key (when needed).
- [ ] Browser Network proves the request is actually a GET Redirect or POST form to the corresponding IdP endpoint.
- [ ] IdP accepts the request and sends SAMLResponse to the ACS; Spring SP verifies it and creates a session.
- [ ] Requests with wrong binding, bad signature, wrong issuer/recipient, or bad correlation **do not** create a login session.
- [ ] No raw SAMLRequest, SAMLResponse, RelayState, cookies, or private keys recorded in tickets/logs.
- [ ] Tested with ingress/proxy/WAF, CSP, TLS, cluster sessions, and IdP metadata change scenarios.

**Key takeaway:** choosing HTTP-Redirect or HTTP-POST is a decision about **how the AuthnRequest is transported from the SP to the IdP's SingleSignOnService**. Spring Security supports both; first verify which binding and URL the IdP publishes, then configure binding + Location + signing policy **consistently**, and finally test the entire flow. This change never removes the obligation to verify the SAMLResponse and enforce application authorization.

## 15. Reference Documentation

- [Spring Security — Producing AuthnRequests](https://docs.spring.io/spring-security/reference/servlet/saml2/login/authentication-requests.html) — HTTP-Redirect default, selecting `Saml2MessageBinding.POST`, and signing credentials.
- [Spring Security — SAML 2.0 Login Overview](https://docs.spring.io/spring-security/reference/servlet/saml2/login/overview.html) — RP/AP, `RelyingPartyRegistration`, ACS, and login flow.
- [Spring Boot — Saml2RelyingPartyProperties.AssertingParty.Singlesignon](https://docs.spring.io/spring-boot/api/java/org/springframework/boot/security/saml2/autoconfigure/Saml2RelyingPartyProperties.AssertingParty.Singlesignon.html) — URL, binding, and sign-request properties in versions with the corresponding API.
- [Spring Security API — Saml2MessageBinding](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/saml2/provider/service/registration/Saml2MessageBinding.html) — Redirect/POST bindings.
- [OASIS — SAML V2.0 Technical Overview](https://docs.oasis-open.org/security/saml/Post2.0/sstc-saml-tech-overview-2.0.html) — Redirect/POST use cases and independence between request and response.
- [OASIS — SAML V2.0 Bindings](https://docs.oasis-open.org/security/saml/v2.0/saml-bindings-2.0-os.pdf) — encoding/signing of HTTP-Redirect and HTTP-POST.
- [Microsoft Learn — SAML protocol for SSO](https://learn.microsoft.com/azure/active-directory/develop/single-sign-on-saml-protocol) — example partner expecting Redirect AuthnRequest and POST SAMLResponse.
