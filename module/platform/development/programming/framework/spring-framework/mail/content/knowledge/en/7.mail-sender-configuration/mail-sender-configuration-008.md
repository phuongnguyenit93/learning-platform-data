# Configuring Multiple Senders for Multiple Purposes

## 1. Why does an application need multiple mail senders?

A Spring application can send many kinds of email: account verification, password resets, order confirmations, invoices, operational alerts, newsletters, or marketing campaigns. These message categories often differ in urgency, provider, SMTP account, sender address, quotas, retry policies, and tracking requirements.

If every email uses a single SMTP configuration, a high-volume mailing burst can exhaust the quota or queue needed by transactional emails. An authentication, rate-limit, or sender-reputation issue in one category can also impact the other.

In **Spring Framework Mail**, each **JavaMailSenderImpl** can hold its own SMTP configuration and be registered as a Spring bean. Services depend on **JavaMailSender** by name/qualifier to use the right account and sending path for each purpose.

Example of two common email categories:

| Purpose | Transactional sender | Campaign sender |
|---|---|---|
| Message types | OTP, password reset, orders, invoices | Newsletters, promotions, marketing updates |
| Requirements | Low latency, minimal lost notifications | Rate control, subscriber preferences |
| Example From address | account@example.com | news@example.com |
| Example SMTP host | smtp-transactional.example.com | smtp-campaign.example.com |
| Retries | Careful with tokens, expiration, duplicate risk | Respect send limits and suppression lists |
| Monitoring | Transaction status, auth errors, bounces | Bounces, complaints, unsubscribes, list quality |

The two hostnames above are purely illustrative. A real system might use two accounts on the same provider, two different providers, or multiple internal SMTP relays. Creating multiple `JavaMailSender` beans does not require multiple physical servers.

### Distinguishing multiple senders from multiple From addresses

Changing the **From** field in a message does not mean changing the SMTP server, authentication account, or transport policy. One sender may be permitted to use several verified From addresses, yet all messages still travel through that sender's SMTP configuration.

Conversely, two `JavaMailSender` beans can share the same From domain while using different SMTP accounts or delivery services, if allowed by the provider. **From is an email header; a sender is the application-side mail-sending configuration and behavior.**

## 2. Multi-sender architecture in Spring

~~~text
                  Application Business Logic
                          |
              +-----------+-----------+
              |                       |
     Account/Order Service      Newsletter Service
              |                       |
              v                       v
    TransactionalMailService   CampaignMailService
              |                       |
              | @Qualifier            | @Qualifier
              v                       v
    transactionalMailSender     campaignMailSender
              |                       |
              v                       v
       JavaMailSenderImpl        JavaMailSenderImpl
              |                       |
         SMTP account A           SMTP account B
              |                       |
              v                       v
           Relay A                 Relay B
              |                       |
              +-----------+-----------+
                          |
                  Receiving Mail Server
~~~

Spring Dependency Injection manages two beans with distinct names that share the **JavaMailSender** type. Services declare explicitly which sender they use. Routing by **notification type** or **business purpose** should happen in an orchestration layer rather than letting individual controllers build SMTP configurations.

Even if two senders share the same host, they can still differ in username, password, TLS, timeouts, proxy/network routing, or quotas. However, **two beans inside the same JVM do not automatically guarantee absolute infrastructure isolation**: connecting out to the same ESP can still share account, IP, domain, or reputation limits under the provider's policies.

## 3. Organizing configuration in application.yml

Spring Boot supports configuring a single standard sender via the **spring.mail** namespace. When an application needs multiple explicitly managed senders, you can define a custom application namespace such as **app.mail**:

~~~yaml
app:
  mail:
    transactional:
      host: smtp-transactional.example.com
      port: 587
      username: transactional@example.com
      password: ${TRANSACTIONAL_SMTP_PASSWORD}
      from: account@example.com
      starttls: true
      timeout-millis: 5000
    campaign:
      host: smtp-campaign.example.com
      port: 587
      username: campaign@example.com
      password: ${CAMPAIGN_SMTP_PASSWORD}
      from: news@example.com
      starttls: true
      timeout-millis: 10000
