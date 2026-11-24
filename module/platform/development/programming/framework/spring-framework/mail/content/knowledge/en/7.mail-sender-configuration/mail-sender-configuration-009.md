# Senders for Transactional Email and Marketing Email

A Spring application can send many kinds of email: account verification, password resets, order confirmations, payment notices, product newsletters, and promotional campaigns. All of them can travel over SMTP, yet **transactional email** and **marketing email** have different goals, operational requirements, and recipient policies. Therefore, sender configuration should clearly reflect the distinction between the two streams.

In **Spring Framework Mail**, `JavaMailSender` is the mail-sending interface. You can use a single sender for simple cases, or declare **two separate senders** when you need distinct SMTP accounts, sender addresses, rate limits, or delivery infrastructure. Separating senders in code routes messages through the right channel, whereas truly isolating sender reputation and quotas requires matching configuration at the email provider.

This lesson walks through choosing an architecture, configuring multiple `JavaMailSender` beans, using `@Qualifier` to route messages, designing sender and unsubscribe headers, and handling errors, queues, quotas, and deliverability tracking.

## 1. How do transactional email and marketing email differ?

### 1.1. Transactional email

Transactional emails are triggered by **a specific business action or state change** involving a user. For example:

- Verifying an email address during account registration.
- Sending a password reset link.
- Confirming an order or payment.
- Sending invoices, receipts, and appointment change notices.
- Notifying support ticket status or account security events.

Common characteristics:

- Must reach **the right person**, promptly, with accurate content.
- Volume tracks application activity and can spike suddenly.
- Delivery failure can directly block features such as sign-in or checkout.
- Needs traceability by user, business event, or outbox ID alongside a retry strategy.
- Content should stay scoped to the transactional purpose; avoid stuffing unnecessary promotions into critical security messages.

Example subject: `Order confirmation #ORD-2081`.

### 1.2. Marketing email

Marketing emails serve **outreach, product announcements, or campaigns**. For example:

- Weekly newsletters, product updates.
- Promotional offers and discount announcements.
- Re-engagement campaigns for subscribed user segments.
- New feature announcements or marketing events.

Common characteristics:

- Recipients come from **subscriber lists and segments**.
- Can be sent on schedules or in large batches.
- Requires managing opt-in consent, unsubscribes, suppression lists, bounces, and complaints.
- Focuses on send rates, domain reputation, inbox placement, and campaign analytics.
- May call for a dedicated marketing platform when automation, segmentation, and complex content management are needed.

Example subject: `November Newsletter: New Features`.

### 1.3. Comparison table for sender design

| Criterion | Transactional email | Marketing email |
|---|---|---|
| Trigger | Specific business event. | Campaign, recurring schedule, or audience segment. |
| Priority | Low latency, accuracy, traceability. | Rate control, list hygiene, campaign effectiveness. |
| Audience | Users directly involved in the event. | Users eligible to receive marketing content. |
| Send controls | Business request idempotency, outbox, retries. | Consent, unsubscribe, suppression, quotas, schedule. |
| Typical sender address | `receipts@example.com`, `security@example.com`. | `news@example.com`, `offers@example.com`. |
| Reply-To | Customer support or transactional contact channel. | Campaign reply channel or monitored mailbox. |
| Monitoring | Acceptance status, delivery, bounces, send errors. | Deliveries, bounces, complaints, unsubscribes, campaign metrics. |
| Impact of backlog | Can disrupt critical business journeys. | Campaign arrives late or underperforms. |

**Not every automated email is transactional.** A message triggered by "user just viewed a product" can still be marketing. Classify by **content purpose and recipient eligibility**, not merely by whether it was generated automatically or manually.

## 2. What configuration layers make up a sender?

The word "sender" in a Spring project often spans several components. Distinguish them to avoid false assumptions:

| Layer | Example | Responsibility |
|---|---|---|
| **Spring sending bean** | `JavaMailSender` | Builds/sends `MimeMessage` via transport configuration. |
| **SMTP account / system** | Host, port, username, password, TLS | Authenticates and accepts mail submission requests. |
| **Header identity** | `From:`, `Reply-To:` | Tells recipients who sent the message and where to reply. |
| **SMTP envelope** | `MAIL FROM` / envelope sender | Mainly serves routing and bounce handling; may differ from `From:` header. |
| **Domain & authentication** | SPF, DKIM, DMARC | Proves sending authority and supports identity and receiver policies. |
| **Delivery policy** | Rate limits, queues, suppression | Regulates volume and eligible recipients. |
| **Receiving / tracking service** | Webhooks, events, dashboards | Reports deliveries, bounces, or complaints after acceptance. |

