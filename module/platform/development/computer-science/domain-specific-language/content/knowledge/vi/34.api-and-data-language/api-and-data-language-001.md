# Mô tả schema

Trong một hệ thống sử dụng ngôn ngữ miền đặc thù (Domain-Specific Language — DSL) để định nghĩa API và dữ liệu, các thành phần cần một cách thống nhất để mô tả hình dạng, kiểu, ý nghĩa và quy tắc của dữ liệu được trao đổi. Một request API có thể chứa mã khách hàng, số tiền, thời điểm tạo và danh sách mặt hàng; một response có thể chứa trạng thái, kết quả và thông tin phân trang. Nếu mỗi service tự hiểu các trường theo cách riêng, hệ thống dễ phát sinh sai lệch: cùng một trường nhưng khác kiểu, trường bắt buộc ở service này lại tùy chọn ở service khác, hoặc một thay đổi nhỏ làm hỏng consumer đã triển khai.

**Mô tả schema** (*schema description*) là việc khai báo có cấu trúc dữ liệu được phép có hình dạng nào, gồm những trường gì, kiểu dữ liệu ra sao, trường nào bắt buộc, các ràng buộc nào phải thỏa mãn, những quan hệ nào tồn tại và cách dữ liệu được biểu diễn khi lưu trữ hoặc truyền qua API. Schema có thể đóng vai trò như một hợp đồng giữa producer và consumer, giữa ứng dụng và database, hoặc giữa các thành phần trong một DSL.

Ví dụ, một schema cho đơn hàng có thể mô tả:

~~~text
schema Order {
    id: OrderId required;
    customerId: CustomerId required;
    createdAt: Instant required;
    currency: CurrencyCode required;
    total: Decimal(precision = 18, scale = 2) required;
    status: OrderStatus required;
    items: List<OrderItem> minItems 1;
    note: String optional maxLength 500;
}
~~~

Khai báo này cho biết một Order có định danh, khách hàng, thời điểm tạo, tiền tệ, tổng tiền, trạng thái, ít nhất một mặt hàng và một ghi chú tùy chọn. Validator có thể dùng schema để kiểm tra dữ liệu; API tool có thể dùng nó để sinh tài liệu; code generator có thể tạo Java record hoặc DTO; database mapper có thể ánh xạ field sang cột; và editor DSL có thể cung cấp completion theo kiểu trường.

Schema không chỉ là danh sách field. Nó còn có semantics: Decimal khác Float; null khác missing; một identifier khác chuỗi tùy ý; reference khác nested object; một enum có tập giá trị hữu hạn; một field có thể read-only hoặc chỉ xuất hiện trong response; một constraint có thể phụ thuộc nhiều field. Mô tả schema tốt phải làm rõ cả cấu trúc lẫn ý nghĩa này.

## 1. Schema là gì?

Schema là mô hình khai báo mô tả cấu trúc và quy tắc của một tập dữ liệu. Nó xác định những giá trị nào được xem là hợp lệ trong một ngữ cảnh cụ thể.

Một schema thường mô tả:

- Tên và định danh của kiểu dữ liệu.
- Các field hoặc property.
- Kiểu dữ liệu của từng field.
- Cardinality: một giá trị, tùy chọn hay danh sách nhiều giá trị.
- Requiredness, nullability, default và computed behavior.
- Constraint như độ dài, miền số, pattern hoặc quan hệ giữa các field.
- Reference tới schema hoặc entity khác.
- Metadata như mô tả, ví dụ, deprecation và sensitivity.
- Quy tắc serialization và versioning nếu schema được dùng làm hợp đồng trao đổi.

### Schema và data instance

Schema mô tả loại dữ liệu; instance là một giá trị cụ thể tuân theo schema.

Ví dụ schema:

~~~text
schema Customer {
    id: CustomerId required;
    displayName: String required maxLength 120;
    email: EmailAddress optional;
}
~~~

Instance minh họa:

~~~json
{
  "id": "CUS-1042",
  "displayName": "Nguyen An",
  "email": "an@example.test"
}
~~~

Schema có thể được dùng để kiểm tra nhiều instance. Một instance không trở thành schema chỉ vì nó có đủ các field; schema còn định nghĩa kiểu, constraint và semantics của các field đó.

### Schema và type

Type trả lời câu hỏi một giá trị thuộc loại nào, ví dụ Integer, String, Order hoặc Instant. Schema thường kết hợp nhiều type và quy tắc để mô tả một cấu trúc hoàn chỉnh. Trong một DSL, type system có thể là nền tảng để xây schema language.

### Schema và contract

Contract mô tả thỏa thuận giữa các thành phần. Schema thường là phần cấu trúc quan trọng của contract, nhưng contract API còn có method, path, authentication, status code, error behavior, pagination, idempotency và các quy tắc vận hành khác. Có schema request/response mà chưa có toàn bộ API contract.

## 2. Vai trò của schema trong DSL API và dữ liệu

Schema là điểm giao giữa nhiều phần của hệ thống.

### Thiết kế dữ liệu

Schema mô tả entity, record, value object, event, command và response. Nó giúp nhóm thống nhất field, kiểu và semantics trước khi viết code.

### Thiết kế API

Request và response schema định nghĩa payload mà client gửi và server trả. Từ đó có thể sinh OpenAPI, tài liệu API, client SDK và validator.

### Kiểm tra dữ liệu

Validator kiểm tra payload có đúng kiểu, required fields, enum, format và constraint hay không. Kiểm tra có thể diễn ra ở compile time, request boundary hoặc trước khi lưu dữ liệu.

### Lưu trữ

Schema có thể ánh xạ sang relational table, document collection, columnar data hoặc binary record. Tuy nhiên, schema API và schema database không nhất thiết giống nhau vì mỗi bên phục vụ mục đích khác.

### Sinh mã

Code generator có thể tạo DTO, Java record, serializer, deserializer, mapper, database migration hoặc test fixture từ schema.

### Trao đổi dữ liệu

Schema làm rõ cách producer và consumer hiểu payload. Schema registry có thể lưu các phiên bản và kiểm tra compatibility trước khi publish.

### Quản trị và governance

Schema có thể mang owner, classification, retention, sensitivity, deprecation và lineage metadata để hỗ trợ quản trị dữ liệu.

## 3. Các loại schema thường gặp

Một hệ thống có thể có nhiều loại schema cùng mô tả một miền dữ liệu ở các ranh giới khác nhau.

| Loại schema | Mục đích | Ví dụ |
|---|---|---|
| Domain schema | Mô hình khái niệm nghiệp vụ | Order, Customer, Invoice. |
| API request schema | Payload client gửi | CreateOrderRequest. |
| API response schema | Payload server trả | OrderResponse. |
| Event schema | Dữ liệu phát qua message/event bus | OrderCreated. |
| Database schema | Bảng, cột, index và constraint | orders, order_items. |
| Configuration schema | Cấu trúc file cấu hình | ServiceSettings. |
| File/document schema | Cấu trúc JSON, XML hoặc tài liệu | ImportBatch. |
| Binary schema | Cấu trúc dữ liệu nhị phân | Protocol Buffers message. |
| Analytics schema | Cấu trúc dữ liệu phục vụ phân tích | DailySalesFact. |

### Không dùng một schema cho mọi ranh giới một cách máy móc

Domain model có thể chứa internal field không nên công khai qua API. API response có thể gom nhiều entity hoặc đổi tên field để thuận tiện cho client. Database có thể chuẩn hóa thành nhiều bảng trong khi API trả một object lồng nhau. Event schema có thể giữ field bất biến để consumer cũ đọc được lịch sử.

Nên xác định rõ schema nào là source of truth cho từng contract và cách mapping giữa các schema.

## 4. Thành phần cơ bản của một schema

Một schema declaration thường có identity, version, field definitions và metadata.

~~~text
schema Order version "2.1" {
    description = "An order placed by a customer";
    owner = "Commerce Platform";

    field id: OrderId {
        required = true;
        immutable = true;
    }

    field total: Money {
        required = true;
        description = "Total amount payable";
    }

    field status: OrderStatus {
        required = true;
        default = PENDING;
    }
}
~~~

### Schema identity

Tên schema giúp người đọc nhận diện, nhưng identity ổn định nên gồm namespace hoặc URI. Ví dụ com.example.commerce.Order tránh nhầm với một schema Order ở miền khác.

