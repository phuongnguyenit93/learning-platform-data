# Passing Configuration at Deployment or Runtime

An application is often deployed across multiple environments such as development, test, staging, and production. Source code and artifacts may be identical, yet service addresses, connection details, resource limits, operating modes, and credentials differ. Hardcoding these values into source code or creating a separate build per environment makes it difficult for the team to guarantee that what was tested is what gets deployed to production.

The right approach is to separate configuration from artifacts and supply configuration at deployment time or application startup. An artifact is built from a pinned commit and then promoted across environments. Each environment provides its corresponding configuration set via environment variables, mounted configuration files, configuration management systems, or secret managers. The application reads, validates, and uses configuration throughout its execution lifecycle.

This lesson explains how to externalize configuration, choose configuration delivery channels, define precedence order, manage secrets, validate configuration before serving requests, handle runtime changes, and trace configuration tied to each deployment. The goal is to keep artifacts consistent, reduce configuration errors, and ensure each environment receives only the values it is authorized to use.

## 1. Why Must Configuration Be Supplied at Deployment or Runtime?

Configuration consists of values that determine how an application operates in a specific environment. For example:

- Addresses of APIs or dependent services.
- Host, port, database name, and connection pool settings.
- Timeouts, retry counts, and concurrency limits.
- File storage paths or storage buckets.
- Logging mode, log level, and telemetry endpoints.
- Feature flags and behavioral options.
- Domain names, callback URLs, and integration settings.
- Required authentication details or access keys.

Some values are non-sensitive yet still vary by environment. Others are secrets and require dedicated protection mechanisms. Neither group should be hardcoded into the artifact if the goal is to reuse the same build output across multiple environments.

Three common problems arise when configuration is tightly coupled to the build process:

1. **Per-environment builds:** staging and production may receive different binaries despite the same source change. This reduces confidence in pre-release testing.
2. **Exposure of sensitive configuration:** passwords, tokens, or private keys can enter Git, image layers, build logs, or artifacts.
3. **Difficult changes and traceability:** changing a service address or timeout may force a rebuild; it also becomes hard to know which exact values were used in a given deployment.

Externalized configuration solves these issues by supplying environment values at deploy time or runtime. The same artifact can be used across multiple environments while each environment receives its own separately managed configuration set.

~~~mermaid
flowchart TD
    A["Source code commit"] --> B["CI builds one artifact"]
    B --> C["Store immutable artifact"]
    C --> D["Deploy same artifact to test"]
    E["Test configuration"] --> D
    D --> F["Verify application"]
    F --> G["Promote same artifact to staging"]
    H["Staging configuration"] --> G
    G --> I["Release approval"]
    I --> J["Deploy same artifact to production"]
    K["Production configuration"] --> J
    J --> L["Verify version and effective configuration"]
~~~

The core insight is that artifacts and configuration have separate lifecycles, yet must be linked in release records. The artifact defines which software runs; configuration defines how that software behaves in the target environment.

## 2. Distinguishing Build-Time and Runtime Configuration

Not every parameter can be changed after the build. You must distinguish configuration used to construct the artifact from configuration read by the application at runtime.

| Type | When applied | Examples | Changeable without rebuilding? |
|---|---|---|---|
| Build-time input | During the build | Compiler version, dependencies, target architecture, build profile | Usually no; changes can produce a different artifact |
| Runtime configuration | At deploy or application startup | Service URLs, database endpoints, timeouts, log level | Yes, if the application supports reading new values |
| Runtime secret | At deploy or when needed | Passwords, tokens, certificates, private keys | Rotatable without rebuilding, depending on how the app loads them |
| Dynamic configuration | While the application is running | Feature flags, business limits, rollout percentages | Yes, if the application supports safe updates |

Build-time inputs can directly affect binary contents. For instance, changing library versions or target platforms typically requires rebuilding. Runtime configuration alters how the artifact behaves without altering artifact contents.

Do not use build profiles to bake production URLs, passwords, or environment endpoints into binaries if the same artifact must traverse multiple environments. A profile can be useful for selecting build features or package types, but it should not become a mechanism for duplicating artifacts solely to swap operational values.

