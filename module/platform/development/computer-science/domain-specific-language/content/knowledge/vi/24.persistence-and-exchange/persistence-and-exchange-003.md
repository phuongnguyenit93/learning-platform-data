# Giải tuần tự hóa

## Giải tuần tự hóa trong DSL là gì?

Trong một hệ thống sử dụng ngôn ngữ chuyên miền (domain-specific language, DSL), dữ liệu và mô hình thường được lưu thành tệp hoặc trao đổi giữa các thành phần. Khi dữ liệu được ghi ra JSON, XML, YAML, binary format hoặc một định dạng riêng, hệ thống cần một cơ chế để đọc biểu diễn đó và dựng lại cấu trúc dữ liệu có thể sử dụng trong chương trình.

Quá trình này được gọi là **giải tuần tự hóa (deserialization)**. Nó chuyển dữ liệu đã được tuần tự hóa thành object, model, AST, cấu trúc cấu hình hoặc một biểu diễn miền có kiểu.

Ví dụ, một rule có thể được lưu dưới dạng JSON:

~~~json
{
  "name": "Free shipping",
  "condition": {
    "operator": "greaterThanOrEqual",
    "left": { "property": "order.total" },
    "right": { "value": 500000, "unit": "VND" }
  },
  "action": {
    "set": "shipment.fee",
    "value": 0,
    "unit": "VND"
  }
}
~~~

Khi nạp tệp, hệ thống đọc JSON, xác định cấu trúc, kiểm tra schema, dựng các đối tượng Rule, Condition, PropertyReference và Action, rồi xác thực các tham chiếu và quy tắc miền. Kết quả có thể được đưa vào compiler, rule engine hoặc giao diện chỉnh sửa.

Giải tuần tự hóa thường được xem là chiều ngược của tuần tự hóa (serialization):

~~~text
In-memory model
      |
      | Serialization
      v
Stored / exchanged representation
      |
      | Deserialization
      v
Reconstructed model
~~~

Hai chiều này có liên quan nhưng không nhất thiết là phép đảo hoàn hảo. Định dạng lưu trữ có thể bỏ comment, thông tin runtime hoặc chi tiết nội bộ. Ngược lại, quá trình nạp có thể bổ sung giá trị mặc định, resolve reference, migrate schema hoặc chuẩn hóa dữ liệu.

Trong phạm vi lưu trữ và trao đổi của DSL, giải tuần tự hóa có vai trò quan trọng vì nó quyết định dữ liệu bên ngoài được đưa vào mô hình nội bộ như thế nào, được kiểm tra ra sao và có thể được sử dụng an toàn đến mức nào.

## Phân biệt giải tuần tự hóa, parsing và khôi phục mô hình

Các thuật ngữ parsing, deserialization và model loading đôi khi được dùng thay thế nhau, nhưng chúng mô tả các công việc khác nhau.

| Khái niệm | Đầu vào | Kết quả chính |
|---|---|---|
| Decoding | Byte sequence | Ký tự hoặc giá trị primitive |
| Parsing | Văn bản hoặc token | Cấu trúc cú pháp theo grammar |
| Deserialization | Biểu diễn đã lưu | Object hoặc model có kiểu |
| Validation | Model hoặc dữ liệu | Kết luận hợp lệ và diagnostics |
| Name/reference resolution | Model có tham chiếu | Liên kết đến phần tử được định danh |
| Migration | Model phiên bản cũ | Model theo schema mới |
| Runtime initialization | Model đã chuẩn bị | Trạng thái có thể thực thi |

Ví dụ, parser của DSL có thể nhận văn bản:

~~~text
RULE "Free shipping"
WHEN order.total >= 500000
THEN shipment.fee = 0
~~~

và tạo AST. Trong khi đó, deserializer JSON có thể nhận object đã lưu và tạo một RuleModel trực tiếp. Hai đường đi có thể cùng tạo ra một mô hình miền chuẩn, nhưng cách xử lý cú pháp và metadata khác nhau.

Một pipeline nạp dữ liệu có thể gồm nhiều bước:

~~~text
Bytes
  |
  v
Character decoding
  |
  v
Format parsing
  |
  v
Raw data structure
  |
  v
Schema and version check
  |
  v
Typed deserialization
  |
  v
Reference resolution
  |
  v
Domain validation
  |
  v
Loaded DSL model
~~~

Trong một số framework, parsing và deserialization được thực hiện trong một API duy nhất. Dù vậy, về mặt thiết kế vẫn nên hiểu các trách nhiệm riêng để phân loại lỗi và kiểm soát dữ liệu.

### Deserialization không đồng nghĩa với validation

Một JSON document có thể parse thành công nhưng không hợp lệ theo schema. Ví dụ, trường name có thể bị thiếu hoặc trường condition có thể chứa một kiểu dữ liệu không được hỗ trợ.

Một model có thể conform với schema cấu trúc nhưng vẫn vi phạm quy tắc miền. Ví dụ, một rule có đầy đủ trường nhưng tham chiếu đến thuộc tính không tồn tại trong domain schema.

Vì vậy, nên phân biệt ít nhất ba kết quả:

- Dữ liệu có cú pháp hợp lệ theo định dạng lưu trữ.
- Dữ liệu có cấu trúc và kiểu phù hợp với schema.
- Mô hình có ý nghĩa hợp lệ trong miền DSL.

Một hệ thống có thể kết hợp các bước này, nhưng không nên xem việc parse thành công là bằng chứng dữ liệu đã sẵn sàng để thực thi.

## Các giai đoạn của pipeline giải tuần tự hóa

Một pipeline rõ ràng giúp kiểm soát dữ liệu từ nguồn ngoài đến mô hình nội bộ.

### 1. Tiếp nhận dữ liệu

Nguồn có thể là tệp cục bộ, HTTP response, message queue, database column, cache, object storage hoặc một API plugin.

Ở bước này cần xác định:

- Nguồn dữ liệu và định danh tài nguyên.
- Kích thước và giới hạn đọc.
- Encoding hoặc content type.
- Định dạng dự kiến.
- Phiên bản schema nếu có.
- Ngữ cảnh tenant, module hoặc project.
- Quyền truy cập đối với tài nguyên.

Không nên giả định phần mở rộng tệp luôn xác định đúng định dạng. Một tệp có tên rules.json vẫn có thể chứa XML hoặc nội dung không hợp lệ. Content type, magic bytes hoặc cấu hình hợp đồng có thể được dùng để xác định format.

### 2. Giải mã byte thành ký tự

Nếu dữ liệu là văn bản, byte sequence cần được giải mã theo encoding. UTF-8 thường được dùng cho dữ liệu trao đổi, nhưng hệ thống cần xử lý rõ trường hợp BOM, encoding không hợp lệ và ký tự không thể biểu diễn.

Lỗi decoding khác với lỗi cú pháp JSON hoặc DSL. Ví dụ, byte sequence không hợp lệ theo UTF-8 phải được báo là lỗi encoding thay vì lỗi thiếu dấu ngoặc JSON.

Nếu dữ liệu là binary format, bước này có thể được thay bằng việc đọc header, version và primitive value theo định dạng tương ứng.

