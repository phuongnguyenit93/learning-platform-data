# Verifying Service Method Existence

A gRPC client can only invoke an RPC if the method exists in the contract from which the client was generated and the provider is serving that exact method endpoint. When a client receives `UNIMPLEMENTED`, the cause may be that the server has not implemented the method, the service is not registered, the client and server use different contract versions, or the method path does not match.

In Spring gRPC, verifying service method existence requires separating three questions:

1. **Is the method present in the protobuf contract?** Check the descriptor generated from proto.
2. **Does the provider register the method route?** Check `ServerServiceDefinition` or the actual server configuration.
3. **Is the handler actually implemented?** Call the RPC via the generated stub and verify the result is not the default `UNIMPLEMENTED`.

Checking only one layer is not enough. The generated base class may bind the method while its default handler still returns `UNIMPLEMENTED`; conversely, the client may have the right descriptor while the server is running an older version without that method. This lesson walks through checking the contract, registration, and runtime behavior.

## 1. How Is a Service Method Identified?

Protobuf example:

```proto
syntax = "proto3";

package shop.catalog.v1;

option java_multiple_files = true;
option java_package = "com.myshop.catalog.v1";
option java_outer_classname = "CatalogProto";

service CatalogService {
  rpc GetProduct(GetProductRequest) returns (Product);
  rpc WatchProduct(WatchProductRequest) returns (stream ProductEvent);
  rpc ImportProducts(stream ImportProductRequest) returns (ImportSummary);
  rpc SyncProducts(stream SyncProductRequest)
      returns (stream SyncProductEvent);
}

message GetProductRequest { string product_id = 1; }
message Product { string product_id = 1; string display_name = 2; }
message WatchProductRequest { string product_id = 1; }
message ProductEvent { string event_id = 1; string product_id = 2; }
message ImportProductRequest { string product_id = 1; }
message ImportSummary { int32 imported_count = 1; }
message SyncProductRequest { string product_id = 1; }
message SyncProductEvent { string state = 1; }
```

With package `shop.catalog.v1` and service `CatalogService`, the full service name is `shop.catalog.v1.CatalogService`. The full method path of `GetProduct` is:

```text
/shop.catalog.v1.CatalogService/GetProduct
```

The path is case-sensitive and serves as the identity used by the gRPC transport. Changing the package, service, or method name can cause clients to call a path the provider has not registered.

## 2. Checking a Method in the Protobuf Descriptor

The generated protobuf outer class provides the file descriptor; the generated gRPC class provides the gRPC service descriptor. The protobuf descriptor gives input/output message types and streaming flags. The gRPC descriptor gives the full method name and method type used at invocation time.

Example checking the protobuf descriptor:

```java
import com.google.protobuf.Descriptors;
import org.junit.jupiter.api.Test;
import static org.junit.jupiter.api.Assertions.*;

class CatalogProtoContractTest {
    @Test
    void getProductExistsInProtoContract() {
        Descriptors.ServiceDescriptor service =
                CatalogProto.getDescriptor()
                        .findServiceByName("CatalogService");

        assertNotNull(service);
        assertEquals("shop.catalog.v1.CatalogService",
                service.getFullName());

        Descriptors.MethodDescriptor method =
                service.findMethodByName("GetProduct");
        assertNotNull(method);
        assertEquals("shop.catalog.v1.GetProductRequest",
                method.getInputType().getFullName());
        assertEquals("shop.catalog.v1.Product",
                method.getOutputType().getFullName());
        assertFalse(method.isClientStreaming());
        assertFalse(method.isServerStreaming());
    }
}
```

Checking the gRPC descriptor to verify the full method path and RPC type:

```java
import io.grpc.MethodDescriptor;
import io.grpc.ServiceDescriptor;

ServiceDescriptor service = CatalogServiceGrpc.getServiceDescriptor();
MethodDescriptor<?, ?> method = service.getMethods().stream()
        .filter(candidate -> candidate.getFullMethodName().equals(
                "shop.catalog.v1.CatalogService/GetProduct"))
        .findFirst()
        .orElseThrow(() -> new AssertionError("GetProduct is absent"));

assertEquals(MethodDescriptor.MethodType.UNARY, method.getType());
```

These two tests confirm that code generated from proto contains the expected method. They do not prove the running server has registered or implemented the method; that is the responsibility of provider tests.

## 3. Checking a Method in ServerServiceDefinition

A Java gRPC service implementation provides a `ServerServiceDefinition` via `BindableService.bindService()`. You can inspect the list of methods registered by the service binding:

```java
BindableService service = new CatalogGrpcService(catalogUseCase);
ServerServiceDefinition definition = service.bindService();

Set<String> registeredMethods = definition.getMethods().stream()
        .map(ServerMethodDefinition::getMethodDescriptor)
        .map(MethodDescriptor::getFullMethodName)
        .collect(Collectors.toSet());

assertTrue(registeredMethods.contains(
        "shop.catalog.v1.CatalogService/GetProduct"));
```

