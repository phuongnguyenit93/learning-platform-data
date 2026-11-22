# Đánh giá schema evolution trước khi chốt proto

Một hợp đồng Protocol Buffers thường tồn tại lâu hơn một phiên bản ứng dụng. Trong thời gian đó, server Spring gRPC, các client Java, ứng dụng mobile, gateway và những dịch vụ tích hợp có thể được nâng cấp ở các thời điểm khác nhau. Vì vậy, một thay đổi trong file .proto cần được đánh giá theo cách các phiên bản cũ và mới cùng trao đổi dữ liệu, chứ không chỉ theo việc mã nguồn có biên dịch thành công hay không.

Đánh giá schema evolution trước khi chốt proto giúp nhóm xác định phần nào có thể mở rộng an toàn, phần nào cần migration có thời gian chuyển tiếp và phần nào phải tạo phiên bản API mới. Đây là bước thiết kế hợp đồng, không phải công việc dọn dẹp sau khi đã phát hành.

## Mục tiêu

Sau bài học, bạn có thể:

- Phân biệt tương thích binary wire, ProtoJSON, mã nguồn sinh tự động và tương thích ngữ nghĩa.
- Đánh giá một thay đổi khi client cũ gọi server mới và khi client mới gọi server cũ.
- Thiết kế field number, field presence, enum, oneof, service và RPC để hỗ trợ tiến hóa.
- Lập kế hoạch rollout theo từng bước khi có client và server lệch phiên bản.
- Dùng Buf, protoc và integration test để phát hiện breaking change trước khi phát hành.

## 1. Vì sao cần đánh giá schema trước khi chốt?

File .proto định nghĩa cấu trúc message và chữ ký RPC. Từ hợp đồng này, protoc sinh ra các kiểu dữ liệu và stub mà ứng dụng Java sử dụng. Khi chạy, gRPC truyền message Protobuf giữa các tiến trình; hai phía có thể đang dùng hai lần sinh mã từ hai phiên bản schema khác nhau.

Ví dụ, một server đã được nâng cấp có thể nhận request từ client chưa cập nhật trong nhiều tuần. Một batch worker cũ có thể tiếp tục gọi RPC sau khi service đã triển khai bản mới. Nếu thay đổi schema làm một phía không đọc được dữ liệu phía kia gửi, lỗi sẽ xuất hiện ở runtime dù cả hai phiên bản đều biên dịch thành công riêng lẻ.

Một schema cần được đánh giá trên ít nhất bốn lớp:

| Lớp tương thích | Câu hỏi cần trả lời |
| --- | --- |
| Binary wire | Message được tuần tự hóa bằng schema cũ có được schema mới đọc đúng không, và ngược lại? |
| ProtoJSON / TextFormat | Tên field, enum và hình dạng JSON có còn được parser hoặc gateway cũ chấp nhận không? |
| Generated source API | Mã Java và các ngôn ngữ khác có còn biên dịch sau khi sinh lại stub không? |
| Ngữ nghĩa nghiệp vụ | Hai phiên bản có hiểu cùng một giá trị theo cùng đơn vị, ý nghĩa, mặc định và quy tắc xử lý không? |

Một thay đổi có thể an toàn ở binary wire nhưng vẫn phá vỡ mã nguồn Java hoặc làm thay đổi ý nghĩa dữ liệu. Do đó, không nên dùng cụm từ “backward compatible” mà không nói rõ đang xét lớp nào và chiều tương thích nào.

## 2. Xác định chiều tương thích cần bảo vệ

Trong hệ thống phân tán, không thể giả định tất cả client và server được triển khai cùng lúc. Hãy đánh giá tối thiểu hai tình huống:

1. **Client cũ gọi server mới:** server phải đọc được request cũ và client cũ phải hiểu response mà server mới trả về.
2. **Client mới gọi server cũ:** server cũ phải xử lý request mới theo cách an toàn và client mới phải chịu được response chưa có các field mới.

Với thay đổi chỉ thêm field, binary wire thường cho phép hai schema cùng trao đổi message. Tuy vậy, logic nghiệp vụ vẫn có thể không tương thích. Ví dụ, client mới gửi thêm field region, nhưng server cũ bỏ qua field đó rồi thực hiện truy vấn trên region mặc định. RPC có thể thành công nhưng trả dữ liệu sai phạm vi.

Một số tình huống cần phân tích riêng:

- Client mới gọi RPC mới trên server cũ: server cũ thường trả status UNIMPLEMENTED.
- Server mới trả enum value mà client cũ chưa biết: code xử lý enum ở client phải có nhánh dự phòng.
- Client mới cần response field mới nhưng server cũ chưa gửi: client phải xử lý trạng thái field vắng mặt.
- Một gateway parse Protobuf thành JSON rồi serialize lại có thể xử lý unknown field khác với một proxy chỉ chuyển tiếp byte.

Hãy ghi rõ ma trận phiên bản được hỗ trợ, ví dụ client hiện tại và client trước đó có thể kết nối với server hiện tại trong khoảng thời gian nào. Chính sách này quyết định mức độ nghiêm ngặt của review và thời điểm được phép xóa API cũ.

## 3. Giữ ổn định field number và định nghĩa field

### 3.1. Field number là định danh trên wire

Protobuf dùng số field để mã hóa dữ liệu. Tên field giúp con người đọc schema và ảnh hưởng đến mã nguồn sinh tự động, nhưng field number mới là định danh của field trong binary wire format.

~~~proto
syntax = "proto3";

package catalog.v1;

option java_package = "com.example.catalog.v1";

message GetBookRequest {
  string isbn = 1;
}

message Book {
  string isbn = 1;
  string title = 2;
  int64 price_micros = 3;
}
~~~

Khi field đã được sử dụng trong môi trường thực tế:

- Không đổi field number của field hiện có.
- Không dùng lại number của field đã xóa.
- Không đổi type chỉ vì kiểu mới thuận tiện hơn trong Java.
- Không gán cùng một number cho hai field trong cùng message.
- Ưu tiên number từ 1 đến 15 cho field thường xuyên xuất hiện vì nhóm number này có encoding ngắn hơn.

Các number từ 19000 đến 19999 được dành riêng cho implementation Protobuf và không được dùng trong schema.

### 3.2. Xóa field phải reserve cả number và name

Khi một field không còn được sử dụng, hãy xóa nó sau khi đã hoàn thành migration và reserve cả number lẫn tên:

~~~proto
message Book {
  string isbn = 1;
  string title = 2;

  reserved 3;
  reserved "price_micros";
}
~~~

Reserve number ngăn một thay đổi sau này vô tình gán number cũ cho dữ liệu có ý nghĩa khác. Reserve name giúp tránh xung đột khi dùng ProtoJSON hoặc TextFormat. Không tái sử dụng number chỉ vì field cũ đã biến mất khỏi code hiện tại.

### 3.3. Đổi tên field có nhiều lớp tác động

Đổi tên field nhưng giữ nguyên number và wire type thường không làm thay đổi binary wire format. Tuy nhiên, tên field được dùng trong JSON, TextFormat và API được sinh tự động. Vì vậy, đổi isbn thành book_code có thể làm hỏng client parse JSON hoặc mã Java đang gọi getter cũ.

Nếu tên mới chỉ giúp code dễ hiểu hơn, hãy cân nhắc giữ tên wire hiện tại và cải thiện tên biến ở tầng mapping/domain. Nếu bắt buộc đổi tên trên contract, hãy đánh giá riêng tất cả consumer của ProtoJSON, gateway và generated source API.

### 3.4. Không đổi type để tái sử dụng field

Một số kiểu Protobuf có chung wire type ở mức encoding, nhưng điều đó không bảo đảm cùng ý nghĩa hoặc cùng miền giá trị. Chẳng hạn, thay đổi giữa các kiểu số có thể làm mất dữ liệu khi giá trị nằm ngoài miền biểu diễn; thay đổi cách diễn giải số có thể khiến cùng byte trở thành một giá trị khác.

Nếu cần một kiểu dữ liệu hoặc ý nghĩa mới, cách an toàn thường là thêm field mới với number mới, chuyển đổi ở tầng ứng dụng và chỉ ngừng field cũ sau khi migration hoàn tất. Không xem “parse được” là bằng chứng dữ liệu vẫn đúng.

## 4. Đánh giá presence, default và cardinality

### 4.1. Phân biệt vắng mặt với giá trị mặc định

Trong proto3, một scalar field không khai báo optional dùng implicit presence. Giá trị mặc định như 0, false hoặc chuỗi rỗng không cho biết client đã chủ động gửi giá trị đó hay chưa.

Nếu nghiệp vụ cần phân biệt “không cung cấp” với “đặt thành 0”, dùng explicit presence:

~~~proto
message UpdateInventoryRequest {
  string sku = 1;
  optional int32 reorder_level = 2;
}
~~~

Với Java generated code, field có explicit presence cung cấp phương thức kiểm tra field đã được đặt hay chưa, bên cạnh getter trả về giá trị. Điều này hữu ích cho PATCH-like update, cấu hình tùy chọn và các trường hợp cần giữ nguyên giá trị hiện tại khi client không gửi field.

Hãy quyết định presence trước khi phát hành. Nếu một field có nghĩa “giữ nguyên khi không gửi” nhưng code lại coi 0 là lệnh đặt về 0, API có thể gây mất dữ liệu dù wire format hoàn toàn hợp lệ.

### 4.2. Cẩn trọng khi đổi cardinality

Thay đổi giữa singular, repeated và map có thể ảnh hưởng đến generated code, JSON shape và cách ứng dụng xử lý dữ liệu. Map được biểu diễn trên binary wire như repeated entry message, nhưng JSON của map là object trong khi repeated là array. Vì vậy, một thay đổi có vẻ đọc được ở binary wire vẫn có thể phá vỡ consumer JSON.

Không chuyển một field đã phát hành từ singular sang repeated hoặc map chỉ để mở rộng khả năng lưu trữ. Hãy thêm field mới hoặc tạo message/version mới nếu hình dạng dữ liệu cần thay đổi đáng kể.

## 5. Tiến hóa enum và oneof

### 5.1. Enum cần giá trị mặc định rõ ràng

Trong proto3, nên dành giá trị số 0 cho trạng thái chưa xác định:

~~~proto
enum BookState {
  BOOK_STATE_UNSPECIFIED = 0;
  BOOK_STATE_DRAFT = 1;
  BOOK_STATE_PUBLISHED = 2;
}
~~~

Khi thêm trạng thái mới, giữ nguyên number của các giá trị hiện tại và chỉ cấp number mới:

~~~proto
enum BookState {
  BOOK_STATE_UNSPECIFIED = 0;
  BOOK_STATE_DRAFT = 1;
  BOOK_STATE_PUBLISHED = 2;
  BOOK_STATE_ARCHIVED = 3;
}
~~~

Binary wire có thể mang enum number mà client cũ chưa biết. Cách runtime biểu diễn giá trị chưa biết phụ thuộc ngôn ngữ và phiên bản Protobuf; trong Java generated enum proto3 có giá trị UNRECOGNIZED và có API lấy numeric value. Code client cần có nhánh fallback, không giả định mọi enum nhận được đều thuộc danh sách đã biết khi biên dịch.

Không đổi number của enum value và không gán lại number đã xóa. Khi xóa enum value, reserve cả number và tên:

~~~proto
enum BookState {
  reserved 1;
  reserved "BOOK_STATE_DRAFT";

  BOOK_STATE_UNSPECIFIED = 0;
  BOOK_STATE_PUBLISHED = 2;
  BOOK_STATE_ARCHIVED = 3;
}
~~~

Ví dụ trên chỉ minh họa cú pháp reserve; trong một schema đang tồn tại, phải giữ nguyên number của các giá trị còn được sử dụng. Không renumber enum chỉ để tạo danh sách liên tục.

Nếu enum được serialize qua ProtoJSON, tên enum cũng là một phần của contract. Hãy kiểm tra consumer JSON và gateway trước khi đổi tên hoặc xóa giá trị.

### 5.2. Oneof làm thay đổi cách hiểu trạng thái

oneof diễn tả rằng tối đa một trong các field thành viên có giá trị tại một thời điểm:

~~~proto
message PaymentMethod {
  message CardPayment {
    string token = 1;
  }

  message BankTransfer {
    string account_reference = 1;
  }

  oneof method {
    CardPayment card = 1;
    BankTransfer bank_transfer = 2;
  }
}
~~~

Khi một parser gặp nhiều member của cùng oneof trên wire, member xuất hiện sau cùng có thể thay thế member trước. Nếu client cũ không biết một member mới, nó có thể thấy oneof ở trạng thái chưa được đặt dù dữ liệu thực tế chứa member mà phiên bản cũ không nhận diện.

Vì vậy:

- Không tùy tiện chuyển field đang tồn tại vào hoặc ra khỏi oneof.
- Không đổi nhóm oneof của field hiện có.
- Không chia hoặc gộp oneof trong một lần phát hành mà chưa có kế hoạch chuyển tiếp.
- Khi thêm member mới, kiểm tra cách client cũ xử lý trạng thái chưa biết và cách gateway giữ unknown field.

