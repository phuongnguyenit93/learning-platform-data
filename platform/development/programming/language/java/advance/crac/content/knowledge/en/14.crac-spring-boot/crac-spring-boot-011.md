# Deferring external service access and loading secrets at the appropriate phase

Spring Boot applications often need to connect to databases, message brokers, external APIs, or secret management services. These dependencies may not be ready when Spring creates the ApplicationContext, may change while the application is being checkpointed, or may have credentials that expire during the time the process is paused. If they are accessed too early, the application may start slowly, fail during bean creation, or save a stale connection and secret into the checkpoint.

With CRaC, the right timing must be chosen for each action: create beans and inspect the application structure at startup; access services when truly needed or at a clearly designed readiness step; load credentials right before creating the connection that depends on those credentials; close or pause resources before checkpoint; and refresh necessary information after restore.

Deferring access does not mean hiding errors indefinitely. The application still needs to decide which dependencies are mandatory to serve requests, which can be initialized on first use, and what happens if the service or secret store is not ready.

## 1. Lifecycle phases in Spring Boot and CRaC

Spring Boot has many initialization phases. Some callbacks run when beans are created; some run after the ApplicationContext has been refreshed; some only run when a lazy bean is requested for the first time.

~~~text
JVM startup
    |
    v
Read environment and system properties
    |
    v
SpringApplication creates ApplicationContext
    |
    v
Create eager singletons and dependencies
    |
    v
Constructor / @PostConstruct / init callback
    |
    v
ApplicationContext refresh
    |
    v
SmartLifecycle and related lifecycle steps
    |
    v
ApplicationRunner / CommandLineRunner
    |
    v
ApplicationReadyEvent and accepting traffic
    |
    v
Preparing checkpoint / CRaC beforeCheckpoint
    |
    v
Checkpoint image
    |
    v
Restore / CRaC afterRestore
    |
    v
Verify dependencies and readiness
    |
    v
Continue accepting traffic
~~~

Key distinctions:

| Phase | Appropriate work | Considerations |
|---|---|---|
| Constructor and field initialization | Store dependencies, check local parameters, create objects without side effects | Should not call secret store or remote API if not necessary |
| @PostConstruct / init callback | Check bean invariants, prepare internal state | Avoid network connections or loading secrets that may expire if the bean is not yet needed |
| ApplicationContext refresh | Complete container structure and initialize eager beans | Mandatory dependencies can be checked here if the policy requires fail-fast |
| ApplicationRunner / CommandLineRunner | Run intentional startup preparation steps | Runs during normal startup; should not be treated as a callback that re-runs automatically after CRaC restore |
| First use | Initialize lazy dependencies when there is actual demand | Needs readiness, timeout, and error handling so the first request does not hang unexpectedly |
| CRaC afterRestore | Refresh secrets, connections, and time-dependent state | Do not assume the entire Spring startup process is re-run |

Checkpoint/restore is not the same as creating a new JVM and re-running SpringApplication. Objects in the ApplicationContext may be restored from the checkpoint; constructors, @PostConstruct, and ApplicationRunner are not automatically re-invoked just because the process is restored. Components that own resources need to participate in the CRaC lifecycle or use the CRaC integration mechanism supported by that version of Spring Boot.

## 2. Why defer external service access?

Creating a bean does not necessarily require opening a network connection. If a constructor or init callback calls a remote service, the following problems can occur:

- Spring startup depends on when the database, broker, or configuration service is ready.
- A non-essential service can prevent the entire ApplicationContext from starting.
- Creating a checkpoint may save a client or open connection that was not properly prepared.
- Connections created before checkpoint may time out or be closed by the peer during the time the process is paused.
- DNS, endpoints, certificates, or access permissions may change before restore.
- A secret loaded at startup may expire or be rotated before the application resumes operation.

A bean should describe how to use a dependency and how to create it. The network access action should be at an intentional step, such as when the dependency is actually used, in a startup preflight, or in a recovery callback after restore.

### Distinguishing object initialization from service connection

A client factory can be created without opening a socket. Conversely, some libraries connect immediately in the constructor or in an initialize step. Read the library's contract to know exactly when the connection is created.

