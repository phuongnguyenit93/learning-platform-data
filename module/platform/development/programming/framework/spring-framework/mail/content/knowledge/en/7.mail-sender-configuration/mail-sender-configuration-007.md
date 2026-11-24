# `JavaMailSender` as a Shared Bean in Spring Framework Mail

In a Spring application, multiple features may need to send email: account registration, address verification, order notifications, reminders, or reports. If each feature creates its own `JavaMailSenderImpl` and configures SMTP separately, the project will soon scatter different hosts, ports, authentication credentials, and timeout rules across many places. When switching email providers or changing security policies, maintaining scattered configurations becomes difficult.

The natural organization in Spring is to **register a `JavaMailSender` as a shared bean**, then use dependency injection so services that need to send email share that same component. A shared sender bean centralizes protocol configuration, reduces duplicated setup code, and makes it easy to swap in a mock during testing.

An essential distinction upfront: **sharing a `JavaMailSender` bean does not mean sharing a single email, a single `MimeMessage`, or one permanently open SMTP connection**. The bean is the sending component and configuration; each send still creates its own message, while the library manages transports and SMTP connections per operation.

## 1. What is `JavaMailSender`?

Spring Framework Mail has several key types:

| Type | Role | Use case |
| --- | --- | --- |
| `MailSender` | Interface for sending `SimpleMailMessage` | Simple plain-text emails |
| `JavaMailSender` | Extends sending capabilities with `MimeMessage` and `MimeMessagePreparator` | HTML emails, MIME, attachments, rich content |
| `JavaMailSenderImpl` | Standard SMTP implementation provided by Spring | Bean connecting to an SMTP relay or Email Service Provider (ESP) |
| `SimpleMailMessage` | Data for a plain-text message | Short notifications, text emails |
| `MimeMessage` | Email message per Jakarta Mail/MIME | HTML, multipart, files, and inline content |
| `MimeMessageHelper` | Spring utility for configuring `MimeMessage` | Setting From/To/Subject, HTML, attachments, inline images |
| `MimeMessagePreparator` | Callback preparing a `MimeMessage` before sending | Encapsulating email content creation in a callback |

`JavaMailSender` is **an interface**. Business code should declare dependencies on this interface; Spring supplies an implementation at runtime. This avoids tight coupling to `JavaMailSenderImpl` and allows substituting another bean in tests or when changing sending approaches.

A simple architecture:

```text
                Spring ApplicationContext
                         |
                         v
              JavaMailSender bean
              (JavaMailSenderImpl)
                 |      |      |
                 |      |      |
        +--------+      |      +---------+
        |               |                |
        v               v                v
  RegistrationMail  OrderMail        ReportMail
      Service        Service          Service
        |               |                |
        +---------------+----------------+
                        |
                 send(message)
                        |
                        v
                  SMTP relay / ESP
```

Services can create different emails while sharing the SMTP configuration and sending mechanism provided by the central bean.

## 2. What does a shared bean mean in Spring?

In Spring, a bean declared with `@Bean` or created by auto-configuration usually has **singleton scope by default**. Within an `ApplicationContext`, Spring typically creates one instance of the bean and supplies a reference to that instance to components with matching dependencies.

Example:

```java
@Service
public class RegistrationMailService {
    private final JavaMailSender mailSender;

    public RegistrationMailService(JavaMailSender mailSender) {
        this.mailSender = mailSender;
    }
}
```

And:

```java
@Service
public class BillingMailService {
    private final JavaMailSender mailSender;

    public BillingMailService(JavaMailSender mailSender) {
        this.mailSender = mailSender;
    }
}
```

If there is only one `JavaMailSender` bean in the context, Spring injects **that same instance** into both services.

### A Spring singleton is not a system-wide singleton

- A singleton bean exists per **ApplicationContext**; it is not automatically shared across separate Java processes.
- Two containers/pods running the same application each have their own sender instance, even if they point to the same SMTP host and credentials.
- Two different ApplicationContexts can have their own separate beans.
- Sharing a Java instance does not create a system-wide rate limit and does not prevent two instances from sending the same email.
- In unit tests, if you instantiate a service manually with `new`, you must pass the dependency into the constructor; the Spring container does not inject into objects you create yourself.

### A sender bean differs from messages and SMTP connections

`JavaMailSenderImpl` holds host, port, username, password, JavaMail properties, and a Jakarta Mail `Session`. It is a sending component, not "the letter currently being drafted."

Typically, the SMTP implementation opens and uses a transport per send or per batch within a single `send` call, then closes the transport afterward. **Merely declaring a singleton bean does not imply an SMTP connection pool or an always-open TCP connection**.

