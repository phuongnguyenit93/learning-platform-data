# Transpilation

Trong thiết kế **Domain-Specific Language (DSL)**, một chương trình có thể được thực thi bằng interpreter, được biên dịch thành bytecode hoặc được chuyển thành mã của một ngôn ngữ khác. Quá trình chuyển đổi từ một ngôn ngữ nguồn sang một ngôn ngữ đích khác ở cùng mức biểu đạt thường được gọi là **transpilation** hoặc **source-to-source compilation**.

Ví dụ, một DSL mô tả quy tắc:

~~~text
rule "bulk-discount" {
    when order.quantity >= 10
    then order.discountRate = 0.15
}
~~~

có thể được chuyển thành mã TypeScript:

~~~typescript
function bulkDiscount(order: Order): void {
    if (order.quantity >= 10) {
        order.discountRate = 0.15;
    }
}
~~~

Mã đích vẫn là một chương trình có thể đọc, biên dịch hoặc chạy trên nền tảng khác. Transpiler chịu trách nhiệm chuyển cấu trúc và ngữ nghĩa của DSL sang những cấu trúc tương ứng ở ngôn ngữ đích.

Transpilation đặc biệt hữu ích khi DSL cần tận dụng hệ sinh thái của một ngôn ngữ chủ: compiler, runtime, thư viện, công cụ kiểm thử, debugger hoặc nền tảng triển khai. Tuy nhiên, việc tạo ra mã đích hợp lệ về cú pháp chưa đủ. Transpiler phải bảo toàn ý nghĩa của chương trình nguồn, quản lý khác biệt giữa hai hệ kiểu và mô hình thực thi, đồng thời cung cấp diagnostics có thể truy ngược về source DSL.

## 1. Transpilation là gì?

**Transpilation** là quá trình dịch một chương trình từ ngôn ngữ nguồn sang một ngôn ngữ đích khác, trong đó kết quả vẫn là chương trình hoặc biểu diễn mã ở mức tương đối cao, có thể tiếp tục được xử lý bởi toolchain của ngôn ngữ đích.

Một transpiler thường thực hiện:

1. Đọc source DSL.
2. Phân tích cú pháp và tạo AST.
3. Phân tích ngữ nghĩa: phân giải tên, kiểm tra kiểu và ràng buộc.
4. Chuyển AST hoặc semantic model thành một mô hình trung gian phù hợp.
5. Ánh xạ các cấu trúc DSL sang cấu trúc của ngôn ngữ đích.
6. Sinh source code đích.
7. Ghi source map, metadata hoặc thông tin debug nếu cần.
8. Có thể gọi compiler của ngôn ngữ đích để kiểm tra hoặc tạo artifact cuối.

Ví dụ luồng:

~~~mermaid
flowchart TD
    A[DSL source] --> B[Lexer and parser]
    B --> C[Source AST]
    C --> D[Semantic analysis]
    D --> E[Typed semantic model]
    E --> F[Target IR]
    F --> G[Code generator]
    G --> H[Target source]
    H --> I[Target compiler or runtime]
~~~

Transpiler không nhất thiết phải chuyển từng dòng source thành một dòng target. Một khai báo DSL có thể được mở rộng thành nhiều hàm, class, lời gọi thư viện hoặc đoạn mã quản lý trạng thái ở ngôn ngữ đích.

## 2. Phân biệt transpiler, compiler và interpreter

Các thuật ngữ này có phần giao nhau, nhưng mô tả những cách xử lý khác nhau:

- **Compiler** chuyển chương trình sang một dạng biểu diễn khác để tiếp tục xử lý hoặc thực thi. Đích có thể là mã máy, bytecode, IR hoặc source của ngôn ngữ khác.
- **Transpiler** là compiler có đích là một ngôn ngữ hoặc dạng mã nguồn khác, thường ở mức trừu tượng tương đương.
- **Interpreter** đọc source hoặc AST và trực tiếp thực hiện chương trình theo ngữ nghĩa của ngôn ngữ nguồn, không nhất thiết tạo source đích.

Ví dụ:

| Cách xử lý | Đầu vào | Đầu ra |
|---|---|---|
| Interpreter | DSL source hoặc AST | Kết quả thực thi |
| Transpiler | DSL source | Source của ngôn ngữ đích |
| Compiler native | DSL source hoặc IR | Mã máy hoặc executable |
| Compiler bytecode | DSL source hoặc IR | Bytecode |

Một hệ thống có thể kết hợp các cách này. Transpiler sinh TypeScript, sau đó TypeScript compiler tạo JavaScript; JavaScript runtime cuối cùng thực thi mã. Trong trường hợp đó, transpilation là một bước trong pipeline biên dịch lớn hơn.

## 3. Vì sao chuyển DSL sang ngôn ngữ khác?

### 3.1. Tận dụng hệ sinh thái đã có

Thay vì tự xây dựng toàn bộ runtime, thư viện, debugger và bộ triển khai, DSL có thể chuyển sang một ngôn ngữ có toolchain trưởng thành.

Ví dụ, DSL tạo giao diện có thể transpile sang TypeScript/JavaScript để chạy trên trình duyệt; DSL truy vấn có thể sinh SQL; DSL mô tả workflow có thể sinh cấu hình hoặc mã gọi API của nền tảng điều phối.

### 3.2. Triển khai trên nhiều nền tảng

Nếu có backend phù hợp, cùng một DSL có thể sinh mã cho nhiều target:

- TypeScript/JavaScript cho trình duyệt hoặc Node.js.
- Java hoặc Kotlin cho JVM.
- C# cho .NET.
- Python cho môi trường phân tích dữ liệu.
- SQL cho hệ quản trị cơ sở dữ liệu.
- C hoặc Rust cho môi trường native hoặc embedded.

