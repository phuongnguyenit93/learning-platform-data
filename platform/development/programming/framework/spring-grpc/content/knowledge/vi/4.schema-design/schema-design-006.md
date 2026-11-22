# Chọn field bắt buộc theo khả năng tương thích trong Spring gRPC

Khi phát triển dịch vụ **Spring gRPC**, một yêu cầu nghiệp vụ thường có những dữ liệu “bắt buộc”: mã đơn hàng phải tồn tại, số lượng phải lớn hơn 0, phương thức giao hàng phải được chọn. Tuy nhiên, trong hợp đồng **Protocol Buffers**, khái niệm *bắt buộc theo nghiệp vụ* không đồng nghĩa với *field luôn phải có mặt trong dữ liệu protobuf*. Nhầm lẫn hai khái niệm có thể khiến client cũ ngừng hoạt động khi server triển khai một phiên bản mới.

Bài học thuộc chương **Schema design** của module **SPRING_GRPC**, tập trung vào cách chọn và kiểm tra field trong `.proto` để các client/server Java, unary RPC và streaming RPC có thể cùng phát triển. Những quyết định này ảnh hưởng đến sinh mã, validation, gRPC status, kiểm thử tích hợp, khả năng retry và độ tin cậy của API.

Sau bài này, bạn có thể:

- Phân biệt ba câu hỏi: field *có hiện diện không*, *có giá trị hợp lệ không* và *có bắt buộc cho một hành vi nghiệp vụ không*.
- Hiểu khác biệt giữa field scalar thường, `optional`, message, `oneof`, `repeated` và enum trong proto3.
- Thiết kế request có validation rõ ràng mà không buộc client cũ gửi field chưa từng được yêu cầu.
- Lập kế hoạch thêm một field mới an toàn qua nhiều phiên bản client/server.
- Viết Java handler Spring gRPC kiểm tra đúng điều kiện, trả lỗi phù hợp và xây dựng bộ kiểm thử tương thích.

## 1. “Bắt buộc” có ba tầng ý nghĩa

Ví dụ hệ thống bán hàng cung cấp `CreateOrder`. Client gửi mã khách hàng và các dòng sản phẩm; server chỉ tạo đơn nếu số lượng mỗi dòng hợp lệ. Có ba mức kiểm tra cần phân biệt:

| Câu hỏi | Ví dụ | Ai quyết định? |
| --- | --- | --- |
| **Field có xuất hiện trong message không?** | Client đã gửi `shipping_country` hay chưa? | Quy tắc *field presence* của protobuf và dữ liệu gửi đến |
| **Giá trị có hợp lệ không?** | `quantity > 0`, `customer_id` không rỗng | Validation của API/server |
| **Khi nào nghiệp vụ cần field đó?** | Địa chỉ giao hàng chỉ cần khi đơn có vận chuyển đến nhà | Hợp đồng và quy tắc nghiệp vụ |

Tầng thứ ba thường có điều kiện. Ví dụ một đơn nhận tại cửa hàng có thể không cần địa chỉ giao, trong khi đơn giao tận nơi cần địa chỉ được xác định. Việc bắt tất cả client gửi địa chỉ cho mọi phương thức nhận hàng sẽ làm API khó dùng và gây thay đổi không cần thiết.

Một schema tốt phải diễn đạt được những điều kiện đó trong tài liệu hợp đồng và trong logic server. **Chỉ khai báo field trong `.proto` chưa có nghĩa trường đó đã được validate.**

## 2. Proto3 xử lý giá trị mặc định và sự hiện diện như thế nào?

Trong cú pháp `proto3`, từ khóa `required` của proto2 **không được phép sử dụng**. Ta thường khai báo field bình thường rồi kiểm tra ràng buộc nghiệp vụ ở server. Nếu cần phân biệt “client không gửi” và “client gửi giá trị mặc định”, dùng khả năng biểu diễn sự hiện diện phù hợp.

| Loại field trong proto3 | Khi không được gửi | Kiểm tra presence trong Java sinh mã | Ghi chú thiết kế |
| --- | --- | --- | --- |
| `string customer_id = 1;` | Đọc thành `""` | Không có `hasCustomerId()` cho scalar thường | Nếu `""` bị cấm, `isBlank()` có thể đủ để validate |
| `int32 quantity = 2;` | Đọc thành `0` | Không có `hasQuantity()` cho scalar thường | Không biết client cố ý gửi `0` hay bỏ trống |
| `bool enabled = 3;` | Đọc thành `false` | Không có `hasEnabled()` cho scalar thường | Dễ nhầm “không đổi” với “đặt false” trong update |
| `optional bool enabled = 4;` | Không hiện diện, nhưng getter vẫn trả giá trị mặc định | `hasEnabled()` | Phân biệt thiếu field với `enabled = false` |
| `Product product = 5;` | Message không hiện diện | `hasProduct()` | Message field trong proto3 có presence |
| `oneof selector { ... }` | Không chọn nhánh nào | `getSelectorCase()`, `has...()` cho nhánh phù hợp | Biểu diễn tối đa một lựa chọn; không tự bắt buộc có lựa chọn |
| `repeated Item items = 6;` | Danh sách rỗng | `getItemsCount()` | Không phân biệt danh sách bị bỏ trống với danh sách rỗng theo dạng thông thường |
| `map<string, string> tags = 7;` | Map rỗng | `getTagsCount()` | Không có presence cho cả map như một giá trị scalar tùy chọn |

