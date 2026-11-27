# 32.9. System Time Synchronization and Handling Clock Skew

## 1. Context: OIDC login succeeds on one node but fails on another

A **Spring Boot + Spring Security OAuth 2.0/OIDC Client** system runs across three replicas, logs in via an OpenID Provider (OP), and uses access tokens to call a Resource Server. In production, hard-to-reproduce errors begin appearing:

- A user just logged in, yet the Client rejects the ID Token because <code>exp</code> already passed or <code>iat</code> is in the future.
- The access token appears valid at the Client, yet the Resource Server returns HTTP 401 <code>invalid_token</code>.
- One Client refreshes continuously, while another node holds a nearly expired token too long.
- The Resource Server reports JWT <code>nbf</code> “not yet valid” right after the OP minted the token.
- TLS connections to Discovery/JWKS/Token Endpoints fail reporting a certificate as not yet valid.
- Operators see logs off by seven hours and assume a server clock is broken, when it is only a display timezone difference.

Behind these symptoms can be **clock skew**: the difference between the clocks of independent machines used to determine the current instant. For OAuth2 and OIDC, accurate time affects authentication, token validation, token renewal, jobs, sessions, and TLS alike.

> **Key takeaway:** Synchronize clocks across all machines first, then apply a small, deliberate clock skew tolerance. Raising tolerance does not fix a node off by several minutes, does not replace signature/issuer/audience checks, and must never be used to mask operational failures.

## 2. Learning objectives

After this lesson, you will be able to:

1. Distinguish UTC, timezones, wall clocks, monotonic clocks, drift, offset, and clock skew.
2. Understand JWT claims <code>exp</code>, <code>nbf</code>, <code>iat</code>, OIDC <code>auth_time</code>, and code/token lifetimes.
3. Distinguish **JWT validation leeway** from **early token refresh buffers**.
4. Configure clock skew on Spring Security authorized-client providers appropriately.
5. Understand the roles of <code>JwtTimestampValidator</code>, <code>Clock</code>, and OIDC ID Token validation.
6. Synchronize clocks using NTP/chrony/systemd-timesyncd/Windows Time or cloud time services.
7. Analyze clocks across Kubernetes nodes, containers, VMs, NTP outages, and timezones.
8. Design unit/integration tests using <code>Clock.fixed</code>, <code>Clock.offset</code>, and boundary timestamps.
9. Distinguish expired tokens due to time skew from token revocation, refresh rotation, issuer mismatches, and session errors.
10. Build metrics, alerts, troubleshooting workflows, and runbooks for production.

## 3. Time concepts: never conflate them

| Concept | Example | Impact |
|---|---|---|
| UTC instant | <code>2026-11-16T10:00:00Z</code> | Absolute point in time for token expiry |
| Timezone | <code>Asia/Ho_Chi_Minh</code> | Local time formatting; does not shift the underlying instant |
| Wall clock | <code>Instant.now()</code> | System clock, adjustable by NTP |
| Monotonic elapsed time | <code>System.nanoTime()</code> | Measures latency/timeouts; never use as an epoch |
| Clock offset/skew | Host is 45 seconds ahead of true UTC | Can break JWT validity windows |
| Clock drift | Host gains 0.2 seconds per day | Cumulative error without sync |
| Clock step | Jumps from 10:00 to 10:02 | Deadlines can trigger “suddenly” |
| Clock slew | Clock rate adjusted gradually | Avoids large jumps |
| JWT validation leeway | Accepts 60 seconds of skew | Widens the JWT acceptance window |
| Token refresh buffer | Refreshes 90 seconds before expiry | Reduces sending nearly expired tokens |

### 3.1. UTC is not a timezone display bug

~~~text
UTC:              2026-11-16 10:00:00Z
Asia/Ho_Chi_Minh: 2026-11-16 17:00:00+07:00
~~~

These represent **the same instant**, even though their formatted strings differ by seven hours.

~~~java
import java.time.Instant;
import java.time.ZoneId;
import java.time.ZonedDateTime;

Instant issuedAt = Instant.parse("2026-11-16T10:00:00Z");
ZonedDateTime display = issuedAt.atZone(
    ZoneId.of("Asia/Ho_Chi_Minh"));
~~~

If one node prints UTC and another prints ICT, never conclude a node has clock skew before comparing their UTC instants.

### 3.2. Wall clock and monotonic clock

JWTs carry absolute expiration times:

~~~java
Instant now = Instant.now();
boolean expired = !now.isBefore(expiresAt);
~~~

This comparison requires a wall clock and an <code>Instant</code>.

To measure Token Endpoint latency:

~~~java
long started = System.nanoTime();
// HTTP request to Token Endpoint
long latencyNanos = System.nanoTime() - started;
~~~

<code>System.nanoTime()</code> has no shared UTC epoch across processes; never use it to compute <code>exp</code> or compare timestamps across JVMs.

### 3.3. Clock skew between two systems

Suppose:

~~~text
Real UTC:                 10:00:00
Authorization Server:    10:00:00
OAuth2 Client A:          10:00:45 (+45 s)
Resource Server B:       09:59:20 (-40 s)
~~~

Nodes A and B differ by **85 seconds**, even though each deviates from UTC by less than a minute. That is why a token can appear “expired” in one place and “not yet valid” in another.

## 4. Timestamps in OAuth2/OIDC

### 4.1. JWT NumericDate

JWT represents many claims as <code>NumericDate</code>: seconds since the Unix epoch in UTC, not local time strings.

~~~json
{
  "iss": "https://sso.example.org/realms/company",
  "sub": "user-123",
  "aud": "portal-web",
  "iat": 1794823200,
  "nbf": 1794823200,
  "exp": 1794826800
}
~~~

These epoch values illustrate format only. When crafting test tokens, derive them from <code>Instant.getEpochSecond()</code> to avoid typos.

### 4.2. exp — expiration

<code>exp</code> is the instant after which a JWT is no longer accepted by timestamp validation, apart from a small configured leeway.

Core model:

~~~text
now < exp       → not expired yet
now >= exp      → expired, without leeway
~~~

The JWT must still pass signature, issuer, audience, token purpose, and other validations.

### 4.3. nbf — not before

<code>nbf</code> specifies the earliest instant at which a token is accepted:

~~~text
now < nbf       → token not yet valid
now >= nbf      → passes not-before check
~~~

Leeway may allow a small offset before <code>nbf</code>.

### 4.4. iat — issued at

<code>iat</code> records when the token was issued. It helps track token age, auditing, and certain authentication policies.

**Do not assume** every JWT validator checks <code>iat</code> with the exact same semantics as <code>nbf</code>. Different validation layers and profiles have their own rules on issuance time.

### 4.5. OIDC auth_time

<code>auth_time</code> represents when the OP authenticated the user, distinct from the ID Token's <code>iat</code>:

~~~text
auth_time = when the user authenticated at the OP
iat       = when the ID Token was issued
~~~

In flows using <code>max_age</code> or step-up auth, <code>auth_time</code> helps decide whether authentication is sufficiently fresh. Clock skew can misjudge freshness if nodes diverge heavily.

### 4.6. Authorization codes, access tokens, and refresh tokens

Not every OAuth2 token is a JWT:

- Authorization codes are typically short-lived, single-use credentials.
- Access tokens may be JWTs or opaque tokens.
- Refresh tokens have independent lifecycles, expiry, rotation/revocation, and may be opaque.
- OIDC ID Tokens are JWTs used for Client authentication.

Clients must not parse every access/refresh token as a JWT. Spring Security's <code>OAuth2AccessToken</code> exposes <code>issuedAt</code>/<code>expiresAt</code> populated by the framework from response metadata.

### 4.7. expires_in is in seconds

The Token Endpoint may return:

~~~json
{
  "access_token": "opaque-test-value",
  "token_type": "Bearer",
  "expires_in": 3600
}
~~~

Per OAuth2, <code>expires_in</code> is typically **seconds** until the access token expires. Never treat it as milliseconds or add it to local time strings.

## 5. Timeline: “expired” and “not yet valid” can occur together

OP mints a token:

~~~text
OP clock: 10:00:00 UTC
nbf:      10:00:00 UTC
exp:      10:05:00 UTC
~~~

Resource Server is 50 seconds slow:

~~~text
RS wall clock: 09:59:10
JWT nbf:       10:00:00
~~~

The RS may report not-yet-valid if its allowance is too tight.

Client is 90 seconds fast:

~~~text
Client clock: 10:05:20
JWT exp:      10:05:00
~~~