Do not assume handshake/authentication overhead disappears just because the sender is a singleton. When high throughput is needed, evaluate batching, connection limits, pooling in the library/ESP, and actual sending policies.

## 3. Preferred approach: Spring Boot auto-creates `JavaMailSender`

With Spring Boot, the simplest approach is adding the mail starter and declaring configuration. When auto-configuration conditions match and no custom sender bean takes precedence, Boot can create `JavaMailSenderImpl` for the application.

### Adding the dependency

With Maven and a project using Spring Boot dependency management:

```xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-mail</artifactId>
</dependency>
```

With Gradle:

```groovy
implementation 'org.springframework.boot:spring-boot-starter-mail'
```

Examples below use Spring Framework 6+/Spring Boot 3+ and the `jakarta.mail.*` package. Older Spring generations may use `javax.mail.*`; never mix both package families in the same application.

### Configuring SMTP in `application.properties`

```properties
spring.mail.host=smtp.example.com
spring.mail.port=587
spring.mail.username=${SMTP_USERNAME}
spring.mail.password=${SMTP_PASSWORD}
spring.mail.default-encoding=UTF-8

spring.mail.properties.mail.smtp.auth=true
spring.mail.properties.mail.smtp.starttls.enable=true
spring.mail.properties.mail.smtp.starttls.required=true

spring.mail.properties.mail.smtp.connectiontimeout=5000
spring.mail.properties.mail.smtp.timeout=10000
spring.mail.properties.mail.smtp.writetimeout=10000
```

Host, port, and TLS mode must match the actual SMTP provider. Port 587/STARTTLS is a common example, not the only option. Environment variables `SMTP_USERNAME` and `SMTP_PASSWORD` should come from the deployment environment or a secret manager rather than putting sensitive values in source code.

The three timeouts are in milliseconds:

| Property | Example value | Meaning |
| --- | ---: | --- |
| `mail.smtp.connectiontimeout` | 5000 | Time limit for opening a socket connection |
| `mail.smtp.timeout` | 10000 | Time limit for reading data from the socket |
| `mail.smtp.writetimeout` | 10000 | Time limit for writing data to the socket |

Omitting timeout values can allow some socket operations to block for a very long time. These properties do not set a total deadline for an entire `send()` call; a single send can perform multiple sequential read/write operations.

Configuration can also use `application.yml`:

```yaml
spring:
  mail:
    host: smtp.example.com
    port: 587
    username: ${SMTP_USERNAME}
    password: ${SMTP_PASSWORD}
    default-encoding: UTF-8
    properties:
      "[mail.smtp.auth]": true
      "[mail.smtp.starttls.enable]": true
      "[mail.smtp.starttls.required]": true
      "[mail.smtp.connectiontimeout]": 5000
      "[mail.smtp.timeout]": 10000
      "[mail.smtp.writetimeout]": 10000
```

Dotted keys under `spring.mail.properties` are Jakarta Mail properties; bracket notation in YAML preserves them as intact map keys.

### Using the Boot-created bean

Once Boot provides the sender bean, services only need dependency injection:

```java
package example.mail;

import org.springframework.mail.javamail.JavaMailSender;
import org.springframework.stereotype.Service;

@Service
public class WelcomeMailService {
    private final JavaMailSender mailSender;

    public WelcomeMailService(JavaMailSender mailSender) {
        this.mailSender = mailSender;
    }

    // Email-sending methods using mailSender go here.
}
```

There is no need to write `new JavaMailSenderImpl()` in each service. Nor is `@Scope("singleton")` needed: singleton is already the default scope for Spring beans.

## 4. Two services sharing one sender while building independent emails

Let's build two workflows: sending registration confirmation in plain text and sending an invoice in HTML.

### Plain-text sending service

```java
package example.mail;

import org.springframework.mail.SimpleMailMessage;
import org.springframework.mail.javamail.JavaMailSender;
import org.springframework.stereotype.Service;

@Service
public class AccountMailService {
    private final JavaMailSender mailSender;

    public AccountMailService(JavaMailSender mailSender) {
        this.mailSender = mailSender;
    }

    public void sendWelcome(String recipient, String displayName) {
        SimpleMailMessage mail = new SimpleMailMessage();
        mail.setFrom("no-reply@example.com");
        mail.setTo(recipient);
        mail.setSubject("Welcome");
        mail.setText("Hello " + displayName + "!\n"
                + "Your account has been created successfully.");

        mailSender.send(mail);
    }
}
```

Here, every call to `sendWelcome` creates a **new** `SimpleMailMessage`. The sender is a shared bean, while the object holding recipient and content belongs to that specific send.

