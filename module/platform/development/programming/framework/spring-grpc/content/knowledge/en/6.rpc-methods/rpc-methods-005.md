# Requests and Responses of Each Method Type in Spring gRPC

An **RPC** (Remote Procedure Call) method defines how a client invokes functionality running on a server. With **Spring gRPC**, the communication contract is declared using **Protocol Buffers (.proto)**, and code generation tools produce the Java messages, service base classes, and client stubs. The four gRPC RPC types differ primarily in **the number of request messages** the client may send and **the number of response messages** the server may return within **a single RPC call**.

This lesson clarifies the request/response structure of **unary**, **server streaming**, **client streaming**, and **bidirectional streaming**, how they are expressed in Protobuf, how to use the gRPC Java APIs in Spring applications, and how to handle deadlines, metadata, statuses, security, testing, and deployment risks.

## 1. Distinguishing RPCs, Messages, and Streams

In an RPC, a **request message** is application data sent from the client to the server; a **response message** is application data sent from the server back to the client. Data is typically a binary-encoded Protobuf object.

**One RPC does not equal one network packet.** gRPC normally uses HTTP/2: a single message may be split across multiple frames, and multiple messages may travel inside the same HTTP/2 stream. Therefore, the request/response counts below refer to **the number of Protobuf messages at the gRPC level**, not the number of packets or frames.

| Method Type | Requests in One RPC | Responses on Success | Protobuf Syntax |
| --- | --- | --- | --- |
| **Unary** | Exactly 1 | Exactly 1 | **rpc Get(Req) returns (Res);** |
| **Server streaming** | Exactly 1 | 0 to many | **rpc Watch(Req) returns (stream Res);** |
| **Client streaming** | 0 to many | Exactly 1 | **rpc Upload(stream Req) returns (Res);** |
| **Bidirectional streaming** | 0 to many | 0 to many | **rpc Exchange(stream Req) returns (stream Res);** |

**Note on failures:** the response counts in the table describe **successful calls**. If an RPC terminates with an error status (other than **OK**), the client may receive no success responses at all, or in streaming it may have received a **partial** set of responses before the error occurred. When streaming requests, an empty stream can be protocol-valid; the business layer may require at least one message.

~~~mermaid
flowchart TD
    A["A gRPC call"] --> B{"Client sends one or many requests?"}
    B -->|"One"| C{"Server returns one or many responses?"}
    B -->|"Many"| D{"Server returns one or many responses?"}
    C -->|"One"| E["Unary"]
    C -->|"Many"| F["Server streaming"]
    D -->|"One"| G["Client streaming"]
    D -->|"Many"| H["Bidirectional streaming"]
~~~

## 2. Example Protobuf Contract with All Four Method Types

Suppose an application monitors devices. A client can view the latest measurement, watch updates, upload a batch of samples, or exchange bidirectional control signals. File **src/main/proto/telemetry.proto**:

~~~proto
syntax = "proto3";

package demo.telemetry.v1;

option java_package = "vn.demo.grpc.telemetry.v1";
option java_multiple_files = true;
option java_outer_classname = "TelemetryProto";

service TelemetryService {
  // One request -> one response.
  rpc GetLatest(ReadingQuery) returns (Reading);

  // One request -> response stream.
  rpc Watch(ReadingQuery) returns (stream Reading);

  // Request stream -> one response.
  rpc Upload(stream Reading) returns (UploadSummary);

  // Request stream <-> response stream.
  rpc Exchange(stream ClientSignal) returns (stream ServerSignal);
}

