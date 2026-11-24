# Secret Rotation and Handling Expired Secrets in Spring Framework Mail

Applications using Spring Framework Mail usually need authentication credentials to log into an SMTP relay: a username/password, app password, service-specific credential, or OAuth2/XOAUTH2 access token. These values are **secrets**. Secrets can be exposed, revoked, expire, or require periodic replacement under security policy. If an application configures a password once at deployment with no update workflow, changing credentials can halt all email delivery; if passwords are stored in source code, a single repository leak can lead to abuse of the mail-sending account.

**Secret rotation** is the process of creating or obtaining a new credential, distributing it to the application, shifting traffic to the new credential, verifying operation, and revoking the old credential. This process must balance two goals simultaneously:

1. **Security:** the old credential is no longer usable after revocation; the new credential is never placed into logs, repositories, or responses.
2. **Continuity:** mandatory notifications are not lost, SMTP AUTH failures do not trigger retry storms, and emails already submitted successfully are not resent.

In Spring Mail, JavaMailSender itself does not manage expiration schedules, fetch new secrets from a vault on its own, or swap credentials automatically just because a secret changed in the store. Those responsibilities belong to application configuration, the secrets management system, and operational procedures.

## 1. Which secrets are involved in SMTP?

A system may involve multiple kinds of credentials, each with a different lifecycle:

| Type | Example | What needs rotation |
| --- | --- | --- |
| SMTP password | Username and password for SMTP AUTH | Change password, update sender, revoke old password |
| App password | Application-specific password, if supported by provider | Create new app password, deploy, delete old one |
| SMTP API credential | Provider-issued token/secret for SMTP usage | Create new credential per provider mechanism |
| OAuth2 access token | Short-lived token used with SASL XOAUTH2 | Refresh token before expiration, never treat as static password |
| OAuth2 refresh token | Token used to fetch new access tokens, if provided by flow | Protect tightly and replace when revoked/rotated per provider |
| Secret-manager access | Identity or credential to read the vault | Manage read permissions, lifetimes, and lifecycle separately |
| TLS private key (if any) | Client certificate in mTLS scenarios | Renew key/certificate via TLS workflow |

This document focuses on SMTP authentication secrets. **TLS certificates, DKIM private keys, and SPF/DMARC are related topics but are not the same as an SMTP password.** Changing an SMTP password does not rotate a DKIM key; changing a DKIM key does not fix SMTP AUTH errors.

### Who owns the credential?

For production systems, use an identity or account dedicated to the application with least-privilege permissions. Never use an employee's personal mailbox password as a long-term credential for a service.

If multiple applications share one credential, rotating it affects all of them simultaneously. Whenever possible, separating credentials by system or workload limits blast radius and clarifies ownership.

### A secret is more than a password string

A secret record may include:

- The authentication value (never logged).
- Username or principal.
- Secret version/credential ID.
- Creation timestamp.
- Expiration timestamp or policy-based rotation schedule.
- Status: active, staged, revoked, expired.
- Permission scope and corresponding account/SMTP endpoint.
- Audit metadata containing no passwords.

Not every provider supplies complete expiration metadata; if `expiresAt` is absent, track an internal rotation schedule rather than assuming the secret never expires.

## 2. Lifecycle of an SMTP secret

A secret can pass through states:

~~~text
PROVISIONED
    |
    v
STAGED (created, not yet used for production)
    |
    v
ACTIVE (currently used by one or more senders)
    |
    v
RETIRING (senders are migrating to the new version)
    |
    v
REVOKED / EXPIRED (must not be reused)
~~~

Actual states depend on the secret manager and provider. Some use version stages like current/previous, while others issue two independent credentials; never assume every provider supports two simultaneously valid passwords.

### Differences between rotation, refresh, and revocation

| Operation | Meaning | Example |
| --- | --- | --- |
| Rotate | Controlled transition from an old credential to a new one | Generating a new SMTP password/app password |
| Refresh | Fetching the current version/value or renewing a short-lived token | Obtaining a new OAuth2 access token |
| Revoke | Invalidating a credential | Disabling an old password |
| Expire | Credential reaches its end-of-life per provider/policy | OAuth2 access token expiring |
| Roll back | Reverting to the previous config/credential before cutover | Possible only if the old credential is still valid |
| Roll forward | Remediating with a newer credential version | Required when the old credential was already revoked |

A revoked secret usually **cannot be used for rollback**, even if the application configuration still holds the old version. Therefore, design the rollback plan before revoking.

## 3. What happens when a secret expires?

An application can run normally for weeks and suddenly start receiving authentication errors. Common scenarios:

- The password was changed at the SMTP provider while Spring configuration still uses the old password.
- An app password was revoked by an administrator.
- The SMTP service account was locked or lost sending permissions.
- An OAuth2 access token expired and was not refreshed.
- A refresh token was revoked, or consent/access permissions changed.
- One pod uses an old secret version while another pod updated.
- The secret manager issued a new version, yet the application still holds the old value inside a bean.

The outcome can be an SMTP authentication failure, such as a 5xx response like **535 Authentication credentials invalid** at some providers. Some relays use temporary 4xx codes to indicate authentication service unavailable, rate limits, or other policies. **Do not infer the cause from a single code alone**: inspect the full SMTP reply, enhanced status code, transport exception, and provider documentation.

### Impact on business flows

| Flow | If SMTP AUTH fails |
| --- | --- |
| OTP/password reset | Users cannot receive codes/links yet; provide appropriate feedback and fallback handling |
| Order confirmation | Never roll back a committed order solely because email failed; keep the request in an outbox |
| Invoices/receipts | Mark unsubmitted, alert, and process once credentials recover |
| Newsletter/marketing | May be deferred, expired, or canceled per policy |
| Background worker | Never retry bad credentials continuously like a transient network error |

**A wrong password is a system-wide authentication issue**, not a per-recipient address error. Never mark thousands of emails as “recipient invalid” when the real cause is an expired SMTP credential.

## 4. Spring Boot Mail configuration flow model

When using the Spring Boot Mail starter and auto-configuration, settings such as host, port, username, and password are typically bound from environment configuration into `MailProperties`, which then configures `JavaMailSenderImpl`.

~~~mermaid
flowchart TD
    A["Secret manager / deployment config"] --> B["Spring Environment / MailProperties"]
    B --> C["JavaMailSenderImpl"]
    C --> D["Jakarta Mail Session / SMTP Transport"]
    D --> E["SMTP AUTH"]
    E --> F["SMTP relay"]
~~~

Example configuration containing no specific secret:

~~~yaml
spring:
  mail:
    host: smtp.example.com
    port: 587
    username: smtp-application-user
    default-encoding: UTF-8
    properties:
      "[mail.smtp.auth]": "true"
      "[mail.smtp.starttls.enable]": "true"
      "[mail.smtp.starttls.required]": "true"
      "[mail.smtp.ssl.checkserveridentity]": "true"
      "[mail.smtp.connectiontimeout]": "5000"
      "[mail.smtp.timeout]": "10000"
      "[mail.smtp.writetimeout]": "10000"
~~~

In the example, **the password does not live in the config file**. `SPRING_MAIL_PASSWORD` can be supplied as an environment variable injected by the deployment platform from a secret store, or through a configured secret manager/config integration. Spring Boot supports mapping environment variables to `spring.mail.password`.

### No automatic reload guarantee

If the application already booted with a password, merely updating the value in the vault **does not mean the running `JavaMailSenderImpl` changed its password**. In standard setups:

- Properties are bound when the application context is created.
- The `JavaMailSenderImpl` bean continues holding its configured username/password.
- Changing a deployment's environment variables does not alter the environment of an already-running process.
- Updating a mounted secret file does not automatically cause `JavaMailSenderImpl` to rebind.

To adopt a new credential, adopt an explicit strategy: **restart/rolling deployment**, **replacing the bean via a verified refresh mechanism**, or **a credential-aware adapter that reads the new secret and swaps senders safely**. Do not rely on assuming the framework automatically detects every rotation.

### Does Spring Cloud RefreshScope solve this automatically?

