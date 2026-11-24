# Redacting Sensitive Data When Enabling Spring Security, OpenSAML, or Kerberos Logs

**Module:** Spring Security – federation  
**Parent topic:** Observability and debugging  
**Reference stack:** Spring Boot 3.x, Spring Security 6.x, OpenSAML 4/5, Spring Security Kerberos/JAAS/JGSS, Java 17+, SLF4J/Logback.

## 1. Why Must Sensitive Data Be Redacted When Enabling Auth Logs?

SAML2, OIDC, and Kerberos deal directly with identity and credentials. When login fails with 401/403, SAML signature invalid, or Kerberos `GSSException`, `DEBUG`/`TRACE` helps locate the filter/validator handling the request. However, the data being debugged can contain **bearer credentials, session tokens, PII, and key material**.

If logged raw, a log entry can become a path to:

- **Session hijacking:** `JSESSIONID` cookies, gateway session cookies, bearer access/refresh tokens, and still-valid authentication tickets can be replayed by anyone reading the logs.
- **Identity leakage:** XML SAML Assertions contain `NameID`, email, employee ID, department, groups, phone, tenant, and attributes.
- **Kerberos credential exposure:** AP-REQ/service tickets, TGTs, GSS contexts, keytab contents, and session keys captured via debug output.
- **Infrastructure exposure:** KDC/realm/service principals, IdP endpoints, key/certificate metadata, and private file paths.
- **Log injection:** input containing CR/LF or multiline XML creates forged log lines, corrupts audits, or bloats log volume.
- **Uncontrolled data proliferation:** console, stdout/stderr, APM, collectors, SIEM, ticket attachments, and backups can all retain copies.

**Never treat Base64 as a security control.** HTTP-POST `SAMLResponse` is Base64-encoded XML; JWT headers/payloads are also readable. A bearer token that "looks like a random string" is still a replayable credential.

### Objectives After This Lesson

1. Classify data fields that **must never appear in logs**.
2. Understand how **Spring Security** `DEBUG`/`TRACE` differs from **JDK Kerberos/JAAS/JGSS** native debug output.
3. Design logs around **`event`/`outcome`/`reasonCode`/`requestId`** instead of dumping `Request`/`Authentication`/`Assertion`.
4. Apply HMAC pseudonymization when events must be linked per user without logging `NameID`/UPN.
5. Inspect **HTTP/proxy access logs, APM, stdout/stderr, and collectors**, not just Logback.
6. Enable debugging with scope/time windows, run synthetic canary tests, and handle incidents when a secret has already been logged.
7. Run a Java 17 example verifying field allowlists, token redaction, and CRLF log-injection protection.

## 2. Data Classification Table When Debugging Federation

| Category | Example Sources | Policy |
| --- | --- | --- |
| **Reusable secret** | `Authorization` Bearer/Basic/Negotiate, cookies, `JSESSIONID`, refresh token, `client_secret`, password | **Never log raw**, even at `DEBUG` |
| **SAML identity assertion** | `SAMLResponse`, `SAMLRequest`, Assertion, `NameID`, Attributes, `SessionIndex`, `RelayState` | Do not dump XML/Base64; log reason enum/IdP alias |
| **Kerberos credential** | AP-REQ/TGT/service ticket, keytab, ticket cache, session keys, GSS token | Do not print bytes, hex dumps, or keytab secrets |
| **Authentication keys** | SP/IdP private keys, signing secrets, keystore passwords, JAAS passwords | Do not log; use key alias/version |
| **Identity/PII** | Email, phone, UPN, principal, tenant/role, internal account ID | Minimize; HMAC-tag from **verified** principal per policy |
| **Session/correlation** | Cookie ID, `InResponseTo`, OAuth code, state, nonce, `code_verifier` | Do not log raw; use server-generated interaction ID |
| **Infrastructure metadata** | SPN/FQDN@REALM, KDC host, IdP entityID, X.509 fingerprint, secret mount path | Approved aliases only; limit topology details |
| **Raw HTTP input** | Header values, body, query string, user-agent, URL, exception message | Untrusted data; never pass directly to loggers |
| **Safe diagnostic** | `AUTH_DENIED`, `SIG_INVALID`, `NO_CRED`, HTTP 403, route template, duration bucket | Permitted under schema allowlist |

Some data **may be public in other contexts** (e.g., IdP metadata or X.509 public certs), yet that does not mean repeating it wholesale in logs. Log only what is genuinely needed to investigate.

**Partial token masking is not enough.** For tokens/cookies/keys, it is far better to **omit the value** or log only `[REDACTED]`/`present=true`. For low-entropy emails/user IDs, unkeyed SHA-256 can be reversed by dictionary attacks; keyed HMAC-SHA-256 is more appropriate for pseudonymization, while still requiring privacy and key governance.

## 3. Layered Log Protection Model

~~~text
HTTP/IdP/KDC request
       |
       v
Application / authentication libraries
  [A] No raw tokens / assertions / private keys in log calls
       |
       +--> SLF4J/Logback/Log4j2
       |
       +--> JVM Kerberos/JAAS/JGSS native stdout/stderr
       |
       v
Runtime / Ingress / Proxy / APM
  [B] No sensitive headers, bodies, full URLs or span attributes
       |
       v
