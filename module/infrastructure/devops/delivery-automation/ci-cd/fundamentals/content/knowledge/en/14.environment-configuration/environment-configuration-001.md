# Distinguishing Application Code, Configuration, and Secrets

An application may run in development, testing, staging, and production environments. Most business logic needs to remain identical across environments, while database addresses, log levels, connection limits, feature flags, and credentials may differ. Mixing these values into source code or packaging everything into a single artifact makes deployments difficult to control, hard to trace, and prone to exposing sensitive data.

When designing CI/CD, you need to clearly distinguish three groups:

- **Application code:** describes the behavior and logic of the software, managed under version control, reviewed, and built into an artifact.
- **Configuration:** values that control how the application behaves in a specific environment or run, such as endpoints, timeouts, log levels, and feature flags.
- **Secrets:** sensitive authentication data or keys that must be protected, such as passwords, access tokens, private keys, and connection credentials.

These three groups have different lifecycles, access permissions, and distribution mechanisms. Separating them allows a single tested artifact to be promoted across multiple environments, enables controlled configuration changes, and ensures secrets are provisioned only where needed.

## 1. Identifying the Three Data Groups

### Application code

Application code defines what the program does and how it processes requests. It includes source code, tests, schemas or resources managed as part of the product, build scripts, and definitions required to produce the artifact.

Examples:

- Billing rules, business validation, and order processing.
- API endpoints exposed by the application.
- How the application reads configuration and connects to services.
- Retry rules, error handling, and input validation.
- Test code, migrations, and build configurations related to the product.

Application code is typically stored in a repository and changed through commits and Pull Requests. A specific version of the source code is identified by a commit SHA and can be built into an artifact such as a JAR, binary, or container image.

### Configuration

Configuration provides values to control the behavior of the same application version across different contexts. Configuration can vary by environment, tenant, deployment region, or operational time.

Examples:

- URLs of databases, message brokers, or external APIs.
- Log levels, timeouts, retry limits, and connection pool sizes.
- Worker counts, request limits, or batch sizes.
- Feature flags, maintenance mode, and adjustable business limits.
- Bucket, queue, or namespace names.
- Paths to public certificates or secret manager endpoints.

Configuration is not necessarily a secret. An internal URL may be architecturally sensitive but is not a credential; a log level like INFO generally does not need protection like a password. However, configuration still needs to be managed, reviewed, and protected by change controls because incorrect values can bring down the application or introduce security risks.

### Secrets

A secret is data that, if known or used by an unauthorized party, can lead to unauthorized access, identity spoofing, data exfiltration, or system modification.

Examples:

- Database and service account passwords.
- API tokens, OAuth client secrets, and access tokens.
- Private keys used for signing artifacts, certificates, or authentication.
- Cloud, registry, and deployment system credentials.
- Encryption keys and recovery keys.
- Connection strings containing a username/password or token.

Not all sensitive data is a secret. Personal data, customer data, or internal business information may fall under data categories that require separate protection under data policies. Secret classification focuses on authentication, authorization, or decryption capabilities; data classification also needs to consider privacy and retention regulations.

### Quick comparison table

| Criterion | Application code | Configuration | Secret |
|---|---|---|---|
| Purpose | Defines software behavior | Adjusts behavior per environment or run | Authentication, authorization, or data protection |
| Examples | Billing logic, API handler | DB host, log level, timeout | DB password, API token, private key |
| Primary management location | Source repository | Config repository, config store, or platform config | Secret manager or protected secret store |
| Change review | Code review, tests, build | Review under configuration policy | Permission review and issuance/revocation process |
| Distribution | Checkout and artifact build | Inject or mount at deploy/runtime | Short-lived issuance or injection into the required workload |
| Lifecycle | Commit, release, version | Version, rollout, validate, rollback | Create, grant access, rotate, revoke, audit |
| Primary risk | Logic bugs, code vulnerabilities | Incorrect values, drift, incompatible configuration | Leakage or privilege abuse |
| Should it be baked into the application image? | Yes, after build | Only as environment-independent default configuration | No |

## 2. Why Separate Code, Config, and Secrets?

### Keep a single artifact usable across multiple environments

If database URLs, bucket names, and staging endpoints are hardcoded into source code, the team may have to build separate artifacts for each environment. This produces multiple different outputs from the same change, increases the risk of deploying to the wrong environment, and makes artifact verification harder.

