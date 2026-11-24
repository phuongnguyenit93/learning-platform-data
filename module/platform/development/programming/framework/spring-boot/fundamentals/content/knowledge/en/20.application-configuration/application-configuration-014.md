# Separating Application Configuration from Runtime-Supplied Secrets

A Spring Boot application typically needs many parameters to operate: HTTP ports, timeouts, service names, database addresses, log levels, API keys, access passwords, or authentication certificates. Spring Boot can read all of these through `Environment`, yet **not every value should be stored and distributed in the same way**.

Separating these two categories is a foundational rule:

- **Application configuration**: values describing how the application behaves, which can normally live in source control provided they contain no sensitive information.
- **Secrets**: values whose disclosure could grant unauthorized access, allow identity impersonation, decrypt data, or cause harm. Secrets must be supplied through a secure channel outside source code and managed under dedicated access controls, lifecycles, and rotation policies.

The word "environment" in this topic should be understood as the **deployment environment and runtime configuration delivery mechanisms**, not merely OS environment variables. Secrets can be delivered via environment variables, securely mounted files, Kubernetes Secrets, a secret manager, or platform-integrated workload identity. These mechanisms differ in protection level and operational characteristics.

This lesson explains how to classify values, combine Spring Boot configuration with runtime secrets, use `@ConfigurationProperties`, and deploy and test without putting sensitive data into repositories.

## 1. What is application configuration?

Application configuration consists of parameters that alter program behavior without recompiling. They enable the same artifact to run in development, testing, and production with appropriate values.

For example:

~~~yaml
server:
  port: 8080

spring:
  application:
    name: catalog-service

app:
  catalog:
    page-size: 50
    cache-enabled: true
  partner:
    base-url: https://partner-api.example.invalid
    connect-timeout: 3s
~~~

These properties specify which port the application listens on, whether caching is enabled, page size, and connection timeout.

Most values like these **are not secrets**. They can live in the project's `application.yml`, be reviewed in pull requests, and be versioned alongside code.

However, **not every URL or hostname is automatically public**. A URL containing a query token, embedded password, or restricted internal endpoint can become sensitive information. Classify based on content and impact of exposure, not field names alone.

## 2. What is a secret?

A secret is data that must remain confidential because anyone possessing it could gain unauthorized access or advantage.

Examples:

- Database passwords and service account credentials.
- API keys, access tokens, refresh tokens, webhook signing secrets.
- Private keys for signing JWTs, TLS private keys, SSH private keys.
- OAuth2 client secrets, message broker passwords.
- Encryption keys, HMAC keys, or keys used to decrypt data.
- Cloud provider credentials, where systems still rely on long-lived credentials.

Bad example in `application-prod.yml`:

~~~yaml
spring:
  datasource:
    username: catalog_writer
    password: SuperSecretPassword123

app:
  payments:
    api-key: live-key-abcdef123456
~~~

The values above are illustrative placeholders, not real credentials. The design flaw is writing them **directly** inside source files that get committed, copied, packaged into artifacts, or printed in pipelines and logs.

Once a secret enters Git, deleting the line on the current branch does not remove it from commit history, clones, CI caches, or existing copies. A real exposed secret must be **revoked or rotated**, not merely "deleted and committed again."

## 3. Config vs. secret classification table

| Value | Typical classification | Notes |
|---|---|---|
| `server.port` | Config | Usually safe to store in source control |
| `spring.application.name` | Config | Service identifier name |
| `app.client.connect-timeout` | Config | Behavioral tuning |
| `app.feature.enabled` | Config | Static per-deployment feature flag |
| API URL without credentials | Config; sensitivity depends on system | Follow policy on publishing internal endpoints |
| JDBC URL without username/password | Config; sensitivity depends on system | Never embed passwords inside the URL |
| Database username | Policy-governed info | May be a non-secret identifier, yet avoid publishing unnecessarily |
| Database password | Secret | Supplied from a secure runtime source |
| API key or bearer token | Secret | Grants permission to call external systems |
| Public TLS certificate | Usually not a secret | Public certificate differs from private key |
| TLS private key | Secret | Protect with access control / secret manager |
| JWT signing key | Secret | Leaking the key allows forging tokens |
| OAuth client ID | Usually not a secret | Distinct from OAuth client secret |
| OAuth client secret | Secret | Never place in frontends or repositories |
| Dummy password used in tests | Test fixture with no real privilege | Mark clearly as dummy; never reuse in production |

