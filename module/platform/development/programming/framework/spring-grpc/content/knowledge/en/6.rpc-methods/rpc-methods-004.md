# Defining Bidirectional Streaming RPCs in Spring gRPC

A **bidirectional streaming RPC** allows the client to send **multiple request messages** and the server to send **multiple response messages** within **a single RPC call**. Both sides can send and receive independently while the RPC remains open: the server does not need to wait for the client to finish sending before responding, and the client can continue sending while the server is emitting data.

In the **Spring gRPC** ecosystem, the RPC contract is defined with **Protocol Buffers**, code-generation tools generate the Java messages and stubs, and the Spring application implements the server and manages the service components. This lesson covers how to **define bidirectional streaming RPCs**, the lifecycle of both streams, server/client code, flow control, metadata, deadlines, status, TLS, testing, and reliability monitoring.

## 1. How Does a Bidirectional Streaming RPC Work?

At the contract level, **both the request and response have the stream keyword**:

~~~proto
rpc Chat(stream ChatMessage) returns (stream ChatEvent);
~~~

Example of an exchange session:

~~~mermaid
sequenceDiagram
    participant C as Java client
    participant S as Spring gRPC server
    C->>S: Open Chat RPC
    C->>S: ChatMessage A
    S-->>C: ChatEvent 1
    S-->>C: ChatEvent 2
    C->>S: ChatMessage B
    C->>S: ChatMessage C
    S-->>C: ChatEvent 3
    C->>S: onCompleted() - half-close
    S-->>C: ChatEvent 4
    S-->>C: onCompleted() + status OK
~~~

In the diagram, the server emits two events after the client has sent only one message, and the client continues sending while responses may be arriving. This is **full-duplex**: both directions can operate concurrently. The number of requests and responses **does not have to be equal**, and the server is not constrained to emit exactly one response per request.

| RPC Type | Client Sends | Server Returns | Protobuf Declaration |
| --- | --- | --- | --- |
| Unary | One message | One message on success | **rpc Get(Req) returns (Res);** |
| Server streaming | One message | A stream of messages | **rpc Watch(Req) returns (stream Res);** |
| Client streaming | A stream of messages | One message on success | **rpc Upload(stream Req) returns (Res);** |
| **Bidirectional streaming** | **A stream of messages** | **A stream of messages** | **rpc Chat(stream Req) returns (stream Res);** |

Each direction has its own message ordering. Within a single direction, gRPC preserves the order sent, but there is **no global ordering between requests and responses**. A response can arrive while the client is still sending requests. Questions such as which request a response answers, who may send first, and when to stop the session must be defined at the **business layer**.

Bidirectional streaming suits real-time chat, IoT devices sending telemetry while receiving commands, multi-user collaboration, or exchanging control signals. If the client only needs to send a batch of data and receive a single aggregated result, client streaming is simpler; if the client sends one request and only receives updates, server streaming may be more appropriate.

## 2. Defining the Contract with Protocol Buffers

Running example: a client sends messages into a room, and the server returns acknowledgment events. This is a **rule of this example**, not a requirement that every bidirectional RPC must reply one-for-one per request.

Create the file **src/main/proto/chat.proto**:

~~~proto
syntax = "proto3";

package demo.chat.v1;

option java_package = "vn.demo.grpc.chat.v1";
option java_multiple_files = true;
option java_outer_classname = "ChatProto";

service ChatService {
  rpc Chat(stream ChatMessage) returns (stream ChatEvent);
}

message ChatMessage {
  string room_id = 1;
  string sender = 2;
  string text = 3;
  int64 client_sequence = 4;
}

message ChatEvent {
  string room_id = 1;
  string sender = 2;
  string text = 3;
  int64 client_sequence = 4;
}
~~~

**Contract explanation:**

1. **service ChatService** is the gRPC service definition containing the **Chat** method.
2. **stream ChatMessage** represents the client direction, which can send from 0 to many messages.
3. **stream ChatEvent** represents the server direction, which can send from 0 to many messages.
4. The full method path name is **/demo.chat.v1.ChatService/Chat**.
5. **package demo.chat.v1** is the Protobuf namespace; **java_package** determines the package of the generated Java classes.
6. **client_sequence** helps correlate responses with requests; by itself, this field does not guarantee durable persistence confirmation or duplicate-processing protection.

