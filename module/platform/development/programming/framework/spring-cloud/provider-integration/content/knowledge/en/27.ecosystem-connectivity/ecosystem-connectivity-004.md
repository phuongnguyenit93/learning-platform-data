# Boundary Between Provider Configuration and Spring Cloud Config

## 1. Context and Objectives

In the **Spring Cloud Provider Integration** module, Spring Boot applications connect to managed services from AWS, Azure, and Google Cloud via the corresponding Spring Cloud libraries, SDKs, and connectors. For those connections to work safely across local, test, staging, and production, an application needs several categories of configuration: Region, endpoints, queues/topics, buckets/containers, database URLs, timeouts, retry policies, feature flags, client IDs, and secrets.

These values are often placed together inside a single YAML file. That practice blurs the boundary between **application configuration**, **provider connection configuration**, and **secrets**. A non-sensitive endpoint can be managed as ordinary config; passwords, private keys, and tokens require a secret store, dedicated access controls, auditing, and rotation. Some settings must change dynamically without restarting; others are read only at startup and require a rollout to take effect.

**Spring Boot ConfigData** provides a mechanism to load configuration from multiple sources by precedence and profile. **Spring Cloud Config** adds a server/client model to centralize application configuration, commonly backed by Git or another repository. Cloud-native services such as AWS Systems Manager Parameter Store, AWS AppConfig, AWS Secrets Manager, Azure App Configuration, Azure Key Vault, and Google Secret Manager provide storage, distribution, or management for configuration/secrets in each provider's own way.

These mechanisms can work together, but they do not completely replace one another. Spring Cloud Config does not automatically act as an adapter for every cloud parameter store. A provider secret manager is not a complete application configuration repository. Source selection must be based on lifecycle, sensitivity, rate of change, identity, auditing, and how the application receives updates.

After this lesson, you will be able to:

1. Distinguish between application config, provider connection config, feature flags, and secrets.
2. Understand Spring Boot ConfigData, profiles, imports, and property precedence.
3. Design Spring Cloud Config Server/Client and appropriate backends.
4. Distinguish centralized Config Server from cloud-native configuration/secret services.
5. Choose AWS Parameter Store, AppConfig, Secrets Manager, Azure App Configuration/Key Vault, or Google Secret Manager for the right purpose.
6. Configure workload identity and read permissions following least privilege.
7. Design refresh, rotation, fail-fast, fallback, and config source outage handling.
8. Test environment-specific configuration without placing real secrets into tests.
9. Operate configuration with auditing, versioning, validation, monitoring, and rollback.

> **Scope:** This lesson focuses on architectural boundaries and Spring integration patterns. Exact starter names, ConfigData import prefixes, and properties depend on the Spring Boot, Spring Cloud, and provider integration versions. Use a compatible release train and verify version-specific documentation before implementation.

## 2. Classifying Configuration Before Choosing a Source

### 2.1. Four Distinct Data Categories

| Category | Examples | Characteristics | Typically Suitable Sources |
| --- | --- | --- | --- |
| Application config | Feature modes, business limits, page sizes, business timeouts | Not necessarily tied to cloud; may need profiles/refresh | Config Server, Git, environment, ConfigMap, App Configuration |
| Provider connection config | AWS Region, S3 bucket, queue URL, Azure endpoint, Pub/Sub topic | Tied to deployment/provider; often changes with infrastructure | Environment, deployment config, Parameter Store/App Configuration |
| Secret | Passwords, client secrets, API tokens, private keys, DB credentials | Sensitive, requires access control, audit, rotation | Secrets Manager, Key Vault, Secret Manager, Vault |
| Dynamic operational config | Feature flags, rollout percentages, kill switches, routing rules | May change rapidly while the app is running | AWS AppConfig, Azure App Configuration, feature flag services |

Not every value in provider connection config is a secret. For instance, Regions, bucket names, and endpoints are usually not credentials, though they can still expose topology and warrant appropriate read permissions. Conversely, connection strings may embed passwords; separate secrets from endpoint portions whenever possible.

### 2.2. A Classification Example

Suppose a service uploads documents to S3, sends notifications via a queue, and connects to a database:

~~~yaml
app:
  documents:
    bucket: rental-documents-prod
    max-upload-size: 20MB
  notifications:
    queue-name: reservation-notifications
  processing:
    retry-limit: 4

spring:
  datasource:
    url: jdbc:postgresql://db.internal:5432/rental
    username: rental_app
    password: value-from-secret-store

aws:
  region: ap-southeast-1
~~~

In this example:

- Bucket, queue, Region, and retry limit are deployment/application configs and do not need embedded access keys.
- Database URL and username are typically connection config; the password is a secret.
- If bucket/queue names vary by environment, manage them via environment variables or an appropriate config source.
- If retry limit is a business policy that changes across rollouts, it can go into dynamic config, with validation and safe bounds.

Do not put placeholder strings like `value-from-secret-store` into production. The example only illustrates boundaries; the integration must actually resolve secrets from an authorized source.

### 2.3. Configuration Must Have an Owner and Lifecycle

Every key should have an owner, authoritative source, and application timing:

| Attribute | Question to Answer |
| --- | --- |
| Owner | Which team is allowed to modify it? |
| Source of truth | Git, IaC, Config Server, or a provider store? |
| Scope | System-wide, environment, service, tenant, or instance? |
| Lifecycle | Read at startup, periodic refresh, or push event? |
| Validation | Where are types, ranges, and cross-key constraints checked? |
| Sensitivity | Is it a secret or restricted topology data? |
| Rollback | How is a previous version restored? |
| Audit | Who changed it, when, and why? |

Avoid managing the same key simultaneously in Git, environment variables, Config Server, and a provider store without explicit precedence. During an incident, the team must know which source supplied the effective value.

## 3. Spring Boot ConfigData and Property Resolution

