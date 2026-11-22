# Kiểm thử ngữ nghĩa cho DSL

Một chương trình DSL có thể đúng cú pháp nhưng vẫn tạo ra kết quả sai. Parser chỉ xác nhận chuỗi đầu vào phù hợp grammar; nó không chứng minh biểu thức được hiểu đúng, biến được resolve đúng, phép tính có kết quả mong đợi hoặc hành động nghiệp vụ tuân theo policy.

**Kiểm thử ngữ nghĩa** (*semantic testing*) là quá trình kiểm tra ý nghĩa và hành vi của chương trình DSL khi được phân tích, biên dịch hoặc thực thi. Mục tiêu là xác nhận các quy tắc của ngôn ngữ được triển khai đúng: kiểu dữ liệu, phạm vi tên, thứ tự đánh giá, toán tử, luồng điều khiển, xử lý lỗi, giá trị thiếu và kết quả quan sát được.

Ví dụ, cả hai biểu thức sau đều có thể parse thành công:

```text
price + tax * quantity
(price + tax) * quantity
```

Nhưng chúng không nhất thiết có cùng ý nghĩa vì precedence và grouping khác nhau. Semantic tests cần xác nhận AST hoặc kết quả đánh giá phản ánh đúng quy tắc của DSL.

Kiểm thử ngữ nghĩa đặc biệt quan trọng với DSL vì ngôn ngữ thường mã hóa quy tắc nghiệp vụ. Một lỗi nhỏ trong type checker, evaluator hoặc compiler có thể làm nhiều chương trình hợp lệ đưa ra quyết định sai mà không gây crash.

## 1. Vì sao kiểm thử ngữ nghĩa khác kiểm thử cú pháp?

Kiểm thử cú pháp xác nhận parser chấp nhận hoặc từ chối cấu trúc văn bản. Kiểm thử ngữ nghĩa xác nhận cấu trúc đó được hiểu và thực hiện đúng.

| Loại kiểm thử | Câu hỏi chính | Ví dụ |
|---|---|---|
| Lexical test | Token được nhận diện đúng không? | 123 là integer literal |
| Parser test | Cấu trúc có đúng grammar không? | if có block hợp lệ |
| Semantic test | Cấu trúc có ý nghĩa hợp lệ không? | Biến được khai báo trước khi dùng |
| Type test | Kiểu có tương thích không? | Không cộng String với Duration |
| Evaluation test | Chương trình trả kết quả nào? | 2 + 3 * 4 cho kết quả 14 |
| Integration test | Các thành phần phối hợp đúng không? | Compiler và runtime cho cùng semantics |

Một chương trình có thể vượt parser tests nhưng thất bại semantic tests. Ví dụ, grammar cho phép gọi function với bất kỳ số argument nào, nhưng semantic analyzer phải kiểm tra arity và type của từng argument.

### Ví dụ

```text
let quantity: Integer = 5
let unitPrice: Decimal = 12.50
let total: Decimal = quantity * unitPrice
```

Đoạn code có thể parse thành công. Semantic tests cần xác nhận phép nhân Integer với Decimal có kết quả Decimal theo type rules, phép gán tương thích và biến total có giá trị 62.50.

## 2. Xác định semantics của ngôn ngữ trước khi viết test

Test chỉ có ý nghĩa khi có quy tắc kỳ vọng rõ ràng. DSL cần đặc tả semantics cho các cấu trúc mà nó hỗ trợ.

Các câu hỏi cần được trả lời:

- Biểu thức được đánh giá theo thứ tự nào?
- Toán tử nào có precedence cao hơn?
- Phép gán có trả về giá trị không?
- Biến có scope ở block, function hay module?
- Shadowing có được phép không?
- Null và missing value được xử lý thế nào?
- Điều kiện phải trả Boolean hay hỗ trợ truthiness?
- Khi có lỗi runtime, execution dừng hay tiếp tục?
- Function call có thể tạo side effect không?
- Integer overflow và decimal rounding được xử lý ra sao?
- Thứ tự duyệt collection có được bảo đảm không?
- Một chương trình chạy trong môi trường nào và có quyền gì?

Nếu semantics chưa được xác định, test dễ mã hóa giả định riêng của người viết test. Khi đó test có thể buộc implementation giữ một behavior chưa từng được thống nhất.

### Semantic contract

Có thể ghi mỗi quy tắc dưới dạng:

