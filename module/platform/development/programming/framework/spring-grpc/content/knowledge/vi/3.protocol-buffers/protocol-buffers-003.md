# Field number và wire compatibility

## Mục tiêu học tập

Sau bài học này, bạn có thể:

- Giải thích vì sao **field number** là danh tính của một trường dữ liệu trong bản mã hóa Protocol Buffers, và cách **wire type** tham gia tạo tag.
- Đọc các ví dụ byte cơ bản để phân biệt số hiệu field, kiểu mã hóa, độ dài và giá trị.
- Đánh giá khả năng tương thích giữa phiên bản client/server gRPC khi thêm, xóa, đổi tên, đổi kiểu hoặc thay đổi cách nhóm field.
- Sử dụng **reserved** và chiến lược triển khai nhiều phiên bản để tránh hiểu sai dữ liệu cũ.
- Thiết kế phép thử cho hợp đồng proto3 trong hệ sinh thái Spring gRPC, bao gồm dữ liệu nhị phân và trường hợp chuyển qua JSON.

## 1. Vì sao field number quan trọng trong Spring gRPC?

Trong **SPRING_GRPC**, một tệp **.proto** là hợp đồng dùng chung giữa client và server. Công cụ **protoc** sinh các lớp message Java; plugin gRPC sinh stub và lớp cơ sở cho RPC unary hoặc streaming. Ứng dụng Spring gọi các phương thức của lớp Java đã sinh, còn gRPC truyền dữ liệu đã mã hóa bằng Protocol Buffers.

Xét một message:

~~~proto
syntax = "proto3";

message Order {
  string order_id = 1;
  int64 total_cents = 2;
  string note = 3;
}
~~~

Mỗi field có ba thành phần: **kiểu** (ví dụ **string**), **tên** (ví dụ **order_id**) và **số hiệu** (ví dụ **1**). Tên hỗ trợ việc đọc schema và tạo phương thức Java như **getOrderId()**; số hiệu là thành phần xác định field trên đường truyền nhị phân. Vì vậy, đổi tên và đổi số hiệu không có cùng hậu quả.

Trong thực tế, không thể giả định mọi ứng dụng đang chạy cùng một phiên bản hợp đồng: ứng dụng di động có thể cập nhật chậm, nhiều instance Spring Boot có thể được triển khai lần lượt, và dữ liệu Protobuf có thể được lưu để đọc lại sau. **Wire compatibility** là khả năng một bên đọc đúng các byte được mã hóa bởi phiên bản schema khác, trong giới hạn của quy tắc mã hóa Protobuf.

Tương thích ở mức byte là điều kiện quan trọng nhưng **chưa đủ**: một message vẫn có thể giải mã thành công trong khi logic nghiệp vụ hiểu sai, ví dụ đổi đơn vị tiền từ **cents** sang **đồng** mà giữ cùng field.

## 2. Tag được tạo từ field number và wire type

Trong định dạng nhị phân Protobuf, mỗi trường được mã hóa bằng một **tag** và phần dữ liệu tương ứng. Tag là một số nguyên varint với công thức:

~~~text
tag = (field_number << 3) | wire_type

field_number = tag >> 3
wire_type    = tag & 0b111
~~~

Ba bit thấp của tag xác định **wire type**; các bit còn lại xác định **field number**. Wire type mô tả cách đọc các byte tiếp theo, không mô tả đầy đủ kiểu logic trong tệp .proto.

| Wire type | Số | Dữ liệu thường gặp | Cách đọc |
| --- | ---: | --- | --- |
| **VARINT** | **0** | **int32**, **int64**, **uint32**, **uint64**, **sint32**, **sint64**, **bool**, enum | Số nguyên có độ dài biến thiên |
| **I64** | **1** | **fixed64**, **sfixed64**, **double** | Chính xác 8 byte |
| **LEN** | **2** | **string**, **bytes**, message lồng nhau, các phần tử scalar **repeated** được packed | Đọc độ dài dạng varint rồi đọc số byte tương ứng |
| **I32** | **5** | **fixed32**, **sfixed32**, **float** | Chính xác 4 byte |

Wire type **3** và **4** là start/end group từ cơ chế group cũ; không nên dùng group khi thiết kế schema proto3 mới. Wire type không phản ánh việc một field được khai báo là **optional**, có tên gì, hoặc có ngữ nghĩa nghiệp vụ ra sao.

