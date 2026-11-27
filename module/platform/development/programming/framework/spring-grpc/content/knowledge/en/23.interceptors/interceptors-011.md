# Shared and Service-Specific Interceptor Configuration

In a Spring gRPC application, many RPCs share common cross-cutting processing such as authentication, tracing, metrics, correlation IDs, or audit logging. Some services or methods also have specific rules, such as business permission checks, adding tenant context, or restricting access. Interceptors let you place these concerns at the right scope without repeating them in every service implementation.

The key decision is **scope of application**: shared interceptors across the entire server or client channel; interceptors attached to only one service; or interceptors applying only to a group of stubs/methods. Choosing the right scope keeps policies consistent, avoids duplicate execution, and keeps services independent.

## 1. Configuration scopes

gRPC Java has both server-side and client-side interceptors. Each side can be applied at a broad or narrow scope:

| Scope | Server side | Client side | Suitable for |
| --- | --- | --- | --- |
| Entire server/channel | `ServerBuilder.intercept(...)` | `ManagedChannelBuilder.intercept(...)` | Tracing, metrics, correlation, shared policies |
| Single service | Wrap `ServerServiceDefinition` with `ServerInterceptors.intercept(...)` | Create a separate channel wrapper for the service's stub | Service-specific authorization or auditing |
| Group of methods | Interceptor inspects full method name and applies rules | Client interceptor inspects method descriptor | Policies intended only for selected RPCs |
| Single stub/client flow | Not a server registration scope; service policy usually fits better | `ClientInterceptors.intercept(channel, ...)` then create stub on wrapper | Headers, tenant, or telemetry for a single client flow |

Broad scopes reduce duplicate configuration and establish a consistent baseline. Narrow scopes apply specialized rules without affecting other services. You can combine them, provided you know which interceptors run on each RPC.

## 2. Shared server-side interceptors

Interceptors attached to `ServerBuilder` apply to all services registered on that server. This is the right place for concerns that should be uniform across the server, such as:

- Generating or normalizing correlation IDs.
- Putting trace context into gRPC `Context`.
- Counting requests, latency, and status codes.
- Server-wide identity authentication.
- Recording technical-level audit information.

Example using the grpc-java API:

```java
import io.grpc.Server;
import io.grpc.ServerBuilder;
import io.grpc.ServerInterceptor;

ServerBuilder<?> builder = ServerBuilder.forPort(8443);
builder.intercept(traceInterceptor);
builder.intercept(metricsInterceptor);
builder.intercept(requestContextInterceptor);

builder.addService(new OrdersService());
builder.addService(new InventoryService());

Server server = builder.build().start();
```

The three interceptors configured on the server builder establish a baseline for both `OrdersService` and `InventoryService`. Interceptors should use injected dependencies, handle each call independently, and never store request data in shared mutable fields.

Not every interceptor should be applied server-wide. For example, a rule meant only for `OrderService` should not be registered globally and then worked around with scattered exception branches when it can be configured directly at service scope. For health/reflection or internal endpoints, explicitly decide whether they are subject to global authentication/auditing or need a dedicated policy; do not accidentally lock out platform health probes.

## 3. Service-specific interceptors

When one service has dedicated rules, wrap its `ServerServiceDefinition` before registering:

```java
import io.grpc.Server;
import io.grpc.ServerBuilder;
import io.grpc.ServerInterceptors;
import io.grpc.ServerServiceDefinition;

ServerServiceDefinition ordersDefinition =
    ServerInterceptors.intercept(
        ordersService.bindService(),
        ordersAuthorizationInterceptor,
        ordersAuditInterceptor);

ServerBuilder<?> builder = ServerBuilder.forPort(8443);
builder.intercept(globalTraceInterceptor);
builder.intercept(globalMetricsInterceptor);
builder.addService(ordersDefinition);
builder.addService(inventoryService);

Server server = builder.build().start();
```

In this example, `OrdersService` has dedicated authorization and auditing; `InventoryService` receives only the global interceptors. Service-specific interceptors do not alter the configuration of other services.

