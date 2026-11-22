# Tài liệu tham chiếu

**Tài liệu tham chiếu** (*reference documentation*) là phần tài liệu mô tả chính xác các thành phần, cú pháp, quy tắc và hành vi mà người dùng có thể tra cứu khi làm việc với một hệ thống. Với một ngôn ngữ đặc tả miền (*Domain Specific Language – DSL*), tài liệu tham chiếu giúp người viết biết construct nào tồn tại, cách viết hợp lệ, kiểu dữ liệu được hỗ trợ, ý nghĩa của từng thuộc tính, giới hạn áp dụng và kết quả mà runtime tạo ra.

Reference documentation thường được sử dụng khi người đọc đã biết mình muốn làm gì và cần xác định cách dùng một thành phần cụ thể. Ví dụ, người viết muốn khai báo một endpoint có thể tra cứu reference của block endpoint để biết các field hợp lệ, type, default, required condition và ví dụ.

Một DSL có thể có phần tham chiếu như sau:

~~~text
endpoint "catalog" {
    scheme = "https"
    hostname = "catalog.example.com"
    port = 443
    basePath = "/api/v2"
}
~~~

Tài liệu tham chiếu cho construct endpoint cần giải thích mục đích, vị trí được phép khai báo, cú pháp và cấu trúc con, các thuộc tính hợp lệ, kiểu dữ liệu và giá trị mặc định, quy tắc validation, quan hệ với construct khác và ví dụ hợp lệ cũng như lỗi thường gặp.

Reference documentation tốt phải chính xác, dễ tra cứu, nhất quán với phiên bản DSL đang sử dụng và đủ cụ thể để người đọc không phải suy đoán semantics.

## 1. Vai trò của tài liệu tham chiếu

DSL thường có nhiều thành phần: keyword, block, expression, type, function, operator, annotation, module và configuration option. Người dùng cần một nguồn thông tin có cấu trúc để tra cứu từng thành phần.

Reference documentation phục vụ các mục đích:

- Xác định cú pháp hợp lệ.
- Tra cứu tên, kiểu và ý nghĩa của thuộc tính.
- Biết default value và required condition.
- Hiểu phạm vi và context mà construct được phép xuất hiện.
- Hiểu semantics khi runtime thực thi.
- Biết giới hạn, constraint và lỗi có thể phát sinh.
- Tra cứu API, function, operator và type có sẵn.
- Kiểm tra khả năng tương thích giữa các phiên bản.
- Hỗ trợ IDE, code completion và diagnostics.
- Làm cơ sở cho code review và bảo trì DSL.

### 1.1. Reference và hướng dẫn học

Reference và tutorial có mục đích khác nhau.

| Loại tài liệu | Câu hỏi chính | Cách trình bày |
|---|---|---|
| Tutorial | Tôi bắt đầu từ đâu? | Hướng dẫn theo từng bước |
| How-to guide | Làm thế nào để hoàn thành một tác vụ? | Quy trình giải quyết vấn đề |
| Explanation | Vì sao hệ thống được thiết kế như vậy? | Khái niệm và lý do |
| Reference | Construct này chính xác hoạt động ra sao? | Định nghĩa có cấu trúc |

Ví dụ, tutorial có thể hướng dẫn tạo API đầu tiên. Reference mô tả đầy đủ mọi field của block api, type của từng field, default và validation.

### 1.2. Reference và specification

Specification định nghĩa contract chính thức của ngôn ngữ hoặc hệ thống. Reference documentation diễn giải contract đó để người dùng tra cứu.

Nếu reference khác specification, cần xác định nguồn nào là authoritative. Với DSL có compiler, grammar và semantic rule nên là nguồn chính thức; tài liệu được sinh từ metadata có thể giảm sai lệch.

### 1.3. Reference không phải danh sách tên

Chỉ liệt kê keyword mà không giải thích type, context và semantics là chưa đủ. Người dùng cần biết construct được dùng ở đâu, có ảnh hưởng gì và điều kiện nào làm nó hợp lệ.

## 2. Các nhóm nội dung trong DSL reference

Một bộ tài liệu tham chiếu thường gồm nhiều nhóm.

~~~text
DSL Reference
├── Language overview
├── Grammar and syntax
├── Statements and blocks
├── Expressions and operators
├── Types and literals
├── Built-in functions
├── Standard library
├── Modules and imports
├── Annotations and metadata
├── Configuration options
├── Runtime semantics
├── Host APIs and extensions
├── Diagnostics and errors
└── Version compatibility
~~~

Không phải DSL nào cũng cần đủ mọi nhóm. Cấu trúc nên phản ánh mô hình thực tế của ngôn ngữ.

### 2.1. Language overview

Phần overview giải thích phạm vi DSL, file extension, cách parse, compile hoặc execute và những khái niệm nền tảng.

### 2.2. Grammar

Grammar mô tả cấu trúc cú pháp: token, expression, statement, block và quy tắc lồng nhau.

### 2.3. Construct reference

Mỗi construct có một trang hoặc mục riêng mô tả syntax, fields, semantics và examples.

### 2.4. Type và literal reference

Mô tả primitive type, collection type, domain type, literal syntax, conversion và compatibility.

### 2.5. Function và standard library

Tra cứu signature, parameter, return type, side effect, exception và ví dụ.

### 2.6. Runtime reference