### 3.1. Spring Boot Loads Configuration from Many Sources

Spring Boot can load configuration from:

- `application.properties` or `application.yaml` files.
- Profile-specific files such as `application-prod.yaml`.
- Environment variables.
- Java system properties.
- Command-line arguments.
- Config trees, mounted secret/config files.
- External sources integrated via ConfigData loaders such as Spring Cloud Config or provider integrations.

Sources are organized into Environment/PropertySources. A key may appear in multiple places; the winning value follows property source precedence and import order. Never guess the final value simply by reading one YAML file.

### 3.2. Profiles and Profile-Specific Config

Example:

~~~yaml
# application.yaml
app:
  storage:
    provider: s3
    connect-timeout: 2s
    read-timeout: 30s
~~~

~~~yaml
# application-local.yaml
app:
  storage:
    endpoint: http://localhost:4566
    bucket: local-documents
~~~

~~~yaml
# application-prod.yaml
app:
  storage:
    bucket: rental-documents-prod
~~~

Activate a profile via environment variable or command line:

~~~bash
SPRING_PROFILES_ACTIVE=prod
~~~

Profiles merely select suitable configuration; they are not a security boundary. Never put production secrets into profile files and commit them to Git. Also avoid creating a profile per tenant when tenants are numerous runtime entities; use tenant-aware configuration/services instead.

### 3.3. ConfigData Imports

Since Spring Boot 2.4, the ConfigData API has been the standard mechanism for importing external configuration sources. Modern Spring Cloud Config Client is typically enabled via:

~~~yaml
spring:
  application:
    name: reservation-service
  config:
    import: configserver:http://config-server.internal:8888
~~~

Use `optional:configserver:` when the application is permitted to start without a Config Server. Omit `optional:` when remote configuration is mandatory and starting without it would cause operational or security failures.

Example:

~~~yaml
spring:
  config:
    import: optional:configserver:
~~~

When importing without specifying a URL, the client can obtain the URI from `spring.cloud.config.uri` or the corresponding discovery mechanism. Exact configuration depends on client version and deployment.

Do not confuse ConfigData imports with the legacy bootstrap context. Older Spring Cloud projects may use `bootstrap.yml`/bootstrap starters; modern projects should follow the guidance for their release train. Avoid enabling both mechanisms simultaneously without understanding load order.

### 3.4. Property Precedence and Overrides

Spring Boot defines precedence across command line, system properties, environment, config data, and other sources. Profile documents and ConfigData imports also follow specific resolution rules. Spring Cloud Config additionally provides properties controlling whether remote property sources can be overridden by local properties.

Operational rules:

1. Pick one source of truth per key group.
2. Document which keys may be overridden via environment/command line.
3. Never allow default file secrets to be accidentally overwritten with empty values.
4. Do not assume `application-prod.yaml` always beats remote config; inspect the actual Environment in your version.
5. For diagnostics, use `/actuator/env` or `/actuator/configprops` in protected environments and never expose these endpoints publicly.

In particular, flags such as `spring.cloud.config.allowOverride`, `overrideNone`, or `overrideSystemProperties` have release-dependent client/server semantics. Configure them only after reading the exact version's docs and writing tests proving which source wins.

### 3.5. Binding Configuration into Safe Types

Prefer `@ConfigurationProperties` for structured config groups instead of scattering `@Value`:

~~~java
import java.time.Duration;
import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.validation.annotation.Validated;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.Positive;

@Validated
@ConfigurationProperties(prefix = "app.storage")
public record StorageProperties(
        @NotBlank String provider,
        @NotBlank String bucket,
        @Positive int maxUploadBytes,
        Duration readTimeout) {
}
~~~

Register via `@ConfigurationPropertiesScan` or `@EnableConfigurationProperties`. You can add range validation, provider allow-lists, and cross-field checks. For records/immutable objects, runtime configuration changes require considering how beans are recreated; do not assume every `@ConfigurationProperties` bean refreshes automatically.

## 4. Spring Cloud Config: Centralizing Application Configuration

### 4.1. What Problem Does Config Server Solve?

Spring Cloud Config Server exposes an HTTP API for clients to retrieve configuration by application name, profile, and label. For example, a client can request config for `reservation-service`, profile `prod`, label `main`.

Core concepts:

- **Application name:** service identifier, usually taken from `spring.application.name`.
- **Profile:** environment/variant such as `dev`, `staging`, `prod`.
- **Label:** branch, tag, or backend version; with Git, usually branch/tag/commit.
- **Repository/backend:** configuration source, such as a Git repository, native filesystem, or Vault.
- **Config Client:** fetches property sources and populates the Spring Environment.

Config Server can serve identical configuration across multiple instances and services. A Git backend enables pull-request reviews, version history, and commit rollbacks. A Vault backend can serve secrets with appropriate lease/policy mechanics. Native/filesystem backends are useful in certain environments but require permission and HA management.

### 4.2. Dependencies and Server Setup

The server needs the Config Server dependency and the enable annotation:

~~~xml
<dependency>
    <groupId>org.springframework.cloud</groupId>
    <artifactId>spring-cloud-config-server</artifactId>
</dependency>
~~~

~~~java
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.cloud.config.server.EnableConfigServer;

@SpringBootApplication
@EnableConfigServer
public class ConfigServerApplication {

    public static void main(String[] args) {
        SpringApplication.run(ConfigServerApplication.class, args);
    }
}
~~~

Manage versions with the Spring Cloud BOM compatible with Spring Boot. Do not pull the latest Config Server version independently of the application's release train.

### 4.3. Git-Backed Configuration

Example server configuring a Git repository:

~~~yaml
server:
  port: 8888

spring:
  cloud:
    config:
      server:
        git:
          uri: https://git.example.org/platform/application-config.git
          default-label: main
          clone-on-start: true
