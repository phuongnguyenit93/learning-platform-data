# Ánh xạ mô hình

## 1. Ánh xạ mô hình trong DSL API và dữ liệu

Một ngôn ngữ miền chuyên biệt (Domain-Specific Language — DSL) thường có mô hình riêng để biểu diễn khái niệm nghiệp vụ, cấu trúc dữ liệu, quy tắc và quan hệ giữa các thành phần. Khi DSL giao tiếp với API, database, message broker hoặc một hệ thống khác, mô hình nội bộ cần được chuyển thành một biểu diễn mà hệ thống đích hiểu được. Chiều ngược lại cũng cần thiết khi dữ liệu từ API hoặc storage được đưa vào DSL.

**Ánh xạ mô hình (model mapping)** là quá trình xác định cách các thành phần trong một mô hình nguồn tương ứng với thành phần trong mô hình đích, cùng những quy tắc chuyển đổi cấu trúc, kiểu dữ liệu, giá trị, quan hệ và ngữ nghĩa.

Ví dụ DSL mô tả đơn hàng:

~~~text
order {
    id = "ORD-1042"
    customer {
        id = "CUS-81"
        display_name = "An Nguyen"
    }
    total = 1250000 VND
    status = PAID
}
~~~

API có thể yêu cầu JSON theo cấu trúc khác:

~~~json
{
  "orderId": "ORD-1042",
  "customerId": "CUS-81",
  "customerName": "An Nguyen",
  "amount": 1250000,
  "currency": "VND",
  "paymentStatus": "paid"
}
~~~

Ánh xạ phải biết rằng customer.id trở thành customerId, customer.display_name trở thành customerName, total được tách thành amount và currency, còn enum PAID được chuyển thành chuỗi paid. Đây không đơn thuần là đổi tên field; nó là một hợp đồng giữa hai mô hình.

Trong bối cảnh DSL API và dữ liệu, ánh xạ mô hình giúp:

- Tách mô hình miền khỏi định dạng API hoặc database cụ thể.
- Chuyển đổi dữ liệu giữa DSL và hệ thống bên ngoài.
- Giữ quy tắc chuyển đổi nhất quán ở nhiều endpoint.
- Kiểm tra dữ liệu trước khi gửi hoặc sau khi nhận.
- Hỗ trợ schema evolution và versioning.
- Giải thích nguồn gốc của giá trị khi debug.
- Giảm lỗi do chuyển đổi kiểu, đơn vị hoặc cấu trúc không rõ ràng.

## 2. Mô hình nguồn, mô hình đích và metamodel

Trước khi viết mapping, cần xác định rõ những mô hình đang tham gia.

### 2.1. Source model

Source model là mô hình mà dữ liệu bắt đầu. Trong DSL, nó có thể là:

- AST hoặc typed AST của chương trình.
- Domain model được tạo sau semantic analysis.
- Object model trong runtime.
- Model được đọc từ một API khác.
- Schema hoặc metadata được nạp từ repository.

Không phải mọi AST node đều là dữ liệu miền. AST có thể chứa dấu ngoặc, token và vị trí nguồn chỉ phục vụ cú pháp. Model mapping nghiệp vụ thường nên làm việc với typed domain model sau khi parser và semantic analyzer đã xác nhận cấu trúc.

### 2.2. Target model

Target model là cấu trúc cần tạo ra, ví dụ:

- REST request/response DTO.
- GraphQL input hoặc output type.
- JSON document.
- XML document.
- Database row hoặc document.
- Message event.
- Model của một framework khác.
- Cấu trúc dữ liệu của runtime hoặc SDK.

### 2.3. Metamodel

Metamodel mô tả cấu trúc và quy tắc của một loại model. Ví dụ metamodel có thể định nghĩa Order gồm id, customer, items, total và status; mỗi field có type, cardinality và constraint.

Nếu DSL cho phép người dùng định nghĩa model riêng, metamodel là cơ sở để compiler hiểu field, type, relation và annotation trước khi sinh mapping.

### 2.4. Schema và instance

Schema mô tả hình dạng và ràng buộc dữ liệu. Instance là một bộ dữ liệu cụ thể tuân theo schema.

Ví dụ schema quy định amount là Decimal, currency là enum và customerId là string. Một instance chứa amount 1250.00, currency USD và customerId C-19.

Mapping có thể hoạt động ở cấp schema (xác định field nào tương ứng) hoặc cấp instance (chuyển giá trị cụ thể). Nhiều hệ thống cần cả hai: compile-time kiểm tra mapping theo schema, runtime áp dụng mapping lên từng record.

### 2.5. Mapping không phải parsing

Parsing biến văn bản thành cấu trúc cú pháp. Mapping chuyển một cấu trúc đã biết sang cấu trúc khác. Parser có thể nhận diện field total; mapper quyết định total trở thành amount và currency hay được chuyển thành một field khác.

### 2.6. Mapping không phải validation

Validation xác định dữ liệu có hợp lệ theo schema hoặc quy tắc miền hay không. Mapping có thể gọi validation trước hoặc sau chuyển đổi, nhưng hai trách nhiệm này nên được phân biệt để lỗi có thể được giải thích chính xác.

## 3. Các kiểu ánh xạ

Ánh xạ mô hình có thể được phân loại theo hướng và mục đích.

### 3.1. Model-to-model mapping

Chuyển một object model sang object model khác. Ví dụ DomainOrder sang ApiOrderRequest.

### 3.2. Model-to-document mapping

Chuyển model sang JSON, XML, YAML, Avro hoặc định dạng document khác.

### 3.3. Document-to-model mapping

Đọc document và tạo object model có kiểu. Quá trình này cần xử lý field thiếu, field thừa, type mismatch và schema version.

### 3.4. Model-to-relational mapping

Chuyển object hoặc quan hệ miền sang bảng, row, column, khóa ngoại và join table.

### 3.5. Model-to-event mapping

Chuyển thay đổi miền thành event có schema riêng, thường cần xác định event identity, timestamp, version và payload.

### 3.6. Mapping một chiều và hai chiều

- One-way mapping: chỉ chuyển source sang target.
- Reverse mapping: chuyển target trở lại source bằng quy tắc riêng.
- Bidirectional mapping: hai mô hình được đồng bộ theo một tập quy tắc nhất quán.

Hai chiều không có nghĩa chỉ cần đảo ngược từng phép gán. Nếu phép chuyển đổi làm mất thông tin, chiều ngược không thể khôi phục dữ liệu ban đầu.

### 3.7. Static và dynamic mapping

Static mapping được xác định khi compile hoặc build. Dynamic mapping được lựa chọn hoặc diễn giải lúc runtime dựa trên metadata, tenant, version hoặc loại dữ liệu. Dynamic mapping linh hoạt hơn nhưng cần kiểm soát type safety và hiệu năng.