Một số ví dụ minh họa:

```proto
syntax = "proto3";

message PreferenceRequest {
  bool active = 1;
  optional bool email_notifications = 2;
}
```

```java
// Đã sinh mã Java từ PreferenceRequest.
PreferenceRequest request = PreferenceRequest.newBuilder().build();

boolean active = request.getActive();                    // false
boolean email = request.getEmailNotifications();         // false
boolean sentEmailField = request.hasEmailNotifications(); // false
```

Nếu một client tạo:

```java
PreferenceRequest request = PreferenceRequest.newBuilder()
        .setEmailNotifications(false)
        .build();

boolean sentEmailField = request.hasEmailNotifications(); // true
```

Hai request có thể cho cùng giá trị `getEmailNotifications() == false` nhưng **khác nhau về ý định**. Presence đặc biệt quan trọng khi cập nhật từng phần, vì “bỏ qua field” không phải lúc nào cũng tương đương “đặt field bằng giá trị mặc định”.

### Presence khác validation

`optional string customer_id = 1;` cho phép kiểm tra `hasCustomerId()`, nhưng **không bảo đảm** ID có giá trị hợp lệ: một client vẫn có thể gửi chuỗi rỗng. Ngược lại, `string customer_id = 1;` không có presence, nhưng kiểm tra `isBlank()` vẫn đủ để từ chối cả trường hợp bỏ trống lẫn truyền chuỗi rỗng nếu nghiệp vụ coi hai trường hợp như nhau.

Vì vậy, **không dùng `optional` cho mọi field chỉ để “trông có vẻ rõ ràng”**. Hãy dùng nó khi hệ thống thực sự cần biết field đã được gửi hay chưa.

## 3. Phản ví dụ: thêm field mới rồi lập tức bắt buộc

Giả sử phiên bản đầu của `CreateOrderRequest` đã được nhiều ứng dụng Java và mobile sử dụng:

```proto
message CreateOrderRequest {
  string customer_id = 1;
  repeated OrderLine lines = 2;
  FulfillmentMethod fulfillment_method = 3;
  string request_id = 4;
}
```

Sau đó nhóm server muốn bổ sung `shipping_country`. Họ triển khai:

```proto
message CreateOrderRequest {
  string customer_id = 1;
  repeated OrderLine lines = 2;
  FulfillmentMethod fulfillment_method = 3;
  string request_id = 4;
  string shipping_country = 5;  // Field mới.
}
```

Về protobuf binary, **thêm field số 5 thường là thay đổi tương thích ở mức định dạng**: client cũ không biết field này nên không gửi; server mới vẫn giải mã được các tag cũ. Vấn đề phát sinh khi server mới đưa ra quy tắc:

```java
if (request.getShippingCountry().isBlank()) {
    throw Status.INVALID_ARGUMENT
            .withDescription("shipping_country is required")
            .asRuntimeException();
}
```

Tất cả client cũ không gửi field số 5 sẽ bị từ chối, kể cả khi trước đó tạo đơn thành công. **Wire-compatible không đồng nghĩa behavior-compatible.** Không cần thay cấu trúc binary hay đổi đường dẫn RPC để phá vỡ ứng dụng; thay đổi validation cũng có thể đủ.

Nếu đơn đã có thể suy ra quốc gia từ hồ sơ giao hàng đáng tin cậy hoặc không cần quốc gia cho phương thức nhận tại cửa hàng, server có thể tiếp tục xử lý các request cũ bằng quy tắc tương thích. Nếu quốc gia **thật sự bắt buộc cho mọi request và không thể suy ra**, đây là thay đổi hành vi phá vỡ hợp đồng; nên cân nhắc một API/phiên bản mới thay vì âm thầm áp bắt buộc trên `v1`.

## 4. Thiết kế hoàn chỉnh: field bắt buộc theo nghiệp vụ, field mới tương thích

Ví dụ sau sử dụng hai RPC unary cho tạo đơn và cập nhật ghi chú. Hợp đồng được đặt tại `src/main/proto/order/v1/order.proto`:

```proto
syntax = "proto3";

package shop.order.v1;

option java_package = "com.myshop.grpc.order.v1";
option java_multiple_files = true;
option java_outer_classname = "OrderProto";

import "google/protobuf/timestamp.proto";

service OrderService {
  rpc CreateOrder(CreateOrderRequest) returns (CreateOrderResponse);
  rpc UpdateOrderNote(UpdateOrderNoteRequest) returns (UpdateOrderNoteResponse);
}

enum FulfillmentMethod {
  FULFILLMENT_METHOD_UNSPECIFIED = 0;
  FULFILLMENT_METHOD_STORE_PICKUP = 1;
  FULFILLMENT_METHOD_HOME_DELIVERY = 2;
}

message OrderLine {
  string product_id = 1;
  int32 quantity = 2;
}

message CreateOrderRequest {
  // Bắt buộc theo nghiệp vụ, server kiểm tra khác rỗng.
  string customer_id = 1;

  // Phải có ít nhất một dòng, mỗi quantity phải > 0.
  repeated OrderLine lines = 2;

  // UNSPECIFIED = 0 bị từ chối trong thao tác tạo đơn.
  FulfillmentMethod fulfillment_method = 3;

  // Đã nằm trong hợp đồng v1 ban đầu; server cam kết xử lý retry theo ID.
  string request_id = 4;

  // Bổ sung sau khi v1 đã có client. Chưa bắt buộc với client v1.
  // Nếu có, sử dụng mã quốc gia ISO 3166-1 alpha-2, ví dụ "VN".
  optional string shipping_country = 5;
}

message CreateOrderResponse {
  string order_id = 1;
  google.protobuf.Timestamp created_at = 2;
}

message UpdateOrderNoteRequest {
  string order_id = 1;

  // Không gửi => không có yêu cầu sửa ghi chú.
  // Gửi "" => yêu cầu xóa nội dung ghi chú.
  optional string note = 2;
}

message UpdateOrderNoteResponse {
  string order_id = 1;
  google.protobuf.Timestamp updated_at = 2;
}
```

Điểm cần lưu ý:

1. `customer_id`, `lines`, `fulfillment_method` và `request_id` có yêu cầu nghiệp vụ rõ ràng ngay từ khi công bố `v1`. Server phải validate; protobuf không tự bắt buộc client điền.
2. `FULFILLMENT_METHOD_UNSPECIFIED = 0` biểu diễn trường hợp client chưa chọn. Tên enum mang ý nghĩa kiểm tra; giá trị `0` là mặc định của enum proto3 và nên có một giá trị không mang hành động nghiệp vụ.
3. `shipping_country = 5` là field **thêm sau**: dùng số mới, giữ nguyên các số cũ, và không lập tức buộc client v1 gửi nó.
4. `optional string note` cho phép phân biệt “không thay đổi ghi chú” với “xóa ghi chú bằng chuỗi rỗng” trong RPC cập nhật.
5. `request_id` chỉ bảo vệ retry khi server có cơ chế chống thực thi trùng gắn với ID và payload. Một field mang tên `request_id` không tự bảo đảm idempotency.

### Quy tắc nghiệp vụ cho shipping_country

Hợp đồng cần nêu rõ cách áp dụng trường mới:

| Loại đơn | Client không gửi `shipping_country` | Client gửi `shipping_country` |
| --- | --- | --- |
| `STORE_PICKUP` | Hợp lệ nếu không cần thông tin quốc gia cho nhận tại cửa hàng | Có thể sử dụng hoặc bỏ qua theo chính sách API đã công bố |
| `HOME_DELIVERY` | Server tiếp tục dùng nguồn địa chỉ giao đã được hỗ trợ trong `v1`; nếu không có dữ liệu cần thiết, áp dụng quy tắc lỗi hiện hành | Validate mã quốc gia và áp dụng vào quyết định giao hàng nếu được hợp đồng cho phép |

Nếu dữ liệu quốc gia trong hồ sơ cũ không đáng tin cậy, **đừng bịa giá trị mặc định “VN” cho mọi khách hàng**. Cách thay đổi an toàn còn phụ thuộc vào việc `v1` từng xử lý giao hàng như thế nào. Khi không có cơ chế tương thích phù hợp, cần hợp đồng mới hoặc luồng nâng cấp dữ liệu trước khi bắt buộc trường.

### Một giới hạn của enum trong tương thích

Server nên phân biệt `FULFILLMENT_METHOD_UNSPECIFIED` (không được chọn) với một **giá trị enum mới chưa biết** do client phiên bản mới gửi. Trong Java protobuf, một enum field thường có getter dạng enum và getter số nguyên, ví dụ `getFulfillmentMethod()` và `getFulfillmentMethodValue()`. Nếu client dùng giá trị chưa được server hiểu, server cần xử lý theo chính sách API thay vì mặc định chuyển sang `STORE_PICKUP`.

## 5. Code Java: validation thực tế ở ranh giới Spring gRPC

Với `protoc` và plugin gRPC Java, `CreateOrderRequest` sinh ra các getter `getCustomerId()`, `getLinesCount()`, `getFulfillmentMethod()` và `hasShippingCountry()`. Handler Spring gRPC có thể validate đầu vào mà không ép client cũ gửi field số 5.