1. Cấu trúc DSL.
2. Điều kiện hợp lệ.
3. Kiểu đầu vào và đầu ra.
4. Hành vi khi dữ liệu biên hoặc thiếu.
5. Kết quả quan sát được.
6. Loại diagnostic nếu không hợp lệ.

Semantic contract là cơ sở để viết unit tests, conformance tests và tài liệu.

## 3. Các lớp kiểm thử ngữ nghĩa

Semantic testing không chỉ là chạy chương trình rồi so sánh một con số. Có nhiều lớp kiểm tra bổ sung cho nhau.

- **Static semantic tests:** kiểm tra name resolution, type checking, scope và constraint trước execution.
- **Evaluation tests:** kiểm tra giá trị của expression và statement.
- **Control-flow tests:** kiểm tra branch, loop, return, break và exception.
- **Runtime contract tests:** kiểm tra builtin functions, host functions và side effects.
- **Compiler conformance tests:** so sánh hành vi giữa interpreter và generated code.
- **Property-based tests:** kiểm tra các tính chất đúng với nhiều input.
- **Metamorphic tests:** biến đổi input hoặc chương trình theo quy tắc mà kết quả cần có quan hệ xác định.
- **Regression tests:** giữ lại các trường hợp từng gây lỗi.
- **Compatibility tests:** xác nhận semantics giữa các language/runtime versions.

Một test suite tốt kết hợp các loại test này theo rủi ro của ngôn ngữ và workload thực tế.

## 4. Kiểm thử name resolution và symbol scope

Name resolution xác định một identifier tham chiếu tới declaration nào.

Ví dụ:

```text
let price = 100

function quote() {
    let price = 80
    return price
}
```

Nếu DSL cho phép local variable che khuất biến bên ngoài, kết quả trong function là 80. Nếu shadowing bị cấm, semantic analyzer cần báo lỗi khi khai báo trùng trong scope lồng nhau.

Các test cần bao phủ:

- Biến được khai báo trước khi sử dụng.
- Biến không tồn tại.
- Khai báo trùng trong cùng scope.
- Shadowing giữa scope cha và con.
- Parameter và local variable cùng tên.
- Import và qualified name.
- Function overload.
- Module visibility và access modifiers.
- Symbol được resolve đúng khi có nhiều tên gần giống.

Không chỉ kiểm tra có diagnostic hay không. Test nên xác nhận symbol được resolve có đúng declaration ID hoặc source location mong đợi.

### Scope lồng nhau

```text
let status = "global"

function process() {
    let status = "local"
    if true {
        let status = "inner"
        print(status)
    }
    print(status)
}
```

Nếu DSL dùng lexical scope, hai lần print lần lượt tham chiếu inner và local. Test có thể kiểm tra symbol binding hoặc kết quả output để xác nhận.

## 5. Kiểm thử type checking

Type checker xác nhận các biểu thức và phép toán phù hợp với type system.

Các trường hợp quan trọng:

- Gán đúng kiểu.
- Gán sai kiểu.
- Implicit conversion được cho phép.
- Conversion bị cấm.
- Numeric promotion.
- Generic type inference.
- Function argument và return type.
- Nullable và optional values.
- Collection element type.
- Union hoặc sum types.
- Enum compatibility.
- Type narrowing sau điều kiện.
- Overload resolution.

Ví dụ:

```text
let count: Integer = 10
let label: String = "items"
let result = count + label
```

Nếu DSL không định nghĩa phép cộng giữa Integer và String, type checker cần từ chối biểu thức và chỉ ra vị trí liên quan. Không nên đợi tới runtime mới phát hiện lỗi có thể xác định tĩnh.

### Diagnostic ổn định

Test nên kiểm tra diagnostic code, severity, source range và type mong đợi. Không nên chỉ so sánh toàn bộ message nếu message có thể được dịch hoặc chỉnh sửa vì lý do UX.

## 6. Kiểm thử operator semantics

Mỗi toán tử cần có semantics xác định cho các kiểu được hỗ trợ.

Ví dụ với số:

```text
7 + 3
7 - 3
7 * 3
7 / 3
7 % 3
```

Cần xác định:

- Integer division trả Integer hay Decimal.
- Chia cho zero tạo exception hay diagnostic.
- Overflow wrap, trap hay dùng kiểu số lớn.
- Decimal có precision và rounding mode nào.
- So sánh NaN nếu hỗ trợ floating point.
- Equality của object so sánh identity hay value.
- String comparison có phân biệt hoa/thường không.
- Null equality có logic hai hay ba giá trị.

