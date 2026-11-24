# spring.mail.protocol and test-connection in Spring Boot Mail

When a Spring Boot application sends email with `JavaMailSender`, two configuration questions commonly arise: **which protocol the application will use to connect to the mail-sending server** and **whether the connection should be checked as soon as the application starts**. Spring Boot provides two direct properties for those two needs:

- `spring.mail.protocol` selects the Jakarta Mail transport protocol, usually `smtp` or `smtps`.
- `spring.mail.test-connection` asks Spring Boot to check the sender's ability to connect during application initialization, when the auto-configuration mechanism applies.

The two properties have very different purposes. `protocol` affects **how the library creates the transport and opens the SMTP session**. `test-connection` affects **when the application tries to connect and how startup reacts to errors**. Enabling the connection check does not automatically send a test email, nor does it prove the email will be delivered to the recipient's mailbox.

## 1. Where the two properties sit in the email-sending flow

A Spring Boot application can use `spring-boot-starter-mail` to get a `JavaMailSender`. A simple flow:

```text
application.properties / application.yml
    |
    +--> spring.mail.host
    +--> spring.mail.port
    +--> spring.mail.username / password
    +--> spring.mail.protocol
    +--> spring.mail.properties.mail.* (TLS, auth, timeout...)
    +--> spring.mail.test-connection
                |
                v
       Spring Boot Mail Auto-configuration
                |
                v
       JavaMailSenderImpl bean
                |
                +--> [when test-connection is enabled]
                |      open transport, connect, close
                |
                +--> [when a service needs to send]
                       JavaMailSender.send(...)
                            |
                            v
                        SMTP / ESP
```

Remember: the mail-sending configuration belongs to the application's **SMTP infrastructure**. `SimpleMailMessage` or `MimeMessage` objects only carry the data of each individual mail; they do not decide whether the application runs a connection check at startup.

Quick distinction table:

| Property | Example | Main effect | Is not |
| --- | --- | --- | --- |
| `spring.mail.protocol` | `smtp`, `smtps` | Selects the transport name for Jakarta Mail to use | A single TLS on/off flag |
| `spring.mail.test-connection` | `true`, `false` | Tries to connect at startup and reports an error if it cannot connect | A test email or a delivered verification |
| `spring.mail.host` | `smtp.example.com` | The destination SMTP server | The `From` domain that appears in the email |
| `spring.mail.port` | `587`, `465` | The connection port | A guarantee that TLS is enabled correctly |
| `spring.mail.properties.mail.smtp.*` | `auth`, `starttls.enable`, `timeout` | Jakarta Mail protocol options | General configuration usable with every protocol prefix |

## 2. How does Spring Boot create `JavaMailSender`?

In a Spring Boot project using Maven:

```xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-mail</artifactId>
</dependency>
```

If using Gradle:

```groovy
implementation 'org.springframework.boot:spring-boot-starter-mail'
```

The starter adds the components needed for Spring Mail and Jakarta Mail. When the auto-configuration conditions are met, for example there is mail host information or a supported way to create a mail session and no custom sender bean has replaced it, Spring Boot can create a `JavaMailSenderImpl` to inject into services.

Example:

```java
package example.notification;

import org.springframework.mail.SimpleMailMessage;
import org.springframework.mail.javamail.JavaMailSender;
import org.springframework.stereotype.Service;

@Service
public class AccountMailService {
    private final JavaMailSender mailSender;

    public AccountMailService(JavaMailSender mailSender) {
        this.mailSender = mailSender;
    }

    public void sendWelcome(String recipient) {
        SimpleMailMessage message = new SimpleMailMessage();
        message.setFrom("no-reply@example.com");
        message.setTo(recipient);
        message.setSubject("Welcome");
        message.setText("Your account has been created successfully.");
        mailSender.send(message);
    }
}
```

The service depends only on the `JavaMailSender` interface. `spring.mail.protocol` and `spring.mail.test-connection` are declared in the application configuration instead of being put into each mail-sending call.

### Scope of auto-configuration

`spring.mail.test-connection=true` is **not a command to create the sender bean** when the application is missing the dependency or has no configuration that creates a suitable mail sender. It only controls the checking mechanism on a sender that Spring Boot recognizes and supports in the actual configuration.

