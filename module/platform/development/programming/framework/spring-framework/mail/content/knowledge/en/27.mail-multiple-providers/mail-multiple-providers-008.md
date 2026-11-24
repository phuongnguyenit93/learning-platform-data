# Managing Separate Credentials and Quotas

## 1. The Problem When Spring Framework Mail Uses Multiple Providers

In a **Spring Framework Mail** application, sending email through a single SMTP server is relatively straightforward: configure `spring.mail.host`, `spring.mail.username`, `spring.mail.password`, build a `MimeMessage`, and call `JavaMailSender.send(...)`. When a system sends mail across **multiple providers (multi-provider)**, however, swapping the host during an incident is not enough.

Each provider may have:

- One or more **credentials** (SMTP username/password, API key, or OAuth2 token).
- Distinct verified **sender identities** and domains.
- Different SMTP AUTH, TLS, port, and authentication-mechanism policies.
- **Quotas** metered by message, recipient, request, connection count, hour/day, or account scope.
- Different rate limits, bursts, concurrency caps, and throttling responses.
- Separate dashboards, audits, message traces, bounce/complaint feeds, and quota telemetry.
- Separate credential-locking, key-rotation, and account-suspension mechanics.

Sharing a single `SMTP_PASSWORD` variable and a single `mailSentToday` counter across all providers makes it easy to send with the wrong identity, exceed quotas, or break the backup route when rotating secrets.

**Goal:** every sending path must have a **provider profile** with isolated credentials, sender permissions, quota policies, and operational state; route selection must be governed so mail jobs never carry passwords or pick arbitrary SMTP hosts.

~~~text
Business events / Notification requests
                  |
                  v
          Mail outbox / queue
                  |
                  v
            Mail dispatcher
                  |
          Approved route policy
                  |
          +-------+--------+
          |                |
          v                v
    Provider A          Provider B
    Account A           Account B
    Credential A        Credential B
    Allowed From A      Allowed From B
    Rate/Quota A        Rate/Quota B
          |                |
          v                v
    JavaMailSender A    JavaMailSender B
          |                |
          v                v
      SMTP A             SMTP B
~~~

**There is no universal permission or quota-counting model across providers.** Throughout this lesson, numbers and provider profile names are design examples, not published limits of any specific vendor. In real operations, check the documentation and console for the exact accounts you use.

## 2. Separate Four Concepts: Provider, Account, Credential, and Sender Identity

These terms are often used interchangeably, yet they can be four distinct entities:

| Entity | Role | Hypothetical example |
|---|---|---|
| Provider | Service supplying SMTP or email API | `PRIMARY_SMTP` |
| Provider account / organization | Unit owning plan and quota | `company-prod-account` |
| Credential / service identity | Identity permitted to authenticate to send | `orders-smtp-key-v3` |
| Sender identity | Address/domain allowed in `From` | `orders@example.com` |
| Route profile | Application configuration linking the components | `PROD_ORDERS_PRIMARY` |

One provider account may issue multiple credentials. Those credentials **may share the account's quota** rather than each key adding extra quota. Conversely, another provider may assign separate limits per sending pool or identity.

Nor does a credential automatically permit sending from every `From` address: providers may require verified senders, Send As rights, or specific delegation setups.

### Why Not Use Username as the Provider ID?

Some SMTP providers use usernames that are not email addresses; some use token identifiers, and some separate SMTP username from account ID. On credential rotation, the username may change while route `PROD_ORDERS_PRIMARY` stays the same logical route.

Therefore use stable logical IDs:

~~~text
providerId        = PRIMARY_SMTP
providerAccountId = PRIMARY_PROD_ACCOUNT
senderProfileId   = ORDERS
credentialRef     = secret://mail/primary/orders/current
quotaScope        = PRIMARY_PROD_ACCOUNT
~~~

This is modeling data, not a mandatory secret-manager URI format. Never write secret values into route profiles, the outbox, or logs.

## 3. Security and Quota Boundary Model

Two providers do not automatically form two independent domains if the application shares keys, accounts, or sending paths:

~~~text
                         Spring Mail Application
                                   |
                        Approved profile resolver
                                   |
                  +----------------+----------------+
                  |                                 |
                  v                                 v
            Provider A                        Provider B
           secret scope A                    secret scope B
           SMTP identity A                   SMTP identity B
           sender policy A                   sender policy B
           quota counter A                   quota counter B
           provider audit A                  provider audit B
                  |                                 |
                  v                                 v
            Accepted / failed                 Accepted / failed
~~~

Boundaries to maintain:

1. **Secrets:** Workload A or sender A cannot read credential B by default.
2. **Provider selection:** Jobs use only application-approved routes, never taking host/username/password from HTTP requests.
3. **Sender authorization:** `From` must be permitted on the chosen provider.
4. **Quotas:** Counters/limiters apply to the exact provider-account scope without deducting from another account's budget.
5. **Outcomes:** Failures on provider A are never misrecorded under provider B's metrics.
6. **Audits:** You can tell which job tried which route and which attempt without exposing credentials or recipient addresses.

### Incidents When Boundaries Are Not Separated

| Broken design | Consequence |
|---|---|
| Sharing one SMTP password across both route configs | Secret exposure hits multiple routes; risk of authenticating against the wrong provider |
| One mutable `JavaMailSenderImpl` calling `setHost/setPassword` per request | Thread races, risk of sending with the wrong identity |
| One rate bucket across all providers | Provider A can drain B's permits even with independent quotas |
| Separate bucket per credential despite shared account quota | Combined volume can exceed the account quota |
| Failing over all errors to B | Duplicates when A accepted yet the response was lost |
| Changing only SMTP host while keeping old `From` | Provider B may reject the unverified sender |
| Logging full SMTP credentials for debugging | Leaking authentication secrets into observability systems |

## 4. Why Use Multiple Providers?

Before designing registries and routing, distinguish your goals:

- **High availability:** having a backup path when primary stops serving.
- **Workload isolation:** OTPs, invoices, and marketing get separate accounts/quotas.
- **Cost optimization:** picking routes by pricing and valid need within policy limits.
- **Geography/compliance:** data and sending must pass through approved providers/regions.
- **Deliverability:** domains, sender reputation, and bounce/complaint handling per route.
- **Provider migration:** gradually shifting traffic to a new system under control.

These goals shape how you choose quota keys:

| Goal | Typical isolation considered |
|---|---|
| HA | Primary and secondary have independent credentials and quota policies |
| High-priority OTP | Dedicated sender identity/account/lane or protected budget |
| High-volume marketing | Separate queues/credentials/quotas from transactional |
| Multi-tenant | Provider profiles and authorization policies per tenant |
| Migration | Route weights and separate quota keys per account with metered rollout |

**Multiple providers are not a way to evade one provider's anti-spam or quota enforcement.** Routing/failover must respect contracts, consent, sender verification, and deliverability rules. If an account is restricted for bad sending practices, shifting traffic elsewhere to continue the same behavior is a security and compliance problem, not HA.

## 5. Least-Privilege Principle for Every Credential

A sending path's credential should only hold permissions needed for its exact job:

- Send email from verified identities or domains.
- No organization/tenant admin rights when only SMTP submission is needed.
- No mailbox read/delete permissions if the app does not read via IMAP/POP or mail APIs.
- Never reuse employee or administrator credentials.
- Separate credentials between production and development/staging.
- Restrict connection sources by IP/relay policy or workload identity where supported.
- Configure quotas/rates and anomaly alerts.
- Independently revocable without breaking other routes.

An example permission matrix:

| Permission | Transactional sender A | Marketing sender B |
|---|---|---|
| SMTP submit from assigned sender | Allowed | Allowed |
| Send As any mailbox in org | No | No |
| Read employee mailboxes | No | No |
| Modify DNS/domain settings | No | No |
| Administer users/accounts | No | No |
| Send through approved endpoint/region | Allowed | Allowed |
| Use production secret in staging | No | No |

A provider may not offer a role literally named "send-only." If the vendor's permission model is broader than required, document the risk, add compensating controls, or consider a better-scoped account/provider.

## 6. Separate Credentials Do Not Automatically Mean Separate Quotas

Example:

~~~text
Provider A / Production account
  |
  +-- SMTP credential order-mailer
  +-- SMTP credential security-mailer
  |
  +-- Shared quota: recipients/day

Provider B / Independent account
  |
  +-- SMTP credential newsletter-mailer
  |
  +-- Own quota: messages/second
~~~

In this hypothetical setup, provider A's `order-mailer` and `security-mailer` use **two different credentials sharing one daily budget**. Building two independent token buckets and letting each spend A's full quota will exceed the total limit.

Therefore apply **two-dimensional separation**:

1. Separate **credentials** for security and usage permissions.
2. Separate/group **quota accounting** to match the exact scope published by the provider.

A single job may simultaneously need to satisfy **total account** quota, **credential** rate, **sender** rate, and **tenant** fairness. Quota boundaries do not necessarily mirror password boundaries.

## 7. Store Credentials in a Secret Manager, Never Embed in Source

An anti-pattern:

~~~yaml
app:
  mail:
    providers:
      primary:
        password: real-smtp-password-committed-to-git
      secondary:
        password: another-real-smtp-password-committed-to-git
~~~

Even if passwords are removed in a later commit, secrets remain in git history, builds, CI logs, and container images. Each provider needs a **distinct secret reference** with read access restricted to the workload actually using it.

A cleaner design:

~~~text
Production secret store
   |
   +-- /mail/primary/transactional/current
   |      +-- SMTP username / password
   |      +-- access limited to transactional workload
   |
   +-- /mail/secondary/transactional/current
   |      +-- distinct credentials
   |      +-- access limited to approved fallback workload
   |
   +-- /mail/primary/marketing/current
          +-- isolated campaign sender identity
~~~

