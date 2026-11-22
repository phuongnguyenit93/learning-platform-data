# RPC và gRPC trong giao tiếp giữa các dịch vụ

## 1. Bài toán: gọi một chức năng nằm ở dịch vụ khác

Trong một ứng dụng nguyên khối, một thành phần Java có thể gọi phương thức của thành phần khác ngay trong cùng một JVM. Ví dụ, xử lý checkout gọi phương thức kiểm tra khả năng giữ hàng và nhận kết quả ngay. Khi tách thành Microservices, Ordering Service và Inventory Service có thể chạy trên các tiến trình, máy hoặc cụm khác nhau. Một lời gọi tương tự lúc này phải đi qua mạng, có định danh đích, giao thức, thời hạn chờ, mã hóa dữ liệu và cách xử lý lỗi.

**RPC (Remote Procedure Call)** là cách tổ chức giao tiếp để một chương trình yêu cầu một chương trình khác thực hiện một thao tác thông qua giao diện giống lời gọi hàm/thủ tục. **gRPC** là một framework RPC hiệu năng cao, đa ngôn ngữ, có hợp đồng API rõ ràng và thường dùng **Protocol Buffers (Protobuf)** làm định dạng mô tả thông điệp và dịch vụ. gRPC chuẩn sử dụng HTTP/2 làm giao thức truyền tải.

Điều quan trọng nhất khi học RPC: **một lời gọi từ xa không có đặc tính giống lời gọi trong bộ nhớ**. Nó có thể chậm, timeout, mất kết nối, bị hủy, gặp phản hồi trễ hoặc hoàn tất ở server nhưng client không nhận được kết quả. Việc cú pháp client giống gọi method chỉ là một lớp trừu tượng, không làm biến mất mạng.

### Mục tiêu sau bài học

- Giải thích sự khác nhau giữa gọi hàm nội bộ, RPC, HTTP REST và gRPC.
- Đọc và định nghĩa hợp đồng gRPC bằng file .proto.
- Hiểu stub/client, server handler, serialization, HTTP/2 và service discovery.
- Phân biệt bốn dạng lời gọi: unary, server streaming, client streaming, bidirectional streaming.
- Áp dụng deadline, cancellation, timeout, retry, idempotency và cơ chế bảo vệ khi downstream lỗi.
- Hiểu các loại gRPC status, metadata, bảo mật, versioning và observability.
- Nhận biết khi nào gRPC phù hợp và khi nào API HTTP/JSON hoặc messaging sẽ đơn giản hơn.

## 2. RPC là mô hình giao tiếp, gRPC là một cách triển khai

Hãy xét đoạn mã Java giả định:

~~~java
ReservationResult result = inventory.reserve(
    new ReserveStockCommand("ORD-1001", "SKU-1", 2)
);
~~~

Nếu inventory là một object cùng JVM, đây là một lời gọi phương thức nội bộ. Nếu inventory là một client proxy/stub nói chuyện với Inventory Service từ xa, cách viết có thể vẫn giống lời gọi method, nhưng các bước thực tế là:

1. Chương trình gọi **client stub**.
2. Stub/transport mã hóa dữ liệu yêu cầu theo hợp đồng đã thống nhất.
3. Client định tuyến đến một endpoint của Inventory Service.
4. Dữ liệu đi qua mạng; server nhận và giải mã.
5. Handler phía server thực thi nghiệp vụ, kiểm tra dữ liệu, truy cập hệ thống cần thiết.
6. Server mã hóa phản hồi hoặc gửi lỗi trạng thái.
7. Client nhận phản hồi, giải mã và trả kết quả cho caller.

~~~mermaid
sequenceDiagram
    autonumber
    participant O as Ordering application
    participant C as Inventory gRPC client stub
    participant T as Network / HTTP2
    participant S as Inventory gRPC server
    participant D as Inventory domain

    O->>C: reserveStock(orderId, sku, qty)
    C->>C: Serialize Protobuf message
    C->>T: RPC request
    T->>S: Forward request
    S->>D: Kiểm tra và giữ hàng
    D-->>S: Reservation result
    S-->>T: RPC response + status
    T-->>C: Response
    C-->>O: Typed result
~~~

**Stub** là mã khách hàng được sinh từ hợp đồng hoặc được tạo bởi framework; nó đóng gói việc chuyển method và message sang request mạng. **Server handler** là phần mã người phát triển hiện thực hành vi nghiệp vụ theo contract đó.

RPC tồn tại dưới nhiều hình thức và framework. REST/HTTP với JSON và RPC đều có thể dùng HTTP; cách khác biệt cốt lõi thường nằm ở **mô hình hợp đồng và giao tiếp**, không phải tên giao thức. Ví dụ endpoint POST /payments/charge là API HTTP có dáng một command, dù thường được gọi là REST API. Ngược lại, gRPC cũng dùng HTTP làm transport nhưng không yêu cầu mô hình tài nguyên giống REST.

### Một lời gọi từ xa có những chi phí nào?

- Thời gian mạng và định tuyến.
- Mã hóa/giải mã message.
- Thiết lập và duy trì kết nối, bảo mật TLS.
- Hàng đợi xử lý, thread pool và connection/resource limits ở server.
- Timeout, hủy và retry.
- Khả năng server hoặc phụ thuộc phía sau bị lỗi.

Vì vậy không nên biến hàng trăm lần gọi method nhỏ trong monolith thành hàng trăm lời gọi RPC trên đường nóng của cùng một request mà không xem xét ranh giới nghiệp vụ.

## 3. Ví dụ xuyên suốt: Ordering gọi Inventory

Giả sử người dùng tạo đơn ORD-1001 với hai sản phẩm SKU-BOOK-01. Ordering Service có nhiệm vụ lưu đơn và điều phối checkout; Inventory Service có nhiệm vụ quản lý số lượng khả dụng và reservation.

Khi nhận đơn, Ordering cần biết **Inventory có giữ được hàng hay không**. Ta định nghĩa một contract:

~~~text
Client: Ordering Service
Provider: Inventory Service
Operation: ReserveStock
Input: orderId, requestId, lineItems(sku, quantity)
Output: reservationId, result
Business errors: không đủ hàng, SKU không hợp lệ
Technical errors: UNAVAILABLE, DEADLINE_EXCEEDED, RESOURCE_EXHAUSTED
~~~

Một luồng thành công:

~~~mermaid
sequenceDiagram
    autonumber
    actor U as Khách hàng
    participant O as Ordering
    participant I as Inventory gRPC
    participant DB as Inventory DB

    U->>O: POST /orders
    O->>O: Tạo Order PENDING
    O->>I: ReserveStock(orderId, requestId, items)
    I->>DB: Kiểm tra và giữ hàng nguyên tử
    DB-->>I: reservationId=RES-1
    I-->>O: ReserveStockResponse(RESERVED, RES-1)
    O->>O: Cập nhật tiến trình đơn
    O-->>U: 202 Accepted / trạng thái hiện tại
~~~

Một điểm thiết kế quan trọng: nếu nghiệp vụ trả “không đủ hàng” như một kết quả được dự liệu, có thể trả một **business result** có cấu trúc. Nếu request không hợp lệ hoặc hạ tầng đang lỗi, gRPC status thích hợp có thể phản ánh lỗi giao thức/kỹ thuật. Hai cách dùng phải được định nghĩa rõ trong contract; không tùy tiện coi mọi lỗi nghiệp vụ là INTERNAL hoặc UNKNOWN.

### Vì sao chọn đồng bộ trong ví dụ này?

Ordering có thể muốn nhận kết quả giữ hàng tương đối nhanh để trả trạng thái cho người dùng. RPC unary thích hợp cho trao đổi ngắn, có deadline và hợp đồng rõ ràng.

Tuy nhiên, nếu tiến trình giữ hàng thường mất lâu hoặc đòi hỏi nhiều bước, kiến trúc bất đồng bộ có thể phù hợp hơn: Ordering phát command, nhận trạng thái đang xử lý và cập nhật khi có StockReserved/StockRejected. **RPC không bắt buộc** toàn bộ checkout phải nằm trong cùng HTTP request của khách.

## 4. Các thành phần chính của gRPC

