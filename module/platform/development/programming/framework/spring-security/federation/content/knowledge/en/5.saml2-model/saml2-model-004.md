# AuthnStatement, AuthnContext, and Authentication Instant in SAML 2.0

**AuthnStatement** is the component of a SAML 2.0 Assertion describing *an identity authentication event*: **when** the Identity Provider (IdP) authenticated the subject and under what **authentication context**. The two core pieces of data are **AuthnInstant** (the actual authentication timestamp) and **AuthnContext** (the authentication context/method asserted by the IdP).

In **Spring Security – federation**, the application acts as a **Service Provider/Relying Party (SP/RP)**. The SP verifies the SAML Response/Assertion from the IdP and can use `AuthnStatement` to understand how recent the authentication event is, require an appropriate authentication method, and design sensitive operations requiring re-authentication. A valid `AuthnStatement` **does not automatically mean** all access permissions are granted, how long an application session must live, or that the user just typed a password at the moment the Response arrived.

## 1. Where Does AuthnStatement Sit in the SAML 2.0 Model?

Typical Web Browser SSO flow:

~~~text
User        --->  Spring Security SP/RP
                       |
                       | 1. SAML AuthnRequest
                       v
                  IdP authenticates
                       |
                       | 2. SAML Response containing Assertion
                       v
               SP verifies Response/Assertion
                       |
                       | 3. Read trusted authentication info
                       v
               Principal + app session + authorization
~~~

A SAML 2.0 Assertion can contain different kinds of statements:

- **AuthnStatement:** when the identity was authenticated and in what context.
- **AttributeStatement:** information about the subject such as email, department, groups; does **not** replace `AuthnStatement`.
- **AuthzDecisionStatement:** a statement about an authorization decision in a specific context; the application remains responsible for enforcing its own active policies.

In Web Browser SSO, the SP typically receives the SAML Response at its **Assertion Consumer Service (ACS)**, checks the issuer, signature, audience, recipient, validity window, and request correlation constraints. Only **after verifying the assertion's validity and trust context** may the application rely on fields inside `AuthnStatement` to make decisions.

**Distinction:** SAML Response and Assertion are outer envelopes; `AuthnStatement` is a section inside the Assertion. Multiple `AuthnStatement` elements may exist depending on content/protocol, so if business logic depends on freshness or authentication method, it must explicitly specify which statement is accepted per policy.

## 2. Structure of AuthnStatement

An XML snippet illustrating **only the AuthnStatement component**:

~~~xml
<saml:AuthnStatement
    xmlns:saml="urn:oasis:names:tc:SAML:2.0:assertion"
    AuthnInstant="2026-11-07T08:00:00Z"
    SessionIndex="_idp-session-123"
    SessionNotOnOrAfter="2026-11-07T16:00:00Z">

    <saml:AuthnContext>
        <saml:AuthnContextClassRef>
            urn:oasis:names:tc:SAML:2.0:ac:classes:PasswordProtectedTransport
        </saml:AuthnContextClassRef>
    </saml:AuthnContext>
</saml:AuthnStatement>
~~~

This is a **structural illustration snippet**, not a complete SAML Assertion/Response and unsigned. Do not use this XML snippet as real login evidence. The URI value inside `AuthnContextClassRef` must follow the exact representation supported by the IdP; the XML in the example is wrapped onto new lines for readability.

According to **SAML 2.0 Core**, the component has these main parts:

| Element/Attribute | Required? | Meaning |
| --- | --- | --- |
| **AuthnInstant** | Yes | Timestamp when the authentication event occurred, in XML Schema dateTime format, UTC-encoded in SAML |
| **AuthnContext** | Yes | Context details the IdP used to authenticate the subject |
| **SessionIndex** | No | Identifier/index for a session between subject and authentication authority; often useful for session references such as Single Logout |
| **SessionNotOnOrAfter** | No | Time at which the session between subject and SAML authority must be considered ended |
| **SubjectLocality** | No | Information such as IP address or DNS name of the device where the authentication event supposedly occurred; should not be blindly treated as a trusted geolocation source |

Inside **AuthnContext**, the standard supports elements such as **AuthnContextClassRef**, **AuthnContextDecl**, **AuthnContextDeclRef**, and **AuthenticatingAuthority** per schema structure. Context can be represented by a class reference, a detailed declaration, a declaration reference, or a valid combination thereof. Not every IdP emits all optional parts.

### Key Fields to Remember

