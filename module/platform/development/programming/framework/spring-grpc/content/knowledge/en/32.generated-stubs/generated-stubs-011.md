# Do Not Share Stubs with a Closed Channel

## 1. Objectives

In gRPC Java, a generated stub holds a reference to a Channel. An application can reuse a stub across many requests because stubs are immutable, but this is only safe while the channel used by the stub remains in its active lifecycle. If one component closes the ManagedChannel while other gateways still hold stubs created from that channel, new RPCs through those stubs will fail.

**Do not share stubs with a closed channel** means never continuing to use a generated stub after the ManagedChannel it references has entered the shutdown state. A stub does not own connections and cannot reopen a channel on its own. To resume making RPC calls, the application must create a new channel and new stubs from that channel, then transition consumers to the new pair through a controlled process.

After this lesson, you can:

- Explain why a stub still exists in memory yet cannot make calls over a closed channel.
- Distinguish a reconnecting channel from a shut-down channel.
- Understand the difference between shutdown() and shutdownNow().
- Manage channels through a single lifecycle owner in Spring.
- Prevent gateways or application services from closing a shared channel themselves.
- Swap channels and stubs atomically when rotating or reinitializing a client.
- Test failures when using an old stub and verify that a new stub works.

## 2. Stubs Hold a Channel; They Do Not Own It

A generated stub in gRPC Java is an immutable facade over a service API. When creating a stub:

```java
ManagedChannel channel = ManagedChannelBuilder
        .forAddress("catalog.internal", 9090)
        .useTransportSecurity()
        .build();

CatalogServiceGrpc.CatalogServiceBlockingStub stub =
        CatalogServiceGrpc.newBlockingStub(channel);
```

The stub stores the passed channel along with call options configuration. When invoking an RPC, the generated stub creates calls on that exact channel. The stub never creates a replacement channel and has no authority to close the transport.

This has two consequences:

- You can create multiple stubs or derived stubs from the same channel and reuse them concurrently while the channel is active.
- If the channel is shut down, every stub referencing that channel is affected, including stubs created via withDeadlineAfter(), withInterceptors(), or other call options.

Example:

```java
var baseStub = CatalogServiceGrpc.newBlockingStub(channel);
var shortStub = baseStub.withDeadlineAfter(
        300, TimeUnit.MILLISECONDS);
var longStub = baseStub.withDeadlineAfter(
        2, TimeUnit.SECONDS);
```

baseStub, shortStub, and longStub are three distinct stub objects, yet all three use the same channel. Closing the channel prevents all three from starting new RPCs.

## 3. Channel Shutdown Is a Terminal State

ManagedChannel has its own lifecycle. Calling shutdown():

- Stops the channel from accepting new RPCs.
- Gives already-accepted RPCs an opportunity to finish.
- Transitions the channel to terminated once in-flight calls complete.
- Cannot bring that same channel object back to an active state.

A new call through an old stub after channel shutdown typically fails with status UNAVAILABLE. The application should not rely on the stub still being a valid object or on stub creation not throwing an error to conclude the channel is still usable.

shutdownNow() is stronger: it requests cancellation of active calls and closes the channel faster. Use it when the graceful shutdown period expires or when an immediate stop is required.

| State/Action | Meaning | Can a Stub Start a New RPC? |
|---|---|---|
| Active channel | Accepts calls according to current connection state | Yes |
| Temporarily disconnected channel, not shut down | May reconnect according to channel policy | Possibly; calls depend on deadline/readiness |
| shutdown() called | Rejects new calls; in-flight calls drain | No |
| shutdownNow() called | Cancels running calls and closes the channel | No |
| Channel terminated | Lifecycle has ended | No |

A temporary network or server error does not mean the channel is closed. ManagedChannel can reconnect automatically when the transport recovers. Do not create a new channel every time UNAVAILABLE is returned; first determine whether the error is a transient outage, deadline expiration, routing issue, or a shut-down channel.

## 4. Why Cannot an Old Stub Be Reopened?

Stub configuration methods such as withDeadlineAfter() or withCallCredentials() create a derived stub while keeping the same channel:

```java
var newDeadlineStub = oldStub.withDeadlineAfter(
        1, TimeUnit.SECONDS);
```

