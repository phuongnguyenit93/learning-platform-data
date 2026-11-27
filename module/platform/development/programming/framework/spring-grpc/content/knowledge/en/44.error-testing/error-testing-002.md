# Testing NOT_FOUND and Missing Resources

A gRPC API often accepts an identifier to read or modify a resource. When the identifier is validly formatted but the resource does not exist within the scope the caller is allowed to access, the server should return the **NOT_FOUND** status. This lesson uses GetOrder in Spring gRPC to demonstrate how to map missing resources to the standard status and test it using a generated blocking stub.

NOT_FOUND means the requested resource does not exist or is not exposed within the query scope. It differs from INVALID_ARGUMENT, which is used when the request has invalid structure or values; and differs from PERMISSION_DENIED, which is used when the resource exists but the caller lacks permission to access it, though depending on security policy the server may intentionally hide existence by returning NOT_FOUND.

## 1. Define the Resource Contract

Suppose the service provides an RPC to read an order:

~~~proto
syntax = "proto3";

package acme.orders.v1;

option java_multiple_files = true;
option java_package = "com.acme.orders.v1";

service OrderService {
  rpc GetOrder(GetOrderRequest) returns (GetOrderResponse);
}

message GetOrderRequest {
  string order_id = 1;
}

message GetOrderResponse {
  string order_id = 1;
  string customer_id = 2;
  int64 total_minor = 3;
  string currency = 4;
}
~~~

The request carries order_id to locate the resource. There are two distinct cases:

- Empty or syntactically invalid ID: the request is invalid, return INVALID_ARGUMENT.
- Valid ID with no matching order in the query scope: return NOT_FOUND.

Do not return NOT_FOUND for every repository error. A database disconnection is UNAVAILABLE or an appropriate infrastructure status; a downstream timeout is DEADLINE_EXCEEDED. If all errors are collapsed into NOT_FOUND, clients will mistakenly think the resource does not exist and may overlook operational incidents.

## 2. Map Optional.empty to NOT_FOUND

The repository should represent a missing resource with Optional.empty() rather than returning null or throwing a generic exception:

~~~java
public interface OrderRepository {
    Optional<OrderRecord> findById(String orderId);
}
~~~

The service implementation validates the identifier first, then performs the lookup and translates a missing result into the status:

~~~java
import io.grpc.Status;
import io.grpc.stub.StreamObserver;

public final class OrderGrpcService
        extends OrderServiceGrpc.OrderServiceImplBase {

    private final OrderRepository repository;

    public OrderGrpcService(OrderRepository repository) {
        this.repository = repository;
    }

    @Override
    public void getOrder(
            GetOrderRequest request,
            StreamObserver<GetOrderResponse> responseObserver) {

        String orderId = request.getOrderId();
        if (orderId == null || orderId.isBlank()) {
            responseObserver.onError(
                Status.INVALID_ARGUMENT
                    .withDescription("order_id must not be blank")
                    .asRuntimeException());
            return;
        }

        Optional<OrderRecord> result = repository.findById(orderId);
        if (result.isEmpty()) {
            responseObserver.onError(
                Status.NOT_FOUND
                    .withDescription("order not found")
                    .asRuntimeException());
            return;
        }

        responseObserver.onNext(toResponse(result.get()));
        responseObserver.onCompleted();
    }

    private GetOrderResponse toResponse(OrderRecord order) {
        return GetOrderResponse.newBuilder()
            .setOrderId(order.id())
            .setCustomerId(order.customerId())
            .setTotalMinor(order.totalMinor())
            .setCurrency(order.currency())
            .build();
    }
}
~~~

OrderRecord is an internal data type for this example. In a Spring application, OrderGrpcService is typically registered through the starter's service registration mechanism and receives OrderRepository via constructor injection. Do not let the implementation depend directly on an HTTP controller or REST exception mapping.

For a unary RPC, return after onError and do not call onNext or onCompleted. If centralized exception mapping or an interceptor is used, ensure missing-resource exceptions are mapped consistently to NOT_FOUND instead of falling back to UNKNOWN.

## 3. Choose the Right Status When a Resource Is Inaccessible

| Situation | Appropriate Status | Meaning |
| --- | --- | --- |
| Empty or malformed ID | INVALID_ARGUMENT | Caller must fix the request |
| Valid ID but resource does not exist | NOT_FOUND | Resource is not present in the query scope |
| Resource exists but caller lacks permission | PERMISSION_DENIED | Caller is not authorized to perform the operation |
| Login required or invalid credentials | UNAUTHENTICATED | Caller identity has not been authenticated |
| Resource is in a state that disallows the operation | FAILED_PRECONDITION | State must be changed first |
| Database or downstream unavailable | UNAVAILABLE | Infrastructure error that may be transient |

The decision between NOT_FOUND and PERMISSION_DENIED may depend on anti-enumeration policy. For example, a multi-tenant API may return NOT_FOUND for both non-existent resources and resources belonging to another tenant, avoiding disclosure that another tenant holds data. If adopting this approach, enforce tenant filtering at the query layer and keep the behavior consistent across all endpoints.