### Version

Version xác định cấu trúc và semantics của schema tại một thời điểm. Không nên giả định tên giống nhau đồng nghĩa nội dung giống nhau.

### Field identity

Field có thể có tên và stable ID. Nếu field được rename, stable ID hoặc migration metadata giúp phân biệt rename với xóa field cũ và thêm field mới.

### Description

Description giải thích ý nghĩa nghiệp vụ, đơn vị, nguồn dữ liệu và điều kiện sử dụng. Tên field đơn thuần thường không đủ, ví dụ amount cần biết là gross amount, net amount hay tax amount.

### Metadata

Metadata có thể gồm owner, tags, classification, deprecation, source, retention, examples và generation hints. Cần phân biệt metadata ảnh hưởng semantics với metadata chỉ phục vụ tooling.

## 5. Kiểu dữ liệu nguyên thủy

Một schema language cần tập kiểu dữ liệu cơ bản rõ ràng.

### Boolean

Boolean biểu diễn true hoặc false. Nếu dữ liệu có thể không biết hoặc chưa cung cấp, không nên ép thành false; cần phân biệt nullable/optional hoặc một kiểu tri-state theo semantics.

### Integer

Integer biểu diễn số nguyên. Schema nên xác định miền giá trị và signedness nếu format đích có giới hạn.

~~~text
quantity: Integer(min = 0, max = 1000000);
retryCount: Int32(min = 0);
sequence: Int64(min = 0);
~~~

### Decimal

Decimal phù hợp với tiền tệ và giá trị cần precision xác định. Nên mô tả precision và scale thay vì dùng binary floating point một cách tùy tiện.

~~~text
unitPrice: Decimal(precision = 18, scale = 2);
taxRate: Decimal(precision = 7, scale = 4);
~~~

### Float và Double

Float/Double phù hợp với dữ liệu đo lường hoặc tính toán khoa học có sai số dấu phẩy động. Không nên dùng chúng cho tiền tệ nếu yêu cầu làm tròn chính xác.

### String

String là chuỗi ký tự. Schema có thể quy định minLength, maxLength, pattern, normalization hoặc alphabet cho phép. Cần xác định độ dài tính theo byte, UTF-16 code unit hay Unicode code point nếu giới hạn có ý nghĩa kỹ thuật.

### Bytes

Bytes biểu diễn dữ liệu nhị phân. Khi serialize thành JSON, thường cần một encoding như Base64; schema cần ghi rõ encoding và giới hạn kích thước.

### Date, Time và DateTime

Các kiểu thời gian cần phân biệt:
- Date: ngày lịch không kèm thời điểm.
- LocalTime: giờ địa phương không gắn timezone.
- LocalDateTime: ngày giờ địa phương chưa xác định offset.
- Instant: một thời điểm trên timeline.
- OffsetDateTime: ngày giờ kèm UTC offset.
- ZonedDateTime: ngày giờ gắn với timezone rule set.

Không nên dùng một kiểu String chung cho mọi trường thời gian nếu cần validation và xử lý timezone chính xác.

### Duration

Duration biểu diễn khoảng thời gian, ví dụ timeout 30 giây hoặc SLA 4 giờ. Cần xác định đơn vị hoặc format chuẩn.

### Identifier

Identifier biểu diễn định danh theo miền. Nó có thể được serialize thành string nhưng semantics khác chuỗi tự do. Schema có thể quy định prefix, format, uniqueness scope và tính bất biến.

### URI, Email, IP và các format chuyên biệt

Các format như URI, email, IPv4/IPv6 hoặc CIDR có thể được mô tả bằng type riêng hoặc String kèm format constraint. Type riêng giúp tooling hiểu semantics tốt hơn.

## 6. Kiểu tổ hợp: record, object và nested schema

Một object/record kết hợp nhiều field có tên.

~~~text
schema Address {
    line1: String required maxLength 150;
    line2: String optional maxLength 150;
    city: String required;
    postalCode: PostalCode optional;
    country: CountryCode required;
}

schema Customer {
    id: CustomerId required;
    name: String required;
    address: Address required;
}
~~~

### Nested object

Nested schema biểu diễn cấu trúc sở hữu. Customer.address chứa một Address object. Nếu Address là value object không có identity riêng, nested representation thường phù hợp.

### Reusable type

Nếu nhiều schema dùng chung Address, có thể định nghĩa một schema/type riêng và tham chiếu lại. Điều này giảm duplication nhưng cần quản lý version dependency.

### Inline schema

Một object nhỏ chỉ dùng ở một vị trí có thể được khai báo inline. Cần cân nhắc khả năng tái sử dụng và cách sinh tên type.

### Record với field động

Một số cấu trúc có tập key không cố định, ví dụ map từ locale sang label. Schema nên dùng Map<K,V> với kiểu key/value rõ thay vì object không có quy tắc.

## 7. Collection: list, set và map

Collection mô tả nhiều giá trị. Cần phân biệt collection có thứ tự và không có thứ tự.

### List

List giữ thứ tự và có thể chứa phần tử trùng lặp.

~~~text
items: List<OrderItem> minItems 1 maxItems 200;
~~~

### Set

Set biểu diễn tập giá trị duy nhất, không phụ thuộc thứ tự. Nếu format trao đổi không có kiểu set riêng, serializer có thể biểu diễn thành array nhưng validator cần kiểm tra uniqueness.

~~~text
permissions: Set<Permission>;
~~~

### Map

Map ánh xạ key sang value.

~~~text
localizedNames: Map<LocaleCode, String>;
quantitiesByWarehouse: Map<WarehouseId, Integer>;
~~~

Schema cần xác định key type và quy tắc serialize key. JSON object chỉ cho phép key là string, vì vậy map với key phức tạp cần mapping rõ.

### Tuple

Tuple là tập giá trị theo vị trí với kiểu có thể khác nhau.

~~~text
coordinate: Tuple<Decimal, Decimal>;
~~~

Tuple hữu ích với cấu trúc cố định, nhưng record có field name thường dễ đọc và tiến hóa hơn.

### Cardinality

Các constraint minItems/maxItems hoặc exact size xác định số lượng phần tử. Cần phân biệt collection không có phần tử với field bị thiếu hoặc null.

## 8. Enum và kiểu phân biệt hữu hạn

Enum giới hạn giá trị vào một tập tên hoặc mã đã định nghĩa.

~~~text
enum OrderStatus {
    PENDING;
    CONFIRMED;
    PAID;
    SHIPPED;
    CANCELLED;
}
~~~

### Enum code và label

API nên có code ổn định, còn label hiển thị có thể được dịch. Không nên dùng label đã dịch làm giá trị wire vì thay đổi ngôn ngữ sẽ làm thay đổi contract.

### Unknown enum value

Consumer có thể nhận enum value mới từ producer mới. Schema và code generation cần xác định cách xử lý: reject, preserve unknown value hoặc ánh xạ về trạng thái UNKNOWN. Với event contract cần compatibility, khả năng giữ unknown enum có thể quan trọng.

### Enum evolution

Thêm enum value có thể là breaking với consumer dùng exhaustive switch. Vì vậy, thêm giá trị không phải lúc nào cũng backward-compatible. Cần xem cách consumer xử lý unknown values.

### Discriminated union

Một union có nhiều biến thể được phân biệt bằng tag.

~~~text
union PaymentMethod discriminator "kind" {
    CardPayment;
    BankTransfer;
    CashOnDelivery;
}
~~~

Mỗi biến thể có schema riêng. Discriminator giúp deserializer xác định đúng subtype mà không phải đoán dựa trên field tình cờ.

## 9. Optional, nullable, missing và default

Đây là một trong những phần dễ gây lỗi nhất khi mô tả schema.

### Required

Required có nghĩa field phải xuất hiện trong payload hoặc object theo contract.

### Optional

Optional có nghĩa field có thể không xuất hiện. Nếu field không xuất hiện, consumer có thể dùng một semantics riêng như không cung cấp.

### Nullable

Nullable có nghĩa field có thể hiện diện với giá trị null. Null có thể biểu thị không biết, không áp dụng hoặc cố ý xóa, tùy contract.

### Missing khác null

Ví dụ:

~~~json
{}
~~~