Không phải mọi DSL đều có thể hỗ trợ mọi target. Mỗi backend cần triển khai đầy đủ ngữ nghĩa và capability mà chương trình nguồn yêu cầu.

### 3.3. Tích hợp với ứng dụng chủ

Một DSL rule có thể được chuyển thành class hoặc function của ngôn ngữ chủ. Ứng dụng có thể gọi mã đó như gọi module thông thường, truyền object miền và nhận kết quả.

### 3.4. Hiệu năng và khả năng tối ưu

Mã đích có thể được compiler nền tảng tối ưu, inline, phân tích kiểu hoặc biên dịch trước. Tuy nhiên, transpilation không tự động làm chương trình nhanh hơn. Chất lượng kết quả phụ thuộc vào cách ánh xạ, chi phí runtime helper và khả năng tối ưu của toolchain đích.

### 3.5. Giảm chi phí xây dựng runtime riêng

Nếu ngôn ngữ đích đã cung cấp quản lý bộ nhớ, exception, scheduler hoặc thư viện chuẩn phù hợp, transpiler có thể tái sử dụng chúng. Những khác biệt ngữ nghĩa vẫn cần được xử lý bằng code generation hoặc runtime support.

## 4. Kiến trúc tổng thể của một transpiler

Một kiến trúc điển hình có các thành phần:

~~~mermaid
flowchart TD
    A[DSL files] --> B[Lexer]
    B --> C[Parser]
    C --> D[AST]
    D --> E[Name and type analysis]
    E --> F[Semantic model]
    F --> G[Lowering]
    G --> H[Target-independent IR]
    H --> I[Target-specific backend]
    I --> J[Code emitter]
    J --> K[Generated source]
    K --> L[Target toolchain]
    L --> M[Executable or deployable artifact]
    F --> N[Diagnostics and source mapping]
    J --> N
~~~

Các thành phần có trách nhiệm riêng:

- Frontend hiểu cú pháp và ngữ nghĩa DSL.
- Semantic model ghi nhận ý nghĩa đã resolve.
- Lowering chuyển cấu trúc cấp cao thành các thao tác đơn giản hơn.
- IR biểu diễn chương trình theo cách phù hợp cho nhiều backend.
- Backend ánh xạ IR sang một target cụ thể.
- Emitter tạo source code có định dạng hợp lệ.
- Source mapping liên kết kết quả đích với vị trí source ban đầu.

Với DSL nhỏ, frontend có thể sinh target code trực tiếp từ AST. Khi DSL lớn hoặc có nhiều target, semantic model và IR riêng giúp giảm sự phụ thuộc giữa cú pháp nguồn với từng backend.

## 5. Frontend: phân tích source DSL

Frontend thực hiện các bước giống một compiler thông thường.

### 5.1. Lexical analysis

Lexer chuyển chuỗi ký tự thành token, chẳng hạn identifier, keyword, literal, operator và dấu phân cách.

Ví dụ:

~~~text
discount = price * 0.1
~~~

có thể tạo chuỗi token:

~~~text
IDENTIFIER(discount)
EQUAL
IDENTIFIER(price)
STAR
NUMBER(0.1)
~~~

Mỗi token nên giữ source span hoặc vị trí dòng/cột để diagnostics và source map có thể trỏ về source gốc.

### 5.2. Parsing và AST

Parser xác nhận cấu trúc theo grammar và tạo AST. Ví dụ:

~~~text
Assign(
    Name("discount"),
    Multiply(
        Name("price"),
        Number(0.1)
    )
)
~~~

AST loại bỏ chi tiết cú pháp không cần thiết cho việc dịch, nhưng cần giữ metadata đủ để tái hiện lỗi và vị trí source. Nếu formatter hoặc công cụ refactoring cần giữ comment và dấu ngoặc, có thể duy trì thêm Concrete Syntax Tree (CST) hoặc trivia.

### 5.3. Semantic analysis

Frontend cần resolve tên, kiểm tra kiểu, kiểm tra overload và xác nhận các ràng buộc của DSL trước khi sinh mã.

Ví dụ, nếu price có kiểu Money và 0.1 là Decimal, frontend cần biết phép nhân đó có hợp lệ và kiểu kết quả là gì. Nếu DSL quy định Money có đơn vị tiền tệ, phép nhân có thể cần một quy tắc riêng thay vì sinh phép nhân số học trực tiếp.

Backend không nên tự đoán ý nghĩa của tên chưa resolve hoặc biểu thức sai kiểu. Nó nên nhận semantic model đã có đủ thông tin hoặc nhận các node lỗi có đánh dấu rõ để phục vụ chế độ IDE.

## 6. Ánh xạ ngữ nghĩa sang ngôn ngữ đích

Đây là phần cốt lõi của transpilation. Mỗi cấu trúc DSL cần được ánh xạ sang một hoặc nhiều cấu trúc target sao cho hành vi quan sát được được bảo toàn.

Ví dụ:

| Cấu trúc DSL | Cấu trúc target có thể dùng |
|---|---|
| Biến và hằng | Variable hoặc constant |
| Hàm | Function hoặc method |
| Record/schema | Type, interface hoặc class |
| Điều kiện | if/else hoặc biểu thức điều kiện |
| Vòng lặp | Loop hoặc iterator |
| Rule | Predicate kết hợp action |
| Workflow step | Function/task cùng dependency metadata |
| Kiểu optional | Nullable type, Option hoặc wrapper |
| Pattern matching | switch, match hoặc chuỗi kiểm tra |