This code only changes call options. It does not invoke ManagedChannelBuilder, create a new transport, or replace the channel reference. Therefore, if oldStub references a shut-down channel, newDeadlineStub is unusable as well.

To restore RPC capability, you must create a new pair:

```java
ManagedChannel replacementChannel = ManagedChannelBuilder
        .forAddress("catalog.internal", 9090)
        .useTransportSecurity()
        .build();

CatalogServiceGrpc.CatalogServiceBlockingStub replacementStub =
        CatalogServiceGrpc.newBlockingStub(replacementChannel);
```

replacementStub uses replacementChannel; it does not depend on the old channel. Only after transitioning consumers to the new pair and draining old calls should the old channel be shut down.

## 5. A Single Lifecycle Owner for a Shared Channel

In Spring, a channel is typically declared as a shared bean. The component that creates the channel or is designated as its owner must manage shutdown. Gateways that merely receive the channel/stub via dependency injection must not close that resource themselves.

Example:

```java
@Configuration
public class CatalogGrpcClientConfiguration {

    @Bean(name = "catalogChannel", destroyMethod = "shutdown")
    ManagedChannel catalogChannel() {
        return ManagedChannelBuilder
                .forAddress("catalog.internal", 9090)
                .useTransportSecurity()
                .build();
    }

    @Bean
    CatalogServiceGrpc.CatalogServiceBlockingStub catalogStub(
            @Qualifier("catalogChannel") ManagedChannel channel) {
        return CatalogServiceGrpc.newBlockingStub(channel);
    }
}
```

The gateway only uses the stub:

```java
@Component
public class CatalogGateway {

    private final CatalogServiceGrpc.CatalogServiceBlockingStub stub;

    public CatalogGateway(
            CatalogServiceGrpc.CatalogServiceBlockingStub stub) {
        this.stub = stub;
    }

    public Product getProduct(String productId) {
        var request = GetProductRequest.newBuilder()
                .setProductId(productId)
                .build();

        return stub.withDeadlineAfter(700, TimeUnit.MILLISECONDS)
                .getProduct(request);
    }
}
```

destroyMethod = "shutdown" tells Spring to call shutdown when the bean is destroyed. CatalogGateway has no responsibility for shutting down the channel. If the Spring gRPC starter manages channels itself, use the starter's lifecycle API rather than introducing a second owner.

Do not place channel.shutdown() inside:

- A method handling a business request.
- `@PreDestroy` of a gateway that merely borrows the channel.
- Cleanup of a single test consumer while the channel is still shared by other tests.
- An error handler running when an RPC receives UNAVAILABLE.

Closing a channel from a consumer can break every other bean sharing that channel.

## 6. Graceful Shutdown and Force Shutdown

When an application stops normally, give in-flight RPCs a bounded period to complete:

```java
static void shutdownGracefully(
        ManagedChannel channel,
        Duration gracePeriod) {
    channel.shutdown();
    try {
        if (!channel.awaitTermination(
                gracePeriod.toMillis(), TimeUnit.MILLISECONDS)) {
            channel.shutdownNow();
            channel.awaitTermination(1, TimeUnit.SECONDS);
        }
    } catch (InterruptedException ex) {
        channel.shutdownNow();
        Thread.currentThread().interrupt();
    }
}
```

This example illustrates the shutdown sequence. In a Spring application, place this logic in the lifecycle owner or use the graceful shutdown mechanism supported by the framework/starter; never call it from a gateway. The grace period should align with the application's total shutdown budget and maximum RPC deadlines.

awaitTermination() only waits for the channel to finish; it does not revive the channel. If the wait expires, shutdownNow() forcibly cancels remaining calls. After the channel has shut down, never reuse old stubs for subsequent requests.

## 7. Distinguishing Reconnect from a Closed Channel

A ManagedChannel can transition through IDLE, CONNECTING, READY, TRANSIENT_FAILURE, and SHUTDOWN states. Connectivity states can change as the network or server recovers; SHUTDOWN is a terminal state.

| Scenario | Handling |
|---|---|
| Server temporarily unreachable, channel not shut down | Let the channel reconnect; apply appropriate deadlines/retries |
| Channel is CONNECTING or TRANSIENT_FAILURE | Calls may wait or fail depending on wait-for-ready and deadline |
| Application explicitly called shutdown() | Treat the channel as retired; create a new channel if continuing |
| Channel is TERMINATED | Cannot be reused |
| RPC returns UNAVAILABLE while channel is still active | Investigate server, proxy, name resolution, load balancing, and retry policy before replacing the channel |

