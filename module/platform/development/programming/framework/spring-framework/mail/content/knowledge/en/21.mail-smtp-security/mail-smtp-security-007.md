# Protecting Secrets in Configuration

## 1. Why is SMTP configuration sensitive data?

In **Spring Framework Mail**, applications typically use `JavaMailSender` to send email through an SMTP server. Alongside host, port, and TLS mode, the client may need authentication credentials such as a username/password, app password, or OAuth 2.0 access token. These values are **secrets** because they allow another process or person to exercise the email-sending permissions of an account or organization.

Example of a simple Spring Boot configuration:

~~~yaml
spring:
  mail:
    host: smtp.example.net
    port: 587
    username: notifications@example.net
    password: some-password
~~~

If `some-password` is a real credential, placing it directly in `application.yml` and committing it to Git is a major risk: anyone who can read the repository, build outputs, artifacts, or backups can access the secret. Beyond source code, secrets can also surface in command lines, debug logs, CI/CD outputs, container images, runtime environments, or management dashboards.

An exposed secret can lead to:

- Sending spam/phishing using the organization's legitimate account.
- Exceeding SMTP quotas or getting the account locked, disrupting transactional emails.
- Accessing mailboxes or other services if credentials are reused.
- Leaking recipient lists, notification contents, and operational details.
- Harder investigations because the attacker's activity looks like application connections.

The goal of this lesson is to configure `JavaMailSender` so that **the application can use secrets when needed without storing, spreading, or exposing them where unauthorized**.

> **Core principle:** Code and artifacts should contain **configuration names**, not **secret values**. Secrets are provisioned at runtime via a controlled channel; only the component that needs to send mail should have read access.

## 2. Distinguishing configuration data and secrets

Not every SMTP property needs the same level of protection:

| Property | Example | Is it a secret? | Recommendation |
| --- | --- | --- | --- |
| SMTP host | `smtp.example.net` | Usually no | Can be placed in environment-specific configuration |
| Port | `587` or `465` | No | Declare explicitly |
| STARTTLS/SSL | `true` | No | Enforce per security policy |
| SMTP username | `mailer@example.net` | Often sensitive operational data | Restrict visibility; may be provisioned alongside secrets |
| SMTP password/app password | Provider-issued string | **Yes** | Never commit, never log, supply at runtime |
| OAuth access token | Short-lived bearer token | **Yes** | Manage lifecycle, scope, and expiration |
| OAuth refresh token/client secret | Credential for obtaining new tokens | **Yes** | Secret manager/identity provider |
| TLS private key (if using mTLS) | Private key | **Yes** | Keystore/secret store, strict access control |
| CA certificate/public certificate | Public cert | Usually no | Can be distributed as trust configuration |

An SMTP username alone may sometimes be insufficient to log in, yet it should still be treated as operational data needing control because it can reveal sending accounts or internal infrastructure. Do not print an entire configuration object merely assuming a username is not a password.

### 2.1. An app password is not the primary account password

If the provider supports **app passwords**, use a dedicated application credential with appropriate scope instead of a personal account or shared login password. When revocation is needed, the organization can disable the app password without forcing password resets for all users.

However, an app password is still a **fully privileged secret within its granted scope**. Never let it appear in Git, Docker images, or logs just because its name includes the word “app”.

### 2.2. OAuth2 does not make tokens public data

Some SMTP providers support OAuth2/XOAUTH2 authentication. In that case, a static password can be replaced by a time-limited, scoped access token. The token is still a credential: never log it, commit it, or send it over an insecure channel. If a refresh token or client secret is used to acquire new tokens, those values must also be protected.

How the authentication mechanism and token acquisition are enabled depends on the provider/Jakarta Mail implementation. Never assume simply changing `spring.mail.password` to a token string will automatically make every provider work with OAuth2.

## 3. Places where secrets commonly leak

Secrets can leak through many paths, not only `application.yml`:

| Leak location | Bad example | Problem |
| --- | --- | --- |
| Source control | Committing real `spring.mail.password` | Secret stored in Git history and clones |
| Packaged config files | Generating `application-prod.yml` with password at build time | Secret baked into JAR/image/artifact |
| Command line | `--spring.mail.password=...` | May appear in process listings, job logs |
| Docker build | `ARG SMTP_PASSWORD` written into a layer | May leak in build history/layers/cache |
| CI pipeline | Printing variables or enabling shell tracing | Secret appears in logs/artifacts |
| Application logs | `log.info("{}", mailProperties)` | Prints entire object including password |
| SMTP debug | Enabling auth debugging arbitrarily | Provider/debug output may disclose sensitive info |
| Actuator | Exposing `/env`, `/configprops` too broadly | Unauthorized users can view configuration |
| Runtime environment | Inspection/process diagnostic tools | Environment variables readable by host/container admins |
| Backups, support bundles | Copying secret files alongside logs | Secret duplicated outside managed channels |
| Chat/tickets | Pasting real credentials when asking for help | Expands who can read the secret |

Leak prevention must cover **development, building, deployment, runtime operation, and incident troubleshooting**.

## 4. What not to do: hard-coding credentials

Example to avoid:

~~~java
@Configuration
class MailConfiguration {

    @Bean
    JavaMailSender mailSender() {
        JavaMailSenderImpl sender = new JavaMailSenderImpl();
        sender.setHost("smtp.example.net");
        sender.setPort(587);
        sender.setUsername("notifications@example.net");
        sender.setPassword("a-real-secret-here"); // NOT RECOMMENDED
        return sender;
    }
}
~~~

Credentials in source code can be:

- Committed to Git or pushed to a remote.
- Copied into feature branches, forks, mirrors, or backups.
- Packaged into source JARs, bytecode, or distributed artifacts.
- Displayed during code reviews or in screenshots.

Converting it to a Base64 string or encrypting it with a key also written in the repository **does not solve the problem**. Base64 is only encoding, not encryption; if the program contains enough hard-coded decryption keys in the same artifact, anyone reading the artifact can figure out how to decrypt it.

