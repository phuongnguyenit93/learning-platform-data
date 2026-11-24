# Configuring the sender across multiple Spring profiles

## 1. Why configure the mail sender by environment?

In an application using **Spring Boot** and **Spring Framework Mail**, the same email-sending feature may run in many environments: the developer's machine, the test environment, staging, and production. Business code can still call the same `JavaMailSender` interface, while the SMTP server, account, TLS, permitted recipients, and level of outbound email sending need to be managed per environment.

For example:

- In **local**, emails should be routed to an SMTP sink such as Mailpit/MailHog so developers can observe the content without sending to real customers.
- In **test**, logic tests should use a fake/mock sender; integration tests can use a controlled test SMTP server.
- In **staging**, the application can send through a provider's test account, with recipient-address restrictions and safe configuration.
- In **production**, the application sends through the official service, using credentials managed as secrets, TLS, and appropriate operational policies.

If every environment shares one SMTP endpoint and password in `application.yml`, running locally could accidentally send real emails or staging could lose access due to using the wrong account. **Spring profiles** help separate configuration by environment while the mail-sending code depends on the same abstraction.

> The goal of a profile is to **select which configuration to use when running the application**. Profiles do not create an anti-misdirected-send system by themselves; the application still needs access control, recipient checks, and appropriate security policies.

## 2. How do profiles affect JavaMailSender?

A **Spring profile** is an identifier name such as `local`, `test`, `staging`, or `prod`. When a profile is activated, Spring Boot can load specific configuration from `application-{profile}.yml`, and Spring Framework can enable/disable beans annotated with `@Profile`.

With ordinary mail configuration, Spring Boot provides **MailSender auto-configuration**: when the classpath and configuration conditions are met, Boot creates a `JavaMailSender` bean (usually implemented by `JavaMailSenderImpl`), assigns the `spring.mail.*` properties, and lets services inject the `JavaMailSender` interface.

~~~mermaid
flowchart TD
    A["Spring Boot starts"] --> B["Reads application.yml"]
    B --> C["Determines active profile"]
    C --> D["Loads profile-specific configuration"]
    D --> E["Merges property sources and overriding values"]
    E --> F["Creates/configures JavaMailSender if conditions are met"]
    F --> G["Injects JavaMailSender into services"]
    G --> H["When requested: creates MIME and sends via SMTP"]
~~~

Reading configuration and creating the bean are **startup-time** steps; connecting to SMTP usually only occurs when code sends email or when the application actively tests the connection. Therefore, configuration loading successfully does not mean the SMTP credentials or network path are definitely correct.

### 2.1. Two different scopes of profiles

| Mechanism | Example | Effect |
| --- | --- | --- |
| **Configuration by profile** | `application-local.yml`, `application-prod.yml` | Properties `spring.mail.host`, `port`, TLS, timeouts, etc. are chosen per environment |
| **Bean by profile** | `@Profile("test")` on a `@Configuration`/`@Bean` | A dedicated sender implementation appears only in that profile |
| **Profile during testing** | `@ActiveProfiles("test")` | Spring Test initializes the context with the profile to be tested |
| **Activation from environment** | `SPRING_PROFILES_ACTIVE=prod` | Selects the profile at startup without modifying source |

**With a single SMTP sender per environment, you usually only need to configure `spring.mail.*` per profile.** There is no need to write identical `@Configuration` classes just to change the host or port.

If you need to swap the *implementation* (for example test uses a fake sender, production uses real SMTP) or have multiple concurrent sending accounts, conditional bean configuration or named senders become necessary.

## 3. Easy-to-manage configuration file structure

A Spring Boot project can organize:

~~~text
src/main/resources/
├── application.yml
├── application-local.yml
├── application-staging.yml
└── application-prod.yml

src/test/resources/
└── application-test.yml
~~~

Meaning:

- `application.yml` contains **shared configurations** independent of environment, such as timeouts.
- `application-local.yml` specifies the SMTP sandbox endpoint on the developer's machine.
- `application-staging.yml` specifies staging's account and connection policy.
- `application-prod.yml` specifies production's policy; takes credentials from a secret source.
- `application-test.yml` contains configuration specific to tests; logic tests can replace the sender with a fake/mock, while integration tests can use a dedicated sink.

The names `local`, `staging`, `prod` are not fixed Spring profile names. They are chosen by the development team and should align with the deployment process.

### 3.1. application.yml: place only shared values

Example:

~~~yaml
# src/main/resources/application.yml
spring:
  mail:
    default-encoding: UTF-8
    properties:
      mail.smtp.connectiontimeout: 5000
      mail.smtp.timeout: 5000
      mail.smtp.writetimeout: 5000