When configuration is supplied at deployment time or application startup, the same artifact can be promoted across dev, staging, and production. Each environment receives its appropriate configuration set while running the exact same tested application contents.

### Avoid committing secrets into source history

A committed password can persist for a long time in Git history, forks, clones, caches, and backups. Deleting the password line in a new commit does not automatically remove the old credential from history.

If a secret is committed or appears in logs, it must be considered compromised: revoke or rotate the credential, audit access scope, and remediate history according to your organization's security process. Removing the file from the repository is only one part of incident response.

### Enable controlled operational changes

Some changes do not require altering application logic: increasing a timeout, switching an endpoint, lowering the log level, or temporarily disabling a feature. If these values are runtime configuration, the team can update them through a reviewed, validated, and audited workflow without creating a new build.

However, configuration can still affect behavior and compatibility. Not every config change is safe to apply directly; validation, controlled rollout, and the ability to roll back to previous values are required.

### Restrict access permissions

Developers may need to read source code and non-sensitive configuration, but do not necessarily need read access to production credentials. Operators may adjust certain production parameters without permission to modify code. Build jobs may need read access to dependencies without deployment permissions.

Separating data enables applying least privilege by role, environment, and purpose.

## 3. Default Configuration and Environment-Specific Configuration

Applications typically have a set of safe default values for running in a development environment. Default values should support startup and testing, but must not contain production-specific details.

Example default configuration:

~~~yaml
app:
  name: order-service
  request-timeout: 3s
  retry:
    max-attempts: 2

logging:
  level:
    root: INFO
~~~

These values can be managed alongside source code if they are common defaults and contain no secrets. Each environment provides overrides where needed:

| Property | Development | Staging | Production |
|---|---|---|---|
| Log level | DEBUG | INFO | INFO or WARN |
| Database endpoint | Local/dev DB | Staging DB | Production DB |
| Request timeout | Can be low for testing | Close to production | Based on SLO and service characteristics |
| Experimental feature flag | Can be enabled | Enabled per test plan | Enabled only when approved |
| External API | Sandbox | Sandbox or pre-production | Production endpoint |
| Credential | Dev account | Staging secret | Dedicated production secret |

You should not copy the entire production configuration into committed files. The repository can store the schema, property names, safe defaults, and sanitized examples. Actual values are supplied by the configuration management system or deployment platform.

### Avoid dangerous defaults

Default values such as enabling debug endpoints, allowing anonymous access, using weak passwords, or disabling TLS verification may make testing convenient, but create severe risks if accidentally deployed to production.

Defaults should be designed on secure-by-default principles:

- Fail to start if required configuration is missing.
- Never fall back to default credentials when a secret is absent.
- Disable dangerous debug features by default.
- Require TLS verification in deployed environments.
- Use least privilege for service accounts.
- Enable high-impact features only when explicitly configured.

## 4. Distinguishing Build-Time and Runtime Configuration

Not all configuration can be changed after an artifact is created. You must distinguish values used during the build from values read by the application at runtime.

### Build-time configuration

Build-time config affects the contents of the artifact or how the compiler packages the product.

Examples:

- Application version generated into a manifest.
- Compiler flags or runtime targets.
- Features stripped from or embedded into the bundle at build time.
- URLs compiled directly into a frontend application.
- Compiler optimization settings or profiles.

Because these values affect the artifact, they must be treated as build inputs, recorded, and controlled to support reproducibility. Do not put secrets into build-time config. Values embedded into binaries, JavaScript bundles, or images can be extracted by anyone who receives the artifact.

### Runtime configuration

Runtime config is supplied when the application starts or while it is running, without rebuilding the artifact.

Examples:

- Database URL, connection pool size, and timeout.
- Auxiliary service endpoints.
- Log level, sampling rate, and request limits.
- Feature flags that can change according to policy.
- Queue, bucket, or namespace names.

Runtime config supports build once, promote many: build once, then promote the same artifact across multiple environments by supplying the appropriate configuration.

### Frontend example

Environment variables during a frontend build are typically substituted into the JavaScript bundle. Values like an API base URL should be considered public information after the build. Do not put API secrets, private keys, or passwords into variables embedded into the frontend.

If you want the same bundle to run across multiple environments, you can serve a public runtime configuration file when the application boots in the browser. That file must only contain publicly safe values and never credentials.

## 5. Managing Configuration by Environment

Configuration can be stored in the same repository, a separate repository, or a config store system. The choice depends on scale, access control, and operational workflow.

### Same repository as the application

