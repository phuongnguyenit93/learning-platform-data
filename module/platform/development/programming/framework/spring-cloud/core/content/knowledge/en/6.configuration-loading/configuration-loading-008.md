# Config Trees for Configuration Mounted by Deployment Platforms

## 1. The Problem: Applications Receiving Configuration from Volume Mounts

In deployment environments such as Docker or Kubernetes, platforms commonly supply configuration to applications by **mounting files or directories into containers** (volume mounts). These files can contain application parameters, service connection details, certificates, or credentials.

Two common data layouts appear:

1. A single file containing full configuration, such as a YAML or Java Properties file.
2. A directory containing many small files, where **the filename is the property name** and **the file content is the value**.

Spring Boot supports the second layout via **configuration trees (config trees)** and the `configtree:` location prefix in **Config Data**. This mechanism turns a mounted directory structure into properties in the Spring `Environment`, allowing the application to read them via `@Value`, `Environment`, or bind them into `@ConfigurationProperties`.

This lesson belongs to the **Configuration Loading** chapter of **SPRING_CLOUD_CORE**. The focus is how a Spring Cloud application consumes external configuration supplied by the deployment platform, especially when separating secrets from images and source code. Remember that **config trees are a Spring Boot configuration loading feature**; Spring Cloud Commons/Context can collaborate with `Environment` and bean refresh, whereas Spring Cloud Config Server is a separate remote configuration mechanism.

## 2. How Does a Config Tree Map Directories to Properties?

Suppose the platform mounts this directory into the container:

```text
/etc/config/
└── inventory/
    ├── feature/
    │   └── reservation-enabled
    └── service/
        └── timeout
```

When importing `/etc/config/`, subdirectory and file names beneath it are joined into property keys:

| File Path | Property Key | Value |
| --- | --- | --- |
| `/etc/config/inventory/feature/reservation-enabled` | `inventory.feature.reservation-enabled` | Contents of file `reservation-enabled` |
| `/etc/config/inventory/service/timeout` | `inventory.service.timeout` | Contents of file `timeout` |

For example, if the `timeout` file contains `1500ms`, the application receives property `inventory.service.timeout` with that content. Type conversion into `Integer`, `Duration`, or other types is handled by Spring Boot's Binder when binding the property; do not assume file content automatically becomes a specific Java type immediately upon reading.

**Directory names are part of the property key.** If you import `/etc/config/inventory/` directly, the two properties become `feature.reservation-enabled` and `service.timeout`, because the `inventory` prefix is excluded from the imported tree.

To import a configuration tree, declare `spring.config.import` in the application's configuration file:

```yaml
spring:
  config:
    import: "optional:configtree:/etc/config/"
```

Values from the tree are added into `Environment` just like other Config Data sources. They can then be read in the standard way:

```java
@Value("${inventory.service.timeout}")
private Duration timeout;
```

Or bound into a structured object:

```java
import java.time.Duration;
import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "inventory")
public class InventoryProperties {

    private Feature feature = new Feature();
    private Service service = new Service();

    public Feature getFeature() {
        return feature;
    }

    public void setFeature(Feature feature) {
        this.feature = feature;
    }

    public Service getService() {
        return service;
    }

    public void setService(Service service) {
        this.service = service;
    }

    public static class Feature {
        private boolean reservationEnabled;

        public boolean isReservationEnabled() {
            return reservationEnabled;
        }

        public void setReservationEnabled(boolean reservationEnabled) {
            this.reservationEnabled = reservationEnabled;
        }
    }

    public static class Service {
        private Duration timeout;

        public Duration getTimeout() {
            return timeout;
        }

        public void setTimeout(Duration timeout) {
            this.timeout = timeout;
        }
    }
}
```

Register the configuration with `@ConfigurationPropertiesScan` on the application class or `@EnableConfigurationProperties(InventoryProperties.class)` in an appropriate configuration class. When property names use kebab-case, Spring Boot relaxed binding maps `reservation-enabled` to the Java property `reservationEnabled`.

### 2.1. Filenames containing dots

Multiple nested directory levels are not required. Config trees also understand dots inside filenames:

```text
/run/secrets/
├── spring.datasource.username
└── spring.datasource.password
```

Importing `/run/secrets/` produces two keys:

- `spring.datasource.username`
- `spring.datasource.password`

