# IdP-Initiated SAML 2.0 Login and Risks Without a Corresponding Request

> **Topic:** Spring Security – federation. **Group:** SAML2 Login Flow. This lesson focuses on **IdP-initiated SSO**, also known as **unsolicited SAML Response**, how it differs from **SP-initiated SSO**, why the absence of `AuthnRequest`/`InResponseTo` introduces distinct risks, and how to evaluate, integrate, and test it in a Spring Security application acting as Service Provider (SP).

## 1. Grasping the True Nature of IdP-Initiated SSO

In SAML 2.0 Web Browser SSO, there are two common ways to initiate login:

- **SP-initiated:** the user visits the SP app first. The SP creates an `AuthnRequest` and sends the browser to the IdP to authenticate; the IdP returns a `SAMLResponse` correlated to the pending request. The SP has grounds to verify **login was initiated by this exact browser/session**.
- **IdP-initiated:** the user starts at the IdP's portal or application dashboard, such as clicking a SaaS app tile. The IdP generates a `SAMLResponse` on its own and sends it via the browser to the SP's **Assertion Consumer Service (ACS)** **without the SP ever having sent an `AuthnRequest` beforehand**.

In the second case, the message is called an **unsolicited response**: "not requested beforehand" from the SP's perspective. That **does not automatically mean a forged message**; it can be signed by a valid IdP and carry a valid assertion. The risk is that the SP lacks evidence of **login intent** from the browser session receiving the response.

Roles to remember:

| Component | Responsibility |
|---|---|
| **Identity Provider (IdP)** | Authenticates users, enforces MFA/policies, creates and signs SAML Responses/Assertions per agreement |
| **Service Provider (SP)** | Verifies IdP origin, signature, audience, recipient, validity period, prevents replay, and grants app sessions/authorities |
| **Browser/User Agent** | Transports redirects or HTML form POSTs; never trusted as an assertion source |
| **ACS endpoint** | SP path receiving `SAMLResponse` over a binding (HTTP-POST in examples) |
| **`AuthnRequest`** | SAML request issued by SP carrying an ID so the IdP correlates the response in SP-initiated flows |
| **`InResponseTo`** | Identifier tying response/subject confirmation back to the original `AuthnRequest` ID on solicited responses |
| **`RelayState`** | Binding parameter carrying navigation state/destination; must be validated/sanitized per contract, especially in IdP-initiated |

**Do not confuse:** IdP-initiated **with no corresponding `AuthnRequest`** is completely different from **SP-initiated that lost its session**. If the SP previously sent an `AuthnRequest` yet lost request state/cookies, never "fix" it by treating that response as unsolicited and skipping correlation checks.

## 2. Both Flows Side by Side

### 2.1. SP-Initiated SSO (With Request Correlation)

~~~text
Browser (session B)           Spring Security SP                 IdP
    | GET /private                    |                             |
    +-------------------------------->|                             |
    |                                 | builds AuthnRequest ID=_req123
    |                                 | saves request/state bound to session B
    |<----------- Redirect SAMLRequest=_req123                      |
    +--------------------------------------------------------------->|
    |                                         auth/MFA               |
    |<------------------- Form POST SAMLResponse --------------------+
    +-- POST ACS -------------------->|                             |
    |                                 | Response.InResponseTo=_req123
    |                                 | SubjectConfirmationData
    |                                 |  .InResponseTo=_req123
    |                                 | verifies signature + conditions
    |                                 | matches request ID, session B
    |<------------------- creates login session if valid ------------|
~~~

**Protective value of `InResponseTo`:** if the IdP returns a response for `_req123` and the SP still holds the matching request in the **same browser/session**, the SP can verify the link between response and initiated login flow. This adds a layer against **login CSRF/session swapping** beyond signature/assertion validation. Comparing an `InResponseTo` string only against a globally stored ID **without browser/session binding** may still fall short of preventing CSRF.

### 2.2. IdP-Initiated SSO (Without Request Correlation)

~~~text
Browser                         IdP portal                  Spring Security SP
    | GET /my-apps                 |                               |
    +----------------------------->|                               |
    | Logged in / MFA at IdP       |                               |
    | Clicks "Portal SP"           |                               |
    |                              | builds new Response without   |
    |                              | AuthnRequest from SP          |
    |<-------- HTML form POST ------+                               |
    +----------------------- POST /login/saml2/sso/corporate ----->|
                                                                   |
                                     Checks sig/issuer/audience/   |
                                     recipient/time/replay & policy|
                                                                   |
    |<--------------------------- SP creates session if accepted --+
~~~

The SP can **know the IdP authenticated an identity**, yet **cannot prove via request correlation that the browser receiving the response actively requested a session under that identity**. Assuming the browser came from the IdP portal is an assumption about navigation flow, not cryptographic proof embedded in the response.

### 2.3. Quick Comparison

| Criterion | SP-initiated | IdP-initiated |
|---|---|---|
| Who initiates the SAML flow? | SP when user visits app | IdP/portal when user clicks app tile |
| `AuthnRequest` from SP? | **Yes** | **No** |
| Pending request ID in SP? | **Yes** if state intact | **No** |
| `Response.InResponseTo` | Points to issued request per profile | **Must be absent** in unsolicited |
| `SubjectConfirmationData.InResponseTo` | Points to original request per profile | **Must be absent** in unsolicited bearer confirmation |
| Login CSRF defense via request/session correlation? | Can be enforced strictly | **Lacks this same guarantee** |
| Signature, issuer, audience, recipient, time | **Mandatory checks** | **Still mandatory checks** |
| Assertion anti-replay | **Mandatory per profile** | **Mandatory per profile** |
| RelayState | Can tie to saved request | May be sent unsolicited by IdP; validate strictly |
| When to use? | Preferred for modern web apps controlling entrypoints | Only when required by IdP portal/legacy after risk review |

