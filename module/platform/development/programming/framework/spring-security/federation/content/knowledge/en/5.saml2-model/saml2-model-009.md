# HTTP-Redirect, HTTP-POST, and Binding Limitations Supported in SAML 2.0

## 1. Purpose and Context

A **binding** in SAML 2.0 is the rule for packaging and transporting a SAML protocol message over a specific communication medium. For Web Browser Single Sign-On (SSO), the two most common bindings are **HTTP-Redirect** and **HTTP-POST**. Both belong to SAML 2.0, yet they differ in HTTP method, where payload data sits, encoding, signature style, and limits encountered across browsers/proxies.

This lesson sits in the context of **Spring Security - federation**, the **SAML 2.0** model, focusing on the **Service Provider (SP), also called Relying Party (RP)** role of `spring-security-saml2-service-provider` on the Servlet stack. The IdP (Identity Provider, also called Asserting Party) is responsible for authenticating the user and issuing responses. The browser relays messages on the front-channel, while Spring Security verifies the response and establishes `Authentication`.

After this lesson, the learner can:

- Distinguish **SAML protocol**, **SAML profile**, and **SAML binding**; understand how one login flow can combine two different bindings.
- Explain how HTTP-Redirect compresses, encodes, and places `SAMLRequest` in the query string; and how HTTP-POST Base64-encodes the message into a form sent via request body.
- Read `AuthnRequest`, `SAMLResponse`, `RelayState`, `SigAlg`, and `Signature` alongside SSO/ACS URLs accurately.
- Identify clearly which bindings Spring Security SP supports when **sending AuthnRequest**, when **receiving Response**, and which bindings are unavailable out of the box.
- Diagnose errors caused by mismatched bindings, metadata, signatures, cookies, endpoints, URL limits, or IdP config.
- Inspect SSO hop by hop without confusing browser redirects with back-channel calls or disabling security checks.

Hosts ending in `.example.org` are solely examples; no live IdP exists for login.

## 2. How Does a Binding Differ from a Profile and a Protocol?

| Concept | Question it answers | Examples |
| --- | --- | --- |
| **Protocol** | What do the messages say and how do they relate? | `AuthnRequest`, `Response`, `LogoutRequest`, `Assertion`, `InResponseTo` |
| **Profile** | In what sequence are protocols/bindings used for a use case? | SAML 2.0 **Web Browser SSO Profile** |
| **Binding** | How does a SAML message travel over HTTP or another medium? | HTTP-Redirect, HTTP-POST, HTTP-Artifact, SOAP, PAOS |

Do not call every HTTP 302 a “SAML HTTP-Redirect binding.” An application may return a 302 from a protected page to Spring's `/saml2/authenticate/corp` endpoint; that is an ordinary application redirect. **SAML HTTP-Redirect binding** is the hop where the URL to the IdP carries the encoded protocol message in `SAMLRequest`.

A typical **SP-initiated Web SSO** flow:

~~~mermaid
sequenceDiagram
    participant U as Browser
    participant SP as Spring Security SP
    participant IDP as SAML IdP
    U->>SP: GET /private
    SP-->>U: 302 to /saml2/authenticate/corp
    U->>SP: GET /saml2/authenticate/corp
    SP-->>U: 302 Location: IdP?SAMLRequest=... (HTTP-Redirect binding)
    U->>IDP: GET /sso?SAMLRequest=...&RelayState=...
    IDP-->>U: Login/MFA or reuse IdP session
    IDP-->>U: HTML form with SAMLResponse (HTTP-POST binding)
    U->>SP: POST /login/saml2/sso/corp
    SP->>SP: Verify SAML and request correlation
    SP-->>U: Set-Cookie SP session; redirect to resource
    U->>SP: GET /private + SP cookie
~~~

In this example, **outbound is HTTP-Redirect and inbound is HTTP-POST**. Having different bindings in the two directions is normal, not a misconfiguration. Another IdP may require **POST AuthnRequest** instead of Redirect, while `SAMLResponse` still normally POSTs back to the ACS.

## 3. HTTP-Redirect Binding: Message Inside the URL

Standard binding identifier:

`urn:oasis:names:tc:SAML:2.0:bindings:HTTP-Redirect`

It is commonly used for the **SP sending `AuthnRequest` to the IdP** via a top-level GET. Packaging steps per SAML 2.0 HTTP-Redirect binding:

1. Construct the XML SAML message (e.g. `<samlp:AuthnRequest>`) and determine the SSO destination.
2. Serialize the message into XML bytes using the appropriate encoding.
3. **Raw DEFLATE** the XML bytes, normally without zlib/gzip wrappers. Note `java.util.zip.Deflater(..., true)`: the `true` flag selects raw DEFLATE.
4. **Base64-encode** the compressed bytes.
5. **URL-percent-encode** the Base64 string so it fits safely in a query parameter value.
6. Build the URL to the IdP endpoint with the **`SAMLRequest`** parameter (or `SAMLResponse` for other message types in the binding definition, though Spring Security's login response handling **does not support** Redirect).
7. If present, attach **`RelayState`** as a separate query parameter. When signing the Redirect binding, add **`SigAlg`** and **`Signature`** per the binding's query-string signing rules.
8. The SP returns an HTTP response with `Location`; the **browser** follows the redirect and issues a new GET to the IdP.

Abbreviated HTTP example:

~~~http
GET /saml2/authenticate/corp HTTP/1.1
Host: app.example.org

HTTP/1.1 302 Found
Location: https://idp.example.org/sso?SAMLRequest=fZH...%3D&RelayState=r-123&SigAlg=...&Signature=...
~~~

The browser continues:

~~~http
GET /sso?SAMLRequest=fZH...%3D&RelayState=r-123&SigAlg=...&Signature=... HTTP/1.1
Host: idp.example.org
~~~

Values `fZH...`, `r-123`, `...` only illustrate shape; they are **not valid SAML messages or signatures**.

### Where Does the HTTP-Redirect Signature Live?

In the standard Redirect binding signing method, the sender signs the **URL-encoded query string**, in the parameter order and subset defined by the spec:

~~~text
SAMLRequest=<url-encoded-value>&RelayState=<url-encoded-value>&SigAlg=<url-encoded-algorithm>
~~~

If `RelayState` is absent, omit `&RelayState=...` completely when constructing the signed string. For `SAMLResponse` messages, the parameter name in the binding formula changes accordingly, yet **do not interpret that as Spring Security Web Browser SSO allowing Redirect login responses**. The `Signature` value is Base64 of the digital signature, then URL-encoded; `SigAlg` specifies the signing algorithm. Never reorder signed parameters, never sign a re-pretty-printed XML copy, and never compare signatures against un-percent-encoded strings.

**Subtle point:** the query-level binding signature differs from an **XML Digital Signature** (`<ds:Signature>`) inside the XML. Spring Security documents a Redirect variant with XML signatures within its APIs, yet you should not assume every IdP supports that variant. In real integrations, rely on metadata and IdP/SP guidance to pick the right signing mode.

### Operational Limits of Redirect

- **URLs have practical limits** across browsers, proxies, WAFs, gateways, logging infrastructure, and IdPs; no single “2,048-character” threshold applies to every infrastructure. Overlong requests can hit 414 URI Too Long, 400, or truncation/blocking.
- URLs routinely appear in **browser history, access logs, tracing, or monitoring tools**; never place passwords, private keys, or long-lived tokens in query parameters.
- **DEFLATE shrinks size**—it does not encrypt or protect secrecy; Base64 is mere encoding, HTTPS protects transport only, and server-side signature/partner verification is still mandatory.
- Differences in DEFLATE wrappers, escaping `+`/`%2B`, `%2F`, `%3D`, signature algorithms, or canonicalization can cause IdP rejection.
- If the XML `AuthnRequest` carries many extensions, complex signing/identifier demands, or policy grows the URL too long, the IdP may prefer **HTTP-POST AuthnRequest**.
- HTTP-Redirect is typically suited for small **requests**, not for transferring large assertions/responses as a regular login URL.

Other query parameters already present on the SSO URL must be handled carefully; never concatenate strings naively or sign the wrong query scope.

## 4. HTTP-POST Binding: Message Inside an HTML Form

Standard binding identifier:

`urn:oasis:names:tc:SAML:2.0:bindings:HTTP-POST`

The SAML message is serialized to XML, **Base64-encoded directly** (without default DEFLATE as in Redirect), and placed in a hidden input of an HTML form. The browser submits the form to the `action` target via HTTP POST, normally `Content-Type: application/x-www-form-urlencoded`. The browser may auto-submit via script or the user clicks a fallback button.

Example response from IdP to SP:

~~~html
<!doctype html>
<html lang="en">
  <body>
    <form id="saml-post" method="post"
          action="https://app.example.org/login/saml2/sso/corp">
      <input type="hidden" name="SAMLResponse"
             value="BASE64_ENCODED_SAML_RESPONSE">
      <input type="hidden" name="RelayState" value="request-correlation">
      <noscript><button type="submit">Continue</button></noscript>
    </form>
    <script>
      document.getElementById("saml-post").submit();
    </script>
  </body>
</html>
~~~

In a real system, `SAMLResponse` may contain sensitive assertions/user attributes; the example above **contains no real message**. `RelayState` may be present or absent and is usually echoed from the initial transaction.

After submission, the HTTP request to the ACS looks like:

~~~http
POST /login/saml2/sso/corp HTTP/1.1
Host: app.example.org
Content-Type: application/x-www-form-urlencoded

SAMLResponse=PHNhbWxwOlJlc3BvbnNlLi4u&RelayState=request-correlation
~~~

In POST binding:
- The primary payload sits in the **body**; the browser issues the actual request rather than the IdP backend calling the ACS directly in standard front-channel flows.
- **XML Signature**, when present, usually resides inside the XML SAML Response or Assertion (`<ds:Signature>`), unlike Redirect's query signature. The SP must verify the right signed scope and protocol conditions.
- **Base64 is not security encryption**. The body can be captured by DevTools, TLS-terminating proxies, logging middleware, HAR files, or browser extensions; never dump the full body into production logs.
- Staying out of the URL reduces overlong-URL risks and URL-log leakage, **but does not make POST inherently trusted or encrypted**.
- JavaScript `fetch()` CORS differs from **top-level HTML form navigation**. Adding CORS headers usually does not fix SAML ACS POST or `SameSite` cookie failures.

HTTP-POST can also be used by the **SP to send `AuthnRequest` to the IdP** if IdP metadata, RP config, and deployment support it. In that case the form field is `SAMLRequest` and the form `action` is the IdP's SSO endpoint; the response back to the SP still uses `SAMLResponse`.

## 5. Choosing Bindings by Direction, Message, and Spring Security Product

This is the most important distinction to get right. **SAML 2.0 is a broad specification; modern Spring Security SAML 2.0 Service Provider implements only a specific scope.**

| Flow / message | Binding | Spring Security SAML 2.0 SP (Servlet) | Notes |
| --- | --- | --- | --- |
| SP → IdP: `AuthnRequest` | **HTTP-Redirect** | **Supported; common/default** | Browser GET to IdP with `SAMLRequest` |
| SP → IdP: `AuthnRequest` | **HTTP-POST** | **Supported when configured** | Browser POSTs HTML form to IdP SSO endpoint; IdP must publish/support POST |
| IdP → SP: SAML **Response** for Web SSO | **HTTP-POST** | **Supported; default login flow** | Browser POSTs `SAMLResponse` to ACS |
| IdP → SP: SAML **Response** via GET Redirect | **HTTP-Redirect** | **Not supported in standard Spring Security Web SSO login** | Do not switch ACS to GET to “catch” responses |
| Web SSO using HTTP-Artifact and ArtifactResolve | **HTTP-Artifact/SOAP** | **Not available in the modern module per migration docs** | Requires dedicated back-channel artifact resolution architecture or another product |
| SOAP / PAOS / ECP / other profiles | Protocol-dependent | **Not a default feature of `saml2Login()`** | Check specific feature/version docs; do not infer from OpenSAML being on classpath |
| SAML Single Logout | Redirect and/or POST per config | SLO is supported in matching Spring Security versions | **Distinct from Web SSO login**; evaluate logout request/response separately, never infer login bindings from logout |

**Version note:** examples and scope here apply to modern Spring Security 6.x/7.x Servlet; check documentation matching your active version. Spring Security's migration guide explicitly states that **HTTP-Redirect binding for SAML 2.0 Response and HTTP-Artifact binding are features not migrated to the new module**. Future releases could evolve so check release notes, but never assume that seeing `Saml2MessageBinding.REDIRECT` means the SP filter accepts all Responses over GET.

**Difference from the legacy product:** the older `Spring Security SAML Extension 1.x` covered a wider surface (HTTP-POST, Redirect, SOAP, PAOS, Artifact…). It is a separate integration, not evidence that modern `spring-security-saml2-service-provider` automatically supports the same bindings. Do not mix legacy filters, endpoints, and metadata into the new chain.

### Four Mandatory Questions Before Choosing a Binding

1. Are we transporting **AuthnRequest, Response, LogoutRequest, or an artifact**?
2. Is the message going **SP → IdP** or **IdP → SP**?
3. Is this the **Web Browser SSO profile** or another profile?
4. Do **both sides on their exact versions/configurations** support the binding and matching endpoint URL in metadata?

Answering “HTTP-POST is supported” is insufficient without specifying **POST what, and to where**.

## 6. Metadata Determines Usable Endpoints and Bindings

Entities in a federation exchange XML metadata containing service elements with `Binding` and `Location`.

**IdP metadata** may advertise multiple `SingleSignOnService` entries:

~~~xml
<md:IDPSSODescriptor
    xmlns:md="urn:oasis:names:tc:SAML:2.0:metadata"
    protocolSupportEnumeration="urn:oasis:names:tc:SAML:2.0:protocol">
  <md:SingleSignOnService
      Binding="urn:oasis:names:tc:SAML:2.0:bindings:HTTP-Redirect"
      Location="https://idp.example.org/sso/redirect"/>
  <md:SingleSignOnService
      Binding="urn:oasis:names:tc:SAML:2.0:bindings:HTTP-POST"
      Location="https://idp.example.org/sso/post"/>
</md:IDPSSODescriptor>
~~~

This is an **illustrative excerpt**; complete metadata needs `EntityDescriptor`, entity ID, key descriptors/signatures, and required elements. POST/Redirect URLs are examples only; many IdPs reuse the same URL for multiple bindings.

**SP metadata** advertises the ACS for responses:

~~~xml
<md:SPSSODescriptor
    xmlns:md="urn:oasis:names:tc:SAML:2.0:metadata"
    protocolSupportEnumeration="urn:oasis:names:tc:SAML:2.0:protocol">
  <md:AssertionConsumerService
      Binding="urn:oasis:names:tc:SAML:2.0:bindings:HTTP-POST"
      Location="https://app.example.org/login/saml2/sso/corp"
      index="0" isDefault="true"/>
</md:SPSSODescriptor>
~~~

Read the attributes carefully:

- `SingleSignOnService@Binding` tells **which binding the IdP accepts `AuthnRequest` over** at which `Location`. This is not the ACS.
- `AssertionConsumerService@Binding` tells **which binding the SP accepts `Response` over** at which ACS `Location`.
- `AuthnRequest@ProtocolBinding` can indicate the binding the SP desires for the Response per profile/config; do not confuse it with the binding used to send **`AuthnRequest` itself**.
- `AuthnRequest@Destination` should point to the IdP SSO endpoint; `Response@Destination` and `SubjectConfirmationData@Recipient` must correspond to the SP ACS per verified conditions.
- `entityID` logically identifies the entity and is not necessarily an endpoint URL; never swap `entityID` for a redirect URI casually.
- `registrationId=corp` is Spring's local identifier for looking up `RelyingPartyRegistration`; this value is not automatically equal to the SAML entity ID.

IdP metadata listing both Redirect and POST **does not mean** Spring will dynamically accept POST or GET responses regardless of SP metadata. Verify the agreed **outbound and inbound** paths on both sides.

## 7. Where Does Spring Security Implement These Bindings?

In a Spring Boot Servlet application with `spring-security-saml2-service-provider`, `RelyingPartyRegistrationRepository`, and `saml2Login()`:

- `Saml2WebSsoAuthenticationRequestFilter` handles login initiation requests at `/saml2/authenticate/{registrationId}`, creates `AuthnRequest`, saves correlation state, and dispatches to the IdP via the matching binding.
- `Saml2WebSsoAuthenticationFilter` handles POSTs to the default ACS `/login/saml2/sso/{registrationId}`, extracts `SAMLResponse`, and verifies it using the registration.
- Spring Security's OpenSAML provider classes perform parsing, condition validation, and authentication building. Class/provider names vary by version.
- `RelyingPartyRegistration` holds SP-side and IdP-side metadata, including IdP SSO endpoint/binding, ACS location, and signing/verification credentials.

A typical Servlet configuration snippet in a Spring Boot project with dependencies and registrations:

~~~java
package com.example.federation;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class SamlSecurityConfig {
    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http) throws Exception {
        return http
                .authorizeHttpRequests(auth -> auth
                        .requestMatchers("/public/**").permitAll()
                        .anyRequest().authenticated())
                .saml2Login(Customizer.withDefaults())
                .build();
    }
}
~~~