Some static frontends need to know the API base URL at build time if the application embeds values into the bundle. In that case, consider serving a runtime configuration file loaded when the app boots or via a configuration endpoint to avoid rebuilding the entire frontend per environment. If the architecture strictly requires build-time configuration, explicitly treat it as a separate artifact variant and verify each variant.

## 3. Choosing Configuration Delivery Sources

Configuration can be delivered through multiple mechanisms. No single mechanism fits every application. Choose based on data type, platform capabilities, security requirements, and operational practices.

| Mechanism | How it works | Suitable for |
|---|---|---|
| Environment variables | Deployment platform sets variables before launching the process | Simple values, per-process configuration |
| Mounted configuration file | Mounts a file into the container or host | Structured config, multi-field configs, or certificates |
| ConfigMap / platform configuration store | Platform manages configuration per workload or environment | Non-secret configuration tied to a deployment |
| Secret manager | Provisions secrets via API, agent, sidecar, or file mount | Passwords, tokens, keys, and certificates |
| Configuration service | Application queries config service at startup or runtime | Multi-service systems needing centralized or dynamic config |
| Deployment manifest / release values | Pipeline passes parameters to the platform during deployment | Configuration tied to a release or environment |

### 3.1. Environment variables

Environment variables are a common way to pass configuration to a process. The platform or startup script sets values before running the application. The application reads variables by agreed names and converts them into required data types.

Example:

~~~bash
APP_ENV=staging
HTTP_PORT=8080
PAYMENT_API_URL=https://payments.staging.example
DB_POOL_MAX=20
LOG_LEVEL=INFO
~~~

This example illustrates non-sensitive values only. Never put real passwords or tokens into committed `.env` files or commands that could be captured in shell history or logs. Secrets should be provisioned from a secret manager or the platform's security mechanism.

Advantages of environment variables include simplicity, broad runtime support, and no dependency on a specific configuration system. Limitations include usually being read only at process startup, difficulty representing complex structures, and potential exposure if an application dumps its entire environment to logs or diagnostic pages.

Define clear naming conventions with application prefixes, explicit data types, and valid value constraints. For example, `DB_POOL_MAX` must parse as a positive integer, while `APP_ENV` only accepts one of the supported environment names.

### 3.2. Mounted configuration files

Configuration files suit cases with many value groups, nested structures, or formats natively supported by the application such as YAML, JSON, TOML, or properties.

Example of a configuration file containing no secrets:

~~~yaml
server:
  port: 8080

database:
  host: db.staging.internal
  name: orders
  pool:
    maxSize: 20
    connectionTimeout: 5s

payment:
  baseUrl: https://payments.staging.example

logging:
  level: INFO
~~~

The deployment platform can mount the file into a container or host machine. The application reads the file from an agreed path, such as `/etc/orders/application.yml`.

You must control file read permissions, ownership, write permissions, and mount lifecycles. Configuration files can contain sensitive data if not separated; therefore, keep secrets in a separate source or mount them via a protected secret mechanism.

### 3.3. Config stores and ConfigMaps

An orchestration platform can provide dedicated configuration objects, such as ConfigMaps or equivalent mechanisms. This allows teams to update configuration without repackaging the application.

Note that ConfigMaps are typically intended for non-secret data. Storing passwords or tokens inside a regular configuration object does not turn it into a secret. Use a secret manager or a platform-protected secret mechanism with proper access controls and encryption.

### 3.4. Configuration service

A centralized configuration service can serve configuration by application, environment, tenant, or version. This mechanism is useful when multiple services share rules or when certain values must update at runtime.

However, the application takes on an additional dependency on the configuration service. Define behavior when the service is unavailable, authentication methods, local caching, configuration versioning, and rollback capability. Never let an application start without valid configuration simply because the config service is failing, unless an explicitly designed safe fallback policy exists.

## 4. Defining Precedence Order When Loading Configuration

An application may receive the same property from multiple sources: default values, configuration files, environment variables, command-line arguments, or a configuration service. Without a defined precedence order, results may differ across local, CI, and production.

A commonly used order, from lowest to highest precedence, is:

1. Safe default values embedded in the application.
2. Default configuration file packaged with the artifact.
3. Mounted environment-specific configuration file.
4. Values from a config store or configuration service per policy.
5. Environment variables supplied to the process.
6. Command-line arguments or explicit per-run overrides, if permitted.

