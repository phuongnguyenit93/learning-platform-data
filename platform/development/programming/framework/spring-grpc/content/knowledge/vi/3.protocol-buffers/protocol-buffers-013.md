# Any, Empty, FieldMask và wrappers

## Mục tiêu học tập

Sau bài này, bạn có thể:

- Chọn đúng well-known type cho payload có kiểu động, RPC không có dữ liệu, cập nhật từng phần và scalar cần presence.
- Đóng gói, kiểm tra và giải nén message bằng **google.protobuf.Any** trong Java.
- Dùng **google.protobuf.Empty** cho request hoặc response không có field.
- Thiết kế update request với **google.protobuf.FieldMask**, xác thực đường dẫn và định nghĩa rõ semantics cập nhật.
- Hiểu vai trò của scalar wrapper types và khi nào nên dùng **optional** thay thế.
- Nhận biết biểu diễn ProtoJSON và các giới hạn tương thích của từng kiểu.

## 1. Chọn well-known type theo mục đích

Protocol Buffers cung cấp các **well-known types (WKT)** để biểu diễn những cấu trúc thường gặp. Trong dịch vụ **SPRING_GRPC**, chúng giúp client và server dùng cùng một hợp đồng chuẩn thay vì tự tạo nhiều kiểu tương tự.

| Kiểu | Dùng khi | Ý nghĩa chính |
| --- | --- | --- |
| **google.protobuf.Any** | Cần chứa một message Protobuf mà kiểu cụ thể chỉ được biết lúc chạy | Gói message cùng định danh kiểu. |
| **google.protobuf.Empty** | RPC không cần dữ liệu request hoặc response | Message chuẩn không có field. |
| **google.protobuf.FieldMask** | Cần chỉ rõ field nào được đọc hoặc cập nhật | Danh sách đường dẫn field. |
| **google.protobuf.*Value** | Cần bọc scalar trong một message có presence, thường để tương thích schema cũ | Message wrapper cho scalar. |

Các kiểu này không thay thế lẫn nhau. **Any** chứa một message có kiểu; **Empty** là message rỗng; **FieldMask** chọn các field theo đường dẫn; wrappers bọc một giá trị scalar. Bài này tập trung vào cách khai báo, API Java, ProtoJSON và các quyết định thiết kế quan trọng.

## 2. Any: chứa message có kiểu được xác định lúc chạy

Khai báo:

~~~proto
syntax = "proto3";

package learning.events.v1;

import "google/protobuf/any.proto";

message EventEnvelope {
  string event_id = 1;
  google.protobuf.Any payload = 2;
}
~~~

**Any** có hai thành phần:

- **type_url**: định danh kiểu Protobuf được đóng gói, thường kết thúc bằng tên đầy đủ của message.
- **value**: byte sequence chứa message đã serialize.

Ví dụ hai loại event:

~~~proto
message OrderCreated {
  string order_id = 1;
  string customer_id = 2;
}

message PaymentCaptured {
  string order_id = 1;
  int64 amount_minor_units = 2;
  string currency_code = 3;
}
~~~

Một EventEnvelope có thể chứa OrderCreated hoặc PaymentCaptured. Schema của envelope không cần thêm một field riêng cho từng loại payload mới.

Any phù hợp với event bus, extension point hoặc API thực sự cần một tập message mở rộng được. Nếu tập lựa chọn đã biết và ổn định, **oneof** thường dễ kiểm tra và an toàn kiểu hơn Any.

## 3. Đóng gói và giải nén Any trong Java

Lớp Java tương ứng là **com.google.protobuf.Any**. Có thể đóng gói message bằng **Any.pack()**:

~~~java
import com.example.events.v1.OrderCreated;
import com.google.protobuf.Any;

OrderCreated event = OrderCreated.newBuilder()
    .setOrderId("O-42")
    .setCustomerId("C-17")
    .build();

Any payload = Any.pack(event);
~~~

