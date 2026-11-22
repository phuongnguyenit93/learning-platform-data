# Tương thích hợp đồng

## 1. Tương thích hợp đồng là gì?

Trong một nền tảng DSL, các thành phần thường trao đổi dữ liệu và gọi nhau thông qua API, service, plugin, compiler interface hoặc message. **Hợp đồng (contract)** mô tả những gì một bên cung cấp và những gì bên còn lại được phép kỳ vọng: cấu trúc dữ liệu, kiểu, quy tắc xử lý, kết quả, lỗi, quyền truy cập và semantics.

**Tương thích hợp đồng (contract compatibility)** là khả năng một phiên bản thành phần tiếp tục giao tiếp và hoạt động đúng với các thành phần khác khi API hoặc schema thay đổi.

Ví dụ, một DSL compiler cung cấp API:

~~~java
CompilationResult compile(SourceDocument source);
~~~

Một plugin generator sử dụng CompilationResult để tạo mã. Nếu compiler đổi tên field, thay kiểu dữ liệu hoặc đổi ý nghĩa của diagnostics, plugin có thể không còn hoạt động dù compiler vẫn build thành công.

Hợp đồng không chỉ là chữ ký method. Nó còn bao gồm:

- Cấu trúc và kiểu của request/response.
- Ý nghĩa của từng field và đơn vị đo.
- Field bắt buộc, tùy chọn, null và default.
- Quy tắc validation và normalization.
- Trạng thái, thứ tự và tính nhất quán của dữ liệu.
- Mã lỗi và cách xử lý lỗi.
- Authentication, authorization và giới hạn sử dụng.
- Idempotency, retry, timeout và cancellation.
- Phiên bản và thời gian hỗ trợ.

Một thay đổi tương thích cần được đánh giá từ góc nhìn của cả producer và consumer. Thêm một field có thể an toàn với consumer bỏ qua field lạ, nhưng lại gây lỗi cho consumer dùng parser nghiêm ngặt. Vì vậy, không có quy tắc đơn giản rằng mọi thay đổi thêm đều tương thích.

## 2. Contract trong DSL API và dữ liệu

Một hệ thống DSL có nhiều loại hợp đồng.

| Loại hợp đồng | Nội dung | Ví dụ |
|---|---|---|
| Public API contract | Interface, method, type và behavior | Compiler API |
| Data contract | Schema, field, kiểu và semantics | AST/IR hoặc JSON model |
| Wire contract | Format và giao thức trao đổi | JSON-RPC, HTTP, message |
| Plugin contract | Capability, lifecycle và extension API | Generator provider |
| Event contract | Event name, payload và ordering | DocumentChanged |
| Configuration contract | Key, type, default và precedence | Project configuration |
| Error contract | Error code, category và recovery | CompilationError |
| Persistence contract | Cấu trúc dữ liệu lưu lâu dài | Process instance record |

Một thay đổi trong model nội bộ có thể không ảnh hưởng contract nếu được che giấu sau API ổn định. Ngược lại, thay đổi một field JSON được public có thể ảnh hưởng nhiều consumer dù chỉ sửa một dòng code.

### 2.1 Producer và consumer

- **Producer/provider:** bên tạo dữ liệu hoặc cung cấp API.
- **Consumer/client:** bên gọi API hoặc đọc dữ liệu.

~~~text
DSL compiler (provider)
       |
       v
CompilationResult
       |
       v
Code generator plugin (consumer)
~~~

Provider có trách nhiệm duy trì contract đã công bố. Consumer có trách nhiệm dùng API theo contract, không dựa vào chi tiết chưa được bảo đảm.

### 2.2 Contract boundary

Ranh giới contract có thể là method call trong cùng process, REST/RPC endpoint, JSON-RPC giữa editor và Language Server, message trên broker, file schema trao đổi giữa compiler và build tool hoặc plugin API giữa framework và extension. Mỗi boundary có cách versioning và triển khai khác nhau.

## 3. Contract gồm cấu trúc và semantics

Một schema có thể mô tả field nhưng không thể tự diễn đạt đầy đủ mọi quy tắc nghiệp vụ.

~~~json
{
  "orderId": "ORD-100",
  "total": 250000,
  "currency": "VND"
}
~~~

Schema có thể xác nhận orderId là string, total là number và currency là string. Nhưng contract còn phải nói total là tổng trước hay sau thuế, đơn vị là đồng hay đơn vị nhỏ nhất, có thể âm không, currency có được thay đổi không và giá trị được làm tròn theo quy tắc nào.

Nếu producer thay đổi total từ số tiền trước thuế sang số tiền sau thuế mà không đổi kiểu, thay đổi đó vẫn có thể phá contract.

### 3.1 Structural compatibility

Structural compatibility liên quan đến hình dạng dữ liệu: tên field, kiểu, cardinality, required/optional, nullability, enum values, nested object và wire encoding.

### 3.2 Semantic compatibility

Semantic compatibility liên quan đến ý nghĩa: đơn vị và timezone, quy tắc rounding, thứ tự kết quả, ý nghĩa trạng thái, điều kiện lỗi, side effect và consistency guarantee.

### 3.3 Behavioral compatibility

