# Custom Resolver

The DNS resolver is appropriate when service names are managed by DNS. However, in some systems, endpoints come from an internal service registry, a control plane, a regional catalog, or a discovery source with custom rules. In those cases, you can write a **custom name resolver** for grpc-java and use it via a target URI in Spring gRPC.

A custom resolver accepts a target, queries endpoints from the discovery source, and supplies an address list to the channel. It does not handle RPC messages, pick an instance for each request, or replace the load balancer. This section focuses on `NameResolverProvider`, `NameResolver`, asynchronous lifecycle, scheme registration, and resolver testing.

## 1. When Is a Custom Resolver Needed?

Consider a custom resolver when DNS cannot represent or provide enough discovery information:

- Endpoints are stored in a service registry with its own API.
- A service has different endpoints per region, tenant, or environment.
- A control plane needs to return additional attributes or service config to the gRPC channel.
- The application needs to receive endpoint updates via events/watches rather than only DNS lookups.
- Service naming rules must be mapped to an address set according to platform policy.

If DNS already meets your requirements, use the standard DNS resolver. A custom resolver adds code, state, retries, caching, security, and operational responsibility; do not create one just to change target syntax.

## 2. Target URI and Custom Scheme

The resolver is selected by the scheme of the target URI. For example:

```text
catalog:///orders
catalog:///inventory
```

In this example, `catalog` is an application-defined scheme; `orders` and `inventory` are service keys. The resolver interprets the path and looks up the corresponding catalog entry.

A target URI should have a clear contract:

| Component | Example Convention | Validation |
| --- | --- | --- |
| Scheme | `catalog` | Must match the provider's `getDefaultScheme()` |
| Authority | Empty in `catalog:///orders` | Reject authorities outside the contract |
| Path | `/orders` | A valid service key with length/character constraints |
| Query | Not used in the basic example | If region/version is supported, parse and validate explicitly |

Do not place passwords, API keys, or registry tokens in the URI. The target may appear in logs, exceptions, diagnostics, or telemetry. Credentials for calling the registry must come from separate secure configuration.

## 3. Two Components: NameResolverProvider and NameResolver

`NameResolverProvider` registers the scheme and creates a resolver for matching targets. `NameResolver` performs discovery and sends results to the channel.

| Component | Responsibility |
| --- | --- |
| `NameResolverProvider` | Declares scheme, priority/availability, and creates a resolver from a URI |
| `NameResolver` | Resolves the service key, emits endpoints, handles refresh and shutdown |
| Registry client | Calls the discovery source, handles auth and timeouts, converts registry data to addresses |
| `NameResolver.Listener2` | Receives resolution results or errors |
| `ResolutionResult` | Carries the list of `EquivalentAddressGroup` instances and optional attributes/service config |
| Load balancer | Receives addresses and decides subchannels/endpoints for RPCs |

The provider should not perform network lookups itself. That belongs in the resolver, usually via an asynchronous registry client injected into the provider.

## 4. Defining a Contract with the Service Registry

Suppose the registry returns socket addresses for a service key. Define a small interface so the resolver does not depend directly on a specific HTTP client or SDK:

```java
import java.net.InetSocketAddress;
import java.util.List;
import java.util.concurrent.CompletionStage;

public interface ServiceCatalog {
    CompletionStage<List<InetSocketAddress>> lookup(String serviceName);
}
```

The concrete implementation of `ServiceCatalog` is responsible for:

- Connecting to the registry using TLS and appropriate credentials.
- Setting request timeouts and bounding retry counts.
- Parsing responses and validating hostnames/IPs and ports.
- Removing duplicate or invalid endpoints according to policy.
- Not returning expired or unpublished endpoints.
- Not logging tokens or sensitive responses.

Using `CompletionStage` avoids blocking threads in the resolver while waiting on the registry. For registries supporting watch/stream updates, you can extend the interface to emit endpoint change events; in that case, manage the subscription and cancel it in `shutdown()`.

## 5. Implementing NameResolverProvider

The provider receives a URI and creates a resolver. The example below accepts only targets of the form `catalog:///service-name` with no authority or query:

```java
import io.grpc.NameResolver;
import io.grpc.NameResolverProvider;
import java.net.URI;

public final class CatalogNameResolverProvider
        extends NameResolverProvider {

    private final ServiceCatalog catalog;
    private final String serviceAuthority;

    public CatalogNameResolverProvider(
            ServiceCatalog catalog,
            String serviceAuthority) {
        this.catalog = catalog;
        this.serviceAuthority = serviceAuthority;
    }

    @Override
    protected boolean isAvailable() {
        return true;
    }

    @Override
    protected int priority() {
        return 5;
    }

    @Override
    public String getDefaultScheme() {
        return "catalog";
    }

    @Override
    public NameResolver newNameResolver(
            URI targetUri, NameResolver.Args args) {
        if (!"catalog".equals(targetUri.getScheme())) {
            return null;
        }

        String path = targetUri.getRawPath();
        boolean validPath = path != null
            && path.matches("/[a-z0-9][a-z0-9-]{0,62}");

        if (targetUri.getRawAuthority() != null
                || targetUri.getRawQuery() != null
                || !validPath) {
            throw new IllegalArgumentException(
                "Expected target catalog:///service-name");
        }

        String serviceName = path.substring(1);
        return new CatalogNameResolver(
            serviceName,
            serviceAuthority,
            catalog,
            args.getSynchronizationContext());
    }
}
```

`isAvailable()` and `priority()` tell the registry whether the provider can be used and its priority. `getDefaultScheme()` returns the `catalog` scheme. `newNameResolver(...)` validates the URI and then creates the resolver. If the target is malformed, fail fast with a clear error rather than silently resolving the wrong service.

`serviceAuthority` is the logical service identity that the resolver represents. Choose it to match how the channel's TLS/authority is configured; do not arbitrarily return an endpoint IP if certificates are issued for the service hostname.

## 6. Implementing an Asynchronous NameResolver

The resolver must retain the listener, call the registry asynchronously, and dispatch results onto gRPC's `SynchronizationContext`. The example below uses a generation counter to ignore stale lookup results if a newer refresh has occurred or the resolver has shut down:

```java
import io.grpc.EquivalentAddressGroup;
import io.grpc.NameResolver;
import io.grpc.Status;
import io.grpc.SynchronizationContext;
import java.net.InetSocketAddress;
import java.util.ArrayList;
import java.util.List;
import java.util.concurrent.CompletionStage;
import java.util.concurrent.atomic.AtomicLong;

final class CatalogNameResolver extends NameResolver {

    private final String serviceName;
    private final String serviceAuthority;
    private final ServiceCatalog catalog;
    private final SynchronizationContext syncContext;
    private final AtomicLong generation = new AtomicLong();

    private volatile Listener2 listener;
    private volatile boolean shutdown;

    CatalogNameResolver(
            String serviceName,
            String serviceAuthority,
            ServiceCatalog catalog,
            SynchronizationContext syncContext) {
        this.serviceName = serviceName;
        this.serviceAuthority = serviceAuthority;
        this.catalog = catalog;
        this.syncContext = syncContext;
    }

    @Override
    public String getServiceAuthority() {
        return serviceAuthority;
    }

    @Override
    public void start(Listener2 listener) {
        this.listener = listener;
        refresh();
    }

    @Override
    public void refresh() {
        if (shutdown || listener == null) {
            return;
        }

        long requestGeneration = generation.incrementAndGet();
        final CompletionStage<List<InetSocketAddress>> lookup;
        try {
            lookup = catalog.lookup(serviceName);
        } catch (RuntimeException ex) {
            reportError(requestGeneration, ex);
            return;
        }

        lookup.whenComplete((addresses, error) ->
            syncContext.execute(() -> {
                if (shutdown || requestGeneration != generation.get()) {
                    return;
                }

                if (error != null) {
                    listener.onError(
                        Status.UNAVAILABLE
                            .withDescription("Service catalog lookup failed")
                            .withCause(error));
                    return;
                }

                if (addresses == null || addresses.isEmpty()) {
                    listener.onError(
                        Status.UNAVAILABLE.withDescription(
                            "No endpoint found for service"));
                    return;
                }

                List<EquivalentAddressGroup> groups = new ArrayList<>();
                for (InetSocketAddress address : addresses) {
                    groups.add(new EquivalentAddressGroup(address));
                }

                ResolutionResult result = ResolutionResult.newBuilder()
                    .setAddresses(groups)
                    .build();
                listener.onResult(result);
            }));
    }

    private void reportError(long requestGeneration, Throwable cause) {
        syncContext.execute(() -> {
            if (shutdown || requestGeneration != generation.get()) {
                return;
            }
            listener.onError(
                Status.UNAVAILABLE
                    .withDescription("Service catalog lookup failed")
                    .withCause(cause));
        });
    }

    @Override
    public void shutdown() {
        shutdown = true;
        generation.incrementAndGet();
    }
}
```