Using a clearly fake sample value for documentation is acceptable, but **never use real credentials in snippets, fixtures, or test commits**.

## 5. Configuring Spring Boot with environment variables

A basic way to separate secrets from source is using placeholders in `application.yml`:

~~~yaml
spring:
  mail:
    host: smtp.example.net
    port: 587
    username: ${SMTP_USERNAME}
    password: ${SMTP_PASSWORD}
    properties:
      mail.smtp.auth: true
      mail.smtp.starttls.enable: true
      mail.smtp.starttls.required: true
      mail.smtp.ssl.checkserveridentity: true
      mail.smtp.connectiontimeout: 5000
      mail.smtp.timeout: 10000
      mail.smtp.writetimeout: 10000
~~~

In this example:

- `SMTP_USERNAME` and `SMTP_PASSWORD` are environment variable **names**, not values.
- Spring resolves placeholders when constructing application configuration.
- `spring.mail.username` and `spring.mail.password` are consumed by the mail sender setup when Spring Boot mail auto-configuration is active.
- Only host/port and TLS/timeout policies live directly in YAML.

Example of launching locally from a shell provisioned with environment variables through a safe channel:

~~~text
SMTP_USERNAME = <value supplied outside the repository>
SMTP_PASSWORD = <value supplied outside the repository>
~~~

Do not put real values into committed scripts, README files, or terminal commands pasted into issues. Variable names can be public; secret values must be injected at runtime.

### 5.1. Do not put default passwords in placeholders

Avoid:

~~~yaml
spring:
  mail:
    password: ${SMTP_PASSWORD:hardcoded-fallback-secret}
~~~

The `${NAME:default}` syntax makes the application silently fall back to the default value if the environment lacks the variable. If the default is a real credential, the secret is back in Git; if the default is a dummy password, production can boot up and fail at runtime in a confusing way.

For configurations requiring authentication, **fail fast** when a secret is missing instead of defaulting to a fixed password. If development does not send mail externally, use a separate profile with an SMTP sink or fake sender rather than a fallback real secret.

### 5.2. Relaxed binding and Spring Boot variable names

Spring Boot can bind environment variables via relaxed binding rules. For example, in some deployment setups:

~~~text
SPRING_MAIL_HOST
SPRING_MAIL_PORT
SPRING_MAIL_USERNAME
SPRING_MAIL_PASSWORD
~~~

can map to the corresponding `spring.mail.*` properties. This is an alternative to `${SMTP_PASSWORD}` placeholders in YAML.

Choose one clear convention per deployment environment and avoid declaring multiple password sources simultaneously with confusing precedence. Do not assume a secret is injected properly just because the variable exists; include runtime checks on configuration and permissions.

### 5.3. Environment variables have security limits

Environment variables are better than hard-coding, yet **they are not a secret vault**:

- Anyone with host/container admin rights can read process environments.
- Certain inspection tools, crash dumps, or support diagnostics can capture environment variables.
- CI/CD misconfigurations can print variables into logs.
- Environment variables generally do not update automatically inside a running process when a secret rotates.

For high-security production environments, consider **read-only mounted secret files or a secret manager** rather than placing every credential in environment variables.

## 6. Protecting credentials in transit over SMTP

Separating secrets from Git only protects credentials **at rest**. When the application sends to an SMTP server, credentials must be protected **in transit**.

Two common connection models:

| Mechanism | Example port | How it is set up |
| --- | ---: | --- |
| Submission with STARTTLS | 587 | Open connection, upgrade to TLS before authenticating |
| Implicit TLS/SMTPS | 465 | TLS starts immediately upon opening connection |

STARTTLS example on port 587:

~~~yaml
spring:
  mail:
    host: smtp.example.net
    port: 587
    username: ${SMTP_USERNAME}
    password: ${SMTP_PASSWORD}
    properties:
      mail.smtp.auth: true
      mail.smtp.starttls.enable: true
      mail.smtp.starttls.required: true
      mail.smtp.ssl.checkserveridentity: true
~~~

`mail.smtp.starttls.enable=true` enables STARTTLS upgrading when the server supports it. **`mail.smtp.starttls.required=true`** requires STARTTLS to succeed rather than proceeding over an unencrypted path when unsupported. `mail.smtp.ssl.checkserveridentity=true` requires verifying the server's hostname against the TLS certificate, helping prevent connecting to a spoofed endpoint.

Implicit TLS example on port 465:

~~~yaml
spring:
  mail:
    host: smtp.example.net
    port: 465
    username: ${SMTP_USERNAME}
    password: ${SMTP_PASSWORD}
    properties:
      mail.smtp.auth: true
      mail.smtp.ssl.enable: true
      mail.smtp.ssl.checkserveridentity: true
~~~

Do not enable both modes just to get “as much TLS as possible”; choose the configuration matching the endpoint type provided by your provider. Ports are common conventions, not proof of security: verify that the server truly supports the required mechanism.

### 6.1. Avoid configurations that disable TLS verification

Do not use:

~~~yaml
spring:
  mail:
    properties:
      mail.smtp.ssl.trust: "*"
~~~

Setting overly broad trust can cause the application to trust unintended certificates, weakening server authentication. If the SMTP server certificate is invalid, fix the trust chain or truststore properly rather than disabling validation just to “make sending work”.

Do not drop `starttls.required` to bypass a TLS error and end up logging in with real credentials over an unprotected connection. Runtime secret security and TLS are two complementary layers of defense.

## 7. Using secret files and Spring Boot config trees

In containers or production environments, one way to supply secrets is **mounting read-only files from a secret store**. The application reads secrets at startup without putting their values into the repository, command line, or Docker image.

Spring Boot supports **config trees**: each file in a directory becomes a property, with the filename as the property key and the file contents as the value. Example directory provisioned at runtime:

~~~text
/run/secrets/smtp/
├── spring.mail.username
└── spring.mail.password
~~~

Example configuration file containing no secrets:

~~~yaml
# application-prod.yml
spring:
  config:
    import: "configtree:/run/secrets/smtp/"
  mail:
    host: smtp.example.net
    port: 587
    properties:
      mail.smtp.auth: true
      mail.smtp.starttls.enable: true
      mail.smtp.starttls.required: true
      mail.smtp.ssl.checkserveridentity: true
      mail.smtp.connectiontimeout: 5000
      mail.smtp.timeout: 10000
      mail.smtp.writetimeout: 10000
~~~

The contents of the two secret files are provisioned by the deployment platform and must never be written into the repository or packaged in the JAR. When Spring Boot reads the config tree, `spring.mail.username` and `spring.mail.password` are supplied to mail auto-configuration.

In the production example, do not prefix `configtree:` with `optional:`: if the secret mount is missing, startup should fail clearly rather than silently ignoring a mandatory configuration source. If an environment **does not use real SMTP**, configure a separate profile rather than using production secrets as a fallback.

### 7.1. Why can file mounts be better than environment variables?

Secret files allow the deployment platform to enforce:

- Filesystem read permissions scoped to the process user/group.
- Read-only volume mounts, reducing accidental modification.
- Secret authorization scoped by workload/service account.
- Separation of secret provisioning from builds and images.
- Access auditing through the secret manager or operations platform.

Still, file mounts **do not make secrets invulnerable**. Users with filesystem read access inside the container or host can still read the contents; once read, the process still holds the secret in memory. Combine with least privilege, network policies, log hygiene, and runtime access controls.

### 7.2. Do not mount secret files into web/static directories

Never mount secrets in directories such as:

~~~text
src/main/resources/static/
public/
wwwroot/
~~~

or any directory that an HTTP server could serve as public files. Secret files must stay outside static resource serving paths and out of user-downloadable areas.

**Path notation note:** `/run/secrets/smtp/` is a Linux/container example, not a universal requirement across all platforms. For Windows services or other environments, use an equivalent location and secret-provisioning mechanism with proper ACLs.

## 8. Kubernetes deployment example

Kubernetes provides the `Secret` object and can mount keys as files inside a Pod. An illustrative `Deployment` snippet:

~~~yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: mail-api
spec:
  replicas: 2
  selector:
    matchLabels:
      app: mail-api
  template:
    metadata:
      labels:
        app: mail-api
    spec:
      containers:
        - name: app
          image: registry.example.net/mail-api:release-tag
          volumeMounts:
            - name: smtp-secret-files
              mountPath: /run/secrets/smtp
              readOnly: true
      volumes:
        - name: smtp-secret-files
          secret:
            secretName: smtp-credentials
            items:
              - key: username
                path: spring.mail.username
              - key: password
                path: spring.mail.password
~~~

This example **contains no secret values**; the Secret named `smtp-credentials` has been created/provisioned by a controlled secrets management workflow. The mounted files match the config tree properties in the previous section.

In real environments:

- Grant Secret read access only to the service account/workload that needs to send mail.
- Configure RBAC and policies restricting who can `get/list/watch` Secrets.
- Enable encryption at rest for Secret data as supported by the cluster.
- Restrict access to Pods, nodes, and `exec`/debug capabilities.
- Set file permissions so non-root applications can read the files without granting access to every process.
- Never commit a `Secret` manifest whose `data` or `stringData` holds real credentials to public Git or unauthorized repositories.

**Kubernetes Secrets do not guarantee absolute secrecy on their own.** Values in `data` are Base64-encoded; Base64 **is not security encryption**. Secrets can be read if RBAC, node permissions, or backup workflows are misconfigured.

### 8.1. Provisioning secrets from external systems

In many organizations, Kubernetes Secrets can be synced from a secret manager via a controller or CSI driver. Then:

~~~text
Secret manager / vault
          |
          v
Controlled workload identity
          |
          v
Secret sync / CSI mount
          |
          v
Read-only runtime file
          |
          v
Spring Boot config tree
          |
          v
JavaMailSender
~~~

Exact steps depend on the provider and infrastructure, while the principles stay constant: secrets never enter images, read access is workload-scoped, rotation exists, and auditing is enabled.

### 8.2. Rotating a mounted file does not mean the app changed its credential

Even when the platform updates the secret file's content, `JavaMailSender` or Spring Boot's configuration objects may have already read the value at startup. Replacing the file does not automatically guarantee the SMTP bean picks up the new password in every setup.

Define an explicit **reload or rolling restart** strategy when rotating secrets. If using a dynamic refresh mechanism, verify thread safety, connection pools, timing of application, and handling of in-flight sends.

## 9. Secret managers and workload identity

For production, organizations can store credentials in a dedicated secrets management system:

- HashiCorp Vault or an equivalent platform.
- A cloud provider's secret manager.
- An internal key/credential management system.
- An identity service issuing short-lived tokens instead of long-lived passwords.

The key difference from storing passwords in source is that **secrets are granted only to authorized workloads at runtime**, usually based on machine/workload identity or a service account.

General flow:

~~~text
Developer commits code (no secrets)
          |
          v
CI builds immutable artifact (no secrets)
          |
          v
Runtime authenticates using workload identity
          |
          v
Secret manager authorizes secret read
          |
          v
Process obtains credential
          |
          v
JavaMailSender authenticates over TLS
~~~

An application using a secret manager must still protect the **identity used to fetch secrets**. If you have to hard-code a “Vault master password” into the application to get the SMTP password, the system merely shifts the problem to another secret.

### 9.1. Least privilege

An email-sending workload should only be allowed to read:

- Credentials for the SMTP account it actually uses.
- The secret version corresponding to its environment (`dev`, `staging`, `production`).
- Keys relevant to its authorized mail-sending flow.

Never grant read access to all organizational secrets just to let one mail service operate. Separate production credentials from staging, separate senders per system where supported by the provider, and limit account capabilities to what is needed.

### 9.2. Environment and tenant isolation

Never share a single SMTP password across:

- Local development, staging, and production.
- Multiple unrelated applications.
- Multiple tenants when isolation requirements carry distinct risk profiles.

