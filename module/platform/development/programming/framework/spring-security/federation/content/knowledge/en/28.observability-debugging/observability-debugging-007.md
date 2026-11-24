# Diagnosing Time, Time Zone, and Clock Skew Errors in Spring Security Federation

## 1. Real-World Problem and Target Outcomes

A Spring Security federated login system can intermittently reject a **SAML 2.0 Assertion**, **OIDC ID Token**, **OAuth 2.0 Access Token**, **CAS ticket**, or session even when signatures, issuers, and URL configurations look right. Failures often appear only on certain pods, around daylight saving transitions, right after token issuance, or near expiration. Messages may say `Assertion is not yet valid`, `Assertion has expired`, `Jwt expired`, `nbf is in the future`, `invalid_grant`, session state/authorization request expired, or certificate not yet valid.

There are at least **four independent causes** to distinguish:

1. **A node's physical clock is wrong**: the IdP thinks the current time is 10:00:50 while the Spring SP sees 10:00:00; every time condition shifts.
2. **Wrong display or parsing time zone**: the same `Instant` renders differently in UTC vs. Vietnam time; or code drops the offset when parsing, shifting comparisons by exact hours.
3. **The valid lifetime genuinely elapsed**: the assertion, token, or ticket truly expired, or a login/browser session took too long; an accurate clock must still reject it.
4. **Wrong or inconsistent clock skew policy**: one service allows 30 seconds of skew while another allows 0 seconds; sometimes expired tokens are accepted too long due to overly wide skew.

This lesson belongs to the **Observability and debugging** group of the **Spring Security - federation** module. The goal is to pinpoint the right failure layer, measure actual drift, analyze `NotBefore`/`NotOnOrAfter` and `nbf`/`exp` bounds, read logs safely, configure Spring validators, write deterministic time-pinned tests in **Java 17**, and fix **the root time-synchronization cause** instead of disabling validation.

**Safety rule:** Clock skew (*leeway*) is a small tolerance for distributed clocks, **not** a way to permit assertions/tokens expired by hours. Never use `permitAll()`, disable signatures, drop audience/recipient checks, or set infinite skew to "fix" time errors.

## 2. Three Concepts Frequently Conflated

| Concept | Definition | Example | When Does It Actually Cause Failures? |
| --- | --- | --- | --- |
| **Instant / absolute point in time** | A single point on the timeline, typically in UTC | `2026-11-07T03:00:00Z` | Source/target clock measures the current instant wrongly |
| **Time zone** | Rules converting an Instant to civil date/time, including DST if any | `Asia/Ho_Chi_Minh` or `Europe/Berlin` | Code parses/compares local time as an absolute instant |
| **UTC offset** | Hour offset at a specific instant, formatted like `+07:00` | `2026-11-07T10:00:00+07:00` | Code strips the offset or attaches the wrong offset |
| **Clock skew** | Difference between source and validator clocks at the same real instant | SP is 45 seconds ahead of IdP | Artifact is seen as "not yet valid" or "already expired" |
| **Latency** | Time spent in network, browser redirects, IdP processing, and queues | SAML POST takes 5 seconds | Short-lived timestamp expires before validation |
| **Validity window** | Interval during which an assertion/token is accepted | `[NotBefore, NotOnOrAfter)` | Request arrives outside the allowed window |
| **TTL** | Lifetime set by the issuer/service | 5-minute token | Token genuinely expires or is replayed |
| **Clock skew allowance** | Validator tolerance for small differences | `Duration.ofSeconds(60)` | Overly wide setting enlarges the replay window |

Another crucial point: **changing the JVM timezone does not make the clock run faster or slower**. If `Instant.now()` on the node is still accurate, `Europe/Berlin` and `Asia/Ho_Chi_Minh` only change **how time is displayed**. If code converts `LocalDateTime` into `Instant` using the default timezone, changing the timezone can make **application logic wrong**; that is a parse/mapping bug, not proof that NTP is broken.

### Illustrating the Same Point in Time

~~~text
UTC:
  2026-11-07T03:00:00Z

Vietnam time (UTC+07):
  2026-11-07T10:00:00+07:00

Both represent exactly the SAME Instant.

Wrong interpretation:
  parse 2026-11-07T10:00:00 as UTC
  => shifts the actual instant forward by 7 hours
~~~

For formats with `Z` or `+07:00`, parse into `Instant` or `OffsetDateTime` and compare on the timeline; never compare local-time strings against ISO UTC or dashboard displays.

## 3. Which Clocks Participate in a Federation Flow?

~~~mermaid
sequenceDiagram
    participant B as Browser
    participant I as IdP clock
    participant P as Proxy/load balancer
    participant S as Spring SP clock
    participant R as Resource Server clock
    B->>I: SSO login
    I->>I: IssueInstant, NotBefore, NotOnOrAfter
    I-->>B: SAMLResponse or OIDC authorization code
    B->>P: Redirect/POST callback
    P->>S: Forward request
    S->>S: Check signature/issuer, then validity at current time
    S-->>B: Session or failure
    opt API Access Token later
        B->>R: Authorization: Bearer token
        R->>R: Check exp/nbf and local clock
        R-->>B: 200 or 401
    end
~~~

Clocks worth paying attention to:

- **IdP/Authorization Server** emits timestamps in Assertions, ID Tokens, and Access Tokens, and creates sessions/tickets.
- **Spring Service Provider/Relying Party** reads current time to evaluate conditions from the IdP.
- **API Resource Server** may be a separate system with its own clock, validating JWT `exp`/`nbf`.
- **CAS Server** typically manages ticket lifetimes server-side; a `CAS Service Ticket` does not necessarily carry SAML-style `NotOnOrAfter`.
- **Reverse proxy/WAF** logs request times and may add queuing/caching/latency; the proxy itself does not necessarily validate Assertions.
- **Browser** has a local clock for JS/cookies/UX, yet **server-side SAML SP** and **JWT Resource Server** must never trust the browser clock for access decisions; cookie/session behavior may still be affected client-side.
- **Container/VM node**: `TZ`/`-Duser.timezone` governs display, while the system clock comes from the kernel/infrastructure; do not assume each container has an independent hardware clock.

**Do not check only the developer machine's clock.** In Kubernetes, IdP and SP worker nodes/pods can span multiple hosts; one node off by 90 seconds creates intermittent "pod A PASS, pod B FAIL" bugs even though both run identical code and config.

## 4. SAML 2.0: NotBefore and NotOnOrAfter

In SAML Core, `<saml:Conditions>` can contain:

~~~xml
<saml:Conditions
    NotBefore="2026-11-07T03:00:00Z"
    NotOnOrAfter="2026-11-07T03:05:00Z">
  <saml:AudienceRestriction>
    <saml:Audience>https://sp.example/metadata</saml:Audience>
  </saml:AudienceRestriction>
</saml:Conditions>
~~~

**Not a complete Assertion**: the example omits XML Signature, issuer, subject, subject confirmation, and other fields.

