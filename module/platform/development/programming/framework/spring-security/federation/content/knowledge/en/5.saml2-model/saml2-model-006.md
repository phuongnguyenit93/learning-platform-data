# Conditions, AudienceRestriction, and Assertion Lifetimes in SAML 2.0

A **SAML 2.0 Assertion** is a set of statements made by an Identity Provider (IdP) about a subject, yet **a validly signed assertion does not mean every Service Provider (SP) is permitted to use it at any time**. The recipient must verify the usage boundaries: **from when until before when** the assertion is valid, **which SP** it is intended for, and **how the subject is confirmed**.

The central group of checks in this lesson is `<saml:Conditions>`, `<saml:AudienceRestriction>`, and the `NotBefore`/`NotOnOrAfter` attributes. For SAML Web Browser SSO, you must also understand the deadline on **`SubjectConfirmationData`**: it is an independent constraint that can render an assertion unusable even when `Conditions` is still valid.

## 1. Locating the Fields in an Assertion

~~~text
samlp:Response
├── @ID, @IssueInstant, @Destination, @InResponseTo
├── saml:Issuer
└── saml:Assertion  (protected by signature per binding/profile)
    ├── @ID, @IssueInstant
    ├── saml:Issuer
    ├── saml:Subject
    │   └── saml:SubjectConfirmation Method="...:bearer"
    │       └── saml:SubjectConfirmationData
    │           ├── @Recipient
    │           ├── @InResponseTo
    │           └── @NotOnOrAfter
    ├── saml:Conditions
    │   ├── @NotBefore
    │   ├── @NotOnOrAfter
    │   └── saml:AudienceRestriction
    │       └── saml:Audience
    └── saml:AuthnStatement
        ├── @AuthnInstant
        └── @SessionNotOnOrAfter (if present)
~~~

The positions above are a conceptual diagram; some elements may be absent or appear multiple times depending on schema/profile. When validating **Web SSO**, you must not look only at `Conditions` while ignoring `Issuer`, `Destination`, `SubjectConfirmation`, signatures, `InResponseTo` correlation, and anti-replay.

| Attribute / element | Meaning | Must not be mistaken for |
| --- | --- | --- |
| `Assertion@IssueInstant` | Time the IdP issued the assertion. | Not itself the expiration deadline. |
| `Conditions@NotBefore` | Earliest time the assertion is permitted to be used per conditions. | Not the user's login timestamp. |
| `Conditions@NotOnOrAfter` | **Exclusive** end boundary of the assertion validity window. | Not an account or HTTP session expiration date. |
| `AudienceRestriction/Audience` | List of relying parties/SPs permitted to use the assertion per audience conditions. | Not a list of roles, groups, or OAuth scopes. |
| `SubjectConfirmationData@NotOnOrAfter` | Independent deadline for the subject confirmation method, typically bearer SSO. | Not an optional copy of `Conditions` that can be skipped. |
| `AuthnStatement@AuthnInstant` | Time the IdP authenticated the user. | Does not alone determine whether the assertion is still valid. |
| `AuthnStatement@SessionNotOnOrAfter` | Authentication session limit advertised by the IdP if present, per SAML semantics. | Does not automatically set the TTL of an application session cookie. |

## 2. Interpreting `NotBefore` and `NotOnOrAfter`

Suppose the IdP issues:

~~~xml
<saml:Conditions
    xmlns:saml="urn:oasis:names:tc:SAML:2.0:assertion"
    NotBefore="2026-11-07T03:00:00Z"
    NotOnOrAfter="2026-11-07T03:05:00Z">
  <saml:AudienceRestriction>
    <saml:Audience>urn:example:sp:reports</saml:Audience>
  </saml:AudienceRestriction>
</saml:Conditions>
~~~

The validity interval is:

~~~text
2026-11-07T03:00:00Z <= check time
                       < 2026-11-07T03:05:00Z
~~~

