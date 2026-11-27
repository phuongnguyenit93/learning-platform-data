# Trailers and outcome metadata

## Learning objectives

After this lesson, you can:

- Explain **HTTP/2 trailers** and their role in concluding a gRPC RPC.
- Distinguish **response messages**, **initial response headers**, **trailers**, **HTTP status**, and **gRPC status**.
- Read **grpc-status**, **grpc-message**, **grpc-status-details-bin**, and custom trailing metadata.
- Return status/trailers from the server using grpc-java; read trailers in blocking and async clients.
- Choose appropriate outcome information for business errors, diagnostics, retries, and operational observability in Spring gRPC.
- Test trailer propagation and handle cases where an RPC terminates without the client receiving trailers.

## 1. What are trailers?

In gRPC over HTTP/2, **trailers** are metadata sent at the end of an RPC. The server uses them to announce the **final outcome** of the call, especially the **gRPC status** code. Trailers are sent via an HTTP/2 **HEADERS frame** ending the stream, usually with the **END_STREAM** flag.

An RPC typically has three types of data on the response side:

| Component | Timing | Purpose |
| --- | --- | --- |
| **Initial response headers** | Start of response, before response messages | Initial metadata such as API version or client-facing info |
| **Response message(s)** | Inside the DATA portion of the HTTP/2 stream | Business data defined in Protocol Buffers |
| **Trailers** | End of RPC | Sends **grpc-status**, error description, and end-of-call metadata |

Successful unary example:

~~~text
Server -> Client
  HEADERS
    :status: 200
    content-type: application/grpc
  DATA
    [serialized GetOrderResponse]
  HEADERS (trailers, END_STREAM)
    grpc-status: 0
~~~

Resource-not-found error example:

~~~text
Server -> Client
  HEADERS (trailers-only, END_STREAM)
    :status: 200
    content-type: application/grpc
    grpc-status: 5
    grpc-message: Order%20not%20found
~~~

The second case is a **trailers-only response**: the error occurred before the server sent initial headers or a response message, so a single final HEADERS block carries all necessary HTTP/gRPC information.

**Key takeaway:** HTTP status **200** does not mean the RPC succeeded. The RPC outcome is determined by **grpc-status**. The gRPC client reads trailers and turns the status code into the corresponding result or exception.

## 2. Standard fields in trailers

| Field | Meaning | Usage |
| --- | --- | --- |
| **grpc-status** | RPC termination code; **0** is OK | Use this numeric code to determine success/failure |
| **grpc-message** | Short error description if present | Diagnostics only; do not parse strings to drive business logic |
| **grpc-status-details-bin** | Extended error details serialized in binary form | Used when client/server agree on the rich error model |

Common status codes:

- **INVALID_ARGUMENT**: invalid request.
- **NOT_FOUND**: business resource does not exist.
- **UNAUTHENTICATED** / **PERMISSION_DENIED**: missing authentication or insufficient permissions.
- **FAILED_PRECONDITION**: current state does not allow the operation.
- **RESOURCE_EXHAUSTED**: quota or resource limit exceeded.
- **UNAVAILABLE**: backend/transport temporarily unavailable.
- **DEADLINE_EXCEEDED**: caller did not receive a result before the deadline.
- **CANCELLED**: RPC was cancelled.

In grpc-java, return statuses using **io.grpc.Status** rather than manually adding a custom header named **grpc-status**. The runtime converts the status into the proper protocol field.

**grpc-message** has its own wire encoding rules. Never include stack traces, SQL, tokens, customer data, or internal details in error descriptions returned to clients.

## 3. Custom trailing metadata: when is it needed?

An application may add custom metadata to trailers, for example:

- **x-error-id**: reference ID to locate internal logs.
- **x-service-version**: server version if needed for diagnostics.
- **x-result-source**: processing source of the result, when permitted to be exposed.

Do not put primary business data into trailers. If the client needs **order_id**, order state, a structured list of validation errors, or the next cursor, declare them in the **response message**. Trailers are for end-of-call metadata for the whole RPC.

Custom key names should be lowercase and must not use the reserved **grpc-** prefix. Keep trailers small; avoid sending large payloads, tokens, or personal data. Proxies/gateways may enforce metadata limits and separate forwarding policies.

## 4. Returning trailers from the server with grpc-java

### 4.1. Attaching trailers when returning an error

In grpc-java, **Status.asRuntimeException(Metadata)** lets you attach metadata alongside a status. Example of a Spring service returning a not-found error and a reference ID:

~~~java
import dev.example.orders.v1.GetOrderRequest;
import dev.example.orders.v1.GetOrderResponse;
import dev.example.orders.v1.OrderServiceGrpc;
import io.grpc.Metadata;
import io.grpc.Status;
import io.grpc.stub.StreamObserver;
import org.springframework.stereotype.Component;

@Component
public class OrderEndpoint
        extends OrderServiceGrpc.OrderServiceImplBase {

    private static final Metadata.Key<String> ERROR_ID =
            Metadata.Key.of(
                    "x-error-id",
                    Metadata.ASCII_STRING_MARSHALLER);

    @Override
    public void getOrder(
            GetOrderRequest request,
            StreamObserver<GetOrderResponse> observer) {

        String id = request.getOrderId().trim();

        if (id.isEmpty()) {
            observer.onError(
                    Status.INVALID_ARGUMENT
                            .withDescription("order_id must not be empty")
                            .asRuntimeException());
            return;
        }

        if (!"order-42".equals(id)) {
            Metadata trailers = new Metadata();
            trailers.put(ERROR_ID, "ord-lookup-404");

            observer.onError(
                    Status.NOT_FOUND
                            .withDescription("Order not found")
                            .asRuntimeException(trailers));
            return;
        }

        observer.onNext(
                GetOrderResponse.newBuilder()
                        .setOrderId(id)
                        .setState("PENDING")
                        .build());
        observer.onCompleted();
    }
}
~~~

When calling **onError(...)**, the runtime finishes the RPC with the attached status and trailers. On success, **onNext(...)** sends the response message and **onCompleted()** finishes the RPC with status **OK**.

The response observer does not expose a general API for adding arbitrary trailers at any point. If you need to add metadata on both success and error paths, use a **ServerInterceptor** to decorate **ServerCall**.

### 4.2. Adding trailers centrally with ServerInterceptor

**ServerCall.close(Status, Metadata)** is where the runtime closes the RPC. An interceptor can wrap this call and add a metadata key:

~~~java
import io.grpc.ForwardingServerCall;
import io.grpc.Metadata;
import io.grpc.ServerCall;
import io.grpc.ServerCallHandler;
import io.grpc.ServerInterceptor;
import io.grpc.Status;

public final class ResultTrailerInterceptor
        implements ServerInterceptor {

    private static final Metadata.Key<String> SERVICE_VERSION =
            Metadata.Key.of(
                    "x-service-version",
                    Metadata.ASCII_STRING_MARSHALLER);

    @Override
    public <ReqT, RespT> ServerCall.Listener<ReqT> interceptCall(
            ServerCall<ReqT, RespT> call,
            Metadata requestHeaders,
            ServerCallHandler<ReqT, RespT> next) {

        ServerCall<ReqT, RespT> decorated =
                new ForwardingServerCall
                        .SimpleForwardingServerCall<ReqT, RespT>(call) {
                    @Override
                    public void close(Status status, Metadata trailers) {
                        trailers.put(SERVICE_VERSION, "orders-v1");
                        super.close(status, trailers);
                    }
                };

        return next.startCall(decorated, requestHeaders);
    }
}
~~~

This interceptor adds metadata to **every terminal outcome** it observes, whether OK or an error. If you only want to add it on error, check **status.isOk()** before adding. Never modify or overwrite **grpc-status**; the runtime owns this standard field.

You can register the interceptor via **ServerInterceptors.intercept(endpoint, interceptor)** when using grpc-java `ServerBuilder`. If a Spring gRPC starter manages servers/services automatically, use the interceptor registration mechanism provided by your starter version to avoid creating a second server on the same port.

**Initial headers differ from trailers:** use **ServerCall.sendHeaders(...)** to send initial metadata. Never call `sendHeaders` intending to replace end-of-RPC outcome metadata.

## 5. Reading trailers on the client

### 5.1. Blocking stub: retrieving trailers on error

With a blocking stub, when an RPC fails, the client usually receives a **StatusRuntimeException**. The exception may carry trailers:

~~~java
import io.grpc.Metadata;
import io.grpc.Status;
import io.grpc.StatusRuntimeException;

private static final Metadata.Key<String> ERROR_ID =
        Metadata.Key.of(
                "x-error-id",
                Metadata.ASCII_STRING_MARSHALLER);

try {
    GetOrderResponse response = stub.getOrder(request);
    // Handle successful response.
} catch (StatusRuntimeException error) {
    Status.Code code = error.getStatus().getCode();
    Metadata trailers = error.getTrailers();

    if (trailers != null) {
        String errorId = trailers.get(ERROR_ID);
        // Use errorId for log lookup; do not treat it as authentication proof.
    }

    // Branch on code; do not parse description text.
}
~~~

