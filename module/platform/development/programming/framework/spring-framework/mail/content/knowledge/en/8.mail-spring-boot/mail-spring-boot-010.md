# Separating configuration with application properties and YAML

In a Spring Boot application using Spring Framework Mail, Java code usually only needs to create the email content and then call **JavaMailSender.send(...)**. The harder part lies in the connection configuration: what the SMTP server is, which port to use, whether authentication is needed, whether to use STARTTLS or TLS from the start, and how long network operations are allowed to wait.

If every parameter lives directly inside Java classes, moving from development to production entails editing code and easily risks leaking credentials. Spring Boot supports **externalized configuration** to separate parameters from business logic. The two most common formats are **application.properties** and **application.yml** (or **application.yaml**).

This lesson explains how to declare mail-sending configuration in both formats, how Spring Boot passes values into **JavaMailSenderImpl**, how to split by profile, and how to load sensitive information from the deployment environment.

## 1. Model: business code and sender configuration are two different responsibilities

Example of a notification-sending service in Spring:

~~~java
import org.springframework.mail.SimpleMailMessage;
import org.springframework.mail.javamail.JavaMailSender;
import org.springframework.stereotype.Service;

@Service
public class NoticeService {

    private final JavaMailSender mailSender;

    public NoticeService(JavaMailSender mailSender) {
        this.mailSender = mailSender;
    }

    public void sendNotice(String recipient) {
        SimpleMailMessage mail = new SimpleMailMessage();
        mail.setFrom("noreply@example.org");
        mail.setTo(recipient);
        mail.setSubject("Notification");
        mail.setText("You have a new notification.");

        mailSender.send(mail);
    }
}
~~~

The service decides the content, displayed sender address, and recipient. It does not need to know the SMTP hostname or authentication details. Those parameters should belong to the **email-sending infrastructure configuration**.

~~~text
        Spring business code
                 |
       JavaMailSender.send(...)
                 |
                 v
         JavaMailSenderImpl
                 ^
                 |
       Spring Boot auto-config
                 ^
                 |
      application.properties
            or
        application.yml
                 ^
                 |
      Profile / Environment
           / Secret store
~~~

**JavaMailSender** is the mail-sending interface; **JavaMailSenderImpl** is a Jakarta Mail-based implementation. In Spring Boot, when the appropriate dependencies and configuration conditions are met, the mail auto-configuration mechanism creates the bean for the application.

Therefore, switching from an SMTP sandbox to production SMTP should normally be a change in **deployment configuration**, not a change to the contents of **NoticeService**.

## 2. How do application.properties and application.yml differ?

Both formats are loaded by Spring Boot into the configuration system to look up keys such as **spring.mail.host**.

**The properties format** uses flat key-value pairs:

~~~properties
spring.mail.host=smtp.example.org
spring.mail.port=587
spring.mail.protocol=smtp
~~~

**The YAML format** uses a nested structure:

~~~yaml
spring:
  mail:
    host: smtp.example.org
    port: 587
    protocol: smtp
~~~

In configuration meaning, the two examples are equivalent.

| Characteristic | application.properties | application.yml |
| --- | --- | --- |
| Structure | Each line contains the full key | Levels are determined by indentation |
| Finding keys | Easy to search the whole string spring.mail.host | Requires understanding parent/child structure |
| Prefix repetition | Yes, e.g. spring.mail.* repeats many times | Less repetition |
| Common errors | Misspelling key names or escaping | Wrong indentation, not quoting special characters |
| Profiles | Supported | Supported |
| Suitable for JavaMailSender | Yes | Yes |

Spring Boot's property set is the same. **YAML does not create a new kind of JavaMailSender**, nor does it make SMTP change protocol.

You can use either the **.yml** or **.yaml** extension. Maintain a single convention in the project so maintainers can easily locate configuration.

## 3. Minimum conditions for Spring Boot to create the sender

For a Gradle project, usually declare:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-mail'
}
~~~

This snippet only illustrates the dependencies part, assuming the project has configured the required plugins and repositories.

Spring Boot can auto-configure **JavaMailSenderImpl** when the classpath and mail settings satisfy auto-configuration conditions, such as having **spring.mail.host** or an appropriate mail Session configuration. Then a service only needs to inject:

~~~java
private final JavaMailSender mailSender;
~~~

There is no need to call **new JavaMailSenderImpl()** yourself in each service.

However, adding the dependency alone is still not enough to send mail. The application also needs a real SMTP endpoint, sending permissions, and authentication details as required by the provider.

### Important Boot properties

| Property | Meaning |
| --- | --- |
| **spring.mail.host** | SMTP server |
| **spring.mail.port** | SMTP port |
| **spring.mail.username** | Account used for authentication |
| **spring.mail.password** | Credential used for authentication |
| **spring.mail.protocol** | Transport protocol, usually smtp |
| **spring.mail.default-encoding** | Default charset when creating messages |
| **spring.mail.properties[...]** | Map containing Jakarta Mail Properties |
| **spring.mail.test-connection** | Requests testing the connection at startup in supported configurations |
| **spring.mail.jndi-name** | References a mail Session from JNDI, used in some infrastructures |

