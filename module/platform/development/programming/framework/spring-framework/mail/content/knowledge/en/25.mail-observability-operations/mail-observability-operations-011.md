# Runbook for authentication, TLS, and DNS errors in Spring Framework Mail

An application using **Spring Framework Mail** may send emails cleanly in development yet fail after deployment: SMTP returns authentication errors, STARTTLS connections fail to upgrade, certificates are invalid, hostnames fail to resolve, or sender DNS records are misconfigured. All of these often present under the same business symptom—**"Emails are not arriving"**—while their root causes, blast radii, and fixes are completely different.

A **runbook** is an actionable document for on-call operators. Rather than merely explaining concepts, it must quickly answer:

1. Was the email created and enqueued by the application?
2. At which step did `JavaMailSender.send(...)` fail?
3. Does the failure belong to **SMTP AUTH**, **TLS/certificates**, **DNS**, or something else?
4. Is the scope one instance, one SMTP account, one recipient domain, or the whole system?
5. Should you pause sending, tune retries, rotate secrets, or fix DNS?
6. How do you verify recovery without sending duplicates or overloading the relay?

This guide presents an adaptable runbook for Spring Boot applications using `JavaMailSenderImpl` and Jakarta Mail alongside a transactional outbox or background sending workers. Hosts, addresses, TTLs, error codes, and durations are **illustrative examples**; final decisions must follow your configured setup and your SMTP provider's documentation.

> The operational goal is to **restore a safe sending path and protect business messages**, not to make exceptions vanish by disabling TLS, skipping certificate validation, or retrying endlessly.

## 1. Map of layers where failures can occur

~~~mermaid
flowchart TD
    A["Business action"] --> B["Transactional outbox / queue"]
    B --> C["Mail worker"]
    C --> D["JavaMailSenderImpl / Jakarta Mail"]
    D --> E["DNS resolver: SMTP hostname"]
    E --> F["TCP connection to relay"]
    F --> G["SMTP greeting + EHLO"]
    G --> H["STARTTLS / TLS handshake"]
    H --> I["SMTP AUTH"]
    I --> J["MAIL FROM / RCPT TO / DATA"]
    J --> K["Relay queue"]
    K --> L["Recipient MX / mailbox"]
    L --> M["Delivered / deferred / bounced"]
~~~

Not every system traverses every step in the same order: port 465 often uses **implicit TLS** before the SMTP greeting, port 587 typically uses **STARTTLS** after `EHLO`, and some internal relays skip `AUTH` on trusted networks. If you use an email provider's HTTP API instead of SMTP, HTTP/TLS/API authentication errors require their own runbook.

The key is **locating the exact boundary**. DNS for the SMTP relay hostname is not the recipient domain's MX record; an `AUTH` failure does not mean the destination mailbox does not exist; a TLS handshake failure must never be "fixed" by disabling certificate verification.

### Distinguish submission from delivery

| Milestone | Proof | Does NOT prove |
| --- | --- | --- |
| Job enqueued | Durable record in outbox/queue | SMTP accepted the message |
| SMTP connection succeeded | TCP socket opened to endpoint | AUTH succeeded or email sent |
| STARTTLS succeeded | TLS channel established per policy | SMTP account is allowed to send |
| AUTH succeeded | SMTP server authenticated the principal | `From` address permitted, remote MX accepted mail |
| SMTP accepted after DATA | Relay took responsibility for this hop | Email landed in the Inbox |
| Provider reported delivered | Provider confirmed delivery per its definition | Recipient actually read the message |

Never log `DELIVERED` immediately when `send()` returns. Log `SUBMITTED` or `ACCEPTED_BY_RELAY` matching actual evidence, then track provider events/bounces where integrated.

## 2. First-minutes incident response workflow

When a "mail delivery failed" alert fires, start with **scoping** and **containment** before editing configurations.

### Step 1 — Verify the symptom

- Are emails missing, delayed, or landing in spam?
- Are business transactions still creating outbox email jobs normally?
- Does SMTP `send()` throw an exception, or succeed with no subsequent provider delivery events?
- Are only new emails failing, or backlog retries too?
- Were there recent changes to deployments, credentials, certificates, DNS, or firewalls?
- Is the failure happening across all workers or only one pod/host?

### Step 2 — Determine priority

| Illustrative level | Scenario | Action |
| --- | --- | --- |
| P1 — Severe impact | OTP/password reset or transactional mail halted at scale with no fallback | Declare incident, assign owner, prevent retry storms |
| P2 — Partial impact | One SMTP account, region, or group of recipient domains failing | Isolate route, prioritize critical jobs |
| P3 — Degraded | Some canary failures, elevated TLS/DNS timeouts while most mail sends | Investigate, monitor, and remediate carefully |
| P4 — Early warning | Secret nearing expiry, certificate nearing expiry, or DNS configuration drift | Schedule rotation before an outage occurs |

This classification is illustrative; real severities and thresholds must follow organizational SLAs/SLOs.

### Step 3 — Protect the system from cascading failures

- Never retry AUTH errors thousands of times with the same broken credential.
- Bound concurrent SMTP requests, open connections, and retry attempts.
- Keep required emails safely in the durable outbox/queue.
- Pause or throttle marketing/campaign mail during transport incidents.
- Never delete `FAILED` or `SUBMISSION_UNKNOWN` records before reconciliation.
- Never rotate DNS/secrets across the board based on a single unverified data point.
- If a credential compromise is suspected, follow emergency revocation procedures rather than keeping the compromised credential for uptime.

### Step 4 — Capture evidence before making changes

Record in the incident log:

- Start time, environment, cluster, and application version.
- Provider/account key, SMTP host/port, and TLS mode (never log secrets).
- Rates of `AUTH_FAILURE`, `TLS_FAILURE`, `DNS_FAILURE`, timeouts, and submission successes.
- A few representative internal notification/attempt IDs.
- SMTP reply codes and enhanced status codes if present.
- DNS resolution observed directly from the failing workload.
- Timestamps of the most recent deployment, secret rotation, and DNS change.
- Current backlog depth and age of waiting messages.

**Never paste** raw SMTP passwords, access tokens, OTPs, reset links, full MIME bodies, or PII into public tickets/chats. Use sanitized traces with proper access controls.

## 3. Quick symptom triage table

| Symptom | First suspect area | Confirming evidence |
| --- | --- | --- |
| `UnknownHostException` / SMTP host unresolved | Configured endpoint DNS | Query A/AAAA/CNAME from the same network; verify hostname |
| `NoRouteToHostException` | Routing/network | Network path, firewalls, network policies |
| `ConnectException: Connection refused` | TCP endpoint/port/firewall | Correct IP/port, listener running, not confusing implicit TLS |
| `SocketTimeoutException: connect timed out` | TCP connect path | Packet drops, proxy, route, `connectiontimeout` |
| Timeout waiting for 220/EHLO | SMTP read/greeting | Server accepted TCP but did not send banner/reply |
| `SSLHandshakeException` | TLS handshake/trust/hostname/protocol | Certificate chain, SAN, truststore, TLS versions |
| "STARTTLS is required but host does not support it" | TLS mode/SMTP capability | EHLO extensions, right port, STARTTLS advertisement |
| `535 5.7.x` at AUTH | Credentials, account rights, AUTH mechanism | Secret version, principal, provider policy |
| `454 4.7.x` or 4xx at AUTH | Provider temporary auth unavailability/throttling | Provider incident, reply text, error frequency |
| `530` authentication/TLS required | SMTP policy / command sequence | Whether TLS/AUTH are enabled and which stage ran |
| `550 5.1.1` at RCPT TO | Recipient invalid per explicit reply | Not a sender password error |
| "MX not found" after relay accepted mail | Recipient domain DNS or downstream delivery | Bounce/provider event; do not confuse with relay DNS |
| SMTP `send()` succeeds but mail does not arrive | Deliverability/downstream | Provider events, bounces, spam, quota, policy |

Exact exception classes and wrapping depend on Spring/Jakarta Mail versions and SMTP transport implementations. A `MailSendException` can wrap `MessagingException`, `SMTPSendFailedException`, `SMTPAddressFailedException`, or `IOException`. This table is a triage starting point, not an exhaustive mapping.

### Minimal decision tree

~~~mermaid
flowchart TD
    A["Mail send fails"] --> B{"Job in outbox?"}
    B -- "No" --> C["Check producer / transaction / enqueue"]
    B -- "Yes" --> D{"SMTP host resolves via DNS?"}
    D -- "No" --> E["Endpoint DNS runbook"]
    D -- "Yes" --> F{"TCP connects?"}
    F -- "No" --> G["Check port / firewall / routing"]
    F -- "Yes" --> H{"TLS handshake valid?"}
    H -- "No" --> I["TLS runbook"]
    H -- "Yes" --> J{"SMTP AUTH succeeds?"}
    J -- "No" --> K["Authentication runbook"]
    J -- "Yes" --> L{"Relay accepts DATA?"}
    L -- "No" --> M["Classify 4xx/5xx/unknown outcome"]
    L -- "Yes" --> N["Monitor provider / delivery / bounce"]
~~~

With implicit TLS, TLS checks happen **before** the SMTP greeting. With STARTTLS, you must receive 220, run `EHLO`, and negotiate `STARTTLS` before `AUTH`. This tree groups failure domains rather than replacing the full SMTP state machine.

## 4. Preparing an explicit Spring Boot configuration

Example sending via SMTP submission on port 587 with STARTTLS:

~~~yaml
spring:
  mail:
    host: smtp.example.net
    port: 587
    username: smtp-service
    default-encoding: UTF-8
    properties:
      "[mail.smtp.auth]": "true"
      "[mail.smtp.starttls.enable]": "true"
      "[mail.smtp.starttls.required]": "true"
      "[mail.smtp.ssl.checkserveridentity]": "true"
      "[mail.smtp.connectiontimeout]": "3000"
      "[mail.smtp.timeout]": "5000"
      "[mail.smtp.writetimeout]": "5000"
~~~

Supply the password from a secret manager or secure deployment mechanism, such as `SPRING_MAIL_PASSWORD` via secret injection. **Never commit real SMTP passwords** into YAML files, repositories, or container images.

### Operational meaning of properties

| Property | Purpose |
| --- | --- |
| `spring.mail.host` | SMTP endpoint the application **actually connects to** |
| `spring.mail.port` | Port matching the transport mode provided |
| `spring.mail.username` / password | Credentials for SMTP AUTH |
| `mail.smtp.auth` | Enables configured SMTP authentication |
| `mail.smtp.starttls.enable` | Allows upgrading plaintext SMTP to TLS via STARTTLS |
| `mail.smtp.starttls.required` | Requires STARTTLS to avoid continuing insecurely if unavailable |
| `mail.smtp.ssl.checkserveridentity` | Verifies certificate hostname per SMTP TLS implementation |
| `mail.smtp.connectiontimeout` | TCP connect timeout limit |
| `mail.smtp.timeout` | Socket read limit |
| `mail.smtp.writetimeout` | Socket write limit |

The three timeouts typically use **milliseconds**. The example numbers are not universal defaults for all SMTP providers. Also, `connectiontimeout`, `timeout`, and `writetimeout` **do not create a single overall deadline for `send()`**, because an SMTP session spans multiple commands.

### Facts to verify before diagnosing

1. Does the provider require port 587 + STARTTLS, 465 + implicit TLS, or another setup?
2. Is the relay reached over public networks or private DNS/VPC?
3. Does the provider use SMTP username/password, app passwords, OAuth2/XOAUTH2, or another mechanism?
4. Is the TLS certificate issued by a public CA or an internal CA?
5. Does the workload run in containers, VMs, Kubernetes, or on-prem, and which DNS resolver does it use?
6. Is there an egress proxy/gateway altering network paths or terminating TLS?
7. Are multiple SMTP accounts/routes writing to the same log with distinct root causes?

Never treat a developer laptop's configuration as proof of what production pods run. Inspect the **effective, redacted runtime values** on the failing environment.

## 5. Runbook A — SMTP authentication failures

### A1. Common signals

- SMTP server returns `535` or enhanced status codes indicating invalid credentials.
- Server demands AUTH/TLS before allowing submission (`530` on some servers).
- Authentication service is temporarily unavailable (`454` or provider-equivalent 4xx).
- App password revoked, secret expired, or service account locked.
- SMTP username is valid, but `From` is unauthorized.
- OAuth2 access token expired or lacks SMTP scopes/permissions.

**AUTH failure is not the same as `From` rejection**: if the server accepts `AUTH` yet rejects `MAIL FROM`, that points to sender permissions/policy and belongs to a separate phase.

### A2. Immediate containment

When evidence shows the same credential is failing across jobs:

1. Pause/circuit-break the affected **provider lane**; stop retrying every email with the stale secret.
2. Keep essential emails in the outbox while monitoring backlog age and expiry.
3. Pause or throttle non-urgent marketing.
4. Page mail-platform on-call and the secret owner.
5. Never print passwords in commands, logs, alerts, or tickets.
6. If credential exposure is suspected, follow security compromise response rather than merely refreshing config.

A single `535` on **one email** does not prove the secret was revoked; inspect provider/account scope, instances, and error details before tripping a system-wide breaker.

### A3. Ordered checks

| Step | Question | Safe verification method |
| --- | --- | --- |
| 1 | Which SMTP account is the app using? | Redacted runtime config metadata; provider key |
| 2 | Was the credential recently rotated/revoked? | Secret manager version and audit logs |
| 3 | Are all workers on the same version? | Per-pod secret version/generation metric |
| 4 | Does the account still have send rights? | Provider account status, SMTP AUTH policy |
| 5 | Is TLS enabled in the right mode? | EHLO, STARTTLS capability, sanitized TLS trace |
| 6 | Are app passwords/MFA or XOAUTH2 required? | Provider docs, security configuration |
| 7 | Is `MAIL FROM` rejected after `AUTH`? | SMTP phase, sender authorization |
| 8 | Does a fresh credential authenticate? | Canary test against an authorized endpoint/mailbox |

**Do not hammer the provider with manual password guesses**, which can lock accounts, trigger abuse heuristics, or leak secrets into shell history.

### A4. Checking secret rotation

For providers supporting two active credentials concurrently:

1. Create credential B in the secret manager without revoking A.
2. Test B via an authorized canary, verifying TLS/AUTH and `From` permissions.
3. Roll out B via rolling restart or a verified sender-swap mechanism.
4. Track which replicas/workers still report using A.
5. Let in-flight work using A complete or drain per policy.
6. Revoke A once fleet cutover is confirmed.

If the provider **allows only one active password**, rotating it can invalidate A immediately. Prepare a brief dispatch pause or coordinated cutover, then drain backlog at a controlled rate. Rolling back configuration to an already-revoked password is **not** a viable recovery plan.

### A5. Updating the secret store does not automatically update JavaMailSender

In typical Spring Boot setups, `JavaMailSenderImpl` reads username/password when the bean is initialized. Updating a secret in Vault, Kubernetes Secrets, or mounted files **does not guarantee** running beans reload the new value. Pick an explicit mechanism:

- Rolling restart with the new secret.
- Verified platform refresh/rebinding.
- Constructing a candidate sender, running `testConnection()`/canary, and atomically swapping the application gateway's reference.

Never call `setUsername(...)` followed by `setPassword(...)` on a shared multi-threaded sender assuming atomicity; it can create a mismatched credential window or leave in-flight sends using stale values.

### A6. OAuth2/XOAUTH2

Some SMTP providers support SASL XOAUTH2, where access tokens expire much sooner than static passwords. When using it:

- Refresh tokens ahead of expiry with a safety margin.
- Verify exact SMTP service scopes/permissions.
- Use single-flight refresh instead of letting every mail worker hit the token endpoint independently.
- Distinguish an expired access token from a revoked refresh token.
- When no valid token can be obtained, pause sending and hold the outbox.
- Never fall back to plaintext or anonymous SMTP when `AUTH` fails.

Some providers let you pass the access token as the password in Jakarta Mail XOAUTH2 flows. Exact settings depend on library versions, OAuth2 providers, and flows; merely setting `mail.smtp.auth.mechanisms=XOAUTH2` is insufficient without a working token provider and matching principal.

### A7. Verifying recovery

- A canary completes TLS/AUTH with the new secret version.
- Relay accepts a canary submission to an authorized test recipient.
- AUTH failure metrics drop back to baseline.
- Every instance runs the approved secret generation.
- Retries resume under bounded rate and concurrency.
- Unexpired OTP/transactional messages take priority.
- No outbox record is deleted or falsely marked `SUBMITTED`.
- Old credentials are revoked per policy and audited.

Note: `JavaMailSenderImpl.testConnection()` checks connectivity and may check AUTH depending on configuration, yet **it does not prove deliverability**, quota availability, or `From` permissions for every address. Canary submission and provider events remain separate checks.

## 6. Runbook B — TLS, STARTTLS, and certificate errors

### B1. Common symptoms

- `SSLHandshakeException`, `SSLException`, `CertificateException`.
- `PKIX path building failed` or untrusted chain errors.
- Certificate hostname mismatch (SAN/CN does not match endpoint).
- Incompatible TLS protocol/cipher suite.
- SMTP server fails to advertise STARTTLS in `EHLO` when required by the app.
- `STARTTLS` command fails or drops when starting TLS.
- Using implicit TLS on a STARTTLS-only port, or vice versa.
- Expired certificate on an internal SMTP proxy/relay.

Do not assume every `MailSendException` is TLS-related: Spring Mail wraps errors from multiple layers. Inspect the cause chain and SMTP stage.

### B2. Distinguish STARTTLS from implicit TLS

| Mechanism | Typical sequence | Configuration must match |
| --- | --- | --- |
| STARTTLS | TCP → SMTP 220/EHLO → STARTTLS → TLS handshake → repeat EHLO → AUTH | Port/provider supports STARTTLS, `starttls.enable/required` |
| Implicit TLS | TCP → TLS handshake → SMTP greeting/EHLO → AUTH | Provider expects SSL/TLS immediately, typically `mail.smtp.ssl.enable=true` |

Port **587** commonly serves SMTP submission with STARTTLS, and **465** commonly serves implicit TLS. These are widespread conventions, not guarantees; verify official provider settings. Port 25 is usually MTA-to-MTA or specific internal relays—never switch ports arbitrarily to bypass security policies.

#### STARTTLS example

~~~properties
spring.mail.properties[mail.smtp.starttls.enable]=true
spring.mail.properties[mail.smtp.starttls.required]=true
spring.mail.properties[mail.smtp.ssl.checkserveridentity]=true
~~~

#### Implicit TLS example

~~~properties
spring.mail.properties[mail.smtp.ssl.enable]=true
spring.mail.properties[mail.smtp.ssl.checkserveridentity]=true
~~~