Field nickname bị thiếu.

~~~json
{
  "nickname": null
}
~~~

Field có mặt nhưng giá trị null. Hai payload này có thể mang ý nghĩa khác nhau trong PATCH API: missing giữ nguyên giá trị cũ, còn null xóa giá trị.

### Default

Default là giá trị được dùng khi field không được cung cấp theo một quy tắc xác định. Cần nói rõ default được áp dụng ở client, server, deserializer hay database.

~~~text
pageSize: Integer optional default 50;
enabled: Boolean required default true;
~~~

### Required và nullable có thể cùng tồn tại

Một field có thể bắt buộc phải xuất hiện nhưng giá trị được phép null. Ví dụ middleName phải có trong một export chuẩn nhưng có thể null nếu không biết. Schema cần biểu diễn hai chiều này độc lập.

### Default không thay thế required semantics

Nếu một field có default, có thể payload thiếu field vẫn hợp lệ. Nhưng hệ thống cần xác định default được vật chất hóa vào model hay chỉ được dùng khi đọc.

## 10. Constraint và validation rule

Constraint mô tả điều kiện mà dữ liệu phải thỏa mãn.

Các nhóm phổ biến:

- Numeric range: min, max, exclusiveMin, exclusiveMax.
- String length: minLength, maxLength.
- Pattern: regular expression hoặc format.
- Collection size: minItems, maxItems, uniqueItems.
- Requiredness và nullability.
- Enum membership.
- Uniqueness trong scope.
- Cross-field validation.
- Referential integrity.
- Business invariant.

Ví dụ:

~~~text
schema User {
    id: UserId required;
    email: EmailAddress required;
    age: Integer min 0 max 130;
    password: String minLength 12 maxLength 128;
    roles: Set<Role> minItems 1;
}
~~~

### Constraint theo field

Field-level constraint kiểm tra một giá trị độc lập, như số tiền không âm hoặc email đúng format.

### Constraint giữa nhiều field

Cross-field constraint kiểm tra quan hệ, ví dụ endAt phải sau startAt, minValue không lớn hơn maxValue hoặc currency phải phù hợp với account.

~~~text
constraint validDateRange on Booking {
    endAt > startAt;
}
~~~

### Conditional requirement

Một field có thể bắt buộc khi field khác mang một giá trị cụ thể.

~~~text
if deliveryMode == PICKUP then pickupLocation required;
if deliveryMode == SHIPPING then shippingAddress required;
~~~

### Uniqueness

Uniqueness có thể áp dụng trong một object, một batch, một table hoặc toàn hệ thống. Schema cần xác định scope và liệu kiểm tra có cần truy cập storage hay không.

### Referential integrity

Reference phải trỏ đến entity tồn tại và đúng loại. Validation có thể chỉ kiểm tra format ID ở boundary; kiểm tra target tồn tại cần lookup hoặc transaction phù hợp.

### Constraint và business rule

Schema constraint nên mô tả tính hợp lệ của dữ liệu. Quy tắc nghiệp vụ phụ thuộc trạng thái hoặc thời điểm, ví dụ không thể hủy đơn đã giao, có thể thuộc domain rule thay vì schema thuần. Phân chia rõ giúp schema không trở thành nơi chứa toàn bộ workflow logic.

## 11. Reference, relationship và ownership

Một schema cần mô tả khi nào dữ liệu được lồng trực tiếp và khi nào tham chiếu đến entity khác.

### Embedded value

Một địa chỉ có thể được nhúng vào Customer nếu nó là một phần giá trị của Customer và không có lifecycle độc lập.

### Entity reference

Order có thể tham chiếu Customer bằng CustomerId. Customer tồn tại độc lập và có thể được nhiều Order sử dụng.

~~~text
schema Order {
    id: OrderId required;
    customer: Reference<Customer> required;
}
~~~

### One-to-one, one-to-many và many-to-many

Domain model có thể mô tả cardinality quan hệ:
- Một Order có một Customer.
- Một Customer có nhiều Order.
- Một Product có thể xuất hiện trong nhiều Order và một Order có nhiều Product.

### Ownership và cascade

Nếu child thuộc vòng đời của parent, xóa parent có thể xóa child. Nếu child là entity độc lập được tham chiếu, không nên cascade delete chỉ vì parent bị xóa. Schema metadata có thể mô tả ownership nhưng hành vi xóa thường thuộc persistence/domain policy.

### Circular reference

Các entity có thể tham chiếu vòng. Serializer cần tránh recursion vô hạn, có thể dùng identity reference hoặc graph format. Với JSON tree, cần chọn chiến lược như ID reference thay vì nhúng object vô hạn.

### Reference resolution

Schema có thể định nghĩa reference bằng ID, URI, key tự nhiên hoặc composite key. Cần xác định scope và quy tắc resolve.

## 12. Inheritance, composition và polymorphism

Schema có thể tái sử dụng cấu trúc thông qua inheritance hoặc composition.

### Inheritance

Một subtype kế thừa field của base type.

~~~text
schema Person {
    id: PersonId required;
    name: String required;
}

schema Employee extends Person {
    employeeNumber: String required;
    department: DepartmentCode required;
}
~~~

Inheritance có thể phù hợp với domain type hierarchy, nhưng khi serialize cần xác định discriminator và cách consumer nhận diện subtype.

### Composition

Composition kết hợp các schema nhỏ thành schema lớn mà không tạo quan hệ subtype.

~~~text
schema AuditFields {
    createdAt: Instant required;
    updatedAt: Instant required;
}

schema Order {
    id: OrderId required;
    audit: AuditFields required;
}
~~~

### Polymorphism

Một field có thể nhận một trong nhiều subtype. Discriminator hoặc tagged union thường an toàn hơn việc suy luận subtype từ tập field.

### Multiple inheritance

Nếu cho phép nhiều base schema, cần quy định xung đột field, precedence và semantics. Nhiều hệ thống chọn composition để tránh diamond inheritance và ambiguity.

### Schema composition

Các phép như allOf, anyOf và oneOf trong JSON Schema có semantics riêng. DSL nên định nghĩa rõ cách kết hợp constraint và xử lý field trùng.

## 13. Schema cho API request và response

API schema mô tả dữ liệu ở biên giao tiếp. Request và response thường có mục đích khác nhau, vì vậy không nên mặc định dùng cùng một schema cho cả hai chiều.

### Request schema

Request thường chứa field client được phép gửi. Một số field như server-generated ID, audit timestamps hoặc computed status có thể bị cấm.

~~~text
schema CreateOrderRequest {
    customerId: CustomerId required;
    currency: CurrencyCode required;
    items: List<CreateOrderItem> minItems 1;
    note: String optional maxLength 500;
}
~~~

### Response schema

Response có thể chứa ID, trạng thái, timestamps, links và dữ liệu tổng hợp.

~~~text
schema OrderResponse {
    id: OrderId required;
    customerId: CustomerId required;
    status: OrderStatus required;
    total: Money required;
    createdAt: Instant required;
    items: List<OrderItemResponse> required;
}
~~~

### Create, update và patch

Create request thường cần dữ liệu đủ để tạo resource. PUT có thể biểu diễn thay thế toàn bộ resource theo contract; PATCH biểu diễn cập nhật một phần. Schema PATCH phải mô tả rõ missing, null và semantics xóa field.

### Read-only và write-only

Field có thể chỉ được trả về hoặc chỉ được nhận vào. Ví dụ password là write-only; createdAt thường read-only. Schema metadata cần được code generator và API documentation hiểu nhất quán.

### Request context

Một số thông tin thuộc header/path/query thay vì body, ví dụ tenant ID, locale, page token hoặc idempotency key. API contract cần mô tả vị trí truyền dữ liệu và schema tương ứng.

## 14. Schema cho event và message

Event schema thường có yêu cầu tiến hóa khác request/response.

Một event có thể gồm envelope và payload:

~~~text
schema EventEnvelope<T> {
    eventId: UUID required;
    eventType: String required;
    occurredAt: Instant required;
    producer: ServiceId required;
    schemaVersion: String required;
    correlationId: UUID optional;
    payload: T required;
}
~~~

### Event identity

Event ID hỗ trợ deduplication và truy vết. Event type cùng schema version cho consumer biết payload được diễn giải theo contract nào.