Behavioral compatibility xem xét cách API hoạt động: thứ tự xử lý, độ trễ, retry, concurrency và khả năng một request tạo side effect lặp.

Một API có thể giữ nguyên schema nhưng thay đổi behavior đủ lớn để consumer bị hỏng.

## 4. Backward, forward và full compatibility

Ba thuật ngữ thường dùng để mô tả khả năng tương thích khi schema thay đổi.

### 4.1 Backward compatibility

Phiên bản mới của consumer có thể đọc dữ liệu được tạo bởi phiên bản cũ của producer.

~~~text
Old data (v1) ---> New reader (v2)
       compatible
~~~

Ví dụ, consumer v2 vẫn đọc được event được phát bởi producer v1.

### 4.2 Forward compatibility

Consumer cũ có thể đọc dữ liệu được tạo bởi producer mới, thường bằng cách bỏ qua field hoặc giá trị chưa biết theo quy tắc được định nghĩa.

~~~text
New data (v2) ---> Old reader (v1)
       compatible
~~~

### 4.3 Full compatibility

Full compatibility yêu cầu cả hai chiều: reader mới đọc được dữ liệu cũ và reader cũ vẫn đọc được dữ liệu mới.

### 4.4 Compatibility phụ thuộc format

Khả năng bỏ qua field lạ tùy thuộc format và parser:

- JSON consumer có thể bỏ qua property không nhận diện nếu được viết theo cách permissive.
- Protobuf có cơ chế giữ unknown fields trong nhiều runtime, nhưng cách xử lý còn phụ thuộc API và version.
- Một parser YAML có thể chấp nhận key lạ hoặc từ chối theo schema.
- Một enum parser nghiêm ngặt có thể lỗi khi gặp giá trị mới.

Phải kiểm tra hành vi thực tế của consumer, không suy luận chỉ từ tên format.

## 5. Ma trận thay đổi schema

Tác động của thay đổi phụ thuộc vào hướng đọc/ghi và chính sách consumer.

| Thay đổi | Reader mới đọc dữ liệu cũ | Reader cũ đọc dữ liệu mới | Ghi chú |
|---|---|---|---|
| Thêm field optional có default | Thường có | Thường có nếu bỏ qua field lạ | Cần kiểm tra parser |
| Thêm field required | Có thể không | Thường không nếu thiếu field | Dễ phá reader cũ |
| Xóa field | Reader mới có thể không cần field | Có thể không nếu reader cũ yêu cầu | Breaking với consumer phụ thuộc field |
| Đổi tên field | Không nếu thiếu alias/migration | Không nếu writer mới chỉ ghi tên mới | Thường breaking |
| Đổi kiểu field | Thường không | Thường không | Cần migration hoặc field mới |
| Thêm enum value | Reader mới thường đọc giá trị cũ | Reader cũ có thể từ chối giá trị mới | Có thể breaking |
| Thay đổi semantics | Có thể parse được | Có thể parse được | Vẫn có thể breaking |
| Nới validation | Thường an toàn với input cũ | Tùy consumer | Có thể mở rộng miền dữ liệu |
| Siết validation | Dữ liệu cũ có thể bị từ chối | Consumer có thể tạo input không hợp lệ | Rủi ro cao |

Bảng này là hướng dẫn khái quát. Một hệ thống cụ thể cần xét parser, default, validation và behavior của từng consumer.

## 6. Thêm field vào data contract

Thêm field thường là thay đổi phổ biến.

Phiên bản cũ:

~~~json
{
  "id": "ORD-100",
  "status": "PENDING"
}
~~~

Phiên bản mới:

~~~json
{
  "id": "ORD-100",
  "status": "PENDING",
  "source": "mobile"
}
~~~

Nếu consumer cũ bỏ qua field không biết, nó có thể tiếp tục hoạt động. Tuy nhiên, nếu consumer dùng schema validation nghiêm ngặt hoặc deserialize vào model cấm unknown property, request có thể bị từ chối.

### 6.1 Field optional

Field mới nên optional trong giai đoạn đầu nếu consumer cũ chưa gửi nó.

~~~json
{
  "type": "object",
  "properties": {
    "source": {
      "type": "string"
    }
  }
}
~~~

### 6.2 Default

Nếu thiếu field, consumer có thể dùng default:

~~~java
String source = request.source() == null
    ? "unknown"
    : request.source();
~~~

Default cần có semantics rõ. "unknown" không nhất thiết giống "web" hoặc "legacy".

### 6.3 Field có thể null

Optional và nullable không đồng nghĩa:

- Optional: field có thể không xuất hiện.
- Nullable: field có thể xuất hiện với giá trị null.

Một contract có thể cho phép một, cả hai hoặc không cho phép trường hợp nào. Cần thể hiện rõ trong schema.

### 6.4 Giai đoạn nâng cấp

Một cách triển khai an toàn:

1. Consumer mới được triển khai để chấp nhận field optional.
2. Provider bắt đầu gửi field.
3. Consumer cập nhật logic để sử dụng field.
4. Sau khi xác nhận toàn bộ consumer cần thiết đã nâng cấp, mới cân nhắc yêu cầu field.

## 7. Xóa hoặc đổi tên field