### HTML sending service

```java
package example.mail;

import jakarta.mail.MessagingException;
import jakarta.mail.internet.MimeMessage;
import java.nio.charset.StandardCharsets;
import org.springframework.mail.javamail.JavaMailSender;
import org.springframework.mail.javamail.MimeMessageHelper;
import org.springframework.stereotype.Service;

@Service
public class InvoiceMailService {
    private final JavaMailSender mailSender;

    public InvoiceMailService(JavaMailSender mailSender) {
        this.mailSender = mailSender;
    }

    public void sendInvoiceNotice(String recipient, String invoiceId)
            throws MessagingException {
        MimeMessage message = mailSender.createMimeMessage();

        MimeMessageHelper helper = new MimeMessageHelper(
                message, true, StandardCharsets.UTF_8.name());
        helper.setFrom("billing@example.com");
        helper.setTo(recipient);
        helper.setSubject("Your Invoice");

        String plain = "Invoice " + invoiceId
                + " is ready.\nView at https://example.com/invoices";

        String html = """
                <!doctype html>
                <html lang="en">
                  <body>
                    <h1>Invoice is ready</h1>
                    <p>Sign in to view your invoice in your account.</p>
                    <a href="https://example.com/invoices">View invoice</a>
                  </body>
                </html>
                """;

        helper.setText(plain, html);
        mailSender.send(message);
    }
}
```

The constructor `MimeMessageHelper(message, true, "UTF-8")` enables multipart mode so both plain-text and HTML versions can be supplied. If HTML uses dynamic data such as names, amounts, or invoice IDs, use a template engine with context-aware escaping instead of interpolating untrusted data into raw HTML.

### Sharing boundary

The two services above share:

- The same `JavaMailSender` and its connection parameters.
- The same TLS, authentication, and SMTP timeout rules.
- The same submission path to the configured SMTP relay.

They **do not share**:

- `SimpleMailMessage` or `MimeMessage`.
- Each email's recipients, subject, body, or attachments.
- Retry state or business metadata for individual sends.

If each notification type needs a different `From` address, each message can set its own **as long as the SMTP provider allows those addresses**. Sharing one sender bean does not automatically grant permission to send on behalf of arbitrary domains.

## 5. Manual `@Bean` declaration when not using auto-configuration

With plain Spring Framework or when a specialized SMTP setup is needed, you can declare the bean in a `@Configuration` class:

```java
package example.mail;

import java.util.Properties;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.mail.javamail.JavaMailSender;
import org.springframework.mail.javamail.JavaMailSenderImpl;

@Configuration
public class MailConfiguration {

    @Bean
    public JavaMailSender javaMailSender() {
        JavaMailSenderImpl sender = new JavaMailSenderImpl();
        sender.setHost("smtp.example.com");
        sender.setPort(587);
        sender.setUsername(System.getenv("SMTP_USERNAME"));
        sender.setPassword(System.getenv("SMTP_PASSWORD"));
        sender.setDefaultEncoding("UTF-8");

        Properties properties = new Properties();
        properties.put("mail.smtp.auth", "true");
        properties.put("mail.smtp.starttls.enable", "true");
        properties.put("mail.smtp.starttls.required", "true");
        properties.put("mail.smtp.connectiontimeout", "5000");
        properties.put("mail.smtp.timeout", "10000");
        properties.put("mail.smtp.writetimeout", "10000");

        sender.setJavaMailProperties(properties);
        return sender;
    }
}
```

Spring invokes the `javaMailSender()` factory method to create the bean, then manages the instance in `ApplicationContext`. Services simply use constructor injection as before.

Do not rely on Boot auto-configuration while simultaneously adding a manual bean unintentionally: once a suitable bean exists, Boot's mail auto-configuration generally backs off in favor of the application-supplied bean. As a result, `spring.mail.*` values may not take effect if the manual bean does not read them.

### Why not instantiate the sender directly inside a service method?

Do not turn a service into a sender factory:

```java
// Avoid this:
public void sendSomething() {
    JavaMailSenderImpl sender = new JavaMailSenderImpl();
    sender.setHost("smtp.example.com");
    // ...
    sender.send(message);
}
```

This duplicates configuration, makes dependencies hard to replace in tests, and causes drift across features. Use constructor injection so Spring manages the instance and lifecycle.

## 6. Lifecycle and stability of a shared bean

At application startup, Spring instantiates beans according to configuration needs and dependencies. `JavaMailSenderImpl` holds the sending settings: SMTP host, port, username/password, Jakarta Mail properties, and a `Session` created or supplied by configuration.

It is a long-lived bean, **not per-send transient state**.