If the system uses Spring Cloud with refresh mechanisms, a refreshable bean can be designed. However, correctness depends on property sources, bean scope, proxy call paths, active resources, and how the secret store notifies changes. `RefreshScope` **is not a built-in guarantee** of Spring Boot Mail. Test thoroughly in practice before relying on it as your production rotation mechanism.

## 5. Where should secrets be stored?

Secrets should live in a managed store with clear access control and auditing, such as a vault, cloud secret manager, or deployment platform secret mechanism. The application needs read access only to its own secret.

### What to do

- Store SMTP credentials outside repositories and image/container artifacts.
- Grant read permissions by service identity, environment, and tenant if needed.
- Use secret versions or revisions to know which version the application runs.
- Separate staging secrets from production secrets.
- Encrypt data at rest/in transit using platform mechanisms.
- Audit secret access and permission changes.
- Never pass credentials in URL queries, command lines, or HTTP responses.
- Restrict who can view/rotate/revoke credentials.

### What not to do

~~~yaml
# NOT RECOMMENDED: real password in repository
spring:
  mail:
    username: team-mailbox@example.com
    password: "hardcoded-real-secret"
~~~

Do not commit a file containing secrets to Git and merely add `.gitignore` afterward. Once committed, deleting it in a newer commit does not remove it from Git history. When a credential leaks, **rotate/revoke** it and handle history/artifacts per policy instead of treating “delete the config line” as sufficient remediation.

### Are environment variables completely safe?

Environment variables are convenient for container config, yet they are not a complete security vault. Users with process/container access, crash dumps, or certain diagnostic tools can read their values. Secrets still need to be supplied through a trusted deployment channel with clear permissions and auditing.

### Files mounted from a secret store

An orchestration platform can project secrets as mounted files. When using this approach:

- Only the required service account can read them.
- Files are never served by a web server or backed up to unsuitable locations.
- File updates avoid letting the application read half-written data.
- The application knows when the file changes and proactively updates the sender.
- Old secrets may still linger in process memory after the file changes.

Updating a mounted file does not mean the SMTP sender uses the new credential. A **controlled reload or restart** step is still required.

## 6. Zero-downtime rotation when the provider supports two credentials

The preferred strategy is **overlapping credentials**: both the old and new credentials remain valid during a transition window.

~~~text
Time ────────────────────────────────────────────────────>

Credential A:  [ ACTIVE ][ DRAINING ][ REVOKED ]
Credential B:             [ STAGED ][ ACTIVE -----------]
                         |         |
                         |         +-- Revoke A after confirmation
                         +------------ Create and verify B
~~~

### Detailed procedure

1. **Build an inventory:** identify all workloads, instances, SMTP accounts, environments, and jobs using credential A.
2. **Confirm provider supports overlap:** such as two app passwords, two SMTP credentials, or two service accounts with equivalent sending permissions.
3. **Create credential B:** grant least-privilege permissions and store the secret in the secret manager.
4. **Staging:** store version B as unused by production or designated for canary.
5. **Test B:** verify connectivity, TLS, sending permissions, permitted From addresses, and a canary email in an authorized environment.
6. **Deploy B:** rolling restart or sender hot-swap, recording which instances switched versions.
7. **Monitor:** watch SMTP AUTH failures, rates, queue age, and submission success.
8. **Confirm A is no longer used:** eliminate old instances and un-cutover workers/jobs; leave no consumer behind.
9. **Revoke A:** invalidate the old credential at the provider.
10. **Post-check:** confirm no pod still uses A; audit the rotation and send health.

### Why is an overlap window needed?

During a rolling deployment, some pods still run A while other pods already use B. If A is revoked immediately after creating B, pods not yet rolled out will suffer SMTP AUTH failures. The overlap window enables migration without halting everything.

The overlap window must cover rollout duration and active connections, yet not stay open indefinitely because the old credential represents residual risk. Exact durations depend on infrastructure and policy.

### Limitation to remember

**Not every SMTP provider allows two passwords to be active simultaneously on one account.** If changing a password immediately invalidates the old password, you cannot apply the overlap workflow verbatim. You may need a second service account, a dedicated SMTP credential, or a scheduled cutover with a brief pause.

## 7. Rotation when the provider allows only one credential

Some systems replace the current password in a way that immediately cancels the old one. In that situation, true zero downtime across multiple replicas is difficult.

A practical procedure:

1. Pick a low-impact cutover window and notify stakeholders.
2. Ensure an outbox durably holds transactional emails.
3. Pause or throttle dispatch just before the swap to avoid errors and retries.
4. Change the password at the provider and save it in the secret manager.
5. Update all instances via rolling restart or sender swap.
6. Test authentication/connectivity with the new credential; resume dispatch only once it succeeds.
7. Drain the backlog through a rate limiter without bursting everything at once.
8. Monitor SMTP AUTH, retries, and backlog after cutover.

If the application can maintain two accounts with valid From permissions, you can achieve overlap at the **two-account** level instead of two passwords on one account. However, verify sender policies, SMTP AUTH identities, quotas, and relay permissions; never assume a new credential automatically has permission to send from every From address.

### Limitations of rollback

Once the old password is invalidated, rolling back to an image/deployment containing the old password will continue failing. A practical recovery approach is **roll forward**: issue a valid credential, update the secret store, and redeploy. Do not write a runbook saying “roll back to credential A” if A has already been revoked.

## 8. Verifying the new credential before cutover

A credential existing in the secret manager is not guaranteed to send emails successfully. Verify each layer:

| Step | What is confirmed | What is NOT yet proven |
| --- | --- | --- |
| Read secret | Workload has permission to fetch the right version | SMTP accepts the credential |
| TLS connection | Secure connection can be established | Username/password are right |
| SMTP AUTH | Server accepts authentication | Permission to send from the desired From address |
| Canary SMTP submission | Relay accepts a test message | Message reached every recipient's inbox |
| Delivery/bounce event | Provider continues processing/delivering mail | Every future email will definitely succeed |

`JavaMailSenderImpl.testConnection()` can help verify connectivity to the mail server, including authentication when configured. However, this test does not prove quotas, sender permissions, or deliverability. To verify end-to-end, send a **canary email** to an authorized test mailbox and observe the outcome through the provider/test environment.

### TLS must be right before evaluating passwords

If SMTP requires STARTTLS, enable and require STARTTLS instead of automatically downgrading to an insecure connection. Example for port 587:

~~~properties
spring.mail.properties[mail.smtp.auth]=true
spring.mail.properties[mail.smtp.starttls.enable]=true
spring.mail.properties[mail.smtp.starttls.required]=true
spring.mail.properties[mail.smtp.ssl.checkserveridentity]=true
spring.mail.properties[mail.smtp.connectiontimeout]=5000
spring.mail.properties[mail.smtp.timeout]=10000
spring.mail.properties[mail.smtp.writetimeout]=10000
~~~

If the provider requires implicit TLS on port 465, configuration must match that mechanism; do not blindly copy STARTTLS/port settings from the 587 example. A new secret cannot fix a wrong TLS mode, certificate validation error, or network policy block.

### Run canaries only on authorized infrastructure

Never send test mail to real users in bulk during rotation. Canaries must use admin-approved recipients and senders containing no sensitive production data. Rate-limit canaries and avoid infinite loops if AUTH is failing.

## 9. Strategies for updating JavaMailSender in a running application

Three common deployment approaches exist, with no single one fitting every scale:

| Approach | How it works | Strengths | Considerations |
| --- | --- | --- | --- |
| Rolling restart | Update secret then restart pods/instances in batches | Easy to observe and reduces dynamic state | Needs overlap or dispatch pause if old credential is revoked immediately |
| Managed refresh | Official refresh mechanism recreates beans with the new secret | Does not necessarily restart the entire process | Must test bean scope, proxies, in-flight senders, and refresh failures |
| Sender hot-swap | Build new sender, test it, then atomically swap reference | Fast switch within the same process | Requires custom code, in-flight management, and no bypass paths |

For simpler systems, an **orchestrated rolling restart with an outbox** is usually easier to operate than custom reload machinery. Hot-swapping helps when rotation frequency is high or restarts are costly, yet it requires tight design.

### Never mutate a shared JavaMailSenderImpl across threads

Suppose dozens of workers share one `JavaMailSenderImpl` bean. If one thread calls `setUsername` or `setPassword` while another thread is inside `send()`, threads may observe an inconsistent configuration—such as the new username paired with the old password, or vice versa.

