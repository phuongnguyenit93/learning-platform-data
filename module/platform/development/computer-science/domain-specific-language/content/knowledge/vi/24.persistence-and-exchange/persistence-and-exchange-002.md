# Tuần tự hóa

## 1. Tuần tự hóa là gì?

Tuần tự hóa (serialization) là quá trình chuyển một giá trị, cấu trúc dữ liệu hoặc trạng thái chương trình thành một chuỗi byte hay văn bản có định dạng để có thể lưu trữ, truyền qua mạng hoặc trao đổi giữa các thành phần. Quá trình ngược lại gọi là giải tuần tự hóa (deserialization): đọc biểu diễn đã lưu hoặc nhận được và khôi phục thành giá trị có thể sử dụng trong chương trình.

Trong một DSL (Domain-Specific Language), tuần tự hóa có thể được dùng cho nhiều loại dữ liệu:

- Giá trị runtime như số, chuỗi, ngày, tiền tệ, danh sách và bản ghi.
- Cấu hình hoặc dữ liệu nghiệp vụ được viết bằng DSL.
- AST hoặc IR của chương trình đã phân tích.
- Rule, workflow, schema hoặc policy đã biên dịch.
- Kết quả thực thi, trạng thái phiên và thông tin trao đổi giữa các dịch vụ.

Ví dụ, một rule được biểu diễn trong DSL:

~~~text
rule high-value-order {
    when order.total > money(10000000, VND)
    then requireManualReview(order.id)
}
~~~

Hệ thống có thể tuần tự hóa cấu trúc rule thành JSON để lưu trong registry:

~~~json
{
  "kind": "Rule",
  "name": "high-value-order",
  "condition": {
    "kind": "GreaterThan",
    "left": { "kind": "MemberAccess", "target": "order", "member": "total" },
    "right": {
      "kind": "Money",
      "amount": "10000000",
      "currency": "VND"
    }
  },
  "action": {
    "kind": "Call",
    "name": "requireManualReview",
    "arguments": [
      { "kind": "MemberAccess", "target": "order", "member": "id" }
    ]
  }
}
~~~

Khi tải lại, hệ thống giải tuần tự hóa JSON thành các node có kiểu, sau đó có thể kiểm tra, hiển thị hoặc thực thi rule. JSON ở đây là một biểu diễn dữ liệu; nó không tự động trở thành mã DSL có thể thực thi.

Tuần tự hóa tạo ra ranh giới giữa dữ liệu trong bộ nhớ và dữ liệu tồn tại bên ngoài process. Vì vậy, thiết kế serialization cần quan tâm đến cấu trúc, kiểu dữ liệu, phiên bản, tính tương thích, tính toàn vẹn và an toàn khi đọc dữ liệu không tin cậy.

## 2. Tuần tự hóa, mã hóa và lưu trữ khác nhau thế nào?

Các thuật ngữ thường xuất hiện cùng nhau nhưng giải quyết những vấn đề khác nhau:

| Khái niệm | Mục đích | Ví dụ |
|---|---|---|
| Serialization | Chuyển cấu trúc dữ liệu thành biểu diễn có thể lưu hoặc truyền | Object thành JSON |
| Deserialization | Khôi phục cấu trúc dữ liệu từ biểu diễn đã tuần tự hóa | JSON thành object |
| Encoding | Biến ký tự hoặc dữ liệu thành dạng byte theo quy ước | UTF-8 |
| Compression | Giảm kích thước dữ liệu | gzip, zstd |
| Encryption | Bảo vệ tính bí mật bằng mật mã | AES-GCM |
| Persistence | Lưu dữ liệu để dùng lại sau này | Ghi file hoặc database |
| Transport | Chuyển dữ liệu giữa các thành phần | HTTP, message queue |

Ví dụ, một object DSL có thể được tuần tự hóa thành JSON text, mã hóa thành UTF-8, nén bằng gzip, rồi gửi qua HTTPS. Serialization định nghĩa cấu trúc JSON; UTF-8 biểu diễn ký tự thành byte; gzip nén byte; TLS bảo vệ kênh truyền. Đây là các lớp có mục tiêu riêng.

Không nên xem JSON là một encoding hoặc xem serialization tự nó bảo đảm dữ liệu đã được bảo mật. Một tệp JSON vẫn có thể chứa bí mật ở dạng đọc được và có thể bị sửa nếu không có cơ chế bảo vệ toàn vẹn.

## 3. Serialization của DSL khác serialization object thông thường ra sao?

Một DSL thường có mô hình dữ liệu mang ý nghĩa miền. Ví dụ, hai giá trị cùng được lưu bằng chuỗi nhưng không nhất thiết thay thế cho nhau:

- CustomerId là định danh khách hàng.
- OrderId là định danh đơn hàng.
- Money<VND> là số tiền theo đơn vị VND.
- LocalDate là ngày lịch không gắn múi giờ.
- Instant là một thời điểm tuyệt đối.

Nếu tuần tự hóa tất cả thành String hoặc Number mà không giữ thông tin kiểu, khi giải tuần tự hóa hệ thống có thể nhầm lẫn hoặc mất ràng buộc miền.

Ví dụ:

~~~json
{
  "customerId": "C-1024",
  "orderId": "C-1024",
  "total": 1250000
}
~~~

Biểu diễn này không nói rõ total dùng loại tiền nào, và hai định danh có thể bị hoán đổi nếu chỉ dựa vào kiểu chuỗi. Một biểu diễn giàu kiểu hơn:

~~~json
{
  "customerId": { "type": "CustomerId", "value": "C-1024" },
  "orderId": { "type": "OrderId", "value": "O-9001" },
  "total": {
    "type": "Money",
    "amount": "1250000",
    "currency": "VND"
  }
}
~~~

