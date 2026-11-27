# Configuration sources fail to load or rotated secrets have not taken effect

Spring Boot may start up successfully yet continue using an outdated endpoint, feature flag, database password, or API key. Another common scenario is the application reporting a missing property even though the value already exists in AWS Systems Manager Parameter Store, AWS Secrets Manager, Azure Key Vault, or Google Cloud Secret Manager.

To diagnose accurately, separate three stages:

1. **Loading configuration sources:** Did Spring Boot locate the file, profile, import, or remote `PropertySource`?
2. **Selecting the effective value:** When multiple `PropertySource`s declare the same key, which source has higher precedence?
3. **Applying the new value:** Did beans, SDK clients, connection pools, and all replicas actually pick up the configuration after the secret was updated?

Creating a new secret version in the secret store only completes the update on the provider side. It does not automatically guarantee that the Spring `Environment` re-read it, singleton beans were recreated, or connection pools opened connections with the new credentials.

This article guides you through inspecting Spring Boot externalized configuration, loading Parameter Store/Secrets Manager/Key Vault/Secret Manager, provider-specific refresh mechanisms, and a credential rotation workflow verifiable in production. Examples cover Spring Boot applications integrating managed services from AWS, Azure, and Google Cloud.

## 1. Identifying which stage the failure belongs to

| Symptom | Stage to check first | Common cause |
| --- | --- | --- |
| Placeholder fails to resolve at startup | Loading configuration sources | Missing starter, wrong `spring.config.import`, wrong profile, path, or endpoint |
| Application uses value from `application.yml` instead of secret store | Selecting effective value | A higher-precedence `PropertySource` is overriding the key |
| Secret store has a new version, but business logs show old connections | Applying the new value | Reload disabled, polling interval not reached, unrefreshed bean, or stale cache |
| Some pods use the new secret while others use the old one | Replica synchronization | Rolling update incomplete, per-process cache, or some pods cannot read the source |
| Refresh reports success, yet DB connections still fail | Stateful resources | `DataSource`/connection pool/SDK client was created with the old credentials |
| Secret is missing and application still runs with default password | Loading configuration sources | Using `optional` import for a required secret or a placeholder with a default |
| Entire fleet loses connectivity immediately after secret rotation | Rotation procedure | Old credential was revoked before workloads switched to the new credential |
| Key Vault/Secret Manager value is right, but application reads wrong value | Mapping and binding | Secret name does not map to the expected property key, or wrong profile/project |

Do not start by logging secrets to compare them. First identify the `PropertySource` name, property origin, profile, version ID, and update timestamp. Secret values should only be read inside the processing flow that needs them and must never appear in logs.

## 2. How does Spring Boot load and select configuration?

### 2.1. Common configuration sources

Spring Boot can read properties from:

- Default properties declared by the application.
- `application.properties` or `application.yml` on the classpath.
- Configuration files external to the JAR.
- Profile-specific files such as `application-prod.yml`.
- `spring.config.import` from files, configuration trees, or library-provided integrations.
- OS environment variables.
- JVM system properties.
- `SPRING_APPLICATION_JSON`.
- Command-line arguments.
- `PropertySource`s added by frameworks or integration libraries.

Spring Boot defines a specific precedence order; higher-priority sources override values in lower-priority ones. In typical deployment environments, environment variables, system properties, and command-line arguments can override properties fetched from config data or secret stores.

For example, the secret store returns:

- `spring.datasource.username=orders_app`
- `spring.datasource.password=<secret value>`

However, the container still carries a stale `SPRING_DATASOURCE_PASSWORD` environment variable. Spring `Environment` may keep picking the environment variable. The secret store was updated correctly, yet the application continues using the old value due to a higher-precedence configuration source.

### 2.2. Profiles determine which files and sources are loaded

Check which profile the process is actually running with:

```bash
printenv SPRING_PROFILES_ACTIVE
```

On PowerShell:

```powershell
$env:SPRING_PROFILES_ACTIVE
```

If configured via profile:

```yaml
spring:
  profiles:
    active: prod
```

Spring Boot can load `application-prod.yml` and profile-specific variants of config locations/imports. Verify the profile on each pod or deployment revision; do not rely on your local machine's profile.

A file may load properly, yet an internal document has a `spring.config.activate.on-profile` condition that does not match. In that case, the expected configuration block will not appear in `Environment`.

### 2.3. spring.config.import and optional

Spring Boot supports importing additional config data:

```yaml
spring:
  config:
    import:
      - optional:file:/etc/orders/application-secrets.yml
      - configtree:/run/secrets/
```

- `file`: reads a specific configuration file.
- `configtree`: maps filenames inside a directory to property keys; file contents become values.
- `optional`: lets the application continue starting if the location does not exist.

`optional` is suitable for genuinely optional configuration. If a database password or signing key is mandatory, do not mark that import as `optional`. If the secret store is unreachable, startup should fail clearly rather than falling back to an invalid default.