~~~

Explanation:

- `spring.mail.default-encoding` sets the default encoding when creating messages per Boot's configuration.
- `mail.smtp.connectiontimeout` limits the TCP connection wait time.
- `mail.smtp.timeout` limits the wait time for reading data over the SMTP socket.
- `mail.smtp.writetimeout` limits the write wait time.
- The timeout values here are in **milliseconds**; they are only examples and need adjusting according to network conditions/provider response time.

To avoid misdirected sends, the example intentionally **does not place** `spring.mail.host`, production accounts, or passwords in the shared file. Whichever environment needs real SMTP supplies the appropriate endpoint itself. If the application must have a `JavaMailSender` in every environment, ensure the corresponding profile can create the bean or supply a fake/mocked bean for tests.

### 3.2. application-local.yml: SMTP sandbox

~~~yaml
# src/main/resources/application-local.yml
spring:
  mail:
    host: 127.0.0.1
    port: 1025
    properties:
      mail.smtp.auth: false
      mail.smtp.starttls.enable: false
      mail.smtp.starttls.required: false
~~~

Assumes the developer's machine runs an **SMTP sink** (such as Mailpit) at `127.0.0.1:1025`. This is a local endpoint example; without an SMTP sink running, sending will fail because the connection cannot reach the server.

An SMTP sink receives messages and stores them in a testing UI instead of routing them out to the Internet. Depending on the tool's configuration, emails can be viewed from a dedicated web UI.

**Do not copy the `auth: false`/`starttls: false` configuration to production.** Disabling authentication and TLS in this example is only for an isolated local SMTP sink. If running the application in a container, `127.0.0.1` points to **the application container itself**, not necessarily the host machine or an SMTP container. In a Docker Compose environment, use the service name/network address declared for the SMTP sink.

### 3.3. application-staging.yml: SMTP submission with STARTTLS

~~~yaml
# src/main/resources/application-staging.yml
spring:
  mail:
    host: ${SMTP_HOST}
    port: ${SMTP_PORT:587}
    username: ${SMTP_USERNAME}
    password: ${SMTP_PASSWORD}
    properties:
      mail.smtp.auth: true
      mail.smtp.starttls.enable: true
      mail.smtp.starttls.required: true
      mail.smtp.ssl.checkserveridentity: true
~~~

Spring Boot resolves placeholders from the environment or other property sources:

- `${SMTP_HOST}`: required SMTP hostname.
- `${SMTP_PORT:587}`: takes the port from `SMTP_PORT`; if unconfigured, uses `587`.
- `${SMTP_USERNAME}` and `${SMTP_PASSWORD}`: take authentication info from external configuration sources.

For submission over port `587`, `STARTTLS` upgrades an already-opened TCP connection to TLS. `mail.smtp.starttls.required=true` forces the transport not to continue sending on a connection that does not meet this requirement. The `mail.smtp.ssl.checkserveridentity=true` property requests checking the server name against the certificate in a Jakarta Mail SMTP provider that supports the corresponding property.

Staging usually needs additional policies at the business layer: restricting recipients, using test domains/accounts, tagging subjects, and logging sends. Those measures **do not appear automatically** just because the profile is named `staging`.

### 3.4. application-prod.yml: production policy

A production example that also uses SMTP submission via STARTTLS:

~~~yaml
# src/main/resources/application-prod.yml
spring:
  mail:
    host: ${SMTP_HOST}
    port: ${SMTP_PORT:587}
    username: ${SMTP_USERNAME}
    password: ${SMTP_PASSWORD}
    properties:
      mail.smtp.auth: true
      mail.smtp.starttls.enable: true
      mail.smtp.starttls.required: true
      mail.smtp.ssl.checkserveridentity: true
~~~

The two staging/prod files can look similar in security method while still using **different environment variable values**. The benefit of keeping them separate is being able to proactively adjust environment-specific policies without modifying mail-sending code.

If the production provider uses **TLS immediately upon opening the connection** on port `465` (*implicit TLS*), the configuration must switch to the appropriate mode, for example:

~~~yaml
spring:
  mail:
    host: ${SMTP_HOST}
    port: 465
    username: ${SMTP_USERNAME}
    password: ${SMTP_PASSWORD}
    properties:
      mail.smtp.auth: true
      mail.smtp.ssl.enable: true
      mail.smtp.ssl.checkserveridentity: true
~~~

This is an **alternative option** to the STARTTLS configuration above; do not merge the two examples arbitrarily. Choose the port and TLS mechanism per the SMTP provider's documentation; do not assume `465`/`587` are always open in every infrastructure.

