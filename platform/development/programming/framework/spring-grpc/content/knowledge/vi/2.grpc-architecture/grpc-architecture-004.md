# RPC method và request, response message

## Mục tiêu học tập

Sau bài này, bạn có thể:

- Phân biệt **RPC method** với phương thức Java thông thường, và giải thích vì sao request/response message là một phần của hợp đồng gRPC.
- Đọc và khai báo phương thức **rpc** trong Protocol Buffers (**.proto**), bao gồm bốn kiểu unary và streaming.
- Hiểu cách một method được định danh, định tuyến qua HTTP/2, gắn với **method descriptor**, client stub và server implementation.
- Thiết kế request/response message bằng field number, kiểu dữ liệu, **optional**, **repeated**, **oneof** và enum; phân biệt dữ liệu nghiệp vụ với metadata và gRPC status.
- Triển khai một unary RPC với **grpc-java** trong Spring, đặt deadline, trả lỗi hợp lệ và kiểm thử contract.
- Nhận diện các thay đổi schema có thể làm hỏng client cũ, cũng như các giới hạn hiệu năng và độ tin cậy của phương thức streaming.

## 1. RPC method là gì và khác gì một phương thức Java?

Trong hệ sinh thái **SPRING_GRPC**, client gọi một dịch vụ từ xa bằng API Java được sinh từ hợp đồng **Protocol Buffers**. Phía client, câu lệnh trông gần giống một lời gọi phương thức tại chỗ:

~~~java
GetOrderResponse response = orderStub.getOrder(
        GetOrderRequest.newBuilder()
                .setOrderId("order-42")
                .build());
~~~

Nhưng **getOrder()** ở đây là **RPC method**: lời gọi phải đi qua stub, Channel, transport, server runtime rồi mới đến logic nghiệp vụ. Nó có thể phát sinh độ trễ mạng, deadline, lỗi xác thực, mất kết nối hoặc lỗi từ server. Lời gọi Java bình thường bên trong cùng một tiến trình không có các ranh giới mạng đó.

Mỗi RPC method gắn với ba điều được công bố trong hợp đồng:

1. **Tên định danh**: service nào cung cấp method, method tên gì.
2. **Kiểu request**: message protobuf nào caller phải gửi.
3. **Kiểu response**: message protobuf nào caller sẽ nhận, cùng việc một phía gửi một hay nhiều message.

Giao tiếp thực tế còn chịu cấu hình **metadata, deadline, credentials, TLS, interceptor, retry và observability**. Các yếu tố này thuộc runtime/chính sách sử dụng method; cú pháp method trong .proto không tự cấu hình chúng.

~~~mermaid
sequenceDiagram
    participant C as Spring client service
    participant S as Generated client stub
    participant H as ManagedChannel/HTTP2
    participant R as gRPC server runtime
    participant I as Spring server implementation
    C->>S: getOrder(GetOrderRequest)
    S->>H: MethodDescriptor + serialized request
    H->>R: POST /shop.orders.v1.OrderQueryService/GetOrder
    R->>I: getOrder(request, responseObserver)
    I-->>R: onNext(GetOrderResponse)
    I-->>R: onCompleted()
    R-->>H: response message + grpc-status
    H-->>S: deserialize + status
    S-->>C: GetOrderResponse
~~~

**Một RPC method không nhất thiết là một HTTP request-response theo nghĩa REST.** Với server/client/bidirectional streaming, cùng một RPC có thể truyền nhiều protobuf message qua **một HTTP/2 stream**.

### 1.1. So sánh các đối tượng liên quan

| Thành phần | Vai trò | Ví dụ |
| --- | --- | --- |
| **Service** | Nhóm các RPC có chung mục đích | **OrderQueryService** |
| **RPC method** | Một thao tác từ xa và kiểu dữ liệu hai chiều | **GetOrder(GetOrderRequest) returns (GetOrderResponse)** |
| **Request message** | Payload đầu vào, có schema và dữ liệu được mã hóa | **order_id = "order-42"** |
| **Response message** | Payload kết quả thành công, có schema | **order.id, order.status** |
| **RPC metadata** | Thông tin header/trailer ở tầng lời gọi | Authorization, trace ID, request ID |
| **gRPC status** | Kết quả thành công/thất bại của lời gọi | **OK**, **INVALID_ARGUMENT**, **NOT_FOUND** |
| **ManagedChannel** | Cung cấp đường đi từ client tới server và quản lý kết nối | Channel trỏ tới backend |
| **Implementation** | Logic xử lý method đã đăng ký trên server | Java override **getOrder(...)** |

Dễ nhầm nhất là **response message** và **gRPC status**. Response mô tả dữ liệu khi xử lý thành công; gRPC status cho biết lời gọi có thành công hay không. Khi có lỗi, server có thể chỉ gửi status và trailers, không có response message thành công.

## 2. Định nghĩa service, method, request và response trong .proto

Một file **.proto** là nguồn hợp đồng chung giữa client và server. Ví dụ dưới đây định nghĩa service truy vấn đơn hàng cùng bốn loại RPC để thấy rõ quan hệ giữa method và message.

~~~proto
syntax = "proto3";

package shop.orders.v1;

option java_package = "com.example.shop.orders.v1";
option java_multiple_files = true;
option java_outer_classname = "OrdersProto";

service OrderQueryService {
  rpc GetOrder(GetOrderRequest) returns (GetOrderResponse);
  rpc WatchOrders(WatchOrdersRequest) returns (stream OrderEvent);
  rpc ImportOrderEvents(stream OrderEvent) returns (ImportOrderEventsResponse);
  rpc SyncOrders(stream SyncOrdersRequest) returns (stream SyncOrdersResponse);
}

message GetOrderRequest {
  string order_id = 1;
  optional string locale = 2;
}

message GetOrderResponse {
  Order order = 1;
  string etag = 2;
}

message Order {
  string id = 1;
  string customer_id = 2;
  OrderStatus status = 3;
  int64 created_at_epoch_ms = 4;
  repeated OrderLine lines = 5;
}

message OrderLine {
  string sku = 1;
  int32 quantity = 2;
}

enum OrderStatus {
  ORDER_STATUS_UNSPECIFIED = 0;
  ORDER_STATUS_PENDING = 1;
  ORDER_STATUS_COMPLETED = 2;
  ORDER_STATUS_CANCELLED = 3;
}

message WatchOrdersRequest {
  string customer_id = 1;
}

message OrderEvent {
  string order_id = 1;
  OrderStatus new_status = 2;
  int64 changed_at_epoch_ms = 3;
}

message ImportOrderEventsResponse {
  int32 accepted_count = 1;
}

message SyncOrdersRequest {
  string cursor = 1;
}

message SyncOrdersResponse {
  string next_cursor = 1;
  Order order = 2;
}
~~~

Từ service definition này, **protoc** và **protoc-gen-grpc-java** thường sinh:

