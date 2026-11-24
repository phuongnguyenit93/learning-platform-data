# Classifying Regular Configuration Values and Secret Information

In Spring Boot, the same **Externalized Configuration** mechanism can provide both ordinary values such as `server.port=8080` and highly sensitive values such as database passwords, API tokens, or private keys. Both can appear as key/value pairs and be accessed via `Environment`, `@Value`, or `@ConfigurationProperties`. However, **how a value is read in Java does not determine whether it is safe to store in Git, display in logs, or include in reports**.

The key skill is **classifying before storing and using**: which values can be public, which values are internal only, which values are confidential data requiring restricted access, and which values are **secrets** that can directly grant system access if exposed.

This lesson guides you through identifying configuration data by risk, distinguishing *secrets* from *sensitive information that is not a credential*, organizing `application.yml` safely, choosing secret sources, limiting leaks via Git/CI/CD/logs/Actuator, implementing a Spring Boot example, and building a response process when secret exposure is suspected.

> **Principle:** Regular configuration can be version-controlled according to project policy; **real secrets must be managed through appropriate provisioning, authorization, protection, and rotation mechanisms**, never hardcoded in source code or committed configuration files.

## 1. Why classify before configuring?

Suppose an `application.yml` file contains:

~~~yaml
server:
  port: 8080

app:
  feature:
    catalog-preview-enabled: false
  external-api:
    base-url: https://partner.example.test
    api-key: REDACTED_EXAMPLE_ONLY
  billing:
    tenant-id: tenant-demo
~~~

Syntactically, `server.port`, `catalog-preview-enabled`, `base-url`, `api-key`, and `tenant-id` are all properties. But their risk levels differ:

- `server.port` is typically an operational parameter and cannot grant access on its own.
- A feature flag may just be a normal setting, though a flag that reveals release strategy or unreleased functionality can be internal.
- A public API base URL is usually not a secret, whereas an internal endpoint may reveal system topology and should have restricted distribution.
- An API key can be a **secret**: anyone possessing a valid key can call the API or consume quota, depending on the key's permissions.
- A Tenant ID is typically an **identifier**, not a password; however, it can still be internal data, a customer identifier, or contextually sensitive.

If you treat every property like ordinary data, you can easily commit credentials by mistake, print entire configuration objects in logs, or return tokens via debug support endpoints. If you treat every property like a secret, the system becomes hard to operate, hard to document, and hard to automate as needed.

Classification helps answer design questions: **where is the value stored, who may view it, may it appear in logs, can it have a default, how is it changed, and what do we do if it leaks?**

## 2. A practical taxonomy for Spring Boot configuration

You can start with four levels. The level names are suggestions; an organization may use a different policy.

| Level | Examples | Risk if exposed | Typical handling |
| --- | --- | --- | --- |
| Public or low-sensitivity | Local port, public feature name, general timeout | Low in many contexts | May reside in version-controlled configuration files if policy allows |
| Internal | Service name, internal hostname, unreleased feature flag, routing architecture | Reveals organization or infrastructure | Restrict who can read the repository and documentation |
| Confidential/sensitive data | Customer identifier, private endpoint, business identifier, personal data | May cause privacy/business risk | Access control, reduced logging, encryption/retention per policy |
| Authentication or cryptographic secret | Password, access token, API key, client secret, private key, signing key | May allow unauthorized actions | Secret manager or controlled secret store, never commit, rotate, and audit |

**A secret is a special kind of sensitive data because the value itself often has the ability to authenticate, decrypt, sign, or grant permissions.** Not all confidential data in the business sense is a credential; yet both still need appropriate protection mechanisms.

A value can change its classification level depending on context. A public endpoint URL may be public; the same URL containing a `token=...` query parameter requires the entire URL string to be protected as a secret. A standalone username usually cannot authenticate on its own, but a username can still be internal information or a personal identifier.

## 3. How to identify a real secret

Ask the following questions:

1. **Is this value used to authenticate or authorize?** If yes, it is usually a secret.
2. **Can someone holding this value read/modify data, sign requests, or consume resources?** If yes, strong protection is required.
3. **Can the value be used to decrypt encrypted data?** Decryption keys are secrets.
4. **Can the value impersonate a system or an identity?** Private keys and signing keys are secrets.
5. **Was the value issued by a provider along with permissions/quota?** API tokens/keys are usually secrets.
6. **Is the value just an identifier name or address with no ability to grant access?** It may still be sensitive, but it is not automatically an authentication secret.
7. **Does the value contain credentials inside a composite string?** The entire string must be evaluated, not just the key name.

Keys that commonly signal secrets:

~~~text
*.password
*.secret
*.token
*.api-key
*.private-key
*.client-secret
*.access-key
*.signing-key
*.credential
*.connection-string
~~~

These are only **indicators**, not a complete classifier. A key `app.demo.fake-token` may be a placeholder with no real permissions; conversely, `app.connection-url` may contain a username/password even though its name does not contain `password`.

### Do not rely on key names as the sole evidence

For example:

~~~properties
# Does not contain credentials in this example:
app.service.endpoint=https://api.example.test

# May contain real credentials if supplied as a DSN:
app.datasource.url=jdbc:postgresql://host.example.test/db?password=REDACTED

# May carry a token in the query string:
app.redirect-url=https://service.example.test/callback?access_token=REDACTED
~~~

When a URL, DSN, or configuration string has embedded credentials, **classify the entire value** at the required protection level. Do not mask only a key named `password` and leave the secret value appearing under a `url` key in logs.

## 4. Examples of classifying common properties

| Key or data type | Suggested classification | Reason |
| --- | --- | --- |
| `server.port` | Regular | Application port, does not authenticate by itself |
| `spring.application.name` | Regular/internal | May reveal system name |
| `logging.level.com.example` | Regular, but requires change control | Log level can increase data leak risk |
| `app.client.timeout` | Regular | Wait duration |
| `app.feature.new-checkout-enabled` | Internal depending on context | May reveal unreleased features |
| `app.partner.base-url` | Regular or internal | Public URLs differ from internal endpoints |
| `spring.datasource.username` | Internal or sensitive | Identifier; can aid exploitation when combined with other information |
| `spring.datasource.password` | Secret | Database access credential |
| `app.partner.api-key` | Secret | Can directly call the API |
| `spring.security.oauth2.client.registration.*.client-secret` | Secret | OAuth client credential |
| `app.jwt.signing-key` | Secret | Can forge tokens if the key is exposed |
| TLS private key | Secret | Proves the service's identity |
| TLS public certificate | Usually distributable | Public certificate does not contain the private key |
| Session identifier token | Secret | May allow session hijacking |
| `app.customer-id` | Internal/sensitive data | May relate to a customer |
| Password hash | Highly sensitive | May aid offline attacks; do not treat as public data |
| Data encryption key | Secret | Can decrypt stored data |
| Kubernetes Secret name | Regular/internal | Resource name is not the secret content; still reveals structure |

