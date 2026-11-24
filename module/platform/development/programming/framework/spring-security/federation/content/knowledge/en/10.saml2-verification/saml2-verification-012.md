# Rejecting Invalid SAML2 Messages Without Leaking Assertions or Keys

> **Topic:** Spring Security – federation · **Track:** SAML2 Verification. This lesson covers how to **safely reject** invalid SAML Responses/Assertions and protocol requests in a Java/Spring Security application acting as a Service Provider (SP): complete verification, non-disclosing error handling, separating user-facing messages from security logs, avoiding raw SAML capture in logs/APM/WAF, protecting signing/decryption keys, and testing failure paths across layers. Integration examples focus on Spring Boot 3.x / Spring Security 6.x Servlet; standalone Java runs on JDK 17+.

## 1. Objectives and Core Principles

After this lesson, you will be able to:

1. Describe **the exact points where the SP must reject** a SAMLResponse failing signature, trust source, audience, recipient, time conditions, state/correlation, or anti-replay checks.
2. Separate **SAML authentication** from **error display/notification**: a rejected message must not mint a new `Authentication`, while the browser response stays a generic message.
3. Configure `saml2Login(...).failureHandler(...)` to respond to authentication errors **without placing exception messages, SAMLResponse, assertions, or keys** into the response.
4. Design safe audit events: use **allowlisted reason codes**, generated/controlled correlation IDs, and verified metadata; never log raw XML/Base64/cookies/RelayState or principal PII.
5. Recognize that the failure handler **does not cover everything**—errors before the filter, proxy/parser/size-limit errors, or startup errors—and apply defense in depth.
6. Write negative tests proving both properties: **the request is rejected** and **no data leaks through responses, logs, traces, or metrics**.

### Short Answer to the Problem

**Not:** "SAML invalid → throw exception with XML and certificate for easy debugging."

**Instead:** "SAML invalid → stop authentication/fail closed → client gets a generic error with no sensitive data → internal audit records only minimal code and correlation ID → protect raw payloads/keys across the entire HTTP/exception/logging/telemetry pipeline."

Data protection must not blind operations: support teams still need to distinguish metadata, clock skew, correlation, and signature failures **on controlled internal channels**. Just never by handing raw assertions, private keys, or stack traces to the browser.

## 2. Trust Model When the SP Receives SAMLResponse

### 2.1. Entry Point and Data Boundaries

A Spring Security app performs SAML 2.0 Web Browser SSO along a common flow:

```text
Browser                 SP / Spring Security                     IdP
   |                             |                                |
   | GET /saml2/authenticate/corp|                                |
   |---------------------------->|                                |
   |    create AuthnRequest, save ID/state                        |
   |<----------------------------| redirect/form to IdP           |
   |                              \------------------------------>|
   |                              IdP authenticates user, signs Assertion
   |<-------------------------------------------------------------|
   | POST /login/saml2/sso/corp (SAMLResponse)                    |
   |---------------------------->|                                |
   |   Saml2WebSsoAuthenticationFilter                             |
   |     -> AuthenticationConverter resolves registration/context |
   |     -> OpenSAML provider parses/decrypts/verifies            |
   |     -> issuer/signature/destination/audience/time/state      |
   |     -> decide Authentication success/failure                 |
   |     -> on failure: generic response + safe audit only        |
   |<----------------------------|                                |
```

`SAMLResponse` is **transported by the browser**, so the POST body arriving at the ACS is **untrusted data** until verified by the provider. An attacker can freely POST to the ACS, altering `SAMLResponse`, `RelayState`, or path/headers. Merely having Base64 content or parseable XML in `SAMLResponse` does not mean it came from a trusted IdP.

Distinguish data at three layers:

| Layer | Immediately trustworthy? | What to do |
| --- | --- | --- |
| HTTP body/query, Base64 `SAMLResponse`, `RelayState`, client headers | **No** | Enforce size limits, do not log, validate format in the right component |
| Decoded/parsed XML Response/Assertion prior to validation | **No** | Use standard provider/validator; never extract claims for permissions or log "user X" in audit |
| `Saml2Authentication`/principal after successful validation | Usable within configured trust scope | Still map tenant/roles and enforce business authorization |

**Base64 is not encryption.** A SAML Response can hold `NameID`, email, groups, personal attributes, subject confirmation, and data reusable within a short window. If the body is logged, having only a Base64 string **neither** protects privacy nor eliminates replay risk.

### 2.2. Which Keys Are Sensitive?

SAML involves **multiple key roles**:

- **IdP private signing key**: used by the IdP to sign Responses/Assertions; never present in SP config.
- **IdP public verification certificate**: held by the SP as a trust anchor to verify IdP signatures; this certificate may be **published in the IdP's public metadata**, as it is not itself a private key. Still, there is no need to disclose/echo certificates and internal trust paths in login errors.
- **SP private signing key**: SP signs `AuthnRequest`, when configured to sign.
- **SP private decryption key**: SP decrypts `EncryptedAssertion`/`EncryptedAttribute`, when the protocol uses encryption.
- **SP public signing/decryption certificates**: may be published per SP metadata/contract; that never permits exposing private keys.

**"Do not leak keys" primarily means protecting private keys, secrets, and sensitive trust config.** Public certificates should not be called secrets; nevertheless, a failure response is not the place to expose certificate chains, key aliases, secret file paths, rollover fingerprints, or HSM slot names to arbitrary visitors.

## 3. Conditions That Trigger Rejecting a SAMLResponse or Assertion

A message must be rejected if it violates **even one mandatory security condition**. Never stop at "XML signature valid" or "IdP posted to the right hostname".