Creating two `JavaMailSender` beans does not automatically create two domain reputations, two IPs, or two quota pools. Those resources are controlled by the provider or mail server. Conversely, changing only the `From:` header while sharing the same SMTP account and rate limit still lets marketing campaigns impact transactional mail.

## 3. Three ways to organize senders

### Option A — One JavaMailSender, multiple content types

The application uses one SMTP account and one `JavaMailSender` bean, while each email sets a different `From`/`Reply-To` **if permitted by the provider**.

```text
OrderService -------\
                     +--> JavaMailSender --> Single SMTP account/relay
CampaignService ----/
```

Suitable when:

- The application is small with modest mail volume.
- Both flows share similar infrastructure policies and quotas.
- The provider authorizes all intended sender identities.
- The application still checks marketing consent and prevents campaigns from starving capacity.

Drawback: hard to isolate quotas, connections, failures, and sending reputation when a campaign creates heavy load. Changing `From` alone does not provide infrastructure isolation.

### Option B — Two JavaMailSenders with separate accounts or configurations

The application defines one sender for transactional mail and one for marketing:

```text
                   +--> transactionalMailSender
OrderService ------|         |
                   |         +--> Transactional SMTP account / relay
                   
                   +--> marketingMailSender
CampaignWorker ----|         |
                             +--> Marketing SMTP account / relay
```

Suitable when:

- Different credentials, SMTP hosts, or quotas are required.
- Different retry, rate, and priority policies are needed.
- You want to prevent marketing bursts from delaying transactional emails.
- You want to switch providers per stream without affecting the other.

The two senders can target **two different hosts**, or the same host with distinct usernames, subaccounts, domain configs, or provider-isolated pools.

### Option C — Transactional via Spring Mail, marketing via dedicated service

```text
Order / Security
      |
      +--> JavaMailSender --> Transactional SMTP

Campaign / Newsletter
      |
      +--> Provider SDK / HTTP API / marketing platform
                                  |
                                  +--> campaigns, consent,
                                       suppression, analytics
```

Suitable when marketing requires segmentation, A/B testing, campaign scheduling, reporting, automated unsubscribes, or delivery/bounce events that plain SMTP does not conveniently offer.

Business layers can depend on interfaces like `TransactionalEmailGateway` and `MarketingEmailGateway`; each implementation can call `JavaMailSender` or a dedicated API. Choosing the transport technology does not force redefining transactional vs. marketing semantics.

## 4. Designing sender identity: From, Reply-To, and envelope sender

Suppose an application has two mail streams:

| Property | Transactional | Marketing |
|---|---|---|
| `From:` | `receipts@example.com` | `news@example.com` |
| Display name | `Example Receipts` | `Example Newsletter` |
| `Reply-To:` | `support@example.com` | `campaigns@example.com` |
| Envelope sender | Bounce-return address/domain configured by SMTP provider for transactional flow | Bounce-return address/domain for marketing flow |
| Management channel | Order, account, and security events | Consent, lists, and campaigns |

### 4.1. From is the displayed sender identity

Example:

```text
From: "Example Receipts" <receipts@example.com>
Reply-To: support@example.com
```

`From` tells the mail client who the displayed author/sender of the message is. The `From` address must belong to an identity/domain that the SMTP account or service **is authorized to send from**. Never spoof someone else's address merely by setting a header.

In Spring:

```java
helper.setFrom("receipts@example.com");
helper.setReplyTo("support@example.com");
```

A Unicode display name can be set via `MimeMessageHelper.setFrom(String, String)` and is encoded using the library's MIME support. When using that overload, code must handle both `MessagingException` and `UnsupportedEncodingException` per the API signature.

### 4.2. Reply-To directs responses

`Reply-To` can differ from `From`. For example, a marketing sender uses `news@example.com` while replies go to a campaign support inbox. Avoid using a "no-reply" address that leaves users with no contact channel when business workflows need replies.

In marketing email, the `Reply-To` address should be monitored or handled by a workflow. The system still needs an independent unsubscribe mechanism; forcing users to reply manually to unsubscribe generally fails modern UX and bulk-sender policies.

### 4.3. Envelope sender and Return-Path

In SMTP, the client declares:

```text
MAIL FROM:<bounces@bounce.example.com>
RCPT TO:<alice@example.net>
```

The `MAIL FROM` address, also called the **envelope sender / reverse-path**, primarily governs delivery error notifications. It **does not have to match** the `From:` header inside the message.

Normally the receiving server generates the `Return-Path` header from the mail transfer path; do not assume manually setting `Return-Path` on a `MimeMessage` is a valid way to control the bounce address.

