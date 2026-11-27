# Testing UNAVAILABLE When the Server Stops

In gRPC, **UNAVAILABLE** indicates that the RPC cannot be executed at the current time, typically because the server is not accepting connections, the transport closed, or the service is temporarily unable to serve. With Spring gRPC, testing a server-stopped scenario must verify that the client receives the expected status, the channel's lifecycle remains properly managed, and the application distinguishes connection errors from business errors.

A stopped server does not mean the client's ManagedChannel must be closed. A channel is a long-lived resource that can reconnect when the endpoint comes back up. Therefore, the test must keep the channel open, stop the server, and then send a new RPC over that same channel. Do not close the channel before calling, because then the test only verifies that the client shut itself down.

## 1. When Does the Client Receive UNAVAILABLE?

UNAVAILABLE typically occurs when:

- The client cannot establish a connection to the server address.
- The server has stopped and no listener accepts new connections.
- The HTTP/2 connection is closed or reset while a call is in flight.
- A load balancer has no eligible backends left.
- A service temporarily refuses to serve according to an availability policy.

This status does not have just one cause. If the server proactively returns UNAVAILABLE from a service handler, the client receives the same status. When diagnosing, combine the status code with cause, channel state, server logs, and telemetry; do not depend on a specific Netty error message string.

Distinguish from nearby statuses:

| Status | Common Meaning | How to Distinguish |
| --- | --- | --- |
| UNAVAILABLE | Cannot connect or service temporarily unavailable | Inspect server/transport/backend |
| DEADLINE_EXCEEDED | RPC deadline expired | Check time budget and processing time |
| CANCELLED | Caller or parent call cancelled the RPC | Check caller-side cancellation |
| NOT_FOUND | Service processed the request but resource does not exist | Business/resource error |
| UNAUTHENTICATED | Credentials could not be verified | Check token/certificate |

## 2. RPC Contract Used in the Example

Suppose a client reads inventory from InventoryService:

~~~proto
syntax = "proto3";

package acme.inventory.v1;

option java_multiple_files = true;
option java_package = "com.acme.inventory.v1";

service InventoryService {
  rpc GetStock(GetStockRequest) returns (GetStockResponse);
}

message GetStockRequest {
  string sku = 1;
}

message GetStockResponse {
  string sku = 1;
  int32 available_quantity = 2;
}
~~~

The test server returns stock for a valid request:

~~~java
import io.grpc.stub.StreamObserver;

public final class InventoryGrpcService
        extends InventoryServiceGrpc.InventoryServiceImplBase {

    @Override
    public void getStock(
            GetStockRequest request,
            StreamObserver<GetStockResponse> responseObserver) {

        responseObserver.onNext(GetStockResponse.newBuilder()
            .setSku(request.getSku())
            .setAvailableQuantity(12)
            .build());
        responseObserver.onCompleted();
    }
}
~~~

This service only provides an endpoint that can be called successfully before the server stops. In a Spring application, the service is registered via the Spring gRPC starter's mechanism; the server lifecycle is managed by the starter.

## 3. Graceful and Forced Server Shutdown

gRPC Java provides two ways to stop a server:

- server.shutdown() stops accepting new RPCs and gives in-flight RPCs a chance to finish. This is the preferred choice during deployments or scale-down.
- server.shutdownNow() requests an immediate stop and cancels active RPCs. Use this when the grace period expires or a forced termination is needed.

Typical graceful shutdown sequence:

~~~java
server.shutdown();
if (!server.awaitTermination(10, TimeUnit.SECONDS)) {
    server.shutdownNow();
    server.awaitTermination(5, TimeUnit.SECONDS);
}
~~~

After shutdown(), the server rejects new calls. Calls already accepted before shutdown may complete. With shutdownNow(), active calls may be cancelled or terminated due to transport closure; the status observed by the client depends on timing and call state.

Do not write a test expecting every in-flight RPC to receive UNAVAILABLE when the server stops. An RPC already accepted by the server can finish successfully during graceful shutdown. To test UNAVAILABLE reliably, wait until the server has terminated before sending a new RPC.

## 4. Test Real Transport with Netty and an Ephemeral Port

In-process transport is well-suited for testing handler logic, but does not fully simulate sockets, HTTP/2 connections, and closed listeners. To test a stopped server, use a Netty loopback server with port 0; the OS assigns an available port and the test reads the actual port via server.getPort().

JUnit 5 example:

~~~java
import static org.junit.jupiter.api.Assertions.*;

import io.grpc.ManagedChannel;
import io.grpc.ManagedChannelBuilder;
import io.grpc.Server;
import io.grpc.Status;
import io.grpc.StatusRuntimeException;
import io.grpc.netty.NettyServerBuilder;
import java.io.IOException;
import java.util.concurrent.TimeUnit;
import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;

class InventoryServerUnavailableTest {

    private Server server;
    private ManagedChannel channel;
    private InventoryServiceGrpc.InventoryServiceBlockingStub stub;