| Layer | SP check | Invalid example | Safe response |
| --- | --- | --- | --- |
| Transport / input | Right method/path/binding, Content-Type, and reasonable size | POST to wrong endpoint, empty/oversized payload, missing form field | Layer-appropriate 4xx/generic failure; do not parse arbitrarily |
| Decode / XML parser | Valid Base64, well-formed XML, entity/DTD/size/depth limits | Bad Base64, malformed XML, XML entity abuse | Reject; do not log raw XML |
| Registration | Trusted `RelyingPartyRegistration` matching context | Unknown registration ID / other tenant | Reject or generic error; never synthesize IdP from payload |
| Signature/trust | Signature protects **exact consumed data**, signing key belongs to trusted IdP | Unsigned, bad signature, attacker's `KeyInfo` | Reject; never fall back to trust-on-first-use |
| `Issuer` | Response/assertion issued by configured IdP | Wrong issuer or matching string with untrusted key | Reject |
| `Destination` / `Recipient` | Response and bearer confirmation target right ACS | Sent to another ACS or wrong HTTP host | Reject; inspect public URL/proxy |
| `AudienceRestriction` | Assertion issued for this exact SP entityID | Assertion belongs to another SP | Reject |
| Time conditions | `NotBefore`, `NotOnOrAfter`, SubjectConfirmationData, `IssueInstant` per policy | Not yet valid, expired, large clock skew | Reject; widen skew only under control |
| Request correlation | `InResponseTo` matches saved AuthnRequest, right registration/session | Wrong/lost/consumed request ID | Reject per SP-initiated policy |
| Anti-replay | IDs unused, when policy mandates single use | Re-submitting old assertion/Response | Atomic reject, even across multiple pods |
| Assertion identity | Valid Subject/NameID, confirmations, and claims | Ambiguous assertion, subject outside signed portion | Reject / do not construct principal |
| SAML Status | Response reports failure | `Requester`, `Responder`, authentication canceled/failed | Do not treat as authenticated |
| Application mapping | Claims map to valid user/tenant/permissions | Invalid group, colliding subject across tenants | Reject mapping or deny permissions per policy |

**Critical point:** invalid signature, wrong audience, expired assertion, replay, decryption failure, and missing `InResponseTo` may be **distinct internal causes**, yet **the client does not need those details**. Externally, all can return the same message: "Unable to complete SSO login. Please try again or contact support."

### 3.1. A Signature Valid Under Some Key Does Not Mean a Trusted Source

If the SP pulls a public key from browser-sent `ds:KeyInfo` and trusts it, an attacker can sign XML with their own key. The SP must verify signatures with certificates/keys from a **vetted IdP registration**, check issuer/tenant, and ensure the object used to build the principal is the object protected by the signature. XML Signature Wrapping illustrates why checking a lone "signature valid" flag is insufficient.

When failing on signature, safe logs can record `INVALID_SIGNATURE` without recording XML signature values, `KeyInfo`, PEM certificates, private keys, full XML canonicalization dumps, or raw SAMLResponse.

### 3.2. Time and Replay

`NotOnOrAfter` is **exclusive**: at that instant it is expired. Clock skew (if permitted) must be a defined policy rather than arbitrarily adding minutes to "make login work". An unexpired assertion can still be **replayed**, so reuse prevention by ID/state is required; especially across multiple nodes, anti-replay caches must be shared and atomic by design.

An expired response should be rejected identically to a bad-signature response at the browser. Internally you only need code `EXPIRED_ASSERTION` and a correlation ID; never return exact timestamps, assertion IDs, or full Conditions XML to the browser.

### 3.3. Do Not Confuse Authentication Failures with Authorization Denials

- **Authentication failure:** no trusted identity was created because the SAMLResponse was invalid; goes through the SAML authentication failure path.
- **Authorization denial:** user is already authenticated, yet lacks permission for the endpoint/tenant/object; normally 403/application authorization handling, **not** a SAML validation error.
- **Infrastructure failure:** Redis/session store unreachable, HSM unavailable, IdP metadata unready; handle cleanly without loosening validation to force login success.

Never turn a default `ROLE_USER` or a `groups=admin` claim in an unverified assertion into privileges to "avoid login errors".

## 4. Fail-Closed Principle and Two Information Channels

When protocol checks fail, the system must:

1. **Create no `Authentication` for that payload**, storing no principal or authorities from unverified claims.
2. **Never skip validation** to keep going; never pick another signing certificate suggested by raw XML.
3. **Return no sensitive data** in body/headers, redirect URLs, HTML hidden fields, exception stack traces, flash attributes, or page-source comments.
4. **Log structured events internally** with minimal codes/identifiers; let operations investigate without copying SAML payloads.
5. **Do not cache** error responses holding user data and never let the error endpoint become an open redirect.
6. **Offer the user a safe next step**: retry login via a fixed link or contact support with an internally generated request reference ID.

### 4.1. User-Facing Data vs. Internal Data

| Information | Browser / user | Controlled internal audit |
| --- | --- | --- |
| Message "Unable to complete SSO login" | **Yes** | Optional |
| Random, identity-free support correlation ID | Allowed | Yes |
| Error category `INVALID_SIGNATURE`, `WRONG_AUDIENCE`, `SAML_EXPIRED` | **No** | Yes, allowlisted |
| Verified IdP Issuer or trusted registration ID | No | Yes if truly needed |
| Raw `SAMLResponse`/assertion XML/Base64 | **No** | **Do not log** |
| `NameID`/email/groups/PII | Do not display in error | Only with business justification and dedicated protection; default **no** |
| Signature values, `KeyInfo` XML, session cookies, secret RelayState | No | Do not log raw |
| SP/IdP private keys or decryption secrets | **Strictly never** | **Strictly never** |
| Stack traces/`exception.getMessage()`/nested causes | No | Avoid logging directly on SAML-input paths; use controlled codes/metrics |
| Node ID, timestamp, route template, validator stage | Unnecessary | Allowed, after normalization |

### 4.2. Why Is `exception.getMessage()` Unsafe?

You cannot rely on an assumption that every library's exception message is always "clean". Depending on validator, parser, servlet container, or exception wrapper version, messages/causes can include XML fragments, signing cert structures, paths containing secrets, claim values, URIs, or attacker-supplied input.

Therefore avoid these anti-patterns:

```java
// DO NOT use in production SAML failure handling.
logger.error("SAML failed, response={}, error={}",
        request.getParameter("SAMLResponse"), exception);
response.getWriter().write(exception.getMessage());
```

This snippet shows **bad behavior** to catch in reviews; it is not a recommended solution. Any statement serializing an exception with its full stack trace also needs scrutiny because the chain may contain sensitive data. If detailed root causes are needed to fix bugs, use PII-free test environments/fixtures, protected debug channels, and restricted access procedures; never enable raw payload logging broadly in production.

### 4.3. Same External Response Yet Sufficient Supportability

User-facing example:

```text
Unable to complete SSO login.
Please try again. If the error persists, contact support
and provide the request code shown on this page.
```

If exposing a **request code** to the browser, generate a UUID/opaque ID independent of SAML content. Internal audits use that same ID to correlate. Never turn the request code into a login session, a secret unlocking XML retrieval, or a public API returning error details.

