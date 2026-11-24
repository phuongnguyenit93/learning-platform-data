# spring-boot-starter-mail and related dependencies

In a **Spring Boot** application, email-sending functionality usually starts with a single dependency line:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-mail'
}
~~~

This small declaration carries great significance: it brings the components needed to **create and send email with Spring Mail** onto the classpath, and also allows **Spring Boot auto-configuration** to create a mail sender from the application's configuration. We can inject `JavaMailSender` and then send plain text or build MIME messages containing HTML, attachments, and images.

However, adding the starter **does not mean emails are sent automatically**. The application still needs a suitable SMTP server or mail-sending service, connection configuration, and authentication rights; the business layer must still decide who receives the mail, what the content is, and when to send.

This lesson explains what the starter provides, which dependencies are direct or transitive, how versions are managed, when you need to add libraries, and how to avoid common classpath configuration errors.

## 1. What is a starter in Spring Boot?

A **starter** is an artifact that serves to bundle the dependencies related to a group of functionality according to Spring Boot conventions. Instead of having to look up and declare each underlying library separately, the application declares the corresponding starter so that Boot manages the appropriate set of components.

For sending mail, the main dependency is:

~~~text
Group   : org.springframework.boot
Artifact: spring-boot-starter-mail
~~~

General model:

~~~mermaid
flowchart TD
    A["Spring Boot application"] --> B["spring-boot-starter-mail"]
    B --> C["Spring Mail support"]
    B --> D["Jakarta Mail API / provider"]
    B --> E["Required Boot and Spring dependencies"]
    F["spring.mail.*"] --> G["Mail sender auto-configuration"]
    C --> G
    D --> G
    G --> H["JavaMailSender"]
    H --> I["SMTP server"]
~~~

In typical Spring Boot 3.x projects, the starter involves Spring Framework's **`spring-context-support`** and a **Jakarta Mail implementation** (usually from the Angus Mail family), along with the necessary underlying dependencies. The specific transitive artifacts and versions depend on the **Spring Boot version** in use; check the project's actual dependency tree to know exactly.

The starter addresses two needs:

1. **Bringing the needed API and implementation onto the classpath**, such as `JavaMailSender` and the Jakarta Mail classes.
2. **Working together with Spring Boot auto-configuration** so it can create the sender bean from the `spring.mail.*` properties.

The starter does **not** automatically create content templates, REST controllers, a mail-sending queue, an email-receiving service, a history table, or a mechanism for tracking whether mail reached the inbox.

## 2. Declaring the dependency with Gradle and Maven

### 2.1. Gradle Groovy DSL

In a **Spring Boot module that has dependency version management set up**, add:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-mail'
}
~~~

`implementation` puts the dependency on the compile classpath and runtime classpath of the module that uses it; it suits applications that only use mail internally. If this is a shared library and the library's public API directly exposes Spring Mail types to other modules, you need to revisit the API boundary and the corresponding dependency scope; do not blindly change every declaration to `api`.

When using the Spring Boot Gradle plugin **together with an appropriate dependency management mechanism**, you usually do not need to declare a separate version for the starter, because the version is managed in sync with Spring Boot. For a Gradle project that does not use this kind of version management, you must set up a BOM/platform or an equivalent mechanism.

### 2.2. Gradle Kotlin DSL

~~~kotlin
dependencies {
    implementation("org.springframework.boot:spring-boot-starter-mail")
}
~~~

The declaration is equivalent in meaning; the main difference lies in the build script syntax. If a multi-module project uses a version catalog, you can create an alias and use that alias, as long as all dependencies remain managed compatibly with the project's Spring Boot.

### 2.3. Maven

In a Maven project that already uses `spring-boot-starter-parent` or imports the Spring Boot dependency BOM:

~~~xml
<dependencies>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-mail</artifactId>
    </dependency>
</dependencies>
~~~

When the parent/BOM manages versions, you do not need to add `<version>` to this dependency. If the Maven project has no suitable parent or BOM, you must configure version management separately first; omitting the version without dependency management will not work.

### 2.4. Version management with the Spring Boot BOM

Spring Boot publishes a set of dependency versions that have been checked for compatibility. A Gradle application using native BOM support can declare it following this model:

~~~groovy
dependencies {
    implementation platform('org.springframework.boot:spring-boot-dependencies:<boot-version>')
    implementation 'org.springframework.boot:spring-boot-starter-mail'
}
~~~