Sau đó đặt Any vào envelope:

~~~java
EventEnvelope envelope = EventEnvelope.newBuilder()
    .setEventId("evt-100")
    .setPayload(payload)
    .build();
~~~

Khi đọc, kiểm tra kiểu trước khi giải nén:

~~~java
import com.google.protobuf.InvalidProtocolBufferException;

if (envelope.getPayload().is(OrderCreated.class)) {
    OrderCreated decoded =
        envelope.getPayload().unpack(OrderCreated.class);
    handleOrderCreated(decoded);
} else if (envelope.getPayload().is(PaymentCaptured.class)) {
    PaymentCaptured decoded =
        envelope.getPayload().unpack(PaymentCaptured.class);
    handlePaymentCaptured(decoded);
} else {
    handleUnsupportedEventType(
        envelope.getPayload().getTypeUrl());
}
~~~

**is(Class)** kiểm tra type URL có khớp kiểu mong đợi; **unpack(Class)** giải mã payload và có thể ném **InvalidProtocolBufferException** nếu dữ liệu không hợp lệ. Không gọi unpack một cách mù quáng với một lớp bất kỳ.

Đối với hệ thống production, hãy lập danh sách kiểu được phép nhận, xử lý rõ kiểu chưa hỗ trợ và ghi log type URL đã được kiểm tra. Any không phải cơ chế phân quyền: biết type URL không có nghĩa người gửi được phép yêu cầu server thực thi hành vi của kiểu đó.

## 4. Any và ProtoJSON

Trong ProtoJSON, Any có thuộc tính đặc biệt **@type** để chỉ kiểu message được đóng gói. Với message thông thường:

~~~json
{
  "@type": "type.googleapis.com/learning.events.v1.OrderCreated",
  "orderId": "O-42",
  "customerId": "C-17"
}
~~~

Khi Any chứa một well-known type có JSON mapping đặc biệt, nội dung thường nằm trong thuộc tính **value**. Ví dụ, Any chứa Duration có dạng:

~~~json
{
  "@type": "type.googleapis.com/google.protobuf.Duration",
  "value": "3.5s"
}
~~~

Để JsonFormat phân giải các kiểu message được phép trong Any, đăng ký descriptor bằng **TypeRegistry**:

~~~java
import com.google.protobuf.TypeRegistry;
import com.google.protobuf.util.JsonFormat;

TypeRegistry registry = TypeRegistry.newBuilder()
    .add(OrderCreated.getDescriptor())
    .add(PaymentCaptured.getDescriptor())
    .build();

String json = JsonFormat.printer()
    .usingTypeRegistry(registry)
    .print(envelope);
~~~

Parser dùng cùng registry:

~~~java
EventEnvelope.Builder builder = EventEnvelope.newBuilder();
JsonFormat.parser()
    .usingTypeRegistry(registry)
    .merge(json, builder);
~~~

Nếu thiếu type trong registry, JsonFormat không thể giải mã phần nội dung Any thành message tương ứng. Registry nên chỉ chứa các kiểu ứng dụng dự kiến hỗ trợ, thay vì mở rộng tùy tiện mọi message trong hệ thống.

## 5. Empty: message không có field

**google.protobuf.Empty** là message chuẩn không có field:

~~~proto
syntax = "proto3";

import "google/protobuf/empty.proto";

message HealthStatus {
  bool serving = 1;
}

service HealthService {
  rpc Check(google.protobuf.Empty) returns (HealthStatus);
  rpc ResetCache(google.protobuf.Empty) returns (google.protobuf.Empty);
}
~~~

Empty vẫn là một message Protobuf. Nó không có nghĩa request không tồn tại hoặc kết nối không gửi frame. Một RPC unary vẫn có request/response message theo chữ ký; message Empty chỉ không mang field dữ liệu.

Trong Java:

~~~java
import com.google.protobuf.Empty;

Empty request = Empty.getDefaultInstance();
~~~

Server có thể trả Empty:

~~~java
observer.onNext(Empty.getDefaultInstance());
observer.onCompleted();
~~~

Empty hữu ích khi thao tác chỉ cần metadata gRPC hoặc context xác thực, ví dụ một lệnh xóa cache toàn cục. Nếu thao tác cần trả số mục đã xóa, thời điểm thực hiện hoặc trạng thái chi tiết, nên định nghĩa response message có các field đó.

ProtoJSON biểu diễn Empty thành object rỗng:

~~~json
{}
~~~

Không dùng Empty cho mọi thao tác “không cần nhiều dữ liệu”. Một request vẫn có thể cần **request_id**, lý do, phạm vi hoặc idempotency key; khi đó nên khai báo message cụ thể.

## 6. FieldMask: chỉ rõ field nào được cập nhật

**google.protobuf.FieldMask** chứa danh sách đường dẫn field. Nó thường xuất hiện trong request cập nhật một phần để phân biệt field cần thay đổi với field cần giữ nguyên.

Ví dụ:

~~~proto
syntax = "proto3";

import "google/protobuf/field_mask.proto";

message UserProfile {
  string display_name = 1;
  string email = 2;
  repeated string labels = 3;
}

message UpdateUserRequest {
  string user_id = 1;
  UserProfile profile = 2;
  google.protobuf.FieldMask update_mask = 3;
}
~~~

Nếu client chỉ muốn cập nhật email, mask có đường dẫn **email**. Nếu muốn xóa danh sách labels bằng cách thay nó thành danh sách rỗng, mask phải chứa **labels** và server phải quy định semantics là replace.

FieldMask không tự sửa dữ liệu, không tự kiểm tra quyền và không quyết định collection được nối hay thay thế. Nó chỉ nói **field nào nằm trong phạm vi cập nhật**; ứng dụng phải định nghĩa cách áp dụng mask.

### Tên đường dẫn

Trong biểu diễn schema và Java, FieldMask lưu path theo tên field Protobuf, thường là **lower_snake_case**:

~~~java
import com.google.protobuf.FieldMask;

FieldMask mask = FieldMask.newBuilder()
    .addPaths("display_name")
    .addPaths("email")
    .build();
~~~

Trong ProtoJSON, FieldMask có biểu diễn chuỗi phân tách bằng dấu phẩy và chuyển tên field sang **lowerCamelCase**:

~~~json
{
  "updateMask": "displayName,email"
}
~~~

Với field lồng nhau, dùng dấu chấm để phân tách đường dẫn, ví dụ **preferences.email** trong schema; ProtoJSON chuyển từng thành phần sang lowerCamelCase. Không dùng chỉ số mảng hoặc khóa map trong path như thể FieldMask là ngôn ngữ truy vấn tùy ý.

## 7. Áp dụng FieldMask ở tầng ứng dụng

Server nên kiểm tra mask trước khi thay đổi entity. Một cách đơn giản là kiểm tra từng path được hỗ trợ:

~~~java
void applyUpdate(
        UpdateUserRequest request,
        UserProfile.Builder current) {

    if (!request.hasProfile()) {
        throw invalidArgument("profile is required");
    }

    for (String path : request.getUpdateMask().getPathsList()) {
        switch (path) {
            case "display_name" ->
                current.setDisplayName(
                    request.getProfile().getDisplayName());
            case "email" ->
                current.setEmail(request.getProfile().getEmail());
            case "labels" -> {
                current.clearLabels();
                current.addAllLabels(
                    request.getProfile().getLabelsList());
            }
            default ->
                throw invalidArgument("Unsupported update path: " + path);
        }
    }
}
~~~

Trong ví dụ, labels được **thay toàn bộ** khi path labels có mặt trong mask. Nếu path không có trong mask, danh sách hiện tại được giữ nguyên. Cách xử lý này cũng cho phép client chủ động thay danh sách bằng rỗng.

Một số quy tắc nên xác định rõ trong API:

- Mask rỗng có nghĩa không cập nhật, hay cập nhật tất cả field?
- Mask bị thiếu có được chấp nhận không?
- Field không được hỗ trợ có bị từ chối hay bỏ qua?
- Repeated/map được replace, append, merge hay xóa theo cách nào?
- Có cho phép cập nhật field định danh, field chỉ đọc hoặc field nhạy cảm không?

Không có một semantics cập nhật tự động phù hợp với mọi API. Tài liệu RPC và logic server phải thống nhất chính sách này.

## 8. FieldMask cho field lồng nhau và kiểm tra đường dẫn

Giả sử:

~~~proto
message Preferences {
  bool marketing_enabled = 1;
  string locale = 2;
}

message UserProfile {
  string display_name = 1;
  Preferences preferences = 2;
}
~~~

Một path như **preferences.locale** chọn field con locale. Nếu mask chỉ chứa **preferences**, ứng dụng có thể định nghĩa thay toàn bộ message Preferences; nếu chứa **preferences.locale**, ứng dụng chỉ sửa locale.

Server cần kiểm tra path dựa trên descriptor của message đích hoặc một allowlist rõ ràng. Không chỉ kiểm tra chuỗi không rỗng rồi dùng reflection tùy ý để cập nhật mọi field, vì điều đó có thể cho phép sửa field nội bộ hoặc field không được phép cập nhật.

Khi một field bị đổi tên trong schema, các path FieldMask cũng chịu ảnh hưởng. Đây là một phần của hợp đồng API, vì vậy cần xem xét client cũ, ProtoJSON và logic cập nhật trong quá trình tiến hóa schema.

## 9. Scalar wrappers: message bao quanh giá trị đơn

Protobuf cung cấp wrapper types:

- **google.protobuf.StringValue**
- **google.protobuf.BoolValue**
- **google.protobuf.Int32Value**, **Int64Value**
- **google.protobuf.UInt32Value**, **UInt64Value**
- **google.protobuf.FloatValue**, **DoubleValue**
- **google.protobuf.BytesValue**

Ví dụ schema cũ:

~~~proto
syntax = "proto3";

import "google/protobuf/wrappers.proto";

message LegacySettings {
  google.protobuf.BoolValue notifications_enabled = 1;
  google.protobuf.Int32Value retry_limit = 2;
  google.protobuf.StringValue nickname = 3;
}
~~~

Vì wrapper là message field, nó có presence:

~~~java
LegacySettings absent = LegacySettings.newBuilder().build();

LegacySettings explicitFalse = LegacySettings.newBuilder()
    .setNotificationsEnabled(
        com.google.protobuf.BoolValue.newBuilder()
            .setValue(false)
            .build())
    .build();

System.out.println(absent.hasNotificationsEnabled());       // false
System.out.println(explicitFalse.hasNotificationsEnabled()); // true
System.out.println(explicitFalse.getNotificationsEnabled().getValue());
// false
~~~

Wrapper giúp schema proto3 cũ phân biệt field scalar vắng mặt với field hiện diện bằng giá trị mặc định. Trong schema mới, **optional bool**, **optional int32** hoặc **optional string** thường đơn giản hơn cho nhu cầu presence scalar:

~~~proto
message ModernSettings {
  optional bool notifications_enabled = 1;
  optional int32 retry_limit = 2;
  optional string nickname = 3;
}
~~~

Không đổi wrapper đã phát hành thành optional scalar trên cùng field number chỉ vì cả hai đều có presence. Wrapper được mã hóa như một message lồng nhau; optional scalar dùng wire type của scalar. Thay đổi này có thể phá tương thích nhị phân.

## 10. ProtoJSON của wrappers và các lưu ý

ProtoJSON biểu diễn wrapper như **giá trị scalar**, không phải object có thuộc tính value:

~~~json
{
  "notificationsEnabled": false,
  "retryLimit": 3,
  "nickname": "An"
}
~~~

