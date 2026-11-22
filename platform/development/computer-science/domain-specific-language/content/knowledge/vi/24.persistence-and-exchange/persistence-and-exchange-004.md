# Schema dữ liệu

Trong một ngôn ngữ chuyên biệt cho lĩnh vực (Domain-Specific Language — DSL), mô hình thường mô tả các khái niệm nghiệp vụ như khách hàng, đơn hàng, sản phẩm, giao dịch, sự kiện và quan hệ giữa chúng. Khi dữ liệu cần được lưu vào cơ sở dữ liệu, ghi thành tệp hoặc trao đổi qua API, hệ thống phải có một cách thống nhất để mô tả cấu trúc dữ liệu, kiểu của từng trường, trường bắt buộc, ràng buộc và cách biểu diễn giá trị. Mô tả có cấu trúc đó được gọi là **schema dữ liệu (data schema)**.

Schema dữ liệu xác định hình dạng và các quy tắc mà dữ liệu cần tuân thủ. Ví dụ, schema của Order có thể quy định rằng mỗi đơn hàng có định danh, trạng thái, thời điểm tạo, tổng tiền và tham chiếu đến khách hàng. Trường định danh là bắt buộc; trạng thái chỉ nhận một số giá trị đã định nghĩa; tổng tiền là số thập phân không âm; thời điểm tạo dùng một định dạng thời gian thống nhất.

Schema giúp các thành phần khác nhau hiểu dữ liệu theo cùng một hợp đồng. DSL có thể dùng một mô hình miền làm nguồn để sinh SQL DDL, JSON Schema, OpenAPI schema hoặc cấu trúc serialization cho một định dạng trao đổi. Tuy nhiên, mỗi đích có khả năng và giới hạn riêng, vì vậy cần định nghĩa rõ cách ánh xạ và bảo toàn ngữ nghĩa.

Bài học này trình bày khái niệm schema dữ liệu, các lớp schema, thành phần thường gặp, cách mô tả kiểu và ràng buộc, quan hệ giữa schema với lưu trữ và trao đổi, quản lý phiên bản, tương thích ngược, migration, validation, sinh schema từ DSL và các kỹ thuật kiểm thử.

## 1. Schema dữ liệu là gì?

Schema dữ liệu là bản mô tả có cấu trúc về dữ liệu hợp lệ. Nó quy định dữ liệu gồm những trường hoặc thành phần nào, kiểu dữ liệu của chúng, cách tổ chức quan hệ và các điều kiện mà giá trị phải thỏa mãn.

Ví dụ, một schema đơn giản cho khách hàng:

~~~json
{
  "type": "object",
  "properties": {
    "id": {
      "type": "string",
      "format": "uuid"
    },
    "name": {
      "type": "string",
      "minLength": 1,
      "maxLength": 120
    },
    "email": {
      "type": "string",
      "format": "email"
    },
    "active": {
      "type": "boolean"
    }
  },
  "required": ["id", "name", "email"]
}
~~~

Schema này mô tả một đối tượng có các trường id, name, email và active. Ba trường đầu là bắt buộc; active có thể vắng mặt theo quy tắc của schema. Nếu dữ liệu có name là chuỗi rỗng hoặc email không đúng định dạng, validator có thể từ chối dữ liệu.

Schema không nhất thiết phải là JSON. Nó có thể được biểu diễn bằng SQL DDL, XML Schema, Protocol Buffers, Avro, một metamodel của DSL hoặc một định dạng khai báo riêng.

### 1.1. Schema mô tả cấu trúc và hợp đồng

Schema thường có hai nhóm thông tin:

- **Cấu trúc:** tên trường, kiểu dữ liệu, collection, object lồng nhau, quan hệ và thứ tự nếu định dạng yêu cầu.
- **Quy tắc:** trường bắt buộc, miền giá trị, độ dài, pattern, uniqueness, default, reference và các constraint khác.

Ví dụ, việc một trường có kiểu Integer chỉ xác định loại giá trị cơ bản. Schema có thể bổ sung rằng số đó phải nằm trong khoảng 1 đến 100, hoặc phải là duy nhất trong một bảng.

### 1.2. Schema không phải dữ liệu thực tế

Cần phân biệt:

| Khái niệm | Ý nghĩa | Ví dụ |
| --- | --- | --- |
| Schema | Quy tắc mô tả dữ liệu hợp lệ | Order có id, status và total |
| Record hoặc instance | Một giá trị dữ liệu cụ thể | Đơn hàng 1024 có total là 250000 |
| Model | Biểu diễn khái niệm và quan hệ trong miền | Entity Order liên kết với Customer |
| Serialization format | Cách mã hóa dữ liệu thành byte hoặc văn bản | JSON, XML, Avro binary |
| Data contract | Thỏa thuận giữa bên tạo và bên nhận dữ liệu | API trả Order theo schema phiên bản 2 |

Một schema có thể được dùng để kiểm tra nhiều record. Một record thường tuân theo một schema hoặc một phiên bản schema cụ thể.

### 1.3. Schema có thể được dùng ở nhiều giai đoạn

Schema không chỉ phục vụ lúc ghi dữ liệu. Nó có thể được dùng để:

- Kiểm tra mô hình DSL trước khi sinh mã.
- Tạo cấu trúc bảng và constraint trong cơ sở dữ liệu.
- Kiểm tra request và response của API.
- Xác định cách serialize và deserialize.
- Sinh class, DTO hoặc type definition.
- Tài liệu hóa hợp đồng trao đổi.
- Hỗ trợ migration và kiểm soát thay đổi.
- Kiểm tra dữ liệu cũ khi nâng cấp hệ thống.

## 2. Vai trò của schema trong DSL

DSL thường cho phép người dùng mô tả dữ liệu ở mức gần với miền nghiệp vụ. Schema cung cấp hợp đồng để chuyển mô hình đó thành cấu trúc có thể lưu trữ hoặc trao đổi.

Ví dụ DSL:

~~~text
entity Customer {
  id: UUID required
  name: String required length(1..120)
  email: Email required unique
  active: Boolean default true
}

entity Order {
  id: UUID required
  customer: Customer required
  total: Decimal required min(0)
  status: OrderStatus default PENDING
}
~~~

Từ mô hình này, hệ thống có thể tạo nhiều loại schema:

- SQL schema để tạo bảng Customer và Order.
- JSON Schema để kiểm tra payload API.
- Java hoặc TypeScript type để hỗ trợ lập trình.
- Avro hoặc Protobuf schema để trao đổi message.
- Tài liệu mô tả các trường và ràng buộc.

### 2.1. Một nguồn mô hình, nhiều schema đích

Một kiến trúc phổ biến:

~~~text
DSL Source
    |
    v
Parser
    |
    v
Validated Domain Model
    |
    +------------------+
    |                  |
    v                  v
SQL Schema       JSON Schema
    |                  |
    v                  v
Database         API Validation

    +------------------+
    |
    v
Java / TypeScript Types
    |
    v
Application Code
~~~

Mô hình nguồn giúp giữ một định nghĩa miền thống nhất. Mỗi generator chuyển đổi mô hình thành schema phù hợp với mục đích đích.

### 2.2. Không phải mọi ràng buộc đều ánh xạ trực tiếp

Một constraint có thể được hỗ trợ ở một đích nhưng không có biểu diễn tương đương ở đích khác.

Ví dụ:

- SQL có thể hỗ trợ unique constraint trong bảng.
- JSON Schema có thể kiểm tra cấu trúc và một số điều kiện trong một document.
- Một quy tắc cần truy vấn dữ liệu ở bảng khác có thể cần application validation.
- Một invariant liên quan nhiều service có thể cần runtime hoặc transaction logic.

Generator phải biết giới hạn của target. Nếu không thể biểu diễn constraint, cần báo rõ hoặc sinh một bước kiểm tra bổ sung; không nên âm thầm bỏ qua.

## 3. Các lớp schema: khái niệm, logic và vật lý

Trong thiết kế dữ liệu, schema có thể được xem xét ở nhiều mức trừu tượng.

### 3.1. Conceptual schema

Conceptual schema mô tả các khái niệm chính của miền và quan hệ giữa chúng mà chưa tập trung vào chi tiết triển khai.

Ví dụ:

~~~text
Customer places Order
Order contains OrderItem
OrderItem refers to Product
~~~

Ở mức này, người thiết kế quan tâm đến ý nghĩa nghiệp vụ, cardinality và các quy tắc tổng quát.

### 3.2. Logical schema