## 4. Xác định correspondence giữa các field

Correspondence là quan hệ cho biết field hoặc thành phần nào ở nguồn tương ứng với thành phần nào ở đích.

### 4.1. Mapping trực tiếp

Hai field có cùng ý nghĩa và kiểu tương thích:

~~~text
source.order_id -> target.orderId
source.created_at -> target.createdAt
~~~

### 4.2. Mapping đổi tên

Tên field khác nhau nhưng ý nghĩa giống nhau:

~~~text
source.display_name -> target.fullName
~~~

Nên khai báo rõ correspondence thay vì dựa hoàn toàn vào quy tắc tự động đổi snake_case thành camelCase. Quy tắc tên chỉ phù hợp khi hai schema có convention tương thích.

### 4.3. Mapping lồng nhau

Source có object lồng nhau nhưng target có thể flatten:

~~~text
source.customer.id   -> target.customerId
source.customer.name -> target.customerName
~~~

Chiều ngược cần tạo lại object customer và xác định cách xử lý nếu chỉ một field có mặt.

### 4.4. Một nguồn thành nhiều đích

Một field có thể được tách:

~~~text
source.full_name -> target.firstName
source.full_name -> target.lastName
~~~

Phép tách cần một quy tắc miền đáng tin cậy. Chia theo dấu cách có thể sai với tên nhiều thành phần, tên không có khoảng trắng hoặc quy ước văn hóa khác nhau.

### 4.5. Nhiều nguồn thành một đích

Nhiều field có thể kết hợp:

~~~text
source.country_code + source.phone_number -> target.phone
~~~

Mapping cần xác định format, chuẩn hóa và cách xử lý khi một phần bị thiếu.

### 4.6. Derived field

Target có thể chứa field được tính từ nhiều field nguồn, ví dụ lineTotal = quantity × unitPrice. Cần xác định đây là giá trị dẫn xuất hay dữ liệu được lưu độc lập.

### 4.7. Constant và default

Target có thể cần một giá trị cố định hoặc default khi source không cung cấp. Cần phân biệt:

- Constant: giá trị luôn được gán theo hợp đồng mapping.
- Default: chỉ dùng khi source không có giá trị.
- Fallback: giá trị thay thế khi một phép lấy dữ liệu thất bại hoặc không đủ điều kiện.

Không nên dùng default để che giấu lỗi dữ liệu bắt buộc.

### 4.8. Ignored field

Một field nguồn có thể không được ánh xạ nếu target không cần. Việc bỏ qua nên được khai báo hoặc giải thích, nhất là khi field chứa thông tin nghiệp vụ quan trọng.

## 5. Type mapping

Hai mô hình có thể dùng kiểu dữ liệu khác nhau dù biểu diễn cùng khái niệm.

### 5.1. Primitive types

Các kiểu thường gặp:

- Boolean.
- Integer và các kiểu số nguyên có độ rộng khác nhau.
- Decimal.
- Floating point.
- String.
- Binary hoặc byte array.
- Date, Time và DateTime.
- UUID hoặc identifier.

Mapping phải xem xét miền giá trị, độ chính xác và cách serialize.

### 5.2. Numeric conversion

Chuyển Long sang Integer có thể gây overflow. Chuyển Decimal sang Integer có thể cần rounding hoặc reject phần thập phân. Chuyển số nguyên lớn sang floating point có thể mất độ chính xác.

Quy tắc cần ghi rõ:

- Exact conversion hay narrowing conversion.
- Rounding mode.
- Overflow behavior.
- Precision và scale.
- Có cho phép NaN hoặc Infinity không.

### 5.3. String conversion

Chuyển mọi giá trị thành String có thể thuận tiện cho logging nhưng làm mất type information. Không nên biến số, ngày hoặc enum thành string tùy tiện nếu target có kiểu rõ.

### 5.4. Enum mapping

Tên enum ở hai mô hình có thể khác nhau:

~~~text
Domain: PAID
API:    "paid"
DB:     2
~~~

Nên dùng bảng mapping tường minh. Không nên dựa vào ordinal của enum vì thứ tự khai báo có thể thay đổi.

### 5.5. Date và time

Mapping ngày giờ cần xác định:

- LocalDate hay Instant.
- Time zone.
- Offset.
- Độ chính xác đến giây, mili giây hoặc nano giây.
- Format serialization.
- Quy tắc daylight saving time.

Một local date-time không chứa timezone không thể tự động được hiểu là một thời điểm toàn cầu nếu thiếu quy ước.

### 5.6. Binary và encoded data

Byte array có thể được biểu diễn bằng Base64, hex hoặc binary field. Cần thống nhất encoding và giới hạn kích thước.

### 5.7. Domain types

Các kiểu như Money, EmailAddress, PostalCode hoặc CustomerId nên giữ ý nghĩa miền thay vì bị ép thành primitive quá sớm. Mapper có thể chuyển sang primitive ở ranh giới API nhưng nên khôi phục domain type khi dữ liệu quay vào miền.

## 6. Null, missing, empty và default

Một trong những nguồn lỗi phổ biến là coi mọi trường hợp không có giá trị là giống nhau.

### 6.1. Null

Null thường biểu thị field có mặt nhưng không có giá trị, tùy schema và semantics.

### 6.2. Missing

Missing nghĩa là field không xuất hiện trong payload. Với API update, missing có thể mang nghĩa giữ nguyên giá trị hiện tại.

### 6.3. Empty

Empty string, empty list hoặc empty object là giá trị có mặt nhưng không chứa phần tử. Nó không nhất thiết tương đương null.

### 6.4. Default

Default được áp dụng theo quy tắc khi field thiếu hoặc null. Phải xác định trường hợp nào kích hoạt default.

### 6.5. Presence model

Có thể mô hình hóa ba trạng thái:

~~~text
FieldValue<T> =
    Missing
  | PresentNull
  | Present(T)
~~~

Với API PATCH, mô hình này giúp phân biệt không cập nhật field, xóa giá trị và gán giá trị mới.

### 6.6. Nullability mismatch

Nếu source cho phép null nhưng target yêu cầu non-null, mapper cần:

- Reject với diagnostic.
- Dùng default đã được nghiệp vụ chấp thuận.
- Bỏ qua field nếu target cho phép.
- Chuyển sang trạng thái cần xử lý.

Không nên tự động tạo chuỗi rỗng hoặc số 0 nếu chúng có ý nghĩa nghiệp vụ khác null.

## 7. Collection và cardinality

Collection có thể khác nhau về kiểu, thứ tự và số lượng phần tử.

### 7.1. List-to-list

Ánh xạ từng phần tử theo cùng một mapper:

~~~text
target.items = map(source.items, mapOrderItem)
~~~

