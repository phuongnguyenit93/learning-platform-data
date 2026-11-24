# Clock Synchronization and Drift Monitoring in Spring Security Federation

## 1. Why Is Timekeeping Part of SSO Security?

A Spring Boot system authenticating via SAML 2.0, OIDC/OAuth2, Kerberos, or CAS requires multiple machines to agree on the **current time**. A valid digital signature and accurate account information are still not enough: an assertion/token can be rejected because it is not yet valid or has already expired.

For example, the Identity Provider (IdP) issues a SAML Assertion at 12:00:00 UTC, valid until 12:05:00. A Service Provider (SP) running on a VM skewed **7 minutes fast** will read 12:07:00 and treat the assertion as expired. Within the same cluster, an accurate-clock pod accepts a JWT while a pod on a skewed node rejects it, producing a seemingly random sequence of 200/401 responses.

This affects:
- SAML IdPs and Spring Security SAML SPs;
- OpenID Providers/Authorization Servers and OIDC clients;
- OAuth2 Resource Servers verifying JWT-signed Access Tokens;
- Kerberos Key Distribution Centers (KDCs), domain controllers, workstations, and SPNEGO services;
- CAS Servers, service-ticket registries, and browser sessions;
- Reverse proxies/ingresses, Java hosts, Kubernetes nodes, VMs, session stores, and certificate validation.

**Knowledge Article:** Spring Security - federation → Deployment and Operations → **“Clock Synchronization and Drift Monitoring”**.

### Learning Objectives

After this article, learners can:

1. Distinguish wall clock, UTC, timezone, monotonic time, offset, drift, NTP error/uncertainty, and protocol clock-skew allowance.
2. Analyze SAML `IssueInstant`, `NotBefore`, `NotOnOrAfter`, `SubjectConfirmationData`, and OIDC/JWT `iat`, `nbf`, `exp`, `auth_time`.
3. Understand why Kerberos clock skew differs from JWT leeway and CAS ticket TTLs follow their own rules.
4. Configure/inspect time sources on Linux (`chronyd`, `systemd-timesyncd`) and Windows (`w32tm`).
5. Identify VMs/containers/Kubernetes nodes with skewed clocks instead of changing timezones or inflating JWT lifetimes.
6. Read `chronyc tracking`, `sources -v`, `sourcestats -v`, and `node_timex_*` metrics.
7. Design dashboards, alert thresholds, and runbooks for NTP outages, VM restores, and clock steps/slews.
8. Configure `JwtTimestampValidator` or SAML assertion `clockSkew` for the exact Spring Security version without dropping critical validators.
9. Write deterministic time-boundary tests using `Clock.fixed` and validly signed fixtures.
10. Run a standalone Java 17 program illustrating clock skew and the effect of leeway.
11. Explain the security risks of overly generous clock skew and how to govern replay.
12. Distinguish clock errors from issuer/audience, signature, certificate, ACS, or request correlation failures.

**Scope:** Java 17+, Spring Security Servlet 6.x/7.x, Linux, Windows Server, and Kubernetes. Hostnames like `example.org`, offsets, and alert thresholds are illustrative examples. Verify exact APIs, NTP mechanisms, and security controls against your active versions and infrastructure.

---

## 2. Four Time Concepts That Must Not Be Equated

### 2.1 Wall-Clock Time

*Wall clock* is absolute calendar time, used to ask "What time is it now?". In Java:

~~~java
import java.time.Instant;

Instant now = Instant.now();
~~~

On common JVMs, this call relies on the system clock. That clock can be adjusted by an NTP daemon, hypervisor, or operator. SAML/JWT validators rely on this kind of time when comparing validity start and expiration timestamps.

### 2.2 Monotonic Time

Use `System.nanoTime()` when measuring **elapsed intervals** within the same JVM:

~~~java
long started = System.nanoTime();
// Perform operation...
long elapsedNanos = System.nanoTime() - started;
~~~

`nanoTime()` is not a Unix epoch timestamp and cannot be compared directly with JWT `exp` or SAML `NotBefore`. A monotonic clock is designed for elapsed time, avoiding many consequences of wall-clock jumps. Specific behavior across suspend/slew depends on the OS/JVM.

### 2.3 Timezone Differs from Clock Offset

- `2026-11-07T12:00:00Z` is a **UTC instant**.
- `Asia/Ho_Chi_Minh` renders that instant as local wall time.
- Switching timezone from GMT+7 to UTC **does not make a host skewed by 90 seconds accurate**.
- JWT `NumericDate` is seconds since the Unix epoch—never add/subtract 7 hours manually.
- SAML timestamps must be parsed with proper XML offset/timezone handling; never treat a UTC string as a timezone-less `LocalDateTime`.

### 2.4 Offset, Drift, and Allowance

| Term | Meaning | Common units |
| --- | --- | --- |
| Clock offset | Difference between host clock and reference source | ms, s |
| Drift | Gradually growing divergence from oscillator/system | ms/min, ppm |
| Frequency correction | Clock rate adjustment | ppm |
| Root dispersion | Accumulated uncertainty from the time-source chain | s |
| Network delay/RTT | Transmission delay of NTP messages | ms |
| Protocol clock skew/leeway | Timestamp discrepancy accepted by a validator | `Duration` |
| Time step | Immediate one-shot clock adjustment | s |
| Time slew | Adjusting rate so the clock converges gradually | ppm, time |
| Synchronization status | Whether tracking a valid time source | state/flag |

**Critically important:** the `Skew` field in ppm from `chronyc tracking` is *frequency uncertainty*, **not** Spring Security's `clockSkew`, which is a `Duration`.

## 3. Architecture of Parties That Must Stay Synchronized

~~~mermaid
flowchart LR
  T[Approved NTP/NTS time sources]
  T --> I[IdP/Authorization Server nodes]
  T --> S[Spring SP/OIDC Client/API nodes]
  T --> K[Kerberos KDC/DC nodes]
  T --> D[DB/Redis/Queue/Schedulers]
  I -->|SAML/JWT timestamps| S
  K -->|Kerberos tickets| S
  D -->|TTL, replay state, sessions| S
~~~

| Component | Relies on time for | Consequence of drift |
| --- | --- | --- |
| SAML IdP | Signing Assertion, `IssueInstant`, Conditions | Response issued with timestamps SP misjudges |
| SAML SP | Conditions, bearer confirmation, request state | Valid signature yet authentication fails |
| OIDC Provider | `iat`, `exp`, `auth_time`, optional `nbf` | ID Token judged too early or expired |
| OAuth2 Resource Server | JWT `exp`, `nbf`, custom policies | 401s on only some pods |
| KDC / Kerberos service | Ticket/authenticator timestamps | Clock skew/replay errors |
| CAS server/registry | Ticket/TGT lifetimes, TTL | ST viewed as expired or not yet valid |
| TLS peer | X.509 notBefore/notAfter | Certificate not yet valid/expired |
| Redis, DB, scheduler | Expiry, TTL, retention, event ordering | Abnormal session expiry, hard-to-audit logs |
| VM / Kubernetes node | Provides wall clock to workloads | Multiple pods skewed together |

IdP A and SP B might **both drift** +5 minutes from UTC and login temporarily succeeds; that does not prove the time service is trustworthy. Third parties, certificates, KDCs, or token consumers on other nodes can still fail. The goal is synchronizing to a governed standard reference, not two systems happening to agree by coincidence.

## 4. SAML: Timestamp Checkpoints

An illustrative XML structure:

~~~xml
<saml:Assertion
    xmlns:saml="urn:oasis:names:tc:SAML:2.0:assertion"
    ID="_assertion-1"
    Version="2.0"
    IssueInstant="2026-11-07T12:00:00Z">
  <saml:Issuer>https://idp.example.org</saml:Issuer>
  <saml:Subject>
    <saml:NameID>opaque-user</saml:NameID>
    <saml:SubjectConfirmation
        Method="urn:oasis:names:tc:SAML:2.0:cm:bearer">
      <saml:SubjectConfirmationData
          Recipient="https://sp.example.org/login/saml2/sso/idp"
          InResponseTo="_request-1"
          NotOnOrAfter="2026-11-07T12:04:00Z"/>
    </saml:SubjectConfirmation>
  </saml:Subject>
  <saml:Conditions
      NotBefore="2026-11-07T11:59:30Z"
      NotOnOrAfter="2026-11-07T12:05:00Z">
    <saml:AudienceRestriction>
      <saml:Audience>https://sp.example.org/metadata</saml:Audience>
    </saml:AudienceRestriction>
  </saml:Conditions>