Ví dụ:

~~~proto
message Example {
  int32 count = 1;
  string label = 2;
}
~~~

Khi **count = 7** và **label = "A"**, một bản mã hóa nhị phân là:

~~~text
08 07 12 01 41
|  |  |  |  |
|  |  |  |  +-- Ký tự ASCII "A" (0x41)
|  |  |  +----- Độ dài string: 1 byte
|  |  +-------- Tag 0x12 = 18 = (2 << 3) | 2
|  +----------- Giá trị count: 7
+-------------- Tag 0x08 = 8 = (1 << 3) | 0
~~~

Nếu chuyển **label** từ field số **2** sang số **16**, tag của string trở thành **0x82 0x01** thay cho **0x12**:

~~~text
// label = "A" tại field số 2
12 01 41

// label = "A" tại field số 16
82 01 01 41
~~~

Hai trường có thể cùng tên và cùng kiểu **string** nhưng phía đọc vẫn xem là **hai field khác nhau** vì khác số hiệu. Phần giá trị giống nhau không làm chúng trở nên tương thích.

### Varint là gì?

Varint mã hóa số nguyên theo từng nhóm 7 bit hữu ích; bit cao của mỗi byte báo còn byte tiếp theo hay không. Số nhỏ thường tốn ít byte. Đây là cách mã hóa cả tag lẫn giá trị của các trường số nguyên thuộc wire type 0.

Kích thước của **tag** phụ thuộc vào field number:

| Field number | Kích thước tag thông thường |
| --- | --- |
| **1–15** | 1 byte |
| **16–2047** | 2 byte |
| **2048** trở lên | 3 byte trở lên |

Vì vậy, nên ưu tiên số **1–15** cho những field xuất hiện thường xuyên, nhất là trong message gửi nhiều lần qua streaming RPC. Tuy nhiên, đây là tối ưu về **tag**, không phải bảo đảm toàn bộ field chỉ tốn một byte. Giá trị và độ dài của nó vẫn chiếm thêm byte; chỉ tối ưu khi cần thiết và có số liệu.

## 3. Quy tắc cấp số hiệu field

Khi đặt số hiệu trong proto3, cần tuân thủ:

1. **Số hiệu hợp lệ:** từ **1** đến **536.870.911** (tức **2²⁹ − 1**), ngoại trừ dải **19.000–19.999** do Protobuf dành riêng. **0**, số âm và số vượt giới hạn đều không hợp lệ.
2. **Duy nhất trong cùng message:** không được định nghĩa hai field có cùng số hiệu trong một message, kể cả hai field thuộc các **oneof** khác nhau. Message khác có không gian số hiệu riêng.
3. **Ổn định suốt vòng đời hợp đồng:** sau khi có client, server hoặc dữ liệu lưu trữ sử dụng field, giữ nguyên số hiệu đó cho cùng ý nghĩa.
4. **Không tái sử dụng số hiệu đã ngừng dùng:** đánh dấu số cũ bằng **reserved**. Có thể dành riêng cả tên cũ để công cụ biên dịch báo lỗi nếu sau này ai đó tạo field trùng tên.
5. **Không dựa vào thứ tự khai báo:** field số **10** có thể được viết trước field số **2** trong file .proto; số hiệu, chứ không phải vị trí trên dòng, quyết định danh tính wire.

Ví dụ không hợp lệ:

~~~proto
message InvalidOrder {
  string id = 1;
  int64 amount = 1;    // Lỗi: trùng field number
  string memo = 19000; // Lỗi: số thuộc khoảng dành riêng
}
~~~

Ví dụ hợp lệ có chừa số cho tương lai:

~~~proto
message Order {
  string id = 1;
  int64 amount_cents = 2;
  string note = 10;
  reserved 3, 4, 6 to 9;
  reserved "old_note";
}
~~~

Giả định rằng các số và tên trong **reserved** ở ví dụ này từng được sử dụng. Với một hợp đồng mới, không cần đặt **reserved** tùy tiện khi chưa có lịch sử dữ liệu hoặc nhu cầu chặn tái sử dụng cụ thể.

## 4. Hai phiên bản của hợp đồng Order

Giả sử dịch vụ đơn hàng có RPC unary **GetOrder**. Bản **v1** đã được nhiều client sử dụng:

~~~proto
// order.proto — phiên bản v1
syntax = "proto3";

