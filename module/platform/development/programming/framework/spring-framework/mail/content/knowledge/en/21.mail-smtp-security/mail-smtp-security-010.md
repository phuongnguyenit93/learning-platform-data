# Separating Sending Accounts by Environment or Function

When a Spring application starts sending email, configuration is often very simple: one SMTP host, one username, one password, and one `From` address. However, once the application has development, staging, and production environments while simultaneously sending account verification emails, invoices, security alerts, and marketing messages, **sharing a single SMTP account across every flow** creates major risks.

For example, if a developer machine accidentally uses production credentials, a test run can send real emails to customers. If the SMTP account serving newsletters is compromised, an attacker can abuse those same permissions to send spoofed security notifications. If a marketing stream gets rate-limited by the provider, critical password-reset emails can be impacted.

Therefore, in **Spring Framework Mail**, consider separating **SMTP accounts/credentials**, server configurations, sender identities, domains, and sending policies by **environment** or **business function**. Separating accounts is more than changing a display address string: it involves provider authentication permissions, credential scope, quotas, logging, recipient policies, and how the application selects a `JavaMailSender`.

This lesson covers the rationale, levels of separation, Spring Boot configuration patterns, multiple `JavaMailSenderImpl` examples, controlled routing mechanisms, secret protection, STARTTLS/implicit TLS, domain management, testing, and operational monitoring.

## 1. What does an SMTP account actually represent?

To send mail through an SMTP relay, an application typically needs:

- **SMTP endpoint**: host and port of the server accepting send requests.
- **Credential**: username/password, SMTP token, or provider-supported authentication method.
- **Transport security**: STARTTLS, implicit TLS, and certificate verification policies.
- **Sender identity**: `From` address, optionally with a display name.
- **Envelope sender**: address used in the `MAIL FROM` command, usually tied to bounces and provider policies.
- **Account permissions**: verified domains/addresses, sending rates, quotas, and which sender identities may be used.
- **Internal policies**: environment, email purpose, and permitted recipients.

Do not confuse these concepts:

| Component | Role |
| --- | --- |
| SMTP username | Authenticates the account or application identity with the relay |
| SMTP password/token | Secret authorizing the relay to accept send operations |
| `From` header | Sender address visible to the recipient |
| `Reply-To` | Suggested address for recipient replies |
| Envelope `MAIL FROM` | Address used for routing/bounces at the SMTP level |
| `To` / `Cc` / `Bcc` | Recipient addresses |
| `Message-ID` | Message identifier used for threading/tracing |

One SMTP account may be allowed by the provider to use multiple `From` addresses, or only specific verified domains. **Changing `helper.setFrom(...)` does not mean you switched SMTP accounts.** Conversely, using two credentials with the same `From` still means two distinct authentication principals, requiring corresponding domain policy checks.

### Example misconception

~~~java
helper.setFrom("security@example.org");
mailSender.send(message);
~~~

If `mailSender` is still configured with marketing credentials, the email may be rejected by the provider, sent under the wrong identity, or tie security traffic to marketing quotas and permissions. Routing decisions must pick the right **transport/account**, not merely swap headers.

## 2. Why separate sending accounts?

Primary objectives:

1. **Reduce blast radius on credential leaks:** one exposed secret must not automatically grant access to every function/environment.
2. **Prevent sending real mail from test environments:** development/staging must not have default capability to email production customers.
3. **Scope permissions by purpose:** marketing accounts should not share permissions or policies with password-reset emails.
4. **Isolate quotas and sending reputation:** high volume or errors in one email category must not throttle the entire system.
5. **Simplify auditing and tracing:** know which job used which account, for what purpose, and where failures occurred.
6. **Independent rotation and incident response:** revoke credentials for one stream without necessarily halting all remaining streams.
7. **Apply provider policies accurately:** domain verification, sender identities, bounces, complaints, and suppressions can be managed separately.
8. **Prevent misconfiguration:** explicit configuration reduces the chance of accidentally hitting production SMTP during local tests.

Separating accounts does not replace recipient validation, authorization, or DMARC. It is **one layer in defense in depth**. An application can still email the wrong person if it holds a valid credential yet chooses the wrong recipient.

## 3. Two separation axes: environment and function

Two common axes exist.

**By environment:** development, test/CI, staging, and production.

**By function:** security/account, transactional/business, marketing/bulk, and operational/monitoring.

Illustrative policy matrix:

| Environment | Security email | Transactional email | Marketing email |
| --- | --- | --- | --- |
| Local development | Mail catcher or sandbox | Mail catcher | Disabled or sandbox |
| Automated tests | Fake sender/SMTP test server | Fake sender | Fake sender |
| Staging | Separate sandbox account + recipient allowlist | Separate sandbox account | Disabled or test recipient group |
| Production | Dedicated security credential | Dedicated transactional credential | Dedicated marketing credential |

You do not necessarily need twelve accounts from day one. What matters is that environments **never inadvertently share sensitive credentials**, while functions with differing risk/quota profiles are isolated appropriately.

### Should separation use accounts, subaccounts, or providers?

Depending on provider features, isolation levels may include:

- Separate SMTP users/credentials under one provider account.
- Separate provider subaccounts or projects.
- Independent tenants/provider accounts.
- Different sending domains/subdomains.
- Completely separate SMTP endpoints.
- Namespace policies within the application.

**Two credentials under the same provider account are not guaranteed to have fully independent quotas, IP reputation, or permissions.** Check at what level the provider truly isolates resources. If the goal is quota or reputation isolation, a secondary user alone may not suffice.

## 4. Separation by environment: dev, test, staging, prod

### 4.1. Development

Developer machines should use an SMTP catcher or sandbox. The goal is inspecting MIME content, subjects, and attachments **without delivering real emails to the Internet**.

Example local config with an SMTP catcher:

~~~yaml
spring:
  config:
    activate:
      on-profile: local
  mail:
    host: localhost
    port: 1025
