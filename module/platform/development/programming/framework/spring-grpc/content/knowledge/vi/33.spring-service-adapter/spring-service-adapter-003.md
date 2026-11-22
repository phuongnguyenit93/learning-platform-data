# Chuyển request thành command hoặc query

## 1. Service adapter là ranh giới giữa gRPC và ứng dụng

Trong **SPRING_GRPC**, Protocol Buffers mô tả service và message trên wire; mã Java được sinh ra cung cấp base class, request/response type và stub. Ở phía server, Spring đăng ký implementation của generated service để nhận RPC. Lớp implementation này thường đóng vai trò **inbound service adapter**: chuyển request gRPC thành ý định nghiệp vụ rồi gọi use case tương ứng.

Adapter đứng giữa hai mô hình:

- **Transport model:** protobuf message, metadata, gRPC status, `StreamObserver`.
- **Application model:** command, query, kết quả use case và lỗi nghiệp vụ.

Luồng xử lý điển hình:

~~~mermaid
flowchart LR
    A["gRPC request / protobuf"] --> B["Spring gRPC adapter"]
    B --> C["Validate và map"]
    C --> D{"Ý định"}
    D -->|Thay đổi trạng thái| E["Command"]
    D -->|Đọc dữ liệu| F["Query"]
    E --> G["Application use case"]
    F --> G
    G --> H["Kết quả / lỗi nghiệp vụ"]
    H --> I["Map sang protobuf response / gRPC status"]
    I --> J["Client"]
~~~

Adapter không nên chứa quy tắc nghiệp vụ hoặc truy cập database trực tiếp. Nhiệm vụ của nó là hiểu hợp đồng gRPC, chuyển đổi dữ liệu và gọi đúng application port.

## 2. Phân biệt command và query

Command và query biểu đạt hai ý định khác nhau:

| Loại | Mục đích | Ví dụ RPC | Kết quả thường gặp |
|---|---|---|---|
| **Command** | Yêu cầu thay đổi trạng thái nghiệp vụ | `CreateOrder`, `CancelOrder`, `ConfirmPayment` | ID tài nguyên, trạng thái mới hoặc kết quả xử lý |
| **Query** | Đọc dữ liệu, không yêu cầu thay đổi trạng thái | `GetOrder`, `ListOrders`, `FindAvailableSlots` | Một view hoặc danh sách dữ liệu |

Không phân loại chỉ dựa trên HTTP/gRPC method hoặc tên động từ. Hãy xét ý nghĩa nghiệp vụ: `GetOrder` là query; `ReserveInventory` là command vì nó giữ chỗ tồn kho và thay đổi trạng thái.

Command có thể bị gửi lại do retry hoặc client không nhận được response. Nếu thao tác tạo side effect, hợp đồng nên có idempotency key hoặc quy tắc chống xử lý trùng. Query thường dễ gọi lại hơn, nhưng vẫn cần xác định yêu cầu consistency và quyền truy cập.

## 3. Không dùng protobuf request làm application command

Protobuf message là hợp đồng giao tiếp công khai. Command/query là mô hình nội bộ của ứng dụng. Hai mô hình có vòng đời và mục đích khác nhau:

- Protobuf phải giữ tương thích giữa client và server qua nhiều phiên bản.
- Command/query nên phản ánh ý định và quy tắc nghiệp vụ hiện tại.
- Một RPC có thể nhận nhiều field transport nhưng chỉ cần một số field để tạo command.
- Một command có thể được gọi từ gRPC, REST, message consumer hoặc tác vụ nội bộ.

Nếu truyền thẳng `CreateOrderRequest` vào use case, tầng ứng dụng sẽ phụ thuộc generated protobuf class. Khi đổi package, field hoặc schema wire, thay đổi có thể lan vào domain/application dù nghiệp vụ không đổi.

Hãy chuyển request thành DTO/record riêng trước khi gọi use case. Không đưa `StreamObserver`, `Metadata`, `StatusRuntimeException` hoặc `ServerCall` vào application layer.

## 4. Ví dụ hợp đồng protobuf

Một service quản lý đơn hàng có thể khai báo command RPC và query RPC:

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

