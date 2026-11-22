# Versioned service và versioned message

## 1. Vì sao cần version hóa service và message?

Trong **SPRING_GRPC**, Protobuf schema định nghĩa request, response và service mà client/server dùng để giao tiếp. Có thay đổi chỉ cần thêm field hoặc RPC mà vẫn giữ được hợp đồng hiện tại. Nhưng khi thay đổi làm client cũ hiểu sai dữ liệu, không còn gọi được method hoặc không thể biểu diễn yêu cầu mới, cần một ranh giới version rõ ràng.

**Versioned service** và **versioned message** giúp nhiều thế hệ API cùng tồn tại trong thời gian chuyển đổi. Client cũ tiếp tục gọi contract v1; client mới dùng contract v2; server có thể đăng ký cả hai và chuyển dữ liệu về cùng application/domain service.

Version hóa ảnh hưởng đến Protobuf package và fully-qualified message names, full gRPC method name, generated Java classes/stubs, type URL của Any, reflection, schema registry, JSON/gateway mapping, health checking, authorization, metrics, tracing và kế hoạch rollout.

Bài tập trung vào cách thiết kế package/service/message v1 và v2, chọn thời điểm tạo version mới, giữ hai phiên bản cùng tồn tại và kiểm thử tương thích khi client/server nâng cấp lệch thời điểm.

## 2. Phân biệt service version và message version

Một API gRPC thường gồm service, RPC method và các message request/response. Các thành phần này có liên hệ nhưng có định danh riêng:

| Thành phần | Ví dụ | Vai trò |
| --- | --- | --- |
| Protobuf package | `commerce.orders.v1` | Namespace của service, message và enum |
| Service | `OrderService` | Nhóm RPC được server đăng ký |
| RPC method | `CreateOrder` | Operation mà client gọi |
| Request/response message | `CreateOrderRequest`, `OrderReply` | Cấu trúc dữ liệu truyền vào/ra |
| Java package | `com.acme.orders.v1` | Namespace của code Java sinh ra |

Trong thiết kế phổ biến, package mang version như `commerce.orders.v1` chứa service và các message của API v1. Khi có breaking change, tạo package `commerce.orders.v2` với service và message tương ứng.

Full method name của một RPC được tạo từ protobuf package, service name và method name:

```text
/commerce.orders.v1.OrderService/CreateOrder
```

Nếu package chuyển sang `commerce.orders.v2`, RPC path cũng đổi:

```text
/commerce.orders.v2.OrderService/CreateOrder
```

Client v1 không tự gọi được method path v2 chỉ vì tên service và method vẫn giống nhau. Server phải đăng ký đúng service descriptor mà client yêu cầu.

## 3. Thiết kế package v1 và v2

Ví dụ API v1:

```proto
syntax = "proto3";

package commerce.orders.v1;

option java_multiple_files = true;
option java_package = "com.acme.orders.v1";

service OrderService {
  rpc CreateOrder(CreateOrderRequest) returns (OrderReply);
  rpc GetOrder(GetOrderRequest) returns (OrderReply);
}

message CreateOrderRequest {
  string customer_id = 1;
  repeated OrderLine lines = 2;
}

message GetOrderRequest {
  string order_id = 1;
}

message OrderLine {
  string product_id = 1;
  int32 quantity = 2;
}

message OrderReply {
  string order_id = 1;
  OrderState state = 2;
  int64 total_cents = 3;
}

enum OrderState {
  ORDER_STATE_UNSPECIFIED = 0;
  ORDER_STATE_PENDING = 1;
  ORDER_STATE_CONFIRMED = 2;
  ORDER_STATE_REJECTED = 3;
}
```

Khi v2 cần idempotency key, biểu diễn tiền bằng message có currency và thay đổi cấu trúc line item, có thể tạo contract mới:

```proto
syntax = "proto3";

package commerce.orders.v2;

option java_multiple_files = true;
option java_package = "com.acme.orders.v2";

import "google/protobuf/timestamp.proto";

service OrderService {
  rpc CreateOrder(CreateOrderRequest) returns (OrderReply);
  rpc GetOrder(GetOrderRequest) returns (OrderReply);
}

message CreateOrderRequest {
  string customer_id = 1;
  repeated LineItem items = 2;
  string idempotency_key = 3;
}

message GetOrderRequest {
  string order_id = 1;
}

message LineItem {
  string product_id = 1;
  int32 quantity = 2;
  string fulfillment_group = 3;
}

message Money {
  int64 units_minor = 1;
  string currency_code = 2;
}

message OrderReply {
  string order_id = 1;
  OrderStatus status = 2;
  Money total = 3;
  google.protobuf.Timestamp created_at = 4;
}

enum OrderStatus {
  ORDER_STATUS_UNSPECIFIED = 0;
  ORDER_STATUS_PENDING = 1;
  ORDER_STATUS_CONFIRMED = 2;
  ORDER_STATUS_REJECTED = 3;
  ORDER_STATUS_CANCELLED = 4;
}
```

Ở đây protobuf package, Java package và service/message names được version hóa nhất quán. Hai generated API có thể cùng tên class đơn giản như `OrderReply`, nhưng fully-qualified Protobuf type và Java class package khác nhau.

Không cần tạo v2 chỉ vì có một lần deploy mới. Nếu thay đổi chỉ bổ sung field với number chưa dùng và có default/fallback an toàn, thường có thể mở rộng contract v1. Tạo version mới khi thay đổi phá compatibility hoặc cần semantics/API surface khác mà không thể chuyển tiếp an toàn trong v1.

## 4. Khi nào cần version mới?

Nên đánh giá cả wire, source, JSON và behavioral compatibility:

| Thay đổi | Thường có thể giữ v1? | Ghi chú |
| --- | --- | --- |
| Thêm field mới với number chưa dùng | Có, nếu default và semantics an toàn | Client cũ bỏ qua field; server cũ không hiểu field mới trong request |
| Thêm RPC method mới | Thường có | Server cần triển khai method trước khi client mới gọi |
| Thêm enum value | Có thể giữ wire compatibility | Client cũ phải xử lý unknown value; không giả định hiểu semantics |
| Xóa field đang được dùng | Không nên làm trực tiếp | Cần deprecate, migrate và reserve number/name |
| Đổi field type/semantics | Thường cần v2 hoặc field mới | Cùng wire type vẫn có thể diễn giải sai |
| Đổi package/service/method identity | Tạo RPC/type identity mới | Client cũ gọi path cũ |
| Thay cấu trúc request/response không tương thích | Nên tạo v2 | Giữ v1 cho consumer cũ trong thời gian chuyển tiếp |

Version không nên tăng cho mọi thay đổi nhỏ. Nếu package đổi mỗi lần thêm field tương thích, số API surface và chi phí vận hành sẽ tăng nhanh. Hãy dùng v1 cho các mở rộng tương thích theo chính sách; tạo v2 cho thay đổi có chủ đích làm thay đổi contract.

Một enum value mới có thể wire-compatible nhưng behavioral breaking với client dùng switch không có fallback. Một field mới có thể parse được nhưng làm sai nghiệp vụ nếu server cũ bỏ qua field mà client mới coi là bắt buộc. Quyết định version phải xét consumer thực tế, không chỉ kết quả compile.

## 5. Protobuf package khác Java package

`package` trong tệp proto quyết định Protobuf fully-qualified names và tham gia tạo RPC full method name. `option java_package` chỉ điều khiển package Java của generated classes.

Ví dụ:

```proto
package commerce.orders.v2;

option java_package = "com.acme.generated.orders";
```

Nếu chỉ đổi `java_package`, binary message field tags và gRPC method path vẫn giữ nguyên, miễn là protobuf package, service và RPC names không đổi. Tuy nhiên, Java source consumers có thể không compile vì generated classes đã chuyển package.

Nếu đổi protobuf package từ v1 sang v2 mà giữ nguyên `java_package`, RPC path và message fully-qualified names vẫn đổi, dù Java package không đổi. Hai phiên bản generated class cũng có thể đụng tên trong cùng package nếu message names giống nhau; nên đặt Java package riêng cho từng version để dễ dùng đồng thời.

Không dùng `java_package` để version hóa gRPC endpoint. Client gọi RPC theo descriptor của Protobuf service, không theo tên package Java.

## 6. Versioned message và type identity

Một message có fully-qualified name như `commerce.orders.v1.OrderReply`. Khi tạo v2, type mới có tên `commerce.orders.v2.OrderReply`.

