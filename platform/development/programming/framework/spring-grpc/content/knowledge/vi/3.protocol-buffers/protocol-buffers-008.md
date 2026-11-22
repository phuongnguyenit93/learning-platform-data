# Enum và giá trị chưa biết

## Mục tiêu học tập

Sau bài này, bạn có thể:

- Khai báo enum proto3 với giá trị mặc định **0** và tên biểu đạt trạng thái chưa xác định.
- Hiểu enum được mã hóa bằng số nguyên trên Protobuf wire và phân biệt **unknown enum value** với **unknown field**.
- Đọc enum trong Java qua **getXxx()**, **getXxxValue()** và xử lý **UNRECOGNIZED** mà không làm mất số nguyên gốc.
- Nhận biết cách ProtoJSON biểu diễn enum đã biết và giá trị số chưa biết.
- Thay đổi enum an toàn khi client/server Spring gRPC triển khai khác phiên bản; không tái sử dụng số hoặc tên đã ngừng dùng.

## 1. Enum dùng để biểu diễn tập giá trị hữu hạn

Trong hợp đồng **SPRING_GRPC**, message Protobuf thường cần biểu diễn trạng thái hoặc lựa chọn có tập giá trị được xác định trước: trạng thái đơn hàng, loại thanh toán, mức độ ưu tiên hay chế độ giao hàng. **Enum** đặt tên cho các giá trị số đó để schema và mã Java dễ đọc.

~~~proto
syntax = "proto3";

enum OrderStatus {
  ORDER_STATUS_UNSPECIFIED = 0;
  ORDER_STATUS_PENDING = 1;
  ORDER_STATUS_PAID = 2;
  ORDER_STATUS_CANCELLED = 3;
}

message Order {
  string order_id = 1;
  OrderStatus status = 2;
}
~~~

Thay vì gửi chuỗi **PAID** trong Protobuf binary, field **status** được mã hóa bằng số **2**. Tên **ORDER_STATUS_PAID** giúp người đọc schema và mã nguồn hiểu ý nghĩa của số ấy.

Enum phù hợp khi các lựa chọn là một tập có ý nghĩa rõ ràng và được quản lý qua phiên bản. Nếu giá trị là chuỗi tự do do người dùng nhập, không nên ép nó thành enum.

## 2. Quy tắc khai báo enum trong proto3

Các quy tắc quan trọng:

1. **Giá trị đầu tiên phải có số 0.** Đây là giá trị mặc định của enum field proto3 không có explicit presence.
2. Nên đặt tên phần tử đầu tiên là **UNSPECIFIED** hoặc **UNKNOWN**, để không nhầm giá trị mặc định với một trạng thái nghiệp vụ đã được xác nhận.
3. Mỗi giá trị có một **tên** và một **số nguyên 32-bit**. Các số phải khác nhau, trừ khi bật alias một cách tường minh.
4. Tên enum value được khai báo trong phạm vi bao quanh enum (package hoặc message), nên dùng tiền tố như **ORDER_STATUS_** để tránh trùng tên với giá trị của enum khác.
5. Không thay đổi ý nghĩa của một số đã phát hành và không tái sử dụng số của giá trị đã xóa.

Ví dụ enum trong message:

~~~proto
message Payment {
  enum Method {
    METHOD_UNSPECIFIED = 0;
    METHOD_CARD = 1;
    METHOD_BANK_TRANSFER = 2;
  }

  Method method = 1;
}
~~~

Các giá trị enum vẫn cần tên duy nhất trong phạm vi của message bao quanh. Quy ước tiền tố giúp schema rõ ràng và tránh xung đột khi enum được khai báo ở cấp package.

### Alias khi hai tên cùng chỉ một số

Proto3 mặc định không cho hai enum value dùng cùng số. Nếu thật sự cần giữ hai tên tương thích trong một giai đoạn đổi thuật ngữ, có thể bật:

~~~proto
enum Color {
  option allow_alias = true;

  COLOR_UNSPECIFIED = 0;
  COLOR_GREY = 1;
  COLOR_GRAY = 1;
}
~~~

Với alias, khi in một số ra tên enum hoặc ProtoJSON, tên được khai báo **đầu tiên** cho số đó thường được dùng. Alias không tạo thêm giá trị nhị phân mới: **COLOR_GREY** và **COLOR_GRAY** đều là số 1. Chỉ dùng khi có lý do tương thích rõ ràng; nếu không, một tên chuẩn duy nhất sẽ dễ quản lý hơn.

## 3. Giá trị mặc định và presence của enum field

Với field enum thông thường:

~~~proto
message Order {
  OrderStatus status = 1;
}
~~~

Nếu không đặt **status**, getter Java trả **ORDER_STATUS_UNSPECIFIED** (số 0). Field enum scalar thông thường dùng **implicit presence**, nên không có **hasStatus()** để phân biệt không gửi với chủ động đặt **ORDER_STATUS_UNSPECIFIED**.

Nếu cần phân biệt hai trường hợp đó, khai báo:

~~~proto
message UpdateOrderRequest {
  optional OrderStatus requested_status = 1;
}
~~~

Java sinh **hasRequestedStatus()**. Khi builder chưa gọi setter, presence là false; khi gọi **setRequestedStatus(ORDER_STATUS_UNSPECIFIED)**, presence là true dù getter vẫn trả thành viên số 0.

~~~java
UpdateOrderRequest absent = UpdateOrderRequest.newBuilder().build();

UpdateOrderRequest explicitDefault =
    UpdateOrderRequest.newBuilder()
        .setRequestedStatus(OrderStatus.ORDER_STATUS_UNSPECIFIED)
        .build();

System.out.println(absent.getRequestedStatus());
// ORDER_STATUS_UNSPECIFIED
System.out.println(absent.hasRequestedStatus()); // false

System.out.println(explicitDefault.getRequestedStatus());
// ORDER_STATUS_UNSPECIFIED
System.out.println(explicitDefault.hasRequestedStatus()); // true
~~~

Giá trị mặc định **UNSPECIFIED** không nên bị diễn giải tự động thành một hành động như hủy đơn hay thanh toán. Logic nghiệp vụ phải quyết định cách xử lý khi enum chưa được cung cấp hoặc đang ở trạng thái chưa xác định.

## 4. Enum được mã hóa thành số trên Protobuf wire

Enum dùng wire type **0 (varint)**, tương tự các kiểu số nguyên varint. Tên enum không được ghi vào Protobuf binary.

~~~proto
message Order {
  OrderStatus status = 2;
}
~~~

Nếu **status = ORDER_STATUS_PAID** (số 2), phần mã hóa field có dạng:

~~~text
10 02
|  |
|  +-- Giá trị enum: 2
+----- Tag: (field_number 2 << 3) | wire_type 0 = 16
~~~

Nếu một client mới gửi số enum **99**, payload có thể là:

~~~text
10 63
|  |
|  +-- Giá trị enum: 99 (0x63)
+----- Tag của field status số 2, wire type 0
~~~

Đối với parser proto3, số 99 vẫn có thể được đọc vào field enum dù schema của phiên bản cũ chưa khai báo tên tương ứng. Đây là **unknown enum value**: parser biết field số 2 là enum, nhưng phiên bản schema hiện tại chưa biết tên cho số 99.

Điều này khác với **unknown field**. Unknown field xảy ra khi parser không nhận ra số hiệu field trong message. Với unknown enum value, parser nhận ra field và kiểu wire, nhưng giá trị số nằm ngoài các enum symbol mà code hiện tại biết.

## 5. Java xử lý enum chưa biết như thế nào?

Với enum proto3, Java code được sinh có một phần tử đặc biệt tên **UNRECOGNIZED** để biểu diễn số enum chưa được phiên bản hiện tại khai báo.

