# Sinh target

Trong quá trình xây dựng một ngôn ngữ chuyên biệt theo miền (Domain-Specific Language — DSL), người dùng thường viết các khai báo, biểu thức và quy tắc bằng cú pháp gần với nghiệp vụ. Để chương trình đó chạy được trên một nền tảng cụ thể, hệ thống có thể chuyển cấu trúc DSL sang mã của một ngôn ngữ khác, một dạng lệnh trung gian hoặc một định dạng mà runtime đích hiểu được. Quá trình tạo ra biểu diễn đích này được gọi là **sinh target (target code generation)**.

Sinh target là một bước quan trọng trong compiler DSL. Nó biến mô hình đã được phân tích và kiểm tra thành đầu ra có thể thực thi hoặc được công cụ khác xử lý. Target có thể là Java, Kotlin, JavaScript, SQL, bytecode, cấu hình triển khai, biểu diễn workflow hoặc một IR chuyên biệt. Lựa chọn target phụ thuộc mục tiêu của DSL, môi trường chạy, yêu cầu hiệu năng, khả năng tích hợp và mức độ kiểm soát mà compiler cần.

Một bộ sinh target tốt cần bảo toàn ngữ nghĩa của DSL, ánh xạ kiểu và thao tác chính xác, tạo mã an toàn, hỗ trợ chẩn đoán có thể truy ngược về nguồn và cho kết quả ổn định. Nó không chỉ ghép các chuỗi văn bản; nó chuyển một mô hình có cấu trúc thành một mô hình đích theo các quy tắc đã xác định.

## 1. Sinh target là gì?

Sinh target là quá trình chuyển AST hoặc biểu diễn trung gian của DSL thành một dạng đầu ra đích. Đầu ra có thể được biên dịch tiếp, thông dịch, nạp vào một engine hoặc triển khai trên hệ thống khác.

Ví dụ, DSL mô tả quy tắc miễn phí vận chuyển:

```text
rule freeShipping {
    when order.total >= 1_000_000 and order.status == PAID
    then shipping.fee = 0
}
```

Compiler có thể chuyển rule này thành mã Java, biểu thức SQL, cấu hình cho rule engine hoặc bytecode. Mỗi target có mô hình thực thi riêng, nhưng phải giữ cùng ý nghĩa đã định nghĩa cho rule.

### 1.1. Target không nhất thiết là ngôn ngữ lập trình

Từ “target” chỉ dạng đầu ra mà compiler hướng tới. Một số ví dụ:

| Target | Mục đích |
|---|---|
| Java/Kotlin/C# | Tích hợp vào ứng dụng JVM hoặc .NET |
| JavaScript/TypeScript | Chạy trong trình duyệt hoặc Node.js |
| SQL | Chuyển DSL truy vấn thành truy vấn cơ sở dữ liệu |
| Bytecode | Chạy trên VM hoặc runtime riêng |
| JSON/YAML | Sinh cấu hình cho hệ thống khác |
| Workflow definition | Chuyển mô hình quy trình thành định dạng của workflow engine |
| IR riêng | Chuẩn hóa chương trình trước khi tối ưu hoặc chạy trên nhiều backend |

Target cần có đặc tả cú pháp, kiểu, semantics và giới hạn rõ ràng. Ví dụ, sinh SQL phải xử lý null, thứ tự, kiểu số, collation và transaction theo cách tương thích với DSL.

### 1.2. Sinh mã và thực thi trực tiếp

Có hai hướng phổ biến:

- **Biên dịch:** DSL được chuyển thành target trước khi chạy. Target có thể được compiler khác biên dịch hoặc được nạp trực tiếp.
- **Thông dịch:** runtime đọc AST hoặc IR và thực hiện các node mà không nhất thiết sinh mã nguồn đích.

Một hệ thống có thể kết hợp cả hai: thông dịch trong chế độ phát triển để có lỗi nhanh, sinh target trong môi trường production để tối ưu hiệu năng hoặc tích hợp.

## 2. Vị trí của target generation trong pipeline

Một pipeline compiler DSL điển hình:

```text
Tệp nguồn DSL
      |
      v
Lexer và Parser
      |
      v
AST
      |
      v
Phân giải tên và kiểm tra ngữ nghĩa
      |
      v
Kiểm tra kiểu và ràng buộc miền
      |
      v
Chuẩn hóa / Lowering sang IR
      |
      v
Tối ưu hóa IR
      |
      v
Target Code Generator
      |
      v
Mã nguồn / bytecode / SQL / cấu hình
      |
      v
Compiler hoặc Runtime đích
```

Không phải compiler nào cũng cần tất cả các bước. DSL nhỏ có thể sinh target trực tiếp từ AST. Hệ thống lớn hoặc có nhiều target thường dùng IR trung gian để tách frontend khỏi backend.

