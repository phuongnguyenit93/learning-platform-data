# Client stub and server implementation

## Learning objectives

After this lesson, you can:

- Explain the responsibilities of the **client stub**, **ManagedChannel**, **server transport**, method router, and **server implementation** in gRPC.
- Distinguish Java code **generated from Protocol Buffers** from business code **written by the developer**.
- Implement and call a unary method in a Spring application; understand the API signatures for all four RPC types.
- Properly use **StreamObserver**, completion statuses, deadlines, metadata, and error handling on both sides.
- Structure client/server lifecycles with Spring, write basic integration tests, and recognize common architectural mistakes.

## 1. Roles of client and server in a gRPC call

In the **SPRING_GRPC** ecosystem, we define contracts with **Protocol Buffers**, generate Java APIs, and connect client and server applications via gRPC. Spring helps manage objects, dependency injection, configuration, and application lifecycle; the gRPC library handles message encoding, RPC transmission, callback dispatching, and error status mapping.

The two central components are:

- **Client stub**: a client-side Java API representing a remote service. Callers invoke methods like Java functions, and the stub turns the call into an RPC over a **Channel**.
- **Server implementation**: a server-side class implementing the methods declared in the contract. gRPC receives the data, locates the matching handler, and invokes that method.

The client stub **does not contain the server's business logic**. Nor does the server implementation **need to parse HTTP/2 frames itself**. Both sides share a contract covering service names, method names, and message types.

~~~mermaid
sequenceDiagram
    participant A as Spring client service
    participant S as Generated client stub
    participant C as ManagedChannel
    participant T as gRPC server transport
    participant I as Server implementation
    A->>S: sayHello(HelloRequest)
    S->>C: RPC method descriptor + request
    C->>T: HTTP/2 headers + protobuf data
    T->>I: sayHello(request, responseObserver)
    I-->>T: onNext(HelloReply)
    I-->>T: onCompleted()
    T-->>C: response + grpc-status
    C-->>S: deserialize/finish RPC
    S-->>A: HelloReply
~~~

For a unary RPC, the sequence above has one request and one response. For a streaming RPC, the same call can carry multiple messages in one or both directions; those messages still belong to **one HTTP/2 stream**.

### 1.1. Who owns what?

| Layer/component | Responsibility | What does the developer typically do? |
| --- | --- | --- |
| **.proto file** | Declares services, methods, messages, and streaming direction | Designs and versions the contract |
| **Code generator** | Generates message classes, service descriptors, and stub types | Configures protoc and the gRPC Java plugin; never edits generated code directly |
| **Client stub** | Provides the Java API to invoke RPCs; submits requests to the Channel | Chooses blocking/async/future stub and configures individual calls |
| **ManagedChannel** | Resolves names, selects backends, manages transports | Creates/reuses the Channel; configures TLS, deadlines, and LB when needed |
| **gRPC server/runtime** | Receives HTTP/2, decodes protobuf, locates the matching RPC handler | Registers services, configures server/interceptors |
| **Server implementation** | Validates input, executes business logic, emits responses/status | Writes handler code, ensures calls terminate properly |

**Key distinction:** creating a Spring bean with a method named **sayHello** is not enough for a gRPC client to call it. That bean must implement the service according to the gRPC API and be **registered with the gRPC server** (manually or via the auto-registration mechanism of the Spring integration in use).

## 2. The Protocol Buffers contract defines the API on both sides

Example greeting service supporting all four RPC types:

~~~proto
syntax = "proto3";

package demo.greeter.v1;

option java_package = "dev.example.grpc.greeter";
option java_multiple_files = true;
option java_outer_classname = "GreeterProto";

service Greeter {
  rpc SayHello(HelloRequest) returns (HelloReply);                 // Unary
  rpc ListGreetings(HelloRequest) returns (stream HelloReply);    // Server streaming
  rpc CollectNames(stream HelloRequest) returns (HelloReply);     // Client streaming
  rpc Chat(stream HelloRequest) returns (stream HelloReply);      // Bidirectional
}