## 3. SAML 2.0 Standard Rules for Unsolicited Responses

**OASIS SAML 2.0 Profiles, §4.1.5** permits an IdP to initiate SSO by sending an unsolicited `Response` to an SP. However, very specific constraints apply:

1. **The Response must not contain `InResponseTo`.** For bearer `SubjectConfirmationData`, the `InResponseTo` attribute **must also be absent**.
2. When using metadata, the IdP should send the Response/artifact to the SP's **default-marked ACS** if none is otherwise specified.
3. Binding-specific `RelayState` may be used per prior IdP/SP agreement to indicate where to continue navigation or an internal post-login resource. The SP should define a **safe default destination** when RelayState is absent.
4. Standard Web Browser SSO checks still apply: signature/trust, confirmation, recipient, expiration, audience, replay protection, and SP policy. Lacking `AuthnRequest` **never permits skipping any other validation**.

**OASIS Errata 05** highlights **CSRF** risks because there is no guarantee the browser actively initiated the SAML flow at the SP. The errata also recommend SPs support **disabling unsolicited responses** when appropriate. With HTTP-POST, consumed assertions must be **protected by digital signatures**—either via per-Assertion signatures or a Response signature covering the assertion per errata; unsigned plain assertions are never allowed merely because a flow is IdP-initiated.

**Avoid semantic confusion:** "Absent `InResponseTo`" is **structurally valid** for an allowed unsolicited response; it does not mean "skip checking `InResponseTo` on every Response". Conversely, a response carrying an `InResponseTo` pointing to a nonexistent request must be treated as an **invalid solicited response**, never silently downgraded to unsolicited.

### 3.1. Illustrative XML: IdP-Initiated

The snippet below is a **condensed XML sketch**, with `...` standing in for required data and signatures; **it is not a valid SAML Response for an ACS**:

~~~xml
<samlp:Response
    xmlns:samlp="urn:oasis:names:tc:SAML:2.0:protocol"
    xmlns:saml="urn:oasis:names:tc:SAML:2.0:assertion"
    ID="_resp_unsolicited_01"
    Destination="https://sp.example.org/login/saml2/sso/corporate">
  <saml:Issuer>https://idp.example.org/issuer</saml:Issuer>
  <!-- ds:Signature, Status, and signed data placed per standard/profile -->
  <saml:Assertion ID="_assertion_unsolicited_01">
    <saml:Issuer>https://idp.example.org/issuer</saml:Issuer>
    <!-- ds:Signature or valid Response-level signature -->
    <saml:Subject>
      <saml:NameID>user-123</saml:NameID>
      <saml:SubjectConfirmation
          Method="urn:oasis:names:tc:SAML:2.0:cm:bearer">
        <saml:SubjectConfirmationData
            Recipient="https://sp.example.org/login/saml2/sso/corporate"
            NotOnOrAfter="2026-11-07T05:05:00Z"/>
      </saml:SubjectConfirmation>
    </saml:Subject>
    <saml:Conditions>...</saml:Conditions>
    <saml:AuthnStatement>...</saml:AuthnStatement>
  </saml:Assertion>
</samlp:Response>
~~~

In the IdP-initiated sample, both `Response` and bearer `SubjectConfirmationData` **omit the `InResponseTo` attribute**. `ID`, expiration, and user values are examples; sample timestamps are meaningless in real runtime execution.

### 3.2. Illustrative XML: SP-Initiated

For a response **with a corresponding request**, the correlation elements carry the `AuthnRequest` ID, for example:

~~~xml
<samlp:Response
    xmlns:samlp="urn:oasis:names:tc:SAML:2.0:protocol"
    ID="_resp_solicited_02"
    InResponseTo="_authnrequest_987"
    Destination="https://sp.example.org/login/saml2/sso/corporate">
  <!-- Issuer, Signature, Status, Assertion... -->
  <saml:Assertion ID="_assertion_solicited_02">
    <saml:Subject>
      <saml:SubjectConfirmation
          Method="urn:oasis:names:tc:SAML:2.0:cm:bearer">
        <saml:SubjectConfirmationData
            InResponseTo="_authnrequest_987"
            Recipient="https://sp.example.org/login/saml2/sso/corporate"
            NotOnOrAfter="2026-11-07T05:05:00Z"/>
      </saml:SubjectConfirmation>
    </saml:Subject>
  </saml:Assertion>
</samlp:Response>
~~~

This remains an **XML outline** lacking full namespace declarations and required elements. In real code, never match tags with regex or hand-roll XML validators; rely on OpenSAML and Spring Security to verify signatures/references and conditions.

## 4. What Vulnerabilities Does Lacking a Corresponding Request Create?

### 4.1. Login CSRF / Session Swapping

**Login CSRF** differs from CSRF on a money-transfer API call. Conceptual scenario:

1. An attacker holds a valid **attacker account** at the IdP; the IdP can issue a **validly signed** SAML Response for that account targeting the victim SP.
2. The attacker tricks the **victim's browser** into submitting that Response to the ACS within its validity window (e.g., via an auto-submitting form on another domain).
3. If the SP permits unsolicited responses and the response has not yet been consumed, the SP may create an **attacker session** in the victim's browser.
4. The victim appears logged in, yet is actually operating inside **the attacker's account**. If the victim enters data or performs actions, that data can land in the attacker's account, causing data leakage or business confusion.

This is **account/session confusion**. The attacker neither steals the victim's session nor forges the IdP's signature. The signature **is completely valid** because the IdP genuinely issued the response for the attacker. What is missing is **binding the response to the victim having actively initiated a login flow at the SP**.

**Subtlety:** a replay cache will not necessarily block the **very first** time a valid Response is submitted in the wrong browser. Replay caches only block **reuse** after an ID is consumed. Signatures and TLS likewise do not solve login CSRF: they protect origin/integrity and transport, not **this exact browser's login intent**.

### 4.2. Replay / Message Insertion

If the SP fails to track consumed assertion/response IDs, an attacker can try re-submitting the same `SAMLResponse` while still valid. For bearer assertions under Web Browser SSO HTTP-POST, the SP must prevent replay, at minimum storing **used assertion IDs** for as long as the assertion remains valid per `SubjectConfirmationData.NotOnOrAfter`; combine with Response ID checks and `OneTimeUse` when profile/policy specifies.

- The **replay cache** must be consistent across clustered SP instances so instance A does not reject while instance B accepts an already-used ID.
- Cache TTL must cover at least the protected validity window plus clock skew; avoid overly short TTLs that let nominally valid assertions be reused.
- Never treat Base64-encoding of `SAMLResponse` as encryption or anti-replay.
- Never lengthen assertion/`SubjectConfirmation` lifetimes just to "make testing easier".

A signed unsolicited response that is expired, wrong audience, wrong recipient, or replayed **must still be rejected**.

### 4.3. RelayState and Open Redirects

In SP-initiated flows, RelayState typically helps the SP restore SP-created state such as the original protected URL. In IdP-initiated flows, **the SP has no pre-issued request state**, so RelayState can originate from the IdP; it is not trusted by default, and in some bindings **has no integrity protection**.

If an SP reads `RelayState=https://external.example.net/collect` and redirects the browser to an arbitrary URL, risks arise:

- **Open redirect:** login finishes and bounces to an attacker domain.
- **Phishing:** users believe the SP is directing them to a trusted resource.
- **Information leakage:** internal query strings or fragments get sent elsewhere unintentionally.
- **Tenant/target mix-up:** RelayState used to pick tenant/IdP/role outside policy.

**Safe policy:** use an **internal URL allowlist or opaque destination identifiers** controlled by the SP. Prefer relative paths with validated path prefixes, rejecting URLs starting with `//`, disallowed schemes, CR/LF, and abnormal encodings; normalize/parse URIs with semantically sound libraries instead of ad-hoc regex. On invalid input, fall back to a **default landing page** or reject per policy. Never let RelayState choose roles, users, or trusted IdPs.

### 4.4. Mixing Up IdPs/Tenants or Linked Identities

An SP supporting multiple IdPs might receive a Response from IdP A while the browser expected IdP B, or hit an inappropriate registration's ACS. Before verification, **never select trust using unverified data** and then try all keys. The SP must bind the Response to a defined **`RelyingPartyRegistration`**, **issuer**, certificate, and **exact SP entityID/audience**.

Systems performing email-based **account linking** are even riskier: email addresses can change, be reassigned, collide across tenants, or go unverified per policy. Never link accounts or escalate privileges based on unsigned/untrusted attributes or a bare email string in a response.

### 4.5. Risks When the IdP Exposes Tiles to All Users

Users might click an app tile before having an SP account or local authorization. Common operational bugs:

- IdP authenticates cleanly, yet the SP finds no application account.
- SP performs JIT user provisioning without checking entitlements/lifecycle, creating orphan accounts.
- IdP sends attributes missing groups, tenants, or using unstable NameIDs.
- IdP-initiated login establishes a session clashing with the victim's existing SP session (e.g., already signed into another account).

Assigning an app tile at the IdP **does not mean** granting every feature in the SP. The SP must still map roles and enforce account status, session switching, and logout/expiration.

## 5. Signatures, Encryption, and SAML Conditions Remain Mandatory

Even though IdP-initiated lacks `AuthnRequest`, **no remaining SAML verification checks may be omitted**. Checklist:

| Check | Field/Source | Why It Matters |
|---|---|---|
| Trusted issuer | `Response.Issuer` / `Assertion.Issuer` | Only registered IdPs may issue assertions to the SP |
| XML signature | Signed Response or signed Assertions per profile | Prevents forged/tampered data; uses the right IdP's public cert |
| Signature coverage | XMLDSig `Reference` / exact node | Prevents XML Signature Wrapping and wrong-assertion selection |
| Audience | `AudienceRestriction` | Blocks assertions meant for other SPs |
| Destination | `Response.Destination` | Response must target the current ACS |
| Recipient | Bearer `SubjectConfirmationData.Recipient` | Confirms assertion targets the right ACS |
| Conditions | `NotBefore/NotOnOrAfter` | Accepts only within valid time window |
| SubjectConfirmation | Bearer Method, `NotOnOrAfter`, and applicable fields | Validates bearer assertion usage context |
| Unsolicited shape | **No** `InResponseTo` on Response or bearer confirmation | Complies with profile; does not spoof an SP request |
| Replay defense | SP Assertion ID cache / policy | Prevents reusing bearer assertions |
| Status | SAML `StatusCode` | Mints sessions only on valid success |
| Principal mapping | `NameID`, issuer, tenant, attributes | Prevents account mix-ups or privilege escalation |
| Authorization | Internal roles/permissions | Authentication does not equal admin rights |