package learning.orders.v1;
option java_package = "com.example.orders.v1";
option java_multiple_files = true;

enum OrderStatus {
  ORDER_STATUS_UNSPECIFIED = 0;
  ORDER_STATUS_PENDING = 1;
  ORDER_STATUS_PAID = 2;
}

message Order {
  string order_id = 1;
  int64 total_cents = 2;
  OrderStatus status = 3;
  string legacy_coupon = 4;
}

message GetOrderRequest {
  string order_id = 1;
}

service OrderService {
  rpc GetOrder(GetOrderRequest) returns (Order);
}
~~~

Sau đó hệ thống ngừng sử dụng mã coupon cũ và bổ sung một ghi chú có thể cập nhật. Bản **v2** giữ nguyên các field hiện có và thêm field mới:

~~~proto
// order.proto — phiên bản v2; biên dịch riêng với v1
syntax = "proto3";

package learning.orders.v1;
option java_package = "com.example.orders.v1";
option java_multiple_files = true;

enum OrderStatus {
  ORDER_STATUS_UNSPECIFIED = 0;
  ORDER_STATUS_PENDING = 1;
  ORDER_STATUS_PAID = 2;
}

message Order {
  string order_id = 1;
  int64 total_cents = 2;
  OrderStatus status = 3;

  reserved 4;
  reserved "legacy_coupon";

  optional string customer_note = 5;
}

message GetOrderRequest {
  string order_id = 1;
}

service OrderService {
  rpc GetOrder(GetOrderRequest) returns (Order);
}
~~~

Hai phiên bản minh họa thay đổi **cùng một hợp đồng** theo thời gian, nên không được biên dịch đồng thời hai tệp có cùng tên định danh Protobuf và package trong một lần sinh mã. Trong một hệ thống thực tế, mỗi phiên bản binary client/server sẽ được biên dịch với schema tương ứng của phiên bản đó.

Thay đổi chính:

- **order_id = 1**, **total_cents = 2**, **status = 3** giữ nguyên số hiệu, kiểu và ý nghĩa.
- **legacy_coupon = 4** không còn được viết trong v2; cả số **4** và tên **legacy_coupon** được **reserved** để ngăn lập trình viên sử dụng lại.
- **customer_note = 5** là trường mới, dùng **optional** để phân biệt không gửi ghi chú với chủ đích gửi ghi chú rỗng.

Lưu ý: **reserved** chỉ cấm khai báo lại field trong schema mới. Nó **không** ngăn phiên bản client cũ tiếp tục gửi field 4 trên đường truyền.

## 5. Backward compatibility và forward compatibility

Hai hướng kiểm tra thường được dùng như sau:

- **Backward compatibility:** bộ đọc **mới** vẫn đọc đúng dữ liệu do phiên bản **cũ** tạo.
- **Forward compatibility:** bộ đọc **cũ** vẫn xử lý hợp lý dữ liệu do phiên bản **mới** tạo.

Một số tài liệu dùng tên gọi theo góc nhìn khác nhau; khi trao đổi trong nhóm, nên nói rõ **ai ghi và ai đọc** thay vì chỉ nêu thuật ngữ.

Với ví dụ Order:

| Bên gửi | Bên nhận | Hiện tượng ở mức Protobuf nhị phân |
| --- | --- | --- |
| v1 | v1 | Các field 1–4 được đọc theo schema v1. |
| v1 | v2 | v2 đọc 1–3; field 4 trở thành **unknown field** do đã bị loại khỏi schema v2. |
| v2 | v1 | v1 đọc 1–3; field 5 là **unknown field** vì v1 chưa biết **customer_note**. |
| v2 | v2 | v2 đọc 1–3 và có thể nhận biết presence của **customer_note = 5**. |

**Unknown field** không có nghĩa là dữ liệu nhị phân chắc chắn bị mất ngay lúc parse. Trong runtime Protobuf Java thông thường, unknown fields có thể được giữ lại trong đối tượng message và được ghi ra lại khi serialize nhị phân. Tuy nhiên, mã ứng dụng v1 **không thể truy cập field 5 qua getter được sinh**, và nếu dữ liệu đi qua chuyển đổi sang JSON, mapping DTO hoặc tái tạo message thủ công, unknown fields có thể bị loại bỏ.

Vì vậy, thêm field mới thường **tương thích về cấu trúc wire**, nhưng **không đảm bảo** client cũ nhìn thấy hoặc xử lý đúng thông tin mới.