Với thay đổi oneof, cần kiểm thử bằng message được serialize từ cả schema cũ và schema mới; kiểm tra cả dữ liệu sau parse lẫn dữ liệu sau khi serialize lại.

## 6. Đánh giá service, package và chữ ký RPC

Một lời gọi gRPC được định danh bằng tên service đầy đủ và tên method. Vì vậy, thay đổi package Protobuf, tên service hoặc tên method có thể làm thay đổi đường dẫn RPC mà client gọi.

~~~proto
package catalog.v1;

message GetBookRequest {
  string isbn = 1;
}

message Book {
  string title = 1;
}

service CatalogService {
  rpc GetBook(GetBookRequest) returns (Book);
}
~~~

Hãy phân biệt các thay đổi:

| Thành phần | Ảnh hưởng chính |
| --- | --- |
| Protobuf package | Thay đổi tên đầy đủ của service/message và có thể thay đổi đường dẫn RPC |
| Tên service hoặc method | Client cũ gọi đường dẫn cũ; server mới có thể không còn method đó |
| Request/response type của RPC | Thay đổi generated signature và có thể làm client/server không còn tương thích |
| Unary thành client/server/bidirectional streaming hoặc ngược lại | Thay đổi giao thức trao đổi, generated stub và vòng đời RPC |
| Java java_package | Thay đổi package của mã Java sinh ra, dù không trực tiếp đổi binary message |
| java_multiple_files và các option sinh mã | Có thể thay đổi cấu trúc lớp và import của ứng dụng Java |

Không đổi package catalog.v1 chỉ vì muốn sắp xếp lại folder Java. package là một phần của định danh Protobuf và gRPC; java_package là cấu hình sinh mã Java. Hai giá trị có thể khác nhau và cần được review độc lập.

Khi cần thay đổi chữ ký RPC hoặc ngữ nghĩa không tương thích, hãy cân nhắc tạo service hoặc package phiên bản mới, ví dụ catalog.v2. Có thể duy trì song song v1 và v2 trong giai đoạn chuyển đổi, sau đó ngừng v1 theo chính sách hỗ trợ đã công bố.

## 7. Lập kế hoạch rollout khi client và server lệch phiên bản

Schema evolution an toàn cần một thứ tự triển khai phù hợp với chiều dữ liệu. Mô hình expand-and-contract giúp các phiên bản cũ và mới cùng tồn tại trong giai đoạn chuyển tiếp.

### 7.1. Khi thêm field vào request

Nếu client mới sẽ gửi field request mới, server phải được triển khai trước để hiểu field đó:

1. Thêm field mới với number chưa từng sử dụng; giữ nguyên hành vi khi field không được gửi.
2. Triển khai server có thể xử lý cả request cũ và request mới.
3. Kiểm thử và quan sát server với client cũ.
4. Sau khi server đã sẵn sàng, triển khai client bắt đầu gửi field mới.
5. Theo dõi tỷ lệ client đã nâng cấp và xác nhận nhánh xử lý mặc định vẫn hoạt động.

Nếu client gửi field mới trước khi server hiểu ý nghĩa của nó, server cũ có thể bỏ qua field và xử lý theo default. RPC thành công nhưng kết quả có thể không đúng ý định của client.

### 7.2. Khi thêm field vào response

Nếu client mới cần đọc field response mới:

1. Thêm field vào schema và triển khai client có thể xử lý cả trường hợp field có mặt lẫn vắng mặt.
2. Triển khai client mới trước, nhưng vẫn hoạt động được với response từ server cũ.
3. Triển khai server bắt đầu populate field mới.
4. Theo dõi việc sử dụng field và xác nhận các client cũ bỏ qua dữ liệu mới một cách an toàn.

Thứ tự này tránh việc client mới giả định mọi server đã nâng cấp đều trả field mới.

### 7.3. Khi thay đổi ngữ nghĩa hoặc chữ ký RPC

Nếu thay đổi không thể tương thích bằng cách thêm field:

1. Tạo field hoặc RPC mới, hoặc tạo package/service phiên bản mới.
2. Triển khai server hỗ trợ cả đường cũ và đường mới.
3. Nâng cấp client theo từng nhóm và đo mức sử dụng đường mới.
4. Ngừng ghi hoặc ngừng gọi đường cũ sau khi các consumer đã chuyển đổi.
5. Chỉ xóa định nghĩa cũ sau khi hết thời gian hỗ trợ, đã kiểm tra log/telemetry và reserve field number/name nếu xóa field.

