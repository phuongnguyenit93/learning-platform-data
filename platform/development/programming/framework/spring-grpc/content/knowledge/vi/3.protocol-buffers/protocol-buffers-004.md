# Field name, JSON name và reserved field

## Mục tiêu học tập

Sau bài học này, bạn có thể:

- Phân biệt **field name** trong tệp .proto, **JSON name** trong ProtoJSON và **field number** trong dữ liệu Protocol Buffers nhị phân.
- Áp dụng quy tắc đặt tên **lower_snake_case**, hiểu cách hình thành **lowerCamelCase** và sử dụng tùy chọn **json_name** khi cần.
- Giải thích vì sao đổi tên field có thể giữ tương thích nhị phân nhưng làm thay đổi API Java và hợp đồng JSON.
- Khai báo **reserved number** và **reserved name** khi xóa field để tránh tái sử dụng danh tính lịch sử.
- Kiểm thử hợp đồng message trong môi trường Spring gRPC có client/server và công cụ JSON chạy khác phiên bản.

## 1. Field name, JSON name và field number khác nhau ở đâu?

Trong module **SPRING_GRPC**, tệp Protocol Buffers định nghĩa cấu trúc dữ liệu được sinh thành lớp Java và trao đổi qua các RPC unary hoặc streaming. gRPC thường dùng mã hóa Protobuf **nhị phân**. Tuy nhiên, request/response đôi khi cũng được xuất thành **ProtoJSON** để phục vụ REST gateway, log, kiểm thử hoặc tích hợp hệ thống ngoài.

Xét:

~~~proto
message Customer {
  string customer_id = 1;
}
~~~

| Khái niệm | Trong ví dụ | Được dùng để làm gì? |
| --- | --- | --- |
| Field name | **customer_id** | Định danh field trong .proto, descriptor và API Java sinh mã. |
| JSON name mặc định | **customerId** | Khóa thuộc tính khi xuất message bằng ProtoJSON. |
| Field number | **1** | Danh tính field trên đường truyền nhị phân. |

Với cấu hình sinh Java thông dụng, trường này có getter **getCustomerId()** và phương thức builder **setCustomerId(...)**. Protobuf nhị phân ghi tag theo **field number** và wire type; nó không ghi tên chuỗi **customer_id** vào mỗi message.

Ba khái niệm không thể thay thế cho nhau. Đổi tên field nhưng giữ **số 1** và kiểu **string** thường vẫn đọc được byte cũ. Ngược lại, đổi số 1 thành số 10 có thể phá giao tiếp nhị phân dù tên field và JSON trông không đổi. Sự khác biệt này rất quan trọng khi nhiều phiên bản client Spring gRPC và server được triển khai độc lập.

## 2. Quy ước đặt field name trong proto3

Protobuf khuyến nghị field name viết theo **lower_snake_case**: chữ thường và dấu gạch dưới giữa các từ.

~~~proto
message Customer {
  string customer_id = 1;
  string display_name = 2;
  string preferred_language = 3;
  int64 points_balance = 4;
}
~~~

Các tên này mô tả dữ liệu, thay vì tên biến tạm hoặc cách hiển thị của một giao diện cụ thể. Nên ưu tiên **amount_cents** nếu số tiền tính theo cent, **created_at** cho thời điểm tạo và **preferred_language** cho ngôn ngữ ưu tiên. Hạn chế các tên quá rộng như **data**, **value** khi message chứa nhiều khái niệm.

Khi soạn schema:

1. Mỗi field có **tên duy nhất** trong cùng message. Tên đang được dành riêng bằng **reserved** không thể được khai báo lại.
2. Định danh phải hợp lệ theo cú pháp .proto: không bắt đầu bằng chữ số, không dùng từ khóa dành riêng của ngôn ngữ schema.
3. Giữ quy ước đặt tên nhất quán giữa các message. Tránh luân phiên **customer_id**, **customerID** và **CustomerId** cho cùng một ý nghĩa.
4. Đừng tùy tiện đổi tên field đã phát hành. Ngay cả khi binary wire không đổi, mã Java sinh ra, tài liệu, reflection và công cụ JSON có thể phụ thuộc tên cũ.
5. Khi nội dung hoặc đơn vị của dữ liệu thay đổi, không nên chỉ đổi tên để che giấu khác biệt nghiệp vụ. Cân nhắc dùng một field mới với số mới.

