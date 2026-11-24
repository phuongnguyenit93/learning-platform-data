# Configuring Senders by Tenant or Domain

A **Spring Framework Mail** application often starts with one SMTP account and one `JavaMailSender`: every email shares the same host, username, password, and `From` address. That works for a single-organization product. However, in a **multi-tenant** system, each enterprise customer may use its own sending domain, brand identity, notification policies, or even a different SMTP provider.

Suppose a platform serves two organizations:

~~~text
Tenant Acme:
  Sending domain: mail.acme.example
  From: orders@mail.acme.example
  SMTP provider: Relay A
  Account: acme-transactional

Tenant Beta:
  Sending domain: notify.beta.example
  From: notices@notify.beta.example
  SMTP provider: Relay B
  Account: beta-primary
~~~

If the application only changes `helper.setFrom(...)` while continuing to use Acme's credentials to send Beta's emails, the system **has not truly selected a sender by tenant**. The provider may reject the message, DNS authentication may fail alignment, or two tenants may end up sharing one account's quotas and permissions. Conversely, if clients are allowed to enter an arbitrary SMTP host, password, and sender account on each request, the application risks becoming an unauthorized mail-relay channel.

**Configuring senders by tenant or domain** means the application enforces an **authoritative routing policy**: verifying the real tenant, selecting an approved sending domain, determining the email purpose, selecting a provider/account authorized for that domain, loading credentials securely, building the MIME message with appropriate From/Reply-To, and sending over the chosen transport. This lesson covers the architecture, Spring Boot configuration, `JavaMailSenderImpl`, dynamic registries, security, DNS, failover, outbox, quotas, feedback, and testing strategies.

## 1. Concepts That Must Be Separated

| Concept | Example | Meaning |
| --- | --- | --- |
| Tenant | `tenant-acme` | Customer unit with its own data and permissions |
| Sending domain | `mail.acme.example` | Domain used for identity and email authentication |
| Provider | Relay A | Mail-sending service provider |
| Provider account/subaccount | `acme-tx` | Scope of credentials, quotas, and policies at the provider |
| SMTP endpoint | `smtp.relay-a.example:587` | Host/port accepting connections |
| SMTP credential | Username/password/token | Secret for SMTP AUTH |
| Header From | `orders@mail.acme.example` | Sender identity displayed to the recipient |
| Reply-To | `support@acme.example` | Address receiving replies |
| Envelope sender | `bounce@bounces.acme.example` | SMTP MAIL FROM, tied to bounces |
| Mail purpose | `SECURITY` / `TRANSACTIONAL` | Business classification of the notification |
| Sender route | Tenant + domain + purpose → account | Rule selecting an allowed transport |

Relationships are not necessarily one-to-one. A tenant can use multiple domains, a domain can have multiple accounts, a provider can serve multiple tenants, and a tenant can also have both primary and backup providers.

You must distinguish **sender identity** from **SMTP principal**. Showing an address in Header From does not prove the SMTP account is authorized to send on behalf of that domain. Changing From is not the same as changing the account.

## 2. Why Is Tenant-Based Routing Needed?

Key drivers:

1. **Branding:** emails to Acme's customers use Acme's verified identity.
2. **Permissions:** tenant A does not use tenant B's credentials or domains.
3. **Blast-radius isolation:** revoking one tenant's credentials does not automatically stop all other tenants.
4. **Quotas:** traffic can be allocated and metered by tenant, account, purpose, and provider.
5. **Sending reputation:** bounces/complaints from bulk marketing should not damage the security stream more than infrastructure forces.
6. **Compliance:** some tenants require restricting providers, processing regions, or retention.
7. **Operations:** you can switch providers, rotate credentials, pause domains, and audit routes.
8. **Scalability of development:** onboarding a new tenant does not require editing email-sending business logic.

Separating SMTP usernames does not necessarily fully isolate quotas/reputation. A provider may enforce limits at the **organization, parent account, IP pool, or sending domain** level. When strict isolation matters, verify at what level the provider actually isolates.

## 3. Common Sender-Isolation Models

| Model | Characteristics | Strengths | Risks/Costs |
| --- | --- | --- | --- |
| Single platform account | All tenants share credentials | Simple | Shared quota, hard to isolate |
| Account per tenant tier/group | Tenants grouped by plan/region | Balances resources | Requires policy mapping |
| Dedicated account per tenant | Independent credentials/subaccount | Easy to revoke and audit | Many secrets and configs |
| Dedicated domain per tenant | From uses verified domain | Clear branding | Requires DNS onboarding |
| BYO provider | Tenant supplies account/provider | Flexible | Egress, TLS, secrets, and abuse |
| Hybrid | Small tenants shared, large tenants dedicated | Matches SLAs | More complex router and billing |

A small platform can start with a set of verified platform accounts separated by purpose. When a tenant needs its own domain/credentials, the router can select a dedicated account. There is no need to force every tenant to create separate SMTP credentials if the product does not require it.

## 4. Tenant, Domain, and Purpose Jointly Determine the Route

A sound routing key can be:

~~~text
environment
  + authenticatedTenantId
  + mailPurpose
  + verifiedSendingDomainId
  -> approved provider account
~~~

Example:

| Tenant | Sending domain | Purpose | Account |
| --- | --- | --- | --- |
| Acme | `mail.acme.example` | Transactional | `acme-tx` |
| Acme | `security.acme.example` | Security | `acme-security` |
| Acme | `news.acme.example` | Marketing | `acme-marketing` |
| Beta | `notify.beta.example` | Transactional | `beta-primary` |
| Beta | `notify.beta.example` | Security | `beta-security` |

If one tenant has multiple domains all serving transactional mail, keying only on `(tenantId, purpose)` may not be enough; a verified domain/brand ID is needed.

Do not derive a domain by string concatenation from the tenant name and assume the tenant owns it. Allowed domains must come from a **trusted onboarding/verification record**.

## 5. Four Boundaries That Must Be Controlled

