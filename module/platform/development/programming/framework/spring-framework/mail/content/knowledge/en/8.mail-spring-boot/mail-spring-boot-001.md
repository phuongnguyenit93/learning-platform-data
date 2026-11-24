# Auto-configuration for the mail sender

## 1. What does it mean for Spring Boot to auto-configure a mail sender?

In **Spring Framework Mail**, an application typically uses the **MailSender** or **JavaMailSender** interface to send email. A common implementation is **JavaMailSenderImpl**, which uses Jakarta Mail to communicate with an SMTP server. With plain Spring Framework alone, the developer must create and configure the mail-sending bean manually or use an equivalent configuration mechanism.

**Spring Boot auto-configuration** handles most of this initial wiring: when the application has the required libraries, has appropriate mail configuration, and has not declared a replacement mail-sending bean, Boot can automatically create a **JavaMailSender** bean for the Spring container. A service only needs to request the interface through dependency injection.

Usage example:

~~~java
import org.springframework.mail.SimpleMailMessage;
import org.springframework.mail.javamail.JavaMailSender;
import org.springframework.stereotype.Service;

@Service
public class RegistrationMailService {

    private final JavaMailSender mailSender;

    public RegistrationMailService(JavaMailSender mailSender) {
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
~~~

In the example, **RegistrationMailService does not instantiate JavaMailSenderImpl itself**. If the auto-configuration conditions are met, Spring Boot creates the bean and Spring injects it into the constructor. The business code does not need to know the SMTP host, the port, how the Jakarta Mail Session is created, or any connection details.

However, **auto-configuration does not mean an SMTP server is already available**, and it also does not mean that merely adding the dependency will make emails send themselves. The application still needs server details, sending permission, network connectivity, and an appropriate mail-sending policy.

## 2. Roles of Spring Framework, Jakarta Mail, and Spring Boot

To correctly understand the scope of auto-configuration, you need to separate the three layers:

| Layer | Components | Responsibility |
|---|---|---|
| **Business code** | RegistrationMailService, NotificationService | Decides what email to send, to whom, and when. |
| **Spring Framework Mail** | MailSender, JavaMailSender, JavaMailSenderImpl, MimeMessageHelper | Provides the API for creating and sending messages; implements sending through the mail platform. |
| **Jakarta Mail** | Session, MimeMessage and the SMTP transport | The API/mechanism for handling MIME, the mail session, and communication with the server. |
| **Spring Boot** | Mail auto-configuration, MailProperties, starter | Brings the dependencies and configuration together, automatically registering the bean when conditions are met. |
| **External infrastructure** | SMTP relay, email service provider, destination mail server | Accepts, routes, delivers, and processes the message across the hops. |

Visualizing the relationships:

~~~text
                  Spring Boot application
                           |
                  @Service / Controller
                           |
                    JavaMailSender
                           ^
                            | auto-configured bean
                           |
               Spring Boot Mail auto-config
                           |
                           v
                   JavaMailSenderImpl
                           |
                           v
                       Jakarta Mail
                           |
                       SMTP/TLS
                           |
                           v
                 SMTP relay or email provider
                           |
                           v
                     Recipient's mail server
~~~

**JavaMailSender is a Spring Framework interface**, while **Spring Boot creates and configures the bean** from environment properties. From there, the ordinary work of sending mail is still performed by JavaMailSenderImpl/Jakarta Mail.

## 3. Adding the spring-boot-starter-mail dependency

For a **Spring Boot 3.x** application using Gradle:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-mail'
}
~~~

Or in Maven:

~~~xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-mail</artifactId>
</dependency>
~~~

Typically, the starter version is managed by the project's Spring Boot dependency management. The starter brings in the components needed for Spring Mail and a compatible Jakarta Mail implementation, so that auto-configuration has the necessary classes on the classpath.

In the Spring Boot 3 / Spring Framework 6 ecosystem, the underlying mail classes use **jakarta.mail**, for example:

~~~java
import jakarta.mail.internet.MimeMessage;
import org.springframework.mail.javamail.JavaMailSender;
import org.springframework.mail.javamail.MimeMessageHelper;
~~~

If a legacy project is still using Spring Boot 2 and **javax.mail**, do not copy and mix imports between the two generations. The Jakarta Mail namespace must match the framework and the dependencies in use.

**Adding the starter alone is not enough to configure the SMTP host.** In the common setup, you must set at least the sending server information via **spring.mail.host**, or configure an appropriate **Jakarta Mail Session** source such as JNDI if the environment uses JNDI.

## 4. Conditions Boot needs to create a JavaMailSender

Boot's auto-configuration follows the principle that it **applies only when appropriate and does not override configuration the application has explicitly declared**. With the common mail configuration of Spring Boot 3.x, the main conditions can be pictured as follows:

1. **The required classes are on the classpath**, including Spring Mail and the necessary Jakarta Mail APIs. The mail starter is the usual way to satisfy this.
2. **There is information to configure the sender**, usually **spring.mail.host** or **spring.mail.jndi-name** with a Jakarta Mail Session from JNDI.
3. **No MailSender bean has been declared by the application or another library**, so that Boot can provide a default bean without conflicting with the application's choice.
4. **Mail auto-configuration is not excluded** from the application startup process.

The auto-configuration class name in Spring Boot 3.x is **MailSenderAutoConfiguration**. Boot binds the properties under the **spring.mail** prefix through **MailProperties**, then configures the sender using those properties or a Session looked up through JNDI. The specific annotations and conditions may change between Boot versions, but the principle of classpath + configuration + bean not already present is the key point to grasp.

### Scenario table

| Scenario | Typical result |
|---|---|
| Mail starter present, spring.mail.host set, no custom MailSender declared | Boot can create a JavaMailSenderImpl bean and register it under the JavaMailSender interface. |
| Mail starter present but no suitable host/JNDI Session | The conditions for the default sender are not met; a service that needs to inject JavaMailSender may report a missing bean. |
| Appropriate Spring Mail/Jakarta Mail dependency missing | There are not enough classes for auto-configuration; the application cannot use the mail API as expected. |
| Application declares its own MailSender or JavaMailSender bean | Boot may **back off**, giving priority to the bean provided by the application. |
| Application declares multiple JavaMailSender beans | Injection by type alone may be ambiguous; usually @Qualifier or @Primary is needed. |
| Auto-configuration created the bean but the SMTP server is unreachable | The application may still start if the connection is not checked at startup; the error appears when sending or when connection checking is enabled. |

**Back off** means Boot does not try to create a default sender once it detects a suitable bean supplied by the application. It does not mean Spring will automatically fix or complete the configuration of the custom bean.

### A general condition diagram

~~~text
                  Spring Boot application starts
                               |
                     Required mail libraries?
                           /             \
                          No               Yes
                          |                |
                     Create no sender    Mail host/JNDI?
                                         /         \
                                        No         Yes
                                        |            |
                                   Do not create Another MailSender
                                   sender          bean exists?
                                                  /       \
                                                 Yes       No
                                                 |           |
                                             Back off      Create default
                                                          sender
~~~

This is an interpretive logic for learning purposes, not the verbatim source code of the auto-configuration.

## 5. Configuring SMTP with application.yml

A common example using SMTP submission over port **587** with STARTTLS:

~~~yaml
spring:
  mail:
    host: smtp.example.com
    port: 587
    username: ${SMTP_USERNAME}
    password: ${SMTP_PASSWORD}
    default-encoding: UTF-8
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
~~~

In this configuration, **smtp.example.com** is an illustrative address; it must be replaced with the provider's real SMTP host. **SMTP_USERNAME** and **SMTP_PASSWORD** are environment variables supplied securely at runtime. Do not put real passwords into committed files or logs.

Explanation:

| Property | Purpose |
|---|---|
| **spring.mail.host** | The SMTP server the application connects to. |
| **spring.mail.port** | The port for connecting to the SMTP server. |
| **spring.mail.username** | The login account name if the SMTP server requires authentication. |
| **spring.mail.password** | The credential for sending email; it should be managed as a secret. |
| **spring.mail.default-encoding** | The default charset used when building messages, for example UTF-8. |
| **spring.mail.properties.mail.smtp.auth** | Enables the SMTP AUTH mechanism in Jakarta Mail. |
| **spring.mail.properties.mail.smtp.starttls.enable** | Allows upgrading the connection to TLS via STARTTLS. |
| **spring.mail.properties.mail.smtp.starttls.required** | Requires STARTTLS to succeed instead of accepting sending without the upgrade. |
| **spring.mail.properties.mail.smtp.connectiontimeout** | Limits the wait time for establishing a connection, in milliseconds. |
| **spring.mail.properties.mail.smtp.timeout** | Limits the wait time for reading from the SMTP server, in milliseconds. |
| **spring.mail.properties.mail.smtp.writetimeout** | Limits the wait time for write operations over SMTP, in milliseconds. |

Properties under **spring.mail.properties** are converted into **Jakarta Mail properties**. For example, the YAML path **properties.mail.smtp.auth** becomes the key **mail.smtp.auth** in the Session. This is how Boot passes the underlying transport configuration without requiring the application to create the Session itself.

### Why do timeouts matter?

Without appropriate wait-time limits, a network problem or an unresponsive SMTP server can hold the sending thread far longer than expected. For an HTTP service that sends email synchronously, this increases latency or exhausts resources when there are many requests.

Timeout settings should match the service requirements, network latency, and retry policy. **A timeout does not guarantee the email has not been received by the server**: if the connection drops after the server has processed DATA but before it returns the acknowledgment, the application may not know the outcome for certain.

### Do not mix up TLS configuration

The example above is the **STARTTLS on port 587** model. Some services use **implicit TLS on port 465**, which requires the corresponding protocol configuration, typically:

~~~yaml
spring:
  mail:
    host: smtp.example.com
    port: 465
    username: ${SMTP_USERNAME}
    password: ${SMTP_PASSWORD}
    properties:
      mail:
        smtp:
          auth: true
          ssl:
            enable: true
          connectiontimeout: 5000
          timeout: 5000
          writetimeout: 5000
~~~

Do not change only the **port** by default while keeping the same TLS mechanism. Cross-check the host, port, STARTTLS/SSL, certificate, and authentication mechanism against the SMTP provider's guidance.

## 6. The flow from properties to the injected bean

When the conditions are met:

~~~text
application.yml / environment / secrets
                    |
                    | Externalized Configuration
                    v
              spring.mail.*
                    |
                    v
              MailProperties
                    |
                    v
        MailSenderAutoConfiguration
                    |
                    v
           JavaMailSenderImpl bean
                    |
                    | Dependency Injection
                    v
         @Service NotificationService
                    |
                    v
            mailSender.send(...)
~~~

This matches the dependency inversion principle: business code only knows **JavaMailSender**; the transport configuration is placed in the deployment environment. When you change the SMTP server, most of the change lies only in configuration, not in the mail-sending service.

**Note:** Spring Boot being able to create the bean does not mean it has automatically chosen the **From** address for every email. The From header address is usually set by the service using **SimpleMailMessage.setFrom(...)**, **MimeMessageHelper.setFrom(...)**, or a dedicated business configuration class.

## 7. Example of sending plain text with the auto-configured sender

After configuring the starter and SMTP, the following service can use the sender injected by Boot:

~~~java
package com.example.notification;

import org.springframework.mail.SimpleMailMessage;
import org.springframework.mail.javamail.JavaMailSender;
import org.springframework.stereotype.Service;

@Service
public class PasswordResetNotificationService {

