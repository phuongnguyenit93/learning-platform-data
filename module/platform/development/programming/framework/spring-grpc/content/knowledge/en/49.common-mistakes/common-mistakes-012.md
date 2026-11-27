# Mocking Everything and Ignoring the Contract

In a `SPRING_GRPC` service, Protocol Buffers (`.proto`) define the contract between client and server. From this contract, the system generates Java messages, service base classes, and client stubs for unary or streaming RPCs. If tests simply use Mockito to replace every component with a mock, tests can stay green while client and server still fail to communicate at runtime.

Mocking is very useful for verifying that a unit calls its dependencies properly. The problem arises when mocks replace the gRPC boundary itself: tests no longer verify service names, method paths, serialization, metadata, deadlines, statuses, interceptors, streaming, or Spring configuration. Those parts are precisely the contract that independent processes must obey.

The goal is choosing the right boundary for each test type: mock dependencies in unit tests, but use generated clients and real gRPC servers in contract/integration tests. That way, tests stay fast at the business layer while catching communication bugs before deployment.

## 1. What constitutes a gRPC service contract?

A contract is more than just a Java method signature. It encompasses multiple parts on which client and server must agree:

| Component | What must stay compatible | Potential errors if ignored |
|---|---|---|
| Service and method | `package`, service name, method name, and full RPC path. | Client calls the wrong endpoint or receives `UNIMPLEMENTED`. |
| RPC type | Unary, server streaming, client streaming, or bidirectional streaming. | Client and server disagree on how to send/receive messages or when the call ends. |
| Protobuf messages | Field numbers, wire types, data types, enum numbers, `oneof`, and presence. | Data is misinterpreted, lost, or incompatible across versions. |
| Metadata | Headers, trailers, authentication tokens, correlation IDs, and custom metadata conventions. | Real requests are rejected even though direct service calls pass in tests. |
| Deadlines and cancellation | Processing time limit, deadline propagation, and reaction when the client cancels the RPC. | Requests hang too long or background work keeps running after the client gives up. |
| Status | Mapping business and system errors to gRPC statuses. | Client cannot distinguish invalid input, missing data, and transient failures. |
| Interceptors and transport | Logging, tracing, auth, compression, TLS, and HTTP/2 configuration. | Tests skip security settings or real connection failures. |

The service and method names form the RPC path `/fully.qualified.Service/Method`. Thus, changing the Protobuf package, service name, or method name can prevent older clients from calling a newer server, even when Java code looks similar at a glance.

The `.proto` file is the source of truth for the contract. Generated Java classes are representations for Java code; never hand-edit generated files to paper over differences between client and server. When the contract changes, update `.proto`, regenerate code with a consistent code generator configuration, and evaluate compatibility before release.

## 2. Why over-mocking strips tests of value

### 2.1. Mocking generated stubs only checks method invocation

Example of a client calling an order service:

```java
OrderServiceGrpc.OrderServiceBlockingStub stub = mock(
        OrderServiceGrpc.OrderServiceBlockingStub.class);

when(stub.getOrder(any(GetOrderRequest.class)))
        .thenReturn(GetOrderResponse.newBuilder()
                .setOrderId("order-42")
                .build());

OrderView result = orderClient.getOrder("order-42");

assertEquals("order-42", result.id());
verify(stub).getOrder(any(GetOrderRequest.class));
```

This can be a valid unit test for `orderClient` logic: it checks how the client adapter handles the returned response. However, no RPC is sent over a channel. The test does not check whether the server registers the right service, whether requests serialize, whether metadata is sent, whether TLS handshakes succeed, or whether the server returns the right status.

Using this test as proof that client and server are compatible draws conclusions far beyond what the test actually verifies.

### 2.2. Mocking or bypassing the service implementation skips the server runtime

A test calling the implementation's Java method directly can verify request/response conversion logic. However, it bypasses the gRPC server, generated method descriptors, interceptor chain, marshallers, and transport. A service registration or interceptor bug may never surface in direct-call tests.

### 2.3. Mocks hide differences between Java objects and Protobuf wire messages