`CreateOrder` biểu đạt yêu cầu tạo đơn nên adapter chuyển thành command. `GetOrder` chỉ đọc thông tin nên adapter chuyển thành query. Cả hai đều là unary RPC, nhưng khác nhau về ý định và use case được gọi.

## 5. Định nghĩa application command và query

Application model không cần biết protobuf:

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

Use case nhận đúng ý định:

~~~java
public interface CreateOrderUseCase {
    OrderResult execute(CreateOrderCommand command);
}

public interface GetOrderUseCase {
    OrderView execute(GetOrderQuery query);
}
~~~

`CreateOrderUseCase` có thể kiểm tra quy tắc như số lượng hợp lệ, khách hàng được phép đặt hàng, tồn kho và idempotency. `GetOrderUseCase` có thể kiểm tra quyền xem đơn và truy xuất dữ liệu. Những quy tắc này thuộc application/domain layer, không nên được nhân đôi trong adapter.

## 6. Map request thành command

Adapter chuyển các field protobuf thành kiểu dữ liệu application. Với `proto3`, scalar field không có presence thường trả về giá trị mặc định như chuỗi rỗng hoặc số 0. Vì vậy, nếu cần phân biệt “không gửi” với “gửi giá trị mặc định”, hãy dùng `optional`, `oneof` hoặc một cấu trúc biểu đạt presence phù hợp trong schema.

Ví dụ mapper:

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

Adapter kiểm tra cấu trúc request và những điều kiện cần để chuyển đổi an toàn. Quy tắc như quantity phải lớn hơn 0, SKU còn bán hoặc khách hàng có hạn mức thuộc use case/domain vì chúng phụ thuộc nghiệp vụ và có thể cần áp dụng từ nhiều loại adapter.

Không mặc định mọi chuỗi rỗng đều sai. Quyết định field nào bắt buộc phải xuất phát từ hợp đồng API và quy tắc nghiệp vụ đã công bố.

## 7. Map request thành query

Query thường nhỏ hơn command vì chỉ mang tiêu chí đọc:

~~~java
private GetOrderQuery toQuery(GetOrderRequest request) {
    String orderId = request.getOrderId().trim();
    if (orderId.isEmpty()) {
        throw new IllegalArgumentException("order_id is required");
    }
    return new GetOrderQuery(orderId);
}
~~~

Nếu query có phân trang, bộ lọc hoặc sắp xếp, chuyển các field đó sang kiểu application rõ nghĩa. Cần kiểm tra giới hạn `page_size`, chuẩn hóa sort field và tránh đưa trực tiếp một biểu thức SQL hoặc tên cột do caller cung cấp vào repository.

Query không nên gây side effect nghiệp vụ. Các hoạt động kỹ thuật như metrics, tracing hoặc cache read không làm query trở thành command, nhưng nếu một RPC thay đổi trạng thái như “đánh dấu đã đọc” thì đó là command riêng.

## 8. Implementation của Spring gRPC adapter

Với Spring gRPC starter cung cấp annotation `@GrpcService`, adapter có thể kế thừa generated `OrdersServiceGrpc.OrdersServiceImplBase` và inject các use case:

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

Ví dụ dùng tên package annotation của Spring gRPC; nếu dự án dùng starter khác, annotation và cơ chế đăng ký service có thể khác. Phần quan trọng không đổi: generated service implementation là adapter, inject use case và chuyển đổi hai chiều giữa protobuf với application model.

Với unary RPC, chỉ gọi một trong hai chuỗi kết thúc:

- Thành công: `onNext(response)` rồi `onCompleted()`.
- Thất bại: `onError(error)`.

Không gọi `onCompleted()` sau `onError()`, không gửi nhiều response cho unary RPC và không gửi response sau khi call đã bị hủy.

## 9. Map kết quả application thành protobuf response

Response mapper chuyển kết quả use case thành wire contract:

~~~java
private GetOrderReply toProto(OrderView view) {
    return GetOrderReply.newBuilder()
            .setOrderId(view.orderId())
            .setCustomerId(view.customerId())
            .setStatus(view.status())
            .build();
}
~~~

Trong code thực tế, nên tách mapper thành class riêng nếu có nhiều field, enum, nested message hoặc mapping được dùng ở nhiều RPC. Giữ mapping rõ ràng giúp thay đổi protobuf schema mà không làm rối use case.

