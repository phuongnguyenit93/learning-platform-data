# Separating build-time configuration from deployment-time configuration

In Java applications using CRaC (Coordinated Restore at Checkpoint), splitting configuration into two phases directly affects checkpoint reusability. Part of configuration describes the application itself and can be fixed at build time; the remainder is only known when deploying into a specific environment, such as database addresses, credentials, service endpoints, ports, and feature flags.

The key detail to note is that a checkpoint saves process state, including already-created Java objects, static values, system properties, and configuration data the application has read into memory. If the application reads environment A's configuration before checkpointing, restoring that checkpoint in environment B does not automatically replace the in-memory values with environment B's configuration.

Therefore, you must clearly determine which configuration is permitted inside the checkpoint, which configuration must be loaded after restore, and which resources must be recreated from deployment configuration. This separation allows one checkpoint to be shared across multiple environments while still connecting to the right database, services, and secrets for each environment.

## 1. Two configuration phases

### 1.1. Build-time configuration

Build-time configuration consists of values determined when compiling the application, packaging the artifact, or preparing a shared checkpoint. They describe the application itself and normally do not change across dev, staging, and production.

Examples:

- Application version and build identifier.
- Java release target, dependency versions, and plugin versions.
- Feature set compiled or packaged.
- Stable default paths inside the image.
- Module names and schema versions supported by the application.
- Default values containing no environment-specific information.
- JVM/JDK build and options required to create the checkpoint.

These values can be packaged with the artifact or recorded in checkpoint metadata. They should be stable, traceable, and free of secrets.

### 1.2. Deployment/runtime configuration

Runtime configuration describes the environment an instance will serve after launching or restoring. These values can differ across deployments and can change over the application lifecycle.

Examples:

- JDBC URL, hostname, port, and database name.
- Username, password, API key, certificate, and token.
- Endpoints of external services.
- Listening port, domain, and network routes.
- Pool sizes and timeouts tuned to environment load.
- Feature flags, tenant, region, and deployment policies.
- Log level, tracing endpoint, and monitoring details.
- Mount directories containing configuration files or secrets.

Runtime configuration must be supplied by the deployment environment, a config service, a secret manager, or mounted files. If a checkpoint is shared across multiple environments, the application should read these values after restore and initialize dependent resources from the fresh configuration.

### 1.3. Comparison

| Criterion | Build-time | Deployment/runtime |
|---|---|---|
| When determined | Building artifact or preparing checkpoint | At deployment or after restore |
| Variability | Usually fixed per build | Can differ across environments and change over time |
| Examples | Version, dependencies, Java target | DB URL, credentials, endpoints, ports |
| Storage location | Artifact, image metadata, build manifest | Environment provider, mounted config, secret manager |
| Should it live in a shared checkpoint? | Yes, if free of sensitive and environment-dependent data | Keep only non-sensitive, stable defaults; environment-specific data should be loaded after restore |
| When changed | Usually requires building a new artifact/checkpoint | Can be reloaded or resources recreated per policy |

A value does not automatically become build-time simply because it is placed in a configuration file. Classify by meaning: if a value varies by deployment environment, it is runtime configuration even if the file containing it is packaged inside an image.

## 2. Why does CRaC make configuration boundaries critical?

A checkpoint contains more than JARs or configuration files. It saves the running process state, which may include:

- Configuration objects created from properties or YAML files.
- Spring beans and singletons that already received configuration values.
- Static fields and caches holding endpoints, ports, or feature flags.
- System properties read at startup.
- Connection pools, HTTP clients, and thread pools built from configuration.
- Credentials, tokens, or sensitive data already loaded onto the heap.
- DNS results, connection state, and other runtime data.

Suppose the application is started in staging:

~~~text
Staging environment
    DB_URL = jdbc:postgresql://staging-db/orders
    API_URL = https://staging-api.example
            │
            ▼
Application reads config and creates objects
            │
            ▼
Process checkpoint
            │
            ▼
Restore the same checkpoint in production
~~~

If objects already hold the staging URL in fields, they can retain that value after restore. Having new environment variables on the production container does not automatically update already-restored objects.

### 2.1. Environment variables are not an automatic reload mechanism

Environment variables are provided to a process when the process is created. The application reads them via System.getenv(). Afterward, if code copies values into objects or static fields, the read values persist in process state.

Example:

~~~java
public final class DatabaseSettings {

    public static final String JDBC_URL =
            System.getenv("DB_JDBC_URL");
}
~~~