Không phải ánh xạ nào cũng là một-một. Một cấu trúc DSL có thể cần nhiều target node để mô phỏng hành vi của nó. Ví dụ, một workflow step có retry và timeout có thể được sinh thành function wrapper, policy object và lời gọi scheduler.

### 6.1. Bảo toàn ngữ nghĩa

Gọi \(P\) là chương trình nguồn và \(T(P)\) là chương trình được transpile. Mục tiêu là:

\[
\llbracket P \rrbracket_{DSL}
\approx
\llbracket T(P) \rrbracket_{Target}
\]

Ký hiệu \(\approx\) biểu thị hai chương trình tương đương theo những hành vi được DSL quy định và có thể quan sát. Hai bên không nhất thiết có cùng cấu trúc nội bộ hoặc cùng cách quản lý bộ nhớ.

Các hành vi cần xem xét có thể gồm:

- Giá trị trả về.
- Thay đổi trạng thái.
- Thứ tự đánh giá.
- Exception và lỗi miền.
- I/O và side effect.
- Thời gian hoặc scheduling nếu DSL quy định.
- Quyền truy cập và giới hạn capability.

Một phép dịch chỉ đúng nếu nó bảo toàn các hành vi thuộc hợp đồng của DSL.

## 7. Thiết kế target language

Trước khi viết backend, cần chọn target và xác định phạm vi tính năng được hỗ trợ.

### 7.1. Chọn target theo môi trường sử dụng

Các yếu tố:

- Nền tảng triển khai hiện có.
- Ngôn ngữ chủ mà ứng dụng tích hợp.
- Runtime và thư viện cần thiết.
- Hiệu năng, startup và memory footprint.
- Khả năng debug và quan sát.
- Mức độ an toàn kiểu.
- Khả năng phân phối và cập nhật.

### 7.2. Target có thể là ngôn ngữ hoặc định dạng chuyên biệt

Transpilation không chỉ giới hạn ở ngôn ngữ lập trình tổng quát. Ví dụ:

- DSL query sang SQL.
- DSL build sang cấu hình build tool.
- DSL giao diện sang HTML/CSS/JavaScript.
- DSL workflow sang cấu hình scheduler.
- DSL hạ tầng sang manifest triển khai.

Với các target dạng khai báo như SQL hoặc YAML, backend cần bảo toàn semantics của DSL trong mô hình truy vấn hoặc cấu hình đích. Việc sinh văn bản đúng cú pháp vẫn chưa bảo đảm target có cùng hành vi trên mọi engine.

### 7.3. Một hay nhiều backend

Nếu chỉ có một target ổn định, backend trực tiếp từ semantic model có thể đủ. Nếu có nhiều target, nên dùng IR độc lập với target để tránh lặp lại frontend và semantic analysis.

## 8. Intermediate Representation (IR)

**Intermediate Representation** là mô hình trung gian biểu diễn chương trình sau khi đã hiểu cú pháp và một phần hoặc toàn bộ ngữ nghĩa. IR giúp tách frontend khỏi backend.

Ví dụ DSL:

~~~text
let total = subtotal + tax
if total > limit {
    approve()
}
~~~

Một IR đơn giản:

~~~text
Declare total
    Add
        Load subtotal
        Load tax

BranchGreaterThan total, limit
    Then:
        Call approve
~~~

IR có thể được thiết kế theo:

- **High-level IR:** giữ các khái niệm DSL như rule, workflow, schema.
- **Lower-level IR:** biểu diễn thao tác đơn giản như load, store, branch, call.
- **SSA form:** mỗi biến được gán một lần, hỗ trợ phân tích và tối ưu.
- **Graph IR:** phù hợp với dependency, dataflow hoặc workflow.
- **Target-oriented IR:** gần với khả năng của một nền tảng cụ thể.

### 8.1. Khi nào cần IR?

IR hữu ích khi:

- Có nhiều backend.
- Cần tối ưu độc lập với ngôn ngữ đích.
- DSL có cấu trúc cấp cao cần lowering nhiều bước.
- Cần phân tích dependency hoặc control flow.
- Muốn kiểm thử frontend và backend riêng.

Với DSL nhỏ, một IR quá phức tạp có thể làm tăng chi phí không cần thiết. Cần chọn mức trừu tượng đủ để biểu diễn ngữ nghĩa và phục vụ các target dự kiến.

## 9. Lowering: chuyển cấu trúc cấp cao thành thao tác đơn giản

**Lowering** là quá trình chuyển một cấu trúc trừu tượng hoặc cấp cao sang dạng biểu diễn đơn giản hơn. Nó thường diễn ra giữa semantic model và target code generation.

Ví dụ DSL có cấu trúc:

~~~text
retry 3 times {
    call service()
}
~~~

Nếu target không có cấu trúc retry tương ứng, lowering có thể tạo vòng lặp và xử lý lỗi:

~~~typescript
let attempt = 0;
while (attempt < 3) {
    try {
        service();
        break;
    } catch (error) {
        attempt += 1;
        if (attempt >= 3) throw error;
    }
}
~~~

Đây chỉ là một cách mô phỏng. Cần xác định chính xác DSL đếm lần thử như thế nào, lỗi nào được retry, thời gian chờ và hành vi khi hủy. Nếu DSL có retry policy phức tạp, lowering có thể tạo một helper từ runtime library thay vì sinh toàn bộ logic lặp lại cho mỗi node.

Lowering giúp backend tập trung vào một tập cấu trúc nhỏ hơn, nhưng mỗi bước lowering phải bảo toàn semantics.

## 10. Sinh mã đích (code generation)

Code generator chuyển IR hoặc semantic model thành source code của target.

Các trách nhiệm:

- Chọn cú pháp target hợp lệ.
- Sinh tên biến, hàm và module.
- Sinh literal và biểu thức.
- Sinh cấu trúc điều khiển.
- Chèn runtime helper khi cần.
- Quản lý import và dependency.
- Giữ mapping từ target node tới source span.
- Định dạng output ổn định và có thể đọc.

### 10.1. Sinh biểu thức

DSL:

~~~text
total = base + quantity * price
~~~

TypeScript:

~~~typescript
total = base + quantity * price;
~~~

Nếu precedence của hai ngôn ngữ giống nhau, có thể giữ cấu trúc bằng biểu thức tương ứng. Nếu khác, emitter phải thêm ngoặc để bảo toàn AST.

### 10.2. Sinh câu lệnh

DSL:

~~~text
if eligible {
    approve(order)
} else {
    reject(order)
}
~~~

Target:

~~~typescript
if (eligible) {
    approve(order);
} else {
    reject(order);
}
~~~

### 10.3. Sinh tên

Tên trong DSL có thể không hợp lệ hoặc trùng từ khóa trong target. Ví dụ, DSL có thể cho phép class làm tên trường nhưng TypeScript dùng class làm keyword trong nhiều ngữ cảnh.

Backend cần một quy tắc name mangling hoặc escaping ổn định. Đồng thời, cần giữ bảng ánh xạ giữa tên DSL và tên target để diagnostics và debugger hiển thị tên nguồn.

## 11. Bảo toàn precedence và associativity khi sinh biểu thức

Một lỗi thường gặp của transpiler là sinh chuỗi biểu thức mà không giữ cấu trúc AST.

Ví dụ DSL:

~~~text
a * (b + c)
~~~

Nếu emitter bỏ ngoặc và sinh:

~~~typescript
a * b + c
~~~

thì target hiểu thành (a * b) + c, khác với source. Emitter cần biết precedence của từng node và thêm ngoặc khi biểu thức con có độ ưu tiên thấp hơn ngữ cảnh cha.

Một thuật toán in biểu thức có thể nhận parentPrecedence:

~~~text
emitExpression(node, parentPrecedence):
    ownPrecedence = precedenceOf(node)
    text = emitNode(node)

    if ownPrecedence < parentPrecedence:
        return "(" + text + ")"

    return text
~~~

Trong thực tế cần xét associativity, vị trí trái/phải và toán tử non-associative. Chỉ so sánh một con số precedence có thể chưa đủ cho mọi trường hợp.

## 12. Khác biệt hệ kiểu giữa source và target

Hai ngôn ngữ có thể có hệ kiểu rất khác nhau. Transpiler cần ánh xạ kiểu nguồn sang kiểu đích hoặc tạo wrapper để mô phỏng hành vi.

Ví dụ:

| Kiểu DSL | Kiểu target có thể dùng |
|---|---|
| Integer | number, bigint, int hoặc long |
| Decimal chính xác | decimal library hoặc kiểu decimal của target |
| Boolean | boolean |
| String | string |
| Optional<T> | T?, Option<T> hoặc wrapper |
| List<T> | Array<T>, List<T> hoặc collection tương ứng |
| Record | interface, struct hoặc class |
| Duration | duration type hoặc số kèm unit |

### 12.1. Số học và độ chính xác

Nếu DSL định nghĩa Decimal chính xác nhưng target JavaScript dùng number theo IEEE 754, sinh phép tính trực tiếp có thể làm thay đổi kết quả. Backend có thể cần dùng decimal library hoặc runtime helper.

Ví dụ:

~~~text
money = price * quantity
~~~

Nếu Money có quy tắc làm tròn theo đơn vị tiền tệ, target code cần áp dụng đúng quy tắc đó. Không nên giả định mọi phép toán số ở hai ngôn ngữ có cùng overflow, rounding và precision.

### 12.2. Nullability và optional

DSL có thể phân biệt rõ T và T?. Target có thể có null hoặc undefined với semantics khác. Transpiler cần chọn representation và kiểm tra phù hợp, có thể dùng wrapper Option hoặc runtime check.

### 12.3. Kiểu miền

CustomerId và OrderId có thể cùng biểu diễn bằng String nhưng có ý nghĩa khác nhau. Nếu DSL dùng nominal type, target nên giữ ranh giới đó bằng branded type, wrapper hoặc class thay vì hạ tất cả về string thuần.

### 12.4. Generic và variance

Nếu source và target có quy tắc variance khác nhau, backend cần bảo đảm các thao tác đọc/ghi collection vẫn an toàn. Không thể chỉ sao chép generic annotation mà bỏ qua hợp đồng kiểu.

## 13. Khác biệt control flow và evaluation order

Transpiler phải xem xét cách source và target thực hiện điều kiện, vòng lặp, exception và biểu thức có hiệu ứng.

Ví dụ DSL có short-circuit:

~~~text
isAuthorized and loadRecord()
~~~

Nếu target && cũng short-circuit với cùng thứ tự, có thể ánh xạ trực tiếp. Nếu target không có semantics tương đương, cần sinh cấu trúc điều kiện tường minh.

Các trường hợp cần xem xét:

- Thứ tự đánh giá toán hạng.
- Short-circuit của AND/OR.
- Vòng lặp và phạm vi của break/continue.
- Exception và finally/cleanup.
- Return trong closure hoặc nested function.
- Async/await và cancellation.
- Iterator có side effect.
- Thứ tự duyệt collection.

Ví dụ, nếu DSL quy định vòng lặp duyệt snapshot của collection nhưng target iterator nhìn thấy phần tử mới được thêm trong lúc duyệt, sinh vòng lặp trực tiếp có thể đổi hành vi. Backend cần mô phỏng snapshot hoặc dùng helper tương ứng.