That means **inclusive** of `NotBefore` and **exclusive** of `NotOnOrAfter`. Without clock-skew tolerance, at exactly `03:00:00Z` it is time-valid; at exactly `03:05:00Z` it has already expired. The current instant must come from a trusted clock and be compared in UTC/instants, never via date string comparisons or wrong timezones.

| SP check time (UTC) | Result considering `Conditions` timing only |
| --- | --- |
| `02:59:59Z` | Invalid: before `NotBefore`. |
| `03:00:00Z` | Valid at the start boundary. |
| `03:04:59Z` | Still within the window. |
| `03:05:00Z` | Invalid: reached `NotOnOrAfter`. |
| `03:10:00Z` | Invalid: past expiration. |

**If a boundary is omitted:** `NotBefore` and `NotOnOrAfter` are optional attributes in the `Conditions` schema; omitting one does not automatically synthesize a default boundary. However, the Web SSO profile, SP configuration, and security policies may mandate short time limits; never conclude “no boundary means the assertion lasts forever” because other constraints and profile rules still apply.

**`NotOnOrAfter` is an absolute timestamp**, not a TTL in minutes. Do not add 5 minutes to `IssueInstant` on your own if the IdP already supplied a concrete expiration timestamp. Never treat `IssueInstant` or `AuthnInstant` as a replacement for checking `Conditions`.

### 2.1. Clock Skew Tolerance

IdP and SP clocks can drift by a few seconds. A validator may allow a small, configurable skew window to avoid rejecting valid assertions due to unsynchronized clocks. Yet every second added to the boundary widens the acceptance window for an assertion.

Do all of the following together:

- Synchronize server clocks with NTP or a trusted time source; prioritize fixing drifted clocks over widening clock skew excessively.
- Pick a tolerance just large enough for your deployment environment and log drift incidents.
- Keep assertion/`SubjectConfirmationData` lifetimes short as appropriate for Web SSO; never turn them into long lifetimes to “stop login errors.”
- Remember that skew tolerance on **`Conditions`** must never skip **SubjectConfirmationData** checks and anti-replay controls.

A 60-second tolerance example is an **illustrative configuration choice**, not a mandatory SAML standard value or universal recommendation.

## 3. `AudienceRestriction`: Which SP Is the Assertion For?

An IdP may trust many SPs, yet an assertion used to log into the **reports SP** must not be accepted by the **HR SP**. `AudienceRestriction` constrains who is allowed to consume the assertion.

Each `<saml:Audience>` element typically holds an **SP/Relying Party entity ID**. That is the identifier declared in SAML configuration/metadata; an entity ID may look like a URL or URN, yet **need not be a reachable URL**. It is also **not synonymous** with the ACS callback URL.

Example:

~~~xml
<saml:AudienceRestriction
    xmlns:saml="urn:oasis:names:tc:SAML:2.0:assertion">
  <saml:Audience>urn:example:sp:reports</saml:Audience>
  <saml:Audience>urn:example:sp:reports-backup</saml:Audience>
</saml:AudienceRestriction>
~~~

If the current SP has entity ID `urn:example:sp:reports`, the condition above passes audience validation. SP `urn:example:sp:payroll` must reject it even if the assertion is unexpired and validly signed.

### 3.1. OR Within One Restriction, AND Across Restrictions

This is a frequently misread point in SAML Core, clarified by OASIS Errata 05:

- **Within one `AudienceRestriction`**, multiple `Audience` elements combine with **OR**: the SP only needs to match at least one audience in that restriction.
- **If there are multiple `AudienceRestriction` elements**, every restriction must be satisfied, combining with **AND**. The SP must appear in at least one audience inside **each** restriction.

Example **valid** for SP `reports`:

~~~xml
<saml:Conditions xmlns:saml="urn:oasis:names:tc:SAML:2.0:assertion">
  <saml:AudienceRestriction>
    <saml:Audience>urn:example:sp:reports</saml:Audience>
    <saml:Audience>urn:example:sp:archive</saml:Audience>
  </saml:AudienceRestriction>
  <saml:AudienceRestriction>
    <saml:Audience>urn:example:sp:reports</saml:Audience>
  </saml:AudienceRestriction>