The numbers **1**, **2**, **3**, **4** are *field numbers* on the wire. In proto3, omitted scalars take default values such as empty string or 0. Therefore, the server must validate required constraints at the business layer. Once the schema is released, preserve compatibility by not changing the meaning of used field numbers; mark removed fields as **reserved** to avoid accidental reuse.

When the build is configured with **protoc** and the **gRPC Java** plugin, generated code typically includes:

- **ChatMessage**, **ChatEvent**, and related Protobuf classes.
- **ChatServiceGrpc.ChatServiceImplBase** for implementing the server.
- **ChatServiceGrpc.ChatServiceStub** for calling the RPC asynchronously from a Java client.

Bidirectional streaming clients use the **async stub** in the standard gRPC Java API. Generated classes should not be edited manually; make contract changes in the **.proto** file and regenerate code.

## 3. Two StreamObservers in One RPC

The bidirectional streaming method signature on a Java server:

~~~java
public StreamObserver<ChatMessage> chat(
    StreamObserver<ChatEvent> responseObserver);
~~~

The **parameter observer** is used by the server to send **ChatEvent** messages to the client; the **returned observer** is used by the server to receive **ChatMessage** messages from the client. Both directions have separate callbacks yet share the lifecycle of a single RPC, including metadata, deadline, completion status, and cancellation.

| Role | Observer | Responsibility |
| --- | --- | --- |
| Server receive | Returned **StreamObserver<ChatMessage>** | **onNext** receives requests; **onCompleted** learns the client finished sending; **onError** learns the receive direction ended abnormally |
| Server send | Passed-in **StreamObserver<ChatEvent>** | **onNext** sends responses; **onCompleted** completes responses successfully; **onError** reports an RPC error |
| Client send | Observer returned from **stub.chat(...)** | **onNext** sends requests; **onCompleted** half-closes; **onError** stops/cancels the send direction |
| Client receive | Observer passed into **stub.chat(...)** | **onNext** receives responses; **onCompleted** RPC completed successfully; **onError** RPC errored |

**Half-close** is when one side stops sending data while still able to receive data from the other side. When the client calls **requestObserver.onCompleted()**, the server can continue sending responses before calling **responseObserver.onCompleted()**. The server can also decide to terminate early based on business rules.

Each sending observer must be terminated exactly once with **onCompleted** or **onError**. After termination, never call **onNext** on that observer. If the RPC is cancelled, stop remaining work and release resources; do not continue treating it as a successful session.

## 4. Implementing the Server in Spring gRPC

Assuming the Spring Boot application has configured Spring gRPC dependencies and Protobuf code generation, and automatically registers Spring beans implementing **BindableService** with the gRPC server. You can then implement:

~~~java
package vn.demo.app;

import io.grpc.Status;
import io.grpc.stub.StreamObserver;
import org.springframework.stereotype.Service;
import vn.demo.grpc.chat.v1.ChatEvent;
import vn.demo.grpc.chat.v1.ChatMessage;
import vn.demo.grpc.chat.v1.ChatServiceGrpc;

@Service
public class ChatServiceImpl extends ChatServiceGrpc.ChatServiceImplBase {

    private static final long MAX_MESSAGES = 1000;