Giải thích evaluation order, scope, lifecycle, error handling, concurrency và resource behavior.

### 2.7. Host integration reference

Mô tả các API hoặc binding mà DSL sử dụng từ host application.

## 3. Mô tả một construct

Mỗi construct nên có một cấu trúc thống nhất để người đọc nhanh chóng tìm thấy thông tin.

Một mục reference cho block service có thể dùng bố cục:

1. Tên và mục đích.
2. Syntax.
3. Context hợp lệ.
4. Fields và nested blocks.
5. Type và default.
6. Semantics.
7. Validation constraints.
8. Interaction với construct khác.
9. Ví dụ.
10. Version và compatibility.

### 3.1. Tên construct

Tên cần khớp chính xác với DSL. Nếu keyword phân biệt hoa thường, tài liệu phải giữ đúng casing.

### 3.2. Mục đích

Mô tả ngắn construct dùng để làm gì. Nên nói rõ tác động của nó đối với chương trình.

### 3.3. Syntax summary

~~~text
service <name> {
    endpoint = <Endpoint>
    timeout = <Duration>
    enabled = <Boolean>
}
~~~

Syntax summary nên thể hiện required field, optional field, nested block và vị trí của expression.

### 3.4. Context

Construct có thể chỉ được phép ở top-level, trong module, trong block khác hoặc trong một phase cụ thể. Reference cần nêu rõ context hợp lệ.

### 3.5. Semantics

Giải thích runtime làm gì khi construct được sử dụng. Cần phân biệt syntax acceptance với hành vi thực thi.

### 3.6. Constraints

Mô tả giới hạn như port range, timeout range, uniqueness, cardinality hoặc điều kiện phụ thuộc field khác.

### 3.7. Examples

Ví dụ nên ngắn, hoàn chỉnh và thể hiện đúng một hoặc vài quy tắc cần tra cứu. Nếu cần nhiều biến thể, tách thành các ví dụ có tiêu đề.

## 4. Syntax và grammar reference

Grammar là nền tảng của tài liệu tham chiếu ngôn ngữ.

### 4.1. EBNF và PEG

Có thể dùng EBNF, PEG hoặc notation riêng để mô tả grammar. Cần giải thích notation một lần và dùng nhất quán.

Ví dụ EBNF minh họa:

~~~text
ServiceDecl  = "service", Identifier, "{", ServiceBody, "}" ;
ServiceBody  = { ServiceMember } ;
ServiceMember = EndpointDecl | TimeoutDecl | EnabledDecl ;
EndpointDecl = "endpoint", "=", StringLiteral ;
TimeoutDecl  = "timeout", "=", DurationLiteral ;
EnabledDecl  = "enabled", "=", BooleanLiteral ;
~~~

Đây chỉ là grammar minh họa. Grammar thực tế cần phản ánh parser đang triển khai.

### 4.2. Terminal và non-terminal

Terminal là token cụ thể như keyword, dấu ngoặc hoặc literal. Non-terminal là cấu trúc được định nghĩa từ các thành phần khác.

### 4.3. Optional và repetition

Notation cần cho biết phần nào optional, phần nào lặp lại và giới hạn số lần lặp. Ví dụ collection có thể cho phép zero-or-more hoặc one-or-more item.

### 4.4. Precedence và associativity

Grammar hoặc operator reference cần mô tả precedence và associativity để người đọc hiểu expression được parse như thế nào.

~~~text
a + b * c
~~~

Nếu multiplication có precedence cao hơn addition, expression được hiểu là a cộng với kết quả b nhân c.

### 4.5. Whitespace và comment

Tài liệu cần nói rõ newline, indentation, whitespace và comment có ảnh hưởng cú pháp không. Nếu indentation không có ý nghĩa, không nên khiến ví dụ ngụ ý rằng indentation bắt buộc.

### 4.6. Reserved keyword

Liệt kê keyword không thể dùng làm identifier hoặc nêu quy tắc escape nếu DSL hỗ trợ.

### 4.7. Grammar version

Grammar có thể thay đổi giữa các phiên bản. Nên ghi version hoặc link đến grammar đúng với compiler release.

## 5. Field reference

Field reference là phần quan trọng trong DSL cấu hình.

Một bảng field thường có:

| Cột | Nội dung |
|---|---|
| Field | Tên thuộc tính |
| Type | Kiểu dữ liệu |
| Required | Có bắt buộc không |
| Default | Giá trị mặc định |
| Description | Ý nghĩa |
| Constraints | Giới hạn hoặc điều kiện |
| Since | Phiên bản bắt đầu hỗ trợ |
| Deprecated | Phiên bản bị đánh dấu deprecated nếu có |

### 5.1. Required field

Required field phải xuất hiện để construct hợp lệ. Nếu field chỉ bắt buộc khi field khác được bật, cần ghi điều kiện đó.

Ví dụ:

~~~text
tls.enabled = true
~~~

Khi TLS được bật, certificate reference có thể trở thành bắt buộc ở server-side configuration.

### 5.2. Optional field

Optional field có thể bỏ qua. Reference cần giải thích hành vi khi không khai báo.

### 5.3. Default value

Default cần ghi chính xác và phân biệt:

- Default do language specification quy định.
- Default do compiler cung cấp.
- Default phụ thuộc environment.
- Default được resolve tại runtime.

Không nên mô tả một giá trị là default nếu thực tế nó đến từ environment variable hoặc host application.