With the Jakarta Mail SMTP provider, the `mail.smtp.from` property can control the envelope sender at the Transport level. However, managed SMTP services may enforce or override values according to their own domain/return-path verification policies.

When separating transactional and marketing streams, consider separate **bounce identities** supported by your provider. This helps analyze per-stream delivery status and manage sending reputation, provided DNS, sender policies, and authentication are configured properly.

### 4.4. SPF, DKIM, DMARC, and alignment

Having the right sender bean alone is not enough for emails to be trusted:

- **SPF** publishes which servers/infrastructure are authorized to send for the domain checked by SPF, usually tied to the envelope sender.
- **DKIM** cryptographically signs selected parts of the message with a key tied to the signing domain so receivers can verify integrity and the declared source.
- **DMARC** sets evaluation and handling policy based on whether SPF/DKIM results **align** with the `From:` header domain.

Alignment does not require identical full strings; it follows domain rules and DMARC policy modes. Verify domains or subdomains with your provider, inspect DNS records, and check actual authentication results.

If transactional and marketing streams use distinct subdomains, such as `tx.example.com` and `news.example.com`, manage DNS, DKIM, and SPF appropriately for each stream. Subdomain separation **can** help classify traffic and operate reputation independently, though actual isolation still depends on infrastructure/IPs/pools and receiver evaluation.

## 5. Configuring two JavaMailSenders in Spring Boot

This section illustrates **two independent sender beans** in Spring Boot 3.x, Spring Framework 6.x, Java 17+, using Jakarta Mail.

### 5.1. Adding the dependency

With Gradle Groovy DSL:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-mail'
}
```

The starter supplies the Spring Mail and Jakarta Mail components needed for standard SMTP setups.

### 5.2. Declaring two channels in application.yml

Instead of relying on a single default auto-configured `spring.mail.*` group, this example uses a custom `app.mail.*` namespace to create **two** `JavaMailSenderImpl` beans:

```yaml
app:
  mail:
    transactional:
      host: ${TX_SMTP_HOST}
      port: ${TX_SMTP_PORT:587}
      username: ${TX_SMTP_USERNAME}
      password: ${TX_SMTP_PASSWORD}
      from: receipts@example.com
      reply-to: support@example.com

    marketing:
      host: ${MKT_SMTP_HOST}
      port: ${MKT_SMTP_PORT:587}
      username: ${MKT_SMTP_USERNAME}
      password: ${MKT_SMTP_PASSWORD}
      from: news@example.com
      reply-to: campaigns@example.com
```

Environment variables holding credentials must be provided by the deployment platform or secret store. Use provider-verified sender addresses; `example.com` addresses are illustrative only.

### 5.3. Binding configuration with ConfigurationProperties

Create a record for Spring Boot to bind configuration data. If the codebase does not use Java records, substitute a class with matching getters/setters:

```java
package com.example.mail;

import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "app.mail")
public record MailChannelsProperties(
    Channel transactional,
    Channel marketing
) {
    public record Channel(
        String host,
        int port,
        String username,
        String password,
        String from,
        String replyTo
    ) {}
}
```

Spring Boot automatically binds kebab-case `reply-to` to the `replyTo` field. A record structure works well when both streams share the same configuration fields.

### 5.4. Creating two sender beans per channel

```java
package com.example.mail;

import java.util.Properties;
import org.springframework.boot.context.properties.EnableConfigurationProperties;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.mail.javamail.JavaMailSender;
import org.springframework.mail.javamail.JavaMailSenderImpl;

@Configuration
@EnableConfigurationProperties(MailChannelsProperties.class)
public class MailSenderConfiguration {

    @Bean("transactionalMailSender")
    public JavaMailSender transactionalMailSender(MailChannelsProperties config) {
        return createSender(config.transactional());
    }

    @Bean("marketingMailSender")
    public JavaMailSender marketingMailSender(MailChannelsProperties config) {
        return createSender(config.marketing());
    }

