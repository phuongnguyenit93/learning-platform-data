# Reserved number và reserved name

## Mục tiêu học tập

Sau bài này, bạn có thể:

- Giải thích vì sao field number và field name đã phát hành cần được bảo vệ sau khi xóa.
- Dùng **reserved number** và **reserved name** trong message, enum proto3.
- Khai báo một số, nhiều số hoặc một khoảng số đã ngừng sử dụng.
- Phân biệt tác dụng của reserved với **deprecated**, unknown field và kiểm tra dữ liệu ở runtime.
- Lập kế hoạch thay đổi schema để tránh dữ liệu cũ bị diễn giải thành field hoặc enum value mới.

## 1. Vì sao cần reserved?

Trong Protocol Buffers, **field number** là định danh của field trên binary wire. Tên field được dùng trong schema, mã Java được sinh, descriptor, ProtoJSON và các công cụ như FieldMask. Khi một field đã được phát hành rồi bị xóa, cả số và tên cũ vẫn có thể xuất hiện trong dữ liệu hoặc code của client chưa nâng cấp.

Giả sử phiên bản đầu có:

~~~proto
message Customer {
  string customer_id = 1;
  string legacy_code = 2;
}
~~~

Sau khi bỏ legacy_code, nếu dùng lại số 2 cho một field mới:

~~~proto
message Customer {
  string customer_id = 1;
  string account_reference = 2;
}
~~~

Một client cũ vẫn gửi field số 2 với ý nghĩa legacy_code. Server mới có thể đọc cùng byte đó thành account_reference nếu wire type tương thích. Dữ liệu cũ khi ấy bị hiểu thành ý nghĩa mới mà không nhất thiết tạo lỗi parse.

Để ngăn điều đó, Protobuf có từ khóa **reserved**. Nó ghi nhận số hoặc tên đã ngừng dùng để compiler từ chối việc tái sử dụng trong cùng phạm vi message hoặc enum.

## 2. Reserved number và reserved name bảo vệ điều gì?

Hai loại reservation giải quyết hai rủi ro khác nhau:

| Reservation | Bảo vệ | Nếu không khai báo |
| --- | --- | --- |
| **Reserved number** | Danh tính field trên binary wire hoặc số enum | Dữ liệu cũ có thể bị diễn giải thành field/value mới. |
| **Reserved name** | Tên trong schema, API sinh, ProtoJSON và đường dẫn FieldMask | Tên cũ có thể được gán cho field mới, gây nhầm lẫn hoặc đổi ý nghĩa JSON/text. |

Vì vậy, khi xóa một field đã phát hành, thông thường phải reserve **cả số lẫn tên**. Chỉ reserve số vẫn cho phép tái sử dụng tên cũ với số mới; chỉ reserve tên vẫn cho phép tái sử dụng số cũ với tên mới.

Tên field không được mã hóa trực tiếp trong binary Protobuf, nhưng vẫn là một phần quan trọng của hợp đồng ở các lớp khác. Ví dụ, JSON có thể dùng **legacyCode**, còn FieldMask có thể chứa path **legacy_code**.

## 3. Cú pháp reserved trong message

Trong message, có thể reserve một số, nhiều số hoặc một khoảng số:

~~~proto
message Customer {
  string customer_id = 1;
  string account_reference = 3;

  reserved 2;
  reserved "legacy_code";
}
~~~

Ví dụ trên giữ số 2 và tên legacy_code khỏi bị tái sử dụng trong message Customer.

Có thể gom nhiều số hoặc khoảng số trong một câu lệnh:

~~~proto
message Customer {
  string customer_id = 1;

  reserved 2, 5, 9 to 12;
  reserved "legacy_code", "old_region";
}
~~~

Hai câu lệnh có mục đích riêng:

- Câu reserved chứa số và khoảng số.
- Câu reserved chứa tên được đặt trong dấu ngoặc kép.

Không trộn số và tên trong cùng một câu lệnh reserved. Một khoảng như **9 to 12** bao gồm cả hai đầu mút: 9, 10, 11 và 12.

## 4. Reserved number trong enum

Enum cũng có thể reserve số và tên. Điều này quan trọng vì enum được truyền bằng số nguyên trên wire:

~~~proto
enum CustomerState {
  CUSTOMER_STATE_UNSPECIFIED = 0;
  CUSTOMER_STATE_ACTIVE = 1;
  CUSTOMER_STATE_SUSPENDED = 3;

  reserved 2;
  reserved "CUSTOMER_STATE_LEGACY";
}
~~~