### Keep configuration immutable after startup

A vital practice is treating `JavaMailSenderImpl` properties as **immutable after the bean has been initialized**.

Example of what NOT to do when multiple threads are sending:

```java
// Avoid mutating a shared sender per request:
JavaMailSenderImpl sender = (JavaMailSenderImpl) mailSender;
sender.setHost(request.getSmtpHost());
sender.setUsername(request.getUsername());
sender.setPassword(request.getPassword());
sender.send(message);
```

If request A changes the host and then request B changes the username before A calls `send`, an email can go out through the wrong account or server. This is both a race condition and a cross-tenant data-leak risk.

The solution is to:

- Lock down each sender bean's configuration when building `ApplicationContext`.
- Create a fresh email object for every send.
- If the application needs multiple concurrent SMTP configurations, create **multiple clearly distinguished sender beans** or a lifecycle-managed per-tenant factory/pool.
- When credential rotation is needed, use a controlled sender recreation/reconfiguration process instead of calling setters on an instance actively serving concurrent requests.

### Is `Session` "an email currently being sent"?

No. `jakarta.mail.Session` holds configuration and provider infrastructure for Jakarta Mail; each `MimeMessage` is its own object. In `JavaMailSenderImpl`, the session can be created or supplied and reused. However, a shared `Session` **does not mean messages or network connections are shared**.

A message should follow this lifecycle:

```text
Service method called
      |
      v
createMimeMessage()
      |
      v
MimeMessageHelper sets content/headers
      |
      v
mailSender.send(message)
      |
      v
Message is no longer modified by the service
```

Never store a `MimeMessage` in a field of a singleton service to edit and reuse across multiple recipients.

## 7. Can a singleton sender be called from multiple threads?

In standard Spring architecture, `JavaMailSenderImpl` is used as **a singleton bean with fixed configuration**, and multiple services/requests can call `send`. The key is distinguishing the sender's stability from the thread-safety of other objects:

| Component | Recommended usage |
| --- | --- |
| Configured-once `JavaMailSender` | Inject and share across multiple services |
| `JavaMailSenderImpl` and `Properties` | Never mutate host, credentials, session, or properties while sending |
| `SimpleMailMessage` | Create a new one per email or use an independent copy |
| `MimeMessage` | Create a new one per send; never modify concurrently |
| `MimeMessageHelper` | Create a new one per `MimeMessage` |
| Mutable template data/model | Use a per-request object; never mutate shared data |
| Retry state / recipient list | Store per delivery/attempt, not in a mutable singleton field |

### A singleton does not limit concurrent SMTP sessions

If 100 requests call `mailSender.send(...)` simultaneously, having **one sender bean** does not mean the application opens only **one connection** or automatically has a 100-item queue. The library and send calls can open multiple concurrent connections/transports.

Consequences to plan for:

- SMTP providers enforce connection, messages-per-minute, or recipient limits.
- Every connect and TLS handshake consumes CPU, network, and latency.
- Blocking socket reads/writes can tie up threads for extended periods.
- Enabling `mail.smtp.writetimeout` in some Jakarta Mail implementations incurs extra per-connection scheduling overhead.
- During widespread network failures, uncontrolled retries can cause overload.

To control load, introduce a queue/worker pool with bounded concurrency and a retry/backoff policy. That throttling **belongs to the mail-sending architecture**, not automatically to singleton bean scope.

## 8. Constructor dependency injection: reasons and rules

Constructor injection is the most controllable pattern when services have required dependencies:

```java
@Service
public class PasswordResetMailService {
    private final JavaMailSender mailSender;
    private final MailTemplateRenderer renderer;

    public PasswordResetMailService(
            JavaMailSender mailSender,
            MailTemplateRenderer renderer) {
        this.mailSender = mailSender;
        this.renderer = renderer;
    }
}
```

Benefits:

1. Dependencies are explicit; a service cannot be constructed incomplete without its sender/renderer.
2. Easy to swap `JavaMailSender` for a mock or fake in unit tests.
3. Fields can be `final`, preventing runtime dependency mutation.
4. The service focuses on content and business rules instead of owning SMTP setup.
5. When there is a single constructor, Spring uses it for injection without needing `@Autowired` in modern Spring versions.

Across multiple services, if they all share common logic like formatting sender names, timing sends, or mapping errors, you can introduce a shared email gateway/adapter. Even then, that class should **receive `JavaMailSender` via constructor**, rather than creating a new sender itself.

### Should you inject `JavaMailSenderImpl` directly?

For example:

```java
private final JavaMailSenderImpl sender;
```