The Client considers the token expired earlier than the OP or RS.

~~~mermaid
flowchart TD
    OP["OP issues JWT with nbf=10:00, exp=10:05"] --> C["OAuth2 Client clock fast +90s"]
    OP --> RS["Resource Server clock slow -50s"]
    C --> R["Client thinks it must refresh early"]
    RS --> N["RS may think JWT has not reached nbf"]
    R --> X["Synchronize clocks and control tolerance"]
    N --> X
~~~

Clock skew tolerance handles only **bounded errors**. If a node is off by several minutes, fixing the clock is an infrastructure responsibility.

## 6. Two mechanisms both called “clock skew” with opposite meanings

| Mechanism | Question | Illustrative formula | Effect |
|---|---|---|---|
| **JWT validation leeway** | Is the JWT still accepted? | <code>now &lt; exp + tolerance</code>, <code>now + tolerance &gt;= nbf</code> | May accept slightly expired or slightly early tokens |
| **Early refresh buffer** | Should the Client fetch a new token yet? | <code>now &gt;= expiresAt - buffer</code> | Refreshes **before** expiry |

### 6.1. Validation leeway

~~~text
JWT exp:            10:30:00
Resource Server now:10:30:35
Allowed skew:       60 seconds
~~~

A validator allowing 60 seconds can still accept the timestamp condition. This **widens the usable token window**, so balance it against security policy. It never rescues a JWT with a bad signature, issuer, or audience.

### 6.2. Early refresh

~~~text
Access token expiresAt: 10:30:00
Refresh buffer:         90 seconds
Refresh threshold:      10:28:30
~~~

Once the Client reaches 10:28:30, it proactively refreshes to avoid the token expiring mid-API call. The buffer does not extend how long the Resource Server accepts expired JWTs.

### 6.3. Do not pick one Duration for both out of habit

<code>clockSkew(Duration.ofSeconds(90))</code> in an authorized-client provider and <code>JwtTimestampValidator(Duration.ofSeconds(90))</code> have **opposite consequences**.

- At the OAuth2 Client, refreshing early reduces downstream failures.
- At the JWT validator, larger leeway extends how long an old access token remains accepted.

### 6.4. Watch your units

~~~java
Duration.ofSeconds(60);  // 60 s
Duration.ofMinutes(2);   // 120 s
Duration.ofMillis(60);   // 0.06 s, not 60 s
~~~

Mixing up ms and s can cause late refreshes or overly broad tolerances.

## 7. Synchronize clocks before touching Java code

Every deployment needs:

1. Hosts/nodes syncing time from trusted NTP/cloud time sources.
2. Verifying **system clock synchronized**, not merely setting timezone to UTC.
3. Monitoring clock offset, frequency/drift, reachability, and last sync.
4. Checking Authorization Server, OAuth2 Client, Resource Server, ingress, database, and Kubernetes nodes per architecture.
5. Using UTC timestamps in telemetry to correlate events.
6. Alerting on sync loss or offset breaching error budgets.
7. Choosing small leeway after measuring expected jitter and latency.

### 7.1. Do not demand literally zero offset

Even healthy NTP has small jitter. The goal is a **low, stable, measurable offset** within security bounds, not nanosecond lockstep across every clock.

### 7.2. TLS also depends on time

X.509 certificates carry <code>NotBefore</code> and <code>NotAfter</code>. A host off by minutes may reject valid certificates as “not yet valid” or “expired”.

Loosening JWT leeway **does not change** TLS certificate validation. Fix the clock, truststore, or certificate deployment; never enable trust-all TLS to push requests through.

## 8. Linux: chrony, NTP, and timesyncd

On Linux, time synchronization may run via <code>chronyd</code>, <code>systemd-timesyncd</code>, or another NTP client. Pick the service suited to your OS/cloud image and avoid running competing daemons adjusting the same clock.

### 8.1. Checking time and sync status

~~~bash
date -u
timedatectl status
~~~

Inspect UTC, timezone, system clock synchronized, and NTP service status. A <code>date -u</code> printout looking roughly right **does not prove** the node is synchronized with a time source.

### 8.2. Chrony

~~~bash
chronyc tracking
chronyc sources -v
~~~

<code>tracking</code> reports offset, drift/frequency, and sync state. <code>sources -v</code> shows whether time sources are reachable.

If all sources are unreachable, investigate DNS, firewalls, network policies, NTP sources, and cloud time services.

### 8.3. systemd-timesyncd

~~~bash
timedatectl timesync-status
timedatectl show-timesync --all
~~~

Subcommands vary by systemd version. If the host uses chrony, inspect chrony rather than assuming `timesyncd` must be active.

### 8.4. Avoid manual clock adjustments in production

A large clock step disrupts:

~~~text
Token expiry decisions
Cache TTLs
Scheduled jobs
Log ordering
Session expiry
Distributed leases
TLS certificate validation
~~~

Never run ad-hoc <code>date -s</code> on production hosts; follow your operations runbook and time-sync automation.

## 9. Windows Server and virtual machines

For Windows Time Service:

~~~powershell
w32tm /query /status
w32tm /query /source
w32tm /query /peers
~~~

Windows PowerShell 5.1 can run:

~~~powershell
[DateTime]::UtcNow.ToString("o")
~~~

to print a UTC timestamp. Do not use <code>Get-Date -AsUTC</code> if the PowerShell runtime does not support that parameter.

If a machine belongs to an Active Directory domain, the clock hierarchy may be governed by domain policy. Never override NTP sources on domain controllers or organizational servers without authorization.

### 9.1. VM resume and snapshots

After suspend/resume or VM snapshot restores, guest clocks can drift temporarily. Verify time synchronization **after** resume, especially before re-adding a node to a load balancer.

### 9.2. Windows timezone does not change JWT NumericDate

A Windows host displaying local time differently from Linux UTC does not break token validation. All <code>exp</code>/<code>nbf</code> checks should operate on UTC instants.

## 10. Kubernetes and Docker: containers usually share the node's clock

In typical Linux container deployments, the JVM inside a container uses the **host kernel's** system clock. Changing timezone inside a container does not change the instant. Nor should a Pod hold privileges to alter a Kubernetes node's clock.

~~~text
Kubernetes Node A clock
  ├── Portal pod A1
  ├── Portal pod A2
  └── API pod A3

Kubernetes Node B clock
  ├── Portal pod B1
  └── API pod B2
~~~

Pods on the same node normally share the same underlying system clock. Pods on **two different nodes** can drift apart if node time sync breaks.

### 10.1. Scaling out makes errors appear random

~~~text
Node A: UTC + 3 seconds
Node B: UTC + 95 seconds
Node C: UTC - 70 seconds
~~~

A request landing on A succeeds, on B gets flagged expired, and on C reports not-yet-valid. Correlate errors by **node/instance**, not just URL.

### 10.2. Check at the node level

- Time synchronization service on the node image.
- Cloud/NTP source reachability.
- Clock offset per node and node age.
- Nodes after autoscaling, rolling replacement, or VM resume.
- Drift trends, missed syncs, and alert rules.
- Network access to the cloud provider's time service.

Restarting a Pod usually **does not fix** a skewed node clock. Never run privileged NTP pods able to mutate host clocks without strict platform/security controls.

### 10.3. Different `TZ` values do not mean different clocks

~~~text
Pod A TZ=UTC
Pod B TZ=Asia/Ho_Chi_Minh
~~~

still return the same <code>Instant.now()</code>. Separate display timezones from absolute instants.

## 11. Java `Instant` and `Clock`

### 11.1. Comparing expiry with `Instant`

~~~java
import java.time.Clock;
import java.time.Duration;
import java.time.Instant;

Clock clock = Clock.systemUTC();
Instant now = Instant.now(clock);
Instant expiresAt = Instant.parse("2026-11-16T10:30:00Z");

boolean expired = !now.isBefore(expiresAt);
boolean closeToExpiry = !now.isBefore(
    expiresAt.minus(Duration.ofSeconds(90)));
~~~

This snippet illustrates arithmetic. In Spring Security, let authorized-client providers and JWT validators manage lifecycles rather than replacing the framework's token manager with a standalone boolean check.

### 11.2. Avoid `LocalDateTime` for absolute expirations

Never store token expiry as a timezone-less string:

~~~text
2026-11-16 10:30:00
~~~

and read it under varying timezones. Use <code>Instant</code>, <code>OffsetDateTime</code>, or a database timestamp type that preserves instants.

~~~java
Instant expiresAt =
    Instant.now(clock).plus(Duration.ofMinutes(5));