Một schema có thể cung cấp kiểu cho từng trường mà không cần lặp tag type trong từng object. Điều quan trọng là hợp đồng dữ liệu phải giữ đủ thông tin để xác thực và khôi phục kiểu miền.

## 4. Tuần tự hóa giá trị và tuần tự hóa chương trình

Trong hệ sinh thái DSL, cần phân biệt ít nhất hai đối tượng:

### 4.1. Tuần tự hóa giá trị

Giá trị runtime là dữ liệu mà chương trình đọc hoặc tạo ra:

~~~text
customer = {
    id: CustomerId("C-1024"),
    active: true,
    balance: money(2500000, VND)
}
~~~

Serialization của giá trị cần định nghĩa cách biểu diễn Boolean, số, chuỗi, ngày, collection, object và kiểu miền. Nó thường được dùng trong API, cache, message, database hoặc log có cấu trúc.

### 4.2. Tuần tự hóa chương trình

Chương trình DSL có thể được biểu diễn bằng AST, IR hoặc bytecode:

~~~text
BinaryExpression
  operator: GREATER_THAN
  left: MemberAccess(order, total)
  right: MoneyLiteral(10000000, VND)
~~~

Serialization của chương trình cần lưu loại node, quan hệ giữa node, literal, symbol reference và có thể cả source location. Nó thường được dùng trong compiler cache, registry rule, IDE, phân phối artifact hoặc thực thi từ xa.

Hai loại serialization có yêu cầu khác nhau. Giá trị runtime cần bảo toàn dữ liệu và kiểu; AST cần bảo toàn cấu trúc cú pháp trừu tượng; bytecode cần bảo toàn hợp đồng instruction và runtime ABI. Không nên dùng cùng một định dạng không có version cho mọi loại chỉ vì chúng đều có thể biểu diễn bằng JSON.

## 5. Các bước trong quá trình serialization

Một quy trình tổng quát:

~~~mermaid
flowchart TD
    A["Object, value hoặc AST"] --> B["Chọn schema và phiên bản"]
    B --> C["Kiểm tra dữ liệu"]
    C --> D["Chuyển thành mô hình tuần tự"]
    D --> E["Encoder / Serializer"]
    E --> F["Bytes hoặc text"]
    F --> G["Lưu trữ hoặc truyền đi"]
    G --> H["Decoder / Deserializer"]
    H --> I["Kiểm tra cấu trúc và phiên bản"]
    I --> J["Khôi phục kiểu và giá trị"]
    J --> K["Validation theo miền"]
~~~

Các bước chính:

1. Xác định đối tượng và schema cần lưu.
2. Kiểm tra các giá trị có thể biểu diễn.
3. Chuyển object hoặc AST thành mô hình tuần tự.
4. Encode thành văn bản hoặc byte.
5. Lưu hoặc gửi qua transport.
6. Khi nhận, decode và kiểm tra định dạng.
7. Giải tuần tự hóa thành cấu trúc có kiểu.
8. Kiểm tra các ràng buộc miền và quyền sử dụng trước khi xử lý tiếp.

Deserialization không nên chỉ dừng ở việc parse được cú pháp. Dữ liệu có thể hợp lệ theo JSON nhưng không hợp lệ theo schema hoặc quy tắc nghiệp vụ.

## 6. Các định dạng tuần tự hóa phổ biến

Không có định dạng tốt nhất cho mọi tình huống. Việc lựa chọn phụ thuộc vào khả năng đọc, kích thước, tốc độ, schema, khả năng tương thích và hệ sinh thái công cụ.

| Định dạng | Dạng | Điểm mạnh | Điểm cần cân nhắc |
|---|---|---|---|
| JSON | Văn bản | Phổ biến, dễ đọc, hỗ trợ rộng | Kiểu dữ liệu hạn chế, verbose |
| YAML | Văn bản | Dễ viết cấu hình, hỗ trợ comment | Quy tắc thụt lề và kiểu ngầm có thể gây nhầm |
| XML | Văn bản | Có namespace, schema và hệ sinh thái lâu đời | Dài và nhiều cú pháp |
| Protocol Buffers | Nhị phân | Schema rõ, gọn, hỗ trợ code generation | Cần quản lý field number và schema |
| Avro | Nhị phân hoặc JSON | Schema evolution và data pipeline | Cần quản lý writer/reader schema |
| CBOR | Nhị phân | Biểu diễn gọn, hỗ trợ nhiều kiểu hơn JSON | Khó đọc trực tiếp |
| MessagePack | Nhị phân | Gần mô hình JSON nhưng gọn hơn | Quy ước schema và kiểu miền do ứng dụng quản lý |
| Java Object Serialization | Nhị phân | Tích hợp với object graph Java | Rủi ro bảo mật và ràng buộc chặt với class |

### 6.1. JSON

JSON thường phù hợp với API, cấu hình và dữ liệu trao đổi giữa các dịch vụ:

~~~json
{
  "ruleId": "high-value-order",
  "enabled": true,
  "threshold": {
    "amount": "10000000",
    "currency": "VND"
  }
}
~~~

JSON có các kiểu cơ bản như object, array, string, number, Boolean và null. Nó không định nghĩa sẵn Date, Decimal chính xác, Money, enum hoặc reference. Những kiểu này cần quy ước ở tầng schema.

Với dữ liệu tiền tệ hoặc số thập phân cần độ chính xác, biểu diễn bằng string hoặc cấu trúc amount/currency có thể an toàn hơn phụ thuộc vào number của JSON và cách runtime xử lý floating point.

