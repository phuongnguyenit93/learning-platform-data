# Restricting Sending Account Permissions

## 1. Why must an SMTP account have least privilege?

In **Spring Framework Mail**, applications commonly use `JavaMailSender` to send notification emails, order confirmations, invoices, or account activation links. To send mail through an authenticated SMTP submission server, the application needs a sending identity, which may be a service account with a dedicated password, OAuth2 credentials, or another provider-supported authentication mechanism.

Security is not merely about **whether the password is strong enough** or **whether the SMTP connection uses TLS**. You must ask: if credentials leak or the mail-sending feature is abused, what can an attacker do with that identity?

The **least privilege** principle requires that the sending account possess only the permissions and scope needed to fulfill its exact business duty:

- Only able to **send** the types of email the application is permitted to issue.
- Only permitted to use organization-approved sender addresses (`From`/`Sender`).
- Only able to send to permitted recipients, domains, or business flows, when the provider and architecture support such limits.
- No permissions to read entire mailboxes, delete messages, modify tenant configuration, or administer users when those permissions are unnecessary.
- Never used as an interactive employee account, for logging into other internal systems, or across multiple unrelated applications.
- Bounded by quotas, sending rates, source IPs, and key/token usage scopes where supported by the provider.

~~~text
Spring application
      |
      | SMTP AUTH / OAuth2
      v
Dedicated sending identity
      |
      +-- Allowed: send notifications from granted address
      |
      +-- Denied: read employee mailboxes
      +-- Denied: administer tenant
      +-- Denied: send from arbitrary From address
      +-- Denied: use by other applications
      |
      v
SMTP submission service
      |
      v
Mail transfer and target mailbox
~~~

**Restricting permissions is not a single Spring Mail setting.** It is a layered set of policies across the identity provider, mail provider/SMTP relay, sending account, secrets system, network, and application business checks.

## 2. Distinguishing three layers of permissions when sending email

When someone says “the sending account has too many permissions”, clarify which layer is meant.

### 2.1. Identity permissions

These are permissions that a credential/token can exercise to access services:

- SMTP submission: submitting messages through an authorized SMTP endpoint.
- Mailbox access: reading, viewing, moving, or deleting emails via other protocols/APIs.
- Delegated send: sending on behalf of or as another mailbox when granted permission.
- Organization administration: creating accounts, altering mail-flow rules, or granting permissions to other identities.

An account may have SMTP submission capability without needing mailbox read access. However, do not infer from the fact that the application **only calls SMTP** that the credential **only has send permissions**. If the same password also works for IMAP, POP3, webmail, or other APIs, its effective scope remains wider than needed.

### 2.2. Sender identity and mail-flow permissions

An authenticated SMTP account is not necessarily permitted to:

- Put any arbitrary address in the `From:` header.
- Use any sender alias.
- Send on behalf of someone else's mailbox.
- Relay to arbitrary external domains.
- Exceed quotas or marketing/bulk sending policies.

Restrictions such as **verified sender**, **Send As**, **Send on Behalf**, domain restrictions, permitted recipients, and sender rewriting are policies enforced by the mail system/provider. Exact permission names vary by provider.

### 2.3. Business-level authorization inside the application

Even if the provider permits sending to any valid email address, the application must not expose an API that lets callers “send any content to any recipient”.

For example, an order confirmation endpoint should only:

1. Authenticate the actor or business event.
2. Identify the order they are authorized to act upon.
3. Retrieve the recipient from a trusted data source.
4. Select an approved template.
5. Create a send job with a clear purpose and boundaries.

**Sender account permissions** and **application authorization** complement each other. The provider locks down what the credential can do; the application locks down *who can request which email, to whom, and when*.

## 3. Threat model: what happens if the sending account is compromised?

Some real-world risks:

| Risk | If using an over-privileged account | If applying least privilege |
|---|---|---|
| Credential exposed in logs/CI | Can send mail, read mailboxes, or access other services | Narrow sending scope only, easy to revoke |
| Attacker abuses sending API | Sends bulk spam/phishing | Rate limits, template policy, recipient restrictions, and quotas limit impact |
| Sender spoofing | Can impersonate many individuals/departments | Restricted to granted sender identities |
| Staging app accidentally uses production secret | May send real mail to customers | Separate credentials/environments, sandbox or recipient restrictions |
| One application is compromised | All systems sharing the credential are affected | Each application/service has its own credential |
| Token stays valid after staff departure | Personal identity creates dependency and revocation friction | Service identity managed by workload lifecycle |
| Admin credential used for sending | Compromising the mail sender enables admin privilege escalation | Never grant admin rights for SMTP sending |

Anti-pattern example:

~~~text
Production Spring Boot app
       |
       +-- uses system administrator's email account
                  |
                  +-- send email
                  +-- read mailboxes
                  +-- administer accounts
                  +-- change mail policies
                  +-- log into other systems
~~~

A minor misconfiguration or small secret leak in the application can escalate into a major incident if the identity carries broad privileges.

Design toward:

~~~text
Production Spring Boot app
       |
       +-- production-notifier identity
                  |
                  +-- send mail only within granted scope
                  +-- no admin mailbox
                  +-- no permission to grant new permissions
                  +-- not used for staging/dev
~~~

## 4. Creating dedicated sending identities per application and environment

Never use the personal email account of a developer, support staff member, or administrator as the production SMTP sender. A dedicated sending identity lets you:

- Block or revoke the application's credential without disrupting employee logins.
- Distinguish traffic between application A and application B.
- Enforce quotas per application or business flow.
- Track audits: which message originated from which service.
- Enforce sender policies and rotate secrets independently.
- Prevent staging/dev from accidentally mailing real customers.

A separation model:

| Environment/application | Sending identity | Permitted sender | Recipients |
|---|---|---|---|
| Production — transactional mail | `prod-order-mailer` | `orders@example.com` | Business customers |
| Production — security notification | `prod-security-mailer` | `security@example.com` | Valid account holders |
| Staging | `staging-mailer` | `staging@example.test` | Test mailboxes or sandbox |
| Development | `dev-mailer` or SMTP sink | Dummy addresses | No Internet relay |

Names in the table are examples. Real accounts and aliases must be provisioned properly through the provider's mechanism—never invent sending rights simply by setting the `spring.mail.username` string.

### Do not share credentials across applications

If an order management application and a marketing application share the same SMTP username/password, an incident in the marketing app can hurt sender reputation, exhaust quotas, and disrupt order emails.

Separate by **content sensitivity, priority, policy, and blast radius**, though you do not necessarily need a separate account for every template. Creating too many accounts raises management overhead; choose the granularity of separation based on risk.

### An identity does not have to be a full mailbox

Some providers support submission-only sender identities/API keys/SMTP credentials with no inbox to read mail. Where available, that is usually better suited for one-way notifications. Some enterprise platforms require a mailbox or service principal with sending rights; review specific platform policies before granting permissions.

Do not automatically assign mailbox read access or excessive licenses/admin privileges just to send email.

## 5. Establishing a least-privilege matrix before provisioning an account

Before configuring SMTP, agree on a permission matrix:

| Action | Application mail account |
|---|---|
| Authenticate to selected SMTP endpoint | Allowed |
| Send from approved sender/alias | Allowed |
| Send from any organization mailbox | Denied |
| Read Inbox/IMAP/POP3 | Denied unless an approved specific need exists |
| Interactive webmail access | Denied when unnecessary |
| Modify mailbox permissions | Denied |
| Create or delete mail accounts | Denied |
| Manage domains/DNS | Denied |
| Modify mail-flow rules/connectors | Denied |
| Read secrets of other applications | Denied |
| Send from staging to real customers | Denied |
| Send at unlimited rate | Denied |

**Deny by default**: grant only explicitly required permissions. If a provider's default role is broader than intended, use custom roles, scoped grants, policies, or another sender identity **if supported by the platform**; never assume every provider offers identical permission controls.