During a real RPC, messages are serialized and deserialized according to Protobuf rules. Default values, field presence, enum numbers, field numbers, and unknown fields all follow specific rules. A mock returning a pre-built Java object does not verify that both sides use compatible schemas.

For example, if business logic must distinguish "user omitted the field" from "user sent an empty value," checking a getter alone may be insufficient. Choose appropriate field types and presence in `.proto` and verify serialization/deserialization behavior with contract tests.

### 2.4. Metadata, deadlines, and statuses get bypassed

A mocked stub does not automatically execute client interceptors or server interceptors. Tests may miss missing tokens, wrong metadata keys, unpropagated deadlines, exceptions mapped to `UNKNOWN`, or business errors mistakenly returning `INTERNAL`.

Similarly, tests calling the implementation method directly do not verify the final status received by the client. Clients rely on `Status.Code` to decide whether to display errors, retry, or abort; therefore, statuses must be verified through a generated stub.

### 2.5. Streaming gets reduced to a single method call

Streaming has its own lifecycle: messages arrive multiple times, the client can half-close its send stream, the server can finish with trailers, and either side can cancel the RPC. Mocking a method to return a list or a single response fails to simulate these behaviors.

If the system uses streaming, test message ordering, stream completion, mid-stream errors, cancellation, and resource cleanup. For long-lived streams, also test deadlines and application-level reconnection protocols.

## 3. Choose the right test type and the right mock boundary

There is no need to ban mocks. Place mocks at the boundary matching the question the test aims to answer.

| Test type | What to use? | What does it verify? |
|---|---|---|
| Business unit test | Mock repositories, clocks, external APIs, or slow dependencies. | Business rules, error branches, and result handling. |
| Client adapter unit test | Can mock the generated stub. | Mapping between internal APIs and Protobuf requests/responses, client-side response handling. |
| gRPC service/contract test | Real generated client stub calling real implementation through a real gRPC server; underlying business dependencies may be mocked. | Service registration, method descriptors, messages, statuses, and RPC behavior at the gRPC boundary. |
| Spring integration test | Initialize Spring context, real beans, real interceptors, and server on a test port. | Wiring, component scanning, starter configuration, lifecycle, and app config. |
| Transport/security test | Connect over TCP/HTTP2 with TLS and auth metadata configured like runtime environments. | TLS handshakes, certificates, trust, auth interceptors, and transport errors. |
| Compatibility test | Client/server generated from different schema versions within the support window. | Compatibility during independent deployment or rolling component upgrades. |

A helpful rule of thumb: mock dependencies inside the boundary under test, but keep real components for the boundary itself. When testing a gRPC contract, keep the generated stub, gRPC server, and real implementation; you can mock repositories or application services to keep tests stable and focused.

## 4. Example: verifying the contract with a generated client and real server

Suppose a service provides an operation to read an order. The Protobuf contract can be declared as follows:

```protobuf
syntax = "proto3";

package shop.orders.v1;

option java_package = "com.example.orders.v1";
option java_multiple_files = true;

service OrderService {
  rpc GetOrder(GetOrderRequest) returns (GetOrderResponse);
}

message GetOrderRequest {
  string order_id = 1;
}

message GetOrderResponse {
  string order_id = 1;
  OrderState state = 2;
}

enum OrderState {
  ORDER_STATE_UNSPECIFIED = 0;
  ORDER_STATE_PENDING = 1;
  ORDER_STATE_PAID = 2;
}
```

The server implementation extends the generated base class and maps results from the application service into Protobuf responses. Condensed example:

```java
public final class OrderGrpcService
        extends OrderServiceGrpc.OrderServiceImplBase {

    private final OrderQuery orderQuery;

    public OrderGrpcService(OrderQuery orderQuery) {
        this.orderQuery = orderQuery;
    }

    @Override
    public void getOrder(
            GetOrderRequest request,
            StreamObserver<GetOrderResponse> responseObserver) {
        try {
            OrderView order = orderQuery.findById(request.getOrderId());

            GetOrderResponse response = GetOrderResponse.newBuilder()
                    .setOrderId(order.id())
                    .setState(toProtoState(order.state()))
                    .build();

            responseObserver.onNext(response);
            responseObserver.onCompleted();
        } catch (OrderNotFoundException ex) {
            responseObserver.onError(Status.NOT_FOUND
                    .withDescription("Order not found")
                    .asRuntimeException());
        }
    }

    private static OrderState toProtoState(OrderStatus state) {
        return switch (state) {
            case PENDING -> OrderState.ORDER_STATE_PENDING;
            case PAID -> OrderState.ORDER_STATE_PAID;
        };
    }
}
```