**Signed Response vs. Signed Assertion:** for HTTP-POST Web Browser SSO, consumed assertions must have valid signature protection—either signing the Assertion itself or signing the Response enclosing the assertion per OASIS errata. Specific IdP/SP contracts may mandate stricter signing. An unsigned Response and unsigned assertions **must never be accepted** merely because they came from an IdP portal.

**EncryptedAssertion:** encryption protects assertion confidentiality for the SP holding the private decryption key, yet **successful decryption does not prove IdP origin**. Signatures and conditions must still be verified; a Response signature covers ciphertext or an Assertion signature sits inside ciphertext depending on IdP config.

**TLS:** HTTPS is necessary for IdP SSO, ACS, and metadata, yet never replaces XML SAML signature verification. Browser form POSTs can be replayed/forged; a valid TLS connection from a browser does not make the browser a trusted issuer.

## 6. "No InResponseTo" Does Not Mean "Totally Insecure"

Separate the assessment into three parts:

1. **Assertion authenticity:** a validly signed unsolicited response with matching issuer/recipient/audience, unexpired and unused, can prove the IdP authenticated the subject described in the assertion.
2. **Browser intent and session:** lacking a pending request, the SP lacks correlation tying this event to a login action initiated at the SP by that browser/user.
3. **Acceptance policy:** an organization may decide to **reject** IdP-initiated flows; or **accept under strict controls** for portal/legacy needs after assessing and mitigating risks.

Thus "no `InResponseTo`" is never a reason to drop all other checks. The irreducible gap is that **you cannot reconstruct an `AuthnRequest` that was never created** to obtain SP-initiated's exact correlation guarantee.

**Design preference:** if you control both the app and entrypoints, configure the IdP portal tile to **link to the SP-initiated login start URL** (or an SP deep link), so the SP issues `AuthnRequest` and saves browser state, and the IdP returns a correlated response. That keeps the "click tile" UX while staying **SP-initiated SAML** on the wire, if IdP and routing allow.

## 7. Deciding Whether to Allow IdP-Initiated in Production

### 7.1. When Should You Reject It?

Prefer rejecting unsolicited responses when:

- The app can initiate SP-initiated flows without legacy interop constraints.
- High-risk data/actions exist where account confusion or login CSRF is material.
- The SP performs sensitive account linking/JIT provisioning without user-intent confirmation.
- No cross-instance replay cache exists or IdP trust/keys cannot be tightly managed.
- RelayState, issuer/tenant, or session switching cannot be cleanly controlled.
- The framework/version lacks unsolicited controls meeting policy requirements.

**Note:** "Disable IdP-initiated" must be enforced at the **SP**, not merely by hiding the app tile at the IdP; attackers can still POST unsolicited responses directly to the ACS if the SP accepts them.

### 7.2. When Support Is Unavoidable

Coordinate SP, IdP, and security teams to enforce:

- **Allowlist of IdP registrations** permitted for unsolicited flows; never enable globally across all IdPs/tenants.
- Accept only at the **exact public ACS/host**; never trust client-supplied hostnames.
- **Trusted signing keys** plus strict issuer/audience/destination/recipient/time/subject-confirmation/replay checks.
- **Tight lifetimes**, MFA requirements, and vetted assertion attributes.
- **RelayState allowlist or opaque identifiers**, safe default landing page, zero open redirects.
- **Policy when the SP already holds another session:** consider rejecting silent account switches, requiring user confirmation to switch accounts, or restarting an SP-initiated flow. This reduces accidental account confusion, though it does not restore unsolicited request correlation.
- **Never link accounts or grant sensitive privileges** from a bare email attribute without federation and lifecycle checks.
- **Monitor events:** unsolicited logins, failed signatures/audiences, replays, account switches, and issuer mismatches.
- **Positive/negative integration tests** with real IdPs, browser/cookie policies, and forged/expired/replayed cases.

**Security reality:** adding a confirmation screen or requiring an extra user click inside the SP can reduce accidental misuse, yet never claim it converts IdP-initiated into SP-initiated or fully eliminates login CSRF. True request correlation requires initiating the flow from the SP first.

## 8. Spring Security Servlet SAML2: Request Path and Where Policy Lives

Spring Security provides **`spring-security-saml2-service-provider`** for Servlet apps acting as SAML SPs. The standard flow typically uses:

- `/saml2/authenticate/{registrationId}` to start SP-initiated flows and build `AuthnRequest`.
- `/login/saml2/sso/{registrationId}` as the ACS receiving `POST` `SAMLResponse`.
- `Saml2WebSsoAuthenticationRequestFilter` to create AuthnRequests.
- `Saml2WebSsoAuthenticationFilter` to handle `SAMLResponse`, invoking the converter and authentication provider.
- `Saml2AuthenticationTokenConverter` to resolve registration/tokens.
- `OpenSaml5AuthenticationProvider` (in Spring Security generations using OpenSAML 5) to verify signatures, issuer, destination, assertions, decryption, and conditions before creating `Saml2Authentication`.
- `RelyingPartyRegistrationRepository` holding SP/IdP entityID, ACS, certs, and SSO endpoints per registration.

