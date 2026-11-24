# Routing by Email Type or Region

## 1. The Problem of Sending Email Through Multiple Providers

In **Spring Framework Mail**, `JavaMailSender` is commonly configured to connect to a single SMTP server. That model suffices for small systems. However, a product with multiple notification categories, multiple tenants, or users across regions may need to **route each email to the appropriate SMTP provider** rather than sending everything through a single account.

For example, an e-commerce platform may generate:

- Login verification and account recovery emails: need fast delivery without delay.
- Order confirmations, invoices, and shipping notifications: need reliability and send history.
- Newsletters, promotions, or marketing campaigns: high volume, must enforce consent/unsubscribe.
- Emails serving customers in different regions: may need to account for data residency requirements, network infrastructure, provider permissions, or local regulations.

If all of them share one SMTP path, a marketing campaign can exhaust the quota of the password-reset stream; a provider outage can disrupt every email category; and outbound data may traverse infrastructure regions inconsistent with the product's data-handling commitments.

**Mail routing** is the process of deciding *who will send a specific delivery, with which configuration and identity, at what time*, based on verified criteria.

~~~text
Business event / mail outbox
               |
               v
       Normalize mail command
          - category
          - tenant
          - recipient region
          - sending identity
          - priority
               |
               v
          Routing policy
               |
         +-----+------+----------------+
         |            |                |
         v            v                v
     SMTP EU       SMTP APAC       Marketing pool
         |            |                |
         +------------+----------------+
                      |
                      v
           Submission outcome + audit
                      |
                      v
          Provider feedback / metrics
~~~

In Spring Mail, **MIME construction and SMTP sending** have built-in APIs, whereas **multi-provider routing policy, health, quotas, retries, failover, and event reconciliation** must be built at the application layer or via infrastructure integration.

> **Principle:** Routing rules must be explicit enough that, given a delivery and a policy version, you can explain why the system chose provider A over B. Never let the choice depend on a global variable mutated arbitrarily across threads.

## 2. Common Routing Criteria

| Criterion | Example | Value | Risk if misapplied |
| --- | --- | --- | --- |
| **Email category** | `SECURITY`, `TRANSACTIONAL`, `MARKETING` | Protects separate quotas, reputation, SLAs | Marketing starves urgent emails |
| **Region** | `EU`, `VN`, `US` | Complies with regional rules, latency, provider availability | Transferring data through a disallowed region |
| **Tenant** | Enterprise A, B | Isolates credentials, budgets, branding | Wrong sender or tenant data leak |
| **Priority** | Critical, normal, bulk | Coordinates capacity and deadlines | A campaign delays OTPs |
| **Provider health** | Healthy, throttled, unavailable | Avoids failing endpoints | Switching providers when SMTP outcome is unclear |
| **Quota/rate limit** | Messages/minute, connection caps | Stays within provider contracts | Retry storms, account suspension |
| **Sending identity** | Domain, envelope sender, DKIM key | Ensures authentication and branding | SPF/DKIM/DMARC failures or misrouted bounces |
| **Content type** | Attachments, size, encryption needs | Picks providers supporting the policy | Messages rejected due to SIZE/type |
| **Cost** | Per-email price, data transfer | Optimizes cost within constraints | Choosing cheap routes that miss SLAs/compliance |

The **region** criterion requires particular care: recipient location does not automatically determine all legal obligations. Data residency can apply to **where queues, logs, webhooks, attachments, metadata, and provider infrastructure are stored**, not merely the SMTP hostname. Real policy must be defined by product owners/legal teams and vendor agreements rather than inferred from region names alone.

### 2.1. Email Type Should Be a Business Enum

Instead of relying on free-form subjects or template names:

~~~java
public enum MailCategory {
    SECURITY,
    TRANSACTIONAL,
    MARKETING
}
~~~

Some applications may add `SYSTEM_ALERT`, `BILLING`, or `LEGAL_NOTICE`. Categories must be stable, business-defined, and never turn an arbitrary string from an HTTP request directly into privilege to use a high-priority provider.

Examples:

- `SECURITY`: email verification, password change alerts, unusual login confirmations.
- `TRANSACTIONAL`: receipts, order updates, appointment changes.
- `MARKETING`: newsletters and promotional campaigns requiring opt-in consent.

Do not label every "seemingly important" email as `SECURITY` just to get better quota/latency. Email category must come from a trusted use case.

### 2.2. Region Should Be Canonicalized, Not Derived from Email TLD

~~~java
public enum DeliveryRegion {
    VN,
    EU,
    US,
    OTHER
}
~~~

An address ending in `.com` does not prove the recipient lives in the US; `.vn` does not prove all recipient data is permitted to be processed in Vietnam. Never route by inspecting country suffixes in email domains.

Region sources can include:

- Verified tenant residency configuration.
- Jurisdiction/address stored in the domain model under business policy.
- Organization or deployment region settings authorized by an administrator.

If region is missing or multiple sources conflict, policy should enter an **unresolved** state requiring missing data or an approved default route—never auto-pick the cheapest region without knowing data-processing rights.

### 2.3. Email Category and Region Are Two Independent Dimensions

Do not write ad-hoc rules like:

~~~text
If recipient contains ".eu" => provider EU
Else if subject contains "sale" => provider marketing
Else => provider default
~~~

The rule above gets both region sourcing and precedence wrong. A marketing email sent to an EU user must satisfy **both marketing and EU** simultaneously. A better approach evaluates a structured context:

~~~text
RoutingContext = {
  category: MARKETING,
  region: EU,
  tenant: tenant-42,
  sendingIdentity: marketing-eu,
  allowedProviders: [smtp-eu-bulk-a, smtp-eu-bulk-b]
}
~~~

`allowedProviders` must be derived by internal policy, never supplied by an unauthorized caller.

## 3. Route Matrix and Policy Evaluation Order

An example routing table:

| Region | Email category | Primary | Conditional secondary | Quota class |
| --- | --- | --- | --- | --- |
| VN | SECURITY | `smtp-vn-critical-a` | `smtp-vn-critical-b` | Critical |
| VN | TRANSACTIONAL | `smtp-vn-tx-a` | `smtp-vn-tx-b` | Normal |
| VN | MARKETING | `smtp-vn-bulk-a` | Not by default | Bulk |
| EU | SECURITY | `smtp-eu-critical-a` | `smtp-eu-critical-b` | Critical |
| EU | TRANSACTIONAL | `smtp-eu-tx-a` | `smtp-eu-tx-b` | Normal |
| EU | MARKETING | `smtp-eu-bulk-a` | `smtp-eu-bulk-b` | Bulk |
| US | SECURITY | `smtp-us-critical-a` | `smtp-us-critical-b` | Critical |
| US | TRANSACTIONAL | `smtp-us-tx-a` | `smtp-us-tx-b` | Normal |
| US | MARKETING | `smtp-us-bulk-a` | Per policy | Bulk |

These provider names are **illustrative logical IDs**, not representing real vendors or guaranteeing any vendor operates infrastructure in the named region. A route is deployed only after verifying real capabilities, sending permissions, domains, and provider data requirements.

### 3.1. Recommended Evaluation Order

~~~text
Validate command / recipient / tenant
                  |
                  v
Check consent, suppression and business deadline
                  |
                  v
Resolve category + permitted sending identity
                  |
                  v
Resolve approved data-processing region
                  |
                  v
Build set of policy-allowed providers
                  |
                  v
Filter by identity, size, capability and tenant rights
                  |
                  v
Filter by health/capacity within allowed set
                  |
                  v
Select primary or approved alternative
                  |
                  v
Persist route decision + version
                  |
                  v
Submit through chosen JavaMailSender
~~~

**Do not check health first and let it override policy:** a provider might be healthy yet unauthorized to process that email category or region. System health only helps **choose within the set of permitted routes**.

### 3.2. Fail-Closed Policy for Region-Restricted Data

If no valid provider remains inside the region to which a delivery is bound, the safe behavior is typically:

~~~text
No eligible provider in permitted region
        |
        v
RETRY / HOLD / NEEDS_OPERATOR
        |
        v
Alert + audit
~~~

Do not automatically divert emails to an out-of-region provider just to boost send success rates unless approved policy permits it and all related conditions are satisfied.

### 3.3. Policy Version for Reconciliation

Routing rules change over time. When an email is sent, persist:

~~~text
deliveryId: opaque-id
routePolicyVersion: 2026-11-routing-03
category: TRANSACTIONAL
region: VN
providerId: smtp-vn-tx-a
identityId: transactional-vn
routeReason: PRIMARY_ELIGIBLE
~~~

These fields explain why an email chose a given provider in the past even if today's config differs. Never store secrets/passwords in audit records.

## 4. Spring Mail's Responsibilities in a Multi-Provider Model

`JavaMailSender` is the interface for sending `SimpleMailMessage` and `MimeMessage`. For SMTP, `JavaMailSenderImpl` is the common implementation configuring host, port, username, password, protocol, and Jakarta Mail properties.

An application using multiple SMTP endpoints can:

1. Define multiple `JavaMailSender` beans with `@Qualifier`.
2. Build an **internal registry** managing multiple `JavaMailSenderImpl` instances by ID.
3. Build senders from a factory using runtime configuration, with managed caching and lifecycles.
4. Use non-SMTP email provider APIs via separate adapters if the system needs both SMTP and HTTP APIs.

There is no built-in "all-provider router" merely from enabling `spring-boot-starter-mail`. Selecting the sender is the responsibility of the routing service layer.

### 4.1. Multiple Static Beans with @Qualifier

~~~java
@Configuration
public class StaticMailSendersConfiguration {

    @Bean("criticalMailSender")
    JavaMailSender criticalMailSender() {
        return createSender(
                "critical-smtp.example.net",
                587,
                System.getenv("CRITICAL_SMTP_USERNAME"),
                System.getenv("CRITICAL_SMTP_PASSWORD"));
    }

    @Bean("bulkMailSender")
    JavaMailSender bulkMailSender() {
        return createSender(
                "bulk-smtp.example.net",
                587,
                System.getenv("BULK_SMTP_USERNAME"),
                System.getenv("BULK_SMTP_PASSWORD"));
    }