For example, a factory that only holds configuration:

~~~java
public final class RemoteClientFactory {
    public RemoteClient create(SecretMaterial secret) {
        return RemoteClient.connect(secret);
    }
}
~~~

Creating a RemoteClientFactory can be entirely local. The create call is where credentials are obtained and the connection is created. This separation allows Spring to initialize the bean structure without calling external services.

## 3. Using ObjectProvider to obtain dependencies when needed

Spring provides ObjectProvider to defer obtaining a bean until the application calls getObject(). This is an explicit way to avoid requesting a lazy dependency right in the constructor of an eager singleton.

~~~java
import org.springframework.beans.factory.ObjectProvider;
import org.springframework.stereotype.Service;

@Service
public final class ReportService {
    private final ObjectProvider<RemoteReportClient> clients;

    public ReportService(ObjectProvider<RemoteReportClient> clients) {
        this.clients = clients;
    }

    public Report loadReport(String reportId) {
        RemoteReportClient client = clients.getObject();
        return client.fetch(reportId);
    }
}
~~~

Here, ReportService can be created during startup without requesting RemoteReportClient. When loadReport is called, Spring then resolves the RemoteReportClient bean. If that bean establishes a connection during initialization, the connection will be deferred until this resolution.

ObjectProvider also has methods like getIfAvailable() or getIfUnique() for cases where the dependency is optional. These methods should not be used to silently skip a mandatory dependency; if there is no client and the business logic cannot continue, report the error explicitly.

### ObjectProvider and @Lazy

@Lazy can defer bean creation until it is requested. However, there is an easily overlooked point: if an eager singleton needs a lazy bean in its constructor, Spring still has to provide the dependency to complete the singleton. In that case, the lazy bean may be created right during startup.

@Lazy can be used at the injection point so that Spring creates a proxy that defers resolving the target:

~~~java
import org.springframework.context.annotation.Lazy;
@Service
public final class LazyReportService {
    private final RemoteReportClient client;

    public LazyReportService(@Lazy RemoteReportClient client) {
        this.client = client;
    }

    public Report load(String id) {
        return client.fetch(id);
    }
}
~~~

ObjectProvider usually makes the timing of dependency retrieval more explicit and allows control over whether to request the bean or not. @Lazy is suitable when you want to use the dependency through a proxy like a regular object. Both approaches only defer bean initialization; they do not automatically manage credential rotation, reconnect, timeout, or CRaC lifecycle.

Global lazy initialization should not be enabled just to avoid connection errors. That approach may shift startup errors to the first request and leave mandatory dependencies unchecked when the application reports ready. Apply lazy selectively for dependencies that can genuinely be deferred.

## 4. Choosing when to access services based on criticality

Not all dependencies should be initialized at the same time.

| Dependency type | Appropriate timing | Policy when not ready |
|---|---|---|
| Database mandatory for handling all requests | Startup preflight or before readiness; recreate connection after restore | Do not accept business traffic when database is not ready |
| Payment gateway used only for some functions | When the payment function is called or in a readiness specific to that function | Reject/limit the dependent function, keep the rest operational if the business allows |
| Optional reporting service | When the user requests a report or via a separate job | Return a controlled unavailable status, retry with limits |
| Secret store | When a secret is needed to create a client or refresh credentials | Do not create dependent client if a valid secret is not available |
| Message broker consumer | When the application is ready to receive messages and after restore | Do not resume consumer until connection and subscription are valid |

For mandatory dependencies, deferral does not mean skipping validation. The application can check the connection in a startup gate or before opening traffic. For optional dependencies, lazy initialization can reduce startup time and avoid making the entire application dependent on a non-essential service.

Distinguish between liveness and readiness. Liveness indicates the process is still running; readiness indicates the instance can accept the type of work it is assigned. A process can be alive but not ready because it has not loaded secrets or has not connected to the database.

## 5. Loading secrets at the right time

Secrets typically include database passwords, API tokens, private keys, certificates, or broker credentials. Secrets can be provided via environment variables, file mounts, workload identity, Vault/secret manager, or internal services.

Loading secrets too early can:

- Make startup depend on the secret store even if the client does not yet need it.
- Keep credentials in the heap longer than necessary.
- Put stale secrets into the checkpoint image.
- Use an expired token after the process is restored.
- Continue using an old password after the secret has been rotated.

Loading secrets too late without readiness can also cause the first request to fail or wait too long. Therefore, the timing of obtaining a secret should be tied to the timing of creating or refreshing the client that depends on it.

### Distinguishing bootstrap identity from application secrets

To read secrets from a secret manager, the application typically needs an initial authentication mechanism, for example workload identity, cloud role, service account, or platform-issued credentials.

These two types of information serve different roles:

- **Bootstrap identity:** helps the application prove its identity to the secret manager.
- **Application secret:** credentials the application retrieves from the secret manager to connect to databases, brokers, or APIs.

A circular dependency should not be created: needing the database password to connect to the secret manager, while the database password can only be obtained from that very secret manager. Use a platform-provided identity bootstrap or an independent initialization mechanism with appropriate protection.

After restore, the bootstrap identity may also expire or need refreshing. The SecretProvider needs to verify the current identity before reading application secrets.

### Not keeping secrets longer than necessary

The number of places that store copies of secrets should be limited:

- Avoid logging secrets or entire configurations containing secrets.
- Avoid storing secrets in static fields or singletons without a clear need.
- Do not put secrets in exception messages.
- Use data types and APIs from the secret provider to limit unnecessary copies.
- Close or clear mutable buffers according to the library's contract when done using them.

Java Strings are immutable and their content cannot be actively overwritten. Converting secrets to Strings can increase the number of copies and their lifetime in the heap. If the library supports it, consider char[] or a secret type with an explicit lifecycle. However, clearing a buffer does not guarantee that all copies created internally by the library are also cleared.

The checkpoint image may contain secrets that have been read into the heap. Protect the access, storage, and distribution of checkpoint images as artifacts that may contain authentication information.

## 6. Designing SecretProvider and client factory

Separating secret retrieval from client usage allows the application to refresh credentials and recreate connections when needed.

~~~java
public interface SecretProvider {
    SecretMaterial load() throws Exception;
}

public interface SecretMaterial extends AutoCloseable {
    char[] credential();

    @Override
    void close();
}

public interface RemoteClient extends AutoCloseable {
    void send(String payload) throws Exception;

    @Override
    void close() throws Exception;
}

public interface RemoteClientFactory {
    RemoteClient connect(SecretMaterial secret) throws Exception;
}
~~~

SecretProvider is responsible for authenticating with the secret store and returning a valid secret. RemoteClientFactory receives a secret to create a client. These interfaces are contracts defined by the application; the actual implementation depends on the platform and library.

An important point is that the factory should create a client after receiving a valid secret. Secrets should not be read in a bean's constructor just because Spring is creating that bean.

## 7. Example: Resource deferring connection and reloading secrets after restore

The following example uses ObjectProvider to only obtain SecretProvider and RemoteClientFactory when a client actually needs to be opened. The Resource is registered early with CRaC, but the connection and application secret loading are deferred.

~~~java
import org.crac.Context;
import org.crac.Core;
import org.crac.Resource;
import org.springframework.beans.factory.ObjectProvider;

public final class RemoteClientManager implements Resource {
    private final ObjectProvider<SecretProvider> secretProviders;
    private final ObjectProvider<RemoteClientFactory> factories;

    private RemoteClient client;
    private boolean reopenAfterRestore;

    public RemoteClientManager(
            ObjectProvider<SecretProvider> secretProviders,
            ObjectProvider<RemoteClientFactory> factories) {
        this.secretProviders = secretProviders;
        this.factories = factories;

        // Register manager; secret is not loaded and connection is not opened yet.
        Core.getGlobalContext().register(this);
    }

    public synchronized void send(String payload) throws Exception {
        RemoteClient active = client;
        if (active == null) {
            active = openClient();
        }
        active.send(payload);
    }