In the application, config values can be injected via environment variables, mounted secrets, or a secret-manager integration. **Environment variables alone are not a secret vault**: anyone able to inspect process environments or crash dumps can read them. Protect runtime access, auditing, and deployment lifecycles.

### Do Not Put Secrets Into the Outbox

A job must be persisted durably to send after an application restart, yet must never snapshot passwords:

~~~json
{
  "jobId": "mail-job-381",
  "senderProfileId": "ORDERS",
  "preferredProvider": "PRIMARY",
  "recipientId": "customer-42",
  "notificationType": "ORDER_RECEIPT"
}
~~~

`preferredProvider` and `senderProfileId` are logical IDs. The worker resolves the approved provider profile and credential at send time. If a job must "freeze" certain policy parameters at creation time, store only a secret-free **version ID**.

### Do Not Log Full Configuration Beans

Avoid:

~~~java
log.debug("SMTP configuration: {}", smtpConfig);
~~~

If `smtpConfig` is a record containing a password field, `toString()` can accidentally dump the secret into logs. For configuration DTOs holding secrets, disable careless automatic logging or serialization; log only `providerId`, `configVersion`, and sanitized fields.

## 8. Spring Boot Configuration for Two Providers

`spring.mail.*` in Spring Boot typically describes one default sender. With multiple SMTP routes, design a dedicated configuration namespace representing **each provider profile**, then create multiple `JavaMailSender` beans.

Example `application.yml`:

~~~yaml
app:
  mail:
    providers:
      primary:
        host: smtp-primary.example.test
        port: 587
        username: ${PRIMARY_SMTP_USERNAME}
        password: ${PRIMARY_SMTP_PASSWORD}
        allowed-from: orders@example.com
        auth: true
        starttls: true
        max-concurrent: 4
      secondary:
        host: smtp-secondary.example.test
        port: 587
        username: ${SECONDARY_SMTP_USERNAME}
        password: ${SECONDARY_SMTP_PASSWORD}
        allowed-from: orders@example.com
        auth: true
        starttls: true
        max-concurrent: 2
~~~

Hostnames and limits are examples. `allowed-from` is only an **application-checked rule**; putting it in YAML does not grant sender authorization at the provider. Before production use, From addresses must be verified/authorized on each provider.

Placeholders are supplied at runtime; never commit real credentials.

### A Record for Binding Configuration

~~~java
import org.springframework.boot.context.properties
        .ConfigurationProperties;

@ConfigurationProperties(prefix = "app.mail.providers")
public record MultiProviderMailProperties(
        SmtpEndpoint primary,
        SmtpEndpoint secondary) {

    public record SmtpEndpoint(
            String host,
            int port,
            String username,
            String password,
            String allowedFrom,
            boolean auth,
            boolean starttls,
            int maxConcurrent) {
    }
}
~~~

Register with Spring:

~~~java
import org.springframework.boot.context.properties
        .EnableConfigurationProperties;
import org.springframework.context.annotation.Configuration;

@Configuration
@EnableConfigurationProperties(
        MultiProviderMailProperties.class)
public class MailProviderPropertiesConfiguration {
}
~~~

`@ConfigurationProperties` only **binds** values. It does not select providers per email or enforce quotas. Add Jakarta Bean Validation on `port`, `host`, and `maxConcurrent` to fail fast on missing or invalid settings.

### Do Not Mix an Auto-Configured Sender with Custom Beans by Accident

In a multi-provider app, you should know exactly which bean serves which route. Once multiple `JavaMailSender` beans exist, unqualified injection causes ambiguity. Never leave a broad-permission default bean lying around for features to grab unchecked.

## 9. Creating a Dedicated JavaMailSender per SMTP Provider

The example below uses only Spring Mail and JavaMail APIs without calling SMTP during bean creation:

~~~java
import java.util.Properties;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.mail.javamail.JavaMailSender;
import org.springframework.mail.javamail.JavaMailSenderImpl;

@Configuration
public class MultiProviderMailConfiguration {

    private JavaMailSenderImpl createSender(
            MultiProviderMailProperties.SmtpEndpoint cfg) {

        JavaMailSenderImpl sender = new JavaMailSenderImpl();
        sender.setHost(cfg.host());
        sender.setPort(cfg.port());
        sender.setUsername(cfg.username());
        sender.setPassword(cfg.password());
        sender.setDefaultEncoding("UTF-8");

        Properties mailProps = sender.getJavaMailProperties();
        mailProps.put("mail.smtp.auth",
                Boolean.toString(cfg.auth()));
        mailProps.put("mail.smtp.starttls.enable",
                Boolean.toString(cfg.starttls()));
        mailProps.put("mail.smtp.starttls.required",
                Boolean.toString(cfg.starttls()));
        mailProps.put("mail.smtp.ssl.checkserveridentity", "true");
        mailProps.put("mail.smtp.connectiontimeout", "5000");
        mailProps.put("mail.smtp.timeout", "10000");
        mailProps.put("mail.smtp.writetimeout", "10000");
        mailProps.put("mail.debug", "false");
        return sender;
    }

    @Bean("primaryMailSender")
    JavaMailSender primaryMailSender(
            MultiProviderMailProperties props) {
        return createSender(props.primary());
    }

    @Bean("secondaryMailSender")
    JavaMailSender secondaryMailSender(
            MultiProviderMailProperties props) {
        return createSender(props.secondary());
    }
}
~~~

Both beans have independent configs, yet **do not enforce provider quotas automatically**. Putting `maxConcurrent` in the config DTO only informs the SMTP coordinator in later steps.

### Selecting Beans with @Qualifier

~~~java
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.mail.javamail.JavaMailSender;
import org.springframework.stereotype.Component;

@Component
public class ProviderSenderRegistry {
    private final JavaMailSender primary;
    private final JavaMailSender secondary;

    public ProviderSenderRegistry(
            @Qualifier("primaryMailSender")
            JavaMailSender primary,
            @Qualifier("secondaryMailSender")
            JavaMailSender secondary) {
        this.primary = primary;
        this.secondary = secondary;
    }

    public JavaMailSender resolve(ProviderId provider) {
        return switch (provider) {
            case PRIMARY -> primary;
            case SECONDARY -> secondary;
        };
    }
}

enum ProviderId {
    PRIMARY, SECONDARY
}
~~~

`ProviderId` is an internal enum. Never accept `providerHost` or `smtpPassword` strings from an HTTP request and instantiate `JavaMailSenderImpl` from client-supplied values.

### Never Mutate a Singleton Sender Before Each Send

Broken under concurrency:

~~~java
// One shared bean; two threads can overwrite each other's config.
sender.setHost(route.host());
sender.setUsername(route.username());
sender.setPassword(route.password());
sender.send(message);
~~~

If thread A is setting primary credentials while thread B overwrites them with secondary, the app can authenticate wrong or send through an unintended path. Keep separate senders per provider profile with immutable config for a deployment/rotation cycle; if dynamic tokens are needed, use a purpose-built authentication mechanism instead of mutating shared globals before each call.

## 10. Separate Sender Identity from Business APIs

A controller must never let callers choose:

~~~json
{
  "smtpHost": "random-host.example",
  "smtpPassword": "supplied-by-client",
  "from": "ceo@example.com",
  "to": "victim@example.net",
  "html": "arbitrary-content"
}
~~~

Such an API turns the backend into an abusable mail relay. Instead, clients describe only the **business action**:

~~~java
public record OrderReceiptCommand(
        String orderId,
        String customerId,
        String locale) {
}
~~~

Application service:

1. Verify permissions on the order.
2. Look up the recipient from trusted data.
3. Select the approved template.
4. Select sender profile `ORDERS` and an eligible route.
5. Persist the job in the outbox.
6. Let the dispatcher enforce quotas/routes when sending.

Just because a job requests sending an email does not mean it may bypass quotas or switch to an arbitrary provider. Business authorization, sender permissions, and quota admission are separate defense layers.

## 11. Verifying From Addresses on Each Provider

An email may use:

~~~text
SMTP authentication identity: api-user-a
Header From: orders@example.com
SMTP envelope MAIL FROM: bounce-a@example.com
Reply-To: support@example.com
~~~

Provider A may have verified `orders@example.com`. Provider B **may not** permit that address yet even if owned by the same organization. When using B, resolve:

- Verified sender/verified domain or Send As permission under B's model.
- DKIM selector and DNS records matching B.
- SPF or custom return-path matching sending via B.
- DMARC alignment and domain policies.
- Bounce/complaint endpoint for B.
- Reputation and specific limits of account B.

In Spring:

~~~java
import org.springframework.mail.javamail.MimeMessageHelper;

var message = selectedSender.createMimeMessage();
var helper = new MimeMessageHelper(message, true, "UTF-8");
helper.setFrom(route.allowedFrom());
helper.setTo(recipient);
helper.setSubject("Order confirmation");
helper.setText(plainText, htmlText);

selectedSender.send(message);
~~~

`route.allowedFrom()` must come from server-side approved configuration; setting it in Java code **does not grant sending authority for that address**. If a provider rejects the sender, never fall back to an admin account authorized for every mailbox as a "quick fix."

## 12. SMTP AUTH, OAuth2, and Email API Credentials

Not every provider uses a username/password pair the same way:

| Mechanism | Typical credentials | What must be managed |
|---|---|---|
| SMTP AUTH username/password | Username, password/app password | Secret store, rotation, TLS, account policy |
| SMTP with XOAUTH2 | Access token, token acquisition/refresh flow | Scope, audience, expiry, client credentials |
| HTTPS email API | API key or OAuth token | Scope, endpoint, key rotation, HTTP 429 |
| IP/cert/connector SMTP relay | Network identity or certificate | Egress IP, mTLS/TLS, connector policy, anti-open-relay |

`JavaMailSender` is an abstraction for sending over Jakarta Mail/SMTP. If Provider B only offers an **HTTP email API**, the app normally needs a dedicated HTTP adapter; do not force every credential/API call through `JavaMailSenderImpl`.