Avoid doing this:

~~~java
// Do not mutate credentials of a sender used concurrently by multiple threads.
sharedSender.setUsername(newUsername);
sharedSender.setPassword(newPassword);
~~~

These two calls do not form an atomic username/password update. Instead, construct **a complete sender** for the new credential, verify connectivity, and swap the adapter's reference.

### Illustrative hot-swap adapter

The example below shows snapshotting the sender per send. `SmtpSecret` is data returned by an internal secret provider; the code does not rely on Spring Boot's auto-config constructor:

~~~java
package com.example.mail;

import jakarta.mail.MessagingException;
import java.util.Properties;
import java.util.Objects;
import java.util.concurrent.atomic.AtomicReference;
import org.springframework.mail.javamail.JavaMailSenderImpl;
import org.springframework.mail.javamail.MimeMessagePreparator;

public final class RotatingSmtpGateway {

    private final AtomicReference<JavaMailSenderImpl> active;
    private final String host;
    private final int port;

    public RotatingSmtpGateway(
            String host, int port, SmtpSecret initialSecret)
            throws MessagingException {

        this.host = Objects.requireNonNull(host);
        this.port = port;
        JavaMailSenderImpl initial = createSender(initialSecret);
        initial.testConnection();
        active = new AtomicReference<>(initial);
    }

    public void send(MimeMessagePreparator preparator) {
        JavaMailSenderImpl snapshot = active.get();
        snapshot.send(preparator);
    }

    public void rotateTo(SmtpSecret next) throws MessagingException {
        JavaMailSenderImpl candidate = createSender(next);

        // If auth/TLS fails, keep the previous sender.
        candidate.testConnection();

        // All sends started after this operation receive the new sender.
        active.set(candidate);
    }

    private JavaMailSenderImpl createSender(SmtpSecret secret) {
        JavaMailSenderImpl sender = new JavaMailSenderImpl();
        sender.setHost(host);
        sender.setPort(port);
        sender.setProtocol("smtp");
        sender.setDefaultEncoding("UTF-8");
        sender.setUsername(secret.username());
        sender.setPassword(secret.password());

        Properties properties = new Properties();
        properties.put("mail.smtp.auth", "true");
        properties.put("mail.smtp.starttls.enable", "true");
        properties.put("mail.smtp.starttls.required", "true");
        properties.put("mail.smtp.ssl.checkserveridentity", "true");
        properties.put("mail.smtp.connectiontimeout", "5000");
        properties.put("mail.smtp.timeout", "10000");
        properties.put("mail.smtp.writetimeout", "10000");
        sender.setJavaMailProperties(properties);
        return sender;
    }
}
~~~

A secret data type should not have a `toString` that prints passwords:

~~~java
public final class SmtpSecret {

    private final String username;
    private final String password;
    private final String version;

    public SmtpSecret(
            String username, String password, String version) {
        this.username = Objects.requireNonNull(username);
        this.password = Objects.requireNonNull(password);
        this.version = Objects.requireNonNull(version);
    }

    public String username() { return username; }
    public String password() { return password; }
    public String version() { return version; }

    // Do not auto-generate toString() containing sensitive fields.
}
~~~

**Important note:** This is an architectural illustration, not a complete production secret hot-reload system. It omits vault change listeners, authorization to call `rotateTo`, multi-replica rollback/canary coordination, metrics, and in-flight sender tracking. Secret strings may still linger on the heap until garbage-collected; do not claim swapping an `AtomicReference` immediately wipes the old credential from memory.

### Why is snapshotting the sender beneficial?

Each `send` call captures a single local reference. After replacing `active` with the new sender, sends started afterward use `candidate`. Sends that already snapshotted the old sender continue running with the old credential. If the old credential is revoked before they finish AUTH, those sends may fail.

Therefore, an overlap window or traffic draining/quiescing during cutover is still needed. **`AtomicReference` protects reference swapping; it does not guarantee zero-downtime SMTP rotation** in all scenarios.

### Do not leave two separate send paths

If other services still inject the default `JavaMailSender` while one service uses `RotatingSmtpGateway`, parts of the system may keep sending with the old credential. In a hot-swap design, you must:

- Establish a single SMTP submission gateway.
- Ensure all notifications go through the updated gateway.
- Audit bean wiring so no unintended bypass routes exist.
- Separate staging/canary senders from production senders.
- Emit metrics tagged with non-sensitive secret versions if policy permits.

If you cannot control every send path, a rolling restart/centralized config update may be more reliable.

## 10. Loading new secrets from a secret manager

A service can read secrets by version, validate them, and update the sender:

~~~java
public interface SmtpSecretProvider {

    SmtpSecret getCurrent();

    SmtpSecret getVersion(String version);
}
~~~

This is an internal contract; it is not a Spring Mail API. An implementation can use a vault, cloud secret manager, or protected mounted file.

### Safe reload steps

~~~text
Secret store publishes a new version
        |
        v
Application receives change event / scheduled refresh
        |
        v
Read version B with workload identity
        |
        v
Validate metadata and configuration
        |
        v
Construct a complete candidate sender
        |
        v
Test TLS + SMTP AUTH (controlled)
        |
        +-- FAILED --> Keep current sender, alert
        |
        +-- PASSED --> Swap active sender reference
                         |
                         v
                Drain old in-flight sends
                         |
                         v
                Revoke old credential per runbook
~~~

Never write the new username/password into logs when reloading fails. If debugging is needed, log the version ID, provider key, stage (read, construct, auth, swap), standardized error code, and correlation ID.

### Distinguishing “secret changed” from “application uses new version”

A secret manager might report current version B while a pod still runs A. Observe separately:

- Secret store current version.
- Sender version actively used by each pod.
- Timestamp when each pod confirmed the new version.
- Count of pods not yet cut over.
- Count of SMTP AUTH failures per pod/provider.

Never log raw credentials or fingerprints easily derived from passwords. A non-sensitive version ID suffices in many systems; if provider-generated version IDs could leak internal metadata, expose them only via access-controlled telemetry.

### Caching and TTL

If the secret provider client caches credentials, define TTLs and invalidation rules. In normal rotation, overly long caching leaves pods on A after B is active; during a credential-exposure incident, caching can delay switching to B.

Depending on implementation, you can:

- Proactively invalidate caches upon receiving rotation events.
- Use periodic refreshes with jitter.
- Check version metadata as expiration nears.
- Reload on AUTH failures signaling credential replacement, while **rate-limiting refreshes** so workers do not hammer the vault simultaneously.

Do not query the secret manager for every individual email unless necessary: a burst of tens of thousands of emails can overwhelm the secret manager. A centralized refresh mechanism with TTL, single-flight, and bounded retries is usually better.

## 11. Handling race conditions during rotation

A multi-instance system can encounter races:

1. Pod A read B; pod B still runs A.
2. Operator revokes A before pod B updates.
3. Worker A sends with the old sender just as the reference swaps.
4. Two refresh events arrive out of order: B then A, causing a downgrade.
5. The secret manager exhibits eventual consistency or staging labels shift mid-read.

### Monotonic versioning principle

Assign a system-managed rotation generation, such as 41 → 42. Each instance accepts promotions only in approved monotonic order. Do not let a late stale callback overwrite a newer sender:

~~~text
Current generation: 42
Incoming event:     41
Action:             Ignore stale update
~~~

If provider version IDs are unordered (such as random UUIDs), do not compare them lexicographically. Use stage/current metadata or a separately managed generation/epoch.

### Single-flight refresh

If 500 workers hit AUTH errors simultaneously, do not let them call the vault and canary 500 times. Use a single coordinator per instance/cluster to perform refreshes while other workers park jobs:

- Only one refresh task runs at a time.
- Duplicate triggers are coalesced.
- Backoff applies if the vault/SMTP is unavailable.
- Invalid candidates never replace an active working sender.
- Timeouts and alerts trigger if a refresh stalls too long.

## 12. OAuth2/XOAUTH2: token expiration differs from password expiration

Some SMTP providers support OAuth2 via SASL XOAUTH2 instead of static passwords. Here, the actual secret in SMTP AUTH is a **short-lived access token**. Token expiration is a normal lifecycle event, not always an incident.