This naming style is convenient when a secret store or deployment platform mounts each secret as a file directly under the same directory.

### 2.2. String and byte array values

Config tree values can be bound as `String` or `byte[]`, depending on the desired data. Strings like usernames, passwords, or URLs are usually bound as `String`; binary data such as certificates or key material may require `byte[]`.

Do not read a binary certificate file as a UTF-8 string and assume its contents remain intact. Identify the data type and target API carefully. For certificates/keystores, check the file format, SSL configuration style, and process read permissions.

## 3. Declaring Config Data Imports

### 3.1. Configuration in YAML

Suppose the application needs general configuration from one volume and database credentials from a secrets volume:

```yaml
spring:
  config:
    import:
      - "optional:configtree:/etc/config/"
      - "optional:configtree:/run/secrets/"
```

The same declaration can be written in `application.properties`:

```properties
spring.config.import=optional:configtree:/etc/config/,optional:configtree:/run/secrets/
```

Each import location can be a separate configuration tree. Files are loaded as property sources during Config Data initialization.

### 3.2. What does `optional:` mean?

By default, if a declared Config Data location does not exist, Spring Boot throws `ConfigDataLocationNotFoundException` and the application does not start. The `optional:` prefix allows ignoring missing-location errors:

```yaml
spring:
  config:
    import: "optional:configtree:/run/secrets/"
```

Choose the declaration style based on operational requirements:

| Declaration | When directory does not exist | When appropriate |
| --- | --- | --- |
| `configtree:/run/secrets/` | Startup fails | Secrets are mandatory; missing secrets must block deployment |
| `optional:configtree:/run/secrets/` | Missing location is skipped | Local/dev or environments where that source is genuinely optional |

**Never use `optional:` to mask a mandatory secret.** If the application needs `spring.datasource.password` to connect to the database yet the secret directory was mounted incorrectly, skipping the location only delays the failure until bean binding or database connection. In production, fail fast when essential credentials are missing.

`optional:` handles the case where a location is absent; it does not make malformed file contents valid, nor does it replace application-level validation of required configuration.

### 3.3. Multiple config trees and wildcards

If the platform mounts multiple subtrees under one parent directory, you can use the `/*/` wildcard to import all **immediate subdirectories**:

```text
/etc/config/
├── database/
│   └── spring/
│       └── datasource/
│           ├── username
│           └── password
└── messaging/
    └── spring/
        └── rabbitmq/
            ├── host
            └── username
```

Import:

```yaml
spring:
  config:
    import: "optional:configtree:/etc/config/*/"
```

The result includes keys `spring.datasource.username`, `spring.datasource.password`, `spring.rabbitmq.host`, and `spring.rabbitmq.username`.

Important points to note:

- Config tree wildcards end with `/*/` and expand immediate subdirectories of the parent directory.
- Directories are expanded in alphabetical path order. If a different order is required, declare each location individually in `spring.config.import`.
- Directory names and filenames inside each tree are still combined into property keys.
- This wildcard does not recursively scan arbitrary directories at every depth.

### 3.4. Import order and value overrides

Config Data imports are processed where they are declared. Imported data has higher precedence than the document declaring the import. If a document imports multiple locations, locations are processed in declaration order and later locations can override earlier ones when both define the same key.

Example:

```yaml
spring:
  config:
    import:
      - "configtree:/etc/config/defaults/"
      - "configtree:/etc/config/environment/"
```

If both trees supply `inventory.service.timeout`, the value from the later `environment` tree takes precedence within this import group. Nevertheless, property sources with higher precedence than Config Data (such as OS environment variables, Java system properties, and command-line arguments) can still override the final result.

## 4. Database Secrets Example

Suppose a container receives secret files from the deployment platform:

```text
/run/secrets/
├── spring.datasource.username
└── spring.datasource.password
```

In `application.yml`:

```yaml
spring:
  config:
    import: "configtree:/run/secrets/"

  datasource:
    url: jdbc:postgresql://postgres:5432/inventory
    # username and password are loaded from files in the config tree
```

Spring Boot can bind `spring.datasource.username` and `spring.datasource.password` to `DataSource` configuration if the application has the appropriate JDBC driver and dependencies. There is no need to write credentials in YAML or pass passwords directly on the command line.