### OAuth2 Does Not Automatically Mean Least Privilege

Short-lived access tokens can beat static passwords when well managed. Yet tokens can still be over-scoped—for example, holding mailbox-read or tenant-admin permissions. Check:

- Grant type: delegated vs. application/service identity.
- Scope/audience genuinely authorized for SMTP submit/send.
- Which senders/mailboxes may be impersonated.
- Whether admin or mailbox-read rights were granted unnecessarily.
- Refresh mechanism, token expiry, revocation, and private-key/client-secret rotation.

Specifically with XOAUTH2, never paste one fixed token in place of a password for long-term deployment. The adapter must fetch fresh tokens per authentication lifecycle, avoid expiring mid-connection/bean life, and never log tokens on error.

## 13. Rotating Credentials Independently per Provider

A multi-provider system must allow rotating credential A without breaking route B. That is a major benefit of **not sharing secrets or a mutable singleton sender**.

Steps to rotate primary credentials:

1. Inspect the current secret version, list of using workloads, and granted permissions.
2. Provision a new credential at provider A with the **same minimal scope**, never adding admin or wildcard sender rights.
3. Store the new credential in the secret manager as a new version.
4. Deploy/reload the app so new instances use the new credential.
5. Test submission from an allowed sender using a sandbox recipient.
6. Verify no old instances or queue consumers still use the old credential.
7. Revoke the old credential after cutover per security policy.
8. Confirm authentication-failure metrics return to baseline and log an audit of the rotation.

If the provider supports **two concurrently active credentials**, you can do blue/green rotation:

~~~text
Secret A v1 ------- production current
            \
             +---- issue A v2
                        |
                        +---- deploy new instances with v2
                        |
                        +---- verify SMTP success
                        |
                        +---- drain old instances / sessions
                        |
                        +---- revoke v1

Secret B --------- unchanged
~~~

If the provider allows only one password, changing it can break authentication on older running instances. Plan a coordinated rollout and retry handling; never assume zero-downtime rotation always works.

### Secret Rotation and Connection Reuse

An already-authenticated SMTP connection may continue working after a secret change depending on server and implementation, while new connections begin failing if they use the old credential.

Therefore:

- Understand how your adapter reuses SMTP transports/connections.
- Never treat "one email just succeeded" as proof every instance is using the new secret.
- Verify opening **new** connections with the new credential.
- Close/drain old sessions on schedule.
- Monitor auth failures by provider and sanitized secret version.

Never log passwords/tokens to check versions. You can log a non-sensitive **configuration version ID** assigned by deployment tooling.

## 14. Handling Compromised or Revoked Credentials

Signals worth watching:

- SMTP auth attempts from unapproved IPs/regions.
- Unexpected volume sent compared to internal outbox jobs.
- Widespread provider auth errors after secret rotation.
- Console quota climbing without matching application dashboard submissions.
- Credentials appearing in repositories, CI output, error traces, or support tickets.

Incident response should stay scoped to the affected route:

~~~text
Credential A suspected compromised
      |
      +-- Disable/revoke A credential or route
      +-- Stop A submissions / quarantine suspicious jobs
      +-- Review A grants, From permissions, provider trace
      +-- Rotate A secret and re-verify sender identity
      +-- Determine impact on shared quota and reputation
      |
      +-- Provider B remains independently managed
             |
             +-- Only allowed jobs can use B
             +-- Apply B quotas and sender permissions
~~~

Do not automatically move **every** A job to B on suspected compromise. Jobs may hold unapproved content or may have already submitted through A with an unclear outcome. Apply failover policy, verify business origin, and classify states.

### Environment Isolation Is Mandatory

Development/staging should use an SMTP sink or dedicated sandbox profile and credentials. If staging holds production keys, a test run against copied customer data can send real emails. Even if the app has `if (profile.equals("staging"))`, **provider-side recipient restrictions** remain a stronger safeguard when supported.

## 15. Version and State Model for Provider Profiles

A profile needs more fields than host/password:

~~~java
public enum ProviderHealth {
    ACTIVE,
    DEGRADED,
    PAUSED,
    RETIRED
}

public record ProviderRoutePolicy(
        ProviderId providerId,
        String accountId,
        String senderProfileId,
        String allowedFrom,
        String quotaScopeKey,
        String configurationVersion,
        ProviderHealth health) {
}
~~~

Purpose of each field:

- `providerId`: logical route identifier.
- `accountId`: identifies account/plan.
- `senderProfileId`: allowed email group.
- `allowedFrom`: valid sending address per application config.
- `quotaScopeKey`: where real provider capacity is accounted.
- `configurationVersion`: supports change auditing.
- `health`: dispatcher status, not auth permission.

**`ProviderHealth.ACTIVE` does not mean tokens are valid, quota remains, or From is permitted.** It is only one slice of operational state; the app still checks quotas, sender policies, and provider responses.

If weighted route selection is needed, configure weights at the routing layer without arbitrarily changing secret/quota scopes per request.

## 16. Per-Provider Quotas Have Multiple Units and Windows

A provider may enforce:

| Limit | Unit | Illustrative example |
|---|---|---|
| Submission rate | messages/second | 8 messages/s |
| Recipient rate | recipients/second | 15 recipients/s |
| Daily sending quota | recipients/rolling 24h | 20,000 recipients |
| API request quota | API calls/minute | 300 calls/min |
| SMTP concurrency | submissions in-flight | 4 operations |
| Per-message recipients | RCPT TO/message | 50 recipients |
| Message size | raw MIME bytes/message | 15 MiB |
| Sender/domain throttle | variable/provider-specific | Slowdown when reputation drops |

These are not numbers from any specific vendor. Having **separate credentials** is no proof each row in the table has an independent per-credential limit.

### A Cost Model Instead of One Shared Limit Variable

~~~java
public record MailQuotaCost(
        int messages,
        int recipients,
        long mimeBytes) {

    public MailQuotaCost {
        if (messages <= 0 || recipients <= 0 || mimeBytes < 0) {
            throw new IllegalArgumentException(
                    "Invalid mail quota cost");
        }
    }
}
~~~

Example of one `MimeMessage` with 1 message and 5 SMTP envelope recipients:

~~~text
message quota     -> cost 1
recipient quota   -> cost 5
byte-size check   -> serialized MIME byte count
concurrency       -> cost 1 in-flight slot
~~~

Do not deduct `1` from every bucket for a multi-recipient message. If a provider meters quota by recipients, count To/Cc/Bcc or actual envelope recipients—not only the `To` header.

### Quota Resets Must Be Exact

A "per day" quota can mean:

- Calendar day in the provider's timezone.
- Rolling 24 hours.
- Window from plan activation time.
- Billing-period reset.

If the provider uses a rolling 24h window while the app resets counters at midnight, you can send nearly twice the threshold around midnight and get throttled. **Know the quota unit, scope, window, and measurement source.**

## 17. Provider-Aware Policy: Never Use One Default Limit for Every Route

An illustrative rate/quota config:

~~~yaml
app:
  mail:
    quota:
      primary:
        scope-key: PRIMARY_PROD_ACCOUNT
        rate-unit: recipients
        tokens-per-second: 4.0
        burst-capacity: 12
        max-concurrent: 3
        safe-daily-recipient-budget: 15000
      secondary:
        scope-key: SECONDARY_PROD_ACCOUNT
        rate-unit: messages
        tokens-per-second: 2.0
        burst-capacity: 6
        max-concurrent: 2
        safe-daily-recipient-budget: 3000
~~~

`app.mail.quota.*` is **application-designed configuration**. Spring Boot does not automatically limit messages/second or recipients/day merely because those keys exist.

Also, the config assumes primary and secondary use two different quota accounts. If two profiles share one provider account, `scope-key` must represent **one shared quota**, never creating two independent buckets each holding the full budget.

### A Quota Policy Record

~~~java
public enum RateUnit {
    MESSAGES,
    RECIPIENTS
}

public record ProviderQuotaPolicy(
        String scopeKey,
        RateUnit unit,
        double tokensPerSecond,
        int burstCapacity,
        int maxConcurrent,
        long safeDailyRecipientBudget) {

    public ProviderQuotaPolicy {
        if (scopeKey == null || scopeKey.isBlank()
                || !Double.isFinite(tokensPerSecond)
                || tokensPerSecond <= 0
                || burstCapacity <= 0
                || maxConcurrent <= 0
                || safeDailyRecipientBudget < 0) {
            throw new IllegalArgumentException(
                    "Invalid provider quota policy");
        }
    }
}
~~~

In real policies, add `quotaWindow`, `accountId`, multiple rate limits if the provider enforces them simultaneously, and a policy version. Never try squeezing both messages/second and recipients/day into a single `unit` field; maintain separate counters.

## 18. Rate Limits and Concurrency Are Two Distinct Controls

Suppose two providers have settings:

~~~text
Primary:
  safe rate = 4 recipient/s
  max concurrent SMTP submissions = 3

Secondary:
  safe rate = 2 messages/s
  max concurrent SMTP submissions = 2
~~~

**Rate** caps units consumed over time; **concurrency** caps network operations running simultaneously. One thread can send many messages/second; setting `maxPoolSize=3` does not mean 3 messages/second.

~~~text
Outbox
  |
  v
Quota reservation by account/sender
  |
  v
Rate gate by provider policy
  |
  v
Concurrency semaphore / connection gate
  |
  v
JavaMailSender.send(...)
  |
  v
Release concurrency slot in finally
~~~

When no permit is available, never hold an SMTP thread in `Thread.sleep(...)` for long. Move the job to waiting state, update `available_at`, and free the worker.

### Why Local Semaphores May Not Be Enough

If 4 replicas each set `maxConcurrent=3` for the same provider account, the cluster can open up to 12 concurrent submissions. If the provider caps the whole account at 3 connections/transactions, you need **global concurrency admission** or a centralized dispatcher. A local setting does not govern shared quotas.