### 7.2. Set-to-list

Set không bảo đảm thứ tự theo mọi implementation. Nếu target là list và thứ tự có ý nghĩa, cần quy định sort key hoặc thứ tự ổn định.

### 7.3. List-to-set

Chuyển list sang set có thể loại bỏ phần tử trùng. Cần xác định equality dựa trên identity hay toàn bộ field.

### 7.4. Map mapping

Map có thể đổi key type hoặc value type. Cần xử lý key collision sau chuyển đổi.

### 7.5. Cardinality

Một quan hệ có thể là:

- One-to-one.
- One-to-many.
- Many-to-one.
- Many-to-many.

Mapping phải bảo toàn cardinality theo hợp đồng hoặc báo lỗi nếu target không thể biểu diễn quan hệ nguồn.

### 7.6. Flattening collection

Một object chứa list có thể được chuyển thành nhiều record đích. Khi đó cần giữ khóa liên kết để có thể nhóm các record lại.

### 7.7. Empty collection

Empty list có thể khác null hoặc field missing. API và database có thể áp dụng semantics khác nhau; mapping phải quy định rõ.

## 8. Object graph, identity và reference

Domain model có thể chứa quan hệ giữa nhiều object, không chỉ cây lồng nhau.

### 8.1. Object identity

Hai object có cùng field value chưa chắc là cùng một thực thể. Mapping cần phân biệt identity (ví dụ customer ID) với equality theo nội dung.

### 8.2. Shared reference

Hai object nguồn có thể cùng trỏ đến một customer instance. Nếu mapper sao chép customer thành hai object đích độc lập, identity hoặc consistency có thể bị mất.

### 8.3. Cyclic reference

Object graph có thể có chu trình:

~~~text
Department.manager -> Employee
Employee.department -> Department
~~~

Mapper đệ quy đơn giản có thể lặp vô hạn. Cần identity map, reference ID hoặc giới hạn chiều sâu.

### 8.4. Reference mapping

Thay vì nhúng toàn bộ object, target có thể chỉ giữ ID:

~~~json
{
  "orderId": "O-1",
  "customerId": "C-7"
}
~~~

Điều này giảm payload và tránh chu trình nhưng cần hệ thống đích resolve reference khi cần.

### 8.5. Embedded object

Một target có thể nhúng snapshot customer tại thời điểm tạo order. Đây là semantics khác với reference đến customer hiện tại. Mapping cần xác định dữ liệu là snapshot hay live relation.

### 8.6. Identity map

Trong một lần mapping, identity map lưu quan hệ source object và target object đã tạo. Khi gặp lại cùng source identity, mapper dùng target đã tồn tại thay vì tạo bản sao mới.

## 9. Inheritance và polymorphism

Mô hình hướng đối tượng hoặc schema union có thể có nhiều subtype.

### 9.1. Base type

Một field có kiểu Payment có thể chứa CardPayment, BankTransfer hoặc WalletPayment.

### 9.2. Discriminator

API có thể dùng field type để xác định subtype:

~~~json
{
  "type": "card",
  "lastFour": "4242",
  "brand": "Example"
}
~~~

Mapper đọc discriminator rồi chọn subtype tương ứng.

### 9.3. Unknown subtype

Nếu API gửi type mới mà client cũ chưa biết, cần quy định reject, giữ raw payload, dùng Unknown variant hoặc bỏ qua phần không hiểu. Lựa chọn phụ thuộc yêu cầu forward compatibility.

### 9.4. Flattened inheritance

Target có thể biểu diễn subtype bằng một object phẳng với discriminator. Mapping cần bảo đảm field chỉ dành cho một subtype không bị áp dụng nhầm.

### 9.5. Sealed union

DSL có thể mô tả một tập variant đóng để compiler kiểm tra exhaustiveness. Khi schema bên ngoài thêm variant, mapping có thể cần cập nhật.

## 10. Mapping giữa domain model và API DTO

API DTO (Data Transfer Object) là cấu trúc được thiết kế để truyền dữ liệu qua ranh giới API. DTO không nhất thiết giống domain model.

### 10.1. Vì sao cần DTO riêng

Domain model có thể chứa:

- Business behavior.
- Internal identifier.
- Audit metadata.
- Lazy relation.
- Sensitive field.
- Invariant nội bộ.

API chỉ nên công khai các field cần thiết theo contract. Dùng DTO riêng giúp tránh vô tình expose nội bộ.

### 10.2. Request mapping

Khi nhận API request, mapper chuyển DTO thành command hoặc domain input. Validation của API format và validation nghiệp vụ có thể diễn ra ở các lớp riêng.

### 10.3. Response mapping

Khi trả kết quả, mapper chuyển domain state thành response DTO. Có thể cần làm phẳng relation, đổi enum, định dạng ngày và loại bỏ field nội bộ.

### 10.4. API version

API v1 và v2 có thể khác tên field hoặc cấu trúc. Không nên buộc domain model thay đổi chỉ vì một phiên bản API đổi contract.

### 10.5. Partial response

API có thể trả field tùy theo quyền, query parameter hoặc projection. Mapper cần biết field nào không được trả và field nào thực sự không có giá trị.

### 10.6. PATCH semantics

Request PATCH thường cần biểu diễn missing, null và present value khác nhau. DTO thông thường với field nullable có thể không đủ để giữ ba trạng thái.

## 11. Mapping giữa domain model và database

Database schema có thể khác domain model về cấu trúc và cách biểu diễn quan hệ.

### 11.1. Object-relational mapping

ORM ánh xạ object và quan hệ sang table, row, column, primary key và foreign key. Model mapping có thể dùng ORM hoặc một mapper riêng.

### 11.2. Aggregate boundary

Domain aggregate xác định ranh giới consistency. Không nên để mapper vô tình tải hoặc cập nhật toàn bộ object graph vượt aggregate chỉ vì relation có thể truy cập.

### 11.3. Embedded value

Money hoặc Address có thể được lưu trong cùng table bằng nhiều column, hoặc trong table riêng. Mapping cần phản ánh semantics của value object.

### 11.4. Join table

Many-to-many relation có thể cần join table. Cần xác định khóa, unique constraint và cách xử lý duplicate.

### 11.5. Database-generated values

ID, timestamp hoặc version có thể được database tạo. Mapper khi ghi dữ liệu cần phân biệt field do ứng dụng cung cấp và field do database sinh sau insert.

### 11.6. Lazy loading

Mapping một object có lazy relation có thể kích hoạt nhiều query không mong muốn. Cần kiểm soát fetch plan và tránh N+1 query.

### 11.7. Denormalized model

Document store hoặc read model có thể lưu dữ liệu lặp để tối ưu query. Mapping cần xác định nguồn sự thật và cách đồng bộ khi field nguồn thay đổi.