~~~mermaid
flowchart TD
    A["Authenticated principal / trusted event"] --> B["Tenant authorization"]
    B --> C["Recipient + business policy"]
    C --> D["Verified domain + mail purpose"]
    D --> E["TenantSenderRouter"]
    E --> F["Approved account"]
    F --> G["SenderRegistry"]
    G --> H["JavaMailSender"]
    H --> I["SMTP provider"]
~~~

**Tenant authorization:** which tenant's data is the caller authorized to act on?

**Recipient policy:** who is the notification sent to? Does the recipient address belong to the workflow and is it permitted to receive this data?

**Sender policy:** which domain/From is the tenant permitted to use, and for which purpose?

**Transport policy:** which credentials, provider, TLS, quota, retries, and fallback are permitted?

Never replace these four boundaries with a single `request.getTenantId() != null` check or with successful SMTP AUTH. A message can submit successfully yet still send wrong data/recipients across tenants.

## 6. Header From Is Not SMTP AUTH

An email may carry these details:

~~~text
SMTP AUTH username:
  smtp-user-acme-tx

SMTP MAIL FROM:
  bounce@bounces.acme.example

Message headers:
  From: Orders <orders@mail.acme.example>
  Reply-To: support@acme.example
  To: buyer@example.org
~~~

- SMTP AUTH proves permission to use the account with the relay.
- From is the sender identity shown in the message.
- Reply-To only suggests where replies should go.
- SMTP MAIL FROM is the envelope identity used for delivery status/bounces.
- Return-Path is typically added during delivery; do not manually set a Return-Path header to substitute for envelope configuration.

In the Jakarta Mail SMTP transport, some cases use the `mail.smtp.from` property to specify the envelope sender. It is a transport/session property, not a simple per-mail field you can mutate on a singleton `JavaMailSenderImpl` without risking race conditions. Many providers also manage bounce domains/custom MAIL FROM via a dedicated dashboard or API.

## 7. SPF, DKIM, and DMARC per Sending Domain

When a tenant wants to use `mail.acme.example`, the application/provider must verify and configure the domain. Related layers:

| Mechanism | Purpose |
| --- | --- |
| Domain verification | Proves authority to use the sending domain with the provider |
| SPF | Authorizes sending IPs/relays for the envelope sender domain |
| DKIM | Signs the message with domain `d=` and selector |
| DMARC | Checks alignment of the Header From domain with SPF or DKIM |
| Custom bounce domain | Handles returned mail/Return-Path per provider |

**Valid SMTP credentials do not guarantee SPF/DKIM/DMARC pass.** The domain may be unverified, the DKIM signature wrong, or SPF passing on the envelope domain yet failing alignment with From under the DMARC policy.

If the same domain sends through two providers:

- Both must be authorized to use the sender identity.
- Each provider's DNS records must be configured properly without conflicts.
- DKIM selectors may be distinct per provider.
- Bounce/return-path setup must be appropriate.
- Alignment must be checked, not merely whether an SPF record exists.
- Never add DNS records by guesswork without following the provider's contract.

A DNS record that is valid for Relay A does not automatically mean Relay B is ready as a backup sender.

## 8. Stateful Sending-Domain Onboarding

A tenant cannot simply enter any domain and start sending production traffic immediately. A workflow can look like:

~~~mermaid
flowchart TD
    A["Tenant admin registers domain"] --> B["Check permissions + uniqueness"]
    B --> C["Generate verification challenge"]
    C --> D["Provide DNS record instructions"]
    D --> E["Check DNS / provider"]
    E --> F{"Verified?"}
    F -->|"No"| G["PENDING_DNS"]
    G --> E
    F -->|"Yes"| H["Verify sender identity and DNS auth"]
    H --> I["ACTIVE"]
    I --> J["Allow production routing"]
~~~

Illustrative states:

~~~text
REQUESTED
PENDING_DNS
VERIFYING
ACTIVE
SUSPENDED
REVOKED
~~~

Only `ACTIVE` is allowed for production sending per policy. If verification lapses or the tenant loses permission to use the domain, routing must stop accordingly.

Fields to persist may include: `tenantId`, `domainId`, `canonicalDomain`, `verificationStatus`, `providerVerificationId`, `allowedFromIdentities`, `allowedPurposes`, `configVersion`, `verifiedAt`, and `revokedAt`.

**A domain belonging to another tenant** must be treated as an ownership conflict, never auto-approved just because two tenants entered the same string.

## 9. One Tenant with Multiple Domains

Tenant Acme might use:

~~~text
mail.acme.example       -> Orders
security.acme.example   -> Password reset
news.acme.example       -> Newsletter
~~~

A routing model using a domain ID avoids accepting raw strings from requests:

~~~java
public record RouteKey(
        String tenantId,
        MailPurpose purpose,
        String sendingDomainId) {
}
~~~

Using an approved domain ID also helps handle renames/ownership changes, IDN canonicalization, and versioning.

Do not validate domains using:

~~~java
email.endsWith("acme.example")
~~~

An address with domain `evil-acme.example` shares the same suffix. You must parse the address and compare the canonicalized domain structurally rather than doing arbitrary string suffix checks. If internationalized domains are supported, apply consistent canonicalization and check ownership against the canonical domain form.

## 10. Spring Boot Single Default Sender

When there is only one SMTP relay, the familiar configuration is:

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

Spring Boot can auto-configure a `JavaMailSender` when auto-configuration conditions match. However, `spring.mail.*` does not automatically look up tenant/domain accounts from a database.

For multi-tenancy, a dedicated configuration and routing layer is needed. If you declare custom `JavaMailSender` beans, Boot's mail auto-configuration may back off via bean conditions. Do not assume Boot always creates an extra default sender alongside your custom beans.

## 11. Configuring Multiple Static Accounts

Example of an application with two tenants/accounts known at deploy time:

~~~yaml
app:
  mail:
    accounts:
      acme-tx:
        provider: relay-a
        host: ${ACME_SMTP_HOST}
        port: 587
        username: ${ACME_SMTP_USER}
        password: ${ACME_SMTP_PASSWORD}
        implicit-tls: false
        sending-domain: mail.acme.example
        from: orders@mail.acme.example
        reply-to: support@acme.example

      beta-primary:
        provider: relay-b
        host: ${BETA_SMTP_HOST}
        port: 465
        username: ${BETA_SMTP_USER}
        password: ${BETA_SMTP_PASSWORD}
        implicit-tls: true
        sending-domain: notify.beta.example
        from: notices@notify.beta.example
        reply-to: help@beta.example

    routes:
      tenant-acme:
        transactional: acme-tx
      tenant-beta:
        transactional: beta-primary