Một số lưu ý:

- Map enum bằng bảng chuyển đổi tường minh; protobuf có thể có giá trị `UNRECOGNIZED`.
- Chuyển `Instant`/`Duration` sang `google.protobuf.Timestamp`/`Duration` qua helper có kiểm tra miền giá trị.
- Không trả trực tiếp persistence entity hoặc lazy proxy.
- Chỉ đưa field mà caller được phép xem vào response.
- Giữ tương thích protobuf khi thêm field; không tái sử dụng field number đã xóa.

## 10. Chuyển lỗi nghiệp vụ thành gRPC status

Adapter là ranh giới phù hợp để ánh xạ lỗi application sang status gRPC. Ví dụ:

| Lỗi/điều kiện | gRPC status thường phù hợp |
|---|---|
| Request thiếu field bắt buộc hoặc sai định dạng | `INVALID_ARGUMENT` |
| Không tìm thấy đơn hàng | `NOT_FOUND` |
| Đơn đã tồn tại theo khóa duy nhất | `ALREADY_EXISTS` |
| Trạng thái hiện tại không cho phép thao tác | `FAILED_PRECONDITION` |
| Caller không có quyền thực hiện | `PERMISSION_DENIED` |
| Chưa xác thực được danh tính | `UNAUTHENTICATED` |
| Hệ thống tạm thời không phục vụ | `UNAVAILABLE` |
| Lỗi ngoài dự kiến | `INTERNAL` |

Ví dụ mapper tập trung:

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

    // Ghi log chi tiết ở server; không gửi exception nội bộ cho client.
    log.error("Unexpected failure in Orders gRPC adapter", error);
    return Status.INTERNAL
            .withDescription("Unable to process order request")
            .asRuntimeException();
}
~~~

Không ánh xạ mọi exception thành `INVALID_ARGUMENT`. Không đưa SQL, stack trace, hostname nội bộ, token hoặc thông tin nhạy cảm vào `description`. Có thể dùng metadata/trailers cho mã lỗi ứng dụng đã được kiểm soát, nhưng client vẫn phải dựa vào status code và hợp đồng lỗi ổn định.

## 11. Validation, authorization và metadata

Validation ở adapter nên giới hạn ở cấu trúc và khả năng chuyển đổi request. Quy tắc nghiệp vụ nằm trong use case. Authorization cần được thực hiện dựa trên danh tính đã xác thực, không dựa vào `customer_id` hoặc `user_id` do caller tự gửi.

Một cách tổ chức:

- Authentication interceptor xác minh credential và đưa principal vào `io.grpc.Context`.
- Adapter lấy principal từ context hoặc nhận qua abstraction của ứng dụng.
- Use case kiểm tra quyền trên tài nguyên và hành động.
- Request field chỉ mô tả tài nguyên/đối tượng caller muốn thao tác.

Ví dụ caller gửi `customer_id = C-10` không chứng minh caller có quyền tạo đơn cho C-10. Quyền phải được xác minh theo principal và policy.

Metadata không nên được trộn vào command nếu đó chỉ là dữ liệu transport như correlation ID hoặc trace context. Nếu một giá trị có ý nghĩa nghiệp vụ và cần được lưu/audit, hãy chuyển nó thành input application có kiểu rõ ràng sau khi xác thực nguồn.

## 12. Transaction và idempotency thuộc đúng tầng

Adapter không nên mở transaction database để bao quanh mapping và gọi use case. Transaction nên nằm ở application service/use case hoặc infrastructure boundary được application điều phối, nơi có thể bao quát toàn bộ thay đổi nghiệp vụ.

Với command có side effect, ví dụ `CreateOrder`, retry có thể khiến cùng request đến server nhiều lần nếu response bị mất. Idempotency key nên:

1. Có trong request contract nếu client cần retry an toàn.
2. Được map vào command.
3. Được use case kiểm tra và lưu cùng kết quả trong một transaction phù hợp.
4. Trả lại kết quả đã tạo nếu cùng key được gửi lại.

Không tự tạo idempotency key mới trong adapter cho mỗi attempt; làm vậy sẽ biến retry thành operation mới. Query không cần idempotency key trong đa số trường hợp, nhưng có thể cần snapshot/cursor nếu kết quả phải nhất quán giữa các lần đọc.