message HelloRequest {
  string name = 1;
}

message HelloReply {
  string text = 1;
}
~~~

When running **protoc** with the Java Protocol Buffers generator and **protoc-gen-grpc-java**, you typically receive:

- **HelloRequest**, **HelloReply**: immutable protobuf message classes with **newBuilder()**, getters, and serialization/parsing capabilities.
- **GreeterGrpc**: a class containing the service descriptor, stub factory methods, and the base class for the server.
- **GreeterGrpc.GreeterImplBase**: the server class with methods to override.
- **GreeterGrpc.GreeterBlockingStub**, **GreeterGrpc.GreeterStub**, **GreeterGrpc.GreeterFutureStub**: the different client APIs.

With standard Java code generation, the method **SayHello** in the proto file becomes **sayHello** in Java. The RPC path on the wire is **/demo.greeter.v1.Greeter/SayHello**. The protobuf package name (**demo.greeter.v1**) identifies the service on the protocol, while **java_package** determines the package of the generated Java classes.

Do not edit generated classes: the next generator run can overwrite everything. When changing the schema, update the **.proto** file, regenerate code on all required sides, and verify contract compatibility.

### 2.1. Method signatures change by RPC type

The following table describes the **grpc-java** API typically generated:

| RPC | Server override in GreeterImplBase | Typical client |
| --- | --- | --- |
| **Unary** | **void sayHello(HelloRequest, StreamObserver<HelloReply>)** | Blocking: returns **HelloReply**; async: passes response observer |
| **Server streaming** | **void listGreetings(HelloRequest, StreamObserver<HelloReply>)** | Blocking: receives **Iterator<HelloReply>**; async: receives each message via observer |
| **Client streaming** | **StreamObserver<HelloRequest> collectNames(StreamObserver<HelloReply>)** | Async stub returns a request observer to send multiple requests |
| **Bidirectional streaming** | **StreamObserver<HelloRequest> chat(StreamObserver<HelloReply>)** | Async stub returns a request observer, receives responses via observer |

**StreamObserver<T>** is gRPC Java's callback interface for handling **application-layer messages**. It is not the HTTP/2 stream object, even though the messages received/sent by the observer are transported over an HTTP/2 stream.

Some code generator versions or options may emit additional API variants; the table above focuses on the three traditional grpc-java stub types.

## 3. Writing the server implementation

We create a Spring bean implementing **GreeterGrpc.GreeterImplBase**. Each overridden method corresponds to a method in the contract.

The example below shows all four RPC types. The **HelloRequest**, **HelloReply**, and **GreeterGrpc** classes must be generated from the proto file in section 2.

~~~java
package dev.example.server;

import dev.example.grpc.greeter.GreeterGrpc;
import dev.example.grpc.greeter.HelloReply;
import dev.example.grpc.greeter.HelloRequest;
import io.grpc.Status;
import io.grpc.stub.StreamObserver;
import java.util.StringJoiner;
import org.springframework.stereotype.Component;

@Component
public class GreeterEndpoint extends GreeterGrpc.GreeterImplBase {

    // 1 request -> 1 response
    @Override
    public void sayHello(HelloRequest request,
                         StreamObserver<HelloReply> responseObserver) {
        String name = request.getName().trim();

        if (name.isEmpty()) {
            responseObserver.onError(
                Status.INVALID_ARGUMENT
                    .withDescription("name must not be empty")
                    .asRuntimeException()
            );
            return;
        }

        responseObserver.onNext(
            HelloReply.newBuilder().setText("Hello, " + name).build()
        );
        responseObserver.onCompleted();
    }

