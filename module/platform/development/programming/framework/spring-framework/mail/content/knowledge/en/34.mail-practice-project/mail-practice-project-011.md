# Configuring TLS and Secrets per Profile

## 1. Practice Problem: One Spring Boot App, Multiple SMTP Environments

In a **Spring Framework Mail** project, an application typically needs to send emails across multiple environments:

- **Local/development:** developers want to inspect emails in an SMTP sink such as Mailpit without sending emails over the Internet.
- **Test/CI:** tests must be reproducible, never use production SMTP accounts, and never depend on external networks.
- **Staging:** connects to real SMTP or a dedicated provider test environment to verify TLS, authentication, sender identity, and limits.
- **Production:** protects credentials, enforces TLS properly, controls access, and supports operational rotation.

A dangerous approach is storing a single configuration:

~~~yaml
spring:
  mail:
    host: smtp.example.net
    port: 587
    username: my-production-account
    password: actual-production-password
~~~

inside the repository and reusing it across all environments. This can expose secrets, accidentally send real emails during tests, and fail to prove encrypted transport. It is equally dangerous if development disables TLS to connect to an SMTP sink and that configuration reaches production.

The solution is **separating configuration by Spring profile**, keeping **non-secret values** in version-controlled files while supplying **secrets** at runtime through a proper secret management mechanism. Security-sensitive environments must enforce TLS **fail closed**, meaning they never silently downgrade to plaintext when TLS cannot be negotiated.

Goals of this practice lesson:

1. Configure `spring-boot-starter-mail` and `JavaMailSender` using `local`, `staging`, and `prod` profiles.
2. Point `local` to an SMTP sink with no passwords and no real accounts.
3. Configure `staging`/`prod` to use STARTTLS on submission port 587 with **required** TLS and hostname/certificate verification.
4. Know when to use implicit TLS/SMTPS on port 465 and avoid mixing 465/587 settings.
5. Pass SMTP username/password via environment variables or secret mounts/secret managers rather than hardcoding in Git.
6. Write a sample mail service, test it, and inspect the effective configuration.
7. Handle handshake errors, authentication failures, profile precedence, rotation, and secret leakage.

> **Scope:** This lesson covers client-side SMTP mail configuration. It does not set up SPF, DKIM, or DMARC, configure a mail server, guarantee inbox delivery, or replace production bounce/retry handling.

## 2. Understanding Security Layers Before Configuring

The mail flow can involve:

~~~text
Spring Boot application
      |
      | JavaMailSender / Jakarta Mail
      v
SMTP submission endpoint
      |
      | provider's relay network
      v
Recipient mail server
      |
      v
Recipient mailbox/client
~~~

TLS in `JavaMailSender` protects **the connection between the application and the SMTP submission endpoint**. It does not guarantee end-to-end encryption across every downstream relay to the recipient's device.

### 2.1. SMTP STARTTLS vs. SMTPS

| Connection Mode | Common Port | Connection Start | TLS Setup | Jakarta Mail Property |
| --- | --- | --- | --- | --- |
| SMTP + STARTTLS | 587 | Plaintext SMTP connection for negotiation | `STARTTLS` command upgrades to TLS before auth/data | `mail.smtp.starttls.enable=true` and `mail.smtp.starttls.required=true` |
| SMTP implicit TLS / SMTPS | 465 | TLS handshake immediately on connect | TLS established before any SMTP exchange | `mail.smtp.ssl.enable=true` with protocol `smtp` |
| Plaintext SMTP for local sink | 1025, tool-dependent | Plaintext SMTP in an isolated environment | No TLS | Disable auth/STARTTLS only in the local profile |
| SMTP port 25 | 25 | Typically server-to-server mail exchange | Depends on purpose and config | Not used by default for client submission |

These ports are **common conventions**, not substitutes for your SMTP provider's documentation. Some systems use different ports. What matters is matching the **TLS mechanism** the server provides.

### 2.2. STARTTLS Must Be Required, Not Merely Enabled

In Jakarta Mail:

~~~properties
mail.smtp.starttls.enable=true
~~~

allows using STARTTLS if the server advertises it. However, enabling this flag alone **does not guarantee** the connection fails if the server does not advertise STARTTLS. Where encryption is mandatory, also add:

~~~properties
mail.smtp.starttls.required=true
~~~

so the client never silently falls back to plaintext SMTP when TLS cannot be negotiated.

### 2.3. Checking Hostname on the Certificate

Add:

~~~properties
mail.smtp.ssl.checkserveridentity=true
~~~

to require verifying that the server identity matches the hostname in the TLS certificate. A trusted CA chain alone is not enough; you must also verify you connected to the **exact** requested server.

Never use these "quick fixes" in production:

~~~properties
mail.smtp.ssl.trust=*
mail.smtp.ssl.checkserveridentity=false
~~~

Trust-all or disabling hostname verification defeats essential parts of TLS authentication and increases man-in-the-middle risk. When certificate or hostname checks fail, fix the endpoint, DNS, certificate chain, or managed truststore instead of turning checks off.

### 2.4. SMTP AUTH Does Not Replace TLS

`mail.smtp.auth=true` requires SMTP authentication, but **AUTH does not mean the transport is encrypted**. A misconfigured server can allow AUTH over an unprotected connection. You need all of:

~~~text
Correct host
    +
TLS required
    +
Certificate and hostname verification
    +
Authentication if provider requires it
    +
Authorized sender identity
~~~

Username and password are secrets for authenticating to the relay, not a mechanism encrypting content across subsequent hops. For providers supporting OAuth2, the secret may be a token or client credential rather than a password; the same protection principles apply.

## 3. Sample Spring Boot Project Structure

The examples use Java 17+, Spring Boot 3.x, and Jakarta Mail via the Spring Boot Mail starter:

~~~text
mail-profile-lab/
├── pom.xml
├── compose.yaml
├── src/
│   ├── main/
│   │   ├── java/com/example/mail/
│   │   │   ├── MailProfileLabApplication.java
│   │   │   ├── MailDemoService.java
│   │   │   ├── MailIdentityProperties.java
│   │   │   └── MailTlsConfigurationGuard.java
│   │   └── resources/
│   │       ├── application.yml
│   │       ├── application-local.yml
│   │       ├── application-staging.yml
│   │       └── application-prod.yml
│   └── test/
│       └── java/com/example/mail/
│           └── MailProfileConfigurationTest.java
└── .gitignore
~~~

File and package names are illustrative. With Gradle, use equivalent dependencies instead of Maven.

### 3.1. Dependencies

In Maven `pom.xml` (assuming the project uses Spring Boot parent/BOM for version management):

~~~xml
<dependencies>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-mail</artifactId>
    </dependency>

    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-validation</artifactId>
    </dependency>

    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-test</artifactId>
        <scope>test</scope>
    </dependency>
</dependencies>
~~~

`spring-boot-starter-mail` brings in auto-configuration for `JavaMailSender` and required Jakarta Mail libraries when configured appropriately. You do not need to instantiate `JavaMailSenderImpl` manually if you have one SMTP sender per active profile.

With Gradle:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-mail'
    implementation 'org.springframework.boot:spring-boot-starter-validation'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}
~~~

The Gradle snippet assumes the project already configures the Spring Boot plugin/dependency management. Never put passwords or tokens in `pom.xml`, `build.gradle`, or build command lines.

### 3.2. Main Application

~~~java
package com.example.mail;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.context.properties.ConfigurationPropertiesScan;

@SpringBootApplication
@ConfigurationPropertiesScan
public class MailProfileLabApplication {

    public static void main(String[] args) {
        SpringApplication.run(
                MailProfileLabApplication.class, args);
    }
}
~~~

`@ConfigurationPropertiesScan` registers configuration property records/classes in the appropriate project packages.

## 4. Spring Profiles Strategy

A simple convention:

| Profile | Mail Connection | Secret | Protection |
| --- | --- | --- | --- |
| `local` | Mailpit/MailHog/GreenMail on localhost or isolated Docker network | No password needed for local SMTP sink | Must never send to the Internet |
| `staging` | Staging SMTP account or provider test account | Dedicated staging secret with scoped rights | STARTTLS required + hostname verification |
| `prod` | Approved production SMTP account | Prod secret from runtime/secret manager | Fail-closed TLS, least privilege, rotation/audit |

**Never assume every non-`prod` profile can use plaintext.** Staging often handles production-like data/senders or connects to external infrastructure, so it must be protected accordingly.

### 4.1. How Spring Boot Loads Configuration

Suppose you have:

~~~text
application.yml
application-local.yml
application-staging.yml
application-prod.yml
~~~

`application.yml` holds shared properties. When `local` is active, Spring Boot merges shared configuration with `application-local.yml`; duplicate keys can be overridden by higher-precedence property sources.

Never place production credentials in `application.yml` and "override" them in local—a missing or misconfigured override could accidentally use production secrets.

### 4.2. Activating Profiles

Example run:

~~~bash
./mvnw spring-boot:run -Dspring-boot.run.profiles=local
~~~

Or set an environment variable:

~~~bash
export SPRING_PROFILES_ACTIVE=local
./mvnw spring-boot:run
~~~

On Windows PowerShell:

~~~powershell
$env:SPRING_PROFILES_ACTIVE = "local"
.\mvnw.cmd spring-boot:run
~~~

These commands are for development. In production, the deployment platform (container orchestrator, runtime service manager) should set the profile. Never commit an `application.yml` containing `spring.profiles.active: prod` hoping every environment overrides it properly.

### 4.3. Do Not Activate Conflicting Profiles Together

Avoid operational configurations like:

~~~text
SPRING_PROFILES_ACTIVE=local,prod
~~~

Both profiles may define `spring.mail.host`, `port`, and TLS flags; the outcome depends on load order and property precedence, risking sending to the wrong endpoint or in plaintext. Pick **one environment profile** for mail transport, or cleanly separate non-conflicting profile groups/feature profiles.

### 4.4. Do Not Treat the Default Profile as a Production Send Path

Treat **no active environment profile** as an incomplete configuration, or permit local sandbox only inside controlled development environments. A production deployment missing `SPRING_PROFILES_ACTIVE=prod` must be caught rather than silently sending through an unknown SMTP endpoint.

## 5. Shared Configuration: application.yml

Put non-secret shared settings into `src/main/resources/application.yml`:

~~~yaml
spring:
  application:
    name: mail-profile-lab

  mail:
    protocol: smtp
    default-encoding: UTF-8
    properties:
      "[mail.smtp.connectiontimeout]": "5000"
      "[mail.smtp.timeout]": "10000"
      "[mail.smtp.writetimeout]": "10000"

app:
  mail:
    from: ""
~~~

Explanation:

- `spring.mail.protocol=smtp` selects the SMTP protocol. This is standard when setting `mail.smtp.*` properties.
- `default-encoding=UTF-8` supports Vietnamese and other Unicode characters in the body and subject; when building MIME messages, still specify explicit encoding on the helper/builder where needed.
- `connectiontimeout` caps waiting to establish a TCP connection.
- `timeout` caps waiting to read SMTP responses.
- `writetimeout` caps writing data over the socket.
- `app.mail.from` is an application-defined configuration property; it is **not a built-in property** of `JavaMailSender`.

The timeout values here are **illustrative only** (in milliseconds) and must be tuned for your provider, message sizes, SLAs, and throughput. Without timeouts, network operations can hang indefinitely and tie up workers.

### 5.1. Why Put Keys in Square Brackets?

`spring.mail.properties` is a map forwarded to Jakarta Mail. In YAML, writing:

~~~yaml
properties:
  "[mail.smtp.starttls.enable]": "true"