</saml:Assertion>
~~~

**Note:** This XML merely illustrates fields; it has **no XML Signature**, is not a valid SAML Response, and must never be used to establish a login session.

### Meaning of Each Field

- `Assertion@IssueInstant`: when the IdP created the assertion.
- `Response@IssueInstant`: when the IdP created the response.
- `Conditions@NotBefore`: the assertion must not be used before this instant per validation policy.
- `Conditions@NotOnOrAfter`: the assertion must not be used at or after this instant (exclusive).
- `SubjectConfirmationData@NotOnOrAfter`: deadline for bearer confirmation; may be shorter than Conditions.
- `SubjectConfirmationData@InResponseTo`: correlation with the AuthnRequest in SP-initiated flow.
- `AuthnStatement@AuthnInstant`: when the IdP actually authenticated the user, distinct from assertion issue time.
- `AuthnStatement@SessionNotOnOrAfter`: IdP SAML session hint per profile; does not mean every SP `HttpSession` terminates immediately.
- `AuthnRequest@IssueInstant`: when the SP created the request; may tie into request-freshness policies.

### Conditions and SubjectConfirmation Must Be Checked Independently

If:
- `Conditions@NotOnOrAfter = 12:05:00`
- `SubjectConfirmationData@NotOnOrAfter = 12:04:00`
- SP currently reads `12:04:30`

then bearer SubjectConfirmation may be invalid even though Conditions has not expired. You cannot test only Conditions and skip bearer rules.

### Difference Between Time and Trust

A SAML Assertion with valid timestamps but missing a valid signature, wrong issuer, or wrong audience must still be rejected. Conversely, a valid XML Signature **does not skip** checking Conditions, Recipient, and correlation.

## 5. Spring SAML2: Configuring Tolerance by Version

Current Spring Security docs illustrate `OpenSaml5AuthenticationProvider.AssertionValidator` and the `.clockSkew(Duration)` builder. A skeleton for a Spring Security 7.x project **with verified matching API**:

~~~java
package com.example.saml;

import java.time.Duration;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.authentication.ProviderManager;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.saml2.provider.service.authentication.OpenSaml5AuthenticationProvider;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class SamlTimeConfiguration {

    @Bean
    SecurityFilterChain security(HttpSecurity http) throws Exception {
        var provider = new OpenSaml5AuthenticationProvider();
        var validator =
                OpenSaml5AuthenticationProvider.AssertionValidator
                        .builder()
                        .clockSkew(Duration.ofSeconds(45))
                        .build();
        provider.setAssertionValidator(validator);

        http.authorizeHttpRequests(auth -> auth
                .anyRequest().authenticated());
        http.saml2Login(saml -> saml
                .authenticationManager(new ProviderManager(provider)));
        return http.build();
    }
}
~~~

**This is a Spring integration snippet**, not standalone Java 17: it requires Spring Security SAML2/OpenSAML dependencies, a registration repository, SP/IdP metadata, and verification credentials. Spring Security 6.x uses `OpenSaml4AuthenticationProvider`/version-dependent APIs; **do not copy 7.x code verbatim into 6.x** without checking.

`Duration.ofSeconds(45)` is an **illustrative choice**, not a SAML default. Docs may use 10 minutes to illustrate the API, **not as a recommendation to open a 10-minute window in production**.

### Preserve the Full Verification Suite When Customizing

- Default signature/trusted verification credential checks must remain active.
- Issuer, Destination, AudienceRestriction, bearer Recipient, and InResponseTo must be retained.
- `NotBefore`/`NotOnOrAfter` validation must remain active.
- OneTimeUse/replay policy, if required, must be preserved; never assume OpenSAML includes a global distributed replay cache in every version.
- Never replace a custom validator with a stub that always returns success.
- Test with **signed negative fixtures**; never use `@WithMockUser` to prove the SAML verifier works.

### Loosening Tolerance Does Not Fix the Clock

If an SP is actually 3 minutes fast, raising assertion validator clock skew from 30 seconds to 5 minutes may make login "stop failing" temporarily, yet:
- The effective TTL/replay window widens across checks that apply skew.
- Other systems (TLS, KDC, Resource Servers) remain out of sync.
- The NTP root cause stays hidden and worsens over time.
- Security approvals and true SLOs become unclear.

Fix the time source **first**; widen skew only when genuinely required for interoperability with an IdP under an agreed profile and risk review.

## 6. OIDC: Distinguishing iat, nbf, exp, and auth_time

An ID Token may contain:

~~~json
{
  "iss": "https://idp.example.org",
  "sub": "user-123",
  "aud": "portal-client",
  "iat": 1794052800,
  "exp": 1794053100,
  "auth_time": 1794052770
}
~~~

This is merely illustrative JSON claims, **not a validly signed JWT**. `NumericDate` values are Unix epoch timestamps, not local time.

| Claim | Meaning | Interpretation |
| --- | --- | --- |
| `exp` | Expiration time, exclusive per JWT | Once current time reaches `exp`, the token is invalid without leeway |
| `nbf` | Not valid before this time | May be optional depending on token/profile |
| `iat` | Time the token was issued | Not automatically identical to `nbf` or `auth_time` |
| `auth_time` | Time the end user actually authenticated | Critical for `max_age`/step-up/fresh login |
| `nonce` | Binds response to login request | Not a clock measurement |
| `iss` | Trusted issuer | Accurate clocks do not replace issuer verification |
| `aud` | Client receiving the ID Token | Not replaced by skew |
| `state` | OAuth2 authorization flow correlation/CSRF | Has its own state TTL, distinct from JWT expiration |

**Do not use an ID Token as an API access token.** A Resource Server accepts an OAuth2 Access Token per contract; an OIDC client validates an ID Token per OIDC rules. Spring's `JwtTimestampValidator` API in a Resource Server is not necessarily the exact API used by OIDC login ID Token validation.

### auth_time and max_age

A newly issued ID Token may rely on an older session at the IdP. Thus `iat` can be brand new while `auth_time` is old. If the app demands reauthentication via `max_age`/step-up, check `auth_time` freshness per OIDC profile—never pass just because `exp` has not elapsed.

A skewed host can cause:
- ID Tokens judged expired;
- ID Tokens judged issued in the future under custom policies;
- `max_age`/freshness misjudged;
- Abnormal logout/refresh scheduling.

Never drop `nonce`, `state`, signature, or `iss` checks because of timestamp tuning.

## 7. OAuth2 Resource Server JWT in Spring Security

With Spring Boot Resource Server:

~~~yaml
spring:
  security:
    oauth2:
      resourceserver:
        jwt:
          issuer-uri: https://idp.example.org
~~~

This snippet omits API audience policies, token types, scopes, and custom rules. Current Spring Security Servlet docs state that Resource Server validates signatures along with `iss`, `exp`, and `nbf` per configuration, with a **default clock skew of 60 seconds**. Verify your exact version and custom decoder; never assume 60 seconds is the default for SAML, Kerberos, or CAS.

### Custom Timestamp Validator

~~~java
package com.example.jwt;

import java.time.Duration;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.oauth2.core.DelegatingOAuth2TokenValidator;
import org.springframework.security.oauth2.core.OAuth2TokenValidator;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.security.oauth2.jwt.JwtDecoder;
import org.springframework.security.oauth2.jwt.JwtDecoders;
import org.springframework.security.oauth2.jwt.JwtIssuerValidator;
import org.springframework.security.oauth2.jwt.JwtTimestampValidator;
import org.springframework.security.oauth2.jwt.NimbusJwtDecoder;

@Configuration
public class JwtTimeConfiguration {

    private static final String ISSUER = "https://idp.example.org";

    @Bean
    JwtDecoder decoder() {
        NimbusJwtDecoder decoder = (NimbusJwtDecoder)
                JwtDecoders.fromIssuerLocation(ISSUER);

        OAuth2TokenValidator<Jwt> validator =
                new DelegatingOAuth2TokenValidator<>(
                        new JwtTimestampValidator(Duration.ofSeconds(45)),
                        new JwtIssuerValidator(ISSUER));
        decoder.setJwtValidator(validator);
        return decoder;
    }
}
~~~