| Thành phần | Vai trò | Cần nhớ |
| --- | --- | --- |
| File .proto | Định nghĩa schema message và service/method | Là hợp đồng giữa producer và consumer |
| Protocol Buffers | Cơ chế mã hóa/giải mã dữ liệu có kiểu | Thường nhỏ gọn, không tự làm rõ toàn bộ semantics |
| protoc + plugin | Sinh mã model và client/server stub | Nhiều ngôn ngữ cùng sử dụng contract |
| Client stub | Bề mặt gọi RPC tại client | Có synchronous/asynchronous API tùy ngôn ngữ |
| Channel | Quản lý kết nối logic tới target | Nên tái sử dụng; có resolver/LB theo cấu hình |
| Server implementation | Thực thi operation | Phải bảo vệ domain invariant và quyền truy cập |
| HTTP/2 | Transport của gRPC chuẩn | Hỗ trợ multiplexed streams, headers/trailers |
| Metadata | Gửi thông tin ngoài payload | Authentication, correlation ID, tracing |
| Deadline/cancellation | Giới hạn thời gian và chấm dứt công việc | Tránh request kéo dài làm cạn tài nguyên |
| Status code | Thông báo kết quả kỹ thuật của RPC | Khác domain result trong response |
| Interceptor/middleware | Cross-cutting logic | Auth, logging, tracing, metrics, policy |

**Protocol Buffers là schema và wire format**; nó không tự bảo đảm thông điệp an toàn, hợp đồng không breaking, hoặc request có thể retry. **gRPC là framework giao tiếp**; nó không tự biến nhiều database thành một transaction chung.

## 5. Định nghĩa hợp đồng bằng Protocol Buffers

Trong Protobuf, file .proto dùng để khai báo message với số thứ tự field và service với các method. Ví dụ contract Inventory:

~~~proto
syntax = "proto3";

package shop.inventory.v1;

option java_multiple_files = true;
option java_package = "com.example.shop.inventory.v1";
option java_outer_classname = "InventoryContract";

service InventoryService {
  rpc ReserveStock(ReserveStockRequest)
      returns (ReserveStockResponse);

  rpc GetReservation(GetReservationRequest)
      returns (GetReservationResponse);
}

message StockLine {
  string sku = 1;
  int32 quantity = 2;
}

message ReserveStockRequest {
  string order_id = 1;
  string request_id = 2;
  repeated StockLine lines = 3;
}

enum ReservationStatus {
  RESERVATION_STATUS_UNSPECIFIED = 0;
  RESERVATION_STATUS_RESERVED = 1;
  RESERVATION_STATUS_REJECTED = 2;
}

message ReserveStockResponse {
  ReservationStatus status = 1;
  string reservation_id = 2;
  string reason_code = 3;
}

message GetReservationRequest {
  string reservation_id = 1;
}

message GetReservationResponse {
  string reservation_id = 1;
  string order_id = 2;
  ReservationStatus status = 3;
}
~~~

Đây là hợp đồng **minh họa**. Một hệ thống thực tế cần quy định request_id có phạm vi duy nhất nào, response có cần timestamp/expiry/version không, có bao nhiêu reservation trên một order và trạng thái RELEASED/EXPIRED được mô hình hóa ra sao.

### Giải thích từng phần

- **syntax = "proto3"**: sử dụng cú pháp Protobuf 3.
- **package shop.inventory.v1**: không gian tên logic của message và service; v1 thể hiện nhóm hợp đồng phiên bản 1 theo quy ước nhóm.
- **java_package**: package của mã Java được sinh. Không bắt buộc phải trùng package bên trong .proto.
- **service InventoryService**: khai báo tập method có thể gọi từ xa.
- **rpc ReserveStock(...) returns (...)**: một method unary nhận một request và trả một response.
- **message StockLine**: kiểu dữ liệu có cấu trúc được truyền giữa hai bên.
- **repeated StockLine**: danh sách dòng hàng.
- **field number 1, 2, 3**: định danh field ở cấp wire format; không phải vị trí trang trí, phải quản lý cẩn thận qua các phiên bản.
- **enum giá trị 0 UNSPECIFIED**: trạng thái mặc định/chưa xác định; consumer phải xử lý tình huống dữ liệu thiếu hoặc giá trị chưa biết.

Trong Java, protoc cùng plugin gRPC Java tạo các lớp message builder, base class để triển khai server và các stub để client gọi InventoryService.

## 6. Message và schema: chú ý field number, type, presence

Ở Protobuf, field number là một phần của hợp đồng nhị phân. Khi schema đã được phát hành và có consumer, hãy quản lý thay đổi với cùng mức nghiêm ngặt như API công khai.

### Một số nguyên tắc tương thích

1. **Không đổi ý nghĩa một field cũ** nhưng giữ cùng tên và số field. Đổi từ “số lượng khả dụng” sang “số lượng đã giữ” là breaking về ngữ nghĩa dù vẫn là int32.
2. **Không tái sử dụng field number đã xóa**. Dùng reserved để chặn việc dùng lại vô tình.
3. **Không đổi type/encoding tùy ý**. Có những thay đổi type gần nhau có thể tương thích về wire trong điều kiện hẹp, nhưng cần hiểu và kiểm tra kỹ; lựa chọn an toàn thường là thêm field mới với số mới.
4. **Có quy ước cho field mới**. Consumer cũ thường có thể bỏ qua field chưa biết, nhưng việc một consumer mới **bắt buộc** field mà producer cũ chưa gửi sẽ phá khả năng chạy song song.
5. **Phân biệt absent với giá trị mặc định**. Trong proto3, nhiều scalar field mặc định không mang presence theo cách dễ hiểu như object nullable. Nếu cần phân biệt “không gửi” với “gửi 0” hoặc “không gửi” với “gửi chuỗi rỗng”, cân nhắc optional field, oneof hoặc wrapper theo nhu cầu contract.
6. **Không dùng enum ordinal làm logic kinh doanh tùy tiện**. Giá trị enum số 0 có thể xuất hiện khi field thiếu; consumer cần xử lý trường hợp không xác định và enum chưa biết.
7. **Dùng contract/version tests** khi producer và consumer có thể deploy độc lập, đặc biệt giai đoạn rolling deployment.

### Ví dụ bỏ field cũ an toàn hơn

Giả sử trước đây request có trường legacy_address; khi bỏ trường, không tái sử dụng tag:

~~~proto
message CheckoutRequest {
  string order_id = 1;
  reserved 2;
  reserved "legacy_address";
  string shipping_address_id = 3;
}
~~~

Ví dụ này cho biết field number 2 và tên legacy_address đã được dành riêng để không ai vô tình khai báo chúng cho một ý nghĩa khác. Trước khi xóa field ngoài thực tế vẫn phải xác nhận các producer/consumer đã được chuyển đổi; reserved **không tự bảo đảm** rollout an toàn.

### Về JSON mapping

Protobuf hỗ trợ cách ánh xạ sang JSON, nhưng nó không đồng nghĩa mọi JSON client có thể gọi trực tiếp gRPC chuẩn từ browser. Các bên cần thống nhất field naming, enum representation, int64 mapping và xử lý unknown fields nếu dùng JSON gateway.

## 7. Bốn kiểu gọi gRPC

gRPC hỗ trợ bốn dạng giao tiếp, thể hiện ngay trong cú pháp .proto.

### 7.1. Unary RPC: một request, một response

~~~proto
rpc GetReservation(GetReservationRequest)
    returns (GetReservationResponse);
~~~

**Phù hợp:** đọc chi tiết, kiểm tra điều kiện, tạo một resource hoặc thực hiện một command có thời gian xử lý dự kiến ngắn.

**Ví dụ:** Ordering hỏi Inventory về một reservation và nhận trạng thái hiện hành. Mỗi RPC có một kết quả hoặc một gRPC status lỗi.

### 7.2. Server streaming RPC: một request, nhiều message phản hồi

~~~proto
rpc WatchReservation(WatchReservationRequest)
    returns (stream ReservationUpdate);
~~~

**Phù hợp:** client theo dõi tiến trình hoặc nhận nhiều kết quả do server phát dần. Ví dụ một công cụ nội bộ muốn quan sát các cập nhật của reservation khi quá trình xử lý kéo dài.

Client mở stream, server gửi nhiều message cho tới khi hoàn tất hoặc bị hủy/lỗi. Không được giả định stream sống mãi; cần xác định reconnect, checkpoint và chính sách xử lý message trùng hoặc bị bỏ lỡ.

### 7.3. Client streaming RPC: nhiều message yêu cầu, một phản hồi cuối

~~~proto
rpc UploadStockChanges(stream StockChange)
    returns (UploadSummary);
~~~

**Phù hợp:** client gửi một chuỗi message trong cùng RPC và server tổng hợp/trả kết quả khi client kết thúc phần gửi.