If the application creates its own custom `JavaMailSender` implementation or skips auto-configuration, you should not assume the connection-check property will work automatically on that implementation. You need to determine how the bean is created and which validator mechanism is applied in the Spring Boot version in use.

## 3. What is `spring.mail.protocol`?

`spring.mail.protocol` selects the transport protocol that `JavaMailSenderImpl` uses through Jakarta Mail. The usual default value is `smtp`.

Example:

```properties
spring.mail.host=smtp.example.com
spring.mail.port=587
spring.mail.protocol=smtp
```

Here, `protocol=smtp` means the application uses the SMTP transport. It **does not mean the connection will be unencrypted**. The SMTP transport can:

- connect and communicate over unencrypted SMTP if the configuration and server allow it;
- upgrade to TLS with **STARTTLS** on an already-open SMTP connection;
- or use **TLS from the start** when SSL is enabled for the `smtp` transport.

Therefore, you cannot rely on `spring.mail.protocol` alone to conclude the level of connection protection. You need to look at **protocol, port, TLS settings, authentication** and the SMTP provider's policy together.

### How do `smtp` and `smtps` differ?

`smtp` and `smtps` are **protocol names** supported by the Jakarta Mail library through the corresponding transport provider. `smtps` is the SMTP variant that uses a TLS connection from the start, commonly called *implicit TLS*.

| Case | `spring.mail.protocol` | Common port | TLS mechanism | Jakarta Mail properties |
| --- | --- | --- | --- | --- |
| SMTP with STARTTLS | `smtp` | `587` | Open SMTP and then upgrade with the `STARTTLS` command | `mail.smtp.starttls.*` |
| SMTP with implicit TLS | `smtp` | `465` | Enable TLS right from connection with `mail.smtp.ssl.enable=true` | `mail.smtp.ssl.*` |
| SMTPS transport | `smtps` | `465` | TLS from the start via the `smtps` transport | `mail.smtps.*` |
| Unencrypted SMTP, if the system allows | `smtp` | Depends on the relay | No TLS | `mail.smtp.*` |

Ports 587 and 465 are common configurations, **not a rule guaranteed for every ESP or internal SMTP relay**. Always cross-check the host, port, TLS mode, and authentication mechanism with the specific provider.

### A misunderstanding about the protocol name

Do not configure:

```properties
spring.mail.protocol=https
```

`https` is a web protocol, not an SMTP transport of the mail library. Similarly, `spring.mail.protocol=465` does not mean choosing port 465. The protocol property selects the **transport name**, while the port must be declared via `spring.mail.port`.

If you choose a transport name that the library does not support, creating or using the transport may raise an error. You should not use an arbitrary value without determining that the corresponding Jakarta Mail provider is already on the classpath.

## 4. Example SMTP configuration with STARTTLS

A common Spring Boot configuration:

```properties
spring.mail.host=smtp.example.com
spring.mail.port=587
spring.mail.protocol=smtp

spring.mail.username=${SMTP_USERNAME}
spring.mail.password=${SMTP_PASSWORD}
spring.mail.default-encoding=UTF-8

spring.mail.properties.mail.smtp.auth=true
spring.mail.properties.mail.smtp.starttls.enable=true
spring.mail.properties.mail.smtp.starttls.required=true

spring.mail.properties.mail.smtp.connectiontimeout=5000
spring.mail.properties.mail.smtp.timeout=10000
spring.mail.properties.mail.smtp.writetimeout=10000

spring.mail.test-connection=false
```

Meaning of each group:

1. `host`, `port`, and `protocol` determine the endpoint and the transport.
2. `username`/`password` supply the authentication information when the provider requires it. In practice, use environment variables or a secret manager.
3. `mail.smtp.auth=true` requests SMTP AUTH according to the server's capability.
4. `mail.smtp.starttls.enable=true` allows upgrading to TLS if the server supports it.
5. `mail.smtp.starttls.required=true` forces STARTTLS to be available; if there is no suitable TLS, the sending process does not continue as a plaintext SMTP connection.
6. The three timeouts prevent connect, read, and write operations from being blocked too long.
7. `test-connection=false` turns off the connection check at startup; a later mail-send call still has to connect to the actual SMTP.

**The difference between `enable` and `required`:** setting only `starttls.enable=true` does not always guarantee that the connection must have TLS. When policy requires mandatory encryption, you must set `starttls.required=true` or an equivalent TLS configuration supported by the provider.

