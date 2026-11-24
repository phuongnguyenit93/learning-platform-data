# Limits of the default configuration in a multi-sender system

An ordinary Spring Boot application only needs to send email from one SMTP account: configure `spring.mail.host`, `spring.mail.port`, `spring.mail.username`, `spring.mail.password`, and then inject `JavaMailSender` into services. This approach is simple and suits many small systems.

However, as a product grows, an application may need multiple sending sources: transactional emails go through account A, invoices go through account B, internal notifications use the company's SMTP relay, and marketing emails go through a separate provider. If you try to cram everything into one `spring.mail.*` configuration, the application will hit limits on **routing, authentication, sending permissions, configuration isolation, and operational governance**.

This lesson explains **the limits of Spring Boot Mail's default configuration in a multi-sender system**, distinguishes the meanings of "sender", and presents how to design multiple `JavaMailSender`s cleanly using Spring configuration, `@Qualifier`, and a send-routing layer.

> **Main point:** `spring.mail.*` by default describes **one mail-sending configuration**, not a mechanism that automatically manages multiple SMTP accounts or selects a provider per message. Multiple `From` addresses do not necessarily require multiple senders; multiple credentials or multiple SMTP transports are what usually call for a different configuration approach.

## 1. "Multiple senders" can carry different meanings

Before choosing an implementation approach, you must know what "sender" refers to.

| Need | Example | Are multiple `JavaMailSender`s needed? |
| --- | --- | --- |
| **Multiple From addresses yet one SMTP account** | `notification@example.org` and `support@example.org` share relay A | **Not necessarily.** One sender can suffice if the provider allows all those From addresses. |
| **Multiple SMTP accounts** | The notification-sending account and the billing-sending account have different username/password | **Usually yes.** Need a way to configure and pick the right credentials for each flow. |
| **Multiple SMTP hosts / providers** | Transactional mail via provider A, marketing via provider B | **May need multiple senders** or a dedicated adapter layer. |
| **Multiple brands / tenants** | Customer X sends with X's domain; customer Y sends with Y's domain | **Depends on scale and tenant rules.** Can use a registry, factory, or centralized sending service. |
| **Multiple recipients of the same message** | One mail sent to three To addresses and one Cc address | **No.** These are multiple recipients, not multiple SMTP senders. |

This distinction helps avoid building unnecessary infrastructure. If you only want to change the displayed sender name within the same relay, calling `helper.setFrom(...)` may suffice. But if the provider requires **logging into a different account, a different host, or a different TLS policy**, changing `From` does not change the SMTP connection being used.

### Example: one application, three kinds of email

Suppose the system has:

- **Account notifications:** `notify@example.org`, going through an SMTP provider for transactional email.
- **Invoices:** `billing@example.org`, going through another SMTP account to manage sending permissions and logs separately.
- **Customer care:** `support@example.org`, which may share the relay with account notifications if the provider allows using that alias.

In this design, the number of From addresses is three yet the number of SMTP connections to configure can be **two**, not three.

## 2. How does Spring Boot auto-configure mail?

When the mail starter and configuration conditions match, Spring Boot can create a mail-sending bean, usually `JavaMailSenderImpl`, based on the `spring.mail.*` property group.

Example of a single configuration:

~~~properties
spring.mail.host=smtp.main.example
spring.mail.port=587
spring.mail.username=${MAIN_SMTP_USERNAME}
spring.mail.password=${MAIN_SMTP_PASSWORD}

spring.mail.properties.mail.smtp.auth=true
spring.mail.properties.mail.smtp.starttls.enable=true
spring.mail.properties.mail.smtp.starttls.required=true
spring.mail.properties.mail.smtp.ssl.checkserveridentity=true
~~~

When the application has only one sender, a service usually only needs:

~~~java
@Service
public class NoticeService {

    private final JavaMailSender mailSender;

    public NoticeService(JavaMailSender mailSender) {
        this.mailSender = mailSender;
    }

    // mailSender.send(...) uses the shared configuration above.
}
~~~

You can picture it as:

~~~mermaid
flowchart TD
    A["spring.mail.*"] --> B["Spring Boot Mail Auto-configuration"]
    B --> C["One JavaMailSender"]
    D["Notification service"] --> C
    E["Billing service"] --> C
    F["Other service"] --> C
    C --> G["One SMTP transport configuration"]
~~~

This approach has the advantage of short configuration, easy dependency injection, and suitability for a single sending route. Yet **by default there is no concept** that "`spring.mail.notification.host` and `spring.mail.billing.host` will automatically create two senders". Those names are not a built-in multi-sender bean-creation mechanism of Spring Boot.

