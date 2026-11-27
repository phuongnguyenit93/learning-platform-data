# Environment-Based Configuration Packaging and Secret Separation

A Spring Cloud application typically runs across multiple environments such as local, test, staging, and production. Each environment has different endpoints, resource limits, feature flags, and connection details. If you create a separate build for each environment or place passwords directly inside packaged configuration files, releasing software and controlling security become difficult.

The right approach is to **build an immutable artifact and supply configuration externally at deployment time**. Non-sensitive values can be organized using profiles, external configuration files, or Spring Cloud Config. Passwords, tokens, private keys, and credentials should be provided by a secret manager or the deployment platform's secret store, with separate access permissions per workload.

Spring Boot provides Config Data, profiles, environment variables, and configuration trees to merge configuration sources into the Environment. Spring Cloud Config adds a centralized configuration store organized by application, profile, and label. Spring Cloud Vault can bring secrets from Vault into the Environment through the Config Data API. These mechanisms work together, but each has its own responsibility.

This lesson belongs to the **Operations** chapter of the **SPRING_CLOUD_CORE** module. Learners will design environment-based configuration packaging, separate public data from secrets, choose appropriate configuration sources, control precedence order, and test the deployment process.

## 1. Learning Objectives

After this lesson, learners can:

1. Explain the principle of deploying one artifact across multiple environments.
2. Classify default configuration, environment-specific configuration, and secret data.
3. Use Spring profiles and Config Data to load environment-specific configuration.
4. Externalize configuration outside the JAR using files, environment variables, or configuration trees.
5. Use Spring Cloud Config by application, profile, and label.
6. Use Spring Cloud Vault or a secret manager to provide credentials.
7. Distinguish between ConfigMap and Secret and understand the limitations of Base64 encoding.
8. Control PropertySource precedence and avoid unsafe secret fallbacks.
9. Bind typed configuration using ConfigurationProperties and validation.
10. Design pipelines for promotion, rollback, rotation, and configuration testing.
11. Protect secrets in repositories, container images, logs, Actuator, and runtime.
12. Diagnose issues caused by incorrect profiles, Config Server, Vault, or secret mounts.

## 2. Principle: One Artifact, Multiple Environments

### 2.1. Do Not Rebuild Just to Change Endpoints

Suppose the same Orders service needs to run in three environments:

| Property | Development | Staging | Production |
| --- | --- | --- | --- |
| Inventory API | inventory-dev.internal | inventory-stg.internal | inventory.internal |
| Log level | DEBUG | INFO | WARN |
| Max connections | 5 | 10 | 40 |
| Experimental features | Can be enabled | Controlled testing | By approval |
| Database credential | Dev credential | Staging credential | Production credential |

Source code and executable artifacts do not need to change just because endpoints or resource limits differ. Each environment provides its own configuration values at startup.

~~~mermaid
flowchart TD
    A[Source code] --> B[Build once]
    B --> C[Immutable artifact]
    C --> D[Deploy Development]
    C --> E[Deploy Staging]
    C --> F[Deploy Production]
    D --> G[Config dev + secrets dev]
    E --> H[Config staging + secrets staging]
    F --> I[Config production + secrets production]
~~~

The same JAR or container image is promoted across environments. The pipeline only changes deployment parameters and the configuration sources supplied to the workload.

### 2.2. Why Should Artifacts Be Immutable?

If each environment has a different build, the following situations can occur:

- Staging tested one binary, but production runs a different binary.
- A build accidentally contains endpoints or secrets from another environment.
- Rollback must locate the right artifact for each environment.
- It is hard to prove that the production binary is the exact binary that was tested.
- Configuration changes inadvertently trigger code rebuilds and redeployments.

Using the same artifact separates two activities:

- **Build:** produce a binary or image from source code and version-locked dependencies.
- **Deploy/configure:** run that artifact with the target environment's configuration and secrets.

An artifact should be identified by a version or digest. The pipeline can record the digest that ran in staging and then promote that exact digest to production.

### 2.3. Not Everything in Configuration Is a Secret

Not every value that changes per environment needs to be placed in a secret manager. For example:

- Internal service URLs.
- Log levels.
- Timeouts.
- Worker counts.
- Non-sensitive feature flags.
- Queue or topic names.
- Retry limits.

These values can reside in profiles or Config Server. Passwords, API tokens, private keys, signing keys, and credentials must be protected separately.

## 3. Classifying Configuration Data

Before choosing tools, classify each property by its nature and lifecycle.

| Category | Examples | Suitable Storage | Notes |
| --- | --- | --- | --- |
| Safe default values | Default timeout, log pattern | application.yml in artifact | Contains no environment-specific details |
| Environment configuration | Endpoint, region, replica hint | Profile, external file, Config Server | Can be version controlled |
| Feature flag | Feature mode | Config Server or feature flag service | Requires audit and rollout |
| Credential | Password, token, API key | Vault, secret manager, platform Secret | Never commit plaintext |
| Encryption key | Private key, signing key | KMS, HSM, Vault, or secret store | Restrict workloads allowed to read |
| Runtime data | Actual port, instance ID | Runtime/platform | Do not package into artifact |

### 3.1. Default Values Should Be Safe

Packaged configuration files should contain default values that pose no risk if the application starts in a new environment.

~~~yaml
spring:
  application:
    name: orders-service

server:
  shutdown: graceful

app:
  partner:
    connect-timeout: 500ms
    read-timeout: 2s
    retry:
      max-attempts: 2
~~~

This example contains no production hosts, usernames, or passwords. Values that vary by environment will be supplied from external sources.

### 3.2. Do Not Use Default Values for Required Secrets

Do not write:

~~~yaml
spring:
  datasource:
    password: default-password
~~~

If the secret source is missing, the application might start with the default credential without operators noticing.

For required secrets, leave the property without a default value and let validation fail startup when missing. If the application has a local mode requiring dummy credentials, provide those credentials from a test fixture or separate local secret, not packaged as a production default.