This is an implementation skeleton focused on the resolver lifecycle. Specific imports/APIs must match your project's grpc-java version. In production, add validation for each `InetSocketAddress`, exception handling when registering callbacks, timeouts, and lookup cancellation. `CompletionStage` in the example does not provide a dedicated cancellation handle; a real registry client should support cancellation or guarantee bounded task duration.

Do not invoke the listener from arbitrary threads. `SynchronizationContext` serializes callbacks according to gRPC's threading model. The generation counter prevents old results from overwriting newer endpoints after a faster refresh.

## 7. ResolutionResult and Endpoint Attributes

The resolver returns a list of `EquivalentAddressGroup`, each containing one or more equivalent `SocketAddress` instances. For a simple resolver, each endpoint can be its own group:

```java
List<EquivalentAddressGroup> groups = new ArrayList<>();
for (InetSocketAddress endpoint : endpoints) {
    groups.add(new EquivalentAddressGroup(endpoint));
}

NameResolver.ResolutionResult result =
    NameResolver.ResolutionResult.newBuilder()
        .setAddresses(groups)
        .build();
listener.onResult(result);
```

When needed, the resolver can attach `Attributes` to groups or the result to pass information such as region, zone, or endpoint metadata to downstream components. Only include non-sensitive attributes with a stable schema; never put registry tokens, credentials, or personal data in attributes.

If the registry returns service config, the resolver can supply the corresponding configuration according to grpc-java APIs and channel policy. Validate configs and test compatibility; do not let untrusted registry data arbitrarily alter client retry or load balancing policies.

## 8. Registering the Resolver in Spring gRPC

Making the provider a Spring bean is not enough: the provider must be registered with `NameResolverRegistry` **before the channel resolves the target**. Example creating the provider and channel in bean dependency order:

```java
import io.grpc.ManagedChannel;
import io.grpc.ManagedChannelBuilder;
import io.grpc.NameResolverRegistry;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
class OrdersGrpcConfiguration {

    @Bean
    CatalogNameResolverProvider catalogResolverProvider(
            ServiceCatalog catalog) {
        return new CatalogNameResolverProvider(
            catalog,
            "orders.internal.example");
    }

    @Bean(destroyMethod = "shutdown")
    ManagedChannel ordersChannel(
            CatalogNameResolverProvider provider) {
        NameResolverRegistry.getDefaultRegistry().register(provider);

        return ManagedChannelBuilder
            .forTarget("catalog:///orders")
            .useTransportSecurity()
            .build();
    }
}
```

This example assumes `ServiceCatalog` is already configured and the provider is registered before the channel is built. The default registry is JVM-wide; avoid repeatedly registering the same provider on every request or every stub creation. If the application uses a Spring gRPC starter to manage channels, register the provider during the bootstrap/configuration phase before the starter builds channels, using the extension point supported by that starter version.

You can use Java's Service Provider Interface if the provider can be instantiated through an appropriate application mechanism. For providers requiring dependency injection such as a registry client, explicit registration during bootstrap is usually easier to control. Either way, channels must be managed according to the application lifecycle and closed on shutdown.

## 9. Resolver, Load Balancer, and Health Checking

The resolver only publishes endpoints; the load balancer chooses subchannels and handles picking for RPCs. Health checking is a separate mechanism that determines whether a service reports a serving status.

| Component | Responsibility |
| --- | --- |
| Custom resolver | Looks up service key and emits endpoint list |
| Load balancer | Selects endpoints/subchannels according to policy |
| Health checking | Monitors the serving status of a gRPC service if configured |
| Retry policy | Decides RPC retries based on status, method, and policy |
| Channel | Manages connections, transport, and call lifecycle |

Do not embed round-robin logic inside the resolver. If the registry returns multiple endpoints, let the load balancer make the selection. The resolver may filter out expired or unpublished endpoints, but it should not infer health if the registry does not provide that information.

When an endpoint is removed, the resolver must emit a new result. The load balancer then updates subchannels; connection draining and in-flight RPCs must be handled according to the channel/server lifecycle. Do not treat endpoint removal in the registry as proof that all existing connections have immediately closed.

