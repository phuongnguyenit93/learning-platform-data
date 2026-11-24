# Testing Expired, Not-Yet-Valid, and Clock-Skewed Assertions in SAML 2.0

> **Module:** Spring Security – federation · **Group:** SAML2 Testing. This lesson guides you through designing and running tests for **SAML Assertion validity windows** in Web Browser SSO flows: `Conditions@NotBefore`, `Conditions@NotOnOrAfter`, `SubjectConfirmationData@NotOnOrAfter`, `IssueInstant`, `AuthnInstant`, `SessionNotOnOrAfter`, and **clock skew** between the IdP (Identity Provider) and SP (Service Provider). It covers exact boundary equality, millisecond precision, bidirectional clock skew, Spring Security/OpenSAML configuration, ACS negative tests, management of validly signed fixtures, and a standalone Java 17 program to verify temporal rules. Domains and data below are illustrative examples.

## 1. Why Test Time Validity Even When the Signature Is Valid?

When a user logs in via SAML2, the Identity Provider issues a `Response` containing an `Assertion`, and the browser POSTs it to the Service Provider's Assertion Consumer Service (ACS). Suppose the IdP's signature is verified using a trusted certificate and `Issuer` matches. **That is still not enough**: an expired or not-yet-valid Assertion must never be accepted merely because the signer is the right IdP.

Typical scenario:

```text
Identity Provider clock = 10:00:00 UTC
Service Provider clock  = 09:58:00 UTC

SAML Assertion:
  NotBefore    = 10:00:00 UTC
  NotOnOrAfter = 10:05:00 UTC

SP reads timestamp using local clock 09:58:00:
  -> assertion is not yet valid.

Conversely, when SP is ahead of IdP:
  -> a freshly issued assertion may be evaluated as already expired
     near the end of the validity window.
```

Distributed systems, containers, domain controllers, proxies, and IdPs can experience clock drift. A small **allowed clock skew** prevents false SSO failures caused by a few seconds of clock offset. However, widening it too far—such as allowing tens of minutes or hours—inadvertently extends the reuse window for expired Assertions.

**Goal:** Accurately reject invalid Assertions, allow **bounded and measured** clock tolerance, and keep signature, issuer, audience, recipient, correlation, and replay checks intact.

### After This Lesson, You Will Be Able To:

1. Explain timestamps and relationships among `Response`, `Assertion`, `Conditions`, `SubjectConfirmationData`, and `AuthnStatement`.
2. Understand that `NotBefore` is **inclusive** and `NotOnOrAfter` is **exclusive**.
3. Test exact equality boundaries, ±1 ms, ±skew, and beyond skew—not just "expired by one day."
4. Know that an Assertion can satisfy `Conditions` yet have an **expired bearer confirmation**.
5. Separate **skew tolerance** from extending Assertion lifetimes, sessions, and replay caches.
6. Configure `OpenSaml5AuthenticationProvider.AssertionValidator.builder().clockSkew(...)` per Spring Security docs and recognize version differences.
7. Build SAML fixtures **validly signed by a test IdP** and adjust timestamps **before signing** to test the right validator.
8. Use Java `Clock.fixed`, `Instant`, and `Duration` for deterministic tests without `Thread.sleep`.
9. Verify negative cases at the ACS/Spring Security: no `Authentication` created, no local authenticated session created, no raw Assertion logged.
10. Implement monitoring and runbooks when NTP, time zones, caches, or IdP/SP clocks drift.

## 2. SAML2 Processing Flow and Where Time Is Checked

```text
Browser                 SP / Spring Security               IdP
   |                            |                           |
   | GET /protected             |                           |
   |--------------------------->|                           |
   |<---------------------------| redirect AuthnRequest     |
   |------------------------------------------------------->|
   |                            |                           |
   |<-------------------------------------------------------|
   |     SAMLResponse with signed Assertion                  |
   |                                                        |
   | POST /login/saml2/sso/corporate                        |
   |--------------------------->|                           |
   |                            | 1. Resolve registration   |
   |                            | 2. Parse/decode Response  |
   |                            | 3. Verify trusted signing |
   |                            | 4. Validate issuer/aud    |
   |                            | 5. Validate time windows  |
   |                            | 6. Validate SubjectConf   |
   |                            | 7. Check InResponseTo     |
   |                            | 8. Enforce replay policy  |
   |                            | 9. Create Authentication  |
   |<---------------------------| success / failure         |
```

Spring Security Servlet SAML2 typically processes requests through `Saml2WebSsoAuthenticationFilter` and `Saml2AuthenticationTokenConverter`, followed by an OpenSAML authentication provider. Current Spring Security documentation describes `OpenSaml5AuthenticationProvider`; older Spring Security 6.x codebases may use `OpenSaml4AuthenticationProvider`. **Do not copy 5.x APIs to another release without checking compatibility.**

**Important:** testing XML timestamps before signature verification only tests a parser/utility. Secure SAML SSO guarantees must be tested **on responses with a valid signature bound to a trusted IdP**. If a test input's timestamp was edited after signing, the failure may come from an **invalid signature**, not the temporal validator.

## 3. Different Time Fields in SAML2

| Attribute | Location | Primary role | Do not confuse with |
| --- | --- | --- | --- |
| `Response@IssueInstant` | `samlp:Response` | Time the protocol response was created; may carry policies rejecting overly old/future responses | Assertion validity window |
| `Assertion@IssueInstant` | `saml:Assertion` | Time the Assertion was created; may drive freshness/max-age rules | `Conditions@NotBefore` |
| `Conditions@NotBefore` | `saml:Conditions` | Earliest instant the Assertion becomes valid | `AuthnInstant` |
| `Conditions@NotOnOrAfter` | `saml:Conditions` | **Exclusive** instant the Assertion expires | `SessionNotOnOrAfter` |
| `SubjectConfirmationData@NotOnOrAfter` | `SubjectConfirmation` with bearer | Deadline for bearer confirmation/presentation at the ACS | Conditions expiration |
| `SubjectConfirmationData@Recipient` | bearer confirmation | Target ACS where subject confirmation is valid | Issuer URL |
| `SubjectConfirmationData@InResponseTo` | bearer confirmation | Correlates `AuthnRequest` in SP-initiated flows | Signature timestamp |
| `AuthnStatement@AuthnInstant` | `saml:AuthnStatement` | When the user authenticated at the IdP; may be earlier due to SSO | Time Response was issued |
| `AuthnStatement@SessionNotOnOrAfter` | `saml:AuthnStatement` | IdP SSO session limit communicated per profile | Bearer Assertion acceptance deadline |
| `Request@IssueInstant` | `samlp:AuthnRequest` | When the SP initiated the request | IdP session lifetime |

A SAML Assertion can contain multiple `AuthnStatement` elements and multiple bearer `SubjectConfirmation` elements. Validators must evaluate the exact **element permitted by the SAML profile**, never grabbing the first timestamp anywhere in the XML.

### 3.1. Illustrative XML

```xml
<samlp:Response
    xmlns:samlp="urn:oasis:names:tc:SAML:2.0:protocol"
    xmlns:saml="urn:oasis:names:tc:SAML:2.0:assertion"
    ID="_response-example"
    Version="2.0"
    IssueInstant="2026-11-07T09:59:50Z"
    Destination="https://portal.example.org/login/saml2/sso/corporate"
    InResponseTo="_request-example">

  <saml:Issuer>https://idp.example.org/saml</saml:Issuer>

  <saml:Assertion ID="_assertion-example"
       Version="2.0"
       IssueInstant="2026-11-07T09:59:50Z">

    <saml:Issuer>https://idp.example.org/saml</saml:Issuer>

    <saml:Subject>
      <saml:NameID>opaque-user-id</saml:NameID>
      <saml:SubjectConfirmation
        Method="urn:oasis:names:tc:SAML:2.0:cm:bearer">
        <saml:SubjectConfirmationData
          InResponseTo="_request-example"
          Recipient="https://portal.example.org/login/saml2/sso/corporate"
          NotOnOrAfter="2026-11-07T10:02:00Z"/>
      </saml:SubjectConfirmation>
    </saml:Subject>

    <saml:Conditions
        NotBefore="2026-11-07T09:59:00Z"
        NotOnOrAfter="2026-11-07T10:05:00Z">
      <saml:AudienceRestriction>
        <saml:Audience>https://portal.example.org/sp</saml:Audience>
      </saml:AudienceRestriction>
    </saml:Conditions>

    <saml:AuthnStatement
        AuthnInstant="2026-11-07T09:45:00Z"
        SessionNotOnOrAfter="2026-11-07T17:00:00Z">
      <saml:AuthnContext>
        <saml:AuthnContextClassRef>
          urn:oasis:names:tc:SAML:2.0:ac:classes:PasswordProtectedTransport
        </saml:AuthnContextClassRef>
      </saml:AuthnContext>
    </saml:AuthnStatement>
  </saml:Assertion>
</samlp:Response>
```

