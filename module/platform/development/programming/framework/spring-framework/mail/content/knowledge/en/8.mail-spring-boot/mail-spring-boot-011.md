# Managing secrets with environment variables or a secret store

In **Spring Boot**, `JavaMailSender` configuration usually includes the SMTP host, port, username, and password. The host/port are only connection parameters; whereas the SMTP password, email provider API key, and authentication token are **secrets** because they grant permission to use an account or service. If exposed, these values can be abused to send unauthorized mail, exhaust quotas, harm domain reputation, and cause operational incidents.

Proper secret management covers the entire lifecycle: **provisioning → storage → distribution → usage → change/rotation → revocation**. Two familiar approaches with Spring Boot are **environment variables** and a **secret store**. They can be combined: the secret store manages values and permissions, while environment variables or mounted files help Spring Boot load the configuration.

This lesson guides you through configuring Spring Framework Mail under both approaches, explains how Spring Boot receives secrets, permissions, protecting logs, rotating credentials, and handling incidents.

## 1. Identifying secrets in a mail-sending system

| Value | Sensitivity level | Role |
|---|---|---|
| `spring.mail.host`, `spring.mail.port` | Usually not a secret | Network parameters for connecting to SMTP. |
| `spring.mail.username` | Potentially sensitive | Account identifier or SMTP information issued by the provider. |
| **`spring.mail.password`** | **Secret** | Password, app password, or token/API key used for SMTP AUTH. |
| HTTP email provider API key | **Secret** | Grants permission to call the email-sending API or other functions. |
| OAuth access/refresh token | **Secret** | Access right that may have an expiration and need refreshing. |
| DKIM private key, if self-signing email | **Secret** | Signing key must be managed as a private key; many providers sign on the application's behalf. |
| `From`, `Reply-To` | Usually not | Displayed sender identity and reply address. |
| `mail.smtp.starttls.required` | No | Connection-protection policy. |

The goal is to **separate credentials from source code**, control who can read and change credentials, and avoid leaks through logs, deployment processes, or diagnostic tools.

You should not treat all mail accounts as identical. Some providers require an **app password**, some issue an SMTP API key, and some support OAuth or another authentication mechanism. Choose the method actually supported by the mail-sending system.

## 2. How do secrets enter JavaMailSender?

```text
Admin / operations team / automation
                |
                v
      Secret manager or platform's
      controlled configuration
                |
       +--------+---------+
       |                  |
       v                  v
  Environment var    Mounted secret file
       |                  |
       v                  v
 Spring Environment  Spring Config Data
       |             (configtree:)
       +--------+---------+
                |
                v
         MailProperties
                |
                v
        JavaMailSenderImpl
                |
                v
         Jakarta Mail
                |
                | SMTP AUTH over TLS
                v
           SMTP relay
```

Different layers solve different tasks:

- **Secret store** is the source that manages secrets: policy, audit, versions, rotation, and distribution mechanism.
- **Environment variable** passes a value into a process. It does not encrypt by itself or grant fine-grained access control.
- **Spring Environment** merges property sources according to Spring Boot's precedence order.
- **`JavaMailSenderImpl`** is configured from properties and uses credentials during SMTP sending.
- **Jakarta Mail Transport** opens the connection, negotiates TLS, and authenticates per configuration.

A receipt-sending service should only know about `JavaMailSender`; it does not need to read the password with `System.getenv(...)` on every call.

## 3. Approach 1: environment variables and application.yml

Spring Boot supports **externalized configuration**: the same JAR can run in local, staging, and production with different secrets.

### 3.1. Configuring SMTP with placeholders

Using `spring-boot-starter-mail` in Gradle Groovy DSL:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-mail'
}
```

Example `application.yml` for SMTP submission on port 587 with STARTTLS:

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
          ssl:
            checkserveridentity: true
          connectiontimeout: 5000
          timeout: 5000
          writetimeout: 5000
```