Chú ý: stream không tự mang lại tính giao dịch nguyên tử cho toàn bộ các message. Nếu server đã ghi một số thay đổi rồi kết nối đứt, client phải biết cách đối chiếu/chạy lại an toàn. Với nghiệp vụ thay đổi tồn kho, cần transaction/idempotency ở domain tương ứng.

### 7.4. Bidirectional streaming: hai phía đều gửi nhiều message

~~~proto
rpc Synchronize(stream SyncRequest)
    returns (stream SyncResponse);
~~~

Hai phía có thể gửi message **độc lập theo thời gian** trong cùng cuộc gọi. Tùy ứng dụng, server có thể phản hồi từng request, đẩy cập nhật định kỳ hoặc gửi message không bắt cặp một-một.

**Phù hợp:** cộng tác thời gian thực, điều khiển thiết bị, đồng bộ hai chiều, luồng tương tác kéo dài.

**Không phù hợp mặc định:** CRUD đơn giản hoặc nghiệp vụ không cần kênh liên tục. Streaming làm tăng nhu cầu quản lý lifecycle, backpressure/flow control, reconnect, timeout, thứ tự và observability.

### Tổng hợp

| Kiểu | Request từ client | Response từ server | Tình huống thường gặp |
| --- | --- | --- | --- |
| Unary | 1 message | 1 message | GetOrder, ReserveStock |
| Server streaming | 1 message | Nhiều message | Theo dõi trạng thái, kết quả lớn được phát dần |
| Client streaming | Nhiều message | 1 message | Upload/summarize nhiều item |
| Bidirectional streaming | Nhiều message | Nhiều message | Đồng bộ, trao đổi thời gian thực |

**Đừng nhầm streaming với messaging bền vững.** Một gRPC stream thường gắn với kết nối/lời gọi đang sống. Nếu cần lưu event lâu dài, phát lại cho consumer offline, consumer group hoặc xử lý qua nhiều giờ, message broker/log và storage thích hợp thường đóng vai trò khác.

## 8. Đi vào một lời gọi unary chi tiết

Khi Ordering gọi InventoryService.ReserveStock, client thường thực hiện:

~~~text
Service method call
  -> generated stub
  -> Protobuf serialization
  -> gRPC framing + HTTP/2 stream
  -> TLS/HTTP2 network
  -> server gRPC runtime
  -> deserialization + interceptor
  -> service handler
  -> domain logic/database
  -> Protobuf response
  -> gRPC status/trailers
  -> client stub return/exception
~~~

### 8.1. HTTP/2 hỗ trợ những gì?

HTTP/2 cho phép nhiều stream logic cùng sử dụng một connection, hỗ trợ framing, flow control, headers/trailers và truyền tải full duplex. gRPC tận dụng những tính năng này để thực hiện unary và streaming.

Tuy nhiên, **HTTP/2 trên TCP không xóa bỏ hoàn toàn head-of-line blocking ở tầng transport** khi có packet loss, và không bảo đảm latency luôn thấp hơn mọi API HTTP/JSON. Hiệu quả phụ thuộc số request, kích thước payload, CPU encode/decode, mạng, TLS, proxy và đặc tính hệ thống.

### 8.2. Phản hồi là dữ liệu + trạng thái của RPC

Một response Protobuf có thể chứa ReservationStatus=REJECTED vì hết hàng; đó là **kết quả nghiệp vụ** được dự liệu. Nếu server không tìm thấy reservation được hỏi, có thể dùng gRPC NOT_FOUND. Nếu hệ thống không khả dụng, có thể dùng UNAVAILABLE. Hai loại phải được client xử lý khác nhau.

**Không đồng nhất HTTP status với gRPC status.** Trong gRPC chuẩn, lớp HTTP/2 và gRPC có hệ thống status riêng. Một kết nối HTTP có vẻ thành công không có nghĩa nghiệp vụ đã hoàn thành; gRPC status có thể mang lỗi trong trailers. Các proxy, monitoring và client phải hiểu giao thức gRPC thay vì chỉ nhìn mã HTTP.

## 9. Ví dụ gRPC server Java: từ contract đến domain

Một dự án dùng **grpc-java** sẽ có mã message và stub được sinh từ file .proto. Bên server triển khai base class sinh ra. Mẫu sau chỉ tập trung vào ý tưởng, giả định đã có lớp OrderReader và bản Protobuf GetOrder tương ứng:

~~~java
import io.grpc.Status;
import io.grpc.stub.StreamObserver;

public final class OrderQueryGrpcService
        extends OrderQueryServiceGrpc.OrderQueryServiceImplBase {

    private final OrderReader reader;

    public OrderQueryGrpcService(OrderReader reader) {
        this.reader = reader;
    }

    @Override
    public void getOrder(
            GetOrderRequest request,
            StreamObserver<GetOrderResponse> observer) {

        if (request.getOrderId().isBlank()) {
            observer.onError(
                Status.INVALID_ARGUMENT
                    .withDescription("order_id is required")
                    .asRuntimeException()
            );
            return;
        }

        try {
            OrderView order = reader.findById(request.getOrderId());

            GetOrderResponse response = GetOrderResponse.newBuilder()
                .setOrderId(order.id())
                .setStatus(order.status())
                .build();

            observer.onNext(response);
            observer.onCompleted();

        } catch (OrderNotFoundException ex) {
            observer.onError(
                Status.NOT_FOUND
                    .withDescription("order not found")
                    .asRuntimeException()
            );
        }
    }
}
~~~

Trong ví dụ, các lớp OrderReader, OrderView, OrderNotFoundException, OrderQueryServiceGrpc, GetOrderRequest và GetOrderResponse phải được định nghĩa/sinh từ contract của dự án. Chọn kiểu status trong .proto cho khớp với giá trị trả từ order.status() nếu sử dụng enum thay vì string.

Các nguyên tắc quan trọng:

- **Handler không nên chứa hết logic nghiệp vụ.** Nó chuyển request Protobuf thành command/query của application layer và chuyển kết quả trở lại response.
- **Validation** kiểm tra dữ liệu hợp lệ trước khi gọi domain.
- **Authorization** phải có ở boundary thích hợp, chẳng hạn service identity và quyền truy cập đơn theo tenant.
- **onNext** gửi response; **onCompleted** kết thúc RPC thành công; **onError** kết thúc với lỗi. Không gọi các terminal callback nhiều lần hoặc tiếp tục gửi sau khi kết thúc.
- Không phát nguyên stack trace hoặc dữ liệu nhạy cảm vào status description gửi cho client.
- Cần cơ chế xử lý exception chưa dự kiến ở middleware/server để không rò thông tin nội bộ.

Đoạn code trên có cấu trúc minh họa, chưa phải server production hoàn chỉnh có dependency injection, security, telemetry và thread management.

## 10. Ví dụ gRPC client Java: stub, channel và deadline

Bên client dùng generated stub. Trong ví dụ này, ứng dụng chạy môi trường local và kết nối trực tiếp để dễ học:

~~~java
import io.grpc.ManagedChannel;
import io.grpc.ManagedChannelBuilder;
import io.grpc.Status;
import io.grpc.StatusRuntimeException;

import java.util.concurrent.TimeUnit;

public final class OrderQueryClientExample {

    public static void main(String[] args) {
        ManagedChannel channel = ManagedChannelBuilder
            .forAddress("localhost", 9090)
            .usePlaintext() // Chỉ dùng cho môi trường local tin cậy
            .build();

        try {
            OrderQueryServiceGrpc.OrderQueryServiceBlockingStub stub =
                OrderQueryServiceGrpc.newBlockingStub(channel)
                    .withDeadlineAfter(800, TimeUnit.MILLISECONDS);

            GetOrderRequest request = GetOrderRequest.newBuilder()
                .setOrderId("ORD-1001")
                .build();

            GetOrderResponse response = stub.getOrder(request);
            System.out.println(response.getStatus());

        } catch (StatusRuntimeException ex) {
            if (ex.getStatus().getCode()
                    == Status.Code.DEADLINE_EXCEEDED) {
                System.err.println("Order query deadline exceeded");
            } else {
                System.err.println("RPC failed: "
                    + ex.getStatus().getCode());
            }
        } finally {
            channel.shutdown();
        }
    }
}
~~~

Mẫu trên là một chương trình standalone nên tạo channel, gọi rồi shutdown. **Trong ứng dụng server chạy lâu dài**, nên tái sử dụng ManagedChannel và stub được quản lý theo lifecycle, tránh mở một kết nối mới cho từng request. Channel là abstraction cho target và cơ chế kết nối, không nhất thiết luôn tương ứng chính xác một TCP socket trong mọi cấu hình.