    private JavaMailSender createSender(
            MailChannelsProperties.Channel channel) {
        JavaMailSenderImpl sender = new JavaMailSenderImpl();
        sender.setHost(channel.host());
        sender.setPort(channel.port());
        sender.setUsername(channel.username());
        sender.setPassword(channel.password());
        sender.setDefaultEncoding("UTF-8");

        Properties properties = sender.getJavaMailProperties();
        properties.put("mail.transport.protocol", "smtp");
        properties.put("mail.smtp.auth", "true");
        properties.put("mail.smtp.starttls.enable", "true");
        properties.put("mail.smtp.starttls.required", "true");
        properties.put("mail.smtp.connectiontimeout", "5000");
        properties.put("mail.smtp.timeout", "5000");
        properties.put("mail.smtp.writetimeout", "5000");

        return sender;
    }
}
```

How each piece works:

1. `@EnableConfigurationProperties` registers `MailChannelsProperties` so Spring binds `app.mail.*`.
2. Each `@Bean` invokes `createSender(...)` with its own channel, giving the two beans independent host, port, and credentials.
3. `@Bean("transactionalMailSender")` and `@Bean("marketingMailSender")` define clear names for purpose-specific injection.
4. `mail.smtp.starttls.required=true` requires TLS upgrade to succeed when using STARTTLS; on failure it refuses to fall back to an unencrypted connection.
5. Timeouts prevent indefinite waiting if an SMTP server is slow or unresponsive.

This example fits providers using **port 587 SMTP submission with STARTTLS and AUTH**. If one channel uses port 465 with implicit TLS, configure `mail.smtp.ssl.enable=true` with matching port/TLS settings. If an internal relay does not use SMTP AUTH, configure it per relay documentation instead of forcing one property set across all environments.

Once multiple `JavaMailSender` beans are declared, injecting **purely by type** cannot resolve which bean to pick. Use `@Qualifier` or an explicit routing business adapter; never rely on bean declaration order.

### 5.5. Using @Qualifier to send on the right stream

The service below injects the two separate senders and reads `From`/`Reply-To` from the bound configuration:

```java
package com.example.mail;

import jakarta.mail.MessagingException;
import jakarta.mail.internet.MimeMessage;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.mail.javamail.JavaMailSender;
import org.springframework.mail.javamail.MimeMessageHelper;
import org.springframework.stereotype.Service;

@Service
public class ApplicationMailService {

    private final JavaMailSender transactionalSender;
    private final JavaMailSender marketingSender;
    private final MailChannelsProperties channels;

    public ApplicationMailService(
            @Qualifier("transactionalMailSender")
            JavaMailSender transactionalSender,
            @Qualifier("marketingMailSender")
            JavaMailSender marketingSender,
            MailChannelsProperties channels) {
        this.transactionalSender = transactionalSender;
        this.marketingSender = marketingSender;
        this.channels = channels;
    }

    public void sendOrderConfirmation(String recipient, String orderCode)
            throws MessagingException {
        MimeMessage message = transactionalSender.createMimeMessage();
        MimeMessageHelper helper =
            new MimeMessageHelper(message, "UTF-8");

        helper.setFrom(channels.transactional().from());
        helper.setReplyTo(channels.transactional().replyTo());
        helper.setTo(recipient);
        helper.setSubject("Order confirmation " + orderCode);
        helper.setText(
            "Your order " + orderCode + " has been recorded."
        );

        transactionalSender.send(message);
    }

    public void sendNewsletter(
            String recipient,
            String htmlBody,
            String plainTextBody) throws MessagingException {
        // Callers must verify consent and suppression before sending.
        MimeMessage message = marketingSender.createMimeMessage();
        MimeMessageHelper helper =
            new MimeMessageHelper(message, true, "UTF-8");

        helper.setFrom(channels.marketing().from());
        helper.setReplyTo(channels.marketing().replyTo());
        helper.setTo(recipient);
        helper.setSubject("Product Newsletter");
        helper.setText(plainTextBody, htmlBody);

        // Basic example; real campaigns need valid unsubscribe headers
        // and a working endpoint, covered below.
        marketingSender.send(message);
    }
}
```

In the example:

- Order confirmations go through `transactionalSender`.
- Newsletters go through `marketingSender`.
- Each email carries the `From` and `Reply-To` of its channel.
- `MimeMessageHelper.setText(plain, html)` sends both plain text and HTML.
- There is no bulk sending loop inside a request: campaigns should run via workers or a campaign system with recipient eligibility checks.

**Important:** `sendNewsletter(...)` illustrates sender routing, not a complete marketing delivery system. Before production use, implement full consent, unsubscribe, suppression, sender address, and rate-control checks.

### 5.6. Distinguishing @Primary and @Qualifier

When two beans implement `JavaMailSender`, if a service writes:

```java
public AlertService(JavaMailSender sender) {
    this.sender = sender;
}
```

Spring can fail with a non-unique bean error (without a disambiguating resolver). Instead use:

```java
public AlertService(
        @Qualifier("transactionalMailSender") JavaMailSender sender) {
    this.sender = sender;
}
```

In an existing application with many legacy services using one sender, `@Primary` can designate a default **if the default's semantics are unambiguous**. Still, where transactional and marketing flows are distinguished, `@Qualifier` makes channel choice much clearer to readers.

## 6. Separating senders with business interfaces

As a system grows, you can separate:

```java
public interface TransactionalEmailGateway {
    void sendReceipt(String recipient, String orderCode);
}