    private final JavaMailSender mailSender;

    public PasswordResetNotificationService(JavaMailSender mailSender) {
        this.mailSender = mailSender;
    }

    public void sendResetLink(String recipient, String resetUrl) {
        SimpleMailMessage message = new SimpleMailMessage();
        message.setFrom("support@example.com");
        message.setTo(recipient);
        message.setSubject("Reset your password");
        message.setText("""
                You have requested a password reset.

                Visit the following link to continue:
                %s

                If you did not make this request, you can ignore this email.
                """.formatted(resetUrl));

        mailSender.send(message);
    }
}
~~~

**JavaMailSender** extends **MailSender**, so you can use **send(SimpleMailMessage)** even though the service depends on the JavaMailSender interface. When a simple email is needed, this API avoids having to build a MIME tree manually.

This sample serves to explain how auto-configuration is consumed. In a real application, the reset link must be a time-limited, hard-to-guess token with access control; do not put the token in logs. The service also needs to limit sending frequency and avoid revealing whether an account exists if there are security requirements.

## 8. Example of sending HTML with JavaMailSender and MimeMessageHelper

Spring Boot does not limit the automatically created sender to plain-text messages. The **JavaMailSender** bean can send MIME messages with HTML, an alternative text version, and file attachments.

~~~java
package com.example.notification;

import jakarta.mail.MessagingException;
import jakarta.mail.internet.MimeMessage;
import java.nio.charset.StandardCharsets;

import org.springframework.mail.javamail.JavaMailSender;
import org.springframework.mail.javamail.MimeMessageHelper;
import org.springframework.stereotype.Service;

@Service
public class InvoiceNotificationService {

