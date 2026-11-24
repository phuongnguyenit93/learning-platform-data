# Externalizing Configuration from Source Code and Managing Secrets

In an email-sending module using **Spring Framework Mail**, application code needs to know *when to send an email, to whom, and with what content*. Information such as **SMTP host, port, account name, password, TLS policy, and default sender address** belongs to operational configuration. They vary by environment and email provider, so they must never be hardcoded inside service classes.

Some configuration values must be protected as **secrets** (such as SMTP passwords, API tokens, OAuth client secrets); other values are not necessarily secret yet still belong outside source code (host, port, timeouts, `From` email, TLS mode). Separating them properly lets the exact same build run in local, test, staging, and production without editing Java code or recommitting the project whenever switching providers.

Example of what **not to do**:

~~~java
JavaMailSenderImpl sender = new JavaMailSenderImpl();
sender.setHost("smtp.production.example");
sender.setPort(587);
sender.setUsername("notification@company.example");
sender.setPassword("real-password-in-source"); // Never store secrets in code.
~~~

If source code is stored in Git, pushed to CI, sent for review, or packaged into a JAR, the password can spread across many copies that developers can barely track. Even if you delete that line later, the old value can linger in commit history, logs, or build artifacts.

The right approach is for **code to depend only on an already-configured mail sender**, while the deployment environment supplies configuration values and secrets at runtime.

## 1. Distinguishing regular configuration from secrets

| Information | Externalize from code? | Is it a secret? | Example |
| --- | --- | --- | --- |
| SMTP host | Yes | Usually no | `smtp.provider.example` |
| SMTP port | Yes | No | `587` or `465` |
| Enable SMTP AUTH | Yes | No | `true` |
| STARTTLS/SSL mode | Yes | No | Enable STARTTLS on appropriate port |
| Connect/read/write timeouts | Yes | No | `5000` ms |
| SMTP username | Yes | Can be sensitive, depending on org | Mail-sending account |
| SMTP password / application password | Yes | **Yes** | Provider-issued password |
| SMTP API token / OAuth client secret | Yes | **Yes** | Token or client secret |
| OAuth refresh token | Yes | **Yes** | Token capable of minting new access tokens |
| `From` and `Reply-To` addresses | Yes | Usually no | `no-reply@company.example` |
| Messages-per-minute limit | Yes | No | Provider rate limit |

Externalizing configuration does not mean **every single value must live in a secret manager**. Host, port, and timeouts can reside in version-controlled config files, while passwords are supplied solely by the runtime environment or secret store.

Values like username may not be strict secrets, yet limiting where they are stored and displayed is still useful. Account names, sender addresses, and system IDs should not be logged indiscriminately if they expose infrastructure details.

## 2. Configuration flow of a Spring Mail module

~~~mermaid
flowchart TD
    A["Java service: requests email send"] --> B["JavaMailSender (injected by Spring)"]
    C["application.yml: host, port, TLS, timeouts"] --> D["Spring Environment / Configuration Binding"]
    E["Environment variables / secret store"] --> D
    D --> F["Mail sender configuration"]
    F --> B
    B --> G["SMTP server"]
~~~

In Spring Boot, the `spring-boot-starter-mail` dependency brings the required mail components into the application. Boot can auto-configure `JavaMailSender` from `spring.mail.*` when auto-configuration conditions are satisfied. Application services simply inject `JavaMailSender` without needing to know where the password came from.

With **plain Spring Framework**, the same principle applies: declare the `JavaMailSenderImpl` bean yourself and bind values from an external configuration source. The core rule is **never place secrets in Java source**, regardless of whether you use auto-configuration or manual configuration.

## 3. Configuring the sender in Spring Boot

### 3.1. Dependency

With Gradle:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-mail'
}
~~~

If the application needs to validate custom configuration classes with Bean Validation, add the appropriate validation dependency. The sender example below does not require creating a custom configuration class.

### 3.2. `application.yml` referencing variable names instead of passwords

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
    from: ${MAIL_FROM:no-reply@company.example}
    reply-to: ${MAIL_REPLY_TO:support@company.example}
~~~

The `${...}` expressions are **Spring property placeholders**. The colon in `${SMTP_PORT:587}` specifies a default of `587` when no other value is set. Notably, `${SMTP_PASSWORD}` **has no default value**: the runtime environment must supply it, preventing accidental use of a dummy or shared password.