This scope works well when:

- `OrderService` requires specific roles or scopes.
- A service needs finer-grained auditing because operations have financial impact.
- A service requires per-service concurrency limits or quotas.
- A service has a dedicated metadata contract, such as tenant or partner identity.

If multiple services share the same policy, you can reuse the same interceptor instance or use a factory creating per-service configurations. However, the interceptor should identify the current service/method from the call descriptor rather than inferring service identity from a Spring bean name.

## 4. Configuring shared and specific interceptors in Spring

In Spring, interceptors are commonly declared as beans for constructor injection of dependencies such as `Tracer`, `MeterRegistry`, `AuthenticationService`, or `AuditService`. Example:

```java
import io.grpc.ServerInterceptor;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
class GrpcInterceptorConfiguration {

    @Bean
    ServerInterceptor traceInterceptor(TraceService traceService) {
        return new TraceServerInterceptor(traceService);
    }

    @Bean
    ServerInterceptor metricsInterceptor(GrpcMetrics metrics) {
        return new MetricsServerInterceptor(metrics);
    }

    @Bean
    ServerInterceptor ordersAuthorizationInterceptor(
            OrdersAuthorization authorization) {
        return new OrdersAuthorizationInterceptor(authorization);
    }
}
```

This shows how to declare dependencies with Spring; attaching beans to the server or services must happen through the server configuration mechanism used by your application. If a Spring gRPC starter manages the server lifecycle, use the server customizer/configuration hook supported by that starter version. Do not spin up a second parallel `Server` just to attach interceptors, as doing so can open another port and create two independent lifecycles.

When the application bootstraps a grpc-java server manually, inject the beans into the server configuration and call `builder.intercept(...)` or wrap service definitions before `addService(...)`. Whether using a starter or manual bootstrap, centralize registration in one place so interceptor order and scope are easy to inspect.

Spring interceptor beans are singletons by default. Since the same instance can handle many concurrent RPCs, store only thread-safe dependencies and immutable configuration. Per-request data must live in local variables or gRPC `Context`, never in fields overwritten across calls.

## 5. Shared client-side interceptors

Client interceptors attached to `ManagedChannelBuilder` apply to all RPCs going through that channel. This is the right place for trace context, client metrics, user-agent, or shared technical metadata:

```java
import io.grpc.ManagedChannel;
import io.grpc.ManagedChannelBuilder;

ManagedChannel channel = ManagedChannelBuilder
    .forTarget("dns:///orders.default.svc.cluster.local:8443")
    .intercept(clientTracingInterceptor)
    .intercept(clientMetricsInterceptor)
    .useTransportSecurity()
    .build();

OrderServiceGrpc.OrderServiceBlockingStub ordersStub =
    OrderServiceGrpc.newBlockingStub(channel);
```

Every stub using this channel passes through the attached client interceptors. If the same channel is reused across multiple services, global interceptors should remain generic and avoid adding metadata valid only for one service.

Do not hardcode a user access token in a singleton interceptor if tokens vary by caller or request. Obtain credentials from per-call context/call credentials, or from a thread-safe provider capable of refreshing. Avoid leaking one request's token into another request when a channel is shared concurrently.

## 6. Stub-specific or RPC-group interceptors

If only one client flow needs specific headers or telemetry, wrap the channel with `ClientInterceptors.intercept(...)` and build the stub on that wrapper:

```java
import io.grpc.Channel;
import io.grpc.ClientInterceptors;

Channel ordersOnlyChannel = ClientInterceptors.intercept(
    sharedChannel,
    ordersTenantInterceptor,
    ordersClientAuditInterceptor);

OrderServiceGrpc.OrderServiceBlockingStub ordersStub =
    OrderServiceGrpc.newBlockingStub(ordersOnlyChannel);

InventoryGrpc.InventoryBlockingStub inventoryStub =
    InventoryGrpc.newBlockingStub(sharedChannel);
```