**This is an XML reading-comprehension fixture lacking `ds:Signature`, so it is not a SAML Response permitted to log in to production.** For integration tests, validly sign with a test IdP key and include full elements/signatures/references/metadata. Editing XML after signing invalidates the signature. `NameID` is a synthetic string—never put real users in fixtures.

### 3.2. Why Do Bearer and Conditions Have Separate Deadlines?

In the example above, `Conditions@NotOnOrAfter=10:05`, while bearer `SubjectConfirmationData@NotOnOrAfter=10:02`. An SP using bearer Web SSO must not accept the Assertion at 10:03 merely because `Conditions` is still valid: **the bearer confirmation has expired**. Depending on profile, distinct confirmations may be evaluated independently; never arbitrarily "pick the largest expiry across all elements."

### 3.3. AuthnInstant Can Be Older While Response Is Fresh

In SSO, a user logs in at the IdP at 09:00, opens app B at 09:50, and the IdP issues a fresh Assertion at 09:50. `AuthnInstant=09:00` and `Assertion@IssueInstant=09:50` can be completely normal. Do not reject solely because `AuthnInstant` predates `NotBefore` if assurance/max-authentication-age policy allows it.

If the business requires **recent re-authentication**, use SAML `AuthnRequest`/`ForceAuthn` or a dedicated authn-freshness policy, validating `AuthnInstant`/`AuthnContext`. **Never widen/skew `Conditions`** to substitute for a fresh-authentication policy.

## 4. Time Rules per SAML Core

### 4.1. Zero Clock Skew

Per SAML Core, `NotBefore` is the start instant and `NotOnOrAfter` is the end instant. When both are present, `NotBefore < NotOnOrAfter` must hold.

Given trusted instant `now` from the **SP clock**:

```text
Assertion Conditions are valid when:

    now >= NotBefore
AND now <  NotOnOrAfter

Invalid if:
    now <  NotBefore      => not yet valid
OR  now >= NotOnOrAfter   => expired
```

**The exact instant `NotBefore` is valid; the exact instant `NotOnOrAfter` is invalid.** This is a mandatory boundary test case.

### 4.2. Adding Allowed Clock Skew

Suppose policy configures `S = 60 seconds`. A common expression of bidirectional tolerance logic:

```text
Start condition:
    now + S >= NotBefore

End condition:
    now - S < NotOnOrAfter

Equivalent:
    now >= NotBefore - S
AND now <  NotOnOrAfter + S
```

Under these formulas, **the start and end limits retain distinct boundaries**. At `now = NotOnOrAfter + S`, it must **reject** because `NotOnOrAfter` is exclusive.

This is a common **testing model** for understanding bidirectional extension. How a given OpenSAML version applies skew to each `Condition`, `SubjectConfirmationData`, `IssueInstant`, or `AuthnStatement` depends on the specific validator/profile; **do not assume a single variable `S` applies identically to every timestamp**. In real tests, verify against your exact Spring/OpenSAML version and active configuration.

### 4.3. Example Policy

```text
SP now:             2026-11-07T10:00:00Z
Allowed skew S:      PT60S
Conditions:
  NotBefore:         2026-11-07T09:55:00Z
  NotOnOrAfter:      2026-11-07T10:05:00Z
SubjectConfirmationData:
  NotOnOrAfter:      2026-11-07T10:02:00Z
```

At `10:00`, both `Conditions` and bearer confirmation are valid. If SP time is 10:02:30 and bearer `NotOnOrAfter=10:02`, acceptance or rejection depends on validator policy `S=60s`; even if accepted within a 30s grace window, the assertion **does not become valid until 10:05+60s** for bearer presentation. Each limit must be checked **independently**.

### 4.4. S Is a Security Policy, Not a Cure for Broken NTP

A small tolerance may be needed for network latency, clock offset, scheduling, and JDK precision. However, raising `S` from 60 seconds to 30 minutes:

- Accepts **not-yet-valid** Assertions 30 minutes early.
- Allows expired Assertions to be used 30 minutes late.
- Widens the replay attack window if replay caches/correlation do not block them.
- Masks NTP problems or systems emitting wrong timestamps.
- May violate the RP–IdP profile/security policy.

Every value of `S` should be threat-modeled and measured; **60s here is an illustrative value**, not a Spring Security default or universal SAML requirement. Spring Security docs use a 10-minute example to illustrate the API; **an API example is not an operational recommendation of 10 minutes for every system**.

## 5. Missing or Invalid Conditions: Separating Core Semantics from Profile Policy

### 5.1. Conditions Attributes Can Be Absent

SAML Core permits `NotBefore` or `NotOnOrAfter` to be omitted. When one bound is missing, that bound is **unspecified by Core**, not an automatic XML parse error. If both are omitted, `Conditions` imposes no temporal bounds itself, though other SAML conditions may still apply.

**In real Web SSO**, the SP may enforce a stricter profile/policy requiring expiry, a maximum lifetime cap, assertion age limits, bearer `NotOnOrAfter`, and replay prevention. Never claim "Core always requires both," and never accidentally accept an Assertion with no expiry merely because "SAML Core allows it."

### 5.2. Mandatory Interval Check When Both Bounds Exist

```text
NotBefore    = 2026-11-07T10:05:00Z
NotOnOrAfter = 2026-11-07T10:03:00Z
```

This is an inverted interval and must be rejected; never let skew make an invalid interval "appear valid." If both timestamps are equal, the interval is empty and also invalid.

### 5.3. Negative Test for Missing Expiry

If the test IdP intentionally issues `Conditions` without `NotOnOrAfter`:

- Determine whether **SP policy** requires it.
- Ensure bearer `SubjectConfirmationData@NotOnOrAfter` is still checked per the Web SSO profile.
- If business/SP policy requires bounded lifetimes, reject missing `Conditions` expiry or enforce max age from `IssueInstant` per approved rules.
- Do not invent an expected result of "always reject per SAML Core" when only an optional attribute is missing.

### 5.4. Invalid Timestamp Strings

SAML's XML schema relies on `xs:dateTime`. Cases:

```text
2026-11-07T10:00:00Z       Normal ISO UTC
2026-11-07T10:00:00.123Z   Sub-second precision
2026-11-07T17:00:00+07:00  Same instant as 10:00Z
not-a-time                 Invalid format
2026-13-99T25:61:00Z       Invalid date/time
```

Parse per exact **XML Schema `dateTime`/`Instant`**, never using `LocalDateTime` and assuming the system time zone. Never strip milliseconds and introduce boundary errors. If a profile requires UTC `Z`, IdP and SP must agree; offset formats must parse with exact instant semantics when permitted.

## 6. Exact Boundaries That Need Testing

Assume `now = 10:00:00.000Z` and `S = 60s`; the cases below examine **`Conditions` first**, assuming all other checks pass.

| # | `NotBefore` | `NotOnOrAfter` | Expected per tolerance formula |
| --- | --- | --- | --- |
| 1 | 09:55:00 | 10:05:00 | ACCEPT |
| 2 | 10:00:00 | 10:05:00 | ACCEPT — equal to `NotBefore` |
| 3 | 10:01:00 | 10:05:00 | ACCEPT — exact lower skew boundary |
| 4 | 10:01:00.001 | 10:05:00 | REJECT — not yet valid > 60s |
| 5 | 10:00:59 | 10:05:00 | ACCEPT — future within skew |
| 6 | 09:55:00 | 10:00:00 | ACCEPT if policy allows 60s skew, though past logical end |
| 7 | 09:55:00 | 09:59:00 | **REJECT** — exact upper skew boundary |
| 8 | 09:55:00 | 09:59:00.001 | ACCEPT — 1ms left in extended window |
| 9 | 09:55:00 | 09:58:59 | REJECT — expired > 60s |
| 10 | 10:01:01 | 10:05:00 | REJECT — not-yet-valid > 60s |
| 11 | 10:03:00 | 10:02:00 | REJECT — invalid interval |
| 12 | 10:00:00 | 10:00:00 | REJECT — zero-length interval |

All examples assume a **fixed trusted clock** and exact skew policy. Integration tests must confirm the real Spring/OpenSAML validator behaves as expected; if an implementation differs at millisecond edges, verify the version and lock down tolerance behavior with tests instead of guessing.