~~~

Inside the repository, files can follow convention:

~~~text
application.yaml
application-prod.yaml
reservation-service.yaml
reservation-service-prod.yaml
~~~

Config Server combines application name/profile/label to select property sources. Never place Git private keys or repository access tokens directly in committed files. Supply deploy keys/tokens via secret injection, TLS, and minimal read-only permissions.

### 4.4. Client Setup

Client dependency:

~~~xml
<dependency>
    <groupId>org.springframework.cloud</groupId>
    <artifactId>spring-cloud-starter-config</artifactId>
</dependency>
~~~

Client:

~~~yaml
spring:
  application:
    name: reservation-service
  config:
    import: configserver:http://config-server.internal:8888
  cloud:
    config:
      label: main
      profile: prod
~~~

Profiles are normally inferred from Spring Boot active profiles; `spring.cloud.config.profile` and `label` can control specific requests. Avoid declaring conflicting profiles in multiple places.

### 4.5. Config Server Is Not a Provider Parameter Store

Config Server is a property source distribution server. It can read from Git, Vault, or supported backends; it does not automatically read AWS Parameter Store, Azure App Configuration, or Google Secret Manager merely because the application runs on that cloud.

Config Server can be deployed on ECS/EKS, Azure Container Apps/AKS, or Cloud Run/GKE. Deployment location does not dictate the backend. For instance, a Config Server running on AWS can still read from Git; an application running on GCP can still use a centralized Config Server.

If using a provider store as the source, you need a specific integration or compatible backend/custom adapter. Do not treat a Config Server URL and a Secret Manager URI as the same kind of import.

### 4.6. When Does Config Server Add Value?

Choose Spring Cloud Config when:

- Many services need centrally managed configuration by app/profile/label.
- Git reviews, versioning, rollbacks, and change audits are desired.
- You want a uniform configuration distribution mechanism across multiple clouds.
- You can operate Config Server with HA, security, and access control.
- Configuration lifecycle must be decoupled from application releases.

You do not necessarily need to deploy Config Server for a small service with a handful of environment variables. Adding a server introduces a runtime dependency, networking, authentication, availability, and operational overhead.
## 5. AWS: Parameter Store, AppConfig, and Secrets Manager

### 5.1. Choosing a Service by Purpose

AWS offers several configuration-related services with different lifecycles:

| Service | Used For | Do Not Confuse With |
| --- | --- | --- |
| Systems Manager Parameter Store | Hierarchical parameters, String/SecureString, path/environment-based config | Dedicated feature flag rollout tool |
| AWS AppConfig | Dynamic configuration, feature flags, gradual deployment, validation, and rollback | General password/key store |
| AWS Secrets Manager | Passwords, API tokens, database credentials, secret rotation | Non-sensitive config store for all keys |
| Environment/Task definition | Deployment-bound values like Region, endpoints, resource names | Long-lived unrotated secret storage |

Parameter Store fits hierarchical configuration parameters, using SecureString when encryption is needed. AppConfig fits configuration requiring controlled rollouts and deployment monitoring. Secrets Manager fits secrets with lifecycles, versioning, and rotation.

### 5.2. Parameter Store with Spring Cloud AWS

AWSpring provides Parameter Store integration per release. For versions supporting ConfigData, the dependency is typically:

~~~xml
<dependency>
    <groupId>io.awspring.cloud</groupId>
    <artifactId>spring-cloud-aws-starter-parameter-store</artifactId>
</dependency>
~~~

Example importing a path:

~~~yaml
spring:
  config:
    import: aws-parameterstore:/config/reservation-service/
~~~

Parameters under the path are loaded into Environment according to the integration's rules. Prefixes, contexts, profile resolution, optional imports, and property mapping depend on the AWSpring version. Check docs for the version in use before choosing path conventions; do not assume every version resolves profiles identically.

The workload identity needs read permissions for the exact path, such as SSM GetParametersByPath/GetParameter and KMS decrypt if SecureString uses a customer-managed key. Do not grant read access to the entire Parameter Store if a service only needs one path.

### 5.3. Secrets Manager with Spring Cloud AWS

Secrets can be imported using the Secrets Manager integration:

~~~xml
<dependency>
    <groupId>io.awspring.cloud</groupId>
    <artifactId>spring-cloud-aws-starter-secrets-manager</artifactId>
</dependency>
~~~

Example ConfigData import:

~~~yaml
spring:
  config:
    import: aws-secretsmanager:/reservation-service/database
~~~

Secret names, import prefixes, and how JSON secrets flatten into properties depend on the AWSpring release. If a secret holds JSON containing username/password, verify property name mapping before binding. Never print secret objects to logs when debugging.

Runtime permissions should be scoped to the specific secret ARN, plus `kms:Decrypt` if required by a customer-managed KMS key. Secret rotation may update the version in Secrets Manager, yet the application does not necessarily pick up the new value immediately; an explicit refresh/reconnect mechanism is required.

### 5.4. AWS AppConfig for Dynamic Configuration

AppConfig suits feature flags and operational configs requiring rollouts:

- Can validate configuration before deployment.
- Can deploy via strategies/percentages and monitor alarms.
- Can roll back deployments when alarms trigger.
- Can use the AppConfig Agent as a local endpoint/cache for the application.
- Applications fetch configuration profiles via the AppConfigData API or the agent.

AppConfig should not be treated as an auto-refreshing Spring PropertySource if the specific integration does not provide that behavior. You can write an adapter reading from AppConfigData/agent and publishing changes to an application-level configuration service. Define polling intervals, cache TTLs, token/session lifecycles, and behavior when the agent/API is unavailable.

Do not put passwords/private keys into feature flag documents simply because AppConfig can store JSON. Secrets still belong in Secrets Manager or a secret store with proper permissions and rotation.

### 5.5. Configuring AWS Identity

