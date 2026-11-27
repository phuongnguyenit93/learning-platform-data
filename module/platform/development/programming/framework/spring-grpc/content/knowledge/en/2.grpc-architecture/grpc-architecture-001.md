# Channels, connections, and HTTP/2 streams

## Learning objectives

After this lesson, you can:

- Distinguish **Channel**, **connection (TCP/TLS connection)**, and **HTTP/2 stream** when building gRPC services with Java and Spring.
- Explain how an RPC call travels from a stub through the name resolver, load balancer, and transport to the server.
- Read the main components of a gRPC exchange over HTTP/2: headers, DATA, message framing, trailers, and status.
- Understand how multiplexing, flow control, deadlines, call cancellation, and reconnection affect performance and reliability.
- Manage channel lifecycle in Spring and recognize several common operational issues.

## 1. Three concepts at three different layers

gRPC is a remote procedure call (RPC) protocol. Java applications typically work with a **stub** generated from Protocol Buffers; the gRPC library is responsible for turning calls into network exchanges. In gRPC Java, the following three terms are not synonymous:

| Concept | Role | Scope and lifecycle |
| --- | --- | --- |
| **Channel** (typically **ManagedChannel** on the client) | Logical object for sending RPCs to a destination; coordinates name resolution, address selection, load balancing, and connection management | Usually long-lived, shared across many calls and multiple stubs |
| **Connection / transport** | An actual network connection, usually TCP with TLS, running the HTTP/2 protocol | Established, interrupted, or replaced depending on network state and channel decisions |
| **HTTP/2 stream** | An independent bidirectional stream at the HTTP/2 layer carrying **one** specific RPC | Opened when the RPC starts and ended when the exchange completes, is cancelled, or encounters an error |

A Channel **does not necessarily correspond to exactly one TCP connection**. Depending on the name resolver, load-balancing policy, and transport, it may use multiple subchannels/connections to different backend addresses. Conversely, **one HTTP/2 connection can carry many concurrent HTTP/2 streams**.

The diagram models a scenario with two backends:

~~~mermaid
flowchart TD
    A["Spring service"] --> B["Stub generated from .proto"]
    B --> C["ManagedChannel: name resolver + load balancer"]
    C --> D["Subchannel A"]
    C --> E["Subchannel B"]
    D --> F["HTTP/2 connection A<br/>TCP + TLS"]
    E --> G["HTTP/2 connection B<br/>TCP + TLS"]
    F --> H["Stream 1: RPC A"]
    F --> I["Stream 3: RPC B"]
    G --> J["Stream 1: RPC C"]
~~~

The numbers 1 and 3 here illustrate **stream IDs** on the same connection A. The stream ID space is scoped per connection, so connection B can also use stream ID 1 without conflict.

> **Rule of thumb:** The stub issues the call; the Channel decides how to transport the call; the connection transmits HTTP/2 frames; the stream groups the frames belonging to **one** RPC.

## 2. How does an RPC traverse the layers?

Suppose a Spring service calls the **SayHello** method on a gRPC service on another server.

1. **The application calls the stub.** Java code builds a Protocol Buffers request and invokes a method on the stub. The stub uses the underlying Channel.
2. **The Channel selects a target.** gRPC can resolve the service name to backend addresses and let the load-balancing policy pick a subchannel. When no transport is ready yet, the Channel may initiate a connection.
3. **Transport establishment.** The client establishes TCP; if TLS is used, both sides perform a TLS handshake and negotiate HTTP/2 via ALPN with the value **h2**. In development environments, cleartext HTTP/2 (**h2c**) can be used if both ends support it.
4. **Opening an HTTP/2 stream.** The client sends request headers and DATA frames containing protobuf messages. Each RPC uses one HTTP/2 stream; messages of a streaming RPC still travel on **that same stream**.
5. **Server processing.** The gRPC server routes the method from the RPC path, decodes the request, runs the handler, and then writes the response and final status.
6. **The client receives the result.** The gRPC library reassembles DATA frames into messages, checks the final status, and returns the result or raises an error to the caller.

Creating a Channel usually **does not mean a TCP connection is opened immediately**: gRPC Java may connect on demand when the first RPC occurs or when the application explicitly requests a connection.

## 3. How does an HTTP/2 stream carry gRPC content?

HTTP/2 splits data into **frames** and assigns each frame to a stream. The important frames for typical RPCs are:

- **HEADERS:** carries the method, RPC path, and initial metadata.
- **DATA:** carries framed gRPC messages.
- **HEADERS at the end of the stream (trailers):** carries the final status, especially **grpc-status**; sometimes an error is returned immediately as *trailers-only*, with no DATA.
- **RST_STREAM:** abnormally terminates a stream, such as when a call is cancelled.
- **SETTINGS, WINDOW_UPDATE, PING, GOAWAY:** control the connection, data flow, and stopping acceptance of new streams.