~~~

This is a **custom namespace** `app.mail.*`. Spring Boot does not automatically bind it into multiple senders unless the application defines its own `@ConfigurationProperties` and factory.

Never commit real passwords. Placeholders are injected via deployment/secret managers. The `provider` field is only routing metadata; it does not configure DKIM or provider accounts automatically.

When there are thousands of tenants, do not generate thousands of YAML entries and restart on every onboarding. Routing metadata can live in a database with caching/versioning, while credentials are stored separately in a secret manager.

## 12. Separating Provider Endpoint, Account, and Route

A clean model consists of three objects:

~~~java
public record SmtpEndpoint(
        String providerId,
        String host,
        int port,
        boolean implicitTls) {
}
~~~

~~~java
public record SenderAccount(
        String accountId,
        String providerId,
        String credentialReference,
        long credentialVersion) {
}
~~~

~~~java
public record ApprovedSenderRoute(
        String tenantId,
        MailPurpose purpose,
        String sendingDomainId,
        String sendingDomain,
        String accountId,
        String fromAddress,
        String replyToAddress,
        long policyVersion) {
}
~~~

These records illustrate the schema/config. Advantages:

- Endpoint describes the provider connection.
- Account describes the principal and secret reference.
- Route describes which tenant/domain/purpose is authorized to use the account.
- When rotating credentials, From/domain rules do not necessarily change.
- When switching providers, template rendering/business workflows do not need to change.

Never log entire objects containing passwords. A record's auto-generated `toString()` can leak sensitive fields into logs if raw secrets are stored directly inside it.

## 13. Deriving MailPurpose from the Use Case

~~~java
public enum MailPurpose {
    SECURITY,
    TRANSACTIONAL,
    MARKETING,
    OPERATIONS
}
~~~

The application layer decides the purpose. For example, a password reset email is always `SECURITY`, even if an HTTP request tries to supply `MARKETING` or an arbitrary SMTP account.

Do not expose an API like:

~~~json
{
  "tenantId": "tenant-beta",
  "smtpAccount": "acme-security",
  "from": "security@mail.acme.example",
  "purpose": "SECURITY"
}
~~~

and trust every field. Clients have no authority to choose SMTP credentials by supplying a string.

A `MailRoutingPolicy` should accept an authorized context and select an approved account, rather than an untrusted request DTO.

## 14. Creating JavaMailSenderImpl per SMTP Account

A factory can build a dedicated sender for each approved account:

~~~java
import java.nio.charset.StandardCharsets;
import java.util.Properties;

import org.springframework.mail.javamail.JavaMailSender;
import org.springframework.mail.javamail.JavaMailSenderImpl;

public final class SmtpSenderFactory {

    public JavaMailSender create(
            String host,
            int port,
            String username,
            String password,
            boolean implicitTls) {

        JavaMailSenderImpl sender =
                new JavaMailSenderImpl();

        sender.setHost(host);
        sender.setPort(port);
        sender.setUsername(username);
        sender.setPassword(password);
        sender.setDefaultEncoding(
                StandardCharsets.UTF_8.name()
        );

        Properties properties =
                sender.getJavaMailProperties();

        properties.put(
                "mail.transport.protocol", "smtp"
        );
        properties.put("mail.smtp.auth", "true");

        if (implicitTls) {
            properties.put(
                    "mail.smtp.ssl.enable", "true"
            );
            properties.put(
                    "mail.smtp.starttls.enable", "false"
            );
        } else {
            properties.put(
                    "mail.smtp.ssl.enable", "false"
            );
            properties.put(
                    "mail.smtp.starttls.enable", "true"
            );
            properties.put(
                    "mail.smtp.starttls.required", "true"
            );
        }

        properties.put(
                "mail.smtp.ssl.checkserveridentity",
                "true"
        );

        properties.put(
                "mail.smtp.connectiontimeout", "5000"
        );
        properties.put(
                "mail.smtp.timeout", "10000"
        );
        properties.put(
                "mail.smtp.writetimeout", "10000"
        );

        return sender;
    }
}
~~~

Port 587 typically pairs with STARTTLS and port 465 with implicit TLS, though you must use whichever mode the provider actually requires. The example enables TLS verification and avoids `mail.smtp.ssl.trust=*` that disables certificate checks in production.

**Do not mutate a singleton sender** whenever the tenant changes:

~~~java
sharedSender.setUsername(account.user());
sharedSender.setPassword(account.password());
sharedSender.send(message);
~~~

If two threads interleave setter calls, tenant A's email can be sent using credentials B. Build preconfigured fixed senders per account and use a registry to select the right instance.

## 15. Named Beans When the Number of Senders Is Small

With a small set of accounts known at build/deploy time:

~~~java
@Configuration
public class MailSenderBeans {

    @Bean("acmeMailSender")
    JavaMailSender acmeMailSender(
            SmtpSenderFactory factory,
            AcmeMailProperties settings) {

        return factory.create(
                settings.host(),
                settings.port(),
                settings.username(),
                settings.password(),
                settings.implicitTls()
        );
    }

    @Bean("betaMailSender")
    JavaMailSender betaMailSender(
            SmtpSenderFactory factory,
            BetaMailProperties settings) {

        return factory.create(
                settings.host(),
                settings.port(),
                settings.username(),
                settings.password(),
                settings.implicitTls()
        );
    }
}
~~~

`AcmeMailProperties` and `BetaMailProperties` are application-defined configuration types; the factory bean also needs to be registered in the Spring context.

When used:

~~~java
public AcmeAdapter(
        @Qualifier("acmeMailSender")
        JavaMailSender sender) {
    this.sender = sender;
}
~~~

However, if the application has thousands of tenants or accounts added at runtime, creating a static bean per account does not scale. Switch to a managed sender registry.