Không tái sử dụng một field cũ để mang ý nghĩa mới. Một field như amount không nên lúc thì biểu diễn đồng, lúc thì biểu diễn xu chỉ vì muốn giữ nguyên number. Hãy tạo field mới có tên và đơn vị rõ ràng, chẳng hạn amount_minor_units cùng thông tin currency, rồi chuyển đổi có kiểm soát.

## 8. Kiểm tra breaking change tự động bằng Buf

Review thủ công dễ bỏ sót thay đổi ở nhiều file .proto. Buf cung cấp lint và breaking-change detection để đưa các quy tắc hợp đồng vào CI.

### 8.1. Chọn mức kiểm tra phù hợp

Buf cung cấp bốn category chính:

| Category | Phạm vi kiểm tra |
| --- | --- |
| FILE | Nghiêm ngặt nhất; phát hiện thay đổi ảnh hưởng generated source API theo từng file |
| PACKAGE | Phát hiện thay đổi generated source API theo package |
| WIRE_JSON | Phát hiện thay đổi ảnh hưởng binary wire hoặc JSON |
| WIRE | Chỉ tập trung vào binary wire encoding |

Với schema được chia sẻ cho nhiều consumer và có generated Java code, FILE là lựa chọn bảo thủ phù hợp để bắt cả thay đổi mã nguồn. Nếu mục tiêu chỉ là kiểm soát encoding, WIRE_JSON là mức tối thiểu đáng cân nhắc khi có consumer JSON. WIRE không bảo vệ source API hay JSON contract.

### 8.2. Cấu hình chính sách

Ví dụ cấu hình Buf v2 dùng category FILE:

~~~yaml
version: v2

breaking:
  use:
    - FILE
~~~

Sau đó chạy lint và so sánh schema hiện tại với một baseline đã phát hành:

~~~bash
buf lint
buf breaking --against '.git#branch=main'
~~~

Ví dụ dùng nhánh main làm baseline; trong CI, hãy thay bằng branch, tag, commit hoặc artifact thực sự đại diện cho schema đã phát hành mà consumer đang sử dụng. Không so sánh với một nhánh không ổn định rồi kết luận contract production không có breaking change.

### 8.3. Buf không thay thế kiểm thử ngữ nghĩa

Breaking checker có thể phát hiện nhiều lỗi về field number, type, cardinality, enum, package và RPC signature. Tuy nhiên, công cụ không thể biết amount đã bị đổi từ đồng sang xu, hoặc timeout_seconds giờ được hiểu là mili giây. Những thay đổi ngữ nghĩa cần review thiết kế và test nghiệp vụ.

Tương tự, nếu hệ thống dùng ProtoJSON, REST transcoding hoặc gateway tự chuyển đổi dữ liệu, cần test trực tiếp đường JSON. Một schema vượt qua binary wire check chưa chứng minh mọi gateway và parser JSON đều tương thích.

## 9. Kiểm thử schema evolution trong dự án Spring gRPC

Một pipeline đáng tin cậy nên kiểm tra cả code generation và giao tiếp giữa các phiên bản.

### 9.1. Kiểm tra ở thời điểm build

- Chạy protoc hoặc plugin sinh mã Protobuf/gRPC bằng phiên bản compiler đã khóa trong build.
- Biên dịch toàn bộ generated Java code và các module sử dụng stub.
- Chạy Buf lint và breaking check so với baseline đã phát hành.
- Kiểm tra các ngôn ngữ consumer khác nếu cùng chia sẻ file .proto.
- Review diff của file .proto và generated API khi có thay đổi package hoặc option sinh mã.

### 9.2. Kiểm tra tương thích hai chiều

Giữ một bộ schema cũ làm fixture và sinh message bằng cả schema cũ lẫn schema mới. Kiểm tra các tình huống:

| Writer | Reader | Điều cần xác nhận |
| --- | --- | --- |
| Schema cũ | Schema mới | Field cũ vẫn được đọc đúng; field mới có default/presence đúng |
| Schema mới | Schema cũ | Unknown field được xử lý an toàn; không làm sai nghiệp vụ |
| Client cũ | Server mới | Request cũ vẫn hoạt động và response không làm client cũ lỗi |
| Client mới | Server cũ | Client chịu được field vắng mặt, enum chưa biết hoặc RPC chưa được hỗ trợ |