When using per-tenant credentials, select the secret based on an **authenticated and authorized** tenant rather than taking a secret path directly from a request and reading arbitrarily. Do not log secret names containing personal info if secret namespaces contain PII.

## 10. Keep SMTP secrets out of Docker images

In CI/CD, SMTP credentials are typically needed only at **runtime**, not for compiling, unit testing, or packaging the JAR.

Avoid:

~~~dockerfile
# NOT RECOMMENDED
ARG SMTP_PASSWORD
ENV SMTP_PASSWORD=$SMTP_PASSWORD
COPY application-prod-with-password.yml /app/application.yml
~~~

Problems:

- Build arguments or `ENV` values can appear in image metadata, history, or build logs.
- Files `COPY`ed into the image persist across published layers/artifacts.
- Rebuilding images on every secret change makes rotation slow and scatters credentials.

Dockerfiles should stay independent of SMTP secrets:

~~~dockerfile
FROM eclipse-temurin:21-jre
WORKDIR /app
COPY app.jar /app/app.jar
ENTRYPOINT ["java", "-jar", "/app/app.jar"]
~~~

The runtime supplies environment variables or secret volumes via the deployment mechanism. Do not try to “hide it inside the Docker image” by encrypting the password with a key also `COPY`ed into the image.

### 10.1. Docker Compose using runtime variables still needs protection

Configuration-level example:

~~~yaml
services:
  mail-api:
    image: registry.example.net/mail-api:release-tag
    environment:
      SMTP_USERNAME: ${SMTP_USERNAME:?required}
      SMTP_PASSWORD: ${SMTP_PASSWORD:?required}
~~~

Here Compose uses interpolation to pull values from the deployment tool's environment. `:?required` requires variables to have values per Compose syntax, preventing deployments with blank variables.

However, values placed in a **container's environment** can be read by inspection tools or anyone with daemon/container admin rights. For high-security environments, prefer supported runtime secret file/secret service mechanisms. If a `.env` file supplies variables, restrict its permissions and **never commit it to Git**; merely adding it to `.gitignore` is insufficient if the file was ever committed.

## 11. Protecting SMTP secrets in CI/CD

Build and deployment pipelines are a common source of credential leaks. A secure workflow should separate two stages:

~~~text
Build stage
   - checkout source
   - compile/test
   - package artifact / container image
   - do not read production SMTP password
          |
          v
Deploy stage
   - deploy built artifact
   - workload receives secret at runtime
   - application starts and authenticates SMTP over TLS
~~~

This allows artifacts to be promoted from staging to production without embedding any environment's credentials.

### 11.1. Pipeline principles

- Store credentials in the **CI/CD secret store or runtime platform**, never in pipeline YAML files.
- Restrict which environments/branches/jobs can access production secrets.
- Grant access only to deploy jobs that genuinely need it; pull-request jobs from untrusted sources must not read credentials.
- Never use `echo`, `printenv`, `set -x`, or dump the full environment when secrets are present.
- Enable pipeline secret masking if supported by the platform, though **masking does not replace avoiding logging secrets**.
- Never write secrets into build caches, test reports, artifacts, support bundles, or terminal transcripts.
- Never pass passwords via command-line arguments visible in process listings.
- Control who can edit pipeline definitions, since anyone able to modify pipeline steps could alter code to read secrets.
- Audit secret access, permission changes, and deployments using production privileges.

If the pipeline must run integration tests with SMTP, use an SMTP sink or a **dedicated test account** with limited quota and scope. Never use production credentials in unit tests or automated tests from unprotected branches.

### 11.2. Secret scanning and Git history

You can add secret scanning in pre-commit hooks or CI to catch credentials added to source, config files, or commits. However, scanners may not recognize every token format and do not replace code review or secrets management.

If a secret was ever committed, adding the filename to `.gitignore` only stops future additions; **it does not erase contents from historical commits, clones, or backups**. Upon detecting an exposed secret, prioritize immediate rotation/revocation, then handle history and copies per incident response procedures.

## 12. Prevent secrets from leaking through logging and SMTP debug

A common mistake when diagnosing SMTP is turning on protocol logging or printing config objects:

~~~java
// NOT RECOMMENDED:
log.info("SMTP config: {}", mailProperties);
log.error("SMTP failed, password={}", password);
~~~

Mail properties objects can contain passwords; auto-generated `toString()` methods on records or Lombok classes can accidentally print every field.

Safer logging example:

~~~java
log.info(
        "Mail sender configured host={} port={} tlsRequired={}",
        configuredHost,
        configuredPort,
        true);
~~~

For send errors:

~~~java
try {
    mailSender.send(message);
} catch (MailException ex) {
    log.warn(
            "Mail send failed deliveryId={} errorType={}",
            deliveryId,
            ex.getClass().getSimpleName());
    throw ex;
}
~~~

Do not print `ex.getMessage()` or full stack traces to broadly accessible logs without verifying that components cannot include recipients, server addresses, tokens, or MIME data. When deep diagnosis is needed, use access-controlled logs and sensitive-data filtering workflows.

### 12.1. Disable SMTP debug modes that can leak data

In production environments, do not arbitrarily enable authentication/protocol debugging:

~~~yaml
spring:
  mail:
    properties:
      mail.debug: false
      mail.debug.auth: false
~~~

When Jakarta Mail debug or `Session.setDebug(true)` is enabled, protocol logs can expose email metadata, SMTP commands, or sensitive info depending on version and configuration. In particular, auth-debugging options should never be enabled in production.

If logging must be turned on for investigation:

1. Do so only briefly, with formal approval.
2. Use a test account whenever possible.
3. Control where logs are stored and who can read them.
4. Never log credentials, tokens, or real email bodies.
5. Turn it back off after investigation and verify retention of collected data.

### 12.2. Exception chains can also carry secrets

`MailSendException` can contain nested causes from Jakarta Mail/SMTP transport. Even if the top-level message is generic, inner causes may contain recipient addresses, hostnames, or server response details.

When persisting errors in an outbox, use a classifier:

~~~java
public record SafeMailError(
        String errorCode,
        String errorType,
        String safeSummary) {
}

SafeMailError error = new SafeMailError(
        "SMTP_AUTH_FAILED",
        exception.getClass().getSimpleName(),
        "SMTP authentication was rejected");
~~~

Do not store raw `Throwable` objects or serialize `MailException` directly into JSON. For metrics, use only standardized `errorCode` values—never exception messages or passwords as labels.

## 13. Protecting Actuator, diagnostic endpoints, and config dumps

Spring Boot Actuator can expose configuration diagnostics via endpoints like `/actuator/env` and `/actuator/configprops` when enabled. These endpoints are useful operationally, yet can reveal property names and, if misconfigured, sensitive values.

A cautious configuration:

~~~yaml
management:
  endpoints:
    web:
      exposure:
        include: "health,info"
  endpoint:
    env:
      show-values: never
    configprops:
      show-values: never
~~~

In Spring Boot versions supporting `show-values`, `never` suppresses property values on those endpoints. The `exposure.include` setting here also avoids exposing `env` or `configprops` over the web.

Do not treat sanitization as the sole defense. You still need to:

- Enable only necessary management endpoints.
- Protect endpoints with authentication/authorization and network restrictions.
- Never publicly expose `/env`, `/configprops`, or debug endpoints arbitrarily.
- Never build a “show current mail config” API returning an object with a password.
- Restrict access to thread dumps, heap dumps, process diagnostics, and support bundles.

Exact properties and Actuator defaults can differ across Spring Boot versions; apply management configurations aligned with environment policy rather than assuming secrets will always be masked by every tool.

### 13.1. Do not expose `@ConfigurationProperties` containing passwords

If the application defines its own config class:

~~~java
@ConfigurationProperties(prefix = "app.smtp")
public class SmtpSettings {
    private String username;
    private String password;

    // Getters/setters omitted.
}
~~~

Never put this object into API responses, metrics, or logs. If using Lombok `@Data` or Java records, beware that `toString()` may print the password. Design configuration objects so `toString` excludes secrets, or explicitly redact fields when diagnosing.

In standard Spring Boot applications, there is no need to define a duplicate copy of credentials if `spring.mail.username` and `spring.mail.password` are already used by auto-configuration. Reducing where secrets are stored/copied reduces leak surface.

## 14. Checking for missing credentials and failing fast

An application requiring authenticated SMTP sending should not boot into production with an empty username or password only to discover it when sending the first email.

With environment placeholders or mandatory config trees, missing configuration sources can be caught at startup. If an explicit policy check is needed, add a dedicated guard for the production profile:

~~~java
package com.example.mail;

import org.springframework.boot.ApplicationRunner;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.Profile;
import org.springframework.core.env.Environment;

@Configuration
@Profile("prod")
public class MailCredentialGuardConfig {

    @Bean
    ApplicationRunner validateSmtpCredentials(
            Environment environment) {

        return args -> {
            String username =
                    environment.getProperty("spring.mail.username");
            String password =
                    environment.getProperty("spring.mail.password");

            if (username == null || username.isBlank()
                    || password == null || password.isBlank()) {
                // Do not include secret values in the exception message.
                throw new IllegalStateException(
                        "Required SMTP authentication is not configured");
            }
        };
    }
}
~~~

Here the guard checks only presence; **it does not log credentials** and does not prove the credentials are valid or that the server is reachable. The guard assumes the `prod` profile requires an SMTP username/password. If using OAuth2 or another mechanism, replace the check with the corresponding credential policy.

If testing SMTP connectivity during startup/health checks, understand that connecting to the provider can couple deployment to network availability or quotas. Do not send real emails solely to test configuration on every startup. Design readiness/health checks around SLA requirements and provider capabilities without leaking auth details in responses.

### 14.1. Empty passwords differ from wrong passwords

Distinguish between:

| Scenario | How to recognize | Action |
| --- | --- | --- |
| Missing secret source | Config import/placeholder fails to resolve | Fail startup or alert deployment |
| Blank password | Application validation | Fail fast, do not attempt SMTP |
| Username/password mismatch | SMTP returns auth error | Report config error; check secret version |
| Secret revoked | SMTP auth suddenly fails after previously working | Check rotation/revocation |
| TLS failure | Cannot verify TLS endpoint | Check cert/CA/hostname; never disable validation |
| SMTP provider outage | Connection timeout or temporary reply | Retry/backoff per policy |

Do not lump everything under an `invalid password` message: TLS, DNS, network, or provider outages are not always credential issues.

## 15. Rotating SMTP credentials

No secret should be assumed to live forever. Credentials may need replacement due to security policy, staff changes, suspected exposure, or provider requirements.

**Rotation** is the process of replacing an old credential with a new one while minimizing mail-sending disruption.

### 15.1. Prepared rotation workflow

If the provider allows two credentials to coexist:

1. Create the new credential with the appropriate account/permissions.
2. Store the new version in the secret manager or environment secret store.
3. Update the deployed version/key reference; never print the value to terminals/logs.
4. Trigger workload reload or rolling restart so `JavaMailSender` picks up the new credential.
5. Verify authentication and send a **test email to an SMTP sink or authorized test recipient**.
6. Monitor auth error rates, queue/outbox state, and failed attempts.
7. Revoke the old credential once all workloads are confirmed on the new version.
8. Record audit logs: who performed it, when, version switched, and revocation confirmation.

If the provider supports only one credential at a time, plan a cutover and accept a brief interruption window. Apply backoff/retries for temporarily failed emails instead of dropping them.

### 15.2. Rotation does not mean updating a file is enough

A Java application may hold a password in a configuration object or mail sender for the entire process lifetime. Thus:

~~~text
Secret manager rotates credential
              |
              v
Runtime mount / environment updated
              |
              v
Does JavaMailSender use new value?
              |
       +------+------+
       |             |
       v             v
     Yes          No / unknown
       |             |
       v             v
 Validate         Reload bean /
 SMTP auth        rolling restart
