# Adding Deadlines and Controlled Retries

In this project, you will build a Spring client calling the unary `GetOrder` RPC on a Spring gRPC service. The client sets a deadline on every call and configures bounded retries when the server returns `UNAVAILABLE`. You will test transient failure recovery, non-retryable errors, and dependencies that exceed the allowed time budget.

The goal is to protect response times and system resources when a downstream dependency fails. Retries are only helpful when an operation can be safely re-executed and time budget remains. Unbounded retry policies can amplify load right when the system is already overloaded.

## 1. Expected Outcomes

After completing this lesson, you will be able to:

- Define a unary RPC with Protocol Buffers and implement the server using Spring gRPC.
- Create a Spring-managed `ManagedChannel` and instantiate blocking stubs.
- Set per-RPC deadlines using `withDeadlineAfter`.
- Configure a retry policy per service and method, specifying max attempts, backoff, and retryable statuses.
- Distinguish a single logical client call from multiple attempts received by the server.
- Test `UNAVAILABLE`, `DEADLINE_EXCEEDED`, `NOT_FOUND`, and cancellation behavior.
- Explain when an idempotency key is required instead of retrying directly.

## 2. Problem Statement and Scope

An order management application needs to fetch order details from `OrderService`. During deployments or temporary dependency outages, the server may return `UNAVAILABLE`. The client should retry a bounded number of times with increasing delays. Each request must also carry a deadline so it never blocks indefinitely.

The `GetOrder` RPC is read-only and can be safely retried as long as the service preserves read semantics. The sample policy allows up to three total attempts, including the initial call, and retries only on `UNAVAILABLE`.

| Parameter | Decision |
|---|---|
| RPC | Unary `orders.v1.OrderService/GetOrder` |
| Per-call deadline | 2 seconds |
| Max attempts | 3, including the initial attempt |
| Initial backoff | 200 ms |
| Max backoff | 1 second |
| Backoff multiplier | 2 |
| Retryable statuses | `UNAVAILABLE` only |
| Non-retryable statuses in this policy | `NOT_FOUND`, `INVALID_ARGUMENT`, `UNAUTHENTICATED`, `PERMISSION_DENIED`, `DEADLINE_EXCEEDED` |

The deadline represents the total budget for the RPC, covering processing time and backoff waits between attempts. Retries stop when the budget expires, even if configured attempts remain.

## 3. Project Structure

Organize the code within your existing module layout. A reference layout:

```text
src/main/proto/
  order_service.proto

src/main/java/com/example/orders/
  server/OrderGrpcService.java
  server/OrderRepository.java
  client/GrpcClientConfiguration.java
  client/OrderClient.java

src/test/java/com/example/orders/
  OrderClientRetryIntegrationTest.java
```

Use the Spring gRPC version and protobuf codegen plugin managed by your project. This exercise focuses on the gRPC Java APIs; protobuf plugin configuration and dependencies must match your Spring gRPC version.

## 4. Declaring the Protobuf Contract

Create `src/main/proto/order_service.proto`:

```protobuf
syntax = "proto3";

package orders.v1;

option java_multiple_files = true;
option java_package = "com.example.orders.grpc";
option java_outer_classname = "OrderServiceProto";

service OrderService {
  rpc GetOrder(GetOrderRequest) returns (GetOrderResponse);
}

message GetOrderRequest {
  string order_id = 1;
}

message GetOrderResponse {
  string order_id = 1;
  string status = 2;
  int64 total_amount = 3;
  string currency = 4;
}
```

After building, the protobuf plugin generates `OrderServiceGrpc`, `GetOrderRequest`, and `GetOrderResponse`. The full service name in the service config is `orders.v1.OrderService`; the method name is `GetOrder`. Both values must match the package and service in the proto file exactly.

## 5. Implementing the Spring gRPC Server

The server maps dependency errors into gRPC statuses. Transient errors map to `UNAVAILABLE`; missing orders map to `NOT_FOUND`. Never map every exception to `UNAVAILABLE`, as the client would then retry programming bugs or bad data.

The example below assumes `OrderRepository` throws `TemporaryDependencyException` when the dependency is temporarily unavailable and `OrderNotFoundException` when an order is missing:

```java
@GrpcService
public class OrderGrpcService extends OrderServiceGrpc.OrderServiceImplBase {

    private final OrderRepository orderRepository;

    public OrderGrpcService(OrderRepository orderRepository) {
        this.orderRepository = orderRepository;
    }

    @Override
    public void getOrder(
            GetOrderRequest request,
            StreamObserver<GetOrderResponse> responseObserver) {
        try {
            Order order = orderRepository.findById(request.getOrderId());

            GetOrderResponse response = GetOrderResponse.newBuilder()
                    .setOrderId(order.id())
                    .setStatus(order.status())
                    .setTotalAmount(order.totalAmount())
                    .setCurrency(order.currency())
                    .build();

            responseObserver.onNext(response);
            responseObserver.onCompleted();
        } catch (OrderNotFoundException ex) {
            responseObserver.onError(
                    Status.NOT_FOUND
                            .withDescription("Order was not found")
                            .asRuntimeException());
        } catch (TemporaryDependencyException ex) {
            responseObserver.onError(
                    Status.UNAVAILABLE
                            .withDescription("Dependency is temporarily unavailable")
                            .withCause(ex)
                            .asRuntimeException());
        } catch (Exception ex) {
            responseObserver.onError(
                    Status.INTERNAL
                            .withDescription("Unable to process request")
                            .withCause(ex)
                            .asRuntimeException());
        }
    }
}
```

`@GrpcService` registers the implementation with Spring gRPC. `Order`, `OrderRepository`, and the exception types are application classes to implement. Never send stack traces or internal dependency details in the status description; log the underlying exception on the server with a correlation ID for investigation.

With synchronous handling, an RPC deadline or cancellation does not automatically abort a blocking JDBC or HTTP call immediately. Propagate the remaining timeout downstream and use APIs that support timeouts/cancellation. With asynchronous processing, check context/cancellation before continuing work and release resources when the client cancels.

## 6. Configuring the Client Retry Policy

gRPC Java accepts retry policies via service config. In Spring, you can register the channel as a bean so Spring manages its lifecycle and injects stubs into client services. The example below uses a local address and plaintext for development:

```java
@Configuration
public class GrpcClientConfiguration {

    @Bean(destroyMethod = "shutdown")
    ManagedChannel orderChannel() {
        Map<String, Object> retryPolicy = Map.of(
                "maxAttempts", 3.0,
                "initialBackoff", "0.2s",
                "maxBackoff", "1s",
                "backoffMultiplier", 2.0,
                "retryableStatusCodes", List.of("UNAVAILABLE")
        );

        Map<String, Object> methodConfig = Map.of(
                "name", List.of(Map.of(
                        "service", "orders.v1.OrderService",
                        "method", "GetOrder"
                )),
                "retryPolicy", retryPolicy
        );

        Map<String, Object> serviceConfig = Map.of(
                "methodConfig", List.of(methodConfig)
        );

        return ManagedChannelBuilder
                .forAddress("localhost", 9090)
                .usePlaintext()
                .enableRetry()
                .defaultServiceConfig(serviceConfig)
                .build();
    }

    @Bean
    OrderServiceGrpc.OrderServiceBlockingStub orderServiceBlockingStub(
            ManagedChannel orderChannel) {
        return OrderServiceGrpc.newBlockingStub(orderChannel);
    }
}
```

Key imports include `ManagedChannel`, `ManagedChannelBuilder`, `OrderServiceGrpc`, `Configuration`, `Bean`, `List`, and `Map`. `usePlaintext()` is strictly for local/test environments. In production, configure TLS or mTLS according to your system's certificate infrastructure.

| Field | Meaning |
|---|---|
| `maxAttempts` | Maximum total attempts, including the initial call |
| `initialBackoff` | Upper bound for wait time before the first retry |
| `maxBackoff` | Maximum delay between attempts |
| `backoffMultiplier` | Multiplier applied to the wait interval after each failure |
| `retryableStatusCodes` | Only listed statuses trigger retries |
| `name` | Service/method scope to which the policy applies |

With this configuration, the expected backoff upper bound before the second attempt is 200 ms and before the third attempt is 400 ms, unless cut short by the deadline or other retry constraints. Retries can only proceed if the RPC has not passed gRPC's commit point—for example, before the server sends response headers. Once the server begins sending a response, gRPC will not arbitrarily replay that RPC.

Do not apply a blanket retry policy across every method. Declare the exact service and method that should retry, select only transient statuses, and bound attempt counts. If your architecture retries across multiple hops (client, gateway, intermediate services), compute the total multiplicative calls to avoid retry amplification during overload.

## 7. Setting Deadlines Per Call

Deadlines should match business requirements. You can take the retry-configured stub and derive a stub with a specific deadline for each call:

```java
@Service
public class OrderClient {

    private final OrderServiceGrpc.OrderServiceBlockingStub baseStub;

    public OrderClient(
            OrderServiceGrpc.OrderServiceBlockingStub baseStub) {
        this.baseStub = baseStub;
    }

    public GetOrderResponse getOrder(String orderId) {
        GetOrderRequest request = GetOrderRequest.newBuilder()
                .setOrderId(orderId)
                .build();

        try {
            return baseStub
                    .withDeadlineAfter(2, TimeUnit.SECONDS)
                    .getOrder(request);
        } catch (StatusRuntimeException ex) {
            Status.Code code = ex.getStatus().getCode();
            if (code == Status.Code.DEADLINE_EXCEEDED) {
                throw new OrderLookupTimeoutException(orderId, ex);
            }
            if (code == Status.Code.NOT_FOUND) {
                throw new OrderNotFoundException(orderId, ex);
            }
            throw ex;
        }
    }
}
```

Stubs are immutable; `withDeadlineAfter` returns a new stub without mutating the injected `baseStub`. Each call receives its own two-second deadline. `OrderLookupTimeoutException` and `OrderNotFoundException` are application-layer exceptions.

The deadline starts when the RPC begins and encompasses processing time, backoff delays, and retries. If three attempts together take more than two seconds, the RPC terminates when the deadline expires. Increasing `maxAttempts` is useless without an adequate time budget; measure real dependency latencies when tuning deadlines and backoffs.

## 8. Creating a Reproducible Transient Failure Scenario

To observe retries in action, build a fake repository for the integration environment. The repository throws a transient error on the first two calls and returns the order on the third:

```java
public final class FlakyOrderRepository implements OrderRepository {

    private final AtomicInteger attempts = new AtomicInteger();

    @Override
    public Order findById(String orderId) {
        int currentAttempt = attempts.incrementAndGet();
        if (currentAttempt <= 2) {
            throw new TemporaryDependencyException(
                    "Dependency is temporarily unavailable");
        }

        return new Order(orderId, "PAID", 125_000L, "VND");
    }

    public int attempts() {
        return attempts.get();
    }
}
```

Register this implementation in the test context instead of the real repository. The server returns `UNAVAILABLE` on the first two requests and `OK` on the third. Because the error occurs before the server sends a response, gRPC retries automatically per the configured policy.

When running the test, verify:

- The client calls `getOrder()` once.
- The server receives up to three attempts.
- The first two attempts fail with `UNAVAILABLE`.
- The third attempt returns a successful response.
- The client receives a single final result without writing a manual retry loop.

Make the test counter resettable between tests so results never depend on execution order. Never use a stateful fake repository in production.

## 9. Testing Deadlines, Retries, and Non-Retryable Statuses

Create an integration test with a real gRPC server in the test context or an in-process server/client. Use a generous enough deadline for the retry-success test so it is not flaky on slow machines:

```java
@Test
void retriesUnavailableAndReturnsSuccessfulResponse() {
    GetOrderResponse response = orderClient.getOrder("order-1001");

    assertEquals("order-1001", response.getOrderId());
    assertEquals("PAID", response.getStatus());
    assertEquals(3, flakyOrderRepository.attempts());
}
```

Add the following test scenarios:

| Scenario | Expected Result |
|---|---|
| Dependency succeeds immediately | Client receives response; server handles one attempt |
| Two `UNAVAILABLE` errors, then success | Client receives response; server handles three attempts |
| Always returns `UNAVAILABLE` | Client receives error after at most three attempts, or sooner if deadline expires |
| Returns `NOT_FOUND` | Client receives `NOT_FOUND`; no retry |
| Dependency slower than deadline | Client receives `DEADLINE_EXCEEDED`; server/dependency work stops where possible |
| Client cancels RPC | Server observes cancellation and releases associated work |

To test deadlines, create a fake repository with latency exceeding the client deadline. Avoid long `Thread.sleep()` calls in test suites if they can be replaced with latches or controllable fake dependencies. If you must simulate delay, bound wait times and always release resources in `finally`.

Example timeout status test:

```java
@Test
void deadlineStopsSlowCall() {
    OrderClient clientWithShortDeadline = createClientWithDeadline(
            Duration.ofMillis(300));

    assertThrows(
            OrderLookupTimeoutException.class,
            () -> clientWithShortDeadline.getOrder("order-slow"));
}
```