public interface MarketingEmailGateway {
    void sendCampaignMessage(String recipient, String campaignId);
}
```

The first implementation can call `transactionalMailSender`; the second can call `marketingMailSender` or a campaign service SDK.

Advantages:

- Order services cannot accidentally use the marketing sender just because both share the `JavaMailSender` interface.
- Each domain can attach its own queues, retries, logging, and metrics.
- Easy to swap providers for one stream without modifying calling services.
- Business code passes purpose-level arguments (`orderCode`, `campaignId`) instead of assembling all SMTP headers itself.

For small apps, injecting two senders with `@Qualifier` may already suffice; avoid adding extra abstractions before concrete needs justify them.

## 7. Specific requirements when configuring a marketing sender

### 7.1. Consent: who is allowed to receive messages?

Before sending marketing mail, the application must verify whether the user opted in to that specific content category and whether consent remains valid. Typical records to manage include:

- Email address and associated user.
- Opted-in email categories (newsletter, offers, product updates).
- Opt-in timestamp/source and consent proof where required.
- Unsubscribe timestamp and scope.
- Bounce/complaint status and active suppressions.

Never assume a past purchaser opted in to all campaigns. Conversely, a user unsubscribing from marketing **is generally not a reason to stop necessary transactional emails**; actual sending policies still depend on legal requirements and content purpose in your operating context.

### 7.2. Unsubscribe and list headers

Marketing emails need a convenient, working unsubscribe mechanism that promptly updates sending lists. Example footer text:

```text
You are receiving this email because you subscribed to the Example newsletter.
Unsubscribe: https://example.com/email/unsubscribe?token=<opaque-token>
```

`<opaque-token>` here is only a placeholder; in production systems the token must be securely issued, bound to the recipient and subscription scope, and free of guessable secrets or exposed personal data.

Beyond body links, marketing emails can include `List-Unsubscribe` headers. To support **one-click unsubscribe per RFC 8058**, headers typically look like:

```text
List-Unsubscribe: <https://example.com/email/one-click/<opaque-token>>
List-Unsubscribe-Post: List-Unsubscribe=One-Click
```

Important details to get right:

1. Add these headers only when the URL is truly an HTTPS endpoint supporting **one-click POST** per the specification; not merely a form page or login-gated page.
2. The endpoint must resolve the subscription using an unguessable token and execute idempotently so repeated requests cause no business errors.
3. Do not auto-unsubscribe merely because a link scanner issues a GET; distinguish one-click POST requests from ordinary visits.
4. Under RFC 8058, `List-Unsubscribe` and `List-Unsubscribe-Post` headers must be covered by a valid DKIM signature so receivers trust one-click actions.
5. Ensure the provider/SMTP relay preserves or supports these headers; some marketing platforms manage unsubscribes themselves and restrict custom overrides.

In `MimeMessage`, given a **trusted system-generated** HTTPS URL, you can set the headers:

```java
MimeMessage message = marketingSender.createMimeMessage();
MimeMessageHelper helper =
    new MimeMessageHelper(message, true, "UTF-8");

helper.setFrom("news@example.com");
helper.setTo(recipient);
helper.setSubject("This Month's Newsletter");
helper.setText(plainTextBody, htmlBody);

// oneClickUrl: valid HTTPS URL generated by the app, never raw user input.
message.setHeader("List-Unsubscribe", "<" + oneClickUrl + ">");
message.setHeader("List-Unsubscribe-Post", "List-Unsubscribe=One-Click");