### Auto-configuration conditions must be understood accurately

Spring Boot usually only auto-creates a sender when the appropriate libraries and configuration sources exist, and no application-supplied mail-sending bean already satisfies the auto-configuration condition. When you define a `MailSender`/`JavaMailSender` bean yourself, the default auto-configuration mechanism may **yield to the manual configuration**.

Therefore, if the application declares a separate sender for billing, **do not assume** Spring Boot still automatically creates a second sender from `spring.mail.*` for notifications. Define clearly every sender needed in the ApplicationContext.

Specific details may differ by Spring Boot version or special setups like a JNDI mail session. The design principle remains: **do not use a single property to infer that the framework is automatically managing multiple independent senders**.

## 3. Limits when using a single default configuration

### 3.1. Only one set of host, port, and credentials

The `spring.mail.*` group usually provides one combination:

~~~text
host + port + username + password + SMTP properties
~~~

These values can be reused for many messages, yet do not automatically change for "billing email" or "notification email". If two flows require two different username/password pairs, a single sender cannot distinguish them based solely on Subject or recipient address.

### 3.2. No business-based router

The framework does not automatically know that a message with Subject "Invoice" must use SMTP A while a message with Subject "Account verification" must use SMTP B. **Route selection must be defined by the application.**

You should not infer routes merely by searching keywords in the Subject: subjects vary by locale, can collide, and are not a stable business key. A parameter such as `MailPurpose.BILLING` or `MailPurpose.NOTIFICATION` is much clearer.

### 3.3. One shared TLS/timeout configuration

Two SMTP providers may have different requirements:

| Factor | Provider A | Provider B |
| --- | --- | --- |
| Host | `smtp.notify.example` | `smtp.billing.example` |
| Port | `587` | `465` |
| TLS | STARTTLS | Implicit TLS |
| Username/password | Credential A | Credential B |
| Timeout | Per notification needs | Per invoice issuance SLA |

A single `spring.mail.properties.mail.smtp.*` set cannot simultaneously represent two independent connection styles without a separate configuration layer.

### 3.4. No separation of quotas, send results, and errors by provider

Providers may have different sending limits, domain verification statuses, recipient rejection policies, and bounce-receiving channels. Using the same service without recording the **selected sender/provider** makes it hard to diagnose when one sending flow is blocked while other flows remain normal.

### 3.5. Does not automatically resolve permission to send from multiple domains

Having multiple `From` addresses in code does not prove the SMTP provider permits sending from those domains. The provider may require address/domain verification, DKIM, SPF, or apply anti-spoofing policies.

`JavaMailSender` cannot bypass these rules by changing `setFrom(...)`. Permitted sending identities are part of the **contract with the SMTP infrastructure**, not merely a Java property.

### 3.6. Missing tenant context and security responsibility

If a multi-tenant application shares one sender configured with tenant A's credentials and then changes `From` to tenant B's domain, that can be a permission violation. For multi-customer systems, you must bind **which sender a tenant is allowed to use**, not just validate email address syntax.

## 4. Distinguishing From, Reply-To, SMTP account, and envelope sender

In a multi-sender system, the following four identities can differ:

| Component | Role | Common way to set |
| --- | --- | --- |
| **SMTP account** | Login identity on the relay | `JavaMailSenderImpl.setUsername(...)` and `setPassword(...)` |
| **From header** | Sender address the recipient sees | `MimeMessageHelper.setFrom(...)` |
| **Reply-To header** | Where replies are suggested to be sent | `MimeMessageHelper.setReplyTo(...)` |
| **Envelope sender** | Identity sent in `MAIL FROM` during the SMTP session; usually used for bounces | Determined by the SMTP transport/provider per configuration and policy |

Example:

~~~text
SMTP account:    smtp-notification-account
From:            Notification Team <notify@example.org>
Reply-To:        helpdesk@example.org
Envelope sender: bounce-route-123@mailer.example.org
~~~

This information can coexist in a single sending flow. **Do not treat `spring.mail.username` as always being `From`**, and do not assume changing `From` swaps the SMTP account.

In particular, if you pick the wrong sender yet set the right From, the message may be rejected, have its sender info rewritten, or trigger domain authentication failures. You need to pick **both the transport** and **the displayed identity** correctly.

## 5. Three design directions for a multi-sender system

Depending on the number of accounts, rate of configuration changes, and operational requirements, you can choose one of three common approaches.

