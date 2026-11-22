# Payload và kiểu dữ liệu trong DSL API

Một ngôn ngữ đặc tả miền (Domain-Specific Language, DSL) thường trao đổi dữ liệu với ứng dụng, dịch vụ và hệ thống lưu trữ thông qua API. Khi gửi yêu cầu hoặc nhận phản hồi, dữ liệu được tổ chức thành một **payload** có cấu trúc. Payload không chỉ là một chuỗi JSON; nó là hợp đồng mô tả ý nghĩa, kiểu, giới hạn và quy tắc diễn giải dữ liệu giữa bên gửi và bên nhận.

**Payload và kiểu dữ liệu** là nền tảng của một API DSL đáng tin cậy. Payload xác định thông tin được truyền đi, còn kiểu dữ liệu xác định mỗi giá trị có hình dạng và semantics nào. Một payload có thể chứa scalar, object, array, enum, ngày giờ, số thập phân, dữ liệu nhị phân hoặc cấu trúc lồng nhau. Nếu hai phía hiểu khác nhau về null, đơn vị tiền tệ, timezone, encoding hoặc version schema, dữ liệu có thể bị sai dù thông điệp vẫn hợp lệ về cú pháp.

Trong DSL, kiểu dữ liệu thường được khai báo trong schema hoặc model, sau đó được dùng để kiểm tra input, suy luận kiểu biểu thức, tạo tài liệu API, serialize kết quả và validate payload tại runtime. Hợp đồng dữ liệu rõ ràng giúp compiler phát hiện lỗi sớm, ứng dụng tích hợp ổn định và hệ thống có thể nâng cấp mà không làm hỏng consumer đang hoạt động.

## 1. Payload là gì?

### 1.1. Khái niệm

Payload là phần dữ liệu nghiệp vụ được gửi trong một thông điệp. Trong API HTTP, payload thường nằm trong request body hoặc response body. Trong message broker, payload là nội dung của message. Trong DSL, payload có thể là input cho một rule, dữ liệu truy vấn, kết quả quyết định hoặc event được phát ra.

Ví dụ request:

~~~json
{
  "customerId": "C-102",
  "orderTotal": 1250000,
  "currency": "VND",
  "items": [
    {
      "productId": "P-10",
      "quantity": 2
    }
  ]
}
~~~

Payload trên chứa định danh khách hàng, tổng tiền, đơn vị tiền tệ và danh sách sản phẩm. Các trường có kiểu và ý nghĩa riêng; consumer cần hiểu đúng trước khi dùng dữ liệu.

### 1.2. Payload và envelope

Trong một số giao thức, message có phần envelope chứa metadata truyền tải và phần payload chứa nội dung nghiệp vụ.

~~~json
{
  "messageId": "msg-901",
  "eventType": "OrderSubmitted",
  "occurredAt": "2026-11-15T08:30:00Z",
  "payload": {
    "orderId": "O-501",
    "customerId": "C-102",
    "total": {
      "amount": "1250000.00",
      "currency": "VND"
    }
  }
}
~~~

Envelope có thể chứa message ID, loại sự kiện, thời điểm, correlation ID, tenant hoặc schema version. Payload chứa dữ liệu cụ thể của nghiệp vụ. Tách hai phần giúp hệ thống xử lý metadata chung mà không phải hiểu mọi cấu trúc nghiệp vụ.

### 1.3. Payload không đồng nghĩa với toàn bộ request

HTTP request còn có method, path, query parameters, headers và authentication context. Body payload chỉ là một phần của request. Một API có thể lấy version qua header, phân trang qua query parameters và dữ liệu nghiệp vụ qua body.

### 1.4. Payload trong các kiểu API

Payload có thể xuất hiện trong request, response, event, message, command, query result hoặc batch. Mỗi trường hợp có semantics khác nhau. Event thường mô tả điều đã xảy ra, còn command mô tả điều người gửi muốn hệ thống thực hiện.

## 2. Payload contract và schema

### 2.1. Hợp đồng dữ liệu

Payload contract mô tả những gì bên gửi được phép gửi và bên nhận cam kết hiểu. Một contract thường xác định:
- Tên trường và ý nghĩa.
- Kiểu dữ liệu.
- Trường bắt buộc và tùy chọn.
- Nullability.
- Miền giá trị hợp lệ.
- Đơn vị đo và quy tắc làm tròn.
- Định dạng ngày giờ.
- Quy tắc encoding.
- Cấu trúc lồng nhau.
- Schema version.
- Hành vi khi có trường chưa biết.

### 2.2. Schema

Schema là mô tả có cấu trúc của payload. Schema có thể được khai báo bằng cú pháp riêng của DSL, JSON Schema, Protocol Buffers, Avro hoặc một định dạng khác.

Ví dụ schema khái niệm:

~~~yaml
type: OrderRequest
fields:
  orderId:
    type: OrderId
    required: true
  customerId:
    type: CustomerId
    required: true
  note:
    type: String
    required: false
  items:
    type: List<OrderItem>
    required: true
    minItems: 1
~~~

### 2.3. Schema và validation

Schema có thể được dùng ở design time để editor gợi ý, compile time để kiểm tra kiểu, build time để xác minh model, runtime để validate dữ liệu và integration time để consumer kiểm tra response hoặc event.

Một payload có JSON hợp lệ chưa chắc hợp lệ theo schema. Ví dụ trường quantity có thể là chuỗi thay vì số nguyên, hoặc giá trị currency không nằm trong enum được cho phép.

### 2.4. Schema là một phần của API

Schema cần được version hóa và phát hành cùng API. Nếu schema thay đổi mà tài liệu hoặc code generator không cập nhật, client có thể tạo payload không còn hợp lệ.

## 3. Kiểu dữ liệu nguyên thủy

### 3.1. Boolean