This table is only a guide: you must apply your organization's classification policy, deployment environment, regulatory requirements, and practical exploitability.

## 5. Separating regular configuration from secret values

A maintainable way to organize configuration is to **commit the structure and property names**, while supplying real secrets from the deployment environment.

For example, an `application.yml` file can be stored in the repository:

~~~yaml
spring:
  application:
    name: order-service

server:
  port: 8080

app:
  external-api:
    base-url: https://api.example.test
    timeout: 3s
    api-key: ${APP_EXTERNAL_APIKEY}
~~~

Meaning:

- `base-url` and `timeout` are regular configuration in this example.
- `api-key` is still a property that Java code can bind.
- `${APP_EXTERNAL_APIKEY}` is a placeholder that resolves a value supplied at runtime via the Spring Environment.
- The real value of `APP_EXTERNAL_APIKEY` **does not appear in the committed file**.

Note: a placeholder does not create a secret by itself and does not perform encryption. It only separates **where configuration is described** from **where the value is supplied**.

### Do not use fake defaults as production credentials

A risky pattern:

~~~yaml
app:
  external-api:
    api-key: ${APP_EXTERNAL_APIKEY:demo-secret}
~~~

If the environment variable is missing in production, the application may receive `demo-secret` and try to operate or fail at API call time. Depending on context, this fallback can mask deployment errors or cause a weak credential to appear in the system.

For required credentials, require full provisioning and use validation/fail-fast. For tests, inject separate fake values in the test context rather than using a production-like secret as a shared default.

## 6. Spring Boot binds secrets just like other properties

`@ConfigurationProperties` does not have an automatic "secret memory" safer than a regular String. The binder simply takes the effective value and converts it into a Java type.

Example:

~~~java
package com.example.orders.config;

import java.net.URI;
import java.time.Duration;

import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;
import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.validation.annotation.Validated;

@Validated
@ConfigurationProperties(prefix = "app.external-api")
public record ExternalApiProperties(
    @NotNull URI baseUrl,
    @NotNull Duration timeout,
    @NotBlank String apiKey
) {}
~~~

Bean registration:

~~~java
package com.example.orders;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.context.properties.ConfigurationPropertiesScan;

@SpringBootApplication
@ConfigurationPropertiesScan
public class OrderApplication {
    public static void main(String[] args) {
        SpringApplication.run(OrderApplication.class, args);
    }
}
~~~

Consumer example:

~~~java
package com.example.orders.client;

import com.example.orders.config.ExternalApiProperties;
import org.springframework.stereotype.Service;

@Service
public class ExternalApiClient {
    private final ExternalApiProperties properties;

    public ExternalApiClient(ExternalApiProperties properties) {
        this.properties = properties;
    }

    public boolean configured() {
        return properties.apiKey() != null
            && !properties.apiKey().isBlank();
    }
}
~~~

This is an example illustrating typed config injection, **not an example of sending credentials to an endpoint**. In a real application, the API client needs to place the key in the header specified by the provider and protect the connection with TLS; do not log the key.

`@NotBlank` helps detect an empty or missing secret in a properly validated model, but **does not evaluate the cryptographic quality** of the key and does not prove that the key is still valid on the provider's system.

### Records have a toString() risk

Java records automatically generate a `toString()` that includes their components. If `apiKey` is present, calling:

~~~java
System.out.println(properties);
~~~

can print the secret. **Do not log an entire configuration record containing credentials.** Similarly, Lombok `@Data` or `@ToString` on a properties class can cause passwords/tokens to appear in logs if not excluded.

If you must log configuration status, log only **whether the key is present**, a version, or reviewed non-sensitive metadata; do not log the secret value. Even logging the first or last few characters of a token needs a clear policy because it can aid correlation or exploitation.

## 7. @Value and Environment do not hide secrets automatically

The same key can be accessed in several ways:

~~~java
String apiKey = environment.getProperty(
    "app.external-api.api-key");
~~~

~~~java
public ApiAdapter(
    @Value("${app.external-api.api-key}") String apiKey
) {
    this.apiKey = apiKey;
}
~~~

~~~java
public ApiAdapter(ExternalApiProperties props) {
    this.apiKey = props.apiKey();
}
~~~

Whether read via `Environment`, `@Value`, or `@ConfigurationProperties`, **the value after being read is still a secret**. These mechanisms do not re-encrypt the secret, restrict who can debug the JVM, or prevent a developer from writing it to logs.

Specifically:

- `System.getenv("APP_EXTERNAL_APIKEY")` reads the process environment variable.
- `System.getProperty("app.external-api.api-key")` reads the corresponding Java system property if provided.
- `Environment.getProperty(...)` looks up across Spring `PropertySource`s in precedence order.
- `@ConfigurationProperties` binds the effective value into a Java object.

Do not treat switching from `@Value` to `@ConfigurationProperties` as a substitute for a secret manager. That is a change in **how code is organized**, not a change in the information protection model.

## 8. Secret supply sources: benefits and limitations

There are many ways to supply secrets to Spring Boot; none of them is secure just because it is called "external".

| Source | Convenience | Risks to control |
| --- | --- | --- |
| Local file outside repository | Easy to use on dev/server machines | Permissions, backups, copied files, files accidentally committed |
| Environment variables | Fits containers/CI, easy to reference | Can leak via debug, runtime inspection, crash dumps, or logs |
| JVM `-Dkey=value` | Convenient for Java systems | Command/process arguments, scripts, deployment logs may leak |
| App command-line `--key=value` | Easy to override | Arguments risk visibility in process listings, history/logs |
| File mounted by orchestrator | Separates secret from artifact | File read permissions, volume/mount, update lifecycle |
| Centralized secret manager | RBAC, audit, version/rotation depending on product | Must protect access identity and connection to the secret store |
| KMS / encrypted configuration | Protects stored data | Must manage decryption keys, permissions, and decryption timing |
| Kubernetes Secret | Deployment and container integration | Base64 is not encryption; requires RBAC and encryption at rest |