| Design | Idea | Suitable when |
| --- | --- | --- |
| **One sender, multiple permitted Froms** | Use one `JavaMailSender`, change `From` per message | One relay allows multiple aliases/sending domains |
| **Multiple JavaMailSender beans** | Each SMTP account/provider is a separate bean, injected with `@Qualifier` | A small number of fixed sending routes |
| **Sender registry/factory** | Pick an authorized configuration from a registry, then use a matching sender | Many tenants or senders changing over time |

With a system that has only two or three fixed providers, **multiple explicitly named beans** usually suffice. With hundreds of tenants, declaring hundreds of static beans in code can become hard to maintain; at that point you need a registry layer, caching, secret management, and resource-limiting policies.

Whichever direction you take, preserve one principle: **business services request sending mail by purpose**, rather than arbitrarily picking an SMTP account from a user-supplied string.

## 6. Example: configuring two independent senders with Spring Boot

Suppose the application uses two SMTP accounts:

- `notification`: sends account status notifications;
- `billing`: sends invoices and receipts.

These two accounts have different hostnames, credentials, and From addresses. To focus on multi-sender limits, the example below assumes **both SMTP relays support submission via STARTTLS on port 587**. If one provider uses implicit TLS on port 465, you must replace the TLS configuration for that specific sender.

### 6.1. Spring Boot dependency

In Gradle:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-mail'
}
~~~

The starter brings Spring Mail/Jakarta Mail components into the application. From here, instead of asking the framework to auto-create multiple senders from `spring.mail.*`, we will **declare two beans ourselves**.

### 6.2. application.yml: application-defined configuration namespace

~~~yaml
app:
  mail:
    notification:
      host: smtp.notify.example
      port: 587
      username: ${NOTIFY_SMTP_USERNAME}
      password: ${NOTIFY_SMTP_PASSWORD}
      from: notify@example.org
    billing:
      host: smtp.billing.example
      port: 587
      username: ${BILLING_SMTP_USERNAME}
      password: ${BILLING_SMTP_PASSWORD}
      from: billing@example.org
~~~

The names `app.mail.notification.*` and `app.mail.billing.*` are **application-defined configuration keys**, not properties Spring Boot understands automatically to create multiple `JavaMailSender`s.

The illustrative data uses hypothetical hostnames. In operations, use real parameters issued by the SMTP provider. Environment variables must be supplied via the runtime environment or a secret-management system; do not store passwords in the repository.

### 6.3. Declaring two JavaMailSender beans

A minimal implementation using `@Value` is:

~~~java
import java.util.Properties;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.mail.javamail.JavaMailSender;
import org.springframework.mail.javamail.JavaMailSenderImpl;

@Configuration(proxyBeanMethods = false)
public class MultiSenderConfiguration {

    @Bean("notificationMailSender")
    public JavaMailSender notificationMailSender(
            @Value("${app.mail.notification.host}") String host,
            @Value("${app.mail.notification.port}") int port,
            @Value("${app.mail.notification.username}") String username,
            @Value("${app.mail.notification.password}") String password) {

        return newStartTlsSender(host, port, username, password);
    }

    @Bean("billingMailSender")
    public JavaMailSender billingMailSender(
            @Value("${app.mail.billing.host}") String host,
            @Value("${app.mail.billing.port}") int port,
            @Value("${app.mail.billing.username}") String username,
            @Value("${app.mail.billing.password}") String password) {

        return newStartTlsSender(host, port, username, password);
    }

    private static JavaMailSenderImpl newStartTlsSender(
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
        props.put("mail.smtp.timeout", "5000");
        props.put("mail.smtp.writetimeout", "5000");

        return sender;
    }
}
~~~

**Points to note in the configuration:**

1. `@Bean("notificationMailSender")` and `@Bean("billingMailSender")` create **two differently named beans**, both implementing the `JavaMailSender` interface.
2. Each bean holds its own set of `host/port/username/password`.
3. The factory method reuses the connection-creation logic instead of duplicating all SMTP properties.
4. Both senders use STARTTLS because **the example deliberately chose two providers with compatible protocols**.
5. `getJavaMailProperties()` holds configuration for Jakarta Mail. Those properties are set when creating the bean, and should not be mutated arbitrarily on every send.
6. The `from` value has not been applied at the transport-creation step. It will be used when **creating the message**, because `From` is part of the message rather than the connection's username.

Note: **declaring two beans of the same type does not mean Spring automatically knows which bean to use for which service**. That is the responsibility of dependency injection and routing.

### 6.4. If the two providers use two different TLS types

When the notification provider uses STARTTLS 587 and the billing provider uses implicit TLS 465, you should not call a shared STARTTLS factory like the example above for both.

You can build a factory that takes a specified connection type:

~~~java
private static void configureTls(
        JavaMailSenderImpl sender,
        boolean implicitTls) {

    Properties props = sender.getJavaMailProperties();
    props.put("mail.smtp.auth", "true");
    props.put("mail.smtp.ssl.checkserveridentity", "true");

    if (implicitTls) {
        // Example when the server supports TLS right from the TCP connection.
        props.put("mail.smtp.ssl.enable", "true");
    } else {
        // Example when the server supports STARTTLS.
        props.put("mail.smtp.starttls.enable", "true");
        props.put("mail.smtp.starttls.required", "true");
    }
}
~~~

The snippet above is an **illustrative helper piece replacing the TLS setting in the factory**; it is not something to call additionally after already attaching both conflicting TLS types. What matters is configuring **each sender** according to its own set of parameters provided by the provider.

## 7. Injecting the right sender with @Qualifier

When there are two beans of type `JavaMailSender`, a constructor like the following no longer states intent clearly:

~~~java
public BillingService(JavaMailSender mailSender) {
    this.mailSender = mailSender;
}
~~~

Without a criterion to resolve a unique bean, Spring may report an error because **multiple matching beans exist** (such as `NoUniqueBeanDefinitionException` during bean creation). You can use `@Qualifier` to specify exactly:

~~~java
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.mail.javamail.JavaMailSender;
import org.springframework.stereotype.Service;

@Service
public class BillingService {

    private final JavaMailSender billingMailSender;

    public BillingService(
            @Qualifier("billingMailSender")
            JavaMailSender billingMailSender) {

        this.billingMailSender = billingMailSender;
    }
}
~~~

Similarly, `NotificationService` uses `@Qualifier("notificationMailSender")`.

You can put `@Primary` on one sender so the application knows the default bean when injecting without a qualifier. But `@Primary` **only decides bean-selection priority during dependency injection**; it does not automatically route billing emails to the billing account when code accidentally calls the primary sender.

If the design needs selection strictly by business purpose, the clear approach is using qualifiers or a service/router with a purpose-based API.

## 8. Mail-sending routing layer by purpose

When a business service has to send several kinds of email, injecting a separate sender into each service may suffice. Yet if one flow can send different kinds of email, you can create a **MailRouter** to centralize sender-selection policy in one place.

### 8.1. Defining the send purpose

~~~java
public enum MailPurpose {
    NOTIFICATION,
    BILLING
}
~~~

This is an application-defined enum, not a standard Spring Mail enum. It describes **business intent**, avoiding having to guess the sender from Subject content or recipient domain.

### 8.2. Router using two beans and two From addresses

~~~java
import jakarta.mail.MessagingException;
import jakarta.mail.internet.MimeMessage;

import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.mail.javamail.JavaMailSender;
import org.springframework.mail.javamail.MimeMessageHelper;
import org.springframework.stereotype.Service;

@Service
public class MailRouter {

    private final JavaMailSender notificationSender;
    private final JavaMailSender billingSender;

    private final String notificationFrom;
    private final String billingFrom;

    public MailRouter(
            @Qualifier("notificationMailSender")
            JavaMailSender notificationSender,
            @Qualifier("billingMailSender")
            JavaMailSender billingSender,
            @Value("${app.mail.notification.from}")
            String notificationFrom,
            @Value("${app.mail.billing.from}")
            String billingFrom) {

        this.notificationSender = notificationSender;
        this.billingSender = billingSender;
        this.notificationFrom = notificationFrom;
        this.billingFrom = billingFrom;
    }

    public void send(
            MailPurpose purpose,
            String recipient,
            String subject,
            String plainText) throws MessagingException {

        if (purpose == null) {
            throw new IllegalArgumentException(
                    "Mail-sending purpose must be specified"
            );
        }

        if (recipient == null || recipient.isBlank()) {
            throw new IllegalArgumentException(
                    "Recipient must not be empty"
            );
        }

        if (subject == null || subject.isBlank()
                || plainText == null || plainText.isBlank()) {
            throw new IllegalArgumentException(
                    "Subject and content must not be empty"
            );
        }

        JavaMailSender selected;
        String from;

        switch (purpose) {
            case NOTIFICATION -> {
                selected = notificationSender;
                from = notificationFrom;
            }
            case BILLING -> {
                selected = billingSender;
                from = billingFrom;
            }
            default -> throw new IllegalArgumentException(
                    "Send purpose is not supported yet"
            );
        }

        // Create the message using the selected sender itself.
        MimeMessage message = selected.createMimeMessage();

        MimeMessageHelper helper =
                new MimeMessageHelper(message, false, "UTF-8");

        helper.setFrom(from);
        helper.setTo(recipient);
        helper.setSubject(subject);
        helper.setText(plainText, false);

        selected.send(message);
    }
}
~~~

