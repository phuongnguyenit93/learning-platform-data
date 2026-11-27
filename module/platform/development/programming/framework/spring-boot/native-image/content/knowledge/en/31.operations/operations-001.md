# Providing configuration, credentials, and service addresses at application runtime

GraalVM Native Image produces an executable whose classpath and codebase are determined during the build process. That does not mean every configuration value must be hardcoded into the binary. Spring Boot can still read configuration, credentials, and service addresses when the process starts via environment variables, command-line arguments, system properties, external configuration files, and configuration trees.

It is important to distinguish **runtime values** from **application structure already processed by AOT**. Database URLs, API keys, timeouts, ports, or service addresses can vary by environment. However, an external configuration file cannot add new classes to a native executable, and you should not rely on changing profiles at runtime to create a different bean graph from the graph already prepared by Spring AOT.

This lesson belongs to the **Operations** chapter of the `SPRING_BOOT_NATIVE_IMAGE` module. We will organize externalized configuration, bind and validate with `@ConfigurationProperties`, supply secrets via environment/config trees, configure service addresses in Docker/Kubernetes, handle credential changes, and inspect actual configuration on a native executable.

## 1. Runtime values and build-time structure

When building a native image, GraalVM analyzes code from the entry point and builds the executable based on what is reachable. The classpath cannot be arbitrarily modified after the binary has been built. Spring AOT also prepares bean definitions and related components during the build process.

| Category | Examples | Decision time |
| --- | --- | --- |
| Runtime values | Database URL, username/password, API endpoint, API key, timeout, port | When the process starts or via a supported refresh mechanism |
| Build/AOT structure | Classes, dependencies, bean graph, proxy types, implementations included in the executable | During compile/AOT/native image build |
| Runtime resources | External YAML files, certificates, mounted secrets, external templates if the application supports reading them | When the process runs; files and access permissions must exist |
| Native metadata | Reflection, resource, serialization, JNI, proxy hints | Primarily determined during build |

You can change the database address using `SPRING_DATASOURCE_URL` when launching the same native executable in staging and production. However, you cannot mount an additional JAR containing a new driver and expect the native executable to dynamically load that driver like a JVM classpath.

Similarly, you can change the API key or URL of a payment service through runtime configuration. If you want to swap bean implementations based on `@Profile` or `@ConditionalOnProperty`, you need to check the Spring AOT limitations for your version. The bean graph of a native application cannot be changed arbitrarily after build.

## 2. Spring Boot configuration sources

Spring Boot supports multiple configuration sources:

- `application.properties` or `application.yaml` files on the classpath.
- Configuration files external to the executable/container.
- Environment variables.
- Java system properties.
- Command-line arguments.
- `SPRING_APPLICATION_JSON`.
- Configuration trees mounted from Docker/Kubernetes or a secret management platform.
- Sources provided by integrations such as Spring Cloud Config/Vault.

Among commonly used operational sources, values from higher-precedence sources override lower-precedence ones:

| Relative order | Source | Example |
| --- | --- | --- |
| Lower | Defaults in code or default properties | Safe default values for timeouts |
| | Config data inside executable/classpath | `application.yaml` |
| | Config data outside executable | `/etc/orders/application.yaml` |
| | Environment variables | `SPRING_DATASOURCE_URL` |
| | Java system properties | `-Dserver.port=8081` |
| | `SPRING_APPLICATION_JSON` | Configuration JSON passed at startup |
| Higher | Command-line arguments | `--server.port=8082` |

This is a simplified view of common sources. Spring Boot has a fuller PropertySource precedence order, including test properties, JNDI, servlet parameters, and other sources. When a property has an unexpected value, inspect all participating sources rather than looking only at the YAML file.

### 2.1. Environment variable mapping

Spring Boot converts canonical property names to environment variables using these rules:

1. Replace dots (`.`) with underscores (`_`).
2. Remove dashes (`-`).
3. Convert to uppercase.

| Property | Environment variable |
| --- | --- |
| `spring.datasource.url` | `SPRING_DATASOURCE_URL` |
| `spring.datasource.username` | `SPRING_DATASOURCE_USERNAME` |
| `spring.datasource.password` | `SPRING_DATASOURCE_PASSWORD` |
| `server.port` | `SERVER_PORT` |
| `app.remote.base-url` | `APP_REMOTE_BASEURL` |
| `app.payment.api-key` | `APP_PAYMENT_APIKEY` |