### Separating technical permissions and business rules

For instance, a provider may only support SMTP credentials capable of mailing any recipient without a recipient allowlist. In that case, the application must enforce recipient restrictions, quotas, and auditing itself. However, application-level rules **cannot stop someone who stole the credential** from calling SMTP directly outside the application. Therefore, provider/network policies or an intermediate relay enforcing recipient restrictions remain a stronger defense layer whenever feasible.

## 6. Which limits are set by SMTP and which by the provider?

SMTP is a mail transfer protocol; by itself it does not define a universal RBAC model across providers. Permission models across provider UIs, IAM, service principals, verified senders, SMTP relay connectors, and mailbox ACLs can differ substantially.

| Constraint | Spring Framework Mail | SMTP server/provider |
|---|---|---|
| Setting username/password or AUTH mechanism | Client configuration | Authenticates credential and decides acceptance |
| Choosing host/port/TLS | Client configuration | Enforces TLS/connection policy |
| Setting From/Sender/Reply-To | Builds headers | Allows, rejects, or rewrites per sender policy |
| Business-level recipient restriction | Application checks | May support recipient/domain policies |
| Send-only account without reading mail | Not controlled from Spring | Identity/mailbox/API permissions |
| Source IP or network restriction | Network deployment | Firewall/relay allowlist/conditional access |
| Quotas/throttling | Can rate-limit in app | Provider enforces final limits |
| Account/domain admin permissions | Unrelated to JavaMailSender | Platform admin/RBAC/IAM |
| Send auditing | App logs/metrics | Provider submission/message traces |

**Swapping `JavaMailSender` for another API client does not automatically achieve least privilege.** Regardless of SMTP or HTTP email APIs, credentials/tokens still need minimal scope and anti-abuse controls.

## 7. Sender restrictions: SMTP authentication does not mean sending as any From

An MIME message typically involves several sender-related fields:

- **SMTP AUTH identity:** identity used to authenticate to the submission server.
- **SMTP envelope sender (MAIL FROM):** address used in the SMTP transaction, tied to return-path/bounces.
- **RFC 5322 From:** address normally shown to the recipient in their email client.
- **Sender:** header used when the actual transmitter differs from the address listed in From.
- **Reply-To:** address where replies should go, not proof of sending authorization.

These values are related, yet **they do not have to match at the protocol level**. Provider policies may require them to match, be verified, or have delegated permissions. A server may reject, rewrite addresses, or accept according to its own rules.

Example:

~~~text
Authenticated identity: order-mailer@example.com
Header From:            invoices@example.com
SMTP MAIL FROM:         bounces@example.com
Reply-To:               support@example.com
~~~

This model is valid only if the provider permits the corresponding sender identity and the organization owns those domains/addresses. **Do not assume being able to set `From` in Java means you are authorized to send under that identity.**

### Setting From in Spring Mail

~~~java
import jakarta.mail.MessagingException;
import jakarta.mail.internet.MimeMessage;
import org.springframework.mail.javamail.JavaMailSender;
import org.springframework.mail.javamail.MimeMessageHelper;

public void composeReceipt(
        JavaMailSender sender,
        String recipient,
        String html) throws MessagingException {

    MimeMessage message = sender.createMimeMessage();
    MimeMessageHelper helper =
            new MimeMessageHelper(message, false, "UTF-8");

    helper.setFrom("orders@example.com");
    helper.setTo(recipient);
    helper.setReplyTo("support@example.com");
    helper.setSubject("Order confirmation");
    helper.setText(html, true);

    sender.send(message);
}
~~~

The example assumes `orders@example.com` is permitted by the provider. `Reply-To` does not substitute for `From` permissions; the application must validate reply addresses and never accept arbitrary values from untrusted requests.

### Send As and Send on Behalf

Some mailbox platforms distinguish:

| Concept | Common meaning |
|---|---|
| `Send As` | Identity can send appearing directly as the granted mailbox/address |
| `Send on Behalf` | Sends on behalf of another, often displaying representative info in clients |
| Sender alias | Secondary address usable under specific conditions |
| Verified sender identity | Address or domain verified and accepted by the provider |

Never grant `Send As` across all organization mailboxes if the application only needs to send from one notification mailbox. If delegation is mandatory, scope it strictly to the target mailbox, specific service principal/account, bounded duration, and audit logs.

### Preventing spoofing via application input

A mail-sending API should never accept a `from` value from any client and assign it directly:

~~~java
// Avoid if the request comes from an unauthorized user.
helper.setFrom(request.getFrom());
~~~

Instead, select the sender from server configuration by notification type:

~~~java
public enum NotificationKind {
    ORDER_RECEIPT,
    SECURITY_ALERT
}

public String senderFor(NotificationKind kind) {
    return switch (kind) {
        case ORDER_RECEIPT -> "orders@example.com";
        case SECURITY_ALERT -> "security@example.com";
    };
}
~~~

Allowing an application to choose between two senders does not mean one credential is permitted to send as both. In strict permission setups, each sender may correspond to **its own dedicated credential/client/adapter**.

## 8. SMTP AUTH: enable where needed, disable where unnecessary

SMTP AUTH lets clients authenticate when submitting messages to a submission server. However, many organizations do not want every mail account enabled for SMTP AUTH because credentials can be abused through out-of-policy clients.

Principles:

1. Enable SMTP submission only for identities or connectors that genuinely need it.
2. Never enable SMTP AUTH tenant-wide if only one application needs it and narrower scoping exists.
3. Prefer strong authentication, properly scoped tokens, and short lifetimes where supported by the platform.
4. If passwords/app passwords must be used, create dedicated credentials, store them in a secret manager, and rotate on schedule.
5. Never re-enable legacy protocols like IMAP/POP merely because an application needs SMTP sending.
6. Remove permissions/credentials when an application is decommissioned or switches providers.

Some mail providers disallow password-based SMTP AUTH for accounts or tenants in certain configuration modes; some require OAuth2 or a dedicated relay connector. Check your platform's policies rather than assuming username/password is always permitted.

### Do not equate MFA with app passwords

MFA protects interactive sign-ins, whereas legacy SMTP integrations using app passwords may bypass MFA prompts on each send. An app password, if still permitted by the provider, is a **long-lived secret** and must be managed like a strong password:

- Provision separately per service; never share across users/applications.
- Store in a secret store, never in source.
- Scope to the service/account and revoke immediately when no longer needed.
- Monitor for anomalous usage.
- Prefer OAuth2 or modern secure mechanisms when available and suitable.

Never say “we have MFA so SMTP passwords aren't a concern”; abuse risk depends on the actual SMTP AUTH method enabled.

## 9. OAuth2 scopes and service principals must be bounded

When a provider supports OAuth2 for SMTP submission, replacing passwords with access tokens improves credential lifecycle management, yet **it does not automatically shrink permissions**.

Determine:

- Is the token **delegated** for a user or an **application/service principal**?
- Which exact permissions/scopes are needed for SMTP submission?
- Can the token also call mail-reading APIs or tenant administration?
- Which mailboxes/senders are the app's permissions restricted to?
- Are there overly broad consents/role assignments?
- How does the token expire and refresh?
- How are the secrets or private keys used to fetch tokens stored, rotated, and audited?

An email API service might offer a `send-only` role or dedicated sending permission; another platform might require mailbox-level access policies. **Never assume a generic scope name across providers.** Use the exact scopes/audiences, grant types, and permissions documented officially by your provider.

### Principle of minimum token scope

Example authorization mindset:

~~~text
Service principal: production-order-notifier
  |
  +-- Token audience: mail submission service
  +-- Allowed operation: submit/send transaction email
  +-- Sender/mailbox scope: orders@example.com
  +-- Lifetime: short, refreshed under control
  +-- No: read/list mailbox
  +-- No: user administration
  +-- No: tenant-wide delegated send
