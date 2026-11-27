# Converting Requests into Commands or Queries

## 1. The Service Adapter as the Boundary Between gRPC and the Application

In **SPRING_GRPC**, Protocol Buffers describe services and messages on the wire; generated Java code provides base classes, request/response types, and stubs. On the server side, Spring registers the implementation of the generated service to receive RPCs. This implementation class usually acts as an **inbound service adapter**: converting gRPC requests into business intent and invoking the corresponding use case.

The adapter sits between two models:

- **Transport model:** protobuf messages, metadata, gRPC status, `StreamObserver`.
- **Application model:** commands, queries, use case results, and business errors.

Typical processing flow:

~~~mermaid
flowchart LR
    A["gRPC request / protobuf"] --> B["Spring gRPC adapter"]
    B --> C["Validate and map"]
    C --> D{"Intent"}
    D -->|State change| E["Command"]
    D -->|Read data| F["Query"]
    E --> G["Application use case"]
    F --> G
    G --> H["Result / business error"]
    H --> I["Map to protobuf response / gRPC status"]
    I --> J["Client"]
~~~

The adapter should not contain business rules or access the database directly. Its job is to understand the gRPC contract, transform data, and invoke the right application port.

## 2. Distinguishing Commands and Queries

Commands and queries express two different intents:

| Kind | Purpose | RPC examples | Typical result |
|---|---|---|---|
| **Command** | Requests a business state change | `CreateOrder`, `CancelOrder`, `ConfirmPayment` | Resource ID, new status, or processing outcome |
| **Query** | Reads data without requesting a state change | `GetOrder`, `ListOrders`, `FindAvailableSlots` | A view or a list of data |

Do not classify solely based on HTTP/gRPC method or verb name. Consider the business meaning: `GetOrder` is a query; `ReserveInventory` is a command because it reserves stock and alters state.

Commands may be resent due to retries or when the client does not receive a response. If an operation produces side effects, the contract should include an idempotency key or duplicate-handling rules. Queries are generally safer to retry, though consistency requirements and access permissions still need to be defined.

## 3. Do Not Use Protobuf Requests as Application Commands

Protobuf messages are the public communication contract. Commands/queries are the application's internal model. The two models have different lifecycles and purposes:

- Protobuf must preserve compatibility between clients and servers across versions.
- Commands/queries should reflect current business intent and rules.
- An RPC may accept multiple transport fields yet need only some of them to construct a command.
- A command may be invoked from gRPC, REST, a message consumer, or an internal job.

Passing `CreateOrderRequest` directly into a use case makes the application layer depend on generated protobuf classes. When packages, fields, or wire schemas change, those changes can leak into the domain/application even if the business logic has not changed.

Convert requests into dedicated DTOs/records before invoking the use case. Do not pass `StreamObserver`, `Metadata`, `StatusRuntimeException`, or `ServerCall` into the application layer.

## 4. Protobuf Contract Example

An order management service might declare both command RPCs and query RPCs:

~~~proto
syntax = "proto3";

package orders.v1;

option java_multiple_files = true;
option java_package = "com.example.orders.rpc";

service OrdersService {
  rpc CreateOrder(CreateOrderRequest) returns (CreateOrderReply);
  rpc GetOrder(GetOrderRequest) returns (GetOrderReply);
}

message OrderLine {
  string sku = 1;
  int32 quantity = 2;
}

message CreateOrderRequest {
  string customer_id = 1;
  repeated OrderLine lines = 2;
  string idempotency_key = 3;
}

message CreateOrderReply {
  string order_id = 1;
  string status = 2;
}

message GetOrderRequest {
  string order_id = 1;
}

message GetOrderReply {
  string order_id = 1;
  string customer_id = 2;
  string status = 3;
}
~~~

`CreateOrder` expresses a request to create an order, so the adapter converts it into a command. `GetOrder` only reads information, so the adapter converts it into a query. Both are unary RPCs, yet they differ in intent and the use case invoked.

## 5. Defining Application Commands and Queries

The application model does not need to know about protobuf:

~~~java
import java.util.List;

public record CreateOrderCommand(
        String customerId,
        List<Line> lines,
        String idempotencyKey) {

    public CreateOrderCommand {
        lines = List.copyOf(lines);
    }

    public record Line(String sku, int quantity) {}
}

public record GetOrderQuery(String orderId) {}

public record OrderResult(String orderId, String status) {}

