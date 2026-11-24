# Session, Transport, and Related Jakarta Mail Objects

When building email-sending features with **Spring Framework Mail**, we usually start from `JavaMailSender`. Beneath Spring's API layer lies **Jakarta Mail**, the library providing the core objects to configure the mail environment, construct messages, open connections to sending/receiving servers, and exchange data over the appropriate protocols.

The two names that appear most often are **`Session`** and **`Transport`**. `Session` holds configuration and creates required objects; `Transport` handles connecting and sending messages. Alongside them are `Message`, `MimeMessage`, `Address`, `Authenticator`, `Store`, `Folder`, and MIME types.

Understanding the role of each object helps you read Spring Mail code, configure SMTP manually when needed, distinguish message-construction errors from network errors, and understand why creating a `Session` does not create an SMTP session every time.

## 1. Big Picture: How Do the Classes Collaborate?

Jakarta Mail is an email API that typically requires an **implementation/provider** to communicate over protocols such as SMTP, IMAP, or POP3. In a typical Spring application using SMTP:

```text
Application service
      |
      v
Spring JavaMailSender
      |
      v
Spring JavaMailSenderImpl
      |
      +-------------------------------------+
      | Jakarta Mail                        |
      |                                     |
      | Session (configuration, factory)    |
      |    |                                |
      |    +--> MimeMessage (message body)  |
      |    |       +--> Address             |
      |    |       +--> Multipart/BodyPart  |
      |    |                                |
      |    +--> Transport (connect, send)   |
      |             |                       |
      +-------------|-----------------------+
                    |
                    v
                SMTP server
                    |
                    v
          Mail sending/receiving infra
```

To **read emails**, Jakarta Mail also has another path:

```text
Session
   |
   +--> Store (IMAP / POP3)
            |
            +--> Folder
                     |
                     +--> Message / MimeMessage
```

Thus, `Session` is the shared starting point; **`Transport` is used for sending**, while **`Store` and `Folder` are used for retrieving messages from a mailbox store**.

| Object | Typical Java package | Primary role |
|---|---|---|
| `Session` | `jakarta.mail.Session` | Holds properties, authenticator, debug settings, and provides factories to obtain protocol components. |
| `Transport` | `jakarta.mail.Transport` | Sends email to a server through a provider, usually SMTP. |
| `Store` | `jakarta.mail.Store` | Connects to and accesses mailboxes on a server, usually via IMAP or POP3. |
| `Folder` | `jakarta.mail.Folder` | Represents a folder/mailbox such as `INBOX`; provides operations to fetch messages. |
| `Message` | `jakarta.mail.Message` | Abstract type for an email message containing sender, recipients, subject, and body. |
| `MimeMessage` | `jakarta.mail.internet.MimeMessage` | MIME/RFC Internet mail message implementation, commonly used for SMTP sending. |
| `Address` / `InternetAddress` | `jakarta.mail.Address` / `jakarta.mail.internet.InternetAddress` | Address model, specifically Internet email addresses. |
| `Authenticator` / `PasswordAuthentication` | `jakarta.mail.*` | Supplies credentials when a provider requires login. |
| `Multipart` / `BodyPart` | `jakarta.mail.*` | Groups multiple content parts of an email. |
| `MimeMultipart` / `MimeBodyPart` | `jakarta.mail.internet.*` | MIME implementations for creating HTML, inline images, and attachments. |
| `MessagingException` | `jakarta.mail.MessagingException` | Checked exception family for message/connection handling at the Jakarta Mail layer. |

These objects can collaborate in a single sending flow, yet **each type manages a distinct scope of responsibility**.

## 2. Session: Configuration Context of Jakarta Mail

### 2.1. What Is Session?

`Session` collects the parameters Jakarta Mail uses to create email components. It can hold:

- **Properties** specifying host, port, protocol, timeouts, TLS, authentication, and provider options.
- **Authenticator** providing login credentials when required by the provider.
- Debug settings and registered provider metadata.
- Factory methods such as `getTransport(...)` and `getStore(...)` to obtain protocol-handling objects.

Point to distinguish:

> **`jakarta.mail.Session` is not an open TCP/SMTP connection.** Creating a `Session` sends no SMTP commands, performs no server authentication, and does not guarantee that the server exists or is reachable.

The name `Session` here also does not mean a user HTTP session or a web login session.

### 2.2. Creating a Session with Properties

Example using Jakarta Mail directly:

```java
import jakarta.mail.Authenticator;
import jakarta.mail.PasswordAuthentication;
import jakarta.mail.Session;
import java.util.Properties;

public class MailSessionFactory {

    public static Session create(String username, String password) {
        Properties properties = new Properties();
        properties.put("mail.transport.protocol", "smtp");
        properties.put("mail.smtp.host", "smtp.example.com");
        properties.put("mail.smtp.port", "587");
        properties.put("mail.smtp.auth", "true");
        properties.put("mail.smtp.starttls.enable", "true");
        properties.put("mail.smtp.starttls.required", "true");
        properties.put("mail.smtp.connectiontimeout", "5000");
        properties.put("mail.smtp.timeout", "5000");
        properties.put("mail.smtp.writetimeout", "5000");

        return Session.getInstance(properties, new Authenticator() {
            @Override
            protected PasswordAuthentication getPasswordAuthentication() {
                return new PasswordAuthentication(username, password);
            }
        });
    }
}
```

In the example:

1. `Properties` describes how the client connects to the server.
2. `Session.getInstance(...)` creates a `Session` object with the given properties and authenticator.
3. `Authenticator` is invoked by the provider when credentials are needed; `PasswordAuthentication` only holds login credentials, not TLS or data-transmission logic.
4. An SMTP connection starts only when a `Transport` connects or a higher-level send operation opens a connection for the application.

`username` and `password` should be loaded from environment variables or a secrets management system. Avoid hardcoding credentials in repositories and avoid writing AUTH details to logs.

### 2.3. getInstance vs. getDefaultInstance

Jakarta Mail offers multiple ways to obtain a `Session`:

```java
Session sessionA = Session.getInstance(properties, authenticator);

Session sessionB = Session.getInstance(properties);

Session sharedDefault = Session.getDefaultInstance(properties);
```

`getInstance(...)` creates a `Session` from the passed arguments. `getDefaultInstance(...)` works with a **shared default Session** at the runtime environment level; subsequent calls may return an already-initialized Session instead of applying new properties.

In Spring applications with multiple accounts, multiple SMTP providers, or multiple configuration sets, it is usually better to use an explicitly configured Session per sending profile rather than relying on the global default Session. Use `getDefaultInstance` only when you understand its impact on shared configuration.

### 2.4. Is Session Thread-Safe?

`Session` is commonly used as a **reusable configuration object** at application scope. You do not need to create a new Session for every email. However, do not treat **`MimeMessage`, `Transport`, or `Folder`** as objects that multiple threads can mutate arbitrarily at the same time.

Common design:

- Reuse the `Session` configuration or `JavaMailSender` bean.
- Create a separate `MimeMessage` for each message.
- Manage `Transport` connection lifecycles per send operation or via a clearly designed sending component.
- Avoid mutating shared `Properties` and message objects across multiple workers during sending.

## 3. Transport: The Object That Performs Sending

### 3.1. What Is Transport?

`Transport` is Jakarta Mail's abstract class for **sending messages**. Under typical configurations, the SMTP implementation is responsible for:

- Connecting to the SMTP server.
- Negotiating the protocol and required extensions.
- Enabling TLS and authenticating if required by configuration.
- Transmitting the message envelope and email body.
- Reading server responses and reporting errors back to the application.
- Closing the connection upon completion.

Relationship:

```text
Session
  |
  | getTransport("smtp")
  v
Transport (disconnected)
  |
  | connect(...)
  v
Transport (connected)
  |
  | sendMessage(message, recipients)
  v
SMTP server responds
  |
  | close()
  v
Transport (closed)
```

**Do not confuse `Transport` with `Message`:** `Message` holds content and headers; `Transport` is the channel that transmits that content.

### 3.2. Two Ways to Send in Jakarta Mail

Jakarta Mail has two common styles:

**Approach A: static `Transport.send(...)` method**

```java
Transport.send(message);
```

With this approach, Jakarta Mail runs necessary message preparation steps (including `saveChanges()`), connects, sends, and closes the connection according to provider mechanics. This is simple for a single message when the Session already has suitable configuration and credentials.

**Approach B: obtain a Transport and manage its lifecycle**

```java
Transport transport = session.getTransport("smtp");
try {
    transport.connect(host, username, password);
    message.saveChanges();
    transport.sendMessage(message, message.getAllRecipients());
} finally {
    transport.close();
}
```

In the second approach, the application explicitly controls **when to connect and close**, allowing one Transport to execute multiple `sendMessage(...)` calls in the same session if supported by the provider and application. Unlike the static method, calling `sendMessage(...)` on an instance **does not automatically guarantee `saveChanges()` is called for you**; prepare the message beforehand.

Do not reuse a closed `Transport` object or share a connected Transport across multiple concurrent sending threads without proper synchronization.

### 3.3. Example Sending Email with Plain Jakarta Mail

The snippet below illustrates the full path from `Session` to `Transport`, without requiring Spring. It uses the Jakarta Mail API and an SMTP-capable implementation at runtime:

```java
import jakarta.mail.Authenticator;
import jakarta.mail.Message;
import jakarta.mail.MessagingException;
import jakarta.mail.PasswordAuthentication;
import jakarta.mail.Session;
import jakarta.mail.Transport;
import jakarta.mail.internet.InternetAddress;
import jakarta.mail.internet.MimeMessage;
import java.util.Properties;

public class PlainJakartaMailExample {

    public static void main(String[] args) throws MessagingException {
        String host = "smtp.example.com";
        String username = System.getenv("SMTP_USERNAME");
        String password = System.getenv("SMTP_PASSWORD");

        if (username == null || password == null) {
            throw new IllegalStateException("Missing SMTP configuration");
        }

        Properties props = new Properties();
        props.put("mail.smtp.host", host);
        props.put("mail.smtp.port", "587");
        props.put("mail.smtp.auth", "true");
        props.put("mail.smtp.starttls.enable", "true");
        props.put("mail.smtp.starttls.required", "true");
        props.put("mail.smtp.connectiontimeout", "5000");
        props.put("mail.smtp.timeout", "5000");
        props.put("mail.smtp.writetimeout", "5000");

        Session session = Session.getInstance(props, new Authenticator() {
            @Override
            protected PasswordAuthentication getPasswordAuthentication() {
                return new PasswordAuthentication(username, password);
            }
        });

        MimeMessage message = new MimeMessage(session);
        message.setFrom(new InternetAddress("no-reply@example.com"));
        message.setRecipient(
            Message.RecipientType.TO,
            new InternetAddress("alice@example.net")
        );
        message.setSubject("Registration confirmation", "UTF-8");
        message.setText(
            "Hello!\nYour account has been created.",
            "UTF-8"
        );

        // Prepare MIME headers before sending via the Transport instance.
        message.saveChanges();

        Transport transport = session.getTransport("smtp");
        try {
            transport.connect(host, username, password);
            transport.sendMessage(message, message.getAllRecipients());
        } finally {
            transport.close();
        }
    }
}
```

Real applications must replace `smtp.example.com`, sender/recipient addresses, port, and configuration according to the provider. This code sends a real email when run with valid configuration; test on an SMTP sandbox or authorized environment before using real recipients.

Key points in the example:

- `Session` is created **first**, with no network connection yet.
- `MimeMessage` stores sender, recipients, subject, body, and MIME headers.
- `message.saveChanges()` prepares headers managed by Jakarta Mail; this may include `Message-ID`.
- `session.getTransport("smtp")` obtains a Transport from the SMTP provider.
- `connect(...)` opens the sending session, and `sendMessage(...)` transmits the message to the server.
- `close()` releases the connection whether sending succeeds or throws an error.

If your goal is simply sending email via Spring, **you do not need to rewrite this Transport management code**. Spring Mail already provides the API layer to execute sending.

## 4. Message and MimeMessage: Objects Representing Email

### 4.1. Message Is an Abstract Class

`jakarta.mail.Message` represents a message, including:

- `From` and recipient types `TO`, `CC`, `BCC`.
- `Subject`, `Date`, and header fields.
- Message body.
- Certain flags/methods supporting reading messages in a Store/Folder context.

Because `Message` is abstract, when creating a new Internet email developers normally use `MimeMessage`:

```java
MimeMessage message = new MimeMessage(session);
```

`MimeMessage` knows how to build and parse messages per Internet email and MIME syntax. It provides methods such as `setSubject(...)`, `setText(...)`, `setContent(...)`, `addHeader(...)`, `getMessageID()`, `getAllRecipients()`, and `saveChanges()`.

### 4.2. Address, InternetAddress, and RecipientType

Jakarta Mail uses the abstract `Address` type, and for Internet email `InternetAddress` is the standard implementation:

```java
import jakarta.mail.Message;
import jakarta.mail.internet.InternetAddress;

message.setFrom(new InternetAddress("no-reply@example.com"));

message.setRecipients(
    Message.RecipientType.TO,
    InternetAddress.parse("alice@example.net,bob@example.org", true)
);

message.addRecipient(
    Message.RecipientType.CC,
    new InternetAddress("team@example.com")
);
```

`Message.RecipientType` distinguishes:

| Type | Representation in the message | Meaning |
|---|---|---|
| `TO` | `To:` header | Primary recipients. |
| `CC` | `Cc:` header | Publicly visible carbon-copy recipients. |
| `BCC` | Envelope recipients, normally omitted from headers in the delivered email | Blind carbon-copy recipients. |

Addresses in headers are not the whole SMTP story: `MAIL FROM` and `RCPT TO` are **the envelope** at the protocol layer. Jakarta Mail/the provider determines how addresses are mapped from the message into the SMTP transaction.

When addresses come from external input, validate and sanitize values; `InternetAddress.parse(...)` checks syntax, **but does not guarantee** the mailbox actually exists or can receive email.

### 4.3. Headers, Date, and Message-ID