Log agent / collector / queue
  [C] Secondary DLP/redaction, encrypted transport
       |
       v
SIEM / dashboards / alerts / archives / exports
  [D] RBAC, audit access, retention, backups, incident handling
~~~

**The primary line of defense is [A] — never emit raw credentials into logs.** Regex masking at the collector is only defense-in-depth because by that point the data may already have passed through console, files, stdout/stderr, or another alert queue.

**A Logback masking converter does not automatically cover:**

- JDK Kerberos/JAAS debug printing to `System.out`/`System.err` outside SLF4J.
- Tomcat/Undertow/Nginx/Envoy access logs.
- OpenTelemetry/APM request header capture and exception attachments.
- HTTP client wire logs or browser HARs/support bundles.
- File appenders or JSON appenders that do not share the converter.
- CI/test reports and crash diagnostics.

You cannot assess safety merely by opening one log file and grepping `Authorization`. You must inventory **every sink and copy**.

## 4. Spring Security: Enabling Targeted DEBUG/TRACE

Spring Security provides `DEBUG`/`TRACE` for `FilterChainProxy`, CSRF, authentication, authorization, and 401/403 handling. It is a useful diagnostic source, yet an application may have custom filters/principals that log extra PII.

### 4.1. Recommended Log Levels in Normal Environments

**src/main/resources/application.yml**

~~~yaml
logging:
  level:
    root: INFO
    org.springframework.security: WARN
    org.springframework.security.saml2: WARN
    org.springframework.security.kerberos: WARN
    org.opensaml: WARN
    net.shibboleth: WARN
    com.example.security.audit: INFO
~~~

**Note:** `org.opensaml` and `net.shibboleth` are reference logger namespaces depending on major version/dependencies; verify in actual runtime. `WARN` does not automatically sanitize messages emitted by other libraries/custom code.

### 4.2. Investigating 403 with Narrow Loggers

In staging or an approved diagnostic window:

~~~yaml
logging:
  level:
    root: INFO
    org.springframework.security: WARN
    org.springframework.security.web.FilterChainProxy: DEBUG
    org.springframework.security.web.access.ExceptionTranslationFilter: DEBUG
    org.opensaml: WARN
    net.shibboleth: WARN
~~~

- **`FilterChainProxy`** shows whether the request was handled by a security chain.
- **`ExceptionTranslationFilter`** helps trace authentication entry point/access denial flows depending on Spring Security version.
- Never enable all of **`org.springframework.security=TRACE`** for hours just to see why one route returns 403.
- When filter debug logs request paths, paths containing PII/path params still require review: never assume every URL is safe.
- Use app-controlled **reason codes** to distinguish `CSRF_DENIED`, `NO_AUTHENTICATION`, `MISSING_AUTHORITY`, or `LOCAL_USER_DISABLED`.

Spring Security documentation describes `DEBUG`/`TRACE` as diagnostics for filter invocations. **It is not a guarantee that `DEBUG` output is secret-free across every custom filter or extension**.

### 4.3. Never Log Full `Authentication` or `Principal`

~~~java
// Anti-pattern: toString() of custom objects may
// print principal attributes, details, or credentials.
log.debug("authentication={}",
    SecurityContextHolder.getContext().getAuthentication());
log.debug("principal={}", authentication.getPrincipal());
log.debug("headers={}", request.getHeader("Authorization"));
~~~

Some implementations try to mask credentials, yet you cannot assume **every** custom `Authentication`/principal/`toString` is redacted. XML claims, emails, roles, request details, or sensitive attributes can still appear.

**Alternative:**

~~~java
// Fragment: correlationId generated by trusted edge/app.
log.info("event={} outcome={} reason={} requestId={}",
    "AUTHORIZATION_DENIED", "DENY",
    "MISSING_REQUIRED_AUTHORITY", correlationId);
~~~

Even parameterized SLF4J **does not automatically redact**. If an argument is a raw `SAMLResponse`, token, or exception containing PII, it leaks just like string concatenation.

## 5. OpenSAML: `SAMLResponse` and `NameID` Are Sensitive Data

Spring Security SAML2 uses OpenSAML to process `SAMLResponse`/Assertions. Objects can hold `NameID`, Attributes, `SessionIndex`, `SignatureValue`, and parsed XML.

### 5.1. Objects to Avoid Logging

- Request parameter **`SAMLResponse`**; Base64 decodes straight to Assertion XML.
- **`SAMLRequest`**, `RelayState`, raw SAML metadata XML.
- **`Saml2Authentication.getSaml2Response()`** or objects holding XML/Response.
- **`Saml2AuthenticatedPrincipal.getAttributes()`** and full `NameID`/Attributes.
- Assertion XML, `SubjectConfirmationData`, `Conditions`, `SessionIndex`, `EncryptedAssertion`.
- Verbatim XMLDSig `SignedInfo`/`SignatureValue`, `KeyInfo`/`X509Data`.
- Raw `exception.getMessage()`, `toString()`, or cause chains if they carry XML or identity text.
- Full HTTP request dumps when SAML assertion validation fails.

**Trust principle:** `NameID`/`Issuer` inside an unverified `SAMLResponse` may be attacker-supplied. Never record them as `verifiedUser` in audits before signature/issuer/audience checks pass.