## 4. Test Using an In-Process gRPC Server

In-process transport runs both server and client in the same JVM, making it suitable for testing service logic, status mapping, and repository interactions without opening a TCP port.

JUnit 5 example using a fake repository:

~~~java
import static org.junit.jupiter.api.Assertions.*;

import io.grpc.ManagedChannel;
import io.grpc.Server;
import io.grpc.Status;
import io.grpc.StatusRuntimeException;
import io.grpc.inprocess.InProcessChannelBuilder;
import io.grpc.inprocess.InProcessServerBuilder;
import java.io.IOException;
import java.util.Optional;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicInteger;
import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;

class OrderGrpcServiceTest {

    private Server server;
    private ManagedChannel channel;
    private OrderServiceGrpc.OrderServiceBlockingStub stub;
    private AtomicInteger repositoryCalls;

    @BeforeEach
    void setUp() throws IOException {
        String serverName = InProcessServerBuilder.generateName();
        repositoryCalls = new AtomicInteger();

        OrderRepository repository = orderId -> {
            repositoryCalls.incrementAndGet();
            return Optional.empty();
        };

        server = InProcessServerBuilder.forName(serverName)
            .directExecutor()
            .addService(new OrderGrpcService(repository))
            .build()
            .start();

        channel = InProcessChannelBuilder.forName(serverName)
            .directExecutor()
            .build();

        stub = OrderServiceGrpc.newBlockingStub(channel)
            .withDeadlineAfter(1, TimeUnit.SECONDS);
    }

    @AfterEach
    void tearDown() throws InterruptedException {
        if (channel != null) {
            channel.shutdownNow();
            assertTrue(channel.awaitTermination(5, TimeUnit.SECONDS));
        }
        if (server != null) {
            server.shutdownNow();
            assertTrue(server.awaitTermination(5, TimeUnit.SECONDS));
        }
    }

    @Test
    void validButMissingOrderReturnsNotFound() {
        GetOrderRequest request = GetOrderRequest.newBuilder()
            .setOrderId("order-404")
            .build();

        StatusRuntimeException error = assertThrows(
            StatusRuntimeException.class,
            () -> stub.getOrder(request));

        assertEquals(
            Status.Code.NOT_FOUND,
            error.getStatus().getCode());
        assertEquals(
            "order not found",
            error.getStatus().getDescription());
        assertEquals(1, repositoryCalls.get());
    }

    @Test
    void blankOrderIdReturnsInvalidArgumentWithoutLookup() {
        GetOrderRequest request = GetOrderRequest.newBuilder()
            .setOrderId(" ")
            .build();

        StatusRuntimeException error = assertThrows(
            StatusRuntimeException.class,
            () -> stub.getOrder(request));

        assertEquals(
            Status.Code.INVALID_ARGUMENT,
            error.getStatus().getCode());
        assertEquals(0, repositoryCalls.get());
    }
}
~~~

The test uses directExecutor() because the handler in this example performs validation and lookup synchronously without blocking on other tasks. If the fake repository introduces a delay, latch, or I/O, use a dedicated executor to avoid blocking the test thread. The grpc-inprocess artifact must match the version of the remaining gRPC Java artifacts.

## 5. Also Test When the Resource Exists

A test that only verifies NOT_FOUND can miss a bug where the service always returns an error. You should include a success test to prove the mapping only applies when the repository actually has no resource:

~~~java
OrderRecord record = new OrderRecord(
    "order-42", "customer-7", 12500, "USD");

OrderRepository foundRepository =
    orderId -> Optional.of(record);

OrderGrpcService service = new OrderGrpcService(foundRepository);
~~~

In a separate test fixture, register this service and call GetOrder with order-42; assert that the response has the expected order_id, customer_id, amount, and currency. The success path must call the repository exactly once and not produce NOT_FOUND.

You should also test these cases:

- Whether soft-deleted resources are treated as non-existent under the contract.
- Whether a valid ID belonging to another tenant returns NOT_FOUND or PERMISSION_DENIED per policy.
- That the repository returns Optional.empty() only when the query completes successfully with no matching row.
- That database errors are propagated as appropriate infrastructure statuses rather than converted to NOT_FOUND.

## 6. Test Against Erroneous Repository Calls and Side Effects

For read RPCs, the key assertion is that the repository is called once for a valid ID and not called when the ID is malformed. For update/delete RPCs, missing resources must be detected before any side effect:

1. Read or check existence inside an appropriate transaction.
2. If the resource is absent, return NOT_FOUND.
3. Do not emit events, write success audit records, or call downstream services as if the operation succeeded.
4. If a race occurs between read and write, handle it via transactions/constraints and map the result consistently.

Do not rely on a separate existsById call before updating if the state can change between the two queries. For updates/deletes, prefer a single conditional statement or transaction to determine the exact number of affected rows.