### Precedence và associativity

Ví dụ:

```text
2 + 3 * 4
20 - 5 - 2
2 ** 3 ** 2
```

Test cần xác nhận multiplication được thực hiện trước addition, subtraction kết hợp trái nếu đó là quy tắc, và exponentiation kết hợp theo semantics đã công bố.

Có thể kiểm tra AST shape và evaluation result. Kiểm tra cả hai giúp phát hiện parser tạo AST sai hoặc evaluator diễn giải AST sai.

## 7. Kiểm thử Boolean và short-circuit

Các toán tử logic thường có short-circuit semantics.

Ví dụ:

```text
false and expensiveCheck()
true or fallback()
```

Nếu and short-circuit, expensiveCheck không được gọi khi vế trái false. Nếu or short-circuit, fallback không được gọi khi vế trái true.

Test cần xác nhận cả giá trị cuối lẫn số lần gọi function. Điều này quan trọng khi function có chi phí hoặc side effect.

### Truth table

| A | B | A and B | A or B |
|---|---|---|---|
| true | true | true | true |
| true | false | false | true |
| false | true | false | true |
| false | false | false | false |

Nếu DSL hỗ trợ unknown hoặc null, cần bổ sung truth table theo logic ba giá trị. Không được tự suy ra unknown giống false nếu language contract không quy định.

## 8. Kiểm thử control flow

Control flow quyết định statement nào được thực hiện và thứ tự thực hiện.

Các cấu trúc cần test:

- if/else.
- switch hoặc match.
- while và for.
- break và continue.
- return.
- throw/catch nếu có.
- Defer hoặc finally nếu DSL hỗ trợ.
- Early exit.
- Nested control flow.

Ví dụ:

```text
let total = 0
for item in items {
    if item.disabled {
        continue
    }
    total = total + item.price
}
return total
```

Test cần xác nhận item disabled bị bỏ qua, các item khác được cộng đúng một lần và return kết thúc function.

### Unreachable code

Compiler có thể phát hiện statement sau return hoặc branch không thể xảy ra. Test nên xác nhận warning/error theo policy của DSL và source range chính xác.

## 9. Kiểm thử function call và argument binding

Function call có nhiều quy tắc:

- Số lượng argument.
- Thứ tự positional arguments.
- Named arguments.
- Default parameter values.
- Variadic parameters.
- Generic inference.
- Overload resolution.
- Return type.
- Evaluation order của argument.
- Exception propagation.

Ví dụ:

```text
function discount(price: Decimal, rate: Decimal = 0.1) {
    return price * rate
}

discount(100)
discount(price = 100, rate = 0.2)
```

Test cần xác nhận lời gọi đầu dùng default rate, lời gọi thứ hai dùng named argument và kết quả có type/precision đúng.

Nếu argument có side effect, evaluation order cần được đặc tả. Không nên để thứ tự phụ thuộc vào implementation detail của compiler.

## 10. Kiểm thử collection và iteration semantics

DSL có thể cung cấp list, set, map, tuple hoặc record. Cần kiểm tra:

- Thứ tự phần tử.
- Index bắt đầu từ 0 hay 1.
- Index ngoài phạm vi.
- Duplicate trong set.
- Map key equality.
- Iteration order.
- Mutation trong lúc duyệt.
- Empty collection.
- Nested collection.
- Generic element type.

Ví dụ:

```text
let values = [10, 20, 30]
values[0]
values.length
```

Nếu list dùng zero-based indexing, values[0] là 10. Nếu DSL dùng semantics khác, test phải phản ánh đặc tả.

### Deterministic iteration

Nếu map không bảo đảm thứ tự, test không nên phụ thuộc vào thứ tự duyệt. Nếu DSL cam kết insertion order hoặc sorted order, test cần xác nhận contract đó.

## 11. Kiểm thử null, missing và optional values

Dữ liệu thiếu có thể có nhiều trạng thái:

- Field không tồn tại.
- Field tồn tại nhưng null.
- Optional value không có.
- Collection rỗng.
- Giá trị mặc định được áp dụng.

Ví dụ:

```text
let a = record.optionalField
let b = record.nullableField
let c = record.missingField
```

DSL cần xác định mỗi trường hợp tạo giá trị nào hoặc diagnostic nào.

Các test nên kiểm tra:

- Dereference null.
- Optional unwrap.
- Null coalescing.
- Default operator.
- Equality với null.
- Serialization absent/null.
- Type narrowing sau kiểm tra null.
- Propagation qua function call.