</saml:Conditions>
~~~

Example **invalid** for SP `reports`:

~~~xml
<saml:Conditions xmlns:saml="urn:oasis:names:tc:SAML:2.0:assertion">
  <saml:AudienceRestriction>
    <saml:Audience>urn:example:sp:reports</saml:Audience>
  </saml:AudienceRestriction>
  <saml:AudienceRestriction>
    <saml:Audience>urn:example:sp:payroll</saml:Audience>
  </saml:AudienceRestriction>
</saml:Conditions>
~~~

The first restriction succeeds for `reports`, yet the second restriction fails to match: the overall result is **invalid**. Do not flatten all `Audience` elements from multiple restrictions into one list and check for a single match.

**In Web Browser SSO:** the SAML Web SSO profile requires an assertion intended for the requester to include an `AudienceRestriction` referencing the SP. If the required audience is missing, reject per profile/policy rules; never treat “unrestricted in Conditions” as sufficient for SSO.

### 3.2. Audience Does Not Replace Authorization

Audience tells **which application may receive the assertion**, not whether the user may view invoice #42. After SAML authentication, the API/application must still enforce role, tenant, ownership, and business permissions. Nor can you trust an audience value read from a user-submitted request; the SP must compare against the **configured trusted entity ID** of the active registration.

## 4. `SubjectConfirmationData` Imposes an Independent Limit

In bearer SAML Web SSO, the IdP normally includes subject confirmation data:

~~~xml
<saml:SubjectConfirmation
    xmlns:saml="urn:oasis:names:tc:SAML:2.0:assertion"
    Method="urn:oasis:names:tc:SAML:2.0:cm:bearer">
  <saml:SubjectConfirmationData
      InResponseTo="_req-456"
      Recipient="https://sp.example.org/login/saml2/sso/corporate"
      NotOnOrAfter="2026-11-07T03:04:00Z"/>
</saml:SubjectConfirmation>
~~~

These attributes have meanings distinct from `Conditions`:

- **`Recipient`**: valid assertion receiving endpoint / Assertion Consumer Service location. Compare with the expected ACS URL per configuration; this is a receiving URL, **not the entity ID in AudienceRestriction**.
- **`InResponseTo`**: correlates the response with the prior SP-generated `AuthnRequest`. In SP-initiated SSO, the SP must verify that the request ID is genuinely pending and bound to the initiating browser session.
- **`NotOnOrAfter` on SubjectConfirmationData**: deadline to use this bearer subject confirmation proof, **independent** of the `Conditions` deadline.
- **`Address`** (if present): an additional constraint in subject confirmation data; handle per profile/policy, and do not rely on IP alone as the sole anti-replay measure.

Suppose `Conditions@NotOnOrAfter` is `03:05Z`, while `SubjectConfirmationData@NotOnOrAfter` is `03:04Z`. At `03:04:30Z`, the assertion's time condition still passes, yet bearer confirmation **has expired**: login must be rejected. You cannot “pick the later expiration timestamp” to extend usability.

An assertion may have multiple `SubjectConfirmation` elements. The validator must find a subject confirmation path satisfying the **right profile/binding**, while simultaneously requiring all global assertion conditions to be valid. Do not arbitrarily pick one branch and skip issuer, signature, or audience checks.

## 5. Deadlines That Must Never Be Conflated

| Timestamp | What does it describe? | Check / consequence |
| --- | --- | --- |
| `Response@IssueInstant` | When the IdP created the response. | May serve as freshness evidence per profile/policy; does not replace assertion expiration. |
| `Assertion@IssueInstant` | When the assertion was created. | Does not automatically keep the assertion valid until “session end.” |
| `Conditions@NotBefore` | Too early to be permitted for use. | Reject if earlier than allowed by configured skew tolerance. |
| `Conditions@NotOnOrAfter` | End boundary of assertion validity. | Reject once expired. |
| `SubjectConfirmationData@NotOnOrAfter` | End boundary of bearer confirmation. | Reject if confirmation expired even when `Conditions` is still valid. |
| `AuthnStatement@AuthnInstant` | When the user authenticated at the IdP. | May be used for “recent login” requirements; does not replace `Conditions`. |
| `AuthnStatement@SessionNotOnOrAfter` | Related authentication session limit if present. | Handle per protocol/policy; does not auto-sync SP session cookie TTL. |
| SP's HTTP session cookie | Application session after successful SAML login. | Has its **own** idle/absolute timeout, logout, and lifecycle policies. |

