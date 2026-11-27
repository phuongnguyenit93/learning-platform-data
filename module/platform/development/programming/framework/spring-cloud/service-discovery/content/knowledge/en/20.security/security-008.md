# Managing Credentials with Externalized Secret Configuration

Spring Cloud Service Discovery applications typically require credentials to connect to the registry, register instances, read service lists, or call administrative APIs. Examples include Consul ACL tokens, Eureka HTTP credentials, ZooKeeper authentication credentials, or login credentials for a secret manager. Putting these values directly in source code, committed application.yml files, or Docker images can expose secrets through Git, logs, image layers, backups, and CI/CD systems.

The secure approach is to separate regular configuration from secrets, store secrets in a secret management system or protected configuration source, and inject them into Spring Boot at runtime. This lesson focuses on credentials for Service Discovery in Spring Cloud: granting role-appropriate permissions, loading external secrets, rotating credentials, and controlling where secrets appear.

## 1. Distinguishing Configuration from Secrets

Configuration tells the application where to connect and how to behave. Secrets prove the application is authorized to access it.

| Data Type | Example | Safe to Commit to Git? |
|---|---|---|
| Registry endpoint | registry.internal:8500 | Yes, if it contains no sensitive info |
| Service name | inventory-service | Yes |
| Application port | 8081 | Yes |
| Connect/read timeout | 2s, 3s | Yes |
| Consul ACL token | Token with service read/register permissions | No |
| Eureka username/password | HTTP Basic credentials | No |
| ZooKeeper credential | Digest/SASL credentials or authentication material | No |
| TLS private key | Client or service private key | No |
| Secret manager token | Token to fetch runtime secrets | No |

Some values look like configuration yet can contain secrets. For example, a URL formatted as user:password@host or a JDBC URL containing a password. Classify by actual contents, not merely by property name.

Secrets should never be placed in source code, committed application.yml files, Dockerfiles, build arguments, image layers, Git commits, pull requests, pipeline logs, service metadata, service names, tags, or labels. Never store secrets in startup logs, exception messages, Actuator endpoints, or tracing baggage.

If a secret has already been committed or logged, deleting the line from the current version is not enough. You must revoke or rotate the secret because copies may still exist in Git history, artifacts, caches, and logs.

## 2. External Secret Sources

Depending on infrastructure, applications can obtain secrets from:

- **Secret manager:** HashiCorp Vault, AWS Secrets Manager, Azure Key Vault, Google Secret Manager, or an equivalent system.
- **Orchestrator:** Kubernetes Secrets mounted into Pods or container platform secret integrations.
- **Container runtime:** Docker/Compose secrets mounted as read-only files.
- **Virtual machines:** systemd credentials, permission-restricted files, or a secret agent.
- **CI/CD:** pipeline secret stores supplying credentials at deploy time without printing values to logs.
- **Spring Boot externalized configuration:** environment variables, external properties files, or config trees mounted from a secure source.

Secret managers typically offer advantages in auditing, policies, rotation, and centralized access control. File mounts or environment variables may fit smaller systems, though operations teams must manage file permissions, distribution, rotation, and revocation.

No single secret source fits every environment. Choose based on access control, auditing, rotation, availability, and how workloads prove their identity to the secret source.

## 3. Loading Secrets with Spring Boot Config Tree

Spring Boot supports importing configuration from a directory via the `configtree:` prefix. Each file in the directory is treated as a property; the filename is the property key and the file contents are the value. This fits secrets mounted from Docker, Kubernetes, or host credential managers.

Example directory layout:

```text
/run/secrets/
  discovery.consul.acl-token
  discovery.registry.username
  discovery.registry.password
```

The `discovery.consul.acl-token` file contains the token, and the username/password files hold the corresponding credentials. Never store real values in the repository.

In `application.yml`, declare:

```yaml
spring:
  config:
    import: "configtree:/run/secrets/"
  application:
    name: inventory-service
  cloud:
    consul:
      host: consul.internal.example
      port: 8500
      discovery:
        register: true
        acl-token: ${discovery.consul.acl-token}
```

In this example, Spring Boot loads the file from the directory and provides the property `discovery.consul.acl-token`. The placeholder passes that value into Consul Discovery's token property. Verify provider-specific property names for the exact Spring Cloud Consul version your project uses.

Do not use the `optional:` prefix for mandatory production secrets if the application cannot operate safely without credentials. When the import is required, Spring Boot fails fast with a configuration error if the required directory or property is missing. Locally you may use optional if a safe development alternative exists, but never let production applications silently run unauthenticated.

### Using an External Properties File

You can mount a dedicated properties file:

```properties
discovery.consul.acl-token=VALUE_INJECTED_AT_RUNTIME
```

Then import the file from its protected location:

```yaml
spring:
  config:
    import: "file:/etc/inventory/secrets/discovery.properties"
```

The file path and permissions must be managed by the OS or secret manager. The file should be readable only by the application user and authorized operators.

## 4. Consul ACL Token Example

Consul can use ACL tokens to control which clients may register, read the catalog, or perform administrative operations. Tokens should be granted only the policies needed by the service.

Example discovery configuration:

```yaml
spring:
  application:
    name: inventory-service
  config:
    import: "configtree:/run/secrets/"
  cloud:
    consul:
      host: consul.internal.example
      port: 8500
      discovery:
        register: true
        acl-token: ${discovery.consul.acl-token}
```

The secret file is mounted at:

```text
/run/secrets/discovery.consul.acl-token
```

Do not use a single full-privilege management token across all microservices. Separate policies by role:

- Providers only have permission to register, update, and deregister within their granted scope.
- Consumers have permission to read only the required services/catalog entries.
- Operational tools have elevated administrative permissions granted to dedicated personnel and workloads.
- Deployment pipelines receive permissions only for the required duration and scope.

Exact policy names and scopes depend on Consul ACL configuration. Test the token's permissions against real operations: whether the provider can register, whether the consumer can read services, and that the token lacks unintended permissions.

## 5. Eureka Credentials and HTTP Client Configuration

Eureka clients typically communicate with Eureka Server over HTTP endpoints. When authentication is enabled on the server, the client must supply credentials using a mechanism supported by your Spring Cloud Netflix version and configured HTTP transport.

There is no universal Spring Cloud username/password property across all registries. Some Eureka setups express credentials in the service endpoint URL, but URLs containing user-info are easily leaked into logs, exceptions, actuator output, or diagnostics. If your version and transport require this approach, pull the entire URL from a secret store, restrict config read access, and mask values in logs. Prefer credential/HTTP client mechanisms that are officially supported and cleanly protectable in your project's version.

Example externalizing the endpoint when the system requires a URL already containing credentials:

```yaml
eureka:
  client:
    service-url:
      defaultZone: ${discovery.eureka.service-url}
```

A secret file or secret manager supplies the `discovery.eureka.service-url` property at runtime. The real value must never be stored in application.yml or Git. Passing the URL via a placeholder only separates the secret from source code; it does not automatically mask the URL in logs or diagnostic endpoints.

When using HTTP Basic or custom Client configuration, verify how credentials are passed for your exact Eureka client version. Avoid writing custom uncontrolled interceptors or transports that accidentally log the Authorization header.

## 6. ZooKeeper Authentication and ACLs

ZooKeeper protects data via per-znode ACLs and authentication schemes such as digest or SASL depending on deployment. Spring Cloud Zookeeper uses the client/Curator to connect and manage registrations. Credentials must be provisioned for the right root path and required operations.

Example external secret layout:

```text
/run/secrets/
  discovery.zookeeper.username
  discovery.zookeeper.password
```

The application reads those properties and configures the authentication mechanism supported by the Curator/ZooKeeper client version in use. Spring Cloud Zookeeper property names, authentication scheme setup, and ACLs vary by version; never assume setting a password property automatically protects all znodes.

Key principles:

- Providers need permissions to create and delete registrations under the granted root path.
- Consumers need read permissions on service registrations.
- Never grant write/delete permissions across the entire ZooKeeper tree to every application.
- Never store digest passwords, SASL secrets, or private keys in service metadata.
- Verify ACLs on znodes after registrations are created rather than checking only that session connection succeeds.

A live ZooKeeper session does not mean credentials are properly protected. Connection authentication and per-znode authorization are two separate steps.

## 7. Distributing Secrets on Virtual Machines

On VMs, secrets can be provided by a secret agent, systemd credentials, or files generated by a configuration management system. Example properties file:

```text
/etc/inventory/secrets/discovery.properties
```

The file must be owned by the appropriate user/group with minimal read permissions. On Linux, permissions equivalent to `0600` can be used if only the application user needs read access. Never place the file in a source directory or publicly backed-up artifact directory.

Example importing an external file:

```yaml
spring:
  config:
    import: "file:/etc/inventory/secrets/discovery.properties"
```

When using systemd, credentials can be supplied via systemd's credentials mechanism and Spring Boot configured to read from the runtime-provided credentials directory. Do not assume identical runtime paths across all systemd versions; use the environment variables and paths provided by the service manager.