### 3.1. Unary exchange example

Suppose a Protocol Buffers file declares the service:

~~~proto
syntax = "proto3";

package demo.hello;
option java_package = "demo.hello";
option java_multiple_files = true;

service Greeter {
  rpc SayHello(HelloRequest) returns (HelloReply);
  rpc WatchGreetings(HelloRequest) returns (stream HelloReply);
}

message HelloRequest {
  string name = 1;
}

message HelloReply {
  string message = 1;
}
~~~

Conceptually, a unary request might look like this (this is a human-readable representation; on the wire these are binary HTTP/2 frames):

~~~text
Client -> Server, stream 1:
  HEADERS
    :method: POST
    :scheme: https
    :path: /demo.hello.Greeter/SayHello
    :authority: greeter.example:443
    content-type: application/grpc
    te: trailers
    grpc-timeout: 1S
  DATA
    [compressed flag: 1 byte][message length: 4 bytes][HelloRequest protobuf]
  END_STREAM (client finished sending request)

Server -> Client, still on stream 1:
  HEADERS
    :status: 200
    content-type: application/grpc
  DATA
    [compressed flag][message length][HelloReply protobuf]
  HEADERS (trailers)
    grpc-status: 0
  END_STREAM
~~~

**A gRPC message** is prefixed with 5 bytes: 1 byte for the compression flag and 4 bytes for the message length in *big-endian* byte order. The remainder is the serialized protobuf, or compressed data when compression is negotiated. A message can be split across multiple HTTP/2 DATA frames, and one DATA frame can contain data from multiple gRPC messages. Therefore, **never assume "one DATA frame = one message"**.

The path **/demo.hello.Greeter/SayHello** combines the full service name with the method name. **grpc-timeout** expresses the remaining deadline as a relative time value; 1S means one second. **grpc-status: 0** corresponds to **OK**.

HTTP status 200 only indicates that the HTTP-layer exchange could take place; the RPC can still fail with a non-zero **grpc-status** in the trailers. When handling gRPC errors, you must inspect the **gRPC status** rather than only looking at the HTTP status.

### 3.2. One stream per RPC type

| RPC type | Requests and responses | Number of HTTP/2 streams for one call |
| --- | --- | --- |
| **Unary** | 1 request → 1 response | 1 |
| **Server streaming** | 1 request → many responses | 1 |
| **Client streaming** | Many requests → 1 response | 1 |
| **Bidirectional streaming** | Many requests ↔ many responses, both directions can interleave | 1 |

With streaming, each side can close its **send half** (*half-close*) when it has no more messages to send; the other side can still continue sending until the RPC ends. **StreamObserver** in gRPC Java is the application API for emitting/receiving messages; do not confuse it with the underlying HTTP/2 stream object.

## 4. Multiplexing: sharing a connection while keeping RPCs separate

HTTP/2 allows frames from multiple streams to be **interleaved** on the same connection:

~~~text
One TCP/TLS connection
  -> HEADERS(stream 1)
  -> HEADERS(stream 3)
  -> DATA(stream 1)
  -> DATA(stream 3)
  -> DATA(stream 1)
  -> trailers(stream 3)
  -> trailers(stream 1)
~~~

The client does not need to open a TCP connection per RPC. This reduces handshake overhead, reuses TLS, and allows multiple RPCs to progress concurrently over a single transport. However, multiplexing **does not mean bandwidth or concurrent RPC capacity is unlimited**:

- The peer may advertise a **SETTINGS_MAX_CONCURRENT_STREAMS** limit; new streams may have to wait for resources, depending on the client and configuration.
- **Flow control** operates at both the **stream** and **connection** levels, independently in each direction. When a receive window is exhausted, the sender must wait for **WINDOW_UPDATE**.
- HTTP/2 streams are frame-independent at the protocol layer, yet they still run over the same TCP connection. TCP packet loss can still affect the progress of multiple streams sharing a connection (*TCP head-of-line blocking*).
- Opening additional connections or spreading load across other backends depends on the Channel/transport policy; it cannot be inferred solely from the number of RPCs.

**Practical example:** a server-streaming RPC emits thousands of records, but the client processes them slowly. If the receiver does not consume fast enough, flow-control windows can slow down or pause the sender. If multiple streams share the same connection, connection-level limits can also affect the remaining streams.

In gRPC Java's asynchronous streaming API, the application should pay attention to **backpressure** and write-readiness signals such as **isReady/onReady** when appropriate; continuously pushing messages unchecked can increase buffering and latency. Transport-level flow control does not completely replace application-level rate management.