For example, the SP sets a 30-minute session cookie after accepting an assertion, while the assertion itself is valid for **login exchange** for only a few minutes. The assertion expiring at `03:05Z` does not mean an already-issued application session must log out at `03:05Z` unless application policy specifies it. Conversely, an unexpired assertion **must not be infinitely reusable**; the callback must verify the transaction and prevent replay.

## 6. Recipient Verification Flow — Necessary Combined Conditions

A secure SAML SP implementation should use a **properly integrated SAML/OpenSAML library**, checking the exact data protected by XML signatures. A verification pipeline can be expressed conceptually as:

1. **Load trusted registration:** determine IdP and SP entity IDs from trusted configuration/metadata; never accept arbitrary entity IDs or signing certificates from the HTTP request.
2. **Verify response/binding:** parse XML safely, verify response/assertion signatures per profile ensuring the consumed assertion is covered by a verified signature; check issuer and `Destination`.
3. **Verify correlation:** for SP-initiated flows, `InResponseTo` must match a pending `AuthnRequest` belonging to that exact browser transaction/session. Verify `Recipient` of bearer confirmation.
4. **Verify Conditions:** enforce `NotBefore`, `NotOnOrAfter`, all `AudienceRestriction` elements, and additional conditions such as `OneTimeUse`/`ProxyRestriction` if present per supported rules. Any condition not understood or safely evaluable must not be silently ignored.
5. **Verify subject confirmation:** ensure a valid subject confirmation method matching the recipient, transaction, and confirmation validity window.
6. **Prevent replay:** consumed responses/assertions and transactions must not be accepted repeatedly; anti-replay caches must persist long enough for accepted validity windows and skew tolerance. Consume transactions safely against concurrent callbacks.
7. **Issue application session:** only after all conditions pass, create the Spring Security `Authentication` and SP session; enforce business authorization independently afterward.

The core point is that **constraints must be satisfied together**. Valid signature + valid audience + valid `Conditions` are **still insufficient** if bearer confirmation has expired or `InResponseTo` mismatches.

### 6.1. Examples of “Some Conditions Pass Yet Login Still Fails”

Assume:

- SP has `entityID = urn:example:sp:reports`, `ACS = https://sp.example.org/login/saml2/sso/corporate`.
- Assertion has `Conditions = [03:00Z, 03:05Z)`; `AudienceRestriction` contains the matching entity ID.
- Bearer `SubjectConfirmationData@NotOnOrAfter = 03:04Z`, `Recipient` is the ACS above.
- `InResponseTo = _req-456` belongs to a pending request in the right session.

| Scenario | Analysis | Result |
| --- | --- | --- |
| Received at `03:03Z`, all other checks valid. | Conditions, audience, and bearer confirmation are valid. | Acceptable after full verification of signature, issuer, replay, etc. |
| Received at `03:04:30Z`. | Conditions still valid, but bearer confirmation has expired. | **Reject.** |
| Received at `03:05Z`. | Reached `Conditions@NotOnOrAfter`. | **Reject** (without clock skew). |
| Received at `03:03Z`, audience only lists `urn:example:sp:payroll`. | Assertion intended for another SP. | **Reject.** |
| Received at `03:03Z`, `InResponseTo` does not match pending request. | Cannot bind callback to prior transaction. | **Reject.** |
| Resubmitting a previously consumed response. | Assertion or transaction replay. | **Reject.** |

## 7. Java 17: Demonstrating Time Boundaries and Audience Logic

