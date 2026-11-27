# Payloadless Methods Using Empty

Some RPCs only need the client to ask the server to perform an action, or only need confirmation that an operation has completed. In such cases, the request or response may not need any data fields. **Protocol Buffers** provides the standard **google.protobuf.Empty** type for an empty message.

**Empty** is still a **Protobuf message**. Using it does not remove the request/response from the contract, skip the gRPC call, or eliminate transport-level transmission. It expresses that the corresponding side needs no field-based business payload. This is the explicit way to declare methods that need no input data, no output data, or neither in **Spring gRPC**.

## 1. Declaring RPCs with google.protobuf.Empty

To use this standard type, import **google/protobuf/empty.proto**:

~~~proto
syntax = "proto3";

package demo.maintenance.v1;

option java_package = "vn.demo.grpc.maintenance.v1";
option java_multiple_files = true;

import "google/protobuf/empty.proto";

service MaintenanceService {
  // Client does not need to send business data.
  rpc RefreshCatalog(google.protobuf.Empty)
      returns (RefreshResult);

  // Server only needs to confirm completion, returning no business payload.
  rpc AcknowledgeStartup(StartupSignal)
      returns (google.protobuf.Empty);

  // Neither side needs a payload.
  rpc Ping(google.protobuf.Empty)
      returns (google.protobuf.Empty);
}

message RefreshResult {
  int64 refreshed_items = 1;
}

message StartupSignal {
  string instance_id = 1;
}
~~~

The three methods demonstrate three cases:

| Method | Request | Response | Meaning |
| --- | --- | --- | --- |
| **RefreshCatalog** | **Empty** | **RefreshResult** | No business parameters needed; server returns a result with data |
| **AcknowledgeStartup** | **StartupSignal** | **Empty** | Client sends data; server only confirms success |
| **Ping** | **Empty** | **Empty** | No business payload in either direction |

In an RPC declaration, Protobuf still requires both a request type and a response type. **google.protobuf.Empty** satisfies the message-type requirement when no fields need to be exchanged. Do not use an empty string, **null**, or omit the return type to represent this case.

## 2. Empty Is an Empty Message, Not the Absence of an RPC

**google.protobuf.Empty** is a **well-known type** defined by Protobuf. This message has no fields. When serialized, the Protobuf payload of an Empty instance is **0 bytes** long.

However, the gRPC call still has:

- An RPC with a full method name and metadata like any other method.
- An HTTP/2 stream to transport the call.
- A gRPC message in the request and/or response direction corresponding to the Empty type.
- A gRPC terminal status, such as **OK** or **INVALID_ARGUMENT**.

At the gRPC framing layer, the message still carries a header containing the compression flag and payload length. For Empty, the payload length is 0; that does not eliminate the message or the HTTP/2 stream. Therefore, when inspecting network traces, do not conclude that the method was not called simply because no business fields appear in the payload.

## 3. Implementing the Server in Spring gRPC

After configuring code generation from .proto, Java uses **com.google.protobuf.Empty**. Example implementing Ping and RefreshCatalog:

~~~java
package vn.demo.maintenance;

import com.google.protobuf.Empty;
import io.grpc.Status;
import io.grpc.stub.StreamObserver;
import org.springframework.stereotype.Service;
import vn.demo.grpc.maintenance.v1.MaintenanceServiceGrpc;
import vn.demo.grpc.maintenance.v1.RefreshResult;

@Service
public class MaintenanceServiceImpl
        extends MaintenanceServiceGrpc.MaintenanceServiceImplBase {

    @Override
    public void ping(
            Empty request,
            StreamObserver<Empty> responseObserver) {
        // No payload to process.
        responseObserver.onNext(Empty.getDefaultInstance());
        responseObserver.onCompleted();
    }

    @Override
    public void refreshCatalog(
            Empty request,
            StreamObserver<RefreshResult> responseObserver) {
        try {
            long refreshed = catalogRefresher.refresh();

            responseObserver.onNext(RefreshResult.newBuilder()
                .setRefreshedItems(refreshed)
                .build());
            responseObserver.onCompleted();
        } catch (CatalogRefreshException ex) {
            responseObserver.onError(Status.INTERNAL
                .withDescription("catalog refresh failed")
                .withCause(ex)
                .asRuntimeException());
        }
    }
}
~~~