This couples the service to the concrete implementation and creates a temptation to mutate host/password from business code. When a service only needs to send mail, depend on `JavaMailSender`. Only configuration/infrastructure layers that genuinely need `JavaMailSenderImpl`-specific APIs should work with the concrete type.

## 9. `MimeMessagePreparator` and sharing a sender per send

When using HTML, templates, or complex MIME, `MimeMessagePreparator` lets you prepare a message via a callback. It is a clean way to keep each message scoped to a single call:

```java
package example.mail;

import org.springframework.mail.javamail.JavaMailSender;
import org.springframework.mail.javamail.MimeMessageHelper;
import org.springframework.stereotype.Service;

@Service
public class NewsMailService {
    private final JavaMailSender mailSender;

    public NewsMailService(JavaMailSender mailSender) {
        this.mailSender = mailSender;
    }

    public void sendNews(String recipient) {
        mailSender.send(mimeMessage -> {
            MimeMessageHelper helper = new MimeMessageHelper(
                    mimeMessage, "UTF-8");
            helper.setFrom("news@example.com");
            helper.setTo(recipient);
            helper.setSubject("New Update");
            helper.setText(
                    "<h2>Latest News</h2><p>Check updates in your account.</p>",
                    true
            );
        });
    }
}
```

The `send(MimeMessagePreparator)` overload asks the library to supply a `MimeMessage` to the callback. Spring handles creation and sending; if preparation fails, exceptions are translated through Spring Mail's mechanism. Never retain a reference to `mimeMessage` after the callback finishes to mutate it on another thread.

If both plain-text and HTML versions are needed, create the helper in multipart mode and call `helper.setText(plain, html)`. Attachments also require multipart mode. The sender bean stays unchanged regardless of message structure.

## 10. Multiple SMTP accounts: when are multiple beans needed?

"One shared bean" is a good default **when the entire application shares one SMTP configuration**. Some systems have legitimately different needs:

- Transactional email via provider A, newsletters via provider B.
- Multi-tenant sending with separate credentials/domains.
- An internal relay for technical alerts, a public ESP for end users.
- Rate limits/load and sender reputation isolation across email categories.

In those cases, define multiple `JavaMailSender` beans with clear names/`@Qualifier` annotations. Example:

```java
package example.mail;

import java.util.Properties;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.mail.javamail.JavaMailSender;
import org.springframework.mail.javamail.JavaMailSenderImpl;

@Configuration
public class MultiSmtpConfiguration {

    @Bean("transactionalMailSender")
    public JavaMailSender transactionalMailSender() {
        return createSender(
                "smtp-transactional.example.com",
                587,
                System.getenv("SMTP_TRANSACTIONAL_USER"),
                System.getenv("SMTP_TRANSACTIONAL_PASSWORD"));
    }

    @Bean("campaignMailSender")
    public JavaMailSender campaignMailSender() {
        return createSender(
                "smtp-campaign.example.com",
                587,
                System.getenv("SMTP_CAMPAIGN_USER"),
                System.getenv("SMTP_CAMPAIGN_PASSWORD"));
    }

    private static JavaMailSender createSender(
            String host, int port, String user, String password) {
        JavaMailSenderImpl sender = new JavaMailSenderImpl();
        sender.setHost(host);
        sender.setPort(port);
        sender.setUsername(user);
        sender.setPassword(password);
        sender.setDefaultEncoding("UTF-8");

        Properties properties = new Properties();
        properties.put("mail.smtp.auth", "true");
        properties.put("mail.smtp.starttls.enable", "true");
        properties.put("mail.smtp.starttls.required", "true");
        properties.put("mail.smtp.connectiontimeout", "5000");
        properties.put("mail.smtp.timeout", "10000");
        properties.put("mail.smtp.writetimeout", "10000");
        sender.setJavaMailProperties(properties);

        return sender;
    }
}
```

Inject the right bean by business role:

```java
package example.mail;

import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.mail.javamail.JavaMailSender;
import org.springframework.stereotype.Service;

@Service
public class CampaignMailService {
    private final JavaMailSender mailSender;

    public CampaignMailService(
            @Qualifier("campaignMailSender") JavaMailSender mailSender) {
        this.mailSender = mailSender;
    }
}
```

If Spring finds **multiple beans of type `JavaMailSender`** and an injection point does not disambiguate, startup can fail with `NoUniqueBeanDefinitionException` or a matching autowire error. Fix this with `@Qualifier`, marking one bean `@Primary` when there is a clear default, or designing an explicit factory/registry.

Hardcoding two beans directly above only illustrates the mechanism. In larger applications, extract host, port, username, password, and timeouts into validated configuration rather than repeating them across methods.

