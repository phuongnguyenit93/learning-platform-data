# UNIMPLEMENTED Due to Unregistered Service

In **SPRING_GRPC**, a client calls an RPC using a full method path consisting of the protobuf package, service name, and method name. If the gRPC server has not registered the corresponding service, the endpoint can return `UNIMPLEMENTED`. This status also appears when the service is registered but the method is not yet implemented, when the client uses an old/wrong contract, or when an intermediary layer returns that status.

You must determine which request the server actually received and which service definitions were bound. `UNIMPLEMENTED` differs from `UNAVAILABLE`: the former usually means a gRPC endpoint responded that the method is not supported; the latter usually indicates the client could not connect or a dependency is temporarily unavailable. This guide walks through tracing from the RPC path, generated code, and Spring bean registration to testing service registration.

## 1. Understand the Full Method Path Called by the Client

gRPC identifies a method with a path of the form:

```text
/package.Service/Method
```

Example contract:

```proto
syntax = "proto3";

package inventory.v1;

option java_package = "com.acme.inventory.grpc.v1";
option java_multiple_files = true;

service InventoryService {
  rpc GetStock(GetStockRequest) returns (GetStockReply);
}

message GetStockRequest {
  string sku = 1;
}

message GetStockReply {
  string sku = 1;
  int32 available = 2;
}
```

The full method path is:

```text
/inventory.v1.InventoryService/GetStock
```

Distinguish between the two package declarations:

- `package inventory.v1` belongs to protobuf and participates in constructing the full method path on the wire.
- `option java_package = "com.acme.inventory.grpc.v1"` determines the Java package of generated classes; it does not change the RPC path.

Therefore, changing `java_package` does not make the client call a new service path. Changing the protobuf `package`, service name, or method name can change the path and cause client/server mismatches.

## 2. Where Can `UNIMPLEMENTED` Come From?

Several scenarios must be distinguished:

| Situation | Symptom | Direction to Check |
| --- | --- | --- |
| Service not registered | Server lacks the matching service descriptor | Spring bean discovery, `@GrpcService`, server registration |
| Service registered, method not overridden/implemented | Service exists yet one method returns `UNIMPLEMENTED` | Generated `ImplBase`, method override, and implementation |
| Client calls wrong package/service/method | Full method path does not match server contract | Proto sources and generated stubs on both sides |
| Client uses old contract/version | Method path or message contract differs from server build | Dependency artifacts and code generation step |
| Server intentionally returns `UNIMPLEMENTED` | Application code or interceptor returns this status | Search for `Status.UNIMPLEMENTED` in code |
| Proxy/gateway returns the status | Request never reaches the right backend service | Routes, upstream clusters, and proxy logs |

Do not conclude a service is unregistered from the status code alone. Cross-check the full method path, server logs, and service registry/definitions of the exact process receiving traffic.

## 3. Check the Generated Service Implementation

A Spring gRPC adapter typically extends the generated `ImplBase`:

```java
@GrpcService
public class InventoryGrpcService
        extends InventoryServiceGrpc.InventoryServiceImplBase {

    private final GetStockUseCase getStock;
    private final InventoryProtoMapper mapper;

    public InventoryGrpcService(
            GetStockUseCase getStock,
            InventoryProtoMapper mapper) {
        this.getStock = getStock;
        this.mapper = mapper;
    }

    @Override
    public void getStock(
            GetStockRequest request,
            StreamObserver<GetStockReply> observer) {
        try {
            StockView result = getStock.execute(
                    new GetStockQuery(request.getSku()));

            observer.onNext(mapper.toProto(result));
            observer.onCompleted();
        } catch (RuntimeException error) {
            observer.onError(Status.INTERNAL
                    .withDescription("Internal server error")
                    .asRuntimeException());
        }
    }
}
```

Check the following points:

- The class extends the right generated base class for the contract the server intends to expose.
- The target method has `@Override` and matches the generated signature.
- The class is Spring-managed and carries the service registration annotation appropriate for your Spring gRPC version.
- No profile/configuration condition excludes the bean from the application context.
- The implementation does not intentionally return `Status.UNIMPLEMENTED` for that method.

