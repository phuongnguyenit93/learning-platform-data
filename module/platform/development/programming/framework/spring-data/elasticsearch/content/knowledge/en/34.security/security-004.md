# Managing Connection Secrets with Environment Configuration

A Spring Data Elasticsearch application typically needs several details to connect to a cluster: node addresses, username, password or API key, CA certificate, and TLS options. Values like host and timeout are operational configuration; passwords, API keys, and private keys are secrets. Writing secrets directly in source code, committed configuration files, Docker images, or launch commands can expose them through Git history, build logs, process lists, image layers, or monitoring tools.

Spring Boot supports externalized configuration: the same application can read configuration from YAML/properties, environment variables, system properties, and external configuration sources. For secrets, you can use environment variables or mount secrets as files and load them via a configuration tree (`configtree:`). Spring Data Elasticsearch takes the bound values to configure `ClientConfiguration`, enable TLS, and authenticate when creating the client.

This lesson covers separating configuration from source code, binding with `@ConfigurationProperties`, injecting credentials into client configuration, using environment variables and secret files, deploying with Docker/Kubernetes, authenticating with Basic Auth or API keys, verifying TLS, rotating secrets, and avoiding accidental secret leaks into logs or management endpoints.

## 1. Distinguishing Regular Configuration from Secrets

Not every connection value needs the same level of protection:

| Value | Example | Classification |
|---|---|---|
| Host and port | `search.internal:9200` | Operational configuration, usually not a secret |
| Index name | `products` | Application configuration |
| Connect/socket timeout | `5s`, `30s` | Operational configuration |
| Username | `catalog-writer` | Identity info; should still limit sharing |
| Password | Service account password | Secret |
| API key | Encoded Elasticsearch API key | Secret |
| TLS private key | Client certificate private key | Secret |
| CA certificate | Public CA certificate | Not a password, but integrity must be protected |
| CA fingerprint | SHA-256 fingerprint | Not a secret; data used to verify the trust anchor |

Hosts, ports, index names, and timeouts can live in environment-managed configuration files. Passwords, API keys, and private keys must be supplied from a secret management source at runtime.

A useful rule of thumb:

- Source code holds property names and connection logic.
- Configuration files hold non-sensitive values or placeholders.
- The deployment platform supplies secrets when the application runs.
- The client only receives secrets via dependency/configuration binding, never reading secrets from Git or hard-coding them in Java.

## 2. Why Never Hard-Code Credentials?

Insecure example:

~~~java
ClientConfiguration configuration = ClientConfiguration.builder()
        .connectedTo("search.example.internal:9200")
        .withBasicAuth("elastic", "my-real-password")
        .build();
~~~

The password lives in source code. Even if you delete this line in a later commit, the secret can remain in Git history, forks, caches, artifacts, and repository clones.

Another insecure approach:

~~~yaml
spring:
  elasticsearch:
    uris: https://search.example.internal:9200
    username: catalog-writer
    password: my-real-password
~~~

If the file is packaged inside a JAR or committed to the repository, anyone with read access to the artifact/source can extract the credential. Never put real secrets in `application.yaml`, `application-prod.yaml`, committed `.env` files, or a `Dockerfile`.

Encrypting strings in source code does not solve the problem either if the decryption key is stored alongside the application. The goal is to separate secret access from source code read access and grant secrets only to the workloads that need them.

## 3. Spring Boot Externalized Configuration

Spring Boot can load properties from multiple sources:

- `application.properties` or `application.yaml`.
- Configuration files external to the JAR.
- Profile-specific configuration such as `application-prod.yaml`.
- OS/container environment variables.
- Java system properties.
- `SPRING_APPLICATION_JSON`.
- Command-line arguments.
- Mounted configuration trees as files.
- Additional sources provided by integration libraries, such as secret stores.

Sources have a precedence order. Higher-precedence sources override same-named properties from lower-precedence ones. In the default order, environment variables override config data in files; system properties have higher precedence than environment variables; command-line arguments have higher precedence than those.

This lets the exact same JAR run in development, staging, and production with different hosts/credentials without rebuilding the artifact.

### 3.1. Property placeholders

In YAML or properties, you can reference another property using:

~~~yaml
app:
  elasticsearch:
    host: ${APP_ELASTICSEARCH_HOST}
    username: ${APP_ELASTICSEARCH_USERNAME}
    password: ${APP_ELASTICSEARCH_PASSWORD}
~~~

Spring Boot resolves placeholders from `Environment`. If a required property is missing and has no default, the application usually fails during binding/initialization. This is desirable for production passwords: missing secrets should prevent starting with empty or default credentials.

You can specify defaults using a colon:

~~~yaml
app:
  elasticsearch:
    host: ${APP_ELASTICSEARCH_HOST:localhost:9200}
~~~

Only use defaults for non-sensitive values that have safe meaning in the target environment. Never write `password: ${APP_ELASTICSEARCH_PASSWORD:password}` or default API keys. Default credentials can cause an application to accidentally run with a weak account in production.

### 3.2. Environment variables and relaxed binding

Spring Boot supports relaxed binding from property names to environment variable names. Basic rules:

1. Replace dots (`.`) with underscores (`_`).
2. Remove hyphens (`-`).
3. Convert everything to uppercase.

Examples:

| Property | Environment Variable |
|---|---|
| `app.elasticsearch.host` | `APP_ELASTICSEARCH_HOST` |
| `app.elasticsearch.username` | `APP_ELASTICSEARCH_USERNAME` |
| `app.elasticsearch.password` | `APP_ELASTICSEARCH_PASSWORD` |
| `app.elasticsearch.ca-fingerprint` | `APP_ELASTICSEARCH_CAFINGERPRINT` |
| `app.elasticsearch.api-key` | `APP_ELASTICSEARCH_APIKEY` |

With `@ConfigurationProperties`, prefixes should use lowercase kebab-case, such as `app.elasticsearch`. Environment variables use uppercase and underscores.

If properties are declared directly with canonical names in `@ConfigurationProperties`, Spring can bind from environment variables without repeating placeholders in YAML. For instance, a class with prefix `app.elasticsearch` and field `password` receives `APP_ELASTICSEARCH_PASSWORD`.

## 4. Using `@ConfigurationProperties` to Bind Connection Configuration

When several related properties exist, `@ConfigurationProperties` is usually clearer and easier to validate than scattering `@Value` across configuration classes.

Example record:

~~~java
package com.example.catalog.config;

import jakarta.validation.constraints.NotBlank;

import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.validation.annotation.Validated;

@Validated
@ConfigurationProperties(prefix = "app.elasticsearch")
public record ElasticsearchConnectionProperties(
        @NotBlank String host,
        @NotBlank String username,
        @NotBlank String password,
        @NotBlank String caFingerprint) {
}
~~~

Validation annotations catch missing or whitespace-only required properties at application startup. A validation implementation must be on the classpath, typically `spring-boot-starter-validation`.

Registering properties:

~~~java
package com.example.catalog;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.context.properties.ConfigurationPropertiesScan;

@SpringBootApplication
@ConfigurationPropertiesScan
public class CatalogApplication {

    public static void main(String[] args) {
        SpringApplication.run(CatalogApplication.class, args);
    }
}
~~~

`@ConfigurationPropertiesScan` discovers configuration classes in the application package and subpackages. Alternatively, use `@EnableConfigurationProperties(ElasticsearchConnectionProperties.class)` on a specific configuration class.

### 4.1. `application.yaml` without secrets

The configuration file can contain only property keys and placeholders:

~~~yaml
app:
  elasticsearch:
    host: ${APP_ELASTICSEARCH_HOST}
    username: ${APP_ELASTICSEARCH_USERNAME}
    password: ${APP_ELASTICSEARCH_PASSWORD}
    ca-fingerprint: ${APP_ELASTICSEARCH_CA_FINGERPRINT}
~~~

This file can be committed because it contains no real credential values. Hostnames, usernames, and fingerprints may still be considered internal information; apply appropriate repository access policies if your environment requires it.

If you prefer binding directly from environment variables, the YAML file can omit the `app.elasticsearch` block altogether. `@ConfigurationProperties` will then receive values from the environment source via relaxed binding.

### 4.2. `@Value` and `Environment`

For a single simple property, you can use:

~~~java
@Value("${app.elasticsearch.host}")
private String elasticsearchHost;
~~~

Or read through `Environment`:

~~~java
String host = environment.getRequiredProperty("app.elasticsearch.host");
~~~

These two approaches fit small cases or dynamic property lookup. When you have a group of connection settings including host, username, password, TLS fingerprint, and timeouts, `@ConfigurationProperties` bundles them into a typed object that is easy to validate and test.

Never log a properties object with `toString()` if it contains secrets. Java records auto-generate `toString()` including all components, which can accidentally print passwords to logs. You can use a class with a masked `toString()` or strictly avoid logging the object.

## 5. Configuring Spring Data Elasticsearch `ClientConfiguration`

Spring Data Elasticsearch provides `ClientConfiguration` to configure cluster addresses, SSL, timeouts, headers, and Basic Authentication. For the current imperative client, you can extend `ElasticsearchConfiguration`.

Example:

~~~java
package com.example.catalog.config;

import org.springframework.context.annotation.Configuration;
import org.springframework.data.elasticsearch.client.ClientConfiguration;
import org.springframework.data.elasticsearch.client.elc.ElasticsearchConfiguration;

@Configuration
public class ProductElasticsearchConfiguration
        extends ElasticsearchConfiguration {

    private final ElasticsearchConnectionProperties properties;

    public ProductElasticsearchConfiguration(
            ElasticsearchConnectionProperties properties) {
        this.properties = properties;
    }

    @Override
    public ClientConfiguration clientConfiguration() {
        return ClientConfiguration.builder()
                .connectedTo(properties.host())
                .usingSsl(properties.caFingerprint())
                .withBasicAuth(
                        properties.username(),
                        properties.password())
                .build();
    }
}
~~~

`connectedTo` accepts host and port. `usingSsl` enables TLS and has an overload accepting a CA fingerprint. `withBasicAuth` configures the username/password for requests. Spring Data creates the client and operations beans from this configuration.

Do not embed username/password in the URL like `https://user:password@host:9200`. Credentials in URLs easily leak into logs, traces, exceptions, or command histories.

### 5.1. If using a CA certificate instead of a fingerprint

You can configure SSL using an `SSLContext` built from the CA certificate and pass it to the matching `usingSsl` overload. Example:

~~~java
SSLContext sslContext = createSslContextFromTrustedCa(caCertificatePath);

ClientConfiguration configuration = ClientConfiguration.builder()
        .connectedTo(properties.host())
        .usingSsl(sslContext)
        .withBasicAuth(properties.username(), properties.password())
        .build();
~~~