Một tên trong .proto còn xuất hiện trong **descriptor**, tài liệu mã sinh và định dạng văn bản Protobuf (**TextFormat**). Vì thế, tên field vẫn là một phần đáng quản lý của hợp đồng, dù không trực tiếp xuất hiện trong payload nhị phân.

## 3. Tên JSON mặc định được tạo như thế nào?

Theo quy tắc ProtoJSON, tên field **lower_snake_case** thường chuyển thành **lowerCamelCase**:

| Tên trong .proto | Khóa ProtoJSON mặc định | Getter Java |
| --- | --- | --- |
| **customer_id** | **customerId** | **getCustomerId()** |
| **display_name** | **displayName** | **getDisplayName()** |
| **preferred_language** | **preferredLanguage** | **getPreferredLanguage()** |
| **points_balance** | **pointsBalance** | **getPointsBalance()** |
| **is_verified** | **isVerified** | **getIsVerified()** |

Ví dụ:

~~~proto
message Customer {
  string customer_id = 1;
  string display_name = 2;
}
~~~

Message có giá trị tương ứng có thể được xuất dưới dạng:

~~~json
{
  "customerId": "C-42",
  "displayName": "Nguyen An"
}
~~~

**ProtoJSON parser** chấp nhận cả tên JSON và tên gốc trong .proto cho cùng field. Vì vậy, với schema trên, khóa **customerId** và khóa **customer_id** đều có thể được đọc thành field số 1. Đây là đặc điểm của parser ProtoJSON, không phải cam kết rằng mọi thư viện JSON tự viết đều có hành vi giống nhau.

Không gửi đồng thời **customerId** và **customer_id** trong một đối tượng để biểu diễn cùng một field. Điều này tạo dữ liệu trùng lặp, có thể bị parser từ chối hoặc xử lý theo chính sách không mong muốn. Đầu ra của một API nên thống nhất một tên khóa.

JSON còn có quy tắc riêng về **giá trị**: kiểu **int64** được xuất thành chuỗi thập phân để tránh mất độ chính xác ở các môi trường dùng số thực IEEE-754; enum thường được xuất bằng tên. Vì vậy khi kiểm tra khả năng tương thích JSON, phải kiểm tra cả khóa lẫn giá trị.

## 4. Tùy chỉnh tên JSON bằng json_name

Nếu hợp đồng JSON công khai đã sử dụng một cách viết khác, bạn có thể đặt tên chính xác bằng tùy chọn **json_name**:

~~~proto
syntax = "proto3";

package learning.customers.v1;

option java_package = "com.example.customers.v1";
option java_multiple_files = true;

message Customer {
  string customer_id = 1 [json_name = "customerID"];
  string display_name = 2;
  optional string preferred_language = 3;
  int64 points_balance = 4;
}
~~~

Trong trường hợp này, đầu ra ProtoJSON sử dụng **customerID** thay cho **customerId**. Những thành phần còn lại vẫn như cũ:

- Field trong .proto vẫn tên **customer_id**.
- Field number vẫn là **1**.
- Getter và setter Java vẫn là **getCustomerId()** và **setCustomerId(...)**.
- Giao tiếp gRPC nhị phân không gửi tên JSON mới; nó vẫn nhận diện field bằng số 1.

Ví dụ một bản JSON hợp lệ:

~~~json
{
  "customerID": "C-42",
  "displayName": "Nguyen An",
  "preferredLanguage": "vi",
  "pointsBalance": "9007199254740993"
}
~~~

Giá trị của **pointsBalance** là chuỗi, vì kiểu .proto là **int64**. Việc Java dùng kiểu **long** không làm ProtoJSON xuất số nguyên 64-bit này thành number theo mặc định.

Nên dùng **json_name** có chủ đích, chẳng hạn khi cần tuân theo tên JSON đã triển khai. Với API mới, tên JSON mặc định thường dễ duy trì hơn. Đặt nhiều quy tắc tùy biến không cần thiết làm schema khó đọc và dễ gây xung đột.