### Components to distinguish

| Component | Lifecycle | Notes |
| --- | --- | --- |
| OAuth2 access token | Short-lived | Must have a valid token when starting SMTP AUTH |
| Refresh token (if any) | Longer-lived, yet revocable | Protect strictly and rotate per provider |
| Client secret/private key | Authenticates client per flow | Manage separately; also requires rotation |
| Workload identity | App identity to token provider | Reduces need for long-lived passwords when supported |
| SMTP account/principal | Email-sending identity | Needs sufficient SMTP permissions/scopes |

OAuth2 flows, scopes, and SMTP permissions depend on the provider. Never assume every SMTP relay accepts XOAUTH2; check provider capabilities and supported auth settings.

### Jakarta Mail property example

~~~properties
mail.smtp.auth=true
mail.smtp.auth.mechanisms=XOAUTH2
mail.smtp.starttls.enable=true
mail.smtp.starttls.required=true
mail.smtp.ssl.checkserveridentity=true
~~~

In some Jakarta Mail integrations, the access token is passed as the password argument in SMTP AUTH XOAUTH2 calls. Verify against your library version and provider. Never put an access token as a static password in `application.yml` expecting the system to refresh it automatically.

### Refreshing before expiry with a buffer

Suppose an access token has `expiresAt`. Do not wait until the exact expiration timestamp to fetch a new token, because:

- Clocks across systems may skew.
- SMTP handshakes take time.
- Token servers have latency.
- A token may expire mid-connection setup.

A policy can fetch a new token whenever remaining lifetime drops below an appropriate **safety margin**. The margin must reflect provider rules, processing latency, and real clock skew; there is no universal value for every system.

### Token refresh failures

If the token endpoint returns transient errors, the application should:

1. Keep the old access token **only while it remains valid**.
2. Refresh with backoff and single-flight, never calling the token endpoint per email.
3. If the token has already expired, halt SMTP submission and preserve the outbox.
4. Distinguish token service unavailability from a revoked refresh token/`invalid_grant`.
5. Alert when recovery exceeds SLA thresholds.

Never fall back to insecure SMTP AUTH or an anonymous relay just because a token could not be fetched.

## 13. Why secret rotation needs an outbox and error-aware retries

When a credential expires, many queued jobs can fail at once. If every job retries immediately with the same old password, the SMTP relay is hit thousands of times uselessly. A durable outbox decouples **retaining send requests** from **calling SMTP right now**.

~~~mermaid
flowchart LR
    A["Email outbox"] --> B["Dispatch gate"]
    B --> C{"Credential usable?"}
    C -- "No" --> D["Pause provider lane / alert"]
    D --> A
    C -- "Yes" --> E["Rate limiter"]
    E --> F["JavaMailSender"]
    F --> G["SMTP relay"]
~~~

Safe behavior when a credential is rejected broadly:

- Record authentication failures at the provider/account level.
- Mark the provider lane as blocked or trip a circuit breaker to OPEN on clear signals.
- Do not escalate per-notification retries.
- Execute refresh/rotation through a dedicated workflow.
- Keep email records in `PENDING`/`RETRY_PENDING` or waiting-for-credential state.
- Resume sending only after the candidate is verified.
- Drain the backlog through a rate limiter and concurrency cap to avoid bursts.

### Is an AUTH failure a permanent email error?

On a login attempt with a bad credential, SMTP may return a 5xx error. Yet this **does not prove the email content or recipient is permanently invalid**. It is usually a system-level config/credential error; do not mark all notifications `FAILED_PERMANENT` and discard send requests.

An additional state model might look like:

~~~text
PENDING
  |
  +-- CREDENTIAL_UNAVAILABLE --> WAITING_FOR_CREDENTIAL
                                    |
                                    v
                          ROTATION_VERIFIED
                                    |
                                    v
                                  PENDING
~~~

This state belongs to the application model, not built-in `JavaMailSender` state. Bound wait times and alert for time-sensitive emails or expiring tokens such as OTPs.

### Do not retry every SMTP error indefinitely

| Error | Action |
| --- | --- |
| AUTH rejected across multiple jobs | Stop provider lane, refresh/rotate, alert |
| AUTH temporarily unavailable at provider | Backoff and assess provider health |
| Connection timeout | Retry with backoff through rate limiter |
| Recipient permanently rejected | Handle per recipient; do not trigger rotation |
| Broken template/MIME | Fix template/data; independent of secrets |
| Unknown SMTP outcome after DATA | Do not blindly retry due to duplicate risk |
| Quota/rate-limit | Throttle rate and retry per policy |

Note: when an AUTH error definitely occurred **before sending DATA**, you generally know that attempt did not submit the message. However, a connection exception after DATA may leave relay acceptance unknown. Adapters must distinguish failure stages whenever transport details allow.

## 14. Retry limits and circuit breakers during secret incidents

Instead of having every job repeatedly test the old password, use a circuit breaker or provider health state:

~~~text
ACTIVE
  |
  +-- AUTH rejected repeatedly --> CREDENTIAL_SUSPECT
                                      |
                                      v
                                DISPATCH_PAUSED
                                      |
                            load/verify new secret
                                      |
                    +-----------------+-----------------+
                    |                                   |
                FAILED                              VERIFIED
                    |                                   |
                stay paused                         RATE_LIMITED_DRAIN
~~~

This is a conceptual state diagram. Transition thresholds should rely on high-confidence authentication failure signals—never trip the breaker on a single 550 recipient error or an isolated DNS hiccup.

### Avoiding credential refresh storms

One failure can trigger simultaneously:

- 200 workers calling SMTP and getting AUTH failures.
- Every worker calling the secret manager.
- Every worker calling `testConnection` with the new credential.
- Both the secret manager and SMTP getting overloaded.

To prevent this:

1. Use one coordinator or single-flight refresh.
2. Add jitter to periodic refreshes across instances.
3. Cap canary/`testConnection` calls per rotation version.
4. Cache secrets by version with explicit TTL and invalidation.
5. When refresh fails, retry at the rotation coordinator level, not per email.
6. Workers simply hold jobs in the outbox rather than looping on SMTP.

### Retries still require idempotency

After a new credential is activated, draining the queue may encounter emails that SMTP had previously accepted before the application recorded `SUBMITTED`. Use notification IDs, states, leases, attempt histories, and reconciliation for uncertain SMTP outcomes; never blindly reset all records to `PENDING` just because the credential changed.

## 15. Tracking expiration before incidents happen

Do not wait until SMTP returns AUTH failures to discover a secret expired. A lifecycle management system should alert **before** expiry and confirm rotation completes.

Metadata to track:

| Attribute | Meaning |
| --- | --- |
| `credentialVersion` | Version currently used by the application |
| `createdAt` | When the credential was created |
| `activatedAt` | When usage began |
| `expiresAt` | Expiration time if provided by provider |
| `rotationDueAt` | Internal policy-driven rotation deadline |
| `lastSuccessfulAuthAt` | Most recent successful SMTP authentication |
| `lastValidatedAt` | Most recent candidate validation |
| `rotationState` | `STAGED`, `ACTIVE`, `RETIRING`, `REVOKED`, etc. |
| `owner/contact` | Team responsible for rotation and incidents |

**Do not use `lastSuccessfulAuthAt` as proof a secret remains valid until a future date**: authenticating today does not guarantee the credential won't be revoked tomorrow. Expiry metadata should also be confirmed with the provider rather than relying solely on app-guessed timestamps.

### Multi-threshold alerting

Set tiered alerts by risk level, for example:

- Policy reminder well ahead of scheduled rotation.
- Early warning when remaining time for staging/canary shrinks.
- Urgent alert if expiry is near and no new version is active.
- Incident when overdue or widespread AUTH failures occur.

Exact windows depend on the organization, system, and secret lifetime. OAuth2 access tokens may live minutes/hours and refresh automatically before expiry; SMTP passwords may rotate on a daily/monthly cadence. Do not apply the same 7-day threshold to every type.

### Helper to check whether refresh is due

~~~java
import java.time.Duration;
import java.time.Instant;
import java.util.Objects;

public final class SecretExpiryPolicy {