To avoid creating a login oracle, never return specific messages like "email X does not exist", "IdP signed with certificate alias K", or "assertion for tenant Z" externally. HTTP statuses may differ at edge/proxy layers, yet the app should keep SAML validation errors uniform in **body and detail level**.

## 5. Where Spring Security Verifies and Handles Failures

### 5.1. Classes to Distinguish

| Component | Responsibility |
| --- | --- |
| `Saml2WebSsoAuthenticationRequestFilter` | Creates/sends `AuthnRequest` to IdP; does not check SAMLResponse |
| `Saml2WebSsoAuthenticationFilter` | Receives `SAMLResponse` POST at ACS, runs authentication flow |
| `Saml2AuthenticationTokenConverter` | Extracts response, resolves registration/context from request or state |
| `RelyingPartyRegistrationRepository` | Supplies IdP trust, valid SP entityID/ACS/credentials |
| `OpenSaml4AuthenticationProvider` / `OpenSaml5AuthenticationProvider` | Depending on OpenSAML/Spring Security version, parses/decrypts/validates SAML |
| `AuthenticationManager` | Coordinates authentication, returns result/exception |
| `AuthenticationFailureHandler` | Chooses response for **authentication failures caught by the auth filter and passed to the handler** |
| `AuthenticationEventPublisher` / observability | May publish failure events; must restrict payload info when logging/emitting metrics |
| `ExceptionTranslationFilter` | Translates certain auth/authz exceptions in the filter chain to entry point/access denied handling |
| Edge/proxy/servlet error handling | Handles errors before or outside SAML auth filter, e.g. oversized body/wrong HTTP method |

**Version note:** Spring Security 6.5 can use OpenSAML 4 or 5 depending on dependencies, and 7.x uses OpenSAML 5 in current documentation. Never hardcode one provider across all versions; retain default validation and verify against your active release.

### 5.2. AuthenticationFailureHandler Does Not Catch Every Error

An `AuthenticationFailureHandler` on `saml2Login` handles `AuthenticationException` instances passing through the SAML authentication processing filter. Yet it is **not guaranteed** to run for:

- HTTP bodies exceeding limits blocked by ingress/Tomcat/WAF before reaching the app.
- Exceptions in a request size limiter, a servlet filter ordered before the SAML filter, or a misconfigured route.
- Startup misconfigurations, unreadable private key files, or metadata dependency failures before the flow builds.
- SAML logout requests/responses if the app implements SLO; SLO has its own filters and failure handling.
- Exceptions outside authentication processing, e.g. errors in downstream custom filters/loggers/trace collectors.

Layered error handling is required: generic edge 400/413/429/503 responses, stack-trace-free servlet/container error mappings, the SAML failure handler for authentication failures, and internal alerts for infrastructure incidents. Never leave Spring Boot's default error page in debug mode exposing exceptions/traces to browsers.

### 5.3. Do Not Alter Validators Just to Beautify Errors

Response/assertion validators can be customized via OpenSAML provider extensions, yet must **compose** with default validation rather than replacing it with code checking only issuer or signature presence. When changing error messages, start with the failure handler, log policy, and error code mappings; never disable signature, audience, replay, or `InResponseTo` checks to avoid an exception.

## 6. Spring Security 6.x Config: Returning Generic Errors on SAML Login Failure

### 6.1. SecurityFilterChain with an Explicit Failure Handler

Source-level example for Spring Boot 3.x / Spring Security 6.x Servlet; uses `saml2Login(saml -> saml.failureHandler(...))`. To reduce leakage risk, the handler **never reads `SAMLResponse` and never serializes exceptions**.

Create `SamlFailureSecurityConfig.java`:

```java
import java.io.IOException;
import java.util.UUID;

import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.MediaType;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.security.web.authentication.AuthenticationFailureHandler;

@Configuration
public class SamlFailureSecurityConfig {

    private static final Logger LOG =
            LoggerFactory.getLogger(SamlFailureSecurityConfig.class);

    @Bean
    AuthenticationFailureHandler samlFailureHandler() {
        return (request, response, exception) -> {
            String eventId = UUID.randomUUID().toString();

            // Do not log exception, SAMLResponse, RelayState, or cookies.
            LOG.warn("event=saml_auth_rejected event_id={} result=DENIED",
                    eventId);

            response.setStatus(HttpServletResponse.SC_UNAUTHORIZED);
            response.setCharacterEncoding("UTF-8");
            response.setContentType(MediaType.TEXT_PLAIN_VALUE);
            response.setHeader("Cache-Control", "no-store");
            response.setHeader("Pragma", "no-cache");
            response.setHeader("Referrer-Policy", "no-referrer");
            response.getWriter().write(
                    "Unable to complete SSO login. "
                  + "Please try again or contact support. "
                  + "Reference ID: " + eventId);
        };
    }

    @Bean
    SecurityFilterChain securityFilterChain(
            HttpSecurity http,
            AuthenticationFailureHandler samlFailureHandler) throws Exception {

        http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/public/**").permitAll()
                .anyRequest().authenticated())
            .saml2Login(saml -> saml
                .failureHandler(samlFailureHandler));

        return http.build();
    }
}
```

**Explanation of limits and behavior:**

- This is a **Spring configuration class**, not a standalone Java program runnable with `javac`. The app also needs `spring-security-saml2-service-provider`, a configured `RelyingPartyRegistrationRepository`/IdP, and a Servlet runtime.
- Each failure receives a random `eventId` for correlation; that ID **is not derived from assertion ID or `NameID`**. Give only the event ID to the user, never internal verification details.
- LOG records only event type, ID, and result. `exception` is omitted from logger args: SLF4J can log a stack trace when a Throwable is passed, so it is deliberately **excluded**.
- `response.setStatus(401)` is an illustrative choice for an app returning a plain-text response. Depending on UX/IdP/browser, an app may redirect to a static error page; there is no single mandatory HTTP status for all SAML login failures.
- `Cache-Control: no-store` reduces caching of error responses carrying reference IDs. `Referrer-Policy: no-referrer` reduces leakage in referers on the error page, yet does not replace log/body policies.
- Spring Security processes authentication failures per filter mechanics; this handler **does not** automatically clear all prior HttpSessions or revoke other sessions. If session revocation is separately required, define an explicit policy to avoid letting attacker-sent invalid POSTs log users out.
- On real sites, you can serve a static error page, i18n text, or internal redirect to a fixed URL. Never echo `exception.getMessage()` or turn a `returnUrl` parameter into a redirect target.
- To avoid login loops, if the error page is a separate endpoint like `GET /sso/error`, it must be `permitAll()` so it does not trigger SAML login again.