### 3.5. application-test.yml: distinguishing unit tests from SMTP integration tests

For service logic tests, the suitable choice is usually replacing `JavaMailSender` with a mock/fake so the test verifies created content and service behavior **without opening outbound connections**. When using Spring Test, activate the profile:

~~~java
@SpringBootTest
@ActiveProfiles("test")
class NotificationServiceTest {
    // Configure or replace JavaMailSender with a mock/fake
    // according to the Spring Test mechanism the project uses.
}
~~~

In Spring Boot 3.3, Boot Test's `@MockBean` can be used to replace the sender in the test context. If code is allowed to call `createMimeMessage()`, the mock needs to return a valid `MimeMessage` (or use a fake sender that records sent messages); a mock returning `null` for every method will not accurately reflect the message-creation path.

For **SMTP integration tests**, you can provide an `application-test.yml` pointing to a test SMTP sink/container:

~~~yaml
# src/test/resources/application-test.yml
spring:
  mail:
    host: 127.0.0.1
    port: 1025
    properties:
      mail.smtp.auth: false
      mail.smtp.starttls.enable: false
~~~

These values are only appropriate when a real test-managed SMTP sink exists at that address. When running in CI/containers, the hostname and port must be supplied to tests by the environment, avoiding relying on an accidental service on a developer's machine. Integration tests should read messages in the SMTP sink to confirm envelope/body/MIME per test objective, rather than sending to public email addresses.

## 4. Activating a profile when running the application

Profile-specific configuration is loaded only when the corresponding profile is active. A few example ways:

~~~bash
# On a Unix-like environment, activate the profile before running:
SPRING_PROFILES_ACTIVE=staging java -jar mail-service.jar

# Using a JVM system property (suitable in many environments):
java -Dspring.profiles.active=prod -jar mail-service.jar

# Using a Spring Boot command-line argument:
java -jar mail-service.jar --spring.profiles.active=local
~~~

On Windows PowerShell, you can set the environment variable in the current shell:

~~~powershell
$env:SPRING_PROFILES_ACTIVE = "local"
java -jar mail-service.jar
~~~

Example with tests:

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.context.ActiveProfiles;

@SpringBootTest
@ActiveProfiles("test")
class MailProfileContextTest {
    @Test
    void contextLoads() {
        // Verify the test profile context initializes.
    }
}
~~~

`spring.profiles.active` can be supplied from property sources outside the application (for example the `SPRING_PROFILES_ACTIVE` environment variable or a command-line argument). For systems with multiple profiles, the value is usually a comma-separated list:

~~~text
SPRING_PROFILES_ACTIVE=staging,observability
~~~

You need to understand **property source order and precedence**: higher-priority configuration can override values from a profile file. When multiple active profiles have overlapping properties, a later-processed profile can override values of an earlier profile within the corresponding configuration group. Do not use conflicting profiles that both supply SMTP hosts/credentials, such as `local,prod`, without a clear merging convention and strict control.

### 4.1. Do not hardcode active profiles in Java code

Example of what not to do:

~~~java
if (environment.getActiveProfiles()[0].equals("prod")) {
    // Manually creating production transport in multiple places in code.
}
~~~

This approach depends on profile order, can fail when there is no active profile, and creates duplicated configuration alongside Spring Boot. For an ordinary mail sender, let the environment configuration system select `spring.mail.*`, while services only inject `JavaMailSender`.

### 4.2. Active profiles must be placed in valid declaration locations

Spring Boot supports files named `application-prod.yml` and multi-document YAML using `spring.config.activate.on-profile`, for example:

~~~yaml
spring:
  mail:
    default-encoding: UTF-8

---
spring:
  config:
    activate:
      on-profile: local
  mail:
    host: 127.0.0.1
    port: 1025

---
spring:
  config:
    activate:
      on-profile: prod
  mail:
    host: ${SMTP_HOST}
    port: ${SMTP_PORT:587}
~~~

This is the **multi-document YAML** option instead of separate `application-*.yml` files. Just choose one consistent organization style so it is easy to read and review.

Do not declare `spring.profiles.active` or `spring.profiles.include` inside a document that is itself activated only by `spring.config.activate.on-profile` or inside a profile-specific file. Spring Boot restricts properties controlling profile activation in profile-specific locations to avoid unpredictable recursive activation loops. Activate profiles from the shared source or runtime environment.

## 5. Which configuration takes effect when multiple sources supply the same property?

Spring Boot's configuration system merges multiple **property sources**: configuration files, environment variables, system properties, command-line arguments, and sources added by the application. When the same property is declared in multiple places, the **value with higher precedence** determines the effective value.

Example:

~~~yaml
# application.yml
spring:
  mail:
    port: 1025
~~~

~~~yaml
# application-prod.yml
spring:
  mail:
    port: 587
~~~

~~~text
SPRING_PROFILES_ACTIVE=prod
SPRING_MAIL_PORT=2525
~~~

In this common setup, `SPRING_MAIL_PORT` is an environment variable that can override the configuration in the file, so the effective value of `spring.mail.port` is `2525`. If there is a higher-priority command-line argument:

~~~text
--spring.mail.port=465
~~~

then `465` can become the effective value. Cases with config imports, custom configuration sources, or special deployment mechanisms can make the overall order more complex; so when in doubt, inspect the **actual property sources of the application context** rather than guessing from file names.

### 5.1. Distinguishing direct environment variables from placeholders

Two valid ways of configuring that work differently:

**Direct binding using Boot's property names:**

~~~text
SPRING_MAIL_HOST=smtp.example.net
SPRING_MAIL_PORT=587
SPRING_MAIL_USERNAME=some-account
SPRING_MAIL_PASSWORD=provided-secret
~~~

**Or having YAML read variables with custom names:**

~~~yaml
spring:
  mail:
    host: ${SMTP_HOST}
    port: ${SMTP_PORT:587}
    username: ${SMTP_USERNAME}
    password: ${SMTP_PASSWORD}
~~~

In the second approach, `SMTP_HOST` is not Boot's `spring.mail.host` property name; it is only pulled in because of the `${SMTP_HOST}` placeholder. Both approaches work, but do not pick arbitrary variable names and expect Spring to automatically treat all of them as `spring.mail.*`.

### 5.2. Do not put secrets into logs when checking precedence

When verifying the configuration in use, you can record **non-sensitive** information such as active profiles, transport type, approved displayable host, and port. Do not record passwords or tokens.

Example:

~~~java
package com.example.mail;

import java.util.Arrays;

import org.springframework.core.env.Environment;
import org.springframework.stereotype.Component;

@Component
public class MailEnvironmentDescription {

    private final Environment environment;

    public MailEnvironmentDescription(Environment environment) {
        this.environment = environment;
    }

    public String describe() {
        return "activeProfiles="
                + Arrays.toString(environment.getActiveProfiles())
                + ", smtpPort="
                + environment.getProperty("spring.mail.port", "unset");
    }
}
~~~

This is only an example of reading metadata; in a real application, information such as internal host/domain sometimes also needs restricted visibility. To identify which source provides a property, you can use Spring Boot's configuration inspection tools in an **authorized environment**, ensuring sensitive values remain masked.

### 5.3. "Default profile" does not mean prod profile

If no active profile is configured, Spring uses the default profile (usually named `default`) for corresponding beans and configuration documents. `application.yml` is still read. When needed, `application-default.yml` can hold configuration used when no profile has been activated.

Do not implicitly treat "no profile" as running in production. A mail-sending application should have an **explicit startup convention**: production must specify the appropriate profile and credentials; an unknown environment must not automatically send mail to real users.

## 6. When is @Profile needed on a sender bean?

An ordinary service can just inject:

~~~java
package com.example.notification;

import jakarta.mail.MessagingException;
import jakarta.mail.internet.MimeMessage;
import org.springframework.mail.javamail.JavaMailSender;
import org.springframework.mail.javamail.MimeMessageHelper;
import org.springframework.stereotype.Service;

@Service
public class NotificationMailer {

    private final JavaMailSender mailSender;

    public NotificationMailer(JavaMailSender mailSender) {
        this.mailSender = mailSender;
    }

    public void send(String recipient, String body)
            throws MessagingException {
        MimeMessage message = mailSender.createMimeMessage();
        MimeMessageHelper helper =
                new MimeMessageHelper(message, false, "UTF-8");

        helper.setFrom("notifications@example.com");
        helper.setTo(recipient);
        helper.setSubject("System notification");
        helper.setText(body, false);

        mailSender.send(message);
    }
}
~~~

This class does not need to know whether the application is in `local` or `prod`. Spring will inject the effective `JavaMailSender` bean according to the context, and that bean uses the corresponding environment configuration.

Use `@Profile` only when you need to swap the **bean/implementation**, for example a service blocking real sends in tests or an adapter dedicated to a legacy system:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.Profile;
import org.springframework.mail.javamail.JavaMailSender;

@Configuration(proxyBeanMethods = false)
@Profile("legacy-smtp")
class LegacyMailConfiguration {

    @Bean
    JavaMailSender legacyMailSender() {
        // Build JavaMailSenderImpl from safe configuration
        // only when the legacy-smtp profile is active.
        throw new UnsupportedOperationException(
                "Configuration skeleton example, concrete implementation needed");
    }
}
~~~

