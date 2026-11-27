# withInterceptors and Metadata

Generated stubs in gRPC Java allow attaching a **ClientInterceptor** using the **withInterceptors(...)** method. An interceptor observes or modifies an RPC at the call layer, while **Metadata** carries auxiliary headers such as request ID, tenant, locale, or tracing information. Combining these two mechanisms lets a Spring gRPC client apply cross-cutting policies across many methods without putting control data into Protobuf messages.

In Spring gRPC, you can create a base stub from a channel managed by the application or starter, attach interceptors once, and then create derived stubs with deadlines or CallCredentials per RPC. Stubs are immutable: every configuration operation returns a new stub. Interceptors should be stateless or thread-safe because the same instance can handle many concurrent calls.

## 1. What Is Metadata and When Is It Used?

Metadata is a set of key-value pairs transmitted alongside an RPC at the protocol layer. It is commonly used for auxiliary information outside the business payload of the request:

- Request IDs and trace/correlation IDs.
- Authenticated tenant or locale.
- Routing information or client version.
- Authentication credentials, when using an appropriate mechanism such as CallCredentials.
- Headers and trailers for diagnostics or call control.

Metadata does not replace fields in Protobuf. If a value is business data that the service needs to process, store, or validate against a schema, put it in the request message. Metadata is suited for communication context, security, and observability at the RPC layer.

gRPC metadata is transmitted as HTTP/2 headers and trailers. Key names must be lowercase. Text keys use an ASCII marshaller; binary keys must end with the **-bin** suffix and use a binary marshaller. Do not create custom keys starting with grpc-, as that namespace is reserved for the protocol.

## 2. Declaring Metadata.Key with the Right Type

Example of declaring an ASCII request ID key:

~~~java
private static final Metadata.Key<String> REQUEST_ID_HEADER =
    Metadata.Key.of(
        "x-request-id",
        Metadata.ASCII_STRING_MARSHALLER);
~~~

Binary metadata can be declared as follows:

~~~java
private static final Metadata.Key<byte[]> SIGNATURE_HEADER =
    Metadata.Key.of(
        "x-payload-signature-bin",
        Metadata.BINARY_BYTE_MARSHALLER);
~~~

Do not use an ASCII marshaller for arbitrary byte arrays. Conversely, do not use a binary marshaller for ordinary text values. Keep keys statically declared so client and server use the exact same name, type, and marshaller.

Metadata is not a place to store large payloads. Headers are subject to size limits at clients, proxies, and servers; sending large data in metadata can cause RPCs to be rejected or increase parsing overhead at every hop.

## 3. ClientInterceptor Adds Metadata to Every Call

ClientInterceptor is invoked when gRPC creates a client call. To add a request header, wrap ClientCall and populate metadata in the start method:

~~~java
import io.grpc.CallOptions;
import io.grpc.Channel;
import io.grpc.ClientCall;
import io.grpc.ClientInterceptor;
import io.grpc.Context;
import io.grpc.ForwardingClientCall;
import io.grpc.Metadata;
import io.grpc.MethodDescriptor;

public final class RequestIdClientInterceptor
        implements ClientInterceptor {

    static final Context.Key<String> REQUEST_ID_CONTEXT =
        Context.key("request-id");

    static final Metadata.Key<String> REQUEST_ID_HEADER =
        Metadata.Key.of(
            "x-request-id",
            Metadata.ASCII_STRING_MARSHALLER);

    @Override
    public <ReqT, RespT> ClientCall<ReqT, RespT> interceptCall(
            MethodDescriptor<ReqT, RespT> method,
            CallOptions callOptions,
            Channel next) {

        Context callContext = Context.current();
        ClientCall<ReqT, RespT> delegate =
            next.newCall(method, callOptions);

        return new ForwardingClientCall
                .SimpleForwardingClientCall<ReqT, RespT>(delegate) {

            @Override
            public void start(
                    Listener<RespT> responseListener,
                    Metadata headers) {
                String requestId =
                    callContext.get(REQUEST_ID_CONTEXT);

                if (requestId != null
                        && headers.get(REQUEST_ID_HEADER) == null) {
                    headers.put(REQUEST_ID_HEADER, requestId);
                }

                super.start(responseListener, headers);
            }
        };
    }
}
~~~