### 5.4. Nullable field

Nullable nghĩa là field có thể nhận null. Optional nghĩa là field có thể không xuất hiện. Hai khái niệm này không giống nhau và cần được mô tả riêng.

### 5.5. Field alias

Nếu DSL hỗ trợ alias hoặc tên legacy, cần nêu alias nào được chấp nhận và quy tắc ưu tiên khi nhiều tên cùng xuất hiện.

### 5.6. Unknown field

Reference nên nói rõ compiler xử lý field không biết như thế nào: báo lỗi, warning, bỏ qua hay chuyển cho extension. Với cấu hình an toàn, fail-fast thường giúp phát hiện typo.

## 6. Type reference

Type reference mô tả loại giá trị mà DSL hỗ trợ và cách các type tương tác.

### 6.1. Primitive types

Các type thường gặp:

- Boolean.
- Integer.
- Decimal hoặc floating-point.
- String.
- Character nếu ngôn ngữ hỗ trợ.
- Null hoặc Unit/Void.

### 6.2. Collection types

Array, list, set và map có thể có semantics khác nhau về thứ tự, duplicate và mutability.

### 6.3. Domain types

DSL chuyên biệt có thể định nghĩa type như Money, Duration, Endpoint, Path, Date, Timestamp, ResourceId hoặc RiskLevel.

### 6.4. Generic type

Nếu DSL hỗ trợ generic, reference cần giải thích type parameter, constraint và type inference.

### 6.5. Union và optional type

Một type có thể cho phép nhiều biến thể hoặc biểu diễn giá trị có thể vắng mặt. Cần nêu cách pattern matching hoặc kiểm tra nullability.

### 6.6. Type conversion

Mô tả conversion implicit và explicit, thứ tự ưu tiên overload và trường hợp conversion thất bại.

### 6.7. Equality và ordering

Reference cần giải thích phép so sánh theo type. Ví dụ equality của string, date và domain object có thể có semantics khác nhau.

### 6.8. Serialization

Nếu type có thể được lưu hoặc truyền qua host API, cần mô tả representation khi serialize, timezone, precision và format.

## 7. Literal reference

Literal là cách viết trực tiếp một giá trị trong source DSL.

### 7.1. String literal

~~~text
name = "catalog"
~~~

Reference cần mô tả quote style, escape sequence, multiline string và encoding.

### 7.2. Numeric literal

~~~text
retryCount = 3
ratio = 0.75
~~~

Cần nêu range, precision, exponent notation và cách xử lý overflow.

### 7.3. Boolean và null

~~~text
enabled = true
fallback = null
~~~

Quy định casing và context hợp lệ của literal.

### 7.4. Duration literal

~~~text
timeout = 250ms
interval = 5s
~~~

Cần ghi đơn vị hỗ trợ, cách làm tròn và giới hạn giá trị.

### 7.5. Date và time literal

Mô tả format, timezone, calendar system và cách xử lý giá trị không hợp lệ hoặc daylight saving time.

### 7.6. Path và endpoint literal

Nếu DSL có type chuyên biệt, cần giải thích cách chuẩn hóa path, URL encoding và relative path resolution.

## 8. Operator reference

Operator reference giải thích phép toán có thể sử dụng trong expression.

### 8.1. Arithmetic operators

| Operator | Ý nghĩa |
|---|---|
| + | Cộng hoặc nối chuỗi tùy type |
| - | Trừ |
| * | Nhân |
| / | Chia |
| % | Chia lấy dư nếu được hỗ trợ |

### 8.2. Comparison operators

~~~text
==  !=  <  <=  >  >=
~~~

Mô tả type compatibility và cách xử lý null hoặc incomparable value.

### 8.3. Logical operators

~~~text
and
or
not
~~~

Nêu short-circuit semantics, precedence và evaluation order.

### 8.4. Membership operators

~~~text
country in allowedCountries
~~~

Giải thích type của collection, equality semantics và độ phức tạp nếu phụ thuộc cấu trúc dữ liệu.

### 8.5. Null-coalescing và optional access

Nếu DSL hỗ trợ, giải thích cách fallback hoặc truy cập an toàn vào field có thể null.

### 8.6. Precedence table

Reference nên có bảng precedence từ cao xuống thấp và nêu associativity. Điều này tránh người đọc đoán thứ tự đánh giá.

## 9. Function và built-in API reference

Mỗi function nên có signature và semantics rõ ràng.

Ví dụ:

~~~text
parseDate(value: String, format: String = "ISO") -> Date
~~~

Thông tin cần mô tả:

- Tên function.
- Signature.
- Parameter và type.
- Required/optional parameter.
- Default argument.
- Return type.
- Side effect.
- Exception hoặc error result.
- Thread-safety nếu có liên quan.
- Version introduced và deprecation.
- Example.

### 9.1. Overload

Nếu một tên function có nhiều overload, cần trình bày cách compiler chọn overload và xử lý ambiguity.

### 9.2. Named argument

Nếu function hỗ trợ named argument, nêu quy tắc casing, thứ tự và cách kết hợp với positional argument.

### 9.3. Variadic parameter

Mô tả function nhận số lượng argument thay đổi và cách type được suy ra.

### 9.4. Side effect

Function có thể thuần hoặc có side effect. Reference nên ghi rõ function có đọc state, ghi dữ liệu, gọi network, tạo file hoặc thay đổi môi trường hay không.