Hai API cần phân biệt:

- **getStatus()** trả enum Java. Nếu số nhận được chưa có trong enum hiện tại, nó trả **OrderStatus.UNRECOGNIZED**.
- **getStatusValue()** trả số nguyên gốc được lưu trong message, kể cả khi phiên bản schema hiện tại không có tên cho số ấy.

Ví dụ khi parse payload có field status số 99:

~~~java
Order parsed = Order.parseFrom(new byte[] {
    0x10, 0x63
});

System.out.println(parsed.getStatus());
// UNRECOGNIZED

System.out.println(parsed.getStatusValue());
// 99
~~~

Nếu cần chuyển tiếp hoặc ghi lại dữ liệu, **đừng thay unknown value bằng ORDER_STATUS_UNSPECIFIED**. Làm như vậy sẽ mất thông tin số 99 và có thể thay đổi ý nghĩa khi message được chuyển tới một service mới hơn.

Builder Java có phương thức **setStatusValue(int)** để đặt trực tiếp số enum:

~~~java
Order forwarded = Order.newBuilder()
    .setOrderId("o-42")
    .setStatusValue(99)
    .build();

System.out.println(forwarded.getStatus());      // UNRECOGNIZED
System.out.println(forwarded.getStatusValue()); // 99
~~~

Không dùng **OrderStatus.UNRECOGNIZED.getNumber()** để lấy số gốc. Thành viên **UNRECOGNIZED** là sentinel của API Java, không đại diện một số enum cụ thể; **getNumber()** trên nó ném **IllegalArgumentException**. Số gốc phải được lấy từ **getStatusValue()** của message.

Với enum repeated, Java cung cấp API đọc các số thô tương ứng như **getStatusesValueList()** bên cạnh danh sách enum. Khi xử lý giá trị chưa biết trong danh sách, hãy dùng API số nguyên để không làm mất số.

## 6. Viết logic nghiệp vụ an toàn với UNRECOGNIZED

Không nên viết switch chỉ xử lý các trạng thái đã biết rồi âm thầm gán mọi giá trị còn lại thành trạng thái mặc định.

~~~java
switch (order.getStatus()) {
    case ORDER_STATUS_PENDING ->
        handlePending(order);
    case ORDER_STATUS_PAID ->
        handlePaid(order);
    case ORDER_STATUS_CANCELLED ->
        handleCancelled(order);
    case ORDER_STATUS_UNSPECIFIED ->
        handleUnspecified(order);
    case UNRECOGNIZED ->
        handleUnknownStatus(order.getStatusValue());
}
~~~

**handleUnknownStatus(...)** có thể ghi nhận metric/log, từ chối thao tác cần hiểu trạng thái, hoặc chuyển tiếp số nguyên gốc tới một hệ thống có schema mới hơn. Quyết định phụ thuộc nghiệp vụ và ranh giới tin cậy; không tự thực hiện hành động thanh toán/hủy khi gặp số không nhận diện.

Một cách kiểm tra tường minh:

~~~java
int rawStatus = order.getStatusValue();
OrderStatus status = order.getStatus();

if (status == OrderStatus.UNRECOGNIZED) {
    // Giữ rawStatus để chẩn đoán hoặc chuyển tiếp.
    recordUnknownStatus(rawStatus);
} else {
    processKnownStatus(status);
}
~~~

Khi ứng dụng nhận enum từ client bên ngoài, nên xác thực cả giá trị đã biết lẫn điều kiện chuyển trạng thái. Enum xác định miền giá trị của schema, nhưng không tự bảo đảm một chuyển đổi như **PENDING → PAID** là hợp lệ ở tầng nghiệp vụ.

## 7. ProtoJSON: tên enum đã biết và số enum chưa biết

ProtoJSON thường biểu diễn enum đã biết bằng **tên**:

~~~json
{
  "status": "ORDER_STATUS_PAID"
}
~~~