This is only a reference model. Frameworks or platforms may use a different order. Teams must document the actual precedence so one source never unexpectedly overrides another.

For example, an application defaults to `HTTP_PORT=8080`, while the deployment sets `HTTP_PORT=9090`. If environment variables take precedence over config files, the application must listen on port 9090. Startup logs may record the selected source and property name, but must never print secrets or full sensitive values.

### 4.1. Avoiding too many override sources

The more override sources exist, the harder troubleshooting becomes. Limit the number of configuration sources and assign clear ownership per group:

- Default values: application development team.
- Environment configuration: operations or platform team.
- Secrets: secret manager or corresponding security system owners.
- Release overrides: pipeline or authorized approvers.

Avoid placing a critical value simultaneously in files, environment variables, command-line arguments, and config services without clear rules. Whenever an override exists, it must be clear where the effective value comes from.

### 4.2. Avoiding dangerous fallbacks

Fallbacks are helpful for non-sensitive values, but introduce risks when applied to required configuration. For example, if a database password is missing, the application must never fall back to a default password. If the production payment endpoint is missing, it must never silently call a development endpoint.

For critical configuration, the right behavior is typically fail fast: refuse to start or refuse to accept traffic while clearly reporting which property is missing without leaking secret values.

## 5. Managing Environment-Specific Configuration

Each environment needs a purposefully defined configuration set. Never arbitrarily copy production configuration down to test or let development share credentials with staging.

| Configuration group | Development | Test / QA | Staging | Production |
|---|---|---|---|---|
| Service endpoints | Local or mock | Test services | Staging services | Production services |
| Database | Local data | Testing database | Staging database | Production database |
| Secrets | Dedicated local credentials | Test secrets | Staging secrets | Production secrets |
| Logging | Controlled DEBUG | INFO/DEBUG as needed | INFO | INFO/WARN per policy |
| Timeouts and pools | Small for development | Close to target config | Production-like | Tuned to load and SLOs |
| Feature flags | Can toggle experimentally | Per test scenario | Per release plan | Per approved rollout |
| Telemetry | Local collector or disabled | Test collector | Staging collector | Production monitoring system |

Environments should align closely in configuration structure and provisioning mechanics, though they do not need the same data or permissions. Staging should reflect critical production characteristics for pre-release testing while using safe data and credentials.

### 5.1. Using the same artifact across multiple environments

A reliable release workflow typically:

1. Builds an artifact from a pinned commit.
2. Tests the artifact in the test environment.
3. Promotes that exact artifact to staging.
4. Approves and promotes the same artifact to production.
5. Records the artifact digest and release configuration used.

If you have to rebuild merely to swap a URL or timeout, the team can accidentally produce a binary different from the tested one. Supply those values from deployment configuration or runtime configuration instead.

### 5.2. Never use development environments as a source for production config

Production configuration must be managed where appropriate access controls exist. Never pull values directly from a developer's local file, personal machine environment variables, or shared secrets. Production values must come from an official, audited, and owned source.

## 6. Passing Secrets at Deployment or Runtime

Secrets are authentication or cryptographic data that can grant access, such as passwords, tokens, private keys, certificates, or connection strings containing credentials.

Secrets must never be:

- Committed to Git.
- Packaged into JARs, WARs, container images, or frontend bundles.
- Stored in build artifacts.
- Written to logs, exception messages, or health/debug pages.
- Placed in command-line arguments that could be recorded.
- Stored in shared caches or workspaces without protection mechanisms.

A reference secret-provisioning flow:

~~~mermaid
sequenceDiagram
    participant P as Pipeline / deployment platform
    participant I as Identity provider
    participant S as Secret manager
    participant A as Application
    P->>I: Request workload identity
    I-->>P: Scoped short-lived token
    P->>S: Read authorized secret
    S-->>P: Secret or secret reference
    P->>A: Provision secret via file mount or secure mechanism
    A->>A: Initialize client and authenticate
    Note over P,A: Never write secret values to logs or artifacts
~~~

Implementations may vary: the platform may mount secrets as files, inject environment variables, issue tokens for the app to query a secret manager directly, or use a sidecar/agent. Choose mechanisms that minimize exposure via process listings, environment dumps, logs, or filesystems.

### 6.1. Separating permissions by environment

Separate secrets across development, test, staging, and production. A test job needs no read access to production secrets. A staging deploy job needs no production deploy permissions.