## 13. Blocking, async và streaming

Ví dụ adapter phía trên gọi use case đồng bộ. Cách này phù hợp nếu server executor được cấu hình đủ năng lực và thời gian xử lý có giới hạn. Nếu use case thực hiện I/O chậm hoặc hệ thống dùng reactive/event-driven execution, không block event loop; có thể dùng API bất đồng bộ và gửi `onNext`/`onCompleted` khi kết quả hoàn tất.

Với server-streaming RPC, request thường được chuyển thành query/subscription:

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
Map từng event thành protobuf message
       |
       v
StreamObserver.onNext(...)
~~~

Một stream có nhiều `onNext` rồi một terminal signal (`onCompleted` hoặc `onError`). Khi client hủy call hoặc deadline hết, adapter/use case cần dừng subscription và giải phóng tài nguyên. Không giữ `StreamObserver` trong singleton field dùng chung giữa các RPC; observer thuộc một call cụ thể.

## 14. Kiểm thử adapter

Kiểm thử adapter tập trung vào chuyển đổi hợp đồng và status, còn quy tắc nghiệp vụ được kiểm thử sâu ở use case:

| Tình huống | Điều cần xác minh |
|---|---|
| `CreateOrderRequest` hợp lệ | Command có đúng customer, lines và idempotency key |
| Request thiếu customer ID hoặc lines | Trả `INVALID_ARGUMENT`; use case không được gọi |
| Quantity không hợp lệ theo nghiệp vụ | Use case từ chối và adapter map lỗi đúng |
| `GetOrderRequest` hợp lệ | Query có đúng order ID |
| Use case trả `OrderNotFoundException` | Client nhận `NOT_FOUND` |
| Use case phát sinh lỗi ngoài dự kiến | Client nhận `INTERNAL`; chi tiết được log ở server |
| Response mapping | Protobuf response có đúng field và enum |
| Caller không có quyền | Không trả dữ liệu; status phù hợp |
| Client hủy RPC | Công việc có thể dừng và không gửi response sau cancellation |
| Retry command cùng idempotency key | Side effect không bị thực hiện trùng |

Có thể dùng generated stub và in-process gRPC server để kiểm tra end-to-end adapter mà không cần mở port mạng. Với TLS, metadata authentication, deadline và cancellation thực tế, bổ sung integration test phù hợp với transport đang triển khai.

## 15. Những lỗi thiết kế thường gặp

| Lỗi | Hậu quả | Cách khắc phục |
|---|---|---|
| Truyền protobuf request vào domain/use case | Application phụ thuộc wire contract | Map sang command/query riêng |
| Đặt business rule trong adapter | Quy tắc bị lặp khi có REST/message adapter | Đưa vào use case/domain |
| Gọi repository trực tiếp từ generated service | Adapter vừa xử lý transport vừa điều phối persistence | Inject application use case |
| Gọi mọi RPC là command | Query bị trộn với thao tác thay đổi state | Phân loại theo ý định nghiệp vụ |
| Map mọi exception thành `INVALID_ARGUMENT` | Client không phân biệt lỗi request và lỗi server | Dùng status mapper tập trung |
| Gửi exception nội bộ trong status description | Rò rỉ chi tiết hệ thống | Log nội bộ, trả thông báo an toàn |
| Tin `customer_id` do client gửi là danh tính | Có thể truy cập chéo tenant | Xác thực principal và kiểm tra quyền |
| Tạo idempotency key mới trong adapter | Retry có thể lặp side effect | Giữ key ổn định xuyên suốt logical operation |
| Giữ `StreamObserver` trong singleton | Lẫn trạng thái giữa các call | Giữ observer trong phạm vi RPC |

**Ghi nhớ:** Spring gRPC service adapter là inbound boundary chuyển protobuf request thành command hoặc query, gọi application use case và map kết quả/lỗi trở lại protobuf response hoặc gRPC status. Command biểu đạt thay đổi trạng thái; query biểu đạt đọc dữ liệu. Giữ protobuf ở tầng transport, business rule và transaction ở application/domain, xác thực principal trước khi kiểm tra quyền, đồng thời thiết kế idempotency cho command có side effect.