Spring Security's SAML2 overview notes **two ways** an IdP issues responses: visiting the IdP and picking an app tile, or hitting a protected SP page so the SP redirects. Hence an ACS can receive non-SP-initiated `SAMLResponse`s under certain configs/versions.

**Do not extrapolate from legacy docs:** the legacy **Spring Security SAML Extension** had a `supportUnsolicitedResponse` property on `ExtendedMetadata`. That is **not** a general property in modern Spring Security SAML2 Service Provider. Before implementing a "solicited-only" policy, check your exact **version**, provider, converter/validator, and where request correlation is enforced. Never copy legacy Spring SAML Extension XML config into modern Spring Boot apps.

### 8.1. Spring Boot Config for an SP (Illustrative)

In a Spring Boot Servlet project (with web, security, and `spring-security-saml2-service-provider`), configure an IdP:

~~~yaml
spring:
  security:
    saml2:
      relyingparty:
        registration:
          corporate:
            entity-id: "https://sp.example.org/saml2/service-provider-metadata/corporate"
            acs:
              location: "https://sp.example.org/login/saml2/sso/corporate"
            assertingparty:
              metadata-uri: "https://idp.example.org/metadata"
~~~

Paths and domains are **illustrative**. The IdP must register the SP entityID/ACS and provide trusted metadata. Property names may vary by Spring Boot version; verify against your project's exact documentation. **This config only tells the SP which IdP to trust**—it is not a complete "block unsolicited" policy.

### 8.2. Java 17+ SecurityFilterChain for SAML Login

File `src/main/java/com/example/saml/SamlSpApplication.java` (runs inside a Spring Boot Servlet project with matching dependencies):

~~~java
package com.example.saml;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@SpringBootApplication
@RestController
public class SamlSpApplication {

    public static void main(String[] args) {
        SpringApplication.run(SamlSpApplication.class, args);
    }

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http) throws Exception {
        return http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/", "/error").permitAll()
                .anyRequest().authenticated())
            .saml2Login(Customizer.withDefaults())
            .build();
    }

    @GetMapping("/")
    String home() {
        return "SAML SP demo";
    }

    @GetMapping("/private")
    String privatePage() {
        return "Authenticated";
    }
}
~~~

This is **complete Java code for the application class**, yet **cannot run with plain `javac`** because it needs the Spring Boot/Security classpath, BOM, and a registered IdP. In a Maven project with Maven Wrapper:

~~~bash
./mvnw spring-boot:run
~~~

Once running cleanly, `GET /` returns `SAML SP demo`. `GET /private` requires authentication; redirects, cookies, usernames, and logs depend on the real IdP/registration/config, with no fixed mock stdout.

**Important:** the config class above **does not enforce a solicited-only policy**, nor does it guarantee a distributed replay cache suitable for every production topology. It is a baseline; before go-live, run the tests in section 12 and apply the policies/extension points supported by your running version.

### 8.3. Approach for Controlling Unsolicited Responses

If the product requires **SP-initiated only**, design target behavior as follows:

~~~text
POST arrives at ACS
  |
  +-- Resolve registration / verify issuer + signature + conditions
  |
  +-- Does Response have InResponseTo?
  |       |
  |       +-- Yes -> accept only if a pending request ID exists
  |                 bound to the exact browser/session and valid constraints
  |
  +-- Response lacks InResponseTo?
          |
          +-- Does policy allow unsolicited for this IdP?
                  |
                  +-- No  -> reject / route to SP start-login
                  |
                  +-- Yes -> verify all SAML conditions + replay +
                             RelayState/session/account-switch policy
                             before considering session creation
~~~

This diagram states a **security requirement**, not an API pipeline guaranteeing exact callback order in every Spring Security release. When customizing, choose extension points supported by your version's docs (e.g., authentication converter/provider response validator/handler or integration gateway), verify signatures before trusting untrusted fields, and retain all default validations. Never swap the provider for a custom parser just to read `InResponseTo`.

**Key error-handling distinction:** a response that **carries** `InResponseTo` when the SP no longer has a matching request **must never fall through to the unsolicited branch**. It explicitly claims to answer a specific request; if the request ID is wrong/missing/cross-session, fail safely.

### 8.4. Request Repository and Session in SP-Initiated

When the SP generates `AuthnRequest`, Spring Security needs somewhere to save/load the request for post-callback correlation. This can be the HTTP session or an application-supplied repository, depending on version/config. Check:

- Does the browser keep the **session cookie** across the redirect/POST from the IdP (`SameSite`, `Secure`, domain)?
- Behind a reverse proxy, does the SP see the right public scheme/host/path?
- In multi-instance deployments, is request state accessible across instances or in shared storage?
- Are session fixation protection, multiple tabs, and late callbacks handled?
- Do expiration and missing state return errors properly? **Never turn off correlation** just to "make login work".

Those failures differ from a profile-valid unsolicited Response: SP-initiated failing due to missing state requires fixing cookies, repositories, clocks, or proxies.

## 9. Standalone Java 17: Simulating Request Correlation Decisions

The program below illustrates **conceptual policy rules**. It assumes signature, issuer, audience, recipient, validity period, and replay **were already verified by a dedicated SAML library** and **is not a SAML validator**. Never use it to replace OpenSAML in production.

File `SamlInitiationPolicyDemo.java`:

~~~java
public class SamlInitiationPolicyDemo {