At runtime, Spring Boot resolves `${SMTP_USERNAME}` and `${SMTP_PASSWORD}` from registered configuration sources, such as the process's environment variables. The YAML snippet has no real password, so it can be managed alongside source code.

| Property | Function |
|---|---|
| `mail.smtp.auth=true` | Uses the SMTP authentication mechanism per provider. |
| `mail.smtp.starttls.enable=true` | Allows upgrading the connection to TLS. |
| `mail.smtp.starttls.required=true` | Requires STARTTLS to succeed; avoids continuing in an unprotected mode when policy demands TLS. |
| `mail.smtp.ssl.checkserveridentity=true` | Checks the host identity against the TLS certificate in the provider. |
| `mail.smtp.connectiontimeout` | Maximum connection time, in milliseconds. |
| `mail.smtp.timeout` | Maximum time to wait to read socket responses. |
| `mail.smtp.writetimeout` | Maximum time to wait to write to the socket. |

You should not put a fallback password in configuration, such as `${SMTP_PASSWORD:changeme}`. When production is missing a required secret, the system should detect it and report an error instead of silently using a default credential or sending unauthenticated.

If the SMTP provider requires port 465 with **implicit TLS**, configure `mail.smtp.ssl.enable=true` and the corresponding port. Do not arbitrarily mix 465 and 587 settings.

### 3.2. Supplying environment variables

In a Bash shell in a development environment, you can use:

```bash
export SMTP_USERNAME="smtp-test-account@example.com"

# Read the password from the terminal without printing characters to the screen.
read -r -s -p "SMTP password: " SMTP_PASSWORD
printf '\n'
export SMTP_PASSWORD

java -jar app.jar
```

This is a local run example. In real deployment, the container platform, CI/CD, or orchestrator should supply values from a secret-management source, avoiding writing plaintext passwords into scripts or shell history.

Spring Boot can also receive properties directly via environment variables:

```text
SPRING_MAIL_HOST=smtp.example.com
SPRING_MAIL_PORT=587
SPRING_MAIL_USERNAME=<smtp-username>
SPRING_MAIL_PASSWORD=<smtp-password>
```

The **relaxed binding** rule allows `SPRING_MAIL_PASSWORD` to map to `spring.mail.password`. When using this approach you can omit the `username` and `password` fields from YAML.

**Choose one clear convention**: either use `SMTP_PASSWORD` through a placeholder or supply `SPRING_MAIL_PASSWORD` directly. If multiple sources exist at once for the same property, understand which source has higher precedence and avoid conflicting values.

### 3.3. JavaMailSender does not need to know how secrets are stored

```java
package com.example.mail;

import org.springframework.mail.SimpleMailMessage;
import org.springframework.mail.javamail.JavaMailSender;
import org.springframework.stereotype.Service;

@Service
public class ReceiptMailService {

    private final JavaMailSender mailSender;

    public ReceiptMailService(JavaMailSender mailSender) {
        this.mailSender = mailSender;
    }

    public void sendReceipt(String recipient, String orderCode) {
        SimpleMailMessage message = new SimpleMailMessage();
        message.setFrom("receipts@example.com");
        message.setTo(recipient);
        message.setSubject("Order confirmation " + orderCode);
        message.setText("Order " + orderCode + " has been recorded.");

        mailSender.send(message);
    }
}
```

Spring Boot configures the sender using the appropriate property sources; Jakarta Mail uses the credentials when connecting to SMTP. The business layer does not need to pass secrets through multiple services.

**Note:** `mailSender.send(...)` without an exception usually means the SMTP server accepted the send request at that hop, not proof that the email reached the Inbox.

### 3.4. Strengths and limits of environment variables

Environment variables are easy to apply, require no separate integration library, and are convenient when the deployment platform already supports secret injection. However:

- Env vars are **not a vault**. Processes, monitoring tools, or accounts with suitable permissions can read them.
- Secrets can leak through deploy logs, shell history, process/debug metadata, crash dumps, or admin tools.
- Env vars do not provide audit, versioning, or rotation by themselves.
- Changing an environment variable on the deployment system does not automatically update values already loaded into memory by a bean.
- SMTP sending still requires TLS, quotas, and permission management on the provider.

For many small applications, env vars are still a reasonable choice **if they are supplied from a secure source and have a rotation process**.

## 4. Approach 2: secret store

A **secret store** is a service that manages sensitive data. Common examples include HashiCorp Vault, AWS Secrets Manager, Google Cloud Secret Manager, Azure Key Vault, and deployment platform secret mechanisms.

| Capability | Meaning when sending email |
|---|---|
| IAM/policy | Only permitted mail-service or worker instances read SMTP credentials. |
| Versioning | Manages the current version and the new version during rotation. |
| Audit | Tracks access, changes, or permission grants. |
| Data encryption | Protects secrets at rest and in transit per provider policy/capability. |
| Workload identity | Uses the Pod/VM/service identity to read secrets instead of embedding another master password. |
| Rotation | Creates, distributes, and revokes credential versions in a controlled manner. |
| Environment separation | Staging has no permission to read production credentials. |

Three common integration styles:

1. **Secret store → env var:** the deployment platform fetches the secret and injects it into the process; Spring Boot uses it as in section 3.
2. **Secret store → mounted file:** a secret agent/orchestrator supplies files; Spring Boot loads them with `configtree:` or another integration.
3. **Spring Boot → secret store:** the application uses a Config Data integration, Spring Cloud Vault, or an SDK/provider-specific integration to read directly using service identity.

You do not have to use all three. What matters is identifying the **source of truth**, access permissions, how it is delivered to the application, and how loaded values are refreshed.

## 5. Mounted secrets with Spring Boot configtree

Spring Boot supports `spring.config.import` of the **`configtree:`** form. In a configuration directory of this kind, the file name corresponds to the property name and the file content corresponds to the value.

Suppose the container has two files:

```text
/run/secrets/
  spring.mail.username
  spring.mail.password
```

The `application.yml` file only needs to declare:

```yaml
spring:
  config:
    import: "configtree:/run/secrets/"
  mail:
    host: smtp.example.com
    port: 587
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

At startup, Spring loads `spring.mail.username` and `spring.mail.password` from the mounted files, then configures the sender. There are no real secrets in source or the JAR.

The two import forms have different effects:

- `configtree:/run/secrets/`: mandatory configuration source; if the directory does not exist, an error is reported during startup.
- `optional:configtree:/run/secrets/`: allows the directory to be absent; useful if local uses env while production uses mounted secrets. You must still verify required credentials in production.

Pay attention to file read permissions, whitespace/newlines in values, precedence order if an env var overrides the same key, and refreshing when the secret source changes. **An updated file does not mean a running `JavaMailSenderImpl` automatically picks up the new password.**

### 5.1. Kubernetes Secret volume example

With Kubernetes, a Secret can be mounted as files, via a `Deployment` section similar to:

```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: mail-service
spec:
  replicas: 2
  selector:
    matchLabels:
      app: mail-service
  template:
    metadata:
      labels:
        app: mail-service
    spec:
      containers:
        - name: app
          image: example/mail-service:1.0.0
          volumeMounts:
            - name: smtp-secrets
              mountPath: /run/secrets
              readOnly: true
      volumes:
        - name: smtp-secrets
          secret:
            secretName: mail-smtp-credentials
            items:
              - key: username
                path: spring.mail.username
              - key: password
                path: spring.mail.password