Xóa field có thể làm consumer không còn đọc được dữ liệu. Đổi tên thường tương đương xóa tên cũ và thêm tên mới.

Phiên bản cũ:

~~~json
{
  "customerName": "Lan"
}
~~~

Phiên bản mới muốn dùng:

~~~json
{
  "displayName": "Lan"
}
~~~

### 7.1 Expand-and-contract

Chiến lược expand-and-contract chia thay đổi thành các giai đoạn:

~~~text
1. Expand:
   Provider ghi cả tên cũ và tên mới.
   Consumer đọc tên mới, fallback tên cũ.

2. Migrate:
   Các consumer chuyển sang tên mới.
   Dữ liệu cũ được backfill nếu cần.

3. Observe:
   Theo dõi việc sử dụng tên cũ.

4. Contract:
   Ngừng ghi và sau đó xóa tên cũ.
~~~

### 7.2 Dual read

Consumer tạm thời đọc cả hai field:

~~~java
String name = request.displayName() != null
    ? request.displayName()
    : request.customerName();
~~~

Nếu cả hai cùng tồn tại nhưng khác giá trị, contract cần quy định field nào thắng hoặc xem đó là lỗi.

### 7.3 Dual write

Provider có thể ghi cả hai field trong thời gian chuyển đổi. Cần tránh hai giá trị bị lệch nhau; tốt nhất tạo chúng từ cùng một nguồn dữ liệu.

### 7.4 Deprecation

Đánh dấu field cũ deprecated, công bố ngày loại bỏ và cung cấp hướng dẫn chuyển đổi. Không xóa field chỉ vì code provider không còn sử dụng nó; consumer bên ngoài có thể vẫn phụ thuộc.

## 8. Thay đổi kiểu dữ liệu

Đổi kiểu field thường là thay đổi có nguy cơ cao.

~~~json
{
  "amount": "125.50"
}
~~~

đổi thành:

~~~json
{
  "amount": 125.50
}
~~~

Một consumer mong đợi string có thể lỗi khi nhận number. Một consumer dùng floating-point cũng có thể gặp sai số nếu amount đại diện tiền tệ.

### 8.1 Tạo field mới

Có thể thêm amountDecimal hoặc amountMinorUnits, duy trì field cũ trong thời gian chuyển đổi.

### 8.2 Conversion rule

Phải định nghĩa cách chuyển đổi, độ chính xác, overflow và rounding. Không nên ép kiểu nếu có thể mất dữ liệu.

### 8.3 Numeric widening

Đổi integer 32-bit sang integer 64-bit có thể an toàn với một số consumer, nhưng không phải mọi serializer hoặc database column đều hỗ trợ. Cần xét wire type và runtime.

### 8.4 Date và time

Đổi ngày dạng string thành timestamp có thể làm thay đổi timezone semantics. Nên xác định rõ UTC, offset, local date và precision.

### 8.5 Units

Đổi milliseconds thành seconds nhưng giữ tên field có thể không gây lỗi parse nhưng gây lỗi nghiệp vụ. Tên field hoặc metadata nên thể hiện đơn vị.

## 9. Enum và tập giá trị mở rộng

Một enum có thể được khai báo:

~~~text
enum OrderStatus {
  PENDING
  PAID
  CANCELLED
}
~~~

Phiên bản mới thêm:

~~~text
enum OrderStatus {
  PENDING
  PAID
  CANCELLED
  REFUNDED
}
~~~

Consumer cũ có thể gặp REFUNDED mà không biết xử lý thế nào.

### 9.1 Unknown enum value

Consumer có thể giữ raw string hoặc numeric value, chuyển thành UNKNOWN, từ chối payload hoặc dùng fallback theo policy. Đối với trạng thái nghiệp vụ, fallback không nên tự biến trạng thái chưa biết thành một trạng thái cho phép hành động nhạy cảm.

### 9.2 Open enum

Open enum cho phép consumer tiếp nhận giá trị chưa biết và giữ lại giá trị gốc. Cách này hỗ trợ forward compatibility nhưng đòi hỏi consumer có xử lý mặc định an toàn.

### 9.3 Closed enum

Closed enum chỉ chấp nhận tập giá trị đã biết. Cách này giúp validation chặt nhưng thêm enum value thường yêu cầu nâng cấp consumer trước.

### 9.4 Numeric enum

Nếu wire format dùng số, không tái sử dụng numeric value đã bị loại bỏ cho ý nghĩa khác. Giá trị cũ có thể vẫn nằm trong dữ liệu được lưu hoặc message replay.

## 10. Schema evolution trong JSON, Protobuf và Avro

Mỗi định dạng có quy tắc riêng.

### 10.1 JSON

JSON linh hoạt vì object có thể chứa field mới. Nhưng tính tương thích phụ thuộc parser:

- Consumer bỏ qua unknown fields thường dễ tương thích hơn.
- Consumer strict validation có thể từ chối field mới.
- Field optional và default cần được xử lý ở application/schema layer.
- Kiểu dữ liệu JSON thay đổi có thể phá consumer.

JSON Schema có thể mô tả required, properties, enum, numeric constraints và additionalProperties. Giá trị additionalProperties quyết định cách schema xử lý field không khai báo.