`createSslContextFromTrustedCa` is an illustrative helper; how the certificate is loaded depends on mount locations and the TLS library used. When using the Elasticsearch Java API Client directly, `TransportUtils.sslContextFromHttpCaCrt(...)` or `sslContextFromCaFingerprint(...)` are utilities documented by Elasticsearch.

A CA certificate does not need to be kept secret like a password, but its integrity must be protected. If an attacker can swap the CA certificate or fingerprint the application trusts, they can trick the application into trusting the wrong endpoint.

### 5.2. Reactive client

For reactive applications, extend `ReactiveElasticsearchConfiguration`:

~~~java
@Configuration
public class ReactiveProductElasticsearchConfiguration
        extends ReactiveElasticsearchConfiguration {

    private final ElasticsearchConnectionProperties properties;

    public ReactiveProductElasticsearchConfiguration(
            ElasticsearchConnectionProperties properties) {
        this.properties = properties;
    }

    @Override
    public ClientConfiguration clientConfiguration() {
        return ClientConfiguration.builder()
                .connectedTo(properties.host())
                .usingSsl(properties.caFingerprint())
                .withBasicAuth(
                        properties.username(),
                        properties.password())
                .build();
    }
}
~~~

The reactive configuration creates `ReactiveElasticsearchOperations` and the corresponding reactive client. Do not use the imperative `ElasticsearchConfiguration` for reactive repositories. If configuring headers via a supplier in the reactive client, the supplier must not block.

### 5.3. Avoid legacy client configuration

Spring Data Elasticsearch 6.x uses `Rest5Client` in current client configurations. Legacy configuration classes based on the old `RestClient` have been deprecated since Spring Data Elasticsearch 6.0. For new configurations, use `ElasticsearchConfiguration` or `ReactiveElasticsearchConfiguration` matching your stack.

## 6. Using an API Key Instead of Username/Password

Elasticsearch supports API key authentication. API keys often fit service-to-service access well because they can carry scoped permissions, expirations, and be revoked independently of user accounts.

When using an API key, the client sends the header:

~~~http
Authorization: ApiKey ENCODED_API_KEY
~~~

Spring Data `ClientConfiguration` can attach default headers:

When choosing an API key, use a dedicated properties class so username/password are not required:

~~~java
@Validated
@ConfigurationProperties(prefix = "app.elasticsearch")
public record ElasticsearchApiKeyProperties(
        @NotBlank String host,
        @NotBlank String apiKey,
        @NotBlank String caFingerprint) {
}
~~~

~~~java
import org.springframework.data.elasticsearch.support.HttpHeaders;

HttpHeaders headers = new HttpHeaders();
headers.add(
        "Authorization",
        "ApiKey " + properties.apiKey());

ClientConfiguration configuration = ClientConfiguration.builder()
        .connectedTo(properties.host())
        .usingSsl(properties.caFingerprint())
        .withDefaultHeaders(headers)
        .build();
~~~

In this setup, `apiKey` is bound from `APP_ELASTICSEARCH_APIKEY` or a secret store. Do not configure both Basic Auth and an API key simultaneously unless the application has a special authentication requirement; pick one clear method to avoid confusion.

An API key is a secret. Do not log the `Authorization` header, never send it to frontends, and do not share one key across unrelated applications.

### 6.1. Least privilege

Do not use the `elastic` account or a superuser for search/catalog applications. Create a service account or API key with only the needed permissions:

- Read indices the application needs to search.
- Index/update documents if the application writes data.
- Create indices or manage mappings only for authorized deployment components.
- Never grant cluster administration permissions if the application only needs to read/write an index.

Separate credentials by workload, such as a read-only key for the search API and a write key for the indexing worker. If one credential leaks, the impact is narrower.

### 6.2. API keys and per-index privileges

When creating an API key, a role descriptor can restrict access by index and action. Illustrative example of the permission concept:

~~~json
{
  "indices": [
    {
      "names": ["products"],
      "privileges": ["read"]
    }
  ]
}
~~~

This is a read privilege example. If a worker needs to write, add only the matching privileges such as `write` or the required index management privileges. Never grant `all` or `manage` out of habit when the application does not need them.

## 7. Providing Secrets via Environment Variables

Environment variables are a common way to pass runtime configuration into processes/containers. Example on Linux/macOS:

~~~bash
export APP_ELASTICSEARCH_HOST="search.internal:9200"
export APP_ELASTICSEARCH_USERNAME="catalog-writer"
export APP_ELASTICSEARCH_PASSWORD="<injected-at-runtime>"
export APP_ELASTICSEARCH_CA_FINGERPRINT="<trusted-sha256-fingerprint>"

java -jar catalog-service.jar
~~~

Values in angle brackets are placeholders; do not use these literal strings as real credentials. The deployment platform must supply real values via a secret store or appropriate runtime mechanism.

On PowerShell, you can set environment variables for the current process:

~~~powershell
$env:APP_ELASTICSEARCH_HOST = "search.internal:9200"
$env:APP_ELASTICSEARCH_USERNAME = "catalog-writer"
$env:APP_ELASTICSEARCH_PASSWORD = "<injected-at-runtime>"
$env:APP_ELASTICSEARCH_CA_FINGERPRINT = "<trusted-sha256-fingerprint>"

java -jar .\catalog-service.jar
~~~

Do not put real passwords in committed scripts or in commands that shell history, terminal transcripts, or process managers might retain. In production, let the orchestrator/secret manager supply environment variables or secret files.