```

The example assumes `mail-smtp-credentials` already exists with keys `username` and `password`, created through a controlled secret-management process. Do not commit manifests containing real credentials.

**Base64 in the `data` field of a Kubernetes Secret is only a data representation, not security encryption.** You need to consider RBAC, API permissions, encryption at rest when supported/configured, Pod permissions, and volume mounts. Even when the platform can update volume contents, the application usually needs a rolling restart or a reload mechanism for the sender to use the new value.

### 5.2. When is a mounted file more suitable than an env var?

- The platform already has a secret volume, CSI driver, or secret agent.
- You want to restrict access by user/container and file.
- You do not want credentials appearing in the process's environment.
- You want a unified Spring Boot configuration mechanism across multiple runtimes.

Mounted files must also be protected: a process with read permission can still access them, and anyone with access to the container/volume can view them.

## 6. Reading a secret store directly via integration

Some projects use **Spring Cloud Vault**, a cloud provider's Config Data integration, or an SDK to read secrets directly. Illustrative flow:

```text
Spring Boot workload
       |
       | Workload identity
       v
Secret store authentication
       |
       | Policy allows reading the exact path
       v
SMTP credential
       |
       v
Spring Environment / sender configuration
       |
       v
JavaMailSenderImpl
```

When choosing this approach, you must answer:

1. **What authenticates to the secret store?** Prefer managed workload identities (Kubernetes auth, cloud identity, etc.) when supported by the system. Do not hardcode an admin token.
2. **Which path may be read?** Only read permission for the service's SMTP secret, without granting wildcard access across the whole store.
3. **What if the store is unreachable at startup?** For mandatory secrets, you usually need to fail fast or report the application as not ready; do not use a fallback password.
4. **How long are values cached?** Account for latency and possible outages of the secret store.
5. **How does rotation affect the bean?** Loading configuration at startup does not automatically ensure a running sender gets refreshed.
6. **Does the integration leak secrets via logs/tracing?** Determine redaction practices and who can view telemetry.

Dependency syntax, `spring.config.import`, auth methods, and specific paths vary by Spring Boot/Spring Cloud/provider version. Use an integration compatible with the running application version and store policy.

Example of organizing keys in a secret store:

```text
prod/mail-service/smtp
    username = [protected value]
    password = [protected value]

staging/mail-service/smtp
    username = [separate value]
    password = [separate value]
```

Path names only illustrate the idea, not a mandatory syntax of a provider.

## 7. Organizing secrets across local, staging, and production

Each environment should have **independent credentials and access permissions**:

| Environment | Suitable configuration source | Principle |
|---|---|---|
| Local development | Temporarily supplied env vars, a developer secret tool, or an SMTP sandbox | Do not use production email-sending accounts for testing. |
| Automated tests | Simulated mail server, fake SMTP, or test fixtures | Do not send real mail to users. |
| Staging | Staging-specific secret store or injection | Separate accounts and restrict the recipient set. |
| Production | Secret store/deploy platform with service identity, audit, and rotation | Real credentials, mandatory TLS, and activity monitoring. |

For example, you can run locally with an SMTP test server on `localhost:1025`, needing no credentials or TLS if it is an isolated test server:

```yaml
# application-local.yml - for internal SMTP sandbox use only
spring:
  mail:
    host: localhost
    port: 1025
    username: ""
    password: ""
    properties:
      mail:
        smtp:
          auth: false
          starttls:
            enable: false
            required: false
```

This is **not a valid configuration for production SMTP**. In production, do not disable TLS/AUTH just to avoid secret or connection errors.

### 7.1. Is a .env file a default Spring Boot mechanism?

Some deployment tools can read `.env`, but **Spring Boot does not implicitly read every `.env` file the way Docker Compose or a dotenv library does**. The file only takes effect if the IDE, shell, container runtime, or an integration has actually loaded the keys into an environment/property source.

If using `.env` for local:

- Create `.env.example` containing only variable names and placeholders, with no real secrets.
- Add `.env` to `.gitignore`; set appropriate machine access permissions.
- Do not copy the file into Docker images or artifacts.
- Do not assume `.gitignore` removes secrets already committed in Git history.
- When a secret is leaked via commit/log, you must **revoke or rotate it**, not merely delete it from the current version.

### 7.2. Injecting from a Kubernetes Secret via environment

If you do not use `configtree:`, you can also let Kubernetes place values into the container's env:

```yaml
# Excerpt of container configuration in a Pod/Deployment
env:
  - name: SPRING_MAIL_USERNAME
    valueFrom:
      secretKeyRef:
        name: mail-smtp-credentials
        key: username
  - name: SPRING_MAIL_PASSWORD
    valueFrom:
      secretKeyRef:
        name: mail-smtp-credentials
        key: password