You need to separate the two layers: **spring.mail.host** is a Boot property, whereas **mail.smtp.auth** is an SMTP transport property handled by Jakarta Mail.

## 4. Complete example with application.properties

Suppose the SMTP provider requires AUTH and STARTTLS on port 587. The **src/main/resources/application.properties** file can contain:

~~~properties
# Connection target
spring.mail.host=${SMTP_HOST}
spring.mail.port=${SMTP_PORT:587}
spring.mail.protocol=smtp

# Credentials received from the runtime environment
spring.mail.username=${SMTP_USERNAME}
spring.mail.password=${SMTP_PASSWORD}

# Content encoding
spring.mail.default-encoding=UTF-8

# Properties for Jakarta Mail SMTP
spring.mail.properties[mail.smtp.auth]=true
spring.mail.properties[mail.smtp.starttls.enable]=true
spring.mail.properties[mail.smtp.starttls.required]=true
spring.mail.properties[mail.smtp.ssl.checkserveridentity]=true

# Timeouts: milliseconds
spring.mail.properties[mail.smtp.connectiontimeout]=5000
spring.mail.properties[mail.smtp.timeout]=5000
spring.mail.properties[mail.smtp.writetimeout]=5000
~~~

Explanation:

- **host** and **port** specify the SMTP endpoint. Port 587 is only an example for SMTP submission with STARTTLS.
- **username** and **password** are taken from environment variables. Do not write real passwords in source.
- **default-encoding=UTF-8** is suitable for Vietnamese messages.
- **mail.smtp.auth=true** tells the transport to use SMTP authentication as configured.
- **starttls.enable=true** allows the client to upgrade the connection to TLS if the server supports it.
- **starttls.required=true** requires the upgrade process to succeed; if not possible, the sending session fails.
- **ssl.checkserveridentity=true** enables checking the SMTP server's hostname identity when using TLS according to provider support.
- The three timeouts limit the network steps of connecting, reading, and writing data.

The number **5000** denotes 5,000 milliseconds, i.e. 5 seconds. This is an illustrative value; a real application must choose based on the network, provider, and email size.

### 4.1. Placeholders taking values from outside

The syntax:

~~~properties
spring.mail.host=${SMTP_HOST}
spring.mail.port=${SMTP_PORT:587}
~~~

means:

- **${SMTP_HOST}**: asks Spring to resolve the value named SMTP_HOST from Environment.
- **${SMTP_PORT:587}**: takes SMTP_PORT if supplied, otherwise uses 587.
- Placeholders are processed by Spring during configuration resolution, not a special feature of SMTP.

Example runtime environment has:

~~~text
SMTP_HOST=smtp.example.org
SMTP_PORT=587
SMTP_USERNAME=mailer@example.org
SMTP_PASSWORD=<secret supplied by deployment>
~~~

These are illustrative names and values. In practice, variables must be supplied **to the Java process** by the shell, IDE, container, deployment system, or secret manager.

If a required placeholder has no value, the application may fail during binding/sender initialization. This is a signal of missing configuration data, and should not be worked around by hardcoding the password into the file.

### 4.2. Avoid fallbacks for secrets

You should not write:

~~~properties
spring.mail.password=${SMTP_PASSWORD:actual-production-password}
~~~

Because fallback values can be committed, packaged, or shown in configuration files. For credentials, requiring the infrastructure to supply the value is an easier choice to control.

## 5. Equivalent example with application.yml

If the project uses YAML, the same intent can be expressed:

~~~yaml
spring:
  mail:
    host: ${SMTP_HOST}
    port: ${SMTP_PORT:587}
    protocol: smtp
    username: ${SMTP_USERNAME}
    password: ${SMTP_PASSWORD}
    default-encoding: UTF-8

    properties:
      "[mail.smtp.auth]": "true"
      "[mail.smtp.starttls.enable]": "true"
      "[mail.smtp.starttls.required]": "true"
      "[mail.smtp.ssl.checkserveridentity]": "true"
      "[mail.smtp.connectiontimeout]": "5000"
      "[mail.smtp.timeout]": "5000"
      "[mail.smtp.writetimeout]": "5000"
~~~

Structurally:

~~~text
spring
└── mail
    ├── host
    ├── port
    ├── protocol
    ├── username
    ├── password
    ├── default-encoding
    └── properties
        ├── mail.smtp.auth
        ├── mail.smtp.starttls.enable
        ├── mail.smtp.starttls.required
        ├── mail.smtp.ssl.checkserveridentity
        └── timeout...
~~~

Here, the **properties** map passes Jakarta Mail Properties to the mail-sending implementation.

**Why do the keys inside properties have square brackets and quotes?**