### 9.5. Error behavior

Nêu function throw exception, trả error value, trả null hay tạo diagnostic. Người dùng cần biết lỗi được truyền lên caller thế nào.

### 9.6. Complexity note

Nếu có ích, nêu complexity hoặc đặc tính hiệu năng quan trọng. Ví dụ lookup trong set thường khác scan list. Không nên đưa cam kết hiệu năng tuyệt đối nếu implementation không bảo đảm.

## 10. Standard library reference

Standard library là tập hợp module, function, type và constant có sẵn cho mọi hoặc phần lớn chương trình DSL.

### 10.1. Module organization

~~~text
std
├── collections
├── strings
├── math
├── dates
├── json
├── http
├── files
├── logging
└── security
~~~

### 10.2. Collection functions

Mô tả map, filter, reduce, sort, groupBy, distinct và các thao tác collection khác.

### 10.3. String functions

Mô tả trim, split, join, replace, match, format và quy tắc Unicode.

### 10.4. Date/time functions

Giải thích timezone, instant, local date/time, parsing và formatting.

### 10.5. JSON và serialization

Mô tả parse, serialize, schema validation và cách biểu diễn null, number, object.

### 10.6. I/O library

Nếu có API file hoặc network, cần nêu quyền cần thiết, blocking/asynchronous behavior, timeout và error semantics.

### 10.7. Security-sensitive API

Các API liên quan credential, cryptography hoặc access control cần ghi rõ trust assumptions và giới hạn sử dụng.

## 11. Module, import và namespace

Reference cần giải thích cách tổ chức DSL program thành module và cách dùng thành phần từ module khác.

### 11.1. Import syntax

~~~text
import std.collections
import com.example.catalog as catalog
~~~

### 11.2. Namespace

Namespace tránh trùng tên giữa module hoặc library. Cần nêu quy tắc resolve tên và alias.

### 11.3. Visibility

Một symbol có thể public, module-private hoặc internal. Reference cần ghi phạm vi truy cập.

### 11.4. Version constraint

Import package có thể pin version hoặc dùng version range. Cần giải thích dependency resolution và lockfile behavior.

### 11.5. Cyclic import

Nêu DSL có cho phép circular import hay không và compiler xử lý thế nào.

### 11.6. Module initialization

Nếu module có initialization side effect, cần mô tả thời điểm chạy, thứ tự và quy tắc chạy một lần hay mỗi lần import.

## 12. Annotation và metadata reference

Annotation hoặc metadata block bổ sung thông tin cho construct mà không nhất thiết thay đổi cấu trúc cú pháp chính.

Ví dụ:

~~~text
@deprecated(since = "2.3", replacement = "newRoute")
route "/legacy" {
    handler = legacyHandler
}
~~~

### 12.1. Target

Annotation có thể áp dụng cho declaration, field, function, parameter hoặc module. Reference cần liệt kê target hợp lệ.

### 12.2. Parameter

Mô tả tên, type, required condition và default của từng annotation parameter.

### 12.3. Retention

Metadata có thể tồn tại trong source, compiled artifact hoặc runtime. Cần nói rõ phase mà annotation còn hiệu lực.

### 12.4. Repeatability

Nêu một annotation có thể xuất hiện nhiều lần trên cùng construct hay không.

### 12.5. Custom annotation

Nếu extension được phép đăng ký annotation mới, cần mô tả namespace, validation và cách tránh xung đột.

## 13. Runtime semantics reference

Syntax chỉ cho biết chương trình được viết thế nào. Semantics giải thích chương trình được hiểu và thực thi ra sao.

### 13.1. Evaluation order

Mô tả thứ tự đánh giá operand, argument, block và expression. Nếu thứ tự không được bảo đảm, cần nói rõ để người viết không phụ thuộc vào một implementation cụ thể.

### 13.2. Scope

Giải thích lexical scope, block scope, module scope và variable shadowing.

### 13.3. State

Mô tả mutable state, immutable binding, state persistence và lifetime.

### 13.4. Error propagation

Giải thích exception, error value, try/catch hoặc failure branch và cách error đi qua function boundary.

### 13.5. Transaction semantics

Nếu DSL hỗ trợ transaction, nêu begin/commit/rollback, isolation level, nested transaction và hành vi khi lỗi.

### 13.6. Concurrency

Mô tả task, thread, async, shared state, cancellation và ordering guarantee.

### 13.7. Resource lifetime

Nêu thời điểm mở/đóng connection, stream, file, transaction hoặc execution context.

### 13.8. Determinism

Nếu runtime có random, clock, environment hoặc external call, cần nêu điều kiện để kết quả tái lập.

## 14. Configuration reference

Một DSL cấu hình có thể có nhiều option ảnh hưởng compiler, runtime hoặc deployment.

### 14.1. Configuration key

Mỗi key cần mô tả type, default, required, scope và source precedence.

### 14.2. Configuration scope

Option có thể ở global, project, module, task, environment hoặc request scope. Cần nêu phạm vi và inheritance.

### 14.3. Precedence

Nếu giá trị đến từ nhiều nguồn, reference cần ghi thứ tự ưu tiên.

~~~text
Default
  < Project config
  < Environment profile
  < Runtime override
~~~

Thứ tự thực tế phải khớp implementation.

### 14.4. Environment variable