The generated base class usually supplies a default implementation for un-overridden RPCs; that default terminates the call with `UNIMPLEMENTED`. Consequently, a service may already be registered while one specific method remains unimplemented.

## 4. Verify the Spring Bean Is Created

With Spring gRPC, service implementations are commonly registered via beans annotated with `@GrpcService`. If the class is outside component scan or excluded by configuration, the server will not have that service.

Example package structure:

```text
com.acme.inventory
├── InventoryApplication.java
└── adapter
    └── grpc
        └── InventoryGrpcService.java
```

The application class should be able to scan the package containing the adapter. If the application class is in a package that is not a parent of the adapter, configure component scan/imports accordingly.

Common causes:

- The adapter lies outside component scan.
- The class is missing the gRPC service registration annotation.
- The bean is excluded by `@Profile`, `@ConditionalOnProperty`, or another condition.
- A constructor dependency error prevents the bean from initializing.
- The adapter lives in a module not included on the runtime classpath.
- Multiple servers/ports exist and the service is registered on a different server than the endpoint the client calls.

Do not just check whether the class has the annotation. Inspect startup logs to see whether the bean was created, the server started, and the service was bound. If application startup already failed due to a bean dependency or duplicate registration, that is a startup configuration error to fix first.

## 5. Check How the Service Is Registered

There are two common wiring styles:

**Spring-managed registration**

```java
@GrpcService
public class InventoryGrpcService
        extends InventoryServiceGrpc.InventoryServiceImplBase {
    // RPC implementations
}
```

Spring gRPC discovers the service bean and registers it with the server using the library version's mechanism.

**Manual server registration**

```java
Server server = ServerBuilder
        .forPort(port)
        .addService(inventoryGrpcService)
        .build()
        .start();
```

In the manual style, creating a Spring bean object does not automatically mean the service was added to the server. You must confirm the exact instance was passed to `addService`.

Avoid registering the same full service name simultaneously through multiple wiring paths. Duplicate registration typically fails at server startup rather than silently fixing `UNIMPLEMENTED`; however, multi-server setups can cause a service to bind on a different endpoint than the one the client uses.

## 6. Compare Client Stub and Server Contract

The generated client stub carries the full method path created from the contract at generation time. If the client uses an outdated artifact, it may invoke a package/service/method no longer exposed by the server.

Check:

1. Locate the `.proto` file the client actually compiles.
2. Confirm the protobuf `package`, `service`, and `rpc` names.
3. Confirm the server compiles a compatible contract.
4. Check dependency versions or generated sources being packaged.
5. Regenerate code after modifying `.proto`.
6. Check the endpoint the channel target points to.

You can print the full method name from the generated method descriptor:

```java
String methodName =
        InventoryServiceGrpc.getGetStockMethod()
                .getFullMethodName();

log.info("Calling gRPC method {}", methodName);
```

Expected value:

```text
inventory.v1.InventoryService/GetStock
```

If client and server log different names, trace the discrepancy in proto sources, artifact versions, or the build pipeline. Do not fix it by changing the Java package when the protobuf package/service/method is what mismatches.

## 7. Verify the Right Endpoint and Right Process

In environments with multiple instances, local profiles, containers, or multiple gRPC ports, a client may successfully connect to another server that has not deployed the service.

Check:

- `forTarget(...)`, DNS name, and port of the channel.
- Which backends service discovery/load balancer returns.
- Published ports/container mappings and ingress routes.
- Active profile/configuration of the running instance.
- Actual image/tag or deployment revision.
- Logs containing instance ID, RPC method, and request timestamp.

`UNIMPLEMENTED` shows that an endpoint returned the status, yet that endpoint might be a proxy, sidecar, or stale server. Correlate the request against logs of each backend to identify which layer stopped the request.

If the client cannot connect at all, you will typically see `UNAVAILABLE`, connection refused, DNS failure, or timeout. Do not handle `UNIMPLEMENTED` with repeated retries as if it were a transient connectivity error; fix service/method registration or the contract path mismatch first.