The timeout values here are only illustrative; there is no single set of parameters suitable for every provider.

## 5. Example implicit TLS configuration on port 465

There are two commonly seen ways to organize the configuration, and you need to **choose one consistently**.

### Option A: Use the `smtp` transport with SSL enabled

```properties
spring.mail.host=smtp.example.com
spring.mail.port=465
spring.mail.protocol=smtp

spring.mail.username=${SMTP_USERNAME}
spring.mail.password=${SMTP_PASSWORD}

spring.mail.properties.mail.smtp.auth=true
spring.mail.properties.mail.smtp.ssl.enable=true
spring.mail.properties.mail.smtp.connectiontimeout=5000
spring.mail.properties.mail.smtp.timeout=10000
spring.mail.properties.mail.smtp.writetimeout=10000
```

Here, the protocol is still `smtp`, but `mail.smtp.ssl.enable=true` requires a TLS connection from the start. The properties continue to use the `mail.smtp.` prefix because the selected transport name is `smtp`.

### Option B: Choose the `smtps` transport

```properties
spring.mail.host=smtp.example.com
spring.mail.port=465
spring.mail.protocol=smtps

spring.mail.username=${SMTP_USERNAME}
spring.mail.password=${SMTP_PASSWORD}

spring.mail.properties.mail.smtps.auth=true
spring.mail.properties.mail.smtps.connectiontimeout=5000
spring.mail.properties.mail.smtps.timeout=10000
spring.mail.properties.mail.smtps.writetimeout=10000
```

Because `smtps` is a separate transport name, the ordinary transport options are looked up under **`mail.smtps.*`**, not `mail.smtp.*`.

A configuration error that is easy to make:

```properties
spring.mail.protocol=smtps
spring.mail.properties.mail.smtp.auth=true
spring.mail.properties.mail.smtp.timeout=10000
```

The author may think the `smtp` properties apply to `smtps`. But when the `smtps` transport is chosen, the properties specific to this protocol usually need the `mail.smtps.*` prefix. A wrong prefix can make timeouts or authentication not work as expected.

**You do not need to add `mail.smtps.starttls.enable=true` to request STARTTLS on implicit TLS.** STARTTLS is a connection-upgrade mechanism; implicit TLS protects from the start. The two approaches have different protocol behaviors.

### Note about TLS certificates

Whether a TLS connection succeeds or fails also depends on the server certificate, the hostname, the trust store, and identity-checking policies. In a production system, you need to configure TLS to **verify the server identity**, and not skip certificate validation merely to make a connection error go away. Properties such as `mail.smtp.ssl.checkserveridentity` or `mail.smtps.ssl.checkserveridentity` may be relevant depending on the transport and implementation; the default hostname verification behavior needs to be checked in the Jakarta Mail version and the actual security configuration.

## 6. What does `spring.mail.test-connection` do?

`spring.mail.test-connection` is a Spring Boot boolean property, usually `false` by default.

```properties
spring.mail.test-connection=true
```

When enabled, in supported Spring Boot Mail configurations, Spring initializes a sender-checking component and invokes an operation equivalent to `JavaMailSenderImpl.testConnection()` during context initialization.

The nature of this operation is:

1. Obtain the transport matching `spring.mail.protocol`.
2. Try to **open a connection** to the SMTP host/port.
3. Perform the steps needed to open the session, such as TLS/authentication per the configuration.
4. Close the transport after the check.
5. If it cannot connect, report the error, which may cause the **Spring ApplicationContext to fail to start**.

It **does not send a test email** to a recipient, does not run the full `MAIL FROM`/`RCPT TO`/`DATA` commands of a business email, and does not receive the final response of the receiving mail system.

Diagram:

```text
Spring Boot starts
        |
        v
Create / configure JavaMailSenderImpl
        |
        v
spring.mail.test-connection = true?
        |
        +-- No ---> continue startup
        |
        +-- Yes ----> open the SMTP/SMTPS connection
                         |
                          +-- Success --> close the transport
                          |                 --> startup continues
                         |
                          +-- Failure ----> bean/context initialization error
                                            --> the application may not come up
```

### Why is this called startup validation?

When sending email is a mandatory function of the application, knowing that SMTP is misconfigured right at deployment time can be useful. For example:

- Wrong host/port or a network policy blocks outbound traffic.
- Wrong username/password, the server requires authentication.
- The server requires TLS but the client is configured wrongly.
- The SMTP server is temporarily unavailable.

Instead of only detecting the error when a user later triggers sending mail, the system can learn early, right at startup.

However, SMTP availability is a condition that **varies over time**. A successful connection at 9:00 does not prove it will still work at 9:05. `test-connection` is a check at a given point in time, not continuous monitoring.

## 7. What does a connection check prove and not prove?

Boundary table:

| Question | Does `test-connection=true` answer it? | Explanation |
| --- | --- | --- |
| Can the application try to open an SMTP transport? | Yes | That is the main goal |
| Are the host/port reachable at startup time? | Usually yes | If the connection completes |
| Is the TLS/auth configuration sufficient to open the transport? | Usually yes | Depends on the server's requirements and how the transport connects |
| Is the optional `From` permitted by the provider? | **Not certain** | The sender policy may only be checked at `MAIL FROM` or at send time |
| Is a given `To` address accepted? | No | Mail delivery to a specific recipient has not been performed |
| Are the HTML/MIME/attachments correct? | No | A business message is not created and transmitted |
| Does the receiving-side MX accept the email? | No | No mail has been sent out yet |
| Does the email land in the inbox or spam? | No | That is a result at the receiving/classification layer |
| Does the user open or click the email? | No | That belongs to post-send interaction telemetry |
| Will SMTP always be available after startup? | No | The check is a snapshot |

A notable case: an ESP may allow login and successfully open the transport but then reject `MAIL FROM` because the domain has not been verified, the sending quota is exhausted, the message is too large, or the account lacks sending permission. Therefore a connection test does not replace **a controlled test email** when you want to assess the end-to-end sending path.

### A connection test is not a mail delivery test

`JavaMailSender#send(...)` performs message sending. When it returns successfully, that usually only confirms the SMTP relay accepted the message at the application's connection boundary; it still **does not prove it was delivered to the mailbox**. `testConnection()` has an even narrower scope: it only checks that the transport connects and then closes it.

You can distinguish three levels:

```text
testConnection()
    └── Can an SMTP/SMTPS session be opened?

send(message)
    └── Does the SMTP relay accept the message-sending process?

ESP delivered event / receiving system
    └── Does the receiving server accept the message?

Inbox placement / human reading
    └── Needs another data source; SMTP does not prove it by itself
```

## 8. When should you enable test-connection?

There is no rule to set `true` for every service. The decision depends on the role of email in the application and how the application is deployed.

| Context | Option to consider | Reason |
| --- | --- | --- |
| A service whose only job is sending email, SMTP is a mandatory dependency | Can enable `true` | Detect configuration or connection errors at startup |
| A business API that must still serve when SMTP is temporarily failing | Usually consider `false` and a separate health/queue | Avoid the whole application failing to start just because of email |
| Local environment without an SMTP server | `false` or use a test SMTP server | Do not make development depend on real email |
| Automated tests that do not need a network | `false`, use mock/fake | Tests are repeatable and do not depend on the external environment |
| A worker that only processes email with retry/backoff | Depends on the worker's readiness policy | Can check at startup but still needs retry after startup |
| Many replicas starting together or autoscaling | Consider connection load and external dependency | Avoid all replicas failing startup together when the ESP is flaky |

For example, a sales service can continue creating orders even when SMTP is slow, and then send notifications through an outbox/queue when the system recovers. If you enable `test-connection=true` across this entire API, an SMTP outage may stop a new deployment from coming up, even though the ordering business could still be served. Conversely, for a worker dedicated to sending email with no other function, failing fast when the SMTP configuration is wrong may be reasonable.

### Fail-fast startup and recoverability

`test-connection=true` helps detect errors but also creates a **startup dependency on SMTP**. If the ESP temporarily loses connectivity during deployment, the application may fail to initialize. With Kubernetes or platforms that have automatic restart mechanisms, this can lead to a startup-failure loop until SMTP recovers.

Instead, you can:

- Start the application without requiring SMTP to be always online.
- Handle send requests with a durable queue/outbox.
- Let the worker apply timeouts and bounded retries.
- Raise an alert when the job backlog or SMTP errors exceed a threshold.
- Include SMTP in readiness only if the instance's function truly cannot operate when SMTP is not available.