### 6.2. YAML

YAML thường được dùng cho cấu hình dễ đọc:

~~~yaml
rule:
  id: high-value-order
  enabled: true
  threshold:
    amount: "10000000"
    currency: VND
~~~

YAML hỗ trợ comment và nhiều kiểu scalar, nhưng một số parser có thể diễn giải ngày, số hoặc Boolean theo quy tắc khác nhau. Với dữ liệu cần trao đổi ổn định giữa nhiều implementation, nên định nghĩa schema và quy ước kiểu rõ ràng.

### 6.3. XML

XML biểu diễn dữ liệu theo cây phần tử và thuộc tính:

~~~xml
<rule id="high-value-order">
    <enabled>true</enabled>
    <threshold currency="VND">10000000</threshold>
</rule>
~~~

XML phù hợp khi cần namespace, schema validation, tài liệu có cấu trúc hoặc tương thích với hệ thống hiện có. Cần chú ý xử lý external entity và cấu hình parser an toàn khi đọc XML không tin cậy.

### 6.4. Protocol Buffers

Protocol Buffers dùng schema để định nghĩa message và field number:

~~~proto
syntax = "proto3";

message Money {
  string amount = 1;
  string currency = 2;
}

message RuleMetadata {
  string rule_id = 1;
  bool enabled = 2;
  Money threshold = 3;
}
~~~

Field number là một phần của wire format. Khi đã phát hành schema, không được tái sử dụng field number của trường đã xóa cho một ý nghĩa khác. Trường cũ nên được đánh dấu reserved nếu không còn dùng.

### 6.5. Định dạng nhị phân khác

CBOR và MessagePack có thể giảm kích thước so với JSON và phù hợp với thiết bị hoặc giao thức cần hiệu quả. Avro thường hữu ích trong data pipeline vì writer schema và reader schema có thể được dùng để xử lý schema evolution.

Dù chọn định dạng nhị phân, hệ thống vẫn cần schema, versioning, validation và chính sách tương thích. Dữ liệu gọn hơn không tự động có nghĩa là dữ liệu an toàn hoặc dễ nâng cấp hơn.

## 7. Schema và hợp đồng dữ liệu

Schema mô tả cấu trúc và ràng buộc của dữ liệu có thể tuần tự hóa. Nó có thể quy định:

- Tên và kiểu trường.
- Trường bắt buộc hoặc tùy chọn.
- Giá trị mặc định.
- Kiểu collection và kiểu phần tử.
- Enum và tập giá trị hợp lệ.
- Ràng buộc độ dài, miền giá trị và pattern.
- Cách biểu diễn null hoặc giá trị vắng mặt.
- Version của schema.

Ví dụ schema khái niệm:

~~~text
RuleDefinition {
    id: String              required
    enabled: Boolean        default true
    threshold: Money        required
    description: String     optional
}
~~~

Khi serializer tạo dữ liệu, nó cần tuân theo schema. Khi deserializer đọc dữ liệu, nó cần kiểm tra cấu trúc và kiểu trước khi tạo object. Sau đó, domain validation có thể kiểm tra thêm các quy tắc như threshold không âm hoặc id không rỗng.

### 7.1. Validation theo nhiều lớp

Có thể tách validation thành:

1. **Syntax validation:** byte hoặc text có đúng định dạng JSON, YAML, XML hay không.
2. **Schema validation:** trường, kiểu và cấu trúc có đúng schema không.
3. **Type validation:** dữ liệu có thể chuyển thành kiểu DSL tương ứng không.
4. **Domain validation:** giá trị có thỏa quy tắc nghiệp vụ không.
5. **Authorization validation:** caller có quyền nạp hoặc sử dụng dữ liệu này không.

Ví dụ JSON hợp lệ và khớp schema vẫn có thể chứa currency là UNKNOWN. Nếu miền chỉ cho phép VND, USD và EUR, domain validation cần từ chối giá trị đó.

## 8. Biểu diễn các kiểu dữ liệu đặc biệt

### 8.1. Số nguyên và số thập phân

JSON number không phân biệt rõ Integer, Decimal, BigDecimal hoặc kiểu số có độ rộng cố định. Schema cần xác định miền giá trị và độ chính xác.

Với số thập phân tài chính, có thể lưu dạng chuỗi thập phân chuẩn:

~~~json
{
  "amount": "12345.6700"
}
~~~

Quy ước cần xác định có giữ scale hay không. 12345.6700 có thể có cùng giá trị số với 12345.67 nhưng khác ý nghĩa nếu scale biểu thị độ chính xác đo lường hoặc số chữ số thập phân được nhập.

### 8.2. Ngày và thời gian

Cần phân biệt:

- LocalDate: ngày lịch, ví dụ 2026-11-15.
- LocalTime: giờ trong ngày, không có múi giờ.
- LocalDateTime: ngày và giờ địa phương.
- Instant: thời điểm tuyệt đối trên timeline.
- ZonedDateTime: ngày giờ kèm múi giờ.
- Duration: khoảng thời gian.

Không nên tuần tự hóa tất cả thành chuỗi không có quy ước. Với Instant, dùng định dạng có timezone hoặc UTC rõ ràng. Với LocalDate, không tự thêm timezone vì có thể đổi ngày khi giải mã ở môi trường khác.

### 8.3. Enum

Enum nên được lưu bằng tên ổn định hoặc mã được quản lý:

~~~json
{
  "status": "APPROVED"
}
~~~

Lưu ordinal hoặc vị trí trong danh sách có thể nguy hiểm nếu thứ tự enum thay đổi giữa phiên bản. Nếu dùng mã số, mã đó phải được xem là hợp đồng ổn định và không được tái sử dụng.

