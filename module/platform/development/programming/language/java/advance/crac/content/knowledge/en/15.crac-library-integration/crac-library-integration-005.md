# Cloud SDKs, credential providers, and connection caching

Java applications commonly use cloud provider SDKs to access object storage, databases, message queues, secret managers, or management APIs. An SDK client may hold multiple internal resources: credential providers, token caches, HTTP connection pools, sockets, TLS sessions, DNS caches, event loops, executors, and credential refresh threads.

When an application uses CRaC (Coordinated Restore at Checkpoint), these resources must be evaluated against the process lifecycle. A checkpoint may be created before deployment and restored many minutes or hours later. During that interval, access tokens may expire, roles or workload identities may change, DNS may point to a different endpoint, sockets may be closed by the peer or NAT, and connection pools may hold unusable connections.

Therefore, do not treat an SDK client still existing in the heap after restore as proof that it can still invoke cloud services. Identify who owns the client, credential provider, and HTTP transport; stop running requests before checkpoint; refresh identity and connections after restore according to the SDK documentation; and verify service connectivity before opening traffic.

## 1. Components inside a cloud SDK client

A cloud SDK client is typically a facade that business code calls to execute requests. Behind the facade, there may be several components:

- **Credential provider:** Obtains credentials from environment variables, configuration files, workload identity, metadata services, role services, or secret managers.
- **Credential/token cache:** Holds access keys, session tokens, OAuth tokens, or temporary credentials to avoid fetching them for every request.
- **HTTP transport:** Executes HTTP/HTTPS requests and manages sockets, TLS, and network protocols.
- **Connection pool:** Reuses connections, caps concurrent connections, and manages idle connections.
- **Retry and timeout policy:** Determines when to retry requests, wait durations, and error handling.
- **Executor/event loop:** Runs asynchronous requests, callbacks, or internal tasks.
- **Endpoint and region resolver:** Resolves service addresses, regions, proxies, or custom endpoints.
- **Metrics, tracing, and signer:** Measures requests, signs requests, and attaches security metadata.

~~~text
Business code
    |
    v
Cloud SDK client
    |
    +---- Credential provider
    |         |
    |         +---- Credential/token cache
    |         +---- Metadata / STS / OAuth / workload identity
    |
    +---- Request signer
    |
    +---- Retry / timeout / endpoint resolver
    |
    +---- HTTP transport
              |
              +---- Connection pool
              +---- DNS / TLS / socket
              +---- Executor / event loop
    |
    v
Cloud service
~~~

Not every SDK has this exact structure. Some components are built into the client; some are shared across multiple clients; some are supplied by an external HTTP library. When planning for CRaC, use the documentation and dependency tree of the exact SDK version to identify ownership boundaries.

## 2. An SDK client should typically outlive a single request

Many Java SDK clients are designed to be reused across threads and requests. Creating a new client for every invocation increases overhead from initialization, DNS lookups, TLS handshakes, pool creation, and fetching credentials. The common pattern is to create the client according to the application lifecycle or endpoint/region configuration, and then inject it into services.

Example of organizing a bean:

~~~java
@Configuration
public class CloudClientConfiguration {
    @Bean(destroyMethod = "close")
    public ObjectStorageClient objectStorageClient() {
        return ObjectStorageClient.builder()
                .region(Region.of("ap-southeast-1"))
                .build();
    }
}
~~~

ObjectStorageClient and Region in the example are illustrative names, not APIs of a specific SDK. With a real SDK, use the builder and close method supported by the vendor's documentation.

Do not create a new client for each request if the SDK is designed to be shared. Equally, do not keep a singleton client forever without managing closing, replacement, or recovery when the environment changes. With CRaC, a singleton still has its own lifecycle: the client may need to be kept, partially refreshed, closed and recreated, or handled automatically by the library via official integration.

## 3. What is a credential provider?

A credential provider is the component responsible for supplying credentials for requests. Business code generally should not read access keys itself and assemble them into every request. Instead, the SDK asks the provider when signing requests or authenticating with the service.

Common credential sources:

| Source | How it works | Points to watch out for |
|---|---|---|
| Environment variables | Reads values from environment variables | Secrets may be baked into the container or checkpoint image |
| Profile/configuration file | Reads configuration files on the host or container | File paths, permissions, and contents may change |
| Instance/pod metadata | Fetches credentials from the runtime environment's metadata endpoint | Metadata endpoints and access tokens depend on the runtime |
| Workload identity | Exchanges workload identity for temporary credentials | Token exchange and trust policies must work after restore |
| STS/role assumption | Requests time-bounded session credentials | Credentials must refresh before expiring |
| OAuth/OIDC provider | Obtains access tokens from an authorization server | Refresh tokens, client assertions, and token caches have separate lifecycles |
| Secret manager | Reads secrets from a secret management service | Secrets may be rotated or policies may change |

Providers may return static credentials or temporary credentials. Temporary credentials usually have an expiration timestamp and can be refreshed automatically. A provider may maintain a cache to avoid calling the metadata service or STS too frequently.

## 4. Credential chains and identity selection order

Some SDKs provide a default credential chain. The chain tries multiple sources in order until a valid credential is found. The exact order depends on the SDK, version, and environment. Conceptual example:

~~~text
Environment credentials
        |
        v
Profile / shared config
        |
        v
Workload identity / web identity
        |
        v
Container credentials endpoint
        |
        v
Instance metadata credentials
        |
        v
Custom-configured credential provider
~~~

This diagram only describes an illustrative chain. Not every SDK has these exact steps or this exact order. Consult the documentation for the provider in use.

A credential chain may select a different source after restore if the environment has changed. For example, a process checkpointed on a build machine might see that machine's profile file; after restoring in a production container, that profile file may not exist or the intended identity comes from workload identity. If the chain already cached credentials or picked a provider at startup, environment changes do not necessarily make the chain re-select a source on its own.

Therefore, identify the intended identity for each environment. For cloud workloads, prefer workload-bound or role-based identity mechanisms recommended by the provider rather than baking long-lived access keys into the image. Verify whether the provider can re-resolve credentials after restore or needs to be recreated.

## 5. Temporary credentials and token lifetimes

Temporary credentials typically consist of an identifier, a secret or access token, a session token, and an expiration timestamp. A provider may cache credentials in memory and refresh only when approaching expiration.

Example:

~~~text
Current credential
  issuedAt  = 10:00
  expiresAt = 11:00

Checkpoint created at 10:20
Image stored until 12:30
Restore at 12:30

Credential in heap: expired
Credential needed: fetch fresh from provider/identity service
~~~

If the first request after restore uses an expired credential, the SDK may return an authentication error. Some providers auto-refresh when they detect credentials are near expiration; some refresh only when invoked; some require an executor or background refresh thread. Exact behavior depends on the provider.

Do not assume every credential provider automatically refreshes immediately after restore. Check:

- Does the provider store the expiration timestamp?
- Does the cache check expiration before returning credentials?
- Is refresh triggered within a safety window ahead of expiry?
- Is refresh triggered by requests or by a background task?
- Does refreshing require a dedicated executor?
- When refresh times out, does the provider return stale credentials or throw an error?
- Is there a way to force the provider to re-resolve credentials or create a new provider?

If the SDK provides a refresh, reload, or close API for the provider, use the documented API. Otherwise, you may need to create a new provider after restore and replace the provider/client according to the application lifecycle.

## 6. Do not bake long-lived secrets into checkpoints

Checkpoints may contain heap data and runtime state. If credentials, access tokens, refresh tokens, or private keys were loaded into memory before the checkpoint, they may appear in the image depending on the checkpoint mechanism and scope.

Checkpoint images must therefore be protected like data that may contain secrets. Restrict read permissions, encrypt at rest and in transit, control retention duration, log access, and purge artifacts per policy. Never write credentials to logs to diagnose restore errors.

Design principles:

- Prefer workload identity or temporary role credentials.
- Avoid placing long-lived secrets in environment variables when safer credential delivery exists.
- Do not take checkpoints when holding credentials in the heap is unnecessary.
- Refresh credentials after restore if tokens can expire or identity depends on the instance.
- Do not share a single snapshotted token as a common identity across multiple replicas.
- Restrict access to checkpoint artifacts and distribution pipelines.
- If a secret is exposed via an artifact, treat it as a credential incident: revoke or rotate according to provider policy.

A credential provider and a credential value are two different things. Keeping a provider object may be fine if it can re-resolve credentials safely; that does not mean cached credentials inside the provider should be kept as-is.

## 7. Workload identity and metadata services

On cloud platforms, applications often fetch credentials from a metadata service or identity endpoint bound to the VM, container, or workload. The provider sends requests to an internal endpoint to receive temporary credentials.

