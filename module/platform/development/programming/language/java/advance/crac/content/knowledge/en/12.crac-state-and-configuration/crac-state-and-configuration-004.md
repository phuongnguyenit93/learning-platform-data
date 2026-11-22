# Environment Variables, System Properties, and Application-Cached Configuration

Java applications typically receive configuration from multiple sources: process environment variables, JVM system properties, configuration files, databases, secret stores, or remote configuration services. Part of the configuration is read at startup and kept in the heap; another part is queried whenever needed. When using CRaC, a checkpoint saves the process state at a point in time, so values that were read and stored in memory can persist after restore.

This creates an important consideration: configuration inside the process may reflect checkpoint time, whereas external configuration has changed. Restore does not automatically re-run the entire startup sequence to reload every environment variable, system property, or configuration file from scratch. The application must determine which sources are startup configuration, which need refreshing after restore, and which must be re-verified before resuming service.

## 1. Distinguishing Configuration Sources

Common configuration sources have different lifecycles:

| Source | How Java accesses it | Typical lifecycle | What to watch out for after restore |
|---|---|---|---|
| Environment variables | System.getenv(...) | Provided to the process at launch | A restored process typically continues with the environment received at launch; orchestrator config changes do not automatically update a running process |
| System properties | System.getProperty(...) | Passed at launch via -D or modified in the JVM via System.setProperty | JVM values at checkpoint may be restored; refresh is needed if the app uses properties for dynamic config |
| Configuration files | Files, Properties, YAML/JSON parsers, or frameworks | Files sit outside the heap; parsed config objects may be held in the heap | Files can change while checkpointed, while parsed objects may still hold old values |
| Database/config service | JDBC, HTTP client, or SDK | State managed by an external service | Connections, caches, and config versions may need verification or re-querying |
| Secret store | Platform SDK or API | Secrets can be rotated independently of the process | Tokens, credentials, or secrets in the heap may expire or be revoked |
| In-heap application configuration | Fields, static fields, singletons, caches | Persists with process state | May be restored to the exact checkpoint value yet be stale relative to the authoritative source |

What must be distinguished is the configuration source versus the application's copy of the configuration. A file or config service can be the authoritative source; Java objects parsed from that source are merely in-memory copies.

## 2. Process Environment Variables

Environment variables are typically set by the shell, container runtime, orchestrator, or deployment system before the Java process starts. Java reads these values using System.getenv:

~~~java
String databaseUrl = System.getenv("APP_DATABASE_URL");
String region = System.getenv("APP_REGION");
~~~

You can retrieve the entire environment map:

~~~java
Map<String, String> environment = System.getenv();
~~~

The map returned by System.getenv() is unmodifiable via the Java API. The application cannot use this map to update the process's environment variables by calling put().

### Environment variables are usually startup configuration

In container environments, environment variables are typically attached to the container or process when the process is created. If deployment configuration changes, a running process does not automatically pick up new values simply because orchestrator manifests or secrets were updated. Usually a new process/container must be created to receive a new set of environment variables.

When CRaC restores a process from a checkpoint, the application resumes from the saved process state. Do not assume that restoring is equivalent to launching a fresh process from an image and reloading the current deployment's entire environment.

For example, an application read APP_REGION as ap-southeast-1 at startup and stored it in a field:

~~~java
public final class RegionConfig {
    private final String region;

    public RegionConfig() {
        this.region = System.getenv("APP_REGION");
    }

    public String region() {
        return region;
    }
}
~~~

The region field belongs to heap state. After restore, the RegionConfig object may continue holding the value read at startup/checkpoint. If the deployment platform changed the environment variable for a new launch, that does not automatically change the field inside the restored object.

Therefore, use environment variables for configuration intentionally tied to the process lifecycle, such as listen ports, deployment profiles, or region names fixed at startup. For configuration that must change without starting a new process, use a dynamic configuration source with a re-read API and versioning mechanism.

### Do not use environment variables as a dynamic configuration store

Do not design an application assuming System.getenv() can be updated after restore to obtain new secrets or endpoints. If you need to rotate credentials or update endpoints, query a secret/config service or a source with explicit refresh capabilities.

In addition, do not log the entire environment map. Environment variables can contain passwords, tokens, connection strings, or other sensitive information.

## 3. JVM System Properties

A system property is a JVM key/value pair. Properties can be passed at launch using the -D option:

~~~shell
java -Dapp.region=ap-southeast-1 -Dapp.mode=production -jar app.jar
~~~

In Java, read the value with System.getProperty:

~~~java
String region = System.getProperty("app.region");
String mode = System.getProperty("app.mode", "development");
~~~

The application can also modify properties at runtime:

~~~java
System.setProperty("app.feature.new-checkout", "true");
~~~

Unlike the environment map, System properties can be modified via System.setProperty or System.clearProperty. The properties and their values are JVM state; if the application modified them before checkpoint, that state may be preserved upon restore.

### System properties do not reload automatically from the command line

The -D option is processed when the JVM starts. Restore does not re-parse the command line and does not initialize a fresh JVM. Therefore, properties set at process startup or changed at runtime may continue holding old values after restore.

If a property represents dynamic configuration, refresh it from the authoritative source using a configuration management component. Do not expect changes to launch arguments in the deployment to be applied to an already restored process.

### Global system properties must be managed carefully

System properties are global JVM state. Modifying them can affect other libraries and components that already read values earlier.

For example, a library may read a property once when the class is initialized:

~~~java
public final class ClientDefaults {
    public static final int TIMEOUT_MS =
            Integer.getInteger("app.client.timeout", 3000);
}
~~~

Calling System.setProperty afterward does not automatically change the static field TIMEOUT_MS. Both the property and the cached value in the static field can be preserved in the checkpoint with different values.

For dynamic configuration, avoid having multiple classes independently read and cache System properties at different times. Use a configuration management component with explicit versioning and refresh rules.

## 4. Application-Cached Configuration in the Heap

Applications commonly read multiple configuration sources at startup and convert them into immutable objects for fast access:

~~~java
public record AppConfig(
        String databaseUrl,
        String region,
        int requestTimeoutMillis,
        boolean newCheckoutEnabled) {}
~~~

A singleton or Spring bean may hold this AppConfig object. If the object sits on the heap at checkpoint time, it is part of the restored application state.

Example:

~~~java
public final class ConfigHolder {
    private volatile AppConfig current;

    public ConfigHolder(AppConfig initialConfig) {
        this.current = initialConfig;
    }

    public AppConfig current() {
        return current;
    }

    public void replace(AppConfig next) {
        this.current = next;
    }
}
~~~

If current was replaced with a new configuration before checkpoint, the new value can be kept in the heap. If the external configuration source changes after checkpoint, the restored current object may still hold the older version.

This is the difference between:

- **State saved inside the process:** configuration objects, static fields, caches, singletons.
- **Authoritative configuration source:** files, databases, config servers, secret managers, or the deployment platform.

If configuration must reflect the current state of the authoritative source, the application must re-read or verify the version after restore. Do not assume the checkpoint automatically refreshes parsed objects.

## 5. Configuration Files and External Data

Configuration files live on the filesystem, whereas objects parsed from those files live in the heap. These two parts may no longer be at the same version after restore.

Example:

1. The application reads app.yml version 10.
2. The configuration is parsed into AppConfig and stored in a singleton.
3. The process creates a checkpoint.
4. While the process is inactive, app.yml is updated to version 11.
5. The process is restored, and the AppConfig object at version 10 still exists.

If the application needs version 11, it must re-read the file or receive a refresh event from the configuration source. Changing the file on disk does not automatically update the Java object.

For a config service or database, a similar situation occurs: the server may return a new configuration, yet the in-heap cache still holds the old version. After restore, the application must check cache TTL, version, or ETag and reload when needed.

Not every configuration setting needs reloading. Some values such as schema mappings or fixed profiles can be treated as startup configuration. Some values such as endpoints, feature flags, quotas, or credentials may need refreshing. This decision must stem from the application's operational requirements.

## 6. Classifying Configuration by Lifecycle Policy

A useful practice is classifying configuration by rate of change:

| Category | Examples | Appropriate policy |
|---|---|---|
| Process-fixed config | Port, profile, deployment region, instance name | Keep startup value; changing it requires creating a new process or a restart procedure |
| JVM config | System properties, timezone, locale, library flags | Keep JVM values at checkpoint; change only via supported and controlled mechanisms |
| Dynamic config | Feature flags, timeouts, endpoints, request limits | Refresh or verify version after restore if the source can change |
| Credentials/secrets | Database passwords, API tokens, certificates | Verify expiration and access; refresh via secret provider when needed |
| Cached business config | Price tables, permission lists, routing rules | Check version/TTL and reload from authoritative source if stale |
| Runtime state | Request counts, counters, temporary caches, scheduler state | Keep if still valid; recreate or reconcile if dependent on time and external services |

Do not blindly reload all configuration. Certain values may only be set at startup; changing them while the application is running can leave components using inconsistent values. Your policy must clearly state which fields can be hot-refreshed and which require a restart.

## 7. Organizing a Refreshable ConfigProvider

A ConfigProvider can encapsulate reading the authoritative source, parsing, validating, and publishing new configuration versions.