### 6.1. Why Does Testing Exact 1ms Boundaries Matter?

If a developer writes `now <= NotOnOrAfter` instead of `now < NotOnOrAfter`, the exact-equality case is wrongly accepted. If timestamps are truncated to epoch seconds via rounding, `09:59:00.001` may collapse to `09:59:00` and introduce boundary bugs. Tests should use `Instant` with nanosecond precision and `Duration`, never truncating to minutes.

### 6.2. Why Not Use Sleep to Test Expiry?

`Thread.sleep(60_000)` makes tests slow and flaky due to schedulers, CI load, clock adjustments, and networking. For pure logic unit tests, use `Clock.fixed(Instant, ZoneOffset.UTC)` and shift `Instant`, or dependency-inject a `Clock`. For OpenSAML integration tests, build **signed fixtures with timestamps relative to the test clock**; if the framework does not expose easy `Clock` injection, place timestamps well outside boundaries to test rejection and reserve exact boundary checks for unit/controlled-time tests.

## 7. Bearer SubjectConfirmationData Has Its Own Expiration

### 7.1. Why Must Bearer Be Checked?

In the SAML Web Browser SSO bearer profile, an Assertion cannot authenticate a user solely because `Conditions` is valid. `SubjectConfirmationData` also enforces:

- `Method="urn:oasis:names:tc:SAML:2.0:cm:bearer"`.
- `Recipient` matching the SP's ACS URL.
- `NotOnOrAfter` still valid for bearer confirmation, with allowable skew if configured.
- `InResponseTo` matching the issued `AuthnRequest` ID in SP-initiated flows.
- Some profiles allow `Address` depending on policy and network/proxy constraints.

The OASIS SAML2 Web SSO profile mandates `Recipient` and `NotOnOrAfter` on bearer `SubjectConfirmationData`; `NotBefore` in bearer confirmation is **not used** in the base profile, though other profiles have their own rules. Never confuse `Conditions@NotBefore` with bearer `SubjectConfirmationData@NotBefore`.

### 7.2. Testing Valid Conditions with Expired Bearer

```text
now                             = 10:00:00Z
skew                            = 60s
Conditions.NotBefore            = 09:50:00Z
Conditions.NotOnOrAfter         = 10:10:00Z
SubjectConfirmation.NotOnOrAfter = 09:58:59Z
```

`Conditions` is still valid, yet bearer expired more than 60s ago ⇒ **REJECT**. This test is mandatory to catch code that inspects only `Conditions@NotOnOrAfter`.

### 7.3. Testing Bearer Recently Expired Within Skew

```text
now                              = 10:00:00Z
skew                             = 60s
Conditions.NotOnOrAfter          = 10:10:00Z
SubjectConfirmation.NotOnOrAfter = 09:59:30Z
```

Under the ±60s tolerance model in section 4, this bearer timestamp falls within grace ⇒ **temporally ACCEPTABLE**, provided validator policy permits it and all other checks pass. If security policy prohibits grace on bearer confirmation, configure the validator/check accordingly and test that decision.

### 7.4. One Assertion with Multiple SubjectConfirmations

SAML profiles can allow multiple confirmation alternatives. Never take a naive `min`/`max` across timestamps while ignoring `Method`/`Recipient`/`InResponseTo`. A validator may succeed when **at least one bearer confirmation is valid per profile**, yet every field of that chosen element must hold. An expired confirmation cannot be "rescued" by another confirmation meant for a different ACS or Request.

## 8. IssueInstant and AuthnInstant Are Not Conditions

### 8.1. Response/Assertion IssueInstant

`IssueInstant` reflects when an object was issued. It helps bound message age and detect far-future timestamps when policy enforces it. However:

- It does not replace `Conditions@NotBefore`/`NotOnOrAfter` or `SubjectConfirmationData@NotOnOrAfter`.
- A freshly issued Response may contain an Assertion with a different lifetime.
- Freshness policies may cap max assertion age, max response age, and future issue allowance.
- Distinguish `Response@IssueInstant` from `Assertion@IssueInstant`; do not inspect only one.
- With multiple assertions, validate each assertion per profile; never take only the first `IssueInstant` in the document.

### 8.2. AuthnInstant and ForceAuthn

`AuthnInstant` records when **the user authenticated at the IdP**, which can be hours before the `SAMLResponse` was issued if the user already had SSO. An SP requiring "authenticated within the last 15 minutes" needs a `maxAuthenticationAge` policy or `AuthnRequest` `ForceAuthn` if supported by the IdP; never treat `Assertion@NotOnOrAfter` as proof of a recent login.

### 8.3. SessionNotOnOrAfter

`AuthnStatement@SessionNotOnOrAfter` describes the **IdP login session** and long-lived context policy. It does not replace the expiry of a bearer assertion presented at the ACS. Per SAML Web SSO profile/errata, the SP should discard its security context once `SessionNotOnOrAfter` passes unless identity is re-established per profile; how the local session framework enforces this must be tested.

### 8.4. Skew Differs by Field

An application may apply skew to Assertion `Conditions`, a separate policy to `Response@IssueInstant`, `maxAuthAge` to `AuthnInstant`, and another policy to sessions. **Never raise a single `"clockSkew=1h"` setting to solve every time failure.** Analyze which validator actually rejected and why, then fix the clock or policy on the exact field.

## 9. Signature, Replay, and Time Are Three Separate Defense Layers

### 9.1. An Expired Assertion Still Has a Valid Signature

The IdP's XML signature does not "expire" automatically when the clock passes `NotOnOrAfter`. An Assertion from last week can remain **cryptographically valid** under the IdP key while **temporally invalid**. Signature unit tests will pass; login must still reject.

### 9.2. Replay Can Occur Inside the Validity Window

Suppose an Assertion is valid from 10:00 to 10:05. Someone holding the `SAMLResponse` may try re-POSTing it at 10:01. Every timestamp check passes; if the SP lacks `InResponseTo` tracking, unique assertion/response ID replay detection, or token-use policy, reuse becomes possible.

**Clock skew does not prevent replay.** You need:
- `InResponseTo` validation against the SP's stored `AuthnRequest` and matching session when applicable.
- A replay cache for assertion/response IDs or equivalent replay protection per framework/profile.
- No new `Authentication` created on duplicate POSTs, even before expiration.
- Replay entries stored with a TTL covering at least the valid risk window **including skew**, tuned per profile.
- Never accept an untrusted XML certificate or wrong audience just to "see if the test passes."

### 9.3. Is a Session Remaining Alive After Assertion Expiry a Bug?

Not necessarily. Assertion `NotOnOrAfter` typically limits **when the assertion may be used to authenticate**, rather than requiring every local app session created from it to terminate at the exact `Conditions` boundary. Local session lifetime, `SessionNotOnOrAfter`, logout, re-authentication, and authorization follow separate policies.

In tests:

- An expired Assertion **never previously accepted** must not create a new `SecurityContext`.
- Once a valid Assertion created a local session, whether the user stays logged in after the assertion's validity window closes depends on session policy; do not mislabel that as "expired assertion accepted" if the app is simply honoring its session cookie.

## 10. Real-World Clock Skew: Slow or Fast?

### 10.1. SP Behind IdP

```text
Real/IdP time  = 10:00:00
SP time        = 09:58:30
IdP NotBefore  = 10:00:00
Skew SP        = 60s
```

The SP is **90s behind**, exceeding the 60s allowed skew ⇒ Assertion is evaluated as **`NOT_YET_VALID`**. The proper fix is NTP/chrony/VM clock synchronization and checking trusted time sources—not raising skew to 10 minutes just to let everyone log in temporarily.

### 10.2. SP Ahead of IdP

```text
IdP time                  = 10:00:00
SP time                   = 10:02:00
Bearer NotOnOrAfter        = 10:01:00
Skew SP                   = 60s
```

The SP is 120s ahead, while bearer expiry is only 60s ahead of IdP time; at SP `now=10:02` and `bearer end + skew = 10:02`, **it hits the upper boundary (exclusive) ⇒ reject**. Fix the clocks and test precision rather than changing the operator to `<=`.

### 10.3. Clock Source and the JVM

Java `Instant.now()` reads the system clock through the JVM; host/VM/container clocks must stay NTP-synchronized. Time zones affect only local time formatting, **never shifting UTC `Instant`**. OS DST transitions do not change SAML UTC instants; using `LocalDateTime` and comparing against XML UTC introduces false errors around DST changes.

If the SP runs across multiple pods, one pod skewed +90s while others are accurate produces "random" login failures. Measure offsets, monitor NTP sync health, and isolate drifted nodes. Never synchronize by reading timestamps from browser requests: that is an **untrusted source**.