### 8.4. Binary data

Nếu định dạng văn bản cần chứa byte, thường dùng Base64:

~~~json
{
  "content": "SGVsbG8="
}
~~~

Base64 chỉ là cách biểu diễn byte thành ký tự; nó không mã hóa bí mật. Dữ liệu lớn có thể được truyền như binary part riêng thay vì nhúng vào JSON để tránh tăng kích thước.

### 8.5. Null, absent và default

Ba trạng thái này cần được phân biệt:

- Field absent: không xuất hiện trong dữ liệu.
- Field null: có mặt nhưng giá trị null.
- Field có giá trị default: được ghi rõ hoặc được reader gán theo schema.

Ví dụ:

~~~json
{}
~~~

khác với:

~~~json
{ "description": null }
~~~

và khác với:

~~~json
{ "description": "" }
~~~

Reader cần biết absent có nghĩa là dùng default, giữ giá trị cũ hay không cập nhật trường. Null có thể là một giá trị hợp lệ hoặc biểu thị xóa trường tùy hợp đồng.

## 9. Tuần tự hóa collection và object graph

Một object có thể tham chiếu tới object khác, tạo thành object graph thay vì một cây đơn giản.

Ví dụ:

~~~text
Order
  customer -> Customer
  items -> List<OrderItem>
  shippingAddress -> Address
~~~

Nếu hai object cùng tham chiếu một Customer, serializer cần quyết định:

- Lặp lại dữ liệu Customer tại mỗi vị trí.
- Ghi một ID rồi tham chiếu tới object dùng chung.
- Chỉ tuần tự hóa một phần quan hệ.

Lặp dữ liệu làm biểu diễn đơn giản nhưng có thể tạo bản sao không đồng bộ. Dùng ID/reference giữ được quan hệ nhưng cần cơ chế resolve khi giải tuần tự hóa.

### 9.1. Chu trình tham chiếu

Object graph có thể có chu trình:

~~~text
Customer.defaultOrder -> Order
Order.customer -> Customer
~~~

Serializer dạng cây đơn giản có thể lặp vô hạn nếu không theo dõi object đã gặp. Các chiến lược:

- Cấm chu trình và báo lỗi.
- Chuyển quan hệ thành ID.
- Dùng reference table hoặc object identity.
- Tuần tự hóa graph với bước tạo object trước rồi liên kết reference sau.

Với dữ liệu trao đổi qua nhiều dịch vụ, mô hình ID/reference thường rõ hơn việc cố bảo toàn identity của object trong bộ nhớ.

### 9.2. Collection và thứ tự

List có thứ tự nên serialization cần giữ thứ tự phần tử. Set có thể không có thứ tự; nếu cần output xác định, serializer nên sắp xếp theo khóa ổn định hoặc định nghĩa thứ tự canonical. Map cần quy định kiểu key và cách xử lý key trùng sau khi normalize.

## 10. Tuần tự hóa AST và IR của DSL

Khi cần lưu chương trình đã phân tích, có thể tuần tự hóa AST hoặc IR thay vì lưu lại source text. Điều này giúp giảm thời gian parse khi nạp, hỗ trợ phân phối rule đã kiểm tra hoặc lưu compiler cache.

Ví dụ AST:

~~~json
{
  "nodeType": "BinaryExpression",
  "operator": "GREATER_THAN",
  "left": {
    "nodeType": "MemberAccess",
    "target": { "nodeType": "Identifier", "name": "order" },
    "member": "total"
  },
  "right": {
    "nodeType": "IntegerLiteral",
    "value": "1000000"
  }
}
~~~

Một AST serialization cần quyết định:

- Tên node và version của node schema.
- Cách biểu diễn operator và literal.
- Quan hệ cha/con hoặc danh sách child.
- Symbol reference: lưu tên, ID hay đường dẫn module.
- Source location có được giữ hay không.
- Comment và trivia có được giữ hay không.
- Metadata của compiler có phải dữ liệu công khai hay chỉ là cache.

### 10.1. AST không nhất thiết là định dạng lưu trữ ổn định

AST nội bộ có thể thay đổi thường xuyên khi grammar hoặc compiler được tái cấu trúc. Nếu lưu AST lâu dài, mọi thay đổi node có thể đòi hỏi migration.

Một lựa chọn là định nghĩa một **serialized IR** riêng có schema ổn định hơn AST nội bộ. Compiler chuyển AST sang serialized IR khi lưu, và chuyển IR về mô hình thực thi hiện tại khi nạp.

Điều này tách vòng đời nội bộ của compiler khỏi hợp đồng artifact lưu trữ.

### 10.2. Lưu source hay lưu AST?

| Cách lưu | Ưu điểm | Hạn chế |
|---|---|---|
| DSL source | Dễ đọc, review, chỉnh sửa; có thể parse lại | Cần parser tương thích; parse mỗi lần |
| AST | Giữ cấu trúc đã phân tích; dễ xử lý node | Schema AST có thể thay đổi; có thể mất formatting/comment |
| IR | Phù hợp cho thực thi hoặc tối ưu hóa | Ít gần source; cần version hóa |
| Bytecode | Nạp và chạy nhanh | Gắn với instruction set và runtime ABI |

Với cấu hình do con người chỉnh sửa, source thường là nguồn sự thật tốt. AST/IR/bytecode có thể là artifact dẫn xuất có thể tái tạo. Nếu cần phân phối rule đã xác thực và không muốn parse ở runtime, có thể lưu cả source lẫn artifact cùng metadata version.

## 11. Schema evolution và tương thích dữ liệu