**Security limitations of this snippet:**
- It illustrates `JwtTimestampValidator` and `JwtIssuerValidator`, **not a complete Resource Server configuration**.
- `setJwtValidator(...)` replaces the decoder's validator composition. **Do not accidentally drop** audience validators, token-type checks, custom required-claim checks, or version-appropriate defaults. If you combine `JwtValidators.createDefaultWithIssuer(...)` with another timestamp validator, the default validator may still veto tokens so the new skew does not behave as expected.
- `45 seconds` is an assumed number that must be approved and tested.
- Signature/JWKS validation must still hold; never trust an issuer URL from user input.
- Use `NimbusReactiveJwtDecoder` and reactive APIs when the application uses WebFlux.
- With opaque token introspection, validity may be decided at the Authorization Server/introspection service rather than this validator.
- **Never take a truly expired JWT and widen skew by hours** to bypass expiration.

### Simple Time-Window Model

Given `notBefore`, `expiresAt`, tolerance `s`, and time `now`, a simple validator model with leeway is:

~~~text
now + s >= notBefore
now - s <  expiresAt
~~~

This formula **illustrates general behavior**; it does not replace API docs or Spring's exact boundary/claim-presence policy. `exp`/`nbf` claims may be optional or required depending on token profile and validator. If token expiry is mandatory, check the specific validator/version rather than assuming.

### Where Multi-Pod Failures Commonly Appear

~~~text
Token expires at:   12:00:30Z
Pod A clock:        12:00:10Z -> ACCEPT
Pod B clock:        12:02:00Z -> EXPIRED
Load balancer:      200, 401, 200, 401...
~~~

Validation tolerance can change the outcome depending on skew size, yet the root cause is time on the host node. Never extend token lifetimes or enable infinite login retries before checking NTP.

## 8. Kerberos and Windows Domains

Kerberos uses timestamps in authenticators and tickets to prevent replay and bound age. Client, KDC/domain controller, and service server must remain within policy limits. Microsoft documents the default Kerberos `SkewTime` as typically around **5 minutes** in Windows/AD; the exact value depends on domain policy and implementation.

### Symptoms

- Kerberos/SPNEGO login fails with errors such as `KRB_AP_ERR_SKEW`.
- A client logs in when talking to DC A but fails on DC B.
- VM snapshot/restore or machine resume introduces a large offset.
- A service ticket is issued, yet the application server rejects the authenticator timestamp.
- Spring Security Kerberos extensions relying on OS/JVM GSS/Kerberos fail even while other OAuth2/SAML apps work.

**Do not widen domain-wide Kerberos policy from 5 minutes to 30 minutes just so one drifted machine can log in.** Instead, check the time source on client, target server, and KDCs; check SPN, keytab, and realm/DNS if the real failure is not clock-related.

### Differences from SAML/JWT

`JwtTimestampValidator` does not adjust KDC clock skew. Nor does `OpenSaml5AuthenticationProvider` govern Kerberos clock tolerance. Each protocol has its own cryptographic freshness model and does not share a single global "clock-skew" property.

## 9. CAS and Ticket Expiration

CAS Service Tickets (STs) are typically short-lived and one-time use. CAS Ticket Granting Tickets (TGTs) also have lifetime/idle policies depending on CAS server/version. Clock drift on the CAS cluster or ticket registry can make tickets appear prematurely expired or late.

- Do not assume an ST is a JWT carrying `nbf`/`exp` claims.
- Check the specific CAS server ticket registry, TTLs, and expiration policy.
- Verify CAS Server nodes have synchronized clocks, especially when a load balancer switches nodes.
- Validate Service Tickets at the **right CAS server and exact service ID**; service URL or ticket-reuse bugs cannot be fixed by NTP.
- Coordinate logout/session token behavior per CAS SLO implementation rather than assuming every Spring HttpSession expires with the TGT.

## 10. TLS and X.509 Are Another Reason Accurate Time Matters

If a host runs 10 days fast, it may treat a certificate as "expired"; if days slow, it may see a new certificate as "not yet valid." TLS/JWKS/metadata fetch failures then happen **before** SAML/JWT validation.

Distinguish the actions needed:
- Actually expired certificate: **rotate/reissue** the certificate, never roll the clock backward.
- Wrong host clock: fix NTP/Windows Time.
- Wrong trust chain/hostname: fix PKI/trust config.
- SAML signing certificate rotation: update trust and metadata per IdP/SP contract.
- Stale OAuth2 JWKS cache: handle key rotation and caching rather than blaming time skew.

**Clock-skew allowance in SAML/JWT cannot substitute for X.509 certificate validity, TLS trust, or other subsystems.**

## 11. NTP: Estimated Offset and Network Delay

NTP uses four timestamps in its model:
- `t1`: client sends request;
- `t2`: server receives request;
- `t3`: server sends response;
- `t4`: client receives response.

Two foundational formulas:

~~~text
Estimated offset (server minus client):
  theta ≈ ((t2 - t1) + (t3 - t4)) / 2

Round-trip delay:
  delta ≈ (t4 - t1) - (t3 - t2)
~~~

Example in milliseconds:

~~~text
t1=0, t2=525, t3=527, t4=52
theta = ((525-0)+(527-52))/2 = +500ms
delta = (52-0)-(527-525)    =   50ms
~~~

In this model example the server is 500ms ahead of the client. Yet network paths are not always symmetric, jitter occurs, and source devices have error. NTP/chrony collects multiple samples across multiple sources to select a reference and estimate uncertainty. **A single round-trip or HTTP Date header cannot prove accurate UTC.**

### Stratum Is Not a Direct Measure of Accuracy

A stratum-2 source with heavy network jitter can be worse than a stable stratum-3 source. Beyond stratum, examine:
- Root delay and root dispersion;
- Reachability and last received;
- Source selection/falsetickers;
- Offset estimates and RMS variation;
- Source trustworthiness, NTS, or trusted infrastructure;
- Uptime/boot drift and VM hypervisors;
- Cross-source consistency.

## 12. Time Synchronization Models

| Model | Suitable for | What to watch |
| --- | --- | --- |
| NTP client to approved servers | Most Linux/Windows/Cloud hosts | Sources, network path, backups |
| NTS-protected NTP | Sources supporting NTS with capable clients | NTS-KE/TLS trust and connectivity |
| Corporate NTP hierarchy | Enterprise/domain networks | Avoid random public pools |
| Managed cloud time service | Cloud VMs/nodes | Provider docs, network/DNS, guest agents |
| PTP | Ultra-time-sensitive workloads with supported infra | NIC/switch/grandmaster; not needed by default for SSO |
| RTC hardware clock | Boot/offline retention | Never replaces ongoing NTP |
| Hypervisor guest-time integration | VM lifecycle | Coordinate to avoid conflicting clock adjustments |

Accurate time is a **security dependency**. A spoofed/compromised time server can affect token validity and audit logs. Use trusted sources and consider NTS support where appropriate; **not every NTP server supports `nts`**.

## 13. Linux with chrony: Safe Inspection Commands

On a host running `chronyd`:

~~~bash
date -u
timedatectl status
chronyc tracking
chronyc sources -v
chronyc sourcestats -v
~~~

These commands are read-only inspection tools. If the daemon is not installed or the service is unused, `chronyc` may error; that alone does not prove the host is unsynchronized, as it may use `systemd-timesyncd` or another time service.

### Reading chronyc tracking Output

Illustrative **simulated** output:

~~~text
Reference ID    : C0A8010A (ntp-a.example.org)
Stratum         : 3
Ref time (UTC)  : Sat Nov 07 12:00:00 2026
System time     : 0.000850000 seconds fast of NTP time
Last offset     : +0.000230000 seconds
RMS offset      : 0.000400000 seconds
Frequency       : 3.150 ppm fast
Residual freq   : +0.020 ppm
Skew            : 0.160 ppm
Root delay      : 0.016000000 seconds
Root dispersion : 0.002000000 seconds
Update interval : 64.0 seconds
Leap status     : Normal
~~~