## 14. Runtime support và helper library

Không phải cấu trúc DSL nào cũng có tương đương trực tiếp trong target. Một **runtime support library** cung cấp hàm hoặc kiểu hỗ trợ để mô phỏng semantics.

Ví dụ DSL:

~~~text
duration = 5 minutes
money = 10.25 USD
retry policy = exponentialBackoff(maxAttempts = 4)
~~~

Target có thể dùng:

~~~typescript
const duration = Runtime.duration(5, "minutes");
const money = Runtime.money("10.25", "USD");
const retryPolicy = Runtime.exponentialBackoff({ maxAttempts: 4 });
~~~

Runtime helper có thể cung cấp:

- Kiểu dữ liệu đặc thù.
- So sánh và chuyển kiểu.
- Arithmetic chính xác.
- Date/time và timezone.
- Pattern matching.
- Retry, timeout và scheduling.
- Serialization.
- Error types.
- Capability bridge.

### 14.1. Hợp đồng giữa generated code và runtime

Generated code cần biết helper nào tồn tại, chữ ký và version của chúng. Manifest hoặc package metadata có thể ghi dependency runtime.

Nếu code generator sinh lời gọi Runtime.money, nhưng runtime package không export hàm đó hoặc đổi semantics, chương trình sẽ không build hoặc chạy đúng. Vì vậy, runtime API là một phần của hợp đồng transpilation.

### 14.2. Khi nào sinh inline code, khi nào gọi helper?

Inline code có thể giảm dependency và giúp target compiler tối ưu, nhưng làm output dài và dễ lặp logic. Helper tập trung semantics và dễ cập nhật, nhưng tạo dependency và chi phí gọi.

Lựa chọn phụ thuộc:

- Mức độ phức tạp của semantics.
- Tần suất dùng cấu trúc.
- Yêu cầu hiệu năng.
- Khả năng debug generated code.
- Chính sách versioning.

## 15. Module, import và dependency

DSL có thể có module, package hoặc thư viện riêng. Transpiler cần ánh xạ chúng sang hệ module của target.

Ví dụ:

~~~text
module billing {
    import customer.Customer
    export function invoiceFor(customer: Customer) { ... }
}
~~~

Backend TypeScript có thể sinh:

~~~typescript
import { Customer } from "../customer/Customer";

export function invoiceFor(customer: Customer) {
    // generated implementation
}
~~~

Những vấn đề cần xác định:

- Quy tắc module path và tên file.
- Export/import mặc định.
- Namespace và alias.
- Chu trình phụ thuộc.
- Visibility và access modifier.
- Cách resolve package version.
- Cách đóng gói runtime helper.

Nếu target có quy tắc module khác source, transpiler cần tạo module wrapper hoặc barrel file để bảo toàn visibility và tên public.

## 16. Sinh mã cho nhiều target

Một DSL có thể có nhiều backend:

~~~mermaid
flowchart TD
    A[DSL source] --> B[Frontend]
    B --> C[Semantic model]
    C --> D[Common IR]
    D --> E[TypeScript backend]
    D --> F[Java backend]
    D --> G[SQL backend]
    E --> H[JavaScript toolchain]
    F --> I[JVM toolchain]
    G --> J[Database engine]
~~~

### 16.1. Chia sẻ frontend

Các backend dùng chung lexer, parser, name resolution, type checking và semantic model. Điều này giúp các target bắt đầu từ cùng một cách hiểu source.

### 16.2. Backend theo capability

Không phải mọi target đều hỗ trợ mọi tính năng. Có thể định nghĩa capability:

| Capability DSL | TypeScript | Java | SQL |
|---|---|---|---|
| Biểu thức số học | Có | Có | Có, tùy kiểu |
| Workflow scheduling | Cần runtime | Cần runtime | Thường không trực tiếp |
| Transaction query | Qua client | Qua client | Có thể biểu diễn |
| Async task | Có | Có | Phụ thuộc engine |
| Object method | Có | Có | Không tương đương trực tiếp |

Backend cần báo lỗi có ý nghĩa nếu chương trình dùng tính năng không được target hỗ trợ. Không nên âm thầm bỏ qua một cấu trúc nguồn.

### 16.3. Tương thích ngữ nghĩa giữa các backend

Nếu cùng một DSL được dịch sang hai target, cả hai cần tuân theo cùng đặc tả. Có thể dùng bộ test ngữ nghĩa chung để chạy source DSL trên từng backend và so sánh kết quả.

## 17. Source map và truy vết về source DSL

Sau transpilation, lỗi có thể xuất hiện trong file target:

~~~text
generated/pricing.ts:48:17
Type 'string' is not assignable to type 'number'.
~~~

Người viết DSL cần biết lỗi bắt nguồn từ đâu trong source. **Source map** lưu ánh xạ giữa vị trí trong mã đích và vị trí trong source ban đầu.

Một mapping có thể chứa:

- File nguồn.
- Dòng và cột trong DSL.
- File đích.
- Dòng và cột trong generated code.
- Tên symbol hoặc node tương ứng.
- Metadata phục vụ debugger.

Sơ đồ:

~~~mermaid
flowchart LR
    A[DSL source span] --> B[AST node]
    B --> C[IR node]
    C --> D[Generated target span]
    D --> E[Source map]
    E --> F[Diagnostic shown in DSL editor]
~~~

Source map hữu ích cho:

- Hiển thị lỗi compile của target tại dòng DSL.
- Debugger đặt breakpoint trong source DSL.
- Stack trace hiển thị tên hàm và vị trí gốc.
- Coverage report ánh xạ về cấu trúc DSL.
- Profiling cho biết phần source nào tiêu tốn thời gian.