Dashes are removed when forming environment variable names. For custom properties with multiple segments, check the relaxed binding rules to avoid misnaming them.

### 2.2. Command-line arguments and JSON

Spring Boot accepts arguments starting with `--` and adds them to the Environment:

```bash
./orders-service --server.port=8081 --app.remote.base-url=https://inventory.internal
```

Command-line arguments have high precedence, which is convenient for testing or occasional overrides. Do not pass passwords, tokens, or private keys via the command line because arguments can appear in process inspection, shell history, or logs of the system running the process.

You can pass multiple properties in a single JSON object:

```bash
SPRING_APPLICATION_JSON='{"app":{"remote":{"base-url":"https://inventory.internal"}}}' ./orders-service
```

A JSON environment variable is not a secret store. Do not place sensitive credentials here if the environment may record environment variables or commands.

## 3. Placing configuration files outside the executable

By default, Spring Boot looks for `application.properties` or `application.yaml` on the classpath and in certain locations outside the working directory, such as the current directory and `config/`. You can add to or replace these locations using two properties:

- `spring.config.additional-location`: adds locations to the default locations.
- `spring.config.location`: replaces the default locations with the specified list.

Keep the default configuration and add a mounted directory:

```bash
./orders-service --spring.config.additional-location=file:/etc/orders/
```

Directory locations should end with a trailing `/`. Spring Boot will look for configuration files matching the configured name, usually `application.yaml`, along with profile-specific files where applicable.

If you want to use only external files:

```bash
./orders-service --spring.config.location=file:/etc/orders/
```

Use `spring.config.location` carefully because it replaces the default search locations. If the external file does not exist, the application may fail to start. Use the `optional:` prefix when a location is truly optional:

```bash
./orders-service --spring.config.additional-location=optional:file:/etc/orders/
```

The properties `spring.config.name`, `spring.config.location`, and `spring.config.additional-location` are used very early to determine which files to load. Pass them via environment variables, system properties, or the command line at process startup; do not expect a bean inside the ApplicationContext to supply these values.

## 4. Default configuration and environment-specific overrides

A default file can hold non-sensitive values:

```yaml
spring:
  application:
    name: orders-service
  datasource:
    url: jdbc:postgresql://localhost:5432/orders
    hikari:
      connection-timeout: 2s
      maximum-pool-size: 10

server:
  port: 8080

app:
  inventory:
    base-url: http://localhost:8081
    connect-timeout: 2s
    read-timeout: 5s
  payment:
    base-url: https://payments.example.internal
```

When running in a container environment, environment variables can replace database URLs and service endpoints without rebuilding:

```bash
SPRING_DATASOURCE_URL=jdbc:postgresql://postgres:5432/orders APP_INVENTORY_BASEURL=http://inventory-api:8080 ./orders-service
```

The name `APP_INVENTORY_BASEURL` maps to the `app.inventory.base-url` property via relaxed binding rules. If you want a more readable environment variable name like `INVENTORY_BASE_URL`, declare a placeholder in YAML:

```yaml
app:
  inventory:
    base-url: ${INVENTORY_BASE_URL:http://localhost:8081}
```

Placeholders have the form `${NAME:default}`. Do not set dummy defaults for production credentials. Local defaults should only serve development; production requires explicit overrides.

## 5. Type-safe configuration binding with @ConfigurationProperties

For configuration with multiple fields, use `@ConfigurationProperties` instead of scattering `@Value` annotations across beans. This groups configuration by domain, performs type conversion, and validates at startup.

Example inventory service configuration:

```java
package com.example.orders.config;

import java.net.URI;
import java.time.Duration;

import jakarta.validation.constraints.NotNull;

import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.validation.annotation.Validated;

@ConfigurationProperties(prefix = "app.inventory")
@Validated
public record InventoryProperties(
        @NotNull URI baseUrl,
        @NotNull Duration connectTimeout,
        @NotNull Duration readTimeout) {
}
```

Enable scanning:

```java
package com.example.orders;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.context.properties.ConfigurationPropertiesScan;

@SpringBootApplication
@ConfigurationPropertiesScan
public class OrdersApplication {

    public static void main(String[] args) {
        SpringApplication.run(OrdersApplication.class, args);
    }
}
```