`<boot-version>` in the illustrative snippet is a **placeholder**, not a runnable version. Use the exact version the project has chosen and ensure compatibility with the Boot plugin, Java, and Spring Framework. If the build already imports the Spring Boot BOM through another mechanism, do not add an unnecessary second source of version management.

Do not arbitrarily assign separate versions to `spring-context-support` or the Jakarta Mail provider just to "get the latest version". Overriding transitive versions can cause runtime errors. When you need to upgrade to fix security issues or for compatibility, you should first choose an appropriate Spring Boot version, then thoroughly check the dependency tree and run integration tests.

## 3. The main dependency layers and their responsibilities

There are three layers to distinguish: the **Spring Mail API**, the **Jakarta Mail API and implementation**, and **Spring Boot auto-configuration**.

| Component | Typical library or package | Role |
| --- | --- | --- |
| Spring Boot starter | `org.springframework.boot:spring-boot-starter-mail` | Bundles the mail dependencies suited to Spring Boot |
| Spring Framework Mail | `org.springframework:spring-context-support`, package `org.springframework.mail.*` | Mail-sending interfaces, simple messages, helpers, and the SMTP implementation |
| Jakarta Mail API | Packages `jakarta.mail.*` and `jakarta.mail.internet.*` | Represents messages, sessions, MIME, addresses, and mail exceptions |
| Jakarta Mail implementation/provider | For example Angus Mail in the Jakarta ecosystem | Executes transport/store protocols such as SMTP; brought onto the classpath according to the chosen dependency |
| Jakarta Activation | `jakarta.activation.*` | Supports data types and content sources for multipart and attachments |
| Spring Boot autoconfigure | The mail configuration classes in Spring Boot | Creates and configures the sender based on classpath, bean, and property conditions |

This table describes the **logical roles**, and is not a claim that every artifact appears as a direct dependency in every version. Some may be pulled in through transitive dependencies.

### 3.1. Spring Framework Mail: the application-level API

Commonly seen classes:

~~~java
import org.springframework.mail.MailSender;
import org.springframework.mail.SimpleMailMessage;
import org.springframework.mail.MailException;
import org.springframework.mail.javamail.JavaMailSender;
import org.springframework.mail.javamail.JavaMailSenderImpl;
import org.springframework.mail.javamail.MimeMessageHelper;
~~~

- **`MailSender`:** the abstraction for sending `SimpleMailMessage`.
- **`JavaMailSender`:** extends `MailSender` to create/send `MimeMessage`.
- **`JavaMailSenderImpl`:** the common implementation that uses Jakarta Mail to interact with an SMTP server.
- **`SimpleMailMessage`:** describes a text-only email with From, To, Reply-To, Cc, Bcc, Subject, and Text.
- **`MimeMessageHelper`:** helps configure MIME such as HTML, multipart, inline images, and attachments.
- **`MailException`:** Spring's exception group for when mail operations fail.

These are classes **belonging to Spring Framework**, not to the `jakarta.mail` package. When reading examples, do not confuse `JavaMailSender` with Jakarta Mail's `Session` or `Transport`: they operate at different levels of abstraction.

### 3.2. Jakarta Mail: the message and protocol model

Commonly encountered types:

~~~java
import jakarta.mail.MessagingException;
import jakarta.mail.Session;
import jakarta.mail.internet.MimeMessage;
import jakarta.mail.internet.InternetAddress;
~~~

Jakarta Mail defines APIs for Internet-standard email, including messages, addresses, MIME, sessions, and transport. When the corresponding library/provider is on the runtime classpath, it handles tasks such as creating MIME content or communicating over SMTP.

**Spring Mail does not replace Jakarta Mail**: Spring provides an integration layer and an application-friendly abstraction, while Jakarta Mail handles the lower-level message representation and protocol.

### 3.3. Jakarta Activation and attachment resources

When creating an HTML email with inline images or attachments, the Activation/`DataSource` APIs help describe the source of bytes and the media type. Spring Mail also accepts Spring Core resources such as `ClassPathResource` and `ByteArrayResource`.

Example:

~~~java
helper.addAttachment(
    "receipt.pdf",
    new ByteArrayResource(pdfBytes),
    "application/pdf"
);
~~~

The need to send a PDF does not oblige the application to add a separate Activation dependency itself: in the common Mail starter configuration, the libraries required for Jakarta Mail and MIME are usually already present via transitive dependencies. Add a separate artifact only when the actual dependency tree shows they are missing or you have a requirement to use a specific implementation.