For instance, `spring.datasource.username` contains only the database username; `spring.datasource.password` contains the password provisioned by the secret management system. **Never put the contents of these files into Git, Docker images, logs, or deployment documentation.**

### 4.1. Reading configuration via `Environment`

If you need to check for a property's presence in code, you can inject `Environment`:

```java
import org.springframework.core.env.Environment;
import org.springframework.stereotype.Component;

@Component
public class DatabaseCredentialCheck {

    private final Environment environment;

    public DatabaseCredentialCheck(Environment environment) {
        this.environment = environment;
    }

    public boolean hasDatabasePassword() {
        String password = environment.getProperty("spring.datasource.password");
        return password != null && !password.isBlank();
    }
}
```

The method above only checks whether a value exists; it never returns the password externally. In real applications, prefer letting Spring Boot auto-configure `DataSource` and using appropriate health checks or connection validation instead of building custom credential-checking endpoints.

### 4.2. Using placeholders with config values

You can combine properties from a config tree with other properties:

```yaml
app:
  database:
    username: "${spring.datasource.username}"
    pool-name: inventory-pool
```

When resolved, the placeholder reads the value currently in `Environment`. However, avoid creating unnecessary extra copies of secrets in objects or logs. Bind only where needed and restrict access to sensitive data.

## 5. Mounting ConfigMaps and Secrets in Kubernetes

Kubernetes can mount ConfigMaps and Secrets as files inside containers. This is a classic use case for config trees.

Illustrative scenario:

- ConfigMap `inventory-config` contains key `inventory.feature.reservation-enabled`.
- Secret `inventory-db` contains keys `spring.datasource.username` and `spring.datasource.password`.
- The Deployment mounts the ConfigMap at `/etc/config` and the Secret at `/run/secrets`.

Illustrative YAML snippet showing container, volume, and volumeMount sections (metadata, selectors, and other Deployment fields omitted):

```yaml
spec:
  template:
    spec:
      containers:
        - name: inventory
          image: example/inventory-service:1.0
          volumeMounts:
            - name: app-config
              mountPath: /etc/config
              readOnly: true
            - name: db-credentials
              mountPath: /run/secrets
              readOnly: true
      volumes:
        - name: app-config
          configMap:
            name: inventory-config
        - name: db-credentials
          secret:
            secretName: inventory-db
```

In the application, import both directories:

```yaml
spring:
  config:
    import:
      - "configtree:/etc/config/"
      - "configtree:/run/secrets/"
```

If both volumes are mandatory, omit `optional:`. During deployment, verify ConfigMap/Secret names, which keys are mounted as which filenames, read permissions for the container user, and actual mount paths. If `items` or `subPath` maps keys to different paths, the property keys produced by config tree depend on the mounted path names.

**ConfigMaps are for non-sensitive configuration data; Secrets are for sensitive information.** Using a Kubernetes Secret does not by itself replace cluster security policies: enforce least-privilege RBAC, cluster-level encryption at rest, restricted read permissions, never print values to logs, and mount Secrets only into containers that need them. Secret data in manifests/APIs is commonly encoded in Base64; Base64 is merely encoding, not security encryption.

Kubernetes can update mounted ConfigMap/Secret volume contents after source data changes, yet updates carry propagation delay and do not automatically refresh `Environment` inside the JVM. In addition, volume mounts using `subPath` do not receive automatic updates from projected volume updates. Choose a rollout and mount strategy aligned with credential rotation requirements.

## 6. Docker Secrets and Mount Directories

Docker Swarm can supply secrets to a service by mounting secrets as files inside the container, typically under `/run/secrets/`. For example, if a secret is named `spring.datasource.password`, the application can import:

```yaml
spring:
  config:
    import: "optional:configtree:/run/secrets/"
```

Then `/run/secrets/spring.datasource.password` becomes the property `spring.datasource.password`.

Do not assume every Docker execution mode provisions secrets identically. Verify the deployment type, secret mechanism, and actual mount path. What matters to Spring Boot is that the process sees the **mounted files** and has read permission on them.

## 7. Distinguishing Config Trees from YAML Files and Spring Cloud Config Server

These three configuration mechanisms solve related but distinct problems:

| Mechanism | Data Format Provided | How Imported | Appropriate Use Case |
| --- | --- | --- | --- |
| Mounted YAML/Properties file | A complete configuration file | `spring.config.import: "file:/etc/app/application.yaml"` (or suitable file location) | Platform mounts an entire configuration file |
| **Config tree** | Multiple files; directory/file names form keys, contents form values | `spring.config.import: "configtree:/etc/config/"` | Kubernetes ConfigMap/Secret volumes, Docker secrets |
| **Spring Cloud Config Server** | Property sources from a remote configuration server | Config Client with `spring.config.import: "configserver:..."` | Centralized network configuration management for multiple apps/environments |

If the platform mounts a complete YAML file, import it as a file format; do not use `configtree:` expecting Spring Boot to parse that YAML file as a structured config document. `configtree:` reads individual files as property key/value pairs.

A config tree is also **not Config Server**. It provides no HTTP API for multiple services to query centralized configuration, manages no server-side configuration versions, and broadcasts no changes automatically. Each process reads the files mounted to it.

In a Spring Cloud architecture, both mechanisms can coexist: Config Server supplies shared configuration over the network; config trees supply secrets or environment data mounted into containers. Design precedence order and property ownership clearly so a single key is not defined in multiple places with unclear provenance.

## 8. Configuration Precedence and Diagnostics

Because config trees are imported via `spring.config.import`, they belong to **Config Data**. Spring Boot places Config Data below sources like OS environment variables, Java system properties, and command-line arguments in overall property source precedence. Thus, a value can be overridden by a higher-precedence source.

For example, a config tree supplies:

`spring.datasource.url=jdbc:postgresql://postgres:5432/inventory`

yet the process is launched with:

```bash
java -jar inventory-service.jar --spring.datasource.url=jdbc:postgresql://localhost:5432/local
```

then the command-line argument has higher precedence and the final value may be the `localhost` URL. This is helpful for intentional overrides yet can also cause an application to connect to the wrong environment inadvertently.

Key configuration sources, from lowest to highest among common runtime sources:

1. Application default values.
2. Config Data, including `application.yml` and imported config trees.
3. OS environment variables.
4. Java system properties.
5. `SPRING_APPLICATION_JSON`.
6. Command-line arguments.

Full ordering also includes sources such as `@PropertySource` and test property sources; for exact diagnostics, consult the Spring Boot documentation for your exact version.

### 8.1. Checking mounted files

Inside the container, inspect **filenames and permissions**, without printing secret contents:

```bash
ls -la /etc/config
ls -la /run/secrets
test -r /run/secrets/spring.datasource.password
```

If the process runs under a user without read permissions, Config Data may fail to load values or startup may fail. Check `runAsUser`, groups, `fsGroup`, file modes, and mount permissions according to the deployment platform.

### 8.2. Inspecting property values without exposing secrets

Actuator provides `env` and `configprops` endpoints to help diagnose property sources. However, these endpoints can expose sensitive property names or values depending on sanitization settings and version. Never enable them publicly just for debugging.

In development environments, you can inspect non-sensitive properties such as `inventory.feature.reservation-enabled`; for passwords/tokens, check only presence or connection status without printing values.

When checking property sources, verify:

- The `configtree:` path exists inside the container.
- Files have the exact expected names and directory depth.
- `spring.config.import` is loaded in a config file before the application context finishes initializing.
- Properties are not overridden by environment variables, system properties, or command-line flags.
- Target bound data types are compatible with file contents.

## 9. If a Config Tree Changes, Does the App Auto-Refresh?

**Never assume a changed mounted file automatically updates Spring `Environment` or running beans.** A config tree is a Config Data source read during configuration loading; the `configtree:` prefix itself creates no file watcher, sends no events to other instances, and does not restart the application.

Some platforms update volume contents after a ConfigMap/Secret changes, yet files changing on the filesystem do not immediately update property sources and beans inside the JVM. The standard deployment pattern is rolling out or restarting instances so applications load the updated configuration at startup.

If the system genuinely requires runtime refresh, design an explicit mechanism:

1. Confirm the updated data source has truly propagated and the process can read it.
2. Have a supported mechanism in your version to reload properties into `Environment`.
3. Publish a change event or invoke the appropriate refresh mechanism.
4. Rebind `@ConfigurationProperties` beans or invalidate `@RefreshScope` target beans as needed.
5. With multiple instances, signal all instances via an appropriate mechanism (e.g., Spring Cloud Bus) or coordinate refreshes at the deployment layer.