### 5.2. What to Log Instead of Payloads?

| Incident | Safe Event / `reasonCode` | Appropriate Metadata |
| --- | --- | --- |
| ACS receives POST | `SAML_ACS_RECEIVED` | `requestId`, approved registration alias |
| Malformed XML | `SAML_XML_REJECTED` | parser error category, byte-size bucket |
| Invalid signature | `SAML_SIGNATURE_INVALID` | trusted IdP alias, signer key version alias |
| Untrusted signing key | `SAML_UNTRUSTED_SIGNING_KEY` | configured trustset alias |
| Issuer mismatch | `SAML_ISSUER_MISMATCH` | expected IdP alias, not raw untrusted issuer |
| Wrong Audience/Recipient | `SAML_AUDIENCE_MISMATCH` | SP registration alias |
| Wrong Destination/ACS | `SAML_DESTINATION_INVALID` | route template |
| Assertion expired | `SAML_ASSERTION_EXPIRED` | clock skew bucket |
| InResponseTo mismatch | `SAML_REQUEST_CORRELATION_FAILED` | server interaction ID |
| Replay detected | `SAML_REPLAY_REJECTED` | replay policy code |
| User lacks local account | `SAML_LOCAL_ACCOUNT_DENIED` | verified `userTag` if present |
| Login success | `SAML_AUTHENTICATED` | verified `userTag`, IdP alias |

Example:

~~~json
{
  "timestamp": "2026-11-07T03:00:00Z",
  "service": "sso-sp",
  "event": "SAML_LOGIN_FAILED",
  "protocol": "SAML2",
  "outcome": "DENY",
  "reasonCode": "SIG_INVALID",
  "registrationAlias": "corp-idp",
  "requestId": "req-91ab",
  "userTag": null
}
~~~

**Never extract raw `Issuer` from a failed XML and place it into a trusted issuer field.** Log the expected registration alias and categorical failure, avoiding recording untrusted claims as fact.

### 5.3. Logging Categories and Legacy SAML Extensions

You may encounter loggers under **`org.opensaml`** and **`net.shibboleth`** depending on version. When debugging is needed, enable specific small classes/packages on staging and review sample output; never enable full `org.opensaml=TRACE` by default.

**Legacy warning:** Older Spring Security SAML Extension/OpenSAML setups had `SAMLDefaultLogger` and `logAllMessages`/`logMessagesOnException` options. Never copy those settings into Spring Security 6.x as if the API were equivalent; on legacy systems, enabling message dumping prints raw Assertion XML.

### 5.4. Failure Handler Without Leaking XML

~~~java
// Fragment inside HttpSecurity; requires logger bean/imports.
http.saml2Login(saml -> saml
    .failureHandler((request, response, exception) -> {
        // DO NOT call request.getParameter("SAMLResponse")
        // DO NOT log exception.getMessage() or toString()
        auditLogger.warn(
            "event={} outcome={} reason={}",
            "SAML_LOGIN_FAILED", "DENY", "VALIDATION_FAILED");
        response.sendRedirect("/login?error");
    }));
~~~

Production should map known provider errors to an **allowlisted enum** and never log raw throwables/causes without inspection. Failure handlers must never use request parameters to build a `Location` containing tokens/`RelayState`.

## 6. Kerberos/JAAS/JGSS: Native Debug Exists Outside Logback

JDK Kerberos/Java GSS-API has debug flags whose behavior varies by version:

~~~text
-Dsun.security.krb5.debug=true
-Dsun.security.jgss.debug=true
-Dsun.security.spnego.debug=true
-Djava.security.debug=all
-Djavax.net.debug=all
~~~

JAAS **`Krb5LoginModule`** also has **`debug=true`**. Some Spring Security Kerberos versions have **`SunJaasKerberosTicketValidator.setDebug(true)`**. **These are high-risk options, never permanent production settings.** Oracle warns that security debug output can contain sensitive information. Verify support and output on the exact JDK version in use.

### 6.1. Why Configuring Logback Alone Is Not Enough?

JDK/JAAS/JGSS can write directly to **`System.out`/`System.err`**. Therefore:

- `logging.level.org.springframework.security=OFF` does not guarantee JDK Kerberos debugging is off.
- Logback `%replace` converters/JSON encoders may not intercept these native JDK lines.
- Container runtimes, `kubectl logs`, and log agents still capture raw stdout/stderr.
- JVM startup flags, environment/process inspection, and support bundles can also expose KDC addresses, principals, or secret paths.

**Policy:** Turn off native debug at the source. If truly needed, use a **test Kerberos realm, service account, and separate keytab** in an isolated process that does not ship to production SIEM.

### 6.2. What Must Never Be Printed from Kerberos?

| Source | Raw Data Prohibited | Replace With |
| --- | --- | --- |
| `Authorization: Negotiate` | GSS/SPNEGO AP-REQ token | `SPNEGO present=true` |
| TGT, ticket cache | Ticket bytes/credential keys | `cacheAvailable` bool |
| Keytab | Secret key bytes, keytab dump | `keytabReadable` bool, rotation alias |
| JAAS Subject/GSSContext | Credentials, ticket objects | auth outcome enum |
| User principal/UPN | `alice@REALM` and employee identity | HMAC `userTag` after validation |
| Service principal | `HTTP/FQDN@REALM` if exposing topology | approved SPN alias |
| `GSSException` | Full message/stack if containing identity | GSS major status enum |
| KDC/realm/path | Internal network and secret mount path | safe realm/service alias |
| Session key/enctype dump | Key material | enctype category when permitted |