## 4. How does Spring Boot auto-configure the mail sender?

Auto-configuration is the **Spring Boot** part, working together with the starter and `spring.mail.*` to create the appropriate bean.

Explained at the application level:

~~~text
spring-boot-starter-mail is in the dependencies
        |
        v
Are suitable MailSender/Jakarta Mail classes on the classpath?
        |
        v
Is there appropriate mail configuration (for example spring.mail.host or a JNDI session)?
        |
        v
No MailSender bean defined by the application yet?
        |
        v
Spring Boot creates/configures JavaMailSender
        |
        v
@Service injects JavaMailSender and calls send(...)
~~~

The detailed conditions and configuration classes may differ between Boot versions; the model above describes the **behavior commonly seen in Spring Boot 3.x**. For ordinary SMTP, the application should declare `spring.mail.host` and the related properties. If the host/JNDI session has not been provided or the application has defined its own sender bean, you should not assume that Boot will definitely create a `JavaMailSender`.

### 4.1. `application.yml` configuration for SMTP

~~~yaml
spring:
  mail:
    host: ${SMTP_HOST}
    port: ${SMTP_PORT:587}
    username: ${SMTP_USERNAME}
    password: ${SMTP_PASSWORD}
    protocol: smtp
    default-encoding: UTF-8
    properties:
      "[mail.smtp.auth]": true
      "[mail.smtp.starttls.enable]": true
      "[mail.smtp.starttls.required]": true
      "[mail.smtp.connectiontimeout]": 5000
      "[mail.smtp.timeout]": 5000
      "[mail.smtp.writetimeout]": 5000

app:
  mail:
    from: ${MAIL_FROM:no-reply@example.com}
~~~

Notes:

- `spring.mail.*` is the standard property group for Spring Boot mail configuration.
- The `mail.smtp.*` keys are transport properties interpreted by the Jakarta Mail provider; in YAML, use the `"[mail.smtp.auth]"` notation to preserve the map key with dots.
- `spring.mail.default-encoding` configures the default encoding; useful for Vietnamese and Unicode content.
- `app.mail.from` is an **application-defined configuration**; the application service must read it and set the `From` header.
- The `SMTP_USERNAME` and `SMTP_PASSWORD` variables must be supplied by the environment if the provider requires authentication; do not store real passwords in Git.
- The example uses `587` and STARTTLS; providers using implicit TLS such as port `465` need `mail.smtp.ssl.enable` configured according to the corresponding guidance.

Depending on the Boot version and configuration model, you can also supply the environment variables `SPRING_MAIL_HOST`, `SPRING_MAIL_PORT`, `SPRING_MAIL_USERNAME`, and `SPRING_MAIL_PASSWORD` directly. Spring Boot will use the property binding/relaxed binding mechanism to read the corresponding values.

### 4.2. Dependency and configuration are two different conditions

| State | What can happen |
| --- | --- |
| Starter present, `spring.mail.host` set, valid configuration | Boot can usually create a `JavaMailSender` |
| Starter present but no host/JNDI session provided | No automatic sender bean in the common configuration |
| Mail classpath present but a `MailSender` bean has been declared | Auto-configuration may yield to the application bean |
| Sender bean present but wrong host/port/credentials | The bean can still be created; sending operations later fail |
| Starter present and a local SMTP test server | You can try sending without an external email provider, if configured appropriately |

Creating the bean and **actually connecting to SMTP** are usually two separate stages. By default, the application starting up does not prove that the SMTP host is reachable, that the credentials are correct, or that the recipient accepts the mail.

Spring Boot has the option `spring.mail.test-connection=true` to try connecting at startup when appropriate. This is an operational choice; if the provider is temporarily down, it can make startup fail. Nor can you infer that one successful test-connection guarantees every email will be delivered to the Inbox.

## 5. Starter usage example: sending plain-text email

Once the starter and SMTP are configured, the application service injects `JavaMailSender`:

~~~java
package com.example.mail.application;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.mail.SimpleMailMessage;
import org.springframework.mail.javamail.JavaMailSender;
import org.springframework.stereotype.Service;

@Service
public class NotificationMailService {
    private final JavaMailSender mailSender;
    private final String fromAddress;