    @BeforeEach
    void setUp() throws IOException {
        server = NettyServerBuilder.forPort(0)
            .addService(new InventoryGrpcService())
            .build()
            .start();

        channel = ManagedChannelBuilder
            .forAddress("127.0.0.1", server.getPort())
            .usePlaintext()
            .build();

        stub = InventoryServiceGrpc.newBlockingStub(channel);

        // Warm up to confirm the channel can already execute an RPC to the server.
        GetStockResponse response = stub
            .withDeadlineAfter(2, TimeUnit.SECONDS)
            .getStock(GetStockRequest.newBuilder()
                .setSku("SKU-42")
                .build());
        assertEquals("SKU-42", response.getSku());
    }

    @AfterEach
    void tearDown() throws InterruptedException {
        if (channel != null) {
            channel.shutdownNow();
            assertTrue(channel.awaitTermination(5, TimeUnit.SECONDS));
        }
        if (server != null && !server.isShutdown()) {
            server.shutdownNow();
            assertTrue(server.awaitTermination(5, TimeUnit.SECONDS));
        }
    }

    @Test
    void newCallAfterServerTerminatesReturnsUnavailable()
            throws InterruptedException {
        server.shutdown();
        assertTrue(server.awaitTermination(5, TimeUnit.SECONDS));

        GetStockRequest request = GetStockRequest.newBuilder()
            .setSku("SKU-42")
            .build();

        StatusRuntimeException error = assertThrows(
            StatusRuntimeException.class,
            () -> stub.withDeadlineAfter(2, TimeUnit.SECONDS)
                .getStock(request));

        assertEquals(
            Status.Code.UNAVAILABLE,
            error.getStatus().getCode());
    }
}
~~~

The test executes a successful RPC to confirm the channel is connected, then gracefully shuts down the server and waits for termination. A new RPC is sent over the existing channel while the channel remains open. Because the server is no longer accepting connections, the client observes UNAVAILABLE.

usePlaintext() is only appropriate for this loopback test. Production-like integration tests should configure TLS, trust chains, and matching hostnames. If the project uses grpc-netty-shaded, import the Netty builder from the shaded package rather than mixing unshaded and shaded classes.

## 5. Why Warm Up the Channel Before Stopping the Server?

ManagedChannel can connect lazily. If you stop the server immediately after creating the channel, the test does not prove an active connection was disrupted; it only tests that the client cannot connect initially.

A warm-up RPC verifies that:

1. The server actually started and registered the service.
2. The client targets the exact port assigned by the server.
3. The channel can send/receive an RPC before shutdown.
4. The failure on the subsequent RPC happens after the server has terminated.

Do not use Thread.sleep() to guess when the channel is READY. A successful warm-up RPC synchronizes directly with actual serving readiness and is more reliable.

## 6. Do Not Enable wait-for-ready in Tests Expecting UNAVAILABLE

By default, a call without wait-for-ready fails when the channel cannot pick a ready transport, typically with UNAVAILABLE. If withWaitForReady() is enabled, gRPC may queue the call until the channel recovers or the deadline expires.

Example:

~~~java
var waitingStub = stub.withWaitForReady()
    .withDeadlineAfter(500, TimeUnit.MILLISECONDS);
~~~

When the server is stopped and no replacement backend exists, a wait-for-ready call can end with DEADLINE_EXCEEDED instead of UNAVAILABLE because the client waited out its entire budget. Therefore, tests asserting UNAVAILABLE must use a stub without wait-for-ready and still set a finite deadline so the test does not hang.

## 7. Distinguish Server Shutdown from Channel Shutdown

Server and client channels have two independent lifecycles:

| Action | Effect |
| --- | --- |
| server.shutdown() | Server stops accepting new calls; active calls are allowed to finish |
| server.shutdownNow() | Server requests cancellation of active calls and stops quickly |
| channel.shutdown() | Client stops creating new calls on the channel and releases transports after current calls finish |
| channel.shutdownNow() | Client cancels active calls and closes the channel quickly |

If a test calls channel.shutdownNow() before the RPC and then asserts UNAVAILABLE, the test is no longer testing a stopped server. Keep the channel open until assertions complete, then shut down the channel in @AfterEach.

Do not create a new channel per RPC to work around connection errors. ManagedChannel is designed to be reused, managing reconnects and load balancing across the client's lifetime.

## 8. Behavior When an RPC Is In Flight

When the server performs a graceful shutdown, an already accepted RPC may finish. During a forced shutdown or sudden connection drop, the client may see UNAVAILABLE, CANCELLED, or another status depending on the timing between the response and transport closure.

For in-flight tests:

- Use a latch to confirm the handler has started.
- Call server.shutdown() and verify the active handler is allowed to complete.
- With server.shutdownNow(), verify the cancellation signal is received and resources are released.
- Do not hardcode a single status for every race between response, deadline, and connection close.

Tests targeting "server stopped, new RPC cannot connect" should be kept separate from "in-flight RPC interrupted." The two scenarios have different lifecycles and expectations.