Here:

- `spring.mail.host`, `port`, `username`, `password`: configure the sender.
- `mail.smtp.*` keys inside `spring.mail.properties` are SMTP transport properties; the `"[mail.smtp.auth]"` syntax preserves dotted property names.
- `spring.mail.default-encoding` helps compose emails with Vietnamese/Unicode content in the right charset.
- `app.mail.from` and `app.mail.reply-to` are **application-defined properties**. Spring Boot does not automatically attach these headers to every email; application services must read and apply them.

The example enables **STARTTLS** on the commonly used port `587`. TLS configuration must follow provider requirements. For SMTP over immediate TLS (SMTPS, commonly port `465`), you may need `mail.smtp.ssl.enable` instead of STARTTLS; do not assume both configurations are equivalent.

The three timeouts `mail.smtp.connectiontimeout`, `mail.smtp.timeout`, and `mail.smtp.writetimeout` bound waiting times during connection, read, and write phases. Choose values matching system requirements; never leave infinite waits when HTTP/worker threads have finite resources.

### 3.3. How are environment variables supplied?

Variables such as the following can be injected into the process at startup by the OS, container runtime, CI/CD, or deployment platform:

~~~text
SMTP_HOST=smtp.provider.example
SMTP_PORT=587
SMTP_USERNAME=<smtp-account>
SMTP_PASSWORD=<value-supplied-by-secret-store>
MAIL_FROM=no-reply@company.example
MAIL_REPLY_TO=support@company.example
~~~

This is **a variable and placeholder schema**, not a file holding real credentials. The actual value of `SMTP_PASSWORD` must be supplied by the runtime environment's secret mechanism. Never commit files containing real values to Git.

Spring Boot also supports **relaxed binding** to map environment variables like `SPRING_MAIL_HOST`, `SPRING_MAIL_USERNAME`, and `SPRING_MAIL_PASSWORD` onto `spring.mail.host`, `spring.mail.username`, and `spring.mail.password`. When using that style, you may not need `${SMTP_...}` placeholders for every property. Pick one consistent convention so environment variables and config files do not override each other unexpectedly.

Example running locally with PowerShell, setting only *non-sensitive* values:

~~~powershell
$env:SMTP_HOST = "localhost"
$env:SMTP_PORT = "1025"
$env:MAIL_FROM = "test@example.invalid"
~~~

When working with production SMTP, never type literal passwords in PowerShell history, shell scripts, CI commands, or screenshots. Let a secret manager or deployment platform inject values into the environment. Environment variables keep secrets out of source code, yet they are not an absolute security boundary: they can still leak via process inspection, crash dumps, debug logs, or privileged host tools.

### 3.4. Application services do not need to know the password

~~~java
package com.example.mail.application;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.mail.SimpleMailMessage;
import org.springframework.mail.javamail.JavaMailSender;
import org.springframework.stereotype.Service;

@Service
public class NotificationMailService {
    private final JavaMailSender sender;
    private final String fromAddress;
    private final String replyToAddress;

    public NotificationMailService(
            JavaMailSender sender,
            @Value("${app.mail.from}") String fromAddress,
            @Value("${app.mail.reply-to}") String replyToAddress) {
        this.sender = sender;
        this.fromAddress = fromAddress;
        this.replyToAddress = replyToAddress;
    }

    public void sendText(String recipient, String subject, String text) {
        SimpleMailMessage message = new SimpleMailMessage();
        message.setFrom(fromAddress);
        message.setReplyTo(replyToAddress);
        message.setTo(recipient);
        message.setSubject(subject);
        message.setText(text);
        sender.send(message);
    }
}
~~~

The service only holds `From` and `Reply-To` addresses to build the message; **it holds no password, opens no SMTP connections itself, and decides no TLS mechanics**. Changing SMTP providers can be just a configuration change, provided the new provider still supports SMTP and compatible authentication requirements.

In real products, recipient addresses must be controlled by business logic; never turn an email-sending method into an open endpoint allowing anyone to supply arbitrary addresses and content.

## 4. Separating configuration by environment

Suppose the same module runs in **local**, **test**, **staging**, and **production**:

| Environment | SMTP source | Secret | Goal |
| --- | --- | --- | --- |
| Local | Test SMTP server like Mailpit/GreenMail | Usually no credentials when test server is configured without AUTH | Inspect test emails without sending to the Internet |
| Unit test | Mock/fake `JavaMailSender` | No real secret needed | Verify message content and send calls |
| Staging | SMTP sandbox/provider with restricted recipients | Staging-only secret | Integration testing without emailing real customers |
| Production | Real SMTP provider | Production-only secret | Send real transactional mail with logging/monitoring and limits |

**Never share the same credentials between staging and production.** If a staging account is compromised, blast radius must stay isolated. Also prevent local developers from accidentally hitting production SMTP just because production environment variables happen to be set on their machine.

### 4.1. Local profile using a mock SMTP server

An example `application-local.yml` that can safely be committed to Git because it contains no secrets:

~~~yaml
spring:
  mail:
    host: localhost
    port: 1025
    username:
    password:
    properties:
      "[mail.smtp.auth]": false
      "[mail.smtp.starttls.enable]": false
      "[mail.smtp.starttls.required]": false

app:
  mail:
    from: dev@example.invalid
    reply-to: dev-support@example.invalid
~~~

The test server must be configured to match: e.g., an SMTP listener on `localhost:1025` requiring no AUTH/TLS. This configuration is **strictly for controlled development environments**; never carry unencrypted connection modes into production.

When the `local` profile is activated, Spring Boot loads matching values according to its configuration merging rules. You can run with:

~~~text
--spring.profiles.active=local
~~~

or have the deployment environment set `SPRING_PROFILES_ACTIVE=local`.

**Profiles are not a secret vault.** Never commit an `application-prod.yml` containing real passwords just because the filename says "prod." Commit non-sensitive configuration in profiles; keep secret values in a secret store or runtime environment.

### 4.2. Understanding precedence to avoid unintended configuration

Spring Boot has multiple configuration sources: config files, profile-specific configs, environment variables, system properties, command-line arguments, and imported configs. Depending on source type, values override one another.

For example, if `application.yml` sets `spring.mail.host` to `smtp-staging.example` while runtime provides `SPRING_MAIL_HOST=smtp-prod.example`, the effective host may become production SMTP even when running under the staging profile.

Therefore, when configuration looks wrong:

1. Determine the **effective value** and **configuration source** in the runtime environment.
2. Check environment variables, command-line arguments, and active config imports.
3. Never log the entire Spring `Environment` or config endpoints if they might contain secrets.
4. Restrict permissions to modify runtime config and tightly control deployment pipelines.

Management endpoints such as Spring Boot Actuator `/env` or `/configprops` can help inspect property sources when secured properly, yet they must be access-controlled and sanitize sensitive values. Never expose those endpoints publicly just to debug SMTP.

## 5. Managing secrets across their lifecycle

Extracting passwords from code is step one; **secret management** also covers provisioning, distribution, access control, scheduled or emergency rotation, and revocation.

~~~mermaid
flowchart LR
    A["SMTP provider issues credentials"] --> B["Secret manager / vault"]
    B -->|"Least-privilege access"| C["Application runtime"]
    C --> D["JavaMailSender"]
    D --> E["SMTP provider"]
    B --> F["Audit / rotation / revoke"]
~~~

### 5.1. Where to store secrets

Common options:

- **Dedicated secret manager:** e.g., AWS Secrets Manager, Azure Key Vault, Google Cloud Secret Manager, or HashiCorp Vault. Usually provides access control, auditing, and secret versioning.
- **Deployment platform secrets:** e.g., secrets/credentials in container orchestrators, hosting platforms, or CI/CD. Verify encryption-at-rest and read permissions.
- **Local environment:** an OS keychain/secret store, dev tool, or **uncommitted** local config file with restrictive permissions.

Not every secret store automatically pushes updated credentials into a running app when rotated. How the runtime receives values (environment variable, file mount, secret API, sidecar/agent) must be explicitly designed.

### 5.2. Least privilege

An application account should only have permission to **read the exact secrets it needs**. Developer, CI, and production accounts should have separate access identities. If the SMTP provider supports it, credentials should only be authorized to **send mail** for approved domains or addresses rather than holding full email-account admin rights.

