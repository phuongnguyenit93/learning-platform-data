# Separating Transactional and Marketing Sending Domains

In an application using **Spring Framework Mail**, order confirmation emails, verification codes, and security alerts have very different requirements from newsletters or promotional campaigns. Transactional emails must be accurate and arrive promptly; marketing emails may be sent in large batches and are strongly affected by unsubscribes, spam complaints, stale lists, and engagement rates.

If both message types share the same sending identity, SMTP account, queue, and provider limits, a marketing campaign flagged as spam or exceeding quota can delay OTPs or invoices. Therefore, **separating transactional and marketing sending domains** is a **deliverability** management technique to reduce the blast radius of incidents and allow appropriate policies for each mail type.

One organization pattern under brand `example.com`:

~~~text
Transactional:
  From: orders@notify.example.com
  DKIM signing domain: notify.example.com
  SMTP/API stream: transactional

Marketing:
  From: newsletter@offers.example.com
  DKIM signing domain: offers.example.com
  SMTP/API stream: marketing
~~~

Both addresses still represent the same brand, yet use **different subdomains** for easier distinction, authentication, and operations.

**Important limitation:** a separate subdomain does not by itself guarantee completely independent reputation. Mailbox providers may evaluate the parent domain, sending IP/pool, provider account, URLs, content, and receipt history. Domain separation is one component of a healthy mail-sending architecture, not a trick to guarantee inbox placement.

## 1. Classifying Emails Before Choosing Domains

### 1.1. Transactional Email

Typically triggered by a specific business event or action:

- email address verification, login OTP, or password reset;
- order confirmation, shipping status, payment, refund;
- invoices, receipts, and account change notifications;
- security alerts or updates to critical information.

Characteristics:

- recipients are tied to an authorized transaction/account;
- requires low latency and clear status tracking;
- content must match business data;
- may contain short-lived links/tokens;
- must design appropriate retries and duplicate prevention.

### 1.2. Marketing Email

Typically aimed at promotion, presenting content, or maintaining engagement:

- periodic newsletters;
- promotional offers;
- new product/feature announcements;
- webinar invitations or customer nurturing campaigns;
- abandoned-cart reminders and upsell suggestions in promotional contexts.

Characteristics:

- usually sent to many recipients by campaign/segment;
- requires consent and unsubscribe policies;
- easily impacted by complaints and invalid lists;
- requires rate limiting, warm-up, and frequency control;
- campaigns can be delayed or paused if deliverability signals worsen.

### 1.3. Hybrid Messages: Do Not Classify by Method Name Alone

A payment confirmation email containing a large discount banner is not necessarily a pure transactional email under provider classifications and applicable regulations.

~~~text
Subject: Payment succeeded A123

Order A123 has been paid.

Buy more today! 40% off everything!
~~~

Do not push promotional emails into the transactional stream by naming the method `sendReceipt(...)`. Separate transactional content from advertising whenever possible.

| Mail Type | Typically Appropriate Stream | Reason |
| --- | --- | --- |
| Login OTP | Transactional | Short-lived, essential |
| Order confirmation | Transactional | Business event |
| Invoice | Transactional | Receipt/transaction record |
| Security alert | Transactional | Account safety |
| Weekly newsletter | Marketing | Promotional/subscribed content |
| Discount code | Marketing | Promotion |
| Service renewal reminder | Needs evaluation | Depends on content and purpose |
| Receipt with heavy upsell | Needs evaluation | May be considered marketing |

This classification is an architectural guideline. Legal requirements and provider policies must be reviewed for the specific region and product type.

## 2. Why Does Sharing a Single Domain Create Risk?

Mailbox providers may evaluate:

- the domain in the `From` header;
- the DKIM signing domain;
- the envelope sender/Return-Path;
- the sending IP and IP pool;
- sending volume, sudden spikes, and sending history;
- hard bounces, spam complaints, and rejection counts;
- content, link/tracking domains, and engagement signals.

Example of a marketing blast sent to an old list:

~~~text
Marketing sends 100,000 emails
    |
    +-- many nonexistent addresses
    +-- spam complaints rise
    +-- ESP applies throttling/quota
    |
    v
Transactional sharing the same SMTP account/pool
    |
    v
OTPs and confirmation emails may also be delayed
~~~

If streams are well separated, the system can pause the campaign while preserving the capacity to send transactional emails.

**Do not confuse separating From with separating infrastructure.** Two From subdomains can still share the same ESP account and IP pool. There are also cases where account-level or root-domain policy suspensions affect both streams. Know the actual isolation boundaries your provider supports.

## 3. Designing the Domain Tree

Example:

~~~text
example.com
  |
  +-- www.example.com               Website
  +-- app.example.com               Application
  +-- notify.example.com            Transactional From
  +-- offers.example.com            Marketing From
  +-- bounce.notify.example.com     Transactional bounce/envelope
  +-- bounce.offers.example.com     Marketing bounce/envelope