Nếu một node DSL được mở rộng thành nhiều đoạn target, mapping có thể là quan hệ một-nhiều. Nếu một đoạn target được tạo từ nhiều node DSL, mapping có thể cần giữ nhiều source location hoặc chọn location chính.

## 18. Diagnostics trong transpiler

Lỗi có thể xảy ra ở nhiều giai đoạn:

| Giai đoạn | Ví dụ |
|---|---|
| Lexer/parser | Token không hợp lệ, thiếu dấu ngoặc |
| Name resolution | Biến hoặc resource không tồn tại |
| Type checking | Gán kiểu không tương thích |
| Lowering | Cấu trúc DSL không thể hạ xuống IR |
| Backend | Target không hỗ trợ capability |
| Code emission | Tên target không hợp lệ hoặc output không thể tạo |
| Target compiler | Generated code có lỗi kiểu hoặc cú pháp |

Một diagnostic tốt nên:

- Nêu lỗi bằng khái niệm của DSL khi có thể.
- Chỉ vị trí source DSL.
- Cung cấp thông tin target khi lỗi bắt nguồn từ backend.
- Gợi ý cách sửa mà không che giấu nguyên nhân.
- Phân biệt lỗi source với lỗi toolchain đích.

Ví dụ:

~~~text
pricing.dsl:12:9
The target backend cannot represent exact Decimal arithmetic
without the decimal runtime library.
Enable the decimal runtime feature or choose a compatible backend.
~~~

Thay vì chỉ hiển thị lỗi từ TypeScript về một phép toán được sinh tự động, transpiler có thể giải thích giới hạn ở cấp DSL.

## 19. Debugging generated code

Generated code có thể được đọc trực tiếp để hỗ trợ debug, nhưng không nên yêu cầu người dùng phải hiểu mọi chi tiết của backend.

Các tính năng hữu ích:

- Chế độ emit code có định dạng dễ đọc.
- Comment chỉ ra source DSL tương ứng.
- Tên biến target ổn định và dễ truy vết.
- Source map.
- Debug metadata cho function, block và expression.
- Tùy chọn giữ artifact trung gian.
- Hiển thị cả source DSL và generated code trong IDE.

Ví dụ comment:

~~~typescript
// Generated from pricing.dsl:12
if (order.quantity >= 10) {
    order.discountRate = 0.15;
}
~~~

Comment hỗ trợ người đọc nhưng không thay thế source map vì comment có thể bị formatter, bundler hoặc optimizer loại bỏ.

## 20. Định dạng output và tính tái lập

Code generator nên tạo output ổn định. Cùng một source, cùng phiên bản compiler và cùng cấu hình nên tạo ra output giống nhau về mặt nội dung hoặc ít nhất tương đương theo hợp đồng đã công bố.

Tính ổn định hữu ích cho:

- Git diff dễ đọc.
- Build cache.
- Reproducible build.
- Kiểm tra thay đổi generated code.
- Debug và hỗ trợ người dùng.

Một số nguyên tắc:

- Sắp xếp import và declaration theo quy tắc xác định.
- Dùng formatter thống nhất.
- Không đưa timestamp hoặc dữ liệu ngẫu nhiên vào output nếu không cần.
- Dùng tên sinh tự động ổn định.
- Chuẩn hóa newline và encoding.
- Ghi version compiler và target profile trong metadata khi cần.

Code generator cũng cần xử lý escaping literal đúng cách. Chuỗi DSL chứa dấu nháy, newline hoặc ký tự đặc biệt phải được encode theo cú pháp target, không được nối trực tiếp vào source code theo cách có thể làm thay đổi chương trình.

## 21. Kiểm thử transpiler

Kiểm thử cần xác nhận cả cấu trúc generated code và hành vi của chương trình sau khi dịch.

### 21.1. Golden tests

Mỗi source DSL mẫu có một file generated output mong đợi. Test chạy transpiler và so sánh output với golden file.

Ưu điểm là phát hiện thay đổi code generation. Tuy nhiên, golden test một mình không chứng minh semantics được bảo toàn; một output thay đổi về format có thể gây diff lớn dù hành vi không đổi.

### 21.2. Compile generated code

Sau khi sinh target source, chạy compiler của target để phát hiện lỗi cú pháp, kiểu hoặc import. Bước này kiểm tra target code có hợp lệ theo toolchain đích hay không.

### 21.3. Differential testing

Nếu có interpreter tham chiếu, chạy cùng input trên interpreter và chương trình đã transpile rồi so sánh kết quả:

~~~text
source = loadDsl("pricing.dsl")
input = sampleOrder()

expected = referenceInterpreter.execute(source, input)
actual = compiledTarget.execute(input)

assertEquivalent(expected, actual)
~~~

So sánh cần xét cả result, error và side effect được quan sát theo hợp đồng DSL.

### 21.4. Kiểm thử theo tính chất

Có thể sinh nhiều chương trình DSL hợp lệ, transpile và kiểm tra các tính chất chung. Ví dụ, phép chuyển đổi source sang target rồi chạy không được làm mất giá trị của một biểu thức thuần.

### 21.5. Kiểm thử source map

Tạo lỗi có chủ đích trong target, xác nhận vị trí được ánh xạ về đúng dòng và cột DSL. Kiểm thử cả trường hợp một source node sinh nhiều target node.

### 21.6. Kiểm thử đa backend

Chạy cùng bộ test ngữ nghĩa trên mọi backend được hỗ trợ. Nếu kết quả khác nhau, cần xác định đó là lỗi transpiler, giới hạn target được tài liệu hóa hay hành vi không xác định của DSL.

## 22. Hiệu năng và tối ưu hóa

