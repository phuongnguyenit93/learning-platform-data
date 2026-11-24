# Checking NotBefore, NotOnOrAfter, and Allowed Clock Skew in SAML 2.0

In SAML 2.0 federation, a Service Provider (SP, or Relying Party) must not accept an Assertion solely because it carries a valid signature. The Assertion must also **be used at the right time**. The two attributes `NotBefore` and `NotOnOrAfter` define the **validity window**; a **clock skew** setting permits a small margin for clock differences between the Identity Provider (IdP) and SP. This tolerance is a bounded margin, **not a way to disable time checks**.

This lesson focuses on SAML2 verification in Java/Spring Security applications: understanding exact start/end boundary semantics, distinguishing `<Conditions>` timing from `<SubjectConfirmationData>` timing, checking units/UTC and clocks, configuring `OpenSaml5AuthenticationProvider.AssertionValidator`, writing boundary tests in Java 17, and troubleshooting IdP incidents.

**Foundational conclusion:** at the current time `now`, a valid window is generally understood as **`NotBefore <= now < NotOnOrAfter`**. With an allowed tolerance `skew`, both sides are widened in a controlled manner, yet all remaining checks must still run: signature, issuer, audience, recipient, request correlation, and anti-replay.

## 1. Why Must SAML Authentication Validate Time?

A SAML Assertion is a statement of identity, authentication event, and/or attributes issued by an IdP to a recipient. Even when signed with a trusted key, a message can still be unsafe if:

- The Assertion is **used before the time permitted by the IdP**.
- The Assertion has **expired** yet is replayed.
- The SP system clock is wrong, causing valid Assertions to be rejected or expired Assertions to be accepted.
- An attacker reuses a captured Response within the acceptance window.
- The validator checks only `<Conditions>` while skipping `<SubjectConfirmationData>` expiration.
- A custom validator reads the current time from a header/client instead of the trusted server clock.

Example: IdP B issues an Assertion valid only from `10:00Z` until before `10:05Z`. If the SP receives it at `10:07Z` without checking `NotOnOrAfter`, the signature may still be valid yet the authentication request **is no longer valid in time**.

**Authentication differs from authorization:** passing time and signature checks is a condition for accepting the principal; roles, tenant data, and resource permissions still must be enforced in the application.

## 2. Locations of NotBefore and NotOnOrAfter in SAML XML

Both attributes appear in several structures, yet at least two contexts must be distinguished:

| Structure | Purpose | How to read |
| --- | --- | --- |
| `Assertion/Conditions@NotBefore` | Earliest time the Assertion may be used per conditions | Cannot be used before this mark, subject to skew |
| `Assertion/Conditions@NotOnOrAfter` | Time when conditions expire | Invalid at or after this mark, subject to skew |
| `Subject/SubjectConfirmation/SubjectConfirmationData@NotBefore` | Earliest time for subject confirmation per method, if present | Additional bound; **does not replace** Conditions |
| `Subject/SubjectConfirmation/SubjectConfirmationData@NotOnOrAfter` | Expiration bound of bearer subject confirmation | Must be checked separately for the confirmation used |
| `Response@IssueInstant` | Time the IdP created the Response | Not equivalent to Assertion expiration |
| `Assertion@IssueInstant` | Time the IdP issued the Assertion | Does not replace NotBefore/NotOnOrAfter |
| `AuthnStatement@AuthnInstant` | Time the user actually authenticated at the IdP | May occur earlier than Assertion issuance |
| `AuthnStatement@SessionNotOnOrAfter` | Session limit associated with the authentication statement, when provided | **Not** a duplicate of Assertion expiration |
| `Metadata@validUntil` | Validity deadline of published SAML metadata | For managing metadata trust, not login Assertions |

**Do not equate fields merely because they all contain timestamps.** For example, the user logs into the IdP at 09:40, the IdP issues the Assertion at 10:00, bearer confirmation expires at 10:03, and Conditions expire at 10:10. The SP must enforce each structure's bound rather than using `AuthnInstant = 09:40` to conclude the current Response has expired.

### XML Example with Two Validity Windows

~~~xml
<saml:Assertion
    xmlns:saml="urn:oasis:names:tc:SAML:2.0:assertion"
    ID="_assertion-example"
    Version="2.0"
    IssueInstant="2026-11-07T10:00:00Z">

    <saml:Issuer>https://idp.example.com/saml</saml:Issuer>

    <saml:Subject>
        <saml:NameID>employee-123</saml:NameID>
        <saml:SubjectConfirmation
            Method="urn:oasis:names:tc:SAML:2.0:cm:bearer">
            <saml:SubjectConfirmationData
                InResponseTo="_request-123"
                Recipient="https://sp.example.com/login/saml2/sso/corp"
                NotOnOrAfter="2026-11-07T10:03:00Z"/>
        </saml:SubjectConfirmation>
    </saml:Subject>

    <saml:Conditions
        NotBefore="2026-11-07T09:59:00Z"
        NotOnOrAfter="2026-11-07T10:10:00Z">
        <saml:AudienceRestriction>
            <saml:Audience>https://sp.example.com/sp/corp</saml:Audience>
        </saml:AudienceRestriction>
    </saml:Conditions>