Schema thay đổi theo thời gian. Một reader mới có thể nhận dữ liệu được ghi bởi writer cũ, hoặc ngược lại. Cần phân biệt:

- **Backward-compatible schema change:** reader mới có thể đọc dữ liệu cũ.
- **Forward-compatible schema change:** reader cũ có thể đọc dữ liệu mới ở mức đã định nghĩa.
- **Full compatibility:** cả hai hướng đều được hỗ trợ theo quy tắc.

Ví dụ schema v1:

~~~json
{
  "id": "rule-10",
  "enabled": true
}
~~~

Schema v2 thêm trường description tùy chọn:

~~~json
{
  "id": "rule-10",
  "enabled": true,
  "description": "Review large orders"
}
~~~

Reader v1 có thể bỏ qua trường mới nếu format và parser cho phép. Reader v2 có thể đọc dữ liệu v1 và gán description theo chính sách default hoặc absent.

### 11.1. Thêm trường

Thêm trường tùy chọn thường dễ tương thích hơn thêm trường bắt buộc. Nếu thêm trường bắt buộc, dữ liệu cũ không có trường đó cần được xử lý bằng default, migration hoặc lỗi rõ ràng.

### 11.2. Đổi tên hoặc xóa trường

Đổi tên trực tiếp có thể làm reader cũ không tìm thấy trường. Có thể hỗ trợ alias trong giai đoạn chuyển tiếp:

~~~text
old field: retryCount
new field: maxAttempts
~~~

Reader mới đọc cả hai tên nhưng writer mới chỉ ghi tên mới. Nếu cả hai cùng xuất hiện, phải có quy tắc xung đột rõ.

### 11.3. Đổi kiểu trường

Đổi trường integer thành string hoặc object có thể phá vỡ reader. Nếu cần đổi, nên thêm trường mới, hỗ trợ đọc cả hai dạng và cung cấp migration. Không nên dùng cùng một tên trường với hai kiểu không tương thích mà không có discriminator hoặc schema version.

### 11.4. Enum evolution

Khi thêm giá trị enum mới, reader cũ có thể không nhận biết. Có thể dùng unknown enum value, fallback an toàn hoặc từ chối dữ liệu tùy ngữ cảnh. Với trạng thái ảnh hưởng quyết định nghiệp vụ, bỏ qua giá trị không biết có thể nguy hiểm; nên fail closed nếu không thể xử lý an toàn.

## 12. Versioning của dữ liệu tuần tự hóa

Một payload nên có cách xác định schema hoặc format version:

~~~json
{
  "schemaVersion": 2,
  "rule": {
    "id": "high-value-order",
    "enabled": true
  }
}
~~~

Version có thể được đặt trong payload, header transport, metadata artifact hoặc registry schema. Cần xác định nguồn nào là authoritative nếu có nhiều nơi ghi version.

Một số nguyên tắc:

- Version schema khác version compiler.
- Version language khác version AST hoặc bytecode.
- Không thay đổi ý nghĩa của một version đã phát hành.
- Reader nên từ chối version mới hơn nếu không thể xử lý an toàn.
- Có thể hỗ trợ nhiều writer version trong một khoảng thời gian.
- Migration cần được kiểm thử và có thể quan sát.

Không nên dùng version của package phần mềm để suy ra schema version nếu hai vòng đời thay đổi độc lập.

## 13. Canonical serialization và tính xác định

Hai payload có thể biểu diễn cùng dữ liệu nhưng khác thứ tự field hoặc khoảng trắng:

~~~json
{ "enabled": true, "id": "rule-10" }
~~~

~~~json
{
  "id": "rule-10",
  "enabled": true
}
~~~

Nếu cần so sánh byte, tạo hash, chữ ký số hoặc cache key, cần một dạng biểu diễn canonical (chuẩn hóa) có quy tắc rõ:

- Thứ tự field và key.
- Cách biểu diễn số.
- Cách escape chuỗi.
- Chuẩn hóa Unicode.
- Cách xử lý whitespace.
- Cách biểu diễn null và field vắng mặt.
- Encoding và line ending.

Canonicalization không chỉ là pretty print. Nó là quy tắc xác định duy nhất một byte sequence cho cùng dữ liệu theo mô hình đã chọn.

### 13.1. Deterministic serialization

Serialization xác định tạo cùng output cho cùng giá trị và cùng schema/configuration. Điều này hữu ích cho:

- Hash và cache.
- Chữ ký số.
- So sánh thay đổi.
- Golden test.
- Build và artifact có thể tái lập.

Nếu map không có thứ tự, serializer cần chọn thứ tự ổn định. Nếu số thập phân có nhiều cách viết tương đương, cần quy tắc canonical cho dấu, exponent và trailing zero. Nếu timestamp được sinh từ clock hiện tại, output sẽ không xác định trừ khi timestamp là một phần dữ liệu đầu vào.

### 13.2. Hash và chữ ký

Không nên ký payload trước khi có quy tắc canonicalization. Hai biểu diễn byte khác nhau của cùng dữ liệu sẽ tạo hash khác nhau. Quy trình an toàn thường là:

1. Xác thực dữ liệu theo schema.
2. Canonicalize theo một chuẩn xác định.
3. Tính hash trên byte canonical.
4. Ký hash hoặc byte theo thuật toán được chọn.
5. Khi nhận, canonicalize và xác minh chữ ký trước khi tin nội dung.

Chữ ký số chứng minh nguồn gốc và tính toàn vẹn theo khóa; nó không thay thế authorization hoặc validation miền.

## 14. Streaming serialization và dữ liệu lớn

