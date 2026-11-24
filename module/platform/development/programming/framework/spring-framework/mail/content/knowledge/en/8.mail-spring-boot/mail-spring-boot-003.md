# The spring.mail.host, port, username, and password properties

A Spring Boot application that wants to send a registration confirmation email needs to know **which server to connect to**, **through which port**, and **which identity to use to be permitted to send mail**. The four configuration properties `spring.mail.host`, `spring.mail.port`, `spring.mail.username`, and `spring.mail.password` are the foundational information Spring Boot uses to prepare the SMTP connection for the email-sending component.

For example, a system may need to submit email to a provider's SMTP service. The business code only calls `JavaMailSender.send(...)`; Spring Boot supplies the connection values so that the Jakarta Mail library can contact the server. This separation makes it possible to change providers, accounts, or deployment environments without modifying the mail-sending logic.

However, **these four properties do not by themselves decide whether the connection is encrypted with TLS**, do not create the `From` sender by themselves, and do not mean the email will definitely be delivered to the Inbox. You need to understand the specific role of each property, the additional SMTP settings, and how to manage secrets safely.

## 1. Where does Spring Boot place these four properties?

In a Spring Boot application with the appropriate mail dependency, the **Mail Auto-configuration** mechanism can create a `JavaMailSender` bean. The `spring.mail.*` values are mapped into a configuration object and passed to the mail-sending implementation, usually `JavaMailSenderImpl`.

You can picture it as:

~~~mermaid
flowchart TD
    A["application.yml / application.properties / environment variables"] --> B["Spring Boot mail configuration"]
    B --> C["JavaMailSender"]
    C --> D["Jakarta Mail SMTP transport"]
    D --> E["SMTP relay / submission server"]
    F["Business service"] -->|"send(message)"| C
    E --> G["Email forwarding infrastructure"]
~~~

Here, Spring Boot manages **how the mail-sending component is created and configured**. The business layer concentrates on the recipient, the subject, and the content.

The four properties to learn:

| Property | Main meaning | Illustrative example |
| --- | --- | --- |
| `spring.mail.host` | The server name or address the application connects to in order to submit mail via SMTP | `smtp.provider.example` |
| `spring.mail.port` | The TCP port on the SMTP server | `587` |
| `spring.mail.username` | The SMTP login identity if the server requires authentication | `mailer@example.org` |
| `spring.mail.password` | The secret used with the corresponding SMTP authentication mechanism | Taken from an environment variable or a secret store |

The values in the table are only illustrative. `smtp.provider.example` is not the address of a publicly available service server. The deployer needs to use the actual parameters issued by the SMTP provider.

## 2. Preparing dependencies so Spring Boot supports mail sending

In a Spring Boot project using Gradle:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-mail'
}
~~~

The starter helps bring the mail integration libraries onto the classpath. With appropriate configuration, Spring Boot can auto-configure `JavaMailSender` so that the application can inject the dependency:

~~~java
import org.springframework.mail.javamail.JavaMailSender;
import org.springframework.stereotype.Service;

@Service
public class MailNotificationService {

    private final JavaMailSender mailSender;

    public MailNotificationService(JavaMailSender mailSender) {
        this.mailSender = mailSender;
    }
}
~~~

Adding the starter is **not enough to send real email**. You need an SMTP server that can be connected to, with the host, port, authentication information (if needed), TLS, and the provider's policies configured correctly.

In the common auto-configuration approach, `spring.mail.host` is the key information for Spring Boot to set up the sender. If there is no host or suitable Jakarta Mail Session configuration source, the application may not have an auto-created `JavaMailSender` bean. In addition, if the project has already defined its own sender bean, auto-configuration will not necessarily create another bean to replace it.

## 3. spring.mail.host — the SMTP server the application connects to

`spring.mail.host` specifies **the destination SMTP server of the outbound connection from the application**. For example:

~~~properties
spring.mail.host=smtp.provider.example
~~~