### 2.1. Vì sao cần semantic analysis trước khi sinh target?

Parser chỉ biết cấu trúc cú pháp. Trước khi sinh mã, compiler cần biết tên tham chiếu đến symbol nào, biểu thức có kiểu gì và các phép toán có hợp lệ không.

Ví dụ `order.total + adjustment` có thể đúng cú pháp nhưng chưa đủ thông tin để sinh mã nếu chưa biết `total` là `Money`, `adjustment` là `Percentage` hay `Decimal`. Nếu compiler sinh mã trước khi phân giải kiểu, nó có thể chọn phép toán sai hoặc tạo target không biên dịch được.

### 2.2. AST và IR

AST thường phản ánh cấu trúc cú pháp và khái niệm của DSL. IR (Intermediate Representation) là biểu diễn trung gian được thiết kế để thuận tiện cho tối ưu hoặc sinh mã.

| Đặc điểm | AST | IR |
|---|---|---|
| Mục đích | Giữ cấu trúc chương trình theo ngôn ngữ nguồn | Biểu diễn thao tác theo dạng thuận tiện cho compiler/backend |
| Mức trừu tượng | Gần với cú pháp và khái niệm DSL | Có thể thấp hơn, rõ luồng điều khiển và kiểu hơn |
| Thông tin nguồn | Thường gắn source span và tên nguồn | Có thể giữ source mapping hoặc origin |
| Phụ thuộc target | Thường ít phụ thuộc target | Có thể độc lập target hoặc được thiết kế riêng cho backend |
| Ví dụ node | `Rule`, `When`, `Assignment` | `LoadField`, `Compare`, `Branch`, `Store` |

IR giúp nhiều backend dùng chung frontend. Compiler chỉ cần chuyển AST sang IR một lần; mỗi backend sau đó chuyển IR sang Java, SQL hoặc bytecode.

## 3. Xác định target và hợp đồng đầu ra

Trước khi viết code generator, cần xác định chính xác target là gì và đầu ra được tiêu thụ như thế nào.

Các câu hỏi quan trọng:

- Target là ngôn ngữ nguồn, bytecode, query hay định dạng cấu hình?
- Phiên bản target nào được hỗ trợ?
- Đầu ra có cần biên dịch tiếp không?
- Target runtime cung cấp những thư viện hoặc API nào?
- Có giới hạn nào về kiểu, precision, null, concurrency hoặc transaction?
- Mã được sinh thành một tệp, nhiều tệp hay package?
- Cần tạo metadata, manifest, source map hoặc schema đi kèm không?
- Người dùng có cần đọc và chỉnh sửa mã được sinh không?

Ví dụ, nếu target là Java 21, compiler có thể sử dụng record, sealed class hoặc pattern matching theo phiên bản được hỗ trợ. Nếu target là Java 8, các cấu trúc đó phải được hạ xuống dạng tương thích.

### 3.1. Target profile

Một compiler có thể định nghĩa target profile gồm:

| Thuộc tính | Ví dụ |
|---|---|
| Ngôn ngữ đích | Java |
| Phiên bản | Java 21 |
| Runtime library | `dsl-runtime` phiên bản tương thích |
| Encoding đầu ra | UTF-8 |
| Quy ước package | Theo module DSL |
| Null model | Optional hoặc kiểm tra null tường minh |
| Numeric model | Decimal có precision xác định |
| Error model | Exception hoặc Result type |
| Build integration | Gradle/Maven hoặc build system khác |

Việc xác định profile tránh tình trạng code generator vô tình dùng tính năng không được runtime đích hỗ trợ.

## 4. Kiến trúc của bộ sinh target

Một bộ sinh mã có thể được chia thành các thành phần:

```text
Compiler Frontend
       |
       v
Typed AST / IR
       |
       v
Target-independent lowering
       |
       v
Target Backend
       |
       +--> Type mapper
       +--> Expression emitter
       +--> Statement emitter
       +--> Runtime API mapper
       +--> Name mangler
       +--> Source map builder
       |
       v
Output files + metadata
```

### 4.1. Target-independent lowering

Bước lowering chuyển những khái niệm cấp cao của DSL thành thao tác cơ bản hơn mà nhiều backend có thể hiểu.

Ví dụ, `unless condition { action }` có thể được hạ thành `if not condition { action }`. Một `Rule` có thể được chuyển thành một hàm nhận context và trả về kết quả đánh giá.

### 4.2. Backend riêng cho từng target

Backend chịu trách nhiệm chuyển IR sang cú pháp và runtime cụ thể. Có thể có `JavaBackend`, `SqlBackend` và `BytecodeBackend` cùng nhận một IR.

Backend nên tập trung vào khác biệt của target như cách biểu diễn kiểu, lời gọi hàm, luồng điều khiển và API runtime. Quy tắc nghiệp vụ của DSL nên được giải quyết ở frontend hoặc IR khi có thể.

