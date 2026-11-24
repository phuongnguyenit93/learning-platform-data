# Limitations of Mock Authentication When Testing the Real SAML Validator

## 1. Problem: Does a Passing Login Test Prove the SAML Response Is Trustworthy?

A Spring Boot application uses **Spring Security SAML 2.0** to let employees log in through an Identity Provider (IdP). The development team writes:

~~~java
@Test
@WithMockUser(username = "linh", roles = "ANALYST")
void analystCanReadReports() throws Exception {
    mvc.perform(get("/reports"))
       .andExpect(status().isOk());
}
~~~

This test has value: the endpoint allows requests carrying the expected mock principal and role. However, this test **does not pass through the real SAML Response validator**. It does not prove the XML signature was issued by a trusted IdP, nor does it check `AudienceRestriction`, `Recipient`, `Destination`, `Issuer`, `InResponseTo`, time bounds, decryption, replay protection, or certificate trust policies.

This is a Knowledge article in **Spring Security - federation → SAML2 Testing**, topic **"Limitations of Mock Authentication When Testing the Real SAML Validator"**.

### Learning Objectives

After this article, you will be able to:
1. Distinguish authorization tests using mock users from **SAML cryptographic/protocol verification** tests.
2. Understand the Spring Security pipeline `Saml2WebSsoAuthenticationFilter → Saml2AuthenticationTokenConverter → AuthenticationManager → OpenSAML provider → Saml2Authentication`.
3. Explain when testing with `@WithMockUser`, `MockMvc.with(user())`, `with(authentication())`, and a mock manager is appropriate, as well as the scope they do not cover.
4. Design unit/slice, provider-level, ACS HTTP integration, and browser/IdP E2E layers.
5. Generate **validly signed fixtures** using test keys, distinguishing signature failures from semantic validator failures.
6. Verify issuer/trust/certificate, audience, destination, recipient, subject, time, correlation, encryption, and replay.
7. Handle saved `AuthnRequest`/`RelayState` and differences between SP-initiated and IdP-initiated flows.
8. Test negative cases **without disabling signature verification in Spring**.
9. Write MockMvc tests that run the real filter/provider and verify `SecurityContext` after the callback.
10. Understand validator customization risks when upgrading Spring Security/OpenSAML.
11. Run a standalone Java 17 demo that classifies test evidence strength without pretending to be a SAML verifier.
12. Prepare a QA matrix and release runbook.

**Environment:** Java 17+, Spring Boot 3.x, Spring Security Servlet 6.x/7.x, SAML 2.0 Web Browser SSO. OpenSAML providers and customization APIs vary by version; Spring code snippets must be verified against actual dependencies. The domains `sp.example.org`/`idp.example.org` and keys in this article are synthetic data.

---

## 2. Two Completely Different Testing Questions

**Question A — Given an already-authenticated user with certain roles, how does the application behave?**

Examples:
- Analysts can read reports; viewers cannot edit.
- Admins cannot access another tenant solely because they have an admin role.
- `@PreAuthorize`, `AuthorizationManager`, controllers, or business services work as intended.
- Local principal mapping to account ID, roles, and resource ACLs is checked.

This is the right scope for mock users, MockMvc request post-processors, and stubbed downstream dependencies.

**Question B — Was this user genuinely confirmed by a trusted IdP for this SP in a SAML Response?**

Examples:
- Is the XML Signature genuine, valid, and protecting the right XML object?
- Did the signature come from the verification key registered for the right IdP?
- Do Response/Assertion have the right Issuer, Audience, Destination, and Recipient?
- Are time, SubjectConfirmation, and request correlation valid?
- Could the assertion be replayed, signature-tampered, or left undecrypted?
- Can IdP B impersonate IdP A's data?

This is **SAML protocol validation**. Pre-creating an `Authentication` answers none of these questions.

| Test | Primary guarantee | Does NOT prove |
| --- | --- | --- |
| `@WithMockUser` | Access logic with fake principal/roles | SAML signature, issuer, audience, time |
| `with(user("linh"))` | `SecurityContext` loaded into test request | IdP actually authenticated `linh` |
| `with(authentication(fake))` | Code after `Authentication` already exists | Provider XML verification |
| Mock `AuthenticationManager` success | Success handling after manager | OpenSAML validators ran |
| POST self-crafted unsigned XML | Parser/error path for unsigned/malformed XML | Positive verifier |
| Real OpenSAML provider + signed fixture | Protocol/crypto validation per configuration | Full browser/cookie/proxy path |
| MockMvc ACS + real provider | Filter/converter/provider on Servlet request | Production IdP/browser compatibility |
| Staging IdP/browser E2E | Protocol interoperability + network/browser | All negative security cases |

**Sanity-check question:** did the test **actually invoke the provider that processes SAML Response XML**? If not, never report "SAML signature validator passed."

## 3. Real SAML Flow in Spring Security

~~~mermaid
sequenceDiagram
    participant B as Browser
    participant SP as Spring SP
    participant IDP as Test IdP
    B->>SP: GET /private
    SP-->>B: Redirect /saml2/authenticate/test-idp
    B->>SP: GET AuthnRequest endpoint
    SP->>SP: Generate AuthnRequest; save state if configured
    SP-->>B: Redirect to IdP with SAMLRequest/RelayState
    B->>IDP: Forward AuthnRequest to IdP
    IDP-->>B: HTML form with signed SAMLResponse
    B->>SP: POST /login/saml2/sso/test-idp
    SP->>SP: Saml2WebSsoAuthenticationFilter
    SP->>SP: Converter decode response, resolve relying party
    SP->>SP: AuthenticationManager -> OpenSAML provider
    SP->>SP: Verify signatures/trust/conditions/decryption
    alt Valid
        SP->>SP: Saml2Authentication / SecurityContext
        SP-->>B: Success per login flow
    else Invalid
        SP->>SP: AuthenticationFailureHandler/EntryPoint
        SP-->>B: Error/redirect; do not grant Authentication
    end
~~~

Key components to remember:

- `Saml2WebSsoAuthenticationRequestFilter`: builds the `AuthnRequest` to start SP-initiated login.
- `Saml2WebSsoAuthenticationFilter`: receives the form POST `SAMLResponse` at the ACS.
- `Saml2AuthenticationTokenConverter`: extracts the response and looks up the right `RelyingPartyRegistration`.
- `AuthenticationManager`: dispatches the token to the provider.
- `OpenSaml4AuthenticationProvider` in some Spring Security 6.x configurations, or `OpenSaml5AuthenticationProvider` in supported versions and Spring Security 7.x.
- OpenSAML provider: verifies signatures, checks issuer/destination, decrypts, validates assertion/time/subject/audience, creates `Authentication`.
- `SecurityContext`: stores the result after validation succeeds.

**Never conclude an HTTP 302 from the ACS means login succeeded**: it could be redirecting back to the IdP or to an error page. Check the authentication state and a protected endpoint on a subsequent request.

### What Does the Mock Path Skip?

~~~text
Mock request + with(user("analyst"))
  -> SecurityContext already has user
  -> AuthorizationFilter
  -> Controller
~~~