The program below is a **learning model for two conditions**, not a real SAML validator. It does not check XML signatures, issuer, recipient, subject confirmation, clock skew, other condition types, or replay. In production, use a SAML validation library.

File `SamlConditionsDemo.java`:

~~~java
import java.time.Instant;
import java.util.List;

public class SamlConditionsDemo {
    static boolean validWindow(Instant now, Instant notBefore,
                               Instant notOnOrAfter) {
        return !now.isBefore(notBefore)
                && now.isBefore(notOnOrAfter);
    }

    static boolean audienceAllowed(
            String expectedEntityId, List<List<String>> restrictions) {
        // For this Web SSO demo: require at least one restriction.
        // OR within each list; AND across lists.
        return !restrictions.isEmpty()
                && restrictions.stream().allMatch(
                    audiences -> audiences.contains(expectedEntityId));
    }

    public static void main(String[] args) {
        Instant from = Instant.parse("2026-11-07T03:00:00Z");
        Instant until = Instant.parse("2026-11-07T03:05:00Z");
        String sp = "urn:example:sp:reports";

        System.out.println(validWindow(from, from, until));
        System.out.println(validWindow(until, from, until));

        System.out.println(audienceAllowed(sp, List.of(
                List.of(sp, "urn:example:sp:archive"))));

        System.out.println(audienceAllowed(sp, List.of(
                List.of(sp),
                List.of("urn:example:sp:payroll"))));
    }
}
~~~

Compile and run with Java 17 or newer:

~~~bash
javac SamlConditionsDemo.java
java SamlConditionsDemo
~~~

Exact output:

~~~text
true
false
true
false
~~~

The first two lines confirm the **[NotBefore, NotOnOrAfter)** interval. The next two lines confirm **OR within a restriction** and **AND across multiple restrictions** for audience. Real software must use a trusted SAML parser/validator and compare entity IDs from configured registrations.

## 8. Configuration in Spring Security SAML 2.0 Login

In Servlet-based Spring Boot with `spring-boot-starter-security` and `spring-security-saml2-service-provider` dependencies (plus repositories matching your project version), use SAML Login configuration and IdP metadata instead of parsing XML manually in controllers.

Example `SecurityFilterChain` configuration in a Spring Boot project:

~~~java
package example.security;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class SamlSecurityConfig {
    @Bean
    SecurityFilterChain filterChain(HttpSecurity http) throws Exception {
        http.authorizeHttpRequests(auth -> auth
                .requestMatchers("/public/**").permitAll()
                .anyRequest().authenticated())
            .saml2Login(Customizer.withDefaults());
        return http.build();
    }
}
~~~

This is project configuration code; it **does not compile standalone** with plain `javac`. Beyond the code above, you must have a valid `RelyingPartyRegistration`: SP entity ID, ACS, IdP entity ID/metadata, signature verification certificates, algorithms/bindings, and key configuration as needed. Configuring the wrong entity ID causes valid audiences to be rejected; “fixing” it by disabling `AudienceRestriction` validation breaks the trust boundary.

Spring Security uses OpenSAML to validate SAML responses and assertions, with validators for signature, issuer/destination, `Conditions`, audience, and subject confirmation depending on the configured version/provider. Components such as `OpenSaml4AuthenticationProvider`, `OpenSaml5AuthenticationProvider`, and validator customization APIs differ across releases; **consult the docs for the exact Spring Security version your project runs**.

When clock-skew tolerance or additional condition checks are needed, configure them at the supported validator layer and **retain the default validators**. Never replace the entire validator with a function that only checks timestamps or only checks signatures. Never use “XML parsed cleanly” as proof an assertion is authenticated.

### 8.1. Safely Debugging Rejected SAML Logins

If users report “SAML token expired” or “invalid audience,” inspect in a systematic order:

1. Compare UTC times on IdP and SP, `NotBefore`, and `NotOnOrAfter` on **Conditions** and **SubjectConfirmationData**; inspect configured clock-skew tolerance.
2. Check the **expected SP entity ID in `RelyingPartyRegistration`** against every `AudienceRestriction`, rather than comparing against the browser address bar URL.
3. Check ACS/`Recipient`/`Destination` across HTTPS, reverse proxies, and public base URLs; this is separate from audience.
4. Check `InResponseTo`, pending transactions, session cookies, and replay, especially during cross-site IdP → SP POSTs.
5. Check issuer, metadata, and signing certificates for the right IdP; avoid switching metadata/trust keys based on user-supplied values.
6. Log **error category, timestamp, registration ID, and sanitized transaction ID**. Avoid placing full assertions, NameIDs, personal attributes, cookies, or sensitive XML into logs/tickets.

## 9. Common Confusions to Avoid

| Confusion | Correct understanding |
| --- | --- |
| “Valid signature means the assertion works forever.” | Signature proves integrity/signing origin; time, audience, subject confirmation, and replay still must be checked. |
| “`NotOnOrAfter` includes the exact end second.” | The validity interval has an **exclusive** upper bound, prior to applying controlled clock skew. |
| “`IssueInstant` = expiration deadline.” | That is issuance time, not a replacement for `ConditionsNotOnOrAfter`. |
| “One matching `Audience` in any `AudienceRestriction` is enough.” | Every restriction must be satisfied independently: **AND across restrictions**, **OR within a restriction**. |
| “Audience is the ACS URL.” | Audience is usually the **SP entity ID**; ACS is the response receiving/`Recipient` URL. |
| “`Conditions` is still valid so `SubjectConfirmationData` can be ignored.” | Bearer confirmation has its own deadline and independent recipient/transaction requirements. |
| “Assertion expiration means the session cookie must be deleted immediately.” | Application session TTL is managed separately by the SP; design session/logout per policy. |
| “An expired assertion can be accepted by setting a huge clock skew.” | Synchronize clocks and use small, bounded skew; never widen skew to mask config bugs. |
| “IdP-initiated and SP-initiated share the same `InResponseTo`.” | IdP-initiated normally has no original request; require dedicated policy rather than an ad-hoc fallback. |
| “Spring Security automatically decides permissions on all resources.” | SAML login provides identity; business/tenant authorization must still be implemented. |

## 10. Knowledge Self-Check

1. An Assertion has `NotBefore=03:00Z` and `NotOnOrAfter=03:05Z`. Is it valid at `03:05:00Z`? **No**, before accounting for clock skew.
2. An Assertion has an `AudienceRestriction` containing `reports` and `archive`, and the SP is `reports`. Does it pass the audience check? **Yes**, if other conditions are valid.
3. An Assertion has **two** `AudienceRestriction` elements: the first contains `reports`, the second contains only `payroll`. Does SP `reports` pass? **No**, because the second restriction fails.
4. `Conditions` is valid until `03:05Z`, while bearer confirmation expires at `03:04Z`. Can it be used at `03:04:30Z`? **No**, because bearer confirmation has expired.
5. Audience, signature, and validity window are all valid, yet `InResponseTo` belongs to another session. Does SP-initiated login accept it? **No**, because it does not belong to the original pending request transaction.
6. Once SAML login succeeds, can the application skip record-level permission checks? **No**, authentication and authorization are two separate steps.

## References

- [OASIS SAML V2.0 Core — Assertions and Protocols](https://docs.oasis-open.org/security/saml/v2.0/saml-core-2.0-os.pdf)
- [OASIS SAML V2.0 Errata 05 — AudienceRestriction AND/OR](https://docs.oasis-open.org/security/saml/v2.0/errata05/os/saml-v2.0-errata05-os.html)
- [Spring Security — SAML 2.0 Login Overview](https://docs.spring.io/spring-security/reference/servlet/saml2/login/overview.html)
- [Spring Security — Authenticating SAML 2.0 Responses](https://docs.spring.io/spring-security/reference/servlet/saml2/login/authentication.html)
- [Spring Security — Producing SAML 2.0 Authentication Requests](https://docs.spring.io/spring-security/reference/servlet/saml2/login/authentication-requests.html)