### 4.3. Runtime support library

Một số semantics của DSL khó hoặc không nên sinh thành mã thuần. Compiler có thể gọi thư viện runtime để xử lý:

- So sánh `Money` và quy đổi đơn vị.
- Logic ba giá trị với `true`, `false`, `unknown`.
- Kiểm tra quyền và context.
- Truy cập dữ liệu hoặc schema.
- Retry, transaction và workflow state.
- Diagnostic runtime và telemetry.

Runtime library là một phần của hợp đồng target. Phiên bản compiler và runtime phải tương thích.

## 5. Ánh xạ kiểu nguồn sang kiểu đích

Type mapping chuyển kiểu của DSL sang kiểu hoặc cấu trúc tương ứng ở target. Ánh xạ không phải lúc nào cũng một-một.

Ví dụ một bảng ánh xạ đơn giản sang Java:

| Kiểu DSL | Kiểu Java có thể dùng | Lưu ý |
|---|---|---|
| `Boolean` | `boolean` hoặc `Boolean` | Primitive không chứa null |
| `Integer` | `long` hoặc `BigInteger` | Chọn theo miền giá trị và overflow |
| `Decimal` | `BigDecimal` | Xác định precision và rounding |
| `String` | `String` | Quy định encoding ở I/O |
| `Date` | `LocalDate` | Ngày lịch, không chứa múi giờ |
| `Instant` | `Instant` | Thời điểm tuyệt đối |
| `Money` | Class runtime `Money` | Cần currency và phép toán miền |
| `List<T>` | `List<Target(T)>` | Kiểm soát mutability nếu cần |
| `Optional<T>` | `Optional<Target(T)>` hoặc nullable wrapper | Chọn null semantics thống nhất |
| Enum | `enum` hoặc value object | Giữ mapping tên và giá trị |

### 5.1. Kiểu số và overflow

Không nên ánh xạ mọi kiểu số DSL sang `double`. Nếu DSL cần số nguyên chính xác hoặc tiền tệ, `double` có thể gây sai số. Compiler cần chọn kiểu đích phù hợp và bảo toàn quy tắc overflow, chia, làm tròn.

Ví dụ, nếu DSL định nghĩa `Decimal` với precision cố định, target có thể dùng `BigDecimal` cùng helper runtime để áp dụng rounding mode thống nhất.

### 5.2. Nullability

Kiểu nullable trong DSL cần được ánh xạ có chủ đích. Nếu `Customer?` được ánh xạ sang một tham chiếu Java có thể null, backend cần sinh kiểm tra hoặc gọi helper tương ứng. Nếu dùng `Optional<Customer>`, mọi thao tác truy cập và gán cần được chuyển đổi phù hợp.

Không được xóa thông tin nullable trong quá trình lowering nếu semantics của DSL yêu cầu phân biệt giá trị thiếu với giá trị bình thường.

### 5.3. Kiểu miền

Các kiểu như `CustomerId`, `OrderId`, `Money` và `Percentage` có thể cùng được biểu diễn bằng chuỗi hoặc số, nhưng không nên bị gộp nếu DSL dựa vào chúng để ngăn nhầm lẫn nghiệp vụ.

Backend có thể sinh wrapper type riêng hoặc dùng class runtime. Chọn cách nào cần cân nhắc khả năng tương thích, chi phí, serialization và mức bảo đảm kiểu.

### 5.4. Generic và variance

Nếu DSL hỗ trợ generic, backend cần ánh xạ tham số kiểu và các ràng buộc của chúng. Một số target có type erasure hoặc mô hình generic khác DSL, nên compiler có thể cần sinh runtime checks hoặc metadata để giữ semantics.

## 6. Sinh biểu thức

Expression emitter chuyển các node biểu thức thành biểu thức target. Cần bảo đảm precedence và associativity của target không làm thay đổi cách nhóm của DSL.

Ví dụ AST:

```text
Add(
    Number(2),
    Multiply(Number(3), Number(4))
)
```

Target Java có thể là:

```java
2 + (3 * 4)
```

Target khác có thể yêu cầu dấu ngoặc hoặc helper function khác. Code generator nên dựa vào cấu trúc AST/IR để sinh dấu ngoặc cần thiết, không dựa vào nối chuỗi ngẫu nhiên.

### 6.1. Precedence và associativity

Ví dụ DSL:

```text
a - (b - c)
```

Nếu backend bỏ ngoặc và sinh `a - b - c`, semantics đổi thành `(a - b) - c`. Vì vậy, emitter cần biết precedence của node cha và node con, hoặc luôn thêm ngoặc theo cách an toàn.

Một cách đơn giản là sinh ngoặc quanh mọi biểu thức con. Cách này thường đúng nhưng có thể tạo mã nhiều ngoặc. Cách tối ưu hơn là dùng bảng precedence của target và chỉ thêm ngoặc khi cần.