~~~

Do not assume a secret updated merely because a mounted file changed. When using environment variables, processes usually snapshot values at launch and need a restart/redeploy. When using secret files with framework refresh mechanisms, specifically verify whether the SMTP bean and open connections actually adopt the new credential.

### 15.3. OAuth token rotation

OAuth access tokens are short-lived; token renewal must happen before expiration following the proper flow/provider. If a refresh token or client secret used to obtain access tokens is exposed, revoke that credential and assess the scope of issued tokens.

Never cache access tokens indefinitely in a `static final String` or log tokens for debugging. When using OAuth2 with SMTP, configure the proper SASL/XOAUTH2 mechanism and permissions per provider; never treat an access token as a permanent password.

### 15.4. Do not retry continuously on rotation errors

If the old credential is revoked before the application reloads, SMTP may return authentication errors for batches of emails. Retrying immediately with the same credential achieves nothing and can trigger provider anti-abuse blocks.

The system should:

- Classify `MailAuthenticationException` as a configuration/authorization incident.
- Alert operators.
- Pause or apply sensible backoff for attempts sharing the same cause.
- Never mark rejected messages as `SENT`.
- Once credentials are updated, redrive still-valid deliveries per policy.

## 16. Handling an exposed SMTP secret

Suppose a real SMTP password was committed to a repository or appeared in build logs. Do not just “delete the secret line” and consider the incident closed: the credential may already have been copied.

A typical incident response process:

| Phase | Action |
| --- | --- |
| **Contain** | Revoke/disable the exposed credential as fast as operational policy allows; issue a new credential via a safe channel |
| **Assess** | Determine exposure scope across repositories, logs, artifacts, images, CI runners, and who had access |
| **Recover** | Update the runtime secret, restart/reload the application, and confirm mail sending works |
| **Investigate** | Inspect SMTP/provider audit logs, unusual email volumes, quota changes, and signs of abuse |
| **Clean up** | Remove the secret from remaining controlled sources/artifacts/logs; handle history/backups per approved procedures |
| **Prevent** | Add secret scanning, permission separation, debug controls, and improved credential provisioning |

When exposure is suspected, **rotation/revocation must take priority over merely rewriting Git history**. Rewriting history does not revoke the old credential from clones, caches, or logs already created.

### 16.1. When credentials leak through logs

Beyond revocation:

- Determine the timeframe when sensitive logs were collected.
- Check which users/roles can read those logs.
- Restrict or purge affected log entries per retention and investigation policies.
- Verify no pipelines, collectors, or dashboards continue emitting sensitive fields.
- Never copy the exposed credential into tickets/chat to “save evidence”; reference incident IDs and protected evidence locations.

Sometimes logs also contain recipient names and email bodies; incident scoping must account for personal data, not just passwords.

### 16.2. Secrets exposed inside a Docker image

If an image already contains a password file, fixing the Dockerfile only affects future builds. You must:

1. Revoke the old credential.
2. Build/publish a clean image.
3. Replace running workloads with the clean image.
4. Control access and retention for registries/caches/artifacts holding the old image.
5. Check whether older deployments are still running or backed up.

Do not expect changing `ENV` at deploy time to make a secret disappear from earlier image layers.

## 17. Local and test environments without production secrets

Most template and MIME development does not require sending real mail. You can use a local SMTP sink such as Mailpit or MailHog so the application delivers emails into a test mailbox instead of a production provider.

Example `application-local.yml`:

~~~yaml
spring:
  mail:
    host: 127.0.0.1
    port: 1025
    properties:
      mail.smtp.auth: false
~~~

This is an example for a **local SMTP sink bound only on loopback and requiring no authentication**. Never carry `auth: false` and no-TLS configurations to production SMTP over public networks. If the sink runs in another container, adjust host/port according to your test network and isolation policies.

Goals:

- Render HTML/plain-text emails and inspect MIME without consuming real mail quotas.
- Avoid handing out real SMTP passwords to every developer.
- Run tests easily with dummy recipients.
- Prevent accidentally sending test notifications to customers.

### 17.1. Where should local secrets be stored?

If you must test against real SMTP in an authorized environment:

- Use a dedicated developer/test credential with restricted quota and scope.
- Store it using an organization-approved tool: password manager, keychain, or local-dev secret store.
- Never commit `.env`, `application-local.yml` containing real values, or shell scripts setting passwords.
- Avoid putting credentials into shell command history when safer config channels exist.
- Delete or revoke test credentials when no longer needed.

**Spring Boot does not automatically turn every `.env` file into a configuration source merely because it is named `.env`.** Tools like Docker Compose or a shell may load it, but how values reach the process must be explicitly configured per environment.

### 17.2. A mock setup for unit tests

For unit testing services calling `JavaMailSender`, use mocks/fakes:

~~~java
@Test
void sendNoticeBuildsExpectedMessage() {
    JavaMailSender mailSender = mock(JavaMailSender.class);
    MimeMessage message =
            new MimeMessage(Session.getInstance(new Properties()));

    when(mailSender.createMimeMessage()).thenReturn(message);

    NotificationMailer service = new NotificationMailer(mailSender);
    service.send("recipient@example.invalid", "Test notification");

    verify(mailSender).send(any(MimeMessage.class));
}
~~~

This example uses JUnit 5/Mockito and assumes `NotificationMailer` exposes the corresponding API. The test requires no real SMTP password and opens no network connection. To verify actual MIME creation, inspect the constructed Jakarta Mail message or send to an SMTP sink in an integration test.

The domain `example.invalid` in the example is a placeholder address; avoid using real customer emails in tests whenever unnecessary.

## 18. Verifying the safety of secret provisioning

Configuration tests should focus on observable behaviors:

### 18.1. Testing without production secrets

Under the `prod` profile, omit the mounted password source or expected environment variable:

1. The application must refuse to start if mandatory credentials are missing.
2. Error messages must not print password values.
3. No automatic fallback to a hard-coded secret.
4. Never enable an unauthenticated/no-TLS SMTP mode just to bypass the error.