Example mounting secrets as files:

```text
/run/secrets/
  spring.datasource.username
  spring.datasource.password
```

Loading into Spring `Environment`:

```yaml
spring:
  config:
    import: configtree:/run/secrets/
```

File contents bind to their matching property names. This works well with Kubernetes Secret volumes, Docker Secrets, or volume mounts managed by the deployment platform.

### 2.4. Distinguishing spring.config.location and spring.config.additional-location

This is a common reason default configuration files vanish:

- `spring.config.location` replaces the default locations Spring Boot searches.
- `spring.config.additional-location` adds new locations alongside the default ones.

If a deployment sets `SPRING_CONFIG_LOCATION=/etc/orders/`, the application may stop loading default files from the classpath as developers expected. If you only want to add external config files, check whether `spring.config.additional-location` should be used instead.

Both properties are read very early during bootstrap; they must be passed via environment variables, system properties, or command-line arguments.

### 2.5. Property names and environment variables

Spring Boot supports relaxed binding. Examples:

| Property key | Environment variable |
| --- | --- |
| `spring.datasource.url` | `SPRING_DATASOURCE_URL` |
| `spring.datasource.username` | `SPRING_DATASOURCE_USERNAME` |
| `spring.datasource.password` | `SPRING_DATASOURCE_PASSWORD` |
| `app.cloud.api-key` | `APP_CLOUD_APIKEY` per environment variable normalization rules |

When a secret store contains dotted keys while a deployment defines environment variables with a different spelling, inspect the binding rules and actual `PropertySource`s. Do not assume naming in Key Vault, Parameter Store, or Secret Manager always maps identically across integrations.

### 2.6. Loaded values do not mean beans change automatically

Example:

```java
import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Component;

@Component
public class PaymentGateway {

    private final String apiKey;

    public PaymentGateway(@Value("${app.payment.api-key}") String apiKey) {
        this.apiKey = apiKey;
    }
}
```

In a real application, `apiKey` is bound from configuration when the bean is created. If the secret store changes later, a singleton bean's field is not reassigned automatically just because Spring `Environment` has a new value.

For multi-field configuration, use `ConfigurationProperties`:

```java
import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "app.payment")
public class PaymentProperties {

    private String endpoint;
    private String apiKey;

    public String getEndpoint() {
        return endpoint;
    }

    public void setEndpoint(String endpoint) {
        this.endpoint = endpoint;
    }

    public String getApiKey() {
        return apiKey;
    }

    public void setApiKey(String apiKey) {
        this.apiKey = apiKey;
    }
}
```

Ensure this class is registered via `ConfigurationPropertiesScan` or `EnableConfigurationProperties`. Simply putting the annotation on the class without scanning/enabling it does not create a bean in the application context.

For a bean to pick up changes after a refresh, an appropriate refresh/rebind mechanism is required. If the bean constructs an SDK client or connection pool from these properties, that resource itself must also be recreated or updated safely.

## 3. Workflow to verify the effective configuration source

Follow these steps in order inside the exact failing container, pod, or VM.

### Step 1 — Confirm deployment revision and profile

Record:

- Service name, namespace, pod/container, and image version.
- Active profile.
- Process start time.
- Relevant `SPRING_CONFIG_*` and `SPRING_PROFILES_ACTIVE` variable names.
- Expected secret reference/version ID for the deployment.

Do not print the entire process environment, as it may contain tokens, passwords, or connection strings.

### Step 2 — Check dependencies and config imports

Verify that the corresponding starter is on the runtime classpath and matches the right release line. A dependency present only in `test` scope will not load remote configuration in production.

Inspect `spring.config.import` in configuration files and verify the scheme, path, and region/project/endpoint. If an import is missing, the application may fail to load that `PropertySource` even while other SDK clients in the application still work.

### Step 3 — Verify PropertySource names and property origin

Use Spring `Environment` to verify whether the property is found and which source provides the key. The following example logs only source names and presence/absence; it never logs values:

```java
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.boot.ApplicationArguments;
import org.springframework.boot.ApplicationRunner;
import org.springframework.core.env.ConfigurableEnvironment;
import org.springframework.core.env.PropertySource;
import org.springframework.stereotype.Component;

@Component
public class ConfigurationOriginProbe implements ApplicationRunner {

    private static final Logger log =
            LoggerFactory.getLogger(ConfigurationOriginProbe.class);

    private final ConfigurableEnvironment environment;

    public ConfigurationOriginProbe(ConfigurableEnvironment environment) {
        this.environment = environment;
    }

    @Override
    public void run(ApplicationArguments args) {
        String key = "spring.datasource.password";

        for (PropertySource<?> source : environment.getPropertySources()) {
            if (source.containsProperty(key)) {
                log.info("Property {} is present in source {}",
                        key, source.getName());
            }
        }

        log.info("Property {} resolved={}",
                key, environment.containsProperty(key));
    }
}
```