Suitable when configuration is small, environments are few, and the same team owns both. It can be organized as:

~~~text
service/
  src/
  config/
    defaults.yaml
    development.yaml
    staging.yaml
    production.example.yaml
  deploy/
    manifests/
  .env.example
~~~

The `production.example.yaml` file only contains the structure and safe illustrative values. Do not store real secrets or credentials.

The advantage is that code and config changes can be reviewed together. The drawback is that repository read permissions may be broader than production config read permissions; additional access controls or sensitive data separation are required.

### Separate configuration repository

A dedicated configuration repository can manage environment manifests, versions, reviews, and change history independently of the application.

Example:

~~~text
service-config/
  development/
    order-service.yaml
  staging/
    order-service.yaml
  production/
    order-service.yaml
~~~

This repository must not contain plaintext secrets. It can contain references to a secret manager, secret names, versions, or resource identities.

Separating repositories clarifies operational permissions and lets configuration be tracked as its own product. You should record which config revision was deployed alongside which artifact revision.

### Config store or control plane

For large systems, configuration can be managed by a central system, orchestration platform, or feature flag service. Applications receive configuration via API, mounted files, environment variables, or an agent.

You need to define:

- Which source is the source of truth.
- Who is allowed to modify and approve changes.
- How the application updates configuration.
- Whether configuration has versioning and audit history.
- What happens if the config service is unreachable.
- How to roll back to a previous version.
- How to control concurrent changes and drift.

Do not allow the same property to be modified arbitrarily in multiple places without precedence rules. When multiple sources exist, clearly specify which source wins and record the final resolved values used by the application.

## 6. Managing Secrets with a Secret Manager

Secrets must be stored in a dedicated system or a platform-protected secret store. Common examples include cloud secret stores, HashiCorp Vault, Kubernetes Secrets combined with proper encryption and access controls, or secret managers integrated into CI/CD platforms.

A secret manager typically provides capabilities such as:

- Encryption at rest and in transit.
- Read access control by identity or policy.
- Auditing of who accessed a secret and when.
- Versioning and rotation.
- Dynamic or short-lived credential issuance.
- Revoking access and credentials during incidents.

Not every system named "Secret" is automatically secure. You must verify encryption at rest, access control, auditing, backups, rotation, and how workloads authenticate.

### Prefer identities and short-lived credentials

If the platform supports workload identity or federation, pipelines can use the job's identity to obtain short-lived credentials instead of storing long-lived access keys in the repository.

General flow:

~~~text
CI job starts
     |
     v
Authenticate with workload identity
     |
     v
Secret manager checks identity and policy
     |
     v
Issue short-lived credential
     |
     v
Job uses credential for one task
     |
     v
Credential expires or is revoked
~~~

Short-lived credentials reduce the window in which a leaked token can be abused. Still, granted permissions must be scoped by repository, branch, environment, and job purpose.

### Secrets are not ordinary configuration

Do not put passwords into `application.yaml` just because the framework supports reading that file. If a secret must be delivered as a file, mount it from a secret manager or a protected volume with restricted filesystem permissions, a clear lifecycle, and proper revocation mechanisms.

Kubernetes Secrets are by default represented as base64-encoded data in API manifests; base64 is encoding, not encryption. You must enable encryption at rest for the datastore per platform configuration, restrict RBAC, avoid committing plaintext secret manifests, and consider integrating an external secret store or CSI driver.

## 7. Delivering Configuration and Secrets to Applications

There are multiple delivery mechanisms; choose based on platform, data sensitivity, and reload capabilities.

| Mechanism | Suitable for | Notes |
|---|---|---|
| Environment variables | Small, simple config and platform-injected secrets | Can appear in process inspection, crash dumps, or debug logs |
| Mounted configuration files | Multi-field configuration or apps requiring files | Must control file permissions, ownership, and lifecycle |
| Secret volume or CSI | Secrets that must be provided as files | Need to understand rotation and file update behavior |
| Secret manager API | Workloads fetching credentials by identity | Must handle timeouts, retries, and access permissions |
| Config service | Dynamically changeable configuration | Must define caching, fallback, versioning, and auditing |
| Platform manifest | ConfigMap, task definition, or deployment spec | Must avoid storing plaintext secrets in repositories |

### Environment variables

Environment variables are convenient for cloud-native applications because they are easy to inject via container runtimes and CI systems. Variable names should be clear, consistent, and documented.

Examples:

~~~sh
APP_LOG_LEVEL=INFO
APP_REQUEST_TIMEOUT=3s
DATABASE_URL=jdbc:postgresql://orders-db.internal:5432/orders
FEATURE_NEW_CHECKOUT=false
~~~

The variables above are illustrative configuration and contain no passwords. Secrets can be injected by the platform using protected mechanisms, but avoid printing the entire environment to logs or letting untrusted processes read it.

### Configuration files

Configuration files suit structures with many fields, lists, or nested objects. Files can be mounted per environment or read from a declared configuration directory.

You need to define which file is the default, which is the override, load order, and behavior when a file is missing. Never let the application silently fall back to default production config when a required file is absent.

### Configuration via API

A config service can deliver feature flags or runtime parameters. The application must control:

- Authentication and read permissions.
- Configuration version.
- Caching and TTL.
- Behavior when the service loses connectivity.
- Atomic updates to prevent half-old, half-new state.
- How to roll back to a previous version if new config causes errors.

Not every configuration item is suitable for dynamic changes. Properties affecting database connections or resource topology may require a restart or controlled rollout.

## 8. Naming Conventions, Structure, and Precedence

Configuration should be easy to find and understand. Names should convey purpose, scope, and unit of measurement.

Good examples:

- DATABASE_CONNECTION_TIMEOUT_SECONDS
- HTTP_MAX_CONNECTIONS
- APP_LOG_LEVEL
- FEATURE_CHECKOUT_V2_ENABLED

Vague names like TIMEOUT, VALUE, or ENABLED are easily misused. For numeric values, explicitly include the unit or document unit conventions in schemas and docs.

### Define precedence order

An application may read configuration from multiple sources:

1. Default values within the application.
2. Common configuration file.
3. Profile/environment-specific configuration file.
4. Environment variables.
5. Command-line arguments or platform-provided overrides.
6. Config service or secret store via integration mechanism.

Actual order depends on the framework. For example, Spring Boot has its own property source precedence rules; do not assume the list above automatically applies to every application.

Document the application's precedence and avoid setting the same value in multiple places where nobody knows which source wins. When investigating issues, it should be possible to inspect source names and config versions without printing secrets.

### Do not confuse configuration with command-line arguments

Command-line arguments can override config for a single run. If a pipeline or operator uses overrides, record non-sensitive parameters and ensure they do not inadvertently expose secrets in process lists or logs.

## 9. Validate Configuration Before Serving Traffic

Invalid configuration can allow an application to start and only fail when handling a request. Validation should happen at startup or before rollout.

Validation categories:

- **Data types:** numbers, booleans, durations, URLs, lists, or enums.
- **Bounds:** timeout greater than 0, pool size within a reasonable range.
- **Required fields:** mandatory endpoints or resource names.
- **Compatibility:** schema and API versions matching the application.
- **Cross-field relationships:** min not greater than max; retry delay compatible with timeout.
- **Security:** TLS verification enabled; debug endpoints not unintentionally exposed.
- **Connectivity:** checking endpoints or credentials without exposing secrets.

For example, if `APP_REQUEST_TIMEOUT` receives `"abc"`, the application should report a clear configuration error and halt startup rather than silently switching to an unexpected value.

### Controlled fail-fast

For required configuration, failing fast catches errors before traffic arrives. Error messages should state the property name and violated rule without printing secret values.

Not every configuration error requires stopping the entire application. An optional feature can be safely disabled when configuration is missing; a non-essential auxiliary endpoint can put its corresponding functionality into a degraded state. Behavior must be defined based on feature criticality.

## 10. Configuration in CI/CD Pipelines

Pipelines also have code, config, and secrets. The workflow file is automation control code; values like JDK version or test profile are configuration; publish tokens and deploy credentials are secrets.

Example workflow with non-sensitive configuration:

~~~yaml
jobs:
  verify:
    runs-on: ubuntu-24.04
    env:
      APP_LOG_LEVEL: INFO
      TEST_PROFILE: ci
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-java@v4
        with:
          distribution: temurin
          java-version: "21"
          cache: gradle
      - run: ./gradlew --no-daemon check
~~~

Secrets needed for a job can be retrieved from the platform's secret store or a secret manager via identity. Only the job performing an operation requiring a secret should be granted read access; lint or unit test jobs should not receive production credentials without an explicit reason.

### Separating permissions across jobs

A pipeline can be divided into:

| Job | Required configuration | Required secrets/permissions |
|---|---|---|
| Lint and unit tests | Toolchain, test profile | Typically no production secrets needed |
| Integration tests | Test service endpoints and settings | Dedicated test environment credentials if needed |
| Build/package | Version, build flags | Dependency read access; no deploy credentials |
| Publish artifact | Registry endpoint, repository | Write access to the target registry |
| Deploy staging | Target, namespace, rollout settings | Staging credentials |
| Deploy production | Production target, release policy | Dedicated production identity and approval |

Separating jobs reduces blast radius if a step is compromised. Jobs still need to protect artifacts and check results passed between stages.

### Do not pass secrets through artifacts or caches

Do not upload `.env` files containing credentials, runner home directories, token files, or debug logs as shared artifacts. Do not cache directories containing secrets or sensitive runtime config files.

Artifacts should be produced from intentional outputs, not the entire workspace. Before uploading, specify exact paths and verify the contents being included.

## 11. Do Not Embed Secrets in Images or Build Arguments

Dockerfiles and image builds are frequently misused to pass credentials.

Unsafe example:

~~~dockerfile
ARG DB_PASSWORD
ENV DB_PASSWORD=$DB_PASSWORD
~~~

The value can appear in metadata, layer history, build logs, or be persisted inside the image. Do not use `ARG` or `ENV` as a secret store.

If a build needs credentials to fetch private dependencies, use the builder's secret mount mechanism or short-lived credentials issued specifically for that step. Secret mounts must be used within the specific step, never copied into layers, and never written to logs.

Runtime secrets should be provisioned when the container runs via a secret manager, orchestrator, or workload identity. The image should only contain the application, runtime, and non-sensitive default configuration.

## 12. Tracking Configuration Versions and Config Drift

Configuration also requires versioning and change history. If application version 2.4.1 is running with config revision C17, the deployment record should store both identifiers.

Config drift occurs when actual state diverges from declared desired configuration. Examples:

- Someone edits environment variables directly on a production host.
- A value is changed through a console UI without updating the configuration repository.
- Two replicas run with two different config revisions.
- A secret is rotated, but older workloads have not picked up the new credential.
- A ConfigMap or deployment manifest no longer matches Git.

To control drift:

- Manage desired configuration in a versioned source.
- Record audit logs for direct changes.
- Periodically compare actual state against desired state.
- Use GitOps or reconciliation mechanisms where appropriate.
- Link config revisions to release/deployment records.
- Alert when instances run inconsistent configurations.

Not all drift should be overwritten automatically. An emergency change may need to be retained temporarily; it should be documented, evaluated, and reconciled back to the source of truth following process.

## 13. Configuration Changes, Rollout, and Rollback

A configuration change can quickly impact all instances if applied simultaneously. Config changes should be deployed as controlled release changes.

Reference workflow:

1. Create the configuration change in a managed source.
2. Validate schema, data types, bounds, and cross-field relationships.
3. Review impact, especially on timeouts, pools, feature flags, and permissions.
4. Test in development or staging.
5. Roll out by instance groups or canary if the platform supports it.
6. Monitor error rates, latency, resource usage, and business behavior.
7. Expand rollout when signals meet criteria.
8. Record the config revision and verification results.

### Compatibility between code and config

A new application version may require a configuration property that the older version does not understand. Conversely, removing a property can break currently running versions.

During a rolling update, multiple application versions may coexist. Design configuration schemas to remain compatible across the transition window:

- Add new properties with safe defaults whenever possible.
- Deploy an application version capable of reading both old and new configurations.
- Switch configuration after instances support it.
- Remove old properties only when no running version depends on them.

### Configuration rollback

If a new config causes errors, you need to know the previous config revision and how to restore it. Rollback can be performed independently of code if the current application version remains compatible with the old configuration.

If the config change accompanied a new schema or behavior, you may need to roll back the application as well or execute a transition step. Do not assume every config can be reverted immediately, especially with migrations, credential rotations, or data changes.

## 14. Example Configuration Organization for a Java Application

With Spring Boot, non-sensitive default configuration can be stored in `application.yaml`:

~~~yaml
server:
  port: 8080

spring:
  application:
    name: order-service
  datasource:
    url: jdbc:postgresql://localhost:5432/orders

app:
  request-timeout: 3s
  retry:
    max-attempts: 2

logging:
  level:
    root: INFO
~~~

The deployment environment supplies overrides via profiles or environment variables. For example, in staging:

~~~sh
SPRING_PROFILES_ACTIVE=staging
SPRING_DATASOURCE_URL=jdbc:postgresql://staging-db.internal:5432/orders
APP_REQUEST_TIMEOUT=3s
APP_RETRY_MAX_ATTEMPTS=2
~~~

Database credentials are fetched from a secret manager or the platform's secret injection mechanism. Do not commit production username/password values into `application.yaml`, profile files, or Docker images.

Key considerations:

- Profiles help organize configuration by environment, yet profile files remain version-controlled content and must not contain real secrets.
- Spring Boot supports relaxed binding from environment variables to properties; verify naming rules for nested properties and data types.
- Use validation annotations or typed configuration properties to catch invalid values at startup.
- Do not log the entire configuration object because it may contain secrets or sensitive data.
- If effective configuration needs to be inspected, expose only allowlisted properties and mask sensitive values.

## 15. Common Mistakes

| Anti-pattern | Consequence | Improvement |
|---|---|---|
| Hardcoding production endpoints in source | Requires rebuilding or editing code when changing environments | Move values to runtime config |
| Committing passwords to Git | Secrets persist in history and clones | Use a secret manager; rotate if exposed |
| Storing secrets in profile files | Files can easily leak into artifacts or logs | Store references only and inject secrets at runtime |
| Using Docker ARG/ENV to pass build passwords | Secrets can leak into image layers or metadata | Use secret mounts and short-lived credentials |
| Sharing the same credentials across dev/staging/prod | An incident in one environment compromises others | Separate identities and secrets per environment |
| Printing the full environment for debugging | Logs may expose tokens and passwords | Log only allowlisted config names and mask values |
| Using default credentials when secrets are missing | Application may start with insecure permissions | Fail fast or disable features per policy |
| Setting the same property in multiple places without precedence | Difficult to determine effective values | Document and verify the winning source |
| Editing config directly in production | Causes config drift, hard to audit and roll back | Manage changes through a versioned source |
| Putting secrets into caches/artifacts | Multiple jobs or users may read them | Restrict upload/cache paths and access permissions |
| Changing config everywhere at once without validation | Failures spread across all instances | Validate, canary, and monitor rollout |
| Granting all jobs read access to production secrets | Increases blast radius if pipeline is compromised | Split jobs and apply least privilege |

## 16. Checklist for Separating Code, Config, and Secrets

### Application code

- [ ] Logic and behavior are managed in a source repository.
- [ ] Changes go through commits, reviews, and tests.
- [ ] Artifacts have a version or digest tied to a commit.
- [ ] Contains no credentials, private keys, or tokens.
- [ ] Does not embed environment-specific values when they can be supplied at runtime.

### Configuration

- [ ] Every property has a clear name, type, unit, and meaning.
- [ ] Safe defaults and rules for required values are defined.
- [ ] Environment-specific configuration is versioned and reviewed.
- [ ] Build-time and runtime config are clearly distinguished.
- [ ] Precedence order is documented.
- [ ] Configuration is validated before receiving traffic.
- [ ] Config revision is attached to deployment records.
- [ ] Mechanisms exist for drift detection and rollback.

### Secrets

- [ ] Secrets are stored in a secret manager or protected store.
- [ ] Access permissions are restricted by identity, job, and environment.
- [ ] Short-lived credentials or workload identity are preferred where supported.
- [ ] Secrets are absent from Git, images, artifacts, caches, and logs.
- [ ] Processes exist for rotation, revocation, and exposure response.
- [ ] Each environment uses dedicated credentials.
- [ ] Secret injection and file permissions are controlled.
- [ ] Audit logs record access and modifications.

### Pipeline and deployment

- [ ] Jobs receive only the configuration and secrets they actually need.
- [ ] Test jobs have no production deployment permissions unless explicitly required.
- [ ] Artifacts are built once and promoted across environments.
- [ ] Runtime config is supplied in the target environment.
- [ ] Config changes are validated, reviewed, and rolled out in a controlled manner.
- [ ] Deployment records store both artifact version and config revision.
- [ ] Post-deployment checks and a rollback plan are in place.

## Conclusion

Application code defines behavior, configuration adjusts how that behavior operates in each environment, and secrets protect identities and access permissions. Separating these three groups keeps a single artifact consistent across environments, enables controlled configuration changes, and limits credential exposure scope. In CI/CD, version control code and non-sensitive configuration, supply runtime config in the target environment, manage secrets with identities and a secret manager, and record both artifact revision and config revision for every deployment.