### 10.2 Protocol Buffers

Protobuf dùng field number và wire type. Khi sửa schema:

- Không đổi field number đã được dùng.
- Không tái sử dụng field number đã xóa.
- Dùng reserved cho field number hoặc name đã bỏ.
- Thêm field mới thường an toàn nếu có field number mới.
- Thận trọng khi đổi wire type hoặc semantics.
- Không thay đổi ý nghĩa của field chỉ vì wire encoding vẫn parse được.

~~~proto
message Order {
  string id = 1;
  string status = 2;
  reserved 3;
  string source = 4;
}
~~~

### 10.3 Avro

Avro schema resolution có thể dùng writer schema và reader schema. Default trong reader schema có vai trò quan trọng khi đọc dữ liệu được ghi bằng schema cũ.

Khi xóa field, reader có thể bỏ qua field không cần; khi thêm field vào reader, default có thể giúp đọc dữ liệu cũ. Cần kiểm tra quy tắc resolution của schema và version thực tế.

### 10.4 Không chuyển quy tắc giữa các format

Một thay đổi an toàn trong Protobuf chưa chắc an toàn trong JSON Schema hoặc Avro. Dùng compatibility checker phù hợp với đúng serialization format và policy của hệ thống.

## 11. Compatibility của API method

Contract của API gồm signature và behavior.

~~~java
CompilationResult compile(SourceDocument source);
~~~

API mới muốn thêm options:

~~~java
CompilationResult compile(
    SourceDocument source,
    CompilationOptions options
);
~~~

Nếu xóa method cũ ngay, consumer đã biên dịch có thể không còn chạy.

### 11.1 Overload

Có thể thêm overload mới và giữ method cũ:

~~~java
CompilationResult compile(SourceDocument source) {
    return compile(source, CompilationOptions.defaults());
}
~~~

### 11.2 Default method

Trong Java interface, default method có thể giúp thêm behavior mà không buộc mọi implementation cũ triển khai ngay. Tuy nhiên, cần xem xét xung đột method và semantics.

### 11.3 Constructor compatibility

Thêm constructor mới thường ít ảnh hưởng hơn xóa constructor cũ. Với public class, constructor signature là một phần của API.

### 11.4 Return type

Thay return type có thể phá source hoặc binary compatibility. Một cách chuyển đổi có thể là thêm method mới với tên khác và deprecate method cũ.

### 11.5 Checked exception

Thêm checked exception vào method có thể buộc consumer sửa code. Thay đổi loại exception hoặc mã lỗi cũng có thể làm logic recovery sai.

### 11.6 Behavior contract

Nếu compile trước đây trả diagnostics theo source order nhưng phiên bản mới trả theo severity, consumer dựa vào thứ tự cũ có thể thay đổi behavior dù signature không đổi.

## 12. Wire protocol và API compatibility

Khi DSL tool giao tiếp qua HTTP, JSON-RPC hoặc message broker, contract cần bao gồm protocol details.

### 12.1 Request và response

Mô tả method, field, kiểu, required/optional, response và lỗi.

### 12.2 HTTP status và error body

Consumer có thể phân nhánh theo HTTP status hoặc error code. Đổi 404 thành 200 với error object có thể phá client.

### 12.3 JSON-RPC method

Đổi tên method, request parameter hoặc notification semantics có thể làm editor và Language Server không tương thích.

### 12.4 Headers và metadata

Headers như version, content type, correlation ID và idempotency key có thể là một phần của contract.

### 12.5 Pagination

Đổi từ offset pagination sang cursor pagination có thể ảnh hưởng client. Cần định nghĩa thứ tự ổn định, cursor expiration và behavior khi dữ liệu thay đổi.

### 12.6 Ordering

Nếu contract không bảo đảm thứ tự, consumer không nên dựa vào thứ tự hiện tại. Nếu thứ tự quan trọng, cần ghi rõ sort key và tie-breaker.

### 12.7 Rate limits

Thay đổi rate limit hoặc quota có thể là behavioral compatibility issue. API nên trả thông tin limit và retry-after theo contract.

## 13. Error contract

Consumer cần biết lỗi nào có thể xảy ra và cách phản ứng.

~~~json
{
  "code": "SCHEMA_VALIDATION_FAILED",
  "message": "Field orderId is required",
  "details": [
    {
      "path": "orderId",
      "reason": "missing"
    }
  ]
}
~~~

### 13.1 Stable error code

Consumer nên dựa vào error code ổn định, không parse message văn bản dành cho người đọc.

### 13.2 Error categories

Có thể phân loại validation error, authentication/authorization error, not found, conflict, rate limited, timeout, transient service error và internal error.

### 13.3 Thêm error code

Thêm code mới có thể làm consumer cũ lỗi nếu họ dùng exhaustive switch hoặc từ chối code không biết. Cần có UNKNOWN/default branch hoặc version policy.

### 13.4 Thay đổi error semantics

Nếu cùng code nhưng điều kiện xảy ra thay đổi, consumer có thể retry sai hoặc bỏ qua lỗi cần xử lý. Giữ ổn định ý nghĩa code.

### 13.5 Không lộ nội bộ

