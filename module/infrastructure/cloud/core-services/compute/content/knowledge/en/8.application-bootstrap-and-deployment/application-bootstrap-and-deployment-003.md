# Separating application configuration from images and source code

## Lesson objectives

An application often runs across multiple environments such as development, testing, staging, and production. These environments may run the exact same version of source code while differing in database addresses, service endpoints, log levels, connection limits, and credentials. If those values are hardcoded in source code or baked into an image, deployment becomes difficult to control and error-prone when promoting across environments.

Separating application configuration from images and source code (externalized configuration) allows a single tested artifact to be deployed across multiple environments by supplying the appropriate configuration at runtime.

After this lesson, you will be able to:

- Distinguish application configuration, source code, deployment images, and secrets.
- Choose between supplying configuration via files, environment variables, or a configuration management service.
- Manage secrets using a secret manager and workload identities.
- Organize configuration by environment, validate required values, and handle precedence order.
- Safely update configuration for virtual machines, containers, and Kubernetes workloads.

## 1. Why separate configuration?

Suppose a Java service connects to PostgreSQL and a payment service. In staging, the application must use the staging database and a sandbox endpoint. In production, it uses the production database, the real endpoint, an appropriate log level, and larger connection limits.

If these addresses are embedded directly in source code, changing environments may require editing code, rebuilding, and releasing a new artifact. That approach increases the risk that:

- Staging and production builds accidentally diverge even for the same application version.
- A test endpoint or sandbox account slips into production.
- Sensitive information gets committed to Git or ends up inside an image.
- Even a small configuration change forces rebuilding and redeploying the entire application.
- It becomes hard to determine the actual configuration an instance is running during an incident.

When configuration is separated, the development team builds a single versioned artifact. The deployment environment supplies the appropriate values when running the application. As a result, the same artifact can run across environments without modifying source code or image contents.

~~~mermaid
flowchart LR
    A["Source code"] --> B["Build once"]
    B --> C["Artifact / container image"]
    C --> D["Deploy to staging"]
    C --> E["Deploy to production"]
    F["Staging configuration"] --> D
    G["Production configuration"] --> E
    H["Secret manager / workload identity"] --> D
    H --> E
~~~

This principle is commonly known as build once, deploy many: build a traceable artifact, then deploy that artifact with environment-specific configuration.

## 2. Distinguishing source code, configuration, and secrets

Not every value that varies across environments carries the same sensitivity level. Classify data before choosing where to store it.

| Information type | Examples | Appropriate management |
|---|---|---|
| Source code and logic | Pricing rules, order processing flows | Git and build/release pipelines |
| Non-secret configuration | Environment name, log level, timeouts, feature flags, public endpoints | Configuration files, environment variables, or config service |
| Secrets | DB passwords, API tokens, private keys, credentials | Secret manager or controlled secret store |
| Resource parameters | CPU, RAM, port, replica count, connection limits | Deployment manifests, machine templates, or IaC |
| Operational data | Order state, user profiles, transactions | Databases or appropriate data storage systems |

Configuration describes how the application should behave in the current environment. Secrets are authorization or authentication data that can grant resource access if exposed. Therefore, secrets require strict access controls, auditing, and rotation mechanisms.

Do not assume every value in a configuration file is non-sensitive. A file may contain internal endpoints, account names, topology details, or operational settings that require restricted access. Classify each value according to its actual sensitivity.

## 3. Ways to supply configuration at runtime

### 3.1. Configuration files

The application reads configuration from YAML, JSON, TOML, properties, or a framework-appropriate format. Files can be placed on a VM, mounted into a container, or fetched from a configuration management system at startup.

Example application.yaml file:

~~~yaml
server:
  port: 8080

app:
  environment: production
  log-level: INFO
  request-timeout: 3s

database:
  host: db.internal.example
  port: 5432
  name: orders
  pool:
    max-size: 30

payment:
  endpoint: https://payments.example.com
~~~

The file above only contains illustrative non-secret configuration. Passwords and tokens should be retrieved separately from a secret manager or the platform's secret mechanism.

Advantages of configuration files:

- Hierarchical structure, easy to read and inspect.
- Can be versioned and changes can be reviewed.
- Well suited for applications with many configuration groups.
- Can be mounted into containers without repackaging the image.