## 12. Mapping sang JSON, XML và định dạng document

Serialization là bước chuyển object thành định dạng trao đổi. Nó thường dùng model mapping nhưng có thêm quy tắc biểu diễn.

### 12.1. JSON field naming

Chọn convention như camelCase, snake_case hoặc tên theo API contract. Không nên để convention serializer quyết định contract công khai mà không có kiểm soát.

### 12.2. Number representation

JSON number không giữ type Decimal riêng. Nếu độ chính xác tiền tệ quan trọng, cần thống nhất cách parse và serialize; có thể dùng decimal string theo contract hoặc integer minor units.

### 12.3. Date serialization

Chọn định dạng ngày giờ chuẩn, timezone và độ chính xác. Tránh dùng format phụ thuộc locale của máy.

### 12.4. XML namespace

XML mapping cần xử lý namespace, element, attribute, ordering nếu schema yêu cầu và quy tắc xử lý unknown element.

### 12.5. Unknown fields

Khi đọc document có field mới, client có thể reject, ignore hoặc giữ lại extension data. Quyết định này ảnh hưởng forward compatibility.

### 12.6. Canonical representation

Canonical serialization tạo biểu diễn ổn định cho cùng một model, hữu ích cho hashing, signature, caching và diff. Cần quy định thứ tự field, number format, Unicode normalization và cách biểu diễn null.

## 13. Mapping giữa API và event

API request thường biểu diễn ý định của caller; event thường biểu diễn sự kiện đã xảy ra. Hai loại payload không nên được xem là tương đương.

### 13.1. Command và event

Command có thể là CreateOrderRequest. Event có thể là OrderCreated. Event thường có event ID, occurredAt, aggregate ID và schema version.

### 13.2. Mapping command

Command mapping chuyển DTO thành command có kiểu và kiểm tra quyền, dữ liệu cần thiết.

### 13.3. Mapping event

Event mapping cần xác định dữ liệu nào được công bố, tránh gửi internal field hoặc thông tin nhạy cảm.

### 13.4. Event evolution

Consumer có thể nhận event cũ hoặc mới trong cùng một giai đoạn rollout. Mapper cần xử lý schema version và default có chủ đích.

### 13.5. Snapshot và delta

Event có thể chứa toàn bộ snapshot hoặc chỉ field thay đổi. Mapping delta cần biết cách áp dụng vào state hiện tại và xử lý event lặp hoặc sai thứ tự.

## 14. Mapping declarative và imperative

Có hai cách phổ biến để định nghĩa mapping.

### 14.1. Declarative mapping

Người viết mô tả correspondence và transformation bằng cấu hình:

~~~text
mapping "OrderToApi" {
    source = DomainOrder
    target = ApiOrder

    field orderId <- id
    field customerId <- customer.id
    field customerName <- customer.displayName
    field amount <- total.value
    field currency <- total.currency
    field paymentStatus <- status using enum("PAID" -> "paid")
}
~~~

Declarative mapping dễ đọc, có thể phân tích tĩnh, sinh code và hiển thị dependency. Tuy nhiên, expression phức tạp có thể khiến DSL mapping trở thành một ngôn ngữ lập trình thứ hai.

### 14.2. Imperative mapping

Người phát triển viết code chuyển đổi trực tiếp:

~~~java
ApiOrder toApi(DomainOrder source) {
    ApiOrder target = new ApiOrder();
    target.setOrderId(source.id());
    target.setCustomerId(source.customer().id());
    target.setAmount(source.total().amount());
    target.setCurrency(source.total().currency().code());
    return target;
}
~~~

Imperative mapping linh hoạt, dễ dùng logic thông thường nhưng có thể lặp lại và khó phân tích tổng thể nếu thiếu quy ước.

### 14.3. Hybrid mapping

Có thể khai báo field correspondence bằng DSL và gọi custom converter cho trường hợp đặc biệt. Cần giới hạn custom code để compiler vẫn có thể kiểm tra phần lớn mapping.

### 14.4. Mapping generation

Từ mapping declarative, compiler có thể sinh Java code, serializer, validation hoặc schema adapter. Generated code cần có source mapping và quy trình regenerate an toàn.

## 15. Mapping expression và transformation

Một field có thể cần xử lý trước khi gán sang target.

### 15.1. Rename

Chỉ đổi tên field mà không đổi giá trị.

### 15.2. Convert

Chuyển kiểu, ví dụ Integer sang Decimal hoặc enum sang string.

### 15.3. Normalize

Chuẩn hóa dữ liệu, ví dụ trim whitespace, chuẩn hóa mã quốc gia hoặc canonicalize identifier.

### 15.4. Derive

Tính giá trị mới từ các field nguồn.

### 15.5. Filter

Chỉ đưa phần tử vào target nếu thỏa điều kiện. Filter có thể làm mất dữ liệu nên cần được thể hiện rõ.

### 15.6. Aggregate

Gộp nhiều phần tử thành tổng, số lượng hoặc nhóm. Cần xác định quy tắc khi collection rỗng.

### 15.7. Lookup

Tra cứu bảng quy đổi hoặc metadata ngoài. Lookup làm mapping phụ thuộc vào dữ liệu khác, do đó cần version, cache và xử lý khi không tìm thấy.

### 15.8. Context-dependent mapping

Giá trị đích có thể phụ thuộc tenant, locale, API version hoặc user role. Context phải được truyền tường minh thay vì đọc từ global state khó kiểm soát.

### 15.9. Pure transformation

Nếu có thể, transformation nên thuần: cùng input và context tạo cùng output, không gọi dịch vụ ngoài hoặc thay đổi state. Pure mapping dễ kiểm thử, cache và tái lập hơn.

## 16. Mapping có điều kiện

Một số field chỉ được ánh xạ khi điều kiện nhất định thỏa mãn.

### 16.1. Conditional field

~~~text
field discountCode <- promotion.code
    when promotion.active == true
~~~

### 16.2. Conditional target type

Một loại domain object có thể ánh xạ sang target variant khác nhau dựa trên discriminator.

### 16.3. Context condition

Một field có thể chỉ được trả trong response dành cho một role hoặc API scope. Đây là điểm cần phối hợp với authorization; không nên coi việc ẩn field ở mapper là cơ chế phân quyền duy nhất.

### 16.4. Precedence

Nếu nhiều rule cùng gán một field, DSL cần quy định precedence hoặc báo conflict. Không nên để kết quả phụ thuộc thứ tự iteration không ổn định.

### 16.5. Default branch

Nếu không điều kiện nào khớp, cần xác định field bị bỏ qua, nhận default hay mapping thất bại.

## 17. Bidirectional mapping và round-trip

Bidirectional mapping giữ hai mô hình đồng bộ theo các thay đổi.

### 17.1. Round-trip property

