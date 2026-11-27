# Integrating OCI Vault and Secret Configuration Sources

Spring Boot applications regularly need database passwords, API tokens, signing keys, SMTP credentials, or credentials to call external services. If these values are stored in source code, `application.yaml`, or container images, they can leak through Git, build logs, artifacts, backups, or overly broad access permissions.

Oracle Cloud Infrastructure (OCI) Vault provides centralized secret storage and management. The Spring Cloud OCI Vault starter connects this service to Spring in two ways: exposing secrets into the Spring `Environment` as a property source, or providing `VaultTemplate` so the application can retrieve secrets on demand.

These two approaches solve different needs. Property sources fit configuration loaded alongside the application; `VaultTemplate` fits on-demand secret retrieval and secret lifecycle management. Both require proper identity and IAM policies, a rotation plan, sensible caching, and handling for when Vault is temporarily unreachable.

## 1. Learning Objectives

After this lesson, learners can:

1. Distinguish OCI Vault, encryption keys, secrets, and secret bundles.
2. Choose the right Spring Cloud OCI Vault starter.
3. Configure Vault as a property source for the Spring `Environment`.
4. Inject secrets into application configuration without writing secret values into the repository.
5. Use `VaultTemplate` to retrieve secrets on demand.
6. Understand secret versions, rotation states, and the version promotion workflow.
7. Design refresh, caching, and rotation for singleton beans and connection pools.
8. Grant IAM policies permitting a workload to read only the required secrets.
9. Distinguish secret read permissions from Vault and encryption key administration permissions.
10. Handle timeouts, 401s, 403s, nonexistent secrets, and Vault unavailability.
11. Test property sources, `VaultTemplate`, rotation, and least privilege.
12. Operate secrets safely across local development, CI/CD, and production.

## 2. What Components Make Up OCI Vault?

The name Vault is commonly used for both the service and the secret container, so distinguish several concepts:

- **Vault:** a resource in the OCI Key Management Service that manages encryption keys and related configuration.
- **Key:** an encryption key used to protect data/secrets according to service configuration.
- **Secret:** a logical resource representing a sensitive value, such as a database password or API token.
- **Secret version:** a content version of a secret. When content changes, OCI creates a new version.
- **Secret bundle:** the payload returned when reading a secret, including secret content, version info, and related metadata.
- **Secret Management Service:** APIs for managing secrets and APIs for reading secret bundles. These two operation groups have separate endpoints.

~~~mermaid
flowchart TD
    A[OCI Vault] --> B[Encryption Key]
    A --> C[Secret Management]
    C --> D[Secret: invoice-db-password]
    D --> E[Version 1: PREVIOUS]
    D --> F[Version 2: CURRENT]
    D --> G[Version 3: PENDING]
    F --> H[Secret Bundle]
    H --> I[Spring Cloud OCI Vault]
    I --> J[Spring Environment]
    I --> K[VaultTemplate]
    J --> L[Spring Boot configuration]
    K --> M[Application service]
~~~

An application that only reads secrets normally needs permission to read secret bundles. It does not necessarily need permission to create Vaults, create encryption keys, rotate keys, or delete secrets. Separate runtime permissions from administrative permissions to reduce blast radius if application credentials are compromised.

### Vault Is Not the Place to Store Every Kind of Data

Choose the service by data type:

| Data | Suitable Service |
| --- | --- |
| Passwords, API tokens, credentials | OCI Vault Secret |
| Encryption keys requiring lifecycle management | OCI Key Management/Vault |
| PDFs, images, archives | OCI Object Storage |
| Queryable business data | Database |
| Non-sensitive configuration | Spring configuration, Config Server, or appropriate config source |

Do not store large files or routine business data inside secrets just because Vault can store strings.

## 3. Choosing the Spring Cloud OCI Vault Starter

Maven:

~~~xml
<dependency>
    <groupId>com.oracle.cloud.spring</groupId>
    <artifactId>spring-cloud-oci-starter-vault</artifactId>
    <version>${spring-cloud-oci.version}</version>
</dependency>
~~~

Gradle:

~~~groovy
dependencies {
    implementation("com.oracle.cloud.spring:spring-cloud-oci-starter-vault:${springCloudOciVersion}")
}
~~~

The starter version must be compatible with the Spring Boot and Spring Cloud OCI release line the application uses. Do not assign the Spring Cloud release train version or an Oracle Database starter version to the OCI Vault starter. Check the release notes and dependency graph for that exact version.

The Vault starter relies on Spring Cloud OCI core authentication. If the application already includes another service starter that pulls in core, inspect the dependency graph before declaring core again.

## 4. Configuring OCI Vault

Spring Cloud OCI Vault can reuse the OCI authentication, region, and compartment configured in the core starter. In addition, the Vault integration needs to know the compartment and Vault OCID.

Key properties:

| Property | Meaning | Required |
| --- | --- | --- |
| `spring.cloud.oci.vault.enabled` | Enables/disables OCI Vault integration | No; defaults to `true` per starter docs |
| `spring.cloud.oci.vault.compartment` | Compartment for Vault API and property sources | Yes |
| `spring.cloud.oci.vault.vault-id` | Vault OCID used for the Vault API | Yes when using `VaultTemplate`/API via config |
| `spring.cloud.oci.vault.property-refresh-interval` | Property source refresh interval | No; defaults to `10m` |
| `spring.cloud.oci.vault.property-sources` | List of Vaults used as Spring property sources | No |
| `spring.cloud.oci.vault.property-sources[i].vault-id` | Vault OCID for an individual property source | Yes per entry |

Basic configuration example:

~~~yaml
spring:
  cloud:
    oci:
      config:
        type: INSTANCE_PRINCIPAL
      region:
        static: ${OCI_REGION}
      vault:
        enabled: true
        compartment: ${OCI_COMPARTMENT_OCID}
        vault-id: ${OCI_VAULT_OCID}
~~~

Uppercase values in the example are placeholders. In real applications, supply them via environment variables, secret mounts, or deployment configuration. Never commit real environment OCIDs or secret contents to the repository if organizational policy treats them as sensitive.

### Region and Compartment

- Region must match the region containing the Vault and secrets.
- The compartment property is the default for Vault integration operations that use it.
- Secrets can reside in a different compartment from the Vault resource; verify the actual secret scope and policy.
- The compartment property does not grant IAM permissions on its own.
- If the application accesses multiple regions or multiple Vaults, configure each source explicitly.

### Choosing Authentication

Common authentication types:

| Environment | Suggested Authentication |
| --- | --- |
| Developer machine | `FILE` or `SESSION_TOKEN` |
| OCI Compute | `INSTANCE_PRINCIPAL` |
| OCI Functions | `RESOURCE_PRINCIPAL` |
| OKE | `WORKLOAD_IDENTITY` if cluster/workload configured |
| External CI outside OCI | Organization-approved identity/federation |

Do not use a developer's personal API key as a long-term credential for production workloads whenever workload identity is available.

## 5. Using Vault as a Spring Property Source

This is the simplest way to bring secrets into the Spring `Environment`. The starter loads secrets from the Vaults declared under `property-sources`; each secret's name becomes a property name.

Example:

~~~yaml
spring:
  cloud:
    oci:
      config:
        type: INSTANCE_PRINCIPAL
      region:
        static: ${OCI_REGION}
      vault:
        enabled: true
        compartment: ${OCI_COMPARTMENT_OCID}
        property-refresh-interval: 10m
        property-sources:
          - vault-id: ${OCI_VAULT_OCID}
~~~

Suppose the Vault contains a secret named `invoice-db-password`. The application can read the property via Spring:

~~~java
@Configuration
public class DatabaseCredentialConfig {

    @Value("${invoice-db-password}")
    private String databasePassword;

    // Use databasePassword when configuring DataSource
}
~~~

In real applications, secret names must follow organizational naming conventions and work cleanly with Spring property resolution. Prefer simple, consistent names and avoid creating multiple secrets whose names differ only by letter case or separators.

### 5.1. How Does the Property Source Work?

High-level workflow:

1. Spring Boot starts and loads configuration.
2. The OCI authentication provider establishes the application's identity.
3. The Vault integration calls the Secret Management API.
4. Secret bundles are fetched and decoded per the SDK/starter.
5. Secrets are registered into the Spring `Environment` under their corresponding property names.
6. Beans can resolve properties via `@Value` or `@ConfigurationProperties`.

Values in the Spring `Environment` reside in plaintext in application memory. Vault protects data at rest and in transit; it does not make secrets vanish from the heap, debuggers, heap dumps, or process memory once the application has read them.

### 5.2. Multiple Vaults/Property Sources

An application can declare multiple Vaults in `property-sources`:

~~~yaml
spring:
  cloud:
    oci:
      vault:
        enabled: true
        compartment: ${OCI_COMPARTMENT_OCID}
        property-sources:
          - vault-id: ${OCI_APPLICATION_VAULT_OCID}
          - vault-id: ${OCI_DATABASE_VAULT_OCID}
~~~

Separating Vaults by environment, domain, or access rights helps manage ownership. However, if two Vaults contain a secret with the same name, clarify the ordering and `PropertySource` precedence rules in your release version. Never let an application rely on duplicate names without tests confirming behavior.

### 5.3. Refreshing the Property Source

Spring Cloud OCI documentation describes `property-refresh-interval` as the interval for reloading properties from Vault. The default value is 10 minutes; set a duration greater than 0 to enable periodic refresh. For example, `10000ms` equals 10 seconds:

~~~yaml
spring:
  cloud:
    oci:
      vault:
        property-refresh-interval: 10m
~~~

An interval that is too short increases Secret Management API calls, system load, and throttling risk. An interval that is too long causes the application to keep holding stale values after a secret is rotated.

Choose the interval based on:

- Rotation frequency.
- Urgency when revoking credentials.
- Number of instances/replicas.
- OCI API rate limits and latency.
- Ability to reconnect/recreate clients.
- Acceptable window for old credentials remaining active.

Refreshing a property source does not mean every object that already injected the secret automatically changes. A singleton bean with an `@Value` field typically keeps the value injected at bean creation time. For `DataSource`, HTTP client, or SDK client credentials, design an explicit refresh/recreation mechanism or read dynamic values through a managed abstraction. Test rotation against real beans, not merely by checking whether the `Environment` received the new value.

## 6. Using `VaultTemplate` for On-Demand Secret Retrieval

The Vault starter auto-configures a `VaultTemplate` bean in the Spring `ApplicationContext`. Use the template when a service needs to retrieve secrets by name at runtime or perform authorized secret management operations.

Configuration example:

~~~yaml
spring:
  cloud:
    oci:
      config:
        type: INSTANCE_PRINCIPAL
      region:
        static: ${OCI_REGION}
      vault:
        enabled: true
        compartment: ${OCI_COMPARTMENT_OCID}
        vault-id: ${OCI_VAULT_OCID}
~~~

Reading a secret example:

~~~java
@Service
public class SecretLookupService {

    private final VaultTemplate vaultTemplate;

    public SecretLookupService(VaultTemplate vaultTemplate) {
        this.vaultTemplate = vaultTemplate;
    }

    public String getSecretByName(String secretName) {
        GetSecretBundleByNameResponse bundle =
                vaultTemplate.getSecret(secretName);

        return vaultTemplate.decodeBundle(bundle);
    }
}
~~~

Class and method names in the example follow the API published in Spring Cloud OCI docs; verify imports/packages in the Javadocs for your exact release.

### 6.1. Why Is There `decodeBundle`?

A secret bundle can contain Base64-encoded content according to the secret content format. `VaultTemplate` provides `decodeBundle` to obtain the decoded content in the starter's integrated manner.

Do not manually grab a response field assuming it is plaintext. Do not Base64-decode twice. Use the starter's API and verify the format of the created secret.

### 6.2. When Should You Use `VaultTemplate`?

Suitable when:

- Secret names are determined per tenant or workload.
- The application needs to fetch secrets per operation rather than loading everything at startup.
- Multiple credentials have different lifecycles.
- You need to actively read versions or control refresh timing per supported APIs.
- An integration adapter needs to hide OCI Vault details from business services.