</saml:Assertion>
~~~

This is only a **semantic illustration XML fragment**; it lacks a SAML Response envelope, `AuthnStatement`, and valid signature, so it **cannot be used to log in**. In real verification, you must verify the XML signature over the right signed element, issuer, and other constraints before trusting attribute content.

At `10:04:00Z` with **zero skew**, `Conditions` is still inside 09:59–10:10, yet bearer `SubjectConfirmationData` already expired at 10:03. Unless another profile-valid SubjectConfirmation exists, the SP must **reject** even though Conditions are still valid.

## 3. What Does NotBefore Mean?

`NotBefore` specifies the **start bound**. If the bound is `2026-11-07T10:00:00Z`:

- `09:59:59.999Z`: not yet eligible when skew is 0.
- `10:00:00.000Z`: has reached the valid start time.
- `10:01:00Z`: passes the start check, yet must still pass the end check and other conditions.

Mathematically, with `b = NotBefore` and `n = now`:

~~~text
Without clock skew:
n >= b    -> passes NotBefore condition
n <  b    -> not yet at NotBefore
~~~

Do not substitute `Assertion.IssueInstant` when `Conditions.NotBefore` has a different value. An IdP may issue an Assertion at `09:59:30Z` while setting `NotBefore = 10:00Z`; the SP receiving it a few seconds early is a timing issue that may need a **small, policy-approved** skew.

In custom checkers, the start-bound condition must be applied to the right `Conditions` or `SubjectConfirmationData` without skipping other time-constraint checks.

## 4. What Does NotOnOrAfter Mean? Why Not "Until the End of That Second"?

`NotOnOrAfter` is the **expiration instant**. The key point is the **exclusive** nature of the end instant.

Suppose `NotOnOrAfter = 2026-11-07T10:05:00Z` and skew is 0:

| `now` | Valid for end bound? | Reason |
| --- | --- | --- |
| `10:04:59.999Z` | Yes | Before the end bound |
| `10:05:00.000Z` | **No** | Exactly at the expiration instant |
| `10:05:00.001Z` | No | Past expiration |
| `10:08:00Z` | No | Long expired |

Formula:

~~~text
Without clock skew:
n < e     -> not expired
n >= e    -> expired
e = NotOnOrAfter
~~~

**Common bug:** writing `now <= NotOnOrAfter` causes an instant equal to expiry to be accepted. In Java, for an exclusive upper bound, use `now.isBefore(expiresAt)`, not `!now.isAfter(expiresAt)`.

Saying "expires at 10:05" does not mean usable through `10:05:59`. Time is a precise `Instant`, not a minute rounded for comparison.

## 5. Half-Open Validity Interval and Input Preconditions

When both attributes are present:

~~~text
[b, e)

b = NotBefore
e = NotOnOrAfter
Requires b < e
Valid when b <= now < e
~~~

This is a **half-open interval**: inclusive on the left, exclusive on the right.

If `NotBefore >= NotOnOrAfter`, the interval is invalid; per SAML Core, when both appear, NotBefore must be **strictly earlier** than NotOnOrAfter. Never use clock skew to "rescue" an inverted interval: that can produce unpredictable behavior and hide IdP bugs.

**Can one attribute be missing?** In `<Conditions>` of **SAML Core**, both `NotBefore` and `NotOnOrAfter` are defined as **optional**. Omitting a bound means that bound is unspecified at the Conditions level. However, **SAML profiles and SP trust policies may mandate specific bounds**. In Bearer Web Browser SSO, `SubjectConfirmationData@NotOnOrAfter` is an important profile constraint. Do not assume "missing is always valid" across all Web SSO, nor claim every `Conditions` missing an attribute is invalid XML.

**Safe decision:** define mandatory bounds per actual profile, never write a custom validator that skips expiration when a field is absent, and never imply infinite validity if enterprise policy requires a maximum TTL.

## 6. What Is Clock Skew and What Effect Does It Have?

Suppose IdP B runs **90 seconds** fast relative to SP A. The IdP issues an Assertion with `NotBefore=10:00:00Z` per its clock, while the SP sees `09:58:30Z`. Without tolerance, the SP rejects a not-yet-valid Assertion even though both sides are operating normally.

**Clock skew tolerance** is a `Duration` configured at the SP, e.g. 120 seconds, to accept small discrepancies **when evaluating timestamps**. Typically tolerance affects **both the early and late bounds**:

- At the start of the interval, allows `now` to be up to `skew` earlier than `NotBefore`.
- At the end of the interval, allows `now` to be up to `skew` later than `NotOnOrAfter`.

Conceptual model with `δ = skew >= 0`:

~~~text
Original:  b <= now < e

With skew:
             now + δ >= b
         AND now - δ <  e

Equivalent to:
          b - δ <= now < e + δ
~~~

Where `b < e` must still hold before applying tolerance.

Example:

~~~text
NotBefore     = 10:00Z
NotOnOrAfter  = 10:05Z
clock skew    = 2 minutes

Original window:           [10:00, 10:05)
Accepted window with skew: [09:58, 10:07)