Error contract không nên tiết lộ stack trace, secret, query nội bộ hoặc thông tin nhạy cảm.

## 14. API compatibility trong DSL compiler và Language Server

Các API của công cụ DSL có consumer cụ thể:

| Provider | Consumer | Contract quan trọng |
|---|---|---|
| Lexer | Parser | Token kind, text, source range |
| Parser | Semantic analyzer | AST node, parent/child, diagnostics |
| Semantic model | Generator | Type, symbol, source mapping |
| Compiler API | Build tool | Options, result, exit status |
| Language Server | Editor client | LSP methods, capabilities, errors |
| Plugin host | Extension | Interface, lifecycle, capability |
| Runtime | Workflow task | Input/output, state, retry |

### 14.1 AST compatibility

Nếu AST public, đổi node class, field hoặc visitor method có thể phá plugin. Có thể cung cấp facade hoặc stable model API để che cấu trúc nội bộ.

### 14.2 Source range

Đổi đơn vị offset từ UTF-16 code units sang Unicode code points có thể làm editor highlight sai dù kiểu field vẫn là integer. Đơn vị và encoding là semantics của contract.

### 14.3 Diagnostics

Consumer có thể dựa vào severity, code, range và related information. Đổi code hoặc ý nghĩa severity có thể phá integration.

### 14.4 LSP capabilities

Server chỉ nên dùng capability client đã quảng bá. Thêm một method mới không có nghĩa mọi client đều hỗ trợ method đó.

### 14.5 Plugin API

Plugin cần biết API version, lifecycle và thread-safety contract. Việc đổi internal class loader hoặc context scope có thể ảnh hưởng extension dù interface công khai không đổi.

## 15. Semantic versioning và API versioning

Semantic Versioning (SemVer) là một quy ước phổ biến:

~~~text
MAJOR.MINOR.PATCH
  2  .  4  .  1
~~~

- **MAJOR:** thay đổi không tương thích.
- **MINOR:** bổ sung tính năng tương thích ngược.
- **PATCH:** sửa lỗi tương thích với contract hiện có.

SemVer chỉ hữu ích nếu dự án định nghĩa rõ public API và thực thi đúng quy tắc.

### 15.1 Public API surface

Không phải mọi class trong artifact đều nhất thiết là public contract. Cần đánh dấu package, module hoặc interface được hỗ trợ chính thức.

### 15.2 API version và product version

Product version có thể thay đổi vì UI, performance hoặc tooling. API version chỉ thay đổi theo chính sách tương thích của contract. Hai số này không nhất thiết giống nhau.

### 15.3 Version trong URL

REST API có thể dùng:

~~~text
/api/v1/orders
/api/v2/orders
~~~

### 15.4 Version trong header hoặc media type

Một số API chọn version qua header hoặc media type. Cần quy định fallback nếu client không gửi version.

### 15.5 Schema version

Payload hoặc persisted data có thể có schemaVersion riêng để reader chọn migration hoặc deserializer.

### 15.6 Version theo capability

Capability negotiation cho phép consumer biết provider hỗ trợ tính năng nào thay vì chỉ so sánh version number.

## 16. Deprecation và chính sách loại bỏ

Khi API cần thay thế, không nên xóa ngay.

Một vòng đời thường gồm:

1. Introduce API mới.
2. Giữ API cũ hoạt động.
3. Đánh dấu API cũ deprecated.
4. Cung cấp migration guide.
5. Theo dõi việc sử dụng API cũ.
6. Thông báo phiên bản dự kiến loại bỏ.
7. Xóa trong major release hoặc thời điểm đã công bố.

### 16.1 Deprecation metadata

~~~java
@Deprecated(since = "3.2", forRemoval = true)
public Result compileLegacy(Source source) {
    return compile(source, Options.defaults());
}
~~~

Annotation giúp compiler cảnh báo nhưng không thay thế tài liệu migration.

### 16.2 Sunset policy

Với API service, có thể công bố ngày sunset, ngày ngừng nhận traffic và cách chuyển endpoint.

### 16.3 Usage telemetry

Theo dõi API cũ được gọi bởi consumer nào, nhưng phải tôn trọng privacy và không thu thập dữ liệu không cần thiết.

### 16.4 Consumer không thể nâng cấp

Một số consumer bên ngoài có vòng đời triển khai dài. Cần cân nhắc adapter, compatibility endpoint hoặc thời gian hỗ trợ phù hợp.

## 17. Migration dữ liệu và API

Khi contract thay đổi, dữ liệu cũ có thể cần được chuyển đổi.

### 17.1 Read-time migration

Reader chuyển đổi dữ liệu cũ khi đọc. Ưu điểm là không cần rewrite toàn bộ ngay; nhược điểm là logic compatibility tồn tại lâu trong runtime.

### 17.2 Write-time migration

Writer ghi theo schema mới, có thể dual-write trong giai đoạn chuyển tiếp. Cần bảo đảm hai dạng dữ liệu nhất quán.

### 17.3 Offline migration

Chạy job chuyển toàn bộ dữ liệu trước khi deploy consumer mới. Cần backup, checkpoint, validation và khả năng resume.

### 17.4 Expand-contract