**catalogRefresher** is a business component injected into the service; its dependency declaration is omitted to focus on the RPC signatures. When using Empty, the server must still complete the observer according to the rules:

- Success: emit one response message (if the response type is Empty, use **Empty.getDefaultInstance()**), then call **onCompleted()**.
- Failure: call **onError(...)** with an appropriate gRPC status; do not emit a success response afterward.

Even when the response is Empty, **do not omit onNext()** in a successful unary implementation. **onCompleted()** only signals the end of the response stream; it does not replace the response message required by the unary contract.

## 4. Calling the RPC from a Java Client

With a blocking stub, the Ping call still returns an Empty instance, even though there are no fields to read:

~~~java
import com.google.protobuf.Empty;
import java.util.concurrent.TimeUnit;

Empty response = blockingStub
    .withDeadlineAfter(2, TimeUnit.SECONDS)
    .ping(Empty.getDefaultInstance());

// No business fields to read from the response.
System.out.println("Ping completed");
~~~

For RefreshCatalog, the client also sends Empty yet receives a populated result:

~~~java
RefreshResult result = blockingStub
    .withDeadlineAfter(10, TimeUnit.SECONDS)
    .refreshCatalog(Empty.getDefaultInstance());

System.out.println("Refreshed: " + result.getRefreshedItems());
~~~

In a Spring application, stubs/channels should be configured and lifecycle-managed via the integration mechanism of your Spring gRPC version. **withDeadlineAfter(...)** bounds the call; having no fields in the request does not remove the need for deadlines or error handling.

## 5. When Should Empty Be Used?

Use google.protobuf.Empty when the corresponding side genuinely **needs no business data**:

- **Empty request:** client requests a global operation needing no parameters, e.g., **RefreshCatalog(Empty)**.
- **Empty response:** server only needs to report operation success via gRPC status, e.g., **AcknowledgeStartup(StartupSignal) returns (Empty)**.
- **Both empty:** simple connectivity check operations such as **Ping(Empty) returns (Empty)**.

Do not use Empty merely to avoid schema design when data actually needs to be passed. For instance, if RefreshCatalog needs to select a tenant, region, or execution mode, it should accept a request message containing those fields.

### Empty or a Dedicated Message with No Fields?

You could declare:

~~~proto
message RefreshCatalogRequest {}

rpc RefreshCatalog(RefreshCatalogRequest)
    returns (RefreshResult);
~~~

However, if the message has no distinct semantics and is certain not to need fields, **google.protobuf.Empty** is a standard, immediately recognizable type that avoids creating extra messages solely to represent emptiness.

Conversely, if the contract is expected to expand with fields such as **tenant_id**, **force_refresh**, or **scope**, consider creating **RefreshCatalogRequest** from the start. Changing a released method's request type from google.protobuf.Empty to a custom message is a contract change that can break existing clients. You cannot add business fields to the standard google.protobuf.Empty type.

## 6. Empty Does Not Replace Metadata or Status

An empty message only means there is no **field payload** in that direction. It does not mean the call can skip:

- **Authentication/authorization:** the server must still determine who is calling and whether they are authorized to perform the action.
- **Metadata:** request IDs, tenant context, or trace context can still be passed in RPC metadata per system policy.
- **Deadlines/cancellation:** a payloadless operation can still run long, be cancelled, or time out.
- **gRPC status:** the client relies on **OK**, **UNAUTHENTICATED**, **PERMISSION_DENIED**, **DEADLINE_EXCEEDED**, **INTERNAL**, and so on to determine the call outcome.