~~~

This diagram is a security goal, not an IAM configuration you can copy verbatim for every system. If a provider **cannot scope permissions down to one sender/mailbox**, document the residual risk and consider a different identity, an intermediate relay, or a provider offering narrower send-only controls.

### Caution when using XOAUTH2 with Spring Mail

`JavaMailSenderImpl` uses Jakarta Mail and can configure SMTP authentication mechanisms supported by the implementation. Using XOAUTH2 properly requires **token acquisition, refresh, scope, audience, expiry, and appropriate Jakarta Mail configuration**; merely swapping `spring.mail.password` to a static access token is insufficient for long-running systems.

When tokens expire over time, the application needs a mechanism to supply fresh tokens per authentication/connection. Never write access tokens into logs, mail headers, or exception messages.

A general illustration of SMTP AUTH properties:

~~~properties
# Illustrative: exact configuration depends on provider and Jakarta Mail.
mail.smtp.auth=true
mail.smtp.starttls.enable=true
mail.smtp.starttls.required=true
mail.smtp.auth.mechanisms=XOAUTH2
~~~

These properties **do not automatically grant OAuth scopes or refresh tokens**. Use a token provider integration matching your implementation and check provider policies; do not copy examples into production without designing token lifecycles.

## 10. Secret management: keep credentials out of source code

Example to avoid:

~~~java
sender.setUsername("prod-mailer@example.com");
sender.setPassword("hard-coded-password");
~~~

Or:

~~~yaml
spring:
  mail:
    username: prod-mailer@example.com
    password: plaintext-secret-committed-to-git
~~~

These values can leak through git history, pull requests, build artifacts, container images, CI outputs, or developer environment copies.

### Spring Boot reading credentials via secret injection

Example application configuration (secret-free):

~~~yaml
spring:
  mail:
    host: ${SMTP_HOST}
    port: ${SMTP_PORT:587}
    username: ${SMTP_USERNAME}
    password: ${SMTP_PASSWORD}
    properties:
      mail.smtp.auth: true
      mail.smtp.starttls.enable: true
      mail.smtp.starttls.required: true
      mail.smtp.connectiontimeout: 5000
      mail.smtp.timeout: 10000
      mail.smtp.writetimeout: 10000
~~~

In real environments, placeholders are populated from securely deployed environment variables, configuration integrations, or secret managers. **Environment variables are not automatically completely secure**: users/processes with rights to read process environments or debug processes can still view them. If your platform offers secret volumes or runtime secret injection with stronger rotation support, evaluate those options.

### Credential storage policy

| Control | Reason |
|---|---|
| Secret manager / protected secret store | Avoids embedding passwords in git/build artifacts |
| Secret read access scoped by workload identity | Only the right pod/service can fetch the secret |
| Never log passwords/tokens | Reduces risk of leaks via log pipelines |
| Masking in CI/CD | Prevents printing secret values in builds/deployments |
| Scheduled rotation | Limits lifetime of any exposed credential |
| Revoking old credentials | Prevents legacy apps or attackers from continuing to use them |
| Separating dev/staging/prod secrets | Limits blast radius and accidental sends |
| Auditing who reads/issues/revokes secrets | Detects anomalies and aids investigations |

### Rotation is more than changing a password

When rotating credentials for Spring Mail:

1. Issue a new credential with the **same least-privilege scope**.
2. Update the secret store and deploy/reload configuration per runtime capabilities.
3. Test submission from the updated application.
4. Revoke the old credential once cutover is confirmed, per security policy.
5. Verify old instances no longer use the revoked secret.
6. Confirm logs/audits do not display passwords/tokens.

If the provider allows two active credentials during a transition period, zero-downtime rotation is possible. If the provider allows only one password, coordinate deployments/rolling restarts and handle post-rotation authentication errors cleanly.

## 11. TLS transport is mandatory, though it is not authorization

A low-privilege credential can still be stolen if transmitted over an unprotected channel. For modern SMTP submission, use TLS per provider policy.

Commonly:

- **Port 587**: connect SMTP and upgrade to TLS via STARTTLS.
- **Port 465**: connect with TLS from the start (implicit TLS) if supported by the provider.
- **Port 25**: typically used for mail transfer/relay; should not be the default for application submission.

These are common conventions, not rigid rules for every provider.

Mandatory STARTTLS example:

~~~yaml
spring:
  mail:
    host: smtp.example.test
    port: 587
    properties:
      mail.smtp.auth: true
      mail.smtp.starttls.enable: true
      mail.smtp.starttls.required: true
      mail.smtp.ssl.checkserveridentity: true
      mail.smtp.connectiontimeout: 5000
      mail.smtp.timeout: 10000
      mail.smtp.writetimeout: 10000
~~~

`mail.smtp.starttls.required=true` enforces a successful TLS upgrade instead of continuing to send if the server lacks support. `mail.smtp.ssl.checkserveridentity=true` enables hostname identity verification as supported by the Jakarta Mail provider, reducing the risk of connecting to the wrong endpoint.

If the provider requires implicit TLS, configure `mail.smtp.ssl.enable=true` on the matching port rather than relying on STARTTLS.

**TLS protects transport; it does not restrict which mailboxes an account can read or which From addresses can be sent.** Least privilege must still be enforced at the identity/provider layer.

### Do not relax certificate checks to “fix” send failures

Avoid:

~~~properties
# Do not use a configuration that skips certificate verification in production.
mail.smtp.ssl.trust=*
~~~

Trusting every certificate can mask DNS/PKI errors or allow connections to the wrong endpoint. Configure an appropriate trust store/CA and hostname; if an internal server uses a private CA, provision the right trust chain instead of bypassing verification altogether.

## 12. Restricting target addresses and recipient domains

An account with only SMTP submission rights can still be abused to send spam or phishing to huge numbers of people if the provider imposes no recipient limits. Therefore, define **who can trigger sending** and **which recipient groups are allowed**.

Common policy categories:

| Policy | Example | Appropriate enforcement layer |
|---|---|---|
| Domain allowlist in staging | Send only to `example.test` or test mailbox domains | Application + SMTP relay if supported |
| Send only to verified accounts | Profile email marked verified | Application authorization/data layer |
| Block external addresses for internal mail | `@example.com` only | Provider/relay/application |
| Controlled BCC recipients | Prevent clients from adding arbitrary BCCs | Application model/templates |
| Cap total recipients | At most N recipients per message/job | App + provider quotas |
| Suppression/opt-out lists | Do not send optional notices to unsubscribed users | Business policy |
| Block high-risk domains | Per abuse policy | Mail provider/gateway |

### Distinguish transactional notifications from marketing

Security alerts or transaction confirmations have different recipient policies than marketing newsletters. Never let a marketing-sending endpoint share the same account/credential and quota as security emails if traffic spikes could delay critical alerts.

Marketing emails also carry consent, unsubscribe, and regional legal requirements; those are additional policies, not automatic permissions of an SMTP account.

### Protecting staging and development

A common mistake is running tests against production data and sending real emails:

~~~text
Staging application
     |
     +-- Production SMTP credential
     |
     +-- Customer data copy
     |
     v
Sends email to unintended customers
~~~

Use an **SMTP sink**, provider sandbox, or dedicated credentials with recipient restrictions for staging/dev. A single `if (profile == "test")` condition in code is not a sufficient sole barrier; configuring the provider/relay to block external domains is a strong safeguard whenever possible.

## 13. Enforcing a recipient allowlist in the Spring layer

When business policy permits sending only to a fixed set of domains, enforce validation before creating a `MimeMessage`.

Example validation service (Java 17+):

~~~java
import jakarta.mail.internet.AddressException;
import jakarta.mail.internet.InternetAddress;
import java.util.Locale;
import java.util.Objects;
import java.util.Set;