### 3. Parse định dạng lưu trữ

Parser của JSON, XML, YAML, CBOR hoặc định dạng riêng tạo ra cấu trúc dữ liệu thô. Ở bước này, hệ thống kiểm tra cú pháp định dạng: dấu ngoặc, dấu phân cách, escape, tag, length field hoặc cấu trúc binary.

Ví dụ JSON hợp lệ:

~~~json
{
  "name": "Rule A",
  "enabled": true
}
~~~

Ví dụ JSON sai:

~~~json
{
  "name": "Rule A",
  "enabled": true,
}
~~~

Nếu định dạng không cho phép trailing comma, document thứ hai phải bị từ chối ở bước parse. Nó chưa đến bước kiểm tra kiểu của Rule.

### 4. Kiểm tra schema và version

Sau khi có cấu trúc thô, hệ thống xác định document tuân theo schema nào. Schema quy định trường bắt buộc, kiểu dữ liệu, giá trị enum, cấu trúc lồng, bội số và các giới hạn.

Ví dụ schema có thể yêu cầu:

- name là chuỗi không rỗng.
- enabled là boolean.
- condition là một expression object.
- actions là danh sách action.
- version là phiên bản schema được hỗ trợ.

Version quyết định cách diễn giải trường và quy tắc tương thích. Không nên deserialize document của một phiên bản chưa được hỗ trợ bằng cách đoán cấu trúc.

### 5. Chuyển thành kiểu dữ liệu nội bộ

Deserializer ánh xạ dữ liệu thô sang class, record, struct hoặc model element có kiểu.

Ví dụ:

~~~text
Raw object
  name: "Rule A"
  enabled: true

        |

        v

Rule
  name: String("Rule A")
  enabled: Boolean(true)
  condition: Optional<Expression>
  actions: List<Action>
~~~

Ở bước này, cần quy định cách xử lý trường thiếu, null, giá trị mặc định, enum, số và kiểu con.

### 6. Dựng quan hệ và resolve reference

Một số model chứa ID tham chiếu đến phần tử khác. Deserializer có thể tạo object trước, sau đó resolve reference khi toàn bộ phần tử đã được nạp.

Ví dụ một rule tham chiếu đến function có ID function-42. Deserializer cần tìm function tương ứng trong registry hoặc module context. Nếu không tồn tại, model có thể được đánh dấu unresolved hoặc phát lỗi theo chính sách.

### 7. Validation miền và khởi tạo

Sau khi object graph được dựng, hệ thống kiểm tra invariant miền: kiểu tương thích, giới hạn giá trị, quan hệ hợp lệ, quyền và các điều kiện nghiệp vụ. Nếu cần, runtime có thể khởi tạo cache, index hoặc liên kết đến service.

Chỉ sau những bước bắt buộc này, model mới nên được đưa vào execution engine hoặc được công bố như một cấu hình đã nạp.

## Các dạng dữ liệu và định dạng trao đổi

DSL có thể dùng nhiều định dạng tùy nhu cầu đọc, hiệu năng, khả năng tương thích và kích thước dữ liệu.

### JSON

JSON phổ biến trong REST API, cấu hình, artifact và trao đổi giữa các ngôn ngữ lập trình. Nó có object, array, string, number, boolean và null.

Ưu điểm:

- Dễ đọc và dễ debug.
- Được hỗ trợ rộng rãi.
- Tích hợp tốt với web API.
- Có nhiều công cụ schema và validation.

Hạn chế:

- Không có kiểu date, decimal, binary hoặc reference riêng trong lõi định dạng.
- Number có thể mất precision khi được đọc bằng kiểu floating-point.
- Comment không thuộc JSON chuẩn.
- Object không cam kết thứ tự key có ý nghĩa.
- Kiểu polymorphic cần được mô tả bằng discriminator hoặc schema.

Với DSL, JSON phù hợp cho cấu hình và API nhưng cần quy ước rõ cho Decimal, timestamp, enum, unit và ID.

### YAML

YAML thường được dùng cho cấu hình vì hỗ trợ cấu trúc phân cấp và cú pháp tương đối dễ đọc.

Ví dụ:

~~~yaml
name: Free shipping
enabled: true
condition:
  operator: greaterThanOrEqual
  left:
    property: order.total
  right:
    value: 500000
    unit: VND
~~~

YAML có nhiều quy tắc về scalar, implicit typing, anchor, alias và tag. Một số chuỗi như ngày tháng hoặc giá trị có hình dạng đặc biệt có thể được parser diễn giải theo kiểu không như mong đợi.

Nếu DSL dùng YAML làm định dạng lưu trữ, nên quy định schema và parser profile được hỗ trợ, tránh phụ thuộc vào các extension khác nhau giữa thư viện.

### XML

XML có cấu trúc element, attribute, namespace và text node. Nó hữu ích khi cần schema mạnh, namespace hoặc tích hợp với hệ thống enterprise.

Ví dụ:

~~~xml
<rule name="Free shipping">
  <condition operator="greaterThanOrEqual">
    <property>order.total</property>
    <constant value="500000" unit="VND"/>
  </condition>
</rule>
~~~

XML có thể dùng XSD để kiểm tra cấu trúc. Tuy nhiên, cần cấu hình parser an toàn, đặc biệt với external entity, DTD và resource resolution.

### Binary format

Các định dạng như Protocol Buffers, Avro, MessagePack hoặc CBOR có thể giảm kích thước và tăng hiệu quả trao đổi. Một số định dạng có schema hoặc hỗ trợ versioning tốt.

Ưu điểm thường gặp:

- Kích thước nhỏ hơn văn bản.
- Parse hiệu quả.
- Có thể hỗ trợ schema evolution.
- Phù hợp message throughput cao.

Hạn chế:

- Khó đọc trực tiếp.
- Cần công cụ debug hoặc dạng text representation.
- Tương thích phụ thuộc schema và quy tắc field number.
- Một số định dạng không tự mang đầy đủ schema.

Lựa chọn binary format không loại bỏ nhu cầu validation. Dữ liệu binary vẫn có thể chứa enum không hợp lệ, field thiếu, length sai hoặc reference không tồn tại.

### Định dạng DSL riêng

Một DSL có thể lưu AST hoặc model bằng định dạng riêng. Ví dụ, artifact biên dịch có thể chứa magic header, version, symbol table, instruction data và source map.

Khi thiết kế format riêng, cần đặc tả:

- Header và magic bytes.
- Version và flags.
- Encoding và byte order.
- Cấu trúc section.
- Length và offset.
- Checksum hoặc integrity metadata nếu cần.
- Quy tắc tương thích.
- Xử lý field hoặc section chưa biết.

Format riêng cho phép kiểm soát hiệu năng và semantics, nhưng tạo trách nhiệm bảo trì parser, migration và công cụ inspect.

## Ánh xạ dữ liệu lưu trữ sang kiểu của DSL

Một phần quan trọng của deserialization là chuyển primitive value trong format sang kiểu dữ liệu có ý nghĩa của DSL.

### String và identifier