    private RemoteClient openClient() throws Exception {
        SecretProvider provider = secretProviders.getObject();
        RemoteClientFactory factory = factories.getObject();

        try (SecretMaterial secret = provider.load()) {
            RemoteClient created = factory.connect(secret);
            client = created;
            return created;
        }
    }

    @Override
    public synchronized void beforeCheckpoint(
            Context<? extends Resource> context) throws Exception {
        reopenAfterRestore = client != null;

        if (client != null) {
            client.close();
            client = null;
        }
    }

    // Called by the checkpoint coordinator if the checkpoint preparation
    // is cancelled and the current process continues running instead of being restored.
    public synchronized void resumeAfterCheckpointFailure()
            throws Exception {
        if (reopenAfterRestore && client == null) {
            openClient();
            reopenAfterRestore = false;
        }
    }

    @Override
    public synchronized void afterRestore(
            Context<? extends Resource> context) throws Exception {
        if (reopenAfterRestore) {
            openClient();
            reopenAfterRestore = false;
        }
    }
}
~~~

In this example:

- RemoteClientManager is created and registered with the global context but does not access the secret store.
- ObjectProvider defers obtaining SecretProvider and RemoteClientFactory.
- The first call to send obtains the secret and creates the client.
- beforeCheckpoint closes the client if it has been used.
- afterRestore creates a new client with a secret reloaded from the provider, rather than relying on old credentials.
- If the client was never opened before checkpoint, the manager does not need to create a connection just for the checkpoint; the first use after restore will open the client.

The example assumes the factory consumes or copies the necessary credentials during connect and does not hold a reference to the closed SecretMaterial. The actual implementation must follow the SDK's contract; if the client needs long-lived secrets, use the SDK's credential provider/refresh API or a credential management mechanism with an explicit lifecycle.

The code also assumes the application has stopped admission and drained send calls before beforeCheckpoint closes the client. synchronized only protects calls going through the same manager; it does not stop another thread that directly holds a reference to the client or calls an adapter outside the manager.

If the checkpoint preparation is cancelled after beforeCheckpoint has closed the client, the original process may continue running without afterRestore. The checkpoint coordinator needs to call a recovery path like resumeAfterCheckpointFailure(), verify that the client is operational, and only then reopen admission. If reopening fails, keep the application in a not-ready state.

### Registering the manager in Spring Boot

The manager can be created as an eager bean so it registers the Resource from startup, while the dependencies that actually access the network are still deferred:

~~~java
import org.springframework.beans.factory.ObjectProvider;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
public class RemoteClientConfiguration {
    @Bean
    RemoteClientManager remoteClientManager(
            ObjectProvider<SecretProvider> secretProviders,
            ObjectProvider<RemoteClientFactory> factories) {
        return new RemoteClientManager(secretProviders, factories);
    }
}
~~~

The manager is created during ApplicationContext initialization and registered with CRaC. SecretProvider and RemoteClientFactory are only resolved when openClient calls getObject(). Ensure that those beans themselves are not requested by another eager component before the desired time.

If the manager is also marked @Lazy, it may not be created and may not register the Resource before checkpoint. Only use that approach if there is a mechanism to ensure the manager is initialized before CRaC starts the checkpoint.

In an application using Spring Boot CRaC integration, check the documentation of the specific Spring Boot version to know how Resources are discovered, registered, and coordinated. Avoid double registration or manually closing a client whose lifecycle is already managed by the framework/library.

## 8. Should secrets be loaded at startup, first use, or afterRestore?

There is no single timing suitable for all secrets. Choose based on the dependency's lifecycle:

| Case | When to obtain secret | Reason |
|---|---|---|
| Credential mandatory for all requests to work | Startup gate or before readiness; refresh after restore | Confirm instance is not ready if unable to access mandatory dependency |
| Credential for a rarely used function | First time the function is called, with appropriate cache/TTL | Do not delay startup for an optional dependency |
| Short-lived token | Right before creating the client or before the token expires | Reduce the risk of checkpoint holding an expired token |
| Credential with rotation | Via a provider that can refresh; check version/expiry after restore | Do not continue using an old secret after the source has rotated |
| Secret used only to create a long-lived client | When creating or refreshing the client | Limit the time the secret exists in the application |
| Secret used for multiple clients | Via a provider/cache with TTL and invalidation policy | Avoid unnecessary multiple accesses to the secret store while still handling rotation |