In this example, only `ordersStub` uses the wrapped channel and receives the dedicated interceptors; `inventoryStub` continues using the shared channel. Both can still share the underlying transport/channel depending on how the wrapper is constructed.

An interceptor attached to a channel wrapper can inspect the method descriptor to apply only to selected methods. This is helpful when a service has multiple RPCs with different policies, though you should use a clear rule table instead of scattered string conditions.

## 7. Filtering by service and method

On the server, the method descriptor provides the full method name so the interceptor can identify the current RPC:

```java
import io.grpc.*;

final class OrdersAuthorizationInterceptor
        implements ServerInterceptor {

    private final OrdersAuthorization authorization;

    OrdersAuthorizationInterceptor(OrdersAuthorization authorization) {
        this.authorization = authorization;
    }

    @Override
    public <ReqT, RespT> ServerCall.Listener<ReqT> interceptCall(
            ServerCall<ReqT, RespT> call,
            Metadata headers,
            ServerCallHandler<ReqT, RespT> next) {

        String method = call.getMethodDescriptor()
            .getFullMethodName();

        if (method.equals("acme.orders.v1.OrderService/CancelOrder")
                && !authorization.mayCancel(headers)) {
            call.close(
                Status.PERMISSION_DENIED
                    .withDescription("Not allowed to cancel this order"),
                new Metadata());
            return new ServerCall.Listener<>() {};
        }

        return next.startCall(call, headers);
    }
}
```

This snippet demonstrates blocking a method before forwarding the call to the service handler. In a real implementation, `mayCancel(...)` must verify an authenticated identity/credential; never trust a self-asserted tenant or user ID header sent by the caller. Use `Context` to pass the authenticated principal from an authentication interceptor to the authorization interceptor.

Full method names in grpc-java have the form `package.Service/Method`, typically without a leading `/`. HTTP/2 paths include a leading `/`. Use the exact format expected when matching or configuring rules.

For complex policies, prefer mapping the method descriptor to a policy object or startup-validated annotations/configuration. Avoid substring matching on method names, which can accidentally match unintended services or versions.

## 8. Interceptor ordering and composition

Interceptors compose into a processing chain around an RPC. Order affects:

- Whether authentication runs before authorization.
- Whether trace context is available when metrics/auditing record a call.
- Which layer translates exceptions into gRPC `Status`.
- Whether metadata is normalized or stripped before another interceptor reads it.
- Whether rejected calls are recorded by auditing/metrics.

For example, a server chain typically needs responsibilities ordered as: trace/context → authentication → authorization → audit/metrics → service handler. This is the logical target order; actual callback execution order also depends on how builders and wrappers compose interceptors in your grpc-java version. Verify with tests recording before/after order rather than guessing from declaration order.

Avoid registering the same interceptor both server-globally and service-specifically unless intentional. A single request could be metered twice, audited twice, or have metadata processed repeatedly. If an interceptor must run at multiple scopes, define each instance's responsibility clearly and test execution counts.

## 9. Safe error, metadata, and Context handling

Interceptors are generally the right place to:

- Read inbound metadata such as trace IDs or credentials.
- Authenticate credentials and build a trusted principal.
- Place the verified principal, tenant, or trace context into `io.grpc.Context`.
- Count metrics and audit records by call outcome.
- Close calls with an appropriate status when rejected.

Key guidelines:

- Do not trust `x-user-id`, `x-role`, or `x-tenant-id` merely because they appear in metadata.
- Do not log authorization headers, tokens, cookies, or sensitive data.
- Return statuses like `UNAUTHENTICATED` for missing/invalid credentials and `PERMISSION_DENIED` for valid principals lacking permission.
- Keep metadata small; never send large business objects in headers.
- Ensure Context stays scoped to the call and does not leak to other threads/requests.
- For streaming RPCs, handle listener/callback lifecycles and async errors, not just call startup.

Interceptors should not contain business logic such as pricing, order state transitions, or repository calls to complete use cases. Those belong in the service/application layer.