When sending mail through an SMTP relay, the Jakarta Mail library uses this hostname to open the network connection. The host can be:

- The DNS name of an SMTP service issued by a provider, for example `smtp.provider.example`.
- The name of an internal SMTP server within a corporate network, for example `mail-relay.internal.example`.
- `localhost` or a container name in a development environment when there is a test SMTP server or local relay.
- An IP address in privately managed environments, although a valid hostname is usually more convenient for checking the TLS certificate.

### The SMTP host differs from the recipient's domain

Suppose the application wants to send to `an@example.net` but is configured with:

~~~properties
spring.mail.host=smtp.provider.example
~~~

The application **does not connect directly to `example.net`** merely because that is the domain in the recipient's address. It connects to `smtp.provider.example`, and hands the message and the recipient addresses to the relay. When the mail needs to be forwarded out to the Internet, the relay or the infrastructure behind it then determines where to deliver mail for the `example.net` domain, usually based on DNS MX.

~~~mermaid
flowchart LR
    A["Spring Boot"] -->|"spring.mail.host"| B["smtp.provider.example"]
    B -->|"Find the delivery route, e.g. DNS MX"| C["Mail server of example.net"]
    C --> D["Mailbox an@example.net"]
~~~

Therefore, entering a **website address**, the **recipient's mail domain**, or the **recipient's MX** into `spring.mail.host` is usually not how an application sends mail through an SMTP submission provider.

### Host and TLS identity

If TLS is enabled together with hostname checking, the name in `spring.mail.host` needs to be compatible with the name that the SMTP server's TLS certificate attests to. Using an IP address or an arbitrary hostname while the certificate is issued only for a different name can lead to a TLS authentication error.

When a provider offers multiple hostnames or regional endpoints, you should use the hostname specified in their documentation, along with the corresponding port and TLS type.

### When the host is unreachable

Common scenarios:

- DNS cannot resolve the host name.
- The server is down.
- A firewall or the network blocks the SMTP port that needs to be used.
- The application runs in a container but uses `localhost` in the wrong context: a container's `localhost` is the container itself, not the host machine or another SMTP container.
- The SMTP service only allows connections from authorized networks/IPs.

These scenarios are problems connecting to the **configured host**, not syntax errors in `SimpleMailMessage` or `MimeMessage`.

## 4. spring.mail.port — the TCP port of the SMTP service

`spring.mail.port` specifies the network port to connect to on the host:

~~~properties
spring.mail.port=587
~~~

This is an integer, different from an email address or a mailbox sequence number. A host may run multiple services on different ports; the port helps the operating system connect to the correct SMTP service.

Commonly seen ports:

| Port | Common usage | Connection security |
| --- | --- | --- |
| **25** | SMTP mail transfer between servers (*mail transfer*) | STARTTLS may be negotiated according to the system's policy |
| **587** | Mail submission from an application/email client to a relay (*submission*) | Usually supports STARTTLS; the provider may require authentication and TLS |
| **465** | Submission with TLS immediately upon connection (*implicit TLS*) | The TLS handshake begins before any SMTP commands are sent |
| Custom port | Internal SMTP or a test service | Depends on the system's configuration |

The port number **does not enable TLS by itself**. For example, setting `port=587` without enabling the STARTTLS configuration does not mean the data is definitely encrypted. Similarly, connecting to port 465 requires the client to be in implicit TLS mode when the server offers that service.

### What if the port is not declared?

SMTP libraries usually have a default behavior when no port is specified (traditional SMTP typically uses port 25). However, **you should not rely on the default port when deploying an application** if the provider requires 587 or 465. Declaring the port explicitly makes the configuration clear and avoids connecting to the wrong service.

Note that there is no fixed relationship such as "port 587 must always be used by every application" or "port 25 can never be used". Prioritize **the set of host, port, TLS, and auth parameters that the SMTP provider requires**.

### Example of an error caused by mismatching port and protocol