## 11. Spring Security: Configuring Controlled Clock Skew

### 11.1. Current API of OpenSAML5 Provider

Per current Spring Security reference docs, one way to configure this is creating `OpenSaml5AuthenticationProvider` and setting `AssertionValidator.builder().clockSkew(Duration)`.

Example **Spring Boot/Security fragment**:

```java
import java.time.Duration;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.authentication.ProviderManager;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.saml2.provider.service.authentication
        .OpenSaml5AuthenticationProvider;
import org.springframework.security.saml2.provider.service.authentication
        .OpenSaml5AuthenticationProvider.AssertionValidator;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class SamlClockSkewConfiguration {

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http)
            throws Exception {

        OpenSaml5AuthenticationProvider provider =
                new OpenSaml5AuthenticationProvider();

        AssertionValidator validator = AssertionValidator.builder()
                .clockSkew(Duration.ofSeconds(60))
                .build();

        provider.setAssertionValidator(validator);

        return http
            .authorizeHttpRequests(auth -> auth
                .anyRequest().authenticated())
            .saml2Login(saml -> saml
                .authenticationManager(new ProviderManager(provider)))
            .build();
    }
}
```

**This is not a standalone runnable Java file.** It requires Spring Security SAML2 dependencies, a trusted `RelyingPartyRegistrationRepository`, a Spring app, an ACS, signing/verifying keys, and a test IdP. The example uses **60s illustratively**, without claiming it is Spring's default or a mandatory duration.

### 11.2. Never Replace the Default Validator with "Always Accept"

A custom validator such as:

```java
// ANTI-PATTERN — DO NOT USE IN PRODUCTION.
// provider.setAssertionValidator(assertionToken ->
//     Saml2ResponseValidatorResult.success());
```

strips out critical SAML protocol checks. When adding validation for `OneTimeUse` or stricter maximum age limits, **compose/extend the provider's defaults** using the official builder APIs for your release. Never "fix" 401s by removing `Conditions`/`SubjectConfirmation` validators.

### 11.3. 4.x, 5.x, Spring Security 6, and 7

- Some Spring Security 6.x setups use `OpenSaml4AuthenticationProvider` with different validator constructors/static factories; migration docs and release Javadocs are authoritative.
- Current docs describe `OpenSaml5AuthenticationProvider.AssertionValidator.builder()` and `clockSkew(Duration)`.
- Spring Security 7 alters certain authentication models and Response/Assertion validation ordering; do not rely on an exception message or static method name from another release.
- OpenSAML 4.x/5.x differ in validation parameters and `Duration` vs. numeric millis in some APIs; do not copy OpenSAML 3.x snippets with mismatched types.
- Setting assertion clock skew **does not automatically** update every validator for `Response@IssueInstant` or local session TTL. Run integration tests on your exact version.

### 11.4. Other Checks Must Still Run

Even when time is tolerated within skew, the SP must verify:

- Trusted IdP certificate/signature, never self-declared `ds:KeyInfo`.
- `Issuer` matching the trusted registration.
- `AudienceRestriction` containing the exact RP entityID.
- `Destination`/`Recipient` matching the expected ACS.
- `InResponseTo` valid against pending `AuthnRequest` if SP-initiated.
- Bearer `SubjectConfirmation` containing complete required data.
- Assertion/Response replay prevention.
- Hardened XML parser (XXE/DTD/oversize) and exact signed subtree consumption.
- Local authorization from trusted/approved claims.

**No `clockSkew` value can turn an invalid signature or wrong audience into valid.**

## 12. Designing Proper Test Fixtures to Isolate Time Failures

### 12.1. Fixture Creation Method

1. Stand up a **test IdP** or SAML message factory (e.g., OpenSAML) with the test realm's dedicated trusted signing key.
2. Configure the SP with `RelyingPartyRegistration` pointing to the test IdP's exact entityID, ACS, audience, and certificate.
3. Generate an `AuthnRequest` and persist its ID/state if testing SP-initiated flow.
4. Build XML with `IssueInstant`, `Conditions`, and bearer `SubjectConfirmationData` per test case.
5. **Sign after setting timestamps**: compute digest, canonicalization, and signature with the **exact test IdP private key**.
6. Encode `SAMLResponse` per binding (HTTP-POST typically Base64 XML) and send to the ACS.
7. Confirm the Response is valid in signature/issuer/audience before diagnosing time validators.
8. Observe `Authentication`, session, sanitized failure code, and protected route behavior.
9. Never bring production SAML assertions/certs/private keys into CI logs/fixtures.
10. Fixture XML should generate timestamps near `Instant.now()` per test run rather than hard-coding 2026 dates that expire in 2027 and break positive tests.

### 12.2. Pitfall When Simply Editing Signed Base64

```text
signedXml = load("valid-response.xml")
tampered = signedXml.replace("10:05:00Z", "09:00:00Z")
POST Base64(tampered)
assertLoginFailed()
```

Rejection here may come from an **invalid signature** because the XML changed after signing. That test **does not prove** `Conditions@NotOnOrAfter` is checked. To test expiration, **re-issue a cryptographically valid signed response** with the altered timestamp, or unit-test the temporal validator with explicitly mocked trust.

### 12.3. Positive Control + Negative Control

Each test group needs:

- **Positive control:** fully configured signed Response with valid timestamps ⇒ login succeeds.
- **Negative case:** alter only the target timestamp and **validly re-sign** ⇒ login rejected by time validator.
- **Independent invalid signature test:** mutate XML post-signing or sign with an untrusted key ⇒ rejected for trust/signature; do not count as time validation coverage.
- **Wrong audience/recipient control:** validly signed with wrong recipient ⇒ rejected per protocol, never "saved" by skew.

### 12.4. No Data Leakage in Fixtures

Fixtures should use `opaque-user-test`, test issuer URLs, test keypairs, and synthetic timestamps. Never store full production `SAMLResponse` payloads containing `NameID`/claims/tokens in Git, issue trackers, or CI artifacts. For debugging, record only allowlisted reason codes and request correlation IDs.

## 13. Runnable Java 17: Testing Conditions and Bearer Expiry

The following example **uses neither Spring nor OpenSAML**. It models two time checks:

1. `Conditions@NotBefore / @NotOnOrAfter`.
2. `SubjectConfirmationData@NotOnOrAfter` of a bearer confirmation.

It uses `Clock.fixed` for exact boundary tests, `Duration.ofSeconds(60)` as an illustrative tolerance, and `Instant` instead of `LocalDateTime`. It also caps skew configuration in the demo at 60 seconds per **example policy**. The program does not parse/sign SAML XML, nor verify signatures, recipient, issuer, audience, `InResponseTo`, XML IDs/replay, `AuthnInstant`, or `SessionNotOnOrAfter`. Never use this function in place of a real provider.

Save `SamlTimeBoundaryDemo.java`:

```java
import java.time.Clock;
import java.time.Duration;
import java.time.Instant;
import java.time.ZoneOffset;
import java.util.Objects;

public class SamlTimeBoundaryDemo {

    record Window(
            Instant notBefore,
            Instant notOnOrAfter,
            Instant bearerNotOnOrAfter) {}

    enum Decision {
        ACCEPT,
        BAD_INTERVAL,
        NOT_YET_VALID,
        ASSERTION_EXPIRED,
        BEARER_EXPIRED
    }

    static Decision validate(
            Window window,
            Clock clock,
            Duration allowedSkew) {

        Objects.requireNonNull(window, "window");
        Objects.requireNonNull(clock, "clock");
        Objects.requireNonNull(allowedSkew, "allowedSkew");
        Objects.requireNonNull(window.notBefore(), "notBefore");
        Objects.requireNonNull(window.notOnOrAfter(), "notOnOrAfter");
        Objects.requireNonNull(
                window.bearerNotOnOrAfter(), "bearerNotOnOrAfter");

        // Demo policy, not a universal SAML/Spring default.
        if (allowedSkew.isNegative()
                || allowedSkew.compareTo(
                    Duration.ofSeconds(60)) > 0) {
            throw new IllegalArgumentException(
                    "Skew outside approved demo policy");
        }

        Instant now = clock.instant();

        // Interval must be nonempty independent of skew.
        if (!window.notBefore().isBefore(
                window.notOnOrAfter())) {
            return Decision.BAD_INTERVAL;
        }

        // NotBefore is inclusive; tolerate SP behind by S.
        if (now.plus(allowedSkew).isBefore(
                window.notBefore())) {
            return Decision.NOT_YET_VALID;
        }

        // NotOnOrAfter is exclusive even after skew.
        if (!now.isBefore(
                window.notOnOrAfter().plus(allowedSkew))) {
            return Decision.ASSERTION_EXPIRED;
        }

        // Bearer confirmation has its own expiry.
        if (!now.isBefore(
                window.bearerNotOnOrAfter()
                      .plus(allowedSkew))) {
            return Decision.BEARER_EXPIRED;
        }

        return Decision.ACCEPT;
    }

    static Window window(
            Instant now,
            long nbOffsetSeconds,
            long endOffsetSeconds,
            long bearerEndOffsetSeconds) {

        return new Window(
                now.plusSeconds(nbOffsetSeconds),
                now.plusSeconds(endOffsetSeconds),
                now.plusSeconds(bearerEndOffsetSeconds));
    }

    static void show(String label, Window w,
                     Clock clock, Duration skew) {
        System.out.println(
                label + ": " + validate(w, clock, skew));
    }

    public static void main(String[] args) {
        Instant now =
                Instant.parse("2026-11-07T10:00:00Z");
        Clock fixed =
                Clock.fixed(now, ZoneOffset.UTC);
        Duration sixtySeconds =
                Duration.ofSeconds(60);

        show("Valid", window(now, -120, 120, 90),
                fixed, sixtySeconds);
        show("Future 61s", window(now, 61, 300, 300),
                fixed, sixtySeconds);
        show("Future exactly 60s",
                window(now, 60, 300, 300),
                fixed, sixtySeconds);
        show("Future within 30s",
                window(now, 30, 300, 300),
                fixed, sixtySeconds);
        show("Expired 61s",
                window(now, -300, -61, 300),
                fixed, sixtySeconds);
        show("Expired exactly 60s",
                window(now, -300, -60, 300),
                fixed, sixtySeconds);
        show("Expired within 30s",
                window(now, -300, -30, 300),
                fixed, sixtySeconds);
        show("Bearer expired 61s",
                window(now, -120, 120, -61),
                fixed, sixtySeconds);
        show("Bearer within 30s",
                window(now, -120, 120, -30),
                fixed, sixtySeconds);
        show("Bad interval",
                window(now, 180, 60, 300),
                fixed, sixtySeconds);
        show("Zero skew expired",
                window(now, -300, -30, 300),
                fixed, Duration.ZERO);
    }
}
```

Compile and run:

```bash
javac SamlTimeBoundaryDemo.java
java SamlTimeBoundaryDemo
```

**Exact** stdout:

```text
Valid: ACCEPT
Future 61s: NOT_YET_VALID
Future exactly 60s: ACCEPT
Future within 30s: ACCEPT
Expired 61s: ASSERTION_EXPIRED
Expired exactly 60s: ASSERTION_EXPIRED
Expired within 30s: ACCEPT
Bearer expired 61s: BEARER_EXPIRED
Bearer within 30s: ACCEPT
Bad interval: BAD_INTERVAL
Zero skew expired: ASSERTION_EXPIRED
```

### 13.1. Explaining the Boundary Math

- `Future 61s`: `now+60s < NotBefore=now+61s` ⇒ reject.
- `Future exactly 60s`: `now+60s = NotBefore` ⇒ accept because the start bound is inclusive.
- `Expired exactly 60s`: `now = NotOnOrAfter+60s` ⇒ reject because the end bound is exclusive.
- `Expired within 30s`: `now < NotOnOrAfter+60s` ⇒ temporally accepted under the illustrative skew policy.
- `Bearer expired 61s`: `Conditions` still valid yet bearer past limit ⇒ reject.
- `Bad interval`: inverted bounds ⇒ reject, even if skew would otherwise let the two comparisons pass individually.
- `Zero skew expired`: no grace, end was 30s before `now` ⇒ reject.

### 13.2. Why Must the Demo Check Bearer Too?

A validator checking only `Conditions` could accept an Assertion at 10:00 even though bearer `NotOnOrAfter=09:58:59`. In the Web SSO bearer profile, that is a critical flaw. The demo shows the order: validate interval, `Conditions` lower/upper, then bearer upper. Integration tests outside the demo must also check `Recipient` and `InResponseTo` against the real request.

### 13.3. What the Demo Does Not Do

- Does not parse `SAMLResponse` XML or Base64-decode.
- Does not verify IdP signing certificate/XML Signature.
- Does not check `AudienceRestriction`, `Destination`, `Recipient`, `Issuer`, or `InResponseTo`.
- Does not defend against replay, duplicate assertion IDs, or XML Signature Wrapping.
- Does not handle multiple `SubjectConfirmation` alternatives or non-bearer profiles.
- Does not check `Response@IssueInstant`, `Assertion@IssueInstant`, `AuthnInstant`, or `SessionNotOnOrAfter`.
- Does not manage real NTP, system clocks, asymmetric one-way skew, or OpenSAML precision policies.
- Does not create a Spring Security `Authentication` or `HttpSession`.

The example is a **test oracle** teaching defined temporal logic, not a production implementation.

## 14. Test Cases by Control Layer

### 14.1. Conditions NotBefore

| Test | Input | Expected result |
| --- | --- | --- |
| NB-01 | `NotBefore` 5 minutes in the past | Pass if other checks valid |
| NB-02 | `NotBefore == now`, S=0 | Pass — inclusive |
| NB-03 | `NotBefore = now+1 ms`, S=0 | Reject |
| NB-04 | `NotBefore = now+S` | Pass per ±S model |
| NB-05 | `NotBefore = now+S+1 ms` | Reject |
| NB-06 | `NotBefore` is valid UTC timestamp, SP display time zone differs | Result follows `Instant`, not local wall-clock |
| NB-07 | `NotBefore` has `+07:00` offset for same UTC instant | Parses/compares properly if profile/parser allows offset |
| NB-08 | `NotBefore="not-a-time"` | Reject parsing/validation |
| NB-09 | `NotBefore` omitted while another profile requires an age limit | Behaves per contract; do not assume Core always mandates it |

### 14.2. Conditions NotOnOrAfter

| Test | Input | Expected result |
| --- | --- | --- |
| EXP-01 | `NotOnOrAfter > now` by several minutes | Temporal pass |
| EXP-02 | `NotOnOrAfter == now`, S=0 | Reject — exclusive |
| EXP-03 | `NotOnOrAfter = now-1ms`, S=0 | Reject |
| EXP-04 | `NotOnOrAfter = now-S` | Reject — upper skew boundary |
| EXP-05 | `NotOnOrAfter = now-S+1ms` | May pass per ±S model |
| EXP-06 | `NotOnOrAfter = now-S-1ms` | Reject |
| EXP-07 | `NotOnOrAfter < NotBefore` | Reject invalid interval |
| EXP-08 | `NotOnOrAfter == NotBefore` | Reject zero-length interval |
| EXP-09 | `NotOnOrAfter` omitted when Web SSO policy mandates bounded lifetime | Reject per policy if configured |
| EXP-10 | End far in the future | Test max assertion TTL/age policy; never assume unlimited |
| EXP-11 | Expired yet signature valid | Reject for time; never create `Authentication` |

### 14.3. Bearer Confirmation

| Test | Input | Expected |
| --- | --- | --- |
| SC-01 | Bearer `NotOnOrAfter` valid, `Conditions` valid | Temporal pass |
| SC-02 | Bearer expired >S, `Conditions` still valid | Reject |
| SC-03 | Bearer = `now-S` | Reject at upper skew boundary |
| SC-04 | Bearer within permitted skew | Behavior per actual validator policy |
| SC-05 | Bearer expiry missing in Web Browser SSO | Reject per profile |
| SC-06 | Bearer `Recipient` wrong ACS | Reject even when timestamps valid |
| SC-07 | Bearer `InResponseTo` mismatches pending request | Reject |
| SC-08 | Multiple confirmations: one expired, one timely yet wrong `Recipient` | Must not auto-accept |
| SC-09 | `SubjectConfirmationData` `NotBefore` in Web SSO bearer | Reject per profile if disallowed |
| SC-10 | Bearer valid yet `Conditions` expired | Reject |

### 14.4. IssueInstant, AuthnInstant, SessionNotOnOrAfter