## 5. Managing Channels in a Spring application

In a Spring application, you should create the Channel as a **shared bean**, inject stubs into services, and let Spring manage the lifecycle. Do not create and close a Channel on every HTTP request or every RPC call, because doing so repeats name resolution, connection establishment, and handshakes.

The following example uses the core **grpc-java** API; the **GreeterGrpc**, **HelloRequest**, and **HelloReply** classes are generated from the proto file above. It is suitable for illustrating the underlying mechanics in a Spring application without depending on configuration property names of a specific Spring gRPC version.

~~~java
import io.grpc.ManagedChannel;
import io.grpc.ManagedChannelBuilder;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
public class GrpcClientConfig {

    @Bean(destroyMethod = "shutdown")
    ManagedChannel greeterChannel() {
        // Use plaintext only for controlled local demos.
        return ManagedChannelBuilder.forAddress("localhost", 9090)
                .usePlaintext()
                .build();
    }

    @Bean
    GreeterGrpc.GreeterBlockingStub greeterStub(ManagedChannel greeterChannel) {
        return GreeterGrpc.newBlockingStub(greeterChannel);
    }
}
~~~

~~~java
import java.util.concurrent.TimeUnit;
import org.springframework.stereotype.Service;

@Service
public class GreetingClient {
    private final GreeterGrpc.GreeterBlockingStub stub;

    public GreetingClient(GreeterGrpc.GreeterBlockingStub stub) {
        this.stub = stub;
    }

    public String greet(String name) {
        HelloRequest request = HelloRequest.newBuilder()
                .setName(name)
                .build();

        HelloReply reply = stub
                .withDeadlineAfter(1, TimeUnit.SECONDS)
                .sayHello(request);

        return reply.getMessage();
    }
}
~~~

Key takeaways from the example:

- **The ManagedChannel bean** persists across many calls to **greet**; underneath, it can open, recover, or replace connections.
- **A stub** is a call-configuration object that can be reused; configuration methods such as **withDeadlineAfter** create a new stub for that specific call. For deadlines, attach them right before the RPC rather than forever reusing a stub with an expired deadline.
- **@Bean(destroyMethod = "shutdown")** lets Spring request the Channel to stop when the context closes. For applications with strict shutdown requirements, you can add a mechanism to wait for in-flight calls to complete within an appropriate timeout.
- **usePlaintext()** is only for development examples in trusted environments. In production deployments, configure TLS, trust chain, and authentication according to your infrastructure; servers/proxies must support HTTP/2 for gRPC.
- **Blocking stubs** make the calling thread wait. For streaming or high load, consider async stubs and proper management of message consumption/emission.

When using Spring gRPC auto-configuration features, you can let the framework create Channels/stubs from the corresponding configuration. Regardless of how they are created, the architectural boundary **stub → Channel → HTTP/2 transport → stream** stays the same.

### 5.1. Channel states and reconnection

gRPC Java has connection states such as:

| State | Operational meaning |
| --- | --- |
| **IDLE** | Not actively connected or resting when there is no activity |
| **CONNECTING** | Establishing a connection to the target |
| **READY** | A transport is ready to accept calls |
| **TRANSIENT_FAILURE** | Connection encountered a temporary failure; may retry with backoff |
| **SHUTDOWN** | Channel has been requested to shut down |

**READY** is not a guarantee that every subsequent RPC will succeed: the network, backend, deadline, or authorization can still change between observing the state and sending the RPC. Likewise, a Channel in **IDLE** is not necessarily an error.

When a connection drops, the Channel typically handles reconnection attempts using a backoff mechanism. RPCs may fail with **UNAVAILABLE** or wait for readiness depending on settings (such as **wait-for-ready**) and deadline. Do not treat reconnection as a guarantee that every sent operation is automatically re-executed: for retries, you must consider the configured policy, *idempotency*, and actual server-side processing state.

## 6. Which layer do deadlines, cancellations, and errors affect?

It is important to distinguish the **RPC/stream lifecycle** from the **Channel/connection lifecycle**:

| Event | Typical scope of impact | What the client observes |
| --- | --- | --- |
| **An RPC exceeds its deadline** | That call is terminated/cancelled; the shared connection can still serve other RPCs | **DEADLINE_EXCEEDED** |
| **Client cancels an RPC** | That call's stream is cancelled, typically via a stream termination signal like **RST_STREAM** | **CANCELLED** on the cancelling side, depending on timing |
| **TCP/TLS connection loss** | Multiple streams using that connection can be affected; the Channel can establish another transport | Typically **UNAVAILABLE** or related error |
| **Server sends an error grpc-status** | Terminates the corresponding RPC; does not necessarily close the connection | The RPC's **Status** code, e.g., **INVALID_ARGUMENT** |
| **Server/proxy sends GOAWAY** | The connection stops accepting new streams per the announced limit; performs draining/connection transition | New/in-flight RPCs are handled depending on timing and policy |