### Trường mới không tự động là trường bắt buộc

Nếu server v2 bắt đầu yêu cầu mọi client phải gửi **customer_note**, các client v1 sẽ không thể đáp ứng và có thể nhận lỗi nghiệp vụ, mặc dù việc parse request vẫn thành công. Proto3 không hỗ trợ nhãn **required**; quy tắc bắt buộc phải được quản lý ở tầng nghiệp vụ với kế hoạch nâng cấp client.

Trong Spring gRPC, lỗi kiểm tra dữ liệu có thể trả về trạng thái **INVALID_ARGUMENT**. Trạng thái RPC này mô tả kết quả xử lý, còn **wire compatibility** mô tả khả năng giải mã request/response; hai vấn đề cần kiểm tra riêng.

## 6. Thay đổi nào an toàn, thay đổi nào rủi ro?

| Thay đổi schema | Đánh giá | Giải thích |
| --- | --- | --- |
| Thêm field mới bằng **số chưa dùng** | Thường an toàn ở mức wire | Bộ đọc cũ bỏ qua field chưa biết; bộ đọc mới phải chấp nhận field vắng mặt. |
| Xóa field và **reserved** số/tên | Có thể tương thích wire | Bản mới không diễn giải dữ liệu cũ theo nghĩa mới; vẫn cần xem có nghiệp vụ còn phụ thuộc field đã bỏ hay không. |
| Đổi **tên field**, giữ số và kiểu | Thường giữ tương thích nhị phân | Có thể phá mã nguồn Java, tên trong Protobuf JSON và hệ thống dùng reflection/schema. |
| Đổi **field number** | **Không an toàn** | Đối tác cũ và mới nhận diện thành hai field khác nhau. |
| Tái sử dụng số hiệu đã xóa | **Không an toàn** | Byte dữ liệu cũ có thể bị diễn giải theo ý nghĩa mới. |
| Đổi **int32** sang **int64** | Có thể đọc cùng kiểu wire, nhưng cần giới hạn giá trị | Đều dùng varint, song reader cũ có thể nhận giá trị ngoài dải **int32** và bị cắt/tràn. |
| Đổi **int32** sang **sint32** | **Không an toàn về giá trị** | Dù cùng wire type 0, **sint32** dùng mã hóa ZigZag nên cùng byte biểu diễn số khác. |
| Đổi **string** sang **bytes** | Không được coi mặc nhiên an toàn | Đều wire type 2, nhưng cách diễn giải UTF-8 và dữ liệu nhị phân khác nhau; có thể phá parser/logic. |
| Đổi **float** sang **fixed32** | **Không an toàn về ngữ nghĩa** | Đều wire type 5 nhưng biểu diễn giá trị khác nhau. |
| Thêm giá trị **enum** | Thường tương thích wire, có rủi ro nghiệp vụ | Client cũ có thể không biết giá trị số mới; phải xử lý giá trị chưa nhận diện. |
| Chuyển nhiều field hiện có vào một **oneof** | Rủi ro | Message cũ có thể đồng thời chứa các field; oneof chỉ giữ một lựa chọn. |
| Thay **repeated** thành singular hoặc ngược lại | Cần đánh giá cụ thể; thường tránh | Thay đổi số lượng giá trị và hành vi gộp, ngay cả khi một số trường hợp dùng cùng wire type. |
| Thay đổi đơn vị hoặc ý nghĩa field | **Không an toàn về nghiệp vụ** | Mã hóa vẫn đọc được nhưng dữ liệu bị hiểu sai. |

Tránh suy luận rằng **hai kiểu có cùng wire type** đương nhiên thay thế được cho nhau. Ví dụ, chuỗi ký tự UTF-8, dãy byte tùy ý, message lồng nhau và danh sách số được packed đều sử dụng wire type **2**, nhưng nội dung của chúng được giải mã theo các quy tắc rất khác.

### Enum mở trong proto3

Ví dụ v3 bổ sung:

~~~proto
enum OrderStatus {
  ORDER_STATUS_UNSPECIFIED = 0;
  ORDER_STATUS_PENDING = 1;
  ORDER_STATUS_PAID = 2;
  ORDER_STATUS_REFUNDED = 3;
}
~~~