~~~

Convert to the user's timezone only in the presentation layer.

### 11.3. Epoch milliseconds and seconds

~~~java
long seconds = Instant.now().getEpochSecond();
long millis = System.currentTimeMillis();
~~~

JWT `NumericDate` uses **seconds**. Writing milliseconds into <code>exp</code> makes a token appear valid for millennia. Reading seconds as milliseconds makes a token look long expired.

### 11.4. Inject `Clock` for deterministic tests

~~~java
public final class ExpiryPolicy {
    private final Clock clock;
    private final Duration buffer;

    public ExpiryPolicy(Clock clock, Duration buffer) {
        this.clock = clock;
        this.buffer = buffer;
    }

    public boolean shouldRefresh(Instant expiresAt) {
        return !Instant.now(clock).isBefore(
            expiresAt.minus(buffer));
    }
}
~~~

This is an illustrative policy, not a built-in Spring Security class. Avoid mixing an injected <code>Clock</code> with parameterless <code>Instant.now()</code> in the same service, as tests lose full control over time.

## 12. Access token `expiresAt` and early refresh

<code>OAuth2AuthorizedClient</code> binds a `ClientRegistration`/principal to an access token and optional refresh token.

~~~java
import org.springframework.security.oauth2.core.OAuth2AccessToken;
import java.time.Instant;

OAuth2AccessToken token = authorizedClient.getAccessToken();
Instant issuedAt = token.getIssuedAt();
Instant expiresAt = token.getExpiresAt();
~~~

### 12.1. Token expiring mid-API call

~~~text
Client selects token:    10:29:58
Token expiresAt:         10:30:00
Network/queue latency:   3 seconds
API receives request:    10:30:01
~~~

The Resource Server may reject the request even if both clocks are perfectly synchronized. That is why an **early refresh buffer** is helpful.

### 12.2. 90-second buffer

~~~text
Token expiresAt: 10:30:00
Buffer:          90 seconds
Refresh at:      10:28:30 or later
~~~

The buffer lowers the chance of tokens expiring before the API processes them. It does not directly alter Resource Server JWT validation.

### 12.3. Never arbitrarily make the buffer longer than the token lifetime

If a token lives 60 seconds while the refresh buffer is 90 seconds, the provider considers the token nearly expired immediately upon issuance, causing continuous refreshes or token churn.

Size the buffer using:

- Token lifetime issued by the OP.
- Token Endpoint p95/p99 latency and retry budget.
- Queue/processing latency prior to API calls.
- Measured clock offset.
- Refresh-token rotation/concurrency policies.
- Token rate limits and expected traffic.

## 13. Spring Security `OAuth2AuthorizedClientProvider` `clockSkew`

Authorized-client providers such as refresh token and client credentials support configuring clock skew to **acquire new access tokens early**.

### 13.1. Service manager for background jobs

~~~java
package example.security;

import java.time.Duration;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.oauth2.client
    .AuthorizedClientServiceOAuth2AuthorizedClientManager;
import org.springframework.security.oauth2.client.OAuth2AuthorizedClientManager;
import org.springframework.security.oauth2.client.OAuth2AuthorizedClientProvider;
import org.springframework.security.oauth2.client
    .OAuth2AuthorizedClientProviderBuilder;
import org.springframework.security.oauth2.client.OAuth2AuthorizedClientService;
import org.springframework.security.oauth2.client.registration
    .ClientRegistrationRepository;

@Configuration
public class JobOAuth2ClientConfig {

    @Bean
    OAuth2AuthorizedClientManager jobAuthorizedClientManager(
            ClientRegistrationRepository registrations,
            OAuth2AuthorizedClientService clientService) {

        Duration buffer = Duration.ofSeconds(90);

        OAuth2AuthorizedClientProvider provider =
            OAuth2AuthorizedClientProviderBuilder.builder()
                .refreshToken(refresh ->
                    refresh.clockSkew(buffer))
                .clientCredentials(client ->
                    client.clockSkew(buffer))
                .build();

        var manager =
            new AuthorizedClientServiceOAuth2AuthorizedClientManager(
                registrations, clientService);

        manager.setAuthorizedClientProvider(provider);
        return manager;
    }
}
~~~

This manager fits service/job flows requiring no <code>HttpServletRequest</code>. It does not open browsers, handle authorization code consent, or replace <code>oauth2Login()</code>.

### 13.2. Web Servlet manager

When using <code>DefaultOAuth2AuthorizedClientManager</code>:

~~~java
import java.time.Duration;
import org.springframework.security.oauth2.client
    .DefaultOAuth2AuthorizedClientManager;
import org.springframework.security.oauth2.client
    .OAuth2AuthorizedClientProviderBuilder;

var manager = new DefaultOAuth2AuthorizedClientManager(
    clientRegistrations,
    authorizedClientRepository);

manager.setAuthorizedClientProvider(
    OAuth2AuthorizedClientProviderBuilder.builder()
        .authorizationCode()
        .refreshToken(refresh ->
            refresh.clockSkew(Duration.ofSeconds(90)))
        .build());
~~~

This snippet assumes <code>clientRegistrations</code> and <code>authorizedClientRepository</code> are injected. The web manager may require Servlet request/response context; never pass it into background schedulers arbitrarily.

### 13.3. Do not confuse with JWT validation

An authorized-client provider's <code>clockSkew</code>:

- Affects when tokens are authorized/refreshed.
- Does not alter <code>exp</code> inside an ID Token.
- Does not change host/Pod clocks.
- Does not make a Resource Server accept expired JWTs longer.
- Does not fix wrong issuers, nonces, or signatures.

If a Resource Server rejects a JWT due to <code>nbf</code>, raising the refresh buffer will not necessarily fix it.

## 14. Storing `expiresAt` in clusters and databases

Token state storage should persist absolute expiry instants, avoiding timezone-dependent string conversions.

Conceptual PostgreSQL schema example:

~~~sql
CREATE TABLE oauth2_authorized_client_state (
    registration_id VARCHAR(120) NOT NULL,
    principal_key VARCHAR(240) NOT NULL,
    access_token_ciphertext BYTEA NOT NULL,
    refresh_token_ciphertext BYTEA,
    access_expires_at TIMESTAMPTZ NOT NULL,
    version BIGINT NOT NULL DEFAULT 0,
    PRIMARY KEY (registration_id, principal_key)
);
~~~

This is **not** a drop-in replacement schema for Spring Security's JDBC authorized-client implementation; it merely illustrates storing encrypted token state, expiry, and version.

### 14.1. `TIMESTAMPTZ` does not guarantee UTC display formatting

PostgreSQL <code>TIMESTAMPTZ</code> stores an instant, while display formatting follows the session timezone. Do not compare string outputs from two sessions with different timezones to diagnose drift.

### 14.2. Token metadata and timezones

If two JVMs write/read <code>Instant</code> via JDBC, run integration tests across differing timezone settings. Stored instants must not “shift hours” when read on another node.

### 14.3. Refresh tokens cannot be inferred from access token `expiresAt`

Refresh tokens have independent expiry, revocation, and rotation policies and do not necessarily carry an <code>exp</code> claim. An <code>invalid_grant</code> may stem from revocation, reuse, or wrong client binding—not just clocks.

## 15. `JwtTimestampValidator`: leeway in JWT verification

In Spring Security OAuth2 Resource Server, class:

~~~java
org.springframework.security.oauth2.jwt.JwtTimestampValidator
~~~

checks temporal claims such as <code>exp</code> and <code>nbf</code> with a configured clock skew tolerance.

### 15.1. Leeway differs from buffer

Suppose the Resource Server has:

~~~text
JWT exp:                  10:30:00
Resource Server clock:    10:30:35
Configured leeway:        60 seconds
~~~

The timestamp check still passes because current time exceeds <code>exp</code> by 35 seconds. **This widens the token acceptance window**, rather than telling the Client to refresh early.

### 15.2. Configuring the timestamp validator

~~~java
import java.time.Duration;
import org.springframework.security.oauth2.jwt.JwtTimestampValidator;

JwtTimestampValidator validator =
    new JwtTimestampValidator(Duration.ofSeconds(60));
~~~

This validates **timestamps only**. It does not prove a valid signature, right issuer, right audience, or required scopes.

### 15.3. Fixed `Clock` for the validator

~~~java
import java.time.Clock;
import java.time.Duration;
import java.time.Instant;
import java.time.ZoneOffset;
import org.springframework.security.oauth2.jwt.JwtTimestampValidator;