    @Override
    public StreamObserver<ChatMessage> chat(
            StreamObserver<ChatEvent> responseObserver) {

        // New observer and state per RPC.
        return new StreamObserver<>() {
            private String roomId;
            private long receivedCount;
            private boolean terminated;

            @Override
            public void onNext(ChatMessage request) {
                if (terminated) {
                    return;
                }

                if (request.getRoomId().isBlank()
                        || request.getSender().isBlank()
                        || request.getText().isBlank()
                        || request.getClientSequence() <= 0) {
                    fail(Status.INVALID_ARGUMENT
                        .withDescription("invalid chat message"));
                    return;
                }

                if (roomId == null) {
                    roomId = request.getRoomId();
                } else if (!roomId.equals(request.getRoomId())) {
                    fail(Status.INVALID_ARGUMENT
                        .withDescription("room cannot change in this RPC"));
                    return;
                }

                if (receivedCount >= MAX_MESSAGES) {
                    fail(Status.RESOURCE_EXHAUSTED
                        .withDescription("too many messages"));
                    return;
                }
                receivedCount++;

                ChatEvent event = ChatEvent.newBuilder()
                    .setRoomId(roomId)
                    .setSender("server")
                    .setText("Received: " + request.getText())
                    .setClientSequence(request.getClientSequence())
                    .build();

                // Can respond while the client continues sending.
                responseObserver.onNext(event);
            }

            @Override
            public void onError(Throwable error) {
                // Client cancelled/stream error: clean up resources if any.
                terminated = true;
            }

            @Override
            public void onCompleted() {
                if (terminated) {
                    return;
                }
                terminated = true;
                responseObserver.onCompleted();
            }

            private void fail(Status status) {
                terminated = true;
                responseObserver.onError(status.asRuntimeException());
            }
        };
    }
}
~~~

In this example, the server sends a **ChatEvent** immediately after each valid **ChatMessage**. The service keeps **roomId**, **receivedCount**, and **terminated** inside a newly created observer per RPC so two concurrent calls do not mix state. Even though Spring usually manages service beans as singletons, session state still must be isolated.

The server returns **INVALID_ARGUMENT** if a message is missing critical fields, switches rooms mid-session, or has an invalid sequence; it returns **RESOURCE_EXHAUSTED** when exceeding the message count limit. After the client validly half-closes, the server closes the response direction with **onCompleted()**.

**Limitations of the example:** the server only sends acknowledgments back to the calling client and does not broadcast messages to other clients. A multi-user chat application needs room membership management, response stream registration, bounded queues, broadcast mechanisms, and connection state tracking. If multiple threads generate events for a single session, **serialize** all calls to the same response observer and coordinate flow control.

How gRPC service beans are registered and ports are configured may differ across Spring gRPC starters/versions. Use the mechanism provided by your project's version; the gRPC Java **StreamObserver** signature still expresses the same bidirectional contract.

## 5. Java Client Exchanging Data Bidirectionally with Async Stub

The client calls **stub.chat(responseObserver)** and receives an observer to send requests. Response callbacks can execute interleaved while the client is sending. Example Java application connecting to a local server:

~~~java
package vn.demo.app;

import io.grpc.ManagedChannel;
import io.grpc.ManagedChannelBuilder;
import io.grpc.Status;
import io.grpc.stub.StreamObserver;
import java.util.List;
import java.util.concurrent.CopyOnWriteArrayList;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicReference;
import vn.demo.grpc.chat.v1.ChatEvent;
import vn.demo.grpc.chat.v1.ChatMessage;
import vn.demo.grpc.chat.v1.ChatServiceGrpc;

public class ChatClientDemo {

    public static void main(String[] args) throws InterruptedException {
        // Plaintext only for controlled local/dev environments.
        ManagedChannel channel = ManagedChannelBuilder
            .forAddress("localhost", 9090)
            .usePlaintext()
            .build();

        try {
            var stub = ChatServiceGrpc.newStub(channel)
                .withDeadlineAfter(5, TimeUnit.SECONDS);

            CountDownLatch finished = new CountDownLatch(1);
            List<ChatEvent> events = new CopyOnWriteArrayList<>();
            AtomicReference<Throwable> failure =
                new AtomicReference<>();

            StreamObserver<ChatMessage> requests = stub.chat(
                new StreamObserver<ChatEvent>() {
                    @Override
                    public void onNext(ChatEvent event) {
                        events.add(event);
                        System.out.println("Server: " + event.getText());
                    }

                    @Override
                    public void onError(Throwable error) {
                        failure.set(error);
                        finished.countDown();
                    }

                    @Override
                    public void onCompleted() {
                        finished.countDown();
                    }
                }
            );

            requests.onNext(ChatMessage.newBuilder()
                .setRoomId("general")
                .setSender("an")
                .setText("Hello!")
                .setClientSequence(1)
                .build());

            requests.onNext(ChatMessage.newBuilder()
                .setRoomId("general")
                .setSender("an")
                .setText("See you later.")
                .setClientSequence(2)
                .build());

            // End the send direction while still waiting for final responses.
            requests.onCompleted();

            if (!finished.await(6, TimeUnit.SECONDS)) {
                throw new IllegalStateException("Chat RPC timed out");
            }
            if (failure.get() != null) {
                Status.Code code =
                    Status.fromThrowable(failure.get()).getCode();
                throw new IllegalStateException(
                    "Chat RPC failed: " + code, failure.get());
            }

            System.out.println("Events received: " + events.size());
        } finally {
            channel.shutdownNow();
        }
    }
}
~~~