The name **mail.smtp.starttls.enable** must be preserved as an **intact key** of the map. Writing **"[mail.smtp.starttls.enable]"** in YAML uses Spring Boot Binder's bracket notation and quotes so YAML understands it as a key name, avoiding interpreting the brackets as collection syntax.

In application.properties, the corresponding form is:

~~~properties
spring.mail.properties[mail.smtp.starttls.enable]=true
~~~

Some examples also write the flat form **spring.mail.properties.mail.smtp.starttls.enable=true**; with map binding, that form can work. However, using brackets clearly unifies the intent to preserve the exact key name the transport expects.

### 5.1. Why are values in the map quoted?

YAML has data types such as boolean and number. Jakarta Mail Properties usually interpret values like **true**, **false**, and **5000** as strings.

Examples using **"true"** and **"5000"** help readers understand these are values passed to the provider. Spring Boot has a type conversion mechanism during binding, but this style reduces confusion when copying into Jakarta Mail configuration.

### 5.2. Proper indentation

Correct:

~~~yaml
spring:
  mail:
    host: smtp.example.org
    port: 587
~~~

Wrong for the intent of setting **spring.mail.port**:

~~~yaml
spring:
  mail:
    host: smtp.example.org
  port: 587
~~~

In the wrong example, **port** is a child of **spring**, not of **spring.mail**. Thus it does not create the **spring.mail.port** key.

Use spaces to indent YAML, avoiding tabs. Two spaces per level is a readable convention.

### 5.3. When do YAML values need quoting?

For values with colons, # signs, or YAML symbols, quote them to avoid parser misinterpretation:

~~~yaml
app:
  mail:
    display-name: "Support Department: Vietnam"
    subject-prefix: "[Support] "
~~~

This is an example of application-defined configuration, not built-in SMTP keys. A seemingly simple string that contains syntax characters may need quotes to keep its value intact.

## 6. Distinguishing Spring Boot and Jakarta Mail properties

You need to know when to use **spring.mail.*** and when to use **mail.smtp.***.

~~~text
application.yml / application.properties
                 |
                 v
         Spring Boot MailProperties
                 |
          +------+------+
          |             |
          v             v
 host, port, user   properties Map
          |             |
          v             v
    JavaMailSenderImpl  Jakarta Mail properties
          |             |
          +------+------+
                 |
                 v
          SMTP transport
~~~

Conversion table:

| Purpose | Spring Boot | Java/Jakarta Mail layer |
| --- | --- | --- |
| SMTP host | spring.mail.host | JavaMailSenderImpl.setHost |
| SMTP port | spring.mail.port | JavaMailSenderImpl.setPort |
| Username | spring.mail.username | JavaMailSenderImpl.setUsername |
| Password | spring.mail.password | JavaMailSenderImpl.setPassword |
| Protocol | spring.mail.protocol | JavaMailSenderImpl.setProtocol |
| Charset | spring.mail.default-encoding | JavaMailSenderImpl.setDefaultEncoding |
| SMTP AUTH | spring.mail.properties[mail.smtp.auth] | mail.smtp.auth |
| STARTTLS | spring.mail.properties[mail.smtp.starttls.enable] | mail.smtp.starttls.enable |
| Require TLS upgrade | spring.mail.properties[mail.smtp.starttls.required] | mail.smtp.starttls.required |
| Implicit TLS | spring.mail.properties[mail.smtp.ssl.enable] | mail.smtp.ssl.enable |
| Connection timeout | spring.mail.properties[mail.smtp.connectiontimeout] | mail.smtp.connectiontimeout |
| Read timeout | spring.mail.properties[mail.smtp.timeout] | mail.smtp.timeout |
| Write timeout | spring.mail.properties[mail.smtp.writetimeout] | mail.smtp.writetimeout |

If writing Java to configure the sender manually:

~~~java
JavaMailSenderImpl sender = new JavaMailSenderImpl();
sender.setHost("smtp.example.org");
sender.setPort(587);
sender.getJavaMailProperties().put(
        "mail.smtp.starttls.enable", "true"
);
~~~

then when using Boot auto-configuration, the equivalent representation is:

~~~properties
spring.mail.host=smtp.example.org
spring.mail.port=587
spring.mail.properties[mail.smtp.starttls.enable]=true
~~~

A common mistake is inventing a key **spring.mail.smtp.auth=true** and expecting Spring Boot to understand it as an SMTP property. With standard configuration, you must use **spring.mail.properties[...]**.

## 7. Separating common and environment-specific configuration

A mail-sending application can run in three environments:

| Environment | SMTP endpoint | Authentication and security |
| --- | --- | --- |
| Local | SMTP capture server, e.g. localhost:1025 | May have no AUTH/TLS in an internal sandbox |
| Staging | SMTP sandbox or test account | Per provider policy |
| Production | Official SMTP service | Managed AUTH/TLS and secrets |

The same Java service can run in every environment if configuration is separated reasonably. Spring Boot supports **profiles** to read files by environment.

Example structure:

~~~text
src/main/resources/
├── application.yml
├── application-local.yml
└── application-prod.yml
~~~