### Why not create a separate bean per request?

If each HTTP request supplies a new SMTP host or credential, creating unbounded singleton beans per request does not fit Spring's model. You can build a per-tenant client/transport management service, accounting for:

- Each tenant's authorization to use sender credentials.
- Policies for storing and refreshing secrets.
- Connection quotas and active tenant counts.
- Resource lifecycle, memory, and cleanup.
- Never mutating one shared sender's config between two tenants.
- Never letting requests pick arbitrary SMTP hosts, which risks SSRF or unintended network access.

Complex multi-tenant setups need dedicated architecture; never solve them by calling `setHost`/`setPassword` on a concurrently used singleton.

## 11. Sharing a sender does not mean sharing a From address

A `JavaMailSender` bean is not permanently tied to one displayed sender address. Distinguish two configuration groups:

- **SMTP account/transport**: host, port, username, password, TLS, timeouts.
- **Email content**: `From`, `To`, `Reply-To`, `Subject`, body, attachments.

For instance, two services sharing one sender can set different `From` addresses. However, the SMTP provider may require `From` addresses or domains to be verified or authorized. Violating this can cause the server to reject the mail, rewrite the sender, or cause receivers to flag the message as suspicious.

`Reply-To` also does not replace the SMTP username or bounce address. Choosing the sending domain affects SPF, DKIM, DMARC, and deliverability, so it must be managed at configuration/deployment level rather than merely changing a string in `SimpleMailMessage`.

One clean organization is configuring sender addresses per notification type and injecting them into services:

```properties
app.mail.from.account=no-reply@example.com
app.mail.from.billing=billing@example.com
```

These are **project-defined application properties**, not built-in Spring Boot defaults. The application can read them via `@ConfigurationProperties` or `@Value` and apply them when building each message.

## 12. Sending mail from HTTP threads and asynchronous processing

`JavaMailSender#send(...)` in standard SMTP usage is a **blocking call**: the calling thread waits until submission finishes or fails. A singleton bean does not turn `send` into a background task.

For example, a request calling directly:

```text
HTTP POST /orders
      |
      v
OrderService.createOrder()
      |
      +--> persist order
      |
      +--> mailSender.send()
               |
               +--> TCP connect / TLS / AUTH / DATA
      |
      v
HTTP response
```

If SMTP is slow or times out, the HTTP request stalls as well. For transaction-coupled notifications, consider a queue or **transactional outbox**:

```text
HTTP request
     |
     v
Business Service
     |
     +--> Persist business data + outbox record
     |    in the same transaction
     |
     v
HTTP response
     |
     v
Background Worker
     |
     +--> JavaMailSender singleton bean
     |    (on this app/worker instance)
     |
     v
SMTP relay / ESP
     |
     v
Delivered/bounced webhooks if supported by provider
```

In this architecture:

1. The business service records the send request.
2. The worker picks up each delivery job, builds a new message, and uses the injected sender bean.
3. The worker bounds concurrency, retries with backoff, and records attempts.
4. The system tracks submission state separately from delivered/bounced states.

If mail is sent synchronously inside a transaction that later rolls back, the email may **already have left the system** while business data was never committed. An outbox avoids this state divergence when implemented properly.

### Does `@Async` replace an outbox?

You can annotate a method with `@Async` in a Spring-managed bean to offload sending to an executor, provided `@EnableAsync` is enabled and an appropriate executor is configured. Internal self-invocation via `this.someAsyncMethod()` typically bypasses the Spring proxy and may not execute asynchronously as expected.

`@Async` does not persist unsent emails across process restarts; a durable outbox or queue is better for notifications that must not be lost. Whether sending synchronously or asynchronously, socket timeouts and retry controls remain necessary.

## 13. Centralizing error handling in one place

Sharing a bean unifies SMTP configuration, yet it does not automatically unify error-handling policy. Depending on architecture, you can introduce an adapter wrapping `JavaMailSender` for business services to call.

Example:

```java
package example.mail;

import org.springframework.mail.MailException;
import org.springframework.mail.SimpleMailMessage;
import org.springframework.mail.javamail.JavaMailSender;
import org.springframework.stereotype.Component;

@Component
public class EmailGateway {
    private final JavaMailSender sender;

    public EmailGateway(JavaMailSender sender) {
        this.sender = sender;
    }

    public void sendPlainText(
            String from, String to, String subject, String body) {
        SimpleMailMessage message = new SimpleMailMessage();
        message.setFrom(from);
        message.setTo(to);
        message.setSubject(subject);
        message.setText(body);

        try {
            sender.send(message);
        } catch (MailException exception) {
            // Here you can log attempt ID, error type, and timestamp.
            // Avoid logging passwords, OTPs, or full emails.
            throw exception;
        }
    }
}
```