Specifically: inspecting keytab metadata via admin tools may use **`klist -k -e`** in an authorized environment, yet **never `-K`** because that prints key material. Never upload keytabs, ticket caches, or raw Kerberos traces to issues/chat.

### 6.3. Example Classifying `GSSException`

~~~java
// Fragment: GSSException from org.ietf.jgss.
// Token accept code provided by the Kerberos library.
try {
    // performKerberosAccept(...); // actual library call
} catch (GSSException ex) {
    String reason = switch (ex.getMajor()) {
        case GSSException.NO_CRED -> "GSS_NO_CRED";
        case GSSException.DEFECTIVE_TOKEN -> "GSS_DEFECTIVE_TOKEN";
        case GSSException.BAD_MIC -> "GSS_BAD_MIC";
        default -> "GSS_FAILURE";
    };
    auditLogger.warn("event={} reason={}",
        "KERBEROS_TICKET_REJECTED", reason);
    // Fail closed; do not grant access when validation fails.
}
~~~

This is a **fragment**, not a standalone compiled class: Kerberos accept and logger configuration come from the app. Never log `ex.toString()`, `ex.getMessage()`, raw `ticket byte[]`, or JAAS `Subject`. Specific causes like unreadable keytab, wrong KVNO, or clock skew should be safely mapped at the right layer.

### 6.4. Safe Kerberos Diagnostics

1. Check whether HTTP 401 includes `WWW-Authenticate: Negotiate` (do **not** log `Authorization` tokens).
2. Reconcile SPN alias, `keytabReadable`, KDC reachability, clock/NTP, and DNS/realm config.
3. Log GSS error category rather than raw tokens or exceptions.
4. If the validator succeeds yet the request gets 403, inspect local `UserDetailsService`/roles rather than assuming GSS broke.
5. Deep debugging belongs strictly in a lab/test realm with test keytabs and isolated stdout/stderr.
6. Disable JVM/JAAS flags after testing and verify the live runtime.

## 7. Leak Paths Outside Spring Security Loggers

Do not look only at Java log statements. An SSO environment can leak at:

- **`CommonsRequestLoggingFilter`** when `includePayload`, `includeHeaders`, or `includeQueryString` is enabled.
- Custom Servlet filters/interceptors/response wrappers logging full requests/responses.
- Nginx/Envoy/Tomcat access logs recording full URIs containing OAuth `code`, `state`, `RelayState`.
- HTTP client wire logs, Reactor Netty, Apache HttpClient/OkHttp interceptors.
- APM/OpenTelemetry traces capturing `url.full`, `enduser.id`, `http.request.header.authorization`, `exception.message`.
- Sentry/error reporters capturing request context/stacktraces containing PII.
- MDC containing email, principal, session ID, `Cookie`, or `SAMLResponse`.
- CI runners, HAR/browser traces, crash dumps, support bundles, container stdout/stderr, and alert attachments.

### RequestLoggingFilter Must Restrict Payloads/Headers

~~~java
// Spring Boot web app fragment.
CommonsRequestLoggingFilter filter =
    new CommonsRequestLoggingFilter();
filter.setIncludeHeaders(false);
filter.setIncludePayload(false);
filter.setIncludeQueryString(false);
filter.setIncludeClientInfo(false);
filter.setMaxPayloadLength(0);
~~~

This configuration **does not mask logs at proxies/APM/JDK**. Never log raw request bodies or queries on ACS, OIDC callback, login, logout, and token endpoints; apply the same policy to business APIs carrying Bearer tokens/Cookies.

URL paths can contain emails/PII; prefer **route templates** (`/api/orders/{id}`) over full URLs.

### Regex Masking and JSON Encoders Are Incomplete Solutions

Regex easily misses tokens inside Base64, URL encoding, multiline XML, nested JSON fields, repeated headers, exception causes, split/truncated tokens, or differently named custom headers. A structured JSON encoder may escape CRLF yet **still print raw secrets** if the event includes them.

**Prioritize source-level field allowlists**; collector DLP/regex only supplements to reduce risk from third-party outputs, and must be tested across encodings.

## 8. Safe Security Audit Event: Only Meaningful Fields

A minimal security event can include:

| Field | Source | Policy |
| --- | --- | --- |
| `timestamp` | Server UTC | Permitted |
| `service` | Deployment alias | Never taken from untrusted `Host` header |
| `requestId` | Server-generated/normalized ingress | Bounded length, contains no credentials |
| `event` | Enum | `SAML_LOGIN_FAILED`, `ACCESS_DENIED` |
| `protocol` | Enum | `SAML2`, `OIDC`, `KERBEROS`, `SPRING_SECURITY` |
| `outcome` | Enum | `SUCCESS`, `DENY`, `ERROR` |
| `reasonCode` | Enum | `SIG_INVALID`, `NO_CRED`, `ISSUER_MISMATCH` |
| `registrationAlias` | Config allowlist | Never raw untrusted Issuer |
| `userTag` | HMAC pseudonym | Only after successful authentication |
| `httpStatus` | 302, 401, 403... | Permitted |
| `durationBucket` | Time bucket | No raw payload |
| `routeTemplate` | App configuration | Avoids raw URL/PII |