An appropriate validation dependency, such as `spring-boot-starter-validation`, is required so Jakarta Validation constraints are enforced. If the URL is missing or the timeout fails to bind, the application should fail fast instead of running with the wrong endpoint. For specific scheme/host requirements, add a custom validator to accept only URIs with an `http` or `https` scheme and a valid host.

### 5.1. Creating a client from runtime properties

Example configuring a `RestClient` using a base URL obtained from the Environment:

```java
package com.example.orders.config;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.web.client.RestClient;

@Configuration(proxyBeanMethods = false)
class InventoryClientConfiguration {

    @Bean
    RestClient inventoryRestClient(
            RestClient.Builder builder,
            InventoryProperties properties) {

        return builder
                .baseUrl(properties.baseUrl().toString())
                .build();
    }
}
```

The address is read when the application initializes the bean. If the environment variable changes after the process is already running, the already-created `RestClient` does not automatically update its base URL. You must restart or use an explicitly supported refresh/configuration mechanism.

### 5.2. Do not bind secrets into logs

You can bind the API key into a separate properties record:

```java
package com.example.orders.config;

import jakarta.validation.constraints.NotBlank;

import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.validation.annotation.Validated;

@ConfigurationProperties(prefix = "app.payment")
@Validated
public record PaymentProperties(
        @NotBlank String apiKey) {
}
```

Do not override `toString()` to print secret values, do not log the entire properties object, and do not include API keys in exception messages. When debugging, log only whether it is configured, not its content.

## 6. Supplying credentials via environment variables

Environment variables are a common way to pass configuration into a process/container:

```bash
SPRING_DATASOURCE_USERNAME=orders_app
SPRING_DATASOURCE_PASSWORD=replace-at-deploy-time
APP_PAYMENT_APIKEY=replace-at-deploy-time
./orders-service
```

The values above merely illustrate variable names. Never commit real passwords to a repository or Dockerfile.

Environment variables have several limitations:

- They can be exposed through process inspection, diagnostics, or crash collection depending on the platform.
- They are easily written to logs if a script prints the full environment.
- They can be stored in deployment or CI job metadata if pipelines are misconfigured.
- Changing the environment of a running container usually does not change the environment of an existing process.

For sensitive credentials, prefer a secret manager or mounted secret files. Environment variables are better suited for non-sensitive configuration such as service URLs, ports, and timeouts.

## 7. Using configuration trees for Docker/Kubernetes secrets

Spring Boot supports the `configtree:` prefix to read a directory where each filename becomes a property name and the file contents become the property value.

Example volume layout:

```text
/run/secrets/orders/
├── spring.datasource.username
├── spring.datasource.password
└── app.payment.api-key
```

In `application.yaml`:

```yaml
spring:
  config:
    import: "optional:configtree:/run/secrets/orders/"
```

The files map to:

| File | Property |
| --- | --- |
| `spring.datasource.username` | `spring.datasource.username` |
| `spring.datasource.password` | `spring.datasource.password` |
| `app.payment.api-key` | `app.payment.api-key` |

The application can bind these properties just like normal configuration sources. If a secret is required in production, ensure the deployment mounts it properly and validation rejects missing configuration. Do not use empty defaults for credentials and let failures surface only on the first request.

The `optional:` prefix lets the application continue when the directory does not yet exist. This is convenient for local development, but it does not replace validating required secrets in production. You can use environment-specific deployment configuration or omit `optional:` in environments that require secrets.

### 7.1. Docker secret mounts

Example `docker run` mounting a read-only secrets directory:

```bash
docker run --rm -p 8080:8080 -v /secure/orders-secrets:/run/secrets/orders:ro -e SPRING_CONFIG_IMPORT=configtree:/run/secrets/orders/ orders-service:native
```

Ensure the files have owner/permissions allowing the UID running the application to read them. Never copy the secrets directory into the image via a Dockerfile.

If using Docker Compose, you can mount secret files into the container. How secrets are managed depends on your Compose/Swarm setup; a regular volume mount does not automatically encrypt files as secrets.

## 8. Kubernetes Secret and Deployment example

Kubernetes can mount a Secret as files inside a container. Secret objects should be created from a secret manager or your organization's secure deployment workflow; never commit real credentials in manifests.