Do not judge solely by variable name. A variable named `DATABASE_URL` may contain `user:password@host`, in which case the entire URL must be treated as a secret. Conversely, a public key may be intentionally shared even though its field name contains the word "key."

## 4. Why shouldn't secrets live in application.yml?

`application.yml` and `application.properties` are normally part of the source tree or packaged application artifact. A hard-coded secret can leak through many paths:

1. **Repository and Git history:** commits, pull requests, forks, clones, and backups.
2. **Build artifacts:** configuration files packaged inside JARs or container images.
3. **CI/CD:** build logs, job parameters, pipeline variables, and pipeline artifacts.
4. **Documentation sharing:** copying config into issues, chats, wikis, or emails.
5. **Runtime diagnostics:** Environment dumps, exceptions, tracing, Actuator, or debug logs.
6. **Over-broad access:** too many developers can read production credentials simply because they have read access to code.

A better approach is **storing configuration structure and reference names** in the repository while supplying actual secrets from the deployment environment.

Example `application.yml`:

~~~yaml
app:
  payments:
    base-url: https://payments.example.invalid
    connect-timeout: 3s
    api-key: ${PAYMENTS_API_KEY}

spring:
  datasource:
    url: ${DB_JDBC_URL}
    username: ${DB_USERNAME}
    password: ${DB_PASSWORD}
~~~

Here the repository holds only placeholder names, not the actual API key or password values. At startup, Spring Boot resolves the placeholders via `Environment` and available property sources.

This alone is not a complete security solution. When secrets are passed via environment variables, the secret still exists in the process's environment and memory. Actual security depends on how the deployment platform delivers values, who can read them, whether they get logged, and your rotation process.

## 5. Where does Spring Boot receive configuration from?

Spring Boot supports **externalized configuration**: the application does not need recompiling when deployment settings change.

Common sources:

- Packaged or external `application.yml` and `application.properties`.
- `application-{profile}.yml` for profile-based configuration.
- Process environment variables.
- Java system properties.
- Command-line arguments.
- `spring.config.import` to load additional configuration data from supported locations.
- Additional `PropertySource`s via appropriate integrations or framework hooks.
- Secret managers or deployment platforms populating the sources above.

Sources follow a **precedence order**. If the same property is declared multiple times, Spring Boot uses the value from the higher-precedence source according to the configuration rules of the version in use.

For example:

~~~yaml
server:
  port: 8080
~~~

The application can receive `SERVER_PORT=9090` from the process environment; normally this external value overrides the value in the config file.

Exact ordering depends on Spring Boot version, config imports, profiles, and custom sources. Do not assume every source type holds the exact same precedence in every application.

### 5.1. An environment variable is not a Spring profile

Two distinct concepts:

- **Environment variable:** a way to supply key/value pairs to a process, such as `DB_PASSWORD`.
- **Spring profile:** an activated group of configurations/beans such as `dev`, `test`, or `prod`, typically via `spring.profiles.active`.

The same `prod` profile can run across multiple clusters with different secrets. A profile is **not** a secret vault and provides no encryption mechanism of its own.

## 6. Complete example: config in repository, secret from runtime

Suppose an application calls a payment provider. We separate safe-to-review settings from the secret API key.

`src/main/resources/application.yml`:

~~~yaml
spring:
  application:
    name: checkout-service

app:
  payments:
    endpoint: https://payments.example.invalid
    timeout: 5s
    api-key: ${PAYMENTS_API_KEY}
~~~

The application uses `@ConfigurationProperties`:

~~~java
package com.example.checkout.config;