A `MimeMessage` may contain:

```text
From: Example App <no-reply@example.com>
To: alice@example.net
Subject: Registration confirmation
Date: Thu, 12 Nov 2026 08:00:00 +0000
Message-ID: <unique-id@mailer.example.com>
MIME-Version: 1.0
Content-Type: text/plain; charset=UTF-8
```

`Message-ID` identifies the **email message** in headers—it is not an SMTP transaction ID, server queue ID, or business ID. The library may generate this header during `saveChanges()`.

If the application needs to trace email-sending transactions, create a **dedicated correlation ID or outbox ID** in the database. `Message-ID` may be generated late or rewritten by mail infrastructure per policy, so do not use it as a sole business key.

### 4.4. What Does saveChanges() Do?

`saveChanges()` tells `MimeMessage` that the object has been modified and must finalize its MIME/header state before sending. This is an operation on **memory/message formatting**, **not opening an SMTP connection or sending an email**.

Notes:

- With static `Transport.send(message)`, Jakarta Mail invokes the message preparation step.
- With instance `transport.sendMessage(message, recipients)`, call `message.saveChanges()` first.
- Certain headers are managed automatically by Jakarta Mail; calling `getMessageID()` before the message is prepared may return `null` or a non-final value.
- Do not modify the same `MimeMessage` from multiple threads while sending.

## 5. MIME: Multipart, BodyPart, and DataHandler

A `MimeMessage` does not only contain plain text. With inline images, HTML, and attachments, the message body can be composed of multiple parts:

```text
MimeMessage
  |
  +-- MimeMultipart (multipart/mixed)
       |
       +-- MimeBodyPart (multipart/related)
       |    |
       |    +-- text/html
       |    +-- image/png (inline, Content-ID)
       |
       +-- MimeBodyPart (application/pdf, attachment)
```

Objects involved:

- `Multipart` and `BodyPart` are general types.
- `MimeMultipart` and `MimeBodyPart` are implementations for MIME content.
- `DataHandler` together with Jakarta Activation `DataSource` types represent binary content and data MIME types.
- `Content-Type` identifies media types such as `text/plain`, `text/html`, `image/png`, `application/pdf`.
- `Content-Disposition` can indicate whether a part is `inline` or `attachment`.
- `Content-ID` lets HTML reference an inline part via `cid:...`.

### 5.1. Plain MIME Example: Alternative Text and HTML

With Jakarta Mail, you can create `multipart/alternative` to supply both plain text and HTML:

```java
import jakarta.mail.internet.MimeBodyPart;
import jakarta.mail.internet.MimeMultipart;

MimeBodyPart plain = new MimeBodyPart();
plain.setText("Hello, thank you for registering.", "UTF-8");

MimeBodyPart html = new MimeBodyPart();
html.setContent(
    "<html><body><b>Hello</b>, thank you for registering.</body></html>",
    "text/html; charset=UTF-8"
);

MimeMultipart alternative = new MimeMultipart("alternative");
alternative.addBodyPart(plain);
alternative.addBodyPart(html);

message.setContent(alternative);
message.saveChanges();
```

`multipart/alternative` means **multiple versions of the same content**. Clients choose the suitable version; it does not send two separate emails.

When HTML needs inline images, use `multipart/related` with `Content-ID`; when independent attachments are needed, use `multipart/mixed`. These containers can be nested.

In Spring applications, manual MIME construction is normally replaced by **`MimeMessageHelper`**, reducing boundary, encoding, inline-resource, and attachment errors.

## 6. Authenticator and Authentication Objects

`Authenticator` is where Jakarta Mail obtains login credentials when a provider requires them. A common implementation returns `PasswordAuthentication`:

```java
Authenticator authenticator = new Authenticator() {
    @Override
    protected PasswordAuthentication getPasswordAuthentication() {
        return new PasswordAuthentication(username, password);
    }
};

Session session = Session.getInstance(props, authenticator);
```

Do not confuse these:

| Component | Role |
|---|---|
| `Authenticator` | Supplies credentials to the provider. |
| `PasswordAuthentication` | Holds the username/password pair. |
| `Transport.connect(...)` | Establishes the connection and performs the login flow via the provider. |
| TLS / STARTTLS | Protects the transport channel; does not replace credentials. |
| Sending permission on SMTP server | Policy enforced by the server, not guaranteed merely by holding credentials. |

Some internal SMTP relays do not require login and instead enforce network or IP rules; in such cases `mail.smtp.auth` depends on relay policy.

Never put passwords in emails, `Message-ID`, custom headers, logs, or long-lived exception messages. Enable debugging only in controlled environments.

## 7. Store and Folder: The Email-Reading Side of Jakarta Mail

Although Spring Framework Mail focuses mainly on **sending**, knowing `Store` and `Folder` gives a complete picture of the Jakarta Mail API:

- `Transport` is for the **sending** path.
- `Store` is for **accessing the mail store** on a server.
- `Folder` represents a specific mailbox/folder inside a Store.
- `Message` is also the data type an application receives when reading mail.

Example reading metadata from an IMAPS mailbox:

```java
import jakarta.mail.Folder;
import jakarta.mail.Message;
import jakarta.mail.Session;
import jakarta.mail.Store;
import java.util.Properties;

public class InboxReader {

    public static void inspectInbox(String username, String password)
            throws Exception {
        Properties props = new Properties();
        props.put("mail.store.protocol", "imaps");
        props.put("mail.imaps.host", "imap.example.com");
        props.put("mail.imaps.port", "993");
        props.put("mail.imaps.connectiontimeout", "5000");
        props.put("mail.imaps.timeout", "5000");

        Session session = Session.getInstance(props);
        Store store = session.getStore("imaps");
        Folder inbox = null;

        try {
            store.connect("imap.example.com", username, password);
            inbox = store.getFolder("INBOX");
            inbox.open(Folder.READ_ONLY);

            int count = inbox.getMessageCount();
            int start = Math.max(1, count - 4);

            if (count > 0) {
                Message[] messages = inbox.getMessages(start, count);
                for (Message message : messages) {
                    System.out.println(message.getSubject());
                }
            }
        } finally {
            if (inbox != null && inbox.isOpen()) {
                inbox.close(false);
            }
            store.close();
        }
    }
}
```

The snippet illustrates the API only; the IMAP server must exist and support the corresponding authentication mechanism. If the account requires OAuth or a special mechanism, configure the provider per the real service.

**`Store` is not used for SMTP sending.** Likewise, calling `JavaMailSender.send(...)` does not open `INBOX` or read mail via `Folder`.

When reading large volumes of messages, pay attention to performance, pagination, `FetchProfile`, queries/search, and IMAP UIDs. A message's sequence number in a folder is not a stable global email identifier.

## 8. How Does Spring Mail Abstract Jakarta Mail?

Spring Framework Mail provides notable abstractions:

| Spring Mail | Related Jakarta Mail | Notes |
|---|---|---|
| `MailSender` | Message sending workflow | Simple Spring API for `SimpleMailMessage`. |
| `JavaMailSender` | `Session`, `MimeMessage`, `Transport` | Interface for creating and sending MIME messages. |
| `JavaMailSenderImpl` | `Session` and SMTP transport | Common Spring implementation for connecting to SMTP. |
| `SimpleMailMessage` | Converted to outgoing message | Spring's simple text model, not `MimeMessage`. |
| `MimeMessageHelper` | `MimeMessage`, MIME multipart and resources | Supports HTML, attachments, inline, encoding, addresses. |
| `MimeMessagePreparator` | Preparing `MimeMessage` | Callback to configure a message before sending. |
| `MailException` | Translated or wrapped errors | Spring Mail's unchecked exception hierarchy. |

In Spring, applications typically work through `JavaMailSender` to decouple business code from SMTP transport details.

### 8.1. Spring Boot Configuration

Spring Boot can auto-configure `JavaMailSender` when the dependency and appropriate properties are present. Gradle Groovy DSL example:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-mail'
}
```

`application.yml` for SMTP submission on port 587:

```yaml
spring:
  mail:
    host: smtp.example.com
    port: 587
    username: ${SMTP_USERNAME}
    password: ${SMTP_PASSWORD}
    properties:
      mail:
        smtp:
          auth: true
          starttls:
            enable: true
            required: true
          connectiontimeout: 5000
          timeout: 5000
          writetimeout: 5000
```

In Spring Boot, `spring.mail.properties.mail.smtp.*` settings are forwarded to the underlying mail provider. Socket timeouts in the example are in milliseconds. Environment variables must be supplied by the deployment system; never place real passwords in committed config files.

In Spring Framework without Boot, you can register the bean:

```java
import java.util.Properties;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.mail.javamail.JavaMailSender;
import org.springframework.mail.javamail.JavaMailSenderImpl;

@Configuration
public class SmtpMailConfiguration {