~~~

This configuration merely illustrates a local mail catcher listening on port `1025`; that service must run separately. Never put production credentials in `application-local.yml`.

You can use a fake `JavaMailSender` for unit tests to avoid opening network connections completely. For integration tests needing to inspect SMTP/MIME, use a dedicated test server and never point at a real provider.

### 4.2. CI/test

Automated tests must not depend on production provider quotas or real emails. Use test doubles or an SMTP test server and direct all recipients to controlled test addresses.

Never put production SMTP secrets into CI just to run a content test. When tests require a real provider sandbox, provision a dedicated sandbox credential with least privilege and proper rotation.

### 4.3. Staging

Staging may need to test TLS, templates, provider integrations, and callbacks. Even so, staging must have **separate** accounts/credentials. Restrict recipients via allowlists/sink domains and avoid production customer data unless governed by strict controls.

An additional safeguard is an **application-layer recipient guard**, such as permitting only registered internal test domains. Merely changing the SMTP host to a sandbox may not save you if an environment variable is misconfigured during deployment.

### 4.4. Production

Production uses dedicated credentials stored via a secret manager or controlled secret deployment mechanism. Access belongs to the workload identity, never a developer's personal account.

Production accounts should have dedicated alerts when:

- Credentials are used from unfamiliar hosts/IPs.
- Traffic spikes suddenly.
- Bounce/complaint rates rise.
- Quotas approach exhaustion.
- The provider reports a lock or rejects authentication.
- Sender identity is no longer verified.

## 5. Separating accounts by business function

An application may have multiple streams:

| Function | Examples | Characteristics |
| --- | --- | --- |
| Security | Password resets, account verification, login alerts | Sensitive, must reach the right person, high reliability priority |
| Transactional | Order confirmations, invoices, shipping | Carries transaction data, needs event-level tracing |
| Marketing | Newsletters, promotions, campaigns | High volume, strict consent/unsubscribe rules |
| Operations | System alerts to operations teams | Internal recipients, separate uptime and permission needs |

Using one account for everything lets marketing behavior affect security: shared quotas, complaints degrading sender reputation, or credentials leaking from a less-protected module.

### 5.1. Security/account mail

Password-reset and account-verification emails often contain sensitive tokens or links. This account should serve only authorized account/security workflows, never an arbitrary HTML-sending endpoint.

Recipients are normally pulled from verified account records or valid verification requests, not merely an arbitrary caller-supplied string. Tokens need expiration, scoping, and single-use policies where appropriate.

### 5.2. Transactional mail

Invoices, order updates, or appointment notices should tie to business events with idempotency keys and delivery tracking. The transactional account may need its own quota so critical notices are not delayed during large marketing campaigns.

### 5.3. Marketing mail

Marketing requires consent, unsubscribes, suppression lists, and rate limits. Marketing accounts are usually monitored separately for reputation/bounces/complaints. Never automatically fall back to security credentials just to bypass marketing throttling.

### 5.4. Operations/internal mail

Operational alerts may go to internal distribution lists. If this account shares the same provider as customer traffic, consider the risk of simultaneous provider outages. For SMTP incident alerts, you may need an **independent alerting channel** (monitoring/paging), not solely email through the very SMTP relay experiencing an outage.

## 6. Separating credentials is not the same as separating From addresses

Three distinct separation patterns exist:

~~~text
A. One credential, multiple From addresses:
   smtp-user-X → orders@example.org
               → security@example.org

B. Multiple credentials, same From address:
   smtp-user-S → notice@example.org
   smtp-user-T → notice@example.org

C. Multiple credentials and sender identities:
   smtp-user-S → security@example.org
   smtp-user-T → orders@example.org
   smtp-user-M → news@example.org
~~~

Option C expresses functional boundaries more cleanly, yet provides real security value only when the provider **enforces separate permissions and resource limits** on each account.

Address and domain choices must align with DNS authentication. Never arbitrarily assign a `From` domain that the provider has not verified.

### Sender policy differs from recipient policy

- **Sender policy:** which workflow may use which account/From/domain?
- **Recipient policy:** which recipients may receive specific content?
- **Content/template policy:** which notification types may be rendered and with what data?
- **Rate policy:** volume, speed, and priority of the sending stream.

A secure design needs all four. If a router selects accounts while callers can pass arbitrary HTML, recipients, and From addresses, abuse risk remains high.

## 7. SPF, DKIM, and DMARC when splitting accounts or domains

Splitting accounts may involve splitting domains/subdomains, for example:

~~~text
security.example.org
tx.example.org
news.example.org
~~~

These are architectural examples; not every application must split subdomains. Each sender domain must satisfy the mail provider's authentication requirements and organizational policy.

Key concepts:

| Mechanism | Role |
| --- | --- |
| SPF | Verifies authorized IPs/relays for the envelope sender domain |
| DKIM | Cryptographic signature bound to the domain in the `d=` tag |
| DMARC | Checks alignment of the From header domain with SPF or DKIM per policy |
| Domain verification | Provider verifies ownership/permission to configure the sender/domain |
| Bounce/Return-Path domain | Relates to the envelope and handling delivery failure responses |

If a security account sends from `security.example.org` with misconfigured DKIM/SPF, emails may be flagged as suspicious. Using a different credential **does not automatically make DMARC pass**.

### Alignment is more than “having an SPF record”

A message can pass SPF on its envelope sender domain yet still fail DMARC if that domain does not align with the `From` header per policy. DKIM also requires a valid signature and matching signing domain.

When adding a subdomain, check:

1. The domain/`From` address is permitted by the provider.
2. SPF/DKIM/DMARC are configured per organizational DNS policy.
3. DKIM selectors and keys are managed and rotated.
4. Bounces, return-paths, and webhooks route to the right account.
5. Staging does not accidentally emit messages resembling production mail.

Depending on the provider, DNS records may be CNAME or TXT entries specified by the provider; do not guess record values from a generic guide.