Usage:

~~~java
mailRouter.send(
        MailPurpose.BILLING,
        "buyer@example.net",
        "Your invoice is ready",
        "You can view the invoice in your account."
);

mailRouter.send(
        MailPurpose.NOTIFICATION,
        "member@example.net",
        "Login from a new device",
        "The system recorded a new login."
);
~~~

The calls above assume they sit inside a service with a `MailRouter mailRouter` dependency. The two emails use **two different transports** without the business layer having to read host/password itself.

### Why choose the sender before creating MimeMessage?

A `MimeMessage` object carries content and headers, yet does not carry a business contract stating **which sender it must be sent through**. Choosing the sender first, then creating the message via `selected.createMimeMessage()`, makes the configuration source easy to trace and avoids accidentally using a different `Session` or default values.

If using low-level Jakarta Mail APIs, you can manage `Session` and `Transport` separately; yet with ordinary Spring Mail, let the chosen `JavaMailSender` encapsulate the SMTP interaction.

### The router should not automatically try another provider on every error

Switching to a second sender to "rescue" a send request is not always right. The second sender might not be permitted to use the same `From` address, might lack matching DKIM, or might not be permitted to send content of that kind. If failover is planned, define **in advance** which sender pairs may substitute for each other, the routing-switch conditions, and duplicate-send prevention mechanisms.

## 9. Why not change host, username, and password on one singleton on every send?

A tempting yet dangerous approach is declaring a single `JavaMailSenderImpl` and changing it before each send:

~~~java
// Example to AVOID in a concurrent service:
sender.setHost(hostForCurrentRequest);
sender.setUsername(userForCurrentRequest);
sender.setPassword(secretForCurrentRequest);
sender.send(message);
~~~

The problem lies not in Java syntax, but in a **shared object with mutable state**.

Picture two requests running concurrently:

~~~text
Request A: setHost(smtp-a.example)
Request B: setHost(smtp-b.example)
Request A: setUsername(user-a)
Request B: setPassword(password-b)
Request A: send(...)
~~~

Then request A risks using a **combination of host/username/password that does not belong to the same account**. Depending on execution and when configuration is read, concurrent mutation can cause authentication errors, sending to the wrong provider, or data leaks between tenants.

Other risks include:

- `JavaMailSenderImpl` may hold or create a `Session` and related components; mutating properties while send operations occur creates unpredictable state.
- Asynchronous mail-sending threads decouple configuration time from execution time.
- Tenant A's credentials may remain in the shared object when request B arrives.
- In operations, it is hard to trace which sender was used at send time.

**Recommendation:** create senders with complete configuration and use them steadily for the routes they serve; when an account change is needed, choose another sender or build a new sender through a safe process. Do not use mutating operations on a singleton as a per-request router.

## 10. When the number of senders grows: Registry and factory

Two fixed beans are easy to understand yet not ideal when the system has dozens or hundreds of tenants. In that case, you can place an abstraction layer:

~~~mermaid
flowchart TD
    A["Business request with tenantId, purpose"] --> B["Mail routing policy"]
    B --> C["Verify tenant permissions"]
    C --> D["Sender registry"]
    D --> E["Approved configuration and secrets"]
    E --> F["Matching JavaMailSender"]
    F --> G["SMTP provider"]
~~~

A router at this scale needs to answer:

1. **Which tenant is allowed to use which sender?**
2. **Where is the sending configuration fetched from, and how is it validated and updated?**
3. **At what moment are credentials decrypted/fetched from the secret manager?**
4. **Are senders cached, how long is the cache kept, and when is it evicted?**
5. **Does changing credentials affect in-flight requests?**
6. **What are the connection and send-rate limits per tenant/provider?**
7. **Do bounces/reply-to addresses/delivery events need to be separated?**

### Example interface of a sender-selection layer

~~~java
public interface SenderRegistry {

    MailRoute resolve(String tenantId, MailPurpose purpose);
}

public record MailRoute(
        JavaMailSender sender,
        String fromAddress) {
}
~~~

The interface above expresses an **application contract**, not a built-in Spring API. An implementation can look up senders in a trusted configuration map or cache initialized instances. It should not accept any arbitrary hostname/credential string from an HTTP request and connect right away.

When the number of senders is too large or sending policies require tracking complex quotas, bounces, and failover, splitting into a **dedicated mail delivery service** or using a provider's API may fit better than endlessly multiplying SMTP configurations inside a web application.

### Warning about dynamic hosts and SSRF

