# Chuẩn hóa cây

Khi parser chuyển mã nguồn DSL thành Abstract Syntax Tree (AST), cây thu được thường phản ánh cấu trúc mà người dùng đã viết. Cùng một ý định có thể được biểu diễn bằng nhiều cách cú pháp khác nhau: có cú pháp rút gọn và cú pháp đầy đủ, có biểu thức lồng nhau và biểu thức phẳng, hoặc có những node trung gian chỉ phục vụ việc phân tích cú pháp. Để các bước xử lý tiếp theo làm việc trên cấu trúc thống nhất, hệ thống có thể thực hiện **chuẩn hóa cây (AST normalization)**.

Chuẩn hóa cây là quá trình biến đổi AST về một dạng biểu diễn quy ước theo các quy tắc đã định nghĩa. Mục tiêu thường là giảm khác biệt cú pháp không cần thiết, làm cấu trúc dễ phân tích, đơn giản hóa các node hoặc đưa những cách viết tương đương về cùng một dạng. Với một DSL, cây sau chuẩn hóa có thể thuận tiện hơn cho kiểm tra ngữ nghĩa, tối ưu hóa, thực thi, sinh mã, so sánh và lưu cache.

Chuẩn hóa không phải là thay đổi tùy ý để cây trông gọn hơn. Mỗi phép biến đổi phải bảo toàn ý nghĩa của chương trình trong phạm vi các giả định và quy tắc ngữ nghĩa của DSL. Một dạng chuẩn cũng chỉ có ý nghĩa khi ngôn ngữ định nghĩa rõ quy tắc nào được áp dụng và thứ tự thực hiện chúng.

## 1. Chuẩn hóa AST là gì?

**Chuẩn hóa AST** là việc áp dụng một tập phép biến đổi có quy tắc lên cây cú pháp để tạo ra biểu diễn thống nhất hơn. Đầu vào và đầu ra thường là AST, dù một số hệ thống chuyển AST sang một dạng biểu diễn trung gian (IR) đã chuẩn hóa.

Ví dụ, giả sử DSL cho phép hai cách viết điều kiện:

```text
order.total >= 1_000_000

order.total >= (1_000_000)
```

Nếu dấu ngoặc chỉ dùng để nhóm biểu thức và không tạo ra cấu trúc có ý nghĩa riêng, cả hai cách viết có thể tạo ra cùng một AST:

```text
GreaterEqual
├── MemberAccess(order, total)
└── NumberLiteral(1000000)
```

Trong trường hợp này, parser đã loại bỏ khác biệt cú pháp khi tạo AST. Các phép chuẩn hóa khác có thể được thực hiện ở những bước sau, chẳng hạn chuyển cú pháp rút gọn thành cấu trúc đầy đủ hoặc chuẩn hóa chuỗi biểu thức logic.

### 1.1. Dạng chuẩn (normal form)

Dạng chuẩn là một hình thức biểu diễn được xác định bởi quy tắc của hệ thống. Nếu hai cây có cùng ý nghĩa theo một phạm vi xác định, mục tiêu của chuẩn hóa có thể là đưa chúng về cùng dạng cấu trúc.

Tuy nhiên, không có một dạng chuẩn duy nhất phù hợp cho mọi DSL. Một ngôn ngữ quy tắc, một DSL truy vấn và một DSL mô tả workflow có những cấu trúc và phép biến đổi khác nhau. Dạng chuẩn phải phục vụ các bước xử lý cụ thể.

### 1.2. Chuẩn hóa có thể diễn ra ở nhiều cấp

Có thể chuẩn hóa:

- **Cấp cú pháp:** bỏ node trung gian, loại bỏ nhóm ngoặc không cần thiết, chuyển cú pháp viết tắt thành node đầy đủ.
- **Cấp cấu trúc:** làm phẳng node lồng nhau, thống nhất cách biểu diễn danh sách hoặc chuỗi phép toán.
- **Cấp tên và literal:** chuẩn hóa cách lưu tên đã phân giải, số, chuỗi hoặc giá trị enum theo quy tắc DSL.
- **Cấp ngữ nghĩa:** thay biểu thức bằng biểu diễn tương đương khi đã biết kiểu và các thuộc tính cần thiết.
- **Cấp IR:** đưa chương trình về các thao tác cơ bản mà backend dễ xử lý.

Không phải mọi dự án đều cần tất cả các cấp này. Chỉ nên đưa vào những phép biến đổi giúp ích cho nhu cầu thật của compiler hoặc công cụ DSL.

## 2. Vì sao cần chuẩn hóa cây?