Therefore, the question is not just "put the secret in a file or env", but: **who provisions it, who can read it, can it leak at intermediate points, what permissions does it have, and can it be revoked if exposed?**

## 9. Why is hardcoding secrets in source code dangerous?

Anti-pattern example:

~~~java
public class DatabaseConfig {
    private static final String PASSWORD =
        "real-production-password-goes-here";
}
~~~

The problem does not stop at a Java file containing a password:

1. The secret enters Git history and can persist in older commits.
2. Forks, mirrors, CI caches, or archived builds may contain the value.
3. Code analysis tools, AI assistants, logs, or issues may accidentally copy it.
4. Packaged artifacts may contain the hardcoded string.
5. Changing the credential requires modifying code and re-releasing, making the secret lifecycle hard to control.
6. Deleting the line in a new commit **does not automatically revoke access for an exposed credential**.

Do not hardcode tokens, private keys, database passwords, or production credentials in Java source, committed YAML, resource files, Dockerfiles, or shared deployment scripts.

### Even a separate config file can still be committed

A file:

~~~text
src/main/resources/application-prod.yml
~~~

is also included in the artifact and can be committed. Simply having `prod` in its name or placing it in `resources` does not make it a safe place for secrets.

Similarly, Docker image layers can retain copied content even if a later build step deletes the file from the final filesystem. Avoid putting secrets into Docker build context/layers or artifacts unless a dedicated, appropriate secret-management mechanism is used.

## 10. .gitignore is a secondary barrier, not a secret manager

A repo can exclude local files:

~~~gitignore
# Example local filenames only; adjust to fit your project
.env.local
secrets/
config/local-secrets.yml
*.private-key.pem
~~~

This helps reduce accidental commits of **files not yet tracked by Git**. However:

- `.gitignore` does not automatically untrack files that have already been committed.
- Secrets can still leak via copy/paste, logs, CI artifacts, or email.
- A previously exposed file may remain in Git history.
- A file named differently from the convention can slip through.
- Even a private repository can be shared or accessed without authorization.

When you discover that a real secret was ever committed, **the first priority is to revoke or rotate the credential**, and only then remove the content from storage and history according to an appropriate process. Do not consider deleting the file in a new commit to be the end of incident handling.

## 11. Supplying secrets with environment variables

A simple pattern, suitable for many deployment platforms, is having Spring Boot receive values from environment variables supplied by the runtime.

Committed file:

~~~yaml
app:
  external-api:
    base-url: https://api.example.test
    timeout: 3s
    api-key: ${APP_EXTERNAL_APIKEY}
~~~

The runtime needs to supply `APP_EXTERNAL_APIKEY`. How it is supplied should come from the deployment platform's secret management system, not from a command containing the real key saved in shell history or job logs.

Spring Boot has relaxed binding for environment variable names. For the canonical key `app.external-api.api-key`, the corresponding variable name can be:

~~~text
APP_EXTERNAL_API_APIKEY
~~~

Here we must distinguish two paths:

- Placeholder `${APP_EXTERNAL_APIKEY}`: reads **the exact property name `APP_EXTERNAL_APIKEY`** used in the placeholder.
- Direct relaxed binding for `app.external-api.api-key`: converts the canonical name into the corresponding environment variable, typically `APP_EXTERNAL_API_APIKEY`.

The two naming conventions **do not automatically match** just because both aim to provide an API key. Choose one convention, document it clearly in the deployment contract, and test it. The YAML example above uses the placeholder `APP_EXTERNAL_APIKEY`; the platform must supply that exact name.

### Do not treat environment variables as absolute secrecy

Environment variables keep values out of the source repository, but they can be seen by processes with appropriate privileges, dumps, observability tools, deployment admin consoles, or debug commands. Restrict runtime access, disable printing the full environment, and do not export secrets via metrics/logs.

For some systems, file-mounted secrets with tight permissions or a secret manager accessed via an appropriate workload identity can reduce the risk of exposure via shell/process arguments.

## 12. Using Config Data configtree for file-mounted secrets

Spring Boot supports Config Data imports from a **configuration tree**: each file under a directory can supply a property, with the file's content as the property's value.

For example, a runtime mounts a directory:

~~~text
/run/secrets/
  app.external-api.api-key
  spring.datasource.password
~~~

Here the filename acts as the property name, and the file content (no real secret shown here) is the corresponding value.

You can use:

~~~properties
# application.properties
spring.config.import=configtree:/run/secrets/
~~~

At startup, if the location is readable, Spring Boot loads data from the config tree into the Config Data/Environment system accordingly.

With the file:

~~~text
/run/secrets/app.external-api.api-key
~~~

code can bind:

~~~java
@ConfigurationProperties(prefix = "app.external-api")
public record ExternalApiProperties(String apiKey) {}
~~~

### optional: and the production environment

For local environments without the mount, you may see examples like:

~~~properties
spring.config.import=optional:configtree:/run/secrets/
~~~

`optional:` allows skipping a nonexistent location according to Config Data rules. However, in production, if a secret is **required**, marking it optional without careful thought can mask configuration errors. Clearly define which environments may omit the mount, enforce required validation, and set an appropriate startup policy.

### File permissions and lifecycle

A config tree does not automatically make file contents secure. You must check:

- The mount path is readable only by the process that needs the secret.
- Secret volumes are not mounted into unrelated containers.
- User/group ownership and file mode are appropriate.
- Secrets are not copied into images, artifacts, or uncontrolled backup directories.
- Whether the platform's file-update mechanism actually causes the application to pick up new values.

Spring Boot Config Data is normally loaded at startup. A secret file rotated on a volume **does not automatically cause every `@ConfigurationProperties` bean to rebind**.

## 13. Kubernetes Secret: understanding its proper role

In Kubernetes, `Secret` is an API object used to hold sensitive data and supply it to workloads via env or volume. It is useful, but it is not an "absolute vault".