Với dữ liệu nhỏ, serializer có thể tạo toàn bộ byte array trong bộ nhớ. Với dữ liệu lớn, streaming giúp ghi hoặc đọc từng phần:

~~~text
DSL records
    |
    v
Streaming encoder
    |
    v
Output stream
    |
    v
File / network
~~~

Ưu điểm:

- Giảm bộ nhớ đỉnh.
- Có thể xử lý dữ liệu lớn hơn bộ nhớ khả dụng.
- Bắt đầu truyền trước khi toàn bộ dữ liệu được tạo.
- Phù hợp với file, network và data pipeline.

Đổi lại, streaming có thể làm việc rollback khó hơn nếu lỗi xuất hiện ở giữa. Cần quyết định cách xử lý file ghi dở, message một phần hoặc transaction. Với file, có thể ghi vào file tạm rồi atomic rename khi hoàn tất. Với network, cần framing hoặc length prefix để receiver biết ranh giới message.

### 14.1. Framing

Một stream byte không tự nói đâu là điểm kết thúc của mỗi message. Giao thức có thể dùng:

- Delimiter, ví dụ newline cho NDJSON.
- Length prefix, ghi độ dài trước payload.
- Container format có record boundary.
- Kết nối hoặc stream riêng cho mỗi message.

Không nên dùng delimiter tùy ý nếu delimiter có thể xuất hiện trong payload mà không có escaping rõ ràng.

### 14.2. Partial failure và backpressure

Khi truyền dữ liệu lớn, receiver có thể chậm hơn sender. Hệ thống cần backpressure để tránh tích lũy buffer không giới hạn. Cần xác định timeout, retry, checkpoint và cách tiếp tục sau khi kết nối bị ngắt.

Retry một message có side effect cũng cần idempotency key hoặc cơ chế deduplication để tránh xử lý lặp.

## 15. Bảo mật khi giải tuần tự hóa

Deserialization là ranh giới nhận dữ liệu từ bên ngoài. Dữ liệu có thể được tạo bởi client không tin cậy, bị sửa trên đường truyền hoặc được tạo bằng phiên bản khác. Vì vậy, không nên mặc định payload hợp lệ chỉ vì parser đọc được.

Các rủi ro:

- Payload quá lớn làm cạn bộ nhớ.
- Collection lồng sâu gây stack overflow.
- Số lượng node hoặc reference quá nhiều.
- Chuỗi cực dài gây chi phí xử lý cao.
- Kiểu dữ liệu không được phép được khởi tạo.
- Reference cycle hoặc graph phức tạp gây vòng lặp.
- Deserialization kích hoạt constructor, callback hoặc side effect ngoài dự kiến.
- Payload chứa dữ liệu nhạy cảm bị ghi vào log.

Biện pháp:

1. Chỉ chấp nhận format và schema đã công bố.
2. Giới hạn kích thước payload, độ sâu lồng, số phần tử và độ dài chuỗi.
3. Dùng allowlist kiểu được phép khôi phục.
4. Tránh cơ chế tự động khởi tạo class tùy ý từ tên trong payload.
5. Validate schema và domain constraints.
6. Kiểm tra authorization trước khi sử dụng dữ liệu hoặc thực thi rule.
7. Xác minh chữ ký hoặc MAC khi cần đảm bảo nguồn gốc và toàn vẹn.
8. Không log toàn bộ payload nếu có thể chứa bí mật hoặc dữ liệu cá nhân.

### 15.1. Java native serialization

Java native serialization có thể khôi phục object graph và hỗ trợ hook tùy chỉnh. Tuy nhiên, đọc object stream không tin cậy có thể kích hoạt quá trình khởi tạo hoặc logic trong class và tạo rủi ro gadget chain.

Với dữ liệu từ bên ngoài, thường nên ưu tiên format dữ liệu có schema rõ như JSON với DTO được kiểm soát hoặc Protocol Buffers. Nếu phải đọc Java serialization cũ, cần filter class, giới hạn graph và áp dụng chính sách chặt chẽ theo hướng dẫn của nền tảng.

### 15.2. Không dùng deserialization như authorization

Một payload có trường role = "ADMIN" không chứng minh caller có quyền admin. Quyền phải được xác thực từ identity và policy đáng tin cậy ở phía server. Dữ liệu được giải tuần tự hóa chỉ là input, không phải bằng chứng quyền hạn.

## 16. Serialization và dữ liệu nhạy cảm

Khi lưu hoặc truyền object DSL, cần quyết định trường nào được phép xuất hiện:

- Password, API key và token không nên được serialize vào artifact thông thường.
- Thông tin cá nhân chỉ nên được đưa vào payload nếu cần thiết.
- Log và trace cần masking hoặc redaction.
- Backup và file cache có thể cần mã hóa ở tầng lưu trữ.
- Transport cần xác thực và bảo vệ kênh truyền.

Encryption at rest và encryption in transit giải quyết các rủi ro khác nhau. Nếu cần bảo vệ payload độc lập với transport hoặc lưu trữ, có thể dùng envelope encryption. Key management, rotation và quyền giải mã phải được thiết kế riêng.

Không nên tự tạo thuật toán mã hóa hoặc ký số. Dùng thư viện và giao thức đã được kiểm chứng, cấu hình đúng mode và quản lý khóa an toàn.

## 17. Hiệu năng và kích thước dữ liệu

Serialization có thể chiếm CPU và bộ nhớ đáng kể khi object graph lớn hoặc message được gửi thường xuyên.

Các yếu tố ảnh hưởng:

- Kích thước object graph.
- Số lượng allocation khi tạo buffer và string.
- Reflection hoặc metadata lookup.
- Chuyển đổi kiểu số, ngày và Unicode.
- Compression.
- Copy giữa các buffer.
- Schema resolution.