## 9. Conditional Retries for UNAVAILABLE

UNAVAILABLE can be transient and suitable for retries in some cases, but not every RPC is safe to resend:

- Idempotent read RPCs can usually be retried with backoff and an overall deadline.
- Write RPCs require an idempotency key or duplicate-prevention semantics.
- If the server already committed but the response was lost when the server stopped, the client cannot infer the operation did not happen.
- Retries must cap attempt counts, use exponential backoff with jitter, and respect the logical operation's deadline.
- Do not retry aggressively when an entire backend is down; circuit breakers or retry throttling help prevent amplifying incidents.

If the server restarts at the same endpoint, ManagedChannel can automatically reconnect when the resolver/transport discovers the new backend. There is no need to create a new channel for each retry; keep the channel alive and let gRPC manage reconnection per policy.

## 10. Spring gRPC and Lifecycle Management

In a Spring application, the server is typically managed by the starter. Do not call shutdownNow() manually from a service bean or business endpoint. When the application context closes, the starter integration should stop the server according to its configured lifecycle.

For client channels:

- Register channels or client stubs through the starter's beans/lifecycle.
- Reuse a channel across multiple RPCs.
- During application shutdown, stop accepting new work before closing the channel.
- Set deadlines on RPCs so calls do not hang indefinitely while downstream is disconnected.
- If creating a ManagedChannel bean manually, declare a destroy method or lifecycle hook to close the channel properly.

Example bean managing a channel directly:

~~~java
@Configuration
public class InventoryClientConfiguration {

    @Bean(destroyMethod = "shutdown")
    ManagedChannel inventoryChannel() {
        return ManagedChannelBuilder
            .forAddress("inventory.internal", 9090)
            .useTransportSecurity()
            .build();
    }

    @Bean
    InventoryServiceGrpc.InventoryServiceBlockingStub inventoryStub(
            ManagedChannel inventoryChannel) {
        return InventoryServiceGrpc.newBlockingStub(inventoryChannel);
    }
}
~~~

This is an example of direct channel management. If the starter already provides a channel, use that channel instead of creating another channel to the same target. Do not use plaintext in production.

## 11. Observe Channel State and Diagnose UNAVAILABLE

When the client receives UNAVAILABLE, identify which layer failed:

1. **DNS/resolver:** does the target resolve to the right backend addresses?
2. **TCP/port:** is the server listening on that address and port?
3. **HTTP/2/TLS:** are the handshake, certificate, ALPN, and proxy working?
4. **Server lifecycle:** is the instance shutting down, restarting, or draining?
5. **Load balancer:** are any SERVING backends left, or have all backends been ejected?
6. **Application:** did the service proactively return UNAVAILABLE due to a dependency?

You can observe channel states such as IDLE, CONNECTING, READY, TRANSIENT_FAILURE, and SHUTDOWN. State is only a point-in-time diagnostic signal, not a replacement for the RPC status. Log target, method, status code, elapsed time, remaining deadline, and request ID; do not log credentials or sensitive payloads.

## 12. Recommended Test Matrix

| Scenario | Expected Result |
| --- | --- |
| Server running, warm-up RPC | Success |
| Server graceful shutdown completed, channel still open | New RPC returns UNAVAILABLE |
| Server shutdownNow while RPC is running | Cancellation/transport status depending on timing; server stops work |
| Channel shut down before call | Test must recognize this as client shutdown, not server outage |
| Wait-for-ready enabled, no backend | Call waits until recovery or deadline expiration |
| Server restarts on same target | Channel can reconnect; new RPC succeeds once backend is ready |
| Multiple backends, one backend stops | LB shifts calls to remaining healthy backends if policy supports it |
| Write RPC times out after commit | Idempotency/operation lookup prevents duplicate data |

Transport shutdown tests should run over Netty loopback or an equivalent environment. In-process tests remain useful for status mapping and service logic, but do not replace testing sockets, HTTP/2, TLS, DNS, or load balancers.

## 13. Takeaways and Self-Check

**Testing UNAVAILABLE when the server stops** requires keeping ManagedChannel open, warming up with a successful RPC, stopping the server, and sending a new RPC after the server has terminated. Use Netty loopback with an ephemeral port to test real transport; do not enable wait-for-ready when the goal is to observe UNAVAILABLE immediately once no backend remains. Distinguish graceful shutdown from forced shutdown, handle in-flight RPCs according to timing, and retry only when safe.

Self-check:

1. Why must the channel remain open after the server stops?
2. How does server.shutdown() differ from server.shutdownNow()?
3. Why is a warm-up RPC more reliable than Thread.sleep()?
4. How can wait-for-ready change the final observed status?
5. Why can you not conclude a transaction did not commit solely from UNAVAILABLE?
6. When the server restarts at the same endpoint, what is the role of ManagedChannel?

Properly testing server-stopped scenarios helps Spring gRPC clients recognize availability errors, maintain stable channel lifecycles, and recover cleanly when backends return.