import java.net.URI;
import java.time.Duration;
import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "app.payments")
public record PaymentProperties(
        URI endpoint,
        Duration timeout,
        String apiKey) {
}
~~~

Register the properties type:

~~~java
package com.example.checkout;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.context.properties.ConfigurationPropertiesScan;

@SpringBootApplication
@ConfigurationPropertiesScan
public class CheckoutApplication {

    public static void main(String[] args) {
        SpringApplication.run(CheckoutApplication.class, args);
    }
}
~~~

Consume in a service:

~~~java
package com.example.checkout.service;

import com.example.checkout.config.PaymentProperties;
import org.springframework.stereotype.Service;

@Service
public class PaymentService {

    private final PaymentProperties properties;

    public PaymentService(PaymentProperties properties) {
        this.properties = properties;
    }

    public void submitPayment() {
        // Use properties.endpoint() and properties.apiKey()
        // when configuring the HTTP client to call the provider.
        // Never log apiKey().
    }
}
~~~

This uses Spring Boot 3 syntax with a Java record. Boot 2.x can use JavaBeans or constructor binding per its version and API. The core point of this lesson does not depend on binding style: **the object can hold secrets at runtime, while secret values do not live in the repository**.

### 6.1. Supplying values via environment variables

Example running locally in a POSIX shell:

~~~bash
export PAYMENTS_API_KEY='local-placeholder-value'
./gradlew bootRun
~~~

The value above is an illustrative placeholder, not for production. Copying a real secret into a shell command can leave it in terminal history, command recordings, or session audit tools; choose a secret entry/delivery workflow that avoids exposure.

In PowerShell, the syntax is:

~~~powershell
$env:PAYMENTS_API_KEY = 'local-placeholder-value'
./gradlew bootRun
~~~

The environment variable is passed into the application **process** or child process as supported by the OS/shell. It is not a setting committed into `application.yml`.

### 6.2. Using property names directly via relaxed binding

Without a placeholder on `app.payments.api-key` in YAML, Spring Boot can bind a matching environment variable directly into `@ConfigurationProperties` following name-conversion rules.

For the canonical property:

~~~text
app.payments.api-key
~~~

The environment variable name under Spring Boot's relaxed binding rules is:

~~~text
APP_PAYMENTS_APIKEY
~~~

General rule: replace dots with underscores, remove dashes, and uppercase characters. Therefore, do not assume `APP_PAYMENTS_API_KEY` is always equivalent; follow Spring Boot's environment variable naming rule and verify the bound property.

Using the `${PAYMENTS_API_KEY}` placeholder in YAML offers a practical benefit: the deployment variable name is short, explicit, and does not rely on inferring relaxed binding rules. Both patterns are valid when applied consistently.

## 7. What should the application do if a secret is missing?

A required secret should never be replaced with a weak password or dummy key in production.

Dangerous example:

~~~yaml
app:
  payments:
    api-key: ${PAYMENTS_API_KEY:password123}
~~~

The portion after the colon is the placeholder's **default value**. If the environment forgets to supply the secret, the application could use `password123` with no obvious warning.

Declare without a secret default:

~~~yaml
app:
  payments:
    api-key: ${PAYMENTS_API_KEY}
~~~

And design **fail-fast** behavior before accepting requests if the secret is missing or invalid.

With `@ConfigurationProperties`, you can use Bean Validation:

~~~java
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;
import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.validation.annotation.Validated;

import java.net.URI;

@Validated
@ConfigurationProperties(prefix = "app.payments")
public record PaymentProperties(
        @NotNull URI endpoint,
        @NotBlank String apiKey) {
}
~~~

A Bean Validation implementation is needed on the classpath, typically via:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-validation'
}
~~~

**Note:** `@NotBlank` catches empty or whitespace-only strings, yet does not prove every placeholder resolved or that the key actually has permissions with the provider. Depending on property source setup and version, an unresolved placeholder may cause a binding error, remain as literal text, or surface as another error. Test startup with missing secrets and build appropriate config checks rather than assuming one annotation covers every case.