This snippet can reveal multiple sources containing the same key. The source visited earlier in `Environment` order has higher precedence. If you need the origin of a Boot-managed config value, use the origin/metadata support appropriate for your Boot version.

Never log `environment.getProperty(key)` when the key is a secret. Never enable full value display for Actuator `env` or `configprops` on public endpoints.

### Step 4 — Check binding and bean lifecycle

Check:

- Whether `ConfigurationProperties` is scanned/enabled.
- Whether prefix and field names match the property key.
- Whether the bean was instantiated before the remote `PropertySource` loaded.
- Whether the bean uses `RefreshScope` or a rebind mechanism.
- Whether dependent beans are recreated when their dependencies change.
- Whether SDK clients, `DataSource`, connection pools, or HTTP clients cache credentials separately.

A property appearing in `Environment` while the bean's field remains stale is usually a lifecycle/refresh issue, not a secret-loading failure.

### Step 5 — Compare all replicas

In multi-replica deployments, check each instance:

- Do pods share the same image/config revision?
- Is the same secret version being read?
- Has polling/reload executed on every replica?
- Does one pod have a different overriding environment variable?
- Does any pod lack permission to read the secret or fail to reach the private endpoint?

Only declare rotation successful once all traffic-serving replicas use the new configuration and real operations against the target service succeed.

## 4. AWS: Parameter Store and Secrets Manager

### 4.1. Choose the right integration and starter

Spring Cloud AWS 3.x provides dedicated starters:

```xml
<dependency>
    <groupId>io.awspring.cloud</groupId>
    <artifactId>spring-cloud-aws-starter-parameter-store</artifactId>
</dependency>

<dependency>
    <groupId>io.awspring.cloud</groupId>
    <artifactId>spring-cloud-aws-starter-secrets-manager</artifactId>
</dependency>
```

Manage versions with the Spring Cloud AWS BOM. Confirm the dependencies are on the runtime classpath and do not mix legacy Spring Cloud AWS 2.x properties with 3.x import schemes/configurations.

### 4.2. Loading configuration from Parameter Store

Suppose Parameter Store has these paths:

```text
/config/orders-api/database/username
/config/orders-api/database/password
/config/orders-api/payment/timeout
```

Load the path into Spring `Environment`:

```yaml
spring:
  application:
    name: orders-api
  config:
    import: aws-parameterstore:/config/orders-api/
```

Parameter Store integration fetches parameters under the specified path and adds them to `Environment`. If a required path does not exist or the SDK cannot read it, the application can fail at startup.

Only use `optional:aws-parameterstore:` when the path is genuinely optional. If a password is required, omit `optional` so misconfiguration is not hidden.

For sensitive data, use Parameter Store `SecureString`. Values are encrypted with AWS KMS; when using a customer-managed key, the principal reading the parameter also needs appropriate decrypt permissions on that key. Never store secrets in `String` or `StringList`.

### 4.3. Loading configuration from Secrets Manager

Suppose a JSON secret contains keys `url`, `username`, and `password`. You can add a prefix to prevent collisions:

```yaml
spring:
  config:
    import: "aws-secretsmanager:/secrets/prod/orders-db?prefix=spring.datasource."
```

Properties are mapped to:

- `spring.datasource.url`
- `spring.datasource.username`
- `spring.datasource.password`

If JSON keys do not match expected properties, inspect the secret structure, prefix, and import URI. If the secret is plain text, the integration can also load the value by secret name; cross-check the secret format and mapping behavior in your release.

The auto-configured `SecretsManagerClient` from the starter can also be used imperatively. When calling the client directly, specify the secret ARN/name, region, and credential provider clearly.

### 4.4. Checking IAM and KMS

Typically required permissions:

| Source | Permission to check |
| --- | --- |
| Secrets Manager | `secretsmanager:GetSecretValue` |
| Parameter Store | `ssm:GetParametersByPath` or the parameter-reading action matching the call |
| `SecureString` using customer-managed KMS key | `kms:Decrypt` on the matching key |

Check the resource ARN, account, region, path, and key policy. An application might be able to read one parameter yet fail on another due to IAM path restrictions or different KMS keys.

Verify with the AWS CLI under the same profile/role as the application:

```bash
aws sts get-caller-identity
aws ssm get-parameter --name /config/orders-api/database/username
aws secretsmanager describe-secret --secret-id /secrets/prod/orders-db
```

Do not run `get-secret-value` in a way that prints payloads to terminals/logs in tickets. When verifying values, inspect version IDs, timestamps, statuses, or purpose-built checksums without exposing secret contents.

### 4.5. Spring Cloud AWS PropertySource reload

Reload for Secrets Manager and Parameter Store is **disabled by default**. Having only `spring.config.import` loads values during bootstrap; it does not mean secrets are polled continuously.