This Java snippet **is a Spring configuration class**, not a standalone program runnable via `javac SamlSecurityConfig.java` outside a project. It uses standard Spring Security 6.x/7.x APIs; the project requires the Spring Boot-mandated JDK, SAML SP dependency, valid metadata/registration, and main application. There is no fixed stdout; observe HTTP redirects and sessions at runtime.

### Loading Bindings from IdP Metadata

In metadata-driven deployments:

~~~yaml
spring:
  security:
    saml2:
      relyingparty:
        registration:
          corp:
            assertingparty:
              metadata-uri: "classpath:saml/corp-idp.xml"
~~~

This is a **complete configuration option in terms of metadata path**, yet requires a real `src/main/resources/saml/corp-idp.xml` supplied by the IdP and SP registration at the IdP. When parsing metadata, Spring Security selects SSO service/binding details as supported by its API and version; never assume that just because the XML lists POST, runtime automatically selects POST if other configuration overrides it.

### Requesting POST AuthnRequest

Modern Spring Security provides the `AssertingPartyMetadata.Builder` API to select POST on `RelyingPartyRegistration`. **Illustrative Java snippet inside a Spring project (requires real metadata and version-matching API)**:

~~~java
package com.example.federation;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.saml2.provider.service.registration.InMemoryRelyingPartyRegistrationRepository;
import org.springframework.security.saml2.provider.service.registration.RelyingPartyRegistration;
import org.springframework.security.saml2.provider.service.registration.RelyingPartyRegistrationRepository;
import org.springframework.security.saml2.provider.service.registration.RelyingPartyRegistrations;
import org.springframework.security.saml2.provider.service.registration.Saml2MessageBinding;