getState(true) can help observe channel state, but READY does not guarantee a particular RPC will succeed; the state can change immediately after reading it. A service's health check RPC provides business-level health signals, whereas channel state only reflects client-side connectivity.

Do not treat creating a new channel as a knee-jerk reaction to every RPC error. Doing so can cause connection churn, repeated TLS handshakes, socket growth, and worsen load incidents.

## 8. Replacing the Channel Requires Replacing the Stub

When rotating endpoints, certificates, or reinitializing a channel after a terminated lifecycle, create a new client generation pairing the channel and corresponding stub:

```java
record CatalogClientGeneration(
        ManagedChannel channel,
        CatalogServiceGrpc.CatalogServiceBlockingStub stub) {
}

static CatalogClientGeneration createGeneration(
        String host,
        int port) {
    ManagedChannel channel = ManagedChannelBuilder
            .forAddress(host, port)
            .useTransportSecurity()
            .build();

    var stub = CatalogServiceGrpc.newBlockingStub(channel);
    return new CatalogClientGeneration(channel, stub);
}
```

A generation bundles two objects that must share the same lifecycle. Consumers obtain the stub from the current generation; when a new generation is created, the new stub must be built from the new channel.

A simple cutover procedure when the application can briefly pause incoming requests:

1. Stop accepting or temporarily pause new requests going to the gateway.
2. Wait for in-flight calls on the old generation to finish within allowed limits.
3. Create the new channel and new stub.
4. Switch the gateway to the new generation.
5. Verify new calls succeed.
6. Shut down the old channel once no consumers remain on the old generation.

If zero-downtime rotation is required, you need a lease/reference-counting or drain coordination mechanism to ensure no thread has just grabbed the old generation without starting its call when the old channel is shut down. Merely using AtomicReference to swap generations and immediately shutting down the old channel can introduce a race at that boundary. Hot-swap mechanisms must be designed and tested explicitly.

## 9. Do Not Keep Old Stubs in Singletons After Rotation

A common mistake is updating the channel in configuration while a gateway still holds an old stub field:

```java
@Component
public class CatalogGateway {
    private final CatalogServiceGrpc.CatalogServiceBlockingStub stub;
    // Stub created from the old channel.
}
```

Creating replacementChannel elsewhere does not change the reference already stored in the gateway. Subsequent calls still go through the old channel.

If channels are configured statically per application context, the simplest solution is to restart/refresh the context through a supported mechanism so Spring recreates both channel and stub beans. If the application requires runtime rotation, inject a client provider/holder capable of swapping generations atomically instead of injecting a fixed stub directly.

Do not use reflection or mutate private fields of a generated stub to swap its channel. Stub immutability is part of the API design; creating a new stub from the new channel is the proper approach.

## 10. Testing Stubs After Channel Closure

A test can prove that an old stub becomes unusable after shutdown and that a new stub works over a new channel. With the in-process transport:

```java
@Test
void stubCannotStartNewCallAfterItsChannelIsShutdown()
        throws Exception {
    String oldName = InProcessServerBuilder.generateName();
    Server oldServer = InProcessServerBuilder.forName(oldName)
            .directExecutor()
            .addService(new FakeCatalogService())
            .build()
            .start();
    ManagedChannel oldChannel =
            InProcessChannelBuilder.forName(oldName)
                    .directExecutor()
                    .build();

    var oldStub = CatalogServiceGrpc.newBlockingStub(oldChannel);
    oldChannel.shutdown();
    assertTrue(oldChannel.awaitTermination(2, TimeUnit.SECONDS));

    StatusRuntimeException error = assertThrows(
            StatusRuntimeException.class,
            () -> oldStub.getProduct(
                    GetProductRequest.newBuilder()
                            .setProductId("product-42")
                            .build()));

    assertEquals(Status.Code.UNAVAILABLE,
            error.getStatus().getCode());

    oldServer.shutdownNow();
    oldServer.awaitTermination(2, TimeUnit.SECONDS);
}
```