public final class RecipientPolicy {
    private final Set<String> allowedDomains;

    public RecipientPolicy(Set<String> allowedDomains) {
        this.allowedDomains = Set.copyOf(
                Objects.requireNonNull(allowedDomains));
    }

    public InternetAddress requireAllowed(String raw)
            throws AddressException {
        if (raw == null || raw.isBlank()) {
            throw new AddressException("Recipient is required");
        }

        InternetAddress address = new InternetAddress(raw, true);
        address.validate();

        String mailbox = address.getAddress();
        if (mailbox == null) {
            throw new AddressException("Recipient has no mailbox");
        }
        int atIndex = mailbox.lastIndexOf('@');
        if (atIndex < 1 || atIndex == mailbox.length() - 1) {
            throw new AddressException("Invalid mailbox");
        }

        String domain = mailbox.substring(atIndex + 1)
                .toLowerCase(Locale.ROOT);
        if (!allowedDomains.contains(domain)) {
            throw new SecurityException(
                    "Recipient domain is not permitted");
        }
        return address;
    }
}
~~~

Usage:

~~~java
RecipientPolicy policy = new RecipientPolicy(
        Set.of("example.test", "qa.example.test"));

InternetAddress recipient =
        policy.requireAllowed(request.recipient());

helper.setTo(recipient);
~~~

This example performs **exact domain matching**, does not automatically allow subdomains, and does not attempt to parse every internationalized address variant. If policy supports IDNs, normalize domains via IDNA and verify canonical forms per organizational rules. For high-security systems, use a thoroughly tested address-validation library/policy.

**Do not check with `endsWith("example.com")`** because that mistakenly accepts `notexample.com`. Also avoid `raw.contains("@example.com")` since inputs can include display names or complex formats. Parse the mailbox and enforce policy on the normalized domain.

### Never trust browser-supplied recipients

In an order confirmation API:

~~~java
// Do not take the recipient directly from a public request.
mailService.sendOrderConfirmation(request.getEmail(), orderId);
~~~

Instead:

~~~java
Order order = orderService.getAuthorizedOrder(
        authenticatedUserId, orderId);

String recipient = order.getVerifiedContactEmail();
mailService.sendOrderConfirmation(recipient, orderId);
~~~

Here `getAuthorizedOrder` and `getVerifiedContactEmail` are illustrative business APIs. If an order can be mailed to another recipient, enforce explicit authorization workflows rather than letting requests supply arbitrary addresses.

### Do not rely solely on an in-app allowlist if credentials leak

An attacker who steals the SMTP username/password will bypass `RecipientPolicy` in Java. If restrictions must hold even when the application host is compromised, enforce matching limits at the **provider/relay/network** layer or change the credential model.

## 14. Limiting email counts, connections, and sending quotas

Least privilege is not just a list of actions; it also means **limiting abuse capacity**.

For example, a transactional email account may need:

- Maximum messages/minute matching normal load.
- Daily message or recipient caps per provider.
- Bounded concurrent SMTP connections.
- Bounded recipients per message.
- Bounded body and attachment sizes.
- Limits on repeatedly sending the same email type to one account within a window.
- Alerts when sending rates spike abnormally.

Choose limits based on real capacity and SLAs rather than one fixed number for every app.

### Concurrency is not rate

If a mail executor has 8 workers, that only caps **concurrent tasks**. If each task finishes quickly, 8 workers can still send many emails per second and exceed quotas.

~~~text
Application / Outbox
        |
        v
Recipient + template policy
        |
        v
Rate limiter (messages/sec, per-account quota)
        |
        v
Mail executor (concurrency)
        |
        v
SMTP server/provider
~~~

In multi-replica deployments, 8 workers per replica across 5 replicas can create 40 concurrent SMTP calls. When provider quotas apply account-wide, enforce a **cluster-wide** limit or use a centralized dispatcher; per-JVM limits alone do not protect shared quotas.

### Provider quotas are the last line of defense

If credentials leak and an attacker connects to SMTP directly, Spring's rate limiter has no effect. Whenever possible, enforce quota and concurrency caps **on the account/connector at the provider**, alongside in-app rate limiters to handle load smoothly before hitting provider `4xx` responses or throttling.

### Avoid turning restrictions into lost emails

For transactional emails that must be delivered, when rate limits hit:

1. Persist the send intent in a durable queue.
2. Track appropriate waiting/`available_at` states.
3. Resend with backoff or scheduled dispatch.
4. Watch backlog age so notifications do not breach SLAs.

Never silently drop emails when a token bucket empties, and never hammer retries in ways that prolong provider quota lockouts.

## 15. Allow SMTP relaying only from trusted sources

Some setups use **IP/connector-based SMTP relays** instead of ordinary username/password authentication. Sending permission is then governed by network source, certificates, or relay policy.

A major hazard is accidentally creating an **open relay**: a server accepting mail from untrusted sources toward arbitrary destinations. Open relays get abused for spam, leading to blocklists and domain reputation damage.

Controls:

- Allowlist only the application's actual egress IP ranges or required internal networks.
- In cloud deployments, avoid allowlisting overly broad shared NAT/egress ranges when separation is possible.
- Enforce TLS/mTLS or additional identity checks when supported by the relay.
- Restrict which sender addresses/domains the connector may use.
- Restrict destination domains/recipients, message rates, and sizes where available.
- Never allow anonymous relaying from the Internet.
- Audit connector changes and regularly review source IPs.

Architectural example:

~~~text
Application pod
      |
      | egress policy: only smtp-relay.internal:587
      v
Internal SMTP relay
      |
      +-- Verify client/network identity
      +-- Enforce allowed sender domains
      +-- Apply rate limits / quotas
      +-- Record audit
      |
      v
External mail provider
~~~

**IP allowlists alone have limits**: IPs may be shared behind NAT, co-located workloads on the same network may share the route, and egress IPs can change on deployments. Service-specific accounts/credentials or mTLS narrow identity further when supported by the platform.

### Network egress policies

At the Kubernetes/firewall/security-group layer, restrict the application so it can only reach approved SMTP hosts/ports. This reduces the chance of stolen credentials being used against unfamiliar servers or apps sending directly over other ports.

Still, network egress policies do not grant per-sender mailbox permissions on their own. Combine them with provider permissions and monitoring.

## 16. Limiting which accounts a service can represent

If an application sends on behalf of multiple brands, tenants, or departments, a single credential authorized for the whole organization poses substantial risk. Consider:

1. Separate sender identities/SMTP credentials per tenant or brand group requiring isolation.
2. A policy defining which tenant is allowed to use which sender.
3. Never accepting arbitrary sender mailboxes from HTTP requests.
4. Loading the matching credential only after verifying tenant authorization.
5. Auditing `tenantId`, `senderId`, and `notificationType` without logging secrets.
6. Isolating quotas so one tenant cannot exhaust another tenant's sending capacity.

An abstraction:

~~~java
public record SenderProfile(
        String profileId,
        String fromAddress,
        String replyToAddress) {
}

public interface SenderProfileResolver {
    SenderProfile forTenantAndType(
            String tenantId,
            NotificationKind type);
}
~~~

`SenderProfileResolver` must read from trusted configuration and enforce authorization; it does not verify SMTP permissions by itself. When multiple accounts are needed, the sending adapter must select the `JavaMailSender` matching the profile and avoid sharing tokens/passwords across tenants lacking shared rights.

### Never pass credentials into request-receiving objects

Avoid APIs like:

~~~java
public void sendEmail(
        String smtpUsername,
        String smtpPassword,
        String from,
        String to,
        String body) {
    // Risk: client chooses its own identity and sending permissions.
}
~~~

Credentials belong to server-side infrastructure. Requests should carry only business actions, entity IDs, and permitted data—never arbitrary SMTP identities.