```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: orders
spec:
  replicas: 2
  selector:
    matchLabels:
      app: orders
  template:
    metadata:
      labels:
        app: orders
    spec:
      containers:
        - name: orders
          image: registry.example.com/orders:1.0.0
          ports:
            - containerPort: 8080
          env:
            - name: SPRING_CONFIG_IMPORT
              value: "optional:configtree:/run/secrets/orders/"
            - name: APP_INVENTORY_BASEURL
              value: "http://inventory-api:8080"
          volumeMounts:
            - name: orders-secrets
              mountPath: /run/secrets/orders
              readOnly: true
      volumes:
        - name: orders-secrets
          secret:
            secretName: orders-runtime
```

The secret volume can contain keys such as `spring.datasource.username`, `spring.datasource.password`, and `app.payment.api-key`. When mounted as a directory, each filename becomes a key in the config tree.

Several operational points:

- Secret volumes should be mounted read-only.
- Do not enable log dumps of the entire environment or config properties.
- Grant only minimal read permissions to the container UID.
- Protect Secret read permissions via RBAC and namespace policies.
- Use encryption at rest and cluster-appropriate secret management.
- Do not put Secrets into image layers, source control, or build artifacts.

If a secret is not mounted, validation must cause the application to fail fast. Do not let the application start with empty credentials and only discover the problem once traffic arrives.

## 9. Configuring service addresses in Docker and Kubernetes

Service addresses should not be hardcoded into the native binary. Provide them via runtime properties, DNS, or service discovery.

### 9.1. Docker Compose

In Docker Compose, services on the same network can call each other by service name:

```yaml
services:
  orders:
    image: orders-service:native
    environment:
      APP_INVENTORY_BASEURL: http://inventory-api:8080
    ports:
      - "8080:8080"
    depends_on:
      - inventory-api

  inventory-api:
    image: inventory-api:latest
    expose:
      - "8080"
```

The name `inventory-api` is resolved by Docker DNS within the Compose network. Do not use `localhost` to call another container: inside a container, `localhost` points to the current container itself. `depends_on` only controls startup order; it does not by default guarantee that the dependency service is ready to accept requests.

### 9.2. Kubernetes Service DNS

In Kubernetes, applications should call the Service name instead of a Pod IP:

- Same namespace: `http://inventory-api:8080`.
- Different namespace: `http://inventory-api.orders:8080`.
- The FQDN typically takes the form `inventory-api.orders.svc.cluster.local`.

The cluster domain can be customized, so do not assume the suffix is always `cluster.local`. Use the stable DNS name of the Service and let Kubernetes manage Pod endpoints.

Pod IPs can change during rollouts or rescheduling. Do not store Pod IPs in native build arguments or configuration files packaged into the image.

### 9.3. localhost inside containers

| Where the client runs | `localhost` points to |
| --- | --- |
| Native executable running directly on the host | The current host |
| Native executable inside a Docker container | That container |
| Pod in Kubernetes | The Pod network namespace |
| Container calling a service on the same Compose network | Use the service name, not localhost |

If you need to call a service on the host from Docker Desktop, a special hostname such as `host.docker.internal` may be available, though support is platform-dependent. Do not rely on this hostname as a portable address across all Linux/container runtimes.

## 10. Configuring timeouts, pools, and retries

A correct URL alone is not enough for stable connectivity. You need to configure:

- Connect timeout: time limit for establishing a connection.
- Read/response timeout: time limit for waiting on a response.
- Connection pool: maximum connections, idle retention time, and max lifetime.
- Retry: retry count, backoff, and which error types are safe to retry.
- Circuit breaker/bulkhead: isolating slow or failing services if the system uses them.
- TLS: trust anchors, hostname verification, and client certificates when required.

Do not blindly retry every request. A write request may have already been processed by the server even if the client timed out; retries require an idempotency key or safe semantics.

Set timeouts according to SLOs and overall request timeout budgets. Total retry duration must not exceed how long the caller can wait.

```yaml
app:
  inventory:
    base-url: http://inventory-api:8080
    connect-timeout: 2s
    read-timeout: 5s
    max-connections: 40
```

Bind these values as `Duration` or integers with explicit units. Do not leave timeouts unbounded because a stalled dependency can hold threads/requests indefinitely and exhaust the pool.