## 8. Spring Boot normally configures one default JavaMailSender

For simple cases:

~~~yaml
spring:
  mail:
    host: smtp.example.org
    port: 587
    username: ${SMTP_USERNAME}
    password: ${SMTP_PASSWORD}
    properties:
      mail.smtp.auth: true
      mail.smtp.starttls.enable: true
      mail.smtp.starttls.required: true
~~~

Spring Boot can auto-configure one `JavaMailSender` from `spring.mail.*` when auto-configuration conditions match. This is the **single default sender** model.

If the application has three SMTP accounts, changing `helper.setFrom` is not enough. You need independent `JavaMailSenderImpl` instances, each with its own host, port, username, password, and TLS config, selected through an appropriate routing layer.

### Avoid mixing two configuration styles unintentionally

When defining your own `JavaMailSender` `@Bean`, Spring Boot's mail auto-configuration may back off due to bean conditions. Do not expect `spring.mail.*` to always create a fourth sender alongside your custom beans.

Choose one clear architecture:

- **Single sender:** use `spring.mail.*` and Boot auto-config when appropriate.
- **Multiple senders:** use a dedicated namespace such as `app.mail.accounts.*`, build sender beans and routing explicitly, and keep `spring.mail.*` only if it serves a clear purpose.
- **Dynamic/tenant senders:** use a factory/registry with bounded caching, secret management, and tenant authorization.

## 9. Multi-account configuration model by purpose

Example production application with three accounts:

~~~yaml
app:
  mail:
    accounts:
      security:
        host: ${SMTP_SECURITY_HOST}
        port: 587
        username: ${SMTP_SECURITY_USER}
        password: ${SMTP_SECURITY_PASSWORD}
        from: security@example.org
        implicit-tls: false

      transactional:
        host: ${SMTP_TX_HOST}
        port: 587
        username: ${SMTP_TX_USER}
        password: ${SMTP_TX_PASSWORD}
        from: orders@example.org
        implicit-tls: false

      marketing:
        host: ${SMTP_MARKETING_HOST}
        port: 465
        username: ${SMTP_MARKETING_USER}
        password: ${SMTP_MARKETING_PASSWORD}
        from: news@example.org
        implicit-tls: true
~~~

This is a **syntax template**, not working credentials. Environment variables must be provisioned via an appropriate secret/deployment mechanism. Never commit passwords to repositories or share config files holding real secrets.

This snippet uses an `implicit-tls` flag to illustrate the two TLS modes:

- `false`: connect SMTP then upgrade with STARTTLS, typically on port 587.
- `true`: wrap the connection in TLS from the start, typically on port 465.

Port numbers are common conventions. Use host/port/TLS mode matching your provider contract rather than inferring blindly from port numbers.

### Do you need separate YAML files per environment?

You can use Spring profiles or externalized configuration:

~~~text
application.yml
application-local.yml
application-staging.yml
application-prod.yml
~~~

Never store production passwords inside profile files. Profile files should describe only **non-sensitive policies**, while secrets are injected by the deployment platform.

For instance, `application-staging.yml` can override accounts to sandbox settings and enable recipient allowlists. Control active profiles at runtime and put safeguards in place so staging cannot accidentally pick up production secret variables.

## 10. Reading configuration with `@ConfigurationProperties`

You can define a configuration type:

~~~java
import java.util.Map;

import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "app.mail")
public record MailAccountsProperties(
        Map<String, SmtpProfile> accounts) {

    public SmtpProfile require(String name) {
        if (accounts == null) {
            throw new IllegalStateException(
                    "app.mail.accounts is not configured"
            );
        }

        SmtpProfile profile = accounts.get(name);

        if (profile == null) {
            throw new IllegalStateException(
                    "Missing SMTP profile: " + name
            );
        }

        return profile;
    }

    public record SmtpProfile(
            String host,
            int port,
            String username,
            String password,
            String from,
            boolean implicitTls) {
    }
}
~~~

This record merely carries configuration data. In production, add explicit validation for host, port, username, password, `From`, and TLS conditions—such as combining Bean Validation or constructor invariants—rather than waiting until send time to discover a missing secret.

If your Spring Boot version has different binding or validation annotation details, configure accordingly in the project. The example emphasizes **separating profiles and reading externalized configuration**, requiring no special mail-routing library.

### Never log objects containing passwords

Java records auto-generate `toString()`, which prints all components including `password`. **Never log raw `SmtpProfile` or properties objects.**

Design secret wrappers whose `toString()` masks values, or isolate credentials in a dedicated component never emitted to logs, traces, Actuator, or error responses. For dynamic configurations, never return secret contents through management endpoints.

## 11. Creating independent `JavaMailSenderImpl` instances

A factory can build a sender from a profile:

~~~java
import java.nio.charset.StandardCharsets;
import java.util.Properties;

import org.springframework.mail.javamail.JavaMailSender;
import org.springframework.mail.javamail.JavaMailSenderImpl;

public final class SmtpSenderFactory {

    private SmtpSenderFactory() {
    }

    public static JavaMailSender create(
            MailAccountsProperties.SmtpProfile p) {

        JavaMailSenderImpl sender = new JavaMailSenderImpl();

        sender.setHost(p.host());
        sender.setPort(p.port());
        sender.setUsername(p.username());
        sender.setPassword(p.password());
        sender.setDefaultEncoding(
                StandardCharsets.UTF_8.name()
        );

        Properties mail = sender.getJavaMailProperties();

        mail.put("mail.transport.protocol", "smtp");
        mail.put("mail.smtp.auth", "true");

        if (p.implicitTls()) {
            // TLS from the start of the SMTP session.
            mail.put("mail.smtp.ssl.enable", "true");
            mail.put("mail.smtp.starttls.enable", "false");
        } else {
            // STARTTLS is mandatory; do not silently downgrade.
            mail.put("mail.smtp.ssl.enable", "false");
            mail.put("mail.smtp.starttls.enable", "true");
            mail.put("mail.smtp.starttls.required", "true");
        }

        // Verify hostname in certificate.
        mail.put("mail.smtp.ssl.checkserveridentity", "true");

        // Example timeouts, in milliseconds.
        mail.put("mail.smtp.connectiontimeout", "5000");
        mail.put("mail.smtp.timeout", "10000");
        mail.put("mail.smtp.writetimeout", "10000");

        return sender;
    }
}
~~~