## 16. SenderRegistry for Dynamic Accounts

A simple interface:

~~~java
public interface SenderRegistry {
    JavaMailSender requireSender(
            String approvedAccountId);
}
~~~

It needs to:

1. Accept only account IDs belonging to the platform's approved catalog.
2. Read account metadata/provider endpoint.
3. Resolve the secret from the secret manager.
4. Create `JavaMailSenderImpl` with TLS and timeouts.
5. Cache the sender by account ID + config/credential version.
6. Never expose passwords via APIs or logs.
7. Invalidate/recreate the sender on rotation or suspension.
8. Bound entry count and idle retention.

**Never pass raw host/password supplied directly by an HTTP client** as factory input in a shared workload. That can create unauthorized outbound connections or uncontrolled mail sending.

A `ConcurrentHashMap` of senders does not solve everything on its own: there are still cache eviction, stale secrets, concurrent object creation, lifecycle, and change propagation across multiple JVMs.

### Cache Should Have Expiration and Versioning

An illustrative cache key:

~~~text
accountId: acme-tx
endpointVersion: 4
credentialVersion: 9
~~~

When credentials rotate, build a new sender for the new version instead of mutating the password on an instance currently used by another thread. You need a policy for handling in-flight sends and when to revoke old credentials.

## 17. TenantSenderRouter Returns Only Valid Routes

Contract definition:

~~~java
public interface TenantSenderRouter {

    ApprovedSenderRoute resolve(
            String authenticatedTenantId,
            MailPurpose purpose,
            String selectedSendingDomainId);
}
~~~

The router checks:

- Tenant exists, is active, and is authorized to send.
- Purpose matches the use case.
- Domain ID belongs to the tenant, is verified, and is active.
- From identity is approved by the tenant/provider.
- Account is authorized to send for that domain/purpose.
- Current environment permits this provider.
- Account is not suspended/revoked.
- No ambiguous routes or dangerous defaults.

When no route exists: **fail closed** with an explicit error; never pick the first entry in a map or fall back to another marketing/security account.

### Example Router with an Immutable Map

~~~java
import java.util.Map;
import java.util.Objects;

public record RouteKey(
        String tenantId,
        MailPurpose purpose,
        String sendingDomainId) {
}

public final class StaticTenantRouter
        implements TenantSenderRouter {

    private final Map<RouteKey, ApprovedSenderRoute> routes;

    public StaticTenantRouter(
            Map<RouteKey, ApprovedSenderRoute> routes) {
        this.routes = Map.copyOf(routes);
    }

    @Override
    public ApprovedSenderRoute resolve(
            String tenantId,
            MailPurpose purpose,
            String domainId) {

        Objects.requireNonNull(tenantId);
        Objects.requireNonNull(purpose);
        Objects.requireNonNull(domainId);

        ApprovedSenderRoute route =
                routes.get(new RouteKey(
                        tenantId, purpose, domainId
                ));

        if (route == null) {
            throw new MailRouteDeniedException(
                    "No permitted sender route"
            );
        }

        return route;
    }
}
~~~

`MailRouteDeniedException` is an application-defined runtime exception. This implementation assumes the map was loaded from **verified active configuration**. In production, the router must account for live state/TTL/revocation rather than trusting a snapshot forever.

## 18. Gateway Chooses Transport Before Building MIME

A DTO holding data that has already passed application policy:

~~~java
public record AuthorizedMail(
        String tenantId,
        MailPurpose purpose,
        String sendingDomainId,
        String recipient,
        String subject,
        String plainText,
        String htmlText) {
}
~~~

The name `AuthorizedMail` is a programming contract; it does not by itself prove the data was checked. Only an application service that has verified the actor, business object, and recipient should construct this DTO.

A gateway:

~~~java
import jakarta.mail.MessagingException;
import jakarta.mail.internet.MimeMessage;

import org.springframework.mail.javamail.JavaMailSender;
import org.springframework.mail.javamail.MimeMessageHelper;

public final class MultiTenantMailGateway {

    private final TenantSenderRouter router;
    private final SenderRegistry registry;

    public MultiTenantMailGateway(
            TenantSenderRouter router,
            SenderRegistry registry) {
        this.router = router;
        this.registry = registry;
    }

    public void send(AuthorizedMail mail)
            throws MessagingException {

        ApprovedSenderRoute route =
                router.resolve(
                        mail.tenantId(),
                        mail.purpose(),
                        mail.sendingDomainId()
                );

        JavaMailSender sender =
                registry.requireSender(
                        route.accountId()
                );

        MimeMessage message =
                sender.createMimeMessage();

        MimeMessageHelper helper =
                new MimeMessageHelper(
                        message, true, "UTF-8"
                );

        helper.setFrom(route.fromAddress());

        if (route.replyToAddress() != null) {
            helper.setReplyTo(
                    route.replyToAddress()
            );
        }

        helper.setTo(mail.recipient());
        helper.setSubject(mail.subject());
        helper.setText(
                mail.plainText(),
                mail.htmlText()
        );

        sender.send(message);
    }
}
~~~

The gateway selects transport through an approved route. It **does not accept SMTP passwords/From from the request**, does not mutate credentials on a singleton, and does not read tenant identity from a `ThreadLocal` when an async worker runs.

If a provider requires a custom bounce/envelope sender, that belongs to dedicated transport/account configuration; do not try to force `Return-Path` via a header.

## 19. Tenant Identity Must Come from a Trusted Source

A request like:

~~~json
{
  "tenantId": "tenant-beta",
  "orderId": "order-981"
}
~~~

is not enough to prove the caller has permission to send Beta's email. You must check token/session/workload identity and order ownership.

Example use-case flow:

~~~java
public void sendOrderConfirmation(
        AuthenticatedActor actor,
        UUID orderId) {

    Order order =
            orderRepository.require(orderId);

    tenantPolicy.requireAccess(
            actor, order.tenantId()
    );

    MailPurpose purpose =
            MailPurpose.TRANSACTIONAL;

    String domainId =
            domainPolicy.requireDomainFor(
                    order.tenantId(), purpose
            );

    // Render template and enqueue an AuthorizedMail
    // or an outbox job based on verified data.
}
~~~