~~~java
public interface ConfigSource {
    LoadedConfig load() throws Exception;
}

public record LoadedConfig(long version, AppConfig config) {}

public final class ConfigProvider {
    private final ConfigSource source;
    private volatile LoadedConfig current;

    public ConfigProvider(ConfigSource source, LoadedConfig initial) {
        this.source = source;
        this.current = initial;
    }

    public AppConfig current() {
        return current.config();
    }

    public long version() {
        return current.version();
    }

    public synchronized void refresh() throws Exception {
        LoadedConfig candidate = source.load();
        validate(candidate.config());
        current = candidate;
    }

    private void validate(AppConfig config) {
        if (config.requestTimeoutMillis() <= 0) {
            throw new IllegalArgumentException(
                    "Request timeout must be positive");
        }
        if (config.databaseUrl() == null
                || config.databaseUrl().isBlank()) {
            throw new IllegalArgumentException(
                    "Database URL is required");
        }
    }
}
~~~

This example illustrates publishing configuration only after reading and validating successfully. current is volatile so threads see the new configuration object. AppConfig is an immutable record, avoiding threads observing an object in a partially updated state.

In a real application, ConfigSource can read a file, database, or config service. LoadedConfig.version can be a revision, generation, or ETag supplied by the authoritative source. If the source does not support versioning, the application must use a suitable freshness-detection mechanism.

Refreshes should not mutate individual fields piecemeal across multiple shared objects without synchronization. If multiple components need the same consistent set of settings, publish a new immutable snapshot for all of them to read.

## 8. Combining Configuration Refresh with a CRaC Resource

If dynamic configuration must be rechecked after restore, you can create a Resource to call ConfigProvider.refresh in afterRestore:

~~~java
import org.crac.Context;
import org.crac.Core;
import org.crac.Resource;

public final class ConfigRefreshResource implements Resource {
    private final ConfigProvider configProvider;

    public ConfigRefreshResource(ConfigProvider configProvider) {
        this.configProvider = configProvider;
        Core.getGlobalContext().register(this);
    }

    @Override
    public void beforeCheckpoint(
            Context<? extends Resource> context) {
        // No need to close ConfigProvider if it only holds snapshots in the heap.
        // If the configuration source has its own connection, the owner of that source
        // needs to manage the connection lifecycle according to its integration.
    }

    @Override
    public void afterRestore(
            Context<? extends Resource> context) throws Exception {
        configProvider.refresh();
    }
}
~~~

This is an example for a configuration source that can be re-queried after restore. If refresh fails, the callback throws an exception so recovery failure is detected. The application should not mark itself ready when mandatory configuration has not been loaded or validated.

Not every ConfigProvider needs a Resource. If configuration is strictly fixed per process with no need for post-restore refresh, the in-heap object can remain unchanged. If the configuration source uses an HTTP client, database connection, or file handle with its own lifecycle, the Resource managing that connection should belong to the component owning the source, avoiding closing/reopening the same resource from multiple callbacks.

### Choosing a sensible restoration order

If ConfigProvider needs an HTTP client to read configuration, the client must be ready before calling refresh. If the client uses credentials fetched from a secret store, the secret must be verified or refreshed before creating the client.

A logical order can be:

~~~text
Restore process
      |
      v
Refresh necessary credentials
      |
      v
Reopen config client
      |
      v
Load and validate dynamic configuration
      |
      v
Create/refresh dependencies using configuration
      |
      v
Health check and readiness
      |
      v
Accept traffic
~~~

Callback ordering across independent Resources must rely on the guarantees of the specific CRaC runtime or framework. If the application needs dependency ordering, use a coordinator component with clear ownership or the framework's lifecycle mechanism.

## 9. Configuration and Secrets in Checkpoints

Environment variables, system properties, and configuration objects can contain sensitive information:

- Database passwords.
- API keys or access tokens.
- Private keys or certificate material.
- Connection strings containing credentials.
- Internal routing information or sensitive service names.

If these values have already been read into the heap, the checkpoint can contain copies of them. Therefore, the checkpoint image and its storage location must be protected as an artifact that may contain secrets.

Some principles:

- Restrict read and write permissions on the checkpoint image.
- Do not log environment variables, system properties, or sensitive config objects.
- Avoid placing secrets in long-lived fields if a refreshable credential provider can be used.
- Verify tokens/credentials after restore if they may expire while the process is paused.
- Rotate secrets following the secret management system's procedures; do not assume deployment environment changes automatically update values in a restored process.
- When a secret is refreshed, refresh clients or pools using the old secret according to library guidelines.

Do not arbitrarily clear secrets from objects currently used by a library without understanding the library's contract. Clearly determine when credentials are consumed, how clients are recreated, and how to stop using old credentials.