    // 1 request -> many responses
    @Override
    public void listGreetings(HelloRequest request,
                              StreamObserver<HelloReply> responseObserver) {
        String name = request.getName().trim();

        if (name.isEmpty()) {
            responseObserver.onError(
                Status.INVALID_ARGUMENT
                    .withDescription("name must not be empty")
                    .asRuntimeException()
            );
            return;
        }

        for (int i = 1; i <= 3; i++) {
            responseObserver.onNext(
                HelloReply.newBuilder()
                    .setText("Greeting " + i + " for " + name)
                    .build()
            );
        }
        responseObserver.onCompleted();
    }

    // Many requests -> 1 response
    @Override
    public StreamObserver<HelloRequest> collectNames(
            StreamObserver<HelloReply> responseObserver) {

        return new StreamObserver<HelloRequest>() {
            private final StringJoiner names = new StringJoiner(", ");

            @Override
            public void onNext(HelloRequest request) {
                names.add(request.getName().trim());
            }

            @Override
            public void onError(Throwable error) {
                // Client cancelled/request stream failed: release resources if any.
            }

            @Override
            public void onCompleted() {
                responseObserver.onNext(
                    HelloReply.newBuilder()
                        .setText("Received: " + names)
                        .build()
                );
                responseObserver.onCompleted();
            }
        };
    }

    // Many requests <-> many responses
    @Override
    public StreamObserver<HelloRequest> chat(
            StreamObserver<HelloReply> responseObserver) {

        return new StreamObserver<HelloRequest>() {
            @Override
            public void onNext(HelloRequest request) {
                responseObserver.onNext(
                    HelloReply.newBuilder()
                        .setText("Echo: " + request.getName())
                        .build()
                );
            }

            @Override
            public void onError(Throwable error) {
                // Receive side ended; clean up related resources if any.
            }

            @Override
            public void onCompleted() {
                responseObserver.onCompleted();
            }
        };
    }
}
~~~

This is an educational example: in production implementations, **CollectNames** also needs limits on message count/data size, per-item validation, and cancellation handling if the client disconnects. For **ListGreetings**, a small loop helps show message flow; a very large data stream needs incremental emission and backpressure rather than pushing everything at once.

### 3.1. Rules for terminating calls with StreamObserver

| Callback method | Meaning | Notes |
| --- | --- | --- |
| **onNext(message)** | Sends/receives another message | Can be repeated multiple times in streaming |
| **onCompleted()** | Successfully ends the outbound message direction | On the server, usually finishes the response and sends status OK |
| **onError(cause)** | Abnormally terminates with an error | Use an appropriate gRPC **Status** when returning business errors |

For the server's response observer, **onCompleted() and onError() are mutually exclusive terminal branches**: terminate exactly once, and do not emit **onNext()** afterward. On validation failure, call **onError()** and then **return** to avoid continuing execution. Do not let arbitrary business exceptions leak out of handlers; map them to **Status.INVALID_ARGUMENT**, **NOT_FOUND**, **PERMISSION_DENIED**, **FAILED_PRECONDITION**, **INTERNAL**, etc., according to their actual meaning.

In streaming RPCs, the **onError()** callback on the request-receiving observer can also signal peer cancellation or connection drop. In that case, clean up resources and do not assume you can send further responses onto a failed stream.

**StreamObserver does not automatically guarantee thread safety when multiple threads invoke write methods concurrently.** If asynchronous producers write to the same observer, the application must coordinate/synchronize writes and terminal state. Asynchronous calls also need cancellation and backpressure control.

### 3.2. Registering the implementation with the gRPC server

To see explicitly how the gRPC server connects the runtime to the implementation, you can register the service using the grpc-java API as follows:

~~~java
package dev.example.server;

import io.grpc.Server;
import io.grpc.ServerBuilder;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
public class GrpcServerConfig {

    @Bean(initMethod = "start", destroyMethod = "shutdown")
    Server grpcServer(GreeterEndpoint endpoint) {
        return ServerBuilder.forPort(9090)
                .addService(endpoint)
                .build();
    }
}
~~~