    public NotificationMailService(
            JavaMailSender mailSender,
            @Value("${app.mail.from}") String fromAddress) {
        this.mailSender = mailSender;
        this.fromAddress = fromAddress;
    }

    public void sendText(String recipient, String subject, String body) {
        SimpleMailMessage message = new SimpleMailMessage();
        message.setFrom(fromAddress);
        message.setTo(recipient);
        message.setSubject(subject);
        message.setText(body);

        mailSender.send(message);
    }
}
~~~

Here:

1. `JavaMailSender` is a **Spring-managed bean**; the application does not need to create a `JavaMailSenderImpl` inside the sending method.
2. The `From` address is taken from configuration, while the recipient/subject/content come from the business logic.
3. `SimpleMailMessage` represents a plain-text message.
4. `send(message)` uses the configured mail transport to submit the mail to the SMTP server.

A real application must check the caller and the recipient data according to business rules. You should not casually open a public REST endpoint that lets others set `To`, `Subject`, and `Body` at will and then send mail.

### 5.1. Do you need to declare `spring-context-support` separately?

With the **ordinary Spring Boot mail starter**, no. The starter already handles pulling the required Spring Mail library into the dependency graph. Adding a second declaration just to use `JavaMailSender` or `SimpleMailMessage` is usually redundant.

Only consider declaring `spring-context-support` directly when:

- the module **does not use the mail starter** but needs the Spring Mail API;
- the project deliberately manages dependencies itself to build its own integration library;
- there is a clear architectural requirement on the public API or runtime scope.

In those cases, you must also ensure that a compatible Jakarta Mail provider is present when real SMTP is needed, and you must decide for yourself how to configure the sender.

## 6. Starter usage example: HTML and attachments

The mail starter also provides the ability to use `MimeMessage` through `JavaMailSender`. There is no need to swap in another starter just because the email has HTML or a PDF.

~~~java
package com.example.mail.application;

import jakarta.mail.MessagingException;
import jakarta.mail.internet.MimeMessage;
import org.springframework.core.io.ByteArrayResource;
import org.springframework.mail.javamail.JavaMailSender;
import org.springframework.mail.javamail.MimeMessageHelper;
import org.springframework.stereotype.Service;

@Service
public class InvoiceMailService {
    private final JavaMailSender mailSender;

    public InvoiceMailService(JavaMailSender mailSender) {
        this.mailSender = mailSender;
    }

    public void sendInvoice(String recipient, byte[] pdfBytes)
            throws MessagingException {
        MimeMessage mime = mailSender.createMimeMessage();
        MimeMessageHelper helper =
                new MimeMessageHelper(mime, true, "UTF-8");

        helper.setFrom("billing@example.com");
        helper.setTo(recipient);
        helper.setSubject("Your invoice");
        helper.setText(
                "Your invoice is ready.",
                "<html><body><h1>Your invoice is ready</h1>" +
                "<p>Thank you.</p></body></html>"
        );
        helper.addAttachment(
                "invoice.pdf",
                new ByteArrayResource(pdfBytes),
                "application/pdf"
        );

        mailSender.send(mime);
    }
}
~~~

Components appearing in the code snippet:

| Type | Source | Role |
| --- | --- | --- |
| `JavaMailSender` | Spring Framework Mail | Creates and sends `MimeMessage` |
| `MimeMessage` | Jakarta Mail | The message object with MIME structure |
| `MimeMessageHelper` | Spring Framework Mail | Builds text/HTML content and attachments |
| `ByteArrayResource` | Spring Core | Supplies bytes for the attachment |
| `MessagingException` | Jakarta Mail | Reports errors related to building/processing the message |

The snippet assumes `pdfBytes` is PDF content prepared in advance. For large files, you should evaluate SMTP size limits, memory, and the possibility of using an appropriate resource/stream instead of always holding all the bytes on the heap.

A normal return from `send` usually means the transport has completed the mail submission under the current protocol. It **does not guarantee** the email has reached the inbox, has not bounced, or has been opened by the recipient.

## 7. Optional dependencies that commonly accompany the mail starter

`spring-boot-starter-mail` serves the foundational mail functionality. Some applications add dependencies for **HTTP input, templates, validation, testing, or job processing**. These additional libraries are not a prerequisite for sending text mail.

