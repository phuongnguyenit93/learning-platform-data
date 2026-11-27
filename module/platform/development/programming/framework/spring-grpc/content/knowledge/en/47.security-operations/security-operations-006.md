# Restricting Service Reflection

gRPC Server Reflection is a protocol that allows clients to discover the services and Protobuf descriptors exposed by a server. Tools like `grpcurl`, `grpcui`, and some IDEs use reflection to list services, inspect method/request/response schemas, and invoke test RPCs without requiring the user to supply `.proto` files beforehand. While helpful for development, debugging, and operations, this capability also exposes internal API structure to any peer able to reach the reflection endpoint.

In Spring gRPC, you must explicitly decide which environments enable reflection, who is allowed to access it, and which descriptors are exposed. Filtering only the service list is insufficient to restrict schema exposure: reflection also supports querying descriptors by symbol, filename, and extension. For sensitive APIs, prefer disabling reflection in production or isolating it on a separate admin listener protected by mTLS and authorization.

## 1. What Information Does Service Reflection Expose?

Server Reflection lets clients discover APIs over a streaming RPC. The protocol has common versions such as `v1` and `v1alpha`; clients/tools must use a version supported by the server.

Information reflection can return includes:

- List of services registered on the server.
- Full names of services and methods.
- Request/response message types of each method.
- Protobuf file descriptors containing messages, fields, enums, services, methods, and import dependencies.
- Extension metadata declared by descriptors.

Descriptors reveal message structure, field numbers, types, cardinality, enum values, and method signatures. While this does not directly leak runtime data or bypass business RPC authorization, it helps attackers map the API surface, resource names, internal conventions, and target methods to probe.

Do not assume `.proto` schemas are top-secret. Even so, if schemas contain internal details or unpublished APIs, treat reflection as an administrative endpoint and apply commensurate access controls.

## 2. Reflection Operates as Its Own RPC

In `grpc-java`, reflection is typically provided by `ProtoReflectionService` in the `grpc-services` artifact. Clients send reflection requests over a bidirectional-streaming method:

```text
grpcurl / grpcui
      |
      | ServerReflectionInfo stream
      v
gRPC server listener
      |
      v
Reflection access interceptor
      |
      v
ProtoReflectionService
      |
      +--> list services
      +--> file containing symbol
      +--> file by filename
      +--> extension queries
      |
      v
FileDescriptorProto responses
```

Common full method names:

- `grpc.reflection.v1.ServerReflection/ServerReflectionInfo`
- `grpc.reflection.v1alpha.ServerReflection/ServerReflectionInfo`

These are reflection methods, not business methods like `OrderService/GetOrder`. Because reflection uses a stream, a client can send multiple types of descriptor queries within a single RPC. Access control must cover the entire stream; if policy filters by individual descriptor request, each message in the stream must be inspected.

## 3. Risks of Broadly Enabling Reflection

Reflection can help outsiders:

- Enumerate internal services and methods absent from public documentation.
- Discover request/response schemas and field names.
- Uncover administrative, debug, or deprecated legacy APIs still registered.
- Identify messages, enums, or extensions tied to business workflows.
- Craft structurally valid requests to probe for authorization or validation bugs.

Reflection alone does not grant permission to invoke business RPCs. Each method still requires independent authentication and authorization. However, schema discovery lowers reconnaissance cost and helps attackers target specific methods or payloads.

Do not rely on hiding service names as a security measure. Real protection must come from authentication, authorization, network boundaries, and not registering unnecessary services.

## 4. Environment-Based Policy

A practical baseline policy:

| Environment | Reflection Policy | Purpose |
| --- | --- | --- |
| Local development | May be enabled | Supports `grpcurl`/`grpcui` and debugging |
| Automated test | Enabled in isolated test servers | Verifies descriptors and client tooling |
| Shared development | Enabled under control | Authenticated developers/workloads only |
| Staging | Disabled by default or restricted like production | Prevents staging from becoming a schema leak source |
| Production | Disabled on public listeners; if needed, open only on admin boundary | Minimizes API discovery surface |

Do not use a configuration with reflection enabled across all profiles and hope network firewalls will always block it properly. Profile/deployment configurations must be tested to ensure production artifacts do not accidentally register reflection.

If production support temporarily needs reflection, require change approval, an automatic expiration, verified operator identity, access auditing, and a plan to disable it after the session.

## 5. Registering ProtoReflectionService in grpc-java

Example of adding the reflection service to a `grpc-java` server:

```java
import io.grpc.Server;
import io.grpc.ServerBuilder;
import io.grpc.protobuf.services.ProtoReflectionService;

Server server = ServerBuilder.forPort(9090)
    .addService(new OrdersService())
    .addService(ProtoReflectionService.newInstance())
    .build()
    .start();
```

The artifact containing `ProtoReflectionService` is `grpc-services`, and its version must align with `grpc-java` core. This example illustrates a standalone server; in Spring gRPC, register the service through the extension point supported by your starter.

Do not register the reflection service in production merely for `grpcurl` convenience. If reflection is required for production support, place it on a dedicated admin server/listener or wrap the service with an interceptor requiring operator identity.