In production, prefer workload-bound roles:

- ECS task role for tasks.
- EKS Pod Identity or IRSA for Kubernetes workloads.
- EC2 instance profile for applications on EC2.
- Local developer profiles only on development machines.

The AWS SDK credential provider chain retrieves credentials from the runtime environment and refreshes them per provider mechanics. Never declare access keys/secret keys in `application.yaml`. Regions can be passed via deployment config; a Region is not a credential.

### 5.6. A Combined AWS Pattern

~~~yaml
spring:
  application:
    name: reservation-service
  config:
    import:
      - aws-parameterstore:/config/reservation-service/
      - aws-secretsmanager:/reservation-service/database
~~~

Use the example above only when your project's AWSpring version supports both ConfigData loaders and corresponding import syntax. Separate non-sensitive parameter paths from secrets; do not reuse a single role with account-wide secret access unnecessarily.

## 6. Azure: App Configuration and Key Vault

### 6.1. Service Division of Roles

| Service | Used For | Characteristics |
| --- | --- | --- |
| Azure App Configuration | Application settings, labels, feature flags, and dynamic refresh | Centralized config management, key/label filters, and refresh |
| Azure Key Vault | Secrets, keys, and certificates | Access policies/RBAC, versioning, auditing, and rotation |
| Environment/Container App settings | Deployment-specific settings | Tied to runtime environment, suited for endpoints/resource references |

App Configuration supports Key Vault references so a setting points to a secret in Key Vault. The application needs an identity with permission to read settings in App Configuration and permission to resolve secrets in Key Vault. Permissions across the two services are separate boundaries.

### 6.2. App Configuration Integration

Spring Cloud Azure provides starters/integrations for App Configuration per release. The dependency typically looks like:

~~~xml
<dependency>
    <groupId>com.azure.spring</groupId>
    <artifactId>spring-cloud-azure-starter-appconfiguration-config</artifactId>
</dependency>
~~~

Example store endpoint declaration:

~~~yaml
spring:
  cloud:
    azure:
      appconfiguration:
        stores:
          - endpoint: https://reservation-config.azconfig.io
            selects:
              - key-filter: "*"
                label-filter: prod
~~~

This is an illustrative structure; verify exact schema/property names for your Spring Cloud Azure version. Labels can separate environments or deployment rings. Do not use labels as a substitute for authorization: store read access is governed by identity/RBAC.

App Configuration supports conditional refresh via sentinel keys or integration refresh strategies. Only beans/config consumers designed to receive updates will change safely. For changes affecting connection pools, credentials, or bean wiring, recreating resources or restarting deployments may be necessary.

### 6.3. Key Vault References and Secrets

You can store references to Key Vault inside App Configuration instead of storing secret values directly. The application uses Managed Identity/Workload Identity to read App Configuration and resolve Key Vault secrets.

If using the Key Vault Secrets starter directly, dependencies and property source/ConfigData support depend on the release. Do not assume import prefixes mirror AWS or Google. Verify your Spring Cloud Azure version's docs to choose secret resolution, endpoints, and credential providers.

Key Vault roles should grant only read access to required secrets, not key/vault management permissions if the workload only reads. Secret versioning enables version control; rotation must be coordinated with the application and downstream services.

### 6.4. Azure Identity

Prefer Managed Identity for Azure-hosted workloads or Workload Identity when running on Kubernetes. `DefaultAzureCredential` supports environment-based credential selection, but configure it explicitly in production to avoid accidental fallback to developer credentials. Separate identities for App Configuration and Key Vault if different permissions are required.

### 6.5. Dynamic Refresh and Feature Flags

Azure App Configuration can refresh key-values and feature flags by policy. Set refresh intervals matching acceptable latency and request costs. Do not poll every key excessively often. Use a sentinel key to trigger refreshes only after a group of settings has been updated together.

Feature flags need safe defaults, owners, expiry dates, and post-rollout cleanup plans. Do not use feature flags as an authorization mechanism; access rights must be checked independently.

## 7. Google Cloud: Secret Manager and Application Config Sources

### 7.1. Secret Manager Is Not a General Configuration Service

Google Cloud Secret Manager stores secret versions, IAM policies, replication, and audits. It fits passwords, tokens, certificates/private keys, and sensitive values. Do not use a secret manager for non-sensitive keys such as page sizes, retry counts, or queue names simply because an API is available.

Google Cloud does not have a single general-purpose application configuration service directly equivalent to AWS AppConfig or Azure App Configuration for every use case. Common options include:

- Environment variables or deployment configuration for values tied to Cloud Run/GKE/Compute Engine.
- ConfigMaps for non-sensitive configuration in GKE.
- Git-backed Spring Cloud Config when centralized review/versioning is needed.
- Secret Manager for secrets and credentials.
- Custom application config services if dedicated dynamic refresh/feature flags are required.

### 7.2. Spring Cloud GCP Secret Manager Integration

Spring Cloud GCP provides Secret Manager integration per release. The dependency typically looks like:

~~~xml
<dependency>
    <groupId>com.google.cloud</groupId>
    <artifactId>spring-cloud-gcp-starter-secretmanager</artifactId>
</dependency>
~~~

Example enabling Secret Manager ConfigData integration:

~~~yaml
spring:
  config:
    import: sm://
~~~

Secrets can be referenced using the integration's prefix in appropriate properties/configs. Illustrative example:

~~~yaml
spring:
  datasource:
    password: sm://reservation-db-password
~~~

Starter names, import prefixes, project selection, and secret versions depend on the Spring Cloud GCP version. Verify the exact reference before applying; do not assume `sm://` is a built-in Spring Boot scheme outside this integration.

### 7.3. Workload Identity on GCP

In GKE, prefer Workload Identity Federation for GKE so Kubernetes service accounts map to authorized Google service accounts or principals. On Cloud Run, use the service's service identity. Locally, use Application Default Credentials for developer accounts per policy.