Useful principles:

- Separate secrets by **application**, **environment**, and **usage permission**.
- Never use personal passwords for a mail sender when the provider offers dedicated app/service credentials.
- Never paste secrets into issues, pull requests, screenshots, guides, or team chats.
- Audit who can view, edit, and revoke secrets; enable access logging where auditing is available.

### 5.3. Secrets in environment variables: convenient yet limited

Environment variables are convenient for containers and CI because Spring reads them without custom APIs. However, secrets can leak via:

- process or container inspection tools run by privileged users;
- memory dumps, crash dumps, or debug error reports;
- pipelines printing all environment variables;
- monitoring agents capturing excessive command-line or environment data;
- staff with permission to inspect runtime/container configs.

Therefore, never consider security "done" merely by moving a password to an environment variable. Access controls, log redaction, and rotation workflows are still essential.

## 6. Reading secrets from mounted files via Config Trees

Instead of putting passwords in environment variables, some platforms supply secrets as **files** mounted into containers. Spring Boot provides **Config Trees** to read files named after properties.

Suppose the environment mounts:

~~~text
/run/secrets/
  spring.mail.password
~~~

The contents of `spring.mail.password` are the real SMTP password distributed by the secret store. This file is **not in Git** and is mounted only at runtime with proper read permissions.

In a deployment configuration using secret files:

~~~yaml
spring:
  config:
    import: "configtree:/run/secrets/"
  mail:
    host: ${SMTP_HOST}
    port: ${SMTP_PORT:587}
    username: ${SMTP_USERNAME}
    protocol: smtp
    properties:
      "[mail.smtp.auth]": true
      "[mail.smtp.starttls.enable]": true
      "[mail.smtp.starttls.required]": true
~~~

In this variant, **do not also declare `spring.mail.password: ${SMTP_PASSWORD}`** in the same file: the secret comes from the config tree under property name `spring.mail.password`. Configure precedence and volume mounts per platform; pick one clear primary source per secret to avoid confusion.

Adding the `optional:` prefix to the import location allows starting up if the directory is missing. For production, it is usually better to **fail fast** when a required secret source is missing rather than booting with broken mail connectivity; verify fail-fast behavior against configuration semantics and application requirements.

When the file changes, an existing `JavaMailSender` **does not automatically re-read credentials**. Check your environment's config refresh capabilities or use a safe restart/rolling-restart procedure.

### 6.1. Kubernetes Secrets and security caveats

Kubernetes has a `Secret` object that can be projected into Pods as environment variables or volumes. However, Base64 encoding in manifests **does not mean secure encryption**. When using Kubernetes, configure RBAC, protect control-plane storage, enable encryption at rest where supported by the cluster, and restrict who can read Secrets or debug Pods.

Never commit manifests holding real secret values even if Base64-encoded. For GitOps workflows, use secret-store references or organization-approved encryption solutions with explicit access control and decryption workflows.

### 6.2. Docker Compose secrets and file mounts

A container setup can mount secrets at `/run/secrets/...` for Spring Boot to read as shown above. If mounting a host secret file in development, keep the source file outside Git and manage permissions. Never put literal passwords directly into `environment:` inside a shared Compose file.

In all cases, secrets passed to a process still require host/container protection; mounting a file does not automatically stop another process running under the same privileges from reading it.

## 7. Without Spring Boot: configuring `JavaMailSenderImpl`

Plain Spring Framework applications can declare the bean explicitly. The example below reads from Spring's `Environment` rather than embedding passwords directly in the class:

~~~java
package com.example.mail.config;

import java.util.Properties;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.env.Environment;
import org.springframework.mail.javamail.JavaMailSender;
import org.springframework.mail.javamail.JavaMailSenderImpl;

@Configuration
public class SmtpConfiguration {