```java
package com.myshop.server.order;

import com.myshop.grpc.order.v1.CreateOrderRequest;
import com.myshop.grpc.order.v1.CreateOrderResponse;
import com.myshop.grpc.order.v1.FulfillmentMethod;
import com.myshop.grpc.order.v1.OrderLine;
import com.myshop.grpc.order.v1.OrderServiceGrpc;
import com.google.protobuf.Timestamp;
import io.grpc.Status;
import io.grpc.stub.StreamObserver;
import java.time.Instant;
import java.util.UUID;
import org.springframework.grpc.server.service.GrpcService;

@GrpcService
public class OrderGrpcEndpoint extends OrderServiceGrpc.OrderServiceImplBase {

    @Override
    public void createOrder(
            CreateOrderRequest request,
            StreamObserver<CreateOrderResponse> observer) {

        if (request.getCustomerId().isBlank()
                || request.getRequestId().isBlank()
                || request.getLinesCount() == 0) {
            observer.onError(Status.INVALID_ARGUMENT
                    .withDescription("customer_id, request_id and lines are required")
                    .asRuntimeException());
            return;
        }

        for (OrderLine line : request.getLinesList()) {
            if (line.getProductId().isBlank() || line.getQuantity() <= 0) {
                observer.onError(Status.INVALID_ARGUMENT
                        .withDescription("each line requires product_id and quantity > 0")
                        .asRuntimeException());
                return;
            }
        }

        if (request.getFulfillmentMethod()
                == FulfillmentMethod.FULFILLMENT_METHOD_UNSPECIFIED
                || request.getFulfillmentMethod()
                == FulfillmentMethod.UNRECOGNIZED) {
            observer.onError(Status.INVALID_ARGUMENT
                    .withDescription("unsupported fulfillment_method")
                    .asRuntimeException());
            return;
        }

        // Chỉ validate field số 5 nếu client thực sự gửi nó.
        if (request.hasShippingCountry()
                && !request.getShippingCountry().matches("[A-Z]{2}")) {
            observer.onError(Status.INVALID_ARGUMENT
                    .withDescription("shipping_country must be an alpha-2 code")
                    .asRuntimeException());
            return;
        }

        // Ví dụ chỉ minh họa validation và response.
        // Ứng dụng thật phải ghi đơn, xử lý idempotency và giao hàng.
        Instant now = Instant.now();
        Timestamp createdAt = Timestamp.newBuilder()
                .setSeconds(now.getEpochSecond())
                .setNanos(now.getNano())
                .build();

        CreateOrderResponse response = CreateOrderResponse.newBuilder()
                .setOrderId(UUID.randomUUID().toString())
                .setCreatedAt(createdAt)
                .build();

        observer.onNext(response);
        observer.onCompleted();
    }
}
```

Ở đoạn mã minh họa, server kiểm tra:

- `customer_id` và `request_id` không rỗng, `lines` có ít nhất một phần tử.
- Mỗi dòng có `product_id` hợp lệ và `quantity > 0`.
- `fulfillment_method` khác `UNSPECIFIED` và không phải enum chưa nhận diện.
- `shipping_country` đúng định dạng **nếu được gửi**; nếu không gửi, không bị chặn bởi quy tắc mới này.

Mã chỉ minh họa validation: trong production, handler phải gọi domain service để tạo đơn thật, xử lý quyền truy cập, nguồn địa chỉ giao, transaction và idempotency. Nếu có cách xử lý `HOME_DELIVERY` thiếu quốc gia dựa trên hợp đồng `v1`, nên triển khai ở domain service rồi viết test cho nó. Không sử dụng ví dụ này như một chức năng tạo đơn hoàn chỉnh.

### Lỗi nào cần trả?

| Vấn đề | Gợi ý gRPC status | Giải thích |
| --- | --- | --- |
| Thiếu `customer_id`, danh sách dòng rỗng, quantity âm | `INVALID_ARGUMENT` | Dữ liệu đầu vào không hợp lệ |
| Mã khách hàng được truyền đúng định dạng nhưng không tồn tại | `NOT_FOUND` | Tài nguyên được yêu cầu không có |
| Đơn không thể tạo vì trạng thái kho không đủ | `FAILED_PRECONDITION` | Điều kiện nghiệp vụ tại thời điểm xử lý không đáp ứng |
| Xung đột cập nhật đồng thời cần đọc lại và thử lại | `ABORTED` trong mô hình phù hợp | Tranh chấp trạng thái, không phải sai cú pháp request |
| Người gọi không có quyền tạo đơn | `PERMISSION_DENIED` | Lỗi quyền truy cập |
| Dịch vụ phụ thuộc không khả dụng | `UNAVAILABLE` | Lỗi tạm thời; retry phải xét trạng thái command đã thực thi hay chưa |

Không nên trả response với `success = false` rồi kết thúc `OK` cho một yêu cầu thất bại; gRPC status giúp interceptor, client retry và hệ thống giám sát hiểu đúng kết quả.

## 6. Optional: khi vắng mặt và giá trị mặc định mang nghĩa khác nhau

Xét thao tác cập nhật ghi chú:

```proto
message UpdateOrderNoteRequest {
  string order_id = 1;
  optional string note = 2;
}
```

Trong Java:

```java
// Không gửi ghi chú: chưa yêu cầu thay đổi.
UpdateOrderNoteRequest a = UpdateOrderNoteRequest.newBuilder()
        .setOrderId("O-100")
        .build();
boolean aHasNote = a.hasNote();  // false

// Gửi ghi chú rỗng: yêu cầu xóa nội dung ghi chú.
UpdateOrderNoteRequest b = UpdateOrderNoteRequest.newBuilder()
        .setOrderId("O-100")
        .setNote("")
        .build();
boolean bHasNote = b.hasNote();  // true
```