Clock testClock = Clock.fixed(
    Instant.parse("2026-11-16T10:00:00Z"),
    ZoneOffset.UTC);

JwtTimestampValidator validator =
    new JwtTimestampValidator(Duration.ofSeconds(60));

validator.setClock(testClock);
~~~

This controls what “now” the validator sees without changing the OS clock. Verify customization APIs against your exact Spring Security version.

### 15.4. Avoid overwriting the validator chain with timestamp-only

Dangerous example:

~~~java
// Wrong if this becomes the entire JWT validation of the Resource Server.
decoder.setJwtValidator(
    new JwtTimestampValidator(Duration.ofMinutes(10)));
~~~

A resource server must preserve signature, issuer, audience, token purpose, and policy checks. Replacing the validator chain with only a timestamp validator strips critical validations.

When adjusting tolerance, use the documented customization points of your Spring Security version and **compose all required validators**. Never equate “timestamp passed” with “valid JWT”.

### 15.5. Default issuer validation

Spring Security provides:

~~~java
import org.springframework.security.oauth2.jwt.JwtValidators;

var validators = JwtValidators.createDefaultWithIssuer(
    "https://sso.example.org/realms/company");
~~~

This validator chain illustrates retaining default validations plus issuer. Real Resource Servers may also require audience, scope, or tenant-specific validators. Never replace defaults with a standalone timestamp validator.

## 16. OIDC ID Token: time is part of authentication

In OAuth2 Login with OpenID Connect, the ID Token establishes **user authentication to the Relying Party**. A proper pipeline checks:

- Signature per OP JWKS and algorithm policy.
- <code>iss</code> matching the configured issuer.
- <code>aud</code> containing the Client ID.
- <code>exp</code>, <code>iat</code>, and other temporal requirements per OIDC profile.
- <code>nonce</code> if used in the authorization request.
- <code>azp</code> and <code>auth_time</code> when required by flow/policy.

### 16.1. When the RP clock is too fast

~~~mermaid
sequenceDiagram
    autonumber
    participant B as Browser
    participant RP as OIDC Client
    participant OP as OpenID Provider
    B->>RP: Callback code + state
    RP->>OP: Token request
    OP-->>RP: ID Token, iat=10:00, exp=10:05
    RP->>RP: Local clock reads 10:07
    RP->>RP: Temporal validation fails
    RP-->>B: Login authentication failure
~~~

If the RP is several minutes ahead of the OP, login failures can signal a time sync issue. Never disable expiry validation or trust claims from an unverified JWT.

### 16.2. Resource Server validators do not apply automatically to `oauth2Login`

<code>JwtTimestampValidator</code> is typically discussed under OAuth2 Resource Server. OIDC Login constructs decoders and validators per <code>ClientRegistration</code> and OIDC rules.

If you need to customize ID Token leeway via <code>OidcIdTokenDecoderFactory</code> or version-specific extension points:

1. Verify the public API and documented behavior of your project's Spring Security version.
2. Keep all issuer, audience, signature, nonce, and `azp` validations intact.
3. Never replace default validators with a standalone timestamp validator.
4. Keep tolerance small, with security review and metrics.
5. Test boundary cases and confirm tokens with bad signatures/issuers are still rejected.

### 16.3. `auth_time` and `max_age`

If the Portal requires authentication within the last 5 minutes:

~~~text
max_age = 300 seconds
auth_time = 10:00:00
Client now = 10:05:20
~~~

Reauthentication/step-up semantics depend on OP and Client policy. A slow Client clock can mistakenly treat stale authentication as fresh; overly wide tolerance weakens step-up enforcement.

### 16.4. `state` and `nonce` are not timestamps

<code>state</code> and <code>nonce</code> provide correlation and replay protection. Errors like:

~~~text
authorization_request_not_found
invalid_state
nonce mismatch
~~~

are not automatically clock skew; they often stem from session cookies, request repositories, wrong instances, multi-tab logins, or tampering. Never disable those checks to work around a clock issue.

## 17. Resource Server HTTP 401: not every error is time-related

The Resource Server may return:

~~~http
HTTP/1.1 401 Unauthorized
WWW-Authenticate: Bearer error="invalid_token"
~~~

However, <code>invalid_token</code> does not automatically reveal the exact root cause.

| Cause | Time-related? | Investigation |
|---|---|---|
| JWT `exp` expired | Yes | Token TTL, offset, refresh |
| JWT `nbf` in the future | Yes | OP/RS clocks |
| Wrong issuer | Not directly | OIDC/OAuth2 issuer trust |
| Wrong audience | No | Token audience / resource indicator |
| Signature/JWK mismatch | No | Key rotation / JWKS |
| Token revoked | Not necessarily | OP revocation/policy |
| Authorization header stripped | No | Proxy / WebClient integration |
| Wrong token type/purpose | No | Validation policy |

A token passing timestamp checks still needs valid signature, issuer, audience, scopes, and business authorization. HTTP 403 <code>insufficient_scope</code> is an authorization error and must not be “fixed” with clock skew or repeated refreshes.

## 18. Client Credentials and token acquisition concurrency

Services using <code>client_credentials</code> receive short-TTL tokens. When entering the early refresh window:

~~~text
10:28:30 — token nearing expiry
10:28:31 — 50 worker threads simultaneously request token
10:28:32 — multiple token acquisition requests may fire
~~~

A clock skew buffer only decides **when** to acquire a token; it does not serialize worker requests.

### 18.1. Per-key single-flight

~~~text
key = registrationId + trustedServicePrincipal
~~~

A cache or token manager using locks or single-flight reduces duplicate token requests. Never fall back to another tenant's or principal's authorized client when the Token Endpoint times out.

### 18.2. Derive buffers from real measurements

Example measurements:

~~~text
Observed max offset:       2 seconds
Token Endpoint p99 latency:1.5 seconds
API queueing:             4 seconds
Retry safety margin:      policy-specific
~~~

Numbers are **illustrative only**. Keep the buffer well below the token lifetime for your use case while covering real network/queue latency.

### 18.3. Token responses age in transit

If the OP mints a token at T0 and the response reaches the Client at T0+3s, remaining validity is already shorter than nominal TTL. Measure Token Endpoint latency and rely on framework expiry metadata rather than assuming you get a full <code>expires_in</code> regardless of network delay.

## 19. Clock skew and refresh-token rotation

With token rotation:

~~~text
Initial: access A0, refresh R0
Refresh: access A1, refresh R1
Reuse R0: OP may return invalid_grant or trigger reuse detection
~~~

Two nodes read the same token R0:

~~~mermaid
sequenceDiagram
    autonumber
    participant A as Node A - fast clock
    participant B as Node B - normal clock
    participant DB as Shared Token Store
    participant OP as Token Endpoint
    A->>DB: Read A0/R0, version 7
    B->>DB: Read A0/R0, version 7
    A->>OP: Refresh R0
    OP-->>A: A1/R1
    B->>OP: Refresh R0
    OP-->>B: invalid_grant
    A->>DB: Save A1/R1, version 8
    B->>DB: Unconditional remove?
    Note over DB: B may delete A's version 8
~~~

### 19.1. Synchronized clocks alone do not prevent races

Even two accurate clocks can refresh R0 at the same instant. Concurrency coordination is required:

~~~text
1. Load authorized client for exact registration/principal.
2. If access token has sufficient validity → use it.
3. If refresh needed → acquire per-key distributed lock/single-flight.
4. After lock, re-read latest token state.
5. If already refreshed → use the new version.
6. Otherwise → execute refresh grant.
7. Atomically persist new access+refresh token with version/CAS.
8. On invalid_grant, conditionally remove only matching old version.
9. Release lock with ownership/lease policy.
~~~

This is architectural pseudocode, **not default behavior** of <code>DefaultOAuth2AuthorizedClientManager</code>.

### 19.2. Refresh timeout is an unknown outcome

The OP may have consumed R0 and minted R1 while the response was lost. Retrying R0 can return <code>invalid_grant</code> or trigger token-family revocation. Increasing clock skew cannot resolve an uncertain distributed transaction state.

## 20. Clock steps, jobs, and distributed leases

System clocks can be adjusted during operations.

### 20.1. Step forward

~~~text
Host clock jumps 10:00 → 10:03
~~~

Scheduled refresh jobs may see many deadlines expire simultaneously, causing a thundering herd. Large forward steps can also abruptly shift token and TLS validity.

### 20.2. Step backward

~~~text
Host clock jumps 10:00 → 09:58
~~~

