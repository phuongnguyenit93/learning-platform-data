# Kiểm tra mã đầu ra

Trong một compiler cho ngôn ngữ chuyên biệt theo miền (Domain-Specific Language — DSL), bước sinh mã chuyển AST hoặc IR thành mã nguồn, bytecode, SQL, cấu hình hay một dạng đầu ra khác. Tuy nhiên, việc tạo được một tệp đầu ra chưa chứng minh rằng đầu ra đó hợp lệ hoặc giữ đúng ý nghĩa của chương trình DSL. **Kiểm tra mã đầu ra (generated output validation)** là quá trình xác nhận sản phẩm của code generator đáp ứng hợp đồng của target và bảo toàn semantics đã được định nghĩa cho DSL.

Kiểm tra mã đầu ra bao gồm nhiều lớp: đầu ra có đúng cú pháp target không, có biên dịch hoặc được nạp thành công không, kiểu và API được dùng có hợp lệ không, hành vi có tương đương với DSL không, và đầu ra có an toàn, ổn định, truy vết được hay không. Tùy target, cách kiểm tra có thể là gọi compiler khác, parse lại đầu ra, chạy test, xác thực schema, thực thi trên sandbox hoặc so sánh với một interpreter tham chiếu.

Đây là bước quan trọng trong pipeline sinh mã vì lỗi ở backend có thể biến một DSL hợp lệ thành chương trình đích sai, khó debug hoặc nguy hiểm. Một chiến lược kiểm tra tốt cần dựa trên hợp đồng target, phân biệt lỗi của người viết DSL với lỗi của code generator và cung cấp thông tin truy ngược về nguồn.

## 1. Vì sao phải kiểm tra mã đầu ra?

Code generator thường xử lý AST hoặc IR đã được phân tích ngữ nghĩa. Dù vậy, backend vẫn có thể sinh ra đầu ra sai do lỗi ánh xạ kiểu, precedence, escape literal, tên target, runtime API hoặc phiên bản target.

Ví dụ, DSL có biểu thức:

```text
2 + 3 * 4
```

Nếu backend sinh `((2 + 3) * 4)` thay vì `2 + (3 * 4)`, mã đích có thể biên dịch thành công nhưng kết quả khác với semantics của DSL. Kiểm tra cú pháp đơn thuần không phát hiện được lỗi này.

Một ví dụ khác là DSL truy vấn:

```text
query activeCustomers {
    from Customer
    where status == ACTIVE
    select id, name
}
```

Backend có thể sinh SQL hợp cú pháp nhưng nối trực tiếp dữ liệu người dùng vào chuỗi truy vấn, dẫn đến SQL injection. Vì vậy, đầu ra phải được kiểm tra cả về cú pháp, hành vi và tính an toàn.

### 1.1. Các mục tiêu chính

- Xác nhận đầu ra tuân theo grammar hoặc định dạng của target.
- Xác nhận mã có thể biên dịch, liên kết, nạp hoặc được hệ thống đích chấp nhận.
- Kiểm tra mapping kiểu, toán tử, luồng điều khiển và API runtime.
- Xác nhận hành vi đầu ra tương đương với semantics DSL trong phạm vi được hỗ trợ.
- Phát hiện lỗi escaping, injection, truy cập ngoài ý muốn và cấu hình không an toàn.
- Bảo đảm source map, debug metadata và thông tin nguồn có thể sử dụng.
- Phát hiện output không ổn định hoặc phụ thuộc môi trường ngoài dự kiến.
- Cung cấp diagnostic rõ ràng để xác định lỗi thuộc DSL, backend hay môi trường target.

### 1.2. Sinh thành công không đồng nghĩa với đầu ra đúng

Có thể phân biệt các trạng thái:

| Trạng thái | Điều đã được xác nhận | Điều chưa được bảo đảm |
|---|---|---|
| File được tạo | Backend đã ghi được output | Cú pháp và semantics |
| Parse thành công | Output có cấu trúc cú pháp hợp lệ | Kiểu, liên kết và hành vi |
| Compile thành công | Target compiler chấp nhận mã | Hành vi có đúng DSL không |
| Runtime test thành công | Một số trường hợp chạy đúng | Các trường hợp chưa được kiểm tra |
| Conformance đạt | Đầu ra đáp ứng bộ hợp đồng và test đã định nghĩa | Mọi lỗi có thể có trong mọi môi trường |

Kiểm tra cần được mô tả theo phạm vi cụ thể. Một kết quả compile thành công không nên được báo cáo như bằng chứng rằng semantics đã được xác nhận toàn diện.

## 2. Kiểm tra đầu ra nằm ở đâu trong pipeline?

Một pipeline có thể tổ chức như sau:

```text
DSL source
    |
    v
Lexer / Parser
    |
    v
AST
    |
    v
Name resolution / Semantic analysis
    |
    v
Type checking / Domain validation
    |
    v
Lowering / Optimization
    |
    v
Target code generator
    |
    v
Generated output
    |
    +--> Parse / format validation
    +--> Target compiler / linker
    +--> Static analysis / security checks
    +--> Runtime and semantic tests
    +--> Source-map validation
    |
    v
Validated artifact
```

Không phải mọi dự án cần chạy mọi bước trên trong mỗi lần build. Ví dụ, kiểm tra compile có thể chạy trong CI; test tương đương semantics có thể chạy trong bộ test backend; kiểm tra schema JSON có thể được thực hiện ngay khi output được tạo.