Một chuỗi trong JSON có thể là tên hiển thị, identifier, qualified name, path, symbol ID hoặc literal văn bản. Không nên coi mọi chuỗi là cùng một kiểu.

Ví dụ:

~~~json
{
  "ruleName": "VIP discount",
  "targetSymbol": "symbol-42",
  "property": "order.total"
}
~~~

Ba trường đều là string ở JSON nhưng có thể được ánh xạ thành RuleName, SymbolId và PropertyPath riêng. Kiểu miền giúp tránh truyền nhầm giá trị.

### Number và precision

JSON number không phân biệt integer, decimal hay floating-point theo một kiểu máy cụ thể. Deserializer cần biết trường đích yêu cầu kiểu nào.

Các lựa chọn:

- Integer với phạm vi xác định.
- Int64 hoặc BigInteger.
- Decimal với precision và scale.
- Rational khi cần phân số chính xác.
- Floating-point khi semantics chấp nhận sai số.

Ví dụ số tiền 123456789012345.67 không nên đi qua một kiểu binary floating-point nếu yêu cầu tài chính cần giữ chính xác từng chữ số. Deserializer nên đọc trực tiếp từ biểu diễn số sang Decimal hoặc dạng số nguyên theo đơn vị nhỏ nhất.

Cũng cần xử lý overflow, exponent, số âm, giá trị không hữu hạn và scale vượt giới hạn. JSON chuẩn không biểu diễn NaN và Infinity; một số thư viện có extension riêng, vì vậy cần thống nhất policy.

### Boolean

Boolean nên được đọc đúng kiểu. Không nên tự động coi chuỗi "true", số 1 hoặc chuỗi "yes" là boolean trừ khi schema hoặc format quy định chuyển đổi đó.

Implicit coercion làm dữ liệu dễ nhập nhưng có thể che lỗi từ producer. Với API hoặc artifact cần ổn định, strict typing thường dễ dự đoán hơn.

### Enum

Enum có thể được lưu bằng tên, code hoặc số ordinal.

Ví dụ:

~~~json
{
  "operator": "GREATER_THAN_OR_EQUAL"
}
~~~

Nếu lưu ordinal, việc đổi thứ tự khai báo enum có thể làm dữ liệu cũ đổi nghĩa. Dùng tên ổn định hoặc mã được quản lý thường an toàn hơn. Deserializer cần có hành vi rõ với giá trị enum chưa biết: từ chối, giữ dạng unknown enum hoặc chuyển sang giá trị fallback đã được đặc tả.

### Date, time và duration

Định dạng lưu trữ cần phân biệt:

- Instant: một thời điểm tuyệt đối.
- Local date-time: ngày giờ địa phương.
- Date: ngày lịch.
- Time: giờ trong ngày.
- Duration: khoảng thời gian.
- Period: khoảng theo lịch như một tháng.

Không nên deserialize mọi chuỗi ngày giờ thành timestamp theo timezone mặc định của máy. Cần lưu offset hoặc timezone khi semantics yêu cầu.

Ví dụ:

~~~json
{
  "createdAt": "2026-11-15T09:30:00Z",
  "timeoutSeconds": 30,
  "billingPeriod": "P1M"
}
~~~

createdAt có thể là Instant; timeoutSeconds là Duration; billingPeriod là Period. Một tháng lịch không tương đương một số giây cố định.

### Quantity và đơn vị đo

Nếu DSL hỗ trợ quantity, dữ liệu cần giữ cả giá trị và đơn vị:

~~~json
{
  "value": 12.5,
  "unit": "km"
}
~~~

Deserializer cần:

1. Đọc giá trị theo kiểu số phù hợp.
2. Resolve ký hiệu unit trong catalog.
3. Xác định dimension.
4. Kiểm tra kiểu đích có tương thích.
5. Áp dụng chuẩn hóa nếu model yêu cầu.
6. Giữ precision và nguồn gốc nếu cần.

Không nên chỉ lưu 12.5 rồi suy ra đơn vị từ tên trường. Nếu đơn vị không được nhận diện hoặc dimension không tương thích, cần diagnostic cụ thể.

### Null và missing value

Trong dữ liệu có cấu trúc, trường bị thiếu và trường có giá trị null có thể mang ý nghĩa khác nhau.

Ví dụ:

~~~json
{}
~~~

~~~json
{ "description": null }
~~~

Document thứ nhất không cung cấp description. Document thứ hai cung cấp trường description với giá trị null. Tùy schema, hai trường hợp có thể có ý nghĩa:

- Dùng default khi trường bị thiếu.
- Giữ null để biểu thị không có giá trị.
- Từ chối null nếu trường bắt buộc.
- Dùng missing để biểu thị không cập nhật trường trong patch request.

Với API cập nhật một phần, phân biệt missing và null đặc biệt quan trọng: missing có thể có nghĩa giữ nguyên giá trị cũ, còn null có thể yêu cầu xóa giá trị.

## Dựng object graph và xử lý reference

Mô hình DSL thường không chỉ là cây lồng nhau. Nhiều phần tử có thể được chia sẻ hoặc tham chiếu lẫn nhau.

Ví dụ:

~~~text
Module
  Rule A ---- references ----> Function F
  Rule B ---- references ----> Function F
  Function F ---- references ----> Type T
~~~

Nếu deserializer tạo một bản sao Function F cho mỗi rule, identity và trạng thái dùng chung có thể bị sai. Cần phân biệt containment với reference.

### Containment

Containment thể hiện phần tử con thuộc quyền sở hữu cấu trúc của phần tử cha. Khi parent bị xóa, child có thể bị xóa cùng. Ví dụ Rule chứa condition và danh sách action.

### Reference

Reference trỏ đến một phần tử tồn tại độc lập. Ví dụ Rule gọi một Function được khai báo ở module khác. Reference thường được lưu bằng ID hoặc qualified name.

### Hai pha nạp mô hình

Một cách phổ biến để xử lý reference là nạp hai pha:

1. Tạo các phần tử và đăng ký ID vào object registry.
2. Resolve các reference sau khi các phần tử mục tiêu đã được đăng ký.

Sơ đồ:

~~~text
Read document
     |
     v
Create model elements
     |
     v
Register stable IDs
     |
     v
Resolve references
     |
     v
Validate graph
~~~

Cách này hỗ trợ forward reference, tức một phần tử có thể tham chiếu đến phần tử được khai báo phía sau trong tài liệu.

### Reference không tồn tại

Nếu reference trỏ đến ID không có trong registry, hệ thống cần xác định:

- Đây là lỗi bắt buộc hay reference tùy chọn?
- Có được phép lazy-load module khác không?
- Có thể giữ unresolved reference để IDE tiếp tục làm việc không?
- Có cần báo cả vị trí khai báo và vị trí tham chiếu không?

Không nên tự tạo một object rỗng để thay thế reference thiếu nếu điều đó có thể khiến model được xem là hợp lệ giả tạo.

### Chu trình và object identity

Object graph có thể có chu trình, chẳng hạn hai module tham chiếu lẫn nhau hoặc entity có quan hệ parent-child hai chiều. Deserializer cần hỗ trợ hoặc từ chối chu trình theo schema.

