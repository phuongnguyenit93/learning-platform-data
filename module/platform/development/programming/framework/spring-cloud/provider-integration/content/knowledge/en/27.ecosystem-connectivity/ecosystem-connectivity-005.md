# Service Binding and Mapping Platform-Provided Connection Information

## 1. Context and Objectives

In the **Spring Cloud Provider Integration** module, Spring Boot applications connect to managed services from AWS, Azure, and Google Cloud via the corresponding Spring Cloud libraries, SDKs, and connectors. When deployed to Kubernetes, Cloud Foundry, or another application platform, an application typically does not create credentials or endpoints itself. The platform or a service broker provisions connection details and injects them into the workload through environment variables, secret volumes, binding directories, or platform metadata.

**Service binding** is the platform mechanism for attaching an application to a service instance and supplying the details needed to consume that service. Details may include host, port, database name, username, password, URI, certificate, topic, queue, resource identifier, or metadata. The application must map these values into Spring Boot configuration and initialize the corresponding clients.

**Spring Cloud Bindings** helps Spring applications consume service bindings following platform conventions such as the Kubernetes Service Binding Specification and Cloud Foundry `VCAP_SERVICES`. The library brings binding information into the Spring Environment for supported mappings. It does not provision services, grant IAM roles, or automatically turn every managed cloud service into a uniform connection.

In AWS, Azure, and Google Cloud environments, many services use workload identity instead of static usernames and passwords. For example, an application may receive a bucket/queue name from deployment configuration and then use an IAM role, Managed Identity, or Workload Identity to invoke APIs. Service binding provides endpoint/resource metadata; the identity provider authenticates access permissions. These two mechanisms complement each other.

After this lesson, you will be able to:

1. Explain service bindings, service instances, service brokers, and binding credentials.
2. Distinguish between the Kubernetes Service Binding Specification, Cloud Foundry `VCAP_SERVICES`, and standard environment/secret configuration.
3. Configure Spring Cloud Bindings to map binding data into Spring Boot.
4. Design binding directory structures, metadata, and secret files.
5. Map databases, messaging, storage, and endpoints across AWS, Azure, and Google Cloud.
6. Combine service bindings with workload identity and least privilege.
7. Manage property precedence, profiles, rotation, refresh, and binding errors.
8. Test bindings locally, in CI, on Kubernetes/Cloud Foundry staging, and against managed services.
9. Operate bindings securely with auditing, permissions, monitoring, and runbooks.

> **Scope:** Service binding is a contract between platform and application. Provisioning/binding capabilities, metadata formats, refresh, and identity depend on the platform, service broker, operator, and library version. Do not assume every AWS/Azure/GCP service has a standard binding provider or is automatically recognized by Spring Cloud Bindings.

## 2. What Problem Does Service Binding Solve?

### 2.1. Decoupling Provisioning from the Application

An application needs to connect to a managed PostgreSQL database. If hostnames, usernames, and passwords are hard-coded in YAML files, each environment requires source edits or custom image builds. When the platform provisions a database instance, it can generate a binding containing the endpoint and credentials, then attach that binding to the workload.

High-level workflow:

~~~mermaid
sequenceDiagram
    participant Dev as Developer / Operator
    participant Platform as Platform / Service Broker
    participant Service as Managed Service
    participant App as Spring Boot App

    Dev->>Platform: Provision service instance
    Platform->>Service: Create database / queue / storage
    Service-->>Platform: Resource endpoint and access details
    Dev->>Platform: Bind service to application
    Platform->>Platform: Create binding metadata / secret
    Platform->>App: Mount binding or inject environment
    App->>App: Map binding data to Spring properties
    App->>Service: Connect using credential or workload identity
~~~

The application image does not need to know the production database hostname. The platform is responsible for supplying connection information; the application is responsible for reading the contract, validating it, and using the right values.

### 2.2. Key Concepts

- **Service offering/catalog:** types of services a platform can provision, such as PostgreSQL, Redis, RabbitMQ, or object storage.
- **Service instance:** a provisioned resource, such as database `reservation-db-prod`.
- **Service broker/operator:** the component executing provision, bind, unbind, and potentially managing resource lifecycles.
- **Binding:** links an application/workload to a service instance.
- **Binding data/credentials:** endpoint, username, password, certificate, URI, or metadata provided to the workload.
- **Consumer application:** the application reading the binding and establishing client connections.
- **Unbind/deprovision:** detaching a binding or deleting the underlying resource per platform lifecycle; these two actions are not necessarily identical.

A service instance can have multiple bindings—for example, one database bound to several applications. Each binding can receive distinct credentials for easier revocation and auditing. Never share a single database admin credential across every workload.

### 2.3. Service Binding Is Not Service Discovery

Service discovery locates service/instance addresses at runtime, usually via DNS, registries, or control planes. Service binding typically provides a bundle of metadata/credentials attached to a specific workload or deployment.

The two concepts work together:

- Binding supplies hostname, port, database, and credentials.
- DNS/service discovery resolves the hostname to a network address.
- Workload identity supplies tokens or API permissions.
- The SDK/client uses the endpoint and credentials to connect.

Having only a hostname without authorization will still reject connections. Having a token with the wrong endpoint will likewise fail requests.

### 2.4. Service Binding vs. Spring Boot ServiceConnection