    public static boolean refreshDue(
            Instant now,
            Instant expiresAt,
            Duration safetyMargin) {

        Objects.requireNonNull(now);
        Objects.requireNonNull(expiresAt);
        Objects.requireNonNull(safetyMargin);
        if (safetyMargin.isNegative()) {
            throw new IllegalArgumentException("Negative margin");
        }

        return !now.isBefore(expiresAt.minus(safetyMargin));
    }
}
~~~

This function only answers **whether the refresh threshold has been reached**; it does not refresh tokens or rotate SMTP credentials itself. For secrets without `expiresAt`, use `rotationDueAt` or a dedicated policy. In real applications, inject a `Clock` to test boundary timestamps and avoid scattered reliance on the system clock.

### Rotation is a process, not just a timestamp

An alert saying “secret expires in 24 hours” is not enough if the application has not deployed the new version. Dashboards should show:

- Is a valid candidate ready?
- Did the canary pass?
- How many instances run the new version?
- Is any traffic still using the old version?
- Has the old credential been revoked?
- Is there an AUTH failure backlog needing handling?

Rotation is considered finished only once all policy-defined conditions are satisfied.

## 16. Readiness, health checks, and startup behavior

Spring Boot supports an optional SMTP connectivity check at startup, for example:

~~~yaml
spring:
  mail:
    test-connection: true
~~~

In matching environments and Spring Boot versions, this can make the application check mail server connectivity on startup. However, consider carefully:

- If SMTP is temporarily unavailable, all new pods may fail readiness during a rolling deploy.
- A provider outage could inadvertently prevent non-email application features from starting.
- Connect/auth checks do not prove emails will be accepted under sender policies.
- Simultaneous pod startups can send bursts of `testConnection` calls to SMTP.

### Should `testConnection` run inside continuous readiness probes?

Avoid running SMTP AUTH on **every** HTTP readiness probe by default. Consequences can include:

- Increased connection counts and consumed authentication quotas.
- During an SMTP outage, load balancers pull all web pods out of service even while core web features work.
- Extra auth/connection storms while the provider is already degraded.

Instead, separate concerns:

- **Web/application readiness:** can the app handle core business requests within commitments?
- **Mail dispatch health:** can workers submit email?
- **Credential freshness:** is the active secret at the right version and unexpired?
- **Backlog health:** is the mail outbox exceeding SLAs?

A dedicated mail-sender service might treat SMTP readiness as critical; a multi-feature web app might tolerate SMTP downtime while still accepting orders and saving outbox jobs. The decision depends on architecture.

### Balancing fail-fast with resilience

For a dedicated SMTP-sending service, failing fast when authentication fails may make sense since it has no other function. For a producer web app using an outbox, allowing startup without SMTP while marking the mail lane unhealthy may be better. Do not turn one example's choice into a universal rule.

## 17. Handling secret manager unavailability

The secret store itself can experience outages. This differs from the SMTP provider rejecting a credential.

### When a valid credential is already held

If the vault is temporarily unavailable while the sender holds credential A, which is neither expired nor revoked, an application may continue using A per policy while:

- Avoiding reading the secret on every email.
- Retrying background refreshes with backoff/jitter.
- Alerting when metadata or new versions cannot be read.
- Pausing rotation rollout until B is verified.
- Bounding how long cached credentials may continue to be used.

This avoids hard real-time dependency on the vault for every SMTP command. However, if security policy mandates immediate revocation or evidence shows A was leaked, never keep A alive solely for uptime.

### When the credential is already expired/revoked

Never use an invalidated credential or fall back to an anonymous relay just to “keep sending”. Preserve the outbox, report errors, and wait for a valid secret. For OTPs and time-sensitive messages, state may expire before infrastructure recovers; provide appropriate user feedback.

### Vault backoff differs from SMTP backoff

Vault errors should be handled by the **secret refresh coordinator**. SMTP errors should be handled by the **mail dispatch worker**. If an incident breaks both, avoid multiplying requests across two retry loops:

~~~text
Vault unavailable
    |
    v
One bounded secret refresh retry loop
    |
    v
Mail lane temporarily paused
    |
    v
Outbox preserved; no per-email vault fetch loop
~~~

## 18. Incident runbook when an SMTP secret has expired

When consecutive notifications hit SMTP AUTH failures, act in order to minimize impact.

### Step 1 — Confirm scope

Check:

- Is the failure on one pod or all instances?
- One SMTP account or all accounts?
- Did errors begin after a rotation/deployment?
- Does the provider report invalid password, locked account, expired token, or temporary service error?
- Did TLS mode, hostname, sender permissions, or IP allowlists change?
- Which secret version are records using?

Do not jump to “secret expired” from a connection timeout alone. It could be network, DNS, certificates, or a provider outage.

### Step 2 — Prevent error amplification

- Pause the sending lane using the failing credential.
- Keep the outbox in `PENDING`/`RETRY_PENDING`, avoiding retry storms.
- Optionally pause marketing and prioritize recovering transactional mail.
- Never delete failed records or increment attempts endlessly.
- Alert the on-call systems team and credential owners.

### Step 3 — Provision/obtain a valid credential

- Look up the current secret version in the authoritative source.
- If the credential was revoked, issue a new credential per policy.
- Verify account permissions and From addresses.
- Read secrets via an authorized workload identity; never paste passwords into chat or tickets.
- Never retry wrong passwords repeatedly and trigger an account lockout.

### Step 4 — Verify candidate

- Test TLS/connect/auth on a canary worker.
- Send a canary message to an authorized test mailbox if submit permissions must be checked.
- Confirm host, port, and STARTTLS/implicit TLS settings match.
- Log the version ID and verification outcome, never password values.

### Step 5 — Deploy and shift traffic

- Swap senders or perform a planned rolling restart.
- Confirm every pod runs the new version.
- If the old credential is invalid, prevent old pods from continuing dispatch.
- Clean up in-flight connections/senders safely.

### Step 6 — Recover backlog

- Re-open the sending lane **through a rate limiter**.
- Prioritize non-expired, high-priority notifications.
- Never blindly replay `SUBMITTED` or `SUBMISSION_UNKNOWN` records.
- Check suppression/expiry before retrying.
- Watch SMTP successes, failures, oldest pending age, and dead-letters.

### Step 7 — Post-incident review

- Analyze why expiry alerts failed or rollout lagged.
- Update rotation schedules, thresholds, runbooks, and owners.
- Audit rotation actions, versions, and revocation timestamps.
- If recipients were impacted, handle communication per organizational policy.

### Incident workflow diagram

~~~mermaid
flowchart TD
    A["AUTH failures spike"] --> B{"Credential actually invalid?"}
    B -- "No / unclear" --> C["Investigate TLS, provider, network"]
    B -- "Yes" --> D["Pause affected mail lane"]
    D --> E["Get/create valid secret"]
    E --> F["Test TLS + AUTH + canary"]
    F --> G{"Candidate valid?"}
    G -- "No" --> H["Keep outbox, alert, investigate"]
    G -- "Yes" --> I["Deploy or swap sender"]
    I --> J["Verify fleet version"]
    J --> K["Drain backlog with limiter"]
    K --> L["Audit and post-incident review"]
~~~

## 19. Responding when a secret is exposed

Scheduled rotation and **credential compromise** response are not identical. If a password leaks in a repository, log, ticket, screenshot, or compromised host, keeping the old credential active during a long overlap window increases abuse risk.

An incident workflow may include:

1. Isolate the affected SMTP account/secret.
2. Restrict or revoke the exposed credential based on urgency and service-continuity plans.
3. Provision a new credential and update the appropriate application/service account.
4. Inspect provider audits/logs for unauthorized sending activity.
5. Audit access permissions to vaults, CI/CD, repositories, and logs where the secret might persist.
6. Handle copies in history, artifacts, or backups per policy; never claim every distributed copy can be erased.
7. Assess incident reporting obligations and recipient support per organizational/legal requirements.
8. Strengthen guardrails to prevent recurrence, such as secret scanning and debug log controls.

If a secret is actively being exploited, revocation priority may outweigh zero-downtime. An outbox preserves send requests while the SMTP path recovers with a new credential.

### Keep secrets out of logs and exceptions