If the class was initialized before the checkpoint, JDBC_URL is already assigned. Restoring that checkpoint in another environment does not cause the static field to re-read the environment variable automatically.

Similarly, System.setProperty() or passing -D... at startup only sets values inside the current process. Restore is not a fresh JVM startup that re-reads all environment variables and system properties from the new deployment.

### 2.2. Already-read configuration files also become in-memory state

For example, the application reads runtime.properties at startup and holds an object:

~~~java
Properties properties = new Properties();

try (var reader = Files.newBufferedReader(configPath)) {
    properties.load(reader);
}

String databaseUrl = properties.getProperty("database.url");
~~~

After checkpointing, if the external file is modified, the Properties object residing on the heap does not update itself. To use the new configuration, the application must re-read the file or call a config service after restore and update dependent components.

### 2.3. Resources already built from old configuration

Even when configuration objects are updated, resources built from the old configuration still need replacement. For example:

- HikariDataSource already created connections to the staging database.
- HTTP client holds a connection pool to the staging API.
- Listener already bound an old port.
- Consumer already subscribed to an old queue.
- Scheduler is running schedules for an old tenant.

Reloading a field does not change the endpoints inside these resources. You must close or stop old resources in the proper order and then create new resources using validated runtime configuration.

## 3. Designing shared configuration for multiple environments

A checkpoint can be used under two different models.

### 3.1. Per-environment checkpoint

The application starts with one environment's configuration, warms up, and creates a checkpoint right inside that environment.

~~~text
Build artifact
     │
     ├── Deploy staging config ──> Start/warm-up ──> Checkpoint staging
     │
     └── Deploy production config -> Start/warm-up -> Checkpoint production
~~~

The advantage is that the application already has full resources and configuration state matching the environment. Restore can be fast because not all components need reinitialization.

In return, the checkpoint is bound to the environment that created it. Do not take a staging checkpoint and use it as a production checkpoint. Configuration and secrets may reside on the heap; connections, file descriptors, and namespaces may also depend on the origin environment. When credentials or endpoints change, the old checkpoint can hold stale values.

### 3.2. Shared checkpoint, loading runtime config after restore

For multiple environments, a shared checkpoint can be created without loading deployment-specific configuration yet:

~~~text
Build artifact
     │
     ▼
Prepare shared checkpoint
  - Load classes and libraries
  - Warm up code safely
  - Do not load secrets/runtime endpoints
  - Do not yet create environment-bound resources
     │
     ▼
Shared checkpoint
     │
     ├── Restore staging ──> Load staging config ──> Create staging resources
     │
     └── Restore production -> Load production config -> Create production resources
~~~

In this model, reusable state is prepared beforehand; environment-specific configuration and dependent resources are initialized after restore.

This model fits when sharing the same checkpoint artifact across multiple deployments. It requires the application to have a bootstrap/lifecycle coordinator to load configuration and initialize dependencies after restore, prior to accepting traffic.

### 3.3. Choosing a model by deployment goal

| Goal | Suitable model |
|---|---|
| Optimize restore for one fixed environment | Per-environment checkpoint |
| Use one checkpoint for dev, staging, and production | Shared checkpoint, load runtime config after restore |
| Secrets rotate frequently | Load secrets after restore from secret manager or mounted secrets |
| Database endpoint differs across environments | Load URL after restore and create matching connection pool |
| JVM options differ across environments | Create checkpoints tailored to each JVM configuration or use separate launch flows; do not assume restore can alter checkpointed JVM settings |
| Warm up code without saving environment data | Warm up with synthetic/safe data before checkpoint, create real resources after restore |

## 4. Classifying configuration before packaging

Configuration can be divided into three groups to decide when each is loaded.

### 4.1. Build-immutable configuration

This group describes the artifact:

- Version and build ID.
- Java bytecode level.
- List of libraries and drivers.
- Compiled feature set.
- Schema compatibility supported by the application.
- Environment-independent defaults.

These can be packaged inside the JAR or image. Changing this group normally requires building a new artifact and creating a corresponding checkpoint.

### 4.2. Deployment configuration

This group describes where the application runs:

- Database endpoint and schema/database name.
- URLs of external services.
- HTTP port and network binding.
- Pool sizes and timeouts.
- Tenant, region, feature flags.
- Log level and monitoring endpoint.

For a shared checkpoint, avoid loading these values before creating the checkpoint. Load them from mounted files or a config service after restore.