## 19. Synchronizing Limits Across Multiple Replicas

A real Spring Boot app often runs on Kubernetes:

~~~text
Primary quota account
      ^
      |
  +---+----+----+
  |        |    |
Pod 1    Pod 2 Pod 3
  |        |    |
local    local local
limiter  limiter limiter
~~~

If each pod has a `4 recipients/second` bucket, total traffic can reach 12 recipients/second. **Rate limits per provider account must be enforced cluster-wide.**

Options:

1. **Single dispatcher per quota scope:** easy quota math, though needs HA and lease planning on dispatcher restarts.
2. **Redis atomic token bucket:** replicas take permits from a shared store via atomic scripts/transactions.
3. **Database-backed reservation:** deduct budget inside a transaction with row-level locks or optimistic concurrency.
4. **Distributed rate-limiter library:** pick an implementation supporting atomicity and required quota scopes.
5. **Static share per replica:** works only when replica counts and other senders are controlled; autoscaling can breach quotas.

**Separate Redis GET then Redis SET is insufficient**:

~~~text
Bucket remaining = 1
Worker A reads 1
Worker B reads 1
Worker A sends
Worker B sends

2 submissions consumed a 1-token budget.
~~~

Check and deduct tokens **in one atomic operation**, while managing clocks, TTLs, failover, and bucket initialization on restarts.

### An Interface for a Quota Gate

~~~java
import java.time.Duration;

public record QuotaDecision(
        boolean allowed,
        Duration retryAfter,
        String reason) {
}

public interface ProviderQuotaGate {
    QuotaDecision reserve(
            String quotaScopeKey,
            MailQuotaCost cost);
}
~~~

`ProviderQuotaGate` is an application-built interface. It is not built into `JavaMailSender`. `quotaScopeKey` names a configured account/provider policy, not a raw email or credential.

When one send must pass multiple limits (account daily budget, credential rate, sender rate), reservation must be **coordinated/atomic** or have a designed compensation mechanism. Never deduct bucket A then bucket B naively so that if B denies, A stays consumed forever.

## 20. Database-Backed Quota Budgets for Provider Accounts

If the app already has an outbox and PostgreSQL, you can persist quota windows per scope:

~~~sql
CREATE TABLE mail_provider_quota_window (
    quota_scope_key VARCHAR(150) NOT NULL,
    window_start TIMESTAMPTZ NOT NULL,
    window_end TIMESTAMPTZ NOT NULL,
    quota_unit VARCHAR(30) NOT NULL,
    capacity BIGINT NOT NULL CHECK (capacity > 0),
    reserved BIGINT NOT NULL DEFAULT 0
        CHECK (reserved >= 0),
    PRIMARY KEY (
        quota_scope_key,
        quota_unit,
        window_start
    ),
    CHECK (window_end > window_start)
);
~~~

Conditional reservation:

~~~sql
UPDATE mail_provider_quota_window
SET reserved = reserved + :cost
WHERE quota_scope_key = :quota_scope_key
  AND quota_unit = :quota_unit
  AND window_start = :window_start
  AND reserved + :cost <= capacity
RETURNING reserved;
~~~

If one row returns, reservation succeeded. If zero rows return, either budget is exhausted or the key/window does not exist; the app must tell them apart rather than assuming quota remains.

PostgreSQL updates the same row inside a transaction using row-level locking, preventing two workers from trivially bypassing `reserved + :cost <= capacity`. However:

- Windows must be initialized cleanly without races.
- If the provider uses a rolling window, this calendar-window table is **not enough**.
- If external systems also send under the same provider account, internal counters miss that usage.
- Never hold a DB transaction open across `JavaMailSender.send(...)`.
- If a worker dies after reserving yet before sending, a bit of virtual budget is lost; manage that trade-off and never refund quota when SMTP outcome is still uncertain.

### Credential Rotation Must Not Reset Daily Quotas

If the quota scope is the account, changing `credentialId` from version 1 to version 2 **does not reset account quota to 0**. Counters must key on stable `quotaScopeKey`, never on password version so you don't accidentally reset the whole budget.

## 21. Daily Quotas: Counting the Right Provider and Reset Cycle

For daily quotas, define at least:

- `quotaScopeKey`: which account, tenant, or pool shares the limit.
- `quotaUnit`: recipients, messages, API requests, or bytes.
- `windowType`: calendar day, rolling 24h, or custom.
- `timezone/resetAt`: provider-specified reset moment.
- `capacity`: contractual cap or **safe operating budget**.
- `usageSource`: internal counter or provider usage API.
- `reconciliationLag`: how far provider reporting lags behind real time.

Hypothetical example:

~~~text
PRIMARY_PROD_ACCOUNT:
  daily recipient quota  = 20,000
  already reserved       = 17,600
  available safe budget  = 2,400

SECONDARY_PROD_ACCOUNT:
  daily recipient quota  = 5,000
  already reserved       = 700
  available safe budget  = 4,300
~~~

Do not add `2,400 + 4,300` and treat the sum as one pool if routes only allow different mail categories or sender identity is not verified on both providers.

### Hard Caps and Soft Caps

You can maintain:

- **Hard cap:** never exceed the vendor-enforced ceiling.
- **Safe cap:** a lower threshold leaving headroom for drift, traffic from other systems, or provider fluctuations.
- **Lane reservation:** reserving capacity for security/transactional mail.

Headroom is an operational, data-driven decision; no fixed percentage suits every account.

### When Daily Quota Is Exhausted

Instead of hammering SMTP continuously:

1. Deny admission for new jobs in that quota scope.
2. Reschedule jobs to `available_at` aligned with reset or next recheck.
3. Keep sending intent durably in the outbox/broker.
4. Monitor backlog age by notification type.
5. Drop jobs past their business deadline.
6. Use provider B only if the route is approved, B has quota, and the message was not accepted by A.

An "end of day" counter must not reset at local midnight if the provider uses a rolling 24-hour window or a different reset time.

## 22. Outbox Structure Preserving Multi-Route Context

Critical emails should not be lost just because a provider hits quota or a process restarts. Persist the mail intent:

~~~sql
CREATE TABLE mail_outbox (
    id UUID PRIMARY KEY,
    notification_type VARCHAR(80) NOT NULL,
    sender_profile_id VARCHAR(80) NOT NULL,
    preferred_provider VARCHAR(40),
    selected_provider VARCHAR(40),
    provider_account_id VARCHAR(100),
    recipient_ref VARCHAR(100) NOT NULL,
    payload_ref VARCHAR(200) NOT NULL,
    status VARCHAR(30) NOT NULL,
    attempt_count INT NOT NULL DEFAULT 0,
    available_at TIMESTAMPTZ NOT NULL,
    expires_at TIMESTAMPTZ,
    lease_until TIMESTAMPTZ,
    claim_token UUID,
    last_error_code VARCHAR(60),
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);
~~~

This is an illustrative schema, not mandatory. For multi-provider needs, separate:

- **Preferred/eligible provider list:** routes allowed by policy.
- **Selected provider:** route chosen for the current send.
- **Attempt history:** provider/attempt/outcome per submission trial.
- **Quota reservation:** reservation ID, quota scope, and cost, containing no credentials.
- **Recipient/payload:** stored in protected tables/objects; never dumped to logs.

### Attempt History Table

~~~sql
CREATE TABLE mail_submission_attempt (
    id UUID PRIMARY KEY,
    mail_job_id UUID NOT NULL REFERENCES mail_outbox(id),
    provider_id VARCHAR(40) NOT NULL,
    provider_account_id VARCHAR(100) NOT NULL,
    route_version VARCHAR(60) NOT NULL,
    attempt_number INT NOT NULL,
    started_at TIMESTAMPTZ NOT NULL,
    finished_at TIMESTAMPTZ,
    outcome VARCHAR(30),
    error_code VARCHAR(60),
    UNIQUE (mail_job_id, attempt_number)
);
~~~

Recording `providerId` and `routeVersion` in attempt records supports tracing after credential changes or route switches without storing passwords/tokens.

### Claim in Small Batches

A worker should claim only as many jobs as it can genuinely handle soon, never pulling the entire backlog into an in-memory queue:

~~~text
100,000 pending jobs
     |
     v
Small batch of ready jobs
     |
     v
Check route and capacity
     |
     +-- no quota -> defer
     |
     +-- permit -> SMTP submit
~~~

If quota is only 5 mails/second, claiming 100,000 jobs into an executor causes RAM pressure, lease expirations, and potential duplicate work across replicas.

## 23. Separate "No Permit Yet" from "SMTP Send Failed"

When the quota gate denies admission:

~~~text
mail_job.status = WAITING_PROVIDER_QUOTA
mail_job.available_at = next_allowed_time
mail_job.attempt_count unchanged
~~~

Do not increment `SMTP attempt_count` because the provider was never called. Conversely, once SMTP starts:

~~~text
mail_submission_attempt:
  provider = PRIMARY
  outcome  = ACCEPTED / REJECTED / UNKNOWN
~~~

State machine example:

~~~mermaid
flowchart TD
    A[PENDING] --> B[Claim job]
    B --> C{Allowed provider route?}
    C -- No --> D[BLOCKED_POLICY]
    C -- Yes --> E{Quota and concurrency?}
    E -- No --> F[WAITING_QUOTA]
    F --> A
    E -- Yes --> G[SMTP submission]
    G --> H{Outcome}
    H -- Accepted --> I[SUBMITTED]
    H -- Temporary reject --> J[RETRY_LATER]
    H -- Permanent reject --> K[FAILED_PERMANENT]
    H -- Unknown --> L[UNKNOWN_OUTCOME]
    J --> A
~~~

`WAITING_QUOTA`, `BLOCKED_POLICY`, and the other states are suggested business enums, not built into Spring Mail.

### Mark SUBMITTED Only with Evidence

