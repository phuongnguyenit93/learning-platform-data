# One Request One Response Does Not Mean No Stream

In gRPC, a **unary RPC** means a single call accepts **one request message** and returns **one response message on success**. That does not mean the call uses no stream. When running over HTTP/2, **every RPC, including unary, is transported over its own HTTP/2 stream**.

Confusion often arises because the word *stream* is used at two different layers:

- **HTTP/2 stream** is a bidirectional channel at the transport layer. gRPC uses it to carry headers, data frames, and trailers for a single RPC.
- **Streaming in a Protobuf contract** describes how many messages one side is allowed to send within a single RPC. The **stream** keyword in a **.proto** file determines this cardinality.

Therefore, unary has no **stream** keyword in the Protobuf method declaration, yet still has an HTTP/2 stream underneath. This is an important distinction when reading contracts, designing APIs, inspecting network traffic, and diagnosing errors in **Spring gRPC**.

## 1. Distinguishing Three Concepts

| Concept | Layer | Question It Answers |
| --- | --- | --- |
| **RPC method** | gRPC API | Which function on the server is the client calling? |
| **Protobuf message cardinality** | **.proto** contract / Application API | Does each side send one or many messages in a single RPC? |
| **HTTP/2 stream** | Transport | Over which logical channel are an RPC's frames carried? |

One HTTP/2 connection can carry many concurrent HTTP/2 streams. Each gRPC RPC uses one stream within that connection; multiple RPCs can run concurrently without opening a new TCP connection for each call. HTTP/2 numbers streams using a **stream ID** to distinguish them on the same connection.

**The stream keyword in .proto does not create an HTTP/2 stream.** An HTTP/2 stream already exists to transport every kind of RPC. This keyword only indicates whether the client or server may send multiple Protobuf messages within the same call.

## 2. Unary RPCs Still Run on an HTTP/2 Stream

Example unary declaration:

~~~proto
syntax = "proto3";

package demo.catalog.v1;

option java_package = "vn.demo.grpc.catalog.v1";
option java_multiple_files = true;

service CatalogService {
  rpc GetItem(GetItemRequest) returns (GetItemResponse);
}

message GetItemRequest {
  string item_id = 1;
}

message GetItemResponse {
  string item_id = 1;
  string name = 2;
  int64 available_quantity = 3;
}
~~~

In the **GetItem** method, there is no **stream** keyword on either the request or the response. That specifies:

- The client sends one **GetItemRequest**.
- The server returns one **GetItemResponse** when the call succeeds.
- The server terminates the RPC with a gRPC status, typically **OK** if processing succeeds.

Yet when sending the call, gRPC still creates an **HTTP/2 stream**. The exchange at the transport level can be pictured as follows:

~~~mermaid
sequenceDiagram
    participant C as gRPC client
    participant H as HTTP/2 connection
    participant S as gRPC server
    C->>H: HEADERS (POST /demo.catalog.v1.CatalogService/GetItem)
    H->>S: Open HTTP/2 stream for RPC
    C->>H: DATA (1 gRPC message containing GetItemRequest)
    Note over C,H: Client closes request send direction
    H->>S: Request message
    S-->>H: HEADERS (response)
    S-->>H: DATA (1 gRPC message containing GetItemResponse)
    S-->>H: Trailers (grpc-status: 0, END_STREAM)
    H-->>C: Response and status OK
~~~

The diagram shows the main components, not a rule that each message must fit inside exactly one DATA frame. In practice, a gRPC message may be split across multiple HTTP/2 DATA frames; frame boundaries do not necessarily align with Protobuf message boundaries.

### One RPC, One HTTP/2 Stream, Two Application Messages

For a successful unary call, you can count at both layers:

| Layer | Count in the GetItem Example |
| --- | --- |
| RPC | 1 **GetItem** call |
| HTTP/2 | 1 stream dedicated to that call |
| Protobuf request | 1 **GetItemRequest** message |
| Protobuf response | 1 **GetItemResponse** message |
| gRPC status | 1 terminal status, e.g., **OK** |

Do not count DATA frames to infer the number of requests/responses. One message can span multiple frames due to size or transport segmentation.

## 3. What Does the stream Keyword in .proto Mean?

Compare the four declarations:

~~~proto
// Unary: one request, one response.
rpc GetItem(GetItemRequest) returns (GetItemResponse);

// Server streaming: one request, many responses.
rpc WatchItem(GetItemRequest) returns (stream ItemUpdate);

// Client streaming: many requests, one response.
rpc UploadItems(stream ItemChunk) returns (UploadSummary);

// Bidirectional streaming: many requests, many responses.
rpc Synchronize(stream SyncRequest) returns (stream SyncEvent);
~~~

All four methods are transported over an HTTP/2 stream. The difference is **the number of application messages in each direction**:

| Method Type | HTTP/2 Stream for RPC | Request Messages | Response Messages on Success |
| --- | --- | --- | --- |
| Unary | Yes, one stream | 1 | 1 |
| Server streaming | Yes, one stream | 1 | 0..N |
| Client streaming | Yes, one stream | 0..N | 1 |
| Bidirectional streaming | Yes, one stream | 0..N | 0..N |

**stream** before the request type only enables sending multiple request messages. **stream** before the response type only enables sending multiple response messages. If neither position has this keyword, the method still runs on an HTTP/2 stream, but with unary cardinality.

Another common misconception: a message containing a **repeated** field is still **one message** if the method accepts or returns that message type:

~~~proto
message ItemBatch {
  repeated GetItemRequest items = 1;
}

service CatalogService {
  rpc GetItems(ItemBatch) returns (ItemBatch);
}
~~~

**GetItems** is still unary: one **ItemBatch** request and one **ItemBatch** response. The number of elements in the **items** field does not change the RPC's cardinality. Only when you want to send parts incrementally over time within a single call should you consider streaming.

## 4. Calling Unary in Java/Spring: Simple API, Stream Still in Transport

After configuring Protobuf and gRPC Java code generation, the server can implement the unary method by extending the service base class:

~~~java
package vn.demo.catalog;

import io.grpc.Status;
import io.grpc.stub.StreamObserver;
import org.springframework.stereotype.Service;
import vn.demo.grpc.catalog.v1.CatalogServiceGrpc;
import vn.demo.grpc.catalog.v1.GetItemRequest;
import vn.demo.grpc.catalog.v1.GetItemResponse;

@Service
public class CatalogServiceImpl
        extends CatalogServiceGrpc.CatalogServiceImplBase {

    @Override
    public void getItem(
            GetItemRequest request,
            StreamObserver<GetItemResponse> responseObserver) {

        if (request.getItemId().isBlank()) {
            responseObserver.onError(Status.INVALID_ARGUMENT
                .withDescription("item_id is required")
                .asRuntimeException());
            return;
        }

        GetItemResponse response = GetItemResponse.newBuilder()
            .setItemId(request.getItemId())
            .setName("Mechanical keyboard")
            .setAvailableQuantity(12)
            .build();

        responseObserver.onNext(response);
        responseObserver.onCompleted();
    }
}
~~~

This is the application-layer server API: the method receives **one request object** and uses **responseObserver** to send **one response object**. The underlying gRPC layer manages the HTTP/2 stream, message framing, and terminal status. The service author does not need to create HTTP/2 streams manually or work directly with DATA frames.

The client can invoke it using a blocking stub:

~~~java
GetItemRequest request = GetItemRequest.newBuilder()
    .setItemId("keyboard-01")
    .build();

GetItemResponse response = blockingStub
    .withDeadlineAfter(2, TimeUnit.SECONDS)
    .getItem(request);

System.out.println(response.getName());
~~~

Here the Java API takes one request and returns one response directly. The stub hides transport details from business code; it does not eliminate the HTTP/2 stream. Each call to **getItem(request)** is a separate RPC and is transported by gRPC over an HTTP/2 stream.

In a Spring application, the service bean is typically registered with the gRPC server via the active starter's integration mechanism. Exact configuration may differ across Spring gRPC versions; that does not change the relationship between Protobuf cardinality and HTTP/2 streams.

## 5. What Does an HTTP/2 Stream Carry?

A gRPC RPC over HTTP/2 typically has three groups of components:

1. **Initial headers:** identify the method, content type, and call metadata.
2. **DATA frames:** carry the framed and encoded gRPC messages.
3. **Trailers:** carry the gRPC terminal status, typically including **grpc-status** and optionally **grpc-message** or additional metadata.

For a successful unary call, the client sends one request message in DATA; the server sends one response message in DATA; the server terminates with trailers containing **grpc-status: 0** (**OK**). On error, the server may return an error status in trailers without any application response message.

### Framing of a gRPC Message

Over HTTP/2 transport, a gRPC message has framing consisting of:

| Component | Size | Meaning |
| --- | --- | --- |
| Compressed flag | 1 byte | Indicates whether the message is compressed |
| Message length | 4 bytes | Length of the following payload |
| Message payload | Per length | Serialized Protobuf data |

The first five bytes are the gRPC message framing header, not HTTP/2 headers. The payload holds the Protobuf message. If compression is enabled, the compression flag and payload must be interpreted according to the corresponding gRPC configuration.

A gRPC message may span multiple DATA frames; the receiver reassembles bytes according to framing to reconstruct the complete message. Therefore:

- One HTTP/2 DATA frame does not equal one Protobuf message.
- One Protobuf message does not necessarily fit into exactly one DATA frame.
- The number of HTTP/2 frames does not determine whether a method is unary or streaming.

## 6. An HTTP/2 Connection Multiplexes Multiple RPCs

HTTP/2 supports **multiplexing**: multiple independent streams can coexist over a single connection. For instance, the same client can call **GetItem** for two product IDs and call another method nearly simultaneously. Those RPCs use distinct HTTP/2 stream IDs while sharing the same TCP connection.