Một runtime Java proto3 cũ có thể giữ nguyên số **3** qua **getStatusValue()**, còn **getStatus()** trả **UNRECOGNIZED** nếu enum Java cũ chưa khai báo thành viên ấy. Mã nghiệp vụ cần xử lý trường hợp không nhận diện, thay vì giả định chỉ có **PENDING** và **PAID**.

Không tái sử dụng số enum đã ngừng dùng; có thể dùng **reserved** trong định nghĩa enum. Giá trị enum **0** nên mang nghĩa **UNSPECIFIED/UNKNOWN**, vì đó là giá trị mặc định của field enum proto3 không có explicit presence.

## 7. Field presence cũng ảnh hưởng đến hành vi tương thích

Trong proto3, field scalar thông thường có **implicit presence**: từ góc nhìn getter, không thể phân biệt field chưa được gửi và field được đặt bằng giá trị mặc định. Ví dụ **string note = 3;** trả về **""** trong cả hai trường hợp.

Với:

~~~proto
optional string customer_note = 5;
~~~

Java được sinh có **hasCustomerNote()** để kiểm tra sự hiện diện. Hai message sau khác nhau về thông tin presence:

~~~java
Order withoutNote = Order.newBuilder()
    .setOrderId("o-42")
    .build();

Order withEmptyNote = Order.newBuilder()
    .setOrderId("o-42")
    .setCustomerNote("")
    .build();

System.out.println(withoutNote.hasCustomerNote());   // false
System.out.println(withEmptyNote.hasCustomerNote()); // true
System.out.println(withEmptyNote.getCustomerNote()); // ""
~~~

Ở bản mã hóa nhị phân, field string **optional** số **5** được thiết lập thành chuỗi rỗng vẫn có thể hiện diện bằng tag **0x2A** (field 5, wire type 2) và độ dài **0x00**:

~~~text
2A 00
|  |
|  +-- Độ dài dữ liệu chuỗi: 0
+----- Tag: (5 << 3) | 2 = 42 = 0x2A
~~~

Nếu không set field, hai byte trên không xuất hiện. **Đừng xem giá trị mặc định là bằng chứng field đã được gửi.** Với cập nhật từng phần, hãy dùng explicit presence hoặc **google.protobuf.FieldMask**, kèm quy tắc rõ ràng để phân biệt "không cập nhật" và "xóa giá trị".

Đổi một scalar giữa implicit và explicit presence có thể không đổi wire type nhưng vẫn đổi cách merge/serialize và logic cập nhật của ứng dụng. Vì vậy cần thử nghiệm cả trường hợp giá trị mặc định.

## 8. Trường repeated và packed encoding

Proto3 mặc định **packed** cho các kiểu **repeated scalar có thể đóng gói** như **int32**, **bool**, **enum**, **float**. Với field:

~~~proto
message Basket {
  repeated int32 quantities = 3;
}
~~~

Giả sử danh sách là **[1, 2]**:

~~~text
Không packed:
18 01 18 02
|     |
+-----+-- Cùng tag 0x18 = (3 << 3) | 0 cho mỗi giá trị

Packed (mặc định trong proto3):
1A 02 01 02
|  |  |  |
|  |  +--+-- Hai giá trị varint 1 và 2
|  +-------- Độ dài payload: 2
+----------- Tag 0x1A = (3 << 3) | 2
~~~

Các parser Protobuf tuân thủ chuẩn nhận được cả biểu diễn **packed** và **unpacked** cho repeated field thuộc nhóm kiểu có thể đóng gói. Có thể yêu cầu bộ phát sinh mã viết dạng unpacked bằng **[packed = false]**:

~~~proto
repeated int32 quantities = 3 [packed = false];
~~~

Tính linh hoạt này **không** có nghĩa là tùy ý đổi **repeated** thành **singular**: singular chỉ đại diện một giá trị; thông tin nhiều phần tử sẽ không còn được hiểu như ban đầu. **string**, **bytes**, message và map không thuộc nhóm scalar packable.

## 9. Xóa field bằng reserved và quản lý lịch sử

Giả sử phiên bản cũ dùng:

~~~proto
string legacy_coupon = 4;
~~~

Có thể đi qua một giai đoạn chuyển tiếp khi field vẫn tồn tại nhưng không nên được dùng tiếp:

~~~proto
string legacy_coupon = 4 [deprecated = true];
~~~