Với source model S, mapping sang target T rồi quay lại S' có thể mong đợi:

~~~text
S -> mapForward -> T -> mapBackward -> S'
~~~

Nếu mapping lossless và canonicalization được định nghĩa, S' có thể tương đương S. Tương đương không nhất thiết là cùng object identity hoặc cùng thứ tự field.

### 17.2. Lossy mapping

Nếu target bỏ field, làm tròn số hoặc gộp nhiều giá trị, chiều ngược không thể khôi phục chính xác source. Cần ghi rõ mapping là lossy.

### 17.3. Bidirectional lens

Một cách mô hình hóa là tách hai thao tác:

- Get: lấy view từ source.
- Put: cập nhật source theo thay đổi của view.

Một số lens laws thường được dùng làm mục tiêu:

- Get-Put: lấy view rồi ghi lại view đó không làm source thay đổi ngoài chuẩn hóa được phép.
- Put-Get: sau khi cập nhật view, đọc lại view cho kết quả vừa ghi.

Các luật này cần được điều chỉnh theo semantics thực tế, nhất là khi có default, derived field hoặc dữ liệu chỉ đọc.

### 17.4. Conflict resolution

Nếu source và target cùng thay đổi, cần quy tắc giải quyết:

- Source of truth thắng.
- Target thắng trong phạm vi field được phép ghi.
- Merge theo field.
- Phát hiện conflict và yêu cầu người dùng giải quyết.

### 17.5. Derived fields

Field dẫn xuất thường không nên được ghi ngược trực tiếp. Ví dụ total có thể được tính từ line items; nếu client sửa total mà không sửa items, mapping cần từ chối hoặc áp dụng quy tắc nghiệp vụ.

## 18. Lossless và lossy mapping

Mapping lossless bảo toàn đủ thông tin để khôi phục mô hình nguồn trong phạm vi được định nghĩa. Mapping lossy làm mất hoặc chuẩn hóa thông tin.

### 18.1. Nguyên nhân mất thông tin

- Bỏ field không được target hỗ trợ.
- Làm tròn số.
- Chuyển timestamp về date.
- Flatten collection mà không giữ identity.
- Gộp nhiều enum vào một giá trị.
- Cắt chuỗi theo giới hạn độ dài.
- Loại bỏ unknown fields.
- Chuẩn hóa dữ liệu không lưu giá trị ban đầu.

### 18.2. Lossiness metadata

Mapping có thể khai báo:

~~~text
mapping "LegacyCustomer" {
    field fullName <- name
    field age <- birthDate using calculateAge(referenceDate)
    loss "birthDate is not preserved"
}
~~~

Nếu target chỉ giữ age, không thể tái tạo chính xác birthDate.

### 18.3. Lossy conversion cần explicit

Compiler có thể yêu cầu annotation hoặc policy rõ khi chuyển đổi có thể mất dữ liệu. Ví dụ Decimal sang Integer cần rounding mode hoặc reject.

### 18.4. Auditability

Với dữ liệu tài chính hoặc tuân thủ, cần giữ nguồn và quy tắc chuyển đổi để giải thích kết quả. Không nên âm thầm làm tròn hoặc bỏ field quan trọng.

## 19. Schema evolution và mapping version

Mô hình nguồn hoặc đích có thể thay đổi theo thời gian.

### 19.1. Additive change

Thêm field optional thường dễ tương thích hơn thêm field required. Tuy nhiên, consumer cũ có thể reject unknown field nếu cấu hình nghiêm ngặt.

### 19.2. Rename

Đổi tên field có thể phá vỡ consumer. Có thể hỗ trợ alias trong một giai đoạn hoặc tạo mapping cho từng schema version.

### 19.3. Type change

Đổi Integer thành Decimal hoặc String thành enum có thể cần converter và validation mới.

### 19.4. Remove field

Xóa field có thể ảnh hưởng client cũ, data migration và report. Cần deprecation period nếu contract được nhiều consumer sử dụng.

### 19.5. Versioned mapping

~~~text
mapping "OrderToApiV1" {
    source = DomainOrder
    target = ApiOrderV1
}

mapping "OrderToApiV2" {
    source = DomainOrder
    target = ApiOrderV2
}
~~~

Domain model có thể giữ ổn định trong khi mapper hỗ trợ nhiều phiên bản API.

### 19.6. Schema registry

Với event hoặc message, schema registry có thể lưu version và compatibility policy. Mapper cần biết schema writer version và reader version để chuyển đổi đúng.

### 19.7. Compatibility modes

Các chế độ thường gặp:

- Backward: reader mới đọc được dữ liệu cũ.
- Forward: reader cũ đọc được dữ liệu mới trong phạm vi quy tắc.
- Full: cả hai hướng đều tương thích theo định nghĩa registry.

Tên và semantics cụ thể phụ thuộc hệ thống schema. Cần kiểm tra contract thay vì chỉ dựa vào nhãn.

## 20. Mapping pipeline

Trong hệ thống thực tế, mapping thường là một chuỗi bước thay vì một phép chuyển đổi duy nhất.

~~~text
Input Document
      |
      v
Parse / Deserialize
      |
      v
Structural Validation
      |
      v
Source Model
      |
      v
Normalize / Enrich
      |
      v
Model Mapping
      |
      v
Domain Validation
      |
      v
Target Model
      |
      v
Serialize / Publish
~~~

### 20.1. Parse

Đọc định dạng bên ngoài và tạo cấu trúc có kiểu. Lỗi cú pháp hoặc format thuộc bước parse.

### 20.2. Structural validation

Kiểm tra schema, required field, type và cardinality của payload.

### 20.3. Normalize

Chuẩn hóa biểu diễn như trim, canonical identifier hoặc timezone theo contract.

### 20.4. Enrich

Tra cứu dữ liệu bổ sung nếu mapping yêu cầu. Enrichment nên được phân biệt với field conversion thuần vì nó có thể phụ thuộc network hoặc trạng thái bên ngoài.

### 20.5. Map

Áp dụng correspondence và transformation rules.

### 20.6. Domain validation

Kiểm tra invariant nghiệp vụ trên model đích hoặc domain command.

### 20.7. Serialize

Chuyển target model thành JSON, XML, row hoặc message.

### 20.8. Error boundary

Mỗi bước nên có lỗi riêng để biết payload sai format, mapping thiếu rule, conversion thất bại hay domain invariant bị vi phạm.

## 21. Mapping DSL và compiler

Một mapping DSL có thể được xem là ngôn ngữ khai báo các correspondence và transformation.

### 21.1. Grammar

Grammar cần biểu diễn:

- Mapping declaration.
- Source và target type.
- Field path.
- Expression.
- Converter.
- Condition.
- Default.
- Collection operation.
- Error policy.
- Version và metadata.