~~~

preserves the exact key `mail.smtp.starttls.enable` when bound into `Properties`. The square brackets belong to the YAML map syntax; **the actual key Jakarta Mail receives** has no brackets.

In a `.properties` file, the equivalent is:

~~~properties
spring.mail.properties.mail.smtp.starttls.enable=true
~~~

Bracketed keys in YAML prevent misinterpreting dotted nested maps, especially when forwarding many verbatim properties to an underlying library.

### 5.2. Shared Timeouts Do Not Mean Skipping Profiles

You can keep shared timeouts as above and override them per profile when a provider requires it. However, **TLS mode, endpoint, and secrets** should be declared explicitly in each environment profile so no profile accidentally inherits an unintended security setting.

## 6. Local Profile: SMTP Sink Without Secrets

Create `src/main/resources/application-local.yml`:

~~~yaml
spring:
  mail:
    host: ${SMTP_LOCAL_HOST:127.0.0.1}
    port: ${SMTP_LOCAL_PORT:1025}
    properties:
      "[mail.smtp.auth]": "false"
      "[mail.smtp.starttls.enable]": "false"
      "[mail.smtp.starttls.required]": "false"
      "[mail.smtp.ssl.enable]": "false"

app:
  mail:
    from: "no-reply@local.test"
    send-demo-on-startup: false
~~~

In the `local` profile:

- The SMTP sink is only for inspecting mail locally, never relaying to the Internet.
- No username or password is required.
- Plaintext is acceptable here only inside an **isolated development environment**.
- `send-demo-on-startup` is a sample application property, off by default so app startup does not automatically send mail.

If your local SMTP sink does use STARTTLS, configure it to match that endpoint rather than forcing the plaintext example. Never use the `local` profile for production relays.

### 6.1. Running Mailpit via Docker Compose

Create a local `compose.yaml`:

~~~yaml
services:
  mailpit:
    image: axllent/mailpit:latest
    ports:
      - "127.0.0.1:1025:1025"
      - "127.0.0.1:8025:8025"
~~~

~~~bash
docker compose up -d mailpit
~~~

Explanation:

- `127.0.0.1:1025`: SMTP sink where JavaMailSender submits messages.
- `http://127.0.0.1:8025`: web UI to inspect captured emails.
- Binding to `127.0.0.1` avoids accidentally exposing the SMTP sink/UI on all network interfaces. Still verify firewall and workstation policies.
- The `latest` tag is convenient only for local examples; CI or reproducible setups should **pin a vetted image tag or digest**.

Never use Mailpit as a production SMTP relay. The sink accepting a message does not prove Gmail/Outlook deliverability or real provider TLS/authentication.

### 6.2. Localhost Changes If the App Runs in Another Container

If Spring Boot runs directly on the host machine, `127.0.0.1:1025` reaches the published port. If the app runs inside **another container on the same Compose network**, `127.0.0.1` points to the Spring Boot container itself, not Mailpit.

In that setup, the app container can use:

~~~text
SPRING_PROFILES_ACTIVE=local
SMTP_LOCAL_HOST=mailpit
SMTP_LOCAL_PORT=1025
~~~

`mailpit` is the service name resolved by Compose internal DNS. Never hardcode `mailpit` in the production profile or assume it exists outside the Docker network.

### 6.3. Using GreenMail or Another Fake SMTP Locally

If you need to simulate specific SMTP error replies—such as `421`, `550`, or disconnect after DATA—a programmable fake SMTP server fits better than a capture-only sink. Even then, the local profile must keep production credentials out of the test environment.

## 7. Staging Profile: Real SMTP with Required STARTTLS

Create `src/main/resources/application-staging.yml`:

~~~yaml
spring:
  mail:
    host: ${SMTP_STAGING_HOST}
    port: ${SMTP_STAGING_PORT:587}
    username: ${SMTP_STAGING_USERNAME}
    password: ${SMTP_STAGING_PASSWORD}
    properties:
      "[mail.smtp.auth]": "true"
      "[mail.smtp.starttls.enable]": "true"
      "[mail.smtp.starttls.required]": "true"
      "[mail.smtp.ssl.enable]": "false"
      "[mail.smtp.ssl.checkserveridentity]": "true"

app:
  mail:
    from: ${SMTP_STAGING_FROM}
    send-demo-on-startup: false
~~~

Placeholders for host, username, password, and sender identity have **no default values**. If the environment omits them, the deployment should fail validation.

Example environment variables:

~~~text
SPRING_PROFILES_ACTIVE=staging
SMTP_STAGING_HOST=[staging SMTP host provided by your provider]
SMTP_STAGING_PORT=587
SMTP_STAGING_USERNAME=[staging user]
SMTP_STAGING_PASSWORD=[secret, injected securely]
SMTP_STAGING_FROM=[verified staging From address]
~~~

These are **illustrative variable names**, not real credentials. Never paste real passwords into docs, source code, screenshots, or issues.

### 7.1. Why Not Share Staging and Production Accounts?

Separate accounts help:

- Limit blast radius if staging credentials leak.
- Prevent tests/CI from exhausting production quota.
- Enforce separate From identities and recipient restrictions.
- Rotate or revoke one environment without disrupting another.
- Separate test audit/logs from real customer mail.

Staging should use test recipients, allowlists, or provider sandbox mode whenever available. Never test by blasting real customers.

### 7.2. TLS Must Fail Closed in Staging

These two properties:

~~~yaml
"[mail.smtp.starttls.enable]": "true"
"[mail.smtp.starttls.required]": "true"
~~~

must be treated as a pair. If the server does not advertise STARTTLS or STARTTLS negotiation fails, the application **must not silently continue sending over plaintext**. This is especially critical before attempting SMTP AUTH.

Include `checkserveridentity=true` to verify the hostname against the certificate. If staging uses an internal server with a private CA, install the valid trust chain in the JVM/container rather than setting `mail.smtp.ssl.trust=*`.

## 8. Production Profile: Required Secrets and Fail-Closed TLS

Create `src/main/resources/application-prod.yml`:

~~~yaml
spring:
  mail:
    host: ${SMTP_PROD_HOST}
    port: ${SMTP_PROD_PORT:587}
    username: ${SMTP_PROD_USERNAME}
    password: ${SMTP_PROD_PASSWORD}
    properties:
      "[mail.smtp.auth]": "true"
      "[mail.smtp.starttls.enable]": "true"
      "[mail.smtp.starttls.required]": "true"
      "[mail.smtp.ssl.enable]": "false"
      "[mail.smtp.ssl.checkserveridentity]": "true"
      "[mail.smtp.connectiontimeout]": "5000"
      "[mail.smtp.timeout]": "15000"
      "[mail.smtp.writetimeout]": "20000"

app:
  mail:
    from: ${SMTP_PROD_FROM}
    send-demo-on-startup: false
~~~

In production:

- No default passwords; never use `:changeme`, `:password`, or dummy fallback values.
- SMTP host, username, password, and sender identity arrive through a secured runtime channel.
- STARTTLS is never "optional" when connecting to SMTP submission outside an isolated sandbox.
- Hostname verification is enabled.
- Bounded timeouts prevent workers from hanging indefinitely.
- Auto-demo sending is disabled and no public endpoint accepts arbitrary recipient addresses for test sending.

These timeouts are examples, not mandatory standards. With large attachments, high throughput, or slow providers, measure real latencies and choose appropriate timeouts and backoff.

### 8.1. Do Not Hardcode Secrets in YAML

Avoid:

~~~yaml
spring:
  mail:
    username: "prod-account"
    password: "very-secret-password"
~~~

And avoid:

~~~yaml
spring:
  mail:
    password: "cHJvZC1wYXNzd29yZA=="
~~~

Base64 is merely reversible encoding, **not encryption or a secret manager**. Git history, artifact images, CI logs, and file permissions can still leak credentials.

### 8.2. Do Not Use Production SMTP for Local Tests

Avoid:

~~~text
SPRING_PROFILES_ACTIVE=local
SPRING_MAIL_HOST=real-production-smtp.example.net
SPRING_MAIL_PASSWORD=production-secret
~~~

Environment overrides can replace profile-file values under Spring Boot's property precedence. Having the `local` profile active **does not guarantee** the final endpoint is Mailpit if unexpected `SPRING_MAIL_*` variables are injected at runtime.

Use validation, isolated CI environments, network policies, and automated tests checking the **effective sender configuration** rather than eyeballing YAML files.

### 8.3. Empty or Missing Secrets Must Fail Deployment

Good behavior:

~~~text
SMTP_PROD_PASSWORD missing
    |
    v
Configuration validation fails
    |
    v
No SMTP submission attempt
~~~

Never send unauthenticated, switch endpoints, or fall back to an old hardcoded credential just to let the service start. For critical jobs, distinguish configuration errors clearly from transient SMTP provider failures.

## 9. Port 465: Configuring Implicit TLS/SMTPS Properly

Some providers require an **immediate** TLS handshake on port 465. In that case, STARTTLS 587 and implicit TLS 465 are mutually exclusive configurations.

An **alternative** production example when the provider gives a port 465 endpoint:

~~~yaml
spring:
  mail:
    protocol: smtp
    host: ${SMTP_PROD_HOST}
    port: 465
    username: ${SMTP_PROD_USERNAME}
    password: ${SMTP_PROD_PASSWORD}
    properties:
      "[mail.smtp.auth]": "true"
      "[mail.smtp.ssl.enable]": "true"
      "[mail.smtp.ssl.checkserveridentity]": "true"
      "[mail.smtp.starttls.enable]": "false"
      "[mail.smtp.starttls.required]": "false"
      "[mail.smtp.connectiontimeout]": "5000"
      "[mail.smtp.timeout]": "15000"
      "[mail.smtp.writetimeout]": "20000"

app:
  mail:
    from: ${SMTP_PROD_FROM}
~~~

**Do not append this alongside the STARTTLS 587 config hoping both work.** Use only the mode matching the endpoint. You can create a dedicated `prod-465` profile or validated deployment-specific config, but never activate `prod` and `prod-465` together if both override the same properties.

### 9.1. Quick Reference Table

| Port | `starttls.enable` | `starttls.required` | `ssl.enable` | Meaning |
| ---: | --- | --- | --- | --- |
| 587 | true | true | false | STARTTLS required |
| 465 | false | false | true | Implicit TLS on connect |
| 1025 (local sink) | false | false | false | Isolated local plaintext |
| 587 | true | false | false | **Downgrade risk** if server omits STARTTLS |
| 465 | true | true | false | Classic mismatch: waits for SMTP greeting instead of starting TLS |
| 587 | false | false | true | Classic mismatch: starts TLS handshake against an endpoint expecting SMTP greeting |

`mail.smtp.ssl.checkserveridentity=true` should be enabled for both STARTTLS and implicit TLS in protected environments. Do not guess the TLS mode purely from the port number if your provider documents otherwise; confirm against provider docs and tests.

### 9.2. TLS Protocols and the JVM Truststore

With Java 17+, the JVM supplies its own TLS stack and truststore. When compliance requires restricting TLS protocol versions, you can consider:

~~~properties
mail.smtp.ssl.protocols=TLSv1.2 TLSv1.3
~~~

but set this only after verifying provider and JVM support and reviewing policy. Forcing an unsupported protocol causes handshake failures. Never enable legacy `SSLv3`/old TLS or disable certificate verification as a "workaround".

If an SMTP server uses an internal organizational CA, manage that CA properly in the JVM truststore, image, or runtime. Avoid passing sensitive truststore passwords on command lines where process listings or logs might capture them; use a runtime-appropriate secret mechanism.