No real email needs to be sent to verify the application reacts properly to missing configuration.

### 18.2. Testing resolved secret sources

In an isolated test environment, supply a dummy string with no real sending permissions from a file or environment variable and verify the mail sender config reads the right property. Never log the dummy string through the same code path production will use for real secrets.

When asserting configuration objects in tests, compare values strictly in memory within test scope without dumping them into test reports or public serialized snapshots.

### 18.3. Testing that logs do not emit secrets

A useful test is supplying a **fake sentinel credential**, triggering an error branch (such as a mail authentication failure), and asserting that configured logs do not contain the sentinel. This check helps catch accidental password logging, though it does not prove the entire system has no other leak paths.

Never run security logging tests with real secrets just to see if they get logged.

### 18.4. Testing that TLS failures fail closed

Against a test endpoint with an untrusted certificate or missing STARTTLS support, confirm the client fails per policy rather than silently sending credentials over an unprotected connection. Never disable hostname verification/truststore checks just to make tests “green”.

### 18.5. Testing after rotation

In a controlled environment:

- New secret is provisioned to the workload.
- Application reloads/restarts per design.
- SMTP authentication with the new credential works.
- Revoked old credential can no longer be used.
- Pending deliveries are not marked `SENT` when authentication fails.
- Jobs can retry with the new credential without losing state.

With multiple instances, test a rolling restart to catch instances still clinging to old credentials.

## 19. Common issues and how to handle them

| Symptom | Possible cause | Remediation |
| --- | --- | --- |
| Production fails to resolve `SMTP_PASSWORD` | Variable not injected or wrong variable name | Check secret injection, key name, and environment without printing values |
| Config tree file not read | Wrong mount path, missing file, lacking process permissions | Verify path, ACLs, read-only mount, and filename |
| Password right in secret manager, yet SMTP auth still fails | Bean read older version or env var overrides new value | Check precedence and reload/restart |
| After rotation a few Pods still fail auth | Rolling deploy incomplete or instance holds old credential | Identify Pod/version, finish rollout, revoke old credential on schedule |
| SMTP sends locally but fails in production | Wrong host/port/TLS policy, network, or unpermitted account | Check network, TLS handshake, quota, and auth per environment |
| JavaMailSender does not authenticate | Missing `mail.smtp.auth=true` or credential unbound | Check SMTP policy and config source |
| TLS reports certificate/hostname error | Certificate chain/CA or hostname mismatch | Fix truststore/cert/hostname; never use wildcard trust |
| Secret appears in build logs | Script prints environment or command tracing enabled | Disable sensitive log streams, revoke/rotate, audit log scope |
| Secret appears in image | `ARG/ENV` or `COPY` of secret file during build | Revoke/rotate, rebuild clean image, clean up old artifacts |
| `/actuator/env` publicly accessible | Endpoint exposed with weak protection | Restrict exposure, authz, network, and show-values |
| Emails fail after credential change | SMTP account revoked, not reloaded, provider limits | Check version, error category, and apply backoff |
| Local secret accidentally pushed to Git | File unignored or force-added | Revoke, clean repository/history per procedure |
| SMTP logs too verbose | Protocol/auth debug left on in production | Disable debug, protect and process collected logs |
| Mistaking Base64 for secret protection | Using encoding instead of encryption/secret store | Move to secret management and least privilege |

### 19.1. Beware of property source precedence

Spring Boot supports multiple configuration sources: profile-specific application files, environment variables, command-line args, config imports, and other integrations. A property can be defined in several places, and a higher-precedence source can **override** the value from a secret store.

Example:

~~~text
Mounted config tree provides spring.mail.password
          |
          v
An old environment variable SPRING_MAIL_PASSWORD also exists
          |
          v
Actual value depends on property-source precedence
~~~

When rotating a secret yet SMTP keeps authenticating with the old version, check the **configuration path**, property names, and override sources. Never print the resolved password value to logs to see which source won. You may temporarily emit diagnostics logging only **source/property names** under access control, never secret contents.

Pick one official secret source for production and avoid ad-hoc overrides via command-line arguments. Keeping conventions clear matters more than trying to “hide” passwords behind layered placeholders.

### 19.2. Secret leaks via toString, exceptions, or serialization

Beyond directly printing passwords, indirect leak paths exist:

~~~java
record MailSettings(String username, String password) {
}

MailSettings settings =
        new MailSettings("mailer@example.net", "dummy-value");

// Do not do this with real settings:
log.debug("settings={}", settings);
~~~

Java records auto-generate `toString()` including all components, so the example above would print the password. Likewise, Lombok `@Data` typically generates `toString()`. If such structures must be used, explicitly exclude secrets from output or never log the object.

Avoid placing secrets in response DTOs, cache keys, exception messages, or serialized debugging events. A property read from a vault **remains a secret** once inside a Java object.

## 20. Frequently asked questions

**“Is putting the password in application.properties and adding it to .gitignore enough?”**  
No. If the file was ever committed, it remains in Git history and copies. If packaged into the JAR, the password travels with the artifact. Configure via environment, runtime mounts, or a secret manager instead.

**“Can I hard-code the password and Base64-encode it?”**  
No. Base64 only changes representation and is trivially decoded. Encrypting with a key hard-coded inside the application also fails to solve how the key itself is kept secret.

**“Are environment variables considered completely secure?”**  
No. They avoid committing into source, yet can be read by users with host/container privileges, diagnostic tools, or log pipelines. Enforce access controls and harden environments.

**“Why use config trees if environment variables already exist?”**  
Config trees allow distributing secrets via mounted files, enforcing filesystem permissions, and separating contents from images/environments where supported by the platform. Not every app strictly needs them, but they are a solid option for production containers.

**“Are Kubernetes Secrets already encrypted?”**  
The `data` field uses Base64, not encryption. Actual protection also depends on cluster encryption at rest, RBAC, node permissions, backups, and provisioning workflows.