Nếu format là JSON thuần, reference thường được biểu diễn bằng ID thay vì lồng object trực tiếp để tránh vòng lặp. Với object graph trong bộ nhớ, registry giúp giữ một instance cho mỗi ID.

## Polymorphism và discriminators

Một trường có thể chứa nhiều subtype. Ví dụ Expression có thể là Constant, PropertyReference, BinaryExpression hoặc FunctionCall.

Dữ liệu nên có discriminator xác định subtype:

~~~json
{
  "kind": "binary",
  "operator": "greaterThanOrEqual",
  "left": {
    "kind": "property",
    "path": "order.total"
  },
  "right": {
    "kind": "constant",
    "value": 500000,
    "unit": "VND"
  }
}
~~~

Deserializer đọc kind rồi chọn class hoặc factory tương ứng. Cần quy định:

- Danh sách discriminator hợp lệ.
- Phiên bản nào hỗ trợ subtype nào.
- Hành vi với kind chưa biết.
- Các trường bắt buộc của từng subtype.
- Có cho phép extension subtype không.
- Làm thế nào để ngăn producer tạo class tùy ý.

Không nên cho dữ liệu bên ngoài chỉ định tên class tùy ý rồi phản chiếu (reflection) để khởi tạo. Discriminator nên được ánh xạ qua registry hoặc allowlist các kiểu đã được phép.

## Default value, constructor và invariant

Một object miền có thể cần giá trị mặc định hoặc điều kiện khởi tạo. Deserializer cần biết khi nào được phép dùng default và khi nào thiếu trường là lỗi.

Ví dụ, Rule có thể có enabled mặc định là true nếu trường không xuất hiện. Nhưng nếu name là bắt buộc, không nên tự đặt tên rỗng để tiếp tục.

Có thể phân loại:

| Loại trường | Khi bị thiếu |
|---|---|
| Required | Báo lỗi |
| Optional | Dùng absent hoặc null theo schema |
| Defaulted | Gán giá trị mặc định đã công bố |
| Derived | Tính từ trường khác |
| Runtime-only | Khởi tạo trong runtime, không đọc từ file |
| Deprecated | Bỏ qua, cảnh báo hoặc migrate theo version |

### Constructor và factory

Một số model có constructor yêu cầu invariant ngay khi tạo. Có thể dùng factory để đảm bảo object chỉ được tạo sau khi dữ liệu cơ bản hợp lệ.

Ví dụ:

~~~text
RuleFactory.create(
  name,
  condition,
  actions,
  enabled
)
~~~

Factory có thể kiểm tra name không rỗng, condition có kiểu Expression và danh sách action thỏa bội số. Nếu model phức tạp có reference vòng, có thể cần builder hoặc hai pha khởi tạo thay vì constructor trực tiếp.

### Trường được tính toán

Một số giá trị không nên được deserialize trực tiếp vì chúng được suy ra từ dữ liệu khác. Ví dụ compiledCondition, cacheKey hoặc runtimeIndex có thể được tính lại sau khi nạp.

Nếu lưu cả giá trị nguồn và giá trị dẫn xuất, cần quy định giá trị nào là authoritative. Một giá trị dẫn xuất cũ có thể không còn đúng sau migration hoặc khi schema thay đổi.

## Schema validation và contract dữ liệu

Schema là hợp đồng giữa producer và consumer. Producer serialize dữ liệu theo schema; consumer deserialize theo schema tương thích.

Schema có thể quy định:

- Tên và kiểu field.
- Field bắt buộc hoặc tùy chọn.
- Default.
- Enum values.
- Cấu trúc object và array.
- Giới hạn độ dài và phạm vi số.
- Pattern cho identifier.
- Quan hệ giữa các trường.
- Version và extension.

JSON Schema, XSD, Protocol Buffers schema hoặc schema riêng đều có thể được dùng. Lựa chọn phụ thuộc format và yêu cầu toolchain.

### Structural validation và semantic validation

Structural validation kiểm tra document có hình dạng đúng. Ví dụ actions là array và mỗi phần tử có field kind.

Semantic validation kiểm tra ý nghĩa giữa các trường. Ví dụ, action SetProperty có target kiểu Money thì value phải có đơn vị tiền tệ tương thích.

Hai lớp validation nên tạo diagnostics khác nhau để người dùng biết lỗi nằm ở schema hay logic miền.

### Strict mode và permissive mode

Strict mode từ chối field không biết, enum không nhận diện hoặc kiểu không đúng. Nó phù hợp với artifact cần tính xác định và dữ liệu có kiểm soát.

Permissive mode có thể giữ extension, bỏ qua field không quan trọng hoặc cho phép model một phần. Nó hữu ích cho công cụ IDE, dữ liệu forward-compatible hoặc hệ thống plugin.

Cần xác định rõ từng trường hợp. Bỏ qua unknown field có thể hỗ trợ tương thích, nhưng nếu field đó ảnh hưởng semantics thì consumer cũ có thể chạy sai mà không biết. Một policy tốt có thể cho phép unknown metadata nhưng từ chối unknown instruction hoặc action.

## Schema evolution và tương thích phiên bản

DSL và format lưu trữ thường phát triển theo thời gian. Phiên bản mới có thể thêm field, đổi kiểu, đổi tên, tách một trường thành nhiều trường hoặc thay đổi semantics.

Deserialization cần xử lý document được tạo bởi phiên bản cũ hoặc mới.

### Backward compatibility

Consumer mới đọc được dữ liệu được tạo bởi producer cũ. Điều này thường khả thi khi schema mới có thể cung cấp default cho field mới và vẫn hiểu cấu trúc cũ.

Ví dụ, version 1 không có enabled; version 2 thêm enabled với default true. Consumer version 2 có thể nạp document version 1 bằng cách áp dụng default.

### Forward compatibility

Consumer cũ đọc được dữ liệu do producer mới tạo. Điều này khó hơn nếu producer mới dùng field hoặc semantics mà consumer cũ không hiểu.

Một consumer có thể bỏ qua field metadata mới, nhưng không nên bỏ qua một action mới có thể thay đổi kết quả thực thi.

### Compatibility matrix

| Thay đổi schema | Thường tương thích? | Điều kiện |
|---|---|---|
| Thêm field optional | Có thể | Consumer cũ bỏ qua an toàn hoặc giữ extension |
| Thêm field required | Thường không | Cần default hoặc version mới |
| Xóa field | Có rủi ro | Producer/consumer cần migration |
| Đổi tên field | Có rủi ro | Alias hoặc migration |
| Đổi kiểu field | Thường không | Cần converter rõ |
| Thêm enum value | Có điều kiện | Consumer xử lý unknown enum |
| Đổi semantics | Không tự động | Cần language/schema version |
| Đổi ID hoặc reference rule | Có rủi ro | Cần migration graph |

### Explicit versioning

Document có thể chứa version rõ ràng:

~~~json
{
  "schemaVersion": 3,
  "languageVersion": "2.1",
  "rules": []
}
~~~