Nếu null có thể lan truyền qua expression, test nên xác định chính xác nơi evaluation trả null và nơi phát sinh error.

## 12. Kiểm thử numeric precision và overflow

Các DSL xử lý giá, thuế, tỷ lệ hoặc tài chính cần đặc biệt chú ý số học.

Ví dụ:

```text
0.1 + 0.2
999999999999999999 + 1
10 / 3
```

Binary floating point có thể không biểu diễn chính xác một số thập phân. Nếu DSL dùng Decimal, cần test precision, scale và rounding mode.

Các trường hợp cần có:

- Giá trị biên min/max.
- Overflow và underflow.
- Chia hết và chia dư.
- Negative zero nếu kiểu hỗ trợ.
- NaN và infinity nếu hỗ trợ floating point.
- Rounding half-up, half-even hoặc policy khác.
- Chuyển đổi giữa Integer và Decimal.
- Serialization round-trip.

Không nên so sánh số thực bằng equality chính xác nếu contract quy định sai số tolerance. Với Decimal chính xác, test có thể so sánh scale và giá trị theo semantics đã định.

## 13. Kiểm thử string, Unicode và locale

String semantics bao gồm indexing, length, normalization, comparison, substring và formatting.

Với Unicode, cần phân biệt byte, code point, UTF-16 code unit và grapheme cluster. Một ký tự hiển thị có thể được biểu diễn bởi nhiều code point hoặc code unit.

Ví dụ test có thể dùng:

```text
"café"
"e\u0301"
"😀"
"ภาษาไทย"
"Tiếng Việt"
```

Các câu hỏi cần đặc tả:

- Hai chuỗi Unicode tương đương về hình thức có được normalize không?
- length trả số code point hay UTF-16 units?
- Indexing có thể cắt giữa surrogate pair không?
- Case conversion phụ thuộc locale hay dùng Unicode default?
- Sorting có locale-aware không?
- Regex engine hỗ trợ Unicode class nào?

Không nên để semantics thay đổi tùy locale của máy chạy nếu DSL cần kết quả tái lập.

## 14. Kiểm thử date, time và timezone

Date/time thường gây lỗi khi chuyển đổi timezone, daylight saving time hoặc định dạng.

Các test cần xác nhận:

- Date không có time.
- LocalDateTime không có timezone.
- Instant hoặc UTC timestamp.
- Offset và timezone identifier.
- Daylight saving gap/overlap.
- Leap day.
- Parsing/formatting.
- So sánh và arithmetic.
- Clock injection.
- Boundary của calendar.

Ví dụ:

```text
date("2024-02-29") + 1 day
instant("2026-11-15T00:00:00Z")
```

Nên dùng fixed clock trong test thay vì đồng hồ hệ thống. Nếu một function trả current time, test cần inject clock để kết quả xác định.

## 15. Kiểm thử side effects và host functions

Nếu DSL gọi host function, test cần kiểm tra contract giữa runtime và ứng dụng.

Một function có thể:

- Đọc dữ liệu.
- Ghi dữ liệu.
- Gửi message.
- Gọi API.
- Tạo resource.
- Trả lỗi domain.

Test nên xác nhận argument binding, quyền, số lần gọi, thứ tự, timeout và cách xử lý exception.

### Mock và fake

Unit tests có thể dùng fake host functions để kiểm tra evaluator mà không gọi hệ thống bên ngoài.

Integration tests cần xác nhận adapter thật chuyển dữ liệu và lỗi đúng contract.

Không nên dùng mock để thay thế toàn bộ test integration, vì mock có thể phản ánh giả định của test chứ không phải behavior của service thật.

### Idempotency

Nếu một function tạo side effect, retry hoặc replay không được tạo hành động trùng ngoài ý muốn. Test cần kiểm tra idempotency key và behavior khi response bị mất sau khi side effect đã hoàn thành.

## 16. Kiểm thử error semantics

DSL cần xác định lỗi nào là compile-time error, runtime exception, recoverable error hoặc domain result.

Ví dụ:

```text
let result = 10 / 0
```

Các câu hỏi:

- Chia cho zero được phát hiện tĩnh hay runtime?
- Exception có thể được catch không?
- Stack trace có DSL source location không?
- Error có được chuyển thành Result type không?
- Khi một expression lỗi, side effect trước đó có được rollback không?
- Một lỗi trong một phần tử collection có làm dừng toàn bộ evaluation không?