Boolean biểu diễn hai trạng thái true và false. Nó phù hợp với cờ hoặc điều kiện rõ ràng:

~~~json
{
  "active": true,
  "verified": false
}
~~~

Không nên dùng chuỗi như "yes", "no", "true" hoặc "false" nếu contract yêu cầu Boolean. Một số hệ thống có logic ba trạng thái do null hoặc missing; cần phân biệt rõ.

### 3.2. Integer

Integer biểu diễn số nguyên, thường dùng cho quantity, số lần, chỉ số hoặc ID dạng số. Cần xác định miền giá trị và độ rộng: 32-bit, 64-bit, unsigned nếu định dạng hỗ trợ hoặc số nguyên có độ lớn tùy ý.

Không nên giả định mọi consumer đều biểu diễn số nguyên rất lớn chính xác. Trong JavaScript, số nguyên vượt giới hạn an toàn của Number có thể mất chính xác.

### 3.3. Decimal

Decimal biểu diễn số thập phân chính xác theo precision và scale được định nghĩa. Nó phù hợp với tiền tệ, tỷ lệ hoặc đại lượng cần làm tròn có kiểm soát.

~~~json
{
  "unitPrice": "1250.50"
}
~~~

Với dữ liệu tài chính, biểu diễn decimal bằng chuỗi có thể tránh việc consumer chuyển qua floating point nhị phân. Contract cần quy định precision, scale và rounding mode.

### 3.4. Float và Double

Float và Double thường dùng IEEE 754 floating point. Chúng phù hợp với đo lường hoặc tính toán khoa học có sai số chấp nhận được. Không nên dùng chúng cho tiền tệ nếu cần kết quả chính xác theo đơn vị nhỏ nhất.

### 3.5. String

String biểu diễn văn bản Unicode. Contract cần xác định encoding, độ dài tối đa, có cho phép chuỗi rỗng không, quy tắc trim hoặc normalize, pattern và cách phân biệt chữ hoa chữ thường.

### 3.6. Byte và binary

Binary data có thể được truyền bằng base64 trong JSON hoặc qua multipart, binary protocol hay object storage reference. Cần xác định giới hạn kích thước, MIME type và cách xác thực nội dung.

### 3.7. Kiểu scalar miền

Không phải mọi giá trị đều nên biểu diễn bằng kiểu nguyên thủy. DSL có thể định nghĩa CustomerId, OrderId, EmailAddress, Money, Percentage, CountryCode hoặc PostalCode. Kiểu miền giúp phân biệt hai chuỗi hoặc số có semantics khác nhau và cho phép kiểm tra constraint chuyên biệt.

## 4. Kiểu dữ liệu phức hợp

### 4.1. Object hoặc record

Object chứa tập trường có tên:

~~~json
{
  "id": "O-501",
  "status": "PENDING",
  "total": {
    "amount": "1250000.00",
    "currency": "VND"
  }
}
~~~

Schema xác định field nào bắt buộc, kiểu từng field và cấu trúc lồng.

### 4.2. Array và list

Array chứa nhiều phần tử theo thứ tự:

~~~json
{
  "tags": ["priority", "online", "gift"]
}
~~~

Schema cần xác định kiểu phần tử, số lượng tối thiểu/tối đa và có cho phép phần tử trùng hay không nếu uniqueness là một phần contract.

### 4.3. Map và dictionary

Map ánh xạ key sang value:

~~~json
{
  "attributes": {
    "color": "blue",
    "size": "large"
  }
}
~~~

Trong JSON, key của object là chuỗi. Nếu DSL cần key kiểu số hoặc enum, serializer cần quy định cách chuyển đổi.

### 4.4. Tuple

Tuple là nhóm giá trị có vị trí cố định:

~~~json
[
  "C-102",
  "An",
  true
]
~~~

Tuple gọn nhưng dễ gây nhầm lẫn nếu consumer không biết thứ tự. Record thường phù hợp hơn cho API công khai vì trường có tên.

### 4.5. Nested object

Payload có thể chứa object lồng nhiều cấp. Độ sâu cần được giới hạn để tránh payload quá phức tạp, khó validate hoặc gây cạn tài nguyên.

### 4.6. Union và polymorphic type

Union biểu diễn một trong nhiều kiểu:

~~~json
{
  "kind": "CARD",
  "card": {
    "last4": "1234"
  }
}
~~~

Discriminator như kind cho biết nhánh đang được sử dụng. Schema cần định nghĩa cách xử lý discriminator không nhận diện để consumer cũ có thể phản hồi an toàn.

### 4.7. Recursive type

Một kiểu có thể tham chiếu chính nó, ví dụ cây danh mục:

~~~text
Category {
    id: CategoryId
    name: String
    children: List<Category>
}
~~~

Recursive payload cần giới hạn độ sâu và kích thước. Schema hoặc serializer phải xử lý chu kỳ tham chiếu nếu mô hình trong bộ nhớ cho phép cycle.

## 5. Required, optional, nullable và missing

### 5.1. Required

Trường required phải xuất hiện trong payload. Nếu không có, validation thất bại. Nếu customerId là required, payload chỉ có orderId sẽ không hợp lệ.

### 5.2. Optional

Trường optional có thể không xuất hiện. Optional không tự động có nghĩa giá trị null được chấp nhận.

~~~json
{
  "orderId": "O-501",
  "customerId": "C-102"
}
~~~

### 5.3. Nullable

Trường nullable có thể xuất hiện với giá trị null:

~~~json
{
  "orderId": "O-501",
  "customerId": "C-102",
  "note": null
}
~~~

### 5.4. Missing khác null

Có ba trạng thái có thể cần phân biệt:
1. Field không có trong payload.
2. Field có mặt với giá trị null.
3. Field có mặt với giá trị cụ thể.