Be careful with:

- `application.yml` or `application.properties` printed during debugging.
- Startup dumps listing the entire Spring Environment.
- HTTP actuator endpoints exposing config details if poorly secured.
- Mail protocol debug and SMTP traces.
- Exceptions containing URLs/parameters with credentials.
- Custom `toString` on credential objects.
- CI pipelines printing environment variables.
- Tracing baggage, APM breadcrumbs, or support bundles.

`mail.debug` or protocol logging helps diagnose issues, yet should never be left on broadly in production. When needed, use controlled environments, masking, short durations, and review recorded data. Never assume every library automatically masks all AUTH strings or tokens in every configuration.

### Secrets in memory

Java `String` objects are immutable and may remain on the heap after changing passwords. Do not claim you can completely wipe every secret copy held by `JavaMailSenderImpl`/Jakarta Mail. Reduce lifetimes by swapping senders, dropping old references, avoiding infinite caches, and restricting heap dump access. For very high security requirements, consider shorter-lived worker processes and platform-managed short-lived identities.

## 20. Rollback and roll-forward for SMTP rotation

A decision table to avoid blind rollbacks:

| Scenario | Choice |
| --- | --- |
| Candidate B fails, A still valid | Keep A, do not promote B; fix and retry |
| B active, A not revoked yet, B hits errors | Controlled rollback to A if safe and permitted |
| B active, A already revoked | Do not roll back to A; roll forward with fixed B or credential C |
| A was exposed | Do not keep A just to restore service; prioritize revoking per incident policy |
| Provider allows only one password | Plan cutover/rollback around ability to reissue passwords |
| OAuth2 token expired | Refresh token/new access token; never “roll back” to expired token |

### Do not lose data during rollback

With an outbox, unsubmitted messages remain preserved. Still, distinguish:

- `SUBMITTED`: already accepted by the SMTP relay; never retry arbitrarily.
- `RETRY_PENDING`: hit a temporary error and scheduled for retry.
- `WAITING_FOR_CREDENTIAL`: unsent because the mail lane is paused.
- `SUBMISSION_UNKNOWN`: uncertain whether the relay accepted it.
- `EXPIRED`/`SUPPRESSED`: no longer permitted to send per policy.

Never reset all states to `PENDING` simply because credentials switched. Doing so creates duplicates and may send expired marketing emails or stale OTPs.

### When to revoke the old credential?

In normal overlapping rotation, revoke only after:

1. The new candidate passes authentication/canary checks.
2. All instances/consumers have cut over.
3. No in-flight requests still require A per policy.
4. Metrics show zero remaining traffic using A.
5. A roll-forward plan is ready in case B fails.

During a compromise incident, earlier revocation may be necessary. Runbooks must clearly distinguish **scheduled rotation** from **emergency revocation**.

## 21. Testing secret rotation before deployment

Do not test only the happy path with a static password. A rotation-capable system needs tests **before, during, and after** secret swaps.

| ID | Scenario | Outcome to prove |
| --- | --- | --- |
| R01 | Valid credential A | Sends via A per initial config |
| R02 | Create valid credential B | B passes AUTH/canary before promotion |
| R03 | Candidate B has wrong password | Active sender unchanged; A keeps working if still valid |
| R04 | Swap A → B succeeds | New sends use B |
| R05 | A has in-flight sends during swap | No mixed new-username/old-password config; in-flight errors handled per policy |
| R06 | Revoke A after B is active | No pod initiates SMTP AUTH with A |
| R07 | One replica misses the event | Version drift detected and A is not revoked prematurely |
| R08 | Refresh event B arrives before stale event A | Does not downgrade from B back to A |
| R09 | Secret manager temporarily unavailable | No per-email fetch loop; outbox intact |
| R10 | Secret expires during large backlog | Mail lane pauses; no retry storm |
| R11 | Credential restored | Backlog drains via rate/concurrency limiter |
| R12 | App restarts after secret change | Fetches current version; does not use stale cached version forever |
| R13 | OAuth2 access token nearing expiry | Token refreshes before safety margin |
| R14 | Refresh token revoked | Does not retry login endlessly; records actionable error |
| R15 | SMTP provider lacks overlap support | Scheduled/paused cutover; does not assume two live passwords |
| R16 | Credential exposed | Revoke/roll-forward incident branch executes |
| R17 | SMTP accepts message but outbox update fails | Does not blindly retry records with uncertain outcomes |
| R18 | Logging enabled in tests | No raw password/access token leaks into logs/traces |

### Building a fake SMTP relay with two credential versions

For integration tests, an SMTP fake can enforce phases:

~~~text
Phase 1: accept credential A, reject B
Phase 2: accept A and B
Phase 3: accept B, reject A
Phase 4: temporarily reject all AUTH
Phase 5: recover and accept B
~~~

The application runs rotation A → B in phase 2, verifies all new senders use B, then switches the fake to phase 3. This scenario verifies overlap handling and detection of stale pods.

If the application runs multiple replicas, test with at least two workers and a coordinator/secret-store fake. Do not conclude a distributed system is safe from a single-bean unit test in one JVM.

### Testing a failing new credential

An essential criterion: if candidate B fails authentication, the gateway **must not replace active sender A**.

Pseudocode:

~~~text
activeSecretVersion = "A"
candidate = "B"  // B invalid

rotateTo(B) -> authentication failure
assert activeSecretVersion == "A"
assert no raw secret appeared in logs

if A is still valid:
    next send uses A
else:
    keep pending; alert for recovery
~~~

For adapters with `AtomicReference`, inject a `SenderFactory` and `CredentialProbe` in unit tests to verify swapping without opening sockets. Real tests against an SMTP fake are still needed to validate AUTH and transport settings.

### Testing concurrent updates

Have multiple threads continuously call `send` during rotation:

- Each send uses a complete sender snapshot.
- Never observe username B combined with password A.
- In-flight sends with A behave according to overlap policy.
- Sends started after B is promoted use B.
- Invalid candidates never overwrite the active reference.

Concurrency tests need latches/barriers and enough iterations to create contention; do not just call two methods sequentially and declare thread safety.

## 22. Unit testing expiration policy with a fixed clock

Separate rotation/expiry logic from schedulers so it can be tested without waiting in real time.

For `SecretExpiryPolicy.refreshDue` shown earlier, you can test:

~~~java
import static org.junit.jupiter.api.Assertions.*;
import java.time.Duration;
import java.time.Instant;
import org.junit.jupiter.api.Test;

class SecretExpiryPolicyTest {

    @Test
    void refreshBeginsAtSafetyMargin() {
        Instant expiry = Instant.parse(
                "2030-06-01T12:00:00Z");
        Duration margin = Duration.ofMinutes(5);

        assertFalse(SecretExpiryPolicy.refreshDue(
                expiry.minus(Duration.ofMinutes(6)),
                expiry,
                margin));

        assertTrue(SecretExpiryPolicy.refreshDue(
                expiry.minus(Duration.ofMinutes(5)),
                expiry,
                margin));

        assertTrue(SecretExpiryPolicy.refreshDue(
                expiry.plusSeconds(1),
                expiry,
                margin));
    }
}
~~~

This tests policy logic, not the token service. For OAuth2 access tokens, add tests for: refresh token endpoint transient failure; revoked refresh token; valid access token; expired access token; multiple workers hitting 401/SMTP AUTH failure concurrently; and single-flight refresh.

### Do not use `Thread.sleep` to wait for secrets to expire

If tests actually sleep for five minutes, CI becomes slow and flaky. Instead, inject a `Clock` or create secret metadata with fixed `expiresAt` values; test with simulated instants. Use an SMTP fake for integration tests requiring auth, never production credentials.

## 23. Testing rolling restarts and multiple instances

Rotation on one service instance may succeed while the cluster still runs credential A on other pods. A staging test should simulate:

1. Three instances A1, A2, A3 running secret version A.
2. Create credential version B and confirm overlap.
3. Update A1, then A2, then A3.
4. After each step, send a canary or verify distributed authentication.
5. Watch each instance's version gauge and SMTP errors.
6. Confirm zero instances remain on A.
7. Revoke A.
8. Continue test sends from all instances using B.

### If an instance gets stuck

