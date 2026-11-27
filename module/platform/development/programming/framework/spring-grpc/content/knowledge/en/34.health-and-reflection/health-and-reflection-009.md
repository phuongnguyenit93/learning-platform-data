# Protecting Health and Reflection

gRPC health and server reflection are two operational support services, yet they publish two different kinds of information. Health reports what state a server or service is in; reflection reports which APIs, methods, and Protobuf descriptors are registered. If both are exposed in production without access policies, unauthorized callers can probe deployment states or map out internal contracts.

In Spring gRPC, protecting these two services requires coordinating service registration, interceptors, TLS, network policies, and the platform's probing mechanism. Keep health probes operating reliably so orchestration schedules instances accurately, while restricting reflection to operators. Business RPC authentication must still be enforced independently; allowing probes to read health does not grant permission to invoke business logic.

## 1. Distinguishing health and reflection

| Service | Data published | Risk if overly exposed |
| --- | --- | --- |
| gRPC Health | SERVING, NOT_SERVING, and related status of the server/service | Leaks service existence, deployment state, outage timing, or readiness |
| Server Reflection | Services, methods, message types, and descriptors | Leaks API structure, internal methods, schemas, and system capabilities |

Health does not answer whether a caller has permission to invoke a business RPC. Reflection does not prove handlers or dependencies are working. Both services may be registered on the same server yet require separate policies:

- Health is typically needed by kubelet, load balancers, or monitoring agents.
- Reflection is typically needed only by developers, QA, or operators.
- Business RPCs require authentication and authorization by caller, service, method, and resource.

Do not apply a uniform authentication rule across all RPCs without considering how health probes are invoked. Conversely, do not exempt the entire server from checks just to let health probes run.

## 2. Health protocol: Check, Watch, and statuses

The standard gRPC health checking protocol lives in grpc.health.v1.Health. It has two main RPCs:

- Check: unary RPC, returns the current status of a service.
- Watch: server-streaming RPC, sends status and updates whenever status changes.

The request has a service field. The empty string typically represents the overall server status; a full name such as acme.orders.v1.OrderService represents a specific service. The application must update status for the exact name that probes/clients use.

Status values in health responses include:

| Status | Meaning |
| --- | --- |
| UNKNOWN | Status has not yet been determined |
| SERVING | Service can serve requests per health policy |
| NOT_SERVING | Service should not receive traffic |
| SERVICE_UNKNOWN | Status used in Watch responses when the queried service is unknown to the health manager |

For the Check RPC, an unknown service name usually results in RPC status NOT_FOUND; do not confuse this with the SERVICE_UNKNOWN enum in Watch responses.

Health status is a signal published by the application. It is trustworthy only when updated according to actual startup, readiness, and shutdown state; a fixed SERVING value set at startup does not reflect failures that occur later.

## 3. Distinguishing startup, liveness, and readiness

The platform's three probe concepts have different goals:

| Probe | Question | Action on failure |
| --- | --- | --- |
| Startup | Has the application finished initializing? | Wait longer before starting other probes |
| Liveness | Is the process still alive and able to recover on its own? | May restart the container/process |
| Readiness | Can the instance currently receive traffic? | Remove the instance from traffic until ready |

Do not use a health check that depends on all downstreams as a liveness check. If a database goes down temporarily, restarting every instance can worsen the outage. Readiness can reflect essential dependencies if the service truly cannot process requests when that dependency is unavailable; liveness should focus on unrecoverable process states.

A service may:

- Not yet be SERVING while initializing schemas/caches or loading configuration.
- Transition to NOT_SERVING when readiness is lost due to a mandatory dependency.
- Transition to NOT_SERVING when graceful shutdown begins to stop receiving new traffic.
- Return to SERVING once serving conditions are restored.

The health protocol does not itself define startup/liveness/readiness. The application, kubelet, or load balancer must define how statuses map to each probe type.

## 4. Registering and updating the health service

grpc-java provides HealthStatusManager in the grpc-services artifact. It manages status by service name and provides the health service to register on the server:

```java
import io.grpc.Server;
import io.grpc.ServerBuilder;
import io.grpc.protobuf.services.HealthStatusManager;
import io.grpc.health.v1.HealthCheckResponse.ServingStatus;

HealthStatusManager health = new HealthStatusManager();

health.setStatus("", ServingStatus.NOT_SERVING);
health.setStatus(
    "acme.orders.v1.OrderService",
    ServingStatus.NOT_SERVING);

Server server = ServerBuilder.forPort(8443)
    .addService(new OrdersService())
    .addService(health.getHealthService())
    .build()
    .start();

// After application initialization and readiness checks complete:
health.setStatus("", ServingStatus.SERVING);
health.setStatus(
    "acme.orders.v1.OrderService",
    ServingStatus.SERVING);
```

This is a grpc-java example illustrating the lifecycle; in a Spring gRPC starter, inject and register the health service via the server configuration hook supported by your starter version. Do not create a second server just to serve health, because probes might check the wrong listener that does not represent the business server.