Spring Boot `@ServiceConnection` and Testcontainers help auto-configure connection details for services used in development/testing. This is a development/test lifecycle connection mechanism, not the Kubernetes Service Binding Specification or a Cloud Foundry service broker binding.

| Mechanism | Purpose | Information Source |
| --- | --- | --- |
| Platform service binding | Supplies connection details to deployed workloads | Service broker/operator/platform |
| Spring Cloud Bindings | Reads binding data and maps it into Spring Environment | Binding directory or `VCAP_SERVICES` |
| Spring Boot `@ServiceConnection` | Auto-creates connection details for dev/test services | Testcontainers or Docker Compose integration |
| Environment variables | Passes simple deployment settings | Container runtime/orchestrator |
| Config tree | Loads key-value files, commonly mounted secrets/configs | Filesystem mount |

Do not use `@ServiceConnection` to replace bindings in production. Conversely, there is no need to deploy a service broker just to run a PostgreSQL Testcontainer in unit/integration tests.

## 3. Common Service Binding Contracts

### 3.1. Kubernetes Service Binding Specification

The Kubernetes Service Binding Specification defines a standard filesystem representation of binding data so applications can read it uniformly. A service binding is usually mounted as a subdirectory under a binding root. The `SERVICE_BINDING_ROOT` environment variable points to that root path.

Example structure:

~~~text
/bindings/
  reservation-db/
    type
    provider
    name
    host
    port
    database
    username
    password
    ca.crt
  reservation-cache/
    type
    provider
    name
    uri
    host
    port
~~~

Each file typically holds a single value. Identifying metadata may include `type`, `provider`, `name`, `version`, `tags`, or other fields depending on the specification/provider. Connection details such as host, port, username, password, or certificates reside in separate files.

In Kubernetes, a Service Binding Operator or compatible component can generate bindings from resources/services and mount secrets into pods. CRD declarations, secret naming, and operator behavior depend on the implementation; do not assume every cluster has an operator installed.

Example deployment receiving a binding root:

~~~yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: reservation-service
spec:
  template:
    spec:
      containers:
        - name: app
          image: example/reservation-service:1.0
          env:
            - name: SERVICE_BINDING_ROOT
              value: /bindings
          volumeMounts:
            - name: service-bindings
              mountPath: /bindings
              readOnly: true
      volumes:
        - name: service-bindings
          projected:
            sources:
              - secret:
                  name: reservation-db-binding
                  items:
                    - key: type
                      path: reservation-db/type
                    - key: host
                      path: reservation-db/host
                    - key: port
                      path: reservation-db/port
                    - key: username
                      path: reservation-db/username
                    - key: password
                      path: reservation-db/password
~~~

This example illustrates volume projection. With a real operator, binding resources and mounts are normally managed by the operator; you do not necessarily author projected volumes manually like this. Secrets must be mounted read-only and only into containers that need them.

### 3.2. Cloud Foundry VCAP_SERVICES

Cloud Foundry supplies binding data in the `VCAP_SERVICES` environment variable, typically JSON grouped by service label. Illustrative structure:

~~~json
{
  "postgresql": [
    {
      "name": "reservation-db",
      "label": "postgresql",
      "tags": ["relational", "database"],
      "plan": "standard",
      "credentials": {
        "hostname": "db.internal",
        "port": 5432,
        "database": "reservation",
        "username": "reservation_app",
        "password": "injected-at-runtime"
      }
    }
  ],
  "redis": [
    {
      "name": "reservation-cache",
      "label": "redis",
      "credentials": {
        "uri": "rediss://cache.internal:6379"
      }
    }
  ]
}
~~~

The platform generates this JSON when binding services to an application. Applications should never bake `VCAP_SERVICES` into images or commit JSON containing credentials into repositories. Local development can use mock fixtures with test credentials.

Cloud Foundry may also provide `VCAP_APPLICATION` containing application/instance metadata. This is runtime metadata, does not replace `VCAP_SERVICES`, and is not a place for arbitrary secrets.

### 3.3. Binding Directories and Config Trees Are Not Identical

Spring Boot ConfigData supports `configtree:` to load a directory of key-value files as a property source. Example:

~~~yaml
spring:
  config:
    import: optional:configtree:/run/secrets/
~~~

This mechanism fits flat mounted secret/config directories. A Kubernetes Service Binding directory normally holds multiple binding subdirectories with `type/provider/name` metadata; importing a binding root merely as a config tree does not automatically produce semantic mappings for each binding.

Use Spring Cloud Bindings when reading a service binding contract. Use ConfigTree when the platform mounts config/secret files using key-value conventions defined by the application. Both mechanisms can coexist if each source has clear ownership and precedence.

### 3.4. Binding Data Should Have Structure and Metadata

A well-formed binding tells the consumer:

- Which service type the binding belongs to (`postgresql`, `redis`, `rabbitmq`, `s3`, ...).
- Which provider or platform created the binding.
- The service instance name or logical resource.
- Endpoint and protocol.
- Credentials or how to obtain credentials.
- Certificate/trust material if TLS is required.
- Version/plan/tags if the application selects behavior accordingly.
- Expiration/rotation reference if provided by the platform.

Do not infer the service type purely from directory names or `name`. Two similarly named services could be a database and a cache; rely on `type`/metadata per the contract.

## 4. Spring Cloud Bindings in Spring Boot Applications

### 4.1. What Does the Library Do?