Explanation:
- `Reference ID`: active time source.
- `Stratum`: logical NTP tier.
- `Ref time (UTC)`: most recent reference timestamp.
- `System time`: estimated divergence of the system clock from NTP time.
- `Last offset`: offset measured at the most recent update.
- `RMS offset`: long-term offset variance.
- `Frequency`: oscillator correction.
- `Residual freq`: remaining frequency error.
- `Skew`: frequency uncertainty **in ppm**.
- `Root delay`: estimated delay to the root source.
- `Root dispersion`: accumulated timing uncertainty.
- `Update interval`: interval between updates.
- `Leap status`: synchronization/leap state.

A running `chronyd` process whose `Leap status` indicates unsynchronized or whose `Ref time` is stale still warrants investigation. A small `System time` **does not guarantee** the time source reflects true UTC if upstream is wrong.

### Reading chronyc sources -v

Common symbols:
- `^*`: currently selected NTP source;
- `^+`: valid source combined into the estimate;
- `^-`: valid source not selected for combining;
- `^?`: insufficient data or unreachable;
- `^x`: classified as a falseticker;
- `^~`: overly variable.

Also inspect `Reach`, `LastRx`, offset/uncertainty, and whether the source is on the allowlist. Never grep for `^*` alone and assume all SSO security timers are safe.

### Reading chronyc sourcestats -v

Per-source statistics help detect:
- A drifting upstream;
- Jitter/packet loss;
- Disagreement across multiple sources;
- VM oscillator drift;
- Falsetickers appearing after network changes.

Good monitoring tracks **both current offset and trends**, not service status alone.

## 14. Controlled Chrony Configuration

Example `chrony.conf` for a Linux host:

~~~conf
# Example internal-network hostnames; not real time sources.
server ntp-a.corp.example.org iburst
server ntp-b.corp.example.org iburst
server ntp-c.corp.example.org iburst

driftfile /var/lib/chrony/drift
makestep 1.0 3
rtcsync
~~~

Explanation:
- `iburst` speeds up initial sampling at startup;
- `driftfile` stores frequency correction;
- `makestep 1.0 3` permits stepping large offsets during the **initial updates** per chrony semantics;
- `rtcsync` governs RTC/kernel sync state updates on supported platforms;
- config file path varies by distro: `/etc/chrony.conf` or `/etc/chrony/chrony.conf`;
- never replace corporate sources with public pools arbitrarily;
- never let `chronyd` and another daemon compete to adjust the same clock unless explicitly architected.

When the organization provides a multi-source pool:

~~~conf
pool ntp.corp.example.org iburst maxsources 4
driftfile /var/lib/chrony/drift
makestep 1.0 3
rtcsync
~~~

`maxsources` is how many sources chrony attempts to draw from the pool—it does not guarantee every source is healthy. When a supported NTS server and matching certificates exist:

~~~conf
server nts-time.corp.example.org iburst nts
driftfile /var/lib/chrony/drift
makestep 1.0 3
rtcsync
~~~

NTS configuration depends on chronyd build, NTS-KE/TLS trust, network ports, and server support. Do not add `nts` to a server that lacks support and assume NTP is "secure" while the client loses sync.

### What Not to Do

- Never run `date -s`, `timedatectl set-time`, or `chronyc makestep` on a live production host without analyzing impact.
- Never point sources to unmanaged machines.
- Never run two competing time daemons.
- Never judge success solely because `systemctl is-active chronyd` returns `active`.
- Never raise SAML/JWT skew to ignore NTP failures.

## 15. systemd-timesyncd or ntpd

On some Linux distros, `systemd-timesyncd` replaces chrony:

~~~bash
timedatectl status
timedatectl timesync-status
timedatectl show -p NTPSynchronized
~~~

`timesync-status`/property support depends on systemd version. An illustrative `/etc/systemd/timesyncd.conf`:

~~~ini
[Time]
NTP=ntp-a.corp.example.org ntp-b.corp.example.org
FallbackNTP=ntp-c.corp.example.org
~~~

This is not advice to run both chrony and timesyncd simultaneously. For `ntpd`/`ntpsec`, use the corresponding tools such as `ntpq -p` where available. Operations must identify the actual daemon and time hierarchy in use.

`timedatectl` may report the NTP service active, yet confirming **accurate synchronization** requires inspecting the source, offset, last successful update, and daemon logs. A live daemon does not equal an accurate clock.

## 16. Windows Time: w32tm, Domain Controllers, and PDC

In Windows/Active Directory, W32Time participates in the domain time hierarchy. Domain controllers/KDCs, domain members, and other Windows services must be checked against domain configuration.

Diagnostic commands:

~~~powershell
w32tm /query /status
w32tm /query /source
w32tm /query /peers
w32tm /query /configuration
~~~

On some systems/permission levels, an elevated command prompt is required; querying remote hosts follows separate policy.

### Common Scenarios

- PDC emulator has a wrong/broken external source, so all DCs receive bad time.
- A branch-office DC loses time sync yet continues issuing Kerberos tickets.
- Hypervisor/VM guest integration fights over clock adjustments.
- A VM snapshot restore brings back an old clock.
- NTP sources are unreachable due to network/firewall rules.
- Source changes via Group Policy, but one node has not picked it up.
- Windows Time service reports healthy status while an independent offset measurement is large.

**Do not configure each domain member to sync from arbitrary external time** when systems must follow the corporate AD hierarchy.

`w32tm /resync` is an active intervention, not a read-only check. Execute it only under a runbook/change approval, especially on KDCs, domain controllers, or service hosts with time-sensitive state. After resync, verify time source, offset, Kerberos, and SSO flows.

## 17. Kubernetes, Containers, and VMs: Find the Real Clock on the Node

Standard Linux containers share the host kernel's realtime clock. A container is not an independent hardware clock; the `TZ` environment variable or timezone package inside an image mainly affects display formatting.

### When One Node Drifts

~~~text
IdP clock     12:00:00Z
k8s node A    12:00:00Z   -> pod A login OK
k8s node B    12:00:00Z   -> pod B login OK
k8s node C    12:07:00Z   -> pod C SAML expired
Load balancer             -> alternating success/failure
~~~

Diagnosis:
1. Grab the `traceId` and map failed requests to the pod and Kubernetes node.
2. Check `date -u` inside the pod if needed, **but inspect NTP on the node/VM host**.
3. Compare `chronyc tracking` or time service status across nodes A/B/C.
4. Check autoscaling, VM migration, suspend/resume, and snapshot restores.
5. Check time-source/network reachability and node exporter metrics.
6. If impact is broad, SREs may cordon/drain the unhealthy node per runbook—not an automatic action for every alert.
7. Fix host time sync and recheck all pods before returning the node to traffic.

### Hypervisors Can Also Interfere

- Guest VM time and host time need compatible policies;
- VM resume/suspend can introduce large deltas;
- Competing guest agents and chronyd can trigger unwanted steps/slews;
- Cloud-managed time services have specific networking and regional settings;
- Never disable host/guest time integration based on generic tips without reading official cloud/hypervisor guidance.

When a Spring app runs on Kubernetes, **readiness** may depend on node time health per platform design, yet individual HTTP logins should never make synchronous external NTP calls on the request path.

## 18. Step vs Slew: Operational Choices with Risk

**Slew:** adjusts clock rate so offset converges gradually. Advantage: avoids large UTC jumps, though correcting large offsets takes longer.

**Step:** adjusts instantaneously. A large step can cause:
- Job schedulers firing repeatedly or skipping runs;
- Sudden changes in session expirations;
- JWT/SAML/certificates abruptly flipping to "expired/not yet valid";
- Out-of-order timestamps in logs;
- Inconsistent cache TTL/replay window evaluation;
- Hard-to-analyze ordering in databases/queues/audit events;
- Code measuring duration via wall clock getting negative or inflated values.

Therefore, instead of running `chronyc makestep` ad hoc in production:
1. Verify the source is right;
2. Measure actual offset and uncertainty;
3. Distinguish a freshly booting host not yet taking traffic from a live production node;
4. Coordinate with the platform owner and maintenance window;
5. If needed, isolate/drain the node before a large jump;
6. Choose step vs slew per change plan;
7. Verify NTP/SSO/sessions/schedulers after remediation;
8. Record the time adjustment in the audit/incident timeline.