    private static JavaMailSender createSender(
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
        Properties props = new Properties();
        props.put("mail.smtp.auth", "true");
        props.put("mail.smtp.starttls.enable", "true");
        props.put("mail.smtp.starttls.required", "true");
        props.put("mail.smtp.ssl.checkserveridentity", "true");
        props.put("mail.smtp.connectiontimeout", "5000");
        props.put("mail.smtp.timeout", "10000");
        props.put("mail.smtp.writetimeout", "10000");
        sender.setJavaMailProperties(props);
        return sender;
    }
}
~~~

Typical imports: `java.util.Properties`, `org.springframework.context.annotation.Bean`, `Configuration`, and classes in `org.springframework.mail.javamail`.

This is a brief example for two static senders. In production, do not scatter `System.getenv` secret reads across multiple beans; inject secrets through controlled runtime configuration validated at startup. Both hostnames are placeholders, not real endpoints.

When multiple beans share the same type:

~~~java
@Service
public class SeparateChannels {

    private final JavaMailSender critical;
    private final JavaMailSender bulk;

    public SeparateChannels(
            @Qualifier("criticalMailSender") JavaMailSender critical,
            @Qualifier("bulkMailSender") JavaMailSender bulk) {
        this.critical = critical;
        this.bulk = bulk;
    }
}
~~~

If using Spring Boot auto-configuration, understand its conditional behavior: once the application defines its own mail senders, auto-configuration may **back off**. Do not assume `spring.mail.*` properties bind automatically onto every custom `JavaMailSenderImpl` bean you declare.

### 4.2. Why a Registry Fits Many Routes

With dozens of routes combining region × category × tenant, declaring a manual bean per route becomes hard to maintain. A registry supports:

~~~text
providerId -> JavaMailSender
            -> identity and credential reference
            -> capability and region metadata
            -> rate limiter / circuit breaker
~~~

**Logical provider ID differs from route ID.** One SMTP provider can serve multiple allowed email types; one route can have multiple candidate providers. Never name provider IDs from unverified recipient or tenant inputs.

## 5. Declaring Multiple SMTP Providers via Spring Boot Configuration

As providers grow, manage endpoints under a dedicated prefix such as `app.mail.providers` rather than inventing ad-hoc `spring.mail.host-1` keys without binding conventions. Illustrative configuration:

~~~yaml
app:
  mail:
    providers:
      smtp-vn-critical-a:
        host: critical-vn.example.net
        port: 587
        username: ${SMTP_VN_CRITICAL_USER}
        password: ${SMTP_VN_CRITICAL_PASSWORD}
      smtp-vn-tx-a:
        host: transactional-vn.example.net
        port: 587
        username: ${SMTP_VN_TX_USER}
        password: ${SMTP_VN_TX_PASSWORD}
      smtp-eu-tx-a:
        host: transactional-eu.example.net
        port: 587
        username: ${SMTP_EU_TX_USER}
        password: ${SMTP_EU_TX_PASSWORD}
      smtp-eu-bulk-a:
        host: bulk-eu.example.net
        port: 587
        username: ${SMTP_EU_BULK_USER}
        password: ${SMTP_EU_BULK_PASSWORD}
~~~

This is an **example endpoint set**, not a mandatory layout and not proof of real server residency. Hostnames ending in `example.net` are illustrative only. In production, passwords must come from a secret manager, environment, or runtime secret file—never committed to the repository.

### 5.1. Binding Configuration into a Record

With Spring Boot 3 and Java 17+, you can use an immutable `@ConfigurationProperties` record:

~~~java
package com.example.mail.routing;

import java.util.Map;
import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "app.mail")
public record MultiProviderMailProperties(
        Map<String, SmtpEndpoint> providers) {

    public record SmtpEndpoint(
            String host,
            int port,
            String username,
            String password) {
    }
}
~~~

Register the properties class:

~~~java
@Configuration
@EnableConfigurationProperties(
        MultiProviderMailProperties.class)
public class MultiProviderMailConfiguration {
    // The registry bean is declared below.
}
~~~

If the project uses a different Spring Boot version, adjust constructor binding and validation for that version. Never put passwords into `toString()`/logs: a Java record's default `toString` prints all components, including secrets. Never log the full `MultiProviderMailProperties` object.

### 5.2. Registry Creating a Dedicated Sender per Endpoint

~~~java
package com.example.mail.routing;

import java.util.HashMap;
import java.util.Map;
import java.util.Properties;

import org.springframework.mail.javamail.JavaMailSender;
import org.springframework.mail.javamail.JavaMailSenderImpl;

public final class MailSenderRegistry {

    private final Map<String, JavaMailSender> senders;

    public MailSenderRegistry(
            MultiProviderMailProperties settings) {

        if (settings.providers() == null
                || settings.providers().isEmpty()) {
            throw new IllegalStateException(
                    "No mail providers configured");
        }

        Map<String, JavaMailSender> built = new HashMap<>();
        settings.providers().forEach((id, endpoint) ->
                built.put(id, createSender(id, endpoint)));
        this.senders = Map.copyOf(built);
    }

    public JavaMailSender requireSender(String providerId) {
        JavaMailSender sender = senders.get(providerId);
        if (sender == null) {
            throw new IllegalArgumentException(
                    "Unknown mail provider ID");
        }
        return sender;
    }

    private static JavaMailSender createSender(
            String id,
            MultiProviderMailProperties.SmtpEndpoint endpoint) {

        if (endpoint == null
                || endpoint.host() == null
                || endpoint.host().isBlank()
                || endpoint.port() <= 0
                || endpoint.port() > 65535
                || endpoint.username() == null
                || endpoint.username().isBlank()
                || endpoint.password() == null
                || endpoint.password().isBlank()) {
            throw new IllegalStateException(
                    "Incomplete mail provider configuration: " + id);
        }

        JavaMailSenderImpl sender = new JavaMailSenderImpl();
        sender.setHost(endpoint.host());
        sender.setPort(endpoint.port());
        sender.setUsername(endpoint.username());
        sender.setPassword(endpoint.password());
        sender.setDefaultEncoding("UTF-8");

        Properties props = new Properties();
        props.setProperty("mail.smtp.auth", "true");
        props.setProperty("mail.smtp.starttls.enable", "true");
        props.setProperty("mail.smtp.starttls.required", "true");
        props.setProperty("mail.smtp.ssl.checkserveridentity", "true");
        props.setProperty("mail.smtp.connectiontimeout", "5000");
        props.setProperty("mail.smtp.timeout", "12000");
        props.setProperty("mail.smtp.writetimeout", "12000");
        sender.setJavaMailProperties(props);
        return sender;
    }
}
~~~

Wire the registry:

~~~java
@Bean
MailSenderRegistry mailSenderRegistry(
        MultiProviderMailProperties settings) {
    return new MailSenderRegistry(settings);
}
~~~

Each `JavaMailSenderImpl` is configured separately; never mutate host, port, username, or password on a sender shared across threads **right before each send**. Configuring once at startup and looking up senders by ID avoids races when multiple workers pick different endpoints.

This configuration uses **SMTP submission over STARTTLS/port 587**. For providers using implicit TLS/port 465, set `mail.smtp.ssl.enable=true` per endpoint. For providers using OAuth2, authentication differs from plain passwords; use an adapter/transport supporting the right SASL/protocol and do not assume passing an access token to `setPassword` suffices.

Beyond the code above, production needs provider capability metadata, verified sender identities, rate limits, and credential rotation. Simply creating a `JavaMailSenderImpl` does not prove the server resides in the named region.

### 5.3. Why Not Use One JavaMailSenderImpl and Call setHost Repeatedly?

Example of **what not to do**:

~~~java
// Singleton used concurrently by multiple workers.
sender.setHost(routeForCurrentRequest.host());
sender.setUsername(routeForCurrentRequest.username());
sender.setPassword(routeForCurrentRequest.password());
sender.send(mimeMessage);
~~~

Two workers can interleave host/credential changes, causing a message to use the wrong account or wrong region. A mail sender must not be treated as a freely mutable "request context."

Solution:

- Create dedicated senders/transports per provider ID with immutable configuration during sending.
- Use a registry for lookup.
- When config must update during secret rotation, use an instance/bean replacement workflow that handles in-flight sends instead of mutating fields sequentially.

## 6. Routing Policy in Java

Before sending, the application must translate trusted business metadata into a route decision. Keys can be modeled as:

~~~java
package com.example.mail.routing;

public enum MailCategory {
    SECURITY,
    TRANSACTIONAL,
    MARKETING
}

public enum DeliveryRegion {
    VN, EU, US, OTHER
}

public record RouteKey(
        DeliveryRegion region,
        MailCategory category) {
}

public record RouteDecision(
        String primaryProviderId,
        String identityId,
        String policyVersion) {
}
~~~

In Java, top-level `public` classes, enums, and records must reside in their own matching files rather than pasted into a single file. The declarations above are independent components.

A policy with several static routes:

~~~java
package com.example.mail.routing;

import java.util.Map;

public final class MailRoutingPolicy {

    private static final String VERSION = "routing-v3";

    private final Map<RouteKey, RouteDecision> routes = Map.of(
            new RouteKey(
                    DeliveryRegion.VN,
                    MailCategory.SECURITY),
            new RouteDecision(
                    "smtp-vn-critical-a",
                    "identity-vn-security",
                    VERSION),
            new RouteKey(
                    DeliveryRegion.VN,
                    MailCategory.TRANSACTIONAL),
            new RouteDecision(
                    "smtp-vn-tx-a",
                    "identity-vn-transactional",
                    VERSION),
            new RouteKey(
                    DeliveryRegion.EU,
                    MailCategory.TRANSACTIONAL),
            new RouteDecision(
                    "smtp-eu-tx-a",
                    "identity-eu-transactional",
                    VERSION),
            new RouteKey(
                    DeliveryRegion.EU,
                    MailCategory.MARKETING),
            new RouteDecision(
                    "smtp-eu-bulk-a",
                    "identity-eu-marketing",
                    VERSION)
    );