## 10. Why Config Files with Placeholders Alone Are Not Secure Enough

Writing:

~~~yaml
password: ${SMTP_PROD_PASSWORD}
~~~

keeps **passwords out of the repository**, yet the secret must still exist when the process runs. If your delivery pipeline feeds secrets insecurely, placeholders alone do not solve the problem.

Common secret exposure paths:

| Location | Risk | Mitigation |
| --- | --- | --- |
| Git/source repository | Passwords enter commits and Git history | Never store secrets; enable secret scanning |
| `.env` files | Accidentally committed, synced, or world-readable | Gitignore, restricted local permissions |
| CI pipeline variables | Printed in build logs/debug output | Masking, scoped access, no echoing |
| Dockerfile `ARG`/`ENV` | Can leak into image layers, history, or build logs | Never bake runtime secrets into images |
| Container environment | Visible via process/container inspection | Restrict access; prefer secret mounts where appropriate |
| Kubernetes Secrets | API access and etcd/manifest exposure | RBAC, encryption at rest, external secret managers |
| Actuator `/env`, `/configprops` | Accidental exposure of config values | Lock down management endpoints, sanitize |
| Jakarta Mail debug | Leaks protocol/account/metadata | Disable debug in production |
| Exceptions/logs | Connection URLs, usernames, email content | Sanitized logging, safe error codes |

**A secret manager does not replace TLS.** A securely fetched password sent over plaintext SMTP can still leak on the wire. Likewise, TLS does not replace a secret manager: encrypted connections do not fix a password committed to Git.

## 11. Providing Secrets via Environment Variables

In `local`, no password is needed. In `staging`/`prod`, a common deployment pattern injects secrets at runtime into the environment variables referenced by YAML:

~~~yaml
spring:
  mail:
    username: ${SMTP_PROD_USERNAME}
    password: ${SMTP_PROD_PASSWORD}
~~~

A deployment must provide:

~~~text
SPRING_PROFILES_ACTIVE=prod
SMTP_PROD_HOST=<approved SMTP endpoint>
SMTP_PROD_PORT=587
SMTP_PROD_USERNAME=<secret or protected account identifier>
SMTP_PROD_PASSWORD=<injected from secret store>
SMTP_PROD_FROM=<verified sender address>
~~~

Values inside `<...>` are illustrative placeholders—**never copy them literally as credentials**. Never paste real passwords into commands/documentation or echo them to logs for verification.

### 11.1. Are Environment Variables Perfectly Safe?

No. They reduce the risk of **committing secrets to the repository**, yet host/container admin access, process inspection, crash dumps, CI logging, or misconfigured observability tools can still expose environment variables.

For stronger protection:

- Inject secrets only at runtime, never at build time.
- Restrict access to container/Pod specs and process environments.
- Use secret managers/workload identity to fetch secrets when appropriate.
- Do not share production SMTP credentials across unrelated services.
- Restrict shell history, diagnostics, and environment dumps.
- Schedule rotation/revocation and audit secret access.

### 11.2. Intentional Variable Naming

Two conventions:

~~~text
Option A:
  SMTP_PROD_PASSWORD
  application-prod.yml -> ${SMTP_PROD_PASSWORD}

Option B:
  SPRING_MAIL_PASSWORD
  Spring Boot direct relaxed binding
~~~

Either works, but pick **one clear convention**. Mixing A and B lets `SPRING_MAIL_PASSWORD` override a property bound from a profile placeholder, making effective values harder to reason about.

When debugging, inspect the **configuration source** without printing secret values. You can log active profile names and a sanitized "secret configured" boolean, never the password.

### 11.3. Do Not Rely on Committed .env Files

A local `.env` file for testing may sit on a developer's machine, but:

- Never commit it to Git.
- Never put real secrets into `.env.example`.
- Never copy it into Docker images.
- Never leave it world-readable on shared machines.
- Never keep production SMTP secrets on developer laptops unnecessarily.

Example `.gitignore`:

~~~gitignore
.env
.env.*
!.env.example
config/secrets/
*.keystore.local
~~~

`.gitignore` only prevents future commits; **it does not erase secrets already in Git history**. If credentials were committed, revoke/rotate immediately and follow history-remediation policy.

## 12. Secret File Mounts and Spring Boot Config Tree

Another option mounts secrets as **read-only files** inside containers. Spring Boot supports `configtree:` to map filenames directly to configuration properties.

Suppose runtime mounts:

~~~text
/run/secrets/smtp/
  SMTP_PROD_USERNAME
  SMTP_PROD_PASSWORD
~~~

In `application-prod.yml`, you can add:

~~~yaml
spring:
  config:
    import: "optional:configtree:/run/secrets/smtp/"
~~~

while keeping:

~~~yaml
spring:
  mail:
    username: ${SMTP_PROD_USERNAME}
    password: ${SMTP_PROD_PASSWORD}
~~~

These are **config sections to merge into one valid YAML file**; do not create two duplicate root `spring:` keys in the same document. When the mount has matching filenames, `configtree:` exposes a property source for placeholders to read.

### 12.1. Why optional:configtree?

`optional:` allows the **directory mount** to be absent when a deployment uses environment variables instead. However, `SMTP_PROD_PASSWORD` **must have no default**: if neither env nor configtree supplies the credential, binding/validation still fails before sending mail.

If production policy **mandates** secret mounts, drop `optional:` so startup fails if the directory is missing. That prevents running with a non-compliant secret source.

### 12.2. Configtree vs. Passing a File Path String

With:

~~~text
/run/secrets/smtp/SMTP_PROD_PASSWORD
~~~

`configtree:` reads the file's contents and provides property `SMTP_PROD_PASSWORD`. By contrast, if you set:

~~~text
SMTP_PROD_PASSWORD=/run/secrets/smtp/password
~~~

the placeholder receives **the literal file path string**, without automatically reading secret bytes. These are distinct mechanisms:

- **Config tree:** property is bound from file contents.
- **Custom secret loader:** application or integration code opens the file/secret manager, handling encoding and lifecycle.

Never confuse a secret file path with the password value when configuring `JavaMailSender`.

### 12.3. File Permissions and Rotation

Secret mounts should be readable only by the JVM account, not every container or user. While some secret mounts update file contents on disk, **Spring Boot/Jakarta Mail does not automatically reload passwords already bound on `JavaMailSenderImpl` in all cases**.

When rotating:

1. Create a new credential in the provider/secret manager.
2. Distribute the new version to workloads through the approved mechanism.
3. Safely restart/refresh or replace the sender bean/instance.
4. Verify connectivity/submission using the new credential.
5. Revoke the old credential once confirmed no workload uses it.

Never assume "the mounted file updated" means every running SMTP connection automatically switches credentials.

## 13. Kubernetes: Using Existing Secrets with Scoped Access

To illustrate injecting secrets into a Spring Boot Pod, suppose administrators **already created** Kubernetes Secret `smtp-prod-auth` via a secure secret workflow. A Deployment can declare:

~~~yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: mail-worker
spec:
  replicas: 2
  selector:
    matchLabels:
      app: mail-worker
  template:
    metadata:
      labels:
        app: mail-worker
    spec:
      containers:
        - name: mail-worker
          image: registry.example.com/mail-worker:<pinned-version>
          env:
            - name: SPRING_PROFILES_ACTIVE
              value: "prod"
            - name: SMTP_PROD_HOST
              valueFrom:
                configMapKeyRef:
                  name: mail-prod-endpoint
                  key: host
            - name: SMTP_PROD_PORT
              value: "587"
            - name: SMTP_PROD_FROM
              valueFrom:
                configMapKeyRef:
                  name: mail-prod-endpoint
                  key: from
            - name: SMTP_PROD_USERNAME
              valueFrom:
                secretKeyRef:
                  name: smtp-prod-auth
                  key: username
            - name: SMTP_PROD_PASSWORD
              valueFrom:
                secretKeyRef:
                  name: smtp-prod-auth
                  key: password
~~~

This is an **illustrative Deployment snippet**; replace image, namespace, resource limits, service account, network policy, pod security, and remaining fields for your cluster. No real credentials appear in the manifest.

### 13.1. What Kubernetes Secrets Do Not Guarantee Automatically

- Secret values are Base64-encoded in YAML/APIs; Base64 **is not encryption**.
- You must configure RBAC so only authorized workloads/operators can read them.
- Enable encryption of Secrets **at rest** in the control plane per cluster governance.
- Control access to Pod specs/environments, auditing, and CI/CD credentials.
- Secrets injected as process env vars do not update automatically when the Kubernetes Secret changes; a rollout/restart is usually required.
- Restrict service account permissions and avoid mounting unnecessary tokens or rights.

With a centralized secret manager, you can use a CSI driver or external-secret integration to mount/sync secrets per policy. Product names and sync behavior depend on your platform; you still must design how the app **picks up new versions** after rotation.

### 13.2. Mounting Secrets as Files Instead of Env Vars

A container option:

~~~yaml
volumeMounts:
  - name: smtp-auth
    mountPath: /run/secrets/smtp
    readOnly: true

volumes:
  - name: smtp-auth
    secret:
      secretName: smtp-prod-auth
      items:
        - key: username
          path: SMTP_PROD_USERNAME
        - key: password
          path: SMTP_PROD_PASSWORD
~~~

These blocks go under `containers[].volumeMounts` and `pod.spec.volumes` in a complete Deployment. Combined with `configtree:/run/secrets/smtp/`, filenames bind directly as properties. When using file mounts, remove duplicate env injection of the same secrets to avoid unclear precedence.

### 13.3. Network Policy

An SMTP-sending Pod typically only needs egress to:

~~~text
Approved SMTP endpoint
Approved port (587 or 465)
DNS resolver
Any required secret-management endpoints
~~~

Do not open unrestricted egress to all IPs/ports when policy requires scoping. Account for dynamic provider IPs, DNS, and proxies rather than hardcoding fragile IPs without an update plan.

## 14. Docker Compose + Secrets: Never Bake Passwords into Images

In Docker builds/Compose, avoid:

~~~dockerfile
ARG SMTP_PASSWORD
ENV SMTP_PASSWORD=$SMTP_PASSWORD
~~~

Passwords can leak through image layers, build history, metadata, or CI build logs. **Build artifacts must remain independent of deployment environment credentials.**

Deployment model:

~~~text
Build once:
  mail-worker.jar / container image (no secrets)
            |
            v
Deploy staging:
  application-staging.yml + staging secret
            |
            v
Deploy production:
  same image + application-prod.yml + prod secret
~~~

One image serves multiple environments via different property sources and secret injection; there is never a reason to rebuild an artifact with a production password inside it.

### 14.1. Docker Secrets Must Be Read Properly

In some Docker Compose/Swarm setups, secrets are mounted under `/run/secrets/<name>` and **are not automatically exported as environment variables**. Use `configtree:` or a secret loader. If the app reads `${SMTP_PROD_PASSWORD}`, verify the property source actually populates that key; merely mounting a file named `smtp_password` without mapping configuration will not bind it.

### 14.2. Never Dump the Entire Environment to Debug

Avoid:

~~~java
System.getenv().forEach((key, value) ->
        log.info("{}={}", key, value));
~~~

This can print passwords, API keys, tokens, private endpoints, and other sensitive data. When confirming profile activation, log only the **profile names** and approved metadata, never secret values.

## 15. CI/CD: Separating Build, Test, and Deployment Credentials

A well-designed pipeline never needs production SMTP passwords to compile or unit-test Java code.

~~~text
Source repository
    |
    v
CI build + unit tests
    |  no production SMTP credentials
    |
    v
Immutable artifact/image
    |
    v