## 10. Errors, Retries, and Resources

A custom resolver becomes part of the client-side control plane, so you must limit blast radius when the registry has issues:

- **Timeouts:** lookups must have finite deadlines; never let a lookup hang indefinitely.
- **Retry/backoff:** retries must use jitter and bounds to avoid request storms when the registry is unavailable.
- **Empty results:** report a resolution error or apply a defined cache policy; never fabricate fake addresses.
- **Stale endpoints:** decide whether to keep using previous results during a grace period; set a clear age limit.
- **Cancellation:** discard stale lookup results after refresh/shutdown and cancel tasks if the registry client supports it.
- **Thread lifecycle:** stop watches, schedulers, and executors owned by the resolver; do not shut down executors supplied by gRPC.
- **Security:** authenticate with the registry, validate returned data, and never log credentials.

`UNAVAILABLE` can be appropriate when the registry is temporarily unable to supply endpoints. Malformed targets should be rejected immediately; do not turn configuration errors into continuous retries. If the resolver previously had valid endpoints, any policy for retaining stale endpoints should be explicitly designed to balance availability and discovery freshness.

## 11. Testing a Custom Resolver

Resolver unit tests should use a fake `ServiceCatalog` to control results and failures:

| Test Case | Expected Result |
| --- | --- |
| Valid `catalog:///orders` target | Provider creates a resolver for service `orders` |
| Wrong scheme | Provider does not accept the target |
| Invalid path or unsupported query | Rejected clearly |
| Registry returns one endpoint | Listener receives one address group |
| Registry returns multiple endpoints | Listener receives all endpoints |
| Registry returns an empty list | Listener receives a resolution error per policy |
| Registry timeout/failure | Listener receives `UNAVAILABLE`; callback does not hang |
| Refresh while an older lookup is still running | Stale result does not overwrite newer result |
| Shutdown before lookup completes | Late callback is ignored; resources are released |
| Spring context closes | Channel shuts down and registry watcher stops |

A useful integration test starts a local gRPC server on a dynamic port, configures a fake catalog to return `InetSocketAddress("127.0.0.1", port)`, builds a channel targeting `catalog:///orders`, and invokes the generated stub. The test verifies that the provider is registered, the resolver returns the endpoint, and the channel actually reaches the server.

Beyond in-process tests, test TLS authority/certificates, registry authentication, timeouts, and endpoint updates in a production-like environment. In-process transport does not test TCP connections to the addresses returned by the resolver.

## 12. Practice Exercise

A platform has an internal registry that returns `PaymentService` endpoints by service key and region. The Spring gRPC client needs to call `catalog:///payments` and receive new endpoints when instances are replaced.

**Requirements:**

1. Define a URI contract for the `catalog` scheme, service key, and optional region.
2. Write a `NameResolverProvider` that validates scheme/path/query and creates the resolver.
3. Write a `NameResolver` that queries the registry asynchronously, emits `ResolutionResult`, and handles errors.
4. Ensure `refresh()` does not allow stale results to overwrite newer ones; `shutdown()` stops watches/executors and ignores late callbacks.
5. Register the provider before the Spring gRPC channel is created; configure the TLS authority to match the service identity.
6. Use a fake registry to test empty results, multiple endpoints, timeouts, refresh, shutdown, and an integration call to a local server.

**Self-Check Questions:**

- How does `NameResolverProvider` differ in responsibility from `NameResolver`?
- Why should registry lookups be asynchronous?
- What data does `ResolutionResult` provide to the channel?
- Should a resolver perform round-robin selection across endpoints itself?
- Why is a generation/version counter needed to discard stale lookup results?
- When should a resolver emit `UNAVAILABLE` versus rejecting a target immediately?
- Why must the provider be registered before the channel resolves a custom scheme?
- How does `getServiceAuthority()` relate to the service's TLS identity?

**Key Takeaways:** A custom resolver extends service discovery by mapping target URIs to endpoints from a proprietary source. `NameResolverProvider` registers the scheme and builds the resolver; `NameResolver` performs asynchronous lookups, emits `ResolutionResult`, refreshes, and shuts down. In Spring gRPC, register the provider before channel creation, keep lookups bounded with timeouts/cancellation, let the load balancer pick endpoints, and test both resolution results and real RPCs.