### Cảnh giác với tên JSON trùng nhau

Hai field có tên khác nhau trong .proto vẫn có thể tạo tên JSON giống nhau:

~~~proto
// Ví dụ minh họa xung đột; không dùng làm schema triển khai.
message BadNaming {
  string user_id = 1;
  string userId = 2;
}
~~~

Hai tên trên có nguy cơ đều ánh xạ thành **userId** trong ProtoJSON. **protoc** kiểm tra các xung đột tên JSON theo quy tắc của compiler; dù thay đổi về cú pháp nào đó có được chấp nhận, không nên tạo hai field cạnh tranh một khóa JSON. Khi dùng **json_name** tường minh, cũng phải tránh đặt trùng tên JSON đang thuộc field khác.

## 5. Hợp đồng gRPC đầy đủ minh họa cách đặt tên

Một ví dụ hoàn chỉnh cho dịch vụ lấy thông tin khách hàng:

~~~proto
syntax = "proto3";

package learning.customers.v1;

option java_package = "com.example.customers.v1";
option java_multiple_files = true;

message Customer {
  string customer_id = 1 [json_name = "customerID"];
  string display_name = 2;
  optional string preferred_language = 3;
  int64 points_balance = 4;

  // Giả sử những field này từng tồn tại trong schema cũ.
  reserved 5, 7 to 9;
  reserved "legacy_nickname";
}

message GetCustomerRequest {
  string customer_id = 1 [json_name = "customerID"];
}

message GetCustomerResponse {
  Customer customer = 1;
}

service CustomerService {
  rpc GetCustomer(GetCustomerRequest) returns (GetCustomerResponse);
}
~~~

**package** là namespace của schema Protobuf; **java_package** xác định package lớp Java sinh ra. **java_multiple_files = true** cho phép các kiểu top-level được sinh thành lớp Java riêng. Việc đặt **json_name** không ảnh hưởng đến chữ ký RPC hoặc cách gRPC truyền request/response.

Trong client Java:

~~~java
import com.example.customers.v1.GetCustomerRequest;
import com.example.customers.v1.GetCustomerResponse;
import com.example.customers.v1.CustomerServiceGrpc;

// Giả sử channel đã được cấu hình và cung cấp cho client.
CustomerServiceGrpc.CustomerServiceBlockingStub stub =
    CustomerServiceGrpc.newBlockingStub(channel);

GetCustomerResponse response = stub.getCustomer(
    GetCustomerRequest.newBuilder()
        .setCustomerId("C-42")
        .build());

String displayName = response.getCustomer().getDisplayName();
~~~

Server Spring gRPC cũng dùng getter từ message đã sinh để đọc request. Cách cấu hình stub, TLS, metadata, deadline, status và interceptor nằm ở tầng giao tiếp và vận hành; chúng không thay đổi quy tắc đặt tên của Protobuf.

## 6. Dùng JsonFormat trong Java

Ứng dụng có thể dùng **com.google.protobuf.util.JsonFormat** thuộc thư viện **protobuf-java-util**, với phiên bản tương thích với runtime Protobuf. Đây là công cụ serialize/parse **ProtoJSON**, khác việc dùng một serializer JSON chung chỉ dựa vào getter của lớp Java.

~~~java
import com.example.customers.v1.Customer;
import com.google.protobuf.util.JsonFormat;

Customer customer = Customer.newBuilder()
    .setCustomerId("C-42")
    .setDisplayName("Nguyen An")
    .setPreferredLanguage("vi")
    .setPointsBalance(9007199254740993L)
    .build();

String json = JsonFormat.printer().print(customer);
System.out.println(json);
// Đầu ra có khóa "customerID" theo json_name đã khai báo.

Customer.Builder builder = Customer.newBuilder();
JsonFormat.parser().merge(json, builder);
Customer restored = builder.build();

System.out.println(restored.getCustomerId());         // C-42
System.out.println(restored.hasPreferredLanguage());  // true
~~~

Nếu yêu cầu xuất tên .proto nguyên gốc, có thể dùng:

~~~java
String protoNamedJson = JsonFormat.printer()
    .preservingProtoFieldNames()
    .print(customer);