This path does **not** build a signed `AuthnRequest`, does not decode `SAMLResponse`, does not look up trusted IdP certificates, and does not run XML Signature or assertion validators. This is an intentional boundary for fast business-logic testing, **not a flaw in MockMvc itself**.

## 4. Four Testing Layers and Honest Result Naming

| Layer | Goal | Tools | Honest result name |
| --- | --- | --- | --- |
| T1 — Unit/Slice | Authorization/business policy with mock users | JUnit, `@WithMockUser`, `user()`, Mockito | `AUTHORIZATION_MOCK_PASS` |
| T2 — Real Provider | XML crypto/trust + semantic conditions | Real OpenSAML provider, signed fixtures | `SAML_VERIFIER_PASS` |
| T3 — ACS integration | Filter, request converter, repository, session, redirect | `@SpringBootTest`, MockMvc, real filters/provider | `SAML_ACS_INTEGRATION_PASS` |
| T4 — Browser/IdP E2E | IdP metadata, browser POST, TLS, proxy, SameSite/cookies | Staging test IdP/browser | `SAML_E2E_PASS` |

T1 can run on every commit, T2 whenever authentication changes, T3 in CI, and T4 in staging/nightly/release pipelines. However, a **positive E2E** does not replace all negative T2 tests, and a **mock authorization test** does not replace T2/T3.

### Test Names Must Match the Evidence

- Good: `analystCanReadOwnReportWithMockPrincipal()`.
- Good: `signedAssertionWithWrongAudienceIsRejected()` when the fixture signature remains valid.
- Bad: `idpSignatureValidated()` when the test only uses `@WithMockUser`.
- Bad: `samlLoginSucceeded()` when the sole assertion is HTTP 302 from the ACS.
- Bad: `replayPrevented()` when the response was rejected only because it expired.

## 5. @WithMockUser Is Useful, But Does Not Prove SAML

Spring Security Test lets a test place an arbitrary principal into `SecurityContext`:

~~~java
package com.example.portal;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.security.test.context.support.WithMockUser;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class ReportAuthorizationTest {

    @Autowired
    MockMvc mvc;

    @Test
    @WithMockUser(username = "linh", roles = "ANALYST")
    void analystCanReadReport() throws Exception {
        mvc.perform(get("/reports"))
                .andExpect(status().isOk());
    }
}
~~~

**Prerequisites:** the project must actually have `GET /reports` returning 200 for analysts, along with Spring Boot Test, Spring Security Test, and an appropriate filter chain. This is an **integration test class inside a Spring project**, has no `main()`, and does not compile standalone with `javac`. If the endpoint requires tenant/object-level authorization, corresponding setup and assertions must be added.

Cases where mocking is genuinely useful:
1. Missing role returns 403.
2. Right role but wrong tenant still returns 403.
3. User disabled at the app account gate is denied.
4. Controller does not leak another user's data.
5. Method security is not accidentally bypassed during refactoring.
6. When services/repositories fail, error handling does not disclose sensitive info.

**However**, the mock user `linh` needs no account in the IdP, no SAML XML, and no signature. Thus, the test only proves behavior **after authentication**, not that the authentication source is trustworthy.

## 6. MockMvc.with(user()) and with(authentication()) Also Bypass the Verifier

Spring Security MockMvc examples:

~~~java
mvc.perform(get("/reports")
        .with(user("linh").roles("ANALYST")));
~~~

With a manually built authentication:

~~~java
mvc.perform(get("/reports")
        .with(authentication(preparedAuthentication)));
~~~

Both snippets require a suitable test class/fields/imports, and `preparedAuthentication` is a test-constructed object. Spring Security docs also support `securityContext(testContext)`.

These post-processors **inject fake security state**. They can test controllers, authorization managers, and session-related behavior, but they do not:
- Parse `SAMLResponse`;
- Verify XML Signatures;
- Check `RelyingPartyRegistration`;
- Decrypt `EncryptedAssertion`;
- Check issuer/recipient/time;
- Consume correlation state;
- Detect replay per SAML policy.

With `MockMvcBuilders.standaloneSetup`, you must also include Spring Security's `FilterChainProxy` or `springSecurity()` in the test for assertions to reflect security filters. When using Boot's auto-configured MockMvc, also verify that security filters are registered.

## 7. Mocking AuthenticationManager: An Easy-to-Make Fake Integration Test

Anti-pattern example:

~~~java
// Illustrative test code; do not use as a provider validation test.
when(authenticationManager.authenticate(any()))
        .thenReturn(fakeAuthenticatedSaml2Authentication);
~~~

If `AuthenticationManager` is mocked with Mockito to return success, the OpenSAML provider never runs. Any request forwarded by the filter to the mocked manager may appear "authenticated" in the test, even if the response was unsigned or had the wrong issuer.

### What Must Stay Real at Layers T2/T3

- `Saml2WebSsoAuthenticationFilter` and token converter when testing the ACS.
- `RelyingPartyRegistrationRepository` with IdP entityId, SP entityId, ACS, and trusted test verification credentials.
- `AuthenticationManager`/`ProviderManager` backed by the **real OpenSAML provider**.
- Properly configured response/assertion validators.
- Decryption credentials if production uses encrypted assertions.
- `AuthnRequest` repository when testing SP-initiated correlation.
- Appropriate failure handler + security context persistence.

You may mock business repositories or remote APIs **downstream of SAML validation** as long as doing so does not erase what the test aims to prove. Never mock the very component the test claims to verify.

## 8. Sample SAML Response for Structural Understanding, Not a Valid Login Fixture

~~~xml
<samlp:Response
    xmlns:samlp="urn:oasis:names:tc:SAML:2.0:protocol"
    xmlns:saml="urn:oasis:names:tc:SAML:2.0:assertion"
    ID="_response-001"
    Version="2.0"
    IssueInstant="2026-11-07T04:00:00Z"
    Destination="https://sp.example.org/login/saml2/sso/test-idp"
    InResponseTo="_request-001">
  <saml:Issuer>https://idp.example.org/metadata</saml:Issuer>
  <samlp:Status>
    <samlp:StatusCode
      Value="urn:oasis:names:tc:SAML:2.0:status:Success"/>
  </samlp:Status>
  <saml:Assertion ID="_assertion-001"
      IssueInstant="2026-11-07T04:00:00Z" Version="2.0">
    <saml:Issuer>https://idp.example.org/metadata</saml:Issuer>
    <saml:Subject>
      <saml:NameID>opaque-user-123</saml:NameID>
      <saml:SubjectConfirmation
        Method="urn:oasis:names:tc:SAML:2.0:cm:bearer">
        <saml:SubjectConfirmationData
          InResponseTo="_request-001"
          Recipient="https://sp.example.org/login/saml2/sso/test-idp"
          NotOnOrAfter="2026-11-07T04:05:00Z"/>
      </saml:SubjectConfirmation>
    </saml:Subject>
    <saml:Conditions NotBefore="2026-11-07T03:59:00Z"
                     NotOnOrAfter="2026-11-07T04:05:00Z">
      <saml:AudienceRestriction>
        <saml:Audience>https://sp.example.org/saml2/metadata</saml:Audience>
      </saml:AudienceRestriction>
    </Conditions>
  </saml:Assertion>