Trong API cập nhật, missing có thể nghĩa là giữ nguyên giá trị cũ; null có thể nghĩa là xóa giá trị hiện tại; giá trị cụ thể nghĩa là cập nhật. Nếu hệ thống gộp missing và null, API có thể không biểu diễn được thao tác patch chính xác.

### 5.5. Optional và nullable trong kiểu DSL

Có thể biểu diễn:

~~~text
note: Optional<String>
email: Nullable<String>
nickname: Optional<Nullable<String>>
~~~

Tên và semantics cụ thể tùy hệ kiểu. Quan trọng là quy định rõ sự khác biệt giữa không có giá trị và giá trị null.

### 5.6. Default value

Một trường có thể có default khi bị thiếu. Cần xác định default được áp dụng ở client, server, compiler hay persistence layer. Nếu nhiều lớp cùng áp dụng, kết quả có thể khác nhau.

### 5.7. Boolean ba trạng thái

Nếu một điều kiện có thể là true, false hoặc unknown, cần dùng kiểu biểu diễn rõ. Không nên ép unknown thành false nếu điều đó làm thay đổi quyết định nghiệp vụ.

## 6. Enum và kiểu miền

### 6.1. Enum

Enum giới hạn giá trị trong một tập lựa chọn:

~~~text
enum OrderStatus {
    DRAFT
    PENDING
    PAID
    CANCELLED
    REFUNDED
}
~~~

### 6.2. Biểu diễn enum trong payload

Enum thường được serialize thành chuỗi ổn định:

~~~json
{
  "status": "PAID"
}
~~~

Tránh serialize bằng ordinal hoặc vị trí số nếu thứ tự enum có thể thay đổi giữa phiên bản.

### 6.3. Unknown enum value

Consumer cũ có thể nhận một giá trị enum mới từ producer mới. Contract cần quy định từ chối, giữ raw string, ánh xạ sang UNKNOWN hoặc bỏ qua field nếu an toàn. Với event và API cần tương thích tiến, khả năng giữ unknown value có thể hữu ích.

### 6.4. Enum và trạng thái chuyển tiếp

Enum chỉ mô tả tập giá trị. Quy tắc trạng thái hợp lệ như PENDING chuyển sang PAID cần được mô tả riêng trong state machine hoặc business rules.

### 6.5. Value object

Value object kết hợp giá trị và invariant:

~~~text
Money {
    amount: Decimal
    currency: CurrencyCode
}
~~~

Constructor hoặc validator có thể đảm bảo amount hợp lệ, currency được hỗ trợ và phép toán không trộn đơn vị không tương thích.

## 7. Số, đơn vị và độ chính xác

### 7.1. Precision và scale

Decimal thường được mô tả bằng precision và scale. Ví dụ Decimal(18,2) có tối đa 18 chữ số, trong đó 2 chữ số sau dấu thập phân. Schema cần xác định có làm tròn khi input vượt scale hay từ chối payload.

### 7.2. Rounding mode

Các cách làm tròn như HALF_UP, HALF_EVEN, FLOOR và CEILING có thể cho kết quả khác nhau. Nếu payload chứa giá trị đã tính, producer và consumer cần thống nhất quy tắc.

### 7.3. Currency

Money cần có currency rõ ràng. Không nên giả định mọi amount đều là VND hoặc mọi currency có hai chữ số thập phân.

### 7.4. Unit of measure

Đại lượng như chiều dài, khối lượng, nhiệt độ hoặc thời lượng cần đơn vị:

~~~json
{
  "distance": {
    "value": "12.5",
    "unit": "KM"
  }
}
~~~

### 7.5. Conversion

Chuyển đổi đơn vị cần quy định độ chính xác và thời điểm áp dụng. Currency conversion còn phụ thuộc tỷ giá, nguồn tỷ giá và thời điểm định giá.

### 7.6. Overflow và range

Schema có thể đặt minimum, maximum hoặc giới hạn độ lớn. Runtime cần xử lý overflow theo hợp đồng, không để giá trị wrap hoặc mất chính xác âm thầm.

### 7.7. NaN và Infinity

JSON chuẩn không biểu diễn NaN hoặc Infinity như number thông thường. Nếu hệ thống cần các giá trị này, phải định nghĩa cách mã hóa riêng hoặc từ chối khi serialize.

## 8. Ngày, giờ và thời gian

### 8.1. Date

Date biểu diễn ngày lịch, không nhất thiết gắn timezone:

~~~json
{
  "dueDate": "2026-12-01"
}
~~~

### 8.2. Time

Time biểu diễn thời điểm trong ngày:

~~~json
{
  "opensAt": "09:30:00"
}
~~~

### 8.3. Timestamp hoặc Instant

Instant biểu diễn một thời điểm tuyệt đối, thường serialize theo ISO 8601/RFC 3339 với offset hoặc Z:

~~~json
{
  "occurredAt": "2026-11-15T08:30:00Z"
}
~~~

### 8.4. Local date-time

Local date-time không có timezone. Nó phù hợp với lịch địa phương nhưng không đủ để xác định một instant nếu không có timezone hoặc quy tắc vùng.

### 8.5. Timezone

Timezone như Asia/Ho_Chi_Minh chứa quy tắc lịch sử và daylight saving của vùng. Offset như +07:00 chỉ mô tả độ lệch tại một thời điểm, không thay thế đầy đủ timezone identity.

### 8.6. Khoảng thời gian

Duration biểu diễn độ dài thời gian; Period có thể biểu diễn ngày/tháng/năm theo lịch. Không nên đồng nhất 1 tháng với một số giây cố định.

### 8.7. Precision và test

Timestamp có thể có precision đến giây, mili giây hoặc nano giây. Producer và consumer cần thống nhất. Nếu rule phụ thuộc thời gian hiện tại, nên truyền thời điểm vào payload hoặc inject clock để kết quả có thể tái hiện.