Each factory call constructs a distinct `JavaMailSenderImpl`. Each sender holds the credentials and properties for its corresponding account.

**Things to avoid:**

- Never use `mail.smtp.ssl.trust=*` to bypass TLS verification.
- Never leave STARTTLS `enable=true` with `required=false` when security policy mandates TLS, as that risks continuing unencrypted under certain setups.
- Never mix implicit TLS and STARTTLS by guesswork.
- Never share a mutable `JavaMailSenderImpl` and overwrite `setUsername`/`setPassword` before each email; concurrent threads may send with each other's credentials.
- Never log `Session`, JavaMail properties, or exceptions in ways that leak credentials.

The example uses `JavaMailSenderImpl` and Jakarta Mail properties. Tune timeouts to your provider and message sizes; example numbers are not universal defaults for every service.

### TLS certificate verification

STARTTLS or implicit TLS only protects the connection when the client properly **verifies the certificate and hostname**. If production uses a private CA or custom truststore, configure the right trust chain instead of disabling verification.

Separate accounts with a downgraded or MITM'd SMTP connection remain a severe risk.

## 12. Registering three sender beans with clear names

~~~java
import org.springframework.boot.context.properties.EnableConfigurationProperties;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.mail.javamail.JavaMailSender;

@Configuration
@EnableConfigurationProperties(MailAccountsProperties.class)
public class MultipleMailSendersConfig {

    @Bean("securityMailSender")
    JavaMailSender securityMailSender(
            MailAccountsProperties properties) {

        return SmtpSenderFactory.create(
                properties.require("security")
        );
    }

    @Bean("transactionalMailSender")
    JavaMailSender transactionalMailSender(
            MailAccountsProperties properties) {

        return SmtpSenderFactory.create(
                properties.require("transactional")
        );
    }

    @Bean("marketingMailSender")
    JavaMailSender marketingMailSender(
            MailAccountsProperties properties) {

        return SmtpSenderFactory.create(
                properties.require("marketing")
        );
    }
}
~~~

Now the application has three beans of the same `JavaMailSender` type.

### `@Qualifier` and `@Primary`

If injected by type without a qualifier:

~~~java
public OrderMailService(JavaMailSender sender) {
    this.sender = sender;
}
~~~

Spring encounters multiple candidates unless a convention or primary bean specifies which one to pick. For sensitive SMTP flows, **explicitly selecting the sender** is usually safer than setting a default that services might accidentally use by mistake.

Example:

~~~java
public SecurityMailService(
        @Qualifier("securityMailSender")
        JavaMailSender sender) {
    this.sender = sender;
}
~~~

`@Primary` can be used when there is an unmistakable default and all other cases use `@Qualifier`. Still, an unexpected default can mask routing mistakes. For security/marketing accounts, designing **without an implicit default** is safer.

### Do not inject a Map by key without policy checks

Spring can inject `Map<String, JavaMailSender>` keyed by bean name. That helps for internal registries, yet never take the bean name straight from a request:

~~~java
// Avoid:
JavaMailSender sender = beanMap.get(request.getSenderName());
~~~

User requests must never be allowed to pick arbitrary credentials or accounts.

## 13. Route by purpose, not by user-supplied values

A central routing layer can choose accounts using an **application-controlled enum**:

~~~java
public enum MailPurpose {
    SECURITY,
    TRANSACTIONAL,
    MARKETING
}
~~~

Output of the application layer:

~~~java
public record ApprovedMail(
        MailPurpose purpose,
        String recipient,
        String subject,
        String plainText,
        String htmlText) {
}
~~~

The name `ApprovedMail` signifies that the application contract has already enforced recipient/content authorization before creating it. The type name alone does not create security; entry points must still follow policies, module visibility, and testing.

### A routing gateway

~~~java
import java.util.EnumMap;
import java.util.Map;

import jakarta.mail.MessagingException;
import jakarta.mail.internet.MimeMessage;

import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.mail.javamail.JavaMailSender;
import org.springframework.mail.javamail.MimeMessageHelper;
import org.springframework.stereotype.Component;

@Component
public final class MailRoutingGateway {

    private final Map<MailPurpose, SenderBinding> accounts;

    public MailRoutingGateway(
            @Qualifier("securityMailSender")
            JavaMailSender securitySender,

            @Qualifier("transactionalMailSender")
            JavaMailSender transactionalSender,

            @Qualifier("marketingMailSender")
            JavaMailSender marketingSender,

            MailAccountsProperties config) {

        EnumMap<MailPurpose, SenderBinding> map =
                new EnumMap<>(MailPurpose.class);

        map.put(
                MailPurpose.SECURITY,
                new SenderBinding(
                        securitySender,
                        config.require("security").from()
                )
        );

        map.put(
                MailPurpose.TRANSACTIONAL,
                new SenderBinding(
                        transactionalSender,
                        config.require("transactional").from()
                )
        );

        map.put(
                MailPurpose.MARKETING,
                new SenderBinding(
                        marketingSender,
                        config.require("marketing").from()
                )
        );

        this.accounts = Map.copyOf(map);
    }