</samlp:Response>
~~~

**This XML has no XML Signature** and cannot be used as a successful SAML login fixture. A SAML `StatusCode` of `Success` or a `NameID` does not prove the IdP authenticated the user. Timestamps and IDs are synthetic.

### Rules That Must Be Tested

| Rule | Security concern |
| --- | --- |
| Signature + signed references | Content was not altered or spliced |
| Trusted verification certificate | Trust only approved IdPs |
| Issuer | Response/Assertion came from the expected IdP |
| Destination | Response was delivered to the right ACS |
| AudienceRestriction | Assertion is intended for the right SP |
| Bearer SubjectConfirmation | Recipient, expiry, and `InResponseTo` per profile |
| Time conditions | Do not accept assertions too early or expired |
| Request correlation | Do not bind a response to another session/request |
| Replay/OneTimeUse | Do not reuse assertions against policy |
| Decryption | Handle encrypted identity/attributes with the right key |
| Principal/roles | Never map unverified data into privileges |
| XML parser safety | No XXE/signature wrapping/ambiguous IDs |

Not every rule behaves identically across all versions/customizations; inspect the running code and config.

## 9. XML Digital Signature: Having a Signature Tag Is Not Enough

A SAML validator must confirm:
1. The XML Signature is cryptographically valid.
2. The verification key belongs to the configured **trusted IdP metadata/certificate**.
3. Signed references cover the exact **Response/Assertion that the SP consumes**.
4. XML ID references and namespaces are not vulnerable to signature wrapping/confusion.
5. If multiple assertions exist, code never reads the principal from an unprotected assertion.
6. Algorithms/transform policies are permitted by configuration.
7. Never trust a certificate supplied inside untrusted XML as a root of trust.

**Never regex `ds:Signature`, `NameID`, or `Attribute` to build an `Authentication`.** Use Spring Security/OpenSAML.

### Bad Test Case

~~~text
Generate XML with NameID=admin
Base64 encode XML
POST to ACS
Test expects login success
~~~

If the Response/Assertion lacks a trusted signature, **a valid provider must reject it per signing policy**. If such a test passes, check:
- Is `AuthenticationManager`/provider mocked?
- Did the ACS filter actually run?
- Did the test pre-populate `Authentication`?
- Does a custom provider skip verification?
- Is the test checking only HTTP status instead of `SecurityContext`?

Never "fix" this by disabling signature validation in a test profile and using that pass to claim SAML is secure.

## 10. A Very Common Bug: Editing Audience After Signing

Suppose you have a **signed** fixture:

~~~text
Audience = https://sp.example.org/metadata
Signature = valid
~~~

You open the XML and change it to:

~~~text
Audience = https://other-sp.example.org/metadata
Signature = now invalid, because signed content changed
~~~

The provider rejects it. Yet a test named `wrongAudienceShouldBeRejected` may pass **solely due to the broken signature**, even if `AudienceRestrictionValidator` was disabled.

**To test a semantic rule**, construct a fixture with the bad field up front and **sign it validly with the trusted test IdP's private key**. All other fields (issuer/recipient/time/correlation) must be valid so execution reaches the target validator.

### How Should Negative Cases Be Built?

| Rule under test | Fixture required |
| --- | --- |
| Signature tampering | Signed fixture with bytes altered inside signed content, without re-signing |
| Untrusted signer | Fixture signed with key B not in IdP A's trusted credentials |
| Wrong issuer | Validly signed fixture with wrong issuer, while independent conditions fit |
| Wrong audience | Wrong audience **before signing**, signature remains valid |
| Wrong destination | Wrong destination before signing |
| Wrong recipient | Wrong Bearer `SubjectConfirmationData` `Recipient` before signing |
| Expired | Expired time conditions, fixture validly signed |
| Future `NotBefore` | `NotBefore` beyond skew, valid signature |
| Wrong `InResponseTo` | Signed response referencing a non-existent/mismatched request ID |
| Missing signature | Response/Assertions missing required signature |
| Replay | Same signed assertion/response submitted multiple times while still unexpired |

Failure tests should verify **no new `Authentication` is created**. If the framework exposes structured error categories, assert the category; do not regex raw exception messages that might contain PII.

## 11. Response vs. Assertion Signatures and Multi-Assertion

SAML allows signatures on the Response and/or Assertion depending on profile and IdP/SP contract. Spring Security docs describe the corresponding verification logic; do not assume every Assertion always has its own signature if a signed enclosing Response is accepted by the provider.

Your test suite should cover:
1. Signed Response with valid assertions.
2. Signed Assertion inside a Response per contract.
3. Both Response and Assertion signed.
4. No valid signature.
5. Signed Response whose Assertion was altered after signing.
6. Signed Assertion A with an injected Assertion B in the XML.
7. Duplicate IDs/ambiguous signed references.
8. Wrong signer yet matching NameID/group attributes.
9. Unchecked assertion carrying role `ADMIN`.
10. Multi-assertion with differing statements per provider behavior.

**Never extract attributes from any Assertion that has not passed all required validations.** Tests should verify "the right principal/authorities are built from the verified assertion," not merely that a signature method returned true.

## 12. Issuer, registrationId, and Tenant Isolation

Suppose the SP trusts two IdPs:
- `https://idp-hr.example.org` with key A.
- `https://idp-partner.example.org` with key B.

Both IdPs might issue NameID `alex` or the same email. That does not prove the same person.

Risks:
- Tests share one verification certificate across all registrations;
- `AuthnRequest` targets IdP A, but the ACS resolver picks B;
- Assertion `Issuer` differs from Response `Issuer`;
- URL `registrationId` does not match the configured IdP;
- Signed SAML response from another tenant grants local admin due to a matching email;
- Environment metadata rotation fails while tests only use one mocked provider.

Tests needed:
1. Signed fixture A is accepted under registration A when valid.
2. Signed fixture B is **not** accepted under A.
3. Wrong issuer is rejected even if NameID matches.
4. Untrusted cert is rejected even if XML signature is internally self-consistent.
5. Local account mapping is scoped by IdP issuer and stable external subject.
6. If IdP-initiated login is enabled, routing/registration inference preserves tenant isolation.

Even when tests prove the signature is valid, post-login authorization must still check business tenant/resource ownership.

## 13. Audience, Destination, and Recipient Are Three Distinct Requirements

| SAML field | Meaning | Negative test |
| --- | --- | --- |
| `AudienceRestriction/Audience` | Target SP entityId permitted to consume the assertion | EntityId of another SP |
| `Response@Destination` | Target where the Response is sent | Internal URL instead of public ACS |
| `SubjectConfirmationData@Recipient` | Endpoint where the bearer assertion is presented | ACS of another tenant/host |
| `InResponseTo` | `AuthnRequest` correlation per flow | Mismatched ID |
| `Issuer` | IdP asserting party | Unregistered issuer |

These fields are **not synonyms**. Audience is typically the SP entityId, whereas Recipient/Destination typically pertain to the ACS URL. A wrong-audience test cannot substitute for a wrong-destination test.

### Reverse Proxy