The types/methods in the example are application abstractions. The key point is that **tenant is derived/verified from the business resource and principal**, not trusted from raw HTTP fields.

With `@Async` or an outbox, do not rely on a `ThreadLocal` TenantContext from an HTTP request that has already finished. Persist the tenant ID and required context into the job, then enforce policy when the worker processes it.

## 20. Sender Domain and Identity Allowlist

A tenant may manage `mail.acme.example`, yet not necessarily be permitted to set any arbitrary From address. Some systems only allow:

~~~text
orders@mail.acme.example
support@mail.acme.example
alerts@mail.acme.example
~~~

Policy may restrict by local-part, verified mailbox, or entire domain depending on the provider contract.

Do not let a public endpoint arbitrarily pass:

~~~java
helper.setFrom(request.getFrom());
~~~

Even when the domain matches, From may represent a sensitive department or identity the caller is not authorized to use.

**Mail purpose determines sender identity.** For example, password resets use approved `security@security.acme.example`; marketing uses `newsletter@news.acme.example`.

## 21. Multi-Provider Does Not Mean Every Transport Is SMTP

A provider may support both SMTP and an HTTP API. When using an HTTP API, you need an adapter separate from `JavaMailSender`.

~~~java
public interface MailTransport {
    SubmissionResult submit(
            ApprovedSenderRoute route,
            AuthorizedMail mail);
}
~~~

Illustrative implementations:

~~~text
SmtpMailTransport
ProviderAHttpApiTransport
ProviderBHttpApiTransport
~~~

Differences to note:

- SMTP returns 2xx/4xx/5xx reply codes.
- HTTP email APIs may return status 429 and Retry-After.
- APIs may have provider message IDs or dedicated idempotency keys.
- Attachment formats, feedback events, and error details differ.
- Domain verification, custom return-path, and quotas differ.

Do not assume `JavaMailSender` understands HTTP 429 on its own. If all providers are used over SMTP, you can share a `JavaMailSenderImpl` factory at the transport layer while still keeping provider-specific domain verification/feedback in another layer.

## 22. Isolating Quotas and Rate Limits by Tenant

A provider may impose limits across:

~~~text
Provider organization
  -> SMTP account / subaccount
     -> Sending domain
        -> Tenant policy
           -> Mail purpose
~~~

A per-tenant-only limiter can let multiple tenants collectively exceed the global provider account quota. A per-account-only limiter can let one tenant consume all capacity, starving other tenants.

Combine:

- Global provider/account caps.
- Tenant-level quotas.
- Purpose-based rate policies.
- Per-account concurrency caps.
- Priority for security and transactional mail.
- Separate queues for bulk marketing.
- Backoff on provider throttling.
- Per-tenant usage/chargeback auditing.

With multiple worker JVMs, a local limiter in each process does not enforce a global cap. A shared quota authority or controlled capacity partitioning is needed.

**Multiple SMTP usernames do not prove independent provider quotas.** Verify the real scope via documentation, dashboards, or provider contracts.

## 23. Failover Between Providers Must Be Pre-Approved

When Relay A fails, should you switch to Relay B? Possibly, but only when:

1. Relay B has an account authorized for the tenant.
2. Domain identity is verified and DKIM/SPF/DMARC align.
3. The email purpose is still permitted.
4. B's credentials/secrets have valid permissions.
5. Quotas and egress policy allow it.
6. Data residency requirements or tenant contracts are not violated.
7. The failure from attempt A has been classified.
8. Duplicate risk has been assessed.

Example fallback policy:

~~~text
tenant: tenant-acme
purpose: TRANSACTIONAL
sendingDomain: mail.acme.example
primary: relay-a/acme-tx
secondary: relay-b/acme-tx-backup
secondaryVerified: true
fallbackFor:
  - PROVIDER_UNAVAILABLE
  - TEMPORARY_CONNECT_FAILURE
~~~

This is illustrative configuration, not built-in Spring syntax. Do not automatically fail marketing over to a security account to bypass throttling. Do not swap From to a platform domain if the tenant has not approved it.

## 24. SMTP Timeouts Can Cause Duplicates During Fallback

A critical failure window:

~~~text
Worker sends SMTP DATA to Relay A
Relay A accepts the message
Network drops before worker receives the response
Worker observes timeout
Worker falls back to Relay B and resends
Recipient may receive two emails
~~~

Therefore the system must distinguish:

- Definite failure before sending data.
- Explicit SMTP rejection.
- Provider rate limiting.
- AUTH/TLS configuration failure.
- Timeout with **unknown outcome**.
- Partial acceptance when a message has multiple recipients.

`Message-ID` helps tracing, but does not require every relay to deduplicate automatically. A transactional outbox can ensure sending intent is persisted and not enqueued twice for the same key, yet **cannot make database and SMTP an atomic transaction**.

When outcome is unknown, retry/fallback must obey policy and account for duplicate risk—never claim exactly-once.

## 25. Outbox Stores Route Intent, Not SMTP Passwords

A job might contain:

~~~json
{
  "mailJobId": "job-981",
  "tenantId": "tenant-acme",
  "purpose": "TRANSACTIONAL",
  "sendingDomainId": "domain-acme-tx",
  "recipientContactId": "contact-77",
  "templateVersion": 3,
  "routingPolicyVersion": 12,
  "idempotencyKey": "evt-981:tenant-acme:contact-77",
  "status": "PENDING"
}
~~~

Do not store SMTP passwords or provider API keys in the job. Store only IDs, necessary business data, and versions/metadata.

### Pin the Route at Enqueue or Resolve at Send?

**Pinning the route** aids auditing and keeps identity stable, though the account could be revoked before the worker sends.

**Re-resolving the route** allows using rotated credentials or a changed provider, though it risks accidentally sending the same job with a different From/domain.

A balanced approach:

- Persist tenant, purpose, verified domain ID, and template/version.
- Store routing policy version or intended account when auditing requires it.
- The worker verifies the account/domain is still active at send time.
- Credentials can rotate per account policy.
- Do not silently change brand/From/recipient on retry without explicit rules.
- Every attempt records the account/provider actually used.