Nếu message chứa số enum chưa biết với phiên bản schema hiện tại, ProtoJSON có thể biểu diễn giá trị ấy dưới dạng **số nguyên**:

~~~json
{
  "status": 99
}
~~~

Parser ProtoJSON chấp nhận số nguyên enum, kể cả số chưa được khai báo trong enum hiện tại. Ngược lại, một chuỗi tên không tồn tại trong phiên bản schema như **ORDER_STATUS_REFUNDED** thường không được parser cũ nhận diện. Vì vậy, khi cần truyền giá trị enum mới qua JSON đến một consumer cũ, biểu diễn số có thể giữ được thông tin tốt hơn chuỗi tên, nhưng chỉ nên dùng nếu hợp đồng JSON và các consumer chấp nhận cách biểu diễn đó.

Trong Java, có thể dùng **JsonFormat** của **protobuf-java-util**:

~~~java
import com.google.protobuf.util.JsonFormat;

Order order = Order.newBuilder()
    .setOrderId("o-42")
    .setStatusValue(99)
    .build();

String json = JsonFormat.printer().print(order);
// Field status được biểu diễn bằng số 99 vì phiên bản enum
// hiện tại không có tên tương ứng.

Order.Builder builder = Order.newBuilder();
JsonFormat.parser().merge("{\"status\":99}", builder);

Order parsed = builder.build();
System.out.println(parsed.getStatus());      // UNRECOGNIZED
System.out.println(parsed.getStatusValue()); // 99
~~~

Không đồng nhất ProtoJSON với serializer JSON tổng quát của Java. Thư viện khác có thể không giữ nguyên số enum chưa biết hoặc có thể từ chối giá trị đó. Khi dùng REST gateway, logging hoặc lưu JSON, cần kiểm thử đúng serializer/parser đang vận hành.

## 8. Thay đổi enum mà vẫn giữ tương thích

Giả sử phiên bản v1 có:

~~~proto
enum OrderStatus {
  ORDER_STATUS_UNSPECIFIED = 0;
  ORDER_STATUS_PENDING = 1;
  ORDER_STATUS_PAID = 2;
}
~~~

Phiên bản v2 bổ sung trạng thái hoàn tiền:

~~~proto
enum OrderStatus {
  ORDER_STATUS_UNSPECIFIED = 0;
  ORDER_STATUS_PENDING = 1;
  ORDER_STATUS_PAID = 2;
  ORDER_STATUS_REFUNDED = 3;
}
~~~

Đây thường là thay đổi **tương thích wire**: số 3 được mã hóa như một varint, parser v1 vẫn nhận được số ấy. Tuy nhiên, code v1 không có symbol **ORDER_STATUS_REFUNDED**; Java proto3 trả **UNRECOGNIZED**, còn **getStatusValue()** giữ số 3.

| Thay đổi | Ảnh hưởng |
| --- | --- |
| Thêm enum value với số mới | Thường tương thích binary; consumer cũ phải xử lý số chưa biết. |
| Đổi tên enum value, giữ số | Binary vẫn mang cùng số; Java constant và ProtoJSON string thay đổi. |
| Đổi số của enum value đã phát hành | Có thể khiến dữ liệu cũ bị hiểu thành trạng thái khác. |
| Xóa enum value rồi tái sử dụng số | Byte lịch sử có thể bị diễn giải sai. |
| Xóa enum value và reserve số/tên | Ngăn schema mới vô tình dùng lại giá trị lịch sử. |

**Không đổi số của enum value đã phát hành chỉ để sắp xếp lại danh sách.** Thứ tự khai báo không phải thứ tự nghiệp vụ; số hiệu là một phần của hợp đồng nhị phân.

### Triển khai client và server khác phiên bản

Khi server v2 phát enum value 3 trong response:

- Client v2 biết **ORDER_STATUS_REFUNDED** và có thể xử lý theo tên.
- Client v1 đọc được số 3 nhưng Java trả **UNRECOGNIZED**; code phải có nhánh xử lý rõ.
- Nếu client v1 chuyển tiếp message nhị phân mà không tái tạo message thủ công, runtime Protobuf có thể giữ số enum chưa biết.
- Nếu client v1 chuyển enum thành chuỗi, DTO hoặc một mô hình chỉ cho phép các giá trị đã biết, số 3 có thể bị mất hoặc bị thay bằng giá trị mặc định.

Do đó, thêm enum value không đủ để bảo đảm toàn bộ hệ thống tương thích. Cần kiểm tra hành vi của code cũ, gateway JSON và các trung gian chuyển tiếp message.

## 9. Xóa enum value bằng reserved

Nếu một enum value đã ngừng sử dụng, reserve cả số và tên:

~~~proto
enum OrderStatus {
  ORDER_STATUS_UNSPECIFIED = 0;
  ORDER_STATUS_PENDING = 1;
  ORDER_STATUS_PAID = 2;

  reserved 3, 5 to 7;
  reserved "ORDER_STATUS_LEGACY";
}
~~~

Ví dụ giả định số 3, 5–7 và tên **ORDER_STATUS_LEGACY** từng được sử dụng. **reserved number** ngăn tái sử dụng số trên wire; **reserved name** ngăn tái sử dụng symbol trong schema. Hai câu lệnh phải tách riêng, không trộn số và tên trong cùng một câu lệnh reserved.

**reserved** không ngăn client cũ gửi số enum đã bị xóa. Parser proto3 mới vẫn có thể nhận số đó như unknown enum value. Nếu nghiệp vụ không còn chấp nhận giá trị cũ, server phải kiểm tra và từ chối hoặc chuyển đổi theo chính sách migration; reserved chỉ bảo vệ schema khi biên dịch.

## 10. Kiểm thử enum chưa biết

Một bộ kiểm thử cần xác nhận:

1. Field enum không đặt trả giá trị số 0.
2. Field optional enum phân biệt không đặt với đặt tường minh **UNSPECIFIED**.
3. Số enum chưa khai báo cho Java hiện tại trả **UNRECOGNIZED**, trong khi **getXxxValue()** giữ số nguyên.
4. Parse rồi serialize lại Protobuf nhị phân không làm mất số enum chưa biết.
5. ProtoJSON chấp nhận giá trị số chưa biết và round-trip vẫn giữ số.
6. Logic nghiệp vụ không âm thầm chuyển unknown value thành trạng thái hợp lệ khác.

Ví dụ JUnit 5 cho enum **OrderStatus** ở mục 1:

~~~java
import static org.junit.jupiter.api.Assertions.*;

import com.example.orders.v1.Order;
import com.example.orders.v1.OrderStatus;
import org.junit.jupiter.api.Test;

class OrderStatusTest {
    @Test
    void preservesUnknownNumericEnumValue() throws Exception {
        Order source = Order.newBuilder()
            .setOrderId("o-42")
            .setStatusValue(99)
            .build();

        Order parsed = Order.parseFrom(source.toByteArray());

        assertEquals(OrderStatus.UNRECOGNIZED, parsed.getStatus());
        assertEquals(99, parsed.getStatusValue());

        Order forwarded = Order.parseFrom(parsed.toByteArray());
        assertEquals(99, forwarded.getStatusValue());
    }
}
~~~

Để kiểm thử tương thích thực sự, nên tạo fixture từ schema v2 có **ORDER_STATUS_REFUNDED = 3**, rồi parse bằng lớp Java v1 không có giá trị 3. Kiểm thử bằng một lớp v1 và một lớp v2 có cùng full Java class name cần được tổ chức ở module/test fixture độc lập để tránh xung đột classpath.

## 11. Lỗi thường gặp