If the public ACS is `https://sp.example.org/login/saml2/sso/test-idp` but Spring sees an internal HTTP scheme/host, validation can fail even when the IdP behaved properly.

Check:
- SP metadata and `assertionConsumerServiceLocation`.
- Public base URL and entityId.
- Trusted forwarded host/proto headers stripped/overwritten by ingress.
- ACS matcher/`registrationId` in Spring.
- IdP ACS allow-list matches the public URL.
- Multiple pods share identical configuration.

**Never disable Destination/Recipient validation to work around a proxy mismatch.** Mock `Authentication` cannot detect this issue either.

## 14. Time Validation: NotBefore, NotOnOrAfter, and Skew

A SAML response/assertion carries several time-related fields. Verify:
- `Conditions@NotBefore`.
- `Conditions@NotOnOrAfter`.
- `SubjectConfirmationData@NotOnOrAfter`.
- `IssueInstant` per profile.
- NTP/clock skew between SP and IdP.
- Boundaries just before/after expiry.
- Old static fixtures that have expired.

**An XML fixture signed at authoring time may stop working days later.** Never widen clock skew by hours just to make tests pass. Generate signed fixtures with timestamps relative to test execution time or inject a test clock via the framework's supported API.

Example cases:
1. Conditions valid within the window.
2. Future `NotBefore` beyond skew.
3. `NotOnOrAfter` just expired.
4. `SubjectConfirmation` expired while `Conditions` is still valid.
5. Time skew within tolerance.
6. Time skew outside tolerance.
7. Fresh fixture timestamps with an untrusted signature (must fail trust).
8. Valid assertion time with wrong request correlation.

Spring Security supports configuring clock skew on the assertion validator in corresponding API versions. **Do not assume default skew is identical across versions.**

## 15. InResponseTo, Request Repository, and RelayState

In **SP-initiated SSO**, Spring generates an `AuthnRequest` and may persist state/correlation in the session/repository, and the IdP returns a `SAMLResponse` referencing that request. `RelayState` tracks browser state/navigation per binding.

**A test that POSTs a Response directly to the ACS without a saved AuthnRequest can legitimately fail due to missing correlation.** Do not disable the `InResponseTo` validator just because a fixture was built out-of-band.

### Testing the Full Flow Properly

~~~text
1. GET /saml2/authenticate/test-idp
2. SP generates AuthnRequest ID and saves request state
3. Test IdP reads AuthnRequest from redirect/binding
4. Test IdP builds validly signed Response:
     Valid InResponseTo
     Valid Recipient/Destination
     Valid Audience
     Valid time conditions
5. Browser/test client POST SAMLResponse + RelayState
   with same browser session/cookie
6. SP parses/verifies/correlates, creates Authentication
7. Subsequent request to protected route, check principal/role
~~~

To test negative correlation, build a **validly signed response** with an `InResponseTo` from another request or missing state per policy.

### IdP-Initiated SSO

An unsolicited IdP-initiated Response may lack an `AuthnRequest`/`InResponseTo` when that integration mode is permitted. Evaluate separately:
- Whether unsolicited SSO is explicitly enabled;
- Whether issuer/trust/audience/recipient/time are still enforced;
- Lack of request-bound CSRF/correlation; login CSRF/identity confusion risk;
- `RelayState`/open-redirect policy;
- Which IdPs are allowed to initiate flows.

**Do not assume "`InResponseTo` is always mandatory" for every product/flow**, and likewise do not strip SP-initiated correlation protection merely to accept unsolicited responses.

## 16. Replay: Even a Signed Assertion Can Be Reused

An XML Signature remains completely valid when an attacker or browser automation replays the same Response. A signature proves content integrity and origin—**it does not prove the assertion has never been used before**.

Defense layers:
- `Condition`/`SubjectConfirmation` expiry;
- `AuthnRequest` correlation and state consumption;
- `OneTimeUse` condition if issued by the IdP;
- Replay cache for assertion/response IDs if required by policy;
- Session binding;
- Cluster-wide store and atomic check across multiple nodes;
- Narrow validity windows and monitoring.

**Do not assume Spring Security enables a global replay cache by default in every version.** OpenSAML provider documentation allows adding `OneTimeUseConditionValidator` via customization; test explicitly if business rules require "an assertion is accepted only once."

### Replay Cases That Must Be Distinguished

| Test | What it proves |
| --- | --- |
| Same `SAMLResponse` re-submitted in the same session | Request correlation/one-time state works |
| Replay while response is still unexpired | Not merely blocked by the time validator |
| Replay after expiration | Only proves expiry denial if anti-replay control is absent |
| Replay across another session | State does not rely on a single browser |
| Replay across another pod | Shared replay/correlation store when needed |
| Concurrent replay | Atomic consume prevents race conditions |
| Same Assertion ID, different Response ID | Assertion-level replay policy |
| With `OneTimeUse` condition | Validator actually enforces `OneTimeUse` |

If using only an in-JVM `HashSet`, never claim multi-pod/multi-node replay protection.

## 17. EncryptedAssertion and Decryption Cannot Be Mocked

SAML can include:
- `EncryptedAssertion`;
- `EncryptedID`;
- `EncryptedAttribute`.

Spring Security/OpenSAML require matching decryption credentials in `RelyingPartyRegistration`. **Signing keys and encryption keys are not necessarily the same**. A mock `Authentication` cannot check:
- Does the SP private key match the encrypted test assertion?
- Is the assertion decrypted and then verified/validated in the right order?
- Are encrypted attributes dropped during role mapping?
- Does key/certificate rotation break login?

Fixture suite should cover:
1. Unencrypted signed baseline if allowed by profile.
2. `EncryptedAssertion` encrypted with SP test public key; app decrypts successfully.
3. Wrong SP decryption key; fails.
4. Corrupted ciphertext; fails.
5. `EncryptedID`/`EncryptedAttribute` if used in production.
6. Signed Response containing an encrypted assertion.
7. Signed Assertion with encrypted attributes.
8. Key rotation overlap using test certificates.

**Never use production signing/decryption private keys in CI.** Keep test IdP and SP test key pairs independent. All test artifacts must avoid real user data.

## 18. Parsers and XML Signature Wrapping

Beyond signatures, XML introduces security cases to verify:
- XML DTD/external entity resolution (XXE);
- Entity expansion/oversized XML/DoS;
- Duplicate XML IDs;
- Signature reference not pointing to the assertion consumed by the app;
- Multiple assertions/conflicting `AttributeStatement` elements;
- Namespace confusion/canonicalization;
- Untrusted `X509Data` embedded in XML;
- Malformed Base64/invalid XML;
- XML parser never fetching URLs/files from input.

Never parse SAML with regex to extract `NameID`. Use OpenSAML/Spring Security with hardened security settings.

### Sample Payload for Parser-Negative Testing

~~~xml
<!DOCTYPE samlp:Response [
  <!ENTITY fake SYSTEM "file:///nonexistent-test-only">
]>
<samlp:Response
    xmlns:samlp="urn:oasis:names:tc:SAML:2.0:protocol">
  <samlp:Status>&fake;</samlp:Status>
</samlp:Response>
~~~