## 17. Do SPF, DKIM, and DMARC replace account permissions?

**No.** SPF, DKIM, and DMARC are email/domain authentication mechanisms at the mail ecosystem layer, not an RBAC system for SMTP accounts.

| Mechanism | Primary objective | Does NOT replace |
|---|---|---|
| SPF | Identifies hosts authorized by a domain at the envelope layer | Granting/blocking SMTP rights for a specific user |
| DKIM | Attaches cryptographic signatures verifying signing domain and signed-part integrity | Restricting which recipients a credential can mail |
| DMARC | Alignment policy and handling for auth failures relative to the From domain | Stopping abuse of a valid compromised credential |

Even with spotless SPF/DKIM/DMARC, an over-privileged admin credential remains risky. An attacker holding a **valid sending credential** can send emails that pass domain authentication depending on setup/provider. Therefore, enforce sending permissions, quotas, monitoring, and incident response.

### Sender identity must be permitted on both sides

A message can be blocked by the provider because the sender isn't verified, or accepted by the provider yet hit deliverability issues due to broken SPF/DKIM/DMARC. These are distinct layers:

~~~text
Application authorized to send?
          |
          v
Provider accepts authenticated sender?
          |
          v
Domain authentication and routing valid?
          |
          v
Recipient system evaluates and delivers?
~~~

Do not try to “fix DKIM” to resolve a “Send As denied” error when the credential lacks From permissions. Conversely, granting broad Send As rights will not fix broken DNS/email authentication records.

## 18. Designing the mail-sending layer to accept only business requests

One way to protect the SMTP account is **preventing arbitrary application components from calling `JavaMailSender` directly with arbitrary headers and recipients**.

Instead of:

~~~java
// This generic mail-sending API is easily abused if exposed across wrong boundaries.
public void sendAny(
        String from,
        String to,
        String subject,
        String html) {
    // ...
}
~~~

Define methods representing authorized business actions:

~~~java
public interface TransactionalMailPort {
    void sendOrderReceipt(OrderReceiptCommand command);
    void sendSecurityAlert(SecurityAlertCommand command);
}
~~~

Example DTOs:

~~~java
public record OrderReceiptCommand(
        String orderId,
        String customerId,
        String locale) {
}

public record SecurityAlertCommand(
        String accountId,
        String eventId,
        String locale) {
}
~~~

**Never accept SMTP username, password, From, BCC, or arbitrary HTML in client commands.** The application service checks authorization, fetches verified recipients, and selects templates and sender profiles from configuration.

Flow:

~~~mermaid
flowchart TD
    A[Authenticated request / committed event] --> B[Business authorization]
    B --> C[Load trusted recipient + domain data]
    C --> D[Select approved template and sender]
    D --> E[Recipient/rate/size policy]
    E --> F[Mail outbox / queue]
    F --> G[Dedicated mail adapter]
    G --> H[SMTP identity with least privilege]
    H --> I[Provider policy and quota]
    I --> J[SMTP submission]
~~~

Benefits:

- Controllers cannot decide sender identities on their own.
- Templates are constrained per use case.
- Business authorization runs before any send action.
- Policies are enforced centrally instead of ad-hoc per service.
- One clear place to audit and classify rejections.

### Validation is not authorization

A syntactically valid email address does not mean the user is allowed to send to it. For example, a password reset endpoint may be designed to mail the email on file; even if a request carries a valid `other@example.com`, that address may not be authorized to receive sensitive notifications.

Conversely, security policy must not inadvertently leak whether an account exists when public endpoints return different responses per recipient. Apply anti-enumeration and rate-limiting measures suited to the business case.

## 19. Isolating sending accounts by sensitivity level

Not all emails belong under the same policy:

| Email type | Characteristics | Permission design to consider |
|---|---|---|
| OTP/account recovery | Sensitive, short-lived, abuse-prone | Dedicated sender, dedicated quota, fixed templates, no arbitrary BCC |
| Invoices/payment receipts | Critical, audit-required | Scoped identity, outbox, approved sender |
| Orders/shipping | Relatively high volume | Sufficient quota and monitoring |
| Marketing/newsletters | Large spikes and suppression policies | Dedicated account/provider lane, opt-outs, separate rate policy |
| Internal alerts | Often internal-domain only | Internal recipient restrictions |

If marketing traffic exhausts a quota shared with OTPs, users may not receive login codes. Separating sender identities/credentials and capping quotas per lane preserves priority for critical flows.

For sensitive content, also ensure:

- Never send secrets/tokens to unauthorized distribution lists.
- Never allow altering `Reply-To` to redirect replies to an unfamiliar address.
- Never let backends inject extra BCCs beyond audit/control requirements.
- For attachments, verify documents belong to the recipient and check access rights.
- Minimize sensitive details in subjects (subjects are frequently exposed unexpectedly).

## 20. Using multiple JavaMailSenders for multiple accounts

When each email category uses a different account or provider, you can configure **two distinct `JavaMailSender` beans** with purpose-scoped identities:

~~~java
import java.util.Properties;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.mail.javamail.JavaMailSender;
import org.springframework.mail.javamail.JavaMailSenderImpl;

@Configuration
public class DedicatedSenderConfiguration {

    private JavaMailSenderImpl newSender(
            String host,
            int port,
            String username,
            String password) {

        JavaMailSenderImpl sender = new JavaMailSenderImpl();
        sender.setHost(host);
        sender.setPort(port);
        sender.setUsername(username);
        sender.setPassword(password);
        sender.setDefaultEncoding("UTF-8");

        Properties props = sender.getJavaMailProperties();
        props.put("mail.smtp.auth", "true");
        props.put("mail.smtp.starttls.enable", "true");
        props.put("mail.smtp.starttls.required", "true");
        props.put("mail.smtp.ssl.checkserveridentity", "true");
        props.put("mail.smtp.connectiontimeout", "5000");
        props.put("mail.smtp.timeout", "10000");
        props.put("mail.smtp.writetimeout", "10000");
        return sender;
    }

    @Bean("ordersMailSender")
    JavaMailSender ordersMailSender(OrderMailCredential credentials) {
        return newSender(
                credentials.host(),
                credentials.port(),
                credentials.username(),
                credentials.password());
    }

    @Bean("securityMailSender")
    JavaMailSender securityMailSender(
            SecurityMailCredential credentials) {
        return newSender(
                credentials.host(),
                credentials.port(),
                credentials.username(),
                credentials.password());
    }
}
~~~

`OrderMailCredential` and `SecurityMailCredential` are secure application-defined configuration abstractions, for example bound from a secret store. **Never hardcode password values in Java source.**

Select the bean via qualifier:

~~~java
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.mail.javamail.JavaMailSender;
import org.springframework.stereotype.Service;

@Service
public class OrderReceiptSender {
    private final JavaMailSender sender;

    public OrderReceiptSender(
            @Qualifier("ordersMailSender")
            JavaMailSender sender) {
        this.sender = sender;
    }
}
~~~

With multiple `JavaMailSender` beans, services missing `@Qualifier` may hit injection ambiguity in Spring. In secure systems, explicitly selecting a business-scoped sender is easier to govern than a single global default bean holding broad privileges.

**Separating `JavaMailSender` beans is only part of the solution.** If both beans share one credential permitted to send from any address, the blast radius has not truly shrunk. The provider must provision two distinct identities/permission sets accordingly.

### Caution with pooling and session sharing

Each `JavaMailSenderImpl` holds its own server/authentication config; never mutate `username` or `password` on a single singleton bean right before each per-tenant send. Mutating shared config across concurrent requests can send under the wrong identity, break auditability, and leak privileges.

If per-tenant selection is required, use a registry of immutable profile-scoped senders/configs with clear lifecycle management and cache/secret rotation. Never accept SMTP credentials from client requests to spin up unbounded dynamic senders.