    public void send(ApprovedMail mail)
            throws MessagingException {

        SenderBinding binding =
                accounts.get(mail.purpose());

        if (binding == null) {
            throw new IllegalArgumentException(
                    "No account configured for mail purpose"
            );
        }

        MimeMessage message =
                binding.sender().createMimeMessage();

        MimeMessageHelper helper =
                new MimeMessageHelper(
                        message, true, "UTF-8"
                );

        // From is determined by the approved account configuration.
        helper.setFrom(binding.from());
        helper.setTo(mail.recipient());
        helper.setSubject(mail.subject());
        helper.setText(
                mail.plainText(),
                mail.htmlText()
        );

        binding.sender().send(message);
    }

    private record SenderBinding(
            JavaMailSender sender,
            String from) {
    }
}
~~~

In the example, `MailRoutingGateway` receives the separated beans and selects the account by `MailPurpose`. `From` is also bound to the account, never taken from request payloads.

This is the transport layer; recipient and permission checks must still occur beforehand. In large applications, add a `MailPolicy` or factory that constructs `ApprovedMail` only after validating the use case.

### Why route by enum?

A fixed enum constrains transport options. A caller may request “send order confirmation”, and the application service resolves that as `TRANSACTIONAL`. A public request must never be allowed to switch purpose from `MARKETING` to `SECURITY` to bypass quotas or suppressions.

## 14. Boundary between application service and transport

A clean flow:

~~~mermaid
flowchart TD
    A["HTTP / Scheduler / Event"] --> B["Application service"]
    B --> C["Authorization + recipient policy"]
    C --> D["Determine MailPurpose"]
    D --> E["Render template from valid data"]
    E --> F["ApprovedMail"]
    F --> G["MailRoutingGateway"]
    G --> H{"Purpose?"}
    H -->|"SECURITY"| I["securityMailSender"]
    H -->|"TRANSACTIONAL"| J["transactionalMailSender"]
    H -->|"MARKETING"| K["marketingMailSender"]
    I --> L["SMTP relay"]
    J --> L
    K --> L
~~~

Controllers merely accept requests, build commands, and invoke use cases. They should not know SMTP passwords, target hosts, or `From` addresses.

**Recipient policy** should distinguish:

- Security: recipient determined by verified auth workflow, preventing token leakage.
- Transactional: contact belongs to the right transaction/tenant and event type.
- Marketing: consent, unsubscribe, suppression, and send limits.
- Staging: recipient belongs to the testing allowlist.
- Internal notifications: only approved groups/addresses.

Just because an email address is syntactically valid does not mean it is authorized to receive data from that use case.

## 15. Separating accounts in multi-tenant systems

Multi-tenant systems raise another question: **should each tenant use a separate sender/account, or share a platform account?**

Models:

| Model | Pros | Cons |
| --- | --- | --- |
| Shared platform account | Easy to deploy and operate | Tenants may share quotas/reputation |
| Account per tenant tier/group | Balances cost and isolation | More complex mapping rules |
| Dedicated account per tenant | Stronger domain/credential isolation if supported by provider | More secrets, rotations, and connections |
| Tenant uses their own provider | Clear ownership of sender domain | Requires onboarding, validation, safe credential handling |

Never assume a client-supplied `tenantId` suffices to choose credentials. The application service must verify the caller belongs to the tenant and holds resource permissions, and only then does the resolver select the matching sender profile.

Example:

~~~java
public record SenderSelection(
        UUID tenantId,
        MailPurpose purpose,
        String approvedAccountId) {
}
~~~

The account ID must resolve from authoritative tenant config; never take raw SMTP host/username/password from HTTP bodies. A registry may query a secret manager by account ID, with caching/TTL, concurrency control, auditing, and rotation.

### Avoid turning the app into an open relay

An API allowing clients to pass arbitrary **recipient + HTML + From + SMTP account ID** can be abused for spam/phishing and credential misuse. Restrict use cases, template types, recipients, quotas, and sending permissions before reaching the gateway.

## 16. Never mutate credentials on a shared sender

Dangerous pattern when trying to reuse one mutable `JavaMailSenderImpl`:

~~~java
// Unsafe when multiple threads send concurrently:
sharedSender.setUsername(account.username());
sharedSender.setPassword(account.password());
sharedSender.send(message);
~~~

Two threads can interleave:

~~~text
Thread A: setUsername/security
Thread B: setUsername/marketing
Thread A: send
~~~

A security message could then be sent using marketing credentials or fail with unpredictable authentication errors. Never alter host, port, password, or JavaMail properties on a singleton sender to route individual emails.

Solutions:

- Create an operationally immutable sender bean per account.
- For dynamic accounts, construct dedicated senders per profile and hold them in a controlled registry.
- Swap references/senders cleanly during credential rotation rather than mutating objects shared across threads.
- Isolate credentials so only the transport layer can read them.

Note that `JavaMailSenderImpl` is not immutable by class design, yet can be used as a **bean with fixed configuration after startup**, calling no setters on send paths.

## 17. SMTP secrets: where to store them and where not to

SMTP passwords/tokens are credentials authorizing sending on behalf of a domain or account. Protect them like any other application secret.

Never put secrets directly into:

- Java/Kotlin source code.
- YAML or properties files committed to Git.
- Unit test snapshots and golden files.
- Hardcoded Dockerfile `ENV` directives.
- Logs, stack trace dumps, Actuator config exposures, or error responses.
- Tickets, chats, public docs, or configuration screenshots.

Instead use:

- A secret manager or platform-provided secret store.
- Environment injection/volume mounts via protected deployment mechanisms.
- IAM/service identities for workloads, restricting read access.
- RBAC and auditing on secret access.
- Per-account and per-environment rotation/revocation.
- Masking/scrubbing across logs, diagnostics, and monitoring.

### Environment variables are not automatically completely safe

Environment variables are better than committing passwords, yet can leak via debug dumps, process management tools, pipeline logs, or host access. Harden runtime environments and restrict who can view deployment secrets.

### Beware record `toString()`

If using `record SmtpProfile(..., String password, ...)`, Java's generated `toString()` can print the password into logs. Never log whole config objects, and consider wrapping secrets in a type whose representation masks the value.