Custom retry/deadline logic built on wall clocks may wait longer than intended. For elapsed timeouts, prefer library/monotonic scheduling facilities.

### 20.3. Distributed lock leases

A lock store using server-side TTL behaves differently from an implementation comparing <code>expires_at</code> against a local Client clock. Know which clock governs lease timeouts.

Even with stable store TTLs, GC pauses or network delays can expire a lease before a refresh finishes. Use re-reads, versions, CAS, or fencing when consistency requires it.

## 21. Choosing tolerance is both an operational and security decision

Evaluate:

1. Maximum observed offset across OP, Client, and Resource Server.
2. NTP jitter and time-source stability.
3. Token Endpoint p95/p99 latency and queueing.
4. Access token TTL, refresh rotation policy, and rate limits.
5. Replay risk while stolen tokens remain accepted within leeway.
6. Step-up requirements and <code>auth_time</code>/<code>max_age</code>.
7. Security and compliance constraints.
8. Testing, rollout, and alerting capabilities.

### 21.1. Example of two separate policies

| Parameter | Illustrative value | Meaning |
|---|---|---|
| Desired max host offset | Under 2 seconds | Internal operations SLO |
| JWT timestamp leeway | 60 seconds | Allows minor variance at Resource Server |
| Early refresh buffer | 90 seconds | Reduces mid-request token expiry |
| Access token TTL | 15 minutes | OP policy |
| Token Endpoint timeout | Per latency SLO | Prevents hanging indefinitely |

These values are **not universal defaults**. Choose based on measured telemetry and your exact Spring Security/OP versions.

### 21.2. Leeway too large

If the Resource Server accepts <code>exp</code> 10 minutes late, a leaked access token remains usable for that extended window. For <code>nbf</code>, tokens become accepted earlier than their nominal start time.

Never raise skew to tens of minutes to mask an NTP outage. Fix time synchronization first.

### 21.3. Buffer too large

~~~text
Access token TTL=60s
Refresh buffer=90s
~~~

The Client considers every freshly issued token “about to expire”, causing refresh loops or token churn. Size the buffer proportionally to TTL.

### 21.4. `Duration.ZERO`

<code>Duration.ZERO</code> removes extra leeway or early refresh buffers depending on the component. “Zero tolerance” is not always stable in distributed systems where network latency and clock jitter always exist.

## 22. Observability: see clock offsets, not just errors

### 22.1. Structured logs in UTC

~~~text
timestamp=2026-11-16T10:00:15.123Z
service=portal
instance=portal-7f5dc8
node=node-b
registrationId=company
operation=oidc_login
stage=id_token_validation
errorCategory=timestamp_invalid
clockSyncHealthy=false
correlationId=example-123
~~~

Never log raw authorization codes, state, nonces, access/refresh/ID Tokens, client secrets, or session cookies.

### 22.2. Node time metrics

Depending on exporter/platform, monitor:

~~~text
node_timex_offset_seconds
node_timex_sync_status
node_timex_maxerror_seconds
node_timex_estimated_error_seconds
~~~

Metric names and semantics depend on exporter version; verify on your real platform before authoring alerts.

### 22.3. OAuth2 application metrics

~~~text
oauth2_login_failure_total{provider,category}
oauth2_token_refresh_total{provider,result}
oauth2_token_request_latency_seconds{provider,grant_type}
oauth2_id_token_timestamp_failure_total{provider}
oauth2_resource_server_invalid_token_total{issuer_alias,category}
~~~

These are **suggested application-instrumented metrics**, not all emitted out of the box by Spring Security.

### 22.4. Alert thresholds

Example internal alert rule for an environment expecting tight offsets:

~~~text
WARN: abs(clock_offset) > 1s continuously for 5 minutes
CRITICAL: lost synchronization or abs(clock_offset) > 5s
~~~

Do not treat these as universal thresholds; tune them to your infrastructure, expected jitter, and security policy. Alert well before offsets approach JWT validator tolerances.

### 22.5. Tracing

~~~text
traceId=request-123
  ├── oidc.callback
  ├── oidc.token.exchange
  ├── authorized_client.lookup
  └── resource_server.api_call
~~~

Measure latency with monotonic elapsed time; record event timestamps using UTC wall clocks. Never infer causal ordering solely from logs across skewed nodes.

### 22.6. Safe metric labels

Use provider alias, operation, normalized error category, and service. Never put user emails, <code>sub</code>, JWTs, <code>jti</code>, request IDs, or raw error descriptions into high-cardinality metric labels.

## 23. Unit tests with `Clock.fixed` and `Clock.offset`

Never change a CI runner's OS clock to test token expiry. Inject <code>Clock</code> for deterministic tests.

### 23.1. Testing early refresh thresholds

~~~java
import java.time.Clock;
import java.time.Duration;
import java.time.Instant;
import java.time.ZoneOffset;
import org.junit.jupiter.api.Test;
import static org.junit.jupiter.api.Assertions.*;

class ExpiryPolicyTest {

    @Test
    void refreshesAtThreshold() {
        Clock clock = Clock.fixed(
            Instant.parse("2026-11-16T10:28:30Z"),
            ZoneOffset.UTC);
        ExpiryPolicy policy = new ExpiryPolicy(
            clock, Duration.ofSeconds(90));

        assertTrue(policy.shouldRefresh(
            Instant.parse("2026-11-16T10:30:00Z")));
    }

    @Test
    void waitsBeforeThreshold() {
        Clock clock = Clock.fixed(
            Instant.parse("2026-11-16T10:28:29Z"),
            ZoneOffset.UTC);
        ExpiryPolicy policy = new ExpiryPolicy(
            clock, Duration.ofSeconds(90));

        assertFalse(policy.shouldRefresh(
            Instant.parse("2026-11-16T10:30:00Z")));
    }
}
~~~

This tests the illustrative policy from section 11, **not the internal implementation of a Spring Security provider**.

### 23.2. Boundary table

| now | expiresAt | buffer | shouldRefresh |
|---|---|---|---|
| 10:28:29 | 10:30:00 | 90s | false |
| 10:28:30 | 10:30:00 | 90s | true |
| 10:29:00 | 10:30:00 | 90s | true |
| 10:30:00 | 10:30:00 | 90s | true |

### 23.3. Simulating fast/slow clocks with `Clock.offset`

~~~java
Clock base = Clock.fixed(
    Instant.parse("2026-11-16T10:00:00Z"),
    ZoneOffset.UTC);

Clock fast = Clock.offset(
    base, Duration.ofSeconds(30));
Clock slow = Clock.offset(
    base, Duration.ofSeconds(-30));
~~~

Avoids affecting other processes or tests. Avoid <code>Thread.sleep</code> when testing boundary conditions.

## 24. Unit testing `JwtTimestampValidator`

~~~java
import java.time.Clock;
import java.time.Duration;
import java.time.Instant;
import java.time.ZoneOffset;
import org.junit.jupiter.api.Test;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.security.oauth2.jwt.JwtTimestampValidator;

import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertTrue;

class JwtTimeValidationTest {

    private final Instant now =
        Instant.parse("2026-11-16T10:00:00Z");

    @Test
    void tokenExpiredThirtySecondsAgoWithinSkew() {
        Jwt jwt = jwtWithExpiry(now.minusSeconds(30));

        var validator = new JwtTimestampValidator(
            Duration.ofSeconds(60));
        validator.setClock(Clock.fixed(now, ZoneOffset.UTC));

        assertFalse(validator.validate(jwt).hasErrors());
    }

    @Test
    void tokenExpiredNinetySecondsAgoIsRejected() {
        Jwt jwt = jwtWithExpiry(now.minusSeconds(90));

        var validator = new JwtTimestampValidator(
            Duration.ofSeconds(60));
        validator.setClock(Clock.fixed(now, ZoneOffset.UTC));

        assertTrue(validator.validate(jwt).hasErrors());
    }

    private Jwt jwtWithExpiry(Instant expiry) {
        return Jwt.withTokenValue("test-header.payload.signature")
            .header("alg", "RS256")
            .subject("alice-test")
            .issuedAt(now.minusSeconds(300))
            .notBefore(now.minusSeconds(300))
            .expiresAt(expiry)
            .build();
    }
}
~~~

<code>test-header.payload.signature</code> is only a placeholder, **not a real signed JWT**. This tests only the timestamp validator—no signature verification, issuer, audience, or OIDC protocol.

### 24.1. Future `nbf` token

