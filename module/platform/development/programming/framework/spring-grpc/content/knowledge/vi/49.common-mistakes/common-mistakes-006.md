# Dùng string tự do thay cho enum hoặc message rõ nghĩa

## 1. Vì sao string tự do làm contract yếu đi?

Trong **SPRING_GRPC**, Protocol Buffers là contract giữa client và server. Một lỗi thiết kế thường gặp là dùng string cho mọi loại dữ liệu: trạng thái đơn hàng, loại thanh toán, vai trò, đơn vị tiền, loại sự kiện hoặc cả một object được serialize thành JSON. Cách này có vẻ linh hoạt, nhưng nó chuyển trách nhiệm định nghĩa contract sang từng client và server.

Ví dụ một field trạng thái có thể nhận các giá trị "pending", "PENDING", "in_progress", "processing" hoặc một typo không được dự kiến. Compiler không thể phát hiện sai chính tả; server phải tự đoán ý nghĩa; client phải so sánh chuỗi và tự xử lý các giá trị chưa biết.

Protobuf cung cấp ba công cụ có mục đích khác nhau:

- **string:** văn bản tự do, identifier hoặc giá trị opaque có tập giá trị mở.
- **enum:** một tập lựa chọn hữu hạn, có tên và số wire ổn định.
- **message:** một cấu trúc dữ liệu có field, kiểu, presence và khả năng tiến hóa.

Chọn đúng kiểu giúp schema thể hiện ý nghĩa, tạo code Java an toàn hơn và hỗ trợ API evolution. Không nên dùng string chỉ vì nó dễ khai báo hoặc cho rằng enum/message làm contract kém linh hoạt.

## 2. Chọn kiểu theo semantics của dữ liệu

Một quy tắc thực tế:

| Dữ liệu | Kiểu thường phù hợp | Lý do |
| --- | --- | --- |
| Tên hiển thị, mô tả, ghi chú | string | Văn bản tự do |
| Customer ID, order ID | string hoặc message wrapper | Identifier có representation văn bản |
| Trạng thái order có tập giá trị hữu hạn | enum | Compiler và contract biết các lựa chọn |
| Loại payment cố định | enum hoặc oneof message | Enum nếu chỉ là nhãn; oneof nếu mỗi loại có payload riêng |
| Địa chỉ, tiền, khoảng thời gian | message | Có nhiều field mang cấu trúc |
| Thời điểm | google.protobuf.Timestamp | Có semantics thời gian chuẩn |
| Thời lượng | google.protobuf.Duration | Có đơn vị và semantics rõ |
| Mã đối tác do bên ngoài định nghĩa | string | Tập giá trị có thể mở, không kiểm soát bởi API |
| Một trong nhiều payload khác cấu trúc | oneof chứa message | Biểu diễn lựa chọn loại trừ lẫn nhau |

Không chọn kiểu chỉ dựa trên dữ liệu hiện tại. Hãy hỏi: tập giá trị có hữu hạn và do API quản lý không? Dữ liệu có nhiều thành phần cần validate riêng không? Client có cần compiler hỗ trợ khi xử lý các trường hợp không?

## 3. Dùng enum cho tập giá trị hữu hạn

Ví dụ trạng thái order có tập giá trị được contract quản lý:

```proto
syntax = "proto3";

package commerce.orders.v1;

enum OrderState {
  ORDER_STATE_UNSPECIFIED = 0;
  ORDER_STATE_PENDING = 1;
  ORDER_STATE_CONFIRMED = 2;
  ORDER_STATE_SHIPPED = 3;
  ORDER_STATE_CANCELLED = 4;
}

message GetOrderReply {
  string order_id = 1;
  OrderState state = 2;
}
```

Enum giúp schema liệt kê rõ các trạng thái hợp lệ. Code Java sinh ra có thể dùng OrderState thay vì string tùy ý:

```java
switch (reply.getState()) {
    case ORDER_STATE_PENDING -> showPending();
    case ORDER_STATE_CONFIRMED -> showConfirmed();
    case ORDER_STATE_SHIPPED -> showShipped();
    case ORDER_STATE_CANCELLED -> showCancelled();
    case ORDER_STATE_UNSPECIFIED, UNRECOGNIZED ->
        handleUnknownState();
}
```

Tên enum trong code giúp IDE/compiler hỗ trợ rename/refactor và giảm typo. Tuy nhiên, client vẫn phải có nhánh xử lý giá trị chưa biết vì server có thể được nâng cấp trước client.

Không dùng enum nếu tập giá trị được tạo tùy ý bởi tenant hoặc đối tác và server không thể kiểm soát danh sách. Trong trường hợp đó, string có validation hoặc một resource/catalog riêng có thể phù hợp hơn.

## 4. Số enum trên wire là một phần contract

Protobuf binary truyền số nguyên của enum, không truyền tên symbol. Vì vậy:

- Không đổi số của enum đã phát hành.
- Không gán lại số đã xóa cho ý nghĩa mới.
- Không dùng số 0 cho một trạng thái nghiệp vụ thực sự; dành nó cho *_UNSPECIFIED hoặc giá trị mặc định an toàn.
- Khi xóa enum value, đánh dấu cả số và tên là reserved.
- Chỉ thêm giá trị mới với số mới.
- Tránh dùng số âm; encoding có thể kém hiệu quả hơn và không đem lại lợi ích contract.

Ví dụ khi loại bỏ một trạng thái cũ:

```proto
enum OrderState {
  ORDER_STATE_UNSPECIFIED = 0;
  ORDER_STATE_PENDING = 1;
  ORDER_STATE_CONFIRMED = 2;

  reserved 3;
  reserved "ORDER_STATE_LEGACY";
}
```

Không tái sử dụng số 3 cho trạng thái mới. Một client cũ có thể vẫn lưu hoặc forward số 3; nếu server mới gán lại số đó cho ý nghĩa khác, cùng wire value sẽ bị hiểu sai.

Ngoài binary wire compatibility, ProtoJSON thường biểu diễn enum bằng tên symbol. Đổi tên enum có thể ảnh hưởng JSON clients, log, config hoặc dữ liệu được lưu dưới dạng JSON dù số wire không đổi. Hãy xem cả binary và JSON contract khi rename.

## 5. Giá trị enum chưa biết và tương thích tiến

Proto3 hỗ trợ open enum semantics: message có thể mang một numeric enum value mà code được sinh ở phiên bản cũ chưa biết. Trong Java, getter enum có thể trả UNRECOGNIZED; numeric accessor giữ giá trị số nhận được.

Ví dụ:

```java
OrderState state = reply.getState();

if (state == OrderState.UNRECOGNIZED) {
    int rawValue = reply.getStateValue();
    log.warn("Unknown order state number: {}", rawValue);
    handleUnknownState();
}
```

Client cũ không nên giả định enum chỉ chứa các giá trị đã biết tại thời điểm compile. Cần quyết định rõ:

- Với trạng thái chỉ dùng để hiển thị, có thể hiển thị “trạng thái mới” và không cho hành động chưa hiểu.
- Với trạng thái ảnh hưởng quyết định tài chính/an toàn, fail closed hoặc yêu cầu nâng cấp client.
- Không tự ép UNRECOGNIZED thành PENDING hay một giá trị mặc định có side effect.
- Nếu proxy/adapter đọc rồi ghi lại message, giữ numeric value chưa biết khi cần forward.

Đối với request từ client, server cũng phải validate numeric enum value. Giá trị chưa biết có thể xuất hiện do client mới gửi tới server cũ; không tự coi nó là một lựa chọn hợp lệ.

## 6. Khi nào string vẫn là lựa chọn đúng?

String phù hợp khi giá trị là văn bản tự do hoặc tập giá trị mở mà API không quản lý đầy đủ:

- Tên người dùng, mô tả hoặc ghi chú.
- Identifier do hệ thống ngoài cấp.
- Mã provider có thể thêm mới mà không cần phát hành schema mới.
- Locale tag hoặc currency code theo chuẩn mở, nhưng vẫn cần validate.
- Search query hoặc filter expression nếu contract định nghĩa cú pháp rõ.

Ngay cả khi dùng string, semantics vẫn phải rõ:

- Giới hạn độ dài và encoding.
- Quy định trim/case sensitivity/normalization.
- Phân biệt empty với absent nếu cần.
- Validate format và namespace.
- Không dùng display label làm identifier ổn định.
- Không dùng chuỗi dịch theo ngôn ngữ làm giá trị máy đọc.

Ví dụ "Đã xác nhận" là nhãn hiển thị, không nên là giá trị trạng thái trong contract. Dùng enum ổn định rồi client tự dịch nhãn theo locale.

## 7. Dùng message cho dữ liệu có cấu trúc

Một string như "12.50 USD" gộp số tiền và đơn vị vào một chuỗi. Client phải parse, xử lý dấu thập phân, locale và quy tắc làm tròn. Một message thể hiện rõ từng phần:

```proto
message Money {
  string currency_code = 1;
  int64 units = 2;
  int32 nanos = 3;
}

message InvoiceReply {
  string invoice_id = 1;
  Money total = 2;
}
```

Message Money cho phép validate currency code, units và nanos riêng. Không dùng float/double cho số tiền cần chính xác thập phân. Semantics của units/nanos phải được định nghĩa nhất quán, gồm quy tắc dấu và độ chính xác.

Tương tự, không gộp địa chỉ thành một string phân tách bằng dấu phẩy nếu client/server cần thao tác từng thành phần. Dùng Address message với street, locality, region, postal_code và country_code.

## 8. Dùng message chuẩn cho thời gian và thời lượng

Không truyền timestamp dưới dạng string tự định nghĩa như "19/11/2026 10:30". Chuỗi có thể mơ hồ về timezone, locale và format.

Dùng các kiểu chuẩn:

```proto
import "google/protobuf/timestamp.proto";
import "google/protobuf/duration.proto";

message Reservation {
  string reservation_id = 1;
  google.protobuf.Timestamp starts_at = 2;
  google.protobuf.Duration duration = 3;
}
```

Timestamp biểu diễn một instant; Duration biểu diễn khoảng thời gian. Server vẫn cần validate range và semantics nghiệp vụ, ví dụ thời gian bắt đầu không ở quá xa trong quá khứ hoặc duration không vượt giới hạn booking.

Không dùng string cho dữ liệu có kiểu chuẩn chỉ vì muốn dễ đọc trong JSON. Protobuf JSON mapping đã định nghĩa representation cho Timestamp và Duration.

## 9. Dùng oneof khi các lựa chọn có payload khác nhau

Enum chỉ biểu diễn nhãn. Nếu mỗi lựa chọn cần dữ liệu riêng, dùng oneof với message tương ứng:

```proto
message CardPayment {
  string payment_token = 1;
}

message BankTransfer {
  string bank_account_reference = 1;
}

message WalletPayment {
  string wallet_provider = 1;
  string wallet_reference = 2;
}

message PaymentMethod {
  oneof method {
    CardPayment card = 1;
    BankTransfer bank_transfer = 2;
    WalletPayment wallet = 3;
  }
}
```

Nếu dùng string type = "CARD" cùng một payload JSON tự do, server phải tự parse và kiểm tra tổ hợp field; compiler không biết payload nào phù hợp với loại nào. oneof làm lựa chọn được biểu diễn trong schema và generated API.

Server vẫn cần kiểm tra trường hợp oneof không có member nào được chọn và validate payload của member đã chọn. Khi thêm member mới, client cũ cần có policy cho lựa chọn chưa biết.

Không dùng oneof cho các field có thể đồng thời tồn tại. Chọn cấu trúc dựa trên semantics thực tế.

## 10. Không nhét JSON vào string để né schema

Một anti-pattern khác là định nghĩa:

```proto
message Event {
  string type = 1;
  string payload_json = 2;
}
```