### 2.1. Giảm số trường hợp mà các bước sau phải xử lý

Nếu một ý niệm có nhiều cách biểu diễn trong AST, semantic analyzer, interpreter hoặc code generator có thể phải xử lý mọi biến thể. Chuẩn hóa giúp đưa chúng về một cấu trúc chung để các bước sau đơn giản hơn.

Ví dụ, DSL có thể cho phép viết `unless condition { action }` như cú pháp rút gọn. Nếu hệ thống chuyển nó thành node `If` với điều kiện phủ định, interpreter chỉ cần xử lý một cấu trúc điều kiện.

### 2.2. Tạo cơ sở cho phân tích và tối ưu hóa

Các phép tối ưu hóa thường dễ viết hơn trên cây có cấu trúc thống nhất. Khi biểu thức `A and (B and C)` và `(A and B) and C` được đưa về một node `And` có danh sách toán hạng, các phép phân tích điều kiện có thể làm việc trên cùng một dạng.

### 2.3. So sánh và phát hiện thay đổi

Hai AST có thể khác nhau vì cách viết, dù ý nghĩa giống nhau. Nếu hệ thống chuẩn hóa trước khi so sánh, nó có thể phát hiện thay đổi thực sự của quy tắc dễ hơn. Điều này hữu ích cho review cấu hình, kiểm tra trùng lặp, tính hash hoặc quyết định có cần biên dịch lại hay không.

### 2.4. Sinh mã nhất quán

Code generator có thể dựa vào một tập node chuẩn thay vì xử lý nhiều cú pháp bề mặt. Điều đó giảm logic đặc biệt trong backend và giúp nhiều backend sinh kết quả nhất quán từ cùng một mô hình.

### 2.5. Hỗ trợ công cụ và chẩn đoán

AST chuẩn hóa có thể giúp công cụ hiển thị cấu trúc quy tắc, tạo tài liệu, phân tích phụ thuộc hoặc tìm những biểu thức tương đương. Tuy nhiên, nếu cần giữ nguyên cách người dùng viết để formatter hoặc IDE hiển thị lại văn bản, hệ thống cần bảo toàn token, CST hoặc thông tin nguồn song song.

## 3. Chuẩn hóa khác gì tối ưu hóa?

Chuẩn hóa và tối ưu hóa thường được thực hiện gần nhau nhưng có mục đích khác nhau.

| Khía cạnh | Chuẩn hóa | Tối ưu hóa |
|---|---|---|
| Mục tiêu chính | Đưa cây về dạng thống nhất, dễ xử lý | Cải thiện hiệu năng hoặc giảm công việc thực thi |
| Động cơ | Giảm khác biệt biểu diễn và cú pháp | Giảm thời gian, bộ nhớ hoặc số thao tác |
| Kết quả | Cấu trúc quy ước, ổn định hơn | Cấu trúc hoặc kế hoạch thực thi hiệu quả hơn |
| Ví dụ | Desugar `unless` thành `if not` | Loại bỏ phép tính lặp hoặc chọn thứ tự lọc hiệu quả |
| Bảo toàn ngữ nghĩa | Bắt buộc trong phạm vi ngôn ngữ | Bắt buộc trong phạm vi ngôn ngữ |

Có những phép biến đổi vừa chuẩn hóa vừa tối ưu, chẳng hạn constant folding. Việc phân loại phụ thuộc mục tiêu của pass. Điều quan trọng là không coi mọi phép biến đổi làm cây ngắn hơn đều là tối ưu an toàn.

Ví dụ, biến đổi `x * 1` thành `x` có thể là một quy tắc đơn giản hóa đại số. Nhưng nếu toán tử `*` được overload hoặc có tác dụng phụ, hoặc kiểu số có quy tắc đặc biệt, phép biến đổi cần được kiểm tra ngữ nghĩa trước khi áp dụng.

## 4. Các phép chuẩn hóa AST phổ biến

### 4.1. Desugaring: chuyển cú pháp rút gọn thành cú pháp cơ bản

**Desugaring** là chuyển cú pháp tiện dụng (syntactic sugar) thành một cấu trúc cốt lõi mà hệ thống xử lý thống nhất.

Giả sử DSL hỗ trợ:

```text
unless order.isCancelled {
    notifyWarehouse(order)
}
```

Ngôn ngữ có thể định nghĩa `unless C { A }` tương đương với `if not C { A }`. AST sau desugaring:

```text
IfStatement
├── condition: Not
│   └── MemberAccess(order, isCancelled)
└── thenBranch
    └── Call(notifyWarehouse, order)
```