### Immutable event

Event đã publish thường được coi là bất biến. Khi semantics thay đổi, thường tạo event version/type mới hoặc bổ sung event mới thay vì sửa lịch sử.

### Additive evolution

Thêm field optional có thể tương thích với consumer bỏ qua field chưa biết, nếu serialization và consumer policy cho phép. Thêm field required thường có rủi ro với producer cũ.

### Unknown fields

Consumer nên có chiến lược với field chưa biết: bỏ qua, giữ lại khi proxy hoặc từ chối theo contract. Với event bus có nhiều consumer độc lập, khả năng forward compatibility thường quan trọng.

### Event payload không phải database row

Event mô tả một sự kiện đã xảy ra, không nhất thiết phản ánh toàn bộ trạng thái hiện tại của entity. Schema event cần tên và semantics theo sự kiện, ví dụ OrderPlaced thay vì một bản sao tùy tiện của bảng Order.

## 15. Mô tả schema và serialization format

Schema mô tả dữ liệu trừu tượng; serialization format xác định cách mã hóa dữ liệu thành bytes hoặc text.

Một schema có thể được serialize bằng JSON, XML, YAML, CBOR, Avro hoặc Protocol Buffers nếu mapping phù hợp.

| Format | Đặc điểm | Trường hợp thường dùng |
|---|---|---|
| JSON | Dễ đọc, phổ biến trong HTTP API. | REST API, config và document exchange. |
| XML | Có namespace và hệ sinh thái schema lâu đời. | Enterprise integration, SOAP và document-centric data. |
| YAML | Dễ viết cho cấu hình, hỗ trợ syntax phong phú. | IaC và config authoring. |
| Protocol Buffers | Binary compact, field numbering và schema evolution. | RPC và service-to-service. |
| Avro | Schema-aware binary serialization, thường dùng trong data pipelines. | Event streaming và data platform. |
| CBOR | Binary representation gần mô hình JSON. | IoT và constrained systems. |

### Schema không đồng nhất với format

Một schema domain có thể được ánh xạ sang JSON Schema cho API validation và Avro cho event stream. Hai format có thể biểu diễn cùng ý nghĩa nhưng có khác biệt về nullability, default, union và unknown fields.

### Mapping phải có quy tắc

Không nên giả định mọi type đều chuyển một-một. Decimal, date-time, map key, enum unknown, recursive reference và polymorphism cần mapping được định nghĩa.

### Canonical representation

Nếu cần hash, signature hoặc compare bytes, có thể cần canonical serialization. Canonicalization phải xác định field ordering, number representation, Unicode normalization và null/default behavior.

## 16. Mô tả schema bằng JSON Schema

JSON Schema là một vocabulary để mô tả và kiểm tra cấu trúc JSON. Nó hỗ trợ type, properties, required, array constraints, enum, pattern, composition và nhiều keyword khác.

Ví dụ tương ứng:

~~~json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "$id": "https://schemas.example.test/commerce/order.schema.json",
  "title": "Order",
  "type": "object",
  "required": ["id", "customerId", "total", "status"],
  "properties": {
    "id": {
      "type": "string",
      "description": "Stable order identifier"
    },
    "customerId": {
      "type": "string"
    },
    "total": {
      "type": "number",
      "minimum": 0
    },
    "status": {
      "type": "string",
      "enum": ["PENDING", "CONFIRMED", "PAID", "CANCELLED"]
    },
    "note": {
      "type": ["string", "null"],
      "maxLength": 500
    }
  },
  "additionalProperties": false
}
~~~

### type và properties

type xác định loại JSON value; properties mô tả field của object. required là danh sách field phải hiện diện.

### additionalProperties

Keyword này quyết định object có thể chứa field ngoài danh sách khai báo hay không. Đóng schema bằng false giúp phát hiện typo nhưng có thể ảnh hưởng forward compatibility nếu consumer nhận payload có field mới.

### $ref

$ref cho phép tái sử dụng schema khác. Cần quản lý URI, version và resolution policy để không tham chiếu một tài liệu thay đổi ngoài ý muốn.

### Composition keywords

allOf, anyOf, oneOf và not hỗ trợ kết hợp schema. Chúng không hoàn toàn giống inheritance trong OOP; cần hiểu semantics validation và discriminator strategy.

### Dialect/version

JSON Schema có nhiều dialect/draft. Schema cần khai báo dialect phù hợp và tooling phải hỗ trợ cùng vocabulary. Không nên trộn keyword từ các draft khác nhau mà không xác định behavior.

## 17. Mô tả schema bằng OpenAPI

OpenAPI mô tả HTTP API: paths, operations, parameters, request bodies, responses, security schemes và schema components. Nó dùng Schema Object để mô tả payload.

Một API operation có thể tham chiếu schema:

~~~yaml
paths:
  /orders:
    post:
      operationId: createOrder
      requestBody:
        required: true
        content:
          application/json:
            schema:
              $ref: '#/components/schemas/CreateOrderRequest'
      responses:
        '201':
          description: Order created
          content:
            application/json:
              schema:
                $ref: '#/components/schemas/OrderResponse'
components:
  schemas:
    CreateOrderRequest:
      type: object
      required:
        - customerId
        - items
      properties:
        customerId:
          type: string
        items:
          type: array
          minItems: 1
          items:
            $ref: '#/components/schemas/CreateOrderItem'
~~~

### Schema component

Components cho phép reuse schema trong nhiều operation. Cần tránh tạo một schema khổng lồ cho mọi endpoint nếu request/response semantics khác nhau.

### Parameter schema

Path, query, header và cookie parameters cũng cần schema. Kiểu dữ liệu trên URL có thể có serialization rules khác body JSON.

### Response schema

Mỗi status code có thể trả payload khác nhau. 200, 201, 400, 404 và 500 không nên bị gộp thành một response shape nếu semantics khác.

### OpenAPI và DSL nguồn

Một DSL nội bộ có thể là source of truth rồi sinh OpenAPI; hoặc OpenAPI có thể là nguồn để import vào DSL. Dù hướng nào, cần quy định phần nào được chỉnh sửa trực tiếp và cách xử lý round-trip.

## 18. Mô tả schema bằng Protocol Buffers và Avro

Các format schema-aware thường cần quy tắc identity và evolution riêng.

### Protocol Buffers

Protocol Buffers dùng message và field number. Field name có thể đổi trong source nhưng field number là phần quan trọng của wire compatibility.

Ví dụ:

~~~proto
syntax = "proto3";

message Order {
  string id = 1;
  string customer_id = 2;
  int64 created_at_epoch_ms = 3;
  string currency = 4;
  int64 total_minor_units = 5;

  reserved 6;
  string status = 7;
}
~~~

Không được tái sử dụng field number đã xóa nếu wire compatibility cần được bảo đảm. Cần đánh giá thay đổi type, cardinality, oneof và default semantics.

### Avro

Avro schema thường định nghĩa record, field, type, default và union. Reader/writer schema resolution cho phép một số dạng evolution, nhưng compatibility phụ thuộc chiều đọc và quy tắc resolution.

Ví dụ:

~~~json
{
  "type": "record",
  "name": "Order",
  "namespace": "example.commerce",
  "fields": [
    {"name": "id", "type": "string"},
    {"name": "customerId", "type": "string"},
    {"name": "note", "type": ["null", "string"], "default": null}
  ]
}
~~~

### Field identity

Trong JSON, field thường được nhận diện bằng tên. Trong Protobuf, field number là wire identity; trong Avro, name và alias tham gia resolution. Một schema DSL trung gian cần giữ metadata đủ để sinh đúng format đích.

### Default semantics

Default trong một DSL, JSON Schema, Protobuf và Avro có thể khác nhau. Cần định nghĩa default ở tầng domain và quy tắc mapping thay vì sao chép keyword một cách máy móc.

## 19. Schema validation trong vòng đời dữ liệu

Validation có thể diễn ra ở nhiều thời điểm.

~~~mermaid
flowchart TD
    A[Schema DSL declaration] --> B[Parse and resolve]
    B --> C[Schema validation]
    C --> D[Generate API / DTO / validators]
    D --> E[Receive payload]
    E --> F[Decode and normalize]
    F --> G[Runtime validation]
    G --> H[Domain processing]
    H --> I[Persistence / event publication]