`JavaMailSender.send(...)` succeeding means the application observed SMTP submission completing—**not a guarantee the email reached the inbox**. Providers can bounce or receivers can filter later.

If the connection drops after DATA and before the final reply, the client cannot tell whether the provider accepted. Marking `FAILED_SAFE_TO_RETRY` and resending immediately via provider B can create two emails.

## 24. Route by Policy and Eligibility, Not Quota Alone

A provider should receive a job only if all hold:

1. Provider is authorized for the notification type/tenant and environment.
2. Sender identity/domain is verified on that provider.
3. Content type, data class, and region are permitted by policy.
4. Credentials/config are currently usable.
5. Quota remains and circuit/health policy allows.
6. Prior attempt outcome is not in an uncertain state.

A route enum:

~~~java
public enum NotificationClass {
    SECURITY,
    TRANSACTIONAL,
    SUBSCRIPTION
}

public record RouteRequest(
        String tenantId,
        NotificationClass notificationClass,
        String senderProfileId) {
}

public interface MailRoutingPolicy {
    java.util.List<ProviderId> eligibleRoutes(
            RouteRequest request);
}
~~~

`eligibleRoutes(...)` must return a server-approved list, never trusting an arbitrary client-supplied provider parameter. For multi-tenant apps, policy must resolve which senders/accounts the tenant is allowed to use before checking quotas.

### Route Order and Provider Weights

You can choose:

- Primary-first, secondary only when primary is unavailable.
- Weighted 90/10 split during migrations.
- Separating security and subscription emails onto different providers.
- Region-based routing per data-handling requirements.

Still, **weighted routing does not enforce quotas by itself**, and every weight shift can affect reputation, sender authentication, and provider traffic profiles.

## 25. Example Route Dispatcher with Sender Registry and Quota Gate

This is an illustrative skeleton emphasizing processing order. It is not a complete production module, as it still needs transactions/leases/transport classification.

~~~java
import jakarta.mail.internet.MimeMessage;
import java.time.Duration;
import org.springframework.mail.MailException;

public final class MultiProviderDispatcher {
    private final MailRoutingPolicy routingPolicy;
    private final ProviderSenderRegistry senders;
    private final ProviderQuotaGate quotas;
    private final MailJobRepository jobs;
    private final MailMessageFactory messages;

    public MultiProviderDispatcher(
            MailRoutingPolicy routingPolicy,
            ProviderSenderRegistry senders,
            ProviderQuotaGate quotas,
            MailJobRepository jobs,
            MailMessageFactory messages) {
        this.routingPolicy = routingPolicy;
        this.senders = senders;
        this.quotas = quotas;
        this.jobs = jobs;
        this.messages = messages;
    }

    public void dispatch(ClaimedMailJob job) {
        var eligible = routingPolicy.eligibleRoutes(
                job.routeRequest());

        if (eligible.isEmpty()) {
            jobs.blockByPolicy(job.id());
            return;
        }

        // Actual route selection must consider health and attempt history.
        ProviderId provider = eligible.get(0);
        ProviderRoutePolicy profile = job.policyFor(provider);

        MailQuotaCost cost = job.quotaCost();
        QuotaDecision decision = quotas.reserve(
                profile.quotaScopeKey(), cost);

        if (!decision.allowed()) {
            jobs.defer(
                    job.id(),
                    decision.retryAfter(),
                    "WAITING_PROVIDER_QUOTA");
            return;
        }

        try {
            var sender = senders.resolve(provider);
            MimeMessage message =
                    messages.compose(sender, job, profile);
            sender.send(message);
            jobs.markSubmitted(job.id(), provider);
        } catch (MailException ex) {
            jobs.recordSubmissionFailure(
                    job.id(), provider,
                    SafeMailErrorClassifier.classify(ex));
        } catch (Exception ex) {
            jobs.recordPreparationFailure(job.id(), provider);
        }
    }
}
~~~

`ClaimedMailJob`, `MailJobRepository`, `MailMessageFactory`, and `SafeMailErrorClassifier` are application-defined abstractions. `ProviderQuotaGate.reserve(...)` must enforce coordinated limits per real policy; `MailQuotaCost` was described earlier.

In production:

- Validate recipient, expiry, consent, and tenant/sender authorization before requesting a permit.
- Acquire a concurrency slot and release it in `finally`.
- Check `claim_token` on every state update.
- Never lump job-status save errors together with composition errors in one `catch(Exception)`; keep phases separate so outcomes are never misrecorded.
- Never refund a permit when it is unknown whether the provider already counted quota.
- If `send(...)` yields an UNKNOWN outcome, never record it as a safe-to-fail-over error.
- Design handling for when `jobs.markSubmitted(...)` fails after SMTP acceptance.

**Explicit limitations of this example:** it shows resolving routes, acquiring separate quotas, and picking matching senders; exactly-once semantics, distributed transactions, and safe retries require additional architecture.

## 26. Ordering Compose vs. Reserve Quota

A design question: should you build `MimeMessage` before or after acquiring a permit?

| Approach | Pros | Risks |
|---|---|---|
| Compose before reserve | Lets you compute raw MIME size and validate early | Wastes CPU/IO on jobs not yet allowed to send |
| Reserve before compose | Avoids rendering batches when quota is exhausted | Composition failures can waste quota reservations |
| Preflight then reserve, compose last | Catches obvious errors while saving CPU | Final raw MIME size may differ from estimate |

A hybrid workflow:

1. Preflight recipient, sender, size policy, and required resources.
2. Compute message/recipient cost by envelope.
3. For providers with hard size caps, compose/serialize early if needed to measure exact size before submitting.
4. Request quota admission for the exact cost.
5. Compose/serialize if not yet done and start SMTP while the permit lease is valid.
6. Account for the outcome per designed semantics.

If a quota reservation is granted and sits unused too long (in an executor queue), actual submission rates can drift from policy. Issue short-lived permits **close to actual sending**, never reserving 10,000 tokens for a backlog and burning them over hours outside the rate window.

### SMTP Accepted Is Not Delivered

Metrics like `mail_submission_accepted_total` reflect only provider acceptance; delivery and bounces require provider-appropriate webhooks/DSNs/message traces. If provider A accepts and later bounces, shifting the same job immediately to B is a very different business decision from retrying an SMTP temporary rejection.

## 27. Retry by Per-Provider Error, Never One Blanket Policy

When Provider A rejects a send, not every failure allows retry or failover:

| Outcome | Meaning | Handling |
|---|---|---|
| Invalid recipient syntax | Bad input data | Reject/fix data; do not retry another provider |
| Sender not authorized | `From` unauthorized at A | Fix sender policy; B only if route is eligible |
| SMTP AUTH rejected | A credentials wrong/revoked | Pause route A, inspect secrets/tokens |
| Quota/rate throttled | Provider A temporarily limiting | Defer per quota and backoff; keep job |
| SMTP temporary rejection pre-accept | Not accepted per available evidence | Retry with backoff when policy allows |
| SMTP permanent rejection | Rejected per response | Never blindly retry; classify root cause |
| Network failure before connecting | Submission never happened | May retry/fail over per policy |
| Connection lost after DATA | Outcome may be unknown | `UNKNOWN` state; avoid automatic resend |
| SMTP accepted | Provider took processing responsibility | Mark `SUBMITTED`; track delivery separately |
| HTTP API 429 | API rate limit | Honor `Retry-After` if provided, per vendor |

**SMTP has no universal HTTP 429 code.** It uses SMTP replies like `421`, `450`, `451`, `452` and enhanced status codes depending on context/provider. Not every SMTP 4xx means "out of quota," and not every `MailSendException` is safe to retry.

### Never Log Raw Provider Exceptions

SMTP servers can echo recipients in responses:

~~~text
451 4.7.0 Temporarily throttled recipient <user@example.net>
~~~

Operational logs should look like:

~~~text
event=mail_submission_failure
jobId=mail-job-381
provider=PRIMARY
providerAccount=PRIMARY_PROD_ACCOUNT
failureCode=RATE_THROTTLED
attempt=2
~~~

Never log raw passwords, tokens, subjects, recipient addresses, or full MIME messages. Beyond security, logging normalized codes makes it easier to compare errors across two vendors with different response formats.

## 28. Exponential Backoff, Jitter, and Quota Windows

When 10,000 jobs are rejected together by Provider A, never schedule them all to retry in exactly 1 second. That triggers a **retry storm**:

~~~text
Provider throttle → 10,000 jobs retry after 1s
                       |
                       v
          10,000 requests arrive together
                       |
                       v
             Provider throttles again
~~~

A formula:

\[
d_n = \min(d_{\max}, d_0 \cdot 2^{n-1})
\]

`n` is consecutive failure count; `d0` is base delay, `dmax` is ceiling. Add jitter:

\[
d_{\text{retry}} \sim U(0,d_n)
\]

If near-zero delays are undesirable, add a minimum wait or use a floored jitter variant.

### Combining Backoff with Quotas

When a job becomes eligible to retry must be no earlier than all applicable constraints:

~~~text
nextAttemptAt =
  max(
    providerRateLimiterNextPermit,
    providerDailyQuotaResetOrRecheck,
    temporaryErrorBackoff,
    providerRetryAfterIfAvailable
  )
~~~

`Retry-After` is an **HTTP** mechanism suited to providers with HTTPS email APIs. SMTP has no universal HTTP-style `Retry-After` header; read response codes and provider documentation.

When a job comes due, the dispatcher **still requests a permit**. Waiting out backoff does not guarantee provider quota is available.

### Per-Category Deadlines

OTPs may stay valid for only a few minutes; marketing emails can have longer sending windows. Once `expires_at` passes, never send an expired OTP just because quota finally opened up.

~~~java
if (job.expiresAt() != null
        && !clock.instant().isBefore(job.expiresAt())) {
    jobStore.markExpired(job.id());
    return;
}
~~~