Nêu tên biến, format, type conversion và hành vi khi thiếu hoặc sai.

### 14.5. Secret reference

Giải thích cách khai báo reference, quyền cần thiết, rotation và redaction. Không đưa secret thật vào ví dụ.

### 14.6. Deprecated option

Ghi version bị deprecated, replacement và thời điểm dự kiến bị loại bỏ nếu đã được công bố.

## 15. Error và diagnostics reference

Tài liệu tham chiếu lỗi giúp người dùng hiểu nguyên nhân và cách xử lý.

Một error entry nên có:

- Error code.
- Message hoặc message pattern.
- Phase phát sinh.
- Điều kiện gây lỗi.
- Source location nếu có.
- Cách khắc phục.
- Có thể retry hay không.

Ví dụ:

~~~text
DSL-E1024: Unknown property 'timeOut'

Cause:
The property is not declared by the endpoint block.

Resolution:
Use the documented property 'timeout'.
~~~

### 15.1. Parse error

Lỗi cú pháp như thiếu dấu ngoặc, token không hợp lệ hoặc expression không hoàn chỉnh.

### 15.2. Type error

Lỗi do giá trị không tương thích type hoặc không resolve được overload.

### 15.3. Semantic error

Lỗi do construct dùng sai context, trùng identifier hoặc vi phạm constraint.

### 15.4. Runtime error

Lỗi xảy ra trong lúc thực thi như timeout, missing resource hoặc host API failure.

### 15.5. Warning

Warning báo hành vi rủi ro, deprecated API hoặc cấu hình đáng ngờ nhưng không nhất thiết chặn compile.

### 15.6. Diagnostic stability

Nếu error code được dùng trong IDE hoặc automation, cần quản lý tính ổn định và compatibility giữa version.

## 16. Ví dụ reference có cấu trúc

Ví dụ mục tài liệu cho construct endpoint:

### endpoint

**Mục đích:** Khai báo địa chỉ kết nối đến một service.

**Context:** Có thể xuất hiện trong client hoặc connector block.

**Syntax:**

~~~text
endpoint <name> {
    scheme = <String>
    hostname = <String>
    port = <Integer>
    basePath = <String>
}
~~~

**Fields:**

| Field | Type | Required | Default | Mô tả |
|---|---|---|---|---|
| scheme | String | Có | — | Protocol scheme |
| hostname | String | Có | — | DNS name hoặc host literal |
| port | Integer | Không | Theo scheme | Port kết nối |
| basePath | String | Không | / | Prefix của resource path |

**Constraints:**

- Scheme phải thuộc tập protocol được hỗ trợ.
- Port phải nằm trong khoảng hợp lệ.
- Hostname không được chứa user credential.
- basePath phải là path hợp lệ.

**Example:**

~~~text
endpoint "catalog" {
    scheme = "https"
    hostname = "catalog.example.com"
    port = 443
    basePath = "/api/v2"
}
~~~

**Runtime behavior:** Runtime resolve endpoint thành client target. DNS lookup và connection được thực hiện theo connection policy của client.

Đây là ví dụ minh họa về cách trình bày, không phải syntax bắt buộc của mọi DSL.

## 17. Versioning tài liệu tham chiếu

DSL thay đổi theo thời gian. Reference documentation cần cho người đọc biết nội dung nào áp dụng cho compiler hoặc runtime version nào.

### 17.1. Version selector

Website documentation có thể cung cấp bộ chọn version:

~~~text
Documentation
  ├── Current
  ├── 2.4
  ├── 2.3
  └── 2.2
~~~

### 17.2. Since

Ghi version đầu tiên hỗ trợ construct hoặc field.

### 17.3. Deprecated

Ghi version đánh dấu deprecated, lý do, replacement và migration path.

### 17.4. Removed

Ghi version loại bỏ và cách chuyển đổi cho người dùng còn sử dụng construct cũ.

### 17.5. Compatibility matrix

Một bảng có thể chỉ rõ compiler, runtime, plugin và module version tương thích.

### 17.6. Language version

Compiler version và language version có thể khác nhau. Nếu người dùng có thể chọn language version, reference cần nói rõ feature nào thuộc language version nào.

## 18. Deprecation và migration reference

Deprecation là tín hiệu API hoặc syntax vẫn còn dùng được nhưng không nên xuất hiện trong code mới.

### 18.1. Deprecation notice

Một notice tốt gồm:

- Tên construct cũ.
- Version bắt đầu deprecated.
- Lý do.
- Construct thay thế.
- Ví dụ trước/sau.
- Version dự kiến removal nếu đã xác định.

### 18.2. Migration example

~~~text
Old:
endpointUrl = "https://catalog.example.com/api"

New:
endpoint {
    scheme = "https"
    hostname = "catalog.example.com"
    basePath = "/api"
}
~~~

### 18.3. Automated migration

Nếu có migration tool, reference cần ghi điều kiện áp dụng, thay đổi tự động và trường hợp cần sửa thủ công.

### 18.4. Compatibility mode

Compiler có thể cung cấp compatibility mode để tiếp tục đọc syntax cũ trong thời gian chuyển đổi. Cần nêu phạm vi và thời hạn của mode này.

## 19. Cross-reference và navigation

Reference documentation có nhiều khái niệm liên kết. Navigation tốt giúp người đọc đi từ construct đến type, function và semantics liên quan.

### 19.1. Link theo khái niệm