If a tenant revokes domain permissions, a queued job should not automatically proceed on the old route merely because it was already enqueued.

## 26. Secrets and Credential Rotation

SMTP credentials can send mail on a tenant's behalf. You must:

- Never commit passwords to Java/YAML/Git.
- Use a secret manager or protected encrypted storage.
- Allow only authorized workloads to read secrets.
- Audit creation, edits, reads, rotation, or revocation of credentials.
- Never dump entire Spring properties/log objects containing passwords.
- Never put secrets in outbox payloads or HTTP errors.
- Never store reset tokens/passwords in feedback logs.

A metadata record might include:

~~~text
account_id
tenant_id / pooled_scope
provider_id
endpoint_id
credential_ref
credential_version
status
rotated_at
~~~

`credential_ref` is a reference, not a raw password.

### Rotation Must Refresh the Sender Cache

Changing a password in the secret manager does not automatically update an already-created `JavaMailSenderImpl`. Process:

1. Create a new secret version.
2. Update account metadata and cache version.
3. Create a new sender instance for new requests/sends.
4. Finish or drain old in-flight sends per policy.
5. Revoke old credentials.
6. Monitor AUTH failures and alerts.

Do not call `setPassword` on a concurrently active singleton to rotate.

## 27. When Tenants Enter Their Own SMTP Host: Outbound Connection Risks

If a platform lets tenants enter:

~~~json
{
  "smtpHost": "custom.example.org",
  "smtpPort": 587,
  "smtpUsername": "tenant-user"
}
~~~

serious thought is required. A tenant-controlled host can point to internal networks, metadata endpoints, or sensitive services, or change via DNS after validation. A "test SMTP connection" feature can also be abused for port scanning.

Defense layers:

1. Tenant admins must be authorized.
2. Prefer allowlisted providers/endpoints.
3. Network egress policy restricts allowed IPs/ranges/ports.
4. DNS rebinding and name resolution are controlled.
5. TLS mandatory, hostname verification enabled, no certificate skipping.
6. Timeouts and connection/rate limits.
7. Credentials stored in a secret manager, never returned by APIs.
8. Onboarding/sandbox test before sending live traffic.
9. Monitor abuse, quotas, and anomalous egress.
10. Isolate workloads if arbitrary endpoints must be supported.

Do not treat a check like `host != "localhost"` as sufficient against outbound abuse; there are many ways to represent or route to internal IPs.

## 28. Delivery Feedback by Tenant/Account

Successful SMTP submission does not prove an email was delivered. Providers can emit events:

~~~text
DELIVERED
BOUNCED
DEFERRED
COMPLAINED
UNSUBSCRIBED
~~~

With multiple providers, each has its own webhook schema and verification mechanism. You can normalize:

~~~java
public record ProviderMailEvent(
        String providerId,
        String providerAccountId,
        String providerMessageId,
        String mailJobId,
        String eventType,
        Instant occurredAt) {
}
~~~

To process webhooks:

1. Verify the provider's signature/origin.
2. Parse the right schema/version.
3. Use trusted provider/account/message IDs to look up the mail job.
4. Map the job back to tenant/domain/purpose.
5. Prevent duplicate event processing.
6. Update the right tenant's suppression/delivery status.
7. Write audit logs and handle unknown mappings.

**Never trust a raw tenantId inside a webhook without verification and reconciliation.** If a webhook could alter another tenant's suppression list, that is a cross-tenant state corruption risk.

## 29. Isolating Content and Attachments as Well

Picking the right SMTP sender is not enough if the body or recipient contains another tenant's data.

Protect:

- Orders/invoices belong to the tenant being processed.
- Contacts/recipients belong to the authorized workflow.
- Template data models match the right tenant.
- Brands/logos/assets belong to the tenant.
- Attachment storage keys are tenant-authorized.
- Domain/From is active and belongs to the tenant.
- Provider account is never selected from raw user input.
- Feedback maps back to the right job/tenant.
- Logs and metrics do not leak sensitive data.

For `@Async` and outbox workers, do not pull the tenant from a request-scoped bean or a `ThreadLocal` that is not propagated across threads. Persist trusted tenant ID/authorization intent and revalidate at the worker boundary when needed.

## 30. Local, Staging, and Production Must Have Separate Routes

| Environment | Sender | Recipient policy |
| --- | --- | --- |
| Local | Mail catcher | No Internet sending |
| Unit test | Fake/mocked gateway | Fixtures, no real SMTP |
| Staging | Provider sandbox / SMTP test server | Allowlist or sink |
| Production | Approved provider accounts | Full business authorization |

Do not grant production credentials to staging just to test "like production." If staging might hold real customer data, add data-handling policies and recipient guards; a misconfigured profile must never send test emails to customers.

Example local configuration:

~~~yaml
spring:
  config:
    activate:
      on-profile: local
  mail:
    host: localhost
    port: 1025
~~~

The mail catcher must run separately. With a custom multi-sender app, the local profile needs to override the registry/router as well, not just `spring.mail.*` if custom senders do not read those properties.

## 31. Unit Testing Routing Without SMTP

A test verifying mapping:

~~~java
@Test
void acmeTransactionalUsesApprovedAccount() {
    ApprovedSenderRoute route =
            router.resolve(
                    "tenant-acme",
                    MailPurpose.TRANSACTIONAL,
                    "domain-acme-tx"
            );

    assertEquals(
            "acme-tx",
            route.accountId()
    );

    assertEquals(
            "orders@mail.acme.example",
            route.fromAddress()
    );
}
~~~

A negative test:

~~~java
@Test
void rejectsForeignTenantDomain() {
    assertThrows(
            MailRouteDeniedException.class,
            () -> router.resolve(
                    "tenant-acme",
                    MailPurpose.TRANSACTIONAL,
                    "domain-beta"
            )
    );
}
~~~

Cases to cover:

| Case | Result |
| --- | --- |
| Active tenant, verified domain, valid purpose | Route approved |
| Another tenant's domain | Rejected |
| Domain pending DNS | Rejected |
| Revoked domain | Rejected |
| Suspended account | Rejected or approved backup |
| Tenant not permitted for purpose | Rejected |
| Marketing has no account | Do not fall back to security |
| Staging selects production route | Rejected |
| From identity outside allowlist | Rejected |
| Backup not yet DKIM verified | Not used |
| Duplicate/ambiguous route | Fail configuration |

These tests need no Spring context, SMTP network, or real secrets if the router is pure logic.

## 32. Gateway Test Selecting the Right JavaMailSender

You can use Mockito and a real in-memory `MimeMessage`:

~~~java
JavaMailSender acmeSender =
        mock(JavaMailSender.class);

JavaMailSender betaSender =
        mock(JavaMailSender.class);

when(acmeSender.createMimeMessage())
        .thenAnswer(invocation ->
                new MimeMessage(
                        Session.getInstance(
                                new Properties()
                        )
                )
        );

// Test registry returns acmeSender for account acme-tx.
// Test router returns Acme's approved route.
// Gateway receives Acme's AuthorizedMail.

gateway.send(authorizedAcmeMail);

verify(acmeSender, times(1))
        .send(any(MimeMessage.class));

verify(betaSender, never())
        .send(any(MimeMessage.class));
~~~

This is a test skeleton: `gateway`, `authorizedAcmeMail`, and test registry/router must be created per project. You can use `ArgumentCaptor<MimeMessage>` to assert recipient, From, Reply-To, decoded subject, and MIME content, not only invocation counts.

Do not mock the entire `MimeMessage` if the goal is verifying headers and multipart semantics. Use real Jakarta Mail objects in RAM and mock the sender to avoid opening SMTP connections.

## 33. Integration Tests with Two SMTP Test Servers

One way to verify route separation end to end:

~~~text
GreenMail/Mailpit A:
  SMTP port A
  Account route: Acme

GreenMail/Mailpit B:
  SMTP port B
  Account route: Beta
~~~

Test:

1. Start two test servers on separate ports.
2. Register two `JavaMailSenderImpl` instances pointing to ports A/B.
3. Create tenant fixtures/verified domain fixtures.
4. Send one Acme message and one Beta message.
5. Verify server A receives only Acme's message.
6. Verify server B receives only Beta's message.
7. Verify From, To, and correlation ID.
8. Clean up servers, fixtures, and queues belonging to the test.

Do not use a shared inbox and grab the latest message by array index. With async workers, wait by correlation ID and a controlled deadline instead of fixed `Thread.sleep`.

SMTP test servers do not by themselves prove SPF/DKIM/DMARC or real provider domain verification. For those requirements, dedicated contract tests in a provider sandbox and domain onboarding tests are needed.

## 34. Observability by Tenant/Provider/Account

A submission log can include:

~~~text
mail_job_id: job-981
tenant_id: tenant-acme
purpose: TRANSACTIONAL
sender_domain_id: domain-acme-tx
provider_id: relay-a
provider_account_id: acme-tx
routing_policy_version: 12
credential_version: 9
attempt: 1
smtp_result: ACCEPTED
latency_ms: 842
~~~

Do not log passwords, reset tokens, full mail bodies, or attachments. For recipients, use contact IDs or masking per policy.

Useful metrics:

| Metric | Meaning |
| --- | --- |
| `mail_submission_total` | Attempt counts by provider/account |
| `mail_smtp_auth_failure_total` | Credential failures |
| `mail_tls_failure_total` | TLS/certificate failures |
| `mail_provider_throttle_total` | Throttling |
| `mail_domain_verification_state` | Domain active/pending/revoked |
| `mail_route_fallback_total` | Backup route usage counts |
| `mail_unknown_outcome_total` | Attempts with ambiguous outcomes |
| `mail_bounce_total` | Bounces by account/domain |
| `mail_complaint_total` | Complaints by account/domain |
| `mail_outbox_oldest_age_seconds` | Jobs waiting longest |
| `mail_sender_cache_entries` | Registry cache size |
| `mail_provider_quota_remaining` | Remaining quota by provider |

If there are hundreds of thousands of tenants, putting tenant ID into every metric label can create huge cardinality. Design aggregate metrics alongside controlled log/trace lookups by tenant.

### Important Alerts

- An active domain loses verification.
- Tenant credentials suffer repeated AUTH failures.
- Account quota nears exhaustion or traffic spikes suddenly.
- Provider outage and fallback rise abnormally.
- DKIM/DMARC alignment fails for a domain.
- Bounces/complaints climb.
- Webhooks fail to map to a message.
- Security mail has a long backlog.
- Sender registry cache grows unbounded.

## 35. Common Implementation Mistakes

### 35.1. Changing Only From

Does not change the SMTP principal, so mail may hit the wrong account, quota, or be rejected by the provider. You must route the account/transport.

### 35.2. Trusting Tenant ID in the Request

Callers can spoof another tenant. You must verify principal and resource ownership.

### 35.3. Selecting an Account from a Raw HTTP Field

Can let users switch purposes or hijack other credentials. Only internal policy may select routes.

### 35.4. Letting Unverified Domains Send

Risks spoofing and DMARC failure. Activate domains only after verification.

### 35.5. Not Separating Provider Account and Sending Domain

One account can use multiple domains, and one domain can have multiple accounts. Explicit mapping is required.

### 35.6. Using @Primary to Hide a Missing Route

A service forgetting a qualifier may silently send through the wrong default account. Use an explicit router.

### 35.7. Mutating JavaMailSenderImpl Across Threads

Creates credential race conditions. Build fixed-configuration instances.

### 35.8. Unbounded Sender Caching

Can retain thousands of objects and secrets. Bound the cache and invalidate by version.

### 35.9. Rotation Without Updating the Sender

The instance still holds the old password. Recreate/swap by credential version.

### 35.10. Allowing Arbitrary Tenant SMTP Hosts

Creates outbound abuse and internal-network connection risks. Use allowlists, egress protection, TLS, and onboarding.

### 35.11. Treating Reply-To as Envelope Sender

Reply-To does not replace SMTP MAIL FROM or provider bounce configuration.