Khi message đi qua một tiến trình trung gian, hãy kiểm tra cả trường hợp parse rồi serialize lại. Nếu ứng dụng chuyển message thành DTO, JSON hoặc tạo message mới bằng cách copy từng field, unknown field có thể bị mất dù Protobuf runtime có khả năng giữ chúng trong quá trình parse/serialize trực tiếp.

### 9.3. Kiểm tra qua transport gRPC thực

Unit test serialize/parse giúp xác nhận wire format, nhưng không kiểm tra toàn bộ service path. Với Spring gRPC, hãy có integration test chạy server và client qua transport thực tế của ứng dụng để xác nhận:

- Method path và service registration vẫn đúng.
- Unary/streaming signature hoạt động như contract.
- Status khi gọi RPC chưa được server hỗ trợ là phù hợp.
- Client xử lý response thiếu field và enum chưa biết.
- Deadline, cancellation và error mapping không bị thay đổi ngoài dự kiến.

Nên có ít nhất một test dùng stub sinh từ schema của bản phát hành trước để gọi server mới. Nếu hệ thống hỗ trợ client mới kết nối server cũ, hãy có test cho chiều ngược lại.

## 10. Checklist trước khi chốt proto

### Contract và ngữ nghĩa

- [ ] Đã xác định consumer, phiên bản client/server và thời gian hỗ trợ phiên bản cũ.
- [ ] Tên field, đơn vị, timezone, default và quy tắc vắng mặt đã rõ ràng.
- [ ] Đã xác định field nào cần explicit presence.
- [ ] Enum có giá trị 0 mang nghĩa unspecified và code client có fallback cho giá trị chưa biết.
- [ ] Không thay đổi ý nghĩa của field hoặc enum number đã phát hành.

### Binary wire và generated API

- [ ] Field number hiện tại được giữ nguyên và không tái sử dụng.
- [ ] Field/enum value đã xóa được reserve cả number và name.
- [ ] Không đổi type, cardinality hoặc cấu trúc oneof tùy tiện.
- [ ] Đã đánh giá riêng Protobuf package, service, method và Java package.
- [ ] Đã kiểm tra request/response type và streaming shape của từng RPC.

### Rollout và kiểm thử

- [ ] Đã xác định chiều triển khai trước cho request field hoặc response field mới.
- [ ] Client mới xử lý được response từ server cũ.
- [ ] Server mới xử lý được request từ client cũ.
- [ ] CI chạy lint, breaking check và code generation.
- [ ] Có integration test dùng schema/stub từ phiên bản trước.
- [ ] Có kế hoạch quan sát mức sử dụng và ngừng API cũ trước khi xóa contract.

## Kết luận

Chốt một file .proto có nghĩa là chốt cách các tiến trình độc lập hiểu dữ liệu và gọi RPC trong nhiều chu kỳ phát hành. Hãy đánh giá binary wire, JSON, generated source API và ngữ nghĩa nghiệp vụ như những lớp riêng; xác định chiều tương thích cần bảo vệ; rồi thiết kế rollout cho client và server lệch phiên bản. Field number bất biến, reserve khi xóa, enum có fallback và CI kiểm tra breaking change sẽ giúp hợp đồng phát triển mà không buộc toàn bộ hệ thống phải nâng cấp cùng lúc.

## Tài liệu tham khảo

- [Protocol Buffers — Updating A Message Type](https://protobuf.dev/programming-guides/proto3/#updating): thay đổi message, wire-safe changes, field number và unknown fields.
- [Protocol Buffers — Deleting Fields](https://protobuf.dev/programming-guides/proto3/#deleting): reserve field number và name sau khi xóa.
- [Protocol Buffers — Enum](https://protobuf.dev/programming-guides/proto3/#enum): enum value, giá trị chưa biết và reserved values.
- [Protocol Buffers — Proto Best Practices](https://protobuf.dev/best-practices/dos-donts/): các nguyên tắc giữ ổn định schema và enum.
- [Buf — Detecting Breaking Changes](https://buf.build/docs/breaking/): category FILE, PACKAGE, WIRE_JSON và WIRE.
- [Buf — Breaking Change Rules](https://buf.build/docs/breaking/rules/): các quy tắc kiểm tra field, enum, oneof và RPC.