When shutdown begins, update status to NOT_SERVING before stopping traffic acceptance and completing graceful shutdown. With multiple services on the same server, set per-service statuses rather than relying solely on overall status if they have different readiness requirements.

## 5. Separate authorization for health and reflection

A commonly used policy:

| Caller | Health Check/Watch | Reflection | Business RPC |
| --- | --- | --- | --- |
| Kubelet or probe agent | Only required methods from internal network | Deny | Grant no permissions |
| Monitoring agent | Read health for permitted services | Usually deny | Grant only if there is a specific need |
| Developer/operator | Per operational permissions | Allow in a controlled way | Role-based permissions, not automatically open to everything |
| Application client | Does not necessarily need health | Deny | Authentication/authorization per business logic |

There is often a valid reason to allow probes to access health without an application bearer token, since some built-in platform probes do not support arbitrary metadata. In that case, restrict the access path using network policies, internal listeners, and port mappings. If using a probe agent that supports TLS/credentials, still verify identity and grant read-only health access.

Reflection should require an authenticated operator identity, such as a workload identity or short-lived token, along with explicit authorization. Do not allow all application clients to download descriptors just because they can call business RPCs.

## 6. Protecting with a per-method interceptor

Health and reflection have distinct full method names. An interceptor can enforce policy based on the method descriptor:

```java
import io.grpc.*;

final class OperationsAccessInterceptor implements ServerInterceptor {
    private static final String HEALTH_CHECK =
        "grpc.health.v1.Health/Check";
    private static final String HEALTH_WATCH =
        "grpc.health.v1.Health/Watch";
    private static final String REFLECTION_V1 =
        "grpc.reflection.v1.ServerReflection/ServerReflectionInfo";

    private final OperatorAuthenticator operators;
    private final ProbeNetworkPolicy probes;

    OperationsAccessInterceptor(
            OperatorAuthenticator operators,
            ProbeNetworkPolicy probes) {
        this.operators = operators;
        this.probes = probes;
    }

    @Override
    public <ReqT, RespT> ServerCall.Listener<ReqT> interceptCall(
            ServerCall<ReqT, RespT> call,
            Metadata headers,
            ServerCallHandler<ReqT, RespT> next) {

        String method = call.getMethodDescriptor().getFullMethodName();

        if (method.equals(HEALTH_CHECK) || method.equals(HEALTH_WATCH)) {
            if (probes.isAllowed(call)) {
                return next.startCall(call, headers);
            }
            call.close(Status.PERMISSION_DENIED, new Metadata());
            return new ServerCall.Listener<>() {};
        }

        if (method.equals(REFLECTION_V1)) {
            if (operators.isAuthenticatedOperator(headers)) {
                return next.startCall(call, headers);
            }
            call.close(Status.UNAUTHENTICATED, new Metadata());
            return new ServerCall.Listener<>() {};
        }

        return next.startCall(call, headers);
    }
}
```

This is a skeleton illustrating policy, not a complete implementation. ProbeNetworkPolicy must rely on trustworthy network identity provided by the proxy/transport; do not trust caller-supplied IP headers. OperatorAuthenticator must verify tokens/certificates rather than merely checking whether a header is present.

If the server supports v1alpha reflection, add the corresponding v1alpha method path to the same policy. When using service-specific interceptors, you can wrap HealthStatusManager.getHealthService() and ProtoReflectionService individually rather than putting all branches in one global interceptor. Choose the registration approach compatible with your starter and test that the interceptor is genuinely installed on the production server.

Do not use a method-name allowlist to bypass all authentication and inadvertently permit other methods. For methods outside the health/reflection group, continue enforcing standard business authentication/authorization.

## 7. Notes for Kubernetes and built-in probes

Kubernetes native gRPC probes call the health checking protocol on the Pod's port and can pass a service name to distinguish readiness/liveness. The built-in probe mechanism does not offer bearer token metadata options or TLS client identity configuration like a general-purpose gRPC client. Therefore, if the health service is protected by mandatory auth/TLS, native probes may fail to connect.

Deployment options:

- Dedicate an internal health listener/port accessible only from the appropriate Pod/kubelet network.
- Permit only Health/Check or Health/Watch from a controlled probe path while keeping other RPCs protected.
- Use exec probes or a probe agent when TLS, credentials, or more complex verification logic are needed.
- Use network policies to restrict who can reach the health port; never expose that port through public ingress.

Verify the behavior of your deployed Kubernetes version and runtime, as well as how any service mesh/sidecar handles HTTP/2 and probe traffic. Do not assume a probe that works locally will pass production network policies.

## 8. Protecting reflection without leaking APIs

Reflection can return descriptors for all services registered on the server. If operators only need to discover a subset of services, consider:

- Disabling reflection on the public production listener.
- Registering reflection only on an internal administrative listener.
- Protecting the reflection RPC with operator identity and authorization.
- Using a gateway that permits only the reflection method path if the architecture supports secure gRPC routing.
- Using versioned descriptor sets when you do not want the server to publish reflection.

A separate administrative listener must use descriptors matching the business server's release. Do not assume a ProtoReflectionService placed on a secondary server automatically sees service definitions from another server. If duplicating service registrations, avoid accidentally exposing business RPCs on the administrative listener.