Limitations to keep in mind:

- Files must be distributed and updated to the right machines or workloads.
- If they contain secrets, read permissions, encryption, and storage workflows must be protected.
- The application must clearly define when to reload files and how to handle syntax errors.

### 3.2. Environment variables

Environment variables pass values into a process at startup. This is a common way to supply configuration to containers and cloud-native applications.

Example:

~~~bash
export APP_ENV=production
export APP_LOG_LEVEL=INFO
export DB_HOST=db.internal.example
export DB_PORT=5432
export DB_NAME=orders
export PAYMENT_ENDPOINT=https://payments.example.com
java -jar orders-service.jar
~~~

The application reads these variables at startup. In Java, they can be accessed via System.getenv("DB_HOST"); frameworks like Spring Boot also support mapping environment variables to configuration properties.

Advantages:

- Simple and widely supported across Linux, Windows, containers, and deployment services.
- Easy to pass values from machine templates, service managers, or container orchestrators.
- Enables running the same image with different configuration sets.

Limitations:

- Environment variables are usually fixed for a process at launch time; external changes do not automatically update a running process's values.
- Values can leak through debugging tools, process dumps, diagnostic configurations, or logs if operated carelessly.
- Not convenient for large configurations, complex structures, or continuously updated data.
- Variable names and data types must be standardized to avoid typos or invalid conversions.

Do not pass secrets into shell commands in ways that expose values in shell history or process listings. When supported by the platform, prefer workload identity combined with a secret manager or mounting secrets as files with restricted access.

### 3.3. Centralized configuration management service

A config service stores and distributes configuration across many applications or instances. For example, an organization can use a cloud provider's parameter management service, a configuration management system, or an internal platform.

Common capabilities:

- Store configuration by application, environment, region, or version.
- Control read and write access by identity.
- Track change history and approvers.
- Distribute configuration to many instances.
- Support rollouts, caching, and rolling back to previous versions.
- Integrate with a secret manager or key management system.

A config service reduces the risk of each machine holding a different copy of configuration. However, applications must handle cases where the config service is unreachable, such as using valid cached values, explicit timeouts, and safe startup policies.

### 3.4. Metadata and user data

On cloud VMs, the metadata service can provide instance information such as ID, zone, network interfaces, or workload identity. User data/startup scripts can pass initialization parameters when creating the machine.

Metadata and user data serve different roles:

- Metadata typically contains platform-provided information about the running resource.
- User data typically contains content or parameters passed by the deployer to bootstrap the machine.
- Do not assume metadata or user data is a secure secret store by default. Access, storage, and protection depend on the platform and configuration.

Put only necessary initialization data into user data. When secrets are needed, use workload identity to access a secret manager and retrieve secrets at runtime.

## 4. Managing configuration by environment

An application often has multiple environments, yet you should not maintain separate source code branches just to change database addresses or log levels.

Configuration can be organized in a structure like:

~~~text
config/
  defaults.yaml
  development.yaml
  staging.yaml
  production.yaml
~~~

defaults.yaml contains safe shared values. Environment files override only the properties that genuinely differ. For example:

~~~yaml
# defaults.yaml
server:
  port: 8080
app:
  log-level: INFO
database:
  port: 5432
  pool:
    max-size: 10
~~~

~~~yaml
# production.yaml
app:
  log-level: WARN
database:
  host: db-prod.internal
  name: orders
  pool:
    max-size: 40
~~~

Environment-dependent values can be supplied from deployment manifests or a config service rather than storing everything in the repository. For production, define who can read and modify configuration, and maintain an audit log of changes.

Key principles:

- Use the same tested artifact across environments.
- Separate shared configuration from environment-specific configuration.
- Do not use dangerous defaults for production, such as sandbox endpoints or sample passwords.
- Do not store production secrets in a repository—even a private one—unless an approved encryption mechanism and secret management process are in place.
- Each environment has its own identities and access permissions.
- Record the deployed configuration version alongside the application version.

## 5. Precedence order and configuration merging

An application can receive the same property from multiple sources: in-app defaults, configuration files, environment variables, command-line arguments, or a config service. Without a defined precedence order, two environments may produce confusingly different results.