Avoid calling Vault on every HTTP request when credentials can be safely cached with a bounded TTL. Every Vault call adds latency, network dependency, and API request volume.

### 6.3. Keeping `VaultTemplate` Inside an Adapter

Do not let domain services depend directly on OCI SDK responses. Define an internal interface:

~~~java
public interface SecretProvider {
    String getRequiredSecret(String name);
}
~~~

An adapter implements the interface and delegates to `VaultTemplate`:

~~~java
@Component
public class OciVaultSecretProvider implements SecretProvider {

    private final VaultTemplate vaultTemplate;

    public OciVaultSecretProvider(VaultTemplate vaultTemplate) {
        this.vaultTemplate = vaultTemplate;
    }

    @Override
    public String getRequiredSecret(String name) {
        GetSecretBundleByNameResponse bundle =
                vaultTemplate.getSecret(name);

        return vaultTemplate.decodeBundle(bundle);
    }
}
~~~

Business services only know `SecretProvider`. Unit tests can mock that interface without calling OCI.

## 7. `VaultTemplate` and Secret Administration Permissions

`VaultTemplate` supports operations on secrets such as create, update, list, and delete depending on module capabilities. However, a runtime application that only needs to read a password should never be granted permission to administer all secrets.

Separate responsibilities:

| Workload | Permissions to Consider |
| --- | --- |
| Business API runtime | Read required secret bundles |
| Rotation job | Create new versions/promote/rotate per procedure |
| Platform provisioning | Create Vaults, keys, secrets, and policies |
| Auditor | Read metadata/audit per granted permissions; avoid reading secret content unless necessary |

If using `VaultTemplate` solely for reads, grant `read secret-bundles` to the workload. If an application also creates or updates secrets, grant specific permissions for those operations and consider separating them into an administrative service/job.

Never grant `delete` or `manage secrets` to every application replica simply because the template exposes administrative APIs.

## 8. OCI IAM Policies for Secret-Reading Workloads

OCI Secret Management integrates with IAM. A dynamic group or user group needs a policy allowing it to read secret bundles.

Example Instance Principal permitted to read only one secret:

~~~text
Allow dynamic-group InvoiceComputeInstances to read secret-bundles in compartment InvoiceSecrets where target.secret.id = 'SECRET_OCID'
~~~

If the workload needs to read multiple secrets in a compartment:

~~~text
Allow dynamic-group InvoiceComputeInstances to read secret-bundles in compartment InvoiceSecrets
~~~

Example Resource Principal for a Function:

~~~text
Allow dynamic-group InvoiceFunctions to read secret-bundles in compartment InvoiceSecrets where target.secret.id = 'SECRET_OCID'
~~~

These statements illustrate scope. Replace dynamic group names, compartments, and OCIDs with real values; verify policy grammar and your tenancy's identity domain. Restrict by `target.secret.id` when the workload only needs a single secret.

### Reading Secrets Differs from Using Encryption Keys

Reading secret bundles and managing encryption keys are distinct permissions/resource types. Applications generally do not need permission to create, rotate, or delete keys just to retrieve secrets. Configure Vault/key access per OCI Secret Management guidelines and the policy reference; do not grant extra key management permissions by guesswork.

### Secret Compartment vs. Vault Compartment

Secrets and Vaults can be moved or managed in separate compartments. Policies must match the compartment holding the secret and the actual resource scope. Moving a secret to a different compartment can cause old policies to stop applying. Do not assume permission to read secrets solely because a principal has permissions on the Vault resource.

## 9. Secret Versions and Rotation States

Every secret has at least one version. When content changes, OCI creates a new version. Version numbers increment monotonically; a version can be identified by number, name, or rotation state.

Common rotation states:

| State | Meaning |
| --- | --- |
| `CURRENT` | The version actively used to access the target system |
| `PENDING` | A version created but not yet put into active use |
| `PREVIOUS` | The prior version |
| `DEPRECATED` | A version no longer used as the current credential |
| `LATEST` | The newest version by version criteria, which may not yet be `CURRENT` |