## 9. Identifier và dữ liệu nhạy cảm

### 9.1. Identifier

ID có thể được biểu diễn bằng string, UUID hoặc kiểu opaque riêng. Consumer không nên suy diễn cấu trúc nội bộ của ID nếu contract chỉ cam kết nó là định danh.

### 9.2. Strongly typed identifier

CustomerId và OrderId có thể cùng được serialize thành chuỗi nhưng là hai kiểu khác nhau trong DSL. Điều này ngăn việc truyền nhầm ID giữa các miền.

### 9.3. Email và số điện thoại

EmailAddress và PhoneNumber cần validation theo policy. Không nên coi một regex đơn giản là bằng chứng đầy đủ rằng địa chỉ có thể nhận thư hoặc số điện thoại đang hoạt động.

### 9.4. Personal data

Payload có thể chứa dữ liệu cá nhân. Schema nên phân loại trường nhạy cảm, quy định mục đích sử dụng, quyền truy cập, masking và thời gian lưu trữ.

### 9.5. Secret và token

Secret không nên được đưa vào payload nghiệp vụ thông thường hoặc log. Credential cần đi qua cơ chế xác thực và secret management riêng.

## 10. Binary, file và media payload

### 10.1. Base64

JSON có thể mang binary bằng base64:

~~~json
{
  "fileName": "invoice.pdf",
  "contentType": "application/pdf",
  "contentBase64": "JVBERi0xLjQK..."
}
~~~

Base64 làm kích thước dữ liệu tăng và yêu cầu encode/decode. Nó phù hợp với file nhỏ hoặc giao thức yêu cầu một body JSON duy nhất.

### 10.2. Multipart

Multipart cho phép gửi metadata và binary part riêng. Cách này phù hợp với file lớn nhưng cần xử lý boundary, streaming và giới hạn từng part.

### 10.3. Object storage reference

Với file lớn, payload có thể chứa object key hoặc URL tạm. Reference cần có thời hạn, quyền truy cập và cơ chế thu hồi.

### 10.4. MIME type và file name

Content type mô tả loại nội dung nhưng không xác minh nội dung thực tế. Server cần kiểm tra magic bytes hoặc parse file an toàn khi phù hợp. Tên file từ người dùng là dữ liệu không đáng tin cậy; không dùng trực tiếp làm đường dẫn trên filesystem.

### 10.5. Kích thước và streaming

Upload lớn nên hỗ trợ streaming, quota, timeout và cancellation. Không đọc toàn bộ file vào bộ nhớ nếu không cần thiết.

## 11. Kiểu dữ liệu trong DSL API

### 11.1. Khai báo request type

Một DSL có thể mô tả request:

~~~text
type CreateOrderRequest {
    customerId: CustomerId required
    items: List<OrderItem> minItems(1)
    note: Optional<String>
}
~~~

### 11.2. Khai báo response type

~~~text
type CreateOrderResponse {
    orderId: OrderId
    status: OrderStatus
    total: Money
    createdAt: Instant
}
~~~

### 11.3. Khai báo endpoint

~~~text
endpoint POST /orders {
    request: CreateOrderRequest
    response: 201 CreateOrderResponse
    errors: OrderApiError
}
~~~

Đây là cú pháp minh họa. DSL thực tế cần định nghĩa mapping giữa type declaration, HTTP status, headers và serialization.

### 11.4. Request và response khác nhau

Không nên dùng cùng một type cho mọi chiều nếu quyền và lifecycle khác nhau. CreateOrderRequest có thể cho phép client gửi items và note, trong khi response chứa orderId, status và createdAt do server tạo.

### 11.5. Command, query và event

- Command payload yêu cầu một hành động.
- Query payload mô tả dữ liệu cần tìm.
- Event payload mô tả sự kiện đã xảy ra.

Các loại này có thể dùng chung value type nhưng cần phân biệt semantics, idempotency và retry behavior.

### 11.6. Header và body

Thông tin xác thực, content negotiation, correlation ID hoặc idempotency key thường thuộc header hoặc transport metadata. Dữ liệu nghiệp vụ thuộc body. Không nên nhân đôi cùng một thông tin ở nhiều nơi nếu không có quy tắc ưu tiên.

## 12. Serialization và deserialization

### 12.1. Serialization

Serialization chuyển giá trị trong bộ nhớ thành biểu diễn có thể truyền hoặc lưu trữ, ví dụ JSON, XML hoặc binary format.

### 12.2. Deserialization

Deserialization đọc payload và tạo giá trị có kiểu. Nó cần kiểm tra cấu trúc, kiểu, range, encoding và discriminator.

### 12.3. Mapping

| Kiểu DSL | JSON representation thường gặp |
|---|---|
| Boolean | true/false |
| Integer | number |
| Decimal chính xác | string hoặc number theo contract |
| String | string |
| Date | ISO date string |
| Instant | ISO timestamp string |
| Enum | string ổn định |
| List<T> | array |
| Record | object |
| Binary | base64 hoặc reference |
| Optional<T> | omitted hoặc null theo policy |

### 12.4. Canonical representation

Nếu cần ký payload hoặc tính hash, hai phía cần canonicalization: thứ tự field, encoding, số thập phân, Unicode normalization và cách biểu diễn null phải được xác định.

### 12.5. Unknown fields và duplicate keys

Consumer có thể gặp field mới do producer nâng cấp. Có thể bỏ qua field chưa biết, giữ raw field khi round-trip hoặc từ chối nếu schema yêu cầu strict validation. Chính sách cần phụ thuộc loại API và mức độ an toàn.

Một số JSON parser xử lý key trùng bằng cách lấy giá trị đầu hoặc cuối. API nên từ chối duplicate keys nếu có nguy cơ tạo cách diễn giải khác nhau giữa các thành phần.