- Các message Java như **GetOrderRequest**, **GetOrderResponse**, **Order**, **OrderEvent**, kèm **Builder** và API parse/serialize.
- Lớp **OrderQueryServiceGrpc** chứa descriptor phương thức, factory tạo các kiểu client stub và lớp cơ sở server **OrderQueryServiceImplBase**.
- Các stub **OrderQueryServiceBlockingStub**, **OrderQueryServiceStub** (async) và **OrderQueryServiceFutureStub**.

**Không sửa trực tiếp mã Java sinh tự động.** Hãy thay đổi .proto, chạy lại generator và cập nhật những caller/implementation liên quan.

### 2.1. Ý nghĩa của tên method trong giao thức

Method **GetOrder** thuộc service **OrderQueryService** trong protobuf package **shop.orders.v1** có:

~~~text
Full service name: shop.orders.v1.OrderQueryService
Full method name:  shop.orders.v1.OrderQueryService/GetOrder
HTTP/2 :path:     /shop.orders.v1.OrderQueryService/GetOrder
~~~

**java_package** chỉ định package Java của lớp được sinh (**com.example.shop.orders.v1**), không thay đổi full method name trên mạng. Tên file .proto cũng không nằm trong đường dẫn RPC. Nếu đổi protobuf package, tên service hay method đang được client sử dụng, đường dẫn RPC sẽ thay đổi và có thể dẫn tới **UNIMPLEMENTED** với client cũ.

### 2.2. Chữ ký method quy định những gì?

Về cú pháp:

~~~proto
rpc MethodName(RequestType) returns (ResponseType);
~~~

Đối với RPC method chuẩn:

- **RequestType** và **ResponseType** là các **message type** protobuf. Không khai báo **rpc GetOrder(string) returns (int32)** trực tiếp; hãy dùng các message có field tương ứng.
- Từ khóa **stream** phía trước một kiểu có nghĩa phía đó gửi **một chuỗi message**.
- Mọi method đều có tên, kiểu request, kiểu response; không có overload theo tham số giống phương thức Java.
- Nếu không cần nội dung request/response, có thể dùng **google.protobuf.Empty**; vẫn có kiểu message, dù không có field.

Ví dụ:

~~~proto
import "google/protobuf/empty.proto";

service DiagnosticService {
  rpc Ping(google.protobuf.Empty) returns (google.protobuf.Empty);
}
~~~

**Lưu ý:** việc method có tên **Ping** không tự có nghĩa runtime bật HTTP/2 PING hay cơ chế keepalive. Đây vẫn là RPC ở tầng ứng dụng.

## 3. Bốn kiểu RPC được quyết định bởi chữ ký

Cùng một nguyên tắc định nghĩa method, từ khóa **stream** mở rộng số lượng message được gửi.

| Loại | Chữ ký trong .proto | Giao tiếp logic | Hướng sử dụng |
| --- | --- | --- | --- |
| **Unary** | **rpc GetOrder(GetOrderRequest) returns (GetOrderResponse);** | Một request, một response thành công | Đọc/ghi một đối tượng, thao tác ngắn |
| **Server streaming** | **rpc WatchOrders(WatchOrdersRequest) returns (stream OrderEvent);** | Một request, không đến nhiều response | Theo dõi thay đổi, phát dữ liệu dần |
| **Client streaming** | **rpc ImportOrderEvents(stream OrderEvent) returns (ImportOrderEventsResponse);** | Không đến nhiều request, một response thành công | Import hoặc tổng hợp batch |
| **Bidirectional streaming** | **rpc SyncOrders(stream SyncOrdersRequest) returns (stream SyncOrdersResponse);** | Không đến nhiều message ở mỗi chiều | Đồng bộ hai chiều hoặc phiên tương tác |

Một unary RPC **thành công** cần trả đúng một response message thuộc kiểu khai báo. Khi lỗi, server có thể kết thúc bằng status mà không trả response message thành công. Với streaming, một phía có thể gửi **0..n** message trước khi kết thúc.

### 3.1. Unary

~~~proto
rpc GetOrder(GetOrderRequest) returns (GetOrderResponse);
~~~

Client tạo **GetOrderRequest**, gọi stub, nhận **GetOrderResponse** hoặc lỗi gRPC. Đây là lựa chọn đơn giản cho phần lớn thao tác có kết quả hữu hạn, ví dụ đọc trạng thái đơn hàng.

### 3.2. Server streaming

~~~proto
rpc WatchOrders(WatchOrdersRequest) returns (stream OrderEvent);
~~~

Client gửi **một** WatchOrdersRequest và nhận nhiều **OrderEvent**. Server có thể phát kết quả theo từng phần, dừng khi không còn dữ liệu hoặc khi client hủy/deadline hết hạn. Trong Java, caller có thể dùng async stub và response observer; blocking stub truyền thống cũng hỗ trợ server-streaming qua **Iterator**.

**Không được giả định stream luôn chạy mãi.** Một stream có thể hoàn thành bình thường, kết thúc vì lỗi hoặc bị hủy. API cần định nghĩa rõ quy tắc dừng, tần suất sự kiện, cursor/resume nếu cần.

### 3.3. Client streaming

~~~proto
rpc ImportOrderEvents(stream OrderEvent) returns (ImportOrderEventsResponse);
~~~

Client mở lời gọi rồi gửi nhiều **OrderEvent**; sau message cuối, client gọi **onCompleted()** trên request observer để half-close chiều gửi. Server xử lý và phát một **ImportOrderEventsResponse** tổng hợp trước khi hoàn tất RPC.

Nếu client quên half-close, server có thể tiếp tục chờ thêm dữ liệu và lời gọi chỉ kết thúc khi có deadline, cancellation hoặc lỗi.

### 3.4. Bidirectional streaming

~~~proto
rpc SyncOrders(stream SyncOrdersRequest) returns (stream SyncOrdersResponse);
~~~

Hai phía có thể gửi message độc lập: server có thể trả một phản hồi ngay khi client chưa kết thúc gửi request. Không mặc định ánh xạ **một request ↔ một response**. Nếu cần cơ chế ACK, sequence number, giao thức bắt tay, retry hoặc resume, chúng phải được mô tả trong **message** và tài liệu contract.

~~~mermaid
sequenceDiagram
    participant Client
    participant Server
    Client->>Server: SyncOrdersRequest(cursor="a")
    Server-->>Client: SyncOrdersResponse(next_cursor="b")
    Server-->>Client: SyncOrdersResponse(next_cursor="c")
    Client->>Server: SyncOrdersRequest(cursor="c")
    Client->>Server: half-close (done sending)
    Server-->>Client: SyncOrdersResponse(next_cursor="d")
    Server-->>Client: trailers grpc-status=OK
~~~

Mặc dù có nhiều message, tất cả chúng thuộc **một RPC trên một HTTP/2 stream**; khác với việc tạo một stream HTTP/2 riêng cho mỗi message.

## 4. Cách thiết kế request message

Một request nên thể hiện **ý định rõ ràng** và chứa đủ dữ liệu nghiệp vụ cần thiết, ví dụ:

~~~proto
message GetOrderRequest {
  string order_id = 1;
  optional string locale = 2;
}
~~~

Ở đây:

- **order_id** là định danh nghiệp vụ để tìm đơn hàng. Proto3 cho phép trường này vắng mặt và getter của string trả chuỗi rỗng, nên **server cần tự kiểm tra** nếu muốn bắt buộc có ID.
- **locale** là tùy chọn; **optional string** cho phép phân biệt **chưa gửi** với **đã gửi chuỗi rỗng**.
- Số **1**, **2** là **field number** trên wire format protobuf, không phải số thứ tự hiển thị trong JSON hay số thứ tự tham số Java.

Trong Java sinh mã, đoạn tạo request có thể là:

~~~java
GetOrderRequest request = GetOrderRequest.newBuilder()
        .setOrderId("order-42")
        .setLocale("vi-VN")
        .build();

// Java class được sinh từ proto3 optional thường có:
boolean localeProvided = request.hasLocale();
~~~

Vì message protobuf Java được sinh thường có tính bất biến sau khi **build()**, việc tạo biến thể request khác thực hiện thông qua builder hoặc **toBuilder()**. Điều này hữu ích khi nhiều thread xử lý request nhưng không làm thay trách nhiệm đồng bộ hóa logic ứng dụng.

### 4.1. Lựa chọn field type

| Kiểu protobuf | Ví dụ | Cân nhắc khi thiết kế |
| --- | --- | --- |
| **string** | ID, tên, locale | UTF-8, giá trị mặc định rỗng; nên ghi rõ quy tắc kiểm tra |
| **int32/int64** | Số lượng, timestamp | Xác định đơn vị, miền giá trị; int64 có cách biểu diễn riêng trong ProtoJSON |
| **bool** | Cờ tính năng | Giá trị mặc định **false**; dùng **optional** nếu cần phân biệt không gửi |
| **bytes** | Hash/dữ liệu nhị phân | Tránh đưa payload không giới hạn vào một message |
| **enum** | Trạng thái đơn | Giá trị 0 nên là **UNSPECIFIED**; xử lý unknown value |
| **message** | Đối tượng lồng nhau | Có thể kiểm tra presence cho singular message field |
| **repeated T** | Danh sách dòng hàng | Giới hạn số phần tử; thứ tự có thể có ý nghĩa |
| **map<K,V>** | Thuộc tính theo khóa | Map không bảo đảm thứ tự nghiệp vụ; tránh giả định thứ tự khi serialize |
| **oneof** | Một trong các cách nhận diện | Biểu diễn các phương án loại trừ nhau |
| **optional T** | Trường scalar có presence | Phân biệt không có giá trị với giá trị mặc định |

Định nghĩa **timestamp** bằng **int64 created_at_epoch_ms** là một cách, nhưng phải ghi rõ đơn vị. Một lựa chọn biểu đạt thời gian có ngữ nghĩa hơn là kiểu chuẩn **google.protobuf.Timestamp**:

~~~proto
import "google/protobuf/timestamp.proto";

message OrderAudit {
  string order_id = 1;
  google.protobuf.Timestamp occurred_at = 2;
}
~~~

Hãy chọn quy ước thống nhất cho toàn bộ API; không trộn giây, mili giây và micro giây mà không nêu rõ.

### 4.2. Presence: "không được gửi" khác "được gửi rỗng"

Trong proto3, nhiều scalar field không có presence tường minh nếu khai báo theo dạng thông thường:

~~~proto
message UpdateOrderRequest {
  string order_id = 1;
  string note = 2;
}
~~~

Với **note** thường, Java getter **getNote()** trả **""** cho cả trường hợp chưa gửi và trường hợp gửi giá trị chuỗi rỗng. Điều này có thể làm một API cập nhật bị mơ hồ: người dùng muốn xóa ghi chú hay không thay đổi ghi chú?

Dạng **optional** giải quyết một phần:

~~~proto
message UpdateOrderRequest {
  string order_id = 1;
  optional string note = 2;
}
~~~

Với mã Java được sinh tương ứng:

~~~java
if (request.hasNote()) {
    // Client chủ động yêu cầu cập nhật note,
    // kể cả khi giá trị là chuỗi rỗng.
    String newNote = request.getNote();
}
~~~

Nếu cần hỗ trợ cập nhật nhiều field theo kiểu patch, có thể dùng **google.protobuf.FieldMask** hoặc thiết kế request update riêng. Chính sách về field được phép cập nhật và giá trị rỗng vẫn phải được tài liệu hóa rõ.

### 4.3. Oneof cho nhiều loại request

~~~proto
message FindOrderRequest {
  oneof lookup_key {
    string order_id = 1;
    string external_reference = 2;
  }
}
~~~

**oneof** biểu diễn lựa chọn tối đa một trường trong nhóm. Nó **không bắt buộc** phải có ít nhất một trường: server cần kiểm tra **lookup_key** đã được thiết lập trước khi xử lý. Trong Java, mã sinh có thể cung cấp **getLookupKeyCase()** để nhận biết lựa chọn.

Một lỗi thiết kế thường gặp là dùng nhiều trường scalar như **order_id**, **external_reference** đồng thời nhưng không quy định ưu tiên khi cả hai cùng có giá trị. **oneof** làm hợp đồng rõ hơn và giảm khả năng mơ hồ.

### 4.4. Kiểm tra request đặt ở đâu?

Proto chỉ quy định cấu trúc và một số ràng buộc kiểu. Nó không đảm bảo **order_id** tồn tại, **quantity** lớn hơn 0, hay caller có quyền đọc đơn hàng. Vì thế:

- **Client** kiểm tra sớm những dữ liệu biết chắc để tránh RPC không cần thiết; không thể coi đây là lớp bảo vệ duy nhất.
- **Server implementation** thực thi validation và authorization cho mọi lời gọi.
- **Interceptor** phù hợp với xác thực, tracing và các chính sách xuyên service, nhưng validation nghiệp vụ thường nằm ở service/domain layer.
- **Status.INVALID_ARGUMENT** cho request không hợp lệ; **NOT_FOUND** cho tài nguyên không tồn tại; **PERMISSION_DENIED** khi caller không có quyền.

Dù dùng thư viện validation gắn với protobuf, việc khai báo rule trong schema chỉ có hiệu lực nếu quá trình build/runtime thực sự có thành phần thi hành rule đó.

## 5. Cách thiết kế response message

Phương thức **GetOrder** trả response wrapper:

~~~proto
message GetOrderResponse {
  Order order = 1;
  string etag = 2;
}
~~~

Ưu điểm của wrapper riêng là có thể bổ sung thông tin như **etag**, paging token hoặc provenance mà không phải thay kiểu response của method. Điều này cũng giúp phần payload thành công tách khỏi status/error gRPC.

Trong Java:

~~~java
Order order = Order.newBuilder()
        .setId("order-42")
        .setCustomerId("customer-7")
        .setStatus(OrderStatus.ORDER_STATUS_PENDING)
        .setCreatedAtEpochMs(1_700_000_000_000L)
        .build();

GetOrderResponse response = GetOrderResponse.newBuilder()
        .setOrder(order)
        .setEtag("version-3")
        .build();
~~~

Vì **order** là singular message field, client có thể kiểm tra **hasOrder()** trước khi đọc. Với API **GetOrder**, nếu quy ước thành công phải có order, server phải bảo đảm điều đó; proto không tự bắt buộc field message tồn tại.

### 5.1. Response của danh sách và phân trang

Với unary RPC trả một danh sách, thường dùng wrapper để mang dữ liệu và token phân trang:

~~~proto
message SearchOrdersRequest {
  string customer_id = 1;
  int32 page_size = 2;
  string page_token = 3;
}

message SearchOrdersResponse {
  repeated Order orders = 1;
  string next_page_token = 2;
}
~~~

Cần thống nhất **page_size** tối đa, ý nghĩa **next_page_token** rỗng và tính ổn định của kết quả khi dữ liệu thay đổi. **repeated Order** giúp gửi nhiều phần tử trong một response, nhưng vẫn là **một protobuf message** của unary RPC; đối với danh sách rất lớn, cần cân nhắc paging hoặc server streaming.

### 5.2. Khi nào nên dùng response chứa mã lỗi nghiệp vụ?

Không nên tạo field **success: bool** hoặc **error_code** rồi mặc định mọi lời gọi đều trả **grpc-status: OK**, nếu lỗi thực tế cần biểu diễn bằng gRPC status. Cách đó khiến client/metrics khó phân biệt RPC hỏng với RPC thành công.

Tuy vậy, một response thành công có thể chứa trạng thái nghiệp vụ hợp lệ: ví dụ đơn hàng đang **PENDING** hay **COMPLETED** là dữ liệu của **OrderStatus**, không phải lỗi transport. Hãy phân biệt:

| Tình huống | Cách biểu diễn thường phù hợp |
| --- | --- |
| Tìm thấy đơn đang chờ xử lý | **GetOrderResponse.order.status = PENDING**, gRPC **OK** |
| Request thiếu ID | **INVALID_ARGUMENT**, mô tả lỗi an toàn |
| Đơn không tồn tại | **NOT_FOUND** |
| Caller không được xem đơn | **PERMISSION_DENIED**, tránh lộ thông tin |
| Backend tạm không sẵn sàng | **UNAVAILABLE** |
| RPC vượt thời hạn | **DEADLINE_EXCEEDED** phía caller |

Khi cần chi tiết lỗi có cấu trúc, hệ sinh thái gRPC có thể dùng **google.rpc.Status** và error details qua cơ chế rich error model. Đây là một lựa chọn mở rộng, cần hỗ trợ tương ứng ở client/server; không nên nhầm message **google.rpc.Status** với **grpc-status** cơ bản trong HTTP/2 trailers.

## 6. Từ message đến bytes: gRPC chở dữ liệu ra sao?

Request/response message Java được sinh có chức năng serialize/deserialize theo protobuf. Stub và runtime áp dụng message marshaller rồi truyền qua HTTP/2.

Một gRPC message trên wire thường được biểu diễn:

~~~text
+----------------+--------------------------+-------------------------+
| Compressed-Flag| Message-Length           | Message bytes           |
| 1 byte         | 4 bytes, big-endian      | serialized protobuf     |
+----------------+--------------------------+-------------------------+
~~~

**Năm byte đầu** là lớp đóng khung message của gRPC: 1 byte cờ nén và 4 byte độ dài payload. Nhiều message có thể lần lượt xuất hiện trên một HTTP/2 stream. Một message có thể bị chia qua nhiều HTTP/2 DATA frame; ngược lại một DATA frame có thể chứa các phần của nhiều message. Do đó:

- **Protobuf message** không đồng nghĩa **HTTP/2 frame**.
- **Một RPC** không đồng nghĩa **một protobuf message** nếu dùng streaming.
- **Một RPC** thường dùng **một HTTP/2 stream**, ngay cả khi có hàng trăm message.
- **HTTP/2 connection** có thể multiplex nhiều RPC/stream song song.

Ví dụ unary **GetOrder**:

~~~text
Client -> Server:
  HEADERS   :method=POST
            :path=/shop.orders.v1.OrderQueryService/GetOrder
            content-type=application/grpc
            te=trailers
            grpc-timeout=2S
  DATA      [5-byte gRPC prefix][serialized GetOrderRequest]
  END_STREAM (client hoàn tất chiều gửi)

Server -> Client:
  HEADERS   :status=200
            content-type=application/grpc
  DATA      [5-byte gRPC prefix][serialized GetOrderResponse]
  HEADERS   grpc-status=0    (trailers)
  END_STREAM
~~~

Đây là biểu diễn **logic** để học, không phải dump frame nhị phân thực tế. Header **grpc-timeout** là thời lượng tương đối còn lại trước deadline và được runtime dùng trong phạm vi phù hợp; việc gửi chính xác ra sao phụ thuộc caller và transport. Trường hợp lỗi có thể là phản hồi **trailers-only** mà không có response DATA.

**HTTP status 200 không đảm bảo RPC thành công.** Client gRPC xử lý **grpc-status** ở cuối trao đổi và chuyển thành kết quả hoặc lỗi tương ứng.

### 6.1. Kích thước message và hiệu năng

Protobuf có thể biểu diễn dữ liệu gọn hơn JSON trong nhiều kịch bản, nhưng hiệu quả cụ thể tùy schema và payload. Không nên suy rằng gRPC luôn nhanh hơn bất kể ngữ cảnh.

Cần quan sát:

- **Serialized message size** và giới hạn message nhận/gửi do framework/transport cấu hình.
- **Số phần tử repeated**: một unary response rất lớn có thể khiến cấp phát bộ nhớ tăng đột biến.
- **Tần suất message streaming** và chi phí callback/serialization.
- **HTTP/2 flow control** ở mức stream và connection; phía gửi có thể phải chờ bên nhận.
- **Deadline và cancellation**: xử lý vô ích sau khi caller rời đi làm tiêu tốn tài nguyên.
- **Compression**: có thể giảm băng thông nhưng tốn CPU; chỉ bật khi đánh giá thực tế.

Với API trả rất nhiều bản ghi, thường nên so sánh **unary + paging** với **server streaming**, xét trải nghiệm client, chi phí hồi phục, tải backend và khả năng tiếp tục sau gián đoạn.

## 7. Triển khai unary method trong Spring với grpc-java

Dưới đây là ví dụ **gRPC Java thuần được Spring quản lý bean**, sử dụng message và service đã định nghĩa ở mục 2. Nó tách **service implementation**, **server registration** và **client stub** để nhìn rõ kiến trúc. Khi dùng Spring gRPC auto-configuration, cần sử dụng cơ chế đăng ký service/stub theo phiên bản thư viện đang tích hợp, tránh tạo server trùng cổng.