Test nên kiểm tra error code, source range, category và trạng thái execution. Message text có thể được kiểm tra ở mức phù hợp với localization policy.

## 17. Kiểm thử module, import và visibility

Module system có thể có import, export, package namespace và visibility rules.

Các trường hợp:

- Import module hợp lệ.
- Module không tồn tại.
- Import cycle.
- Symbol không được export.
- Alias import.
- Hai module có tên symbol trùng.
- Version dependency không tương thích.
- Private/public visibility.
- Re-export nếu hỗ trợ.

Test nên xác nhận resolution ổn định và diagnostic chỉ ra nguồn import hoặc declaration liên quan.

## 18. Kiểm thử macro, template và code expansion

Nếu DSL hỗ trợ macro hoặc template, quá trình expansion có thể thay đổi cấu trúc chương trình trước semantic analysis.

Cần kiểm tra:

- Argument substitution.
- Hygiene và variable capture.
- Expansion order.
- Recursive macro limit.
- Source mapping từ expanded node về source gốc.
- Error trong macro body.
- Deterministic expansion.
- Không cho expansion tạo construct ngoài policy.

Macro hygiene đặc biệt quan trọng. Một macro không nên vô tình bắt hoặc làm thay đổi tên biến của caller nếu semantics yêu cầu hygiene.

Golden tests có thể lưu expanded AST hoặc normalized output để phát hiện thay đổi ngoài ý muốn.

## 19. Kiểm thử interpreter và compiler parity

Một DSL có thể có interpreter để chạy trực tiếp và compiler để sinh bytecode hoặc mã đích. Hai cách thực thi phải tuân theo cùng semantics.

Một chiến lược là chạy cùng input qua cả hai:

```text
source = load("pricing.dsl")
input = fixture("order-100")

interpreted = interpreter.execute(source, input)
compiled = compiler.compile(source).execute(input)

assert interpreted == compiled
```

Đây là differential test. Nếu kết quả khác nhau, có thể lỗi nằm ở evaluator, code generator, runtime library hoặc target-language mapping.

Cần so sánh cả:

- Return value.
- Error category.
- Side effect trace.
- Ordering.
- Nullability.
- Numeric precision.
- Source mapping nếu là một phần contract.

## 20. Golden tests và snapshot tests

Golden test lưu output mong đợi cho một input cụ thể. Với DSL, output có thể là:

- AST hoặc normalized AST.
- Type inference result.
- Diagnostics.
- Evaluation result.
- Generated bytecode.
- Generated source.
- Execution trace.

Ví dụ, một test fixture có source và expected diagnostic:

```text
source:
    let total: Integer = "100"

expected:
    code: DSL-TYPE-001
    severity: error
    range: line 1, columns 24-29
```

Golden tests dễ review vì thay đổi output tạo diff. Tuy nhiên, không nên tự động cập nhật golden files mà không xem xét nguyên nhân. Một output sai có thể bị chấp nhận nếu cập nhật golden không được review.

Snapshot nên được chuẩn hóa để tránh thay đổi không liên quan như absolute path, timestamp hoặc thứ tự map.

## 21. Property-based testing

Property-based testing kiểm tra một tính chất đúng với nhiều input được sinh tự động thay vì chỉ một vài ví dụ cố định.

Ví dụ property cho phép cộng số nguyên:

- Với các giá trị không overflow, a + b phải bằng b + a nếu operator được định nghĩa giao hoán.
- a + 0 phải bằng a.
- Parse/format round-trip giữ nguyên giá trị theo contract.

Property cho collection:

- length của list sau append tăng đúng một.
- map lookup theo key vừa insert trả value đã insert.
- filter không tạo phần tử không thỏa predicate.

### Generator input

Cần xây dựng input generator theo type system của DSL:

- Integer trong khoảng hợp lệ và gần boundary.
- Decimal với scale khác nhau.
- String chứa Unicode và escape.
- List rỗng, một phần tử và nhiều phần tử.
- Object có field optional/null.
- AST có độ sâu giới hạn.
- Module graph có và không có cycle.

### Shrinking

Khi property thất bại, framework có thể thu nhỏ input để tạo counterexample đơn giản hơn. Điều này giúp tìm nguyên nhân và biến lỗi thành regression test.

## 22. Metamorphic testing

Trong một số trường hợp không dễ biết output chính xác cho mọi input. Metamorphic testing kiểm tra quan hệ giữa nhiều lần chạy.

Ví dụ, nếu filter được áp dụng thêm điều kiện AND hẹp hơn, tập kết quả không được lớn hơn tập ban đầu.