TLS/mTLS protects the wire and can verify client certificates, yet authorization must still decide which certificate identities may read descriptors. Disabling reflection also does not replace access control on business RPCs.

## 9. Health Watch, rate limiting, and log information

Watch is a stream that can remain open long-lived and receive many updates. When protecting the health service, consider:

- Limiting concurrent Watch streams per caller or probe source.
- Cancelling streams when clients disconnect/cancel and releasing resources.
- Avoiding opening a new Watch repeatedly if the probe only needs unary Check.
- Not logging every status update emitted; avoid generating huge log volume.
- Logging status transitions, caller identity, and access errors at an appropriate level.

For reflection, limit stream/request counts and audit operator access. Logs should include verified identity, endpoint, timestamp, method, allow/deny decision, and status; never log tokens, private keys, or full metadata.

Health responses can also disclose dependency state. Publish only the level of detail probes need. For example, external probes typically only need SERVING/NOT_SERVING, while database/cache details belong in internal telemetry with appropriate access control.

## 10. Combining Spring health with gRPC health

Spring Boot Actuator health and the gRPC Health protocol are two different surfaces. An application can have a HealthIndicator for databases, message brokers, or dependencies; the gRPC health manager needs to be updated according to the gRPC service's policy.

You can build an adapter in the application layer:

1. Collect results from essential dependencies using the Spring health mechanism.
2. Map results to the readiness state of each gRPC service.
3. Update HealthStatusManager at startup, when dependency state changes, and at shutdown.
4. Keep liveness policy independent of dependency health to avoid restart loops.
5. Do not include internal error details or credentials in health responses.

Do not poll every dependency aggressively just to update health. Use appropriate caching/monitoring, controlled short timeouts, and circuit breakers where needed. If health evaluation depends on a downstream RPC, avoid letting health Checks add heavy load to the very dependency experiencing an outage.

## 11. Testing health and reflection policies

Tests must verify permitted callers, rejected callers, and that business authorization is not inadvertently bypassed:

| Test case | Expected result |
| --- | --- |
| Probe from allowed network calls Health/Check | Receives accurate service status |
| Source outside allowlist calls health | Rejected or unable to connect |
| Permitted Health Watch | Receives initial status and updates when status changes |
| Watch cancelled | Stream and resources are released |
| Valid operator calls reflection | list/describe returns descriptors per policy |
| Caller without operator identity | Reflection is rejected |
| Reflection v1/v1alpha | All supported paths follow the same policy |
| Business RPC using probe identity | Still rejected by business authorization |
| Startup incomplete | Readiness does not report SERVING |
| Essential dependency lost | Readiness transitions to NOT_SERVING per policy |
| Shutdown starts | Health transitions to NOT_SERVING before server stops |
| Kubernetes native probe | Connects within actual auth/TLS/network constraints |
| Spring profile/lifecycle | Exact services are registered, updated, and stopped with the context |
| Audit/rate limit | Logs access and throttles abnormal streams |

In-process tests are suited for status transitions, method authorization, and Watch behavior. Add integration tests over TCP/TLS, network policies, or a Kubernetes staging environment to verify real probes. A unit test of an interceptor does not prove kubelet can reach the production listener.

## 12. Practice exercise

A Spring gRPC application running on Kubernetes has OrderService, InventoryService, a health service, and reflection. Kubelet needs to check readiness; a monitoring agent tracks health; operators use grpcurl to inspect descriptors during incidents. Security requires that application clients cannot read reflection or use the health identity to call business RPCs.

**Requirements:**

1. Define health status for the whole server and each service; describe when to transition SERVING/NOT_SERVING.
2. Distinguish startup, liveness, and readiness; avoid turning dependency failures into liveness failures if the process can recover.
3. Choose how Kubernetes probes access Health/Check without opening a public health endpoint.
4. Protect Health/Watch by probe network or probe identity; limit Watch streams.
5. Protect reflection with operator authentication/authorization, TLS/mTLS, and network policy.
6. Include reflection v1/v1alpha in the same access policy if the server supports both.
7. Keep business RPC authorization independent and verify the probe identity cannot call OrderService.
8. Write integration tests for status transitions, reflection allow/deny, TLS, and the Kubernetes probe path.

**Self-check questions:**

- What kinds of information do health and reflection publish?
- How does Check differ from Watch?
- How does SERVICE_UNKNOWN differ from RPC status NOT_FOUND?
- Why should liveness not depend on all downstreams?
- Why might Kubernetes native gRPC probes fail when health requires metadata/TLS client identity?
- How can probes access health without exempting business RPCs from authentication?
- Why does reflection need a separate operator policy?
- How does Spring Actuator health differ from the gRPC Health service?
- Which tests need to run on real Kubernetes/networking?

**Remember:** Protect health and reflection with two separate policies. Health must remain accessible enough for authorized probes and reflect readiness/lifecycle accurately; reflection should be restricted to operators via identity, TLS, and network controls. In Spring gRPC, register services on the proper server lifecycle, apply interceptors per method/service, keep business authorization independent, and test probes on the real production network path.