| Need | Common dependency | Why add it? |
| --- | --- | --- |
| Send plain text via SMTP | `spring-boot-starter-mail` | Sufficient core components to create/use a sender once correctly configured |
| Generate HTML from a template | `spring-boot-starter-thymeleaf` | Renders HTML templates with business data |
| REST API that triggers sending | `spring-boot-starter-web` | Provides HTTP controllers in a Servlet/MVC application |
| Validate DTO/request | `spring-boot-starter-validation` | Supports Bean Validation such as `@NotBlank`, `@Email` |
| Unit/integration test | `spring-boot-starter-test` | Provides the Spring Boot testing foundation and commonly used test libraries |
| Simple asynchronous sending | Spring's async capability once a suitable framework is in place | Runs the sending operation on another executor, but does not create a durable queue |
| Durable job/queue | Depends on architecture: database, broker, Spring Batch, etc. | Stores send requests, retry, duplicate-processing prevention, and monitoring |

### 7.1. HTML templates and Thymeleaf

If the HTML has the recipient's name, an order code, or a data table, concatenating strings directly easily makes the content hard to maintain. You can use Thymeleaf with a separate dependency:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-mail'
    implementation 'org.springframework.boot:spring-boot-starter-thymeleaf'
}
~~~

Example resources:

~~~text
src/main/resources/
  templates/
    mail/
      welcome.html
      invoice.html
~~~

Flow:

~~~mermaid
flowchart LR
    A["Business data"] --> B["Thymeleaf / template renderer"]
    B --> C["HTML string"]
    C --> D["MimeMessageHelper"]
    D --> E["JavaMailSender"]
    E --> F["SMTP server"]
~~~

**Thymeleaf does not send email.** It only renders HTML content; Spring Mail/Jakarta Mail still handle creating and sending the message. You can use another template engine or build the text string yourself, depending on project scale. When putting user data into HTML, use appropriate escaping syntax; do not insert untrusted HTML directly.

### 7.2. A REST API is not a requirement of the mail module

If a business case needs an internal endpoint such as "resend confirmation email", you can use `spring-boot-starter-web` for the controller. However, many mail modules are triggered from:

- user registration or payment events;
- a consumer receiving events from a message broker;
- a scheduler sending reports on a schedule;
- a worker processing jobs from a database/queue;
- an internal service called directly within the same application.

These models **do not require a REST controller**. Do not add the web starter just because the problem involves sending email; choose dependencies according to the actual runtime architecture.

### 7.3. Validation for send-request data

If the application receives a request:

~~~java
import jakarta.validation.constraints.Email;
import jakarta.validation.constraints.NotBlank;

public record SendNotificationRequest(
        @NotBlank @Email String recipient,
        @NotBlank String message
) {}
~~~

The annotations above are usually provided through the Bean Validation dependency and implementation when the application uses the validation starter. `@Email` only checks according to the validator's rules and **does not confirm that the mailbox exists** or that the person entering it has the right to use that address. You still need to authenticate the caller, control the recipient, and apply rate limiting according to the business.

### 7.4. Test dependencies and simulated SMTP

Unit tests can mock `JavaMailSender` to verify the content passed to `send(...)` **without needing a real SMTP server**. For integration tests, tools such as Mailpit or GreenMail allow receiving and inspecting email in a local/test environment.

If you choose an SMTP test library embedded in the JVM, add that library's dependency to the **test scope** (for example `testImplementation`), and do not put it into the production runtime without a clear reason.

Gradle example:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-mail'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}
~~~

When you want to integrate Mailpit running outside the JVM, the application usually only needs `spring.mail.host=localhost` and the port of the test SMTP server configured; it is not necessary to add a Mailpit library to the Java dependencies.

## 8. Boot 3.x, Jakarta Mail, and differences from older examples

When reading Java Mail tutorials on the Internet, you may encounter two groups of packages:

~~~java
// Old code following JavaMail before the switch to the Jakarta namespace:
import javax.mail.internet.MimeMessage;

// Code in Spring Boot 3.x / Spring Framework 6:
import jakarta.mail.internet.MimeMessage;
~~~

Spring Framework 6 and Spring Boot 3.x use the **Jakarta EE** ecosystem, in which Jakarta Mail uses the `jakarta.mail.*` packages. Older guides based on Spring Boot 2.x may use `javax.mail.*`.

Important distinctions:

| Item | In Boot 3.x |
| --- | --- |
| `JavaMailSender` | Still `org.springframework.mail.javamail.JavaMailSender` |
| `SimpleMailMessage` | Still `org.springframework.mail.SimpleMailMessage` |
| `MimeMessage` | `jakarta.mail.internet.MimeMessage` |
| `MessagingException` | `jakarta.mail.MessagingException` |
| Jakarta Activation | Package `jakarta.activation.*` |

Do not "fix" an import error by randomly adding the old `javax.mail` dependency to a Boot 3.x application. The two namespaces `javax.mail` and `jakarta.mail` are different Java types; mixing them easily leads to compile errors or runtime incompatibility.

If you are maintaining a Spring Boot 2.x project, you need to use the APIs and dependencies corresponding to that line. When upgrading to Boot 3.x, update the imports as well as the compatible mail extension libraries, and check the runtime configuration.

### 8.1. Do not pin an incompatible provider

The classpath may contain the Jakarta Mail API and an SMTP provider implementation. If the project deliberately excludes or overrides these libraries, the symptoms may be:

- compilation sees `MimeMessage` but at runtime there is no provider for sending SMTP;
- `ClassNotFoundException` or `NoClassDefFoundError` errors;
- errors involving `javax.mail` and `jakarta.mail` when another module or library uses an incompatible API;
- the `JavaMailSender` bean is not auto-configured because the classpath condition is broken.

Before adding a dependency based on a random suggestion, check the **resolved dependency graph** and the reason the artifact appears/is excluded.

## 9. When should you use Spring Mail without the starter?

In some cases an application or library only needs the Spring Mail API and does not want to depend on the Spring Boot starter:

1. **A plain Spring Framework application:** wants to declare `JavaMailSenderImpl` and the corresponding Jakarta Mail libraries itself.
2. **A shared library:** only needs to compile against `MailSender` or its own abstraction, while the consuming application is responsible for configuring the implementation.
3. **Provider integration via HTTP API instead of SMTP:** may not need `JavaMailSender`, and instead uses the provider's SDK/HTTP client and a gateway at the application layer.

With plain Spring Framework, an example configuration bean (assuming the properties have been loaded into the Spring `Environment`):

~~~java
import java.util.Properties;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.env.Environment;
import org.springframework.mail.javamail.JavaMailSender;
import org.springframework.mail.javamail.JavaMailSenderImpl;

@Configuration
public class MailConfig {

    @Bean
    JavaMailSender javaMailSender(Environment env) {
        JavaMailSenderImpl sender = new JavaMailSenderImpl();
        sender.setHost(env.getRequiredProperty("mail.host"));
        sender.setPort(env.getRequiredProperty("mail.port", Integer.class));
        sender.setUsername(env.getRequiredProperty("mail.username"));
        sender.setPassword(env.getRequiredProperty("mail.password"));
        sender.setDefaultEncoding("UTF-8");

        Properties properties = sender.getJavaMailProperties();
        properties.put("mail.smtp.auth", "true");
        properties.put("mail.smtp.starttls.enable", "true");
        properties.put("mail.smtp.starttls.required", "true");
        return sender;
    }
}
~~~

In this architecture, the application itself manages the Spring Mail dependency, Jakarta Mail/provider, configuration, and sender lifecycle. If you are already using the ordinary Spring Boot mail starter, **there is no need to recreate a bean like the example** unless there is a specific customization requirement.

A module that sends email only through a provider's **HTTP API** can choose something entirely different: a client/SDK sends HTTPS requests and handles the provider's response. `spring-boot-starter-mail` mainly fits when using the Spring Mail API and/or SMTP; it is not a mandatory dependency for every kind of email-sending service.

## 10. How to see which dependencies have actually been brought into the project

In a multi-module Gradle build, declared dependencies are not necessarily identical to the artifacts resolved for runtime. To understand what the starter pulls in, you can use the **reference** commands below in the appropriate module:

~~~bash
# View all runtime dependencies of the module.
./gradlew dependencies --configuration runtimeClasspath

# Find out why spring-context-support is present.
./gradlew dependencyInsight --dependency spring-context-support --configuration runtimeClasspath

# Check the resolved mail implementation/provider.
./gradlew dependencyInsight --dependency jakarta.mail --configuration runtimeClasspath
~~~

If running from the root of a multi-project build, you need to specify the project path explicitly in the command, for example `:my-mail-app:dependencies`, according to the module's actual name. With Maven:

~~~bash
mvn dependency:tree
~~~

These commands help you check:

- which starter pulled Spring Mail in;
- the final version of `spring-context-support` and Jakarta Mail/provider;
- whether any dependency is excluded or overridden;
- whether another library brings in legacy `javax.mail`;
- whether the scope/runtime classpath contains the required classes.

Do not guess the dependency graph from the starter name alone when the project has multiple plugins, BOMs, or resolution rules.

## 11. Common errors when adding the mail starter

| Symptom | Possible cause | What to check |
| --- | --- | --- |
| `NoSuchBeanDefinitionException: JavaMailSender` | Missing starter, missing appropriate host/JNDI configuration, auto-configuration conditions not satisfied, or the bean was replaced | Classpath, `spring.mail.host`, custom beans, and the auto-configuration report |
| `ClassNotFoundException` involving `jakarta.mail` | Provider/API excluded, wrong scope, or incompatible version | Resolved dependency graph and runtime classpath |
| `package javax.mail does not exist` | Old code not yet migrated to Jakarta when using Spring Boot 3.x | Imports and dependencies according to the Boot version |
| `MailAuthenticationException` | Wrong credentials or the provider rejects the authentication method | Environment variables, account, SMTP AUTH mechanism |
| Connection refused / timeout | Wrong SMTP host/port, server not running, firewall/network policy, timeout | Environment connectivity and `spring.mail.*` |
| Server rejects STARTTLS | Server does not support it or the security configuration does not match | `mail.smtp.starttls.*`, the provider's TLS mode |
| TLS certificate error | Wrong hostname, expired certificate, or an unsuitable truststore | Certificate, trust chain, DNS, and connection security |
| Vietnamese message text is corrupted | Charset/encoding misconfigured | `spring.mail.default-encoding`, MIME headers, and the receiving client |
| `send(...)` returns without error but the recipient does not see the mail | The mail was accepted by the server but is still pending/has bounced/went to spam | Provider dashboard, DSN, webhook, not just the Java exception |
| Assuming the starter will send email automatically on events | Missing a service/event handler/job that triggers sending | The business flow and where `JavaMailSender.send` is called |

### 11.1. Distinguishing startup errors from sending errors

If there is no `JavaMailSender` bean, the application may fail when creating a service that depends on that bean. If the bean has been created but the SMTP host is wrong or the credentials have expired, the error may **only appear when calling `send(...)`**.

For important transactional mail, you should record errors in a structured way and design bounded retry where appropriate. Do not retry every exception indefinitely: permanent recipient rejection, wrong authentication, and temporary network errors need different handling. Losing the connection after the client has sent the content can also create a situation where it is unclear whether the server received the mail, so retrying risks producing duplicate mail.

### 11.2. Configuring the host is not proof of readiness to send

The existence of three different things:

~~~text
Dependency present -> Sender bean exists -> SMTP sends successfully
~~~

You should not merge these into a single step. The dependency is only a **capability at the classpath level**; the bean is a **configuration in the Spring container**; actual SMTP depends on the **network, TLS, credentials, provider policy, and server state**.

## 12. Examples of choosing dependencies by scenario

| Scenario | Suitable starting dependency | Notes |
| --- | --- | --- |
| A Spring Boot microservice sending OTP or text notifications via SMTP | `spring-boot-starter-mail` | Use `SimpleMailMessage`; control sensitive data in the content |
| A service sending an HTML invoice with a PDF | `spring-boot-starter-mail` | Use `MimeMessageHelper`; no separate attachment starter needed |
| A service using HTML templates with dynamic content | Mail starter + Thymeleaf starter if you choose Thymeleaf | The renderer and the sender are two separate responsibilities |
| An application with a REST endpoint to resend notifications | Mail starter + web/validation depending on architecture | Protect the endpoint, avoid becoming an open mail relay |
| A worker sending email from a queue | Mail starter + queue dependency according to the broker | The queue is not provided automatically by the mail starter |
| Unit test of a mail service | Mail starter at runtime/compile + test starter at test scope | Mock the sender to check the message |
| Internal SMTP integration test | Mail starter + an external SMTP test tool or test library | Do not use production credentials |
| A Spring Framework library not running Spring Boot | Spring Mail API and Jakarta Mail/provider as needed | Configure the sender yourself, do not rely on Boot auto-configuration |
| Sending email via the provider's REST API | The corresponding SDK or HTTP client | May not use the mail starter if the Spring SMTP API is not needed |

## 13. A small exercise: from dependency to a first email