Các quan hệ có thể kiểm tra:

- Thêm điều kiện filter không làm tăng kết quả.
- Sắp xếp hai lần theo cùng key cho cùng thứ tự.
- Biểu thức cộng với zero giữ nguyên giá trị.
- Parentheses không làm đổi kết quả nếu grouping không đổi.
- Alpha-renaming biến local không làm đổi semantics.
- Inlining một pure function tương đương với gọi function.
- Interpreter và compiler trả kết quả tương đương.

Metamorphic relation phải dựa trên semantics thực sự. Ví dụ, đổi thứ tự hai phép tính có side effect không nhất thiết giữ nguyên kết quả.

## 23. Fuzz testing và kiểm thử robustness

Fuzz testing tạo nhiều input ngẫu nhiên hoặc được biến đổi để tìm crash, hang, memory exhaustion và behavior không xác định.

Với DSL, có thể fuzz:

- Lexer input.
- Parser grammar.
- AST generator.
- Type checker.
- Macro expansion.
- Evaluator.
- Serializer/deserializer.
- Compiler output.

Fuzzing cần giới hạn thời gian, memory và độ sâu để tránh chính test harness bị quá tải.

### Grammar-based fuzzing

Grammar-based fuzzer sinh chương trình theo grammar nên tạo được nhiều input có cấu trúc hợp lệ. Có thể thêm mutation để tạo chương trình gần hợp lệ, giúp kiểm tra parser và diagnostic.

### Semantic fuzzing

Semantic-aware generator có thể tạo AST hợp lệ theo type system, sau đó biến đổi một phần để kiểm tra type errors hoặc runtime behavior. Cách này đi sâu hơn parser fuzzing.

## 24. Kiểm thử regression

Khi phát hiện lỗi semantics, cần tạo một test tái hiện nhỏ và giữ lại lâu dài.

Regression fixture nên chứa:

- DSL source tối thiểu.
- Input context.
- Kết quả hoặc diagnostic mong đợi.
- Language version.
- Runtime/compiler version nếu cần.
- Lý do test tồn tại hoặc bug reference.

Ví dụ, nếu precedence của toán tử bị sai, hãy giữ một fixture kiểm tra cả AST và result. Nếu bug do Unicode offset, fixture cần giữ đúng ký tự và vị trí gây lỗi.

Regression tests giúp ngăn lỗi cũ quay lại khi parser, optimizer hoặc runtime được thay đổi.

## 25. Kiểm thử optimization semantics

Compiler có thể tối ưu constant folding, dead code elimination, inlining, common subexpression elimination hoặc loop transformation.

Mỗi optimization phải giữ nguyên semantics trong phạm vi được phép.

Ví dụ:

```text
let x = 2 * 3 + 4
```

Compiler có thể thay expression bằng constant 10. Nhưng nếu expression gọi function có side effect hoặc có thể ném exception, optimizer không được loại bỏ hoặc sắp xếp lại một cách tùy tiện.

Test cần so sánh:

- Optimization bật và tắt.
- Output interpreter và compiled output.
- Side effect order.
- Exception behavior.
- Floating point precision.
- Source mapping.
- Performance không làm thay đổi kết quả.

### Optimization guards

Một số phép biến đổi chỉ hợp lệ với pure expression hoặc type nhất định. Compiler cần kiểm tra điều kiện trước khi áp dụng optimization.

## 26. Kiểm thử concurrency và state isolation

Nếu runtime hỗ trợ nhiều execution đồng thời, semantic tests cần xác nhận state của một execution không rò sang execution khác.

Các trường hợp:

- Hai execution dùng cùng compiled program nhưng input khác.
- Mutable variable không được chia sẻ.
- Host function context gắn đúng principal.
- Cache không trả kết quả của tenant khác.
- Cancellation một execution không hủy execution khác.
- Parallel evaluation giữ đúng ordering contract nếu có.
- Shared builtin registry không bị mutation.

Test nên chạy nhiều request đồng thời với dữ liệu và danh tính khác nhau. Kết quả cần được so sánh theo từng execution ID để phát hiện cross-talk.

## 27. Kiểm thử version compatibility

Khi language version thay đổi, semantics có thể được sửa hoặc mở rộng.

Một compatibility suite có thể chạy chương trình đại diện qua nhiều runtime version và so sánh:

- Parse acceptance.
- Type checking.
- Evaluation result.
- Diagnostics.
- Serialization.
- Builtin behavior.
- Compiler/interpreter parity.

