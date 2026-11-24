# Saml2WebSsoAuthenticationFilter and Receiving SAMLResponse

When a user logs in via **SAML 2.0 Web Browser SSO**, the Identity Provider (IdP) authenticates the user and returns a **SAML Response** to the Service Provider (SP) application. In Spring Security Servlet, the component receiving this result is **`Saml2WebSsoAuthenticationFilter`**. It serves as the bridge from the HTTP callback at the **Assertion Consumer Service (ACS)** to Spring Security's `AuthenticationManager`.

Understanding the responsibility boundary is essential: **the filter routes and kicks off authentication, the converter extracts payload/request context, and the authentication provider performs SAML verification**. A browser submitting a `SAMLResponse` field does not prove identity; only after verification steps succeed does the application obtain a trusted `Authentication` to establish a session and enforce access control.

## 1. Two Filters for Two Stages of Login

In Spring Security, SAML login has a **request stage** and a **response-handling stage**:

| Stage | Component | Typical Path | Responsibility |
| --- | --- | --- | --- |
| Start SSO | `Saml2WebSsoAuthenticationRequestFilter` | `/saml2/authenticate/{registrationId}` | Generates `AuthnRequest`, saves pending request, sends to IdP SSO endpoint via supported binding. |
| Receive SSO result | **`Saml2WebSsoAuthenticationFilter`** | **`/login/saml2/sso/{registrationId}`** | Receives callback with `SAMLResponse`, converts to `Saml2AuthenticationToken`, invokes `AuthenticationManager`. |

The first path is where the **SP initiates** the outbound request to the IdP; the second is where the **SP receives** the response from the IdP. In SP metadata, the second path must be reflected in `AssertionConsumerService/@Location`. Newer Spring Security versions may also support ACS URLs without `registrationId`; when changing endpoints or registration lookup, verify against the documentation and configuration of your running version.

**Do not confuse the names:** `Saml2WebSsoAuthenticationRequestFilter` contains *Request* and sends AuthnRequest; `Saml2WebSsoAuthenticationFilter` processes the *Response*. They are not two names for the same filter.

## 2. Complete Processing Chain: From Browser to SecurityContext

~~~text
                  SP / Spring Security                      IdP
                        |                                   |
Browser -- GET /private --> AuthorizationFilter            |
                        | unauthenticated                   |
                        v                                   |
              ExceptionTranslationFilter                    |
                        |                                   |
                        v                                   |
        Saml2WebSsoAuthenticationRequestFilter              |
                        | builds & saves AuthnRequest       |
                        +----- AuthnRequest --------------->|
                                                            | authenticate
Browser <---------------- HTML form (SAMLResponse) ---------+
                        |
                        | POST to SP ACS
                        v
       Saml2WebSsoAuthenticationFilter
                        |
                        v
          Saml2AuthenticationTokenConverter
          - extracts SAMLResponse from HttpServletRequest
          - finds trusted RelyingPartyRegistration
          - links saved AuthnRequest when present
                        |
                        v
              Saml2AuthenticationToken
                        |
                        v
               AuthenticationManager
                        |
                        v
          OpenSAML AuthenticationProvider
          - parses/decrypts and verifies signature
          - issuer, destination, audience, validity window
          - InResponseTo, subject confirmation, replay
                        |
             +----------+------------+
             |                       |
          failure                 success
             |                       |
       failure handler      Saml2Authentication
       no session issued       SecurityContext
                                     |
                           success handler / SP session
                                     |
                              protected resource
~~~

This is a **responsibility diagram**, not a rigid layout of every filter or handler in a particular Spring Security release. Exact placement depends on `SecurityFilterChain`, authentication success/failure handlers, repositories, and library version. With a default web app setup, upon success Spring Security typically redirects the user back to their prior request via a saved-request success handler; do not assume the browser will always receive HTTP 200 directly from the ACS.

### 2.1. Sample HTTP Requests

The user starts at a resource requiring login:

~~~http
GET /private HTTP/1.1
Host: sp.example.org
~~~

The SP redirects to the IdP with `SAMLRequest` and transaction state; the IdP authenticates and sends an HTML form POSTing to the ACS. Structurally, the incoming message to the SP looks like:

~~~http
POST /login/saml2/sso/corporate HTTP/1.1
Host: sp.example.org
Content-Type: application/x-www-form-urlencoded
Cookie: JSESSIONID=...

SAMLResponse=<BASE64_ENCODED_SAML_XML>&RelayState=<TRANSACTION_STATE>
~~~

The data above **only illustrates form/field names**; values inside `<...>` are not usable login responses. When using the **HTTP-POST binding**, `SAMLResponse` is SAML XML encoded in Base64 per binding rules; **Base64 is neither encryption nor signature protection**. Real responses remain subject to profile rules for XML, signatures, issuer, expiration, and correlation fields. Never paste `SAMLResponse` contents, session cookies, NameIDs, or assertions containing personal data into public debugging tools.

`RelayState` may travel alongside the response, yet it is **not a credential**. The SP must correlate `RelayState` with protected transaction state and `InResponseTo` with the pending request. In multi-IdP apps, `registrationId` in the URL is only a **controlled routing hint**, not proof that the incoming XML can be trusted.

## 3. What Is the Filter Responsible For vs. Not Responsible For?

`Saml2WebSsoAuthenticationFilter` extends `AbstractAuthenticationProcessingFilter`. Consequently, it participates in Spring Security Servlet mechanics: matching authentication requests, triggering authentication processing, handling success/failure, and updating `SecurityContext`.

| Action | Typical Responsible Component |
| --- | --- |
| Does the request match the **ACS login processing URL**? | Request matcher of **`Saml2WebSsoAuthenticationFilter`**. |
| Reading HTTP `SAMLResponse` parameters, finding matching registration? | `Saml2AuthenticationTokenConverter` used by the filter. |
| Finding saved `AuthnRequest` to know original transaction? | `Saml2AuthenticationRequestRepository`, working with converter/filter. |
| Packaging info to verify into `Saml2AuthenticationToken`? | Authentication converter. |
| Deciding if assertion is valid on signature, issuer, audience, time, subject? | `OpenSamlXAuthenticationProvider` and corresponding validators. |
| Producing authenticated `Authentication` result? | Authentication provider. |
| Persisting authentication state in app and redirecting per policy? | `AbstractAuthenticationProcessingFilter` and Spring Security session/success strategies. |
| Deciding if user may view reports of another tenant? | Application **Authorization**, independent of SAML login. |

**The filter does not declare XML valid merely because the HTTP POST succeeded.** Never write a `@PostMapping("/login/saml2/sso/...")` that manually calls `Base64.decode` and mints a session directly; doing so skips signature checks, assertion conditions, and transaction management.

## 4. Step 1 — Receiving the Callback at the ACS

### 4.1. Matcher and HTTP-POST Binding

In standard SAML 2.0 login setups, the IdP delivers `Response` via **HTTP-POST binding** to the ACS. Spring Security uses a login-processing endpoint like:

~~~text
https://sp.example.org/login/saml2/sso/corporate
~~~

Here `corporate` is the **registrationId** of the SP/IdP pair configured in the application. The public endpoint must match `AssertionConsumerService.Location` registered at the IdP and the URL actually handled at runtime.

If the IdP POSTs to `/auth/saml/acs` while the filter only listens on `/login/saml2/sso/{registrationId}`, the request skips the filter and hits 404, 403, or another handler depending on the chain. Fix properly by aligning **login processing URL, ACS Location/metadata, and IdP registration**.

### 4.2. CSRF Tokens and Cross-Site Callbacks

With SAML HTTP-POST binding, the IdP submits the form; it does not possess a CSRF token generated by the SP for ordinary forms. Spring Security `saml2Login` configures a CSRF exemption **specifically for the Web SSO processing endpoint** so POSTs are accepted. That exemption is narrowly scoped; **never disable CSRF for the entire application**.

Callback security still rests on **SAML signatures + assertion conditions + `AuthnRequest`/session transaction + anti-replay**. `SameSite` cookie behavior is crucial because IdP → SP is often a cross-site POST: if the browser withholds the session cookie at the ACS, Spring Security will not find the original `AuthnRequest`. Configure sessions/cookies for the deployment context and test in real browsers; **never drop the `InResponseTo` check just to bypass login failures**.