Logical schema mô tả chi tiết cấu trúc dữ liệu độc lập tương đối với một hệ quản trị cụ thể:

- Entity hoặc relation.
- Attribute và kiểu logic.
- Primary key và foreign key.
- Cardinality.
- Nullability.
- Unique và check constraint.
- Chuẩn hóa và phụ thuộc dữ liệu.

Ví dụ:

~~~text
Customer(
  customerId: UUID [PK],
  name: String [NOT NULL],
  email: String [NOT NULL, UNIQUE]
)

Order(
  orderId: UUID [PK],
  customerId: UUID [FK -> Customer.customerId],
  createdAt: Instant [NOT NULL]
)
~~~

### 3.3. Physical schema

Physical schema mô tả cách dữ liệu được triển khai trên một công nghệ cụ thể:

- Tên bảng và cột thực tế.
- Kiểu dữ liệu cụ thể của database.
- Index.
- Partition.
- Tablespace hoặc storage option.
- Encoding và collation.
- Chiến lược khóa và tối ưu truy vấn.

Ví dụ, kiểu logic Decimal có thể được ánh xạ thành DECIMAL(18, 2) trong một database. Một database khác có thể dùng NUMERIC(18, 2) hoặc một kiểu tương đương.

### 3.4. Quan hệ giữa ba lớp

~~~text
Conceptual Schema
  Khách hàng đặt đơn hàng
          |
          v
Logical Schema
  Customer, Order, OrderItem
  keys, attributes, constraints
          |
          v
Physical Schema
  table, column, index, database types
~~~

Tách các lớp giúp mô hình miền ít phụ thuộc vào một database cụ thể. Khi đổi database hoặc thêm target trao đổi, hệ thống có thể giữ conceptual model và thay đổi phần physical mapping.

## 4. Các thành phần cơ bản của schema

Một schema thường chứa các thành phần sau.

### 4.1. Định danh và tên

Mỗi schema, entity, field hoặc type cần có tên hoặc định danh ổn định. Tên hiển thị có thể thay đổi, nhưng định danh dùng trong migration và tham chiếu nên được quản lý cẩn thận.

Ví dụ:

~~~text
schema sales
entity Order
property orderId
~~~

Tên cần tuân thủ quy tắc của DSL và có thể phải được ánh xạ sang tên bảng, cột hoặc field trong định dạng đích.

### 4.2. Kiểu dữ liệu

Kiểu xác định tập giá trị được chấp nhận và các phép toán hợp lệ.

Các nhóm thường gặp:

- Boolean.
- Integer, Long, Decimal.
- String và Text.
- Date, Time, Instant.
- UUID hoặc identifier miền.
- Enum.
- Object hoặc record.
- Array, List, Set và Map.
- Binary.
- Reference đến entity hoặc schema khác.

### 4.3. Nullability và requiredness

Một trường có thể bắt buộc, có thể vắng mặt hoặc cho phép giá trị null. Đây là các khái niệm cần được phân biệt.

Ví dụ:

~~~text
property phone: String optional
property nickname: String nullable
property email: String required
~~~

Tùy DSL, optional có thể nghĩa là trường được phép không xuất hiện; nullable nghĩa là trường có thể xuất hiện với giá trị null. Có định dạng gộp hai trường hợp này, có định dạng phân biệt chúng.

### 4.4. Default value

Giá trị mặc định được áp dụng khi trường không được cung cấp theo quy tắc của schema hoặc runtime.

~~~text
property active: Boolean default true
property retryCount: Integer default 3
~~~

Cần quy định default được áp dụng ở bước nào: khi tạo record, khi đọc, trong database hay trong application. Default của SQL column không tự động có nghĩa JSON payload thiếu trường sẽ được điền giá trị.

### 4.5. Constraint

Constraint mô tả điều kiện mà dữ liệu phải thỏa mãn:

- Minimum và maximum.
- Độ dài chuỗi.
- Pattern.
- Unique.
- Not null.
- Referential integrity.
- Check expression.
- Cardinality.
- Quan hệ giữa nhiều trường.

Một schema tốt thể hiện được các quy tắc quan trọng và xác định nơi thực thi chúng.

### 4.6. Quan hệ và tham chiếu

Schema có thể mô tả object lồng nhau, reference theo ID, foreign key hoặc liên kết đến schema khác.

Ví dụ, Order có thể chứa customerId thay vì nhúng toàn bộ Customer. Cách biểu diễn phụ thuộc yêu cầu lưu trữ, kích thước payload, quyền truy cập và vòng đời dữ liệu.

## 5. Thiết kế kiểu dữ liệu

Chọn kiểu dữ liệu không chỉ là chọn tên. Cần xem xét miền giá trị, độ chính xác, cách serialize và khả năng tương thích giữa các nền tảng.

### 5.1. Số nguyên

Integer thường dùng cho số đếm, số lượng hoặc định danh dạng số. Cần xác định miền giá trị và khả năng tràn số.

Một kiểu Integer 32-bit có miền nhỏ hơn Integer 64-bit. Nếu dữ liệu có thể tăng vượt giới hạn, schema nên dùng kiểu rộng hơn hoặc kiểu định danh khác.

### 5.2. Số thập phân

Decimal phù hợp với tiền tệ, tỷ lệ hoặc dữ liệu cần độ chính xác thập phân. Schema có thể khai báo precision và scale:

~~~text
property unitPrice: Decimal(precision = 18, scale = 2)
~~~

Precision là tổng số chữ số có nghĩa; scale là số chữ số sau dấu thập phân. Cần kiểm tra quy tắc làm tròn và giá trị vượt giới hạn.

Dùng floating-point cho tiền tệ có thể tạo sai số. Việc ánh xạ sang database, Java hoặc định dạng message cần bảo toàn độ chính xác theo hợp đồng.

### 5.3. Chuỗi

String có thể cần các ràng buộc:

~~~text
property code: String length(3..20)
property email: String format(email)
property countryCode: String pattern("[A-Z]{2}")
~~~

Schema cần xác định độ dài tính theo byte, code point hay ký tự theo quy ước của nền tảng. Unicode có thể khiến số byte và số ký tự khác nhau.

### 5.4. Ngày và thời gian

Nên phân biệt:

- Date: ngày lịch, không có giờ.
- Time: thời gian trong ngày.
- LocalDateTime: ngày và giờ không gắn múi giờ.
- Instant: thời điểm tuyệt đối.
- ZonedDateTime: thời điểm kèm múi giờ.

Trong trao đổi dữ liệu, ISO 8601 thường được dùng cho ngày và thời gian. Cần quy định múi giờ, độ chính xác và cách xử lý giá trị không có offset.

### 5.5. UUID và định danh miền

UUID hữu ích khi cần định danh phân tán. Tuy nhiên, một ID miền như CustomerId có thể được biểu diễn bằng UUID nhưng vẫn nên giữ tên kiểu riêng trong mô hình để tránh nhầm lẫn giữa các loại ID.

~~~text
type CustomerId = UUID
type OrderId = UUID
~~~

Hai kiểu có cùng biểu diễn cơ sở nhưng mang ý nghĩa khác nhau. Type system và schema nên giữ được sự phân biệt nếu điều đó quan trọng với miền.

### 5.6. Enum

Enum giới hạn giá trị vào một tập hữu hạn:

~~~text
enum OrderStatus {
  PENDING
  CONFIRMED
  PAID
  CANCELLED
}
~~~

Khi serialize, cần quyết định dùng tên symbol, chuỗi hiển thị hay số ordinal. Dùng ordinal có thể nguy hiểm nếu thứ tự enum thay đổi giữa phiên bản. Dùng tên ổn định thường dễ đọc hơn, nhưng việc đổi tên enum value cũng cần quản lý tương thích.

## 6. Object, collection và kiểu lồng nhau

Schema thường cần mô tả dữ liệu phức tạp hơn scalar.

### 6.1. Object lồng nhau

Ví dụ:

~~~json
{
  "type": "object",
  "properties": {
    "shippingAddress": {
      "type": "object",
      "properties": {
        "street": { "type": "string" },
        "city": { "type": "string" },
        "postalCode": { "type": "string" }
      },
      "required": ["street", "city"]
    }
  }
}
~~~

Object lồng nhau phù hợp với dữ liệu có cấu trúc thuộc về một record và thường được đọc cùng nhau. Tuy nhiên, nếu object có vòng đời riêng hoặc được nhiều record tham chiếu, có thể cần một entity độc lập.

### 6.2. Array và List