Upon restore, the metadata endpoint or metadata protection token may depend on the network namespace, link-local address, container identity, or current node. A request prepared before the checkpoint may no longer be valid after restore.

Verify:

- Does the SDK/provider support the deployed workload identity type?
- Is the metadata endpoint reachable from the container after restore?
- Is the token required to call the metadata endpoint refreshed?
- Do any proxies or network policies affect the internal endpoint?
- Does the identity after restore match the intended service account/role?
- Does the provider cache endpoints or credentials by old instance?

Do not hardcode a cloud provider's metadata endpoint when the SDK provides an appropriate provider. Endpoints and security requirements can differ by platform, region, and configuration. Use official integration and verify with a credential-fetch operation that produces no side effects.

## 8. Token refresh and background refresh threads

Some credential providers refresh tokens in the background before expiration. This prevents requests from waiting on token exchanges. However, the refresh thread may be running, waiting, or holding sockets when a checkpoint occurs.

Before checkpoint, know:

- Does the provider have a background refresh scheduler?
- Is a refresh operation currently running?
- Is there a pending metadata/STS/OAuth request?
- Can the refresh thread be paused via an official API?
- Does the provider or executor need to be closed?
- Can the provider restart after restore, or must it be recreated?

After restore, do not rely on a previously saved timer to determine when to refresh. The process may have been stopped longer than the token lifetime. Let the provider check expiration against current wall-clock time and force fresh resolution if the API supports it.

If the provider has no CRaC integration, an application-owned adapter can stop new refreshes, wait for in-flight refreshes to complete, and then close or mark the provider for recreation. Do not call private methods via reflection to control internal schedulers.

## 9. What is an HTTP connection pool?

An HTTP connection pool manages network connections reusable across multiple requests. Instead of opening a TCP connection and performing a TLS handshake for every request, the client borrows an available connection, sends the request, and returns the connection to the pool.

A pool typically manages:

- Maximum connection count.
- Idle connection count and idle retention time.
- Connection acquisition wait timeout.
- Connect and socket read/write timeouts.
- Keep-alive and connection reuse.
- Connection health/validation.
- HTTP/1.1 connections or HTTP/2 connections/streams.
- Threads, event loops, and callbacks for asynchronous I/O.

Pools improve performance but hold network-bound state. A socket may be closed by the server, load balancer, NAT, or firewall while the process is checkpointed. Upon restore, the connection object may remain in the heap while the physical connection is dead or no longer valid.

## 10. Why can a connection pool become stale after restore?

Suppose an SDK client holds 20 idle connections. The application takes a checkpoint and stays paused for 45 minutes. During that time:

- The server may close keep-alive connections.
- NAT or firewalls may drop state mappings.
- Load balancers may switch backends.
- DNS may change addresses.
- TLS sessions or certificates may expire or be rotated.
- Proxies may change or require re-authentication.
- Cloud endpoints may change zones or routes.

After restore, the pool may hand out a connection the client believes is still open. The first request may encounter connection reset, broken pipe, EOF, timeout, or TLS errors.

Some HTTP clients perform stale connection checks, idle eviction, or automatic removal of failed connections. However, do not assume every pool detects every case. Read the HTTP transport documentation and test with your exact SDK version.

## 11. Who owns the HTTP transport and connection pool?

An SDK client may create a default HTTP transport itself, or receive an HTTP client/transport shared by the application. Ownership boundaries directly affect closing and recreation.

| Model | Common owner | Notes |
|---|---|---|
| SDK creates transport itself | SDK client | Closing the client may also close the transport and pool |
| Application passes shared transport | Application or config bean | Closing one SDK client may not be allowed to close the shared transport |
| Multiple SDK clients share a transport | Transport config component | Close clients first, then close the transport in order |
| Async SDK uses its own event loop | SDK or executor owner | Drain requests and handle threads/event loops |
| Framework-managed HTTP transport | Spring/container or integration | Follow framework lifecycle, avoid double closing |

Do not call close() in multiple places on the same transport if ownership is unclear. One client may merely borrow an application-owned transport; another client may own its transport directly. Confirm the close/dispose contract in the SDK and HTTP library documentation.

## 12. Choosing between keeping, refreshing, or recreating the client

No single action fits every SDK. Options fall into three groups:

| Strategy | When appropriate | What to verify |
|---|---|---|
| Keep client and let SDK self-recover | SDK/transport has CRaC support or docs confirm socket/token handling after restore | Compatibility, integration callbacks, and connection error testing |
| Keep client, refresh credentials, and evict stale connections | Client/provider has a refresh API or pool has a supported recovery API | Thread safety, in-flight request state, and refresh ordering |
| Close client/transport and create a new client | SDK or transport does not support continuing with old resources, or docs recommend recreating | Owner, atomic client replacement, request gate, and cleanup |

Do not arbitrarily close the client inside a callback if the SDK integration already manages it. Conversely, do not retain the client just because the object still exists. Choose the strategy based on the documentation for the exact SDK version and HTTP transport.

## 13. Before checkpoint: stop requests and drain SDK calls

A cloud request may be uploading an object, writing a message, creating a resource, or awaiting a response. If a checkpoint happens mid-operation, the outcome on the service side may be uncertain.

A quiesce workflow may include:

1. Stop accepting new requests or stop dispatching new jobs to workers.
2. Wait for running SDK calls to complete within a time limit.
3. Cancel or bring long-running operations to a retryable state if waiting is impossible.
4. Handle open multipart uploads, streaming bodies, and response bodies.
5. Wait for in-flight credential refreshes to finish or stop per provider API.
6. Close the client/transport if required by the strategy.
7. Confirm no operations are still using the pool or credential provider.
8. Permit checkpointing only once all owners report ready.

Do not merely wait for HTTP threads to finish while ignoring uncompleted async callbacks, streams, or futures. An SDK call can return a CompletableFuture while the request is still running. Track active operations at the application layer.

## 14. After restore: refresh identity before opening traffic

After restore, the typical recovery order is:

1. Re-read instance-dependent identity and configuration.
2. Resolve fresh credentials or force the provider to refresh.
3. Recreate the HTTP transport/connection pool if needed.
4. Recreate the SDK client if the old client was closed or keeping it is unsupported.
5. Perform a lightweight health check that creates no side effects.
6. Open workers and ingress once dependencies are ready.

If the SDK client depends on a credential provider, the provider must be ready before the client issues requests. If the client was constructed with a refreshable provider reference, keeping the client may work by design; if the client holds an immutable credential snapshot, recreating the client may be required.

Not every SDK fetches credentials on every request. Some sign requests using a dynamic provider; some store credentials in a signer or client config; some use internal token caches. Check how the specific SDK obtains credentials to decide whether rebuilding the client is necessary.

## 15. Example: managing an SDK client with a replaceable factory

A general design is placing the client in an application-owned holder. The holder is responsible for creating, replacing, and closing the client. Business code retrieves the current client via the holder.

~~~java
public interface CloudClient extends AutoCloseable {
    void healthCheck() throws Exception;

    @Override
    void close() throws Exception;
}

public interface CloudClientFactory {
    CloudClient createWithCurrentIdentity() throws Exception;
}

public final class CloudClientHolder {
    private final CloudClientFactory factory;
    private volatile CloudClient current;

    public CloudClientHolder(CloudClientFactory factory) {
        this.factory = factory;
    }

    public synchronized void initialize() throws Exception {
        if (current == null) {
            current = factory.createWithCurrentIdentity();
        }
    }

    public CloudClient current() {
        CloudClient client = current;
        if (client == null) {
            throw new IllegalStateException("Cloud client is not ready");
        }
        return client;
    }

    public synchronized void replace() throws Exception {
        CloudClient replacement = factory.createWithCurrentIdentity();
        try {
            replacement.healthCheck();
        } catch (Exception ex) {
            replacement.close();
            throw ex;
        }

        CloudClient previous = current;
        current = replacement;

        if (previous != null) {
            previous.close();
        }
    }

    public synchronized void closeCurrent() throws Exception {
        CloudClient previous = current;
        current = null;
        if (previous != null) {
            previous.close();
        }
    }
}
~~~

This is an illustrative abstraction. Real clients may not implement AutoCloseable, may have a close() method that throws no checked exception, or may use a shared transport. Adapt to the real API. The example also requires a request gate or reference management if requests are actively using the old client during replacement; do not close the old client before operations have drained.

A client-replacing holder lets the application avoid reinitializing the entire Spring ApplicationContext. However, all services must use the holder or a stable proxy; if a service keeps a direct reference to the old client, replacing the holder does not update that reference.

## 16. Example CRaC Resource for a cloud client