~~~

| Role | Address or Domain |
| --- | --- |
| Order sender | `orders@notify.example.com` |
| Security sender | `security@notify.example.com` |
| Newsletter sender | `news@offers.example.com` |
| Promotions sender | `promotions@offers.example.com` |
| Transactional Reply-To | `support@example.com` |
| Marketing Reply-To | `marketing-support@example.com` |
| Transactional envelope/bounce | `bounce.notify.example.com` |
| Marketing envelope/bounce | `bounce.offers.example.com` |

Usually, **subdomains of the brand domain** are easier to recognize than completely unrelated domains. You do not necessarily need to buy two extra root domains.

### 3.1. Distinguishing Related Domain Names

A message may have:

~~~text
From: orders@notify.example.com
Reply-To: support@example.com
MAIL FROM: bounces@bounce.notify.example.com
DKIM-Signature: ... d=notify.example.com; s=txn1; ...
SMTP host: smtp.provider.example
~~~

These values are not one and the same:

- **From:** displays the sender and serves as the reference domain for DMARC.
- **Reply-To:** mailbox receiving user replies.
- **MAIL FROM / Return-Path:** envelope sender for bounces, tied to SPF.
- **DKIM d=:** signing domain for authentication.
- **SMTP host:** transport server, which may belong to the provider and differ from the From domain.

Separating From subdomains is meaningful only when **SPF/DKIM/DMARC and provider identities** are also configured properly.

### 3.2. Is an Independent Root Domain Needed?

An organization may use a different root domain for each distinct brand, yet should not switch to an unfamiliar domain merely to evade poor reputation. A new domain lacks history, can be harder to recognize, or may look suspicious to recipients.

Subdomain separation is a sensible starting point while preserving a single brand.

## 4. SPF, DKIM, and DMARC: The Foundation of Each Sending Domain

Splitting domains **does not authenticate emails automatically**. Each stream must be configured with the actual sending provider.

### 4.1. SPF and Envelope Identity

SPF checks whether an SMTP server is authorized to send by the domain used as the SMTP identity, typically the `MAIL FROM` domain (or HELO in applicable contexts).

Example:

~~~text
Visible From: orders@notify.example.com
Envelope MAIL FROM: bounce@bounce.notify.example.com
~~~

In this case, SPF is checked against `bounce.notify.example.com`, **not automatically** against `notify.example.com` in the From header.

**Illustrative** record, do not use verbatim:

~~~dns
bounce.notify.example.com. TXT "v=spf1 include:_spf.tx-provider.invalid -all"
~~~

`_spf.tx-provider.invalid` is an example name, not a real hostname. Use the DNS records supplied by your ESP. Some providers require CNAME/MX for custom Return-Path, while others manage this differently.

SPF must be configured on the right domain and must not have multiple competing `v=spf1` SPF records on the same name. SPF also has a limit on DNS-querying mechanisms; avoid blindly stuffing all providers into one record.

### 4.2. DKIM and the Signing Domain

DKIM signs emails with a private key, enabling receivers to look up the public key via DNS and verify the signed body/headers.

~~~text
Transactional:
  From: orders@notify.example.com
  DKIM d=notify.example.com
  Selector: txn1

Marketing:
  From: news@offers.example.com
  DKIM d=offers.example.com
  Selector: mkt1
~~~

The DKIM selector addresses in DNS look like:

~~~text
txn1._domainkey.notify.example.com
mkt1._domainkey.offers.example.com
~~~

The ESP may require a public key TXT record or a CNAME to their infrastructure. Do not invent records by guessing. You can separate selectors and keys to manage/rotate each stream independently.

A DKIM pass does not guarantee Inbox placement. It only proves signature authentication, not that recipients want the message.

### 4.3. DMARC Alignment with From

DMARC takes the domain in the **From header** as its reference point. For DMARC to pass, at least one of two paths is required:

1. SPF passes **and** the SPF identity is aligned with From.
2. DKIM passes **and** DKIM `d=` is aligned with From.

Example:

~~~text
From: orders@notify.example.com
DKIM d=notify.example.com           -> exact alignment
MAIL FROM: bounce.notify.example.com
~~~

DKIM `d=notify.example.com` matches the From domain exactly, so DMARC can pass if the signature is valid.

SPF domain `bounce.notify.example.com` is not identical to `notify.example.com`; strict SPF alignment fails, but relaxed alignment can succeed since they share the same organizational domain. Even though strict SPF is unaligned, an aligned DKIM pass is sufficient for DMARC to pass.

| From Domain | Authenticated Domain | Relaxed Alignment | Strict Alignment |
| --- | --- | --- | --- |
| `notify.example.com` | DKIM `d=notify.example.com` | Yes | Yes |
| `notify.example.com` | DKIM `d=example.com` | Yes in organizational domain example | No |
| `notify.example.com` | SPF `bounce.notify.example.com` | Yes in organizational domain example | No |
| `notify.example.com` | DKIM `d=another.invalid` | No | No |