Nếu thay đổi là chủ đích, cần đánh dấu expected behavior theo language version và có migration note.

Không nên ép mọi version phải trả cùng kết quả nếu language specification đã thay đổi semantics một cách có version.

## 28. Test oracle và expected result

Một khó khăn của semantic testing là xác định kết quả đúng (*test oracle*).

Các nguồn oracle có thể gồm:

- Language specification.
- Formal semantics hoặc reference interpreter.
- Kết quả được tính thủ công cho fixture nhỏ.
- Một implementation độc lập.
- Algebraic properties.
- Golden output đã được review.
- Kết quả từ version đã được xác nhận.

Nếu dùng cùng một implementation để vừa tạo expected output vừa kiểm tra nó, test có thể lặp lại cùng bug. Với semantics quan trọng, nên có oracle độc lập hoặc tính toán thủ công cho các trường hợp nhỏ.

## 29. Thiết kế test fixtures và tổ chức test suite

Fixture nên được tổ chức theo feature hoặc semantic rule để dễ tìm và mở rộng.

Ví dụ cấu trúc:

```text
tests/
  semantics/
    expressions/
      precedence.dsl
      precedence.expected
    types/
      assignment-mismatch.dsl
      assignment-mismatch.expected
    scope/
      nested-shadowing.dsl
      nested-shadowing.expected
    control-flow/
      loop-continue.dsl
      loop-continue.expected
    runtime/
      null-propagation.dsl
      null-propagation.expected
  regression/
    issue-001.dsl
    issue-001.expected
```

Mỗi fixture nên nhỏ và tập trung vào một quy tắc chính. Test end-to-end vẫn cần thiết nhưng không nên là cách duy nhất để kiểm tra mọi semantics vì khi thất bại sẽ khó xác định thành phần gây lỗi.

### Test naming

Tên test nên thể hiện quy tắc và điều kiện, ví dụ typecheck_rejects_string_for_decimal hoặc evaluator_short_circuits_false_and. Tên rõ giúp log CI dễ hiểu.

## 30. Tích hợp semantic tests vào CI

Một pipeline có thể chia test theo thời gian và phạm vi:

1. Parser và static semantic tests chạy sớm.
2. Unit evaluation tests chạy sau build compiler.
3. Golden và regression tests chạy cho mọi pull request.
4. Property-based tests chạy với seed cố định trong CI và seed đa dạng theo lịch.
5. Fuzzing dài chạy trong job định kỳ.
6. Interpreter/compiler differential tests chạy trước release.
7. Compatibility suite chạy khi thay language/runtime version.

Test failure nên cung cấp source fixture, input, expected result, actual result và runtime version. Nếu property-based test thất bại, cần lưu seed để tái hiện.

Không nên để test ngẫu nhiên thất bại mà không ghi lại seed hoặc counterexample.

## 31. Ví dụ end-to-end: kiểm thử semantics của biểu thức giá

Giả sử DSL hỗ trợ tính giá sau thuế:

```text
function finalPrice(
    base: Decimal,
    taxRate: Decimal,
    discount: Decimal
): Decimal {
    return base * (1 + taxRate) - discount
}
```

Test fixture:

```text
input:
    base = 100.00
    taxRate = 0.10
    discount = 5.00

expected:
    result = 105.00
    type = Decimal
```

Ngoài trường hợp cơ bản, cần test:

- taxRate bằng 0.
- discount bằng 0.
- discount lớn hơn tổng trước giảm.
- base bằng 0.
- Decimal có scale khác nhau.
- Giá trị biên.
- Input null nếu schema cho phép.
- Rounding theo currency policy.
- Compiler và interpreter cho cùng kết quả.

Một property có thể xác nhận khi taxRate = 0 và discount = 0, kết quả bằng base. Một property khác có thể xác nhận tăng discount không làm finalPrice tăng nếu các điều kiện còn lại giữ nguyên.

## 32. Những lỗi thường gặp trong semantic testing

**Chỉ kiểm tra parser acceptance.** Chương trình parse được nhưng có thể resolve hoặc evaluate sai. Bổ sung static semantic và runtime tests.

**Chỉ kiểm tra một kết quả cuối.** Lỗi có thể nằm ở symbol binding, type inference hoặc execution trace. Kiểm tra các intermediate representation khi phù hợp.

**Expected output được tạo từ cùng implementation.** Test có thể lặp lại bug. Dùng specification, oracle độc lập hoặc fixture tính tay.