// Khi đó khóa là "customer_id", "display_name", ...
~~~

Tùy chọn này tác động đến cách in JSON ở ranh giới ứng dụng; nó không sửa schema hay số hiệu field. Hai bên trao đổi JSON cần thống nhất cách đặt tên trước khi phụ thuộc vào nó.

Khi parse, thư viện chấp nhận tên JSON được chỉ định và tên gốc trong .proto. Nhưng khi nhận **khóa không xác định**, parser mặc định có thể báo lỗi. Java có tùy chọn bỏ qua:

~~~java
Customer.Builder builder = Customer.newBuilder();
JsonFormat.parser()
    .ignoringUnknownFields()
    .merge(jsonFromOtherVersion, builder);
~~~

Chỉ bỏ qua unknown fields nếu hợp đồng cho phép làm mất thông tin ấy. Khi dữ liệu Protobuf nhị phân được đọc rồi chuyển sang JSON, các unknown fields của phiên bản mới có thể mất ở khâu trung gian; không nên mặc nhiên cho rằng dữ liệu luôn được bảo toàn.

## 7. Đổi field name nhưng giữ số hiệu

Giả sử một API đã phát hành message v1:

~~~proto
message Customer {
  string customer_id = 1;
  string display_name = 2;
}
~~~

Vì yêu cầu thuật ngữ nội bộ, nhóm phát triển định đổi **display_name** thành **full_name**:

~~~proto
// Ví dụ v2 — biên dịch riêng với v1.
message Customer {
  string customer_id = 1;
  string full_name = 2 [json_name = "displayName"];
  reserved "display_name";
}
~~~

So sánh:

| Góc nhìn | Kết quả |
| --- | --- |
| Binary wire | Field **2** vẫn là **string**; byte cũ thường được đọc thành cùng giá trị. |
| ProtoJSON xuất ra | **json_name** duy trì khóa **displayName** như v1. |
| ProtoJSON đầu vào | v2 nhận **displayName** và tên .proto mới **full_name**; không nên giả định vẫn nhận alias cũ **display_name**. |
| API Java | Getter **getDisplayName()** thành **getFullName()**; code gọi phải sửa. |
| Descriptor, TextFormat | Tên trong schema đã đổi; công cụ tra cứu theo tên cũ có thể bị ảnh hưởng. |
| Reserved name | Ngăn khai báo lại tên .proto **display_name** trong message. |

**Không được reserved số 2** trong trường hợp này, vì field mới **full_name** vẫn sử dụng số 2. Việc reserve tên cũ giúp kiểm soát thay đổi tên; còn việc giữ số và kiểu duy trì danh tính binary.

Trong nhiều tình huống, chỉ cần đổi nhãn hiển thị ở frontend hoặc DTO là đủ. Giữ nguyên tên .proto sẽ giảm số vị trí cần sửa, đặc biệt khi nhiều client dùng lớp Java sinh mã. Nếu JSON API thực sự cần đổi khóa, phải có kế hoạch nâng cấp client và kiểm thử hợp đồng tương ứng.

**json_name không phải hệ thống alias vô hạn.** Nó khai báo một tên JSON chính cho field hiện tại; parser còn chấp nhận tên .proto hiện tại, nhưng không tự động duy trì mọi tên .proto lịch sử.

## 8. Reserved field bảo vệ hợp đồng như thế nào?

Từ khóa **reserved** dùng để đánh dấu các **số hiệu field** hoặc **tên field** không còn được phép dùng trong một message. Cơ chế này hữu ích khi xóa một field từng được gửi qua mạng hoặc lưu trong database, queue, bản sao lưu.

Phiên bản trước:

~~~proto
message Customer {
  string customer_id = 1;
  string legacy_nickname = 5;
  int32 old_score = 7;
}
~~~

Phiên bản mới:

~~~proto
message Customer {
  string customer_id = 1;

  reserved 5, 7;
  reserved "legacy_nickname", "old_score";

  string display_name = 2;
}
~~~