@Configuration
public class SamlPostRequestConfiguration {

    @Bean
    RelyingPartyRegistrationRepository relyingPartyRegistrationRepository() {
        RelyingPartyRegistration registration = RelyingPartyRegistrations
                .fromMetadataLocation("classpath:saml/corp-idp.xml")
                .registrationId("corp")
                .assertingPartyMetadata(party ->
                        party.singleSignOnServiceBinding(Saml2MessageBinding.POST))
                .build();

        return new InMemoryRelyingPartyRegistrationRepository(registration);
    }
}
~~~

- `singleSignOnServiceBinding(Saml2MessageBinding.POST)` changes the **binding used to send `AuthnRequest` to the IdP**, not the binding receiving `SAMLResponse` at the ACS.
- IdP metadata must contain an SSO endpoint supporting POST; if it only advertises Redirect, forcing POST does not guarantee interoperability.
- When supplying your own `RelyingPartyRegistrationRepository`, understand Boot's auto-configuration rules; avoid creating two distinct registrations with the same ID.
- Check signature requirements: Redirect binding typically signs the query string; POST binding typically signs the XML message. If the IdP mandates signed `AuthnRequest`s, the SP must hold a **signing private key + certificate**, and the recipient must have the public info to verify.
- Builder APIs can change between Spring Security 6.x and 7.x; follow your exact version's docs before copying.