### 21.2. Name resolution

Compiler cần resolve field path theo schema nguồn và đích. Một field không tồn tại phải được báo lỗi ở compile time nếu schema đã biết.

### 21.3. Type checking

Compiler kiểm tra kiểu output của expression có gán được cho target field hay không. Converter phải có input/output type rõ.

### 21.4. Dependency graph

Nếu field đích phụ thuộc field đích khác, compiler có thể xây dependency graph để xác định thứ tự tính. Chu trình trong derived field cần được phát hiện.

### 21.5. Code generation

Mapping có thể được biên dịch thành Java method, serializer hoặc runtime plan. Generated code nên tránh reflection không cần thiết nếu hiệu năng quan trọng.

### 21.6. Interpreter

Một mapping engine thông dịch có thể đọc mapping metadata lúc runtime. Cách này linh hoạt nhưng cần cache plan, kiểm tra schema và giới hạn expression.

### 21.7. Static analysis

Compiler có thể phát hiện:

- Target field chưa được gán.
- Source field không được dùng.
- Hai rule ghi cùng target field.
- Type conversion có nguy cơ mất dữ liệu.
- Nullability mismatch.
- Mapping không exhaustive với enum hoặc union.
- Collection cardinality không tương thích.
- Dependency cycle.

## 22. Mapping syntax minh họa

Một DSL mapping có thể kết hợp khai báo field, converter và policy:

~~~text
mapping "CustomerToPartner" {
    source = Customer
    target = PartnerCustomer
    version = "2"

    field partnerId <- id
    field displayName <- profile.name
    field email <- contact.email using normalizeEmail

    field createdAt <- createdAt
        using toIsoInstant

    field state <- status
        using enumMap {
            ACTIVE -> "enabled"
            SUSPENDED -> "blocked"
            CLOSED -> "archived"
        }

    field labels <- tags
        using mapEach(tag -> tag.value)

    ignore internalNotes
}
~~~

Compiler có thể kiểm tra field path, converter signature và enum coverage. Với trường hợp đặc biệt, mapping có thể gọi custom converter đã đăng ký trong runtime.

### 22.1. Converter contract

Converter nên có kiểu rõ ràng:

~~~text
converter toIsoInstant(LocalDateTime, ZoneId) -> String
converter normalizeEmail(String) -> EmailAddress
~~~

Nếu converter cần timezone hoặc locale, dependency đó nên là input/context tường minh.

### 22.2. Error policy

Mỗi mapping có thể định nghĩa hành vi khi conversion thất bại:

- Reject toàn bộ record.
- Ghi diagnostic và bỏ record.
- Dùng fallback đã khai báo.
- Đưa record vào error channel hoặc quarantine.

Không nên mặc định bỏ qua field lỗi vì có thể tạo target object thiếu dữ liệu quan trọng.

## 23. Source mapping và traceability

Trong DSL, cần biết một giá trị target đến từ đâu để giải thích và debug.

### 23.1. Field-level provenance

Target field có thể giữ metadata:

- Source model type.
- Source field path.
- Source record ID.
- Mapping rule ID.
- Mapping version.
- Converter được sử dụng.

### 23.2. Mapping trace

Trace có thể cho biết:

~~~text
target.customerId
  <- source.customer.id
  rule: CustomerToApi.customerId
  conversion: identity
~~~

### 23.3. Error navigation

Nếu conversion thất bại, diagnostics có thể trỏ đến mapping rule và source field liên quan. Trong editor, người dùng có thể đi từ target field về declaration nguồn.

### 23.4. Provenance của derived field

Nếu total được tính từ items, trace nên giữ danh sách input và expression version. Điều này hữu ích khi giải thích dữ liệu hoặc điều tra sai lệch.

### 23.5. Privacy

Trace không nên ghi raw value nhạy cảm mặc định. Có thể ghi field path, type, length hoặc masked value tùy nhu cầu.

## 24. Error handling và mapping diagnostics

Một mapper cần trả lỗi có cấu trúc thay vì chỉ ném exception chung chung.

### 24.1. Missing source field

Schema nguồn không có field được mapping tham chiếu. Đây thường là lỗi compile-time nếu schema đã biết.

### 24.2. Missing target assignment

Target yêu cầu field bắt buộc nhưng mapping không gán. Compiler có thể phát hiện trước khi chạy.

### 24.3. Type conversion failure

Giá trị không thể chuyển đổi, ví dụ chuỗi không phải số hoặc enum không có giá trị tương ứng.

### 24.4. Constraint violation

Giá trị đã chuyển kiểu nhưng vi phạm range, pattern hoặc domain invariant.

### 24.5. Lookup failure

Reference data không tìm thấy hoặc dịch vụ enrichment không sẵn sàng. Cần phân biệt lỗi dữ liệu và lỗi hạ tầng.

### 24.6. Partial mapping

Với batch, có thể một số record thành công và một số thất bại. Hợp đồng cần quy định atomicity theo batch hay theo record, cách retry và cách quarantine record lỗi.

### 24.7. Diagnostic structure

Một diagnostic mapping có thể chứa:

- Code ổn định.
- Mapping ID và rule ID.
- Source path.
- Target path.
- Record ID hoặc correlation ID.
- Expected type và actual type.
- Severity.
- Remediation hint.

Không nên nhúng toàn bộ payload vào diagnostic vì payload có thể lớn hoặc nhạy cảm.

## 25. Mapping, validation và data quality

Mapping đúng cấu trúc chưa chắc dữ liệu đúng về nghiệp vụ.

### 25.1. Structural validation

Kiểm tra dữ liệu tuân schema: kiểu, required field, format và cardinality.

### 25.2. Semantic validation

Kiểm tra ý nghĩa: ngày kết thúc không trước ngày bắt đầu, tổng tiền không âm, trạng thái chuyển hợp lệ.

### 25.3. Referential validation

Kiểm tra reference có tồn tại hoặc có thể resolve, ví dụ customer ID thuộc tenant hiện tại.

### 25.4. Cross-field validation

Kiểm tra quan hệ giữa nhiều field, ví dụ currency phải phù hợp với payment method hoặc country.

### 25.5. Data quality metrics

Có thể đo tỷ lệ record mapping thành công, missing field, conversion failure, default usage và rejected record. Metric giúp phát hiện drift của upstream schema.

### 25.6. Validation placement

Validation đầu vào nên diễn ra trước transformation khi cần bảo vệ parser/mapper. Validation miền nên diễn ra sau khi tạo domain model. Target contract validation nên diễn ra trước serialization hoặc gửi request.

## 26. Hiệu năng và quy mô

Mapping có thể nằm trên đường xử lý của hàng triệu record hoặc request thời gian thực.

### 26.1. Reflection và generated code