Nếu bỏ `optional` rồi chỉ kiểm tra `getNote().isEmpty()`, server không phân biệt được hai ý định. Hợp đồng cần nêu rõ trường hợp `hasNote() == false`: có thể là no-op hoặc bị từ chối vì RPC chỉ có mục tiêu cập nhật ghi chú. Với ví dụ này, lựa chọn rõ ràng là **trả `INVALID_ARGUMENT` nếu không gửi `note`**, còn chuỗi rỗng có nghĩa là xóa ghi chú. Đây là validation theo ý nghĩa RPC, không phải do `optional` tự bắt buộc.

### Khi nào chọn FieldMask?

Nếu một RPC cho cập nhật nhiều trường, dùng `google.protobuf.FieldMask` để liệt kê đường dẫn được cập nhật:

```proto
import "google/protobuf/field_mask.proto";

message EditableOrderFields {
  string delivery_note = 1;
  bool gift_wrap = 2;
}

message UpdateOrderRequest {
  string order_id = 1;
  EditableOrderFields changes = 2;
  google.protobuf.FieldMask update_mask = 3;
}
```

Ví dụ `update_mask.paths = ["gift_wrap"]` với `changes.gift_wrap = false` có nghĩa **chủ ý đặt về false**. Server cập nhật chỉ các field trong mask, kiểm tra whitelist đường dẫn và coi những field không có trong mask là không thay đổi. Đường dẫn trong `FieldMask` dùng tên field proto, như `gift_wrap`, chứ không dùng tên getter Java. Cách biểu diễn FieldMask trong ProtoJSON có chuyển đổi sang dạng camelCase (ví dụ `"updateMask": "giftWrap"`).

`optional` phù hợp khi chỉ một vài scalar cần biết presence; `FieldMask` phù hợp khi cần một tập đường dẫn cập nhật, đặc biệt với đối tượng lớn hoặc lồng nhau. Không dùng chúng như cách tránh validation nghiệp vụ.

## 7. Oneof và message field: các kiểu bắt buộc có điều kiện

Một truy vấn có thể cho phép client chọn *một trong hai* cách định danh:

```proto
message FindOrderRequest {
  oneof selector {
    string order_id = 1;
    string external_reference = 2;
  }
}
```

`oneof` bảo đảm tối đa một nhánh được đặt trong message tại cùng thời điểm. Tuy nhiên, client vẫn có thể gửi **không có nhánh nào**; server phải kiểm tra `getSelectorCase()` và từ chối trường hợp không chọn. Ngoài ra, client có thể chọn nhánh `order_id` nhưng đặt chuỗi rỗng, nên vẫn cần validate giá trị.

Với field kiểu message:

```proto
message Address {
  string country_code = 1;
  string city = 2;
}

message ShipOrderRequest {
  string order_id = 1;
  Address destination = 2;
}
```

Trong Java, `hasDestination()` cho biết message `destination` có hiện diện. Nhưng một `Address` rỗng vẫn là message hiện diện: cần validate `country_code`, `city` và những ràng buộc địa chỉ khác. Message presence không thay thế validation bên trong message.

### Enum và default value

Enum trong proto3 nên có giá trị đầu tiên bằng 0, thường dùng hậu tố `_UNSPECIFIED`:

```proto
enum PaymentMethod {
  PAYMENT_METHOD_UNSPECIFIED = 0;
  PAYMENT_METHOD_CARD = 1;
  PAYMENT_METHOD_BANK_TRANSFER = 2;
}
```

Nếu nghiệp vụ bắt buộc client chọn phương thức thanh toán, server từ chối `PAYMENT_METHOD_UNSPECIFIED`. Nhưng đừng ép buộc thêm một giá trị enum mới vừa được giới thiệu vào request cũ: những client chưa nâng cấp không thể gửi nó. Hãy thiết kế cách xử lý giá trị không xác định và chính sách versioning rõ ràng.

## 8. Thiết kế tương thích khi thêm field mới: kế hoạch triển khai

Khi muốn thêm field vào một request đang được sử dụng, hãy tách câu chuyện **mở rộng wire format** và **thay đổi quy tắc nghiệp vụ**:

| Giai đoạn | Server | Client | Mục tiêu |
| --- | --- | --- | --- |
| 1. Công bố | Nhận field mới; vẫn hỗ trợ cách gọi cũ | Client cũ giữ nguyên | Không làm gián đoạn traffic hiện tại |
| 2. Nâng cấp dần | Validate giá trị mới nếu có; duy trì fallback đã cam kết | Client mới bắt đầu gửi field | Kiểm chứng giá trị mới trong vận hành |
| 3. Quan sát | Thống kê tỷ lệ thiếu field theo phiên bản client nếu phù hợp, không log dữ liệu nhạy cảm | Khắc phục các client chưa triển khai | Biết ai còn phụ thuộc hợp đồng cũ |
| 4. Chốt bắt buộc | Giữ hợp đồng v1 hoặc công bố endpoint/namespace v2 nếu không thể tương thích | Di chuyển theo tài liệu migration | Thay đổi quy tắc mà không bất ngờ phá client cũ |