## 6. Protecting Reflection with a Server Interceptor

You can wrap the reflection service with a `ServerInterceptor` to allow only authenticated callers holding an operational role:

```java
import io.grpc.Metadata;
import io.grpc.ServerCall;
import io.grpc.ServerCallHandler;
import io.grpc.ServerInterceptor;
import io.grpc.ServerServiceDefinition;
import io.grpc.ServerInterceptors;
import io.grpc.Status;

final class ReflectionAccessInterceptor implements ServerInterceptor {
    private final ReflectionAuthorizer authorizer;

    ReflectionAccessInterceptor(ReflectionAuthorizer authorizer) {
        this.authorizer = authorizer;
    }

    @Override
    public <ReqT, RespT> ServerCall.Listener<ReqT> interceptCall(
            ServerCall<ReqT, RespT> call,
            Metadata headers,
            ServerCallHandler<ReqT, RespT> next) {

        boolean allowed =
            authorizer.isOperator(headers, call.getAttributes());
        if (!allowed) {
            call.close(
                Status.PERMISSION_DENIED
                    .withDescription("reflection access denied"),
                new Metadata());
            return new ServerCall.Listener<>() {};
        }
        return next.startCall(call, headers);
    }
}

ServerServiceDefinition protectedReflection =
    ServerInterceptors.intercept(
        ProtoReflectionService.newInstance(),
        new ReflectionAccessInterceptor(reflectionAuthorizer));

Server server = ServerBuilder.forPort(9090)
    .addService(new OrdersService())
    .addService(protectedReflection)
    .build()
    .start();
```

`ReflectionAuthorizer` is an application abstraction: it must verify authenticated credentials or peer identity, then check the operational role/policy. Never trust a self-asserted header like `x-operator: true` sent by the caller. With mTLS, you can bind the transport certificate identity to an operator identity, though a valid certificate does not automatically mean the caller is permitted to read schemas.

This example blocks the entire reflection stream if the caller lacks permission. It does not filter individual descriptors; an authorized caller opening the stream can send any reflection query supported by the implementation. If specific symbols/files must be restricted, use a reflection implementation/filter with full request and response control.

## 7. Why Allowlisting list_services Alone Is Insufficient

The reflection protocol includes more than the service listing request. Key queries include:

| Request Type | Purpose |
| --- | --- |
| `list_services` | Lists registered services |
| `file_containing_symbol` | Retrieves the descriptor file containing a symbol |
| `file_by_filename` | Retrieves a descriptor by filename |
| `all_extension_numbers_of_type` | Lists extension numbers for a message type |
| `file_containing_extension` | Finds the descriptor containing an extension |

If a custom filter only strips a service from the `list_services` response, clients can still query `file_containing_symbol` or `file_by_filename` to retrieve descriptors. Moreover, a single `.proto` file may define multiple services/messages; allowing one service may inadvertently expose other symbols in the same file.

Descriptor files can also reference dependencies. When returning a descriptor for a symbol, reflection usually must supply dependency files so the client can decode the schema. Therefore, an allowlist by service name does not automatically equate to an allowlist over the descriptor graph.

If a restricted schema subset must be published, control every request type, symbol, filename, extension query, and dependency closure, and inspect response contents. A simpler and safer approach is usually splitting sensitive `.proto` definitions into separate files/packages or using a separate listener registering only the services intended for publication.

## 8. Separating Admin and Business Listeners

When operators need reflection in production, separating the admin endpoint reduces exposure to regular clients:

```text
Public gRPC listener
  - business services
  - normal authentication/authorization
  - reflection disabled

Private admin listener
  - reflection service
  - mTLS required
  - operator authorization
  - network ACL / VPN / bastion
  - access audit and short-lived enablement
```

The admin listener should have its own port, firewall rules, DNS/service discovery, and certificates. Never expose the admin listener through a public ingress. Restrict access sources at the network layer, then still authenticate and authorize at the gRPC layer; network ACLs do not replace identity.

If using a service mesh or ingress that terminates TLS, clearly determine where mTLS terminates and which identity is forwarded. A service may trust forwarded identity only when the proxy-to-service hop is authenticated and external callers cannot spoof headers.

## 9. Restricting Reflection by Role and Method

Use dedicated roles such as `SCHEMA_READ` or `PLATFORM_OPERATOR` instead of granting reflection to every authenticated workload. Policy should answer:

- Which role may list services?
- Which role may retrieve descriptors?
- Are any services strictly forbidden from publication?
- Must access be scoped by environment/tenant?
- Is access time-bounded and who approves it?
- Does reflection access generate audit events?

Because reflection is a bidirectional stream, call-level interceptor authorization only decides whether a caller can open the stream. If different policies are needed per descriptor query within the same stream, use a wrapper/filter inspecting each request message; you cannot check once in `interceptCall` and claim symbol-level allowlisting is enforced.

Do not return partial descriptors in a way that breaks the dependency graph. If responses are filtered, clients may fail to resolve types and tooling will report incomplete schemas. Test with real clients/tools across all expected query paths.