Từ field timeout có thể liên kết đến Duration type và timeout policy.

### 19.2. See also

Mỗi mục có thể có phần See also trỏ đến construct liên quan, nhưng chỉ nên liên kết khi có ích.

### 19.3. Breadcrumb

Breadcrumb thể hiện vị trí trong cấu trúc tài liệu, ví dụ Language Reference / Networking / Endpoint.

### 19.4. Search

Search cần index keyword, alias, error code, type và tên field. Tìm kiếm không nên chỉ dựa trên tiêu đề trang.

### 19.5. Stable URL

URL reference nên ổn định qua các lần chỉnh sửa. Nếu đổi slug, cần redirect hoặc mapping để link cũ không bị hỏng.

### 19.6. Anchor

Heading và field anchor giúp liên kết trực tiếp đến một phần nhỏ của trang. Anchor nên ổn định và dễ đoán.

## 20. Tài liệu tham chiếu được sinh tự động

Một phần reference có thể được sinh từ source metadata hoặc compiler schema.

### 20.1. Source of truth

Có thể lưu metadata trong annotation, schema definition hoặc declarative registry:

~~~text
@reference(
    description = "Maximum time to wait for a response",
    since = "2.1",
    default = "5s"
)
property timeout: Duration
~~~

Generator đọc metadata để tạo bảng field, type và version.

### 20.2. Generated grammar

Nếu parser có grammar machine-readable, có thể sinh syntax reference từ grammar để giảm sai lệch.

### 20.3. API documentation generator

Function signature, parameter type và return type có thể được lấy từ symbol metadata hoặc API descriptor.

### 20.4. Generated reference không đủ

Metadata có thể mô tả field nhưng không diễn giải lý do, semantics phức tạp hoặc ví dụ thực tế. Nên kết hợp nội dung biên tập với phần tự động sinh.

### 20.5. Generated output review

Generated documentation vẫn cần kiểm tra link, format, version mapping và tính dễ đọc. Generator sai có thể nhân bản lỗi trên toàn bộ tài liệu.

## 21. Documentation as code

Documentation as code là cách quản lý tài liệu trong cùng quy trình version control và review với source code.

### 21.1. Source control

Reference source được commit cùng repository hoặc repository tài liệu. Thay đổi semantics và thay đổi reference có thể được review trong cùng pull request.

### 21.2. Review

Reviewer kiểm tra syntax, semantics, examples và compatibility. Người hiểu compiler/runtime nên xác nhận mô tả hành vi.

### 21.3. Build documentation

Pipeline có thể render Markdown, kiểm tra link, validate code sample và tạo site.

### 21.4. Preview

Pull request có thể tạo preview để reviewer xem bố cục, navigation và code formatting trước khi publish.

### 21.5. Release synchronization

Reference version nên được phát hành cùng language/compiler release tương ứng. Tránh cập nhật current docs trước khi feature có mặt trong release.

## 22. Code examples trong reference

Code example là một phần quan trọng của reference vì nó cho thấy syntax trong ngữ cảnh cụ thể.

### 22.1. Minimal example

Ví dụ nhỏ giúp người đọc tập trung vào construct đang tra cứu.

### 22.2. Complete example

Một số construct cần context đầy đủ để hiểu. Khi đó cung cấp một ví dụ complete nhưng vẫn giới hạn phạm vi.

### 22.3. Expected output

Nếu runtime output có ý nghĩa, hiển thị output hoặc kết quả tương ứng.

~~~text
Input:
calculateTax(100, 0.1)

Output:
10
~~~

### 22.4. Runnable examples

Ví dụ nên được chạy tự động nếu có thể. Một example compile được không nhất thiết chứng minh semantics được mô tả đầy đủ, nhưng giúp phát hiện syntax lỗi thời.

### 22.5. Negative example

Có thể đưa ví dụ không hợp lệ cùng diagnostic mong đợi để làm rõ constraint.

### 22.6. Placeholder

Giá trị placeholder cần được đánh dấu rõ và không khiến người đọc nhầm là credential hoặc endpoint thật.

### 22.7. Example version

Ví dụ phải tương thích với version reference. Nếu syntax chỉ có từ version mới, cần gắn version note.

## 23. Accessibility và readability

Reference thường dài và được dùng trong lúc lập trình. Cấu trúc dễ quét giúp giảm thời gian tìm thông tin.

### 23.1. Headings

Dùng heading mô tả nội dung cụ thể, không dùng tiêu đề chung như Miscellaneous cho các khái niệm khác nhau.

### 23.2. Tables

Bảng phù hợp với field, type, default và compatibility. Nội dung dài hoặc semantics phức tạp nên được giải thích ở đoạn riêng thay vì nhồi vào ô.

### 23.3. Code formatting

Dùng code block cho syntax, signature và output. Giữ indentation nhất quán và phân biệt source với output.

### 23.4. Language

Dùng câu ngắn, thuật ngữ nhất quán và giải thích abbreviation ở lần xuất hiện đầu.

### 23.5. Responsive layout

Bảng nhiều cột cần có cách hiển thị trên màn hình nhỏ. Không nên dùng bảng cho đoạn văn dài.

### 23.6. Screen reader

Heading hierarchy, link text và table header cần có ý nghĩa để người dùng screen reader điều hướng được.

## 24. Localization và thuật ngữ