Transpiler có thể thực hiện tối ưu ở IR hoặc dựa vào compiler target.

Các kỹ thuật phổ biến:

- Constant folding: tính trước biểu thức hằng.
- Dead code elimination: loại bỏ mã không thể ảnh hưởng kết quả.
- Common subexpression elimination: tái sử dụng biểu thức lặp nếu an toàn.
- Inlining: thay lời gọi bằng thân hàm trong điều kiện phù hợp.
- Simplification: rút gọn biểu thức và nhánh điều kiện.
- Lowering: chuyển cấu trúc cấp cao thành thao tác target.

Mọi tối ưu phải bảo toàn semantics. Ví dụ, không được loại bỏ một lời gọi hàm chỉ vì không dùng kết quả nếu hàm có side effect hoặc có thể ném exception.

### 22.1. Tối ưu trong transpiler hay target compiler?

Transpiler nên thực hiện những tối ưu dựa trên ngữ nghĩa riêng của DSL hoặc cần thiết để biểu diễn target. Compiler target nên được tận dụng cho các tối ưu phụ thuộc nền tảng.

Không nên tái triển khai mọi tối ưu mà target compiler đã làm tốt. Tuy nhiên, target compiler không biết các bất biến miền của DSL nếu transpiler không truyền chúng thành cấu trúc phù hợp.

## 23. Bảo mật khi sinh và chạy mã đích

Generated code thường được biên dịch hoặc thực thi như mã của ngôn ngữ đích. Vì vậy, dữ liệu từ DSL phải được xử lý như input không đáng tin cậy.

### 23.1. Không nối source trực tiếp

Không nên tạo code bằng cách nối chuỗi từ dữ liệu người dùng:

~~~text
generated = "query = '" + userInput + "'"
~~~

Nếu userInput chứa dấu nháy hoặc cú pháp target, nó có thể thay đổi cấu trúc code. Cần dùng AST builder, serializer hoặc escaping đúng theo grammar của target.

### 23.2. SQL injection

Nếu DSL sinh SQL, dữ liệu runtime cần được truyền bằng parameter binding. Không nên nối giá trị đầu vào trực tiếp vào SQL string.

### 23.3. Capability và quyền

Không nên sinh lời gọi cho phép DSL truy cập mọi API của host. Backend chỉ nên expose capability đã được cho phép và runtime phải enforce quyền tương ứng.

### 23.4. Kiểm tra target artifact

Nếu generated code được build hoặc chạy trong pipeline tự động, cần kiểm soát nguồn artifact, dependency, compiler flags và quyền của tiến trình build.

## 24. Quản lý phiên bản và tương thích

Transpiler có nhiều thành phần có thể thay đổi độc lập:

- Phiên bản ngôn ngữ DSL.
- Phiên bản compiler/transpiler.
- Phiên bản IR schema.
- Phiên bản target language.
- Phiên bản runtime helper.
- Phiên bản thư viện hoặc framework đích.
- Phiên bản source map/debug metadata.

Một thay đổi ở backend có thể làm generated code khác nhưng vẫn giữ semantics; một thay đổi ở frontend hoặc language specification có thể làm cùng source được hiểu khác.

### 24.1. Target profile

Backend nên xác định target profile, chẳng hạn:

~~~text
target:
    language: TypeScript
    languageVersion: 5.x
    moduleSystem: ESModules
    runtime: Node
    runtimeVersion: 22
~~~

Profile giúp code generator biết cú pháp, thư viện và khả năng nền tảng nào được phép dùng.

### 24.2. Breaking changes

Nếu thay đổi semantics của DSL, cần cân nhắc language version hoặc migration. Nếu chỉ thay đổi target formatting, có thể không cần thay language version nhưng vẫn nên ghi compiler version để build tái lập.

Nếu runtime helper đổi chữ ký, generated code cũ có thể không build. Cần giữ API tương thích trong khoảng hỗ trợ hoặc phát hành artifact kèm dependency version rõ ràng.

## 25. Ví dụ tổng hợp: transpile DSL rule sang TypeScript

Giả sử DSL:

~~~text
rule "free-shipping" {
    when order.total >= 500000 and order.isPaid
    then order.shippingFee = 0
}
~~~

### 25.1. AST khái niệm

~~~text
Rule
    name: "free-shipping"
    condition:
        And
            GreaterThanOrEqual(
                Member(Name(order), "total"),
                Number(500000)
            )
            Member(Name(order), "isPaid")
    action:
        Assign(
            Member(Name(order), "shippingFee"),
            Number(0)
        )
~~~

### 25.2. Semantic model

Frontend xác nhận:

- order là input có kiểu Order.
- total là Money hoặc kiểu số có quy tắc so sánh phù hợp.
- isPaid là Boolean.
- shippingFee có kiểu tương thích với giá trị 0.
- AND short-circuit theo semantics của DSL.

### 25.3. Generated TypeScript

~~~typescript
export function freeShipping(order: Order): void {
    const eligible =
        order.total >= Money.fromMinorUnits(500000) &&
        order.isPaid;

    if (eligible) {
        order.shippingFee = Money.zero(order.currency);
    }
}
~~~

Đoạn code minh họa cách backend có thể gọi helper Money để bảo toàn semantics tiền tệ. Cách biểu diễn thực tế phụ thuộc type system và target runtime.

### 25.4. Source mapping

Function freeShipping có thể được map về declaration rule free-shipping. Điều kiện được map về dòng when, còn assignment được map về dòng then. Nếu TypeScript compiler báo lỗi tại biểu thức Money, transpiler có thể hiển thị lỗi tại node DSL liên quan.

## 26. Chọn kiến trúc transpiler