### 4.3. Secrets and credentials

Secrets must be managed separately:

- Database password.
- API keys and access tokens.
- Private keys, client certificates, and TLS material.
- Refresh tokens and message broker credentials.

Do not place secrets in source code, build arguments, image layers, or shared checkpoints. A secret already read onto the heap before checkpointing can remain in the snapshot even if the application sets the field to null prior to checkpoint.

Fetch secrets from a secret manager or mounted secret files after restore. If fresh credentials are needed after a long checkpoint interval, perform refresh/rotation before putting resources into service.

## 5. Organizing configuration files

A straightforward layout separates build metadata from deployment configuration:

~~~text
application/
├── app.jar
├── build-info.properties
└── config/
    └── defaults.properties        # Environment-independent default values

Deployment mount:
├── /run/app-config/runtime.properties
└── /run/secrets/
    ├── database-password
    └── partner-api-token
~~~

Example build metadata:

~~~properties
application.name=orders-service
application.version=2.4.0
application.build=git-8f31c2a
java.release=21
~~~

Example runtime configuration:

~~~properties
server.port=8080
database.url=jdbc:postgresql://db.internal:5432/orders
database.username=orders_app
database.passwordFile=/run/secrets/database-password
partner.apiUrl=https://partner.internal/api
partner.tokenFile=/run/secrets/partner-api-token
request.timeout=PT3S
feature.newCheckout=true
logging.level=INFO
~~~

The runtime file above only illustrates structure; in production, it is mounted or supplied by the deployment's configuration system. Never commit files containing internal production endpoints and details to a public repository. The password/token entries are only paths to secrets, not secret values.

### 5.1. Mount paths should be stable

If a shared checkpoint needs to read files after restore, choose a stable path inside the container, for example:

- /run/app-config/runtime.properties
- /run/secrets/database-password

Each deployment mounts different contents at the same path. Thus, application code and checkpoints only need to know the read location; specific data is supplied by the deployment environment.

If the configuration path itself also differs across environments, that path must be provided by a bootstrap mechanism changeable after restore. Do not store a staging path in a static field before checkpointing and expect the production deployment to replace it automatically.

## 6. Loading runtime configuration after restore

A config loader should perform the following steps:

1. Read a file or call a config service from the deployment environment.
2. Parse values into explicit data types.
3. Validate required fields and value bounds.
4. Retrieve secrets from a separate source.
5. Create dependent resources such as connection pools, HTTP clients, and listeners.
6. Mark the application READY only when mandatory dependencies are operational.

Example configuration type:

~~~java
package com.example.app;

import java.net.URI;
import java.nio.file.Path;
import java.time.Duration;

public record RuntimeConfig(
        int httpPort,
        URI databaseUrl,
        String databaseUsername,
        Path databasePasswordFile,
        URI partnerApiUrl,
        Path partnerTokenFile,
        Duration requestTimeout,
        boolean newCheckoutEnabled) {
}
~~~

Loader reading the runtime file:

~~~java
package com.example.app;

import java.io.Reader;
import java.net.URI;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.time.Duration;
import java.util.Properties;

public final class RuntimeConfigLoader {

    private RuntimeConfigLoader() {
    }

    public static RuntimeConfig load(Path configFile)
            throws Exception {

        Properties properties = new Properties();

        try (Reader reader = Files.newBufferedReader(
                configFile, StandardCharsets.UTF_8)) {
            properties.load(reader);
        }

        int port = Integer.parseInt(
                required(properties, "server.port"));

        if (port < 1 || port > 65535) {
            throw new IllegalArgumentException(
                    "server.port must be between 1 and 65535");
        }

        Path passwordFile = Path.of(
                required(properties, "database.passwordFile"));

        Path tokenFile = Path.of(
                required(properties, "partner.tokenFile"));

        Duration timeout = Duration.parse(
                required(properties, "request.timeout"));

        if (timeout.isNegative() || timeout.isZero()) {
            throw new IllegalArgumentException(
                    "request.timeout must be positive");
        }

        return new RuntimeConfig(
                port,
                URI.create(required(properties, "database.url")),
                required(properties, "database.username"),
                passwordFile,
                URI.create(required(properties, "partner.apiUrl")),
                tokenFile,
                timeout,
                Boolean.parseBoolean(
                        properties.getProperty(
                                "feature.newCheckout", "false")));
    }