Relaxed alignment is based on the organizational domain per DMARC/Public Suffix List rules, not simply checking whether one string contains another.

### 4.4. Dedicated DMARC for Subdomains

Example record during the observation phase:

~~~dns
_dmarc.notify.example.com. TXT "v=DMARC1; p=none; rua=mailto:dmarc-reports@example.com"
_dmarc.offers.example.com. TXT "v=DMARC1; p=none; rua=mailto:dmarc-reports@example.com"
~~~

`p=none` is for monitoring and collecting reports. After verifying legitimate sending sources, the organization can gradually move to `p=quarantine` or `p=reject` if appropriate.

DMARC has inheritance/subdomain policy rules, including the `sp=` tag on the organizational domain when applicable. If a subdomain has its own record, lookup uses that corresponding record per the standard. Do not assume a single root DMARC record controls every subdomain identically in all configurations.

If the aggregate report address `rua` is outside the related domain, an external report destination DNS verification mechanism may be required. Follow DMARC and ESP documentation.

**Do not disable DMARC policy just to fix sending errors** without investigating alignment. If legitimate sending sources are unconfigured, list and onboard them one by one.

## 5. Separating Identities and Sending Resources

Two From subdomains are a starting point; real isolation has multiple layers:

~~~mermaid
flowchart TD
    A["Application"] --> B{"Mail type"}
    B -->|"Transactional"| C["TX queue/outbox"]
    B -->|"Marketing"| D["MKT queue/campaign"]
    C --> E["TX sender credential/stream"]
    D --> F["MKT sender credential/stream"]
    E --> G["notify.example.com + TX DKIM"]
    F --> H["offers.example.com + MKT DKIM"]
    G --> I["Mail receivers"]
    H --> I
~~~

| Component | Transactional | Marketing |
| --- | --- | --- |
| From domain | `notify.example.com` | `offers.example.com` |
| DKIM domain | `notify.example.com` | `offers.example.com` |
| Bounce identity | `bounce.notify.example.com` | `bounce.offers.example.com` |
| ESP stream | TX if supported | Marketing if supported |
| Credentials/API keys | Dedicated or scoped | Dedicated or scoped |
| Queue | Latency-prioritized | Batch, scheduling, pacing |
| Quota/rate limiting | Reserve capacity for critical notifications | Cap campaigns |
| Suppression | By notification type and deliverability | Consent, opt-out, complaints |
| Observability | OTP/order latency, failures | Complaints, bounces, unsubscribes |

### 5.1. IP Pools and Account-Level Quotas

If both streams share a **shared IP pool**, IP reputation and quotas may still be coupled. Dedicated IPs offer another level of control, yet require warm-up and steady sending volume; they are not a mandatory upgrade for every application.

Some providers use feature names such as message streams, subaccounts, IP pools, or sending identities. Check the specific documentation:

- Does a stream have its own quota or still share an account quota?
- Does a spam suspension affect only the stream or the whole account?
- Is the suppression list per-stream or account-wide?
- Can webhooks/bounce events and credential permissions be separated?
- Are IPs shared or dedicated?

**Merely naming two beans in Java does not create two reputation pools.** They must be configured accordingly on the ESP.

### 5.2. Separating Queues to Prevent Head-of-Line Blocking

If using a single shared queue:

~~~text
Shared queue:
  50,000 newsletter jobs
  1 reset-password job
  1 order-confirmation job
~~~

An OTP may have to wait behind marketing jobs ahead of it. Consider:

~~~text
Transactional:
  business event -> outbox -> high-priority worker -> TX stream

Marketing:
  campaign segment -> queue -> paced worker -> MKT stream
~~~

Even with separate queues, if the SMTP provider enforces a shared quota, marketing can still consume capacity. Rate limiters should reserve sufficient budget for transactional mail, or truly separate accounts/streams when the provider supports it.

## 6. Configuring Multiple JavaMailSenders in Spring Boot

Spring Boot normally auto-configures a single `JavaMailSender` from `spring.mail.*`. When two transports/sender identities are needed, you can register **two `JavaMailSender` beans** and use `@Qualifier` to choose the right sender.

### 6.1. application.yml

~~~yaml
app:
  mail:
    transactional:
      host: ${TX_SMTP_HOST}
      port: ${TX_SMTP_PORT:587}
      username: ${TX_SMTP_USER}
      password: ${TX_SMTP_PASSWORD}
      from: orders@notify.example.com
      reply-to: support@example.com
    marketing:
      host: ${MKT_SMTP_HOST}
      port: ${MKT_SMTP_PORT:587}
      username: ${MKT_SMTP_USER}
      password: ${MKT_SMTP_PASSWORD}
      from: newsletter@offers.example.com
      reply-to: marketing-support@example.com