### 7.1. application.yml: shared values

~~~yaml
spring:
  mail:
    protocol: smtp
    default-encoding: UTF-8
    properties:
      "[mail.smtp.connectiontimeout]": "5000"
      "[mail.smtp.timeout]": "5000"
      "[mail.smtp.writetimeout]": "5000"
~~~

Shared timeouts and character encodings do not need to be repeated in every profile when they have the same values.

### 7.2. application-local.yml: using an SMTP capture server

~~~yaml
spring:
  mail:
    host: localhost
    port: 1025
    properties:
      "[mail.smtp.auth]": "false"
      "[mail.smtp.starttls.enable]": "false"
~~~

This configuration is **only appropriate when** the internal SMTP capture server truly does not require AUTH/TLS. Do not apply it casually to a production SMTP server.

The goal of the local environment is to observe the emails the application creates without accidentally sending mail to real users.

### 7.3. application-prod.yml: sending through the official SMTP server

~~~yaml
spring:
  mail:
    host: ${SMTP_HOST}
    port: ${SMTP_PORT:587}
    username: ${SMTP_USERNAME}
    password: ${SMTP_PASSWORD}

    properties:
      "[mail.smtp.auth]": "true"
      "[mail.smtp.starttls.enable]": "true"
      "[mail.smtp.starttls.required]": "true"
      "[mail.smtp.ssl.checkserveridentity]": "true"
~~~

Spring Boot combines the shared configuration with the values specific to the active profile according to Config Data precedence order. Identical keys can be overridden by higher-precedence sources.

### 7.4. Activating a profile

Via environment variable:

~~~text
SPRING_PROFILES_ACTIVE=prod
~~~

Or application run argument:

~~~text
java -jar mail-demo.jar --spring.profiles.active=prod
~~~

In a development environment, you can choose **local** instead of **prod**.

You should not put **spring.profiles.active** inside the **application-prod.yml** file itself and expect it to activate itself. The profile must be selected from a valid configuration source effective before the profile-specific file is loaded.

### 7.5. Profiles are not a place to store passwords

The **application-prod.yml** file can still be committed to Git. Therefore, production configuration should contain **placeholders**, not real passwords:

~~~yaml
spring:
  mail:
    username: ${SMTP_USERNAME}
    password: ${SMTP_PASSWORD}
~~~

The profile name selects the **configuration group**, while the deployment's secret store or environment determines the **secret value**.

## 8. Similar profile configuration using application.properties

There is no need to switch to YAML just to use profiles. A project can also have:

~~~text
src/main/resources/
├── application.properties
├── application-local.properties
└── application-prod.properties
~~~

Common file **application.properties**:

~~~properties
spring.mail.protocol=smtp
spring.mail.default-encoding=UTF-8
spring.mail.properties[mail.smtp.connectiontimeout]=5000
spring.mail.properties[mail.smtp.timeout]=5000
spring.mail.properties[mail.smtp.writetimeout]=5000
~~~

File **application-local.properties**:

~~~properties
spring.mail.host=localhost
spring.mail.port=1025
spring.mail.properties[mail.smtp.auth]=false
spring.mail.properties[mail.smtp.starttls.enable]=false
~~~

File **application-prod.properties**:

~~~properties
spring.mail.host=${SMTP_HOST}
spring.mail.port=${SMTP_PORT:587}
spring.mail.username=${SMTP_USERNAME}
spring.mail.password=${SMTP_PASSWORD}
spring.mail.properties[mail.smtp.auth]=true
spring.mail.properties[mail.smtp.starttls.enable]=true
spring.mail.properties[mail.smtp.starttls.required]=true
spring.mail.properties[mail.smtp.ssl.checkserveridentity]=true
~~~

Both sets of YAML/properties examples accomplish the goal: separating **shared**, **local**, and **prod** configuration without modifying the JavaMailSender class in the service.

A project can mix formats, though choosing the same format for files in the same group usually reduces confusion in operations.

## 9. Precedence order when multiple sources have the same key

Spring Boot does not read just a single file. An application can receive configuration from:

- The application file packaged inside the JAR.
- An application file outside the JAR.
- Files for active profiles.
- Operating system environment variables.
- Java system properties.
- Command-line arguments.
- Imported sources or custom configurations.

Example:

~~~yaml
# application-prod.yml
spring:
  mail:
    host: smtp.primary.example.org
~~~

Yet the runtime environment has:

~~~text
SPRING_MAIL_HOST=smtp.backup.example.org
~~~

Under Boot's common property-source mechanism, the **SPRING_MAIL_HOST** environment variable can override the **spring.mail.host** value from the file. If an operator only reads the YAML, they may think the application is using the primary endpoint.

### 9.1. Directional rules

In default Spring Boot configuration, you can generally understand:

1. **Command-line arguments** like **--spring.mail.host=...** can override environment variables and many configuration sources.
2. **Environment variables** can override application files.
3. **Java system properties** are also a source with higher priority than many configurations in files.
4. **Configuration outside the JAR** usually takes priority over configuration packaged inside, in the default Config Data order.
5. **Files specific to active profiles** override corresponding values from common configuration within Config Data loading rules.

These are directional rules, not an exhaustive list of every source order. An application with **spring.config.import**, a custom PropertySource, test properties, or special launcher configuration may need to check the specific precedence rules of the Spring Boot version in use.

### 9.2. Having both application.properties and application.yml

If both files coexist in one location and contain duplicate keys, Spring Boot usually prefers **.properties** over YAML at that location.

~~~text
src/main/resources/application.properties
src/main/resources/application.yml
~~~

Do not use this duplication as an implicit production/local switching mechanism. Have one clear source for each key and use profiles or intentional overrides when needed.

### 9.3. Difference between the value in the file and the final value

Do not just ask "what does application.yml say?". The real operational question is:

> Which configuration is the JavaMailSender bean using after Spring Environment resolves profiles and property sources?

If an operator edits a file and the application still connects to the old server, check the overriding source, when the application was deployed, and whether the sender was created manually.

## 10. Two ways to supply configuration from environment variables

### 10.1. Method A: using custom-named placeholders

In **application.yml**:

~~~yaml
spring:
  mail:
    host: ${SMTP_HOST}
    port: ${SMTP_PORT:587}
    username: ${SMTP_USERNAME}
    password: ${SMTP_PASSWORD}
~~~

Deployment supplies:

~~~text
SMTP_HOST
SMTP_PORT
SMTP_USERNAME
SMTP_PASSWORD
~~~

This is a way of clearly declaring which variables the application needs.

### 10.2. Method B: using Spring Boot's direct environment variable names

Spring Boot supports relaxed binding, for example:

~~~text
SPRING_MAIL_HOST
SPRING_MAIL_PORT
SPRING_MAIL_USERNAME
SPRING_MAIL_PASSWORD
~~~

These variables can directly supply values corresponding to **spring.mail.host**, **spring.mail.port**, and other keys without needing custom placeholders in the file.

Both methods are suitable. What matters is keeping conventions consistent:

- If the file requires **${SMTP_PASSWORD}**, deployment must supply the corresponding variable.
- If only **SPRING_MAIL_PASSWORD** is supplied, the application can use direct binding/override, but you should not write a placeholder for a different name and then assume every situation works the same.
- When there are multiple sources, you must understand the precedence order and the actual effective value.

### 10.3. Spring Boot does not read every .env file by default

A **.env** file placed beside the repository does not automatically become the JVM's Environment in every way of running Spring Boot.

The shell, IDE, Docker Compose, or deployment tool may load that file and then create environment variables. If no component performs this step, variables like **SMTP_HOST** may still not exist for the Java process.

Therefore, when using .env, know **which tool loads the file**, who has read access, whether the file is committed, and whether variables are passed into the actual running container/process.

## 11. STARTTLS and implicit TLS need different configurations

Two common SMTP configurations:

### 11.1. Port 587 submission with STARTTLS

In properties:

~~~properties
spring.mail.host=${SMTP_HOST}
spring.mail.port=587
spring.mail.properties[mail.smtp.auth]=true
spring.mail.properties[mail.smtp.starttls.enable]=true
spring.mail.properties[mail.smtp.starttls.required]=true
spring.mail.properties[mail.smtp.ssl.checkserveridentity]=true
~~~

YAML equivalent:

~~~yaml
spring:
  mail:
    host: ${SMTP_HOST}
    port: 587
    properties:
      "[mail.smtp.auth]": "true"
      "[mail.smtp.starttls.enable]": "true"
      "[mail.smtp.starttls.required]": "true"
      "[mail.smtp.ssl.checkserveridentity]": "true"
~~~

Conceptual flow: establish TCP connection, SMTP greeting/EHLO, STARTTLS upgrade, authenticate if server requires, then send mail.

**starttls.enable** allows using STARTTLS when the server supports it, whereas **starttls.required** forces the upgrade to succeed. If the application requires securing the sending channel, these two meanings need to be distinguished.

### 11.2. Port 465 with TLS from the start

In properties:

~~~properties
spring.mail.host=${SMTP_HOST}
spring.mail.port=465
spring.mail.properties[mail.smtp.auth]=true
spring.mail.properties[mail.smtp.ssl.enable]=true
spring.mail.properties[mail.smtp.ssl.checkserveridentity]=true
~~~

YAML equivalent:

~~~yaml
spring:
  mail:
    host: ${SMTP_HOST}
    port: 465
    properties:
      "[mail.smtp.auth]": "true"
      "[mail.smtp.ssl.enable]": "true"
      "[mail.smtp.ssl.checkserveridentity]": "true"
~~~

When using implicit TLS, the connection starts with a TLS handshake before SMTP exchanges. Merely changing the port from 587 to 465 while ignoring the endpoint's TLS mechanism can cause the client to wait for the wrong protocol and time out.