No free-form `details` field accepting XML/headers/exception messages.

~~~json
{
  "timestamp": "2026-11-07T03:00:00Z",
  "service": "sso-sp",
  "requestId": "req-56a1",
  "event": "SAML_LOGIN_FAILED",
  "protocol": "SAML2",
  "outcome": "DENY",
  "reasonCode": "SIG_INVALID",
  "registrationAlias": "corp-idp",
  "userTag": null,
  "httpStatus": 401
}
~~~

### SLF4J Application Code

~~~java
// Fragment inside Spring Boot, logger already declared:
auditLogger.warn(
    "event={} protocol={} outcome={} reason={} requestId={}",
    "SAML_LOGIN_FAILED", "SAML2", "DENY",
    "SIG_INVALID", safeServerGeneratedRequestId);
~~~

**Never pass an exception as the final argument** without evaluating it: SLF4J prints the `Throwable`/stacktrace, including messages carrying tokens, XML, or internal paths.

## 9. Runnable Java 17: HMAC Pseudonymization and Field Allowlisting

The exercise below uses **pure JDK 17**, needing no Spring, OpenSAML, IdP, or KDC. It demonstrates:

- Only `event`, `outcome`, `reason`, `requestId`, and `userTag` are permitted into the log line.
- Raw `Authorization`/Bearer, `SAMLResponse`, and `Cookie` are dropped when building the event.
- User ID is pseudonymized with HMAC-SHA-256 (12 digest bytes → 24 hex chars).
- CRLF/tabs/control chars in `requestId` become underscores, with bounded length.
- Output prints only boolean assertions, never the actual `userTag`.

**File: `SafeSecurityLogDemo.java`**

~~~java
import java.nio.charset.StandardCharsets;
import java.security.GeneralSecurityException;
import java.util.HexFormat;
import java.util.Map;
import java.util.Set;
import javax.crypto.Mac;
import javax.crypto.spec.SecretKeySpec;

public final class SafeSecurityLogDemo {

    private static final Set<String> ALLOWED =
        Set.of("event", "outcome", "reason", "requestId", "userTag");

    // DEMO key; never use in production.
    private static final byte[] TEST_KEY =
        "demo-not-a-production-secret"
            .getBytes(StandardCharsets.UTF_8);

    static String tag(String user, byte[] key)
            throws GeneralSecurityException {
        Mac mac = Mac.getInstance("HmacSHA256");
        mac.init(new SecretKeySpec(key, "HmacSHA256"));
        byte[] digest =
            mac.doFinal(user.getBytes(StandardCharsets.UTF_8));
        return HexFormat.of().formatHex(digest, 0, 12);
    }

    static String safeValue(String value) {
        if (value == null) {
            return "-";
        }
        StringBuilder out = new StringBuilder();
        for (int i = 0; i < value.length()
                && out.length() < 80; i++) {
            char c = value.charAt(i);
            if (Character.isISOControl(c)
                    || c == '\u2028' || c == '\u2029') {
                out.append('_');
            } else {
                out.append(c);
            }
        }
        return out.toString();
    }

    static String event(Map<String, String> input) {
        StringBuilder out = new StringBuilder();
        String[] keys =
            {"event", "outcome", "reason", "requestId", "userTag"};
        for (String key : keys) {
            if (!ALLOWED.contains(key)) {
                continue;
            }
            if (out.length() > 0) {
                out.append(' ');
            }
            out.append(key).append('=')
                .append(safeValue(input.get(key)));
        }
        return out.toString();
    }

    public static void main(String[] args)
            throws GeneralSecurityException {
        String user = "alice@example.test";
        String bearer = "fake-bearer-never-log";
        String saml = "fake-saml-never-log";
        String cookie = "fake-cookie-never-log";

        String a = tag(user, TEST_KEY);
        String same = tag(user, TEST_KEY);
        String b = tag("bob@example.test", TEST_KEY);

        Map<String, String> fields = Map.of(
            "event", "SAML_LOGIN_FAILED",
            "outcome", "DENY",
            "reason", "SIG_INVALID",
            "requestId", "req-001\nspoofed=admin",
            "userTag", a,
            "Authorization", bearer,
            "SAMLResponse", saml,
            "Cookie", cookie);

        String line = event(fields);

        System.out.println("stableTag=" + a.equals(same));
        System.out.println("differentUsers=" + !a.equals(b));
        System.out.println("hasRawUser=" + line.contains(user));
        System.out.println("hasBearer=" + line.contains(bearer));
        System.out.println("hasSaml=" + line.contains(saml));
        System.out.println("hasCookie=" + line.contains(cookie));
        System.out.println("hasNewline=" + line.contains("\n"));
        System.out.println("safeRequestId=" +
            line.contains("requestId=req-001_spoofed=admin"));
    }
}
~~~

Compile and run:

~~~bash
javac SafeSecurityLogDemo.java
java SafeSecurityLogDemo
~~~

**Exact stdout per Java 17 logic:**