Không nên dựa vào việc tất cả client “sẽ sớm cập nhật” nếu chưa có bằng chứng. Với mobile, hệ thống đối tác hoặc các phiên bản được triển khai độc lập, client cũ có thể tồn tại rất lâu. Nếu server không thể xác định hoặc quản lý phiên bản client, việc cưỡng ép field mới trên endpoint cũ càng rủi ro.

### Vì sao “server mới đọc được request cũ” chưa đủ?

Xét bốn hướng tương tác:

| Cặp phiên bản | Điều thường xảy ra ở tầng protobuf | Rủi ro thực tế |
| --- | --- | --- |
| **Client cũ → server mới** | Các field cũ vẫn giải mã được; field mới vắng mặt | Server mới có thể thay validation, bất ngờ từ chối client cũ |
| **Client mới → server cũ** | Server cũ thường bỏ qua field mới không biết trong binary protobuf | Ý định mới có thể bị **bỏ qua**; ví dụ quốc gia giao hàng không được áp dụng |
| **Client mới → server mới** | Hai bên hiểu field mới | Vẫn cần validate, quyền và bảo đảm nghiệp vụ |
| **Client cũ → server cũ** | Hành vi cũ tiếp tục | Nếu cần chuyển đổi, phải lên kế hoạch vòng đời API |

Nếu client **phụ thuộc vào hành vi mới**, không nên gửi request mới tới server cũ rồi mặc định rằng nó đã áp dụng field mới. Trong quá trình triển khai nhiều instance server, cần bảo đảm server phiên bản cũ không âm thầm bỏ qua dữ liệu ảnh hưởng tính đúng đắn. Có thể triển khai server hỗ trợ trường mới trước client, sử dụng endpoint/capability riêng khi cần hoặc version API.

### Khi nào nên tạo v2?

Nên cân nhắc phiên bản mới khi **không thể giữ cùng ngữ nghĩa cho client cũ**, ví dụ:

- Mọi đơn giao tận nơi từ nay cần một loại thông tin mà server v1 không có cách xác định an toàn.
- RPC cũ từng cho phép thiếu field, nhưng nghiệp vụ mới bắt buộc client cung cấp trực tiếp.
- Loại hoặc kiểu của field thay đổi đến mức client cũ không thể diễn giải đúng.
- Client mới cần server xử lý một trường quan trọng mà server cũ chắc chắn bỏ qua.

Một namespace mới như `shop.order.v2` hoặc RPC mới được công bố rõ sẽ giúp vận hành song song hợp đồng trong giai đoạn chuyển đổi. Không bắt buộc nâng version khi chỉ thêm field tùy chọn có mặc định an toàn.

## 9. Tương thích binary, ProtoJSON và mã Java là ba chuyện khác nhau

Đừng đánh giá tác động chỉ dựa vào việc message protobuf có thể parse được hay không:

| Thay đổi | Binary protobuf | ProtoJSON / Java / hành vi |
| --- | --- | --- |
| Thêm field số mới tùy chọn | Client/server cũ thường bỏ qua field không biết | Các client cũ không gửi field; hành vi mới cần fallback |
| Đổi `string x = 1` thành `optional string x = 1` | Tag và wire type vẫn tương thích ở nhiều tình huống | Java sinh thêm `hasX()`; biểu diễn giá trị mặc định và presence có thể ảnh hưởng logic |
| Đổi tên field, giữ nguyên số và kiểu | Có thể vẫn đọc được payload nhị phân | Getter/builder Java, khóa JSON mặc định và descriptor đổi |
| Đổi field number của field đã công bố | Có nguy cơ đọc sai hoặc mất dữ liệu | Ảnh hưởng mọi bên tiêu thụ |
| Đổi tên message | Field binary riêng lẻ có thể không đổi | Generated API, reflection và `google.protobuf.Any` có thể bị ảnh hưởng |
| Đổi proto `package`, tên service hoặc tên RPC | Payload có thể vẫn tương đương | **Đổi đường dẫn gRPC** như `/shop.order.v1.OrderService/CreateOrder` |

Trong ProtoJSON, một field thường dùng tên dạng `lowerCamelCase` (ví dụ `shippingCountry` cho `shipping_country`). Người dùng Java có thể gọi `hasShippingCountry()` với field `optional`, nhưng client JSON cũ có thể không gửi khóa này. Ngoài ra, với một số kiểu dữ liệu, giá trị mặc định và field vắng mặt được serializer trình bày khác nhau tùy cấu hình; đừng dùng sự xuất hiện của khóa JSON làm phương án duy nhất để xác định ý định mà chưa hiểu mapping.

### Xóa field và reserved

Nếu một field đã phát hành được xóa khỏi schema, không dùng lại số hoặc tên cho ý nghĩa mới:

```proto
message ExampleRequest {
  reserved 7;
  reserved "legacy_customer_code";

  string customer_id = 1;
}
```