If the system needs to verify a real key against an external service, weigh fail-fast startup against resilience when an upstream is temporarily unavailable. Never make network calls inside a properties record constructor.

## 8. Profile-specific configuration is still not a place to store secrets

Profiles help group **non-secret values** by environment.

For example:

`application.yml`:

~~~yaml
app:
  client:
    timeout: 3s
~~~

`application-dev.yml`:

~~~yaml
app:
  client:
    endpoint: http://localhost:9090
    timeout: 10s
~~~

`application-prod.yml`:

~~~yaml
app:
  client:
    endpoint: https://partner.example.invalid
    timeout: 2s
~~~

These files can be reviewed safely in the repository as long as they hold no sensitive info. Secrets for each environment are still supplied separately:

~~~text
dev deployment  -> dev PAYMENTS_API_KEY
test deployment -> test PAYMENTS_API_KEY
prod deployment -> production PAYMENTS_API_KEY
~~~

Do not store a production password in `application-prod.yml` merely because that file is "only used in production." The file can still be committed, packaged into the JAR, or read from artifacts.

### Separating access control by environment

In a well-run deployment setup, read permissions for production secrets differ from dev/test permissions. Developers can run unit and integration tests with dummy data without needing production credentials. If the same secret is shared across dev and production, a leak in a less-protected environment compromises the critical one.

## 9. Environment variables: convenient, yet not automatically secure

Environment variables are a popular way for deployment platforms to pass secrets into Spring Boot processes. Advantages:

- No need to store values in source files.
- Easy integration with containers, CI/CD, and cloud runtimes.
- One artifact runs across environments with different secrets.
- Spring Boot reads the environment automatically and supports binding values.

However, an environment variable is **not encrypted by default just because it is an environment variable**. Risks include:

- Processes running with the same privileges or OS administrators can read process environments depending on OS controls.
- Debuggers, process dumps, or diagnostic tools can capture values.
- An application might accidentally log the full `Environment`.
- CI jobs can print secrets when shell tracing is enabled or logging is misconfigured.
- Some platform UIs/CLIs display environment variables to anyone allowed to inspect workloads.
- Process environments are typically snapshotted at startup; updating a value in a secret store does not automatically update running processes.

Treat environment variables as a **transport channel**, not an absolute secrecy guarantee. Pair them with access control, log hygiene, proper deployment practices, and rotation procedures.

### 9.1. Do not pass secrets directly on the command line when safer options exist

Example to avoid in production:

~~~bash
java -jar checkout.jar --app.payments.api-key=real-secret-here
~~~

Arguments can appear in process listings, command logs, or monitoring tools. Also avoid leaving secrets in commands captured by shell history.

Using a platform-supported secret channel (controlled environment injection or securely mounted files) is generally better, while still evaluating access permissions and logging risks.

### 9.2. Never log the entire Environment while debugging

Dangerous example:

~~~java
log.info("Payment API key: {}", properties.apiKey());
~~~

Never write tokens, passwords, or private keys to logs. For diagnostics, log presence checks or non-sensitive metadata instead:

~~~java
log.info("Payment provider endpoint configured: {}",
        properties.endpoint() != null);
~~~

Even an endpoint can be sensitive if it embeds tokens or access parameters. When designing logs, decide deliberately what data is safe to emit.

## 10. Supplying secrets via mounted files and configtree

Another pattern supplies secrets as files on the runtime filesystem. For instance, an orchestrator or secret manager mounts a file:

~~~text
/run/secrets/
└── app.payments.api-key
~~~

The file's contents are the secret supplied by the deployment platform, absent from the repository and never baked into the image.

Spring Boot supports importing `configtree` configuration starting in version 2.4. For example:

~~~yaml
spring:
  config:
    import: "configtree:/run/secrets/"
~~~

With the layout above, the filename `app.payments.api-key` maps to the `app.payments.api-key` property, and the file content becomes the bound value.

`configtree:` is a **config data source**, not an encryption tool. Security relies on how files are mounted, file permissions, container/volume access rights, the secret store, and which processes can read the files.

### 10.1. optional:configtree and mandatory secrets