Array hoặc List biểu diễn một dãy phần tử có thứ tự:

~~~text
property tags: List<String>
property lineItems: List<OrderItem>
~~~

Schema có thể giới hạn số phần tử:

~~~text
property tags: List<String> size(0..20)
~~~

Cần xác định thứ tự có ý nghĩa hay không và phần tử trùng lặp có được phép không.

### 6.3. Set

Set biểu diễn tập phần tử duy nhất, không nhất thiết có thứ tự. Nếu target chỉ có array, generator có thể sinh validation để phát hiện phần tử trùng hoặc chuẩn hóa thành tập.

### 6.4. Map

Map ánh xạ key sang value:

~~~text
property labels: Map<String, String>
~~~

Cần quy định kiểu key, cách serialize và thứ tự nếu định dạng đích có thể sắp xếp. JSON object chỉ hỗ trợ key dạng chuỗi; map có key phức tạp có thể cần chuyển thành danh sách cặp key/value.

### 6.5. Recursive schema

Một kiểu có thể tham chiếu chính nó:

~~~text
entity Category {
  id: UUID
  name: String
  parent: Category?
  children: List<Category>
}
~~~

Schema đệ quy cần cơ chế reference thay vì lặp vô hạn khi mở rộng định nghĩa. Khi serialize dữ liệu, cần xác định cách xử lý chu trình object graph, độ sâu tối đa và việc tham chiếu bằng ID hay nhúng object.

## 7. Required, optional, null và default

Đây là nhóm khái niệm dễ gây lỗi khi chuyển schema giữa các định dạng.

### 7.1. Trường vắng mặt khác với null

Một payload:

~~~json
{
  "name": "An"
}
~~~

không có trường nickname.

Payload khác:

~~~json
{
  "name": "An",
  "nickname": null
}
~~~

có trường nickname với giá trị null.

Một số hệ thống xem hai trường hợp tương đương; hệ thống khác dùng chúng để phân biệt “không thay đổi”, “xóa giá trị” hoặc “không biết”.

### 7.2. Required không nhất thiết cấm null

Một trường có thể bắt buộc xuất hiện nhưng cho phép null. Ví dụ, schema có thể yêu cầu key nickname tồn tại nhưng giá trị có thể là string hoặc null.

Ngược lại, một trường có thể không bắt buộc xuất hiện nhưng nếu xuất hiện thì phải là string khác null.

### 7.3. Default không tự động điền ở mọi tầng

Giả sử schema khai báo default là true cho active. Điều đó có thể có các ý nghĩa khác nhau:

- Validator chỉ xem giá trị thiếu là hợp lệ.
- Deserializer điền true khi trường vắng mặt.
- Database áp dụng DEFAULT khi INSERT không cung cấp cột.
- Application constructor khởi tạo true.

Các tầng này không tự động đồng bộ. Cần xác định default là một phần của schema contract hay chỉ là hành vi của một implementation.

### 7.4. Bảng quyết định

| Trạng thái đầu vào | Ý nghĩa cần định nghĩa |
| --- | --- |
| Không có trường | Absent hoặc dùng default |
| Trường có null | Null tường minh |
| Trường có giá trị | Giá trị được cung cấp |
| Trường có giá trị sai kiểu | Validation error |
| Trường có giá trị ngoài miền | Constraint violation |

Schema và runtime cần thống nhất cách xử lý từng trạng thái.

## 8. Ràng buộc dữ liệu

Schema không chỉ mô tả hình dạng mà còn có thể mô tả các điều kiện hợp lệ.

### 8.1. Ràng buộc miền giá trị

Ví dụ:

~~~text
property age: Integer min(0) max(130)
property score: Decimal min(0) max(100)
~~~

Validator kiểm tra giá trị nằm trong khoảng. Cần quy định biên có bao gồm hay không và xử lý giá trị null thế nào.

### 8.2. Ràng buộc chuỗi

Các quy tắc phổ biến:

- minLength và maxLength.
- Pattern hoặc regular expression.
- Format như email, URI hoặc date-time.
- Danh sách giá trị được phép.

Format có thể chỉ là kiểm tra hình thức. Ví dụ một chuỗi đúng cấu trúc email không chứng minh địa chỉ đó tồn tại hoặc người dùng sở hữu nó.

### 8.3. Uniqueness

Unique constraint đảm bảo giá trị không trùng trong phạm vi xác định.

~~~text
property email: Email unique
~~~

Trong database, unique index hoặc constraint có thể thực thi quy tắc này. Validator ở application có thể kiểm tra trước để đưa thông báo thân thiện, nhưng vẫn cần database constraint để xử lý hai request đồng thời.

### 8.4. Referential integrity

Foreign key hoặc reference constraint đảm bảo giá trị trỏ đến một record hợp lệ.

~~~text
Order.customerId references Customer.id
~~~

Nếu target là database quan hệ, có thể sinh foreign key. Nếu target là JSON document hoặc message stream, cần validation hoặc lookup ở tầng ứng dụng.

### 8.5. Constraint liên trường

Một số điều kiện phụ thuộc nhiều trường:

~~~text
constraint dateRange:
  endDate >= startDate
~~~

Một số schema format hỗ trợ biểu diễn một phần điều kiện này; phần còn lại có thể cần application validator.

### 8.6. Invariant cấp entity

Invariant là điều kiện phải đúng với toàn bộ đối tượng:

~~~text
constraint paidOrderHasPayment:
  status != PAID or paymentId != null
~~~

Invariant thường cần validator có khả năng truy cập nhiều trường. Cần xác định nó được kiểm tra khi tạo, cập nhật, serialize hay trước khi commit transaction.

## 9. Khóa và quan hệ dữ liệu

Schema lưu trữ thường cần mô tả định danh và quan hệ giữa các thực thể.

### 9.1. Primary key

Primary key xác định duy nhất một record trong bảng. Nó có thể là một trường hoặc tổ hợp nhiều trường.

~~~text
entity Customer {
  id: UUID primaryKey
  name: String
}
~~~

Một primary key nên ổn định và không phụ thuộc vào thuộc tính có thể thay đổi như tên hoặc email.

### 9.2. Natural key và surrogate key

- Natural key lấy từ dữ liệu miền, chẳng hạn mã quốc gia hoặc mã sản phẩm được quản lý.
- Surrogate key là định danh kỹ thuật, chẳng hạn UUID hoặc số tăng tự động.

Natural key có ý nghĩa nghiệp vụ nhưng có thể thay đổi hoặc có quy tắc duy nhất phức tạp. Surrogate key thường ổn định hơn cho quan hệ nội bộ. Schema có thể giữ cả hai với vai trò khác nhau.

### 9.3. Foreign key

Foreign key liên kết record với record khác:

~~~sql
CREATE TABLE Orders (
    id UUID PRIMARY KEY,
    customer_id UUID NOT NULL,
    FOREIGN KEY (customer_id) REFERENCES Customer(id)
);
~~~

Cần xác định hành vi khi record được tham chiếu bị xóa hoặc thay đổi: restrict, cascade, set null hoặc chính sách khác.

### 9.4. Cardinality

Quan hệ có thể là:

- Một-một.
- Một-nhiều.
- Nhiều-một.
- Nhiều-nhiều.

Cardinality trong mô hình miền cần được ánh xạ đúng sang foreign key, join table hoặc collection. Không nên chỉ tạo collection ở một phía rồi xem đó là đủ để thực thi mọi ràng buộc.

### 9.5. Quan hệ có thuộc tính riêng

Nếu quan hệ có dữ liệu riêng, ví dụ vai trò thành viên hoặc thời điểm tham gia, có thể mô hình hóa thành entity trung gian:

~~~text
entity Membership {
  userId: UserId
  groupId: GroupId
  joinedAt: Instant
  role: MembershipRole
}
~~~

Cấu trúc này biểu diễn rõ khóa, thuộc tính và vòng đời của quan hệ.

## 10. Chuẩn hóa dữ liệu và thiết kế schema quan hệ

Với database quan hệ, schema cần cân nhắc chuẩn hóa để giảm dư thừa và bất nhất.

### 10.1. Vì sao cần chuẩn hóa?

Nếu một bảng lưu lặp thông tin khách hàng trong mọi đơn hàng, việc cập nhật địa chỉ có thể phải sửa nhiều dòng. Nếu chỉ sửa một số dòng, dữ liệu trở nên không nhất quán.

Chuẩn hóa phân tách dữ liệu theo phụ thuộc và quan hệ để giảm các vấn đề:

- Update anomaly: cập nhật không đồng bộ.
- Insert anomaly: không thể thêm một thông tin nếu thiếu thông tin khác.
- Delete anomaly: xóa một record vô tình làm mất thông tin cần giữ.

### 10.2. First Normal Form

Một quan hệ thường được thiết kế theo 1NF khi mỗi ô chứa một giá trị nguyên tố theo miền thuộc tính và không lưu danh sách lặp trong một cột theo cách làm khó truy vấn.

Ví dụ, thay vì lưu chuỗi "red,blue,green" trong cột colors nếu cần truy vấn từng màu, có thể dùng bảng liên kết.

### 10.3. Second và Third Normal Form

2NF loại bỏ phụ thuộc bộ phận vào một phần của khóa ghép. 3NF xử lý phụ thuộc bắc cầu không phù hợp giữa thuộc tính không khóa.

Trong thiết kế thực tế, cần hiểu khóa ứng viên và functional dependency trước khi quyết định tách bảng.

### 10.4. Denormalization

Đôi khi hệ thống chủ động lưu dữ liệu dư thừa để tối ưu đọc hoặc phù hợp mô hình document. Đây là denormalization.

Ví dụ, một Order document có thể nhúng snapshot tên khách hàng tại thời điểm mua để hiển thị lịch sử. Dữ liệu snapshot không nhất thiết là bản sao đồng bộ của Customer hiện tại; nó có semantics riêng.

Schema cần ghi rõ dữ liệu nào là nguồn chuẩn và dữ liệu nào là snapshot hoặc cache.

## 11. Schema cho lưu trữ và schema cho trao đổi

Schema dùng cho database và schema dùng cho API/message có mục tiêu khác nhau.

### 11.1. Storage schema

Storage schema tối ưu cho lưu trữ, truy vấn, transaction và tính toàn vẹn:

- Primary key.
- Foreign key.
- Index.
- Unique và check constraint.
- Partition.
- Kiểu dữ liệu cụ thể của database.
- Chính sách xóa và cập nhật.

### 11.2. Exchange schema

Exchange schema mô tả payload trao đổi giữa hệ thống:

- Field name và type.
- Required/optional.
- Serialization format.
- Enum representation.
- Version.
- Compatibility.
- Reference hoặc nested object.
- Metadata cho API hoặc message broker.

Exchange schema cần xem xét tính ổn định qua mạng và khả năng tương thích giữa producer và consumer có thể được triển khai ở các thời điểm khác nhau.

### 11.3. Không nên dùng một schema vật lý cho mọi mục đích

Một bảng database có thể có cột nội bộ như deletedAt, internalNote hoặc tenantPartitionKey mà không nên đưa ra API công khai. Ngược lại, API có thể có trường displayName được tính từ nhiều cột và không được lưu trực tiếp.

Có thể dùng một domain model chung rồi định nghĩa storage projection và exchange projection riêng.

~~~text
Domain Model
   |
   +--> Persistence Schema
   |
   +--> API Request Schema
   |
   +--> API Response Schema
   |
   +--> Event Schema
~~~

Các projection cần có quy tắc mapping và traceability để tránh sai khác ngoài ý muốn.

## 12. JSON Schema

JSON Schema là một cách mô tả cấu trúc và ràng buộc của dữ liệu JSON. Nó thường được dùng để kiểm tra request/response, cấu hình và tài liệu trao đổi.

Ví dụ:

~~~json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "$id": "https://example.org/schemas/order.json",
  "title": "Order",
  "type": "object",
  "properties": {
    "id": {
      "type": "string",
      "format": "uuid"
    },
    "status": {
      "type": "string",
      "enum": ["PENDING", "PAID", "CANCELLED"],
      "default": "PENDING"
    },
    "total": {
      "type": "number",
      "minimum": 0
    }
  },
  "required": ["id", "total"],
  "additionalProperties": false
}
~~~

### 12.1. Các keyword thường gặp

- type: kiểu dữ liệu.
- properties: định nghĩa trường của object.
- required: danh sách trường bắt buộc.
- items: schema cho phần tử array.
- enum: tập giá trị được phép.
- minimum và maximum: giới hạn số.
- minLength và maxLength: giới hạn chuỗi.
- pattern: biểu thức chính quy.
- format: định dạng được quy ước.
- additionalProperties: có cho phép trường ngoài danh sách hay không.
- $ref: tham chiếu đến schema khác.
- allOf, anyOf, oneOf: kết hợp hoặc lựa chọn schema.

### 12.2. Required và nullable trong JSON Schema

Trong JSON Schema, required quy định property phải xuất hiện trong object. Việc một property có nhận null hay không được thể hiện qua type hoặc schema tương ứng.

Ví dụ:

~~~json
{
  "type": "object",
  "properties": {
    "nickname": {
      "type": ["string", "null"]
    }
  }
}
~~~

Property nickname có thể vắng mặt vì không nằm trong required; nếu xuất hiện thì có thể là string hoặc null.

### 12.3. Reference và tái sử dụng

Có thể định nghĩa một schema Customer riêng và tham chiếu từ Order:

~~~json
{
  "$defs": {
    "CustomerRef": {
      "type": "object",
      "properties": {
        "customerId": {
          "type": "string",
          "format": "uuid"
        }
      },
      "required": ["customerId"]
    }
  },
  "type": "object",
  "properties": {
    "customer": {
      "$ref": "#/$defs/CustomerRef"
    }
  }
}
~~~

Reference giúp tránh lặp schema và hỗ trợ cấu trúc lồng nhau. Cần quản lý URI, định danh và phiên bản schema được tham chiếu.

### 12.4. Format không phải lúc nào cũng là validation đầy đủ

Một validator có thể hỗ trợ format email, date-time hoặc uri ở mức kiểm tra cú pháp; mức hỗ trợ phụ thuộc implementation và cấu hình. Không nên giả định mọi validator đều thực thi mọi format giống nhau.

Nếu một format là yêu cầu bắt buộc, cần kiểm tra khả năng của validator hoặc thêm custom validation.

## 13. XML Schema và dữ liệu XML

XML Schema (XSD) mô tả cấu trúc, kiểu và ràng buộc cho tài liệu XML.

Ví dụ XML:

~~~xml
<Order>
  <Id>6d2b2a9e-40e7-4d6c-b58a-123456789abc</Id>
  <Status>PENDING</Status>
  <Total>125000.00</Total>
</Order>
~~~

XSD có thể định nghĩa element, attribute, complex type, simple type, sequence, choice, minOccurs, maxOccurs và các constraint.

### 13.1. Element và attribute

XML phân biệt element và attribute. Schema cần xác định dữ liệu nào được biểu diễn dưới dạng element, dữ liệu nào là attribute. Việc chọn ảnh hưởng đến cách đọc, namespace và tương thích.

### 13.2. Namespace

XML namespace giúp phân biệt các element có cùng tên nhưng thuộc các vocabularies khác nhau. Schema cần định nghĩa target namespace và quy tắc import/include.

### 13.3. Sequence và choice

XSD có thể yêu cầu các element xuất hiện theo thứ tự hoặc chỉ một trong các lựa chọn. Điều này khác với object JSON thường không phụ thuộc thứ tự key.

Khi ánh xạ mô hình DSL sang XML, cần quyết định thứ tự element có thuộc hợp đồng hay không.

### 13.4. Schema validation

Một XML document có thể hợp lệ về cú pháp XML nhưng không hợp lệ theo XSD. Cần phân biệt well-formedness và schema validity.

## 14. Schema trong định dạng message: Avro và Protocol Buffers

Khi trao đổi message giữa service hoặc qua event stream, schema thường được dùng để serialize dữ liệu hiệu quả và quản lý thay đổi.

### 14.1. Apache Avro

Avro mô tả schema bằng JSON và hỗ trợ serialization nhị phân. Schema thường khai báo record, field, type, union, enum, array, map và default.

Ví dụ:

~~~json
{
  "type": "record",
  "name": "OrderCreated",
  "namespace": "sales.events",
  "fields": [
    { "name": "orderId", "type": "string" },
    { "name": "total", "type": "double" },
    {
      "name": "currency",
      "type": "string",
      "default": "VND"
    }
  ]
}
~~~

Avro thường dùng schema writer và reader để diễn giải dữ liệu. Khi schema thay đổi, compatibility phụ thuộc cách reader và writer xử lý field mới, field bị bỏ và default.