Mở rộng schema trước, chuyển producer/consumer, quan sát, rồi mới xóa field cũ.

### 17.5 Migration phải có version

Migration nên xác định version nguồn, version đích, cách chuyển đổi, cách xử lý dữ liệu không hợp lệ và tính idempotent khi chạy lại.

### 17.6 Không mất dữ liệu không biết

Nếu reader cũ đọc và ghi lại payload có field mới, nó có thể làm mất field mà nó không hiểu. Với pipeline read-modify-write, cần giữ unknown fields hoặc tránh ghi đè toàn bộ object.

## 18. Contract testing

Contract test kiểm tra provider và consumer có thống nhất về hợp đồng.

### 18.1 Provider contract test

Kiểm tra provider chấp nhận request hợp lệ, từ chối request sai theo error contract, trả field và kiểu đúng, giữ semantics/status code và tuân thủ authentication/authorization.

### 18.2 Consumer contract test

Consumer xác định những behavior nó thực sự cần từ provider. Test có thể dùng mock server hoặc contract artifact để kiểm tra assumption.

### 18.3 Consumer-driven contract testing

Consumer công bố expectation. Provider chạy các expectation đó trong pipeline để xác nhận thay đổi không phá consumer đã đăng ký.

### 18.4 Schema compatibility check

Có thể so schema mới với schema cũ bằng compatibility checker của format hoặc registry. Cần chọn policy backward, forward hoặc full phù hợp.

### 18.5 Golden fixtures

Lưu request/response hoặc serialized payload đại diện để kiểm tra reader mới vẫn đọc được dữ liệu đã phát hành trước đó.

### 18.6 Integration test

Chạy provider và consumer thực tế với phiên bản được hỗ trợ, thay vì chỉ test hai bên riêng lẻ.

### 18.7 Test semantics

Schema checker không phát hiện mọi thay đổi semantics. Cần test đơn vị, rounding, ordering, state transitions, error handling và side effects.

## 19. Compatibility matrix và quản lý phiên bản

Một sản phẩm có thể có nhiều phiên bản provider và consumer cùng tồn tại.

| Provider | Consumer | Kết quả |
|---|---|---|
| API v1 | Client v1 | Supported |
| API v2 | Client v1 | Supported qua compatibility layer |
| API v2 | Client v2 | Native |
| API v3 | Client v1 | Unsupported |
| API v3 | Client v2 | Cần kiểm tra policy |

### 19.1 Ma trận được công bố

Nêu rõ version nào được hỗ trợ và trong thời gian nào. Không để consumer phải thử ngẫu nhiên.

### 19.2 N-1 hoặc N-2 support

Một số hệ thống hỗ trợ phiên bản hiện tại và một hoặc hai phiên bản trước. Chính sách cần dựa trên khả năng vận hành và vòng đời consumer.

### 19.3 Compatibility layer

Adapter có thể chuyển request cũ sang API mới hoặc chuyển response mới về format cũ.

### 19.4 Chi phí duy trì

Mỗi compatibility path làm tăng code, test và support burden. Nên đặt thời hạn loại bỏ và metrics để biết khi nào có thể kết thúc.

## 20. Rollout an toàn khi thay đổi contract

Một thay đổi API nên được triển khai theo thứ tự giảm rủi ro.

~~~text
Prepare:
  Deploy consumer that accepts old + new contract

Expand:
  Deploy provider that supports both forms

Migrate:
  Move traffic and stored data to new form

Observe:
  Check errors and legacy usage

Contract:
  Remove old form after support window
~~~

### 20.1 Consumer-first rollout

Khi provider bắt đầu gửi field mới, consumer phải có khả năng xử lý nó hoặc bỏ qua an toàn. Vì vậy, thường triển khai consumer tương thích trước.

### 20.2 Provider dual support

Provider có thể tạm thời chấp nhận request cũ và mới. Nếu response cũng thay đổi, có thể negotiate version hoặc content type.

### 20.3 Canary

Triển khai với một nhóm consumer nhỏ, quan sát lỗi parse, validation và behavior trước khi mở rộng.

### 20.4 Rollback

Rollback application không tự động rollback schema hoặc dữ liệu đã migrate. Cần bảo đảm phiên bản cũ vẫn có thể đọc trạng thái dữ liệu hiện tại trong giai đoạn rollback.

### 20.5 Feature flag

Feature flag có thể bật hành vi mới theo consumer hoặc tenant. Cần ghi nhận flag state vì nó ảnh hưởng semantics.

## 21. Contract trong plugin và extension API

Plugin API là hợp đồng giữa framework host và extension.

Contract nên quy định interface và type public, plugin ID/API version, capability cung cấp/yêu cầu, lifecycle initialize/activate/dispose, thread safety, cancellation và timeout, error isolation, configuration schema và quyền truy cập.

### 21.1 Binary compatibility

Trong Java, thay đổi method signature, constructor, visibility hoặc superclass có thể khiến plugin đã biên dịch không chạy.

### 21.2 Class loading

Plugin có thể dùng dependency khác version. Class loader strategy và package ownership cần được công bố.

### 21.3 Capability negotiation

Host có thể công bố capability như semantic-model-v2 hoặc cancellation-support. Plugin kiểm tra capability trước khi dùng tính năng.