~~~

In this example:

- Each group has its own **host/port**, SMTP account, and **From** address.
- **starttls** indicates whether TLS upgrade is required for port 587 submission.
- **timeout-millis** is the timeout value applied to socket/mail transport settings; this is a custom application property.
- Passwords load from environment variables, avoiding real secrets in committed files.
- The **app.mail** namespace is application-chosen, **not** a property group Spring Boot automatically recognizes to create two `JavaMailSender` beans.

For an SMTP server using implicit TLS on port 465, transport settings must differ: use **mail.smtp.ssl.enable=true** and matching certificate checks. Never copy a port 587 STARTTLS example blindly to every service.

### Account and From address must be compatible

Setting **from: news@example.com** does not guarantee the campaign account is permitted to send from that address. Many providers require verifying the sending domain or address alongside proper SPF/DKIM/DMARC records. Those belong to mail system and DNS policies outside Spring bean configuration.

## 4. Mapping configuration to typed properties objects

In Spring Boot 3 on Java 21, a **record** can be used with **@ConfigurationProperties** to bind configuration:

**MailAccounts.java**

~~~java
package com.example.mail;

import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "app.mail")
public record MailAccounts(
        Account transactional,
        Account campaign
) {
    public record Account(
            String host,
            int port,
            String username,
            String password,
            String from,
            boolean starttls,
            int timeoutMillis
    ) {
    }
}
~~~

The record captures both **transactional** and **campaign** sender configurations from YAML. Spring Boot supports constructor binding for records when registered as configuration properties, such as with **@EnableConfigurationProperties(MailAccounts.class)**.

Although sensitive values like password are bound into the object, still protect them via secret management, config access controls, and logging hygiene. Never log the full configuration record, because **a record's `toString()`** would include the password field.

For production, add validation to catch blank hosts, invalid ports, missing passwords, or invalid timeouts at startup. You can use **jakarta.validation** with Spring Boot's validation support when the dependency is present. The basic example below focuses on declaring the senders.

## 5. Creating two JavaMailSender beans

A configuration class creates two distinct implementations of the **JavaMailSender** interface. Both reuse an internal factory method to avoid duplicating transport setup logic.

**MailSenderConfiguration.java**

~~~java
package com.example.mail;

import java.nio.charset.StandardCharsets;
import java.util.Properties;

import org.springframework.boot.context.properties.EnableConfigurationProperties;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.mail.javamail.JavaMailSender;
import org.springframework.mail.javamail.JavaMailSenderImpl;

@Configuration
@EnableConfigurationProperties(MailAccounts.class)
public class MailSenderConfiguration {

    @Bean("transactionalMailSender")
    public JavaMailSender transactionalMailSender(MailAccounts accounts) {
        return createSender(accounts.transactional());
    }

    @Bean("campaignMailSender")
    public JavaMailSender campaignMailSender(MailAccounts accounts) {
        return createSender(accounts.campaign());
    }

    private JavaMailSender createSender(MailAccounts.Account account) {
        JavaMailSenderImpl sender = new JavaMailSenderImpl();
        sender.setHost(account.host());
        sender.setPort(account.port());
        sender.setUsername(account.username());
        sender.setPassword(account.password());
        sender.setDefaultEncoding(StandardCharsets.UTF_8.name());

        Properties properties = sender.getJavaMailProperties();
        properties.setProperty("mail.transport.protocol", "smtp");
        properties.setProperty("mail.smtp.auth", "true");
        properties.setProperty(
                "mail.smtp.starttls.enable",
                Boolean.toString(account.starttls())
        );
        properties.setProperty(
                "mail.smtp.starttls.required",
                Boolean.toString(account.starttls())
        );

        String timeout = Integer.toString(account.timeoutMillis());
        properties.setProperty("mail.smtp.connectiontimeout", timeout);
        properties.setProperty("mail.smtp.timeout", timeout);
        properties.setProperty("mail.smtp.writetimeout", timeout);

        return sender;
    }
}
~~~

**Step-by-step explanation:**