Grant Secret Manager Secret Accessor at the specific secret level whenever possible. Do not grant project-wide secret access if the workload only needs a few secrets. Secret Manager API access and application data access are two distinct layers.

### 7.4. Versions, Aliases, and Rotation

Secret Manager provides secret versions and enabled/disabled/destroyed states. Use aliases/version selection per policy; avoid hard-coding old versions if rotation is required. However, switching to the latest version does not automatically update in-memory objects in a running process. The application must re-read the secret, refresh credentials, or restart connection pools appropriately.

For database password rotation, coordinate in two phases: update the credential on the database/provider, then update the secret and refresh connection pools. Ensure an overlap window or rollback mechanism so all instances do not lose connectivity simultaneously.

## 8. Comparing Options Across Providers

| Need | AWS | Azure | Google Cloud |
| --- | --- | --- | --- |
| Centralized non-sensitive config | Parameter Store, AppConfig, Spring Cloud Config | App Configuration, Spring Cloud Config | Git/Config Server, deployment env, GKE ConfigMap |
| Dynamic feature flags | AppConfig | App Configuration Feature Management | Feature flag service or application solution |
| Secrets | Secrets Manager, Parameter Store SecureString | Key Vault | Secret Manager |
| Secret reference from config store | AppConfig integration/custom resolution by design | Key Vault reference in App Configuration | Secret Manager integration |
| Workload identity | IAM role | Managed Identity/Workload Identity | Workload Identity/Cloud Run service identity |
| Refresh | AppConfig polling/agent or integration-specific | App Configuration refresh | Integration-specific Secret Manager refresh; app config needs custom solution |

Do not decide solely from a feature checklist. Consider where the service runs, which cloud teams operate, latency/network boundaries, IAM models, audit requirements, refresh behavior, quotas, and costs. A multi-cloud Config Server can standardize application config; secrets typically still belong in the deployment environment's secret manager or a centrally managed vault.
## 9. Refresh, Rotation, and Runtime Lifecycle

### 9.1. Startup Loading vs. Runtime Refresh

A ConfigData loader normally reads configuration sources during bootstrap/startup. Once the application context is created, changes at the source do not automatically mutate every bean. Explicitly classify each key:

- **Startup-only:** Region, endpoints, pool sizes, TLS truststores, or topology requiring client recreation. Normally applied via restart/rollout.
- **Refreshable:** feature modes, business thresholds, or routing rules designed to be re-read safely.
- **Secret rotation:** passwords/tokens that must be reloaded and applied to clients/connection pools via a defined procedure.
- **Deployment config:** changes rolled out with workload deployments, not necessarily refreshed in place.

Never promise "dynamic config" just because a source supports updating values. The application must have mechanisms to receive changes, validate, publish, and apply them to running components.

### 9.2. Spring Cloud Config Refresh

Spring Cloud Config can coordinate with Spring Boot Actuator and Spring Cloud Bus to broadcast refresh events to multiple instances. Some applications expose a refresh endpoint to ask the context to update supported beans.

Example Actuator dependency:

~~~xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-actuator</artifactId>
</dependency>
~~~

A bean can be annotated with refresh scope:

~~~java
import org.springframework.cloud.context.config.annotation.RefreshScope;
import org.springframework.stereotype.Component;

@RefreshScope
@Component
public class NotificationPolicy {

    private final NotificationProperties properties;

    public NotificationPolicy(NotificationProperties properties) {
        this.properties = properties;
    }

    public boolean shouldSend(String eventType) {
        return properties.enabledEventTypes().contains(eventType);
    }
}
~~~

This example illustrates a bean that can be recreated within refresh scope; injection and property binding must be designed consistently. Do not slap `@RefreshScope` onto every bean indiscriminately. Clients holding connections, threads, executors, or native resources may require explicit closing/recreation.

Refresh endpoints and bus endpoints are sensitive management surfaces. Expose them only on protected management networks, enforce authentication/authorization, audit calls, and restrict who can invoke them. Never expose all Actuator endpoints on the public internet.

### 9.3. Safe Refresh Using Versioning and Validation

A refresh workflow should:

1. Fetch the new version from the config source.
2. Parse and bind into typed configuration.
3. Validate ranges, enums, cross-field constraints, and allow-lists.
4. Check whether dependencies can safely apply the new configuration.
5. Atomically swap to the new snapshot.
6. Record the version, timestamp, and refresh outcome.
7. If validation/application fails, retain the last known valid snapshot and raise an alert.

For configs spanning multiple related keys, prevent the application from observing a half-old, half-new state. Use versions/revisions or composite documents for atomic updates. Feature flags can have safe defaults; routing/security policies should never fall back to a more permissive state.

### 9.4. Secret Rotation Is More Than Reading a New Value

When a database password changes, existing connection pools may continue holding connections authenticated with the old credential. Updating a property does not automatically make a pool reconnect. The design must answer:

- Is a new secret version detected via polling, event, or restart?
- Does the new credential overlap with the old credential?
- Which credential does the pool use for new connections?
- How are old connections drained/closed?
- If partial rotation fails, can the secret/database be rolled back?
- Do token clients refresh before expiration?

For OAuth/client credentials, use a token provider that supports refresh; never cache access tokens indefinitely. For databases, prefer provider-supported rotation mechanisms and pools capable of credential updates/recreation. Never log secrets when rotation fails.

### 9.5. Do Not Use Config Refresh in Place of Deployment

Changing Regions, endpoints, TLS trust, network paths, encryption keys, or topology may require a restart/rollout. Changing connection pool counts or SDK clients also requires evaluating resource lifecycles. Refresh is appropriate only when code is built to read and apply updated values safely.

## 10. Fail-Fast, Fallback, and Outage Handling