~~~text
stableTag=true
differentUsers=true
hasRawUser=false
hasBearer=false
hasSaml=false
hasCookie=false
hasNewline=false
safeRequestId=true
~~~

**Explanation:** HMAC generates a stable tag for the same user/key and distinct tags for two users with very high probability; non-allowlisted fields are dropped; CR/LF become `_` so forged log lines cannot be injected.

**Limitations:** This is an illustrative event builder, not a Logback plugin, and does not inspect HTTP/native JVM logs. Production must load the HMAC key from a secret manager/KMS (never hardcode), enforce rotation/ACLs, and scope by environment/tenant. `userTag` can still qualify as pseudonymous personal data; never treat HMAC as absolute anonymity. `event`/`outcome`/`reason` in real systems should be server-selected enums, never client-supplied strings. `requestId` is best server-generated; sanitization is an extra layer.

## 10. MDC and Distributed Tracing

MDC helps correlate events within one request. Never place session IDs, raw principals, emails, or `Authorization` into MDC: every appender/trace exporter can record those fields.

~~~java
import org.slf4j.MDC;

// Fragment: serverRequestId generated by trusted edge/server.
try (MDC.MDCCloseable scope =
        MDC.putCloseable("requestId", serverRequestId)) {
    filterChain.doFilter(request, response);
}
~~~

You must clear MDC in `finally`/try-with-resources to prevent one request's data from bleeding into the next request on a thread pool. Async/reactive or virtual threads need proper context propagation; never assume MDC automatically follows across threads.

**Anti-pattern:**

~~~java
MDC.put("Authorization", request.getHeader("Authorization"));
MDC.put("sessionId", request.getSession().getId());
MDC.put("username", authentication.getName());
MDC.put("saml", request.getParameter("SAMLResponse"));
~~~

APM tracing follows the same rules: avoid span attributes like raw full URLs, sensitive headers, XML bodies, or `exception.message` if they carry PII. A JSON encoder only escapes output; **it does not redact contents**.

## 11. Time-Boxed Debugging and Rollback

### Before Enabling

1. Define the question: FilterChain match? SAML signature/Issuer? Kerberos keytab? Clock skew? `UserDetailsService`?
2. Have a ticket/owner, approval, logger category, environment, pod count, end time, and rollback plan.
3. Prefer staging and a **test IdP/test Kerberos realm** with fake credentials/`NameID`.
4. Check every destination: console, stdout/stderr, file appenders, proxy access logs, APM, collectors/SIEM/alerts.
5. Run synthetic canaries to confirm no tokens/XML/UPN leak.
6. Enable only narrow loggers at the lowest needed `DEBUG` level; never reflexively turn on all/`TRACE`.
7. Verify RBAC/retention/exports and who can read logs during the debug window.

### While Enabled

- Scope strictly to target workload/pods; monitor log volume, CPU/disk, and event categories.
- Correlate with `requestId`, never print raw `InResponseTo`/session keys.
- If a credential appears in stdout/stderr/collectors, halt collection immediately and assess the incident.
- Never paste HARs/debug bundles containing raw tokens into unauthorized issues/chat/email.

### Afterward

1. Lower logger levels; turn off JVM `krb5`/`jgss`/`spnego` flags and JAAS `debug=true` (may require JVM restart).
2. Verify the **live runtime config** actually returned to safe levels, not just YAML/Git.
3. Verify new logs contain no canaries while safe audit events still emit.
4. Review older copies across agents, SIEM, alerts, queues, backups, and exports.
5. If a leak occurred, revoke/rotate per scope and audit who accessed the logs.
6. Write a safe incident summary and add regression tests/deployment guardrails.

**Turning off `DEBUG` does not erase credentials already written into old logs.**

## 12. Diagnosing Without Raw Tokens

### 12.1. SAML2 Login Failures

- Check ACS endpoint and approved registration alias without printing `SAMLResponse`.
- Inspect reason codes: `XML_MALFORMED`, `SIG_INVALID`, `UNTRUSTED_KEY`, `ISSUER_MISMATCH`, `AUDIENCE_MISMATCH`, `DESTINATION_INVALID`, `ASSERTION_EXPIRED`, `CORRELATION_FAILED`, `REPLAY_REJECTED`.
- Check SP EntityID/ACS URL, trusted IdP signing key alias, timestamps, and local user mapping.
- If signature verification fails, **never trust `NameID` in the XML as an authenticated user**.
- Reproduce with signed synthetic fixtures in staging rather than printing real users' Assertions.

### 12.2. Kerberos Negotiate 401

- Check `WWW-Authenticate: Negotiate`, logging presence only and never the `Authorization` token.
- Check service principal alias, `keytabReadable`, and KVNO/enctype metadata via approved admin channels.
- Check DNS/KDC/clock/skew, browser trusted-site policies, and GSS major status.
- Distinguish ticket validation failures from local account/role denials.
- Run native JDK debug only in a lab with a test realm/keytab and isolated stdout/stderr.

### 12.3. Spring Security 403

- Check security chain, CSRF vs. unauthenticated vs. missing authority.
- Log route template, method, event, reason enum, status, and `requestId`.
- If the principal is verified, you may log an HMAC `userTag` per policy.
- Never log raw `SecurityContext`/`Authentication`/session/CSRF tokens.
- On tenant/resource denials, check business policy without printing sensitive object data.