EnvironmentFile can be a simple option, though environment variables may appear in process inspection, diagnostic dumps, or management tools. For high-value secrets, prefer tightly restricted credential files or a secret agent.

## 8. Distributing Secrets in Docker and Kubernetes

### Docker Compose Secrets

Docker Compose can mount secrets as files inside containers:

```yaml
services:
  inventory:
    image: example/inventory:1.0
    secrets:
      - source: consul_acl_token
        target: discovery.consul.acl-token

secrets:
  consul_acl_token:
    file: ./runtime-secrets/consul_acl_token
```

Inside the container, the file can appear at `/run/secrets/discovery.consul.acl-token`. Configure Spring Boot to import the directory:

```yaml
spring:
  config:
    import: "configtree:/run/secrets/"
```

How Compose stores secrets depends on the deployment mode and runtime. Never commit the source file `runtime-secrets/consul_acl_token` to Git; protect the file on the host and control who has permission to deploy.

### Kubernetes Secret Volume

A Kubernetes Secret key can be mounted as a file:

```yaml
apiVersion: v1
kind: Secret
metadata:
  name: inventory-discovery-credentials
  namespace: shop
type: Opaque
stringData:
  discovery.consul.acl-token: REPLACE_AT_DEPLOY_TIME
---
apiVersion: apps/v1
kind: Deployment
metadata:
  name: inventory
  namespace: shop
spec:
  replicas: 2
  selector:
    matchLabels:
      app: inventory
  template:
    metadata:
      labels:
        app: inventory
    spec:
      containers:
        - name: inventory
          image: example/inventory:1.0
          volumeMounts:
            - name: discovery-secrets
              mountPath: /run/secrets
              readOnly: true
      volumes:
        - name: discovery-secrets
          secret:
            secretName: inventory-discovery-credentials
```

With the `discovery.consul.acl-token` key, Kubernetes creates the corresponding file in the mount directory; Spring Boot Config Tree can read the property of the same name. Example using a placeholder:

```yaml
spring:
  config:
    import: "configtree:/run/secrets/"
  cloud:
    consul:
      discovery:
        acl-token: ${discovery.consul.acl-token}
```

A Kubernetes Secret does not automatically mean data is encrypted safely everywhere. Enable encryption at rest for the datastore per cluster configuration, restrict RBAC, scope Secret read permissions by namespace/service account, protect backups, and control node access. Never put real values in committed manifests. Let pipelines or External Secrets/CSI integrations create Secrets from a secret manager.

## 9. Using Spring Cloud Vault or a Secret Manager

Spring Cloud Vault supports loading configuration from Vault via Spring Boot Config Data. Once the appropriate dependency and secure authentication are configured, applications can import secrets:

```yaml
spring:
  config:
    import: "vault://"
```

Vault paths, mounts, profiles, and property mappings must be configured according to your Spring Cloud Vault version and your organization's secret layout. The token used to authenticate to Vault is itself a secret; never store long-lived tokens in application.yml. Prefer workload identity, Kubernetes auth, AppRole, or an equivalent identity mechanism so workloads get least-privilege access.

If using AWS Secrets Manager, Azure Key Vault, or Google Secret Manager, choose an organization-supported integration. The principle remains the same: the application authenticates to the secret manager using workload identity, reads only the right secrets, limits lifetimes, and never prints values to logs.

Do not let the secret manager become an undesigned dependency. Define what happens when the secret manager is temporarily unreachable: whether running applications retain credentials in memory, whether new startups are blocked, how long cache TTL lasts, and what recovery mechanisms exist.

## 10. Separating Registration and Query Permissions

Providers and consumers have different permission requirements. Sharing one full-access credential means one bug or compromised workload can impact the entire registry.

| Role | Required Permissions | Permissions to Avoid |
|---|---|---|
| Provider | Register/update/deregister instances of owned services | Delete or modify another service's registrations |
| Consumer | Read required services and instances | Register fake services or modify the catalog |
| Health checker | Read/check endpoints as configured | Unrelated registry administrative permissions |
| Operator | Task-scoped administration and auditing | Using operator credentials as runtime credentials |
| CI/CD | Inject secrets/deploy within pipeline scope | Using long-lived runtime tokens across all build steps |

With Eureka, authorization is typically controlled at the server/proxy layer and via HTTP authentication; with Consul, via ACL policies/tokens; with ZooKeeper, via authentication and znode ACLs. The permission models differ, but the least-privilege principle is identical.

Also distinguish registry credentials from service-to-service identity. A token allowing a consumer to read Consul does not automatically prove the consumer is allowed to call a payment API. Business traffic still requires TLS, authentication/authorization, and dedicated policies.

## 11. Secret Rotation and Revocation