Nhờ vậy, interpreter chỉ cần hiểu `IfStatement` và `Not`; không cần triển khai riêng `UnlessStatement` ở mọi backend.

Desugaring cần giữ đúng phạm vi biến, thứ tự đánh giá và hành vi của nhánh. Nếu cú pháp rút gọn có semantics khác với cú pháp cơ bản, không thể chỉ thay node dựa trên hình thức.

### 4.2. Làm phẳng biểu thức kết hợp (flattening)

Một biểu thức logic có thể tạo ra cây nhị phân lồng nhau:

```text
A and (B and C)
```

AST nhị phân:

```text
And
├── A
└── And
    ├── B
    └── C
```

Nếu DSL định nghĩa phép `and` có tính kết hợp và thứ tự đánh giá được bảo toàn, có thể chuẩn hóa thành node danh sách:

```text
And
├── A
├── B
└── C
```

Biểu diễn phẳng giúp duyệt điều kiện, tạo mã hoặc áp dụng các phép phân tích trên nhiều toán hạng dễ hơn. Cần giữ nguyên thứ tự nếu phép đánh giá có short-circuit hoặc các biểu thức con có tác dụng phụ. Không được tự ý sắp xếp các toán hạng chỉ vì AND được xem là giao hoán trong logic Boolean thuần túy.

### 4.3. Chuẩn hóa chuỗi phép truy cập

Một DSL có thể cho phép nhiều hình thức tham chiếu thuộc tính. Chẳng hạn, cú pháp rút gọn `customerName` có thể được chuyển thành `customer.name` nếu ngữ nghĩa và phạm vi của DSL xác định rõ alias đó.

```text
// Cú pháp bề mặt
customerName == "Lan"

// AST chuẩn hóa
Equal(
    MemberAccess(Identifier("customer"), "name"),
    StringLiteral("Lan")
)
```

Không nên suy diễn alias chỉ từ tên gần giống. Việc chuyển đổi phải dựa trên khai báo hoặc quy tắc ngôn ngữ rõ ràng, nếu không có thể trỏ nhầm thuộc tính.

### 4.4. Chuẩn hóa literal

Literal có thể được viết theo nhiều dạng tương đương. Ví dụ, DSL có thể chấp nhận dấu phân cách chữ số `1_000_000` và `1000000`. AST có thể lưu giá trị số đã phân tích thành cùng một kiểu số, thay vì giữ nguyên hai chuỗi khác nhau.

Với chuỗi, cần thận trọng hơn. Các escape khác nhau có thể tạo cùng giá trị chuỗi, nhưng không phải mọi chuỗi nhìn giống nhau đều tương đương Unicode. Nếu AST dùng giá trị chuỗi đã giải mã, cần giữ raw text hoặc source span nếu formatter và diagnostics cần cách viết gốc.

### 4.5. Chuẩn hóa toán tử và biểu thức

Parser có thể chuyển cú pháp nhiều cách viết thành một tập node chuẩn. Ví dụ, nếu DSL hỗ trợ cả `and` và `&&` như hai cách viết đồng nghĩa, cả hai có thể tạo node `And`. Tuy nhiên, nếu hai cú pháp có semantics khác nhau, chúng cần node hoặc thông tin phân biệt riêng.

Một ví dụ khác là phép so sánh phủ định:

```text
not (status == PAID)
```

Có thể được biểu diễn thành:

```text
Not(Equal(status, PAID))
```

Có thể chuyển tiếp thành `NotEqual(status, PAID)` nếu DSL bảo đảm hai dạng tương đương trên kiểu và giá trị thiếu đang xét. Nếu DSL dùng logic ba giá trị hoặc equality tùy biến, phải chứng minh điều kiện tương đương trước khi thay đổi.

### 4.6. Constant folding

Constant folding tính trước các biểu thức chỉ phụ thuộc vào hằng số:

```text
2 + 3 * 4
```

có thể được chuyển thành:

```text
14
```

Phép biến đổi này hữu ích khi kiểu và quy tắc số học đã rõ. Cần xét overflow, độ chính xác thập phân, làm tròn, đơn vị và phép toán có thể phát sinh lỗi. Ví dụ, phép chia cho 0 không được âm thầm biến thành một giá trị tùy ý.

### 4.7. Chuẩn hóa cấu trúc khai báo

DSL có thể cho phép khai báo thuộc tính theo nhiều hình thức, ví dụ dạng ngắn và dạng đầy đủ:

```text
// Dạng ngắn
name: String

// Dạng đầy đủ
attribute name: String required
```