With the demo server, two valid requests lead to two acknowledgment events. However, the number of responses is a decision of the **business protocol**, not a fixed rule of bidirectional streaming. Even before the client calls **requests.onCompleted()**, the **responseObserver.onNext(...)** callback can already receive data.

The example creates a channel in a console program for ease of learning. In a Spring application, configure the endpoint from application properties, reuse channels, and use the channel/stub management provided by Spring gRPC. Calling **shutdownNow** at the end of main suits a short example; long-running applications should tie channel lifecycle to the application lifecycle.

### Keeping a Session Open Long-Term

A client can keep the request stream open to send whenever the user types a new message, while the server also emits events at any time. When the user ends the session, the client can half-close and continue receiving final events, or cancel the RPC outright according to application rules. Clearly define when the server is allowed to close the stream, inactivity timeouts, and reconnection mechanisms on network loss.

## 6. Ordering, Correlation, and Flow Control

**Ordering is preserved within each direction of a stream**, but there is no shared ordering between client → server and server → client. Therefore, you must not assume:

- Request message **N** always produces response **N**.
- Receiving a response means the message has been **durably persisted** to the database.
- Returning from **onNext(...)** means the other side has finished processing.
- gRPC automatically deduplicates events when the client reconnects and resends messages.

When you need to correlate requests and responses, add a **correlation ID** or **sequence** (like **client_sequence**) and clearly define the acknowledgment semantics. If the server proactively emits multiple event types, you can use Protobuf **oneof** to distinguish acknowledgments, notifications, status updates, or business errors.

HTTP/2/gRPC **flow control** manages data transfer at the transport level, but does not automatically bound application-level queues. One side calling **onNext** too quickly while the receiving side processes slowly can cause data buildup and increased memory usage.

In gRPC Java:

1. **ClientCallStreamObserver** and **ServerCallStreamObserver** provide **isReady()** and **setOnReadyHandler(...)** so the application can pace sending with current write capacity.
2. Async streaming clients can configure send control in **ClientResponseObserver.beforeStart(...)** before transmitting many messages.
3. **isReady()** reflects flow-control write readiness, **not confirmation that the server has received or durably stored** the data.
4. Implement **bounded queues**, message count/size quotas, concurrent stream limits, and a strategy to cancel streams when the receiver is slow.
5. gRPC callbacks should avoid long blocking work. If a dedicated executor is needed, coordinate results back to the observer in the proper order and protect shared state.

**StreamObserver is not thread-safe by default.** When multiple threads emit events into the same response observer, serialize **onNext/onCompleted/onError** rather than calling them concurrently. Avoid letting send and receive directions wait indefinitely on each other and cause deadlocks.

## 7. Deadlines, Cancellation, Status, and Session Recovery

Deadlines apply to the **entire RPC**, including the time the stream is open, sending messages, server processing, and exchanging responses:

~~~java
var stub = ChatServiceGrpc.newStub(channel)
    .withDeadlineAfter(5, TimeUnit.SECONDS);
~~~

Sending a new message **does not automatically extend the deadline**. For potentially long-lived sessions, choose an appropriate lifetime and reconnection policy aligned with application semantics.

