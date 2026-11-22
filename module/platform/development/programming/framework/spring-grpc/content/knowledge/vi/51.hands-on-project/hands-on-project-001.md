# Định nghĩa proto cho service quản lý đơn hàng

Trong dự án Spring gRPC, hợp đồng Protocol Buffers cần mô tả rõ các thao tác mà client được phép thực hiện, dữ liệu được trao đổi và những quy tắc mà server phải bảo đảm. Bài thực hành này thiết kế contract cho một service quản lý đơn hàng: tạo đơn, đọc đơn, liệt kê đơn theo trang, cập nhật ghi chú, hủy đơn và theo dõi sự kiện của một đơn hàng.

Mục tiêu không chỉ là viết một file `.proto` có thể sinh Java. Contract cần giữ ổn định field number, biểu diễn đúng presence, tránh để client tự quyết định dữ liệu giá như server, hỗ trợ retry an toàn cho thao tác tạo đơn và xác định rõ semantics của streaming. Sau bài này, người học có thể dùng schema làm đầu vào để sinh gRPC stub và triển khai provider/client trong Spring.

## 1. Xác định phạm vi và use case

Service quản lý vòng đời đơn hàng với các use case:

| Use case | RPC | Kiểu RPC |
| --- | --- | --- |
| Tạo đơn hàng từ danh sách sản phẩm | CreateOrder | Unary |
| Lấy chi tiết một đơn | GetOrder | Unary |
| Liệt kê đơn của khách hàng | ListOrders | Unary có pagination |
| Sửa ghi chú của đơn | UpdateOrder | Unary |
| Hủy đơn khi còn đủ điều kiện | CancelOrder | Unary |
| Theo dõi thay đổi của một đơn | WatchOrderEvents | Server streaming |

Chọn unary cho thao tác có một request và một kết quả hữu hạn. ListOrders dùng page token để client điều khiển từng trang; không cần stream toàn bộ lịch sử vì pagination giúp giới hạn bộ nhớ và hỗ trợ tiếp tục truy vấn. WatchOrderEvents dùng server streaming vì một client có thể đăng ký theo dõi nhiều event trong một khoảng thời gian.

Một số quy tắc nghiệp vụ cần thống nhất trước khi viết proto:

- Đơn mới được server tạo ở trạng thái PENDING.
- Client gửi product ID và quantity; server tra cứu tên, giá và trạng thái sản phẩm tại thời điểm tạo đơn.
- Mọi item trong một đơn phải dùng cùng currency.
- Quantity phải lớn hơn 0; server kiểm tra tồn kho và quyền của customer.
- Đơn chỉ được hủy khi trạng thái hiện tại cho phép.
- Mỗi thay đổi đơn phát sinh event có sequence tăng đơn điệu trong phạm vi đơn hàng.
- CreateOrder nhận idempotency key để retry không tạo đơn trùng.

Các quy tắc này là behavior contract. Proto định nghĩa cấu trúc và RPC shape; server vẫn phải validate và thực thi các quy tắc.

## 2. Chọn package và Java options

Dùng package có version để tạo namespace ổn định:

- Protobuf package: `shop.order.v1`.
- Java package: `com.myshop.order.v1`.
- File: `src/main/proto/shop/order/v1/order_service.proto`.
- Service: `OrderService`.

`v1` là version của contract công khai, không phải version build của ứng dụng. Khi có thay đổi breaking không thể giữ tương thích, có thể tạo package/service version mới như `shop.order.v2` và duy trì v1 trong giai đoạn chuyển đổi.

Các message dùng `google.protobuf.Timestamp` cho thời điểm và `google.protobuf.FieldMask` cho cập nhật một phần. Đây là well-known types đi cùng Protocol Buffers.

## 3. Định nghĩa file order_service.proto

Tạo file `src/main/proto/shop/order/v1/order_service.proto` với nội dung:

```proto
syntax = "proto3";

package shop.order.v1;

option java_multiple_files = true;
option java_package = "com.myshop.order.v1";
option java_outer_classname = "OrderServiceProto";

import "google/protobuf/field_mask.proto";
import "google/protobuf/timestamp.proto";

service OrderService {
  // Creates an order. The idempotency key makes retries safe.
  rpc CreateOrder(CreateOrderRequest) returns (Order);

  // Returns one order visible to the authenticated caller.
  rpc GetOrder(GetOrderRequest) returns (Order);

  // Lists orders using an opaque page token.
  rpc ListOrders(ListOrdersRequest) returns (ListOrdersResponse);

  // Updates only the fields named in update_mask.
  rpc UpdateOrder(UpdateOrderRequest) returns (Order);

  // Cancels an order if its current state allows cancellation.
  rpc CancelOrder(CancelOrderRequest) returns (Order);

  // Streams events whose sequence is greater than after_sequence.
  rpc WatchOrderEvents(WatchOrderEventsRequest)
      returns (stream OrderEvent);
}

enum OrderStatus {
  ORDER_STATUS_UNSPECIFIED = 0;
  ORDER_STATUS_PENDING = 1;
  ORDER_STATUS_CONFIRMED = 2;
  ORDER_STATUS_SHIPPED = 3;
  ORDER_STATUS_DELIVERED = 4;
  ORDER_STATUS_CANCELLED = 5;
}

enum OrderEventType {
  ORDER_EVENT_TYPE_UNSPECIFIED = 0;
  ORDER_EVENT_TYPE_CREATED = 1;
  ORDER_EVENT_TYPE_UPDATED = 2;
  ORDER_EVENT_TYPE_CANCELLED = 3;
}

message OrderItemInput {
  string product_id = 1;
  int32 quantity = 2;
}

message OrderItem {
  string product_id = 1;
  string product_name = 2;
  int32 quantity = 3;
  int64 unit_price_minor = 4;
  string currency_code = 5;
}

message Order {
  string order_id = 1;
  string customer_id = 2;
  repeated OrderItem items = 3;
  OrderStatus status = 4;
  int64 total_amount_minor = 5;
  string currency_code = 6;
  google.protobuf.Timestamp created_at = 7;
  google.protobuf.Timestamp updated_at = 8;
  optional string note = 9;
  int64 version = 10;
}

message CreateOrderRequest {
  string customer_id = 1;
  repeated OrderItemInput items = 2;
  optional string note = 3;
  string idempotency_key = 4;
}

message GetOrderRequest {
  string order_id = 1;
}

message ListOrdersRequest {
  string customer_id = 1;
  optional OrderStatus status = 2;
  int32 page_size = 3;
  string page_token = 4;
}

message ListOrdersResponse {
  repeated Order orders = 1;
  string next_page_token = 2;
}

message OrderPatch {
  optional string note = 1;
}

message UpdateOrderRequest {
  string order_id = 1;
  OrderPatch patch = 2;
  google.protobuf.FieldMask update_mask = 3;
  int64 expected_version = 4;
}

message CancelOrderRequest {
  string order_id = 1;
  string reason = 2;
  int64 expected_version = 3;
}

message WatchOrderEventsRequest {
  string order_id = 1;
  int64 after_sequence = 2;
}

message OrderEvent {
  string event_id = 1;
  string order_id = 2;
  int64 sequence = 3;
  OrderEventType event_type = 4;
  google.protobuf.Timestamp occurred_at = 5;

  oneof detail {
    Order order_snapshot = 6;
    string cancellation_reason = 7;
  }
}
```

Đây là một contract v1 có chủ đích giới hạn. Nó cung cấp thao tác cốt lõi để thực hành generated Java API, unary call, pagination và server streaming. Các chức năng như thanh toán, hoàn tiền, phân quyền quản trị hoặc tìm kiếm nhiều tiêu chí có thể được thêm sau khi có use case rõ ràng.

## 4. Thiết kế request và response theo nguyên tắc sở hữu dữ liệu

CreateOrderRequest chỉ nhận product ID và quantity. Client không được tự gửi product name hoặc unit price để server ghi thẳng vào đơn, vì giá và tên phải được xác định từ catalog đáng tin cậy tại thời điểm tạo đơn. Server lưu snapshot giá vào OrderItem để lịch sử đơn không đổi khi giá catalog cập nhật.