Nếu dạng ngắn có nghĩa là thuộc tính bắt buộc theo mặc định, parser hoặc một pass desugaring có thể chuyển cả hai về cùng một node `AttributeDeclaration` với giá trị `required = true`. Quy tắc mặc định phải được định nghĩa rõ; không được tự suy đoán.

## 5. Dạng chuẩn và tính tương đương ngữ nghĩa

Điều kiện quan trọng nhất của phép chuẩn hóa là bảo toàn ngữ nghĩa. Hai cây có thể khác cấu trúc nhưng cho cùng kết quả trong mọi ngữ cảnh được phép. Khi đó, chúng có thể được xem là tương đương ngữ nghĩa theo định nghĩa của DSL.

### 5.1. Tương đương không chỉ là giống kết quả ở một ví dụ

Giả sử `A and B` và `B and A` cho cùng kết quả Boolean trong một trường hợp cụ thể. Điều đó chưa đủ để kết luận có thể hoán đổi hai nhánh trong mọi chương trình. Nếu `A` hoặc `B` có tác dụng phụ, ném lỗi hoặc phụ thuộc short-circuit, thứ tự đánh giá có thể ảnh hưởng hành vi.

Vì vậy, phép chuẩn hóa cần dựa trên semantics của toán tử, kiểu dữ liệu và các biểu thức con, không chỉ dựa vào một phép biến đổi đại số quen thuộc.

### 5.2. Một số phép biến đổi cần điều kiện

| Phép biến đổi | Điều kiện cần xem xét |
|---|---|
| `x + 0` → `x` | Kiểu số và phép cộng phải bảo đảm đồng nhất; không có overload hay tác dụng phụ khác thường |
| `A and (B and C)` → `And(A, B, C)` | Ngữ nghĩa kết hợp phù hợp và thứ tự đánh giá được giữ nguyên |
| `not (A == B)` → `A != B` | Equality/inequality tương thích, kể cả cách xử lý null hoặc unknown |
| `if true then X else Y` → `X` | Điều kiện là hằng số thuần túy và việc bỏ nhánh không làm mất tác dụng phụ cần thiết |
| `1_000` → `1000` | Hai literal được phân tích thành cùng giá trị và định dạng gốc không cần bảo toàn ở node |
| `unless C { A }` → `if not C { A }` | Cùng semantics về scope, thứ tự và nhánh thực thi |

### 5.3. Chuẩn hóa có thể phụ thuộc kiểu

Một phép biến đổi có thể an toàn với số nguyên nhưng không an toàn với kiểu khác. Ví dụ, `x * 1 = x` là quy tắc quen thuộc với số học thông thường, nhưng DSL có thể overload `*` cho ma trận, đơn vị đo hoặc kiểu tùy biến. Phép biến đổi cần biết kiểu đã được phân giải.

Do đó, một số pass chỉ nên chạy sau name resolution và type checking. Không nên áp dụng các quy tắc dựa trên giả định kiểu khi hệ thống chưa biết kiểu của node.

## 6. Thứ tự các bước chuẩn hóa

Không phải mọi phép chuẩn hóa đều có thể chạy ngay sau parser. Một pipeline có thể được tổ chức như sau:

```text
Văn bản DSL
    |
    v
Lexer và Parser
    |
    v
AST cú pháp ban đầu
    |
    v
Desugaring cú pháp
    |
    v
Phân giải tên và kiểm tra ngữ nghĩa
    |
    v
Kiểm tra kiểu
    |
    v
Chuẩn hóa phụ thuộc kiểu / hằng số
    |
    v
AST chuẩn hóa hoặc IR
    |
    v
Interpreter / Code generator
```

Đây là một pipeline tham khảo. Một số phép chuẩn hóa cú pháp có thể chạy trước semantic analysis; những phép cần biết kiểu hoặc hằng số chỉ có thể chạy sau khi có thông tin ngữ nghĩa. Một DSL đơn giản có thể gộp một vài bước vào cùng pass.

### 6.1. Chia thành các pass nhỏ

Thay vì viết một hàm lớn thực hiện mọi phép biến đổi, nên chia thành các pass có mục tiêu rõ:

1. `DesugarPass`: chuyển cú pháp rút gọn về cấu trúc cốt lõi.
2. `ResolveNamesPass`: liên kết identifier với khai báo tương ứng.
3. `TypeCheckPass`: xác định kiểu và kiểm tra phép toán.
4. `NormalizeExpressionsPass`: chuẩn hóa biểu thức theo semantics đã biết.
5. `ConstantFoldPass`: tính trước biểu thức hằng số an toàn.
6. `LowerToIRPass`: chuyển AST cấp cao thành IR phù hợp với backend.