| gRPC status | Common Meaning | Handling Suggestion |
| --- | --- | --- |
| **OK** | RPC completed successfully | Finalize session |
| **INVALID_ARGUMENT** | Invalid message | Fix data, do not retry verbatim |
| **UNAUTHENTICATED** | Missing or invalid credentials | Handle authentication |
| **PERMISSION_DENIED** | Lacks permission to access resource | Check authorization |
| **RESOURCE_EXHAUSTED** | Exceeded quota or stream limit | Reduce load, check limits |
| **DEADLINE_EXCEEDED** | RPC exceeded time limit | Determine which operations occurred |
| **CANCELLED** | Call was cancelled | Clean up state and resources |
| **UNAVAILABLE** | Service or connection temporarily unavailable | Reconnect with control |
| **INTERNAL** | Internal processing error | Log trace/error safely, investigate |

The client can read the status code in the error callback via **Status.fromThrowable(error).getCode()**. The server uses **responseObserver.onError(Status.INVALID_ARGUMENT.withDescription("...").asRuntimeException())** to report structured errors.

Client **onCompleted()** means normal completion of sending, whereas **onError(...)** or gRPC's cancellation API is used to terminate abnormally or cancel the call. After termination, send no further messages. If the server already processed part of the stream before cancellation, cancelling does not automatically roll back those business side effects.

When the network drops, the client may not know which messages the server processed. Automatically replaying the whole stream easily causes duplicate writes. A reliable recovery protocol typically needs a **session ID/resume token**, **message ID/sequence**, duplicate-processing prevention, and application-level checkpoints/acknowledgments. gRPC does not automatically provide **exactly-once** guarantees for business write operations.

## 8. Metadata, Interceptors, TLS, and Monitoring

**Metadata** carries RPC-level information, such as authorization tokens, request IDs, tenant IDs, and trace context. It does not replace per-message payloads; fields like **room_id**, **sender**, and **client_sequence** belong in Protobuf, while authentication credentials are typically handled at call boundaries.

**Client/server interceptors** can attach metadata, perform authentication/authorization, record traces, and collect timing and status code metrics. For long streams, one RPC can contain thousands of messages, so measure **messages/bytes in each direction** alongside RPC counts.

Key deployment principles:

- Use **TLS** in production; consider **mTLS** when services need mutual authentication.
- Do not trust the client-sent **sender** field as an authenticated identity; verify credentials and check room/tenant permissions.
- Do not log tokens, sensitive content, or entire large streams.
- Monitor **active open streams**, stream lifetimes, error rates by status, latency, message/byte throughput, and cancellations or deadline exceedances.
- Enforce quotas, time limits, and memory limits so long streams do not consume unbounded resources.

**usePlaintext()** in the client code is only for illustration in trusted local/dev runs. Actual TLS/interceptor configuration depends on your Spring gRPC version, gRPC Java, and deployment infrastructure.

## 9. Testing Bidirectional Streaming RPCs

You should test that both directions genuinely exchange messages. You can use a **gRPC in-process server/channel** to run calls with the async stub without occupying a network port:

~~~java
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNull;
import static org.junit.jupiter.api.Assertions.assertTrue;

import io.grpc.ManagedChannel;
import io.grpc.Server;
import io.grpc.inprocess.InProcessChannelBuilder;
import io.grpc.inprocess.InProcessServerBuilder;
import io.grpc.stub.StreamObserver;
import java.util.List;
import java.util.concurrent.CopyOnWriteArrayList;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicReference;
import org.junit.jupiter.api.Test;
import vn.demo.grpc.chat.v1.ChatEvent;
import vn.demo.grpc.chat.v1.ChatMessage;
import vn.demo.grpc.chat.v1.ChatServiceGrpc;

class ChatServiceImplTest {