### 3.3. Profiles Are Not a Security Boundary

Profiles such as dev, staging, and prod help select appropriate configuration. However, profiles do not grant or enforce data access permissions by themselves. Someone can change the profile or call endpoints if infrastructure does not enforce access control.

Do not place production secrets in `application-prod.yml` and assume the file is safe just because it is only loaded when the `prod` profile is active. If the file resides in the JAR or a repository readable by many people, the secret has already been shared with them.

## 4. Spring Boot Config Data and Profiles

### 4.1. Common Files and Profile-Specific Files

Spring Boot supports files such as:

- `application.yml`: common configuration.
- `application-local.yml`: local configuration.
- `application-test.yml`: test configuration.
- `application-staging.yml`: staging configuration.
- `application-prod.yml`: production configuration.

Example structure:

~~~text
src/main/resources/
  application.yml
  application-local.yml
  application-test.yml
  application-staging.yml
  application-prod.yml
~~~

`application.yml` contains shared configuration. When a profile is activated, the corresponding file is loaded and matching keys can override shared values.

Example `application.yml`:

~~~yaml
app:
  inventory:
    base-url: http://localhost:8081
    connect-timeout: 500ms
    read-timeout: 2s

logging:
  level:
    root: INFO
~~~

`application-staging.yml`:

~~~yaml
app:
  inventory:
    base-url: https://inventory-stg.internal
    connect-timeout: 1s
    read-timeout: 3s
~~~

`application-prod.yml`:

~~~yaml
app:
  inventory:
    base-url: https://inventory.internal
    connect-timeout: 700ms
    read-timeout: 2s

logging:
  level:
    root: WARN
~~~

Do not put credentials into these files. They are suitable for non-sensitive configuration that can be reviewed in Git.

### 4.2. Activating Profiles from the Deployment Environment

The production profile should be selected from deployment configuration, for example:

~~~bash
SPRING_PROFILES_ACTIVE=prod
~~~

In Kubernetes, you can declare environment variables in the Deployment or Helm values. For other containers, use the corresponding platform mechanism.

Avoid hard-coding `spring.profiles.active=prod` in the artifact. If the profile is baked into the binary, the same artifact is difficult to promote across environments.

### 4.3. Multiple Profiles and Ordering

Spring Boot allows activating multiple profiles:

~~~bash
SPRING_PROFILES_ACTIVE=prod,observability
~~~

If multiple profiles declare the same key, the profile processed later can override earlier profiles. Therefore, the order of the profile list matters.

You can use profile groups to bundle profiles by purpose. For example:

~~~yaml
spring:
  profiles:
    group:
      production:
        - prod
        - metrics
        - tracing
~~~

When `production` is activated, the related group of profiles can be enabled together. Do not use profile groups to authorize secret access; that access must be managed by the secret manager or platform.

### 4.4. Do Not Activate Profiles from Profile-Specific Documents

Properties that control profile selection, such as `spring.profiles.active`, must not be placed arbitrarily inside a document that is itself activated by a profile. Set active profiles at the deployment layer or in a non-profile-specific configuration source.

If you need profile groups or profile includes, use the profile group/include mechanisms supported for your specific Spring Boot version.

### 4.5. Packaged Files and External Files

Spring Boot can read Config Data from the classpath and from the filesystem. In common order:

1. `application.yml` packaged inside the JAR.
2. `application-{profile}.yml` packaged inside the JAR.
3. `application.yml` outside the JAR.
4. `application-{profile}.yml` outside the JAR.

Sources processed later can override earlier sources. Consequently, external files can adjust configuration without rebuilding the JAR.

## 5. Externalizing Non-Sensitive Configuration Outside the Artifact

### 5.1. Using spring.config.additional-location

If you want to keep the default Config Data inside the JAR and add an external configuration directory, use `spring.config.additional-location`.

Example:

~~~bash
java -jar orders-service.jar --spring.config.additional-location=optional:file:/etc/orders/
~~~

The directory can contain:

~~~text
/etc/orders/
  application.yml
  application-prod.yml
~~~

When the `prod` profile is active, Spring Boot can load the profile-specific file from that location.

Use `additional-location` when you want to **add** locations. `spring.config.location` replaces the default search locations and can easily cause packaged configuration to be missed if not declared completely.

### 5.2. Using spring.config.import

You can import separate files from `application.yml`:

~~~yaml
spring:
  config:
    import: optional:file:/etc/orders/overrides.yml
~~~

Imported sources are processed as Config Data. Values from the imported file can override values in the file declaring the import according to Config Data rules.

The `optional:` prefix allows the application to continue if the location does not exist. Only use `optional` for configuration that is truly optional. If the application requires a configuration file to operate safely, omit `optional:` so startup fails when it is missing.

### 5.3. Paths Must Suit the Runtime

Paths on a developer's machine can differ from production containers or VMs. Declare locations using stable runtime mount paths rather than relying on a developer's home directory.

For containers, mount configuration into a standardized directory, such as `/etc/orders/config`. Ensure the user running the application has read permission and does not have write permission if unnecessary.

### 5.4. Do Not Embed Secret Files in Images

Dockerfiles should not `COPY` files containing credentials into image layers. Deleting the file in a later layer does not guarantee the secret disappears from earlier layers.

Non-sensitive configuration can be mounted or supplied via Config Data. Secrets should be mounted or injected at runtime from a secret manager or platform secret facility.

## 6. Environment Variables and Relaxed Binding

### 6.1. Using Environment Variables for Simple Configuration

Spring Boot can read OS environment variables. For example:

~~~bash
SPRING_PROFILES_ACTIVE=staging
SERVER_PORT=8080
APP_INVENTORY_BASE_URL=https://inventory-stg.internal
APP_INVENTORY_READ_TIMEOUT=3s
~~~