```

This is an excerpt; it must sit properly inside a Pod's container definition. The secret keys have been created beforehand. Spring Boot binds directly from `SPRING_MAIL_USERNAME` and `SPRING_MAIL_PASSWORD` at startup.

Changing the value of a Kubernetes Secret does not change the environment variables of a **running process**. Usually a rolling restart or Pod recreation is needed for new processes to pick up the new value.

## 8. Scoping secret permissions by service and sending channel

The **least privilege** principle: each workload reads only the secrets it needs to use.

Example of a system separating transactional email and marketing email:

```text
secret/prod/mail/transactional
    └── readable only by transaction-mail-worker

secret/prod/mail/marketing
    └── readable only by campaign-mail-worker

secret/staging/mail/test
    └── readable only by staging-mail-service
```

Why separate them?

- Revoking marketing credentials does not force changing transactional credentials.
- Easy to track access sources and limit quotas/permissions.
- One compromised worker does not necessarily read all production SMTP credentials.
- Each channel can use a different account, sending domain, or provider.

However, **two `JavaMailSender` beans in the same JVM do not create a strong security boundary**. If the process has permission to read both secrets, privileged code in the process can access both. When strict isolation is needed, separate the workloads and service identities.

In addition to read permission from the secret store, the SMTP account/API key should also be granted the **minimum sending permissions** the provider supports. If there are separate scopes, do not grant account-administration permissions when the application only needs to send mail.

## 9. Rotation: replacing SMTP credentials safely

**Rotation** means replacing an old secret with a new secret, then revoking the old secret. A favorable case is when the provider allows two credentials to exist simultaneously during the transition window:

```text
T0  App instances A/B/C use credential v1
 |
 v
T1  Create credential v2 at the SMTP provider
 |
 v
T2  Save v2 into the secret store
 |
 v
T3  Rolling restart / refresh each instance
 |   so the sender uses v2
 |
 v
T4  Verify AUTH, send test, observe errors
 |
 v