**.addService(endpoint)** accepts an implementation satisfying **BindableService**; from there, gRPC builds the mapping between method descriptors and the corresponding Java handlers. **initMethod = "start"** tells Spring to start the server when the bean initializes; **destroyMethod = "shutdown"** tells it to stop accepting new work when the context closes. In production systems, consider waiting for in-flight RPCs to complete within a bounded timeout rather than assuming calling **shutdown()** waits for all RPCs to finish.

The configuration above is an example of **plain grpc-java managed by Spring**. If you use a **Spring gRPC** integration library that auto-creates the server and auto-discovers service beans, follow that mechanism to avoid opening a second server on the same port. Specific annotation names and configuration properties may differ across integration library versions.

## 4. Client stub: choosing the right API for how you call

gRPC Java typically provides three stub types:

| Stub | Usage model | Suitable calls |
| --- | --- | --- |
| **BlockingStub** | Blocks the calling thread until a result or error is received | Unary, server streaming (via Iterator) |
| **FutureStub** | Returns a future for a result arriving later | Typically unary, suitable when composing futures |
| **Stub** (asynchronous) | Registers StreamObserver callbacks without blocking synchronously | All four RPC types, especially client/bidirectional streaming |

All stubs use a **Channel**. Stubs are usually lightweight and can be created and shared sensibly; the important thing is to **reuse the ManagedChannel** rather than building a new connection after every call.

### 4.1. Unary client example in Spring

The following example shows a **separate Spring client application** connecting to the server running on port 9090:

~~~java
package dev.example.client;

import dev.example.grpc.greeter.GreeterGrpc;
import io.grpc.ManagedChannel;
import io.grpc.ManagedChannelBuilder;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
public class GrpcClientConfig {

    @Bean(destroyMethod = "shutdown")
    ManagedChannel greeterChannel() {
        // Local demo; real deployments need TLS and proper authentication.
        return ManagedChannelBuilder.forAddress("localhost", 9090)
                .usePlaintext()
                .build();
    }

    @Bean
    GreeterGrpc.GreeterBlockingStub greeterBlockingStub(
            ManagedChannel greeterChannel) {
        return GreeterGrpc.newBlockingStub(greeterChannel);
    }

    @Bean
    GreeterGrpc.GreeterStub greeterAsyncStub(
            ManagedChannel greeterChannel) {
        return GreeterGrpc.newStub(greeterChannel);
    }
}
~~~

~~~java
package dev.example.client;

import dev.example.grpc.greeter.GreeterGrpc;
import dev.example.grpc.greeter.HelloReply;
import dev.example.grpc.greeter.HelloRequest;
import io.grpc.Status;
import io.grpc.StatusRuntimeException;
import java.util.concurrent.TimeUnit;
import org.springframework.stereotype.Service;

@Service
public class GreetingClientService {
    private final GreeterGrpc.GreeterBlockingStub greeter;

    public GreetingClientService(
            GreeterGrpc.GreeterBlockingStub greeter) {
        this.greeter = greeter;
    }

    public String greet(String name) {
        HelloRequest request = HelloRequest.newBuilder()
                .setName(name)
                .build();

        try {
            HelloReply response = greeter
                    .withDeadlineAfter(2, TimeUnit.SECONDS)
                    .sayHello(request);

            return response.getText();
        } catch (StatusRuntimeException ex) {
            Status.Code code = ex.getStatus().getCode();
            // Map the gRPC code to an appropriate application error here.
            throw new IllegalStateException(
                    "Greeter RPC failed: " + code, ex);
        }
    }
}
~~~

**Core points:**

- **ManagedChannel** is a lifecycle-managed resource. The Channel may not open a connection immediately upon **build()**; transport is typically established on demand.
- **GreeterBlockingStub** holds RPC call configuration (channel, credentials, interceptors, deadline/call options). Calling **withDeadlineAfter(...)** returns **a new configured stub** without mutating the original stub. Attach deadlines close to the call to avoid reusing an expired deadline.
- **StatusRuntimeException** carries the status code and sometimes trailer metadata. Clients should distinguish data errors like **INVALID_ARGUMENT** from infrastructure errors like **UNAVAILABLE** and timeouts like **DEADLINE_EXCEEDED**.
- **usePlaintext()** is only suitable for demos or specifically controlled internal infrastructure; production requires configuring TLS/trust and authentication according to the deployment.