## 8. Use Reflection and grpcurl to Inspect Services

If the server enables gRPC Server Reflection, you can use `grpcurl` to list services:

```bash
grpcurl -plaintext localhost:9090 list
grpcurl -plaintext localhost:9090 describe inventory.v1.InventoryService
```

The `list` output should include `inventory.v1.InventoryService`; `describe` displays the service's RPCs. With TLS, use the matching CA/client certificate flags instead of `-plaintext`.

Reflection is a diagnostic tool, not a prerequisite for a service to function. If reflection is disabled, `grpcurl list` cannot discover services even though they are registered. In that case, invoke known methods using a proto descriptor/file or inspect server logs and registration in the application.

Do not expose reflection publicly in production purely for debugging convenience if security policy forbids it. It can be enabled in internal or test environments with controlled network access.

## 9. Check the Service Registry at Startup

Ensure the right server instance received the service definition. With Spring-managed registration, inspect Spring gRPC startup logs and the bean condition report when needed. With manual registration, inspect the list of `ServerServiceDefinition` objects added to the server builder before start.

You can log an allowlist of service names at startup:

```java
server.getServices().forEach(definition ->
        log.info(
                "Registered gRPC service: {}",
                definition.getServiceDescriptor().getName()));
```

This snippet only applies if your server/runtime API exposes the list of service definitions at the inspection point. Otherwise, log the service name where the application calls `addService` or use framework startup diagnostics; do not add reflection or internal APIs solely to read the registry.

The service name must match the protobuf package plus service name, e.g., `inventory.v1.InventoryService`. A Java class named `InventoryGrpcService` does not prove the wire service was registered properly.

## 10. Test Service Registration with In-Process gRPC

An in-process test verifies that a service implementation is added to a server and the generated client can invoke the RPC. The test requires no TCP port:

```java
String serverName = InProcessServerBuilder.generateName();

InventoryGrpcService service =
        new InventoryGrpcService(getStockUseCase, mapper);

Server server = InProcessServerBuilder
        .forName(serverName)
        .directExecutor()
        .addService(service)
        .build()
        .start();

ManagedChannel channel = InProcessChannelBuilder
        .forName(serverName)
        .directExecutor()
        .build();

try {
    InventoryServiceGrpc.InventoryServiceBlockingStub client =
            InventoryServiceGrpc.newBlockingStub(channel);

    GetStockReply reply = client.getStock(
            GetStockRequest.newBuilder()
                    .setSku("SKU-42")
                    .build());

    assertEquals("SKU-42", reply.getSku());
} finally {
    channel.shutdownNow();
    server.shutdownNow();
    channel.awaitTermination(2, TimeUnit.SECONDS);
    server.awaitTermination(2, TimeUnit.SECONDS);
}
```

This test proves the service definition and method implementation work through the gRPC runtime. It does not yet verify Spring component scanning or annotation-based registration, because the test added the service directly.

To test Spring registration, add an integration test that boots the Spring application context with the active gRPC server auto-configuration, then invokes the generated stub against the test server. Do not manually add the service in that test; the goal is to prove the framework discovers the bean and registers the right service.

## 11. Test the Unregistered Service Case

A negative test can start an in-process server without adding the service, then invoke the stub:

```java
@Test
void unknownServiceReturnsUnimplemented() throws Exception {
    String serverName = InProcessServerBuilder.generateName();

    Server server = InProcessServerBuilder.forName(serverName)
            .directExecutor()
            .build()
            .start();

    ManagedChannel channel = InProcessChannelBuilder.forName(serverName)
            .directExecutor()
            .build();

    try {
        InventoryServiceGrpc.InventoryServiceBlockingStub client =
                InventoryServiceGrpc.newBlockingStub(channel);

        StatusRuntimeException error = assertThrows(
                StatusRuntimeException.class,
                () -> client.getStock(
                        GetStockRequest.newBuilder()
                                .setSku("SKU-42")
                                .build()));

        assertEquals(
                Status.Code.UNIMPLEMENTED,
                Status.fromThrowable(error).getCode());
    } finally {
        channel.shutdownNow();
        server.shutdownNow();
        channel.awaitTermination(2, TimeUnit.SECONDS);
        server.awaitTermination(2, TimeUnit.SECONDS);
    }
}
```