    private final JavaMailSender mailSender;

    public InvoiceNotificationService(JavaMailSender mailSender) {
        this.mailSender = mailSender;
    }

    public void sendInvoiceNotice(String recipient, String invoiceCode)
            throws MessagingException {
        MimeMessage message = mailSender.createMimeMessage();
        MimeMessageHelper helper = new MimeMessageHelper(
                message,
                true,
                StandardCharsets.UTF_8.name()
        );

        helper.setFrom("billing@example.com");
        helper.setTo(recipient);
        helper.setSubject("Invoice notice " + invoiceCode);

        String plainText = "Invoice " + invoiceCode
                + " has been issued. Visit the customer portal to view the details.";
        String htmlText = "<html><body>"
                + "<h2>The invoice has been issued</h2>"
                + "<p>Please visit the customer portal to view the details.</p>"
                + "</body></html>";

        helper.setText(plainText, htmlText);
        mailSender.send(message);
    }
}
~~~

In the example:

1. **createMimeMessage()** creates the MIME object according to the sending configuration.
2. **MimeMessageHelper** configures the sender, recipient, subject, and content.
3. The **setText(plainText, htmlText)** overload creates two alternative representations per MIME, suitable for email clients that display plain text or HTML.
4. **send(message)** performs the mail-sending request through the bean that Boot has configured.

If you want to add an attachment, use **helper.addAttachment(...)** once multipart mode is enabled; if you want an inline image, you can use **helper.addInline(...)** with an appropriate MIME structure. This functionality belongs to Spring Framework Mail, while Boot helps register and configure the sender.

## 9. Customizing some values through external configuration

You should not hardcode the From address in many services when they all share one sending identity. **spring.mail** is mainly for mail transport configuration; the application can define its own properties, for example:

~~~yaml
app:
  notification:
    from: no-reply@example.com
    reply-to: support@example.com
~~~

Then inject them into the service:

~~~java
import org.springframework.beans.factory.annotation.Value;
import org.springframework.mail.SimpleMailMessage;
import org.springframework.mail.javamail.JavaMailSender;
import org.springframework.stereotype.Service;

@Service
public class StatusMailService {