## 19. Monitoring Offset Alone Is Insufficient: Multiple Signals Must Converge

| Metric/Signal | Role | Warning sign |
| --- | --- | --- |
| Estimated current offset | Host fast/slow vs reference | Exceeds target or climbing |
| Selected NTP source | Which source is tracked | Unfamiliar source / lost source |
| Last sync/reference age | How long since last update | Stale source |
| Root dispersion/maxerror | Uncertainty bound | High even when offset looks small |
| RMS offset/jitter | Stability | Growing variance |
| Frequency/skew ppm | Oscillator drift | Anomaly after VM event |
| Kernel time-sync flag | Kernel-reported sync state | Cross-check with daemon |
| Step/time-adjust events | Whether clock jumped | Sudden jump |
| SAML expired/not-before failures | App symptom | Correlate by node/IdP |
| JWT exp/nbf errors | API symptom | Correlate by node/token age |
| Kerberos skew errors | KDC/client/service | Correlate by site/DC |
| TLS certificate date errors | Clock or cert issue | Distinguish from rotation |
| Clock source network errors | NTP unreachable | UDP 123/NTS/TLS/DNS |

A host with a small current offset whose NTP source stopped updating and whose uncertainty is climbing can still trigger an incident within hours. Conversely, a "sync lost" metric can be misread if daemon/kernel flag integration behaves differently.

## 20. Prometheus node_exporter: timex Metrics

On Linux, `node_exporter` includes the `timex` collector. Common metrics include:
- `node_timex_offset_seconds`
- `node_timex_sync_status`
- `node_timex_maxerror_seconds`

Per `node_exporter` docs, `timex` reflects kernel state. **Some versions/daemons do not maintain the kernel sync flag identically**; with chrony, `rtcsync` plays a role. Thus never treat `node_timex_sync_status=0` alone as proof that NTP is broken without checking `chronyc tracking` and actual sources.

### Sample Prometheus Alert Rules

~~~yaml
groups:
  - name: time-synchronization
    rules:
      - alert: NodeClockOffsetWarning
        expr: abs(node_timex_offset_seconds) > 0.10
        for: 10m
        labels:
          severity: warning
        annotations:
          summary: "Clock offset above 100ms"
          description: "Inspect approved NTP source and chrony tracking"

      - alert: NodeClockOffsetCritical
        expr: abs(node_timex_offset_seconds) > 1
        for: 2m
        labels:
          severity: critical
        annotations:
          summary: "Clock offset above 1 second"
          description: "Assess SSO/JWT/Kerberos traffic"

      - alert: NodeTimeSyncFlagLost
        expr: node_timex_sync_status == 0
        for: 10m
        labels:
          severity: warning
        annotations:
          summary: "Kernel sync flag not set"
          description: "Cross-check chrony configuration and sources"
~~~

**100ms and 1s here are illustrative only**; each organization must choose thresholds based on SLOs, actual clock accuracy, traffic, token lifetimes, and protocol skew. High-precision deployments may need much tighter bounds.

### Additional Checks When Using These Rules

- Are metrics actually emitted by the `timex` collector?
- Do the kernel and exporter support those fields?
- Does the `instance` label map accurately to the Kubernetes node/VM?
- Do missing metrics/scrape failures alert separately instead of looking like zero offset?
- Does `node_timex_sync_status` actually reflect chrony state?
- Which daemon/exporter provides root dispersion, selected source, and last successful NTP poll?
- Do alerts account for startup grace periods and auto-scaling?
- Are duplicate alarms avoided for nodes currently draining?

**The goal is detecting drift before SSO fails**, not waiting until offset reaches several minutes to fire an alert.

## 21. Designing a Dashboard for Federation Investigations

An effective dashboard groups signals into:

**Time infrastructure**
- Offset by region/cluster/node;
- Positive/negative signed offset;
- Selected source/reachability;
- Root dispersion and last sync age;
- Frequency changes and clock step count;
- Windows time status/peer source;
- Approved-source compliance.

**Application symptoms**
- SAML conditions/subject-confirmation failure count by IdP alias and node;
- JWT expired/nbf invalid rate by API node;
- OIDC token time/freshness rejections by client;
- Kerberos clock skew errors by realm/DC;
- Certificate date errors;
- Authentication success/denied rates;
- Session/token expiry anomalies.

**Deployment context**
- Node restarts/VM restores;
- IdP/AS rollouts;
- NTP source configuration changes;
- Certificate rotations;
- Load-balancer distribution;
- JVM/Spring Security version differences;
- Region/zone.

Never use email, NameID, `sub`, raw JWTs, cookies, service tickets, or session IDs as metric labels. When failures come from provider exceptions, log **structured error categories** only where backed by reliable evidence—never guess from raw exception text or HTTP 302s.

## 22. Evaluating Alarms: Accurate NTP Source or Confidently Wrong?

A daemon can be synchronized to an upstream server that is **wrong relative to UTC**. Therefore:
- Verify the source is on the approved trust list.
- Use multiple sources (per network policy) to detect disagreement.
- Inspect stratum, yet **never treat low stratum as a guarantee of accuracy**.
- Watch root dispersion, RTT, and measurement uncertainty.
- Where policy demands, compare against an independent reference or NTS/PTP source.
- Check clocks on both IdP/AS and SP/Resource Server; never check only one side.
- Never treat an HTTP `Date` header as a UTC oracle without knowing trust, latency, and caching.

### Do Not Confuse Latency with Clock Skew

If the IdP generates a SAML Response at 12:00:00 and the browser submits it at 12:04:30 against a 12:04:00 expiration:
- The user may have paused on MFA or in a browser tab;
- The browser/queue/proxy may have been slow;
- The IdP may have set too short a bearer lifetime;
- The SP clock may be fast;
- The Response may be an old static test fixture.

Measure network/browser latency and clock offset independently. **Do not increase skew when the user genuinely submitted an assertion too late** if security policy forbids it.

## 23. Incident: SAML `NotBefore` in the Future

Suppose a SAML Response is validly signed yet the provider reports Conditions are not yet valid.

Runbook:
1. Identify the IdP registration, the node handling ACS, and the UTC timestamp.
2. Verify signature/issuer/audience/recipient first so failures are not misclassified.
3. Read `chronyc tracking`/time service on that SP node.
4. If authorized, check the IdP host clock/time source.
5. Identify the exact rejected field: Conditions `NotBefore`, SubjectConfirmation expiry, `IssueInstant` policy, or request correlation.
6. Separate browser delay from clock offset.
7. Fix any NTP/VM issue uncovered.
8. Retest with a **valid signed fixture**, never modifying XML after signing.
9. Consider adjusting SAML skew under an approved contract only if time sources are healthy yet reasonable minor variance remains.

**Never remove Conditions from assertions or disable signature validation to make login pass.**

## 24. Incident: Random JWT 401s Across Pods

Symptoms:
- The same token hitting the same API alternates between 200 and 401.
- Structured errors indicate invalid `exp` or `nbf` on a subset of pods.
- Signatures/issuer/audience are valid.

Steps:
1. Map request trace → pod → host node.
2. Compare token issue/expiry against a trusted reference clock, **without logging raw tokens**.
3. Verify whether custom `JwtTimestampValidator`/decoder/skew configs are identical across pods.
4. Check node offset, selected source, root dispersion, and VM resume events.
5. Check downstream network/time daemon connectivity.
6. If a node is badly skewed, contain/drain per change plan.
7. Fix NTP and verify with positive + negative JWT tests.
8. Investigate whether remaining 401s are **genuinely expired tokens** rather than assuming "every 401 is clock skew."

Never extend JWT lifetimes or refresh-token policies just to mask a single skewed node.

## 25. Incident: Kerberos/SPNEGO Fails After VM Restore

A restored old VM snapshot may carry a guest clock from the past:
1. Check UTC on the guest, hypervisor, and KDC/domain controllers.
2. Inspect `w32tm` or chrony status/offset.
3. Check whether the time source changed after restore.
4. Confirm the true Kerberos error (`KRB_AP_ERR_SKEW` vs SPN/keytab).
5. If a clock step is needed, assess impact and isolate/drain the node first.
6. Resync per runbook.
7. Test with fresh tickets/logins; cached tickets can mislead.
8. Check other services sharing that VM: TLS, JWT, and DB audits.