09:57:59 -> FAIL
09:58:00 -> passes time check
10:04:59 -> passes time check
10:05:00 -> passes time check due to skew
10:06:59 -> passes time check due to skew
10:07:00 -> FAIL
~~~

**This is only a mathematical model for learning:** the actual Spring Security/OpenSAML verifier also involves multiple validators, policies, resolution/precision, and profile requirements. Never interpret a `true` time check as proof that authentication succeeded.

### Why Not Just Set Skew to One Hour for Convenience?

If skew is too large, the SP accepts Assertions **earlier or later** than the IdP intended. The window expands on both ends, increasing replay exposure or undermining expiration. Skew is **not** session lifetime and must never substitute for NTP configuration.

The right value depends on security requirements and synchronization accuracy between both sides; **there is no single numeric value valid for every organization**. Some docs use 10 minutes to illustrate the API, which does not mean production should set 10 minutes.

## 7. How Should Allowed Clock Skew Be Chosen?

First distinguish **observed offset** from **approved tolerance**:

- `observed offset`: discrepancy of the server clock against an accurate time source, measurable by infra/NTP.
- `configured clock skew`: tolerance accepted by the validator when evaluating SAML timestamps.
- `Assertion lifetime`: validity issued by the IdP (e.g., 2–5 minutes for bearer confirmation under a specific policy).
- `Session lifetime`: cookie/application session duration; does not necessarily match Assertion lifetime.

Selection procedure:

1. Measure clock drift between KDC/NTP/system time of IdP and SP hosts at multiple times.
2. Check drift across Spring nodes behind a load balancer, pods/containers, and hosts.
3. Synchronize clocks using NTP/chrony/systemd-timesyncd/Windows Time per infrastructure.
4. Agree with IdP administrators on SAML assertion lifetime, bearer confirmation lifetime, and **maximum tolerance**.
5. Pick the **smallest skew sufficient for legitimate drift and network jitter** once clocks are stable; do not raise it endlessly to hide infra faults.
6. Test boundary timestamps and negative cases across multiple real nodes.
7. Monitor failures over time, tuning NTP before increasing skew.
8. Document the chosen value, owner, rationale, and review date.

**Study recommendation:** you can experiment with `Duration.ofSeconds(60)` or `Duration.ofMinutes(2)` in staging to observe effects, then apply to production only after measuring offset and obtaining approval. These are **examples**, not mandatory defaults of Spring Security or the SAML standard.

## 8. Handling When Both Conditions and SubjectConfirmationData Are Present

SAML Web Browser SSO does not inspect only one time window. An Assertion typically carries:

1. `Conditions@NotBefore/NotOnOrAfter` — bounds **usability of the Assertion**.
2. `SubjectConfirmationData@NotOnOrAfter` — bounds **bearer subject confirmation** at the right recipient/ACS.
3. `SubjectConfirmationData@NotBefore` — start bound **if provided by profile/message**.
4. Other constraints such as `AudienceRestriction` and `SubjectConfirmationData@Recipient/InResponseTo`.

An Assertion is usable only if **Conditions are valid** **and** there is a **profile-valid SubjectConfirmation**, after all other verifications also succeed.

### Why Not Take the Latest Expiration Bound?

Suppose:

~~~text
Conditions:              [09:59, 10:10)
SubjectConfirmationData: [10:00, 10:03)

SP receipt time:         10:04
Skew:                    0 minutes

Conditions:              PASS
SubjectConfirmationData: FAIL
Bearer verification:     FAIL
~~~

If you pick `max(10:10, 10:03) = 10:10` as a combined expiry, you **unwittingly bypass** the bearer confirmation bound. Conversely, picking "the earlier expiry" is just shorthand for two specific intervals; in production you must verify **each element with its proper validator** because SAML can have multiple SubjectConfirmations and extra conditions.

### What If Multiple SubjectConfirmations Exist?

SAML may contain multiple `<SubjectConfirmation>` elements. Per profile/errata, **one matching SubjectConfirmation** can suffice to confirm the subject, yet each entry must be evaluated with its method, recipient, InResponseTo, time window, and applicable policy. Never take the longest `NotOnOrAfter` across entries and implicitly apply it to all; nor treat an expired confirmation as valid merely because another confirmation is valid when the two entries differ in method or recipient.

## 9. Receipt Time, Verification Time, and Server Clock

Three timestamps are easily confused:

- **`IssueInstant`:** timestamp set by the IdP when creating the Response/Assertion.
- **`receivedAt`:** time the SP actually receives the HTTP POST at the ACS; measured by a trusted server clock.
- **`validatedAt`:** time the validator performs the comparison; in synchronous processing, very close to receivedAt.

Never take timestamps from the browser, a user-sent `Date` header, frontend JavaScript, or client-supplied RelayState as `now` for validation. If the application distributes work via queues or processes asynchronously, define a policy for evaluating at receipt vs verification per library/design and guard against long-delayed messages.

**Use `Instant` / `Clock`, not timezone-less local time.** Example:

~~~text
2026-11-07T10:00:00Z
2026-11-07T17:00:00+07:00

The two values above represent the exact same instant.
~~~