Với dữ liệu tiền tệ, nên cân nhắc biểu diễn decimal có độ chính xác phù hợp thay vì dùng double nếu cần giữ giá trị chính xác.

### 14.2. Protocol Buffers

Protocol Buffers (Protobuf) dùng message và field number:

~~~proto
syntax = "proto3";

package sales.events;

message OrderCreated {
  string order_id = 1;
  string customer_id = 2;
  int64 created_at_epoch_ms = 3;
  string status = 4;
}
~~~

Field number là một phần quan trọng của wire format. Khi bỏ một field, nên reserve tên và số field đã dùng để tránh tái sử dụng gây diễn giải sai dữ liệu cũ.

### 14.3. Tại sao field number quan trọng?

Protobuf không dựa hoàn toàn vào tên field khi mã hóa trên wire. Field number giúp nhận diện dữ liệu. Nếu một số đã dùng bị gán cho field khác, consumer cũ có thể đọc nhầm dữ liệu.

Vì vậy, schema evolution của Protobuf cần quy tắc riêng: thêm field với số mới, tránh đổi type không tương thích và reserve field đã xóa.

### 14.4. Chọn định dạng trao đổi

| Định dạng | Điểm mạnh thường gặp | Điều cần cân nhắc |
| --- | --- | --- |
| JSON | Dễ đọc, phổ biến trên web | Payload văn bản, schema cần được quản lý riêng |
| XML | Hỗ trợ namespace và schema phong phú | Dài và phức tạp hơn cho nhiều ứng dụng |
| Avro | Schema-aware binary, hỗ trợ writer/reader schema | Cần quản lý schema và codec |
| Protobuf | Binary gọn, field number ổn định | Cần quản lý số field và generated code |

Không có định dạng tốt nhất cho mọi hệ thống. Cần chọn theo yêu cầu về khả năng đọc, hiệu năng, kích thước, tương thích, hệ sinh thái và vận hành.

## 15. Schema registry và quản lý schema tập trung

Trong hệ thống event-driven hoặc microservices, nhiều producer và consumer có thể cùng sử dụng một schema. **Schema registry** là dịch vụ hoặc kho quản lý schema và phiên bản của chúng.

Một registry có thể cung cấp:

- Đăng ký schema mới.
- Gán định danh và version.
- Kiểm tra compatibility.
- Lưu lịch sử schema.
- Tra cứu schema theo ID.
- Quản lý subject hoặc namespace.
- Tích hợp với producer và consumer.

### 15.1. Subject và version

Một subject có thể đại diện cho schema của một loại message, chẳng hạn sales.OrderCreated. Mỗi lần thay đổi schema, registry lưu một version mới.

Cần xác định quy tắc đặt tên subject và cách liên kết schema với domain event. Không nên chỉ dựa vào tên file vì nhiều nhóm có thể tạo tên trùng.

### 15.2. Compatibility mode

Registry thường hỗ trợ các chế độ kiểm tra như backward, forward hoặc full compatibility. Ý nghĩa cụ thể phụ thuộc công cụ và cấu hình.

- Backward: consumer dùng schema mới có thể đọc dữ liệu được ghi theo schema cũ, theo quy tắc của định dạng.
- Forward: consumer dùng schema cũ có thể đọc dữ liệu được ghi theo schema mới.
- Full: cần đáp ứng cả hai hướng.
- Transitive: kiểm tra với nhiều hoặc tất cả phiên bản trước, tùy registry.

Cần kiểm tra định nghĩa chính xác của registry đang dùng. Không nên giả định mọi công cụ có cùng cách xử lý default hoặc optional.

### 15.3. Registry không thay thế kiểm thử tích hợp

Schema registry có thể xác minh một số quy tắc compatibility, nhưng không chứng minh consumer hiểu đúng ý nghĩa nghiệp vụ mới. Thêm một enum value có thể hợp lệ ở wire format nhưng khiến consumer cũ không có nhánh xử lý.

Cần kiểm thử producer, consumer và quy trình triển khai cùng nhau.

## 16. Schema evolution và tương thích phiên bản

Schema hiếm khi bất biến. Nghiệp vụ thay đổi khiến hệ thống cần thêm field, đổi kiểu, bỏ field hoặc thay đổi constraint.

**Schema evolution** là quá trình thay đổi schema theo thời gian mà vẫn quản lý được dữ liệu và các hệ thống đang sử dụng phiên bản cũ.

### 16.1. Các dạng thay đổi

- Thêm một field.
- Bỏ một field.
- Đổi tên field.
- Đổi kiểu field.
- Thay đổi requiredness hoặc nullability.
- Thêm enum value.
- Bỏ enum value.
- Thay đổi default.
- Thay đổi nested schema.
- Thay đổi constraint hoặc reference.

Không phải mọi thay đổi đều có cùng mức rủi ro.

### 16.2. Backward compatibility

Backward compatibility thường có nghĩa phần mềm mới có thể đọc dữ liệu được tạo theo schema cũ.

Ví dụ, thêm một trường optional có default có thể tương thích nếu reader mới biết cách xử lý dữ liệu cũ không chứa trường đó.

Tuy nhiên, thay đổi requiredness hoặc đổi kiểu có thể khiến reader mới không đọc được record cũ.

### 16.3. Forward compatibility

Forward compatibility thường có nghĩa consumer cũ có thể đọc dữ liệu được tạo theo schema mới, trong phạm vi các trường và quy tắc mà nó hiểu.

Nếu consumer cũ không biết field mới, một định dạng có thể cho phép bỏ qua field đó. Nhưng nếu field mới thay đổi ý nghĩa của field cũ hoặc được consumer cũ coi là bắt buộc về nghiệp vụ, việc bỏ qua có thể tạo kết quả sai.

### 16.4. Full compatibility

Full compatibility yêu cầu cả reader mới đọc dữ liệu cũ và reader cũ đọc dữ liệu mới theo quy tắc được áp dụng. Đây là mục tiêu chặt hơn và có thể hạn chế những thay đổi schema.

### 16.5. Ví dụ thay đổi schema

Phiên bản 1:

~~~json
{
  "type": "object",
  "properties": {
    "id": { "type": "string" },
    "name": { "type": "string" }
  },
  "required": ["id", "name"]
}
~~~

Phiên bản 2 thêm phone optional:

~~~json
{
  "type": "object",
  "properties": {
    "id": { "type": "string" },
    "name": { "type": "string" },
    "phone": { "type": "string" }
  },
  "required": ["id", "name"]
}
~~~

Payload cũ vẫn có thể hợp lệ theo schema mới vì phone không bắt buộc. Nhưng nếu phiên bản 2 thêm phone vào required, dữ liệu cũ có thể không còn hợp lệ.

### 16.6. Đổi tên field

Đổi tên field có thể giống như xóa field cũ và thêm field mới đối với nhiều định dạng. Consumer cũ chỉ đọc tên cũ; consumer mới chỉ đọc tên mới có thể không tương thích.

Có thể dùng giai đoạn chuyển tiếp:

1. Thêm field mới.
2. Producer ghi cả field cũ và mới trong một thời gian.
3. Consumer đọc field mới và fallback sang field cũ.
4. Chờ các consumer được nâng cấp.
5. Ngừng ghi field cũ.
6. Bỏ field cũ trong một phiên bản sau.

Quy trình cụ thể phụ thuộc khả năng của serialization format và hệ thống.

## 17. Versioning schema

Schema cần có chiến lược định danh phiên bản để producer, consumer, database và công cụ biết đang sử dụng hợp đồng nào.

### 17.1. Version tường minh

Có thể khai báo:

~~~text
schema Order version 2 {
  id: UUID required
  total: Decimal required
  currency: String default "VND"
}
~~~

Version tường minh giúp tài liệu và migration tham chiếu một định nghĩa cụ thể. Cần quy định version tăng khi nào và có cho phép sửa nội dung của một version đã phát hành không.

### 17.2. Semantic versioning

Một số dự án dùng major/minor/patch:

- Major: thay đổi không tương thích.
- Minor: bổ sung tương thích theo chính sách.
- Patch: sửa mô tả hoặc metadata không làm thay đổi hợp đồng.

Không phải mọi schema registry hoặc định dạng đều dùng semantic versioning. Nếu chọn, cần ghi rõ tiêu chí để nhóm phát triển không diễn giải tùy ý.

### 17.3. Immutable published schema

Sau khi schema đã được công bố và có dữ liệu phụ thuộc, không nên âm thầm sửa nội dung version cũ. Thay vào đó, tạo version mới và giữ lịch sử.