    public RouteDecision requireRoute(
            DeliveryRegion region,
            MailCategory category) {

        RouteDecision decision =
                routes.get(new RouteKey(region, category));
        if (decision == null) {
            throw new IllegalStateException(
                    "No approved mail route for this category and region");
        }
        return decision;
    }
}
~~~

This illustrative policy covers only **four combinations**. Undeclared routes must be rejected/held rather than silently picking a default. In multi-tenant/multi-provider deployments, routes are typically stored in a database or versioned declarative config, and policy must additionally filter by consent, quota, health, sender identity, and residency.

### 6.1. Do Not Let Users Pick High-Priority Categories

Never treat a public API DTO as authoritative policy:

~~~json
{
  "recipient": "unknown@example.com",
  "category": "SECURITY",
  "region": "EU",
  "providerId": "smtp-eu-critical-a"
}
~~~

If any user can specify `SECURITY` and `providerId`, they can bypass quotas or send through unauthorized providers/identities. Services must determine category from the authenticated use case, region from trusted business data, and provider from internal policy.

### 6.2. Precedence Order of Routing Rules

Some applications order rules by specificity:

~~~text
1. Explicit authorized tenant override
2. Region + category
3. Region default category
4. Global default (only if allowed by policy)
~~~

Not every system should have a `global default`. Under strict residency rules, a missing regional rule must stop sending. If a tenant override exists, validate that it stays within allowed providers for region, identity, quota, and security policy.

### 6.3. Do Not Route by Random Percentage Without Traceability

Weighted routing (80% provider A, 20% provider B) helps load testing or gradual provider migrations. However, choices must be recorded:

~~~text
routePolicyVersion
candidateProviderIds
selectedProviderId
selectionReason
experimentBucket or stable hash key (if used)
~~~

For retries of **the same delivery**, re-randomizing providers on every attempt makes behavior unpredictable. A better choice is usually pinning the provider on the first attempt and changing only when a **new valid fallback decision** is logged with an audit trail.

## 7. Combining Routing with Sender Identity

A route is more than an SMTP hostname. A provider may require verified domains or `From` addresses, matching SPF/DKIM, and a dedicated bounce/Return-Path.

Example:

| Route | Header From | Reply-To | Envelope sender / bounce | DKIM identity |
| --- | --- | --- | --- | --- |
| VN security | `security@example.com` | `support@example.com` | `bounce@bounces.example.com` | `example.com` |
| VN transactional | `orders@example.com` | `orders-help@example.com` | `bounce@bounces.example.com` | `example.com` |
| EU marketing | `newsletter@news.example.com` | `marketing-help@example.com` | `bounce@bounces.news.example.com` | `news.example.com` |

These are **illustrative names**, not a guarantee that an SMTP account is automatically permitted to send from those addresses. Domains/subdomains and DKIM keys must be verified inside each provider.

### 7.1. From, Reply-To, and Envelope Sender Differ

~~~java
helper.setFrom("security@example.com");
helper.setReplyTo("support@example.com");
~~~

Those two calls set **MIME headers**. They do not directly guarantee SMTP envelope `MAIL FROM` points to the desired bounce domain. With Jakarta Mail's SMTP transport, `mail.smtp.from` configures the transport envelope sender; providers may also override `Return-Path`. Do not manually set a `Return-Path` header to fake the envelope.

If one provider endpoint is shared across multiple sender identities with different bounce addresses, do not mutate `mail.smtp.from` on a singleton sender's `Properties` before each request. Use separate senders per identity, a supported per-message transport mechanism, or the provider's custom return-path configuration.

### 7.2. SPF, DKIM, and DMARC Are Route Requirements

When adding a new provider:

- Verify ownership of domains used in the `From` header.
- Configure SPF for sending infrastructure per provider docs; avoid overlapping SPF records or exceeding DNS lookup limits.
- Configure DKIM signing and verify matching keys/domains.
- Verify DMARC alignment between Header `From` and the SPF domain (envelope sender) and/or DKIM `d=`.
- Configure MX/routing for the bounce domain if using inbound DSNs.
- Send test messages to a test environment and inspect authentication results.

Never assume that because provider A can send for domain X, provider B can too. During failover, **identity and authentication configurations must be compatible**; otherwise emails may be accepted by the SMTP relay yet flagged as spam or rejected by receivers.

### 7.3. Reputation and Quotas Are Not Properties of a Single IP

Providers may enforce limits and track sending quality at multiple levels:

- SMTP credentials/accounts.
- Sender domains/subdomains.
- IP pools, tenants, or regions.
- Destination domains, complaint/bounce rates.
- Traffic types or service agreements.

Separating `MARKETING` from `SECURITY` helps avoid quota contention and reduces reputation risk, yet only works when account/domain/pool configuration and provider policies actually isolate them.

## 8. Dispatch Service: Pick the Sender, Then Build MIME with That Same Sender

An easy design bug is calling `createMimeMessage()` on sender A and then choosing sender B based on region. The message may still be a valid Jakarta Mail object, yet charsets, `Session`, envelope properties, or transport-specific behavior can mismatch across configurations.

In the routing service, decide the provider **before** calling `createMimeMessage()` and use that same sender for the whole attempt:

~~~text
Validated mail command
         |
         v
Select approved route
         |
         v
Resolve providerId -> JavaMailSender
         |
         v
sender.createMimeMessage()
         |
         v
MimeMessageHelper: From / To / body / attachment
         |
         v
sender.send(mimeMessage)
         |
         v
Store SMTP submission result
~~~

### 8.1. A Strongly Typed Command

~~~java
package com.example.mail.routing;

import java.util.UUID;

public record ValidatedMailCommand(
        UUID deliveryId,
        String tenantId,
        DeliveryRegion region,
        MailCategory category,
        String recipient,
        String subject,
        String plainText,
        String htmlText) {
}
~~~

The name `ValidatedMailCommand` means the command is constructed **after** business layers check recipient, tenant, category, region, permissions, suppression/consent, and business deadlines. Simply naming a record that way **does not perform validation by itself**.

A dedicated identity registry:

~~~java
package com.example.mail.routing;

import java.util.Map;

public record SenderIdentity(
        String fromAddress,
        String replyToAddress) {
}

public final class SenderIdentityRegistry {

    private final Map<String, SenderIdentity> identities =
            Map.of(
                    "identity-vn-security",
                    new SenderIdentity(
                            "security@example.com",
                            "support@example.com"),
                    "identity-vn-transactional",
                    new SenderIdentity(
                            "orders@example.com",
                            "orders-help@example.com"),
                    "identity-eu-transactional",
                    new SenderIdentity(
                            "orders@example.com",
                            "orders-help@example.com"),
                    "identity-eu-marketing",
                    new SenderIdentity(
                            "newsletter@news.example.com",
                            "marketing-help@example.com"));

    public SenderIdentity requireIdentity(String id) {
        SenderIdentity identity = identities.get(id);
        if (identity == null) {
            throw new IllegalArgumentException(
                    "Unconfigured sender identity");
        }
        return identity;
    }
}
~~~

Identities here are illustrative configuration; production must integrate provider verification, domain alignment, bounce addresses, and tenant rules.

### 8.2. RoutingMailDispatcher

~~~java
package com.example.mail.routing;

import jakarta.mail.MessagingException;
import jakarta.mail.internet.MimeMessage;

import org.springframework.mail.javamail.JavaMailSender;
import org.springframework.mail.javamail.MimeMessageHelper;
import org.springframework.stereotype.Service;

@Service
public final class RoutingMailDispatcher {

    private final MailRoutingPolicy policy;
    private final MailSenderRegistry senderRegistry;
    private final SenderIdentityRegistry identities;

    public RoutingMailDispatcher(
            MailRoutingPolicy policy,
            MailSenderRegistry senderRegistry,
            SenderIdentityRegistry identities) {
        this.policy = policy;
        this.senderRegistry = senderRegistry;
        this.identities = identities;
    }

    public RouteDecision submit(
            ValidatedMailCommand command)
            throws MessagingException {

        RouteDecision route = policy.requireRoute(
                command.region(), command.category());

        SenderIdentity identity =
                identities.requireIdentity(route.identityId());

        JavaMailSender sender =
                senderRegistry.requireSender(
                        route.primaryProviderId());

        MimeMessage message = sender.createMimeMessage();
        MimeMessageHelper helper =
                new MimeMessageHelper(message, true, "UTF-8");

        helper.setFrom(identity.fromAddress());
        helper.setReplyTo(identity.replyToAddress());
        helper.setTo(command.recipient());
        helper.setSubject(command.subject());
        helper.setText(
                command.plainText(), command.htmlText());

        sender.send(message);
        return route;
    }
}
~~~

This is a **minimal synchronous sending path**. It demonstrates route selection and sender lookup, without outbox, health, rate limiting, circuit breakers, or failover. In reliable deployments, do not persist the route **only after** `send`: if the JVM crashes after SMTP acceptance, you lose track of which provider was used. Record the route decision/attempt record **before** calling SMTP, inside a short transaction as shown next.

`MailRoutingPolicy` and `SenderIdentityRegistry` can be registered as Spring beans via `@Bean` or `@Component`; in the example they are plain classes to keep focus on the core mechanism. Do not mark one provider `@Primary` just to silence injection errors and accidentally funnel every service through it.

### 8.3. When Using SimpleMailMessage

`SimpleMailMessage` fits plain-text emails:

~~~java
SimpleMailMessage mail = new SimpleMailMessage();
mail.setFrom(identity.fromAddress());
mail.setTo(recipient);
mail.setSubject(subject);
mail.setText(text);
sender.send(mail);
~~~

It lacks the HTML/multipart/attachment capabilities of `MimeMessageHelper`. Routing policy remains an independent concern: select the sender by category/region, then send with the appropriate message type.

### 8.4. One Delivery with Multiple Recipients

Suppose you send the same content to:

~~~text
user-a@example.vn   -> region VN
user-b@example.eu   -> region EU
user-c@example.us   -> region US
~~~

Do not put all three into **one** MIME message and pick a single provider based on the first recipient. Because recipients can belong to different routes, privacy policies, consent states, and quotas, create **one delivery per recipient**, or split into groups with explicitly compatible routes and obligations.