Never combine both modes blindly on one connection without verifying provider behavior. With implicit TLS, verify `host/port` and check certificate names against the connected hostname.

### B3. Containment

1. If TLS is required and handshakes fail, **stop sending on that route** while holding the outbox.
2. Never disable `starttls.required`, hostname verification, or trust validation as a temporary workaround.
3. Never set `mail.smtp.ssl.trust=*` in production to bypass chain failures.
4. Scope the issue: one pod/JVM, one SMTP hostname, all environments, or one egress proxy path?
5. Gather timestamps of recent certificate rotations, CA updates, JDK updates, and egress network changes.
6. Fail over only to an approved backup provider/route that passes full TLS validation—never bypass policy.

### B4. Inspecting TLS directly without exposing credentials

From an environment with OpenSSL and the same egress path as the failing workload, inspect STARTTLS:

~~~bash
openssl s_client \
  -starttls smtp \
  -connect smtp.example.net:587 \
  -servername smtp.example.net \
  -verify_hostname smtp.example.net \
  -showcerts
~~~

For implicit TLS:

~~~bash
openssl s_client \
  -connect smtp.example.net:465 \
  -servername smtp.example.net \
  -verify_hostname smtp.example.net \
  -showcerts
~~~

These commands only inspect the **certificate chain and TLS handshake** without sending passwords or bodies. Run from the actual pod/VM/network when possible; workstation DNS/proxies may not reflect production.

**Do not rely solely on `s_client` exiting 0:** read the chain/hostname verification output, negotiated TLS protocol, presented certificates, and warnings. CA validation depends on the OpenSSL version and OS trust store, which **differ from the Java truststore**.

### B5. Inspecting chains and hostnames

For `PKIX path building failed`, check:

- Is the leaf certificate issued by a trusted CA?
- Does the server send required intermediate certificates?
- Which truststore does the JDK/JRE runtime use?
- Does a custom workload truststore omit an internal CA?
- Was a certificate rotated while an older node still serves the previous chain?
- Is a TLS-inspecting proxy unexpectedly swapping certificates?
- Is clock skew causing "not yet valid" or "expired"?

For hostname mismatches:

- Does the app connect to `smtp.example.net` while SAN only lists `mail.internal.example.net`?
- Does a DNS CNAME point to another host whose certificate omits **the hostname the app verifies**?
- Does a load balancer/SNI route return another tenant's certificate?
- Is the app connecting directly by IP instead of the expected hostname?

**Never fix this by disabling `mail.smtp.ssl.checkserveridentity`.** Fix the configured hostname, certificate SAN, or endpoint instead.

### B6. Distinguish Java truststores from OpenSSL

OpenSSL may trust certificates in the OS store, whereas the JVM uses its own truststore or properties such as:

~~~text
javax.net.ssl.trustStore
javax.net.ssl.trustStoreType
javax.net.ssl.trustStorePassword
~~~

These are JVM/system properties in some Java TLS configurations. Never print truststore passwords or dump full JVM arguments containing secrets. When inspecting a truststore, use tools like `keytool -list` against the exact path with proper authorization, and keep sensitive output restricted.

A custom truststore can omit standard public CAs, causing a laptop to connect while pods fail. For private CAs, add the **approved trusted CA** via operational processes—never use trust-all.

### B7. Expired certificates

An expired certificate can break all workers simultaneously at the exact expiry timestamp. Runbook:

1. Verify `notBefore`/`notAfter` on the certificate **actually served by the endpoint**.
2. Check hostnames across all endpoints/load-balancer pool nodes.
3. Check system clocks and clock skew.
4. Renew/deploy the new certificate with a valid chain.
5. Reload/restart TLS endpoints per infrastructure procedure.
6. Test a canary against the real hostname from a workload sharing the same truststore.
7. Monitor TLS failures and outbox backlog while resuming dispatch with pacing.

Do not inspect a cert file on an admin laptop and assume the live server uses it. A listener may not have reloaded, a load-balancer node may hold an older cert, or SNI may route elsewhere.

### B8. TLS protocol/cipher mismatches

A newer JVM may disable legacy protocols/ciphers while an older SMTP relay has not upgraded—or a provider may require newer TLS. On handshake failures:

- Identify JDK version, Java security policy, and proposed TLS versions.
- Inspect supported protocols/ciphers on client and server using approved diagnostics.
- Check recent JDK, server, or proxy updates.
- Upgrade the relay/provider to support modern secure protocols.
- Never re-enable weak ciphers/protocols without explicit security sign-off.

### B9. STARTTLS stripping/downgrade

If the provider requires TLS and the server stops advertising `STARTTLS`, the client must refuse to send when `starttls.required=true`. An attacker or misbehaving proxy can strip capabilities; that is **never a reason to turn off TLS**.

Check:

1. Are port and host right?
2. Do `EHLO` capabilities on the failing path advertise `STARTTLS`?
3. Is a proxy/firewall performing SMTP protocol inspection?
4. Is the provider having an incident or changing submission endpoint settings?
5. Were implicit TLS and STARTTLS confused?

### B10. Verifying TLS recovery

- TLS handshake succeeds with a valid certificate chain.
- Hostname verification passes on the **real runtime**.
- SMTP AUTH succeeds without transmitting credentials over an unencrypted channel.
- Canary submission is accepted.
- TLS failure rates drop and mail queues drain within rate limits.
- No temporary `trust-all`, TLS-off, or disabled validation settings remain.

## 7. Runbook C — DNS failures

**DNS** serves multiple roles in email delivery. Separate:

1. DNS for the **SMTP submission endpoint** `JavaMailSender` connects to.
2. DNS for **recipient domains** used during downstream delivery.
3. DNS for **sender identity authentication**: SPF, DKIM, DMARC.
4. Reverse DNS/PTR and reputation (typically managed by the outbound MTA/provider).

An application using a configured SMTP relay usually **does not look up MX records for recipient domains** inside `JavaMailSender.send()`. It connects to the relay hostname; the relay/provider performs downstream routing. Keep this boundary clear during investigations.

### C1. Symptoms by DNS category

| Category | Signals | Mechanism |
| --- | --- | --- |
| SMTP host unresolved | `UnknownHostException`, DNS timeout | App cannot resolve IP for `spring.mail.host` |
| A/AAAA route mismatch | IPv6 connect errors, stale IP not serving SMTP | Resolver returns an unreachable IP |
| Wrong CNAME/alias | Points to staging or another region | Connects to wrong server or causes TLS mismatch |
| Recipient domain MX failure | Provider reports deferred/bounced post-acceptance | Relay cannot find a downstream mail route |
| Wrong/missing SPF | Auth/reputation issues or remote rejects | Domain fails to authorize sending sources |
| Wrong/missing DKIM record | Remote DKIM verification fails | Public key selector/domain mismatches signature |
| DMARC policy/alignment | Remote reject/quarantine per receiver | Header `From` misaligns with SPF/DKIM under strict policy |
| PTR/reverse DNS | Remote reputation/policy rejection | Outbound IP lacks or mismatches reverse mapping |

Do not edit SPF/DKIM/DMARC records when `UnknownHostException` occurs for the SMTP host. They belong to different DNS layers.

### C2. Checking the effective SMTP hostname

First verify the effective `spring.mail.host` on failing instances. It may be:

- A public provider-assigned hostname.
- A private hostname resolvable only inside a VPC/VPN.
- An internal relay alias with split-horizon DNS.
- A Kubernetes Service DNS name.
- An alias injected from secrets/config/Helm charts.

Do not "fix" DNS by hardcoding an IP address if the provider requires hostname/SNI for TLS verification. Using raw IPs breaks TLS validation, bypasses load balancing/failover, and can misroute traffic.

### C3. Checking DNS from the right environment

On Windows PowerShell:

~~~powershell
Resolve-DnsName smtp.example.net -Type A
Resolve-DnsName smtp.example.net -Type AAAA
Resolve-DnsName smtp.example.net -Type CNAME
Test-NetConnection smtp.example.net -Port 587
~~~

Where `dig` is available:

~~~bash
dig smtp.example.net A
dig smtp.example.net AAAA
dig smtp.example.net CNAME
~~~

Or `nslookup` when present:

~~~text
nslookup smtp.example.net
~~~

`Test-NetConnection` checks basic TCP reachability; **it does not verify STARTTLS, TLS certificates, or SMTP AUTH**. `dig`/`nslookup` query the local shell environment's resolver; their results may differ from `InetAddress` inside the JVM if JVM caching or resolver configs differ.

### C4. Interpreting DNS responses accurately

| Response | What to investigate |
| --- | --- |
| NXDOMAIN | Domain name does not exist in the current resolver/view |
| SERVFAIL | Resolver/authoritative DNS hit an error serving the lookup |
| Timeout | DNS query got no timely reply; check network/resolver |
| NOERROR with no requested record | Name may exist, but not with that record type |
| A returns unreachable IP | DNS returned data, yet route/firewall/endpoint is broken |
| AAAA returns IPv6 with broken path | IPv6 connect fails; check address selection/routing |
| CNAME points to wrong region/endpoint | Stale alias/config or un-synced DNS rollout |

Never lump NXDOMAIN, SERVFAIL, timeouts, and TCP refused together as "DNS is down." Each has distinct causes and owners.

### C5. Query DNS directly from the pod/VM

In Kubernetes/container production:

- Query DNS from a pod sharing the mail worker's namespace and network policies.
- Inspect `nameserver`/`search` entries in the pod's resolver configuration.
- Check CoreDNS or internal DNS resolvers if present.
- Compare results with a healthy pod in the same cluster.
- Verify DNS policies, egress rules, NAT, and routing to the SMTP endpoint.
- Check for differences across nodes, zones, or regions.

A passing `dig` on a laptop never proves production pods can resolve the name. With DNS caching, the JVM may keep an older IP even after `dig` returns the new one.

### C6. Java DNS caching and TTL

Java networking can cache name lookups. TTL behavior depends on runtime, security properties, OS, and how the app performs lookups. When an SMTP provider changes IPs while the app keeps hitting the old endpoint:

1. Check when the DNS record changed.
2. Check whether the resolver returns the new or old answer.
3. Check JVM/runtime positive and negative DNS caching.
4. Never set extremely low or infinite TTLs without evaluating load, latency, and failover impact.
5. If a rollout/restart is needed to flush caches or connections, do it systematically.

Relevant Java settings include `networkaddress.cache.ttl` and `networkaddress.cache.negative.ttl` in Java security properties. Enforcement depends on JDK version and environment; never assume placing them in `application.yml` updates JVM caching automatically.

### C7. A and AAAA: IPv4/IPv6 paths

When an SMTP hostname publishes both `A` and `AAAA` records, the Java/network stack tries addresses according to runtime order/policy. A broken IPv6 path can make one environment time out while IPv4 succeeds.

Actions:

- Compare returned `A`/`AAAA` answers across healthy and failing workloads.
- Test real connectivity to each returned IP with authorized diagnostics.
- Check recent IPv6/network changes.
- Work with network/platform teams to fix routing, firewalls, or provider endpoints.

Never set `-Djava.net.preferIPv4Stack=true` as a "blanket fix" without diagnosing first, since it changes JVM-wide networking and can affect other services.

### C8. Wrong DNS alias triggers TLS hostname mismatch

Suppose `smtp.internal.example.net` CNAMEs to a provider endpoint, yet the certificate SAN only covers the provider hostname or another alias. Resolving to the right IP is not enough; TLS hostname verification will still fail.

Fixes:

- Use a hostname supported in the provider's TLS certificate.
- Or provision an appropriate certificate on your internal relay/proxy.
- Check SNI and load-balancer routing.
- Never disable hostname verification just to keep an incompatible alias.

### C9. Recipient domain DNS: querying MX for downstream issues

If `JavaMailSender` submits successfully yet the provider reports bounces/deferrals for failing to locate recipient mail servers, query MX records **for the recipient domain**, not the SMTP submission host:

~~~bash
dig example.org MX
dig example.org A
dig example.org AAAA
~~~

In PowerShell:

~~~powershell
Resolve-DnsName example.org -Type MX
~~~

Notes:

- Lack of MX does not always mean a domain rejects mail: SMTP allows fallback to address records under specific rules, whereas a null MX (`0 .`) explicitly signals no mail accepted.
- An MX pointing to an unresolvable target or broken route can cause delivery failure.
- Providers cache DNS, queue, and retry automatically; applications must not generate duplicate messages upon seeing `DEFERRED`.
- Inspect remote MX replies and provider events; never judge mailbox validity solely from an MX query.

Never equate a successful DNS MX lookup with Inbox delivery.

### C10. SPF, DKIM, and DMARC: sender identity DNS

Another failure mode occurs when `JavaMailSender.send()` succeeds, yet remote servers reject or spam-folder mail due to failed sender authentication. In that case, inspect the sending domain's DNS, not just the SMTP relay hostname.

| Technology | DNS record / mechanism | Purpose |
| --- | --- | --- |
| SPF | Domain TXT record used for SPF evaluation, usually tied to envelope `MAIL FROM` | Lists IPs authorized to send for that domain |
| DKIM | TXT at `selector._domainkey.example.net` | Public key validating the message's DKIM signature |
| DMARC | TXT at `_dmarc.example.net` | Policy and alignment of header `From` with SPF/DKIM |
| PTR/reverse DNS | Reverse mapping of outbound IP | Aids identity/routing/reputation checks at receiving servers |

#### Checking SPF

~~~bash
dig example.net TXT
~~~

Or:

~~~powershell
Resolve-DnsName example.net -Type TXT
~~~

Verify which SPF domain receivers actually evaluate—it may differ from the visible `From` header domain. Simply seeing `v=spf1` in a TXT record does not guarantee pass; evaluation depends on **sending IP, envelope identity**, `include`/`redirect` chains, DNS lookup limits, and actual provider routing.

#### Checking DKIM

If a message carries a DKIM header with selector `s=mail2026` and signing domain `d=example.net`, inspect:

~~~bash
dig mail2026._domainkey.example.net TXT
~~~

During DKIM key rotation, ensure the signer uses the matching selector and the public key is published to receiving resolvers before cutting over all traffic. Some providers manage DKIM automatically; avoid manual record edits conflicting with provider guidance.

#### Checking DMARC

~~~bash
dig _dmarc.example.net TXT
~~~

DMARC is not merely "having SPF and DKIM records." Evaluate both **authentication results** and domain alignment with the header `From`. Providers can report SPF pass or DKIM pass while DMARC fails due to misalignment. `p=none`, `quarantine`, and `reject` carry very different effects. Never downgrade `p=reject` to `p=none` hastily without impact analysis and approval.

#### Dependency diagram

~~~text
Application SMTP submission
          |
          v
Outbound relay / provider
          |
          +-- Uses sending IP / envelope sender  -> SPF assessment
          +-- Adds DKIM signature                -> DKIM DNS lookup
          +-- Sends header From domain           -> DMARC alignment
          |
          v
Remote MX evaluates authentication and policy
          |
          +-- Accept / defer / reject / spam handling
~~~

**Boundary to remember:** SPF/DKIM/DMARC are normally evaluated downstream by receivers during delivery. They do not directly explain why your application throws `UnknownHostException` resolving `spring.mail.host`.

### C11. DNS propagation, caches, and inconsistent views

A DNS update can look different depending on resolver, TTL, split-horizon views, and cache fill times. During triage:

1. Record old/new values, TTL, and change timestamp.
2. Query the exact resolver used by the workload.
3. If authorized and appropriate, compare authoritative DNS against recursive resolvers.
4. Check for typos, stale aliases, duplicate policies, or nonexistent targets.
5. Compare affected versus unaffected nodes/pods.
6. Avoid editing records repeatedly before TTLs expire; constant churn extends inconsistency.

Never promise "DNS propagation will finish in exactly 5 minutes" without evidence. Resolvers enforce positive/negative caches and internal environments have custom rules.

### C12. Verifying DNS recovery

- SMTP hostname resolves consistently from the affected network/pods.
- Target IP is reachable and the TCP port is open.
- TLS hostname/certificate matches the resolved name and connection config.
- AUTH succeeds and a canary submission is accepted.
- DNS errors, mail queue age, and delivery latency return to normal ranges.
- For SPF/DKIM/DMARC, verify authentication results or test-recipient headers/reports, not merely "the TXT record exists."
- Deferred/bounced messages are handled per policy, never replayed en masse without evidence.

## 8. Runbook D — separating DNS, TCP, TLS, and AUTH in practice

Ordered investigation from least invasive to most invasive:

~~~text
1) Inspect redacted app config
   - host, port, TLS mode, provider key
          |
          v
2) Resolve host via DNS from the workload
   - A/AAAA/CNAME, NXDOMAIN/SERVFAIL/timeout
          |
          v
3) Test TCP to host:port
   - refused, timeout, route/firewall
          |
          v
4) Check SMTP banner/EHLO and TLS handshake
   - STARTTLS/implicit TLS, certificate, SAN/chain
          |
          v
5) Test SMTP AUTH with an authorized canary
   - principal, secret version, OAuth2 rights
          |
          v
6) Check MAIL FROM/RCPT TO/DATA
   - From authorization, recipient/policy, quota
          |
          v
7) Monitor provider queue/events
   - deferred/bounce/delivered/complaint
~~~

### Example of multi-layer failures occurring simultaneously

A single deployment might change `spring.mail.host` to a new hostname, miss the alias in the TLS certificate, and load the wrong secret version. Fixing DNS exposes the TLS error; fixing TLS exposes the AUTH error. Never assume full recovery simply because the first exception disappeared.

Work layer by layer until a canary submission succeeds, then observe downstream delivery.

### Avoiding self-inflicted issues during diagnosis

- Keep canary volume low using an authorized test mailbox.
- Never have every worker call `testConnection()` in tight loops.
- Avoid changing truststores, DNS, and secrets simultaneously when changes can be isolated.
- Log timestamps of every change and before/after observations.
- Before rolling back, confirm old credentials/certificates/records are still valid.
- Never run diagnostic tools with passwords or tokens on command lines or in URLs.

## 9. Classifying SMTP replies to avoid misdiagnosis

AUTH, TLS, and DNS errors can overlap with SMTP recipient or policy errors. Useful rule table:

| Evidence | Failure domain | Suggested action |
| --- | --- | --- |
| SMTP host DNS NXDOMAIN | Endpoint/config/platform | Fix DNS/hostname, preserve outbox |
| DNS timeout | Resolver/network | Check DNS service/route, retry with backoff |
| TCP refused | Endpoint/firewall/port | Check listener, port, network policy |
| Untrusted TLS certificate | TLS endpoint/trust | Fix chain/truststore safely; never trust-all |
| STARTTLS required yet unavailable | Transport mode/policy | Fix endpoint/port/TLS capability; no downgrade |
| SMTP AUTH 535 | Account/credentials/policy | Stop retry storm, check secret and rights |
| SMTP AUTH 454 | Provider temporary AUTH issue | Backoff/monitor provider; avoid refresh floods |
| MAIL FROM 553 | Sender/permission/policy | Check `From` permissions; do not suppress recipients |
| RCPT TO 550 5.1.1 | Specific invalid recipient reply | May be permanent/suppress recipient |
| RCPT TO 450/451 | Temporary recipient/service issue | Bounded retry, monitor |
| DATA 554 | Explicit message/content/policy reply | Investigate content/policy |
| Lost final reply after DATA | Unknown outcome | Do not immediately resend; reconcile |
| SMTP 250 after DATA | Relay accepted | Track downstream provider events |

Providers may attach different meanings to codes depending on phase. Enhanced status codes and reply text aid classification yet can be incomplete; preserve sanitized diagnostics for analysis.

### SMTP 4xx is not HTTP 429

SMTP uses its own reply codes and enhanced status codes. HTTP provider APIs can return `429 Too Many Requests` with `Retry-After`, whereas SMTP **has no standard HTTP `Retry-After` header**. If a provider embeds retry guidance in SMTP text or docs, handle it per that contract rather than parsing HTTP headers from `MailException`.

## 10. Structuring Spring code for diagnosis and recovery

`JavaMailSenderImpl` is an SMTP submission adapter; business layers must not catch a broad `MailException` and label everything "invalid recipient" or "retryable."

### Application failure classification model

~~~java
package com.example.mail.ops;

public enum MailFailureCategory {
    DNS_RESOLUTION,
    TCP_CONNECTIVITY,
    SMTP_READ_TIMEOUT,
    SMTP_WRITE_TIMEOUT,
    TLS_CONFIGURATION,
    TLS_CERTIFICATE,
    SMTP_AUTH,
    SMTP_AUTH_TEMPORARY,
    SENDER_POLICY,
    RECIPIENT_TEMPORARY,
    RECIPIENT_PERMANENT,
    CONTENT_POLICY,
    SUBMISSION_UNKNOWN,
    OTHER
}

public record MailFailure(
        MailFailureCategory category,
        String providerKey,
        String normalizedSmtpCode,
        String phase,
        boolean retryable,
        boolean recipientScoped) {
}
~~~

These are internal application types, not built-in Spring Mail classes. The adapter inspects the cause chain and Jakarta Mail transport exceptions while recording the **SMTP phase** when instrumented. Never rely solely on fragile exception message strings to trigger permanent suppression.

### Layering responsibilities

~~~text
Business service
  - Persist notification + outbox inside transaction
           |
           v
Mail worker
  - Claim work / check expiry & suppression
  - Acquire rate limiter/concurrency budget
           |
           v
Transport adapter
  - Build MIME / call JavaMailSender.send()
  - Normalize exception into MailFailure
           |
           v
Policy service
  - Retry? hold account? suppress recipient?
  - Unknown submission? alert?
           |
           v
Outbox state + telemetry + incident monitoring
~~~

### Example exception-translation boundary

~~~java
import org.springframework.mail.MailException;
import org.springframework.mail.javamail.JavaMailSender;
import org.springframework.mail.SimpleMailMessage;

public final class SmtpSubmissionAdapter {

    private final JavaMailSender sender;
    private final MailFailureClassifier classifier;

    public SmtpSubmissionAdapter(
            JavaMailSender sender,
            MailFailureClassifier classifier) {
        this.sender = sender;
        this.classifier = classifier;
    }

    public SubmissionResult submit(SimpleMailMessage message) {
        try {
            sender.send(message);
            return SubmissionResult.submitted();
        } catch (MailException cause) {
            MailFailure failure = classifier.classify(cause);
            return SubmissionResult.failed(failure);
        }
    }
}
~~~

`MailFailureClassifier` and `SubmissionResult` are application-defined interfaces/types. This shows where normalization sits—it does **not** imply every `MailException` carries enough context to identify the SMTP phase. When the final `DATA` response drops, deeper transport hooks or provider message lookups may be needed to recognize `SUBMISSION_UNKNOWN`.

### How to use `JavaMailSenderImpl.testConnection()`

`testConnection()` verifies basic connectivity with the active configuration, not full end-to-end deliverability. Never wire it into every HTTP readiness probe across hundreds of pods or during provider outages, as that triggers connection/auth storms. Use it for:

- Rate-controlled startup/canary checks.
- A rate-limited, backoff-protected scheduled health probe.
- Pre-cutover validation of a candidate secret/TLS config.
- One-off verification after a config change.

In multi-function web apps using an outbox, an SMTP outage makes the mail lane degraded yet **does not necessarily** justify pulling the whole web tier out of the load balancer. Readiness strategy depends on architecture and SLAs.

## 11. Observability and metrics supporting the runbook

A runbook only works effectively when telemetry answers "which layer failed" and "did recovery actually take hold."

| Suggested metric | Purpose |
| --- | --- |
| `mail_submission_attempts_total` | Total submission attempts started |
| `mail_submission_success_total` | Successful SMTP submissions per reply |
| `mail_submission_failures_total` | Failures by category/provider/stage |
| `mail_smtp_auth_failures_total` | Detect credential/account failures |
| `mail_tls_handshake_failures_total` | Track TLS failures |
| `mail_dns_failures_total` | Track hostname resolution failures |
| `mail_smtp_timeout_total` | Track connect/read/write timeouts when known |
| `mail_smtp_latency_seconds` | Submission execution duration |
| `mail_inflight_sends` | Active concurrent send calls |
| `mail_outbox_pending` | Pending backlog |
| `mail_outbox_oldest_age_seconds` | Age of oldest waiting job |
| `mail_retry_pending` | Messages scheduled for retry |
| `mail_submission_unknown_total` | Attempts with uncertain outcome |
| `mail_secret_active_generation` | Active secret generation per instance |
| `mail_secret_seconds_until_expiry` | Credential expiry countdown if metadata exists |
| `mail_tls_cert_seconds_until_expiry` | Certificate expiry if monitor has authoritative source |
| `mail_provider_deferred_total` | Provider-reported deferrals |
| `mail_provider_bounced_total` | Provider-reported bounces |

Metric names are application-defined via Micrometer/Spring Boot Actuator or your monitoring stack. **Spring Mail does not emit all of these automatically.**

### Labels and cardinality

Prefer low-cardinality dimensions such as:

- provider key or SMTP route ID.
- failure category.
- SMTP phase.
- notification category (security, transactional, marketing).
- region/cluster.
- JVM/instance identifier as needed.

Avoid:

- Raw SMTP passwords or OAuth tokens.
- Full recipient addresses, OTPs, or reset tokens.
- Notification UUIDs as Prometheus labels.
- Raw exception messages as labels (risks sensitive data leaks and huge cardinality).

Detailed IDs belong in access-controlled logs/event stores, not per-message metric labels.

### Structured log example

~~~json
{
  "event": "mail_submission_failed",
  "notificationId": "notif-184",
  "attemptId": "attempt-3",
  "providerKey": "smtp-primary",
  "smtpPhase": "AUTH",
  "category": "SMTP_AUTH",
  "smtpCode": "535",
  "secretGeneration": "g42",
  "retryable": false
}
~~~

This log format is illustrative, not built into Jakarta Mail. Log only investigative metadata; never copy raw SMTP transcripts containing credentials, bodies, or recipient lists into public dashboards or traces.

## 12. Setting up alerts and defining recovery

### Useful alerts

| Alert | Signal | Escalation owner |
| --- | --- | --- |
| SMTP AUTH spike | AUTH errors rising rapidly on an account | Mail ops + secret owner |
| TLS handshake failures | TLS error rate climbs after deploy/cert rotation | Platform/network/security |
| DNS resolution failures | NXDOMAIN/SERVFAIL/timeouts from app | Platform/DNS/network |
| Secret expires soon | Credential nears expiry with no newer active version | Secret owner |
| TLS cert expires soon | Active certificate nears expiration | TLS endpoint owner |
| Email backlog SLA breach | Oldest age breaches category SLA | Mail ops + business owner |
| Too many unknown submissions | Many attempts lost final reply | Mail ops/provider |
| Provider 4xx throttling | Deferrals or temporary SMTP errors rising | Mail ops/provider |

### Avoiding noisy alerts

A single transient DNS timeout is rarely a P1 incident. Base alerts on:

- Both absolute count and error ratio over sufficient sample size.
- Number of affected clusters/instances.
- Impact on transactional/OTP delivery.
- Backlog growth rate and oldest message age.
- Provider degradation or recent changes.
- Sustained recurrence over a meaningful window.

One OTP exceeding its SLA can be worse than thousands of delayed marketing emails. Set thresholds per notification type and business purpose.

### Post-remediation verification criteria

Do not close an incident just because an alert clears. Verify:

1. DNS resolution and TCP connectivity are stable from live workloads.
2. TLS handshakes pass with the right hostname and truststore.
3. SMTP AUTH or configured mechanism succeeds with the provider.
4. A canary SMTP submission succeeds.
5. Provider events (if integrated) continue flowing.
6. Actual error rates stay low across multiple observation windows.
7. Backlog shrinks and valid OTP/transactional jobs drain.
8. No weakened temporary credential/certificate settings remain.
9. `SUBMISSION_UNKNOWN` records were not blindly resent en masse.
10. Changes, audits, and follow-up actions are recorded.