### 6.2. Literal

Literal cần được escape và biểu diễn đúng kiểu target:

- String cần escape dấu nháy, dấu gạch chéo và ký tự điều khiển.
- Number cần giữ độ chính xác và định dạng hợp lệ.
- Date/time cần chuyển theo API target đã chọn.
- Enum cần tham chiếu đúng constant hoặc constructor.
- Null/None cần được biểu diễn theo mô hình nullability.

Không nên chèn raw text của literal vào target mà không qua encoder phù hợp. Ví dụ, chuỗi người dùng chứa `"` hoặc newline có thể làm hỏng mã nguồn nếu không được escape.

### 6.3. Truy cập thuộc tính

Node `MemberAccess(order, total)` có thể thành `order.getTotal()`, `order.total` hoặc `readField(order, TOTAL_ID)` tùy target và runtime. Mapping phải dựa trên symbol đã phân giải, không chỉ tên văn bản.

### 6.4. Gọi hàm

Node lời gọi hàm cần chuyển callee và đối số theo đúng chữ ký đã resolve. Nếu DSL hỗ trợ named arguments, default arguments hoặc overload, backend phải chuyển chúng thành lời gọi positional hoặc helper tương ứng mà vẫn giữ semantics.

### 6.5. Toán tử có overload hoặc semantics đặc biệt

Một phép `+` của DSL có thể có nghĩa cộng `Money`, nối chuỗi hoặc cộng số. Backend không nên luôn sinh ký hiệu `+`; nó cần dựa trên kiểu đã phân giải để chọn helper hoặc method đúng.

## 7. Sinh câu lệnh và luồng điều khiển

Statement emitter chuyển các node khai báo, gán, điều kiện, vòng lặp và khối thành cấu trúc tương ứng ở target.

### 7.1. Gán

DSL:

```text
shipping.fee = 0
```

Target có thể là:

```java
shipping.setFee(Money.zero(shipping.currency()));
```

Mapping cần xét property có setter hay không, kiểu của giá trị và semantics của phép gán. Nếu gán trong DSL tạo event hoặc command chứ không cập nhật trực tiếp, backend phải sinh API tương ứng.

### 7.2. Điều kiện

DSL:

```text
if order.isPaid {
    createShipment(order)
} else {
    holdOrder(order)
}
```

Java target:

```java
if (order.isPaid()) {
    createShipment(order);
} else {
    holdOrder(order);
}
```

Nếu DSL có logic ba giá trị, `if` không thể luôn ánh xạ trực tiếp sang `if` của Java. Compiler cần gọi helper hoặc sinh nhánh xử lý `UNKNOWN` theo semantics.

### 7.3. Vòng lặp

DSL có thể có `for each item in items`. Target có thể dùng enhanced for, iterator hoặc helper runtime. Cần giữ semantics về thứ tự, mutation, collection lazy và xử lý lỗi.

### 7.4. Return và break

Các cấu trúc thoát luồng phải được ánh xạ đúng phạm vi. Nếu DSL cho phép `break` trong nested workflow hoặc lambda, target cần xác định chính xác loop/block đích.

### 7.5. Khối và scope

Block trong DSL có thể tạo scope biến cục bộ. Backend cần sinh block target hoặc cách quản lý môi trường tương đương. Nếu hai biến DSL cùng tên ở hai scope khác nhau, name mangler phải tạo tên target không xung đột.

## 8. Lowering từ khái niệm DSL sang primitive target

DSL thường cung cấp cấu trúc cấp cao để người dùng diễn đạt ý định miền. Target có thể không có khái niệm tương ứng trực tiếp. Khi đó compiler thực hiện lowering.

Ví dụ `rule` có thể được chuyển thành một hàm đánh giá:

```text
RuleDeclaration
├── condition
└── action
       |
       v
Generated function:
    evaluate(context)
        if condition(context):
            execute action(context)
```

### 8.1. Desugaring

Desugaring chuyển cú pháp tiện dụng thành cấu trúc cốt lõi trước khi sinh target. Ví dụ `unless C { A }` có thể được hạ thành `if not C { A }` nếu hai cấu trúc có semantics tương đương.

### 8.2. Lowering cấu trúc nghiệp vụ

Một khai báo `entity` có thể được hạ thành class, record, schema hoặc descriptor. Một `workflow` có thể được hạ thành state machine. Một `query` có thể được hạ thành relational algebra rồi thành SQL.

### 8.3. Tách semantics khỏi cách biểu diễn target

Nếu một backend tự quyết định semantics của `Money`, `null` hoặc `and`, các backend có thể cho kết quả khác nhau. Nên xác định semantics trong frontend/IR hoặc runtime chung, sau đó backend chỉ biểu diễn chúng bằng cơ chế target tương ứng.

## 9. Sinh SQL từ DSL truy vấn