- **AuthnInstant** is an attribute of **AuthnStatement** itself, not the browser's current time.
- **SessionIndex** is an identifier in the IdP/SAML authority's context. Do not use it directly in place of Spring's `HttpSession` ID.
- **SessionNotOnOrAfter** refers to the **session with the SAML authority**; it has no mandatory relationship with the assertion's **Conditions.NotOnOrAfter**.
- **AuthnContext** describes *how the authentication occurred*; it does not implicitly contain all of the user's business permissions.

## 3. Exactly What Timestamp Is AuthnInstant?

**AuthnInstant** is required on every `AuthnStatement` and represents **the time authentication occurred at the identity provider**. This is a critical attribute when an application needs to know whether authentication is fresh enough for a sensitive action.

Example UTC timeline:

| Timestamp | Event | Attribute/object |
| --- | --- | --- |
| 08:00:00Z | User logs into the IdP; IdP authenticates successfully | **AuthnInstant = 08:00:00Z** |
| 09:10:00Z | User opens Portal; IdP reuses the existing SSO session and issues a new SAML assertion | **Assertion.IssueInstant = 09:10:00Z** |
| 09:15:00Z | Assertion validity expires per Conditions | **Conditions.NotOnOrAfter = 09:15:00Z** |
| 16:00:00Z | Session between subject and IdP must be considered ended per statement | **SessionNotOnOrAfter = 16:00:00Z** |

**Consequence:** at **09:12Z**, the assertion may still be within its validity window and accepted by the SP for login, yet **the original authentication event happened 72 minutes earlier**. If approving a wire transfer requires the user to have authenticated within the **last 10 minutes**, using **IssueInstant = 09:10** to conclude “only 2 minutes ago” is **wrong**. You must inspect **AuthnInstant = 08:00**, apply the freshness policy, and require re-authentication if needed.

An IdP can genuinely re-authenticate and issue a new statement with a new `AuthnInstant`. However, issuing a **new Response**, renewing the **SP session**, or **redirecting the browser through the IdP** does not prove the IdP performed a fresh authentication event.

## 4. Distinguishing Every Timestamp Commonly Seen in SAML

| Field/concept | Belongs to | Answers the question |
| --- | --- | --- |
| **Response.IssueInstant** | SAML Response | When was this Response issued? |
| **Assertion.IssueInstant** | SAML Assertion | When was this Assertion issued? |
| **AuthnStatement.AuthnInstant** | Authentication statement | When did the IdP authenticate the user? |
| **Conditions.NotBefore** | Assertion conditions | Before when must the Assertion not be used? |
| **Conditions.NotOnOrAfter** | Assertion conditions | At or after when must the Assertion be treated as expired? |
| **SubjectConfirmationData.NotOnOrAfter** | Subject confirmation | After what time must the subject confirmation evidence be rejected in that confirmation context? |
| **AuthnStatement.SessionNotOnOrAfter** | Subject–SAML authority session | At the latest, when does the SAML authority session end? |
| **Spring application session timeout** | Web session at SP | When does the SP-managed application session expire? |

These timestamps are **not interchangeable**:

1. **A still-valid assertion** does not mean **the authentication event is fresh enough** for step-up.
2. **A fresh AuthnInstant** does not mean **the assertion is valid** if signature, audience, recipient, or assertion validity timestamps fail.
3. **The IdP's SessionNotOnOrAfter** is not an automatic directive setting the `HttpSession` timeout of a Spring application.
4. **SessionIndex** can support session referencing when Single Logout is properly implemented, but does not mean logging out at the IdP automatically terminates every SP session immediately.

SAML expresses timestamps in UTC; for example, **Z** denotes UTC. When parsing or comparing in Java, prefer **Instant** rather than a timezone-less `LocalDateTime`. Allow **clock skew** in checks as governed by your library and security policy; never remove all time checks just because servers may drift.

## 5. What Does AuthnContext Tell Us?

**AuthnContext** describes the **context, method, or assurance level of the authentication event** as asserted by the IdP. A common sub-element is **AuthnContextClassRef**, holding a URI referencing an authentication context class.

Examples of standard SAML URIs:

- **urn:oasis:names:tc:SAML:2.0:ac:classes:PasswordProtectedTransport**: password authentication over a protected transport channel.
- **urn:oasis:names:tc:SAML:2.0:ac:classes:Password**: password authentication context class.
- **urn:oasis:names:tc:SAML:2.0:ac:classes:TimeSyncToken**: context class based on a time-synchronized token.
- **urn:oasis:names:tc:SAML:2.0:ac:classes:SmartcardPKI**: context class using a smart card and PKI.
- **urn:oasis:names:tc:SAML:2.0:ac:classes:PreviousSession**: context class relating to relying on a previous authentication session.