Không nhất thiết phải có một pass riêng cho từng mục. Việc tách pass nên giúp trách nhiệm rõ ràng, kiểm thử dễ và tránh lặp lại traversal không cần thiết.

### 6.2. Thứ tự pass và phụ thuộc

Ví dụ, constant folding cần biết kiểu số và quy tắc overflow. Desugaring một cú pháp alias có thể cần biết alias đó được khai báo trong scope nào. Một pass không nên chạy trước khi thông tin mà nó phụ thuộc đã sẵn sàng.

Có thể mô tả phụ thuộc:

```text
Parse
  |
  v
Desugar
  |
  v
Resolve names
  |
  v
Type check
  |
  +-------> Normalize typed expressions
                 |
                 v
             Constant fold
                 |
                 v
               Lower IR
```

## 7. Cách triển khai một pass chuẩn hóa

Một pass thường duyệt cây, kiểm tra từng loại node và tạo node mới hoặc giữ nguyên node nếu không cần thay đổi.

### 7.1. Visitor hoặc recursive transformer

Ví dụ mã giả theo phong cách Kotlin:

```kotlin
sealed interface Expr
data class NumberLiteral(val value: Long) : Expr
data class Add(val left: Expr, val right: Expr) : Expr
data class Multiply(val left: Expr, val right: Expr) : Expr

fun normalize(expr: Expr): Expr = when (expr) {
    is NumberLiteral -> expr
    is Add -> {
        val left = normalize(expr.left)
        val right = normalize(expr.right)

        when {
            left is NumberLiteral && right is NumberLiteral ->
                NumberLiteral(left.value + right.value)
            else -> Add(left, right)
        }
    }
    is Multiply -> {
        val left = normalize(expr.left)
        val right = normalize(expr.right)

        when {
            left is NumberLiteral && right is NumberLiteral ->
                NumberLiteral(left.value * right.value)
            else -> Multiply(left, right)
        }
    }
}
```

Đây là ví dụ constant folding tối giản. Một compiler thực tế phải kiểm tra overflow và dùng đúng kiểu số học của DSL; ví dụ trên không nên được xem là quy tắc hoàn chỉnh cho mọi kiểu số.

### 7.2. Tạo node mới thay vì sửa tùy tiện

AST bất biến thường thuận tiện cho việc viết pass: mỗi phép biến đổi tạo node mới nếu có thay đổi và tái sử dụng node cũ nếu không đổi. Cách này giúp tránh việc một bước làm thay đổi cây mà bước khác đang tham chiếu.

Với AST mutable, cần quy định rõ quyền sở hữu node, cách cập nhật cha-con và cách vô hiệu hóa cache hoặc semantic annotation sau khi thay đổi.

### 7.3. Pass nên có đầu vào và đầu ra rõ

Mỗi pass nên mô tả:

- Loại AST mà nó nhận.
- Các node hoặc cấu trúc mà nó có thể thay đổi.
- Những giả định ngữ nghĩa cần có trước khi chạy.
- Bất biến mà cây đầu ra phải thỏa mãn.
- Thông tin nguồn và metadata nào được bảo toàn.
- Cách báo lỗi nếu đầu vào không thỏa điều kiện.

Điều này giúp các pass có thể kết hợp mà không phải dựa vào những giả định ngầm.

## 8. Tính kết thúc, tính lặp lại và tính ổn định

Một hệ thống chuẩn hóa cần bảo đảm các pass không biến đổi qua lại vô hạn hoặc tạo ra kết quả không ổn định.

### 8.1. Tính kết thúc (termination)

Ví dụ, nếu một pass biến `A` thành `B`, còn pass khác biến `B` trở lại `A`, chạy lặp cho đến khi không còn thay đổi sẽ không bao giờ kết thúc.

Để tránh điều này:

- Định nghĩa hướng biến đổi rõ ràng, ví dụ từ cú pháp cấp cao sang cấu trúc cơ bản.
- Không tạo lại cú pháp rút gọn sau khi đã desugar.
- Dùng một độ đo giảm sau mỗi phép biến đổi nếu có thể.
- Giới hạn hoặc phát hiện chu kỳ nếu thuật toán lặp đến điểm cố định.

### 8.2. Tính idempotent

Một phép chuẩn hóa thường nên có tính idempotent: chạy lại trên kết quả đã chuẩn hóa không làm thay đổi kết quả nữa.