Order dùng integer `unit_price_minor` và `total_amount_minor`, tránh sai số nhị phân của float/double khi tính tiền. `currency_code` xác định đơn vị tiền tệ; contract của service cần quy định cách quy đổi major/minor unit theo currency và bảo đảm tất cả item trong một đơn cùng currency. Không cộng các amount thuộc currency khác nhau.

`Order.version` là version tăng sau mỗi lần cập nhật. UpdateOrderRequest và CancelOrderRequest gửi `expected_version`; server từ chối ghi nếu version hiện tại đã thay đổi. Cách này giúp phát hiện lost update khi nhiều client cùng thao tác một đơn.

`created_at`, `updated_at` và `occurred_at` dùng Timestamp UTC thay vì chuỗi ngày giờ tự định dạng. Client nên chuyển thành kiểu thời gian phù hợp ở ngôn ngữ của mình và không giả định múi giờ local của server.

## 5. Quyết định presence và validation

Proto3 scalar thông thường có implicit presence: nếu client không gửi string, getter trả chuỗi rỗng; nếu không gửi int32, getter trả 0. Với field cần phân biệt absent và explicit default, khai báo `optional`.

Trong schema này:

- `Order.note` là optional để client phân biệt đơn không có ghi chú với ghi chú hiện diện.
- `CreateOrderRequest.note` là optional để biết caller có gửi ghi chú hay không.
- `ListOrdersRequest.status` là optional để phân biệt không lọc trạng thái với lọc theo giá trị enum.
- `OrderPatch.note` là optional để hỗ trợ set/clear thông qua update mask.

Proto không có từ khóa required trong proto3. Server cần validate:
- customer_id và idempotency_key không được rỗng.
- items phải có ít nhất một phần tử và không vượt giới hạn số item.
- product_id không rỗng, quantity lớn hơn 0.
- page_size nằm trong giới hạn; ví dụ 1–100. Nếu bằng 0, server có thể áp dụng default đã công bố.
- order_id phải đúng định dạng và caller có quyền truy cập đơn.
- expected_version phải khớp version hiện tại.

Request sai nên kết thúc với INVALID_ARGUMENT. Không tìm thấy đơn trả NOT_FOUND; caller không có quyền xem đơn trả PERMISSION_DENIED. Không đủ điều kiện hủy trả FAILED_PRECONDITION; expected_version xung đột có thể trả ABORTED. Các status này là behavior contract và cần được kiểm thử riêng.

## 6. Quy định semantics cho từng RPC

**CreateOrder**

Server xác thực customer, kiểm tra từng sản phẩm, tồn kho, currency và quantity, sau đó tính tổng tiền từ catalog. `idempotency_key` phải được lưu cùng kết quả tạo đơn trong phạm vi customer/caller. Nếu cùng key và cùng payload được gửi lại, trả lại đơn đã tạo; nếu cùng key nhưng payload khác, trả lỗi theo policy đã công bố, thường là INVALID_ARGUMENT hoặc ALREADY_EXISTS.

**GetOrder**

Server kiểm tra order ID và quyền truy cập. Không tiết lộ sự tồn tại của đơn thuộc customer khác nếu chính sách bảo mật yêu cầu che giấu tài nguyên; khi đó có thể trả NOT_FOUND thay vì PERMISSION_DENIED theo policy thống nhất.

**ListOrders**

`page_size` có default và maximum rõ ràng. `page_token` là token opaque do server phát hành, không phải offset mà client tự tăng. Token nên gắn với filter/customer và thứ tự sắp xếp để client không đổi query giữa các trang. `next_page_token` rỗng báo hết trang.

**UpdateOrder**

`update_mask` xác định field được cập nhật. Trong v1, chỉ hỗ trợ path `note`. Nếu mask không có note, giữ nguyên ghi chú. Nếu mask có note và `patch.hasNote()` là true, đặt giá trị mới; nếu mask có note nhưng field không hiện diện, xóa ghi chú. Server từ chối path ngoài danh sách cho phép. `expected_version` bảo vệ cập nhật đồng thời.

**CancelOrder**