DSL thường có keyword tiếng Anh nhưng tài liệu có thể được dịch sang nhiều ngôn ngữ.

### 24.1. Giữ nguyên keyword

Keyword, identifier, type name và API symbol nên giữ nguyên spelling chính thức. Phần giải thích có thể được dịch.

### 24.2. Glossary

Duy trì glossary cho các thuật ngữ như scope, binding, evaluation, execution plan, host, runtime và module.

### 24.3. Translation consistency

Một thuật ngữ nên được dịch nhất quán. Nếu có nhiều cách dịch, glossary cần ghi lựa chọn được sử dụng.

### 24.4. Locale-sensitive behavior

Nếu DSL xử lý number, date hoặc string theo locale, reference cần ghi rõ locale nào được dùng và default lấy từ đâu.

### 24.5. Localized examples

Ví dụ có thể dùng dữ liệu phù hợp với ngôn ngữ, nhưng syntax và output cần giữ chính xác theo DSL.

## 25. Quality và maintenance của reference

Reference có thể trở nên lỗi thời khi compiler, runtime hoặc standard library thay đổi.

### 25.1. Accuracy

Thông tin phải khớp implementation và specification. Không nên mô tả behavior dựa trên phỏng đoán.

### 25.2. Completeness

Các field public, operator, function và error code cần có mục tra cứu phù hợp.

### 25.3. Consistency

Tên, type notation, default notation, version format và section structure cần thống nhất.

### 25.4. Discoverability

Người dùng phải tìm được mục từ tên construct, alias, error message hoặc concept.

### 25.5. Freshness

Tài liệu cần được cập nhật cùng thay đổi API và language feature.

### 25.6. Broken links

Kiểm tra internal link, external link và anchor. External URL có thể thay đổi nên cần owner hoặc periodic check.

### 25.7. Feedback

Cho phép người đọc báo lỗi hoặc đề xuất cải thiện. Feedback cần được chuyển đến nơi có thể xử lý và theo dõi.

## 26. Reference cho extension và plugin

DSL có thể cho phép extension bổ sung type, function, block hoặc provider.

### 26.1. Extension contract

Reference cần mô tả extension point, interface, lifecycle, capability và version compatibility.

### 26.2. Registration

Nêu cách đăng ký extension, namespace, identifier và thứ tự load nếu có ảnh hưởng.

### 26.3. Custom function

Mô tả signature, type conversion, permission, exception và side effect.

### 26.4. Custom type

Giải thích cách parse, validate, compare và serialize custom type.

### 26.5. Capability

Extension có thể cần quyền network, filesystem hoặc secret access. Reference nên ghi capability cần thiết và cách cấp.

### 26.6. Compatibility

Nêu host runtime version, DSL language version và plugin API version được hỗ trợ.

## 27. Tích hợp reference với IDE và tooling

Reference có thể được sử dụng trực tiếp bởi IDE, language server và command-line tool.

### 27.1. Hover documentation

Khi hover keyword hoặc field, IDE có thể hiển thị description, type, default và link đến trang reference.

### 27.2. Completion

Completion gợi ý construct hợp lệ trong context hiện tại. Metadata có thể cung cấp label, type và description.

### 27.3. Diagnostics link

Error message có thể dẫn đến mục reference giải thích cách sửa.

### 27.4. Schema-aware editor

Configuration DSL có thể cung cấp schema để editor validate field, type và completion.

### 27.5. Search integration

IDE search có thể tìm symbol trực tiếp trong reference hoặc mở trang theo symbol ID.

### 27.6. Offline reference

Một số môi trường cần documentation offline. Có thể đóng gói reference versioned cùng SDK hoặc development kit.

## 28. Quy trình xây dựng bộ reference

Một quy trình có thể gồm:

1. Xác định audience và phạm vi DSL.
2. Liệt kê public construct, type, function và option.
3. Xác định nguồn sự thật cho grammar và semantics.
4. Thiết kế information architecture.
5. Chuẩn hóa template cho từng loại entry.
6. Viết mô tả và ví dụ.
7. Sinh phần metadata phù hợp.
8. Kiểm tra examples và links.
9. Review với compiler/runtime owner.
10. Gắn version và phát hành cùng DSL release.
11. Thu thập feedback và cập nhật.

### 28.1. Inventory

Inventory giúp biết construct nào cần tài liệu. Có thể lấy từ grammar, symbol registry, standard library descriptor và public API.

### 28.2. Ownership

Mỗi nhóm reference nên có owner chịu trách nhiệm nội dung và cập nhật.

### 28.3. Change process

Khi thêm field hoặc đổi semantics, change proposal cần chỉ ra phần reference bị ảnh hưởng.

### 28.4. Release process

Tài liệu được version hóa, build và publish theo release. Bản cũ nên tiếp tục truy cập được trong thời gian hỗ trợ.

## 29. Ví dụ: function reference entry

Một mục cho function string normalization:

### normalizeWhitespace

**Signature:**

~~~text
normalizeWhitespace(value: String) -> String
~~~

**Description:** Thay chuỗi whitespace liên tiếp bằng một dấu cách và loại bỏ whitespace ở đầu/cuối chuỗi.

**Parameters:**

| Parameter | Type | Mô tả |
|---|---|---|
| value | String | Chuỗi đầu vào |

**Returns:** Chuỗi đã chuẩn hóa. Function không thay đổi giá trị đầu vào.

**Behavior:**