**Do not infer mechanically:** the **PasswordProtectedTransport** URI does not assert the user completed MFA. The **TimeSyncToken** URI does not by itself prove an application satisfies a specific NIST AAL level. Nor should you arbitrarily rank all class URIs on a weak-to-strong scale unless the IdP and SP have agreed on their meanings.

An IdP may use **custom URIs** to represent MFA policies, passkeys, phishing-resistant authentication, or assurance levels. The SP should rely on such a URI only when backed by a trust contract with the IdP: what the URI means, what actual mechanism backs it, when it may change, and whether re-authentication is enforced.

### AuthnContextClassRef, DeclRef, and AuthenticatingAuthority

- **AuthnContextClassRef:** URI identifying the authentication context *class*. This is the concise and common representation.
- **AuthnContextDecl / AuthnContextDeclRef:** detailed declaration or URI referencing a declaration of the authentication context; expresses policies and technical procedures deeper than a class name.
- **AuthenticatingAuthority:** can indicate one or more authorities involved in authentication; useful in multi-hop authentication delegation, though the authority name itself does not replace trust verification.

What the SP must do is **compare the reported context against application policy**, never treating all `AuthnContext` values as equivalent.

## 6. RequestedAuthnContext and ForceAuthn: Request First, Verify Afterward

There is a difference between what the application **asks the IdP to do** and what the assertion **actually reports the IdP did**.

### RequestedAuthnContext

In a SAML **AuthnRequest**, the SP can send **RequestedAuthnContext** to request one or more authentication context classes/declarations. The **Comparison** attribute has these values in SAML 2.0:

| Comparison | Protocol-level meaning |
| --- | --- |
| **exact** | The result must match at least one requested context exactly; this is the default |
| **minimum** | Context evaluated by the IdP as at least as strong as one of the requested ones |
| **better** | Context evaluated by the IdP as stronger than the requested ones by its rules |
| **maximum** | Strongest context evaluated by the IdP without exceeding the requested limit |

What “stronger” means in comparisons is not lexicographical URI sorting; it relies on the responder's semantics/comparison model. Therefore in real integrations, **exact** with an agreed-upon context is usually easier to test; some IdPs also support only a subset of comparison operators.

XML snippet illustrating a context request inside `AuthnRequest`:

~~~xml
<samlp:RequestedAuthnContext
    xmlns:samlp="urn:oasis:names:tc:SAML:2.0:protocol"
    xmlns:saml="urn:oasis:names:tc:SAML:2.0:assertion"
    Comparison="exact">
    <saml:AuthnContextClassRef>
        urn:oasis:names:tc:SAML:2.0:ac:classes:SmartcardPKI
    </saml:AuthnContextClassRef>
</samlp:RequestedAuthnContext>
~~~

This is only an **illustrative sub-snippet**, not a complete `AuthnRequest`. The class reference parameter is meaningful only if the IdP actually supports that context class and both organizations agree on its interpretation.

### ForceAuthn

An **AuthnRequest** with **ForceAuthn="true"** asks the IdP to **authenticate the user directly** rather than relying solely on a previous security context; the default when omitted is **false**. This helps require fresh authentication when a user performs a high-risk operation.

**ForceAuthn does not automatically require MFA.** Requiring MFA or a specific assurance level requires matching IdP policy and requested context; the SP must still verify `AuthnContext` and `AuthnInstant` in the verified assertion. Some IdPs have implementation limitations, so test interoperability rather than assuming every request attribute is supported identically.

**If the IdP cannot satisfy the requested context**, the protocol defines errors such as **NoAuthnContext**. The SP must handle failures/unmet requirements explicitly, never silently downgrading requirements to let a sensitive transaction proceed.

## 7. When Should Authentication Freshness Be Checked?

An application might accept ordinary SSO for viewing a dashboard, yet require **recent authentication** for sensitive actions:

- Changing recovery email, password, or MFA settings.
- Approving a money transfer, exporting sensitive data, or granting admin roles.
- Executing legal actions, signing orders, or changing security policies.
- Enabling a short-lived privileged admin session.

Example policy:

> “To approve a payment, the most recent authentication event must be within **10 minutes**, and the `AuthnContext` must belong to the enterprise-approved list of strong authentication contexts.”