You may see:

~~~yaml
spring:
  config:
    import: "optional:configtree:/run/secrets/"
~~~

The `optional:` prefix allows startup to proceed if the import path does not exist, rather than failing over a missing directory. This is convenient in local development, **but inappropriate if production requires secrets in that directory** and has no other validation check.

If a secret is mandatory, keep the path non-optional or enforce validation/fail-fast checks. Do not add `optional:` thoughtlessly and let the application boot without required credentials.

### 10.2. File permissions and access rights

To protect secret files:

- Mount only into workloads that require them.
- Restrict read permissions for the container user/group.
- Never bake secrets into image layers.
- Avoid copying file contents into logs or build artifacts.
- Account for how the platform updates mounted files and whether the app re-reads them.
- When using secret volumes, audit backups and node/host access controls.

Updating a mounted secret file's content does not mean `@ConfigurationProperties` or existing connections automatically refresh. Design how new secrets take effect.

## 11. Kubernetes Secrets: not encrypted safely by default

In Kubernetes, workloads can receive secrets via environment variables or mounted volumes. Example container referencing a pre-created Secret:

~~~yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: checkout-service
spec:
  replicas: 1
  selector:
    matchLabels:
      app: checkout-service
  template:
    metadata:
      labels:
        app: checkout-service
    spec:
      containers:
        - name: app
          image: example/checkout-service:1.0
          env:
            - name: PAYMENTS_API_KEY
              valueFrom:
                secretKeyRef:
                  name: payments-credentials
                  key: api-key
~~~

This manifest contains no secret value—only a reference to the Secret object by name and key. Creating, restricting, and managing `payments-credentials` belongs to a separate deployment process.

**Important warning:** Kubernetes Secret objects commonly represent data in Base64 in manifests and API responses; **Base64 is encoding, not encryption**. Achieving real protection requires evaluating RBAC, cluster encryption at rest, API server/etcd access, network/runtime security, and limiting who can read secrets.

### 11.1. Env injection vs. volumes?

| Delivery method | Advantages | Limitations |
|---|---|---|
| Secret as environment variable | Easy with placeholders and relaxed binding | Process environment values normally do not update after Secret changes |
| Secret mounted as file | Avoids placing values in env vars; pairs well with `configtree` | File permissions and reload behavior must be managed |
| External secret manager / CSI integration | Central access control, auditing, rotation | Requires configuring workload identity and secret fetch/refresh behavior |

No single option is universally safest in every organization. Choose based on threat model, operational maturity, management workflows, and actual access controls.

## 12. Secret managers: better for strict control

For production, many systems use a dedicated secret manager, such as a cloud service or internal secret management platform. These tools can provide:

- Access policies scoped to service/workload identity.
- Audit logs for secret reads and changes.
- Controlled rotation and expiration workflows.
- Secret versioning and rollback capabilities.
- Deployment integrations injecting secrets without committing to Git.
- Encryption and key management per provider capabilities.

Two common integration patterns:

1. **Platform delivers secrets to the process:** a deploy controller or agent reads the secret manager and populates environment variables or mounted files before Spring Boot launches.
2. **Application integrates with the secret store at bootstrap/runtime:** uses a compatible library to load configuration from an external service or request credentials via SDK under the workload's identity.

Diagram:

~~~text
                Source repository
                (code + non-secret defaults)
                          |
                          v
                    Build artifact
                          |
                          v
                     Deployment
                          |
             +------------+------------+
             |                         |
             v                         v
    Application config           Secret manager
    (endpoint, timeout)          (API keys, passwords)
             |                         |
             +------------+------------+
                          |
                          v
                Spring Boot process
                   Environment /
                   mounted files /
                   approved client
                          |
                          v
               Typed configuration beans
~~~

Never pull a secret from a secret manager and accidentally save it into a committed `application-prod.yml`, or print it to stdout in a pipeline. Moving secrets between systems stays safe only when every intermediate step is controlled.

### 12.1. Prefer workload identity over long-lived credentials