~~~java
@Test
void allowsNbfThirtySecondsInFutureWithSixtySecondSkew() {
    Instant now = Instant.parse("2026-11-16T10:00:00Z");

    Jwt jwt = Jwt.withTokenValue("test-token")
        .header("alg", "RS256")
        .subject("alice-test")
        .issuedAt(now)
        .notBefore(now.plusSeconds(30))
        .expiresAt(now.plusSeconds(600))
        .build();

    var validator = new JwtTimestampValidator(
        Duration.ofSeconds(60));
    validator.setClock(Clock.fixed(now, ZoneOffset.UTC));

    org.junit.jupiter.api.Assertions.assertFalse(
        validator.validate(jwt).hasErrors());
}
~~~

Add another case with <code>nbf=now+90s</code> to verify rejection when tolerance is 60 seconds.

### 24.2. Do not confuse unit tests with decoder integration

In real validation:

~~~text
Signed JWT from test OP
    ↓
JwtDecoder signature/JWKS
    ↓
Issuer + audience + timestamps + other validators
    ↓
Resource Server authorization
~~~

A <code>JwtTimestampValidator</code> unit test does not replace any other stage in that pipeline.

## 25. OIDC Login integration tests with time skew

An OIDC integration suite with a test/stub OP signing valid ID Tokens:

~~~text
Test OP issuer: https://sso.test.example/realms/it
Client ID:      portal-it
Flow:           Authorization Code + PKCE when applicable
Callback:       /login/oauth2/code/it-op
~~~

### 25.1. Cases to distinguish

| Scenario | Fixture | Expectation |
|---|---|---|
| Normal login | ID Token `exp` far enough ahead | Authentication succeeds |
| Expired ID Token | `exp` older than tolerance | Authentication fails |
| Near-expiry ID Token | `exp` near `now` | Matches validator policy |
| Future-issued ID Token | Future `iat` per test profile | OIDC temporal validation matches policy |
| Wrong issuer | `iss` differs from `ClientRegistration` | Fails despite valid timestamps |
| Wrong audience | `aud` lacks client ID | Fails |
| Nonce mismatch | `nonce` differs from authorization request | Fails |
| Bad JWT signature | Fails JWK verification | Fails |
| Small OP clock skew | Temporal claims within tolerance | Confirmed expected behavior |
| Large OP clock skew | Temporal claims outside tolerance | Fails + triggers clock health alert |

**Do not treat future `iat` as one uniform rule across all validators**: exact criteria depend on OIDC profile, Spring Security version, and custom validators. Integration tests verify the enforced contract.

### 25.2. `oidcLogin()` only mocks a principal

~~~java
mockMvc.perform(get("/private").with(oidcLogin()));
~~~

is useful for testing controllers/authorization once authenticated. It **does not** execute Token Endpoint calls, code exchanges, ID Token signature/issuer/nonce validation, or authentication success/failure handlers.

To test clock skew in OIDC login, run a real callback against a test/stub OP issuing signed JWTs and running full validation.

### 25.3. Never alter the CI runner's clock

Use:

- Test JWT fixtures with chosen temporal claims.
- <code>Clock.fixed</code>/<code>Clock.offset</code> in components accepting an injected `Clock`.
- A test OP/Token Endpoint stub with test public/private signing keys.
- Negative fixtures for expiry, `iat`, `nonce`, and `issuer`.

Never run OS date commands to mutate a shared host's clock and reset it afterward.

## 26. Integration testing: Authorization Server, Client, and Resource Server

A lab setup:

~~~text
Authorization Server test:
    issuer = https://sso.test.example
    access token TTL = 5 minutes

OAuth2 Client:
    authorized-client provider early refresh buffer = 60 seconds

Resource Server:
    issuer/audience/signature validation
    JWT timestamp tolerance = 30 seconds
~~~

**This is an illustrative test configuration, not a mandatory production default.**

### 26.1. Synchronized clocks

1. OP mints token with valid <code>nbf/iat/exp</code>.
2. Client obtains token.
3. Client calls Resource Server before expiry.
4. Resource Server validates signature, issuer, audience, and timestamps.
5. Endpoint checks scopes/roles/business ownership and returns the result.

### 26.2. Client 45 seconds fast

1. Simulate Client authorization clock 45 seconds ahead.
2. Client refreshes earlier than nominal wall clock.
3. Zero refresh loops or abnormal token churn occur.
4. API calls succeed with a valid access token.

### 26.3. Resource Server 45 seconds slow

1. OP mints JWT with <code>nbf=now</code>.
2. RS validator clock is fixed to <code>now-45s</code>.
3. With 30-second tolerance, timestamp validation fails.
4. With 60-second tolerance per test policy, timestamp check passes.
5. Signature, issuer, and audience checks still run independently.

### 26.4. Large offset exceeding tolerance

When a node skews by 5 minutes while tolerance is 30–60 seconds:

~~~text
Expected: token timestamp failure
Expected: node time synchronization alert
Expected: security validation remains enabled
~~~

Never raise test tolerance to 10 minutes just to turn the test green.

### 26.5. Token Endpoint outage

If the Client tries to refresh and the Token Endpoint times out / returns 503:

- Never treat an expired access token as valid indefinitely.
- Resource Server enforces validation per policy.
- Application returns a domain-level dependency error, bounded retry, or reauthorization depending on context.
- Never log or return raw refresh tokens or error descriptions to the browser.

## 27. Distinguishing clock skew from other OAuth2 errors

| Symptom | Possibly clock skew? | Other causes to check |
|---|---|---|
| JWT expired immediately after issuance | Yes | Very short TTL, timezone/epoch conversion bug |
| JWT not-yet-valid | Yes | OP issues future `nbf` by policy |
| Future ID Token `iat` | Possibly | Test fixture or provider bug |
| Authorization code `invalid_grant` | Indirectly possible | Code reuse, `redirect_uri`, PKCE, client mismatch |
| Refresh token `invalid_grant` | Possible, not default | Rotation, revocation, client binding |
| OAuth state mismatch | Usually not directly | Cookies, sessions, multi-tab, request repository |
| Issuer mismatch | Not directly | Public OP hostname, discovery, wrong registration |
| Audience mismatch | No | Client/resource ID |
| Invalid JWT signature | No | Wrong key/JWK, tampering |
| TLS certificate not yet valid | Yes | Certificate validity/deployment |
| Resource Server 403 `insufficient_scope` | No | Scope/role/tenant authorization |
| Token Endpoint 503 | Not directly | OP outage/network |

### 27.1. `invalid_grant` is not a time error by default

In the Authorization Code Flow, <code>invalid_grant</code> can stem from an expired code, reused code, wrong PKCE verifier, wrong redirect URI, or mismatched client binding.

In the Refresh Token Flow, it can stem from token revocation, rotation reuse detection, expired refresh tokens, or disabled token families.

Check **grant type, stage, and storage state** before blaming NTP.

### 27.2. Callback missing authorization request

Errors:

~~~text
authorization_request_not_found
invalid_state
~~~

can be caused by session cookies missing on return to the Portal, `SameSite` policies, reverse proxies, node B failing to read shared sessions, or overwritten authorization requests. Increasing JWT tolerance will not restore request correlation.

### 27.3. Clock errors also surface outside OAuth2

A node off by minutes commonly exhibits:

~~~text
TLS certificate time errors
Scheduled jobs early/late
Unexpected cache expiration
Audit logs out of order
Database timestamps inconsistent
Distributed lease anomalies
~~~

If multiple services on one node report time anomalies simultaneously, inspect node time synchronization first.

## 28. Production troubleshooting workflow

~~~mermaid
flowchart TD
    A["Login/API fails"] --> B{"Error mentions exp, nbf, iat, or certificate time?"}
    B -->|No| C["Check issuer/audience/PKCE/state/scope/network"]
    B -->|Yes| D["Identify OP, app, node/instance, and UTC timestamps"]
    D --> E{"Is node time synchronization healthy?"}
    E -->|No| F["Fix NTP/cloud time; consider isolating node"]
    E -->|Yes| G["Compare observed offset with token exp/nbf/iat"]
    G --> H{"Offset within budget yet near expiry boundary?"}
    H -->|Yes| I["Measure request latency; review refresh buffer and leeway"]
    H -->|No| J["Check TTL, OP behavior, refresh race/storage"]
    F --> K["Re-run E2E login/API/TLS and watch metrics"]
    I --> K
    J --> K
~~~

### 28.1. Gather context

~~~text
service
instanceId / podName
nodeName
providerAlias
registrationId
operation = oidc_login | token_refresh | api_call
stage = callback | token_endpoint | resource_server
normalizedErrorCategory
UTC event timestamp
nodeClockSyncStatus
correlationId
~~~