To enable reload, configure a strategy and add the dependencies required by Spring Cloud AWS:

```xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-actuator</artifactId>
</dependency>
<dependency>
    <groupId>org.springframework.cloud</groupId>
    <artifactId>spring-cloud-commons</artifactId>
</dependency>
<dependency>
    <groupId>org.springframework.cloud</groupId>
    <artifactId>spring-cloud-context</artifactId>
</dependency>
```

Example for Secrets Manager:

```yaml
spring:
  cloud:
    aws:
      secretsmanager:
        reload:
          strategy: refresh
          period: 30s
```

Example for Parameter Store:

```yaml
spring:
  cloud:
    aws:
      parameterstore:
        reload:
          strategy: refresh
          period: 30s
```

Strategies:

- `refresh`: refreshes configuration beans annotated with `ConfigurationProperties` or `RefreshScope` via Spring Cloud Context.
- `restart_context`: gracefully restarts the Spring `ApplicationContext` and recreates beans.

With `restart_context`, the Actuator `restart` endpoint must be enabled and exposed per your version's documentation. This endpoint must be restricted to the management network and protected with authentication/authorization; never expose the restart endpoint on public ingress.

Set `period` explicitly based on operational requirements and check the exact properties for your release line. Frequent polling increases API calls and cost; slow polling extends the window during which applications hold old values.

### 4.6. AWS Secrets Manager Java cache

If the application uses the AWS Secrets Manager Java caching component instead of relying solely on Spring `PropertySource`, the cache has its own refresh cycle. Java cache documentation describes a default refresh interval of one hour; the cache has no instant invalidation mechanism.

Therefore, after updating a secret:

- Check cache TTL and refresh interval.
- Check whether the application retains references to stale cached values.
- Check whether the provider/client re-reads from the cache.
- If immediate change is required, use a supported cache/client refresh mechanism or a controlled rollout process.

Do not confuse Spring Cloud AWS `PropertySource` polling with the TTL of a custom Secrets Manager cache inside the service.

## 5. Azure: Spring Cloud Azure and Key Vault PropertySource

### 5.1. Loading secrets from Key Vault

Add the starter:

```xml
<dependency>
    <groupId>com.azure.spring</groupId>
    <artifactId>spring-cloud-azure-starter-keyvault-secrets</artifactId>
</dependency>
```

Example Key Vault `PropertySource` configuration:

```yaml
spring:
  cloud:
    azure:
      keyvault:
        secret:
          property-source-enabled: true
          property-sources:
            - name: orders-key-vault
              endpoint: https://orders-prod.vault.azure.net/
              secret-keys:
                - spring-datasource-url
                - spring-datasource-username
                - spring-datasource-password
              refresh-interval: 5m
```

Key Vault secret names only support a restricted character set, so dots in property keys are commonly represented as hyphens. For example, `spring-datasource-password` maps to property `spring.datasource.password`.

Use `secret-keys` to fetch only the secrets the application needs rather than loading the entire vault. Check secret names, case sensitivity, and mappings before concluding Key Vault returned no data.

### 5.2. Checking PropertySource priority

Spring Cloud Azure Key Vault `PropertySource` has its own precedence order. Per current documentation:

- When `SystemEnvironmentPropertySource` is present, environment variables take higher precedence than the Key Vault `PropertySource`.
- When multiple Key Vault `PropertySource`s are configured, declaration order determines priority.

For instance, Key Vault has the updated password, yet the deployment still contains an old `SPRING_DATASOURCE_PASSWORD`. Spring may keep using the environment variable. Inspect the Deployment/Helm/Container App/App Service manifest and remove obsolete overrides.

Never print environment variable values to investigate. Check only whether the variable exists, the configuration source, and when the deployment changed.

### 5.3. Key Vault refresh interval

`KeyVaultPropertySource` refreshes every 30 minutes by default. You can change this with:

```yaml
spring:
  cloud:
    azure:
      keyvault:
        secret:
          property-sources:
            - name: orders-key-vault
              endpoint: https://orders-prod.vault.azure.net/
              refresh-interval: 5m
```

Setting `refresh-interval: 0` disables auto refresh. If the application still uses the old value, check:

1. Is the property source enabled?
2. Is `refresh-interval` set to `0` or too long?
3. Does the process have permission to read the new secret version?
4. Is an environment variable overriding it?
5. Are the beans/clients using the property updated?

Refreshing the `PropertySource` and refreshing stateful resources are two separate things to verify. Do not assume `@Value` fields, SDK clients, `DataSource`, or connection pools updated automatically just because `KeyVaultPropertySource` read the new version.

### 5.4. Checking permissions and secret state

With Microsoft Entra ID, verify:

- The workload's actual principal (managed identity/service principal).
- Read permission on the right Key Vault.
- Whether the Key Vault uses Azure RBAC or access policies.
- Whether the new secret version is enabled.
- Whether the secret is expired, disabled, or in another vault.
- Whether the application's endpoint and tenant are right.

A common data-plane role is `Key Vault Secrets User` or a narrower permission satisfying secret reads. Subscription `Contributor` does not substitute for data-plane secret read permissions.

If checking with the Azure CLI, ensure the CLI identity matches the relevant principal. A CLI user having access does not prove the Java process's managed identity also has access.

### 5.5. When using SecretClient directly

If the application calls the Azure Key Vault SDK directly, check the exact secret name and version. `SecretClient` can fetch the current version by secret name; if code passes a specific version string, it will keep reading that exact version even after a new version is created.

When a secret changes, check whether the client invokes `getSecret` again or holds a `KeyVaultSecret`/value read earlier in a singleton bean or internal cache.

## 6. Google Cloud: Secret Manager and Secret Version

### 6.1. Secret Manager stores immutable versions

Google Cloud Secret Manager does not overwrite the payload of an existing version. During rotation, create a new secret version. A secret can have multiple versions in `enabled`, `disabled`, or `destroyed` states.

The `latest` alias points to the most recently created version. While convenient for development, it can roll out a broken value across all workloads. Google documentation recommends considering pinning version IDs in production and deploying through a release process for controlled rollouts/rollbacks.

### 6.2. Verify project, identity, and IAM

Check the project used by the Java client, the workload's service account/Workload Identity, and that the Secret Manager API is enabled.

The permission typically required to read a version is `secretmanager.versions.access`. The commonly used predefined role is `roles/secretmanager.secretAccessor`, which should be granted at the secret scope if possible rather than project-wide.

For Compute Engine or GKE, check VM/node OAuth access scopes if scopes still apply in your environment; Secret Manager requires the `cloud-platform` scope. For GKE Workload Identity or external workload identity, verify the federation binding and principal.

### 6.3. Reading a secret version in Java

Example using Google Cloud Secret Manager Java Client:

```java
import com.google.cloud.secretmanager.v1.AccessSecretVersionResponse;
import com.google.cloud.secretmanager.v1.SecretManagerServiceClient;
import com.google.cloud.secretmanager.v1.SecretVersionName;

public byte[] loadSecret(
        SecretManagerServiceClient client,
        String projectId,
        String secretId,
        String versionId) {

    SecretVersionName name =
            SecretVersionName.of(projectId, secretId, versionId);

    AccessSecretVersionResponse response =
            client.accessSecretVersion(name);

    return response.getPayload().getData().toByteArray();
}
```

Pass a specific version ID, such as `12`, when deploying an approved version. Use `latest` only when application policy accepts receiving the newest version on each read. Never print payloads to logs or console.

Create `SecretManagerServiceClient` once during the application lifecycle and reuse it across accesses; close the client on shutdown. Do not create a new client per request.

If code reads the secret once at startup and stores the byte array/string in a bean, adding a new version does not alter the loaded content. You must re-read on a schedule/event or redeploy the process.

### 6.4. Using Pub/Sub notifications to coordinate rotation

Secret Manager can publish events to a Pub/Sub topic when a secret or version changes. Events include:

- `SECRET_VERSION_ADD`
- `SECRET_VERSION_ENABLE`
- `SECRET_VERSION_DISABLE`
- `SECRET_VERSION_DESTROY`
- `SECRET_ROTATE`

Notifications do not automatically update Spring beans. Your application or subscriber workflow must receive the event, identify the changed secret/version, verify its state, and decide to refresh, restart, or roll out the deployment.

For rotation schedules, `SECRET_ROTATE` is a signal for a workflow to execute rotation steps. It neither creates a new credential in the target database/API nor updates every application consuming the secret.

A workflow might perform:

1. Receive event from Pub/Sub.
2. Create a new credential on the target system while the old credential remains active.
3. Add a new version to Secret Manager.
4. Roll out the new version via deployment strategy or trigger a controlled refresh.
5. Verify all replicas use the new version and connect successfully.
6. Revoke the old credential once no workload uses it.

### 6.5. Spring Cloud Config Server backend for Google Secret Manager

If your architecture already uses Spring Cloud Config Server, you can configure Config Server's Google Secret Manager backend. This backend requires the `secret-manager` Spring profile and the `google-cloud-secretmanager` library on Config Server's classpath.

This is a **Config Server** integration, distinct from merely adding the Google Cloud Secret Manager Java Client to a regular Spring Boot application. With this backend, Config Server builds a `PropertySource` from secret payloads matched by application/profile labels. Current documentation describes picking the newest enabled version by version number; do not assume client applications automatically poll Secret Manager without configuring Spring Cloud Config's refresh mechanism.

If the application does not use Config Server, use the Secret Manager Java Client or a dedicated configuration workflow. Do not assume a native `spring.config.import` scheme exists for Google Secret Manager like `aws-secretsmanager:` unless your dependency/release line actually provides one.