A server is waiting for a **TLS handshake right from the start** on port 465; the client instead starts with a plaintext SMTP command to negotiate STARTTLS. The two sides wait for different bytes, causing a timeout or a handshake error.

Conversely, a server on 587 waits for the SMTP greeting and then the `STARTTLS` command; the client instead initiates implicit TLS as soon as it connects. That is also a wrong configuration even though the hostname and username are both correct.

## 5. spring.mail.username — the SMTP authentication identity

`spring.mail.username` is the username value the client supplies for the SMTP authentication process when the service uses SMTP AUTH:

~~~properties
spring.mail.username=mailer@example.org
~~~

The provider may require:

- A full email address such as `mailer@example.org`.
- A login name issued by the system, not necessarily an email address.
- A fixed identifier name, while the secret part is an API key or token supported by the provider.
- Another authentication mechanism that needs additional configuration or libraries.

Therefore, **the username does not always match the sending email address**.

### Username differs from From and Reply-To

The three values below fulfill three different roles:

| Value | Role |
| --- | --- |
| `spring.mail.username` | The login identity with the SMTP server, if there is authentication |
| `From` on the message | The sender address displayed in the email content |
| `Reply-To` on the message | The address suggested for the recipient to reply to |

For example, the application may log in to SMTP with `smtp-account-42` but send with:

~~~text
From: Notifications <notice@example.org>
Reply-To: helpdesk@example.org
~~~

This only works if the provider allows the use of that sender identity. They may require domain/address verification, override `From`, or refuse to send if it does not match their policy.

**Spring Boot does not implicitly take `spring.mail.username` to assign `From` for every message.** If the product needs a fixed sender, declare a separate application configuration, for example `app.mail.from`, and then use `setFrom(...)`.

### Does unauthenticated SMTP need a username?

Not every SMTP server requires login. An internal relay restricted by network/IP or a test SMTP server may allow sending without SMTP AUTH. In that case, `spring.mail.username` and `spring.mail.password` can be left empty if that matches the server's policy.

However, the fact that a server does not require authentication **does not mean it is publicly open for anyone to send**. The infrastructure needs an anti-open-relay policy and appropriate limits on connection sources.

## 6. spring.mail.password — the SMTP authentication secret

`spring.mail.password` is the secret data used with the SMTP provider's authentication mechanism:

~~~properties
spring.mail.password=${SMTP_PASSWORD}
~~~

The configuration above tells Spring Boot to take the value from the environment variable `SMTP_PASSWORD` when the application starts. This is a **Spring configuration substitution** placeholder, not a literal password string and also not a mechanism that creates secrets by itself.

The name `password` does not mean you must use the **web login password of a personal account**. The provider may require an application password, separately issued SMTP credential information, or a mail-sending key with an appropriate usage mechanism. You need to follow the provider's official documentation.

### Why not write the password directly?

The following style of configuration should not be put into source code or Git:

~~~properties
# Example of a configuration to avoid:
spring.mail.password=your-real-password-here
~~~

A directly stored password can end up in Git history, repository copies, build artifacts, screenshots, logs, or CI systems. Once exposed, deleting the line in a new commit **may not remove the old copies**; you usually have to revoke/rotate the exposed key.

Secrets should be supplied through the runtime environment, the platform's secret store, or a protected configuration management mechanism. The account used for the application should be granted appropriate permissions and be capable of rotation when needed.

### Distinguishing environment variables from a .env file

Spring Boot supports reading operating-system environment variables and the configuration sources that have been loaded. But **an arbitrary `.env` file placed in the project directory is not implicitly loaded by Spring Boot as environment variables**. If you use a container/IDE/script tool to load `.env`, that tool itself must put the values into the runtime environment or a configuration source that Spring reads.

Do not put real passwords in source code examples or in startup command arguments if they risk being stored in shell history, the process list, or the deployment system's logs.

## 7. Configuring all four properties in application.properties