Các API sinh mã, dependency/version và tên class phụ thuộc hợp đồng .proto cùng toolchain đang dùng. Ví dụ là hướng dẫn ý tưởng, không tuyên bố có sẵn dependency hoặc class trong một repository cụ thể.

### Blocking và asynchronous stub

- **Blocking stub** chờ unary response theo cách lập trình đồng bộ; phù hợp khi luồng thực thi chấp nhận chờ và có giới hạn.
- **Async stub** trả kết quả bằng callback/observer; hữu ích cho streaming và xử lý không chặn.
- **Future-style stub** có thể giúp kết hợp nhiều call và xử lý kết quả bất đồng bộ tùy ngôn ngữ.

Không nên chọn blocking stub trong một event loop không được phép block. Trong ứng dụng reactive, sử dụng adapter hoặc mô hình nonblocking phù hợp với runtime.

## 11. Deadline, timeout và cancellation

**Deadline** là thời điểm một RPC không còn hữu ích với caller. Một client có thể đặt “phải hoàn tất trong vòng 800 ms” bằng API deadline tương ứng. Nếu hết deadline, client thường nhận **DEADLINE_EXCEEDED**.

Lý do cần deadline:

1. Tránh một downstream chậm giữ thread/connection đến vô hạn.
2. Đảm bảo request đầu cuối không bị treo vì một nhánh phụ thuộc.
3. Giới hạn tiêu thụ tài nguyên trong chuỗi service.
4. Cho phép fallback hoặc trả trạng thái “chưa rõ/đang xử lý” có kiểm soát.

Ví dụ:

~~~text
Client -> Gateway: ngân sách 1500 ms
Gateway -> Ordering: ngân sách còn ~1300 ms
Ordering -> Inventory: deadline 500 ms
Ordering -> Pricing: deadline 300 ms
Ordering -> Payments: không thể áp dụng bừa timeout ngắn cho kết quả tiền
~~~

**Ngân sách thời gian** phải tính thêm thời gian xử lý và mạng; không lấy toàn bộ timeout đầu-cuối rồi gán nguyên cho mỗi downstream call nối tiếp. Framework có thể hỗ trợ lan truyền deadline giữa các service, nhưng ứng dụng phải bảo đảm cấu hình và hành vi phù hợp.

### Timeout khác lỗi nghiệp vụ

Nếu ReserveStock timeout, có thể Inventory đã commit reservation nhưng response bị mất. Ordering **không được tự mặc định** rằng reservation chưa được tạo. Cần dùng requestId/idempotency key, API tra cứu theo requestId/reservationId hoặc cơ chế reconciliation.

Đối với thao tác tài chính, timeout còn nguy hiểm hơn: client gọi ChargePayment lại với id mới có thể tạo khoản thu thứ hai. Khi kết quả không rõ, phải tra cứu hoặc retry với **cùng identity của thao tác**, theo hợp đồng idempotency.

### Cancellation không phải rollback

Client có thể hủy RPC khi user đóng trang hoặc deadline hết. Server cần kiểm tra tín hiệu hủy và dừng phần công việc không còn cần thiết khi có thể. Nhưng một transaction database đã commit, khoản thanh toán đã gửi nhà cung cấp hoặc event đã phát **không tự bị rollback** bởi việc gRPC client cancel.

Đối với công việc dài, nên định nghĩa explicit cancel command (nếu nghiệp vụ cho phép) hoặc quy trình bù, thay vì dựa vào hủy kết nối.

## 12. Giao tiếp đồng bộ và nguy cơ dependency chain

Giả sử một HTTP request cần:

~~~text
Gateway -> Ordering -> Pricing
                    -> Inventory
                    -> Payments
                    -> Shipping
~~~

Mỗi lời gọi đồng bộ tạo ra một phụ thuộc về **thời gian sẵn sàng và latency**. Nếu Ordering chờ Pricing, Inventory và Payments nối tiếp, latency đầu-cuối có thể xấp xỉ tổng thời gian các bước, cộng phần xử lý và mạng.

Với nhiều tầng gọi lồng nhau, một downstream chậm có thể lan thành request timeout ở upstream, thread pool cạn hoặc số kết nối đợi tăng.

### Các câu hỏi trước khi thêm một RPC

- Kết quả có **phải có ngay trong request của khách** không?
- Bên gọi cần dữ liệu mới đến mức nào?
- Một lời gọi thay vì mười lời gọi nhỏ có phù hợp ranh giới domain hơn không?
- Có thể chuyển công việc nền qua event/message broker không?
- Caller sẽ trả response gì nếu downstream quá deadline?
- Retry có thể gây tác động phụ không?
- Có cần đọc một projection thay vì gọi nhiều context cho từng item không?
- Có cách nào tránh dependency cycle giữa các service?

Ví dụ việc gửi email xác nhận không nên làm request đặt hàng phải đợi SMTP xong nếu thông báo có thể xử lý nền. Ngược lại, kiểm tra một quyền truy cập cực quan trọng có thể cần kết quả đồng bộ theo chính sách bảo mật.

## 13. Xử lý status code và lỗi có chủ đích

gRPC có bộ mã trạng thái chuẩn. Một số mã thường gặp:

| gRPC status | Ý nghĩa điển hình | Client nên làm gì? |
| --- | --- | --- |
| OK | RPC hoàn tất ở mức giao thức | Vẫn kiểm tra kết quả nghiệp vụ trong response |
| INVALID_ARGUMENT | Yêu cầu không hợp lệ | Sửa dữ liệu, thường không retry giống hệt |
| UNAUTHENTICATED | Chưa có credential hợp lệ | Xác thực lại/kiểm tra token theo policy |
| PERMISSION_DENIED | Đã có danh tính nhưng không đủ quyền | Không retry mù; kiểm tra quyền |
| NOT_FOUND | Tài nguyên được hỏi không tồn tại trong phạm vi hợp lệ | Xử lý “không thấy” theo nghiệp vụ |
| ALREADY_EXISTS | Tạo đối tượng đã tồn tại | Có thể là xung đột hoặc idempotency, phải theo contract |
| FAILED_PRECONDITION | Điều kiện hệ thống/nghiệp vụ tiên quyết chưa thỏa | Không coi như lỗi tạm mặc định |
| ABORTED | Thao tác bị hủy do xung đột đồng thời/transaction | Có thể retry ở cấp cao hơn nếu an toàn |
| RESOURCE_EXHAUSTED | Vượt quota/tài nguyên | Backoff, giới hạn tốc độ, giảm tải |
| UNAVAILABLE | Tạm không thể liên hệ hoặc phục vụ | Retry có giới hạn cho operation phù hợp |
| DEADLINE_EXCEEDED | Hết thời gian chờ | Kết quả server có thể chưa rõ; đối soát |
| CANCELLED | RPC bị hủy | Phân biệt client cancel và trạng thái nghiệp vụ |
| INTERNAL | Lỗi nội bộ hoặc invariant kỹ thuật | Alert/điều tra; không tự retry vô hạn |
| UNKNOWN | Không xác định được trạng thái | Ghi telemetry và tìm nguyên nhân |
| UNIMPLEMENTED | Method/operation chưa được triển khai | Kiểm tra contract/version/deployment |

**Không có một chính sách retry chung cho tất cả status.** Ví dụ UNAVAILABLE với GET thông tin có thể retry ngắn hạn; UNAVAILABLE sau ChargePayment vẫn có nguy cơ thao tác đã được thực hiện ở bên ngoài. DEADLINE_EXCEEDED đặc biệt phải được coi là **không biết chắc kết quả** khi có side effect.

### Domain error so với transport error

Ví dụ Inventory có thể trả:

~~~json
{
  "status": "RESERVATION_STATUS_REJECTED",
  "reason_code": "INSUFFICIENT_STOCK"
}
~~~

Đây là kết quả có thể tiên liệu của lệnh reserve. Với request bị thiếu orderId, server dùng INVALID_ARGUMENT. Với database tạm không khả dụng, có thể trả UNAVAILABLE. Trong thực tế, một số đội dùng richer gRPC error details hoặc domain-specific error model. Điều quan trọng là hợp đồng nêu rõ **lỗi nào thuộc dòng nghiệp vụ và lỗi nào thuộc lỗi RPC**, tránh consumer phải đoán ý nghĩa qua chuỗi description tự do.