## 7. Why do connections still use old details after a secret changes?

### 7.1. Singleton beans hold initialization-time values

A bean using `@Value` normally receives its value when Spring instantiates the bean. Changing a `PropertySource` does not automatically update that field.

How to handle:

- Use `ConfigurationProperties` for refreshable configuration groups.
- Combine Spring Cloud Context refresh with `RefreshScope` for suitable beans.
- Recreate secret-dependent beans/clients on refresh.
- If safe refresh is not possible, roll out/restart instances following your release procedure.

### 7.2. RefreshScope does not automatically apply to every dependent bean

Marking a factory/configuration bean with `RefreshScope` does not mean every bean produced by that factory refreshes automatically. Beans holding references to the old client may also continue using old credentials.

For SDK clients, HTTP clients, or database connection pools, identify clearly which objects must be recreated and who owns their lifecycle.

Spring Cloud has restrictions on specific bean types. For example, `HikariDataSource` is listed among default non-refreshable beans in Spring Cloud Refresh Scope. For a Hikari datasource, design an appropriate rotation/restart flow rather than adding `RefreshScope` and expecting the pool to swap credentials on its own.

### 7.3. Connection pools retain old connections

A database may allow existing sessions to remain active even after the old password is changed. When the pool opens a new connection, however, authentication will fail.

Check:

- Has the pool closed old connections and opened new ones?
- Do connection lifetime/idle timeouts allow the pool to reuse old sessions?
- Does the new credential have permissions and does the database user exist?
- Does the database support two active credentials concurrently during the transition window?
- Was the pool closed/recreated after binding the new configuration?

Never revoke the old password immediately upon writing the new password to the secret store. Wait for workloads to switch and verify first.

### 7.4. SDK clients or secret caches hold old values

Some clients/caches store credentials or fetched payloads in memory. Check:

- Cache TTL and refresh policy.
- Whether the client receives a dynamic provider or a static provider.
- Whether the client was built with a `StaticCredentialsProvider` holding the old value.
- Which beans retain references to the secret string/byte array.
- Whether multiple cache layers exist (Spring, SDK, application, sidecar).

If an SDK supports a credential provider capable of refreshing tokens/credentials automatically, prefer it over static credentials where applicable. However, a token-refreshing provider does not automatically re-read passwords/API keys from a secret store.

### 7.5. Unsynchronized replicas

In Kubernetes or multi-instance setups, each process has its own cache, timers, and startup time. Some pods may have refreshed while others have not yet reached their poll interval or are hitting permission/network errors.

Compare secret version metadata and reload timestamps across each replica. Never log payloads to figure out which version a replica is using.

## 8. Symptom-based troubleshooting matrix

| Symptom | Possible cause | How to check |
| --- | --- | --- |
| Could not resolve placeholder | Missing import/profile/property key | Check active profile, config import, property name, and startup logs |
| AWS fails to load Parameter Store | Missing starter, wrong scheme/path, region, or IAM | Check `aws-parameterstore` import, SSM endpoint/region, and `ssm:GetParametersByPath` |
| AWS fails to load Secrets Manager | Wrong secret name/region, missing `GetSecretValue`, KMS decrypt denied | Check secret ARN, account/region, IAM, and KMS key policy |
| Secret changed, but AWS does not reload | Reload disabled by default or refresh dependencies missing | Enable reload strategy, add Actuator/Spring Cloud Context dependencies, check polling |
| AWS reload runs, yet beans do not change | Bean does not use `ConfigurationProperties`/`RefreshScope` | Check bean lifecycle or choose `restart_context` |
| Parameter Store returns old value | Wrong path, version/label, or overridden property | Check parameter path, profile, and `PropertySource` precedence |
| Key Vault fails to load | Starter/property source not enabled, wrong endpoint or credentials | Check `property-source-enabled`, endpoint, managed identity, and Key Vault role |
| Key Vault has a new version, but app uses old one | `refresh-interval` too long/0 or bean holds old value | Check `refresh-interval`, bean scope, and refresh timestamps |
| Key Vault secret changed, yet has no effect | Environment variable has higher precedence than Key Vault | Check `SPRING_*` variable names in deployment without printing values |
| Key Vault secret key fails to map to property | Wrong dots/casing/key name | Apply hyphen mapping rules, check case sensitivity and `secret-keys` |
| GCP reads wrong secret version | Code pins old version or uses `latest` unintentionally | Check version ID passed to `SecretVersionName` |
| GCP fails to read secret | Wrong project/principal, missing `secretmanager.versions.access`, or API disabled | Check ADC/runtime service account, IAM, and API enablement |
| GCP created new version, yet app does not change | App only reads once at startup | Add polling/event subscriber or roll out deployment |
| GCP notification arrives, yet app does not refresh | Pub/Sub subscriber only receives events without an update handler | Check subscription, event type, retry/DLQ, and workflow |
| Refresh succeeds, yet DB still fails | Connection pool retains old connections/credentials | Recreate pool per lifecycle or roll out instances |
| Some pods use old secret | Unsynchronized polling/cache/restart or pod cannot read store | Check version metadata, logs, and rollout status per pod |
| Application still runs with default password | Secret import marked `optional` or placeholder has a default | Remove `optional`/defaults on required secrets and fail fast |
| Secret store reads fine, yet value is wrong | Another `PropertySource` overrides it | Check origin and precedence, especially environment/system/CLI |
| 401/403 spikes after rotation | New credential lacks permissions or old credential revoked too early | Check credential state on target system and rollout timing |
| Connection errors spike after refresh | Dependent beans recreated without proper lifecycle handling | Check graceful shutdown, connection pool, and in-flight requests |