`clock` and `jobStore` are application-defined dependencies. Never apply one shared retry deadline to every notification type.

## 29. Failover Between Two Providers Does Not Guarantee Exactly-Once

A critical scenario:

~~~text
Job J
  |
  +-- Provider A:
  |      SMTP DATA accepted by server
  |      connection drops before client sees final reply
  |
  +-- Client observes timeout
  |
  +-- Immediate retry to Provider B
         |
         +-- B accepts

Result: recipient may receive two emails.
~~~

Because SMTP delivery and database transactions do not share one atomic commit, applications generally cannot prove **exactly-once email delivery** via an outbox or request ID alone.

Mitigations:

- Record `attemptId` and `Message-ID` or provider message IDs when available by design.
- Distinguish `UNKNOWN_OUTCOME` from rejections proven pre-acceptance.
- Reconcile against provider submission audits/message traces when feasible.
- For duplicate-tolerant notifications, design idempotent content/business actions.
- For sensitive emails or ones with duplicate side effects, enforce manual decision/reconciliation policies.
- Never automatically treat connection timeouts as "definitely not sent."

**`Message-ID` does not stop providers from sending duplicates**, and receivers have no obligation to deduplicate by `Message-ID`. It is a useful correlation signal, not an exactly-once guarantee.

### Failover Must Respect B's Quota as a Fresh Send

If A is throttled, B may still have quota. Shifting a job to B requires:

1. B is in the job's `eligibleRoutes`.
2. B has valid sender permissions and policies.
3. B has remaining rate/daily budget and concurrency capacity.
4. No unresolved `UNKNOWN` state poses duplicate risk.
5. Attempt history records the route switch.

Never pull out credential B just to "route around" A's limit when sending behavior violates anti-abuse policies.

## 30. Separating Priority for Security and Marketing Emails

A multi-provider system typically sends categories with differing needs:

| Lane | Examples | Characteristics |
|---|---|---|
| SECURITY | OTPs, unusual login alerts | Short deadlines, needs priority |
| TRANSACTIONAL | Invoices, order confirmations | Needs reliability and auditing |
| SUBSCRIPTION | Newsletters, subscribed updates | Schedulable and smoothable |
| BULK_CAMPAIGN | Authorized marketing campaigns | Large bursts, requires consent/suppression |

If all of them share one provider account quota, a campaign can burn the budget and delay OTPs. You can:

- Separate providers/accounts/credentials per lane when policy genuinely grants independent quotas.
- Reserve dedicated budget for priority mail.
- Use weighted fair queueing across lanes.
- Pause campaigns when quota drops low or a provider degrades.
- Set deadlines on time-sensitive jobs and skip them once expired.

**Creating a new credential on the same account does not automatically increase quota.** Verify at what level the provider enforces limits before deciding to split accounts.

### Fairness Across Multiple Tenants

If multiple enterprise customers share one provider account, one tenant can monopolize capacity. A two-tier policy:

~~~text
Global account quota
         |
         +-- Tenant A fair share
         +-- Tenant B fair share
         +-- Tenant C fair share
         |
         +-- Security reserved lane
~~~

Tenant quotas only **partition** remaining capacity; they do not manufacture extra provider quota. Unused tenant shares can be lent to others under explicit policy to prevent starvation while staying under the global cap.

## 31. Monitoring by Provider, Account, Lane, and Quota Scope

A multi-provider system must answer:

- Which providers are currently used, and in what proportions?
- On which accounts are credential/auth errors occurring?
- How much quota remains per scope and when does it reset?
- Is any provider throttling more heavily?
- How many jobs are waiting on quota vs. waiting on transport failures?
- Is failover increasing duplicates/`UNKNOWN` counts?
- Does the OTP lane stay within SLA during campaigns?

Useful metrics:

| Metric | Purpose |
|---|---|
| `mail_submission_total` | Attempts/accepted/rejected counts by provider |
| `mail_provider_auth_failure_total` | Detect wrong/expired credentials |
| `mail_provider_throttle_total` | Throttling rate per provider/account |
| `mail_provider_quota_remaining` | Estimated remaining budget, possibly lagged |
| `mail_quota_reservation_denied_total` | Jobs held back by quota |
| `mail_outbox_pending` | Backlog by lane/provider |
| `mail_outbox_oldest_age_seconds` | Longest wait time compared against SLA |
| `mail_submission_duration_seconds` | Submission latency p50/p95/p99 |
| `mail_provider_failover_total` | Jobs routed to backup |
| `mail_submission_unknown_total` | Attempts with uncertain outcome |
| `mail_credential_rotation_failure_total` | Failures during secret rotation |
| `mail_quota_gate_error_total` | Redis/DB quota service errors |

### Metric Labels Must Be Low Cardinality

Use bounded values:

~~~text
provider=PRIMARY
account=PROD_ORDERS
lane=TRANSACTIONAL
outcome=THROTTLED
~~~

Never use:

~~~text
recipient=user@example.net
passwordVersionSecret=...
jobId=unique-for-every-message
subject="Invoice #12345 for Alice"
~~~

Recipients are PII; `jobId` is high cardinality; secrets must never be logged; subjects can hold sensitive details. Use job IDs in access-controlled logs/traces, never as metric labels.

### Alert on Impact

Examples:

- Primary authentication failures spike after secret rotation.
- Secondary quota nears exhaustion despite being a backup route.
- Provider A throttling persists and `mail_outbox_oldest_age_seconds` climbs.
- Console account usage climbs without matching app submission logs—another system may be sharing the credential/account.
- Fallback rate surges unexpectedly after a new deployment.
- OTP backlog breaches targets while campaigns keep sending.

Do not alert only on high SMTP error rates. A limiter can be **working exactly as designed** while backlogs still grow because incoming job volume exceeds quota; operations still needs to intervene.

## 32. Unit Test: Selecting the Right JavaMailSender per Provider

With two `JavaMailSender` beans, a wiring bug can make the secondary route use the primary sender. Test the registry with Mockito:

~~~java
import static org.assertj.core.api.Assertions.assertThat;
import static org.mockito.Mockito.mock;

import org.junit.jupiter.api.Test;
import org.springframework.mail.javamail.JavaMailSender;

class ProviderSenderRegistryTest {

    @Test
    void resolvesDistinctSendersForEachRoute() {
        JavaMailSender primary =
                mock(JavaMailSender.class);
        JavaMailSender secondary =
                mock(JavaMailSender.class);

        ProviderSenderRegistry registry =
                new ProviderSenderRegistry(
                        primary, secondary);

        assertThat(registry.resolve(ProviderId.PRIMARY))
                .isSameAs(primary);
        assertThat(registry.resolve(ProviderId.SECONDARY))
                .isSameAs(secondary);
        assertThat(registry.resolve(ProviderId.PRIMARY))
                .isNotSameAs(
                        registry.resolve(ProviderId.SECONDARY));
    }
}
~~~

This test checks registry logic, **not** whether Spring injected the right qualifiers into both beans. To test real wiring, use `@SpringBootTest` or a context slice with test configuration containing no real secrets.

### Testing That the Other Provider's Send Is Never Called

In service/dispatcher tests:

~~~java
import static org.mockito.Mockito.never;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.verifyNoInteractions;
import static org.mockito.ArgumentMatchers.any;

// When policy allows only PRIMARY:
dispatcher.dispatch(job);

verify(primary).send(any(jakarta.mail.internet.MimeMessage.class));
verifyNoInteractions(secondary);
~~~

This assertion skeleton relies on project-defined test fixtures and mocked `dispatcher`, `primary`, and `secondary`. When an app has backup logic, explicitly configure failure/route policies and confirm **only** approved branches execute.

## 33. Testing Credential Isolation and Configuration Protection

Unit tests must never contain production secrets. For test config:

~~~text
PRIMARY_USERNAME=test-primary-user
PRIMARY_PASSWORD=fake-primary-password
SECONDARY_USERNAME=test-secondary-user
SECONDARY_PASSWORD=fake-secondary-password
~~~

Tests should verify:

1. The primary bean receives primary's test host/port/username.
2. The secondary bean receives secondary's values.
3. Both apply their configured TLS policies.
4. A profile missing secrets fails fast before accepting jobs.
5. `toString()` on configuration objects or logging never exposes passwords/tokens.
6. An SMTP auth failure on A never mutates B's password.
7. Route profiles hold only secret **references/versions**, never raw secrets in outbox or job logs.

Example bean-properties test:

~~~java
import static org.assertj.core.api.Assertions.assertThat;

import org.junit.jupiter.api.Test;
import org.springframework.mail.javamail.JavaMailSenderImpl;

class MultiSenderConfigurationTest {
    @Test
    void keepsTwoProviderConnectionsSeparate() {
        var configs = new MultiProviderMailProperties(
                new MultiProviderMailProperties.SmtpEndpoint(
                        "smtp-a.example.test", 587,
                        "user-a", "fake-a",
                        "orders@example.com", true, true, 2),
                new MultiProviderMailProperties.SmtpEndpoint(
                        "smtp-b.example.test", 587,
                        "user-b", "fake-b",
                        "orders@example.com", true, true, 3));

        MultiProviderMailConfiguration factory =
                new MultiProviderMailConfiguration();
        JavaMailSenderImpl a = (JavaMailSenderImpl)
                factory.primaryMailSender(configs);
        JavaMailSenderImpl b = (JavaMailSenderImpl)
                factory.secondaryMailSender(configs);

        assertThat(a.getHost()).isEqualTo("smtp-a.example.test");
        assertThat(b.getHost()).isEqualTo("smtp-b.example.test");
        assertThat(a.getUsername()).isEqualTo("user-a");
        assertThat(b.getUsername()).isEqualTo("user-b");
        assertThat(a.getPassword()).isNotEqualTo(b.getPassword());
    }
}
~~~