The system must check **simultaneously**:

1. The Response/Assertion has passed full verification: trusted IdP, valid signature, right audience, recipient, `InResponseTo` when applicable, valid time window, and no replay.
2. Current **AuthnInstant** is recent enough against the server clock and allowed skew.
3. **AuthnContext** reflects the agreed-upon authentication policy/quality, not merely any URI name.
4. The account holds business permission to perform the transaction, not just a successful login.
5. If unmet, redirect to a **step-up / fresh authentication** flow and re-verify the result before allowing the action.

**Risk:** reading `AuthnInstant` from XML before verifying signatures and SAML conditions lets an attacker forge a recent timestamp or a “strong” `AuthnContext`. This data is meaningful only once it belongs to a **validly verified assertion**.

## 8. Java 17 Example: Checking Elapsed Time from AuthnInstant

The following example is **standalone, compiles, and runs on Java 17+**. It illustrates computing the age of an IdP-verified authentication event; it is **not a SAML signature verification library**.

Create file **AuthnFreshnessDemo.java**:

~~~java
import java.time.Duration;
import java.time.Instant;

public class AuthnFreshnessDemo {

    public static void main(String[] args) {
        Instant authnInstant =
                Instant.parse("2026-11-07T08:00:00Z");
        Instant now =
                Instant.parse("2026-11-07T09:12:00Z");

        Duration age = Duration.between(authnInstant, now);
        Duration maxAge = Duration.ofMinutes(10);

        boolean freshEnough =
                !age.isNegative()
                && age.compareTo(maxAge) <= 0;

        System.out.println("Authn age (minutes): " + age.toMinutes());
        System.out.println("Fresh enough: " + freshEnough);
    }
}
~~~

Compile and run:

~~~bash
javac AuthnFreshnessDemo.java
java AuthnFreshnessDemo
~~~

**Exact** stdout:

~~~text
Authn age (minutes): 72
Fresh enough: false
~~~

Explanation:

- `09:12Z` minus `08:00Z` equals **72 minutes**.
- With a 10-minute maximum policy, **freshEnough = false**.
- The example uses fixed timestamps for reproducible output. In a real system, obtain **AuthnInstant from the SP-verified assertion**, get server time from a trusted **Clock**, and add bounded clock-skew tolerance rules.
- Do not use this calculation as a substitute for checking **Conditions.NotOnOrAfter**, **SubjectConfirmationData**, **signatures**, **audience**, **AuthnContext**, or application authorization.
- If `AuthnInstant` is in the “future” due to clock skew, the example intentionally returns **false** by disallowing negative age. Real systems need careful clock-skew policies without dropping freshness checks.

**Think it through:** If the IdP issues a new assertion at `09:11Z` without re-authenticating and keeps `AuthnInstant = 08:00Z`, stdout is **still 72 minutes**. If the IdP truly re-authenticates at `09:11Z`, the new `AuthnInstant` may be `09:11Z` and age drops to 1 minute, yet action permission still depends on `AuthnContext` and authorization.

## 9. How Does Spring Security Use AuthnStatement?

With Spring Security on servlet-based Spring Boot, the **SAML 2.0 Login** module receives SAML Responses at the ACS endpoint and processes them via an OpenSAML-based provider. After login succeeds, the application has an **Authentication**, a **principal**, and can establish a corresponding Spring Security session.

A simple login configuration for **Spring Boot 3 / Spring Security 6** (requires Spring Web, Spring Security, and **spring-security-saml2-service-provider** dependencies, plus a valid **RelyingPartyRegistration** with the IdP):

File **src/main/java/com/example/security/SamlSecurityConfig.java**:

~~~java
package com.example.security;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class SamlSecurityConfig {

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http)
            throws Exception {
        return http
            .authorizeHttpRequests(authorize -> authorize
                .requestMatchers("/public").permitAll()
                .anyRequest().authenticated())
            .saml2Login(Customizer.withDefaults())
            .build();
    }
}
~~~

This is a **configuration class belonging to a Spring Boot project**, not a standalone program runnable with plain **javac/java**; it has no fixed stdout. In addition to the code above, you must configure the IdP issuer/entity ID, metadata/signing certificates, ACS, and SP identity properly. Spring Security SAML Login manages many Web SSO protocol verification steps automatically, but **that does not mean the application automatically enforces a “re-authenticate within 10 minutes with MFA” policy**.