### 4.3. Input Requirements

Per binding/profile, the callback must contain a valid `SAMLResponse` and resolve to a configured registration. If fields are missing, Base64 is malformed, XML is invalid, transaction data is missing, or no registration matches, authentication must **fail safely**. Never build a fallback like "any XML with a NameID logs the user in".

## 5. Step 2 — Saml2AuthenticationTokenConverter Builds the Authentication Request Token

Spring Security uses **`Saml2AuthenticationTokenConverter`** to convert HTTP inputs into a **`Saml2AuthenticationToken`**. At this stage the token is an **untrusted authentication request**, not a logged-in `Saml2Authentication`.

Conceptually, the converter:

1. Extracts `SAMLResponse` from the request and handles it per supported binding.
2. Locates the matching **`RelyingPartyRegistration`**: the configured relationship between SP entityID, IdP entityID, ACS, and verification keys.
3. Loads relevant `AuthnRequest` context from `Saml2AuthenticationRequestRepository` when SP-initiated.
4. Constructs `Saml2AuthenticationToken` holding the SAML message and partner config needed by the verification provider.

**`RelyingPartyRegistration` must never be derived from unverified XML as a new trust source.** With multiple IdPs, the converter can use pending request info, `registrationId` in the URL, and—in versions that support it—the Response issuer to *look up an already-configured registration*. Finding it **does not mean trusting a self-asserted issuer**; the authentication provider must still verify the issuer and signature against that registration's keys.

### 5.1. Registration Identifiers and Endpoints

Example:

~~~text
registrationId: corporate
SP entityID:    urn:example:sp:portal
IdP entityID:   urn:example:idp:corporate
SP ACS:         https://sp.example.org/login/saml2/sso/corporate
IdP SSO:        https://idp.example.org/saml/sso
~~~

`corporate` is purely an **internal Spring Security config key**, not a SAML NameID and not necessarily identical to the SP/IdP entityID. If the application supports two tenants with two distinct IdPs, registration selection must come from policy/transaction state, then verify against the IdP's true trust anchor.

### 5.2. Relationship with AuthnRequestRepository

At SSO start, `Saml2WebSsoAuthenticationRequestFilter` saves an `AbstractSaml2AuthenticationRequest` into `Saml2AuthenticationRequestRepository`. By default in common Spring Security setups this is `HttpSessionSaml2AuthenticationRequestRepository`: the pending request is bound to `HttpSession`.

When the ACS receives `SAMLResponse`, the filter/converter uses the repository to retrieve the saved request and check `InResponseTo` and transaction details via the provider/validators. If the response belongs to another browser session, expired, was already used, or the request is gone, never invent a new transaction from `RelayState`. **IdP-initiated/unsolicited SSO** (no prior AuthnRequest) is an explicit integration choice with its own policy—never an ad-hoc fallback when SP-initiated login breaks.

When deploying multiple Spring Boot instances, ensure a shared session store or appropriate routing: callbacks hitting another instance without transaction state can be rejected. Never sacrifice correlation merely to mask a sticky-session bug.

## 6. Step 3 — AuthenticationManager Passes the Token to the OpenSAML Provider

After the converter runs, `Saml2WebSsoAuthenticationFilter` invokes `AuthenticationManager#authenticate(...)` with `Saml2AuthenticationToken`. Typically a `ProviderManager` selects the provider capable of handling this token type.

**Version differences:** Spring Boot 3.3 / Spring Security 6.3 applications typically use **`OpenSaml4AuthenticationProvider`**; newer Spring Security generations use **`OpenSaml5AuthenticationProvider`**. Check your actual dependencies before importing classes or writing custom validators. Both share the same role: authenticating SAML against a trusted registration; detailed configuration APIs differ between the two generations.

### 6.1. What Must the Provider Verify?

Upon receiving the callback, the message/identity claims from the browser are **untrusted**. Critical validation groups include:

| Check Group | Meaning | Example Rejected Failure |
| --- | --- | --- |
| XML parsing and structure | Message is well-formed SAML Response/Assertion matching supported profile; XXE-safe parser. | Malformed XML, unexpected elements, invalid format. |
| Signature and trusted cert | Verifies signature on the **exact element consumed** using IdP's registered key; guards against XML signature wrapping. | Invalid signature or signed by key outside trust store. |
| `Response@Status` | IdP reports success or failure; only success status creates a session. | `Responder`, `AuthnFailed`, or non-success status. |
| `Issuer` | Matches the configured IdP. | Assertion comes from an issuer differing from registration. |
| `Destination` | Response targets the matching **ACS URL**. | Response intended for another URL. |
| `AudienceRestriction` | Assertion is permitted for the current **SP entityID**. | Token intended for a different SP. |
| `Conditions@NotBefore/NotOnOrAfter` | Assertion is within its validity window. | Expired or not yet valid. |
| `SubjectConfirmationData` | Bearer confirmation matches `Recipient`, `InResponseTo`, and expiration. | Recipient differs from ACS, expired confirmation. |
| Transaction correlation | `InResponseTo` points to the pending AuthnRequest of the initiating session. | Login CSRF or response from another transaction. |
| Replay and reuse limits | Prevents accepting old assertions/responses repeatedly per profile/config. | Replay of an already-consumed assertion. |
| Decryption (if configured) | Decrypts `EncryptedAssertion`/`EncryptedAttribute` using matching SP private key. | Missing private key or decryption failure. |

**No single check replaces the others:** a valid signature does not mean audience is right; a matching ACS does not mean the assertion is unexpired; having a `NameID` does not mean the user is authorized for any resource.

In SAML, `NotOnOrAfter` is an **exclusive** time bound. `SubjectConfirmationData@NotOnOrAfter` can expire earlier than `Conditions@NotOnOrAfter`; if confirmation has expired, do not accept merely because Conditions remain valid. Clock skew tolerance should be small and bounded, with IdP/SP clocks synchronized.

### 6.2. What Does a Response Contain?

A SAML Response returned to the ACS typically looks structurally like (this is **not** complete or signed XML):

~~~xml
<samlp:Response
    xmlns:samlp="urn:oasis:names:tc:SAML:2.0:protocol"
    xmlns:saml="urn:oasis:names:tc:SAML:2.0:assertion"
    ID="_response-42"
    Version="2.0"
    IssueInstant="2026-11-07T03:00:00Z"
    Destination="https://sp.example.org/login/saml2/sso/corporate"
    InResponseTo="_request-17">
  <saml:Issuer>urn:example:idp:corporate</saml:Issuer>
  <samlp:Status>
    <samlp:StatusCode Value="urn:oasis:names:tc:SAML:2.0:status:Success"/>
  </samlp:Status>
  <saml:Assertion ID="_assertion-22" Version="2.0"
                  IssueInstant="2026-11-07T03:00:00Z">
    <saml:Issuer>urn:example:idp:corporate</saml:Issuer>
    <!-- Subject, SubjectConfirmation, Conditions, signature,
         AuthnStatement, AttributeStatement ... -->
  </saml:Assertion>
</samlp:Response>
~~~

The condensed XML above merely shows where `Response` and `Assertion` sit. It **cannot authenticate** because it lacks signatures, profile-required conditions, and subject confirmation data. In practice, the IdP may sign Response, Assertion, or both per configuration/profile; the provider must verify the **exact elements and content consumed**, never assuming an entire document is safe just because a `Signature` tag appears somewhere.

**The HTTP form field `SAMLResponse` differs from the XML element `<samlp:Response>`.** The filter receives the form field and delegates XML processing through the converter/provider; never expose an unverified assertion to application logic before authentication finishes.

## 7. Step 4 — Creating Saml2Authentication and the Application Session

When the provider accepts the Response, it creates **`Saml2Authentication`** (an authenticated `Authentication`). The resulting object typically contains:

- **Principal** of type `Saml2AuthenticatedPrincipal`, holding the identifier name and processed attributes.
- **`name`/NameID** of the user per mapping policy; NameID may not be an email and can vary by format/IdP.
- **GrantedAuthorities**. With the default provider in common versions, this typically includes `ROLE_USER`; **groups/roles in `AttributeStatement` do not automatically turn into business permissions**.
- SAML Response info via the corresponding API; this data can be sensitive and should not be printed/logged raw.