A common SMTP submission configuration using STARTTLS can be written as follows:

~~~properties
# SMTP submission target issued by the provider
spring.mail.host=smtp.provider.example
spring.mail.port=587

# Credentials taken from the environment
spring.mail.username=${SMTP_USERNAME}
spring.mail.password=${SMTP_PASSWORD}

# Additional properties for the Jakarta Mail SMTP transport
spring.mail.properties.mail.smtp.auth=true
spring.mail.properties.mail.smtp.starttls.enable=true
spring.mail.properties.mail.smtp.starttls.required=true
spring.mail.properties.mail.smtp.ssl.checkserveridentity=true

# Time-out limits (milliseconds)
spring.mail.properties.mail.smtp.connectiontimeout=5000
spring.mail.properties.mail.smtp.timeout=5000
spring.mail.properties.mail.smtp.writetimeout=5000

# Application-specific configuration, not part of spring.mail.*
app.mail.from=${APP_MAIL_FROM}
~~~

The configuration is divided into three meaningful groups:

1. **`host` and `port`**: the connection target.
2. **`username` and `password`**: authentication information, when the server requires it.
3. **`mail.smtp.*`**: additional Jakarta Mail properties, for example SMTP AUTH, STARTTLS, hostname verification, and timeouts.

`app.mail.from` is a custom key of the **application** that represents the default sender. Spring Boot has no convention that this custom key will automatically fill in `From`; the mail-sending code needs to read and use that value.

### Why add mail.smtp.auth?

The four properties `spring.mail.host`, `port`, `username`, and `password` determine the target and the authentication information. When the SMTP provider requires login, the configuration usually comes with:

~~~properties
spring.mail.properties.mail.smtp.auth=true
~~~

This property tells the Jakarta Mail SMTP transport that the service uses SMTP AUTH. The specific authentication method may depend on the mechanism the server advertises and the client supports. When the server requires OAuth2 or a specific method, supplying only an ordinary username/password may not be enough.

Do not confuse `mail.smtp.auth=true` with TLS: **AUTH authenticates the account**, while **TLS protects the network connection**. They address two different requirements and are usually used together.

### Optional STARTTLS versus required STARTTLS

~~~properties
spring.mail.properties.mail.smtp.starttls.enable=true
spring.mail.properties.mail.smtp.starttls.required=true
~~~

- `starttls.enable=true` allows the client to request an upgrade to TLS when the server supports it.
- `starttls.required=true` requires STARTTLS to be available and to succeed; otherwise the send operation must fail.

When using an SMTP account on a network that is not fully trusted, a configuration that **requires TLS** and appropriate hostname verification helps avoid inadvertently sending information over a plaintext connection.

### Timeouts are not an automatic retry feature

The three properties `connectiontimeout`, `timeout`, and `writetimeout` limit the kinds of wait time when connecting, reading, or writing. They help avoid connections that hang for too long, but they **do not create a retry queue by themselves**, do not remove duplicate recipients by themselves, and do not guarantee that the email is delivered to the recipient.

A timeout error still needs to be handled according to context, because there are cases where the SMTP server has accepted the mail but the final response does not reach the application. Resending the same message can create duplicate mail.

## 8. Equivalent configuration with application.yml

If the project uses YAML, you can express the same intent:

~~~yaml
spring:
  mail:
    host: smtp.provider.example
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
          ssl:
            checkserveridentity: true
          connectiontimeout: 5000
          timeout: 5000
          writetimeout: 5000

app:
  mail:
    from: ${APP_MAIL_FROM}
~~~

In YAML, the hierarchical structure represents `spring.mail.properties.mail.smtp.*`. A practical note: the properties under `spring.mail.properties` are used as **Jakarta Mail properties**, not Spring Boot options that change meaning on their own. If you use YAML and need a flat key containing dots, you can use a notation suited to the configuration mapping mechanism; for example, the nested structure above makes each hierarchy level clear.