**Prerequisites:** The filter chain must match ACS `/login/saml2/sso/{registrationId}`. If the app has multiple `SecurityFilterChain` beans, ensure callbacks enter the chain containing `saml2Login`. If the IdP response is blocked by a proxy before the filter, the handler will not run; generic error mapping is needed at ingress.

### 6.2. Variant Redirecting to a Static Error Page

If the browser needs a UI instead of rendering text on the ACS POST, you can use:

```java
import org.springframework.security.web.authentication.SimpleUrlAuthenticationFailureHandler;

// Fragment for saml2Login config when GET /sso/error is public:
SimpleUrlAuthenticationFailureHandler handler =
        new SimpleUrlAuthenticationFailureHandler("/sso/error");

// http.saml2Login(saml -> saml.failureHandler(handler));
```

This is a **fragment**, not a standalone runnable class. The `/sso/error` page displays only a generic message and a retry button pointing to an allowed login-initiation URL, holding no exceptions, assertions, certificates, or arbitrary `next` URLs. Check whether the handler/framework stores the exception in session or request attributes for UI rendering unexpectedly; the error page must never read/display that content. If choosing this over an audit-logging failure handler, instrument separate auditing that does not leak Throwables.

### 6.3. When Categorizing Reason Codes

Internal error classification is best done at a **safely verified validator/integration boundary**, using a fixed enum. Example:

```text
INVALID_FORMAT
UNTRUSTED_ISSUER
INVALID_SIGNATURE
WRONG_AUDIENCE
WRONG_RECIPIENT
EXPIRED_ASSERTION
REQUEST_CORRELATION_FAILED
REPLAY_DETECTED
DECRYPTION_FAILED
INTERNAL_AUTHENTICATION_ERROR
```

Never try classifying by:

```java
// Anti-pattern: never treat exception message as a reason code.
String reason = exception.getMessage();
LOG.error("reason=" + reason);
```

The snippet above is unsafe because exception messages can hold payload data. If only a generic authentication exception exists without knowing the exact reason, logging `AUTHENTICATION_REJECTED` is better than guessing from exception text. For deeper reason codes, emit events from validator layers with safe telemetry and normalize to an enum; never log raw SAML.

## 7. Safe Operational Observability: Log Less, Yet Useful

### 7.1. Sample Audit Event

```json
{
  "event": "saml_auth_rejected",
  "event_id": "b8aee5d2-0d66-4749-98b5-81563f1b2008",
  "reason_code": "INVALID_SIGNATURE",
  "registration": "corp",
  "node": "pod-b",
  "result": "DENIED",
  "timestamp": "2026-11-07T03:00:00Z"
}
```

This is a **simulated JSON sample**, not log output emitted by `SamlFailureSecurityConfig` above (that code logs only event/result/ID, without a validator reason_code). Populate `registration` only after control or allowlist matching: a raw `registrationId` in the path or an unverified XML `Issuer` is attacker input. `timestamp` uses system time, never `IssueInstant` from an untrusted response as event time.

Depending on context, you can add:

- `correlation_id` generated by ingress/service, distinct from secret RelayState; consistent across nodes without holding raw SAML.
- Stage codes `DECODE`, `TRUST`, `CONDITIONS`, `CORRELATION` (fixed catalog), latency, and HTTP response class.
- Approved IdP registration ID (avoid storing unverified Issuer strings unless necessary).
- Known node/cluster/region, IdP integration version, and non-sensitive key-rollover phase flags.
- Event counts by reason code for incident detection, never tagging emails/NameIDs as metric labels.

### 7.2. Sources That Can Leak Data Even When the Handler Logs Nothing

| Component | Risk | Safeguard |
| --- | --- | --- |
| Servlet logging filters, e.g. `CommonsRequestLoggingFilter` capturing bodies | Writes `SAMLResponse`/cookies into access/debug logs | Disable includePayload on ACS; redact sensitive fields |
| Reverse proxy/ingress access logs | Records request bodies, Redirect URLs with `SAMLRequest`/RelayState | Disable body logging for SSO; avoid raw query strings holding state |
| WAF/IDS request capture | Saves full flagged payloads | Configure controlled redaction/exclusions for ACS |
| APM/OTel tracing | Auto-captures request bodies/form fields/exception attributes | Exclude `SAMLResponse`, `SAMLRequest`, Cookie, Authorization, and raw exceptions |
| Error monitoring (Sentry/…) | Attaches HTTP body, headers, request params, or exception locals | Configure scrubbing/before-send; test with synthetic canary data |
| Framework/OpenSAML debug logs | Prints XML, signatures, input bytes when log level is too verbose | Restrict logger levels in production; use test fixtures for debugging |
| Application logger | `log.error("SAML", exception)` serializes message + cause | Log only allowlisted event/reason; protect separate debugging |
| Error page/JSON response | `exception.getMessage()`, stack traces, raw SAML codes | Generic response; global error mapping |
| Redirect URL/`Location` | Query holds `RelayState`, key paths, assertion IDs, raw errors | Fixed URL or opaque event ID; allowlist return targets |
| Metrics labels | `NameID`/Issuer string/Exception text as labels | Tag only low-cardinality allowlisted values |
| Support tickets/screenshots | Users/devs paste URLs, SAML bodies, PEMs | Instruct sending event ID only; mask sensitive info |
| Redis/session dumps | Pending requests or unclassified SAML state | ACLs, encryption, TTL; never dump into uncontrolled debug |
| CI/CD, startup diagnostics | Private keys in env vars/config prints, debug mounts | Secret manager, file permissions, redaction, never commit |

**Important:** safe logging inside `AuthenticationFailureHandler` cannot compensate for ingress/WAF/APM capturing bodies before the handler. Audit **from browser to SP and from SP to every telemetry backend**.

### 7.3. Redaction: Do Not Trust Regex Alone

Indicators to mask:

```text
SAMLResponse
SAMLRequest
RelayState (if carrying reusable opaque secrets/state)
Cookie / Set-Cookie
Authorization
NameID, assertion XML, AttributeValues containing PII
ds:SignatureValue / KeyInfo XML
private-key PEM blocks, credentials, decryption keys
```

A regex matching `SAMLResponse=...` can miss:

- Bodies using multipart/other encodings, form URL-encoded variants, or different key casing.
- Base64 values with line breaks, duplicate parameter names, or double-encoding.
- XML captured after decoding without the `SAMLResponse` field name.
- Exception messages holding assertion fragments or PEMs without field names.
- Trace middleware logging Java objects, JSON-serialized exceptions, or unexpected span attributes.

**Safer mindset:** **never collect bodies/query credentials in the first place** (allowlist logged fields), then apply secondary masking/scrubbing and verify with canaries. Blacklist-based redaction is an extra layer, never the sole defense.

### 7.4. Sanitize Untrusted Data Before Logging

Attackers can try injecting newlines/control characters into `Issuer`, `RelayState`, or other fields to cause **log injection**, forging a fake "LOGIN_SUCCESS" log line. If logging any user-influenced string, cap length, escape control characters, use structured JSON encoding, and allowlist. Best practice is logging the registration ID from config post-validation rather than raw XML issuers.

Never use arbitrary exception messages as dynamic metric labels, as that both leaks info and causes **cardinality explosion** in metrics systems.

## 8. Protecting Keys and Certificates in Error Handling

### 8.1. Signatures and Trust Anchors

SAML Responses/Assertions are signed by the IdP with its private key. The SP verifies signatures using the **IdP public signing key/certificate from a trusted `RelyingPartyRegistration`**, not any certificate embedded in XML `ds:KeyInfo`.

A public certificate in SP/IdP metadata is not a secret, yet still requires strict trust and rotation governance. If the IdP rotates its public cert before the SP updates, users may hit SAML signature failures. The right response is a generic error plus an operational rollover alert; **never** send internal certificates/PEMs to users, and never skip signature verification to let logins proceed.

### 8.2. Key Material Must Never Enter Responses

Items that must never appear in responses/logs:

- `-----BEGIN PRIVATE KEY-----`, PKCS#8 PEMs, JWK private parameters, HSM credentials, keystore passwords.
- Passwords unlocking keystores, environment secret values, cloud KMS tokens.
- `Saml2X509Credential` or credential object dumps containing private keys.
- Debug stack traces exposing secret mount paths alongside sensitive info; file paths might not be secrets yet still should not be publicized via login errors.

Never place private keys in YAML under source control. Use secret stores, key rotation, and least-privilege read permissions. If a secret value was ever logged, treat it as a **credential exposure incident**, not merely deleting one log line: audit backups/trace pipelines, revoke/rotate keys, and review active sessions and permissions.

### 8.3. Decryption Errors

If `EncryptedAssertion`/`EncryptedAttribute` cannot be decrypted with the right private decryption key, **never** fall back to plaintext elsewhere or skip validation. Log a `DECRYPTION_FAILED` code in internal audit while the client sees a generic message. Avoid logging ciphertext, decrypted attributes, key handles, IVs, or full crypto library exception chains.

Changing the order of decryption and signature validation can break XML signatures or security invariants. When customizing the OpenSAML provider, understand signature coverage and version extensions, consulting official docs to ensure unverified assertions are never read.

### 8.4. Public Certificates Do Not Mean "Permit Public Debugging"

Some SPs publish their SP public certificate in SAML metadata so the IdP can verify signed AuthnRequests. That does **not** mean login error messages should list all IdP signing certs, SHA fingerprints, keystore aliases, and rollover schedules. An error page is an interface to untrusted clients; limit disclosing config details that help attackers fingerprint the environment.

## 9. Failure Paths That Bypass the SAML Authentication Failure Handler

### 9.1. Proxies, Servlet Containers, and Request Size

An attacker can send an oversized `SAMLResponse` to trigger DoS or force reverse-proxy error logging. Limit HTTP request bodies, form parameters, XML parser depth/entity expansion, and processing time **before** content reaches the validator.

Size limits should reflect real assertion/attribute sizes with headroom for Base64/encoding; never copy an arbitrary number as a production standard. When limits are exceeded, ingress/servlet returns a generic error (e.g. 413) without echoing the payload. The `saml2Login` failure handler may not run because the request was blocked earlier.

### 9.2. Base64 / XML Parsing Failures

A `SAMLResponse` with an empty field, invalid characters, or malformed XML must be rejected. The parser must forbid/limit external entities, DTD/XXE, entity expansion, and unintended schema fetching per library configuration. Avoid parsing raw SAML XML yourself with custom regex/XPath for `NameID` while only letting the provider verify a different element's signature.

DoS controls: cap compressed/expanded sizes, attribute/assertion counts, parse duration, and concurrency. Test malformed inputs with safe fixtures rather than pasting production payloads into bug reports.

### 9.3. Application/Host Error Pages

Spring Boot has its own error handling mechanism. If staging enables stacktraces/exception details in error payloads, a failure before/outside the SAML filter can accidentally expose XML or secret paths. In production, keep error pages generic, disable stack traces/exception messages, and never attach request bodies.

Illustrative properties (**verify against your Spring Boot version**):

```yaml
server:
  error:
    include-message: never
    include-stacktrace: never
    include-exception: false
```

These properties help reduce Boot's default error exposure; they **do not** govern responses built by custom controllers, proxies, servlet filters, or external loggers. Verify actual output across negative test cases.

### 9.4. Error Processing Outside Login: SAML Logout

`Saml2LogoutRequestFilter` and `Saml2LogoutResponseFilter` handle Single Logout (SLO) with their own callbacks/signatures/policies. A failure handler attached only to `saml2Login` does not cover SAML Logout. If SLO is enabled, apply the same non-disclosure rules for payloads/keys across those error paths.

## 10. Designing Error Responses: APIs and Browsers

### 10.1. When Users Log In via Browser

You can return status 401 with generic error text/page or a fixed redirect to `/sso/error`. A safe redirect requires:

- Fixed/allowlisted internal URL, never taken from unvalidated `RelayState`/`returnUrl`.
- Error page accessible anonymously; protecting it with SSO creates an infinite loop.
- HTML responses never reflecting untrusted `Issuer`, `NameID`, `statusMessage`, or exception text.
- Never storing raw SAMLResponse in flash/session just to render a message.
- `Cache-Control: no-store` and appropriate security headers.

If the error page has a "Try again" button, point it to a standard SSO-initiation URL like `/saml2/authenticate/corp` for an allowed registration, never re-submitting an old raw SAMLResponse.

### 10.2. When Backend APIs Rely on SAML Sessions