For example, **RefreshCatalog(Empty)** may require administrative permissions. If the caller lacks permission, the server returns **PERMISSION_DENIED**; do not send Empty as though the operation succeeded.

## 7. Testing Methods That Use Empty

Tests should verify both that the client sends Empty properly and that the server returns the expected response/status. Example using gRPC in-process:

~~~java
import static org.junit.jupiter.api.Assertions.assertNotNull;

import com.google.protobuf.Empty;
import io.grpc.ManagedChannel;
import io.grpc.Server;
import io.grpc.inprocess.InProcessChannelBuilder;
import io.grpc.inprocess.InProcessServerBuilder;
import org.junit.jupiter.api.Test;
import vn.demo.grpc.maintenance.v1.MaintenanceServiceGrpc;

class MaintenanceServiceTest {

    @Test
    void pingAcceptsAndReturnsEmptyMessage() throws Exception {
        String serverName = InProcessServerBuilder.generateName();
        Server server = InProcessServerBuilder.forName(serverName)
            .directExecutor()
            .addService(new MaintenanceServiceImpl())
            .build()
            .start();
        ManagedChannel channel = InProcessChannelBuilder
            .forName(serverName)
            .directExecutor()
            .build();

        try {
            var stub = MaintenanceServiceGrpc.newBlockingStub(channel);
            Empty response = stub.ping(Empty.getDefaultInstance());
            assertNotNull(response);
        } finally {
            channel.shutdownNow();
            server.shutdownNow();
        }
    }
}
~~~

This test requires JUnit and the **gRPC in-process** dependency compatible with the project's gRPC Java version. To verify Spring auto-registration of the service bean, interceptors, and security policies, add an integration test booting the Spring context under test configuration. For methods with side effects like refreshing data, test access permissions, deadlines, error statuses, and whether the operation actually completed.

## 8. Common Mistakes

| Mistake | Consequence | Fix |
| --- | --- | --- |
| Thinking Empty means no request/response | Misunderstands contract and RPC lifecycle | Treat Empty as a message with zero fields |
| Omitting onNext() because the response has no data | Unary server fails to emit a response message per contract | Send **Empty.getDefaultInstance()** then **onCompleted()** |
| Using Empty when tenant or execution mode is needed | Cannot pass business parameters | Create a request message with explicit fields |
| Using empty string or null instead of Empty | Not a valid Protobuf message type | Use **google.protobuf.Empty** |
| Assuming an Empty method needs no security | Can expose sensitive operations to unauthorized callers | Still enforce authentication and authorization |
| Switching Empty to a custom message post-release without migration | Older clients may become incompatible | Publish a new contract or migration plan |

## 9. Summary and Self-Check

Standard declaration:

~~~proto
import "google/protobuf/empty.proto";

rpc Ping(google.protobuf.Empty)
    returns (google.protobuf.Empty);
~~~

**google.protobuf.Empty** is a **Protobuf message with no fields**, used when one direction of an RPC needs no business payload. The RPC still has request/response messages, an HTTP/2 stream, metadata, and a gRPC status. In Java, use **Empty.getDefaultInstance()** to construct the empty message; a successful unary server still sends a response via **onNext()** followed by **onCompleted()**.

Self-check:

1. Is **Ping(Empty) returns (Empty)** a call without an HTTP/2 stream? Explain.
2. Why must the server still call **onNext(Empty.getDefaultInstance())** when returning an Empty response?
3. When should you use google.protobuf.Empty, and when should you create a dedicated empty request message?
4. Does a method accepting Empty still need authentication, metadata, and deadlines? Why?
5. Why can changing a request type from Empty to a custom message affect already-released clients?

Choosing Empty at the right time makes contracts clearly express when an operation requires no payload in a given direction, while keeping Protobuf and Java APIs clean and consistent in Spring gRPC.