Một số kiểu có quy tắc JSON riêng của scalar bên trong: wrapper int64/uint64 được biểu diễn như chuỗi số thập phân; BytesValue được biểu diễn bằng Base64.

Với wrapper field, JSON **null** được chấp nhận để biểu thị field không có giá trị/presence. Điều này khác với đặt wrapper thành false hoặc 0:

- **notificationsEnabled** không xuất hiện hoặc là null: wrapper không hiện diện.
- **notificationsEnabled: false**: wrapper hiện diện với giá trị false.

Trong schema mới, optional scalar cũng có thể biểu đạt presence; hãy kiểm thử đúng hành vi parser/printer được dùng ở gateway. Không nhầm null với lệnh xóa dữ liệu trong database nếu hợp đồng cập nhật chưa định nghĩa điều đó.

Wrappers hiện chủ yếu cần cho tương thích schema cũ hoặc API đòi hỏi một message wrapper cụ thể. Với field scalar mới trong proto3, ưu tiên **optional** nếu chỉ cần explicit presence.

## 11. Chọn Any, oneof, Struct hay wrappers?

| Nhu cầu | Lựa chọn thường phù hợp | Lý do |
| --- | --- | --- |
| Một trong vài payload đã biết, tập lựa chọn được kiểm soát | **oneof** | API sinh kiểu cụ thể và case rõ ràng. |
| Payload mở rộng bằng message Protobuf được xác định lúc chạy | **Any** | Mang type URL và byte của message. |
| Dữ liệu JSON động, không có schema Protobuf cố định | **Struct/Value/ListValue** | Mô hình hóa object/array/value kiểu JSON. |
| Scalar cần presence trong schema mới | **optional scalar** | Gọn hơn wrapper. |
| Scalar wrapper đã tồn tại trong API cũ | **google.protobuf.*Value** | Giữ tương thích kiểu message hiện có. |
| RPC không cần field dữ liệu | **Empty** | Dùng message chuẩn rỗng. |
| Cập nhật một phần message | **FieldMask** | Nêu rõ đường dẫn field cần xử lý. |

Any không nên được dùng chỉ để tránh định nghĩa schema. Nó làm mất một phần tính an toàn kiểu ở thời điểm biên dịch và yêu cầu runtime kiểm tra type URL, allowlist và khả năng giải nén. Nếu biết trước các payload, oneof thường là lựa chọn dễ kiểm soát hơn.

## 12. Kiểm thử các well-known types

Các trường hợp quan trọng:

1. Any đóng gói và giải nén đúng message; type không hỗ trợ được xử lý có chủ đích.
2. Any round-trip qua ProtoJSON với TypeRegistry chứa đúng descriptor.
3. Empty được gửi và nhận như message rỗng; không nhầm với việc bỏ qua RPC.
4. FieldMask giữ đúng path, chuyển đúng tên khi qua ProtoJSON và từ chối path không được hỗ trợ.
5. FieldMask chọn repeated/map rỗng vẫn áp dụng đúng semantics replace đã định nghĩa.
6. Wrapper phân biệt absent với present-default; JSON null và false/0 được xử lý khác nhau.
7. Schema cũ và mới không tráo wrapper với optional scalar trên cùng field number.

Ví dụ JUnit 5 kiểm tra Any:

~~~java
import static org.junit.jupiter.api.Assertions.*;

import com.example.events.v1.OrderCreated;
import com.google.protobuf.Any;
import com.google.protobuf.InvalidProtocolBufferException;
import org.junit.jupiter.api.Test;

class AnyPayloadTest {
    @Test
    void packsAndUnpacksKnownMessage() throws Exception {
        OrderCreated source = OrderCreated.newBuilder()
            .setOrderId("O-42")
            .setCustomerId("C-17")
            .build();

        Any packed = Any.pack(source);

        assertTrue(packed.is(OrderCreated.class));
        assertEquals(source, packed.unpack(OrderCreated.class));
    }
}
~~~