### 7.1. Advantages and limitations of environment variables

Advantages:

- Supported by almost all runtimes, container platforms, and CI/CD systems.
- Easy to bind into `@ConfigurationProperties`.
- Avoids packaging secrets inside the JAR.
- One artifact works across multiple environments.

Limitations:

- Process environments can be read by users with sufficient permissions on the host/container.
- They can show up in diagnostic dumps or debug scripts.
- Values are usually fixed at process startup; changing a secret at the source does not automatically update a running process's environment.
- Long values or special characters can be awkward to pass through some shells/platforms.

Environment variables are a configuration delivery channel, not a complete secret manager. For sensitive secrets, mounted secret files or secret managers typically offer better access control and rotation.

### 7.2. Do not pass secrets via command-line arguments

Avoid:

~~~bash
java -jar catalog-service.jar \
  --app.elasticsearch.password="real-password"
~~~

Command-line arguments can be visible in process lists, job logs, shell history, or monitoring agents. Moreover, command-line properties have high precedence and can override environment variables, making configuration troubleshooting confusing.

Supply secrets through runtime environments or mounted secret files instead.

## 8. Using a Configuration Tree for Secret Files

Spring Boot supports `configtree:` to turn filenames in a directory into property keys and file contents into property values. This fits well when Kubernetes Secrets or Docker Secrets are mounted into a container.

Example directory layout:

~~~text
/run/secrets/
    app.elasticsearch.username
    app.elasticsearch.password
    app.elasticsearch.ca-fingerprint
~~~

Each file's contents represent its corresponding value. The file `app.elasticsearch.password` holds the password; the filename produces the property `app.elasticsearch.password`.

Add to `application.yaml`:

~~~yaml
spring:
  config:
    import: "configtree:/run/secrets/"
~~~

Once imported, properties can be bound like any other property:

~~~java
@ConfigurationProperties(prefix = "app.elasticsearch")
public record ElasticsearchConnectionProperties(
        @NotBlank String username,
        @NotBlank String password,
        @NotBlank String caFingerprint) {
}
~~~

`configtree:` does not encrypt file contents. It simply loads platform-mounted files into Spring `Environment`. File permissions, encryption at rest, mount permissions, and rotation remain managed by the secret platform.

### 8.1. Optional or required config tree?

If the secret volume is mandatory in production, use a required import:

~~~yaml
spring:
  config:
    import: "configtree:/run/secrets/"
~~~

If you add the `optional:` prefix:

~~~yaml
spring:
  config:
    import: "optional:configtree:/run/secrets/"
~~~

Spring Boot can still start when the directory does not exist. This works for dev/test environments with alternative config, but should not accidentally mask missing secrets in production. Even with an optional import, `@ConfigurationProperties` validation must still guarantee required credentials are populated before creating the client.

### 8.2. Importing a single file or extensionless file

If the platform mounts a complete YAML/Properties file, you can import that file via `spring.config.import`. For extensionless files, specify an extension hint:

~~~yaml
spring:
  config:
    import: "file:/etc/catalog/elasticsearch-config[.yaml]"
~~~

If each secret is its own file, use `configtree:`. If one file holds a full YAML/Properties config group, import that file directly.

## 9. Kubernetes Secrets

Kubernetes can mount a `Secret` into a container as a volume. One approach is creating a `Secret` whose keys match the property names:

~~~yaml
apiVersion: v1
kind: Secret
metadata:
  name: catalog-elasticsearch
type: Opaque
stringData:
  app.elasticsearch.username: catalog-writer
  app.elasticsearch.password: REPLACE_WITH_SECRET_MANAGER_VALUE
  app.elasticsearch.ca-fingerprint: REPLACE_WITH_TRUSTED_FINGERPRINT
~~~

These values only illustrate the structure. Never commit production `Secret` manifests containing real credentials to Git. In practice, use a secret manager or platform provisioning workflow to create/update Kubernetes Secrets.

Deployment mounting the Secret:

~~~yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: catalog-service
spec:
  template:
    spec:
      containers:
        - name: catalog-service
          image: example/catalog-service:1.0.0
          volumeMounts:
            - name: elasticsearch-secrets
              mountPath: /run/secrets
              readOnly: true
      volumes:
        - name: elasticsearch-secrets
          secret:
            secretName: catalog-elasticsearch
            defaultMode: 0440
~~~

With this layout, files in the volume are loaded via `configtree:/run/secrets/`.

### 9.1. Kubernetes Secrets do not automatically mean encryption

Kubernetes `Secret` objects are typically represented in Base64 in manifests/APIs. Base64 is only encoding, not encryption. Apply:

- Encryption at rest for Secret data in etcd.
- RBAC restricting who can read, create, or update Secrets.
- Restricted service account and namespace permissions.
- Mounting secrets only into containers that need them.
- Read-only mounts.
- Never putting secrets into images or ConfigMaps.
- Using an external secret manager when centralized auditing, rotation, and access policies are needed.

### 9.2. Secrets as environment variables in Kubernetes

Kubernetes can also expose a Secret as environment variables using `secretKeyRef`. Example:

~~~yaml
env:
  - name: APP_ELASTICSEARCH_PASSWORD
    valueFrom:
      secretKeyRef:
        name: catalog-elasticsearch
        key: password
~~~

When using this approach, Spring binds properties from environment variables. However, values are injected into the container environment and typically update only when the Pod is recreated. With secret file mounts, files can be updated via Kubernetes volume updates, though Spring `Environment` and already-initialized clients do not automatically reload new values.