```text
normalize(normalize(AST)) = normalize(AST)
```

Tính chất này giúp pipeline dễ dự đoán và hỗ trợ cache. Không phải mọi pass đều cần idempotent độc lập, nhưng pass chuẩn hóa dạng canonical thường nên hướng đến tính chất này.

### 8.3. Tính xác định (determinism)

Cùng một đầu vào và cùng một phiên bản quy tắc nên tạo cùng một AST chuẩn hóa. Không nên để thứ tự duyệt map, thứ tự thread hoặc dữ liệu thời gian ngẫu nhiên ảnh hưởng đến dạng cây.

Tính xác định hữu ích cho hash, cache, build lặp lại và so sánh thay đổi. Nếu DSL cố ý cho phép thứ tự khai báo mang ý nghĩa, chuẩn hóa phải giữ nguyên thứ tự đó.

## 9. Bảo toàn source location, comment và định dạng

AST chuẩn hóa có thể không còn giữ cấu trúc văn bản gốc. Điều này gây khó khăn cho diagnostics, formatter, refactoring và IDE nếu thông tin nguồn bị mất.

### 9.1. Source span

Mỗi node có thể lưu span trỏ đến đoạn nguồn tạo ra nó. Khi một node bị thay thế bằng nhiều node, hệ thống cần quy định span của node mới được kế thừa từ node cũ hay từ các node con.

Ví dụ, `unless condition { action }` được chuyển thành `if not condition { action }`. Node `If` có thể giữ span của toàn bộ `unless`; node `Not` có thể giữ span của phần điều kiện hoặc được đánh dấu là node tổng hợp do compiler tạo ra.

### 9.2. Node tổng hợp (synthetic node)

Node được tạo trong quá trình chuẩn hóa có thể không tương ứng trực tiếp với văn bản do người dùng viết. Có thể đánh dấu chúng là synthetic và lưu nguồn gốc (origin) hoặc node gốc đã tạo ra chúng.

Điều này giúp compiler phân biệt lỗi phát sinh từ mã người dùng với lỗi do một phép biến đổi nội bộ. Khi cần, thông báo lỗi có thể trỏ về biểu thức gốc thay vì vị trí không tồn tại trong văn bản.

### 9.3. Comment và trivia

Comment, khoảng trắng và xuống dòng thường không ảnh hưởng semantics, nhưng quan trọng với công cụ chỉnh sửa mã. Nếu AST loại bỏ chúng, formatter hoặc refactoring có thể không tái tạo được văn bản gần với bản gốc.

Một giải pháp là lưu CST hoặc token stream song song với AST; một giải pháp khác là gắn trivia vào node/token. Lựa chọn phụ thuộc việc DSL có cần format-preserving transformation hay chỉ cần biên dịch và thực thi.

## 10. Chuẩn hóa tên và liên kết symbol

AST ban đầu thường chứa tên ở dạng văn bản. Sau name resolution, identifier có thể được liên kết với một symbol duy nhất thay vì chỉ giữ chuỗi tên.

Ví dụ, hai tham chiếu `total` trong hai scope khác nhau có thể trỏ đến hai thuộc tính khác nhau. Sau phân giải tên, semantic model có thể gắn symbol ID cho mỗi node. Các bước sau làm việc với symbol ID sẽ tránh phải so sánh tên văn bản lặp lại.

Với DSL hỗ trợ Unicode, việc chuẩn hóa tên cần theo chính sách đã công bố, chẳng hạn NFC và quy tắc phân biệt hoa thường. Khai báo và tham chiếu phải đi qua cùng quy trình. Không nên tự ý áp dụng case folding hoặc normalization cho string literal nghiệp vụ chỉ vì identifier có quy tắc riêng.

## 11. Chuẩn hóa có thể ảnh hưởng đến thứ tự và tác dụng phụ

Đây là một trong những giới hạn quan trọng nhất của AST normalization. Một phép biến đổi trông hợp lý về đại số có thể làm thay đổi hành vi chương trình.

### 11.1. Short-circuit

Giả sử DSL định nghĩa `and` theo short-circuit: nếu vế trái là false, vế phải không được đánh giá. Biểu thức:

```text
A and B
```

có thể không tương đương với một dạng đánh giá cả hai vế trước rồi kết hợp kết quả nếu `B` có tác dụng phụ hoặc có thể phát sinh lỗi.

Khi làm phẳng cây `And`, cần giữ thứ tự toán hạng và semantics short-circuit.

### 11.2. Phép toán không giao hoán hoặc có overload