Tùy bộ sinh mã, nhãn **deprecated** giúp cảnh báo người dùng API; nó **không** làm field biến mất khỏi định dạng wire. Sau khi bỏ logic phụ thuộc, phiên bản mới chuyển sang:

~~~proto
reserved 4;
reserved "legacy_coupon";
~~~

Ý nghĩa của hai dòng này khác nhau:

- **reserved 4;** bảo vệ danh tính nhị phân **4**, ngăn một người khác khai báo field mới dùng lại số đó.
- **reserved "legacy_coupon";** ngăn khai báo lại cùng tên trong schema. Tên field không được mã hóa vào wire binary; giữ tên giúp ngăn nhầm lẫn khi phát triển.

Nếu xóa nhiều field, cú pháp có thể gộp số/range:

~~~proto
reserved 4, 7, 10 to 12;
reserved "legacy_coupon", "old_reference";
~~~

Chỉ dùng các số/tên tương ứng với lịch sử thực tế của message. **reserved** thuộc về từng message, không tự động áp dụng cho message khác.

Với dữ liệu lưu trữ lâu dài, phải giữ lịch sử schema đủ để biết từng số hiệu từng mang ý nghĩa gì. Sau nhiều năm, một field đã không còn xuất hiện trong mã nguồn hiện tại vẫn có thể tồn tại trong byte lưu trữ, bản sao lưu hoặc client chưa nâng cấp.

## 10. Mã Java sinh ra và khả năng bảo toàn unknown fields

Từ schema v2, **protoc** tạo lớp **Order** trong package **com.example.orders.v1**. Ví dụ mã phía ứng dụng:

~~~java
import com.example.orders.v1.Order;
import com.example.orders.v1.OrderStatus;

Order source = Order.newBuilder()
    .setOrderId("o-42")
    .setTotalCents(12500L)
    .setStatus(OrderStatus.ORDER_STATUS_PAID)
    .setCustomerNote("")
    .build();

byte[] bytes = source.toByteArray();
Order decoded = Order.parseFrom(bytes);

System.out.println(decoded.getOrderId());        // o-42
System.out.println(decoded.getTotalCents());     // 12500
System.out.println(decoded.hasCustomerNote());   // true
System.out.println(decoded.getCustomerNote());   // ""
~~~

Khi một chương trình Java biên dịch bằng **v1** đọc message có field **5** do v2 gửi, nó không có getter **getCustomerNote()**. Nếu dùng runtime Protobuf Java thông thường, có thể kiểm tra dữ liệu chưa biết bằng **getUnknownFields()**:

~~~java
// Ví dụ khái niệm: biến orderV1 là Order sinh từ schema v1.
boolean hasUnknownField5 =
    orderV1.getUnknownFields().asMap().containsKey(5);
~~~

Đoạn trên cần chạy với class **Order v1** và một payload thực sự chứa field 5; không thể chạy đồng thời hai bản class cùng tên/package của v1 và v2 trong một module Java đơn giản. Khi tạo lại message từ đầu bằng builder mới, chỉ copy những field đã biết, hoặc chuyển qua JSON, unknown fields có thể bị bỏ. Do đó, một proxy đọc rồi ghi lại Protobuf không nhất thiết giữ được mọi dữ liệu của phiên bản mới trong tất cả luồng xử lý.

Để kiểm chứng thực tế, cần dựng **hai phiên bản client/server độc lập** hoặc hai bộ sinh mã trong module/package thử nghiệm riêng, trao đổi payload giữa chúng rồi so sánh. Không nên chỉ serialize và parse bằng cùng một phiên bản để tuyên bố schema tương thích.

## 11. Binary wire, JSON và API Java là ba lớp khác nhau

Giao thức gRPC thường truyền Protobuf nhị phân. Nhưng hệ thống thực có thể thêm REST gateway, logging JSON hoặc dữ liệu lưu trữ ngoài:

| Lớp giao tiếp | Điều quyết định tương thích |
| --- | --- |
| **Protobuf binary** | Field number, wire type, quy tắc giải mã và ngữ nghĩa field |
| **Protobuf JSON** | Tên field/JSON name, cách biểu diễn số, enum, default/presence và chính sách xử lý unknown fields |
| **API Java được sinh** | Package, tên message, enum, tên field và các getter/setter/builder method |
| **Nghiệp vụ** | Đơn vị đo, điều kiện bắt buộc, giá trị mặc định, các trạng thái mới, ý nghĩa của field |