1. **@EnableConfigurationProperties** registers `MailAccounts` so Spring Boot binds from **app.mail**.
2. Two **@Bean** methods produce two beans of type `JavaMailSender` with distinct names: **transactionalMailSender** and **campaignMailSender**.
3. The **createSender(...)** factory sets hostname, port, username, password, charset, and JavaMail properties for each account.
4. **mail.smtp.auth** enables Jakarta Mail's SMTP AUTH; **mail.smtp.starttls.enable** and **mail.smtp.starttls.required** control STARTTLS enforcement.
5. Timeouts cap connection/read/write durations, preventing indefinite hangs during server issues.

This example models SMTP submission requiring AUTH and optional STARTTLS. For services without AUTH, using another auth mechanism, or using a different TLS port, configure them separately rather than forcing the same factory. Never set **starttls=false** and accidentally transmit passwords over an unencrypted connection; TLS choices must follow the SMTP server's security policy.

### Note on Spring Boot auto-configuration

**spring-boot-starter-mail** brings in the mail dependencies and auto-configuration support. Spring Boot can provide a default mail sender when config conditions match and no application-defined bean takes its place.

Once you manually define mail sender beans as above, Boot's mail sender auto-configuration can **back off**, so do not assume **spring.mail.host**, **spring.mail.username**, or other **spring.mail.*** properties automatically apply to both beans. Values in the example are read from **app.mail** and applied explicitly to each `JavaMailSenderImpl`.

The example omits **@Primary** so every consumer of `JavaMailSender` must state which bean it wants. If a component injects `JavaMailSender` by type without a qualifier, Spring can fail with **NoUniqueBeanDefinitionException** because multiple candidates exist.

## 6. Selecting a sender with @Qualifier

With two beans of the same type, a service can request the appropriate sender for its role using **@Qualifier**.

### Transactional email service

**TransactionalMailService.java**

~~~java
package com.example.mail;

import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.mail.SimpleMailMessage;
import org.springframework.mail.javamail.JavaMailSender;
import org.springframework.stereotype.Service;

@Service
public class TransactionalMailService {

    private final JavaMailSender sender;
    private final String from;

    public TransactionalMailService(
            @Qualifier("transactionalMailSender") JavaMailSender sender,
            MailAccounts accounts
    ) {
        this.sender = sender;
        this.from = accounts.transactional().from();
    }

    public void sendOrderConfirmation(String recipient, String orderCode) {
        SimpleMailMessage message = new SimpleMailMessage();
        message.setFrom(from);
        message.setTo(recipient);
        message.setSubject("Order confirmation " + orderCode);
        message.setText("Order " + orderCode + " has been recorded.");
        sender.send(message);
    }
}
~~~

**@Qualifier("transactionalMailSender")** ensures Spring injects the transactional sender. This reduces the risk of accidentally using the campaign account for critical flows like order confirmations or account recovery.

### Campaign newsletter service

**CampaignMailService.java**

~~~java
package com.example.mail;

import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.mail.SimpleMailMessage;
import org.springframework.mail.javamail.JavaMailSender;
import org.springframework.stereotype.Service;

@Service
public class CampaignMailService {

    private final JavaMailSender sender;
    private final String from;

    public CampaignMailService(
            @Qualifier("campaignMailSender") JavaMailSender sender,
            MailAccounts accounts
    ) {
        this.sender = sender;
        this.from = accounts.campaign().from();
    }

    public void sendNewsletter(String recipient, String articleUrl) {
        SimpleMailMessage message = new SimpleMailMessage();
        message.setFrom(from);
        message.setTo(recipient);
        message.setSubject("Latest Newsletter");
        message.setText("Read the newsletter at " + articleUrl);
        sender.send(message);
    }
}
~~~

The examples use plain text to keep focus on configuration and sender selection. When HTML, multipart, or attachments are needed, services can call **sender.createMimeMessage()**, use **MimeMessageHelper**, and call **sender.send(mimeMessage)**. Qualifier-based sender selection stays identical.

For real campaigns, the sending service must check recipient consent, suppression/unsubscribe lists, and relevant quotas/policies. **JavaMailSender** only handles the sending interface, not consent or unsubscribe management.

## 7. Dynamic routing by sending purpose