Spring Cloud Bindings provides auto-configuration to read platform-supplied bindings and create corresponding Spring Boot properties. For supported service types and formats, the library maps binding data into configurations understood by the Spring ecosystem, such as datasources or messaging connections.

High-level flow:

1. Application starts and detects the binding root or platform environment.
2. Library reads binding directories/metadata.
3. Binding type/provider is identified.
4. Connection details are converted into property sources.
5. Spring Boot auto-configuration uses those properties to create datasources/clients.
6. Application uses the configured beans to access managed services.

Spring Cloud Bindings does not provision resources, does not assign IAM policies, and does not guarantee built-in mappers for every custom service type. If a service is unrecognized or default mappings do not fit, configure manually or write a dedicated integration adapter.

### 4.2. Dependencies and Compatibility

Maven dependency typically looks like:

~~~xml
<dependency>
    <groupId>org.springframework.cloud</groupId>
    <artifactId>spring-cloud-bindings</artifactId>
</dependency>
~~~

Manage versions via the Spring Cloud BOM compatible with your Spring Boot version. Check release notes to confirm support for the binding specification, Cloud Foundry, service mappers, and property behavior. Do not pick the latest version independently of the release train.

An application only needs Spring Cloud Bindings when the platform actually provides service bindings matching a contract supported by the library. If the application merely receives a few environment variables, `@ConfigurationProperties` can be simpler and easier to control.

### 4.3. Binding Typed Properties After Bindings Load

Example application service using a Spring Boot datasource:

~~~java
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Repository;

@Repository
public class ReservationRepository {

    private final JdbcTemplate jdbcTemplate;

    public ReservationRepository(JdbcTemplate jdbcTemplate) {
        this.jdbcTemplate = jdbcTemplate;
    }

    public int countReservations() {
        return jdbcTemplate.queryForObject(
                "select count(*) from reservations",
                Integer.class);
    }
}
~~~

If a binding mapper supplies datasource properties recognized by Spring Boot, auto-configuration can create `DataSource` and `JdbcTemplate`. The application repository does not need to read binding files or parse platform JSON.

Example typed config for custom resource metadata:

~~~java
import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.validation.annotation.Validated;
import jakarta.validation.constraints.NotBlank;

@Validated
@ConfigurationProperties(prefix = "app.storage")
public record StorageBindingProperties(
        @NotBlank String bucket,
        @NotBlank String region,
        String endpoint) {
}
~~~

Register with `@ConfigurationPropertiesScan` or `@EnableConfigurationProperties`. For credentials, do not store passwords in custom property objects if the SDK can use workload identity/default credential providers.

### 4.4. Verifying Bindings at Startup

Never log the entire binding object. You can log non-sensitive attributes such as binding type, logical service name, provider, and resolved status; mask endpoints if topology is restricted. Inspect property bindings via actuator on a protected management plane, without exposing secret values.

If the app starts and cannot find a binding, make an explicit decision:
- Required service: fail startup with a clear error.
- Optional service: disable the feature or use a configured local/test implementation.
- Never fall back to hard-coded production hostnames/passwords.
- Never synthesize dummy credentials or broaden permissions just to "make the app run".

### 4.5. Binding Types and Mappers

Spring Cloud Bindings may support mappings for several common services depending on version. Verify the type/tag/metadata conventions recognized by each mapper. Do not assume `type` must be a vendor or SDK name. For instance, `postgresql` describes the service type; `provider` may indicate the broker/platform creating the binding.

If a binding has an unsupported type, the app can still read the raw binding via a custom integration, taking responsibility for parsing, validation, property generation, and secret protection. Never alter binding secrets on the filesystem just to trick a mapper into recognizing them.
## 5. Mapping Bindings into Spring Boot Properties

### 5.1. From Binding Data to Connection Properties

Service bindings usually hold data in a framework-neutral form. Spring Boot auto-configuration, however, expects specific properties to construct clients. The mapping layer translates between these two models.

For example, a database binding might contain:

~~~text
type=postgresql
host=db.internal
port=5432
database=reservation
username=reservation_app
password=<secret>
~~~

The application may need datasource properties:

~~~yaml
spring:
  datasource:
    url: jdbc:postgresql://db.internal:5432/reservation
    username: reservation_app
    password: <resolved-secret>
~~~

The password value must be read from the secret file/secret store at runtime. Never put literal placeholders or real passwords in source code. If the binding supplies a complete URI, the mapper can use it per contract; still verify TLS options, database name, and encoding.

### 5.2. Database Mapping

| Binding Data | Spring Boot Property / Connection Detail |
| --- | --- |
| host, port, database | Construct JDBC URL or R2DBC URL |
| username | `spring.datasource.username` |
| password | `spring.datasource.password` |
| URI/JDBC URL | `spring.datasource.url` |
| TLS CA/certificate | SSL/truststore properties or client configuration |
| pool size/timeout | Hikari/R2DBC pool settings per application policy |

Do not assume every mapper constructs a valid JDBC URL for every database driver. Verify scheme, SSL mode, timezone, query parameters, and driver dependencies. For R2DBC, use the corresponding property prefix and driver instead of reusing a JDBC URL.

Example application code injecting only the datasource:

~~~java
import javax.sql.DataSource;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
class DatabaseAccessConfiguration {

    @Bean
    JdbcTemplate jdbcTemplate(DataSource dataSource) {
        return new JdbcTemplate(dataSource);
    }
}
~~~

The application does not need to parse binding directories in repositories or controllers. Keep mapping at the startup/configuration boundary so domain/application code stays independent of platform contracts.