    static String decide(
            boolean samlValidated,
            boolean responseHasInResponseTo,
            boolean matchingPendingRequestForBrowser,
            boolean allowUnsolicited) {

        if (!samlValidated) {
            return "REJECT: invalid SAML";
        }

        if (responseHasInResponseTo) {
            if (matchingPendingRequestForBrowser) {
                return "ACCEPT: correlated request";
            }
            return "REJECT: missing browser request";
        }

        if (!allowUnsolicited) {
            return "REJECT: unsolicited disabled";
        }

        return "REVIEW: unsolicited policy checks";
    }

    public static void main(String[] args) {
        System.out.println(decide(true, true, true, false));
        System.out.println(decide(true, true, false, true));
        System.out.println(decide(true, false, false, false));
        System.out.println(decide(true, false, false, true));
        System.out.println(decide(false, false, false, true));
    }
}
~~~

Compile and run with Java 17+:

~~~bash
javac SamlInitiationPolicyDemo.java
java SamlInitiationPolicyDemo
~~~

Exact stdout:

~~~text
ACCEPT: correlated request
REJECT: missing browser request
REJECT: unsolicited disabled
REVIEW: unsolicited policy checks
REJECT: invalid SAML
~~~

**Case breakdown:**

1. SAML validated, carries `InResponseTo`, and matching pending request exists for that browser → correlation passes.
2. Response declares `InResponseTo` yet SP has no browser request even though unsolicited is allowed → **still rejected**, no fallback.
3. Response lacks `InResponseTo`, policy forbids unsolicited → rejected.
4. Response lacks `InResponseTo`, policy allows unsolicited → only **eligible for review**, still requiring Replay/RelayState/session/account policy checks.
5. SAML failed signature/condition validation → rejected regardless of request presence.

Intentionally returning `REVIEW` in case 4 guards against thinking flipping an `allowUnsolicited` flag alone resolves all risks. This is deterministic illustrative code **without an XML parser, certificates, request repository, or HTTP handlers**.

## 10. RelayState Example: Internal Navigation After IdP-Initiated Login

Suppose the IdP portal has three buttons: "Dashboard", "Reports", "Account". Do not let the IdP send an arbitrary URL for the SP to redirect to blindly. A safer agreement:

| RelayState Value | Valid Post-Login Destination |
|---|---|
| `dashboard` | `/dashboard` |
| `reports` | `/reports` |
| `account` | `/account` |
| empty / unrecognized | `/home` |

Key condition: the mapping must be defined by the **SP**; use RelayState as a navigation hint **only after SAML is authenticated**, never to pick accounts, roles, or issuers. If external-domain redirects are required, enforce an exact URL allowlist and strict normalization covering scheme, port, hostname, path, and encoding variants.

Avoid dangerous patterns such as:

~~~java
// UNSAFE example: illustrates an anti-pattern only.
response.sendRedirect(request.getParameter("RelayState"));
~~~

That line performs no destination domain checks, creating an immediate open redirect. Real implementations require allowlist logic and proper Spring Security context handling, rather than copying this anti-pattern into runnable code.

## 11. Scenario Matrix: Which Checks May Never Be Skipped?

| Case | `InResponseTo` | Validation State | SP Expectation |
|---|---|---|---|
| SP-initiated, right browser and request ID | Present, matches | Valid signature/conditions | Allow per session, roles, and policy |
| SP-initiated, wrong request ID | Present, mismatches | Valid signature | **Reject** for missing correlation |
| SP-initiated, browser lost cookie/session | Present, yet no request in session | Valid signature | **Reject**, fix session/cookies |
| IdP-initiated, policy forbids | Absent | Valid signature | **Reject** and guide user to start at SP |
| IdP-initiated, policy allows | Absent | Valid signature/conditions/replay | Consider accepting under added constraints, aware of login CSRF risk |
| IdP-initiated yet Response carries `InResponseTo` | Present | May be validly signed | Invalid as unsolicited per OASIS |
| IdP-initiated yet bearer confirmation carries `InResponseTo` | Present on `SubjectConfirmationData` | May be validly signed | Invalid for unsolicited bearer confirmation |
| IdP-initiated, wrong issuer/cert | Absent | Fails verification | **Reject** |
| IdP-initiated, wrong `Audience` | Absent | Valid signature | **Reject** |
| IdP-initiated, wrong `Recipient`/ACS | Absent | Valid signature | **Reject** |
| IdP-initiated, expired | Absent | Valid signature | **Reject** |
| IdP-initiated, assertion ID already used | Absent | Valid signature | **Reject replay** |
| IdP-initiated, RelayState points to unapproved external domain | Absent | Valid signature | Do not redirect externally; default landing or reject |
| IdP-initiated, claims admin role from unpermitted issuer | Absent | Claim fails policy | Do not grant role; check issuer/role mapping |
| IdP-initiated while SP already logged in as another user | Absent | Valid signature | Handle account switching per policy; never silently overwrite arbitrarily |

"Valid signature" cases alone are **insufficient** to grant access. In high-security applications, policy may reject unsolicited logins altogether to retain full request correlation.

## 12. Integration Testing with Spring Security and a Real IdP

### 12.1. Positive Tests