This is an example infrastructure boundary. The adapter can add metrics, error classification, and correlation IDs as needed. When business domains format content differently, avoid cramming all emails into a single `sendPlainText` method; add MIME methods or separate rendering collaborators.

### Error categories to anticipate

| Issue group | Symptom | Handling direction |
| --- | --- | --- |
| SMTP connectivity | Connect/read/write timeout, connection refused | Check network, timeouts, and bounded retries |
| Authentication | Invalid credentials or SMTP policy rejection | Fix secrets/sending rights; do not retry blindly |
| Content/headers | Invalid email, MIME, or address | Validate data and fix message construction |
| Provider policy | Rate limit, unverified sender, recipient limit | Follow ESP policy and adjust configuration |
| Uncertain send outcome | Timeout after sending DATA yet before confirmation | Reconcile before retrying to reduce duplicates |
| Post-submission delivery | Bounce, deferred, spam filtering | Monitor ESP events; do not infer from `send()` |

A `sender.send(message)` call succeeding usually only confirms the SMTP relay accepted the submission within that connection scope. **You cannot conclude the email reached the inbox or was read**.

## 14. Testing services enabled by dependency injection

A practical advantage of sharing a bean via an interface is that **unit tests need no SMTP server**. You can pass a mock `JavaMailSender` into the constructor and verify the generated content.

Example using JUnit Jupiter and Mockito for `AccountMailService` from section 4:

```java
package example.mail;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.mock;

import org.junit.jupiter.api.Test;
import org.mockito.ArgumentCaptor;
import org.springframework.mail.SimpleMailMessage;
import org.springframework.mail.javamail.JavaMailSender;

class AccountMailServiceTest {

    @Test
    void sendsWelcomeMessage() {
        JavaMailSender sender = mock(JavaMailSender.class);
        AccountMailService service = new AccountMailService(sender);

        service.sendWelcome("user@example.net", "An");

        ArgumentCaptor<SimpleMailMessage> captor =
                ArgumentCaptor.forClass(SimpleMailMessage.class);
        verify(sender).send(captor.capture());

        SimpleMailMessage sent = captor.getValue();
        assertEquals("no-reply@example.com", sent.getFrom());
        assertEquals("Welcome", sent.getSubject());
        assertEquals("user@example.net", sent.getTo()[0]);
        assertEquals(
            "Hello An!\nYour account has been created successfully.",
            sent.getText()
        );
    }
}
```

The test above only verifies how the service constructs and passes a `SimpleMailMessage` to the sender. It **does not test real SMTP connectivity**, TLS, credentials, or mailbox delivery.

For MIME messages, you can use a fake/mock `JavaMailSender` or dedicated MIME inspection utilities to check headers, bodies, and attachments. An integration test can configure `JavaMailSender` against **a local test SMTP server** to verify real SMTP exchange without emailing actual users.

### Splitting test levels

| Level | Goal | Suggestion |
| --- | --- | --- |
| Service unit test | Verify To/From/Subject, template choice, and content | Mock the `JavaMailSender` interface |
| Component test | Verify bean configuration and sender selection | Boot a Spring test context |
| Integration test | Verify real SMTP/MIME exchange | Local test SMTP server, test configuration |
| End-to-end / production monitoring | Verify delivery, bounces, and provider policies | ESP webhooks, dashboards, and controlled test emails |

Never let unit tests depend on network calls or production credentials. Spring having a singleton bean does not guarantee the SMTP server is available; other test and monitoring levels must verify that.

## 15. Common bean configuration errors

| Symptom | Common cause | How to resolve |
| --- | --- | --- |
| `NoSuchBeanDefinitionException` for `JavaMailSender` | Missing dependency, unmet auto-configuration condition, or config not scanned | Check starter, `spring.mail.host`, context, and `@Bean` declarations |
| `NoUniqueBeanDefinitionException` | Multiple sender beans of the same type | Use `@Qualifier` or intentional `@Primary` |
| Service sees `mailSender` as `null` | Service instantiated via `new` without passing dependency, or not Spring-managed | Use constructor injection and let Spring manage beans |
| Settings in `application.properties` have no effect | Custom `JavaMailSender` bean suppressed auto-configuration, or wrong profile | Inspect which bean is created and actual active config |
| Email type A sends fine while type B is rejected | `From` outside allowed domain, attachment too large, or ESP policy | Check message and provider rules |
| Concurrent sends throttled | Provider limits connections/rate; too many workers | Add queue, concurrency cap, backoff |
| Message contents from different requests mix together | Reusing mutable `MimeMessage`/`SimpleMailMessage` across threads | Create a new message for every delivery |
| Errors persist after password change | Secret not updated in running instances/config | Design secret rotation and controlled sender reinitialization |
| HTTP requests slow down due to SMTP | `send()` called synchronously | Use worker/outbox/queue per business requirements |
| Tests accidentally send real emails | Unit tests use production bean or real SMTP config | Inject mock/fake; isolate SMTP tests |