## 9. Safe secret rotation workflow

Secret rotation should be a stateful workflow, not a single payload-overwrite command.

### Step 1 — Identify all consumers

List:

- Applications and deployments using the secret.
- Region/project/subscription/vault hosting the secret.
- Current secret version.
- Caches, sidecars, connection pools, and SDK clients holding the secret.
- Non-Spring Boot consumers such as batch jobs, migrations, workers, or scheduled tasks.

### Step 2 — Create the new credential on the target system

If the target system supports two concurrent credentials, create the new credential and keep the old one active during the transition window. For databases, you can alternate users or grant permissions to a new user before shifting workloads.

If the system permits only one credential at a time, plan a maintenance/rollout window and a separate rollback procedure.

### Step 3 — Save the new version in the secret store

Create a new version in AWS Secrets Manager, update Parameter Store, or create a new secret version in Azure Key Vault or Google Secret Manager. Record the version ID, timestamp, and state; never paste payloads into tickets.

### Step 4 — Trigger application updates

Pick the appropriate mechanism:

- Spring Cloud AWS: `PropertySource` reload with a suitable strategy or rolling restart.
- Azure Key Vault: refresh interval and bean/client recreation mechanism; if no suitable refresh lifecycle exists, rolling restart.
- Google Secret Manager: subscriber/polling workflow or update pinned version in deployment and roll out.
- Kubernetes Secret volume/config tree: verify how the volume updates and whether process restart is required.

### Step 5 — Verify all replicas

Verify:

- Loaded version ID or metadata.
- Connections to the target database/API succeed.
- Error rates do not rise.
- Workers/background jobs also use the new credential.
- No requests are still signed or authenticated with the old credential.

Use a health check capable of verifying real connectivity without returning secrets or sensitive details on public health endpoints.

### Step 6 — Revoke the old credential

Revoke only after all consumers have switched to the new credential and the drain window for old connections/sessions has elapsed. If errors appear, roll back to the saved good version and restore the old credential's privileges per emergency runbook.

## 10. Lab: updating the database password for Orders API

Goal: Orders API uses a password from the secret store to connect to PostgreSQL. After rotation, all replicas must connect using the new password.

### Step 1 — Declare the configuration source

Pick the mechanism matching your environment:

AWS Secrets Manager:

```yaml
spring:
  config:
    import: aws-secretsmanager:/secrets/prod/orders-db?prefix=spring.datasource.
```

Azure Key Vault:

```yaml
spring:
  cloud:
    azure:
      keyvault:
        secret:
          property-source-enabled: true
          property-sources:
            - name: orders-db
              endpoint: https://orders-prod.vault.azure.net/
              secret-keys:
                - spring-datasource-url
                - spring-datasource-username
                - spring-datasource-password
              refresh-interval: 5m
```

Google Secret Manager uses the Java client or configured Config Server backend. If pinning versions, set the version ID in deployment configuration.

### Step 2 — Bind properties to datasource configuration

```yaml
spring:
  datasource:
    url: jdbc:postgresql://orders-db.internal:5432/orders
    username: orders_app
    password: REQUIRED_FROM_SECRET_STORE
```

The placeholder string shown here must never serve as a production default password. Real configuration must ensure the secret store supplies the required property and startup fails if it is missing.

### Step 3 — Create the new credential and store a new version

Create a new password for the database user or alternating user. Update the secret store and record the version ID/timestamp.

Keep the old credential valid during rollout if the database supports two concurrent users or passwords.

### Step 4 — Refresh or roll out

If using Spring Cloud AWS reload, verify the reload strategy and bean scopes. If using Azure Key Vault, wait for the refresh interval or trigger a controlled rollout. If using GCP Secret Manager, emit the event/deploy the new version per workflow.

For `HikariDataSource`, plan a pool recreation or rolling restart because the active pool may not be supported by refresh scope.

### Step 5 — Verify

Each replica should safely report:

- Active secret version ID/metadata.
- Datasource health check.
- Result of opening a new connection.
- Count of authentication failures.
- Deployment revision and refresh timestamp.

Never print URLs with embedded credentials, passwords, or secret payloads.

### Step 6 — Revoke the old password

After all replicas and jobs have moved to the new credential, revoke the old user/password and monitor connection errors for a window appropriate to the workload.

## 11. Protecting secrets during troubleshooting

- Never log secret payloads, access tokens, API keys, private keys, SAS tokens, or full connection strings.
- Never pass secrets in command-line arguments, as they can appear in process lists or shell history.
- Never enable Actuator endpoints displaying raw configuration values on public ingress.
- If `/refresh` or `/restart` must be used, expose them only on an authenticated, authorized management interface.
- Never grant read access to an entire vault/project/account just to inspect one secret.
- Record secret names, version IDs, timestamps, and provider request IDs instead of payloads.
- Use rollback-capable secret versions and keep old credentials during transition windows when the target system supports it.
- Disable old versions before destroying them if the platform supports an intermediate state and you need verification time.
- Never mark required secrets as `optional` or supply default passwords in production.
- Inspect masked logs/traces before sharing them with support teams.

## 12. Key takeaways

- Loading config, selecting the winning `PropertySource`, and applying config to beans are three separate stages.
- `spring.config.import` loads remote config during bootstrap; `optional` can mask missing required secrets.
- `spring.config.location` replaces default locations; `spring.config.additional-location` appends locations.
- Environment variables, system properties, or command-line arguments can override values from a secret store.
- `@Value` resolves when the bean is constructed; singleton beans do not update fields automatically when the secret store changes.
- Spring Cloud AWS Secrets Manager/Parameter Store reload is disabled by default. Enable the appropriate strategy, refresh dependencies, and bean scopes.
- Azure Key Vault `PropertySource` refreshes every 30 minutes by default; environment variables can take higher precedence.
- Google Secret Manager creates immutable versions. `latest` is convenient, but production should generally pin versions and roll out in a controlled manner.
- Secret Manager Pub/Sub notifications only initiate workflows; applications must perform refresh/restart/rollout themselves.
- `RefreshScope` does not automatically refresh every dependent bean. Connection pools and SDK clients require explicit lifecycle handling.
- Retain old credentials during transition windows when the target system allows it, verify every replica, and revoke only afterward.
- Mark rotation complete only when real requests to the target database/API succeed across all replicas.

## Official reference documentation

1. [Spring Boot — Externalized Configuration](https://docs.spring.io/spring-boot/reference/features/external-config.html)
2. [Spring Cloud — Refresh Scope](https://docs.spring.io/spring-cloud-commons/reference/spring-cloud-commons/application-context-services.html)
3. [Spring Cloud AWS 3.4.2 — Secrets Manager integration and PropertySource reload](https://docs.awspring.io/spring-cloud-aws/docs/3.4.2/reference/html/index.html)
4. [Spring Cloud AWS 3.4.2 — Parameter Store integration and PropertySource reload](https://docs.awspring.io/spring-cloud-aws/docs/3.4.2/reference/html/index.html)
5. [AWS Systems Manager — Parameter Store and SecureString](https://docs.aws.amazon.com/systems-manager/latest/userguide/what-is-a-parameter.html)
6. [AWS Secrets Manager — Java client-side caching](https://docs.aws.amazon.com/secretsmanager/latest/userguide/retrieving-secrets_cache-java.html)
7. [AWS Secrets Manager — Rotation schedules](https://docs.aws.amazon.com/secretsmanager/latest/userguide/rotate-secrets_schedule.html)
8. [Spring Cloud Azure — Secret Management with Key Vault](https://microsoft.github.io/spring-cloud-azure/current/reference/html/index.html)
9. [Spring Cloud Azure — KeyVaultPropertySource refresh interval and priority](https://learn.microsoft.com/en-us/azure/developer/java/spring-framework/secret-management)
10. [Google Cloud Secret Manager — Access a secret version](https://docs.cloud.google.com/secret-manager/docs/access-secret-version)
11. [Google Cloud Secret Manager — Rotation recommendations](https://docs.cloud.google.com/secret-manager/docs/rotation-recommendations)
12. [Google Cloud Secret Manager — Event notifications](https://docs.cloud.google.com/secret-manager/docs/event-notifications)
13. [Google Cloud Secret Manager — Rotation schedules](https://docs.cloud.google.com/secret-manager/docs/secret-rotation)
14. [Spring Cloud Config — Google Secret Manager backend](https://docs.spring.io/spring-cloud-config/reference/server/environment-repository/gcp-secret-manager-backend.html)

Property names, refresh intervals, and reload capabilities depend on starter/SDK versions. Check your running BOM and release line; after every rotation, verify property origin, bean lifecycle, new connections, and per-replica status rather than assuming success just because the secret store recorded a new version.