Loosening Kerberos domain policy by tens of minutes is not a professional fix.

## 26. Distinguishing Clock Failures from Other SSO Errors

| Error | Possibly clock-related? | What to verify |
| --- | --- | --- |
| SAML NotBefore / NotOnOrAfter | Yes | Signed SAML, IdP/SP clocks, browser delay |
| SAML Signature invalid | Not fixed by clockSkew | Signing key/trust/XML references |
| SAML wrong Audience | No | Entity ID/SP registration |
| SAML Recipient/Destination wrong | No | Public ACS/proxy forwarded host |
| SAML InResponseTo mismatch | Not directly | Saved AuthnRequest/session/RelayState |
| JWT exp/nbf | Yes | Token timestamps and Resource Server clock |
| JWT wrong issuer/audience | No | Trusted issuer/client/API config |
| OAuth2 state/nonce invalid | Not directly | Browser session/correlation |
| Kerberos skew error | Usually | Client/service/KDC clocks |
| Kerberos principal unknown | No | SPN/realm/keytab |
| CAS ticket expired | Possibly | CAS ticket TTL and network/browser delay |
| TLS cert not-yet-valid | Possibly | Host clock and cert validity |
| 302 login loop | Possibly, not certain | Cookies/CSRF/metadata/redirect/session |
| Wrong Redis/session TTL | Possibly | Store clock/expiry semantics |

Never change a global "skew" property merely upon seeing `authentication_failed`. Classify failures at the **exact validation layer**.

## 27. Deterministic Timestamp Testing with `Clock.fixed`

When writing custom services that check deadlines or token issued age, inject `Clock` instead of hardcoding `Instant.now()`:

~~~java
import java.time.Clock;
import java.time.Instant;
import java.time.ZoneOffset;

Clock testClock = Clock.fixed(
        Instant.parse("2026-11-07T12:00:00Z"),
        ZoneOffset.UTC);
Instant current = testClock.instant();
~~~

Using a test clock lets you test boundaries without sleeping for seconds via `Thread.sleep` or changing the OS clock. `JwtTimestampValidator` in current Spring Security APIs offers `setClock(Clock)`; use it only after confirming the method/version and ensuring the entire decoder composition uses that instance.

### Boundary Test Matrix

| Test | Expectation |
| --- | --- |
| `now` before `nbf` beyond skew | Reject |
| `now` exactly at `nbf` | Per exact validator boundary |
| `now` inside window | Pass time check |
| `now == exp` with zero skew | Reject per exclusive expiry semantics |
| `now` past exp beyond skew | Reject |
| `now` slightly outside within approved skew | Accepted per policy |
| Future `iat` | Per custom OIDC/JWT policy, do not assume |
| `auth_time` too old for `max_age` | Force fresh authentication |
| SAML bearer expiry earlier than Conditions expiry | Must honor bearer deadline |
| Signed SAML fixture with wrong time | Rejected **for time**, not broken signature |
| Replay before expiry | Per OneTimeUse/correlation/replay policy |
| Multi-node JVMs with time skew | Detect diverging decisions and fix node |

**Never edit a time field in signed XML/JWT after signing and cite the resulting rejection as proof of the time validator**: the signature breaks. Generate wrong-time fixtures **before signing validly with a test key**, keeping all other conditions valid.

## 28. Standalone Java 17 Program: Simulating Leeway

The program below uses the **Java Standard Library**, requires no Spring, and verifies neither SAML nor JWT signatures. It clarifies timestamp comparison and the effect of a fast host.

Create `ClockSkewDemo.java`:

~~~java
import java.time.Clock;
import java.time.Duration;
import java.time.Instant;
import java.time.ZoneOffset;

public final class ClockSkewDemo {

    private static String validateWindow(
            Instant now,
            Instant notBefore,
            Instant expiresAt,
            Duration leeway) {

        if (leeway.isNegative()) {
            throw new IllegalArgumentException("negative leeway");
        }
        if (now.plus(leeway).isBefore(notBefore)) {
            return "TOO_EARLY";
        }
        if (!now.minus(leeway).isBefore(expiresAt)) {
            return "EXPIRED";
        }
        return "ACCEPT_TIME_ONLY";
    }

    private static long offsetMillis(
            Instant local, Instant reference) {
        return Duration.between(reference, local).toMillis();
    }

    public static void main(String[] args) {
        Instant reference =
                Instant.parse("2026-11-07T12:00:00Z");
        Clock fixed = Clock.fixed(reference, ZoneOffset.UTC);
        Instant correctNow = fixed.instant();
        Instant fastHostNow = reference.plusSeconds(90);

        Instant notBefore = reference.minusSeconds(10);
        Instant expiresAt = reference.plusSeconds(45);

        System.out.println("Reference UTC: " + correctNow);
        System.out.println("Fast host offset ms: "
                + offsetMillis(fastHostNow, reference));

        System.out.println("Correct, skew=0: "
                + validateWindow(correctNow, notBefore, expiresAt,
                        Duration.ZERO));
        System.out.println("Fast, skew=0: "
                + validateWindow(fastHostNow, notBefore, expiresAt,
                        Duration.ZERO));
        System.out.println("Fast, skew=60s: "
                + validateWindow(fastHostNow, notBefore, expiresAt,
                        Duration.ofSeconds(60)));

        System.out.println("Very old, skew=60s: "
                + validateWindow(reference, notBefore,
                        reference.minusSeconds(180),
                        Duration.ofSeconds(60)));

        System.out.println("Future nbf, skew=60s: "
                + validateWindow(reference,
                        reference.plusSeconds(120),
                        reference.plusSeconds(300),
                        Duration.ofSeconds(60)));

        System.out.println("At exp boundary, skew=0: "
                + validateWindow(reference.plusSeconds(45),
                        notBefore, expiresAt, Duration.ZERO));

        System.out.println("In UTC: "
                + correctNow.atOffset(ZoneOffset.UTC));
    }
}
~~~

Run:

~~~bash
javac ClockSkewDemo.java
java ClockSkewDemo
~~~

**Exact** stdout:

~~~text
Reference UTC: 2026-11-07T12:00:00Z
Fast host offset ms: 90000
Correct, skew=0: ACCEPT_TIME_ONLY
Fast, skew=0: EXPIRED
Fast, skew=60s: ACCEPT_TIME_ONLY
Very old, skew=60s: EXPIRED
Future nbf, skew=60s: TOO_EARLY
At exp boundary, skew=0: EXPIRED
In UTC: 2026-11-07T12:00Z
~~~

**Explanation:** The host is 90s fast. The token has `exp=12:00:45Z`. The host reads 12:01:30Z, seeing the token as 45s past expiry. With a 60s tolerance, the time-only check still accepts. This **does not fix the clock offset**—it merely widens the validation window. On an accurate host, the token is accepted up to its nominal deadline.

**Limitations:**
- Simulates only a symmetric-leeway `nbf`/`exp` window; exact boundaries and required claims vary across libraries.
- Verifies neither signature, issuer, audience, recipient, full SAML Conditions, OAuth2 state, nor OIDC nonce.
- Does not measure NTP on a real host.
- Does not demonstrate replay caches, token revocation, or global policy.
- `ACCEPT_TIME_ONLY` **does not mean Authentication is valid**.
- This is a standalone program; the Spring Security snippets above require their own project/dependencies.

## 29. Integration Tests and Skew Experiments in a Safe Environment

### Unit/Service Tests
- Inject `Clock.fixed` into business expiration logic;
- Create exact expiry and not-before boundary cases;
- Verify timezone serialization and UTC Instants;
- Confine fake time to test scope—never alter production OS clocks.

### SAML Verifier Tests
- Use a test IdP signing key/certificate;
- Build Responses/Assertions with valid and invalid conditions;
- Sign **after** setting timestamps;
- Keep issuer/audience/recipient/InResponseTo accurate;
- Verify the actual OpenSAML provider response;
- Never use `@WithMockUser` as proof of SAML signature/time validation.