Spring Cloud Context provides `EnvironmentChangeEvent`, `@RefreshScope`, and refresh endpoints in suitable configurations. Yet `@RefreshScope` only handles scoped target beans after `Environment` already holds new values; it is not a file watcher and does not turn a volume mount update into a refresh event. Verify config tree reload behavior on your exact Boot/Cloud version and test with the real volume mechanism before relying on runtime refresh in production.

For credentials such as database passwords, certificates, or private keys, controlled rollouts are usually more predictable. Also plan for old connection lifecycles, credential revocation timing, and transition windows across instances.

## 10. Checklist for Deploying Config Trees

| Item | Question to Verify |
| --- | --- |
| Data source | Is this a complete YAML/Properties file or multiple key/value files? Did we pick `file:` vs. `configtree:` correctly? |
| Import path | Is the path correct inside the container? Trailing `/` on directories? Is `optional:` appropriate? |
| Property keys | Do directory and file names combine into the exact keys the application expects? |
| Wildcards | Does `/*/` expand immediate subdirectories properly? Is alphabetical ordering acceptable? |
| Binding | Do values bind into `String`, numbers, `Duration`, or `byte[]`? Are types and required constraints validated? |
| Secrets | Using proper Secret stores, least-privilege RBAC, restricted file permissions, and zero secret logging? |
| Overrides | Are any environment variables or command-line arguments overriding config tree properties? |
| Refresh | Do file changes require a restart/rollout? If runtime refresh is used, are sources reloaded and all instances notified? |
| Observability | Can status be diagnosed without exposing passwords/tokens? |
| Recovery | Is there a rollback procedure for configuration and credentials if a deployment fails? |

## 11. Practice Exercise

**Scenario:** `inventory-service` runs in a container. The deployment platform mounts configuration at `/etc/config` and database credentials at `/run/secrets`.

1. Create the file tree `/etc/config/inventory/feature/reservation-enabled` containing `true`.
2. Create `/etc/config/inventory/service/timeout` containing `1500ms`.
3. Create `/run/secrets/spring.datasource.username` and `/run/secrets/spring.datasource.password` with safe local test values.
4. Import both trees with `spring.config.import`, then bind `inventory.feature.reservation-enabled`, `inventory.service.timeout`, and the `DataSource` configuration.
5. Change the import path from `/etc/config/` to `/etc/config/inventory/` and observe how the resulting property keys change.
6. Test removing `optional:` when the directory does not exist, then add it back and compare startup behavior.
7. Set an environment variable overriding a non-sensitive property and verify the final value in `Environment`.
8. Simulate updating a file while the application is running; check whether existing beans change automatically. Test a restart/rollout or configured refresh mechanism and record the outcome.

**Pass criteria:** accurately explain how directory/file names form property keys, configure `configtree:` locations properly, distinguish full config files from config trees, identify override precedence, and avoid exposing secrets during diagnostics.

## 12. Official References

- [Spring Boot — Externalized Configuration](https://docs.spring.io/spring-boot/reference/features/external-config.html) — Config Data, `spring.config.import`, optional locations, configuration trees, wildcards, and property precedence.
- [Spring Boot — Configuration Properties](https://docs.spring.io/spring-boot/reference/features/external-config.html#features.external-config.typesafe-configuration-properties) — binding structured configuration.
- [Spring Cloud Context — Application Context Services](https://docs.spring.io/spring-cloud-commons/reference/spring-cloud-commons/application-context-services.html) — `EnvironmentChangeEvent`, refresh scope, and refresh endpoints.
- [Kubernetes — ConfigMaps](https://kubernetes.io/docs/concepts/configuration/configmap/) — supplying configuration data via volumes.
- [Kubernetes — Secrets](https://kubernetes.io/docs/concepts/configuration/secret/) — supplying sensitive data and security considerations.
- [Docker — Manage sensitive data with Docker secrets](https://docs.docker.com/engine/swarm/secrets/) — secrets mounted into service containers.

*This guide focuses on Spring Boot Config Data `configtree:` and its use in deployment platforms. Volume layout, file permissions, mount updates, and refresh mechanics must be verified against your exact container/orchestrator platform.*