This payload only illustrates the entity risk and is **not a SAML success fixture**. Negative tests must ensure the parser refuses to resolve external entities and creates no `Authentication`. Never point test fixtures at sensitive files or network targets.

## 19. Designing Safe Signed Fixtures

To build a genuine valid fixture:
1. Create a dedicated **test IdP entityID**.
2. Use a **test signing private key**, placing its public cert into the SP's trusted test verification credentials.
3. Use exact SP entityId, public ACS, and `registrationId`.
4. Generate an `AuthnRequest` ID and correlate state when testing SP-initiated flow.
5. Set valid Response/Assertion time conditions.
6. Choose the proper signing scope: signed Response or Assertion per profile.
7. Compute the XML Signature after populating all signed fields.
8. Use synthetic principal/attributes, never real emails/PII.
9. Encode properly for HTTP-POST binding.
10. Clear/rotate state if tests run in parallel or across nodes.

You can use a standalone test IdP or a well-tested OpenSAML fixture factory. **Do not "sign" by pasting a fake `SignatureValue` tag** and do not treat Base64 encoding as a substitute for signing.

### Three Fixture Categories

**VALID:** signed/trusted, valid audience/recipient/issuer/time/correlation.

**INVALID_CRYPTO:** unsigned, tampered signature, untrusted certificate, wrong reference.

**INVALID_SEMANTIC_BUT_SIGNED:** wrong audience/destination/recipient/issuer/time/correlation where the **signature remains valid** under the trusted lab key. This third group is essential to prove semantic validators actually execute.

### Controlling Fixture Freshness

- Generate fixtures against a test clock rather than checking in expired static responses.
- Avoid colliding random IDs across test runs.
- For replay tests, **intentionally** reuse the ID and capture the control run.
- Document fixture provenance, issuer, signing key alias (not private key), and expected rule.
- Never include test IdP trust certificates in production SP configuration outside an approved migration process.
- Fixtures captured from a SaaS staging IdP may hold state valid for only a few minutes; do not replay them days later to test positive login.

## 20. Provider-Level Tests: Focused on Validation, Not Full E2E

At T2, use:
- `Saml2AuthenticationToken` carrying a real Base64 `SAMLResponse` per your version's constructor/API.
- Real OpenSAML provider.
- `RelyingPartyRegistration` with the test IdP verification certificate and test SP decryption credential.
- Valid and invalid signed fixtures.
- Production-like response/assertion validators.

Check:
- Valid fixture → `Authentication` succeeds per policy.
- Invalid fixture → `AuthenticationException` or failure result; no `Authentication` created.
- Principal/attributes/authorities match the verified assertion.
- Error category if structured evidence is available.

**Do not pass a pre-constructed `Saml2Authentication` into a provider test.** It is the output of authentication, not the `SAMLResponse` input to verify.

### Limitations of Provider Tests

They do not verify:
- That the ACS URL receives POSTs properly;
- CSRF filter exceptions/matchers;
- `AuthnRequest` repository persistence/correlation across the browser;
- Session fixation/cookie persistence;
- Reverse proxy `X-Forwarded-Host`/`Proto` and TLS;
- Browser HTML POST form encoding;
- Redirects and `RelayState`;
- Operational metadata fetching/certificate rollover.

That is why T3 and T4 are required.

## 21. ACS HTTP Integration Tests with MockMvc

Spring Security's default ACS typically expects:

~~~http
POST /login/saml2/sso/test-idp HTTP/1.1
Host: sp.example.org
Content-Type: application/x-www-form-urlencoded
Cookie: JSESSIONID=[TEST_SESSION]

SAMLResponse=[BASE64_SIGNED_RESPONSE]&RelayState=[STATE]
~~~

Bracketed strings are illustrative placeholders, not valid credentials.

### Spring Boot Test Skeleton

~~~java
package com.example.saml;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.mock.web.MockHttpSession;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;

@SpringBootTest
@AutoConfigureMockMvc
class SamlAcsIntegrationTest {

    @Autowired
    MockMvc mvc;

    @Test
    void malformedSamlResponseIsProcessedBySecurityChain()
            throws Exception {

        MockHttpSession browser = new MockHttpSession();
        var response = mvc.perform(
                post("/login/saml2/sso/test-idp")
                        .session(browser)
                        .param("SAMLResponse", "not-base64"))
                .andReturn();

        // Skeleton only: replace with assertions that:
        // 1. No successful Saml2Authentication exists in browser state.
        // 2. A protected route stays inaccessible after callback.
        // 3. The configured failure handler was invoked.
        // 4. No sensitive SAML data appears in response/logs.
        org.junit.jupiter.api.Assertions.assertNotNull(response);
    }
}
~~~

**Explicit limitation:** asserting `assertNotNull(response)` alone **does not prove the verifier rejected it**; this skeleton only shows how an HTTP request hits the ACS in the test app. Production tests must add assertions matching the project's session/response contract. `@SpringBootTest` must actually load the `SecurityFilterChain` and OpenSAML provider without mocking the manager. If the test lacks a relying party registration, the callback may fail on configuration before XML parsing even runs.

### More Complete Integration Flow

~~~text
arrange:
  Boot app + real SecurityFilterChain
  IdP test cert in RelyingPartyRegistration
  Real AuthnRequest repository/session
  Test IdP with matching signing key pair
  Test browser starts GET /saml2/authenticate/test-idp

act:
  Test IdP reads AuthnRequest ID
  Create signed SAMLResponse with exact InResponseTo/Recipient/Audience
  Browser uses same cookie/session to POST SAMLResponse + RelayState

assert:
  ACS/filter/provider succeeds or fails per fixture
  Valid response creates proper principal/role/account session
  Invalid response creates no new Authentication
  Protected endpoint after login matches expectation
  No SAMLResponse/PII leaked in HTTP response/logs
~~~

### Checking CSRF

IdP HTTP-POSTs to the ACS do not normally include the Spring app's CSRF token. Spring SAML2 integration handles the callback per framework design; if adding custom security chains or CSRF matchers, test them explicitly. **Never disable CSRF app-wide** just because the ACS returned 403; inspect filter order, matchers, callback path, HTTP method, and `Content-Type`.

### Interpreting HTTP 302 Properly

- Redirect to a protected return URL after login may indicate success.
- Redirect to login/error may indicate failure.
- HTTP status 302 is not a SAML `StatusCode`.
- Use the browser/session on a subsequent request to confirm whether the user **is actually authenticated**.

## 22. Checking Local User/Role Mapping After Protocol Validation

The provider may produce a `Saml2Authentication` containing a NameID and SAML attributes. The application must still:
- Look up the app account by stable identity + issuer scope;
- Never auto-link by email/UPN solely because a claim matches;
- Check `ACTIVE` account status and tenant membership;
- Map group attributes → local `GrantedAuthorities` per approved policy;
- Handle multi-valued `AttributeStatement` elements properly;
- Check resource ownership and object-level ACLs;
- Invalidate/refresh sessions/roles when a user is disabled or changes organization;
- Avoid granting `ADMIN` from an arbitrary unchecked `groups` attribute.

Compare:

~~~text
Mock:
  username = linh
  roles = [FINANCE_ADMIN]
  expected = 200

Real SAML:
  NameID = opaque-4ab2
  groups = [finance-viewers]
  app account = DISABLED
  resource tenant = people
  expected = DENY
~~~

The two outcomes **do not contradict each other**. The mock test never passed through verified SAML identity + account policy.

## 23. Replay Tests Require Multi-Session and Multi-Node Coverage When SLA Demands It

Special caveat: replaying the same `SAMLResponse` after several minutes might fail simply due to expiration. To genuinely test replay:
1. Use a validly signed, unexpired assertion.
2. Perform a valid initial login.
3. Replay the exact same response/assertion before expiry.
4. Retry within the same session, a different session, and another node matching topology.
5. If `OneTimeUse` is required, verify the validator/cache enforces it.
6. Test concurrent duplicate submissions and atomicity.
7. Track Assertion ID/Response ID per policy without logging raw XML/tokens.
8. Never allow session B to inherit A's `Authentication`.

**Never claim "replay prevented" merely because an IdP-generated test Response expired.** Likewise, never assume every Spring Security setup has a distributed replay cache enabled.

## 24. Validator Customization and Upgrading Spring Security

Spring Security versions differ:
- Spring Security 6.x uses the OpenSAML provider matching dependencies (`OpenSaml4AuthenticationProvider` or `OpenSaml5AuthenticationProvider` when supported).
- Spring Security 7.x reference defaults to `OpenSaml5AuthenticationProvider`.
- Response/Assertion validator hooks, decryption, and principal conversion can change across versions.
- Migration to 7 changes the ordering of response validation and assertion validation.
- `OneTimeUseConditionValidator` may require custom registration when needed.
- A custom `ResponseValidator` or `AssertionValidator` can **replace default rules** if wired through the wrong API.

Test the following after every upgrade:
1. Valid signed responses are still accepted.
2. Invalid/unsigned/untrusted signers are still rejected.
3. Signed fixtures with wrong audience/recipient/destination/time still fail.
4. Request correlation/`RelayState` still work.
5. Decryption and principal mapping did not change unexpectedly.
6. Replay policy remains intact.
7. Failure handlers and session persistence never grant `Authentication` after an invalid response.

**Never disable or remove default validators just for test convenience.** When adding custom checks, compose with the default validator via the official API and write negative tests for the default rules too.

## 25. Recommended Negative Test Matrix

| Group | Fixture/input | Expected |
| --- | --- | --- |
| XML | Malformed Base64 | No authentication |
| XML | Invalid XML/DTD/XXE | No authentication, no external entity reads |
| Signature | Unsigned response/assertions | Rejected per signing policy |
| Signature | Tampered signed bytes | Signature failure |
| Signature | Trusted signature protecting wrong element | Wrong content not used |
| Trust | Valid signature with untrusted test cert | Rejected |
| Issuer | Signed response issuer differs from registration | Rejected |
| Tenant | Same NameID under another IdP | Does not map to shared account |
| Audience | Wrong audience, validly signed | Audience rejection |
| Destination | Wrong ACS destination, validly signed | Destination rejection |
| Recipient | Wrong bearer recipient, validly signed | `SubjectConfirmation` rejection |
| InResponseTo | Different saved request, validly signed response | Correlation rejection per flow |
| Time | Expired signed assertion | Expiry rejection |
| Time | Future `NotBefore` beyond skew | Time rejection |
| Status | SAML non-Success status | No authentication |
| Encryption | Correct test SP private key | Succeeds if valid |
| Encryption | Wrong decryption key | No authentication |
| Replay | Second use before expiry | Denied if one-time policy required |
| Multiple assertions | Unsigned injected assertion | Not used |
| RelayState | Arbitrary external return URL | No open redirect |
| Session | Invalid response after previous session | No new session or privilege escalation |
| Reverse proxy | Wrong forwarded Host/Proto | Do not remove validation; fix URL config |
| Browser | SameSite/session state | E2E passes if environment permits |
| Authorization | Valid SAML but disabled app account | Deny |
| Multi-node | Saved request/replay state on another pod | Matches policy |
| Rotation | New IdP test cert | Trust updates per approved metadata |

### Why Must Fixtures Be Isolated?

If you alter audience without re-signing, the signature validator may reject it first. If a fixture is both expired and signed with the wrong key, the test does not prove the expiry validator works. If `InResponseTo` is wrong and there is no saved request, the test only proves the repository is empty. **Ensure only one condition fails whenever testing a specific validator.**

## 26. Standalone Java 17: Classifying Test Evidence Strength

The following program does not parse SAML, generate certificates, or replace OpenSAML/Spring. It simulates an **evidence classifier**: whether a test mocks `SecurityContext`, uses a real provider + signed trusted fixture, includes semantic negative cases, and runs ACS/IdP E2E.

File `SamlTestEvidenceDemo.java`:

~~~java
public final class SamlTestEvidenceDemo {

    record Evidence(
            boolean mockAuthentication,
            boolean realProvider,
            boolean signedFixture,
            boolean trustedTestKey,
            boolean semanticNegativeCases,
            boolean acsHttpFlow,
            boolean browserIdpFlow) {
    }

    static String classify(Evidence e) {
        if (e.mockAuthentication()) {
            return "MOCK_AUTHORIZATION_ONLY";
        }
        if (!e.realProvider()) {
            return "NO_REAL_VERIFIER";
        }
        if (!e.signedFixture()) {
            return "NO_VALID_SIGNED_FIXTURE";
        }
        if (!e.trustedTestKey()) {
            return "NO_TRUST_VALIDATION";
        }
        if (!e.semanticNegativeCases()) {
            return "VALIDATOR_COVERAGE_INCOMPLETE";
        }
        if (!e.acsHttpFlow()) {
            return "PROVIDER_VALIDATION_ONLY";
        }
        if (!e.browserIdpFlow()) {
            return "ACS_INTEGRATION_ONLY";
        }
        return "BROWSER_E2E_COVERED";
    }

    public static void main(String[] args) {
        System.out.println("Mock user: " + classify(
                new Evidence(true, false, false, false,
                        false, false, false)));
        System.out.println("Mock manager: " + classify(
                new Evidence(false, false, false, false,
                        false, true, false)));
        System.out.println("Unsigned XML: " + classify(
                new Evidence(false, true, false, false,
                        false, true, false)));
        System.out.println("Untrusted key: " + classify(
                new Evidence(false, true, true, false,
                        false, false, false)));
        System.out.println("Happy path only: " + classify(
                new Evidence(false, true, true, true,
                        false, false, false)));
        System.out.println("Verifier: " + classify(
                new Evidence(false, true, true, true,
                        true, false, false)));
        System.out.println("ACS integration: " + classify(
                new Evidence(false, true, true, true,
                        true, true, false)));
        System.out.println("Full E2E: " + classify(
                new Evidence(false, true, true, true,
                        true, true, true)));
    }
}
~~~

Run:

~~~bash
javac SamlTestEvidenceDemo.java
java SamlTestEvidenceDemo
~~~

**Exact** stdout:

~~~text
Mock user: MOCK_AUTHORIZATION_ONLY
Mock manager: NO_REAL_VERIFIER
Unsigned XML: NO_VALID_SIGNED_FIXTURE
Untrusted key: NO_TRUST_VALIDATION
Happy path only: VALIDATOR_COVERAGE_INCOMPLETE
Verifier: PROVIDER_VALIDATION_ONLY
ACS integration: ACS_INTEGRATION_ONLY
Full E2E: BROWSER_E2E_COVERED
~~~

**Limitation:** all Booleans are self-declared by the developer; this is **not a cryptographic verifier or SAML test runner**. In CI, evidence must include test reports, fixture provenance, provider execution, and staging E2E logs. Even `BROWSER_E2E_COVERED` does not prove every attack vector has been tested.

## 27. Staging IdP/Browser E2E Catches Bugs Mocks Miss

A real browser test must cover:
- Public HTTPS for both SP and IdP;
- Correct Entity IDs/metadata/ACS URLs;
- Redirect binding for `AuthnRequest`;
- HTTP-POST binding for `SAMLResponse`;
- Browser cookies/`SameSite`/sessions;
- `RelayState`/request repository;
- MFA/IdP conditional access per policy;
- Reverse proxy TLS/forwarded headers;
- Certificate rollover and metadata refresh;
- Post-login user/tenant/role mapping;
- Session fixation/logout if required;
- Multi-node auth state;
- Real NTP/clock skew.

**MockMvc does not fully simulate cross-domain browser cookies, proxy TLS, or IdP sessions.** T3 success does not guarantee T4 success, and T4 happy-path success does not replace T2 negative verifier tests.

### Staging Safety

- Never copy IdP production private keys into tests.
- Never configure a production SP to trust test signing certificates outside an approved migration.
- Never save real `SAMLResponse` payloads containing PII in CI logs.
- Never disable certificate verification when a proxy fails.
- Never open wildcard issuer/audience/ACS values just to make tests pass.
- Use isolated test subjects and test tenants.
- Clean up test sessions and replay records between runs.

## 28. Common Test Design Mistakes

| Anti-pattern | Why it's wrong | Replace with |
| --- | --- | --- |
| Only `@WithMockUser` | Never reaches verifier | Signed provider/ACS tests |
| Mock `AuthenticationManager` | Skips signature/trust/validators | Real OpenSAML provider |
| Craft unsigned XML and expect success | Encourages disabling security checks | Test IdP signing with test key |
| Wrong audience by breaking signature | Fails to isolate audience check | Build wrong audience then re-sign |
| Trust self-declared cert inside XML | Trust poisoning | Registered IdP trusted credentials |
| Disable `InResponseTo` when state is missing | Loses correlation protection | Initiate `AuthnRequest` first |
| Assert only HTTP 302 | Cannot tell success from failure | Check `SecurityContext` and protected route |
| Use NameID/email as global account key | Tenant confusion/takeover | Issuer-scoped subject binding |
| Expired static fixture, disable time validation | Weakens security | Fresh signed fixtures/test clock |
| Replay test after expiry | Tests time, not replay | Reuse before expiry |
| Skip encrypted assertion tests | Production decryption may break | Test dedicated encryption keys |
| ACS returns CSRF 403, disable CSRF site-wide | Web routes lose CSRF defense | Fix ACS matcher/filter config |
| Skip multiple-assertion tests | May consume unsigned data | Signature-scope negative cases |
| Production signing key in CI | Exposes root of trust | Test-only keypairs |
| E2E happy path without negative cases | Only proves interoperability | Add signed semantic negative tests |
| Skip disabled local account tests | Valid SAML could still grant access | App account gate and ACL tests |
| Upgrade Spring/OpenSAML running only mocks | Misses validator regressions | Re-run T2/T3/T4 |

## 29. Logging and Runbook for Investigating Test Failures

When a SAML login/test fails:
1. Determine whether the test is T1/T2/T3/T4.
2. Check whether the request hit the `AuthnRequest` endpoint or the ACS.
3. Confirm no mocked `AuthenticationManager` is present.
4. Check signed fixture freshness and test certificate trust.
5. Check SAML `Issuer`, SP entity ID, and `registrationId`.
6. Check `Destination`, `Recipient`, and `Audience` independently.
7. Check `InResponseTo`, saved `AuthnRequest`, and `RelayState`.
8. Check `NotBefore`, `NotOnOrAfter`, and clock skew.
9. Check decryption keys if using encrypted assertions.
10. Check the actual failure status/handler and `SecurityContext`.
11. Check principal/attributes/local roles and account state.
12. For E2E, check cookies, HTTPS, proxy, metadata, and NTP.
13. Verify whether negative cases actually preserved a valid signature.
14. Never remove validation to fix a red test; fix the fixture/flow/config root cause.

### Sample Redacted Event

~~~json
{
  "event": "saml_authentication_failed",
  "traceId": "saml-opaque-test-001",
  "registrationId": "test-idp",
  "category": "AUDIENCE_VALIDATION",
  "fixtureId": "signed-wrong-audience",
  "result": "DENY"
}
~~~

This is an internal log example, not a default Spring event. If the provider only returns a generic failure, do not fabricate categories by parsing raw messages. Never log raw `SAMLResponse`/XML, NameIDs, Attributes, cookies, private keys, or session IDs.

Metric labels should only use approved registration aliases or categorical reasons, never user emails or high-cardinality assertion IDs.

## 30. Testing When Upgrading Spring Security/OpenSAML

On every upgrade:
1. Confirm the default provider version.
2. Verify custom response/assertion validators still **include default checks**.
3. Run the valid signed fixture.
4. Run invalid signature/untrusted cert/wrong issuer cases.
5. Run signed wrong audience/recipient/destination/time/`InResponseTo` cases.
6. Run encrypted fixtures if used.
7. Run replay/`OneTimeUse` tests per policy.
8. Verify principal converter/authority mapping.
9. Verify request repository/`RelayState`.
10. Run browser staging E2E with proxy/cert rollover.

Spring Security 7 documentation notes changes in response/assertion validation ordering and principal conversion. Do not assume 6.x APIs for `OpenSaml4AuthenticationProvider` and 7.x APIs for `OpenSaml5AuthenticationProvider` are identical.

## 31. Pre-Release QA Checklist