**Do not write your own controller receiving `SAMLResponse` via GET** or tweak Spring filter matchers to bypass limits. Doing so creates a non-standard processing path lacking full integrated validation.

## 8. Self-Running Java 17 Example: Encode/Decode Mechanics for Redirect

To see that “DEFLATE → Base64 → URL-encode” are genuinely three distinct steps, the following program uses only the **Java Standard Library**. It performs a round-trip on a minimal XML string to illustrate **transport mechanics**, does not produce a valid SAML `AuthnRequest`, does not sign XML, and is **not how to implement production SAML yourself**.

File `SamlRedirectCodecDemo.java`:

~~~java
import java.io.ByteArrayInputStream;
import java.io.ByteArrayOutputStream;
import java.net.URLDecoder;
import java.net.URLEncoder;
import java.nio.charset.StandardCharsets;
import java.util.Base64;
import java.util.zip.Deflater;
import java.util.zip.DeflaterOutputStream;
import java.util.zip.Inflater;
import java.util.zip.InflaterInputStream;

public class SamlRedirectCodecDemo {
    public static void main(String[] args) throws Exception {
        String xml = "<AuthnRequest ID=\"demo-1\"/>";

        ByteArrayOutputStream compressedOut = new ByteArrayOutputStream();
        try (DeflaterOutputStream stream = new DeflaterOutputStream(
                compressedOut, new Deflater(Deflater.DEFAULT_COMPRESSION, true))) {
            stream.write(xml.getBytes(StandardCharsets.UTF_8));
        }

        String base64 = Base64.getEncoder().encodeToString(compressedOut.toByteArray());
        String queryValue = URLEncoder.encode(base64, StandardCharsets.UTF_8);

        String decodedBase64 = URLDecoder.decode(queryValue, StandardCharsets.UTF_8);
        byte[] compressed = Base64.getDecoder().decode(decodedBase64);

        String restored;
        try (InflaterInputStream stream = new InflaterInputStream(
                new ByteArrayInputStream(compressed), new Inflater(true))) {
            restored = new String(stream.readAllBytes(), StandardCharsets.UTF_8);
        }

        System.out.println("Round-trip matches: " + xml.equals(restored));
        System.out.println("Query value exists: " + !queryValue.isBlank());
    }
}
~~~

Compile and run with Java 17+ in the directory containing the file:

~~~bash
javac SamlRedirectCodecDemo.java
java SamlRedirectCodecDemo
~~~

Exact stdout:

~~~text
Round-trip matches: true
Query value exists: true
~~~

Meaning: `Deflater(..., true)` uses raw DEFLATE; `Base64` produces a text representation of bytes; `URLEncoder` protects special characters in query values; decoding must reverse the order. **Never use this demo instead of OpenSAML**, as it lacks SAML protocol namespaces, signatures, metadata, issuer, destination, replay protection, and IdP policy.

If illustrating POST, simply Base64-encode the XML and place it in a form field; **do not apply raw DEFLATE** as in Redirect.

## 9. RelayState: Value Carried Alongside the Message, Not a Signature

`RelayState` allows passing transactional context state across SP–IdP–SP. For instance, the SP may hold a short correlation token linking `AuthnRequest` to the URL the user wanted to visit after login.

- With **Redirect binding**, `RelayState` is a separate query parameter and, if the message uses a binding signature, is normally part of the signed string.
- With **POST binding**, `RelayState` is a hidden input alongside `SAMLRequest` or `SAMLResponse`.
- `RelayState` can hold an **opaque handle** to server-side data; avoid placing sensitive data or full authorization info here.
- The SAML binding spec places length constraints on `RelayState` (commonly cited as at most 80 bytes) and recommends integrity protection; check interoperability and actual implementation behavior.
- **`RelayState` is not authentication proof.** A POST form with a plausible `RelayState` must still pass SAML signature verification, assertion checks, and `InResponseTo` correlation if SP-initiated.
- When using `RelayState` for post-login navigation, never let arbitrary values cause an **open redirect** to an untrusted domain.

In Spring Security, `Saml2AuthenticationRequestRepository` typically stores `AuthnRequest` in the HTTP session. The browser brings the session cookie and message back to the ACS so the SP can match them. If implementing a custom distributed cache or cookie strategy, ensure transaction isolation and protection against login CSRF/session fixation.

## 10. Signatures, Certificates, and Unsafe Assumptions

Digital signatures do not “come for free” from HTTPS or Base64. In SAML, distinguish:

| Location | Example | Who verifies |
| --- | --- | --- |
| **Redirect binding query signature** | `SAMLRequest=...&SigAlg=...&Signature=...` | IdP when receiving a signed `AuthnRequest` over Redirect |
| **XML Digital Signature inside message** | `<ds:Signature>` inside `AuthnRequest`, `Response`, or `Assertion` | Recipient, per configuration and SAML profile |
| **TLS certificate of HTTPS endpoint** | Web server cert of `idp.example.org` or SP | Connecting TLS client/browser/server |
| **SAML signing certificate** | Public X.509 in metadata or trust registration | Recipient verifying XML/binding signatures |

A valid TLS certificate **does not prove the SAML Response issuer**; conversely, a SAML signing certificate does not replace TLS for browsers. Beyond signatures, the SP must verify audience, issuer, `Destination`/`Recipient`, validity window, `SubjectConfirmation`, `InResponseTo` correlation, and anti-replay per flow.

**An unsigned POST is not “safe just because it's in the body.”** **A Redirect with a query signature does not encrypt the message.** Trust resides in SAML policies and server-side validation, not the HTTP method.

## 11. Cookies, SameSite, and the POST to ACS

In a typical SP-initiated flow:
- The browser visits the SP; the SP saves `AuthnRequest` in the session.
- The browser is redirected to the IdP (a different site).
- The IdP returns a form and the browser POSTs to the SP's ACS.

This is a **cross-site POST** request in many deployments. An SP session cookie with `SameSite=Lax` is normally **not** sent on standard cross-site POSTs. Spring Security may fail to find the saved request to match `InResponseTo`; login gets rejected even though the IdP authenticated the user.

Do not solve this by removing `InResponseTo` checks. Choose the right cookie/session configuration for your architecture, such as evaluating `SameSite=None; Secure` for relevant cookies or an alternative request repository strategy with anti-forgery and session-fixation protections. Inside embedded iframes, third-party cookie restrictions affect flows even more than top-level navigation.

**CORS** governs JavaScript reading cross-origin responses via fetch/XHR, not SAML form submission verification. A 403/404 error on ACS POST cannot be blamed on CORS; inspect the filter chain, route/method, appropriate CSRF exceptions, and session correlation. Never disable CSRF across the entire application just to “allow SAML.”

## 12. Why Doesn't Spring Security Receive Responses via Redirect?

This is a **product/Web SSO flow scope limit**, not that the SAML spec lacks a Redirect binding. In Spring Security's migration guide, **HTTP-Redirect for SAML 2.0 Response** is listed as unsupported. Responses carrying assertions are typically large and ill-suited for URLs; signing and Web Browser SSO profile rules also differ from small `AuthnRequest`s.

Example misconfigured IdP returning:

~~~http
HTTP/1.1 302 Found
Location: https://app.example.org/login/saml2/sso/corp?SAMLResponse=...
~~~

Standard Spring Security login flow **expects a POST form** carrying `SAMLResponse`. Although some converter/version APIs have options touching GET, that is not a promise of standard Web Browser SSO Response HTTP-Redirect support; do not use it as a standard workaround for a misconfigured IdP.

**Fix:** change the IdP's **Response Binding** to **HTTP-POST**, ensure SP metadata advertises the HTTP-POST ACS at the exact URL, and test end to end. If an IdP supports only a profile/binding outside Spring Security's scope, reconsider integration requirements/SP solutions rather than turning GET queries into `Authentication` yourself.

## 13. Artifact, SOAP, PAOS: Understanding Limits and Options

SAML 2.0 defines more bindings than the two covered in detail here:

| Binding | Idea | Relation to modern Spring Security Web SSO |
| --- | --- | --- |
| **HTTP-Artifact** | Browser carries a short reference artifact; SP normally resolves the actual message from IdP via back-channel | Not supported out of the box in `spring-security-saml2-service-provider` per migration docs |
| **SOAP** | Server–server transport for protocols like artifact resolution | Having OpenSAML on the classpath does not mean SOAP SP Web SSO is included |
| **PAOS (Reverse SOAP)** | Enhanced Client or Proxy (ECP) scenarios | Not standard browser SSO enabled by `saml2Login()` |
| **HTTP-POST** | Form POST carrying Base64 XML | Supported SAML Response reception flow in Spring Security |
| **HTTP-Redirect** | GET query carrying DEFLATE/Base64 XML | Primary `AuthnRequest` outbound flow in SP login |

Before signing a federation agreement, ask the IdP to specify its **SSO request binding** and **response binding** clearly. If Artifact or PAOS is mandatory, address architecture/feature support upfront rather than discovering during integration testing that the ACS endpoint expects a different binding.

## 14. Diagnosing with DevTools and Server Logs

Use a browser with Developer Tools → **Network** → **Preserve log** and an authorized test IdP. Observe the sequence of redirects and POSTs; there is no need to export raw assertions or cookies.