Never put ID Tokens, codes, state, client secrets, Authorization headers, or session cookies into logs.

### 28.2. Check each layer

1. **OP:** JWT issuance timestamps, time service, issuer settings.
2. **Client:** Node wall clock, token `expiresAt`, refresh buffer.
3. **Resource Server:** Node wall clock, JWT timestamp validator, issuer/audience.
4. **TLS:** Certificate `NotBefore`/`NotAfter`, JVM truststore, current host time.
5. **Session:** Cookie/`SameSite`, state repository, session TTL.
6. **Telemetry:** UTC timestamps, node labels, offset metrics.

### 28.3. Multi-region incidents

Never compare <code>10:00:00</code> from one region with <code>17:00:00</code> from another if logged in local timezones. Normalize to UTC instants before establishing causal order.

## 29. Runbook when a host clock drifts

### 29.1. Determine scope

~~~text
Affected:
  OAuth2 Login?
  Resource Server JWT?
  Background token refresh?
  TLS to OP?
  Session store?

Scope:
  One pod?
  One node?
  One availability zone?
  OP itself?
~~~

### 29.2. Collect status

Linux:

~~~bash
date -u
timedatectl status
chronyc tracking
chronyc sources -v
~~~

Windows:

~~~powershell
w32tm /query /status
w32tm /query /source
~~~

### 29.3. Fix infrastructure first

1. Verify NTP/time service is running.
2. Check time-source DNS/network reachability.
3. Inspect current offset, drift/frequency, and last synchronization.
4. If a node is badly skewed, consider draining it from traffic per runbook.
5. Fix node time sync or replace the node per platform procedure.
6. Return the node to service only after clock health meets policy.
7. Re-measure login failures, `invalid_token`, and TLS errors.

Never arbitrarily mutate the system clock on a shared machine or domain controller.

### 29.4. Tune app config only after nodes are healthy

Once clocks are synchronized, if tokens still expire mid-API call:

- Measure Token Endpoint and API latency.
- Verify `issuedAt`/`expiresAt` conversion and token TTL.
- Tune the early refresh buffer appropriately.
- Evaluate validator leeway against your threat model.
- Review refresh rotation/concurrency and token storage.
- Test boundaries, canary roll out, and monitor metrics.

Never use a multi-minute tolerance to hide an NTP outage.

### 29.5. Post-remediation verification

1. E2E OIDC login succeeds.
2. ID Tokens with wrong issuers or expired beyond tolerance are still rejected.
3. Resource Server accepts valid access tokens and rejects expired ones.
4. Token refreshes fire at the expected threshold.
5. Zero new refresh loops or races appear.
6. TLS handshakes to OP/Discovery/JWKS succeed.
7. UTC metrics and logs are consistent.
8. Node time offsets return within SLO.

## 30. Anti-patterns to avoid

### 30.1. Disabling token expiry validation

Never drop <code>exp</code>/<code>nbf</code> checks to stop login errors. Fix clocks and use bounded tolerance.

### 30.2. Dropping issuer/audience/signature checks to “fix” errors

Valid JWT timestamps do not prove the JWT was signed by the right OP or issued for the right Client/Resource Server. Never skip trust validation.

### 30.3. Using huge leeway

Large leeway extends how long leaked tokens remain valid; require security review and monitoring.

### 30.4. Using `LocalDateTime` for absolute expirations

<code>LocalDateTime</code> lacks timezone/offset and can be interpreted differently across nodes. Use <code>Instant</code>.

### 30.5. Using `System.nanoTime` as an epoch

<code>System.nanoTime()</code> measures elapsed duration, not Unix timestamps.

### 30.6. Running uncoordinated refresh schedulers on every node

Clock buffers do not serialize token requests; with rotation, uncoordinated refreshes cause replays and races.

### 30.7. Retrying `invalid_grant` indefinitely

Consumed codes or refresh tokens do not become valid through retries; reuse can revoke the token family.

### 30.8. Restarting Pods to “reset NTP”

Container clocks usually match the host node clock. Restarting Pods cannot fix a node's NTP outage.

### 30.9. Changing CI runner clocks for tests

Mutating OS clocks breaks TLS, package managers, background jobs, and concurrent tests; use fixed `Clock` instances and JWT fixtures.

### 30.10. Logging raw tokens just to inspect `exp`

Tokens carry credentials and PII. Log sanitized expiry deltas and safe metadata instead of raw JWT diagnostics.

## 31. Test scenario matrix

| ID | Scenario | Expectation |
|---|---|---|
| TIME-01 | OP/Client/RS clocks close together | Valid tokens accepted |
| TIME-02 | JWT `exp` expired within tolerance | Timestamp behavior follows policy |
| TIME-03 | JWT `exp` expired beyond tolerance | Token rejected |
| TIME-04 | JWT `nbf` future within tolerance | Timestamp behavior follows policy |
| TIME-05 | JWT `nbf` future beyond tolerance | Token rejected |
| TIME-06 | ID Token `iat` in future | OIDC/profile checks match policy |
| TIME-07 | ID Token expired | Login fails |
| TIME-08 | Bad signature, valid time | Still fails |
| TIME-09 | Wrong issuer/audience, valid time | Still fails |
| TIME-10 | 91s remaining, 90s buffer | Does not refresh yet |
| TIME-11 | 90s remaining, 90s buffer | Refreshes per policy |
| TIME-12 | TTL shorter than refresh buffer | No refresh loop |
| TIME-13 | High Token Endpoint latency | Avoids casually sending dying tokens |
| TIME-14 | Token Endpoint timeout | Unknown outcome / recovery per policy |
| TIME-15 | Two nodes share R0 | Does not delete new R1 |
| TIME-16 | One K8s node skewed 5 minutes | Detected, alerted, isolated |
| TIME-17 | JVMs run different timezones | `Instant` comparisons stay accurate |
| TIME-18 | Epoch seconds/millis conversion | No absurd expirations |
| TIME-19 | TLS cert not yet valid | Check clock/cert, never trust-all |
| TIME-20 | API 403 `insufficient_scope` | Not treated as time skew |
| TIME-21 | Callback missing state | Investigate session, never disable state |
| TIME-22 | VM resume after suspend | Syncs before taking traffic |
| TIME-23 | NTP source unreachable | Alert & recovery |
| TIME-24 | NTP recovers | OIDC login/JWT/TLS stabilize |

Split deterministic unit tests, component protocol tests, OP integration tests, and infrastructure chaos tests by cost. Security-critical tests must always verify wrong-issuer, bad-signature, and out-of-tolerance rejections.

## 32. Self-study exercises

### Exercise 1 — Timezone or clock skew?

Server A logs <code>10:00 UTC</code>; server B logs <code>17:00 Asia/Ho_Chi_Minh</code>.

**Answer:** Likely the same instant; convert to UTC before claiming clocks are skewed.

### Exercise 2 — JWT `exp` and leeway

JWT `exp=10:30:00`, RS `now=10:30:40`, allowance=60s.

**Answer:** Timestamp validation passes within tolerance; signature, issuer, audience, and permissions must still hold.

### Exercise 3 — JWT `nbf`

JWT `nbf=10:00:00`, RS `now=09:58:30`, leeway=60s.

**Answer:** Fails not-before because 90 seconds > 60 seconds.

### Exercise 4 — Refresh buffer

`expiresAt=10:30:00`, buffer=90s.

**Answer:** Client can begin refreshing at 10:28:30.

### Exercise 5 — Leeway vs. buffer

**Answer:** Validator leeway widens the JWT acceptance window; early refresh buffer controls when the Client requests a new token.

### Exercise 6 — Offset between nodes

Node A is +45s fast; node B is -40s slow.

**Answer:** Relative skew between A and B is 85 seconds.

### Exercise 7 — NumericDate

A developer writes <code>System.currentTimeMillis()</code> into <code>exp</code>.

**Answer:** Classic unit error; `NumericDate` uses seconds while `currentTimeMillis()` returns milliseconds.

### Exercise 8 — `LocalDateTime` in a database

Token expiry is stored as <code>2026-11-16 10:30:00</code> without timezone.

**Answer:** Unsafe when readers run in different timezones; use `Instant`/UTC-aware mappings.

### Exercise 9 — API 403

Resource Server returns <code>insufficient_scope</code>.

**Answer:** Authorization/scope issue—do not adjust clock skew to fix it.

### Exercise 10 — Refresh R0

Node A saves R1; Node B with R0 gets `invalid_grant`.