## 21. Protecting From/Reply-To/Return-Path configuration

For emails involving replies or bounces, developers easily confuse:

- `From` header: displayed author/sender.
- `Reply-To` header: suggested destination for replies.
- Envelope sender/return-path: tied to bounces and mail routing.

An account permitted to send mail does not necessarily have permission to alter all three arbitrarily. Providers may rewrite values or require domain/sender verification. Notably, attackers can abuse `Reply-To` to divert replies to an address they control even when `From` looks legitimate.

Policy example:

~~~java
public record ApprovedMailIdentity(
        String fromAddress,
        String replyToAddress) {
}

public ApprovedMailIdentity identityFor(
        NotificationKind kind) {
    return switch (kind) {
        case ORDER_RECEIPT -> new ApprovedMailIdentity(
                "orders@example.com", "support@example.com");
        case SECURITY_ALERT -> new ApprovedMailIdentity(
                "security@example.com", "security@example.com");
    };
}
~~~

The mail composer accepts only server-selected profiles. Never accept arbitrary `replyTo` parameters from public endpoints. If dynamic reply-to addresses per employee or partner are needed, enforce ownership and domain checks per policy.

### Custom headers are not an authorization mechanism

Adding a header like `X-Application-Name` or `X-Tenant-Id` can aid internal tracing, yet SMTP providers do not naturally treat it as proof of authorization. If a mail gateway relies on custom headers to enforce policies, you must control who can inject/modify headers and authenticate the source via a trusted mechanism.

## 22. Outbox and authorization: preserving send decisions across transactions

For business-triggered emails, separate the **approved send intent** from the SMTP action:

~~~text
Business transaction
    |
    +-- Verify event + user permissions
    +-- Identify trusted recipient
    +-- Select template + sender profile ID
    +-- Write outbox record
    |
    v
COMMIT
    |
    v
Mail worker
    |
    +-- Load granted sender profile
    +-- Re-validate necessary policies
    +-- Apply quota/rate limit
    +-- JavaMailSender.send
~~~

Outbox records should hold a **sender profile ID** or approved notification type rather than storing usernames/passwords. Workers look up credentials from the secret store or server-side security infrastructure.

Payload example:

~~~json
{
  "eventId": "mail-job-2810",
  "notificationType": "ORDER_RECEIPT",
  "senderProfileId": "production-orders",
  "orderId": "ORD-001",
  "recipientId": "CUSTOMER-900",
  "payloadVersion": 1
}
~~~

If business policy permits snapshotting the recipient, you can record the verified email address at commit time. If the worker looks up the latest recipient, determine whether an email change after event creation should redirect who receives it. **Never let an outbox consumer send with broad privileges just because it runs in the background.**

### When policies change between job creation and sending

Suppose an account is locked after a password-reset email was added to the outbox but before the worker sends it. Business rules may require canceling the notification or altering handling. Therefore, define:

- Which checks are frozen at commit time?
- Which checks must be re-evaluated at dispatch time?
- Which jobs must be canceled if an account/consent/tenant is disabled?
- Could the job contain an expired token?

Decisions depend on notification type; an outbox does not automatically solve authorization and time-varying data validity.

## 23. Testing least privilege from application to mail provider

SMTP security testing needs at least **two layers**:

1. **Application policy tests:** verify controllers/services block unauthorized sends and pick the right sender, recipient, and template.
2. **Provider/relay authorization tests:** using test accounts in a controlled environment, confirm the provider genuinely rejects out-of-scope actions.

### Testing the domain allowlist

For `RecipientPolicy` shown earlier:

~~~java
import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

import jakarta.mail.internet.AddressException;
import java.util.Set;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;

class RecipientPolicyTest {
    private RecipientPolicy policy;

    @BeforeEach
    void init() {
        policy = new RecipientPolicy(
                Set.of("example.test", "qa.example.test"));
    }

    @Test
    void permitsExplicitlyAllowedDomain() throws Exception {
        assertThat(
                policy.requireAllowed("user@example.test").getAddress())
                .isEqualTo("user@example.test");
    }

    @Test
    void rejectsUnapprovedDomain() {
        assertThatThrownBy(
                () -> policy.requireAllowed("user@external.example"))
                .isInstanceOf(SecurityException.class);
    }

    @Test
    void rejectsLookalikeDomain() {
        assertThatThrownBy(
                () -> policy.requireAllowed("user@notexample.test"))
                .isInstanceOf(SecurityException.class);
    }

    @Test
    void rejectsMissingRecipient() {
        assertThatThrownBy(
                () -> policy.requireAllowed("  "))
                .isInstanceOf(AddressException.class);
    }
}
~~~

This tests policy in the Java layer, not whether the real SMTP account is correspondingly restricted at the provider.

### Testing that sending does not run when policy denies

Example mocking `JavaMailSender` for a policy-enforcing adapter:

~~~java
import static org.assertj.core.api.Assertions.assertThatThrownBy;
import static org.mockito.Mockito.never;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.verifyNoInteractions;

import java.util.Set;
import org.junit.jupiter.api.Test;
import org.springframework.mail.javamail.JavaMailSender;

class PolicyGuardTest {
    @Test
    void doesNotReachMailSenderForBlockedRecipient() {
        JavaMailSender sender =
                org.mockito.Mockito.mock(JavaMailSender.class);
        RecipientPolicy policy =
                new RecipientPolicy(Set.of("example.test"));

        assertThatThrownBy(() ->
                policy.requireAllowed("outside@other.test"))
                .isInstanceOf(SecurityException.class);

        verifyNoInteractions(sender);
    }
}
~~~

This snippet illustrates the fail-before-send principle by testing policy in preprocessing; in real applications, invoke the **service combining validation and `mailSender`** and assert `verifyNoInteractions(sender)` to prove the send path cannot be reached when policy rejects. Do not test only the helper/policy in isolation and assume the whole system is protected.

### Provider authorization tests

In a test environment with tightly scoped permissions, verify:

- Credentials sending as the authorized sender are accepted.
- Attempting an ungranted `From` is rejected or rewritten per policy.
- If recipient restrictions exist, sending outside the allowlist is blocked.
- If IP restrictions exist, requests from unauthorized sources are rejected.
- If quotas exist, exceeding limits is controlled (without spamming real users).
- Credentials lack mailbox/API read permissions that were not granted.
- Revoked old secrets stop working after rotation.

**Never run brute-force tests, generate spam, or try exceeding quotas in production to “test” security.** Use sandbox accounts, controlled mailboxes, and verify permissions via admin/provider APIs or authorized procedures.

### Negative tests matter more than happy paths

Successfully sending an email from `orders@example.com` only proves the account has enough permission to do that. **It does not prove the account lacks permission to send as `ceo@example.com` or read mailboxes.** Least-privilege testing requires controlled negative tests covering prohibited grants.

## 24. Periodic permission reviews and drift detection

An account may start with narrow permissions, yet over time:

- An admin adds Send As to fix an urgent incident.
- The account gets added to an overly broad group.
- The connector's IP allowlist gets widened.
- SMTP AUTH gets enabled on more accounts than intended.
- Staging accidentally shares a secret with production.
- An API key gets reused for both marketing and security alerts.
- Mailbox read rights are added and never revoked.

That is **privilege drift**: effective permissions growing larger than the original design.

A periodic permission review can compare:

| Review item | Desired state | Action needed if |
|---|---|---|
| Service principal/account | Approved identities only | Personal users or unknown accounts appear |
| Authentication method | Policy-approved mechanisms | Legacy methods enabled unnecessarily |
| Send As grants | Approved mailboxes/aliases only | Extra mailboxes or wildcard scopes exist |
| Mailbox read permissions | None if send-only | IMAP/POP/API read access enabled |
| Admin/IAM roles | None | Tenant or org admin roles attached |
| IP/source restrictions | Approved egress only | Overly broad allowlist or unfamiliar sources |
| Sender domains | Exact verified list | Unrelated domains present |
| Recipient/relay limits | Exact business scope | Unexpected external relaying allowed |
| Quotas/alerts | Clear thresholds | No alerts on spikes |
| Secrets | Environment-separated, rotated | Old credentials remain usable |