1. **SP-initiated baseline:** unauthenticated browser visits protected page, SP emits `AuthnRequest`; IdP returns `Response.InResponseTo` pointing to exact ID and matching bearer confirmation; SP creates session only after all checks.
2. **IdP portal app tile:** when policy explicitly allows, browser visits IdP portal and clicks tile; IdP issues response **without `InResponseTo`** on both Response and bearer confirmation; SP receives POST at the right ACS.
3. **Issuer/registration mapping:** verify IdP entityID, signing cert, and SP Audience; run for every permitted tenant.
4. **Default landing page:** IdP sends no RelayState → SP navigates to a safe internal URL.
5. **Allowed RelayState:** agreed internal identifier → routes to right page after SAML verification.
6. **Role/account checks:** user assigned app in IdP yet lacking internal roles still cannot access restricted resources.
7. **Distributed replay cache:** identical assertion ID cannot be consumed on two nodes in multi-replica deployments.

### 12.2. Negative Tests — Mandatory

| Test | Expected Outcome |
|---|---|
| SP-initiated-only policy, send validly signed unsolicited | SP **rejects** for missing request correlation |
| Response carries random `InResponseTo` | SP **rejects**, no unsolicited fallback |
| Request ID exists yet belongs to **another browser/session** | SP **rejects** |
| Response omits `InResponseTo`, bearer confirmation carries `InResponseTo` | SP **rejects** per unsolicited profile |
| Invalid signature or cert from untrusted IdP | SP **rejects** |
| Assertion signature wrapped / Reference does not cover consumed node | SP **rejects** |
| Wrong issuer/audience/recipient/destination | SP **rejects** |
| Expired/not-before invalid or clock exceeds skew | SP **rejects** |
| Second replay of Response/Assertion | SP **rejects** |
| RelayState is attacker domain URL or `javascript:` | SP does not redirect there |
| Existing session for user A, response identifies user B | Handled per account-switch policy; no silent confusion |
| Modified group/role in unverified payload | No authority granted |
| User not assigned to app in IdP | No valid session issued |
| IdP outage / metadata signing cert rotation | Fails safely, clear notice, recoverable |

**Proper testing:** do not rely solely on mock authentication to test business routes. Integrate with a **test IdP** capable of issuing unsolicited, solicited, wrong-audience, expired, duplicate, and malformed cases. For negative SAML tests, do not fake invalid signatures casually and assume the provider works; verify the test harness observes the expected rejection.

### 12.3. Testing Login CSRF Defensively

Using **authorized test accounts and test environments**, simulate the distinction:

- A browser **with no pending `AuthnRequest`** receives a valid unsolicited Response.
- When policy forbids unsolicited, the browser must **not create a session**; when policy allows, document the risk and mitigations explicitly.
- A response valid by ID/cert yet naming a **different `NameID` than the active session user** must not silently swap identities outside policy.
- Verify logs capture SSO type, issuer, registration, error reason, session correlation status, and hashed assertion ID where needed—never raw Base64 responses or PII.

**Distinguish results:** "Replay rejected" does not prove **first-use login CSRF** was blocked. "Signature validation succeeded" does not prove the browser itself issued `AuthnRequest`.

## 13. Logging, Metrics, and Operations

Observe structured events such as:

- `saml.login.initiation=sp|idp` based on verified classification.
- `saml.login.result=success|failure` and failure category: signature, issuer, audience, recipient, request correlation, expired, replay, RelayState, account switch.
- **Allowlisted** `registrationId`, tenant, or IdP issuer.
- Processing latency, unsolicited attempt counts per IdP, invalid response rate.
- Alerts on spikes in unsolicited responses, reused assertion IDs, or metadata/certificate changes.
- Clock/NTP drift, session repository, cache cluster, and IdP availability.

**Log boundaries:** avoid logging raw `SAMLResponse`, JWTs, private keys, sensitive NameIDs/emails/attributes, or cookies. If correlation is needed for investigation, hash IDs and enforce proper retention/access controls.

When rolling out a policy **forbidding unsolicited**, prepare UX for users clicking IdP app tiles:

1. Coordinate with the IdP admin so the tile **points to the SP start-login URL** instead of sending an unsolicited assertion.
2. Verify the SP generates `AuthnRequest` with the right registration/entityID and saves session state before redirecting to the IdP.
3. Verify solicited callbacks succeed on target browsers and devices.
4. Monitor request correlation errors, proxy/cookie behavior, and redirects.
5. Never turn off validation or widen IdP allowlists when errors occur.

When legacy IdP-initiated support must stay, maintain an **exception record** covering IdP, ACS, data sensitivity, controls, approver, expiration date, and re-testing after changes.

## 14. Common Misconceptions

**Myth 1: "The IdP signed it, so login CSRF is impossible."** False. A validly signed response for an **attacker's account** can still be fed to a victim's browser before being consumed; missing request/session correlation is a separate problem.

**Myth 2: "Missing `InResponseTo` is an XML error."** False for profile-compliant IdP-initiated flows; unsolicited **must omit** that field. Still, an SP is entitled to forbid unsolicited flows under security policy.

**Myth 3: "If the SP lost `AuthnRequest`, treat the response as IdP-initiated."** False. A response with `InResponseTo` or replying to a solicited flow must be checked against pending state; a lost session is a bug to fix.

**Myth 4: "A replay cache solves login CSRF."** Insufficient. A cache stops reuse after an assertion ID is recorded; the very first delivery to the wrong browser can still succeed.

**Myth 5: "`RelayState` comes from the IdP, so it is definitely safe."** False. RelayState may lack integrity protection per binding and must never serve as an unrestricted redirect URL.

**Myth 6: "Spring Security has a `supportUnsolicitedResponse` property in every version."** False. That was a config name in the **legacy Spring Security SAML Extension**; never assume it applies to modern `spring-security-saml2-service-provider`. Check exact documentation and integration code.