When supported by the platform, applications can authenticate to the secret manager using a workload or service account identity instead of storing another static master key to fetch other secrets.

This reduces the "storing a secret to read secrets" problem, though it does not eliminate access control requirements. Identities still need least-privilege scopes and protection for metadata/service-account tokens.

## 13. CI/CD: secrets do not belong in artifacts or logs

A typical delivery pipeline has three stages:

~~~text
Build -> Test -> Deploy
~~~

Principles to enforce:

- **Build:** produce one artifact from source code; never embed production secrets inside JARs or images.
- **Test:** use dummy fixtures, test credentials, or test-environment-only secrets.
- **Deploy:** supply production secrets at runtime through an access-controlled deployment channel.

When building Docker images, avoid:

~~~dockerfile
# Avoid:
ARG PAYMENTS_API_KEY
ENV PAYMENTS_API_KEY=$PAYMENTS_API_KEY
~~~

This can leave traces in image history, metadata, or image layers depending on the build setup. Never use build arguments or Dockerfile `ENV` to bake long-lived secrets into released images.

Instead, build a neutral image and supply secrets at deployment time:

~~~text
checkout-service:1.0
  +
runtime configuration
  +
secret injection
  =
checkout-service running in a specific environment
~~~

### 13.1. CI/CD pipeline permissions

Pipelines themselves hold privileges and can leak secrets through:

- Verbose logging or shell tracing.
- Steps printing the environment.
- Over-privileged jobs running on pull requests from untrusted sources.
- Artifacts or caches containing secret files.
- Granting production secret access to every branch or job.

Only jobs that genuinely need a secret should access it. Never expose production credentials to untrusted PR builds. Restrict who can edit pipelines and secret injection rules.

## 14. Actuator, configuration errors, and sensitive data

Spring Boot Actuator improves observability, yet some endpoints expose configuration, property sources, or bean metadata. Boot versions include value display controls and sanitization; however, **never treat default masking as an excuse to expose endpoints publicly or log secrets freely**.

Keep in mind:

- Do not expose `/actuator/env` or `/actuator/configprops` to the public Internet without strong security policies.
- Limit exposed endpoints to operational needs.
- Enable authentication, authorization, and internal network restrictions on sensitive endpoints.
- Never log raw `Environment` or properties beans containing secrets.
- Never include tokens in exception messages, HTTP error responses, or trace attributes.
- Never put secrets into metric tags/labels; metrics are often retained long-term and widely readable.

Example to avoid:

~~~java
log.debug("Datasource password: {}", dataSourceProperties.getPassword());
~~~

Log selective diagnostic info instead:

~~~java
log.info("Datasource configuration loaded");
~~~

Never print passwords or tokens even when log levels are enabled only in development; dev logs still get collected and shared.

## 15. Handling exposed secrets

If a real secret appears in a repository, log, document, or artifact, response steps must go beyond deleting the line of code.

High-level response steps:

1. **Revoke or rotate the secret** at the issuing system as soon as appropriate per incident procedures.
2. Assess impact scope: exposure window, granted permissions, affected services and environments.
3. Inspect logs/audits within system capabilities for unauthorized access.
4. Remove traces where unneeded and handle Git history through controlled procedures; never assume rewriting history revokes access from existing clones.
5. Issue and deliver the new secret through a secure runtime channel.
6. Add secret scanning, code review checks, and least-privilege policies for prevention.

For API keys, database credentials, or private keys, changing values often requires coordinating rollouts to avoid service downtime. A brief overlap between old and new credentials may be needed if supported by the provider, provided the old secret's permissions are bounded and revoked on schedule.

## 16. Secret rotation and applying changes

Secrets have a different lifecycle from regular configuration.

Settings like `app.client.timeout=3s` might change only when deploying a new release. Secrets like database passwords, API keys, or TLS private keys may require rotation due to policy, expiration, or incidents.

A typical rotation flow looks like:

~~~text
Create new secret
      |
      v
Update secret store / runtime provider
      |
      v
Roll out or reload app/connections
      |
      v
Verify app uses new credentials
      |
      v
Revoke old credentials
~~~