## 18. Credential rotation and revocation

When a marketing credential leaks, the organization must be able to:

1. Revoke the marketing credential alone.
2. Create a new credential with required permissions.
3. Update the secret store/deployment.
4. Roll/restart or safely swap the sender instance to load the new credential.
5. Verify the marketing account works.
6. Monitor anomalous traffic and review sent notifications.

If every flow shared one credential, revoking it would halt both security and transactional mail. Separation shrinks the impact scope.

### Do not assume changing the secret updates the sender immediately

A `JavaMailSenderImpl` created at startup normally holds the configured username/password. When the secret store changes, the existing bean **does not automatically reload**. You need an explicit rotation strategy: restart/rolling deployment, managed refresh, or synchronized sender instance swap.

During rotation, avoid mutating passwords on a singleton used concurrently. You can allow a dual-credential transition window if supported by the provider, while never keeping old credentials active longer than necessary.

### Distinguishing rotation from failover

Rotation replaces an account's credential. Failover switches to a backup provider/account when the current account is unavailable. Failing over across functions must check sender identities, consent, quotas, and domain policies; **never automatically grab security credentials to send marketing mail**.

## 19. TLS and SMTP authentication

Separating accounts means less if credentials travel over an improperly secured connection. Distinguish the two modes:

### 19.1. STARTTLS

Normally the connection starts as SMTP and upgrades to TLS:

~~~properties
mail.smtp.auth=true
mail.smtp.starttls.enable=true
mail.smtp.starttls.required=true
mail.smtp.ssl.checkserveridentity=true
~~~

`required=true` prevents continuing if the server does not support upgrading to TLS when policy demands it. Verify certificates and hostnames properly.

### 19.2. Implicit TLS

TLS connection from the very beginning of the session:

~~~properties
mail.smtp.auth=true
mail.smtp.ssl.enable=true
mail.smtp.ssl.checkserveridentity=true
~~~

Do not rely solely on port numbers to guess configuration; providers may use custom ports or endpoints.

### 19.3. Configurations not to use as “quick fixes”

Avoid configuring:

~~~properties
mail.smtp.ssl.trust=*
mail.smtp.starttls.required=false
~~~

and assuming all connections remain protected. `ssl.trust=*` weakens certificate trust controls; `required=false` can permit downgrades in STARTTLS setups. All TLS decisions must be reviewed against your threat model and provider contract.

### 19.4. Timeouts

Even with multiple accounts, a hanging SMTP connection can exhaust thread pools:

~~~properties
mail.smtp.connectiontimeout=5000
mail.smtp.timeout=10000
mail.smtp.writetimeout=10000
~~~

Values are in milliseconds; tune for latency and email sizes. Never set infinite timeouts expecting `@Async` to solve resource exhaustion.

## 20. Account separation and traffic limiting

Providers may enforce quotas at multiple levels:

- SMTP user.
- Provider account/subaccount.
- Sending domain.
- IP pool.
- Tenant or organization.
- Total messages/recipients per time window.

Separating users does not guarantee separate quotas if the provider meters at the parent account level. Measure in practice and verify the contract.

A priority allocation policy:

| Stream | Goal | Strategy |
| --- | --- | --- |
| Security | Low latency, minimal disruption | Small prioritized pool, reserved quota |
| Transactional | Reliable event-driven sending | Queue/outbox, retries, and idempotency |
| Marketing | High volume, deferrable | Rate limits, batching, suppression |
| Operations | May need to work during primary SMTP outage | Separate alert channel or independent provider |

If every purpose still shares one `ThreadPoolTaskExecutor` or unbounded queue, separated accounts can still contend for JVM resources. When needed, separate executors/queues, concurrency caps, and retry policies by purpose.

## 21. Retries, fallbacks, and account boundaries

Suppose the marketing account receives throttling errors from the SMTP relay. Should jobs move over to the security account?

**Not by default.** Doing so can break quota isolation, sender policies, complaint handling, or consent rules. Distinguish:

- Retry the same account after backoff.
- Rotate the same account's credential per procedure.
- Fail over to a backup account/provider pre-approved for the **same purpose**.
- Pause the campaign to avoid impacting other systems.

A simple policy interface:

~~~java
public interface MailRoutePolicy {
    SenderAccount resolve(
            MailPurpose purpose,
            UUID tenantId);
}
~~~

The policy determines permitted sending routes. If fallbacks exist, backup routes must be pre-configured and authorized rather than falling back simply because another credential “still works”.

### The outbox needs purpose, never SMTP passwords

An outbox job may contain:

~~~json
{
  "jobId": "mail-job-123",
  "eventId": "evt-981",
  "purpose": "TRANSACTIONAL",
  "recipientContactId": "contact-77",
  "templateCode": "ORDER_CONFIRMED",
  "status": "PENDING"
}
~~~

The worker reads the job, checks recipient policies for the purpose, and asks the routing gateway for the account. Never store raw SMTP passwords in outbox payloads.

On retry, **the purpose and idempotency key of the send intent stay stable**. If an account rotates, the same purpose uses the new credential per policy. If failing over to a different provider, consider the risk that the earlier attempt was accepted by the first relay with an uncertain outcome; resending could cause duplicates.

## 22. Staging guards cannot rely solely on SMTP accounts

A staging config can accidentally point at a production account due to a CI/deployment mistake. Use layered defenses:

1. Separate staging credentials; never grant production credentials to staging.
2. Staging sender identities clearly distinguishable from production.
3. Application-layer recipient allowlists or sinks.
4. Guards rejecting any address outside test scope.
5. Provider sandboxes where appropriate.
6. Configuration checks at startup/deployment.
7. Alerts if staging generates unusual send volumes.

Example policy:

~~~java
@Component
@Profile("staging")
public class StagingRecipientGuard {

    private final Set<String> allowedDomains =
            Set.of("qa.example.org", "internal.example.org");