    @Bean
    public JavaMailSender javaMailSender(Environment env) {
        JavaMailSenderImpl sender = new JavaMailSenderImpl();
        sender.setHost(env.getRequiredProperty("mail.smtp.host"));
        sender.setPort(
                env.getRequiredProperty("mail.smtp.port", Integer.class));
        sender.setUsername(env.getRequiredProperty("mail.smtp.username"));
        sender.setPassword(env.getRequiredProperty("mail.smtp.password"));
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
~~~

This example requires `mail.smtp.host`, `mail.smtp.port`, `mail.smtp.username`, and `mail.smtp.password` to be present in `Environment` before bean creation. When a required property is missing, `getRequiredProperty` catches the misconfiguration.

**If the application already uses Spring Boot mail auto-configuration**, you usually do not need this extra bean. Declaring a sender bean yourself can keep Boot from creating the default bean as expected. Only use manual configuration when you genuinely need control over instantiation.

## 8. Do not confuse protecting secrets with protecting the SMTP connection

Even when passwords live in a secret manager, sending credentials over an improperly encrypted connection still exposes them in transit.

With SMTP over port `587`, the flow typically uses `EHLO`, `STARTTLS`, and then SMTP AUTH over the TLS connection. You can enable:

~~~yaml
spring:
  mail:
    properties:
      "[mail.smtp.starttls.enable]": true
      "[mail.smtp.starttls.required]": true
~~~

Meaning: permit STARTTLS and require the upgrade to succeed before continuing under this config. If the SMTP server does not support STARTTLS, the connection must fail per security policy rather than silently continuing unencrypted.

With implicit TLS on port `465`, configurations per provider guidance usually set:

~~~yaml
spring:
  mail:
    port: 465
    properties:
      "[mail.smtp.ssl.enable]": true
~~~

Never set `mail.smtp.ssl.trust=*` to "quick-fix" certificate errors or disable TLS identity verification in production. When certificate errors arise, fix truststore configuration, hostname, or server certificates.

Different layers protect different things:

| Layer | What does it protect? |
| --- | --- |
| Secret store and access control | Protects credentials at rest, management, and distribution |
| TLS between app and SMTP provider | Protects data and credentials over that connection hop |
| SPF, DKIM, DMARC | Helps verify/evaluate sender legitimacy and prevent domain spoofing |
| Securing logs, metrics, tracing | Prevents the app from accidentally disclosing sensitive data |

TLS on one SMTP hop does not mean email is end-to-end encrypted; email can traverse multiple servers and rest in different mailboxes. If business logic demands content confidentiality, evaluate dedicated content-encryption solutions.

## 9. Rotating and revoking SMTP credentials

A password or token may need rotation due to periodic policy, suspected compromise, provider changes, or permission narrowing.

### 9.1. Controlled secret rotation procedure

1. **Issue new credentials** from the provider with appropriate sending scope. If the provider allows overlapping old and new credentials, use a transition window to avoid service interruption.
2. **Store the new version in the secret store** without pasting the value into code, tickets, or deployment logs.
3. **Roll out to the application** by updating runtime secret injection and restarting/refreshing the sender per designed process.
4. **Verify mail submission** using an authorized test address, monitoring authentication, connection, and send-queue errors.
5. **Revoke old credentials** after confirming all instances have switched to the new credential.
6. **Record rotation time and scope** for auditing and recovery if needed.

If the provider only supports one active credential at a time, plan the cutover for minimal downtime with an appropriate rollback plan.

### 9.2. Do updated secrets take effect automatically?

**Do not assume hot reload.** In a typical Spring Boot application, `JavaMailSenderImpl` is configured at bean creation time. If the password changes in the secret manager while the process keeps running, the sender may keep holding the old value.

Common approaches are **rolling restarts** of instances to load new credentials, or a configuration/credential provider component with an explicit refresh mechanism. If mail sends go through a queue, coordinate retry state during the transition so send requests are not lost.

### 9.3. If a secret was accidentally committed

Prioritize response steps:

1. **Treat the credential as compromised** and revoke/rotate it immediately via the provider or secret store.
2. Assess impact: which accounts or services may have used the secret, and are there signs of unauthorized mail sending?
3. Remove the value from tracked source files and replace it with a config reference.
4. Evaluate secret exposure in Git history, PRs, CI artifacts, logs, and repository clones; handle history/copies per team policy.
5. Add secret scanning, review policies, and secret provisioning controls to prevent recurrence.

**Simply deleting the password line and making another commit is not enough**, because older commits still persist. `.gitignore` also does not untrack files already tracked by Git.

## 10. Preventing secret leaks via logs and operational tools

Never expose secrets by doing:

~~~java
// Avoid this:
log.info("SMTP configuration password={}", smtpPassword);
log.debug("All configuration: {}", environment);
~~~

Watch for other leak vectors:

- Enabling mail protocol debug (`mail.debug` / `mail.smtp.debug` depending on library context) can emit traces with session details. Enable only temporarily in safe environments, mask/redact, and disable once diagnosis completes.
- Exception logs can include hosts, email addresses, SMTP replies, and internal details. Never paste raw logs into public channels.
- Admin endpoints, heap dumps, profilers, APM, and tracing can capture config data or payloads. Restrict access and retention.
- CI/CD can accidentally print environment variables when running shells with verbose/xtrace or echoing parameters.
- Documentation should use placeholders like `<smtp-password>`, never active credentials "for convenience."

Operational fields safe to log:

~~~text
mail.provider=primary
mail.smtp.host=smtp.provider.example
mail.smtp.port=587
mail.tls.mode=STARTTLS_REQUIRED
mail.send.result=AUTH_FAILURE
mail.job.id=job-742
~~~

These fields illustrate operational observability; avoid logging `spring.mail.password`, access tokens, or full email contents.

### 10.1. Keeping secrets out of the source package

Places where secrets easily leak by mistake:

~~~text
src/main/resources/application.yml           # Must not contain real secrets.
src/main/resources/application-prod.yml      # Must not contain real secrets.
.env                                         # Usable locally, never commit.
docker-compose.yml                           # Must not contain literal passwords.
Dockerfile                                   # Never use ENV/ARG for build secrets.
README.md / wiki / issue                     # Placeholders only.
test/resources/*.yml                         # Never copy production credentials.
~~~

If using a local `.env` file, keep it out of Git and ignored from the start. Some dev tools read `.env`, yet **Spring Boot by default does not treat arbitrary `.env` files in the project directory as config sources**. Be explicit about what loads environment variables before starting the app.

Beyond `.gitignore`, organizations can use pre-commit and remote repository secret scanning. Secret scanning is a detection control; it does not replace revoking exposed credentials.

## 11. Validating configuration at startup and send time

### 11.1. Validating configuration inputs

Questions to verify:

- Is the SMTP host provided and right for the environment?
- Is the port valid and aligned with the provider's TLS mode?
- When SMTP AUTH is required, are username and credential present?
- Does `From` belong to a domain authorized by the provider?
- Are timeouts aligned with request/worker limits?
- Are all instances using the current secret version after the latest rotation?

An application can apply Bean Validation to its own `@ConfigurationProperties` or run startup checks for required values. Still, **checking presence** does not prove the server accepts the credentials: true authentication is only confirmed when connecting to the SMTP provider.

### 11.2. What does `spring.mail.test-connection` mean?

Spring Boot provides the option:

~~~yaml
spring:
  mail:
    test-connection: true
~~~

When supported and enabled, the application attempts to connect to the mail server at startup to catch certain config/availability issues. This can cause startup to fail if the SMTP provider is temporarily unreachable. A passing connection check also **does not guarantee future emails will be accepted**, does not guarantee permission to send to all recipients, and does not verify delivery.

Consider it in environments where startup strictly depends on SMTP reachability; if the system uses a queue/outbox designed to tolerate provider outages, prefer health/metrics and retries rather than blocking every startup.

### 11.3. Local testing without production secrets

A unit test can mock `JavaMailSender` to verify the service sets the right address, subject, and text. For integration tests, use a local mock SMTP server like Mailpit or GreenMail. Never feed production credentials into test pipelines just to verify how `SimpleMailMessage` is built.

In staging with an SMTP sandbox, restrict allowed recipients to prevent automated tests from accidentally emailing real customers.

## 12. A practical design for multiple email types

Suppose an application sends two types of email:

- **Account notifications:** `From=no-reply@company.example`, `Reply-To=support@company.example`.
- **Invoices:** `From=billing@company.example`, `Reply-To=billing-help@company.example`.

Both can use **one `JavaMailSender`** if they share one SMTP provider and credential set. The application selects headers per notification type while the sender gets connection info from runtime config.

~~~text
AccountService / BillingService
             |
             v
NotificationMailService
  - choose From and Reply-To
  - build subject and body
             |
             v
JavaMailSender (Spring-managed bean)
  - SMTP host/port
  - TLS/AUTH/timeouts
  - runtime-supplied credentials
             |
             v
SMTP provider
~~~

If the two email types must use **two providers or two independent SMTP accounts**, you may need two named/qualified sender beans with separate configs, or a dedicated provider-routing adapter. Even then, never let business code read passwords or assemble connections directly; the mail infrastructure layer selects the transport while services hold notification semantics.

### 12.1. Conventions a team should agree on

| Decision | Implementation suggestion |
| --- | --- |
| What belongs in Git? | YAML templates and non-sensitive settings, no real secrets |
| Who supplies passwords? | Secret manager or deployment platform |
| How does the app read them? | Spring Environment / config binding / config tree via one consistent convention |
| Who can view production secrets? | Only authorized runtime identities and personnel |
| When credentials change? | Rotate + update runtime + restart/refresh + verify |
| When mail fails? | Log error codes/statuses safely, never passwords or tokens |
| When testing? | Mock sender or local SMTP server, never production credentials |

## 13. Common misconceptions

| Misconception | Correct understanding |
| --- | --- |
| "Keeping passwords in `application-prod.yml` is safe because only production reads it." | If the file sits in Git or accessible artifacts, the secret is still exposed. |
| "Environment variables are completely secret." | Environment variables avoid hardcoding, yet still require access, log, process-inspection, and runtime controls. |
| "Updating a secret on the server makes the running app use it immediately." | The sender may already be initialized with the old value; a refresh or restart mechanism is needed. |
| "`.gitignore` protects files already committed." | Git keeps tracking previously committed files; handle both the credential and relevant history. |
| "Base64 in a Kubernetes Secret means it is encrypted." | Base64 is only data encoding; security depends on RBAC and storage encryption. |
| "Enabling TLS is enough; no secret management needed." | TLS protects the connection; secrets still need secure storage and distribution. |
| "`From` is the SMTP username." | The two values can differ; the provider governs authorized sender addresses. |
| "`app.mail.from` applies automatically to every email." | That is an application-specific property; code must read and set the header. |
| "One test email succeeding means operations are done." | Still need monitoring for errors, bounces, quotas, rotation, and provider outages. |
| "To debug, just log the entire `Environment`." | Risks leaking credentials, endpoints, and many sensitive properties. |

## 14. End-to-end scenario: switching SMTP providers without editing code

Initially the application uses provider A. Java code already has:

~~~java
private final JavaMailSender sender;

// ... when business logic needs it:
sender.send(message);
~~~

When switching to provider B:

1. The new provider supplies `SMTP_HOST`, `SMTP_PORT`, SMTP account, and appropriate secrets.
2. Operations stores the new secret in production's secret vault and grants read permission to the runtime.
3. Deployment configuration switches to the new host/port; TLS/AUTH settings are adjusted per provider B's instructions.
4. The application rolls out/restarts so `JavaMailSender` picks up the new configuration.
5. Send a test email to an authorized destination, verify submission status, and monitor 4xx/5xx errors and bounces.
6. After confirming all instances run stably, revoke unused credentials from provider A.

Throughout the transition, services creating `SimpleMailMessage` or `MimeMessage` never need to know the SMTP password, never require a rebuild for hostname changes, and never alter business content logic.

That is the direct payoff of **externalizing sender configuration from source code**: the system adapts deployment conditions and credentials under strict control while code responsibilities stay clean. Combining Spring configuration binding, least-privilege secrets, TLS, rotation procedures, and monitoring makes email sending both easy to operate and resistant to credential leaks.

### References

- **Spring Boot Reference — Sending Email:** `spring-boot-starter-mail`, `spring.mail.*`, and `spring.mail.test-connection`.
- **Spring Boot Reference — Externalized Configuration:** property sources, profile-specific files, environment variables, and precedence.
- **Spring Boot Reference — Config Trees:** reading properties from mounted secret files.
- **Spring Framework Reference — Email:** `MailSender`, `JavaMailSender`, `JavaMailSenderImpl`, and `MimeMessageHelper`.
- **Jakarta Mail SMTP Provider Properties:** `mail.smtp.auth`, `mail.smtp.starttls.enable`, `mail.smtp.ssl.enable`, and timeouts.