### 2.1. Kiểm tra trước và sau khi sinh mã

Kiểm tra AST/IR trước khi sinh mã giúp loại bỏ những đầu vào chưa đủ điều kiện: node chưa phân giải, kiểu chưa xác định hoặc tính năng target không hỗ trợ. Kiểm tra sau khi sinh mã xác nhận backend đã chuyển mô hình hợp lệ thành output đúng.

Hai lớp kiểm tra bổ sung cho nhau. Nếu chỉ kiểm tra đầu vào, lỗi trong emitter có thể lọt qua. Nếu chỉ kiểm tra output, diagnostic có thể khó truy ngược vì thông tin nguồn và ý định DSL đã bị hạ xuống.

### 2.2. Validation trong phát triển và production

Trong môi trường phát triển, compiler có thể thực hiện thêm parse lại, compile thử và test nhanh để cung cấp phản hồi sớm. Trong production, có thể xác thực artifact một lần ở pipeline build, ký hoặc đóng gói artifact đã kiểm tra, rồi triển khai đúng artifact đó.

Không nên tạo một output rồi kiểm tra một bản khác hoặc sinh lại sau kiểm tra mà không ràng buộc nội dung. Artifact được triển khai cần là artifact đã được xác thực.

## 3. Xác định hợp đồng đầu ra (output contract)

Trước khi kiểm tra, cần biết output phải tuân thủ điều gì. Hợp đồng đầu ra mô tả định dạng, phiên bản, runtime, API, giới hạn và semantics mà backend cam kết.

Ví dụ target Java:

| Thuộc tính | Hợp đồng ví dụ |
|---|---|
| Ngôn ngữ | Java |
| Phiên bản | Java 21 |
| Encoding | UTF-8 |
| Package | Ánh xạ từ module DSL |
| Runtime library | `dsl-runtime` phiên bản tương thích |
| Null model | Optional và kiểm tra null theo DSL |
| Số thập phân | `BigDecimal` với rounding mode xác định |
| Error model | Exception runtime có source metadata |
| Build artifact | Các class và metadata liên quan |

Với SQL, hợp đồng cần chỉ rõ dialect, schema, parameter binding và semantics null. Với JSON/YAML, hợp đồng cần xác định schema, version và các trường bắt buộc.

### 3.1. Kiểm tra đúng target version

Mã có thể hợp lệ ở phiên bản mới nhưng không hợp lệ ở phiên bản mà người dùng đang triển khai. Vì vậy, kiểm tra phải dùng đúng phiên bản target và runtime đã khai báo.

### 3.2. Kiểm tra runtime compatibility

Output có thể tham chiếu class hoặc function không có trong runtime thực tế. Cần xác nhận dependency và API mà code generator sử dụng tồn tại trong phiên bản runtime được hỗ trợ.

### 3.3. Khả năng của target

Không phải mọi tính năng DSL đều có thể biểu diễn trên mọi target. Hợp đồng cần liệt kê khả năng hỗ trợ hoặc backend phải từ chối các node không thể ánh xạ đúng. Không nên âm thầm sinh một cấu trúc gần giống nhưng có semantics khác.

## 4. Kiểm tra cấu trúc và cú pháp của output

Lớp đầu tiên là xác nhận output đúng định dạng mà target yêu cầu.

### 4.1. Parse lại mã nguồn được sinh

Với target là ngôn ngữ có parser, có thể parse lại output bằng parser của target hoặc công cụ tương ứng. Việc này phát hiện lỗi như thiếu dấu ngoặc, sai dấu phân cách, literal không hợp lệ hoặc cấu trúc cú pháp bị emitter tạo sai.

Ví dụ, nếu DSL sinh Java, có thể dùng parser Java hoặc gọi compiler Java ở chế độ kiểm tra. Với SQL, có thể dùng parser của dialect hoặc database trong môi trường kiểm thử.

Parse lại chỉ xác nhận cú pháp. Nó không chứng minh các symbol tồn tại, kiểu tương thích hoặc hành vi đúng.

### 4.2. Xác thực schema cho định dạng dữ liệu

Nếu output là JSON, YAML, XML hoặc một định dạng cấu hình, cần kiểm tra cú pháp và schema:

- JSON có parse được không?
- Các trường bắt buộc có tồn tại không?
- Kiểu của trường có đúng không?
- Enum hoặc giá trị có nằm trong tập cho phép không?
- Các tham chiếu và quan hệ giữa trường có hợp lệ không?

Ví dụ, output JSON có thể parse thành công nhưng `replicas` lại là chuỗi `"3"` trong khi schema yêu cầu integer. Cần schema validation sau syntax parsing.

### 4.3. Kiểm tra cấu trúc file và artifact

Với output nhiều file, kiểm tra manifest, package, đường dẫn, tên file, encoding và tập file cần thiết. Một class Java có thể đúng cú pháp nhưng nằm sai package path; một artifact có thể thiếu metadata mà runtime cần.

### 4.4. Không dựa hoàn toàn vào regex

Regex hữu ích cho một số kiểm tra định dạng đơn giản, nhưng không thay thế parser của target đối với ngôn ngữ lồng nhau hoặc có grammar phức tạp. Ví dụ, tìm chuỗi `;` không thể chứng minh mọi câu lệnh Java đều kết thúc đúng, vì dấu đó có thể xuất hiện trong string hoặc comment.

## 5. Biên dịch, liên kết và nạp thử

