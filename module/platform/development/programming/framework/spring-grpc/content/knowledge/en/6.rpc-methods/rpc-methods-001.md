# Defining Unary RPCs in Spring gRPC

In the **Spring gRPC** ecosystem, a **unary RPC** (single-request, single-response Remote Procedure Call) lets a Java application call a method on a service on another machine almost like calling a regular function. The communication contract is declared using **Protocol Buffers (Protobuf)**; code generation tools generate data types and client/server classes for Java. Spring manages the lifecycle of service components, while gRPC handles message transport, call status handling, and communication over HTTP/2.

This lesson focuses on how to **define, implement, and use unary RPCs**. Concepts such as metadata, deadlines, status, interceptors, TLS, testing, and observability are introduced to the extent needed to use unary methods properly.

## 1. What is a Unary RPC?

A unary RPC has the logical form:

**One request → server processing → one success response, or one error status.**

- **Client** sends exactly one *request message* of the declared data type.
- **Server** processes the request. If successful, the server sends exactly one *response message* and ends the RPC with gRPC status **OK**.
- If processing fails, the server ends the RPC with a non-OK **gRPC status**; the client may receive an error without receiving a response message.
- A single Protobuf request/response may be transported across multiple HTTP/2 frames. The number of network frames does not change the **one request message, one success response message** rule of a unary RPC.

~~~mermaid
sequenceDiagram
    participant C as Java client
    participant T as gRPC / HTTP/2
    participant S as Spring gRPC server
    C->>T: SayHello(HelloRequest)
    T->>S: Forward 1 request
    S->>S: Validate and process
    alt Success
        S-->>T: HelloReply + status OK
        T-->>C: 1 response
    else Failure
        S-->>T: Error gRPC status
        T-->>C: StatusRuntimeException (blocking stub)
    end
~~~

Suitable examples: fetching a profile by ID, validating a request, calculating shipping fees, looking up inventory, or creating an order. An important distinction is that **unary describes the number of messages in one RPC**, not that the server may only perform a single internal operation, nor does it automatically guarantee that business processing happens only once if the client retries the request.

| RPC Type | Client Request | Server Response | Syntax in Protobuf |
| --- | --- | --- | --- |
| **Unary** | 1 message | 1 message on success | **rpc SayHello(HelloRequest) returns (HelloReply);** |
| Server streaming | 1 message | Stream of multiple messages | Has **stream** before the response type |
| Client streaming | Stream of multiple messages | 1 message | Has **stream** before the request type |
| Bidirectional streaming | Stream of multiple messages | Stream of multiple messages | Has **stream** on both sides |

## 2. Declaring a Unary RPC Contract with Protocol Buffers

Create the file **src/main/proto/greeting.proto**:

~~~proto
syntax = "proto3";

package demo.greeting.v1;

option java_package = "vn.demo.grpc.greeting.v1";
option java_multiple_files = true;
option java_outer_classname = "GreetingProto";

service Greeter {
  rpc SayHello(HelloRequest) returns (HelloReply);
}

message HelloRequest {
  string name = 1;
}

message HelloReply {
  string message = 1;
}
~~~

Key components:

1. **service Greeter** is the gRPC service name.
2. **rpc SayHello(HelloRequest) returns (HelloReply)** defines a method that takes one **HelloRequest** and returns one **HelloReply**. There is no **stream** keyword, so this is a unary RPC.
3. **message** declares a Protobuf data structure. The number **1** is the *field number* used in the binary representation, not a default value.
4. **package demo.greeting.v1** is the service's namespace in Protobuf; the full RPC path is **/demo.greeting.v1.Greeter/SayHello**.
5. **java_package** specifies the package for generated Java code; **java_multiple_files = true** allows message classes to be generated separately.

After configuring the Protobuf compiler and the gRPC Java plugin in the project build, generated code typically includes:

- **HelloRequest**, **HelloReply**, and Protobuf support classes.
- **GreeterGrpc** with the base class **GreeterGrpc.GreeterImplBase** for server implementation.
- Client stub types such as **GreeterGrpc.GreeterBlockingStub**, **GreeterGrpc.GreeterFutureStub**, and **GreeterGrpc.GreeterStub**.

This is **contract-generated** code; you should not edit it manually. When evolving a new version of a message, preserve the meaning and field numbers of already-released fields; add new fields with unused numbers and use **reserved** for removed numbers or names to prevent reuse that breaks compatibility.

## 3. Implementing a Unary RPC on the Spring Server

Assuming the Spring Boot project already includes the Spring gRPC server component and the Java code-generation step from Protobuf files. You can implement the service by extending the generated base class, then declaring the implementation class as a Spring bean:

~~~java
package vn.demo.app;

import io.grpc.Status;
import io.grpc.stub.StreamObserver;
import org.springframework.stereotype.Service;
import vn.demo.grpc.greeting.v1.GreeterGrpc;
import vn.demo.grpc.greeting.v1.HelloReply;
import vn.demo.grpc.greeting.v1.HelloRequest;

@Service
public class GreeterService extends GreeterGrpc.GreeterImplBase {

    @Override
    public void sayHello(
            HelloRequest request,
            StreamObserver<HelloReply> responseObserver) {

        String name = request.getName().trim();
        if (name.isEmpty()) {
            responseObserver.onError(
                Status.INVALID_ARGUMENT
                    .withDescription("name must not be blank")
                    .asRuntimeException()
            );
            return;
        }

        HelloReply reply = HelloReply.newBuilder()
            .setMessage("Hello, " + name + "!")
            .build();

        responseObserver.onNext(reply);
        responseObserver.onCompleted();
    }
}
~~~

In a Spring gRPC configuration that automatically registers beans implementing **BindableService**, the **GreeterService** bean is registered with the gRPC server. If your project uses a different starter or integration version, check the corresponding service registration mechanism; the unary contract itself and the usage of **StreamObserver** remain unchanged.

The Java method **sayHello** follows the code-generation naming convention from **SayHello** in Protobuf. The **responseObserver** object is the channel through which the server completes the call:

- **Success:** call **onNext(reply)** exactly once, then call **onCompleted()** exactly once.
- **Failure:** call **onError(exception)** and return; do not subsequently call **onNext** or **onCompleted**.
- **Do not** call **onNext** twice to simulate a list of results. If you need multiple records in a single unary response, place them in a message with a **repeated** field; if you need to emit records sequentially, define a streaming RPC.

Do not report business errors using a success message containing a string like “ERROR” if they are actually RPC errors. Using appropriate gRPC status codes enables structured handling on the client.

## 4. Calling a Unary RPC from a Java Client

For unary RPCs, the simplest approach is a **blocking stub**: the Java call waits for the response or throws an exception if the RPC fails. The following example illustrates a Spring-managed client that uses gRPC Java to create a channel manually:

~~~java
package vn.demo.app;

import io.grpc.ManagedChannel;
import io.grpc.ManagedChannelBuilder;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import vn.demo.grpc.greeting.v1.GreeterGrpc;

@Configuration
public class GreetingClientConfig {

    @Bean(destroyMethod = "shutdown")
    ManagedChannel greetingChannel() {
        // Use plaintext only in trusted development environments.
        return ManagedChannelBuilder
            .forAddress("localhost", 9090)
            .usePlaintext()
            .build();
    }

    @Bean
    GreeterGrpc.GreeterBlockingStub greeterBlockingStub(
            ManagedChannel greetingChannel) {
        return GreeterGrpc.newBlockingStub(greetingChannel);
    }
}
~~~

~~~java
package vn.demo.app;