    @Bean
    public JavaMailSender javaMailSender() {
        JavaMailSenderImpl sender = new JavaMailSenderImpl();
        sender.setHost("smtp.example.com");
        sender.setPort(587);
        sender.setUsername(System.getenv("SMTP_USERNAME"));
        sender.setPassword(System.getenv("SMTP_PASSWORD"));
        sender.setDefaultEncoding("UTF-8");

        Properties props = sender.getJavaMailProperties();
        props.put("mail.smtp.auth", "true");
        props.put("mail.smtp.starttls.enable", "true");
        props.put("mail.smtp.starttls.required", "true");
        props.put("mail.smtp.connectiontimeout", "5000");
        props.put("mail.smtp.timeout", "5000");
        props.put("mail.smtp.writetimeout", "5000");

        return sender;
    }
}
```

The illustrative code assumes a Jakarta Mail implementation is present at runtime, environment variables are configured, and the SMTP host uses compatible STARTTLS. Credential management, error monitoring, and secrets-store integration must follow your real deployment environment.

### 8.2. Using MimeMessageHelper

Example Spring service sending HTML with a plain-text version:

```java
import jakarta.mail.MessagingException;
import jakarta.mail.internet.MimeMessage;
import org.springframework.mail.javamail.JavaMailSender;
import org.springframework.mail.javamail.MimeMessageHelper;
import org.springframework.stereotype.Service;

@Service
public class AccountMailService {

    private final JavaMailSender mailSender;

    public AccountMailService(JavaMailSender mailSender) {
        this.mailSender = mailSender;
    }

    public void sendWelcome(String recipient) throws MessagingException {
        MimeMessage message = mailSender.createMimeMessage();
        MimeMessageHelper helper =
            new MimeMessageHelper(message, true, "UTF-8");

        helper.setFrom("no-reply@example.com");
        helper.setTo(recipient);
        helper.setSubject("Welcome");
        helper.setText(
            "Hello, welcome to the application.",
            "<html><body><h1>Welcome!</h1>"
                + "<p>We are glad to have you join us.</p></body></html>"
        );

        mailSender.send(message);
    }
}
```

Here:

- Spring creates a `MimeMessage` suited to the sender configuration.
- `MimeMessageHelper` sets headers, content, and MIME structure.
- `JavaMailSenderImpl` uses Jakarta Mail to create/manage the SMTP connection appropriately.
- The service does not manually obtain `Transport`, call `connect(...)`, or `close()`.

Using `MimeMessageHelper(message, true, "UTF-8")` enables multipart content. If only simple text is sent, `SimpleMailMessage` may suffice.

### 8.3. MimeMessagePreparator: Callback for Message Configuration

Spring allows sending email via a `MimeMessagePreparator` callback:

```java
mailSender.send(mimeMessage -> {
    MimeMessageHelper helper =
        new MimeMessageHelper(mimeMessage, "UTF-8");

    helper.setFrom("no-reply@example.com");
    helper.setTo("alice@example.net");
    helper.setSubject("Notification");
    helper.setText("Notification content");
});
```

This fits when MIME preparation is encapsulated into one operation and there is no need to retain the message object in the service. Spring remains responsible for orchestrating the send process.

## 9. Comparing Plain Jakarta Mail and Spring JavaMailSender Flows

<div>

```text
Plain Jakarta Mail
-------------------------------------------
Properties / Authenticator
      -> Session
      -> MimeMessage
      -> saveChanges()
      -> session.getTransport("smtp")
      -> connect()
      -> sendMessage()
      -> close()

Spring Mail
-------------------------------------------
JavaMailSender (configured)
      -> createMimeMessage()
      -> MimeMessageHelper or Preparator
      -> send()
            |
            +--> JavaMailSenderImpl and Jakarta Mail
                 execute SMTP operations
