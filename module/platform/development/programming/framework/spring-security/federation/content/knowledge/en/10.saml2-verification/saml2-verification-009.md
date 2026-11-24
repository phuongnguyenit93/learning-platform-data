# Distinguishing IdP Error Status Codes from Application Verification Errors in Spring Security SAML 2.0

## 1. Objective: Finding the Exact Source of an SSO Failure

A SAML 2.0 login attempt can fail at the **Identity Provider (IdP)**, while the browser transports the message, or when the **Service Provider (SP)** validates the response. End users usually only see a "Sign-in failed" screen, HTTP 302, 403, or 500. Those symptoms are **not enough** to identify who generated the error.

This lesson focuses on **SAML2 Verification** in **Spring Security - federation** systems. The core task is distinguishing:

1. **Protocol status codes sent by the IdP inside `<samlp:Response>`**, such as `Responder / NoPassive`, `Requester / InvalidNameIDPolicy`, `AuthnFailed`.
2. **Verification failures at the SP/Spring Security application**, such as invalid signature, wrong issuer, wrong audience, expired assertion, decryption failure, or missing matching AuthnRequest.

Both groups may surface through **the same login-failure handling path in Spring Security**, yet **their evidence sources and remedies differ**. The goal is not merely decoding XML, but having a reliable evidence-based triage workflow without skipping security validation.

After this lesson, learners will be able to:

- Read `StatusCode`, nested `StatusCode`, `StatusMessage`, and `StatusDetail` in a SAML Response.
- Know the four **top-level statuses** of SAML Core and notable subcodes in Web Browser SSO.
- Build a classification table: IdP errors, transport/browser errors, SP trust/validation errors, and post-login authorization errors.
- Understand how Spring Security Servlet processes `SAMLResponse` and the roles of `Saml2AuthenticationException`, `Saml2Error`, and failure handlers.
- Diagnose incidents across HTTP hops, server logs, IdP logs, correlation IDs, and verified SAML conditions.
- Design error messages/logs that do not leak assertions, identities, cookies, or private certificates.
- Run a standalone Java 17 example to practice classification without attempting to simulate XML Signature verification.
- Actively test failure cases in test environments and avoid "fixing" errors by turning off signature, expiry, or `InResponseTo` checks.

Examples use **Spring Boot 3.x / Spring Security 6.x Servlet/MVC, Java 17+**. Class names in Spring Security 7.x/OpenSAML 5 may differ from 6.x/OpenSAML 4; consult documentation for the exact version. `*.example.org` domains and IDs in this lesson are illustrative only.

## 2. Four Error Layers That Must Be Distinguished

Before reading a stack trace or DevTools, identify **which layer produced the observed value**.

| Layer | Observed object/code | Who produces it? | Examples | Is it a SAML StatusCode from the IdP? |
| --- | --- | --- | --- | --- |
| **HTTP/network** | HTTP status/transport error | Browser, proxy, ingress, web server | 302, 400, 403, 404, 414, 500, timeout, TLS error | **No** |
| **SAML protocol** | `<samlp:StatusCode Value="urn:oasis:...">` | IdP or a SAML responder issuing `Response` | `Success`, `Requester`, `Responder`, `NoPassive` | **Yes**, when actually present in Response |
| **SP authentication validation** | Java exception/error code in Spring Security | SP application after receiving/validating response | `Saml2AuthenticationException`, internal error code, signature invalid | **Not necessarily**; may be local error or relay of protocol error |
| **Application authorization/business** | 403/controller/domain exception after login | Authorization policy, controller, or downstream service | User is authenticated yet lacks permission to view orders | **No** |

**Important example:** the browser sees HTTP **200** when the IdP returns an HTML page containing the POST form; that form may carry a **SAML Response with top-level `Responder`**. HTTP 200 does not mean login succeeded. Conversely, a SAML Response with `Success` yet an invalid signature must still be rejected by the Spring SP.

Therefore **never invent a rule like "HTTP 4xx = IdP error; HTTP 5xx = SP error"**. Both IdP and SP/proxy can return 4xx or 5xx, and the IdP can report a SAML-level error inside an HTML POST returned with HTTP 200.

## 3. Authentication Flow and Where Each Error Occurs

~~~mermaid
sequenceDiagram
    participant B as Browser
    participant SP as Spring Security SP
    participant I as Identity Provider
    B->>SP: GET /portal/private
    SP-->>B: Redirect to SAML login
    B->>SP: GET /saml2/authenticate/corp
    SP-->>B: AuthnRequest (Redirect or POST binding)
    B->>I: Forward AuthnRequest
    alt IdP rejects request / fails to authenticate
        I-->>B: HTML form with SAMLResponse containing error Status
        B->>SP: POST SAMLResponse to ACS
        SP->>SP: Detect protocol status, handle authentication failure
        SP-->>B: Failure page, no Authentication created
    else IdP authenticates successfully
        I-->>B: HTML form with SAMLResponse Status=Success
        B->>SP: POST SAMLResponse to ACS
        alt Assertion checks pass
            SP->>SP: Verify trust, signature, issuer, audience, time...
            SP-->>B: Establish Authentication/SP session
        else SP detects validation error
            SP->>SP: Saml2AuthenticationException / failure handler
            SP-->>B: Login failed, no new Authentication created
        end
    end
~~~

A third failure path happens when **the browser never POSTs a SAMLResponse to the ACS**: the IdP may render an HTML error page, the browser may block cookies, SSO redirects break, TLS fails, a proxy returns 502, or the user closes the tab. In this case **there may be no SAML StatusCode to read at all**.

Regardless of cause, only issue an SP session after the SAML/application pipeline succeeds per policy. Never build a classifier on untrusted data and let it bypass validation.

## 4. Structure of <samlp:Status> in a SAML Response

SAML 2.0 Core defines `<Status>` for multiple protocol responses. For `<samlp:Response>`, the status section contains:

- **Mandatory `StatusCode`**: has a `Value` URI attribute; the outermost code is **top-level**.
- **Optional nested `StatusCode`**: a more specific subcode. Not every IdP emits a subcode; the spec and errata permit omitting subcodes in several cases, including avoiding information leakage.
- **Optional `StatusMessage`**: text supplied by the responder. It may be absent, contain vendor-specific wording, or contain content unsafe to display directly.
- **Optional `StatusDetail`**: additional data that may be an XML extension; there is no fixed contract across all IdPs.

Illustrative example of **IdP unable to perform passive authentication**:

~~~xml
<samlp:Response
    xmlns:samlp="urn:oasis:names:tc:SAML:2.0:protocol"
    xmlns:saml="urn:oasis:names:tc:SAML:2.0:assertion"
    ID="_resp-demo"
    Version="2.0"
    IssueInstant="2026-11-07T00:00:00Z"
    InResponseTo="_authn-demo"
    Destination="https://app.example.org/login/saml2/sso/corp">
  <saml:Issuer>https://idp.example.org/entity</saml:Issuer>
  <samlp:Status>
    <samlp:StatusCode
        Value="urn:oasis:names:tc:SAML:2.0:status:Responder">
      <samlp:StatusCode
          Value="urn:oasis:names:tc:SAML:2.0:status:NoPassive"/>
    </samlp:StatusCode>
    <samlp:StatusMessage>
      Passive authentication is not available
    </samlp:StatusMessage>
  </samlp:Status>