In normal rotation, do not revoke A while a pod still uses A without a mitigation plan. You can:

- Restart the stuck instance.
- Pause mail dispatch on that instance.
- Drain traffic away from the old pod.
- Check listeners/refresh events or cache TTLs.

In a compromise incident, you may need to revoke A regardless of rollout completion, while being prepared for send interruptions and outbox recovery.

### Beware of live connections/sessions

An SMTP connection already authenticated with an old credential may stay usable depending on transport/server behavior. That does not prove new connections will authenticate after revocation. When verifying rotation, distinguish:

- Sends reusing an existing transport/connection.
- Sends opening a new connection and authenticating anew.
- A sender bean updated with new credentials while a worker retains an old reference.

If the application uses connection pooling or a custom transport wrapper, verify connection closing/rotation policy; the demo snippet creating a new `JavaMailSenderImpl` does not automatically govern every pooling behavior in a system.

## 24. Metrics and alerts for SMTP secrets

Metrics should answer “has the secret been updated across the entire workload?” and “did rotation disrupt email?” without exposing secret values.

| Suggested metric | Purpose |
| --- | --- |
| `smtp_auth_failures_total` | Detect rejected AUTH rates |
| `smtp_secret_rotation_attempts_total` | Number of rotation attempts |
| `smtp_secret_rotation_success_total` | Number of successful promotions |
| `smtp_secret_rotation_failure_total` | Number of invalid candidates |
| `smtp_secret_seconds_until_expiry` | Remaining lifetime if metadata exists |
| `smtp_secret_age_seconds` | Age of the currently active credential |
| `smtp_secret_active_generation` | Generation active on each instance |
| `smtp_secret_version_drift_instances` | Count of instances not on the expected version |
| `smtp_dispatch_paused` | Whether the SMTP lane is paused |
| `smtp_outbox_pending` | Count of pending messages |
| `smtp_outbox_oldest_age_seconds` | Age of the oldest pending message |
| `smtp_submission_success_total` | Count of relay-accepted submissions |
| `smtp_submission_unknown_total` | Count of indeterminate outcomes |
| `smtp_secret_refresh_latency_seconds` | Latency to fetch and validate a new secret |

These names are application-defined telemetry examples; Spring Mail does not emit all of these metrics out of the box. Use Micrometer, Actuator, or your existing observability stack to collect them.

### Tiered alerts

| Situation | Response |
| --- | --- |
| Secret near expiry with no candidate | Alert team responsible for rotation |
| Candidate AUTH fails | Keep old version if safe; investigate |
| Multiple instances showing version drift | Hold scheduled revocation, fix stale instances |
| Sudden spike in AUTH failures | Isolate lane, inspect credential/provider |
| Mail queue exceeds SLA | Escalate alert per category |
| Refresh token revoked | Alert that permissions/token grant must be re-issued |
| Prolonged secret manager outage | Infrastructure alert; check remaining lifetime of current credential |

Metric labels must never contain passwords, access tokens, OTPs, full email addresses, or usernames. Avoid putting notification IDs in labels due to high cardinality. Version/generation should be non-sensitive metadata exposed only to authorized system viewers.

### Difference between version gauges and audits

Gauges show current state; audits record who rotated, from which version to which version, at what time, and whether revocation succeeded. Never substitute a gauge metric for an audit system.

## 25. Auditing, permissions, and controlled changes

A rotation event should record:

- Affected service/account/provider.
- Rotation request ID or change ticket.
- Operator or automation identity.
- Before and after versions/generations.
- Timestamps for create/stage/promote/revoke.
- Canary/`testConnection` outcome, containing no credentials.
- Count of updated instances.
- Backlog and post-cutover errors.
- Reason for rotation: scheduled, expiry, compromised credential, permission change.

### Least privilege

| Role | Appropriate permissions |
| --- | --- |
| Application runtime | Read only the required secret version |
| Rotation automation | Create/stage/promote secrets per policy |
| Security operator | Revoke/incident rotation with audit |
| Mail operator | Pause/resume queues, view non-sensitive status |
| Developer | View non-secret config, run tests on staging secrets |
| Auditor | View change history without viewing passwords |

Never grant every application pod permission to **rotate or revoke** secrets by default. Separating read access from mutation access limits the damage if a workload is compromised.

### Do not treat secret manager logs as application logs

A secret manager audit may show a workload read version B, yet it does not guarantee the workload constructed a new `JavaMailSender`, authenticated successfully, or stopped using A. Both orchestration audits and application telemetry are needed.

## 26. Common implementation mistakes

### 26.1. Hardcoding SMTP passwords in Git

Credentials persist in history, artifacts, and CI logs. Move them to a secret store; if previously exposed, rotate/revoke rather than simply deleting the line.

### 26.2. Changing the secret in the vault without refreshing JavaMailSender

Previously bound beans may keep using the old password. Restart, use verified refresh, or hot-swap.

### 26.3. Revoking the old credential immediately after creating the new one

Pods not yet cut over will fail AUTH. Use overlap when supported by the provider and revoke only after verifying the fleet; compromise incidents may require faster action.

### 26.4. Automatically rolling back to a revoked credential

Rolling back an image does not make an old password valid again. Roll forward with a newly issued credential.

### 26.5. Calling setUsername and setPassword directly on a shared sender

Not an atomic credential update. Build a new sender and perform a controlled reference swap or restart.

### 26.6. Assuming testConnection success means deliverability is fine

Successful AUTH does not prove From is allowed, quota remains, or mail reaches inboxes. Use canaries and provider events when needed.

### 26.7. Refreshing credentials on every send

Overloads the secret manager and risks refresh storms. Use a refresh coordinator, cache/TTL, and single-flight.

### 26.8. Retrying AUTH failures per notification

A bad shared credential fails the entire account, so retrying individual emails only adds load. Pause the lane and recover the credential first.

### 26.9. Leaving mail.debug enabled continuously in production

Can expose protocol details or sensitive data. Use only in controlled environments with masking.

### 26.10. Ignoring expiration of OAuth2 tokens

Short-lived access tokens require automated refresh before expiry; they cannot be stored like static passwords.

### 26.11. Allowing anonymous SMTP fallback

Lowering security on AUTH errors can permit unauthorized relaying or data leaks. Never silently downgrade AUTH/TLS without explicit approved policy.

### 26.12. Conflating AUTH errors with recipient errors

Wrong credentials are a system error; 550 recipient errors are address/destination errors. The two require different retries and alerts.

### 26.13. Dumping the entire backlog immediately after rotation

Can trigger SMTP throttling right after credentials recover. Drain through a rate limiter and concurrency gate.

### 26.14. Failing to verify all replicas and workers

Old pods or scheduled jobs outside the rollout may still use version A. Track fleet versions before revoking.

### 26.15. Putting credential details into metric labels

Raw secrets, tokens, or sensitive account keys do not belong in telemetry. Use only safe metadata with controlled access.

### 26.16. Treating secret cache expiration as proof the SMTP secret was revoked

Cache TTL is just an application reload policy. It does not reflect exact credential lifecycle at the provider. Distinguish cache expiry from credential expiry.

### 26.17. Deleting all failed records once the new credential works

Loses audit history and obscures which emails were never submitted. Keep outbox/attempt history and process each state per policy.

## 27. Checklist before, during, and after rotation

### Before rotation

1. Complete inventory of all SMTP consumers/service accounts.
2. Clear owner, schedule, and credential expiration deadlines.
3. Confirmed whether the provider supports overlap.
4. Secret B created in the right environment's secure store.
5. Canary ready to verify TLS, AUTH, and From permissions.
6. Metrics for secret version, AUTH failures, and queue age.
7. Ability to pause mail dispatch without losing the outbox.
8. Realistic rollback or roll-forward plan.
9. Emergency revocation runbook if credentials leak.

### During rotation

1. Record audit change/rotation ID.
2. Verify B is valid before promotion.
3. Roll out in batches or via safe hot-swap.
4. Check which pods still use A.
5. Prevent retry storms if AUTH fails.
6. Monitor OTP/transactional backlogs and provider quotas.
7. Never log passwords/tokens while diagnosing.

### After rotation