Staging deployment
    |  staging secrets only
    |  approved test recipients
    v
Staging smoke tests
    |
    v
Production approval/deploy
       production workload identity/secret
~~~

### 15.1. Controls to Have

- Secret scanning on commits and pull requests.
- Never print `env`, shell commands carrying secrets, or fully resolved `application-prod.yml`.
- CI tests should talk only to fake/sink SMTP whenever possible.
- Staging secrets have separate scope and lifecycle.
- Prod deployment jobs use short-lived identities or least-privilege secret access.
- When workflows must read secrets, restrict access by branch, environment, and approvals.
- Never embed credentials in test reports, crash dumps, artifacts, or container build args.

### 15.2. Testing in CI Without Sending Real Mail

Most automated tests should verify:

1. Local profile binds the right host/port/auth settings.
2. Staging/prod profiles bind required TLS flags properly.
3. Missing-secret configurations are rejected / fail validation.
4. Mail composers build valid MIME messages.
5. Zero production SMTP calls occur from unit/integration tests.

Only authorized staging smoke tests should hit real SMTP to confirm certificates, AUTH, sender identity, and provider constraints.

## 16. Writing a Simple Mail Service to Test Profiles

The practice project should include a small service verifying `JavaMailSender` injection and sender identity. This service **does not choose the profile itself**; Spring Boot has already resolved the effective configuration at startup.

### 16.1. Application Properties

Create `MailIdentityProperties.java`:

~~~java
package com.example.mail;

import jakarta.validation.constraints.NotBlank;

import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.validation.annotation.Validated;

@Validated
@ConfigurationProperties(prefix = "app.mail")
public record MailIdentityProperties(
        @NotBlank String from) {
}
~~~

`@Validated` paired with `spring-boot-starter-validation` fails startup when `app.mail.from` is blank. This is basic validation; a production service must also ensure the sender domain belongs to identities verified with the SMTP provider.

### 16.2. Service Using SimpleMailMessage

Create `MailDemoService.java`:

~~~java
package com.example.mail;

import org.springframework.mail.SimpleMailMessage;
import org.springframework.mail.javamail.JavaMailSender;
import org.springframework.stereotype.Service;

@Service
public final class MailDemoService {

    private final JavaMailSender mailSender;
    private final MailIdentityProperties identity;

    public MailDemoService(
            JavaMailSender mailSender,
            MailIdentityProperties identity) {
        this.mailSender = mailSender;
        this.identity = identity;
    }

    public void sendTestMessage(String recipient) {
        SimpleMailMessage message = new SimpleMailMessage();
        message.setFrom(identity.from());
        message.setTo(recipient);
        message.setSubject("Spring Mail profile test");
        message.setText(
                "Hello! This is a configuration test email.");

        mailSender.send(message);
    }
}
~~~

`SimpleMailMessage` works for plain text. For HTML, CID images, or attachments, use `MimeMessage`/`MimeMessageHelper` (next section), while TLS and secret config at the `JavaMailSender` layer apply identically.

**Never expose a public HTTP endpoint taking an arbitrary `recipient` just for testing**, as it can be abused to send unwanted mail, burn quota, or distribute spam.

### 16.3. Runner Enabled Only Intentionally in Local

Create a configuration class:

~~~java
package com.example.mail;

import org.springframework.boot.ApplicationRunner;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.Profile;

@Configuration
@Profile("local")
public class LocalMailDemoConfiguration {

    @Bean
    @ConditionalOnProperty(
            prefix = "app.mail",
            name = "send-demo-on-startup",
            havingValue = "true")
    ApplicationRunner sendLocalDemo(MailDemoService service) {
        return args ->
                service.sendTestMessage("demo@local.test");
    }
}
~~~

Code sends only when **both** conditions hold:

1. Active profile is `local`.
2. `app.mail.send-demo-on-startup=true`.

In `staging`/`prod`, the bean is never created. Never ship a `CommandLineRunner` that fires test emails whenever a production deployment starts.

### 16.4. Running a Local Smoke Test

With Mailpit running:

~~~bash
SPRING_PROFILES_ACTIVE=local \
APP_MAIL_SEND_DEMO_ON_STARTUP=true \
./mvnw spring-boot:run
~~~

On Windows PowerShell:

~~~powershell
$env:SPRING_PROFILES_ACTIVE = "local"
$env:APP_MAIL_SEND_DEMO_ON_STARTUP = "true"
.\mvnw.cmd spring-boot:run
~~~

Open `http://127.0.0.1:8025` and check for a `Spring Mail profile test` email. Afterward, unset `APP_MAIL_SEND_DEMO_ON_STARTUP` or disable the flag so subsequent runs do not send automatically.

If Spring runs inside a Compose network, remember to set `SMTP_LOCAL_HOST=mailpit`. Never turn a local demo runner into a production cron job or REST endpoint.

## 17. Sending HTML and Attachments Does Not Change TLS Config

TLS and authentication live at the SMTP transport layer, whereas `MimeMessageHelper` builds the message body and attachments. There is never a reason to create a "less secure" sender for HTML.

~~~java
package com.example.mail;

import jakarta.mail.MessagingException;
import jakarta.mail.internet.MimeMessage;

import org.springframework.core.io.ClassPathResource;
import org.springframework.mail.javamail.JavaMailSender;
import org.springframework.mail.javamail.MimeMessageHelper;

public final class HtmlWelcomeComposer {

    private final JavaMailSender sender;

    public HtmlWelcomeComposer(JavaMailSender sender) {
        this.sender = sender;
    }

    public void send(
            String from,
            String recipient) throws MessagingException {

        MimeMessage message = sender.createMimeMessage();
        MimeMessageHelper helper = new MimeMessageHelper(
                message,
                MimeMessageHelper.MULTIPART_MODE_MIXED_RELATED,
                "UTF-8");

        helper.setFrom(from);
        helper.setTo(recipient);
        helper.setSubject("Welcome!");

        helper.setText(
                "Welcome to the service.",
                "<html><body>"
                    + "<h1>Welcome!</h1>"
                    + "<img src=\"cid:brandLogo\" alt=\"Company\">"
                    + "</body></html>");

        helper.addInline(
                "brandLogo",
                new ClassPathResource("mail/images/logo.png"),
                "image/png");

        sender.send(message);
    }
}
~~~

This example requires the asset `src/main/resources/mail/images/logo.png` to exist in the build artifact. `ClassPathResource` reads from JARs; never embed `C:\...`, `/opt/app/...`, or `file:///...` paths into recipient HTML.

### 17.1. Do Not Confuse SMTP TLS with Image HTTPS

An email sent over STARTTLS may contain:

~~~html
<img src="https://cdn.example.com/email/logo.png">
~~~

When opened, the mail client fetches that image over a separate HTTPS connection; that is **a completely different transaction** from SMTP STARTTLS between Spring and the relay. HTTP assets are not encrypted merely because the message used SMTP TLS.

### 17.2. Attachments Can Still Leak Even with SMTP TLS

TLS protects SMTP transport to the relay, but after the provider accepts, the email/MIME may be processed across multiple systems. When sending sensitive documents:

- Verify the recipient is accurate and authorized.
- Protect the attachment source and object storage.
- Enforce content, size, and malware controls.
- Never log raw MIME bytes or sensitive file paths.
- Consider an authenticated portal link when revocation or access control is needed.

## 18. Creating a Startup Guard for TLS Policy

Secure YAML is essential, yet **unintended property overrides** can sneak in through environment variables, profile activation, deployment flags, or secret sources. High-assurance applications can inspect the **effective JavaMailSender configuration** and refuse to start if it violates policy.

### 18.1. Example MailTlsConfigurationGuard

~~~java
package com.example.mail;

import java.util.Arrays;
import java.util.List;
import java.util.Properties;

import org.springframework.boot.ApplicationArguments;
import org.springframework.boot.ApplicationRunner;
import org.springframework.core.env.Environment;
import org.springframework.mail.javamail.JavaMailSender;
import org.springframework.mail.javamail.JavaMailSenderImpl;
import org.springframework.stereotype.Component;

@Component
public final class MailTlsConfigurationGuard
        implements ApplicationRunner {

    private final Environment environment;
    private final JavaMailSender mailSender;

    public MailTlsConfigurationGuard(
            Environment environment,
            JavaMailSender mailSender) {
        this.environment = environment;
        this.mailSender = mailSender;
    }

    @Override
    public void run(ApplicationArguments args) {
        List<String> active = Arrays.asList(
                environment.getActiveProfiles());

        int environmentProfiles = 0;
        if (active.contains("local")) {
            environmentProfiles++;
        }
        if (active.contains("staging")) {
            environmentProfiles++;
        }
        if (active.contains("prod")) {
            environmentProfiles++;
        }

        if (environmentProfiles != 1) {
            throw new IllegalStateException(
                    "Exactly one mail environment profile is required");
        }

        if (active.contains("local")) {
            return;
        }

        if (!(mailSender instanceof JavaMailSenderImpl sender)) {
            throw new IllegalStateException(
                    "Mail transport requires an approved TLS validator");
        }

        Properties p = sender.getJavaMailProperties();

        boolean starttlsEnabled = flag(
                p, "mail.smtp.starttls.enable");
        boolean starttlsRequired = flag(
                p, "mail.smtp.starttls.required");
        boolean implicitTls = flag(
                p, "mail.smtp.ssl.enable");
        boolean hostVerified = flag(
                p, "mail.smtp.ssl.checkserveridentity");

        boolean starttlsMode =
                starttlsEnabled && starttlsRequired && !implicitTls;
        boolean implicitTlsMode =
                implicitTls && !starttlsEnabled;

        if (!(starttlsMode || implicitTlsMode)) {
            throw new IllegalStateException(
                    "Approved TLS mode is required for SMTP");
        }
        if (!hostVerified) {
            throw new IllegalStateException(
                    "SMTP hostname verification must be enabled");
        }
        if ("*".equals(p.getProperty("mail.smtp.ssl.trust"))) {
            throw new IllegalStateException(
                    "Trust-all SMTP TLS configuration is forbidden");
        }

        if (blank(sender.getHost())
                || blank(sender.getUsername())
                || blank(sender.getPassword())) {
            throw new IllegalStateException(
                    "SMTP endpoint or credentials are missing");
        }
    }

    private static boolean flag(
            Properties p, String key) {
        return Boolean.parseBoolean(
                p.getProperty(key, "false"));
    }

    private static boolean blank(String value) {
        return value == null || value.isBlank();
    }
}
~~~

**Limitations of this example:**

- The guard assumes a single `JavaMailSenderImpl` from Spring Boot Mail auto-configuration. If the project wraps the sender in a proxy, uses a JNDI session, multiple provider adapters, or a custom SSL socket factory, write the validator against your real abstraction.
- The guard checks TLS mode, host verification, and credentials **in configuration**; it does not prove the live certificate or endpoint is valid before connecting.
- The guard never prints secrets or hostnames into exceptions.
- The guard does not test SMTP network reachability itself; a provider outage can still happen after startup.
- If you add another environment profile, update the policy rather than ignoring it silently.

### 18.2. Preventing Multiple Environment Profiles at Once

The code above requires exactly one of `local`, `staging`, or `prod`. This is a **practice project** policy, not a general Spring requirement. A system with extra feature profiles (`metrics`, `cloud`) can still activate them alongside, as long as two **environment mail profiles** are never active together.

### 18.3. Do Not Rely on the Guard Against All Overrides

If an attacker can alter environment variables, secrets, or application code, they can bypass in-app guards too. The guard is **defense in depth** to catch misconfiguration, not a replacement for RBAC, network policy, secret managers, and deployment testing.