The choice reflects an **operational policy**, not something that is always technically "more correct".

## 9. Per-environment configuration with Spring profiles

An application may want to enable the connection test in production but disable it in local/CI, or the reverse depending on need. Use Spring profiles to separate these values.

Example of the common `application.yml` file:

```yaml
spring:
  mail:
    host: smtp.example.com
    port: 587
    protocol: smtp
    username: ${SMTP_USERNAME}
    password: ${SMTP_PASSWORD}
    test-connection: false
    properties:
      "[mail.smtp.auth]": true
      "[mail.smtp.starttls.enable]": true
      "[mail.smtp.starttls.required]": true
      "[mail.smtp.connectiontimeout]": 5000
      "[mail.smtp.timeout]": 10000
      "[mail.smtp.writetimeout]": 10000
```

A separate `application-mail-worker.yml`:

```yaml
spring:
  mail:
    test-connection: true
```

When running with the `mail-worker` profile, the appropriate configuration is overridden. For example:

```properties
spring.profiles.active=mail-worker
```

In a real system, you should usually choose the profile in the runtime environment or on the command line instead of committing a fixed active profile for every environment. Do not put production accounts/passwords directly in configuration files.

### Configuration with environment variables

Spring Boot has relaxed binding for simple properties. For example:

```text
SPRING_MAIL_PROTOCOL=smtp
SPRING_MAIL_TEST_CONNECTION=true
```

However, the deeply nested keys of `spring.mail.properties.mail.smtp.*` need to be mapped correctly under the configuration binding mechanism. Using `application.properties`/`application.yml` with dotted keys is the more readable and less error-prone way; if configuring entirely from the environment, you need to verify the actual values bound into the Jakarta Mail properties.

When there are multiple configuration sources (defaults, profile, environment, command-line, secret manager), the **source with higher precedence** can override values from files. Therefore, if the startup behavior differs from what you want, first check the effective configuration and the active profile, avoiding exposing passwords in logs.

## 10. test-connection combined with timeouts: configuration you cannot do without

A common mistake is to enable:

```properties
spring.mail.test-connection=true
```

but not configure socket timeouts. When the SMTP endpoint does not respond, the check step may wait too long, slowing down startup.

Three properties of interest:

```properties
spring.mail.properties.mail.smtp.connectiontimeout=5000
spring.mail.properties.mail.smtp.timeout=10000
spring.mail.properties.mail.smtp.writetimeout=10000
```

They mean:

- **Connection timeout**: limits the time to open the TCP connection.
- **Read timeout**: limits the time to wait for a data-receive operation from the SMTP server.
- **Write timeout**: limits the time a write operation on the socket can be blocked.

When using the `smtps` transport, use the corresponding prefix:

```properties
spring.mail.properties.mail.smtps.connectiontimeout=5000
spring.mail.properties.mail.smtps.timeout=10000
spring.mail.properties.mail.smtps.writetimeout=10000
```

Do not treat these three timeouts as a total deadline for startup or `send()`. DNS resolution, multiple sequential reads/writes, and TLS steps can make the total time exceed each individual threshold. When the SMTP dependency affects startup time, you should observe startup latency and set an appropriate deployment policy.

### Read timeout matters for the connection test too

An endpoint may accept TCP quickly but **not send the SMTP banner** or respond slowly during STARTTLS/AUTH. `connectiontimeout` cannot handle every such case. `mail.smtp.timeout` is what helps prevent a read from hanging.

### Write timeout is not only for attachments

In a connection-check session, there can still be protocol write operations such as `EHLO`, `STARTTLS`, and `AUTH`. In a real mail-sending session, the write timeout matters even more when transmitting the body or attachments. Both contexts need correct configuration when a socket write may block.

## 11. Calling `testConnection()` yourself when configuring the bean manually

When the application does not use Spring Boot's auto-configured connection-check mechanism, `JavaMailSenderImpl` has a `testConnection()` method that can be called directly at the infrastructure layer or in a controlled diagnostic command.

Example code using an already-initialized bean:

```java
package example.mail;

import jakarta.mail.MessagingException;
import org.springframework.mail.javamail.JavaMailSenderImpl;

public class MailConnectionDiagnostic {
    private final JavaMailSenderImpl sender;

    public MailConnectionDiagnostic(JavaMailSenderImpl sender) {
        this.sender = sender;
    }

    public void verifySmtpConnection() throws MessagingException {
        sender.testConnection();
    }
}
```