Cách này biến Protobuf thành một lớp envelope mỏng; payload thực tế không có schema Protobuf. Hệ quả:

- Compiler không sinh kiểu cho payload.
- Sai tên field hoặc sai kiểu chỉ phát hiện lúc runtime.
- Client phải tự parse JSON và quản lý version.
- Validation và field presence bị phân tán.
- Schema registry/tooling Protobuf không kiểm tra được nội dung payload.
- Log/metrics khó phân tích và dễ lộ dữ liệu nhạy cảm.

Nếu event có các loại payload đã biết, dùng oneof với message cụ thể. Nếu thực sự cần payload động theo type URL, cân nhắc google.protobuf.Any với type registry và policy versioning rõ ràng. Any không phải nơi chứa JSON tùy tiện và vẫn yêu cầu client/server hiểu type được đóng gói.

## 11. Enum trong request cần validate ở server

Một enum field có thể nhận giá trị mặc định *_UNSPECIFIED hoặc numeric value chưa biết. Server không nên mặc định coi mọi giá trị khác 0 là hợp lệ.

Ví dụ:

```java
public void validate(CreateOrderRequest request) {
    OrderPriority priority = request.getPriority();

    if (priority == OrderPriority.UNRECOGNIZED) {
        throw new RequestValidationException(
            "priority contains an unsupported value"
        );
    }

    if (priority == OrderPriority.ORDER_PRIORITY_UNSPECIFIED) {
        throw new RequestValidationException(
            "priority must be specified"
        );
    }
}
```

Map validation exception sang INVALID_ARGUMENT ở biên gRPC. Không đưa numeric value không được hỗ trợ vào switch mà thiếu default/UNRECOGNIZED handling.

Nếu server cần forward một enum value chưa hiểu qua service khác, giữ numeric value thay vì chuyển qua enum domain rồi làm mất giá trị. Chỉ forward khi contract cho phép và không thực hiện side effect dựa trên semantics chưa hiểu.

## 12. Field presence: string rỗng không luôn giống absent

Trong proto3, scalar field dùng implicit presence thường trả default value khi field không được gửi. Với string, getter trả chuỗi rỗng; với enum, getter trả giá trị số 0.

Nếu API cần phân biệt “caller không gửi field” với “caller gửi giá trị rỗng/default”, hãy dùng optional hoặc message wrapper phù hợp:

```proto
message UpdateCustomerRequest {
  string customer_id = 1;
  optional string display_name = 2;
}
```

Server có thể kiểm tra hasDisplayName():

- Absent: giữ nguyên tên hiện tại.
- Present nhưng empty: xóa tên nếu contract cho phép.
- Present có giá trị: cập nhật tên.

Với enum, optional có thể cần thiết nếu absent có semantics khác với *_UNSPECIFIED. Message field có presence theo Protobuf semantics; hãy định nghĩa rõ hành vi patch/update.

Không tự diễn giải empty string thành “không thay đổi” nếu contract không nói vậy.

## 13. Validation, default và business semantics

Kiểu dữ liệu rõ không loại bỏ validation. Enum vẫn có thể là UNSPECIFIED hoặc UNRECOGNIZED; message vẫn có thể thiếu field bắt buộc theo nghiệp vụ; string vẫn có thể sai format.

Tách các lớp:

- **Schema type:** Protobuf đảm bảo dữ liệu có dạng string, enum hoặc message.
- **Structural validation:** kiểm tra presence, length, range và tổ hợp field.
- **Domain validation:** kiểm tra giá trị có ý nghĩa trong nghiệp vụ.
- **Authorization:** kiểm tra caller có quyền sử dụng lựa chọn/tài nguyên đó.

Ví dụ payment method có thể hợp lệ về schema nhưng tenant không được bật wallet provider đó. Đây là business precondition hoặc permission policy, không phải lỗi parse Protobuf.

Không dùng enum như một danh sách quyền truy cập thay cho authorization. Giá trị enum mô tả lựa chọn, còn quyền được phép dùng lựa chọn cần kiểm tra ở server.