This checks the route created by the service binding. There is an important detail: the generated `CatalogServiceImplBase` typically creates bindings for every method in the proto. If a subclass does not override a method, the generated base's default handler may still return `UNIMPLEMENTED`. Therefore, a method appearing in `getMethods()` only proves the route is bound; it does not yet prove the method logic has been written.

If Spring gRPC registers services via annotations or auto-configuration, testing `bindService()` alone does not prove that the bean is actually attached to the server. You need an integration test that starts the Spring-managed server and calls the method over a channel like a real client.

## 4. Distinguishing Declared Methods from Implemented Methods

Example implementation that only overrides `GetProduct`:

```java
public final class CatalogGrpcService
        extends CatalogServiceGrpc.CatalogServiceImplBase {
    private final CatalogUseCase catalog;

    public CatalogGrpcService(CatalogUseCase catalog) {
        this.catalog = catalog;
    }

    @Override
    public void getProduct(
            GetProductRequest request,
            StreamObserver<Product> observer) {
        Product product = catalog.getProduct(request.getProductId());
        observer.onNext(product);
        observer.onCompleted();
    }
}
```

In this example, `GetProduct` has an implementation. `WatchProduct`, `ImportProducts`, or `SyncProducts` may still retain their default implementations if not overridden. They still appear in the descriptor and server definition, yet calling them may return `UNIMPLEMENTED`.

Do not use reflection on Java method names to conclude that a handler is implemented. Generated base classes, overrides, and Spring proxies make reflection checks prone to false results. The reliable way is to invoke the RPC over a test transport and verify the committed behavior/status.

## 5. Provider Testing with an In-Process Server

An in-process server lets you invoke the service implementation through the gRPC runtime without opening a TCP port. This test verifies that the method is bound and the handler returns the expected result:

```java
class CatalogMethodRegistrationTest {
    private Server server;
    private ManagedChannel channel;
    private CatalogServiceGrpc.CatalogServiceBlockingStub stub;

    @BeforeEach
    void setUp() throws IOException {
        String name = InProcessServerBuilder.generateName();
        server = InProcessServerBuilder.forName(name)
                .addService(new CatalogGrpcService(testCatalogUseCase()))
                .build()
                .start();
        channel = InProcessChannelBuilder.forName(name).build();
        stub = CatalogServiceGrpc.newBlockingStub(channel)
                .withDeadlineAfter(2, TimeUnit.SECONDS);
    }

    @AfterEach
    void tearDown() throws InterruptedException {
        channel.shutdownNow();
        server.shutdownNow();
        channel.awaitTermination(1, TimeUnit.SECONDS);
        server.awaitTermination(1, TimeUnit.SECONDS);
    }

    @Test
    void getProductIsImplementedAndCallable() {
        Product response = stub.getProduct(
                GetProductRequest.newBuilder()
                        .setProductId("P-100")
                        .build());
        assertEquals("P-100", response.getProductId());
    }
}
```

The fixture `testCatalogUseCase()` supplies test data. If the service does not register the expected service/method path, the call terminates with `UNIMPLEMENTED`; if the method is registered but the handler encounters a business error, the test receives the corresponding status. Therefore, tests must assert specific contract responses or statuses rather than merely asserting that the call did not throw an arbitrary exception.

## 6. Testing Unoverridden Methods and Older Server Versions

You can create an implementation that intentionally omits overriding a method to verify that tests catch the default `UNIMPLEMENTED`:

```java
final class IncompleteCatalogService
        extends CatalogServiceGrpc.CatalogServiceImplBase {
    // getProduct not overridden: generated default handler returns UNIMPLEMENTED.
}
```

When calling `getProduct` via a stub against this service, the test should verify:

```java
StatusRuntimeException error = assertThrows(
        StatusRuntimeException.class,
        () -> stub.getProduct(
                GetProductRequest.newBuilder()
                        .setProductId("P-100")
                        .build()));

assertEquals(Status.Code.UNIMPLEMENTED,
        error.getStatus().getCode());
```

A similar situation occurs when a client is generated from a newer proto while the production server is still running an older binary without the method. This is why contract tests need to verify client/provider versions and run provider verification against the artifact about to be released.

`UNIMPLEMENTED` is a useful signal, though not the sole proof that a method does not exist in the proto. A handler can deliberately return that status; test fixtures need to distinguish the default handler from an intentional business policy.

## 7. Verifying All Four RPC Types

Method existence also includes having the right RPC shape:

| RPC | Proto signature | Method type |
| --- | --- | --- |
| Unary | `rpc GetProduct(A) returns (B);` | `UNARY` |
| Server streaming | `rpc WatchProduct(A) returns (stream B);` | `SERVER_STREAMING` |
| Client streaming | `rpc ImportProducts(stream A) returns (B);` | `CLIENT_STREAMING` |
| Bidirectional streaming | `rpc SyncProducts(stream A) returns (stream B);` | `BIDI_STREAMING` |