The example above **only illustrates annotation placement**, not yet a usable bean. In real implementation, the method must return a fully configured `JavaMailSenderImpl`. If `spring.mail.*` and Boot auto-config are already present, creating an unnecessary custom bean can cause auto-configuration to **back off** or cause conflicts by bean type. Choose one clear ownership mechanism for mail-sending configuration.

### 6.1. @Profile and @ConditionalOnProperty are different

| Need | Appropriate mechanism |
| --- | --- |
| Enable separate config for `prod` | `application-prod.yml` file or `@Profile("prod")` when swapping beans |
| Create fake mailer only in `test` | `@Profile("test")` on the test configuration bean |
| Enable notification sending by a business flag | `@ConditionalOnProperty` with a property such as `app.notifications.email.enabled` |
| Set host and port per environment | `spring.mail.*` in profile-specific files |
| Use two SMTP accounts simultaneously in one profile | Two named beans and `@Qualifier` or a separate abstraction |

A profile describes the **active environment or configuration set**; a feature flag describes **the state of a feature**. There is no need to create a new profile for every business choice. At the same time, when toggling email sending via a feature flag, check the execution path to ensure tasks do not use another sender that bypasses that mechanism.

### 6.2. Example selecting a different configuration with @Profile

If an application needs to create `JavaMailSenderImpl` itself for a specific profile, it can configure:

~~~java
package com.example.mail.config;

import java.util.Properties;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.Profile;
import org.springframework.mail.javamail.JavaMailSender;
import org.springframework.mail.javamail.JavaMailSenderImpl;

@Configuration(proxyBeanMethods = false)
@Profile("custom-smtp")
public class CustomSmtpConfiguration {

    @Bean
    JavaMailSender mailSender(
            org.springframework.core.env.Environment environment) {

        JavaMailSenderImpl sender = new JavaMailSenderImpl();
        sender.setHost(environment.getRequiredProperty("app.smtp.host"));
        sender.setPort(Integer.parseInt(
                environment.getProperty("app.smtp.port", "587")));
        sender.setUsername(
                environment.getRequiredProperty("app.smtp.username"));
        sender.setPassword(
                environment.getRequiredProperty("app.smtp.password"));
        sender.setDefaultEncoding("UTF-8");

        Properties properties = sender.getJavaMailProperties();
        properties.put("mail.smtp.auth", "true");
        properties.put("mail.smtp.starttls.enable", "true");
        properties.put("mail.smtp.starttls.required", "true");
        properties.put("mail.smtp.ssl.checkserveridentity", "true");
        properties.put("mail.smtp.connectiontimeout", "5000");
        properties.put("mail.smtp.timeout", "5000");
        properties.put("mail.smtp.writetimeout", "5000");

        return sender;
    }
}
~~~

With the `custom-smtp` profile, `app.smtp.*` properties must be supplied by appropriate configuration or the runtime environment. This example shows how a bean is created only in one profile; it does not require editing the `NotificationMailer` service code above.

This is a **custom** option, intended for when tighter control over sender creation is needed. For ordinary applications, `spring.mail.*` with Spring Boot auto-configuration remains the simpler setup.

## 7. Multiple profiles and multiple concurrent senders are two different problems

A common misconception:

> "I have `application-staging.yml` and `application-prod.yml`, so Spring creates both `JavaMailSender`s?"

No. Within one Spring context, properties for active profiles are merged to form the **effective configuration**. The default model is usually **one `JavaMailSender` using the current configuration**, not spawning one sender per file.

If the application needs to send transactional emails via provider A and support emails via provider B simultaneously, create **two explicitly named beans**. Example:

~~~yaml
app:
  mail:
    transactional:
      host: ${TRANSACTIONAL_SMTP_HOST}
      port: ${TRANSACTIONAL_SMTP_PORT:587}
      username: ${TRANSACTIONAL_SMTP_USERNAME}
      password: ${TRANSACTIONAL_SMTP_PASSWORD}
    support:
      host: ${SUPPORT_SMTP_HOST}
      port: ${SUPPORT_SMTP_PORT:587}
      username: ${SUPPORT_SMTP_USERNAME}
      password: ${SUPPORT_SMTP_PASSWORD}
~~~

Bean configuration:

~~~java
package com.example.mail.config;

import java.util.Properties;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.mail.javamail.JavaMailSender;
import org.springframework.mail.javamail.JavaMailSenderImpl;

@Configuration(proxyBeanMethods = false)
public class MultipleSendersConfiguration {