### 18.4. Startup Validation vs. Health Checks

You can set `spring.mail.test-connection=true` so Spring Boot tests SMTP connectivity on startup in certain setups. However, that can stop the service from booting during a temporary provider outage—an availability/readiness trade-off that often fits poorly with a durable-outbox worker.

Distinguish:

- **Configuration validation:** host, credentials, and TLS flags are valid.
- **Transport connectivity check:** can we open a socket, negotiate TLS, and authenticate?
- **Application readiness:** can the worker serve mail flows within SLO?
- **Business delivery:** did the provider accept/deliver the message?

Never put "send a real test email" inside every startup health check; it risks duplicates, quota waste, and domain reputation harm.

## 19. Testing Profile Configurations Without Real SMTP

The first goal is verifying Spring Boot binds the expected `JavaMailSenderImpl` properties and never accidentally disables TLS in staging/prod. This **requires zero network connectivity**.

### 19.1. Unit/Integration Test of Effective Prod Properties

Example using JUnit 5 and Spring Boot Test:

~~~java
package com.example.mail;

import static org.assertj.core.api.Assertions.assertThat;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.mail.javamail.JavaMailSender;
import org.springframework.mail.javamail.JavaMailSenderImpl;
import org.springframework.test.context.ActiveProfiles;

@SpringBootTest(properties = {
    "SMTP_PROD_HOST=smtp.test.invalid",
    "SMTP_PROD_PORT=587",
    "SMTP_PROD_USERNAME=non-secret-test-user",
    "SMTP_PROD_PASSWORD=non-secret-test-value",
    "SMTP_PROD_FROM=test-sender@example.test",
    "spring.mail.test-connection=false"
})
@ActiveProfiles("prod")
class MailProdConfigurationTest {

    @Autowired
    private JavaMailSender mailSender;

    @Test
    void prodRequiresStarttlsAndHostnameVerification() {
        assertThat(mailSender)
                .isInstanceOf(JavaMailSenderImpl.class);

        JavaMailSenderImpl sender =
                (JavaMailSenderImpl) mailSender;

        assertThat(sender.getHost())
                .isEqualTo("smtp.test.invalid");
        assertThat(sender.getPort()).isEqualTo(587);

        assertThat(sender.getJavaMailProperties())
                .containsEntry(
                        "mail.smtp.auth", "true")
                .containsEntry(
                        "mail.smtp.starttls.enable", "true")
                .containsEntry(
                        "mail.smtp.starttls.required", "true")
                .containsEntry(
                        "mail.smtp.ssl.enable", "false")
                .containsEntry(
                        "mail.smtp.ssl.checkserveridentity", "true");
    }
}
~~~

`smtp.test.invalid` and the credentials here are **deliberately non-functional dummy values**, and the test never calls `send(...)`. It tests config binding, not live SMTP TLS handshakes. Never put real provider credentials into automated tests just to check property binding.

For implicit TLS 465 configurations, write a corresponding test asserting `ssl.enable=true` and `starttls.enable=false` instead of applying the STARTTLS test to port 465.

### 19.2. Testing Local Without Authentication

~~~java
@SpringBootTest(properties = {
    "spring.mail.test-connection=false",
    "app.mail.send-demo-on-startup=false"
})
@ActiveProfiles("local")
class MailLocalConfigurationTest {

    @Autowired
    JavaMailSenderImpl sender;

    @Test
    void localTargetsIsolatedSmtpSink() {
        assertThat(sender.getPort()).isEqualTo(1025);
        assertThat(sender.getJavaMailProperties())
                .containsEntry("mail.smtp.auth", "false")
                .containsEntry(
                        "mail.smtp.starttls.required", "false")
                .containsEntry(
                        "mail.smtp.ssl.enable", "false");
    }
}
~~~

This test assumes default local port 1025 with no `SMTP_LOCAL_PORT` override. If CI sets override variables, pin host/port explicitly in test properties or isolate the environment for reproducible results.

### 19.3. Testing Missing Secrets

A negative test should verify:

~~~text
active profile = prod
SMTP_PROD_HOST present
SMTP_PROD_USERNAME present
SMTP_PROD_PASSWORD absent/blank

Expected:
  application configuration fails safely,
  no SMTP connection is attempted.
~~~

If using `ApplicationContextRunner` or `SpringApplicationBuilder` to spin up an isolated context, make sure the test context **does not inherit production secrets from the CI machine**. A "missing password" test running where a password env var is present gives false results.

Never document tests as `PASS` unless you actually ran them. This lesson shows test patterns that each project must adapt to its real dependency and version setup.

### 19.4. Testing Protection Against Unsafe Overrides

Useful cases:

| Profile | Misconfigured Property | Expected Outcome |
| --- | --- | --- |
| `prod` | `mail.smtp.starttls.required=false` | Guard rejects |
| `prod` | `mail.smtp.ssl.checkserveridentity=false` | Guard rejects |
| `staging` | Blank `spring.mail.password` | Guard rejects |
| `prod` | `mail.smtp.ssl.trust=*` | Guard rejects |
| `local,prod` | Two environment profiles active | Guard rejects |
| `local` | Demo runner disabled | No automatic send |
| `prod` | `app.mail.send-demo-on-startup=true` | Local runner not created |
| `prod` | Missing sender identity | Property validation fails |
| `prod-465` (if used) | SSL off / STARTTLS on | Mode policy fails |

An in-app guard protects only part of the policy. To ensure `local` never hits production SMTP, also add **a local-endpoint allowlist/test** and govern high-precedence config sources rather than relying solely on prod's TLS policy.

## 20. Checking STARTTLS and Certificates with Diagnostic Tools

In an authorized staging environment, you can inspect the endpoint from a host with network routing similar to the application.

### 20.1. Checking STARTTLS on Port 587

Example with OpenSSL:

~~~bash
openssl s_client \
  -starttls smtp \
  -connect smtp.staging.example.net:587 \
  -servername smtp.staging.example.net \
  -verify_return_error
~~~

Replace the hostname with your real staging endpoint. This command needs no username or password to test the **TLS handshake and certificate** at the protocol level. Verification status depends on the CA truststore on the host running OpenSSL; the JVM has its own truststore and may behave differently.

Check:

- Does the server properly advertise STARTTLS?
- Does the TLS handshake succeed?
- Is the certificate unexpired with a trusted chain?
- Does the SAN/hostname match the endpoint?
- Is a proxy or corporate TLS inspector swapping certificates?
- Do negotiated protocols/ciphers comply with policy?

### 20.2. Checking Implicit TLS on Port 465

~~~bash
openssl s_client \
  -connect smtp.staging.example.net:465 \
  -servername smtp.staging.example.net \
  -verify_return_error
~~~

For implicit TLS, omit `-starttls smtp` because the client must start the TLS handshake immediately upon connect. Using the wrong mode causes timeouts, `wrong version number`, or errors reading the SMTP greeting.

### 20.3. OpenSSL Success Does Not Prove JavaMailSender Success

A TLS probe only tests part of the stack:

~~~text
Network reachability
      |
      v
TLS handshake
      |
      v
SMTP AUTH
      |
      v
MAIL FROM / RCPT TO
      |
      v
DATA / provider accepts
~~~

OpenSSL typically does not verify AUTH, sender identity, quota, or MIME payloads. `JavaMailSender` may also use a different JVM truststore, TLS protocol list, and proxy configuration. An authorized staging smoke test is still required before rollout.

### 20.4. Never Paste Passwords into Terminal Tests

Never enter commands containing real usernames or passwords into shell history or issue trackers. If a tool requires auth, use an approved credential injection flow and avoid printing transcripts containing secrets. Never turn on full protocol debugging in production just to "see if SMTP connects".

## 21. Classifying Configuration Failures by Symptom

TLS, authentication, profile, and SMTP connection errors can surface as similar Spring exceptions. **Identify the stage** before applying a fix.

| Symptom | Likely Cause | Check / Next Step |
| --- | --- | --- |
| `Could not connect to SMTP host` | Wrong host/port/DNS/firewall, service down | Confirm effective host/port and network egress |
| `Connection refused` | Nothing listening or port blocked | Check SMTP endpoint/Mailpit/local vs. container network |
| `Connection timed out` | Firewall, DNS/routing, unresponsive endpoint | Traceroute/egress policy in permitted environments |
| `STARTTLS is required but host does not support STARTTLS` | Server does not advertise STARTTLS | Confirm endpoint/port; **never turn off required in prod** |
| `Could not convert socket to TLS` | Handshake, protocol/cipher, cert, or proxy | Inspect nested cause, CA/truststore, endpoint mode |
| `PKIX path building failed` | Java does not trust certificate chain | Install proper CA/complete certificate chain |
| `No subject alternative DNS name matching` | Hostname mismatches certificate | Fix hostname/SAN; never disable verification |
| `SSLHandshakeException` | Various TLS causes | Inspect root cause and 587 vs. 465 endpoint |
| `Unsupported or unrecognized SSL message` | Mixing implicit TLS with plaintext/STARTTLS | Fix `ssl.enable`/port |
| `AuthenticationFailedException` | Wrong/expired credential, disabled account, AUTH policy | Check secret version, provider account, auth mechanism |
| `535 Authentication credentials invalid` | SMTP AUTH rejected | Rotate/reissue account; stop retrying bad password |
| `530 Must issue STARTTLS first` | AUTH or MAIL sent before TLS | Enable STARTTLS required and verify port |
| `550 Sender address rejected` | From/envelope/domain disallowed | Check verified sender identity and provider policy |
| `421 Service not available` | Provider temporarily unavailable | Backoff, rate limit, and alert per policy |
| `454 TLS not available temporarily` | Server TLS capability temporarily failing | Do not downgrade; retry boundedly |
| `spring.mail.username` null | Missing profile/secret config | Check active profile and property sources without printing value |
| Unresolved `${SMTP_PROD_PASSWORD}` placeholder | Secret not injected | Check secret mount/env key and startup validation |
| Running local yet sending real mail | Wrong property override or profile | Inspect effective host and `SPRING_MAIL_*` sources |
| CI tests fail because prod SMTP is unreachable | Tests accidentally hit real provider | Switch to local fake SMTP; never use prod creds |
| Mail accepted yet missing from inbox | Provider/recipient delivery, spam, bounce | Check SPF/DKIM/DMARC, feedback, provider logs—not just TLS |

Never "fix" things by turning every `MailException` into infinite retries. Configuration errors like wrong credentials or hostnames will not heal without changing configuration.

### 21.1. Capturing the Root Cause

`JavaMailSender` can throw `MailAuthenticationException`, `MailSendException`, or `MailPreparationException`, wrapping Jakarta Mail and TLS exceptions underneath. Trace the cause chain and stage:

~~~text
MailSendException
  -> MessagingException
     -> SSLHandshakeException
        -> ValidatorException / certificate cause
~~~

This separates:

- Certificate trust failures.
- Hostname/SAN mismatches.
- TLS protocol mismatches.
- SMTP AUTH rejections.
- Unreadable attachments before sending.
- Ambiguous submission outcomes after SMTP transport began.

Never log full stack traces to broadly accessible destinations if exceptions contain metadata or sensitive user data. Use safe error codes and correlation IDs for monitoring.

### 21.2. An SMTP Exception Does Not Always Prove Non-Delivery

If a failure occurs after all DATA is transmitted and the client loses the response, the provider may have accepted the message. Retrying blindly **risks duplicates**. A TLS timeout or socket reset is only a transport symptom; the system needs `UNKNOWN`/reconciliation per business policy instead of immediate resending.