Sinh SQL là ví dụ rõ về việc target không chỉ là ngôn ngữ lập trình tổng quát. Giả sử DSL:

```text
query activeCustomers {
    from Customer
    where status == ACTIVE and age >= 18
    select id, name
    orderBy name ascending
}
```

Compiler có thể tạo SQL:

```sql
SELECT id, name
FROM Customer
WHERE status = ? AND age >= ?
ORDER BY name ASC
```

Các giá trị `ACTIVE` và `18` được truyền dưới dạng bind parameters, không nối trực tiếp vào chuỗi SQL.

### 9.1. SQL dialect

Các hệ quản trị cơ sở dữ liệu có khác biệt về cú pháp, kiểu, hàm, pagination, JSON và thời gian. Backend cần biết dialect đích như PostgreSQL, SQLite hoặc SQL Server.

### 9.2. Null semantics

SQL dùng logic ba giá trị trong điều kiện với `NULL`. Nếu DSL dùng Boolean hai giá trị hoặc có quy tắc null khác, backend cần chuyển đổi để giữ semantics hoặc từ chối biểu thức không thể ánh xạ an toàn.

### 9.3. Identifier và parameterization

Giá trị dữ liệu nên được bind parameter. Tên bảng, cột và identifier không thể thay bằng bind parameter theo cách tương tự; chúng cần được lấy từ symbol/schema đã xác thực và quote theo dialect.

Không được đưa raw identifier hoặc nội dung người dùng tùy ý vào SQL. Code generator phải dùng metadata đã phân giải và quy tắc quoting an toàn.

### 9.4. Biểu thức không thể đẩy xuống database

Không phải mọi hàm DSL đều có phép tương ứng trong SQL. Compiler có thể:

- Dịch sang SQL nếu semantics tương thích.
- Dùng user-defined function đã được đăng ký.
- Thực hiện một phần lọc ở runtime sau khi lấy dữ liệu.
- Báo lỗi compile nếu không thể biểu diễn đúng.

Không nên âm thầm thay hàm không hỗ trợ bằng biểu thức gần giống nhưng khác semantics.

## 10. Sinh target an toàn

Code generation là một ranh giới bảo mật quan trọng. Nếu compiler nối văn bản đầu vào trực tiếp vào mã đích, người dùng có thể tạo code injection hoặc phá cấu trúc target.

### 10.1. Escape literal

String literal cần được encode theo quy tắc target. Escape cho Java string khác escape cho SQL string, JSON hoặc JavaScript. Không nên dùng một hàm escape chung cho mọi target.

### 10.2. Không nối raw code từ dữ liệu

Giá trị người dùng nhập phải được biểu diễn như literal hoặc parameter. Chỉ những node đã được xác thực và có semantics rõ mới được phép sinh thành cấu trúc mã.

### 10.3. Identifier mangling

Tên trong DSL có thể là từ khóa của target, chứa ký tự không được phép hoặc trùng với tên compiler sinh. Name mangler cần chuyển tên thành định danh target hợp lệ và duy nhất.

Ví dụ DSL có biến `class`, nhưng `class` là từ khóa Java. Backend có thể sinh `class_` hoặc tên nội bộ được ánh xạ qua symbol table. Cần giữ mapping để diagnostic và debug vẫn hiển thị tên nguồn.

### 10.4. Không sinh mã từ biểu thức không được kiểm tra

Backend nên nhận typed AST hoặc IR đã được xác thực. Nếu nhận node lỗi hoặc symbol chưa phân giải, cần dừng với diagnostic nội bộ rõ ràng thay vì sinh target không xác định.

### 10.5. SQL injection và command injection

Với target là SQL, shell command hoặc template triển khai, parameterization và allowlist là bắt buộc. Không được xem chuỗi được quote đơn giản là đủ an toàn trong mọi context.

## 11. Source mapping và debug mã được sinh

Mã target thường khác nhiều so với mã DSL gốc. Khi runtime báo lỗi ở dòng target, người dùng cần biết lỗi bắt nguồn từ cấu trúc nào trong DSL.

Source mapping liên kết đoạn mã target với source span của node AST/IR.

Ví dụ:

```text
DSL source:
shipping.dsl:12
    shipping.fee = 0

Generated Java:
ShippingRules.java:48
    context.shipping().setFee(Money.zero());
```

Mapping có thể cho phép IDE hoặc runtime hiển thị lỗi ở `shipping.dsl:12` thay vì chỉ hiện dòng 48 của Java.

### 11.1. Metadata nguồn

Mỗi node IR có thể giữ source span và origin. Khi emitter sinh đoạn target, nó ghi nhận output range tương ứng với source range.

### 11.2. Source map theo định dạng chuẩn

Một số target có định dạng source map sẵn, ví dụ JavaScript source maps. Với target khác, compiler có thể tạo sidecar file chứa mapping hoặc comment metadata.