This is a factory test making no SMTP connections. Inspecting `getPassword()` in a dummy test fixture does not mean production code may log or expose passwords.

### Rotation Tests Must Verify New Connections

When rotating secrets, a config test can confirm a new instance builds with the new secret version. However, an already-authenticated old SMTP connection may keep working; add integration tests against a sandbox provider/test double verifying new connections use the new credential and the old credential is revoked per policy.

## 34. Testing Independent Quotas and Shared Quotas

Two critical scenarios:

### Case A: Two Providers with Independent Quotas

~~~text
Primary remaining = 1
Secondary remaining = 3

Reserve cost 1 for PRIMARY
  -> Primary remaining = 0
  -> Secondary remains 3

Reserve cost 1 for SECONDARY
  -> Secondary remaining = 2
~~~

Tests must verify that using provider A **does not consume B's budget** when the two scopes are genuinely independent.

### Case B: Two Credentials Sharing One Account Quota

~~~text
Account quota remaining = 1
Credential ORDER uses account PRIMARY_PROD
Credential SECURITY uses account PRIMARY_PROD

Both request 1 permit concurrently:
    exactly one granted
    one denied
~~~

Tests must verify the quota key is the **account scope**, not credential ID. When two workers both see one token, reservation must be atomic.

### Multi-Replica Testing

A distributed-limiter integration test can simulate 100 concurrent workers each requesting 1 token from a bucket of capacity 10 within a non-refilling window:

~~~text
Expected:
    10 grants
    90 denials
    total reserved = 10
~~~

Do not test multi-replica behavior using only each instance's local in-memory limiter. Inspect shared store state after reservations and ensure deterministic clocks/windows in tests.

### Testing Quotas by Recipient and Window

Other cases:

| ID | Condition | Expected outcome |
|---|---|---|
| QT-01 | 1 message, 1 recipient | Deduct exact cost |
| QT-02 | 1 message, 20 recipients | Deduct 20 from recipient quota, 1 from message quota |
| QT-03 | Message exceeds max recipients | Reject/split per policy pre-send |
| QT-04 | Cost exceeds burst capacity | Catch bad config/admission; do not wait forever |
| QT-05 | Primary exhausted, secondary has quota | Route B only when eligible and A's outcome is safe |
| QT-06 | Both exhausted | Jobs stay in durable outbox |
| QT-07 | Rotate credentials on same account | Account quota does not reset |
| QT-08 | Provider uses rolling 24h | Do not reset wrongly at calendar midnight |
| QT-09 | Distributed store times out | No uncontrolled fail-open |
| QT-10 | Worker crashes after reserve | Reservation and job state recover per policy |
| QT-11 | Auth failure on A | Only A degrades/pauses; B untouched |
| QT-12 | Multi-tenant sharing one account | Aggregate quota enforced, per-tenant fairness |

## 35. Integration Testing with SMTP Sinks and Provider Sandboxes

Unit tests verify bean/route/quota algorithms; integration tests are needed to prove the right credentials are actually used on the SMTP wire.

A test topology:

~~~text
App under test
        |
        +-- PRIMARY   -> SMTP sink A / test port A
        |
        +-- SECONDARY -> SMTP sink B / test port B
~~~

Scenarios:

1. Send a PRIMARY-routed job; verify sink A receives it and sink B does not.
2. Send a SECONDARY-routed job; verify the reverse.
3. Simulate SMTP AUTH failure on A; verify A's state and retry/failover per policy.
4. Simulate temporary 4xx; verify job defers without a retry storm.
5. Simulate B quota exhaustion; verify routing never pushes past B's limit.
6. Simulate connection drop after DATA; verify outcome `UNKNOWN` instead of auto-retrying across A and B.
7. Verify `From` sender and MIME across route switches.
8. Verify test accounts lack mailbox-read or ungranted Send As permissions under provider-specific policies.

An SMTP sink like Mailpit or GreenMail captures messages without sending to real recipients. However, simple sinks do not simulate real quotas. Use a test double capable of actively returning SMTP codes/holding connections, or an approved provider sandbox for auth/throttling scenarios.

**Never intentionally blow past production quotas or generate spam to "verify" correctness.** Rate/credential tests must use test accounts and dummy addresses.

## 36. Controlling Secret Access in CI/CD and Runtime

Managing separate credentials does not stop at setting two environment variables. Govern the entire lifecycle:

| Stage | Risk | Control |
|---|---|---|
| Development | Developers copy production keys to laptops | Use sandbox credentials; grant no production access |
| Build | Secrets embedded in source/image layers | Never inject secrets at build time unless needed |
| CI tests | Printing configs/stack traces exposing passwords | Fake secrets, masking, and log policies |
| Deploy | Secrets attached to the wrong environment | Scope by workload/namespace, require approvals |
| Runtime | Pod/service reads another provider's key | RBAC/secret mounts scoped to the required workload |
| Rotation | Old key remains active | Audit, revoke, and verify |
| Incident | Exports/backups store raw credentials | Access controls, retention, encryption |
| Decommission | Stale credentials/profiles linger | Revoke keys, stop queues/routes, remove permissions |

### Workload Identity and Namespaces

Where possible, mount/inject Provider B's secret only into workers authorized to send via B. If all provider credentials live inside one process, that process can reach every route; that design can be acceptable when the router is trusted, yet must be treated as a **high-value workload** with proper audits, least privilege, and network egress rules.

Under strict isolation requirements, deploy **separate dispatcher processes per provider** instead of one monolith holding every secret.

## 37. When to Split Provider Adapters into Separate Services?

In small applications, two `JavaMailSender` beans suffice. At larger scale, an independent sender service per provider has advantages:

~~~text
Shared notification / outbox service
                    |
            Approved route policy
                    |
             Internal broker
             /             \
            v               v
    Provider A worker   Provider B worker
    A secret only       B secret only
    A quota only        B quota only
            |               |
            v               v
          SMTP A          SMTP B
~~~

Benefits:

- Workload A does not need to read credential B.
- Provider-specific libraries/token refresh stay out of the main app.
- Failures or dependency outages on A stay isolated.
- Per-provider quota admission and connection pools become easier to measure.
- Workers can scale independently by each route's throughput/latency.

Trade-offs:

- More services, deployments, queues, and monitoring to operate.
- Requires shared idempotency, attempt history, and routing state.
- Provider switching can still produce duplicates when outcomes are unclear.
- Can complicate enforcing one account quota shared across multiple worker services.

Do not split into microservices merely because you have two SMTP passwords. Scale, blast radius, compliance, and operational needs decide.

## 38. Runbook When a Provider Has an Incident

### Scenario A: Primary Authentication Starts Failing

Example:

~~~text
PRIMARY auth failures UP
SECONDARY healthy
ORDER_RECEIPT backlog age UP
~~~

Response steps:

1. Inspect provider A, account/credential, and when errors began.
2. Check secret rotation schedules, deployments, OAuth scope changes, or SMTP AUTH policy updates.
3. Never log/paste passwords or raw access tokens into incident tickets.
4. Pause A if continuing to send only produces auth failures.
5. Check whether B has route eligibility, sender verification, quota, and valid permissions.
6. Move only jobs whose outcomes were never accepted and are not `UNKNOWN` per policy.
7. Fix A's secret/config, test a fresh connection, then ramp back up gradually.
8. Reconcile attempt counts and queue states to avoid drops or duplicates.

### Scenario B: Primary Quota Exhausts Early

~~~text
PRIMARY daily recipient quota remaining = 0
SECONDARY account quota remaining > 0
Outbox pending = 12,000
~~~

Do not immediately dump 12,000 jobs onto B:

- Verify B's policy allows this content category.
- Verify B's real quota and account/sender scope.
- Check which jobs were already accepted through A.
- Reserve budget for critical emails; pause lower-priority lanes if needed.
- Schedule sends within B's capacity rather than flooding B in one burst.
- Watch B's errors/complaints/reputation after rerouting.

### Scenario C: Quota Store (Redis/DB) Fails

The default for non-urgent workloads can be **fail closed**: hold sending, keep in outbox. For critical emails, use a **pre-approved** bounded fallback with a cluster-wide cap. Never let every replica bypass the quota gate and send unbounded.

### Scenario D: Suspected Credential Compromise

- Disable or revoke the affected secret.
- Reconcile provider submission audits against legitimate jobs.
- Check provider-side Send As, mailbox/API grants, and IP allowlists.
- Issue a new secret with least privilege.
- Never let other routes inherit broader permissions.
- Track and manage backlog during the sending pause.

## 39. Anti-Patterns in Multi-Provider Credential and Quota Management

### 39.1. One SMTP Username/Password for All Providers

Each provider/account needs its own credentials. Never copy one password across routes: an exposure hits the whole system, and auth mechanisms can differ.

### 39.2. Sharing Admin Accounts Instead of Service Identities

An app that only sends mail needs no permission to read every mailbox or administer tenants. Use dedicated accounts with minimal grants.

### 39.3. Two JavaMailSender Beans Sharing a Global Credential

Two beans provide no isolation if they still point to one overly privileged secret. Inspect permissions and account scopes, not just class/bean names.

### 39.4. Mutating Host/Username/Password on a Singleton Between Requests

A multi-threaded race condition; can send down the wrong route or authenticate as the wrong identity. Use separate adapters/senders with stable configuration.

### 39.5. Letting Requests Pick Arbitrary SMTP Endpoints

Creates SSRF or relay-abuse risk. Clients must never pass host, port, credentials, and `From` unchecked.

### 39.6. Assuming a New API Key Grants New Quota

Providers may meter quota at the organization/account level. Identify the real `quotaScopeKey` and use shared counters.

### 39.7. One Shared Rate Limiter Across Independent Providers

A exhausting quota can block B even when B has spare capacity. Keep counters per true quota scope, alongside org-wide caps if they genuinely exist.

### 39.8. One Local Token Bucket per Pod on a Shared Account