| Sai lầm | Hậu quả | Cách xử lý |
| --- | --- | --- |
| Không khai báo giá trị enum số 0 đầu tiên | Schema proto3 không hợp lệ | Thêm **UNSPECIFIED = 0**. |
| Xem số 0 là trạng thái đã xác nhận | Dữ liệu vắng mặt bị hiểu sai | Dùng tên **UNSPECIFIED** và kiểm tra presence khi cần. |
| Chỉ gọi **getStatus()** khi cần giữ giá trị lạ | Nhận **UNRECOGNIZED**, mất số gốc nếu thay bằng mặc định | Đọc **getStatusValue()**. |
| Gọi **UNRECOGNIZED.getNumber()** | Java ném **IllegalArgumentException** | Lấy số từ message bằng **getStatusValue()**. |
| Thêm enum value mà không cập nhật code cũ | Client cũ không xử lý được trạng thái mới | Xử lý nhánh unknown và kiểm thử nhiều phiên bản. |
| Đổi số enum đã phát hành | Dữ liệu cũ bị diễn giải thành trạng thái khác | Giữ số ổn định, không tái sử dụng. |
| Chỉ reserve tên enum cũ | Số cũ có thể bị gán nghĩa mới | Reserve cả số và tên. |
| Chuyển unknown enum thành **UNSPECIFIED** khi proxy | Mất thông tin để service mới hiểu đúng | Giữ số nguyên và chuyển tiếp khi phù hợp. |

## 12. Bài tập thực hành

Một hệ thống vận chuyển dùng enum:

~~~proto
enum ShipmentStatus {
  SHIPMENT_STATUS_UNSPECIFIED = 0;
  SHIPMENT_STATUS_CREATED = 1;
  SHIPMENT_STATUS_IN_TRANSIT = 2;
  SHIPMENT_STATUS_DELIVERED = 3;
}

message Shipment {
  string shipment_id = 1;
  ShipmentStatus status = 2;
}
~~~

Hãy:

1. Bổ sung trạng thái **RETURNED** bằng một số mới mà không thay đổi số cũ.
2. Giải thích điều client phiên bản trước sẽ nhận khi đọc shipment có trạng thái mới.
3. Viết Java kiểm tra **getStatus()**, **getStatusValue()** và xử lý **UNRECOGNIZED**.
4. Serialize message có số enum 99, parse lại và chứng minh số 99 không bị chuyển thành 0.
5. Biểu diễn trạng thái đã biết và chưa biết bằng ProtoJSON; giải thích khác biệt giữa chuỗi tên enum và số nguyên.
6. Giả sử trạng thái số 4 bị loại bỏ trong tương lai, viết reserved cho cả số 4 và tên enum cũ.

**Tiêu chí hoàn thành:** hiểu enum là số trên wire, xử lý được giá trị không có tên trong phiên bản Java hiện tại, và đề xuất được thay đổi enum an toàn cho client/server triển khai độc lập.

## 13. Ghi nhớ

- Enum proto3 phải bắt đầu bằng số **0**, thường đặt tên **UNSPECIFIED**.
- Protobuf binary mã hóa enum bằng số nguyên varint; tên enum không được gửi trên wire.
- Java trả **UNRECOGNIZED** cho số enum chưa biết, nhưng **getXxxValue()** vẫn giữ số nguyên gốc.
- ProtoJSON dùng tên cho enum đã biết và có thể dùng số cho giá trị chưa biết.
- Thêm enum value mới thường tương thích wire, nhưng code cũ phải xử lý giá trị chưa biết; không âm thầm đổi nó thành trạng thái khác.
- Khi xóa enum value, reserve cả **số** và **tên**; không tái sử dụng danh tính đã phát hành.

Hiểu enum và giá trị chưa biết giúp dịch vụ Spring gRPC tiến hóa hợp đồng an toàn khi client, server và các gateway được nâng cấp ở thời điểm khác nhau, đồng thời giữ nguyên thông tin trạng thái mà phiên bản hiện tại chưa hiểu.