### OIDC/JWT Verifier Tests
- Use a test Authorization Server/JWKs and signed tokens;
- Supply tokens with `nbf`, `exp`, `iat`, `auth_time` on boundaries;
- Keep issuer/audience/nonce valid to isolate the time validator;
- Test expiration and refresh behavior on the proper token type;
- For opaque tokens, test introspection/AS semantics rather than faking JWTs.

### Staging Infrastructure Tests
- Simulate a skewed node in an **isolated/approved environment**;
- Test SSO traffic across every node;
- Test clock step/slew, VM suspend/resume, and NTP outages/source changes;
- Test HPA/node autoscaling and restart recovery;
- Verify monitoring marks a host unready when offset exceeds policy;
- Never alter clocks on production KDCs/IdPs or shared CI hosts.

## 30. Alerts and SLOs: Detect Drift Before Users Cannot Log In

A target design:
- `measured steady-state offset` must be **much smaller** than `allowed protocol skew`;
- Warning alarms fire well before offset consumes most of the allowance;
- A separate alert fires for **stale/un-updated NTP sources** even if current offset looks small;
- Root dispersion/uncertainty stays within acceptable limits;
- Security-critical services stop receiving traffic if the clock becomes untrusted per readiness policy;
- Incident response balances availability **and** the risk of replay/accepting expired tokens.

**The 100ms, 1s, or 10m values in examples are not universal company standards**. Windows KDCs default to a few minutes' tolerance; SAML bearer SubjectConfirmation may live only a few minutes; API token TTLs can also be short. Choose thresholds using actual measurements, threat models, and network topology.

### Which Events Need Alerts?

1. Rapidly growing `abs(offset)`.
2. Offset crossing warning/critical thresholds.
3. A node selecting a source outside the approved set.
4. Sustained growth in root dispersion/maxerror.
5. No selected sync source.
6. Kernel sync flag lost, after confirming daemon semantics.
7. Node exporter missing timex metrics.
8. VM resume/clock step occurred.
9. IdP/SP SAML time failures rising on a specific node.
10. Abnormal increase in JWT expired/nbf errors.
11. Kerberos skew errors rising at a DC/site.
12. TLS "not yet valid" errors coinciding with time alarms.

### Avoid Information Leakage in Logs/Metrics

Record trace ID, node, region, IdP alias, evidence-backed validator error category, and UTC timestamp. **Never** log raw JWTs, SAML Assertions, CAS tickets, passwords, private keys, emails, or session IDs to public telemetry. Never use `sub`/NameID/email as high-cardinality metric labels.

## 31. Time Synchronization Incident Runbook

**Step 1 — Scope the impact.** Which apps? IdP/AS/SP/KDC/DB? Single node or multiple nodes? When did it start? Does it correlate with a deploy or VM resume?

**Step 2 — Identify the exact failure.** Signature/issuer/audience failure differs from NotBefore/NotOnOrAfter. Kerberos skew differs from SPN failure. TLS not-yet-valid differs from unknown certificate chain.

**Step 3 — Read host clocks.** Linux: `date -u`, `chronyc tracking`, `chronyc sources -v`; Windows: `w32tm /query /status`, `/source`. Compare across nodes and approved time sources.

**Step 4 — Inspect sources.** NTP servers, DNS, UDP 123/network, NTS certificates/connectivity, domain time hierarchy, hypervisor/guest agents.

**Step 5 — Containment.** If a node risks accepting expired tokens or causing widespread login failures, consider routing around/draining the node per change policy. Never widen skew recklessly.

**Step 6 — Remediation.** Repair NTP sources, daemon config, or VM time issues. Assess clock step vs slew and impact on jobs/sessions/DB.

**Step 7 — Verify.** Check selected source, offset, uncertainty, last sync, and health over several cycles; run SAML/OIDC/JWT/Kerberos positive + negative tests.

**Step 8 — Recovery.** Return healthy nodes to traffic; roll back any incident-approved temporary skew exceptions.

**Step 9 — Postmortem.** Document root cause, outage duration, security impact, alert blind spots, config drift, and preventive actions.

## 32. Common Operational Mistakes

| Mistake | Why it is dangerous | Fix |
| --- | --- | --- |
| Raising SAML/JWT skew to 30 minutes | Widens token/assertion validity, hides broken NTP | Fix clocks, bound allowance |
| Changing timezone to "fix the time" | Changes display formatting only | Check actual UTC offset |
| Assuming `chronyd` running equals synchronized | Source may be lost, root dispersion growing | Read tracking/sources/status |
| Trusting low stratum as guaranteed accuracy | Stratum misses network/source quality | Check uncertainty/trust |
| Monitoring only container clocks | Misses node/VM time sources | Monitor Kubernetes nodes |
| Alerting only at the 5-minute Kerberos threshold | Users suffer failures before alerts fire | Set warnings well below tolerance |
| Using HTTP Date as reference clock | Network/cache/proxy delay and weak trust | Approved NTP/NTS reference |
| Removing SAML `NotBefore` validator | Lowers security to mask failures | Fix IdP/SP clocks |
| Editing signed XML timestamps after signing | Breaks signature, tests the wrong cause | Generate fresh fixture then sign |
| Dropping `exp` so old JWTs pass | Expired tokens get accepted | Enforce expiry, fix clocks |
| `setJwtValidator` with timestamp only | Drops audience/issuer/custom checks | Compose full validators |
| Running `chronyc makestep` ad hoc | Clock jump disrupts sessions/jobs | Change plan/maintenance window |
| Running two competing time daemons | Clock adjusted erratically | One authoritative time hierarchy |
| Ignoring Windows KDC clocks | Kerberos fails despite healthy Spring | Check DC/PDC W32Time |
| Ignoring unsynced startup nodes | New pods take traffic too early | Readiness/time-source policy |
| Measuring cache/TTL with skewed wall clock | Erratic session expiry/retention | Monotonic durations and accurate UTC deadlines |
| Clock alerts checking sync flag only | Daemon may not update kernel flag | Cross-check chrony/root dispersion |
| Treating every 401 as NTP | Could be invalid issuer/audience/token | Classify by validator layer |
| Ignoring leap/smear policy | Conflicting source policies diverge UTC at events | Ensure source compatibility |
| Disabling cert checks on TLS errors | Opens PKI vulnerabilities | Separate time offset from cert validity |

## 33. Review Exercises with Answers

**Q1.** Does changing timezone from GMT+7 to UTC make the UTC clock more accurate?

**Answer:** No; timezone only changes time formatting, while NTP/time synchronization fixes offset.

**Q2.** Is `System.nanoTime()` a Unix epoch timestamp?

**Answer:** No. Use it for elapsed duration, never for JWT/SAML deadlines.

**Q3.** SAML Conditions are valid, yet bearer SubjectConfirmation has expired. Should login succeed?

**Answer:** No if bearer confirmation fails validator policy; the conditions are evaluated independently.

**Q4.** A JWT has a valid signature, yet `nbf` is in the future beyond tolerance. Should it pass?

**Answer:** No; cryptographic validity does not replace time-window validation.

**Q5.** What default clock skew does current Spring Resource Server documentation specify?

**Answer:** Current documentation specifies 60 seconds. Check your exact version/custom decoder, and do not assume it applies to SAML/Kerberos.

**Q6.** Does `JwtTimestampValidator(Duration.ofSeconds(45))` adjust the OS clock?

**Answer:** No. It only adjusts timestamp comparison leeway.

**Q7.** Which validators can `JwtDecoder#setJwtValidator(...)` accidentally drop if misused?

**Answer:** Issuer, audience, token-type/custom required-claim checks, or other defaults; compose the complete validator set.

**Q8.** Roughly what default tolerance does Windows/AD Kerberos typically use?

**Answer:** Microsoft documents around 5 minutes under common policy; healthy clocks should stay far closer.

**Q9.** Is the `Skew` field in `chronyc tracking` Spring SAML's `clockSkew`?

**Answer:** No; chrony's `Skew` is frequency uncertainty in ppm, while Spring's is a time `Duration`.

**Q10.** Does `node_timex_sync_status=1` guarantee offset < 1 ms?

**Answer:** No. Inspect offset/uncertainty, approved sources, and daemon metrics.

**Q11.** Why might a container's `date -u` be wrong, and where do you fix it?

**Answer:** Linux containers normally share the host node's realtime clock; fix NTP/VM host rather than changing timezone or running privileged NTP inside every pod.