```

</div>

Both paths use the same foundational concepts. Spring does not change the nature of `Session` or the SMTP protocol; Spring provides a convenient interface, container integration, configuration, and application-friendly exceptions.

| Criterion | Direct Jakarta Mail | Spring JavaMailSender |
|---|---|---|
| Creating `Session` | Created and configured manually. | Typically managed by `JavaMailSenderImpl`/Boot. |
| Creating message content | `MimeMessage` and MIME APIs. | `SimpleMailMessage` or `MimeMessage` + `MimeMessageHelper`. |
| Sending | `Transport.send(...)` or `Transport.sendMessage(...)`. | `JavaMailSender.send(...)`. |
| Connection management | Can control `Transport` manually. | Usually handled by the implementation. |
| Exception handling | `MessagingException` and subclasses. | `MailException` and subclasses; MIME building calls can still throw `MessagingException`. |
| Business code coupling | Tied directly to Jakarta Mail APIs. | Can depend on Spring interfaces for easier implementation swapping. |

**If the application already runs on Spring**, start with `JavaMailSender` by default. Use the Jakarta Mail API directly when you need specific operations that Spring's abstraction does not expose directly, such as reading mail via IMAP/POP3 or managing a custom Transport connection lifecycle.

## 10. Practical Lifecycle and Common Confusions to Avoid

### 10.1. Does One Session Equal One SMTP Connection?

**No.** You can create one `Session` and spawn many `MimeMessage` and `Transport` instances over time. Conversely, one connected `Transport` can send multiple messages within the same SMTP session if used properly.

### 10.2. Does Calling saveChanges() Send Mail?

**No.** `saveChanges()` updates MIME state/headers. Only sending via `Transport` or the corresponding abstraction starts transmitting data to the mail server.

### 10.3. Does Transport Sending Successfully Mean the Recipient Read It?

**No.** An SMTP server can accept a message and queue it for forwarding. Bounces or rejections at later hops can still happen. Delivery status requires data from the provider or email infrastructure; the result of `sendMessage(...)` is not an email-open report.

### 10.4. Does Jakarta Mail Automatically Handle Exactly-Once Retries?

Never assume that. A timeout occurring after the client finishes transmitting the message but before receiving the final reply can leave an **indeterminate state**: whether the server accepted the message or not. Immediate retries can cause duplicate emails. For critical workflows, use an outbox, queue, backoff, correlation IDs, and status reconciliation where supported by the provider.

### 10.5. Does Closing Transport Delete the Message?

**No.** `Transport.close()` closes the transport service/connection. `MimeMessage` is the application-side object holding message content; closing Transport does not delete the message object or retract copies already accepted by the SMTP server.

### 10.6. Can One MimeMessage Be Shared Across Multiple Send Jobs?

Generally create a dedicated `MimeMessage` per message. Having multiple workers modify one message easily mixes headers, recipients, and `saveChanges()` state. When sending one piece of content to multiple recipients, decide explicitly between **one message with multiple recipients** and **multiple personalized messages**, as the two choices affect content, Message-ID, and per-recipient error handling.

## 11. Error Handling: Jakarta Mail and Spring Mail

### 11.1. Common Jakarta Mail Exceptions

Typical error types:

| Error | Example scenario |
|---|---|
| `MessagingException` | General error category for message, connection, or protocol handling. |
| `AuthenticationFailedException` | Mail server login failed. |
| `SendFailedException` | Send operation failed, possibly involving invalid recipients or partial sends. |
| `AddressException` | Invalid email address syntax during parsing. |
| `FolderClosedException` / `StoreClosedException` | Mailbox-reading resource closed mid-operation. |

When reading exceptions, distinguish **whether the message could be built**, **whether the connection opened**, **whether the server authenticated**, **which recipients were accepted**, and **whether the server accepted the entire DATA phase**.

A `SendFailedException` can include valid/invalid recipient lists at the Jakarta Mail layer. Do not assume every thrown exception means **no recipient received the message**.

### 11.2. Spring MailException

When using `JavaMailSender`, Spring may throw errors such as:

- `MailAuthenticationException`: authentication failure with the sending server.
- `MailSendException`: failure executing the send.
- `MailParseException`: failure preparing/parsing the message.
- `MailPreparationException`: failure during the message preparation stage.

These classes belong to Spring's `MailException` hierarchy and are unchecked exceptions. Meanwhile, operations on `MimeMessage` or `MimeMessageHelper` can still declare Jakarta Mail's `MessagingException`.

Example classification at the service layer:

```java
import org.springframework.mail.MailAuthenticationException;
import org.springframework.mail.MailException;
import org.springframework.mail.MailSendException;

