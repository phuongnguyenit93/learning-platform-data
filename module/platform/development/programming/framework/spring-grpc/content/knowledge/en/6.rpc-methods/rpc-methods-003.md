# Defining Client Streaming RPCs in Spring gRPC

A **client streaming RPC** is a gRPC method that lets the client send **a stream of multiple messages** to the server within **a single RPC**, after which the server sends **one response message on success**. It is one of the four RPC types supported by Protocol Buffers. In the **Spring gRPC** ecosystem, the contract is declared in a **.proto** file, Java client/server code is generated automatically, and Spring manages the service implementation components.

This lesson explains how to define a client streaming RPC, implement the gRPC Java server in Spring, send a stream from a Java client, and handle practical concerns: stream termination, error statuses, deadlines, metadata, authentication, TLS, testing, and reliability monitoring.

## 1. How Does a Client Streaming RPC Work?

With client streaming, the client opens **one RPC call**, sends request messages sequentially, signals that it has finished sending (*half-close*), and then receives one response message from the server. The server typically processes or aggregates incoming messages before producing the final result.

~~~mermaid
sequenceDiagram
    participant C as gRPC client
    participant S as Spring gRPC server
    C->>S: UploadReadings() - open RPC
    loop 0..N request messages
        C->>S: Reading
        S->>S: Validate and accumulate
    end
    C->>S: onCompleted() - stop sending
    S->>S: Finalize aggregation
    S-->>C: UploadSummary (one response)
    S-->>C: status OK - finish
~~~

Key point: **0..N messages** on the client side refers only to the number of messages within **a single RPC**, not N independent calls. Whether an empty stream is valid depends on business rules. The server can also terminate early with an **error status** without waiting for the client to finish sending all messages.

| RPC Type | Client Sends | Server Returns | Definition in .proto |
| --- | --- | --- | --- |
| Unary | One message | One message | **rpc Get(Request) returns (Response);** |
| Server streaming | One message | A stream of messages | **rpc List(Request) returns (stream Response);** |
| **Client streaming** | **A stream of messages** | **One message** | **rpc Upload(stream Request) returns (Response);** |
| Bidirectional streaming | A stream of messages | A stream of messages | **rpc Chat(stream Request) returns (stream Response);** |

Suitable use cases include: sending batches of IoT telemetry records, aggregating metrics from agents, uploading chunked data, or sending events for the server to return a final validation result. If the application needs an individual acknowledgment response for **each message**, pure client streaming does not cover that; consider bidirectional streaming or multiple unary RPCs.

## 2. Defining the Protobuf Contract

Example: a device sends multiple measurement values in the same RPC, and the server responds with the total count of accepted samples and the sum of their values.

Create the file **src/main/proto/telemetry.proto**:

~~~proto
syntax = "proto3";

package demo.telemetry.v1;

option java_package = "vn.demo.grpc.telemetry.v1";
option java_multiple_files = true;
option java_outer_classname = "TelemetryProto";

service Telemetry {
  rpc UploadReadings(stream Reading) returns (UploadSummary);
}

message Reading {
  string device_id = 1;
  int64 sequence = 2;
  double value = 3;
}

message UploadSummary {
  int64 accepted_count = 1;
  double total = 2;
}
~~~

Breakdown of the method definition line:

~~~proto
rpc UploadReadings(stream Reading) returns (UploadSummary);
~~~

- **UploadReadings** is the RPC name.
- The **stream** keyword precedes **Reading**: the client can send multiple **Reading** messages in order within the same RPC.
- **UploadSummary** has no **stream**: the server returns **exactly one response message when the RPC succeeds**.
- The RPC's full identifier is **/demo.telemetry.v1.Telemetry/UploadReadings**.
- **java_package** is the Java package of the generated classes; it is independent of the Protobuf **package** namespace.

In messages, the numbers **1**, **2**, **3** are field numbers used in the Protobuf binary representation. Once a contract is in use, do not arbitrarily change the meaning of or reuse old field numbers; when removing fields, use **reserved**. In proto3, standard scalar fields have default values (such as empty string, 0) if omitted; explicitly enforce any business-required fields at the application layer.

When the build is configured with **protoc** and the **gRPC Java** code-generation plugin, key generated classes typically include:

- **Reading** and **UploadSummary**: Protobuf types for constructing and reading messages.
- **TelemetryGrpc.TelemetryImplBase**: base class for the server.
- **TelemetryGrpc.TelemetryStub**: asynchronous stub; supports client streaming via **StreamObserver**.

The **blocking stub** is generated primarily for unary and server streaming; to **send a client stream** in the standard gRPC Java API, use the **async stub**. Do not manually edit Java files generated by protoc.