Với target là ngôn ngữ được biên dịch, bước xác thực quan trọng là gọi compiler hoặc linker đích.

### 5.1. Compile generated source

Compile thử phát hiện nhiều lỗi mà parse không phát hiện:

- Kiểu không tương thích.
- Method hoặc class không tồn tại.
- Sai package hoặc import.
- Chữ ký hàm không khớp.
- Truy cập thành phần private.
- Generic constraint không thỏa.
- Phiên bản ngôn ngữ không hỗ trợ cú pháp được sinh.

Compiler đích nên được cấu hình với đúng classpath, module path, target version và compiler flags như môi trường build thật.

### 5.2. Link và resolve dependency

Ngay cả khi từng source file compile riêng, toàn bộ artifact có thể thất bại khi link hoặc resolve dependency. Cần kiểm tra các symbol external, thư viện runtime, plugin và module cần thiết.

### 5.3. Load hoặc instantiate thử

Với một số runtime, việc nạp class, module hoặc workflow definition có thể phát hiện lỗi cấu hình chỉ xuất hiện sau compile. Ví dụ, dependency injection container không tìm thấy binding, workflow engine không nhận ra một task type hoặc plugin descriptor không hợp lệ.

### 5.4. Môi trường kiểm tra phải được kiểm soát

Compile hoặc load thử cần dùng môi trường tách biệt, dependency đã khóa phiên bản và không thực hiện tác dụng phụ ngoài ý muốn. Nếu bước kiểm tra có thể chạy code do generator tạo, nên dùng sandbox hoặc giới hạn quyền phù hợp.

## 6. Kiểm tra ánh xạ kiểu

Một output có thể hợp cú pháp nhưng sai kiểu vì backend ánh xạ type không chính xác.

Ví dụ DSL:

```text
let amount: Money = order.total
```

Nếu `Money` được ánh xạ thành `double` nhưng semantics DSL yêu cầu decimal chính xác và currency, output có thể compile nhưng làm sai nghiệp vụ.

### 6.1. Type mapping

Kiểm tra cần xác nhận:

- Kiểu nguồn được ánh xạ sang kiểu target đã định nghĩa.
- Nullable/optional không bị mất.
- Generic và variance được xử lý đúng.
- Kiểu miền như `Money`, `CustomerId` không bị gộp sai.
- Precision, overflow và rounding được giữ.
- Kiểu kết quả của toán tử đúng với chữ ký runtime.

### 6.2. Kiểm tra phép toán

Ví dụ, DSL định nghĩa `Money * Percentage -> Money`. Backend cần sinh lời gọi hoặc biểu thức target tương ứng. Nếu sinh `Money * double` nhưng runtime không có phép toán đó, compile sẽ thất bại; nếu có phép toán nhưng rounding khác semantics DSL, compile vẫn thành công mà hành vi có thể sai.

### 6.3. Nullability và giá trị thiếu

Nếu DSL phân biệt null, missing và unknown, output cần giữ được sự phân biệt này. Ánh xạ tất cả thành `null` hoặc default value có thể làm thay đổi kết quả điều kiện và hành vi truy cập.

### 6.4. Kiểm tra type metadata

Với target có type erasure hoặc kiểu runtime yếu, compiler có thể cần metadata hoặc runtime checks. Kiểm tra output nên xác nhận metadata được sinh đủ để thực hiện các ràng buộc DSL ở runtime.

## 7. Kiểm tra bảo toàn ngữ nghĩa

Đây là lớp quan trọng nhất: output phải thực hiện cùng ý nghĩa với chương trình DSL nguồn theo phạm vi tính năng được hỗ trợ.

### 7.1. So sánh với interpreter tham chiếu

Nếu DSL có interpreter, có thể chạy cùng input qua interpreter và chương trình target được sinh rồi so sánh kết quả quan sát được.

```text
                 DSL program
                      |
             +--------+--------+
             |                 |
             v                 v
       Reference interpreter  Code generator
             |                 |
             v                 v
       Reference result     Generated target
                               |
                               v
                          Target runtime
                               |
                               v
                         Target result
             |                 |
             +--------compare--+
```

So sánh cần bao gồm giá trị trả về, trạng thái được thay đổi, lỗi, thứ tự tác dụng phụ và các kết quả quan sát được khác.

### 7.2. Golden tests

Golden test lưu output mong đợi cho một input DSL cụ thể. Khi code generator thay đổi, test so sánh output mới với bản chuẩn.

Golden tests hữu ích để phát hiện thay đổi ngoài ý muốn trong tên, format, cấu trúc file và mapping. Tuy nhiên, output khác nhau về whitespace không nhất thiết có nghĩa semantics sai; cần quyết định so sánh byte-for-byte hay chuẩn hóa output trước khi so sánh.

### 7.3. Differential testing

Differential testing chạy cùng chương trình trên nhiều cách thực thi hoặc nhiều backend rồi so sánh kết quả. Ví dụ interpreter, Java backend và bytecode backend phải cho kết quả tương đương trong phạm vi chung.

### 7.4. Property-based testing

Có thể sinh nhiều AST hoặc chương trình DSL hợp lệ, chạy qua interpreter và generated target, rồi kiểm tra các tính chất. Cách này mở rộng vùng đầu vào ngoài một số ví dụ viết tay.

### 7.5. Kiểm tra ranh giới và trường hợp biên

Các trường hợp cần chú ý gồm:

- Số âm, số rất lớn, overflow và rounding.
- Null, missing và unknown.
- Chuỗi Unicode, ký tự escape và chuỗi rỗng.
- Danh sách rỗng, một phần tử và nhiều phần tử.
- Nhánh điều kiện không được thực hiện.
- Short-circuit và thứ tự đánh giá.
- Exception và lỗi từ dịch vụ ngoài.
- Giá trị biên của refinement type hoặc đơn vị đo.

## 8. Kiểm tra luồng điều khiển và thứ tự đánh giá

Backend có thể sinh mã đúng cú pháp nhưng thay đổi cách nhóm hoặc thứ tự thực thi.

### 8.1. Operator precedence

DSL:

```text
a + b * c
```

Nếu `*` có precedence cao hơn `+`, output cần giữ `a + (b * c)`. Nếu emitter bỏ ngoặc sai, target có thể tạo cây biểu thức khác.

### 8.2. Associativity

Biểu thức `a - b - c` thường có nghĩa `(a - b) - c`. Backend không được sinh cách nhóm khác nếu target có quy tắc associativity khác hoặc nếu biểu thức đã được lowering thành cấu trúc cụ thể.

### 8.3. Short-circuit

Nếu DSL định nghĩa `and` và `or` theo short-circuit, target phải không đánh giá nhánh bị bỏ qua. Việc thay `and` bằng một hàm nhận hai đối số đã được đánh giá trước có thể làm thay đổi tác dụng phụ.

### 8.4. Thứ tự câu lệnh

Các hành động trong block có thể cần chạy tuần tự. Backend không được tái sắp xếp nếu hành động có tác dụng phụ hoặc phụ thuộc trạng thái trước đó.

### 8.5. Exceptions và finally

Nếu DSL định nghĩa cleanup, rollback hoặc finally semantics, target cần bảo đảm các bước này xảy ra cả khi có lỗi. Cần kiểm tra đường đi bình thường và đường đi exception.

## 9. Kiểm tra target SQL

Khi sinh SQL, output validation cần xét cả dialect và cách truy vấn được thực thi.

### 9.1. Parse theo đúng dialect

SQL có khác biệt giữa PostgreSQL, SQLite, MySQL, SQL Server và các hệ quản trị khác. Kiểm tra bằng parser hoặc database phải dùng đúng dialect target.

### 9.2. Parameter binding

Giá trị dữ liệu cần được truyền qua bind parameters thay vì nối trực tiếp vào chuỗi SQL.

Ví dụ an toàn:

```sql
SELECT id, name
FROM Customer
WHERE status = ? AND age >= ?
```

Giá trị `ACTIVE` và `18` được truyền riêng qua API parameter. Tên bảng và cột cần lấy từ schema hoặc symbol đã xác thực, sau đó quote theo dialect.

### 9.3. Semantics của null và Boolean

SQL dùng logic ba giá trị trong nhiều biểu thức. Nếu DSL có logic hai giá trị, backend cần chuyển đổi rõ để không làm thay đổi kết quả lọc.

### 9.4. Kiểm tra schema và quyền

Query có thể hợp cú pháp nhưng tham chiếu bảng/cột không tồn tại hoặc user database không có quyền. Có thể kiểm tra bằng schema metadata, prepare statement hoặc chạy trong database test có schema đại diện.

### 9.5. Kiểm tra kế hoạch truy vấn

Với một số DSL truy vấn, có thể kiểm tra query plan để phát hiện full scan hoặc index không được sử dụng. Đây là kiểm tra hiệu năng riêng, không thay thế kiểm tra correctness.

## 10. Kiểm tra output JSON, YAML và cấu hình

Khi target là định dạng dữ liệu hoặc cấu hình, validation thường gồm nhiều tầng:

1. Parse cú pháp định dạng.
2. Validate schema.
3. Kiểm tra tham chiếu và quan hệ giữa các trường.
4. Kiểm tra phiên bản schema hoặc API.
5. Nạp thử vào hệ thống đích trong môi trường an toàn.

Ví dụ cấu hình triển khai:

```yaml
service:
  name: order-api
  replicas: 3
  port: 8080
```

YAML parser chỉ xác nhận cú pháp. Schema có thể yêu cầu `replicas` là số nguyên dương, `port` nằm trong khoảng hợp lệ và `name` tuân theo quy tắc đặt tên. Hệ thống đích còn có thể áp dụng chính sách về tài nguyên, network hoặc quyền.

### 10.1. Schema version

Output cần khai báo đúng phiên bản schema mà consumer hỗ trợ. Một file hợp lệ với schema mới có thể bị runtime cũ từ chối.

### 10.2. Defaults và trường bị bỏ qua

Nếu generator bỏ qua trường vì cho rằng target có default, cần xác nhận default của target tương đương với semantics DSL. Default có thể thay đổi giữa phiên bản target.

## 11. Kiểm tra bảo mật đầu ra

Output generated code có thể trở thành đầu vào cho compiler, database, shell, browser hoặc hệ thống triển khai. Vì vậy, cần kiểm tra cách dữ liệu và identifier được biểu diễn.

### 11.1. Injection

Các rủi ro phổ biến:

- SQL injection khi nối dữ liệu vào query.
- Command injection khi sinh shell command.
- Code injection khi chèn chuỗi người dùng vào source code.
- Template injection khi dữ liệu được diễn giải như template expression.
- Path traversal khi tên file hoặc đường dẫn lấy từ input.