The example above contains no real credentials; the environment variables must be supplied in the runtime environment. With YAML, you also need to keep the indentation correct and avoid accidentally writing the same key multiple times, which would lose the intended configuration.

### Using the SPRING_MAIL_* environment variables

Spring Boot supports mapping property names to environment variables. For example:

~~~text
SPRING_MAIL_HOST=smtp.provider.example
SPRING_MAIL_PORT=587
SPRING_MAIL_USERNAME=<assigned value>
SPRING_MAIL_PASSWORD=<assigned secret>
~~~

The lines above describe **variable names**, and are not a configuration file to be committed with the application nor a shell command to be copied verbatim. How the variables are supplied depends on Docker, the IDE, the operating system, CI/CD, or the deployment platform.

You can use the environment variables directly following Spring Boot's mapping rules, or use the placeholders `${SMTP_USERNAME}`/`${SMTP_PASSWORD}` as in the earlier examples. Choose one approach consistently according to the project's configuration management infrastructure.

## 9. Configuring implicit TLS when the SMTP server uses port 465

Some providers support SMTP submission over **implicit TLS** on port 465. In that case, the TLS handshake begins right after the TCP connection is opened; there is no plaintext SMTP phase followed by an upgrade with the `STARTTLS` command.

Example:

~~~properties
spring.mail.host=smtp.provider.example
spring.mail.port=465
spring.mail.username=${SMTP_USERNAME}
spring.mail.password=${SMTP_PASSWORD}

spring.mail.properties.mail.smtp.auth=true
spring.mail.properties.mail.smtp.ssl.enable=true
spring.mail.properties.mail.smtp.ssl.checkserveridentity=true

spring.mail.properties.mail.smtp.connectiontimeout=5000
spring.mail.properties.mail.smtp.timeout=5000
spring.mail.properties.mail.smtp.writetimeout=5000
~~~

In this case, `mail.smtp.ssl.enable=true` requires the SMTP connection to be protected by TLS from the start. There is no need to require `STARTTLS` on a connection that already began in TLS.

A brief comparison:

| Characteristic | STARTTLS submission (usually 587) | Implicit TLS submission (usually 465) |
| --- | --- | --- |
| Initial connection | Ordinary SMTP | Immediate TLS handshake |
| How TLS is enabled | The `STARTTLS` command on the SMTP connection | Enable `mail.smtp.ssl.enable=true` |
| Main properties | `mail.smtp.starttls.enable`, possibly `required` | `mail.smtp.ssl.enable` |
| Server identity verification | Hostname checking should be enabled | Hostname checking should be enabled |
| Login information | As required by the SMTP provider | As required by the SMTP provider |

You should not just change the `port` and keep all the TLS properties from another configuration. **The host, port, TLS type, and auth must form a compatible set of parameters**.

## 10. Sending a test mail with JavaMailSender

After configuring SMTP, a service can receive `JavaMailSender` via constructor injection and send mail:

~~~java
import org.springframework.beans.factory.annotation.Value;
import org.springframework.mail.SimpleMailMessage;
import org.springframework.mail.javamail.JavaMailSender;
import org.springframework.stereotype.Service;

@Service
public class WelcomeMailService {

    private final JavaMailSender mailSender;
    private final String from;

    public WelcomeMailService(
            JavaMailSender mailSender,
            @Value("${app.mail.from}") String from) {

        this.mailSender = mailSender;
        this.from = from;
    }

    public void sendWelcome(String recipient) {
        if (recipient == null || recipient.isBlank()) {
            throw new IllegalArgumentException(
                    "The recipient address must not be empty"
            );
        }

        SimpleMailMessage message = new SimpleMailMessage();
        message.setFrom(from);
        message.setTo(recipient);
        message.setSubject("Welcome");
        message.setText(
                "Your account has been created successfully."
        );

        mailSender.send(message);
    }
}
~~~

The relationship between code and configuration:

| Step | Responsible party |
| --- | --- |
| Choose the recipient, subject, and content | `WelcomeMailService` |
| Get the application's own `From` address | `app.mail.from` |
| Know the host, port, username, password | Spring Boot configuration `spring.mail.*` |
| Build and transfer the mail via SMTP | `JavaMailSender` and Jakarta Mail |
| Accept the mail, forward it, handle limits and bounces | SMTP relay / email infrastructure |

To run successfully, you need a real SMTP host, sending permission configured, an account (if there is authentication), and a `From` address that the provider accepts. A mail accepted by the SMTP relay can still be bounced or land in the spam folder; `send(...)` returning normally does not prove the mail reached the Inbox.

### Using MimeMessageHelper with HTML and Unicode

When you need HTML, attachments, or a MIME structure, you can use the same `JavaMailSender`:

~~~java
import jakarta.mail.MessagingException;
import jakarta.mail.internet.MimeMessage;
import org.springframework.mail.javamail.MimeMessageHelper;

public void sendHtml(String recipient) throws MessagingException {
    MimeMessage mime = mailSender.createMimeMessage();

    MimeMessageHelper helper =
            new MimeMessageHelper(mime, false, "UTF-8");

    helper.setFrom(from);
    helper.setTo(recipient);
    helper.setSubject("Registration confirmation ✅");
    helper.setText(
            "<p>Your registration is <strong>complete</strong>.</p>",
            true
    );

    mailSender.send(mime);
}
~~~

The method is illustrated as an **additional member of a service class that already has** the `mailSender` and `from` fields. `MimeMessageHelper` handles the content/formatting; it does not need to retrieve the host or username itself. The connection configuration is reused when calling `send(...)`.

## 11. Each environment can use a different SMTP

An application usually has multiple environments:

- **Local development:** a test SMTP server that retains emails in a testing interface and does not forward mail out to the Internet.
- **Test/staging:** an SMTP account with restricted permissions, a low quota, or sending only to a test group.
- **Production:** an official SMTP relay, a verified domain/sender, and securely managed credentials.

For example, the same `WelcomeMailService` code still works with a different configuration:

| Environment | `host` | `port` | `username/password` |
| --- | --- | --- | --- |
| Local with an SMTP test server | `localhost` or an internal container hostname | The test server's port | May not be needed |
| Staging | The provider's SMTP sandbox | Per provider | Staging credentials |
| Production | The official SMTP relay | Per provider | Production credentials |

In a container environment, `localhost` points to the **current container**. If the SMTP test server runs in another container, you need to use a network/container name resolvable within the same network instead of defaulting to `localhost`.

You can use Spring Boot profiles such as `application-local.yml` and `application-prod.yml` to declare the corresponding host/port. **Production credentials should not be committed into profile files**. These secrets should be supplied independently from the deployment infrastructure.

A note: when using a placeholder without a corresponding environment value, creating the configuration or using the bean may fail. For a system that needs to send email, this is usually a signal that the configuration needs fixing, rather than replacing the password with an unsafe default string.

## 12. Does the spring.mail.* configuration check the server at startup?

Normally, having a `JavaMailSender` bean and the four bound properties **does not mean** the application has established an SMTP connection or authenticated successfully. Many errors only appear when actually sending.

Spring Boot has the option:

~~~properties
spring.mail.test-connection=true
~~~

When supported and applied, this option requires trying to connect to the server when the mail configuration is initialized. It can help detect unsuitable host/port/credentials early, but it also creates an **application-startup dependency on SMTP being reachable at that moment**.

You should not treat `test-connection=true` as evidence that every later email will send successfully:

- The connection may succeed at startup but fail at send time.
- An account may be able to authenticate but not have permission to use a specific `From` address.
- The SMTP provider may limit recipients, quota, or content.
- A mail may be accepted by the relay but fail delivery afterward.

For an application that needs to keep serving other functions even when SMTP is temporarily down, carefully consider forcing a connection check at startup. For an application dedicated to sending mail, detecting a faulty configuration from the start can be useful.