### 7.1. Server implementation

~~~java
package com.example.shop.server;

import com.example.shop.orders.v1.GetOrderRequest;
import com.example.shop.orders.v1.GetOrderResponse;
import com.example.shop.orders.v1.Order;
import com.example.shop.orders.v1.OrderQueryServiceGrpc;
import com.example.shop.orders.v1.OrderStatus;
import io.grpc.Status;
import io.grpc.stub.StreamObserver;
import org.springframework.stereotype.Component;

@Component
public class OrderQueryEndpoint
        extends OrderQueryServiceGrpc.OrderQueryServiceImplBase {

    @Override
    public void getOrder(
            GetOrderRequest request,
            StreamObserver<GetOrderResponse> responseObserver) {

        String orderId = request.getOrderId().trim();

        if (orderId.isEmpty()) {
            responseObserver.onError(
                    Status.INVALID_ARGUMENT
                            .withDescription("order_id không được rỗng")
                            .asRuntimeException());
            return;
        }

        // Demo: kho dữ liệu chỉ chứa một đơn hàng.
        if (!"order-42".equals(orderId)) {
            responseObserver.onError(
                    Status.NOT_FOUND
                            .withDescription("Không tìm thấy đơn hàng")
                            .asRuntimeException());
            return;
        }

        Order order = Order.newBuilder()
                .setId("order-42")
                .setCustomerId("customer-7")
                .setStatus(OrderStatus.ORDER_STATUS_PENDING)
                .setCreatedAtEpochMs(1_700_000_000_000L)
                .build();

        GetOrderResponse response = GetOrderResponse.newBuilder()
                .setOrder(order)
                .setEtag("version-3")
                .build();

        responseObserver.onNext(response);
        responseObserver.onCompleted();
    }
}
~~~

Phương thức **getOrder(...)** có chữ ký theo lớp cơ sở được sinh. **StreamObserver<GetOrderResponse>** là API callback ở tầng ứng dụng; nó không phải đối tượng HTTP/2 stream mà ta trực tiếp thao tác.

Với unary thành công, server gửi **một** response qua **onNext()**, sau đó **onCompleted()**. Với lỗi, gửi **onError()** rồi dừng. Một RPC không được phát tiếp response sau khi đã gọi **onCompleted()** hoặc **onError()**. Server thật nên chuyển logic lấy đơn hàng sang service nghiệp vụ/repository và ánh xạ exception phù hợp, hạn chế để lộ chi tiết nội bộ trong description.

### 7.2. Đăng ký với gRPC server

~~~java
package com.example.shop.server;

import io.grpc.Server;
import io.grpc.ServerBuilder;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
public class GrpcServerConfig {

    @Bean(initMethod = "start", destroyMethod = "shutdown")
    Server orderServer(OrderQueryEndpoint endpoint) {
        return ServerBuilder.forPort(9090)
                .addService(endpoint)
                .build();
    }
}
~~~

**@Component** đăng ký implementation trong Spring context. **addService(endpoint)** mới đăng ký method handler vào gRPC server. Hai bước này là trách nhiệm khác nhau.

Cấu hình **initMethod = "start"** khởi động server lúc khởi tạo bean; **destroyMethod = "shutdown"** yêu cầu dừng khi đóng Spring context. Production nên có chiến lược **graceful shutdown**, chờ có giới hạn để RPC đang chạy hoàn tất.

Ví dụ chỉ override **GetOrder**. Những RPC còn lại trong hợp đồng sẽ cần triển khai riêng; gọi method chưa override thường nhận **UNIMPLEMENTED** từ lớp cơ sở.

### 7.3. Client stub và ManagedChannel trong Spring

Ví dụ sau nằm trong **ứng dụng client riêng**:

~~~java
package com.example.shop.client;

import com.example.shop.orders.v1.OrderQueryServiceGrpc;
import io.grpc.ManagedChannel;
import io.grpc.ManagedChannelBuilder;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
public class GrpcClientConfig {

    @Bean(destroyMethod = "shutdown")
    ManagedChannel orderChannel() {
        // Demo local; không dùng plaintext làm mặc định cho môi trường thật.
        return ManagedChannelBuilder.forAddress("localhost", 9090)
                .usePlaintext()
                .build();
    }

    @Bean
    OrderQueryServiceGrpc.OrderQueryServiceBlockingStub orderStub(
            ManagedChannel orderChannel) {
        return OrderQueryServiceGrpc.newBlockingStub(orderChannel);
    }
}
~~~

~~~java
package com.example.shop.client;

import com.example.shop.orders.v1.GetOrderRequest;
import com.example.shop.orders.v1.GetOrderResponse;
import com.example.shop.orders.v1.OrderQueryServiceGrpc;
import io.grpc.Status;
import io.grpc.StatusRuntimeException;
import java.util.concurrent.TimeUnit;
import org.springframework.stereotype.Service;

@Service
public class OrderLookupClient {
    private final OrderQueryServiceGrpc.OrderQueryServiceBlockingStub stub;

    public OrderLookupClient(
            OrderQueryServiceGrpc.OrderQueryServiceBlockingStub stub) {
        this.stub = stub;
    }

    public GetOrderResponse findOrder(String orderId) {
        GetOrderRequest request = GetOrderRequest.newBuilder()
                .setOrderId(orderId)
                .build();

        try {
            return stub.withDeadlineAfter(2, TimeUnit.SECONDS)
                    .getOrder(request);
        } catch (StatusRuntimeException error) {
            Status.Code code = error.getStatus().getCode();
            // Ví dụ: tầng ứng dụng sẽ ánh xạ code sang lỗi phù hợp.
            throw new IllegalStateException(
                    "GetOrder thất bại: " + code, error);
        }
    }
}
~~~

**ManagedChannel** nên được tái sử dụng để tránh mở một connection mới mỗi lần gọi. **withDeadlineAfter(...)** tạo một stub mới với call options của lời gọi; đặt deadline gần thời điểm gọi để không giữ deadline đã hết hạn trên stub sống lâu.

**Blocking stub** hợp với unary trong luồng đồng bộ nhưng chặn thread của caller. Với các RPC streaming hoặc ứng dụng bất đồng bộ, sử dụng async stub và quản lý lifecycle observer, backpressure, cancellation.

**usePlaintext()** chỉ dùng cho ví dụ local hoặc đường truyền được kiểm soát. Ở môi trường thật, cấu hình TLS/mTLS, chain xác thực và credential theo kiến trúc triển khai.

## 8. Mapping method sang API client/server trong grpc-java

Định nghĩa RPC quyết định chữ ký Java mà generator sinh. Bảng sau giúp đọc code từ hai phía.