## 13. Protecting the transactional outbox during SMTP incidents

In transactional systems, AUTH/TLS/DNS failures must never lose business data or block database transactions across network waits.

### Decouple database writes from email sending

~~~text
Order/payment/signup transaction
      |
      +-- Save business data
      +-- Save email outbox request
      |
      v
     COMMIT
      |
      v
Mail dispatcher
      |
      +-- Check expiry, consent, suppression
      +-- Acquire concurrency + rate budget
      +-- Submit via JavaMailSender
      |
      +-- SUBMITTED
      +-- RETRY_PENDING
      +-- WAITING_FOR_CREDENTIAL
      +-- SUBMISSION_UNKNOWN
      +-- FAILED_PERMANENT / EXPIRED
~~~

Never make blocking SMTP calls inside a long database transaction. The mail server does not participate in database ACID transactions: if the relay accepts the email and the DB rolls back, the email still goes out for a cancelled business action.

### States to distinguish

| Application state | Meaning | Can scheduler send immediately? |
| --- | --- | --- |
| `PENDING` | Request saved, not yet started | Yes, if eligible and within quota |
| `PROCESSING` | Worker claimed with lease | Never double-claim while lease valid |
| `RETRY_PENDING` | Temporary error, waiting for `nextAttemptAt` | Only when due |
| `WAITING_FOR_CREDENTIAL` | Lane blocked due to AUTH/secret issue | Not until credentials are valid |
| `SUBMITTED` | Relay accepted per response received by app | Never auto-retry |
| `SUBMISSION_UNKNOWN` | Uncertain whether relay accepted | Never retry blindly |
| `FAILED_PERMANENT` | Current error should not retry as transient | Replay only after investigation |
| `EXPIRED` | Content/token no longer valid | No |
| `SUPPRESSED` | Blocked by consent/bounce/complaint | No |

This is an application-defined illustrative model, not states provided by Spring Mail.

### Pre-submission AUTH/TLS/DNS errors

If DNS fails to resolve or TLS handshakes fail before any SMTP `DATA` is sent, the application has strong grounds to know **that attempt did not submit the message to the relay**. It can reschedule retries once infrastructure recovers, subject to expiry, rate limits, and retry budgets.

For AUTH failures on the same account, the right policy is usually holding the queue and pausing the provider lane until credentials are fixed, rather than burning `attempts` endlessly across jobs.

### Uncertainty after DATA

~~~text
Application                     SMTP relay
    |-------- DATA body --------->|
    |-------- end marker -------->|
    |                              | Relay may have accepted
    |<-- final response lost ------X
    |
    v
SUBMISSION_UNKNOWN
~~~

This case is not a typical DNS/TLS/AUTH failure, yet it matters greatly when recovering backlogs after network incidents. Resetting every `PROCESSING` or `FAILED` row back to `PENDING` risks resending messages the relay already accepted.

Keep the attempt ID, provider correlation ID if available, send timestamp, and status. If the provider exposes an event API or relay logs, reconcile first; otherwise apply an approved duplicate-risk policy. `Message-ID` assists tracing but does not guarantee exactly-once SMTP delivery.

### Budgeted retries and recovery

- Exponential backoff with jitter for recoverable failures.
- Maximum attempts and maximum notification age.
- Provider/account-wide rate limits, not just per-instance caps.
- Cap on concurrent in-flight SMTP sends.
- Retry schedules persisted in the durable outbox without sleeping worker threads.
- When the circuit breaker closes, drain the backlog within quota instead of dumping everything at once.
- Valid OTP/security mail takes priority over optional campaigns.
- Marketing messages past campaign windows or for unsubscribed recipients must be suppressed/expired.

A 15-minute DNS outage can leave thousands of jobs due simultaneously once DNS recovers. **Restoring infrastructure is step one; pacing catch-up traffic is step two.**

## 14. Pinpointing failures from Spring Mail exceptions

Spring Mail defines several `MailException` subclasses; Jakarta Mail and networking libraries add underlying exceptions. Runbooks should capture a **sanitized** cause chain and classify it in a dedicated adapter.

### Common exceptions

| Exception/type | Likely indication |
| --- | --- |
| `MailAuthenticationException` | AUTH failure per Spring Mail mapping |
| `MailSendException` | One or more messages failed to send |
| `MailParseException` | Message structure/parsing error |
| `MailPreparationException` | Error while preparing email |
| `MessagingException` | Jakarta Mail error; inspect nested cause/phase |
| `UnknownHostException` | Resolver failed to find host or lookup failed |
| `ConnectException` | Connection refused or other connect error |
| `SocketTimeoutException` | A socket operation timed out |
| `SSLHandshakeException` | TLS handshake failed to complete; various causes |

Never classify from exception type name alone. For instance, `SocketTimeoutException` can happen waiting for the greeting, AUTH reply, or final `DATA` reply—each with different retry consequences. If a transport wrapper does not know the phase, treat the outcome as **uncertain** rather than guessing "not sent."

### One way to model classification results

~~~java
public enum RecoveryDecision {
    RETRY_WITH_BACKOFF,
    PAUSE_PROVIDER_LANE,
    FIX_TLS_OR_DNS_CONFIG,
    FIX_RECIPIENT_OR_CONTENT,
    RECONCILE_UNKNOWN,
    HOLD_EXPIRED_OR_SUPPRESSED
}

public record MailIncidentClassification(
        MailFailureCategory category,
        RecoveryDecision decision,
        String sourceProvider,
        String smtpPhase,
        String sanitizedDiagnosticCode) {
}
~~~

These are application-layer types. Not every field applies to every exception; when the phase is unknown, represent missing information accurately rather than guessing.

### Never print raw SMTP transcripts

Low-level SMTP protocol debug logging helps in isolated environments, yet can expose usernames, `AUTH` exchanges, recipients, and message bodies. In production:

- Prefer structured logs containing only provider, phase, category, code, and attempt ID.
- Sanitize exception text before persistence.
- Never leave `mail.debug=true` enabled long-term without auditing its output.
- Never log raw `spring.mail.password`, OAuth access tokens, or email content.
- Enforce restricted access and short retention on deep-investigation support bundles.

## 15. Controlled diagnostics with common tools

Commands below are diagnostic examples. Do not assume every tool is installed in containers, and never ad-hoc install packages into production images against policy. Run from an authorized diagnostic pod sharing the same DNS/network path.

### 15.1. Checking DNS and TCP

Windows PowerShell:

~~~powershell
Resolve-DnsName smtp.example.net -Type A
Resolve-DnsName smtp.example.net -Type AAAA
Test-NetConnection smtp.example.net -Port 587
~~~

Linux with standard utilities installed:

~~~bash
getent ahosts smtp.example.net
dig smtp.example.net A
dig smtp.example.net AAAA
~~~

`Test-NetConnection` showing TCP success does not prove TLS/AUTH works. `dig` returning an `A` record does not prove the firewall allows traffic.

### 15.2. Checking TLS and certificates

STARTTLS:

~~~bash
openssl s_client -starttls smtp \
  -connect smtp.example.net:587 \
  -servername smtp.example.net \
  -verify_hostname smtp.example.net
~~~

Implicit TLS:

~~~bash
openssl s_client \
  -connect smtp.example.net:465 \
  -servername smtp.example.net \
  -verify_hostname smtp.example.net
~~~

No username/password is needed; never paste credentials into a terminal session to "test AUTH" where shell history or shared logs capture them. Verify authentication via controlled application/secret-integrated canaries.

### 15.3. Checking sender DNS

~~~bash
dig example.net TXT
dig mail2026._domainkey.example.net TXT
dig _dmarc.example.net TXT
~~~

Query only the actual DKIM selector used by your app/provider rather than guessing `mail2026`. Check the `DKIM-Signature` header of an authorized test email if permitted.

### 15.4. Querying a specific resolver

Where querying a specific DNS resolver is authorized:

~~~bash
dig @192.0.2.53 smtp.example.net A
~~~

`192.0.2.53` is a documentation IP, not a real operational resolver. Replace it with a valid DNS server for the environment under investigation. Avoid using public resolvers as a workaround for private DNS if that violates policy or leaks internal domain names.

### 15.5. Checking certificates from the JVM side

When OpenSSL succeeds yet Java reports PKIX errors:

- Record the JDK runtime version and active truststore.
- Inspect truststore JVM system properties **without printing passwords**.
- Inspect CA/intermediate entries inside the truststore with authorized tooling.
- Verify JDK hostname verification and TLS protocol settings.
- Never deploy an all-trusting `TrustManager` in production.

An integration check running `JavaMailSenderImpl.testConnection()` with production-matching config against a canary endpoint provides more direct proof of Java TLS behavior than OpenSSL output from a laptop.

## 16. Case studies: common incident scenarios

### Case 1 — Secret rotated, one pod still uses the old version

**Symptom:** after rotation, two pods send cleanly while one continuously logs `AUTH 535`. All share identical SMTP host and TLS settings.

**Investigation:**

1. Compare secret generation/rollout revision across pods.
2. Check whether the failing instance restarted/rebound its sender.
3. Verify whether the old credential was revoked before pod cutover.
4. Pause dispatching on the stale pod to stop an AUTH storm.
5. Update the sender / restart the pod and verify with a canary.
6. Confirm the whole fleet uses the approved generation before closing the incident.