### 5.3. Messaging Mapping

Bindings for RabbitMQ/Kafka may contain broker host, port, vhost, username, password, TLS certificates, or bootstrap servers. Required properties depend on the binder:

- Rabbit binder: addresses, virtual host, username/password, SSL, and queue/exchange options.
- Kafka binder: bootstrap servers, security protocol, SASL mechanism, truststore, and topic/group configs.
- Cloud-native messaging: project/namespace, topic/queue/subscription, and identity provider.

Do not use a generic property like `uri` assuming every binder interprets it identically. When multiple brokers exist, identify each binding by type/name/provider and attach it explicitly to the intended destination/binder.

### 5.4. Object Storage Mapping

Spring Cloud Bindings may lack default mappers for every provider's buckets/containers. A custom binding can supply non-sensitive metadata:

~~~text
type=object-storage
provider=aws
bucket=rental-documents-prod
region=ap-southeast-1
~~~

The application binds metadata into a dedicated type:

~~~java
@ConfigurationProperties(prefix = "app.storage")
public record ObjectStorageProperties(
        String provider,
        String bucket,
        String region,
        String endpoint) {
}
~~~

The AWS SDK client uses the runtime credential provider chain; bucket and Region are resource configuration. There is no need to place access keys/secret keys into bindings when the workload already has an IAM role.

### 5.5. Custom Binding Mappers

When a service type is not supported by Spring Cloud Bindings, build a small integration adapter:

1. Read the binding root from the environment per platform contract.
2. Iterate through binding directories and parse metadata.
3. Select bindings explicitly by type/provider/name.
4. Validate required keys, URI schemes, port ranges, and certificates.
5. Convert to typed properties or a property source.
6. Construct clients via Spring configuration beans.
7. Mask secrets in exceptions/logs and never write credentials to disk.

Never write custom mappers inside business controllers/services. Never blindly pick the first binding when multiple bindings share the same type; use logical names or explicit selection to avoid connecting to the wrong service.

### 5.6. Simple Custom Binding Reader Example

The snippet below reads a binding directory by configured name. It does not replace Spring Cloud Bindings' full parser/spec validation:

~~~java
import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.Optional;

public final class BindingFiles {

    private final Path root;

    public BindingFiles(Path root) {
        this.root = root;
    }

    public Optional<String> read(
            String bindingName, String key) throws IOException {
        Path file = root.resolve(bindingName).resolve(key).normalize();

        if (!file.startsWith(root.normalize()) || !Files.isRegularFile(file)) {
            return Optional.empty();
        }

        return Optional.of(Files.readString(file).trim());
    }
}
~~~

In production, canonicalize root/paths and guard against symlinks to prevent path traversal. Allow binding names/keys only from a trusted configuration allow-list; never accept arbitrary paths from HTTP requests. Read secret files only when needed and never retain secret contents in debug messages.

## 6. Combining Service Binding with AWS

### 6.1. AWS Does Not Have One Unified Service Binding Contract for All Services

AWS managed services are typically accessed via AWS APIs and AWS SDKs. Credentials usually come from IAM roles/credential provider chains. Depending on the runtime, workloads may use ECS task roles, EKS Pod Identity/IRSA, or EC2 instance profiles.

Binding/platform metadata can supply:
- Region.
- Resource identifiers such as bucket, queue URL, topic ARN, or database endpoint.
- Database name and connection options.
- Secret ARN/reference if the service uses passwords.
- Endpoint overrides for local/test or private endpoints.

It should not contain static AWS access keys when runtime identity can grant permissions directly.

### 6.2. RDS/Aurora Databases

For RDS/Aurora using username/password, bindings can provide endpoint, port, database, username, and secret reference/password. Mappers construct the JDBC URL and datasource properties. The workload role needs permission to read the secret/KMS if passwords live in Secrets Manager.

When using IAM database authentication, the application must generate short-lived auth tokens via the AWS SDK; tokens are not static passwords to store long-term in bindings. Datasources/connection pools must support acquiring fresh tokens when opening new connections. Verify driver, token lifecycle, and pool integration.

### 6.3. S3 Object Storage

Bindings for S3 should provide bucket and Region; endpoint overrides are used only when needed. The AWS SDK uses the workload's role to sign requests. Policies should restrict buckets/prefixes and operations such as GetObject/PutObject. Do not put access keys/secret keys into binding files when an IAM role is present.

### 6.4. SQS, SNS, and EventBridge

Bindings can provide queue URL/name, topic ARN, event bus name, and Region. Applications use AWSpring or AWS SDK v2. Roles need only SendMessage/ReceiveMessage/DeleteMessage, Publish, or PutEvents permissions respectively. Even if a binding contains a queue URL, still validate account/Region and permissions; a URL is not a credential.

EventBridge PutEvents can return per-entry errors; adapters must check for partial failures. Never treat a successful HTTP response as proof that every event was published.

### 6.5. EKS and Kubernetes Bindings

When running on EKS, the Kubernetes Service Binding Operator or Secret volumes can inject resource metadata into pods. AWS workload identity remains the authentication layer. Service binding does not automatically create IAM role associations or grant S3/SQS permissions. Configure ServiceAccounts, Pod Identity/IRSA, and IAM policies independently of binding directories.
## 7. Combining Service Binding with Azure

### 7.1. Azure Managed Services and Identity