Secrets can leak, expire, or require policy-based replacement. Rotation should be planned to avoid disconnecting all providers/consumers from the registry at once.

General procedure:

1. Create a new credential with equal or narrower permissions than the old credential.
2. Store the new credential in the secret manager or secret source.
3. Distribute it to a small test group of providers/consumers.
4. Verify registration, heartbeats, and lookups work with the new credential.
5. Roll out gradually to remaining instances.
6. Confirm no clients still use the old credential.
7. Revoke the old credential.
8. Monitor authentication errors and audit logs after rotation.

Not all clients automatically reload credentials when mounted files change. Some integrations read configuration only at startup or construct HTTP clients once. When dynamic refresh is unsupported, perform a controlled rolling restart after the new secret is ready.

For short-lived tokens, handle refresh before expiration, clock synchronization, and errors when the secret manager is temporarily unreachable. Do not retry infinitely with a revoked token; distinguish authentication failures from network errors.

## 12. Protecting Secrets from Logs and Management Endpoints

Secrets can leak even when excluded from Git. Common leak sources include:

- Config logs or exceptions containing URLs with user-info.
- HTTP Authorization headers logged at DEBUG level.
- Actuator env/configprops exposing sensitive properties.
- Heap dumps, thread dumps, crash dumps, or diagnostic bundles.
- CI/CD echoing environment variables or enabling shell tracing.
- Container inspection, process arguments, or filesystem snapshots.
- Registry metadata or tags containing tokens.

Risk reduction measures:

- Never log secret values; log only property names and present/missing status.
- Mask URLs and Authorization headers in HTTP logging.
- Restrict Actuator endpoints; never expose env/configprops to public networks.
- Never use `set -x`, `echo $SECRET`, or commands printing secret variables in pipelines.
- Restrict access to heap dumps and backups.
- Use separate secrets per environment and workload.
- Have a revocation/rotation procedure when logs or artifacts are found to be exposed.

When debugging, you may log whether a token was loaded using a boolean or an irreversible fingerprint under an approved procedure; never print the raw token.

## 13. Troubleshooting

| Symptom | Possible Cause | Resolution |
|---|---|---|
| Spring Boot reports missing placeholder | Secret file not mounted or wrong property key | Check filename, mount path, and config import |
| Consul returns 403 | Valid token but missing policy | Check ACL policy and per-service permissions |
| Consul returns 401 | Missing, wrong, or expired token | Check secret source and rotation state |
| Eureka returns 401/403 | Credential or authorization mismatch | Check server security and HTTP client configuration |
| ZooKeeper reports AuthFailed | Wrong auth scheme/credential or ACL disallows | Check client auth and znode ACLs |
| Registry connection times out | DNS, routing, firewall, or TLS | Check networking before rotating credentials |
| New secret does not take effect | Client has not refreshed or reads only at startup | Verify reload mechanism; rolling restart if needed |
| Runs locally but fails in container | Different secret mount/path or file permissions | Check read-only mounts and container run user |
| Secret appears in logs | URL/header/config logged | Reduce logging, mask data, and rotate exposed secret |

Distinguish authentication errors from connectivity errors. HTTP 401/403 or ZooKeeper AuthFailed usually points to credential/authorization issues; timeouts and connection refused usually relate to DNS, routing, firewalls, ports, or server state. Do not repeatedly rotate tokens when the root cause is networking.

## 14. Pre-Deployment Checklist

1. Registry endpoint configuration and service names contain no secrets.
2. Secrets are stored outside source code, Git, and container images.
3. Spring Boot loads secrets from a protected runtime source.
4. Mandatory secrets are not accidentally configured as optional.
5. Providers and consumers have separate role-based credentials.
6. Tokens/ACLs grant only least-privilege permissions.
7. Eureka/ZooKeeper/Consul use the proper auth mechanism for their version.
8. TLS and trust material are managed separately; no private keys embedded in repositories.
9. Secrets never appear in logs, Actuator, metadata, or pipeline output.
10. Procedures exist for rotation, refresh, and revocation.
11. Fallback plans exist when the secret manager or config source is temporarily unreachable.
12. Real authentication is verified from each workload post-deploy.
13. Secret reads and policy changes are audited.
14. Procedures exist for handling compromised credentials.

Managing credentials through externalized secret configuration decouples registry access from source code and deployment artifacts. Spring Boot can load secrets from config trees, file mounts, or secret managers; provider-specific integrations turn those values into credentials for Consul, Eureka, or ZooKeeper. Effective security depends on least privilege, TLS, log protection, rotation, and revocation capability — not merely moving passwords out of application.yml.