### 10.1. Choosing Optional vs. Required

Config Server Client supports fail-fast/retry modes depending on version. ConfigData imports can use an optional prefix. The choice depends on the configuration category:

| Scenario | Typically Appropriate Behavior |
| --- | --- |
| Config Server required to locate production DB/queues | Fail startup if config cannot be retrieved |
| Supplementary config that does not affect safety, with valid defaults | Can be optional |
| Secrets needed for DB connections or token signing | Fail startup/operation; never use dummy or empty secrets |
| Non-critical feature flags | Use approved safe defaults |
| Temporary outage of dynamic config source | Retain last known valid snapshot, alert, and retry with bounds |

Optional does not mean safe. If missing remote properties cause an app to fall back to default endpoints or empty secrets, the application may start up only to fail later or connect to the wrong resources.

### 10.2. Config Client Retries

Config Client can be configured to retry when Config Server is temporarily unavailable. Depending on the release, retries require supporting dependencies and properties for attempts, initial interval, multiplier, and max interval. Total retry duration must fit within startup deadlines/orchestrator health checks.

Illustrative bounded retry policy example:

~~~yaml
spring:
  cloud:
    config:
      fail-fast: true
      retry:
        max-attempts: 6
        initial-interval: 1000
        max-interval: 2000
        multiplier: 1.1
~~~

Exact property names and retry dependencies depend on the Config Client release; some versions need Spring Retry/AOP and different retry properties when using ConfigData imports. Never copy a snippet without verifying it against your project's release train.

Do not retry indefinitely. If Config Server remains unreachable for long, rollouts can stall and exhaust capacity. Use timeouts, bounded retries, alerts, and recovery procedures. Never fall back to dev/local configuration in production.

### 10.3. Caching and Last-Known-Good

For dynamic configuration, you can retain the last valid snapshot to keep operating when the source is temporarily unavailable. The snapshot must:

- Be verified for source authenticity and version.
- Be stored securely per policy if it contains secrets.
- Have a maximum age limit and raise alerts when stale.
- Never contain more permissive settings when data is missing.
- Have an invalidation/rollback procedure.

Never cache secrets in plaintext files or uncontrolled shared volumes. If using a local agent cache, verify encryption, permissions, and restart behavior.

### 10.4. Circuit Breakers and Dependency Isolation

Do not let every business request call config/secret APIs directly. Load configuration at startup or via controlled refreshes/caches. Secret provider outages should not trigger request storms. Circuit breakers/backoff can be used in the integration layer; however, never keep using stale secrets past security policies or token expiry.

## 11. Protecting Configuration and Secrets

### 11.1. Secrets Must Not Be Committed to Git

Git-backed Config Servers are convenient for reviews and versioning, yet should not hold plaintext secrets. If using encrypted properties or a Vault backend, manage encryption keys/leases/tokens separately. A secret deleted from a current file still persists in Git history.

Rules:

- Store secrets in Secrets Manager, Key Vault, Secret Manager, or Vault.
- Store references/identifiers in the config repository instead of secret values.
- Restrict secret read access per service/environment.
- Never print Environment, binding objects, or full configs in logs.
- Never expose Actuator env/configprops publicly.
- Scan repositories and CI artifacts to detect committed credentials.
- Maintain rotation/revocation procedures when a secret leaks.

### 11.2. Config Server Encryption

Spring Cloud Config supports property encryption/decryption in certain setups. Encrypted values can be stored as ciphertext in the repository and decrypted by Config Server when serving clients.

This does not automatically replace a secret manager. Config Server becomes a component holding encryption capability; keys must be protected, rotated, backed up, and audited. If the server is compromised, an attacker could obtain decrypted config or abuse decrypt endpoints depending on permissions. Only expose encryption endpoints on a management network with strict authentication and authorization.

### 11.3. Identity and Least Privilege

Use distinct identities per service/environment:

- Config Client can read only its required application/profile/label.
- Config Server can read only the repositories/backends it manages.
- Workloads can read only the specific secrets they need.
- Runtime identities cannot create/delete secrets or modify policies unless required.
- CI/CD identities are authorized to publish config per workflow, separate from runtime credentials.

Separate roles for dev, staging, and production. Never use one service account with read access to every service's secrets.

### 11.4. TLS and Network Boundaries

Enable TLS between clients and Config Server/provider APIs. For private endpoints, configure DNS, routing, and firewalls/security groups/network policies properly. Verify certificate hostnames, truststore rotation, and proxies. Never disable certificate validation to work around connection errors.

### 11.5. Auditing and Data Classification

Every config change needs an actor, timestamp, source revision, environment, reason, and approval when required. Secret access requires separate auditing; never log secret values. Configuration may contain internal hostnames, account IDs, or topology; classify data before permitting access through Config Server/Actuator.
## 12. Testing Configuration and Provider Integration

### 12.1. Unit Testing Typed Configuration

Verify binding and validation with test values, without using real secrets:

~~~java
import static org.assertj.core.api.Assertions.assertThat;
import org.junit.jupiter.api.Test;
import org.springframework.boot.context.properties.bind.Binder;
import org.springframework.boot.context.properties.source.MapConfigurationPropertySource;

class StoragePropertiesTest {

    @Test
    void bindsStorageSettings() {
        var source = new MapConfigurationPropertySource();
        source.put("app.storage.provider", "s3");
        source.put("app.storage.bucket", "test-documents");
        source.put("app.storage.max-upload-bytes", "1048576");
        source.put("app.storage.read-timeout", "10s");

        StorageProperties properties = new Binder(source)
                .bind("app.storage", StorageProperties.class)
                .orElseThrow();

        assertThat(properties.provider()).isEqualTo("s3");
        assertThat(properties.maxUploadBytes()).isEqualTo(1048576);
    }
}
~~~