~~~

These are **custom** `app.mail.*` properties defined by the application, not default `spring.mail.*`. Credentials come from a secret store/environment variables, not hard-coded.

The two hosts may be identical if using the same ESP with separate credentials/streams per policy; **do not treat identical or differing hosts as sole proof of quota/reputation separation**.

### 6.2. Configuration Properties

Spring Boot 3 / Java 17+ example:

~~~java
package com.example.mail.config;

import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "app.mail")
public record MailStreamsProperties(
        SenderProperties transactional,
        SenderProperties marketing) {
}

record SenderProperties(
        String host,
        int port,
        String username,
        String password,
        String from,
        String replyTo) {
}
~~~

In production, validate host, port, From email, and required settings. If the provider uses OAuth2, use an appropriate adapter/token provider instead of putting an expiring access token into a static password field.

### 6.3. Two Sender Beans

~~~java
package com.example.mail.config;

import java.util.Properties;
import org.springframework.boot.context.properties.EnableConfigurationProperties;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.mail.javamail.JavaMailSender;
import org.springframework.mail.javamail.JavaMailSenderImpl;

@Configuration
@EnableConfigurationProperties(MailStreamsProperties.class)
public class MailSenderConfiguration {

    @Bean("transactionalMailSender")
    JavaMailSender transactional(MailStreamsProperties settings) {
        return createSender(settings.transactional());
    }

    @Bean("marketingMailSender")
    JavaMailSender marketing(MailStreamsProperties settings) {
        return createSender(settings.marketing());
    }