| Symptom | Diagnostic clue | Check and fix |
| --- | --- | --- |
| GET SSO returns 414/400 | Redirect URL/`SAMLRequest` too long or blocked | Check byte/size limits at proxy/WAF; consider POST `AuthnRequest` if IdP supports it |
| GET SSO reports “binding unsupported” | IdP only exposes a POST SSO endpoint or is misconfigured | Read `SingleSignOnService@Binding/Location`, pick POST at the exact address |
| IdP reports “signature invalid” on Redirect `AuthnRequest` | Algorithm mismatch, wrong signing key, or query encoded/signed wrongly | Check `SigAlg`, signed string, cert, algorithm, and metadata |
| IdP reports missing signed request on POST | POST `AuthnRequest` lacks XML signature required by policy | Configure SP signing credentials and match IdP policy |
| After login, browser GETs ACS with `SAMLResponse` | IdP configured for Response Redirect | Switch response binding to POST; fix metadata/ACS |
| Browser POSTs ACS but gets 404 | Wrong endpoint/`registrationId` or custom filter matcher | Check public ACS URL, POST method, and filter chain |
| Browser POSTs ACS but gets 403 | CSRF/filter chain or registration/validation rejection | Inspect sanitized server logs; avoid disabling CSRF globally |
| Response rejected with “InResponseTo” | Cannot locate `AuthnRequest`/SP session | Check `SameSite` cookies, session persistence, and repository |
| Response rejected for issuer/audience/recipient | Entity ID or ACS/metadata mismatch | Compare IdP & SP metadata; fix public URL/reverse proxy |
| SAML Response signature error | Stale/wrong IdP cert, altered response, or mismatched profile | Verify metadata, cert rollover, and XML signature |
| IdP POSTs HTML form yet browser fails to submit | JavaScript blocked or bad form action; CSP may interfere | Inspect HTML, submit manually if supported, check console/network |
| User logs into IdP yet returns to app still unauthenticated | `SAMLResponse` not processed or SP session not created | Check ACS status/`Set-Cookie` and `SecurityContext`; do not confuse IdP session with SP session |

### Reconstructing the Transaction Without Leaking Data

1. Record method, status, origin, and path of every HTTP hop; distinguish application redirects from SAML redirects carrying `SAMLRequest`.
2. Check whether the request to the IdP carries `SAMLRequest` **in the GET URL** or **in the POST form body**.
3. Check that the browser returns to the ACS via **POST** with form field **`SAMLResponse`**.
4. Compare actual URLs against metadata: IdP `SingleSignOnService`, SP `AssertionConsumerService`, HTTPS scheme, port, context path, `registrationId`.
5. Check whether the SP session and cookie accompany the POST. If not, investigate `SameSite`/`Secure`/Domain and proxies.
6. Check the ACS response, post-login SP session, and server-side validation logs.
7. Redact `SAMLRequest`, `SAMLResponse`, cookies, `RelayState`, signatures, and assertion attributes before sharing HARs/logs.

The browser cannot verify XML Signatures itself; seeing POST 200/302 in the Network tab is not enough to conclude the user is authenticated. You must observe the SP creating a valid session/`Authentication` and granting access to the protected resource.

## 15. Common Misconceptions

1. **“Redirect and POST are two different SSO protocols.”** False: they are two message transport bindings of the **same SAML 2.0 protocol**.
2. **“HTTP-POST requires everything to be POST.”** False: a flow can use Redirect when sending `AuthnRequest` and POST when receiving `Response`.
3. **“HTTP-Redirect means the SP backend calls the IdP directly.”** False: the server returns `Location`; the browser issues the next request.
4. **“The POST body is encrypted so no signature is needed.”** False: Base64 does not encrypt, and HTTPS does not replace SAML signature validation.
5. **“Spring Security has a REDIRECT enum so it can receive GET Responses.”** False for standard Spring SAML SP Web SSO; binding support depends on **message/direction/profile**.
6. **“Having the OpenSAML dependency means Artifact/SOAP/PAOS are ready to use.”** False: a low-level XML library does not mean integrated endpoints and state machines exist.
7. **“A valid RelayState means the assertion is valid.”** False: `RelayState` is for correlation; the Response itself and all conditions must be verified.
8. **“HTTP-Redirect only needs Base64.”** False: Redirect applies raw DEFLATE before Base64 plus URL percent-encoding, unlike POST.
9. **“URLs longer than 2,048 characters always fail.”** False: limits vary by browser/proxy/IdP and configuration; test the full path.
10. **“CORS causes every cross-domain login error.”** False: form navigation differs from fetch/XHR; usually check ACS, cookies, CSRF, signatures, and redirect URIs.
11. **“Successful IdP login automatically creates an SP session.”** False: the SP creates `Authentication` only after receiving and verifying a valid `SAMLResponse`.
12. **“Choosing the binding at the SP alone is enough.”** False: IdP and SP metadata/URLs/policies **must match simultaneously**.

## 16. Exercises with Answers

**Exercise 1 — Identifying bindings.** You observe the browser GET `https://idp.example.org/sso?SAMLRequest=...&RelayState=...`, followed by POST `https://app.example.org/login/saml2/sso/corp` with `SAMLResponse`. Which bindings are used?

**Answer:** `AuthnRequest` uses **HTTP-Redirect**, and `SAMLResponse` uses **HTTP-POST**. They are two steps of a single SAML 2.0 Web Browser SSO flow.