This also makes it easier to track partial SMTP failures, retry counts, suppression, and bounces per recipient.

## 9. Pinning the Route in a Transactional Outbox

A system requiring reliable mail sending should generally not call SMTP directly inside a business database transaction. Instead:

~~~text
Create order / user event
           |
           v
BEGIN transaction
   +-- save business data
   +-- create mail_outbox row
   +-- assign category, region, tenant
COMMIT
           |
           v
Worker claims delivery
           |
           v
Routing policy resolves approved candidates
           |
           v
Persist route decision + attempt STARTED
COMMIT
           |
           v
JavaMailSender for providerId
           |
     +-----+------+
     |            |
     v            v
 SMTP accepted   Error / unknown
     |            |
     v            v
  mark SENT    RETRY / FAILED / UNKNOWN
~~~

Separating database transactions from network calls prevents workers from holding database locks while SMTP or attachment generation is slow.

### 9.1. Illustrative Schema

~~~sql
CREATE TABLE mail_outbox (
    id UUID PRIMARY KEY,
    tenant_id UUID NOT NULL,
    delivery_key VARCHAR(180) NOT NULL UNIQUE,
    recipient VARCHAR(320) NOT NULL,
    category VARCHAR(30) NOT NULL,
    region VARCHAR(30) NOT NULL,
    template_key VARCHAR(120) NOT NULL,
    template_version VARCHAR(80),
    status VARCHAR(30) NOT NULL DEFAULT 'PENDING',
    attempt_count INT NOT NULL DEFAULT 0,
    max_attempts INT NOT NULL DEFAULT 5,
    next_attempt_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    selected_provider_id VARCHAR(100),
    selected_identity_id VARCHAR(100),
    route_policy_version VARCHAR(100),
    route_reason VARCHAR(100),
    claim_token UUID,
    lease_until TIMESTAMPTZ,
    last_error_code VARCHAR(100),
    last_error_kind VARCHAR(40),
    smtp_accepted_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX ix_mail_outbox_due
    ON mail_outbox(status, next_attempt_at);

CREATE INDEX ix_mail_outbox_provider
    ON mail_outbox(selected_provider_id, status);
~~~

This schema is **illustrative**: add storage/models or durable references for template data, ownership/concurrency controls, retention, and encryption/PII policies as needed by your application.

### 9.2. Attempt History Must Record the Actual Chosen Provider

~~~sql
CREATE TABLE mail_delivery_attempt (
    id UUID PRIMARY KEY,
    outbox_id UUID NOT NULL REFERENCES mail_outbox(id),
    attempt_no INT NOT NULL,
    provider_id VARCHAR(100) NOT NULL,
    identity_id VARCHAR(100) NOT NULL,
    policy_version VARCHAR(100) NOT NULL,
    route_reason VARCHAR(100) NOT NULL,
    status VARCHAR(30) NOT NULL DEFAULT 'STARTED',
    error_code VARCHAR(100),
    failure_stage VARCHAR(60),
    started_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    finished_at TIMESTAMPTZ,
    UNIQUE(outbox_id, attempt_no)
);
~~~

History might look like:

| Attempt | Provider | Status | Reason |
| --- | --- | --- | --- |
| 1 | `smtp-vn-tx-a` | RETRYABLE_FAILURE | SMTP connect refused |
| 2 | `smtp-vn-tx-a` | RETRYABLE_FAILURE | Temporary throttle |
| 3 | `smtp-vn-tx-b` | SMTP_ACCEPTED | Approved failover |

Having `provider_id` on every attempt lets operators distinguish same-provider retries from fallbacks to another provider.

### 9.3. Persist the Route Decision Before the SMTP Call

Inside the claim/route transaction:

1. Claim the delivery atomically with a row lock/lease.
2. Verify category, region, and suppression are still valid.
3. Select a route under an auditable policy version.
4. Write provider/identity/policy version into the attempt record.
5. Increment `attempt_count` and commit.
6. Only then execute the SMTP send.

If the worker crashes after choosing the route yet before sending, the attempt remains `STARTED`. A reconciler can detect expired attempts. Never assume SMTP received the message merely because a route decision exists.

### 9.4. When Policy Changes Between Attempts

Suppose a delivery is created in VN at T1. At T2, an operator switches primary from `smtp-vn-tx-a` to `smtp-vn-tx-b`. Two strategies:

- **Pin policy version to the delivery:** use the exact policy recorded at enqueue time, good for audit/reproducibility.
- **Re-evaluate on retry:** apply the newly approved policy, recording the new decision/version on each attempt.

Neither option is universally right. Under data-residency requirements, a newer policy might narrow permitted providers and must take effect immediately. For large campaign batches, pinning avoids mid-batch route shifts. Either way, **route changes must be explicitly recorded**, never caused by unchecked config overrides.

## 10. Failover Is Not "Switch Providers on Every Exception"

Suppose primary SMTP fails and the app wants to switch to secondary. The single most important distinction is **whether primary already accepted the email or not**.

~~~text
SMTP attempt to provider A
          |
          +--> Definite failure before message submission
          |      |
          |      v
          |  Evaluate eligible fallback candidates
          |
          +--> Definite permanent error
          |      |
          |      v
          |  Fix recipient/credential/policy; no blind failover
          |
          +--> SMTP accepted
          |      |
          |      v
          |  Record accepted; do not send again
          |
          +--> Unknown after DATA/timeout
                 |
                 v
            Reconcile / duplicate-aware policy
            (do not blindly submit to B)
~~~

### 10.1. Failures That Can Permit Fallback

Examples to consider:

- Primary endpoint is unreachable **before sending the message**.
- Provider is temporarily unavailable with proof the message was not accepted.
- Provider returns `421`/`4xx` at a stage safe to try another endpoint.
- Primary exhausted quota while secondary is authorized, has capacity, and has compatible sender identity.

Even when the error looks transient, verify secondary is **permitted for the region/category/tenant** and does not violate deadline/consent/size policies.

### 10.2. Failures Where You Should Not Immediately Fall Back

| Error | Why not switch providers automatically? |
| --- | --- |
| Invalid recipient | Switching SMTP relays does not turn a bad address into a valid one |
| Missing template variable | Data/rendering needs fixing; other providers will fail too |
| Authentication failure from wrong secret | May be misconfiguration or revoked credentials; inspect and alert |
| Unverified sender domain | Secondary may also lack authorization for that From/Return-Path |
| Message too large | Secondary helps only if policy/capabilities actually accept that type/size |
| Security/suppression restriction | Failover must never bypass consent or blocklists |
| SMTP result unknown | Primary may have received it; sending via B creates duplicates |
| Region restriction | Switching to another region just because the local endpoint failed is disallowed |

### 10.3. The Hard Case: Timeout After DATA

~~~text
App -> A: DATA + MIME bytes
A   -> App: [connection lost before final response]

Did A accept the email?
  - Possibly yes
  - Possibly no
~~~

If the application immediately sends the same message to B, the recipient may receive **two copies**, and bounces/delivery events can arrive from both providers.

With plain SMTP, there is no shared transaction with the database, so you typically achieve **at-least-once**. `Message-ID` helps correlation, yet does not force SMTP servers to deduplicate. If a provider API offers idempotency keys, use them per its contract; never assume SMTP supports exactly-once.

A sound policy:

1. Mark the outcome `UNKNOWN` or store an attempt with uncertain result.
2. Record provider ID and the phase where the timeout occurred.
3. Reconcile against provider logs/APIs if available.
4. Use business deadlines and duplicate tolerance to decide retry/redrive.
5. If retrying, record a new attempt and decision reason rather than silently changing providers.

### 10.4. Controlled Failover via Candidate Allowlist

A route can store:

~~~text
primary: smtp-eu-tx-a
approvedFallbacks:
  - smtp-eu-tx-b
disallowed:
  - smtp-us-tx-a
  - smtp-eu-bulk-a
~~~

`smtp-eu-tx-b` can be chosen only if identity/domain, data policy, capacity, and contract compatibility are configured. Do not build fallback lists automatically from every key in the registry.

**Safe order:** policy eligibility first, provider health/capacity second, then pick from the remaining set.

## 11. Per-Provider Rate Limits and Circuit Breakers

Even a valid route can fail if the whole system floods the same SMTP account with too many emails. Each provider or sending identity should enforce limits on:

- Messages per minute, hour, or day.
- Recipients per message and total recipients per minute.
- Concurrent SMTP connections.
- MIME message size.
- Allowed email types, sending hours, or campaign limits.
- Retries within an interval and backoff policy.

~~~text
Ready mail deliveries
          |
          v
Route + provider eligibility
          |
          v
Per-provider quota / limiter
          |
          +--> Capacity available
          |      |
          |      v
          |  Submit via sender
          |
          +--> No capacity
                 |
                 v
            Schedule later
            (do not claim and spin)
~~~

A **circuit breaker** can pause calling a provider if timeout/unavailable rates spike. However, an open circuit does not prove individual deliveries permanently failed; usually deliveries remain waiting or retry with backoff. Avoid counting every circuit-open skip as a failed SMTP attempt when SMTP was never actually called.

### 11.1. Isolating Capacity for Security and Marketing

If both email categories share an SMTP account and quota, separate routing classes alone **are not enough** to ensure OTPs are not slowed down by a campaign. You can use:

- Separate accounts/IP pools or credentials when the provider supports them.
- Separate queues and concurrency caps.
- Priority schedulers or reserved capacity.
- Token buckets per provider and category.
- Bulkheads for thread pools/connection pools.

### 11.2. Backoff and Jitter

An illustrative retry policy:

\[
d_n = \min(d_{\max}, d_0 \cdot 2^{n-1})
\]

With `d_0 = 30 seconds` and jitter, transient failures do not cause thousands of workers to reconnect at the exact same instant. `max_attempts`, retry deadlines, and backoff must vary by email category: password resets have shorter deadlines than non-urgent newsletters.

Never use infinite retries to mask the lack of an eligible provider; emit observable and actionable `NO_ELIGIBLE_ROUTE` or `PROVIDER_UNAVAILABLE` signals.

## 12. Every Route Also Needs a Bounce/Feedback Path

After sending, the application may receive asynchronous errors: the provider accepted the SMTP message, yet the destination server rejected delivery later. A multi-provider strategy must know **which delivery a bounce/webhook belongs to**.

~~~text
Outbox delivery D1
     |
     +--> Provider A submit -> providerMessageId A-100
     |
     +--> (if approved, later attempt) Provider B
                -> providerMessageId B-240

Provider A webhook / DSN ----+
                             |
Provider B webhook / DSN ----+--> verify source
                             |    normalize event
                             |    match delivery + attempt + recipient
                             v
                      Delivery feedback history
~~~

Do not build one generic webhook handler accepting payloads from all providers and reading only the `email` field to block future sends. Events must be verified with **provider-defined signatures/credentials** and correlated to a concrete provider ID/attempt/recipient.

### 12.1. IDs to Distinguish

| ID | Generated where? | Role |
| --- | --- | --- |
| `deliveryId` | Application system | Identifies one delivery to one recipient |
| `attemptId` | Application system | Identifies one SMTP submission trial |
| `providerId` | Routing registry | SMTP/API path used |
| `providerMessageId` | Provider | Correlates provider events when returned |
| `Message-ID` | MIME/transport | Traces emails, though not guaranteed unique per recipient |
| `eventId` | Provider/webhook | Deduplicates delivery/bounce/complaint events |

Some providers do not return `providerMessageId` cleanly over SMTP, or expose IDs only via headers/APIs/logs. Design correlation around each provider's real capabilities rather than assuming `JavaMailSender.send` always returns an external ID.

### 12.2. Normalizing Provider Events

Provider A might emit `delivered` and `bounce`, while provider B emits `deferred`, `failed`, or DSN `Action: failed`. Adapters should translate them into a common model:

~~~java
public enum MailFeedbackType {
    SMTP_ACCEPTED,
    RECEIVER_ACCEPTED,
    DELAYED,
    HARD_BOUNCE,
    FINAL_SOFT_BOUNCE,
    COMPLAINT,
    UNKNOWN
}

public record NormalizedMailFeedback(
        String providerId,
        String providerEventId,
        String providerMessageId,
        java.util.UUID deliveryId,
        String recipient,
        MailFeedbackType type,
        String safeErrorCode,
        java.time.Instant occurredAt) {
}
~~~

This is an illustrative application model, not a Spring Mail API. A `DELAYED` event usually means the provider is still trying to deliver—**do not automatically make the app resend via provider B**. Creating a new message while provider A retries internally carries high duplicate risk.

### 12.3. Hard Bounces and Complaints Apply Across Providers

If an address is verified as nonexistent, switching to another provider rarely helps. Maintain an application-layer **suppression policy**:

~~~text
Verified hard bounce / spam complaint
              |
              v
Central suppression policy
              |
        +-----+------+
        |            |
        v            v
     Provider A   Provider B
     cannot send  cannot send
     outside policy for same recipient
~~~

Do not rely solely on provider A's internal suppression list, because on failover B may not know the recipient bounced/complained. For marketing, enforce consent/unsubscribe at the right scope; for transactional/security, apply policy for invalid addresses rather than "evading" suppression merely by changing providers.

### 12.4. Domain Alignment and Bounce Routing on Failover

If providers A and B use different bounce domains:

- Verify MX/Return-Path for each provider.
- Maintain separate webhook/IMAP credentials and secrets per stream.
- Persist provider/attempt at send time so you know which path emitted an event.
- Never overwrite an earlier attempt's `providerMessageId` just because a retry used a new provider.
- Update aggregate state only according to event ordering and confidence rules.

The `Reply-To` address for user replies is **not** necessarily where SMTP DSNs return. Bounce addresses usually tie to envelope `MAIL FROM` or provider Return-Path policies.

## 13. Regional Routing and Data Controls

Names like `smtp-eu-a` or `smtp-vn-a` are merely **logical labels**. Never treat a name as proof that:

- The provider stores data in that region.
- Backups/logs/webhook metadata stay in that region.
- Emails never traverse relays or networks in other regions.
- Subprocessors/data centers meet all legal requirements.

Data policies to evaluate:

| Data/system | Questions to determine |
| --- | --- |
| Mail body/attachments | Is there personal data or restricted documents barred from crossing regions? |
| Outbox database | In which region are queues/payloads stored? |
| SMTP provider | Where does the provider process, buffer, log, and back up data? |
| Webhooks/DSNs | Do delivery callbacks include recipients, bodies/headers? To which region? |
| Observability | Do logs, traces, and metrics contain PII or tenant identifiers? |
| Support/admin access | Who is authorized to access messages and metadata? |
| Retention | How long does data persist at each provider? |
| Encryption/keys | How are TLS, encryption at rest, and key ownership managed? |

**Route selection is only part of meeting residency requirements.** Sending via EU SMTP while writing full bodies into a central queue in a disallowed region does not satisfy the end-to-end goal.

### 13.1. Resolving Region from Trusted Sources

Example region-resolution service:

~~~java
public interface RecipientRegionResolver {
    DeliveryRegion resolveFor(
            String tenantId,
            String recipientAccountId);
}
~~~

Implementations may rely on tenant policies, verified addresses, or customer contracts. Never infer region from country-code email suffixes, recent access IPs, or unverified request fields.

### 13.2. Cross Regions Only When Permitted

A policy may stipulate:

~~~text
EU transactional:
  primary = smtp-eu-tx-a
  permitted fallback = smtp-eu-tx-b
  cross-region fallback = prohibited
~~~

If both EU providers are unavailable, the system must wait or record no valid route—**never auto-shift to US merely because US is healthy**. Another policy might allow cross-region when authorized by contract and conditions are met; that decision must appear explicitly in the policy version and audit trail.

### 13.3. Multi-Tenant Isolation

If the application serves multiple enterprises:

- Tenant A must never use tenant B's SMTP account, sender domain, or quota.
- Route rules and secret references must be tenant-scoped.
- When receiving feedback, verify the event/delivery's `tenantId`.
- Never accept arbitrary `providerId` values in public APIs to look up secrets.
- Dashboards/traces must restrict data by tenant access permissions.

One provider can serve multiple tenants if contracts/permissions allow. Still, keep identities, quotas, `From` domains, suppressions, and webhook correlation isolated where required.

## 14. Capability-Based Provider Selection Rules

Not every SMTP provider accepts the same message types. A registry can store capability metadata:

~~~java
public record ProviderCapability(
        String providerId,
        DeliveryRegion approvedRegion,
        boolean transactionalAllowed,
        boolean marketingAllowed,
        long maxMessageBytes,
        int maxRecipients,
        boolean supportsRequiredTls,
        java.util.Set<String> verifiedIdentityIds) {
}
~~~

The fields above represent **information verified by operators or integration systems**, never inferred merely because a provider initialized cleanly. Other important capabilities include custom Return-Path support, dedicated IPs, DKIM, API feedback, deliverability reporting, attachment restrictions, or regional data policies.

### 14.1. Example Intentional Filter

A provider is eligible only when every condition holds:

~~~text
provider.region approved for this delivery
AND category allowed
AND identityId is verified by provider
AND estimatedMessageBytes <= provider message limit
AND recipient count within policy
AND required TLS and authentication available
AND tenant authorized to use provider
AND sender health/capacity acceptable
~~~

If no valid provider exists, do not fall back globally regardless of conditions. Record structured routing errors such as `NO_ELIGIBLE_PROVIDER`, `IDENTITY_NOT_VERIFIED`, `REGION_RESTRICTED`, or `MESSAGE_SIZE_UNSUPPORTED`; depending on the error, transition to `HOLD`, `RETRY`, or `FAILED` per policy.

### 14.2. Switching Providers When a Message Has Attachments

When a secondary has a smaller size limit than the primary, a message accepted by primary may be rejected by secondary. Therefore filter not only by category and region, but also check **estimated MIME size after transfer encoding**. Binary attachments grow due to Base64; a 20 MiB file produces a substantially larger message.

To reduce risk, you can:

- Use secure download links instead of attachments when business policy allows.
- Enforce input limits before constructing MIME.
- Choose routes supporting the calculated size.
- Never retry oversized-message errors endlessly across providers.

### 14.3. Email Category Also Affects Delivery Deadlines

Illustrative policy example:

| Category | Priority | Sample deadline | Behavior when provider unavailable |
| --- | --- | --- | --- |
| SECURITY | Highest | Before OTP/reset token expires | Fast bounded retries; never send expired tokens |
| TRANSACTIONAL | Normal/high | Per business SLA | Retry/backoff, monitor outbox |
| MARKETING | Bulk | Campaign window | Delay/pause when quota is low; never exceed consent |

These are not Spring Mail defaults. If a password-reset link expires in 10 minutes and the email arrives later, delivering a stale message confuses users.

## 15. Configuration Changes and Rollout Process

When adding or replacing a provider:

1. Provision credentials via a secret manager with proper tenant/region permissions.
2. Verify sender domain, SPF/DKIM/DMARC, and bounce domain.
3. Verify TLS, hostname/certificate, AUTH, and network endpoint.
4. Verify message limits, quotas, throughput, retention, and data policies.
5. Define capability metadata and route eligibility.
6. Publish a new **routing policy version** instead of silently editing a live rule.
7. Test in staging with controlled test identities/recipients.
8. Canary a small percentage of traffic from the eligible set.
9. Monitor SMTP acceptance, latency, error rates, bounces/complaints, and quotas.
10. Gradually increase traffic with a rollback and audit plan.

### 15.1. Why Canaries Need Sticky Selection

If a single delivery retries multiple times, per-attempt randomness can send it through both A and B. For canaries, assign the test cohort using a stable hash on delivery/tenant or a controlled sampling key, then **persist the route decision** in the outbox.

~~~text
stableBucket(deliveryId or tenantId)
  0..4 -> canary provider B
  5..99 -> existing provider A
~~~

Never use a persistent hash of recipient email as a public metric label or share PII-derived values. If tenant stickiness is needed, store buckets securely and verify data policies before bucketing.

### 15.2. Config Rollback Does Not Rewrite Sent History

When a canary fails, you can shift new traffic back to the old provider. However:

- Attempts already SMTP-accepted must retain their original provider ID.
- Bounce/delivery events from the canary provider can still arrive after rollback.
- Jobs still in `UNKNOWN` are not automatically resent.
- The canary provider's credentials and webhook endpoint may need to remain active during reconciliation.

Shutting down all event ingestion for a rolled-back provider risks losing feedback on emails already sent.

## 16. Observing Routing via Metrics, Logs, and Tracing

A multi-provider system must answer:

- In the last 15 minutes, how many emails of each category went through providers A and B?
- Why did the EU secondary provider start receiving traffic?
- Which provider is seeing rising `4xx`, `5xx`, authentication errors, or timeouts?
- Which emails lacked an eligible route?
- Were any cross-region routes or identity mismatches detected?
- Were any messages submitted twice due to failover/retries?
- How did cost, quota, and latency change after the canary?

### 16.1. Recommended Metrics

| Metric | Type | Meaning |
| --- | --- | --- |
| `mail_route_decisions_total` | Counter | Route selections by category/region/provider/reason |
| `mail_route_rejected_total` | Counter | Missing eligible route or policy block |
| `mail_provider_submissions_total` | Counter | SMTP submissions by provider/outcome |
| `mail_provider_send_duration_seconds` | Timer/Histogram | Transport duration per provider |
| `mail_provider_failover_total` | Counter | Attempts choosing an approved secondary |
| `mail_provider_retry_total` | Counter | Retries actually started, not merely scheduled |
| `mail_provider_capacity_denied_total` | Counter | Provider out of quota/concurrency at app layer |
| `mail_provider_circuit_open` | Gauge | Whether circuit breaker is open |
| `mail_provider_inflight` | Gauge | In-flight attempts using the provider |
| `mail_outbox_due_count` | Gauge | Due deliveries not yet sent |
| `mail_outbox_oldest_due_age_seconds` | Gauge | Maximum overdue age |
| `mail_feedback_events_total` | Counter | Verified delivery/bounce/complaint events per provider |

With Micrometer:

~~~java
public void recordRoute(
        MeterRegistry registry,
        RouteDecision route,
        MailCategory category,
        DeliveryRegion region,
        String reason) {

    Counter.builder("mail.route.decisions")
            .tag("provider", route.primaryProviderId())
            .tag("category", category.name())
            .tag("region", region.name())
            .tag("reason", reason)
            .register(registry)
            .increment();
}
~~~

`MeterRegistry` and `Counter` belong to `io.micrometer.core.instrument`. In production code, `reason` must come from a **bounded** set such as `PRIMARY`, `FALLBACK_AFTER_PRE_SUBMISSION_FAILURE`, `CAPACITY_SHIFT`. Never use raw exception messages as tags.

**Never** use `recipientEmail`, high-cardinality `tenantId`, `deliveryId`, `Message-ID`, or verbatim SMTP responses as metric labels. Use access-controlled structured logs/audits to investigate individual deliveries.

### 16.2. Do Not Double-Count Metrics Across Replicas

Counters emitted by each worker can be summed across instances for rates. However, if every worker queries the **same outbox database** and exports a global queue gauge, summing all gauges multiplies the backlog by N. For global snapshots, use an authoritative collector or appropriate aggregation (such as `max` over the same scope) and document the source.

### 16.3. Structured Log per Routing Attempt

~~~json
{
  "event": "mail.routing.attempt_started",
  "deliveryId": "opaque-id",
  "attempt": 2,
  "category": "TRANSACTIONAL",
  "region": "VN",
  "providerId": "smtp-vn-tx-b",
  "identityId": "identity-vn-transactional",
  "routePolicyVersion": "routing-v3",
  "routeReason": "APPROVED_FALLBACK",
  "workerId": "worker-02"
}
~~~

This is an illustrative log containing no username/password, recipient email, subject, MIME body, or tokens. After each attempt, emit an outcome event with `smtpResult`, `failureStage`, `safeErrorCode`, `durationMs`, and outbox commit result.

If region/tenant data is considered sensitive under policy, restrict log read permissions and detail level. Never serialize the full `MultiProviderMailProperties` object containing passwords just to debug routing.

### 16.4. Useful Alerts

| Signal | Meaning | First action |
| --- | --- | --- |
| `NO_ELIGIBLE_PROVIDER` spikes | Missing policy or disabled provider | Check route/capabilities matrix |
| Security mail misses deadline | Priority lane congested | Inspect queue, quota, and critical endpoint |
| SMTP auth failures spike | Credential/provider change | Check secret version; do not aggressively retry |
| Failover rate rises | Primary may be unstable | Check primary errors/health/capacity |
| Secondary also throttled | Whole pool lacks capacity | Rate-limit, apply backpressure, reduce bulk |
| Sender identity rejected | Domain unverified or policy changed | Check From/DKIM/Return-Path at provider |
| Cross-region attempts blocked | Policy working as designed or wrong region input | Investigate region/tenant data source |
| Bounces/complaints rise post-rollout | Reputation/deliverability degraded | Halt canary, inspect DNS/consent |
| UNKNOWN attempts climb | Timeouts after DATA or DB state-update errors | Reconcile before retry/fallback |

Alert thresholds must reflect SLOs and traffic volume. An isolated failure is not necessarily an incident, whereas 100% authentication failures on the password-reset route warrant immediate paging.

### 16.5. Health Checks Are Not Proof of Delivery

`JavaMailSenderImpl.testConnection()` can verify transport connectivity/authentication; running it too often as a health probe creates traffic and depends on provider/network quotas. Never send real emails from a health endpoint running every few seconds.

Health assessment should typically combine:

- Circuit-breaker state.
- Recent connection/submission success rates.
- Remaining quota/limits from provider APIs if available.
- Worker progress and queue latency.
- Low-frequency, bounded-timeout probes only when truly needed.

A provider that "can connect" can still reject messages on submission due to From/domain/size/quota. Health is a **route-selection signal**, not an outcome guarantee.

## 17. Testing Routing Policy

Separating policy from SMTP transport lets fast unit tests verify decisions while integration tests verify each sender connects and receives the right messages.

### 17.1. Unit Testing the Category × Region Matrix

~~~java
import static org.assertj.core.api.Assertions.assertThat;
import static org.junit.jupiter.api.Assertions.assertThrows;

import org.junit.jupiter.api.Test;

class MailRoutingPolicyTest {

    private final MailRoutingPolicy policy =
            new MailRoutingPolicy();

    @Test
    void choosesEuBulkForEuMarketing() {
        RouteDecision decision = policy.requireRoute(
                DeliveryRegion.EU,
                MailCategory.MARKETING);

        assertThat(decision.primaryProviderId())
                .isEqualTo("smtp-eu-bulk-a");
        assertThat(decision.identityId())
                .isEqualTo("identity-eu-marketing");
    }

    @Test
    void rejectsCombinationWithoutApprovedRoute() {
        assertThrows(
                IllegalStateException.class,
                () -> policy.requireRoute(
                        DeliveryRegion.OTHER,
                        MailCategory.SECURITY));
    }
}
~~~

These tests verify the illustrative policy defined in Section 6. Production tests must cover **all supported combinations**, missing routes, tenant overrides, fallback restrictions, suppression, capabilities, message sizes, and policy version changes.

### 17.2. Property-Based or Table-Driven Tests

Instead of writing separate tests for dozens of routes:

~~~text
Input:
  (VN, SECURITY)       -> smtp-vn-critical-a
  (VN, TRANSACTIONAL)  -> smtp-vn-tx-a
  (EU, TRANSACTIONAL)  -> smtp-eu-tx-a
  (EU, MARKETING)      -> smtp-eu-bulk-a

Invariant:
  region matches approved processing region
  category allowed by provider capability
  identity verified on selected provider
  no rule bypasses tenant policy
~~~

You can use `@ParameterizedTest` with `@MethodSource` in JUnit 5 to validate the table; if routes live in config, tests should also confirm **every provider ID in policy exists in the registry**. Such config tests catch YAML edits that forgot credentials/endpoints.

### 17.3. Testing Two Providers with SMTP Sinks

An integration test can run **two separate Mailpit or GreenMail containers**:

~~~text
                    Spring Boot test
                          |
                RoutingMailDispatcher
                   /            \
                  v              v
         JavaMailSender VN   JavaMailSender EU
                  |              |
                  v              v
             Mailpit VN       Mailpit EU
                  |              |
                  +------+-------+
                         |
                         v
                    Test assertions
~~~

Test cases:

1. Send a `TRANSACTIONAL/VN` message; Mailpit VN receives it, Mailpit EU does not.
2. Send a `MARKETING/EU` message; the right marketing sender/route receives it, not the security pool.
3. Verify MIME `From` and `Reply-To` match the configured identity.
4. When a category/region lacks a route, neither SMTP server receives any message.
5. Send to both regions concurrently, ensuring credentials/hosts never swap.
6. Resend the same command after state `SENT`; outbox/idempotency policy must block it unless duplicates are allowed.

With Testcontainers, use `getHost()` and `getMappedPort(1025)` for each container rather than assuming both share a host port. Use distinct subjects or correlation IDs per test; avoid flaky tests from leftover mailbox messages or unfinished `@Async` work.

### 17.4. Failover Integration Tests

You need a fake SMTP server capable of **controlled fault injection** to test protocol stages:

| Scenario | Expected result |
| --- | --- |
| Primary unreachable before submit | Secondary used only if in approved fallbacks |
| Primary returns permanent recipient error | Do not resend via secondary |
| Primary reports 250 accepted | Do not send via secondary |
| Connection lost after DATA, unclear outcome | No blind fallback; transition to UNKNOWN/reconciliation |
| Secondary not permitted for region | Fail closed, do not send |
| Primary auth fails | Credential/config alert, no aggressive retries |
| Primary throttles, secondary quota full | Schedule retry, do not force send |
| Policy changed between attempts | Attempt history keeps full selected policy/provider |

Default SMTP sinks mainly accept and store mail and may not simulate every 4xx/5xx error or post-DATA timeout. For those scenarios, use a programmable fake SMTP server, transport-layer mocks for pure logic, and appropriate integration harnesses.

### 17.5. Testing Webhooks and Suppression

With two providers, verify:

- Webhook A cannot pass verifier B.
- Duplicate event IDs are deduplicated per provider namespace.
- Late events after failover still map to the exact attempt/delivery.
- A verified hard bounce blocks subsequent sends **on both A and B** per policy.
- Marketing complaints are not treated as SMTP submission failures.
- `DELAYED` from provider A does not trigger submitting a new message to B while A retries internally.
- A DSN that cannot map to a delivery/recipient does not auto-remove valid recipients.

### 17.6. Security and Residency Tests

Test these invariants:

1. Users cannot pick `providerId` from a request to bypass permissions.
2. Tenant A cannot use tenant B's credentials/From domain.
3. Routes missing an approved region have **no global fallback**.
4. Logs and metrics never leak SMTP passwords/tokens.
5. Marketing emails lacking consent are never submitted to any provider.
6. Test accounts/SMTP sinks never relay to the public Internet.
7. Secondaries without verified domains are never selected.
8. When no valid provider exists, jobs get an explicit status/cause instead of vanishing silently.

In production, test against approved data-processing rules; an `EU` enum alone does not prove full infrastructure compliance.

## 18. Operational Scenario: Primary Provider Failure in One Region

Suppose at 09:00, the primary SMTP for transactional mail in VN loses connectivity. The system has an approved secondary in the same provider pool.

~~~text
09:00  smtp-vn-tx-a starts timing out before SMTP handshake
09:01  Queue VN/TRANSACTIONAL age begins rising
09:02  Circuit breaker opens for primary A
09:02  Routing policy confirms secondary B is eligible
09:03  New, not-yet-submitted deliveries are routed to B
09:04  Retryable attempts with proven pre-submission failure
       may route to B according to policy
09:05  A's unknown-outcome attempts remain for reconciliation
09:06  Dashboard shows increased route_reason=APPROVED_FALLBACK
09:10  A recovers; rollout back to A follows recovery policy
~~~

**Never mix these two job groups**:

- **Never submitted over SMTP or proven failed pre-submission:** may choose B if policy allows.
- **Possibly accepted by A without client confirmation:** reconcile and assess duplicate risk before resending via B.

### 18.1. Runbook When Fallback Spikes Rapidly

**Step 1 — Confirm signals.** Check failover rate, SMTP timeouts/auth failures, queue age, and metric sources. Never declare a provider outage from a single error request.

**Step 2 — Scope the impact.** How many `SECURITY`, `TRANSACTIONAL`, or `MARKETING` deliveries are affected, in which regions, and with how much time before deadlines?

**Step 3 — Inspect primary.** Check DNS/network, TLS, authentication, quotas, rate limits, recent secret changes, and provider status.

**Step 4 — Verify secondary eligibility.** Does secondary have verified sender identity, domain alignment, regional policy, free quota, and a working feedback route?

**Step 5 — Temporarily pace throughput.** Curb bulk traffic if needed to preserve capacity for security emails; do not exceed B's rate limits.

**Step 6 — Isolate UNKNOWN.** Do not bulk-redrive attempts that timed out after DATA or failed committing `SENT`.

**Step 7 — Confirm recovery.** Queue age drops, SMTP accepted rate recovers, bounces/complaints stay normal; keep monitoring late feedback from A.

### 18.2. When Secondary Is Ineligible

If B is out of quota, lacks a verified sender domain, or fails residency:

~~~text
no eligible secondary
      |
      v
hold/retry while still within business deadline
      |
      v
alert owner with safe error code
      |
      v
operator fixes capacity/configuration
      |
      v
dispatch if still allowed
~~~

This may be the **policy-correct** outcome even if SLOs suffer. Never fix the issue by deleting region checks or bypassing suppression.

## 19. Operational Scenario: Marketing Consumes Transactional Quota

An application has two rules, `MARKETING` and `TRANSACTIONAL`, yet both map to the same SMTP account. A big campaign starts at 08:00, the provider enforces quotas per account, and transactional emails start getting throttled.

~~~text
Marketing campaign 50,000 messages
            |
            v
Shared SMTP account quota
            |
            +--> bulk traffic uses capacity
            |
            +--> invoice/order mail receives temporary failures
~~~

Changing Java routing classes alone does not create capacity isolation. Determine the provider's real limits:

1. Can accounts/IP pools or credentials be split for independent quotas?
2. If quota is shared, can rate limiters reserve tokens for security/transactional traffic?
3. Does the scheduler check priority and deadlines before claiming bulk jobs?
4. Are marketing retries causing traffic spikes?
5. Are separate circuits/bulkheads in place so marketing error storms cannot starve worker threads?

A practical policy can pause marketing while transactional backlogs are high. Log/metric the reason clearly (`BULK_PAUSED_FOR_CAPACITY`) and define when the campaign resumes.

## 20. Common Troubleshooting Table

| Symptom | Possible cause | Fix |
| --- | --- | --- |
| All emails go through the default provider | Service accidentally injects `@Primary` or bypasses routing service | Use registry + policy; verify routes in attempt history |
| `NoUniqueBeanDefinitionException` injecting `JavaMailSender` | Multiple beans of the same type without `@Qualifier` | Inject explicit bean names or registry |
| `spring.mail.host` does not affect custom senders | Spring Boot auto-config backed off or bean does not bind property | Bind `app.mail.providers`, configure senders in factory |
| Thread A sends via thread B's endpoint | Mutating shared `JavaMailSenderImpl`/Session properties | Separate senders per endpoint/identity; avoid per-request mutation |
| Security email goes through marketing pool | Category taken from request or global fallback | Derive category from use case; validate candidate sets |
| EU email goes through US provider | Wrong region resolution or health overrode policy | Fail-close region/tenant constraints before checking health |
| Provider B rejects From/domain | Domain/identity unverified | Configure verified identities, SPF/DKIM/DMARC |
| SMTP auth fails on only one provider | Wrong secret or rotation not reloaded | Check secret version, permissions, TLS/AUTH |
| SMTP send succeeds yet events never arrive | Webhook/DSN route unconfigured or provider rolled back | Keep feedback ingestion active; check signatures/MX/Return-Path |
| Duplicate emails after failover | Primary outcome UNKNOWN yet app sent via B immediately | Persist UNKNOWN, reconcile, and retry with audit |
| Continuous retries despite bounced recipient | Suppression existed only on old provider | Central suppression per recipient/tenant and policy |
| Some recipients lost in a batch | Multiple recipients in one delivery with broken partial-failure handling | Split deliveries per recipient and store separate states |
| Policy changes break auditability | Policy version/provider ID not saved per attempt | Add route decision history |
| Bulk sends fast while OTP is slow | Shared quota/worker pool | Reserved capacity, per-category limiters |
| High latency despite healthy provider | Outbox backlog, DNS/TLS, attachment I/O | Measure queue wait, MIME build, and SMTP duration separately |
| Route rejected due to large file | Secondary has lower message size limit | Account for MIME overhead; choose download link if allowed |
| Dashboard shows empty queue yet nothing sends | Worker hung in-flight, producer not enqueuing, stale collector | Track in-flight, last progress, metric freshness |
| One region has no route | Missing configuration combination | Fail closed and alert `NO_ELIGIBLE_ROUTE` |

### 20.1. Provider Is Healthy Yet Route Is Blocked

This is not necessarily a bug:

~~~text
Provider health: HEALTHY
Delivery category: SECURITY
Provider capability: MARKETING only
Result: REJECTED_BY_POLICY
~~~

A provider working fine at the SMTP layer **is not automatically eligible** to process every email category.

### 20.2. "Region Mismatch" from Conflicting Data Sources

For instance, a tenant has an `EU_ONLY` policy while a user profile recently updated its address to VN. Never use the new profile location to silently drop the tenant's data-processing obligations. The system must prioritize approved policy and route conflicts to data verification or governance workflows.

### 20.3. Rotating Credentials in a Multi-Sender System

When a provider's password rotates, never log the entire `MultiProviderMailProperties` just to inspect config. You should:

- Store secret versions/references without raw secret values.
- Create or refresh senders under a controlled lifecycle.
- Verify authentication using health/smoke tests without exposing passwords.
- Avoid interrupting in-flight attempts where avoidable.
- Block new routes to old revoked senders.
- Keep ingesting webhooks/bounces for emails sent before rotation.

A bean that read its password at startup does not update automatically just because the secret manager updated. If the framework lacks safe live refresh, use rolling restarts/registry replacement per policy.

## 21. Frequently Asked Questions

**"Does Spring Framework Mail automatically choose providers by region?"**  
Not automatically. `JavaMailSender` sends over its configured transport; the application needs policy to resolve region/category, pick the sender, and record the route.

**"Can I use multiple JavaMailSender beans?"**  
Yes. Use `@Qualifier` on injection or a registry mapping senders by provider ID. Avoid a single shared mutable bean whose host/password changes before every request.

**"Should I mark a default provider with @Primary?"**  
Only when the application intentionally has a default and unconstrained services are allowed to use it. In systems routing by region/tenant, an implicit default can cause new code to send through the wrong provider. Registry + explicit policy are easier to govern.

**"Can spring.mail.host configure multiple endpoints?"**  
`spring.mail.*` normally describes one auto-configured sender. For multiple endpoints, create an `app.mail.providers` structure bound into a registry, or declare multiple explicit sender beans.

**"Should I route by the recipient's .vn/.eu/.com domain?"**  
No. TLDs do not prove recipient location or residency obligations. Use verified region data governed by tenant/account policy.

**"How does SECURITY email differ from TRANSACTIONAL?"**  
`SECURITY` usually needs short processing times and tight deadlines due to verification tokens/alerts. `TRANSACTIONAL` covers commerce/account activity. Both are business categories requiring consistent definitions, not arbitrary caller-chosen labels.

**"If the EU provider fails, can I immediately send via US?"**  
Only if data policy, agreements, and provider/identity conditions explicitly permit that route. Under an EU-only constraint, fail closed or wait for an EU provider rather than crossing regions just because US is healthy.

**"Can one SMTP provider serve multiple regions?"**  
Technically yes, though you must verify real regional processing capabilities, data handling, quotas, legal constraints, and policy. Logical provider names alone never prove physical location.

**"Can I fail over whenever JavaMailSender throws MailSendException?"**  
Not every `MailSendException` is safe to retry/fail over. Determine which stage failed, whether SMTP accepted, and whether duplicate risk exists.

**"If a timeout happens after DATA, should I send via provider B?"**  
Not automatically. Primary may have received the message; sending via B creates duplicates. Store `UNKNOWN`, reconcile, or apply an audited risk-accepting retry policy.

**"Can Message-ID guarantee exactly-once?"**  
No. `Message-ID` is tracing metadata, not something forcing SMTP servers to deduplicate. If a provider API supports idempotency keys, follow its contract; plain SMTP normally has a duplicate window.

**"Do failover and retry differ?"**  
Yes. Retry executes a new attempt, potentially on the same provider. Failover selects a different provider under policy. Log each separately to evaluate effectiveness and root causes.

**"Should I pick a random provider per email?"**  
Weighted routing across eligible candidates works when paired with stable assignment, capacity policies, and audits. Randomness per attempt makes retries unpredictable and hard to investigate.

**"Do marketing and security need separate domains?"**  
Not strictly required in every product, yet separating sending identities/traffic pools helps reputation and quotas when supported by infrastructure/providers. Matching SPF/DKIM/DMARC and verified sender domains are needed.

**"Is enabling SPF for provider A enough for provider B?"**  
Not necessarily. SPF/DKIM and domain verification must match each provider's sending infrastructure. An identity verified on A may not yet be authorized on B.

**"How do I handle bounces across multiple providers?"**  
Each provider has its own webhook/DSN format and source verification. Normalize events, correlate by provider ID + attempt/delivery/recipient, persist history, and enforce suppression at a shared layer when needed.

**"If provider A reports deferred, should I send a new copy via B?"**  
Not automatically. Provider A may still be retrying internally. Wait for a final outcome or follow a provider-coordinated policy to prevent duplicates.

**"After switching providers, are the old provider's webhooks still needed?"**  
Yes, because earlier emails can still emit late delivery/bounce events. Do not shut off ingestion the moment new traffic shifts elsewhere.

**"How do I prevent tenant A from using tenant B's credentials?"**  
Enforce authorization and tenant-scoped routing/identity mapping, never letting callers pass arbitrary provider IDs. Isolate secret references and audit trails per tenant.

**"If a provider is healthy yet out of quota, should I send anyway?"**  
Do not push past quotas. Pick an eligible secondary with capacity or schedule retry/backoff. Health and quota are independent conditions.

**"Should I increase the thread pool when a provider throttles?"**  
Usually counterproductive—it often increases errors. Use rate limiters, backoff, bulkheads, and pace traffic to real quotas.

**"Does outbox SENT mean the email reached the user's inbox?"**  
No, if `SENT` means SMTP accepted. Provider delivery feedback, bounces, and spam filtering are a separate tracking layer.

**"Where should the route policy version be stored?"**  
At minimum on the delivery or on each attempt, alongside provider/identity/reason. That enables reconciliation even after policy changes.

**"Must the route stay pinned across retries?"**  
Depends on policy. Pinning favors consistency; re-evaluating on retry helps recover from provider outages. Either way, every attempt must record the actual route and never violate region/identity constraints.

**"When no valid provider exists, should we generate an error email to the user?"**  
Do not default to sending another email when mail infrastructure itself is failing. Record state/cause, alert operators, and use a business-approved alternate channel if needed.

## 22. Multi-Provider Routing Deployment Checklist

### Business Design

1. Define categories (`SECURITY`, `TRANSACTIONAL`, `MARKETING`, or product-appropriate groups).
2. Canonicalize regions from trusted sources rather than inferring from email TLD/IP.
3. Define policy by category × region × tenant/sending identity.
4. Establish rules for consent, unsubscribe, suppression, and business deadlines.
5. Specify behavior when a route is missing: hold, retry, or fail—never silent fallback.
6. When sending to multiple recipients across regions, create separate deliveries/routes per recipient or compatible group.

### Providers and Sending Identities

7. Each SMTP endpoint has its own host/port/TLS/AUTH config and runtime secret.
8. Never mutate properties on a singleton sender per request.
9. Every `From`/domain/`Return-Path` is verified on the permitted provider.
10. Verify SPF, DKIM, DMARC, and bounce routing.
11. Store capability metadata: category, region, message size, quota, identity support.
12. Enforce tenant authorization to use providers/sending identities.
13. Never push secrets into logs, database audits, Docker images, or CI reports.

### Route Decisions and State

14. Route policies are versioned, audited, and tested across combinations.
15. Select the provider before creating MIME and send with that same `JavaMailSender`.
16. Persist provider/identity/policy version before the SMTP attempt.
17. Increment attempt counts consistently and store claim tokens/leases under concurrency.
18. Distinguish `SMTP_ACCEPTED`, `RETRY`, `FAILED`, and `UNKNOWN`.
19. Do not treat `Message-ID` as an exactly-once mechanism.
20. Outbox/broker retries use backoff, jitter, and max attempts/deadlines.

### Failover and Quotas

21. Fallbacks pick only from policy-approved providers.
22. Never fail over when SMTP outcome is unclear without assessing duplicate risk.
23. Never bypass region, suppression, or sender identity rules to boost delivery rates.
24. Enforce rate limits and capacity isolation for critical/transactional/bulk traffic.
25. Maintain circuit breakers and halt sending when an entire region's providers are unavailable.
26. Route according to message size capabilities and attachment limits.

### Feedback and Operations

27. Ingest each provider's webhooks/DSNs with separate origin verification.
28. Correlate provider events by attempt/delivery/recipient and deduplicate.
29. Keep old provider feedback ingestion active after rollout/rollback until reconciliation finishes.
30. Central suppression applies at the right scope across providers.
31. Maintain metrics for route decisions, rejections, failovers, SMTP outcomes, latency, quotas, and queue age.
32. Actionable alerts fire when security mail misses deadlines, no eligible routes exist, or auth failures spike.
33. Maintain runbooks for outages/secret rotation/identity mismatches and controlled redrives.

### Testing

34. Test the route matrix and disallowed combinations.
35. Test with two fake SMTP servers proving VN/EU never swap endpoints.
36. Test concurrent sending has no races from mutating sender properties.
37. Test partial SMTP failures, timeouts after DATA, and state-update failures.
38. Test unapproved fallbacks and out-of-region fallbacks are blocked.
39. Test accurate `From`/`Reply-To`, MIME/attachments, and size limits.
40. Test duplicate webhooks, late callbacks, bounces/complaints, and cross-provider suppression.
41. Test canary policy rollbacks preserve route history.
42. Never use production credentials or real recipients in integration tests.

## 23. Summary Model

~~~text
                  Trusted business event
                            |
                            v
                    Recipient delivery
                     (one recipient)
                            |
                            v
                   Transactional outbox
                            |
                            v
               Validate consent / suppression
                            |
                            v
                 Resolve category + region
                            |
                            v
                Versioned routing policy
                            |
                            v
           Provider candidates permitted by policy
                            |
            +---------------+----------------+
            |                                |
            v                                v
     Capability and identity          Health / rate limit
     TLS, domain, region, size         quota, circuit state
            |                                |
            +---------------+----------------+
                            |
                            v
              Select and persist route attempt
                            |
                 +----------+-----------+
                 |                      |
                 v                      v
           Primary SMTP            Approved secondary
                 |                      |
                 +----------+-----------+
                            |
                            v
                  JavaMailSender.send
                            |
            +---------------+----------------+
            |               |                |
            v               v                v
       Accepted         Safe failure       Unknown
            |               |                |
            v               v                v
          SENT           RETRY/FAILED     Reconciliation
            |               |                |
            +---------------+----------------+
                            |
                            v
                    Attempt history / audit
                            |
                            v
                   Metrics / alert / runbook
                            |
                            v
           Provider webhook / DSN processing
                            |
                            v
              Delivery feedback + suppression
~~~

The model shows that **routing** is not an isolated if/else layer. It is tied to trusted business data, sender identity, provider capabilities, quotas, retries, event feedback, and data policies.

### Key Takeaways

- **Email category and region are two independent dimensions**; a marketing email to an EU recipient must satisfy both marketing and EU rules simultaneously.
- **Never route on untrusted data** such as request-supplied provider IDs or email TLDs.
- **Each provider/identity uses its own configured sender**, never mutating a singleton's host/credentials before each send.
- **Fail over only within the permitted set**, and only when enough is known about the SMTP outcome to avoid dangerous resends.
- **Submission is not inbox delivery**; DSNs/webhooks and per-attempt reconciliation are required.
- **Data residency is an end-to-end concern**, not just an SMTP hostname.
- **Audit policy versions and provider IDs** to trace past decisions after configuration changes.
- **Security/transactional traffic must be shielded from bulk quotas**, using routing, reserved capacity, and appropriate limits.

## Conclusion

**Routing by email type or region** in Spring Framework Mail is the challenge of coordinating business policy across multiple SMTP transports. An implementation can start with multiple separately configured `JavaMailSenderImpl` beans and a `MailRoutingPolicy` deciding by `MailCategory`, `DeliveryRegion`, and verified identity. As scale grows, add a registry, capability filtering, quotas, health, an outbox, audit trails, and a delivery-feedback pipeline.

A reliable solution does more than pick a provider that "is running." It must prove the provider **is authorized to handle that specific delivery**, use the right sender identity, respect regional boundaries, avoid blind duplicates when SMTP outcomes are ambiguous, and continue tracking bounces/complaints after provider switches. When these boundaries are cleanly designed, the system can isolate security, transactional, and marketing streams, operate across regions, and recover in a controlled manner without sacrificing correctness, security, or auditability.