Một số cách tối ưu:

- Dùng streaming cho dữ liệu lớn.
- Tái sử dụng buffer khi thư viện cho phép an toàn.
- Tránh serialize field không cần cho use case.
- Dùng schema và code generation nếu reflection là nút thắt.
- Chọn binary format khi băng thông hoặc storage là vấn đề.
- Nén payload lớn nếu chi phí CPU hợp lý.
- Đo latency, throughput, allocation và kích thước thực tế.

Không nên chọn định dạng nhị phân chỉ vì nó có vẻ nhanh hơn. Với payload nhỏ, thời gian mạng hoặc database có thể lớn hơn nhiều so với chi phí parse JSON. Cần benchmark theo dữ liệu và workload thực tế.

## 18. Serialization trong API và message exchange

Khi DSL trao đổi dữ liệu qua API hoặc message broker, serialization trở thành một phần của wire contract.

Một message có thể có envelope:

~~~json
{
  "messageType": "RuleEvaluationRequested",
  "schemaVersion": 2,
  "messageId": "msg-812",
  "correlationId": "req-551",
  "payload": {
    "ruleId": "high-value-order",
    "orderId": "O-9001"
  }
}
~~~

Envelope giúp receiver biết loại message, schema version và cách liên kết với request. Payload chứa dữ liệu miền.

Giao thức cần quy định:

- Message type và schema version.
- Encoding và content type.
- Framing hoặc message boundary.
- Kích thước tối đa.
- Timeout và retry.
- Idempotency và duplicate delivery.
- Unknown field hoặc unknown message type được xử lý thế nào.
- Authentication, authorization và audit.

Nếu message có side effect, receiver nên xử lý duplicate delivery an toàn. Message ID hoặc idempotency key có thể hỗ trợ deduplication, nhưng cần lưu trạng thái xử lý theo một chính sách nhất quán.

## 19. Lỗi serialization và deserialization

Các lỗi thường gặp:

| Loại lỗi | Nguyên nhân | Hướng xử lý |
|---|---|---|
| Malformed payload | JSON/XML/nhị phân không đúng format | Báo vị trí hoặc byte offset |
| Schema mismatch | Thiếu trường bắt buộc hoặc sai kiểu | Nêu trường và kiểu kỳ vọng |
| Unsupported version | Reader không hỗ trợ schema version | Yêu cầu phiên bản tương thích hoặc migration |
| Unknown enum | Giá trị enum mới chưa biết | Fallback an toàn hoặc từ chối |
| Numeric overflow | Giá trị vượt miền kiểu đích | Báo giá trị và giới hạn |
| Invalid encoding | Byte không hợp lệ theo encoding | Từ chối hoặc áp dụng policy rõ |
| Resource limit | Payload quá lớn hoặc quá sâu | Dừng sớm và báo giới hạn |
| Integrity failure | Chữ ký hoặc MAC không hợp lệ | Không sử dụng payload |

Diagnostic cần phân biệt lỗi cú pháp của format với lỗi schema và lỗi miền. Ví dụ, JSON parser có thể thành công nhưng trường amount là chuỗi "abc"; schema có thể chấp nhận string nhưng domain parser không thể chuyển thành Decimal.

Không nên tự thay giá trị sai bằng 0 hoặc chuỗi rỗng nếu điều đó làm thay đổi ý nghĩa. Fallback chỉ phù hợp khi hợp đồng quy định rõ và giá trị thay thế an toàn.

## 20. Quy trình thiết kế serialization cho DSL

Khi thiết kế cơ chế tuần tự hóa, có thể thực hiện theo trình tự:

1. **Xác định đối tượng cần lưu hoặc truyền.** Giá trị runtime, AST, IR, bytecode, schema hay kết quả thực thi?
2. **Chọn nguồn sự thật.** DSL source, serialized IR hay artifact đã biên dịch?
3. **Định nghĩa schema.** Trường, kiểu, nullability, default và ràng buộc.
4. **Chọn format.** Cân bằng khả năng đọc, kích thước, tốc độ, schema và hệ sinh thái.
5. **Quy định kiểu miền.** Money, Date, Identifier, enum và đơn vị đo phải có biểu diễn rõ.
6. **Thiết kế versioning.** Ghi schema/artifact version và chính sách reader/writer.
7. **Định nghĩa evolution.** Thêm, đổi tên, xóa trường và xử lý unknown field.
8. **Quy định tính xác định.** Thứ tự key, số, Unicode, encoding và canonicalization.
9. **Đặt giới hạn an toàn.** Payload size, nesting depth, object count và kiểu được phép.
10. **Tích hợp transport/storage.** Framing, compression, encryption, retry và atomic write.
11. **Thiết kế diagnostics.** Mã lỗi, vị trí, field và version liên quan.
12. **Kiểm thử tương thích và hiệu năng.** Dùng dữ liệu từ các phiên bản cũ và workload đại diện.

## 21. Kiểm thử serialization

Serialization cần được kiểm thử cả theo cấu trúc, dữ liệu và vòng đời phiên bản.

### 21.1. Round-trip test

Một kiểm thử cơ bản:

~~~text
decoded = deserialize(serialize(value))
assert equivalent(decoded, value)
~~~

Không phải mọi object đều cần giữ identity hoặc trạng thái nội bộ giống hệt. Cần định nghĩa equivalence theo hợp đồng: giá trị, kiểu miền, thứ tự collection, reference hoặc các trường được cam kết.

### 21.2. Golden payload