</samlp:Response>
~~~

This is **structural illustration XML**, not a signed/usable SAMLResponse. There is no assertion in the example because the responder reported an error; this **does not make an error status non-compliant**. Signature requirements for error responses and trust rules for error messages must follow the profile, metadata, policy, and product capabilities.

From the example:
- Top-level = **`Responder`**.
- Subcode = **`NoPassive`**.
- `StatusMessage` is explanatory wording, **not a standard code**.
- Initial conclusion is "IdP *reported* inability to satisfy passive", **not** "bad signature at Spring SP".

**Crucial note on source trust:** merely decoding XML from the browser does not make all content trustworthy. If an error response is not verified by an appropriate mechanism, log the observation as **reported/unverified status** and do not use it to bypass security policy or authorization.

## 5. Four Top-Level SAML StatusCodes

Standard URIs share the prefix `urn:oasis:names:tc:SAML:2.0:status:`.

| Top-level code | Meaning per SAML Core | Initial triage |
| --- | --- | --- |
| **`Success`** | The SAML request succeeded at protocol processing level | Continue verifying response, assertion, signature, issuer, conditions; **not enough for SP login success** |
| **`Requester`** | Request could not be fulfilled due to an error on the requesting entity's side | Inspect AuthnRequest, SP entity ID, policy, binding, signature, NameIDPolicy; **do not blame the end user's browser** |
| **`Responder`** | Request could not be fulfilled due to an error on the responder/SAML authority | Inspect IdP policy, session, login event, IdP backend, and any subcode |
| **`VersionMismatch`** | Responder could not process because request version is unsuitable | Check Version/protocol and actual IdP endpoint |

A common misconception: `Requester` is named after the **entity sending the SAML request**, typically the **SP** in SP-initiated login, rather than meaning "user typed wrong password". And `Responder` does not automatically mean IdP HTTP 500; an IdP can process a request cleanly and send status Responder via a normal HTML form POST.

Top-level `Success` means the responder **reported** protocol success. The Spring SP must still validate the entire Response/Assertion and application policy. Never write "if status Success then set SecurityContext" in a custom controller.

## 6. Common Subcodes in Web Browser SSO Integration

Subcodes are **not mandatory**. OASIS defines a set of second-level codes, while vendors may use other URIs by agreement. Do not hardcode an assumption that every error always has two levels.

| Subcode | Typical SAML meaning | Appropriate check |
| --- | --- | --- |
| **`AuthnFailed`** | Responder could not authenticate the principal | Account/credentials, MFA, risk policy, IdP audit; do not jump to "wrong password" |
| **`NoPassive`** | Cannot fulfill requested passive authentication | `IsPassive=true`, IdP session, and silent auth capability; fall back to interactive if allowed |
| **`NoAuthnContext`** | Cannot satisfy requested authentication context | `RequestedAuthnContext`, assurance/MFA level, and IdP policy |
| **`InvalidNameIDPolicy`** | IdP cannot/will not support `NameIDPolicy` | Compare `Format`, `SPNameQualifier`, `AllowCreate`, IdP config |
| **`RequestDenied`** | Responder could process yet chose not to respond/request rejected | SP trust, request policy, request signature, rate/risk policy, contract; do not assume user is locked |
| **`RequestUnsupported`** | Request type not supported by responder | Sent to wrong protocol/endpoint or unsuitable feature/binding |
| **`UnsupportedBinding`** | Responder cannot respond using specified binding | IdP metadata SSO binding, SP ACS binding, HTTP-Redirect/POST |
| **`UnknownPrincipal`** | Responder does not recognize principal specified or implied by request | IdP user provisioning/directory, subject/name identifier; guard against user enumeration |
| **`NoAvailableIDP`, `NoSupportedIDP`** | Federation proxy/discovery has no suitable IdP | IdPList, federation links, upstream routing |
| **`ProxyCountExceeded`** | Cannot proxy AuthnRequest further due to limit | Scoping/ProxyCount, IdP proxy chain |
| **`InvalidAttrNameOrValue`** | Invalid Attribute/AttributeValue for query/protocol | Mapping and attribute profile support; not automatically a regular login error |
| **`PartialLogout`** | Only part of participating parties logged out | **Single Logout**, must not be treated as a regular login success/failure code |

OASIS also defines `RequestVersionDeprecated`, `RequestVersionTooHigh`, `RequestVersionTooLow`, `ResourceNotRecognized`, `TooManyResponses`, and `UnknownAttrProfile`. They carry specific protocol/request meanings and should not be listed as login errors every IdP emits.

### Avoid Over-Inferring from Subcodes

- `AuthnFailed` is not enough to say "wrong password"; it may be a blocked user, failed MFA, risk policy, or upstream provider.
- `InvalidNameIDPolicy` does not mean the token/assertion had a bad signature.
- `NoAuthnContext` differs from an SP issuer/audience error: it indicates the IdP **could not fulfill AuthnContext**, whereas the SP may separately reject an assertion whose context fails policy.
- `UnsupportedBinding` in XML status means the **responder reports an unsupported binding**. HTTP 405/404 at the ACS is an HTTP route/filter mapping error, possibly with no SAML response.
- `RequestDenied` may be used by the IdP to avoid disclosing sensitive details; do not demand that the IdP return a StatusMessage describing internal checks.

## 7. What Is **Not** an IdP Status Code

This is where many engineering teams misdiagnose.

### HTTP Status Is Not SAML StatusCode

An HTTP response showing:

~~~http
HTTP/1.1 302 Found
Location: /login?error
~~~

indicates the browser was redirected after an event; it **does not tell you** whether the SAML Response held `Responder` or was rejected by the SP for a bad signature. Both cases can produce the exact same redirect.

HTTP `403 Forbidden` at `/login/saml2/sso/corp` can stem from CSRF configuration, filter chain, access control, or response error handling; **you cannot infer** top-level SAML `Requester`.

HTTP `403` at `/portal/admin` after the user already has a valid SSO session may be an **authorization failure**, not a SAML login failure.

### SP Exceptions Are Not SAML StatusCodes Either

Spring may throw:

~~~text
org.springframework.security.saml2.provider.service.authentication.Saml2AuthenticationException
~~~

This is a **Java exception inside the application**. It can occur because **the IdP sent an unsuccessful status** or because **the SP detected a local error** while parsing/validating the response. **Looking only at the exception name cannot separate the causes.**