### 11.3. Node tổng hợp

Compiler có thể sinh nhiều dòng target từ một node DSL hoặc tạo node target không có dòng nguồn trực tiếp. Những đoạn này cần được đánh dấu synthetic hoặc liên kết với node gốc gần nhất để diagnostics có ý nghĩa.

### 11.4. Debug symbol và tên biến

Để debug dễ hơn, compiler có thể giữ tên biến DSL trong metadata, sinh debug symbols hoặc tạo mapping từ symbol DSL sang biến target. Điều này đặc biệt hữu ích khi tên đã bị mangling.

## 12. Tính xác định và khả năng tái lập

Cùng một chương trình DSL, cùng phiên bản compiler và cùng target profile nên tạo đầu ra giống nhau về mặt nội dung hoặc ít nhất tương đương theo một quy tắc xác định.

Những yếu tố có thể làm đầu ra không ổn định:

- Thứ tự duyệt map hoặc collection không xác định.
- Timestamp hoặc đường dẫn máy cục bộ được chèn vào mã.
- Random identifier không có seed cố định.
- Thứ tự module phụ thuộc cách liệt kê tệp.
- Phiên bản runtime hoặc thư viện target thay đổi.
- Locale ảnh hưởng định dạng số, ngày hoặc tên.

Để có reproducible output, compiler nên dùng thứ tự ổn định, định dạng locale độc lập, phiên bản target profile rõ ràng và tránh metadata không cần thiết.

### 12.1. Output ổn định và cache

Hash của đầu vào cùng dependency và cấu hình có thể dùng làm cache key. Nếu code generator có tính xác định, compiler có thể tái sử dụng output khi không có thành phần phụ thuộc nào thay đổi.

### 12.2. Tên tạm ổn định

Compiler có thể cần sinh biến tạm như `tmp1`, `tmp2`. Nên tạo chúng theo traversal ổn định hoặc symbol ID ổn định, để thay đổi không liên quan không làm toàn bộ output đổi tên.

## 13. Định dạng và tổ chức file đầu ra

Compiler cần quyết định đầu ra gồm những file nào và cấu trúc thư mục ra sao.

Ví dụ:

```text
generated/
├── src/
│   └── main/
│       └── java/
│           └── generated/
│               ├── Order.java
│               └── ShippingRules.java
├── resources/
│   └── dsl-metadata.json
└── source-maps/
    └── ShippingRules.map
```

### 13.1. Một file hay nhiều file

Có thể sinh một file cho mỗi module, mỗi entity hoặc gom nhiều rule vào một class. Quyết định phụ thuộc kích thước chương trình, khả năng incremental build, quy ước target và nhu cầu debug.

### 13.2. Package và namespace

Namespace DSL có thể được ánh xạ sang package target. Cần chuẩn hóa tên package, tránh xung đột và bảo đảm đường dẫn file phù hợp với target.

### 13.3. Encoding và newline

Đầu ra cần encoding và newline xác định. UTF-8 là lựa chọn phổ biến cho mã nguồn hiện đại. Formatter có thể chuẩn hóa indentation và newline để diff ổn định.

### 13.4. Atomic output

Khi sinh nhiều file, nên tránh để dự án ở trạng thái nửa cũ nửa mới nếu quá trình sinh thất bại giữa chừng. Có thể ghi vào thư mục tạm rồi thay thế output sau khi hoàn tất, hoặc dùng manifest để xác định tập file thuộc một lần build.

## 14. Sinh target cho nhiều backend

Một DSL có thể cần chạy trên nhiều nền tảng. Ví dụ, cùng một query DSL có thể sinh SQL cho PostgreSQL và code lọc trong memory cho môi trường test.

Kiến trúc có thể là:

```text
                DSL Source
                    |
                    v
              Frontend + IR
                /   |   \\
               v    v    v
          Java BE  SQL BE  Bytecode BE
             |       |        |
             v       v        v
          JVM App  Database  Custom VM
```

### 14.1. Semantics dùng chung

Các backend phải tuân thủ cùng semantics. Ví dụ, nếu DSL định nghĩa `and` short-circuit, backend SQL và Java phải xử lý theo quy tắc tương đương trong phạm vi target cho phép.

### 14.2. Khả năng biểu diễn của target

Không phải target nào cũng biểu diễn được mọi tính năng DSL. Compiler cần có capability model hoặc kiểm tra trước để biết backend hỗ trợ những node nào.

Ví dụ, backend SQL có thể không hỗ trợ gọi hàm tùy ý có tác dụng phụ. Thay vì sinh mã sai, compiler nên báo tính năng không được hỗ trợ hoặc yêu cầu một UDF đã đăng ký.

### 14.3. Backend-specific lowering