A small app can let each service inject a fixed sender. If a system routes many notification types through a central dispatcher, you can create a **MailRouter** keyed by an explicit purpose enum.

~~~java
package com.example.mail;

public enum MailPurpose {
    TRANSACTIONAL,
    CAMPAIGN
}
~~~

~~~java
package com.example.mail;

import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.mail.javamail.JavaMailSender;
import org.springframework.stereotype.Component;

@Component
public class MailSenderRouter {

    private final JavaMailSender transactional;
    private final JavaMailSender campaign;

    public MailSenderRouter(
            @Qualifier("transactionalMailSender") JavaMailSender transactional,
            @Qualifier("campaignMailSender") JavaMailSender campaign
    ) {
        this.transactional = transactional;
        this.campaign = campaign;
    }

    public JavaMailSender select(MailPurpose purpose) {
        return switch (purpose) {
            case TRANSACTIONAL -> transactional;
            case CAMPAIGN -> campaign;
        };
    }
}
~~~

For example, a dispatcher can call **router.select(MailPurpose.TRANSACTIONAL)** to get the matching sender and compose a message:

~~~java
JavaMailSender sender = router.select(MailPurpose.TRANSACTIONAL);
SimpleMailMessage message = new SimpleMailMessage();
message.setFrom("account@example.com");
message.setTo("customer@example.net");
message.setSubject("Order confirmation");
message.setText("Your order has been recorded.");
sender.send(message);
~~~

The snippet uses illustrative addresses to demonstrate selecting a sender. In real designs, pair **From** with the route configuration rather than letting callers pass arbitrary From values.

### Why is an enum better than arbitrary strings?

If a controller accepts raw strings like **"smtpHost"** or **"senderName"** from an HTTP request to pick a bean, callers could accidentally or maliciously pick the wrong infrastructure. A **MailPurpose** is an application-controlled set of purposes, constraining valid choices and keeping business logic clear.

There is no need to call **ApplicationContext.getBean(...)** on every send. Constructor injection of specific senders checks dependencies early and makes testing straightforward.

## 8. @Primary and common injection errors

When multiple beans of type `JavaMailSender` exist:

~~~text
Bean type: JavaMailSender
  ├── transactionalMailSender
  └── campaignMailSender
~~~

The following constructor causes ambiguity:

~~~java
public NotificationService(JavaMailSender mailSender) {
    this.mailSender = mailSender;
}
~~~

Without further guidance, Spring cannot pick a unique bean and startup can fail with **NoUniqueBeanDefinitionException**.

Three common ways to handle it:

| Approach | When appropriate | Notes |
|---|---|---|
| **@Qualifier** at injection point | Each service has a clear sending purpose | Readable and explicit choice. |
| **@Primary** on one bean | Most injection points need one default sender | Watch out for tasks accidentally using the default. |
| **MailSenderRouter** | A central dispatcher chooses the sender by event type | Keeps routing rules centralized and extensible. |

Example using `@Primary`:

~~~java
@Bean("transactionalMailSender")
@Primary
JavaMailSender transactionalMailSender(MailAccounts accounts) {
    return createSender(accounts.transactional());
}
~~~

With this, a dependency declaring plain `JavaMailSender` receives the preferred sender per Spring's bean resolution rules. However, **@Primary does not replace purpose-based routing**. In apps with both transactional and campaign emails, `@Qualifier` or a router is usually clearer.

## 9. Multiple accounts on one SMTP provider vs. multiple providers

A multi-sender architecture does not necessarily mean using two different email service brands.

**Case A — Same SMTP host, different accounts**

~~~yaml
app:
  mail:
    transactional:
      host: smtp.mail-provider.example
      username: account-transactional@example.com
      # ...
    campaign:
      host: smtp.mail-provider.example
      username: account-campaign@example.com
      # ...
~~~

This can separate permissions or per-account quotas **if** supported by the provider. However, IP limits, domain limits, sending pools, or reputation may still be shared.

**Case B — Two different SMTP providers**

~~~text
Transactional -> Provider A -> Internet mail
Campaign      -> Provider B -> Internet mail
~~~