Applications normally need `CURRENT`. Do not confuse `LATEST` with `CURRENT`: the newest version may still be `PENDING` and not yet accepted by the target system.

### 9.1. Creating a New Version

When updating secret content, OCI creates a new secret version. You can create the version in `PENDING` state to test before putting it into active service.

Illustrative workflow:

1. Create a new credential on the target system or trigger the target's rotation workflow.
2. Create a new secret version in Vault.
3. Place the new version in `PENDING` if staging is needed.
4. Verify the application or a test job can authenticate with the new credential.
5. Synchronize the target system and secret version per the rotation procedure.
6. Promote the ready version to `CURRENT`.
7. Refresh/recreate clients or connection pools.
8. Monitor for authentication failures.
9. Retire the old credential only once no consumers still use it.

Exact ordering depends on the target system and auto-rotation mechanism. Never promote a new password before the target database/API actually accepts that password.

### 9.2. Rollback

If a new version does not work:

- Check whether the target system still accepts the previous credential.
- Promote the appropriate version back to `CURRENT` if the procedure allows it.
- Refresh/recreate clients holding the old/new credentials.
- Monitor connection failures and audits.
- Never delete the old version immediately after rotating.

Rollback succeeds only if the target system still accepts the corresponding credential. Changing `CURRENT` in Vault does not automatically change the password on the target database or service.

### 9.3. Scheduled Deletion

OCI supports scheduling deletion for a secret or secret version. A secret pending deletion can disrupt workloads depending on it; a secret version scheduled for deletion is also no longer eligible for normal rotation/updates. Final deletion is irreversible once the waiting period expires.

Never schedule deletion for a secret currently used by an application. Before deleting, verify no workloads, deployments, replicas, or rollback procedures still depend on that secret.

## 10. Designing Rotation for Spring Boot Applications

Rotation is more than swapping a string in Vault. The application may already have initialized a `DataSource`, HTTP client, or SDK client with the old credential.

### Credentials Loaded at Startup

For example, a `DataSource` receives its password when the bean is created. When the property source refreshes, an existing `DataSource` does not necessarily reopen its pool with the new password automatically.

Design one of these approaches:

- Controlled refresh/recreation of the `DataSource` or connection pool.
- Using a pool that supports verified credential updates.
- Creating credential overlap so both old and new credentials remain valid during the transition window.
- Rolling restart after the `CURRENT` secret changes.
- Using a dynamic credential provider if supported by the target service and integration.

Never change the database password and expect every open connection to pick up the new password automatically.

### Credentials Fetched on Demand

With `VaultTemplate`, an adapter can read secrets when needed. Still, calling Vault on every operation has cost. You can cache values in memory with an appropriate TTL, provided you have:

- A TTL shorter than the system's acceptable rotation/revocation window.
- An invalidation mechanism upon rotation.
- Bounded retries when Vault is unavailable.
- No caching to disk or unprotected distributed caches.
- No logging of secret values on cache misses or decode errors.

### Multi-Replica Rotation

When running multiple instances:

1. Ensure the target system accepts the new credential.
2. Promote the new version to `CURRENT`.
3. Wait for property source refresh or actively trigger refresh on each instance.
4. Recreate/reconnect clients per application design.
5. Verify all replicas are using the new credential.
6. Only then revoke the old credential.

Never revoke the old credential immediately after promoting `CURRENT` while replicas still hold cached values or old connection pools.

## 11. Property Source, `VaultTemplate`, or Secret Mount?

All three approaches can coexist, each with different trade-offs.

| Approach | Pros | Cons |
| --- | --- | --- |
| Vault property source | Integrates directly into Spring `Environment`; simple config | Secrets are loaded into `Environment`; already-injected beans may need explicit refresh |
| `VaultTemplate` | On-demand retrieval; adapter actively controls cache/versions | Requires code for error handling, caching, and lifecycle |
| Secret mount/env injection | Application does not call Vault API directly | Rotation and file/env refresh depend on platform/sidecar/deployment |

Choose one primary read path per credential type. Avoid mixing property source, `VaultTemplate`, and secret mounts for the same secret with three competing precedence rules.