## 13. How do wrong parameters typically show up?

Configuration errors can be recognized by stage:

| Symptom | Property to check first | Common reason |
| --- | --- | --- |
| Cannot resolve or connect to the SMTP host | `spring.mail.host` | Wrong hostname, DNS failure, hostname unreachable |
| Connection refused / timeout | `host` and `port` | Wrong port, firewall blocking, server not running |
| TLS handshake fails | `port` and `spring.mail.properties.mail.smtp.*` | STARTTLS/implicit TLS does not match the server, invalid certificate or hostname |
| SMTP reports authentication failure | `username`, `password`, `mail.smtp.auth` | Wrong credentials, locked account, wrong AUTH mechanism |
| Mail rejected because of the sender | `From` on the message and the provider's policy | The username is valid but the `From` address is not yet permitted |
| Waiting too long when sending | Jakarta Mail timeouts, network | Read/write time not limited or the infrastructure responds slowly |
| `JavaMailSender` is not created | Starter, `host`, auto-configuration settings | Missing dependency, host configuration, or a custom bean already exists |
| Sent successfully but the recipient does not see the mail | Not dependent solely on the four properties | Bounce, spam, wrong address, quota, or receiving policy |

### Authentication error: distinguish username/password from TLS

When an SMTP relay returns a `535 Authentication failed` error or a similar message, you need to check the login information, the authentication mechanism, and the account state. But an authentication error can also occur when the server only allows AUTH after STARTTLS and the client has not upgraded successfully.

Conversely, if a TLS certificate error is reported, changing the password does not help fix a wrong hostname or trust chain. You need to cross-check the **correct stage: connection → TLS → AUTH → mail submission**.

### Errors after SMTP accepts

If the send command receives a successful response, that usually only confirms that the SMTP relay received the message at the moment of submission. Transferring the mail through servers and to the destination mailbox may happen afterward.

When the product needs to know the status of each recipient, you should integrate bounce feedback, webhooks, or delivery events from the email provider. `spring.mail.*` does not by itself provide Inbox-tracking functionality.

## 14. Secrets, logs, and operational management

The four properties have different levels of sensitivity:

- `spring.mail.host` and `port` are usually service configuration information; they are not passwords but still need to be managed per environment.
- `spring.mail.username` may reveal the identity of the service account, so limit its appearance in logs if not needed.
- `spring.mail.password` is a secret, must be protected, and must not be printed to the console, logs, or API responses.

Some operating principles:

1. Use a dedicated SMTP account for the application and grant only the necessary permissions.
2. Store credentials in a secret store or protected environment configuration, and do not commit them to the repository.
3. Have a process for **credential rotation/revocation** that does not require modifying business code.
4. Enable TLS and hostname verification in the way the SMTP provider supports.
5. Do not write raw MIME or real email content to logs, to avoid leaking personal data.
6. Limit timeouts, sending rate, and the number of retries according to product requirements.
7. Separate local, staging, and production credentials, avoiding one account for everywhere.
8. Do not enable Jakarta Mail debug indiscriminately in production, because protocol session logs may contain email addresses and sensitive metadata.

If a credential is exposed, you need to revoke or change it following the provider's process. Deleting a configuration line from the file does not necessarily remove the secret from Git history or logging systems.

## 15. Common misconceptions

### "If there is a username, Spring automatically uses that address as From"

No. `spring.mail.username` is SMTP authentication information; `From` is a field of the email set by the application. The provider may require From to be compatible with the account, but that is the **server's policy**, not an automatic rule of the four properties.

### "Port 587 means the email is encrypted"

No. The port itself only identifies the TCP connection point. STARTTLS needs to be configured and negotiated successfully; if TLS must be enforced, there must be a policy requiring TLS and server verification.

### "Every SMTP server needs a username/password"