~~~

### Parse-time validation

Kiểm tra cú pháp schema DSL: dấu ngoặc, field declaration, type syntax và annotation format.

### Schema-time validation

Kiểm tra tham chiếu type tồn tại, không có field trùng, constraint hợp lệ, dependency resolve được và schema composition không mâu thuẫn.

### Compile-time validation

Nếu DSL có type system, có thể kiểm tra mapping giữa schema, API operation, serializer và target type trước khi deploy.

### Runtime validation

Kiểm tra payload thực tế tại trust boundary. Payload bên ngoài không được tin cậy chỉ vì client SDK đã sinh từ schema.

### Persistence validation

Kiểm tra invariant trước khi ghi dữ liệu. Một số constraint như uniqueness hoặc foreign key cần được bảo vệ bằng transaction/database constraint để tránh race giữa validate và write.

### Validation result

Một validation result nên có path, error code, expected constraint, actual type/value summary và source schema version. Không nên chỉ trả một chuỗi invalid data không thể xử lý tự động.

## 20. Schema evolution và versioning

Schema thay đổi theo yêu cầu nghiệp vụ. Versioning giúp producer và consumer biết cách diễn giải dữ liệu.

### Semantic versioning

Có thể dùng major/minor/patch nếu quy tắc compatibility được định nghĩa rõ:
- Major: thay đổi có thể phá contract.
- Minor: mở rộng tương thích theo policy.
- Patch: sửa metadata hoặc mô tả không đổi semantics.

Không nên dùng nhãn semver mà không có compatibility rules thực tế.

### Immutable published schema

Một schema version đã publish nên được coi là bất biến. Nếu cần sửa, tạo version mới. Điều này giúp historical event và client cũ có thể được diễn giải nhất quán.

### Schema registry

Registry lưu schema versions, IDs, metadata, compatibility policy và reference dependencies. Producer có thể đăng ký schema mới; registry kiểm tra compatibility trước khi cho publish.

### Version pinning

API hoặc event producer có thể pin schema version. Consumer cần biết version của payload hoặc schema ID để decode đúng.

### Migration

Migration chuyển dữ liệu hoặc model từ schema cũ sang schema mới. Nó có thể là field rename, split, merge, unit conversion hoặc thay đổi representation.

### Version của schema và version của API

API version và schema version có liên quan nhưng không nhất thiết trùng. Một endpoint có thể giữ path version trong khi response schema mở rộng; hoặc một schema được dùng bởi nhiều API version.

## 21. Backward, forward và full compatibility

Compatibility phải được xét từ góc nhìn producer và consumer.

### Backward compatibility

Consumer mới có thể đọc dữ liệu được tạo theo schema cũ.

Ví dụ thường tương thích nếu:
- Thêm field optional với default phù hợp.
- Consumer mới chấp nhận payload cũ thiếu field mới.

### Forward compatibility

Consumer cũ có thể đọc dữ liệu được tạo theo schema mới.

Ví dụ có thể tương thích nếu:
- Producer mới thêm field và consumer cũ bỏ qua unknown fields.
- Enum consumer có chiến lược xử lý unknown values.

### Full compatibility

Cả consumer cũ đọc dữ liệu mới và consumer mới đọc dữ liệu cũ đều hoạt động theo contract.

### Breaking changes thường gặp

- Xóa field đang được consumer dùng.
- Đổi kiểu field, ví dụ String thành Integer.
- Đổi semantics hoặc đơn vị mà không đổi tên.
- Thêm required field không có default cho producer cũ.
- Thu hẹp miền giá trị.
- Đổi enum code hoặc discriminator.
- Đổi nullability.
- Đổi meaning của missing/null/default.
- Thay đổi identity hoặc reference resolution.

### Compatibility phụ thuộc policy

Thêm field optional có thể vẫn phá consumer strict nếu consumer từ chối unknown properties. Vì vậy, compatibility cần được kiểm tra với behavior thực tế của producer/consumer và format, không chỉ dựa trên một danh sách quy tắc chung.

## 22. Thiết kế schema migration

Migration cần mô tả cách chuyển dữ liệu hiện có mà không mất semantics.

Ví dụ field fullName được tách thành givenName và familyName.

~~~text
migration Customer_1_to_2 {
    from Customer@1;
    to Customer@2;

    transform {
        givenName = splitName(fullName).first;
        familyName = splitName(fullName).last;
    }
}
~~~

Đây là cú pháp minh họa. Migration thực tế cần xử lý tên có nhiều phần, khoảng trắng, dữ liệu thiếu và trường hợp không thể phân tách chắc chắn.

### Expand and contract

Một chiến lược phổ biến:
1. Thêm field mới mà consumer cũ vẫn hoạt động.
2. Producer bắt đầu ghi cả field cũ và mới.
3. Consumer chuyển sang đọc field mới.
4. Backfill dữ liệu lịch sử.
5. Ngừng ghi field cũ sau khi mọi consumer đã chuyển.
6. Xóa field cũ ở một version sau.

### Data backfill

Backfill cập nhật dữ liệu hiện có. Cần idempotency, batching, checkpoint, retry và khả năng resume.

### Dual read/write

Trong giai đoạn chuyển tiếp, service có thể đọc field mới trước rồi fallback field cũ; hoặc ghi cả hai. Cần tránh hai nguồn giá trị mâu thuẫn.

### Rollback

Rollback code không nhất thiết rollback dữ liệu đã migrate. Migration cần có chiến lược forward-fix hoặc reverse migration nếu có thể.

### Audit migration

Ghi schema version nguồn/đích, migration ID, thời điểm, số record thành công/thất bại và lỗi theo record. Không log dữ liệu nhạy cảm không cần thiết.

## 23. Schema registry và quản lý dependency

Khi nhiều team dùng chung schema, registry giúp kiểm soát contract.

Một schema registry có thể quản lý:
- Schema ID và subject.
- Namespace và version.
- Serialization format/dialect.
- Compatibility mode.
- Owner và documentation.
- References đến schema khác.
- Lifecycle: draft, approved, deprecated, retired.
- Signature hoặc provenance.
- Usage và consumer inventory.

### Subject naming

Subject có thể được đặt theo topic, API operation, record type hoặc domain. Quy ước cần tránh trùng tên giữa môi trường và tenant.

### Reference dependency

Schema Order có thể tham chiếu Address, Money và CustomerId. Registry cần biết version dependency nào được dùng để schema Order có thể được resolve tái lập.

### Compatibility check trong CI

Khi PR thay schema, CI có thể so version mới với published version và các consumer contract. Nếu breaking change, yêu cầu migration plan hoặc API version mới.

### Deprecation lifecycle

Một field hoặc schema có thể đi qua các trạng thái:
- Active.
- Deprecated.
- Sunset announced.
- Retired.

Deprecation cần replacement guidance, ngày sunset và usage metrics nếu có.

## 24. Metadata và documentation trong schema

Schema nên chứa thông tin giúp con người và tooling hiểu dữ liệu.

Các metadata hữu ích:
- Description và display name.
- Owner/team.
- Example values.
- Format và unit.
- Sensitivity classification.
- Read-only/write-only.
- Deprecated và replacement.
- Data lineage/source.
- Retention category.
- PII/secret markers.
- Validation message key.
- UI hint như display order hoặc widget type.

### Description cần có ý nghĩa

Ví dụ amount: Decimal chưa đủ. Nên mô tả “Tổng tiền khách phải thanh toán, chưa gồm phí vận chuyển” hoặc “Giá trị theo đơn vị minor currency unit” để tránh hiểu sai.

### Unit

Field kiểu number nên nêu đơn vị: milliseconds, bytes, meters, percent, basis points hoặc minor currency units. Không nên chỉ dựa vào tên field.

### Examples

Example giúp người đọc hiểu format nhưng không thay thế validation. Example cần là dữ liệu giả hoặc đã được làm sạch, không chứa thông tin cá nhân thật.

### UI metadata

Metadata cho form renderer có thể xác định label, placeholder, order hoặc widget. Nên tách presentation hint khỏi core schema semantics để consumer không phụ thuộc giao diện cụ thể.

## 25. Unknown fields và strictness policy

Khi schema thay đổi, payload có thể chứa field mà consumer chưa biết.

### Strict mode