A Resource can coordinate the holder's lifecycle. The example below assumes the application already has a request gate to block new operations and wait for running operations to finish.

~~~java
import org.crac.Context;
import org.crac.Core;
import org.crac.Resource;
import org.springframework.stereotype.Component;

@Component
public final class CloudClientCracResource implements Resource {
    private final CloudRequestGate requestGate;
    private final CloudClientHolder clientHolder;
    private final CredentialLifecycle credentials;

    public CloudClientCracResource(
            CloudRequestGate requestGate,
            CloudClientHolder clientHolder,
            CredentialLifecycle credentials) {
        this.requestGate = requestGate;
        this.clientHolder = clientHolder;
        this.credentials = credentials;
    }

    @PostConstruct
    public void register() {
        Core.getGlobalContext().register(this);
    }

    @Override
    public void beforeCheckpoint(Context<? extends Resource> context)
            throws Exception {
        requestGate.stopNewCalls();
        requestGate.awaitInFlightCalls();
        credentials.stopRefreshAndWait();
        clientHolder.closeCurrent();
    }

    @Override
    public void afterRestore(Context<? extends Resource> context)
            throws Exception {
        credentials.resolveFreshIdentity();
        clientHolder.initialize();
        clientHolder.current().healthCheck();
    }

    public interface CloudRequestGate {
        void stopNewCalls() throws Exception;
        void awaitInFlightCalls() throws Exception;
    }

    public interface CredentialLifecycle {
        void stopRefreshAndWait() throws Exception;
        void resolveFreshIdentity() throws Exception;
    }
}
~~~

The CloudRequestGate and CredentialLifecycle interfaces are application-defined abstractions, not standard Spring or CRaC APIs. The example demonstrates the logical order: drain requests, stop refreshes, and close the client before checkpoint; after restore, resolve identity, create the client, and verify connectivity.

In a real application, determine who owns the credential provider and transport. If the client owns the provider or transport, closing the client may close them. If the provider or transport is shared, manage them under the right owner and order. If the SDK has an official CRaC integration, use that integration and avoid registering duplicate callbacks.

There must also be a handling path when the checkpoint is cancelled after beforeCheckpoint() has already closed the client. The application must know how to reopen the client if the process continues running without a restore. The exact lifecycle depends on how the runtime and framework signal checkpoint failure/cancellation; never assume a client-closing callback will always be followed by restore.

## 17. Managing credential providers separately from clients

A credential provider can outlive a single client and be shared across multiple clients. For example, one provider supplies credentials for object storage, queues, and secret manager. If each client creates its own provider, refreshes and caches may be duplicated; if a shared provider is used, closing it must be managed by the proper owner.

An application abstraction might look like:

~~~java
public interface CredentialLifecycle {
    void stopRefreshAndWait() throws Exception;
    void resolveFreshIdentity() throws Exception;
    void verifyIdentity() throws Exception;
}
~~~

resolveFreshIdentity() can perform one of the following depending on the SDK:

- Request the provider to refresh credentials via a supported API.
- Create a new provider from current configuration.
- Clear the token cache via a public API.
- Call an identity service or metadata provider to verify the current role.
- Recreate the client if the client cannot accept a new provider.

Do not clear private fields inside a provider or signer yourself. Internal caches may have synchronization and invariants; mutating via reflection can leave the provider in a broken state.

If the provider has a refresh thread, stop it via a supported API and wait for running operations. If the provider has no lifecycle API, keeping the provider is safe only if documentation confirms it checks expiration itself and refreshes properly after restore. Test rather than assume.

## 18. Connection pool and HTTP settings to review

An HTTP transport may allow configuring the following limits:

| Configuration | Meaning | Impact on restore |
|---|---|---|
| Max connections | Concurrent connection limit | Avoids overloading endpoints when many instances restore |
| Max idle connections | Idle connections retained | Old connections may be stale in the image |
| Idle timeout | How long idle connections are kept | Should align with server/proxy keep-alive |
| Connection TTL | Maximum lifetime of a connection | Helps retire long-lived connections |
| Connect timeout | TCP/TLS establishment timeout | Prevents restore from waiting indefinitely |
| Read/write timeout | I/O wait timeout | Controls hanging requests |
| Retry policy | How requests are retried | May cause duplicate side effects if requests are non-idempotent |
| DNS cache TTL | How long DNS results are cached | Endpoints may change during checkpoint |
| TLS/session cache | TLS handshake and validation state | May require re-handshaking or refreshing trust material |