Spring also has `Saml2Error` and **framework API** error codes (e.g., classifying decryption, invalid response, missing subject depending on version). Those codes **are not automatically** OASIS `urn:oasis:names:tc:SAML:2.0:status:...` URIs sent by the IdP.

### Spring Controller / Business Errors Are Also Not IdP Statuses

After SAML login succeeds, an application service may:
- Fail to find the user in the internal database;
- Deny access by role/group;
- Fail to map the account to a tenant;
- Return 500 when calling a downstream service;
- Return 403 because the user lacks permission on a resource.

Those are **provisioning/authorization/application** errors, requiring mapping and policy fixes. Never swap IdP certificates or disable SAML validation to "fix" business errors.

## 8. How Does an IdP Report an Error Without Returning an Assertion?

A failed Response may contain only `Status` and **no successful Assertion**. Example:

~~~xml
<samlp:Response
    xmlns:samlp="urn:oasis:names:tc:SAML:2.0:protocol"
    xmlns:saml="urn:oasis:names:tc:SAML:2.0:assertion"
    ID="_response-failed-example"
    Version="2.0"
    IssueInstant="2026-11-07T00:00:00Z"
    InResponseTo="_request-example"
    Destination="https://app.example.org/login/saml2/sso/corp">
  <saml:Issuer>https://idp.example.org/entity</saml:Issuer>
  <samlp:Status>
    <samlp:StatusCode
        Value="urn:oasis:names:tc:SAML:2.0:status:Requester">
      <samlp:StatusCode
          Value="urn:oasis:names:tc:SAML:2.0:status:InvalidNameIDPolicy"/>
    </samlp:StatusCode>
  </samlp:Status>
</samlp:Response>
~~~

**Conclusion:** the IdP *reports* a request error regarding NameIDPolicy. The SP must not turn this Response into an authenticated user even if issuer/response metadata look fine. Conversely, if the SP needs to verify that this status **genuinely came from a trusted IdP**, it must rely on response signature/trust, channel, and appropriate config; never render raw StatusMessage as trusted content.

When an IdP cannot complete a SAML request, how errors are emitted also depends on the product and profile:
- Some IdPs **POST a SAML Response containing an error Status** to the ACS.
- Some IdPs display an HTML error page, return no Response, or only write internal logs.
- Some IdPs use custom error URIs/support codes instead of full subcodes.
- A reverse proxy may block/time out before the IdP produces any SAML status.

**Therefore, seeing no StatusCode in a browser trace is insufficient to conclude the IdP succeeded.**

## 9. SAML Response Reports Success Yet SP Rejects — Why?

Example Response containing:

~~~xml
<samlp:Status
    xmlns:samlp="urn:oasis:names:tc:SAML:2.0:protocol">
  <samlp:StatusCode
      Value="urn:oasis:names:tc:SAML:2.0:status:Success"/>
</samlp:Status>
~~~

Its meaning is solely that **the responder reported protocol success**. Below are what the SP still must check:

1. **Parsing/encoding:** is `SAMLResponse` Base64 valid, and can XML be read without allowing XXE/entity expansion?
2. **Relying Party registration:** which IdP/registration does the response bind to, and which metadata was approved?
3. **Response signature/Assertion signature:** is the signature valid under trusted verification credentials? Depending on implementation/version, required signed parts and binding rules are explicit.
4. **Issuer:** does it match the trusted IdP entity ID in `RelyingPartyRegistration`?
5. **Destination and Recipient:** do Response/SubjectConfirmation target the SP's exact public ACS URL?
6. **AudienceRestriction:** is the assertion issued for the exact SP entity ID?
7. **InResponseTo:** does the response correlate to an AuthnRequest created in the session/browser per SP-initiated flow?
8. **Subject / SubjectConfirmationData:** are NameID/subject and confirmation method sufficient per policy?
9. **NotBefore/NotOnOrAfter:** are the assertion/subject confirmation valid within allowed clock skew?
10. **Replay/one-time use:** was the request/assertion/response ID reused or outside policy?
11. **Decryption:** if the IdP encrypted the assertion/attribute, does the SP have the right private key to decrypt while preserving proper verification order?
12. **Mapping:** do subject/attribute data suffice to build the principal per framework config without granting unauthorized roles?

**Even a single failed item suffices for the SP to reject**, despite IdP status `Success`. Do not "change" status to Responder because local verification failed: **the IdP did not emit Responder in this scenario**.

## 10. SP Verification Error Groups and Investigation Paths

| Local error | Symptom at SP | Causes to examine | What not to conclude |
| --- | --- | --- | --- |
| **Malformed/missing SAMLResponse** | Cannot read POST parameter, Base64 error, XML parser error | Wrong binding, proxy/body limits, malformed request | "IdP returned AuthnFailed" before reading status |
| **Invalid signature** | Provider rejects XML Signature | IdP signing certificate, cert rollover, canonicalization, modified response, trust config | "Changing status code to Success will pass" |
| **Unknown registration** | Cannot resolve `registrationId`/`RelyingPartyRegistration` | ACS URL, RelayState, multi-IdP registration | "User entered wrong password" |
| **Issuer mismatch** | Response issuer differs from trusted entity ID | Wrong IdP metadata imported, entity ID, multi-tenant | "IdP just had an availability blip" |
| **Destination/Recipient mismatch** | Response targets URL other than running ACS | Reverse proxy, HTTP↔HTTPS, host/port/path, SP metadata | "Fix browser redirect without involving IdP" |
| **Audience mismatch** | Assertion not meant for current SP | Wrong SP entity ID or misconfigured audience at IdP | "Once signed, every SP may accept the assertion" |
| **Expired assertion** | `NotOnOrAfter` passed | Clock skew, server NTP, replay, IdP session timing | "Increase clock skew indefinitely" |
| **NotBefore in future** | Assertion not yet valid | Clock drift, misissued timestamp | "Disable time checks" |
| **InResponseTo mismatch** | No matching AuthnRequest found | SameSite session/cookies, request repository, multi-tab, IdP-initiated flow | "Drop correlation for speed" |
| **Missing subject** | Cannot determine NameID/principal | IdP NameID/attribute mapping, encrypted ID | "HTTP 500 error at IdP" |
| **Decrypt failed** | Cannot decrypt EncryptedAssertion/ID/attribute | SP decryption key/cert/algorithm, wrong key rotation | "Just disable encryption" |
| **Replay detected** | Request/Assertion ID already used | Repeated callback, replay attack, repository TTL | "Increasing TTL is safe" |
| **Response signed but assertion not acceptable** | Provider rejects assertion policy | Conditions, subject confirmation, signature model, auth context | "A single response signature covers every condition" |

**Do not confuse an "issuer mismatch at SP" with `Requester` sent by the IdP.** One is **local response verification**, while the other is a **protocol status emitted by the responder**.

## 11. A Single Response Can Carry Both Status and Local Errors

A real pipeline may encounter:

**Scenario 1 — IdP reports a clear error, no assertion:** Response contains `Responder / NoPassive`. The SP must recognize failure, create no session, and may guide the user to try a new interactive login. Still verify source/status per trust policy.

**Scenario 2 — Response reports Success yet signature is invalid:** This is an **SP validation failure**. Keep the response rejected; never skip signature verification just because status Success "looks good".

**Scenario 3 — Error response from IdP also fails signature/issuer:** You may see a subcode in raw XML yet **cannot assert it is trustworthy**. Primary triage should reflect "message not verified by SP" alongside the observation "untrusted reported status present"; never attribute an error to the IdP based on a value an attacker could craft.

**Scenario 4 — Response Success verified and authenticated, yet route returns 403:** SAML authentication **succeeded**, while authorization failed. Inspect application roles/tenant/provisioning, not SAML issuer, ACS, or signature.

**Scenario 5 — Browser receives HTTP 500 from IdP, no POST to ACS:** No SAML status exists yet. Investigate the IdP HTTP layer and request traces; do not invent `Responder` if the IdP sent no SAML Response.

**Scenario 6 — Lost RelayState/cookie:** Spring cannot find the AuthnRequest and may reject a valid Response for missing correlation. This is an **SP session/correlation/browser** issue; the IdP may have succeeded from its perspective. Do not turn it into an "AuthnFailed" error.

## 12. Decision Tree for Ticket Triage

~~~mermaid
flowchart TD
    A[User reports SSO failure] --> B{Did browser POST SAMLResponse to ACS?}
    B -- No --> C[Investigate IdP page, redirect, TLS, proxy, cookie, network]
    B -- Yes --> D{Did SP receive and parse response safely?}
    D -- No --> E[Transport, binding, parsing, or filter error at SP]
    D -- Yes --> F{Does Response have non-Success SAML Status?}
    F -- Yes --> G[IdP reported protocol failure; evaluate trust and subcode]
    F -- No or Success --> H{Did SP verification pass?}
    H -- No --> I[Local SAML authentication validation failure]
    H -- Yes --> J{Was Authentication created?}
    J -- No --> K[Mapping, principal, or app authentication pipeline]
    J -- Yes --> L{Did post-login resource return 403?}
    L -- Yes --> M[Application authorization or provisioning]
    L -- No --> N[Login succeeded; check UX/redirect if issue persists]
~~~

**Caution:** the branch reading SAML status is a **diagnostic step**, not authorization. A "reported" IdP error response may still fail trust checks; verify source per policy before treating it as the confirmed root cause. When multiple errors coexist, **never use XML read order to declare a single origin**; record observations, trust status, and local check steps.

The tree above does not suggest decrypting assertions into principals yourself. Verification belongs to the Spring Security/OpenSAML provider.

## 13. How Does Spring Security Handle the SAMLResponse Callback?

In Spring Security Servlet SAML 2.0 Service Provider:

1. The IdP creates a Response and the browser typically **HTTP POSTs** the `SAMLResponse` field to the default ACS `/login/saml2/sso/{registrationId}`.
2. `Saml2WebSsoAuthenticationFilter` handles the callback (when chain/matcher match).
3. A converter, typically `Saml2AuthenticationTokenConverter`, extracts the request and resolves `RelyingPartyRegistration`.
4. `AuthenticationManager` delegates the token to Spring Security's OpenSAML-backed provider: in **6.x** there is `OpenSaml4AuthenticationProvider` depending on dependencies; in **7.x** modern guides use `OpenSaml5AuthenticationProvider`.
5. The provider decodes/parses and validates in the appropriate order, potentially checking status, signatures, issuer/destination, conditions, subject, audience, and decryption.
6. Upon success, returns `Saml2Authentication` holding `Saml2AuthenticatedPrincipal` and authorities; filter/chain sets SecurityContext per configuration.
7. Upon failure, `AuthenticationException` goes to the authentication failure handler / entry point; **no new authenticated principal is created**.

API names, validators, and exact step order can change across versions/providers. Do not import 7.x class names into a 6.x project that does not support OpenSAML 5.

### Why Is One Exception Insufficient to Name the Root Cause?

`Saml2AuthenticationException` is a subclass of `AuthenticationException` for SAML-related failures, e.g.:
- Missing or malformed XML SAMLResponse;
- Missing/invalid Response/Assertion signature or untrusted certificate;
- Failed Assertion conditions, subject, or expiry;
- Decryption failure;
- Provider encountered an unsuccessful protocol response.

The framework may route different failures into the same failure handler branch to present similar UX. To classify properly, rely on **response status (if present and trusted), framework error code, validation stage, and correlated logs**, rather than regex-matching exception message strings and treating them as standard IdP codes.

## 14. <samlp:StatusCode> Differs from <Saml2Error.getErrorCode()>

This is an important technical distinction in Java.

**SAML StatusCode** resides in XML under the namespace:

~~~text
urn:oasis:names:tc:SAML:2.0:status:
~~~

It belongs to the **protocol**, reported by the IdP/SAML responder.

**`Saml2Error`** is an object in Spring Security's API `org.springframework.security.saml2.core.Saml2Error`. It holds `getErrorCode()` and `getDescription()`. `Saml2AuthenticationException#getSaml2Error()` reads the error raised by the Spring framework in the authentication pipeline.

A Spring error code can represent an **internal error**, not an OASIS StatusCode. In Spring Security 7.0+, factories exist such as `invalidResponse()`, `malformedResponseData()`, `decryptionError()`, `relyingPartyRegistrationNotFound()`, and `subjectNotFound()`. **They must not be treated as URIs from the IdP.** Codes/constants and APIs can vary across versions.

Example classification code when handling an `AuthenticationException`:

~~~java
String diagnosticCode = "OTHER_AUTHENTICATION_FAILURE";
if (exception instanceof Saml2AuthenticationException samlException) {
    diagnosticCode = samlException.getSaml2Error().getErrorCode();
}
~~~

This is only a **code fragment inside a failure handler with proper imports**. The `diagnosticCode` variable represents the **framework API**; it is **insufficient** to directly infer top-level `Responder`, subcode `NoPassive`, or the XML signer. If a business event like "IdP reported NoPassive" is needed, the system must have protocol status evidence under an appropriate trust policy rather than guessing from any error code.

## 15. Spring Security Java 17+ Example: Safe Failure Handler

Below is a **complete configuration class** for a Spring Boot Servlet project with compatible Spring Security/SAML 2.0 dependencies and a valid IdP registration. It does not manually parse SAML XML, does not replace provider validation, and **does not echo exception messages to the browser**. File:

`src/main/java/com/example/federation/SamlFailureConfiguration.java`

~~~java
package com.example.federation;

import java.io.IOException;