A common illustrative order:

1. Safe in-application defaults.
2. Shared configuration file.
3. Environment-specific configuration file.
4. Environment variables provided by the deployment platform.
5. Explicitly passed command-line arguments.

A config service may sit at a different position in the order depending on the design. This is not a mandatory rule for every framework; choose and document the exact precedence order your application actually supports.

For example, if DB_POOL_MAX is set to 10 in the shared file and 40 in a production environment variable, the application can use 40 if the precedence rule gives environment variables higher priority.

Control merging carefully:

- Explicitly define which source can override which.
- Validate data types, value ranges, and required fields.
- Do not fall back to default values automatically when a critical security setting is missing.
- When two sources conflict, log the property name and configuration source, never the secret value.
- Avoid having multiple sources control the same value unnecessarily.

## 6. Example: Java application reading external configuration

A straightforward approach is reading configuration from environment variables and validating it immediately on startup:

~~~java
public final class DatabaseConfig {
    private final String host;
    private final int port;
    private final String database;

    public DatabaseConfig() {
        this.host = required("DB_HOST");
        this.port = Integer.parseInt(
            System.getenv().getOrDefault("DB_PORT", "5432")
        );
        this.database = required("DB_NAME");

        if (port < 1 || port > 65535) {
            throw new IllegalArgumentException("DB_PORT is out of range");
        }
    }

    private static String required(String name) {
        String value = System.getenv(name);
        if (value == null || value.trim().isEmpty()) {
            throw new IllegalStateException(
                "Missing required configuration: " + name
            );
        }
        return value;
    }

    public String host() { return host; }
    public int port() { return port; }
    public String database() { return database; }
}
~~~

This example only demonstrates reading and validating non-secret configuration. In real applications, use an appropriate configuration framework and validate hostname formats, timeouts, pool sizes, and other required properties. Passwords should be retrieved via a secret manager or platform secret mechanism, and getters should never print passwords to logs.

A useful principle is **fail fast**: if required configuration is missing or a value is invalid, the application fails clearly and refuses traffic. Starting up with a wrong default endpoint can cause the service to connect to the wrong system.

## 7. Secrets and workload identity

Secrets must be managed differently from regular configuration. Examples include:

- Database passwords.
- API tokens or OAuth client secrets.
- Private keys and certificates with private keys.
- Credentials for accessing registries or external systems.

Preferred workflow:

1. Assign an identity to the workload, such as a service account, instance role, or managed identity.
2. Grant least-privilege permissions so that identity can read only the exact secrets it needs.
3. At startup, use a supported SDK or agent to fetch secrets from a secret manager.
4. Keep secrets in memory or mount them into files with restricted read permissions as required by the application.
5. Avoid writing secrets to logs, traces, metric labels, exception messages, or crash dumps.
6. Monitor secret reads and rotate secrets on signs of exposure or according to schedule.

Example access flow:

~~~mermaid
sequenceDiagram
    participant App as Application
    participant Id as Workload identity
    participant SM as Secret manager
    participant DB as Database
    App->>Id: Request token for workload identity
    Id-->>App: Short-lived token
    App->>SM: Read secret with token
    SM-->>App: Authorized secret
    App->>DB: Connect using credential
    DB-->>App: Authenticated connection
~~~

Workload identities eliminate the need to embed long-lived access keys into images or deployment files. Short-lived tokens must also be protected during use; never write tokens to logs or transmit them over insecure channels.

### Why shouldn't secrets be baked into images?

Images are routinely copied across regions, accounts, pipelines, and environments. If a secret resides inside an image, anyone with permission to pull or run the image can extract it. Deleting a secret file in the final image layer does not remove the data from earlier layers.

If you suspect a secret was baked into an image, treat it as a potential credential exposure: revoke or rotate the secret, build a clean image, and audit distribution history. Do not simply delete the configuration line in a newer image.

## 8. Configuration in containers and Kubernetes

### 8.1. Docker

Docker allows passing configuration via environment variables or mounted files:

~~~bash
docker run --rm \
  -e APP_ENV=production \
  -e DB_HOST=db-prod.internal \
  -e DB_PORT=5432 \
  -v /etc/orders/config.yaml:/app/config/config.yaml:ro \
  orders-service:1.8.2