Appropriate values depend on workload, service, and HTTP implementation. Do not set max connections overly high just to reduce queue times; when multiple replicas restore together, total connections can exceed service quotas.

If multiple SDK clients share one HTTP transport, calculate total request concurrency. One pool can become a shared bottleneck or shared point of failure. With CRaC, know whether the pool can be kept, evicts stale connections, or must be recreated.

## 19. DNS, TLS, proxies, and endpoints after restore

Connectivity does not depend solely on sockets. SDKs may also cache endpoints, DNS results, TLS sessions, certificate chains, and proxy configurations.

After a long checkpoint interval:

- DNS records may have changed.
- Regional endpoints may have been reconfigured.
- Proxies may require fresh credentials.
- CA bundles or certificates may have been rotated.
- TLS session caches may no longer be valid.
- Service discovery may return new addresses.
- Network policies or routes may have changed.

Do not hardcode assumptions that an endpoint address resolved before checkpoint remains valid. Use supported endpoint resolvers and DNS behavior. If endpoint configuration can change, re-read configuration or recreate the client after restore.

When testing, observe both the case where the connection pool is empty and where many idle connections exist in the checkpoint. A request succeeding via automatic retry does not prove the old connection recovered; inspect transport metrics and logs to confirm whether the pool evicted stale connections.

## 20. Retries, timeouts, and idempotency for cloud requests

A checkpoint may happen while a request is sending or awaiting a response. The service side may have executed the operation while the response never reached the client. If restored and retried, the operation may be repeated.

For example, a create-resource request reaches the cloud API and the server creates it successfully, but the client is checkpointed before receiving the response. After restore, the application does not know the outcome and resends the request. If the API lacks an idempotency key or state-lookup mechanism, the resource may be created twice.

Principles:

- Do not checkpoint while requests with uncertain side effects are pending if draining is possible.
- Use idempotency tokens/request IDs if the API supports them.
- Persist operation IDs and progress state durably.
- For multipart uploads, persist upload IDs and part state per the service contract; do not keep them only in the heap.
- Distinguish pre-send connection errors from post-send timeouts.
- Bound retries and use backoff/jitter.
- Do not automatically retry non-idempotent operations if the prior outcome is unknown.

Retry policies in the SDK can mask some stale connection errors, but do not replace business idempotency. Check how the SDK classifies retryable exceptions and how it handles whether request bodies can be replayed.

## 21. Restoring multiple replicas from the same checkpoint

If one checkpoint serves as a template for multiple instances, each replica may start with the same credential cache, endpoint cache, and connection pool state in the heap. This is why shared baseline state must be separated from per-instance state.

After restore, each replica needs:

- Its own identity from the workload environment.
- Credentials resolved for the replica's actual role/service account.
- Not sharing a snapshotted short-lived token as a common credential.
- Its own connection pool, or a transport designed to be shared safely.
- No sharing of sockets or file descriptors based on assumptions not guaranteed by the platform.
- Its own client ID if required by the SDK/service.
- Concurrency limits on token refreshes and connection initialization to prevent thundering herds.
- Reporting ready only after identity and clients are verified.

If 50 replicas restore together and call STS or the metadata endpoint simultaneously, the identity system may experience a sudden load spike. Add jitter, concurrency limits, properly designed caches, or staged initialization. Do not use a single heap-based credential cache as a cross-replica coordination mechanism.

## 22. Security when handling checkpoints and cloud credentials

Checkpoints may contain tokens, credentials, request headers, payloads, or sensitive data sitting in the heap. Apply appropriate controls:

- Restrict read/write permissions on checkpoint artifacts.
- Encrypt artifacts at rest and in transit if required by platform policy.
- Use a secret manager or workload identity to issue credentials after restore.
- Avoid logging access keys, bearer tokens, session tokens, private keys, or Authorization headers.
- Define checkpoint retention periods and purge old artifacts per policy.
- Rotate/revoke credentials if unauthorized artifact access is suspected.
- Separate permissions for creating, restoring, downloading, and deleting checkpoints.
- Do not feed real user data or real business payloads into warmup just to warm up the SDK.

If credential verification is needed after restore, log publicly safe identity names/roles, expirations, or validity status; never log secret values. You can call an identity introspection API or a safe read operation with least privilege.