import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.authentication.AuthenticationServiceException;
import org.springframework.security.core.AuthenticationException;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.saml2.provider.service.authentication.Saml2AuthenticationException;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class SamlFailureConfiguration {

    private static final Logger log =
            LoggerFactory.getLogger(SamlFailureConfiguration.class);

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http) throws Exception {
        return http
                .authorizeHttpRequests(auth -> auth
                        .requestMatchers("/auth/problem", "/error", "/public/**").permitAll()
                        .anyRequest().authenticated())
                .saml2Login(saml -> saml.failureHandler(this::onFailure))
                .build();
    }

    private void onFailure(
            HttpServletRequest request,
            HttpServletResponse response,
            AuthenticationException exception) throws IOException {

        String category = "OTHER_AUTHENTICATION_FAILURE";
        String internalCode = "none";

        if (exception instanceof Saml2AuthenticationException saml) {
            category = "SAML_AUTHENTICATION_FAILURE";
            String code = saml.getSaml2Error().getErrorCode();
            if (code != null && code.matches("[A-Za-z0-9_.:-]{1,100}")) {
                internalCode = code;
            }
        }
        else if (exception instanceof AuthenticationServiceException) {
            category = "AUTHENTICATION_SERVICE_FAILURE";
        }

        log.warn("SAML login failed; category={}, localCode={}",
                category, internalCode);

        response.sendRedirect(request.getContextPath() + "/auth/problem");
    }
}
~~~

**Notes when running:**
- Requires `spring-boot-starter-security`, `spring-security-saml2-service-provider`, Spring Web/Servlet, Java 17, and OpenSAML dependencies resolved per Spring Security version.
- This class is component-scanned under a `@SpringBootApplication`. It is **not** a standalone program compiled with `javac SamlFailureConfiguration.java` on an empty JDK.
- Create a public page/controller for `/auth/problem` (without echoing raw exceptions); without a controller, that URL may return 404 even after the handler runs.
- `saml2Login(... failureHandler(...))` is the hook **for SAML authentication failures** at the filter; a post-login 403 authorization error or a 404 at a proxy does not automatically enter this handler.
- `Saml2Error.getErrorCode()` is logged under the label **`localCode`**, not named `idpStatus`. The regex retains only a short technical string; production systems also need log sampling/redaction policies and a correlation ID.
- The code does not log usernames, XML, SAMLResponse, RelayState, cookies, Authorization headers, `StatusMessage`, or unsanitized exception messages.
- Failures outside the Spring filter scope (proxy, IdP HTML page, browser blocking cookies before callback) **do not trigger** this code.

**Expected HTTP result when the handler is invoked:** the browser receives a redirect to the generic error page `/auth/problem`; there is no "fixed stdout" because logging is a runtime event dependent on requests and the provider. Do not use a successful redirect to infer protocol status.

### When a Support Code Is Needed for the User

The error page should show a non-disclosing message:
> "Unable to complete login. Please try again or contact support and provide the request code."

The request code can be an **opaque server-generated request correlation ID**, not SAMLResponse, NameID, or internal exception descriptions. In server logs, operations teams use that ID to correlate SP and IdP records (under logging/privacy policy). Do not create a public error page containing `getSaml2Error().getDescription()` because descriptions can leak validation details, endpoints, certs, or partner-supplied data.

## 16. Minimal SAML SP Config for Lab Verification

In a Spring Boot 3.x Servlet project with dependencies already configured, a registration can use vetted IdP metadata:

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

File `src/main/resources/saml/corp-idp.xml` must be valid metadata from a verified IdP, containing issuer, SSO endpoint, and signing certificate. Never use example hosts or randomly self-generated certificates and call it production trust.

In Gradle using Boot BOM/dependency management:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-security'
    implementation 'org.springframework.security:spring-security-saml2-service-provider'
}
~~~

This is only a `dependencies` snippet to insert into an existing Boot project; resolving OpenSAML may require the Shibboleth releases repository per Spring Security docs and build policy. Do not pin versions incompatible with the Spring Boot BOM.

**Distinguish configuration from operation:** proper dependencies + metadata + filter chain only start the flow; the IdP must also register the exact SP entity ID/ACS, signing policy, and test user. A successful build does not verify any status or assertion.

## 17. Do Not Use StatusMessage as a Trusted Information Source

`StatusMessage` is free text that an IdP/SAML responder may send. Even when validly signed, it can contain:
- Username, email, or tenant details;
- Security group names, MFA policies, account state;
- Internal IdP info;
- Arbitrary text or extensions forwarded from an upstream IdP.

To stay safe:
1. **Never render verbatim to users** in unescaped HTML. Prevent XSS and user enumeration.
2. **Never store raw in general logs** without a data protection policy.
3. Never branch business logic on English/Vietnamese/vendor-localized text.
4. **Prefer structured codes**: top/sub StatusCode once properly verified; for local failures, use exception type and framework error code with validation stage.
5. If logging vendor reasons is required for support, restrict access, apply redaction, and enforce retention.
6. StatusDetail can contain unfamiliar XML extensions; never parse with an unhardened XML parser or deserialize into arbitrary objects.

A "User does not exist" sentence in StatusMessage can disclose account information. Public login pages should show generic messages, keeping investigative details in access-controlled logs.

## 18. Look at Browser DevTools Without Ignoring Server Logs

**Browser Network → Preserve log** shows the front-channel:
- Initial request to SP;
- GET/POST initiating `/saml2/authenticate/corp`;
- Redirect/form to IdP;
- SAMLResponse POST back to SP ACS;
- Redirect to failure page or resource;
- Whether session cookie was sent on the ACS POST.

**Spring SP server logs** reveal verification outcomes and local causes invisible to the browser:
- Base64/XML parsing errors;
- Missing registration/issuer;
- Signature or certificate mismatch;
- Audience/Destination/Recipient;
- Timestamps and correlation;
- Decryption, principal mapping;
- Whether the failure handler fired before or after creating Authentication.

**IdP audit/logs** (if accessible) reveal:
- Which AuthnRequest the IdP received;
- SP entity ID and IdP entity ID pair;
- User/session/method/policy (within granted access);
- Reason for returning an error SAML Status or issuing no Response;
- Whether MFA/ForceAuthn/IsPassive/RequestedAuthnContext were satisfied;
- Whether an upstream proxy IdP was involved.

**Not every incident can be solved from a single HAR.** Seeing a status in browser XML does not prove signature validity; seeing login success in IdP logs does not prove the SP accepted the assertion.

## 19. Repeatable 12-Step Investigation Workflow

### Step 1 — Lock Down the Scenario

Record environment, UTC timestamp, registration ID, public SP ACS, permitted IdP issuer, login initiation type (SP-initiated or IdP-initiated), browser, and action. Do not record passwords or full NameIDs in tickets.

### Step 2 — Locate the First Failing HTTP Hop

Use sanitized DevTools/HAR. Confirm whether `SAMLResponse` was POSTed to the ACS. If **not**, investigate IdP/network/browser/redirects before blaming SP assertion signatures.

### Step 3 — Identify Who Generated the HTTP Status