## 14. Retry, backoff, idempotency và retry storm

Một request đến server có thể gặp lỗi trước khi thực thi, trong lúc xử lý, hoặc sau khi đã commit nhưng trước khi response tới client. Client không phải lúc nào cũng phân biệt được ba trường hợp này.

### 14.1. Retry có giới hạn

Một chính sách retry cho operation an toàn thường giới hạn số lần thử, tổng thời gian và có backoff/jitter để tránh nhiều client retry đồng loạt.

~~~text
Attempt 1 -> UNAVAILABLE
Wait (backoff + jitter)
Attempt 2 -> UNAVAILABLE
Wait longer
Attempt 3 -> OK
Stop
~~~

Ví dụ chỉ mô tả cách tiến trình có thể phục hồi. Chính sách retry thực tế còn phải tôn trọng deadline còn lại và loại operation.

### 14.2. Chống trùng cho command có side effect

Với ReserveStock, Ordering gửi:

~~~text
orderId   = ORD-1001
requestId = reserve-ORD-1001-v1
lines     = [SKU-BOOK-01 x 2]
~~~

Inventory cần lưu identity thao tác và kết quả theo **phạm vi ổn định**, đồng thời bảo vệ bằng transaction/unique constraint hoặc cơ chế nguyên tử phù hợp. Nếu request đến hai lần với cùng requestId và cùng payload, kết quả nên gắn với **cùng reservation** thay vì giữ hàng hai lần.

Nếu cùng requestId nhưng payload khác, phải có quy tắc xung đột rõ. Idempotency key cần được lưu đủ lâu theo vòng đời retry và khả năng đối soát, không chỉ trong cache local của một instance.

### 14.3. Cẩn thận retry nhiều tầng

Một hệ thống có gateway retry 3 lần, Ordering retry 3 lần và Inventory client retry 3 lần có thể nhân số request tệ hơn nhiều so với dự tính. Cần xác định **một hoặc vài vị trí** chịu trách nhiệm retry, giới hạn retry budget toàn chuỗi và bảo vệ downstream bằng rate limit/circuit breaker/bulkhead phù hợp.

**Retry không sửa được lỗi nghiệp vụ** như thiếu hàng hoặc thiếu quyền. Retry nóng còn có thể biến sự cố nhỏ thành quá tải lớn.

## 15. Tìm đúng instance: name resolution và load balancing

Client gRPC thường gọi một **target logic** như inventory-service.internal:9090. Target đó có thể đại diện cho nhiều instance đang chạy.

~~~mermaid
flowchart LR
    O[Ordering Service] --> C[gRPC Channel / Stub]
    C --> R[Resolver / Service Discovery]
    R --> A[Inventory A]
    R --> B[Inventory B]
    R --> D[Inventory C]
~~~

Sơ đồ minh họa quan hệ; đường request thực tế do client-side policy, proxy hoặc hệ thống service mesh chọn. Resolver không nhất thiết nằm trên đường dữ liệu của từng request.

Các lựa chọn phổ biến:

- **Proxy/server-side balancing:** gRPC client kết nối qua một proxy/Envoy/ingress hoặc địa chỉ service đã được điều phối; proxy chọn backend.
- **Client-side balancing:** resolver trả danh sách địa chỉ instance và gRPC client áp dụng policy tương ứng, ví dụ round-robin nếu được hỗ trợ và cấu hình.
- **Kubernetes Service:** cung cấp tên DNS ổn định và tầng định tuyến; hành vi phân phối kết nối/HTTP2 phải được hiểu rõ, nhất là khi connection dài hạn được duy trì.

**Lưu ý về kết nối dài hạn:** một kết nối HTTP/2 từ client đến một virtual IP/proxy có thể được ghim đến một backend tùy hạ tầng. Điều này có thể gây phân phối request không đều giữa nhiều pod nếu không có gRPC-aware proxy hoặc client-side load balancing thích hợp. Không giả định tăng số replica luôn chia đều lưu lượng ngay.

### Health và readiness

Một instance có process chạy không đồng nghĩa đã sẵn sàng nhận RPC. Cần readiness/health policy; gRPC Health Checking Protocol là một lựa chọn để báo trạng thái phục vụ của dịch vụ trong server. Kubernetes cũng hỗ trợ các cách probe phù hợp. Liveness và readiness có ý nghĩa khác nhau; không để một downstream lỗi tạm thời gây restart hàng loạt mọi instance upstream.

### Kết nối và channel

- Tái sử dụng channel được quản lý thay vì tạo một channel mới cho mỗi request.
- Đặt giới hạn kết nối, concurrent streams, max message size theo nhu cầu.
- Hiểu idle timeout, keepalive, proxy/nginx/mesh và load balancer đang dùng.
- Không gửi ping keepalive quá dày đến server/proxy không chấp nhận; có thể bị đóng kết nối.
- Đóng channel có kiểm soát khi ứng dụng shutdown.

## 16. Metadata, interceptors và context truyền qua các dịch vụ

Ngoài payload Protobuf, gRPC hỗ trợ metadata trong request/response. Metadata thường dùng để gửi:

- Authorization credential hoặc service identity.
- Trace context, correlation ID/request ID.
- Locale hoặc yêu cầu vùng dữ liệu nếu có hợp đồng rõ.
- Idempotency key theo policy của ứng dụng.
- Thông tin routing hoặc feature/capability version khi cần.

### Ví dụ ý tưởng

~~~text
RPC: InventoryService/ReserveStock
Metadata:
  authorization: Bearer <short-lived-service-token>
  x-correlation-id: checkout-1001
  x-request-id: reserve-ORD-1001-v1
Payload:
  order_id: ORD-1001
  request_id: reserve-ORD-1001-v1
  lines: ...
~~~

Trong hệ thống thật, không ghi giá trị token thô vào log. Credential trong ví dụ chỉ là placeholder; mọi kết nối truyền credential phải dùng transport bảo mật.

**Interceptor** có thể tập trung các việc như authentication, tracing, metrics, logging có lọc dữ liệu và áp policy chung. Nhưng các **quy tắc nghiệp vụ** như “được phép hủy đơn ở trạng thái nào” vẫn cần được thực thi trong domain/application boundary. Một interceptor biết userId không tự quyết định user đó được xem mọi orderId.

### Correlation và trace

- **traceId/spanId:** nhận diện lời gọi trong distributed tracing.
- **correlationId:** liên kết các hoạt động cùng một tiến trình nghiệp vụ, có thể kéo dài hơn một trace.
- **requestId/idempotencyKey:** nhận diện thao tác để chống xử lý trùng.

Các mã này có vai trò khác nhau. Không coi trace ID là idempotency key nếu tracing có thể tạo ID mới cho mỗi lần retry.

## 17. Bảo mật gRPC giữa các dịch vụ

gRPC thường chạy trong mạng nội bộ, nhưng “nội bộ” không tự đồng nghĩa với tin cậy. Các lựa chọn cần đánh giá:

### 17.1. TLS và mTLS

- **TLS** bảo vệ kết nối và cho phép client xác minh danh tính server qua chứng chỉ.
- **Mutual TLS (mTLS)** cho phép cả hai phía chứng thực lẫn nhau ở tầng transport.
- **Plaintext** chỉ nên dùng cho môi trường test/local có phạm vi kiểm soát phù hợp; không gửi token bí mật qua kết nối không bảo vệ.

Có thể dùng service mesh để quản lý mTLS, rotation và policy giữa workloads, nhưng vẫn phải hiểu boundary và không đưa toàn bộ authorization nghiệp vụ xuống tầng mạng.

### 17.2. Authentication

Một server có thể xác thực client qua identity gắn với mTLS, bearer token, workload identity hoặc cơ chế đã được thống nhất. Các trường như orderId/customerId trong payload **không tự là bằng chứng quyền**.

### 17.3. Authorization

Inventory có thể cho Ordering gọi ReserveStock nhưng không cho mọi service tự do điều chỉnh tồn kho. Payment Service có thể cho một số caller tạo payment attempt nhưng không cho tất cả gọi refund. Ghi rõ quyền theo service identity, tenant và operation.

### 17.4. Bảo vệ message và log

- Giới hạn kích thước message để tránh lạm dụng bộ nhớ.
- Validate string, số lượng, enum và giá trị nghiệp vụ trước khi sử dụng.
- Không ghi payment token, thông tin người dùng nhạy cảm hoặc authorization header vào log.
- Theo dõi lỗi auth, TLS handshake, permission denied và hành vi bất thường.
- Duy trì rotation cho khóa/chứng chỉ và khả năng cập nhật trust khi nhiều phiên bản chạy đồng thời.