import io.grpc.StatusRuntimeException;
import java.util.concurrent.TimeUnit;
import org.springframework.stereotype.Service;
import vn.demo.grpc.greeting.v1.GreeterGrpc;
import vn.demo.grpc.greeting.v1.HelloReply;
import vn.demo.grpc.greeting.v1.HelloRequest;

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

        try {
            HelloReply reply = stub
                .withDeadlineAfter(2, TimeUnit.SECONDS)
                .sayHello(request);
            return reply.getMessage();
        } catch (StatusRuntimeException ex) {
            // Here the application can map the status code to a business error.
            throw new IllegalStateException(
                "gRPC SayHello failed: " + ex.getStatus().getCode(), ex);
        }
    }
}
~~~

Prerequisites for the example to work: the server is listening on the corresponding host/port; the client and server use classes generated from compatible contracts; the development environment has gRPC Java, Spring gRPC, and Protobuf code-generation dependencies configured. In real applications, load the address from configuration instead of hardcoding **localhost:9090**, and prefer the channel/client management mechanism provided by your project's Spring gRPC version.

**Blocking stub** fits synchronous processing flows. **Future stub** provides asynchronous results, while **async stub** supports callbacks via observers; both still adhere to the one-request, one-response contract of a unary RPC. Avoid blocking an asynchronous processing thread just to wait on a blocking stub if the architecture requires non-blocking behavior.

## 5. Deadlines, Status, Metadata, and Interceptors

### Deadlines and Call Cancellation

A **deadline** is the time limit a client is willing to wait for an RPC to complete. In the example, **withDeadlineAfter(2, TimeUnit.SECONDS)** creates a stub configured with a deadline for that call without mutating the original stub. When the deadline expires, the client typically receives **DEADLINE_EXCEEDED**. The server can also observe cancellation to stop work that is no longer needed.

Deadlines should derive from the time budget of the entire request, including downstream RPCs. Receiving a deadline exceeded error on the client **does not prove** that the server has not mutated data. When a unary RPC causes side effects such as payments or order creation, design an **idempotency key** or duplicate-execution prevention mechanism.

### Common Status Codes

| gRPC status | Common meaning | Handling approach |
| --- | --- | --- |
| **OK** | RPC completed successfully | Read response |
| **INVALID_ARGUMENT** | Invalid request data | Fix input; do not retry verbatim |
| **NOT_FOUND** | Requested resource does not exist | Handle not-found result |
| **UNAUTHENTICATED** | Missing or invalid credentials | Reissue/handle credentials |
| **PERMISSION_DENIED** | Identity verified but lacks permission | Check authorization |
| **DEADLINE_EXCEEDED** | Allowed time expired | Evaluate timeout and operation state |
| **UNAVAILABLE** | Service/connection temporarily unavailable | May retry with control if safe |
| **INTERNAL** | Internal error on the service side | Log for investigation, avoid exposing sensitive details |

On a **blocking stub**, RPC errors are represented by **StatusRuntimeException**, allowing you to read **ex.getStatus().getCode()** and, when present, trailer metadata. Regular Java exceptions on the server should not leak to the client as debug details; translate expected errors into appropriate statuses and log diagnostic details on the server side.

### Metadata, Interceptors, and TLS

**Metadata** is auxiliary information in the headers or trailers of a gRPC call, such as bearer tokens, request IDs, or tracing information. Primary business data should reside in Protobuf messages. **Client/server interceptors** are suitable for cross-cutting concerns such as authentication, timing logs, attaching trace IDs, and counting calls; avoid duplicating these operations in every **sayHello** method.

For example, a client can send **x-request-id** in metadata; a server interceptor reads this value to attach it to logs. Metadata does not provide security on its own: in production environments, protect the channel with **TLS**, consider **mTLS** when two services need mutual authentication, and configure appropriate authorization rules. Calling **usePlaintext()** in the example is for local/dev use only.

## 6. Testing Unary RPCs

You should test at least three cases: a valid request returns **one** response, an invalid request returns the expected status, and the client handles timeouts/connection errors according to policy. With gRPC Java, you can create an **in-process** server and channel to test the protocol without occupying a network port:

~~~java
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;