~~~mermaid
flowchart TB
    C["One HTTP/2 connection"] --> S1["Stream 1: unary GetItem"]
    C --> S3["Stream 3: unary GetItem"]
    C --> S5["Stream 5: server streaming WatchItem"]
    S1 --> R1["1 request / 1 response"]
    S3 --> R3["1 request / 1 response"]
    S5 --> R5["1 request / many responses"]
~~~

The streams are independent at the HTTP/2 layer, yet still share connection and network resources. Multiplexing does not mean every RPC must be streaming at the Protobuf layer; two concurrent unary RPCs remain two unary calls, each with one HTTP/2 stream.

HTTP/2 streams also have half-closed states. After finishing sending the request, the client can close its send direction while the server is still returning the response. For unary calls, this occurs naturally after the single request; the server proceeds to send the response and trailers to complete the RPC.

## 7. Termination States: HTTP/2 END_STREAM and gRPC Status

These two signals are related but not synonymous:

- **HTTP/2 END_STREAM** marks that the sender has finished sending frames on the corresponding direction of the HTTP/2 stream.
- **gRPC status** represents the outcome of the call at the gRPC layer, such as **OK**, **INVALID_ARGUMENT**, or **UNAVAILABLE**.

Normally, the gRPC server sends the status in **trailers** and ends the HTTP/2 stream. Hence, seeing that the request has closed its send direction does not mean the RPC is complete; the client may still be waiting for the response and trailers from the server.

For unary:

1. Client sends the request message and closes its send direction.
2. Server processes the request.
3. Server sends the response message if successful.
4. Server sends trailers containing **grpc-status**, then closes the stream.

If the server returns **INVALID_ARGUMENT**, there may be no response message. The client receives the error through the gRPC API, such as **StatusRuntimeException** with a blocking stub. Do not rely solely on the presence of a DATA frame or HTTP status to conclude business success; inspect **gRPC status**.

## 8. Observing and Diagnosing at the Right Layer

When debugging a unary RPC, separate these questions:

| Question | Where to Observe |
| --- | --- |
| Which method did the client call? | RPC path, e.g., **/demo.catalog.v1.CatalogService/GetItem** |
| Did the call create a transport stream? | HTTP/2 stream ID and connection state |
| How many application requests/responses occurred? | gRPC message cardinality, method-level logs/interceptors |
| Did the call end successfully? | gRPC trailers and **grpc-status** |
| Why was the call slow? | Deadline, latency, server processing, network, and queues |

**Metadata** and **interceptors** typically operate at the RPC level and can attach request IDs, authenticate, trace, and measure timing. For unary calls, logging method, status, and latency is usually enough to track cardinality. When reading traces or network captures, avoid misinterpreting an HTTP/2 stream as a Protobuf-level streaming RPC.

In production, secure transport with **TLS**; do not log tokens or sensitive data. Deadlines bound waiting time, while gRPC status lets clients classify outcomes. None of these factors alter whether a method is unary or streaming.

## 9. Common Misconceptions

| Misconception | Accurate Understanding |
| --- | --- |
| Unary has no stream | Unary still uses one HTTP/2 stream to carry the RPC |
| No **stream** in .proto means no HTTP/2 stream | The Protobuf keyword governs application message count; the HTTP/2 stream still exists |
| An HTTP/2 stream always carries multiple messages | Unary typically has one request and one response message on that stream |
| One DATA frame equals one Protobuf message | A message may be split across multiple DATA frames |
| **repeated** means streaming | **repeated** is multiple elements inside one message; streaming is multiple messages in one RPC |
| Once the client finishes sending the request, the RPC is complete | The RPC still awaits the server response and gRPC status |
| HTTP status 200 means business success | Check gRPC status in trailers |

## 10. Summary and Self-Check

Unary declaration:

~~~proto
rpc GetItem(GetItemRequest) returns (GetItemResponse);
~~~

Without the **stream** keyword on either side, the method has **one request, one response** cardinality. Even so, gRPC still uses **one HTTP/2 stream for that RPC**. The HTTP/2 stream is the transport mechanism; the **stream** keyword in **.proto** determines whether a side of the API may send multiple messages.

Self-check:

1. Can a unary RPC be sent over an HTTP/2 stream? Why?
2. Will two concurrent unary RPCs on the same HTTP/2 connection use one or two HTTP/2 streams?
3. Does a Protobuf message containing a **repeated** field with 500 elements turn a unary method into a streaming method?
4. Why can a single gRPC message occupy multiple HTTP/2 DATA frames?
5. When the client has finished sending the request but has not yet received trailers, is the RPC finished?

Distinguishing **message cardinality at the gRPC layer** from **transport streams at the HTTP/2 layer** enables you to read Protobuf contracts accurately, understand generated gRPC Java APIs, and diagnose network traffic without confusing unary with streaming.