## 23. Workflow for integrating a cloud SDK with CRaC

An implementation workflow can be split into steps:

### Step 1: Build an inventory

List all SDK clients, credential providers, token caches, HTTP transports, connection pools, executors, and background refresh threads. For each component, record the creator, owner, consumers, and close/refresh/rebuild APIs.

### Step 2: Confirm CRaC support

Check the JDK distribution, SDK version, HTTP client version, and vendor documentation. Identify which components have official CRaC integration and which need adapters.

### Step 3: Choose an identity strategy

Identify credential sources in build, test, staging, and production. Prefer workload identity or temporary credentials. Define how identity is re-resolved after restore and how stale tokens are avoided.

### Step 4: Design the request gate

Stop accepting new requests, track running SDK calls, drain futures/streams/uploads, and handle operations with uncertain outcomes. Do not merely count synchronous threads.

### Step 5: Manage credentials and transport

By owner, stop refresh tasks, refresh or recreate providers, and close/rebuild clients and connection pools if required. Never close a shared transport from multiple owners.

### Step 6: Create the checkpoint

Permit checkpointing only after the request gate and all resource owners confirm a safe state. Protect the artifact as data that may contain credentials.

### Step 7: Restore and verify

Resolve fresh identity, recreate or recover transport, perform a side-effect-free health check, verify readiness, and only then open traffic.

### Step 8: Test failures and load

Test expired tokens, unavailable metadata endpoints, DNS changes, stale sockets, request timeouts, callback failures, and multiple replicas restoring simultaneously.

## 24. Environment-based configuration example

A configuration can separate non-secret details from credentials:

~~~yaml
cloud:
  region: ap-southeast-1
  endpoint: https://storage.example.internal
  identity:
    mode: workload
  http:
    max-connections: 100
    connection-timeout: 3s
    read-timeout: 10s
    idle-timeout: 30s
~~~

This is an illustrative configuration structure; property names and binding depend on the application. Never place access keys or refresh tokens directly inside YAML files packaged into the image. Credentials should be supplied from an identity provider or secret manager per environment policy.

With Spring Boot, non-secret configuration can bind to ConfigurationProperties, while credential providers and clients are built by bean factories. If endpoints or identities change after restore, a lifecycle is needed to update configuration/clients or create a new bean holder. Do not assume Spring automatically re-binds the entire Environment when the process restores.

## 25. Observability and post-restore diagnostics

To verify the SDK recovered properly, monitor individual layers:

| Metric/log | What to observe |
|---|---|
| Credential resolve duration | Time to obtain identity/credentials after restore |
| Credential refresh success/failure | Whether the provider refreshes successfully |
| Credential expiration margin | Time remaining before token expires |
| HTTP pool active/idle/pending | Whether the pool has abnormal connections or queues |
| Connection creation/reuse | Whether new connections are created or old ones reused |
| DNS resolution | Which address the endpoint resolves to |
| TLS handshake failures | Whether certificates or sessions have issues |
| SDK request latency/error | First request and subsequent post-restore requests |
| Retry count | Whether retries spike due to stale sockets or timeouts |
| In-flight request count | Whether undrained requests remained during checkpoint preparation |
| Client rebuild count | How many times clients/transports are recreated |

Attach restore ID and instance ID to logs/metrics to distinguish replicas. Do not log secrets or sensitive payloads. When the first request fails, classify authentication errors, DNS, TLS, connection reset, timeout, and service-side errors before altering retry policies.

## 26. Testing cloud SDKs after checkpoint/restore

A test suite should use the exact CRaC JDK, SDK version, HTTP transport, and identity environment planned for deployment.

### Expired credential test

1. Use temporary credentials with a short TTL in the test environment.
2. Start the application and confirm the provider fetches credentials.
3. Create a checkpoint.
4. Wait until the old credential expires.
5. Restore.
6. Invoke a safe read API.
7. Confirm the provider fetches fresh credentials and the request succeeds.

### Stale connection pool test

1. Create several idle connections using a test workload.
2. Create a checkpoint while the pool has idle connections.
3. While the process is paused, close server-side connections or let the proxy/NAT idle timeout expire.
4. Restore and send a request.
5. Confirm the transport detects failed connections, evicts them, and creates new connections per policy.
6. Verify retries do not create duplicate side effects.

### In-flight request test