    private final JavaMailSender sender;
    private final String from;
    private final String replyTo;

    public StatusMailService(
            JavaMailSender sender,
            @Value("${app.notification.from}") String from,
            @Value("${app.notification.reply-to}") String replyTo
    ) {
        this.sender = sender;
        this.from = from;
        this.replyTo = replyTo;
    }

    public void sendStatus(String recipient) {
        SimpleMailMessage message = new SimpleMailMessage();
        message.setFrom(from);
        message.setReplyTo(replyTo);
        message.setTo(recipient);
        message.setSubject("Processing status");
        message.setText("Your request has been processed.");
        sender.send(message);
    }
}
~~~

The **app.notification** property is a namespace defined by the application itself; Spring Boot does not automatically turn it into mail headers. The service needs to use it to set the **From** and **Reply-To** headers.

This also shows that you must distinguish between:

- **SMTP username**: the authentication information when the application submits mail.
- **From header**: the sending address that the recipient sees.
- **Reply-To**: where email clients usually direct replies.
- **SMTP envelope sender / return path**: the sender information used in transport and bounce handling.

These values may differ but must conform to the SMTP provider's policy, the right to use the address, and the domain authentication configuration.

## 10. If the application has already declared its own JavaMailSender

Auto-configuration usually applies the **back off** principle when it detects a suitable sender bean. This is useful because the application can decide the configuration itself when it has special requirements.

Example of registering your own sender:

~~~java
import java.util.Properties;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.mail.javamail.JavaMailSender;
import org.springframework.mail.javamail.JavaMailSenderImpl;

@Configuration
public class CustomMailConfiguration {