**Do not:** turn on tight per-email retries or mark all recipients invalid.

### Case 2 — Relay certificate renewed while pods hold an old truststore

**Symptom:** OpenSSL on a workstation sees a valid chain, yet Java inside containers throws `PKIX path building failed`.

**Investigation:**

1. Compare the certificate chain from the pod's network path vs workstation.
2. Inspect runtime/JDK version and custom truststore.
3. Check whether the provider recently changed intermediate/root CAs.
4. Check whether any load-balancer node still serves the old certificate.
5. Update the truststore/CA via security workflow and roll out a canary.
6. Never add trust-all or disable hostname verification.

**Verification point:** test SMTP AUTH and submission with the actual Java sender, not OpenSSL handshakes alone.

### Case 3 — SMTP hostname changed IP, inconsistent caches/resolvers

**Symptom:** one region/pod times out to the old IP while other pods send normally.

**Investigation:**

1. Check SMTP hostname and `A`/`AAAA` results in each region.
2. Compare DNS resolvers, TTLs, and change timestamps.
3. Inspect JVM DNS caching and persistent connection reuse.
4. Check routing/firewalls to each resolved IP.
5. Fix DNS/network issues or perform a controlled rollout refresh.
6. Watch per-region success rates and backlogs.

**Do not:** temporarily hardcode a provider IP and break TLS hostname validation or failover.

### Case 4 — SMTP AUTH succeeds, sender policy rejects

**Symptom:** `AUTH 235` succeeds, yet the server returns `553` or `550`/`554` at `MAIL FROM`.

**Investigation:**

1. Inspect both the envelope sender and the `From` header.
2. Verify whether the account has rights to send for that domain/identity.
3. Check provider verified identities and sender policies.
4. Check DKIM/SPF/DMARC if the reply mentions them.
5. Fix permissions or sender identity, then send a canary with the right `From`.

**Do not:** rotate the SMTP password when credentials already authenticate and the real failure is sending authorization.

### Case 5 — SPF/DKIM/DMARC errors after switching providers

**Symptom:** the app's `send()` succeeds, yet provider events show remote recipient MXs rejecting or spam-foldering mail after cutover.

**Investigation:**

1. Identify the new provider's sending IPs, envelope `MAIL FROM`, and DKIM signing domain.
2. Verify SPF `TXT`, DKIM selector `TXT`, and DMARC record/alignment.
3. Inspect authentication headers on an authorized canary email.
4. Adjust DNS per provider documentation and domain policy.
5. Monitor bounce/deferral/complaint rates across before/after cohorts.

**Do not:** bump SMTP timeouts or rotate passwords to solve remote authentication failures.

### Case 6 — TLS mismatch after switching to port 465

**Symptom:** previously used 587 + STARTTLS; after changing to port 465, the client never receives 220 as expected or fails handshaking.

**Investigation:** check whether the provider expects implicit TLS on 465; if so, set `mail.smtp.ssl.enable=true` with proper hostname verification and avoid running `STARTTLS` on an implicit-TLS endpoint unless supported. Verify with OpenSSL in the right mode plus a Java canary.

### Case 7 — Endpoint DNS healthy, yet provider reports deferrals

**Symptom:** the app resolves the SMTP host, completes AUTH, and submits cleanly; numerous `DEFERRED` events appear for one recipient domain.

**Investigation:** inspect provider queues/remote MX behavior, SMTP 4xx replies, per-domain throttling, and recipient MX DNS if warranted. Never mint new messages while the provider is already retrying delivery. This is a **downstream issue**, not the submission endpoint DNS your app connects to.

### Case 8 — Lost response after DATA during a network glitch

**Symptom:** a worker hits `IOException` after transmitting the body; the outbox is not marked `SUBMITTED`.

**Investigation:** identify the SMTP phase, check relay logs/provider IDs if available, keep `SUBMISSION_UNKNOWN`, and avoid bulk replay. Update to `ACCEPTED` if provider evidence confirms acceptance; if irreconcilable, follow an audited risk-based resend process.

## 17. Practicing runbooks in isolated environments

Runbooks should not wait until production breaks. Rehearse with a test fake SMTP/relay and controlled network/DNS faults.

| ID | Drill scenario | What to prove |
| --- | --- | --- |
| R01 | Wrong or revoked credential | AUTH failure classified, lane paused, no retry storm |
| R02 | New secret updated on only some pods | Version drift detected; rotation completes cleanly |
| R03 | Expired OAuth2 token | Proactive refresh before expiry; no per-email token storms |
| R04 | SMTP requires STARTTLS but omits capability | Client fails closed; never sends plaintext |
| R05 | TLS certificate wrong hostname | Hostname verification rejects connection |
| R06 | Certificate chain missing intermediate | Java trust validation fails; safe remediation path verified |
| R07 | SMTP 465/587 mode misconfigured | Transport mode mismatch classified accurately |
| R08 | SMTP endpoint DNS NXDOMAIN | Workers do not suppress recipients; outbox holds safely |
| R09 | DNS SERVFAIL/timeout | Backoff and scoped resolver diagnostics work |
| R10 | `A`/`AAAA` returns unroutable IP | Distinguishes DNS resolved from TCP unreachable |
| R11 | CNAME alias lacks matching SAN | TLS hostname verification remains enabled |
| R12 | Recipient MX fails post-submission | Tracks provider deferrals/bounces; never auto-resends |
| R13 | Wrong DKIM selector DNS | Does not misreport submission failure; investigates downstream auth |
| R14 | Large outbox backlog after recovery | Rate-limited drain; valid urgent mail prioritized |
| R15 | Worker restart mid-incident | Status/`nextAttemptAt` survive restarts |
| R16 | Lost final reply after `DATA` | No blind retry; `unknown` state recorded |
| R17 | Hammered `testConnection()` | Health probe bounded; no auth storm |
| R18 | Logging during AUTH/TLS failures | Zero leaked secrets, tokens, bodies, or recipient PII |

Drills must use fake servers or fault injection inside test environments—never provoke bulk rejections against production providers. If tests rely on units/mocks, state their scope clearly; a mocked `MailAuthenticationException` does not prove real TLS handshakes or provider AUTH protocols work.

### Post-drill recovery checks

Once fault injection is turned off, verify:

1. Canaries succeed across the proper route.
2. Outbox messages remain intact with valid statuses.
3. No zero-delay retry loops exist.
4. No secrets leaked into debug logs.
5. Concurrency slots and SMTP sockets are released on failure.
6. Old secrets/certs/DNS records are cleaned up per plan.
7. Metrics and alerts transition cleanly from failure to recovered.

Never treat a single short test without `MailException` as complete proof; verify subsequent email processing and backlog drain rate.

## 18. Quick action cheat sheet for on-call operators

When a new alert fires, consult this table to avoid editing the wrong component.

| Alert/symptom | Check immediately | Do NOT do | Recovery state to see |
| --- | --- | --- | --- |
| `AUTH 535` spike | Secret version, account status, AUTH mechanism, last rotation | Unbounded per-email retries, printing secrets | Canary AUTH/submission passes; fleet uses valid secret |
| `STARTTLS required` | Host/port, EHLO capabilities, proxy, TLS mode | Disabling required STARTTLS | Verified TLS negotiation, secure AUTH |
| `PKIX path building failed` | Server cert chain, Java truststore, CA rotation | `trust-all` or disabling checks | Valid Java TLS handshake and hostname verification |
| Certificate hostname mismatch | SAN, hostname, SNI, DNS alias, load balancer | Connecting by IP and skipping validation | Certificate hostname matches configuration |
| TLS protocol mismatch | JDK security policy, relay TLS versions | Arbitrarily enabling weak ciphers | Client/server negotiate approved TLS |
| SMTP host `NXDOMAIN` | Effective `spring.mail.host`, DNS resolver, `A`/`AAAA` | Editing recipient MX instead of relay host | Workload resolves name, then TCP/TLS/AUTH pass |
| DNS timeout/SERVFAIL | DNS service, firewall to resolver, CoreDNS, network | Labeling it "invalid recipient" | Stable DNS resolution, falling error rate |
| TCP connect refused | SMTP listener, port, egress policy | Raising read timeouts infinitely | TCP connects to intended endpoint |
| Submit OK yet bounces spike | Provider events, SPF/DKIM/DMARC, recipient quality | Rotating secret when AUTH works | Downstream root cause fixed; new cohorts improve |
| Provider deferrals rising | Receiving MX, SMTP 4xx, provider queue, rates | Resending every deferred event | Provider queue/retries normalize; outcomes tracked |
| Backlog spike post-outage | Outbox age, limiters, workers, provider health | Dumping entire queue unthrottled | Backlog drains smoothly within quota; no duplicate spike |

### Short incident ticket template

~~~text
Incident ID:
Started at / timezone:
Environment / cluster:
Affected notification categories:
SMTP provider/account key:
SMTP host/port/TLS mode (no secrets):
First observed failure category:
SMTP reply / enhanced code / phase (sanitized):
Affected instances / regions:
Current outbox pending + oldest age:
Recent deploy / DNS / certificate / secret changes:
Mitigation taken:
Canary result:
Risk of SUBMISSION_UNKNOWN:
Recovery metrics:
Remaining blockers:
Owner / next update:
~~~

This template requires neither full recipient emails nor passwords. If personal data is needed for investigation, reference an internal record ID through an access-controlled tool.