The code illustrates the API and does not create a startup check by itself. To call it at startup, you can create a suitable initializing bean or runner, but you need to consider whether failing startup matches the operational intent.

If you use `JavaMailSender` through the interface, remember that **`testConnection()` is an API on `JavaMailSenderImpl`** and not a required method of every `JavaMailSender` implementation. Therefore, business code that sends email should continue to depend on the interface; the transport-checking code may live in a separate infrastructure class that knows precisely which implementation type it is checking.

### A manual `@Bean` sender

```java
package example.mail;

import java.util.Properties;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.mail.javamail.JavaMailSender;
import org.springframework.mail.javamail.JavaMailSenderImpl;

@Configuration
public class ManualMailConfiguration {
    @Bean
    public JavaMailSender mailSender() {
        JavaMailSenderImpl sender = new JavaMailSenderImpl();
        sender.setHost("smtp.example.com");
        sender.setPort(587);
        sender.setProtocol("smtp");
        sender.setUsername(System.getenv("SMTP_USERNAME"));
        sender.setPassword(System.getenv("SMTP_PASSWORD"));

        Properties settings = new Properties();
        settings.put("mail.smtp.auth", "true");
        settings.put("mail.smtp.starttls.enable", "true");
        settings.put("mail.smtp.starttls.required", "true");
        settings.put("mail.smtp.connectiontimeout", "5000");
        settings.put("mail.smtp.timeout", "10000");
        settings.put("mail.smtp.writetimeout", "10000");

        sender.setJavaMailProperties(settings);
        return sender;
    }
}
```

`sender.setProtocol("smtp")` here corresponds in purpose to `spring.mail.protocol=smtp` when Boot configures the sender. However, if you have created the bean manually as above, the `spring.mail.*` properties are **not necessarily still bound into that bean by Boot**. Do not keep two configuration sources at the same time without knowing which one is actually used.

If you enable `spring.mail.test-connection=true`, whether Boot's validator applies to a self-declared bean also depends on the bean type and the auto-configuration conditions/version. The safe approach is to determine clearly the sender's lifecycle in the project; do not assume a property takes effect on every custom bean.

## 12. Startup errors and how to diagnose them

When `spring.mail.test-connection=true`, an SMTP error can make the context fail to start or cause a BeanCreationException to appear. The inner message may contain a cause from Jakarta Mail or Java networking.

| Symptom/cause | Possible cause | How to handle |
| --- | --- | --- |
| `UnknownHostException` | DNS cannot resolve the hostname | Check `spring.mail.host`, DNS, and network policy |
| `ConnectException: Connection refused` | The port is not open or the endpoint refuses | Check the host, port, and outbound firewall |
| `SocketTimeoutException: connect timed out` | The TCP connect does not complete | Check network connectivity, firewall dropping packets, and the connection timeout |
| `SocketTimeoutException: Read timed out` | The server does not return data on time | Check the SMTP banner, TLS/auth, and the read timeout |
| `535 Authentication failed` or similar error | Wrong username/password or authentication method | Check the secret, the account, and the provider's requirements |
| `SSLHandshakeException` | Certificate, hostname, or TLS protocol error | Verify the certificate chain, trust store, and TLS mode |
| STARTTLS-not-supported message | The server has no STARTTLS or the wrong port/mode is used | Choose the right protocol/port; do not carelessly turn off TLS |
| Transport provider not found | `spring.mail.protocol` is invalid or a dependency is missing | Check the protocol name and the Jakarta Mail implementation |
| Startup succeeds but a real mail send is rejected | Sender address, recipient, quota, size, or policy is checked at send time | Check the SMTP reply and ESP logs; test connection does not cover it |

### Wrong port and TLS mode can create confusing symptoms

Example:

```properties
spring.mail.protocol=smtp
spring.mail.port=465
spring.mail.properties.mail.smtp.starttls.enable=true
```

If the actual 465 endpoint **requires TLS from the start**, an ordinary SMTP client is waiting for a plaintext banner, while the server waits for the client to begin the TLS handshake. This mismatch can produce a read timeout or a protocol error.

The correct configuration should be one of the forms compatible with the server:

```properties
# One way to use implicit TLS with the smtp transport:
spring.mail.protocol=smtp
spring.mail.port=465
spring.mail.properties.mail.smtp.ssl.enable=true
```

or:

```properties
# Use the smtps transport:
spring.mail.protocol=smtps
spring.mail.port=465
spring.mail.properties.mail.smtps.auth=true
```

Do not fix the error by increasing the timeout indefinitely. Determine first whether the server uses STARTTLS or implicit TLS.

### An authentication error is not necessarily a password error

The server may reject because the account is locked, the application password has not been issued, the IP is not permitted, the AUTH mechanism is not supported, or the security policy does not accept the login method. Check the information from the SMTP provider; avoid writing or sharing the authentication information verbatim in diagnostic logs.

## 13. Testing and CI environments

`test-connection=true` can make a test that loads the whole Spring ApplicationContext depend on a real SMTP. This makes tests prone to failure because of DNS, firewalls, provider outages, or missing secrets.

For service **unit tests**, usually you only need to mock `JavaMailSender`:

```java
package example.mail;

import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.verify;

import org.junit.jupiter.api.Test;
import org.springframework.mail.SimpleMailMessage;
import org.springframework.mail.javamail.JavaMailSender;

class AccountMailerTest {
    @Test
    void sendsMessageThroughInjectedSender() {
        JavaMailSender sender = mock(JavaMailSender.class);

        SimpleMailMessage message = new SimpleMailMessage();
        message.setTo("test@example.net");
        message.setSubject("Test");
        message.setText("Hello");

        sender.send(message);

        verify(sender).send(message);
    }
}
```

The example only illustrates how a mock can be used when a test calls `send`. In a real business unit test, you need to inject the mock into the **service under test**, trigger the service's behavior, and then verify the content that was sent.

For a mail configuration **integration test**, you can run a local SMTP test server or a simulated SMTP container, then set `spring.mail.host` and `spring.mail.port` to that endpoint. When you want to test startup validation, enable `test-connection=true` in a controlled test environment.

Example configuration for a test SMTP server on the local machine:

```properties
spring.mail.host=127.0.0.1
spring.mail.port=2525
spring.mail.protocol=smtp
spring.mail.test-connection=true

spring.mail.properties.mail.smtp.auth=false
spring.mail.properties.mail.smtp.starttls.enable=false
spring.mail.properties.mail.smtp.connectiontimeout=2000
spring.mail.properties.mail.smtp.timeout=3000
spring.mail.properties.mail.smtp.writetimeout=3000
```

This configuration is only suitable if the test SMTP server actually listens on port 2525 and allows connections without authentication/TLS. **Do not use such a plaintext configuration for production Internet SMTP.**

### Different levels of testing

| Test type | Goal | Is `test-connection` enough? |
| --- | --- | --- |
| Content-creation unit test | Check To, Subject, body, template | No SMTP connection needed |
| Startup connection test | Verify the transport can connect | Can use `true` |
| SMTP integration test | Verify sending commands/data and MIME | Need to send mail into an SMTP test server |
| Provider acceptance test | Check sender/domain/quota/policy | Need a real send test per the provider's rules |
| End-to-end delivery test | Confirm delivered/bounce at the destination system | Need ESP events or a test mailbox |

When using CI, you should not let every unit test inadvertently connect to a production SMTP account. Secrets and the external network make tests slow, unstable, and able to create unintended real send requests.

## 14. test-connection does not replace continuous health checks

Spring Boot has the Actuator system to provide health/readiness according to configuration and supporting components. However, `spring.mail.test-connection` by itself is a **startup check**, not a periodic check schedule.

A separate health indicator or probe can check SMTP connectivity, but you need to consider the impact:

- Each SMTP session opening may cost DNS, TCP, TLS, AUTH, and provider resources.
- Calling at too high a frequency can increase the number of connections, hit throttling, or cause the server's security to detect unusual logins.
- Putting an SMTP outage into the readiness of **every** HTTP instance can cause traffic to be pulled from the whole application even though other APIs still work.
- If you use `testConnection()` synchronously in a health request, the probe can hang when there is no timeout.
- One successful check does not guarantee later sends will succeed.

For a system that sends email via a queue, metrics such as **number of pending jobs**, **age of the oldest job**, **send error rate**, **retry backlog**, **bounce rate**, and **provider API status** usually provide a more useful operational picture than opening a new SMTP connection every second.