public record OrderView(
        String orderId,
        String customerId,
        String status) {}
~~~

Use cases accept the exact intent:

~~~java
public interface CreateOrderUseCase {
    OrderResult execute(CreateOrderCommand command);
}

public interface GetOrderUseCase {
    OrderView execute(GetOrderQuery query);
}
~~~

`CreateOrderUseCase` can check rules such as valid quantities, whether the customer is permitted to place orders, inventory, and idempotency. `GetOrderUseCase` can check permission to view the order and retrieve data. These rules belong to the application/domain layer and should not be duplicated in the adapter.

## 6. Mapping a Request to a Command

The adapter converts protobuf fields into application data types. With `proto3`, scalar fields without presence typically return default values such as an empty string or zero. Therefore, if you need to distinguish "not sent" from "sent with the default value", use `optional`, `oneof`, or a suitable schema construct expressing presence.

Mapper example:

~~~java
import java.util.List;
import java.util.stream.Collectors;

private CreateOrderCommand toCommand(CreateOrderRequest request) {
    String customerId = request.getCustomerId().trim();
    if (customerId.isEmpty()) {
        throw new IllegalArgumentException("customer_id is required");
    }

    if (request.getLinesCount() == 0) {
        throw new IllegalArgumentException("at least one order line is required");
    }

    List<CreateOrderCommand.Line> lines =
            request.getLinesList().stream()
                    .map(line -> new CreateOrderCommand.Line(
                            line.getSku().trim(),
                            line.getQuantity()))
                    .collect(Collectors.toList());

    String idempotencyKey = request.getIdempotencyKey().trim();
    if (idempotencyKey.isEmpty()) {
        throw new IllegalArgumentException("idempotency_key is required");
    }

    return new CreateOrderCommand(
            customerId,
            lines,
            idempotencyKey);
}
~~~

The adapter checks request structure and the prerequisites for safe conversion. Rules such as quantity greater than 0, whether an SKU is active, or customer credit limits belong to the use case/domain because they depend on business state and may need to apply across multiple adapter types.

Do not assume every empty string is invalid. Deciding which fields are required must come from the published API contract and business rules.

## 7. Mapping a Request to a Query

Queries are usually smaller than commands because they only carry read criteria:

~~~java
private GetOrderQuery toQuery(GetOrderRequest request) {
    String orderId = request.getOrderId().trim();
    if (orderId.isEmpty()) {
        throw new IllegalArgumentException("order_id is required");
    }
    return new GetOrderQuery(orderId);
}
~~~

If a query includes pagination, filtering, or sorting, convert those fields into meaningful application types. Validate `page_size` bounds, normalize sort fields, and avoid passing caller-supplied SQL expressions or column names directly into repositories.

Queries should not cause business side effects. Technical activities such as metrics, tracing, or cache reads do not turn a query into a command, but if an RPC alters state such as "mark as read", that is a separate command.

## 8. Implementing the Spring gRPC Adapter

With a Spring gRPC starter providing the `@GrpcService` annotation, the adapter can extend the generated `OrdersServiceGrpc.OrdersServiceImplBase` and inject the use cases:

~~~java
import io.grpc.Status;
import io.grpc.stub.StreamObserver;
import org.springframework.grpc.server.service.GrpcService;

@GrpcService
public class OrdersGrpcAdapter
        extends OrdersServiceGrpc.OrdersServiceImplBase {

    private final CreateOrderUseCase createOrder;
    private final GetOrderUseCase getOrder;

    public OrdersGrpcAdapter(
            CreateOrderUseCase createOrder,
            GetOrderUseCase getOrder) {
        this.createOrder = createOrder;
        this.getOrder = getOrder;
    }

    @Override
    public void createOrder(
            CreateOrderRequest request,
            StreamObserver<CreateOrderReply> observer) {
        try {
            CreateOrderCommand command = toCommand(request);
            OrderResult result = createOrder.execute(command);

            CreateOrderReply reply = CreateOrderReply.newBuilder()
                    .setOrderId(result.orderId())
                    .setStatus(result.status())
                    .build();

            observer.onNext(reply);
            observer.onCompleted();
        } catch (RuntimeException ex) {
            observer.onError(toGrpcError(ex));
        }
    }

    @Override
    public void getOrder(
            GetOrderRequest request,
            StreamObserver<GetOrderReply> observer) {
        try {
            GetOrderQuery query = toQuery(request);
            OrderView result = getOrder.execute(query);

            GetOrderReply reply = GetOrderReply.newBuilder()
                    .setOrderId(result.orderId())
                    .setCustomerId(result.customerId())
                    .setStatus(result.status())
                    .build();

            observer.onNext(reply);
            observer.onCompleted();
        } catch (RuntimeException ex) {
            observer.onError(toGrpcError(ex));
        }
    }
}
~~~