HTTP 403 from `idp.example.org`, HTTP 403 from `app.example.org`, and HTTP 403 from a WAF in front of the SP are three distinct systems. Inspect shareable host/path/response headers, proxy logs, and trace IDs.

### Step 4 — If SAMLResponse Exists, Read Status Safely

Only use authorized test environments/tools. Read top-level and subcode (if present); label them **observed/reported** before proving trust. If status is non-Success, no new user is authenticated.

### Step 5 — Find the Spring Authentication Failure/Success Event

Inspect handler/provider logs. `Saml2AuthenticationException` may describe local validation; never infer origin from exception name alone.

### Step 6 — Verify Origin and Registration

Compare `Issuer` (response/assertion) against approved IdP metadata, `Destination` against ACS, and `Audience` against SP entity ID. Any mismatch is a local or federation configuration error even if the IdP reported Success.

### Step 7 — Verify Signatures and Certificates

Check certificate trust, rollover, and response/assertion signing policies. Never eyeball Base64 strings to declare a signature valid. Never blindly add certificates from SAMLResponse into the trust store.

### Step 8 — Check Timestamps

Inspect `IssueInstant`, `NotBefore`, `NotOnOrAfter`, SubjectConfirmation, and NTP clocks; evaluate bounded clock skew. Never widen by hours just to make tests pass.

### Step 9 — Check Request Correlation

For SP-initiated flows, compare AuthnRequest ID with `InResponseTo` and session/request repository. SameSite cookies can cause IdP POSTs to the SP without the browser sending the required session cookie.

### Step 10 — Check Post-Login Business Errors

If SP Authentication was already created, subsequent 403/404 resource responses usually stem from authorization, routing, tenant, user provisioning, or downstream issues. Do not alter SAML StatusCodes.

### Step 11 — Align the SP–IdP Timeline

Correlate timestamps, SP request IDs, IdP event IDs, and app trace IDs via approved log channels. Never share assertions/raw HARs containing personal data in public chat channels.

### Step 12 — Record Conclusions with Confidence Level

Use the structure:

~~~text
Observed:
  - Browser posted a SAMLResponse to the expected ACS
  - The Response contains a reported top-level Responder
  - The subordinate code is NoPassive
Validated:
  - SP authentication was not established
  - The request had IsPassive=true
Attribution:
  - IdP reported inability to satisfy passive authentication
  - Signature/source verification is [verified | not verified]
Next action:
  - Check IdP passive policy and retry with a new interactive request if allowed
~~~

This is a **ticket content template**, not default Spring Security logging; do not write `verified` unless actually verified. If local validation failed, replace Attribution with the exact detail (for instance, audience mismatch) and record the IdP status as a separate observation.

## 20. Standalone Java 17 Exercise: Evidence-Based Classification

This program **does not receive or verify real SAML XML**. It only simulates classification based on **already observed/checked facts**: whether the callback reached ACS, whether an IdP status exists, whether SP verification failed, whether the user is authenticated, and whether the app subsequently returned 403.

File `SamlFailureTriageDemo.java`:

~~~java
public final class SamlFailureTriageDemo {

    record Evidence(
            boolean reachedAcs,
            String idpTopStatus,
            boolean localVerificationFailed,
            boolean authenticated,
            boolean accessDeniedAfterLogin) {
    }

    static String classify(Evidence evidence) {
        if (!evidence.reachedAcs()) {
            return "NO_SAML_RESPONSE_AT_ACS";
        }
        if (evidence.localVerificationFailed()) {
            return "SP_VERIFICATION_FAILED";
        }
        if (evidence.idpTopStatus() != null &&
                !"Success".equals(evidence.idpTopStatus())) {
            return "IDP_REPORTED_PROTOCOL_FAILURE";
        }
        if (evidence.authenticated() && evidence.accessDeniedAfterLogin()) {
            return "APPLICATION_AUTHORIZATION_FAILED";
        }
        if (evidence.authenticated()) {
            return "AUTHENTICATED";
        }
        return "INSUFFICIENT_EVIDENCE";
    }

    public static void main(String[] args) {
        System.out.println(classify(
                new Evidence(false, null, false, false, false)));
        System.out.println(classify(
                new Evidence(true, "Responder", false, false, false)));
        System.out.println(classify(
                new Evidence(true, "Success", true, false, false)));
        System.out.println(classify(
                new Evidence(true, "Success", false, true, true)));
        System.out.println(classify(
                new Evidence(true, "Success", false, true, false)));
    }
}
~~~

Compile and run:

~~~bash
javac SamlFailureTriageDemo.java
java SamlFailureTriageDemo
~~~

**Exact** stdout:

~~~text
NO_SAML_RESPONSE_AT_ACS
IDP_REPORTED_PROTOCOL_FAILURE
SP_VERIFICATION_FAILED
APPLICATION_AUTHORIZATION_FAILED
AUTHENTICATED
~~~

**Explanation:** line 1 has no Response yet; line 2 IdP *reported* Responder and no local validation failure was recorded; line 3 IdP reported Success yet SP verification failed; line 4 SSO authenticated yet the app denied access; line 5 login succeeded. Parameters are **externally verified input facts**, not values verified by this Java code itself.

**Mandatory limitation:** if an untrusted response carries status Responder alongside a signature error, set `localVerificationFailed=true` so an untrusted status value is not treated as the verified cause. This demo code does not alter protocol semantics, process XML Signatures, validate OASIS schemas, or act as production SSO middleware.

## 21. Integration Test Matrix

| Test scenario | IdP/browser expectation | SP expectation | Error category to record |
| --- | --- | --- | --- |
| Valid login, valid assertion | Status Success, POST Response | Create Authentication and session | Success |
| User fails IdP policy | May return Response Responder/AuthnFailed or IdP error page | Create no new session | **IdP reported** if status exists, or non-SAML IdP error |
| IsPassive=true without silent auth | May return Responder/NoPassive | Create no session, safe fallback | **IdP status**, not local signature error |
| RequestedAuthnContext too high | May return Responder/NoAuthnContext | Disallow task needing assurance | **IdP status/policy** |
| Incompatible NameIDPolicy | May return Requester/InvalidNameIDPolicy | Create no session | **IdP status** |
| Unsupported SP AuthnRequest binding | May return UnsupportedBinding, or HTTP error before ACS | Handle failure; do not silently switch binding | **IdP protocol or HTTP** per evidence |
| IdP Response Status Success yet signed with untrusted cert | HTTP POST Response to ACS | Reject signature | **SP verification** |
| Status Success, wrong Audience | Browser still POSTs | Reject audience | **SP verification** |
| Status Success, wrong Recipient/Destination | Browser POSTs to wrong or right ACS yet XML destination differs | Reject | **SP verification** |
| Status Success, expired NotOnOrAfter | Browser POSTs | Reject | **SP verification/time** |
| Status Success, InResponseTo lacks matching request | Browser POSTs | Reject per policy; do not drop correlation | **SP verification/session** |
| Empty/malformed SAMLResponse | Browser POSTs malformed field | Converter/provider fails, no Authentication created | **SP parsing/transport** |
| IdP HTTP 502, no Response | No ACS callback | No new Authentication | **IdP/proxy/network**, no SAML status yet |
| SP authenticated then /admin returns 403 | Login succeeds | AccessDeniedHandler/authorization | **Application authorization** |