The interceptor captures Context when the call is created, then reads the request ID during start. If the caller has already set that header, this example preserves that value. The interceptor does not store the request ID in a field because the same instance can serve many requests in parallel.

## 4. Attaching Interceptors with withInterceptors

A generated stub can accept interceptors and return a new stub:

~~~java
PaymentServiceGrpc.PaymentServiceBlockingStub paymentStub =
    PaymentServiceGrpc.newBlockingStub(channel)
        .withInterceptors(new RequestIdClientInterceptor());
~~~

Then invoke the RPC within a context containing the request ID:

~~~java
String requestId = requestContext.requestId();
Context callContext = Context.current().withValue(
    RequestIdClientInterceptor.REQUEST_ID_CONTEXT,
    requestId);

PaymentResponse response;
Context previous = callContext.attach();
try {
    response = paymentStub
        .withDeadlineAfter(500, TimeUnit.MILLISECONDS)
        .getPayment(request);
} finally {
    callContext.detach(previous);
}
~~~

Context is attached for the scope of the call and detached in finally so the value does not leak to other work on the same thread. In asynchronous code, ensure the right context is active when the call is created; when offloading to an executor, use Context.wrap(...) or fixedContextExecutor(...).

If the gRPC Java version in use does not provide withInterceptors on the generated stub, you can wrap the channel before creating the stub via ClientInterceptors.intercept(channel, interceptor). Pick only one attachment point per purpose to avoid adding headers or running logic twice.

## 5. Per-Stub vs. Per-Channel Interceptors

Two scopes are commonly used:

| Attachment Method | Scope | When Appropriate |
| --- | --- | --- |
| stub.withInterceptors(...) | Derived stub and calls created from it | A group of clients or a single service needs a dedicated policy |
| ClientInterceptors.intercept(channel, ...) | Stubs created from the wrapped channel | Common policy for every service sharing that channel |

Example of wrapping a channel:

~~~java
Channel interceptedChannel = ClientInterceptors.intercept(
    channel,
    new RequestIdClientInterceptor(),
    new ClientMetricsInterceptor());

PaymentServiceGrpc.PaymentServiceBlockingStub paymentStub =
    PaymentServiceGrpc.newBlockingStub(interceptedChannel);
~~~

Do not attach the same interceptor on both the channel and the stub unintentionally. A request could pass through the logic repeatedly, producing duplicate metadata or double-counting metrics. Interceptor order also affects ClientCall wrapping order; verify effective ordering with tests when interceptors depend on one another.

## 6. Propagating Metadata from a Server Interceptor

A ServerInterceptor can read incoming metadata before the service implementation runs. For example, extracting a request ID and placing it into gRPC Context so handlers, loggers, or tracing code can access it:

~~~java
import io.grpc.Context;
import io.grpc.Contexts;
import io.grpc.Metadata;
import io.grpc.ServerCall;
import io.grpc.ServerCallHandler;
import io.grpc.ServerInterceptor;

public final class RequestIdServerInterceptor
        implements ServerInterceptor {

    private static final Context.Key<String> REQUEST_ID_CONTEXT =
        Context.key("request-id");

    private static final Metadata.Key<String> REQUEST_ID_HEADER =
        Metadata.Key.of(
            "x-request-id",
            Metadata.ASCII_STRING_MARSHALLER);

    @Override
    public <ReqT, RespT> ServerCall.Listener<ReqT> interceptCall(
            ServerCall<ReqT, RespT> call,
            Metadata headers,
            ServerCallHandler<ReqT, RespT> next) {

        String requestId = headers.get(REQUEST_ID_HEADER);
        if (requestId == null || requestId.isBlank()) {
            return next.startCall(call, headers);
        }

        Context context = Context.current().withValue(
            REQUEST_ID_CONTEXT, requestId);
        return Contexts.interceptCall(context, call, headers, next);
    }
}
~~~

Register the interceptor on the server builder or via the customizer mechanism of the Spring gRPC starter in use. Do not assume every starter uses the same annotation or property. If request ID is mandatory, validate it and return an appropriate status; if it is only for tracing, generate a new ID when missing according to system policy.

