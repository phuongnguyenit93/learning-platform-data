# Outbound Message Size Limits

## Learning Objectives

After this lesson, you will be able to:

- Explain outbound message size limits and identify which endpoint actually enforces the limit.
- Distinguish outbound message size from the peer's inbound limit, HTTP/2 frame size, and flow-control windows.
- Check the serialized size of a Protobuf message before sending in Java.
- Design outbound limits for unary and streaming RPCs, including when messages are generated asynchronously.
- Choose how to handle oversized payloads and design chunking for large data.
- Combine message-size guards with queues, byte budgets, compression, and tests to prevent runtime failures.

## 1. What Is Outbound Message Size?

An outbound message is a message that the current endpoint sends to its peer. On a server, this is typically a response; on a client, it is typically a request. **Outbound message size** is the size of the serialized Protobuf data that the endpoint prepares to transmit in a single send call.

An excessively large message can increase memory needed for objects, serialization buffers, gRPC buffers, and data waiting to be transmitted. If the peer does not accept that size, the RPC may terminate with an error after the sender has already started sending. In streaming, a single oversized message can break the entire RPC even if earlier messages have already been processed.

In **SPRING_GRPC**, outbound size must be considered on both the client and the server. A client can send large requests to the server; a server can return large responses to the client. The sending endpoint should check size before sending, while the receiving endpoint must still configure inbound limits to protect itself.

## 2. The Receiver Is Where the Inbound Limit Is Enforced

The size a sender can successfully transmit depends on the peer's receive limit. For example:

| Direction | Where is outbound? | Where is the inbound limit checked? |
| --- | --- | --- |
| Client sends request | Client | Server |
| Server sends response | Server | Client |
| Client-streaming | Client sends each request chunk | Server receives each chunk |
| Server-streaming | Server sends each response | Client receives each response |
| Bidirectional | Both sides send | Each side checks messages received from the other |

Inbound limits are local configurations of the receiving endpoint. Do not assume gRPC automatically negotiates a shared message limit between two peers over HTTP/2. A server may not know the client's actual inbound configuration in advance; a client does not necessarily know the server's limit either.

Therefore, the sender should enforce a limit per the application contract and check before calling send. The receiver must still enforce its inbound limit because a peer may be a different client version or bypass sender-side checks.

## 3. Serialized Size Differs from Object Size

A Java message can hold data across many objects and byte arrays. An object's heap size does not equal its Protobuf wire size:

- **Heap size** includes object headers, references, collection backing arrays, byte arrays, and runtime overhead.
- **Serialized size** is the number of bytes needed to encode the message in Protobuf binary format.
- **Wire bytes** additionally involve gRPC framing, HTTP/2 frames, and possibly compression.

With Protobuf Java, generated messages typically provide **getSerializedSize()**. This value is useful for checking payloads before sending:

~~~java
UploadRequest request = buildRequest();
int serializedBytes = request.getSerializedSize();

System.out.println("Serialized bytes: " + serializedBytes);
~~~

Do not use the original file size or the length of a single field as a proxy for the whole message. Field tags, length prefixes, nested messages, and other fields also contribute to serialized size.

## 4. Setting Application Limits Before Sending

A clear approach is to define an outbound threshold per the service contract and check messages before passing them to the stub or observer:

~~~java
import com.google.protobuf.MessageLite;

final class MessageSizeGuard {
    private final int maxBytes;

    MessageSizeGuard(int maxBytes) {
        if (maxBytes <= 0) {
            throw new IllegalArgumentException("maxBytes must be positive");
        }
        this.maxBytes = maxBytes;
    }

    void check(MessageLite message) {
        int size = message.getSerializedSize();
        if (size > maxBytes) {
            throw new IllegalArgumentException(
                "Outbound message is " + size
                    + " bytes; limit is " + maxBytes);
        }
    }
}
~~~

Example of a client checking before calling a unary RPC:

~~~java
MessageSizeGuard guard =
    new MessageSizeGuard(4 * 1024 * 1024);

CreateDocumentRequest request = buildRequest();
guard.check(request);

CreateDocumentResponse response = blockingStub.createDocument(request);
~~~

This is an application-layer check that catches oversized payloads early and produces an intelligible error for the caller. It does not replace the server's inbound limit, as another client could bypass this guard.

## 5. Server Checking Responses Before onNext

For server-streaming or bidirectional streaming, check each response before sending:

~~~java
private static final int MAX_RESPONSE_BYTES = 2 * 1024 * 1024;

void sendUpdate(
        PriceUpdate update,
        StreamObserver<PriceUpdate> responseObserver) {

    int size = update.getSerializedSize();
    if (size > MAX_RESPONSE_BYTES) {
        responseObserver.onError(
            Status.RESOURCE_EXHAUSTED
                .withDescription("Outbound response exceeds service limit")
                .asRuntimeException());
        return;
    }

    responseObserver.onNext(update);
}
~~~

In a real service, ensure terminal errors are emitted only once and the producer stops after calling `onError`. Never keep calling `onNext` after `onError` or `onCompleted`. If responses are produced by multiple workers, route them through a single sequential outbound writer to check size and send in a single order.