    public void requireAllowed(String email) {
        String domain = extractValidatedDomain(email);

        if (!allowedDomains.contains(
                domain.toLowerCase(Locale.ROOT))) {

            throw new IllegalArgumentException(
                    "Staging cannot send to this recipient"
            );
        }
    }
}
~~~

`extractValidatedDomain` is an application-implemented utility/parser; the snippet simply illustrates where policy is enforced. In production, use a proper email parser and never rely solely on `endsWith("example.org")` because addresses like `evil-example.org` can slip past naive suffix checks.

**Important:** The recipient guard must be invoked by the shared application boundary through which every send flow passes. A declared component that is never called offers no protection.

### Never rely on `@Profile` as the sole security control

Profiles are runtime configuration switches and can be activated wrongly. Credential segmentation, secret access policies, and recipient guards must coexist to lower risk.

## 23. Auditing, logging, and monitoring per account

Separating accounts improves observability when each send records metadata:

~~~text
mail_request_id: req-789
business_event_id: evt-981
purpose: SECURITY
environment: production
sender_profile: security
recipient_contact_id: contact-77
smtp_result: ACCEPTED
duration_ms: 842
attempt: 1
~~~

Never log usernames/passwords, reset tokens, or full HTML email bodies. You do not need to log full recipient addresses either; use contact IDs or masking per policy.

Metrics to track separately:

- SMTP AUTH failures per account.
- TLS handshake/certificate failures.
- SMTP latency and timeouts.
- Provider throttling, quotas, and rejections.
- Bounces/complaints/unsubscribes per purpose.
- Emails sent per account and environment.
- Fallback counts and reasons.
- Outbox backlog, retry counts, and wait durations.
- Anomalies in sender identity or domain verification.

### “Sent” status is not “delivered”

`JavaMailSender.send(...)` returning normally indicates the transport accepted the submission per the API—it does not prove the message reached the recipient's inbox. The provider may bounce or defer it afterward. If delivered status is required, integrate provider feedback/webhooks or equivalent tracking mechanisms.

Separating accounts makes tracing provider feedback cleaner, yet does not add delivery confirmation by itself.

## 24. Testing routing and environment guards

Test security boundaries rather than only checking pretty HTML rendering.

### 24.1. Unit testing right sender selection

With three fake `JavaMailSender` instances, verify:

- `SECURITY` calls only the security sender, never the marketing sender.
- `TRANSACTIONAL` calls the transactional sender.
- `MARKETING` calls the marketing sender.
- `From` comes from the matching account configuration.
- Unconfigured purposes fail closed without falling back to an arbitrary sender.

Example test skeleton:

~~~java
@Test
void securityMailUsesSecuritySender() {
    ApprovedMail mail = new ApprovedMail(
            MailPurpose.SECURITY,
            "tester@example.org",
            "Account verification",
            "Verification code...",
            "<p>Verification code...</p>"
    );

    gateway.send(mail);

    // Assert securitySender was called.
    // Assert transactionalSender/marketingSender were not called.
}
~~~

This is an illustrative test skeleton. In real tests, capture the `MimeMessage` or use fake senders to verify messages and send counts.

### 24.2. Testing that local/staging never sends to production

- Active profile is right.
- Staging runtime cannot read production secrets.
- Recipients outside the allowlist are rejected.
- Staging SMTP endpoints point to a sandbox/test catcher.
- Staging credentials lack permission to use production sender domains when forbidden by policy.
- Tests use fake/sandbox senders and never email real users.

### 24.3. Testing multi-bean configuration

- `securityMailSender`, `transactionalMailSender`, and `marketingMailSender` beans are present.
- No dependency injection ambiguity in critical services.
- Each bean has the right host, port, TLS mode, and account.
- Missing mandatory profiles/secrets fail startup per policy rather than silently falling back to a default sender.
- No debug/test beans are active outside intended environments.

### 24.4. Integration testing with an SMTP test server

An SMTP test server lets you inspect:

- Envelope and sender headers.
- `From`, `Reply-To`, `To`, `Cc`, `Bcc`.
- Plain/HTML MIME bodies and attachments.
- TLS/SMTP AUTH when supported by the test server.
- Simulated timeouts, AUTH rejections, and provider throttling.

Avoid production credentials in automated tests. If testing directly against a provider, use sandbox accounts and controlled recipients.

## 25. Common configuration mistakes

### 25.1. Changing only `From` without changing the account

Sending security emails with `From=security@example.org` while still using marketing username/password. Select the right `JavaMailSender` and verify the provider permits that `From`.

### 25.2. Sharing production credentials in staging

Staging can send real mail or leak secrets via logs/debugging. Create separate sandbox credentials and never grant production secrets to staging workloads.

### 25.3. Letting requests pick arbitrary SMTP profiles

External requests must never switch marketing purpose to security or pick high-privilege accounts. Route based on authenticated use cases and internal policies.

### 25.4. Using one mutable sender and swapping passwords before every send

Concurrent sends can race and use the wrong credentials. Build separate senders or a thread-safe registry with fixed configs.

### 25.5. Using `@Primary` to mask missing routing

A service forgetting `@Qualifier` could silently grab the wrong functional default sender. When accounts have distinct security boundaries, prefer explicit routing.

### 25.6. Splitting credentials while quotas stay shared

Providers may enforce quotas/reputation at the parent account level. Verify real quota boundaries instead of assuming multiple usernames equal isolation.

### 25.7. Skipping SPF/DKIM/DMARC when changing `From`/subdomains

Valid credentials can still lead to rejected or spam-foldered mail due to misaligned domain authentication.

### 25.8. Disabling TLS verification just to connect

`ssl.trust=*` or optional STARTTLS breaks connection protection. Configure truststores/certificates properly.

### 25.9. Logging entire `@ConfigurationProperties` objects

Records with passwords in `toString()` can expose credentials. Mask secrets and avoid dumping properties.

### 25.10. Updating the secret store without reloading senders