Nếu số 2 và tên CUSTOMER_STATE_LEGACY từng được sử dụng, reservation ngăn schema mới gán lại chúng cho một trạng thái khác.

Enum proto3 phải có giá trị đầu tiên bằng 0. Không xóa hoặc reserve giá trị mặc định số 0 nếu enum vẫn cần tuân thủ quy tắc này; thường giữ một giá trị như **UNSPECIFIED = 0**.

Có thể reserve nhiều số hoặc một khoảng:

~~~proto
enum PaymentState {
  PAYMENT_STATE_UNSPECIFIED = 0;
  PAYMENT_STATE_PENDING = 1;
  PAYMENT_STATE_PAID = 2;

  reserved 3, 5 to 8;
  reserved "PAYMENT_STATE_OLD", "PAYMENT_STATE_ARCHIVED";
}
~~~

Tên enum value cũng cần được giữ lại sau khi xóa. Tên value được dùng trong source code, descriptor và ProtoJSON; số value được dùng trên binary wire.

## 5. Phạm vi của reserved

Reservation chỉ áp dụng trong **message hoặc enum nơi nó được khai báo**:

~~~proto
message Parent {
  reserved 2;

  message Child {
    string child_id = 1;
    string child_note = 2;
  }
}
~~~

reserved 2 ở Parent chỉ bảo vệ số field của Parent. Nó không ngăn Child dùng field số 2. Ngược lại, reservation trong Child cũng không ảnh hưởng field của Parent.

Tương tự, reserved trong một enum chỉ bảo vệ số và tên của enum đó. Nó không tự động áp dụng cho enum khác dù hai enum cùng nằm trong một file hoặc package.

Khi xóa field lồng nhau, hãy đặt reservation bên trong đúng message lồng nhau. Khi xóa enum value, đặt reservation bên trong đúng enum.

## 6. Field number hợp lệ và khoảng số

Field number Protobuf hợp lệ nằm trong khoảng **1 đến 536.870.911**. Số 0 không hợp lệ. Dải **19.000 đến 19.999** được Protobuf dành riêng cho implementation và không được dùng làm field number.

Khi khai báo khoảng reserved:

~~~proto
message HistoricalRecord {
  string id = 1;

  reserved 2 to 10;
  reserved 20 to max;
}
~~~

**to max** kéo dài tới field number tối đa. Dùng khoảng lớn khi một nhóm field cũ đã bị loại bỏ và tổ chức muốn khóa toàn bộ dải số đó.

Không reserve một khoảng rộng hơn lịch sử cần thiết nếu vẫn có kế hoạch thêm field trong phần đó. Reservation là ràng buộc schema lâu dài, nên cần chọn khoảng có chủ đích và ghi nhận lý do trong tài liệu thay đổi.

Đối với enum, giá trị là số nguyên 32-bit. Có thể reserve một số hoặc khoảng số enum đã bỏ, nhưng phải giữ cấu trúc enum hợp lệ, đặc biệt giá trị mặc định 0 trong proto3.

## 7. Xóa field an toàn: ví dụ trước và sau

Phiên bản cũ:

~~~proto
message UserProfile {
  string user_id = 1;
  string display_name = 2;
  string legacy_region = 3;
  string email = 4;
}
~~~

Sau khi legacy_region không còn được hỗ trợ:

~~~proto
message UserProfile {
  string user_id = 1;
  string display_name = 2;
  string email = 4;

  reserved 3;
  reserved "legacy_region";
}
~~~

Nếu muốn bổ sung field mới, chọn số chưa từng được dùng:

~~~proto
message UserProfile {
  string user_id = 1;
  string display_name = 2;
  string email = 4;
  string locale = 5;

  reserved 3;
  reserved "legacy_region";
}
~~~

Không đổi email = 4 thành số 3 chỉ vì số 3 đang trống trong schema hiện tại. Số 3 đã từng được dùng, do đó cần tiếp tục xem nó là đã tiêu thụ.

## 8. Xóa enum value an toàn

Phiên bản cũ:

~~~proto
enum DeliveryState {
  DELIVERY_STATE_UNSPECIFIED = 0;
  DELIVERY_STATE_QUEUED = 1;
  DELIVERY_STATE_SENT = 2;
  DELIVERY_STATE_LEGACY_SENT = 3;
}
~~~

Sau khi bỏ trạng thái cũ:

~~~proto
enum DeliveryState {
  DELIVERY_STATE_UNSPECIFIED = 0;
  DELIVERY_STATE_QUEUED = 1;
  DELIVERY_STATE_SENT = 2;

  reserved 3;
  reserved "DELIVERY_STATE_LEGACY_SENT";
}
~~~