Lưu các payload mẫu và xác nhận serializer mới tạo output theo quy tắc đã công bố. Với canonical format, có thể so sánh byte chính xác. Với format không canonical, nên parse và so sánh cấu trúc thay vì so sánh whitespace.

### 21.3. Schema compatibility test

Kiểm tra writer cũ với reader mới và các chiều tương thích khác trong ma trận hỗ trợ. Bao gồm field mới, field bị thiếu, enum mới, alias và default.

### 21.4. Negative test

Thử payload sai format, sai kiểu, version không hỗ trợ, chu trình reference, payload quá sâu và dữ liệu vượt giới hạn. Xác nhận hệ thống từ chối an toàn, không crash hoặc thực thi side effect.

### 21.5. Fuzz test

Fuzzing tạo nhiều đầu vào biến thể để tìm lỗi parser, decoder, overflow và resource exhaustion. Với deserializer xử lý dữ liệu không tin cậy, fuzz test đặc biệt hữu ích.

### 21.6. Performance test

Đo thời gian serialize/deserialize, throughput, allocation, peak memory và kích thước payload với dữ liệu nhỏ, trung bình và lớn.

## 22. Ví dụ end-to-end: lưu và nạp rule DSL

Giả sử ứng dụng lưu rule đã kiểm tra vào registry:

~~~text
rule high-value-order {
    when order.total > money(10000000, VND)
    then requireManualReview(order.id)
}
~~~

Quy trình lưu:

1. Parse source thành AST.
2. Kiểm tra tên, kiểu và quyền gọi function.
3. Chuyển AST thành serialized rule model ổn định.
4. Thêm schemaVersion, languageVersion và ruleId.
5. Validate model theo schema.
6. Canonicalize nếu cần hash hoặc chữ ký.
7. Serialize thành JSON hoặc binary.
8. Lưu payload cùng metadata và source gốc.

Khi nạp:

1. Đọc metadata và kiểm tra schemaVersion.
2. Kiểm tra kích thước và tính toàn vẹn payload.
3. Deserialize thành rule model.
4. Validate schema và domain constraints.
5. Chuyển model sang AST/IR nội bộ của runtime hiện tại.
6. Resolve function registry và capability.
7. Thực thi trong runtime context riêng.

Nếu schema version cũ, hệ thống có thể chạy migration trước khi tạo AST. Nếu version quá mới và không thể diễn giải an toàn, nên từ chối với diagnostic rõ thay vì bỏ qua cấu trúc không hiểu.

## 23. Những lỗi thiết kế thường gặp

### Serialize trực tiếp object nội bộ

Thay đổi class hoặc field nội bộ có thể làm dữ liệu đã lưu không đọc được. Dùng DTO hoặc serialized model có schema và version riêng.

### Không giữ kiểu miền

Money, Date, Identifier và enum bị biến thành string hoặc number không có quy ước. Định nghĩa biểu diễn và validation cho từng kiểu.

### Dùng ordinal cho enum

Thay đổi thứ tự enum có thể khiến dữ liệu cũ được diễn giải thành trạng thái khác. Dùng tên hoặc mã ổn định.

### Không phân biệt absent và null

Reader có thể hiểu sai ý nghĩa cập nhật hoặc default. Quy định rõ ba trạng thái và test từng trường hợp.

### Không version hóa payload

Reader không biết cách diễn giải dữ liệu được tạo từ schema cũ. Gắn schema/artifact version và duy trì chính sách tương thích.

### Deserialize kiểu tùy ý

Khôi phục class hoặc object tùy ý từ payload có thể kích hoạt code không mong muốn. Dùng allowlist và mô hình dữ liệu được kiểm soát.

### Không giới hạn kích thước và độ sâu

Payload độc hại hoặc lỗi có thể làm cạn bộ nhớ và stack. Đặt resource limits trước khi tạo object graph lớn.

### Dùng output không canonical cho chữ ký hoặc hash

Thứ tự key và cách viết số khác nhau làm hash không ổn định. Canonicalize trước khi tính hash hoặc ký.

### Cache artifact mà thiếu version key

AST/IR cũ có thể được nạp vào compiler không tương thích. Cache key cần bao gồm schema, compiler hoặc runtime version thích hợp.

### Trộn serialization với encryption

Base64 hoặc JSON không bảo vệ bí mật. Dùng transport security và encryption phù hợp với yêu cầu, đồng thời quản lý khóa riêng.

## 24. Kết luận

Tuần tự hóa chuyển giá trị, cấu trúc dữ liệu hoặc chương trình DSL thành biểu diễn có thể lưu trữ và trao đổi; giải tuần tự hóa khôi phục chúng thành mô hình có thể sử dụng. Trong DSL, đối tượng có thể là giá trị runtime, cấu hình, AST, IR hoặc bytecode, và mỗi loại cần một hợp đồng serialization phù hợp.

Một thiết kế tốt cần schema rõ, biểu diễn kiểu miền chính xác, versioning, quy tắc schema evolution, tính xác định và validation ở nhiều lớp. Định dạng văn bản như JSON hoặc YAML thuận tiện cho con người; định dạng nhị phân có thể hiệu quả hơn cho payload lớn hoặc giao tiếp có schema. Lựa chọn phải dựa trên nhu cầu thực tế và hệ sinh thái hỗ trợ.

Deserialization cần được xem là ranh giới nhận dữ liệu không tin cậy. Hãy giới hạn tài nguyên, chỉ khôi phục kiểu được phép, kiểm tra schema và miền, bảo vệ dữ liệu nhạy cảm và xử lý version không hỗ trợ một cách an toàn. Khi có các quy tắc đó, serialization giúp DSL lưu trữ, phân phối và thực thi chương trình một cách ổn định qua nhiều process và phiên bản.