**Không kiểm tra boundary values.** Lỗi thường xuất hiện tại min/max, zero, empty và null. Thêm test sát biên.

**So sánh diagnostic message nguyên văn.** Thay đổi wording làm test nhiễu. Ưu tiên code, severity, range và structured details.

**Bỏ qua evaluation order.** Short-circuit hoặc side effect có thể bị thực hiện sai thứ tự. Dùng spy function và trace để xác nhận.

**Không kiểm tra Unicode.** Offset và indexing có thể sai khi có surrogate pair hoặc combining mark. Dùng fixture đa ngôn ngữ.

**Không kiểm tra compiler/interpreter parity.** Hai execution backend có thể hiểu khác nhau. Dùng differential tests.

**Golden files tự động cập nhật không review.** Hành vi sai có thể được chấp nhận. Review diff và lý do thay đổi.

**Property tests không lưu seed.** Lỗi khó tái hiện. Lưu seed và minimized counterexample.

**Fuzz tests không giới hạn tài nguyên.** Test có thể treo hoặc làm cạn CI. Đặt timeout, memory và input limits.

**Test side effect trên hệ thống thật.** Có thể gửi message hoặc ghi dữ liệu ngoài ý muốn. Dùng fake service hoặc môi trường test cô lập.

## 33. Quy trình xây dựng semantic test suite

Có thể triển khai theo trình tự:

1. Viết hoặc xác nhận language semantics cho từng feature.
2. Chia semantics thành name resolution, type rules, operators, control flow, runtime và host integration.
3. Tạo fixture nhỏ cho hành vi hợp lệ và không hợp lệ.
4. Kiểm tra AST, symbol binding và type result khi cần.
5. Kiểm tra evaluation result, error category và side effect trace.
6. Bổ sung boundary cases, null, missing, Unicode và numeric precision.
7. Viết golden tests cho diagnostics, normalized AST và generated output.
8. Dùng property-based testing cho invariant tổng quát.
9. Dùng metamorphic testing khi khó có expected output trực tiếp.
10. Dùng differential tests giữa interpreter, compiler và reference implementation.
11. Fuzz lexer, parser, semantic analyzer và runtime với resource limits.
12. Biến mọi bug đã sửa thành regression fixture.
13. Kiểm tra concurrency, version compatibility và optimization parity.
14. Tích hợp các nhóm test vào CI theo thời gian phù hợp.
15. Lưu seed, counterexample và version metadata để tái hiện failure.

## 34. Câu hỏi tự kiểm tra

1. Kiểm thử ngữ nghĩa khác kiểm thử cú pháp như thế nào?
2. Vì sao cần đặc tả semantics trước khi viết expected results?
3. Static semantic tests kiểm tra những thành phần nào?
4. Name resolution và scope tests nên bao phủ trường hợp nào?
5. Type checker cần kiểm tra implicit conversion và overload ra sao?
6. Precedence và associativity có thể được kiểm tra bằng AST và evaluation như thế nào?
7. Short-circuit tests cần xác nhận điều gì ngoài giá trị Boolean?
8. Null, missing và optional values cần các fixture nào?
9. Vì sao numeric precision và overflow cần test riêng?
10. Unicode có thể làm sai indexing hoặc source range theo cách nào?
11. Host function tests cần kiểm tra quyền, retry và side effects ra sao?
12. Interpreter/compiler parity được xác nhận bằng differential testing như thế nào?
13. Golden tests có lợi ích và rủi ro gì?
14. Property-based testing và metamorphic testing khác nhau ra sao?
15. Fuzzing lexer/parser khác semantic-aware fuzzing ở điểm nào?
16. Regression fixtures cần lưu những metadata gì?
17. Optimization có thể làm thay đổi semantics trong trường hợp nào?
18. Test oracle độc lập giúp tránh lỗi gì?
19. Vì sao CI cần lưu seed và counterexample của property-based tests?
20. Hãy thiết kế semantic test suite cho DSL tính giá, bao gồm type rules, rounding, null handling, host functions và compiler parity.

Kiểm thử ngữ nghĩa xác nhận DSL hiểu và thực thi chương trình theo đúng hợp đồng ngôn ngữ. Khi test bao phủ name resolution, type system, operators, control flow, runtime behavior, dữ liệu biên và các backend thực thi, nhóm có thể phát hiện lỗi làm sai kết quả nghiệp vụ trước khi chúng đi vào ứng dụng.