For applications using Spring Cloud OCI, property source and `VaultTemplate` are built into the Vault starter. Secret mounts are a deployment/runtime choice and can be coordinated when required.

## 12. Spring Configuration Precedence

Spring `Environment` has multiple `PropertySource` layers: command-line arguments, system properties, environment variables, application config, profile config, and integration-added property sources.

When the same key appears in multiple sources, the higher-precedence source wins. Explicitly define whether secrets may be overridden by environment variables or test profiles.

Principles:

- Do not allow production secrets to be accidentally overridden by default config.
- Do not allow test profiles to accidentally use production credentials.
- Never print `Environment` or configuration properties containing secrets to logs.
- Never expose Actuator `/env` or `/configprops` endpoints publicly.
- Test precedence using integration tests with dummy secrets.
- Avoid declaring the same secret name in multiple Vaults unless precedence order is explicitly verified.

In production, maintain one authoritative source per secret. Manual overrides should be audited and restricted.

## 13. Protecting Secrets Inside the Application

Once a secret enters the JVM, the application must protect it as sensitive data.

Do not:

- Commit secrets to Git.
- Put secrets in Docker build `ARG`s or image layers.
- Print secrets in logs, exceptions, or traces.
- Record secrets in metric labels.
- Return secrets in REST responses or error details.
- Write secrets to unprotected temporary files.
- Capture secrets in uncontrolled heap dumps or support bundles.
- Send secrets via unapproved tickets/chat channels.

Do:

- Use workload identity and least privilege.
- Keep secrets in memory for as short a time as possible when feasible.
- Mask values in logs and test reports.
- Use TLS and control network paths.
- Restrict secret read access per service identity.
- Rotate credentials and revoke old ones on schedule.
- Audit who reads, modifies, and promotes versions.
- Separate runtime permissions from administrative permissions.

### Secrets in Exceptions

Never include secret values in exception messages. When logging errors, only log properly classified secret aliases/OCIDs, operations, status codes, and request IDs. Secret names/OCIDs themselves may also be sensitive metadata under organizational policy.

## 14. Error Handling and Availability

Vault is an external dependency. The application must define behavior when secrets cannot be retrieved.

| Error | Recommended Behavior |
| --- | --- |
| `401 NotAuthenticated` | Check identity provider, token/signature, and clock |
| `403 NotAuthorized` | Check `read secret-bundles` policy and compartment/secret scope |
| `404 NotFound` | Check `vault-id`, secret name, region, and secret lifecycle |
| `429`/throttling | Backoff with jitter, cap retries, and reduce refresh frequency |
| `5xx`/service unavailable | Bounded retry; use valid cached value if policy permits |
| Timeout/network error | Short timeout, explicit retry budget, circuit breaker if appropriate |
| Decode/content format error | Check secret type template and do not double-decode |
| Secret expired/target credential revoked | Rotate/recover per target system; do not retry indefinitely |

### Fail Fast or Use Cache?

For credentials required at application startup, fail fast if a valid secret cannot be fetched. This prevents the service from booting with missing config or unsafe default credentials.

For credentials used only by optional tasks, you may keep a valid cached value for a short grace period if policy permits. Never keep using a cache indefinitely after a secret has been revoked.

Never fall back to a hard-coded default password when Vault is unavailable. If a secret cannot be retrieved, fail safely and trigger appropriate alerts.

### Retries and Circuit Breakers

- Retry only transient errors.
- Do not retry 401/403/404 or format errors indefinitely.
- Use backoff with jitter.
- Cap total wait duration.
- Prevent request storms when multiple replicas refresh simultaneously.
- Add jitter across refresh schedules.
- Track refresh failures and secret cache age.

## 15. Testing OCI Vault Integration

### Unit Tests

Mock the `SecretProvider`/`VaultTemplate` boundary to verify:

- Service behavior when secrets are present/missing.
- Cache TTL and invalidation.
- Mapping OCI errors to internal errors.
- Secrets never appearing in logs.
- Retries occurring only on transient errors.

### Context Tests

Verify the Vault starter creates expected beans and property sources in test config. Use dummy secrets or a test profile; never use production secrets.

### Integration Tests with an OCI Test Compartment