### 21.4 Lifecycle compatibility

Nếu host đổi thời điểm gọi dispose hoặc bắt đầu chạy callback song song, plugin có thể lỗi dù method signatures không đổi. Lifecycle là một phần của behavior contract.

## 22. Contract trong event và message

Event là dữ liệu được phát ra để consumer xử lý độc lập.

~~~json
{
  "eventId": "evt-123",
  "eventType": "OrderSubmitted",
  "schemaVersion": 2,
  "occurredAt": "2026-11-15T03:00:00Z",
  "aggregateId": "ORD-100",
  "aggregateVersion": 7,
  "payload": {
    "orderId": "ORD-100"
  }
}
~~~

### 22.1 Event name

Event name nên mô tả sự kiện đã xảy ra, không phải lệnh yêu cầu thực hiện.

### 22.2 Immutable event

Event đã phát thường được xem là dữ liệu lịch sử. Không nên thay đổi ý nghĩa payload cũ sau khi consumer đã xử lý.

### 22.3 Schema evolution

Consumer cần xử lý field mới và event version mới theo policy. Nếu thay đổi semantics lớn, có thể phát event type mới.

### 22.4 Ordering và delivery

Contract cần nêu guarantee về ordering, at-least-once hoặc at-most-once, deduplication và replay.

### 22.5 Event replay

Consumer có thể nhận lại event cũ khi rebuild projection. Handler phải biết replay có được phép tạo side effect hay không.

## 23. Contract của configuration và persisted data

Configuration và dữ liệu lưu trữ có vòng đời dài hơn một request.

### 23.1 Configuration schema

Thêm required key có thể khiến project config cũ không còn load được. Nên có default, migration hoặc giai đoạn optional.

### 23.2 Persisted process state

Process instance có thể tồn tại nhiều ngày hoặc nhiều tháng. Khi engine nâng cấp, state cũ cần được đọc hoặc migrate.

### 23.3 Database schema

Thay đổi column, constraint hoặc index cần phối hợp với các phiên bản application đang chạy. Expand-contract cũng hữu ích với database migration.

### 23.4 Serialized AST hoặc IR

Nếu AST/IR được cache hoặc lưu ra file, schema của nó cần version. Không nên giả định cache được tạo bởi compiler version trước luôn đọc được.

### 23.5 Cache compatibility

Cache key cần chứa compiler, schema, plugin và configuration version có ảnh hưởng kết quả. Nếu không, dữ liệu cũ có thể được dùng với semantics mới.

## 24. Compatibility và security

Giữ tương thích không có nghĩa phải giữ mọi behavior nguy hiểm.

### 24.1 Security fix

Một bản sửa bảo mật có thể từ chối input trước đây được chấp nhận. Đây là thay đổi behavior nhưng có thể cần thiết.

### 24.2 Strict validation

Siết validation có thể làm dữ liệu cũ không còn hợp lệ. Cần đánh giá mức độ rủi ro và cung cấp diagnostic/migration.

### 24.3 Authentication change

Đổi token format hoặc yêu cầu scope mới ảnh hưởng consumer. Cần hỗ trợ chuyển tiếp và thông báo trước khi thu hồi cơ chế cũ.

### 24.4 Authorization

Thay đổi quyền có thể làm request trước đây thành công nay bị từ chối. Cần phân biệt breaking change có chủ ý với regression.

### 24.5 Không giữ backdoor vì compatibility

Không nên duy trì cơ chế xác thực yếu chỉ để hỗ trợ client cũ không còn được quản lý. Dùng sunset plan và migration an toàn.

## 25. Những sai lầm thường gặp

### Chỉ kiểm tra method signature

API vẫn compile nhưng semantics, ordering hoặc error behavior đã đổi.

**Cách khắc phục:** xem contract ở cả cấu trúc, behavior và semantics.

### Xóa field ngay khi provider không dùng

Consumer bên ngoài vẫn có thể phụ thuộc field.

**Cách khắc phục:** deprecate, dual-read/dual-write, quan sát và loại bỏ theo thời hạn.

### Thêm enum value mà không chuẩn bị consumer

Consumer dùng exhaustive switch có thể lỗi.

**Cách khắc phục:** unknown-value handling hoặc nâng cấp consumer trước.

### Đổi đơn vị nhưng giữ tên field

Payload parse được nhưng tính toán sai.

**Cách khắc phục:** field mới, unit metadata và migration.

### Cho rằng JSON luôn forward-compatible

Strict schema hoặc deserializer có thể từ chối field lạ.

**Cách khắc phục:** test parser và policy unknown fields của từng consumer.

### Không version hóa persisted data

Engine mới có thể đọc sai process state hoặc cache cũ.

**Cách khắc phục:** schema version, reader compatibility và migration.

### Không kiểm tra consumer thực tế

Provider team không biết những consumer nào đang dùng API cũ.

**Cách khắc phục:** consumer inventory, contract tests và usage telemetry.

### Rollback application nhưng quên dữ liệu

Phiên bản cũ không đọc được schema đã migrate.

**Cách khắc phục:** thiết kế rollout sao cho old reader tiếp tục đọc được trong rollback window.