### 12.6. Encoding

JSON thường dùng UTF-8 trong trao đổi API. Hệ thống cần xác định charset và xử lý ký tự Unicode, ký tự kết hợp và ký tự điều khiển đúng cách.

## 13. Validation payload

### 13.1. Structural validation

Kiểm tra payload là object, array hay scalar đúng yêu cầu; field bắt buộc có mặt; kiểu field chính xác; cấu trúc lồng đúng và discriminator hợp lệ.

### 13.2. Constraint validation

Kiểm tra min/max, minLength/maxLength, pattern, minItems/maxItems, uniqueItems, range ngày giờ, precision, scale và enum membership.

### 13.3. Semantic validation

Payload có thể đúng schema nhưng sai nghiệp vụ:
- Currency không được hỗ trợ cho thị trường này.
- Ngày kết thúc sớm hơn ngày bắt đầu.
- Quantity bằng zero khi nghiệp vụ yêu cầu số dương.
- Customer không thuộc tenant đang gọi.
- Tổng dòng không khớp tổng hóa đơn.

Semantic validation cần domain model và context, không chỉ JSON schema.

### 13.4. Validation theo phase

Có thể chia:
1. Parse payload.
2. Validate cấu trúc.
3. Chuyển thành kiểu miền.
4. Kiểm tra invariant.
5. Kiểm tra authorization.
6. Thực hiện nghiệp vụ.

Thứ tự này giúp không thực hiện side effect trước khi dữ liệu và quyền đã được xác nhận.

### 13.5. Fail fast và collect errors

API có thể dừng ở lỗi đầu tiên hoặc trả danh sách lỗi. Với form hoặc batch import, collect errors giúp người dùng sửa nhiều lỗi một lần. Với payload nguy hiểm hoặc quá lớn, fail fast có thể tiết kiệm tài nguyên.

### 13.6. Validation client và server

Client validation cải thiện trải nghiệm nhưng không thay thế server validation. Client có thể bị bỏ qua hoặc bị sửa đổi; server luôn phải xác minh payload trước khi tin cậy.

## 14. Error payload

### 14.1. Lỗi có cấu trúc

API nên trả error payload ổn định thay vì chỉ trả chuỗi thông báo:

~~~json
{
  "type": "https://api.example.com/errors/validation",
  "title": "Payload validation failed",
  "status": 400,
  "code": "INVALID_ORDER",
  "detail": "One or more fields are invalid.",
  "errors": [
    {
      "field": "items[0].quantity",
      "code": "MINIMUM_VALUE",
      "message": "Quantity must be greater than zero."
    }
  ],
  "correlationId": "req-702"
}
~~~

### 14.2. Error code và message

Error code nên ổn định để client xử lý logic. Message dành cho con người có thể được dịch hoặc thay đổi cách diễn đạt.

### 14.3. Không tiết lộ nội bộ

Không đưa stack trace, SQL, đường dẫn file, secret hoặc chi tiết hệ thống nội bộ vào error payload công khai. Ghi chi tiết vào log có kiểm soát và liên kết bằng correlation ID.

### 14.4. Lỗi một phần

Với batch payload, API có thể trả kết quả theo từng item:

~~~json
{
  "results": [
    {"index": 0, "status": "ACCEPTED", "id": "O-1"},
    {"index": 1, "status": "REJECTED", "code": "INVALID_CURRENCY"}
  ]
}
~~~

Contract cần quy định batch có atomic hay không và item thất bại có ảnh hưởng item khác không.

## 15. Version hóa schema và payload

### 15.1. Vì sao cần version?

Payload là hợp đồng giữa producer và consumer. Khi thêm, đổi hoặc xóa trường, các client cũ có thể bị ảnh hưởng. Version hóa giúp xác định semantics của thông điệp và quản lý migration.

### 15.2. Version trong path

Ví dụ endpoint có thể dùng /api/v1/orders và /api/v2/orders. Path version dễ quan sát nhưng có thể tạo nhiều endpoint cần duy trì.

### 15.3. Version trong header

Có thể dùng media type hoặc custom header để chọn version. Cần tài liệu hóa cách negotiation và fallback.

### 15.4. Version trong payload

Event hoặc file có thể chứa schemaVersion:

~~~json
{
  "schemaVersion": 2,
  "eventType": "OrderSubmitted",
  "payload": {
    "orderId": "O-501"
  }
}
~~~

### 15.5. Schema registry

Schema registry lưu schema theo subject và version, hỗ trợ kiểm tra tương thích khi publish. Producer và consumer có thể tra schema tương ứng để serialize và deserialize.

### 15.6. Không nhầm schema version với API version

API version có thể bao gồm endpoint, auth và behavior, trong khi schema version chỉ mô tả cấu trúc dữ liệu. Chúng có liên quan nhưng không nhất thiết giống nhau.

## 16. Tương thích ngược và tiến

### 16.1. Backward compatibility

Consumer mới có thể đọc payload do producer cũ tạo. Ví dụ consumer mới hỗ trợ một field optional mà payload cũ không có.

### 16.2. Forward compatibility

Consumer cũ có thể đọc payload mới nếu nó bỏ qua field chưa biết và không gặp thay đổi semantics phá vỡ.

### 16.3. Thay đổi thường ít phá vỡ hơn

- Thêm field optional với default rõ.
- Thêm metadata không bắt buộc.
- Mở rộng enum nếu consumer xử lý unknown value.
- Thêm endpoint mới mà giữ endpoint cũ.

Tính tương thích phụ thuộc parser, schema policy và cách consumer sử dụng dữ liệu.

### 16.4. Thay đổi thường phá vỡ