This example tests basic binding. For validation annotations, initialize validation infrastructure or use a Spring Boot test context to verify invalid values fail startup/tests as expected.

### 12.2. Testing Profiles and Property Precedence

Use test properties or test environments to verify:

- Local/staging/prod profiles select the right endpoints/buckets.
- Environment variables override only permitted keys.
- ConfigData imports follow the expected order.
- Missing required properties fail startup.
- Outages of optional sources do not cause the app to pick the wrong prod/local endpoint.
- Typed config validation catches out-of-range values.

Do not assert just a single property value. Test both which source wins and behavior when a source lacks a key or returns an invalid value.

### 12.3. Testing Config Client with Config Server

You can run a test Config Server instance backed by a local/test fixture repository or HTTP stub to test the client. Verify application name, profile, label, property source order, and error behavior. Never use production Config Server/secret stores in unit tests.

Contract tests should verify that the Config Server endpoint returns the expected property sources for an app/profile/label, the client binds types properly, and label/version updates propagate via the designed refresh/restart workflow.

### 12.4. Testing Provider Config Sources

Test integrations by provider:

- **AWS:** local test profiles with LocalStack when supported by the integration; staging verifies IAM roles, Parameter Store paths, Secrets Manager ARNs, KMS, and AppConfig sessions/agents.
- **Azure:** test App Configuration/Key Vault using a test store or Azure test subscription; verify Managed Identity/RBAC and Key Vault reference resolution.
- **Google Cloud:** test Secret Manager clients with suitable emulators/mocks; staging verifies Workload Identity and secret-level IAM.

Emulators do not prove real cloud IAM, network boundaries, encryption key policies, auditing, or rotation. Maintain a small staging contract test suite with cost caps and resource cleanup.

### 12.5. Keep Secrets Out of Test Artifacts

Use synthetic secrets and test-only identities. Never write real values into `application-test.yaml`, snapshots, assertion messages, build logs, reports, or CI environment dumps. When verifying secret resolution, assert that the bean receives the predefined test value without printing it to output.

## 13. Observing and Operating the Configuration Plane

### 13.1. Metrics to Monitor

| Metric | Meaning |
| --- | --- |
| Config fetch success/failure | Whether clients successfully retrieve property sources |
| Config fetch latency | Which source slows down startup/refresh |
| Refresh success/failure | Whether changes are being applied |
| Current config revision/label | Which version each instance is running |
| Secret access denied | Identity or policy issues |
| Secret refresh age | How old the active credential is |
| Config validation failures | Invalid values or schema drift |
| Config source availability | Whether Config Server/provider APIs are reachable |

Never include secret values, tokens, or raw configurations in metric labels. Revision, application name, and environment labels should have bounded cardinality.

### 13.2. Safe Logging and Tracing

Logs can record:

- Application name, profile, and config source type.
- Config revision/label/version.
- Fetch/refresh duration and outcome.
- Masked secret identifier if allowed by policy.
- Error code and correlation ID.

Never log the entire Environment, configuration properties objects, secret JSON, connection strings, or tokens. When debugging, print only key names and resolved/unresolved status; protect Actuator endpoints and management ports.

### 13.3. Config Server Outage Runbook

1. Check DNS, TLS, routing, and Config Server health.
2. Check Git/backend availability and server credentials.
3. Determine whether new instances are failing startup while old instances continue running on valid snapshots.
4. Never substitute local/dev profiles or empty secrets.
5. If using last-known-good, verify snapshot version and age.
6. Restore the backend/server, then roll out/refresh per policy.
7. Verify all instances are running the intended revision.

Config Server is a startup dependency and can become a central point of failure. Deploy with HA, health checks, connection timeouts, appropriate caching, and capacity for bursts when many instances restart simultaneously.

### 13.4. Failed Secret Rotation Runbook

1. Inspect the new secret version and its enabled status.
2. Verify workload identity has permission to read the new version and decrypt if required.
3. Verify downstream databases/APIs accept the new credential.
4. Check whether applications refreshed tokens/connection pools.
5. If a subset of instances fails, halt rollout and preserve access via the latest valid credential per security policy.
6. Recover/roll back rotation per the provider's runbook.
7. Confirm no secrets were logged or saved to temporary files.

### 13.5. Cost and Request Rate

Config/secret APIs have quotas and costs. Never call secret managers on every HTTP request. Cache secrets/config according to lifecycle, use reasonable agent/refresh intervals, and avoid continuously polling all keys. Secret rotation and config refreshes should include jitter so multiple replicas do not generate synchronized request bursts.

## 14. Common Issues

| Symptom | Possible Cause | Resolution |
| --- | --- | --- |
| Config Server returns 404 | Wrong application name/profile/label or repository layout | Check endpoint request and file naming |
| Client does not load remote config | Missing ConfigData import or wrong bootstrap mechanism | Check release train and `spring.config.import` |
| Local value overrides remote | Property precedence/override policy differs from expectation | Inspect Environment and version-specific override flags |
| App starts without secret | Optional import or unsafe empty default | Mark source required and validate at startup |
| AWS Parameter Store AccessDenied | Wrong role/path/KMS permission | Check task/pod role, path ARN, and `kms:Decrypt` |
| Azure App Configuration does not refresh | Misconfigured sentinel/refresh policy or identity | Check key filters, refresh triggers, and Managed Identity |
| Key Vault reference fails to resolve | Missing Key Vault permissions or bad reference | Check RBAC and endpoint/key references |
| GCP Secret Manager permission denied | Service identity lacks accessor role on secret | Check Workload Identity and secret-level IAM |
| Secret changed but connections still fail | Beans/pools hold old credentials | Refresh/recreate clients or roll out |
| Refresh creates half-old, half-new config | Multiple keys updated non-atomically | Use versioned snapshots and apply atomically |
| Slow Config Server startup | Slow Git clone, DNS/TLS, or backend | Intentional clone-on-start, timeouts, and health checks |
| Secret exposed in logs | Dumping Environment/config objects or exceptions | Mask logs, lock down Actuator, and rotate secrets |
## 15. Design and Migration Workflow

