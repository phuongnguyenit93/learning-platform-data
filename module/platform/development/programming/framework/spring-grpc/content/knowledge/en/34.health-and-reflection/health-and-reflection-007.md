# Restricting Reflection in Production

Server reflection allows operational tools to discover the services, methods, and Protobuf descriptors published by a gRPC server. This feature is useful during development and troubleshooting, yet descriptors also reveal internal API structures, administrative method names, and data types supported by the system. Production requires an explicit decision: disable reflection if unnecessary, or permit only authenticated operators to access it over a controlled connection.

In Spring gRPC, the policy must be enforced on the actual server serving RPCs, aligned with the application's profiles and lifecycle. Three layers must be distinguished: TLS protects the connection and authenticates the server; authentication/authorization decides who may read descriptors; network/gateway policy restricts where reflection can be called from. Enabling TLS alone does not mean reflection is protected.

## 1. What information surface does reflection expose?

Reflection publishes descriptors of services registered on the server. Callers can discover:

- Package names and fully qualified service names.
- RPC methods, input types, and output types.
- Messages, field numbers, field types, enums, and nested messages.
- Dependent descriptor files needed to decode the contract.
- Internal services or administrative methods if they are registered on the same server.

This information does not itself contain request data, database records, or credentials. However, administrative method names, message structures, and API versions can help outsiders map the system and craft targeted requests. Therefore, reflection is an information surface that requires governance even though it executes no business logic itself.

Reflection also does not automatically grant permission to invoke discovered services. A caller may read descriptors and still be rejected by business RPC authorization; conversely, disabling reflection does not protect a method if the endpoint still allows callers to invoke it directly. The two policies must be designed independently.

## 2. Choosing policy by environment

There is no need to enable reflection in every environment:

| Environment | Typical appropriate policy | Reason |
| --- | --- | --- |
| Local development | Enable | Supports grpcurl, IDEs, and fast debugging |
| CI/integration test | Enable on test servers | Verifies descriptors and service registration |
| Staging | Enable in a controlled way | QA/operators can verify APIs after deployment |
| Public-facing production | Disable if there is no operational need | Avoids exposing internal schemas on a public surface |
| Internal production | Allow access for authorized operators only | Supports controlled diagnostics and contract verification |

If production does not need reflection, do not register the reflection service on the production server. This is the most direct way to reduce the API surface. If needed for operations, enable it conditionally and require appropriate identity, authorization, network restrictions, and auditing.

Do not rely on ordinary tools not calling reflection by default. Any client that knows the reflection protocol and can reach the endpoint can send requests if the server allows it.

## 3. Toggling with controlled configuration

Define an application-managed property to decide whether reflection is registered:

```yaml
# application-local.yml
app:
  grpc:
    reflection:
      enabled: true

---
# application-prod.yml
app:
  grpc:
    reflection:
      enabled: false
```

This is an example application property, not a standard property name shared across all Spring gRPC starters. When the starter manages the server automatically, use a conditional bean or server customizer supported by your exact starter version; verify that the bean is registered on the actual production server. If the application creates its server manually with grpc-java, add the reflection service only when the property allows it.

Example with a directly bootstrapped server:

```java
import io.grpc.Server;
import io.grpc.ServerBuilder;
import io.grpc.protobuf.services.ProtoReflectionService;

ServerBuilder<?> builder = ServerBuilder.forPort(8443)
    .addService(new OrdersService())
    .addService(new InventoryService());

if (reflectionEnabled) {
    builder.addService(ProtoReflectionService.newInstance());
}

Server server = builder.build().start();
```

Do not create a second server outside the Spring lifecycle just to enable reflection. That can open an extra port, use different TLS/authentication settings, and make production configuration harder to control. Keep business services and reflection under the lifecycle, transport, and shutdown policy managed by the application.

## 4. Protecting reflection with authentication and authorization

The reflection protocol uses a bidirectional streaming RPC. An interceptor can inspect identity at the call level and allow only operators to access the reflection service. In grpc-java, you can wrap the service definition separately:

```java
import io.grpc.Server;
import io.grpc.ServerBuilder;
import io.grpc.ServerInterceptors;
import io.grpc.ServerServiceDefinition;
import io.grpc.protobuf.services.ProtoReflectionService;

ServerServiceDefinition reflectionDefinition =
    ServerInterceptors.intercept(
        ProtoReflectionService.newInstance().bindService(),
        operatorAuthorizationInterceptor);

Server server = ServerBuilder.forPort(8443)
    .addService(new OrdersService())
    .addService(new InventoryService())
    .addService(reflectionDefinition)
    .build()
    .start();
```

This is a grpc-java example for a self-configured server. In Spring gRPC, place similar logic into the starter's server customizer/registration hook or configure the service definition before registration. If the starter auto-registers every BindableService bean, verify how to apply an interceptor specifically to reflection using your version's API.