import io.grpc.ManagedChannel;
import io.grpc.Server;
import io.grpc.Status;
import io.grpc.StatusRuntimeException;
import io.grpc.inprocess.InProcessChannelBuilder;
import io.grpc.inprocess.InProcessServerBuilder;
import org.junit.jupiter.api.Test;
import vn.demo.grpc.greeting.v1.GreeterGrpc;
import vn.demo.grpc.greeting.v1.HelloRequest;

class GreeterServiceTest {

    @Test
    void unaryReturnsReplyOrValidationStatus() throws Exception {
        String serverName = InProcessServerBuilder.generateName();
        Server server = InProcessServerBuilder.forName(serverName)
            .directExecutor()
            .addService(new GreeterService())
            .build()
            .start();
        ManagedChannel channel = InProcessChannelBuilder
            .forName(serverName)
            .directExecutor()
            .build();

        try {
            var stub = GreeterGrpc.newBlockingStub(channel);
            var reply = stub.sayHello(
                HelloRequest.newBuilder().setName("An").build());
            assertEquals("Hello, An!", reply.getMessage());

            StatusRuntimeException error = assertThrows(
                StatusRuntimeException.class,
                () -> stub.sayHello(
                    HelloRequest.newBuilder().setName("  ").build()));
            assertEquals(
                Status.Code.INVALID_ARGUMENT,
                error.getStatus().getCode());
        } finally {
            channel.shutdownNow();
            server.shutdownNow();
        }
    }
}
~~~

The test above requires the **gRPC in-process** library and the corresponding JUnit dependencies, testing RPC logic and the gRPC Java protocol. To verify that Spring actually registers the service bean, add an **integration test that boots the Spring context/gRPC server** and makes calls over a channel configured for the test environment. For TLS or interceptors, separate integration tests are needed for transport and metadata.

In operations, monitor **success/error rates by status**, **latency per method and p95/p99 percentiles**, **active in-flight RPCs**, and **exceeded deadlines**. Use trace IDs to correlate a unary RPC with downstream operations, while avoiding logging authentication tokens or sensitive data.

## 7. Common Design Mistakes

1. **Confusing unary with streaming:** calling **onNext** multiple times on a unary server or declaring **stream** when only one response is needed. Choose cardinality right in the Protobuf contract.
2. **Forgetting to complete the observer:** calling **onNext** without **onCompleted**, leaving the RPC improperly terminated. Every execution branch must end with **onCompleted** or **onError**.
3. **Missing deadlines:** clients may wait indefinitely when a downstream dependency hangs. Set intentional time budgets at call boundaries.
4. **Retrying non-idempotent operations:** the request was processed by the server, but the client never received the response; retrying may create duplicate data. Design idempotency keys or verify outcomes before retrying.
5. **Changing released Protobuf field numbers:** can cause old data to be misinterpreted. Keep field numbers stable and manage contract compatibility.
6. **Using plaintext or leaking error details in production:** configure TLS, authentication, and error mapping appropriate to trust boundaries.

## 8. Summary and Self-Check

To define a unary RPC, simply declare an **rpc Method(Request) returns (Response)** method inside a Protobuf **service** without the **stream** keyword. On the Java server, implement the corresponding method from **GreeterGrpc.GreeterImplBase** and ensure every call ends according to the rule: **one response on success or one error status**. On the client, use the generated stub and set deadlines according to the application's time budget.

Answer the following questions to check your understanding:

- If you need to return 100 products in a unary RPC, how should you model the response? When should you switch to server streaming?
- Why is calling **onNext(reply)** without calling **onCompleted()** a bug?
- If a client receives **DEADLINE_EXCEEDED** after sending an order creation request, is it safe to conclude that the order was not created?
- In the case of invalid input data, should the server return **INVALID_ARGUMENT** or **INTERNAL**? How should the client handle them differently?

Mastering these rules forms the foundation for implementing gRPC services with Spring and expanding into streaming RPCs, advanced interceptors, security, and reliability testing.