The filter and framework then execute success logic: updating `SecurityContext`, persisting authentication state via the configured `SecurityContextRepository`/session strategy, and invoking the success handler or continuing the chain as configured. The user is typically redirected back to the pre-login page (saved request). **An Assertion expiring after a few minutes does not automatically force the SP session cookie to expire at that instant**: SP session lifetime/logout is a separate policy.

### 7.1. Accessing the Principal in a Spring MVC Controller

File `src/main/java/example/federation/CurrentUserController.java` in a Spring Boot app configured with SAML login:

~~~java
package example.federation;

import java.util.Map;
import org.springframework.security.core.annotation.AuthenticationPrincipal;
import org.springframework.security.saml2.provider.service.authentication.Saml2AuthenticatedPrincipal;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class CurrentUserController {

    @GetMapping("/me")
    public Map<String, String> me(
            @AuthenticationPrincipal Saml2AuthenticatedPrincipal principal) {
        return Map.of("principalName", principal.getName());
    }
}
~~~

`/me` must be protected by authorization (e.g., `.anyRequest().authenticated()`). The example returns only the **currently logged-in user's principal name**; do not dump all SAML attributes or responses in an API. This Java code belongs to a Spring Boot project with matching dependencies and **cannot be compiled/run with standalone JDK `javac`**.

In services, map a **stable, issuer/tenant-scoped** identifier to an internal account and verify active status, roles, and resource permissions. Do not use email or display name as a sole unique key if it can change or be reused. A user with a successful SAML login can still receive 403 due to missing resource permissions.

## 8. Spring Boot and Spring Security Setup

Simple example for a **Servlet** app using Java 17+ and compatible Spring Boot/Spring Security. Core libraries:

~~~gradle
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-security'
    implementation 'org.springframework.security:spring-security-saml2-service-provider'
}
~~~

This is the **`dependencies` snippet of `build.gradle`** in a project with Spring version management and required repositories configured (OpenSAML may require an appropriate repository). Do not treat it as a standalone build file.

Configuration `src/main/resources/application.yml` using **mock IdP metadata** to define one registration:

~~~yaml
spring:
  security:
    saml2:
      relyingparty:
        registration:
          corporate:
            assertingparty:
              metadata-uri: https://idp.example.org/metadata
~~~

The URL above is illustrative. Running for real requires valid IdP metadata, established signing/verification trust credentials, accurate public base URL, and matching registration; if the IdP requires signed `AuthnRequest`s, the SP must have matching signing keys/certificates.

Filter chain config in `src/main/java/example/federation/SecurityConfig.java`:

~~~java
package example.federation;

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
        http.authorizeHttpRequests(auth -> auth
                .requestMatchers("/public/**", "/error").permitAll()
                .anyRequest().authenticated())
            .saml2Login(Customizer.withDefaults());
        return http.build();
    }
}
~~~

Once integration prerequisites are complete, Spring Security registers the SAML request/response components without needing to write a manual `Saml2WebSsoAuthenticationFilter` bean. `Saml2WebSsoAuthenticationFilter` handles ACS callbacks, while `Saml2WebSsoAuthenticationRequestFilter` sends AuthnRequests.

**Do not call the sample endpoint with arbitrary Base64 via `curl` to "test login success"**: a valid `SAMLResponse` requires proper signature/issuer/conditions and an established trust relationship. Real testing requires a test IdP or properly signed and correlated SAML test fixtures.

### 8.1. When You Need to Change the ACS Processing URL

Suppose the application wants the IdP to POST SAML Responses to `/saml/acs/corporate`. Update in sync:

1. Configure `saml2Login(...loginProcessingUrl(...))` so the **filter matcher** handles that path.
2. Configure `RelyingPartyRegistration.assertionConsumerServiceLocation` or the corresponding SP property/metadata.
3. Update the **ACS URL on the IdP side** to match the new public URL.
4. If omitting `{registrationId}` from the URL, ensure the converter/resolver still finds the **right** registration; never let an issuer in the request decide trust on its own.
5. Test the ACS URL in generated metadata, `Response@Destination`, `SubjectConfirmationData@Recipient`, and SP-initiated correlation.

DSL snippet when matching registration/ACS is already configured:

~~~java
.saml2Login(saml2 -> saml2
    .loginProcessingUrl("/saml/acs/corporate"))
~~~

This is an **illustrative chain snippet, not a standalone Java class**. When configuring a custom URL, note that `Saml2AuthenticationTokenConverter` APIs in some versions expect `{registrationId}` in the path: ensure lookup/resolver rules remain trustworthy. Never change only one side, as `Destination`/`Recipient` and ACS Location will stop matching.

## 9. Customize the Right Layer While Keeping Default Validators

SAML login often requires mapping IdP details to app accounts and roles, or adjusting failure behavior. Pick the **extension point matching the responsibility**:

| Need | Suitable Extension Point | What to Preserve |
| --- | --- | --- |
| Change how IdP/registration is chosen | Version-appropriate `RelyingPartyRegistrationResolver` or `AuthenticationConverter`. | Use only trusted configured registrations; prevent IdP mix-up. |
| Change `AuthnRequest` store | `Saml2AuthenticationRequestRepository`. | Bind transaction to browser session, TTL, single use. |
| Adjust clock skew, issuer/conditions validation | Version-appropriate OpenSAML provider validator. | Invoke/keep default validators and widen skew minimally. |
| Decrypt encrypted assertion/attribute | Provider credentials/decrypter. | Use SP private key; never leak plaintext to logs. |
| Map NameID/attributes to principal and authorities | Response authentication converter or post-auth user mapper. | Map only from verified assertions; enforce tenant/permissions properly. |
| Post-login redirect or friendly errors | Authentication success/failure handler. | Never expose assertions/tokens in URLs or messages. |
| Resource, tenant, row-level permissions | `authorizeHttpRequests`, method security, business authorization service. | SAML login only verifies identity; it never replaces business authorization. |

**Never replace the entire `AuthenticationManager` with `NameID != null` or a manual XML decoder.** A custom manager would have to replicate all SAML checks, which is highly error-prone. When you only need an extra mapping/validation step, extend the official provider, **delegate to built-in verification logic**, and then apply application rules.

### 9.1. Differences Between OpenSaml4 and OpenSaml5

In Spring Security 6.3, integration docs typically reference `OpenSaml4AuthenticationProvider` with its corresponding converter/validator hooks. In Spring Security 7.x, newer docs use `OpenSaml5AuthenticationProvider`, with partially changed validation/configuration APIs. Therefore, do not copy an `OpenSaml5AuthenticationProvider` customization snippet into a 6.3 project assuming it compiles; verify your dependency version and use the matching API/validators. **The filter → converter → manager → provider → Authentication flow remains the stable principle**.

## 10. Success, Failure, and HTTP Outcomes

### 10.1. Successful Login

General conditions: request hits the right ACS, trusted registration found, `SAMLResponse` valid per profile, transaction/session correlated properly, provider returns `Saml2Authentication`. The framework then sets the authentication context and runs the success handler. The user is typically sent back to their original URL. A callback POST **is not a REST endpoint "returning JSON with a JWT"** unless the application intentionally adds a separate post-auth layer.

### 10.2. Failed Login

Example causes: missing/corrupt `SAMLResponse`, mismatched issuer, invalid signature, unsuccessful response status, wrong audience/recipient/destination, expired assertion, missing session holding original request, `InResponseTo` mismatch, or untrusted IdP metadata.

When the authentication provider throws `AuthenticationException`, the filter runs the failure path: clears/prevents retaining invalid authentication per config and invokes the failure handler/entry point to notify or restart login. **Do not map every SAML error to a fixed 401, 403, or 500**; the HTTP status and redirect page depend on the configured failure strategy.

### 10.3. When the Filter Does Not Handle the Request

A request not matching the ACS matcher passes on to other filters. It may hit the authorization filter, a controller, 404, 405, or CSRF depending on routing. Thus a POST returning 403 does not always mean a bad SAML signature; the request **may never have reached the SAML filter**. To diagnose, first check URL, HTTP method, selected filter chain, and CSRF rules.

## 11. Operations and Diagnostics Checklist