Time semantics of Conditions:

- **`NotBefore`:** do not accept the Assertion **before** this instant; at the exact start instant it is valid if all other conditions hold.
- **`NotOnOrAfter`:** do not accept the Assertion **on or after** this instant; at the exact end instant it is already expired.
- The validity interval under a zero-skew model is **`[NotBefore, NotOnOrAfter)`**, i.e., **inclusive** start, **exclusive** end.
- Time attributes may be absent depending on profile and validator; never infer "missing expiration = unlimited acceptance". The application/IdP contract must still enforce freshness, subject confirmation, and replay limits.
- Never edit XML timestamps signed by the IdP and expect the signature to stay valid.

### Zero-Skew SAML Boundary Table

| SP Current UTC Time | NotBefore | NotOnOrAfter | Conclusion Considering Conditions Alone |
| --- | --- | --- | --- |
| 02:59:59 | 03:00:00 | 03:05:00 | **Not yet valid** |
| 03:00:00 | 03:00:00 | 03:05:00 | Valid at start boundary |
| 03:04:59 | 03:00:00 | 03:05:00 | Valid inside window |
| 03:05:00 | 03:00:00 | 03:05:00 | **Expired** |
| 03:05:01 | 03:00:00 | 03:05:00 | **Expired** |

All times in the table are on the same UTC date purely to clarify boundaries; a real SAML response must still pass signature, issuer, audience, recipient, subject confirmation, and correlation/replay checks.

### SubjectConfirmationData Has Its Own Window

In Web Browser SSO, a bearer `<saml:SubjectConfirmationData>` can carry `Recipient`, `InResponseTo`, and `NotOnOrAfter`:

~~~xml
<saml:SubjectConfirmation Method=
    "urn:oasis:names:tc:SAML:2.0:cm:bearer">
  <saml:SubjectConfirmationData
      InResponseTo="_authn-request-test-01"
      Recipient="https://sp.example/login/saml2/sso/corp"
      NotOnOrAfter="2026-11-07T03:02:00Z"/>
</saml:SubjectConfirmation>
~~~

**Tighter bound wins**: even if Conditions remain valid until 03:05, if bearer SubjectConfirmationData expires at 03:02, a Response arriving at 03:03 must be rejected by the subject confirmation validator. Never check Conditions alone and assume SAML login is valid.

You must also check `Recipient`, `InResponseTo` per SP-initiated flow, the exact subject confirmation method, issuer, audience, and request correlation. If the IdP allows IdP-initiated SSO, the `InResponseTo`/response correlation policy differs from SP-initiated; never relax it freely without a trust model.

## 5. IssueInstant Is Not NotOnOrAfter

SAML Response and Assertion can carry `IssueInstant`. This is **when it was issued**, not the start/end of bearer confirmation validity. Some validators/profiles enforce freshness limits on `IssueInstant` or response age; do not confuse it with `NotBefore` or `NotOnOrAfter`.

Example:

~~~text
Response IssueInstant:             03:00:00Z
Assertion Conditions NotBefore:    02:59:30Z
Assertion Conditions NotOnOrAfter: 03:05:00Z
SubjectConfirmationData expiry:   03:02:00Z
SP receives at:                   03:02:30Z

Conclusion:
  Conditions may still be within window.
  Bearer subject confirmation has already expired.
  Authentication must fail unless a narrowly approved leeway
  and the actual profile validator allow it.
~~~

A frequent bug is taking **Response IssueInstant**, adding 5 minutes as a "valid-until", and ignoring SubjectConfirmationData. That is an unsafe homegrown SAML validator. Spring Security/OpenSAML performs configured validations; business code must **never** parse raw XML to replace the provider.

### Does Skew Apply to Every Field Simultaneously?

Not by default. **Clock skew allowance** belongs to a **specific condition's validator**. Spring/OpenSAML provides default validators for Conditions/SubjectConfirmationData, and may have separate response-specific checks and policies. Check the docs and integration tests for your actual version rather than assuming one property shifts every timestamp on every path.

## 6. Clock Skew: Direction of Drift and Acceptance Window

Suppose:
- IdP issues an Assertion with `NotBefore = 03:00:00Z`.
- At that same real instant, the SP sees `02:59:40Z`, **20 seconds behind**.
- With zero skew: the SP sees the Assertion as **not yet valid**.
- If the SP validator allows **30 seconds** of leeway, the Assertion can pass time checks (all other checks remain mandatory).

Opposite case:
- IdP sets `NotOnOrAfter = 03:05:00Z`.
- SP clock is **20 seconds fast**, reading `03:05:10Z` when real time is 03:04:50.
- With zero skew: the SP sees it as **expired**.
- A 30-second leeway allows the SP to accept near the boundary.

Conceptual formula for a `[start, end)` window, given `now` and tolerance `s ≥ 0`:

~~~text
Start check:
  now + s >= start

End check:
  now - s < end

Combined:
  (now + s >= start) AND (now - s < end)
~~~

This is an **educational model** to explain leeway; libraries can have specific comparison details/precision per SAML/JWT/profile, so **never use this formula to replace the Spring/OpenSAML security validator**.

**Security impact:** allowing 10 minutes of skew can accept an Assertion/token expired **by up to 10 minutes on the validator's clock** or 10 minutes before its start time. Thus it widens the credential acceptance window and increases replay risk in systems lacking replay protection. Skew must be small, grounded in measurements, consistent, and monitored.

### Why Is "Increasing Skew to 24 Hours" an Anti-Pattern?

- Masks broken NTP or missing-timezone parsing bugs.
- Extends the reuse window for bearer assertions/tokens.
- Strips timestamp freshness of meaningful value.
- Creates policy discrepancies across SP, API, and IdP.
- Can break short expiration rules on CAS tickets/anti-replay caches.
- Removing the wide skew later causes widespread login outages.

Root fix: **synchronize IdP/SP/API node clocks**, emit timestamps with standard timezones, fix clock sources, and keep only small skew for real jitter/latency.

## 7. Spring Security SAML2: Setting Clock Skew with the Right API and Version

Current **Spring Security** documentation describes `OpenSaml5AuthenticationProvider.AssertionValidator` with the `clockSkew(...)` builder. The following is a **Spring Security Servlet JavaConfig fragment**, requiring real SAML2 dependencies, IdP metadata, and `RelyingPartyRegistration`:

~~~java
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
public class SamlClockSkewSecurityConfig {

    @Bean
    SecurityFilterChain filterChain(HttpSecurity http)
            throws Exception {
        OpenSaml5AuthenticationProvider provider =
                new OpenSaml5AuthenticationProvider();

        AssertionValidator assertionValidator =
                AssertionValidator.builder()
                        .clockSkew(Duration.ofSeconds(60))
                        .build();
        provider.setAssertionValidator(assertionValidator);

        return http
                .authorizeHttpRequests(auth -> auth
                        .anyRequest().authenticated())
                .saml2Login(saml2 -> saml2
                        .authenticationManager(
                                new ProviderManager(provider)))
                .build();
    }
}
~~~