Nếu một enum dùng **option allow_alias = true** và có nhiều tên cùng trỏ tới một số, việc xóa một alias cần cân nhắc riêng. Nếu số đó vẫn được một tên còn hoạt động sử dụng, chỉ reserve **tên alias đã bỏ**; không reserve số vẫn còn hợp lệ.

Không đổi số enum chỉ để sắp xếp lại thứ tự hoặc đổi tên. Số enum là dữ liệu trên wire và có thể được lưu lâu dài trong database, log hoặc message queue.

## 9. Reserved khác deprecated như thế nào?

**deprecated** và **reserved** phục vụ hai giai đoạn khác nhau:

~~~proto
message UserProfile {
  string legacy_region = 3 [deprecated = true];
}
~~~

| Cơ chế | Ý nghĩa | Có còn field trong schema? | Có ngăn tái sử dụng? |
| --- | --- | --- | --- |
| **deprecated = true** | Báo cho người dùng schema rằng field không nên tiếp tục được dùng | Có | Không |
| **reserved number/name** | Khóa số hoặc tên đã bị loại bỏ | Không còn field tương ứng | Có, ở thời điểm biên dịch schema |

Một lộ trình thường dùng:

1. Đánh dấu field cũ là deprecated và công bố kế hoạch loại bỏ.
2. Cập nhật client/server để ngừng đọc/ghi field đó.
3. Xác nhận các consumer quan trọng đã di chuyển.
4. Xóa field khỏi schema.
5. Reserve cả số và tên cũ.

**deprecated = true** không tự xóa accessor Java, không ngăn client gửi field và không khóa số. Chỉ reserve sau khi field đã được gỡ khỏi khai báo.

## 10. Reserved không phải bộ lọc dữ liệu runtime

Một điểm dễ hiểu nhầm: **reserved** chủ yếu là ràng buộc khi biên dịch schema, không phải quy tắc từ chối dữ liệu ở runtime.

Khi parser mới nhận binary từ client cũ:

- Một field number đã reserve không còn được schema mới định nghĩa; dữ liệu có thể được giữ dưới dạng **unknown field**.
- Ứng dụng không đọc được nó qua getter cũ vì getter đã không còn trong lớp Java mới.
- Runtime Protobuf có thể giữ unknown field khi parse rồi serialize lại cùng message, nhưng một bước chuyển đổi qua DTO, JSON hoặc dựng message mới chỉ từ các field đã biết có thể làm mất dữ liệu đó.

Với enum proto3, một số enum không còn được khai báo có thể vẫn được parse như **unknown enum value**. Java thường trả **UNRECOGNIZED** qua getter enum và giữ số gốc qua **getXxxValue()**. Reservation không tự động khiến parser từ chối số đó.

Nếu server không còn chấp nhận một giá trị cũ, phải kiểm tra và từ chối ở tầng ứng dụng, đồng thời ánh xạ lỗi gRPC phù hợp. Không dựa vào reserved để thực hiện validation nghiệp vụ.

## 11. Tên field cũng là một phần của hợp đồng

Tên field không nằm trong binary tag, nhưng ảnh hưởng nhiều giao diện khác:

- Java generated API, ví dụ **getLegacyRegion()** và **setLegacyRegion()**.
- ProtoJSON, ví dụ **legacyRegion**.
- FieldMask path, ví dụ **legacy_region**.
- Descriptor, reflection và công cụ tài liệu hóa schema.
- Protobuf text format và các công cụ thao tác schema.

Nếu chỉ reserve số 3 nhưng tái sử dụng tên legacy_region cho field mới ở số 5, JSON cũ chứa legacyRegion có thể bị hiểu thành dữ liệu mới. Nếu chỉ reserve tên nhưng tái sử dụng số 3, binary cũ có thể bị hiểu thành field mới.

Do đó, khi field đã được phát hành và bị xóa, hãy reserve cả hai định danh. Với enum, cũng giữ lại cả số và tên của giá trị đã bỏ.

## 12. Kiểm tra reservation trong quá trình phát triển

Compiler **protoc** sẽ báo lỗi nếu schema khai báo field number hoặc tên nằm trong vùng reserved:

~~~proto
message UserProfile {
  string user_id = 1;

  reserved 3;
  reserved "legacy_region";

  // Hai khai báo sau phải bị compiler từ chối:
  // string new_region = 3;
  // string legacy_region = 5;
}
~~~

Có thể kiểm tra schema bằng bước generate code trong build. Khi cần kiểm tra độc lập, dùng **protoc** với include path đúng:

~~~bash
protoc \
  --proto_path=src/main/proto \
  --descriptor_set_out=build/schema.pb \
  customer/profile.proto
~~~

Lệnh chỉ thành công khi schema và dependency hợp lệ. Trong CI, nên chạy kiểm tra schema/code generation để phát hiện việc vô tình tái sử dụng số hoặc tên trước khi merge.

Một bộ kiểm tra tiến hóa schema nên xác nhận:

1. Field hoặc enum value đã xóa được reserve cả số và tên.
2. Field mới không dùng số đã phát hành trước đây.
3. Enum mới không tái sử dụng số cũ, kể cả khi tên cũ không còn trong source.
4. Tên field mới không dùng lại tên đã reserve.
5. Client cũ gửi dữ liệu cũ được xử lý theo chính sách unknown field/enum đã định.
6. ProtoJSON và FieldMask không vô tình ánh xạ tên cũ sang field mới.

## 13. Lỗi thường gặp

| Sai lầm | Hậu quả | Cách xử lý |
| --- | --- | --- |
| Xóa field nhưng không reserve số | Số cũ có thể được tái sử dụng và làm sai nghĩa binary | Reserve số đã phát hành. |
| Chỉ reserve số, bỏ tên | Tên cũ có thể được dùng lại cho field khác | Reserve cả tên. |
| Chỉ reserve tên, bỏ số | Số cũ có thể được gán cho field mới | Reserve cả số. |
| Khai báo số và tên trong cùng một câu reserved | Schema không hợp lệ | Tách thành câu lệnh reserved riêng. |
| Đặt reserved ở message cha cho field của message con | Không bảo vệ đúng phạm vi | Đặt trong đúng message/enum sở hữu field. |
| Nghĩ reserved sẽ chặn client cũ gửi dữ liệu | Dữ liệu unknown vẫn có thể đến runtime | Kiểm tra và xử lý ở server. |
| Dùng deprecated thay cho reserved sau khi xóa | Số và tên vẫn có thể bị tái sử dụng | Xóa field rồi reserve cả số và tên. |
| Reserve số enum vẫn còn alias đang hoạt động | Schema xung đột với enum value còn tồn tại | Chỉ reserve tên alias đã bỏ nếu số vẫn được dùng. |

## 14. Bài tập thực hành

Phiên bản cũ của hợp đồng:

~~~proto
message Account {
  string account_id = 1;
  string legacy_number = 2;
  string owner_name = 3;
}

enum AccountState {
  ACCOUNT_STATE_UNSPECIFIED = 0;
  ACCOUNT_STATE_OPEN = 1;
  ACCOUNT_STATE_OLD = 2;
  ACCOUNT_STATE_CLOSED = 3;
}
~~~

Hãy thiết kế phiên bản mới theo yêu cầu:

1. Xóa legacy_number và reserve cả field number 2 lẫn tên legacy_number.
2. Thêm field external_reference bằng số mới, không dùng lại số 2.
3. Xóa enum value ACCOUNT_STATE_OLD, reserve số 2 và tên tương ứng.
4. Giữ nguyên giá trị mặc định enum số 0.
5. Giải thích điều gì xảy ra khi server mới parse binary do client cũ gửi field số 2.
6. Giải thích vì sao reserved không tự từ chối unknown field ở runtime.
7. Viết ví dụ schema cố tình dùng lại số hoặc tên đã reserve và dự đoán lỗi compiler.

**Tiêu chí hoàn thành:** schema mới không tái sử dụng định danh cũ, reservation nằm đúng phạm vi, và có thể giải thích riêng tác động tới binary wire, Java API, ProtoJSON cùng dữ liệu runtime.

## 15. Ghi nhớ

- **Field number** xác định field trên binary wire; không bao giờ tái sử dụng số đã phát hành.
- **Field name** ảnh hưởng source Java, ProtoJSON, FieldMask và descriptor; không tái sử dụng tên đã bỏ.
- Khi xóa field hoặc enum value, reserve **cả số và tên** trong đúng message/enum.
- Có thể reserve nhiều số, khoảng số và nhiều tên; số và tên phải nằm trong các câu lệnh riêng.
- **deprecated** báo ngừng khuyến nghị sử dụng; **reserved** khóa định danh sau khi xóa.
- Reserved bảo vệ schema lúc biên dịch, không thay thế kiểm tra unknown field/enum ở runtime.

Dùng reserved number và reserved name đúng cách giúp hợp đồng Protocol Buffers tiến hóa an toàn, tránh dữ liệu lịch sử bị diễn giải thành field mới và giữ tính nhất quán giữa các phiên bản client/server Spring gRPC.