## 10. Static Initializers and Read-Once Configuration

Some classes read configuration in a static initializer:

~~~java
public final class FeatureFlags {
    public static final boolean NEW_FLOW =
            Boolean.getBoolean("app.feature.new-flow");

    private FeatureFlags() {}
}
~~~

The value of NEW_FLOW is computed when the class is initialized. Changing the system property later does not recompute the static field. When the checkpoint saves class and static field state, this value can continue being used after restore.

Similarly, a framework may read environment variables or system properties when creating an ApplicationContext and retain them inside beans. Reloading an external file does not automatically refresh beans or static fields.

If a value must change at runtime, avoid reading it once in a static initializer. Use ConfigProvider or an official framework refresh mechanism. If a value only changes upon process restart, explicitly document it as startup-only configuration and start a new process when applying changes.

## 11. Common Post-Restore Scenarios

| Scenario | What can happen | How to handle |
|---|---|---|
| Deployment changes env vars while the process is checkpointed | The restored process can still continue with the old environment | Start a new process to receive the new startup environment, or read dynamic config from another source |
| System.setProperty was called before checkpoint | The JVM restores properties according to the saved state | Re-verify if the property represents a mutable value |
| Config file was modified after checkpoint | Parsed objects in the heap may still hold the old version | Re-read the file, validate, and publish a new snapshot |
| Feature flag changed in config service | The in-heap cache may not have updated yet | Check revision/TTL and refresh |
| Secret expired while checkpointed | Old credential object stays in the heap yet is no longer accepted | Fetch new secret/token and recreate dependent clients |
| Database URL changed | Old DataSource or pool may still point to the old endpoint | Recreate or reconfigure the pool via a safe procedure |
| New configuration is invalid | Refresh can leave half-old, half-new state if fields are updated piecemeal | Parse and validate the snapshot first; publish only when complete |

These cases show that restore requires a clear configuration policy. Do not automatically refresh everything if doing so could unsafely alter business behavior.

## 12. Common Misconceptions

**"When an environment variable changes in the container, System.getenv() updates automatically."**

Normally untrue for a running process. The environment is provided when the process launches; updating orchestrator manifests or secrets does not automatically alter the process environment. Restore also does not create a new process.

**"System properties passed via -D will be re-read on restore."**

Incorrect. -D is processed when the JVM starts. Restore resumes the checkpointed JVM; it does not re-run the command line.

**"The config file changed, so config objects inside Spring beans also change."**

Not automatically. Objects parsed and stored in the heap retain their values until the framework or application performs a refresh.

**"Reloading all configuration after restore is always safe."**

Not necessarily. Some fields are allowed to be set only at startup; hot-swapping them can leave running dependencies inconsistent. Distinguish startup-only from dynamic config.

**"Secrets in the heap are not included in the checkpoint."**

Do not assume that. If a secret was read into an object or system property, the checkpoint can contain a copy in process state. Protect checkpoint artifacts and limit long-lived secrets in the heap.

**"Once ConfigProvider refreshes, every client automatically uses the new configuration."**

Incorrect if clients or pools were already created from the old configuration. The component owning the dependency must run a step to recreate or update it according to the library's contract.

## 13. Testing Configuration Policies

Test on the actual target JDK/CRaC runtime and deployment platform:

- Launch with a specific set of environment variables and system properties, create a checkpoint, and restore.
- Modify files or the config service during the checkpoint window and confirm the refresh policy behaves as expected.
- Change feature flags and verify the new configuration snapshot is published atomically.
- Expire or revoke credentials while the process is paused, then verify the application refreshes clients.
- Make the config service unavailable to verify the callback reports an error and readiness does not open prematurely.
- Supply invalid configuration to confirm the previous snapshot is retained or the application transitions to an error state per policy.
- Perform multiple checkpoint/restore cycles to catch duplicate refreshes, duplicate listeners, or clients still using stale credentials.
- Verify checkpoint artifacts and logs do not leak secrets outside permitted scopes.

Log the active configuration revision, refresh timestamp, and success/failure status. Do not log secret values. Readiness should reflect verified mandatory configuration and dependencies.

## 14. Conclusion

Environment variables, system properties, and application configuration have different lifecycles. Environment variables are typically tied to process launch; system properties belong to JVM state; parsed configuration objects reside in the heap; and files, databases, config services, and secret stores continue changing on external lifecycles.

CRaC restores process state as of checkpoint time, so values stored in the heap may be stale relative to the authoritative configuration source. The application must classify startup-only versus dynamic configuration, identify which values must be refreshed or verified after restore, protect secrets inside checkpoint artifacts, and open traffic only after configuration and mandatory dependencies are ready.