| Kiến trúc | Ưu điểm | Hạn chế |
|---|---|---|
| AST trực tiếp sang target | Đơn giản, ít tầng | Backend phụ thuộc chặt frontend |
| Semantic model sang target | Dịch dựa trên thông tin đã resolve | Cần mô hình semantic rõ |
| AST qua IR chung | Dễ hỗ trợ nhiều backend và tối ưu | Thêm chi phí thiết kế IR |
| DSL sang DSL trung gian | Có thể tái sử dụng compiler khác | Phụ thuộc semantics và toolchain trung gian |
| Sinh code qua runtime helper | Tập trung logic đặc thù | Cần quản lý runtime API/version |

Với một DSL nhỏ và một target duy nhất, AST-to-target có thể phù hợp. Với DSL có nhiều target, nhiều phép tối ưu hoặc semantics phong phú, semantic model và IR thường tạo ranh giới dễ bảo trì hơn.

## 27. Những lỗi thiết kế thường gặp

| Lỗi | Hệ quả | Cách xử lý |
|---|---|---|
| Chỉ sinh code đúng cú pháp | Hành vi có thể khác DSL | Xác định và kiểm tra semantic preservation |
| Dịch trực tiếp bằng nối chuỗi | Dễ sai escaping và injection | Dùng AST/IR và emitter có cấu trúc |
| Bỏ qua khác biệt kiểu số | Sai precision, rounding hoặc overflow | Dùng mapping kiểu và runtime helper phù hợp |
| Bỏ ngoặc khi in biểu thức | Thay đổi precedence và kết quả | Emitter dựa trên AST và precedence target |
| Không xử lý evaluation order | Side effect xảy ra khác thứ tự | Mô phỏng thứ tự đánh giá của DSL |
| Sinh code phụ thuộc helper không version | Artifact cũ có thể không build | Ghi dependency và quản lý API runtime |
| Không có source map | Khó debug lỗi target từ DSL | Giữ mapping source span xuyên suốt pipeline |
| Giả định mọi target hỗ trợ mọi tính năng | Một số semantics bị bỏ qua | Khai báo capability và từ chối target không phù hợp |
| Dùng target compiler làm validator duy nhất | Lỗi hiển thị bằng khái niệm target | Chạy semantic analysis ở frontend DSL |
| Không kiểm thử hành vi sau dịch | Golden output có thể đúng hình thức nhưng sai semantics | Differential và integration testing |
| Thay đổi backend làm output không tái lập | Git diff và build cache thiếu ổn định | Chuẩn hóa emitter và version metadata |
| Sinh lời gọi host quá rộng | Tăng quyền và rủi ro bảo mật | Capability boundary và target policy |

## 28. Quy trình triển khai một transpiler

Một quy trình có thể thực hiện theo các bước:

1. **Đặc tả semantics DSL:** xác định kiểu, thứ tự đánh giá, lỗi, side effect và các cấu trúc miền.
2. **Chọn target:** xác định ngôn ngữ, phiên bản, runtime và nền tảng hỗ trợ.
3. **Xây frontend:** lexer, parser, AST, name resolution và type checking.
4. **Xây semantic model:** lưu binding, type, source span và thông tin miền.
5. **Thiết kế IR hoặc lowering:** quyết định cấu trúc nào cần hạ cấp trước code generation.
6. **Lập bảng ánh xạ:** ghi cách mỗi node DSL được biểu diễn trong target.
7. **Xây runtime support nếu cần:** định nghĩa helper, API và version.
8. **Viết backend và emitter:** sinh code hợp lệ, ổn định và có source mapping.
9. **Tích hợp target toolchain:** compile hoặc validate generated code.
10. **Kiểm thử semantics:** so sánh interpreter tham chiếu với output đã dịch.
11. **Kiểm thử diagnostics và source map:** bảo đảm lỗi quay về đúng source.
12. **Quản lý version và phân phối:** ghi compiler, target profile, runtime dependency và quy trình migration.

Mỗi cấu trúc DSL nên có ví dụ nguồn, semantic model mong đợi, target output và hành vi thực thi mong đợi. Điều này tạo cơ sở để triển khai backend và kiểm tra các thay đổi về sau.

## 29. Tiêu chí của một transpiler tốt

Một transpiler tốt tạo ra chương trình đích hợp lệ, bảo toàn ngữ nghĩa DSL, giải thích được lỗi bằng ngôn ngữ của người dùng và quản lý rõ phụ thuộc vào target runtime. Nó cũng cần output ổn định, có thể kiểm thử và có thể truy vết về source ban đầu.

Các câu hỏi quan trọng:

- Target có biểu diễn được mọi cấu trúc DSL cần hỗ trợ không?
- Khác biệt hệ kiểu và mô hình thực thi được xử lý thế nào?
- Cấu trúc cấp cao được lowering ra sao?
- Cần IR chung cho nhiều backend không?
- Runtime helper nào là bắt buộc và version được quản lý thế nào?
- Precedence, evaluation order và side effect có được bảo toàn không?
- Source map liên kết generated code về source DSL ra sao?
- Generated code được kiểm tra bằng toolchain nào?
- Có test so sánh semantics giữa interpreter và các backend không?
- Artifact có thể build lại và triển khai trên target profile đã công bố không?

Transpilation giúp DSL tận dụng ngôn ngữ và nền tảng đã có bằng cách chuyển source sang một dạng mã đích có thể tiếp tục biên dịch hoặc thực thi. Khi frontend hiểu đúng ngữ nghĩa, IR và lowering giữ được cấu trúc cần thiết, backend xử lý chính xác khác biệt của target, và source mapping cùng versioning được quản lý rõ, transpiler trở thành một phần đáng tin cậy trong hệ sinh thái DSL.