    @Bean
    public JavaMailSender javaMailSender(
            @Value("${app.smtp.host}") String host,
            @Value("${app.smtp.port}") int port,
            @Value("${app.smtp.username}") String username,
            @Value("${app.smtp.password}") String password
    ) {
        JavaMailSenderImpl sender = new JavaMailSenderImpl();
        sender.setHost(host);
        sender.setPort(port);
        sender.setUsername(username);
        sender.setPassword(password);
        sender.setDefaultEncoding("UTF-8");

        Properties properties = sender.getJavaMailProperties();
        properties.setProperty("mail.smtp.auth", "true");
        properties.setProperty("mail.smtp.starttls.enable", "true");
        properties.setProperty("mail.smtp.starttls.required", "true");
        properties.setProperty("mail.smtp.connectiontimeout", "5000");
        properties.setProperty("mail.smtp.timeout", "5000");
        properties.setProperty("mail.smtp.writetimeout", "5000");
        return sender;
    }
}
~~~

With this approach, the application must supply the **app.smtp.*** properties itself, for example from environment configuration. These values are **not spring.mail.***, so they do not automatically receive values from the default auto-configuration. Once you create the bean manually, you take full responsibility for TLS, timeouts, the account, and the operational choices of that bean.

The example above suits SMTP submission using STARTTLS. If the system uses a JNDI Session, implicit TLS, or a provider that requires its own configuration, the way the sender is created must be adjusted.

**When is a manual bean needed?** When there are multiple senders, you want to use a specially managed Jakarta Mail Session, you need deep transport customization, or you want explicit control over bean selection. For a common single SMTP account, Boot's auto-configuration is usually the simpler and more maintainable choice.

## 11. Multiple senders and @Qualifier

If the application has several kinds of mail, for example transactional and campaign, you can declare two **JavaMailSender** beans. Spring does not guess which bean should handle each kind of email.

~~~java
@Bean("transactionalMailSender")
JavaMailSender transactionalMailSender() {
    // Returns a JavaMailSenderImpl configured for transactional mail.
    throw new UnsupportedOperationException("Configuration example");
}

@Bean("campaignMailSender")
JavaMailSender campaignMailSender() {
    // Returns a JavaMailSenderImpl configured for campaigns.
    throw new UnsupportedOperationException("Configuration example");
}
~~~

The snippet above **only illustrates the bean names and configuration intent**; it is not a method that can run to send mail. In real code, each method must return a configured sender, not throw an exception as a placeholder.

Services should inject by explicit name:

~~~java
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.mail.javamail.JavaMailSender;
import org.springframework.stereotype.Service;

@Service
public class TransactionalEmailGateway {