- [ ] T1 mock authorization, T2 provider, T3 ACS, and T4 staging IdP layers are clearly separated.
- [ ] Mock `Authentication` is never used as proof of SAML signature validation.
- [ ] T2/T3 run the real OpenSAML provider without mocking `AuthenticationManager`.
- [ ] `RelyingPartyRegistration` points to the right test IdP trusted certificate.
- [ ] Positive fixtures have valid signatures and unexpired timestamps.
- [ ] Tampered/unsigned/untrusted-cert payloads are rejected.
- [ ] Wrong issuer/audience/destination/recipient fixtures are **validly signed** to isolate each rule.
- [ ] Time tests cover fresh signed fixtures, boundaries, and clock skew.
- [ ] SP-initiated tests persist `AuthnRequest`/session/`RelayState` properly.
- [ ] IdP-initiated unsolicited flow has an explicit policy if supported.
- [ ] Multiple assertions/signature references/XXE/oversized XML have negative tests.
- [ ] Replay tests run before expiry and across sessions/nodes if policy requires.
- [ ] `OneTimeUse`/replay cache is never assumed active without testing.
- [ ] Encrypted assertions/decryption use a test SP keypair, never a production key.
- [ ] Real ACS POSTs pass through `SecurityFilterChain` and the provider.
- [ ] Failures never create an `Authentication` or escalate privileges.
- [ ] HTTP 200/302 alone is never used to prove login success.
- [ ] Principal/attributes/roles derive from verified assertions and the app account gate.
- [ ] Disabled users or wrong tenants are blocked even with a valid assertion.
- [ ] Browser E2E verifies metadata, HTTPS/ACS, cookies, `SameSite`, proxy, and MFA.
- [ ] Certificate rollover and metadata refresh have integration tests.
- [ ] Signature/time/audience validators are never disabled just to get green tests.
- [ ] Test-only keys and fixtures contain no real user data.
- [ ] Logs/metrics never expose `SAMLResponse`/keys/PII/tokens.
- [ ] Test reports explicitly state evidence tiers and remaining limitations.

## 32. Review Questions and Answers

**Q1.** Does a passing `@WithMockUser(roles="ADMIN")` test prove the IdP signed properly?

**Answer:** No. It injects a fake `SecurityContext` and never runs the SAML verifier.

**Q2.** Is `MockMvc.with(user("linh"))` a SAML login from the IdP?

**Answer:** No, it is a request post-processor that creates a mock user.

**Q3.** Does mocking `AuthenticationManager` to return `Saml2Authentication` check Audience?

**Answer:** No, if the real provider is not invoked.

**Q4.** Is a `SAMLResponse` containing `StatusCode` `Success` and `NameID` already valid?

**Answer:** Not yet. Valid XML signature, trust, conditions, and correlation are required.

**Q5.** If changing Audience after signing causes rejection, does that prove `AudienceRestrictionValidator` works?

**Answer:** Not necessarily. The signature broke first. You must re-sign the wrong-audience response with a trusted test key.

**Q6.** Is an assertion signed by IdP B treated as belonging to IdP A if the NameID matches?

**Answer:** No. Issuer, certificate, and relying party registration must match.

**Q7.** Are Audience and Recipient the same thing?

**Answer:** No. Audience targets the SP entityId; Recipient targets the ACS receiving the bearer assertion per profile.

**Q8.** Why can a direct POST to the ACS without an `AuthnRequest` fail?

**Answer:** Missing `InResponseTo`/request repository correlation in an SP-initiated flow.

**Q9.** Is `RelayState` the signature of the SAML Response?

**Answer:** No. It correlates binding state/navigation and must be protected against tampering/open redirects.

**Q10.** Can a validly signed assertion be replayed?

**Answer:** Yes. A signature does not prove one-time use; expiry, correlation, and caching per policy are required.

**Q11.** Does replaying after expiry prove the global replay cache works?

**Answer:** No. The time validator alone may have rejected it.

**Q12.** Which default SAML2 provider does Spring Security 7 reference?

**Answer:** `OpenSaml5AuthenticationProvider`, depending on actual version configuration.

**Q13.** Does HTTP 302 at the ACS prove login succeeded?

**Answer:** No. It could be a failure redirect; verify `SecurityContext` and a protected route.

**Q14.** Does a passing provider test prove `SameSite` cookies work in a real browser?

**Answer:** No, staging browser E2E is required.

**Q15.** What does `EncryptedAssertion` require to be processed?

**Answer:** Matching SP decryption private key/config alongside signature/trust/conditions validation.

**Q16.** Can a valid SAML Response log in a user disabled in the app?

**Answer:** It must not. The app-local account gate must deny per policy even when the protocol payload is valid.

**Q17.** When upgrading Spring Security, is running only mock tests enough?

**Answer:** No; signed provider/ACS/E2E regression tests are required.

**Q18.** Does a passing happy-path staging login prove there are no XML Signature Wrapping bugs?

**Answer:** No. Negative verifier/security tests are required.

**Q19.** Why not use the production IdP signing private key in CI?

**Answer:** Risk of compromising signing authority; use test-only keypairs.

**Q20.** If several negative cases all fail with `SIGNATURE_INVALID`, does that mean all semantic validators were tested?

**Answer:** No. Perhaps none reached the semantic validators; fix the fixtures so their signatures remain valid.

## 33. Conclusion

**Mock authentication is a great tool for testing authorization assuming a user is already authenticated. It is not proof that the SP can verify a real SAML Response.**

To test the SAML validator:
1. Use the **real provider** with a trusted test IdP key and **signed fixtures**.
2. Test signature, issuer, audience, recipient, destination, time, and request correlation using **independent negative fixtures**, validly signed for semantic failures.
3. Test the ACS Servlet filter, saved `AuthnRequest`, `RelayState`, and `SecurityContext`.
4. Test replay/`OneTimeUse` if policy requires; never assume every version enables caching.
5. Test decryption, multi-assertion handling, and XML parser safety.
6. Run staging IdP/browser E2E to test proxies, cookies, metadata, and interoperability.
7. Keep SAML authentication separate from local user/role/resource authorization.
8. Never disable validation just to make tests pass.

**Right mindset:** mocking answers "given an `Authentication`, how does the app handle it?"; the real verifier answers "was this SAML Response genuinely confirmed by a trusted IdP for the right SP, unexpired, matching the request, and policy-compliant?". Only by measuring both questions properly are QA results honest.

### Official Documentation

1. Spring Security — SAML2 Login Overview, ACS filter, and OpenSAML provider: https://docs.spring.io/spring-security/reference/servlet/saml2/login/overview.html
2. Spring Security — Authenticating SAML Responses, validators/decryption/OneTimeUse: https://docs.spring.io/spring-security/reference/servlet/saml2/login/authentication.html
3. Spring Security — AuthnRequest and Request Repository: https://docs.spring.io/spring-security/reference/servlet/saml2/login/authentication-requests.html
4. Spring Security — Running Test as User in MockMvc (@WithMockUser/user/authentication): https://docs.spring.io/spring-security/reference/servlet/test/mockmvc/authentication.html
5. Spring Security — MockMvc integration: https://docs.spring.io/spring-security/reference/servlet/test/mockmvc/
6. Spring Security — SAML2 migration 7: https://docs.spring.io/spring-security/reference/migration-7/saml2.html
7. OASIS — SAML 2.0 Core: https://docs.oasis-open.org/security/saml/v2.0/saml-core-2.0-os.pdf
8. OASIS — SAML 2.0 Profiles: https://docs.oasis-open.org/security/saml/v2.0/saml-profiles-2.0-os.pdf
9. OASIS — SAML 2.0 Bindings: https://docs.oasis-open.org/security/saml/v2.0/saml-bindings-2.0-os.pdf
10. W3C — XML Signature Syntax and Processing 1.1: https://www.w3.org/TR/xmldsig-core1/
11. OWASP — SAML Security Cheat Sheet: https://cheatsheetseries.owasp.org/cheatsheets/SAML_Security_Cheat_Sheet.html