Java's `Instant.parse("2026-11-07T10:00:00Z")` represents UTC. If receiving a timestamp with an offset, parse via `OffsetDateTime.parse(...).toInstant()`. Never parse SAML timestamps with `LocalDateTime` and implicitly apply the server's timezone.

Note that local timezone/daylight-saving changes must not alter `Instant`; SAML timestamps follow `xsd:dateTime` per spec, usually emitted in UTC `Z`.

## 10. Configuring Clock Skew in Spring Security 7.x / OpenSAML 5

**Version milestone:** official Spring Security 7.1 documentation states that inbound SAMLResponse processing uses `Saml2AuthenticationTokenConverter` and `OpenSaml5AuthenticationProvider`. To configure clock skew, Spring Security provides the API:

~~~java
OpenSaml5AuthenticationProvider provider =
        new OpenSaml5AuthenticationProvider();

OpenSaml5AuthenticationProvider.AssertionValidator validator =
        OpenSaml5AuthenticationProvider.AssertionValidator.builder()
                .clockSkew(Duration.ofMinutes(2))
                .build();

provider.setAssertionValidator(validator);
~~~

`Duration.ofMinutes(2)` here is **merely a sample policy**, not a general recommendation or framework default.

### JavaConfig for a Spring Security Servlet Application

File `SamlSkewSecurityConfiguration.java`:

~~~java
import java.time.Duration;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.authentication.ProviderManager;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.saml2.provider.service.authentication.OpenSaml5AuthenticationProvider;
import org.springframework.security.saml2.provider.service.authentication.OpenSaml5AuthenticationProvider.AssertionValidator;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class SamlSkewSecurityConfiguration {

    @Bean
    SecurityFilterChain samlSecurity(HttpSecurity http) throws Exception {
        OpenSaml5AuthenticationProvider provider =
                new OpenSaml5AuthenticationProvider();

        AssertionValidator assertionValidator = AssertionValidator.builder()
                .clockSkew(Duration.ofMinutes(2))
                .build();

        provider.setAssertionValidator(assertionValidator);

        http.authorizeHttpRequests(auth -> auth
                .anyRequest().authenticated())
            .saml2Login(saml -> saml
                .authenticationManager(new ProviderManager(provider)));

        return http.build();
    }
}
~~~

This is **configuration code inside a Spring project**, not a plain Java program compiled with `javac`. It requires Spring Security SAML2 dependencies, `RelyingPartyRegistrationRepository`, IdP metadata/certificates, and valid web config. If the project has multiple `SecurityFilterChain` beans, ensure the ACS endpoint goes through the chain using the customized provider.

Explanation:

- `OpenSaml5AuthenticationProvider` performs authentication and applies required validators to SAML Response/Assertions.
- `AssertionValidator.builder().clockSkew(...)` adjusts time-check tolerance in the assertion validation context per current API.
- `setAssertionValidator(...)` supplies the configured validator to the provider.
- `saml2Login(...authenticationManager(...))` ensures the SAML filter uses the `ProviderManager` holding the customized provider rather than leaving an unused bean.
- Using the default builder with `clockSkew` **does not disable** issuer, audience, signature, or subject confirmation validation.

**Important:** this configuration targets **Spring Security 7 / OpenSAML 5** or a branch confirmed to support that exact API. Do not copy 7.x class/method names into a Spring Security 5/6 app using a different OpenSAML provider without checking versions. In particular, assertion validator `clockSkew` **must not be assumed to automatically alter all other time bounds** such as metadata validUntil, session TTL, logout timestamps, or cookie expiration.

## 11. What to Do When Using Spring Security 5.x or 6.x?

Spring Security evolved provider classes across generations:

| Line | Related Provider/API | Approach |
| --- | --- | --- |
| **Legacy Spring Security 5.4/5.5** | `OpenSamlAuthenticationProvider` | Legacy `setResponseTimeValidationSkew(Duration)` (deprecated), or custom assertion validator using `ValidationContext` |
| **Spring Security 6.0–some 6.x** | `OpenSaml4AuthenticationProvider` | Check `createDefaultAssertionValidatorWithParameters` and `ValidationContext` for your exact patch |
| **Branches supporting OpenSAML 5** | `OpenSaml5AuthenticationProvider` | Use `AssertionValidator.builder().clockSkew(...)` when Javadoc confirms |
| **Spring Security 7.x** | `OpenSaml5AuthenticationProvider` | Use documented `AssertionValidator` builder as above |

In older APIs, parameters like `SAML2AssertionValidationParameters.CLOCK_SKEW` of OpenSAML `ValidationContext` are measured in **milliseconds**. Never pass `120` thinking it is 120 seconds when the API expects **milliseconds**: that is only 0.12 seconds. Newer API lines take `java.time.Duration`, avoiding unit mistakes.

**Do not guess the provider from Spring Boot's major version alone.** Inspect the runtime dependency graph:

~~~bash
./gradlew dependencies --configuration runtimeClasspath
./gradlew dependencyInsight --configuration runtimeClasspath --dependency spring-security-saml2-service-provider
./gradlew dependencyInsight --configuration runtimeClasspath --dependency spring-security-config
~~~