| Symptom | Likely Cause | Safe Resolution |
| --- | --- | --- |
| IdP reports ACS URL not allowed. | Wrong URL in SP metadata/IdP registration. | Compare `AssertionConsumerService.Location` and public callback. |
| Browser POSTs `SAMLResponse` yet app returns 404. | No filter/handler matches path, or wrong context path. | Check `saml2Login`, ACS matcher, proxy, and servlet context. |
| POST gets 403 before SAML validation. | CSRF/matcher/another filter chain intercepted request. | Inspect chain and ACS-only CSRF exemption. |
| Cannot locate relying party registration. | Wrong `registrationId`, empty repository, mismatched converter lookup. | Check configured registrations, ACS path, resolver. |
| `InResponseTo` mismatch or missing AuthnRequest. | Lost cookie/session, multiple tabs, RelayState mismatch, wrong session callback. | Check correlation store, SameSite, TTL, shared multi-instance sessions. |
| Signature verification failed. | Wrong IdP certificate/metadata, key rotation, wrong signed element. | Check trust anchor and ensure signature is validated on the right object. |
| Destination or Recipient mismatch. | IdP POSTs to different host/scheme than declared ACS. | Check public HTTPS URL, proxy forwarded headers, ACS metadata. |
| AudienceRestriction mismatch. | IdP issued assertion for another SP entityID. | Compare configured SP entityID against assertion audience. |
| Assertion expired or not yet valid. | Clock skew, overly short TTL, slow callback. | NTP/UTC, expiration windows, reasonable clock skew; never widen indefinitely. |
| Login succeeds yet user lacks business roles. | Default grants only `ROLE_USER`; groups/attributes not mapped. | Configure verified mapping and check role/tenant in service. |
| Login succeeds then loops back to login. | `SecurityContext`/session cookie not persisted, bad cookie policy or session repo. | Check success handler, Secure/SameSite, session fixation, session store. |
| IdP has two tenants yet user lands in wrong tenant. | Wrong registration selected or identity mapping ignores tenant. | Bind issuer/registration/tenant to transaction and user mapping. |
| Debug shows NameID yet filter still fails. | NameID alone does not authenticate SAML. | Check status, signature, issuer, subject confirmation, audience, and replay. |

**Practical debug order:** 1) Did URL/method enter the filter? → 2) Did converter find the right registration/original request? → 3) At which step did provider reject? → 4) Did success handler/session persist? → 5) Did business authorization allow access? Log **error category, configured IdP registration ID, protected transaction/correlation ID, and UTC timestamp**; avoid logging raw `SAMLResponse`, XML with PII, cookies, private keys, or decrypted assertions.

## 12. Required Test Scenarios

| Test Case | Expected Result |
| --- | --- |
| SP-initiated login, validly signed `SAMLResponse`, right ACS, right `InResponseTo`. | Authentication succeeds, valid principal, app session created per config. |
| POST to ACS with missing `SAMLResponse` or invalid Base64. | No authentication created. |
| Invalid assertion signature or untrusted signing key. | Rejected. |
| Issuer from unregistered IdP. | Rejected; never create registration from request. |
| Audience meant for another SP. | Rejected. |
| Destination/Recipient does not match published ACS. | Rejected. |
| `Conditions@NotOnOrAfter` passed or `SubjectConfirmationData` expired. | Rejected under bounded clock skew. |
| Response carries `InResponseTo` from another browser session. | Rejected as login CSRF/session swapping. |
| Replay same response/transaction after success. | Rejected by system's replay/correlation controls. |
| Callback lands on another node without shared session. | Not auto-accepted; diagnose session store. |
| Valid SAML data yet app account is disabled. | App access denied per lifecycle policy. |
| Successful login yet accessing another tenant's resource. | Denied at authorization regardless of valid SAML login. |

End-to-end tests should use a **test IdP or validly signed fixtures** in an environment configured with trusted keys. A unit test that only decodes XML or mocks `NameID` does not prove the full authentication chain operates securely.

## 13. Pitfalls to Avoid