| RPC | Server override | Client sử dụng |
| --- | --- | --- |
| **Unary GetOrder** | **void getOrder(GetOrderRequest, StreamObserver<GetOrderResponse>)** | Blocking stub trả **GetOrderResponse**; async stub nhận response observer |
| **Server streaming WatchOrders** | **void watchOrders(WatchOrdersRequest, StreamObserver<OrderEvent>)** | Blocking stub trả **Iterator<OrderEvent>**; async stub nhận nhiều onNext |
| **Client streaming ImportOrderEvents** | **StreamObserver<OrderEvent> importOrderEvents(StreamObserver<ImportOrderEventsResponse>)** | Async stub trả request observer, caller gửi nhiều onNext |
| **Bidi SyncOrders** | **StreamObserver<SyncOrdersRequest> syncOrders(StreamObserver<SyncOrdersResponse>)** | Async stub trả request observer, nhận response độc lập |

Một số cách sinh mã hoặc phiên bản thư viện có thêm biến thể stub, nhưng các kiểu RPC và hướng message vẫn do hợp đồng quyết định.

### 8.1. Hai observer trong client streaming

~~~java
// asyncStub là OrderQueryServiceGrpc.OrderQueryServiceStub.
// Chỉ là ví dụ luồng callback, chưa xử lý retry/backpressure.
StreamObserver<ImportOrderEventsResponse> responseObserver =
        new StreamObserver<ImportOrderEventsResponse>() {
    @Override
    public void onNext(ImportOrderEventsResponse value) {
        System.out.println("Accepted: " + value.getAcceptedCount());
    }

    @Override
    public void onError(Throwable error) {
        System.err.println(
                "RPC failed: " + Status.fromThrowable(error).getCode());
    }

    @Override
    public void onCompleted() {
        System.out.println("Import completed");
    }
};

StreamObserver<OrderEvent> requestObserver =
        asyncStub.importOrderEvents(responseObserver);

requestObserver.onNext(OrderEvent.newBuilder()
        .setOrderId("order-42")
        .setNewStatus(OrderStatus.ORDER_STATUS_COMPLETED)
        .build());

requestObserver.onCompleted();
~~~

Trong snippet này, các loại **StreamObserver**, **Status**, **OrderEvent**, **OrderStatus**, **ImportOrderEventsResponse** được import từ grpc-java và mã sinh, còn **asyncStub** đã được tạo từ Channel dùng chung.

**requestObserver.onCompleted()** chỉ đánh dấu client đã xong chiều gửi. Caller vẫn cần chờ **responseObserver.onCompleted()** hoặc **onError()** để biết kết quả cuối cùng của RPC.

### 8.2. Nhiều response không có nghĩa nhiều method call

Nếu server gửi ba **OrderEvent** trong một lời gọi **WatchOrders**, client thường nhận ba lần **onNext(...)** rồi một lần **onCompleted()**. Điều đó vẫn là một call, một deadline và một status kết thúc. Với streaming, mỗi observer gắn với **một RPC cụ thể**, không tái sử dụng observer của call đã kết thúc cho call mới.

Nếu có nhiều thread cùng phát message lên một **StreamObserver**, ứng dụng cần điều phối ghi; observer không tự bảo đảm thread-safe cho các lần gọi đồng thời. Khi gửi khối lượng lớn, dùng các tín hiệu **isReady()/setOnReadyHandler(...)** trên observer chuyên biệt của grpc-java để kết hợp flow control và backpressure.

## 9. Metadata, deadline, status và interceptor liên quan đến method

Dù request/response message xác định dữ liệu nghiệp vụ, một RPC thực tế còn có ngữ cảnh về quyền truy cập, giới hạn thời gian và truy vết.

### 9.1. Metadata nằm ngoài request message

**Metadata** thường đi trong headers/trailers, ví dụ authorization token và correlation ID. Không nên nhét token xác thực vào mọi request message chỉ để truyền giữa services; phù hợp hơn là sử dụng **CallCredentials** hoặc client interceptor theo cơ chế của ứng dụng.

Nếu một trường có ý nghĩa nghiệp vụ, cần lưu/audit như **customer_id**, nó có thể thuộc request/response schema. Nếu chỉ là **trace ID** hoặc credential dùng xuyên nhiều method, metadata là vị trí thích hợp hơn. Tránh ghi token hoặc thông tin bí mật vào log.

### 9.2. Deadline là thuộc tính của lời gọi

Giả sử client gọi **GetOrder** với deadline 2 giây. Nếu backend chậm, caller có thể nhận **DEADLINE_EXCEEDED** ngay cả khi request có cấu trúc hoàn toàn hợp lệ. Việc tăng deadline không thay thế tối ưu backend hay kiểm soát quá tải.

Server nên quan sát cancellation và dừng công việc không còn cần thiết khi client đã ngắt. Tuy nhiên, client timeout **không bảo đảm** server đã rollback thao tác ghi; đối với RPC có tác dụng phụ, chính sách retry cần xét tính **idempotent** và khả năng xử lý trùng request.

### 9.3. Đừng nhầm mã trạng thái nghiệp vụ với gRPC status

**OrderStatus.ORDER_STATUS_PENDING** chỉ trạng thái đơn hàng được trả trong response thành công. **Status.NOT_FOUND** là lỗi của lời gọi tìm kiếm.

| Trường hợp | Phần dữ liệu/status |
| --- | --- |
| Đơn tìm thấy, đang chờ | **GetOrderResponse.order.status = PENDING**, gRPC **OK** |
| Request không có order_id | Không có response thành công; gRPC **INVALID_ARGUMENT** |
| Đơn không tồn tại | Không có response thành công; gRPC **NOT_FOUND** |
| Caller không được phép | gRPC **PERMISSION_DENIED** |
| Server/connection tạm không khả dụng | Thường gặp gRPC **UNAVAILABLE** |
| Deadline hết trước khi xong | Caller nhận **DEADLINE_EXCEEDED** |

Một response HTTP/2 có **:status 200** vẫn có thể chứa gRPC status lỗi. Hãy lấy status từ exception/callback gRPC và metrics theo method, không chỉ dựa vào HTTP status.

### 9.4. Interceptor dùng cho hành vi chung

Interceptor phù hợp để gắn/đọc metadata, triển khai xác thực, thống kê latency, tracing và audit ở **mức RPC**. Logic kiểm tra quyền trên đối tượng đơn hàng vẫn cần được thực hiện ở server/business layer theo mô hình phân quyền của ứng dụng.

Interceptors không bắt buộc xuất hiện trong file .proto và không tự can thiệp vào từng frame HTTP/2. Tương tự, service definition không tự bật TLS: Channel và gRPC server phải được cấu hình đúng, cùng với proxy/LB có hỗ trợ HTTP/2 và ALPN khi dùng TLS.

## 10. Versioning và tương thích request/response

Các message là **contract dùng chung**. Thay đổi cách giải nghĩa field có thể gây lỗi âm thầm dù code vẫn compile được, đặc biệt khi client và server triển khai ở các thời điểm khác nhau.

### 10.1. Field number là danh tính trên wire

~~~proto
message GetOrderRequest {
  string order_id = 1;
  optional string locale = 2;
}
~~~