**Base64 is encoding, not encryption.** A manifest containing:

~~~yaml
apiVersion: v1
kind: Secret
metadata:
  name: external-api
type: Opaque
data:
  api-key: <BASE64_VALUE_REDACTED>
~~~

must not be considered safe to commit just because the value in `data` is encoded. Anyone with permission to read the manifest can decode it.

A container can reference a provisioned Secret object:

~~~yaml
env:
  - name: APP_EXTERNAL_APIKEY
    valueFrom:
      secretKeyRef:
        name: external-api
        key: api-key
~~~

This is only a container configuration fragment inside a Pod/Deployment, not a complete Kubernetes Deployment manifest. It does not contain a real secret value. You must protect the Secret object itself with RBAC, govern how it is created/updated, control who can read env at runtime, and enable encryption at rest for cluster data when appropriate.

### When using a volume mount

You can mount a Secret as files and use `configtree:/run/secrets/`. This is helpful when you want to avoid placing secrets into the process environment, though the files must still have proper permissions and applications must read them safely.

Kubernetes has a mechanism to update some types of secret volumes when a Secret changes, but **Spring Boot applications usually do not automatically refresh already-bound beans**. With env variables, the Pod/process typically needs to restart to receive the new value. Do not confuse "the volume file changed" with "the connection pool is using the new credential".

## 14. Centralized secret manager: boundaries of responsibility

A system can use a secret vault such as HashiCorp Vault or a cloud provider's secret manager service. Benefits can include:

- Access control by workload, environment, and resource.
- Versioning/rotation and revocation support.
- Access auditing (depending on product/configuration).
- Reducing the number of places where static secrets are stored.
- Separating application identity from secret data.
- CI/CD and orchestrator integration.

However, **how the application authenticates to the secret manager must also be protected**. If an unlimited token hardcoded in source is needed to fetch other secrets, the risk is merely shifted.

Common options to consider are workload identity, least-privilege service accounts, short-lived token issuance, or deployment platform identity. Spring Boot can receive data placed into the Environment via an appropriate integration or via platform-provided files/env.

**Do not assume every Spring Boot application supports every secret manager automatically without dependencies and integration configuration.** Choose an integration that genuinely fits your stack and version; avoid writing custom secret-fetching clients too early in startup and causing startup dependency cycles.

## 15. Secrets in database configuration

Some datasource parameters belong to the regular or internal category:

~~~properties
spring.datasource.url=jdbc:postgresql://db.internal.example.test:5432/orders
spring.datasource.username=orders_app
spring.datasource.hikari.maximum-pool-size=10
~~~

Whereas:

~~~properties
spring.datasource.password=REDACTED_EXAMPLE_ONLY
~~~

is a **secret** if it contains a real password. A safer approach is supplying the value outside committed files:

~~~properties
spring.datasource.password=${ORDERS_DB_PASSWORD}
~~~

Or keeping the shared config file without declaring the password and using environment binding or a config tree with the matching property name.

### Avoid embedding credentials in the JDBC URL

A URL containing `user=...` or `password=...` in the query/connection string can make **the entire URL sensitive**. When logging connection information, do not log the verbatim JDBC URL if it might contain credentials.

Do not use a generic `toString()` on datasource config for debugging. For configuration logs, display only selected attributes, such as a non-sensitive pool size, or a "credential configured" status without outputting the value.

## 16. OAuth2 client secrets, JWT signing keys, and private keys

Not every "token" plays the same role, but many types require protection.

### OAuth client secret

~~~properties
spring.security.oauth2.client.registration.partner.client-id=public-id-example
spring.security.oauth2.client.registration.partner.client-secret=${PARTNER_OAUTH_CLIENT_SECRET}
~~~

`client-id` is usually an identifier, not inherently secret, though it can be internal. `client-secret` is the credential that lets the client authenticate to the authorization server and must be protected.

### JWT signing key

If the application signs JWTs with a symmetric key, exposing the signing key allows forging valid signatures. It must be managed as a secret. If asymmetric keys are used, the **private key** for signing is a secret, while the public key can be distributed to verifiers by design.

Do not print keys, PEM private content, or valid tokens into logs; do not use a "demo key" as a production default.

### A certificate is not the same as a private key

A public certificate file can be shared by TLS design. However, the corresponding private key **must not** be placed in public artifacts or repositories. If a keystore file contains both a private key and a certificate, classify the entire file at the required protection level.

Even the passphrase protecting a keystore is a secret; do not hardcode it in the same committed file.

## 17. Do not overlook secrets inside composite strings

Many leaks come from a property whose name does not sound like a secret:

~~~properties
app.partner.connection-string=...
app.partner.url=...
app.legacy.headers=...
app.proxy.url=...
app.callback.template=...
~~~

These strings can carry:

- Username/password in URL userinfo.
- Query parameters such as `api_key`, `token`, or `signature`.
- Authorization headers or cookies.
- A DSN containing credentials.
- A presigned URL with a signature and expiration.
- A session identifier, password reset token, or one-time code.

For example, strings like:

~~~text
https://user:REDACTED@example.test/path
https://example.test/download?signature=REDACTED
~~~

must be treated as sensitive even if the enclosing key is simply named `endpoint` or `url`.

**Rule:** classify based on **content, purpose, and the access the value grants**, not solely on property-name regexes. Do not allow logging full query strings if they can carry credentials.

## 18. Beware of logs and exceptions

A dangerous example:

~~~java
log.info("Loaded external API config: {}", properties);
~~~

If `properties` is a record containing `apiKey`, the log can expose the secret.

Equally dangerous:

~~~java
log.debug("Environment: {}", System.getenv());
log.info("API key: {}", apiKey);
log.error("Connection failed with properties {}", connectionOptions);
~~~

Avoid indiscriminately printing `Environment`, system properties, `Authorization` headers, cookies, connection options, or request/response bodies containing credentials.

### How to log usefully?

A message can contain only status:

~~~java
log.info(
    "External API configured: endpointPresent={}, credentialPresent={}",
    properties.baseUrl() != null,
    properties.apiKey() != null
        && !properties.apiKey().isBlank()
);
~~~

In the example, no real value is logged. Even so, whether "credential is present" can be publicly exposed varies; this log is still internal operational data. For high-risk fields, log only a classified status code.