marketingSender.send(message);
```

The snippet illustrates **setting headers**; it assumes `recipient`, `oneClickUrl`, `plainTextBody`, `htmlBody`, and `marketingSender` are supplied in context and that the system has a live one-click endpoint, DKIM signing, and complete consent checks. Never accept arbitrary URLs containing newlines directly into headers.

Unsubscribe rules and bulk-sending requirements vary by jurisdiction, provider, and receiving mail service. Apply rules tailored to your target markets and mailing lists.

### 7.3. Suppression lists and delivery feedback

A **suppression list** tracks addresses that must no longer receive messages for one or more reasons: unsubscribes, hard bounces, complaints, manual blocklists, or user requests.

Marketing pipelines need to:

1. Check consent and suppression when building the target list.
2. Re-check right before the worker actually sends, since users may unsubscribe after the campaign is scheduled.
3. Ingest bounce/complaint webhooks or events from the provider where supported.
4. Update recipient status and block future sends according to policy.
5. Separate marketing suppression from continuing necessary transactional emails, where permitted by policy and law.

A successful `mailSender.send(...)` call **does not provide** downstream bounce and complaint data generated after the SMTP relay accepts the message. If that feedback is core to your workflow, you need provider event integrations or a dedicated email platform.

### 7.4. One recipient per message is usually easier to manage

When sending personalized newsletters, create **one message per recipient**:

- Easy to embed per-recipient unsubscribe links and tokens.
- Avoids exposing recipient email lists via `To` or `Cc`.
- Easy to track bounces, complaints, and campaign status per address.
- Easy to control retries and suppressions individually.

Never put an entire customer list into a single `To` field. `Bcc` hides addresses from displayed headers, yet cannot substitute for a marketing delivery system with per-recipient tracking, segmentation, and unsubscribe handling.

## 8. Priority and sending rate: keep marketing from slowing transactions

### 8.1. Organizing queues per channel

```text
Order creation event
        |
        v
transactional_outbox / transaction_queue
        |
        v
Transactional worker ----> transactionalMailSender
                                    |
                                    v
                              Transactional SMTP

Scheduled campaign
        |
        v
campaign_queue / marketing_jobs
        |
        v
Marketing worker --(rate limit)--> marketingMailSender
                                         |
                                         v
                                   Marketing SMTP
```

This layout allows you to:

- Prioritize transactional mail when load spikes.
- Maintain separate retry/backoff strategies.
- Pause a campaign without halting password-reset emails.
- Monitor queue lag, throughput, errors, and quotas separately.

**Two sender beans do not automatically create queues or concurrency controls.** To gain those properties, implement them in application workers, message brokers, or your email provider.

### 8.2. Provider rate limits and quotas

Limits can include emails/second, recipients/hour, message size, concurrent SMTP connections, or quotas per account/domain/IP.

If a provider returns temporary errors for exceeding send rates, marketing workers should:

- Reduce concurrency or sending rate.
- Retry with reasonable backoff and jitter.
- Honor provider rate limits or retry signals where given.
- Avoid unbounded retries that cause overload.
- Provide a circuit-breaker or pause mechanism if errors persist or bounce rates spike.

For transactional mail, latency targets are tighter and alerts should fire early if queue depth climbs. If both senders share one provider quota, separating beans in Spring **is not enough** to shield transactional mail from campaigns.

### 8.3. Classifying retries by error type

| Scenario | Typical handling |
|---|---|
| Connection timeout before sending data | Retry with backoff; inspect network health and quotas. |
| Temporary SMTP `4xx` | Controlled retry if eligible; respect provider policy. |
| `535` authentication failed | Inspect credentials/config; blind retries rarely help. |
| `550 5.1.1` address does not exist | Mark address invalid; do not retry unconditionally. |
| Timeout **after sending DATA** before final reply | Outcome may be uncertain; retrying risks duplicates. |
| Bounce/complaint after provider acceptance | Update suppression and state from provider events; do not treat as connect error. |

A transactional notification like a receipt usually needs **a stable business event ID**, because retries should not create multiple independent send requests. Marketing requires campaign/recipient keys plus an unsubscribe check immediately before each send.

## 9. Send states and Message-ID

In email systems, several distinct identifiers often appear together:

| ID | Source | Purpose |
|---|---|---|
| `outboxId` / `eventId` | Application | Traces a send request tied to a business action. |
| `campaignId` + `recipientId` | Marketing system | Identifies one campaign delivery to a specific recipient. |
| `Message-ID` header | Message builder / Jakarta Mail / provider | Identifies an email message. |
| SMTP queue ID | SMTP server | Correlates relay acceptance logs. |
| Provider message ID | Email service | Queries provider-side events and status. |

Never treat `Message-ID` as an SMTP-enforced idempotency key. Two sends carrying the same Message-ID can still be delivered as two copies. For transactional mail, maintain an outbox ID and track each attempt; for marketing, `(campaignId, recipientId)` keys prevent duplicate job creation.

### 9.1. States worth distinguishing

```text
CREATED / QUEUED
      |
      v
SENDING
      |
      +--> ACCEPTED_BY_SMTP / ACCEPTED_BY_PROVIDER
      |            |
      |            +--> DELIVERED (when event arrives)
      |            +--> BOUNCED (when event arrives)
      |
      +--> TEMPORARY_FAILURE -> bounded retry
      |
      +--> PERMANENT_FAILURE -> handle error / suppression
      |
      +--> UNKNOWN -> reconcile / retry cautiously