schemaVersion xác định cấu trúc lưu trữ; languageVersion xác định semantics hoặc cú pháp DSL. Hai version này có thể khác nhau. Một thay đổi cách serialize không nhất thiết là thay đổi ngôn ngữ, và một thay đổi semantics có thể không làm JSON schema đổi hình dạng.

Nếu format có header binary, version có thể được lưu trong header thay vì payload.

## Migration trong quá trình deserialization

Migration chuyển dữ liệu cũ sang mô hình hoặc schema mới. Nó thường được thực hiện sau khi parse cấu trúc cũ và trước khi tạo model nội bộ mới, hoặc bằng một chuỗi chuyển đổi giữa các phiên bản.

Ví dụ:

~~~text
Stored document v1
       |
       v
Deserialize v1 model
       |
       v
Migration v1 -> v2
       |
       v
Migration v2 -> v3
       |
       v
Current model
~~~

Một migration có thể:

- Đổi tên field.
- Chuyển scalar thành object.
- Thêm default.
- Tách hoặc gộp phần tử.
- Chuyển enum cũ sang enum mới.
- Chuyển đơn vị hoặc kiểu số.
- Tạo stable ID cho phần tử cũ.
- Chuyển reference sang cơ chế mới.

### Migration có tính xác định

Với cùng document và cùng migration version, kết quả nên giống nhau. Migration không nên âm thầm gọi dịch vụ bên ngoài hoặc dùng thời gian hệ thống nếu không được đưa vào context.

### Migration có mất dữ liệu hay không

Một số migration có thể không đảo ngược được. Ví dụ, schema cũ lưu một chuỗi không phân biệt display name và identifier, còn schema mới tách hai trường. Nếu không có đủ thông tin, migration cần chọn policy rõ và có thể phát warning.

Nếu dữ liệu quan trọng, nên giữ bản gốc hoặc tạo bản sao trước migration. Không nên ghi đè dữ liệu lưu trữ trước khi migration và validation thành công.

### Migration chain và version support

Có thể hỗ trợ migration trực tiếp từ mọi phiên bản cũ đến mới, hoặc dùng chuỗi migration từng bước. Chuỗi từng bước giảm số lượng mapping riêng nhưng cần đảm bảo mọi bước còn được hỗ trợ và có test.

Một hệ thống lớn có thể giới hạn các version cũ nhất được hỗ trợ. Khi gặp version quá cũ, deserializer nên báo lỗi và hướng dẫn nâng cấp qua công cụ tương thích thay vì đoán.

## Unknown field, unknown enum và extension data

Khi schema thay đổi, document có thể chứa field hoặc giá trị mà consumer chưa biết.

Có ba policy phổ biến:

1. Từ chối ngay.
2. Bỏ qua dữ liệu không biết.
3. Giữ lại dữ liệu không biết để serialize lại hoặc chuyển tiếp.

Policy thứ ba thường được gọi là extension data hoặc unknown-field preservation. Nó hữu ích với proxy, editor hoặc công cụ chỉ sửa một phần document mà cần bảo toàn phần chưa hiểu.

Ví dụ:

~~~json
{
  "name": "Rule A",
  "enabled": true,
  "vendorExtension": {
    "displayColor": "blue"
  }
}
~~~

Một consumer cũ có thể không hiểu vendorExtension nhưng vẫn giữ nguyên object này khi lưu lại. Tuy nhiên, nếu field lạ là một loại action có semantics, giữ dữ liệu mà không thực thi không đồng nghĩa hỗ trợ tính năng đó.

Cần phân biệt:

- Unknown metadata có thể an toàn để giữ.
- Unknown semantic construct cần cảnh báo hoặc từ chối.
- Unknown enum value có thể được giữ dưới dạng unknown value nếu API cho phép.
- Unknown binary field có thể được giữ theo khả năng của format.

## Định danh, tham chiếu ngoài và liên kết tài nguyên

Một model có thể tham chiếu đến resource nằm ngoài document: module, schema, file, secret, service hoặc function registry.

Ví dụ:

~~~json
{
  "rule": "rule-17",
  "moduleRef": "module://pricing/common",
  "schemaRef": "schema://orders/v4"
}
~~~

Deserializer cần phân biệt việc đọc reference string với việc thực sự tải resource. Việc resolve có thể cần quyền, mạng hoặc cache; vì vậy không nên để parser định dạng tự động tải mọi URI xuất hiện trong dữ liệu.

Một resource resolver nên có hợp đồng:

- Scheme hoặc namespace được phép.
- Cách xác thực và phân quyền.
- Timeout và retry.
- Version hoặc content hash.
- Cache và invalidation.
- Hành vi khi resource không tồn tại.
- Chính sách với reference vòng.

Với dữ liệu không tin cậy, chỉ cho phép resolve các scheme và vị trí đã được cấu hình. Một URI tùy ý trong document không nên tự động trở thành yêu cầu truy cập mạng hoặc file system.

## Deserialization an toàn

Dữ liệu lưu trữ và trao đổi có thể đến từ người dùng, dịch vụ khác hoặc hệ thống cũ. Deserializer là ranh giới đầu vào và cần được thiết kế để chống lỗi, lạm dụng tài nguyên và thực thi ngoài ý muốn.

### Không khởi tạo kiểu tùy ý

Một số cơ chế deserialization dựa trên tên class và reflection. Nếu dữ liệu bên ngoài có thể chỉ định class bất kỳ, việc khởi tạo có thể gọi constructor hoặc hook không an toàn.

Nên dùng registry các subtype được phép, discriminator đã kiểm soát và factory có hợp đồng rõ. Không cho document quyết định tùy ý class runtime.

### Giới hạn kích thước và độ sâu

Một document nhỏ có thể tạo object graph rất lớn nếu có alias, reference hoặc expansion. Cần giới hạn:

- Kích thước payload.
- Độ dài chuỗi.
- Số phần tử trong array.
- Số node model.
- Độ sâu lồng nhau.
- Số reference và chu trình.
- Số extension field.
- Thời gian parse và resolve.
- Bộ nhớ dành cho object graph.

Giới hạn cần dựa trên use case và có diagnostics rõ. Khi vượt ngưỡng, deserializer nên dừng có kiểm soát.

### XML và external entity

XML parser cần được cấu hình để không tự tải external entity hoặc DTD nếu use case không yêu cầu. Việc resolve entity có thể dẫn đến đọc tài nguyên cục bộ hoặc truy cập mạng ngoài dự kiến.

Nếu cần DTD hoặc schema ngoài, nên dùng catalog tin cậy và resolver có allowlist thay vì bật truy cập tự do.

### YAML tags và object construction

YAML có thể hỗ trợ tag và cơ chế chuyển đổi sang kiểu cụ thể tùy thư viện. Cần giới hạn tag được chấp nhận và tránh cấu hình cho phép tạo object tùy ý từ dữ liệu.

Với cấu hình DSL, một tập scalar và collection chuẩn thường dễ kiểm soát hơn việc cho phép mọi custom tag.

### Billion laughs và expansion