Binary payload của message thông thường chủ yếu chứa field tags và values; tên fully-qualified message không được lặp lại trong mỗi payload. Nếu v1 và v2 có cấu trúc field tương tự, bytes có thể parse theo cả hai descriptor trong một số trường hợp. Tuy nhiên, điều đó **không biến hai message thành cùng một type contract**.

Type identity được dùng bởi descriptor/reflection và dynamic message APIs; `google.protobuf.Any`, trong đó type URL chứa tên message; Protobuf JSON của Any; schema registry; event store; data catalog; validation tooling; và Java generated classes.

Ví dụ, một Any chứa type URL `type.googleapis.com/commerce.orders.v1.OrderReply` không tự đổi thành `commerce.orders.v2.OrderReply`. Consumer v2 cần resolve type v1 hoặc có bước chuyển đổi rõ ràng.

Nếu dữ liệu lưu trữ dùng Any, descriptor hoặc type URL, cần giữ schema v1 và khả năng resolve type cũ trong suốt thời gian dữ liệu còn tồn tại. Không xóa v1 chỉ vì RPC v1 đã ngừng nhận traffic.

## 7. Có nên để service v2 dùng message v1?

Về kỹ thuật, service trong package v2 có thể import và sử dụng message thuộc package v1:

```proto
syntax = "proto3";

package commerce.orders.v2;

import "commerce/orders/v1/order_messages.proto";

service OrderService {
  rpc GetOrder(commerce.orders.v1.GetOrderRequest)
      returns (commerce.orders.v1.OrderReply);
}
```

Cách này có thể phù hợp nếu message thực sự là contract ổn định, không thay đổi giữa hai service version. Nhưng nó tạo phụ thuộc rõ ràng: API v2 tiếp tục mang type identity v1. Consumer và tooling phải biết điều đó.

Không nên tái sử dụng message v1 chỉ để tránh viết message mới khi semantics đã khác. Điều đó khiến v2 bị khóa vào giới hạn của v1 và có thể làm người dùng hiểu nhầm rằng request/response đã được nâng cấp.

Có ba lựa chọn:

1. **Tái sử dụng message v1:** chỉ khi cấu trúc và semantics không đổi, và việc phụ thuộc type v1 là chủ đích.
2. **Tạo message v2:** khi field, presence, validation hoặc semantics đã thay đổi; mapping giữa hai phiên bản nằm ở adapter.
3. **Tạo package dùng chung không gắn version:** chỉ cho kiểu thực sự ổn định, có vòng đời độc lập và được quản lý như contract riêng. Tránh gom mọi message vào một package common chỉ để giảm trùng lặp.

Ưu tiên hợp đồng rõ ràng và vòng đời độc lập hơn việc loại bỏ mọi dòng khai báo lặp.

## 8. Server có thể phục vụ v1 và v2 cùng lúc

Trong giai đoạn migration, một server có thể đăng ký hai service implementation được sinh từ hai package khác nhau:

```java
Server server = ServerBuilder.forPort(port)
    .addService(new OrderServiceV1Adapter(orderApplicationService))
    .addService(new OrderServiceV2Adapter(orderApplicationService))
    .build();
```

Tên class adapter là minh họa. Mỗi adapter triển khai service base class được sinh từ contract tương ứng.

Hai adapter nên gọi cùng application/domain service thay vì nhân đôi nghiệp vụ. Adapter chịu trách nhiệm chuyển request v1 hoặc v2 thành command/domain input; kiểm tra validation và quy tắc riêng của contract; chuyển domain result thành response đúng version; ánh xạ lỗi domain thành gRPC status phù hợp; và giữ semantics riêng của từng version nếu chúng có khác biệt.

Ví dụ, v1 có `total_cents` còn v2 có `Money`; cả hai adapter có thể nhận cùng domain amount và chuyển thành kiểu response tương ứng. Nếu currency không có trong domain v1, không tự suy đoán currency khi tạo response v2; cần nguồn dữ liệu hoặc quy tắc nghiệp vụ rõ ràng.

## 9. Mapping giữa message version và domain model

Không nên dùng generated Protobuf message làm domain model trung tâm nếu nhiều version API có semantics khác nhau. Một application service có thể nhận command nội bộ và trả domain result:

```java
public interface OrderApplicationService {
    OrderResult createOrder(CreateOrderCommand command);
    OrderResult getOrder(String orderId);
}
```

Adapter v1 chuyển request cũ sang command:

```java
CreateOrderCommand command = new CreateOrderCommand(
    request.getCustomerId(),
    mapV1Lines(request.getLines()),
    null
);

OrderResult result = applicationService.createOrder(command);
```

Adapter v2 chuyển request mới:

```java
CreateOrderCommand command = new CreateOrderCommand(
    request.getCustomerId(),
    mapV2Items(request.getItems()),
    request.getIdempotencyKey()
);

OrderResult result = applicationService.createOrder(command);
```

Đây là minh họa mapping; kiểu command/result thực tế phụ thuộc domain model. Cần quyết định rõ cách xử lý trường v2 như idempotency key khi request v1 không có trường đó. Có thể dùng default policy, sinh key nội bộ theo quy tắc được công bố, hoặc không hỗ trợ tính năng đó qua v1. Không tạo giá trị giả có thể làm thay đổi tính đúng đắn.

Tách adapter giúp một version có thể deprecate mà không buộc domain service đổi theo. Đồng thời, test adapter độc lập giúp bảo vệ mapping giữa contract và nghiệp vụ.

## 10. Rollout v1/v2 an toàn

Một trình tự phổ biến là triển khai khả năng đọc/nhận trước, rồi mới chuyển consumer:

1. **Kiểm kê v1:** xác định client, server, batch job, gateway, event consumer và dữ liệu đã lưu đang dùng package/type v1.
2. **Đóng băng contract v1:** chỉ nhận thay đổi tương thích theo chính sách; không tái sử dụng field/enum numbers.
3. **Thiết kế v2:** tạo package/service/messages mới, ghi rõ khác biệt và mapping.
4. **Triển khai server dual registration:** server mới phục vụ cả v1 và v2.
5. **Cập nhật hạ tầng:** health checking, authorization, interceptor, routing, service config, reflection, metrics và tracing nhận diện cả hai version.
6. **Kiểm thử cả hai API:** old client gọi v1; new client gọi v2; xác minh semantics và lỗi.
7. **Phát hành client v2 theo nhóm:** chuyển dần consumer, theo dõi lỗi và khả năng rollback.
8. **Đo traffic v1:** dùng metrics theo full method name, xác định consumer còn gọi v1.
9. **Deprecate v1:** thông báo thời hạn, owner và điều kiện ngừng hỗ trợ.
10. **Gỡ v1 có điều kiện:** chỉ khi không còn traffic, stored-data dependency hoặc consumer được cam kết hỗ trợ.

Nếu client v2 cần gửi request có semantics mới, server phải hỗ trợ v2 trước khi client gửi. Với rolling deployment, mọi replica có thể nhận traffic phải đăng ký service v2 trước khi bật client v2.

## 11. Những tích hợp phải cập nhật khi thêm version

Thêm service v2 không chỉ là thêm generated class. Kiểm tra mọi thành phần sử dụng service name, method path hoặc message FQN:

| Thành phần | Điều cần cập nhật |
| --- | --- |
| Server registration | Đăng ký v1 và v2 trong thời gian chuyển tiếp |
| gRPC health checking | Đăng ký health status theo từng service name cần hỗ trợ |
| Authorization/interceptor | Cho phép full method name v1/v2 theo policy |
| Service config/retry | Kiểm tra method config có match path mới |
| Reflection | Công bố service descriptors cần thiết |
| Gateway/transcoding | Thêm route và mapping v2 |
| Metrics/tracing | Theo dõi version riêng; cập nhật dashboard/alert |
| Any/type registry | Giữ resolver cho message FQN cũ và mới |
| Schema registry/CI | So sánh từng package/version với baseline đúng |
| Data store/event consumer | Đọc và migrate payload v1 khi cần |

Không gộp metric v1/v2 thành một nhãn duy nhất nếu cần biết consumer nào còn dùng API cũ. Tránh đưa mọi type URL hoặc giá trị tùy ý vào label có cardinality cao; chọn các nhãn version/service có giới hạn.

## 12. Kiểm thử versioned service và message

Một bộ test nên bao gồm:

| Test | Điều cần xác nhận |
| --- | --- |
| v1 client → server dual-register | Full method path v1 vẫn được phục vụ |
| v2 client → server dual-register | Full method path v2 hoạt động |
| v1 message fixture → v1 parser | Dữ liệu cũ đọc đúng |
| v1 payload → adapter/domain | Mapping cũ không mất semantics |
| v2 request → adapter/domain | Field mới được validate và xử lý đúng |
| v2 response → v2 client | Type identity và mapping đúng |
| Any v1/v2 | Type URL cũ/mới được resolve theo kế hoạch |
| Health/auth/reflection | Từng service version được công bố và bảo vệ đúng |
| Rollback | Client quay về v1 khi v2 có sự cố vẫn gọi được service v1 |

Ví dụ kiểm tra full method name:

```java
assertEquals(
    "commerce.orders.v1.OrderService/CreateOrder",
    OrderServiceGrpc.getCreateOrderMethod().getFullMethodName()
);

assertEquals(
    "commerce.orders.v2.OrderService/CreateOrder",
    com.acme.orders.v2.OrderServiceGrpc
        .getCreateOrderMethod()
        .getFullMethodName()
);
```

Tên Java class được sinh ra phụ thuộc `java_package`; ví dụ trên giả định hai version có Java package riêng. Ngoài descriptor test, cần integration test qua server thật để xác nhận cả hai service đã được đăng ký và có thể xử lý request.

CI nên chạy lint và breaking check riêng với baseline của từng version. Thêm v2 không phải lý do để xóa baseline v1 hoặc bỏ kiểm tra tương thích của v1 khi v1 vẫn được hỗ trợ.

## 13. Deprecation và ngừng hỗ trợ v1

Một version cũ chỉ nên bị gỡ khi có bằng chứng consumer đã chuyển. Quy trình deprecation cần xác định ngày bắt đầu deprecate và ngày dự kiến sunset; owner chịu trách nhiệm thông báo; metrics chứng minh traffic v1 đã về 0 hoặc phần còn lại đã được xử lý; batch job, integration ngoài tổ chức và client phát hành chậm đã được kiểm kê; dữ liệu lưu trữ, backup và event có message FQN/Any v1 còn cần đọc hay không; cùng kế hoạch rollback nếu phát hiện consumer bị bỏ sót.

Gỡ RPC v1 và xóa schema v1 khỏi repository là hai quyết định khác nhau. Server có thể ngừng nhận RPC v1 nhưng vẫn cần schema v1 để đọc event cũ hoặc giải mã Any. Chỉ xóa schema/tooling khi vòng đời dữ liệu và contract đã cho phép.

## 14. Checklist review

- Version mới được tạo vì có thay đổi contract thực sự cần ranh giới mới.
- Package v1/v2 có quy ước nhất quán và service full method name được xác định.
- Message v2 được tạo khi semantics/cấu trúc đã thay đổi; không tái sử dụng message v1 chỉ để tiết kiệm code.
- `java_package` được quản lý riêng với protobuf package.
- Field number và enum number trong từng message/version được quản lý ổn định; không tái sử dụng number đã xóa.
- Any, descriptor/reflection và JSON mapping được xem xét nếu có sử dụng.
- Server có thể dual-register v1/v2 trong giai đoạn chuyển tiếp.
- Adapter chuyển đổi mỗi version sang domain model với fallback và validation rõ ràng.
- Health, auth, retry, gateway, metrics và tracing đã cập nhật.
- Có integration tests cho old/new clients và rollback.
- CI breaking checks dùng baseline đúng cho từng version.
- Deprecation có owner, số liệu traffic và điều kiện sunset.

Với **SPRING_GRPC**, versioned service và versioned message tạo ranh giới rõ ràng cho các thay đổi API không thể chuyển tiếp an toàn trong contract cũ. Protobuf package quyết định type identity và tham gia tạo RPC path; Java package quyết định namespace generated code. Giữ v1 và v2 cùng tồn tại qua adapter, rollout server trước client, kiểm thử cả RPC path lẫn message mapping và chỉ ngừng v1 khi consumer/dữ liệu cũ đã được xử lý sẽ giúp hệ thống tiến hóa mà không làm gián đoạn các client đang hoạt động.