    private final JavaMailSender sender;

    public TransactionalEmailGateway(
            @Qualifier("transactionalMailSender") JavaMailSender sender
    ) {
        this.sender = sender;
    }
}
~~~

With multiple beans of the same type, injection by the **JavaMailSender** interface alone may be unable to pick a single bean and report **NoUniqueBeanDefinitionException**. You can use **@Qualifier**, **@Primary** when you deliberately define a default sender, or create a router to dispatch by business purpose.

**Two mail-sending beans do not automatically produce two queues, retry policies, or rate limits.** To truly separate sending resources, you need to configure the appropriate transport, workers, quotas, and provider infrastructure.

## 12. Using a Jakarta Mail Session from JNDI

Some environments have an application server or infrastructure that manages a **Jakarta Mail Session** outside the application. In that case, Spring Boot can be configured to obtain the Session from **JNDI**:

~~~yaml
spring:
  mail:
    jndi-name: java:comp/env/mail/Session
~~~

The JNDI name is only an example. The runtime environment must actually provide a resource with that name and an appropriate Session configuration. If the application runs as an ordinary Spring Boot executable JAR without a mail Session registered in JNDI, setting this property will not create the resource by itself.

**When spring.mail.jndi-name is used, the Session obtained from JNDI takes priority over the ordinary properties that create a Session.** SMTP settings on the container/JNDI side must be checked where the resource is defined.

JNDI is useful when the operations team wants to manage mail connections centrally at the application server. For most microservices running standalone in containers, configuring directly through **spring.mail.host** and environment variables is usually easier to operate.

## 13. What does spring.mail.test-connection do?

In Spring Boot, you can enable an SMTP connection check when the application starts:

~~~yaml
spring:
  mail:
    test-connection: true
~~~

When the check applies to a suitable sender, Boot tries to connect to the mail system at startup. If the server is unreachable or the transport configuration fails, startup may report an error early instead of waiting until the first email.

| test-connection | Expected behavior |
|---|---|
| **false** (the common default) | Does not proactively check the SMTP connection at startup; connection problems may only surface when sending. |
| **true** | Requires a mail connection check at startup, helping detect configuration/availability errors early. |

**Limits of the check:** A successful connection does not prove that the SMTP server will allow every From address, recipient, or message content. Nor does it prove that DNS SPF/DKIM/DMARC are correct, that the email has been delivered, or that the message will land in the Inbox. The provider may reject at the MAIL FROM, RCPT TO, or DATA command even though the initial connection succeeded.

Enabling the check at startup also affects service availability: a temporary SMTP outage may prevent the application from starting. Choose the behavior according to system requirements, especially when sending email is only a secondary feature and the system still needs to serve other APIs.

## 14. How to tell whether auto-configuration is working

If a service reports that it cannot find a **JavaMailSender** bean, check in the following order:

1. **Dependency**: does the project have the mail starter or compatible Spring Mail/Jakarta Mail libraries?
2. **Host/JNDI properties**: does the running environment receive **spring.mail.host** or **spring.mail.jndi-name**?
3. **Profile and configuration files**: is the application running with the correct Spring profile, the correct file, and the correct environment variables?
4. **Bean declared by the application**: is there a MailSender bean that causes auto-configuration to back off?
5. **Type of bean to inject**: does the service request JavaMailSender while the project only provides a different MailSender, or are there multiple JavaMailSender beans without a distinguishing qualifier?
6. **Auto-configuration exclusions**: is there a configuration excluding MailSenderAutoConfiguration?
7. **Initialization conditions**: check Boot's condition evaluation report to see which conditions match or do not match.

Spring Boot has a **condition evaluation report** that explains why each auto-configuration was applied or skipped. When you need to diagnose in a development environment, you can enable Boot's debug mode, for example:

~~~properties
debug=true
~~~

Or use the configuration-condition inspection tools available in environments with Spring Boot Actuator and an appropriate endpoint. Do not leave overly detailed logging enabled long-term in production; configuration information or SMTP debug output may contain sensitive data.

### The bean exists but sending fails

When injection succeeds but the send() call still fails, the error may lie in SMTP:

- Wrong host or port, or DNS cannot resolve.
- A firewall or network policy blocks the connection.
- STARTTLS/implicit TLS mismatch, or an invalid certificate.
- Wrong or revoked credentials, or no SMTP AUTH permission.
- The account is not permitted to use the From address.
- The SMTP server rejects the relay, the recipient address, the message size, or the sending rate.
- The receiving system blocks spam, applies SPF/DKIM/DMARC, or routes the message to Junk/Spam.

These problems are not necessarily faults of auto-configuration. **Being able to create the JavaMailSender bean is only the step of configuring a mail-sending client.**

## 15. Common exceptions when sending through the auto-configured sender

Spring Mail provides a group of application-level exceptions:

| Exception | Common scenario | Investigation direction |
|---|---|---|
| **MailAuthenticationException** | SMTP AUTH failed | Check credentials, account permissions, and provider authentication requirements. |
| **MailSendException** | Failure during sending | Look at the root cause, the SMTP reply, and per-recipient errors if any. |
| **MailPreparationException** | Error preparing the MimeMessage or callback | Check the data, template, attachments, and how the MIME is built. |
| **MailParseException** | Unable to create or interpret a valid message | Check the addresses, headers, and message structure. |

In the MIME flow, **jakarta.mail.MessagingException** can also occur when building content, for example through MimeMessageHelper. Distinguish **message preparation errors** from **SMTP transport errors** before applying retry.

A network error or timeout at exactly the moment data is submitted can make it unclear whether the message **was accepted by the SMTP server or not**. Resending immediately risks creating duplicate emails. For important functions, you should manage an attempt ID and a notification ID, and cross-check the provider's logs.

## 16. Synchronous sending, queues, and deployment environments

Boot's auto-configuration creates and configures the mail-sending bean; it **does not automatically create a queue**, does not automatically run a background worker, does not guarantee retry, and does not create a distributed transaction with the database. Under ordinary usage:

~~~java
mailSender.send(message);
~~~

This call is **synchronous with respect to the calling thread**: the thread waits for the preparation/communication with the sending system to complete or to receive an exception. A successful send() usually only indicates that the SMTP server at the submission hop has accepted the request; it does not guarantee the recipient sees the message in the Inbox.

If you need to send in large volume or avoid slowing down HTTP requests, the system can use a queue or a transactional outbox:

~~~text
HTTP request / business event
               |
               v
    Write business data + outbox
               |
             COMMIT
               |
               v
          Mail worker
               |
               v
      Auto-configured JavaMailSender
               |
               v
          SMTP relay
               |
               v
          Destination mail server
~~~

The outbox helps record the **intent to send mail** together with the business data consistently when using an appropriate database transaction. However, it does not by itself create an exactly-once guarantee: a worker may send the mail and then stop before updating the status. You need retry policy, duplicate-send prevention, and handling of unknown outcomes at the application layer.

### Configuration per environment

In a real system, SMTP settings may differ between local, staging, and production:

| Environment | Commonly chosen option |
|---|---|
| **Local development** | An SMTP test inbox or a simulated mail server; do not send email to real customers. |
| **Integration testing** | A fake JavaMailSender or an SMTP test server that can observe the created messages. |
| **Staging** | An SMTP sandbox or a test account with controlled domains/recipients. |
| **Production** | A real SMTP/ESP, secure credentials, TLS, timeouts, monitoring, rate limits, and a retry policy. |

Configuration is separated using **Spring profiles**, environment variables, or a configuration management platform. Avoid letting the development profile use production credentials and recipient lists.

## 17. Testing email-sending logic without a real SMTP

Auto-configuration is useful when running the real application; but in a service's unit test, connecting to SMTP is not required. Because the service depends on the **JavaMailSender** interface, you can supply a fake or mock to observe the message content.

Example idea with Mockito:

~~~java
import org.junit.jupiter.api.Test;
import org.mockito.ArgumentCaptor;
import org.springframework.mail.SimpleMailMessage;
import org.springframework.mail.javamail.JavaMailSender;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.mockito.Mockito.*;

class RegistrationMailServiceTest {