Azure workloads can use Managed Identity on Azure-hosted compute or Workload Identity when running on AKS. Service bindings can supply endpoints, namespaces, databases, containers, or resource identifiers; `DefaultAzureCredential`/credential providers fetch tokens from the runtime identity.

If a provider/platform generates a binding containing a connection string with a SAS key/password, treat it as a secret. For services supporting Entra ID authentication, prefer identity-based auth where appropriate with scoped role assignments.

### 7.2. Azure Database for PostgreSQL

Bindings can supply hostname, port, database, username, and password, or strictly the connection endpoint when using Entra ID authentication. Spring datasources take JDBC URL/username/password per driver. When using Entra ID tokens, you need a mechanism to acquire and refresh tokens when creating new connections; do not treat access tokens as long-lived passwords.

### 7.3. Blob Storage

Bindings should provide account endpoint and container name. Managed Identity needs the appropriate data-plane role such as blob read/write scoped to the container/account. The Azure SDK uses the credential provider; no account key needs to be stored when the identity is authorized.

### 7.4. Service Bus and Event Hubs

Bindings can supply namespace endpoint, queue/topic or event hub name, and consumer group. Managed Identity needs sender/receiver or matching roles on the entity/namespace. If using SAS connection strings, protect them as secrets and maintain a rotation procedure. Event Hubs partition/checkpoint semantics remain governed by the service; bindings only carry metadata/connection details.

### 7.5. AKS and Secret Store CSI

In AKS, binding directories can be created from Kubernetes Secrets or compatible operators. The Secret Store CSI Driver with the Azure provider can mount secrets from Key Vault. These are two different ways to supply file/runtime secrets; choose based on platform contracts and lifecycles. Do not assume a CSI mount automatically produces the Service Binding Specification structure without an adapter/operator converting it.

## 8. Combining Service Binding with Google Cloud

### 8.1. GCP Workload Identity and Resource Metadata

On GKE, use Workload Identity Federation for GKE; on Cloud Run, attach a service identity to the service. Service bindings or deployment configurations can supply project ID, bucket, topic, subscription, database instance connection name, and endpoints. ADC/Google credential providers obtain credentials from the workload identity.

Bindings should not contain service account JSON keys when workload identity is configured. IAM roles must be scoped by resource and operation.

### 8.2. Cloud SQL

Bindings can supply instance connection name, database, username, and secret references. With the Cloud SQL connector/auth proxy, applications need the instance identifier and an identity permitted to connect; database users/authentication are a separate layer. When using direct TCP host/port, secure the network path, TLS, and credentials.

Do not confuse Cloud SQL Client permission with database login permission. An identity may be allowed to open a connection while still needing a valid database user or IAM database authentication.

### 8.3. Cloud Storage

Bindings can supply bucket name/project ID. Workload identity needs minimal data-plane permissions on the bucket. The Google Cloud Storage client uses ADC; do not store service account keys in bindings. Endpoint overrides are strictly for emulators/tests or special environments.

### 8.4. Pub/Sub

Bindings can supply project ID, topic, and subscription. Publishers need publish permission on the topic; subscribers need consume permission on the subscription. Workload identity supplies tokens. Ack deadlines, ordering keys, retries, and dead-letter policies belong to subscription configuration; do not infer them from binding names.

### 8.5. GKE Secret Volumes and Secret Manager CSI

GKE can mount Kubernetes Secrets or integrate Secret Manager via CSI/providers. A Service Binding Specification directory must still match the contract if the application uses Spring Cloud Bindings. A single secret file mounted into `/var/secrets` does not automatically become a binding with type/name/metadata.

## 9. Mapping Matrix by Service Type and Provider

| Service Type | Possible Binding Data Needed | Spring Integration / Consumer |
| --- | --- | --- |
| PostgreSQL | host, port, database, username, password/secret ref, TLS | Spring Boot JDBC/R2DBC |
| Redis | host, port, username/password, TLS, database index | Spring Data Redis |
| RabbitMQ | host, port, vhost, username/password, TLS | Spring AMQP / Rabbit binder |
| Kafka | bootstrap servers, security protocol, SASL/TLS, topic metadata | Spring Cloud Stream Kafka binder |
| AWS S3 | bucket, Region, endpoint if needed | AWS SDK v2/AWSpring |
| AWS SQS/SNS | queue URL/topic ARN, Region | AWSpring/AWS SDK |
| Azure Blob | account endpoint, container | Azure Storage SDK |
| Azure Service Bus | namespace, queue/topic, subscription | Azure SDK/Spring Cloud Azure |
| GCP Cloud Storage | project, bucket | Google Cloud Storage client |
| GCP Pub/Sub | project, topic, subscription | Google Cloud Pub/Sub integration |

This table describes data an application might need; it is not a promise that Spring Cloud Bindings automatically maps every service type. Built-in mappers and property names must be verified for your library version. For API-based managed services, endpoint/resource metadata and workload identity are usually sufficient; do not invent usernames/passwords if the provider does not use that model.

## 10. Property Precedence and Binding Selection

A pod may simultaneously receive:
- A binding directory mounted by the platform.
- Environment variables from the Deployment.
- `application.yaml` inside the image.
- ConfigData from Config Server or a provider store.
- Separately mounted secret/config trees.

If the same property appears in multiple sources, the winner depends on property source ordering and the binding library. Never assume Spring Cloud Bindings always overrides environment variables or vice versa.