If your platform supports infrastructure as code, keep **permission policies and connectors** in reviewed, approved configuration. Secrets never go into IaC repositories. For emergency changes, record justification, approver, and expiration time for temporary permissions.

### Auditing who modified permissions

Do not track only sent email counts; also track:

- Who created/reset credentials?
- Who enabled/disabled SMTP AUTH?
- Who granted or revoked Send As/Send on Behalf?
- Who added IPs to allowlists?
- Who altered quotas or recipient policies?
- Which app uses new vs. old tokens?

These audit events reside mainly in the identity provider/mail provider, not emitted by `JavaMailSender` itself. Application logs can complement them with event IDs, sender profiles, and sending purpose.

## 25. Monitoring abnormal sending account behavior

Even a least-privilege service identity can still be abused within its granted scope. Monitor for anomalies:

| Signal | Possible meaning |
|---|---|
| Sudden spike in emails/minute | Loop bug, spam, or compromised credential |
| Surge in new/unfamiliar recipients | Business flow being abused |
| Sending at unusual hours | Abnormal event or abuse |
| High SMTP AUTH failures | Expired secret, misconfiguration, or brute-force attempt |
| High Send As denied errors | App picking wrong From or spoofing attempt |
| High relay prohibited errors | Recipient/domain restriction firing or being probed |
| High provider rejections | Quotas, reputation issues, or policy violations |
| Source IP/auth location shift | Egress deployment change or credential compromise |
| Rising bounce/complaint rates | Bad recipient list or abuse |

### Application-level logging

Record sufficient metadata:

~~~text
event=mail_submission
notificationType=ORDER_RECEIPT
senderProfile=production-orders
jobId=mail-job-2810
tenantId=tenant-42
recipientDomain=example.test
result=SMTP_ACCEPTED
durationMs=731
~~~

This is dummy sample data. If recipient domains or tenant IDs are sensitive in your system, adjust/redact accordingly. Never log passwords, OAuth tokens, body content, attachments, OTPs, magic links, or unnecessary customer data.

When sending via SMTP, log error codes/categories and attempt counts. **Never use raw exception messages or recipient addresses as metric labels** due to high cardinality and data exposure risks.

### Alerts must link to operational actions

A good alert includes:

- Affected sender profile.
- Time window and magnitude of send/failure surge.
- Data source: app metrics vs. provider submission audits.
- Initial triage path: credentials, quotas, Send As rights, network, or templates.
- Procedure to pause the sending lane and revoke secrets if compromise is suspected.

You do not need to alert on every single temporary `SMTP 4xx` rate limit. Base alerts on rates, duration, backlog impact, and notification type.

## 26. Incident response when an SMTP credential leaks

If signs point to a credential leaking via commits, logs, CI artifacts, container images, or anomalous sending, treat it as a security incident:

1. **Contain:** identify affected apps, accounts, sender profiles, environments, and credential stores.
2. **Limit abuse:** pause identity submission or apply provider blocks/quotas per incident plan.
3. **Revoke/rotate credentials:** invalidate old secrets/tokens; check all replicas and jobs still holding them.
4. **Assess scope:** audit Send As grants, mailbox access, admin roles, relay connectors, and token grants.
5. **Reconcile logs:** compare the app outbox against provider submission audits; find messages not originating from approved business flows.
6. **Recover safely:** provision new least-privilege credentials; redeploy via secret store.
7. **Assess impact:** review recipients, domains, reputation, complaints/bounces, and notify stakeholders if required.
8. **Eliminate root cause:** purge secrets from improper locations, fix CI masking, review code/configs, and tighten policies.

### A risk of merely rotating a password

If old tokens or credentials remain valid, changing a password in a UI without revoking associated sessions/tokens may be insufficient. Procedures must match the provider: revoke refresh tokens, API keys, app passwords, SMTP credentials, or service principal grants accordingly.

If an account held tenant admin rights, the investigation scope expands dramatically. That is one of the strongest reasons **never to use admin credentials for Spring Mail**.

### Outboxes aid recovery, yet replays must be controlled

When pausing sending during an incident, the outbox holds unsubmitted jobs. After provisioning new credentials:

- Verify jobs belong to authorized types.
- Block jobs that have expired (e.g., expired OTPs).
- Apply quotas when replaying the backlog.
- Reconcile `UNKNOWN` jobs to avoid unnecessary duplicates.
- Track audits to pinpoint the recovery timestamp.

Never replay all queued jobs unconditionally. A compromised account may coincide with unauthorized jobs; replay only requests with verified provenance and authorization.

## 27. Configuration symptoms and diagnostic guidance

Common errors when a sending account is properly scoped:

| Symptom | Likely cause | How to check |
|---|---|---|
| SMTP AUTH rejected | Wrong/expired credential/token, SMTP AUTH blocked, wrong scope | Check auth method, token audience/scope, account policy |
| Authenticates, yet From rejected | Missing Send As/verified sender grant | Compare authenticated identity with sender profile and provider policy |
| Fails only in staging | Sandbox credential/recipient allowlist | Check environment, profile, egress, and test domains |
| Can send internally, not to Internet | Relay policy restricts external recipients | Check connector, recipient rules, and domain policy |
| Certain tenants cannot send | Tenant-to-sender authorization or quota | Check profile resolver and per-tenant permissions |
| Mailbox access denied | Mail read access disabled by design | Confirm whether the app genuinely needs read access |
| SMTP 4xx under higher traffic | Provider throttling or quotas | Check rates, concurrency, backlog, and response codes |
| SMTP 5xx on certain recipients | Recipient/sender policy, domain validation | Inspect SMTP reply codes, policies, and recipient data |
| TLS handshake or hostname error | Trust chain, host, TLS version/cert | Fix trust and endpoint; never enable trust-all |
| Rejected from new instances | Egress IP missing from allowlist | Check NAT egress/connector and deployment |
| Sends successfully, lands in spam | Deliverability, reputation, authentication | Check SPF/DKIM/DMARC and content; never broaden account permissions |

**Never fix a “Send As denied” error by granting an admin role to the service account.** Grant the exact permission on the sender identity the application genuinely needs. Similarly, when throttled, never switch to an employee's credential just to “send faster”.

### Layered diagnosis

~~~mermaid
flowchart TD
    A[Spring Mail submission failed] --> B{Connection and TLS succeeded?}
    B -- No --> C[DNS, port, TLS, certificate, network]
    B -- Yes --> D{SMTP AUTH succeeded?}
    D -- No --> E[Credential, token, auth policy/scope]
    D -- Yes --> F{Sender permitted?}
    F -- No --> G[Verified sender, Send As, mailbox scope]
    F -- Yes --> H{Recipient/rate/relay permitted?}
    H -- No --> I[Quota, recipient allowlist, IP policy]
    H -- Yes --> J[Submission accepted]
    J --> K[Delivery/DMARC/spam filtering checked separately]
~~~

This is a conceptual path; SMTP providers may enforce checks in different orders and return codes that do not map strictly one-to-one to every branch. Inspect nested exceptions, SMTP responses, and provider logs before concluding.

## 28. Anti-patterns to avoid

### 28.1. Using an administrative mailbox credential for SMTP

An application bug or leaked secret can lead to breaches far beyond sending. Use a service identity carrying only required permissions.

### 28.2. Putting the same secret into development, staging, and production

A secret leaked from a developer laptop could affect all production recipients. Separate environments and restrict staging recipients at the provider/relay whenever possible.

### 28.3. Enforcing permissions only in Java without provider checks