## 11. Credentials and TLS certificates

Connecting to a database or secured service may require:

- Username/password.
- API key or OAuth client secret.
- Client certificate and private key.
- CA certificate or truststore.
- Token endpoint and audience/scope.

Separate credentials from URLs if URLs might be logged. Do not embed passwords in JDBC URLs or HTTP URLs. Bind each property separately and configure clients through the appropriate API.

For TLS:

1. Provide the CA certificate/truststore via a secret or volume mount.
2. Set the runtime path and proper read permissions for the container UID.
3. Configure HTTP/JDBC clients to use the appropriate truststore.
4. Keep hostname verification enabled.
5. If using mTLS, protect the private key and restrict read permissions.
6. Verify the handshake with the native executable on the exact target base image and GraalVM version.

How truststores/certificates are loaded can depend on the JDK, GraalVM, HTTP client, and driver. Do not infer that passing JVM tests guarantees the native binary uses the same truststore. Always test TLS handshakes from the released executable/container.

Do not disable certificate validation as a quick fix for TLS errors. Inspect the CA chain, hostname, expiry, clock, and truststore instead.


## 12. Secret rotation and configuration changes while running

Environment variables are assigned when the process/container starts. Changing values in a manifest or secret store does not change the environment of an already running process.

Mounted secret files may be updated by the platform via its volume mechanism, but Spring Boot does not automatically guarantee that every already-bound bean, DataSource, connection pool, or HTTP client will be reconfigured when file contents change.

| Change | Typical behavior |
| --- | --- |
| Editing an environment variable in deployment | Requires recreating/restarting containers for processes to pick up new values |
| Updating a Secret volume | Files may be updated; the application does not automatically refresh beans |
| Changing a URL in a config file | Requires restart or an explicitly configured refresh mechanism |
| Changing an API key in an already-bound bean | Does not change automatically unless the bean/client supports refresh |
| Changing the database password | Existing pool connections may still keep sessions authenticated with old credentials |
| Changing a Service DNS record | New connections can use the new DNS; existing open connections may still hold the old endpoint |

A safe rotation procedure typically consists of:

1. Creating the new credential on the target system.
2. Allowing both old and new credentials to remain active during a transition window if the target system supports it.
3. Updating the Secret/config.
4. Rolling out/restarting the application or using a tested refresh integration.
5. Verifying that new instances connect successfully.
6. Draining old connections and monitoring error rates.
7. Revoking the old credential once all instances have transitioned.

If using Spring Cloud Vault, Spring Cloud Kubernetes, or a config refresh integration, verify clearly which properties are refreshed and which beans/clients actually pick up changes. Never assume a native image automatically refreshes all configuration when files change.

## 13. Profiles and Spring AOT limitations

Spring Boot profiles can supply different properties such as database URLs, log levels, or endpoints. However, Native Image relies on a closed-world assumption and Spring AOT generates the bean graph during the build process.

This means:

- You can externalize runtime configuration values.
- You should not rely on activating an arbitrary profile after build to add beans or implementations that were not processed by AOT.
- `@Profile` and `@ConditionalOnProperty` have limitations when they alter the bean graph.
- If environments need different bean graphs, check what your Spring Boot version supports and consider building separate artifacts for each AOT configuration.
- If only URLs, credentials, timeouts, or feature values differ, prefer externalized properties on the same bean graph.

Staging and production can run the same native executable with different `APP_INVENTORY_BASEURL` values. If staging uses a mock bean while production uses an HTTP client bean via `@Profile`, inspect the AOT output and test each artifact/profile according to supported configurations.

## 14. Validate configuration and fail fast

Misconfiguration should be caught immediately at startup rather than waiting for the first request.

You should validate:

- URLs have valid schemes/hosts.
- Ports fall within valid ranges.
- Timeouts are positive and not excessively large.
- Required credentials are non-empty.
- Certificate/truststore files exist and are readable.
- Pool sizes and retry counts are within bounds.
- Required services have configured endpoints.

Example validating properties:

```java
@ConfigurationProperties(prefix = "app.payment")
@Validated
public record PaymentProperties(
        @NotNull URI baseUrl,
        @NotBlank String apiKey,
        @NotNull Duration responseTimeout) {

    @AssertTrue(message = "payment base-url must use HTTPS")
    public boolean isSecureBaseUrl() {
        return baseUrl != null
                && "https".equalsIgnoreCase(baseUrl.getScheme())
                && baseUrl.getHost() != null;
    }
}
```