Không được tự động đổi `A + B` thành `B + A` nếu phép cộng không giao hoán với kiểu dữ liệu đó, hoặc nếu một trong hai biểu thức có tác dụng phụ.

### 11.3. Giá trị thiếu và logic ba giá trị

Với logic có `unknown` hoặc `null`, các luật Boolean quen thuộc có thể cần điều chỉnh. Ví dụ, `not (A == B)` không nhất thiết tương đương `A != B` nếu equality và inequality xử lý giá trị thiếu khác nhau.

### 11.4. Ngoại lệ và lỗi runtime

Đưa một biểu thức hằng số ra tính trước có thể làm lỗi xảy ra ở thời điểm biên dịch thay vì thời điểm thực thi. Điều này có thể được chấp nhận hoặc không tùy semantics của DSL. Compiler cần quy định rõ lỗi constant expression được báo ở giai đoạn nào.

## 12. So sánh AST trước và sau chuẩn hóa

Ví dụ một DSL quy tắc có cú pháp rút gọn:

```text
rule remoteShipping {
    unless destination.zone == "local" {
        shipping.fee += 15_000
    }
}
```

AST cú pháp ban đầu có thể là:

```text
RuleDeclaration
└── UnlessStatement
    ├── Equal
    │   ├── MemberAccess(destination, zone)
    │   └── StringLiteral("local")
    └── Block
        └── AddAssignment
            ├── MemberAccess(shipping, fee)
            └── NumberLiteral(15000)
```

Sau desugaring:

```text
RuleDeclaration
└── IfStatement
    ├── Not
    │   └── Equal
    │       ├── MemberAccess(destination, zone)
    │       └── StringLiteral("local")
    └── Block
        └── AddAssignment
            ├── MemberAccess(shipping, fee)
            └── NumberLiteral(15000)
```

Interpreter chỉ cần hỗ trợ `IfStatement` và `Not` nếu `UnlessStatement` không còn tồn tại sau pass. Source span của node mới cần liên kết với vị trí `unless` ban đầu để lỗi và công cụ IDE vẫn có thể trỏ về mã nguồn.

## 13. Chuẩn hóa và canonical representation

Khi cần so sánh hai chương trình hoặc tạo hash, một hệ thống có thể sinh biểu diễn chuẩn (canonical representation) từ AST đã chuẩn hóa.

Ví dụ, các literal số có dấu phân cách khác nhau có thể cùng được lưu dưới giá trị nguyên `1000000`. Các biểu thức có ngoặc dư có thể tạo cùng cấu trúc. Một bộ serialize canonical có thể ghi node, kiểu và giá trị theo thứ tự xác định để tạo hash ổn định.

Ứng dụng:

- **Caching:** dùng hash AST chuẩn hóa làm khóa cache cho kết quả phân tích hoặc sinh mã.
- **Deduplication:** nhận diện các quy tắc có cấu trúc tương đương theo phạm vi được hỗ trợ.
- **Diff:** tập trung vào thay đổi cấu trúc thay vì thay đổi khoảng trắng hoặc cách viết literal tương đương.
- **Audit:** ghi nhận phiên bản quy tắc và dạng biểu diễn đã được xử lý.
- **Reproducible builds:** bảo đảm cùng đầu vào và cùng phiên bản compiler tạo biểu diễn trung gian ổn định.

Canonical representation không nên loại bỏ thông tin có ý nghĩa. Nếu thứ tự khai báo ảnh hưởng đến ưu tiên thực thi, không được sắp xếp lại các khai báo chỉ để hash ổn định. Có thể tạo hai dạng: một dạng giữ semantics đầy đủ và một dạng phục vụ so sánh ở phạm vi hẹp đã định nghĩa.

## 14. Kiểm thử các phép chuẩn hóa

Kiểm thử pass không chỉ xác nhận cây đầu ra có hình dạng mong muốn. Cần kiểm tra cả điều kiện áp dụng, tính ổn định và việc bảo toàn semantics.

Các loại kiểm thử hữu ích:

1. **Kiểm thử cấu trúc:** đầu vào cụ thể phải tạo đúng loại node và quan hệ cha-con sau pass.
2. **Kiểm thử ngữ nghĩa:** đánh giá AST trước và sau trên cùng tập dữ liệu phải cho kết quả tương đương theo đặc tả.
3. **Kiểm thử idempotence:** chuẩn hóa hai lần phải cho cùng kết quả như một lần.
4. **Kiểm thử thứ tự pass:** xác nhận pass không chạy trước khi các phụ thuộc như type information đã có.
5. **Kiểm thử source mapping:** lỗi trên node tổng hợp vẫn trỏ về vị trí nguồn hữu ích.
6. **Kiểm thử trường hợp biên:** null/unknown, overflow, tác dụng phụ, short-circuit, Unicode và cấu trúc lồng sâu.
7. **Kiểm thử không áp dụng:** nếu điều kiện biến đổi không thỏa, cây phải được giữ nguyên hoặc báo lỗi phù hợp.