T5  Revoke credential v1
```

Operational steps:

1. **Issue a new credential** with properly scoped permissions and update the secret store by version.
2. **Deploy instance groups gradually** so they receive the new credential; avoid disrupting the whole sending flow if possible.
3. **Verify connection/authentication and send a test mail** using appropriate metrics, without printing credentials to logs.
4. **Check that no workload still uses v1** and revoke v1.
5. **Monitor AUTH errors and the mail-sending queue** after the switchover.
6. Record rotation metadata such as timestamp, performing person/system, and version; do not store secret values in reports.

Not every SMTP provider allows creating two active credentials simultaneously. If not supported, plan the switchover window or switch accounts within the provider's limits. When a credential has been exposed, prioritize emergency revocation according to risk level rather than waiting for the scheduled rotation.

### 9.1. Why does changing the secret store not make JavaMailSender use the new password yet?

`JavaMailSenderImpl` usually receives the username/password when the bean is created or configured. Afterward:

- The secret store may already hold **v2**.
- The mounted secret file may already contain **v2**.
- The running bean and SMTP transport may still be using **v1**.

**Updating the data source** and **refreshing configuration in-process** are two different actions. You can perform a rolling restart, recreate the sender bean, or use an explicitly designed dynamic refresh mechanism. If refreshing directly, pay attention to in-flight send calls, already-authenticated connections, and consistency across multiple workers.

Do not just put `@RefreshScope` on a bean and assume every secret source can emit refresh events or that all SMTP connections will automatically switch credentials.

### 9.2. What if a credential expires mid-send?

A job may have been dequeued and hit an `AUTH` error because the old secret was revoked. You should:

- Classify authentication errors separately from recipient-address errors.
- Not retry continuously with a credential the server has already rejected.
- Put the job into a state requiring retry or waiting for recovery per policy, while alerting operations.
- After the application uses the new secret, allow reprocessing of eligible jobs.
- If a timeout happens **after the SMTP server may have received all of `DATA`**, the send result may be undetermined; retrying may cause duplicate mail.

Secret management does not replace an outbox, a message queue, or a controlled retry policy.

## 10. Protecting secrets while the application is running

Even when the password is no longer in Git, it can still be exposed at runtime.

| Place easily exposed | Example | Risk-reduction direction |
|---|---|---|
| Process arguments | `--spring.mail.password=...` | Avoid passing secrets directly via command-line arguments. |
| Shell/script | `export SMTP_PASSWORD=real-password` in a committed script | Use platform injection or safe terminal input when local. |
| Startup and exception logs | Printing `MailProperties`, `Environment`, tokens, or payloads | Log only the error type, event ID, hostname, and status; do not log secrets. |
| Spring Boot Actuator | `/actuator/env`, `/actuator/configprops` | Restrict endpoints and access permissions; do not rely only on default masking. |
| CI/CD | Deploy logs, build artifacts, echoed variables | Use secret masking, restrict view permissions and retention time. |
| Container/JVM dump | Heap dumps, process info, debug tools | Limit who has access, apply appropriate encryption/storage and retention. |
| Git/Docker image | `application-prod.yml` containing a password | Do not commit or bake real values into images. |
| Email header/body | Putting an API key into `Message-ID` or custom headers | Do not transmit secrets in email content or headers. |

**Logs sufficient for diagnosis** can be:

```text
mail_channel=transactional
smtp_host=smtp.example.com
smtp_port=587
event_id=evt-1028
attempt=1
result=AUTH_FAILED
duration_ms=410
```

**Do not log**:

```text
smtp_password=...
api_key=...
AUTH PLAIN <encoded-credentials>
secret_store_token=...
```

Some Spring Boot versions have a mechanism to sanitize sensitive properties when displayed, but you must control both Actuator access permissions and logs generated by the application, libraries, or infrastructure. Jakarta Mail debug may contain sensitive metadata; enable it only when needed, in a controlled environment, and do not publish raw protocol transcripts.

## 11. SMTP TLS protects credentials in transit

A secret store protects storage and distribution, yet **SMTP AUTH still needs a protected connection**. Two common models:

**Port 587 with STARTTLS:**

```yaml
spring:
  mail:
    port: 587
    properties:
      mail:
        smtp:
          auth: true
          starttls:
            enable: true
            required: true
          ssl:
            checkserveridentity: true
```

**Port 465 with TLS from the start:**

```yaml
spring:
  mail:
    port: 465
    properties:
      mail:
        smtp:
          auth: true
          ssl:
            enable: true
            checkserveridentity: true
```

Do not downgrade to an unencrypted connection or disable certificate checking just to "get mail sent". Actual configuration needs to match the host/port/certificate published by the provider.

Besides the connection, mail-sending configuration needs to consider account sending permissions, domain verification, and SPF, DKIM, DMARC. **Protecting passwords** and **ensuring mail is trusted by receiving systems** are two related yet distinct tasks.

## 12. Checking connectivity without printing secrets

You can check SMTP connectivity with `JavaMailSenderImpl.testConnection()` in an appropriate environment. This method helps detect some host, TLS, or authentication errors; it does not send a complete test email and **does not prove mail reached the Inbox**.

Example:

```java
package com.example.mail;