If tenants are allowed to enter arbitrary SMTP hosts and ports and the application opens direct network connections, the system can be abused as a mechanism to connect to internal network addresses or sensitive services. Restrict accepted endpoints, control egress network, check configuration permissions, and do not return credential details in errors. This is a security issue of **dynamically configured multi-sender systems**, which cannot be solved by `JavaMailSender` alone.

## 11. Managing @Primary, @Qualifier, and default beans

Suppose two beans already exist:

~~~text
notificationMailSender: JavaMailSender
billingMailSender:      JavaMailSender
~~~

If a service injects:

~~~java
public ReportService(JavaMailSender sender) { ... }
~~~

Spring needs to know which bean to pick. Several options:

| Option | Meaning | What to be careful about |
| --- | --- | --- |
| `@Qualifier("billingMailSender")` | Selects the exact bean by name or qualifier | Name must match configuration and align with purpose |
| `@Primary` on one bean | Selects the preferred bean when there is no specific qualifier | May mask a service forgetting to choose a sender by business logic |
| `MailRouter` layer | Uses send purpose to select sender | Router must have a clear policy, not pick arbitrarily |
| Injecting a bean collection/map | Receives multiple beans, picks by key | Need to restrict keys and usage permissions |

An example using a Spring-injected map:

~~~java
@Service
public class SenderInspector {

    private final Map<String, JavaMailSender> senders;

    public SenderInspector(Map<String, JavaMailSender> senders) {
        this.senders = senders;
    }
}
~~~

`Map<String, JavaMailSender>` usually has keys equal to **bean names**. This injection style is convenient for a simple admin/registry layer, yet you should not let web clients pass a bean name directly to pick SMTP credentials. Map from an **authorized business purpose** to a specific bean.

### Should spring.mail.* be kept when two senders are already self-declared?

If all senders are defined by the application itself using `app.mail.*`, you may **not need** `spring.mail.host/port/username/password` for the same goal. Keeping two parallel configuration sources without a clear convention easily misleads operators.

If you intentionally maintain one "default" sender from `spring.mail.*` alongside other senders, check exact auto-configuration conditions and verify how beans are created. The most predictable approach in a multi-sender system is usually **explicitly declaring every important sending route**.

## 12. Constraining From, Reply-To, and domain verification per sender

After picking the right SMTP account, you must still check **which From is allowed on that account**.

For example, a router can define:

~~~text
notificationMailSender:
  allowedFrom:
    - notify@example.org
    - support@example.org

billingMailSender:
  allowedFrom:
    - billing@example.org
~~~

This is illustrative policy data, not a standard Spring Boot property. When a service asks to send using an address outside the list, the router should reject early per the application's contract.

Some providers apply policies:

- Requiring verification of the sending domain or address.
- Configuring DKIM to sign mail with the sending domain.
- Checking SPF and DMARC policies for domain authentication capability.
- Restricting which `From` or `Reply-To` may be used.
- Creating a dedicated envelope sender address for bounce processing.

Picking the right SMTP account is only the first step. **The mail identity and domain configuration must be compatible with the chosen provider.**

If there are two independent brand domains, do not assume both can share one account merely because `setFrom(...)` technically allows changing it.

## 13. Separating secret configurations between senders

A multi-sender system has many credentials. Instead of putting all of them into one shared file as plaintext, use environment variables or a secret manager per route.

Example variable names:

~~~text
NOTIFY_SMTP_USERNAME
NOTIFY_SMTP_PASSWORD

BILLING_SMTP_USERNAME
BILLING_SMTP_PASSWORD
~~~

Principles:

1. Each sender uses **credentials and sending permissions matching** its purpose.
2. Separate credentials across local, staging, and production environments.
3. Manage credential rotation/revocation per provider to avoid one issue affecting everything.
4. Do not log username/password, MIME content, or entire recipient lists if unnecessary.
5. Do not put real credentials in the repository, training docs, or exception output variables.
6. When tenants exist, check configuration access permissions so tenant A cannot read or use tenant B's secrets.
7. If caching senders, have a mechanism to replace/evict the cache when credentials change.

Changing `username/password` on a singleton sender per request is not a safe secret-management approach. For systems that rotate credentials frequently, you need a process to **update senders by configuration version** and define clearly when old instances are no longer used.

## 14. Operating multiple senders: quotas, timeouts, retries, and observability

Two SMTP providers can have very different policies. Adding more beans does not automatically create a reliable orchestration system.

### 14.1. Limits are needed per provider

Example:

| Criterion | Notification sender | Billing sender |
| --- | --- | --- |
| Priority | High | High |
| Rate policy | Per notification provider quota | Per billing provider quota |
| Timeout | Short, per application SLA | Per invoice processing policy |
| Retry | For transient errors | For transient errors, with reconciliation |
| Bounce tracking | Notification channel | Billing channel |