Nếu muốn thêm **request_source**, thông thường có thể dùng field number mới:

~~~proto
message GetOrderRequest {
  string order_id = 1;
  optional string locale = 2;
  string request_source = 3;
}
~~~

Client cũ thường bỏ qua trường mới mà không biết; client mới khi nhận message từ client/server cũ sẽ thấy giá trị mặc định tương ứng. Nhưng **wire compatibility** không đảm bảo **semantic compatibility**: nếu server mới bắt buộc request_source khác rỗng, client cũ sẽ bị từ chối.

Khi xóa field đã dùng, không được tái sử dụng field number cho ý nghĩa mới. Dùng **reserved** cho số hiệu và tên cũ:

~~~proto
message ArchivedOrder {
  reserved 3, 7;
  reserved "legacy_flag", "legacy_state";
  string id = 1;
  string customer_id = 2;
}
~~~

Việc reserve giúp ngăn compiler cho phép dùng lại số hiệu/tên; nó không tự chuyển đổi dữ liệu đã lưu.

### 10.2. Các thay đổi cần đánh giá

| Thay đổi | Tác động thường gặp | Khuyến nghị |
| --- | --- | --- |
| Thêm field mới, số hiệu mới | Thường wire-compatible | Ghi rõ giá trị mặc định và fallback |
| Thêm enum value | Wire format có thể đọc được, nhưng client cũ chưa biết value | Xử lý unknown/UNRECOGNIZED theo API và không assume mọi value đã liệt kê |
| Đổi số hiệu field | Dễ phá dữ liệu đã có | Giữ field number ổn định |
| Tái sử dụng field number đã xóa | Nguy cơ hiểu sai dữ liệu cũ | Dùng **reserved** |
| Đổi kiểu field | Có thể đổi wire type/presence/range/semantics | Đánh giá quy tắc tương thích cụ thể trước khi áp dụng |
| Đổi protobuf package/service/method | Đổi full RPC path | Coi là breaking với client cũ |
| Đổi unary thành streaming | Đổi method descriptor và API callback | Coi là breaking; tạo method mới |
| Thêm RPC method | Thường không ảnh hưởng lời gọi cũ | Triển khai/đăng ký trước khi client mới gọi |
| Đổi ý nghĩa dữ liệu trong field cũ | Có thể phá hành vi dù wire vẫn hợp lệ | Tạo field/version mới hoặc migration có kiểm soát |

**Ví dụ:** nếu **created_at_epoch_ms** ban đầu là mili giây nhưng server đổi sang giây mà vẫn giữ field number và tên cũ, dữ liệu trên wire vẫn là int64 nhưng client sẽ diễn giải sai thời gian. Đây là lỗi tương thích ngữ nghĩa.

### 10.3. Thiết kế API version

Namespace như **shop.orders.v1** giúp phân biệt hợp đồng theo phiên bản. Nếu thay đổi có thể phá client đang chạy, hãy cân nhắc phát hành **shop.orders.v2.OrderQueryService**, duy trì v1 trong giai đoạn chuyển tiếp và kiểm thử cross-version. Đổi package v1 sang v2 trực tiếp làm đổi đường dẫn RPC; client cũ không tự tìm thấy endpoint mới.

Quy tắc triển khai an toàn thường là: thêm field/endpoint mới trước, triển khai server tương thích, cập nhật client, theo dõi lưu lượng cũ, sau cùng mới loại bỏ những API đã ngừng được dùng theo kế hoạch rõ ràng.

## 11. Kiểm thử method và message với grpc-inprocess

Kiểm thử trực tiếp implementation bằng việc gọi Java method chỉ chứng minh một phần logic. Để kiểm chứng **generated stub → descriptor → gRPC runtime → registered implementation → response/status**, có thể dùng transport **in-process**.

Ví dụ JUnit 5 dưới đây sử dụng **OrderQueryEndpoint** ở mục 7; cần dependency **grpc-inprocess** tương thích với phiên bản grpc-java, cùng lớp protobuf sinh mã.

~~~java
package com.example.shop.server;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;

import com.example.shop.orders.v1.GetOrderRequest;
import com.example.shop.orders.v1.GetOrderResponse;
import com.example.shop.orders.v1.OrderQueryServiceGrpc;
import io.grpc.ManagedChannel;
import io.grpc.Server;
import io.grpc.Status;
import io.grpc.StatusRuntimeException;
import io.grpc.inprocess.InProcessChannelBuilder;
import io.grpc.inprocess.InProcessServerBuilder;
import org.junit.jupiter.api.Test;

class OrderQueryEndpointTest {

    @Test
    void getOrderReturnsResponseAndValidatesRequest() throws Exception {
        String serverName = InProcessServerBuilder.generateName();

        Server server = InProcessServerBuilder.forName(serverName)
                .directExecutor()
                .addService(new OrderQueryEndpoint())
                .build()
                .start();

        ManagedChannel channel = InProcessChannelBuilder.forName(serverName)
                .directExecutor()
                .build();

        try {
            OrderQueryServiceGrpc.OrderQueryServiceBlockingStub stub =
                    OrderQueryServiceGrpc.newBlockingStub(channel);

            GetOrderResponse result = stub.getOrder(
                    GetOrderRequest.newBuilder()
                            .setOrderId("order-42")
                            .build());

            assertEquals("order-42", result.getOrder().getId());

            StatusRuntimeException invalid = assertThrows(
                    StatusRuntimeException.class,
                    () -> stub.getOrder(
                            GetOrderRequest.newBuilder().build()));

            assertEquals(Status.Code.INVALID_ARGUMENT,
                    invalid.getStatus().getCode());

            StatusRuntimeException missing = assertThrows(
                    StatusRuntimeException.class,
                    () -> stub.getOrder(
                            GetOrderRequest.newBuilder()
                                    .setOrderId("order-404")
                                    .build()));

            assertEquals(Status.Code.NOT_FOUND,
                    missing.getStatus().getCode());
        } finally {
            channel.shutdownNow();
            server.shutdownNow();
        }
    }
}
~~~

**directExecutor()** giúp test đơn giản vì callback có thể chạy trực tiếp; không phù hợp để mô phỏng hoạt động phức tạp với blocking hoặc concurrency. Kiểm thử in-process bao phủ nhiều phần của gRPC Java nhưng **không xác minh** cấu hình TLS, proxy HTTP/2, DNS, load balancing hay lỗi kết nối mạng thật.

Nên bổ sung kiểm thử theo nhu cầu:

- **Serialization/compatibility**: client và server dùng hai phiên bản schema, kiểm tra field mới/cũ.
- **Method registration**: gọi method đã triển khai và chưa triển khai để xác định status đúng.
- **Validation/error**: ID rỗng, không có quyền, không tìm thấy và lỗi backend.
- **Deadline/cancellation**: backend chậm hoặc client hủy, theo dõi tài nguyên được giải phóng.
- **Streaming**: nhiều message, kết thúc đúng một lần, backpressure và tình huống nửa chừng mất kết nối.
- **Observability**: metrics/tracing phải phân biệt đầy đủ tên method và gRPC status.