Descriptor tests should verify the `isClientStreaming()` and `isServerStreaming()` flags for each method. Runtime tests need to call using the appropriate stub type:

- Unary: blocking or async stub, assert response/status.
- Server streaming: read the iterator or observer up to the terminal signal, assert the stream emits according to contract.
- Client streaming: send request messages and complete the request stream, assert the final response.
- Bidirectional: verify both directions, message ordering, and terminal behavior.

If the proto declares server streaming while generated/server bindings have a different method type, descriptor tests catch it before execution. If the method exists but the server does not implement the stream properly, runtime streaming tests catch it.

## 8. Verifying Service Registration in Spring gRPC

In a Spring application, services are typically registered via annotations or the framework version's auto-configuration. Unit tests calling `bindService()` directly do not verify whether the application context discovers the bean.

A Spring integration test should:

1. Start the application context with test gRPC configuration.
2. Wait for the server to be ready and obtain a channel/client stub pointing to that server.
3. Call the method via the generated stub with a valid request.
4. Assert a specific contract response or status while verifying `UNIMPLEMENTED` is not returned.
5. Close the channel and stop the context after the test.

Annotation names, random port setup, and how channels are injected depend on the Spring gRPC starter/version the project uses. Use the available extension points; do not assume any service bean is automatically registered without an integration test proving it.

Server reflection can help tools discover services/methods, but reflection is a separate service and may be disabled or restricted for security reasons. Do not treat reflection not listing a method as sole proof that the application service lacks the method. Contract tests should inspect descriptors and execute RPCs against the real endpoint.

## 9. Diagnosing Missing Method Errors

| Symptom | Possible Cause | How to Check |
| --- | --- | --- |
| Client fails to compile when calling method | Client code generated from a proto without the method | Check proto dependency and generated source version |
| Runtime returns `UNIMPLEMENTED` | Older server, unregistered service, missing route, or default handler | Check deployed artifact, service definition, and provider invocation |
| Service exists but full path differs | Package/service/method name mismatch | Compare full method name in client and server descriptors |
| Method is bound but not overridden | Generated base default handler | Invoke the RPC and assert status/response; do not just check the method list |
| Local test passes but Spring app fails | Bean not scanned/registered or different server configuration | Run a Spring integration test against the context's real server |
| Reflection does not list the method | Reflection disabled, blocked, or pointing to another endpoint | Check server configuration and invoke the method directly |

When troubleshooting a version mismatch, verify which contract artifact the client and server builds use. With rolling deployments, older servers may continue receiving traffic from newer clients; only roll out clients calling new methods after compatible providers are ready or have fallbacks.

## 10. Contract Test Checklist

- [ ] Proto descriptor has the expected service and method names.
- [ ] Full service name and full method path match the published contract.
- [ ] Request/response message types are correct.
- [ ] RPC cardinality is correct: unary, server, client, or bidi streaming.
- [ ] Generated gRPC descriptor contains the expected method type.
- [ ] `ServerServiceDefinition` has the expected route.
- [ ] Bound routes are not confused with overridden handlers.
- [ ] Provider tests call through an in-process server and assert specific responses/statuses.
- [ ] Tests exist to catch default `UNIMPLEMENTED` when a method is unimplemented.
- [ ] Spring integration tests verify the service is registered in the application context.
- [ ] Client/server contract versions are verified prior to release/rolling deployment.
- [ ] Reflection is only a supplementary discovery tool, not a replacement for contract tests.

**Self-Check**

**Question 1.** What does the protobuf descriptor confirm when it finds a service method?

*Answer:* It confirms the method is declared in the compiled schema, including input/output types and streaming shape. It does not confirm that a running provider has registered or implemented the method.

**Question 2.** Why can a method present in `ServerServiceDefinition` still return `UNIMPLEMENTED`?

*Answer:* The generated service base may bind every method and provide a default handler returning `UNIMPLEMENTED` if the subclass has not overridden that method.

**Question 3.** Which test confirms a handler actually works?

*Answer:* Invoking the RPC via a generated stub against a running provider in an in-process or Spring integration test, then asserting the committed response or status; do not only inspect the method list.

**Question 4.** What components make up a full method path?

*Answer:* It consists of the protobuf package, service name, and method name in the form `/package.Service/Method`; getting any component wrong can prevent the server from finding the route.

**Question 5.** Why can you not rely solely on server reflection?

*Answer:* Reflection may be disabled, restricted, or pointing to another endpoint. It assists discovery but does not prove the handler implements the contract properly; descriptor and runtime contract tests are still required.

Verifying service method existence must span from schema to server runtime. Descriptors protect method names and shapes; server definitions show bound routes; provider/Spring integration tests prove the handler actually returns contract-compliant results instead of the default `UNIMPLEMENTED`. Combining all three catches code generation errors, service registration issues, and client-server version drift early.