This is a test outline: `createClientWithDeadline` must be implemented in the test fixture to inject a stub with a 300 ms deadline. In production, deadlines should come from request budgets or business configuration rather than hardcoding a single value across all methods.

## 10. Understanding Idempotency Before Retrying Writes

`GetOrder` is a read operation and can be re-executed without side effects. If the problem changes to `CreateOrder`, retries could create duplicate orders if the server persisted the first write and the response was lost in transit.

For write operations, add an idempotency key to the contract:

```protobuf
message CreateOrderRequest {
  string idempotency_key = 1;
  string customer_id = 2;
  repeated OrderLine lines = 3;
}
```

The server must store the idempotency key alongside its result inside a transaction protected by a unique constraint. When the same key arrives again, return the stored result instead of re-executing the side effect. Reusing the same key with a different payload must be detected and rejected per business rules. Only after guaranteeing these semantics should you consider retrying transient errors on write RPCs.

Never blindly retry these statuses:

- `INVALID_ARGUMENT`, `NOT_FOUND`, `UNAUTHENTICATED`, and `PERMISSION_DENIED` typically require fixing the request or credentials.
- `RESOURCE_EXHAUSTED` may signal quota limits or overload; immediate retries can worsen the condition.
- `DEADLINE_EXCEEDED` does not prove the server failed to execute the side effect. For writes, the outcome may be ambiguous to the client.
- `UNAVAILABLE` is typically transient, yet still requires idempotency if the method has side effects.

## 11. Observing and Operating Retry Policies

To verify the policy works as intended, record metrics and logs on both client and server:

| Signal | Measured Side | Meaning |
|---|---|---|
| Logical call count | Client | Number of times the application invoked the RPC |
| Attempt count | Server or attempt instrumentation | Actual requests received by the server |
| `UNAVAILABLE` rate | Client and server | Severity of transient errors |
| `DEADLINE_EXCEEDED` rate | Client | Insufficient time budget or slow dependency |
| End-to-end completion latency | Client | Actual caller experience including retries and backoff |
| Retry recovery count | Client/server | Transient failures recovered via retry |

A client interceptor can observe logical calls at the client layer; a server interceptor typically sees each individual attempt sent to the server. Do not expect these two counters to match. When correlating logs, attach a stable trace/correlation ID to the logical call and include an attempt number wherever attempts can be distinguished.

Do not use order IDs, customer IDs, or idempotency keys as metric labels, as label cardinality will explode. You can include needed identifiers in access-controlled logs subject to retention policies.

Monitor post-retry latency as well. A retry policy can boost success rates while pushing p99 latency past SLOs. When that happens, revisit deadlines, backoffs, max attempts, downstream timeouts, and server capacity rather than simply raising retry counts.

## 12. Acceptance Criteria

The project is complete when all of the following are verified:

- [ ] The protobuf contract generates Java stubs and the service base class.
- [ ] The Spring gRPC server serves the unary `GetOrder` RPC.
- [ ] The client channel lifecycle is managed by Spring.
- [ ] Every `GetOrder` call sets a finite deadline.
- [ ] The retry policy applies only to the intended service/method and `UNAVAILABLE` status.
- [ ] `maxAttempts` is understood as total attempts, including the initial call.
- [ ] Two transient failures followed by success return the result within the deadline.
- [ ] `NOT_FOUND` is never retried.
- [ ] Exceeding the deadline returns `DEADLINE_EXCEEDED` and the server halts work where possible.
- [ ] Logs/metrics distinguish logical calls, attempts, statuses, and final latency.
- [ ] Write operations are never retried without proper idempotency guarantees.

## 13. Extension Exercises

1. Replace `FlakyOrderRepository` with a probabilistic HTTP dependency simulator; measure success rate and p95/p99 latency as `maxAttempts` changes.
2. Configure distinct deadlines for `GetOrder` and another RPC with longer processing time.
3. Test `RESOURCE_EXHAUSTED` and observe why the sample policy does not retry this status.
4. Add an idempotency key to `CreateOrder` and test two concurrent requests sharing the same key.
5. Simulate a server restart between attempts and verify the client completes or fails within its deadline.
6. Add a dashboard displaying logical calls, attempts, retry recoveries, `UNAVAILABLE`, and `DEADLINE_EXCEEDED`.

When tuning policies, change one parameter at a time and re-run the same test suite. Document the deadline, attempt count, backoff, retryable statuses, and resulting latency so you can explain why a new configuration improves or degrades reliability.