1. Create a test Vault and encryption key.
2. Create a secret containing a dummy value.
3. Grant `read secret-bundles` policy to the test identity.
4. Configure the Spring Cloud OCI Vault starter.
5. Verify the property source resolves the secret.
6. Verify `VaultTemplate` reads and decodes the secret.
7. Update the secret version.
8. Verify refresh behavior.
9. Run negative policy tests.
10. Clean up test resources according to procedure.

### Rotation Tests

- Create a new version in `PENDING`.
- Verify the application still reads the old `CURRENT` version.
- Promote the new version to `CURRENT`.
- Wait for refresh or trigger refresh per design.
- Verify real beans/clients use the new credential.
- Verify old replicas do not continue using the revoked credential.
- Test rollback if the target still accepts the prior credential.

Do not only test that `Environment` returns the new string. Verify that `DataSource`/HTTP clients actually reconnect with the new credential.

## 16. Observability for Vault

Monitor signals that never expose secret values:

| Metric/Log | Meaning |
| --- | --- |
| `vault_secret_read_total` | Secret read count |
| `vault_secret_read_failure_total` | Failed secret read count |
| `vault_secret_read_duration` | Secret retrieval latency |
| `vault_property_refresh_total` | Property source refresh count |
| `vault_property_refresh_failure_total` | Failed property source refresh count |
| `vault_secret_cache_age` | Age of cached secret value |
| `vault_secret_version` | Version metadata if permitted to record |
| `vault_auth_failure_total` | Authentication errors |
| `vault_authorization_failure_total` | Policy authorization errors |
| `vault_throttling_total` | Throttling event count |

Logs should include:

- Operation and timestamp.
- Service/region.
- Secret alias approved for logging.
- HTTP status/error code.
- OCI request ID.
- Correlation ID.
- Refresh success/failure and appropriate version metadata.

Never log secret contents, encoded contents, `Authorization` headers, tokens, or full secret bundle responses.

## 17. Lab Exercise: Moving the Database Password into OCI Vault

**Context:** Invoice Service runs on OCI Compute. The application connects to Oracle Database and needs its password from OCI Vault. Local developers use a `FILE` profile; production uses Instance Principal. When the password rotates, the application must switch to the new version without prolonged downtime.

### Part A — Creating the Secret

1. Create a Vault and encryption key inside a secured compartment.
2. Create a secret named `invoice-db-password`.
3. Store a dummy password for the test database.
4. Verify the secret has a `CURRENT` version.
5. Record the Vault OCID and Secret OCID in protected internal config docs.

### Part B — Configuring Spring Cloud OCI

1. Add `spring-cloud-oci-starter-vault` at a compatible version.
2. Configure region, compartment, and Vault OCID.
3. Use `FILE` for local development.
4. Use `INSTANCE_PRINCIPAL` for Compute.
5. Grant a `read secret-bundles` policy scoped strictly to the secret OCID.
6. Verify the application context starts cleanly.

### Part C — Loading the Secret

1. Configure `property-sources` pointing to the Vault.
2. Resolve `invoice-db-password` in the Spring `Environment`.
3. Alternatively, use `VaultTemplate` via a `SecretProvider` adapter.
4. Never print secret values to logs.
5. Verify `DataSource` connects using the test credential.

### Part D — Rotation

1. Create a new credential on the test database.
2. Create a new secret version in `PENDING`.
3. Verify the new credential using a test connection.
4. Promote the new version to `CURRENT`.
5. Refresh/recreate `DataSource` per design.
6. Verify all replicas connect successfully.
7. Revoke the old password once no consumers remain.

### Part E — Failure Testing

1. Temporarily remove the secret read policy and verify 403 is logged safely.
2. Supply a wrong secret name and verify `NotFound` handling.
3. Simulate timeout/throttling and verify the retry budget.
4. Disable the Vault endpoint in test and verify cache/fail-fast policy.
5. Confirm no secret values appear in logs or test reports.

### Deliverables