Một số phép biến đổi chỉ phù hợp với target cụ thể. Có thể giữ IR chung ở mức cao, sau đó chạy lowering riêng cho từng backend. Nhưng không nên để backend tự định nghĩa lại semantics của DSL.

## 15. Sinh target cho workflow và state machine

Với DSL workflow, target có thể là một định nghĩa state machine hoặc cấu hình cho orchestration engine.

Ví dụ DSL:

```text
workflow fulfillOrder {
    step validateOrder
    step chargePayment
    step prepareShipment
    step dispatchShipment
}
```

Compiler có thể sinh graph:

```text
START
  |
  v
validateOrder
  |
  v
chargePayment
  |
  v
prepareShipment
  |
  v
dispatchShipment
  |
  v
END
```

Backend cần ánh xạ retry, timeout, transition, compensation và persistence theo khả năng của workflow engine. Nếu DSL có transaction semantics mà target không hỗ trợ trực tiếp, compiler cần runtime adapter hoặc báo giới hạn.

## 16. Sinh target và tối ưu hóa

Code generator thường nhận IR đã tối ưu, nhưng một số tối ưu có thể được thực hiện trong backend vì phụ thuộc đặc tính target.

Các kỹ thuật có thể gặp:

- Constant folding: tính trước biểu thức hằng.
- Dead code elimination: loại bỏ nhánh không thể chạy.
- Common subexpression elimination: tái sử dụng phép tính lặp nếu an toàn.
- Inlining: thay lời gọi hàm bằng thân hàm khi phù hợp.
- Query optimization: chọn cách biểu diễn hoặc thứ tự phép toán phù hợp backend.
- Register allocation hoặc instruction selection nếu sinh bytecode/mã máy.

### 16.1. Bảo toàn semantics

Mọi tối ưu phải giữ hành vi quan sát được theo semantics DSL. Không được đổi thứ tự biểu thức có tác dụng phụ hoặc loại bỏ kiểm tra có thể phát sinh lỗi chỉ vì biểu thức trông dư thừa.

### 16.2. Tối ưu target-specific

Backend SQL có thể đẩy filter xuống database; backend JVM có thể tận dụng method call hoặc primitive; backend bytecode có thể chọn instruction cụ thể. Những tối ưu này nên được kiểm tra riêng cho từng target.

## 17. Quản lý lỗi trong quá trình sinh target

Code generation có thể thất bại nếu IR chưa hợp lệ, target không hỗ trợ một cấu trúc hoặc cấu hình backend thiếu thông tin.

Các loại lỗi thường gặp:

- Node AST/IR chưa được hạ xuống dạng backend hỗ trợ.
- Symbol chưa phân giải hoặc kiểu chưa xác định.
- Không có mapping cho kiểu miền.
- Target version không hỗ trợ tính năng cần sinh.
- Hàm DSL không có implementation hoặc runtime binding.
- Tên target xung đột hoặc không hợp lệ.
- Biểu thức không thể dịch sang target mà vẫn giữ semantics.
- Đường dẫn hoặc quyền ghi output không hợp lệ.

### 17.1. Phân biệt lỗi compiler và lỗi người dùng

Nếu người dùng viết một cấu trúc không được backend hỗ trợ, đó là diagnostic về khả năng target. Nếu compiler gặp một node nội bộ không thể xảy ra sau semantic analysis, đó có thể là lỗi nội bộ của compiler.

Thông báo nên phân biệt hai trường hợp để người dùng biết cần sửa DSL, đổi target profile hay báo lỗi compiler.

### 17.2. Không sinh output một phần như thể build thành công

Nếu backend thất bại giữa quá trình sinh nhiều file, output cần được đánh dấu không hoàn chỉnh hoặc giữ trong thư mục tạm. Không nên để công cụ build tiếp tục sử dụng một tập file trộn giữa phiên bản cũ và mới mà không cảnh báo.

## 18. Kiểm thử code generator

Kiểm thử sinh target không chỉ so sánh chuỗi đầu ra. Cần xác nhận mã sinh ra đúng cú pháp target và bảo toàn semantics DSL.

Các lớp kiểm thử hữu ích:

1. **Golden tests:** với một đầu vào DSL, so sánh output target với file chuẩn đã lưu.
2. **Compile tests:** biên dịch mã sinh ra bằng compiler target thật.
3. **Execution tests:** chạy output và so sánh kết quả với semantics mong đợi.
4. **Differential tests:** so sánh interpreter DSL với target được sinh từ cùng chương trình.
5. **Source map tests:** lỗi trong target phải trỏ được về nguồn DSL.
6. **Security tests:** chuỗi, identifier và dữ liệu độc hại không được phá cấu trúc target.
7. **Determinism tests:** cùng đầu vào và cấu hình phải sinh output ổn định.
8. **Backend conformance tests:** nhiều backend phải cho hành vi tương đương trong phạm vi tính năng chung.