**Myth 7: "Disabling CSRF app-wide is necessary for SAML POSTs to work."** False. The ACS is a specialized callback needing framework-managed cross-site POST handling, not a reason to disable CSRF protection across business POST routes; any SAML CSRF exemption must stay tightly scoped and backed by signature/conditions/replay and security policy.

**Myth 8: "Completing SSO grants admin privileges."** False. SAML authentication and application authorization are independent steps; IdP identity/claims must be verified and mapped to permissions under strict controls.

## 15. Design and Acceptance Checklist

- [ ] Explicit **allow/deny unsolicited** decision made based on business needs, risk, and current framework/version.
- [ ] Where possible, IdP portal tiles point to the **SP-initiated entrypoint** so the SP issues stateful `AuthnRequest`.
- [ ] When accepting unsolicited, Response and bearer `SubjectConfirmationData` **omit `InResponseTo`**.
- [ ] Responses with `InResponseTo` are accepted only when **matching a pending request of the exact browser/session**.
- [ ] IdP issuer, trusted signing certs, SP entityID/audience, destination/recipient, and bindings match metadata.
- [ ] Signatures protect the exact Assertion/Response consumed, XML parsing is hardened, no signature wrapping.
- [ ] Cluster-wide shared bearer-assertion anti-replay cache covers validity windows.
- [ ] Expiry/NotBefore/`SubjectConfirmationData`, clock skew, and account states are checked.
- [ ] RelayState accepts only allowed values with a safe default landing page; zero open redirects.
- [ ] No risky automatic account linking or silent account switching.
- [ ] SP enforces separate authorization; IdP users are assigned and MFA-enforced as required.
- [ ] CSRF exemptions (if needed for ACS) are strictly scoped to the SAML callback without affecting business routes.
- [ ] Tested positive/negative flows with a test IdP, multiple browsers, multiple tabs, expired sessions, and multiple replicas.
- [ ] Appropriate logging/metrics/auditing and a sunset plan for unsolicited support when no longer needed.

## 16. Self-Check Questions

1. **Does a valid unsolicited SAML Response contain `InResponseTo`?** No. Per SAML Profiles §4.1.5, both Response and bearer `SubjectConfirmationData` in unsolicited flows must omit this field.
2. **Can IdP-initiated be spec-compliant yet still risky?** Yes. Lacking correlation to browser login intent leaves login CSRF/account confusion as a risk.
3. **Why doesn't a valid signature guarantee login intent?** A signature proves data origin and integrity under trust; it does not prove the victim's browser initiated an `AuthnRequest`.
4. **Can a response with `InResponseTo=_a1` whose session lost `_a1` be accepted as unsolicited?** No. That is a solicited response that lost correlation; fail safely and fix session handling.
5. **Can `RelayState` be used directly as a redirect URL?** No. It must be allowlisted/normalized or mapped via an opaque key to a trusted internal destination.
6. **Does a replay cache prevent all login CSRF?** No. It does not guarantee the **first** consumer is the browser that intended to log in.
7. **How do you keep the "click app tile" UX while remaining SP-initiated?** Point the tile to the SP login entrypoint; the SP creates `AuthnRequest` and redirects to the IdP in a quick round-trip.
8. **In modern Spring Security, should you copy the `supportUnsolicitedResponse` property from the old Spring SAML Extension?** No; check your exact version and supported extension points.
9. **Is a successful IdP-initiated login enough to authorize sensitive actions?** No; check authorization and require step-up/reconfirmation per your risk model.
10. **What should appear in a test report?** Initiation mode, validation/trust/correlation/replay, session/account outcome, RelayState, roles, and negative scenarios.

## 17. Authoritative References

- OASIS SAML 2.0 Profiles, **§4.1.3–4.1.5** (Web Browser SSO, bearer confirmation, unsolicited responses): https://docs.oasis-open.org/security/saml/v2.0/saml-profiles-2.0-os.pdf
- OASIS **SAML V2.0 Errata 05** (clarifies assertion/Response signing and CSRF, RelayState warnings): https://docs.oasis-open.org/security/saml/v2.0/errata05/os/saml-v2.0-errata05-os.html
- OWASP SAML Security Cheat Sheet, **Unsolicited Response Considerations**: https://cheatsheetseries.owasp.org/cheatsheets/SAML_Security_Cheat_Sheet
- Spring Security Servlet SAML2 Login Overview (APIs/flows and how IdP produces responses): https://docs.spring.io/spring-security/reference/servlet/saml2/login/overview.html
- Spring Security Authenticating SAML2 Responses (validators, converter, authentication provider): https://docs.spring.io/spring-security/reference/servlet/saml2/login/authentication.html
- Spring Security Producing AuthnRequests: https://docs.spring.io/spring-security/reference/servlet/saml2/login/authentication-requests.html
- Spring Security **SAML Extension** legacy reference (historical comparison only; do not use for configuring the modern module): https://docs.spring.io/spring-security-saml/docs/current/reference/htmlsingle/

**Principle to remember:** IdP-initiated SSO can be permitted by the SAML spec and validly signed by the IdP, yet when the SP **has no pending `AuthnRequest`**, the SP lacks evidence tying the response to **the browser's login intent**. Unless business requirements force it, prefer SP-initiated. When support is required, still verify signatures/issuer/audience/recipient/time/replay/authorities, constrain `RelayState`, and explicitly recognize the login CSRF risk that signatures alone cannot eliminate.