Suppose the application needs to send a text notification from a technical account:

1. **Declare** `spring-boot-starter-mail` in the Spring Boot module.
2. **Choose the SMTP server**: a local test server or a provider with real sending rights.
3. **Supply the configuration** `spring.mail.host`, port, AUTH/TLS, timeouts, and secrets from the environment.
4. **Inject** `JavaMailSender` into the service; avoid creating a sender on every send.
5. **Create** a `SimpleMailMessage`, set From, To, Subject, and Text.
6. **Call** `send(message)`; monitor errors and the mail submission result.
7. **Verify** the received email in the SMTP test server, including headers, Vietnamese characters, and content.
8. **Upgrade** to `MimeMessageHelper` if you need HTML, attachments, or multiple MIME parts.

There is no need to create a controller, scheduler, template engine, or queue for the exercise of sending one text notification. Those dependencies only make sense when the business or architectural requirements truly need them.

The shortest core example:

~~~java
SimpleMailMessage mail = new SimpleMailMessage();
mail.setFrom("no-reply@example.com");
mail.setTo("reader@example.net");
mail.setSubject("Hello");
mail.setText("This is a test email sent with Spring Boot Mail.");
javaMailSender.send(mail);
~~~

The snippet assumes `javaMailSender` has been injected and the SMTP sender is correctly configured; it cannot run standalone outside an application context that already has a sender bean.

## 14. Misunderstandings to avoid

| Misunderstanding | Correct understanding |
| --- | --- |
| "Just adding `spring-boot-starter-mail` makes email send automatically." | The starter provides dependencies; the application must still configure SMTP and call the sender. |
| "To get HTML or PDF, I must find another mail starter." | `JavaMailSender` and `MimeMessageHelper` in the Spring Mail ecosystem already support MIME. |
| "I must add `spring-context-support` and Jakarta Mail libraries one by one." | With the ordinary mail starter, they are usually transitive dependencies; only add them when truly needed. |
| "The starter is an SMTP server." | The starter is an application library; the SMTP server/provider is an external operational component. |
| "Spring Mail also receives and reads the inbox." | A mail-sending API does not become an email-receiving system; inbound is a separate problem. |
| "Adding the web starter is a mandatory condition for sending mail." | Email can be triggered by a service, event, scheduler, or worker. |
| "`javax.mail` and `jakarta.mail` can be swapped freely." | They belong to different API generations; they must be compatible with the Spring Boot/Spring Framework in use. |
| "Email submitted to SMTP means the user has read it." | Delivery and read status need to be tracked separately if the business requires it. |
| "The starter comes with a queue and retry." | Queue, outbox, backoff, idempotency, and status tracking must be designed separately. |

## 15. Knowledge to take away from this lesson

When you encounter `spring-boot-starter-mail` in `build.gradle` or `pom.xml`, you can understand that:

- The project has chosen the **Spring Mail integration** to build mail-sending functionality.
- APIs such as `JavaMailSender`, `SimpleMailMessage`, and `MimeMessageHelper` come from **Spring Framework Mail**.
- The types `MimeMessage` and `MessagingException` come from **Jakarta Mail** in the Boot 3.x ecosystem; the implementation/provider helps communicate with SMTP.
- **Spring Boot auto-configuration** uses the classpath, existing beans, and `spring.mail.*` to decide whether to create the sender.
- **Template engines, web APIs, validation, queues, and test SMTP** are additional components according to requirements, not automatic features of the starter.

Understanding these boundaries correctly helps you choose just enough dependencies, avoid version conflicts, know where to check when `JavaMailSender` does not exist, and clearly distinguish a **classpath**, **bean configuration**, **SMTP connection**, or **mail delivery** error.

### Reference documentation

- **Spring Boot Reference — Sending Email:** the starter, `spring.mail.*`, and mail auto-configuration.
- **Spring Boot Reference — Dependency Management:** BOM and dependency versions managed by Spring Boot.
- **Spring Framework Reference — Email:** `MailSender`, `JavaMailSender`, and `MimeMessageHelper`.
- **Spring Framework API — `org.springframework.mail.*`:** the related interfaces, messages, and exceptions.
- **Jakarta Mail Specification / API:** `MimeMessage`, `Session`, the SMTP provider, and MIME.
- **Gradle User Manual / Maven Dependency Plugin:** viewing the resolved dependency graph and why transitive dependencies appear.