The table only illustrates how to think about it, not the limits of a specific provider. **Increasing the number of senders does not mean total quota is split evenly or tracked automatically by Spring.**

### 14.2. Errors need to be classified by route

An email can fail because of:

- DNS or connection failure to the SMTP host.
- Incompatible port/TLS configuration.
- Invalid username/password or expired credentials.
- Sender not permitted to use the From address.
- SMTP server temporarily rejecting or rate-limiting.
- Recipient address rejected.
- Message bounced after the relay accepted it.

When recording errors, attach the **request ID**, **send purpose**, **senderId/providerId**, and error type. You do not need to log passwords or raw emails to trace the origin.

### 14.3. One successful send does not prove DELIVERED

`JavaMailSender.send(...)` returning normally usually reflects that submitting the mail to the sending infrastructure completed per the received response. That does not guarantee the recipient has the mail in their Inbox.

To track delivery by sender/provider, you may need webhooks, a bounce mailbox, dashboards, or the provider's event API. A multi-sender system must know **which account an event belongs to**, avoiding mixing statuses across sending routes.

### 14.4. Retries must respect the original sender and business correctness

If an invoice was created from the billing sender yet a retry picks the notification sender, switching routes may violate sending permissions or produce inconsistent emails. In a queued system, store attributes such as:

~~~text
mail_request_id: 93f...
purpose: BILLING
sender_id: billing
recipient: buyer@example.net
template_id: invoice-ready
status: RETRY_WAITING
attempt_count: 2
~~~

This is an illustrative application data model. `sender_id` tells the worker which sending route was approved; on an intentional failover, the application needs to record the **decision to pick an alternate route** and the reason.

SMTP has no exactly-once guarantee for sends through the application API. If the connection drops after the server received the mail yet before the client saw the final response, resending can create duplicate mail. Use an **outbox, business idempotency keys, retry limits, and UNKNOWN state when needed**.

## 15. Testing multiple senders without sending real mail

The most important verification problem is usually **correct routing**:

- Account notifications must call the notification sender.
- Invoices must call the billing sender.
- The From header matches the chosen sender.
- No request uses the wrong credentials or provider due to a shared configuration variable.
- When a sender reports an error, the system only retries/fails over according to permitted policy.

You can test the router layer by replacing `JavaMailSender`s with separate fakes/mocks, then verifying which sender receives the `send(...)` call. There is no need to open real SMTP connections for route-selection logic tests.

Example model:

~~~text
given:  purpose = BILLING
when:   mailRouter.send(...)
then:   billingMailSender.send(...) is called
and:    notificationMailSender.send(...) is not called
and:    From matches billing
~~~

When wanting to test SMTP protocol and TLS, you can use an SMTP test server or a sandbox managed by the test environment. Test configuration should separate real credentials to avoid unintended sends to customers.

Do not use a single mock for both senders if you want to prove the router actually picks the right route; you need two distinct objects and corresponding assertions.

### Separating three layers of verification

| Layer | What to verify |
| --- | --- |
| **Router unit test** | Picks right bean, right From, right purpose |
| **Integration test with SMTP test server** | Each sender uses the right host/port and security config, message is built as desired |
| **Real operations** | Credentials, quotas, domain verification, bounces, and deliverability of each provider |

Each layer answers a different question. A router passing unit tests does not by itself prove an Internet SMTP provider allows sending.

## 16. Common design mistakes

### 16.1. Using multiple Froms and thinking you have multiple SMTP senders

~~~java
helper.setFrom("billing@example.org");
mailSender.send(message);
~~~

Changing From **does not change** the `mailSender` being used. If the application still injects the default notification sender, the message still goes through that relay.

### 16.2. Setting app.mail.billing.host yourself without creating a bean

~~~properties
app.mail.billing.host=smtp.billing.example
~~~

A custom key does not automatically make Spring Boot generate `billingMailSender`. You need application code or a configuration mechanism that reads this key and creates the corresponding sender.

### 16.3. Having two JavaMailSenders yet injecting ambiguously

A service with an unqualified `JavaMailSender` may hit a multiple-bean error, or receive a `@Primary` bean that does not match business logic. Use qualifiers or a router.

### 16.4. Mutating a shared JavaMailSenderImpl per request

Changing host/credentials on a singleton object can create race conditions and mix data between concurrent requests. Use fixed senders per route or a controlled registry.

### 16.5. Trying to configure port 465 with STARTTLS 587