Server kiểm tra state transition. Ví dụ đơn PENDING hoặc CONFIRMED có thể được hủy theo policy; SHIPPED hoặc DELIVERED không thể hủy trực tiếp. Hủy thành công cập nhật status, version và phát OrderEvent. Gọi hủy lặp lại cần có semantics rõ: có thể trả đơn đã ở CANCELLED nếu reason/operation idempotent, hoặc trả FAILED_PRECONDITION nếu contract yêu cầu.

**WatchOrderEvents**

Server chỉ phát event có sequence lớn hơn `after_sequence`, theo thứ tự tăng dần. Mỗi event có `event_id` để consumer deduplicate khi reconnect. Nếu cursor quá cũ và event đã hết retention, server có thể trả OUT_OF_RANGE kèm hướng dẫn client tải snapshot bằng GetOrder rồi đăng ký stream mới. Client hủy stream phải khiến server dừng subscription và giải phóng tài nguyên.

## 7. Quy tắc tiến hóa schema

Field number là định danh trên wire và không được tái sử dụng. Khi xóa field, reserve cả number và name. Không đổi type/cardinality hoặc chuyển field vào/ra oneof mà không đánh giá compatibility.

Một số nguyên tắc cho v1:
- Thêm field mới với number mới theo hướng additive.
- Giữ các enum number đã phát hành; thêm enum value mới với số chưa dùng.
- Duy trì enum zero value có hậu tố UNSPECIFIED.
- Client phải xử lý enum value chưa biết.
- Không đổi package, service hoặc method path đã công bố.
- Không đổi unary thành streaming tại cùng method.
- Nếu cần thay đổi breaking, phát hành v2 và duy trì v1 trong support window.

Ví dụ nếu sau này loại bỏ `note` cũ có field number 9 trong Order, không dùng lại số 9:

```proto
message Order {
  string order_id = 1;
  reserved 9;
  reserved "note";
  // Các field còn lại giữ nguyên số đã phát hành.
}
```

## 8. Sinh Java code và kiểm tra contract

Với protoc và plugin gRPC Java đã được cài trong môi trường build, có thể sinh message classes và gRPC stubs từ file proto. Ví dụ lệnh minh họa:

```bash
protoc \
  -I src/main/proto \
  --java_out=build/generated/source/proto/main/java \
  --plugin=protoc-gen-grpc-java=/path/to/protoc-gen-grpc-java \
  --grpc-java_out=build/generated/source/proto/main/grpc \
  src/main/proto/shop/order/v1/order_service.proto
```

Đường dẫn plugin và output directory phụ thuộc môi trường. Build plugin của dự án có thể tự cấu hình protoc và gRPC Java generator; điều quan trọng là cả hai generator dùng cùng proto source và dependency version.

Các lớp chính được sinh ra gồm:
- Message classes như CreateOrderRequest, Order, OrderItem và OrderEvent.
- `OrderServiceGrpc` với blocking, async và future stub tùy generator/dependency.
- `OrderServiceImplBase` làm base class cho provider implementation.
- Descriptor để kiểm tra package, service, method, request/response type và RPC cardinality.

Một descriptor test đơn giản:

```java
@Test
void orderServiceExposesExpectedRpcMethods() {
    io.grpc.ServiceDescriptor descriptor =
            OrderServiceGrpc.getServiceDescriptor();

    Set<String> methods = descriptor.getMethods().stream()
            .map(io.grpc.MethodDescriptor::getFullMethodName)
            .collect(Collectors.toSet());

    assertTrue(methods.contains(
            "shop.order.v1.OrderService/CreateOrder"));
    assertTrue(methods.contains(
            "shop.order.v1.OrderService/WatchOrderEvents"));
}
```

Test này xác nhận generated gRPC descriptor có method path mong đợi. Nó chưa chứng minh provider đã đăng ký hoặc triển khai handler; provider integration test sẽ kiểm tra điều đó ở bước triển khai service.

## 9. Dùng generated stub từ client

Ví dụ tạo request và gọi CreateOrder bằng blocking stub:

```java
CreateOrderRequest request = CreateOrderRequest.newBuilder()
        .setCustomerId("customer-42")
        .addItems(OrderItemInput.newBuilder()
                .setProductId("keyboard-01")
                .setQuantity(2))
        .setIdempotencyKey("checkout-2026-000184")
        .build();

Order order = orderStub
        .withDeadlineAfter(2, TimeUnit.SECONDS)
        .createOrder(request);

assertEquals(OrderStatus.ORDER_STATUS_PENDING, order.getStatus());
assertEquals("customer-42", order.getCustomerId());
```

Trong ứng dụng Spring, channel và stub nên được quản lý theo lifecycle phù hợp; deadline được đặt theo từng call. Không tạo channel mới cho mỗi request. Authentication credential và correlation metadata được gắn ở client credentials/interceptor, không nhúng token vào protobuf request.

Với WatchOrderEvents, dùng async stub và StreamObserver để nhận event liên tục. Client cần xử lý onError/onCompleted, giữ sequence cursor cuối cùng và reconnect có kiểm soát. Khi reconnect, gửi after_sequence để tiếp tục từ event tiếp theo; event_id hỗ trợ deduplicate nếu server phát lại event ở ranh giới reconnect.

## 10. Checklist hoàn thành dự án

- [ ] File proto nằm đúng package path và có version v1.
- [ ] java_package, java_multiple_files và outer class được đặt rõ.
- [ ] RPC unary/streaming phù hợp use case.
- [ ] Request chỉ chứa input do client được phép cung cấp.
- [ ] Server sở hữu việc tra cứu giá, tính tổng và chuyển trạng thái.
- [ ] Field number duy nhất, enum có zero UNSPECIFIED và không tái sử dụng số.
- [ ] Optional/presence được dùng ở field cần phân biệt absent/default.
- [ ] Pagination dùng opaque page token.
- [ ] CreateOrder có idempotency key và semantics retry.
- [ ] UpdateOrder dùng FieldMask và expected_version.
- [ ] WatchOrderEvents có sequence, cursor và cancellation behavior.
- [ ] Status code cho validation, not-found, permission, conflict và precondition được định nghĩa.
- [ ] Java message/stub được sinh từ đúng proto source.
- [ ] Descriptor test xác nhận full method path và RPC shape.
- [ ] Có kế hoạch compatibility/versioning cho các lần mở rộng sau này.

**Tự kiểm tra**

**Câu 1.** Vì sao CreateOrderRequest không nên nhận unit price từ client?

*Đáp án:* Giá phải do server tra cứu từ catalog đáng tin cậy tại thời điểm tạo đơn. Nếu tin giá client gửi, caller có thể sửa giá và làm sai dữ liệu tài chính.

**Câu 2.** Vì sao cần idempotency_key cho CreateOrder?

*Đáp án:* Khi response bị mất hoặc client retry sau deadline, cùng một ý định tạo đơn có thể được gửi nhiều lần. Idempotency key giúp server trả lại kết quả đã tạo thay vì tạo đơn trùng.

**Câu 3.** Vì sao ListOrders dùng page_token thay vì offset?

*Đáp án:* Token opaque cho phép server giữ cursor/sort/filter ổn định và thay đổi cách phân trang mà không phụ thuộc offset nội bộ. Client chỉ gửi lại token server đã cấp.

**Câu 4.** update_mask và optional note phối hợp như thế nào?

*Đáp án:* update_mask xác định field được phép cập nhật. Khi mask chứa note, presence của patch.note phân biệt set giá trị mới với yêu cầu xóa ghi chú theo semantics đã công bố.

**Câu 5.** Vì sao WatchOrderEvents cần after_sequence và event_id?

*Đáp án:* after_sequence giúp client tiếp tục từ vị trí đã nhận sau reconnect; event_id hỗ trợ deduplicate khi event bị phát lại ở ranh giới kết nối.

Định nghĩa proto tốt làm rõ quyền sở hữu dữ liệu, trạng thái nghiệp vụ, retry, pagination và vòng đời stream ngay tại ranh giới client/server. Với OrderService v1, các RPC có tên và shape ổn định, field có number rõ ràng, optional/presence đúng nhu cầu và event stream có cursor để reconnect. Đây là nền tảng để sinh Java stub và triển khai service quản lý đơn hàng trong Spring gRPC.