## 3. Implementing the Server with gRPC Java and Spring

With client streaming, the server method **does not take a single request message** like unary. Instead, it **receives an observer for sending the response and returns an observer for receiving messages from the client**.

General signature:

~~~java
public StreamObserver<Reading> uploadReadings(
    StreamObserver<UploadSummary> responseObserver)
~~~

Assuming the Spring gRPC project is configured for Protobuf code generation and automatic registration of Spring beans implementing **BindableService**, you can write:

~~~java
package vn.demo.app;

import io.grpc.Status;
import io.grpc.stub.StreamObserver;
import org.springframework.stereotype.Service;
import vn.demo.grpc.telemetry.v1.Reading;
import vn.demo.grpc.telemetry.v1.TelemetryGrpc;
import vn.demo.grpc.telemetry.v1.UploadSummary;

@Service
public class TelemetryService extends TelemetryGrpc.TelemetryImplBase {

    private static final long MAX_READINGS = 10_000;

    @Override
    public StreamObserver<Reading> uploadReadings(
            StreamObserver<UploadSummary> responseObserver) {

        // Each RPC call creates a dedicated observer and aggregation state.
        return new StreamObserver<>() {
            private long acceptedCount;
            private double total;
            private boolean terminated;

            @Override
            public void onNext(Reading reading) {
                if (terminated) {
                    return;
                }

                if (reading.getDeviceId().isBlank()
                        || !Double.isFinite(reading.getValue())) {
                    fail(Status.INVALID_ARGUMENT
                        .withDescription("invalid reading"));
                    return;
                }

                if (acceptedCount >= MAX_READINGS) {
                    fail(Status.RESOURCE_EXHAUSTED
                        .withDescription("too many readings"));
                    return;
                }

                acceptedCount++;
                total += reading.getValue();
            }

            @Override
            public void onError(Throwable error) {
                // Client cancelled the RPC or transport encountered an error:
                // discard in-progress aggregation state, do not send a success response.
                terminated = true;
            }

            @Override
            public void onCompleted() {
                if (terminated) {
                    return;
                }

                terminated = true;
                UploadSummary summary = UploadSummary.newBuilder()
                    .setAcceptedCount(acceptedCount)
                    .setTotal(total)
                    .build();

                responseObserver.onNext(summary);
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

The example above accepts **0..10,000** valid messages; if the client sends an empty stream and completes, the server returns a summary with **accepted_count = 0**, **total = 0**. This is a **business rule chosen for the example**, not a mandatory requirement of client streaming. If business rules require at least one message, check **acceptedCount == 0** in **onCompleted()** and terminate with **INVALID_ARGUMENT**.

### Lifecycle of the Request Observer on the Server

| Request Observer Callback | When Is It Called? | Responsibility |
| --- | --- | --- |
| **onNext(Reading)** | Whenever another message arrives | Validate, accumulate, or process data |
| **onCompleted()** | Client has half-closed successfully | Finalize aggregation, send **one** summary, and complete response |
| **onError(Throwable)** | Request stream ended abnormally | Clean up resources, do not treat incomplete data as success |

To respond successfully, the server calls **responseObserver.onNext(summary)** once and then **responseObserver.onCompleted()**. When processing cannot continue, call **responseObserver.onError(statusException)**. Once the response observer has terminated, never call **onNext**, **onCompleted**, or **onError** on that observer again.

The state fields **acceptedCount**, **total**, and **terminated** are placed **inside each RPC's observer** so concurrent calls do not share state. If you implement asynchronous processing or hand off data to multiple threads, ensure state access and observer calls are properly synchronized/serialized. gRPC Java does not guarantee thread-safety for calls to a **StreamObserver** from multiple threads.

Stream completion **does not automatically create a database transaction**. If each **onNext** immediately persists data to a DB, a mid-stream error can leave partial data behind. If all-or-nothing semantics are required, the server must implement transactions, buffering, staging, or controlled commits.

## 4. Java Client Sending Multiple Messages via Asynchronous Stub

In gRPC Java, the client calls **uploadReadings(responseObserver)** on the **async stub** to obtain a **requestObserver**. The client then sends each **Reading** sequentially via **onNext** and calls **onCompleted** exactly once to signal that sending is complete.

Simple Java program example, assuming the server is running at **localhost:9090**:

~~~java
package vn.demo.app;

import io.grpc.ManagedChannel;
import io.grpc.ManagedChannelBuilder;
import io.grpc.stub.StreamObserver;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicReference;
import vn.demo.grpc.telemetry.v1.Reading;
import vn.demo.grpc.telemetry.v1.TelemetryGrpc;
import vn.demo.grpc.telemetry.v1.UploadSummary;

public class TelemetryClientDemo {

    public static void main(String[] args) throws InterruptedException {
        // Plaintext is only suitable for local/dev examples.
        ManagedChannel channel = ManagedChannelBuilder
            .forAddress("localhost", 9090)
            .usePlaintext()
            .build();

        try {
            var stub = TelemetryGrpc.newStub(channel)
                .withDeadlineAfter(5, TimeUnit.SECONDS);

            CountDownLatch finished = new CountDownLatch(1);
            AtomicReference<UploadSummary> response =
                new AtomicReference<>();
            AtomicReference<Throwable> failure =
                new AtomicReference<>();

            StreamObserver<Reading> requests = stub.uploadReadings(
                new StreamObserver<UploadSummary>() {
                    @Override
                    public void onNext(UploadSummary summary) {
                        response.set(summary);
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

            requests.onNext(Reading.newBuilder()
                .setDeviceId("sensor-01")
                .setSequence(1)
                .setValue(2.5)
                .build());

            requests.onNext(Reading.newBuilder()
                .setDeviceId("sensor-01")
                .setSequence(2)
                .setValue(3.0)
                .build());

            // Client has sent all Readings in this RPC.
            requests.onCompleted();

            if (!finished.await(6, TimeUnit.SECONDS)) {
                throw new IllegalStateException("RPC callback timeout");
            }
            if (failure.get() != null) {
                throw new IllegalStateException(
                    "UploadReadings failed", failure.get());
            }

            UploadSummary summary = response.get();
            if (summary == null) {
                throw new IllegalStateException("Missing response");
            }

            System.out.println(
                "Accepted: " + summary.getAcceptedCount()
                    + ", total: " + summary.getTotal());
            // Accepted: 2, total: 5.5
        } finally {
            channel.shutdownNow();
        }
    }
}
~~~

In a Spring application, the channel or stub is typically configured as a Spring-managed bean, and the server address should be loaded from configuration. Across different Spring gRPC starters/versions, channel bean declarations and service registration may vary; the **Protobuf definition** and **StreamObserver protocol** remain unchanged.

Behavioral notes:

1. **stub.uploadReadings(...)** opens a client streaming RPC and returns an observer for writing requests; it is not a synchronous call that immediately returns **UploadSummary**.
2. **requests.onNext(...)** sends another message into the stream. Calling this method does not guarantee the message has already been processed or durably stored by the server.
3. **requests.onCompleted()** is a *half-close* action on the client side. The client stops sending requests but still waits for the server's reply; do not shut down the channel before receiving the callback.
4. On the client's **response observer**, **onNext** is called at most once when the server responds successfully, followed by **onCompleted**. On failure, the client receives **onError**.
5. For tasks sending data concurrently from multiple threads, serialize **onNext/onCompleted/onError** calls on the same request observer. Never write to an observer after it has terminated.

The code snippet uses **CountDownLatch** to observe the result clearly in the demo program. Event-driven applications typically handle results via callbacks or their own async mechanisms rather than blocking threads. With client streaming, channels should be **reused** across RPCs and closed as part of the application lifecycle, rather than creating and closing a channel for every Reading.

## 5. Error Handling, Deadlines, and Stream Cancellation

Not every stream terminates normally. Notable scenarios:

| Event | Expected Behavior |
| --- | --- |
| An invalid Reading | Server terminates with **INVALID_ARGUMENT** |
| Reading count limit exceeded | Server terminates with **RESOURCE_EXHAUSTED** |
| Client signals sending complete | Server returns one summary and **OK** if processing succeeds |
| Client proactively cancels | RPC terminates; server should stop work and release resources |
| RPC deadline exceeded | Client typically receives **DEADLINE_EXCEEDED**; server may be notified of cancellation |
| Connection or service unavailable | May receive **UNAVAILABLE** or corresponding transport error |

The client sets a deadline using **withDeadlineAfter(5, TimeUnit.SECONDS)** in the example. The deadline applies to the **entire RPC**, including the time to send multiple messages, server processing time, and waiting for the response; it does not reset each time a new Reading is sent. When the deadline expires, the client may see an error even if the server has already processed part of the data.

In client error-handling code, you can extract the gRPC status:

~~~java
import io.grpc.Status;

@Override
public void onError(Throwable error) {
    Status.Code code = Status.fromThrowable(error).getCode();
    // Example: INVALID_ARGUMENT, DEADLINE_EXCEEDED, UNAVAILABLE.
    // Log or map to an appropriate application-layer error.
    finished.countDown();
}
~~~

The snippet above illustrates reading the status inside the callback; when applying this to the client from the previous section, remember to keep storing **failure** if downstream code needs to handle that error.

If the client decides to cancel before finishing sending, it can call **requests.onError(...)** once to terminate the client-side send stream; it can also cancel via the gRPC API appropriate to the call/stub type in use. Do not call **requests.onCompleted()** after cancelling.

**Retries** require particular care: if the connection drops mid-stream, the client does not automatically know which messages the server received and persisted. Replaying the entire stream can cause duplicate writes. To support reliable transfer, an additional design is needed: a shared **upload ID / idempotency key** for the RPC, message sequence numbers, duplicate record filtering, checking results before resending, or a dedicated acknowledgment/checkpoint API. gRPC client streaming does not automatically provide business-level exactly-once transactions.

## 6. Flow Control, Resource Limits, and Ordering

Client streaming is useful when there are many messages, but it should not be taken to mean an application can send an unbounded stream without regard for resources.

- gRPC runs over HTTP/2 with **flow control**; the async **onNext** API may write into a buffer instead of waiting for the message to actually be transmitted. For large streams, the client needs to control send rate and queue size.
- In gRPC Java, **ClientCallStreamObserver.isReady()** and **setOnReadyHandler(...)** are tools for emitting data according to the transport's receive capacity. Proper usage requires configuring callbacks at call start (typically via **ClientResponseObserver.beforeStart**). **isReady()** is not a confirmation that the server has processed or persisted a message.
- Within a single stream, gRPC preserves the **order of messages** sent sequentially. If multiple threads write to the observer, the application must establish ordering before sending.
- The server should limit **message count**, **size per message**, **processing time**, and **memory usage**. The example already limits the number of Readings; message size limits are typically configured at the server/channel or shared handler layer.
- For large datasets, process sequentially in batches or use staging instead of holding all messages in an unbounded **List**.

If each Reading represents a monetary amount, do not sum using **double** as in the measurement example: represent money in the smallest integer unit or an appropriate decimal type at the business layer.

## 7. Metadata, Interceptors, and TLS in Spring gRPC

**Metadata** is RPC-level information that can carry request IDs, tenant IDs, upload IDs, or authentication credentials. It is sent with the call, not as a new Reading for each message. Sensor data and measurement order belong in Protobuf messages; stream-wide metadata can go in metadata headers or a well-designed envelope message.

**Client interceptors** can automatically attach metadata and record send timing; **server interceptors** can check authentication, authorization, create trace spans, and measure RPC-level metrics. Simply counting successful RPCs is insufficient for client streaming: a single RPC can contain thousands of Readings, so also track received message counts and payload sizes.

For production deployments:

- Protect connections with **TLS**; use **mTLS** if mutual service authentication is required.
- Enforce authentication and authorization at appropriate boundaries, never trusting **device_id** simply because it appears in the payload.
- Do not log tokens, sensitive data, or full large stream payloads.
- Limit concurrent streams and total resources per client/tenant; combine with deadlines to prevent streams from remaining open unnecessarily long.

**usePlaintext()** in the client example is only for trusted development environments. Specific TLS, interceptor, and policy integrations depend on your Spring gRPC starter and deployment configuration.

## 8. Integration Testing Client Streaming at the gRPC Level

Instead of calling individual callbacks directly on the server and mocking success, you can use gRPC Java's **in-process server/channel**. This executes real calls through the stub, verifying that the server receives multiple messages and the client receives one response after ending the request stream.

~~~java
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertNull;
import static org.junit.jupiter.api.Assertions.assertTrue;

import io.grpc.ManagedChannel;
import io.grpc.Server;
import io.grpc.inprocess.InProcessChannelBuilder;
import io.grpc.inprocess.InProcessServerBuilder;
import io.grpc.stub.StreamObserver;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicInteger;
import java.util.concurrent.atomic.AtomicReference;
import org.junit.jupiter.api.Test;
import vn.demo.grpc.telemetry.v1.Reading;
import vn.demo.grpc.telemetry.v1.TelemetryGrpc;
import vn.demo.grpc.telemetry.v1.UploadSummary;

class TelemetryServiceTest {

    @Test
    void clientStreamProducesOneAggregatedResponse() throws Exception {
        String name = InProcessServerBuilder.generateName();
        Server server = InProcessServerBuilder.forName(name)
            .directExecutor()
            .addService(new TelemetryService())
            .build()
            .start();
        ManagedChannel channel = InProcessChannelBuilder.forName(name)
            .directExecutor()
            .build();

        try {
            CountDownLatch done = new CountDownLatch(1);
            AtomicReference<UploadSummary> summary =
                new AtomicReference<>();
            AtomicReference<Throwable> failure =
                new AtomicReference<>();
            AtomicInteger replyCount = new AtomicInteger();

            var stub = TelemetryGrpc.newStub(channel)
                .withDeadlineAfter(3, TimeUnit.SECONDS);
            StreamObserver<Reading> requests = stub.uploadReadings(
                new StreamObserver<UploadSummary>() {
                    @Override
                    public void onNext(UploadSummary response) {
                        replyCount.incrementAndGet();
                        summary.set(response);
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

            requests.onNext(Reading.newBuilder()
                .setDeviceId("d1").setSequence(1).setValue(2.5).build());
            requests.onNext(Reading.newBuilder()
                .setDeviceId("d1").setSequence(2).setValue(3.0).build());
            requests.onCompleted();

            assertTrue(done.await(4, TimeUnit.SECONDS));
            assertNull(failure.get());
            assertEquals(1, replyCount.get());
            assertNotNull(summary.get());
            assertEquals(2L, summary.get().getAcceptedCount());
            assertEquals(5.5, summary.get().getTotal(), 0.000001);
        } finally {
            channel.shutdownNow();
            server.shutdownNow();
        }
    }
}
~~~

This test requires **gRPC in-process** and JUnit matching the project's dependencies. To test the real Spring lifecycle, add an integration test that starts the Spring context and gRPC server, verifying that the service bean is registered, interceptors run properly, and the client receives the response.

Additional test cases to include:

1. Sending **0** Readings then completing: receives summary **0/0** per the example rule.
2. Sending a Reading with a blank **device_id** or invalid **value**: client receives **INVALID_ARGUMENT**, with no success summary.
3. Sending **10,001** Readings: receives **RESOURCE_EXHAUSTED**.
4. Cancelling mid-stream or setting a short deadline: server releases state; does not emit a success response for incomplete data.
5. Two client streams running concurrently: isolated aggregation results, no cross-stream state mixing.
6. For production environments: test TLS, authentication, retry/idempotency policies, memory limits, and behavior on connection drops.

Monitoring should collect **overall RPC latency**, **success/error rates by status**, **open stream count**, **messages/bytes per RPC**, processing latency, and **cancellation or deadline-exceeded counts**. A sudden spike in long-open streams may indicate clients forgetting to complete streams or server processing bottlenecks.

## 9. Common Mistakes and How to Avoid Them

| Mistake | Consequence | Fix |
| --- | --- | --- |
| Forgetting **requests.onCompleted()** | Server keeps waiting for the stream to end; client does not receive summary in time | Half-close once all messages are sent |
| Server calls **responseObserver.onNext** for each Reading | Violates client streaming's single-response contract | Aggregate data, return exactly one summary |
| Using blocking stub to send a client stream | Lacks the expected API for sending multiple request messages | Use async stub and request observer |
| Sharing counters across RPCs | Client data gets mixed together | Store state inside each call's own observer |
| Writing to observer from multiple uncoordinated threads | Can cause race conditions or out-of-order messages | Serialize send operations |
| Not setting deadlines or capacity limits | Stream can consume resources too long | Deadlines, quotas, flow control |
| Retrying from the start without deduplication | Data may be written multiple times | Upload ID, sequence, deduplication, checkpoints |
| Treating **onNext** as durable persistence confirmation | Assuming data is persisted when it was only sent/buffered | Confirm only via appropriate business protocol |

## 10. Summary and Self-Check

The **core syntax** for client streaming is:

~~~proto
rpc Upload(stream RequestMessage) returns (ResponseMessage);
~~~

On the client side, the **async stub** returns a **StreamObserver<RequestMessage>** to send multiple messages sequentially and finish with **onCompleted()**. On the server side, the implementation method returns a **StreamObserver<RequestMessage>** to receive messages, maintain per-RPC state, and return **one ResponseMessage** upon successful completion. On errors or cancellation, use **gRPC status** mechanisms and release resources appropriately.

Self-check with four questions:

1. Why must **stream** be placed before the **request** type and not before **response** when defining client streaming?
2. What happens if the client sends all 50 messages but never calls **onCompleted()**?
3. If the server persists 20 messages and then the connection drops, why can retrying the full 50-message stream cause duplicate data?
4. When should you choose client streaming, and when should you switch to bidirectional streaming for per-message responses?

Once you clearly understand the **Protobuf contract**, the **lifecycle of both observers**, and **completion/error semantics**, you can implement reliable client streaming RPCs in Spring gRPC and continue expanding into bidirectional streaming, security, and observability.