Biện pháp chính là phân biệt dữ liệu với cấu trúc mã, dùng parameterization, encoder theo context, allowlist identifier và kiểm tra đường dẫn.

### 11.2. Escape theo đúng context

Không có một hàm escape dùng an toàn cho mọi target. Escape Java string, JavaScript string, JSON string, HTML, SQL literal và shell argument có quy tắc khác nhau.

Generator nên dùng API hoặc thư viện chuyên biệt cho target thay vì tự thay thế một vài ký tự theo cách thủ công.

### 11.3. Dependency và API được sinh

Output có thể tham chiếu thư viện hoặc API nguy hiểm. Có thể kiểm tra danh sách dependency, quyền truy cập và các API được phép theo policy của hệ thống.

### 11.4. Không chạy output không tin cậy trên máy chủ chính

Nếu cần execution test, chạy trong sandbox với quyền filesystem, network, CPU và memory giới hạn. Không dùng dữ liệu production hoặc credentials thật cho một output chưa được xác thực.

### 11.5. Kiểm tra artifact và provenance

Với build quan trọng, có thể ghi lại hash output, phiên bản compiler, target profile, dependency và nguồn DSL. Metadata này hỗ trợ audit và xác định artifact đã được tạo từ đầu vào nào.

## 12. Kiểm tra source map và khả năng debug

Mã target thường có cấu trúc khác DSL. Source map giúp liên kết vị trí trong output với vị trí nguồn.

Ví dụ:

```text
DSL: rules/shipping.dsl:12
    shipping.fee = 0

Generated: ShippingRules.java:48
    context.shipping().setFee(Money.zero());
```

### 12.1. Kiểm tra mapping tồn tại

Có thể xác nhận mỗi đoạn target quan trọng có mapping hoặc được đánh dấu synthetic. Các lỗi runtime ở đoạn target được sinh cần có cách truy về node AST/IR nguồn.

### 12.2. Mapping chính xác

Kiểm tra không chỉ sự tồn tại mà cả vị trí mapping: source span phải trỏ đến node tương ứng, không lệch sang khai báo hoặc biểu thức bên cạnh.

### 12.3. Generated code không có source tương ứng

Compiler có thể sinh helper, temporary variable hoặc wrapper không xuất hiện trực tiếp trong DSL. Những đoạn này cần được đánh dấu compiler-generated và có liên kết origin nếu hữu ích.

### 12.4. Unicode và vị trí

Source map cần thống nhất cách tính offset, dòng và cột giữa DSL và target. UTF-8 byte, UTF-16 code unit và cột hiển thị có thể khác nhau; chuyển đổi sai sẽ làm debugger đánh dấu sai vị trí.

## 13. Tính xác định và tái lập của output

Cùng một đầu vào DSL, cùng dependency và cùng cấu hình nên tạo output ổn định. Tính xác định giúp review diff, cache, reproducible builds và điều tra sự cố.

Các nguồn gây output không ổn định:

- Thứ tự duyệt map hoặc symbol table không xác định.
- Timestamp hoặc đường dẫn tuyệt đối của máy build.
- Tên biến tạm sinh ngẫu nhiên.
- Locale ảnh hưởng số, ngày và định dạng chuỗi.
- Phiên bản dependency không được khóa.
- Thứ tự module phụ thuộc cách liệt kê file.

### 13.1. Kiểm tra determinism

Có thể sinh output nhiều lần từ cùng input trong môi trường cố định rồi so sánh hash hoặc nội dung. Nếu khác nhau, cần xác định phần khác biệt có được phép hay không.

### 13.2. Kiểm tra reproducible build

Reproducible build yêu cầu đầu vào, compiler, runtime, dependency và cấu hình được kiểm soát. Output phải có thể tái tạo trên môi trường build khác trong phạm vi cam kết.

### 13.3. Cache và invalidation

Cache output cần gắn với hash của DSL source, dependency, compiler version, target profile và runtime contract. Khi một thành phần ảnh hưởng đến output thay đổi, cache phải được invalidated.

## 14. Kiểm tra output nhiều file

Một backend có thể sinh nhiều file source, metadata, resource và manifest. Khi đó, validation cần xét artifact như một tập hợp.

Các kiểm tra có thể gồm:

- Mọi file được tham chiếu trong manifest đều tồn tại.
- Không có tên file hoặc package trùng ngoài ý muốn.
- Mọi class/module được import đều có trong output hoặc dependency.
- Source map trỏ đến file target có thật.
- Metadata version tương thích với runtime.
- Không còn file cũ không thuộc build hiện tại nếu build yêu cầu output sạch.
- Không có đường dẫn vượt ra ngoài thư mục output được phép.

### 14.1. Manifest output

Generator có thể tạo manifest liệt kê file, loại artifact, hash và module liên quan. Validator so sánh manifest với filesystem để phát hiện thiếu hoặc thừa file.

### 14.2. Atomic generation

Nên tránh để lần sinh mã thất bại tạo một output nửa cũ nửa mới. Một chiến lược là sinh vào thư mục tạm, xác thực toàn bộ, rồi thay thế output hiện hành khi mọi bước cần thiết thành công.

### 14.3. Output stale

Khi một khai báo bị xóa khỏi DSL, file generated cũ tương ứng có thể còn sót lại. Build system cần biết tập file thuộc generator để xóa hoặc đánh dấu file stale một cách an toàn.

## 15. Kiểm tra nhiều backend