- Xóa field đang được dùng.
- Đổi tên field.
- Đổi kiểu dữ liệu.
- Đổi required thành optional hoặc ngược lại theo chiều không tương thích.
- Thay nullability.
- Thay đơn vị hoặc rounding.
- Đổi semantics mà không đổi cấu trúc.
- Thay discriminator hoặc enum code.

### 16.5. Expand-contract

Một chiến lược migration:
1. Thêm field mới, giữ field cũ.
2. Producer ghi cả hai trong giai đoạn chuyển tiếp.
3. Consumer chuyển sang field mới.
4. Theo dõi consumer cũ.
5. Ngừng ghi field cũ khi mọi consumer đã chuyển.
6. Xóa field cũ trong version major hoặc schema mới.

### 16.6. Compatibility test

Test các cặp producer/consumer version: producer cũ với consumer mới; producer mới với consumer cũ; payload thiếu field optional; payload có field unknown; enum value mới; decimal hoặc timestamp ở precision mới.

## 17. Payload trong event-driven system

### 17.1. Event payload

Event mô tả sự kiện đã xảy ra:

~~~json
{
  "eventId": "evt-1001",
  "eventType": "OrderPaid",
  "occurredAt": "2026-11-15T08:30:00Z",
  "schemaVersion": 1,
  "payload": {
    "orderId": "O-501",
    "amount": "1250000.00",
    "currency": "VND"
  }
}
~~~

### 17.2. Event immutable

Event thường được xem là dữ liệu lịch sử bất biến. Khi schema thay đổi, không nên âm thầm sửa event cũ; consumer có thể cần upcaster hoặc adapter để đọc nhiều version.

### 17.3. Command payload

Command yêu cầu thực hiện hành động. Nó có thể cần idempotency key, actor và deadline. Command thường chịu authorization khác với event.

### 17.4. Correlation và causation

Correlation ID liên kết các thông điệp trong một workflow. Causation ID chỉ ra thông điệp nào gây ra event hiện tại. Chúng thường thuộc envelope metadata.

### 17.5. Event ordering và duplicate delivery

Nếu thứ tự event quan trọng, cần partition key, sequence number hoặc version aggregate. Timestamp một mình không luôn đủ để xác định thứ tự. Message broker có thể giao event nhiều lần; consumer cần idempotency hoặc deduplication theo event ID khi side effect không được lặp.

## 18. Payload lớn và batch

### 18.1. Batch payload

Batch gộp nhiều item để giảm overhead:

~~~json
{
  "batchId": "batch-22",
  "items": [
    {"externalId": "A1", "quantity": 2},
    {"externalId": "A2", "quantity": 5}
  ]
}
~~~

### 18.2. Atomic và partial success

API cần quy định batch là atomic hay từng item độc lập. Nếu một item lỗi, toàn batch rollback hay những item hợp lệ vẫn được xử lý?

### 18.3. Giới hạn kích thước

Đặt giới hạn tổng byte của body, số item, độ sâu JSON, độ dài string, số field và kích thước binary.

### 18.4. Pagination

Payload response lớn nên hỗ trợ page size, cursor hoặc continuation token. Cursor cần được coi là opaque và có thể hết hạn.

### 18.5. Streaming và compression

Với dữ liệu lớn, streaming tránh giữ toàn bộ body trong memory. Cần hỗ trợ timeout, cancellation, backpressure và giới hạn tổng dữ liệu. Compression giảm kích thước truyền nhưng có thể tạo rủi ro decompression bomb; giới hạn cả kích thước nén và kích thước sau giải nén.

## 19. Bảo mật payload

### 19.1. Validate mọi input

Không tin cậy payload từ client, message broker hoặc file import. Validate cấu trúc, kiểu, miền giá trị và quyền trước khi xử lý.

### 19.2. Mass assignment

Không ánh xạ trực tiếp mọi field trong payload vào object domain hoặc database entity. Client có thể gửi field nội bộ như isAdmin, approvedBy hoặc balance. Chỉ cho phép field được công bố trong request schema.

### 19.3. Injection

Payload có thể chứa dữ liệu dùng trong SQL, expression, template hoặc command. Dùng parameterized query và API an toàn; không nối chuỗi đầu vào thành lệnh thực thi.

### 19.4. Path traversal

File name hoặc path trong payload phải được chuẩn hóa và giới hạn vào vùng lưu trữ cho phép.

### 19.5. Oversized và deeply nested payload

Giới hạn kích thước, độ sâu và số phần tử để tránh cạn CPU, memory hoặc stack.

### 19.6. Sensitive data

Không log toàn bộ payload mặc định. Mask hoặc loại bỏ token, mật khẩu, dữ liệu thanh toán và thông tin cá nhân.

### 19.7. Authorization

Payload có thể chứa customerId hoặc tenantId, nhưng việc client gửi một ID không chứng minh họ có quyền truy cập. Server phải xác thực quyền trên resource.

### 19.8. Replay và idempotency

Với command có side effect, dùng nonce, timestamp, idempotency key hoặc cơ chế chống replay phù hợp.

### 19.9. Content type và parser safety

Kiểm tra Content-Type, giới hạn parser và từ chối định dạng không được hỗ trợ. Không tự động deserialize kiểu tùy ý từ payload không tin cậy.

## 20. Hiệu năng và tối ưu payload

### 20.1. Payload vừa đủ

Chỉ gửi trường consumer cần. Payload quá rộng làm tăng băng thông, latency, chi phí serialize và rủi ro lộ dữ liệu.

### 20.2. Projection và denormalization

API hoặc DSL query có thể hỗ trợ field selection để trả một phần record. Denormalization có thể giảm số request nhưng làm tăng kích thước và nguy cơ dữ liệu không nhất quán.

### 20.3. Binary format và compression

Binary serialization có thể giảm kích thước và tăng tốc parse, nhưng cần schema management và công cụ debug. Compression hữu ích với payload lớn; cần đo CPU và latency sau giải nén.