Từ chối unknown fields. Phù hợp với boundary cần kiểm soát chặt, phát hiện typo và payload ngoài contract.

### Permissive mode

Bỏ qua unknown fields. Có thể giúp consumer cũ tiếp tục đọc payload mới.

### Preserve mode

Giữ unknown fields khi parse rồi serialize lại. Hữu ích với gateway hoặc proxy chuyển tiếp payload mà không hiểu mọi field.

### Per-boundary policy

Không nhất thiết dùng một policy cho mọi nơi. API public có thể permissive ở response và strict ở request; config security-critical có thể strict; event consumer có thể preserve unknown fields.

### Unknown enum values

Unknown enum value là trường hợp riêng với unknown field. Consumer cần fallback an toàn và không giả định enum luôn chỉ chứa những giá trị đã biết lúc compile.

### Forwarding

Nếu service đọc rồi ghi lại payload, việc bỏ unknown fields có thể làm mất dữ liệu do producer mới gửi. Cần cân nhắc preserve behavior cho pass-through service.

## 26. Schema mapping giữa DSL và Java

Một DSL API/data có thể sinh Java type để giảm boilerplate và tăng type safety.

Ví dụ schema:

~~~text
schema Order {
    id: OrderId required;
    total: Decimal(18, 2) required;
    status: OrderStatus required;
    note: String optional nullable;
}
~~~

Có thể ánh xạ sang Java:

~~~java
public record Order(
    OrderId id,
    BigDecimal total,
    OrderStatus status,
    @Nullable String note
) {}
~~~

### Mapping kiểu

| Schema type | Java mapping gợi ý |
|---|---|
| Boolean | boolean hoặc Boolean |
| Int32 | int hoặc Integer |
| Int64 | long hoặc Long |
| Decimal(p,s) | BigDecimal |
| String | String |
| Bytes | byte[] hoặc ByteBuffer |
| Instant | Instant |
| LocalDate | LocalDate |
| Duration | Duration |
| List<T> | List<T> |
| Set<T> | Set<T> |
| Map<K,V> | Map<K,V> |
| Enum | Java enum hoặc extensible value type |
| Reference<T> | ID type hoặc reference wrapper |

### Primitive và boxed type

Primitive Java không biểu diễn null. Nếu schema nullable hoặc optional, generator cần chọn boxed type, Optional wrapper hoặc một presence-aware representation.

### Optional không đơn giản là Optional<T>

Java Optional thường mô tả sự hiện diện trong API code, nhưng không phải lúc nào cũng phân biệt được missing, explicit null và default đã áp dụng. Với PATCH hoặc schema evolution, có thể cần tri-state wrapper.

### Decimal precision

BigDecimal giữ precision/scale tốt hơn double. Generator hoặc validator cần kiểm tra precision/scale theo schema.

### Enum extensibility

Java enum đóng có thể gặp khó khi server gửi enum value mới. Có thể dùng unknown constant hoặc value object giữ raw string tùy compatibility requirement.

### Validation annotations

Có thể sinh Jakarta Bean Validation annotations cho constraint cơ bản. Cross-field hoặc reference validation thường cần custom validator và runtime dependency.

## 27. Schema mapping với database

Schema API và database schema thường liên quan nhưng không đồng nhất.

### Relational mapping

Object có thể ánh xạ thành nhiều bảng:
- Order thành bảng orders.
- OrderItem thành bảng order_items.
- Customer reference thành customer_id foreign key.

### Normalization

Database có thể chuẩn hóa dữ liệu để giảm duplication, trong khi API trả nested object thuận tiện cho client.

### Nullability

Database column NULL và API optional/null có semantics khác nhau. Mapping cần xác định khi nào field thiếu được lưu thành NULL, giữ nguyên giá trị hoặc dùng default.

### Defaults

Database default chỉ chạy khi column bị bỏ khỏi INSERT theo quy tắc database; gửi explicit NULL có thể không kích hoạt default. API deserializer có thể áp default trước khi persistence. Cần tránh áp default hai lần theo cách khác nhau.

### Constraints

Unique, check và foreign key constraints ở database bảo vệ dữ liệu trước race condition. Validation ở application giúp trả lỗi dễ hiểu nhưng không thay thế database constraint khi cần đảm bảo toàn vẹn đồng thời.

### Schema migration

Database migration có thể gồm create/alter table, index, backfill và constraint rollout. Cần đồng bộ với API schema evolution và deployment order.

### Document database

Với document store, schema có thể linh hoạt hơn nhưng vẫn cần version và validation policy. Không có schema cứng ở database không có nghĩa ứng dụng không cần schema contract.

## 28. Schema normalization và canonicalization

Normalization chuẩn hóa dữ liệu để validation và comparison nhất quán.

Ví dụ:
- Trim hoặc giữ nguyên whitespace theo semantics.
- Chuẩn hóa Unicode khi identifier yêu cầu.
- Chuẩn hóa timestamp về UTC hoặc giữ offset.
- Chuẩn hóa decimal scale.
- Chuẩn hóa enum code.
- Chuẩn hóa URI hoặc email theo quy tắc được công bố.
- Chuẩn hóa map/set ordering khi serialize canonical.

### Không normalize tùy tiện

Không phải mọi string đều nên trim hoặc lowercase. Password, signature, opaque token và user-entered text có thể cần giữ nguyên byte/character semantics. Normalization phải dựa trên type và contract.

### Validation trước hay sau normalization?

Thứ tự ảnh hưởng semantics. Ví dụ maxLength có thể được kiểm tra trước hoặc sau Unicode normalization. Schema DSL cần quy định pipeline để producer và consumer cho kết quả giống nhau.

### Canonical form

Canonical form hữu ích cho hashing, signing, cache key và diff. Cần xác định null, omitted default, number notation, property ordering và Unicode behavior.

## 29. Schema và data quality

Schema validation kiểm tra cấu trúc và một số invariant, nhưng data quality rộng hơn.

Các chiều data quality có thể gồm:
- Completeness: trường quan trọng có dữ liệu không.
- Accuracy: dữ liệu có phản ánh thực tế không.
- Consistency: các nguồn có thống nhất không.
- Timeliness: dữ liệu có đủ mới không.
- Uniqueness: có duplicate không.
- Validity: dữ liệu có đúng schema và rule không.

Một schema có thể đảm bảo createdAt là Instant, nhưng không thể tự chứng minh timestamp đó đúng với thời điểm thực tế. Có thể cần data quality rule hoặc provenance.

### Schema validation và semantic validation

Schema validation xác nhận dữ liệu có đúng cấu trúc. Semantic validation kiểm tra ý nghĩa, ví dụ Order total phải bằng tổng các line item cộng thuế. Domain invariant thường cần logic riêng.

### Data contract tests

Producer có thể kiểm thử payload thực tế với schema; consumer có thể khai báo assumptions và kiểm thử compatibility. Contract tests giúp phát hiện sai lệch trước deployment.

## 30. Security và privacy metadata

Schema có thể là nơi khai báo phân loại dữ liệu và quy tắc xử lý.

Ví dụ:

~~~text
schema CustomerProfile {
    id: CustomerId {
        classification = internal;
    }

    email: EmailAddress {
        classification = personal;
        pii = true;
    }

    accessToken: Secret {
        classification = secret;
        writeOnly = true;
        log = never;
    }
}
~~~

### PII và sensitive data

Schema có thể đánh dấu field chứa thông tin cá nhân, tài chính hoặc bí mật. Tooling dùng metadata này để cảnh báo khi log, export hoặc expose field.

### Secret type

Secret nên có kiểu/reference chuyên biệt thay vì String thông thường. Điều này giúp tránh serialize secret vào response, log hoặc debug output.

### Read/write access

Field-level access metadata có thể hỗ trợ API projection hoặc authorization policy, nhưng quyết định quyền phải được kiểm tra ở runtime trên server.

### Redaction

Redaction có thể thay giá trị bằng placeholder khi hiển thị log hoặc error. Không nên thay đổi payload gốc trước khi validation nếu điều đó làm sai semantics.

### Retention và deletion

Schema metadata có thể chỉ định retention category hoặc deletion policy. Thực thi thực tế cần tích hợp storage, audit và legal policy.

### Không để schema tự trở thành security boundary