### When the Application Needs AuthnInstant or AuthnContext

1. **First step:** complete SAML Response/Assertion verification using the appropriate Spring Security/OpenSAML components; never use XML directly from the request as a trusted source.
2. **Second step:** from the verified SAML Response, access **AuthnStatement** and **AuthnContext** through the OpenSAML API/converter/provider extension matching **your active Spring Security version**. Do not assume these fields are pre-mapped into principal attributes or default `GrantedAuthority` instances.
3. **Third step:** interpret `AuthnContextClassRef` per the contract agreed with the IdP; check `AuthnInstant` against freshness policy, accounting for multiple statements or missing data.
4. **Fourth step:** store the **vetted** result in the session/application state needed for step-up policies, with an expiration and a mechanism to update upon re-authentication.
5. **Fifth step:** enforce business authorization in controller/service/method security; if authentication info is stale or too weak, trigger a supported flow to request fresh authentication from the IdP.

**Version note:** OpenSAML provider, converter, and assertion accessor APIs can change across Spring Security releases. Check the API docs of your actual version when writing `AuthnStatement` extraction code. Avoid writing manual XML parsers to read from an **unverified HTTP SAMLResponse**, and especially avoid disabling signature, audience, or subject confirmation checks.

### Do Not Misunderstand Spring Security Sessions

- The SP's **HttpSession/SecurityContext** follows the application's configured lifecycle.
- **SessionIndex/SessionNotOnOrAfter** describe the IdP session in the SAML protocol.
- **AuthnInstant** describes the **authentication event**, not when a new `HttpSession` was created.
- **AuthnContextClassRef** does not automatically turn into **ROLE_ADMIN** in Spring Security.
- When implementing **Single Logout**, design the IdP/SP interaction and `SessionIndex` per protocol; do not assume logging out on one side always terminates every session on the other side instantly.

## 10. Business Scenario: Viewing a Dashboard vs. Approving a Payment

**Context:** An employee logs into the IdP at `08:00Z` using a password. At `09:10Z`, they open the Portal via SSO; the IdP issues a new assertion with **AuthnInstant 08:00Z** and **AuthnContext PasswordProtectedTransport**.

**Action A — viewing the dashboard at 09:12Z:** Permitted if the SAML assertion passed verification, the SP session is valid, and the user has view permissions. The dashboard policy does not require an authentication event within the last 10 minutes.

**Action B — approving a payment at 09:12Z:** Policy requires authentication within 10 minutes and a context rated by the enterprise as suitable MFA. `AuthnInstant 08:00Z` is too old, and `PasswordProtectedTransport` does not prove MFA. The Portal must **temporarily deny the action** and initiate the agreed **step-up/fresh authentication** mechanism.

**After step-up:** The IdP completes fresh authentication and returns a valid assertion with `AuthnInstant` around `09:13Z` and an allowed `AuthnContext`. The Portal re-verifies the response, time policy, and context; only then does it check the employee's permission to approve that specific order.

**If the IdP only issues a new assertion with an unchanged AuthnInstant:** The Portal must still deny Action B under its freshness policy. Never assume an SSO redirect equals MFA or re-authentication.

## 11. Common Mistakes and How to Fix Them

| Mistake | Consequence | Fix |
| --- | --- | --- |
| Using **IssueInstant** instead of **AuthnInstant** | Falsely concludes the user just authenticated | Compute freshness from `AuthnStatement.AuthnInstant` |
| Treating **Conditions.NotOnOrAfter** as IdP session end | Conflates assertion lifetime with session lifecycle | Inspect `SessionNotOnOrAfter` and SP session policy properly |
| Treating **SessionNotOnOrAfter** as auto-expiring `HttpSession` | Leads to broken logout/session design | Manage SP sessions independently; handle SAML logout per configuration |
| Equating **PasswordProtectedTransport** with MFA | Lets high-assurance actions pass without MFA | Agree on context mapping with IdP and test actual policies |
| Sending **ForceAuthn=true** without inspecting the returned assertion | Integration fails to catch non-compliant responses | Verify signed/verified `AuthnInstant` and `AuthnContext` on response |
| Reading `AuthnStatement` from unverified XML | Vulnerable to forged timestamps or authentication classes | Use data only after full SAML verification |
| Ignoring clock skew or using `LocalDateTime` with wrong timezone | False rejections or false freshness acceptance | Use `Instant`/UTC and bounded clock skew |
| Treating **SessionIndex** as a fixed user ID | Broken linking logic and cross-session leaks | Use verified subject identifiers per policy; never use `SessionIndex` as user ID |
| Granting admin roles based on `AuthnContext` | Confuses strong authentication with business authorization | Combine role/permission checks and specific object authorization |
| Assertion has multiple `AuthnStatement` elements and code blindly picks the first | May apply the wrong freshness or context | Define statement selection rules and reject ambiguity for high assurance |