Một DSL có thể sinh Java, SQL và bytecode từ cùng IR. Các backend cần đáp ứng cùng bộ semantics trong phần tính năng chung.

```text
                 Typed IR
                    |
          +---------+---------+
          |         |         |
          v         v         v
       Java BE    SQL BE   Bytecode BE
          |         |         |
          v         v         v
       JVM tests  DB tests   VM tests
          |         |         |
          +---- semantic comparison ----+
```

### 15.1. Conformance suite

Có thể xây dựng một bộ test chung gồm chương trình DSL và kết quả mong đợi. Mỗi backend chạy bộ test trên target tương ứng. Những tính năng không được backend hỗ trợ cần được khai báo rõ, không nên bị bỏ qua âm thầm.

### 15.2. So sánh hành vi quan sát được

Các backend không nhất thiết tạo output giống nhau, nhưng cần có hành vi tương đương: giá trị trả về, trạng thái, lỗi và tác dụng phụ theo semantics DSL.

### 15.3. Capability matrix

Một bảng capability giúp xác định target nào hỗ trợ tính năng nào:

| Tính năng DSL | Java backend | SQL backend | Bytecode backend |
|---|---|---|---|
| Boolean expressions | Có | Có, cần mapping null | Có |
| Custom domain functions | Runtime API | Chỉ nếu có UDF/mapping | Runtime call |
| Side-effect actions | Có | Thường giới hạn | Có |
| Workflow retry | Runtime support | Không trực tiếp | Runtime support |

Bảng thực tế phải được duy trì theo phiên bản backend và target profile.

## 16. Phân loại lỗi khi kiểm tra mã đầu ra

Khi validation thất bại, cần phân biệt nguyên nhân để người dùng hoặc nhóm phát triển biết bước xử lý.

| Nhóm lỗi | Ví dụ | Chủ thể có thể cần xử lý |
|---|---|---|
| Lỗi DSL nguồn | Biểu thức không hợp lệ hoặc sai kiểu | Người viết DSL hoặc frontend |
| Lỗi lowering | Node không được chuyển đúng sang IR | Nhóm compiler |
| Lỗi code generator | Thiếu dấu ngoặc, sai mapping hoặc import | Nhóm backend |
| Lỗi target compatibility | Dùng API không có ở target version | Cấu hình target hoặc backend |
| Lỗi dependency | Thiếu runtime library hoặc version conflict | Build/dependency setup |
| Lỗi semantics | Output chạy nhưng khác hành vi DSL | Compiler/runtime implementation |
| Lỗi môi trường | Database, filesystem hoặc runtime không sẵn sàng | Môi trường kiểm tra |
| Lỗi security policy | Output dùng API hoặc dependency bị cấm | Backend/policy configuration |

### 16.1. Diagnostic nên truy về nguồn DSL

Nếu compiler target báo lỗi ở dòng generated code, source map nên giúp tìm node DSL tương ứng. Diagnostic có thể bao gồm cả vị trí target và vị trí DSL.

### 16.2. Lỗi nội bộ của generator

Nếu một IR node đã được xác thực nhưng backend không biết sinh nó, đó thường là lỗi thiếu hỗ trợ hoặc lỗi nội bộ backend. Không nên báo người dùng rằng cú pháp DSL sai nếu lỗi xảy ra sau semantic analysis.

### 16.3. Không che lỗi bằng output thay thế

Khi validation thất bại, không nên tự động dùng một đoạn mã mặc định hoặc output cũ mà không báo. Artifact không hợp lệ cần được đánh dấu thất bại để tránh triển khai nhầm.

## 17. Tổ chức validation pipeline

Một pipeline có thể chia thành các tầng với chi phí và mục tiêu khác nhau:

| Tầng | Nội dung | Thời điểm phù hợp |
|---|---|---|
| Fast structural checks | File, encoding, syntax, schema và manifest | Mỗi lần sinh |
| Target compile checks | Compile/link/load với toolchain target | CI hoặc build validation |
| Semantic tests | So sánh interpreter và generated output | Test suite của backend |
| Security checks | Injection, dependency, API policy, sandbox | CI và trước release |
| Reproducibility checks | Sinh lặp và so sánh output/hash | CI hoặc release pipeline |
| Deployment validation | Nạp thử vào hệ thống đích trong môi trường staging | Trước triển khai |

### 17.1. Fail fast

Các lỗi cấu trúc và cú pháp nên được phát hiện sớm vì chúng rẻ và có thể chặn các bước tốn kém hơn. Nếu output không parse được, không cần chạy execution tests trên output đó.

### 17.2. Chạy kiểm tra độc lập song song

Khi các kiểm tra không phụ thuộc nhau, có thể chạy song song: source map validation, static security scan và determinism checks. Nhưng compile cần output đã ghi xong; runtime test cần artifact compile thành công. Cần tổ chức dependency rõ ràng.

### 17.3. Lưu kết quả có thể truy vết

Mỗi lần validation nên ghi nhận compiler version, target profile, input hash, output hash, toolchain version và kết quả từng tầng. Điều này giúp xác định chính xác artifact nào đã được kiểm tra.

## 18. Ví dụ tổng hợp: xác thực Java output từ DSL

DSL nguồn:

```text
rule freeShipping {
    when order.total >= Money(1_000_000, VND)
         and order.status == PAID
    then order.shippingFee = Money.zero(VND)
}
```

Backend sinh Java:

```java
public final class ShippingRules {
    public static void applyFreeShipping(Order order) {
        boolean eligible =
            order.total().compareTo(Money.of(1_000_000, Currency.VND)) >= 0
            && order.status() == OrderStatus.PAID;

        if (eligible) {
            order.setShippingFee(Money.zero(Currency.VND));
        }
    }
}
```

Một quy trình validation có thể gồm:

1. **Structural check:** xác nhận file Java được tạo, encoding UTF-8 và package path đúng.
2. **Parse/compile:** biên dịch bằng đúng Java version và runtime library.
3. **Type/API check:** xác nhận `Money`, `Order`, `OrderStatus` và các method được tham chiếu tồn tại với chữ ký phù hợp.
4. **Semantic test:** tạo đơn hàng dưới ngưỡng, bằng ngưỡng và trên ngưỡng; kiểm tra phí vận chuyển sau khi chạy.
5. **Boundary test:** kiểm tra currency khác, giá trị null nếu được phép và lỗi khi dữ liệu không hợp lệ.
6. **Source-map check:** lỗi trong method được sinh có thể truy về dòng rule DSL.
7. **Determinism check:** sinh lại với cùng input và profile để xác nhận output ổn định.
8. **Artifact check:** xác nhận mọi class và metadata cần thiết có trong gói output.

Nếu compile thất bại vì `Money.zero` không tồn tại, đó có thể là lỗi mapping runtime API. Nếu compile thành công nhưng kết quả sai ở ngưỡng, cần xem lại semantics của phép so sánh hoặc cách biểu diễn tiền. Nếu chỉ sai source location, cần xem source-map builder.

## 19. Ví dụ tổng hợp: xác thực SQL output

DSL:

```text
query adultCustomers {
    from Customer
    where age >= minimumAge and status == ACTIVE
    select id, name
}
```

SQL được sinh:

```sql
SELECT id, name
FROM Customer
WHERE age >= ? AND status = ?
```

Các bước kiểm tra:

1. Parse theo SQL dialect được chọn.
2. Kiểm tra `Customer`, `age`, `status`, `id` và `name` tồn tại trong schema.
3. Xác nhận bind parameters có kiểu phù hợp.
4. Prepare statement trong database test.
5. Chạy trên fixture dữ liệu và so sánh kết quả với interpreter DSL.
6. Kiểm tra null semantics và collation nếu chúng ảnh hưởng kết quả.
7. Kiểm tra query plan nếu có yêu cầu hiệu năng.
8. Xác nhận input dữ liệu không được nối vào SQL text.

SQL parse được chưa chứng minh query đúng schema hoặc an toàn. Vì vậy cần nhiều tầng kiểm tra.

## 20. Kiểm thử mã đầu ra trong CI

CI có thể tự động hóa validation để mỗi thay đổi compiler hoặc DSL được kiểm tra nhất quán.

Một pipeline mẫu:

```text
Checkout source + dependencies
          |
          v
Run DSL frontend and semantic checks
          |
          v
Generate target artifacts
          |
          v
Validate file structure / schema
          |
          v
Compile / parse with target toolchain
          |
          v
Run conformance and runtime tests
          |
          v
Run security and reproducibility checks
          |
          v
Package validated artifact + metadata
```

### 20.1. Không bỏ qua lỗi kiểm tra

Nếu validation là điều kiện bắt buộc, CI phải trả trạng thái thất bại khi một bước quan trọng không đạt. Không nên ghi warning rồi tiếp tục đóng gói artifact không hợp lệ.

### 20.2. Phân biệt test bắt buộc và test bổ sung

Có thể phân loại kiểm tra theo mức độ:

- Required: parse, schema, compile và các test semantics cốt lõi.
- Extended: property-based, fuzzing, performance và security scans chuyên sâu.
- Environment-specific: database hoặc workflow engine trong staging.

Phân loại giúp thời gian CI hợp lý nhưng không được biến một kiểm tra correctness bắt buộc thành tùy chọn mà không có quyết định rõ.

### 20.3. Giữ artifact đã kiểm tra

Artifact nên được hash và lưu cùng metadata validation. Khi triển khai, dùng đúng artifact đó thay vì sinh lại ở bước sau với cấu hình có thể khác.

## 21. Fuzzing và kiểm tra độ bền của code generator

Fuzzing có thể tạo nhiều chương trình DSL hoặc AST đầu vào để tìm trường hợp khiến generator crash, treo, sinh output không parse được hoặc tạo hành vi bất thường.

### 21.1. Grammar-based fuzzing

Sinh input theo grammar giúp tạo nhiều chương trình gần với DSL hợp lệ. Có thể tập trung vào biểu thức lồng sâu, collection lớn, tên Unicode, literal biên và tổ hợp toán tử.

### 21.2. Mutation-based fuzzing

Bắt đầu từ chương trình hợp lệ rồi thay đổi token, kiểu, literal hoặc cấu trúc để kiểm tra compiler xử lý đầu vào gần sai như thế nào.

### 21.3. Kiểm tra invariant

Các invariant hữu ích:

- Generator không crash với AST hợp lệ.
- Output hợp lệ theo parser target.
- Mọi symbol được tham chiếu đều có mapping hoặc dependency.
- Output không vượt giới hạn tài nguyên đã quy định.
- Cùng input và cấu hình tạo output xác định.
- Runtime behavior giữ các tính chất semantics đã đặc tả.

Fuzzing bổ sung cho test có ví dụ; nó không thay thế bộ test nghiệp vụ và test conformance.