Ports 587/465 are common conventions; check the provider's actual requirements. Do not turn off certificate verification or trust every hostname just to fix TLS errors.

## 12. Timeouts and limits of sender configuration

Three commonly used keys:

| Property | Operation limited | Unit |
| --- | --- | --- |
| **mail.smtp.connectiontimeout** | Opening the socket | Millisecond |
| **mail.smtp.timeout** | Reading responses | Millisecond |
| **mail.smtp.writetimeout** | Writing data | Millisecond |

YAML example:

~~~yaml
spring:
  mail:
    properties:
      "[mail.smtp.connectiontimeout]": "5000"
      "[mail.smtp.timeout]": "5000"
      "[mail.smtp.writetimeout]": "5000"
~~~

Or properties:

~~~properties
spring.mail.properties[mail.smtp.connectiontimeout]=5000
spring.mail.properties[mail.smtp.timeout]=5000
spring.mail.properties[mail.smtp.writetimeout]=5000
~~~

Timeouts help avoid waiting too long when the SMTP server or network path has an incident. However, three 5-second timeouts **do not prove the total time of send() will be only 5 seconds**, because a sending session involves multiple steps and there may be retries at another layer.

For an application serving HTTP requests, consider a mail-sending queue and retry policy instead of making user requests wait too long on the SMTP transport.

## 13. Application-specific configuration outside spring.mail.*

Beyond sender properties, an application may need a display name, From email, and flags enabling notifications. These values belong to **notification business logic**, not the SMTP connection.

YAML example:

~~~yaml
app:
  notifications:
    from-address: noreply@example.org
    display-name: "Notification System"
    welcome-enabled: true
~~~

Properties format:

~~~properties
app.notifications.from-address=noreply@example.org
app.notifications.display-name=Notification System
app.notifications.welcome-enabled=true
~~~

These are **keys defined by the application itself**. Spring Boot does not automatically put **app.notifications.from-address** into JavaMailSenderImpl; the service or the application's **@ConfigurationProperties** class must read them.

Example:

~~~java
import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "app.notifications")
public record NotificationProperties(
        String fromAddress,
        String displayName,
        boolean welcomeEnabled
) {}
~~~

This record needs to be registered via a mechanism such as **@ConfigurationPropertiesScan** or **@EnableConfigurationProperties(NotificationProperties.class)**.

Distinguish:

- **spring.mail.***: connection and sender transport.
- **app.notifications.***: business choices and behavior controlled by the application itself.

You should not put business information into arbitrary transport keys or invent **spring.mail.custom-from** keys and assume Boot will use them automatically.

## 14. A complete example: a service independent of configuration format

Configuration can be properties or YAML, yet the Java service can remain unchanged:

~~~java
package com.example.maildemo;

import org.springframework.mail.SimpleMailMessage;
import org.springframework.mail.javamail.JavaMailSender;
import org.springframework.stereotype.Service;

@Service
public class ConfirmationMailService {

    private final JavaMailSender sender;
    private final NotificationProperties options;

    public ConfirmationMailService(
            JavaMailSender sender,
            NotificationProperties options
    ) {
        this.sender = sender;
        this.options = options;
    }

    public void sendConfirmation(String recipient) {
        if (!options.welcomeEnabled()) {
            return;
        }

        SimpleMailMessage message = new SimpleMailMessage();
        message.setFrom(options.fromAddress());
        message.setTo(recipient);
        message.setSubject("Registration confirmation");
        message.setText("We have received your registration.");

        sender.send(message);
    }
}
~~~

The example assumes **NotificationProperties** in the previous section has been registered as a bean. The service receives **JavaMailSender** from Spring Boot and business configuration from **app.notifications.***.

When switching environments, there is no need to recreate the sender in the service. Spring Boot will resolve property sources at startup and configure the appropriate bean.

### If using MimeMessageHelper

When HTML or attachments are needed, still use the same sender:

~~~java
import jakarta.mail.MessagingException;
import jakarta.mail.internet.MimeMessage;
import org.springframework.mail.javamail.MimeMessageHelper;

public void sendHtmlNotice(String recipient)
        throws MessagingException {

    MimeMessage message = sender.createMimeMessage();
    MimeMessageHelper helper = new MimeMessageHelper(
            message, false, "UTF-8"
    );

    helper.setFrom(options.fromAddress());
    helper.setTo(recipient);
    helper.setSubject("Notification");
    helper.setText("<p>You have a <strong>new notification</strong>.</p>", true);

    sender.send(message);
}
~~~

The message type may differ, but host, port, TLS, AUTH, and timeouts still come from the configured sender, not from whether SimpleMailMessage or MimeMessage is used.

## 15. When Spring Boot does not use the configuration as expected

### 15.1. Missing the mail starter

Having application.yml is not enough to get a JavaMailSender bean. The classpath needs the appropriate libraries for Boot auto-config to work.

### 15.2. Host or suitable Session not yet declared