This test illustrates a new call after channel shutdown. In real tests, place server/channel cleanup inside try/finally or JUnit lifecycle hooks so resources are always closed even if assertions fail.

A follow-up test should create a new server/channel, create a new stub from the new channel, and verify the RPC succeeds. Do not reuse oldStub:

```java
ManagedChannel replacementChannel =
        InProcessChannelBuilder.forName(newServerName)
                .directExecutor()
                .build();

var replacementStub =
        CatalogServiceGrpc.newBlockingStub(replacementChannel);

Product product = replacementStub.getProduct(request);
```

In this test, newServerName must point to a running server fixture. The test must close the replacement channel and server during cleanup.

## 11. Testing the Spring Lifecycle

Unit tests on a channel can verify gRPC Java behavior, but they do not prove Spring closes the right bean or that no consumer retains an old stub. A Spring integration test should verify:

- The context creates a channel bean for the target.
- Stubs/gateways receive the right channel generation.
- Gateways do not shut down the channel while other beans still depend on it.
- When the context closes, the channel owner performs shutdown.
- After the old context has closed, calls are no longer issued to the old gateway.
- When a new context is created, new channels and stubs are injected.

If the application supports runtime refresh or certificate rotation, test cutover with concurrent calls: one batch running on the old channel, one new batch after the switch, and no new calls routed to the shut-down channel.

## 12. Common Pitfalls

| Symptom | Cause | Fix |
|---|---|---|
| Stub object still exists, yet RPC returns UNAVAILABLE | The channel held by the stub was shut down | Create a new channel and new stub |
| withDeadlineAfter() does not recover calls | Derived stub still uses the old channel | Create a stub from the replacement channel |
| Gateway A breaks Gateway B | A closed the shared channel | Only the lifecycle owner calls shutdown |
| Creating a channel on every UNAVAILABLE error | Confusing transient outage with shutdown | Inspect channel lifecycle and transport root cause |
| In-flight calls cut off on app stop | Calling shutdownNow() immediately | Graceful shutdown with a grace period |
| New channel created, yet calls still fail | Gateway still holds the old stub | Replace the full client generation or recreate beans |
| Channel rotation causes random errors | Old channel shut down before consumers stop grabbing it | Use quiescence or lease/drain coordination |
| Spring context closes, yet channel stays alive | No clear lifecycle owner | Manage channel bean/destroy lifecycle |
| Tests pass, yet production rotation fails | Only tested single calls without concurrency | Add cutover tests with in-flight calls |

## 13. Hands-On Exercise

**Scenario:** A Spring application has CatalogGateway and RecommendationGateway sharing a ManagedChannel. One component closes the channel after finishing its own task; afterward, both gateways start receiving UNAVAILABLE. The team wants to swap the Catalog endpoint without letting old stubs continue to be used.

Complete the following:

1. Identify which component creates the channel and which component truly owns its lifecycle.
2. Remove shutdown calls from gateways/consumers that only borrow the channel.
3. Create a client generation pairing a ManagedChannel and its corresponding generated stub.
4. Distinguish a shut-down channel from a reconnecting channel when encountering UNAVAILABLE.
5. Write a test proving old stubs cannot initiate new RPCs after shutdown.
6. Create a new channel/stub generation and verify RPCs succeed.
7. Design cutover: quiesce requests or use lease/drain coordination before shutting down the old generation.
8. Test in-flight calls, new calls, and Spring context shutdown.
9. Verify no gateway retains stubs from the retired generation.

**Completion criteria:** only one owner closes the channel; all shared stubs are treated as invalid once the channel shuts down; new generations always build stubs from the new channel; in-flight calls drain or cancel per policy; no new requests enter a retired channel.

## 14. Takeaways

A generated stub holds a reference to the channel passed when it was created; derived stubs continue using that channel. Once a ManagedChannel shuts down, it cannot be revived by creating more stubs or changing deadlines. shutdown() stops accepting new calls and lets current calls drain; shutdownNow() forcibly cancels remaining calls. Distinguish a reconnecting channel from a shut-down channel to avoid creating unnecessary new connections. In Spring, only the lifecycle owner closes the channel. When a channel must be replaced, create a new generation comprising both a new channel and new stubs, transition consumers in a controlled manner, and then drain and close the old generation. Never share or continue invoking stubs referencing a closed channel.