`OrderQuery`, `OrderView`, and `OrderNotFoundException` represent application-layer types. Enum conversion in a project should explicitly map between domain states and Protobuf enums; never rely on Java enum ordinals when both sides can evolve independently.

The test below uses grpc-java's `InProcessServerBuilder` and `InProcessChannelBuilder`. It runs the real implementation through a generated blocking stub; only the business dependency is mocked:

```java
class OrderGrpcContractTest {

    private Server server;
    private ManagedChannel channel;
    private OrderQuery orderQuery;

    @BeforeEach
    void setUp() throws IOException {
        String serverName = InProcessServerBuilder.generateName();
        orderQuery = mock(OrderQuery.class);

        server = InProcessServerBuilder.forName(serverName)
                .directExecutor()
                .addService(new OrderGrpcService(orderQuery))
                .build()
                .start();

        channel = InProcessChannelBuilder.forName(serverName)
                .directExecutor()
                .build();
    }

    @AfterEach
    void tearDown() {
        if (channel != null) {
            channel.shutdownNow();
        }
        if (server != null) {
            server.shutdownNow();
        }
    }

    @Test
    void callsGeneratedContractAndMapsResponse() {
        when(orderQuery.findById("order-42"))
                .thenReturn(new OrderView("order-42", OrderStatus.PAID));

        GetOrderRequest request = GetOrderRequest.newBuilder()
                .setOrderId("order-42")
                .build();

        GetOrderResponse response = OrderServiceGrpc
                .newBlockingStub(channel)
                .getOrder(request);

        assertEquals("order-42", response.getOrderId());
        assertEquals(OrderState.ORDER_STATE_PAID, response.getState());
        verify(orderQuery).findById("order-42");
    }

    @Test
    void mapsMissingOrderToNotFoundStatus() {
        when(orderQuery.findById("missing"))
                .thenThrow(new OrderNotFoundException());

        StatusRuntimeException error = assertThrows(
                StatusRuntimeException.class,
                () -> OrderServiceGrpc.newBlockingStub(channel)
                        .getOrder(GetOrderRequest.newBuilder()
                                .setOrderId("missing")
                                .build()));

        assertEquals(Status.Code.NOT_FOUND, error.getStatus().getCode());
    }
}
```

This example assumes the project includes a `grpc-inprocess` dependency compatible with the grpc-java version in use, along with JUnit 5, Mockito, and the domain types declared above. `directExecutor()` fits small, synchronous examples; do not use it to draw conclusions about production executor behavior or performance.

In-process transport lets you test RPCs through generated stubs and servers without opening sockets. It does not replace TCP/HTTP2, TLS, certificate, load balancer, or deployment configuration tests. If those factors belong to the service's operational contract, integration tests over real transport are required.

## 5. Checking Protobuf compatibility when schemas change

A test making a successful RPC between a client and server generated from the same `.proto` version only confirms the two current sides match. It does not prove older clients still work with a newer server during staged deployments.

When updating a schema, review these rules:

- Never change published field numbers. When deleting a field, use `reserved` to keep the removed field number and name; never reuse a field number for a different meaning.
- Add new fields compatibly and understand proto3 default values. If business logic must distinguish an absent field from a field carrying a default value, use appropriate presence such as `optional` or a message wrapper by design.
- Keep published numeric enum values unchanged. When deleting an enum value, reserve the old number and name; maintain `*_UNSPECIFIED = 0` as an intentional default.
- Be cautious when changing field types, `oneof`, RPC types, request/response messages, or a field's business meaning. A change can compile cleanly yet remain incompatible in wire format or semantics.
- Changing the Protobuf package, service name, or method name changes the RPC path. If an incompatible change is needed, consider versioning the package/service, such as `shop.orders.v2`, and plan client/server migration.
- Distinguish Protobuf `package` from `option java_package`. `package` forms part of the fully qualified service name in the gRPC contract; `java_package` determines the generated Java package.