### 35.12. Setting Return-Path Manually for Bounce Handling

Return-Path belongs to delivery processing; configure provider/custom MAIL FROM per contract.

### 35.13. Falling Back to an Unverified Provider

Can send with wrong DNS auth and identity. Backup routes must be prepared beforehand.

### 35.14. Uncontrolled Retry of Unknown Outcomes

SMTP timeouts after DATA can cause duplicates. Dedicated state and policy are required.

### 35.15. Outbox Not Storing Tenant/Domain

Workers may pick the wrong account or lose auditability. Persist trusted identity and route intent.

### 35.16. Old Jobs Still Sending After Domain Revocation

Revalidate permissions at send time.

### 35.17. Assuming Multiple SMTP Users Have Strictly Separate Quotas

Providers may enforce global organization/IP caps. Verify the real behavior.

### 35.18. Processing Webhooks Without Signature Verification

Can corrupt suppression/status for the wrong tenant. Verify and map trusted IDs.

### 35.19. Using ThreadLocal Tenant Context in Async Workers

Context can be lost or leaked across tasks. Persist trusted tenant IDs.

### 35.20. Assuming SMTP Accepted Means Delivered

The provider may only have accepted the message for forwarding; delivery/bounces require separate feedback.

## 36. Practice Questions

**Question 1.** Two tenants use two different Header From addresses but share one SMTP username. Are accounts separated?

No. Only sender identity may differ; credentials/quotas are still shared.

**Question 2.** Tenant A sends a request with `tenantId=B`. Should the router use account B?

No, unless the actor/business resource proves authorization for B.

**Question 3.** A tenant enters a domain whose DNS is not yet verified. Should production sending be allowed?

No. The domain must be active under provider/platform policy.

**Question 4.** Tenant Acme has two transactional domains. Is a RouteKey with only tenant and purpose sufficient?

No. You also need a domain ID/brand or an approved selection rule.

**Question 5.** Does changing `helper.setFrom` to Beta's domain make `JavaMailSenderImpl` use Beta's credentials?

No. Account selection happens in the sender/registry.

**Question 6.** Credentials are rotated in the secret manager. Does the old sender cache automatically know to update?

Not by default. Version-based invalidation/recreation is required.

**Question 7.** Provider A has valid DKIM, while provider B has not verified the domain. Can you fall back to B?

No. The backup must meet DNS/provider identity requirements.

**Question 8.** SMTP A times out after sending DATA and the worker switches to B immediately. What is the risk?

The email may be sent twice because the outcome from A is uncertain.

**Question 9.** A tenant enters an SMTP host pointing to a private IP. Is that safe?

No. Outbound egress, host/port, and DNS controls are required.

**Question 10.** A provider webhook claims tenant B, but the signature is invalid. Should B's bounce list be updated?

No. You must verify the callback and reconcile against trusted message/account records.

**Question 11.** Do multiple SMTP credentials in the same provider organization have independent quotas?

Do not assume so. Confirm at what level quotas apply.

**Question 12.** Should you use the security account when marketing is throttled?

No. Only use backup routes approved for the same purpose.

**Question 13.** A route was pinned at enqueue time, but the domain was revoked before the worker sent. What should happen?

Revalidate status/permissions at send time and fail closed or handle per policy, rather than trying to send with stale permissions.

**Question 14.** Does successful SMTP AUTH mean DKIM/DMARC are configured properly?

No. Those are independent mechanisms.

**Question 15.** An email for tenant A uses sender A, yet reads an attachment from tenant B. Has routing ensured isolation?

No. Content/attachment authorization is also a mandatory part of end-to-end tenant isolation.

## 37. Mental Model

~~~mermaid
flowchart TD
    A["Trusted actor / business event"] --> B["Resolve tenant + permissions"]
    B --> C["Check recipient + content"]
    C --> D["MailPurpose + verified domain"]
    D --> E["TenantSenderRouter"]
    E --> F{"Valid route?"}
    F -->|"No"| G["Fail closed / hold job"]
    F -->|"Yes"| H["SenderRegistry"]
    H --> I["Account metadata + secret version"]
    I --> J["JavaMailSenderImpl"]
    J --> K["MimeMessageHelper"]
    K --> L["SMTP provider"]
    L --> M["Record account/provider/attempt"]
    M --> N["Provider feedback"]
    N --> O["Verify + map to right tenant"]
~~~

Principles:

1. **Tenant, sending domain, provider, SMTP account, and From are not the same thing.**
2. **Changing From does not mean changing credentials.** You must select the matching transport/account.
3. **Tenant identity must be trusted**, never taking arbitrary accounts from requests.
4. **Domains must be verified and active**; provider permissions and SPF/DKIM/DMARC must align.
5. **Route keys can include tenant, purpose, and domain ID**, especially for tenants with multiple brands/domains.
6. **A single Spring Boot `spring.mail.*` does not route multi-tenant traffic automatically.** Use named beans or a registry.
7. **Never mutate a singleton sender across threads**; rotate via new instances/versions.
8. **Secrets and registry caches must be controlled**, avoiding careless storage or logging of credentials.
9. **BYO SMTP endpoints carry egress/SSRF-style risks**, requiring strong security controls.
10. **Provider failover only when the backup route is pre-approved**, without violating purpose/domain policies.
11. **Unknown SMTP outcomes can cause duplicates**; do not rely on Message-ID to guarantee exactly-once.
12. **Outbox persists tenant/domain/purpose and routing intent**, not passwords; revalidate permissions at send time.
13. **Quotas may be shared at the organization/IP level**, even with multiple accounts.
14. **Provider webhooks must be verified and mapped to the right tenant**, preventing cross-tenant state updates.
15. **Test routing, transport, and provider integration at separate boundaries**, avoiding real SMTP dependencies in unit tests.

In Spring Framework Mail with multiple providers, the most important factor is not the number of `JavaMailSenderImpl` instances, but a **sender-selection policy that can be verified, protected, and audited**. When tenant identity, verified sending domain, mail purpose, provider account, and credentials are explicitly bound together, the application can send email under each tenant's brand while still governing security, quotas, secret lifecycles, provider feedback, and failover incidents.