## 10. Common configuration mistakes

| Symptom | Possible cause | Fix |
| --- | --- | --- |
| Interceptor never runs | Bean created but not attached to server/channel | Check registration hooks and builder scope |
| Other services also blocked | Service-specific policy registered globally | Move to service-specific or method-specific scope |
| Audit/metrics doubled | Same interceptor attached at multiple scopes | Inspect chain and remove duplicate registration |
| One service's headers appear on another | Using channel-wide interceptor for service-specific metadata | Create a dedicated channel wrapper or check method |
| User/tenant mixed across requests | Storing request state in mutable singleton field | Use local variables and gRPC `Context` |
| Health probe gets `UNAUTHENTICATED` | Global auth blocks health service | Design an explicit allowlist or probe credentials |
| Authorization misbehaves | Wrong service name or full method format | Check descriptor and `getFullMethodName()` |
| Wrong execution order | Assuming declaration order equals callback order | Write tests confirming the actual chain |

## 11. Testing interceptor scope

Tests should prove both that the interceptor applies where intended and that out-of-scope services remain unaffected:

| Test case | Expected result |
| --- | --- |
| Server-global interceptor | Runs for every service registered on the server |
| Service-specific interceptor | Runs only for the wrapped service |
| Method-specific rule | Only methods matching the full method name receive the policy |
| Client channel interceptor | Runs for every stub/call over the channel |
| Client stub wrapper | Only stubs using the wrapper receive the dedicated interceptor |
| Authentication before authorization | Authorization reads the authenticated principal |
| Permission denial | Call returns the right status and audit/metrics record per policy |
| Health/reflection | Probes/ops tools work per designed allowlist |
| Concurrent calls | No metadata or principal leaks across requests |
| Streaming call | Context and cleanup stay accurate across the entire lifecycle |
| No duplicate registration | Metrics/audits are not recorded twice |

You can use an in-process server/channel to verify interceptor scope and ordering. Add integration tests with real transport when you need to verify TLS, metadata through proxies, or starter-created client channels. With Spring, verify that the ApplicationContext creates only the intended beans and that configuration hooks genuinely attach them to the server/channel.

## 12. Practice exercise

A Spring gRPC application has `OrderService`, `InventoryService`, and a health service. All require tracing and metrics. `OrderService` needs role-based authorization; `CancelOrder` specifically needs detailed auditing. Clients share a single channel for both Orders and Inventory, but only Orders requires tenant metadata.

**Requirements:**

1. Choose server-global interceptors for tracing/metrics.
2. Attach dedicated authorization to `OrderService` and dedicated auditing to `CancelOrder`.
3. Decide whether the health service falls under the global authentication policy or uses an allowlist/probe credential.
4. Attach shared tracing/metrics to the client channel; create a channel wrapper for `OrderService` to add tenant metadata.
5. Define how the authenticated principal propagates through gRPC `Context`.
6. Verify singleton interceptors are thread-safe and hold no per-request state in fields.
7. Write tests confirming scope, ordering, no duplicate registration, and no tenant leakage between the two stubs.

**Self-check questions:**

- When should you use `ServerBuilder.intercept(...)` vs. `ServerInterceptors.intercept(...)`?
- How does a channel-attached client interceptor differ from one attached only to a single stub's channel wrapper?
- Why must shared interceptors be thread-safe?
- How do you apply a policy to a single method?
- Why shouldn't you trust a user/tenant ID purely from metadata?
- How does interceptor order affect authentication, authorization, and auditing?
- How do you prevent an interceptor from running twice due to duplicate configuration?
- When should logic live in an interceptor vs. the service layer?

**Takeaway:** Shared interceptors establish a baseline for a server or channel; dedicated interceptors restrict policies to the service, method, or stub that needs them. In Spring gRPC, declare interceptors with dependency injection but attach them through the proper server or channel lifecycle/configuration hook. Clearly define scope, ordering, thread safety, and metadata policies; test both where an interceptor must run and where it must not.