### Redaction must be applied before output

When a system uses structured logging, log appenders, APM, or tracing, ensure sensitive fields are stripped/masked **before** sending. Do not rely solely on a filter layer at the end of the pipeline, because copies of the secret may already have appeared in stdout, agents, queues, or buffers.

When a secret appears in an exception message from a library, apply a safe exception logging policy. Do not swallow all exceptions and lose diagnostic capability; preserve the error type, key/path, and necessary metadata without exposing secret contents.

## 19. Spring Boot Actuator env and configprops

Spring Boot Actuator provides diagnostic endpoints such as `env` and `configprops`. They are useful for understanding property sources and typed configuration, but **they can leak environment information if access is misconfigured**.

Do not expose configuration diagnostic endpoints to the public Internet. Protect them with authentication, authorization, network restrictions, and the principle of granting access only to appropriate operators.

In Spring Boot versions that support them, properties such as:

~~~properties
management.endpoint.env.show-values=never
management.endpoint.configprops.show-values=never
~~~

are one way to configure not showing values through these two endpoints. Other options like `when-authorized` or `always` (when supported by the version) must be weighed very carefully, because they can broaden who can view configuration information. Always consult the exact Spring Boot version running and the security configuration.

### Masking does not replace access control

Even when values are masked, **key names, profiles, configuration sources, property structures, or origins** can reveal infrastructure details. Do not treat all metadata in Actuator as public.

In addition, Actuator masking values **does not protect** a secret if a custom controller, log statement, or another library's exception outputs it. Protection must be applied at every boundary.

## 20. Be careful with debugging, heap dumps, and thread dumps

A secret loaded as a `String` can remain in JVM memory for the lifetime of the running application. Diagnostic tools with appropriate access can inspect memory regions or process information.

Points to watch out for:

- Heap dumps can contain objects with passwords/tokens.
- Core dumps or crash artifacts can contain sensitive data.
- Process arguments can expose values passed directly via `--key=value` or `-Dkey=value`.
- Debuggers and JVM attach permissions can access runtime information.
- APM/tracing sometimes captures request headers or parameters unless filtering is configured.
- Log files and backups can retain data long after a request finishes.

No single Java technique completely removes every copy of a secret from memory. Restrict server/process access, control retention, and restrict access to dumps/logs/artifacts.

### Do not pass secrets on the command line if a better channel exists

A syntax example:

~~~bash
java -Dapp.external-api.api-key=REDACTED -jar app.jar
~~~

is **an illustration of one property-supply path**, not a recommendation to put real tokens on the command line. In environments supporting a secret manager, file-mounted secrets, or controlled runtime injection, prefer channels with lower exposure.

## 21. Secrets in CI/CD and build pipelines

A pipeline may need credentials for deployment or integration testing. Common risks:

- Printing env vars in a debug step.
- Running shell commands with secrets in arguments and logging the entire command.
- Writing secrets into artifacts, test reports, caches, or downloadable workspaces.
- Granting production credentials to all branches or untrusted pull requests.
- Forked/untrusted code running in jobs with permission to read secrets.
- Failing to revoke temporary credentials after a job finishes.
- Sharing a single credential across build, deploy, and runtime, resulting in overly broad permissions.

### A better workflow

1. Separate build/test from deployment jobs that require secret permissions.
2. Supply secrets only to the jobs and environments that truly need them.
3. Prefer short-lived identities or workload identities when supported by the platform.
4. Do not run untrusted code with credentials that have production permissions.
5. Enable appropriate masking, but do not treat masking as the sole safeguard.
6. Reduce secret lifetimes and artifact retention.
7. Audit access permissions and job behavior.

For Docker builds, avoid placing secrets in `ARG`/`ENV` that artifacts or layers might store. If a build genuinely needs credentials to fetch dependencies, consider the build system's dedicated secret mount mechanism instead of copying credentials into the image.

## 22. Least privilege: secrets do not just need hiding, they need scoped permissions

Suppose an API key only needs to list orders. If you grant it system-wide admin rights, hiding the key still does not reduce **the blast radius if the key leaks**.

Least-privilege principles:

- Credentials only have permission to call the exact required API/operations.
- Database users only have the necessary schema/table/permissions.
- Separate read keys and write keys when business logic allows.
- Do not use a database superuser for an ordinary service.
- Separate development, staging, and production environments.
- Separate credentials across services/tenants when appropriate.
- Limit quotas, network policies, IP allowlists, or usage scopes when supported by the platform.
- Prefer short-lived or rotatable secrets.

A good secret management system does not merely store "secret strings"; it also manages **identity, authorization, auditing, and permission revocation**.

## 23. Separating secrets by environment

A dangerous design mistake is using the same API key for local development, test, staging, and production. In that case, a compromised laptop or experimental pipeline can lead to losing control of production.

An illustrative policy table:

| Environment | Regular configuration values | Credentials |
| --- | --- | --- |
| Local development | Mock URLs, dev timeouts, local ports | Dedicated dev/test credentials, least privilege |
| CI unit test | Test config and mocks | No real secrets needed |
| Integration test | Sandbox endpoints | Scoped sandbox secrets |
| Staging | Staging endpoints | Staging credentials, never production |
| Production | Production endpoints | Production credentials via tightly controlled channel |

You can use Spring profiles to select **differing regular values**:

~~~yaml
# application-dev.yml
app:
  external-api:
    base-url: https://sandbox.example.test
~~~

~~~yaml
# application-prod.yml
app:
  external-api:
    base-url: https://api.example.test
~~~

However, do not put real credentials directly into a committed `application-prod.yml`. Profiles select Config Data; **they are not a security boundary** and do not encrypt secrets.

## 24. Classifying by lifecycle: static, short-lived, rotating

Not all secrets have the same lifecycle.

**Static credentials:** passwords/long-lived API keys may be stored for months. They require a rotation policy, scoped permissions, and a revocation procedure.

**Short-lived credentials:** access tokens, session tokens, or temporary cloud credentials with short lifetimes. They require issuance and refresh mechanisms, never committed to files.

**Signing or encryption keys:** affect data that has already been signed/encrypted. Rotation must account for key versioning, verifying older tokens, decrypting historical data, and transition windows.