### 20.4. Cache

Cache key cần tính đến resource identity, schema version, tenant, authorization và query parameter ảnh hưởng kết quả. Không cache response nhạy cảm theo key thiếu phạm vi.

### 20.5. Payload size budget

Có thể đặt ngân sách kích thước cho từng endpoint hoặc event. Theo dõi P50/P95/P99 thay vì chỉ trung bình để phát hiện payload ngoại lệ.

## 21. Kiểu dữ liệu và code generation

### 21.1. Sinh client model

Từ schema, công cụ có thể sinh class hoặc type cho Java, TypeScript, Kotlin hoặc ngôn ngữ khác. Generated type giúp giảm sai sót tên field và kiểu.

### 21.2. Mapping kiểu

| DSL type | Java minh họa | TypeScript minh họa |
|---|---|---|
| Boolean | boolean/Boolean | boolean |
| Integer | int/long | number hoặc bigint |
| Decimal | BigDecimal | string hoặc decimal library |
| String | String | string |
| Instant | Instant | string/Date wrapper |
| List<T> | List<T> | T[] |
| Optional<T> | Optional<T> | T hoặc undefined theo contract |
| Record | class/record | interface/type |
| Enum | enum | string union/enum |

Mapping thực tế cần xét nullability và wire format, không chỉ kiểu ngôn ngữ đích.

### 21.3. Generated validator và documentation

Schema có thể sinh validator để kiểm tra required field, range, enum và nested structure. Business rule phức tạp vẫn cần logic riêng. Cùng một schema cũng có thể tạo API reference, ví dụ payload và tài liệu kiểu dữ liệu.

### 21.4. Generated code và compatibility

Khi schema đổi, generated code cần được tái tạo và kiểm thử. Không sửa tay generated file nếu thay đổi sẽ bị ghi đè ở lần generate tiếp theo.

## 22. Kiểm thử payload và kiểu dữ liệu

### 22.1. Schema tests

Kiểm tra payload hợp lệ được chấp nhận và payload sai schema bị từ chối với error code đúng.

### 22.2. Boundary tests

Kiểm tra string rỗng và độ dài tối đa; số tại min/max và vượt ngưỡng; decimal có scale đúng và vượt scale; array rỗng, minItems và maxItems; ngày trước, đúng và sau giới hạn; payload đúng và vượt giới hạn byte.

### 22.3. Null/missing tests

Test riêng field bị bỏ, field null, field có giá trị và default application.

### 22.4. Serialization round trip

Serialize rồi deserialize một giá trị và so sánh semantics:

~~~text
decode(encode(value)) == value
~~~

Với kiểu có precision hoặc normalization, equality cần theo contract, không nhất thiết so sánh byte hoặc object identity.

### 22.5. Compatibility tests

Chạy payload từ producer version cũ với consumer version mới và ngược lại theo ma trận được hỗ trợ.

### 22.6. Fuzz và property-based tests

Fuzz parser và deserializer với dữ liệu bất thường để phát hiện crash, parser ambiguity, memory exhaustion hoặc lỗi Unicode. Sinh nhiều giá trị hợp lệ theo schema rồi xác nhận serializer/deserializer giữ nguyên dữ liệu và validator không từ chối nhầm.

### 22.7. Contract và security tests

Consumer-driven contract test xác nhận producer đáp ứng những trường và semantics mà consumer đang sử dụng. Test bảo mật nên thử field không được phép, payload quá lớn, nested depth cao, duplicate keys, injection string, path traversal và dữ liệu nhạy cảm trong log.

## 23. Ví dụ tổng hợp: API tạo đơn hàng

### 23.1. Schema miền

~~~text
type Money {
    amount: Decimal(18,2)
    currency: CurrencyCode
}

type OrderItemRequest {
    productId: ProductId
    quantity: Integer min(1) max(1000)
    unitPrice: Money
}

type CreateOrderRequest {
    customerId: CustomerId
    items: List<OrderItemRequest> minItems(1)
    note: Optional<String>
}

type CreateOrderResponse {
    orderId: OrderId
    status: OrderStatus
    total: Money
    createdAt: Instant
}
~~~

### 23.2. Request payload

~~~json
{
  "customerId": "C-102",
  "items": [
    {
      "productId": "P-10",
      "quantity": 2,
      "unitPrice": {
        "amount": "125000.00",
        "currency": "VND"
      }
    }
  ],
  "note": "Giao giờ hành chính"
}
~~~

### 23.3. Response payload

~~~json
{
  "orderId": "O-501",
  "status": "PENDING",
  "total": {
    "amount": "250000.00",
    "currency": "VND"
  },
  "createdAt": "2026-11-15T08:30:00Z"
}
~~~

### 23.4. Validation và idempotency

Server kiểm tra customerId tồn tại và caller có quyền tạo đơn; items không rỗng; quantity là số nguyên trong miền cho phép; unitPrice có currency hợp lệ; note không vượt giới hạn độ dài. Nếu client retry request do timeout, idempotency key có thể giúp tránh tạo hai đơn hàng.

## 24. Ví dụ: payload event OrderPaid

### 24.1. Event contract và payload

~~~text
event OrderPaid {
    eventId: EventId
    occurredAt: Instant
    orderId: OrderId
    amount: Money
    paymentMethod: PaymentMethod
}
~~~

~~~json
{
  "eventId": "evt-1001",
  "schemaVersion": 1,
  "eventType": "OrderPaid",
  "occurredAt": "2026-11-15T08:30:00Z",
  "payload": {
    "orderId": "O-501",
    "amount": {
      "amount": "250000.00",
      "currency": "VND"
    },
    "paymentMethod": "CARD"
  }
}
~~~

### 24.2. Consumer behavior