For unary RPCs, run the guard before calling `onNext` and `onCompleted`. If a response exceeds the application limit, terminate the call with the specified status instead of attempting to send a payload the client may reject.

## 6. Outbound Configuration APIs Depend on Version and Transport

gRPC Java configures inbound message size on server and channel builders, but you should not assume every builder or every transport has a symmetric outbound setter. Certain per-call or transport APIs/options can vary across library versions.

Before using a specific outbound option:

1. Check the Javadoc for the exact version of `grpc-java` in use.
2. Confirm whether the option applies to client requests, server responses, or both.
3. Confirm whether the actual transport supports that option.
4. Test messages just below and above the threshold over a real channel/server.

Do not invent calls like **maxOutboundMessageSize()** on a **ServerBuilder** just because the inbound API has **maxInboundMessageSize()**. If the transport does not provide an outbound guard, perform application-layer checks using serialized size and let the receiver enforce its own inbound limit.

Even when the transport offers an outbound option, an application guard remains useful for returning clear business errors, avoiding serializing/sending payloads guaranteed to be too large, and protecting queues before messages enter the transport.

## 7. Outbound Message Size in Streaming

An outbound limit applies per message, not to the total volume of the entire stream. A server-streaming RPC can send thousands of small responses whose cumulative data is many times larger than the per-message threshold.

With streaming, distinguish:

- **Per-message limit**: maximum size of each individual message.
- **Per-RPC byte quota**: total data permitted to be sent in a single RPC.
- **Queue byte budget**: total payload currently waiting to be sent in memory.
- **Rate limit**: sending rate over a time window.

This rule applies to both directions: the client must check each chunk before calling the request observer in client-streaming; the server must check each response before calling the response observer in server-streaming. With bidirectional streaming, each endpoint runs guards for its own outbound messages.

Messages can be below the per-message limit and still cause queues to grow excessively if the producer generates responses faster than the transport sends them. Therefore, size guards must be paired with outbound readiness and bounded queues.

Example of draining responses based on readiness:

~~~java
void drain() {
    while (!cancelled.get() && outbound.isReady()) {
        PriceUpdate next = pending.poll();
        if (next == null) {
            return;
        }

        sizeGuard.check(next);
        outbound.onNext(next);
    }
}
~~~

This snippet assumes the queue holds only checked messages or that the guard can emit an error along a single terminal path. If the guard throws an exception, the writer must catch it, stop the producer, and terminate the RPC properly.

## 8. Large Payloads: Chunk or Raise the Limit?

Raising the limit can make sense when large payloads are an explicit business requirement, concurrency is low, and the memory budget is accounted for. For files, images, or large binary data, chunked streaming usually provides better control over memory and progress.

Example:

~~~proto
syntax = "proto3";

message DownloadChunk {
  string transfer_id = 1;
  uint64 sequence = 2;
  int64 offset = 3;
  bytes data = 4;
  bytes checksum = 5;
  bool last = 6;
}

service FileService {
  rpc Download(DownloadRequest) returns (stream DownloadChunk);
}
~~~

Each chunk must stay below the server's outbound limit and the client's inbound limit. The contract should specify:

- Target and maximum chunk size.
- Sequence/offset to detect missing or duplicate chunks.
- Per-chunk checksum and whole-file checksum if needed.
- Maximum total transfer size.
- How to resume after reconnection and handle cancellation.
- Transfer expiration and content access permissions.

Do not pick an arbitrary chunk size while ignoring receiver limits. Chunks that are too large still get rejected; chunks that are too small increase framing, callback, and processing overhead.

## 9. Compression Does Not Replace Size Guards

gRPC can compress messages to reduce bytes transmitted over the network. However, compression does not remove the need to control application data sizes:

- **getSerializedSize()** measures the Protobuf message before compression.
- Decompressed data can be much larger than bytes sent on the wire.
- Compression consumes CPU and can allocate additional buffers.
- A large message still needs to be serialized, held in memory, and processed at the receiver.

Do not assume a message exceeding the application threshold becomes safe just because it compresses well. Set guards based on serialized payloads and receiver limits; test with the actual client/server compression configuration.

For already-compressed content such as JPEG, ZIP, or video codecs, adding gRPC compression may not noticeably reduce size. Evaluate benefits and CPU cost before enabling compression for all messages.

## 10. Outbound Metadata Is a Separate Limit

gRPC metadata is transmitted in HTTP/2 headers/trailers, not the Protobuf message body. Metadata size is typically bounded separately at the receiving endpoint.

Do not move large payloads into metadata to bypass outbound message limits. Metadata is appropriate for:

- Authentication tokens and credentials.
- Trace IDs and correlation IDs.
- Small routing hints or protocol versions.
- Status details or bounded control information.

Document contents, large JSON payloads, long lists, or binary payloads belong in the message body or an appropriate storage channel. Increasing the metadata limit does not increase the message-size limit either.

## 11. Handling Outbound Messages That Exceed the Threshold

Identify errors before sending whenever the application has enough information:

- For unary RPCs, return an error with an appropriate status, typically **RESOURCE_EXHAUSTED** when exceeding allowed quotas/sizes.
- For streaming, stop the producer, do not emit the oversized message, and end the stream through a single terminal path.
- If the payload can be split, return guidance or use a dedicated streaming RPC.
- If the error comes from the peer's inbound limit, record the returned status and do not retry the identical unchanged payload.

Do not convert size errors into **INTERNAL** when the cause is a known resource or contract limit. Do not return payload contents in the status description; include only actual size, threshold, and correlation ID if appropriate.

If clients need to know server limits in advance, expose capabilities/limits in an API or configure clients to match the deployment contract. Do not rely on gRPC automatically exchanging these limits.

## 12. Testing Outbound Message Sizes

Tests must verify both sender-side guards and receiver behavior:

1. A message smaller than the application limit is sent successfully.
2. A message exceeding the application limit is blocked before calling send.
3. A message below the sender's guard but above the peer's inbound limit is rejected by the peer.
4. A server response exceeding the client's inbound limit is verified from the client side.
5. Streaming with multiple valid messages whose total bytes exceed the quota is handled per the per-RPC policy.
6. Queues do not retain payloads exceeding the byte budget.
7. Enabling/disabling compression does not bypass application guards.
8. Cancellation/deadlines stop the producer when a response cannot be sent.

Example unit test for the guard:

Schema used in the example:

~~~proto
syntax = "proto3";

package learning.documents.v1;
option java_package = "com.example.documents.v1";
option java_multiple_files = true;

message DocumentPayload {
  bytes content = 1;
}
~~~

~~~java
import static org.junit.jupiter.api.Assertions.*;

import com.google.protobuf.ByteString;
import org.junit.jupiter.api.Test;

class MessageSizeGuardTest {
    @Test
    void rejectsMessageAboveLimit() {
        DocumentPayload payload = DocumentPayload.newBuilder()
            .setContent(ByteString.copyFrom(new byte[1024]))
            .build();

        MessageSizeGuard guard = new MessageSizeGuard(512);

        assertThrows(
            IllegalArgumentException.class,
            () -> guard.check(payload));
    }
}
~~~

Unit tests verify the application guard. Integration tests still need a real channel/server to check the receiver's inbound limit and the status observed across the RPC.

## 13. Common Mistakes

| Mistake | Consequence | How to handle |
| --- | --- | --- |
| Assuming the sender automatically knows the peer's inbound limit | Messages may be sent only to be rejected by the peer | Share limits via contract and guard before sending. |
| Confusing outbound size with HTTP/2 frame size | Tuning frames does not solve oversized messages | Check serialized message size and receiver limits. |
| Limiting only individual messages | Stream totals or queues can still grow too large | Add per-RPC quotas and byte budgets. |
| Using file size instead of serialized size | Misses Protobuf fields/tags/framing | Use `getSerializedSize()` on the complete message. |
| Believing compression makes oversized messages valid | Decompressed payload can still exceed limits | Control payload size before compression and test the receiver. |
| Assuming every builder has `maxOutboundMessageSize` | Compilation failure or ineffective configuration | Check version/transport APIs; keep an application guard. |
| Continuing the stream after a response is rejected | Terminal error, resources remain held | Stop the producer and terminate the RPC strictly once. |
| Ignoring queues when checking sizes | Many valid messages still spike heap usage | Bound queues by both message count and bytes. |

## 14. Practice Exercises

A Spring gRPC service sends reports via server-streaming:

1. Set an application outbound limit of 2 MiB per response.
2. Use `getSerializedSize()` to check each response before enqueueing and before sending.
3. Bound the outbound queue by both message count and total bytes.
4. Use `isReady()` to drain the queue with only a single writer for the response observer.
5. Produce a response larger than 2 MiB and verify the server terminates the RPC with the specified status.
6. Produce a response below the server guard but larger than the client's inbound limit; verify the client observes the error.
7. Design a chunked streaming version for large reports, including sequence, offset, and checksum.
8. Test with compression enabled/disabled and multiple concurrent RPCs.

**Completion criteria:** distinguish outbound guards from receiver inbound limits, accurately check serialized sizes, bound queues and total quotas, and handle unsendable messages consistently.

## 15. Key Takeaways

- Outbound refers to messages sent from the current endpoint; inbound limits are enforced at the receiving peer.
- Do not assume gRPC automatically negotiates a shared message limit between two endpoints.
- Use **getSerializedSize()** to check Protobuf payloads before sending; this is not heap size.
- Per-message limits differ from total stream bytes, queue budgets, HTTP/2 frame sizes, and metadata limits.
- For streaming, check each message, bound queues, and cap total quotas; use chunking for large payloads.
- Compression reduces bytes on the wire but does not replace guards or receiver limits.
- Do not assume all builders/transports have an outbound API identical to inbound; verify your version and always keep an application guard.

Controlling outbound message sizes helps Spring gRPC services avoid generating payloads that peers cannot receive, reduces memory pressure, and maintains predictable behavior for both unary and streaming RPCs.