When building negative tests, use only a **test IdP/test SP** and authorized synthetic data. Never alter a real user's signature and send it to production. For signature tests, use an official harness or mock/test IdP with a test certificate; never publish assertions, private keys, or HARs containing cookies.

## 22. "One Error Code, Multiple Possibilities" Cases

### 22.1 AuthnFailed

An IdP may send subcode `AuthnFailed` when:
- User enters wrong credentials;
- User fails to complete MFA;
- Account is locked/disallowed by policy;
- Upstream IdP returns an error;
- Risk engine denies the session.

Never expose raw account status to end users. Obtain details from **IdP audit** within authorized access rather than guessing from the SAML StatusCode.

### 22.2 Requester

May stem from invalid SP AuthnRequest signature, NameIDPolicy, entity ID, binding, IdP-accepted ACS, or SP policy. Do not conclude the browser's HTTP request was malformed just because the code is Requester; **requester here means the SAML requester**.

### 22.3 Responder

May stem from the IdP failing to process the request, no active/passive session, service error, upstream identity failure, or policy. Yet an IdP HTTP 502 does not become Responder unless a SAML Response is actually issued.

### 22.4 Success + Login Failure

Triage starts with **SP verification and application pipeline**: signature, trust, issuer, audience, subject, time, correlation, decryption, principal mapping. "Success" in IdP logs reflects only the IdP's perspective.

### 22.5 No Status

Failure occurred before any SAML Response existed: user closed tab, misdiagnosed CORS, third-party cookies, DNS, TLS, IdP HTML error, ACS 404/405, WAF block. Never fabricate a status like AuthnFailed in reports.

## 23. Cookie / RelayState Errors Often Misattributed to the IdP

In SP-initiated SSO, Spring Security by default may store AuthnRequest in HTTP session. Browsers coming from the IdP usually **cross-site POST** SAMLResponse to the ACS. With `SameSite=Lax` or `Strict` cookies, the browser may withhold the SP cookie on that POST per policy, causing Spring to lose request correlation.

Symptoms:
- Browser POSTed the response to the right ACS path.
- IdP audit records a successful authentication event.
- Spring SP cannot locate the saved request, hits `InResponseTo` mismatch, or treats it unexpectedly as unsolicited.
- SAML status may be Success yet SP rejects due to **missing local session/correlation state**.

Resolution steps:
1. Inspect `Set-Cookie` before redirect and `Cookie` on ACS POST in a test environment.
2. Check SameSite/Secure/Domain/Path and public HTTPS URL/reverse proxy.
3. Check sticky sessions/Spring Session/distributed store in multi-replica deployments.
4. Pick a cookie policy suited to cross-site SSO while preserving CSRF/login fixation defenses.
5. Never drop `InResponseTo` or allow all unsolicited responses just to get login working again.

This is a **transaction receipt/verification failure at the SP/browser**, with no evidence the IdP returned `AuthnFailed`.

## 24. Mapping / Authorization Errors After SP Accepted SAML

A user has a verified SAML assertion, Spring built `Authentication` in SecurityContext, and then the user requests:

~~~http
GET /portal/admin HTTP/1.1
Host: app.example.org
~~~

The application returns:

~~~http
HTTP/1.1 403 Forbidden
~~~

This can be Spring Security authorization failing due to missing authority, unconfigured role mapping, unprovisioned user, or disallowed tenant policy. There is no default reason to blame `Responder` at the IdP.

Explanation:
- **Authentication:** IdP + SP determine who the user is.
- **Authorization:** the application decides what the user may do.
- By default, Spring Security's SAML provider may grant a baseline authority for authenticated users; it **does not automatically map every IdP group into an admin role**.
- An `AttributeStatement` containing groups/roles not normalized/trusted per policy is insufficient to grant arbitrary privileges.
- If an error occurs inside `UserDetailsService` or a post-validation custom converter, it can still route through authentication failure. Distinguish **custom local mapping** from IdP protocol status.

Operations teams should check `Authentication.isAuthenticated()`, authorities, and route rules **without logging raw NameID/attributes**.

## 25. Logging and Metrics by Cause Layer

Do not use a single `saml_error_total` metric and assume every failure means "IdP down". A useful taxonomy:

| Metric/log group | Definition | Example safe labels |
| --- | --- | --- |
| `idp_saml_status_reported` | Actually observed non-Success SAML StatusCode | topCode=`Responder`, subCode=`NoPassive`, trust=`verified/unverified` |
| `sp_saml_validation_failed` | Local provider/validation rejected Response | category=`signature/issuer/audience/time/correlation/decryption/other` |
| `saml_transport_failed` | No valid Response reached ACS due to HTTP/route/network | stage=`idp/acs/browser/proxy` |
| `app_authorization_denied` | Authenticated yet lacked route permission | routeGroup=`admin/orders/other` |
| `saml_login_success` | SP created Authentication after validation | bounded-cardinality registrationId |

**Never put NameID, email, SAMLResponse, random RelayState, or session IDs into metric labels**: they cause high cardinality and personal-data exposure. Request details can live in access-restricted logs under correlation ID/timestamp and a retention policy.

Distinguish `reported` from `verified`. A raw status observed when the signature is invalid must not be tallied as **a confirmed IdP decision**. Significant validation errors can indicate misconfiguration, cert rollover, or an attack; never automatically assume user error.

## 26. Rules for Displaying Errors to End Users

Users need next steps, not SAML stack traces:

- When IdP reports `NoPassive` in a silent flow: you can show "Unable to sign in automatically; please select Sign In to continue", then issue a **new interactive request** if permitted.
- When IdP reports `NoAuthnContext`: show "Unable to meet the service's authentication requirements; contact support", without disclosing MFA policy details.
- When SP rejects signature/issuer/audience: show a generic error with a support code; do not reveal key/trust-anchor details to the client.
- When authenticated user gets 403: show "Your account does not currently have permission to access this resource"; direct privilege requests through proper workflow.
- When IdP returns no Response: show retry or support guidance after checking network status; **do not claim "wrong account" without evidence**.

Avoid every security-breaking quick fix:
- `csrf.disable()` across the entire app;
- Removing XML signature verification;
- Trusting any certificate appearing in the response;
- Dropping Issuer/Audience/Recipient/InResponseTo validation;
- Unconditionally accepting expired assertions;
- Setting clock skew to infinity;
- Creating `Authentication` solely because status = Success;
- Logging or rendering raw unsanitized `StatusMessage`.

## 27. Exercises with Answers