This lets each mail category have independent operational policies, though it requires managing two sets of credentials, DNS, DKIM/SPF records, billing, webhooks, and status dashboards. Error behaviors across providers may also differ.

**Case C — Multiple senders for failover**

~~~text
Transactional sender
     |
     +--> Primary SMTP
     |
     +--> Secondary SMTP (on classified failures)
~~~

If implementing failover, do not simply catch any exception and immediately resend through the secondary provider. Some timeouts happen **after the primary provider already accepted the email** while the client missed the reply; resending via another provider can cause duplicates. The system must record attempts, **UNKNOWN** outcomes, reconciliation policies, and conditional failover rules.

## 10. Operational policies by purpose

Configuring multiple senders delivers far more value when each email category has its own policy.

| Policy | Transactional email | Campaign / newsletter |
|---|---|---|
| **Sending speed** | Prioritize low latency within safe bounds | Rate-limit and batch per provider capacity |
| **Retries** | Only for eligible errors; watch token expiration | Bounded retries; respect throttling and unsubscribes |
| **Queue** | Dedicated queue for critical notifications | Separate queue for bulk volume |
| **Sender identity** | Verified domain/address for transactions | Verified From for subscription programs |
| **Monitoring** | Confirmation mail, bounces, timeouts, unknown states | Deliveries, bounces, complaints, unsubscribes |
| **Incident response** | Early alerting, controlled fallback | Pause campaigns to protect quotas and reputation |
| **Data permissions** | Send only to the rightful account owner | Send only to opted-in, active subscribers |

### A sender is not a queue

**JavaMailSender.send(...)** normally blocks the caller synchronously. Two `JavaMailSender` beans **do not automatically create two queues**, priority tiers, retries, or background workers.

To manage high volumes, the application must design or integrate:

- Queues or a **transactional outbox** to persist send intent.
- Dedicated workers/pools per email category.
- Rate and concurrency limits per account/provider.
- Bounded retries with backoff, distinguishing transient from permanent failures.
- Tracking message IDs, bounces/complaints, and webhooks if supported by the provider.

A simple design:

~~~text
Business event
     |
     v
Notification dispatcher
     |
     +----------------------------+
     |                            |
 Transactional queue          Campaign queue
     |                            |
 Transactional worker         Campaign worker
     |                            |
 transactionalMailSender      campaignMailSender
     |                            |
 SMTP provider A              SMTP provider B
~~~

Queues ensure different purposes do not compete on the same worker thread, though actual resource isolation also depends on worker pools, connection limits, providers, and deployment topology.

## 11. Retries, failover, and duplicate-send risk

Suppose a worker invokes the transactional sender; the SMTP server receives all data, yet the connection drops before the application receives the success reply:

~~~text
Spring app                         SMTP server
    | -------- message DATA -------> |
    |                                | Accepts and queues
    | <----- ACK lost ----------X    |
    |
    +-- App sees a timeout
        without knowing whether the server accepted the email.
~~~

If the router immediately fails over to a backup sender, the email may be sent **twice** through two providers. This is inherent to distributed communication, not unique to Spring.

When orchestrating retries/failover:

1. Record a **notification ID** for the send intent and an **attempt ID** for each try.
2. Separate permanent configuration/auth errors from transient network/throttling errors.
3. Record an **UNKNOWN** state whenever server acceptance cannot be confirmed.
4. Reconcile status with the provider using message IDs or logs where possible.
5. Fail over only according to defined policy; never promise exactly-once delivery merely by swapping SMTP servers.

Some ESPs offer idempotency APIs or request lookup endpoints, whereas **plain SMTP and JavaMailSender** do not offer a uniform idempotency contract across providers.

### What does a transactional outbox solve?

When an email results from a database transaction (e.g., creating an order), you can persist **the order + an outbox record** in the same transaction and let a worker send afterward once committed. This prevents losing send intent if an error occurs between database commit and SMTP submission.

However, an outbox does not automatically prevent duplicates: a worker can send the email and crash before marking the outbox row complete. You still need state tracking, attempts, retry rules, and verification against the sending infrastructure.

## 12. Securing multi-sender configurations