~~~

In this example, the orders-service:1.8.2 image does not need to change between staging and production. Environment values and files are supplied when running the container. The application must be configured to read the file at /app/config/config.yaml; mounting a file alone does not automatically make the application load its contents.

Do not pass passwords directly in `-e` flags inside shared shells or systems that record command history. For secrets, use the orchestrator's secret mechanism or a secret manager.

### 8.2. Kubernetes ConfigMap

A ConfigMap stores non-secret configuration data for Pods to consume via environment variables or volume mounts.

~~~yaml
apiVersion: v1
kind: ConfigMap
metadata:
  name: orders-config
data:
  APP_ENV: production
  LOG_LEVEL: INFO
  DB_HOST: db-prod.internal
  DB_PORT: "5432"
~~~

A Deployment can inject these values into containers:

~~~yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: orders
spec:
  replicas: 3
  selector:
    matchLabels:
      app: orders
  template:
    metadata:
      labels:
        app: orders
    spec:
      containers:
        - name: app
          image: registry.example.com/orders:1.8.2
          envFrom:
            - configMapRef:
                name: orders-config
          ports:
            - containerPort: 8080
~~~

ConfigMaps are suitable for endpoints, log levels, and non-secret parameters. Never use a ConfigMap to store passwords or tokens.

### 8.3. Kubernetes Secret

Secrets are intended for sensitive data such as passwords or tokens:

~~~yaml
apiVersion: v1
kind: Secret
metadata:
  name: orders-db-credentials
type: Opaque
stringData:
  username: orders_app
  password: REPLACE_WITH_SECRET
~~~

A Secret field can be referenced into an environment variable:

~~~yaml
env:
  - name: DB_USERNAME
    valueFrom:
      secretKeyRef:
        name: orders-db-credentials
        key: username
  - name: DB_PASSWORD
    valueFrom:
      secretKeyRef:
        name: orders-db-credentials
        key: password
~~~

The YAML snippets only illustrate structure. Never commit real passwords to Git. The stringData field accepts plaintext string values; Kubernetes converts them when storing the Secret object. Secret data in manifests/APIs is typically represented in base64, but base64 is only an encoding representation, not security encryption. Configure encryption at rest for the cluster datastore, restrict RBAC, protect backups, and consider integrating an external secret manager.

If a workload uses a CSI driver or an external secrets operator, secrets can be mounted from an external system. Verify update behavior and how the application reloads files after secret rotation.

### 8.4. Updating configuration and Pod rollouts

How an application receives configuration updates depends on the source:

- Environment variables are assigned when the container starts; existing Pods do not automatically pick up new values just because a ConfigMap changed.
- ConfigMaps/Secrets mounted as volumes can be updated by Kubernetes, but the application must reload the file or be restarted to apply changes.
- ConfigMaps/Secrets mounted via subPath have different update behavior; do not assume mounted files will update automatically.
- Some applications read configuration only once at startup, so a Pod rollout is required to load new values.

You can include a configuration checksum in the Pod template or use a rollout tool to recreate Pods when configuration changes. Before deploying, determine whether the application supports dynamic reloading or requires a restart.

## 9. Making configuration changes safely

Configuration changes can have an impact comparable to source code changes. A wrong endpoint, oversized pool, or inappropriate timeout can cause service disconnects or resource exhaustion.

Recommended workflow:

1. **Create traceable changes:** record who changed what, why, environment, version, and timestamp.
2. **Validate schema:** verify required fields, data types, numeric bounds, and formats.
3. **Verify connectivity:** verify endpoints, DNS, certificates, IAM permissions, and reachable dependencies.
4. **Canary deploy:** apply to a single instance or canary group.
5. **Monitor:** inspect errors, latency, connection rates, logs, and metrics.
6. **Expand:** roll out in waves if metrics meet expectations.
7. **Rollback:** restore the previous configuration version if errors occur.
8. **Record:** update inventory and observed configuration state.

Do not edit configuration directly on individual machines without updating the canonical source of truth. Manual edits easily create configuration drift: machines with the same role running with different values.

## 10. Static and dynamic configuration

Not every setting needs to update while the application is running.