Reflection is a distinct service with methods such as /grpc.reflection.v1.ServerReflection/ServerReflectionInfo; v1alpha-compatible implementations may use the corresponding method path in the v1alpha package. Call-level authorization on reflection typically allows or denies the entire discovery stream. If you need to publish only a subset of descriptors, you must use a reflection implementation that filters descriptors or a custom discovery service; checking only the reflection RPC name is not enough to filter individual services queried inside the payload.

Authentication must verify actual credentials, such as an operator token or workload identity. Never trust roles, user IDs, or tenants self-asserted by the caller in metadata without verification. If the authentication dependency is unavailable, fail closed for reflection rather than temporarily opening access.

## 5. TLS, mTLS, and network restrictions

TLS protects reflection traffic in transit and helps clients verify the server via its certificate. mTLS adds client certificate verification, yet the server still needs authorization to decide which certificate identities are permitted to read descriptors.

A grpcurl command over TLS can use a trusted CA:

```bash
grpcurl -cacert operator-ca.pem \
  orders.internal.example:8443 \
  list
```

If the listener requires mTLS, supply the client certificate and private key:

```bash
grpcurl -cacert operator-ca.pem \
  -cert operator-client.pem \
  -key operator-client-key.pem \
  orders.internal.example:8443 \
  list
```

The connecting hostname must match a SAN in the certificate or an intentionally configured authority override. Never use plaintext, disable hostname verification, or accept untrusted certificates to work around configuration errors.

Network policy should restrict access sources for reflection:

- Allow access only from operator networks, bastions, or designated administrative workloads.
- Use ingress/gateway allowlists by identity and RPC path if the gateway supports gRPC.
- Do not route reflection on public listeners if only internal administration is needed.
- Restrict egress/ingress between operational tools and servers to the exact port.
- Keep business RPC authorization independent, even when reflection is exposed only internally.

If using a gateway to block reflection, check both v1 and v1alpha reflection paths supported by servers/tools. Do not block only one package version and inadvertently leave another variant open.

## 6. Separating an administrative endpoint when needed

Some systems need reflection in production without exposing it on the public listener. You can design a dedicated internal administrative endpoint under these conditions:

1. The administrative listener binds only to an internal network/interface and is never published on public ingress.
2. Transport uses dedicated TLS/mTLS and trust material suited to operators.
3. Reflection is registered only on the administrative listener.
4. Published service descriptors must come from the exact same contract/version as the business server.
5. Lifecycle, port, readiness, shutdown, and monitoring of the administrative listener are explicitly managed.

Depending on architecture, the administrative listener may need a shared reflection registry/descriptor source or a matching set of service definitions. Do not assume a reflection service placed on a secondary server automatically knows the descriptors of another business server. Inspect the service list and descriptions on the administrative endpoint to ensure it returns the actual running services.

If duplicating service registrations accidentally exposes business RPCs on the administrative listener, use a gateway/proxy allowing only reflection methods or an appropriate descriptor-only implementation. Review access paths separately and do not let the administrative endpoint become an uncontrolled clone of the public server.

## 7. Do not confuse reflection authorization with business authorization

Reflection tells callers that a method exists and what request/response types it uses. It does not grant permission to invoke that method. Every business RPC must still verify identity and permissions on the server:

| Surface | Required policy |
| --- | --- |
| Reflection service | Who may list services and download descriptors? |
| Business service | Who may call each service/method and on which resources? |
| Health service | Which probes may read status and what status is published? |
| Admin RPC | Which operators may perform administrative actions? |

Do not treat disabled reflection as proof that an API is secured. Clients can invoke methods using generated stubs or existing descriptor sets. Authorization must reside on each RPC or service/method group per the security contract.

Similarly, do not open the entire server to operators just because they need to read reflection. If operators only need descriptors, restrict access to the reflection service and keep business/admin RPC invocation governed by least privilege.

## 8. Auditing, logging, and rate limiting

Reflection is frequently used during incident investigations, CI, and automation. Log enough for traceability without storing sensitive data:

- Authenticated identity and network origin of the operator.
- Timestamp, endpoint, and environment accessed.
- Reflection protocol version and operation type if telemetry can distinguish them.
- Allow/deny decision and final status.
- Correlation ID or trace ID to link with gateway audit logs.

Never log access tokens, private keys, full metadata, or sensitive payloads. A reflection stream can send many consecutive requests; apply appropriate rate limits/concurrency limits to prevent a single client from generating unnecessary load. Rate limits should be keyed by operator identity or trusted source, not solely by IP if multiple operators share NAT.

Alert on reflection access from outside allowlists, sudden spikes in denials, or production reflection being enabled outside expected configuration. Enabling reflection should be a reviewed, auditable configuration change.

## 9. Fallback when reflection is disabled

Disabling reflection does not stop operations teams from verifying contracts. You can distribute descriptor sets built and versioned alongside releases:

```bash
grpcurl -cacert operator-ca.pem \
  -protoset orders-release.protoset \
  orders.internal.example:8443 \
  acme.orders.v1.OrderService/GetOrder
```

Or use proto files and an import path:

```bash
grpcurl -cacert operator-ca.pem \
  -import-path ./proto \
  -proto orders.proto \
  orders.internal.example:8443 \
  describe acme.orders.v1.OrderService
```

Descriptor sets should be produced in the build pipeline, stored alongside artifact/release metadata, and include version/checksum information. They let tools use reviewed contracts without requiring the server to publish reflection. However, a descriptor set only describes that build's contract; check release versions to avoid applying an outdated schema to a newer server.

If you need to verify a live API while reflection is disabled, use health/metrics and authorized smoke RPCs, or run checks against a staging environment with controlled reflection. Do not temporarily enable public reflection just for the convenience of a one-off debug session.

## 10. Spring configuration and profile verification

With Spring, manage reflection as a conditionally configured feature. Example properties:

```yaml
app:
  grpc:
    reflection:
      enabled: false
      operator-only: true
```

operator-only here is an application-defined property controlling how reflection is registered/protected, not a standard property across all starters. The application should validate startup configuration: if reflection is enabled without TLS or an operator authorization bean, fail startup instead of silently opening access.

A startup checklist:

- Does the active profile match the deployment environment?
- Is reflection registered if and only if policy permits?
- Are interceptors/operator identity attached to the reflection service?
- Does the listener use TLS/mTLS and the right trust material?
- Does the gateway/network policy restrict reflection paths?
- Are auditing and rate limiting enabled?
- Does shutdown stop the reflection listener and related resources?

If using a Spring gRPC starter, write integration tests against the actual server created by the starter. A test that builds its own standalone ServerBuilder only proves grpc-java configuration; it does not prove Spring's conditional beans or customizers ran.

## 11. Testing reflection security in production

Tests should verify both permitted configurations and forbidden access paths:

| Test case | Expected result |
| --- | --- |
| Production reflection disabled | Reflection method is not registered or is blocked by gateway |
| Local/staging reflection enabled | Test operator can list and describe |
| Missing credentials | Reflection is rejected |
| Invalid/expired token | Rejected without leaking credential details |
| Valid identity without operator role | PERMISSION_DENIED |
| Valid operator over TLS | Can read descriptors per policy |
| Untrusted client certificate | TLS handshake fails |
| Call via public ingress | Reflection unreachable if policy requires internal-only |
| Reflection v1/v1alpha | All server-supported paths obey the same policy |
| Unauthorized business RPC | Still rejected even if the caller can read descriptors |
| Descriptor fallback | Release-matched protoset works when reflection is disabled |
| Spring profile switch | Server registers exact services per profile with no unintended extra listener |
| Audit/rate limit | Logs identity/status properly and throttles abnormal streams/requests |

After each deploy, you can run a smoke test from the operator network: verify the production endpoint does not publicly expose reflection, the admin endpoint requires identity, and returned descriptors match the release. At the same time, verify that an unauthorized business RPC is still rejected.

## 12. Practice exercise

A Spring gRPC service runs on Kubernetes. The development team wants to use grpcurl to inspect staging; production hosts internal services such as AdminService and OrderService. Security requires that only operators over mTLS may view descriptors, while application callers may only invoke business methods according to their role.

**Requirements:**

1. Propose profiles/configuration to enable reflection in local/staging and disable it on the public production listener.
2. If production requires reflection, design an internal administrative endpoint and ensure the descriptor source stays synchronized with the business server.
3. Attach separate authorization to the reflection service; distinguish operator permissions from permissions to invoke AdminService/OrderService.
4. Configure TLS/mTLS, SANs, trust chain, and network allowlists.
5. Identify the reflection v1/v1alpha paths that the gateway must control.
6. Design auditing, rate limiting, and alerts for unauthorized access.
7. Generate a descriptor set in the build pipeline for use when reflection is disabled.
8. Write integration tests under the production profile to verify reflection is not public, operator access works, and business authorization remains independent.

**Self-check questions:**

- What kinds of information does reflection reveal and why can it aid reconnaissance?
- Why does TLS not replace authentication/authorization?
- How does call-level reflection authorization differ from filtering descriptors by service?
- Why does disabling reflection not mean business RPCs are secure?
- When is a dedicated administrative endpoint needed, and what must be watched regarding descriptor sources?
- How do you protect both reflection v1 and v1alpha at the gateway?
- How do descriptor sets aid operations when reflection is disabled?
- Which tests prove production does not inadvertently expose reflection publicly?

**Remember:** Production should disable reflection unless needed; if needed, grant access only to operators via TLS/mTLS, authentication, authorization, and network policy. Protect the reflection service separately, keep business RPC authorization independent, audit access, and control every supported protocol path. In Spring gRPC, manage registration via profiles/lifecycle, test against the real starter-created server, and version descriptor sets as the contract discovery fallback when reflection is closed.