**Distinguish updating a secret at the source from updating the secret actively used by the application.**

- Environment variables are normally captured at process startup, so updating platform secrets often requires a restart or rollout.
- Mounted secret files may update via volume sync, yet `@ConfigurationProperties` does not automatically rebind just because file content changes.
- A database connection pool may hold authenticated connections using older credentials.
- HTTP clients or SDKs may cache tokens/credentials.
- A secret manager client may support refresh via its own mechanism, requiring clear cache TTL, retry, and error-handling design.

When selecting a secret delivery channel, design and test **how new versions take effect**, not only how initial values are read.

## 17. Distinguishing secrets from encrypted configuration

Developers sometimes ask: "Can we encrypt passwords and store the ciphertext in YAML?"

Encrypted values in files can be safer than plaintext **if** decryption keys are protected independently and access rights and lifecycles are well managed. However, it still raises hard questions:

- Where does the decryption key live?
- Who has permission to decrypt, and are accesses audited?
- Do both key and ciphertext reside together in the repository or image?
- How do both secrets and encryption keys rotate?
- When does the app hold plaintext in memory, and could it be logged or dumped?

Storing ciphertext alongside its decryption key provides minimal security benefit. A secret manager or platform secret injection usually offers a much clearer operational model.

**Base64 is not encryption**, and naming a file `secrets.yml` does not automatically make that file secure.

## 18. Testing configuration without production secrets

A well-designed project lets developers run tests using dummy secrets or test-environment-only credentials.

Example `application-test.yml`:

~~~yaml
app:
  payments:
    endpoint: http://localhost:9099
    timeout: 1s
    api-key: local-test-placeholder
~~~

The value here is a test string granting no access to any real environment. In tests, properties can be overridden directly:

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.boot.test.context.SpringBootTest;

@SpringBootTest(properties = {
        "app.payments.endpoint=http://localhost:9099",
        "app.payments.timeout=1s",
        "app.payments.api-key=unit-test-placeholder"
})
class PaymentServiceTest {

    @Test
    void contextLoadsWithTestConfiguration() {
        // Can add assertions on beans and bound values.
    }
}
~~~

Tests for configuration binding can use `ApplicationContextRunner` to avoid launching the entire web server:

~~~java
import static org.assertj.core.api.Assertions.assertThat;

import org.junit.jupiter.api.Test;
import org.springframework.boot.context.properties.EnableConfigurationProperties;
import org.springframework.boot.test.context.runner.ApplicationContextRunner;
import org.springframework.context.annotation.Configuration;

class PaymentPropertiesTest {

    @Configuration(proxyBeanMethods = false)
    @EnableConfigurationProperties(PaymentProperties.class)
    static class TestConfiguration {
    }

    private final ApplicationContextRunner runner =
            new ApplicationContextRunner()
                    .withUserConfiguration(TestConfiguration.class);

    @Test
    void bindsNonSecretAndPlaceholderTestValues() {
        runner
                .withPropertyValues(
                        "app.payments.endpoint=https://example.invalid",
                        "app.payments.timeout=2s",
                        "app.payments.api-key=test-only-placeholder"
                )
                .run(context -> {
                    PaymentProperties p =
                            context.getBean(PaymentProperties.class);

                    assertThat(p.timeout())
                            .isEqualTo(java.time.Duration.ofSeconds(2));
                    assertThat(p.apiKey())
                            .isEqualTo("test-only-placeholder");
                });
    }
}
~~~

This test illustrates binding typed properties. It needs no production credentials and makes no calls to external payment services.

Scenarios worth covering in real systems:

- Valid secret supplied from a test source; application binds properly.
- Secret missing/blank; application rejects startup or disables the feature per policy.
- Secret malformed; validation or client initialization handles it cleanly.
- Logs and exceptions never print secret values.
- Test profiles never accidentally point at production endpoints.
- On secret rotation, the application adopts the new version per the designed mechanism.
- With ConfigTree/Kubernetes, files/volumes mount with appropriate read permissions.

Never put real secrets into test fixtures just to "simplify CI."