**Static configuration** is typically read at startup, such as listening port, pool size, or thread settings. Changing these usually requires a restart or rollout.

**Dynamic configuration** can be reloaded by the application at runtime, such as feature flags, rate thresholds, or blocklists. The application must be designed to check for new versions, validate values, and apply them safely.

| Criterion | Static configuration | Dynamic configuration |
|---|---|---|
| When applied | Typically at startup | Can happen at runtime |
| Update mechanism | Restart/redeploy or process restart | Polling, push events, watchers, or API |
| Complexity | Lower | Higher due to synchronization and error handling |
| Risk | Brief disruption during rollout | State across instances may diverge if updates are asynchronous |
| Examples | Port, heap size, DB pool size | Feature flags, business thresholds, allowlists |

For dynamic configuration, define behavior when the config service loses connectivity, a new version is invalid, or two updates arrive close together. The application should retain the last known good configuration or fall back to a safe mode per business requirements.

## 11. Validating configuration before serving traffic

Applications should validate configuration immediately upon startup and before reporting ready.

Useful checks:

- Required fields must not be empty.
- Ports fall within valid ranges.
- Timeouts and retry limits are non-negative and not excessive.
- Pool sizes fit within database connection limits.
- URLs have valid schemes and hostnames.
- Log levels belong to the supported set of values.
- Feature flags have valid boolean or enum types.
- Workload identity can access required secrets and resources.

Separate two types of checks:

- **Liveness:** the process is alive and not deadlocked.
- **Readiness:** the application has loaded required configuration and can accept traffic.

If a secret is missing or a mandatory dependency is unreachable, the application can fail readiness to avoid accepting requests only to return mass errors. However, readiness should not depend too tightly on non-essential auxiliary services, or an outage in a secondary dependency could pull the entire workload out of traffic.

## 12. Common pitfalls and how to avoid them

**Hardcoding endpoints or credentials in source code:** creates divergence across environments and increases secret exposure risk. Move configuration to external sources and secrets to a secret store.

**Building separate images per environment:** causes staging and production artifacts to differ and harms traceability. Build one versioned artifact and inject configuration at deployment time.

**Baking secrets into images or build layers:** secrets may linger in old layers, caches, or registries. Rotate exposed credentials and build a clean image.

**Using environment variables for every data type:** environment variables suit small, simple values, whereas mounted files or config services suit larger structures and complex updates.

**Treating Kubernetes Secrets as if base64 were encryption:** base64 does not protect secrets. Configure encryption at rest, RBAC, auditing, and secret manager integration.

**Missing precedence rules:** the same variable set across multiple sources creates unpredictable behavior. Document the canonical source and override order.

**Missing input validation:** invalid values can make the application run with dangerous settings. Validate schemas and fail fast on required fields.

**Changing config without rollout or reload:** running processes may continue using stale values. Define the reload/restart mechanism for each configuration source.

**Manual per-machine edits:** causes configuration drift. Manage configuration through IaC, a config service, or traceable pipelines.

**Logging secrets for debugging:** logs are often forwarded to many systems and users. Log only field names, sources, and validation status; mask or strip sensitive values.

## 13. Externalized configuration design checklist

- [ ] Classified source code, non-secret configuration, secrets, and application data.
- [ ] The same artifact is used across target deployment environments.
- [ ] Configuration has a clear canonical source and precedence order.
- [ ] Required values are validated before the application accepts traffic.
- [ ] Secrets are stored in a secret manager or appropriate secret mechanism.
- [ ] Workloads use dedicated identities with least-privilege access.
- [ ] Secrets never appear in Git, images, user data, or logs.
- [ ] Configuration has versioning, auditing, and designated owners.
- [ ] Determined whether the application requires a restart or supports reload on config changes.
- [ ] Canary rollout, monitoring, and rollback exist for critical changes.
- [ ] Environments are checked to detect configuration drift.
- [ ] Readiness reflects ability to serve with the current configuration.

Separating configuration from images and source code allows the same artifact to run consistently across multiple environments. Configuration files, environment variables, and config services supply operational parameters; secret managers and workload identities protect credentials. With clear configuration sources, precedence rules, input validation, and rollout workflows, operations teams can safely adapt environments without rebuilding the application for every config change.