### Special considerations with multiple replicas

Suppose the application runs across three pods. Inside each pod, Spring holds one `JavaMailSender` singleton. That means there are actually **three sender instances**, and all three can send concurrently to the same ESP.

If a provider allows 20 connections/second or a specific rate limit, a thread pool cap inside **one pod** may not bound total load. Account for shared quotas, centralized queues, worker scaling, and throttling retries.

Also, if all three pods read the same outbox without proper claim/lock semantics, they may send duplicate notifications. That belongs to delivery job coordination and cannot be solved by singleton scope.

## 16. Practices for safe and maintainable configuration

A shared sender bean should be treated as an **infrastructure gateway** for the application, standardizing several elements:

1. **Keep configuration outside source code**: use environment variables, a secret manager, or deployment config for host, credentials, and timeouts.
2. **Match provider TLS requirements**: for STARTTLS, enable `mail.smtp.starttls.enable` and `required` when policy mandates encryption; for implicit TLS, use matching config.
3. **Never log secret data**: avoid printing passwords, verification codes, email bodies, access tokens, or unnecessary recipient data.
4. **Set clear timeouts**: configure connect/read/write timeouts with realistic values; do not treat them as total send deadlines.
5. **Control throughput**: queues, worker pools, provider quotas, backoff, and backlog monitoring.
6. **Observe each send**: delivery ID, attempt ID, message type, sender profile, timestamp, error type, and sanitized SMTP diagnostics.
7. **Separate submission from delivery**: use ESP webhooks/events if you need delivered, bounced, or post-relay statuses.
8. **Enforce domain sending permissions**: one bean can set different `From` headers per message, yet the sender account must still be authorized by the provider.
9. **Create messages per invocation**: never store `MimeMessage`, attachment streams, or recipient state in mutable fields of a singleton service.
10. **Keep the interface as the dependency**: services depend on `JavaMailSender`, while `JavaMailSenderImpl` and SMTP properties stay in the configuration layer.

### Example directory organization

A clean structure could look like:

```text
src/main/java/example/
├── config/
│   └── MailConfiguration.java       (if manual config is needed)
├── mail/
│   ├── EmailGateway.java            (shared sending adapter, architecture-dependent)
│   ├── AccountMailService.java      (registration emails)
│   ├── InvoiceMailService.java      (invoice emails)
│   └── MailTemplateRenderer.java    (template rendering)
└── order/
    └── OrderService.java            (core business logic)

src/main/resources/
├── application.properties
└── templates/mail/
    ├── welcome.html
    └── invoice.html
```

With Spring Boot auto-configuration, **`MailConfiguration.java` may not even be needed**. That is a key benefit: the dependency and properties suffice to provide a shared sender bean. Services focus on content and business workflows instead of building network plumbing.

## 17. A complete implementation flow

Suppose the requirement is "a Spring app sends registration and invoice emails using one shared SMTP account."

**Step 1:** Add `spring-boot-starter-mail`, declare `spring.mail.*`, and supply credentials via environment secrets.

**Step 2:** Let Boot create `JavaMailSender` when auto-configuration conditions are met; avoid instantiating senders inside individual services.

**Step 3:** Implement `AccountMailService` and `InvoiceMailService`, injecting `JavaMailSender` via constructor. Create a new message per call.

**Step 4:** Set `From`, `Reply-To`, charset, subject, and body for each email type; verify sender addresses are authorized by the ESP.

**Step 5:** For less critical emails, decide whether synchronous sending is acceptable; for critical transactional emails, consider an outbox + worker to decouple SMTP from HTTP transactions.

**Step 6:** Write unit tests for email logic using the mocked interface and integration tests against a test SMTP server. Monitor deliveries/bounces from the ESP in production.

**Step 7:** If another provider is needed later, add a clearly qualified config/bean or design a sender registry; never mutate host and credentials on a singleton bean serving live requests.

The essence of **`JavaMailSender` as a shared bean** is **sharing the Spring-managed email configuration and sending component**. Messages themselves remain independently instantiated and processed per delivery. Keeping that boundary crisp makes the application easy to test, easy to swap SMTP providers, and scalable for concurrent email sending without mixing state across recipients.