**mTLS keys/certificates:** the private key is a secret; the public certificate has an expiration lifecycle. A renewal policy and the application's ability to load the new key/certificate pair are required.

### Why is rotation not just changing an environment variable?

Spring Boot typically binds configuration properties at startup. If a secret is changed in the secret store, the application may continue using old instances:

- HikariCP or a connection pool may retain credentials to open connections.
- An HTTP client may retain an Authorization header/token provider.
- Immutable beans may retain bound values.
- Pod env vars may not change until restart.
- Some secret manager integrations support refresh, but they must be configured and tested.

Rotation design must define **when consumers start using the new credential** and **when the old credential is revoked**, not just updating the store.

## 25. Zero-downtime rotation process

A general example for an API key can have an overlap phase:

1. Issue a new secret with least privilege.
2. Update the secret manager or deployment reference.
3. Restart/refresh the necessary workloads according to platform capabilities.
4. Verify that new requests use the new key and succeed.
5. Revoke the old key after ensuring all workloads have switched over.
6. Record the timestamp and operator per audit policy.
7. Confirm the old key no longer remains in pipelines, servers, or easily accessible backups.

The actual process depends on whether the provider supports two active keys simultaneously. If only one active key is supported, a different cutover plan is needed to minimize downtime.

**Avoid logging the real key during verification.** You may log a non-sensitive key version or identifier supported by the system, though even such metadata should be evaluated before display.

## 26. When secret exposure is suspected: priority response

Suppose a production credential is found in a commit, log, ticket, or screenshot. Do not simply delete the line and consider it done.

General response process:

1. **Determine the scope:** which secret, what permissions, how long it may have been exposed, where it was copied.
2. **Trigger incident response** according to the organization's security process.
3. **Revoke/rotate the credential** as promptly as appropriate for the risk level and service continuity requirements.
4. **Assess potential abuse** using audit logs, API usage, and related indicators.
5. **Remove or restrict copies** in Git, CI logs, artifacts, issues, chat, paste services, and caches as feasible.
6. **Re-release/update the application** to use the new credential.
7. **Improve prevention:** secret scanning, controls, and access control.
8. **Report/review** in accordance with internal policy and applicable obligations.

With Git, cleaning history may require rewriting history, which affects clones/forks and team workflows. **Deleting history does not make an exposed credential safe again**: rotating/revoking the credential remains the primary measure.

Do not paste the verbatim secret back into incident reports, chat notices, or documentation examples. Use classified IDs/versions and metadata.

## 27. How to inspect repositories and configurations safely

A development team can apply secret scanning in pre-commit hooks, CI, and repository monitoring. Indicators include:

~~~text
api_key=
client_secret:
BEGIN PRIVATE KEY
Authorization: Bearer ...
password=...
jdbc:...password=...
~~~

Scanners can detect many patterns but also have false positives/false negatives. Do not conclude "scanner passed means the repository has no secrets." Encoded values, split fragments, or values in binary files can be hard to detect.

During code review, ask:

- Does the file contain real values or only placeholders?
- Are production credentials included in sample/test data?
- Do example URIs contain query tokens?
- Do Docker images or pipelines print `env`/system properties?
- Do property beans have a default `toString()` and get logged?
- Could CI artifacts and backups contain secrets?
- Do config tree/secret mounts have overly broad read permissions?

Do not require developers to copy real secrets into pull requests to prove configuration works. Use fake secrets and appropriately authorized integration tests.

## 28. Testing without production secrets

A service unit test should receive a configuration object using fake values, for example:

~~~java
import java.net.URI;
import java.time.Duration;

ExternalApiProperties properties = new ExternalApiProperties(
    URI.create("https://api.example.test"),
    Duration.ofSeconds(1),
    "fake-test-credential-not-valid"
);
~~~

This is a fake value, not a secret capable of accessing a system. Test logic with a mock HTTP client or fake server as appropriate.

To test Spring Boot binding:

~~~java
import static org.assertj.core.api.Assertions.assertThat;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;

@SpringBootTest(properties = {
    "app.external-api.base-url=https://api.example.test",
    "app.external-api.timeout=2s",
    "app.external-api.api-key=fake-test-credential-not-valid"
})
class ExternalApiPropertiesTest {

    @Autowired
    ExternalApiProperties properties;

    @Test
    void bindsConfiguredValues() {
        assertThat(properties.baseUrl().getHost())
            .isEqualTo("api.example.test");
        assertThat(properties.timeout().toSeconds()).isEqualTo(2);
        assertThat(properties.apiKey()).isNotBlank();
    }
}
~~~

The test assumes `ExternalApiProperties` is properly scanned/enabled and the project has the required dependencies. The goal is to verify typed binding, **without calling the provider API with real credentials**.

### Testing fail-fast when a secret is missing

You can create a test context without providing `app.external-api.api-key` and verify that startup fails due to the `@NotBlank` constraint when Bean Validation is enabled and the model is registered. With integration tests using `@SpringBootTest`, failing the entire context can happen before test methods run; `ApplicationContextRunner` is often more convenient for asserting startup failure.

If `application.yml` has a required placeholder and the test does not supply the variable, the failure may come from placeholder resolution before Bean Validation runs. Distinguish the cause in tests rather than assuming every missing-secret failure is `@NotBlank`.

## 29. Default policy: regular data and secrets differ

Regular configuration can have safe defaults:

~~~yaml
app:
  client:
    timeout: 3s
    max-retries: 2
~~~

However, production credentials usually should not have shared defaults:

~~~yaml
app:
  external-api:
    api-key: ${APP_EXTERNAL_APIKEY}
~~~

Some tests may use fixed fake credentials within test scope, but fake credentials **must have no production access**.

### Why are secret defaults dangerous?

- They mask unconfigured deployments.
- They encourage sharing the same credential across environments.
- A "demo password" can end up in production.
- They are hard to rotate and revoke because multiple workloads share them.
- A default hardcoded in a library can be extracted from the artifact.

**Rule:** operational parameters may have defaults if safe; required secrets should be supplied from the appropriate environment and validated. Do not "fail open" when a credential is missing.

## 30. Masking and redaction: limitations

Suppose a log needs to record a property name:

~~~text
app.external-api.api-key = [REDACTED]
~~~

Masking values with `[REDACTED]` is useful, but be careful:

- A value may appear multiple times in other fields.
- A secret may reside in a URL, stack trace, or header rather than a field named `api-key`.
- Some libraries log request bodies or error details.
- Base64/URL encoding makes regex detection harder.
- A log already emitted before masking is enabled does not disappear by itself.
- A partially exposed token can still assist correlation or attacks in some systems.

Apply an **allowlist of logged fields** rather than logging everything and trying to mask keys with sensitive names. Regex redaction is a supplementary defense layer, not the entire strategy.

Be especially careful when formatting:

~~~java
log.info("Configuration: {}", properties);
~~~

because a record/Lombok-generated `toString()` can print many secret fields without the log author noticing.

## 31. How to organize configuration trees and file layouts

A project can separate:

~~~text
src/main/resources/
  application.yml
  application-dev.yml
  application-prod.yml

external runtime:
  /run/secrets/
    spring.datasource.password
    app.external-api.api-key
~~~

Classification:

- `application.yml`: general settings, property names, timeouts, containing no real secrets.
- `application-dev.yml`: local/sandbox endpoints, containing no real credentials in Git.
- `application-prod.yml`: non-secret settings for production or placeholders per the deployment contract.
- `/run/secrets`: secret data mounted by the runtime/secret manager, with restricted permissions.
- CI/CD: responsible for supplying references and usage permissions, not exposing values.

An external secret source can be a file, environment variable, or service; the layout above is an example, not a requirement that every application use `/run/secrets`.

### Do not embed secrets in filenames/paths

Avoid putting credentials in filenames or directory names such as:

~~~text
/run/secrets/token-realvalue-...
~~~

Filenames can be logged or displayed in diagnostics. Use **stable property names that do not contain secret content**. If versioning is needed, use a non-sensitive metadata/version ID by design.

## 32. Protecting access in code and at runtime

Secrets must exist where the application can use them, but that does not mean every component in the same application needs to read them.

Design suggestions:

- Only client beans that need credentials should inject typed credentials/config.
- Do not put credential objects into DTOs returned by controllers.
- Do not serialize `@ConfigurationProperties` containing secrets into JSON debug endpoints.
- Do not pass credentials across layers that do not need to know them.
- Do not use secrets as message queue payloads or events.
- Do not put secrets into metric labels or tracing attributes.
- Do not expose secrets via error responses to users.
- Restrict OS/container permissions of the process and read permissions of mounts.
- Control diagnostic endpoints, heap dumps, and debugger attach permissions.

Within the same JVM, separating beans **is not absolute security isolation**; privileged code in the same process can still access memory or context. However, clear dependency boundaries help reduce misuse and reduce where secrets are copied.

## 33. Sensitive non-credential data still needs control

A configuration entry might be:

~~~properties
app.billing.customer-tenant-id=tenant-demo
app.ops.internal-runbook-url=https://internal.example.test/runbook
app.feature.unannounced-pricing-enabled=false
~~~

These values may not allow direct authentication. However, they can reveal customer data, operational procedures, or business plans.

Do not force all such values into a secret store simply because they are "internal"; choose protection levels based on risk, policy, and distribution paths. For instance, an internal feature flag can live in a separate config repository with RBAC; a customer identifier may need to be handled under personal data policies.

**Classification helps distinguish protection goals:**
- Protect **access rights** (credentials).
- Protect **privacy** (PII).
- Protect **business confidentiality** (internal content).
- Protect **configuration integrity** (settings whose change can make the system insecure).

Even `logging.level` or `security.enabled` is not a secret, yet changing them can be dangerous. That is why separate change control is needed for **non-secret values with major security impact**.

## 34. Controlling configuration integrity

The question "is this value a secret?" differs from "who is allowed to change this value?".

Examples:

~~~properties
management.endpoints.web.exposure.include=health
app.security.enforce-mfa=true
app.rate-limit.enabled=true
~~~

The settings above are not necessarily secrets. Yet changing them can affect the attack surface or defensive capabilities.

Therefore, even regular configuration may need:

- Code review/approval before changes.
- Git protection and change history.
- Deployment promotion across environments.
- Schema/validation checks.
- Change auditing and controlled rollback.
- Authorization for production updates.

**Secrecy classification and integrity-criticality classification are two distinct axes.** A non-secret setting can still require strict change control.

## 35. Common mistakes and root causes

| Symptom | Common cause | Resolution |
| --- | --- | --- |
| Secret appears in Git | Real value committed to YAML/`.env` | Rotate/revoke, clean history, and strengthen controls |
| App runs locally but fails in production due to missing key | Deployment did not supply secret or wrong variable name | Check runtime contract, fail fast |
| App uses wrong credential despite right file | Another env/CLI/Config Data source overrides it | Check precedence and effective source without printing values |
| Token appears in logs | Logged full config, headers, request body, or `toString()` | Reduce logged data, redact, and handle copies |
| Actuator exposes configuration | Broad endpoint access or `show-values` enabled | Restrict access, configure masking |
| Mounted file changes but app still uses old key | Bean/client connection did not refresh | Design restart/rebind/rotation |
| Kubernetes Secret base64 thought to be encrypted | Confusing encoding with encryption | RBAC, encryption at rest, restrict access |
| Same API key shared across all environments | Dev/staging/prod not separated | Separate scope and provision per environment |
| Secret has admin privileges | Least privilege not applied | Reduce privileges and rotate credential |
| CI uploads artifacts containing secrets | Script/log/cache or build layer retained value | Narrow scope, delete/revoke, inspect pipeline |
| Seemingly regular URL contains query token | Classified by key name instead of content | Protect entire URL and remove credentials from URL if possible |
| Tests require production credentials | Tests not mocked or lacking sandbox identity | Use fakes, mocks, or dedicated sandbox secrets |

To diagnose, distinguish **secret provisioning errors**, **authorization errors**, **conversion/binding errors**, and **credential usage errors at the provider**. A present secret that is invalid or revoked can cause the API to return 401/403; that is not necessarily a Spring Boot Binder bug.

## 36. Implementation workflow in a Spring Boot project

A reference workflow:

1. **Inventory property contracts** of the service: keys, data types, environments, owners.
2. **Classify** into public/internal/confidential/secret based on actual risk.
3. **Determine value sources**: code repository for normal config; secret manager/runtime injection for secrets.
4. **Never commit secret values**. Store only key names/placeholders/fake samples.
5. **Design typed config** with `@ConfigurationProperties`, validation for required keys, and no logging of objects containing secrets.
6. **Restrict permissions** to access the secret store and the resources the credential grants access to.
7. **Protect observability**: log allowlists, masking, Actuator, tracing, dumps, and artifacts.
8. **Test** with fake/sandbox credentials, verifying fail-fast when missing.
9. **Define rotation**: how to update, restart/refresh, overlap window, and revocation.
10. **Monitor and respond to leaks**: secret scanning, auditing, incident response.
11. **Control changes** for regular settings that carry security impact.
12. **Update deployment documentation** with variable/key names and policies, never publishing real values.

This is a lifecycle-wide protection process, rather than just editing an `application.properties` file.

## 37. Classification exercises

### Exercise 1 — server.port

~~~properties
server.port=8080
~~~

**Question:** Is this a secret?

**Answer:** Usually not. It is an operational parameter. Even so, changing the port may require control under deployment policy.

### Exercise 2 — URL with token

~~~properties
app.partner.url=https://api.example.test/items?token=REDACTED
~~~

**Question:** Can the URL be logged verbatim because the key name is `url`?

**Answer:** No. A URL with a token must have its entire value protected or be redesigned to remove credentials from the URL per the appropriate API.

### Exercise 3 — database username and password

~~~properties
spring.datasource.username=orders_app
spring.datasource.password=REDACTED
~~~

**Answer:** The password is a secret. The username is usually an identifier/internal, though it should not automatically be considered public in all contexts.

### Exercise 4 — public certificate and private key

There is a PEM file containing a public certificate and a PEM file containing the corresponding private key.

**Answer:** The public certificate can usually be distributed per TLS design; the private key is a secret. If both are packaged in a keystore, the keystore must be protected accordingly.

### Exercise 5 — feature flag

~~~properties
app.feature.unannounced-pricing-enabled=true
~~~

**Answer:** Not necessarily an authentication secret. However, it can be sensitive internal information requiring access and change control.

### Exercise 6 — environment variable

The runtime supplies `APP_EXTERNAL_APIKEY`. **Question:** Is the value completely safe?

**Answer:** Not yet. It is not in Git, but it can still leak via process inspection, logs, dumps, or privileged deployment tools. Access must be restricted and intermediate points protected.

### Exercise 7 — secret in Git

A real API key was committed yesterday, and today a developer deleted that line.

**Answer:** Not yet resolved. You must assess the incident, revoke/rotate the key, check copies and history, and then improve controls.

### Exercise 8 — Kubernetes data field

A Secret manifest contains `data.api-key` in base64. **Question:** Can it be committed publicly because it is "encrypted"?

**Answer:** No. Base64 is only encoding; it does not stop readers from decoding the secret.

### Exercise 9 — record toString

A record `ExternalApiProperties(String apiKey)` is printed to logs as `log.info("{}", props)`.

**Answer:** There is a risk of printing the plaintext key from the default `toString()`. Do not log the object; replace with selected status information.

### Exercise 10 — rotation

The secret store updated the database password, but HikariCP still uses the old credential.

**Answer:** Updating the store does not guarantee pools/beans update automatically. You must design refresh/restart/recreation of the connection pool according to your deployment model.

### Exercise 11 — application-prod.yml

The production file contains the database host, timeout, and password.

**Answer:** Host/timeout can be non-secret or internal depending on context; the password is a secret and must not be committed. Keep host/timeout in appropriate Config Data, with the password supplied at runtime.

### Exercise 12 — security setting

~~~properties
app.security.enforce-mfa=false
~~~

**Answer:** The boolean value itself is not a secret, but changing it poses a major risk to configuration integrity. It requires review/approval, not just hiding the value.

## 38. End-of-lesson checklist

| Question | What to verify |
| --- | --- |
| Does the value directly authenticate, sign, or decrypt? | Classify as a secret |
| Is the value only an address/identifier? | Assess contextual sensitivity and combination risks |
| Does a URL/DSN have embedded credentials? | Protect the entire value |
| Is the secret in Git/source/artifacts? | Remove safely, rotate if exposed |
| Is there a placeholder while the runtime lacks a value? | Have clear validation/fail-fast |
| Can env/CLI be exposed in logs/process listings? | Reduce exposure and access permissions |
| Does the config tree mount have right permissions? | Check file/volume access |
| Does the Kubernetes Secret have RBAC and at-rest protection? | Do not mistake base64 for encryption |
| Does the secret manager use an appropriate workload identity? | Do not hardcode a credential to fetch other credentials |
| Does the config bean have a `toString()`/log secret risk? | Do not print objects containing secrets |
| Are Actuator `env`/`configprops` protected? | Limit exposure, `show-values`, authorization |
| Does CI log environments or artifacts containing keys? | Reduce secret scope and retention |
| Does the secret have least privilege and environment separation? | RBAC/scope/dev-staging-prod |
| Are rotation and incident response in place? | Ability to revoke and update consumers |
| Do tests use fake/sandbox secrets? | Avoid production credentials in unit tests |
| Non-secret settings with security impact? | Change control and integrity checks |

## 39. Conclusion

Spring Boot Externalized Configuration is a mechanism for supplying and binding key/value pairs; **it does not automatically turn every value into protected data**. Proper classification determines how values are stored, authorized, logged, provisioned, and revoked.

You can remember three decision groups:

1. **Regular configuration:** ports, timeouts, retry counts, service names, public endpoints — can be version-controlled if they contain no sensitive information and comply with policy.
2. **Internal/sensitive configuration:** private hostnames, customer identifiers, unreleased feature flags, operational details — control access and distribution based on context.
3. **Secrets:** passwords, API tokens, private keys, client secrets, signing/encryption keys — never hardcode/commit, supply via controlled channels, restrict permissions, mask in observability, and plan rotation.

**Classification is not just looking at key names.** You must evaluate **actual content, the permissions the value grants, the possibility of combining it with other data, and the impact of exposure**. A secure project keeps secrets out of source, limits privileges in use, prevents secrets from being copied via logs/Actuator/CI/artifacts, and controls changes to ordinary settings that impact security.