When an application uses Spring gRPC auto-configuration, the Channel and stubs can be created by the framework from configuration, but the architecture remains **Spring client service → generated stub → Channel → remote gRPC server**.

### 4.2. Server-streaming client example with an async stub

With server streaming, the client receives each **HelloReply** via callbacks. The snippet below illustrates the asynchronous flow; it **does not** wait for the RPC to complete before returning:

~~~java
package dev.example.client;

import dev.example.grpc.greeter.GreeterGrpc;
import dev.example.grpc.greeter.HelloReply;
import dev.example.grpc.greeter.HelloRequest;
import io.grpc.Status;
import io.grpc.stub.StreamObserver;
import java.util.concurrent.TimeUnit;
import org.springframework.stereotype.Service;

@Service
public class GreetingStreamClient {
    private final GreeterGrpc.GreeterStub stub;

    public GreetingStreamClient(GreeterGrpc.GreeterStub stub) {
        this.stub = stub;
    }

    public void printGreetings(String name) {
        HelloRequest request = HelloRequest.newBuilder()
                .setName(name)
                .build();

        stub.withDeadlineAfter(5, TimeUnit.SECONDS)
            .listGreetings(request, new StreamObserver<HelloReply>() {

                @Override
                public void onNext(HelloReply value) {
                    System.out.println(value.getText());
                }

                @Override
                public void onError(Throwable error) {
                    System.err.println(
                        "RPC error: " + Status.fromThrowable(error).getCode()
                    );
                }

                @Override
                public void onCompleted() {
                    System.out.println("Server stream completed");
                }
            });
    }
}
~~~

In real applications, forward results/errors to a suitable abstraction (such as a future, a business-layer callback, or a properly integrated reactive stream) rather than printing to the console. Never assume data is already available immediately after calling **printGreetings()**.

### 4.3. Client-streaming and bidirectional-streaming

With client streaming, the async stub returns a **request observer**. The caller sends multiple messages via **onNext()** and then calls **onCompleted()** to signal it has finished sending. The result arrives via the **response observer**:

~~~java
StreamObserver<HelloReply> responseObserver =
        new StreamObserver<HelloReply>() {
    @Override
    public void onNext(HelloReply value) {
        System.out.println(value.getText());
    }

    @Override
    public void onError(Throwable error) {
        System.err.println(Status.fromThrowable(error).getCode());
    }

    @Override
    public void onCompleted() {
        System.out.println("CollectNames completed");
    }
};

StreamObserver<HelloRequest> requests =
        asyncStub.collectNames(responseObserver);

requests.onNext(HelloRequest.newBuilder().setName("Lan").build());
requests.onNext(HelloRequest.newBuilder().setName("Minh").build());
requests.onCompleted();
~~~

In the code above, **asyncStub** is a variable of type **GreeterGrpc.GreeterStub** already initialized from a Channel. With **chat(responseObserver)**, the client likewise receives a request observer, but the server can send interleaved responses while the client is still sending requests. Therefore, **you do not need to wait until calling onCompleted() on the send side before receiving messages on the response side** in bidirectional streaming.

Calling **onCompleted()** means **the client's send direction** has ended, not necessarily that the entire RPC has ended. The client must still wait for **onCompleted()** or **onError()** on the response observer to know the final outcome.

## 5. From stub call to server handler

Suppose the client calls:

~~~java
HelloReply reply = blockingStub.sayHello(
    HelloRequest.newBuilder().setName("Lan").build()
);
~~~

The main steps beneath the Java API layer are:

1. **The stub identifies the method descriptor**, service/method name, and request/response types; attaches call options such as deadline, credentials, and message limits.
2. **The Channel creates a client call**, selecting a transport/backend via the name resolver and load balancer. If needed, the Channel opens or reconnects TCP/TLS.
3. **The gRPC client** encodes the message to protobuf, wraps it in gRPC message framing, and sends it on an HTTP/2 stream along with headers/metadata.
4. **The gRPC server** receives headers with the path **/demo.greeter.v1.Greeter/SayHello**, decodes the request, and looks up the registered handler.
5. **The implementation** executes **sayHello()**, validates data, calls **responseObserver.onNext()**, and finishes with **onCompleted()** or **onError()**.
6. **The server runtime** sends the response and trailers containing **grpc-status**. The client runtime decodes the message and status, then completes the blocking/async/future call according to its API.

In traditional gRPC over HTTP/2, **one RPC corresponds to one HTTP/2 stream**; using streaming at the RPC level changes how many messages travel through the stream, rather than automatically creating a new connection or stream per message.

### 5.1. Difference between HTTP errors and gRPC errors

A failed RPC may still receive HTTP status **200**, because the application status code is conveyed via **grpc-status** in the trailers. Common codes include:

| gRPC code | Illustrative scenario | Client-side handling |
| --- | --- | --- |
| **INVALID_ARGUMENT** | Empty **name** field, malformed input | Fix the request; usually do not retry the same request as-is |
| **NOT_FOUND** | Business resource does not exist | Return appropriate information to the caller |
| **UNAUTHENTICATED** | Missing/invalid authentication credentials | Check credentials and session |
| **PERMISSION_DENIED** | Authenticated identity lacks permission | Handle authorization; do not retry automatically |
| **UNAVAILABLE** | Backend, connection, or proxy temporarily unavailable | Controlled retry when the operation is safe |
| **DEADLINE_EXCEEDED** | RPC did not finish before the deadline | Check latency and deadline; be cautious since the server may have already processed it |
| **INTERNAL** | Unexpected internal error | Log/trace on the server and return safe error details |

The server should use **Status** codes with clear semantics; the client should not rely on the **description** string to drive business logic because descriptions may change across versions or languages. For unknown errors, do not expose stack traces or secrets from the server to the client.

## 6. Metadata, deadlines, interceptors, and security

Although stubs hide HTTP/2, every call still has **operational context** to manage:

- **Metadata**: key-value pairs traveling in RPC headers/trailers. Typically used for request IDs, correlation IDs, tokens, or tracing information. Avoid logging full metadata if it contains secrets.
- **Deadline**: time limit for a call; can be propagated to the server via **grpc-timeout**. The server can cancel in-progress work when the deadline expires, though business logic needs to cooperate with cancellation properly.
- **Interceptor**: inserts logic around calls to record metrics, authenticate, propagate metadata, and trace. There are **client** and **server** interceptors; RPC-level interceptors are not a tool for manipulating individual HTTP/2 frames.
- **TLS**: protects the transport channel, verifies server identity, and can support mTLS. TLS requires properly configured certificates, trust chains, and HTTP/2/ALPN along the real network path.

**Clean separation of responsibilities:** interceptors handle cross-cutting concerns such as authentication/observability; handlers implement business logic and validate data preconditions; client services decide timeouts, error behavior, and retries for each use case.

A client deadline is a **hard bound for the caller**; do not treat it as a rollback guarantee. The RPC may have already mutated server data before the client receives **DEADLINE_EXCEEDED**. When write operations need retries, design an **idempotency key** or an appropriate deduplication mechanism.

## 7. Threading, backpressure, and lifecycle

### 7.1. Callbacks do not imply a separate business worker pool

With a blocking stub, the client thread waits for the result. With an async stub, the call returns early and callbacks run on the configured executor/runtime. On the server, implementation methods are also typically invoked by the runtime on execution threads; therefore:

- Avoid blocking processing threads with heavy, long-running work if the infrastructure is not designed for it; when necessary, offload work to an appropriate executor.
- Do not treat **StreamObserver** as an unsynchronized shared buffer when multiple threads emit messages concurrently.
- Cancel unnecessary work when the peer cancels, the deadline expires, or the server is shutting down.
- Enforce message limits and control send rates and buffering in streaming RPCs to prevent excessive memory usage.

**Backpressure** is the ability to slow down or pause sending data when the receiver is not ready. In gRPC Java, specialized observers such as **ServerCallStreamObserver** or **ClientCallStreamObserver** expose **isReady()** and **setOnReadyHandler(...)** signals to throttle output. Design carefully to handle readiness transitions, cancellations, and resume requests; HTTP/2 flow control does not fully replace application-level queue management.

### 7.2. Resource management rules

| Resource | Recommendation |
| --- | --- |
| **ManagedChannel** | Reuse across multiple RPCs/stubs; manage via bean or framework configuration; close on application shutdown |
| **Client stub** | Reusable; create newly configured variants with **with...** methods when needed |
| **Server** | Register services once; monitor status, shutdown, and RPC drain time |
| **StreamObserver** | Scoped to each streaming RPC; never reuse after a terminal event |
| **Executor / background jobs** | Bound load, clean up resources, and handle cancellation |

A common mistake is **creating a new ManagedChannel for every request**. This increases handshake, connection, and resource-management overhead and can cause bottlenecks under high load. The opposite mistake is **retaining a StreamObserver after an RPC has ended** and trying to keep sending on it; the result may be callback failures or undefined behavior.

## 8. Testing client/server over an in-process transport

gRPC-level integration tests can use **InProcessServerBuilder** and **InProcessChannelBuilder**. They allow calls to pass through the gRPC runtime without binding a TCP port, verifying service registration, API-level protobuf serialization, calls, and statuses.

JUnit 5 example:

~~~java
package dev.example.server;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;

import dev.example.grpc.greeter.GreeterGrpc;
import dev.example.grpc.greeter.HelloReply;
import dev.example.grpc.greeter.HelloRequest;
import io.grpc.ManagedChannel;
import io.grpc.Server;
import io.grpc.Status;
import io.grpc.StatusRuntimeException;
import io.grpc.inprocess.InProcessChannelBuilder;
import io.grpc.inprocess.InProcessServerBuilder;
import org.junit.jupiter.api.Test;

class GreeterEndpointTest {

    @Test
    void shouldReturnGreetingAndRejectBlankName() throws Exception {
        String serverName = InProcessServerBuilder.generateName();

        Server server = InProcessServerBuilder.forName(serverName)
                .directExecutor()
                .addService(new GreeterEndpoint())
                .build()
                .start();

        ManagedChannel channel = InProcessChannelBuilder.forName(serverName)
                .directExecutor()
                .build();

        try {
            GreeterGrpc.GreeterBlockingStub stub =
                    GreeterGrpc.newBlockingStub(channel);

            HelloReply result = stub.sayHello(
                    HelloRequest.newBuilder().setName("Lan").build()
            );
            assertEquals("Hello, Lan", result.getText());

            StatusRuntimeException error = assertThrows(
                    StatusRuntimeException.class,
                    () -> stub.sayHello(
                        HelloRequest.newBuilder().setName("").build()
                    )
            );
            assertEquals(
                    Status.Code.INVALID_ARGUMENT,
                    error.getStatus().getCode()
            );
        } finally {
            channel.shutdownNow();
            server.shutdownNow();
        }
    }
}
~~~

This test requires the **grpc-inprocess** artifact compatible with your grpc-java version and JUnit 5. **directExecutor()** is fine for simple examples because callbacks execute directly, but should not be used to simulate systems with blocking operations or complex concurrency.

**Limitation of in-process tests:** they verify the service API and RPC handling, but **do not prove** that TLS configuration, HTTP/2 proxies, DNS, load balancing, or real-network behavior are correct. Those aspects require separate integration tests with a real transport and matching infrastructure configuration.