    private static String required(
            Properties properties,
            String key) {

        String value = properties.getProperty(key);

        if (value == null || value.isBlank()) {
            throw new IllegalArgumentException(
                    "Missing required configuration: " + key);
        }

        return value.trim();
    }
}
~~~

The loader reads only secret paths; it does not yet load passwords or tokens into the RuntimeConfig object. Components owning connections or API clients will read secrets once bootstrap has identified the exact environment.

In production, add protocol-specific validation, verify URI schemes, verify read permissions on secret files, and report clear errors when the configuration file is missing or malformed.

## 7. Coordinator managing configuration and resources after restore

To ensure the service does not start before configuration is available, a CRaC coordinator can be used. The coordinator is registered prior to checkpointing and is responsible for loading config, initializing dependencies in order, and stopping them before checkpoint.

Example contract for components:

~~~java
package com.example.app;

public interface RuntimeComponent {

    // Initialize from the current deployment's configuration.
    void start(RuntimeConfig config) throws Exception;

    // Must be safe if start only partially completed.
    void stop() throws Exception;
}
~~~

Coordinator:

~~~java
package com.example.app;

import org.crac.Context;
import org.crac.Core;
import org.crac.Resource;

import java.nio.file.Path;
import java.util.ArrayList;
import java.util.List;

public final class RuntimeBootstrap implements Resource {

    public interface Readiness {
        void markReady();
        void markNotReady();
    }

    private enum State {
        INACTIVE,
        ACTIVE,
        FAILED
    }

    private final Path configFile;
    private final List<RuntimeComponent> components;
    private final Readiness readiness;
    private final List<RuntimeComponent> attempted =
            new ArrayList<>();

    private State state = State.INACTIVE;

    public RuntimeBootstrap(
            Path configFile,
            List<RuntimeComponent> components,
            Readiness readiness) {

        this.configFile = configFile;
        this.components = List.copyOf(components);
        this.readiness = readiness;

        // Register coordinator before initializing dependent resources.
        Core.getGlobalContext().register(this);
    }

    public synchronized void activate() throws Exception {
        if (state == State.ACTIVE) {
            return;
        }

        if (state == State.FAILED) {
            throw new IllegalStateException(
                    "Runtime bootstrap is in FAILED state");
        }

        readiness.markNotReady();

        RuntimeConfig config =
                RuntimeConfigLoader.load(configFile);

        try {
            for (RuntimeComponent component : components) {
                // Record beforehand so partial start can be cleaned up.
                attempted.add(component);
                component.start(config);
            }

            state = State.ACTIVE;
            readiness.markReady();

        } catch (Exception startupFailure) {
            Exception cleanupFailure = stopInReverseOrder();

            state = State.FAILED;

            if (cleanupFailure != null) {
                startupFailure.addSuppressed(cleanupFailure);
            }

            throw startupFailure;
        }
    }

    @Override
    public synchronized void beforeCheckpoint(
            Context<? extends Resource> context) throws Exception {

        readiness.markNotReady();

        if (state != State.ACTIVE) {
            return;
        }

        Exception failure = stopInReverseOrder();
        state = failure == null ? State.INACTIVE : State.FAILED;

        if (failure != null) {
            throw failure;
        }
    }

    @Override
    public synchronized void afterRestore(
            Context<? extends Resource> context) throws Exception {

        // Re-read deployment configuration and create fresh resources.
        activate();
    }

    private Exception stopInReverseOrder() {
        Exception firstFailure = null;

        for (int index = attempted.size() - 1; index >= 0; index--) {
            try {
                attempted.get(index).stop();
            } catch (Exception failure) {
                if (firstFailure == null) {
                    firstFailure = failure;
                } else {
                    firstFailure.addSuppressed(failure);
                }
            }
        }

        attempted.clear();
        return firstFailure;
    }
}
~~~

Example creating the bootstrap:

~~~java
Path runtimeConfig = Path.of(
        "/run/app-config/runtime.properties");

List<RuntimeComponent> components = List.of(
        databaseComponent,
        partnerClientComponent,
        applicationServiceComponent,
        httpServerComponent
);

RuntimeBootstrap bootstrap =
        new RuntimeBootstrap(
                runtimeConfig,
                components,
                readiness);

// Run during normal startup:
if (!checkpointPreparationMode) {
    bootstrap.activate();
}
~~~