| Test | Purpose |
| --- | --- |
| ISSUE-01 | `Response@IssueInstant` too far in future; verify response freshness policy |
| ISSUE-02 | `Assertion@IssueInstant` too old despite long `Conditions`; enforce max assertion age if required |
| ISSUE-03 | `Response` `IssueInstant` and `Assertion` `IssueInstant` differ reasonably; do not confuse them |
| AUTH-01 | `AuthnInstant` old yet user's IdP SSO session valid; do not falsely reject if `maxAuthAge` is not required |
| AUTH-02 | `AuthnInstant` too old for high-assurance step-up policy; require re-auth |
| AUTH-03 | `AuthnInstant` in future > allowed skew; reject per policy |
| SESS-01 | `SessionNotOnOrAfter` elapsed; local security context handled per SP/profile policy |
| SESS-02 | `SessionNotOnOrAfter` far ahead yet bearer expired; reject new login |
| PREC-01 | Fractional seconds/UTC offsets parse without losing precision |

## 15. Re-Testing Signed SAMLResponses: Implementation Notes

### 15.1. Intact Signed Assertion That Has Expired

A fixture **signed before expiration** and stored in tests can still verify its signature. When sent to the ACS after its end bound, the SP must reject it. This is a good production-path integration test, though testing exact ±1 ms edges requires controlling the JVM/CI clock; avoid tests made brittle by latency.

### 15.2. To Test Future NotBefore, Re-Signing Is Required

To build a valid future assertion:

1. Generate XML with `NotBefore=now+S+epsilon`.
2. Set a valid future `NotOnOrAfter` and non-conflicting bearer expiry.
3. Set `Response`/`Assertion@IssueInstant` and `InResponseTo` validly per test profile.
4. Sign with the **test IdP private key**, never an attacker key or production credential.
5. Base64-encode per SAML HTTP-POST.
6. POST to the ACS; assert no authenticated session, with reason code `NOT_YET_VALID` in internal telemetry if exposed.

### 15.3. Testing Clock Skew When Clocks Differ

Test logic with `Clock.fixed` offsets, and integration test with:

- Fixtures carrying timestamps relative to the SP clock.
- A test IdP with a controllable issuance clock (test-only).
- A test SP JVM/container with a virtual clock or dependency-injected trusted `Clock` where supported by the framework.
- Controlled NTP mismatch tests in staging; never alter production host clocks to "try it out."

**Never let CI tests mutate the system clock** on shared runners or production hosts. Virtual-time test environments and recorded fixtures must stay isolated.

### 15.4. Signing Order in XMLDSig

When both Assertion and Response are signed, editing child nodes like `Conditions` can invalidate either the Assertion-level or Response-level digest/signature. Never "re-sign one level" if an outer signature references the modified subtree. Use trusted OpenSAML test factories that preserve proper signature coverage and re-sign all affected layers; verify with a positive control before running negative tests.

## 16. Spring Security Integration Tests: Asserting Final Outcome, Not Just HTTP Status

### 16.1. Test Infrastructure Model

```text
JUnit test / Test IdP / trusted test signing key
        |
        +-- Generate valid signed SAML Response
        +-- Case-specific timestamps
        +-- Valid expected ACS, Audience, Issuer, InResponseTo
        |
        v
Spring Boot Test + MockMvc or embedded test server
        |
        +-- SAML ACS /login/saml2/sso/corporate
        +-- RelyingPartyRegistration configured for Test IdP
        +-- OpenSAML temporal validators
        +-- AuthenticationSuccessHandler / FailureHandler
        |
        v
ASSERT:
  no authenticated principal on expired/not-yet-valid
  no local authenticated session is created
  protected endpoint still requires login
  safe error code, no raw SAML assertion in logs
```

### 16.2. Test Lifecycle Pseudocode

```java
// Illustrates workflow for a test harness with an IdP signing helper.
// Not a standalone JUnit class; helper is supplied by app test suite.
Instant clockAt = trustedTestClock.instant();

byte[] validSigned = testIdp.signSamlResponse(
    responseWithConditions(
        clockAt.minusSeconds(30),
        clockAt.plusSeconds(120)
    )
);

byte[] expiredSigned = testIdp.signSamlResponse(
    responseWithConditions(
        clockAt.minusSeconds(600),
        clockAt.minusSeconds(121)
    )
);

assertSamlLoginAccepted(validSigned);
assertSamlLoginRejected(expiredSigned);
assertNoSecurityContextForRejectedResponse();
```

**Core point:** the test helper must keep all other metadata/protocol checks valid to isolate time. `expiredSigned` is a newly signed response re-signed with the test key—never use string replacement on a signed fixture.

### 16.3. Do Not Hard-Code Expecting 401/302

Spring Security may redirect to a login page (3xx), return 401/403, or invoke a custom failure handler. An HTTP 302 after the ACS does not prove rejection if it redirects to a dashboard; an HTTP 200 can also be a generic error page. Tests should assert **`Authentication` outcome**, `SecurityContextHolder`/session state, and a protected resource using the same cookie, plus internal allowlisted reason codes. Never rely on HTTP status alone.

### 16.4. Avoiding False Positives from Unrelated Errors

If the fixture has a bad `InResponseTo`, wrong signing cert, wrong Audience, or missing bearer Recipient, login may fail before temporal validators run. When targeting `EXPIRED_ASSERTION` or `NOT_YET_VALID`, verify via sanitized traces/validator unit tests and a **positive control** proving the exact same fixture passes all checks except time.

### 16.5. Replay Cache in Tests

A repeated assertion ID may be rejected for replay before timestamps are even checked. Every test should use fresh Assertion/Response IDs and `AuthnRequest` IDs, or properly reset the **test-only replay store**. Also maintain a dedicated test confirming duplicate valid signed Assertions are rejected. Never disable replay protection in full-stack tests for convenience.

## 17. Multi-Pod, NTP, Network Latency, and Production Behavior

### 17.1. When One Pod Drifts

```text
IdP:        10:00:00
SP pod A:   10:00:02   PASS
SP pod B:   09:58:20   NOT_YET_VALID
SP pod C:   10:02:15   possibly EXPIRED bearer
```

Pods sharing identical signing certs, `RelyingPartyRegistration`, and code can still diverge because of system clocks. Partial login failures behind a load balancer are a **clue pointing to clock drift**. Check time synchronization and VM/container host clocks across **all nodes**, not just the primary server.

### 17.2. Network Latency vs. Clock Skew

Delay between IdP issuance and SP receipt is not purely clock offset. A Response delayed by network queues, large POSTs, or slow redirects can arrive after bearer expiry even with synchronized clocks. Solutions include reducing latency or having the IdP issue an appropriate bearer lifetime per profile—never opening skew unboundedly. Monitor latency separately from clock drift.

### 17.3. Time Zones and DST

SAML `dateTime` values normally use UTC `Z`. `2026-11-07T10:00:00Z` and `2026-11-07T17:00:00+07:00` represent the exact same `Instant`. Direct string comparison reports them different, yet temporally they are equal. Never parse into `LocalDateTime.now()` of `Asia/Ho_Chi_Minh` or a container time zone and compare against UTC without conversion.

### 17.4. Forward/Backward Clock Jumps

Large NTP steps, VM suspend/resume, or leap/clock corrections can shift system clocks. Tests can straddle boundary intervals when a logger reads one instant and the validator reads another. When debugging, log **UTC event timestamps** and measured offsets rather than substituting log time for validator time. Synchronized clocks and monotonic elapsed metrics help, though SAML wall-clock validity still relies on trusted actual time.

### 17.5. Multi-Region and Disaster Recovery

During failover to another region, nodes must share synchronized time, skew configs/IdP registrations, and replay caches. If the replay store is local-only, an unexpired Assertion could be replayed to region B after region A already accepted it. Accurate clocks do not replace distributed replay protection. Test failover using the same response ID and time windows.

## 18. Troubleshooting: Which Error, Which Fix?

| Symptom | Likely cause | Action |
| --- | --- | --- |
| `NotBefore` a few seconds in future | Clock drift / IdP issuance offset | Measure NTP offset, configure small bounded skew |
| `NotBefore` 2 minutes in future, S=60s | SP slow or IdP clock fast beyond policy | Sync clocks; do not widen arbitrarily |
| `NotOnOrAfter` elapsed | Response delay, reused response, SP fast | Check IdP issuance/latency and cache |
| `Conditions` valid yet bearer expired | `SubjectConfirmationData@NotOnOrAfter` is earlier | Check bearer limits independently |
| Repeated 401/redirects on pod B | Pod B clock drifted or skew config differs | Per-pod timestamp/NTP/status check |
| Only millisecond boundaries fail | Precision rounding or wrong inclusive comparison | Test `Instant`/millis, inspect implementation |
| Valid XML test also fails | Wrong signature/issuer/ACS/`InResponseTo` | Fix fixture before blaming time |
| Expired XML test passes unexpectedly | Skew too large, validator overridden, or no expiry policy | Verify actual assertion validator config |
| Missing `Conditions` expiry accepted | Core permits omission, SP policy lacks bound | Add required lifetime/max-age policy if needed |
| `AuthnInstant` old yet Response fresh | User had long-lived SSO session at IdP | Apply `maxAuthAge`/`ForceAuthn` per use case |
| `SessionNotOnOrAfter` past | Separate SSO session expiry | Review local session policy/SLO |
| SAML parse fails on offset/time zone | Parser/format/schema issue | Use XML-schema-compliant parser |
| Replayed valid Assertion accepted | Missing correlation/replay cache | Enable replay protection and tests |
| 302 after ACS yet user authenticated | Failure test asserted HTTP status only | Assert `SecurityContext`/session/protected route |
| Login fails after upgrade | OpenSAML/Spring defaults/APIs changed | Review release notes/validation chain |
| Logs print raw Assertion | Debug statement / APM capture | Sanitize and secure logs immediately |