With Maven:

~~~bash
mvn dependency:tree -Dincludes=org.springframework.security
~~~

Consult docs/Javadoc for the **exact artifact version**. A Spring Security upgrade can also change OpenSAML, Servlet `javax` → `jakarta`, or method signatures. Never override just `spring-security-saml2-service-provider` alone to grab an API while ignoring the rest of the module BOM.

### Should You Replace the Assertion Validator Completely?

Not if you only need to adjust tolerance. A handwritten custom validator can accidentally drop `AudienceRestrictionValidator`, `BearerSubjectConfirmationValidator`, or other condition checks. Spring Security docs show ways to retain the default validator and chain additional validation; **do not replace the entire default** without proving all profile checks remain intact.

Especially, **never** fix time errors by removing all condition validators, disabling signatures, or dropping `InResponseTo`. Achieving login by deleting safety constraints is a design failure.

## 12. Standalone Java 17: Verifying Exact Boundaries and Clock Skew

The following example uses no Spring Security, OpenSAML, or XML. It **models half-open interval comparison** so you can verify inclusive/exclusive signs, skew expansion, and having **two** check windows: `Conditions` and `SubjectConfirmationData`.

Create file **`SamlTimeWindowDemo.java`**:

~~~java
import java.time.Duration;
import java.time.Instant;

public class SamlTimeWindowDemo {

    record Window(Instant notBefore, Instant notOnOrAfter) {}

    static boolean validAt(
            Instant now, Window window, Duration skew) {
        if (skew.isNegative()) {
            throw new IllegalArgumentException("negative skew");
        }
        if (!window.notBefore().isBefore(window.notOnOrAfter())) {
            return false;
        }
        return !now.plus(skew).isBefore(window.notBefore())
                && now.minus(skew).isBefore(window.notOnOrAfter());
    }

    static boolean bothValid(
            Instant now, Window conditions,
            Window subjectConfirmation, Duration skew) {
        return validAt(now, conditions, skew)
                && validAt(now, subjectConfirmation, skew);
    }

    public static void main(String[] args) {
        Instant now = Instant.parse("2026-11-07T10:00:00Z");
        Duration none = Duration.ZERO;
        Duration threeMinutes = Duration.ofMinutes(3);

        Window normal = new Window(
                now.minusSeconds(60), now.plusSeconds(300));

        Window future = new Window(
                now.plusSeconds(120), now.plusSeconds(300));

        Window endingNow = new Window(
                now.minusSeconds(300), now);

        Window expiredFiveMinutesAgo = new Window(
                now.minusSeconds(900), now.minusSeconds(300));

        Window subjectExpiredOneSecondAgo = new Window(
                now.minusSeconds(60), now.minusSeconds(1));

        Window invalid = new Window(
                now.plusSeconds(60), now.minusSeconds(60));

        System.out.println("Inside: "
                + validAt(now, normal, none));
        System.out.println("End exclusive: "
                + validAt(now, endingNow, none));
        System.out.println("Future without skew: "
                + validAt(now, future, none));
        System.out.println("Future with 3m skew: "
                + validAt(now, future, threeMinutes));
        System.out.println("Expired 5m, skew 3m: "
                + validAt(now, expiredFiveMinutesAgo, threeMinutes));
        System.out.println("Subject expires first: "
                + bothValid(now, normal, subjectExpiredOneSecondAgo, none));
        System.out.println("Invalid interval: "
                + validAt(now, invalid, threeMinutes));
    }
}
~~~

Run with JDK 17 or later:

~~~bash
javac SamlTimeWindowDemo.java
java SamlTimeWindowDemo
~~~

**Exact stdout:**

~~~text
Inside: true
End exclusive: false
Future without skew: false
Future with 3m skew: true
Expired 5m, skew 3m: false
Subject expires first: false
Invalid interval: false
~~~

Why is each result right?

- `Inside: true` — now falls within [-1 minute, +5 minutes].
- `End exclusive: false` — expiry equal to now is **expired**.
- `Future without skew: false` — Assertion has not reached NotBefore (+2 minutes).
- `Future with 3m skew: true` — +3 minute tolerance covers the +2 minute offset.
- `Expired 5m, skew 3m: false` — expired beyond the allowed tolerance.
- `Subject expires first: false` — Conditions still have time left yet bearer confirmation expired.
- `Invalid interval: false` — `NotBefore` after `NotOnOrAfter` must be rejected before considering skew.

**Important limitation:** `Window` requires both bounds for ease of study; SAML Core permits `Conditions` to omit one bound, and the Web Browser bearer profile has distinct rules. The program cannot fully simulate missing-field rules, signatures, issuer, recipient, multiple confirmations, DateTime precision, replay cache, or Spring Security policies. Never use `validAt` in place of `OpenSaml5AuthenticationProvider`.

## 13. Boundary Test Table to Avoid Comparison Bugs

Use a sample Assertion with:

~~~text
NotBefore     = 2026-11-07T10:00:00Z
NotOnOrAfter  = 2026-11-07T10:05:00Z
Skew          = 0 or 2 minutes
~~~