## 19. Common mistakes and fixes

| Symptom | Common cause | Fix |
|---|---|---|
| Application fails to connect to production DB | `DB_PASSWORD` missing or incorrect | Check secret injection and workload read rights; never print passwords |
| Passes locally, fails in CI | CI job lacks test secret or test accidentally needs real credentials | Use test placeholders/mocks or scoped CI-only secrets |
| Secret committed to `application-prod.yml` | Mistaking profiles for secret storage | Rotate secret, purge from source/artifacts, move to runtime delivery |
| `@ConfigurationProperties` receives `null` | Wrong prefix, property name, bean registration, or unloaded source | Check binding and startup; do not log sensitive values |
| Env variable looks like the property name yet fails to bind | Wrong relaxed binding rule | Use canonical property names or explicit `${...}` placeholders |
| App still uses old secret after secret manager update | Process/cache/connection pool has not reloaded | Design rollout/refresh and verify new credentials take effect |
| Secret appears in Actuator or logs | Unprotected endpoints, responses, or logs | Reduce exposure, enforce access controls, stop logging secrets |
| Kubernetes Secret seen in Base64 | Confusing Base64 with encryption | Audit RBAC, encryption at rest, and runtime access |
| Docker image contains credentials | Secret passed at build time or inside packaged files | Build neutral images, inject secrets at deploy, rotate leaked credentials |
| Weak default secret used unintentionally | Placeholder has an unsafe default | Remove secret defaults and fail startup when secrets are missing |

## 20. Guide for choosing a delivery source

| Deployment need | Usually appropriate option |
|---|---|
| Simple, non-sensitive config shared across environments | `application.yml` in the repository |
| Config differing across dev/test/prod without credentials | Profile-specific files or externalized config |
| Secrets for local development | Protected local secret mechanism, shell/env, or uncommitted file; separate test credentials |
| Simple containers with secret injection | Runtime environment variables injected by platform |
| Containers requiring file-based secrets | Mounted secret files + `configtree` if appropriate |
| Kubernetes workloads | Secrets referenced via `secretKeyRef` or secret volumes paired with RBAC/encryption |
| Systems needing strict auditing, rotation, and least privilege | Secret manager and workload identity |
| Secrets needing zero-restart rotation | Explicitly designed and tested runtime refresh/rotation, not env vars alone |
| Test configuration | Placeholders/fixtures with no real privileges |

Good design ensures the application knows **which property names and data types it requires**, without knowing where real secrets are stored in source code. The deployment platform supplies access and values; Spring Boot's Binder converts them into typed configuration for beans to consume.

## 21. Principles to remember

1. **Do not equate config with secrets.** Timeouts and page sizes are usually config; passwords, tokens, and private keys are secrets.
2. **Never commit real secrets.** Including production-specific files or files added to `.gitignore` after already being exposed.
3. **Keep one artifact across environments.** Supply environment-specific values via deployment/config sources.
4. **Environment variables are only a transport channel.** They do not encrypt or hide secrets from anyone with machine/process access.
5. **Use a secret manager or permission-scoped mounts when appropriate.** Evaluate RBAC, auditing, encryption at rest, workload identity, and rotation.
6. **Never set weak fallbacks for mandatory secrets.** Test missing-secret scenarios and fail-fast policies.
7. **Never leak secrets via logs, Actuator, error responses, traces, or build artifacts.**
8. **Separate dev, test, and production secrets.** Never let testing environments access production credentials.
9. **Rotation must update consumers.** Updating a secret store does not automatically change Spring beans, process environments, or connection pools.
10. **Test with dummy values.** Tests should verify binding and error handling without requiring real secrets.

Conclusion: `application.yml`, profiles, and `@ConfigurationProperties` describe **what values the application needs and how it uses them**. Real secrets should be supplied from the deployment environment through an appropriate secure channel with least-privilege access, kept out of Git history, and backed by a rotation workflow. Properly separating these two responsibilities makes Spring Boot applications easy to deploy across environments while reducing the risk of credential exposure.