This example requires importing the constraints `jakarta.validation.constraints.NotBlank`, `NotNull`, and `AssertTrue`. Ensure the validation starter is present in dependencies.

Do not put default values like `password=changeme` or `api-key=test-key` in production config. Defaults used for local development must be explicitly overridden; required secrets must fail fast when missing.

## 15. Readiness and dependency health

A service may start successfully yet still be unable to serve traffic if required dependencies are not ready.

- **Liveness:** is the process alive and should it keep running?
- **Readiness:** can the instance receive traffic?
- **Dependency check:** is the database or remote service currently operating?

Do not put every dependency into the liveness probe. If a database temporarily fails and liveness fails, the orchestrator may restart instances en masse, making the situation worse.

Readiness can reflect required dependencies if the application genuinely cannot process traffic when those dependencies are unavailable. For optional dependencies or endpoints with fallbacks, evaluate based on actual behavior.

```yaml
management:
  endpoint:
    health:
      probes:
        enabled: true
  endpoints:
    web:
      exposure:
        include: health
```

Kubernetes can point its readiness probe to `/actuator/health/readiness`. Configure a startup probe if the native application needs noticeable startup time under low resource limits.


## 16. Inspecting actual configuration in operations

When an application connects to the wrong endpoint or lacks a credential, you need to see which values are actually bound without exposing secrets.

1. Confirm environment variables have the exact right names.
2. Confirm external configuration files are mounted at the right path.
3. Check `spring.config.import` and locations passed before startup.
4. Check file read permissions for the container UID.
5. Verify property binding and validation.
6. Test DNS/service names from the exact network namespace.
7. Check ports, TLS handshake, and timeouts.
8. Check connection pool/retry behavior.
9. Review redacted startup logs and metrics.

Spring Boot Actuator provides the `env` and `configprops` endpoints, which are useful when investigating property sources and binding. Only expose them on a protected management interface, restrict access, and ensure secret values are sanitized according to your configuration/version. Never expose the full Environment or config properties on unauthenticated endpoints.

You can log non-sensitive details such as service hosts, ports, timeouts, and active profile names. Never log passwords, API keys, access tokens, private keys, or the full command line if it might contain secrets.

## 17. Troubleshooting common issues

| Symptom | Causes to check | Resolution |
| --- | --- | --- |
| Native executable uses local URL in production | Environment variable does not bind to the right name | Check relaxed binding and variable name |
| External config is not loaded | Wrong `location`/`additional-location`, wrong path, or missing trailing `/` | Check startup arguments and file mounts |
| Missing config file causes process failure | Location was declared as required | Use `optional:` only when truly optional |
| Empty password | Secret not mounted or wrong key in config tree | Check filename, permissions, and validation |
| Secret changed but app still uses old credential | Bean/pool bound at startup and not refreshed | Rollout/restart or use a tested refresh integration |
| Connecting to service via localhost fails | `localhost` points to the current container/Pod | Use Docker/Kubernetes service DNS |
| Service DNS resolves but requests time out | Port, NetworkPolicy, TLS, or service not ready | Check network path, endpoint, and timeouts |
| Runs on JVM but native fails to read config | Differences in file/resource handling or native packaging | Check external files, resource hints, and executable runtime |
| Changing active profile does not change beans | Bean graph was already processed by AOT | Align AOT profiles or build appropriate artifacts |
| TLS handshake fails on native | Incompatible CA/truststore or native client config | Inspect certificate chain and test from the binary |
| Actuator shows an unexpected value | Higher-precedence PropertySource is overriding it | Check env, system properties, JSON, and CLI |
| Container cannot read secret | Mismatched UID/GID or file mode | Adjust mount permissions to the minimum needed |

## 18. Configuration deployment workflow for native executables