Rotated credentials leave singleton senders holding old passwords. Perform rolling restarts or managed instance swaps.

### 25.11. Automatically failing over marketing to security

Can bypass restrictions or exhaust security email quotas. Fail over only to accounts pre-approved for the same purpose.

### 25.12. Having no recipient guard in non-production

Even sandbox accounts or right profiles can be misconfigured. Enforce allowlists and policies at application boundaries to cut risk.

### 25.13. Assuming different accounts mean completely separate IP reputation

Accounts at the same provider may share IP pools or reputation policies. Verify actual isolation mechanisms when required.

### 25.14. Treating SMTP credentials as permission to send any content

Even if the account authenticates, the application must still verify resource permissions, consent, recipients, tenants, and templates.

### 25.15. Not limiting sending rates per function

Splitting credentials while sharing one unbounded queue and thread pool can still cause bottlenecks or provider throttling. Add bounded queues, rate limits, and prioritization.

## 26. Practice questions

**Q1.** You have two addresses `security@example.org` and `news@example.org` using the same SMTP username/password. Have you separated accounts?

No. Those are only two sender identities if the credential stays the same; account principal, quotas, and permissions may still be shared.

**Q2.** Can you simply call `helper.setFrom("security@example.org")` to pick the security account?

No. `setFrom` only sets a header; you must select the `JavaMailSender` with the right credentials and confirm the provider permits that sender identity.

**Q3.** Should staging use production credentials because `@Profile("staging")` is active?

No. Profiles can be misconfigured and do not restrict credential permissions. Use separate staging secrets, provider sandboxes, and recipient guards.

**Q4.** Why should marketing and security be isolated?

Because they differ in risk, consent, quotas, sender reputation, and reliability requirements. A marketing incident should not automatically disrupt password resets.

**Q5.** Does using two SMTP users under the same provider account guarantee independent quotas?

No. Check at which level the provider enforces quotas and reputation.

**Q6.** Can clients pass `smtpAccountName` to a mail-sending endpoint?

No. Clients must be authorized to execute a use case; internal application policy chooses the account.

**Q7.** Is `@Primary` always a good idea when having three `JavaMailSender` beans?

No. A default sender can hide places where someone forgot to specify the account. For sensitive streams, explicit routing or clear `@Qualifier` annotations are usually safer.

**Q8.** Why shouldn't a singleton `JavaMailSenderImpl` be mutated while sending multiple emails?

Because threads can interleave modifications to username/password/host, sending emails through the wrong account or causing unpredictable errors.

**Q9.** The marketing credential leaked. How does separation help?

It lets you revoke/rotate the marketing credential alone, reducing impact on security and transactional credentials, provided the provider truly isolates their permissions.

**Q10.** Does STARTTLS `enable=true` always guarantee mail never travels over plaintext?

Not if configuration/policy fails to mandate TLS. When TLS is required, set `required=true` and verify certificates/hostnames.

**Q11.** Does sending an email successfully via SMTP prove SPF/DKIM/DMARC are valid?

No. Transport submission and domain authentication/deliverability are separate layers.

**Q12.** An outbox job stores `MailPurpose.TRANSACTIONAL`. On retry, should it automatically switch to an idle marketing account?

Not by default. Retries must preserve business purpose and follow approved account/failover policies.

**Q13.** Why separate staging and production accounts even when they share the same templates?

Because environments, data, recipients, and blast radius differ. Identical templates do not make production credentials safe to use in staging.

**Q14.** If separate accounts share one thread pool, are the streams completely isolated?

No. They can still contend for threads, queues, memory, and provider quotas. Operational isolation may need dedicated executors, queues, and rate policies.

## 27. Mental model to remember

~~~mermaid
flowchart TD
    A["Request / Event"] --> B["Application use case"]
    B --> C["Authorization + recipient policy"]
    C --> D["Mail purpose determined internally"]
    D --> E["Routing gateway"]
    E --> F{"Function?"}
    F -->|"SECURITY"| G["Security SMTP account"]
    F -->|"TRANSACTIONAL"| H["Transactional SMTP account"]
    F -->|"MARKETING"| I["Marketing SMTP account"]
    G --> J["SMTP provider"]
    H --> J
    I --> J
    K["Local/Staging/Prod policies"] --> E
    L["Secret manager + TLS + domain policy"] --> E
~~~

Keep in mind:

1. **Separating accounts means separating principals/credentials and permissions**, not just swapping `From` addresses.
2. **Separate by environment** so dev/staging cannot accidentally send with production secrets.
3. **Separate by function** when security, transactional, and marketing differ in permissions, quotas, consent, or risk.
4. **Verify the provider's real isolation boundaries**; multiple SMTP users do not automatically guarantee independent quotas/reputation.
5. **Each SMTP account has its own transport configuration**, including host, port, username, password, and TLS mode.
6. **Spring Boot `spring.mail.*` typically describes one sender**, whereas multiple accounts require multiple beans or an application-managed registry.
7. **Route explicitly by `MailPurpose` and internal policy**, never by client-supplied raw account names/`From` values.
8. **Keep sender configurations fixed during sends**, avoiding mutating singletons across threads.
9. **Manage secrets, rotation, revocation, and log masking** at runtime; never commit credentials.
10. **STARTTLS/implicit TLS require certificate verification**, and sender domains need SPF/DKIM/DMARC configured per provider.
11. **Separating accounts does not replace recipient authorization, consent, suppression, or idempotency.**
12. **Test environments, routing, negative cases, and monitor quotas/rejections** before running in production.

In Spring Framework Mail, `JavaMailSenderImpl` represents a specific SMTP transport configuration; `MimeMessageHelper` builds the message; and application services plus the routing gateway decide **which account is permitted for which notification type**. When accounts are separated properly by environment and function, applications shrink blast radius if a credential leaks, prevent accidental real emails from test environments, and operate critical notification streams independently with stronger control.