    @Test
    void createsWelcomeMessage() {
        JavaMailSender sender = mock(JavaMailSender.class);
        RegistrationMailService service = new RegistrationMailService(sender);

        service.sendWelcome("learner@example.net");

        ArgumentCaptor<SimpleMailMessage> captured =
                ArgumentCaptor.forClass(SimpleMailMessage.class);
        verify(sender).send(captured.capture());

        SimpleMailMessage message = captured.getValue();
        assertEquals("learner@example.net", message.getTo()[0]);
        assertEquals("Welcome", message.getSubject());
    }
}
~~~

The snippet assumes the project has JUnit 5 and Mockito. It tests that the service creates the message and calls the interface, and **does not test SMTP connectivity**. To test the **spring.mail** binding and the auto-configured bean in an ApplicationContext, a separate integration test is needed. To test the actual sending process, use a test SMTP server or an appropriate sandbox.

## 18. Common misconceptions

**"If I have spring-boot-starter-mail, can I use JavaMailSender right away?"** Not necessarily. Auto-configuration also depends on configuration conditions such as host/JNDI and the beans that exist. Adding the dependency does not provide an SMTP server.

**"Does auto-configuration pre-create every From, To, and Subject header?"** No. Boot configures the sending mechanism. The application is still responsible for building the content and the specific headers for each email.

**"Does setting spring.mail.host guarantee mail reaches the Inbox?"** No. The host is only where the application submits mail; the provider, DNS, the receiving server, and mail filters decide many subsequent hops.

**"If I declare a JavaMailSenderImpl manually, will Boot merge spring.mail.* into that bean?"** You should not assume so. When you create the bean yourself, the application must configure the bean and understand the back off mechanism; Boot's properties are not automatically applied to every bean written by users.

**"Can two JavaMailSender beans be injected automatically without specifying which?"** If there are multiple candidates, Spring may report ambiguous injection. Use @Qualifier or an explicit bean-selection strategy.

**"Does test-connection=true verify the ability to deliver mail to recipients?"** No. It only checks the connection within the scope supported by the sender and configuration; SMTP acceptance, spam, bounces, or the Inbox are other steps.

**"Does JavaMailSender.send() run in the background automatically?"** No. The ordinary call is synchronous. If you need async, a queue or outbox must be designed separately.

**"Does Spring Boot always use javax.mail?"** Not with Spring Boot 3 / Spring Framework 6; the underlying mail API uses the jakarta.mail namespace.

## 19. Key takeaways

**Spring Boot auto-configuration for the mail sender** helps the application create a **JavaMailSender** bean without having to write an ordinary SMTP configuration class. With **spring-boot-starter-mail**, the properties **spring.mail.host**, **spring.mail.port**, **spring.mail.username**, **spring.mail.password**, and the **spring.mail.properties.mail.smtp.***, Boot can configure a **JavaMailSenderImpl** and then inject it into services through the interface.

Auto-configuration only works when the conditions regarding the classpath, configuration, and the presence of beans are met. When the application registers its own MailSender/JavaMailSender or needs multiple senders, it must proactively organize the beans, qualifiers, and corresponding configuration. The JNDI Session and **spring.mail.test-connection** are additional options for special environments.

Finally, **auto-configuring the sender does not mean automatically operating the entire email system**. The application must still create accurate content and manage credentials, TLS, timeouts, and SMTP responses; if high reliability is needed, it must add queue, retry, monitoring, and handling of uncertain sending status.