Một số định dạng hoặc parser hỗ trợ entity, alias hay reference có thể tạo ra lượng dữ liệu sau mở rộng lớn hơn payload ban đầu. Cần giới hạn số lần mở rộng, phát hiện chu trình và đặt ngân sách bộ nhớ.

### Kiểm tra đường dẫn và tài nguyên

Nếu document chứa đường dẫn file, tên module hoặc URI, cần kiểm tra chúng theo policy. Tránh path traversal, tải file ngoài thư mục được phép hoặc truy cập resource của tenant khác.

### Không thực thi trong lúc nạp

Deserialization nên tái tạo dữ liệu và model. Việc gọi function nghiệp vụ, chạy script hoặc thực thi action chỉ vì document chứa một node tương ứng cần nằm trong một bước runtime có kiểm soát riêng.

## Xử lý lỗi và diagnostics

Một pipeline deserialization có thể phát hiện lỗi ở nhiều lớp. Diagnostics nên chỉ ra lỗi nào xảy ra, tại đâu và có thể sửa thế nào.

Các nhóm lỗi:

| Giai đoạn | Ví dụ |
|---|---|
| I/O | Tệp không đọc được, network timeout |
| Decoding | Encoding sai hoặc byte sequence không hợp lệ |
| Parsing | JSON/XML/YAML sai cú pháp |
| Schema | Thiếu field bắt buộc, sai kiểu |
| Type mapping | Giá trị không thể chuyển thành Decimal hoặc enum |
| Reference | ID không tồn tại hoặc sai loại |
| Migration | Không hỗ trợ version hoặc chuyển đổi thất bại |
| Domain validation | Model vi phạm invariant |
| Resource resolution | Module hoặc schema bên ngoài không tải được |
| Initialization | Không thể tạo runtime state |

### Diagnostic có cấu trúc

Một diagnostic có thể chứa:

~~~text
Diagnostic
  code
  severity
  message
  documentId
  path
  line
  column
  byteOffset
  relatedLocations
  stage
  suggestedFix
~~~

Với JSON, path có thể là $.rules[2].condition.right.unit. Với XML, path có thể là XPath hoặc vị trí element. Với binary format, byte offset và field number có thể hữu ích hơn line/column.

### Tách lỗi fatal và recoverable

Một lỗi có thể làm document không thể dùng, ví dụ sai magic header hoặc thiếu field bắt buộc. Một lỗi khác có thể cho phép nạp phần còn lại, ví dụ unknown metadata hoặc một rule bị lỗi trong editor mode.

Cần định nghĩa policy theo mục tiêu:

- Import chính thức: thường yêu cầu toàn bộ document hợp lệ.
- IDE: có thể giữ model một phần và diagnostics.
- Preview: có thể bỏ qua một số phần không hỗ trợ.
- Runtime production: thường không thực thi model có lỗi nghiêm trọng.
- Migration: có thể thu thập nhiều lỗi độc lập để người dùng sửa dữ liệu.

Không nên bỏ qua lỗi rồi trả object mặc định mà không thông báo. Điều đó khiến consumer khó phân biệt dữ liệu gốc với dữ liệu đã được thay thế.

## Streaming và giải tuần tự hóa dữ liệu lớn

Nếu document rất lớn, đọc toàn bộ payload vào bộ nhớ rồi parse thành object graph có thể tốn kém. Streaming deserialization xử lý dữ liệu theo từng token, record hoặc message.

Ví dụ:

~~~text
Input stream
     |
     v
Streaming parser
     |
     v
Record decoder
     |
     v
Validate record
     |
     v
Consume / persist / emit
~~~

Streaming hữu ích khi:

- Import hàng triệu rule hoặc record.
- Đọc event log.
- Xử lý message queue.
- Nạp dữ liệu theo batch.
- Cần giới hạn memory footprint.
- Consumer không cần giữ toàn bộ model cùng lúc.

### Trade-off của streaming

Streaming giảm bộ nhớ nhưng làm một số thao tác khó hơn:

- Forward reference có thể chưa được khai báo khi gặp.
- Validation toàn document cần trạng thái tích lũy.
- Một lỗi ở cuối file có thể xuất hiện sau khi các record trước đã được xử lý.
- Rollback hoặc atomicity cần được thiết kế.
- Một số migration cần biết toàn bộ model.

Có thể dùng hai pha: streaming đọc và lưu record tạm cùng ID; sau khi đọc xong, resolve reference và validate toàn cục. Hoặc xử lý theo batch có transaction để không công bố dữ liệu chưa hoàn chỉnh.

### Backpressure và cancellation

Trong pipeline bất đồng bộ, producer có thể tạo dữ liệu nhanh hơn consumer. Backpressure giới hạn tốc độ đọc để tránh tích lũy hàng đợi lớn. Cancellation cho phép dừng khi người dùng hủy, vượt thời gian hoặc có lỗi fatal.

Deserializer streaming nên xác định rõ resource ownership, đóng stream đúng lúc và không giữ reference đến buffer đã được tái sử dụng.

## Partial deserialization và phục hồi trong IDE

Một editor DSL thường cần hiển thị tài liệu ngay cả khi người dùng đang nhập dở. Document có thể thiếu dấu ngoặc, field hoặc giá trị. Deserializer strict có thể từ chối toàn bộ; editor có thể cần một mô hình một phần.

Một partial model có thể chứa:

- Phần tử đã đọc hợp lệ.
- Placeholder cho field thiếu.
- Unknown node giữ nguyên payload.
- Reference chưa resolve.
- Diagnostics gắn với vùng lỗi.
- Trạng thái incomplete.

Ví dụ, khi document có ba rule và rule thứ hai sai cấu trúc, IDE có thể hiển thị Rule A và Rule C cùng diagnostic tại Rule B nếu parser hỗ trợ recovery theo record. Nhưng import production có thể từ chối toàn bộ để tránh lưu một trạng thái không nhất quán.

Partial model cần có trạng thái rõ ràng để không bị đưa nhầm vào execution engine. Một API có thể trả LoadedModel cùng trạng thái Complete, Partial hoặc Invalid.

## Deserialization và cập nhật một phần

Một số API không gửi toàn bộ model mà chỉ gửi các trường thay đổi. Patch format cần quy định ý nghĩa của missing, null và giá trị cụ thể.

Ví dụ:

~~~json
{
  "name": "Updated rule"
}
~~~

Có thể có nghĩa chỉ cập nhật name, giữ nguyên các trường khác. Trong khi:

~~~json
{
  "description": null
}
~~~

có thể có nghĩa xóa description.

Các chiến lược thường gặp:

- Full replacement: document mới thay thế toàn bộ model.
- Merge patch: chỉ các trường được gửi mới được cập nhật.
- JSON Patch: danh sách thao tác add, remove, replace, move hoặc test.
- Domain command: biểu diễn ý định như RenameRule hoặc DisableRule.

Không nên dùng cùng một deserializer cho full replacement và patch nếu semantics của field thiếu khác nhau. Cần biết trạng thái hiện tại của model và policy merge trước khi áp dụng.

## Round-trip với serialization

Một hệ thống lưu trữ thường cần đọc rồi ghi lại model. Round-trip testing kiểm tra quan hệ giữa serialize và deserialize.