1. Send a cloud request with a sufficiently long processing time.
2. Initiate the quiesce procedure.
3. Confirm the request finishes or cancels per policy.
4. Create the checkpoint.
5. Restore and check that no operation was executed twice unexpectedly.

### Workload identity test

1. Run the application with an identity provisioned by the test environment.
2. Create a checkpoint.
3. Change or rotate credentials/roles per test scenario.
4. Restore.
5. Confirm the application resolves identity per current configuration.
6. Verify least-privilege access permissions remain correct.

### Multi-replica test

1. Create a baseline checkpoint containing no side effects or instance-specific identity.
2. Restore multiple replicas.
3. Confirm each replica gets the appropriate identity.
4. Measure load on metadata/STS/secret services.
5. Check pools and connection counts do not exceed quotas.
6. Confirm no tokens or client identities are shared unintentionally.

## 27. Common errors

**Keeping cached credentials in the checkpoint.** Tokens may expire or identity may no longer be correct. Re-resolve credentials after restore via a supported provider.

**Baking long-lived access keys into the checkpoint image.** Artifacts can contain secrets. Prefer workload identity and protect checkpoints as sensitive data.

**Assuming an SDK client still in the heap is usable.** Sockets or TLS sessions may be stale. Check integration and recover the transport.

**Creating a new client for every request.** This wastes connection pools and handshakes. Manage clients per application lifecycle with a replacement mechanism when needed.

**Closing a shared transport from multiple clients.** One client may break other clients sharing the pool. Assign a single owner and close in order.

**Leaving refresh threads running across checkpoints without checking.** Refresh tasks may be mid-flight or hold old timers. Use the provider's lifecycle API or recreate the provider.

**Health-checking only by checking for non-null objects.** An object existing does not prove identity, network, or endpoints work. Perform a safe verification operation.

**Retrying all request errors.** Timeouts may occur after the service already executed side effects. Use idempotency keys and check operation state.

**Opening traffic before the client is ready.** First requests may fail in bulk. Readiness must wait until credentials and transport are verified.

**Restoring many replicas that all refresh immediately.** Can cause a thundering herd on metadata/STS. Use jitter, concurrency limits, and staggered rollout.

**Assuming all SDKs support CRaC identically.** Clients, credential providers, and HTTP transports have separate versions/lifecycles. Check documentation for exact dependency versions.

## 28. Checklist for integrating cloud SDKs with CRaC

- [ ] Have all SDK clients, credential providers, token caches, HTTP transports, and connection pools been listed?
- [ ] Have the creator, owner, and consumers of each component been identified?
- [ ] Do the SDK version and HTTP implementation have CRaC support documentation?
- [ ] Does the credential provider have automatic refresh, background threads, or its own cache?
- [ ] Has the intended identity in the post-restore environment been identified?
- [ ] Are tokens and temporary credentials re-resolved when needed?
- [ ] Have checkpoint artifacts that may contain secrets been protected appropriately?
- [ ] Are synchronous requests, futures, streams, and active uploads drained?
- [ ] Are refresh tasks awaited/stopped via public APIs?
- [ ] Do shared transports have a single owner and avoid duplicate closing?
- [ ] Does the connection pool handle stale sockets after restore?
- [ ] Are DNS, TLS, proxies, and endpoints re-verified when the environment changes?
- [ ] Is the decision to keep, refresh, or recreate clients based on SDK documentation?
- [ ] Do requests with side effects have idempotency or operation IDs?
- [ ] Does readiness wait for identity and a safe cloud operation to succeed?
- [ ] Have expired credentials, stale connections, and multi-replica restores been tested?
- [ ] Can logs/metrics aid diagnostics without leaking secrets?

## Conclusion

Cloud SDKs typically include multiple components with distinct lifecycles: credential providers, token caches, HTTP transports, connection pools, DNS/TLS state, and executors. At checkpoint time, these components may hold expiring credentials or network connections that become invalid. Successful process restoration does not prove the next cloud request will succeed.

Clearly identify the owner of each client/provider/transport, prefer workload identity and temporary credentials, drain all SDK operations before checkpoint, and refresh identities and connections using supported APIs after restore. If clients need recreation, use a holder or lifecycle manager for controlled replacement and open traffic only after health checks pass. With multiple replicas, assign distinct identities, avoid sharing old tokens, and throttle refresh/connection initialization load. Testing on the exact SDK version, CRaC JDK, and target cloud environment confirms both recovery capability and request safety.