If one provider uses implicit TLS and one provider uses STARTTLS, configure **each sender separately**. Do not use one STARTTLS factory for everything without checking the connection type.

### 16.6. Routing by Subject or recipient domain

Subjects can change due to translation, templates, or user data; recipient domains usually do not express business intent. Pass a controlled explicit `purpose`/`senderId` instead of guessing.

### 16.7. Choosing SMTP hosts dynamically directly from user input

This is not only a logic bug; it can create unauthorized network connection paths and leak credentials. You need allowlists, configuration permissions, egress policies, and validation of chosen routes.

### 16.8. Unconditional failover to another account

Another provider may not be permitted to send the same From/domain. Avoid automatically switching routes just because the first provider failed; failover must have constraints on sending identity and prior submission status.

### 16.9. Sharing logs and statuses and not knowing which sender failed

When there are multiple accounts, identify the provider and route in logs/metrics. You do not need to expose credentials to have good observability.

### 16.10. Thinking one successful send means mail was delivered

Multiple senders do not change the meaning of `JavaMailSender.send(...)`. To know DELIVERED/BOUNCED you need a reliable delivery-event source.

## 17. Reasoning exercises

**Question 1.** An application has three From addresses, yet all three are verified by the SMTP relay and permitted to send through the same account. Is it mandatory to create three `JavaMailSender` beans?

**No.** You can use one sender and set the appropriate From on each message, as long as it meets the relay's policy and business-data isolation.

**Question 2.** `spring.mail.host=smtp.a.example` and the application adds `app.mail.billing.host=smtp.b.example`. Does Spring Boot automatically create an extra billing sender?

**No.** `app.mail.billing.host` is a custom key; it requires a mechanism to read configuration and create the corresponding bean/registry.

**Question 3.** There are two beans `notificationMailSender` and `billingMailSender`. Every service constructor-injects `JavaMailSender` without a qualifier. What problem can occur?

Spring may fail to resolve a suitable bean, or use a default bean unsuitable for the sending flow. Use `@Qualifier` or a clear router.

**Question 4.** You want to send invoices from account B yet only call `helper.setFrom("billing@example.org")` on a message created from sender A. Has the SMTP account changed?

**Not yet.** Changing the From header does not change the username/password, host, or SMTP transport.

**Question 5.** Should you modify `setHost`/`setPassword` on a singleton sender per request to save memory?

**You should not.** This is shared mutable configuration; concurrent requests can mix parameters and cause errors sending via the wrong route. Use independently configured senders or a managed factory/registry.

**Question 6.** A system has 200 tenants and each tenant has its own SMTP credentials. Should you write 200 manual `@Bean` methods?

Usually not a maintainable direction. A controlled registry/factory, tenant policies, secret management, bounded caching, and per-provider monitoring fit better.

**Question 7.** The billing sender hits a timeout while the notification sender is healthy. Can you automatically send invoices through notification?

Only when there is an **approved failover policy**, the substitute sender has permission for the relevant From/domain, and prior send state has been handled to reduce duplicates. Do not switch arbitrarily.

**Question 8.** A message was accepted by the relay. Can you record `DELIVERED` for the recipient yet?

**Not yet.** Separate delivery evidence is needed, usually from the provider or receiving infrastructure. `send(...)` does not itself provide this final guarantee.

## 18. Memory model

In Spring Boot, `spring.mail.*` is a **good starting point for simple SMTP configuration**, yet is not an orchestration system for multiple mail-sending accounts.

~~~mermaid
flowchart TD
    A["Email send request"] --> B{"Purpose and tenant?"}
    B --> C["Routing policy"]
    C --> D["Notification sender"]
    C --> E["Billing sender"]
    C --> F["Other authorized sender"]
    D --> G["SMTP provider A"]
    E --> H["SMTP provider B"]
    F --> I["SMTP provider N"]
~~~

Remember four boundaries:

1. **From is not the SMTP account.** Changing From only changes the message's display information, without automatically changing host and credentials.
2. **One `spring.mail.*` does not automatically create multiple senders.** To get multiple routes, configure `JavaMailSender` beans or an explicit registry/factory.
3. **Multiple beans need a selection mechanism.** Use `@Qualifier`, intentional `@Primary`, or a router by controlled purpose/tenant.
4. **Correct routing is not enough to guarantee successful sending.** Each sender still needs its own TLS configuration, From permissions, secrets, quotas, retries, and delivery tracking.

When a system has few fixed routes, two or three independently configured beans are usually easy to read and operate. When a system has many tenants or changes senders frequently, upgrade to a registry/factory and corresponding governance layer, instead of turning a shared `JavaMailSenderImpl` into an object whose host/password gets mutated before every send.