**getTrailers() can return null**, for example if a transport error occurred before the client received a final server response. Therefore, never assume every exception carries custom trailing metadata.

A blocking stub returns the response message and does not directly expose trailers for a successful RPC. If you need to read trailers on both success and failure paths, use a **ClientInterceptor**.

### 5.2. ClientInterceptor: receiving status and trailers in onClose

At a lower grpc-java layer, **ClientCall.Listener.onClose(Status, Metadata)** is invoked when the RPC ends. This is the place to observe status and trailers for both successes and failures:

~~~java
import io.grpc.CallOptions;
import io.grpc.Channel;
import io.grpc.ClientCall;
import io.grpc.ClientInterceptor;
import io.grpc.ForwardingClientCall;
import io.grpc.ForwardingClientCallListener;
import io.grpc.Metadata;
import io.grpc.MethodDescriptor;
import io.grpc.Status;

public final class ResultTrailerClientInterceptor
        implements ClientInterceptor {

    private static final Metadata.Key<String> SERVICE_VERSION =
            Metadata.Key.of(
                    "x-service-version",
                    Metadata.ASCII_STRING_MARSHALLER);

    @Override
    public <ReqT, RespT> ClientCall<ReqT, RespT> interceptCall(
            MethodDescriptor<ReqT, RespT> method,
            CallOptions options,
            Channel next) {

        ClientCall<ReqT, RespT> delegate =
                next.newCall(method, options);

        return new ForwardingClientCall
                .SimpleForwardingClientCall<ReqT, RespT>(delegate) {
            @Override
            public void start(
                    Listener<RespT> listener,
                    Metadata requestHeaders) {

                Listener<RespT> wrapped =
                        new ForwardingClientCallListener
                                .SimpleForwardingClientCallListener<RespT>(
                                        listener) {
                            @Override
                            public void onClose(
                                    Status status,
                                    Metadata trailers) {

                                String version =
                                        trailers.get(SERVICE_VERSION);

                                // Forward status/version to safe telemetry.
                                super.onClose(status, trailers);
                            }
                        };

                super.start(wrapped, requestHeaders);
            }
        };
    }
}
~~~

In real applications, send needed data to telemetry or a context scoped to that specific RPC; do not store metadata in a shared singleton variable across calls. If the client uses Spring, attach the interceptor to the Channel wrapper or stub via your configuration mechanism. Interceptors do not create new connections.

## 6. Rich error details with google.rpc.Status

For errors requiring rich machine-readable details, gRPC can use the **rich error model**. Details are packed inside **google.rpc.Status** and transmitted in the binary metadata **grpc-status-details-bin**.

Conceptual example for a validation error:

~~~java
import com.google.protobuf.Any;
import com.google.rpc.BadRequest;
import com.google.rpc.Status;
import io.grpc.protobuf.StatusProto;
import io.grpc.stub.StreamObserver;

BadRequest detail = BadRequest.newBuilder()
        .addFieldViolations(
                BadRequest.FieldViolation.newBuilder()
                        .setField("order_id")
                        .setDescription("Value must not be empty"))
        .build();

Status richStatus = Status.newBuilder()
        .setCode(io.grpc.Status.Code.INVALID_ARGUMENT.value())
        .setMessage("Invalid request")
        .addDetails(Any.pack(detail))
        .build();

observer.onError(StatusProto.toStatusRuntimeException(richStatus));
~~~

Clients can extract details using **StatusProto.fromThrowable(error)** if the corresponding library is included and both sides agree on the error detail schemas. The example above needs compatible dependencies for **grpc-protobuf**, **protobuf-java**, and **proto-google-common-protos**.

Rich error details are useful when the client needs to display or handle field-level errors without parsing strings. However:

- Send only details the client is allowed to see.
- Never put stack traces, SQL queries, internal paths, or tokens inside **Any**.
- Do not send an excessively large list of error details.
- Clients must tolerate unknown detail types or newer detail versions.
- The base **Status.Code** remains the primary classification; details enrich the error's meaning.

Do not confuse **google.rpc.Status** with the method's protobuf response. When an RPC fails, rich status is an RPC-layer error description, not a business method's success response.

## 7. Trailers in streaming RPCs

With server streaming, the client may receive many response messages before the RPC ends:

~~~text
One HTTP/2 stream:
  initial HEADERS
  DATA: OrderUpdate #1
  DATA: OrderUpdate #2
  DATA: OrderUpdate #3
  trailing HEADERS: grpc-status=0
  END_STREAM