### 18.1. Do Not Log XML Containing User Data for Debugging

A SAML Assertion can contain `NameID`, email, roles, session index, and sensitive identity data. Never dump raw `SAMLResponse` or decoded XML into application/proxy/APM logs. Log:

```json
{
  "event": "saml_authentication_rejected",
  "registration": "corporate",
  "reason_code": "ASSERTION_EXPIRED",
  "clock_skew_policy_seconds": 60,
  "verification_stage": "assertion_conditions",
  "correlation_id": "opaque-internal-event",
  "result": "rejected"
}
```

This JSON is an **illustrative audit event**. Never log raw tokens, XML, `NameID`, assertion IDs, session cookies, cert private keys, or unbounded user-controlled values as metric labels. For clock monitoring, use per-node clock offset/health and aggregate counts rather than raw identities.

## 19. Consolidated Security Test Matrix

| Case | Signature status | Conditions | Bearer | Expected |
| --- | --- | --- | --- | --- |
| T01 Baseline | Trusted valid | Within window | Within window | ACCEPT |
| T02 Expired 2 min, S=1 min | Trusted valid | Expired | Within window | REJECT |
| T03 `NotBefore` +61s, S=60s | Trusted valid | Not yet valid | Within window | REJECT |
| T04 `NotBefore` +60s, S=60s | Trusted valid | Lower skew edge | Within window | Temporal pass |
| T05 End = `now-60s`, S=60s | Trusted valid | Upper skew edge | Within window | REJECT |
| T06 End = `now-59.999s` | Trusted valid | Inside upper grace | Within window | Temporal pass |
| T07 `Conditions` valid, bearer expired | Trusted valid | Within window | Expired | REJECT |
| T08 `Conditions` expired, bearer valid | Trusted valid | Expired | Within window | REJECT |
| T09 Bad `NotBefore > NotOnOrAfter` | Trusted valid | Invalid interval | Within window | REJECT |
| T10 Missing bearer `NotOnOrAfter` | Trusted valid | Within window | Missing bound | REJECT per Web SSO |
| T11 Expired + wrong audience | Trusted valid | Expired | Within window | REJECT; do not count as time-only test |
| T12 Valid time + wrong signature | Untrusted | Within window | Within window | REJECT signature |
| T13 Valid time + wrong `Recipient` | Trusted valid | Within window | Wrong ACS | REJECT |
| T14 Valid time + wrong `InResponseTo` | Trusted valid | Within window | Wrong request | REJECT |
| T15 Duplicate valid Assertion | Trusted valid | Within window | Within window | REJECT replay |
| T16 Validly signed but IdP B issuer | Trusted key other tenant | Within window | Within window | REJECT issuer-key binding |
| T17 `Conditions` missing `NotOnOrAfter` | Trusted valid | Unbounded upper | Within window | Per strict defined SP policy |
| T18 Future `AuthnInstant` | Trusted valid | Within window | Within window | Per authn freshness/clock policy |
| T19 Old `AuthnInstant` | Trusted valid | Within window | Within window | Re-auth if `maxAuthAge` requires |
| T20 `SessionNotOnOrAfter` past | Trusted valid | Within window | Within window | Local session policy must handle |
| T21 UTF-8/fractional timestamps | Trusted valid | 1ms boundary | Within window | Parse/compare accurately |
| T22 Different system time zones | Trusted valid | Same UTC instant | Within window | Same decision |
| T23 Pod A UTC right / Pod B drift | Trusted valid | Near boundary | Within window | Metrics detect offset |
| T24 Unapproved 30-min skew | Trusted valid | Overly wide | Within window | Configuration QA FAIL |
| T25 Real expired assertion re-sent after logout | Trusted valid | Expired | Possibly expired | REJECT |
| T26 XML mutated post-signing to alter `NotOnOrAfter` | Invalid signature | Any | Any | REJECT signature; do not count as temporal test |
| T27 Both `Conditions` bounds missing | Trusted valid | Unbounded | Within window | Per profile/max-lifetime policy |
| T28 Signed SAML Assertion with malicious unsigned sibling | Partial trusted valid | Any | Any | REJECT/ignore unsigned node |
| T29 Wrong issuer yet timestamps pass | Valid math/other key | Within window | Within window | REJECT |
| T30 Expired Assertion creates no authenticated session | Trusted valid | Expired | Within window | Empty `SecurityContext`/new login denied |

### 19.1. Layered CI Testing

**Unit (fast, deterministic):** Comparison logic with `Clock.fixed`, ±1ns/±1ms/±skew edges. **Provider-level:** OpenSAML/Spring assertion validation with valid signatures and hardened parser. **E2E:** browser/ACS/request correlation, cookies, failure handler, session isolation. **Operations:** NTP drift, multi-pod, metrics, and replay cache distribution.

### 19.2. Test Priority When Time Is Limited

Prioritize at least the 8 highest-value tests:

1. Valid signed baseline accepts.
2. Expired `Conditions` rejects.
3. Future `NotBefore` rejects.
4. Expiry at exact `NotOnOrAfter` rejects with S=0.
5. Boundary at `NotOnOrAfter + S` rejects.
6. Valid `Conditions` with expired bearer rejects.
7. Invalid signature with valid time rejects.
8. Duplicate signed Assertion rejects even within the validity window.

Then expand to max lifetime, `AuthnInstant`, session policy, and multi-region tests.

## 20. Clock Skew Incident Runbook

### 20.1. When Users Report "SSO Only Fails on Fresh Logins"

1. Determine whether the request actually hits the ACS or another login redirect loop.
2. Use internal reason codes to distinguish `ASSERTION_NOT_YET_VALID`, `ASSERTION_EXPIRED`, `SUBJECT_CONFIRMATION_EXPIRED`, `INVALID_SIGNATURE`, `WRONG_ISSUER`, `REPLAY`.
3. Measure current UTC and NTP offsets on the **SP pod**, IdP nodes, and reverse proxy nodes if relevant to the flow.
4. Check the actual `clockSkew` config for the running release and registration; do not infer from sample code.
5. Inspect Assertion `Conditions` and bearer end **in a test environment or sanitized privileged diagnostics**, never dumping raw production assertions.
6. Check latency from IdP Response issuance to browser ACS callback.
7. Confirm state/correlation/ACS Destination and TLS forwarded headers are accurate.
8. If clocks drifted, fix NTP/time sync; never disable expiration checks.
9. Adjust skew only with policy approval, assess blast radius, and keep it as small as possible.
10. Re-test positive + negative + boundary cases and confirm errors stopped; track p95/percentile authentication delays.

### 20.2. When the IdP Issues Too Short a Time Window

An IdP might issue a 30-second bearer lifetime while the browser takes 40 seconds due to MFA/redirects/proxies. If clocks are accurate, the SP is right to reject. Coordinate with the IdP to set a balanced validity window per SAML Web SSO profile and risk policy, and optimize redirect/network latency. Never use a huge skew to override the IdP's lifetime without review.

### 20.3. When IdP Timestamps Use the Wrong Time Zone

If the IdP emits `2026-11-07T10:00:00Z` when it actually meant unconverted UTC+7 time, the timestamp is skewed by 7 hours. That is a **timestamp issuance bug**, not something to patch with a 7-hour `clockSkew`. Fix issuer serialization and NTP; test `Instant` equivalence between `Z` and `+07:00`.

### 20.4. When Signs of Replay/Malicious Reuse Appear

If multiple POSTs repeat the same assertion ID/timestamp within the window, never widen time limits to let the user log in. Inspect the replay store, `InResponseTo`, anomalous IPs/paths, and trigger incident response. Even with valid timestamps, a reused signed assertion must never create a new session. Never log raw `SAMLResponse` payloads in incident tickets.