1. Package an immutable native executable/container image.
2. Put non-sensitive defaults in `application.yaml`.
3. Identify which properties must change per environment.
4. Supply database URLs and service endpoints via environment variables/external config files.
5. Supply usernames/passwords/API keys via a secret manager or config tree.
6. Mount CA/truststores and verify TLS if applicable.
7. Validate configuration at startup; stop the process if required values are missing.
8. Verify DNS, ports, and connectivity from inside the container/Pod.
9. Wait for readiness before accepting traffic.
10. Verify business endpoints and critical dependencies.
11. Record non-sensitive config version/secret version for auditability.
12. On rotation, roll out or refresh using a tested mechanism.
13. Monitor error rates, timeouts, connection pools, and readiness after deployment.

The same native image can be promoted across staging and production if the bean graph, target platform, and native build assumptions remain compatible. Each environment provides its own runtime values through a managed configuration mechanism.

## 19. Operations checklist

- [ ] Native executable contains no database passwords, API keys, or private keys.
- [ ] Runtime config is passed via Environment, config data, or secret integration.
- [ ] `spring.config.location` and `spring.config.additional-location` are used appropriately.
- [ ] Environment variables follow relaxed binding rules.
- [ ] Complex configuration is bound via `@ConfigurationProperties`.
- [ ] Validation catches missing or invalid URLs, timeouts, and required credentials.
- [ ] Secrets are supplied from a secret manager or mounted configuration tree.
- [ ] Secret files are mounted read-only with minimal read permissions for the application UID.
- [ ] Secrets never appear in command lines, logs, Dockerfiles, or CI output.
- [ ] Service addresses use stable DNS/service discovery, not hardcoded Pod IPs.
- [ ] `localhost` is never used to call another container/Pod.
- [ ] Connect/read timeouts, pools, and retries are configured according to SLOs.
- [ ] TLS truststores/certificates are verified on the actual native executable.
- [ ] Bean graph/profiles are compatible with the Spring AOT build.
- [ ] Secret rotation has a restart/refresh procedure and connection draining.
- [ ] Readiness and liveness probes are configured for their distinct purposes.
- [ ] Actuator management endpoints are secured and sanitize secrets.
- [ ] Post-deployment includes smoke tests and monitoring of error rates/timeouts.

### Self-assessment questions

1. Why can a database URL be changed at runtime while a native executable cannot load a new driver JAR after deployment?
2. How does the precedence order of config files, environment variables, and command-line arguments affect a property declared in multiple places?
3. What is the difference between `spring.config.location` and `spring.config.additional-location`?
4. Why is `@ConfigurationProperties` better suited for multi-field configuration than scattered `@Value` annotations?
5. How does `configtree:` map filenames and file contents into properties?
6. Why should passwords not be passed via command-line arguments or written into a Dockerfile?
7. In Docker/Kubernetes, what does `localhost` point to, and what address should be used to call another service?
8. Why does updating a Secret volume not guarantee that an already-bound DataSource or HTTP client will automatically switch credentials?
9. How does Spring AOT restrict changing the bean graph via profiles or conditional properties?
10. What states should readiness and liveness probes reflect?
11. When a native TLS handshake fails, what factors should be checked?
12. How can you verify which properties are bound without logging secrets?

## References

- [Spring Boot — Externalized Configuration](https://docs.spring.io/spring-boot/reference/features/external-config.html): PropertySource precedence, external files, environment variables, `spring.config.import`, and configuration trees.
- [Spring Boot — Type-safe Configuration Properties](https://docs.spring.io/spring-boot/reference/features/external-config.html#features.external-config.typesafe-configuration-properties): binding, validation, and relaxed binding.
- [Spring Boot — GraalVM Native Images](https://docs.spring.io/spring-boot/reference/packaging/native-image/introducing-graalvm-native-images.html): closed-world assumptions, fixed classpath, and Spring AOT limitations.
- [Spring Boot — Application Availability](https://docs.spring.io/spring-boot/reference/features/spring-application.html): startup, liveness, and readiness.
- [Kubernetes — Secrets](https://kubernetes.io/docs/concepts/configuration/secret/): creating, mounting, and managing Secrets in Pods.
- [Docker — Secrets](https://docs.docker.com/engine/swarm/secrets/): supplying secrets to services via file mounts.

**Target outcome:** be able to run the same Spring Boot Native Image across multiple environments by supplying database URLs, credentials, service addresses, timeouts, and certificates at runtime; know how to validate configuration at startup, understand bean graph limitations imposed by AOT, and have a safe workflow for secret rotation, DNS/service discovery, and readiness.