As replicas scale up, total rate exceeds quota. Use a distributed limiter or centralized dispatcher.

### 39.9. Using maxPoolSize as a Rate Limit

Concurrent worker count is not messages/second or recipients/day. Keep rate quotas and concurrency gates separate.

### 39.10. Ignoring Cc/Bcc in Recipient Quotas

One send call can deliver to many envelope recipients. Meter in the unit the provider bills/enforces, not just `send` call counts.

### 39.11. Switching to Secondary Immediately After Every Exception

SMTP outcomes can be `UNKNOWN` and cause duplicates. Classify failure point/acceptance before failing over.

### 39.12. Not Verifying From Permissions on Secondary

An address verified on A is not guaranteed valid on B. B may reject or rewrite the sender; DKIM/SPF/DMARC must also be configured properly.

### 39.13. Storing Credentials Inside Outbox Jobs

Credentials can linger in databases and leak through logs/support exports. Outboxes hold only route/profile IDs and protected business data.

### 39.14. Resetting Quota Counters When Rotating Keys

Changing credential versions does not give the account a fresh budget. Quota keys must stay tied to quota scope.

### 39.15. Sending First, Checking Quota Later

Counting after `send(...)` already happened cannot prevent burst overruns. Reserve/acquire permits before submission; record outcomes separately afterward.

### 39.16. Refunding Every Permit on Any MailException

The provider may have counted quota or accepted the message even though the client saw an error. Refund only when provably safe and semantics are clear.

### 39.17. Applying an HTTP 429 Parser to Every SMTP Exception

HTTP email APIs and SMTP are different protocols. `Retry-After` belongs to HTTP, whereas SMTP uses provider-specific response/enhanced codes.

### 39.18. Claiming Tens of Thousands of Jobs into RAM When Quota Is Low

A backpressure bug: holds workers/leases and risks lost state on restarts. Use small batches, durable outboxes, and `available_at`.

### 39.19. Letting Marketing Drain the OTP Budget

Separate credentials/quotas exist to contain blast radius and protect critical mail. Never share an unprioritized budget across streams with differing SLAs.

### 39.20. Monitoring Only SMTP Errors Without Quota Denials

A properly working limiter can hold the entire backlog in the queue with zero SMTP errors. Monitor waiting age and accepted throughput alongside errors.

## 40. Rollout Process for Multiple Providers in a Spring App

A practical roadmap:

1. **Inventory sending paths:** providers, accounts, credentials, sender identities, domains, environments, and notification classes.
2. **Establish boundaries:** provider profile IDs and workloads authorized to read each secret.
3. **Verify senders:** From/Reply-To, Send As, domains, DKIM/SPF/DMARC at each provider.
4. **Gather real quotas:** message/recipient rates, daily budgets, reset windows, concurrency, size caps, and quota scopes.
5. **Store secrets securely:** secret manager, workload identity, rotation, revocation, audits.
6. **Build separate senders/adapters:** `JavaMailSender` with qualifiers for SMTP, separate HTTP adapters if using APIs.
7. **Define route policies:** only approved providers per tenant, category, and environment.
8. **Build quota gates:** shared/distributed when accounts are shared across replicas, with explicit units/costs.
9. **Add concurrency controls:** per provider/account, never conflated with rate.
10. **Create durable outbox:** store intents, route eligibility, attempt history, `available_at`, and expiry.
11. **Define retry/failover:** separate handling for throttling, permanent, temporary, and `UNKNOWN`.
12. **Protect critical lanes:** OTP, transactional, and newsletters with appropriate priorities/fairness and budgets.
13. **Add safe metrics and logs:** provider, route, version, quota, result, attempt, backlog; no raw secrets/recipients.
14. **Test:** wiring, fake credentials, quota isolation/shared scopes, multi-replica races, SMTP failures/failover.
15. **Roll out:** sandbox then small traffic, measuring accepted throughput, auth errors, quota burn, and bounces.
16. **Operate:** runbooks for revoke/rotate, provider outages, depleted quotas, and queue recovery.
17. **Decommission:** stop routes, drain or reroute valid jobs, revoke keys, remove permissions, and update quota docs.

### Deployment Completion Criteria

| Criterion | Technical evidence |
|---|---|
| Credentials A and B independent | Separate secret references and workload access |
| Scoped sender permissions | Exact provider verified sender / Send As grants |
| Right route per job | Route integration tests and attempt history |
| No wrong cross-quota usage | Unit/distributed integration tests for quota scopes |
| No lost emails on quota exhaustion | Durable queue + deferred state |
| Rotation does not break B | Sandbox rotation/drain test |
| Retries do not flood providers | Backoff, jitter, rate-gate admission |
| `UNKNOWN` outcomes handled | Job state and replay/failover policy |
| No password/token leaks | Secret scanning, log policy, CI reviews |
| Full operability | Dashboards, alerts, runbooks, and audits |

## 41. Frequently Asked Questions

**Can I use just one `spring.mail.*` with two providers?** Spring Boot normally auto-configures one default sender. With multiple SMTP routes, create separate explicitly configured `JavaMailSender` beans or adapters and use qualifiers/a registry.

**Do two `JavaMailSender` beans isolate quotas automatically?** No. Quotas are enforced by the provider per account/organization/credential/sender and must be coordinated by your dispatcher according to real scope.

**Does a new API key mean a fresh daily quota?** No. Multiple keys often share one account quota. Check provider policies.

**Should I grant one account permission to send from all domains?** Not by default. Least privilege and per-provider/profile sender verification reduce blast radius if a credential leaks.

**Can both providers use the same `From` address?** Yes, provided both are authorized to send from that address/domain and authentication/deliverability requirements are met.

**Should credentials go in `application.yml`?** Never store real values in source. Use placeholders resolved from a secret manager or runtime secret injection.

**Should SMTP passwords be passed into queue jobs to survive restarts?** No. Queues/outboxes should hold provider profile IDs and needed metadata; workers look up runtime-injected secrets.

**Does credential rotation reset provider quotas?** Not if quota scope is the account or organization. Counters must track the quota key, not the password.

**Does OAuth2 auto-refresh if I put a token into the password field?** No. Implement token acquisition and refresh according to token lifetimes and provider protocols; never deploy static expiring tokens.

**When Provider A runs out of quota, can I send via B?** Only if B is approved for that job, the sender is valid, B has quota, and A's prior outcome is clear enough to avoid duplicates.

**If a provider returns temporary 4xx, should I retry immediately?** No. Classify the error, apply backoff/jitter, and re-acquire permits; not every 4xx is a rate limit.

**Can `maxPoolSize=5` guarantee staying under 5 messages/second?** No. Pool size caps concurrent tasks, not sustained throughput rates.

**What must I do when multiple pods share one provider account?** Use a shared quota limiter/dispatcher or controlled cluster-wide quota partitioning. Independent local limiters are not enough.

**Why keep per-provider attempt history?** To know which routes a job tried, what outcomes occurred, and whether failover carries duplicate risk.

**If A succeeded yet the email is not in the inbox, should I resend via B?** Not automatically. SMTP acceptance does not guarantee inbox delivery, and retrying via B risks duplicates. Monitor bounces/delivery and follow explicit business policy.

**Should routing automatically pick the lowest-cost provider?** Only after satisfying sender authorization, consent, region/compliance, quotas, SLAs, and vendor policies. Price is never the sole criterion.

**How do I protect OTPs from marketing batches?** Isolate lanes/accounts when separate budgets exist, or reserve quota and prioritize dispatch on shared accounts.

**If the Redis limiter fails, should we send unbounded so OTPs aren't lost?** No. Fail closed or use a pre-designed bounded fallback with a cluster-wide cap while the outbox holds jobs until capacity returns.

**Should SMTP usernames/passwords be logged on auth failures?** No. Log only provider ID, account ID, config version, failure code, and safe job ID.

**What if a backup provider only offers an HTTP API instead of SMTP?** Use a matching adapter. `JavaMailSender` handles SMTP; HTTP email APIs use dedicated clients/adapters under the same routing/quota/outbox abstraction.

## 42. Summary

In **Spring Framework Mail** with multiple providers, **credentials and quotas must be managed as two independent yet related axes**:

- **Credentials** answer: under which identity does the app authenticate, which senders may it use, and who may read/rotate/revoke secrets?
- **Quotas** answer: which provider/account/sender is limited, in what unit, over which window, and how much capacity remains?

A complete architecture:

~~~text
Business command
     |
     v
Authorized notification intent
     |
     v
Durable outbox / attempt history
     |
     v
Route eligibility (tenant, type, sender)
     |
     +---------------------+
     |                     |
     v                     v
Provider A profile     Provider B profile
  - secret A             - secret B
  - allowed From A       - allowed From B
  - quota scope A        - quota scope B
  - rate/concurrency A   - rate/concurrency B
     |                     |
     v                     v
JavaMailSender A       JavaMailSender B
     |                     |
     +----------+----------+
                |
                v
       Outcome classification
       Accepted / Retry / Unknown
                |
                v
           Outbox state
~~~

**Key principles:**

1. Isolate secrets/providers/production environments and grant minimal sending permissions.
2. Never let clients dictate hosts, credentials, `From`, or unapproved providers.
3. Track quotas at their true scope; **never equate credential IDs with quota account IDs**.
4. Apply rate, daily quota, and concurrency controls in the right units, coordinated cluster-wide when shared.
5. Persist sending intent durably; lacking a permit means **not yet your turn to send**, not an SMTP error.
6. Rotation/failover must never wipe quota state or ignore `UNKNOWN` submission risks.
7. Monitor per provider/account/route/outcome and protect credentials/recipients in logs.

When boundaries are modeled properly, adding a new provider is more than configuring another SMTP host. It is onboarding an independently governed **domain of credentials, sender permissions, sending capacity, and operational accountability**, while all jobs remain consistently controlled by business policy and delivery state.