When expanding coverage, also test unary success/failure, all four streaming modes, deadlines, mid-flight cancellation, metadata/interceptors, message limits, and graceful shutdown.

## 9. Common implementation pitfalls

| Symptom | Likely cause | Remediation |
| --- | --- | --- |
| Client receives **UNIMPLEMENTED** | Server did not register the implementation or deployed the wrong proto version/method | Check service descriptor, RPC path, registration, and contract compatibility |
| Client cannot connect even though Spring beans initialized | gRPC server not started or wrong port/TLS/HTTP2 | Check bean lifecycle, socket, proxy, and TLS settings |
| Unary RPC hangs until deadline | Handler did not call **onCompleted()** or **onError()**; blocking work | Ensure exactly one terminal event, measure handler duration |
| Streaming drops messages or hits callback errors | Multiple threads writing to the same observer; early termination or post-terminal writes | Coordinate writes and observer lifecycle |
| Client-streaming receives no response | Client did not call **onCompleted()** on the request observer | Send half-close and wait for terminal callback on the response side |
| CPU/memory grows under streaming load | Unbounded data, large queues, missing backpressure | Monitor buffers, bound in-flight items, and handle **isReady()** |
| Retries cause duplicate writes | Retrying non-idempotent RPCs when outcome is unclear | Use idempotency keys / business-aware retry policies |
| HTTP 200 yet call fails | Evaluating HTTP status instead of **grpc-status** | Handle **StatusRuntimeException** and gRPC status codes |

To monitor performance and reliability, record **RPC latency**, **gRPC status by method**, **in-flight RPCs**, **deadline exceeded**, **cancellation**, and streaming load characteristics. Combining client/server tracing helps pinpoint whether delays sit in queues, connections, interceptors, or handlers.

## 10. Hands-on lab and self-check questions

Follow these steps in order across two Spring applications or a suitable test environment:

1. Generate Java code from the proto file in section 2. Identify **GreeterGrpc**, message classes, the three stub types, and **GreeterImplBase**; do not edit generated files.
2. Start a gRPC server with **GreeterEndpoint** and call **SayHello** from a blocking stub. Confirm the method/response names and try an empty request to observe **INVALID_ARGUMENT**.
3. Call **ListGreetings** with an async stub and observe three **onNext()** calls followed by one **onCompleted()**.
4. Call **CollectNames** by sending multiple requests through the request observer, then half-close. Call **Chat** and observe that responses can arrive before the client finishes sending.
5. Apply a short deadline, simulate a slow server, and observe **DEADLINE_EXCEEDED**. Verify the client can reuse the Channel for another call.
6. Add an interceptor that records trace ID/latency and run an in-process test. When moving to a real transport, verify TLS/proxy, cancellation, and shutdown separately.

**Question 1: Which class must be modified when greeting logic changes but the .proto contract does not?**  
Usually the **server implementation**. Generated client stubs and messages stay unchanged as long as the contract does not change.

**Question 2: Why doesn't a Spring bean with a sayHello method automatically become a gRPC endpoint?**  
The gRPC runtime needs a service implementation matching the generated contract and **registered** with the gRPC server. Registration can be explicit or performed by the Spring integration library.

**Question 3: In client-streaming, does calling onCompleted() on the request observer mean the result has already been received?**  
**No.** It only indicates that the client has stopped sending requests. The final result arrives via the response observer.

**Question 4: Should you use a blocking stub for bidirectional streaming?**  
With the traditional grpc-java API shown in this lesson, **no**; use an async stub, request observer, and response observer for two-way communication.

## Summary

The **client stub and server implementation** architecture lets two Spring applications communicate using a clear Protocol Buffers contract. **Generated code** handles messages and RPC invocation APIs; the **client service** chooses the invocation style, deadlines, and error handling; **ManagedChannel** transports RPCs; and the **server implementation** validates requests, executes business logic, and properly completes the response stream. When building unary or streaming RPCs, tightly manage observer, Channel, resource lifecycles, and error states to keep the system reliable.