Java permits wrapping long import statements around dots as shown, yet **this is a fragment dependent on Spring Security/OpenSAML versions, not a standalone `javac` file**. Run integration tests against your resolved dependencies.

**60 seconds is only a policy example**, not a universal default across all SAML2 versions. Spring docs illustrate another value (10 minutes); that **does not mean 10 minutes is a production recommendation or provider default**. Production values should derive from measured clock drift plus a small security-approved margin.

### Spring Security 6 vs. 7

- Spring Security 5/6 has many guides using `OpenSaml4AuthenticationProvider`; custom `assertionValidator`/clock skew APIs may differ.
- Spring Security 7 uses `OpenSaml5AuthenticationProvider` and the `AssertionValidator` builder in current reference docs.
- `RelyingPartyRegistration`, decryption/signing credentials, issuer/ACS/EntityID, and IdP metadata must still be right.
- Do not copy another version's API and strip checks to fix compile errors.
- When replacing the custom assertion validator, **retain all required default validations**; never implement a converter that always returns success.
- After changes, test both `NotBefore` and `NotOnOrAfter` on Conditions and SubjectConfirmationData using **signed fixtures** near the skew boundary.
- Never treat `Destination`/`Audience`/`Signature` errors as "clock skew"; those require fixing trust/metadata.