## 14. Tiến hóa schema an toàn

Khi thay string bằng enum/message, cần xem đây là thay đổi contract:

1. Xác định semantics và các giá trị string đang được sử dụng thực tế.
2. Chuẩn hóa các alias/case/typo trước khi chọn enum values.
3. Chọn tên và số enum ổn định; dành số 0 cho UNSPECIFIED.
4. Thêm field mới với field number mới, giữ field cũ trong giai đoạn chuyển đổi.
5. Server có thể đọc cả field cũ và mới trong thời gian migration, với quy tắc ưu tiên rõ ràng.
6. Client chuyển sang field mới theo từng đợt.
7. Theo dõi usage của field cũ và unknown enum values.
8. Chỉ deprecate/remove field cũ khi mọi consumer đã chuyển.
9. Khi xóa field/enum value, reserve field number/name và enum number/name tương ứng.

Không đổi kiểu của một field đang dùng tại cùng field number từ string sang enum/message. Binary wire type hoặc semantics sẽ không còn tương thích; hãy thêm field mới hoặc version API.

Tên enum có thể được serialize trong ProtoJSON, nên rename cũng cần migration và compatibility review.

## 15. Kiểm thử contract và generated Java

Các test nên bao gồm:

| Kịch bản | Điều cần xác nhận |
| --- | --- |
| Enum value đã biết | Client/server hiểu đúng semantics |
| Enum UNSPECIFIED | Server từ chối hoặc xử lý theo default contract |
| Numeric enum value chưa biết | Client không crash; server xử lý theo policy |
| Enum number bị xóa | Không tái sử dụng số cũ; reserved được khai báo |
| String sai chính tả | Validation phát hiện nếu field có vocabulary đóng |
| Message thiếu field cần thiết | Structural/domain validation đúng |
| oneof không chọn member | Server xử lý trường hợp absent |
| oneof có member mới | Client cũ có fallback an toàn |
| ProtoJSON enum name đổi | Kiểm tra tương thích JSON consumer |
| Field cũ và field mới cùng có | Migration precedence nhất quán |
| Unknown field được forward | Giá trị không bị mất nếu proxy cần bảo toàn |

Test qua gRPC server thật để kiểm tra status và generated code behavior. Thêm schema compatibility check trong CI để ngăn đổi field number, tái sử dụng enum number hoặc thay đổi wire type không tương thích.

## 16. Checklist review

- String chỉ dùng cho free text, identifier hoặc vocabulary mở có lý do rõ.
- Tập lựa chọn hữu hạn do API quản lý được biểu diễn bằng enum.
- Dữ liệu nhiều thành phần/typed structure được biểu diễn bằng message.
- Các biến thể payload loại trừ nhau dùng oneof khi phù hợp.
- Enum số 0 là *_UNSPECIFIED hoặc default an toàn.
- Enum number đã phát hành không bị đổi hoặc tái sử dụng.
- Khi xóa enum value, reserve cả number và name.
- Client xử lý UNRECOGNIZED/unknown enum values.
- Server validate enum request và không chấp nhận UNSPECIFIED tùy tiện.
- Không dùng string JSON làm payload thay schema nếu payload có cấu trúc ổn định.
- Dùng Timestamp/Duration và kiểu chuẩn khi semantics phù hợp.
- Field presence/default semantics được định nghĩa cho update/patch.
- Migration không đổi kiểu field tại cùng field number.
- Có binary/ProtoJSON compatibility tests và generated Java tests.

Trong **SPRING_GRPC**, string tự do cho mọi loại dữ liệu làm contract mất vocabulary, cấu trúc và khả năng kiểm tra sớm. Dùng enum cho tập lựa chọn hữu hạn, message cho dữ liệu có cấu trúc và string cho văn bản/identifier hoặc giá trị mở thực sự. Kết hợp presence, validation và quy tắc tiến hóa Protobuf để client/server hiểu cùng một semantics qua nhiều phiên bản.