## 13. Testing Against Leaks Across Every Sink

Use **only fake secrets/canaries** in staging/testing; never place real tokens/keytabs into tests.

| # | Test | Expectation |
| --- | --- | --- |
| 1 | Fake `Authorization: Bearer` token | Never logged raw |
| 2 | Fake `Authorization: Negotiate` GSS token | Never logged raw |
| 3 | Fake Basic auth base64 | Never logged raw |
| 4 | Fake `Cookie: JSESSIONID` | Never logged raw |
| 5 | `Set-Cookie` session response | Never logged raw |
| 6 | Base64 `SAMLResponse` with fake `NameID` | No raw XML/Base64 |
| 7 | Fake `SAMLRequest` and `RelayState` | Never raw |
| 8 | `EncryptedAssertion`/`SignatureValue` | Never dumped |
| 9 | OIDC `access_token`/`id_token`/`refresh_token` | Never logged raw |
| 10 | OAuth `state`/`code`/`code_verifier` | Never logged raw in queries |
| 11 | CSRF 403 | Reason enum logged, no CSRF token |
| 12 | Custom `Authentication.toString` | No attributes/credentials dumped |
| 13 | Invalid SAML signature | `SIG_INVALID`, no raw assertion |
| 14 | Wrong Issuer from untrusted XML | Never log raw received issuer as trusted |
| 15 | SAML fails before validation | `userTag` null |
| 16 | Kerberos `GSS_NO_CRED` | Log code, no ticket |
| 17 | Unreadable keytab | Log boolean/alias, no secret |
| 18 | Native `krb5` debug in test realm | Inspect stdout/stderr |
| 19 | Narrow Spring Security `DEBUG` logger | No fake secrets appear |
| 20 | `CommonsRequestLoggingFilter` | Excludes headers/body/query |
| 21 | Nginx/Tomcat/Envoy access logs | No full URL queries with code/tokens |
| 22 | HTTP client wire logging | Never dumps auth headers |
| 23 | APM/OTel spans | Contain no PII/tokens/sessions |
| 24 | MDC with fake token | Dropped from logging schema |
| 25 | CRLF in `requestId` | No log injection |
| 26 | Nested JSON secret | Never slips past encoder/collector |
| 27 | Exception message containing fake token | Never print raw message/stack |
| 28 | Oversized user input | Bounded; no log DoS |
| 29 | HMAC same user | Stable pseudonym |
| 30 | HMAC different users | Distinct tags with overwhelming probability |
| 31 | HMAC key rotation | Key never exposed, properly scoped |
| 32 | Async/multiple appenders | Policy enforced across all sinks |
| 33 | SIEM alerts/exports/backups | Contain no raw canary |
| 34 | Debug expiry | `TRACE`/JVM flags verified disabled |
| 35 | Log RBAC/retention | Proper TTL and permissions |
| 36 | Audit events at reduced log level | Safe events still present |

**Testing procedure:**

1. Create canary tokens and XML with fake data, testing raw/Base64/URL-encoded/JSON-escaped forms.
2. Send through success and failure paths of SAML2/OIDC/Kerberos test endpoints.
3. Capture stdout, stderr, Logback console/files, proxy access logs, APM spans, collector queues, SIEM test indices, and alert payloads.
4. Assert no canary—encoded or decoded—appears in any sink.
5. Assert safe audit events still appear: `event`/`outcome`/`reasonCode`/`requestId`.
6. Verify RBAC, retention, alert exports, and backups per policy.
7. Re-run after upgrading JDK/OpenSAML/Spring Security/Logback or adding new filters.

**Completely empty logs are not a QA PASS**, because missing security audit events can blind attack detection.

## 14. Incident Response If Secrets Were Already Logged

When production has logged `Authorization`, session cookies, SAML XML, or Kerberos credentials:

1. **Stop new leaks at the source:** turn off raw logging/native debug and roll back config.
2. **Isolate sinks:** restrict viewers/exports, locate app logs, stdout, collectors, SIEM, alert attachments, and backups.
3. Classify exposure: reusable tokens/sessions, SAML PII, Kerberos tickets, keytabs/private keys.
4. Revoke/expire sessions/tokens or rotate service credentials/keytabs/keys per exposure scope and threat model.
5. Audit log access and assess privacy/legal notification obligations.
6. Never re-paste raw tokens/PII into incident reports; use safe correlation IDs.
7. Fix code/log policies, update CI canary tests, and enforce debug expiry/approvals.
8. Monitor for credential reuse or anomalous activity.

**Encryption at rest only protects log storage, not source-level minimization.** Anyone authorized to query/export logs still sees raw secrets if the app wrote them.

## 15. Common Mistakes