message ReadingQuery {
  string device_id = 1;
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

message ClientSignal {
  string device_id = 1;
  int64 client_sequence = 2;
  string payload = 3;
}

message ServerSignal {
  int64 client_sequence = 1;
  string payload = 2;
}
~~~

Whether the **stream** keyword is placed before the request type or the response type **determines which direction carries multiple messages**. A method without that keyword on either side is unary. Types such as **Reading** or **UploadSummary** only describe the **structure of a single message**; the message itself does not dictate how many times it appears in an RPC.

After configuring **protoc** and the gRPC Java plugin in the build, generated code typically contains:

- **ReadingQuery**, **Reading**, **UploadSummary**, **ClientSignal**, **ServerSignal**: the Protobuf classes.
- **TelemetryServiceGrpc.TelemetryServiceImplBase**: base class for implementing the service on the server.
- **TelemetryServiceGrpc.TelemetryServiceBlockingStub**: convenient for synchronous unary and server streaming calls.
- **TelemetryServiceGrpc.TelemetryServiceStub**: async stub using **StreamObserver**, supporting all four method types, especially client/bidirectional streaming.
- **TelemetryServiceGrpc.TelemetryServiceFutureStub**: supports unary calls returning a future result; not an API for sending request streams.

All examples in this lesson assume the Spring application already has the Spring gRPC dependency, Protobuf code generation configured, and the ability to register beans implementing **BindableService**. Configuration property names, channel creation, or service registration may vary by starter version; contract semantics and the gRPC Java APIs are the core concepts.

## 3. Unary: One Request and One Response

Declaration:

~~~proto
rpc GetLatest(ReadingQuery) returns (Reading);
~~~

In a **GetLatest** call, the client sends **exactly one ReadingQuery**; the server returns **exactly one Reading** on success. There are no request/response streams at the application API level.

~~~mermaid
sequenceDiagram
    participant C as Client
    participant S as Server
    C->>S: GetLatest(ReadingQuery)
    S-->>C: Reading
    S-->>C: status OK
~~~

Example using **blocking stub**:

~~~java
ReadingQuery query = ReadingQuery.newBuilder()
    .setDeviceId("sensor-01")
    .build();

Reading response = blockingStub.getLatest(query);
System.out.println(response.getValue());
~~~

The generated server method has the signature:

~~~java
public void getLatest(
    ReadingQuery request,
    StreamObserver<Reading> responseObserver);
~~~

The server executes exactly one **responseObserver.onNext(reading)** call, followed by **responseObserver.onCompleted()**. If it cannot return a result, the server uses **onError(Status...asRuntimeException())** instead of returning a dummy Reading with an error message inside a value field.

Unary suits single-record queries, price calculations, or short operations with a single final result. A unary response can still hold multiple items if the message has a **repeated** field; the number of elements inside one message **is different from** the number of response messages of the RPC.

## 4. Server Streaming: One Request and Many Responses

Declaration:

~~~proto
rpc Watch(ReadingQuery) returns (stream Reading);
~~~

The client sends **one ReadingQuery** to subscribe; the server emits **0 to N Readings** over time and then ends the stream. The server can send messages as soon as data appears without waiting for an entire list before responding.

~~~mermaid
sequenceDiagram
    participant C as Client
    participant S as Server
    C->>S: Watch(ReadingQuery)
    S-->>C: Reading(sequence=1)
    S-->>C: Reading(sequence=2)
    S-->>C: Reading(sequence=3)
    S-->>C: status OK after onCompleted
~~~

With a **blocking stub**, gRPC Java typically returns an **Iterator<Reading>**:

~~~java
ReadingQuery query = ReadingQuery.newBuilder()
    .setDeviceId("sensor-01")
    .build();

Iterator<Reading> stream = blockingStub.watch(query);
while (stream.hasNext()) {
    Reading reading = stream.next();
    System.out.println(reading.getSequence() + ": " +
        reading.getValue());
}
~~~

**hasNext()** and **next()** may block while waiting for data. If the server terminates with an error mid-stream, iterating can throw **StatusRuntimeException**; wrap error handling around the entire loop, not only when creating the iterator.

Server signature:

~~~java
public void watch(
    ReadingQuery request,
    StreamObserver<Reading> responseObserver);
~~~

The server can call **responseObserver.onNext(reading)** multiple times, finally calling **onCompleted()**, or calling **onError(...)** on failure. The client has no API to send subsequent requests in the same Watch call because the request direction is not declared **stream**. If filters must change continuously while receiving data, consider bidirectional streaming.

## 5. Client Streaming: Many Requests and One Response

Declaration:

~~~proto
rpc Upload(stream Reading) returns (UploadSummary);
~~~

The client sends **a sequence of Readings** in the same RPC; the server aggregates them and returns **one UploadSummary** upon successful processing.

~~~mermaid
sequenceDiagram
    participant C as Client
    participant S as Server
    C->>S: Open Upload
    C->>S: Reading 1
    C->>S: Reading 2
    C->>S: Reading 3
    C->>S: requestObserver.onCompleted()
    S-->>C: UploadSummary
    S-->>C: status OK
~~~

On the Java client side, the **async stub** accepts a response-handling observer and **returns a request observer**:

~~~java
StreamObserver<Reading> requests = asyncStub.upload(
    new StreamObserver<UploadSummary>() {
        @Override
        public void onNext(UploadSummary summary) {
            System.out.println(
                "Accepted: " + summary.getAcceptedCount());
        }

        @Override
        public void onError(Throwable error) {
            System.err.println(
                Status.fromThrowable(error).getCode());
        }

        @Override
        public void onCompleted() {
            System.out.println("Upload finished");
        }
    });

requests.onNext(Reading.newBuilder()
    .setDeviceId("sensor-01")
    .setSequence(1)
    .setValue(10.5)
    .build());
requests.onNext(Reading.newBuilder()
    .setDeviceId("sensor-01")
    .setSequence(2)
    .setValue(11.5)
    .build());
requests.onCompleted();
~~~

On the server, the method has the signature:

~~~java
public StreamObserver<Reading> upload(
    StreamObserver<UploadSummary> responseObserver);
~~~

The server **returns an observer** with **onNext(Reading)** to receive each request. When **onCompleted()** is invoked on the request-receiving observer, the server usually finalizes aggregation, sends one **UploadSummary**, and calls **responseObserver.onCompleted()**. On error, the server ends with **responseObserver.onError(...)**.

The client-side action **requests.onCompleted()** **half-closes** the send direction: the client sends no further messages while still **receiving** the response. In the example, the server waits for the client to half-close before aggregating; at the API level, the server can terminate with an error before receiving all requests.

**Note:** an empty request stream is valid at the gRPC level. If Upload requires at least one Reading, the server must actively check the count and return **INVALID_ARGUMENT** when zero messages arrive; Protobuf does not enforce that rule automatically.

## 6. Bidirectional Streaming: Many Requests and Many Responses

Declaration:

~~~proto
rpc Exchange(stream ClientSignal) returns (stream ServerSignal);
~~~

Both client and server can send **0 to N messages** within one RPC. The server can respond while the client is still sending; both directions are independent in cadence and message count.

~~~mermaid
sequenceDiagram
    participant C as Client
    participant S as Server
    C->>S: Open Exchange
    C->>S: ClientSignal 1
    S-->>C: ServerSignal A
    S-->>C: ServerSignal B
    C->>S: ClientSignal 2
    C->>S: ClientSignal 3
    S-->>C: ServerSignal C
    C->>S: requestObserver.onCompleted()
    S-->>C: ServerSignal D
    S-->>C: status OK
~~~

Like client streaming, the **async stub** returns a request observer and accepts a response observer:

~~~java
StreamObserver<ClientSignal> requests = asyncStub.exchange(
    new StreamObserver<ServerSignal>() {
        @Override
        public void onNext(ServerSignal response) {
            System.out.println(
                response.getClientSequence() + ": " +
                response.getPayload());
        }

        @Override
        public void onError(Throwable error) {
            System.err.println(
                Status.fromThrowable(error).getCode());
        }

        @Override
        public void onCompleted() {
            System.out.println("Exchange finished");
        }
    });

requests.onNext(ClientSignal.newBuilder()
    .setDeviceId("sensor-01")
    .setClientSequence(1)
    .setPayload("request-calibration")
    .build());

// Can continue receiving responses before ending the send direction.
requests.onCompleted();
~~~

On the server side, the method has the signature:

~~~java
public StreamObserver<ClientSignal> exchange(
    StreamObserver<ServerSignal> responseObserver);
~~~

Inside the request observer's **onNext(ClientSignal)**, the server can emit **0, 1, or many ServerSignals** via **responseObserver.onNext(...)**. Once the client half-closes, the server can finish sending remaining data and call **onCompleted()**, or end with **onError(...)** if an error occurs.

**Do not assume the Nth response corresponds to the Nth request.** If business logic requires pairing, design a **correlation ID** or **client_sequence**. Each direction preserves its own ordering, but there is no global ordering across both directions. When confirmation is needed that the server has durably persisted data, define the exact meaning of an acknowledgment response; calling or receiving **onNext** does not automatically mean durable persistence.

## 7. Summary of Java Signatures and Callbacks for Each Type

On the server side, gRPC Java generates methods in two patterns:

- **Unary and server streaming:** accepts **one request object** plus a **response StreamObserver**, returns **void**.
- **Client and bidirectional streaming:** accepts a **response StreamObserver**, returns a **request StreamObserver** to receive multiple requests.

Example of the four signatures in **TelemetryServiceGrpc.TelemetryServiceImplBase**:

~~~java
// Unary: 1 request -> 1 response.
public void getLatest(
    ReadingQuery request,
    StreamObserver<Reading> responseObserver);

// Server streaming: 1 request -> many responses.
public void watch(
    ReadingQuery request,
    StreamObserver<Reading> responseObserver);

// Client streaming: many requests -> 1 response.
public StreamObserver<Reading> upload(
    StreamObserver<UploadSummary> responseObserver);

// Bidirectional streaming: many requests -> many responses.
public StreamObserver<ClientSignal> exchange(
    StreamObserver<ServerSignal> responseObserver);
~~~

The **response StreamObserver** pattern appears in all four RPC types, but its usage differs:

| Method | Server calls **response.onNext(...)** | Server calls **response.onCompleted()** |
| --- | --- | --- |
| Unary | Exactly once on success | After the single response |
| Server streaming | 0 to many times | When no more responses remain |
| Client streaming | Exactly once on success | After the single summary |
| Bidirectional streaming | 0 to many times | When ending the response direction |

On the client side, remember stub usage as follows:

| Method | Blocking stub | Async stub |
| --- | --- | --- |
| **GetLatest** | Returns **Reading** directly | Takes **StreamObserver<Reading>** to receive one result |
| **Watch** | Returns **Iterator<Reading>** | Takes **StreamObserver<Reading>** to receive multiple results |
| **Upload** | No blocking API to stream multiple requests this way | Returns **StreamObserver<Reading>** for client to send requests |
| **Exchange** | No corresponding bidirectional blocking API in the standard blocking stub | Returns **StreamObserver<ClientSignal>** for client to send, and uses callbacks to receive |

The snippets above use **blockingStub** and **asyncStub** variables created from a channel, for example:

~~~java
ManagedChannel channel = ManagedChannelBuilder
    .forAddress("localhost", 9090)
    .usePlaintext()
    .build();

var blockingStub = TelemetryServiceGrpc.newBlockingStub(channel)
    .withDeadlineAfter(3, TimeUnit.SECONDS);
var asyncStub = TelemetryServiceGrpc.newStub(channel)
    .withDeadlineAfter(3, TimeUnit.SECONDS);

// Reuse channel across multiple RPCs.
// Shut down channel at the end of application lifecycle.
~~~

In real Spring applications, read the address from configuration and use the managed beans/channels/stubs appropriate to your Spring gRPC version. **usePlaintext()** is only appropriate for trusted local/dev environments; production systems need **TLS** and proper authentication configured.

## 8. A Server Service Demonstrating All Four Methods

The following simple example shows **the differences in how the server handles requests and emits responses**. Data is constructed inline to focus on RPC flow; in real projects, replace this with proper business services, authentication, and persistence:

~~~java
package vn.demo.app;

import io.grpc.Status;
import io.grpc.stub.StreamObserver;
import org.springframework.stereotype.Service;
import vn.demo.grpc.telemetry.v1.*;

@Service
public class TelemetryServiceImpl
        extends TelemetryServiceGrpc.TelemetryServiceImplBase {

    @Override
    public void getLatest(
            ReadingQuery query,
            StreamObserver<Reading> responses) {
        if (query.getDeviceId().isBlank()) {
            responses.onError(Status.INVALID_ARGUMENT
                .withDescription("device_id is required")
                .asRuntimeException());
            return;
        }

        responses.onNext(Reading.newBuilder()
            .setDeviceId(query.getDeviceId())
            .setSequence(3)
            .setValue(12.5)
            .build());
        responses.onCompleted();
    }

    @Override
    public void watch(
            ReadingQuery query,
            StreamObserver<Reading> responses) {
        if (query.getDeviceId().isBlank()) {
            responses.onError(Status.INVALID_ARGUMENT
                .withDescription("device_id is required")
                .asRuntimeException());
            return;
        }

        for (int seq = 1; seq <= 3; seq++) {
            responses.onNext(Reading.newBuilder()
                .setDeviceId(query.getDeviceId())
                .setSequence(seq)
                .setValue(seq * 1.5)
                .build());
        }
        responses.onCompleted();
    }

    @Override
    public StreamObserver<Reading> upload(
            StreamObserver<UploadSummary> responses) {
        return new StreamObserver<>() {
            private long count;
            private double total;
            private boolean ended;

            @Override
            public void onNext(Reading reading) {
                if (ended) return;
                if (reading.getDeviceId().isBlank()
                        || !Double.isFinite(reading.getValue())) {
                    ended = true;
                    responses.onError(Status.INVALID_ARGUMENT
                        .withDescription("invalid reading")
                        .asRuntimeException());
                    return;
                }
                count++;
                total += reading.getValue();
            }

            @Override
            public void onError(Throwable error) {
                ended = true; // Discard incomplete aggregation data.
            }

            @Override
            public void onCompleted() {
                if (ended) return;
                ended = true;
                responses.onNext(UploadSummary.newBuilder()
                    .setAcceptedCount(count)
                    .setTotal(total)
                    .build());
                responses.onCompleted();
            }
        };
    }

    @Override
    public StreamObserver<ClientSignal> exchange(
            StreamObserver<ServerSignal> responses) {
        return new StreamObserver<>() {
            private boolean ended;

            @Override
            public void onNext(ClientSignal signal) {
                if (ended) return;
                if (signal.getDeviceId().isBlank()) {
                    ended = true;
                    responses.onError(Status.INVALID_ARGUMENT
                        .withDescription("device_id is required")
                        .asRuntimeException());
                    return;
                }
                // Example returning one response per signal.
                responses.onNext(ServerSignal.newBuilder()
                    .setClientSequence(signal.getClientSequence())
                    .setPayload("received: " + signal.getPayload())
                    .build());
            }

            @Override
            public void onError(Throwable error) {
                ended = true;
            }

            @Override
            public void onCompleted() {
                if (ended) return;
                ended = true;
                responses.onCompleted();
            }
        };
    }
}
~~~

Each **Upload** or **Exchange** call creates **its own request observer and state**. Do not store per-stream counters in mutable fields on the singleton service, because concurrent RPCs would mix data.

Here **Watch** sends three results and finishes; if data arrives continuously, the server must push on events and handle cancellation/flow control. Do not run an infinite loop continuously calling **onNext**. The illustrative code performs no database or external I/O and therefore does not address full production concurrency, transaction, and shutdown concerns.

## 9. Normal Completion, Errors, and Deadlines

### When Does an RPC Truly Complete?

- For **unary**, the server sends one response and terminates with **onCompleted()**.
- For **server streaming**, the server sends 0 to many responses and then calls **onCompleted()**.
- For **client streaming**, the client must call **requestObserver.onCompleted()** to half-close once all requests are sent; the server can then return one aggregated result and complete.
- For **bidirectional streaming**, the client can half-close the request direction while still receiving responses until the server terminates the response direction. The server can also terminate early according to the business protocol.

**onCompleted()** on a send/receive observer is a **message stream**-level event; gRPC status **OK** is sent when the server completes the call successfully. On error, the terminating side uses **onError(...)**, and the other side receives **StatusRuntimeException** or the **onError(Throwable)** callback. After the terminal callback, no more messages may be emitted to that observer.

### Common Error Statuses

| Status | Example Usage | Handling Approach |
| --- | --- | --- |
| **INVALID_ARGUMENT** | Query missing device ID; Reading invalid value | Fix input, do not retry verbatim |
| **NOT_FOUND** | Unary GetLatest did not find device | Handle non-existence |
| **UNAUTHENTICATED** | Missing credentials | Re-authenticate |
| **PERMISSION_DENIED** | Lacks permission to read/send device data | Check authorization |
| **RESOURCE_EXHAUSTED** | Stream exceeded quota/buffer | Throttle load, check limits |
| **DEADLINE_EXCEEDED** | RPC did not finish before deadline | Check task state and time budget |
| **CANCELLED** | Call was cancelled | Release resources |
| **UNAVAILABLE** | Cannot connect or service temporarily down | Controlled retry if safe |
| **INTERNAL** | Server internal error | Log/trace safely for investigation |

**Deadlines** apply to the **entire RPC**, not individual messages. If client streaming takes 5 seconds to send 100 Readings, waiting for the response also falls within that same deadline. If server streaming stays open long, the deadline may expire before the server finishes sending all data. The client can use:

~~~java
var timedStub = TelemetryServiceGrpc.newStub(channel)
    .withDeadlineAfter(5, TimeUnit.SECONDS);
~~~

When the client receives **DEADLINE_EXCEEDED** or loses connection, **it cannot assume the server has processed zero messages**. Especially for write RPCs, retries can duplicate side effects. Add an **idempotency key / upload ID**, message IDs, and deduplication mechanisms when recovery is required.

## 10. Metadata, Ordering, Flow Control, and Security

### Metadata Belongs to an RPC, Not a Message

**Metadata** usually carries authorization tokens, request IDs, tenant IDs, or trace context. It is call-level information sent via gRPC headers/trailers and does not automatically change per message in a stream. Business data that varies per message belongs in Protobuf fields.

Client/server **interceptors** can add/read metadata, authenticate, create traces, and record per-method status/latency stats. With streaming, track both **message/byte counts** and **open stream counts** because a single RPC can transmit thousands of messages.

### Request/Response Ordering and Correlation

gRPC preserves message ordering **within the same stream direction**. However:

- **Unary:** just one request and one response, easily correlated via the call itself.
- **Server streaming:** multiple responses all belong to the single request that opened the stream, though they may carry many records/timestamps.
- **Client streaming:** multiple requests contribute to one aggregated response; there is no independent acknowledgment per request unless explicitly designed by business logic.
- **Bidirectional:** both directions have independent ordering; one request can trigger 0, 1, or many responses. Use a **correlation ID/sequence** when pairing is needed.

Do not treat returning from **onNext()** as confirmation that data was durably persisted. If transactional guarantees, deduplication, or per-message acknowledgments are required, design them at the application layer.

### Flow Control and Resource Limits

HTTP/2 and gRPC have **flow control**, yet applications still need limits on message count, message size, buffer memory, and concurrent streams. In gRPC Java, **ClientCallStreamObserver** and **ServerCallStreamObserver** expose **isReady()** and **setOnReadyHandler(...)**; the **ClientResponseObserver.beforeStart(...)** callback supports configuring readiness-based sending for async client streaming.

**StreamObserver is not thread-safe by default**: if multiple threads emit messages into one observer, serialize **onNext/onCompleted/onError** calls. When handling asynchronously, avoid long-blocking callbacks and never maintain unbounded queues. **isReady()** only indicates transport write readiness, not confirmation that the server has processed business logic.

### TLS and Authorization

In production, **TLS** is required on the transport channel; consider **mTLS** between services. Authentication/authorization must be checked at trust boundaries, rather than relying on a client-supplied **device_id** string. Do not log tokens, sensitive data, or entire stream payloads.

## 11. Testing Request/Response Semantics per Method Type

Rather than merely calling Java methods directly, use a gRPC **in-process server/channel** or an integration test running the Spring context to verify request/response shapes through the generated stubs. Minimum test matrix:

| Method | Success Test | Key Error Tests |
| --- | --- | --- |
| **GetLatest** | One query returns exactly one Reading | blank device ID → INVALID_ARGUMENT |
| **Watch** | One query receives exactly 3 Readings and finishes | invalid query → INVALID_ARGUMENT; mid-stream error |
| **Upload** | Two Readings produce summary count=2, exact total | invalid Reading → INVALID_ARGUMENT; empty stream per policy |
| **Exchange** | Two ClientSignals receive multiple ServerSignals, receive works before half-close | invalid signal; client cancellation or deadline expiration |

A simple bidirectional test using gRPC in-process:

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
import vn.demo.grpc.telemetry.v1.*;

class TelemetryRpcContractTest {

    @Test
    void exchangeAcceptsMultipleRequestsAndResponses()
            throws Exception {
        String name = InProcessServerBuilder.generateName();
        Server server = InProcessServerBuilder.forName(name)
            .directExecutor()
            .addService(new TelemetryServiceImpl())
            .build()
            .start();
        ManagedChannel channel = InProcessChannelBuilder
            .forName(name)
            .directExecutor()
            .build();
        try {
            List<ServerSignal> responses =
                new CopyOnWriteArrayList<>();
            AtomicReference<Throwable> failure =
                new AtomicReference<>();
            CountDownLatch finished = new CountDownLatch(1);

            var stub = TelemetryServiceGrpc.newStub(channel)
                .withDeadlineAfter(3, TimeUnit.SECONDS);
            StreamObserver<ClientSignal> requests = stub.exchange(
                new StreamObserver<ServerSignal>() {
                    @Override
                    public void onNext(ServerSignal response) {
                        responses.add(response);
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
                });

            requests.onNext(ClientSignal.newBuilder()
                .setDeviceId("sensor-01")
                .setClientSequence(1)
                .setPayload("ping")
                .build());
            requests.onNext(ClientSignal.newBuilder()
                .setDeviceId("sensor-01")
                .setClientSequence(2)
                .setPayload("status")
                .build());
            requests.onCompleted();

            assertTrue(finished.await(4, TimeUnit.SECONDS));
            assertNull(failure.get());
            assertEquals(2, responses.size());
            assertEquals(1L, responses.get(0).getClientSequence());
            assertEquals("received: status",
                responses.get(1).getPayload());
        } finally {
            channel.shutdownNow();
            server.shutdownNow();
        }
    }
}
~~~

The test requires JUnit and the corresponding **gRPC in-process** dependency. It verifies message flow through gRPC Java, but does not prove Spring automatically registers the bean or that TLS/interceptors are configured properly. To test true Spring gRPC integration, add an integration test starting the Spring context and server under test configuration.

When performance testing is needed, monitor **per-method latency**, **OK/error status rates**, p95/p99, messages/bytes per direction, stream lifetimes, open streams, cancellations, and deadlines. Notably, a streaming method may have few RPCs yet huge message volumes, so counting only RPCs misses the actual load.

## 12. Choosing a Method Type and Mistakes to Avoid

| Need | Choose Method | Why |
| --- | --- | --- |
| Fetch latest measurement by ID | **Unary** | One query, one result |
| Watch continuously updated measurements | **Server streaming** | One subscription request, multiple responses |
| Send a batch of measurement samples and receive accepted count | **Client streaming** | Many requests, one aggregated response |
| Device sends signals while simultaneously receiving commands | **Bidirectional streaming** | Both sides need to emit data continuously |

Common pitfalls:

1. **Confusing fields inside a message with RPC message count.** A unary response can contain a **repeated** field, yet remain a single response message.
2. **Forgetting the stream keyword.** Omitting **stream** on one side changes the RPC type and the generated Java signature.
3. **Choosing streaming for every operation.** Streaming brings extra responsibility for lifecycle management, flow control, and timeouts; unary is usually easier to test for short operations.
4. **Calling onCompleted too early or never calling it.** Client streaming may wait indefinitely if the client never half-closes; closing too early loses unsent data.
5. **Assuming each streaming request has a matching response.** With bidirectional streaming, explicit correlation rules are needed; with client streaming, results usually aggregate the entire stream.
6. **Failing to handle mid-stream errors.** Streaming can return partial data and then fail; clients must distinguish received items from the final RPC status.
7. **Uncontrolled retries.** A failed RPC may have already caused side effects; design deduplication and business-level recovery mechanisms.
8. **Not setting buffer and stream-length limits.** A long stream can exhaust server/client resources.

## 13. Summary and Self-Check

The rule for reading Protobuf contracts is concise:

~~~proto
rpc Unary(Request) returns (Response);
rpc ServerStream(Request) returns (stream Response);
rpc ClientStream(stream Request) returns (Response);
rpc BidiStream(stream Request) returns (stream Response);
~~~

Look at **where the stream keyword appears** to tell which side can send multiple messages. All transmitted payloads are **Protobuf messages**; server/client in gRPC Java interact through stubs, **StreamObserver**, and terminal callbacks. For every RPC, properly handle status, deadlines, cancellation, security, and resource limits.

Answer the following questions:

1. If a unary response contains a **repeated Reading** field with 100 items, is that one response or 100 response messages?
2. Why does server streaming not allow the client to send additional filters after opening the RPC, unless a separate call is designed?
3. In client streaming, why must the client call **requests.onCompleted()** after finishing sending Readings?
4. With bidirectional streaming, what guarantees that a response corresponds to a specific request? If absent, what should be added to the schema?
5. If a client receives several responses and then encounters **UNAVAILABLE**, should the RPC be considered successfully completed? Before retrying, what must be checked?

Accurately distinguishing the **cardinality and direction of requests/responses in each method** is foundational for designing sound Protocol Buffers contracts, implementing Spring gRPC clients/servers effectively, and operating stable services.