Java code blocking recipients has no effect if an attacker steals credentials and connects to SMTP directly. Enforce provider policies, egress restrictions, and auditing.

### 28.4. Granting wildcard Send As or unnecessary tenant-wide permissions

An app that only sends from `orders@example.com` does not need permission to send on behalf of every mailbox. Grant narrow per-sender permissions.

### 28.5. Letting endpoints accept arbitrary From, Reply-To, and HTML content

This can turn the backend into a legitimate spam/phishing relay. Allow sending only via approved templates and business rules; validation and authorization must come before SMTP.

### 28.6. Committing real passwords in `application.yml` to git

Git history and artifacts retain secrets even if removed in newer commits. Use a secret manager and rotate any leaked secret.

### 28.7. Assuming OAuth2 automatically means send-only

Tokens can carry broad application permissions if grants are broad. Audit scopes, audiences, application roles, mailbox scopes, and consents.

### 28.8. Believing SPF/DKIM/DMARC stop compromised credentials

These mechanisms address domain authentication/deliverability, not user/application SMTP permissions.

### 28.9. Increasing concurrency to bypass rate limits

Providers may lock accounts or throttle harder; raising pool sizes also complicates backlogs and retries. Respect quotas and throttle rates.

### 28.10. Bypassing authorization errors by switching to another sender

If `orders@example.com` is rejected due to missing permissions, never fall back automatically to `admin@example.com` or a shared global account. That can violate policy. Block submission, log the error code, and fix permissions.

### 28.11. Failing to audit permissions after changing providers

A new provider may give credentials broader sending rights or require different authentication mechanisms. Re-verify the permission matrix, sender aliases, quotas, TLS, and webhook/bounce scopes before cutover.

### 28.12. Running an open relay without trusted sources

A relay allowing external sources to send to arbitrary destinations creates a spam gateway. Restrict network identities, sender domains, rates, and logging.

## 29. Workflow for implementing least privilege in Spring Mail

A practical step-by-step workflow:

1. **Inventory requirements:** which email types does the app send, from which addresses, to which recipient groups, and at what expected volume?
2. **Select the auth model:** SMTP AUTH password, OAuth2, or relay identity per provider capabilities and security policy.
3. **Create a dedicated identity:** never use admin or personal employee accounts.
4. **Grant least privilege:** submission only, approved senders/mailboxes only; omit mailbox read or tenant admin unless required.
5. **Configure provider policies:** verified senders, Send As, allowed recipients/domains, and quotas/IP restrictions where supported.
6. **Isolate environments:** independent credentials, senders, and recipient policies for dev/staging/prod.
7. **Store secrets securely:** use a secret manager, restrict which workloads can read them, and maintain a rotation plan.
8. **Configure Spring:** accurate host/port/TLS/auth/timeouts; never log credentials.
9. **Build application authorization:** endpoints submit business requests only; the mail adapter selects senders and templates from config.
10. **Bound load:** rate limiting, concurrency, batch sizes, and per-account/cluster-wide quotas.
11. **Test positive and negative cases:** allowed identity sends succeed; out-of-scope senders/recipients/IPs are blocked.
12. **Monitor and audit:** submission rates, auth failures, Send As denied, quotas, unfamiliar IPs, and privilege changes.
13. **Operate lifecycle:** rotate, revoke, review drift, and handle credential compromises.

### Minimum decision matrix

| Question | If “Yes” | Action |
|---|---|---|
| App only needs to send without reading inbox? | Yes | Do not grant mailbox read permissions |
| Needs to send from only one sender? | Yes | Verify/allow only that sender |
| Multiple unrelated apps exist? | Yes | Separate credentials by blast radius |
| Staging/dev environments exist? | Yes | Separate credentials and recipient sandboxes |
| Provider supports recipient restrictions? | Yes | Enforce policy directly at provider/relay |
| Provider lacks recipient restrictions? | Yes | Add app policy, network controls, and monitoring; document theft risk |
| Needs to send via multiple accounts? | Yes | Use separate sender profiles/`JavaMailSender` beans and matching grants |
| Account holds admin permissions? | Yes | Review and revoke unnecessary rights |
| Cluster-wide quota exists? | Yes | Coordinate rate/concurrency cluster-wide |
| Mail must survive restarts? | Yes | Transactional outbox/broker, not `@Async` alone |

## 30. Frequently asked questions

**Does an SMTP account need mail-server admin privileges?** No. A typical mail sender needs only submission rights and its corresponding sender identity. Admin rights dramatically increase blast radius.

**If an account is created “just for sending”, can it definitely not read mailboxes?** Not necessarily. Effective rights depend on the provider and enabled protocols/APIs. Inspect actual grants/protocol access, not just the account's naming intent.

**Do setting `spring.mail.username` and `spring.mail.password` restrict permissions by themselves?** No. These properties configure how the client authenticates. Permissions are governed by the provider/account and external policies.

**Can one account be used for every From address?** Only if the provider grants the corresponding permission, yet that is usually overly broad if the app only needs a few senders. Restrict by address/alias or separate identities.

**Should an application change From dynamically per request?** No for untrusted requests. Select server-side sender profiles by business type and authenticated tenant.

**Is SMTP AUTH with OAuth2 always safer than passwords?** Appropriately scoped, time-limited tokens reduce risk, yet OAuth2 can still receive overly broad permissions or leak refresh tokens/client secrets. Audit grants and token lifecycles.

**Is enabling MFA on the SMTP account enough?** No. Some SMTP AUTH methods, app passwords, or service-to-service grants do not prompt for MFA per send. Verify the auth mechanism and apply least privilege.

**Does TLS restrict recipients or sender addresses?** No. TLS protects transport; authorization and sender/recipient restrictions live at the provider, relay, and application.

**Do IP allowlists replace passwords/OAuth2?** Not completely. They bind network sources only and can be affected by NAT/shared egress. Combine service authentication, TLS, and sender policies whenever possible.

**Do SPF, DKIM, and DMARC prevent compromised accounts from sending mail?** No. Domain authentication mechanisms do not replace credential management and sending permissions.

**Are Send As permissions and Reply-To the same thing?** No. Send As governs permission to send as a mailbox/identity; Reply-To is merely a header indicating where replies go and needs separate anti-abuse controls.

**Does separating two `JavaMailSender` beans provide security isolation on its own?** Only if each bean genuinely uses distinct credentials/permissions and separate configs/provider policies. Two beans using the same global credential do not create least privilege.

**Can a recipient allowlist exist only inside Spring?** It provides one defensive layer, yet leaked credentials can be used outside the app. Enforce provider/relay/network restrictions if that guarantee is mandatory.

**Does a sending account need an outbox?** An outbox is not a permission mechanism. It durably persists send intent; sender permissions must still be restricted. The two solve different problems and work well together.

## 31. Summary

In Spring Framework Mail, **restricting sending account permissions** means creating dedicated identities with the smallest necessary scope: permitted only to send required notifications, under approved sender identities, through appropriate SMTP endpoints/policies, and within controlled quotas.

Achieving this requires coordinating multiple layers:

- **Identity/provider:** authentication, scopes/grants, Send As, and actual mailbox permissions granted.
- **Network/SMTP relay:** TLS, source restrictions, preventing open relays, and recipient/traffic limits.
- **Spring application:** rejecting arbitrary From/recipients/HTML, using fixed sender profiles, validation, and authorization.
- **Secret management:** storage, rotation, revocation, and environment isolation.
- **Operations:** auditing, metrics, anomaly alerts, privilege drift reviews, and incident response.

Remember the rule: **`JavaMailSender` is only a mail-sending client; the credential's true permissions live outside Spring.** Securing the application does not stop at encrypting transport or picking a strong password. Shrink what the credential is allowed to do, limit how much mail can be abused, and ensure a compromised application never grants mailbox read access or control over the entire email system.