## 21. Production Checklist

- [ ] IdP/SP clocks are NTP-synchronized, with offset measured per node/region.
- [ ] SAML timestamp comparisons use UTC `Instant` with proper precision.
- [ ] `Conditions@NotBefore` inclusive and `NotOnOrAfter` exclusive are tested at boundaries.
- [ ] Invalid and zero-length validity intervals are rejected.
- [ ] Bearer `SubjectConfirmationData@NotOnOrAfter` is checked **independently**.
- [ ] Bearer `Recipient`/`InResponseTo` are validated per the Web SSO profile.
- [ ] Allowed skew `S` has an owner, is small, versioned, and tested at ±S.
- [ ] The 10-minute sample in docs is not blindly treated as a production default.
- [ ] Default validators are not bypassed and expiry is never globally ignored to reduce 401s.
- [ ] Trusted signature, issuer, audience, destination, and replay checks still execute.
- [ ] Negative SAML fixtures are **re-signed after editing timestamps**.
- [ ] Positive controls and negative time controls use the same signing key/profile.
- [ ] Expired Assertion tests create no authenticated `SecurityContext`/session.
- [ ] Replay cache, `InResponseTo` store, and session isolation are E2E-tested.
- [ ] `AuthnInstant`/`SessionNotOnOrAfter` are distinguished from `Conditions` lifetimes.
- [ ] Missing `Conditions` attributes are tested per SP security policy.
- [ ] Java 17 unit tests are deterministic via `Clock.fixed`, with no `sleep` or manual clock hacks.
- [ ] Time zone offsets, 1ms precision, and invalid date parser errors are tested.
- [ ] CI/staging tests cover NTP drift, multiple pods, and failover.
- [ ] Monitoring uses allowlisted reason codes without raw SAML XML/PII.
- [ ] Exact Spring Security/OpenSAML versions are pinned and regression-tested.
- [ ] Max assertion age, session TTL, and re-authentication freshness have dedicated policies.
- [ ] Incident runbooks prioritize fixing clocks/IdP issuance over unbounded skew increases.

## 22. Review Questions

**1. Is `NotBefore` equal to the current instant valid?**  
Yes, the start bound is **inclusive**.

**2. Is `NotOnOrAfter` equal to the current instant valid (S=0)?**  
No, the end bound is **exclusive**.

**3. When S=60s, what happens if `NotOnOrAfter=now-60s`?**  
Under the illustrative bidirectional grace rule, **reject**, because `now=NotOnOrAfter+S` is the exclusive upper boundary.

**4. Is `NotBefore=now+60s` accepted when S=60s?**  
It may pass temporally under `now+S >= NotBefore`, though all other checks remain mandatory.

**5. If `Conditions` is still valid while bearer `SubjectConfirmationData` has expired, can login succeed?**  
No. Bearer confirmation is an independent condition.

**6. Why doesn't an old `AuthnInstant` automatically prove the Assertion expired?**  
It records when the user authenticated at the IdP; while IdP SSO remains active, a fresh Assertion can be issued later. `MaxAuthAge` is a separate policy.

**7. Can a valid signature be treated as meaning the timestamps are valid?**  
No. An XML signature can remain mathematically valid even after the Assertion expires.

**8. Does SAML Core mandate both `NotBefore` and `NotOnOrAfter` inside `Conditions`?**  
No. Either bound may be absent; SAML Web SSO and SPs may enforce stricter profile/lifetime policies.

**9. How do you prove a test failed due to expiry rather than an invalid signature?**  
Build the fixture with the expired timestamp **before signing**, re-sign with the trusted test IdP key, and prove the positive control passes.

**10. What are the downsides of using `Thread.sleep` in tests?**  
Flaky and slow due to CI clocks and scheduling; use `Clock.fixed` in unit tests.

**11. What happens if the SP clock is +2 minutes ahead while the IdP is accurate?**  
It may prematurely reject assertions near their end bound; fix NTP/time sync rather than widening skew excessively.

**12. If a SAML Response has a fresh `IssueInstant`, can an Assertion with expired `Conditions` still pass?**  
No. `IssueInstant` does not override `Conditions` expiry.

**13. Is an Assertion replayed within its validity window rejected?**  
It must be rejected per replay/correlation policy; valid timestamps never permit arbitrary reuse.

**14. After a user logs in validly, does the app session automatically end when `Conditions` expires?**  
Not automatically solely because the Assertion expired; local sessions and `SessionNotOnOrAfter` have separate lifecycles/policies.

**15. Which API configures skew in current Spring Security?**  
`OpenSaml5AuthenticationProvider.AssertionValidator.builder().clockSkew(Duration)`, followed by `setAssertionValidator`; verify per version.

**16. Should the default validator be replaced with an always-success function to fix expired logins?**  
No. That is a security flaw that can drop issuer/audience/subject checks.

**17. What if two pods make different decisions for the same Assertion?**  
Check clock offsets, skew configs, signing trust state, and replay routing on each pod/region.

**18. Is a fixture file whose `NotOnOrAfter` was edited after signing enough to prove expiry validation?**  
No. Failure may come solely from a broken signature; re-sign and isolate.

**19. Should `SubjectConfirmationData@NotBefore` be used to test Web SSO bearer `NotBefore`?**  
Do not confuse it with `Conditions@NotBefore`. The base Web Browser SSO bearer profile disallows `NotBefore` in bearer confirmation; test schema/profiles separately.

**20. Is widening skew to 1 day to avoid clock drift safe?**  
No. It widens acceptance for expired and future assertions; fix NTP/IdP issuance and use bounded tolerance.

## 23. References and Standards

- [OASIS SAML 2.0 Core — Assertions and Protocols](https://docs.oasis-open.org/security/saml/v2.0/saml-core-2.0-os.pdf): `Conditions`, `NotBefore`/`NotOnOrAfter` semantics, subject confirmation, `AuthnStatement`, and timestamp data types.
- [OASIS SAML 2.0 Profiles — Web Browser SSO](https://docs.oasis-open.org/security/saml/v2.0/saml-profiles-2.0-os.pdf): bearer `SubjectConfirmationData`, `Recipient`, `NotOnOrAfter`, request correlation, and session guidance.
- [OASIS SAML 2.0 Approved Errata](https://docs.oasis-open.org/security/saml/v2.0/sstc-saml-approved-errata-2.0-cd-02.html): Web SSO bearer expiry, `Recipient`, `InResponseTo`, and `SessionNotOnOrAfter`.
- [Spring Security — Authenticating SAML2 Responses](https://docs.spring.io/spring-security/reference/servlet/saml2/login/authentication.html): `OpenSaml5AuthenticationProvider`, `AssertionValidator` `clockSkew(Duration)`, customizing defaults, and SAML2 validation.
- [Spring Security — SAML2 Login Overview](https://docs.spring.io/spring-security/reference/servlet/saml2/login/overview.html): ACS filter, signature/time/subject/audience verification pipeline.
- [Spring Security — SAML2 Migration Notes](https://docs.spring.io/spring-security/reference/6.5/migration-7/saml2.html): `OpenSaml5AuthenticationProvider`/`AssertionValidator` API and version evolution.
- [OpenSAML 5.2.2 — SAML2AssertionValidationParameters](https://shibboleth.net/api/java-opensaml/5.2.2/org/opensaml/saml/saml2/assertion/SAML2AssertionValidationParameters.html): `CLOCK_SKEW` parameter and time-related validation context.
- [Java 17 — java.time.Clock](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/time/Clock.html): `Clock.fixed` and dependency-injected clock for deterministic tests.
- [Java 17 — java.time.Instant](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/time/Instant.html): UTC instant comparison and precision.
- [OWASP SAML Security Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/SAML_Security_Cheat_Sheet.html): signature validation, replay, protocol restrictions, and secure XML.
- [OWASP Logging Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Logging_Cheat_Sheet.html): redacting SAML Assertions, secrets, session IDs, and identity data.

**Remember:** `NotBefore` is **inclusive**, `NotOnOrAfter` is **exclusive**. With bounded skew `S`, test both **`now+S`** at the lower bound and **`NotOnOrAfter+S`** at the upper bound; the exact upper bound must still be rejected. `Conditions` and `SubjectConfirmationData` have **independent windows**, while `AuthnInstant`, `IssueInstant`, and `SessionNotOnOrAfter` address different questions. Every expiration integration test must use a **validly signed Response/Assertion** with timestamps set **before signing**, valid issuer/audience/recipient/`InResponseTo`, and replay protection. When clocks drift, prioritize fixing clocks/NTP and IdP issuance—**never disable temporal validators or widen skew without bounds**.