## 22. Hiệu năng của quá trình validation

Kiểm tra output có thể tốn thời gian, đặc biệt khi compile target, chạy database hoặc thực thi nhiều test.

Có thể quản lý chi phí bằng cách:

- Chạy kiểm tra rẻ trước kiểm tra đắt.
- Chỉ kiểm tra lại phần output bị ảnh hưởng nếu dependency graph cho phép.
- Cache kết quả theo hash input, compiler, target profile và toolchain.
- Chia test thành smoke, conformance và stress suites.
- Chạy độc lập các bước không phụ thuộc nhau song song.
- Dùng môi trường test tối giản nhưng tương thích với runtime thật.

Không nên bỏ qua kiểm tra semantics hoặc security chỉ vì chúng tốn thời gian. Có thể phân tầng thời điểm chạy, nhưng cần bảo đảm các bước bắt buộc vẫn xảy ra trước khi phát hành hoặc triển khai.

## 23. Những lỗi thường gặp khi kiểm tra mã đầu ra

| Sai lầm | Hậu quả | Cách khắc phục |
|---|---|---|
| Chỉ kiểm tra file tồn tại | Output có thể sai cú pháp hoặc semantics | Parse và compile bằng toolchain target |
| Chỉ compile mà không chạy test | Mã hợp cú pháp nhưng hành vi sai vẫn lọt | Dùng conformance và differential tests |
| Kiểm tra bằng sai target version | Kết quả không phản ánh môi trường triển khai | Khóa target profile và toolchain |
| So sánh text mà không xét semantics | Whitespace khác bị coi là lỗi hoặc lỗi hành vi bị bỏ qua | Kết hợp golden, compile và execution tests |
| Bỏ qua null và precision | Kết quả nghiệp vụ sai ở trường hợp biên | Kiểm thử kiểu, số học và giá trị thiếu |
| Dùng raw string cho SQL hoặc code | Injection và hỏng cấu trúc output | Parameterize và encode theo target |
| Không kiểm tra runtime dependency | Output compile được nhưng không load/run được | Kiểm tra link, load và runtime contract |
| Không kiểm tra source map | Lỗi target khó truy về DSL | Validate mapping và related spans |
| Không kiểm tra determinism | Diff và cache không ổn định | Sinh lặp và so sánh output/hash |
| Dùng output mới sinh thay cho artifact đã kiểm tra | Artifact triển khai có thể khác artifact validation | Hash và phát hành đúng artifact đã xác thực |
| Không phân loại lỗi | Người dùng không biết lỗi thuộc DSL hay backend | Diagnostic theo tầng và source mapping |

## 24. Nguyên tắc thiết kế kiểm tra mã đầu ra

Khi xây dựng compiler DSL, có thể áp dụng các nguyên tắc sau:

1. **Xác định output contract trước.** Nêu rõ target version, runtime, schema và giới hạn được hỗ trợ.
2. **Kiểm tra từ rẻ đến đắt.** Bắt đầu với file, syntax và schema trước compile và execution.
3. **Dùng công cụ thật của target.** Parse, compile, link hoặc load với đúng phiên bản và cấu hình triển khai.
4. **Kiểm tra semantics.** So sánh interpreter và generated output trên bộ test đại diện.
5. **Kiểm tra kiểu và trường hợp biên.** Bao gồm null, precision, overflow, đơn vị và thứ tự đánh giá.
6. **Kiểm tra an toàn.** Parameterize dữ liệu, encode theo context và giới hạn quyền khi chạy thử.
7. **Xác thực source map.** Bảo đảm lỗi trong output có thể truy về DSL.
8. **Kiểm tra nhiều file như một artifact.** Xác nhận manifest, dependency và metadata nhất quán.
9. **Bảo đảm tính xác định.** Kiểm tra output lặp lại và quản lý cache theo đầy đủ dependency.
10. **Phân loại diagnostic.** Phân biệt lỗi nguồn, lỗi lowering, lỗi backend, lỗi target và lỗi môi trường.
11. **Giữ artifact đã xác thực.** Dùng đúng output có hash và kết quả validation khi đóng gói hoặc triển khai.
12. **Tự động hóa trong CI.** Đặt các kiểm tra bắt buộc thành điều kiện để chấp nhận thay đổi hoặc phát hành.

## 25. Kết luận

Kiểm tra mã đầu ra xác nhận rằng sản phẩm của code generator đáp ứng hợp đồng target và giữ đúng ý nghĩa của DSL. Nó bao gồm kiểm tra cấu trúc, parse, schema, compile, link, runtime, semantics, bảo mật, source map, tính xác định và tính toàn vẹn của artifact.

Không có một bước kiểm tra đơn lẻ nào đủ để chứng minh mọi khía cạnh. Parse thành công chỉ nói đầu ra có cấu trúc cú pháp hợp lệ; compile thành công chỉ nói target compiler chấp nhận mã; chỉ các kiểm tra hành vi mới cung cấp bằng chứng rằng output thực hiện đúng semantics DSL trong những trường hợp đã kiểm tra.

Một pipeline validation hiệu quả cần bắt đầu từ output contract, dùng đúng toolchain target, kết hợp test cấu trúc với test ngữ nghĩa, bảo vệ ranh giới bảo mật và giữ source mapping để truy vết lỗi. Khi các bước này được tự động hóa và gắn với artifact cụ thể, code generation trở nên đáng tin cậy hơn và dễ bảo trì khi DSL hoặc target phát triển.