Với các phép biến đổi phức tạp, có thể dùng property-based testing để sinh nhiều AST hợp lệ rồi so sánh kết quả thực thi trước và sau. Cách này hỗ trợ phát hiện trường hợp mà một số ví dụ thủ công bỏ sót.

## 15. Những sai lầm thường gặp

| Sai lầm | Hậu quả | Cách khắc phục |
|---|---|---|
| Coi mọi phép làm cây ngắn hơn là chuẩn hóa an toàn | Có thể thay đổi kết quả hoặc tác dụng phụ | Định nghĩa điều kiện ngữ nghĩa cho từng rewrite |
| Chuẩn hóa trước khi biết kiểu | Áp dụng luật không đúng với kiểu thực tế | Chạy pass sau type checking khi cần |
| Sắp xếp lại toán hạng tùy tiện | Làm thay đổi short-circuit hoặc thứ tự tác dụng phụ | Giữ thứ tự trừ khi chứng minh được phép hoán đổi |
| Không giữ source span | Diagnostic trỏ sai hoặc không trỏ được về mã gốc | Bảo toàn origin và source mapping |
| Gộp mọi pass thành một hàm lớn | Khó hiểu phụ thuộc và khó kiểm thử | Chia pass theo mục tiêu và hợp đồng |
| Pass biến đổi qua lại | Pipeline không kết thúc hoặc kết quả không ổn định | Đặt hướng biến đổi, kiểm tra chu kỳ và idempotence |
| Chuẩn hóa cả string literal một cách ngầm định | Thay đổi dữ liệu người dùng | Phân biệt chính sách identifier và nội dung chuỗi |
| Dùng AST chuẩn hóa để tái tạo mã nguồn gốc | Mất comment, dấu ngoặc và định dạng | Giữ CST/token/trivia song song nếu cần |

## 16. Nguyên tắc thiết kế thực tế

Khi xây dựng chuẩn hóa cây cho DSL, có thể áp dụng các nguyên tắc sau:

- Xác định mục đích cụ thể của dạng chuẩn: semantic analysis, execution, code generation, caching hay tooling.
- Chỉ chuẩn hóa những khác biệt không có ý nghĩa hoặc đã chứng minh được tương đương theo semantics.
- Chia phép biến đổi thành pass nhỏ, có đầu vào, đầu ra và điều kiện rõ ràng.
- Chạy pass phụ thuộc kiểu sau khi đã có thông tin kiểu và symbol cần thiết.
- Giữ thứ tự đánh giá và tác dụng phụ theo đúng semantics của DSL.
- Bảo toàn source span, origin và trivia khi công cụ cần truy ngược về văn bản.
- Đảm bảo pass kết thúc, có tính xác định và hướng đến idempotence.
- Kiểm thử cả cấu trúc cây lẫn tương đương ngữ nghĩa.
- Quản lý phiên bản của quy tắc chuẩn hóa vì thay đổi pass có thể ảnh hưởng cache và kết quả build.

## 17. Kết luận

Chuẩn hóa cây là quá trình đưa AST về một dạng biểu diễn có quy ước để các bước xử lý DSL làm việc đơn giản và nhất quán hơn. Các kỹ thuật thường gặp gồm desugaring, làm phẳng biểu thức, chuẩn hóa literal và tên, constant folding, cùng chuyển đổi sang IR.

Điều kiện cốt lõi là bảo toàn ngữ nghĩa. Mỗi phép biến đổi phải xét kiểu dữ liệu, thứ tự đánh giá, short-circuit, giá trị thiếu, tác dụng phụ và lỗi runtime. Pipeline cũng cần có thứ tự pass rõ, bảo đảm kết thúc và giữ đủ thông tin nguồn cho diagnostics hoặc IDE.

Một AST chuẩn hóa tốt giúp kiểm tra ngữ nghĩa, thực thi, sinh mã, tối ưu, so sánh và cache dễ dàng hơn. Hãy chọn dạng chuẩn theo mục tiêu của DSL, chỉ áp dụng các phép biến đổi có cơ sở và kiểm thử để bảo đảm cây sau chuẩn hóa vẫn biểu đạt đúng ý định ban đầu của người viết.