1. All instances run version B per policy.
2. Auth/canary sends succeed.
3. No in-flight senders still require A.
4. A revoked at the right time.
5. Outbox drained under control.
6. No widespread AUTH failures remain.
7. No `SUBMISSION_UNKNOWN` records blindly replayed.
8. Audits and dashboards reflect the new version.
9. Next rotation schedule updated.

## 28. Real-world scenario examples

### Scenario A — Scheduled SMTP password rotation with two credentials

An order confirmation service has two worker replicas using SMTP credential A. The provider supports creating an independent credential B with equivalent sending permissions.

**Implementation:**

1. Create B in the secret manager without placing the password in deployment manifests.
2. Run a canary using B confirming STARTTLS, AUTH, and permission to send from the allowed address.
3. Roll out the first replica to B; check auth failures and test sending.
4. Roll out the second replica to B.
5. Confirm no sending paths remain on A, including scheduled jobs and legacy workers.
6. Revoke A.
7. Keep metrics/audits and watch the queue post-rollout.

**Expected outcome:** zero outbox loss, no window where the entire system fails AUTH, and no secrets stored in the repository.

### Scenario B — Password expires while processing a backlog

A marketing campaign queues many jobs while invoice emails are also pending. Credential A expires and all new AUTH attempts fail.

**What not to do:** let each notification retry 10 times immediately while 20 pods hammer the secret manager and SMTP. That creates an authentication storm without sending any emails.

**What to do:**

1. Classify AUTH errors on the shared account.
2. Pause the affected SMTP lane and alert.
3. Preserve the outbox; pause deferrable marketing emails.
4. Issue/read B, test AUTH and canary.
5. Roll out B and verify versions across the cluster.
6. Open dispatch with rate limiting; prioritize still-valid invoices/OTPs.
7. Mark expired marketing/OTPs as `EXPIRED` per policy.

### Scenario C — OAuth2 token expires overnight

An application uses XOAUTH2 with a short-lived access token. After some time, the token expires and SMTP starts rejecting logins.

**Right direction:** confirm the token flow and scopes, refresh tokens via the token provider per policy, check clocks and safety margins, and avoid simultaneous refreshes across every worker. If the refresh token was revoked, re-establish the grant/identity per provider mechanism; retrying with the same expired access token will not help.

**What to measure:** token refresh count, latency, error rate, remaining lifetime, pods running valid token generations, and outbox state during the outage.

### Scenario D — New secret lacks permission for the From address

Candidate B authenticates via SMTP AUTH, yet the provider forbids sending from one of the application's From addresses.

**Problem:** `testConnection` may pass, yet sending a canary with the target From fails.

**Handling:** check sender/account permissions and verified identities, adjust permissions at the provider, re-test with a valid canary, and promote B only when real sending requirements pass. Do not conclude the password is wrong simply because the server rejects `MAIL FROM`.

### Scenario E — Credential leaked in logs

A developer accidentally logged an `SmtpSecret` object containing a password during troubleshooting.

**Handling:** treat this as a credential exposure incident. Identify the log scope and who has read access, rotate/revoke the credential based on risk level, inspect provider audits for unauthorized sending, delete/restrict affected logs per policy, and fix the code so it never serializes secrets. Deleting just one newly emitted log line is not enough to be sure all copies are gone.

## 29. Self-check questions

**1. Why doesn't changing a secret in the secret manager mean JavaMailSender changed its password?**

Because in standard setups `JavaMailSenderImpl` receives its username/password when the bean is created. The application needs a rolling restart, verified refresh mechanism, or sender hot-swap; the secret store does not mutate running objects by itself.

**2. How does rotation differ from refreshing a token?**

Rotation transitions to a new credential/version and revokes the old credential per policy. Refreshing a short-lived token fetches a new access token for upcoming AUTH calls; refresh tokens or client secrets also have their own lifecycle requiring rotation.

**3. Should a personal mailbox's SMTP password be used as a production credential?**

No. Prefer dedicated service identities/credentials with least privilege, clear ownership, and defined rotation/auditing.

**4. Why shouldn't setUsername and setPassword be updated directly on a bean shared across threads?**

Two separate calls are not an atomic change; other threads may observe an inconsistent config. Construct a complete new sender and swap references or restart.

**5. When can the old credential be revoked?**

In overlapping rotation, after the candidate passes checks, all instances cut over, and no in-flight sends need the old credential per policy. During a compromise incident, emergency revocation may be needed sooner.

**6. If a provider allows only one password, is absolute zero downtime guaranteed?**

Do not promise that. Plan a cutover, optionally pause dispatch, update all instances, and recover the backlog. If two separate accounts/credentials are supported with proper permissions, you can design overlap.

**7. Does testConnection succeeding prove emails are delivered to inboxes?**

No. It primarily checks connectivity and configured authentication. A real canary send is needed to test submit permissions; delivery/bounces happen at a later stage.

**8. Does SMTP returning 535 definitely mean the secret expired?**

No. It could be wrong credentials, revocation, a locked account, an incompatible AUTH mechanism, or provider policy errors. Inspect context, enhanced status codes, and recent changes.

**9. Should SMTP AUTH errors be retried per email?**

Do not retry continuously. When a shared credential is invalid, pause the lane and perform controlled refresh/rotation; the outbox retains jobs.

**10. What if the secret manager is unavailable while the active credential is still valid?**

You may continue using the cached credential per policy when there is no evidence of revocation/exposure, while retrying refreshes with backoff and alerting. Never continue using a secret known to be expired or revoked.

**11. When should an OAuth2 access token be refreshed?**

An appropriate safety margin before `expiresAt`, factoring in connection time, token service latency, and clock skew—never wait until AUTH is guaranteed to fail.

**12. Do you need to check every pod during a rolling rotation?**

Yes. A single stale pod or legacy job still using credential A will fail immediately once A is revoked. Track active versions across all relevant workloads.

**13. Should mail.debug be left on in production throughout rotation?**

Not by default. Protocol debugging can expose sensitive info. Enable only under strict bounds, masking, access control, and a turn-off plan.

**14. Can you roll back to the old password after the provider revokes it?**

No. Once the old credential is invalid, you must roll forward or issue a new credential; rolling back an image does not make a revoked password work again.

**15. Once the secret is updated, should all FAILED emails be replayed?**

No. Distinguish states, error causes, expiry, suppression, and `SUBMISSION_UNKNOWN`. Replay only eligible records, all throttled through a rate limiter.

**16. Why must expiry monitoring include rollout status?**

Because knowing a secret expires soon is not enough; you need to know whether a candidate was validated and whether all instances switched to the new version.

**17. Can SMTP usernames be logged?**

A username may be an internal identifier or sensitive email address. Log only when needed with appropriate masking/access controls; never log passwords or access tokens.

**18. Why isn't changing an SMTP password the same as changing a TLS certificate or DKIM key?**

They are different credentials/functions: SMTP AUTH controls relay login, TLS protects the transport channel, and DKIM signs messages. Each has its own lifecycle and rotation procedure.

**19. What should you do if credential B passes AUTH but MAIL FROM is rejected?**

Check sender authorization, verified identities, and provider policies. Do not shift full traffic until a canary using the actual From address succeeds.

**20. How do you know rotation is truly complete?**

The new candidate is verified, all workloads run the right version, the old credential is revoked per policy, no widespread AUTH failures remain, the backlog is safely processed, and the audit logs the result.

## Conclusion

**SMTP secret rotation is an ongoing security and operational process, not merely swapping a password in configuration.** With Spring Framework Mail, you must establish where credentials are managed, version/expiry lifecycles, how `JavaMailSender` reloads them, SMTP AUTH permissions, and how instances transition without losing send requests. When a provider supports two credentials, create an overlap window, verify the candidate, and only then revoke the old version; when unsupported, plan a controlled cutover backed by a durable outbox. With OAuth2/XOAUTH2, refresh access tokens ahead of expiry and avoid refresh storms. If credentials fail broadly, pause the sending lane, classify errors, alert, and recover with a valid secret instead of endlessly retrying individual emails. Finally, test rotation, track expiry/version drift, protect logs, drain backlogs via rate limiters, and record audits. **A well-designed system can rotate credentials safely, catch expirations before incidents happen, and restore email delivery without sacrificing security or causing cascading failures.**