Property names like `app.inventory.read-timeout` are typically represented using uppercase letters and underscores in environment variables.

Environment variables are convenient for simple deployment configuration and short values. However, for credentials, consider how the platform manages environment read permissions and the potential for exposure via process diagnostics, crash dumps, or debugging tools.

### 6.2. Avoid Passing Secrets via Command Line Whenever Possible

Example to avoid:

~~~bash
java -jar orders-service.jar --spring.datasource.password=secret-value
~~~

Command-line arguments can appear in process inspection or process management system logs. Using a secret file mount or secret manager is more appropriate.

### 6.3. Placeholders Connect Properties

Spring supports placeholders to compose values:

~~~yaml
app:
  partner:
    base-url: ${PARTNER_BASE_URL:https://partner.local}
    timeout: ${PARTNER_TIMEOUT:2s}
~~~

The example above uses fallbacks for non-sensitive configuration. For required passwords or tokens, avoid setting a fallback to a dummy or default credential. Let a missing secret cause validation to fail.

## 7. Configuration Trees and Secret File Mounts

### 7.1. Why Are Configuration Trees Useful?

Some platforms can mount a ConfigMap or Secret as a directory containing multiple files. Spring Boot provides the `configtree:` prefix to convert a file structure into a property source.

Example directory:

~~~text
/run/secrets/
  spring/
    datasource/
      username
      password
    rabbitmq/
      username
      password
~~~

Directory and file names form the property key:

| File | Property |
| --- | --- |
| /run/secrets/spring/datasource/username | spring.datasource.username |
| /run/secrets/spring/datasource/password | spring.datasource.password |
| /run/secrets/spring/rabbitmq/username | spring.rabbitmq.username |
| /run/secrets/spring/rabbitmq/password | spring.rabbitmq.password |

### 7.2. Importing a Configuration Tree

Declare in `application.yml`:

~~~yaml
spring:
  config:
    import: configtree:/run/secrets/
~~~

Because these secrets are required, the example omits `optional:`. If the directory does not exist, startup should fail rather than running with missing configuration.

If secrets only exist in a specific environment, you can declare the import in the appropriate file or document, while verifying that profiles and imports are processed properly in that runtime.

### 7.3. Optional Config Tree Imports

In local environments that do not need secret mounts, you can use:

~~~yaml
spring:
  config:
    import: optional:configtree:/run/secrets/
~~~

Only use this approach when the application has a safe alternative secret source locally or in tests. Do not switch production configuration to `optional` just to prevent the container from failing when a mount is missing.

### 7.4. Mounting Multiple Configuration Groups

You can separate secrets by source:

~~~text
/run/secrets/
  database/
    spring.datasource.username
    spring.datasource.password
  messaging/
    spring.rabbitmq.username
    spring.rabbitmq.password
~~~

Or use subdirectories following property name conventions. Spring Boot supports wildcard config trees for immediate subdirectories:

~~~yaml
spring:
  config:
    import: configtree:/run/secrets/*/
~~~

Wildcard directories are processed in name order. If two trees supply the same property, avoid collisions or explicitly specify import order.

### 7.5. Values Can Be String or byte[]

Configuration trees can bind file contents as `String` or `byte[]` depending on the target property type. This is useful for certificates, keys, or binary data, though you must clearly specify encoding and how libraries consume the data.

Do not read a private key as a `String` and then log it or include it in exception messages.

## 8. Kubernetes ConfigMap and Secret

### 8.1. Distinguishing the Two Resource Types

In Kubernetes:

- `ConfigMap` is for non-confidential configuration data.
- `Secret` is for passwords, tokens, keys, and sensitive data.

Examples:

| Data | Resource |
| --- | --- |
| Inventory service URL | ConfigMap |
| Log level | ConfigMap |
| Non-sensitive feature flag | ConfigMap |
| Database password | Secret |
| API token | Secret |
| TLS private key | Secret or integrated secret manager |

### 8.2. Base64 Is Not Encryption

Kubernetes Secrets represent some fields in Base64. Base64 is merely encoding and provides no confidentiality. Anyone who can read the manifest or decode the value can obtain the secret.

Do not commit Secret manifests containing real data into Git just because the `data` field is Base64-encoded.

### 8.3. Protecting Kubernetes Secrets

With Kubernetes, you should:

- Enable encryption at rest for Secret data in etcd.
- Use least-privilege RBAC to restrict who can `get`, `list`, or `watch` Secrets.
- Mount Secrets only into containers that need to use them.
- Restrict permissions on mounted files.
- Do not place secrets into images, public Helm chart values, or logs.
- Protect etcd backups and manifest backups.
- Verify the application does not log secrets after reading them.

A Pod with multiple containers should not share every Secret with all containers if only one container needs that credential.

### 8.4. ConfigMap Is Not a Place to Store Credentials

Do not put passwords into a ConfigMap and assume a namespace or private cluster provides enough protection. Separate non-sensitive data and secrets from the start of your design so access permissions can be scoped independently.

## 9. Spring Cloud Config for Centralized Configuration

### 9.1. Role of Config Server

Spring Cloud Config Server serves remote configuration to multiple Config Clients. The data source is commonly a Git repository, though the server supports other backends as well.

Config Server identifies a configuration set by three components:

- `application`: typically corresponds to `spring.application.name`.
- `profile`: active profiles of the client.
- `label`: configuration version, typically a branch, tag, or commit in a Git backend.

A client can request configuration by application, profile, and label. As a result, multiple services can share common configuration while adding service-specific settings.

### 9.2. Example Git Repository Structure

~~~text
config-repo/
  application.yml
  application-prod.yml
  orders-service.yml
  orders-service-prod.yml
  inventory-service.yml
  inventory-service-prod.yml
~~~

Meaning:

- `application.yml`: shared configuration for clients.
- `application-prod.yml`: shared configuration for the `prod` profile.
- `orders-service.yml`: configuration specific to Orders.
- `orders-service-prod.yml`: Orders configuration in production.
- `inventory-service.yml`: configuration specific to Inventory.
- `inventory-service-prod.yml`: Inventory configuration in production.

According to Environment Repository rules, application-specific and profile-specific configuration can have higher precedence than default configuration. Check the actual property source response when multiple files declare the same key.

### 9.3. Declaring Config Data Import

In the Config Client:

~~~yaml
spring:
  application:
    name: orders-service
  config:
    import: configserver:
  cloud:
    config:
      label: release-2026-11
~~~

The Config Server address can be configured via `spring.cloud.config.uri` or declared directly in the import location. For example:

~~~yaml
spring:
  config:
    import: configserver:https://config.internal
~~~

Config Data import has been supported since Spring Boot 2.4. This is the current default approach for Spring Cloud Config Client. Legacy bootstrap may still exist in older projects, but you should not mix the two models without understanding the property source ordering of each.

### 9.4. Optional vs. Required Config Server Connections

Two configuration styles have different meanings:

~~~properties
spring.config.import=optional:configserver:
~~~

~~~properties
spring.config.import=configserver:
~~~

With `optional:`, the application can continue starting up if Config Server is unreachable. Without `optional:`, the client fails startup if it cannot fetch configuration from the server.

For required production configuration such as critical endpoints, policies, or security-impacting properties, you should not allow the application to silently run with default values when Config Server is disconnected.

If the application can operate safely using local defaults when Config Server is temporarily unavailable, `optional` may be appropriate, provided the conditions are documented and alerts are monitored.

### 9.5. Config Client May Call the Server Multiple Times at Startup

With Config Data, the client may fetch configuration for the `default` profile first to discover profiles activated by remote configuration, then call again with the active profiles. Multiple requests during startup are normal behavior in this mechanism.

Do not immediately assume multiple requests indicate an error. Inspect the application name, profile, and label sent by the client.

### 9.6. Using Labels to Version Configuration

A label can be a branch, tag, or commit ID depending on the backend. For repeatable deployments, choose a stable revision for each deployment instead of having production continuously read a mutable branch without recording the revision.

A pipeline can:

1. Create a configuration commit.
2. Review and validate the change.
3. Tag the commit or record the commit ID.
4. Deploy staging with that label.
5. Verify the results.
6. Promote the same label to production.
7. If rollback is needed, revert to a previously tested label.

### 9.7. Config Server Should Not Store Plaintext Secrets in Git

Config Server enables centralized configuration management, but a Git repository does not automatically become a secret manager. If plaintext passwords are stored in Git, anyone with read access to the repository can obtain the credentials.

You can use the following approaches:

- Store non-sensitive configuration in the Git Config Repository.
- Store secrets in Vault or a secret manager.
- Use the Config Server Vault backend if architecture requires it.
- Use encrypted properties when appropriate, with separately managed keys.

## 10. Separating Secrets with Spring Cloud Vault

### 10.1. Vault as a Dedicated Secret Source

Spring Cloud Vault integrates HashiCorp Vault to expose secret backends as a `PropertySource` in the Spring `Environment`. Applications can fetch secrets by application name and active profile.

This approach ensures:

- Secrets do not need to be stored as plaintext in Git.
- Secret read permissions are tied to workload identity.
- Secrets are separated by service and environment.
- Versioned KV backends are supported.
- Auditing and secret lifecycle management follow centralized Vault policies.

### 10.2. Using the Config Data API

Spring Cloud Vault supports the Config Data API. Basic configuration:

~~~yaml
spring:
  config:
    import: vault://
  cloud:
    vault:
      uri: https://vault.internal
~~~

The application needs the Spring Cloud Vault Config dependency matching its release train. Connecting to Vault requires TLS and an authentication mechanism. Do not put a root token or long-lived shared token in `application.yml`.

### 10.3. Context Paths by Application and Profile

With the default KV backend, Spring Cloud Vault can fetch data from context paths such as:

~~~text
/secret/application
/secret/application/prod
/secret/orders-service
/secret/orders-service/prod
~~~

Backend name, default context, application name, profile separator, and KV version can all be configured. The actual structure depends on your organization's Vault setup.

For example, Vault might contain:

~~~text
secret/
  application/
    common-property: value
  orders-service/
    datasource-username: orders_app
  orders-service/
    prod/
      datasource-password: ...
~~~

This example illustrates the logical structure; with KV v2, the API path includes a `data` segment handled by Vault. Do not manually construct KV v1/v2 HTTP paths when using Spring Cloud Vault.

### 10.4. Importing Specific Contexts

If you do not want to use the default contexts, you can import specific paths:

~~~yaml
spring:
  config:
    import: vault:///apps/orders-service/prod
~~~

You can combine multiple Vault locations and other Config Data sources. Import order matters; if multiple sources supply the same property, verify which source wins in the `Environment`.

### 10.5. Workload Authentication

Vault must authenticate clients before issuing secrets. Depending on the platform, you can use Kubernetes auth, AppRole, cloud IAM, or other supported mechanisms.

Principles:

- Each workload has its own identity.
- Policies only allow reading necessary paths.
- Never use a root token in applications.
- Minimize long-lived tokens.
- Protect TLS certificates and auth material.
- Audit secret reads.
- Revoke identity when a workload or service is no longer authorized.

### 10.6. Do Not Confuse Config Server Vault Backend with Config Client Vault

There are two distinct integration models:

1. Config Server uses Vault as a backend to retrieve configuration and serve it to Config Clients.
2. Config Client uses Spring Cloud Vault directly to import secrets into the `Environment`.

These two architectures have different permission boundaries and data flows. Choose the one that fits your governance model; do not configure both for the same property without controlling precedence.

## 11. Property Encryption in Spring Cloud Config

### 11.1. Encrypted Properties

Spring Cloud Config supports values prefixed with `{cipher}`. Config Server can decrypt them before returning property sources to clients. This keeps ciphertext in Git instead of plaintext.

Example in YAML:

~~~yaml
spring:
  datasource:
    password: '{cipher}ENCRYPTED_VALUE'
~~~

### 11.2. Encryption at Rest Does Not Replace a Secret Manager

In the server-side decryption model:

1. Git stores ciphertext.
2. Config Server reads ciphertext.
3. Config Server uses a key to decrypt it.
4. The client receives plaintext over the Config Server connection.

Therefore, Config Server and the key material become components with access to plaintext. You must protect the server, keys, endpoints, TLS, and authorization.

Property encryption suits certain Git-based configuration workflows, but it does not natively provide full capabilities such as workload identity, leases, secret access auditing, or secret manager rotation policies.

### 11.3. When to Choose Vault Over Encrypted Properties?

| Criterion | Encrypted Property in Config Server | Vault / Secret Manager |
| --- | --- | --- |
| Non-sensitive configuration | Can be stored in Git | Can be stored, though not strictly necessary |
| Secret at rest | Stores ciphertext | Secrets are managed in a dedicated backend |
| Workload-level authorization | Depends on Config Server authorization and key design | Policies can be bound to workload identity |
| Rotation | Requires generating new ciphertext and deploying keys/config | Versions/rotation can be managed by the backend |
| Dynamic credentials | Not a primary goal | Some backends support dynamic credentials |
| Secret read auditing | Depends on the Config Server system | Vault provides configurable auditing |

There is no single choice for every organization. You can use Config Server for general configuration and Vault for secrets; what matters is avoiding two competing sources of secrets without clear rules.

## 12. Designing Typed Configuration Classes

### 12.1. Do Not Scatter Property Keys Throughout Code

Instead of reading properties arbitrarily across many classes:

~~~java
String url = environment.getProperty("partner.api.base-url");
String token = environment.getProperty("partner.api.token");
~~~

group related configuration into a typed object with a prefix and validation.

~~~java
@ConfigurationProperties(prefix = "partner.api")
@Validated
public record PartnerApiProperties(
        @NotBlank String baseUrl,
        @NotBlank String token,
        @NotNull Duration connectTimeout,
        @NotNull Duration readTimeout
) {
}
~~~

Register it with `@ConfigurationPropertiesScan` or `@EnableConfigurationProperties`.

### 12.2. Validation Fails Startup When Secrets Are Missing

If `token` is required, `@NotBlank` prevents the application from starting with an empty value. Do not set a default token inside the record.

Example non-sensitive configuration:

~~~yaml
partner:
  api:
    base-url: https://partner.internal
    connect-timeout: 500ms
    read-timeout: 2s
~~~

The token is supplied from a secret source under the key `partner.api.token`. When the source lacks that property, validation fails instead of silently using a dummy value.

### 12.3. Split Properties Classes by Responsibility

You can split them into:

- `DatabaseConnectionProperties`.
- `MessagingConnectionProperties`.
- `PartnerApiProperties`.
- `FeatureProperties`.
- `ObservabilityProperties`.

Do not create a monolithic class holding every property in the system. Grouping by owning component and lifecycle makes configuration sources, secret permissions, and refresh behavior clearer.

### 12.4. Do Not Expose Secrets via toString

Records generate a default `toString` that prints every field. If a class contains a password or token, avoid logging the object directly. You can use a regular class instead of a record or override `toString` to mask sensitive fields.

Never return secrets in Actuator, error responses, metric tags, or exception messages.

## 13. Precedence Order and Avoiding Shadowing

### 13.1. Multiple Sources Can Declare the Same Key

A property may appear in:

- `application.yml` in the JAR.
- `application-prod.yml`.
- External files.
- Environment variables.
- JVM system properties.
- Command line arguments.
- Config Server.
- Vault.
- Configuration trees.
- Test property sources.

The final value depends on Config Data import order and the `PropertySource` entries created in the `Environment`. Do not assume Vault or Config Server always wins simply because it is a remote source.

### 13.2. Import Order Matters

Spring Boot processes Config Data imports as additional sources inserted at the declaration point. Multiple imports are processed in declaration order; later imports can override earlier ones.

Example:

~~~yaml
spring:
  config:
    import: configserver:,vault://
~~~

If both Config Server and Vault provide `partner.api.token`, determine which source takes precedence in your version and declaration style. Best practice is that only one source owns a specific secret key.

### 13.3. Do Not Create Fallbacks for Production Secrets

Dangerous example:

~~~yaml
spring:
  datasource:
    password: ${DB_PASSWORD:local-password}
~~~

If `DB_PASSWORD` is missing in production, the application still runs with `local-password`. This hides deployment errors and can cause the application to use the wrong credential.

For required secrets, use placeholders without fallbacks or enforce mandatory validation. You may have a separate local profile, but it must be selected explicitly and never activated automatically in production.

### 13.4. Inspecting the Winning Source

When a value is unexpected:

1. Read `Environment.getProperty(key)` in a protected environment.
2. List the `PropertySource` names containing the key.
3. Confirm active profiles.
4. Check Config Server application/profile/label.
5. Check the Vault context path.
6. Check config tree mounts.
7. Check environment variables and system properties.
8. Inspect the `ConfigurationProperties` bean after binding.

Never dump the entire `Environment` or property sources to logs, as this can leak secrets.

## 14. Managing Environment Configuration in Git

### 14.1. Separating the Configuration Repository from Source Code

A common layout:

~~~text
orders-config/
  application.yml
  application-staging.yml
  application-prod.yml
  orders-service.yml
  orders-service-staging.yml
  orders-service-prod.yml
  inventory-service.yml
  inventory-service-prod.yml
~~~

This repository stores non-sensitive configuration and is reviewed like code. Merge permissions for production branches/tags should be stricter than for development configuration.

### 14.2. Separating by Application and Profile

Use `application.yml` for shared values. Use `orders-service.yml` for configuration specific to Orders. Use `orders-service-prod.yml` for production differences of Orders.

Do not duplicate the entire shared file into every service if only a few keys differ. Duplication increases the risk of configuration drift across applications.

### 14.3. Version Control and Rollback

Every configuration change should record:

- Author and reviewer.
- Purpose of change.
- Affected environment.
- Commit/tag or label.
- Verification method.
- Rollback plan.

For production, prefer immutable labels such as a commit ID or an approved release tag. A continuously changing branch can cause the same deployment to restart with different configuration at a later time.

### 14.4. Do Not Commit Local Secret Files

Files such as `.env`, `application-local-secret.yml`, `credentials.json`, or personal keystores must be excluded from Git using an appropriate `.gitignore`. However, `.gitignore` does not remove data committed previously. If a secret was ever committed, rotate the credential and clean repository history according to policy.

Do not use git-ignored local files as a production secret mechanism. Production requires a platform-managed and audited secret source.

## 15. Configuration Promotion Pipeline

A controlled deployment workflow:

1. Build the artifact once.
2. Scan dependencies and images against policy.
3. Record the artifact digest.
4. Review non-sensitive configuration in the repository.
5. Grant secrets to the workload using identity or secret mounts.
6. Deploy the same artifact digest to development.
7. Test startup, health, and dependency connectivity.
8. Promote the same digest and config revision to staging.
9. Run integration/smoke tests.
10. Approve production release.
11. Deploy the same digest with production profile, Config Server label, and secret scope.
12. Verify readiness and loaded revision.
13. Record deployment state for rollback.

~~~mermaid
flowchart TD
    A[Build artifact once] --> B[Record digest]
    B --> C[Review config revision]
    C --> D[Deploy dev]
    D --> E[Smoke and integration tests]
    E --> F[Deploy staging same digest]
    F --> G[Validate and approve]
    G --> H[Deploy production same digest]
    H --> I[Verify config revision and secret access]
    I --> J[Monitor health and rollback readiness]
~~~

### 15.1. Scoping Secrets by Workload

Each service should only receive the secrets it needs. Orders does not need to read all Inventory secrets. Development does not need permission to read production secrets.

With Vault, create separate policies by application/path. With Kubernetes, restrict Secrets mounted into Pods and ServiceAccount RBAC. With cloud secret managers, use workload identity and resource-level policies.

### 15.2. Do Not Put Secrets in Pipeline Logs

Pipelines should only record secret references, versions, or non-sensitive credential names. Do not echo secrets, print the entire environment, or enable HTTP request debug logging that contains tokens.

If a pipeline must create secrets, use the CI/CD secret store with masking and least privilege. Masking does not replace avoiding printing secrets in the first place.

## 16. Rotation, Refresh, and Restart

### 16.1. Changing a Secret at the Source Does Not Guarantee Beans Update

An application may read a password at startup and bind it into a singleton bean or connection pool. When the secret source changes, already-created objects may still retain old values.

You must determine:

- Does the secret source have a notification or refresh mechanism?
- Does Config Client re-fetch property sources?
- Is the bean inside `RefreshScope`?
- Does the connection pool support safely swapping credentials?
- Is an instance restart needed to recreate resources?

Do not assume that because a mounted secret file changed, the `Environment` and every bean update automatically.

### 16.2. Refresh or Restart?

| Change | Commonly Considered Handling |
| --- | --- |
| Dynamically read feature flag | Can be updated via config refresh or feature service |
| Timeout of a refreshable client | Target can be refreshed if design supports it |
| Database credential | Requires pool replacement/drain or controlled restart |
| JVM flags or heap | Restart process |
| Classpath or dependencies | Build and deploy a new artifact |
| TLS private key | Depends on client/server reload support; may require restart |

Spring Cloud Context provides refresh for suitable beans. It does not automatically turn every singleton into an object that reads configuration dynamically.

### 16.3. Rotation with an Overlap Period

When changing credentials, the target system may support two credentials simultaneously for a period. A safe process typically looks like:

1. Create the new credential.
2. Provide the new credential to the secret manager.
3. Update the application or clients.
4. Verify all instances use the new credential.
5. Revoke the old credential.
6. Check connection pools and authentication errors after rotation.

Do not revoke the old credential before all instances still using it have switched over, unless handling a compromise incident that requires emergency revocation.

### 16.4. Rollback Must Include Configuration and Secrets

Rolling back only code without rolling back compatible configuration can prevent the application from starting. Conversely, restoring an old secret that has already been revoked is not a viable solution either.

Each deployment should record:

- Artifact digest.
- Config label/revision.
- Secret version or secret reference.
- Profile.
- Deployment timestamp.
- Health status.

When rolling back, restore a tested, compatible bundle rather than just a single `application.yml` file.

## 17. Securing Configuration Data

### 17.1. Least-Privilege Authorization

Users or workloads should only read properties and secrets required for their duties. Do not grant read access to the entire config repository or secret namespace unnecessarily.

### 17.2. Protecting Data in Transit

Config Client, Config Server, Vault, and secret managers must communicate over TLS when traversing a network. Verify certificates and hostnames; do not disable SSL validation to bypass certificate errors in production.

### 17.3. Protecting Data After Reading

Secrets can appear in:

- `Environment`.
- `ConfigurationProperties` objects.
- Connection pools.
- HTTP clients.
- Heap dumps.
- Debuggers.
- Logs or exceptions.
- Actuator endpoints.

After the application reads a secret, you still need to protect the process, host/container, log pipeline, and debug permissions. A secret manager cannot prevent secret leakage if the application logs plaintext itself.

### 17.4. Actuator and Configuration Endpoints

Do not expose `env`, `configprops`, or administrative endpoints broadly. If configuration inspection is needed, use secured endpoints, mask sensitive values, and grant access only to operations roles.

### 17.5. Backups and History

Backups of the Config Server repository, Vault, and secret stores may all contain sensitive information or decryptable ciphertext. Protect backups, audit read access, and enforce retention policies.

## 18. Testing Environment-Based Configuration

### 18.1. Testing Profiles

Use `@ActiveProfiles` to confirm profile-specific files load in tests:

~~~java
@SpringBootTest
@ActiveProfiles("test")
class OrdersConfigurationTest {

    @Autowired
    Environment environment;

    @Test
    void usesTestProfile() {
        assertThat(environment.getActiveProfiles())
                .contains("test");

        assertThat(environment.getProperty("app.inventory.base-url"))
                .isEqualTo("http://localhost:18081");
    }
}
~~~

Do not use the production profile in tests merely to check files. You can create test fixtures with non-sensitive values.

### 18.2. Testing Required Configuration

Use `ApplicationContextRunner` or `@SpringBootTest` to verify that the context fails when required secrets are missing. This is an important test because it prevents silent fallback bugs.

Example:

~~~java
@Test
void missingPartnerTokenPreventsStartup() {
    new ApplicationContextRunner()
            .withUserConfiguration(PartnerConfiguration.class)
            .withPropertyValues(
                    "partner.api.base-url=https://partner.test",
                    "partner.api.connect-timeout=500ms",
                    "partner.api.read-timeout=2s"
            )
            .run(context -> {
                assertThat(context).hasFailed();
            });
}
~~~

This example assumes `PartnerConfiguration` registers `PartnerApiProperties` with validation enabled. It omits `partner.api.token` to test that the application refuses to start.

### 18.3. Testing Secret Sources

For config trees, you can create a test directory containing username/password files and start the context using `configtree:` import. For Vault, use a Vault test environment or appropriate mocks; never call production Vault from automated tests.

### 18.4. Testing Config Server with Fixed Labels

Integration tests should:

1. Use a test Config Server or repository fixture.
2. Specify a clear application name.
3. Select a test profile.
4. Select a fixed label/commit.
5. Start the Config Client.
6. Check property sources and resolved values.
7. Verify that missing remote config leads to failure or policy-compliant fallback.
8. Never use production secrets in tests.

### 18.5. Verifying Secrets Are Not Logged

You can check captured logs in tests during startup and validation failures. Ensure messages do not contain the supplied token or password. Do not check only response objects; an exception or `toString` call can expose values.

## 19. Troubleshooting Common Issues

| Symptom | Possible Cause | Remediation |
| --- | --- | --- |
| Application uses local config in production by mistake | Profile not active or external source not loaded | Check `SPRING_PROFILES_ACTIVE` and `PropertySource` |
| External file does not override JAR file | Wrong `spring.config.location` usage or path not found | Check `additional-location`, path, and Config Data logs |
| Config Server is not called | Missing `configserver` import or dependency | Check Config Client starter and `spring.config.import` |
| Startup succeeds when Config Server fails | Import has `optional:` | Decide explicitly whether running with local config is allowed |
| Client reads wrong configuration set | Wrong application name, profile, or label | Check request path and config revision |
| Secret is empty | Wrong secret mount/Vault path or read permission denied | Check mount, Vault policy, and masked startup logs |
| Default secret is used | Placeholder has fallback or bean has default | Remove fallback and add mandatory validation |
| Vault 403 | Workload identity or policy denies path read | Check auth method, role, and policy |
| Vault 404 | Context path or profile path does not exist | Check application name, profile, backend, and KV version |
| Kubernetes Secret not updated | Volume update semantics or app has not reloaded | Verify file mount and trigger appropriate refresh/restart |
| Secret appears in logs | Logging config object or exception contains plaintext | Mask data, fix logging, and review log retention |
| Some replicas use different config | Inconsistent config label/secret version | Record revision per instance and roll out by group |
| Rollback fails | Incompatible artifact, config revision, and secret version | Restore a tested compatible version bundle |
| Works locally but fails in container | Different file path, permissions, or environment | Check mounts and runtime user |
| Base64 Secret treated as encrypted | Confusing encoding with encryption | Use Secret store properly, encryption at rest, and RBAC |

## 20. Recommended Operations Workflow

For an Orders service using Config Server for configuration and Vault for secrets:

1. Package `application.yml` with only the application name, safe defaults, and Config Data imports.
2. Build one container image and record its digest.
3. Configure the active profile from the deployment environment.
4. Config Server returns Orders configuration by application/profile/label.
5. Vault supplies datasource credentials and partner tokens based on workload identity.
6. The application binds configuration via `ConfigurationProperties` and validates it.
7. Readiness passes only when required configuration and essential dependencies are ready.
8. The pipeline deploys the same image digest to staging and then production.
9. Each deployment records the config revision and secret version.
10. Rotation updates the secret source, then refreshes/restarts necessary components.
11. Rollback restores a compatible artifact/configuration set and verifies credentials remain valid.
12. Audit secret reads, configuration changes, and administrative actions.

~~~mermaid
flowchart TD
    A[Immutable application image] --> B[Spring Boot Config Data]
    C[Deployment profile] --> B
    D[Spring Cloud Config] --> B
    E[Vault or secret manager] --> B
    F[Mounted config tree] --> B
    B --> G[Environment and PropertySources]
    G --> H[ConfigurationProperties binding]
    H --> I[Validation]
    I --> J[Application starts]
    J --> K[Readiness and dependency checks]
~~~

## 21. Pre-Production Configuration Checklist

### Artifact and Profile

- [ ] The same artifact digest is used across environments.
- [ ] The profile is selected from the deployment layer.
- [ ] `application.yml` contains only safe defaults.
- [ ] Profile-specific files contain no plaintext secrets.
- [ ] No production endpoints or credentials are hard-coded in source code.

### Config Data and Config Server

- [ ] Config Data locations are clearly defined.
- [ ] `additional-location` is used when adding external files.
- [ ] Whether Config Server import uses `optional` is decided based on availability requirements.
- [ ] Application name, profile, and label are correct.
- [ ] Config revision is recorded.
- [ ] Continuously changing branches are not used when reproducible deployments are required.

### Secrets

- [ ] Passwords/tokens/private keys are not in Git or images.
- [ ] Secrets are supplied from Vault, a secret manager, or platform Secrets.
- [ ] Workloads only have read access to required secrets.
- [ ] Required secrets have no default fallback.
- [ ] Kubernetes Secrets are protected with RBAC and encryption at rest.
- [ ] Secrets do not appear in logs, metrics, or Actuator.
- [ ] A credential rotation and revocation process is in place.

### Runtime and Rollback

- [ ] `ConfigurationProperties` are validated.
- [ ] Startup fails when required configuration is missing or invalid.
- [ ] Readiness reflects actual serving capability.
- [ ] Rotation includes a resource refresh/restart plan.
- [ ] Artifact, config revision, and secret version are recorded.
- [ ] Rollback has been tested.

## 22. Practice Exercises

**Exercise 1 — One artifact, multiple environments.** Create `application.yml` and `application-staging.yml`. Build one JAR, run it twice with two different profiles, and prove the artifact is unchanged while the configured endpoint changes.

**Exercise 2 — External configuration file.** Mount `/etc/orders` into a container. Use `spring.config.additional-location` to load `application-prod.yml`. Verify external values outside the JAR override defaults.

**Exercise 3 — Configuration tree.** Create `/run/secrets/spring/datasource` containing `username` and `password`. Import via `configtree:` and confirm `DataSource` receives the correct properties.

**Exercise 4 — Required secret.** Create `PartnerApiProperties` with `@NotBlank` on `token`. Run the context with and without the token; verify the missing case fails startup.

**Exercise 5 — Config Server.** Create a repository with `application.yml`, `orders-service.yml`, and `orders-service-prod.yml`. Select application/profile/label and inspect the property sources and final values.

**Exercise 6 — Optional and fail-fast.** Shut down Config Server in a test. Compare `configserver:` with `optional:configserver:` and define the appropriate policy for production.

**Exercise 7 — Vault.** Using a test Vault environment, create secrets by application and profile. Import `vault://` and verify the client reads secrets using workload authentication.

**Exercise 8 — Kubernetes Secret.** Create a ConfigMap for a URL and a Secret for a password. Mount each resource into the right container. Verify RBAC, encryption at rest, and file permissions.

**Exercise 9 — Property precedence.** Intentionally declare the same key in `application.yml`, Config Server, and Vault. Check which `PropertySource` wins, then remove the duplication so only one source owns the key.

**Exercise 10 — Rotation.** Change a database password in the secret store. Determine whether the pool can reload or needs a restart. Execute rotation with an overlap period and revoke the old credential.

**Exercise 11 — Rollback.** Deploy artifact digest A with config label X and secret version 1. Next, deploy digest B with label Y and secret version 2. Simulate a failure and restore a tested compatible version bundle.

**Exercise 12 — Leak check.** Run the application with test secrets, collect logs and Actuator output. Confirm there are no plaintext secrets in logs, responses, or metric tags.

## 23. Key Takeaways and Reference Resources

- Use one immutable artifact across environments; supply profiles, configuration, and secrets at deployment time.
- Distinguish non-sensitive configuration from credentials, tokens, and private keys.
- Profiles help select Config Data and beans; profiles are not a security boundary.
- `application.yml` should contain safe defaults; profile-specific files should not contain plaintext secrets.
- `spring.config.additional-location` adds external locations; `spring.config.location` replaces default locations.
- Configuration trees turn mounted files into property sources using `configtree:`.
- Kubernetes ConfigMaps are for non-confidential data; Secrets are for sensitive data, though Base64 is not encryption.
- Spring Cloud Config serves configuration by application, profile, and label; use stable labels for reproducible deployments.
- Spring Cloud Vault can import secret backends into the `Environment` via the Config Data API using `vault://`.
- Config Server encrypted properties protect ciphertext at rest, but server-side decryption still delivers plaintext to clients.
- Required secrets need validation and should not have default fallbacks.
- Rotation must coordinate the secret source, beans/resources, refresh or restart, and old credential revocation.
- Rollback must consider artifact digest, config revision, and secret version together.
- Do not log secrets or expose `Environment`/configuration over public management endpoints.

Official references matching your project's Spring Boot/Spring Cloud versions:

1. [Spring Boot Reference – Externalized Configuration](https://docs.spring.io/spring-boot/reference/features/external-config.html)
2. [Spring Cloud Config – Config Client](https://docs.spring.io/spring-cloud-config/reference/client.html)
3. [Spring Cloud Config – Environment Repository](https://docs.spring.io/spring-cloud-config/reference/server/environment-repository.html)
4. [Spring Cloud Config – Property Overrides](https://docs.spring.io/spring-cloud-config/reference/server/environment-repository/property-overrides.html)
5. [Spring Cloud Config – Encryption and Decryption](https://docs.spring.io/spring-cloud-config/reference/server/encryption-and-decryption.html)
6. [Spring Cloud Vault – Config Data API](https://docs.spring.io/spring-cloud-vault/reference/config-data.html)
7. [Spring Cloud Vault – Secret Backends](https://docs.spring.io/spring-cloud-vault/reference/secret-backends.html)
8. [Spring Cloud Vault – Authentication](https://docs.spring.io/spring-cloud-vault/reference/authentication.html)
9. [Kubernetes – Good Practices for Secrets](https://kubernetes.io/docs/concepts/security/secrets-good-practices/)
10. [Kubernetes – Encrypting Confidential Data at Rest](https://kubernetes.io/docs/tasks/administer-cluster/encrypt-data/)
11. [Spring Cloud – Release train and Spring Boot compatibility](https://spring.io/projects/spring-cloud/)