    @Bean("transactionalMailSender")
    JavaMailSender transactionalSender(
            @Value("${app.mail.transactional.host}") String host,
            @Value("${app.mail.transactional.port:587}") int port,
            @Value("${app.mail.transactional.username}") String user,
            @Value("${app.mail.transactional.password}") String password) {
        return createSender(host, port, user, password);
    }

    @Bean("supportMailSender")
    JavaMailSender supportSender(
            @Value("${app.mail.support.host}") String host,
            @Value("${app.mail.support.port:587}") int port,
            @Value("${app.mail.support.username}") String user,
            @Value("${app.mail.support.password}") String password) {
        return createSender(host, port, user, password);
    }

    private JavaMailSender createSender(
            String host, int port, String user, String password) {
        JavaMailSenderImpl sender = new JavaMailSenderImpl();
        sender.setHost(host);
        sender.setPort(port);
        sender.setUsername(user);
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

At this point services must select the right bean:

~~~java
package com.example.mail;

import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.mail.javamail.JavaMailSender;
import org.springframework.stereotype.Service;

@Service
public class TransactionalEmailService {

    private final JavaMailSender mailSender;

    public TransactionalEmailService(
            @Qualifier("transactionalMailSender")
            JavaMailSender mailSender) {
        this.mailSender = mailSender;
    }

    // Build MimeMessage and send through the explicitly designated sender.
}
~~~

If you inject `JavaMailSender` without distinguishing by name, in a context with multiple beans of the same type Spring may report an **ambiguous single bean error** (`NoUniqueBeanDefinitionException`) if there is no other selection mechanism. `@Qualifier` makes code express its intent clearly. `@Primary` can designate a preferred bean, yet you should avoid using it to mask important differences between two sending paths.

**Points to distinguish:**

- `spring.mail.*` is the auto-configuration namespace for the default sender; the two groups `app.mail.transactional.*` and `app.mail.support.*` are **application-defined properties** read directly by the code above.
- When the application defines its own `MailSender`/`JavaMailSender` bean, Spring Boot mail auto-configuration may back off per its conditions; do not assume Boot keeps creating a third sender.
- `@Qualifier` selects the sender by business purpose; profiles can still swap **host, port, and credentials** of both senders in each environment.
- One broken provider does not make Spring automatically switch to another sender. Failover, retry, and idempotency must be designed if the business needs them.

The pattern above illustrates creating two fixed senders. Projects with multiple accounts should usually group configuration under `@ConfigurationProperties` and validate inputs at startup, rather than duplicating individual parameters and setters across multiple beans.

## 8. Credentials, TLS, and profile-specific policies

### 8.1. Profiles do not replace a secret store

`application-prod.yml` can reference environment variables, yet should not hold real SMTP passwords in Git. A common deployment practice is supplying `SMTP_USERNAME`/`SMTP_PASSWORD` at runtime from a secret manager, orchestration platform, or the organization's secret-management mechanism.

For staging and production:

- Use an account authorized for the sending domain; do not let public forms arbitrarily set `From`.
- Separate credentials across environments to reduce blast radius during an incident.
- Use TLS per provider requirements and verify the server appropriately.
- Specify permitted recipients in test environments; avoid sending test mail to real customers.
- Limit sending frequency and retries; monitor authentication and delivery errors.
- Rotate credentials without modifying source code or committing new values.

Merely seeing `prod` in `SPRING_PROFILES_ACTIVE` is not proof that a request has permission to send real email. Sending permission must be granted and enforced by the system at the application/provider layer.

### 8.2. Avoid "fixing" TLS by skipping certificate checks

Examples of SMTP yet two commonly seen mechanisms:

| Commonly used port | Mechanism | Related properties |
| --- | --- | --- |
| `587` | Submission, connects and upgrades with STARTTLS | `mail.smtp.starttls.enable=true`, optionally `required=true` |
| `465` | TLS right from connection start (*implicit TLS*) | `mail.smtp.ssl.enable=true` |
| `1025` on local sink | Isolated test SMTP, possibly no auth/TLS | Depends on SMTP sink; never treat as Internet default |

When hitting `SSLHandshakeException`, check port configuration, TLS mode, trust store, and hostname verification. Do not switch automatically to plaintext or enable "trust all certificates" just to send successfully.

### 8.3. JNDI Session and spring.mail.*

Besides host/port/user/password, Spring Boot can also configure a Jakarta Mail `Session` via `spring.mail.jndi-name` in environments supporting JNDI. If a JNDI session is configured, direct mail sender properties may be handled differently or overridden in priority by the JNDI session depending on auto-configuration mechanics.

Therefore, when host/port appear unchanged despite editing `application-prod.yml`, check whether the sender is obtaining `Session` from JNDI. Do not configure multiple session sources simultaneously with ambiguous intent.

## 9. Verifying configuration before sending real mail

There are three levels to distinguish:

| Level | Method | What is proven |
| --- | --- | --- |
| **Spring context configuration** | Check active profiles, `JavaMailSender` bean, property values with secrets masked | Context has the bean and effective parameters as expected |
| **SMTP connectivity** | Test connection in an allowed environment, or use `spring.mail.test-connection` in a controlled way | Endpoint and connection/auth session respond at check time |
| **End-to-end email sending** | Send to an SMTP sink or test account, inspect the actually received message | Creation, transport, and test reception work under those conditions |

Spring Boot has the `spring.mail.test-connection` property. When enabled in suitable configurations, Boot can attempt connecting to the mail server during initialization and fail startup if the connection check does not succeed.

Example in staging:

~~~yaml
# application-staging.yml
spring:
  mail:
    test-connection: true
~~~

This is an **addition** to the earlier staging configuration. Consider operational policy: an external email system temporarily unavailable can prevent the application from starting. This property **does not send an email to a recipient to prove delivery**, nor does a successful connection guarantee every subsequent send will succeed.

For logic tests, the suitable approach is usually not opening network connections. Check `MimeMessage` creation and `JavaMailSender` calls on a fake/mock. For integration tests, use an SMTP sink to read actual messages and verify recipient addresses, text/HTML, inline images, and attachments.

### 9.1. Checking active profiles in code

When needing to inspect context, you can use `Environment`:

~~~java
import java.util.Arrays;
import org.springframework.core.env.Environment;

String active = Arrays.toString(environment.getActiveProfiles());
boolean production = environment.acceptsProfiles(
        org.springframework.core.env.Profiles.of("prod"));
~~~

`acceptsProfiles(...)` expresses profile conditions more clearly than merely taking `getActiveProfiles()[0]`. However, an application should not decide its entire SMTP configuration via `if (production)` checks scattered across business code. Use profile conditions when truly needed to choose behavior; host/TLS configuration should stay centralized in config.

## 10. Common misconfiguration scenarios

### 10.1. No qualifying bean of type JavaMailSender

Example:

~~~text
No qualifying bean of type 'JavaMailSender' available
~~~

Causes can include missing Jakarta Mail/Spring Mail dependencies, unmet auto-configuration conditions, missing `spring.mail.host` or JNDI session, or a custom bean disabled due to a mismatched profile.

How to resolve:

1. Check the classpath and mail starter.
2. Confirm the active profile.
3. Confirm required properties/bean conditions.
4. If tests intentionally use a fake, ensure the fake bean is imported/registered in the right context.

Merely naming a file `application-prod.yml` does not guarantee `JavaMailSender` appears in every profile.

### 10.2. Multiple JavaMailSenders and ambiguous injection

Symptom:

~~~text
NoUniqueBeanDefinitionException:
expected single matching bean but found 2
~~~

If the application creates its own senders for marketing and transactional, inject with `@Qualifier` or an explicit selection mechanism. Use `@Primary` when there really is a suitable default, rather than letting services arbitrarily receive a sending account meant for another purpose.

### 10.3. Local mistakenly sends to production provider

Common possibilities:

- The runner set `SPRING_PROFILES_ACTIVE=prod` without realizing it.
- The `SPRING_MAIL_HOST` environment variable overrides the value in `application-local.yml`.
- Multiple active profiles cause an unintended configuration to take precedence.
- A self-created bean holds production credentials instead of using the `spring.mail.*` the team is inspecting.

Observe the **effective configuration values and configuration sources**, rather than just opening `application-local.yml` and concluding an SMTP sink is in use.

### 10.4. Staging hits AuthenticationFailedException

Possible causes include an account lacking SMTP permissions, secret not injected, username/password from the wrong environment, AUTH method not accepted by the provider, or TLS policy.

Inspect `MailAuthenticationException` and its inner cause. Do not log passwords/tokens or switch to unauthenticated mode just to bypass the error. Also do not assume an auth error is always from typing the wrong password.

### 10.5. Production hits TLS handshake error

For example, the SMTP server requires implicit TLS on `465` while the application uses STARTTLS configuration on a plaintext connection. Or the trust store does not accept the server certificate.

Distinguish port/protocol and read causes such as `SSLHandshakeException`. Do not resolve by dropping `mail.smtp.starttls.required` or disabling hostname verification before identifying the cause.

### 10.6. One profile works while another hits SMTP timeout

Check first:

- Endpoint/port corresponding to the profile.
- Firewall, outbound network policy, and DNS from **the environment where the application actually runs**.
- If running in a container, does hostname `localhost` point to the right SMTP service?
- Are default timeouts or `spring.mail.properties.mail.smtp.*timeout` values being overridden?

One environment may reach SMTP while another is blocked by network policy; do not rewrite all `JavaMailSender` code if the issue lies in the network path.

### 10.7. Profile-specific property has no effect

Check:

- Does the file name match the active profile, e.g. `application-prod.yml` with `prod`?
- Are there YAML indentation errors or typos in property names?
- Are command-line arguments or environment variables overriding it?
- Are there multiple config/import files with different precedence?
- Is the real sender created from `spring.mail.*` or from a custom `app.mail.*` namespace?
- Was the bean already created/supplied a `Session` through another source?

When editing a property, do not conclude its effect merely by grepping source. Check the configuration **resolved by the Spring context** and the bean's actual behavior.

## 11. Designing per-environment mail sending without changing service code

Consider an account verification email-sending system:

~~~text
RegistrationService
    |
    v
VerificationMailer (inject JavaMailSender)
    |
    +-- profile=local   -> SMTP sink 127.0.0.1:1025
    |
    +-- profile=test    -> mock/fake or test SMTP sink
    |
    +-- profile=staging -> test SMTP account (STARTTLS)
    |
    +-- profile=prod    -> official SMTP account (STARTTLS or implicit TLS)
~~~

The service can keep its logic:

~~~java
public void sendVerification(String recipient, String verificationUrl)
        throws jakarta.mail.MessagingException {

    var message = mailSender.createMimeMessage();
    var helper = new org.springframework.mail.javamail.MimeMessageHelper(
            message, false, "UTF-8");

    helper.setFrom("no-reply@example.com");
    helper.setTo(recipient);
    helper.setSubject("Verify your account");
    helper.setText("Please open the link: " + verificationUrl, false);

    mailSender.send(message);
}
~~~

In the example, `no-reply@example.com` and `verificationUrl` are illustrative values. The real sender address must belong to a permitted domain and should be configured centrally per environment; verification links need to be generated securely in the business layer. `VerificationMailer` itself does not need an `if/else` block for each profile because Spring's configuration mechanism selects the sender.

If an environment requires a different `From` address, also inject an application property such as `app.mail.from-address` from the corresponding profile configuration. Changing the sender address via configuration as well helps avoid hardcoding dummy values into production.

Example:

~~~yaml
# application-local.yml
app:
  mail:
    from-address: dev-notifications@example.test

# application-prod.yml (in a separate actual file)
app:
  mail:
    from-address: ${MAIL_FROM_ADDRESS}
~~~

Trong code:
In code:
~~~java
public VerificationMailer(
        JavaMailSender mailSender,
        @org.springframework.beans.factory.annotation.Value(
                "${app.mail.from-address}")
        String fromAddress) {
    this.mailSender = mailSender;
    this.fromAddress = fromAddress;
}
~~~

The example only illustrates configuration injection; the class needs the corresponding `mailSender` and `fromAddress` fields. If there are multiple sending addresses, display names, or policies per email type, create a clear mail configuration structure rather than duplicating literals across multiple services.

## 12. Principles to apply in real systems

| Design decision | Reason |
| --- | --- |
| Place shared timeouts and encoding in `application.yml` | Reduces duplication and ensures consistent behavior |
| Place SMTP endpoints in `application-{profile}.yml` or external property sources | Each environment uses an appropriate sending path |
| Do not commit real credentials | Reduces risk of exposing mail-sending accounts |
| Use sink or fake for local/test | Enables testing content without accidentally emailing customers |
| Staging/prod require TLS matching the provider | Protects sending connections and verifies the server |
| Services inject `JavaMailSender` | Keeps business logic independent of SMTP host/profile |
| Use `@Qualifier` when there are multiple senders at once | Selects the right account/provider per business purpose |
| Distinguish submission from delivery | Completing `send(...)` does not guarantee email landed in Inbox or was read |
| Retry according to real status and limits | Avoids duplicate sending or infinite loops on timeouts |
| Check effective configuration when diagnosing | Detects overrides by environment/CLI/imports |

Spring profiles solve the problem of **running the same application across multiple environments** well. `JavaMailSender` serves as the shared abstraction, while `spring.mail.*`, placeholders, and profile-specific configuration files determine the appropriate SMTP endpoint, authentication, and TLS. When multiple senders are needed at the same time, create and inject explicitly named beans; when testing, use a fake or controlled SMTP sink. This separation allows changing configuration across local, test, staging, and production without altering the `MimeMessage` creation workflow in business services.