A negative test confirms gRPC runtime behavior when the service is unbound. In real test suites, pair it with a positive test to prove the right service is registered and the method works.

## 12. Systematic Troubleshooting Sequence

When receiving `UNIMPLEMENTED`, follow this order:

1. Record the full method path from the generated descriptor or server logs.
2. Confirm the host/port/backend the client actually calls.
3. Verify protobuf package, service name, and method name across both sides.
4. Confirm the server's generated base class matches the contract and the method is overridden.
5. Confirm the Spring bean is created and not excluded by profiles/conditions.
6. Confirm the service is bound to the right gRPC server.
7. Use reflection/grpcurl if the environment allows.
8. Write or run an in-process registration test.
9. Check proxies/gateways if requests do not reach the expected process.
10. After fixing, restart/deploy the right artifact and confirm the call succeeds.

Do not start by retrying the RPC or altering status handling on the client. `UNIMPLEMENTED` usually requires fixing server registration, method implementation, or contract paths.

## 13. Common Mistakes

| Mistake | Why It Causes `UNIMPLEMENTED` | Resolution |
| --- | --- | --- |
| Forgetting `@GrpcService` or registration | Service bean is never bound | Register the service via the active Spring gRPC mechanism |
| Adapter outside component scan | Spring never creates the bean | Fix package scan/imports |
| Profile excludes the adapter | Service does not exist in that runtime | Check active profiles/conditions |
| Extending generated `ImplBase` without overriding RPC | Default method returns `UNIMPLEMENTED` | Implement the method or remove it from the contract if unsupported |
| Client uses outdated proto | Full method path mismatches | Update contract artifact and regenerate |
| Confusing protobuf package with `java_package` | Inspects the wrong wire path | Use protobuf package/service/method |
| Calling wrong port/backend | Request reaches a server without the service | Check target, discovery, and deployment |
| Reflection disabled | Cannot list services via grpcurl | Use known proto or startup diagnostics |
| Server intentionally returns `UNIMPLEMENTED` | Status unrelated to registration | Locate where the status is created in code/interceptors |

## 14. Practice Exercises

1. Create `inventory.v1.InventoryService` with RPC `GetStock`.
2. Generate Java code and print the full method name from the generated descriptor.
3. Write `InventoryGrpcService` extending generated `ImplBase` and overriding `getStock`.
4. Register the adapter via the Spring gRPC bean mechanism; verify the bean is created at application startup.
5. Temporarily remove the annotation/registration and observe the error from the generated client.
6. Restore registration, re-call the RPC, and verify a successful response.
7. Create an in-process positive test for the registered service.
8. Create a negative test for an unknown service and assert `Status.Code.UNIMPLEMENTED`.
9. Use grpcurl/reflection if enabled to inspect the service name and method list.
10. Change the protobuf package or use an outdated client artifact in a test environment; confirm the full method path changes and document the fix.

### Remember

**`UNIMPLEMENTED` usually means a gRPC endpoint responded that the called service or method path is not supported.** Verify the full method path, generated contract, method override, Spring bean discovery, and service registration on the exact server instance. Distinguish an unregistered service from an unimplemented method or an outdated client contract; validate with in-process tests and startup diagnostics before changing the client or adding retries.

## References

- [gRPC — Status Codes](https://grpc.io/docs/guides/status-codes/)
- [gRPC — Reflection](https://grpc.io/docs/guides/reflection/)
- [gRPC Java — ServerServiceDefinition](https://grpc.github.io/grpc-java/javadoc/io/grpc/ServerServiceDefinition.html)
- [gRPC Java — ServerBuilder](https://grpc.github.io/grpc-java/javadoc/io/grpc/ServerBuilder.html)
- [Spring gRPC — Server Services](https://docs.spring.io/spring-grpc/reference/server.html)
- [grpcurl](https://github.com/fullstorydev/grpcurl)