## 12. Các lỗi thiết kế và chẩn đoán thường gặp

| Triệu chứng | Nguyên nhân khả dĩ | Cách xử lý |
| --- | --- | --- |
| **UNIMPLEMENTED** khi gọi một method | Tên service/method không khớp hoặc server chưa đăng ký/override handler | So sánh full method name, version proto, registration |
| Caller tưởng order_id bắt buộc nhưng server nhận rỗng | Proto3 không tự enforce required string | Kiểm tra input tại server hoặc áp dụng validation runtime rõ ràng |
| Client không biết phân biệt "vắng mặt" với "rỗng" | Trường scalar thiếu presence | Dùng **optional**, **oneof** hoặc field mask theo use case |
| Server trả status OK dù nghiệp vụ lỗi | Nhét mã lỗi vào payload và vẫn onCompleted | Ánh xạ lỗi thật bằng gRPC status phù hợp |
| Client nhận HTTP 200 nhưng RPC thất bại | Chỉ đọc HTTP status | Đọc **grpc-status** và exception/callback gRPC |
| Đổi field number khiến dữ liệu đọc sai | Phá hợp đồng wire format | Khôi phục tag cũ, reserve tag bị xóa và quản lý migration |
| Unary response quá lớn | repeated field chứa toàn bộ dữ liệu không giới hạn | Phân trang, giới hạn kích thước hoặc server streaming |
| Client-streaming không có kết quả | Client chưa half-close request observer | Gọi **onCompleted()** khi gửi xong, chờ terminal callback từ server |
| Stream chậm hoặc chiếm nhiều bộ nhớ | Bên nhận chậm, hàng đợi không giới hạn, thiếu backpressure | Dùng cơ chế isReady/onReady phù hợp, giới hạn inflight |
| Deadline hết nhưng thao tác ghi vẫn xảy ra | Server đã commit trước khi caller biết timeout | Thiết kế idempotency key/reconciliation cho thao tác ghi |
| Method chạy local nhưng lỗi sau reverse proxy | HTTP/2, TLS, ALPN hoặc định tuyến chưa đúng | Kiểm thử transport thực và kiểm tra proxy |
| Gọi nhiều lần làm quá nhiều kết nối | Tạo ManagedChannel trong mỗi request | Chia sẻ Channel và quản lý shutdown |

Khi điều tra, nên tách vấn đề theo tầng: **contract** (package/method/message), **client** (stub/deadline/credentials), **transport** (HTTP/2/TLS), **server runtime** (registration/interceptor), rồi **implementation** (validation/business logic). Cách chia này giúp tìm đúng nguyên nhân thay vì chỉnh sửa ngẫu nhiên nhiều cấu hình.

## 13. Bài thực hành và câu hỏi tự kiểm tra

### Bài thực hành: mở rộng RPC GetOrder

1. Từ file .proto ở mục 2, sinh mã Java bằng **protoc** và **protoc-gen-grpc-java**. Xác định lớp request/response và method descriptor tương ứng **GetOrder**.
2. Khởi chạy **OrderQueryEndpoint** qua gRPC server. Gọi **getOrder("order-42")** và kiểm tra trạng thái đơn trong response; thử **order_id = ""** và **"order-404"**.
3. Thêm **optional string trace_label = 3;** vào **GetOrderRequest**. So sánh getter với **hasTraceLabel()** trong Java sinh mã, nêu sự khác nhau giữa không gửi và gửi chuỗi rỗng.
4. Thiết kế **SearchOrdersRequest/SearchOrdersResponse** với **page_size**, **page_token**, **repeated Order** và **next_page_token**; đặt giới hạn page_size để tránh response quá lớn.
5. Viết một client async gọi **WatchOrders**, nhận ba event, kết thúc observer đúng cách. Sau đó mô phỏng client hủy giữa chừng và kiểm tra server dừng công việc.
6. Viết test in-process cho GetOrder, sau đó thử với server thật có TLS/HTTP/2 để kiểm chứng phần transport và cấu hình bảo mật.
7. Mô tả thay đổi nào cần phương thức mới hoặc package v2 thay vì sửa trực tiếp schema đang phục vụ client cũ.

### Câu hỏi tự kiểm tra

**1. Tên package Java có quyết định HTTP/2 :path của RPC không?**  
Không. Đường dẫn dựa vào **protobuf package + service + method**, ví dụ **/shop.orders.v1.OrderQueryService/GetOrder**. **java_package** chỉ quyết định vị trí mã Java sinh ra.

**2. Vì sao request/response phải dùng message type thay vì string/int trực tiếp trong chữ ký rpc?**  
Hợp đồng gRPC khai báo **message** protobuf cho hai phía. Message mang schema có thể phát triển, field number và dữ liệu được mã hóa/giải mã thống nhất.

**3. Unary và server streaming khác nhau ở đâu?**  
Unary có một request và một response thành công; server streaming có một request và có thể gửi nhiều response message trong cùng một RPC.

**4. Khi dùng optional string note, hasNote() và getNote() trả lời hai câu hỏi khác nhau thế nào?**  
**hasNote()** cho biết trường có được gán không; **getNote()** lấy giá trị, có thể là chuỗi rỗng cả khi chưa gán hoặc đã gán rỗng.

**5. OrderStatus.PENDING có phải mã lỗi gRPC không?**  
Không. Đó là giá trị enum của dữ liệu nghiệp vụ. Lỗi gRPC được mô tả bằng **Status.Code** như **NOT_FOUND** hoặc **INVALID_ARGUMENT**.

**6. Khi thêm một field vào response, vì sao vẫn phải kiểm thử với client cũ?**  
Thêm field mới với tag mới thường tương thích về wire format, nhưng logic client cũ có thể không đáp ứng ý nghĩa nghiệp vụ hoặc trạng thái mới. Kiểm thử giúp phát hiện bất tương thích ngữ nghĩa.

**7. Client-streaming đã gọi onCompleted() trên request observer nghĩa là RPC hoàn tất chưa?**  
Chưa. Client mới kết thúc **chiều gửi**, còn phải chờ **onCompleted()** hoặc **onError()** của response observer để xác định kết quả cuối cùng.

## Tổng kết

**RPC method** là đơn vị thao tác từ xa, được nhận diện bởi **protobuf package, service và method name**. **Request/response message** là hợp đồng dữ liệu của thao tác: gồm field number, kiểu dữ liệu và ý nghĩa nghiệp vụ, được mã hóa bằng Protocol Buffers. Từ hai thành phần đó, gRPC Java sinh API client/server và runtime thực hiện việc truyền message qua HTTP/2. Khi xây dựng dịch vụ Spring gRPC, cần thiết kế đúng kiểu unary/streaming, validation và gRPC status, kiểm soát deadline/bảo mật, giữ tương thích schema và kiểm thử cả contract lẫn hành vi vận hành.