Without the input values required by auto-configuration, the mail-sending bean may not be created. Then you need to check the conditions that activate the sender, not only look at the missing-bean error in the service.

### 15.3. Manual JavaMailSender bean present

If the application has declared:

~~~java
@Bean
public JavaMailSender javaMailSender() {
    JavaMailSenderImpl sender = new JavaMailSenderImpl();
    sender.setHost("smtp.manual.example.org");
    return sender;
}
~~~

Boot's auto-configuration will usually yield to the user-defined bean. Keys like **spring.mail.host** in YAML are not necessarily applied to a self-created bean if code does not actively read them.

Therefore, choose one clear mechanism:

- Boot auto-config uses **spring.mail.***.
- A self-created bean reads configuration through Environment/ConfigurationProperties with deterministic rules.

Avoid configuring a manual bean and application files in two places and assuming Boot merges everything automatically.

### 15.4. Mail Session from JNDI

Some application servers pre-manage **jakarta.mail.Session**. Spring Boot can be configured to reference that session via **spring.mail.jndi-name** in supported contexts.

This is an advanced scenario. For standalone SMTP applications, configuring host/port/credentials directly is usually easier to understand. When using an infrastructure-supplied Session, understand the property source and precedence order clearly.

## 16. How to find the effective configuration values

When an application sends mail to the wrong SMTP endpoint, check:

1. The actual active profile.
2. Which application files are packaged and loaded.
3. Whether environment variables and command-line args override them.
4. Whether any external config or import changes values.
5. Whether the JavaMailSender bean is created automatically or manually.
6. Whether **spring.mail.properties[...]** keys are passed intact to Jakarta Mail.

You can read some non-sensitive values via Environment:

~~~java
import org.springframework.core.env.Environment;

public String mailEndpoint(Environment env) {
    String host = env.getProperty(
            "spring.mail.host", "(not configured)"
    );
    String port = env.getProperty(
            "spring.mail.port", "(default)"
    );
    return host + ":" + port;
}
~~~

This is an example of reading properties. If the sender bean is created manually or uses JNDI, Environment does not necessarily reflect every final property of that bean.

**Do not log passwords, tokens, the entire Environment, or JavaMail Session Properties without checking for sensitive data.**

In applications with Spring Boot Actuator, Environment/configuration inspection endpoints can assist diagnosis per security settings and sensitive-value masking mechanisms. Do not expose configuration endpoints publicly just to debug email.

### Commonly encountered errors

| Symptom | What to check |
| --- | --- |
| Cannot create JavaMailSender bean | Dependency, host, auto-config conditions |
| Host differs from configuration in YAML | Profile, environment variables, system properties, external config |
| AUTH fails | Credentials, mail.smtp.auth, TLS, provider policy |
| STARTTLS does not work | Port, mail.smtp.starttls.enable/required, server capabilities |
| TLS handshake fails | Wrong implicit TLS/STARTTLS mode, hostname, certificate chain |
| Send waits very long | Connection/read/write timeouts |
| Works locally but fails in prod | Endpoint, firewall, secret, account permissions, provider policy |
| Sends successfully but not seen in inbox | Bounce, spam, quota, SPF/DKIM/DMARC, delivery status |

SMTP errors can occur after a connection has already succeeded, for example recipient rejected or message too large. **testConnection** does not replace controlled test sends.

## 17. Does spring.mail.test-connection solve every problem?

Spring Boot supports an option to test the mail connection in appropriate configurations:

~~~properties
spring.mail.test-connection=true
~~~

Or YAML:

~~~yaml
spring:
  mail:
    test-connection: true
~~~

When the check mechanism is activated, Boot can try connecting to SMTP during startup. This helps detect a wrong host/port or authentication details earlier.

But you must distinguish:

| Milestone | Can confirm | Cannot assert |
| --- | --- | --- |
| JavaMailSender bean created successfully | A sender object exists | The SMTP server is actually reachable |
| Connection check succeeds | Session established to server per current config | A specific recipient is allowed to receive |
| send() completes | Send request completed at sending layer per received response | The recipient opened the email |
| Provider reports delivery | Delivery signal exists per provider definition | The user read the content |

Enabling connection checking at startup also makes the application depend on SMTP reachability at startup time. For a service whose only function is sending email, this policy may fit; for an application with many functions, you may want separate health checks and queue-based sending.

## 18. Scenario: using environment variables in production deployment

Suppose a team shares one Spring Boot build for local and production.

**In the repository:**

~~~text
src/main/resources/
├── application.yml
├── application-local.yml
└── application-prod.yml
~~~

**In application.yml:** shared protocol, encoding, and timeout configuration.

**In application-local.yml:** SMTP capture server of the development environment.

**In application-prod.yml:** production host, port, and TLS flags, reading credentials from placeholders.

**In deployment:** supply these variables under a secret-management mechanism:

~~~text
SPRING_PROFILES_ACTIVE=prod
SMTP_HOST=smtp.example.org
SMTP_PORT=587
SMTP_USERNAME=mailer@example.org
SMTP_PASSWORD=<protected runtime secret>
~~~