| Mistake | Why It Is Wrong | Resolution |
| --- | --- | --- |
| Default `TRACE` on Spring Security in prod | Excessive data/volume/PII | Narrow loggers and time windows |
| Treating Base64 `SAMLResponse` as harmless | Decodes straight to XML/`NameID` | Never log body/params |
| Assuming one Logback regex masks everything | JDK stderr/proxies/APM sit outside the converter | Source-level allowlists + multi-sink tests |
| Assuming JSON logs auto-redact | JSON still serializes tokens | Schema allowlist |
| Assuming `Authentication.toString` is always safe | Custom principals/details can leak | Event/outcome/verified tag |
| Unsalted SHA-256 of email | Vulnerable to dictionary attacks | Keyed HMAC or do not log |
| Dumping full exceptions to debug faster | Raw messages carry XML/PII/file paths | Safe error enums |
| Assuming Kerberos debug is an SLF4J logger | JDK writes native stdout/stderr | Disable JVM/JAAS flags |
| Skipping redaction for internal SIEM logs | Multiple viewers/exports/backups | RBAC, minimization, TTL |
| Thinking turning off debug deletes leaks | Old copies still persist | Incident response + revoke/rotate |
| Treating Issuer in failed SAML as verified identity | Has not passed trust validation | Log configured alias/reason |
| Putting session ID in MDC for easier searching | Credentials can leak | Server `requestId` or HMAC per policy |

## 16. Production Checklist

- [ ] Inventoried all data flows: Spring/SLF4J, JVM stdout/stderr, reverse proxy, APM, collector, SIEM.
- [ ] Never log raw `Authorization` Bearer/Basic/Negotiate, Cookies/`JSESSIONID`, or access/refresh/ID tokens.
- [ ] Never log raw `SAMLResponse`/`SAMLRequest`, XML Assertions, `NameID`, Attributes, `RelayState`, or `SessionIndex`.
- [ ] Never log Kerberos AP-REQ/TGT/ticket caches, keytabs/private keys, `GSSContext`, JAAS `Subject`, or session keys.
- [ ] Never log raw `Authentication`/`Principal`/`Saml2Authentication` or unreviewed exception messages.
- [ ] Spring Security and OpenSAML logger levels kept low; `DEBUG` restricted to narrow classes/packages when approved.
- [ ] JDK `krb5`/`jgss`/`spnego.debug` and `Krb5LoginModule debug=true` never left enabled permanently.
- [ ] Native Kerberos console/stdout/stderr tested separately from Logback.
- [ ] HTTP access logs, `CommonsRequestLoggingFilter`, APM/OTel, and HTTP clients never auto-dump auth headers/bodies/queries.
- [ ] Log only safe event enums, outcomes, `reasonCode`, approved registration aliases, route templates, and `requestId`.
- [ ] `userTag` derived only from verified principals via keyed HMAC under privacy/key lifecycle governance.
- [ ] MDC/trace attributes contain no tokens, emails, session IDs, or XML.
- [ ] CRLF/control chars and lengths of untrusted fields bounded; log injection blocked.
- [ ] JSON/Logback regexes are supplemental only, never replacing source minimization.
- [ ] Log storage enforces encryption, RBAC, export audits, retention/deletion, and backup controls.
- [ ] Debug tickets have scope, owner, expiry, rollback, and verified runtime deactivation.
- [ ] Canary leak tests run across console/files/stdout/stderr/proxy/APM/collector/SIEM.
- [ ] Safe security events remain emitted even without raw payloads.
- [ ] Incident response plan covers revoking/rotating if logs ever capture secrets.
- [ ] After upgrading frameworks/JDK/loggers, regression tests run before production.

**Conclusion:** Enabling `DEBUG`/`TRACE` for Spring Security, OpenSAML, or Kerberos **widens the access surface for authentication data**, rather than merely adding log lines. Preserve diagnostic value through **typed security events, reason codes, `requestId`, and verified HMAC `userTag`**, while avoiding emitting raw credentials/Assertions/keytabs into logs in the first place. Inspect JVM native debug, proxies, APM, and SIEM as well, time-box debugging, and treat leaks through incident response. No single regex or JSON encoder can guarantee secrecy.

## 17. References

- [Spring Security – Servlet Architecture / Logging](https://docs.spring.io/spring-security/reference/servlet/architecture.html): filter chain `DEBUG`/`TRACE` and 401/403 diagnostics.
- [Spring Security – Authenticating SAML2 Responses](https://docs.spring.io/spring-security/reference/servlet/saml2/login/authentication.html): OpenSAML/`Saml2Authentication` flow and `SAMLResponse` handling.
- [Spring Boot 3.5 – Logging](https://docs.spring.io/spring-boot/3.5/how-to/logging.html): `logging.level`, Logback/`logback-spring.xml`.
- [Oracle Java 17 – Troubleshooting Security](https://docs.oracle.com/en/java/javase/17/security/troubleshooting-security.html): Java security debug flags.
- [Oracle JGSS Debugging Guide](https://docs.oracle.com/en/java/javase/24/security/troubleshooting-security.html): Kerberos/JGSS/JAAS debug and cautions, verify runtime version.
- [OWASP Logging Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Logging_Cheat_Sheet.html): sensitive data to exclude, log injection, and event schemas.
- [OWASP Session Management Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Session_Management_Cheat_Sheet.html): avoid logging raw session IDs, correlation.
- [OWASP Authentication Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Authentication_Cheat_Sheet.html): authentication failures/privacy.
- [SLF4J Manual](https://www.slf4j.org/manual.html): SLF4J APIs, MDC.
- [Java 17 javax.crypto.Mac API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/javax/crypto/Mac.html): `HmacSHA256` pseudonymous tagging.