**Answer:** Likely a rotation race; use coordination, re-reads, and versioned conditional cleanup.

### Exercise 11 — Docker timezone

Pod A uses <code>TZ=UTC</code>; Pod B uses <code>TZ=Asia/Ho_Chi_Minh</code>.

**Answer:** Display timezone differences do not shift `Instant`; inspect host node clock offsets.

### Exercise 12 — Node skewed by 5 minutes

The team proposes raising JWT leeway to 10 minutes.

**Answer:** Do not treat that as a root fix; fix the time source/NTP, isolate the skewed node, and keep leeway aligned with your threat model.

### Exercise 13 — Nonce mismatch

The ID Token is unexpired, yet <code>nonce</code> mismatches.

**Answer:** OIDC login must fail; clock skew never makes a mismatched nonce valid.

### Exercise 14 — TLS certificate

Token Endpoint fails with certificate not yet valid.

**Answer:** Check host clock, certificate validity, and truststore. `JwtTimestampValidator` does not affect TLS.

### Exercise 15 — Chrony

**Task:** Use <code>chronyc tracking</code> and <code>chronyc sources -v</code> to determine whether a node is synchronized.

**Hint:** Inspect offset, stratum, reachability, reference source, last sync, and drift—not merely timezone.

### Exercise 16 — `Clock.fixed`

**Task:** Test `ExpiryPolicy` at 10:28:29 and 10:28:30 with expiry 10:30 and buffer 90s.

**Answer:** Before threshold returns `false`; at threshold returns `true`.

### Exercise 17 — `Clock.offset`

Simulate a Client 30 seconds fast using <code>Clock.offset(base, Duration.ofSeconds(30))</code>.

**Answer:** Allows testing early-refresh decisions without mutating the OS clock.

### Exercise 18 — Testing JWT leeway

A JWT expired 30 seconds ago with 60-second validator leeway.

**Answer:** Timestamp check passes; the full decoder pipeline must still verify signature, issuer, and audience.

### Exercise 19 — `invalid_grant` in code exchange

The Token Endpoint rejects the authorization code.

**Answer:** Check code TTL, reuse, PKCE, redirect URI, and `ClientRegistration`; clock skew might play a role, though it is not the default cause.

### Exercise 20 — Single-node incident

Only node C reports frequent expired/not-yet-valid errors.

**Answer:** Correlate by pod/node, measure NTP offset, isolate the node if needed, repair time sync, and verify alerts and JWT validation post-recovery.

### Exercise 21 — Unknown refresh outcome

OP mints R1 from R0, yet the response times out.

**Answer:** The Client does not know whether R0 was consumed. Blind retries risk `invalid_grant`/reuse detection; coordinate recovery.

### Exercise 22 — Step-up `auth_time`

The user authenticated 8 minutes ago; the endpoint requires authentication within 5 minutes.

**Answer:** Trigger reauthentication/step-up per policy rather than raising leeway to accept stale `auth_time`.

### Exercise 23 — Logging

Operations logs entire JWTs/codes/state to inspect timestamps.

**Answer:** Risks exposing credentials and PII. Log offset metrics, normalized errors, and sanitized expiry deltas instead.

### Exercise 24 — Capstone lab

Build a lab with:

1. A test OP issuing JWTs with deterministic TTLs.
2. A Spring Security OIDC Client using the Authorization Code Flow.
3. A Resource Server verifying signature, issuer, audience, and timestamps.
4. Early refresh buffer configured separately from JWT validation leeway.
5. Unit tests using <code>Clock.fixed</code> for <code>exp/nbf</code> boundaries.
6. Unit tests using <code>Clock.offset</code> for fast/slow Client clocks.
7. OIDC integration tests with signed ID Tokens from the test OP.
8. Negative tests ensuring wrong issuer/signature/nonce still fail even with valid temporal claims.
9. Tests for JWTs expired beyond tolerance.
10. Tests classifying Resource Server 401/403 properly.
11. Refresh-token rotation tests across two nodes ensuring the newer token is never deleted accidentally.
12. Monitoring for node time offsets and synchronization status.
13. Tests for TLS cert validity errors without disabling TLS validation.
14. An NTP recovery runbook and safe logging practices.

Explain why **NTP synchronization**, **JWT validation leeway**, and **OAuth2 early refresh buffers** are three distinct mechanisms that must be operated and tested separately.

## 33. Summary

- **UTC Instant** is the basis for token expiration; timezones affect display only. JWT `NumericDate` uses epoch seconds.
- OIDC and OAuth2 involve multiple timestamps: <code>exp</code>, <code>nbf</code>, <code>iat</code>, <code>auth_time</code>, authorization code TTL, access token <code>expiresAt</code>, refresh policies, and TLS certificate validity.
- **JwtTimestampValidator leeway** tolerates minor clock variance during timestamp checks and widens the security acceptance window.
- **OAuth2AuthorizedClientProvider `clockSkew` / early refresh buffer** prompts the Client to fetch a new token ahead of expiry; it does not alter Resource Server JWT validation.
- Never reuse the same `Duration` for both without understanding their semantics, token TTLs, and threat model.
- Synchronizing via NTP/chrony/Windows Time/cloud time services is foundational; never use large leeway to substitute for time sync.
- Containers usually share the host node's wall clock; restarting Pods does not fix skewed node clocks.
- Java <code>Instant</code> and <code>Clock</code> fit expiry logic and tests; monotonic elapsed time fits latency measurement.
- <code>OAuth2AuthorizedClientProviderBuilder</code> can configure early refresh on refresh-token and client-credentials providers.
- <code>JwtTimestampValidator</code> never replaces signature, issuer, audience, nonce, or authorization checks. Never reduce the validator chain to timestamp-only.
- OIDC ID Token validation has its own pipeline requiring temporal checks and OIDC-flow validations.
- HTTP 401 <code>invalid_token</code> can stem from time or from trust, audience, or revocation. HTTP 403 <code>insufficient_scope</code> is a permissions error.
- Refresh rotation races still occur even with synchronized clocks; use locks/single-flight, re-reads, CAS, and conditional cleanup.
- Clock steps affect jobs, caches, and locks; follow platform runbooks instead of mutating OS clocks ad hoc.
- Unit tests should use <code>Clock.fixed</code>, <code>Clock.offset</code>, and JWT fixtures; integration tests must still enforce signatures, issuers, and audiences.
- Observability needs UTC timestamps, node offset/sync status, operation/stage/category, and bounded-cardinality metrics—never logging tokens, codes, state, or secrets.
- Production runbooks must identify affected nodes/issuers, repair time sources, and verify E2E OIDC Login, Resource Server JWT, and TLS after recovery.

### References

- **Spring Security Reference — OAuth2 Client:** authorized-client providers, token refresh, client credentials, and `clockSkew`.
- **Spring Security Java API — OAuth2AuthorizedClientProviderBuilder:** configuring refresh and client-credentials providers.
- **Spring Security Java API — JwtTimestampValidator:** `exp`, `nbf`, `Clock`, and timestamp tolerance.
- **Spring Security Reference — OAuth2 Resource Server JWT:** issuer, JWT signature, timestamps, and audience validation.
- **Spring Security Reference — OIDC Login:** ID Token validation, nonce, issuer, audience, and authentication flows.
- **RFC 7519 — JSON Web Token (JWT):** `NumericDate`, `exp`, `nbf`, `iat`, and clock skew leeway.
- **RFC 6749 — OAuth 2.0 Authorization Framework:** token expiration metadata, authorization codes, and refresh grants.
- **RFC 6750 — Bearer Token Usage:** `invalid_token`, `insufficient_scope`, and Resource Server HTTP errors.
- **RFC 9700 — Best Current Practice for OAuth 2.0 Security:** token replay, refresh rotation, and OAuth security.
- **OpenID Connect Core 1.0:** ID Token temporal claims, `auth_time`, `nonce`, and `max_age`.
- **Java Platform API — `java.time.Clock`, `Instant`, `Duration`:** UTC instants and deterministic tests.
- **chrony Documentation — tracking and sources:** clock offset, frequency/drift, and time source monitoring.
- **`systemd-timesyncd`/`timedatectl` Documentation:** Linux time synchronization.
- **Microsoft Windows Time Service Documentation:** `w32tm` and Windows Time hierarchy.
- **Kubernetes/Cloud Provider Node Time Documentation:** host clocks, managed node synchronization, and containers.
- **OWASP Logging Cheat Sheet:** safe log events, UTC timestamps, and avoiding credentials/PII in logs.