Một quy trình cơ bản:

1. Tạo model nội bộ.
2. Serialize thành document.
3. Deserialize document thành model mới.
4. So sánh hai model theo semantics cần bảo toàn.

~~~text
Model A
  |
  v
Serialize
  |
  v
Document
  |
  v
Deserialize
  |
  v
Model B

Assert: Model A ≈ Model B
~~~

Ký hiệu tương đương không nhất thiết có nghĩa object identity hoặc mọi metadata giống hệt. Hai model có thể khác cache, runtime state hoặc thứ tự field nhưng tương đương về dữ liệu miền.

### Structural round-trip

Kiểm tra cấu trúc: field, collection, kiểu, reference và giá trị được bảo toàn theo schema.

### Semantic round-trip

Kiểm tra hành vi: model sau khi nạp tạo kết quả tương đương khi được đánh giá hoặc thực thi trên cùng context.

### Textual round-trip

Kiểm tra văn bản được bảo toàn nguyên vẹn. Điều này chỉ khả thi khi serializer/deserializer giữ comment, whitespace, thứ tự và chi tiết cú pháp cần thiết, thường cần CST hoặc trivia.

### Canonical serialization

Một serializer canonical tạo biểu diễn chuẩn: thứ tự field hoặc collection theo quy tắc, số được định dạng ổn định, enum dùng tên chuẩn và whitespace nhất quán. Canonical form hữu ích cho diff, hash, cache và chữ ký số.

Tuy nhiên, canonicalization không được làm thay đổi semantics. Không được sắp xếp collection nếu thứ tự phần tử có ý nghĩa.

## Tính xác định và canonicalization

Cùng một model nên được deserialize thành kết quả tương đương khi dùng cùng schema, version và context. Các yếu tố có thể làm kết quả khác nhau:

- Default phụ thuộc môi trường.
- Locale hoặc timezone mặc định.
- Catalog enum hoặc unit thay đổi.
- Reference resolver trả version khác.
- Thứ tự iteration không ổn định.
- Migration phụ thuộc thời gian.
- Coercion khác nhau giữa thư viện.

Để tăng tính xác định:

- Đưa locale và timezone vào context rõ ràng.
- Khóa version schema và catalog.
- Dùng default được định nghĩa trong schema.
- Quy định cách xử lý unknown value.
- Resolve reference theo version hoặc content hash.
- Dùng Decimal hoặc kiểu số có semantics xác định khi cần.
- Tránh side effect trong deserialization.

Canonicalization có thể chuẩn hóa document sau khi nạp, nhưng cần phân biệt normalized model với source text gốc. Nếu cần round-trip nguyên văn, hãy giữ văn bản hoặc token/trivia riêng.

## Lưu trữ, API và message contract

Deserialization thường nằm ở ranh giới giữa các thành phần. Mỗi ranh giới cần một contract rõ.

### File storage

File có thể lưu DSL source, model document hoặc compiled artifact. Cần xác định encoding, schema version, atomic write và cách xử lý file hỏng.

### REST API

API thường dùng JSON hoặc binary payload. Consumer cần kiểm tra content type, version header, authentication context và schema trước khi tạo model.

### Message queue

Message cần có envelope chứa message ID, schema version, producer, timestamp và payload. Consumer cần xử lý duplicate, ordering, retry và poison message.

### Database

Database có thể lưu model thành JSON column, relational tables hoặc binary blob. Deserializer cần biết schema version và cách nạp quan hệ giữa các bảng. Lazy loading có thể ảnh hưởng object graph và transaction.

### Compiled artifact

Artifact có thể chứa IR hoặc bytecode. Khi nạp, runtime cần xác minh magic header, version, target, checksum và runtime ABI trước khi giải mã instruction. Artifact không tương thích không nên được thực thi.

## Tích hợp deserializer vào kiến trúc DSL

Một kiến trúc có thể tách các lớp:

~~~text
Storage / API adapter
        |
        v
Format decoder and parser
        |
        v
Raw document model
        |
        v
Schema/version validator
        |
        v
Typed deserializer
        |
        v
Reference resolver
        |
        v
Domain validator
        |
        v
Canonical DSL model
        |
        +----> Editor
        +----> Compiler
        +----> Interpreter
        +----> Runtime
~~~

Tách adapter khỏi model giúp DSL không bị phụ thuộc vào JSON hoặc YAML. Nếu đổi định dạng lưu trữ, chỉ adapter và mapping liên quan cần thay đổi, trong khi compiler có thể tiếp tục nhận cùng canonical model.

### DTO và domain model

Một số hệ thống dùng Data Transfer Object (DTO) làm kiểu gần với schema bên ngoài, rồi chuyển DTO thành domain model.

DTO có thể chứa field tùy chọn và cấu trúc phù hợp JSON. Domain model có thể dùng kiểu mạnh hơn, constructor có invariant và reference đã resolve.

Cách tách này hữu ích khi:

- API schema khác domain model.
- Cần hỗ trợ nhiều phiên bản document.
- Cần migration trước khi tạo model.
- Cần kiểm tra dữ liệu không tin cậy.
- Domain object không nên được khởi tạo trực tiếp từ payload.

Không phải mọi dự án đều cần hai lớp. Với schema đơn giản và ít thay đổi, có thể deserialize trực tiếp nếu vẫn kiểm soát validation và constructor.

## Ví dụ triển khai khái quát

Giả sử một DSL có model:

~~~text
Rule
  id: RuleId
  name: RuleName
  enabled: Boolean
  condition: Expression
  actions: List<Action>
~~~

Dữ liệu lưu trữ:

~~~json
{
  "schemaVersion": 2,
  "id": "rule-17",
  "name": "Free shipping",
  "enabled": true,
  "condition": {
    "kind": "comparison",
    "operator": "greaterThanOrEqual",
    "left": {
      "kind": "property",
      "path": "order.total"
    },
    "right": {
      "kind": "quantity",
      "value": 500000,
      "unit": "VND"
    }
  },
  "actions": [
    {
      "kind": "setProperty",
      "target": "shipment.fee",
      "value": {
        "kind": "quantity",
        "value": 0,
        "unit": "VND"
      }
    }
  ]
}
~~~

Một deserializer có thể thực hiện logic theo thứ tự:

~~~text
document = parseJson(bytes)
version = readSchemaVersion(document)
rawRule = validateAndReadRuleV2(document, version)

ruleId = parseRuleId(rawRule.id)
name = RuleName(rawRule.name)
condition = deserializeExpression(rawRule.condition)
actions = rawRule.actions.map(deserializeAction)

rule = RuleFactory.create(
  ruleId,
  name,
  rawRule.enabled,
  condition,
  actions
)

resolveReferences(rule, moduleRegistry)
validateDomain(rule, domainSchema)
return rule
~~~

Các hàm trên là pseudocode. Điểm quan trọng là từng bước có trách nhiệm riêng: đọc định dạng, xác định version, chuyển kiểu, dựng object, resolve reference và kiểm tra miền.