Metadata sent by the client is untrusted data. Do not rely on a tenant ID or user ID in a header as the basis for authorization unless verified by server-side credentials and policy.

## 7. Metadata for Authentication: When to Use CallCredentials?

You can add an authorization header with a ClientInterceptor, but for dynamic tokens or credentials that need refreshing, **CallCredentials** is usually a better fit. CallCredentials provides a dedicated callback to obtain authentication metadata per call and receives security level information.

Distinction:

- Use ClientInterceptor for request IDs, trace IDs, locales, or non-secret cross-cutting metadata.
- Use CallCredentials for bearer tokens or credentials with their own lifecycle/refresh behavior.
- Use Protobuf request fields for business data.

Do not hard-code access tokens in a singleton interceptor. Do not log authorization metadata, cookies, or secrets. Only send bearer tokens over TLS; the server must still validate tokens and access permissions.

## 8. Response Metadata and Trailers

The server can send initial metadata as well as trailers when the call finishes. Initial metadata is typically sent before the response body; trailers are sent at the end to carry information such as request IDs, diagnostic codes, or auxiliary status.

Trailers should not be used to transmit critical business data that the client must treat as the primary response. Trailers may not arrive if the transport is abruptly disconnected. Use response messages for business results and gRPC status for the call's success or failure outcome.

Avoid putting stack traces, SQL, tokens, or personal data in trailers. Metadata and trailers may be logged by proxies or observability agents; include only necessary, approved information.

## 9. Metadata Limits and Security

Safety guidelines:

1. Use lowercase, ASCII key names with a custom namespace such as x-request-id.
2. Binary keys end with -bin and use BINARY_BYTE_MARSHALLER.
3. Do not place custom keys in the grpc- namespace or HTTP/2 pseudo-headers.
4. Keep metadata small; do not pass payloads or large lists in headers.
5. Validate all metadata values coming from clients before using them for authorization or routing.
6. Do not log tokens, secrets, cookies, or sensitive data.
7. Avoid writing the same key multiple times if the application expects only a single value.
8. Consider metadata size limits on proxies/servers to protect against oversized request headers.

Metadata may be filtered or transformed by proxies depending on configuration. If a header must traverse multiple hops, verify allowlist/forwarding policies on gateways and service meshes.

## 10. Testing Interceptors and Metadata

You should test these behaviors:

- Client interceptor adds x-request-id when Context holds a value.
- A header already set by the caller is preserved according to policy.
- Two concurrent RPCs do not mix up each other's request IDs.
- Server interceptor reads the header and places the value into the handler's Context.
- Binary metadata uses the proper -bin key suffix and marshaller.
- Base stub remains unchanged after withInterceptors.
- Interceptor is attached only once, avoiding duplicate headers or metrics.
- Authorization uses CallCredentials and is not logged.
- Real proxies forward required metadata while stripping disallowed headers.

You can use a gRPC in-process server/channel to verify interceptor logic and Context propagation. For TLS, proxies, or metadata filtering, integration tests over the real transport and infrastructure are required; in-process tests cannot verify gateway behavior.

## 11. Takeaways and Self-Check

**withInterceptors(...) creates a new stub with interceptors attached; Metadata carries auxiliary RPC headers and trailers.** Use interceptors to attach request IDs or tracing metadata, Context to pass per-call data, CallCredentials for dynamic credentials, and Protobuf for business data. Metadata must use the right marshaller, stay small, be validated, and avoid exposing logged secrets.

Self-check:

1. Why must an interceptor add headers inside ClientCall.start(...)?
2. How does withInterceptors(...) differ from ClientInterceptors.intercept(channel, ...) in scope?
3. Why should a request ID not be stored in a field of a shared interceptor?
4. When should you use CallCredentials instead of adding authorization via ClientInterceptor?
5. Why must binary metadata keys end with -bin?
6. Why is a tenant ID in metadata alone insufficient to authenticate a tenant?

Combining immutable generated stubs, stateless interceptors, and controlled metadata enables Spring gRPC clients to apply request context consistently, observe calls, and maintain clean boundaries between metadata, credentials, and business payloads.