**reserved 5, 7** ngăn ai đó sử dụng lại số 5 hoặc 7 cho dữ liệu mới. Đây là bảo vệ quan trọng cho tương thích binary: một client cũ vẫn có thể gửi byte mang số 5 hoặc 7 sau khi server đã nâng cấp.

**reserved "legacy_nickname", "old_score"** ngăn một kỹ sư vô tình tái sử dụng tên .proto cũ với ý nghĩa khác. Tên field không xuất hiện trong Protobuf binary thông thường, nhưng vẫn liên quan đến JSON, mã sinh và tài liệu. Khi xóa field đã phát hành, thường nên reserve **cả số lẫn tên**.

### Reserved không phải cơ chế xóa dữ liệu

Reserved chỉ là quy tắc **tại thời điểm biên dịch schema**:

- Không xóa field cũ khỏi byte dữ liệu đã lưu.
- Không ngăn một client cũ tiếp tục gửi field ấy.
- Không tự chuyển giá trị cũ sang field mới.
- Không buộc parser gRPC trả lỗi khi gặp field số cũ; field đó có thể trở thành **unknown field**.
- Không biến tên JSON cũ thành một alias hợp lệ của field khác.

Protobuf Java có thể giữ unknown fields khi parse và serialize lại binary. Tuy nhiên, việc ánh xạ DTO, chuyển qua JSON hoặc tạo lại message thủ công có thể loại bỏ chúng. Vì vậy, phải quản lý dữ liệu lịch sử và client cũ bằng kế hoạch nâng cấp thực tế.

## 9. Cú pháp reserved: số, khoảng và tên

Trong một message, có thể reserve số riêng lẻ hoặc khoảng số:

~~~proto
message Event {
  string event_id = 1;
  reserved 2, 4 to 6, 10;
  reserved "legacy_owner", "old_payload";
}
~~~

**4 to 6** bao gồm cả 4, 5 và 6. Số hiệu field hợp lệ của Protobuf từ **1** đến **536.870.911**, ngoại trừ khoảng **19.000–19.999** dành riêng cho triển khai Protobuf.

Tên và số phải nằm trong **câu lệnh reserved riêng**, không được trộn:

~~~proto
// Hợp lệ:
reserved 2, 5 to 8;
reserved "old_name", "retired_code";

// Không hợp lệ:
// reserved 2, "old_name";
~~~

Hai câu lệnh minh họa cú pháp trên phải được đặt **bên trong một message**, không nằm trực tiếp ở cấp tệp. Tương tự, không được reserve một số hiệu hoặc tên đã thuộc về field đang hoạt động. Field bên trong **oneof** vẫn phải tuân theo phạm vi tên và số của chính message đó.

Reserved theo phạm vi: số 5 đã reserve trong **Customer** không ngăn message **GetCustomerRequest** dùng số 5. Trong schema mới chưa từng sử dụng, không nên tự khai báo một loạt số reserved chỉ vì dự đoán tương lai; hãy dành số/tên theo lịch sử hoặc một quyết định thiết kế có căn cứ.

## 10. Vì sao phải giữ cả reserved number và reserved name?

| Điều cần bảo vệ | Reserve số cũ | Reserve tên cũ |
| --- | --- | --- |
| Ngăn field mới dùng lại cùng số trên binary | **Có** | Không |
| Ngăn field mới dùng lại tên .proto | Không | **Có** |
| Giảm nguy cơ dữ liệu binary cũ bị hiểu thành nghĩa mới | **Trực tiếp** | Không trực tiếp |
| Ngăn client cũ gửi byte chứa số đã xóa | Không | Không |
| Làm khóa JSON cũ tự động bị từ chối | Không | Không |
| Ánh xạ JSON cũ sang field mới | Không | Không |

Xét lỗi sau: field cũ **string old_email = 3** bị loại bỏ, nhưng schema mới chỉ reserve tên rồi thêm **string phone = 3**. Vì cả hai dùng số 3 và cùng loại mã hóa nhị phân của string, dữ liệu email lịch sử có thể bị server mới hiểu nhầm là số điện thoại. **Reserve name không thể ngăn lỗi này**.

Schema đúng hơn:

~~~proto
message Contact {
  reserved 3;
  reserved "old_email";

  string phone = 4;
}
~~~