    @Test
    void bidiStreamExchangesMultipleMessages() throws Exception {
        String name = InProcessServerBuilder.generateName();
        Server server = InProcessServerBuilder.forName(name)
            .directExecutor()
            .addService(new ChatServiceImpl())
            .build()
            .start();
        ManagedChannel channel = InProcessChannelBuilder
            .forName(name)
            .directExecutor()
            .build();

        try {
            List<ChatEvent> replies = new CopyOnWriteArrayList<>();
            AtomicReference<Throwable> failure =
                new AtomicReference<>();
            CountDownLatch done = new CountDownLatch(1);

            var stub = ChatServiceGrpc.newStub(channel)
                .withDeadlineAfter(3, TimeUnit.SECONDS);
            StreamObserver<ChatMessage> requests = stub.chat(
                new StreamObserver<ChatEvent>() {
                    @Override
                    public void onNext(ChatEvent event) {
                        replies.add(event);
                    }

                    @Override
                    public void onError(Throwable error) {
                        failure.set(error);
                        done.countDown();
                    }

                    @Override
                    public void onCompleted() {
                        done.countDown();
                    }
                });

            requests.onNext(ChatMessage.newBuilder()
                .setRoomId("general")
                .setSender("an")
                .setText("One")
                .setClientSequence(1)
                .build());
            requests.onNext(ChatMessage.newBuilder()
                .setRoomId("general")
                .setSender("an")
                .setText("Two")
                .setClientSequence(2)
                .build());
            requests.onCompleted();

            assertTrue(done.await(4, TimeUnit.SECONDS));
            assertNull(failure.get());
            assertEquals(2, replies.size());
            assertEquals(1L, replies.get(0).getClientSequence());
            assertEquals("Received: Two", replies.get(1).getText());
        } finally {
            channel.shutdownNow();
            server.shutdownNow();
        }
    }
}
~~~

The test requires JUnit and **gRPC in-process** compatible with the project's gRPC Java version. It tests the bidirectional contract at the gRPC level, but does not verify Spring bean registration. To verify Spring gRPC integration, add an integration test that starts the Spring context and real server under test configuration, verifying interceptors and channels if present.

Additional scenarios to test:

1. Empty stream: client half-closes immediately, server completes normally per example rules.
2. Invalid message, such as blank **room_id** or **client_sequence <= 0**: RPC terminates with **INVALID_ARGUMENT**.
3. Two concurrent sessions: state/responses do not mix.
4. Client cancels or deadline expires mid-session: server cleans up resources and does not send success responses after the RPC is cancelled.
5. Many requests while the receiver is slow: queues and flow control operate within limits.
6. TLS, authorization, and reconnection: verify session ID, deduplication, and checkpoints.

## 10. Common Design Mistakes

| Mistake | Consequence | Fix |
| --- | --- | --- |
| Placing **stream** on only one side | Becomes client/server streaming, not bidirectional | Place **stream** on both request and response |
| Waiting for client completion before responding in all cases | Loses real-time exchange, can cause mutual waiting | Emit responses per business rules when data is ready |
| Always assuming one response per request | Confusion when server emits independent events | Define correlation IDs and event types |
| Using singleton state variables per session | Data from multiple RPCs gets mixed | Create state inside each RPC's own observer |
| Calling **onNext** from multiple uncoordinated threads | Race conditions, out-of-order messages, callback errors | Serialize writes to the observer |
| Lacking buffer or lifetime limits | Stream consumes resources indefinitely | Flow control, quotas, deadlines |
| Closing channel immediately after sending | Misses unreceived responses | Wait for completion callbacks, manage channel lifecycle |
| Retrying the whole stream on network loss | Can reprocess duplicate messages | Session ID, sequence, idempotency |
| Using plaintext or trusting the **sender** field | Data exposure, identity spoofing | TLS/mTLS, authentication and authorization |

## 11. Summary and Self-Check

Core syntax to **define a bidirectional streaming RPC**:

~~~proto
service ExampleService {
  rpc Exchange(stream Request) returns (stream Response);
}
~~~

On the **server**, the method receives an observer for sending responses and returns an observer for receiving requests; on the **client**, the async stub receives a response observer and returns a request observer. Both directions can send data concurrently, each direction has its own ordering, and both share the metadata/deadline/status of a single RPC. Lifecycle, cancellation, resource limits, and session recovery must be handled at the application layer.

Self-check questions:

1. Why must the **stream** keyword be on both sides of **rpc Chat(...)**?
2. Once the client calls **requests.onCompleted()**, can it still receive **ChatEvent** messages?
3. Can the server send three events for one request in bidirectional streaming? Why?
4. Why is one acknowledgment event insufficient to conclude a request was durably persisted?
5. When a connection drops mid-session, what additional information is needed to replay without duplicate processing?

Understanding the Protobuf contract, both **StreamObserver**s, termination semantics, and independent data flows provides the foundation for building safe, testable, and observable bidirectional streaming RPC services in Spring gRPC.