In checkpoint preparation mode, the application does not call activate() before checkpointing. The coordinator is registered yet remains in INACTIVE state. When the checkpoint is restored at the target deployment, afterRestore() reads that deployment's runtime file, validates configuration, and initializes components in order.

During normal startup, activate() is called so the application operates without needing restore. With a shared checkpoint, the checkpointPreparationMode flag is a choice of the build/prepare workflow; it must be determined before starting warm-up. How the flag is passed depends on the pipeline, yet you should not use a deployment-specific value baked into a shared checkpoint.

This is a skeleton illustrating the orchestration flow. A real application needs proactive shutdown, timeouts, FAILED state handling, readiness integration, and synchronization with frameworks. RuntimeComponent implementations must stop safely even when start failed partially.

## 8. Initialization and callback order

When the coordinator manages components in dependency order:

~~~text
RuntimeConfig
     │
     ▼
Database pool
     │
     ▼
Partner API client
     │
     ▼
Application service
     │
     ▼
HTTP server
~~~

After restore, config is loaded first, and then components are initialized in list order. The HTTP server opens last so requests do not enter while the database or services are not yet ready.

If individual components also register CRaC Resources themselves, registration order must be defined explicitly. Within the same context, beforeCheckpoint callbacks run in reverse registration order; afterRestore callbacks run in registration order. Do not let both the coordinator and a component close/open the same resource twice.

With the coordinator architecture above, child components do not register callbacks themselves for the same pool or client. The coordinator is the lifecycle owner and calls start/stop in dependency order.

## 9. Configuration in Spring and dependency injection

In Spring Boot or DI frameworks, configuration is commonly bound into beans and injected into services. When the application context is created prior to checkpointing, many beans may retain runtime values read at that time.

For example, a bean holding a JDBC URL:

~~~java
@ConfigurationProperties(prefix = "database")
public record DatabaseProperties(URI url) {
}

@Component
public class DatabaseClient {

    private final URI jdbcUrl;

    public DatabaseClient(DatabaseProperties properties) {
        this.jdbcUrl = properties.url();
    }
}
~~~

If this bean was created before checkpointing in staging, restoring that checkpoint in production does not re-run the constructor with production properties.

Organizational approaches:

- Keep build metadata and immutable configuration in ordinary beans.
- Use a RuntimeConfigProvider whose configuration can change after restore.
- Create dependent beans/resources after RuntimeConfigProvider has loaded and validated configuration.
- Close and recreate connection pools, HTTP clients, or consumers whose endpoints changed.
- Announce readiness only after the application context or required runtime parts are ready.

If the entire Spring context is built before checkpointing, identify which beans can be kept and which must be refreshed/recreated. Simply changing Environment or a Properties object does not automatically update fields already injected into singletons.

Some applications can recreate part of the context after restore; others use facades or dynamic providers. The choice depends on framework integration and startup time. Whichever approach is chosen, maintain a single lifecycle owner for each resource.

## 10. JVM settings that cannot be treated as ordinary runtime reloads

Certain settings are applied when the JVM starts and affect the runtime process:

- Heap sizing such as Xms and Xmx.
- Garbage collector and JVM flags.
- Classpath/module path.
- Native library path.
- Certain system properties read once by libraries.
- Agents, instrumentation, and runtime options.

If a checkpoint is created with a given JVM configuration, do not assume the restore command can arbitrarily change settings that shaped process state. Changing heap, GC, or foundational JVM settings usually requires creating a new matching checkpoint or using a different launch procedure.

Distinguish JVM options from application runtime configuration. A database URL can be reloaded by the application if the design supports it; JVM heap size cannot be changed by reloading a properties file in a callback.

Also record vendor, version, build number, architecture, and JVM options when creating a checkpoint. Restoring must run in an environment compatible with the checkpoint and CRaC/CRIU constraints.

## 11. Secrets and sensitive data in checkpoints

Checkpoints can contain data on the heap and process state. If the application read passwords, API tokens, or private keys before creating a checkpoint, those values may remain in the snapshot.

Setting a field to null before checkpointing does not guarantee secret bytes vanish from all memory pages. Garbage collection, internal copies, buffers, and native libraries may have created additional copies.

For shared checkpoints:

1. Do not load secrets before creating the checkpoint.
2. Keep only stable secret paths or provider names if needed.
3. After restore, authenticate with the secret manager or read mounted secrets.
4. Do not write secrets into logs, build metadata, or image layers.
5. Protect checkpoint artifacts like sensitive data if they may contain other runtime state.
6. Design refresh/rotation if secrets can change over the checkpoint lifetime.