Ví dụ đổi **order_id** thành **id** nhưng giữ **= 1** và kiểu **string** thường vẫn đọc được payload binary cũ. Tuy nhiên, Java đổi **getOrderId()** thành **getId()** và Protobuf JSON mặc định đổi tên thuộc tính từ **orderId** thành **id** nếu không có cấu hình tên JSON riêng. Code Java cũ không còn biên dịch khi cập nhật lớp sinh mã; JSON consumer cũng có thể không nhận đúng thuộc tính.

Tương tự, thêm enum mới có thể làm nhánh **switch** trong code nghiệp vụ không xử lý được trạng thái lạ, dù parser nhị phân giữ lại số. Việc cập nhật hợp đồng cần được đánh giá trên đúng các đường dữ liệu mà hệ thống sử dụng.

## 12. Quy trình thay đổi hợp đồng khi deploy Spring gRPC

Một quy trình thực tế cho thay đổi từ v1 sang v2:

1. **Kiểm tra field đã dùng:** xác định số hiệu, kiểu, tên, ý nghĩa và dữ liệu lưu trữ. Với field ngừng dùng, ghi nhận lịch sử trước khi đánh dấu **reserved**.
2. **Bổ sung field mới:** chọn số hiệu chưa dùng (ví dụ **5**), loại field và presence phù hợp. Không đổi các field 1–3 chỉ vì muốn sắp xếp đẹp lại schema.
3. **Sinh mã độc lập và kiểm tra:** biên dịch .proto và lớp Java tại mỗi phiên bản; xác nhận code client/server dùng đúng kiểu mới. Tránh đóng gói hai định nghĩa cùng full name trong một binary.
4. **Đánh giá cả hai hướng giao tiếp:** đưa payload từ v1 sang reader v2 và từ v2 sang reader v1; kiểm tra giá trị đọc được, unknown fields và phản ứng của code nghiệp vụ.
5. **Triển khai theo mức độ phụ thuộc:** thường cập nhật bên đọc trước khi bên gửi bắt đầu phụ thuộc vào trường mới, đồng thời tiếp tục hỗ trợ request từ client cũ. Với rolling deployment, thử nghiệm khi hai phiên bản instance cùng tồn tại.
6. **Giám sát sau triển khai:** ghi nhận lỗi RPC **INVALID_ARGUMENT**, **INTERNAL**, lỗi parse, tỷ lệ request thất bại, độ trễ và tỷ lệ client theo phiên bản. Lưu ý metadata, deadline, TLS và interceptor thuộc tầng vận hành/cơ chế RPC khác, nhưng vẫn ảnh hưởng đến khả năng chẩn đoán sự cố.
7. **Chỉ gỡ logic cũ khi đủ điều kiện:** đánh giá client còn hoạt động, dữ liệu lưu trữ lâu dài và khả năng rollback. Luôn giữ số hiệu cũ trong **reserved**.

Nếu thay đổi cần một đơn vị dữ liệu hoặc ngữ nghĩa mới hoàn toàn, có thể tạo **field mới với số mới**, chuyển đổi dữ liệu trong giai đoạn quá độ rồi ngừng dùng field cũ. Với thay đổi lớn trên nhiều RPC, cân nhắc hợp đồng/service có version mới thay vì cố giữ binary compatibility một cách hình thức.

## 13. Kiểm thử tương thích cần bao phủ gì?

Một phép thử round-trip cùng schema sẽ xác nhận mã hóa/giải mã cơ bản nhưng không phát hiện đầy đủ lỗi tương thích nhiều phiên bản. Với Spring gRPC, nên có ít nhất các nhóm sau:

| Phép thử | Nội dung xác minh |
| --- | --- |
| **v1 → v2** | Dữ liệu tạo từ v1 vẫn đọc được các field hiện có; field mới v2 có giá trị/presence hợp lý khi không được gửi. |
| **v2 → v1** | v1 đọc đúng các field chung; xử lý trường chưa biết mà không gây lỗi logic. |
| **Giá trị mặc định** | Scalar không gửi, scalar đặt giá trị mặc định và **optional** được đặt giá trị mặc định có kết quả theo thiết kế. |
| **Enum mới** | Code cũ xử lý giá trị chưa nhận biết; không giải thích nhầm số enum thành trạng thái khác. |
| **Repeated/packed** | Bộ đọc chấp nhận cách mã hóa phù hợp của phiên bản đối tác, vẫn bảo toàn số lượng và thứ tự phần tử. |
| **JSON/gateway** | Tên JSON, enum, số nguyên 64-bit, unknown fields và chuyển đổi nhị phân–JSON phù hợp với contract công khai. |
| **gRPC tích hợp** | Client và server khác phiên bản gọi unary/streaming, nhận status/trailer đúng và không có lỗi dữ liệu bị hiểu sai. |