Nếu field cũ tên **old_email**, JSON name mặc định là **oldEmail**. **reserved "old_email"** bảo vệ tên định danh trong .proto, không phải một danh sách cấm dành riêng cho tất cả khóa JSON. JSON parser vẫn xử lý các khóa đầu vào theo schema và chính sách unknown fields hiện tại.

## 11. Reserved trong enum

Với enum proto3, các giá trị có **số enum** và **tên enum**. Nếu ngừng dùng một trạng thái, không được lấy lại số hoặc tên cũ cho trạng thái khác:

~~~proto
enum CustomerState {
  CUSTOMER_STATE_UNSPECIFIED = 0;
  CUSTOMER_STATE_ACTIVE = 1;
  CUSTOMER_STATE_PAUSED = 2;

  reserved 3, 5 to 7;
  reserved "CUSTOMER_STATE_LEGACY";
}
~~~

Ví dụ giả định các giá trị reserved đã tồn tại trong lịch sử. Enum proto3 phải có phần tử đầu tiên mang số **0**; tên như **UNSPECIFIED** giúp thể hiện trạng thái mặc định chưa xác định.

Trong Protobuf binary, enum truyền dưới dạng số; trong ProtoJSON, enum thường được ghi bằng **tên**. Do đó, đổi số enum có thể phá cách hiểu nhị phân, còn đổi tên enum có thể phá client JSON đang dựa vào chuỗi tên cũ. Reserved số và tên enum giúp tránh tái sử dụng vô ý, nhưng không tự chuyển dữ liệu lịch sử.

## 12. So sánh thay đổi schema theo từng lớp tương thích

| Thay đổi | Binary Protobuf | JSON, mã Java và nghiệp vụ |
| --- | --- | --- |
| Đổi field name, giữ số và kiểu | Thường giữ được khả năng đọc byte cũ. | Có thể đổi JSON name, getter/setter và descriptor. |
| Đổi riêng **json_name** | Binary không đổi. | Khóa JSON được xuất thay đổi; client cũ có thể hỏng. |
| Đổi field number, giữ tên và kiểu | Không tương thích đáng tin cậy. | JSON nhìn giống cũ nhưng binary coi là field khác. |
| Thêm field mới với số chưa dùng | Thường an toàn về cấu trúc binary. | Client cũ không có getter hoặc không biết khóa JSON mới. |
| Xóa field và reserve số/tên | Parser mới có thể coi field cũ là unknown. | Code Java không còn getter; JSON cũ có thể có khóa không được nhận diện. |
| Dùng lại số cũ cho nghĩa mới | Nguy hiểm, có thể hiểu sai dữ liệu. | Các client có thể cho ra giá trị nghiệp vụ sai. |
| Đổi tên enum, giữ số | Binary có thể giữ được. | JSON enum dạng tên có thể phá hợp đồng cũ. |

**Tương thích binary không đồng nghĩa tương thích mã nguồn.** Hợp đồng có thể giải mã byte đúng nhưng ứng dụng Java không biên dịch sau khi đổi getter. Ngược lại, một hệ thống JSON có thể hỏng vì đổi khóa JSON trong khi các cuộc gọi gRPC thuần Protobuf nhị phân vẫn hoạt động bình thường.

Với dịch vụ Spring gRPC, còn cần kiểm tra các quy tắc nghiệp vụ như field bắt buộc về mặt ứng dụng, giá trị mặc định, trạng thái enum và cách server trả **INVALID_ARGUMENT**. Đó là các yêu cầu bổ sung, độc lập với việc field number có hợp lệ hay không.

## 13. Chiến lược thay đổi một field đã phát hành

Giả sử hệ thống trước đó dùng:

~~~proto
message Customer {
  string display_name = 2;
}
~~~

Có ba lựa chọn chính:

**Giữ tên cũ nếu ý nghĩa không đổi.** Khi muốn sửa cách hiển thị ở giao diện, cập nhật frontend hoặc nhãn DTO; giữ nguyên định danh .proto sẽ giảm thay đổi với mã Java, ProtoJSON và công cụ đọc schema.

**Đổi tên .proto nhưng giữ tên JSON cũ khi bắt buộc.** Có thể dùng:

~~~proto
message Customer {
  string full_name = 2 [json_name = "displayName"];
  reserved "display_name";
}
~~~

Điều này giữ số field và khóa JSON được xuất, nhưng vẫn cần sửa Java call site và kiểm tra đầu vào JSON dùng tên .proto cũ.

**Tạo field mới nếu ý nghĩa thay đổi.** Nếu trước kia chỉ lưu tên hiển thị, nay muốn lưu tên pháp lý theo một quy tắc khác, dùng field mới:

~~~proto
message Customer {
  string display_name = 2 [deprecated = true];
  string legal_name = 6;
}
~~~

Trong giai đoạn chuyển tiếp, server có thể đọc cả hai field, ghi nhận phiên bản client và định nghĩa rõ ưu tiên khi cả hai xuất hiện. Khi chắc chắn không còn phụ thuộc dữ liệu cũ, có thể gỡ field cũ và reserve:

~~~proto
message Customer {
  reserved 2;
  reserved "display_name";
  string legal_name = 6;
}
~~~

Nhãn **deprecated** chỉ đánh dấu API không nên dùng tiếp; nó không đổi mã hóa trên wire và không tự di chuyển dữ liệu.

## 14. Kiểm thử với JsonFormat và nhiều phiên bản

Một kiểm thử sử dụng **JUnit 5** và schema đầy đủ ở mục 5:

~~~java
import static org.junit.jupiter.api.Assertions.*;

import com.example.customers.v1.Customer;
import com.google.protobuf.util.JsonFormat;
import org.junit.jupiter.api.Test;

class CustomerJsonTest {
    @Test
    void acceptsJsonNameAndOriginalProtoName() throws Exception {
        Customer original = Customer.newBuilder()
            .setCustomerId("C-42")
            .setDisplayName("Nguyen An")
            .build();

        String json = JsonFormat.printer().print(original);
        assertTrue(json.contains("\"customerID\""));
        assertTrue(json.contains("\"displayName\""));

        Customer.Builder parsed = Customer.newBuilder();
        JsonFormat.parser().merge(
            "{\"customer_id\":\"C-42\",\"display_name\":\"Nguyen An\"}",
            parsed);

        assertEquals(original, parsed.build());
    }
}
~~~

Kiểm thử này chứng minh parser hiểu tên .proto gốc và printer dùng JSON name của schema hiện tại. Nhưng một phép thử với **cùng một phiên bản** chưa đủ kết luận tương thích khi nâng cấp.

Để kiểm tra thay đổi trong dự án thực tế:

1. Lưu payload nhị phân do **client/schema v1** tạo, rồi đọc bằng **reader v2**; làm cả chiều ngược lại.
2. Lưu mẫu ProtoJSON v1, chạy parser v2; xác nhận các khóa JSON cũ vẫn được hỗ trợ hoặc có phương án nâng cấp.
3. Kiểm tra getter/setter Java và các client đang build bằng mã sinh từ v1/v2.
4. Kiểm tra cả trường hợp field không gửi, field optional được đặt thành giá trị mặc định và field/enum chưa biết.
5. Chạy kiểm thử tích hợp với các phiên bản client và server Spring gRPC khác nhau, quan sát dữ liệu thực tế, status và hành vi khi rollout từng phần.

Protoc có thể phát hiện lỗi tĩnh như trùng field number, đụng **reserved** hoặc xung đột tên. Tuy nhiên, công cụ biên dịch không thể tự biết lịch sử nghiệp vụ hoặc dữ liệu mà client cũ đang lưu trữ. Phần đó cần tài liệu thay đổi và fixture kiểm thử.

## 15. Những lỗi thường gặp