## 7. Missing Resources in Multi-Tenant Systems

In a multi-tenant system, queries must bind the tenant from the authenticated identity:

~~~java
Optional<OrderRecord> findByIdAndTenantId(
    String orderId,
    String authenticatedTenantId);
~~~

authenticatedTenantId must come from the verified principal/credentials; do not trust a tenant ID supplied by the caller in the request or metadata. If querying by both order ID and tenant ID returns empty, the service can return NOT_FOUND to avoid disclosing resources belonging to another tenant.

Do not include sensitive tenant IDs, customer IDs, or other resource details in the status description if the caller is not permitted to see them. Log internally with a request ID and standardized error code; restrict logging full identifiers according to data policy.

## 8. Rich Error Details When Resource Info Is Needed

NOT_FOUND with a short description is usually sufficient for simple APIs. If the client needs to know what kind of resource is missing, you can use the rich error model with google.rpc.Status and google.rpc.ResourceInfo details:

~~~java
import com.google.protobuf.Any;
import com.google.rpc.ResourceInfo;
import com.google.rpc.Status;
import io.grpc.protobuf.StatusProto;

ResourceInfo resourceInfo = ResourceInfo.newBuilder()
    .setResourceType("acme.orders.v1.Order")
    .setResourceName("orders/order-404")
    .setOwner("")
    .setDescription("The requested order was not found")
    .build();

com.google.rpc.Status richStatus = com.google.rpc.Status.newBuilder()
    .setCode(com.google.rpc.Code.NOT_FOUND_VALUE)
    .setMessage("order not found")
    .addDetails(Any.pack(resourceInfo))
    .build();

responseObserver.onError(StatusProto.toStatusRuntimeException(richStatus));
~~~

This snippet requires compatible protobuf common types, including google.rpc.ResourceInfo and Any. Only include the resource name if the caller is authorized to see it; in multi-tenant APIs, details may leak resource existence. Clients read details using StatusProto.fromThrowable(error) and unpack the corresponding type URL.

Not all proxies or clients preserve rich error detail trailers. If details are mandatory, test across the full production path and still keep the basic status code/message clear enough when details are stripped.

## 9. Do Not Retry NOT_FOUND

NOT_FOUND is typically a stable query result at execution time. Immediate retries of the same request rarely help and can generate unnecessary load. Do not put NOT_FOUND in the retryable status codes list unless the API has documented special semantics, such as a resource created asynchronously while the caller actively polls with backoff.

If a resource may appear later, design an explicit operation/polling flow: return a pending state or a dedicated operation resource instead of turning NOT_FOUND into a generic retry error. For resource-creation requests, use an idempotency key so callers can query the outcome after a timeout without creating duplicates.

## 10. Test Through the Spring Application Context

In-process tests verify service logic and status mapping, but do not prove that the starter has registered the service or interceptors properly. Add Spring integration tests to:

- Boot the application context with a fake repository or test database.
- Call GetOrder over a channel to the starter-managed server.
- Verify the service name and method path are registered properly.
- Check that interceptors do not alter NOT_FOUND into another status.
- Check metadata/trailers and rich error details if the API uses them.
- Verify TLS/proxy if they are part of the deployment.

The port property name and how the channel is obtained depend on the starter/version. Use your project's actual extension point; do not assume every Spring gRPC starter shares the same configuration.

## 11. Recommended Test Matrix

| Scenario | Status/Result | Repository |
| --- | --- | --- |
| Empty ID | INVALID_ARGUMENT | Not called |
| Valid ID that does not exist | NOT_FOUND | Called once |
| Valid ID and resource exists | Success | Called once |
| Resource belongs to another tenant | Per policy, typically NOT_FOUND to prevent enumeration | Query is tenant-scoped |
| Database unavailable | UNAVAILABLE or appropriate infrastructure mapping | Error distinguished from empty result |
| Soft-deleted resource | Per API contract | Query applies soft-delete rules |

Check the status code first, then check the description or rich details. Do not assert only the message string because messages may evolve while status semantics must remain stable.

## 12. Takeaways and Self-Check

**Testing NOT_FOUND and missing resources** must prove that valid IDs with no matching resource map to NOT_FOUND, while malformed IDs remain INVALID_ARGUMENT. Use an Optional repository, a generated blocking stub, and an in-process server to verify status, description, lookup count, and the success path. For multi-tenant systems, queries must be scoped by authenticated identity and avoid leaking resources outside the caller's scope.

Self-check:

1. Why does a valid resource ID with no result differ from a malformed request?
2. When should you use NOT_FOUND instead of PERMISSION_DENIED?
3. Why must database errors not be mapped to NOT_FOUND?
4. What must tests verify besides the status code to prove the mapping is correct?
5. Why must tenant scope come from the authenticated identity?
6. When can the ResourceInfo rich error detail leak data?

Testing NOT_FOUND properly helps clients distinguish missing resources from request errors and infrastructure failures, while protecting data and keeping API behavior consistent.