If a dependency is mandatory for the application to serve traffic, the secret can be loaded and the client created before readiness. This is still intentional external access, with explicit timeout and fail-fast. If the dependency is optional, lazy access may be more appropriate.

Secrets should not be fetched on every request if the secret store has latency or rate limits. Use a cache with TTL, versioning, or refresh-ahead when appropriate; ensure the cache does not outlast the credential's validity period and can be invalidated after restore.

## 9. Startup runner, ApplicationReadyEvent, and SmartLifecycle

Spring Boot provides many lifecycle hooks, but they serve different purposes:

- Constructor and @PostConstruct are suitable for local initialization, parameter checking, and invariants.
- ApplicationRunner and CommandLineRunner are suitable for intentional startup preparation steps after the ApplicationContext is created.
- ApplicationReadyEvent indicates that normal startup has completed and the application is about to accept traffic.
- SmartLifecycle manages components with start/stop according to the ApplicationContext lifecycle.
- CRaC Resource or the corresponding integration manages actions before checkpoint and after restore.

ApplicationReadyEvent should not be used as a callback to replace afterRestore. Restoring a checkpoint does not mean re-running SpringApplication and replaying all startup events. If secrets need to be reloaded or clients reopened after restore, attach that action to the CRaC lifecycle.

SmartLifecycle can be useful for starting/stopping consumers or listeners within the ApplicationContext lifecycle. However, a bean implementing SmartLifecycle does not by itself prove it will receive callbacks after restore. If used together with CRaC, explicit integration or Resource coordination is needed.

## 10. Readiness, timeout, and error handling

Deferring dependencies changes when errors appear. Without readiness design, the application may report ready while the client has not been created, and only the first request discovers that the secret store or remote service is not operational.

Classify dependencies:

- **Mandatory:** if this dependency is absent, business requests cannot succeed. Only open readiness after the connection and credentials have been verified.
- **Optional:** the dependent function can return a controlled error or be disabled, while the rest continues serving.
- **Recoverable:** retry with backoff and time limits, while keeping the corresponding function in a not-ready state.

Each external access needs a connection timeout and an operation timeout. Do not let an afterRestore callback wait indefinitely when the secret store or remote service is not responding. Retries should have limits, backoff, and jitter to avoid multiple instances creating a sudden load spike after restore.

If loading a secret fails:

1. Do not create a client with empty credentials or old credentials that have expired.
2. Keep the dependency in an unavailable state.
3. Report an error with context but without containing the secret value.
4. Do not open readiness for the dependent function.
5. Allow retry according to the operational policy.

If a client has been created but the authentication or handshake step fails, close the incomplete client and release resources. Do not publish a partial client to other threads.

## 11. Recovery order of dependencies

A client may depend on a secret provider, DNS, TLS trust material, connection pool, or dynamic configuration. After restore, recovery must follow dependency order:

~~~text
Restore process
       |
       v
Restore bootstrap identity
       |
       v
Connect to secret/config provider
       |
       v
Load and verify current secret
       |
       v
Recreate remote client / connection pool
       |
       v
Health check and readiness
       |
       v
Resume consumer / accept traffic
~~~

The order of callbacks between multiple independent Resources should not be relied upon if the CRaC runtime or framework does not guarantee that order. When there are dependencies, use a coordinating Resource with clear ownership or an ordered lifecycle mechanism. If the library already has CRaC integration, follow the library's guidance and avoid duplicate callbacks.

Before checkpoint, the shutdown order typically goes in reverse of the startup order: stop traffic and consumers, drain requests, close clients, then close the configuration/secret client source if they need to be closed. Do not close the secret provider before the dependent client has completed its necessary preparation step.

## 12. Spring Boot configuration and secrets in the environment

Spring Boot can bind environment variables or system properties to @ConfigurationProperties when the ApplicationContext initializes. Configuration objects that have been bound may persist in the heap after checkpoint.

For example:

~~~java
import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "remote.service")
public record RemoteServiceProperties(
        String endpoint,
        String username,
        String password) {}