try {
    mailSender.send(message);
} catch (MailAuthenticationException ex) {
    // Check credentials, AUTH mechanism, and server policy.
    throw ex;
} catch (MailSendException ex) {
    // Record attempt, error type, and possibility of partial send.
    throw ex;
} catch (MailException ex) {
    // Other Spring Mail sending issues.
    throw ex;
}
```

The pattern above illustrates **classification**, not a complete retry policy. Do not retry authentication errors or malformed recipient addresses indefinitely.

### 11.3. Timeout and TLS Configuration

Important SMTP properties:

| Property | Purpose |
|---|---|
| `mail.smtp.host` | SMTP server. |
| `mail.smtp.port` | SMTP port. |
| `mail.smtp.auth` | Enables SMTP authentication when required by the server. |
| `mail.smtp.starttls.enable` | Allows STARTTLS if supported by the server. |
| `mail.smtp.starttls.required` | Requires STARTTLS to succeed. |
| `mail.smtp.ssl.enable` | Enables implicit TLS from connection start, typically suited to port 465 per provider. |
| `mail.smtp.connectiontimeout` | Time limit waiting to establish connection. |
| `mail.smtp.timeout` | Time limit waiting for socket reads. |
| `mail.smtp.writetimeout` | Time limit waiting for socket writes. |

Port 587 typically uses STARTTLS; port 465 typically uses implicit TLS. Never mismatch the TLS model with the actual port.

When enabling debug:

```java
session.setDebug(true);
```

Enable only in controlled test environments; protocol traces and email metadata can contain sensitive data. Never send debug logs containing credentials, message bodies, or tokens to unauthorized destinations.

## 12. Common Design Mistakes

**"Creating a Session already verified the SMTP connection."** False. Session is primarily configuration; to test connectivity you need Transport to communicate with the server.

**"Transport and Store are two names for the same operation."** False. Transport is for sending; Store is for reading/managing mail stores.

**"MimeMessageHelper is a Jakarta Mail class."** False. `MimeMessageHelper` is a Spring utility built atop Jakarta Mail objects.

**"SimpleMailMessage is a MimeMessage."** False. `SimpleMailMessage` is Spring's own data type for describing simple plain-text mail; Spring converts/coordinates with the Jakarta Mail layer when sending.

**"Calling getTransport(...) means already connected."** False. `getTransport(...)` obtains the transport object; connecting normally begins when calling `connect(...)` or a higher-level send method.

**"saveChanges() is the same as sendMessage()."** False. `saveChanges()` prepares message data; `sendMessage(...)` transmits over a connected Transport.

**"Transport.send returning without error means the email is in the Inbox."** False. Success at the SMTP hop confirms acceptance only at that corresponding server layer.

**"To speed things up, share one MimeMessage across all threads."** Inappropriate. Easily mixes recipient info, bodies, and headers. Create a dedicated message per email.

**"Using javax.mail in Spring Framework 6 examples is equivalent to jakarta.mail."** No. Spring Framework 6 and Spring Boot 3 use the Jakarta namespace; earlier generations may still use `javax.mail`. Never mix both namespaces arbitrarily in the same code.

## 13. Practice Exercises

### Exercise 1: Identify Responsibilities

Given the tasks: (a) hold SMTP properties; (b) build MIME content; (c) open connection and send; (d) read `INBOX`; (e) represent email addresses; (f) conveniently create HTML content with attachments in Spring.

Match them with `Session`, `MimeMessage`, `Transport`, `Store/Folder`, `InternetAddress`, and `MimeMessageHelper`.

**Hint:** (a) Session; (b) MimeMessage; (c) Transport; (d) Store/Folder; (e) InternetAddress; (f) MimeMessageHelper.

### Exercise 2: Fix Missing saveChanges

An application uses Jakarta Mail directly:

```java
MimeMessage message = new MimeMessage(session);
message.setFrom(new InternetAddress("no-reply@example.com"));
message.setRecipient(
    Message.RecipientType.TO,
    new InternetAddress("alice@example.net")
);
message.setSubject("Notification");
message.setText("Content");

Transport transport = session.getTransport("smtp");
transport.connect(host, username, password);
transport.sendMessage(message, message.getAllRecipients());
transport.close();
```

Add the message preparation call before `sendMessage(...)` and move `close()` into a `finally` block so resources are released even on failure.

### Exercise 3: Convert Plain Jakarta Mail Code to Spring Mail

Given a text-sending function using `Session`, `MimeMessage`, `Transport.connect(...)`, `sendMessage(...)`, and `close()`. Rewrite it by constructor-injecting `JavaMailSender`, creating `MimeMessage` from the sender, using `MimeMessageHelper` to populate fields, and calling `mailSender.send(message)`.

The goal is replacing business code directly coupled to the Transport lifecycle with Spring's sending abstraction.

### Exercise 4: Reading Error Logs

Scenario: the application creates a Session normally, but hits a timeout at `transport.connect(...)`. What does succeeding at Session creation prove?

**Answer:** It only proves the configuration object was created. It does not prove the SMTP host is reachable or authenticable. Inspect DNS, host, port, firewall, TLS, and timeouts.

### Exercise 5: Compare Sending and Reading

An application needs to send order confirmation emails and read reply emails from `INBOX`. Which objects do the two flows require?

**Hint:** send via `JavaMailSender` or `Session + Transport + MimeMessage`; read via `Session + Store + Folder + Message`. `JavaMailSender` is not a mailbox-reading API.

### Exercise 6: Propose Retry Handling

A worker transmitted an email to the SMTP server, then timed out before receiving the final reply. Can we treat this as "not sent" and immediately call again?

**Hint:** We cannot be sure. Record the attempt status as unknown/indeterminate, use an application/outbox ID for tracing, apply bounded retries, and reconcile status if supported by infrastructure. Reusing Message-ID alone does not guarantee duplicate prevention.

## 14. Summary

In Jakarta Mail, **`Session` is the configuration context and factory**, **`Transport` handles sending**, and **`Message`/`MimeMessage` represent message content**. `Address` models senders and recipients; `Authenticator` assists in supplying credentials; `Multipart`/`BodyPart` model complex content. On the reading side, `Store` and `Folder` provide access to stored messages.

Spring Framework Mail builds atop these components through **`JavaMailSender`, `JavaMailSenderImpl`, and `MimeMessageHelper`**. Understanding the underlying structure helps you choose the right API, diagnose issues layer by layer, manage connections properly, and distinguish server acceptance of an email from actual delivery to the recipient.