As the number of senders grows, so do credentials and access policies. Never place all SMTP details in source code or write them to logs.

**Key precautions:**

- Load passwords/API tokens from environment variables or a role-restricted secret manager.
- Never log the entire **MailAccounts** object, since the record contains passwords.
- Use TLS appropriate for the server, verify certificates, and avoid accidental connection downgrades.
- Separate sending permissions between transactional and campaign accounts where provider supports it.
- Permit only **From** addresses authorized for verified accounts/domains.
- Route account verification, OTP, and password resets through the proper transactional channel; never mix sensitive flows into campaign senders.
- Never log OTPs, password-reset links, tokens, or private recipient details in standard logs.
- Protect dashboards, webhooks, and SMTP admin tables; delivery/bounce events can also carry user data.

### SPF, DKIM, and DMARC with multiple providers

When using multiple sending systems for one domain, configure and verify:

| Mechanism | What to watch |
|---|---|
| **SPF** | Authorize sending from the right IP/system sources per SMTP identity; avoid missing sources or exceeding SPF lookup limits. |
| **DKIM** | Each provider may require its own selector/signing key DNS record and valid signing configuration. |
| **DMARC** | Ensure authentication passes and **alignment** matches the From header domain per domain policy. |
| **Bounce / return-path** | Envelope sender addresses may be managed separately per provider, distinct from the From header. |
| **Reputation** | Separate senders do not guarantee isolated reputation if sources share IPs/domains or are linked by receiver policy. |

These belong to email infrastructure and DNS configuration. **spring-boot-starter-mail** does not create these records automatically.

## 13. Per-sender status and observability

When two senders serve distinct purposes, metrics should carry a purpose label (**transactional/campaign**) rather than lumping every email into a single aggregate chart.

Useful signals include:

| Signal | Purpose |
|---|---|
| **Emails requested** | Measures sending demand by purpose. |
| **SMTP accepts / rejects** | Distinguishes provider responses at the submission step. |
| **`send()` duration** | Detects network issues or slow SMTP servers. |
| **Authentication errors** | Catches revoked/expired credentials or misconfiguration. |
| **Connection timeouts** | Detects SMTP host or network outages. |
| **Queue depth and age** | Surfaces backlogs affecting delivery timeliness. |
| **Bounce, complaint, delivered events** | Tracks post-submission outcomes if provided by ESP. |
| **Retries and UNKNOWN attempts** | Measures duplicate-send risk or indeterminate failures. |

Logs should include **notification ID**, **attempt ID**, **sender name/purpose**, **timestamp**, **error code**, and minimal diagnostics. Recipient addresses should be minimized or partially masked per data-protection policy. **Never log secrets, tokens, MIME bodies, or attachments.**

Seeing **sender.send(...)** return without throwing does not prove the message landed in the recipient's inbox. For downstream status, use ESP webhooks or logs and understand each provider's event semantics.

## 14. Testing sender selection flows

With multiple beans of the same type, two easy mistakes are **injecting the wrong bean** or **routing to the wrong purpose**. You can verify how a service uses its sender with a simple unit test using a mock.

Example testing `TransactionalMailService`:

~~~java
package com.example.mail;

import org.junit.jupiter.api.Test;
import org.springframework.mail.SimpleMailMessage;
import org.springframework.mail.javamail.JavaMailSender;
import org.mockito.ArgumentCaptor;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.mockito.Mockito.*;

class TransactionalMailServiceTest {

    @Test
    void sendsOrderConfirmationViaConfiguredSender() {
        JavaMailSender sender = mock(JavaMailSender.class);
        MailAccounts accounts = new MailAccounts(
                new MailAccounts.Account(
                        "smtp-transactional.example.com",
                        587,
                        "txn-user",
                        "dummy-secret",
                        "account@example.com",
                        true,
                        5000
                ),
                new MailAccounts.Account(
                        "smtp-campaign.example.com",
                        587,
                        "campaign-user",
                        "dummy-secret",
                        "news@example.com",
                        true,
                        10000
                )
        );

        TransactionalMailService service =
                new TransactionalMailService(sender, accounts);
        service.sendOrderConfirmation("buyer@example.net", "ORD-123");

        ArgumentCaptor<SimpleMailMessage> captor =
                ArgumentCaptor.forClass(SimpleMailMessage.class);
        verify(sender).send(captor.capture());

        SimpleMailMessage sent = captor.getValue();
        assertEquals("account@example.com", sent.getFrom());
        assertEquals("Order confirmation ORD-123", sent.getSubject());
        assertEquals("buyer@example.net", sent.getTo()[0]);
    }
}
~~~