The example uses the Spring gRPC annotation package name; if a project uses a different starter, the annotation and service registration mechanism may differ. The core pattern remains the same: the generated service implementation acts as the adapter, injects use cases, and converts bidirectionally between protobuf and the application model.

For a unary RPC, invoke only one of the two terminal sequences:

- Success: `onNext(response)` followed by `onCompleted()`.
- Failure: `onError(error)`.

Do not call `onCompleted()` after `onError()`, do not send multiple responses for a unary RPC, and do not send a response after the call has been cancelled.

## 9. Mapping Application Results to Protobuf Responses

The response mapper turns the use case result into the wire contract:

~~~java
private GetOrderReply toProto(OrderView view) {
    return GetOrderReply.newBuilder()
            .setOrderId(view.orderId())
            .setCustomerId(view.customerId())
            .setStatus(view.status())
            .build();
}
~~~

In production code, extract the mapper into a separate class when there are many fields, enums, nested messages, or mappings reused across multiple RPCs. Keeping mappings clear lets the protobuf schema evolve without cluttering use cases.

Key considerations:

- Map enums using an explicit conversion table; protobuf may contain `UNRECOGNIZED`.
- Convert `Instant`/`Duration` to `google.protobuf.Timestamp`/`Duration` via helpers that check valid ranges.
- Do not return persistence entities or lazy proxies directly.
- Include only fields the caller is authorized to see in the response.
- Preserve protobuf compatibility when adding fields; never reuse deleted field numbers.

## 10. Translating Business Errors into gRPC Statuses

The adapter is the proper boundary to map application errors to gRPC statuses. For example:

| Error/condition | Typical appropriate gRPC status |
|---|---|
| Request missing required field or malformed | `INVALID_ARGUMENT` |
| Order not found | `NOT_FOUND` |
| Order already exists for unique key | `ALREADY_EXISTS` |
| Current state does not allow the operation | `FAILED_PRECONDITION` |
| Caller lacks permission to perform action | `PERMISSION_DENIED` |
| Identity is unauthenticated | `UNAUTHENTICATED` |
| System temporarily unavailable | `UNAVAILABLE` |
| Unexpected failure | `INTERNAL` |

Centralized mapper example:

~~~java
private RuntimeException toGrpcError(RuntimeException error) {
    if (error instanceof IllegalArgumentException) {
        return Status.INVALID_ARGUMENT
                .withDescription(error.getMessage())
                .asRuntimeException();
    }
    if (error instanceof OrderNotFoundException) {
        return Status.NOT_FOUND
                .withDescription("Order was not found")
                .asRuntimeException();
    }
    if (error instanceof OrderAlreadyExistsException) {
        return Status.ALREADY_EXISTS
                .withDescription("Order already exists")
                .asRuntimeException();
    }

    // Log details on the server; do not send internal exceptions to the client.
    log.error("Unexpected failure in Orders gRPC adapter", error);
    return Status.INTERNAL
            .withDescription("Unable to process order request")
            .asRuntimeException();
}
~~~

Do not map every exception to `INVALID_ARGUMENT`. Do not put SQL, stack traces, internal hostnames, tokens, or sensitive information into `description`. Metadata/trailers may carry controlled application error codes, but clients should still rely on status codes and a stable error contract.

## 11. Validation, Authorization, and Metadata

Validation in the adapter should be limited to request structure and convertibility. Business rules belong in the use case. Authorization must be performed using the authenticated identity, not a `customer_id` or `user_id` self-reported by the caller.

One way to organize this:

- An authentication interceptor verifies credentials and places the principal into `io.grpc.Context`.
- The adapter reads the principal from context or receives it through an application abstraction.
- The use case checks permissions on the resource and action.
- Request fields only describe the resource/target the caller wants to operate on.

For instance, a caller sending `customer_id = C-10` does not prove the caller is authorized to create orders for C-10. Permissions must be verified against the principal and policy.