| Lỗi | Hậu quả | Cách phòng tránh |
| --- | --- | --- |
| Coi tên .proto là tên JSON mặc định | API JSON dùng khóa khác kỳ vọng. | Hiểu quy tắc lowerCamelCase và kiểm tra đầu ra JsonFormat. |
| Đổi tên field rồi chỉ thử gRPC binary | Bỏ sót lỗi API Java, JSON và descriptor. | Kiểm tra từng lớp hợp đồng. |
| Chỉ reserve tên cũ | Số field cũ có thể bị dùng lại gây hiểu sai binary. | Reserve cả số và tên của field bị xóa. |
| Dùng lại tên cũ cho một nghĩa khác | Tài liệu và client cũ có thể hiểu nhầm. | Reserve tên đã ngừng sử dụng. |
| Dùng json_name để che sự khác biệt ngữ nghĩa | JSON còn khóa cũ nhưng giá trị thay nghĩa. | Tạo field mới nếu giá trị không còn cùng ý nghĩa. |
| Nghĩ reserved sẽ xóa byte hoặc chặn client cũ | Dữ liệu lịch sử vẫn xuất hiện dưới dạng unknown field. | Lập kế hoạch chuyển tiếp và kiểm thử. |
| Bỏ qua unknown JSON để che mọi lỗi | Lỗi gõ tên khóa hoặc thay đổi hợp đồng bị che giấu. | Chỉ dùng ignoringUnknownFields khi có chính sách rõ ràng. |

## 16. Bài tập thực hành

Một dịch vụ đơn hàng ban đầu có schema:

~~~proto
syntax = "proto3";

message Order {
  string order_id = 1;
  string customer_name = 2;
  string legacy_coupon = 3;
  int64 total_cents = 4;
}
~~~

Yêu cầu cho phiên bản kế tiếp:

1. Giữ số **1** và tên .proto **order_id**, nhưng xuất ProtoJSON với khóa **orderID**.
2. Đổi nhãn hiển thị của **customer_name** ở giao diện, giữ nguyên ý nghĩa dữ liệu. Giải thích vì sao có thể không cần đổi field name trong schema.
3. Gỡ **legacy_coupon**, đồng thời bảo vệ **số 3** và **tên legacy_coupon**.
4. Thêm **optional string delivery_note** ở một số field chưa sử dụng; phân biệt không gửi và gửi chuỗi rỗng.
5. Giải thích hậu quả nếu một người dùng lại số **3** cho field **bool is_priority = 3**.
6. Viết kiểm thử ProtoJSON xác nhận khóa **orderID**, khả năng parser nhận **order_id**, và trạng thái **hasDeliveryNote()** trước/sau khi đặt giá trị rỗng.

Một schema đáp ứng yêu cầu cấu trúc:

~~~proto
syntax = "proto3";

message Order {
  string order_id = 1 [json_name = "orderID"];
  string customer_name = 2;
  reserved 3;
  reserved "legacy_coupon";
  int64 total_cents = 4;
  optional string delivery_note = 5;
}
~~~

Đây vẫn là một **thay đổi hợp đồng JSON** đối với client đang chờ khóa **orderId**. Khi có REST gateway hoặc client ngoài, cần kiểm tra và lên kế hoạch chuyển đổi tên JSON trước khi phát hành.

## 17. Ghi nhớ

- **Field name** xác định field trong .proto, **JSON name** xác định thuộc tính ProtoJSON, còn **field number** xác định field trong Protobuf nhị phân.
- Tên .proto nên dùng **lower_snake_case**; ProtoJSON mặc định sử dụng **lowerCamelCase**. Dùng **json_name** khi thực sự cần tên JSON tường minh.
- Đổi tên .proto có thể giữ binary compatibility nếu giữ số/kiểu, nhưng không bảo đảm mã Java, JSON và descriptor tương thích.
- **Reserved number** ngăn tái sử dụng số cũ; **reserved name** ngăn tái sử dụng tên .proto cũ. Khi xóa field đã phát hành, thông thường cần giữ cả hai.
- **Reserved** là ràng buộc schema khi biên dịch, không phải cơ chế xóa hay chuyển đổi dữ liệu runtime.
- Kiểm thử khi thay đổi hợp đồng phải xét **binary**, **ProtoJSON**, **mã Java** và **ngữ nghĩa ứng dụng**, nhất là khi client/server Spring gRPC nâng cấp độc lập.

Hiểu rõ field name, JSON name và reserved field giúp thiết kế hợp đồng Protocol Buffers có khả năng phát triển qua nhiều phiên bản mà vẫn giữ dịch vụ Spring gRPC ổn định từ unary đến streaming RPC.