Nếu schema version 1 dùng trường targetProperty thay cho target, migration có thể chuẩn hóa dữ liệu trước khi gọi deserializeAction của model hiện tại. Nhờ vậy, domain model không cần chứa mọi biến thể lịch sử của schema.

## Kiểm thử deserialization

Một bộ test nên kiểm tra cả dữ liệu hợp lệ, dữ liệu lỗi, tương thích version và các trường hợp an toàn.

### Test dữ liệu hợp lệ

- Document tối thiểu có đủ trường bắt buộc.
- Document đầy đủ optional field.
- Collection rỗng và collection có nhiều phần tử.
- Mỗi subtype polymorphic.
- Enum và default value.
- Decimal, timestamp, duration và quantity.
- Reference nội bộ và reference liên module.
- Extension metadata được giữ nếu policy yêu cầu.

### Test dữ liệu không hợp lệ

- JSON/XML/YAML sai cú pháp.
- Encoding không hợp lệ.
- Field bắt buộc bị thiếu.
- Field có kiểu sai.
- Enum không nhận diện.
- Number overflow hoặc precision không phù hợp.
- Null ở trường không cho phép.
- Reference không tồn tại.
- Chu trình không được hỗ trợ.
- Schema version không được hỗ trợ.
- Model vi phạm invariant miền.

### Test compatibility và migration

- Nạp document từ mỗi version còn hỗ trợ.
- Field mới có default đúng.
- Field deprecated được xử lý theo policy.
- Unknown field được reject, ignore hoặc preserve đúng.
- Migration giữ semantics.
- Document sau migration serialize theo schema hiện tại.
- Version không được hỗ trợ tạo diagnostic rõ.

### Test security và resource limit

- Payload vượt kích thước tối đa.
- Object lồng quá sâu.
- Array quá lớn.
- Alias hoặc entity expansion vượt giới hạn.
- Discriminator trỏ đến subtype không được phép.
- URI hoặc path không được phép.
- Binary length field sai.
- Parser bị hủy giữa chừng.
- Timeout khi resolve reference.

### Test round-trip và differential

Tạo model, serialize, deserialize rồi so sánh theo semantics. Nếu có nhiều format như JSON và binary, có thể deserialize cùng model từ cả hai format rồi so sánh kết quả. Nếu có hai implementation deserializer, differential test có thể tìm khác biệt trong cách xử lý field, default và reference.

## Những lỗi thiết kế thường gặp

### Coi parse thành công là dữ liệu hợp lệ

Parser chỉ xác nhận cú pháp định dạng. Cần schema validation, type mapping, reference resolution và domain validation.

### Dùng một kiểu dữ liệu cho mọi giá trị

Chuỗi và số primitive không thể giữ đầy đủ ý nghĩa của identifier, money, quantity, timestamp hoặc symbol reference. Dùng kiểu miền khi semantics yêu cầu.

### Không phân biệt missing và null

Điều này có thể làm API patch xóa dữ liệu ngoài ý muốn hoặc áp dụng default sai. Cần quy định riêng trạng thái absent, null và value.

### Dựa vào tên class từ dữ liệu ngoài

Khởi tạo class tùy ý qua reflection có thể mở ra hành vi không an toàn. Dùng discriminator và registry subtype được phép.

### Không quản lý version

Document cũ có thể được diễn giải theo schema mới một cách sai lệch. Cần explicit version và migration có kiểm soát.

### Resolve reference ngay khi đọc từng field

Forward reference hoặc chu trình có thể không resolve được theo thứ tự đọc. Dùng registry và pha resolve riêng khi cần.

### Âm thầm bỏ qua field không biết

Consumer có thể bỏ mất semantics quan trọng. Phân biệt unknown metadata với unknown construct có ý nghĩa thực thi.

### Để deserialization tạo side effect

Việc nạp model không nên tự gửi email, cập nhật database hoặc gọi action nghiệp vụ. Thực thi cần là bước riêng với quyền và resource budget rõ.

### Không giới hạn tài nguyên

Document lồng sâu hoặc payload lớn có thể gây memory exhaustion hoặc CPU exhaustion. Cần giới hạn và cancellation.

### Không giữ diagnostics và source location

Lỗi chỉ được báo là invalid document khiến người dùng khó tìm field sai. Giữ path, line/column hoặc byte offset từ parser và mapper.

## Quy trình thiết kế giải tuần tự hóa cho DSL

Một quy trình có thể thực hiện theo các bước:

1. **Xác định nguồn dữ liệu:** file, API, database, message queue hay artifact.
2. **Chọn format và encoding:** JSON, YAML, XML, binary hoặc format riêng; quy định charset và header.
3. **Thiết kế schema:** field, kiểu, bội số, default, enum, version và extension.
4. **Xác định model đích:** DTO, domain model, AST hoặc canonical model.
5. **Thiết kế mapping:** quy định primitive-to-domain type, subtype, reference và null semantics.
6. **Tách pipeline:** decoding, parsing, schema validation, deserialization, migration, reference resolution và domain validation.
7. **Quản lý compatibility:** xác định backward/forward policy và các version được hỗ trợ.
8. **Thiết kế diagnostics:** mã lỗi, path, source location, stage và cách phục hồi.
9. **Kiểm soát an toàn:** subtype allowlist, resource limits, URI policy và parser configuration.
10. **Xác định streaming:** chọn full-document hay streaming theo kích thước và dependency.
11. **Thiết kế round-trip:** xác định mức structural, semantic hay textual cần bảo toàn.
12. **Kiểm thử:** valid/invalid fixtures, migration, security, limits, round-trip và integration.
13. **Theo dõi vận hành:** metrics về lỗi, kích thước payload, thời gian parse và version producer.

Hợp đồng cần được công bố cho cả producer và consumer. Khi schema thay đổi, cần cập nhật tài liệu, migration và test cùng lúc. Không nên để quy tắc deserialize chỉ tồn tại ngầm trong implementation.

## Kết luận

Giải tuần tự hóa chuyển dữ liệu đã lưu hoặc trao đổi thành object và mô hình có kiểu mà DSL có thể sử dụng. Một pipeline đầy đủ thường bao gồm tiếp nhận dữ liệu, decoding, parsing định dạng, kiểm tra schema và version, dựng kiểu nội bộ, resolve reference, migration và validation miền.

Thiết kế tốt cần phân biệt parsing với validation, missing với null, containment với reference và dữ liệu cấu trúc với semantics miền. Nó cũng cần xử lý polymorphism có kiểm soát, precision, unit, timestamp, unknown field, schema evolution, streaming, diagnostics và giới hạn tài nguyên. Khi dữ liệu đến từ nguồn không tin cậy, deserializer phải kiểm soát subtype, external resource và side effect.

Serialization và deserialization cần có hợp đồng tương thích, nhưng không nhất thiết tạo lại nguyên văn cùng một document. Điều cần bảo toàn phải được xác định rõ: cấu trúc, semantics, metadata hay văn bản. Với schema versioning, migration, validation và round-trip tests được thiết kế có chủ đích, DSL có thể lưu trữ và trao đổi model ổn định qua nhiều phiên bản và nhiều thành phần hệ thống.