## 22. Verifying Effective Configuration Without Leaking Secrets

When debugging a deployment, safe diagnostics to expose include:

~~~text
environmentProfile = prod
smtpMode = STARTTLS_REQUIRED
smtpPort = 587
hostnameVerification = true
smtpAuthEnabled = true
smtpSecretPresent = true
smtpSecretVersion = [approved non-secret version identifier]
~~~

You do not even need to log the hostname if infrastructure hostnames are considered sensitive. Never log:

~~~text
smtpPassword = ...
smtpAuthToken = ...
JavaMail properties dump (possibly includes sensitive data)
MimeMessage content / recipients / attachment bytes
~~~

### 22.1. Restrict Actuator

Spring Boot Actuator helps inspect app status, yet endpoints like `/env` or `/configprops` can expose configuration or metadata if misconfigured. Expose only necessary endpoints behind authentication/authorization, and never enable `show-values=always` in public production.

Properties named `password` are often masked by framework endpoints, yet **never rely solely on masking** to protect secrets; custom properties or custom log statements can still leak values.

### 22.2. Jakarta Mail Debugging and Headers

Never enable `mail.debug=true` in production without strict controls, because protocol transcripts, email addresses, capabilities, AUTH mechanisms, and more can enter logs. Even if a library obscures parts of AUTH payloads, do not treat that as permission to log everything.

If staging debugging is required, enable it briefly using test accounts/recipients and store logs under tight retention.

## 23. Secret Rotation and Maintaining Availability

App passwords, SMTP passwords, or OAuth credentials may rotate on a schedule, after a leak, or due to provider policy changes.

### 23.1. Controlled Rotation Workflow

~~~text
Create new provider credential
           |
           v
Store new version in secret manager
           |
           v
Deploy/refresh limited canary workload
           |
           v
Confirm TLS + auth + approved sender identity
           |
           v
Roll out remaining instances
           |
           v
Monitor auth failures, queue age, send outcomes
           |
           v
Revoke old credential
           |
           v
Audit and close rotation
~~~

If the provider supports **two active credentials simultaneously** during cutover, rotation causes minimal disruption. If only one password exists at a time, plan a coordinated rolling restart or dispatch pause and notify operators.

### 23.2. Never Mutate Password Arbitrarily on a Singleton

In a multi-threaded app, never overwrite `JavaMailSenderImpl.setPassword(...)` concurrently with ongoing sends without explicit synchronization/versioning:

~~~text
Worker A starts SMTP AUTH with credential v1
Secret reload overwrites shared sender to v2
Worker B starts send with changed configuration
~~~

Refresh mechanisms must keep sender and connection settings consistent per attempt. With Spring Boot auto-configuring a single SMTP account, **a rolling restart with the new secret version** is usually safer and easier to reason about than mutating a bean in place.

### 23.3. When Rotation Fails

If the new credential fails authentication:

1. Check version, permissions, and account status without logging the password.
2. Stop aggressively retrying with the bad credential; repeated AUTH failures can lock the account.
3. Hold mail intents in the durable queue if your workflow supports it.
4. Roll back to the still-valid prior version **only if policy permits and it has not been revoked**.
5. Fix secret distribution/config, then validate with a test send.
6. Log the incident and update the runbook if assumptions proved false.

Never treat an AUTH failure like a transient network blip and retry hundreds of times per minute.

## 24. When Providers Use OAuth2 Instead of SMTP Passwords

Some providers require or prefer token-based authentication over static passwords. Profile separation still applies, though the secret becomes:

- A client credential used to fetch access tokens.
- A policy-approved refresh token.
- Workload identity linked to a token issuer.
- Short-lived tokens for SMTP AUTH XOAUTH2.

Never try to hardcode a permanent OAuth2 access token into `application-prod.yml`, because tokens expire and require lifecycle refresh.

### 24.1. Architectural Questions to Answer

1. How is the workload issued tokens?
2. Are token audience/scopes narrowly restricted to mail submission?
3. When does the token expire and how is it refreshed?
4. How is the token passed into Jakarta Mail AUTH?
5. Are existing connections affected when a token rotates?
6. Can sending pause cleanly when the identity provider is unavailable?
7. How do we log auth failures without logging access/refresh tokens?

XOAUTH2 and Jakarta Mail specifics depend on your SMTP provider's documentation and library version. Never swap a password for a token in `spring.mail.password` assuming every server negotiates the mechanism automatically.

### 24.2. OAuth2 Does Not Eliminate TLS Requirements

Whether AUTH uses a password or OAuth2, you still need:

~~~text
TLS required and host verified
    +
Authorized SMTP endpoint
    +
Token/credential scoped to sender account
    +
Safe logging and rotation
~~~

An access token is a live bearer secret during its lifetime; sending it over plaintext is a security vulnerability.

## 25. TLS and Secrets Across Multiple SMTP Providers

This practice project uses one `JavaMailSender` per profile, while larger systems may route across multiple SMTP relays or HTTP email APIs. In that case, never mutate `host`, `username`, and `password` on **a single shared sender** per email.

~~~text
Business mail service
       |
       v
Provider selector (tenant, region, category)
       |
       +--> SMTP Provider A
       |      senderA with its own TLS/auth/secret
       |
       +--> SMTP Provider B
       |      senderB with its own TLS/auth/secret
       |
       +--> HTTP API Provider C
              clientC with its own HTTPS auth
~~~

Every SMTP adapter needs:

- Valid endpoint host/port.
- Enforced TLS mode matching the provider and security policy.
- Hostname/certificate verification.
- Separate secrets per account/identity.
- Clear timeout, quota, and retry policies.
- Provider-specific feedback/bounce correlation.

**Fallback must never bypass policy**: if Provider A fails a TLS handshake, do not fall back to Provider B in a disallowed region or using an unverified From domain. And if SMTP DATA on A was sent before an ambiguous failure, **never blindly fail over** just because A timed out.

### 25.1. Never Use "Relaxed Security for Fallback"

Wrong:

~~~text
Primary A:
  STARTTLS required = true

Fallback B:
  STARTTLS required = false
  hostname check = false
~~~

A fallback provider must meet **equivalent minimum security controls**, not serve as a shortcut stripping TLS just to force messages out.

### 25.2. Secrets per Provider/Identity

A naming pattern might look like:

~~~text
SMTP_PROVIDER_A_SECRET_REF
SMTP_PROVIDER_B_SECRET_REF
~~~

which the app resolves from a trusted secret store when constructing each adapter. Never accept secret references or provider credentials from public HTTP requests. Variable names above are illustrative metadata, not real secret paths.

## 26. Observability for TLS and Secrets Without Leaking Data

Production deployments must distinguish **configuration incidents**, **transport incidents**, and **delivery submission results**. Metrics must never carry raw recipients or secrets.

### 26.1. Useful Metric Groups

| Logical Metric | Purpose |
| --- | --- |
| `mail_smtp_connection_failures_total` | Detect DNS/connect/timeout issues |
| `mail_smtp_tls_handshake_failures_total` | Track TLS issues |
| `mail_smtp_auth_failures_total` | Track credential/account failures |
| `mail_smtp_submission_outcomes_total` | Accepted, rejected, unknown |
| `mail_smtp_send_duration_seconds` | Monitor submission latency |
| `mail_outbox_oldest_due_age_seconds` | Measure real-time backlog age |
| `mail_secret_refresh_failures_total` | Detect rotation/refresh failures |
| `mail_provider_circuit_open` | Provider temporarily paused |

These metrics are **application-instrumented suggestions**, not built-in Spring Boot Mail guarantees.

### 26.2. Keep Labels Low Cardinality

Example:

~~~text
profile = staging | prod
provider = primary | secondary
stage = connect | tls | auth | data | unknown
outcome = accepted | rejected | unknown
error_code = tls_handshake | invalid_credentials | timeout
~~~

Never put raw recipient emails, passwords, tokens, subjects, or per-message UUIDs in metric labels. Those fields leak data and explode series counts.

### 26.3. Safe Structured Logs

~~~json
{
  "event": "smtp.connection.failure",
  "profile": "prod",
  "providerGroup": "transactional-primary",
  "stage": "TLS_HANDSHAKE",
  "safeErrorCode": "SMTP_TLS_HOSTNAME_MISMATCH",
  "deliveryId": "opaque-id",
  "attemptId": "opaque-id"
}
~~~

For startup failures before any delivery ID exists, log only a startup incident/correlation ID. Never fabricate a "mail failed" delivery record when no specific send intent existed.

### 26.4. Actionable Alerts

| Alert | Priority Investigation |
| --- | --- |
| TLS handshake failures spike after deploy | CA truststore, endpoint hostname, TLS mode |
| 100% SMTP AUTH failure | Secret version, disabled account, mechanism |
| Provider timeouts spike | Network, quota, socket timeouts, provider outage |
| STARTTLS capability disappears | Endpoint/proxy, server config; never downgrade |
| Mail backlog grows | Worker concurrency, provider quota, retry storm |
| Unknown outcomes spike | Timeout after DATA, state commit failure, reconciliation |
| Secret rotation failures | Secret mount/identity/RBAC, canary rollout |

Repeated TLS handshake failures across all production mail warrant an urgent page because no mail can leave, yet **never auto-disable TLS to restore traffic**.

## 27. Runbook: Production Cannot Send Due to TLS

### 27.1. Step 1 — Scope the Incident

Ask:

- How many workers/Pods are affected?
- One SMTP provider or all of them?
- Did failures begin after a deploy, certificate renewal, DNS change, or secret rotation?
- Is it STARTTLS 587 or implicit TLS 465?
- Did any jobs start SMTP DATA and land in UNKNOWN?
- Is the outbox preserving durable intents, or are requests failing directly?

### 27.2. Step 2 — Check Effective Transport Mode

~~~text
If port 587:
  mail.smtp.starttls.enable  = true
  mail.smtp.starttls.required = true
  mail.smtp.ssl.enable        = false
  mail.smtp.ssl.checkserveridentity = true

If port 465:
  mail.smtp.ssl.enable        = true
  mail.smtp.starttls.enable   = false
  mail.smtp.ssl.checkserveridentity = true
~~~

If configuration mixes port 465 with STARTTLS mode, fix the mode/port per provider documentation; never relax certificate checks.

### 27.3. Step 3 — Verify Certificates and Truststore

Inspect:

- Certificate chain, expiration, SANs, and hostname.
- DNS/SMTP relay IPs and any TLS proxy.
- The running JVM's truststore, not just a developer's laptop CA store.
- TLS versions and ciphers supported by both client and server.
- If using an internal CA, verify the right version was packaged into the image/runtime.

If the truststore needs updating, do so through controlled deployment artifacts/truststore policy. Never inject a trust-all socket factory at runtime instead of fixing configuration properly.

### 27.4. Step 4 — Fix and Canary

1. Fix the true source of config, certificate, or endpoint mismatch.
2. Validate on a canary Pod or equivalent staging setup.
3. Confirm TLS handshake, authentication, and sender identity.
4. Watch error rates and queue age.
5. Roll out to remaining instances.
6. Reconcile `UNKNOWN` attempts before resending.

### 27.5. Step 5 — Document the Incident

Do not merely write "re-enabled SMTP". Record:

~~~text
Incident:
  Time window
  Active profile
  Intended TLS mode
  Error stage and safe code
  Certificate/config root cause
  Number of pending/accepted/unknown deliveries
  Resolution deployment version
  Prevention test/alert added
~~~

Never paste passwords or raw MIME into incident reports.

## 28. Runbook: Suspected or Confirmed SMTP Secret Exposure

When an SMTP password or send token may have entered Git, logs, or build artifacts, **simply deleting the line containing the password is not enough**.