~~~

This is a configuration snapshot at the time of binding. If the secret or endpoint changes externally during the time the process is paused, the bound properties object does not update itself. If rotation is needed, use a SecretProvider or an official refresh mechanism with explicit versioning and lifecycle.

Updating the container's environment should not be treated as a way to refresh the environment inside a running or restored process. The environment is typically provided when the process starts. If new credentials are needed, read from the secret provider or create a new process according to the deployment policy.

If using @ConfigurationProperties to bind secrets, ensure the object is not logged by toString(), actuator endpoints, or diagnostic dumps. With records, the default toString() may print the fields; avoid using records containing secrets if the output could be logged. Consider separating secrets from regular properties or customizing the representation to mask sensitive values.

## 13. Common misconceptions

**"Marking a bean @Lazy means all network access is deferred."**

Not necessarily. The bean may be requested by an eager singleton or another startup step. @Lazy defers bean creation until it is resolved; it does not automatically manage all side effects inside the bean. Use ObjectProvider if you want explicit control over when resolution happens.

**"Constructor or @PostConstruct is a good place to connect all services."**

Not always. These callbacks run during bean creation and can make the entire ApplicationContext depend on external services. Only do this when it is a mandatory startup condition and there is explicit timeout/fail-fast.

**"ApplicationRunner will re-run after restore."**

No. Runners belong to the normal startup of Spring Boot. Restore does not re-initialize the ApplicationContext. Use CRaC Resource or the appropriate integration to recover resources.

**"Secrets bound to ConfigurationProperties will update automatically when the secret store rotates."**

Not automatically. The bound bean is a snapshot in the heap. A provider/refresh mechanism is needed along with updating the dependent client.

**"Old secrets can be used as long as the client object still exists."**

Not guaranteed. Tokens can expire, passwords can be rotated, or permissions can be revoked. After restore, verify credentials and recreate the client when needed.

**"Rollback or closing the client will erase all side effects."**

Not true. Sending emails, publishing messages, or writing external data may have already completed. Do not call adapters that cause side effects during warmup or lifecycle preparation without a clear policy.

**"Just reconnecting after restore is enough."**

A new connection may still need new secrets, new configuration, TLS handshake, subscription, or lease ownership. Recovery needs to consider the entire dependency chain.

## 14. Testing deferral and secret reloading

Testing should be performed on the exact Spring Boot version, JDK/CRaC runtime, secret provider, and client library being used:

- Start the ApplicationContext and confirm the manager bean is created without calling the secret store.
- Call the function for the first time and confirm the secret is only loaded at the expected time.
- Make the secret store slow or unavailable to test timeout and readiness state.
- Change credentials while the process is checkpointed then restore; confirm the new client uses the current secret.
- Make old credentials expire or be revoked and confirm the old client is not continued to be used.
- Make the remote service unavailable during afterRestore and confirm the application does not open traffic too early.
- Check that close/reopen callbacks do not run redundantly and do not leak connections.
- Check that optional dependencies do not break independent functions.
- Check that logs, exceptions, actuator, and checkpoint artifacts do not expose secrets beyond the allowed scope.
- Perform multiple checkpoint/restore cycles to detect unregistered managers, stale clients still alive, or secret caches not being refreshed.

Do not only check that the ApplicationContext starts successfully. Confirm the timing of secret provider calls, when connections are opened, behavior during restore, and the readiness state before accepting requests.

## 15. Conclusion

In Spring Boot, constructors, @PostConstruct, ApplicationRunner, ApplicationReadyEvent, SmartLifecycle, and CRaC Resource serve different phases. Not all external service access and secret loading should be placed at bean creation time. Defer dependency resolution using ObjectProvider or a controlled lazy mechanism, then load credentials right before creating or refreshing the client.

With CRaC, remember that the ApplicationContext is restored along with the process state; normal startup hooks do not automatically re-run. Components that own remote clients should close before checkpoint and refresh secrets, creating connections after restore in the correct dependency order. Readiness should only be opened when credentials and mandatory services have been verified, and checkpoint images and logs must be protected as places that may contain sensitive information.