## 18. gRPC và HTTP/JSON: chọn công cụ theo bài toán

| Tiêu chí | gRPC chuẩn | HTTP API + JSON |
| --- | --- | --- |
| Hợp đồng | .proto, schema và stubs sinh mã | OpenAPI/JSON Schema hoặc tài liệu/API contract khác |
| Kiểu payload phổ biến | Protobuf nhị phân | JSON văn bản |
| Transport thông dụng | HTTP/2 | HTTP/1.1 hoặc HTTP/2 tùy triển khai |
| Streaming | Hỗ trợ bốn kiểu RPC ở mức framework | Có thể dùng streaming/SSE/WebSocket/HTTP riêng |
| Client nhiều ngôn ngữ | Sinh stub/kiểu dữ liệu từ .proto | Có nhiều SDK/generator; thường dễ gọi thủ công |
| Browser trực tiếp | gRPC chuẩn không phù hợp trực tiếp với browser API phổ biến; thường cần gRPC-Web/gateway | Rất phổ biến qua fetch và công cụ web |
| Quan sát thủ công | Cần công cụ hiểu gRPC và Protobuf | Dễ xem/curl/debug với JSON |
| Hiệu năng payload | Có thể hiệu quả cho message nhỏ, tần suất cao | Dễ dùng, chi phí encode có thể cao hơn tùy trường hợp |
| Thay đổi hợp đồng | Quản lý field number, schema và version | Quản lý field, media type, version, compatibility |
| Rủi ro lỗi mạng | Có | Có |

**Không khẳng định gRPC luôn nhanh hơn REST.** Cần benchmark đúng workload, serialization, message size, số kết nối, cấu hình HTTP/2, network RTT, TLS, proxy và resource constraints. Với request thưa, dữ liệu nhỏ và nhu cầu tích hợp web rộng, lợi ích gRPC có thể không bù chi phí vận hành.

### Khi gRPC thường phù hợp

- Giao tiếp nội bộ giữa các dịch vụ có hợp đồng rõ, nhiều ngôn ngữ.
- Yêu cầu typed stub và giới hạn API chính xác.
- Lưu lượng request tương đối lớn hoặc payload nhị phân, cần benchmark tối ưu.
- Các luồng streaming thời gian thực được yêu cầu nghiệp vụ.
- Có năng lực quản lý Protobuf schema, code generation, service discovery, observability và security.

### Khi HTTP/JSON có thể tốt hơn

- API công khai cho đối tác/browser.
- Đội ngũ hoặc công cụ vận hành cần đọc, thử nhanh bằng curl.
- Tích hợp đơn giản, tần suất thấp, không cần streaming hoặc typed client riêng.
- Hạ tầng proxy/cổng API chưa hỗ trợ gRPC đầy đủ.
- Muốn tận dụng khả năng caching, semantics và hệ sinh thái HTTP của API theo resource.

Một kiến trúc có thể kết hợp: **Public HTTP/JSON ở Gateway**, sau đó **gRPC nội bộ** đến các service, và **message broker** cho tác vụ bất đồng bộ. Việc dùng nhiều giao thức cần có lý do rõ, tránh ép mọi vấn đề vào một transport.

## 19. Browser, gRPC-Web và API Gateway

Trình duyệt không thường cung cấp toàn quyền truy cập các tính năng HTTP/2 mà gRPC chuẩn cần (đặc biệt kiểm soát trailers/stream theo cách runtime gRPC chuẩn sử dụng). Vì vậy ứng dụng web thường:

1. Gọi HTTP/JSON tới Backend for Frontend (BFF) hoặc API Gateway, Gateway gọi gRPC nội bộ; hoặc
2. Dùng **gRPC-Web** ở browser và một proxy/adapter hỗ trợ chuyển đổi giữa gRPC-Web và gRPC chuẩn.

~~~mermaid
flowchart LR
    W[Browser] --> H[HTTP JSON / gRPC-Web]
    H --> G[Gateway / BFF / Proxy]
    G -->|gRPC| O[Order Service]
    G -->|gRPC| I[Inventory Service]
~~~

gRPC-Web có giới hạn khác gRPC chuẩn tùy phiên bản và transport, nhất là về kiểu streaming có thể dùng từ browser. Đừng mặc định một client trình duyệt có thể sử dụng nguyên các method bidirectional streaming giống ứng dụng backend; hãy kiểm tra hỗ trợ của client/proxy thực tế.

Gateway có thể dịch response gRPC sang HTTP status/JSON cho external API. Cần thống nhất mapping, cấu trúc lỗi, authorization, deadline và truyền trace context qua ranh giới đó.

## 20. Tương thích phiên bản, schema registry và triển khai độc lập

Một Microservice có thể nâng cấp trước consumer của nó. Ví dụ Inventory v2 được triển khai trong khi Ordering v1 còn chạy. Điều này đòi hỏi hợp đồng giữa hai phiên bản tương thích đủ lâu.

### 20.1. Thay đổi mở rộng trước

Cách an toàn thường là **expand–migrate–contract**:

1. Producer hỗ trợ field/method mới mà không phá field/method cũ.
2. Consumer mới bắt đầu sử dụng khả năng mới với feature/version strategy phù hợp.
3. Theo dõi phiên bản consumer thực tế và kết quả contract tests.
4. Chỉ xóa hợp đồng cũ khi đã xác nhận không còn consumer phụ thuộc và có lịch deprecation rõ.

### 20.2. Không thay field number khi đổi tên đơn thuần

Protobuf trên wire dựa vào field number/type. Việc đổi tên field mà giữ số có thể không phá binary decoding trong các điều kiện nhất định, nhưng vẫn ảnh hưởng generated code, JSON mapping, tài liệu, reflection và người phát triển. Do đó **khả năng tương thích wire không đồng nghĩa mọi client đều tương thích ở mức source/API**.

### 20.3. Khi nào dùng package version mới?

Nếu buộc phải thay semantic lớn hoặc shape không thể tương thích, có thể công bố một package mới như shop.inventory.v2 và chạy song song với v1 trong giai đoạn chuyển đổi. Đừng tăng version cho mọi thay đổi nhỏ; nhưng cũng đừng ngụy trang breaking change bằng cách giữ tag cũ.

### 20.4. Contract tests và các phiên bản chạy song song

Kiểm tra tối thiểu:

- Ordering v1 gọi được Inventory v2 trong giai đoạn rolling deployment?
- Inventory v1 còn hiểu request từ Ordering v2?
- Giá trị enum mới có bị consumer cũ xử lý sai?
- Field cũ bị thiếu/optional có làm thay đổi quyết định nghiệp vụ?
- Authorization/metadata mới có làm client cũ bị từ chối ngoài dự kiến?
- Proxy/gateway có định tuyến đúng method path và package?
- Nếu có stream, client cũ có xử lý kết thúc, lỗi và reconnect phù hợp?

Một file .proto compile thành công không chứng minh cách dùng nghiệp vụ đã tương thích.

## 21. Quan sát và vận hành gRPC

Muốn hiểu vì sao checkout chậm, cần biết request đi qua những service nào và mỗi RPC mất bao lâu. Instrumentation có thể triển khai bằng OpenTelemetry, interceptor/middleware và khả năng của proxy/service mesh.

| Nhóm tín hiệu | Ví dụ | Ý nghĩa |
| --- | --- | --- |
| Latency | p50/p95/p99 cho InventoryService/ReserveStock | Phát hiện downstream chậm |
| Error rate | Tỷ lệ DEADLINE_EXCEEDED, UNAVAILABLE, INTERNAL | Phân biệt network/dependency/logic |
| Throughput | RPC/s theo method và service | Quan sát tải |
| Saturation | Active streams, CPU, thread pool, connection pool | Nút nghẽn tài nguyên |
| Retry | Số lần retry, backoff, retry budget tiêu thụ | Tránh bão retry |
| Security | Auth failures, permission denied, TLS errors | Kiểm tra truy cập |
| Streaming | Stream duration, messages per stream, cancellation | Phát hiện stream kẹt hoặc bị hủy |
| Backend | DB latency, transaction conflicts, queue lag | Lỗi nằm phía sau handler |
| Tracing | traceId, span, peer service, method | Ghép hành trình request |

Ví dụ log có cấu trúc:

~~~text
service=ordering operation=checkout orderId=ORD-1001
rpc.service=shop.inventory.v1.InventoryService
rpc.method=ReserveStock
rpc.status=OK duration_ms=42
correlationId=checkout-1001
~~~

Nếu dùng status OK nhưng business result là REJECTED do hết hàng, metrics nghiệp vụ phải tách khỏi metrics status kỹ thuật. Không thể kết luận “100% success checkout” chỉ bằng 100% RPC OK.

### Tránh cardinality không kiểm soát

Không đưa orderId, userId, requestId hoặc token làm **label trực tiếp** trên metric tổng quát có số lượng chuỗi thời gian rất lớn. Các ID này phù hợp hơn trong log/trace có chính sách bảo vệ dữ liệu. Metric label thường ưu tiên service, method, status, môi trường và phiên bản được kiểm soát.

### Tracing xuyên RPC

Caller nên truyền trace context qua propagation mechanism được framework/instrumentation hỗ trợ. Khi một request từ Gateway qua Ordering đến Inventory, trace giúp nhìn thời gian chờ ở từng hop. Với Saga kéo dài nhiều phút, có thể dùng correlationId để liên kết nhiều trace, không bắt buộc gộp toàn bộ vòng đời vào một trace khổng lồ.

## 22. Những lỗi triển khai thường gặp

### Lỗi 1 — Không đặt deadline

**Biểu hiện:** Khi Inventory chậm, thread của Ordering bị giữ lâu, số request chờ tăng và gateway timeout hàng loạt.

**Cách xử lý:** Đặt deadline theo use case, giới hạn concurrency, bổ sung metrics và fallback phù hợp.

### Lỗi 2 — Tự retry mọi lỗi

**Biểu hiện:** Command ReserveStock hoặc ChargePayment tạo nhiều tác động phụ khi timeout.

**Cách xử lý:** Phân biệt lỗi tạm, business rejection và trạng thái không rõ; có idempotency key và quy tắc đối soát trước khi retry.

### Lỗi 3 — Tạo channel cho mỗi request

**Biểu hiện:** Nhiều TLS handshake, socket, CPU và tài nguyên connection bị lãng phí.

**Cách xử lý:** Tái sử dụng ManagedChannel theo lifecycle ứng dụng, quản lý shutdown và giới hạn tài nguyên.

### Lỗi 4 — RPC quá nhỏ và chatty

**Biểu hiện:** Dịch vụ A gọi 100 RPC để lấy 100 item nhỏ thay vì một query phù hợp, làm latency tăng mạnh.

**Cách xử lý:** Thiết kế operation theo ranh giới nghiệp vụ, cân nhắc batch API hoặc read model; không tạo một method RPC cho từng getter Java.

### Lỗi 5 — Dùng gRPC stream làm event store

**Biểu hiện:** Khi client rời mạng, lịch sử event biến mất và không thể replay.

**Cách xử lý:** Dùng broker/log/storage bền vững khi cần persistence, replay và consumer offline; gRPC stream chỉ là kênh giao tiếp đang hoạt động.

### Lỗi 6 — Không kiểm tra schema compatibility

**Biểu hiện:** Producer đổi field number hoặc semantics, consumer giải mã sai hoặc triển khai mới bị crash.

**Cách xử lý:** Quản lý .proto như hợp đồng chính thức, contract tests, versioning và quy trình deprecation.

### Lỗi 7 — Xem gRPC status là nghiệp vụ cuối cùng

**Biểu hiện:** RPC ReserveStock trả OK nhưng response REJECTED; Ordering vẫn đánh dấu hàng đã được giữ.

**Cách xử lý:** Kiểm tra cả gRPC status và domain result. Định nghĩa rõ kết quả nào là expected business outcome.

### Lỗi 8 — Quên auth giữa các service

**Biểu hiện:** Bất kỳ workload nào trong cluster cũng có thể gọi method hoàn tiền hoặc đọc đơn của tenant khác.

**Cách xử lý:** TLS/mTLS/service identity, authorization theo method và phạm vi dữ liệu; không tin đơn thuần vào IP nội bộ.

### Lỗi 9 — Tưởng tăng replica luôn chia đều traffic

**Biểu hiện:** Một pod quá tải trong khi nhiều pod khác rảnh vì kết nối HTTP/2 lâu dài hoặc policy LB chưa phù hợp.

**Cách xử lý:** Kiểm tra resolver, proxy, balancing policy, connection reuse, endpoint health và số lượng stream thực tế.

### Lỗi 10 — Coi deadline cancellation như rollback

**Biểu hiện:** Caller hủy request thanh toán nhưng server đã commit trước khi nhận cancellation, khiến luồng nghiệp vụ bị hiểu sai.

**Cách xử lý:** Lưu trạng thái operation bền vững, có identity của thao tác, đối soát và compensation theo domain.

## 23. Một bài thực hành Java và Microservices theo từng bước

Bài tập: tạo hai ứng dụng tối giản **Ordering Client** và **Inventory Server**. Tập trung vào interface, transport và cách xử lý lỗi; có thể dùng một repository với hai module độc lập.

### Bước 1 — Viết contract

Tạo file inventory.proto với ReserveStock và GetReservation như ví dụ. Quy định rõ:

~~~text
ReserveStock
  order_id: không được trống
  request_id: idempotency key ổn định
  lines: phải có ít nhất một dòng, mỗi quantity > 0

Response
  RESERVED: có reservation_id
  REJECTED: có reason_code nghiệp vụ
~~~

Chọn package Java và phương án quản lý schema sao cho hai ứng dụng có thể sinh stub tương thích từ cùng một contract version. Không copy paste thông điệp thủ công rồi để lệch field number.

### Bước 2 — Sinh mã

Dùng protoc và grpc-java codegen để tạo các message class và InventoryServiceGrpc. Nếu dùng Gradle, có thể dùng Protobuf Gradle plugin phù hợp với project hiện có; dependency cần gồm Protobuf runtime và gRPC runtime/stubs theo lựa chọn build.

Không chốt tùy tiện phiên bản thư viện trong bài học này vì dự án cụ thể cần sử dụng dải version được kiểm thử cùng nhau. Điều cần quan sát là **mã client và server được tạo từ cùng hợp đồng**.

### Bước 3 — Viết handler ở Inventory

Handler:

1. Nhận request Protobuf và kiểm tra tham số.
2. Chuyển request thành ReserveStockCommand nội bộ.
3. Gọi InventoryApplicationService.
4. Sử dụng transaction cục bộ để kiểm tra số lượng và giữ hàng.
5. Trả RESERVED hoặc REJECTED theo hợp đồng.
6. Mapping lỗi kỹ thuật ra gRPC status đúng loại.

Đừng ghi inventory thay đổi trong callback mà thiếu transaction hoặc chỉ dùng synchronized để bảo vệ nhiều instance.

### Bước 4 — Viết Ordering client

Ordering tạo channel/stub một lần cho lifecycle ứng dụng, đặt deadline phù hợp, gửi ReserveStock với cùng request_id khi retry. Sau khi nhận kết quả:

- RESERVED: lưu reservationId và tiếp tục quy trình.
- REJECTED: thông báo hết hàng, không thu tiền.
- UNAVAILABLE: áp retry bounded nếu hợp đồng và deadline cho phép.
- DEADLINE_EXCEEDED: tra cứu kết quả của request_id trước khi quyết định gửi lại hoặc hủy.
- INVALID_ARGUMENT: xử lý lỗi dữ liệu, không retry nguyên trạng.

### Bước 5 — Quan sát qua log và tracing

Thêm correlationId, service/method, status và latency. Mọi log phải loại bỏ credential. Thử tạo vài request rồi xác nhận được chuỗi:

~~~text
Ordering: order=ORD-1001 requestId=resv-1 calling ReserveStock
Inventory: requestId=resv-1 valid qty=2
Inventory: reservation RES-1 committed
Ordering: requestId=resv-1 status=RESERVED reservation=RES-1
~~~

### Bước 6 — Tạo lỗi có kiểm soát

Trong môi trường thử nghiệm:

1. Cho Inventory trả UNAVAILABLE tạm thời trước khi xử lý.
2. Cho Inventory xử lý chậm hơn deadline.
3. Cho Inventory commit reservation rồi chặn phản hồi.
4. Gửi lại cùng request_id hai lần.
5. Thử hai client cùng giữ chiếc hàng cuối cùng.
6. Dừng một replica Inventory khi có request đang chạy.

Kết quả mong đợi là **không giữ hàng trùng**, không bán quá lượng tồn, không coi timeout là bằng chứng thất bại và có log/metrics đủ để xác định trạng thái.