Docker build arguments or ENV variables in a Dockerfile are not secret stores. Build arguments can appear in metadata/layers depending on usage; ENV is baked into image config. Use the build system's secret mechanism for build steps needing credentials, and use a secret manager or secret mount at deployment time.

## 12. Changing configuration while the application is running

Runtime configuration may change after restore. Define a reload policy:

- **Immediate reload:** update providers and resources that support safe live configuration changes.
- **Versioned reload:** load a new config snapshot, validate it, create new resources, switch traffic, and then close old resources.
- **Restart/re-restore:** use when changes cannot be applied safely inside the running process.

Do not update individual fields piecemeal while requests are reading configuration. A safe pattern is constructing a new immutable RuntimeConfig and publishing it via a volatile reference or AtomicReference:

~~~java
private final AtomicReference<RuntimeConfig> current =
        new AtomicReference<>();

public RuntimeConfig current() {
    RuntimeConfig config = current.get();

    if (config == null) {
        throw new IllegalStateException(
                "Runtime configuration is not active");
    }

    return config;
}

public void publish(RuntimeConfig updated) {
    current.set(updated);
}
~~~

In-flight requests can retain the config snapshot they started with; new requests receive the new snapshot. For resources like connection pools, implement a dedicated cutover procedure so the old pool is not closed while requests still use it.

After restore, always validate new config before publishing. If configuration is invalid or secrets are unreachable, keep readiness at NOT_READY and report specific errors. Never silently fall back to staging endpoints or old credentials.

## 13. Warm-up when preparing a shared checkpoint

Warm-up helps load classes and warm up code prior to creating a checkpoint. However, separate warming up code from initializing deployment-specific data.

Safe warm-up activities include:

- Exercising representative processing flows with synthetic data.
- Loading classes and initializing libraries independent of environment endpoints.
- Performing CPU-bound computations requiring no credentials.
- Preparing caches containing only immutable metadata or public data.
- Warming up code paths before runtime resources are created.

Avoid:

- Connecting to production/staging databases and retaining pools in a shared checkpoint.
- Loading API tokens, passwords, or private keys.
- Caching tenant, user, or sensitive data.
- Resolving and caching environment-specific endpoints.
- Recording test request outcomes containing real data.
- Initializing consumers or schedulers bound to specific queues/tenants.

If warm-up needs a database, use a test database with synthetic data and close the resource completely before checkpointing; even better, separate code warm-up from external integration warm-up.

After restore, deployment-specific resources are recreated from runtime config. If warming up connection pools or caches for the target environment is needed, perform it after loading the right config and before marking READY.

## 14. Reproducible build and deploy workflow

A pipeline for shared checkpoints can be divided into stages:

~~~text
BUILD
  - Compile source
  - Resolve dependency versions
  - Package application
  - Record build metadata
        │
        ▼
PREPARE CHECKPOINT
  - Start CRaC-enabled JDK
  - Load application classes
  - Warm-up code with synthetic data
  - Keep deployment config/secrets unloaded
  - Register runtime bootstrap coordinator
  - Create checkpoint
        │
        ▼
PACKAGE
  - Store JAR and checkpoint
  - Store JDK/build/architecture metadata
  - Record checksums
        │
        ▼
DEPLOY
  - Mount runtime config at stable path
  - Mount secrets or connect secret provider
  - Provide compatible Linux/CRIU environment
        │
        ▼
RESTORE
  - Restore checkpoint
  - Load and validate deployment config
  - Fetch secrets
  - Create database/client/server resources
  - Run health checks
  - Mark READY
~~~

Store alongside the checkpoint:

- Git commit and build ID.
- Checksums of JAR and checkpoint artifacts.
- JDK vendor/version/build.
- Key JVM options.
- OS/kernel, CPU architecture, and CRIU version.
- Non-sensitive build-time configuration.
- Supported runtime config version/schema.

Do not store secret values in build manifests. Deployments need separate configuration and secrets, with versions or revisions so restore investigations can pinpoint exactly which configuration was used.

### 14.1. Pre-restore compatibility checks

Before restoring, confirm:

- JDK/CRaC build matches the checkpoint.
- OS, kernel, architecture, and CRIU meet requirements.
- Required mount paths exist.
- Runtime config is present and conforms to schema.
- Secret provider is reachable.
- Databases and required endpoints have network routes.
- Ports and resource limits match the deployment.