```

**`ACCEPTED_BY_SMTP` does not equal `DELIVERED`.** Without reliable delivery events, never mark an email delivered right after a successful `send(...)`.

When using `JavaMailSender`, `MailException` reflects failures during Spring-managed preparation/sending. Operations on `MimeMessage` or `MimeMessageHelper` can throw Jakarta Mail's `MessagingException`. Separate content-building failures from transport failures and downstream delivery failures.

## 10. Separate monitoring and alerting per channel

A sound sender configuration needs matching observability:

| Metric | Transactional | Marketing |
|---|---|---|
| Requested / SMTP-accepted count | Per minute and per business event type. | Per campaign and per send batch. |
| Latency | From business event to SMTP acceptance. | From campaign schedule to per-recipient processing. |
| Queue lag | Alert early on sudden spikes. | Tune worker count and send rate. |
| Errors by type | TLS/AUTH/timeout/recipient/size. | Rate limits, bounces, complaints, suppressions. |
| Delivery events | Where provider supports it, track critical emails. | Track by campaign, recipient, and segment. |
| Rejection rate | Helps spot sender/config issues. | Crucial for protecting list hygiene. |

Example structured logs:

```text
channel=transactional event_id=evt-1028
recipient_hash=... status=accepted_by_smtp
duration_ms=420