| Check time `now` | Skew = 0 | Skew = 2 minutes | Interpretation |
| --- | --- | --- | --- |
| 09:57:59Z | FAIL | FAIL | Before widened start |
| 09:58:00Z | FAIL | PASS on time | Exact widened start |
| 09:59:59Z | FAIL | PASS on time | Less than 2 minutes early |
| 10:00:00Z | PASS | PASS | Exact NotBefore, inclusive |
| 10:04:59Z | PASS | PASS | Before expiry |
| 10:05:00Z | **FAIL** | PASS on time | Exact expiry, exclusive without skew |
| 10:06:59Z | FAIL | PASS on time | Less than 2 minutes late |
| 10:07:00Z | FAIL | **FAIL** | Exact widened end, exclusive |
| 10:07:01Z | FAIL | FAIL | Past widened end |

**PASS on time** only means the illustrative time formula passed; it is **insufficient** to authenticate a SAML Response.

Additional mandatory cases:

- NotBefore **equal to** NotOnOrAfter → FAIL because interval has zero length.
- NotBefore **after** NotOnOrAfter → FAIL even with large skew.
- Conditions still valid yet SubjectConfirmationData expired → FAIL unless another valid confirmation exists.
- Conditions expired yet SubjectConfirmationData still valid → FAIL; both are mandatory constraints.
- SAML timestamp with `Z` and with `+07:00` representing the same Instant → results must not differ.
- IdP signs an assertion too far in the future beyond skew → FAIL.
- Assertion valid in time yet wrong issuer/audience/recipient → FAIL.
- Assertion valid in time yet invalid signature → FAIL.
- Assertion valid in time yet `InResponseTo` mismatches request → FAIL per SP-initiated policy.
- Replaying an old Response within tolerance window → must be blocked by anti-replay per policy.

## 14. Why Does Valid Time Not Prevent Replay?

An attacker holding a copy of a validly signed Assertion may not be able to alter its content. However, if re-submitted while the SP still considers it valid, checking NotBefore/NotOnOrAfter alone can be **insufficient** to detect reuse.

Defensive layers to combine:

1. **Short time bounds** for bearer confirmation and Conditions per IdP contract.
2. **Recipient/Destination** matching the exact permitted ACS.
3. **AudienceRestriction** matching the application's SP Entity ID.
4. **Issuer + signature** from the exact registered IdP.
5. **InResponseTo** bound to the browser/session AuthnRequest when using SP-initiated SSO.
6. **Replay detection** by Message/Assertion ID when threat model/profile requires.
7. **Session management** guarding against login fixation, cookie issues, and timeouts.
8. **Independent role/object authorization** so SAML never widens privileges by itself.

If skew grows from 2 minutes to 15 minutes, the time check widens in both directions; **the window for re-accepting old messages increases** in the simple model. Raising skew alone does not fix broken NTP and cannot replace anti-replay.

For `OneTimeUse` in SAML Conditions, verify whether the framework/profile actually enforces this condition. Per Spring Security 7.x docs, `OneTimeUseConditionValidator` can be added to the assertion validator via the builder when policy requires; do not assume a NotOnOrAfter check enforces OneTimeUse automatically.

## 15. Handling Clock Drift in Real Infrastructure

Faults can originate on any side:

| Layer | Risk | What to inspect |
| --- | --- | --- |
| **IdP** | IdP/cluster host clock drifts or shifts on failover | Accurate time across nodes and NTP sources |
| **SP** | JVM/container reads non-standard host clock | Monitor host time, NTP, image/OS, multiple pods |
| **Network** | Request to IdP and return is slow, proxy/buffering | Round-trip, P95/P99 latency, timeouts, queues |
| **Load balancer** | Node A on time, node B drifted | Check all nodes simultaneously |
| **Clock configuration** | Confusing Instant drift with display timezone | Compare UTC timestamps and actual offset |
| **Parser** | Parsing `xsd:dateTime` with wrong timezone or second rounding | Use SAML/XML library and exact `Instant` |
| **IdP policy** | Bearer lifetime too short for user flow | Coordinate valid TTL with IdP instead of setting huge skew |
| **SP policy** | Custom validator drops Conditions/bearer expiration | Restore standard validators, add regression tests |

On Linux with systemd, inspect system time (depending on distro):

~~~bash
date -u
timedatectl status
~~~

If chrony is installed:

~~~bash
chronyc tracking
chronyc sources -v
~~~

On a Windows Domain Controller or Windows host:

~~~powershell
w32tm /query /status
w32tm /query /source
~~~

There is **no fixed stdout** for the commands above. Inspect actual status, estimated offset, time source, reachability, and synchronization health. Never manually shift a production clock just to get past a SAML login failure: side effects can hit TLS, log ordering, databases, caches, schedulers, and other auth protocols.

In Kubernetes, most containers share the host clock; do not assume changing a container's `TZ` shifts UTC Instant. `TZ` mainly affects local time formatting. The root issue may be host NTP or the virtualization clock provider.

## 16. Diagnosing Failures Before Increasing clockSkew

When seeing logs such as "assertion not yet valid", "assertion expired", or "subject confirmation has expired", determine:

1. Was the Assertion rejected at **Conditions** or **SubjectConfirmationData**?
2. What are the exact `NotBefore` / `NotOnOrAfter` values in the message after **signature verification**?
3. When did the SP receive the request per a trusted UTC clock? Is the IdP fast or slow?
4. Were `IssueInstant` or `AuthnInstant` confused with expiry?
5. Was time lost to IdP MFA, cross-domain redirects, browser delays, proxy queues, or network?
6. Was session/`InResponseTo` lost or audience/recipient wrong, while logs lumped it under "SAML invalid"?
7. Which validator is actually running: default or custom `AssertionValidator`?
8. Is the configured skew attached to the active provider, or sitting on an unused bean?

**Prioritized fix order:**

- First synchronize **IdP/SP clocks** and check network/NTP/firewalls in the environment.
- Next evaluate **IdP-issued lifetimes** and SAML round-trip properly.
- Then verify a tight **clock skew policy** configured in the right place.
- Lastly adjust complex SAML validation components only if evidence shows an API/config defect.

If a specific request only fails when routed through node B, suspect **per-node clock drift** before tuning application-wide beans.

## 17. Session, Logout, and Post-Login Validity Concerns

Assertion validity applies when **accepting the SAML Assertion** at the ACS. Once Spring Security builds `Authentication` and the app issues its own session cookie, **the application session does not automatically expire when NotOnOrAfter passes**. Those are two distinct time layers.

Example:

~~~text
10:00 IdP issues Assertion (Conditions expire 10:10)
10:02 SP verifies successfully and creates app session
10:10 Assertion's Conditions expire
10:30 App session remains active (if app is configured so)
~~~

This is not self-contradictory: a SAML Assertion serves to **establish identity at login time**; the application must manage session TTL, `SessionNotOnOrAfter` if applied per profile, logout, role refresh, and deprovisioning per policy.

Therefore do not tune session timeout by raising/lowering `clockSkew`, nor treat `NotOnOrAfter` as the moment all cookies must immediately be cleared. If SAML session policy requires the SP to honor `SessionNotOnOrAfter`, enforce it explicitly via session management and dedicated tests.

## 18. Other SAML Timestamps Must Not Be Handled Blindly Together

Beyond Assertion Conditions, other marks exist:

- `SAML Response IssueInstant`: message generation; not Assertion expiration.
- `Assertion IssueInstant`: Assertion issuance; may have a separate "staleness" limit per policy, yet does not replace `Conditions`.
- `SubjectConfirmationData NotOnOrAfter`: bearer confirmation expiration, often tighter than `Conditions`.
- `AuthnStatement AuthnInstant`: when user authentication occurred; usable for evaluating `max authentication age` and MFA freshness.
- `AuthnStatement SessionNotOnOrAfter`: session time cap per statement, if present.
- `SAML Metadata validUntil`: metadata validity period; requires reload/refresh workflow and signature verification.
- `LogoutRequest NotOnOrAfter`: logout message bound, not login assertion.

Do not apply `clockSkew` to every timestamp via a single custom helper unless the profile/library does so. For instance, metadata or logout bounds may be handled by other components; verify with per-component tests and resolved Javadoc.

## 19. Scenario Exercises

### Scenario A: 90-Second Offset

IdP issues `NotBefore=10:00:00Z`, `NotOnOrAfter=10:05:00Z`. SP receives at `09:58:30Z`.

- Skew = 0: **FAIL** because NotBefore has not been reached.
- Skew = 2 minutes: **PASS on the illustrative timestamp** because now + 2 minutes = 10:00:30Z.
- If issuer/signature/audience are wrong: still **FAIL overall** despite valid timestamps.

**Operational path:** check NTP/SP offset first; if a small stable drift exists that policy permits, configure tight skew and document it.

### Scenario B: Conditions Still Valid Yet SubjectConfirmation Expired

`Conditions` expires at 10:10, `SubjectConfirmationData` expires at 10:03; SP receives at 10:04; skew=0.

**Result:** bearer confirmation expired; must reject unless another valid confirmation exists. Do not use 10:10 as the expiry for both.

### Scenario C: Exactly Equal to NotOnOrAfter

`NotOnOrAfter=10:05:00Z`, SP evaluates `10:05:00Z`, skew=0.

**Result:** **FAIL**. Because NotOnOrAfter is exclusive; writing `now <= e` is a comparison bug.

### Scenario D: Increasing Skew to 30 Minutes to Prevent Login Timeout

A team wants to raise skew to 30 minutes because users take long completing MFA at the IdP.

**Analysis:** 30 minutes widens the SAML assertion acceptance window, increasing replay risk. Check **when the IdP issues the assertion**: if the IdP issues it after MFA, user interaction time beforehand does not necessarily count against Assertion age. Check real round-trip, NTP, and bearer confirmation lifetime; increase tolerance only to a measured/approved bound.

### Scenario E: Multi-Node Clock Drift

Node A succeeds at login; Node B fails `NotBefore` with the same IdP under a load balancer.

**Analysis:** compare `date -u` / NTP offset across hosts A/B, check NTP sources, time drift, session propagation, and reverse proxy. Do not jump to changing SAML issuer/audience when identical configs differ only by node.