If you need a dynamic health indicator for SMTP, you should determine the deployment scope, frequency, timeout, and effect on readiness/liveness deliberately. Do not confuse a startup check with recoverability.

## 15. A few frequently asked questions

### Is it only with `spring.mail.protocol=smtps` that email is sent securely?

No. `smtp` can use STARTTLS or implicit TLS when configured correctly. `smtps` is the transport name for implicit TLS; security depends on the TLS settings, the certificate, authentication, the SMTP and server policy, not just the protocol name.

### Is it OK to set `spring.mail.protocol=smtp` with port 465?

Yes, **if** you use `mail.smtp.ssl.enable=true` and the provider requires implicit TLS. If you only enable STARTTLS against an endpoint that only accepts TLS from the first byte, you may get a timeout or a handshake error.

### Does `spring.mail.test-connection=true` automatically send a mail to the configured account?

No. It checks the ability to open the SMTP transport and closes it again. No recipient address or test mail content is sent just because of this property.

### Why does it start up but `send()` still fails?

Because the startup check does not cover the rules for `From`, `To`, message size, MIME content, quota limits, or network state that changes after startup. The provider may only reject when a mail-sending command is actually issued.

### If test connection is turned off, can mail still be sent?

Yes. `spring.mail.test-connection=false` only skips the check at startup. When a service calls `send()`, the transport still connects and sends the mail according to the normal SMTP configuration.

### Should you set `test-connection=true` to use it as a readiness probe?

Not by default. This property only affects startup. A readiness probe needs its own design, considering whether an SMTP outage truly prevents the instance from serving its main functions.

### Does changing `spring.mail.protocol` require changing other properties?

Usually yes. If you change from the `smtp` to the `smtps` transport, the specific options such as `auth` and timeouts may need their prefix changed from `mail.smtp.*` to `mail.smtps.*`. In addition, you need to align the port and TLS mode with the provider.

## 16. How to implement it in a real project

Suppose an application has an ordering API and a separate email-sending worker. The two components use the same SMTP provider but have different availability requirements.

**Ordering API configuration:** The API must be able to serve even when the ESP is temporarily failing. It writes email requests into an outbox for the worker to process. In this environment, enabling test-connection on the API is not necessarily useful, especially if the API does not send SMTP directly. Prefer letting the API start up and keep the outbox safe.

**Email-sending worker configuration:** The worker needs an SMTP connection to do its main job. You can use:

```properties
spring.mail.host=smtp.example.com
spring.mail.port=587
spring.mail.protocol=smtp

spring.mail.username=${SMTP_USERNAME}
spring.mail.password=${SMTP_PASSWORD}

spring.mail.properties.mail.smtp.auth=true
spring.mail.properties.mail.smtp.starttls.enable=true
spring.mail.properties.mail.smtp.starttls.required=true

spring.mail.properties.mail.smtp.connectiontimeout=5000
spring.mail.properties.mail.smtp.timeout=10000
spring.mail.properties.mail.smtp.writetimeout=10000

spring.mail.test-connection=true
```

If the worker cannot connect right from the start, the startup error signals that the configuration or the network has a problem. However, the worker must still be designed with **retry/backoff** at runtime because SMTP can drop after a successful startup.

**In CI:** Unit tests do not connect to a real SMTP; integration tests use an SMTP test server managed in the test environment. You can enable test connection for a specific startup test to confirm the correct behavior.

**In operations:** Observe the events of connection, sending, authentication errors, timeouts, backlog, and delivered/bounce. Do not equate a "green startup test" with "every email has been delivered successfully".

## 17. Key takeaways

The two properties work together, but at two different layers:

```text
spring.mail.protocol
  = choice of the SMTP/SMTPS transport
  = affects the property prefix, the TLS mode, and how the connection is made

spring.mail.test-connection
  = whether a trial open/close of the transport is performed at startup
  = helps detect connection/configuration errors early
  = does not create a test email, does not prove delivered
```

When configuring Spring Boot Mail, **choose the protocol according to the SMTP provider's requirements**, set the corresponding host/port/TLS/auth/timeouts, and enable `test-connection` only when depending on SMTP right at startup fits the operational architecture. A successful connection test is a signal of the transport's availability at that moment; the ability to send, deliver, and read email needs to be verified with separate mechanisms.