**Exercise 1.** Browser receives HTTP 200 from IdP; the page renders a POST form with `SAMLResponse`, and the XML inside has `Responder / NoPassive`. Does HTTP 200 prove login succeeded?

**Answer:** no. 200 here is the HTTP response delivering the form; protocol status says the IdP reported it cannot satisfy passive auth. The SP must not grant Authentication from an error Response.

**Exercise 2.** IdP audit records Success, browser POSTs SAMLResponse to ACS, Spring logs "invalid signature". Where is this error?

**Answer:** **SP verification failure** (trust/signature), even though the IdP reported protocol success. Check signing cert/metadata/cert rotation/payload and policy; do not alter StatusCode.

**Exercise 3.** XML has top-level `Requester` and nested `InvalidNameIDPolicy`. Did the user type the wrong password?

**Answer:** no evidence of that. That is the IdP reporting an unsuitable NameID request/policy; inspect AuthnRequest NameIDPolicy and IdP capabilities.

**Exercise 4.** SAML Response reports Success and valid signature, yet audience is another SP. Should Authentication be created?

**Answer:** no. The assertion was not issued for the current SP; **SP audience validation fails**. A signature does not make a wrong audience right.

**Exercise 5.** Login succeeds yet `GET /admin` returns HTTP 403. How should this be classified?

**Answer:** if Authentication was genuinely created and remains valid, this is an **authorization/application failure**. Inspect role mapping/permissions; do not blame IdP status by default.

**Exercise 6.** `Saml2AuthenticationException` has `getSaml2Error().getErrorCode()`. Can all such values be treated as IdP OASIS StatusCodes?

**Answer:** no. Those are Spring framework error codes, which can describe local failures. Only call it an IdP status with XML SAML status evidence from the responder and proper trust evaluation.

**Exercise 7.** Browser never POSTs SAMLResponse to ACS; IdP returned HTML 500. Can you conclude top-level Responder?

**Answer:** no. There is no Response containing a SAML StatusCode; investigate HTTP/network/IdP service first.

**Exercise 8.** User just logged in at IdP, yet Spring cannot find `InResponseTo`. Should correlation be disabled?

**Answer:** no. Check SP session cookie SameSite/Secure, request repository, browser, and multi-node state. Correlation is an important defense against login fixation/replay.

**Exercise 9.** Raw XML contains `Responder / AuthnFailed` yet signature/issuer are invalid. Is "IdP rejected the user" certain?

**Answer:** uncertain. The status value is an **untrusted observation**; what is certain is that **the SP could not verify the response**. Check source/IdP logs before attributing the cause.

**Exercise 10.** IdP reports `NoAuthnContext`, yet application logs also show "principal missing". Which should be checked first?

**Answer:** if trusted status evidence exists, the IdP reported inability to satisfy RequestedAuthnContext; do not expect a principal from a failed response. Also verify how the SP handles status rather than forging a dummy subject to get past.

**Exercise 11.** Request from SP to IdP is blocked by WAF with HTTP 414 due to URL length. What error class is this?

**Answer:** HTTP/transport/binding error before the IdP issues any SAML Response; no top-level status exists to report. Inspect HTTP-Redirect URL limits and consider HTTP-POST AuthnRequest.

**Exercise 12.** SP has multiple IdP registrations; response arrives at the right ACS yet issuer is IdP B while SP picked registration A. Is this IdP "AuthnFailed"?

**Answer:** no. This is an **SP registration/issuer trust mismatch** or federation misconfiguration; do not arbitrarily switch registrations based on an unverified issuer.

## 28. SAML Incident Handoff Checklist

- [ ] Confirm exact public SP/ACS URL, registrationId, and approved IdP issuer.
- [ ] Establish HTTP timeline: whether browser actually POSTed SAMLResponse to ACS.
- [ ] Do not equate HTTP status, XML StatusCode, Java exceptions, and 403 authorization.
- [ ] If Response exists, read **top-level SAML status**, plus nested subcode if present; do not require subcodes.
- [ ] Clearly label observed status as **verified** or **unverified** per trusted source.
- [ ] Check whether the IdP issued a successful Assertion or only returned an error Response.
- [ ] Even with top-level Success, verify signature, issuer, destination, audience, expiry, subject, replay, correlation, and decryption.
- [ ] When Spring reports `Saml2AuthenticationException`, store **framework** error code separately from **protocol** status.
- [ ] For post-Authentication 403s, inspect role/authority/tenant/route rather than lumping under IdP failure.
- [ ] Evaluate SameSite/Secure cookies, request repository, and session on InResponseTo mismatches.
- [ ] Cross-check IdP audit logs before concluding IdP policy/account/MFA causes.
- [ ] Never display or log raw StatusMessage, SAMLResponse, assertions, cookies, RelayState, or personal data.
- [ ] Failure handler provides only generic message/support code, never disabling validation.
- [ ] Assign next action to the right owner: IdP team, SP/security team, network team, or application team.

## 29. Conclusion

**Errors reported by the IdP via SAML StatusCode and verification errors detected by the Spring Security SP are two distinct information layers.** A Response can carry `Responder / NoPassive` to report the IdP could not meet the request; or carry `Success` yet still be rejected by the SP for invalid signature, issuer, audience, timing, or correlation. Without a POSTed Response, **no SAML status code may exist** to read; a post-login 403 can likewise be pure authorization.

For evidence-backed investigation, always combine **HTTP trace + protocol status (with trust assessment) + SP verification logs + IdP audit + application authorization**. Keep all security checks intact and present failures to users with appropriate messages without leaking sensitive SAML data.

### Official Documentation

1. OASIS — SAML V2.0 Core, Section 3.2.2 `StatusResponseType`, `Status`, `StatusCode`, and top/sub code sets: https://docs.oasis-open.org/security/saml/v2.0/saml-core-2.0-os.pdf
2. OASIS — SAML V2.0 Approved Errata (clarifies second-level StatusCode is optional): https://docs.oasis-open.org/security/saml/v2.0/sstc-saml-approved-errata-2.0.pdf
3. Spring Security — SAML 2.0 Login Overview, filters, and provider validation: https://docs.spring.io/spring-security/reference/servlet/saml2/login/overview.html
4. Spring Security — Authenticating SAML Responses: https://docs.spring.io/spring-security/reference/servlet/saml2/login/authentication.html
5. Spring Security 6.5 — Authenticating SAML Responses (reference for OpenSAML 4): https://docs.spring.io/spring-security/reference/6.5/servlet/saml2/login/authentication.html
6. Spring Security API — `Saml2AuthenticationException`: https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/saml2/provider/service/authentication/Saml2AuthenticationException.html
7. Spring Security API — `Saml2Error` (framework local error code): https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/saml2/core/Saml2Error.html
8. Spring Security — Producing AuthnRequests / request repository: https://docs.spring.io/spring-security/reference/servlet/saml2/login/authentication-requests.html