import jakarta.mail.MessagingException;
import org.springframework.mail.javamail.JavaMailSenderImpl;
import org.springframework.stereotype.Component;

@Component
public class SmtpConnectionProbe {

    private final JavaMailSenderImpl sender;

    public SmtpConnectionProbe(JavaMailSenderImpl sender) {
        this.sender = sender;
    }

    public boolean canConnect() {
        try {
            sender.testConnection();
            return true;
        } catch (MessagingException ex) {
            // Can raise an alert by error type, do not log the password.
            return false;
        }
    }
}
```

This snippet assumes the application has a suitable `JavaMailSenderImpl` bean. If there are multiple senders, specify the bean with `@Qualifier` or create separate probes per channel. Avoid calling it continuously at high frequency for health checks, because opening connections/authenticating has a cost and may hit rate limits.

When errors occur, distinguish:

| Sign | Cause group to examine |
|---|---|
| Cannot resolve SMTP host | DNS/host configuration or network. |
| Connection refused/timeout | Port, firewall, relay, timeout. |
| TLS handshake error | Port/TLS mechanism, certificate, trust/hostname. |
| `535 Authentication failed` | Old credential, locked account, AUTH policy, rotation not yet reflected in bean. |
| Temporary `4xx` | Quota, rate limit, or SMTP server status. |
| `5xx` at recipient | Sending policy or recipient address, not necessarily related to secrets. |

Never troubleshoot an error by logging the whole password to "see whether the application is reading it right".

## 13. Choosing env vars or a secret store?

| Criterion | Environment variable | Secret store |
|---|---|---|
| Setup | Simple, directly supported by Spring Boot. | Requires infrastructure/integration and service identity. |
| Policy-backed storage | Depends on the source that injected the variable. | Usually has platform-backed policies, audit, and versioning. |
| Access control | Mostly by process/host/deployment. | Can be fine-grained by workload and secret path. |
| Rotation | Requires changing the source and refreshing the process/bean. | Can manage versions/rotation yet still requires refreshing the application. |
| Local development | Convenient. | May require extra permission/authentication steps. |
| Multiple services, multiple environments | Needs an orchestrator to manage distribution. | Easy to govern centrally when policies are well designed. |
| Risk if misconfigured | Exposure via commands/logs/metadata. | Overly broad IAM, bootstrap token leaked, faulty refresh. |

**Selection suggestions by need:**

- **Local and demo:** environment variables with an SMTP sandbox, no real passwords in the repo.
- **Production on a platform supporting secret injection:** use the platform's secret manager to supply env/files; Spring Boot binds normally.
- **Many applications and critical credentials:** a secret store with clear identity, audit, and rotation.
- **Credentials needing continuous updates:** design real integration and refresh, rather than assuming Config Data updates beans automatically.

You can use a **secret store as the source of truth** and **env vars/configtree as the distribution method**. You do not have to choose one and discard the other.

## 14. Handling suspected SMTP credential exposure

Suppose an API key or password appears in a Git commit, CI/CD log, or support ticket. Steps to take:

1. **Determine scope:** which account/environment the credential belongs to, what permissions it has, and where it appeared.
2. **Revoke or rotate:** create a new value and invalidate the exposed value according to urgency.
3. **Update the secret source safely:** put the new version into the secret store or injection mechanism.
4. **Redeploy the application:** restart/refresh so the sender uses the new credential; monitor AUTH errors and queue latency.
5. **Review for abuse:** check unusual sending activity, quota, logs from the SMTP provider, and related alerts.
6. **Contain copies:** handle secrets that may exist in Git history, artifacts, logs, and support data per process.
7. **Prevent recurrence:** add secret scanning, permission management, config reviews, and limit who can view logs/CI.

**Deleting a line from a new commit does not make an exposed credential safe.** Revocation/rotation is mandatory whenever there is a risk of unauthorized use.

## 15. Common misconceptions

**"Putting a password in an environment variable means the password is encrypted."** False. Env vars are where the process receives values; you must control where the source is stored and runtime access permissions.

**"A Kubernetes Secret with Base64 is securely encrypted."** False. Base64 is a representational encoding that can be decoded easily; encryption at rest, RBAC, and identity are separate configurations.

**"Already using Vault means SMTP TLS is unnecessary."** False. Vault protects storage and distribution, while TLS protects credentials over the SMTP connection.

**"Changing a secret in the store makes every JavaMailSender use the new value immediately."** False. Many senders are bound at startup and need a refresh/restart mechanism.

**"The password is not in YAML, so logging it is fine."** False. Logs/traces/artifacts can also be viewed or retained long-term.

**"Having one production SMTP account for all services is optimal."** It may seem convenient initially, yet widens the blast radius if the credential leaks and makes auditing/revocation harder.

**"If the password is missing, allow sending without AUTH so the application keeps running."** Unsuitable when the SMTP provider requires authentication. Errors should be detected clearly, not by silently lowering security standards.

**"A secret store automatically solves duplicate or lost emails."** False. Durability of send requests, retry, and idempotency belong to worker/outbox design, not a secret store's function.

## 16. Practice exercises

### Exercise 1 — Supply credentials via environment variables

Create a `spring.mail.*` configuration using `${SMTP_USERNAME}` and `${SMTP_PASSWORD}`. Supply the two variables via shell or IDE and send an email to an SMTP sandbox.

Try running without `SMTP_PASSWORD` and observe the configuration or sending error. Explain why you do not add a default password in code to avoid this error.

### Exercise 2 — Switching from env to configtree

Suppose a Pod has:

```text
/run/secrets/spring.mail.username
/run/secrets/spring.mail.password
```

Write the required `spring.config.import`. Explain when to use `configtree:` and when to use `optional:configtree:`. State how to restrict file read permissions and the process for refreshing the sender if a secret changes.

### Exercise 3 — Separating secrets between transactional and marketing

A system has two email-sending workers with different needs and quotas. Design two secret paths and two service identities, pointing out what condition causes creating two beans in the same process to still fall short of a strong security boundary.

### Exercise 4 — Rotation across multiple instances

Three Spring Boot instances are using SMTP credential v1. The provider temporarily allows using v1 and v2 in parallel. Lay out the sequence: create v2, update store, rolling restart, verify AUTH/test send, revoke v1, monitor errors after switchover.

### Exercise 5 — Diagnosing errors at the right layer

The application connected, yet SMTP reports `535 Authentication failed`. List what to check without printing the password: the secret version supplied by deployment, property precedence order, whether pods have restarted, whether the account/role is still valid, and whether the provider changed the AUTH mechanism.

### Exercise 6 — Data classification

Given the values `SMTP_HOST`, `SMTP_PASSWORD`, `SMTP_API_KEY`, `From`, `DKIM_PRIVATE_KEY`, and `mail.smtp.starttls.required`. Identify which values must be managed as secrets and which belong to ordinary configuration; explain each choice.

## 17. Summary

In Spring Boot Mail, **environment variables** help separate SMTP credentials from source code; a **secret store** supports managing permissions, audit, versioning, and rotation. Spring can receive values from environment variables, `configtree:` files, or integrations with a secret manager. Whichever approach is chosen, `JavaMailSender` still only needs to be configured and used through the familiar email-sending API.

You need to protect the entire secret lifecycle: grant appropriate permissions, do not write passwords into Git/logs, use TLS matching the SMTP provider, restrict runtime access, design rotation alongside bean restart/refresh, and revoke exposed credentials. **Keeping passwords out of `application.yml` is the first step; real security depends on how the application and infrastructure manage secrets from provisioning to revocation.**