## 10. Docker Secrets

Docker Swarm can provide secrets as mounted files inside containers, usually under `/run/secrets`. Spring Boot can read them via a configuration tree:

~~~yaml
spring:
  config:
    import: "configtree:/run/secrets/"
~~~

In Compose/Swarm, you can map a secret name to a target filename:

~~~yaml
services:
  catalog:
    image: example/catalog-service:1.0.0
    secrets:
      - source: elasticsearch-password
        target: app.elasticsearch.password

secrets:
  elasticsearch-password:
    file: ./local-secrets/elasticsearch-password.txt
~~~

The container sees `/run/secrets/app.elasticsearch.password`, from which Spring creates the property `app.elasticsearch.password`.

The local source file is only an example for development. Never commit files containing real secrets. In production, use platform secret management and restrict read permissions.

## 11. Using an External Secret Manager

When operating many services or environments, a secret manager centralizes credential lifecycle management:

- HashiCorp Vault.
- Cloud provider secret managers.
- Kubernetes external secrets integrations.
- Secret stores integrated via Spring Cloud or corresponding libraries.

Spring Boot does not encrypt every property by default. It provides integration hooks to load configuration from external sources; the library/secret manager handles authentication, authorization, retrieval, and potentially secret rotation.

A typical deployment flow:

~~~text
Secret Manager
      |
      | issues credentials to workload identity
      v
Runtime / deployment platform
      |
      | injects env or mounts secret files
      v
Spring Boot Environment
      |
      | binds @ConfigurationProperties
      v
ClientConfiguration
      |
      v
Elasticsearch client
~~~

When using Vault or a cloud secret manager, prefer workload identity/service identity over storing yet another long-lived credential in application config just to read the secret manager.

## 12. Do Not Put Secrets in Profile Files

Profiles like `dev`, `staging`, and `prod` are useful for selecting hosts, index prefixes, timeouts, or feature flags:

~~~yaml
spring:
  config:
    activate:
      on-profile: prod

app:
  elasticsearch:
    host: search-prod.internal:9200
    connect-timeout: 5s
    socket-timeout: 30s
~~~

Do not place production passwords in `application-prod.yaml`. Profile files normally live in source or artifacts, whereas secrets should be supplied by the deployment environment.

You can use the exact same JAR across all environments:

| Environment | Host | Credential |
|---|---|---|
| Local | `localhost:9200` | Dedicated dev credential |
| Test | Elasticsearch container | Disposable test credential |
| Staging | Staging cluster | Staging secret |
| Production | Production cluster | Production secret |

Never share passwords/API keys across environments. A leaked dev credential must never grant access to the production cluster.

## 13. TLS and Server Verification

User authentication and transport encryption are two distinct tasks:

- Authentication identifies who the client is.
- TLS encrypts the transport and verifies the server endpoint.

Simply using HTTPS/TLS does not mean the client has verified the right server. The client must trust a valid CA certificate or fingerprint.

With self-managed Elasticsearch, security features can enable authentication and TLS. You can obtain the CA certificate `http_ca.crt` or the CA's SHA-256 fingerprint from cluster setup/startup. Verify the fingerprint via a trusted channel before putting it into configuration.

Spring Data example:

~~~java
ClientConfiguration configuration = ClientConfiguration.builder()
        .connectedTo(properties.host())
        .usingSsl(properties.caFingerprint())
        .withBasicAuth(properties.username(), properties.password())
        .build();
~~~

Never disable hostname verification, use a trust-all certificate manager, or skip certificate validation to quick-fix SSL errors. Those shortcuts let the client connect to spoofed servers.

### 13.1. Distinguishing CA fingerprint from password

A CA fingerprint is not a user authentication credential. It is a value used to verify the CA. It usually does not need to be kept secret, but it must come from a trusted source and be updated carefully when the CA rotates.

Passwords/API keys must be kept confidential and revocable. Fingerprints/certificates need integrity protection and timely updates when the certificate authority changes.

### 13.2. Do not pass credentials in URLs

Do not use:

~~~text
https://catalog-writer:secret-value@search.internal:9200
~~~

Use a separate host and dedicated authentication configuration:

~~~java
ClientConfiguration.builder()
        .connectedTo("search.internal:9200")
        .usingSsl(caFingerprint)
        .withBasicAuth(username, password)
        .build();
~~~

URLs frequently appear in access logs, error messages, metric labels, or tracing spans.

## 14. Restricting Elasticsearch Account Privileges

Do not use the built-in `elastic` superuser in ordinary applications. Create dedicated users or API keys per workload:

| Workload | Recommended Privileges |
|---|---|
| Search API | Read/search permitted indices |
| Catalog writer | Read/write required catalog indices |
| Index migration job | Create indices/mappings/aliases during deployment |
| Monitoring agent | Required monitoring privileges only |

If an application only reads `products`, do not grant write access to `orders` or cluster administration. If a worker writes `products`, it does not need permissions to delete indices or manage users.

Narrower privileges mean smaller impact if a credential leaks. Record the owner, purpose, index scope, expiration, and revocation procedure for every API key.

## 15. Rotating Passwords or API Keys

Secrets have a lifecycle: creation, issuance, usage, rotation, revocation. Changing a secret in a secret manager does not automatically make running clients switch to the new value.

A safe rotation workflow:

1. Create a new credential with equivalent or narrower privileges.
2. Store the new credential in the secret manager or secret store.
3. Update the runtime secret for the workload.
4. Restart/roll out or use a designed and tested client refresh mechanism.
5. Verify the updated application authenticates and performs required operations.
6. Monitor authentication errors during the transition window.
7. Revoke the old credential once all instances have switched to the new one.
8. Record the timestamp, owner, and rotation outcome.

If secrets are mounted as files, the platform may update file contents, but already-bound `@ConfigurationProperties` and already-created Elasticsearch clients do not re-read files automatically. A restart/rollout or a controlled refresh that recreates the client is required.

With API keys, you can create the new key first, switch workloads over, and then invalidate the old key. Avoid revoking the old key before updated instances connect successfully if there is no rollback path.

### 15.1. Do not rotate by modifying files inside an image

Never rebuild a Docker image just to change a password. Images should be immutable; secrets are supplied when containers run. When a secret changes, update the runtime secret and roll out the workload per procedure.

### 15.2. Handling exposed credentials

If a password/API key is committed or appears in logs:

- Revoke or rotate the credential immediately.
- Review the credential's permissions and audit logs.
- Identify artifacts, logs, forks, and environments that may have received the secret.
- Remove the secret from current source, remembering that deleting it from a new commit does not purge copies in Git history.
- Review access history and narrow privileges on the replacement credential.

Do not simply delete the password line and consider the incident closed; any exposed secret must be assumed copied.

## 16. Avoiding Secret Leaks via Logs and Observability

Never log:

- Passwords or API keys.
- `Authorization` headers.
- `@ConfigurationProperties` objects containing secrets.
- Full `Environment` dumps or property sources.
- URLs containing usernames/passwords.
- Debug requests/responses containing credentials.

Do not enable transport-level `TRACE` logging in production without evaluating what gets logged. Request logs can expose headers or sensitive payloads depending on the client and configuration.

Actuator provides endpoints like `env` and `configprops` that help diagnose configuration. They can reveal configuration details; restrict exposed endpoints, enforce authentication/authorization, and verify sanitization policies. Never expose these endpoints on untrusted networks.

When logging connection errors, log enough information to investigate without logging credentials:

~~~java
log.error(
        "Cannot connect to Elasticsearch host {}",
        properties.host(),
        exception);
~~~

Do not log the `properties` object or password in the message. Also check whether hostnames are considered internal details that need masking in your specific environment.

## 17. Preventing Secrets from Entering Git, CI/CD, or Container Images

Common places secrets accidentally land:

- Source code and test fixtures.
- `application-prod.yaml`.
- `.env` or local files.
- `Dockerfile` `ENV` or `ARG`.
- Docker build logs.
- CI/CD variables echoed to stdout.
- Gradle/Maven command lines.
- Shell history.
- Artifacts, crash dumps, and support bundles.

Practical rules:

- Add local secret files to `.gitignore`.
- Commit `.env.example` containing only variable names and placeholders.
- Never use `ARG PASSWORD` or `ENV PASSWORD` in a `Dockerfile` to bake credentials into images.
- Use runtime secret injection.
- Mask CI/CD secrets in logs and avoid printing commands that expand secret values.
- Restrict who can view pipeline variables.
- Scan repositories and artifacts for accidentally committed credentials.
- When a secret appears in Git, rotate it rather than just editing the file.

Example `.gitignore`:

~~~gitignore
.env
.env.*
!.env.example
local-secrets/
secrets/
~~~

Example `.env.example`:

~~~dotenv
APP_ELASTICSEARCH_HOST=localhost:9200
APP_ELASTICSEARCH_USERNAME=
APP_ELASTICSEARCH_PASSWORD=
APP_ELASTICSEARCH_CA_FINGERPRINT=
~~~

Sample files contain no real secrets. Developers can create local-only files or use environment-issued test secrets.

## 18. Validating Required Configuration and Failing Fast

An application should not start with a default password or empty value only to fail when the first request arrives.

Use validation:

~~~java
@Validated
@ConfigurationProperties(prefix = "app.elasticsearch")
public record ElasticsearchConnectionProperties(
        @NotBlank String host,
        @NotBlank String username,
        @NotBlank String password,
        @NotBlank String caFingerprint) {
}
~~~

If using an API key instead of Basic Auth, define matching properties and validate the chosen method. Avoid leaving both password and API key optional and accidentally building an unauthenticated client.

You can add custom validation to check host format, fingerprint length/hex format, or enforce HTTPS/TLS in the production profile. Never log the invalid value in validation error messages if it is a secret.

Safe message example:

~~~text
Configuration property app.elasticsearch.password must be provided
~~~

Avoid messages like:

~~~text
Invalid Elasticsearch password: <actual-secret-value>
~~~

## 19. Testing Configuration Without Production Credentials

Tests should use dedicated credentials, dummy values, or test containers. Never load production secrets into unit tests and never print property values in assertion failures.

### 19.1. Unit testing `@ConfigurationProperties`

You can test binding with `ApplicationContextRunner` or Spring Boot test properties:

~~~java
@SpringBootTest(properties = {
        "app.elasticsearch.host=localhost:9200",
        "app.elasticsearch.username=test-user",
        "app.elasticsearch.password=test-only-secret",
        "app.elasticsearch.ca-fingerprint=test-fingerprint"
})
class ElasticsearchConnectionPropertiesTest {

    @Autowired
    ElasticsearchConnectionProperties properties;