Ví dụ trên chỉ minh họa một field cũ số 7 đã bị loại bỏ. `reserved` giúp ngăn nhà phát triển vô tình tái sử dụng field number/tên cũ. Không tự ý đổi số hiện tại để “sắp xếp lại” schema.

## 10. Metadata, deadline, lỗi và retry không thể thay field contract

Hợp đồng message cần chứa dữ liệu nghiệp vụ; nhiều thông tin kỹ thuật của lời gọi có vị trí khác:

| Mối quan tâm | Đặt ở đâu | Liên quan đến field bắt buộc |
| --- | --- | --- |
| Xác thực người gọi, trace context | gRPC metadata và interceptor | Không cần thêm `auth_token` vào mọi request nghiệp vụ |
| Deadline | Client gRPC đặt deadline, server xử lý cancellation | Deadline hết không có nghĩa command chắc chắn chưa commit |
| Trạng thái lỗi | gRPC status và error details khi cần | Thông báo input thiếu field bằng `INVALID_ARGUMENT` |
| TLS/mTLS | Channel và server transport | Bảo vệ đường truyền, không phải một field `secure = true` |
| Idempotency | Request ID nghiệp vụ cùng cơ chế lưu/dedupe ở server | Nếu một client retry sau timeout, phải giữ nguyên ID cho cùng ý định |
| Giám sát | Metrics/traces theo service và method | Quan sát tỷ lệ thiếu field để đánh giá migration |

**Chú ý retry:** nếu `CreateOrder` đã commit nhưng client không nhận response do deadline, việc thử lại bằng `request_id` khác có thể tạo hai đơn. Vì vậy, nếu hợp đồng yêu cầu idempotency, server phải triển khai ràng buộc duy nhất/khả năng trả lại kết quả cho cùng request ID và cùng nội dung. Tương tự, không thể suy ra “không gửi field mới” là lỗi có thể retry ngay: nếu client cũ chưa biết field ấy, retry bao nhiêu lần vẫn thiếu.

Với server streaming hoặc bidirectional streaming, vấn đề tương tự xuất hiện trên **mỗi thông điệp trong luồng**. Nếu thêm field mới và coi nó là bắt buộc cho mọi sự kiện, các client stream cũ có thể không hiểu payload mới; nếu bắt mọi request stream cũ gửi field mới, kết nối sẽ lỗi. Cần thiết kế compatibility theo schema message và hành vi của consumer, đồng thời kiểm thử cancellation, backpressure, phân đoạn dữ liệu và trạng thái kết thúc luồng.

## 11. Kiểm thử tương thích: đừng chỉ kiểm tra phiên bản mới

Kiểm thử gRPC nên dùng stub Java sinh từ các phiên bản schema phù hợp, hoặc dùng fixture binary/ProtoJSON tương ứng. Khi đã triển khai thêm `shipping_country`, ít nhất cần những tình huống:

| Trường hợp | Input | Kỳ vọng |
| --- | --- | --- |
| Client v1 tạo đơn | Không có tag 5 | Server v1 mở rộng vẫn xử lý theo quy tắc tương thích đã cam kết |
| Client mới không gửi field mới | `hasShippingCountry() == false` | Không tự áp quy tắc bắt buộc mới lên toàn bộ request v1 |
| Client gửi quốc gia hợp lệ | `shipping_country = "VN"` | Validate và sử dụng đúng chính sách nghiệp vụ |
| Client gửi quốc gia sai định dạng | `shipping_country = "Vietnam"` | `INVALID_ARGUMENT` nếu hợp đồng quy định mã alpha-2 |
| Danh sách dòng rỗng | `lines_count = 0` | `INVALID_ARGUMENT`; không tạo đơn |
| Số lượng bằng 0 hoặc âm | `quantity <= 0` | `INVALID_ARGUMENT` |
| Enum không được chọn | `FULFILLMENT_METHOD_UNSPECIFIED` | `INVALID_ARGUMENT` |
| Update note không gửi `note` | `hasNote() == false` | Trả lỗi hoặc no-op **theo quy ước công bố** |
| Update note đặt chuỗi rỗng | `hasNote() == true`, `getNote().isEmpty()` | Xóa ghi chú nếu hợp lệ |
| Client mới gửi field tới server cũ | Server không biết tag 5 | Phát hiện nguy cơ field bị bỏ qua; kiểm soát routing/rollout |
| Client retry cùng `request_id` | Cùng payload sau timeout | Không tạo lặp trong phạm vi cam kết idempotency |
| Client đã cũ gọi API v2 | RPC mới hoặc package mới | Không giả định stub cũ tự gọi được; kiểm tra migration rõ ràng |

### Thử bằng grpcurl

Khi server thử nghiệm đang chạy ở `localhost:9090` và cho phép kết nối plaintext, có thể gửi request theo mapping ProtoJSON:

```bash
grpcurl -plaintext \
  -import-path src/main/proto \
  -proto order/v1/order.proto \
  -d '{
    "customerId": "C-100",
    "lines": [{"productId": "P-100", "quantity": 2}],
    "fulfillmentMethod": "FULFILLMENT_METHOD_STORE_PICKUP",
    "requestId": "order-20261119-001"
  }' \
  localhost:9090 shop.order.v1.OrderService/CreateOrder
```

Request trên cố ý **không** có `shippingCountry`, mô phỏng client cũ. Một server tương thích không nên từ chối nó *chỉ vì* field số 5 chưa được gửi. Trong môi trường thực, cổng và cấu hình TLS phải phù hợp, còn handler phải có logic nghiệp vụ thật để tạo đơn.

Để kiểm tra presence của field mới, thêm khóa:

```json
{
  "shippingCountry": "VN"
}
```

Đoạn JSON này là phần bổ sung vào request phía trên, không phải toàn bộ input hợp lệ độc lập. Với `optional string shipping_country`, server Java có thể kiểm tra `hasShippingCountry()` thay vì suy đoán từ `getShippingCountry().isEmpty()`.

## 12. Checklist ra quyết định trước khi công bố field

Trước khi thêm, xóa hoặc đổi một field trong API Spring gRPC, hãy trả lời:

1. **Về nghiệp vụ:** field bắt buộc cho mọi lời gọi, chỉ một nhánh điều kiện, hay chỉ là tùy chọn cải thiện kết quả?
2. **Về presence:** có cần phân biệt “không gửi” với “gửi giá trị mặc định” không? Nếu có, scalar `optional`, `oneof`, message hoặc `FieldMask` có đáp ứng đúng ý định?
3. **Về client cũ:** request được sinh từ proto trước đây có gửi field này không? Server mới có thể duy trì hành vi cũ một cách an toàn không?
4. **Về client mới:** server cũ bỏ qua field mới có gây kết quả sai nguy hiểm không? Có cần server-first deployment, capability negotiation hoặc API v2?
5. **Về validation:** giá trị trống, 0, false, danh sách rỗng, enum không biết và message rỗng được xử lý ra sao?
6. **Về wire:** field number có giữ nguyên không, kiểu có tương thích không, số/tên đã xóa đã `reserved` chưa?
7. **Về vận hành:** gRPC status, metadata, deadline, idempotency và tỷ lệ lỗi của từng phiên bản client được theo dõi như thế nào?
8. **Về kiểm thử:** đã chạy cả client cũ → server mới, client mới → server cũ và các tình huống presence chưa?

### Tự kiểm tra

**Câu 1.** Trong proto3, `int32 quantity = 1;` không có `optional`. Server nhận `getQuantity() == 0`. Có biết chắc client đã gửi giá trị 0 không?

**Đáp án:** Không. Với scalar thường, server không có presence để phân biệt 0 do client gửi với 0 do field bị bỏ trống. Nếu nghiệp vụ cấm cả hai, chỉ cần từ chối `quantity <= 0`; nếu cần phân biệt, dùng cơ chế presence phù hợp.

**Câu 2.** API `CreateOrder` đã có nhiều client. Thêm `string shipping_country = 5;` là tương thích binary. Có thể từ ngày mai trả `INVALID_ARGUMENT` cho mọi request thiếu field 5?

**Đáp án:** Không nên nếu phải giữ tương thích hành vi với client cũ. Client trước đây không thể gửi field này. Cần fallback an toàn, migration hoặc hợp đồng mới khi phải bắt buộc.

**Câu 3.** Với `optional bool gift_wrap = 2;`, phân biệt không gửi và gửi `false` bằng cách nào trong Java?

**Đáp án:** Dùng `hasGiftWrap()` để kiểm tra sự hiện diện; `getGiftWrap()` trả giá trị. `hasGiftWrap() == true` cùng `getGiftWrap() == false` nghĩa là client chủ ý truyền false.

**Câu 4.** Vì sao `oneof` vẫn cần validation nếu request bắt buộc chọn đúng một trong hai định danh?

**Đáp án:** `oneof` bảo đảm tối đa một nhánh được đặt, nhưng có thể không nhánh nào được gửi; nhánh được chọn vẫn có thể chứa giá trị rỗng hoặc sai định dạng.

**Câu 5.** Client mới gửi `shipping_country` đến server cũ, lệnh RPC trả `OK`. Có chắc server đã sử dụng quốc gia được gửi?

**Đáp án:** Không. Server cũ có thể bỏ qua field chưa biết khi parse binary protobuf. Nếu hành vi mới phụ thuộc vào field này, phải bảo đảm client gọi server có hỗ trợ hoặc dùng hợp đồng/phiên bản mới.

Trong thiết kế schema gRPC, **điều kiện bắt buộc phải xuất phát từ nghiệp vụ và phải được kiểm tra ở server**, còn cách thể hiện sự hiện diện thuộc về protobuf. Khi thêm một field vào hợp đồng đang hoạt động, hãy bảo vệ cả *khả năng giải mã* lẫn *hành vi mà client cũ đã được cam kết*. Đó là nền tảng để dịch vụ Spring gRPC mở rộng ổn định qua nhiều phiên bản và nhiều kiểu RPC.