Ví dụ kiểm thử tập trung vào API Any. Trong ứng dụng thật, bổ sung test cho type URL không nằm trong allowlist, payload hỏng, giới hạn kích thước và JSON parser với TypeRegistry.

## 13. Lỗi thường gặp

| Sai lầm | Hậu quả | Cách xử lý |
| --- | --- | --- |
| Dùng Any cho một tập payload cố định | Mất kiểm tra kiểu ở compile time, tăng logic runtime | Dùng oneof khi các lựa chọn đã biết. |
| Giải nén Any mà không kiểm tra type | Lỗi parse hoặc xử lý sai loại message | Kiểm tra **is()**, allowlist rồi mới **unpack()**. |
| Không đăng ký TypeRegistry khi parse Any JSON | JsonFormat không phân giải được kiểu payload | Đăng ký descriptor của kiểu được hỗ trợ. |
| Dùng Empty cho request cần id hoặc lý do | Server không có dữ liệu để thực hiện đúng thao tác | Tạo request message cụ thể. |
| Cho rằng FieldMask tự cập nhật dữ liệu | Bỏ sót replace/merge/clear và kiểm tra quyền | Triển khai semantics rõ ở server. |
| Bỏ qua path lạ trong FieldMask | Client có thể tưởng field đã được cập nhật | Từ chối hoặc xử lý theo hợp đồng đã công bố. |
| Dùng wrapper cho mọi scalar mới | Schema dài hơn và API phức tạp hơn cần thiết | Dùng optional scalar khi chỉ cần presence. |
| Đổi wrapper sang optional cùng số field | Có thể phá wire compatibility | Dùng field mới hoặc migration có kiểm soát. |

## 14. Bài tập thực hành

Một dịch vụ hồ sơ cần hỗ trợ event mở rộng, kiểm tra sức khỏe và cập nhật từng phần:

1. Tạo **EventEnvelope** chứa event_id và **Any payload**; đóng gói một **UserCreated** rồi kiểm tra type trước khi unpack.
2. Viết RPC **Ping** nhận và trả **Empty**; giải thích vì sao lời gọi vẫn có message request/response.
3. Tạo **UpdateProfileRequest** có UserProfile và FieldMask; chỉ cập nhật display_name khi path display_name có trong mask.
4. Quy định rõ cách thay repeated labels bằng danh sách rỗng khi mask chứa labels.
5. Tạo một schema legacy dùng **BoolValue** và một schema mới dùng **optional bool**; so sánh API Java, JSON và wire format.
6. Dùng JsonFormat và TypeRegistry để round-trip EventEnvelope có Any payload.

**Tiêu chí hoàn thành:** chọn đúng WKT theo ngữ nghĩa, kiểm tra được kiểu Any, dùng Empty đúng mục đích, áp dụng FieldMask có kiểm soát và hiểu giới hạn tương thích của wrappers.

## 15. Ghi nhớ

- **Any** chứa type URL và bytes của message; kiểm tra kiểu, allowlist và giải nén đúng lớp.
- **Empty** là message không có field, không phải một RPC không tồn tại.
- **FieldMask** chỉ ra đường dẫn field; server phải định nghĩa validation và semantics cập nhật.
- **Wrappers** cung cấp presence cho scalar trong schema cũ; với schema proto3 mới, thường ưu tiên optional scalar.
- ProtoJSON có mapping riêng cho Any, Empty, FieldMask và wrappers; dùng JsonFormat khi cần tuân thủ hợp đồng.
- Không tráo đổi các WKT chỉ vì chúng đều là message: chọn theo ý nghĩa dữ liệu và khả năng tương thích.

Hiểu Any, Empty, FieldMask và wrappers giúp thiết kế hợp đồng Protobuf linh hoạt mà vẫn kiểm soát được kiểu dữ liệu, cập nhật từng phần và tương thích giữa các phiên bản client/server Spring gRPC.