- Diagram of Vault, key, secret, and secret versions.
- Maven/Gradle dependency for the Vault starter.
- Property source and `VaultTemplate` configuration.
- Least-privilege `read secret-bundles` IAM policy scoped to the secret.
- Unit and integration tests.
- Evidence of `CURRENT`/`PENDING` rotation.
- Evidence of `DataSource` reconnecting with the new credential.
- Dashboard for refresh failures/secret cache age.
- Runbook for rotating, rolling back, and revoking credentials.

## 18. Self-Check Questions

1. How do Vault, encryption keys, secrets, and secret bundles differ?
2. Why doesn't an application reading secret bundles need Vault admin permissions?
3. What are the two main integration modes of the Spring Cloud OCI Vault starter?
4. How does a property source expose secrets into the Spring `Environment`?
5. What does `property-refresh-interval` do, and what is its default?
6. Why doesn't refreshing `Environment` automatically update values already injected into singleton beans?
7. What roles do `VaultTemplate.getSecret` and `decodeBundle` play?
8. Why shouldn't you call Vault on every HTTP request?
9. How do `CURRENT`, `PENDING`, `PREVIOUS`, and `LATEST` secret versions differ?
10. Why might `LATEST` not yet be `CURRENT`?
11. When should you create a `PENDING` version?
12. Why must rotation be coordinated with the target database/API?
13. How does a `read secret-bundles` policy differ from `manage secrets`?
14. How do you restrict reading a single secret using `target.secret.id`?
15. What should you check when Vault returns 403?
16. When Vault is unavailable, when should you fail fast vs. use a cache?
17. How do you prove `DataSource` switched to the new credential after rotation?

## 19. Key Takeaways

- OCI Vault stores and manages secrets; secrets are protected by encryption keys per service configuration.
- The Spring Cloud OCI Vault starter provides property sources and `VaultTemplate`.
- Property sources fit config loaded into Spring `Environment`; `VaultTemplate` fits on-demand retrieval.
- Secret bundles contain content plus metadata/version; use `decodeBundle` per the starter API.
- `property-refresh-interval` defaults to 10 minutes; refreshing the property source does not automatically update all singleton beans/clients.
- `CURRENT` is the active version; `LATEST` may be `PENDING` and not yet accepted by the target system.
- Rotation must coordinate Vault, target credentials, caches, connection pools, and replicas.
- Runtime identities normally only need `read secret-bundles`; separate them from create, update, rotate, or delete permissions.
- Restrict IAM policies by compartment and `target.secret.id` wherever possible.
- Never log, commit, or bake secrets into images; protect plaintext in memory and diagnostic artifacts.
- When Vault fails, apply bounded retries and policy-governed caching; never fall back to default passwords.
- Test rotation against real `DataSource`/clients, not just Spring `Environment`.

## References

- [Spring Cloud OCI Vault integration](https://oracle.github.io/spring-cloud-oracle/site/docs/oci/vault/)
- [Spring Cloud Oracle latest reference — OCI Vault](https://oracle.github.io/spring-cloud-oracle/latest/reference/html/index.html)
- [OCI Secret Management Service overview](https://docs.oracle.com/en-us/iaas/Content/secret-management/overview.htm)
- [OCI Secret Versions and rotation states](https://docs.oracle.com/en-us/iaas/Content/secret-management/Concepts/secret-versions.htm)
- [OCI Creating a Secret Version](https://docs.oracle.com/en-us/iaas/Content/secret-management/Tasks/create-secret-version.htm)
- [OCI Promoting a Pending Secret Version](https://docs.oracle.com/en-us/iaas/Content/secret-management/Tasks/promote-secret-version.htm)
- [OCI Getting Secret Bundle Contents](https://docs.oracle.com/en-us/iaas/Content/secret-management/Tasks/get-secrets-contents.htm)
- [OCI Vault IAM policy reference](https://docs.oracle.com/en-us/iaas/Content/Identity/Reference/keypolicyreference.htm)
- [OCI Secret Management and IAM policy example](https://docs.oracle.com/en-us/iaas/autonomous-database-serverless/doc/vault-secret-credentials-oci.html)
- [OCI Scheduling deletion of a secret](https://docs.oracle.com/en-us/iaas/Content/secret-management/Tasks/delete-secret.htm)