A **deadline** bounds the duration of an individual RPC, including time spent waiting for a connection, transferring data, and processing. **Keepalive PING**, on the other hand, helps detect connection health and keep connections alive when permitted; it **does not replace deadlines**. Setting keepalive too aggressively can be rejected by the server or proxy, even leading to GOAWAY.

Metadata for an RPC typically travels in headers/trailers, whereas connection state is governed by HTTP/2/TCP/TLS. gRPC interceptors are well suited for attaching metadata, propagating context, or logging/tracing at the **RPC level**; do not assume every interceptor sees individual HTTP/2 frames.

## 7. Symptoms and diagnostic approach

| Symptom | Layer to inspect | Approach |
| --- | --- | --- |
| Client cannot call the service when running behind a reverse proxy | TLS/ALPN/HTTP/2, routing | Check whether the path supports gRPC over HTTP/2 and proxy configuration; verify host, port, certificate |
| At times many RPCs wait even though CPU is idle | Stream concurrency, pool, flow control | Check concurrent streams limit, number of in-flight RPCs, and streaming consumption status |
| Unary RPCs frequently time out | Deadline, backend latency, DNS/LB | Separate connection wait time from processing time; correlate traces and metrics per method |
| Streaming starts fast but slows down later | Backpressure and flow-control windows | Check whether the reader/writer processes slowly, and whether queues or buffers are growing |
| After a backend restart, some RPCs fail temporarily | Connection/Channel/reconnection | Observe states, UNAVAILABLE codes, backoff, and graceful shutdown/GOAWAY behavior |
| HTTP 200 yet the application still reports an error | Trailers/gRPC status | Inspect **grpc-status** and message, do not rely solely on HTTP status |

In a Spring gRPC deployment, you should monitor at a minimum **active/in-flight RPCs**, **per-method latency**, **error rate by gRPC status**, **deadline exceeded**, **cancellation**, as well as connection/subchannel counts when the transport exposes metrics. Distributed tracing helps correlate client-side latency with server handlers; metadata logging must avoid leaking tokens and sensitive data.

Do not automatically increase the number of connections to fix every problem. First identify whether the bottleneck lies in **Channel/LB**, **HTTP/2 stream limit**, **flow control**, **network**, or **backend processing**.

## 8. Hands-on lab to verify the model

Suppose there is a gRPC server on **localhost:9090** and a Spring client like the example in section 5.

1. **Reuse the Channel.** Create one Channel for many concurrent **SayHello** calls; compare against creating a new Channel per call. Observe connection overhead and latency. The actual number of connections depends on transport/policy, so verify with metrics or network tools rather than assuming it is always 1.
2. **Switch from unary to server streaming.** Call **WatchGreetings** returning multiple messages. Observe that one RPC has multiple DATA/messages but only one HTTP/2 stream.
3. **Test a short deadline.** Intentionally make the server take longer than the deadline. Confirm the call receives **DEADLINE_EXCEEDED**, then send another call on the still-existing Channel.
4. **Simulate a slow receiver.** Have the streaming client process data slowly; observe memory usage, message emission rate, and backpressure signals.
5. **Restart the backend.** Track connection state changes and gRPC status, then verify the Channel can continue serving RPCs once the backend is ready again.

### Self-check questions

**1. How many connections does a Channel hold and how many RPCs does a connection hold?**  
A Channel can manage multiple connections depending on policy and destination. Each HTTP/2 connection can carry many concurrent RPCs as separate streams, subject to resource limits and flow control.

**2. If a server-streaming RPC emits 500 messages, how many HTTP/2 streams does it create?**  
**One** stream for the entire RPC; the messages are framed and sent across multiple DATA frames on that stream.

**3. When an RPC hits its deadline, should you close the shared Channel?**  
Usually **no**. A deadline is a per-RPC limit; the shared Channel and connection can still serve other calls.

## Summary

With Spring gRPC, manage **ManagedChannel** as a shared resource and let stubs create individual RPC calls. The Channel handles locating and maintaining paths to the server; one **HTTP/2 connection** carries many **streams**, with each stream corresponding to one RPC, including streaming RPCs with many messages. When troubleshooting performance or reliability issues, analyzing the right layer — Channel, connection, stream, or handler — leads to well-grounded solutions.