    @Test
    void bindsConnectionProperties() {
        assertThat(properties.host()).isEqualTo("localhost:9200");
        assertThat(properties.username()).isEqualTo("test-user");
        assertThat(properties.password()).isEqualTo("test-only-secret");
    }
}
~~~

In real tests, avoid printing properties objects or passwords. You can simply verify the property is present or the client is created.

### 19.2. `@DynamicPropertySource` with Testcontainers

When using Testcontainers, the Elasticsearch address is dynamically assigned. You can register properties with `@DynamicPropertySource`:

~~~java
@DynamicPropertySource
static void elasticsearchProperties(DynamicPropertyRegistry registry) {
    registry.add(
            "app.elasticsearch.host",
            () -> elasticsearchContainer.getHost()
                    + ":" + elasticsearchContainer.getMappedPort(9200));
    registry.add("app.elasticsearch.username", () -> "test-user");
    registry.add("app.elasticsearch.password", () -> "test-only-password");
    registry.add("app.elasticsearch.ca-fingerprint", () -> testFingerprint);
}
~~~

This snippet assumes the container and TLS fixture are configured. If using a test cluster without security enabled, use a separate test configuration that does not require production secrets; never disable TLS validation in production just to make tests easier to run.

### 19.3. Verifying secrets never appear in logs

You can use a test appender to confirm a dummy password never shows up in log messages during client startup or connection failures. You do not need to print the value to debug the test; the assertion only checks that the secret string is absent.

## 20. Diagnosing Connection Errors

When the application cannot connect to Elasticsearch, classify the error before changing credentials:

| Symptom | Likely Cause | What to Check |
|---|---|---|
| Connection refused | Wrong host/port or service not listening | DNS, service endpoint, port, network policy |
| Unknown host | DNS or wrong hostname | DNS inside container/pod |
| `401 Unauthorized` | Wrong or expired username/password/API key | Secret source, key status, auth method |
| `403 Forbidden` | Valid credential, but lacks privileges | Role descriptor and index privileges |
| SSL handshake failure | Wrong CA/fingerprint, expired certificate, or hostname mismatch | Trust chain, fingerprint, SAN, and certificate validity |
| Timeout | Network, overloaded cluster, or too-low timeout | Connectivity, cluster health, timeout, and retry |
| Missing property | Secret not mounted or property name mismatch | `spring.config.import`, filename, and env binding |
| Old value after rotation | Process still holds old properties/client | Restart/refresh and rollout status |

Do not fix TLS errors by disabling certificate verification. Do not fix 403 errors by granting superuser; grant only the minimum required privileges.

## 21. Inspecting Property Sources Safely

Spring Boot Actuator `env` and `configprops` can help identify which source provided a property, but should not be opened publicly just for debugging.

When diagnosing:

1. Check property keys and configuration sources.
2. Verify whether environment variables exist in the container without echoing secret values.
3. Check whether secret files exist, along with permissions and filenames.
4. Confirm `configtree:` imports the right directory.
5. Confirm the `@ConfigurationProperties` bean is registered and bound.
6. Confirm the client uses the right host, TLS, and authentication method.
7. Inspect error types/statuses without logging headers or passwords.

If you need to confirm a secret was loaded, check its present/not-present status or an internal non-reversible hash rather than printing the secret value to a terminal.

## 22. Complete Configuration Example with Environment Variables

`application.yaml`:

~~~yaml
app:
  elasticsearch:
    host: ${APP_ELASTICSEARCH_HOST}
    username: ${APP_ELASTICSEARCH_USERNAME}
    password: ${APP_ELASTICSEARCH_PASSWORD}
    ca-fingerprint: ${APP_ELASTICSEARCH_CA_FINGERPRINT}
~~~

Properties:

~~~java
@Validated
@ConfigurationProperties(prefix = "app.elasticsearch")
public record ElasticsearchConnectionProperties(
        @NotBlank String host,
        @NotBlank String username,
        @NotBlank String password,
        @NotBlank String caFingerprint) {
}
~~~

Client configuration:

~~~java
@Configuration
public class ProductElasticsearchConfiguration
        extends ElasticsearchConfiguration {

    private final ElasticsearchConnectionProperties properties;

    public ProductElasticsearchConfiguration(
            ElasticsearchConnectionProperties properties) {
        this.properties = properties;
    }

    @Override
    public ClientConfiguration clientConfiguration() {
        return ClientConfiguration.builder()
                .connectedTo(properties.host())
                .usingSsl(properties.caFingerprint())
                .withBasicAuth(
                        properties.username(),
                        properties.password())
                .withConnectTimeout(Duration.ofSeconds(5))
                .withSocketTimeout(Duration.ofSeconds(30))
                .build();
    }
}
~~~

The runtime platform provides the four environment variables. Source code and the JAR contain no credentials. Spring Data creates `ElasticsearchClient` and `ElasticsearchOperations` from `ClientConfiguration`; repositories use the configured operations underneath.

## 23. Complete Configuration Example with Mounted Secret Files

`application.yaml`:

~~~yaml
spring:
  config:
    import: "configtree:/run/secrets/"

app:
  elasticsearch:
    host: search.internal:9200
~~~

Mounted files:

~~~text
/run/secrets/
    app.elasticsearch.username
    app.elasticsearch.password
    app.elasticsearch.ca-fingerprint
~~~

`@ConfigurationProperties` binds `host` from YAML and `username`/`password`/`caFingerprint` from the configuration tree. The client configuration uses the same constructor injection as the environment-variable example.