channel=marketing campaign_id=nov-newsletter
recipient_hash=... status=rate_limited
attempt=2
```

Never log SMTP passwords, password-reset tokens, tokenized unsubscribe URLs, sensitive body content, or full recipient addresses without legitimate need and access controls. Splitting logs by channel helps pinpoint incidents without exposing full email payloads.

### 10.1. Risks when sharing a single provider

If transactional and marketing streams share underlying infrastructure, clarify:

- Are quotas separated by API key or subaccount?
- Are IPs or sending pools isolated?
- Are sending domains or subdomains verified separately?
- Can marketing bounces/complaints affect transactional quotas or reputation?
- Is capacity reserved for critical transactional flows?

Answers depend on the actual service. Changing an SMTP username alone does not guarantee isolated IPs or sending reputation.

## 11. Architecture selection scenarios

### 11.1. Small app sending a few hundred emails per day

A website sends order confirmations and occasional newsletters to subscribers. The provider offers one SMTP account and webhooks are not yet needed.

You can start with one `JavaMailSender`, provided you maintain:

- Two clear service flows without mixing content.
- Consent/suppression checks for newsletters.
- Rate limiting on campaigns so they do not exhaust resources.
- Authorized `From` addresses and a working unsubscribe flow.
- Error and deliverability monitoring.

As volume grows or delivery SLAs diverge, split senders and underlying infrastructure accordingly.

### 11.2. E-commerce needing prioritized transactional mail

Orders, invoices, and password resets require fast delivery; marketing sends large daily batches.

Recommended setup:

1. Transactional outbox or prioritized queue.
2. `transactionalMailSender` and SMTP setup with sufficient transactional quota.
3. Separate marketing queue/workers, with rate-limited and scheduled `marketingMailSender`.
4. Provider events capturing bounces/deliveries where needed.
5. Per-channel dashboards and alerts.

This separation clarifies business boundaries and keeps campaigns from disrupting account and checkout flows.

### 11.3. Multi-campaign marketing with complex segmentation

When you need list management, templated content, A/B testing, audience segmentation, customer-journey automation, or campaign analytics, an **email marketing platform** usually fits better than writing bulk loops over `JavaMailSender`.

Spring can keep handling the transactional sender while marketing integrates via the dedicated platform's SDK/API or workflows. Ensure the application still enforces consent policies and synchronizes state appropriately per channel.

## 12. Common mistakes when configuring senders

### 12.1. "I created two JavaMailSenders, so I definitely have two sending reputations"

No. Beans are JVM configurations. IPs, pools, quotas, and reputation are evaluated by providers/relays and receiving servers. True isolation requires matching provider-level configuration.

### 12.2. "To send marketing, just change the `From` address on the transactional sender"

Insufficient if content, send rates, consent, unsubscribes, and suppression are uncontrolled. A `From` header alone does not make a safe marketing pipeline.

### 12.3. "When a user unsubscribes from marketing, stop all emails"

Distinguish marketing unsubscribe scope from transactional necessity. Password resets or receipts must follow business rules and applicable policies rather than getting swept into campaign blocks simply for sharing SMTP.

### 12.4. "Success from JavaMailSender means the email arrived"

No. A successful send usually only means the SMTP server accepted the message. Final delivery, bounces, and complaints can occur afterward.

### 12.5. "Spring Boot automatically knows which bean is transactional"

No. With multiple beans of the same type, route deliberately via `@Qualifier`, adapter beans, or business structure; never leave resolution to chance.

### 12.6. "Putting all recipients in one `To` saves effort and stays private"

No. `To` and `Cc` headers expose recipient lists to everyone. Personalized marketing typically needs one message per recipient with individual unsubscribe tokens and tracking states.

### 12.7. "Adding `List-Unsubscribe-Post` automatically enables one-click"

No. It requires a live HTTPS POST endpoint following the one-click contract, secure tokens, real unsubscribe processing, DKIM signing covering those headers, and provider support.

### 12.8. "Enabling `starttls.enable` already mandates encryption"

Not necessarily. To require STARTTLS to succeed, you typically also need `mail.smtp.starttls.required=true` with a compatible Jakarta Mail SMTP provider. Port 465 uses a different implicit TLS model.

### 12.9. "Changing `From` automatically changes where bounces go"

No. `From` is the display header; the envelope sender and bounce-handling address can be configured separately on SMTP/provider side. Check sending domain and service return-path settings.

## 13. Practice exercises

### Exercise 1 — Choosing senders

An app sends registration verification codes and a monthly newsletter. Verification needs fast delivery; the newsletter goes to 50,000 subscribers with unsubscribe support.

**Question:** Should you use one or two sending channels? What else must be separated beyond Spring beans?

**Hint:** Two channels with separate queues/rate limits and policies make more sense; consider credentials, provider quotas, domains/subdomains, and event tracking while enforcing marketing consent and suppression.

### Exercise 2 — Configuring two beans

Using `MailChannelsProperties` and `MailSenderConfiguration`, add a third `security` channel dedicated to security emails if required by the system. Give the new bean a clear name, its own SMTP configuration, and inject it via `@Qualifier` in the appropriate service.

**Hint:** No need to manually build a `Session` per email; `JavaMailSenderImpl` manages Jakarta Mail underneath.

### Exercise 3 — Distinguishing addresses

An email displays:

```text
From: "Example Newsletter" <news@example.com>
Reply-To: campaigns@example.com
```

The provider configures the envelope sender as `bounce@bounces.example.com`.

**Question:** Which address does the recipient see, which receives replies when clicking Reply, and which handles bounce returns?

**Hint:** `From` is the displayed identity; `Reply-To` directs replies; the envelope sender handles delivery failure returns. All three can differ.

### Exercise 4 — Pre-send marketing checks

A campaign built a list of 10,000 recipients. Afterward, 200 people unsubscribed. What happens if workers send from the stale snapshot?

**Hint:** Sends violate current consent state. Workers must check suppression/consent close to send time and process unsubscribes arriving while a campaign runs.

### Exercise 5 — Classifying errors

During transactional sending, SMTP returns `535 Authentication failed`. During marketing sending, SMTP returns temporary `451` due to rate limits. Would you handle both identically?

**Hint:** No. `535` requires checking credentials/configuration, where unconditional retries do not help; `451` usually calls for backoff, rate limiting, and queue throttling.

### Exercise 6 — Designing email tracking

Identify fields to record when tracking a transactional receipt and a marketing email. Include at minimum:

| Transactional | Marketing |
|---|---|
| `eventId`, `outboxId`, `attempt` | `campaignId`, `recipientId`, `attempt` |
| `channel=transactional` | `channel=marketing` |
| Time from event to SMTP acceptance | Queue time and processing rate |
| Transport error / provider event | Bounces, complaints, unsubscribes, suppressions |

**Hint:** Know which IDs are application-issued and which come from providers or SMTP relays. Never rely on `Message-ID` alone as a deduplication key.

## 14. Conclusion

In Spring Framework Mail, `JavaMailSender` is the sending mechanism, yet **senders for transactional email** and **senders for marketing email** must be designed around distinct business requirements. Transactional mail prioritizes latency, accuracy, and traceability; marketing prioritizes list controls, unsubscribes, send rates, and campaign deliverability.

You can start with one sender when the system is small and shared infrastructure meets requirements. When independent control is needed, configure **two `JavaMailSenderImpl` beans** with separate credentials/hosts and identities, route via `@Qualifier` or business gateways, and isolate queues, rate limits, and status tracking. When marketing requires deep automation and analytics, pairing Spring Mail for transactions with a dedicated email marketing platform can be the right fit.

The decisive factor is not bean count, but **matching message purpose, eligible recipients, sender identity, infrastructure capacity, and outcome tracking**.