    private JavaMailSender createSender(SenderProperties config) {
        JavaMailSenderImpl sender = new JavaMailSenderImpl();
        sender.setHost(config.host());
        sender.setPort(config.port());
        sender.setUsername(config.username());
        sender.setPassword(config.password());
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

For SMTP ports requiring **implicit TLS** instead of STARTTLS, use the appropriate property and port, such as `mail.smtp.ssl.enable`; the example above is for a matching STARTTLS endpoint. Do not disable TLS or hostname verification to work around certificate errors.

Because there are two beans of the same type, injection without a qualifier can cause ambiguity. The application layer must select the stream explicitly.

### 6.4. Sending Stream Model

~~~java
public enum MailStream {
    TRANSACTIONAL,
    MARKETING
}

public record OutgoingMail(
        MailStream stream,
        String recipient,
        String subject,
        String plainText,
        String htmlText,
        String messageKey) {
}
~~~

Real requests should validate recipients, subject, body, data source, template, size limits, and message key. `MailStream` must not be taken directly from an external user-selectable parameter to bypass marketing policies.

### 6.5. Router Using the Right Sender and From

~~~java
import jakarta.mail.MessagingException;
import jakarta.mail.internet.MimeMessage;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.mail.javamail.JavaMailSender;
import org.springframework.mail.javamail.MimeMessageHelper;
import org.springframework.stereotype.Service;

@Service
public class RoutedMailService {
    private final JavaMailSender transactionalSender;
    private final JavaMailSender marketingSender;
    private final MailStreamsProperties config;

    public RoutedMailService(
            @Qualifier("transactionalMailSender")
            JavaMailSender transactionalSender,
            @Qualifier("marketingMailSender")
            JavaMailSender marketingSender,
            MailStreamsProperties config) {
        this.transactionalSender = transactionalSender;
        this.marketingSender = marketingSender;
        this.config = config;
    }

    public void send(OutgoingMail request) throws MessagingException {
        boolean marketing = request.stream() == MailStream.MARKETING;
        JavaMailSender sender = marketing
                ? marketingSender : transactionalSender;
        SenderProperties identity = marketing
                ? config.marketing() : config.transactional();

        MimeMessage message = sender.createMimeMessage();
        boolean hasHtml = request.htmlText() != null
                && !request.htmlText().isBlank();

        MimeMessageHelper helper =
                new MimeMessageHelper(message, hasHtml, "UTF-8");
        helper.setFrom(identity.from());
        helper.setTo(request.recipient());
        helper.setReplyTo(identity.replyTo());
        helper.setSubject(request.subject());

        if (hasHtml) {
            helper.setText(request.plainText(), request.htmlText());
        } else {
            helper.setText(request.plainText());
        }

        sender.send(message);
    }
}
~~~

This snippet illustrates **routing to the right SMTP sender and From**. It does not yet include:

- use-case email classification;
- validation/authorization;
- marketing consent and unsubscribe;
- suppression checks;
- attachments/inline resources;
- retries and outbox;
- `List-Unsubscribe` headers;
- end-to-end SPF/DKIM/DMARC testing.

These responsibilities should be organized into separate components rather than loading everything onto a simple router.

## 7. Classify at the Application Boundary, Not with an Arbitrary Boolean

An unclear API:

~~~java
mailService.send(to, subject, body, true);
~~~

`true` could accidentally mean "bypass opt-out." It is better to model by use case:

~~~java
public interface TransactionalNotificationService {
    void sendOrderConfirmation(OrderConfirmationData data);
    void sendSecurityAlert(SecurityAlertData data);
}

public interface MarketingCampaignService {
    void sendNewsletter(NewsletterJob job);
}
~~~

Transactional services require valid business events; marketing services verify consented lists and unsubscribe policies.

If using an outbox, store the stream alongside the logical job:

~~~text
MailJob(
  stream=TRANSACTIONAL,
  template=order-confirmation,
  recipient=user-88,
  messageKey=order-confirmed:evt-12:user-88
)
~~~

When a worker retries, the stream must remain stable; never automatically switch a marketing message to transactional just because the provider rejected it or the campaign exhausted its quota.

## 8. Per-Stream Unsubscribe and Preferences

**Marketing opt-out** differs from choices around receiving security/transactional emails.

Example:

~~~text
User preferences:
  marketingNewsletter = false
  productOffers       = false
  orderReceipts       = true
  securityAlerts      = true
~~~

If marketing unsubscribes are applied to the transactional SMTP stream as well, users can miss password reset emails or essential invoices. Conversely, sending marketing content through transactional to bypass opt-out breaks classification and can damage deliverability.

### 8.1. List-Unsubscribe and One-Click

For marketing emails within applicable scope, provide headers:

~~~text
List-Unsubscribe: <https://offers.example.com/unsubscribe/opaque-token>
List-Unsubscribe-Post: List-Unsubscribe=One-Click
~~~

RFC 2369 describes `List-Unsubscribe`; RFC 8058 describes one-click HTTPS unsubscribe using HTTP POST. The endpoint must genuinely process the unsubscribe, protect tokens, prevent abuse, and avoid side effects on GET since email security scanners may prefetch links.

Merely adding these two headers does not mean every mailbox client will display an unsubscribe button. Providers have their own authentication and endpoint functionality requirements. Marketing content should also provide a clearly visible way to manage preferences/unsubscribe.

### 8.2. Consent and Suppression States

Distinguish the reasons:

| Status | Meaning | Impact |
| --- | --- | --- |
| Marketing unsubscribed | Does not want promotional mail | Block relevant marketing |
| Hard bounce | Address definitively cannot receive mail | May block all streams under a sensible policy |
| Soft bounce | Temporary failure | Bounded retry/backoff |
| Spam complaint | Recipient reported spam | Block marketing; investigate acquisition source |
| Security notification enabled | Policy/agreement requires alerts | Do not auto-block solely from marketing opt-out |

The final policy must align with notification obligations, consent, and privacy. Transactional mail still needs to verify that the recipient belongs to a valid account/transaction and must not be sent unconditionally.

### 8.3. ESP Suppression Lists Can Be Account-Wide

Even if the application separates domains, the ESP may still share suppression lists across streams. Verify:

- whether hard-bounce suppression applies account-wide or per-stream;
- whether marketing opt-outs live in the ESP or the application preference center;
- which webhooks have authority to update recipient status;
- when restoring an address, which streams may resume sending.

Do not handle all suppression types with a single contextless Boolean `emailBlocked` flag.

## 9. Bounces, Complaints, and Delivery Events

Successful SMTP submission **does not mean the email reached the Inbox**. You may receive a bounce later or the mailbox provider may classify it as spam.

A state model:

~~~text
PENDING -> SUBMITTING -> SUBMITTED
                          |
                          +-- DELIVERED (provider event)
                          +-- BOUNCED (provider event)
                          +-- DEFERRED (provider event)
~~~

For marketing, there are also events:

~~~text
COMPLAINT
UNSUBSCRIBED
~~~

Typical handling needed:

- Hard bounce: update address status; avoid sending indiscriminately afterward.
- Soft bounce: back off and cap retry attempts.
- Complaint: block marketing and investigate consent origin.
- Unsubscribe: update preferences within the right scope.
- Delivered: record per provider semantics; do not infer the recipient read it.

### 9.1. Independent Webhooks per Stream

~~~text
TX provider webhook
    -> transactional delivery events

MKT provider webhook
    -> marketing delivery events

Both:
    -> normalized recipient delivery store
~~~

Webhooks must be authenticated using the mechanism published by the provider (e.g., signature and timestamp), handled idempotently, and checked for message/job ID mapping. Do not trust an unauthenticated HTTP event to alter suppression or account state.

## 10. Content, URLs, and Tracking Also Need Separation

Transactional emails may contain:

~~~text
https://app.example.com/orders/A123
~~~

Marketing may use:

~~~text
https://offers.example.com/campaign/summer
~~~

If the ESP uses click tracking, you can configure a separate branded tracking domain for marketing. Tracking domains and destination URLs can also act as spam signals, so you should:

- prevent open redirects;
- use HTTPS only;
- restrict redirect destinations;
- never embed credentials in links;
- never log password-reset tokens;
- carefully evaluate enabling click tracking in security alerts.

SPF/DKIM/DMARC authenticate the **sending identity**, not that links are harmless or content is wanted by recipients.

## 11. Warming Up New Subdomains and IP Pools

A new marketing subdomain lacks sending history. Immediately sending high volume can trigger deferrals or stricter spam filtering. You can start with opted-in, well-engaged recipients and gradually ramp up volume based on live signals.

High-level roadmap:

1. Verify DNS/domain with the ESP.
2. Send small test emails; inspect raw headers.
3. Start with a valid, engaged recipient segment.
4. Increase volume in controlled steps.
5. Monitor hard bounces, complaints, deferrals, and provider feedback.
6. Pause increases or throttle down when signals degrade.

There is no fixed warm-up schedule applicable to every provider. A new dedicated IP may need its own warm-up plan; ESP-managed shared IPs may take a different approach.

### 11.1. Do Not Rotate Subdomains to Evade Bad Reputation

If `offers.example.com` generates high complaints, switching to `deals1.example.com` and continuing to mail the same poor-quality list **does not fix the root cause**. Audit consent, clean the list, reduce frequency, and improve content. Receivers can correlate reputation at the root domain level and via many other signals.

## 12. DNS Migration Without Disrupting Existing Mail

Domain separation requires inventorying services currently using the root domain:

- employee email on Google Workspace, Microsoft 365, or other systems;
- current SPF/DKIM/DMARC records;
- MX records for incoming mail;
- domain aliases and sender identities;
- registered custom bounce domains or tracking domains;
- queued jobs and mail in transit.

### 12.1. Do Not Change the Root Domain's MX Just to Send via an ESP

MX primarily serves **receiving** mail. If employees receive mail at `example.com`, do not point the root MX to a transactional ESP just because you added `notify.example.com` as From.

Some ESPs require MX for a dedicated **bounce subdomain**; that is a separate setup. Only modify records on the exact hostnames specified by the provider.

### 12.2. Keep Old DKIM Keys Long Enough

When switching ESPs, do not immediately delete the public key selector used for previously sent messages. Messages may still be forwarded or have signatures checked after send time. Maintain a transition window and key rotation policy.

### 12.3. Monitor DMARC During Migration

Do not immediately switch everything to `p=reject` without knowing which systems send on behalf of the domain. Observe reports under `p=none`, verify each source, and tighten enforcement when ready.

## 13. Per-Stream Deliverability Metrics

Do not stop at a dashboard showing "total emails sent."

| Metric | Transactional | Marketing |
| --- | --- | --- |
| Submission attempts/success | Yes | Yes |
| SMTP/API latency | Priority | Yes |
| Queue depth/oldest age | Alert priority | Used to pace campaigns |
| Deferrals and 4xx responses | Yes | Yes |
| Hard/soft bounces | Yes | Yes |
| Complaints | Monitor | Critically important |
| Unsubscribes | Depends on type | Mandatory to observe |
| DKIM/DMARC failures | Yes | Yes |
| Provider quota usage | Yes | Yes |
| Delivery events | If provider supplies | If provider supplies |

Log example:

~~~text
event=mail_submission
stream=transactional
senderDomain=notify.example.com
mailType=ORDER_CONFIRMATION
jobId=job-752
result=SUBMITTED
latencyMs=420
~~~

Do not put recipient email, full subject, or individual message keys into high-cardinality metric labels. Logs should minimize personal data and never contain SMTP passwords, OAuth tokens, or unnecessary message bodies.

### 13.1. Business-Driven SLOs

Transactional needs to measure:

~~~text
OrderConfirmed event
    -> outbox persisted
    -> worker picked up
    -> SMTP/API submitted
    -> delivery event (if available)
~~~

OTP emails care about delivery time before token expiration. Marketing cares about compliant reach, complaints, unsubscribes, and list quality. Both streams should not share one "send success" metric and assume both are healthy.

### 13.2. Alerts Worth Watching

- Transactional queue age rises even while marketing sends normally.
- SMTP authentication failures on a sender identity.
- DMARC alignment failures after DNS changes.
- Marketing complaints or hard bounces spike.
- Provider quota risks exhaustion due to a campaign.
- Bounce webhooks fail, delaying suppression updates.
- ESP suspends the account at a scope broader than a single stream.

## 14. Testing Domain Separation

### 14.1. Unit Testing the Router

With two mocked senders, you can verify routing:

~~~java
@Test
void orderConfirmationUsesTransactionalSender() throws Exception {
    routedMailService.send(transactionalMail);

    verify(transactionalSender).send(any(MimeMessage.class));
    verifyNoInteractions(marketingSender);
}

@Test
void newsletterUsesMarketingSender() throws Exception {
    routedMailService.send(marketingMail);

    verify(marketingSender).send(any(MimeMessage.class));
    verifyNoInteractions(transactionalSender);
}
~~~

This illustrates the test idea. When mocking `JavaMailSender`, stub `createMimeMessage()` to return a valid MIME object and use fixtures matching the router implementation.

Additional test cases:

- From/Reply-To per stream;
- transactional never picks up marketing SMTP credentials by mistake;
- marketing blocked without consent;
- unsubscribe applies only to the right notification type;
- sender cannot be selected by arbitrary client input;
- job retries preserve the stream;
- errors on one provider are attributed to the right stream/job.

### 14.2. SMTP and DNS Integration Testing

Use an authorized test mailbox to verify:

1. Transactional From is actually `notify.example.com`.
2. Marketing From is actually `offers.example.com`.
3. DKIM `d=` matches each stream.
4. SPF passes on the appropriate envelope domain.
5. DMARC passes with proper alignment.
6. Return-Path/bounce mapping is correct.
7. Marketing unsubscribe works.
8. Provider events map to the right job/stream.
9. Employee email MX was not altered by mistake.

A test mailbox can provide `Authentication-Results` and raw MIME. However, Java unit tests or SMTP mocks cannot prove real inbox placement; different receivers evaluate reputation differently.

### 14.3. Operational Testing

- Pause the marketing worker: transactional still gets processed.
- Marketing hits rate limits: does not pull transactional into backlog by design.
- Provider account blocked: confirm account-level incident plan.
- Duplicate webhook delivery: handler is idempotent.
- A marketing hard bounce: updates suppression per policy without blindly altering all preference types.
- Transport retry after timeout: preserves UNKNOWN status when unsure whether the provider accepted the message.

## 15. Migration Plan from One Domain to Two

Assume the starting state:

~~~text
From: no-reply@example.com
SMTP account: shared
Queue: one queue for all mail
Templates: mixed transactional and marketing
~~~

A transition process can consist of phases:

### Phase A — Inventory and Classification

List all email types, templates, event sources, From, reply-to, domains, provider credentials, quotas, queues, and webhooks. Split emails with mixed content. Identify recipient permissions and marketing opt-outs.

### Phase B — Configure New Identities

Design:

~~~text
TX:  notify.example.com  + transactional provider identity
MKT: offers.example.com  + marketing provider identity
~~~

Set up DKIM, SPF for the right envelope domains, DMARC, and bounce domains. Configure streams/subaccounts/quotas on the ESP where needed.

### Phase C — Implement Routing

Create two sender beans or adapters; include the stream in outbox/jobs; enforce consent/opt-out for marketing; separate queues and rate limiters.

### Phase D — Canary and Warm-Up

Run controlled tests using owned accounts/mailboxes; verify Authentication-Results, webhooks, logging, and domain alignment. Ramp transactional traffic first under a safe plan, then marketing to eligible segments.

### Phase E — Observe, Expand, Retire Legacy

Monitor latency, complaints, bounces, DMARC reports, deferrals, and quotas. Keep old records/credentials while legitimate traffic remains; retire on schedule after migration completes.

**Avoid changing everything at once**: changing provider, SMTP host, domain, DKIM, queue, and templates on the same day makes diagnosing any drop in deliverability very difficult.

## 16. Common Mistakes

| Mistake | Consequence | Remedy |
| --- | --- | --- |
| Changing only From while sharing all senders/queues | Quota/backlog risks remain shared | Separate infrastructure appropriately |
| Not configuring DKIM for the new subdomain | DMARC may fail | Verify `d=` and DNS selectors |
| SPF passes but misaligned | DMARC may fail | Check envelope domain and From |
| Using Reply-To to infer DMARC | Wrong mechanism | DMARC relies on the From header |
| Publishing multiple SPF records on one hostname | SPF permerror | Use a single valid SPF policy |
| Deleting old DKIM selectors too soon | Mail in transit may fail DKIM | Retain keys during transition |
| Sending marketing via transactional to bypass unsubscribe | Consent/policy violation, harms TX reputation | Classify by content and use case |
| Marketing unsubscribe blocking OTPs too | Loss of essential notifications | Scope preferences |
| Not tracking bounces/suppression per stream | Cannot pinpoint incident source | Separate event mapping and dashboards |
| Letting campaigns exhaust shared quota | OTPs delayed/rejected | Reserve capacity/separate stream or account |
| Blasting high volume on a new domain | Deferrals and spam filtering | Warm up and monitor |
| Assuming every subdomain has independent reputation | False expectations | Monitor root domain/IP/provider as well |
| Using a new domain to keep spamming an old list | Underlying issue unsolved | Clean list and enforce consent |
| Treating SMTP `250` as Inbox delivery | Misreports delivery | Track delivery events separately |
| Failing over and blindly retrying when outcome is unknown | Recipients may receive duplicates | Idempotency/UNKNOWN policy |

## 17. End-to-End Scenario: Online Store

The application needs to send order confirmations and newsletters:

~~~text
Order A123 is confirmed
    |
    v
Transactional outbox
    |
    v
TX MailWorker
    |
    v
orders@notify.example.com
    |
    v
SMTP/API transactional stream

Weekend product campaign
    |
    v
Eligible marketing segment
    |
    v
MKT MailWorker (pacing + unsubscribe)
    |
    v
newsletter@offers.example.com
    |
    v
SMTP/API marketing stream
~~~

When a marketing campaign generates many hard bounces:

1. Marketing monitoring detects rising bounce/complaint counts.
2. The campaign is throttled down or paused.
3. The system updates the suppression list and audits consent sources.
4. The transactional queue and sender continue operating on reserved capacity.
5. If the ESP enforces account-wide quotas or suspensions, operators still must intervene because that boundary is not necessarily isolated.

The desired outcome is the ability to **isolate, detect, and respond**, not a promise that every email reaches the Inbox.

## 18. Pre-Production Checklist

### Classification and Sending Authorization

- [ ] Every email type has an explicit stream.
- [ ] Transactional content does not arbitrarily mix in advertisements.
- [ ] Marketing has proper consent, unsubscribe, and preference policies.
- [ ] Callers cannot arbitrarily switch marketing to transactional.

### Domains and Authentication

- [ ] Separate From subdomains for the two streams.
- [ ] DKIM signs with the right signing domains.
- [ ] SPF records match envelope/bounce identities and ESP.
- [ ] DMARC alignment passes with appropriate policy/reporting.
- [ ] Root domain MX and existing employee inboxes are unaffected.
- [ ] Reply-To, bounce, and tracking hostnames are clearly defined.

### Infrastructure

- [ ] Credentials and streams configured properly per provider.
- [ ] Queues/workers/limiters prevent marketing from clogging transactional.
- [ ] Clear understanding of the scope at which quotas, IP pools, and suppression apply.
- [ ] Retries carry a message key and do not blindly resend after timeouts.
- [ ] Webhooks are authenticated and processed idempotently.

### Operations

- [ ] Dashboards distinguish TX/MKT.
- [ ] Alerts exist for latency, bounces, complaints, deferrals, and authentication failures.
- [ ] Warm-up, migration, and rollback plans are ready.
- [ ] Never log SMTP passwords, API keys, or unnecessary personal content.
- [ ] Runbook exists to pause campaigns without halting critical notifications.

## 19. Things to Remember

- **Separate transactional and marketing emails by purpose before separating domains.**
- You can use `notify.example.com` and `offers.example.com` under the same brand domain.
- From, DKIM, SPF envelope identity, Return-Path, and SMTP host are distinct concepts.
- Each stream requires proper DNS authentication and DMARC alignment.
- Separating From subdomains **does not** guarantee isolated IP reputation, quotas, or account-level restrictions.
- Marketing requires consent/unsubscribe, list hygiene, pacing, and complaint handling; transactional requires low latency and accuracy.
- Separate queues, workers, credentials, streams, and monitoring to the extent supported by the system.
- New subdomains/IPs may need warm-up; do not spike volume before observing signals.
- Good authentication does not automatically mean good deliverability, nor does it guarantee every email reaches the Inbox.

In Spring Framework Mail, separating transactional and marketing sending domains is **an architectural and operational decision**, not merely changing the `setFrom(...)` string. Properly classifying use cases, authenticating subdomains, isolating sending resources, and tracking results separately reduces the chance of a marketing campaign disrupting critical emails while enabling more responsible marketing operations.

### References

- **Spring Framework Reference — Email:** `JavaMailSender`, `MimeMessageHelper`.
- **Spring Boot Reference — Sending Email:** mail auto-configuration and properties.
- **RFC 5321 — Simple Mail Transfer Protocol:** `MAIL FROM`, `RCPT TO`, and SMTP submission.
- **RFC 5322 — Internet Message Format:** `From`, `Reply-To`, and message headers.
- **RFC 7208 — Sender Policy Framework (SPF):** SMTP domain checks and DNS lookup limits.
- **RFC 6376 — DomainKeys Identified Mail (DKIM):** domain/selector signing and verification.
- **RFC 7489 — Domain-based Message Authentication, Reporting, and Conformance (DMARC):** identifier alignment, policy, reporting.
- **RFC 2369 — URLs as Meta-Syntax for Core Mail List Commands:** `List-Unsubscribe`.
- **RFC 8058 — Signaling One-Click Functionality for List Email Headers:** one-click unsubscribe.
- **Documentation for your current ESP/mailbox provider:** sending domain verification, quotas, bounce handling, suppression, and deliverability guidance.