Reflection giúp mapping động và giảm code viết tay, nhưng có thể tăng overhead và làm lỗi chỉ xuất hiện runtime. Generated code có thể nhanh và dễ kiểm tra hơn nhưng cần quy trình build.

### 26.2. Cache mapping plan

Nếu schema và mapping version không đổi, có thể cache plan hoặc converter lookup. Cache key cần bao gồm version và context ảnh hưởng semantics.

### 26.3. Avoid N+1 enrichment

Không gọi API lookup một lần cho mỗi record nếu có thể batch hoặc preload reference data. Enrichment cần timeout, cache và rate limit riêng.

### 26.4. Streaming

Với payload lớn, streaming parser và mapper có thể xử lý từng record mà không nạp toàn bộ document vào memory.

### 26.5. Batch mapping

Batch có thể amortize overhead nhưng cần xác định lỗi một record có làm hỏng toàn batch hay không.

### 26.6. Parallel mapping

Record độc lập có thể map song song. Cần bảo đảm converter thread-safe, context không bị chia sẻ mutable và output ordering được giữ nếu cần.

### 26.7. Memory allocation

Tránh tạo nhiều object trung gian không cần thiết. Tuy nhiên, tối ưu allocation không được làm giảm khả năng kiểm tra, traceability hoặc an toàn dữ liệu.

### 26.8. Benchmark thực tế

Đo mapping trên schema và dữ liệu gần production, bao gồm record lỗi, collection lớn, converter phức tạp và lookup. Chỉ đo happy path nhỏ có thể gây kết luận sai.

## 27. Security và trust boundary

Mapping là một ranh giới chuyển dữ liệu giữa các hệ thống có thể có mức tin cậy khác nhau.

### 27.1. Allowlist field

Response DTO nên chỉ expose field được phép. Không serialize toàn bộ domain object rồi hy vọng framework tự bỏ field nội bộ.

### 27.2. Mass assignment

Khi map request trực tiếp vào entity, client có thể gửi thêm field như role, ownerId hoặc isAdmin. Nếu mapper gán các field đó mà không có authorization, đây là rủi ro mass assignment.

### 27.3. Tenant boundary

Không cho phép request tự chọn tenant ID rồi mapper ghi vào entity nếu tenant chưa được xác thực từ security context. Kiểm tra ownership ở application/domain layer.

### 27.4. Sensitive fields

Password, token, private note hoặc dữ liệu cá nhân cần được loại khỏi response, log và trace theo policy.

### 27.5. Untrusted converter

Nếu mapping cho phép plugin hoặc expression do người dùng cung cấp, cần sandbox, giới hạn thời gian và quyền truy cập. Converter không được tự ý đọc file, gọi mạng hoặc truy cập secret nếu không được phép.

### 27.6. Injection

Mapping vào SQL, expression hoặc template phải dùng parameter binding và escaping đúng ngữ cảnh. Không nối chuỗi dữ liệu không tin cậy vào câu lệnh thực thi.

### 27.7. Denial of service

Payload lồng sâu, collection khổng lồ hoặc graph có chu trình có thể làm mapper tiêu thụ nhiều CPU và memory. Đặt giới hạn kích thước, chiều sâu và số phần tử.

## 28. Triển khai mapper bằng Java

Một cách triển khai đơn giản là dùng mapper tường minh ở ranh giới API.

### 28.1. Domain model

~~~java
public record Money(
        java.math.BigDecimal amount,
        String currency
) {
}

public record Customer(
        String id,
        String displayName
) {
}

public record DomainOrder(
        String id,
        Customer customer,
        Money total,
        OrderStatus status
) {
}
~~~

### 28.2. API DTO

~~~java
public record ApiOrder(
        String orderId,
        String customerId,
        String customerName,
        java.math.BigDecimal amount,
        String currency,
        String paymentStatus
) {
}
~~~

### 28.3. Explicit mapper

~~~java
public final class OrderMapper {
    public ApiOrder toApi(DomainOrder source) {
        return new ApiOrder(
            source.id(),
            source.customer().id(),
            source.customer().displayName(),
            source.total().amount(),
            source.total().currency(),
            mapStatus(source.status())
        );
    }

    private String mapStatus(OrderStatus status) {
        return switch (status) {
            case PAID -> "paid";
            case PENDING -> "pending";
            case CANCELLED -> "cancelled";
        };
    }
}
~~~

Ví dụ dùng Java record và switch expression. Nếu enum được mở rộng, switch không có default có thể giúp compiler chỉ ra nơi cần cập nhật tùy cấu hình và phiên bản Java.

### 28.4. Mapper với validation

~~~java
public ApiOrder toApi(DomainOrder source) {
    if (source.customer() == null) {
        throw new MappingException("customer is required");
    }
    if (source.total() == null) {
        throw new MappingException("total is required");
    }
    return new ApiOrder(
        source.id(),
        source.customer().id(),
        source.customer().displayName(),
        source.total().amount(),
        source.total().currency(),
        mapStatus(source.status())
    );
}
~~~

Trong ứng dụng thực tế, nên phân biệt lỗi cấu trúc model với lỗi domain invariant. Không dùng mapper để thay thế toàn bộ validation nghiệp vụ.

### 28.5. Converter registry

Một hệ thống có thể đăng ký converter theo cặp kiểu:

~~~java
public interface Converter<S, T> {
    T convert(S source, MappingContext context);
}
~~~

MappingContext có thể chứa locale, timezone, schema version và tenant đã xác thực. Không nên chứa global mutable state hoặc quyền truy cập rộng không cần thiết.

### 28.6. Generic mapping

Reflection-based generic mapper có thể giảm boilerplate nhưng cần quy tắc rõ cho null, nested object, cycle, collection và unknown field. Với contract API quan trọng, explicit mapping hoặc generated mapper thường dễ review hơn.

## 29. Kiểm thử model mapping

Mapping cần được kiểm thử theo schema và semantics.

### 29.1. Field correspondence tests

Xác nhận mỗi field đích nhận đúng field nguồn hoặc converter tương ứng.

### 29.2. Type conversion tests

Bao phủ giá trị bình thường, min/max, overflow, rounding, null và format không hợp lệ.

### 29.3. Enum exhaustiveness

Khi thêm enum variant mới, test hoặc compiler phải phát hiện mapping chưa xử lý.

### 29.4. Collection tests

Kiểm tra empty, singleton, duplicate, ordering, null element và collection lớn.

### 29.5. Cycle and identity tests

Dùng object graph có shared reference và cycle để xác nhận mapper không lặp vô hạn hoặc nhân bản identity sai.

### 29.6. Round-trip tests

Với mapping được kỳ vọng lossless, chuyển đi rồi về và so sánh theo equality semantics đã định nghĩa. Không áp dụng round-trip assertion cho field bị loại hoặc chuẩn hóa mất thông tin.