Reasonable incident response steps:

1. Identify and contain where the secret is exposed; avoid copying the secret into more systems while investigating.
2. Revoke/rotate the credential at the provider urgently.
3. Update the secret store and roll out the new version to authorized workloads.
4. Audit the SMTP account for unusual activity, quota burn, or unauthorized sends.
5. Locate copies across logs, CI artifacts, and Git history, and remediate per policy.
6. Replace credentials in other environments **if shared**; never patch only one profile.
7. Verify TLS/authenticated submission with the new credential.
8. Update alerts, secret scanning, access controls, and postmortem actions.

**Never print the new credential in chat or terminal** just to "prove it changed". Verify via version IDs, connection status, and approved test outcomes.

### 28.1. Consequences of Sharing Secrets Across Profiles

If local, staging, and prod share one SMTP account, a leak on a developer machine compromises production. Give every profile its own account and permissions so sensitive secrets have minimal blast radius and independent revocation.

## 29. Step-by-Step Practice Exercises

### Exercise 1 — Send to Local Mailpit

**Setup:** Java/Maven/Docker installed, project containing the files illustrated above.

1. Start Mailpit via Docker Compose.
2. Run Spring with `SPRING_PROFILES_ACTIVE=local`.
3. Enable `APP_MAIL_SEND_DEMO_ON_STARTUP=true` for a single smoke test.
4. Open the Mailpit web UI and verify the subject, From, To, and UTF-8 body.
5. Turn the demo runner off and restart to verify the app no longer sends on startup.

**Expected result:** email lands in the local sink; no staging/prod credentials needed and nothing reaches a real SMTP provider.

### Exercise 2 — Guarantee Prod Always Requires TLS

**Setup:** Use dummy test values; never call real SMTP.

1. Run `MailProdConfigurationTest`.
2. Confirm `starttls.enable/required` and hostname verification take effect.
3. Try overriding `mail.smtp.starttls.required=false` in the test.
4. Verify `MailTlsConfigurationGuard` rejects the configuration.
5. Restore valid configuration.

**Expected result:** local intentionally allows its isolated plaintext sink; staging/prod **cannot** pass the guard with weaker-than-policy transport settings.

### Exercise 3 — Test Implicit TLS Configuration

**Setup:** A staging/sandbox endpoint supporting implicit TLS 465, or a fake SMTP server configured with matching TLS.

1. Create an alternative configuration using `ssl.enable=true`.
2. Disable STARTTLS mode for that endpoint.
3. Enable hostname verification.
4. Test the TLS handshake and certificate in an authorized environment.
5. Contrast what breaks if STARTTLS 587 settings are pointed at a 465 endpoint.

**Expected result:** distinguish immediate TLS handshakes from STARTTLS upgrades without disabling TLS verification.

### Exercise 4 — Missing Secret

**Setup:** A test context that does not inherit external credentials.

1. Select the `prod` profile.
2. Supply dummy host/username/from, omitting the password.
3. Start the context.
4. Confirm startup/config validation fails with zero submission attempts.
5. Supply a **dummy test secret** and verify binding succeeds without contacting a real provider.

**Expected result:** no default production password exists, and AUTH is never silently skipped.

### Exercise 5 — Secret Rotation

**Setup:** A staging account with rotation permissions or a simulated environment.

1. Note the credential version currently used by staging (without recording raw values).
2. Create a new version in the secret store.
3. Canary-rollout/restart the app per deployment workflow.
4. Verify TLS and authentication with a staging smoke test.
5. Revoke the old version once safe.
6. Simulate a failed canary and verify rollback/halt policy.

**Expected result:** secret rotation requires no source code edits, exposes no credentials, and separates auth failures from network/TLS failures.

### Exercise 6 — Anti-Misconfiguration Profile Test

1. Activate `local,prod` simultaneously.
2. Verify the guard rejects startup.
3. Run `local` with an unintended `SPRING_MAIL_HOST` override in an isolated test.
4. Confirm tests or deployment checks catch the unexpected endpoint.
5. Enforce profile and allowed-host controls per project policy.

**Expected result:** property precedence cannot silently route tests through a production relay.

### Exercise 7 — Diagnosing Certificate Errors

1. Against staging/fake TLS, use a certificate untrusted by the JVM or a mismatched hostname (never break production to test errors).
2. Verify the TLS handshake fails when verification is enabled.
3. Record the safe error code and sanitized nested cause.
4. Fix the trust chain or hostname properly.
5. Re-test with `checkserveridentity=true`.

**Expected result:** fix the certificate root cause rather than setting `ssl.trust=*` or disabling hostname verification.

## 30. Practice Project Completion Matrix

A lab succeeds only when you separate **configured**, **tried**, **verified**, and **deployed**. The matrix below is a checklist for learners to execute; it does not claim the current project has already passed these checks.

| Item | How to Verify | Required Result |
| --- | --- | --- |
| Local isolation | Mailpit captures mail under local profile | No credentials or Internet SMTP needed |
| Profile selection | Run local/staging/prod independently | Each environment uses its own endpoint/identity |
| Configuration source | Inspect sanitized config | Zero passwords in repository |
| STARTTLS | Test effective prod properties | `enable=true`, `required=true` |
| Certificate verification | Test effective properties | `ssl.checkserveridentity=true` |
| Implicit TLS | Run dedicated port 465 test | `ssl.enable=true`, STARTTLS not mistakenly enabled |
| No silent downgrade | Fake SMTP omitting STARTTLS | Connection fails rather than sending plaintext |
| No trust-all | Override `ssl.trust=*` | Rejected by policy |
| Missing secret | Test context without password | Startup fails, no send |
| Conflicting profiles | `local,prod` active | Guard rejects |
| Local auto-send | Runner active only when flag enabled | Does not send when false or in prod |
| Fake SMTP | Send test and inspect MIME | Correct body, subject, and encoding |
| TLS handshake | Authorized staging smoke test | Valid cert, host, CA, and protocol |
| SMTP auth | Separate staging credential | AUTH succeeds with scoped rights |
| Sender identity | Send from verified address | Provider accepts From |
| Secret rotation | Canary/rollout test | Old credential revoked cleanly |
| Outage handling | Fake provider unreachable | Proper retry/backoff/incident; never weakens TLS |
| Logging | Audit lab logs | No raw passwords, tokens, or bodies |
| CI isolation | Unit/integration tests | No production SMTP secrets needed |
| Deployment | Review Pod/Compose manifests | No secrets baked into container images |

### 30.1. Lab Inputs Must Stay Isolated

Use only:

- Test recipients, never real customer addresses.
- Isolated SMTP sinks or authorized staging/sandbox accounts.
- Dummy secrets in unit tests.
- Templates/bodies free of real PII or tokens.
- Production credentials only inside authorized deployments.

Never run a bulk "test send" in production to check deliverability without explicit approval, quota, and a plan.

### 30.2. Classifying Verification Depth

~~~text
CONFIG_ONLY
  The expected properties have been bound.

TLS_HANDSHAKE_VERIFIED
  Transport handshake and certificate checks succeeded.

SMTP_AUTH_VERIFIED
  Provider accepted authentication.

SMTP_SUBMISSION_ACCEPTED
  Provider accepted the test submission.

RECIPIENT_DELIVERY_OBSERVED
  Test mailbox/provider feedback observed delivery.
~~~

These milestones **are not interchangeable**. Passing a property-binding unit test does not mean a live TLS handshake succeeded; SMTP accepted is not yet inbox delivery.

## 31. Design Mistakes to Avoid

| Mistake | Why It Is Wrong | Right Approach |
| --- | --- | --- |
| Hardcoding SMTP passwords in YAML | Leaks via Git and build artifacts | Inject at runtime from a secret store |
| Base64 passwords in Git | Base64 decodes trivially | Commit no representation of any secret |
| Sharing one SMTP account across profiles | Expands blast radius and mixes quotas | Separate accounts per environment |
| Local pointing at production endpoint | Sends real mail during tests | Isolated SMTP sink and allowlists |
| Enabling only `starttls.enable` | May silently skip TLS if STARTTLS missing | Also set `starttls.required=true` |
| Disabling hostname verification | Fails to confirm server identity | Keep `ssl.checkserveridentity=true` |
| `ssl.trust=*` | Trusts every certificate blindly | Configure proper CA/truststore |
| Port 465 with STARTTLS 587 properties | Incompatible protocol handshake | Use implicit TLS mode |
| Port 587 with `ssl.enable=true` | Starts TLS before SMTP greeting | Use STARTTLS |
| SMTP AUTH without requiring TLS | Credentials exposed on wire | Enforce fail-closed TLS before AUTH |
| Trusting all certs in staging | Staging stops reflecting prod security | Fix trust chains and test properly |
| Committing a real `.env` | Secrets leak in version control | Gitignore + secret scanning + rotation if exposed |
| Using Docker `ARG` for prod password | Leaks in image layers and build history | Runtime injection |
| Treating Base64 K8s Secrets as encryption | Does not secure data at rest | RBAC, encryption at rest, external secret stores |
| Mounting secret files without configtree/loader | App gets a path string, not the password | Bind file contents via property source |
| Assuming JavaMailSender reloads mutated secret files | Beans/config can cache old values | Controlled restart or refresh |
| Dumping all Spring properties to debug | Can expose passwords and metadata | Structured sanitized diagnostics |
| Turning on `mail.debug` in prod | Logs protocol, recipients, and auth metadata | Restrict to authorized scoped troubleshooting |
| Checking only `application-prod.yml` on disk | Misses runtime overrides | Test effective config and guards |
| Running `local,prod` together | Precedence yields mixed settings | One environment profile at a time |
| Auto-sending in prod `ApplicationRunner` | Restarts fire unwanted mail | Local-only opt-in demo |
| Sending test mail to real users | Spam, quota waste, PII issues | Staging/test recipients only |
| Retrying infinitely on AUTH 535 | Locks accounts and wastes quota | Fix credentials or permissions |
| Falling back to plaintext to "save mail" | Breaks security policy | Hold, alert, and fix TLS |
| Retrying after every SMTP timeout | Risks duplicate sends | Check stage; use UNKNOWN/reconciliation |
| Treating STARTTLS as end-to-end encryption | SMTP protects only each hop | Threat-model across all relays |
| Treating SMTP accepted as inbox delivered | Misrepresents delivery success | Track bounces and feedback separately |

## 32. Frequently Asked Questions

**"Which profile should be the default during development?"**  
Developers can explicitly enable `local`. In security-critical projects, having no active environment profile should fail config validation rather than picking production SMTP or an unknown default relay.

**"Should spring.profiles.active be set in application.yml?"**  
Usually let runtime/deployment select the environment. Hardcoding an active profile in the shared config file makes local, CI, and prod diverge in surprising ways.

**"Does Spring Boot find application-prod.yml automatically?"**  
Yes, when `prod` is active under Spring Boot's config data rules. Values can still be overridden by command-line args, env vars, and higher-precedence property sources.

**"Can local and prod be enabled at the same time?"**  
Spring permits multiple profiles, yet here both environment profiles define SMTP endpoint, TLS, and identity. Combining them causes ambiguous precedence, so the guard rejects it.

**"Should placeholders specify a default password?"**  
Never in staging or prod. `${SMTP_PROD_PASSWORD:password}` silently uses a weak string when a deployment misses a secret. Fail startup and fix the secret source.

**"Does Spring Boot provide JavaMailSender out of the box?"**  
`spring-boot-starter-mail` pairs with auto-configuration to build `JavaMailSenderImpl` when matching properties exist. If you declare your own bean, verify how properties are applied.