### Duy trì compatibility vô thời hạn

Adapter và nhánh cũ làm tăng chi phí và bề mặt lỗi.

**Cách khắc phục:** công bố support window, theo dõi usage và xóa theo kế hoạch.

## 26. Quy trình thay đổi một contract

Khi cần thay đổi DSL API hoặc data schema, có thể thực hiện:

1. **Xác định contract:** API, schema, event, plugin, configuration hay persisted state.
2. **Liệt kê consumer:** service, plugin, editor, build tool và phiên bản đang sử dụng.
3. **Mô tả thay đổi:** field, type, semantics, behavior hoặc error.
4. **Phân tích chiều tương thích:** backward, forward hoặc full.
5. **Kiểm tra tác động:** parser, generated code, database, cache và event replay.
6. **Chọn chiến lược:** optional field, alias, overload, adapter, version endpoint hoặc migration.
7. **Cập nhật consumer:** chấp nhận dạng cũ và mới trước khi provider chuyển đổi.
8. **Cập nhật provider:** dual support hoặc phát contract mới.
9. **Kiểm thử:** schema checker, provider/consumer contract, golden fixtures và integration.
10. **Triển khai canary:** quan sát error rate và legacy usage.
11. **Migrate dữ liệu:** backfill hoặc read-time migration khi cần.
12. **Deprecate:** thông báo và theo dõi consumer còn dùng dạng cũ.
13. **Contract:** loại bỏ dạng cũ sau support window.
14. **Ghi nhận version:** cập nhật tài liệu, compatibility matrix và migration guide.

## 27. Ví dụ tổng hợp: đổi CompilationResult

Giả sử compiler v1 trả:

~~~json
{
  "success": true,
  "errors": [],
  "generatedFiles": [
    "build/Policy.java"
  ]
}
~~~

Consumer gồm IDE plugin, CLI và build service.

### 27.1 Nhu cầu thay đổi

Compiler muốn bổ sung warnings, diagnostics có source range và artifact metadata:

~~~json
{
  "success": true,
  "errors": [],
  "warnings": [],
  "diagnostics": [],
  "artifacts": [
    {
      "path": "build/Policy.java",
      "kind": "JAVA_SOURCE"
    }
  ]
}
~~~

### 27.2 Expand

Provider thêm warnings, diagnostics và artifacts như field optional. Trong thời gian chuyển đổi, vẫn trả generatedFiles để consumer cũ tiếp tục hoạt động.

Consumer mới được triển khai để đọc artifacts và fallback sang generatedFiles nếu cần.

### 27.3 Migrate

IDE plugin, CLI và build service lần lượt chuyển sang artifacts. Contract test chạy với payload cũ và mới.

### 27.4 Observe

Provider theo dõi consumer version và số lần truy cập đường compatibility cũ. Nếu còn consumer dùng generatedFiles, chưa xóa field.

### 27.5 Contract

Sau support window đã công bố, provider có thể loại bỏ generatedFiles trong một major API version mới. Consumer cũ phải nâng cấp hoặc dùng adapter tương thích.

### 27.6 Semantic compatibility

Trong quá trình đổi, cần bảo đảm success vẫn có cùng ý nghĩa, errors không bị mất, thứ tự diagnostics được xác định và artifact path vẫn có quy tắc tương đối/tuyệt đối rõ ràng. Chỉ thêm field không đủ để chứng minh tương thích.

## 28. Câu hỏi tự kiểm tra

1. Hợp đồng API và dữ liệu bao gồm những gì ngoài method signature?
2. Phân biệt producer/provider và consumer/client.
3. Structural, semantic và behavioral compatibility khác nhau như thế nào?
4. Backward, forward và full compatibility mô tả những chiều nào?
5. Vì sao thêm một field có thể vẫn phá consumer?
6. Optional, nullable và default khác nhau như thế nào?
7. Expand-and-contract giúp đổi tên field ra sao?
8. Vì sao đổi kiểu dữ liệu thường cần field mới hoặc migration?
9. Consumer nên xử lý enum value chưa biết như thế nào?
10. JSON, Protobuf và Avro có quy tắc schema evolution khác nhau ra sao?
11. Overload và default method có thể giúp duy trì API Java như thế nào?
12. Error code ổn định quan trọng hơn message văn bản ở điểm nào?
13. SemVer, API version và schema version khác nhau ra sao?
14. Deprecation window cần thông tin gì?
15. Consumer-driven contract test kiểm tra điều gì?
16. Vì sao schema checker không phát hiện mọi thay đổi semantics?
17. Rollout consumer-first và provider dual support giảm rủi ro thế nào?
18. Persisted process state và cache cần được version hóa vì sao?
19. Security fix có thể tạo breaking behavior như thế nào?
20. Những bước nào cần hoàn tất trước khi xóa một field deprecated?

Tương thích hợp đồng giúp các thành phần DSL phát triển độc lập mà vẫn giao tiếp đúng. Khi contract mô tả cả cấu trúc lẫn semantics, thay đổi được phân loại theo chiều tương thích, consumer được nâng cấp có kế hoạch và dữ liệu được version hóa, hệ thống có thể tiến hóa mà không làm gián đoạn các tích hợp đang hoạt động.