Recommended conventions:

1. Each property has one source of truth.
2. Binding names are selected explicitly if multiple services share the same type.
3. Environment overrides are allowed only for approved keys.
4. Secrets come strictly from the designated secret source; never fall back to empty defaults.
5. Provider resource identifiers are validated against environment/account/project.
6. At startup, log non-sensitive source/type/version details for diagnostics.

Never put a binding password into `application.yaml` expecting the platform to override it cleanly without testing. Use a test context to prove property source precedence for your exact Spring Cloud Bindings/Spring Boot release.
## 11. Lifecycle, Rotation, and Refresh

### 11.1. When Are Bindings Read?

Many integrations read bindings at startup to build Spring property sources and connection beans. If the platform updates a Secret or binding directory afterward, the application does not necessarily re-read it automatically. Behavior depends on filesystem mounts, the platform, and the library.

Classification:
- **Startup-only:** endpoint, driver, database name, TLS truststore, or client configuration.
- **Rotatable secrets:** passwords, tokens, certificates that may change while the app runs.
- **Dynamic metadata:** feature/routing settings designed to be refreshed.
- **Deployment changes:** new bindings or new resources requiring rollout/restart.

Never assume Spring Cloud Bindings automatically refreshes every datasource/client when files change.

### 11.2. Kubernetes Secret Updates

Kubernetes projected Secret volumes may update after a propagation delay; mounts using `subPath` may not receive standard projected volume updates at all. The application must know whether file updates are observed and whether clients reload. A simple, controllable approach is rolling out pods when credential bindings change.

Never rely on environment variables hoping secrets update dynamically inside a running process; process environments are fixed when containers start.

### 11.3. Cloud Foundry Binding Lifecycle

Cloud Foundry service binding credentials can change when a service instance/binding is updated. Applications require restaging/restarting or a platform-supported refresh mechanism to pick up new values. Verify service broker and platform behavior; never assume running `VCAP_SERVICES` mutates inside a live process.

### 11.4. Safe Rotation

Rotation workflows must coordinate the provider and application:

1. Create a new credential/version or trigger provider rotation.
2. Update the binding/secret reference.
3. Provide an overlap window if the service supports dual concurrent credentials.
4. Restart/refresh workloads per lifecycle.
5. Verify connection pools/clients are using the new credential.
6. Revoke the old credential after all instances switch over.
7. Monitor auth failures and maintain a rollback plan.

With IAM/Managed Identity/Workload Identity, rotation is normally handled by token providers/runtimes. Never cache access tokens indefinitely; use SDK credential providers that refresh automatically.

## 12. Securing Service Bindings

### 12.1. Binding Credentials Are Secrets

Bindings can hold passwords, access tokens, private keys, SAS connection strings, or certificate private material. Treat the entire binding directory as sensitive data until each field is classified.

- Never commit binding fixtures containing real secrets.
- Never bake credentials into container images.
- Never print environments, binding JSON, or full files to logs.
- Never expose bindings via actuator, debug endpoints, or support bundles.
- Mask secrets in exceptions and diagnostic output.
- Never place credentials in metric labels, trace baggage, or message headers.

Resource names, buckets, hosts, and project IDs may not be secrets, yet can still expose internal topology. Log them only when permitted by policy.

### 12.2. Least Privilege on the Platform

Bind workloads only to the services they need. In Kubernetes, RBAC restricts who can read Secrets; service accounts need only required permissions. Never mount every secret in a namespace into every pod. In Cloud Foundry, bind only required service instances and use per-application credentials when supported by the broker.

When a service broker generates binding credentials, verify:
- Are credentials scoped to the application/service instance?
- Does unbinding revoke the credentials?
- Can credentials be rotated/revoked individually?
- Does auditing record who created, read, or deleted bindings?
- Are secrets encrypted at rest and transmitted over TLS?

### 12.3. Kubernetes Secrets and Filesystem Permissions

Kubernetes Secret volumes are usually mounted with appropriate permissions, yet Base64 encoding in manifests is not encryption. Enable encryption at rest for etcd, restrict RBAC, use external secret providers where appropriate, and mount read-only.

Do not mount bindings into sidecar containers that do not need credentials. Choose `defaultMode`/file permissions matching the process UID/GID; avoid overly broad modes like 0777. Never copy secrets to writable `/tmp` or image layers.

### 12.4. Cloud Identity Is a Separate Authorization Layer

Service binding does not replace IAM/RBAC:

- AWS: IAM roles/policies for API operations and resource ARNs.
- Azure: Managed Identity/Workload Identity and Azure RBAC/data-plane roles.
- Google Cloud: service accounts/workload identity principals and IAM roles.
- Kubernetes: service accounts, RBAC, and network policies.
- Cloud Foundry: service broker credentials and platform isolation.

An endpoint/queue name does not prove an application has access rights. Credentials inside bindings must also be protected by scope and rotation policies.

### 12.5. TLS and Certificates

If a binding provides a CA certificate/client certificate, configure the client truststore/SSL properly. Verify hostnames, certificate chains, expiration, and rotation. Never disable hostname verification or trust all certificates to work around errors. Private keys must be read from secret mounts, never placed in source control.
## 13. Testing Service Bindings

### 13.1. Binding Directory Fixtures

Create test fixtures containing no real secrets:

~~~text
src/test/resources/bindings/
  reservation-db/
    type
    provider
    name
    host
    port
    database
    username
    password