If runtime config or secrets are missing, bootstrap must fail before opening traffic. Never use build-time config as a fallback for environment endpoints or credentials.

## 15. Verifying configuration separation

You can verify using two simulated deployments sharing the same checkpoint artifact yet using different configurations.

### 15.1. Two runtime config sets

Staging:

~~~properties
server.port=8080
database.url=jdbc:postgresql://staging-db:5432/orders
database.username=orders_staging
database.passwordFile=/run/secrets/database-password
partner.apiUrl=https://staging-partner.example/api
partner.tokenFile=/run/secrets/partner-api-token
request.timeout=PT3S
feature.newCheckout=false
~~~

Production:

~~~properties
server.port=8080
database.url=jdbc:postgresql://production-db:5432/orders
database.username=orders_app
database.passwordFile=/run/secrets/database-password
partner.apiUrl=https://partner.example/api
partner.tokenFile=/run/secrets/partner-api-token
request.timeout=PT2S
feature.newCheckout=true
~~~

Both deployments mount their respective files at the same path inside the container. The shared checkpoint contains neither staging-specific nor production-specific endpoints or secrets.

### 15.2. Evidence to observe

After restoring in staging:

- RuntimeConfig shows the staging database URL.
- Connection pool connects to the staging database.
- Partner client uses the staging endpoint.
- Feature flags are read per staging configuration.
- Readiness transitions to READY only after health checks succeed.

After restoring in production:

- RuntimeConfig shows the production database URL.
- Connection pool connects to the production database.
- Partner client uses the production endpoint.
- Feature flags are read per production configuration.
- No old connections or clients point to staging.

Logs should record only the environment name, config revision, publicly permissible endpoints, and validation results. Never log passwords, tokens, or secret contents.

### 15.3. Testing configuration changes

To prove the application genuinely re-reads configuration after restore:

1. Create a shared checkpoint before runtime config is loaded.
2. Restore with the staging file and confirm resources use staging endpoints.
3. Stop the staging instance per procedure.
4. Restore the same checkpoint artifact with the production file.
5. Confirm resources use production endpoints.
6. Modify the config revision or secret in a test environment.
7. Restore again and confirm bootstrap receives the new revision.
8. Check logs and health endpoints to confirm no old resources remain active.

Do not only inspect file contents after restore. Verify that resources were created from that configuration via a real health check or query.

## 16. Common mistakes

| Mistake | Consequence | Fix |
|---|---|---|
| Reading DB URL before shared checkpoint | Production restore still retains staging endpoint | Load deployment config only after restore |
| Believing new environment variables overwrite static fields | Restored objects still use old values | Use a config loader/provider capable of re-reading |
| Only modifying Properties while keeping the old connection pool | Pool continues connecting to previous endpoint | Close and recreate dependent resources |
| Baking passwords into the image | Secrets persist in image layers or checkpoints | Use secret manager/mounts and load after restore |
| Loading config file once without reloading | File changes while beans retain old values | Reload and publish a new config snapshot |
| Opening HTTP server before config/dependencies are ready | Requests arrive in an incomplete state | Initialize dependencies first, open listener last |
| Using a checkpoint with mismatched JVM options | Restore fails to match desired runtime configuration | Create a checkpoint compatible with needed JVM options |
| Warming up with production data | Checkpoint may retain environment-specific data or caches | Use synthetic data, discard unused state |
| Having two lifecycle owners for the same resource | Duplicate close/open or out-of-order callbacks | Designate a single coordinator/owner per resource |
| Failing to log config revision | Difficult to tell which configuration an instance used | Log revision and non-sensitive build metadata |

## 17. Design principles to remember

Treat a checkpoint as a snapshot of an already-stateful process. Any configuration already read into objects, static fields, singletons, or resources prior to that point can be restored along with the process. A new deployment does not automatically replace those values.

With shared checkpoints, include only immutable and safely reusable state in the snapshot. Keep runtime configuration and secrets in external sources, read them after restore, validate, and recreate dependent resources. With per-environment checkpoints, explicitly record the environment and configuration version to which the checkpoint is bound.

An application should accept traffic only after deployment configuration has loaded, secrets have been fetched from an appropriate source, databases/clients/listeners have been recreated, and required health checks have succeeded. When build-time and runtime boundaries are clearly established, the same artifact can be deployed predictably without carrying over endpoints or sensitive state from the checkpoint-creation environment.