**Q12.** Can `chronyd active` with unreachable time sources cause SAML logins to fail?

**Answer:** Yes; service liveness does not mean synchronized.

**Q13.** How do NTP step and slew differ?

**Answer:** Step jumps the clock immediately while slew adjusts rate to converge; stepping can affect logs, token windows, sessions, and schedulers.

**Q14.** Does modifying `NotBefore` in a signed SAML fixture after signing and seeing it rejected prove the time validator works?

**Answer:** No. A broken signature may be the cause. Generate a wrong-time fixture first and sign it validly.

**Q15.** Are `auth_time` and `iat` in OIDC the same?

**Answer:** No. `auth_time` is when the end user actually authenticated; `iat` is when the token was issued.

**Q16.** What risk does a host running 2 minutes slow introduce?

**Answer:** Depending on the validator, it may continue accepting tokens already expired in UTC or misjudge authentication freshness.

**Q17.** Should large root dispersion with a small current offset be investigated?

**Answer:** Yes; high uncertainty can signal lost source synchronization and an untrustworthy clock.

**Q18.** One node runs 7 minutes fast while another pod is on time. Can alternating 200/401 responses occur?

**Answer:** Yes. The load balancer routes requests across nodes making different timestamp decisions.

**Q19.** Is a "not yet valid" certificate definitely caused by a wrong timezone?

**Answer:** No. Check the UTC clock alongside actual certificate validity/deployment/trust.

**Q20.** Should NTS be enabled against any arbitrary NTP server?

**Answer:** No; client build, server NTS support, TLS trust, and network paths must all support it.

**Q21.** Does `JwtTimestampValidator` validate CAS ticket expiry?

**Answer:** No; CAS ticket lifetimes are governed by the CAS server/registry implementation.

**Q22.** Is alerting only at the exact 5-minute Kerberos threshold good practice?

**Answer:** It should not be the first alert; set early warnings well below the impact threshold.

**Q23.** Does seeing `^*` in `chronyc sources` prove the clock is absolutely accurate?

**Answer:** Not alone; check root dispersion, source trust/accuracy, and actual offset.

**Q24.** Can a SAML Signature invalid error be fixed by raising `clockSkew`?

**Answer:** No. That is a trust/signature or XML data failure.

**Q25.** Why shouldn't every login request query an NTP server directly?

**Answer:** It adds latency and external failure dependencies; sync the OS via daemon and check readiness/telemetry instead.

## 34. Production Checklist

- [ ] IdP/AS/SP/KDC/Resource Server nodes use approved time sources.
- [ ] Clocks are evaluated as UTC Instants; timezones are for display only.
- [ ] Host/container/VM responsibilities are clearly defined.
- [ ] No two competing daemons/time agents adjust the same clock.
- [ ] Multiple trusted time sources or proper failover exist.
- [ ] NTS is used where client/server support it and trust/network are verified.
- [ ] `chronyc tracking/sources` or `w32tm` health is monitored.
- [ ] Metrics cover offset, root dispersion/uncertainty, and source age.
- [ ] Prometheus timex metrics are verified live and interpreted for the active daemon.
- [ ] Missing metrics/scrape failures trigger alerts instead of looking like 0 offset.
- [ ] Warning thresholds sit below protocol tolerance, alongside critical thresholds.
- [ ] Kubernetes node/VM time health is monitored, not only app pods.
- [ ] Startup readiness strategy accounts for unsynchronized hosts.
- [ ] Runbooks exist for VM resume/snapshot/clock jumps and time-source outages.
- [ ] Step vs slew policies are approved for production hosts.
- [ ] Spring SAML `clockSkew` aligns with profile/version and security approval.
- [ ] SAML signature/issuer/audience/recipient/Conditions validators remain intact.
- [ ] JWT `exp`/`nbf` are checked with measured skew, never inflated arbitrarily.
- [ ] Custom `setJwtValidator` preserves full issuer/audience/token-policy checks.
- [ ] OIDC `auth_time`, `max_age`, and `nonce` are never equated with `iat`.
- [ ] Kerberos KDC/DC clocks are verified against domain policy.
- [ ] CAS Ticket TTLs and store clocks are verified per implementation.
- [ ] TLS certificate validity is distinguished from time drift and key rotation.
- [ ] Time-boundary tests use `Clock.fixed`/validly signed fixtures.
- [ ] Timestamps in signed payloads are never altered after signing.
- [ ] Session/replay/OneTimeUse/revocation policies remain sound after any skew change.
- [ ] Logs use UTC + trace IDs, avoiding raw tokens/assertions/PII.
- [ ] Alerts correlate host metrics with SAML/JWT/Kerberos failure categories.
- [ ] Post-remediation tests verify positive and negative SSO flows across multiple nodes.
- [ ] Any temporary incident skew exception has an owner, expiry, and rollback plan.
- [ ] Source/time config drift is audited across clusters/regions and KDC sites.

## 35. Summary

**Clock synchronization is an operational prerequisite for federated authentication, not merely a log-formatting preference.** Even when an IdP issues validly signed SAML/JWT payloads, a drifted SP can reject them; an overly slow SP can also widen token acceptance windows beyond intent.

Five pragmatic principles:

1. **Fix clock infrastructure first:** approved NTP/NTS/chrony/W32Time, inspecting the right host/VM/Kubernetes node.
2. **Clock skew is only a validator allowance:** widening skew does not fix clocks and carries security trade-offs.
3. **Read multiple signals:** offset + uncertainty + selected source + last sync + application time failures.
4. **Test the true cause:** signed SAML/JWT fixtures with intentionally wrong timestamps yet valid signatures/trust and other conditions.
5. **Maintain incident readiness:** runbooks for step/slew, NTP outages, VM resumes, multi-node inconsistencies, and security impact.

The objective is **a trusted, monitored UTC clock with minimal error**, allowing Spring Security to keep critical validations intact rather than widening time windows until every token passes.

### Official References

1. Spring Security — Resource Server JWT, Customizing Timestamp Validation and default clock skew: https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/jwt.html
2. Spring Security — SAML2 Authentication, AssertionValidator clock skew: https://docs.spring.io/spring-security/reference/servlet/saml2/login/authentication.html
3. Spring Security — JwtTimestampValidator API, `setClock`: https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/oauth2/jwt/JwtTimestampValidator.html
4. OASIS SAML 2.0 Core, assertion Conditions and SubjectConfirmation: https://docs.oasis-open.org/security/saml/v2.0/saml-core-2.0-os.pdf
5. OpenID Connect Core 1.0, ID Token claims and `max_age`: https://openid.net/specs/openid-connect-core-1_0.html
6. RFC 7519 — JSON Web Token, NumericDate, exp/nbf/iat: https://www.rfc-editor.org/rfc/rfc7519.html
7. Chrony — chronyc tracking/sources/sourcestats: https://chrony-project.org/doc/4.4/chronyc.html
8. Chrony — chrony.conf configuration: https://chrony-project.org/doc/latest/chrony.conf.html
9. Chrony — Configuration examples and accuracy: https://chrony-project.org/examples.html
10. Prometheus node_exporter — Monitoring time sync with timex: https://github.com/prometheus/node_exporter/blob/master/docs/TIME.md
11. Prometheus node_exporter — NodeClockSkewDetected/NodeClockNotSynchronising alert examples: https://github.com/prometheus/node_exporter/blob/master/docs/node-mixin/alerts/alerts.libsonnet
12. Microsoft Learn — Windows Time Service Tools and Settings (`w32tm`): https://learn.microsoft.com/en-us/windows-server/networking/windows-time-service/windows-time-service-tools-and-settings
13. Microsoft Learn — Kerberos protocol KDC configuration, typical SkewTime default: https://learn.microsoft.com/en-us/troubleshoot/windows-server/windows-security/kerberos-protocol-registry-kdc-configuration-keys
14. Microsoft Learn — Authoritative time source for PDC: https://learn.microsoft.com/en-us/services-hub/microsoft-engage-center/health/remediation-steps-ad/configure-the-root-pdc-with-an-authoritative-time-source-and-avoid-widespread-time-skew
15. IETF RFC 8915 — Network Time Security for NTP: https://www.rfc-editor.org/rfc/rfc8915.html