Source: [Spring Security — Authenticating SAML2 Responses, Setting a Clock Skew](https://docs.spring.io/spring-security/reference/servlet/saml2/login/authentication.html).

## 8. OAuth/OIDC/JWT: exp, nbf, and iat Are Not the Same

An illustrative JWT claim set:

~~~json
{
  "iss": "https://login.example/realms/staff",
  "sub": "user-041",
  "aud": "reports-api",
  "iat": 1794020400,
  "nbf": 1794020400,
  "exp": 1794020700
}
~~~

**This is an unsigned JSON claim subset** purely for illustrating structure. NumericDate numbers are seconds since the UTC Unix epoch, **not milliseconds**. In real systems, read claims from a JWT verified by Spring/JWT decoder; never call `Base64.getDecoder()` and grant Authentication yourself.

Per **RFC 7519**:

- **`exp`:** time **on or after which the token must not be accepted**; the validator requires `now < exp` when there is no leeway.
- **`nbf`:** token **must not be accepted** if `now < nbf`; at exactly `nbf` it can be accepted.
- **`iat`:** **when the token was issued**, used to determine token age; **not itself an expiration date**. Rejecting future `iat` or enforcing max age requires a corresponding validator/policy; do not assume every Spring JWT decoder treats `iat` like `nbf`.
- **`auth_time`:** in OIDC, when **end-user authentication** occurred at the IdP, distinct from the ID Token's `iat`; relates to `max_age`/fresh login/step-up.
- **`jti`:** ID usable for replay tracking when paired with a store/policy, not a timestamp.
- **`aud`/`iss`/signature:** mandatory per token/profile and resource server trust; **never replaced by checking `exp`**.

RFC 7519 allows **a small leeway (usually no more than a few minutes)** to account for clock skew on `exp`/`nbf`. Never pick skew wider than the token TTL. In particular, **expires at `exp`** is an **exclusive** boundary, not "valid until end of day" if `exp` marks the start of day.

### Easy to Confuse Epoch Seconds with Milliseconds

~~~text
JWT NumericDate / unix seconds:
  1794020400

Java Instant.ofEpochSecond(...):
  right unit if the value is seconds

Java Instant.ofEpochMilli(...):
  will point to a very different instant if given 1794020400
~~~

If a timestamp looks off by decades, first check **seconds vs. milliseconds units** rather than rushing to raise clock skew.

## 9. Spring Security Resource Server: JwtTimestampValidator

Spring Security Resource Server docs state:

- Default decoders check `iss` when `issuer-uri` is configured.
- `JwtTimestampValidator` checks `exp` and `nbf`.
- Current docs note **Resource Server defaults to 60 seconds of clock skew**.
- It can be customized via `new JwtTimestampValidator(Duration.ofSeconds(...))`.
- Replacing the validator must **preserve issuer checks** and any other policy-required validators such as audience or application token type.

Example **Spring project fragment** for Servlet Resource Server (not standalone):

~~~java
import java.time.Duration;
import org.springframework.context.annotation.Bean;
import org.springframework.security.oauth2.core.DelegatingOAuth2TokenValidator;
import org.springframework.security.oauth2.core.OAuth2TokenValidator;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.security.oauth2.jwt.JwtDecoders;
import org.springframework.security.oauth2.jwt.JwtIssuerValidator;
import org.springframework.security.oauth2.jwt.JwtTimestampValidator;
import org.springframework.security.oauth2.jwt.NimbusJwtDecoder;

public class JwtTimeValidationConfig {

    @Bean
    NimbusJwtDecoder jwtDecoder() {
        String issuer = "https://login.example/realms/staff";

        NimbusJwtDecoder decoder = (NimbusJwtDecoder)
                JwtDecoders.fromIssuerLocation(issuer);

        OAuth2TokenValidator<Jwt> timeAndIssuer =
                new DelegatingOAuth2TokenValidator<>(
                        new JwtTimestampValidator(
                                Duration.ofSeconds(60)),
                        new JwtIssuerValidator(issuer));

        decoder.setJwtValidator(timeAndIssuer);
        // Production: add required audience/token-purpose validators.
        return decoder;
    }
}
~~~

**Note:** the code above illustrates explicit timestamp + issuer validation per the docs, **without adding audience/client-scope validators yet**, and may omit defaults if the app already uses custom validators. In production config, add audience/token-type/scope checks per your resource server contract; never accidentally replace the entire validation pipeline with just a clock check.

Source: [Spring Security — OAuth2 Resource Server JWT, Customizing Timestamp Validation](https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/jwt.html).

### OIDC Browser Login Differs from JWT Resource Server

`oauth2Login()` handles client-side Authorization Code/OIDC authentication; `oauth2ResourceServer().jwt()` handles API bearer Access Tokens. **Do not tweak the API's `JwtTimestampValidator` and assume OIDC ID Token login at the browser client now shares the same skew**. Nimbus/ID Token validators and OAuth2 Client logic can differ; check the exact failing flow.

In the OIDC Authorization Code flow there are also:
- `state` and authorization request **timeout** in the session/repository.
- `nonce` binding the ID Token.
- Code expiry, redirect URI/PKCE verifier, and single-use at the token endpoint.
- IdP login session and user authentication freshness (`auth_time`/`max_age`).

A request failing with `invalid_grant` can be caused by an **expired or already-used authorization code**, wrong redirect_uri, PKCE mismatch, or client auth failure—never blame NTP indiscriminately.

## 10. CAS: Ticket TTL and CAS Server Clock

Classic CAS SSO passes a `Service Ticket` like `ticket=ST-...` on the service callback, which `CasAuthenticationProvider`/the ticket validator verifies against the CAS server. Tickets typically have short TTLs and are single-use, yet **do not carry a SAML-style `NotBefore`/`NotOnOrAfter` pair in the browser URL**.

If the CAS server rejects a service ticket:

1. Verify the **service URL binding** is exact.
2. Check whether the ticket was already used once before.
3. Check TTL and ticket registry/policy **for the exact CAS server version**.
4. Check clock sync across CAS nodes if the registry/session is distributed.
5. Check proxy/browser redirect loops or queues adding delay.
6. Check network/TLS and log locations.

**Never assume "CAS ST always expires after N seconds"** without knowing the CAS version and policy; timeouts are configurable. Nor should you apply `JwtTimestampValidator` to a CAS ST, or replay a previously validated ST to "avoid expiry".

## 11. Sessions, Cookies, and TLS Also Have Time-Related Failures

A login can fail even with a valid SAML Assertion due to another layer:

| Situation | Layer | What to Check? |
| --- | --- | --- |
| SAML Assertion `NotOnOrAfter` just expired | SAML provider | Conditions/SubjectConfirmationData, actual skew |
| JWT `exp` expired | Resource Server | `exp` NumericDate, node clock, skew |
| ID Token login fails on `iat`/`nonce`/`auth_time` | OIDC Client | Auth request correlation, issuer/session policy |
| CAS ST expired | CAS server/registry | Ticket TTL, single use, queue delays |
| TLS certificate `NotBefore` in the future | PKIX/TLS | Server/client cert validity, current node clock |
| Session timeout | Spring/IdP sessions | Last accessed/absolute TTL, session store, logout |
| Wrong cookie `Expires`/`Max-Age` | Browser/client | Cookie attributes, browser clock/refresh behavior |
| CSRF token expired | Web session/form | Form lifetime and session/cookie policy |
| `LoginState`/`RelayState` missing | Session/cache persistence | Correlation store TTL, wrong node, SameSite cookie |
| Secret/metadata rollover time | Key management | Cert rotation window/keys, not SAML Conditions |

**TLS example:** the JVM throws `NotYetValidException` because a node is genuinely 2 days behind. Widening SAML skew **does not fix TLS trust**. Conversely, a truly expired certificate must never be "solved" by setting the system clock backward, as that breaks federation and auditing elsewhere.

### Cookie Expires vs. Max-Age

Browsers can use server time info when processing cookie expiry and have implementation-specific adjustments. Never blame every `SameSite`/`Secure`/`HttpOnly` behavior on NTP. A cookie blocked on a cross-site SAML POST is a cookie policy issue, **not clock skew**.

## 12. NTP, chrony, and Time Synchronization on Linux/Kubernetes

In production, **system clocks must synchronize with a trusted time source** via NTP or your infrastructure's managed time service. On Linux using `chrony`, check:

~~~bash
# Read-only: sync/timezone status
date -u +"%Y-%m-%dT%H:%M:%SZ"
date +"%Y-%m-%d %H:%M:%S %Z %z"
timedatectl status

# If chrony is installed
chronyc tracking
chronyc sources -v
chronyc sourcestats -v

# Check running service (distro-dependent)
systemctl status chronyd
systemctl status chrony
~~~

**These are read-only status commands**; the service name may be `chronyd` or `chrony` depending on distro, and `timedatectl` may not work inside containers without systemd. If using a cloud provider managed time service, check the corresponding dashboard/metrics.

Pay attention to fields in `chronyc tracking` such as reference time, last offset, system time, RMS offset, root delay/root dispersion, leap status, and update interval for your chrony version. **Never treat "local timezone GMT+7" as proof that the server is 7 hours off**.

### Kubernetes

~~~text
IdP pod A on node-01: current instant +0s
IdP pod B on node-02: current instant +95s
Spring pod C on node-03: current instant +2s

Consequence:
  tokens/assertions from pod B appear "issued in future"
  only for some login attempts
~~~

Containers normally share the host/kernel system clock; `TZ` only affects displayed time and local time APIs. In certain specialized virtualization/time-namespace setups behavior may differ, yet by default **fix NTP on the node/VM**, not merely by changing `TZ` inside the pod.

Check:
- The node running the pod issuing tokens/IdP/sessions.
- The node running the rejecting SP/API resource server.
- Clock sync status of **all nodes**, not just one replica.
- Hypervisor/VM resume/suspend, snapshots, host drift, virtual time services, chrony/NTP conflicts.
- NTP reachability, ACLs/firewalls, DNS, and approved time sources.
- Multiple conflicting time-sync daemons or leap-second handling.
- Clock jumps at startup/VM migration, monotonic vs. wall clock.

**Never change production clocks arbitrarily with `date -s`.** Hand it to the infra/time-sync team, because stepping time can affect database transactions, logs, cert validity, distributed locks, and security sessions.

## 13. Standardizing Timestamps in Logs for Diagnosability

A minimal audit event should include:

~~~text
timestamp_utc=2026-11-07T03:00:45.123Z
service=spring-sp
instance=sp-node-03
environment=prod
protocol=SAML2
registration_id=corp-idp
event=SAML_AUTHN_FAILURE
reason_code=ASSERTION_NOT_YET_VALID
correlation_id=nonsecret-opaque-id
observed_clock_offset_ms=+1800
validation_stage=ASSERTION_CONDITIONS
~~~

This is illustrative data. Every field needs a reliable measurement source:

- **`timestamp_utc`:** log ISO 8601 UTC with `Z` offset so logs from different systems are comparable.
- **`instance`/`node`:** pinpoint the pod/VM causing intermittent failures.
- **`observed_clock_offset_ms`:** include only when measured from NTP/monitoring; **do not compute it from the difference between two log timestamps** because log delays vary.
- **`validation_stage`:** distinguish Conditions vs. SubjectConfirmationData vs. JWT Timestamp vs. SSO session.
- **`reason_code`:** an enum/error code mapped by the app from exceptions without printing raw credentials.
- **`correlation_id`:** a dedicated ID, never `SAMLResponse`, CAS ticket, access token, or raw NameID.

Avoid logging:
- Full `SAMLResponse`/Assertion XML, ID Token/JWT, or CAS tickets.
- Session cookies, Authorization headers, SAML attributes/PII.
- Private keys and signed assertions.
- Raw query strings containing `code`, `state`, or `ticket`.
- Detailed exception variables if they contain XML/tokens.

An SP in UTC+07 may still emit logs showing `10:00+07:00`; if SIEM ingestion parses the offset properly, that is `03:00Z`. Only if the SIEM **drops the offset** and attaches the wrong timezone will the dashboard show a 7-hour shift.

## 14. Tracing Evidence When a Request Fails

Do not start with "add 10 minutes of skew". Take the event's **correlation ID**, then ask:

1. Which component rejected? **IdP, Spring SP, Resource Server, CAS Server, gateway, or browser?**
2. Is it genuinely a **time** error, or an issuer/signature/audience/recipient/session error?
3. Are log timestamps **UTC Instants** or local times? Was the offset preserved or stripped?
4. When did the IdP issue the artifact, and when did SP/API validate it? Was there abnormal **queue/redirect latency**?
5. Do `NotBefore`/`NotOnOrAfter` belong to Conditions or SubjectConfirmationData? Which bound expired first?
6. How much leeway is officially configured in the running validator? What is the default of the **actual version**?
7. Which IdP/SP/API node issued and received the request? What is each node's NTP offset/root dispersion?
8. Do failures correlate with one node/pod, or right after a deploy/VM resume/clock step?
9. Do failures happen only after browser idle, a long-open login page, or a redirect loop?
10. Did the token/cookie/session genuinely expire per TTL?
11. Did anyone recently change clocks/timezones/JVM flags or update time-zone rules?
12. Did anyone override the default Spring Security validator with a custom implementation that dropped timestamp checks?

### Distinguishing Latency from Skew

An Assertion with a 60-second lifetime can expire even when IdP and SP clocks match perfectly if the user stalls on an intermediate consent page or the browser hangs before POSTing. Conversely, a 90-second clock skew causes immediate failure even with 100 ms network latency.

Never infer clock drift from `(SP receive timestamp − IdP issue timestamp)` without subtracting **network/processing latency** and understanding timestamp semantics. Cross-check with NTP offset telemetry and tracing span timestamps.

## 15. Timezone Parsing Pitfalls in Java/Spring

**Right:** use `Instant` for points on the timeline, `OffsetDateTime` when input has `Z`/`+07:00` and the original offset matters, `ZonedDateTime` for regional display, and `Duration` for elapsed spans.

**Common mistake:**

~~~java
// Do not do this to check SAML/JWT absolute timestamps:
LocalDateTime source = LocalDateTime.parse("2026-11-07T10:00:00");
Instant guessed = source.atZone(ZoneId.systemDefault())
        .toInstant();
// Result depends on the running machine's timezone config.
~~~

This is an anti-pattern: a string without an offset **cannot supply an absolute instant on its own**. If the IdP sends times with standard offsets, preserve/parse the offset; if a legacy integration sends offset-less strings, establish an **explicit timezone contract** before converting and handle DST ambiguity.

Good example:

~~~java
import java.time.Instant;
import java.time.OffsetDateTime;
import java.time.ZoneId;
import java.time.ZonedDateTime;

Instant utc = Instant.parse("2026-11-07T03:00:00Z");
Instant vn = OffsetDateTime
        .parse("2026-11-07T10:00:00+07:00")
        .toInstant();

boolean sameMoment = utc.equals(vn);
ZonedDateTime display =
        utc.atZone(ZoneId.of("Asia/Ho_Chi_Minh"));
~~~

`sameMoment == true`. `display` is the local time of the same `Instant`; it does not grant the token extra lifetime.

### What Bugs Does DST Cause?

In regions like `Europe/Berlin`, one hour on a daylight-saving transition day can **fail to exist** or **occur twice**. `LocalDateTime.of(...)` cannot unambiguously map those hours to an `Instant`. Use `ZonedDateTime`, `ZoneId`, and a clear policy for ambiguous local times when calendar scheduling is truly needed. **Federation token timestamps should be UTC instants**, never offset-less local times.

### JWT NumericDate Is Seconds, Not Milliseconds

~~~java
Instant correct = Instant.ofEpochSecond(1794020400L);
// Wrong if NumericDate input is in seconds:
Instant incorrect = Instant.ofEpochMilli(1794020400L);
~~~

Getting the unit wrong can make tokens look decades expired or decades in the future. Spring JWT decoders typically convert `exp` to `Instant`; never re-parse raw JSON manually when `Jwt.getExpiresAt()` is available.

## 16. Standalone Java 17: Diagnosing UTC, Clock Skew, and Boundaries

The code below simulates the **`[NotBefore, NotOnOrAfter)` window** at an educational level. It uses `Clock.fixed` so tests do not depend on wall-clock time and `Clock.offset` to simulate a node running 45 seconds fast. All data is synthetic and does not create/verify real SAMLResponses or JWTs. Production must still use **Spring Security/OpenSAML/Nimbus validators**.

Create file **`FederationClockDiagnosticsDemo.java`**:

~~~java
import java.time.Clock;
import java.time.Duration;
import java.time.Instant;
import java.time.OffsetDateTime;
import java.time.ZoneId;
import java.time.ZoneOffset;

public class FederationClockDiagnosticsDemo {

    // Model a half-open interval [NotBefore, NotOnOrAfter).
    // Only use this in education; real SAML/JWT validation does more.
    static boolean withinWindow(
            Clock clock,
            Instant notBefore,
            Instant notOnOrAfter,
            Duration skew) {

        if (skew.isNegative()
                || !notBefore.isBefore(notOnOrAfter)) {
            throw new IllegalArgumentException("Invalid time policy");
        }

        Instant now = clock.instant();
        return !now.plus(skew).isBefore(notBefore)
                && now.minus(skew).isBefore(notOnOrAfter);
    }

    public static void main(String[] args) {
        Instant base =
                Instant.parse("2026-11-07T03:00:00Z");

        Clock reference = Clock.fixed(base, ZoneOffset.UTC);
        Clock fastNode =
                Clock.offset(reference, Duration.ofSeconds(45));

        Instant fromVietnamOffset = OffsetDateTime.parse(
                "2026-11-07T10:00:00+07:00").toInstant();

        System.out.println("Same UTC instant: "
                + base.equals(fromVietnamOffset));

        System.out.println("Vietnam local: "
                + base.atZone(ZoneId.of("Asia/Ho_Chi_Minh")));

        Instant start = base.minusSeconds(60);
        Instant end = base.plusSeconds(30);

        System.out.println("Reference valid: "
                + withinWindow(reference, start, end,
                        Duration.ZERO));

        System.out.println("Fast node valid without skew: "
                + withinWindow(fastNode, start, end,
                        Duration.ZERO));

        System.out.println("Fast node valid with 30s skew: "
                + withinWindow(fastNode, start, end,
                        Duration.ofSeconds(30)));

        System.out.println("Exact expiry valid without skew: "
                + withinWindow(reference,
                        base.minusSeconds(60),
                        base, Duration.ZERO));

        System.out.println("Future NBF +25s allowed with 30s: "
                + withinWindow(reference, base.plusSeconds(25),
                        base.plusSeconds(90),
                        Duration.ofSeconds(30)));

        System.out.println("Future NBF +31s allowed with 30s: "
                + withinWindow(reference, base.plusSeconds(31),
                        base.plusSeconds(90),
                        Duration.ofSeconds(30)));

        System.out.println("Expired 20s allowed with 30s: "
                + withinWindow(reference, base.minusSeconds(90),
                        base.minusSeconds(20),
                        Duration.ofSeconds(30)));

        System.out.println("Expired 31s allowed with 30s: "
                + withinWindow(reference, base.minusSeconds(90),
                        base.minusSeconds(31),
                        Duration.ofSeconds(30)));

        System.out.println("Fast-node offset seconds: "
                + Duration.between(
                        reference.instant(),
                        fastNode.instant()).getSeconds());
    }
}
~~~

Run with JDK 17 or higher:

~~~bash
javac FederationClockDiagnosticsDemo.java
java FederationClockDiagnosticsDemo
~~~

**Exact stdout:**

~~~text
Same UTC instant: true
Vietnam local: 2026-11-07T10:00+07:00[Asia/Ho_Chi_Minh]
Reference valid: true
Fast node valid without skew: false
Fast node valid with 30s skew: true
Exact expiry valid without skew: false
Future NBF +25s allowed with 30s: true
Future NBF +31s allowed with 30s: false
Expired 20s allowed with 30s: true
Expired 31s allowed with 30s: false
Fast-node offset seconds: 45
~~~

### Explaining Each Result

- **Same UTC instant: true:** `03:00Z` and `10:00+07:00` are the same instant.
- **Vietnam local:** Java `ZonedDateTime` uses timezone ID `Asia/Ho_Chi_Minh` for display without altering `Instant`.
- **Reference valid:** current instant is inside `[now−60s, now+30s)`.
- **Fast node without skew: false:** a node 45 seconds ahead passes an end bound only 30 seconds in the future.
- **Fast node with 30s skew: true:** a 30-second validator tolerance makes it valid in the model; production still needs the node clock fixed.
- **Exact expiry without skew: false:** at `NotOnOrAfter` or JWT `exp`, it is already expired.
- **Future NBF +25s:** accepted if policy allows 30s skew; **+31s** exceeds tolerance.
- **Expired 20s:** accepted with 30s skew; **31s** exceeds the limit.
- **Fast-node offset seconds: 45:** simulated offset between clocks, not a real NTP measurement.

This code does **not** verify signatures, issuer, audience, recipient, InResponseTo, subject confirmation, replay, CAS ST, or PKIX certificates. **Never copy `withinWindow` into production to replace JWT/SAML validators**. Use it as a boundary-reasoning exercise and to build unit tests for business policies *after* protocol validation passes.

## 17. Testing Deterministically with Clock.fixed and Clock.offset

**Never write tests like this**:

~~~java
// Anti-pattern: test running near midnight or under load will be flaky.
Instant now = Instant.now();
assertTrue(tokenExpiration.isAfter(now));
Thread.sleep(2000);
// Assertion may or may not expire due to environment/GC delays.
~~~

Instead, use **Clock injection** for code that manages time itself:

~~~java
import java.time.Clock;
import java.time.Duration;
import java.time.Instant;
import java.time.ZoneOffset;

// Test helper fragment; does not verify SAML itself:
Clock atStart = Clock.fixed(
        Instant.parse("2026-11-07T03:00:00Z"), ZoneOffset.UTC);

Clock thirtySecondsLater =
        Clock.offset(atStart, Duration.ofSeconds(30));
Clock oneMinuteEarlier =
        Clock.offset(atStart, Duration.ofMinutes(-1));
~~~

JUnit/MockMvc/provider integration tests require fixtures covering signatures, audience, correlation, and timestamps. **Injecting `Clock` into business code alone does not make the OpenSAML provider use that clock**. To test real provider skew, use the appropriate version-specific testing API, a signed SAML test IdP with fixed timestamps, or a safely controlled test environment clock; never swap `System.currentTimeMillis()` globally.

### Highest-Value Boundary Matrix

| Test | Input/Time Scenario | Expected |
| --- | --- | --- |
| T01 | SAML now 1ms before NotBefore | Reject if skew is 0 |
| T02 | SAML now exactly at NotBefore | Conditions start acceptable |
| T03 | SAML now 1ms before NotOnOrAfter | Conditions end acceptable |
| T04 | SAML now exactly at NotOnOrAfter | Reject if skew is 0 |
| T05 | SAML Conditions unexpired, SubjectConfirmationData expired | Reject |
| T06 | IdP clock 30s fast, SP clock accurate | Check leeway policy |
| T07 | SP clock 45s fast, leeway 30s, short window | Outcome per binding/validator; no blanket accept |
| T08 | Signed Assertion has timestamp edited after signing | Signature fails; test does not prove time validation |
| T09 | NotBefore after NotOnOrAfter | Invalid conditions, reject |
| T10 | Missing times yet invalid bearer confirmation | Reject per profile/policy |
| T11 | SAML IssueInstant far in the future | Response freshness/policy rejects when enforced |
| T12 | Invalid Recipient/Audience with valid time | Reject |
| T13 | Duplicate/replayed Assertion ID with valid time | Replay policy rejects |
| T14 | OIDC/JWT now == exp | Reject per RFC semantics if no skew |
| T15 | JWT now == nbf | Valid per time boundary if unexpired |
| T16 | JWT nbf future +25s with skew 30 | Evaluates within tolerance |
| T17 | JWT exp past 31s with skew 30 | Reject |
| T18 | JWT iat in future while nbf/exp valid | Reject only if a specific **iat policy** exists |
| T19 | NumericDate seconds parsed as millis | Test catches wildly wrong date |
| T20 | UTC Z vs +07 equivalent | Same Instant, identical outcome |
| T21 | IdP/SP pods on nodes with different clocks | Exposes intermittent failures |
| T22 | Clocks synced, network delay exceeds TTL | Reject genuine expiry |
| T23 | Browser holds login form too long | Separate state/correlation expiration |
| T24 | Cookie blocked by SameSite on cross-site POST | Do not misdiagnose as clock skew |
| T25 | TLS cert not yet valid due to wrong clock | Fails PKIX; fix host clock/CA, not SAML skew |
| T26 | Leap second/DST transition/local time logs | Logs canonicalize UTC, no double counting |
| T27 | CAS ticket already used | CAS denies replay; skew does not validate it |
| T28 | CAS ticket expired per policy | Deny; check actual CAS registry TTL |
| T29 | Multi-node time sync OK yet validator configs differ | Fix config drift, do not alter timezone |
| T30 | Negative skew configured | Reject invalid policy/config |

### Critical Note on Fixture Timestamps and Signatures

If you edit `NotOnOrAfter` or `IssueInstant` inside a raw signed `SAMLResponse`, the signature becomes invalid; the test may fail signature checks before reaching time validation. To test time boundaries, **regenerate the Assertion using a test IdP/OpenSAML signer** and re-sign it with a **lab private key**, or use a controlled provider fixture builder. Never take a real production `SAMLResponse` and edit or log it.

For JWTs, never edit `exp` in the payload after signing and call it an "expired token test" if you want to reach the timestamp validator. You must **re-issue a validly signed JWT** using a test key and valid issuer/audience.

## 18. Observing Clocks Across Multiple Nodes: Comparing Accurately

Sample node inventory checklist:

~~~text
node-id   role            utc_now               ntp_offset    sync
idp-01    IdP             03:00:00.100Z         +1ms          yes
idp-02    IdP             03:01:30.000Z         +90s          no
sp-01     Spring SP       03:00:00.150Z         +2ms          yes
sp-02     Spring SP       03:00:00.170Z         +4ms          yes
api-01    Resource Server 03:00:00.160Z         +3ms          yes
~~~

This is **illustrative synthetic data**; each host's clock was sampled at different moments, so you cannot infer offset from the `utc_now` column without real measurements. The **`ntp_offset`** column must come from a calibrated monitoring service with uniform units.

If only `idp-02` drifts by +90s, tokens issued from that node can have future `nbf` or `iat` relative to the SP and trigger intermittent failures; raising skew to 120s might mask it, yet **fixing NTP on `idp-02`** is the proper remedy.

### Recommended Monitoring

- Node time sync status / stratum/reachability/chrony last offset/root dispersion.
- Absolute offset thresholds and alerts when exceeding risk limits.
- Time validation failures by **provider / registration / SP instance / issuer / reason**.
- Histograms of `NotBefore − SP now` and `SP now − NotOnOrAfter` from **synthetic fixtures/anonymized metrics** when properly designed, without logging raw Assertions.
- Request latency, queue duration, token exchange duration.
- Authentication failures after NTP daemon restarts, VM migrations, clock steps, or deployments.
- Configuration drift: all SP nodes share the same skew policy and version.
- Session/token age and revocation alerts.

**Never push NameID/email, raw JWT/SAMLResponse, or CAS tickets into metric labels**, as that causes cardinality/PII leaks and exposes protected tokens.

## 19. Layered Remediation Workflow Without Weakening Security Checks

### Step 1 — Isolate the Failure

Distinguish **SAML assertion Conditions**, **bearer SubjectConfirmationData**, **OAuth/JWT timestamp**, **OIDC nonce/auth_time**, **CAS ticket TTL**, **TLS PKIX certificate validity**, and **session timeout** using the specific error stage.

### Step 2 — Collect Minimal Evidence

Record correlation ID, trusted registrationId, node/pod ID, UTC event time, validation reason enum, skew config version, and node NTP offset; never collect raw credentials.

### Step 3 — Check Absolute Time

Check `date -u`/chrony on IdP/SP/API nodes; compare using `Instant`. If timezones differ while UTC Instants match, that is purely display.

### Step 4 — Read Actual Time Bounds

Use test fixtures/closed environments to inspect `NotBefore`/`NotOnOrAfter` on Conditions, bearer SubjectConfirmationData, `IssueInstant`, and `exp`/`nbf`/`iat`. Never copy real payloads into public logs.

### Step 5 — Check Latency and Replay

If clocks are synced yet artifacts expired, check overly short TTLs, redirect loops, browser idle, queues, and duplicate reuse; do not rush to widen skew.

### Step 6 — Synchronize Infrastructure

Fix NTP/chrony/cloud time services and node drift through infrastructure change control; never step production system clocks arbitrarily without assessing dependencies.

### Step 7 — Minimal Policy Tuning

If real clock drift is only a few seconds, pick a small allowance, document the owner, test both start/end boundaries plus issuer/correlation/replay, and monitor metrics. Never allow hours of skew.

### Step 8 — Recover and Post-Verify

Ensure signing, audience, recipient, session/cookie, and tenant policies still hold; verify truly expired/replayed tokens are rejected properly. Retain incident data per policy and purge sensitive logs.

## 20. Symptom-Based Error Runbook

| Symptom | Likely Cause | Action to Take |
| --- | --- | --- |
| `NotBefore condition is not yet valid` | SP clock slow, IdP clock fast, UTC parse shift, leeway too small | Compare UTC/NTP offsets, inspect Conditions |
| `SubjectConfirmationData expired` | Browser delay, tighter bound than Conditions, SP clock fast | Check subject end bound and latency, not Conditions alone |
| `Assertion expired` | Real TTL expired, SP clock fast, skew/config mismatch | Measure NTP and effective end bound |
| SAML signature invalid | Wrong IdP signing cert/XML tampering | Fix trust/signature; **never increase skew** |
| SAML audience mismatch | Wrong EntityID/registration | Fix metadata/audience |
| SAML response passes on pod A, fails on pod B | Time sync drift or differing key/validation configs | Check node clocks and deployment drift |
| JWT `exp` expired | Token TTL, system clock, validator skew | Compare `exp` NumericDate and now |
| JWT `nbf` in future | AS fast/resource server slow, wrong epoch units | Compare UTC `Instant`s |
| JWT `iat` unexpectedly future | Node time drift or strict policy | Check `iat` validator separately; do not infer from `exp` |
| OIDC `invalid_grant` | Code expired/redeemed, PKCE mismatch, redirect URI | Classify token endpoint error before blaming clock |
| OIDC login loop | Session/cookie/state issue, clock/timebound | Check SameSite/correlation storage and token timing |
| CAS ST invalid | Ticket replay/expired/service mismatch | Check CAS ticket validation + registry |
| TLS `NotYetValidException` | Cert dates or host clock wrong | Check PKIX/certificate/NTP |
| TLS `CertificateExpiredException` | Cert truly expired or host fast | Renew cert or fix time source |
| Log shows IdP 10:00, SP 03:00 for same event | +07 offset vs. UTC | Convert timestamps; do not alter clocks if Instants match |
| JWT `exp` looks like year 1970 | Epoch seconds treated as milliseconds | Switch to `ofEpochSecond` |
| Fails only on DST days | Broken `LocalDateTime`/`ZoneId` parsing | Use ISO `Instant`/`OffsetDateTime` |
| Session expires quickly on one node | Session store/TTL/clock drift | Check store semantics and node clock |
| Widened skew yet login still fails | Signature/audience/recipient/replay/auth state | Go back and pinpoint the failing stage |

**Never log decoded token XML or raw URLs "to see more clearly"**. Use sanitized structured logs, test identities, approved secure tools, and short-lived diagnostics.

## 21. Dangerous Anti-Patterns

### A — "Servers run UTC, users are in Vietnam so there is a 7-hour offset"

False. UTC 03:00 and Vietnam 10:00 are the same `Instant`; errors only occur when a parser strips the offset/zone or attaches the wrong one. **Never add 7 hours of skew**.

### B — "Disable NotBefore/NotOnOrAfter so logins fail less"

False. These are critical replay/freshness bounds. Skipping them allows expired bearer assertions to be accepted. Fix clock/issuer/latency, never drop SAML conditions.

### C — "IssueInstant plus 5 minutes instead of all time checks"

False. Conditions and SubjectConfirmationData have their own bounds; `InResponseTo`, recipient, and audience are also mandatory per profile. Never hand-roll a simplified validator.

### D — "JWT iat is basically exp"

False. `iat` is issuance time; `exp` is expiration time; `nbf` is not-before time. Each claim has distinct semantics in RFC 7519.

### E — "Different JVM timezone means node clock is off"

False. `-Duser.timezone=UTC` helps unify log display, yet **does not fix actual NTP offset**. Measure skew via trusted reference clocks and UTC instants, not by comparing local strings.

### F — "10-minute skew means no need for NTP sync"

False. Skew widens the acceptance window and can mask node time drift. Monitoring/NTP is the primary control; leeway is a small cushion.

### G — "Edit signed XML/JWT to create an expired test"

False. Signature verification fails before time validation. Generate a **validly signed fixture using test keys** and then test boundaries.

### H — "Replay a CAS ticket a second time to test the clock"

False. CAS STs are normally single-use; the second attempt fails due to replay, proving nothing about clock skew.

### I — "Token exp in 5 minutes means login session also expires in 5 minutes"

Not necessarily. Access Token, ID Token, IdP SSO session, Spring session, CAS ticket, and certificate lifetime are independent mechanisms. Map out an actual TTL table.

### J — "Any still-valid ID Token grants API access"

False. An ID Token is for the OIDC client; an API Resource Server requires an **Access Token with the right audience/scope**, and this distinction must never be bypassed to work around expiry.

## 22. QA Handoff Checklist

- [ ] Distinguished UTC Instant, offset, ZoneId, DST, and clock drift.
- [ ] Logs canonicalize ISO 8601 UTC with `Z`/offset, preserving timezones on ingest.
- [ ] SAML Conditions inclusive `NotBefore` / exclusive `NotOnOrAfter` tested.
- [ ] Bearer SubjectConfirmationData has its own expiration/Recipient/InResponseTo checks.
- [ ] `IssueInstant` is never substituted for condition expiry.
- [ ] Signature, issuer, audience, destination, recipient, correlation, and replay remain validated.
- [ ] IdP and SP/resource server NTP/chrony telemetry measured per node.
- [ ] `TZ` timezone is never changed alone to "fix" NTP drift.
- [ ] Spring SAML OpenSAML version and `AssertionValidator.clockSkew` verified accurately.
- [ ] Wide skew is never chosen from doc examples without a risk assessment.
- [ ] JWT Resource Server has `JwtTimestampValidator` checking `nbf`/`exp`.
- [ ] JWT issuer and audience/scope validations remain intact alongside custom timestamp validators.
- [ ] OIDC browser login `state`/`nonce`/code timeouts are not confused with API JWTs.
- [ ] CAS ticket TTL, replay, and service binding distinguished from SAML time conditions.
- [ ] TLS certificate validity, cookie/session TTL, and IdP session lifetime distinguished.
- [ ] Offset-less `LocalDateTime` never treated as an absolute auth timestamp.
- [ ] JWT NumericDate parsed as epoch seconds, not milliseconds.
- [ ] Java tests use `Clock.fixed`/`Clock.offset` when testing business logic.
- [ ] Signed/encrypted SAML fixtures and signed JWT fixtures exist for time boundary tests.
- [ ] Tested at-start, at-end, +/−skew, invalid issuer/signature, and replay.
- [ ] Verified pod A/B and IdP/SP/API nodes run uniform configs/skew policies.
- [ ] Never log raw SAMLResponse, JWT, CAS tickets, cookies, secrets, or PII.
- [ ] Root cause (clock/latency/token TTL/formatter/validation) clearly documented.
- [ ] Monitoring, alerts, and incident/runbook exist for time synchronization drift.
- [ ] After changes, genuinely expired, wrong-issuer, and replayed assertions/tokens are still rejected.

## 23. Official Reference Documentation

1. [Spring Security — Authenticating SAML2 Responses / Setting a Clock Skew](https://docs.spring.io/spring-security/reference/servlet/saml2/login/authentication.html): `OpenSaml5AuthenticationProvider.AssertionValidator.builder().clockSkew(...)` and validator.
2. [Spring Security — SAML2 Login Overview](https://docs.spring.io/spring-security/reference/servlet/saml2/login/overview.html): SAML response processing, signature, decryption, assertion conditions, and subject validation.
3. [Spring Security — OAuth2 Resource Server JWT](https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/jwt.html): `JwtTimestampValidator`, 60s default, and custom clock skew.
4. [RFC 7519 — JSON Web Token](https://www.rfc-editor.org/rfc/rfc7519): `exp`, `nbf`, `iat`, NumericDate, and clock leeway.
5. [OpenID Connect Core 1.0](https://openid.net/specs/openid-connect-core-1_0.html): `auth_time`/`max_age`, ID Token, nonce, expiration/issuer.
6. [OASIS SAML 2.0 Core](https://docs.oasis-open.org/security/saml/v2.0/saml-core-2.0-os.pdf): `Conditions`, `NotBefore`, `NotOnOrAfter`, `IssueInstant`, subject confirmation.
7. [OASIS SAML 2.0 Profiles](https://docs.oasis-open.org/security/saml/v2.0/saml-profiles-2.0-os.pdf): Web Browser SSO bearer SubjectConfirmationData and SP obligations.
8. [Oracle Java 17 — Clock](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/time/Clock.html): `Clock.fixed`, `Clock.offset`, and testable current time.
9. [Oracle Java 17 — java.time package](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/time/package-summary.html): `Instant`, `OffsetDateTime`, `LocalDateTime`/`ZonedDateTime`.
10. [Oracle Java 17 — DateTimeFormatter](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/time/format/DateTimeFormatter.html): ISO instant/offset parsing.
11. [chrony Project — Documentation](https://chrony-project.org/documentation.html): `chronyc tracking`/`sources` and host time synchronization.
12. [Spring Security — CAS Authentication Filter Javadoc](https://docs.spring.io/spring-security/site/docs/current/api/org/springframework/security/cas/web/CasAuthenticationFilter.html): CAS service ticket callback/token validation.
13. [OWASP — SAML Security Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/SAML_Security_Cheat_Sheet.html): signing, subject, validity, replay, SP validation.
14. [OWASP — Logging Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Logging_Cheat_Sheet.html): avoiding logging credentials and PII when debugging.
15. [RFC 9700 — OAuth 2.0 Security Best Current Practice](https://www.rfc-editor.org/rfc/rfc9700): authorization code binding, replay/expiry, and modern OAuth security.

**Conclusion:** Most "SAML/JWT time" errors are only solved when you distinguish **actual Instant**, **display timezone**, **genuine TTL expiration**, **latency**, and **inter-node clock skew**. SAML has multiple independent time bounds (Conditions, SubjectConfirmationData, IssueInstant), JWT has `nbf`/`exp`/`iat`, and CAS tickets have their own registry TTL. Spring Security supports customizing validators, yet **no configuration replaces NTP/chrony and full validation**. Measure offsets on every IdP/SP/API node, standardize on UTC, use genuinely signed fixtures in integration tests, keep leeway small, and preserve signature/audience/recipient/replay checks before marking the incident resolved.