Điều này giúp tái lập payload cũ, kiểm tra migration và điều tra sự cố.

### 17.4. Version trong payload hay ngoài payload?

Có thể đặt version trong payload:

~~~json
{
  "schemaVersion": 2,
  "id": "..."
}
~~~

Hoặc quản lý version ngoài payload bằng message header, schema ID hoặc endpoint API. Đưa version vào payload giúp dễ nhận biết khi lưu tệp, nhưng làm tăng dữ liệu và cần quy tắc xử lý version không biết.

## 18. Migration dữ liệu và chuyển đổi schema

Khi schema lưu trữ thay đổi, dữ liệu hiện có có thể cần chuyển đổi. **Migration** là quy trình biến đổi cấu trúc hoặc giá trị dữ liệu từ phiên bản cũ sang phiên bản mới.

### 18.1. Thay đổi additive

Thêm một cột nullable hoặc có default có thể là migration tương đối đơn giản:

~~~sql
ALTER TABLE Customer
ADD COLUMN phone VARCHAR(30);
~~~

Nhưng cần xác định default, index, backfill và cách ứng dụng cũ xử lý cột mới.

### 18.2. Backfill

Nếu trường mới cần giá trị cho dữ liệu cũ, có thể chạy backfill:

~~~sql
UPDATE Customer
SET country_code = 'VN'
WHERE country_code IS NULL;
~~~

Giá trị backfill cần dựa trên quy tắc nghiệp vụ hoặc dữ liệu đáng tin cậy. Không nên tự gán một giá trị mặc định tùy tiện nếu nó làm sai ý nghĩa lịch sử.

### 18.3. Đổi kiểu dữ liệu

Đổi kiểu có thể cần chuyển đổi dữ liệu và kiểm tra giá trị không hợp lệ:

~~~sql
ALTER TABLE Invoice
ALTER COLUMN amount TYPE NUMERIC(18, 2)
USING amount::NUMERIC(18, 2);
~~~

Cú pháp cụ thể phụ thuộc database. Trước migration cần kiểm tra dữ liệu có thể chuyển đổi, overflow, rounding và ảnh hưởng đến index hoặc constraint.

### 18.4. Expand-and-contract

Một chiến lược triển khai an toàn cho thay đổi không tương thích là expand-and-contract:

1. Expand: thêm cấu trúc mới mà code cũ vẫn hoạt động.
2. Deploy ứng dụng có thể đọc cả cấu trúc cũ và mới.
3. Backfill hoặc đồng bộ dữ liệu.
4. Chuyển producer sang ghi cấu trúc mới.
5. Xác minh consumer và dữ liệu.
6. Contract: loại bỏ cấu trúc cũ sau khi không còn sử dụng.

Cách này giảm nguy cơ phải nâng cấp tất cả service cùng một thời điểm.

### 18.5. Migration có thể đảo ngược hay không?

Một migration có thể có down migration, nhưng không phải mọi thay đổi đều đảo ngược được. Nếu đã gộp nhiều field thành một hoặc xóa dữ liệu, không thể khôi phục đầy đủ nếu không có backup hoặc lịch sử.

Cần xác định chiến lược backup, rollback và recovery trước khi triển khai migration quan trọng.

## 19. Validation và thời điểm kiểm tra schema

Schema chỉ có giá trị khi được dùng để kiểm tra dữ liệu ở các ranh giới phù hợp.

### 19.1. Validation ở đầu vào

Kiểm tra request hoặc tệp import ngay khi dữ liệu đi vào hệ thống:

- Cấu trúc object.
- Trường bắt buộc.
- Kiểu và format.
- Miền giá trị.
- Kích thước payload.
- Phiên bản schema.

Dữ liệu không hợp lệ nên bị từ chối với diagnostic rõ ràng.

### 19.2. Validation trong application

Một số quy tắc nghiệp vụ không thể biểu diễn đầy đủ trong schema tĩnh. Application cần kiểm tra:

- Quyền của người dùng.
- Trạng thái hiện tại.
- Quy tắc phụ thuộc dữ liệu khác.
- Điều kiện liên service.
- Invariant theo transaction.

### 19.3. Validation ở database

Database constraint là lớp bảo vệ cuối cùng cho dữ liệu được lưu:

- NOT NULL.
- UNIQUE.
- PRIMARY KEY.
- FOREIGN KEY.
- CHECK.
- Index và các quy tắc cụ thể của database.

Application validation giúp thông báo sớm và thân thiện. Database constraint bảo vệ tính toàn vẹn khi có nhiều ứng dụng hoặc request đồng thời.

### 19.4. Không dựa vào một lớp validation duy nhất

Một request có thể hợp lệ theo JSON Schema nhưng vi phạm foreign key trong database. Một record có thể qua database constraint nhưng vi phạm quy tắc nghiệp vụ cần kiểm tra trạng thái đơn hàng.

Các lớp validation bổ sung cho nhau và cần được phân chia trách nhiệm rõ.

## 20. Schema registry, documentation và data catalog

Ngoài schema kỹ thuật, hệ thống có thể cần metadata để người dùng hiểu dữ liệu.

### 20.1. Description

Mỗi entity và field nên có mô tả:

~~~text
entity Order {
  /// Đơn hàng do khách hàng tạo.
  id: UUID required

  /// Tổng tiền trước hoặc sau thuế theo chính sách đơn hàng.
  total: Decimal required
}
~~~

Description giúp sinh tài liệu, IDE tooltip và catalog dữ liệu. Cần tránh mô tả mơ hồ như “giá trị của đơn hàng” nếu người dùng cần biết có bao gồm thuế và vận chuyển hay không.

### 20.2. Data catalog

Data catalog có thể bổ sung:

- Chủ sở hữu dữ liệu.
- Mục đích sử dụng.
- Phân loại nhạy cảm.
- Nguồn dữ liệu.
- Chính sách lưu giữ.
- Lineage.
- Chất lượng dữ liệu.
- Hệ thống tiêu thụ.

Các metadata này không nhất thiết trở thành constraint của schema vật lý, nhưng giúp quản trị dữ liệu.

### 20.3. Schema documentation

Từ DSL, generator có thể tạo bảng tài liệu:

| Field | Type | Required | Default | Description |
| --- | --- | --- | --- | --- |
| id | UUID | Yes | — | Định danh đơn hàng |
| status | OrderStatus | No | PENDING | Trạng thái hiện tại |
| total | Decimal | Yes | — | Tổng tiền theo đơn vị tiền tệ |
| createdAt | Instant | Yes | — | Thời điểm tạo |

Tài liệu nên chỉ rõ đơn vị, timezone, nullability và ý nghĩa nghiệp vụ, không chỉ tên và kiểu.

## 21. Schema và bảo mật dữ liệu

Schema có thể chứa metadata nhạy cảm hoặc mô tả trường chứa dữ liệu cá nhân. Việc thiết kế schema cần cân nhắc bảo mật và quyền riêng tư.

### 21.1. Phân loại dữ liệu

Có thể gắn nhãn:

- Public.
- Internal.
- Confidential.
- Sensitive hoặc personal data.

Nhãn có thể được dùng để sinh tài liệu, kiểm tra policy hoặc cảnh báo khi một trường nhạy cảm xuất hiện trong API công khai.

### 21.2. Không đưa mọi trường nội bộ vào exchange schema

Một entity lưu trữ có thể có passwordHash, internalRiskScore hoặc auditMetadata. Không nên tự động xuất tất cả trường đó vào response schema.

Nên định nghĩa projection hoặc DTO riêng cho từng boundary.

### 21.3. Data minimization

Chỉ trao đổi các trường cần thiết cho mục đích cụ thể. Payload nhỏ hơn, giảm rủi ro lộ dữ liệu và giảm phụ thuộc giữa producer và consumer.

### 21.4. Validation không thay thế authorization

Schema có thể xác minh rằng role là một trong các giá trị được phép, nhưng không thể tự xác minh người gửi có quyền gán role đó. Authorization cần kiểm tra danh tính và chính sách truy cập ở runtime.

### 21.5. Schema và secret

Không lưu secret thật trong schema hoặc ví dụ. Nếu một trường tham chiếu đến secret, schema nên mô tả kiểu hoặc nguồn tham chiếu; secret được cấp qua cơ chế quản lý bí mật riêng.

## 22. Sinh schema từ mô hình DSL

Một DSL có thể dùng metamodel làm nguồn để sinh schema cho nhiều target.

Ví dụ mô hình:

~~~text
namespace sales {
  enum OrderStatus {
    PENDING
    PAID
    CANCELLED
  }

  entity Customer {
    id: UUID required
    name: String required length(1..120)
    email: String required unique
  }

  entity Order {
    id: UUID required
    customer: Customer required
    status: OrderStatus default PENDING
    total: Decimal(18, 2) required min(0)
    createdAt: Instant required
  }
}
~~~

### 22.1. Pipeline sinh schema

~~~text
DSL Source
    |
    v
Parser
    |
    v
AST
    |
    v
Name Resolution
    |
    v
Type and Constraint Validation
    |
    v
Domain Schema Model
    |
    +-------------------+
    |                   |
    v                   v
SQL Generator      JSON Schema Generator
    |                   |
    v                   v
DDL Files          API Contract Files
~~~

### 22.2. Chuẩn hóa trước khi sinh

Trước khi render schema, generator nên:

- Phân giải mọi type reference.
- Chuẩn hóa default và constraint.
- Xác định key và relation.
- Kiểm tra tên trùng.
- Xác định namespace và target profile.
- Phát hiện kiểu hoặc constraint không hỗ trợ.

Điều này giúp template không phải tự suy luận ý nghĩa.

### 22.3. Type mapping

Một TypeMapper có thể chuyển kiểu miền sang kiểu đích:

| Kiểu DSL | SQL minh họa | JSON Schema |
| --- | --- | --- |
| UUID | UUID | string, format uuid |
| String | VARCHAR(n) | string |
| Integer | INTEGER | integer |
| Decimal(18,2) | DECIMAL(18,2) | number hoặc biểu diễn decimal theo contract |
| Boolean | BOOLEAN | boolean |
| Instant | TIMESTAMP WITH TIME ZONE | string, format date-time |
| OrderStatus | VARCHAR hoặc native enum | string, enum |

Cần lưu ý JSON number thường được biểu diễn theo số học của consumer; nếu yêu cầu chính xác thập phân tuyệt đối, có thể chọn chuỗi decimal theo một contract rõ ràng thay vì number.

### 22.4. Mapping constraint

Constraint cần được phân loại:

- Có thể sinh trực tiếp thành SQL constraint.
- Có thể sinh trực tiếp thành JSON Schema keyword.
- Cần application validator.
- Không thể tự động ánh xạ.
- Cần cấu hình target cụ thể.

Generator nên báo rõ constraint nào chưa được thực thi ở target.

### 22.5. Giữ traceability

Mỗi table, column, property hoặc schema definition nên giữ liên kết đến khai báo DSL nguồn. Khi schema validation thất bại, công cụ có thể điều hướng về đúng dòng trong DSL.

## 23. Quản lý tên, namespace và reference

Schema có thể được chia thành nhiều file hoặc module. Tên và reference cần ổn định để tránh xung đột.

### 23.1. Namespace

Namespace phân nhóm schema và tạo tên đầy đủ:

~~~text
sales.Customer
sales.Order
billing.Invoice
~~~

Cùng tên Customer có thể tồn tại ở namespace khác nếu quy tắc cho phép. Generator cần chuyển namespace sang package, SQL schema hoặc URI phù hợp.

### 23.2. Reference

Reference có thể là:

- Tham chiếu nội bộ trong cùng schema.
- Tham chiếu đến file khác.
- Tham chiếu URI.
- Foreign key đến bảng khác.
- Schema ID trong registry.

Cần quy định cách resolve reference, version được tham chiếu và hành vi khi resource không tồn tại.

### 23.3. Circular reference

Hai schema có thể tham chiếu lẫn nhau. Một số định dạng hỗ trợ reference vòng, nhưng tool hoặc validator có thể có giới hạn.

Cần phân biệt vòng tham chiếu kiểu hợp lệ với chu trình dữ liệu khi serialize. Nếu object graph có vòng, serializer cần dùng ID/reference hoặc phát hiện chu trình.

### 23.4. Tên kỹ thuật và tên hiển thị

Schema nên giữ tên kỹ thuật ổn định. Nhãn hiển thị có thể được bản địa hóa riêng:

~~~text
property createdAt {
  type: Instant
  displayName:
    en: "Created at"
    vi: "Thời điểm tạo"
}
~~~

Không nên dùng tên hiển thị đã dịch làm field name trong JSON hoặc column name nếu điều đó làm thay đổi contract giữa locale.

## 24. Canonicalization, thứ tự và tính xác định

Hai schema có thể tương đương về ý nghĩa nhưng khác thứ tự key, khoảng trắng hoặc cách format. Khi lưu schema trong version control hoặc tính fingerprint, cần quy tắc canonicalization.

### 24.1. Canonical representation

Canonicalization có thể quy định:

- Thứ tự property ổn định.
- Cách sắp xếp import và reference.
- Chuẩn hóa kiểu và default.
- Encoding UTF-8.
- Newline thống nhất.
- Bỏ metadata không ảnh hưởng semantics khỏi fingerprint nếu phù hợp.

### 24.2. Hash và schema identity

Có thể tính hash từ canonical schema để nhận diện nội dung. Nhưng hash không thay thế version semantics: hai schema khác văn bản nhưng tương đương có thể có hash khác; một thay đổi mô tả có thể đổi hash dù wire format không đổi.

Cần xác định hash dùng cho cache, identity hay compatibility check.

### 24.3. Không để thứ tự map tình cờ quyết định đầu ra

Nếu generator duyệt HashMap không ổn định, schema có thể thay đổi thứ tự field giữa các lần chạy. Hãy sắp xếp hoặc dùng cấu trúc có thứ tự theo chính sách đã định.

## 25. Kiểm thử schema

Schema cần được kiểm thử ở mức cấu trúc, validation, compatibility và tích hợp.

### 25.1. Kiểm thử schema syntax

Xác minh file schema được parser hoặc validator của định dạng đích chấp nhận. Ví dụ, JSON Schema phải đúng dialect; XSD phải hợp lệ; Protobuf phải biên dịch.

### 25.2. Kiểm thử dữ liệu hợp lệ và không hợp lệ

Tạo fixture đại diện:

- Record đầy đủ.
- Trường optional bị bỏ qua.
- Trường null.
- Giá trị sai kiểu.
- Enum value không hợp lệ.
- Số ngoài miền.
- Chuỗi quá dài.
- Reference không tồn tại.
- Collection vượt cardinality.

Kiểm tra validator trả kết quả như contract quy định.

### 25.3. Kiểm thử schema evolution

So sánh schema mới với các phiên bản đã phát hành. Kiểm tra backward/forward compatibility theo policy và định dạng cụ thể.

Không chỉ kiểm tra công cụ báo tương thích; cần chạy consumer thực tế với payload cũ và mới nếu thay đổi ảnh hưởng logic.

### 25.4. Kiểm thử migration

Dùng bản sao dữ liệu đại diện để chạy migration. Kiểm tra:

- Số lượng record.
- Giá trị được chuyển đổi.
- Constraint sau migration.
- Index và foreign key.
- Thời gian thực thi.
- Khả năng rollback hoặc phục hồi.

### 25.5. Kiểm thử generator

Cùng mô hình và cấu hình phải tạo schema ổn định. Có thể dùng golden files, compile/validate target và so sánh canonical representation.

### 25.6. Contract test giữa producer và consumer

Producer tạo payload theo schema mới; consumer đọc payload đó. Kiểm tra cả trường hợp producer và consumer được triển khai ở các version khác nhau.

Contract test phát hiện vấn đề mà kiểm thử schema riêng lẻ có thể bỏ sót, đặc biệt khi semantics nghiệp vụ thay đổi.

## 26. Những lỗi thiết kế thường gặp

**Đồng nhất schema với dữ liệu.** Schema là hợp đồng mô tả; record là dữ liệu cụ thể. Tách hai khái niệm giúp kiểm tra và quản lý phiên bản.

**Chỉ mô tả kiểu mà bỏ qua semantics.** Decimal không nói rõ đơn vị tiền tệ, Instant không nói rõ timezone contract, String không nói rõ ý nghĩa. Cần metadata nghiệp vụ và constraint phù hợp.

**Nhầm optional với nullable.** Trường vắng mặt và trường có null có thể mang ý nghĩa khác nhau. Phải xác định rõ ở từng target.

**Cho rằng default được áp dụng ở mọi tầng.** JSON validator, deserializer, application và database có thể xử lý default khác nhau. Cần chỉ rõ nơi áp dụng.