### 18.1. Golden tests

Golden test hữu ích để phát hiện thay đổi định dạng hoặc mapping ngoài ý muốn. Tuy nhiên, thay đổi output không nhất thiết là thay đổi semantics; cần kết hợp compile và execution tests để đánh giá ý nghĩa.

### 18.2. Differential testing

Nếu có interpreter tham chiếu, chạy cùng input qua interpreter và target đã sinh. Kết quả phải tương đương theo mô hình quan sát của DSL. Cách này đặc biệt hữu ích khi có nhiều quy tắc kiểu, null, số học hoặc thứ tự đánh giá.

## 19. Ví dụ tổng hợp: sinh Java từ DSL rule

DSL nguồn:

```text
module shipping

rule freeShipping {
    when order.total >= Money(1_000_000, VND)
         and order.status == PAID
    then order.shippingFee = Money.zero(VND)
}
```

Giả sử semantic analysis đã xác nhận:

- `order` có kiểu `Order`.
- `total` và `shippingFee` có kiểu `Money`.
- `status` có kiểu `OrderStatus`.
- `VND` là currency hợp lệ.
- Điều kiện có kiểu Boolean.
- Rule được phép cập nhật `shippingFee`.

Target Java minh họa:

```java
package generated.shipping;

public final class ShippingRules {
    private ShippingRules() {}

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

Đây là dạng minh họa; API thực tế phụ thuộc runtime target. Một code generator cần xác định:

1. Package được ánh xạ từ module `shipping`.
2. Rule name được chuyển thành tên method hợp lệ.
3. `Money` được ánh xạ sang class runtime.
4. Phép so sánh tiền dùng `compareTo` thay vì so sánh object bằng `>=`.
5. `and` được ánh xạ sang `&&` nếu semantics hai giá trị tương thích.
6. `PAID` được ánh xạ đến enum constant.
7. Assignment được chuyển thành setter hoặc API cập nhật phù hợp.
8. Source map liên kết method và các dòng sinh ra với vị trí DSL.

Nếu DSL dùng logic ba giá trị, biểu thức điều kiện có thể không ánh xạ trực tiếp sang `boolean`; backend cần helper hoặc nhánh xử lý `UNKNOWN`.

## 20. Nguyên tắc thiết kế bộ sinh target

Khi xây dựng backend cho DSL, có thể áp dụng các nguyên tắc sau:

1. **Sinh từ AST/IR đã được xác thực.** Không dùng raw text làm nguồn duy nhất để tạo mã.
2. **Định nghĩa target profile.** Ghi rõ phiên bản, runtime, kiểu và giới hạn target.
3. **Tách frontend và backend.** Giữ semantics DSL ở một nơi, đưa khác biệt target vào backend.
4. **Ánh xạ kiểu có chủ đích.** Bảo toàn precision, nullability, đơn vị và kiểu miền.
5. **Giữ precedence và thứ tự đánh giá.** Sinh ngoặc, nhánh và lời gọi đúng semantics.
6. **Dùng encoder theo target.** Escape string, identifier và parameter đúng context.
7. **Không sinh cấu trúc không hỗ trợ.** Báo diagnostic khi target không thể biểu diễn semantics.
8. **Giữ source mapping.** Cho phép truy ngược lỗi target về DSL.
9. **Tạo output xác định.** Duy trì thứ tự và tên sinh ổn định để hỗ trợ cache và review.
10. **Quản lý runtime compatibility.** Compiler và runtime library cần có hợp đồng phiên bản.
11. **Kiểm soát output nhiều file.** Tránh để build thất bại tạo ra tập mã nửa cũ nửa mới.
12. **Kiểm thử hành vi.** Biên dịch và chạy output, không chỉ kiểm tra chuỗi được sinh.

## 21. Kết luận

Sinh target là quá trình chuyển AST hoặc IR của DSL thành mã nguồn, bytecode, SQL, cấu hình hoặc một dạng đầu ra khác mà hệ thống đích có thể xử lý. Nó là cầu nối giữa ngôn ngữ nguồn gần với miền nghiệp vụ và môi trường thực thi cụ thể.

Một bộ sinh target đáng tin cậy cần ánh xạ kiểu, biểu thức, câu lệnh và luồng điều khiển theo đúng semantics; xử lý null, số học và kiểu miền có chủ đích; dùng encoding an toàn; giữ source mapping; và tạo output ổn định. Khi hỗ trợ nhiều target, IR và runtime support chung giúp giảm lặp lại và giữ hành vi nhất quán.

Thiết kế tốt bắt đầu bằng việc xác định hợp đồng của target, sau đó xây dựng lowering và backend theo từng trách nhiệm rõ ràng. Mã được sinh chỉ có giá trị khi nó không chỉ hợp cú pháp target mà còn thực hiện đúng ý nghĩa mà người viết DSL đã biểu đạt.