This example uses JUnit 5 and Mockito, assuming the project has matching test dependencies. It verifies the service builds the right content and invokes the injected sender; **it does not test real SMTP**. To verify Spring selects the right qualified bean, add an `ApplicationContext` integration test with `MailSenderConfiguration`. To test the SMTP flow, use a test mail server or provider sandbox.

A test environment can configure two independent mock SMTP hosts to verify transactional and campaign emails follow separate routes. Never send real emails to customers merely to verify configuration.

## 15. Common errors and how to resolve them

| Symptom | Cause | Resolution direction |
|---|---|---|
| Startup fails with **NoUniqueBeanDefinitionException** | Multiple `JavaMailSender` beans exist while injecting by generic type | Use `@Qualifier`, or `@Primary` when an intentional default exists. |
| **app.mail** config creates no senders | Custom namespace; Boot does not auto-generate beans for it | Declare `@ConfigurationProperties` and `@Bean` explicitly. |
| **spring.mail** properties do not affect the two beans | Manual senders do not automatically inherit Boot default settings | Bind explicitly and apply to each `JavaMailSenderImpl`. |
| Transactional mail goes out via campaign account | Wrong qualifier injected or wrong route in router | Place sender choice in purpose-specific service/router. |
| SMTP returns authentication error | Wrong credentials, missing account rights, wrong AUTH mechanism | Check secrets and account/provider policies. |
| STARTTLS/SSL handshake failure | Wrong port/TLS mode, invalid certificate | Check server TLS requirements, SSL/STARTTLS, and trust config. |
| Mail rejected due to From | Unverified From domain/address or not allowed for account | Verify identity, DNS, and ESP policies. |
| Campaign burst slows transactional mail | Shared quota, queue, connection pool, IP, or global limits | Separate workers/rate limits and provider resources where needed. |
| Duplicate sends on failover | Primary provider may have accepted the message before timeout | Log attempts, UNKNOWN state, reconcile before retrying. |
| Send succeeds yet recipient sees nothing | Spam, quarantine, late bounce, or mailbox issue | Check ESP logs, policies, and folders on receiving side. |
| Passwords leaked in logs | Dumping full properties object or unfiltered exceptions | Never print secrets; reduce log detail and restrict access. |

## 16. When are multiple senders unnecessary?

Not every application needs multiple SMTP connections.

**One sender may suffice** if the application sends one category of mail, low volume, from one verified address/domain, under one security policy and operational quota. Adding extra beans in that scenario only increases configuration surface and failure points.

**Multiple senders help** when purposes diverge clearly: transactional mail needs low latency and priority, campaigns need separate quotas/rate limits, tenants have distinct SMTP accounts, or provider isolation is required.

If you only need to vary **From** per message while using the same authorized SMTP account, one `JavaMailSender` may still be enough. If many tenants change dynamically at large scale, you do not have to create one static bean per tenant; instead, design a **sender registry** that configures, manages lifecycles, and selects senders per authorized tenant. Carefully control caching, secret handling, connection resources, and data isolation in such designs.

## 17. Summary

Spring Framework Mail lets you configure **multiple `JavaMailSenderImpl` instances** as distinctly named beans for different purposes. Store each SMTP account's settings in a structured namespace, bind them with **@ConfigurationProperties**, instantiate beans with **@Bean**, and select the right bean via **@Qualifier** or a purpose-based router.

What matters goes beyond creating two SMTP connections: pair each sender with **the right email category, authorized From address, security policy, quotas, retries, and monitoring**. Two beans only separate sending paths on the Spring side; queues, failover, deliverability, and end-to-end outcome tracking still must be designed at the appropriate layers.