Business APIs backed by `HttpSession` post-SSO can return 401 when unauthenticated or 403 on insufficient authority. Still, the **ACS callback remains a SAML browser protocol**, so never turn raw `SAMLResponse` errors into JSON error dumps for frontends. Protect state-changing endpoints with CSRF, guard session fixation, and set `Secure`/`HttpOnly`/`SameSite` cookies properly; never disable CSRF site-wide to prevent ACS POSTs from failing.

### 10.3. Do Not Leak Classification Details via Arbitrary Timing

Validation failures can take different amounts of time (signature verify, decrypt, XML parse). Complete request-level constant-time execution cannot be assumed for all failures. However, never deliberately return distinct messages/statuses/headers that let attackers distinguish certificates, account existence, or tenant mappings. Use a generic response for authentication failures and rate limiting/monitoring for abuse.

When exposing richer details to operations staff, never rely on browser-sent `?debug=true`. Operations channels must be independently authenticated/authorized and avoid retaining raw credentials without dedicated procedures.

## 11. Pure Java 17: Separating Internal Error Codes from Public Messages

The following example runs on **JDK 17+ without Spring Security**. It simulates validation outcomes already supplied as booleans. This is **not** a SAML parser/validator: booleans are self-constructed in the demo, with no cryptographic signature verification.

Create `SafeSamlFailureDemo.java`:

```java
public class SafeSamlFailureDemo {

    enum Reason {
        ACCEPTED,
        INVALID_SIGNATURE,
        WRONG_AUDIENCE,
        EXPIRED_ASSERTION,
        REQUEST_CORRELATION_FAILED
    }

    record Candidate(boolean signatureTrusted,
                     boolean audienceMatches,
                     boolean withinTimeWindow,
                     boolean requestCorrelated) {}

    static Reason evaluate(Candidate candidate) {
        if (!candidate.signatureTrusted()) {
            return Reason.INVALID_SIGNATURE;
        }
        if (!candidate.audienceMatches()) {
            return Reason.WRONG_AUDIENCE;
        }
        if (!candidate.withinTimeWindow()) {
            return Reason.EXPIRED_ASSERTION;
        }
        if (!candidate.requestCorrelated()) {
            return Reason.REQUEST_CORRELATION_FAILED;
        }
        return Reason.ACCEPTED;
    }

    static String publicMessage(Reason reason) {
        return reason == Reason.ACCEPTED
                ? "Sign-in complete"
                : "SSO sign-in failed";
    }

    public static void main(String[] args) {
        Candidate invalidSignature =
                new Candidate(false, true, true, true);
        Candidate wrongAudience =
                new Candidate(true, false, true, true);
        Candidate valid =
                new Candidate(true, true, true, true);

        Reason first = evaluate(invalidSignature);
        Reason second = evaluate(wrongAudience);
        Reason third = evaluate(valid);

        System.out.println("client 1: " + publicMessage(first));
        System.out.println("audit 1: " + first.name());
        System.out.println("client 2: " + publicMessage(second));
        System.out.println("audit 2: " + second.name());
        System.out.println("client 3: " + publicMessage(third));
        System.out.println("audit 3: " + third.name());
    }
}
```

Compile and run:

```bash
javac SafeSamlFailureDemo.java
java SafeSamlFailureDemo
```

Exact stdout:

```text
client 1: SSO sign-in failed
audit 1: INVALID_SIGNATURE
client 2: SSO sign-in failed
audit 2: WRONG_AUDIENCE
client 3: Sign-in complete
audit 3: ACCEPTED
```

Learning points:

- Two different failures (`INVALID_SIGNATURE` and `WRONG_AUDIENCE`) produce the **identical client message**.
- The `audit` channel uses fixed reason codes without raw assertions or keys.
- `ACCEPTED` in the demo **does not** prove SAML was verified: booleans are self-generated by the program. Production must use Spring Security/OpenSAML to verify signatures/conditions/state before creating `Authentication`.
- The demo uses `System.out` for readability; production auditing uses structured loggers/metrics with access control, retention, log scrubbing, and correlation IDs.
- In practice, a validation failure can involve multiple causes at once; reason-code categorization needs a consistent policy rather than guessing from untrusted exception messages.

## 12. QA Testing: "Reject" Is Not Enough—Must "Reject Without Leak"

### 12.1. SAML Security Behavior Tests

| Negative case | Authentication outcome | Display / logging outcome |
| --- | --- | --- |
| Missing `SAMLResponse` | No principal created | Generic error; never dump form fields |
| Invalid Base64 | Reject | Do not echo Base64 or stack traces |
| Malformed XML | Reject | Return no XML fragments/DTDs in response |
| XML with entity/size abuse | Reject/413 per layer | Do not log body; enforce resource limits |
| Missing signature | Reject | Internal reason code only; return no certificate info |
| Invalid signature | Reject | Never log `SignatureValue`, XML, or full exceptions |
| Untrusted `Issuer` | Reject | Never reflect raw Issuer from payload |
| Response for another SP entityID | Reject | Client never sees expected Audience value |
| `Destination`/`Recipient` differs from ACS | Reject | Never leak internal URLs or proxy headers |
| `NotBefore` in the future | Reject | Never print timestamps/subject data to browser |
| `NotOnOrAfter` passed | Reject | Never print assertion ID/Conditions |
| `InResponseTo` wrong/consumed | Reject | Generic error; safe audit code |
| Replay SAMLResponse across two pods | Reject repeat attempt | No raw payloads in duplicate detection logs |
| Undecryptable encrypted assertion | Reject | Never print decrypted/plaintext/ciphertext or private key paths |
| Assertion with XML signature wrapping | Reject; use only verified XML region | Never print raw XML to "prove" parser error |
| IdP returns unsuccessful Status | Not authenticated | Generic client error; internal code if needed |
| Claims with unknown group/wrong tenant | Mapping/authorization rejects per policy | Never leak claims or account existence |
| Skewed signing cert rollover | Reject until trust aligns | Internal ops alert; never disable signatures |
| Wrong ACS path / missing filter | No login | Generic 404/401; no stack traces |
| Client sends RelayState to external host outside allowlist | No open redirect | Never reflect/redirect to raw value |
| Real test response captured in WAF/APM canary test | Test fails if secret appears | Fix redaction/collection at the source |

### 12.2. Unit Tests for the Failure Handler

You do not need real assertions to test **how error responses are emitted**. Use `MockHttpServletRequest`, `MockHttpServletResponse`, and a test `AuthenticationException`, invoke the handler directly, and assert:

- Expected status (e.g. 401), Content-Type text/plain UTF-8 or allowlisted redirect.
- Body contains no `SAMLResponse`, raw `NameID`, PEM certificate, exception message, or stacktrace.
- Response headers contain no `RelayState`, private key path, or assertion ID.
- `Cache-Control: no-store` is present where required.
- Event ID has valid opaque formatting; use a test log appender to verify no raw request params/exceptions appear in audit logs.
- Handler never uses `exception.getMessage()` as client output.

**Caution:** checking only the HTTP response without checking logs/traces/proxies can still miss leaks. Test the logging layer and telemetry exports separately with canary values.

### 12.3. End-to-End Integration Tests

With a test IdP and test certificate:

1. Create an SP-initiated `AuthnRequest` from Spring Security; save correlation state.
2. Send a valid SAMLResponse signed by the **test IdP private key**; verify success.
3. Send fixtures with bad signature, wrong audience, expired timestamps, wrong recipient, and replay; verify no new `Authentication`/session is created.
4. Inspect response bodies, headers, redirect chains, and browser error pages; scan for secret canaries/PII/certificate details.
5. Inspect application logs, ingress/WAF/APM, and test-environment metrics; scan for canary strings in raw XML, Base64, URL-encoded forms, and debug exceptions.
6. Test callbacks across another pod and blocked session cookies to ensure `InResponseTo` is not bypassed.
7. Test 4xx/413 before the Spring filter, 5xx from config/Redis/keystore faults, and SAML Logout errors if present; all must yield generic external errors.
8. When a test fails, fix **the right layer**: request-size guard, ACS matcher, IdP trust, cookie policy, failure handler, log scrubber, or observability configuration.

### 12.4. Data-Leak Canary Test

In a test environment **using synthetic data only**, place a canary token such as:

```text
TEST_ONLY_SAML_CANARY_7F3A
```

into an AttributeValue/NameID inside a test-IdP-signed assertion or validly prepared test fixture. After submitting failing fixtures, scan all logs/traces/error responses to check if the canary leaked. Never use real user assertions and **never** share PII in tickets/screenshots.

Layers to scan: pre-SP request body capture, OpenSAML/Spring Security loggers, failure handler, custom exception mappers, API gateway/WAF/APM, crash reports, and support systems. If the canary appears, the test **FAILS** even if the SP properly rejected authentication.

## 13. Diagnosing Incidents Without Enabling Raw Payload Logging

| Symptom | Possible source | Safe diagnostic data |
| --- | --- | --- |
| Spike in `INVALID_SIGNATURE` after cert rollover | SP metadata/IdP cert out of sync | Config deploy timestamps, IdP registration, public cert metadata on admin channel |
| `WRONG_AUDIENCE` after hostname change | SP entityID mismatch | Configured public entityID (never sent in browser error) |
| `WRONG_RECIPIENT`/`Destination` mismatch | Wrong ACS URL behind proxy | Public scheme/host/path/trusted forwarded headers |
| `EXPIRED_ASSERTION` spike | Clock skew/IdP clock/latency | NTP metrics, allowed skew policy, histogram by event code |
| `REQUEST_CORRELATION_FAILED` | Lost session state, SameSite cookie, different request ID | Whether cookie arrived (not its value), session store health, registration ID |
| `REPLAY_DETECTED` across two pods | Non-atomic/unshared cache | Replay store health, atomic transaction metrics |
| `DECRYPTION_FAILED` | Wrong SP private decryption key, rollover | Version/rotation status on admin channel; never print private key |
| XML decode errors rise | Client attack, proxy body rewrite, oversized payload | Body size/histogram/error count; do not store body |
| Error page exposes stack trace | Spring Boot error config or filter exception | Review global error mapping, integration test response |
| APM still sees SAMLResponse | Auto-capture of forms/exception locals | Agent config, denylisted fields, scrub policy |
| 401 response yet user session remains | Failure path does not equate to session revocation | Separate session lifecycle/reauth/logout policy |
| Many 403s after login success | Authorization/domain mapping | Role/object policy; do not blame all 403s on SAML validation |

**Sensible debugging sequence:** identify the error stage via event code; inspect registration/metadata/clock/proxy/session via config data; use signed **test fixtures** to reproduce; use protected local debuggers only on synthetic data; never turn on "dump SAMLResponse" logging across production.

## 14. Safe Observability and Incident Response When Data Leaks

### 14.1. If SAMLResponse/Assertion Appeared in Logs

1. **Stop collection** at the exact source: proxy, WAF, servlet request logger, APM agent, or custom exception formatter.
2. Restrict access to logs/traces containing credentials and determine the timeframe, data, and who could view them.
3. Assess whether assertions remain reusable (lifetime, audience, subject confirmation, replay defense) and which sessions were created; revoke affected sessions on signs of abuse.
4. Coordinate with privacy/security teams on retention, legal obligations, and purging/restricting copies in archives/backups per policy.
5. Add canary tests and regression tests to prevent recurrence.

**Never** paste raw assertions into a new ticket or group chat to ask for root cause; use event IDs, reason codes, and synthetic fixtures instead.

### 14.2. If a Private Signing/Decryption Key Is Compromised

1. Treat this as **more severe than a public certificate leak**: secure key storage, halt unauthorized distribution, audit access and permissions.
2. Depending on the compromised key, coordinate IdP/SP rotation, update metadata/cert trust, and revoke affected keys via established procedures.
3. Identify responses/requests/sessions that could have been forged or decrypted, checking for unauthorized access.
4. Revoke secondary secrets (keystore passwords, cloud credentials) if exposed from the same source; inspect CI logs/backups.
5. Monitor signature/decryption failures and anomalous login successes during key transition.
6. Never treat "deleted the log" as sufficient remediation if the key could already have been copied.

### 14.3. If Errors Spike Without Attack Evidence

SAML failures also commonly stem from misconfiguration: IdP cert rollover, clock drift, changed ACS URL, SameSite cookies, or session store outages. Do not assume every `INVALID_SIGNATURE` is an attacker, yet never disable validation to keep login rates up. Investigate causes systematically using internal metrics and metadata/endpoint checks.

## 15. Production Checklist