Một kiểm thử ngắn cho presence với mã Java **v2**:

~~~java
import static org.junit.jupiter.api.Assertions.*;

Order source = Order.newBuilder()
    .setOrderId("o-42")
    .setCustomerNote("")
    .build();

Order restored = Order.parseFrom(source.toByteArray());

assertTrue(restored.hasCustomerNote());
assertEquals("", restored.getCustomerNote());
assertEquals("o-42", restored.getOrderId());

Order missingNote = Order.newBuilder()
    .setOrderId("o-43")
    .build();

assertFalse(missingNote.hasCustomerNote());
~~~

Kiểm thử này chứng minh presence trong cùng schema v2; để kiểm thử **wire compatibility**, cần thêm các fixture payload tạo bởi từng phiên bản schema và bộ đọc độc lập của phiên bản kia.

## 14. Tình huống thực hành

Nhóm phát triển đang thay đổi message **Payment**:

~~~proto
// Phiên bản hiện tại
message Payment {
  string payment_id = 1;
  int64 amount_cents = 2;
  string currency = 3;
  string reference = 4;
}
~~~

Đội sản phẩm đưa ra bốn đề xuất:

1. Đổi **amount_cents = 2** thành **double amount = 2** vì muốn hiển thị số tiền thập phân.
2. Đổi **payment_id = 1** thành **payment_code = 1**, vẫn dùng kiểu **string**.
3. Thêm **optional string failure_reason = 5**.
4. Bỏ **reference = 4**, dùng lại số **4** cho **bool is_refunded = 4**.

Hãy phân loại mức độ rủi ro của từng đề xuất ở cả ba góc độ **wire binary**, **API Java/JSON** và **ngữ nghĩa nghiệp vụ**. Sau đó viết schema sửa đổi an toàn hơn, giữ nguyên những số đang có và dùng **reserved** cho field ngừng sử dụng.

**Gợi ý kiểm tra:**

- **double** dùng wire type **1**, còn **int64** dùng wire type **0**; ngoài khác biệt mã hóa còn có nguy cơ sai số và thay đổi đơn vị.
- Đổi tên giữ số/kiểu có thể không đổi binary nhưng làm thay đổi getter Java và tên mặc định trên JSON.
- Thêm **failure_reason = 5** không khiến client cũ phải biết field mới, nhưng server vẫn phải xử lý khi field ấy vắng mặt.
- Tái sử dụng số **4** cho dữ liệu boolean có thể khiến bản cũ/bản mới hiểu sai hoặc bỏ mất dữ liệu. Cách an toàn hơn là ngừng dùng số 4, giữ nó trong **reserved**, và cấp số mới cho **is_refunded**.

## 15. Những nguyên tắc cần nhớ

- **Field number quyết định danh tính trên wire**; số hiệu phải duy nhất trong mỗi message, ổn định và không được tái sử dụng sau khi xóa.
- **Tag = (field number << 3) | wire type**; trùng wire type không đồng nghĩa hai field có cùng ngữ nghĩa.
- **Thêm field** thường an toàn về cấu trúc nhị phân nếu dùng số mới, nhưng bên đọc cũ có thể bỏ qua dữ liệu mới.
- **reserved** bảo vệ số/tên trong schema mới; không xóa được dữ liệu lịch sử và không chặn client cũ phát byte tương ứng.
- **Kiểm thử hai hướng, nhiều phiên bản**, và đánh giá thêm API Java, Protobuf JSON, presence và yêu cầu nghiệp vụ.

Nắm vững field number và wire compatibility giúp thay đổi hợp đồng Protocol Buffers mà vẫn duy trì dịch vụ Spring gRPC ổn định khi các client/server unary hay streaming được nâng cấp độc lập. Đây cũng là nền tảng để thiết kế quy trình giám sát và kiểm thử tích hợp đáng tin cậy trước khi đưa dịch vụ vào vận hành.