### Bước 7 — Đổi contract có kiểm soát

Bổ sung field tùy chọn như warehouse_id với field number mới. Kiểm tra các cặp client cũ/server mới và client mới/server cũ theo chính sách. Sau đó thử đổi nghĩa field cũ và giải thích vì sao đó là breaking change ngay cả khi .proto vẫn biên dịch.

### Bước 8 — Đánh giá kiến trúc

Tự hỏi ReserveStock có cần trả kết quả ngay trong request không. Nếu việc đặt giữ hàng yêu cầu chờ lâu, hãy mô tả phương án command/event bất đồng bộ và cách UI tra cứu trạng thái cuối. Bài tập giúp nhận ra **chọn RPC hay messaging là quyết định về luồng nghiệp vụ**, không chỉ là thay thư viện.

## 24. Bài tập tình huống và câu hỏi kiểm tra

### Tình huống A: đặt hàng qua ba dịch vụ

Ordering gọi Pricing, Inventory, Payments theo thứ tự. Pricing mất 250 ms, Inventory mất 700 ms, Payments mất 900 ms; bỏ qua overhead khác. Gateway chỉ cho toàn request 1.200 ms. Hãy giải thích vì sao “mỗi RPC có deadline 1.200 ms” là thiết kế chưa hợp lý và mô tả một cách tổ chức workflow khác.

**Gợi ý:** latency cộng dồn có thể vượt ngân sách, dù từng call đơn lẻ vẫn dưới 1.200 ms. Có thể tách các bước dài sang Saga và trả trạng thái đang xử lý; deadline phải xét ngân sách còn lại.

### Tình huống B: retry bị mất phản hồi

Inventory nhận ReserveStock, ghi reservation rồi kết nối đứt trước khi gửi response. Client nhận DEADLINE_EXCEEDED. Hãy thiết kế request_id, GetReservationByRequestId hoặc reconciliation để tránh giữ hàng lần thứ hai.

**Gợi ý:** cùng identity của operation phải cho ra một kết quả nghiệp vụ, được bảo vệ bằng transaction/unique constraint.

### Tình huống C: thay đổi field number

Bản v1 có quantity = 2 trong StockLine. Nhóm Inventory muốn đổi quantity thành field số 4 mà vẫn gọi là v1. Điều gì xảy ra với consumer cũ? Cách thay đổi nào an toàn hơn?

**Gợi ý:** field number tham gia wire format; đổi số làm consumer cũ có thể không nhận giá trị và sử dụng mặc định. Phải giữ field cũ hoặc có lộ trình schema/version chính thức.

### Tình huống D: chỉ một instance nhận traffic

Inventory tăng từ 1 lên 5 pod nhưng gRPC client vẫn dồn nhiều request vào một pod. Giải thích vai trò connection HTTP/2 lâu dài, Kubernetes Service, client-side LB và gRPC-aware proxy.

**Gợi ý:** tăng replica mới tăng năng lực tiềm năng; cơ chế chọn backend/connection mới quyết định lưu lượng có được phân phối phù hợp hay không.

### Tình huống E: lỗi xác thực

Ordering không có quyền gọi RefundPayment nhưng mạng cho phép kết nối đến Payments. Server nên xử lý thế nào?

**Gợi ý:** xác thực service identity rồi thực thi authorization theo operation; trả PERMISSION_DENIED khi đã xác thực nhưng không được phép. Không dựa vào mạng “nội bộ” như cơ chế ủy quyền.

### Tình huống F: stream bị ngắt

Client theo dõi WatchReservation qua server streaming và mất mạng sau 20 cập nhật. Khi kết nối lại, client cần làm gì để có trạng thái đúng?

**Gợi ý:** stream không tự bảo đảm replay; cần API snapshot, sequence/checkpoint và chính sách bỏ qua duplicate/out-of-order; nếu yêu cầu lịch sử bền vững cần lưu ngoài stream.

### Tình huống G: status OK nhưng nghiệp vụ từ chối

ReserveStock trả RPC OK và response status=REJECTED. Ordering lại chuyển Order sang STOCK_RESERVED. Đây là lỗi gì?

**Gợi ý:** caller kiểm tra transport nhưng không xử lý domain result; contract phải định nghĩa rõ kết quả từ chối hợp lệ.

### Câu hỏi tự kiểm tra

1. Điểm khác biệt chính giữa gọi hàm nội bộ và RPC là gì?
2. RPC là một khái niệm hay một sản phẩm? gRPC thuộc nhóm nào?
3. File .proto và generated stub giúp ích gì cho team đa ngôn ngữ?
4. Vì sao field number trong Protobuf phải được bảo vệ khi thay schema?
5. Streaming trong gRPC khác với event log/broker bền vững thế nào?
6. DEADLINE_EXCEEDED có chứng minh server chưa commit không?
7. Vì sao mỗi command có side effect cần identity/idempotency ổn định?
8. UNAUTHENTICATED khác PERMISSION_DENIED ở điểm nào?
9. Có thể gọi gRPC chuẩn từ browser mà không có điều kiện bổ sung không?
10. Khi nào nên dùng gRPC unary, khi nào nên đổi sang workflow bất đồng bộ?
11. Một channel đến service name có bảo đảm traffic chia đều giữa mọi instance không?
12. Vì sao metric RPC status OK không đủ để kết luận nghiệp vụ thành công?
13. Vì sao client/server cùng biên dịch được .proto mới chưa chứng minh semantic compatibility?
14. Cần truyền context nào qua các hop mà không làm lộ credential vào log?
15. gRPC có giải quyết tự động transaction nhiều database, Saga hoặc consistency không?

## 25. Checklist thiết kế một RPC cho Microservices

Khi chuẩn bị thêm một method mới, hãy ghi lại các mục sau trong tài liệu API:

| Hạng mục | Cần quyết định |
| --- | --- |
| Ranh giới nghiệp vụ | Service nào sở hữu operation, dữ liệu và invariant? |
| Hợp đồng .proto | Package, service, method, request/response, enum, field numbers |
| Semantics | Operation là query, command có side effect hay luồng streaming? |
| Input validation | Required/optional, giới hạn dữ liệu, payload size |
| Business result | Kết quả hợp lệ, rejection và reason codes |
| Error mapping | Status code gRPC và richer error details nếu dùng |
| Deadline | Thời gian cho phép và cách truyền budget |
| Retry | Lỗi nào retry, ở lớp nào, số lần, backoff và jitter |
| Idempotency | Key, scope, thời gian lưu, conflict handling |
| Concurrency | Transaction, unique constraint, version/invariant |
| Auth | Service identity, TLS/mTLS, quyền theo method/tenant |
| Routing | Resolver, service discovery, LB, health checks |
| Lifecycle | Channel reuse, shutdown, cancellation, resource limit |
| Compatibility | Schema version, consumer tests, rollout/deprecation |
| Observability | RPC latency/status, tracing, domain metrics |
| Recovery | Đối soát khi timeout, xử lý sự kiện trùng, manual handling |
| Fallback | Khi dependency unavailable, client trả gì? |
| Asynchronous alternative | Có phù hợp dùng event/queue thay vì chờ RPC? |

Đây là checklist thiết kế; mỗi dự án có thể chi tiết hóa thêm theo độ quan trọng nghiệp vụ.

## 26. Ghi nhớ

**RPC** mô tả một cách gọi thao tác từ xa; **gRPC** cung cấp framework, hợp đồng Protobuf, stub đa ngôn ngữ và transport HTTP/2 cho unary/streaming. Lợi ích lớn là **giao tiếp service-to-service có kiểu và hợp đồng rõ**, nhưng tính đúng đắn của hệ thống vẫn phụ thuộc vào thiết kế nghiệp vụ và khả năng chịu lỗi.

Khi xây Microservices, đừng chỉ hỏi “dùng gRPC có nhanh hơn REST không?”. Hãy hỏi: operation thuộc context nào, dữ liệu nào cần có ngay, điều gì xảy ra nếu mạng timeout, retry có tạo tác động trùng không, phiên bản cũ/mới có tương thích không, và liệu một lời gọi đồng bộ có đang làm chuỗi phụ thuộc quá dài. Tạo contract rõ ràng, chọn deadline hợp lý, bảo vệ idempotency, xác thực/ủy quyền, quan sát latency và có phương án phục hồi khi kết quả không rõ. Đó mới là nền tảng sử dụng gRPC hiệu quả trong hệ thống phân tán.