## 10. Configuring Reflection in Spring gRPC

In Spring, how `BindableService` or `ServerServiceDefinition` is registered depends on the starter and version. Some starters auto-detect service beans, while others require a server customizer or registration hook. Therefore:

1. Identify the exact service registration extension point of your starter.
2. Gate registration by profile/property so reflection is registered only in permitted environments.
3. If using an interceptor, verify it actually wraps the reflection service rather than merely being declared as a bean.
4. Probe the actual server listener from a test environment to confirm whether reflection is registered.
5. Ensure the production profile does not accidentally activate local/test configuration.

Do not assume beans implementing `BindableService` are automatically registered by every Spring gRPC starter. Nor assume global interceptors apply identically to business services and the reflection service; verify the actual chain.

If the admin listener is a separate server, manage its lifecycle, TLS material, health/readiness, and shutdown independently. Do not reuse the public channel merely for configuration convenience.

## 11. Testing with grpcurl and Integration Tests

`grpcurl` can verify reflection by listing services and describing descriptors:

```bash
grpcurl -plaintext localhost:9090 list
grpcurl -plaintext localhost:9090 describe acme.orders.v1.OrderService
```

These two commands are for non-TLS local/test environments only. With TLS, provide the appropriate CA and target hostname; with mTLS, add client certificate/key per tool flags. Never disable certificate verification to make tests pass.

Test matrix:

| Test Case | Expected Outcome |
| --- | --- |
| Reflection disabled | Client cannot list/describe via reflection |
| Valid operator | Accesses only policy-permitted listener/descriptors |
| No credentials | Rejected before receiving descriptors |
| Valid identity lacking role | `PERMISSION_DENIED` |
| Descriptor request outside allowlist | Rejected or omitted per policy |
| Querying file with multiple symbols | Does not leak out-of-scope symbols |
| Descriptor dependencies | Returns only required dependencies, none outside policy |
| `v1` and `v1alpha` | Exposes only approved versions |
| Production profile | Reflection not registered on public listener |
| Admin listener | Reachable only from permitted network/operator identities |
| Audit | Events emitted for allow/deny access |

Beyond `grpcurl`, write integration tests using a generated reflection client or equivalent tool to exercise every request type, especially when custom-filtering descriptors. A test running only `list_services` does not prove `file_by_filename` or `file_containing_symbol` are restricted.

## 12. Monitoring and Temporary Enablement Procedures

Monitor:

- Number of open reflection streams by identity and network source.
- Reflection query types requested.
- Denial counts and TLS/authentication failures.
- Whether admin listeners/endpoints ever appear on public ingress.
- Timestamps when reflection is enabled/disabled and the approver.

When temporary reflection enablement is needed:

1. Create a change/incident record and identify the operator.
2. Grant short-lived access via mTLS/role.
3. Open only the admin listener or restricted policy.
4. Audit each stream and relevant queries.
5. Disable reflection or revoke permissions when the window expires.
6. Verify externally that the endpoint is no longer reachable.

Do not rely on an operator closing `grpcurl` to assume a stream ended; the server needs appropriate idle/maximum stream durations and cancellation handling.

## 13. Applied Exercise

`OrderService` and `PaymentService` run on the same Spring gRPC server. The `Payment` schema contains internal admin methods; operations needs `grpcurl` to debug `OrderService` in staging and occasionally in production.

**Tasks:**

1. Define which environments enable reflection and which listeners expose it.
2. Register `ProtoReflectionService` via the starter's extension point.
3. Protect reflection with mTLS and the `SCHEMA_READ` role.
4. Write tests proving unauthenticated and authenticated-without-role callers are rejected.
5. Test `list_services`, `file_containing_symbol`, and `file_by_filename`.
6. Assess the risk of `OrderService` and `PaymentService` sharing one `.proto` file.
7. If descriptor restriction is required, design an allowlist covering dependency closure and all request types.
8. Write a Spring context test for registration/interceptor chaining and a `grpcurl` test for the staging/admin listener.
9. Establish a procedure for temporary enablement, auditing, and automatic disablement after debugging sessions.

**Self-check questions:**

- Which types of descriptors/schemas does reflection expose?
- Why does reflection increase risk even though it does not grant business RPC permissions?
- What is the full method name of `ServerReflectionInfo`?
- Why is allowlisting `list_services` insufficient?
- What can `file_containing_symbol` and `file_by_filename` expose?
- Why must descriptor dependency closure be considered when filtering schemas?
- When should a dedicated admin listener be used?
- Does mTLS replace role authorization?
- Why must both reflection `v1` and `v1alpha` be tested if the server exposes both?
- How do you verify the Spring starter actually registers the interceptor for the reflection service?

**Takeaway:** Reflection is a schema discovery tool, not an authorization mechanism for business RPCs. Disable it by default on production listeners; if operationally required, isolate it on an admin boundary, enforce mTLS and appropriate roles, and audit access. Allowlists must control every descriptor query type and the dependency graph; filtering only the service list is insufficient. Test with `grpcurl`/reflection clients and verify actual Spring configuration per profile.