**Exercise 2 — Misconfigured Response.** The IdP only offers “SAML Response over Redirect/GET.” Should you build a GET controller at `/login/saml2/sso/corp` and trust the decoded XML?

**Answer:** no. Spring Security SAML SP Web SSO does not provide standard Response Redirect support. You must negotiate with the IdP to use Response HTTP-POST or change integration requirements/solutions to one supporting that protocol.

**Exercise 3 — Overlong URL.** `AuthnRequest` keeps growing and the WAF returns 414. What is the reasonable direction?

**Answer:** inspect request size/WAF limits and what is placed into `AuthnRequest`; if the IdP exposes a POST `SingleSignOnService`, switch the outbound **`AuthnRequest`** binding to HTTP-POST. Never truncate URLs/signatures or switch **`SAMLResponse`** to Redirect.

**Exercise 4 — Signatures.** Redirect binding carries `Signature` yet IdP verification fails; a student tries “re-signing the Base64-decoded XML.” Where is the mistake?

**Answer:** Redirect query-style signatures sign the URL-encoded parameter string in the specified order, including `SigAlg` and `RelayState` if present; XML Signature is a different mechanism. Check keys, algorithms, and byte representation matching the binding.

**Exercise 5 — Cookies.** The IdP POSTs `SAMLResponse` to the ACS, yet the server cannot find `AuthnRequest` in the session even though the browser hit the right URL. What is the likely cause?

**Answer:** the browser may have omitted the SP session cookie on the cross-site POST due to `SameSite`, or the session/request repository is inconsistent. Inspect `Cookie`, `Set-Cookie`, `SameSite`, proxy settings, and request IDs; never drop `InResponseTo`.

**Exercise 6 — Reading metadata.** The IdP has two `SingleSignOnService` entries (Redirect, POST), while SP metadata has only a POST `AssertionConsumerService`. Is that a contradiction?

**Answer:** no. `SingleSignOnService` describes how the **IdP receives requests**, while ACS describes how the **SP receives responses**. The SP may choose Redirect or POST when sending `AuthnRequest`, while the Response still returns to the POST ACS.

## 17. IdP Integration Checklist

- [ ] Clearly identified Web Browser SSO, transport direction, and message type at each hop.
- [ ] Identified which IdP SSO endpoints support Redirect and/or POST for `AuthnRequest`.
- [ ] SP metadata advertises **HTTP-POST ACS** matching the actual public URL.
- [ ] IdP is configured to return **`SAMLResponse` via HTTP-POST**, not Redirect/GET or Artifact with default Spring Security SP login.
- [ ] Confirmed signing policy: Redirect query signature, POST XML signature, trusted certificates, validity windows, audience, and recipient.
- [ ] `RelayState`/Request ID are stored and matched; unsolicited response policy is defined if IdP-initiated login is enabled.
- [ ] Browser sends appropriate session cookies on cross-site POSTs; matching `SameSite`/CSRF strategy is in place.
- [ ] Tested through real proxies/WAFs to catch overlong URIs, wrong host/scheme, and URL encoding bugs.
- [ ] Checked Spring Security build/version and actually supported binding features; did not rely on legacy SAML Extension features.
- [ ] Logs/HARs have sensitive data redacted and all assertions are verified server-side.

## 18. Key Takeaways and References

**Quick mnemonic:**

- **HTTP-Redirect**: XML → raw DEFLATE → Base64 → URL-encode → `SAMLRequest` in **GET URL** (usually SP → IdP).
- **HTTP-POST**: XML → Base64 → HTML form → **POST body** (usually IdP → SP with `SAMLResponse`; can also be SP → IdP with `SAMLRequest`).
- **Modern Spring Security SAML 2.0 SP**: sends **`AuthnRequest` via Redirect or POST**; receives **login `Response` via POST**. Do not assume Artifact or login Response Redirect are available out of the box.
- **Both sides must align metadata**: IdP SSO Location/Binding, SP ACS Location/Binding, entity IDs, signing policy, and SAML conditions.

Standards and version references:
1. Spring Security — SAML 2.0 Login Overview: https://docs.spring.io/spring-security/reference/servlet/saml2/login/overview.html
2. Spring Security — Producing AuthnRequests, including Redirect/POST: https://docs.spring.io/spring-security/reference/servlet/saml2/login/authentication-requests.html
3. Spring Security — SAML 2.0 Extension Migration (Redirect Response and Artifact limitations): https://docs.spring.io/spring-security/reference/6.5/servlet/saml2/saml-extension-migration.html
4. Spring Security — SAML 2.0 Migration (GET Response converter by version): https://docs.spring.io/spring-security/reference/migration/servlet/saml2.html
5. Spring Security API — Saml2MessageBinding: https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/saml2/provider/service/registration/Saml2MessageBinding.html
6. OASIS — SAML 2.0 Technical Overview (profiles/bindings): https://docs.oasis-open.org/security/saml/Post2.0/sstc-saml-tech-overview-2.0.html
7. Spring Security SAML Extension 1.x (legacy documentation, do not apply verbatim to the new module): https://docs.spring.io/spring-security-saml/docs/current/reference/htmlsingle/