Prefer short-lived credentials or workload identity when supported by the platform. Trust policies must restrict which repository, branch, environment, workflow, or workload identity may obtain credentials. Never grant broad permissions simply because the pipeline requires automation.

### 6.2. Rotating secrets

Secrets may need rotation on a schedule, when personnel permissions change, or upon suspected exposure. Applications must be able to receive new credentials without rebuilding artifacts.

Depending on how secrets are loaded, you can:

- Provision new credentials and redeploy the workload.
- Mount the new secret version and restart the process.
- Use clients supporting refresh tokens or certificates.
- Use a secret manager with short-lived leases and automatic renewal.

Do not delete old credentials before verifying the application has switched to the new ones, unless emergency revocation is required. For scheduled rotation, use an overlap window accepting both old and new credentials to avoid downtime.

## 7. Validating Configuration Before Serving Traffic

Misconfiguration can prevent an application from starting, connect it to the wrong environment, or cause insecure operation. Therefore, validate configuration immediately at startup and before accepting traffic.

Check that:

- Required properties exist.
- Values match expected data types.
- URLs have valid schemes and hosts.
- Ports fall within permitted ranges.
- Timeouts, pool sizes, and retry limits have sensible values.
- Environment names and endpoints are compatible.
- Feature flags do not form invalid state combinations.
- Secrets can be read and used without being printed.
- Configuration does not accidentally point production to test services or vice versa.

Conceptual schema example:

~~~yaml
application:
  environment:
    required: true
    allowed:
      - development
      - test
      - staging
      - production

  http:
    port:
      type: integer
      min: 1
      max: 65535

  database:
    url:
      required: true
    poolMax:
      type: integer
      min: 1
      max: 100

  payment:
    baseUrl:
      required: true
    connectTimeout:
      type: duration
      min: 100ms
      max: 30s
~~~

This is an illustrative schema description, not a mandatory configuration format. Applications can use framework validation, JSON Schema, configuration libraries, or custom validation logic.

### 7.1. Fail fast on required configuration

If required configuration is missing or invalid, the application should halt startup with an error clearly identifying the property name and reason, such as `PAYMENT_API_URL is required`. Never include secret values or full connection strings in error messages.

Failing fast prevents an application from running in a half-working state only to fail when users send requests. The deployment platform must distinguish between a running container/process and an application ready to serve traffic.

### 7.2. Cross-value compatibility checks

Individual values may be valid while their combination is broken. For example:

- `APP_ENV=production` while the database URL points to a test host.
- TLS disabled while the endpoint requires TLS.
- Excessive retries combined with long timeouts holding resources too long.
- A feature flag enabling functionality whose dependent endpoint is unconfigured.
- Pool size exceeding the database's maximum connection limit.

Add cross-field validation for high-risk combinations. For production endpoints or secrets, add environment-specific allowlists or validation rules.

## 8. Static Configuration and Runtime-Mutable Configuration

Not all configuration changes share the same lifecycle.

- **Startup configuration:** read when the process starts, such as port, database pool, or TLS keys.
- **Reloadable configuration:** reloadable by the application without restarting, such as log levels or certain timeouts.
- **Dynamic configuration:** updated at runtime via a config service or feature flags.
- **Deployment configuration:** applied by the platform when creating or updating workloads.

Classify which properties belong to which group. If an application reads environment variables only at startup, updating an environment variable on the deployment will not automatically update running processes; a workload restart or rollout is needed.

### 8.1. Safe configuration reloading

If an application supports reloading, avoid mutating fields piecemeal in ways that leave processes in an inconsistent state. A safe approach is:

1. Load the entire new configuration version.
2. Parse and validate every field.
3. Verify cross-field constraints.
4. Only replace the active configuration if everything is valid.
5. Record the new configuration version and application result.
6. On failure, retain the previous version and emit an alert.

For properties affecting connections, thread pools, or resources, define how old resources are recreated and closed. Reloading a value is not as simple as reassigning a variable if dependent components were initialized earlier.

### 8.2. Feature flags do not replace infrastructure configuration

Feature flags typically control toggling product behaviors or feature rollouts. They should not replace management of endpoints, credentials, or access permissions. Distinguish feature flags, operational configuration, and secrets because they carry different security, audit, and lifecycle requirements.