- Xử lý whitespace theo quy tắc Unicode được runtime hỗ trợ.
- Không thay đổi chữ hoa/chữ thường.
- Trả về chuỗi rỗng nếu input chỉ chứa whitespace.

**Example:**

~~~text
normalizeWhitespace("  hello   world  ")
~~~

Result:

~~~text
"hello world"
~~~

**Errors:** Báo type error nếu argument không thể chuyển thành String theo conversion rule của DSL.

Đây là ví dụ minh họa cho bố cục reference; semantics thật phải được xác định từ implementation của function.

## 30. Ví dụ: operator reference entry

### Logical AND

**Syntax:**

~~~text
left && right
~~~

**Operand types:** Boolean và Boolean.

**Result type:** Boolean.

**Evaluation:** Đánh giá left trước. Nếu left là false, không đánh giá right. Nếu left là true, đánh giá right và trả kết quả của right.

**Side effects:** Vì có short-circuit, side effect trong right có thể không xảy ra.

**Example:**

~~~text
account != null && account.enabled
~~~

Expression chỉ truy cập enabled khi account khác null, nếu semantics của optional value cho phép điều kiện này.

## 31. Những sai lầm thường gặp

**Viết reference như tutorial.** Hướng dẫn theo từng bước không thay thế bảng cú pháp và semantics có thể tra cứu nhanh.

**Chỉ liệt kê field.** Không có type, default, context và constraint thì người đọc vẫn phải đoán.

**Không phân biệt optional và nullable.** Một field có thể bỏ qua khác với field hiện diện nhưng nhận null.

**Mô tả default không chính xác.** Default có thể đến từ compiler, environment hoặc runtime và không phải lúc nào cũng là hằng số.

**Ví dụ không chạy được.** Code sample lỗi thời làm giảm niềm tin và khiến người đọc mất thời gian.

**Bỏ qua evaluation semantics.** Syntax đúng chưa đủ để giải thích thứ tự đánh giá và side effect.

**Không gắn version.** Người dùng có thể áp dụng field chỉ có trong bản mới vào compiler cũ.

**Không ghi deprecation.** API cũ tiếp tục được dùng và gây khó khăn khi nâng cấp.

**Sinh tài liệu hoàn toàn tự động.** Metadata thường không đủ diễn giải semantics và ví dụ thực tế.

**Dùng link không ổn định.** URL thay đổi mà không redirect làm hỏng liên kết từ IDE, issue và code review.

**Thuật ngữ không nhất quán.** Một khái niệm có nhiều tên trong các trang khác nhau khiến người đọc khó tìm kiếm.

**Không có owner.** Khi implementation thay đổi, không ai chịu trách nhiệm cập nhật reference.

## 32. Ghi nhớ

- Reference documentation là nguồn tra cứu chính xác về syntax, type, field, function, semantics và behavior của DSL.
- Reference khác tutorial, how-to và explanation về mục tiêu cũng như cách tổ chức.
- Mỗi construct nên có mục đích, syntax, context, fields, defaults, constraints, semantics và examples.
- Grammar cần mô tả token, production, precedence, associativity, whitespace và reserved keyword.
- Field reference cần phân biệt required, optional, nullable, default và unknown field.
- Type, literal, operator và function cần có semantics, conversion và error behavior rõ.
- Runtime reference cần giải thích evaluation order, scope, state, transaction, concurrency và resource lifetime.
- Configuration reference cần nêu scope, precedence, environment variable và secret reference.
- Error reference giúp liên kết diagnostic với nguyên nhân và cách khắc phục.
- Versioning, since, deprecated, removed và compatibility matrix giúp người dùng chọn đúng thông tin.
- Generated reference giảm sai lệch metadata nhưng vẫn cần nội dung biên tập.
- Documentation as code giúp review và phát hành đồng bộ với source.
- Code examples cần ngắn, chính xác, có thể chạy và gắn version phù hợp.
- Navigation, search, stable URL và anchor giúp tăng khả năng tìm thấy thông tin.
- Reference cần được duy trì cùng grammar, compiler, runtime, standard library và plugin API.

## 33. Câu hỏi tự kiểm tra

1. Tài liệu tham chiếu là gì và giải quyết nhu cầu nào của người dùng DSL?
2. Phân biệt reference documentation, tutorial, how-to guide và explanation.
3. Một mục reference cho construct nên có những thành phần nào?
4. Grammar reference cần giải thích terminal, non-terminal, precedence và associativity ra sao?
5. Phân biệt required, optional và nullable field.
6. Vì sao cần mô tả chính xác default value và nguồn của default?
7. Một function reference nên ghi signature, parameter, return type và side effect như thế nào?
8. Runtime semantics reference cần mô tả evaluation order, scope và error propagation ra sao?
9. Versioning, since, deprecated và removed giúp người dùng nâng cấp như thế nào?
10. Generated reference có ưu điểm và giới hạn gì?
11. Documentation as code giúp đồng bộ tài liệu với implementation như thế nào?
12. Làm thế nào để bảo đảm code examples không lỗi thời?
13. Vì sao stable URL, search và cross-reference quan trọng?
14. Reference cho extension/plugin cần mô tả những contract nào?
15. IDE có thể sử dụng reference metadata cho hover, completion và diagnostics ra sao?
16. Hãy thiết kế cấu trúc reference entry cho một block cấu hình có nhiều field và nested block.