~~~

There is **only one set of trailers at the end of the RPC**, not one set of trailers per message. If an event needs **sequence**, **event_id**, cursor, or update status, declare them in the protobuf message.

With client streaming and bidirectional streaming, the client can **half-close** its send direction with **onCompleted()** while still waiting for responses. Trailers arrive only when the entire RPC concludes. When the caller cancels or the connection drops, the client may not receive trailers from the server.

Therefore, clients must never use trailers as a continuous progress-update channel. Use response messages for streaming data and trailers for end-of-call metadata.

## 8. Status and trailers are not a retry guarantee

A custom trailer such as **x-retry-after-ms** can be defined by an application, yet gRPC does not automatically interpret that custom key as a retry policy. If used, it needs a clear contract and value validation. Normally, choose a semantically clear **Status.Code** and use a controlled service config/backoff policy.

| Outcome | Meaning | Retry? |
| --- | --- | --- |
| **OK** | RPC succeeded | Not needed |
| **INVALID_ARGUMENT** | Caller sent bad input | Fix the request |
| **NOT_FOUND** | Resource does not exist | Usually no |
| **UNAUTHENTICATED** | Missing/invalid authentication | Refresh credentials if appropriate |
| **PERMISSION_DENIED** | Insufficient permissions | Do not retry blindly |
| **RESOURCE_EXHAUSTED** | Quota/resources depleted | Back off, follow policy |
| **UNAVAILABLE** | Temporarily unable to serve | May retry with backoff if operation is safe |
| **DEADLINE_EXCEEDED** | Caller did not receive result in time | Check idempotency and actual server state |

Especially for write operations, **DEADLINE_EXCEEDED** does not prove the server did not commit. A custom **x-error-id** trailer only aids lookup; it cannot confirm whether a transaction rolled back or succeeded.

## 9. Cases where the client receives no trailers

Trailers are the final result of an RPC that progressed far enough for the server/transport to send an ending block. They can be absent if:

- DNS, TCP, or TLS fails before the RPC reaches the server.
- A proxy or connection closes mid-flight.
- The client cancels the RPC before the server finishes.
- The deadline expires before receiving the final response.
- The transport fails while transmitting trailers.

In these cases, the runtime may supply a client/transport-generated status, while **custom trailers from the server do not exist or never reach the client**. Client code must tolerate **null trailers or missing keys**.

Never build business flows that require **x-error-id** to proceed. Trailers are a helpful diagnostic channel, not durable state storage.

## 10. Testing trailers with grpc-inprocess

You can use **InProcessServerBuilder** and **InProcessChannelBuilder** to test status/trailer delivery through the gRPC runtime without network ports. The JUnit 5 example below tests a **NOT_FOUND** error with a custom trailer:

~~~java
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNotNull;

import dev.example.orders.v1.GetOrderRequest;
import dev.example.orders.v1.OrderServiceGrpc;
import io.grpc.ManagedChannel;
import io.grpc.Metadata;
import io.grpc.Server;
import io.grpc.Status;
import io.grpc.StatusRuntimeException;
import io.grpc.inprocess.InProcessChannelBuilder;
import io.grpc.inprocess.InProcessServerBuilder;
import org.junit.jupiter.api.Test;

class ResultTrailerTest {

    private static final Metadata.Key<String> ERROR_ID =
            Metadata.Key.of(
                    "x-error-id",
                    Metadata.ASCII_STRING_MARSHALLER);

    @Test
    void notFoundIncludesErrorReference() throws Exception {
        String name = InProcessServerBuilder.generateName();

        Server server = InProcessServerBuilder.forName(name)
                .directExecutor()
                .addService(new OrderEndpoint())
                .build()
                .start();

        ManagedChannel channel = InProcessChannelBuilder.forName(name)
                .directExecutor()
                .build();

        try {
            OrderServiceGrpc.OrderServiceBlockingStub stub =
                    OrderServiceGrpc.newBlockingStub(channel);

            StatusRuntimeException error = org.junit.jupiter.api.Assertions
                    .assertThrows(
                            StatusRuntimeException.class,
                            () -> stub.getOrder(
                                    GetOrderRequest.newBuilder()
                                            .setOrderId("missing")
                                            .build()));

            assertEquals(Status.Code.NOT_FOUND,
                    error.getStatus().getCode());

            Metadata trailers = error.getTrailers();
            assertNotNull(trailers);
            assertEquals("ord-lookup-404", trailers.get(ERROR_ID));
        } finally {
            channel.shutdownNow();
            server.shutdownNow();
        }
    }
}
~~~