### Scenario F: Java Local-Time Parsing

IdP issues `2026-11-07T10:00:00Z`; developer parses it as local `10:00` in Asia/Ho_Chi_Minh and compares against server UTC.

**What went wrong?** `10:00Z` is actually `17:00+07:00`. Convert all instants to `Instant`, never mixing local time and UTC; changing display timezone does not fix clock drift.

## 20. Testing and Operations Checklist

- [ ] Identify the actual Spring Security/OpenSAML provider from the dependency graph.
- [ ] `RelyingPartyRegistration` trusts the right IdP, certificate, and ACS.
- [ ] Check `Conditions@NotBefore` inclusive and `Conditions@NotOnOrAfter` exclusive.
- [ ] Check `SubjectConfirmationData@NotOnOrAfter`, `Recipient`, and `InResponseTo` separately.
- [ ] Comparisons with `NotBefore >= NotOnOrAfter` must reject.
- [ ] All timestamps normalized to UTC/`Instant`; never round to minutes.
- [ ] Clock skew is measured/approved and small, not guessed by default.
- [ ] JavaConfig attaches the assertion validator to the **active** authentication provider.
- [ ] Retain all default validations for signature, issuer, audience, subject confirmation, and conditions.
- [ ] Test just before/at/after every boundary with and without skew.
- [ ] Test Conditions still valid yet bearer confirmation expired, and vice versa.
- [ ] Enforce IdP-initiated per separate policy; never drop request correlation carelessly.
- [ ] Appropriate replay prevention and session cookie security are in place.
- [ ] SP/IdP nodes and container hosts synchronize from reliable time sources.
- [ ] Negative tests do not turn into PASS merely by raising skew.
- [ ] Never store raw SAML Assertions, private keys, or personal data in production logs.
- [ ] Monitor time-validation failure metrics to catch clock drift or IdP lifetime changes.
- [ ] Verify session TTL/`SessionNotOnOrAfter` separately from Assertion expiration.
- [ ] When adjusting skew, record the decision, test in staging, and have a rollback plan.

## 21. Authoritative Source References

Spring Security docs and API versions change; open the exact line running in your application:

1. [Spring Security — Authenticating SAML Responses](https://docs.spring.io/spring-security/reference/servlet/saml2/login/authentication.html): guide for **Setting a Clock Skew** with `OpenSaml5AuthenticationProvider.AssertionValidator.builder().clockSkew(Duration)` and wiring `AuthenticationManager`.
2. [Spring Security — SAML2 Login Overview](https://docs.spring.io/spring-security/reference/servlet/saml2/login/overview.html): SP/IdP flow, ACS, and role of `Saml2WebSsoAuthenticationFilter`.
3. [Spring Security — SAML 2.0 Migrations](https://docs.spring.io/spring-security/reference/6.5/migration-7/saml2.html): OpenSAML 4/5 differences and provider versions during upgrade.
4. [Spring Security 6.0 — OpenSaml4AuthenticationProvider Javadoc](https://docs.spring.io/spring-security/site/docs/6.0.x/api/org/springframework/security/saml2/provider/service/authentication/OpenSaml4AuthenticationProvider.html): `ValidationContext` parameters and adding validators in legacy APIs.
5. [Spring Security 5.4 — OpenSamlAuthenticationProvider Javadoc](https://docs.spring.io/spring-security/site/docs/5.4.2/api/org/springframework/security/saml2/provider/service/authentication/OpenSamlAuthenticationProvider.html): legacy `setResponseTimeValidationSkew` API and deprecation notes.
6. [OASIS SAML 2.0 Core, `2.5.1.2`](https://docs.oasis-open.org/security/saml/v2.0/saml-core-2.0-os.pdf): semantics of `NotBefore`, `NotOnOrAfter`, optional Conditions bounds, and requirement `NotBefore < NotOnOrAfter` when both appear.
7. [OASIS SAML 2.0 Approved Errata](https://docs.oasis-open.org/security/saml/v2.0/sstc-saml-approved-errata-2.0-cd-02.html): validating bearer SubjectConfirmationData NotOnOrAfter, Recipient, InResponseTo, and SessionNotOnOrAfter lifetime.
8. [RFC 7522 — SAML2 Profile for OAuth2](https://www.rfc-editor.org/rfc/rfc7522.html): a **different profile from Web Browser SSO**, yet illustrates expiry and clock skew requirements for SAML bearer assertions. Do not substitute this RFC for OASIS Web SSO conditions.
9. [Microsoft Learn — SAML Protocol](https://learn.microsoft.com/azure/active-directory/develop/single-sign-on-saml-protocol): real-world examples of `Conditions` and `SubjectConfirmationData` and their differing lifetimes.

**Final takeaway:** `NotBefore` is an **inclusive start bound**, `NotOnOrAfter` is an **exclusive expiration instant**, and `clockSkew` is only a small margin to compensate for clock drift. The SP must independently validate **Conditions**, **SubjectConfirmation**, signature, issuer, audience, recipient, request correlation, and anti-replay. Fix clock infrastructure first, tune policy-approved clock skew second; never use a large skew to bypass SAML2 security boundaries.