## 9. Versioning Configuration and Avoiding Drift

Configuration also requires versioning. A deployment depends not only on the artifact but also on the applied configuration.

Metadata worth storing includes:

- Artifact version and digest.
- Commit SHA and pipeline run ID.
- Target environment.
- Config bundle version or revision.
- Secret version reference, without storing secret values.
- Application timestamp and executing actor or workflow.
- Validation and rollout results.

**Configuration drift** happens when actual configuration diverges from declared or approved configuration. For example, someone modifies a timeout directly in production while the repository config file keeps the old value. The next deployment may overwrite the change or yield unpredictable behavior.

To reduce drift:

- Manage non-secret configuration via version control or a config system with history.
- Restrict direct edits in running environments.
- Use deployment automation to apply reviewed configuration.
- Periodically compare desired state against actual state.
- Audit all changes and actors.
- Maintain a process to restore configuration to a known version.

Never put secrets into Git just to version them. Repositories can store secret names, references, schemas, and policies; actual secret values belong in a secret manager. Release records should reference secret versions or identifiers without copying values.

## 10. Configuration and Rollback Capability

Rolling back an application does not necessarily restore full system state if configuration changed independently. For example, a new version requires a new endpoint or schema; reverting to an older binary while keeping the new configuration may prevent startup or cause misbehavior.

When designing rollbacks, consider:

- Is the old artifact still retained and verifiable?
- Is the old configuration versioned and retained?
- Are rotated secrets still compatible with the old version?
- Is the database schema backward-compatible?
- Did feature flag changes affect persisted data?
- Were network configurations or IAM permissions changed alongside the release?
- Can both configuration and artifact be restored from a unified release record?

A release record should capture the deployed artifact and configuration combination. During rollback, the team must know whether both can be reverted or whether a forward fix is required. For secrets revoked due to a security incident, never reinstate old credentials just to make an old app version run; issue compatible new credentials instead.

### 10.1. Controlled configuration changes

Configuration can change without rebuilding, yet not every change is safe. Modifying timeouts, pool sizes, endpoints, permissions, or feature flags can directly alter system behavior and load.

For high-impact changes:

- Review and approve.
- Check schemas and policies.
- Apply via phased rollout or canary if appropriate.
- Monitor metrics and logs after the change.
- Retain the previous version for recovery.
- Record the timestamp, actor, and outcome.

## 11. Example Environment-Based Configuration Deployment

The following example shows a conceptual manifest, not complete syntax for Kubernetes or any specific platform:

~~~yaml
application:
  image: registry.example/orders@sha256:ARTIFACT_DIGEST

  environment:
    APP_ENV: production
    HTTP_PORT: "8080"
    PAYMENT_API_URL: https://payments.internal
    LOG_LEVEL: INFO
    DB_POOL_MAX: "30"

  secretReferences:
    DATABASE_PASSWORD: secret-manager://production/orders/database-password
    PAYMENT_API_TOKEN: secret-manager://production/orders/payment-token

  configuration:
    file: /etc/orders/runtime-config.yml
    revision: orders-production-config-v12
~~~

The manifest contains only non-secret values and secret references. The deployment platform or workload identity provisions actual secrets according to configured permissions. The artifact is identified by digest to prevent mutable tags from pointing to different contents.

A deployment sequence might follow:

1. Pipeline verifies the artifact and intended configuration.
2. Platform creates the workload with environment variables and config files.
3. Secret manager issues credentials based on workload identity.
4. Application starts, loads configuration, and validates it.
5. Readiness checks succeed only after required configuration is applied.
6. Pipeline verifies the running artifact digest and config revision.
7. After rollout, monitoring tracks health, connection errors, and key metrics.

## 12. Troubleshooting Common Configuration Errors