This pattern fits platforms that manage secrets via file mounts. Ensure the directory exists in production, file permissions are restricted, and the import is not marked `optional` if missing secrets should halt startup.

## 24. Common Mistakes

### Committing passwords in `application.yaml`

Packaged or committed configuration files can be read by many people and pipelines. Commit only placeholders and supply real values from a runtime secret source.

### Encrypting passwords and committing ciphertext

If the decryption key sits in the same source or artifact, an attacker has both ciphertext and key. Use a secret manager or runtime injection.

### Using default credentials

Default passwords like `changeme` can allow applications to start with weak accounts. Production secrets must be mandatory and validated.

### Putting secrets in command-line arguments

Process lists, shell histories, and logs can capture arguments. Use environment variables or mounted secret files.

### Treating environment variables as a secret manager

Environment variables are just a configuration source. They do not inherently provide auditing, access policies, encryption at rest, or rotation.

### Using `configtree` without mounting files

Properties go missing or fail to bind. Check `spring.config.import`, paths, filenames, and permissions. For required secrets, do not use `optional` imports to mask deployment errors.

### Using Kubernetes Secrets while forgetting Base64 is not encryption

Protect etcd, RBAC, and mount permissions. Consider an external secret manager.

### Using the `elastic`/superuser account

An exposed credential would allow cluster-wide administration. Create dedicated users/API keys with least privilege per index and action.

### Enabling TLS without verifying certificates

Never use trust-all or skip hostname verification. Use a trusted CA certificate or fingerprint.

### Putting passwords in URLs

URLs are frequently logged and traced. Configure authentication via client builders/headers.

### Logging properties objects

Record `toString()` can print the entire password. Never log objects containing secrets; if needed, log present/absent status only.

### Exposing Actuator `env`/`configprops` to everyone

These endpoints can reveal configuration details. Restrict exposure and protect access.

### Assuming updating a secret file automatically changes the client's password

Spring binds properties and initializes clients at startup. Perform a controlled restart/refresh or implement an actual rotation mechanism.

### Deleting a secret from a file without rotating it

The secret may still exist in Git history, artifacts, or logs. Revoke/rotate any exposed credential.

## 25. Connection Secret Management Workflow

When deploying a Spring Data Elasticsearch connection:

1. List required properties and classify which values are secrets.
2. Create a dedicated service account/API key for the application.
3. Grant least privilege per index and operation.
4. Choose a secret delivery source: environment variables, config tree, or secret manager.
5. Keep real secrets out of source code, profile files, and Docker images.
6. Bind properties via `@ConfigurationProperties`.
7. Validate required hosts, usernames, and credentials at startup.
8. Configure `ClientConfiguration` with TLS and authentication.
9. Verify CA certificates/fingerprints from a trusted source.
10. Never log secrets, `Authorization` headers, or properties objects.
11. Restrict secret read permissions and mount only into workloads that need them.
12. Test using dedicated test credentials and never production secrets.
13. Monitor 401, 403, TLS, and missing-property errors.
14. Establish a rotation process covering rollout, verification, and revoking the old credential.
15. When a secret is exposed, revoke/rotate it and investigate wherever the credential may have been copied.

## 26. Summary

Managing connection secrets means separating credentials from source code and artifacts, supplying them to the application at runtime, and controlling their lifecycle. Spring Boot supports externalized configuration via environment variables, property placeholders, `@ConfigurationProperties`, and configuration trees. For mounted secret files, `configtree:` turns filenames into property keys and file contents into property values; Kubernetes Secrets and Docker Secrets work cleanly with this approach.

Spring Data Elasticsearch takes the bound properties to build `ClientConfiguration`. `withBasicAuth` configures username/password; API keys can be sent via the `Authorization: ApiKey ...` header. `usingSsl` with a CA fingerprint or `SSLContext` verifies TLS. Never store passwords in URLs, never use a superuser for applications, and never disable certificate verification.

Environment variables are a configuration delivery channel, not a replacement for a secret manager. In production, enforce RBAC, file permissions, encryption at rest, logging hygiene, controlled Actuator exposure, and rotation. When a secret changes, already-bound properties and created clients do not update automatically; a controlled rollout/reload is needed. If a credential is exposed, revoke or rotate it rather than merely deleting it from the current file.

## References

- [Spring Boot – Externalized Configuration](https://docs.spring.io/spring-boot/reference/features/external-config.html)
- [Spring Boot – Configuration Properties](https://docs.spring.io/spring-boot/reference/features/external-config.html#features.external-config.typesafe-configuration-properties)
- [Spring Data Elasticsearch – Elasticsearch Clients](https://docs.spring.io/spring-data/elasticsearch/reference/elasticsearch/clients.html)
- [Spring Data Elasticsearch – ClientConfiguration API](https://docs.spring.io/spring-data/elasticsearch/reference/api/java/org/springframework/data/elasticsearch/client/ClientConfiguration.html)
- [Elasticsearch Java API Client – Connecting](https://www.elastic.co/docs/reference/elasticsearch/clients/java/setup/connecting)
- [Elasticsearch – Authentication](https://www.elastic.co/docs/api/doc/elasticsearch/authentication)
- [Kubernetes – Secrets](https://kubernetes.io/docs/concepts/configuration/secret/)
- [Docker – Manage sensitive data with Docker secrets](https://docs.docker.com/engine/swarm/secrets/)
- [Spring Cloud Vault](https://docs.spring.io/spring-cloud-vault/reference/)