## 19. Roles and communication during incidents

SMTP failures often span teams. Without clear ownership, uncoordinated edits prolong outages.

| Role | Suggested responsibilities |
| --- | --- |
| Incident commander/on-call | Scoping, severity calls, coordinating changes, status updates |
| Application/mail worker owner | Outbox, retries, `JavaMailSender` config, app bugs, SLA protection |
| Platform/network | DNS resolvers, firewalls, routes, egress proxies, Kubernetes networking |
| Security/secret owner | SMTP credentials, OAuth2, certificate trust, emergency revocation |
| SMTP/provider admin | SMTP endpoints, account/`From` rights, quotas, relay queues, provider incidents |
| Domain/DNS owner | SPF/DKIM/DMARC, MX, records/TTLs, DNS updates and rollbacks |
| Business/product owner | Email prioritization, expired content decisions, user comms |

Small organizations may assign multiple roles to one person. What matters is that **the runbook explicitly documents owners, data sources, and approval rights** for sensitive actions like revoking secrets, changing SPF/DMARC, enabling provider failover, or pausing entire mail lanes.

### Communicating while root cause is still under investigation

Instead of saying "SMTP is down," report verifiable status:

> Since 09:20 UTC, workers in Region A have seen elevated SMTP AUTH failures following a credential rotation. The transactional outbox remains intact; the affected account lane is paused to avoid a retry storm. We are verifying secret versions across instances and running a canary against the new credential.

Once TLS or DNS is confirmed, update the message with concrete evidence. Never promise recovery ETAs or report emails "delivered" when telemetry only confirms submission acceptance.

## 20. Change control and rollback

During incident response, every edit should carry a hypothesis and verification plan. Examples:

| Change | Verify beforehand | Rollback risk |
| --- | --- | --- |
| Rotate SMTP secret | New credential validity, send permissions, all workloads inventoried | Old credential may already be revoked |
| Change `spring.mail.host` | Endpoint DNS, TLS hostname, account region/quota | Old endpoint may no longer be live |
| Change port/TLS mode | Provider supports exact mode and certificate | Misconfiguration can send AUTH unencrypted |
| Update Java truststore | Approved CA chain, impact on other services | Old truststore may lack the new CA |
| Update DNS A/CNAME | Target endpoint, TTL, SNI, network route | Caches stay inconsistent; rollback is not instant |
| Update SPF/DKIM/DMARC | Real source identities, alignment, desired policy strictness | Old records may trigger rejections or weaken policy |
| Increase retries/concurrency | Provider quota and failure root cause | Can trigger a send storm |
| Fail over to backup provider | `From` identity, quota, auth, suppression sync | Unknown/duplicate messages across reroutes |

### Change one variable at a time when possible

Changing the DNS hostname, password, and TLS truststore simultaneously makes it nearly impossible to tell what fixed the issue—or caused a new one. Major incidents sometimes demand multiple fixes, yet each should have:

1. An explicit hypothesis.
2. An assigned owner/approver.
3. A redacted configuration snapshot.
4. A post-change canary.
5. Before/after telemetry.
6. A realistic rollback or roll-forward plan.

Especially with revoked secrets, **rolling forward** to a fresh credential is the right move rather than trying to revert to an invalidated one.

## 21. Post-incident review

After the mail lane stabilizes, examine both root cause and recurrence prevention.

### Review questions

- Did alerts catch the issue before customers reported it?
- Did we isolate DNS/TCP/TLS/AUTH within the first few minutes?
- Did logs and metrics expose correlation, SMTP phase, and category without leaking secrets?
- Were DNS, JDK, TLS certs, SMTP accounts, or OAuth2 policies changed recently?
- Do rotation workflows and expiry monitors catch expirations ahead of time?
- Did staging tests simulate this failure class?
- Did the outbox preserve send intents cleanly throughout the outage?
- Did any duplicates occur from unknown outcomes or layered retries?
- Did the backlog drain within rate limits?
- Were expired emails or unsubscribed recipients prevented from sending post-recovery?
- Which runbooks, alert thresholds, owners, or canary checks need updates?

### Desired outputs

- Timeline of incident and changes.
- Impact broken down by category, provider, and region.
- Proven root cause (or explicit gaps in available evidence).
- Mitigations applied, including effectiveness and limits.
- Action items with owners and due dates.
- New isolated tests reproducing the failure mode.
- Updated secret/certificate/DNS change procedures where needed.

Never close a review with "email works again" without accounting for pending, unknown, bounced, or expired messages.

## 22. Self-check questions

**1. When `UnknownHostException` occurs for the SMTP hostname, should you immediately edit recipient MX records?**

No. That is a resolution error for the endpoint your app connects to. Check `spring.mail.host`, resolvers, and `A`/`AAAA`/`CNAME` for the SMTP relay first.

**2. Why does a successful `Test-NetConnection` not prove SMTP works?**

It mainly verifies TCP reachability. SMTP greeting, STARTTLS, TLS certificates, AUTH, sender permissions, and `DATA` are separate stages.

**3. Does SMTP 535 always mean the password expired?**

No. It could be wrong credentials, a revoked app password, a locked account, bad OAuth2 grants/scopes, or an incompatible AUTH mechanism. Check provider replies and change history.

**4. Should you retry every email aggressively during a broad AUTH 535 outage?**

No. Account-wide auth failures cause authentication storms. Pause the provider lane, keep intents in the outbox, and fix credentials/permissions first.

**5. Does updating a secret in a vault automatically update a running `JavaMailSenderImpl`?**

Not by default. You need a restart, a verified refresh mechanism, or safe atomic sender replacement.

**6. How do STARTTLS and implicit TLS differ?**

STARTTLS starts in plaintext SMTP and upgrades to TLS after `EHLO`; implicit TLS establishes TLS right after TCP connect before the SMTP greeting.

**7. Why must `mail.smtp.ssl.trust=*` not be used in production?**

It weakens certificate verification and allows connecting to untrusted endpoints; fix the CA chain or truststore properly instead.

**8. What should you inspect when OpenSSL connects cleanly yet Java reports PKIX errors?**

The Java truststore, JDK version, CA/intermediate chain, and the actual network/SNI path the JVM hits. OpenSSL and Java may rely on different trust anchors.

**9. How should a certificate hostname mismatch be fixed?**

Ensure the hostname used by the client is covered by the certificate's SAN and hits the right endpoint/SNI. Never disable hostname verification.

**10. Should you fix TLS errors by switching from port 587 to port 25?**

Not arbitrarily. Check supported provider modes and security policy. Switching ports blindly can break routing or downgrade TLS.

**11. Are NXDOMAIN and SERVFAIL the same thing?**

No. NXDOMAIN says the domain name does not exist in the resolver's view; SERVFAIL means the resolver/authoritative lookup failed to process the query. Each requires different debugging.

**12. Why might one pod fail DNS while another succeeds?**

Different resolvers, nodes, cache TTLs, split-horizon views, regions, network policies, or DNS update timing.

**13. What do SPF/DKIM/DMARC fix?**

They govern sender domain authentication and downstream mail-acceptance policies; they do not fix DNS lookups for your SMTP relay hostname.

**14. If SMTP `send()` succeeds, can you conclude the email reached the Inbox?**

No. It only indicates the relay accepted the submission. Mailbox delivery depends on downstream signals.

**15. When a provider reports DEFERRED, should the app immediately send a new email?**

Usually not if the provider already accepted the submission and is retrying on its side. Respect the responsibility boundary to avoid duplicates.

**16. What state should be recorded when the final reply after DATA is lost?**

Typically `SUBMISSION_UNKNOWN` when you cannot confirm relay acceptance; reconcile or apply a duplicate-risk policy before retrying.

**17. Do the three SMTP timeouts enforce a single total deadline for `send()`?**

Not necessarily. They bound individual socket operations across multiple SMTP commands; enforce an overall deadline at the worker layer when needed.

**18. Why avoid calling `testConnection()` inside every readiness probe?**

Hundreds of pods probing constantly can trigger connection/auth storms during degradation, and an SMTP outage can pull the entire web tier offline even when non-mail features work.

**19. If an SMTP credential leaks, can revocation wait until off-peak hours?**

There is no one-size rule, yet this is a security incident: assess exposure, follow emergency revocation workflows, and protect traffic via outbox and a new credential. Never prioritize uptime by keeping an actively compromised secret.

**20. Post-fix, is seeing AUTH failures drop enough to close the incident?**

No. Verify with a canary, check TLS/DNS, watch backlog age, process unexpired mail, reconcile unknowns, and confirm delivery against SLAs.

## Conclusion

**Runbooks for authentication, TLS, and DNS failures in Spring Framework Mail must begin by pinpointing the exact layer: SMTP endpoint DNS, TCP, TLS/certificates, SMTP AUTH, sender policy, or downstream delivery.** Operators need a quick triage table, evidence from the affected workload, safe DNS/TLS inspection commands, secret metadata, and visibility into SMTP phases. When credentials fail or TLS breaks, pause the sending lane and hold the outbox—never weaken security just to "keep mail flowing." When DNS breaks, separate resolvers, `A`/`AAAA`, recipient MX, and SPF/DKIM/DMARC so you fix the right record. Verify every recovery via canaries, metrics, job states, and backlog drain; keep retries rate-limited and handle post-DATA unknown outcomes cautiously. **An effective runbook fixes today's outage while cutting triage time, preventing duplicates, protecting recipient data, and stopping repeat incidents.**