Metadata should not be mixed into commands if it is purely transport data such as correlation IDs or trace context. If a value carries business meaning and must be persisted/audited, convert it into a strongly typed application input after verifying its source.

## 12. Transactions and Idempotency Belong in the Right Layer

The adapter should not open a database transaction wrapping mapping and use case invocation. Transactions belong at the application service/use case or an application-coordinated infrastructure boundary that can encompass all business changes.

For commands with side effects, such as `CreateOrder`, retries can cause the same request to arrive at the server multiple times if a response is lost. An idempotency key should:

1. Be present in the request contract if clients need safe retries.
2. Be mapped into the command.
3. Be checked and stored alongside the result by the use case within an appropriate transaction.
4. Return the previously created result if the same key is sent again.

Do not generate a new idempotency key inside the adapter for each attempt; doing so turns every retry into a new operation. Queries do not need idempotency keys in most cases, though they may require snapshots/cursors if results must remain consistent across reads.

## 13. Blocking, Async, and Streaming

The adapter example above invokes use cases synchronously. This is suitable when the server executor is adequately sized and processing time is bounded. If a use case performs slow I/O or the system uses reactive/event-driven execution, do not block the event loop; use async APIs and send `onNext`/`onCompleted` when the result completes.

For server-streaming RPCs, requests are typically converted into a query/subscription:

~~~text
WatchOrderRequest
       |
       v
WatchOrderQuery
       |
       v
Application stream / event source
       |
       v
Map each event to a protobuf message
       |
       v
StreamObserver.onNext(...)
~~~

A stream emits multiple `onNext` calls followed by a single terminal signal (`onCompleted` or `onError`). When the client cancels the call or the deadline expires, the adapter/use case must stop the subscription and release resources. Do not store a `StreamObserver` in a singleton field shared across RPCs; an observer belongs to a specific call.

## 14. Testing the Adapter

Adapter testing focuses on contract conversion and statuses, while business rules are tested thoroughly at the use case level:

| Scenario | What to verify |
|---|---|
| Valid `CreateOrderRequest` | Command has the expected customer, lines, and idempotency key |
| Request missing customer ID or lines | Returns `INVALID_ARGUMENT`; use case is not called |
| Business-invalid quantity | Use case rejects it and adapter maps the error properly |
| Valid `GetOrderRequest` | Query has the expected order ID |
| Use case throws `OrderNotFoundException` | Client receives `NOT_FOUND` |
| Use case throws unexpected error | Client receives `INTERNAL`; details are logged on the server |
| Response mapping | Protobuf response has the exact expected fields and enums |
| Caller lacks permission | No data returned; appropriate status |
| Client cancels RPC | Work can be stopped and no response is sent after cancellation |
| Command retry with same idempotency key | Side effects are not duplicated |

You can use generated stubs and an in-process gRPC server to test the adapter end-to-end without opening network ports. For real TLS, metadata authentication, deadlines, and cancellation, add integration tests matching the deployed transport.

## 15. Common Design Mistakes

| Mistake | Consequence | Fix |
|---|---|---|
| Passing protobuf requests into domain/use cases | Application depends on wire contract | Map to dedicated commands/queries |
| Placing business rules in the adapter | Rules get duplicated when REST/message adapters exist | Move into use case/domain |
| Calling repositories directly from generated service | Adapter handles both transport and persistence orchestration | Inject application use cases |
| Treating every RPC as a command | Queries get mixed with state-mutating operations | Classify by business intent |
| Mapping all exceptions to `INVALID_ARGUMENT` | Clients cannot distinguish request errors from server errors | Use a centralized status mapper |
| Sending internal exceptions in status description | Leaks system details | Log internally, return safe messages |
| Trusting client-sent `customer_id` as identity | Risk of cross-tenant access | Authenticate principal and check permissions |
| Generating a new idempotency key in the adapter | Retries can repeat side effects | Keep key stable across the logical operation |
| Storing `StreamObserver` in a singleton | State leaks between calls | Keep observer scoped to the RPC |

**Key takeaway:** A Spring gRPC service adapter is the inbound boundary that converts protobuf requests into commands or queries, invokes application use cases, and maps results/errors back into protobuf responses or gRPC statuses. Commands express state changes; queries express data reads. Keep protobuf at the transport layer, business rules and transactions in the application/domain, authenticate the principal before checking permissions, and design idempotency for commands with side effects.