This model lets **the same Java source** operate across multiple environments. The difference between local and prod is expressed in property sources, while email-sending logic does not need to know the environment name itself.

### Why not preset SPRING_PROFILES_ACTIVE=local in the build?

If the production environment forgets to override it, the application may connect to the SMTP sandbox by mistake. A good deployment process should actively supply the profile and check required values for each environment.

### Is it mandatory to split every file by profile?

No. If the application is small and has only one environment, a single configuration file plus environment variables may suffice. Profiles are useful when there are **genuinely different groups of values**. Splitting too many files each holding one key also makes tracing harder.

## 19. Security principles to uphold when separating configuration

### 19.1. Do not commit credentials

Do not store real SMTP passwords or tokens in application.properties, application.yml, committed sample files, logs, screenshots, or docs. Environment variables or a secret manager must be provisioned with appropriate access permissions.

### 19.2. Separate configuration from mail-sending permissions

A syntactically valid recipient or From address can still violate business permissions. Configuring JavaMailSender properly does not replace checking who is allowed to receive which content.

### 19.3. Do not disable TLS just to send

If you hit a TLS error, check the hostname, certificate, JDK truststore, port, and connection type. Do not use a trust-everything setting or disable server verification in production.

### 19.4. Timeouts must be finite and appropriate

Configuring timeouts helps the application avoid hanging indefinitely on certain network operations, but you also need retry limits, queues, send-state management, and error observability.

### 19.5. Avoid printing sensitive configuration when diagnosing

Log only necessary data such as environment, non-secret endpoints, error types, or SMTP codes. Avoid logging passwords, access tokens, and sensitive message content.

### 19.6. Distinguish sending from final delivery

JavaMailSender connects to SMTP and hands the message to the sending system. Whether the recipient actually sees the message in their inbox still depends on delivery infrastructure, spam filtering, domain policies, and mailbox state. Proper sender configuration does not by itself guarantee all downstream steps succeed.

## 20. Practice and reinforcement questions

**Question 1: I changed application.yml, yet the application still connects to the old SMTP server. Why?**

There may be a properties file with duplicate keys, a different active profile, overriding environment variables or command-line args, a manually created sender bean, or the new configuration was not deployed. Check the effective configuration source.

**Question 2: Do I need to use both application.properties and application.yml?**

No. Choosing one primary format is usually enough. Both support spring.mail.* and Spring profiles.

**Question 3: If using application-prod.properties, do I need to rewrite every timeout from application.properties?**

No, as long as the shared values still fit and the profile-specific file does not override them. Declare only the keys that differ by environment.

**Question 4: What is spring.mail.properties[mail.smtp.auth]?**

It is an entry in the JavaMail Properties map that Spring Boot passes to the SMTP transport. It differs from direct properties such as spring.mail.host.

**Question 5: Can SMTP_PASSWORD be put into a .env file?**

You can use a deployment system that reads .env and supplies it as environment variables, though Spring Boot does not automatically load every .env. Protect the file and avoid committing secrets.

**Question 6: Should port 465 be used with starttls.enable=true?**

If the 465 endpoint uses implicit TLS as commonly configured, use **mail.smtp.ssl.enable=true**. Port and TLS mechanism must match the provider's specific requirements.

**Question 7: Can a SPRING_MAIL_HOST variable override host in YAML?**

Under Spring Boot's common relaxed binding and property-source precedence, yes. This is helpful for deployment, yet also a common reason readers of YAML misunderstand the effective value.

**Question 8: When do you need to write a custom @ConfigurationProperties class?**

When the application has a configuration group it owns, such as **app.notifications.from-address** or **app.notifications.welcome-enabled**. There is no need to create a separate class just to re-read spring.mail.* properties already supported by Boot auto-config.

**Question 9: Does test-connection=true send a test email?**

No. It serves to check connectivity/sending session per configuration, not proof that mail reached an inbox.

**Question 10: Can the same Java code be shared for local and production?**

Yes. Services depend on JavaMailSender; profiles and the runtime environment decide which endpoint the sender connects to. That is the main benefit of separating configuration.

## 21. Key takeaways on separating Spring Boot Mail configuration

**application.properties** and **application.yml** are two ways of representing the same Spring Boot property source system. With Spring Framework Mail, **spring.mail.host/port/username/password** declare sender parameters, while **spring.mail.properties[...]** passes AUTH, TLS, and timeout options into Jakarta Mail.

Put **shared configuration** in the base application file, **environment differences** in profiles or external configuration, and **secrets** in protected sources. Business code injects **JavaMailSender** so it does not depend on SMTP addresses or credential management.

When the application sends mail unexpectedly, trace the **effective configuration values** after Spring Boot resolves all property sources, then cross-check with the SMTP server's endpoint and policy. This organization lets the same application deploy consistently across environments while maintaining clear boundaries between code, configuration, and secrets.