A safe release process should check both schema and behavior:

1. Run code generation from `.proto` using the compiler/plugin version pinned in the build.
2. Run schema breaking-change checks using the compatibility tool chosen by the project, if available.
3. Run integration tests with the generated client and server of the current version.
4. For independently deployed systems, run an old-client/new-server and new-client/old-server compatibility matrix across the committed support window.
5. Delete old fields or endpoints only after clients have migrated and the legacy version support window has ended.

Do not rely solely on eyeballing generated Java sources. Protobuf contracts have their own wire compatibility rules; schema check tools and cross-version compatibility tests catch dangerous changes earlier.

## 6. Parts that must be tested through Spring context and real transport

The in-process test above verifies the path through the gRPC API and generated stub. It does not confirm Spring wired the whole application correctly. For a Spring gRPC service, maintain integration tests that boot the application context to verify:

- Service beans are registered with the server and are neither missing nor duplicated.
- Interceptors apply in the right order, such as auth, logging, tracing, and exception mapping.
- Required metadata is read under the right keys and propagated downstream when needed.
- Deadlines are applied and cancellation propagates to background work.
- Spring shutdown stops the server per the expected lifecycle and does not close dependencies before in-flight RPCs finish.
- Port configuration, health checks, and service discovery match the deployment environment.

For TLS, use test certificates and connect client/server over TCP. Test both success cases and untrusted certificates, hostname mismatches, or expired certificates within the scope the system must support. In-process channels do not test TLS handshakes.

For streaming, use real clients and servers to test multiple messages, ordering, half-close, terminal statuses, cancellation, and deadlines. For high-volume streams, add backpressure and resource-limit tests. A test checking only a single returned message does not cover stream termination and cancellation scenarios.

## 7. Signs that tests are mocking too deeply

Revisit your testing strategy if you notice any of these signs:

- All tests call Java methods directly or mock generated stubs; no test boots a gRPC server.
- No test uses request/response classes generated from `.proto` through a generated client stub.
- No status checks exist for `NOT_FOUND`, `INVALID_ARGUMENT`, `UNAUTHENTICATED`, `PERMISSION_DENIED`, or transient errors appropriate to the API.
- Tests never verify metadata, deadlines, interceptors, or cancellation even though those are service requirements.
- Streaming RPCs are tested with a single mocked response.
- `.proto` changes do not trigger code generation, schema compatibility checks, or integration tests.
- Client and server are always built together, yet production deploys them independently without cross-version tests.

When `UNIMPLEMENTED` appears in production, check the service/method path and implementation registration. When `UNAUTHENTICATED` or `PERMISSION_DENIED` appears, check metadata and interceptors. When receiving `INVALID_ARGUMENT`, compare request validation and semantics. When data is wrong or fields go missing, check the schema, field numbers, presence, and generated code versions. Status codes are only clues; confirm with logs and the actual contract.

## 8. Checklist before merging gRPC changes

- [ ] Unit tests mock business dependencies at the right boundary and cover necessary branches.
- [ ] Tests exist that use generated client stubs to call a real gRPC server and service implementation.
- [ ] Tests verify Protobuf responses and status codes for both success and error cases.
- [ ] Metadata, deadlines, cancellation, and interceptors are tested if part of the method's contract.
- [ ] Each streaming mode in use has tests for stream lifecycle and terminal errors.
- [ ] `.proto` changes have been evaluated for field numbers, enum numbers, presence, RPC paths, and wire compatibility.
- [ ] Spring integration tests verify bean registration, server configuration, and lifecycle.
- [ ] TLS/transport tests run when changes involve certificates, channels, or security configuration.
- [ ] If client/server deploy independently, compatibility is tested across versions in the support window.

Mocks keep unit tests focused and decoupled from the environment. However, a gRPC contract is only verified when requests flow through the generated client, server, and communication layers that production actually uses. Keep mocks on internal dependencies and add contract and integration tests at the proper boundaries; only then can the test suite catch failures that an all-mock suite completely misses.