Một field được đánh dấu internal không tự động ngăn API trả field đó. Runtime serializer, authorization và API contract phải thực thi metadata.

## 31. Schema references và dependency graph

Schema lớn thường tham chiếu các type khác.

Ví dụ:

~~~text
schema Order {
    customer: CustomerRef required;
    items: List<OrderItem> required;
    shippingAddress: Address;
}

schema OrderItem {
    product: ProductRef required;
    quantity: Integer min 1;
    price: Money required;
}
~~~

### Namespace

Namespace tránh xung đột tên và hỗ trợ phân chia ownership.

### Import

Schema có thể import type từ module hoặc package khác. Dependency cần pin version để build tái lập.

### Circular dependencies

Schema A tham chiếu B và B tham chiếu A có thể hợp lệ với reference identity, nhưng có thể gây khó cho code generation và initialization. Cần hỗ trợ forward declaration hoặc tách shared type module.

### Dependency resolution

Resolver cần phát hiện missing schema, version conflict, duplicate identity và cycle không hợp lệ. Error nên chỉ rõ đường dependency gây vấn đề.

### Reference URI

Một reference có thể dùng fully qualified name, registry ID hoặc URI. Không nên dùng path file cục bộ làm public identity nếu schema cần trao đổi giữa nhiều repository.

## 32. Code generation từ schema

Schema có thể là đầu vào cho nhiều generator.

~~~mermaid
flowchart TD
    A[Schema DSL] --> B[Parse and resolve]
    B --> C[Canonical schema model]
    C --> D[Runtime validators]
    C --> E[Java DTOs]
    C --> F[OpenAPI / JSON Schema]
    C --> G[Database mapping]
    C --> H[Serialization adapters]
    C --> I[Documentation]
    C --> J[Test fixtures]
~~~

### Canonical schema model

Nên chuyển source DSL thành một model chuẩn đã resolve type, reference và metadata. Các generator dùng cùng model để tránh mỗi generator diễn giải source theo cách riêng.

### Deterministic generation

Cùng schema version và generator version nên tạo output ổn định. Thứ tự field, import, annotation và naming cần được xác định.

### Generated code ownership

File generated nên được đánh dấu và không sửa tay nếu lần generate tiếp theo ghi đè. Custom behavior có thể được đặt trong partial class, adapter hoặc extension point được thiết kế.

### Generator version

Generated artifact có thể thay đổi khi generator được nâng cấp dù schema không đổi. Build cần ghi generator/toolchain version để tái lập.

### Source mapping

Diagnostic từ generated validator hoặc target schema nên có khả năng trỏ về schema DSL field/constraint nguồn.

## 33. API error schema và validation response

Khi payload không hợp lệ, API nên trả lỗi có cấu trúc.

Ví dụ:

~~~json
{
  "type": "https://api.example.test/problems/validation",
  "title": "Request validation failed",
  "status": 400,
  "code": "VALIDATION_ERROR",
  "errors": [
    {
      "path": "/items/0/quantity",
      "code": "MINIMUM",
      "message": "Quantity must be at least 1",
      "expected": 1,
      "actual": 0
    }
  ],
  "traceId": "trace-abc123"
}
~~~

### Stable error code

Client nên xử lý error code, không parse message text. Message có thể đổi hoặc dịch.

### JSON Pointer hoặc field path

Path cần xác định field lỗi trong payload. JSON Pointer hoặc một path syntax chuẩn giúp client focus đúng field.

### Nhiều lỗi

Validator có thể trả nhiều lỗi trong một response. Cần giới hạn số lỗi và payload để tránh phản hồi quá lớn với dữ liệu rất sai.

### Không tiết lộ nội bộ

Không trả stack trace, SQL, secret hoặc internal class name cho client. Có thể trả trace ID để support tra log có quyền.

### Error schema version

Error response cũng là schema contract và cần compatibility. Client cũ phải có fallback khi gặp error code mới.

## 34. Schema cho pagination, filtering và sorting

API collection thường cần contract cho page request và response.

~~~text
schema PageRequest {
    limit: Integer min 1 max 200 default 50;
    cursor: String optional;
}

schema Page<T> {
    items: List<T> required;
    nextCursor: String optional;
    hasMore: Boolean required;
}
~~~

### Offset pagination

Dùng offset và limit đơn giản nhưng có thể gây duplicate/missing khi dữ liệu thay đổi giữa các page và offset lớn có chi phí cao.

### Cursor pagination

Cursor biểu diễn vị trí tiếp tục. Nó cần opaque với client và gắn với sort order hoặc snapshot semantics.

### Filter schema

Filter nên mô tả field nào được phép lọc, operator nào hợp lệ và kiểu operand tương ứng. Không nên cho client gửi tên field tùy ý để tạo query động thiếu kiểm soát.

### Sort schema

Sort field và direction cần allowlist. Với nhiều field, cần quy định stable tie-breaker để pagination nhất quán.

### Query complexity

Schema query có thể giới hạn số filter, độ sâu lồng, số sort field và page size để tránh request tốn tài nguyên.

## 35. Schema cho PATCH và partial update

Partial update cần semantics rõ vì field có thể missing, null hoặc mang giá trị mới.

Ví dụ payload:

~~~json
{
  "displayName": "An Nguyen",
  "phone": null
}
~~~

Một contract có thể định nghĩa:
- displayName có mặt: cập nhật tên.
- phone có mặt và null: xóa số điện thoại.
- address bị thiếu: giữ nguyên địa chỉ.

### Presence-aware field

Có thể biểu diễn field bằng trạng thái Absent, Present(value) hoặc Present(null) nếu null được phép. Cách này tránh mất thông tin khi deserialize vào object mà field không có mặt.

### Merge Patch và JSON Patch

JSON Merge Patch dùng object merge semantics, trong đó null thường được dùng để xóa member. JSON Patch dùng danh sách operation như add, remove, replace, move và test. Hai format có semantics khác nhau và schema cần mô tả đúng contract.

### Validation sau merge

Với partial update, validation field riêng chưa đủ. Sau khi merge với state hiện tại, cần kiểm tra invariant của toàn object. Ví dụ thay currency mà không cập nhật amount có thể tạo dữ liệu không hợp lệ.

### Concurrency

PATCH có thể dùng ETag/If-Match hoặc version field để tránh ghi đè update đồng thời. Schema mô tả payload không thay thế concurrency contract.

## 36. Schema và serialization compatibility

Một schema có thể hợp lệ nhưng serializer/deserializer vẫn không tương thích.

Các vấn đề thường gặp:
- Number lớn vượt giới hạn JavaScript safe integer.
- Decimal bị chuyển thành floating point.
- Timestamp mất timezone hoặc precision.
- Null và missing bị gộp.
- Unknown enum value bị reject.
- Field order ảnh hưởng signature dù semantics object không đổi.
- Binary field encode sai Base64 variant.
- Unicode normalization khác nhau.
- Map key không phải string bị biến đổi.
- Polymorphic subtype thiếu discriminator.

### Wire compatibility test

Nên kiểm tra payload được tạo bởi version producer cũ có đọc được bởi consumer mới và ngược lại theo compatibility policy.

### Golden payload

Lưu các payload đại diện cho schema version. Dùng chúng để kiểm thử serialization, deserialization và migration.

### Round-trip

Serialize rồi deserialize cần giữ semantics. Với canonicalization hoặc default materialization, byte output có thể khác nhưng model semantics cần được xác định rõ.

## 37. Quản trị schema và ownership

Schema là tài sản dùng chung. Nếu không có ownership, field có thể được thêm/xóa mà không ai biết consumer nào bị ảnh hưởng.

### Schema owner

Mỗi schema nên có team hoặc domain owner chịu trách nhiệm về meaning và evolution.

### Consumer inventory

Registry hoặc catalog nên ghi consumer sử dụng schema nào, version nào và qua API/topic nào. Điều này giúp đánh giá blast radius trước breaking change.

### Review policy

Thay đổi schema public có thể cần review từ producer owner, consumer đại diện, security và data governance tùy loại dữ liệu.

### Deprecation notice

Thông báo field/schema deprecated cần có replacement, thời gian sunset và kế hoạch hỗ trợ consumer.

### Schema catalog

Catalog có thể cho phép tìm theo domain, owner, tag, classification, producer và consumer. Description và example giúp giảm việc tạo schema trùng lặp.