When migrating from hard-coded config or local YAML files to external configuration, follow this sequence:

1. Inventory active keys and classify them as application config, provider config, feature flags, or secrets.
2. Define owner, source of truth, profile/environment, and lifecycle for each key.
3. Choose Config Server, provider stores, or deployment environments per use case.
4. Design key naming/paths, labels, versions, and secret references.
5. Provision workload identities and least-privilege policies.
6. Add ConfigData/property source integrations and typed configuration validation.
7. Test locally, in integration, and under outage, refresh, and rotation scenarios.
8. Deploy to canary/staging, verifying resolved values and metrics.
9. Roll out to production; verify active revisions across all instances.
10. Remove legacy credentials/config after confirming zero remaining consumers.

Do not move every key into one provider store solely for centralization. Keep deployment settings close to the deployment system where fitting, application configs in a reviewed/versioned source, and secrets in a secret manager.

## 16. Production Readiness Checklist

1. **Classification:** every key classified as application config, provider config, feature flag, or secret.
2. **Ownership:** clear owner and source of truth; no overlapping sources lacking explicit precedence.
3. **Compatibility:** Spring Boot, Spring Cloud, and provider starters align on a compatible release train.
4. **ConfigData:** imports/profiles/labels and property precedence tested.
5. **Validation:** typed properties enforce type/range/enum and cross-field validation.
6. **Identity:** dedicated workload identities per service/environment; no static credentials in source.
7. **Least privilege:** read access scoped strictly to required apps/profiles/paths/secrets.
8. **Secret handling:** secrets absent from Git, logs, metrics, headers, and test artifacts.
9. **Refresh:** clear distinction between startup-only, refreshable, and restart-required keys.
10. **Rotation:** secret rotation procedure updates downstream and recreates clients/pools.
11. **Resilience:** fail-fast/optional, retries, timeouts, and last-known-good explicitly decided.
12. **Security:** TLS, management endpoints, auditing, and network boundaries secured.
13. **Testing:** unit, Config Server contract, provider staging, and outage/rotation tests.
14. **Operations:** metrics, alerts, revision visibility, and runbooks in place.
15. **Rollback:** ability to revert to a valid revision/config without restoring revoked secrets.

## 17. Practice Exercises

1. Classify 15 keys of a Spring Boot service into application config, provider config, feature flags, and secrets; identify the source of truth for each group.
2. Set up a Config Server with a Git backend and a Config Client using ConfigData import; verify application name/profile/label resolution.
3. Create local and prod profiles; test property precedence across YAML, environment variables, and remote config.
4. Bind storage/database properties using `@ConfigurationProperties`; add validation so startup fails on invalid buckets or timeouts.
5. Integrate AWS Parameter Store for a config path and Secrets Manager for a database password; grant a role read access strictly to those resources.
6. Use AWS AppConfig for feature flags; design refresh, caching, safe defaults, and rollback.
7. Integrate Azure App Configuration with environment labels and Key Vault references; verify the identity requires permissions on both services.
8. Use Google Secret Manager via Spring Cloud GCP; separate secrets from non-sensitive configuration loaded from environment/Config Server.
9. Simulate a Config Server outage at startup and at runtime; decide between fail-fast and last-known-good.
10. Simulate database secret rotation; prove the pool opens connections with the new credential without logging secrets.
11. Write tests proving a key comes from the expected source and overrides follow policy.
12. Design a runbook for when an invalid config revision rolls out to a subset of instances.

**Completion criteria:** learners accurately distinguish Spring Cloud Config from provider-native configuration/secret services, choose sources based on lifecycle and sensitivity, configure clients with ConfigData, apply workload identity/least privilege, control refresh/rotation/outages, and prove behavior through tests.

## References

- [Spring Boot Externalized Configuration](https://docs.spring.io/spring-boot/reference/features/external-config.html): property sources, profiles, ConfigData, and precedence.
- [Spring Cloud Config Reference](https://docs.spring.io/spring-cloud-config/reference/): Config Server, Config Client, backends, and encryption.
- [Spring Cloud Config — Client configuration](https://docs.spring.io/spring-cloud-config/reference/client.html): ConfigData imports, profiles, labels, and retries.
- [Spring Cloud AWS Reference](https://docs.awspring.io/spring-cloud-aws/docs/3.4.2/reference/html/index.html): Parameter Store and Secrets Manager integrations by release.
- [AWS Systems Manager Parameter Store](https://docs.aws.amazon.com/systems-manager/latest/userguide/systems-manager-parameter-store.html): parameter hierarchy, SecureString, and access control.
- [AWS AppConfig](https://docs.aws.amazon.com/appconfig/latest/userguide/what-is-appconfig.html): dynamic configuration, validation, and deployment strategies.
- [AWS Secrets Manager](https://docs.aws.amazon.com/secretsmanager/latest/userguide/intro.html): secret lifecycles and rotation.
- [Spring Cloud Azure documentation](https://learn.microsoft.com/azure/developer/java/spring-framework/): App Configuration, Key Vault, and identity integration.
- [Azure App Configuration](https://learn.microsoft.com/azure/azure-app-configuration/overview): key-values, labels, feature flags, and refresh.
- [Azure Key Vault](https://learn.microsoft.com/azure/key-vault/general/overview): secrets, keys, certificates, and access control.
- [Spring Cloud GCP Secret Manager](https://googlecloudplatform.github.io/spring-cloud-gcp/reference/html/index.html): Secret Manager integration and configuration.
- [Google Cloud Secret Manager](https://cloud.google.com/secret-manager/docs/overview): secret versions, IAM, and auditing.