Consumer xác minh schema version, event ID, type và quyền truy cập. Nếu nhận event trùng, nó kiểm tra idempotency trước khi thực hiện side effect.

### 24.3. Schema evolution

Nếu thêm field optional paymentReference, consumer cũ cần bỏ qua field chưa biết hoặc dùng schema version phù hợp. Không đổi amount từ Decimal thành Float mà không có kế hoạch migration.

## 25. Những sai lầm thường gặp

### 25.1. Chỉ kiểm tra JSON syntax

JSON parse thành công không có nghĩa payload đúng kiểu, đủ field hoặc hợp lệ nghiệp vụ. Cần schema và semantic validation.

### 25.2. Dùng String cho mọi thứ

Biểu diễn ngày, tiền, ID và trạng thái bằng chuỗi tùy ý làm mất type safety và khiến mỗi consumer phải tự parse.

### 25.3. Dùng Float cho tiền

Floating point có thể tạo sai số. Dùng Decimal hoặc integer theo đơn vị nhỏ nhất với contract rõ.

### 25.4. Không phân biệt missing và null

API update có thể cần hai ý nghĩa khác nhau: không thay đổi field và xóa field. Cần biểu diễn tường minh.

### 25.5. Dùng enum ordinal

Đổi thứ tự enum có thể làm dữ liệu cũ được diễn giải thành trạng thái khác. Dùng string code hoặc numeric code ổn định được công bố.

### 25.6. Không version hóa schema

Producer và consumer có thể triển khai lệch phiên bản mà không biết payload nào được hỗ trợ.

### 25.7. Cho phép unknown field một cách tùy tiện

Bỏ qua field lạ có thể hữu ích, nhưng với field điều khiển quyền hoặc quyết định quan trọng, việc bỏ qua có thể gây hiểu sai. Cần policy theo loại payload.

### 25.8. Không giới hạn payload

Body quá lớn hoặc lồng quá sâu có thể làm cạn tài nguyên. Đặt quota và timeout.

### 25.9. Log toàn bộ payload

Log có thể làm lộ dữ liệu nhạy cảm. Mask hoặc log metadata cần thiết.

### 25.10. Dùng chung request và response type

Request và response có quyền ghi, lifecycle và field khác nhau. Tách type giúp tránh client gửi các field chỉ server được phép đặt.

### 25.11. Không kiểm thử tương thích

Schema thay đổi nhỏ có thể làm hỏng client cũ. Cần compatibility tests và rollout có kiểm soát.

## 26. Quy trình thiết kế payload contract

Một quy trình thực tế có thể gồm:
1. Xác định mục đích thông điệp: request, response, command, query, event hay batch.
2. Xác định consumer và producer: ai tạo, ai đọc, vòng đời dữ liệu ra sao.
3. Thiết kế shape: scalar, record, array, map, tuple hay union.
4. Chọn kiểu miền: Money, ID, Date, Instant, enum và các value object.
5. Xác định required/optional/null: ghi rõ semantics của missing và null.
6. Đặt constraint: range, length, precision, scale, item count và pattern.
7. Định nghĩa serialization: JSON, binary, encoding, date format và decimal representation.
8. Định nghĩa validation: structural, semantic, authorization và error mapping.
9. Version hóa schema: xác định compatibility policy và migration.
10. Xem xét bảo mật: dữ liệu nhạy cảm, giới hạn kích thước, injection và replay.
11. Tạo ví dụ và tài liệu: payload hợp lệ, không hợp lệ và error response.
12. Sinh type và validator nếu có code generation.
13. Viết contract test: serialization round trip, boundary và compatibility.
14. Theo dõi vận hành: payload size, validation error, schema version và consumer adoption.

## 27. Câu hỏi tự đánh giá

1. Payload khác envelope và toàn bộ HTTP request như thế nào?
2. Payload contract cần mô tả những gì ngoài kiểu dữ liệu?
3. Phân biệt Integer, Decimal và floating point.
4. Vì sao Money nên chứa cả amount và currency?
5. Required, optional, nullable và missing khác nhau ra sao?
6. Vì sao enum không nên serialize bằng ordinal?
7. Date, LocalDateTime và Instant biểu diễn những khái niệm gì?
8. Khi nào nên dùng base64, multipart hoặc object storage reference?
9. Structural validation khác semantic validation như thế nào?
10. Unknown fields và unknown enum values nên được xử lý ra sao?
11. Schema version khác API version như thế nào?
12. Expand-contract giúp thay đổi payload an toàn ra sao?
13. Vì sao event payload cần event ID và idempotency?
14. Những giới hạn nào cần đặt cho payload lớn?
15. Serialization round-trip test xác nhận điều gì?

## Kết luận

Payload là dữ liệu được trao đổi giữa các thành phần, còn kiểu dữ liệu và schema xác định cách diễn giải dữ liệu đó. Một API DSL cần mô tả rõ shape, kiểu scalar và composite, required/optional/nullability, enum, đơn vị, precision, ngày giờ, binary và cấu trúc lồng. Hợp đồng cũng cần quy định serialization, validation, error payload, versioning và khả năng tương thích giữa producer với consumer.

Thiết kế payload tốt bắt đầu từ semantics nghiệp vụ, sau đó mới chọn cách biểu diễn trên wire. Kiểu miền giúp tránh nhầm lẫn giữa những giá trị có hình thức giống nhau nhưng ý nghĩa khác nhau. Schema version và compatibility tests giúp thay đổi có kiểm soát; giới hạn kích thước, validation server-side, authorization và masking bảo vệ hệ thống khi nhận dữ liệu không đáng tin cậy. Khi payload contract được tài liệu hóa và kiểm thử như một phần của DSL API, các dịch vụ có thể trao đổi dữ liệu nhất quán, an toàn và dễ nâng cấp.