**Dùng một schema cho mọi boundary.** Storage model và API contract thường có nhu cầu khác nhau. Dùng projection riêng để tránh lộ trường nội bộ và tạo phụ thuộc không cần thiết.

**Bỏ qua giới hạn của target.** Một constraint không có biểu diễn trực tiếp ở JSON Schema hoặc SQL có thể bị mất nếu generator không báo. Cần phân loại và xử lý rõ.

**Đổi tên field mà không có kế hoạch chuyển tiếp.** Producer và consumer có thể chạy các phiên bản khác nhau. Cần alias, dual-read/dual-write hoặc một chiến lược migration phù hợp.

**Tái sử dụng số field Protobuf đã xóa.** Dữ liệu cũ có thể bị diễn giải sai. Hãy reserve số và tên đã dùng.

**Sửa schema đã phát hành tại chỗ.** Điều này làm mất khả năng tái lập và gây khó khăn khi xử lý dữ liệu lịch sử. Hãy tạo version mới.

**Chỉ kiểm tra schema mà không kiểm tra dữ liệu.** Schema hợp lệ không bảo đảm payload thực tế hoặc migration không có lỗi. Cần fixture và contract test.

**Không lưu lineage.** Khi schema sinh ra sai, người dùng khó tìm về khai báo DSL. Hãy giữ traceability.

## 27. Quy trình thiết kế schema dữ liệu cho DSL

Khi bổ sung một schema hoặc generator cho DSL, có thể thực hiện theo các bước:

### Bước 1: Xác định mục đích sử dụng

Schema phục vụ lưu trữ, API, event, file cấu hình hay nhiều mục tiêu? Xác định producer, consumer và vòng đời dữ liệu.

### Bước 2: Xác định khái niệm miền

Liệt kê entity, value object, enum, relation và invariant. Định nghĩa ý nghĩa nghiệp vụ của từng trường.

### Bước 3: Chọn kiểu dữ liệu

Xác định miền giá trị, precision, scale, timezone, nullability, collection và serialization representation.

### Bước 4: Định nghĩa khóa và quan hệ

Chọn primary key, natural key, foreign key, cardinality và hành vi khi xóa hoặc cập nhật.

### Bước 5: Định nghĩa constraint

Ghi rõ required, unique, range, pattern, reference, cross-field rule và nơi thực thi từng constraint.

### Bước 6: Chọn định dạng schema đích

Chọn SQL DDL, JSON Schema, XSD, Avro, Protobuf hoặc định dạng khác theo yêu cầu.

### Bước 7: Xác định version và compatibility policy

Quy định thay đổi nào được phép, default được xử lý thế nào và cách migration dữ liệu.

### Bước 8: Xây generator và validator

Tách domain model, target mapping, rendering và validation. Báo rõ những đặc điểm không thể ánh xạ.

### Bước 9: Kiểm thử dữ liệu và consumer

Dùng fixture hợp lệ/không hợp lệ, compatibility test, migration test và contract test.

### Bước 10: Công bố và quản trị

Lưu version bất biến, tài liệu hóa schema, ghi owner, nguồn gốc và quy trình thay đổi.

## 28. Ví dụ tổng hợp: schema đơn hàng cho database và API

Giả sử DSL:

~~~text
namespace sales {
  enum OrderStatus {
    PENDING
    CONFIRMED
    PAID
    CANCELLED
  }

  entity Customer {
    id: UUID required
    name: String required length(1..120)
    email: String required unique
  }

  entity Order {
    id: UUID required
    customerId: UUID required references Customer.id
    status: OrderStatus default PENDING
    total: Decimal(18, 2) required min(0)
    createdAt: Instant required
    note: String optional length(0..500)
  }
}
~~~

### 28.1. Logical schema

Ở mức logic:

- Customer có khóa chính id.
- email là duy nhất.
- Order có khóa chính id.
- customerId tham chiếu Customer.id.
- status thuộc tập OrderStatus.
- total là số thập phân không âm với precision và scale xác định.
- note có thể vắng mặt và bị giới hạn độ dài.

### 28.2. SQL schema minh họa

~~~sql
CREATE TABLE Customer (
    id UUID PRIMARY KEY,
    name VARCHAR(120) NOT NULL,
    email VARCHAR(320) NOT NULL UNIQUE
);

CREATE TABLE Orders (
    id UUID PRIMARY KEY,
    customer_id UUID NOT NULL,
    status VARCHAR(16) NOT NULL DEFAULT 'PENDING',
    total DECIMAL(18, 2) NOT NULL CHECK (total >= 0),
    created_at TIMESTAMP WITH TIME ZONE NOT NULL,
    note VARCHAR(500),
    CONSTRAINT fk_orders_customer
        FOREIGN KEY (customer_id) REFERENCES Customer(id),
    CONSTRAINT chk_orders_status
        CHECK (status IN ('PENDING', 'CONFIRMED', 'PAID', 'CANCELLED'))
);
~~~

Đây là SQL minh họa; cú pháp UUID và timestamp khác nhau theo database. Generator thực tế cần target profile theo dialect.

### 28.3. JSON Schema cho API request

~~~json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "title": "CreateOrderRequest",
  "type": "object",
  "properties": {
    "customerId": {
      "type": "string",
      "format": "uuid"
    },
    "status": {
      "type": "string",
      "enum": ["PENDING", "CONFIRMED", "PAID", "CANCELLED"],
      "default": "PENDING"
    },
    "total": {
      "type": "number",
      "minimum": 0
    },
    "note": {
      "type": "string",
      "maxLength": 500
    }
  },
  "required": ["customerId", "total"],
  "additionalProperties": false
}
~~~

API request không cần nhận id hoặc createdAt nếu server tự sinh chúng. Điều đó cho thấy API request schema là projection của domain model, không phải bản sao toàn bộ storage schema.

### 28.4. JSON Schema cho response

Response có thể chứa thêm id, createdAt và thông tin khách hàng:

~~~json
{
  "type": "object",
  "properties": {
    "id": { "type": "string", "format": "uuid" },
    "customerId": { "type": "string", "format": "uuid" },
    "status": {
      "type": "string",
      "enum": ["PENDING", "CONFIRMED", "PAID", "CANCELLED"]
    },
    "total": { "type": "number", "minimum": 0 },
    "createdAt": { "type": "string", "format": "date-time" }
  },
  "required": ["id", "customerId", "status", "total", "createdAt"],
  "additionalProperties": false
}
~~~

### 28.5. Thay đổi schema trong phiên bản sau

Giả sử phiên bản 2 bổ sung trường sourceChannel:

~~~text
property sourceChannel: String default "WEB"
~~~

Nếu field optional hoặc default được xử lý đúng, payload cũ có thể tiếp tục được đọc. Tuy nhiên, cần kiểm tra consumer cũ có bỏ qua field lạ hay không. Với database, cần migration thêm cột và quyết định backfill. Với event schema, cần kiểm tra compatibility theo định dạng và registry.

### 28.6. Kiểm tra trước khi phát hành

Trước khi công bố schema mới, nhóm có thể:

- Validate schema syntax.
- Validate payload mẫu.
- So sánh compatibility với phiên bản cũ.
- Chạy migration trên bản sao dữ liệu.
- Kiểm thử producer và consumer.
- Kiểm tra mapping giữ nguyên Decimal, timezone và enum.
- Xem diff các file schema được sinh.
- Xác nhận API không xuất trường nội bộ.

## 29. Kết luận

Schema dữ liệu là hợp đồng mô tả cấu trúc, kiểu và quy tắc của dữ liệu. Trong DSL, schema kết nối mô hình miền với database, API, tệp và hệ thống message. Nó giúp producer và consumer hiểu cùng một cấu trúc, hỗ trợ validation, sinh mã, tài liệu hóa và quản lý thay đổi.

Khi thiết kế schema, cần xác định rõ mục đích sử dụng, lớp conceptual/logical/physical, kiểu dữ liệu, nullability, default, constraint, khóa, quan hệ và serialization format. Storage schema và exchange schema có thể cần các projection riêng. Những thay đổi theo thời gian cần versioning, compatibility policy và migration có kiểm soát.

Một schema tốt không chỉ làm dữ liệu đúng hình dạng mà còn giữ được ý nghĩa nghiệp vụ qua các ranh giới hệ thống và các phiên bản. Khi DSL dùng một mô hình nguồn có cấu trúc, generator có quy tắc rõ và kiểm thử được dữ liệu thực tế, schema trở thành nền tảng đáng tin cậy cho lưu trữ và trao đổi.