### 29.7. Schema compatibility tests

Chạy mapping với payload của các schema version được hỗ trợ, bao gồm field mới, field thiếu và enum mới.

### 29.8. Golden files

Snapshot JSON/XML có thể giúp phát hiện thay đổi contract. Cần canonicalize thứ tự hoặc format để diff không bị nhiễu.

### 29.9. Property-based tests

Sinh model hợp lệ ngẫu nhiên và kiểm tra invariant như:

- Mapping không tạo giá trị ngoài range.
- ID được giữ nguyên.
- Tổng tiền không đổi khi chuyển biểu diễn tương đương.
- Mapping không làm lộ field bị cấm.
- Round-trip giữ các field được khai báo lossless.

### 29.10. Performance tests

Đo throughput, latency và memory với dataset đại diện. Kiểm tra cả trường hợp nhiều nested object và converter có lookup.

## 30. Những sai lầm thường gặp

### 30.1. Dùng chung domain model và API DTO

Contract API thay đổi có thể làm domain model biến dạng hoặc expose field nội bộ. Tách DTO ở ranh giới hệ thống.

### 30.2. Dựa hoàn toàn vào tên field

Hai field cùng tên chưa chắc cùng nghĩa; hai field khác tên có thể tương ứng. Khai báo correspondence theo semantics.

### 30.3. Ép mọi thứ thành String

Chuyển kiểu sang string làm mất type safety và có thể gây lỗi format, locale hoặc so sánh.

### 30.4. Không phân biệt missing và null

PATCH hoặc partial response có thể bị ghi đè dữ liệu ngoài ý muốn nếu mapper coi missing là null.

### 30.5. Bỏ qua đơn vị và timezone

1000 milliseconds không giống 1000 seconds; LocalDateTime không tự xác định timezone. Dùng type và unit rõ ràng.

### 30.6. Dùng enum ordinal

Thứ tự enum có thể thay đổi giữa phiên bản. Dùng stable code hoặc mapping tường minh.

### 30.7. Không xử lý cycle

Mapper đệ quy trên object graph có chu trình có thể stack overflow. Dùng identity map hoặc reference representation.

### 30.8. Tạo N+1 query

Mapper truy cập lazy relation cho từng record có thể tạo hàng nghìn query. Xác định fetch plan hoặc batch lookup.

### 30.9. Bỏ qua field không được hỗ trợ

Silent ignore có thể làm mất dữ liệu quan trọng. Phân loại ignored field có chủ đích và field chưa được mapping.

### 30.10. Không version mapping

Khi schema đổi, mapping cũ có thể cho kết quả sai mà không báo lỗi. Gắn mapping với source/target schema version.

### 30.11. Cho client ghi field nội bộ

Map request trực tiếp vào entity có thể tạo mass assignment. Dùng request model allowlist và kiểm tra quyền.

### 30.12. Coi round-trip luôn phải bằng nhau

Mapping có thể lossy hoặc chuẩn hóa. Định nghĩa rõ field nào phải bảo toàn và cách so sánh tương đương.

### 30.13. Đưa side effect vào converter

Converter gọi network hoặc ghi database làm mapping khó tái lập và khó retry. Tách enrichment và side effect thành bước có hợp đồng riêng.

### 30.14. Không giữ provenance

Khi giá trị sai, nhóm không biết nó đến từ field nào hoặc converter nào. Giữ mapping rule ID và trace metadata phù hợp.

## 31. Quy trình thiết kế ánh xạ mô hình

Một quy trình thực hiện có thể gồm:

1. **Xác định boundary.** Làm rõ source model, target model và hệ thống sở hữu từng mô hình.
2. **Thu thập schema.** Lấy field, type, cardinality, constraint, enum và version.
3. **Xác định semantics.** Phân biệt field có cùng tên nhưng khác nghĩa, đơn vị hoặc lifecycle.
4. **Lập correspondence.** Ghi field-to-field, nested, flatten, split, combine, constant và ignored fields.
5. **Định nghĩa conversion.** Quy định numeric, date/time, enum, unit, null và collection behavior.
6. **Xác định lossiness.** Ghi rõ thông tin bị loại, gộp hoặc chuẩn hóa.
7. **Định nghĩa versioning.** Chọn schema version, alias, compatibility và migration policy.
8. **Thiết kế mapping language.** Quy định grammar, expression, converter, condition và error policy.
9. **Kiểm tra tĩnh.** Resolve field path, type check, phát hiện missing assignment và dependency cycle.
10. **Triển khai mapper.** Dùng explicit code, generated code hoặc interpreter phù hợp.
11. **Thêm validation.** Tách structural, semantic và target contract validation.
12. **Thêm traceability.** Giữ mapping ID, source path và version để debug.
13. **Bảo vệ boundary.** Allowlist field, kiểm tra tenant, authorization và dữ liệu nhạy cảm.
14. **Kiểm thử.** Bao phủ conversion, null, collection, round-trip, compatibility và performance.
15. **Vận hành và tiến hóa.** Theo dõi mapping failure, schema drift, version rollout và deprecation.

## 32. Câu hỏi tự kiểm tra

1. Ánh xạ mô hình là gì và vì sao cần trong DSL API và dữ liệu?
2. Phân biệt source model, target model, metamodel, schema và instance.
3. Model mapping khác parsing và validation như thế nào?
4. Nêu các kiểu mapping model-to-model, model-to-document, model-to-relational và model-to-event.
5. Correspondence giữa field có thể là direct, rename, nested, flatten, split hoặc combine ra sao?
6. Vì sao type mapping cần quan tâm overflow, precision, rounding và timezone?
7. Missing, null, empty và default khác nhau như thế nào trong API update?
8. Collection mapping cần xử lý ordering, duplicate và cardinality ra sao?
9. Object identity, shared reference và cyclic reference ảnh hưởng mapper thế nào?
10. Discriminator giúp ánh xạ polymorphic model ra sao và cần xử lý unknown subtype thế nào?
11. Vì sao domain model nên tách khỏi API DTO?
12. Declarative mapping và imperative mapping có trade-off gì?
13. Bidirectional mapping và round-trip property có giới hạn nào?
14. Lossy mapping có thể xảy ra trong những tình huống nào?
15. Schema evolution cần chiến lược versioning và compatibility ra sao?
16. Một mapping pipeline thường gồm những bước nào?
17. Compiler có thể phát hiện những lỗi mapping nào ở compile time?
18. Source provenance giúp điều tra lỗi chuyển đổi như thế nào?
19. Mapping có thể tạo rủi ro mass assignment hoặc tenant leakage ra sao?
20. Hãy thiết kế mapping từ DomainOrder sang hai phiên bản API khác nhau, nêu field correspondence, converter, null policy và cách kiểm thử.