### Data lineage

Schema có thể liên kết với nguồn dữ liệu và output downstream. Lineage hỗ trợ hiểu tác động khi field thay đổi.

## 38. Kiểm thử schema

Schema cần được kiểm thử như một contract có thể thực thi.

### Schema compilation tests

Xác nhận cú pháp, reference, namespace, dependency và constraint được resolve.

### Positive validation tests

Payload hợp lệ phải được chấp nhận. Bao gồm boundary values, optional fields, defaults và nested structures.

### Negative validation tests

Payload sai kiểu, thiếu required field, enum không hợp lệ, number ngoài range hoặc reference không resolve phải bị từ chối với error code phù hợp.

### Compatibility tests

Kiểm tra schema version mới theo backward/forward/full compatibility policy.

### Serialization tests

Kiểm tra round-trip, canonicalization, number precision, timestamp, Unicode, null/missing và unknown fields.

### Code generation tests

Sinh Java DTO, validator và OpenAPI rồi compile hoặc kiểm tra contract. Cần xác nhận generated code không mất semantics của schema nguồn.

### Migration tests

Dùng fixture schema cũ để migrate sang mới, kiểm tra data loss, default, rename, split/merge và rollback policy.

### Consumer-driven contract tests

Consumer khai báo assumptions quan trọng; producer chạy contract tests để xác nhận response thực tế vẫn đáp ứng. Điều này bổ sung cho schema compatibility tĩnh.

### Security tests

Kiểm tra PII/secret metadata, redaction, read-only/write-only, field authorization và không rò dữ liệu qua validation error.

## 39. Những lỗi thiết kế thường gặp

**Dùng String cho mọi kiểu.** Identifier, email, date, currency và secret có semantics khác nhau. Kiểu chuyên biệt giúp validation và tooling chính xác hơn.

**Không phân biệt optional với nullable.** Payload missing và explicit null có thể mang ý nghĩa khác, nhất là trong PATCH.

**Dùng Float cho tiền tệ.** Sai số dấu phẩy động có thể gây lệch khi tính và serialize. Nên dùng Decimal với precision/scale hoặc integer minor units theo contract.

**Dùng một schema cho request và response.** Client có thể gửi field server-owned hoặc không nhận được field cần thiết. Tách schema theo direction và use case.

**Không mô tả đơn vị.** Một field timeout: Integer không cho biết milliseconds hay seconds. Unit phải là một phần semantics.

**Dùng enum mà không tính unknown values.** Consumer có thể crash khi producer thêm giá trị mới. Cần chiến lược extensibility phù hợp.

**Thêm required field vào schema đang dùng.** Producer cũ có thể không gửi field mới và consumer mới sẽ từ chối. Cần default, migration hoặc version mới.

**Đổi semantics mà giữ nguyên tên và kiểu.** Ví dụ amount chuyển từ gross sang net nhưng vẫn Decimal. Đây là breaking change dù schema syntax không đổi.

**Cho phép unknown fields không có chủ đích.** Strictness cần phù hợp boundary; permissive quá mức có thể che typo hoặc field injection.

**Không quản lý schema references.** Dependency không pin version có thể làm cùng một schema resolve ra cấu trúc khác ở các lần build.

**Sinh nhiều output từ các parser khác nhau.** OpenAPI, DTO và validator có thể hiểu schema khác nhau. Nên dùng canonical schema model chung.

**Coi validation là bảo đảm data quality.** Schema đúng không chứng minh dữ liệu phản ánh sự thật hoặc còn mới.

**Không có owner và consumer inventory.** Breaking change có thể làm hỏng service mà producer không biết.

**Không kiểm thử serialization thực tế.** Schema compatibility trên giấy không bảo đảm wire format giữ đúng number, timestamp, null và enum semantics.

## 40. Quy trình thiết kế schema trong một DSL

Một quy trình thực tế có thể gồm:

1. **Xác định mục đích:** domain model, API request/response, event, configuration hay persistence schema.
2. **Xác định owner và namespace:** chọn identity ổn định và team chịu trách nhiệm.
3. **Mô hình hóa field:** tên, type, description, unit, requiredness và mutability.
4. **Chọn type semantics:** integer, decimal, temporal, enum, collection, record, union và reference.
5. **Định nghĩa constraint:** range, pattern, cardinality, uniqueness và cross-field invariant.
6. **Định nghĩa null/default:** phân biệt missing, null, default và computed value.
7. **Thiết kế relationship:** embedded, reference, ownership và cardinality.
8. **Thiết kế serialization:** JSON, XML, Avro, Protobuf hoặc format khác.
9. **Định nghĩa validation:** compile-time, boundary, domain và persistence checks.
10. **Định nghĩa API/event usage:** request/response direction, error, pagination và partial update semantics.
11. **Thiết kế evolution:** versioning, compatibility, migration và deprecation.
12. **Thêm metadata:** examples, sensitivity, owner, retention và documentation.
13. **Sinh artifact:** DTO, validators, OpenAPI, serializer, migration và documentation.
14. **Kiểm thử:** positive/negative, compatibility, wire, migration, security và consumer contracts.
15. **Đăng ký và phát hành:** schema registry, review, release notes và consumer notification.

## 41. Checklist trước khi publish schema

Trước khi publish một schema dùng chung, cần xác nhận:

- Schema có namespace và identity ổn định không?
- Owner và mục đích sử dụng đã rõ chưa?
- Mỗi field có type và description đủ cụ thể không?
- Unit, precision, scale và temporal semantics đã được ghi chưa?
- Required, optional, nullable và default có phân biệt rõ không?
- Collection có cardinality và ordering semantics không?
- Enum có policy cho unknown value không?
- Reference có identity, scope và resolution policy không?
- Cross-field constraints có được mô tả và kiểm thử không?
- Request/response/event schema có tách theo direction không?
- Unknown field policy có phù hợp boundary không?
- Serialization mapping có giữ đúng semantics không?
- Schema version và compatibility mode đã xác định chưa?
- Migration/backfill có kế hoạch và test không?
- PII, secret, read-only/write-only và retention được đánh dấu chưa?
- Generated DTO/validator/OpenAPI có tương đương schema nguồn không?
- Consumer inventory và deprecation policy có sẵn không?
- Example payload không chứa dữ liệu nhạy cảm thật không?

## 42. Kết quả cần có sau khi thiết kế mô tả schema

Một thiết kế schema description hoàn chỉnh cho DSL API và dữ liệu thường cung cấp:

- **Schema identity:** namespace, name, version và owner.
- **Type system:** primitive, decimal, temporal, identifier, enum, record, collection, union và reference.
- **Field contract:** type, requiredness, nullability, default, mutability và direction.
- **Constraint model:** range, length, pattern, cardinality, uniqueness, cross-field và referential integrity.
- **Relationship model:** embedded value, entity reference, ownership, inheritance và composition.
- **Serialization contract:** JSON/XML/binary mapping, encoding, canonicalization và unknown field policy.
- **API/event contract:** request/response, event envelope, error schema, pagination và partial update semantics.
- **Validation pipeline:** parse, schema compile, runtime boundary, domain và persistence validation.
- **Evolution strategy:** schema version, compatibility policy, migration, deprecation và registry.
- **Generated artifacts:** Java DTO, validators, serializers, OpenAPI, database mapping và documentation.
- **Governance metadata:** owner, examples, sensitivity, lineage, retention và access policy.
- **Test strategy:** positive/negative, compatibility, serialization, migration, consumer contract và security.

Mô tả schema là nền tảng để các thành phần trong hệ thống hiểu dữ liệu theo cùng một hợp đồng. Một schema hữu ích cần định nghĩa rõ identity, type, field, cardinality, constraint, reference và semantics của missing/null/default; đồng thời chỉ ra cách dữ liệu được serialize, validate và tiến hóa qua các phiên bản. Trong DSL API và dữ liệu, schema nên được chuyển thành một canonical model để nhiều công cụ cùng sử dụng cho OpenAPI, DTO, validator, persistence mapping và tài liệu. Khi có owner, compatibility policy, migration và contract tests, schema trở thành tài sản có thể quản trị lâu dài, giúp producer và consumer thay đổi độc lập mà vẫn duy trì khả năng tương tác.