| Symptom | Possible cause | Investigation approach |
|---|---|---|
| Application fails to start | Missing required variable or wrong value type | Check property names, schema, and delivery source |
| Application connects to wrong environment | Wrong default or precedence override | Verify effective endpoint and configuration source |
| Works locally but fails in staging | Different secrets, DNS, permissions, or mounted config file | Compare config metadata, verify permissions and connectivity |
| Env var change has no effect | Process reads configuration only at startup | Check reload mechanism and perform a rollout if needed |
| New secret not picked up | Credential cache, unrefreshed mount, or un-reloaded process | Check secret version, mount timestamp, and client lifecycle |
| Logs accidentally contain secrets | Environment dump or exception printing connection string | Mask/redact logs, revoke exposed secret, and fix logging |
| Production drift after deploy | Direct manual edits outside automation | Compare desired vs. actual state and review audit logs |
| Application rollback still fails | New config incompatible with old binary | Restore compatible config revision or perform a forward fix |
| Config service unreachable | DNS, network, credential, or config service outage | Verify dependencies, retry policy, and designed fallback |
| Individual values valid but combination fails | Missing cross-field validation | Add compatibility checks before accepting traffic |

When investigating, determine the effective value, provisioning source, and configuration version before making changes. Never ask operators to paste secrets into tickets or logs to reproduce bugs. Use variable names, secret references, existence flags, and validation outcomes without exposing values.

## 13. Example Scenario: Promoting the Same Artifact Across Three Environments

Suppose a team develops an order management service and prepares to release a new version.

1. CI builds an artifact from the merged commit, runs tests, and stores the artifact with its digest.
2. Pipeline deploys the artifact to test. The platform provides the test database endpoint, payment sandbox URL, and test credentials.
3. The application loads configuration, validates the schema, and runs smoke and integration tests.
4. Once passing, the pipeline promotes the exact same digest to staging. Staging receives its own endpoints and secrets, plus production-like timeout and pool settings.
5. The team runs acceptance tests, verifies payment flows, and confirms the artifact/config revision.
6. Upon approval, the pipeline deploys the same digest to production. The secret manager supplies production credentials to the workload via scoped identity and permissions.
7. The application validates configuration before readiness succeeds. The pipeline records the artifact digest, config revision, and rollout result.
8. If misconfiguration is discovered post-deploy, the team can restore a compatible config revision or roll back both artifact and configuration per the release record.

Thus, differences across environments reside in managed configuration while the tested artifact remains untouched. Configuration changes can also be reviewed, approved, and traced independently of the build process.

## 14. Practice Roadmap

You can practice on a sample application using these steps:

1. **Inventory configuration:** classify values into build-time, runtime, secret, and dynamic configuration.
2. **Extract environment values from source:** move URLs, ports, timeouts, and log levels to runtime environment variables or config files.
3. **Separate secrets:** move passwords and tokens into a secret manager or platform secret store; pass only references in manifests.
4. **Define precedence:** document the exact order across defaults, files, config stores, environment, and command line.
5. **Add validation:** check required properties, types, ranges, and cross-field compatibility; test starting with invalid configuration.
6. **Reuse the same artifact:** deploy one digest across test, staging, and production with separate configuration sets.
7. **Test runtime changes:** modify one reloadable value and one startup-only value; verify the behavioral difference.
8. **Verify secret rotation:** issue a new credential version in a test environment and confirm the application transitions safely.
9. **Detect drift:** modify configuration outside automation in a test environment and verify the system detects the divergence.
10. **Rehearse rollback:** restore a known artifact/config revision pair and verify application operation.
11. **Audit traceability:** trace from a deployment back to artifact digest, commit, config revision, secret reference, and validation results.

### Completion criteria

Learners can consider the exercise complete when they can demonstrate:

- Explaining why configuration is separated from artifacts.
- Distinguishing build-time, runtime, secret, and dynamic configuration.
- Selecting appropriate configuration delivery mechanisms per data type.
- Determining precedence order and the source of effective values.
- Managing per-environment configuration without rebuilding the application.
- Provisioning least-privilege, rotatable secrets.
- Validating configuration before the application receives traffic.
- Handling reloads, restarts, and controlled configuration changes.
- Detecting configuration drift and tracing revisions.
- Restoring the right artifact/configuration combination during rollback.

## Conclusion

Passing configuration at deployment or runtime decouples the software lifecycle from environment lifecycles. An artifact built and tested once can be promoted across multiple environments; each environment supplies its own endpoints, operational limits, and secrets through managed mechanisms.

To make this practice reliable, teams must define configuration sources and precedence, validate values before serving traffic, protect secrets, version configuration, and detect drift. Release records must link artifact digests with applied configuration so teams can investigate, recover, and explain exactly how the application ran in its target environment.