This example assumes **OrderEndpoint** from section 4 is registered and returns **x-error-id** on not-found. A compatible **grpc-inprocess** dependency for your grpc-java version is required. This test checks status/trailers through the runtime; it does not verify proxies, TLS, or whether a real external gateway preserves custom trailers.

Consider adding tests for:

- Successful RPC with trailers added by a server interceptor.
- Errors without custom trailers; the client must not assume the key is always present.
- Client interceptor observing **onClose(status, trailers)** for both OK and errors.
- Trailers-only responses.
- Rich error details with known and unknown detail types on the client.
- Connection drop/cancellation before trailers arrive.

## 11. Operations and security

Trailers are usually small, yet they still travel through HTTP/2 infrastructure and can be capped or filtered by proxies. When designing:

- **Keep metadata brief**: error IDs, versions, or a few diagnostic fields; never send large JSON/payloads.
- **Never send secrets**: tokens, cookies, personal data, and internal infrastructure details should not appear in trailers.
- **Redact logs**: an interceptor logging status and error IDs can be helpful, but do not log all metadata by default.
- **Do not replace messages with trailers**: business data that must be stored or displayed belongs in protobuf responses.
- **Track status by method**: measure OK, NOT_FOUND, UNAVAILABLE, DEADLINE_EXCEEDED rates and latency.
- **Test real proxies**: gateways/service meshes may apply different header limits or forwarding policies.

A good **x-error-id** is a random, non-disclosing reference code linked to access-controlled server logs. It aids operations without sending stack traces to callers.

## 12. Hands-on lab and self-check questions

### Hands-on lab

1. Use **OrderService/GetOrder** and the existing Spring implementation. When an order does not exist, return **NOT_FOUND** with an **x-error-id** trailer.
2. Write a blocking client catching **StatusRuntimeException**, reading **getTrailers()**, and handling missing trailers or missing keys.
3. Add **ResultTrailerInterceptor** to attach **x-service-version** to every finished RPC. Test both success and error paths.
4. Write a **ClientInterceptor** observing **onClose(Status, Metadata)**; record status and custom trailers without storing metadata in a mutable singleton.
5. Create a rich error using **google.rpc.Status** and a **BadRequest.FieldViolation**. Verify the client extracts the detail; test with an unknown detail.
6. Switch the method to server streaming, emit multiple events, and finish. Confirm trailers appear only once at the end of the RPC.
7. Run in-process tests, then test through proxy/TLS if your deployment uses a gateway; verify custom trailers are preserved and header limits are respected.

### Self-check questions

**1. How do trailers differ from initial response headers?**  
Initial headers arrive before response messages; trailers arrive at the end of the RPC and carry **grpc-status** plus final metadata.

**2. Does HTTP status 200 guarantee RPC success?**  
No. You must inspect **grpc-status** in trailers.

**3. Why doesn't a blocking stub return trailers alongside a successful response?**  
The blocking stub API returns the protobuf response directly; to observe trailers on both success and failure paths, use **ClientInterceptor.onClose(...)**.

**4. When can StatusRuntimeException.getTrailers() be null?**  
When the error occurs before the client receives trailers, such as a connection failure or mid-flight transport closure.

**5. Should you put order_id or the entire response inside trailers?**  
No. Business data belongs in the protobuf response message; trailers are for compact end-of-call metadata.

**6. How many sets of trailers does a server-streaming RPC have?**  
One set at the end of the RPC, not one set per message.

**7. How are rich error details transmitted?**  
Using **google.rpc.Status** and error details serialized in **grpc-status-details-bin**, with compatible libraries and contracts on both sides.

**8. Does a custom x-retry-after-ms trailer automatically trigger retries?**  
No. It is merely custom metadata; the client needs logic/policy understanding that key and must still consider status, deadlines, and idempotency.

## Summary

**Trailers** are the final metadata block of a gRPC RPC, where the runtime sends **grpc-status** and optionally error descriptions or custom trailing metadata. They differ from initial response headers and protobuf response messages: messages carry business data, while trailers describe the final outcome and aid diagnostics. In Spring gRPC, the server can attach trailers via **Status.asRuntimeException(Metadata)** or **ServerInterceptor/ServerCall.close(...)**; the client reads error trailers from **StatusRuntimeException** and observes all outcomes via **ClientCall.Listener.onClose(...)**. Keep metadata short, safe, optional on transport errors, and test success, failure, and streaming cases.