**“Should SMTP usernames be stored in Git?”**  
A username does not always grant standalone access, yet it can reveal sending accounts/infrastructure. Often it is best configured outside source if organizational policy treats it as sensitive operational data.

**“Should I use an app password instead of the primary password?”**  
If supported by the provider, a dedicated app password helps limit blast radius and simplifies revocation. Still, it must be managed like a real secret.

**“Does OAuth2 eliminate the need for secret management?”**  
No. Access tokens are secrets; refresh tokens, client secrets, or identities used to fetch tokens also need protection. OAuth2 supports short-lived tokens and scoping, yet does not automatically guarantee safe logging and storage.

**“Is port 587 always secure because it has STARTTLS?”**  
No. You must require STARTTLS, verify certificates/hostnames, and ensure provider support. Choosing port 587 alone is not enough.

**“Do ports 465 and 587 differ in how secrets are used?”**  
Both require protecting credentials. Port 465 typically uses TLS from connection start; port 587 typically uses STARTTLS to upgrade. Configuration must match the endpoint.

**“Can I set mail.smtp.ssl.trust=* to quickly fix TLS errors?”**  
No. Broad trust weakens server authentication. Fix the certificate chain/truststore and hostname properly instead.

**“Should mail.debug be enabled when production fails?”**  
Only under controlled diagnostic conditions with time bounds and clear log protection policies. Never enable auth debugging or print credentials. Prefer categorized error logs and correlation IDs.

**“If debug is turned off, are secrets guaranteed not to appear in logs?”**  
No such guarantee exists. Application code, frameworks, exception chains, and pipelines can still log secrets by mistake. Apply defense in depth and test sensitive log paths.

**“Can I expose /actuator/env to verify the password was loaded?”**  
Never rely on inspecting password values in diagnostic endpoints. Restrict endpoints, require proper authorization, and verify config status via signals that do not expose secrets.

**“During rotation, will a new secret file make JavaMailSender automatically use the new password?”**  
Not guaranteed. The bean may have read the value at startup. Reload/restart per design and verify authentication with the new credential.

**“If SMTP_PASSWORD is missing, can the app use a default value?”**  
Never use hard-coded default passwords in production. If mandatory config is missing, fail fast; if local environments do not send real mail, use a dedicated SMTP sink profile.

**“Should the app send a real email on every startup to test the secret?”**  
Unnecessary in many apps, and can cause spam/quota usage or couple startup to provider availability. Use configuration validation, appropriate health policies, and separate integration tests.

**“After discovering a secret was committed, is deleting the commit enough?”**  
No. The secret may already live in clones, caches, CI logs, or images. Revocation/rotation is the critical first step; then handle data and copies per incident response.

## 21. Checklist for securing SMTP secrets

When taking Spring Framework Mail to production, review these areas:

### Configuration sources

1. Passwords/app passwords/tokens are absent from source code, committed config files, and test fixtures.
2. Secrets are provisioned via a controlled runtime source: environment, mounted files, or secret manager.
3. No hard-coded fallback secrets in `${NAME:default}`.
4. Secret sources are scoped by environment and workload.
5. Production credentials are never shared with local/staging.
6. No stale property source accidentally overrides new secrets.

### Network and SMTP

7. Choose the right TLS mode for the endpoint: mandatory STARTTLS or implicit TLS.
8. Verify certificates/hostnames; never use uncontrolled wildcard trust.
9. Transmit credentials only over connections meeting TLS policy.
10. Configure SMTP timeouts and error handling to prevent threads hanging indefinitely.

### Build, deploy, and operations

11. Docker/JAR artifacts contain no SMTP passwords.
12. CI/CD never prints secret values or passes them via easily observable command lines.
13. Actuator/diagnostic endpoints are exposed only under least privilege.
14. SMTP debug/auth debug are never arbitrarily enabled in production.
15. Logs and metrics contain no recipients/tokens/passwords or raw config objects.
16. A reload/restart plan exists for credential rotation.
17. Access to secrets and version changes are audited by user/role.
18. A revocation/rotation procedure exists for exposed credentials.

### Application and testing

19. Missing mandatory SMTP config fails fast rather than silently falling back to a default password.
20. Local/unit tests use an SMTP sink, fake sender, or dedicated test credentials.
21. Post-rotation auth failures are not hammered by rapid retries with the old password.
22. Unsent emails preserve proper state to retry after config is fixed.
23. Secrets are never printed in exceptions, support tickets, or public error payloads.
24. Tests verify the app does not consume production secret sources in local profiles.

## 22. Secure architecture pattern

~~~text
                       Source repository
                              |
                              | no SMTP secret
                              v
                          CI / build
                              |
                              | immutable JAR / image
                              v
                      Runtime deployment
                              |
          +-------------------+------------------+
          |                                      |
          v                                      v
   Workload identity                       Mail properties
          |                               - host / port
          v                               - TLS / timeout
   Secret manager                          - no password
          |
          v
   Protected secret delivery
     (file mount / controlled environment)
          |
          v
   Spring Boot configuration binding
          |
          v
   JavaMailSender + TLS verification
          |
          v
   SMTP server / provider
          |
          v
   Success or classified error
          |
          v
   Outbox status / retry / safe metrics
~~~

In this model, credentials never enter source, build outputs, or dashboards. The runtime is authorized to read only the exact secret needed, Spring Mail sends over an appropriate TLS channel, and monitoring receives only standardized error codes and statuses.

## Conclusion

**Protecting secrets in SMTP configuration** is more than moving `spring.mail.password` to an environment variable. A complete solution covers the entire credential lifecycle: provisioning, runtime distribution, TLS-protected usage, read-access restriction, preventing leaks via logs/Actuator/CI/images, rotation, and incident response.

With Spring Framework Mail, the right approach is typically: **keep host/port/TLS policies in non-secret config; supply usernames/passwords or tokens via a managed runtime source; enforce TLS and server verification; never print secrets on any logging path; and maintain clear rotation/revocation procedures**. Those principles both reduce credential exposure risk and keep the email-sending service operable when credentials expire, rotate, or require emergency revocation.