**"Is STARTTLS on 587 encrypted from the very first byte?"**  
No. The SMTP session begins plaintext to negotiate STARTTLS, then upgrades with a TLS handshake. `starttls.required=true` fails if upgrade fails; implicit TLS on 465 starts with the TLS handshake immediately.

**"Why are both starttls.enable and starttls.required needed?"**  
`enable` permits STARTTLS; `required` refuses to proceed if STARTTLS is absent or fails. In protected environments, `enable` alone is insufficient.

**"Should mail.smtp.ssl.enable be true for STARTTLS 587?"**  
No. Standard configs set `ssl.enable=false` for 587 STARTTLS and `ssl.enable=true` for 465 implicit TLS. Always match your provider endpoint.

**"Can port 587 ever use ssl.enable=true?"**  
If a port 587 endpoint expects an SMTP greeting/STARTTLS, an implicit TLS client tries to handshake immediately and fails. Only configure that if your provider explicitly contracts otherwise.

**"What does checkserveridentity protect against?"**  
It verifies the SMTP endpoint's hostname matches the TLS certificate; paired with CA chain trust, this proves the app is talking to the intended server rather than any server holding a trusted cert.

**"Why not use ssl.trust=* just for quick testing?"**  
Because it trusts anything, masking certificate errors and MITM attacks. Use a proper CA/truststore and keep hostname verification so tests mirror production.

**"Does STARTTLS guarantee the message stays encrypted to the recipient's mailbox?"**  
No. It protects only the hop from your Spring client to your SMTP relay. Subsequent relays follow their own contracts, and providers may store email content.

**"Do we still need SMTP AUTH when using TLS?"**  
Depends on the provider. TLS encrypts the transport; AUTH identifies your account. Most submission providers require both, while an internal IP-authenticated relay may have a different contract.

**"Should the SMTP password go into the Dockerfile?"**  
No. Build environment-agnostic images and inject secrets at runtime per deployment.

**"Is a Kubernetes Secret already secure because it uses Base64?"**  
No. Base64 is encoding, not encryption. You still need RBAC, encryption at rest, restricted API/env inspection, and often an external secret manager.

**"Does configtree read filenames or file contents?"**  
When imported properly, it uses filenames as config keys and file contents as values. Merely putting a file path into an env var does not make Spring read the file without dedicated support.

**"Why did the app keep using the old password after rotating a Kubernetes Secret?"**  
Env-injected secrets do not auto-refresh inside running processes, and updated mounted files do not auto-reload inside `JavaMailSenderImpl`. You need a rolling restart or an explicit refresh design.

**"Can OAuth2 replace SMTP passwords?"**  
Yes, if supported by the provider and configured with the right AUTH mechanism and token lifecycle. Tokens remain secrets and still require TLS.

**"Does testing the prod profile need real secrets?"**  
Not for binding/policy tests. Use dummy placeholders without calling SMTP; only authorized staging smoke tests need real staging credentials.

**"Can we log the secret value briefly to check the app loaded the right one?"**  
No. Compare secret version IDs, check successful authentication in authorized environments, and inspect sanitized metadata instead.

**"How does Connection refused differ from PKIX path building failed?"**  
Connection refused occurs at TCP connect/port level; PKIX is a certificate trust-chain failure during TLS handshake. They require completely different fixes.

**"Can AuthenticationFailedException be caused by bad TLS?"**  
Some providers reject AUTH until TLS is active, though wrong passwords, account locks, or AUTH mechanisms cause it too. Inspect stage, cause chain, and sanitized server replies.

**"Should we fix 535 errors by retrying the password repeatedly?"**  
No. That can lock the account, exhaust quotas, and trigger alerts. Verify the secret version and account policy first, then test boundedly.

**"Should we call testConnection on application startup?"**  
Depends on availability goals. During a provider outage, failing startup may be undesirable for a durable-outbox worker. Separate config validation, readiness, and SMTP connectivity checks.

**"If mail sent over TLS lands in spam, was TLS misconfigured?"**  
Not necessarily. Deliverability also depends on SPF/DKIM/DMARC, sender reputation, content, complaints/bounces, and recipient/provider filtering.

**"Can Spring Mail send HTML and attachments over the same TLS config?"**  
Yes. Transport handles TLS/auth while `MimeMessageHelper` builds MIME. Keep multipart modes, encoding, and attachment sources safe.

**"Does an SMTP exception guarantee the email wasn't sent?"**  
No. After DATA, the client can lose the reply even though the relay accepted. Use `UNKNOWN` and reconciliation to prevent duplicate sends on retry.

**"Do we need to switch profiles for every individual email?"**  
No. Profiles define deployment environments. If one app talks to multiple SMTP providers, use an adapter registry with per-provider configs rather than mutating profiles or a singleton sender per request.

**"When is this practice lab complete?"**  
When you have verified local sink capture, zero repo secrets in staging/prod, fail-closed TLS, certificate validation, negative tests, a rotation plan, and clear verification boundaries. Passing a unit test never equals real provider delivery.

## 33. Pre-Production SMTP Configuration Checklist

### Configuration and Profiles

1. Only the single `prod` mail environment profile is active in production deployments.
2. Neither `local` nor test profiles are active alongside `prod`.
3. Host and port come from approved provider configuration.
4. SMTP mode matches the endpoint: STARTTLS 587 or implicit TLS 465.
5. STARTTLS sets both `enable=true` and `required=true`.
6. Implicit TLS sets `ssl.enable=true` without misconfigured STARTTLS.
7. Hostname verification is enabled.
8. No `ssl.trust=*`, custom trust-all socket factories, or disabled certificate validation exist.
9. Connection, read, and write timeouts are bounded for your workload.
10. Runtime property overrides are verified after Spring Boot binding, not only by reading YAML.

### Secrets and Identity

11. Zero passwords or tokens exist in source code, YAML, Dockerfiles, or build artifacts.
12. Secrets come from runtime/secret managers with least privilege.
13. Local, staging, and prod use separate credentials and account scopes.
14. Passwords and tokens have no weak default fallbacks when config is missing.
15. Secret mount/env mappings have accurate names and Spring reads values, not file paths.
16. A rotation/revocation procedure and version verification exist.
17. Pods/service accounts can read only required secrets.
18. Logs, metrics, and Actuator never leak credentials or raw MIME.
19. From/envelope identities are provider-authorized; SPF/DKIM/DMARC are configured and tested.
20. If using OAuth2, token refresh and AUTH mechanisms are explicitly designed.

### Isolation and Operability

21. Local/CI uses an SMTP sink or fake server, never calling production providers.
22. Staging uses test recipients and dedicated credentials.
23. No public test runner or open test-send endpoint exists in production.
24. Network egress to SMTP endpoints is properly scoped.
25. Metrics track connect/TLS/AUTH errors, submission outcomes, and queue age when using workers.
26. Alerts catch config errors right after deploys or rotations.
27. Runbooks cover certificate mismatches, credential revocations, and provider outages.
28. TLS negotiation failures fail closed.
29. Failures after SMTP DATA are never blindly retried or failed over as definitely unsent.
30. Retry limits/backoff, business deadlines, and reconciliation fit your mail architecture.

### Verification

31. Unit/integration tests verify `application-prod.yml` and `application-staging.yml` binding.
32. Negative tests cover missing secrets, disabled TLS, disabled hostname checks, and conflicting profiles.
33. Separate implicit TLS tests exist if port 465 is supported.
34. Staging smoke tests verify certificates, AUTH, and sender identity.
35. UTF-8/HTML/attachment MIME tests pass against fake SMTP when used.
36. Canary secret rotation tests confirm old credentials are gone before revocation.
37. Real Docker/Kubernetes env and secret mounts are tested beyond laptop unit tests.
38. Record exact verification scope—config, TLS, AUTH, SMTP accepted, or delivery feedback—without conflating them.

## 34. Architecture Diagram and Trust Boundaries

~~~text
                  Source repository
                         |
                         v
                   Versioned config
                  application.yml
                   profile YAMLs
                  (NO credentials)
                         |
                         v
                  Immutable build
                         |
                         v
                  Runtime environment
                         |
          +--------------+-----------------+
          |              |                 |
          v              v                 v
      Local profile   Staging profile   Prod profile
          |              |                 |
          v              v                 v
     Mailpit sink    Staging secrets     Prod secrets
     no SMTP AUTH     secret manager      secret manager
     plaintext only      |                   |
     in isolation        |                   |
          |              v                   v
          |         STARTTLS required   STARTTLS required
          |         or implicit TLS     or implicit TLS
          |              |                   |
          +--------------+-------------------+
                         |
                         v
                   Spring Boot Mail
               JavaMailSenderImpl + config
                         |
                         v
                 TLS policy validation
                         |
                         v
                MailDemoService / worker
                         |
                         v
                SMTP network submission
                         |
              +----------+-----------+
              |                      |
              v                      v
         ACCEPTED               ERROR/UNKNOWN
              |                      |
              v                      v
      Delivery feedback       Error classification,
      processed separately    retry/reconciliation
~~~

### 34.1. What Is Guaranteed at Each Layer?

| Layer | What Is Controlled | What Is Not Guaranteed |
| --- | --- | --- |
| Spring profiles | Expected settings per environment | Cannot block all runtime overrides alone |
| Secrets/runtime injection | Keeps credentials out of source | Does not remove all runtime env inspection |
| STARTTLS required | Blocks plaintext downgrade on failed upgrade | Not end-to-end encryption across relays |
| Hostname/certificate verification | Verifies endpoint against TLS trust model | Does not verify sender domain or delivery |
| SMTP AUTH | Authenticates account access to relay | Does not confirm recipient opened mail |
| JavaMailSender accepted | Observes provider accepted submission | Does not guarantee inbox placement or read |
| Outbox (if used) | Stores durable send intent with business data | Does not make SMTP exactly-once |
| Feedback processing | Ingests provider bounce/delivery events | Cannot always confirm exact inbox placement |

### 34.2. Implementation Principles to Remember

- **Profiles** define intended environment settings; **runtime secret sources** supply credentials.
- **TLS mode** must match the endpoint: 587 STARTTLS with `required=true`, or 465 implicit TLS.
- **Hostname verification** and trust chains must be valid; never use trust-all.
- **Local SMTP sinks** are deliberate isolated exceptions, never staging/prod standards.
- **Production has no default password** and never relies on log masking as a sole defense.
- **CI configuration tests** need neither production credentials nor network sends.
- **Secret rotation** is an explicit runtime lifecycle change, not just editing a file.
- **SMTP accepted** is a submission result, not yet inbox delivery.

## 35. Conclusion

**Configuring TLS and secrets per profile** is a foundational practice step that turns Spring Framework Mail from a local laptop example into a safely deployable component. Start by separating `local`, `staging`, and `prod` cleanly; configure an SMTP sink solely for local; supply isolated runtime secrets per environment; and enforce STARTTLS or implicit TLS alongside certificate and hostname verification on real SMTP connections.

With Spring Boot, `application-<profile>.yml` files express environment policy, `spring.mail.properties` forwards TLS flags to Jakarta Mail, and `JavaMailSender` lets mail-sending code stay decoupled from specific passwords and hostnames. Still, **correct files on disk are not enough**: verify effective properties, govern secret sources, block unsafe overrides, maintain a rotation plan, and test TLS/AUTH failures before rollout.

The goal of this lab is not simply "one email sent successfully", but a verifiable, explainable delivery setup: **dev never touches production accounts, real environments never downgrade TLS, zero secrets live in the repository, missing secrets fail closed, and connection incidents are diagnosed without weakening security**.