No. An internal relay or a test server may use other permission mechanisms. But the application must comply with the server's access policy; you should not build a public open relay.

### "The password is the ordinary web login password"

Not necessarily. Many providers require **credentials dedicated to SMTP**, an app password, a token, or another authentication mechanism. Use exactly the kind of credential the provider issues.

### "The host must be the recipient's MX"

No. With the common configuration, the host is the application's **SMTP submission relay**. The relay is responsible for routing and forwarding mail to the recipient's domain.

### "Just the four properties are enough to send email securely"

Not enough. You need appropriate TLS configuration, server identity, sending permission, the From address, secret management, and error handling. The four properties mainly describe the **connection and authentication**.

### "Having a password in application.properties but not committing it is safe"

You still need to consider where the file is stored, access permissions, copies, and how it is deployed. The file may be synchronized or backed up unintentionally. A secret store and a managed environment-variable supply mechanism are usually more suitable for production credentials.

### "Once connected to SMTP successfully, every email will reach the Inbox"

No. SMTP has many stages; the provider and the receiving system also handle sending permission, the destination address, spam policy, quota, and later delivery feedback.

## 16. Configuration reasoning exercises

**Scenario 1.** The provider requires `smtp.provider.example`, port 587, SMTP AUTH, and mandatory STARTTLS. Which groups of properties do you need?

You need `spring.mail.host`, `spring.mail.port`, the corresponding credentials, `mail.smtp.auth=true`, and `mail.smtp.starttls.enable=true` together with `required=true`, plus server identity verification per policy. Do not just set port 587 and consider that TLS.

**Scenario 2.** The application logs in with `mailer@example.org` but wants to send mail from `support@example.org`. Is setting only `spring.mail.username=mailer@example.org` enough?

No. You must set `From` on the message to `support@example.org` and ensure the SMTP provider allows that identity. `username` does not automatically become `From`.

**Scenario 3.** The configuration is complete, but when running in Docker, `spring.mail.host=localhost` fails to connect. Why?

`localhost` points to the application container itself. If the SMTP relay runs on the host machine or in another container, you need a hostname or network configuration that corresponds to where the SMTP server actually runs.

**Scenario 4.** The application uses port 465 implicit TLS but only enables `starttls.enable=true`. What can happen?

The client may start with the wrong kind of connection relative to the server, causing a timeout or a TLS handshake error. You need to use `mail.smtp.ssl.enable=true` for implicit TLS according to the provider's requirements.

**Scenario 5.** The SMTP test server does not require authentication. Is it mandatory to set a fake username/password?

No. Only supply the properties the environment actually requires. Also ensure the SMTP test server is not accessed without authorization from outside the test environment.

**Scenario 6.** The mail was submitted to the relay but the recipient has not seen it. Can you fix it by only changing `spring.mail.password`?

There is no basis for that. You need to examine the delivery status, bounces, spam, the recipient address, and the provider's policy. A correct password only solves part of the authentication needed to submit mail.

## 17. A mnemonic model

When reading the four Spring Boot mail properties, you can ask four questions:

| Question | Answering property |
| --- | --- |
| **Which server to connect to?** | `spring.mail.host` |
| **Through which port to connect?** | `spring.mail.port` |
| **Which identity to log in with?** | `spring.mail.username` |
| **What secret to authenticate with?** | `spring.mail.password` |

The next questions lie elsewhere: **Is TLS mandatory?** → `spring.mail.properties.mail.smtp.*`; **what From/To/Subject/body does the mail have?** → the message-creating code; **has the mail been delivered yet?** → the SMTP relay and the email infrastructure's tracking mechanism.

A maintainable Spring Boot configuration is one with a **clear host/port**, **credentials taken from an appropriate secret source**, **TLS that is correct for the provider**, and business code that only uses `JavaMailSender`. Mastering this boundary lets you change the environment or SMTP provider while keeping the mail-sending logic clear, while also reducing connection and authentication errors and the leaking of secrets.