## 12. Self-Check Questions

**Question 1:** A SAML Assertion is issued at 11:00, while `AuthnInstant` is 09:00. Which timestamp reflects when the user authenticated?  
**Answer:** **09:00**. `IssueInstant` 11:00 is when the assertion was issued, not a new authentication event at 11:00.

**Question 2:** An Assertion has `Conditions.NotOnOrAfter` at 11:05. Is that enough to confirm the user authenticated within 5 minutes prior to 11:04?  
**Answer:** **No**. `Conditions` defines the assertion's validity window, whereas authentication freshness relies on `AuthnInstant`.

**Question 3:** `AuthnContextClassRef` is `PasswordProtectedTransport`. Can we conclude the user completed MFA?  
**Answer:** **No**. That URI alone does not prove two-factor authentication; an assurance/mapping contract with the IdP is required.

**Question 4:** Is `SessionIndex` the ID of the Spring `HttpSession`?  
**Answer:** **No**. It belongs to the IdP/SAML authority session and can support SAML logout mechanisms when implemented.

**Question 5:** Does sending `ForceAuthn=true` guarantee the IdP performed fresh authentication and met the business-requested context?  
**Answer:** It is a **SAML protocol request**, but the SP must still check the verified response, `AuthnInstant`, `AuthnContext`, and actual IdP compliance.

**Question 6:** If `AuthnInstant` is fresh enough, can SAML signature verification or transaction approval permissions be skipped?  
**Answer:** **No**. Freshness is an additional condition, not a replacement for assertion verification or authorization.

## 13. Deployment Checklist

- [ ] Clearly identify the IdP and SP; configure trusted issuer/entity ID, metadata, ACS, certificates, and signatures.
- [ ] Let Spring Security/OpenSAML verify the SAML Response/Assertion **before** trusting `AuthnStatement`.
- [ ] Understand that **AuthnInstant**, **IssueInstant**, **Conditions.NotOnOrAfter**, **SubjectConfirmationData.NotOnOrAfter**, and **SessionNotOnOrAfter** are distinct timestamps.
- [ ] Freshness policy uses `AuthnInstant` in UTC/`Instant` with bounded clock-skew tolerance, never timezone-less local time.
- [ ] Map `AuthnContext` from the IdP to approved authentication policies; never infer MFA from an arbitrary URI.
- [ ] When re-authentication is needed, send the appropriate SAML request (`ForceAuthn` and/or `RequestedAuthnContext` supported by the IdP), then verify the actual result.
- [ ] Never equate `SessionIndex` with a user ID or Spring `HttpSession` ID.
- [ ] Define clear rules for multiple `AuthnStatement` elements, missing optional fields, or results failing policy.
- [ ] Protect sensitive data; do not log full assertions that may contain personal info and session traces.
- [ ] Role, tenant, and business-resource authorization must still be checked independently.

## 14. Key Takeaway

**AuthnStatement answers “when and in what context was the user authenticated?”, not the entirety of “what is the user allowed to do?”.** The **AuthnInstant** field records the actual authentication event, while **AuthnContext** describes the authentication context asserted by the IdP. **IssueInstant** and assertion/session lifetimes are separate facts. In Spring Security, verify SAML first, then evaluate authentication freshness and context with a dedicated policy when business logic requires it; finally, always enforce access permissions.

### Official Documentation

- **OASIS SAML 2.0 Core** — section 2.7.2 Authentication Statement and section 3.4 Authentication Request Protocol: https://docs.oasis-open.org/security/saml/v2.0/saml-core-2.0-os.pdf
- **OASIS SAML 2.0 Authentication Context** — definitions of authentication context classes/contexts: https://docs.oasis-open.org/security/saml/v2.0/saml-authn-context-2.0-os.pdf
- **Spring Security — SAML 2.0 Login Overview**: https://docs.spring.io/spring-security/reference/servlet/saml2/login/overview.html
- **Spring Security — Authenticating SAML Responses**: https://docs.spring.io/spring-security/reference/servlet/saml2/login/authentication.html