~~~

Example test file:

~~~text
type=postgresql
provider=test
name=reservation-db
host=localhost
port=5432
database=reservation_test
username=test_user
password=test_password_only
~~~

Configure the test environment to point the binding root to the fixture in the manner supported by your library/version. Never mount this fixture in production images. Tests should verify resulting datasource property mappings and failures when required keys are missing.

### 13.2. Testing Cloud Foundry VCAP_SERVICES

Use JSON fixtures with fake credentials. Verify:
- Parser reads the right service label/name.
- Multiple services sharing a label are selected per policy.
- Missing credentials produce clear errors.
- Malformed JSON does not cause the app to fall back to production endpoints.
- Secrets never appear in logs/test reports.

Never place `VCAP_SERVICES` fixtures in the global developer environment; scope them to the test process.

### 13.3. Testing the Spring Context

You can use `ApplicationContextRunner` or `@SpringBootTest` with test property sources to verify typed configuration and auto-configuration. For datasources, Testcontainers can provide PostgreSQL/Rabbit/Kafka to test real connections in CI. Testing the binding parser and testing network connections are two separate layers.

Useful assertions:
1. Binding type/name/provider are recognized.
2. Datasource URL/username are constructed properly; password is verified without printing it.
3. Connection pool initializes cleanly.
4. Optional bindings disable features according to policy.
5. Missing or mismatched required bindings fail startup.
6. Environment overrides happen only for permitted keys.
7. Multiple bindings of the same type do not connect to the wrong resource.

### 13.4. Platform Contract Tests

Staging tests should verify that the real operator/service broker produces the expected contract:
- `SERVICE_BINDING_ROOT` is set.
- Directory/metadata/secret keys conform to spec.
- Volume mounts are read-only with appropriate file permissions.
- Workload identity has permissions to the managed service.
- Rotation/restart/unbind behave as designed.
- Service endpoints are reachable across network policies/private endpoints.
- Auditing and secret masking are active.

Emulators/mocks do not prove platform brokers, IAM, RBAC, network policies, or secret rotation. Keep at least one staging contract test for each critical platform/service integration.

## 14. Observability and Troubleshooting

### 14.1. Safe Logging

Safe to log:
- Binding type and logical name.
- Provider/platform name.
- Required/optional and resolved/unresolved status.
- Masked endpoint class/protocol if needed.
- Client initialization success/failure and error category.

Never log:
- Passwords/tokens/SAS strings.
- Private keys/certificate private material.
- Full `VCAP_SERVICES`.
- Contents of binding files.
- Full Environment or Spring Environment dumps.

### 14.2. Metrics to Monitor

| Metric | Purpose |
| --- | --- |
| Binding discovery success/failure | Whether the platform supplies bindings properly |
| Binding parse/validation errors | Contract/metadata mismatches |
| Client initialization failures | Invalid endpoints/credentials/TLS |
| Connection pool active/idle/pending | Database capacity and connection issues |
| Auth failures by provider | IAM/RBAC/credential rotation issues |
| Binding age/version | Stale credentials or metadata |
| Secret refresh/restart count | Rotation and rollout frequency |
| Downstream latency/error rate | Managed service health |

Do not use user-supplied binding names, secret versions, or arbitrary tenant IDs as metric labels if they can cause unbounded cardinality.

### 14.3. Common Issues

| Symptom | Possible Cause | Resolution |
| --- | --- | --- |
| Binding root not found | Missing `SERVICE_BINDING_ROOT` or bad volume mount | Check pod env, mount path, and operator status |
| Binding directory unrecognized | Missing metadata/type files or invalid contract | Check spec and mapper version |
| Multiple bindings of same type | Mapper picked wrong binding | Select logical name explicitly |
| Wrong datasource URL | Incorrect host/port/database mapping or incompatible driver | Validate URI and driver |
| AccessDenied despite valid binding | Missing IAM/RBAC or wrong identity | Check workload identity and resource scope |
| TLS handshake fails | Wrong CA/truststore/hostname | Check certificate chain and endpoint |
| New secret not applied | App reads only at startup or mount did not update | Restart/refresh per lifecycle |
| Cloud Foundry misses new credentials | App not restaged/restarted or broker not updated | Check binding lifecycle and platform |
| App works locally but fails on cluster | Local fixture differs from real contract/permissions | Run staging contract tests |
| Secret appears in logs | Dumping binding/environment/exceptions | Mask output, rotate credentials, and fix diagnostics |

### 14.4. Runbook When a Binding Fails

1. Verify the service instance is provisioned and healthy.
2. Verify the binding is attached to the right application/workload.
3. Check the environment root and directory mount.
4. Verify metadata files, type, provider, and required keys.
5. Check file read permissions and process UID/GID.
6. Verify endpoint DNS/networking/private links.
7. Verify workload identity and IAM/RBAC independently.
8. Check TLS, certificates, and clock skew.
9. Verify Spring property mapping and precedence.
10. Log only key names/status; never dump secrets to debug.

## 15. Workflow for Introducing Service Binding into an Application

When moving from hard-coded config to platform bindings, follow this sequence:

1. Identify service instances and applications/workloads to bind.
2. Choose the platform-supported contract: Kubernetes Service Binding Specification, Cloud Foundry, or a provider-specific mechanism.
3. List metadata/credentials the application actually needs; separate resource identifiers from secrets.
4. Pick explicit binding names/types if multiple services of the same kind exist.
5. Configure the operator/service broker, volumes/environment, and minimal permissions.
6. Add Spring Cloud Bindings or a custom adapter matching the platform contract.
7. Bind metadata into typed configuration and validate at startup.
8. Configure SDK credential providers/workload identity independently of resource metadata.
9. Test local fixtures, CI integration, and staging contracts.
10. Design rotation, restart/refresh, unbind, and rollback.
11. Deploy to canary; verify the app uses the expected resources and identities.
12. Revoke legacy credentials or delete old bindings once workloads have migrated.

Do not bundle every secret into one shared binding if an application only needs a subset. Each workload should receive strictly its own services and credential scope.

## 16. Production Readiness Checklist

1. **Contract:** exact Service Binding Specification, Cloud Foundry, or provider-specific format defined.
2. **Binding selection:** service type/name/provider chosen explicitly, independent of directory order.
3. **Mapping:** properties/URIs validated; JDBC/R2DBC, broker, and SDK configs match protocols.
4. **Identity:** workload identity/IAM/RBAC configured independently of binding metadata.
5. **Least privilege:** workloads read only their bindings and access only required services.
6. **Secret handling:** binding credentials absent from Git, images, logs, metrics, and support bundles.
7. **Filesystem:** read-only mounts, proper file permissions, path traversal prevented.
8. **Precedence:** source of truth and override policies explicit and tested.
9. **Lifecycle:** clear whether bindings are read at startup or refreshed; restart/rollout strategy in place.
10. **Rotation:** new credentials verified before revoking old credentials.
11. **Network/TLS:** DNS, private endpoints, firewalls, and certificates verified.
12. **Testing:** fixtures, context tests, broker/database integration, and staging contract tests.
13. **Observability:** metrics for binding discovery, mapping errors, client init, auth failures, and binding age.
14. **Recovery:** runbooks for bind/unbind, secret rotation, and provider outages.
15. **Compatibility:** Spring Boot, Spring Cloud Bindings, and provider integrations on a compatible release train.

## 17. Practice Exercises

1. Draw a sequence diagram from provisioning a PostgreSQL service instance to Spring Boot injecting `JdbcTemplate`.
2. Create a Kubernetes Service Binding directory fixture and explain the roles of type, provider, name, host, port, and password.
3. Compare binding directories with Cloud Foundry `VCAP_SERVICES` and Spring Boot config trees.
4. Add Spring Cloud Bindings to a Spring Boot application; verify the datasource is configured from the binding fixture.
5. Create two PostgreSQL bindings of the same type; design how to select the intended service by logical name.
6. Write a custom reader for an object storage binding containing provider, bucket, and Region; validate required keys.
7. Deploy an app on EKS: binding supplies bucket/queue metadata, IAM role supplies permissions; prove the two layers are independent.
8. Deploy an app on AKS: binding supplies Blob endpoint/container, Managed Identity supplies data-plane permissions.
9. Deploy an app on GKE: binding supplies Pub/Sub topic/subscription, Workload Identity supplies publish/consume permissions.
10. Simulate secret rotation while a pod is running; determine when a restart is needed and how to verify the connection pool uses the new credential.
11. Write tests for missing bindings, malformed metadata, permission denied, and multiple bindings of the same type.
12. Write a runbook for when a binding directory exists yet the application receives `AccessDenied` from the managed service.

**Completion criteria:** learners can describe the platform's service binding contract, map binding data into Spring Boot, distinguish resource metadata from identity/secrets, connect at least one managed service via binding, test lifecycle behavior, and safely handle rotation/unbinding.

## References

- [Kubernetes Service Binding Specification](https://servicebinding.io/spec/core/1.0.0/): binding directory, metadata, and environment contract.
- [Kubernetes Service Binding Operator](https://github.com/redhat-developer/service-binding-operator): operator implementing service binding on Kubernetes.
- [Spring Cloud Bindings](https://github.com/spring-cloud/spring-cloud-bindings): support for Spring applications reading platform service bindings.
- [Cloud Foundry VCAP_SERVICES](https://docs.cloudfoundry.org/devguide/deploy-apps/environment-variable.html#VCAP-SERVICES): service binding environment structure.
- [Spring Boot Externalized Configuration](https://docs.spring.io/spring-boot/reference/features/external-config.html): property sources, environment, and config trees.
- [Spring Boot Service Connections](https://docs.spring.io/spring-boot/reference/features/dev-services.html): connection details for development/test services.
- [AWS SDK for Java 2.x — Default credentials provider chain](https://docs.aws.amazon.com/sdk-for-java/latest/developer-guide/credentials-chain.html): credential resolution for workloads.
- [Amazon EKS Pod Identity](https://docs.aws.amazon.com/eks/latest/userguide/pod-identities.html): associating IAM roles with Kubernetes workloads.
- [Azure Workload Identity for AKS](https://learn.microsoft.com/azure/aks/workload-identity-overview): workload authentication on AKS.
- [Azure DefaultAzureCredential](https://learn.microsoft.com/java/api/com.azure.identity.defaultazurecredential): credential chain for the Azure SDK.
- [Google Cloud Workload Identity Federation for GKE](https://cloud.google.com/kubernetes-engine/docs/how-to/workload-identity): workload identity on GKE.
- [Google Cloud Secret Manager](https://cloud.google.com/secret-manager/docs/overview): secret versions and access control.