1. **"The filter directly verifies every SAML signature."** The filter orchestrates; `AuthenticationManager`/OpenSAML provider verifies the message.
2. **"An IdP POST reaching the ACS means the user is logged in."** HTTP POST is untrusted input; it must pass every validator.
3. **"Base64 `SAMLResponse` is securely encrypted data."** Base64 is encoding, offering no confidentiality or tamper protection.
4. **"ACS URL, IdP SSO URL, and metadata URL are the same."** ACS receives responses, SSO receives AuthnRequests, metadata URL serves configuration XML.
5. **"Having NameID alone is enough to create an account/admin role."** NameID in unverified XML is untrusted; authorization must follow explicit policy.
6. **"`registrationId` in the URL proves the XML came from that IdP."** It routes to a registration; issuer/signature must be verified separately.
7. **"If `InResponseTo` fails, fall back to IdP-initiated."** Never downgrade policy without explicit approval.
8. **"Disable CSRF app-wide to accept SAML POSTs."** Only the ACS gets a targeted exemption; other routes still need CSRF per policy.
9. **"Changing ACS without updating metadata is fine."** Runtime ACS, SP metadata, and IdP configuration must stay aligned.
10. **"As long as an assertion is unexpired, it can be reused."** Anti-replay and transaction correlation are required; SP sessions have their own lifecycle.
11. **"Having `ROLE_USER` means every permission is granted."** Admin/tenant/resource permissions must be mapped and checked intentionally.
12. **"Copying provider code from newer Spring Security into an older version will work."** Class names and extension APIs change; stick to your exact version.

## 14. Summary and Self-Check Questions

**Flow summary at the right abstraction level:**

~~~text
HTTP POST /login/saml2/sso/{registrationId}
        |
Saml2WebSsoAuthenticationFilter
        |
Saml2AuthenticationTokenConverter
        | extracts SAMLResponse, finds RelyingPartyRegistration
        | restores AuthnRequest transaction when present
Saml2AuthenticationToken (unauthenticated)
        |
AuthenticationManager
        |
OpenSaml4 / OpenSaml5 AuthenticationProvider
        | signature, issuer, audience, ACS, conditions,
        | subject confirmation, InResponseTo, replay
Saml2Authentication (authenticated)
        |
SecurityContext + session/success handler
        |
Business authorization for subsequent requests
~~~

**Self-check:**

- **Which filter creates `AuthnRequest`?** `Saml2WebSsoAuthenticationRequestFilter`.
- **Which filter receives `SAMLResponse` at the ACS?** **`Saml2WebSsoAuthenticationFilter`**.
- **What converts the HTTP request into an authentication request token?** `Saml2AuthenticationTokenConverter`.
- **What validates the SAML Response/assertion?** `AuthenticationManager` invoking `OpenSamlXAuthenticationProvider` and its validators.
- **Why keep `AuthnRequest` in the session?** To bind the response to the transaction initiated by the right browser.
- **Why can a callback with a valid signature still fail?** Destination, recipient, audience, validity window, or `InResponseTo` may be wrong.
- **Does successful SAML login automatically grant admin rights?** No. Roles/permissions must be mapped and checked separately via authorization.

## References

- [Spring Security — SAML 2.0 Login Overview](https://docs.spring.io/spring-security/reference/servlet/saml2/login/overview.html)
- [Spring Security — Authenticating SAML Responses](https://docs.spring.io/spring-security/reference/servlet/saml2/login/authentication.html)
- [Spring Security — Producing AuthnRequests and Request Repository](https://docs.spring.io/spring-security/reference/servlet/saml2/login/authentication-requests.html)
- [Spring Security API — Saml2WebSsoAuthenticationFilter](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/saml2/provider/service/web/authentication/Saml2WebSsoAuthenticationFilter.html)
- [Spring Security API — Saml2AuthenticationTokenConverter](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/saml2/provider/service/web/Saml2AuthenticationTokenConverter.html)
- [Spring Security 6.3.4 API — OpenSaml4AuthenticationProvider](https://docs.spring.io/spring-security/site/docs/6.3.4/api/org/springframework/security/saml2/provider/service/authentication/OpenSaml4AuthenticationProvider.html)
- [OASIS SAML V2.0 Core](https://docs.oasis-open.org/security/saml/v2.0/saml-core-2.0-os.pdf)
- [OASIS SAML V2.0 Profiles — Web Browser SSO](https://docs.oasis-open.org/security/saml/v2.0/saml-profiles-2.0-os.pdf)