- [ ] ACS accepts only configured SAML responses/bindings; body size and parser complexity are bounded.
- [ ] Spring Security/OpenSAML verifies signatures on the right object, trusted issuer, audience, recipient, destination, time conditions, correlation, and replay policy.
- [ ] **Never** create `Authentication`/principal/roles when a SAML response is invalid.
- [ ] `AuthenticationFailureHandler` for SAML login returns only a generic message and independent correlation ID; never serializes Throwables or raw request bodies.
- [ ] Error mappings outside the handler (proxy, servlet, global error page, startup/Redis/metadata failures, SAML Logout) also disclose no details.
- [ ] No `SAMLResponse`/`SAMLRequest`/Cookie/sensitive `RelayState` in access logs, traces, WAF, or APM.
- [ ] Structured audits use **allowlisted reason codes**, never untrusted Issuer, NameID, exception messages, or raw URLs as log fields.
- [ ] Private signing/decryption keys reside in a secret manager/keystore, are never printed in startup/logs/responses, and have a rotation plan.
- [ ] Public certificates follow proper trust governance; never treat browser `KeyInfo` as a trust anchor.
- [ ] TLS, security headers, `Cache-Control: no-store`, and request-size limits have been tested.
- [ ] Negative tests exist for bad signature, expiration, audience, recipient, InResponseTo, replay, and malformed XML.
- [ ] **Data-leak canary tests** scanning responses, logs, traces, and metrics run with synthetic data.
- [ ] Raw-assertion debug logging is never enabled in production to "debug faster".
- [ ] Error pages cause no login redirect loops, open redirects, or account/tenant existence disclosure.
- [ ] Dashboards/alerts track error codes, nodes, and time; audit read permissions and retention are controlled.
- [ ] Incident response separates assertion leaks from private key leaks and ordinary misconfigurations.

## 16. Self-Check Questions

**Q1.** A SAMLResponse has a mathematically valid signature using a certificate attached in `KeyInfo`. Can the SP log the user in immediately?  
**Answer:** No. The SP only trusts public signing keys bound to an **approved IdP registration**, and must also verify issuer/audience/recipient/time/correlation and other conditions. Browser-supplied keys do not become trust anchors on their own.

**Q2.** Should you write `log.error("SAML rejected", exception)` in production logs for easier debugging?  
**Answer:** Not by default. Exceptions/causes can carry data from SAML payloads or sensitive config; prefer allowlisted event/reason codes, event IDs, and protected diagnostics with synthetic fixtures.

**Q3.** Should rejecting logins for `INVALID_SIGNATURE` vs `EXPIRED_ASSERTION` return two different error messages to the browser?  
**Answer:** Usually no. Clients only need a generic message; operations distinguish causes in controlled audits.

**Q4.** `SAMLResponse` is Base64, so is logging that string safer than logging XML?  
**Answer:** No. Base64 provides no security encryption; it can be decoded to reveal assertions and PII, or even replayed within the acceptance window.

**Q5.** Is disabling application body logging enough to prevent assertion leaks?  
**Answer:** Not enough. Gateways, WAFs, reverse proxies, APMs, error monitoring, and support systems may still capture bodies or exception details.

**Q6.** If the IdP signing certificate changes before the SP updates, what is the right handling?  
**Answer:** Reject the mismatched signature, record an operations event, verify and update trust per rollover procedure. Never disable signature validation as a temporary login workaround.

**Q7.** Does the SAML failure handler also catch requests blocked by nginx for being too large?  
**Answer:** No. A 413 error can happen before reaching Spring Security; generic error handling and redaction must exist at the edge.

**Q8.** Does "do not leak keys" mean every public signing certificate is a secret?  
**Answer:** No. Public certificates are commonly published in SAML metadata. **Private keys and secrets** must stay confidential; failure pages also have no reason to expose internal trust/keystore details.

**Q9.** Why is testing "response = 401" insufficient?  
**Answer:** Because that same invalid request may have logged the raw `SAMLResponse` at the WAF/APM or leaked in an exception. You must test **reject + no leak** end to end.

**Q10.** Can full error details be returned to support via a `?debug=true` query parameter?  
**Answer:** No. Debugging requires a separate authenticated/authorized channel with minimal data. A browser-sent query parameter is no proof of authorization to view secrets.

## 17. Official References and Best Practices

- [Spring Security – SAML2 Login Overview](https://docs.spring.io/spring-security/reference/servlet/saml2/login/overview.html): authentication flow and failure points before/after the OpenSAML authentication provider.
- [Spring Security – Authenticating SAML Responses](https://docs.spring.io/spring-security/reference/servlet/saml2/login/authentication.html): how the provider verifies SAMLResponse, issuer/destination, assertion conditions, and customizing validation/decryption.
- [Spring Security – AuthenticationFailureHandler Javadoc](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/web/authentication/AuthenticationFailureHandler.html): handler for authentication failures.
- [Spring Security – Servlet Authentication Events](https://docs.spring.io/spring-security/reference/servlet/authentication/events.html): publishing success/failure events and exception mapping; reviewing logged data.
- [Spring Boot – Common Application Properties](https://docs.spring.io/spring-boot/appendix/application-properties/): `server.error.*` and servlet-related limits/config.
- [OASIS SAML 2.0 Core](https://docs.oasis-open.org/security/saml/v2.0/saml-core-2.0-os.pdf): SAML Response, Assertion, signature/trust, Audience, SubjectConfirmation, and Conditions.
- [OASIS SAML 2.0 Bindings](https://docs.oasis-open.org/security/saml/v2.0/saml-bindings-2.0-os.pdf): HTTP Redirect/POST, `SAMLResponse`, `RelayState`.
- [OWASP SAML Security Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/SAML_Security_Cheat_Sheet): signature wrapping, trust keys, replay, and SAML response validation.
- [OWASP Logging Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Logging_Cheat_Sheet): data not to log, masking/sanitization, log injection, security events, and access control.
- [OWASP Error Handling Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Error_Handling_Cheat_Sheet.html): returning generic errors to users, controlling details, and avoiding secret/stack-trace leaks.
- [OWASP Session Management Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Session_Management_Cheat_Sheet): session cookies, fixation, expiration, and logout.

**Key takeaway:** **Rejecting invalid SAML** is an authentication decision: never create a principal/privileges when signature, trust, audience, recipient, time, or correlation checks fail. **Not leaking assertions or keys** is a system-wide decision: the browser sees only a generic error, audits record only controlled codes/correlation IDs, and proxies, servlet logs, OpenSAML diagnostics, APMs, WAFs, and tech support must never collect raw SAMLResponses, private keys, or secrets. Both conditions must hold for the error path to be secure.