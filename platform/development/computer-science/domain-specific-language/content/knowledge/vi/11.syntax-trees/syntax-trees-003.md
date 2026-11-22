# Nút và quan hệ cây

## 1. Cây cú pháp biểu diễn điều gì?

Trong một ngôn ngữ miền chuyên biệt (Domain-Specific Language — DSL), văn bản nguồn được tổ chức thành các cấu trúc có ý nghĩa: khai báo, câu lệnh, biểu thức, tên, giá trị và nhóm thành phần. Sau khi parser phân tích văn bản theo ngữ pháp, công cụ thường tạo ra một cấu trúc dữ liệu dạng cây để biểu diễn những thành phần đó. Cấu trúc này là nền tảng cho kiểm tra ngữ nghĩa, định dạng, phân tích, sinh mã và thực thi.

Một **nút (node)** biểu diễn một thành phần trong cấu trúc cú pháp. **Quan hệ cây** mô tả cách các nút liên kết với nhau, chẳng hạn nút nào chứa nút nào, nút nào là cha, nút nào là con và thứ tự các nút con. Một cây có một nút gốc, mỗi nút khác có đúng một nút cha và không có chu trình theo quan hệ cha-con.

Ví dụ, xét DSL giả định:

~~~text
pipeline "daily-revenue" {
    source "orders.csv"
    filter status == "PAID"
    aggregate total = sum(amount)
}
~~~

Parser có thể tạo cây khái quát:

~~~text
Pipeline
├── Name("daily-revenue")
├── Source
│   └── Path("orders.csv")
├── Filter
│   └── Equal
│       ├── Field("status")
│       └── String("PAID")
└── Aggregate
    ├── Target("total")
    └── Sum
        └── Field("amount")
~~~

Nút Pipeline là gốc của cây trong ví dụ. Nó chứa các nút con biểu diễn tên pipeline và các khai báo. Nút Filter chứa biểu thức điều kiện Equal; biểu thức này lại chứa hai nút con là tham chiếu trường và giá trị chuỗi. Cây thể hiện cả cấu trúc lẫn quan hệ bao chứa của chương trình.

## 2. Nút là đơn vị cơ bản của cây

Mỗi nút thường đại diện cho một loại cấu trúc đã được ngữ pháp hoặc mô hình cú pháp xác định. Nút có thể mang dữ liệu riêng, chứa các nút con hoặc thực hiện cả hai vai trò.

Một nút thường có một số thông tin:

| Thành phần | Ý nghĩa | Ví dụ |
|---|---|---|
| Loại nút (node kind) | Cho biết nút biểu diễn cấu trúc nào | Pipeline, Filter, BinaryExpression |
| Giá trị hoặc thuộc tính | Dữ liệu gắn với nút | Tên pipeline, toán tử, literal |
| Các nút con | Thành phần nằm bên trong nút | Hai toán hạng của phép so sánh |
| Vị trí nguồn | Vị trí tương ứng trong văn bản DSL | Tệp, dòng, cột, khoảng ký tự |
| Metadata | Thông tin phục vụ phân tích hoặc công cụ | Kiểu suy luận, mã định danh, chú thích |

Không phải mọi loại nút đều cần mọi trường. Nút literal có thể chỉ chứa giá trị và vị trí nguồn; nút biểu thức nhị phân cần toán tử và hai nút con; nút khai báo có thể chứa tên, danh sách tham số và thân khai báo.

### 2.1. Loại nút

Loại nút xác định cách các giai đoạn sau hiểu và xử lý nút. Ví dụ:

- PipelineDeclaration: khai báo pipeline.
- SourceDeclaration: khai báo nguồn dữ liệu.
- FilterStatement: câu lệnh lọc.
- AggregateStatement: câu lệnh tổng hợp.
- IdentifierExpression: biểu thức tham chiếu tên.
- StringLiteral: giá trị chuỗi.
- BinaryExpression: biểu thức có toán tử hai ngôi.

Tên và số lượng loại nút phụ thuộc vào ngôn ngữ. Có thể tạo một loại nút riêng cho mỗi cấu trúc quan trọng, hoặc dùng một số loại tổng quát kèm trường mô tả. Thiết kế nên giúp các thao tác phân tích dễ hiểu và hạn chế trạng thái không hợp lệ.

### 2.2. Thuộc tính của nút

Thuộc tính là dữ liệu được lưu trực tiếp trên nút. Ví dụ:

~~~text
StringLiteral
    value = "PAID"
    sourceStart = 52
    sourceEnd = 58
~~~

Giá trị chuỗi là nội dung ngữ nghĩa; vị trí nguồn cho phép công cụ trỏ ngược đến đoạn văn bản. Với một nút biểu thức so sánh, thuộc tính có thể chứa loại toán tử như EQUALS, trong khi hai toán hạng được biểu diễn bằng nút con.

Nên phân biệt dữ liệu thuộc về chính nút với dữ liệu được biểu diễn bằng nút con. Chẳng hạn, tên hàm sum có thể là thuộc tính của CallExpression, hoặc có thể là một nút IdentifierExpression con. Lựa chọn nào phù hợp tùy vào việc ngôn ngữ cần xử lý tên hàm như một tham chiếu độc lập hay chỉ như một phần cố định của cấu trúc lời gọi.

### 2.3. Nút lá và nút trong

- **Nút lá (leaf node)** không có nút con. Literal, tên định danh hoặc token được giữ lại trong cây thường là nút lá.
- **Nút trong (internal node)** có ít nhất một nút con. Nút khai báo, câu lệnh, phép toán và lời gọi hàm thường là nút trong.

Ví dụ:

~~~text
Add
├── Number(2)
└── Multiply
    ├── Number(3)
    └── Number(4)
~~~

Add và Multiply là nút trong; ba nút Number là nút lá. Cấu trúc này thể hiện phép nhân được nhóm trước phép cộng theo cách biểu thức đã được phân tích.

## 3. Các quan hệ trong cây

Quan hệ cha-con là quan hệ cốt lõi của cây, nhưng khi làm việc với AST còn cần hiểu thứ tự, số lượng và loại quan hệ giữa các nút.

### 3.1. Quan hệ cha-con

Nếu nút A trực tiếp chứa nút B, A là cha (parent) và B là con (child). Một nút có thể có không, một hoặc nhiều nút con.

~~~text
FilterStatement
└── EqualExpression
    ├── FieldReference
    └── StringLiteral
~~~

Trong hình trên:

- FilterStatement là cha trực tiếp của EqualExpression.
- EqualExpression là cha của FieldReference và StringLiteral.
- FieldReference và StringLiteral là anh em (siblings), vì chúng có cùng nút cha.
- FilterStatement là tổ tiên (ancestor) của hai nút lá.

Quan hệ cha-con có hướng từ nút bao chứa đến nút thành phần. Khi đi từ một nút lên phía gốc, ta lần theo các quan hệ cha; khi đi xuống, ta duyệt các nút con.

### 3.2. Thứ tự các nút con

Trong AST của một ngôn ngữ lập trình, thứ tự nút con thường có ý nghĩa. Ví dụ, trong phép trừ:

~~~text
Subtract
├── Left: Number(10)
└── Right: Number(3)
~~~

Đổi vị trí hai nút con sẽ biến 10 - 3 thành 3 - 10. Vì vậy, danh sách con thường phải giữ đúng thứ tự xuất hiện hoặc thứ tự ngữ nghĩa mà grammar quy định.

Một số cấu trúc có thể xem các phần tử như tập hợp không thứ tự. Tuy nhiên, nếu thứ tự ảnh hưởng đến cách thực thi, định dạng hoặc kết quả, mô hình cây phải bảo toàn thứ tự đó. Không nên dùng cấu trúc dữ liệu không bảo đảm thứ tự cho một danh sách câu lệnh tuần tự.

### 3.3. Số lượng nút con (arity)

Arity là số lượng toán hạng hoặc nút con mà một cấu trúc nhận:

- Nút một ngôi (unary) có một toán hạng, ví dụ NotExpression.
- Nút hai ngôi (binary) có hai toán hạng, ví dụ AddExpression.
- Nút nhiều ngôi (n-ary) có một danh sách toán hạng, ví dụ AllExpression.

~~~text
Not
└── Field("enabled")

GreaterThan
├── Field("amount")
└── Number(100)

All
├── Condition A
├── Condition B
└── Condition C
~~~

Arity thường được kiểm soát bằng kiểu dữ liệu hoặc ràng buộc khi tạo nút. Một nút phép cộng nhị phân không nên được tạo với chỉ một toán hạng; nút danh sách có thể cho phép số phần tử thay đổi theo ngữ pháp.

### 3.4. Quan hệ chứa và quan hệ tham chiếu

Quan hệ cha-con thể hiện cấu trúc cây. Nó khác với quan hệ tham chiếu đến một khai báo hoặc đối tượng khác trong miền.

Ví dụ:

~~~text
let taxRate = 0.08

rule "calculate-tax" {
    set tax = subtotal * taxRate
}
~~~

Nút IdentifierReference("taxRate") trong biểu thức có thể tham chiếu đến nút khai báo VariableDeclaration("taxRate"). Hai nút không nhất thiết có quan hệ cha-con trực tiếp. Một nút là thành phần của biểu thức; nút còn lại nằm trong phần khai báo khác.

Sau phân tích ngữ nghĩa, công cụ có thể lưu liên kết từ nút tham chiếu đến ký hiệu (symbol) tương ứng, hoặc lưu mã định danh của ký hiệu. Liên kết này bổ sung cho cây cú pháp và thường tạo thành một đồ thị quan hệ riêng.

## 4. Cây phân tích cú pháp và AST

Hai cấu trúc thường gặp là cây phân tích cú pháp cụ thể (Concrete Syntax Tree — CST, còn gọi là parse tree) và cây cú pháp trừu tượng (Abstract Syntax Tree — AST). Chúng có quan hệ gần gũi nhưng phục vụ mục đích khác nhau.

### 4.1. Concrete Syntax Tree

CST phản ánh sát các quy tắc của grammar. Nó thường giữ lại các nút tương ứng với non-terminal, token, dấu phân cách và đôi khi cả thành phần trình bày.

Ví dụ với biểu thức:

~~~text
amount + 2 * tax
~~~

CST giản lược có thể có dạng:

~~~text
Expression
└── AdditiveExpression
    ├── MultiplicativeExpression
    │   └── Primary
    │       └── Identifier("amount")
    ├── PLUS("+")
    └── MultiplicativeExpression
        ├── Primary
        │   └── Number("2")
        ├── STAR("*")
        └── Primary
            └── Identifier("tax")
~~~

CST giữ các tầng grammar và token toán tử. Điều này hữu ích khi cần ánh xạ chính xác cấu trúc nguồn, xử lý lỗi cú pháp hoặc định dạng lại văn bản.

### 4.2. Abstract Syntax Tree

AST bỏ qua nhiều chi tiết cú pháp không cần thiết cho các thao tác ngữ nghĩa. Cây cho cùng biểu thức có thể được rút gọn:

~~~text
Add
├── Identifier("amount")
└── Multiply
    ├── Number(2)
    └── Identifier("tax")
~~~

AST làm nổi bật cấu trúc có ý nghĩa: cộng amount với tích của 2 và tax. Dấu ngoặc, quy tắc ưu tiên hoặc các tầng grammar trung gian không nhất thiết được lưu thành nút riêng nếu chúng không mang thêm ý nghĩa cho các giai đoạn sau.

### 4.3. So sánh CST và AST

| Tiêu chí | CST / Parse tree | AST |
|---|---|---|
| Mục tiêu | Phản ánh cấu trúc theo grammar | Biểu diễn cấu trúc có ý nghĩa của chương trình |
| Chi tiết token | Thường giữ nhiều token và dấu phân cách | Có thể bỏ token trình bày hoặc dấu không cần thiết |
| Số tầng | Có thể nhiều tầng trung gian | Thường gọn hơn |
| Quan hệ với grammar | Gắn chặt với quy tắc grammar | Có thể độc lập hơn với cách viết grammar |
| Định dạng nguồn | Có thể thuận lợi khi giữ token và trivia | Cần thêm thông tin nguồn hoặc CST nếu muốn tái tạo nguyên văn |
| Kiểm tra ngữ nghĩa | Có thể thực hiện nhưng thường nhiều chi tiết cú pháp | Thường thuận tiện hơn cho phân tích biểu thức và khai báo |

Không phải parser nào cũng tạo cả CST lẫn AST. Một số parser tạo AST trực tiếp; một số công cụ giữ CST để phục vụ IDE hoặc formatter rồi chuyển sang AST cho phân tích. Lựa chọn phụ thuộc vào việc có cần bảo toàn khoảng trắng, chú thích và cách viết nguyên gốc hay không.

## 5. Mô hình hóa các loại nút thường gặp

Khi xây dựng AST cho DSL, nên xác định các nhóm nút dựa trên cấu trúc của miền và grammar.

### 5.1. Nút chương trình và khai báo

Nút gốc thường biểu diễn toàn bộ tệp hoặc đơn vị biên dịch:

~~~text
Program
├── ImportDeclaration
├── VariableDeclaration
├── PipelineDeclaration
└── RuleDeclaration
~~~

Nút Program có thể chứa danh sách khai báo cấp cao nhất. Các khai báo có thể là pipeline, quy tắc, biến, module hoặc thành phần khác tùy DSL.

### 5.2. Nút câu lệnh

Câu lệnh biểu diễn một thao tác hoặc cấu trúc điều khiển:

~~~text
PipelineBody
├── SourceStatement
├── FilterStatement
├── GroupByStatement
└── OutputStatement
~~~

Mỗi loại câu lệnh có thể có tập nút con riêng. Ví dụ, FilterStatement chứa biểu thức Boolean; OutputStatement chứa vị trí và định dạng đầu ra.

### 5.3. Nút biểu thức

Biểu thức biểu diễn giá trị hoặc phép tính:

~~~text
GreaterThan
├── FieldReference("amount")
└── NumberLiteral(100)
~~~

Một biểu thức có thể là literal, tham chiếu tên, lời gọi hàm, phép toán, truy cập thuộc tính hoặc biểu thức điều kiện. Nút biểu thức thường được lồng đệ quy, nên cây có thể có độ sâu thay đổi.

### 5.4. Nút literal và định danh

Literal chứa giá trị được viết trực tiếp trong nguồn:

- StringLiteral: chuỗi ký tự.
- NumberLiteral: số.
- BooleanLiteral: true hoặc false.
- NullLiteral: giá trị rỗng nếu DSL hỗ trợ.

Định danh (identifier) đặt tên cho biến, trường, hàm hoặc thành phần miền. Cần phân biệt nút định danh trong khai báo với nút tham chiếu định danh trong biểu thức nếu chúng có quy tắc xử lý khác nhau.

### 5.5. Nút danh sách và nút tùy chọn

Một khai báo có thể chứa danh sách tham số, câu lệnh hoặc phần tử:

~~~text
FunctionCall("sum")
└── Arguments
    └── FieldReference("amount")
~~~

Nút danh sách có thể chứa không, một hoặc nhiều nút con. Một thành phần tùy chọn có thể được biểu diễn bằng giá trị nullable, kiểu Optional, hoặc một loại nút cụ thể. Cần chọn cách biểu diễn nhất quán để phân biệt “không được cung cấp” với “được cung cấp nhưng có giá trị rỗng”.

## 6. Quan hệ cây qua một ví dụ biểu thức

Xét biểu thức:

~~~text
(price - discount) * quantity >= 100
~~~

Theo quy tắc ưu tiên và dấu ngoặc, AST có thể là:

~~~text
GreaterThanOrEqual
├── Multiply
│   ├── Subtract
│   │   ├── Identifier("price")
│   │   └── Identifier("discount")
│   └── Identifier("quantity")
└── Number(100)
~~~

Có thể đọc cấu trúc từ gốc xuống:

1. Nút gốc là phép so sánh lớn hơn hoặc bằng.
2. Vế trái là phép nhân.
3. Toán hạng trái của phép nhân là phép trừ giữa price và discount.
4. Toán hạng phải của phép nhân là quantity.
5. Vế phải của phép so sánh là số 100.

Nếu thay đổi ngoặc:

~~~text
price - (discount * quantity) >= 100
~~~

AST thay đổi:

~~~text
GreaterThanOrEqual
├── Subtract
│   ├── Identifier("price")
│   └── Multiply
│       ├── Identifier("discount")
│       └── Identifier("quantity")
└── Number(100)
~~~

Hai cây có quan hệ khác nhau nên biểu diễn hai phép tính khác nhau. AST không chỉ lưu các token; nó thể hiện cách các toán hạng được kết hợp.

## 7. Mô hình nút trong Java

Trong một công cụ DSL viết bằng Java, có thể dùng interface, lớp, record hoặc sealed hierarchy để biểu diễn các loại nút. Cấu trúc phù hợp phụ thuộc phiên bản Java và mức độ mở rộng dự kiến.

### 7.1. Dùng interface và record

Ví dụ giản lược với Java 17:

~~~java
sealed interface Expr
    permits NameExpr, NumberExpr, StringExpr, BinaryExpr {
}

record NameExpr(String name) implements Expr {
}

record NumberExpr(java.math.BigDecimal value) implements Expr {
}

record StringExpr(String value) implements Expr {
}

record BinaryExpr(
    Expr left,
    BinaryOperator operator,
    Expr right
) implements Expr {
}

enum BinaryOperator {
    ADD,
    SUBTRACT,
    MULTIPLY,
    DIVIDE,
    EQUALS,
    GREATER_THAN
}
~~~

Expr là kiểu gốc của nhóm biểu thức. Các record biểu diễn từng loại nút cụ thể. BinaryExpr có hai nút con left và right, cùng một thuộc tính operator.

Ví dụ tạo cây:

~~~java
Expr expression = new BinaryExpr(
    new NameExpr("amount"),
    BinaryOperator.GREATER_THAN,
    new NumberExpr(new java.math.BigDecimal("100"))
);
~~~

Kiểu sealed giới hạn các loại biểu thức được phép triển khai Expr theo danh sách permits. Điều này hữu ích khi DSL có tập nút được kiểm soát. Nếu cần plugin bên ngoài định nghĩa nút mới, mô hình mở bằng interface thông thường có thể phù hợp hơn.

### 7.2. Nút câu lệnh và chương trình

Có thể tạo hệ thống kiểu riêng cho câu lệnh:

~~~java
sealed interface Statement
    permits FilterStatement, OutputStatement, AggregateStatement {
}

record FilterStatement(Expr condition) implements Statement {
}

record OutputStatement(String path) implements Statement {
}

record AggregateStatement(String name, Expr expression)
    implements Statement {
}

record Program(java.util.List<Statement> statements) {
    Program {
        statements = java.util.List.copyOf(statements);
    }
}
~~~

Program chứa danh sách câu lệnh theo thứ tự. Dùng List.copyOf tạo một danh sách không thể bị sửa qua tham chiếu trả về của record, giúp cấu trúc AST ổn định hơn sau khi xây dựng.

### 7.3. Kiểm soát tính hợp lệ khi tạo nút

Mỗi loại nút nên bảo đảm các bất biến của nó. Ví dụ:

- Nút biểu thức nhị phân phải có đủ hai toán hạng.
- Nút khai báo cần có tên hợp lệ.
- Nút danh sách không nên chứa phần tử null nếu grammar không cho phép.
- Nút tổng hợp cần có hàm và biểu thức đầu vào.
- Danh sách con nên giữ thứ tự nguồn nếu thứ tự có ý nghĩa.

Có thể kiểm tra bất biến trong constructor hoặc factory method. Điều này giúp tránh tạo AST ở trạng thái không hợp lệ và làm đơn giản các giai đoạn phân tích sau.

## 8. Vị trí nguồn và thông tin phụ trên nút

Một AST chỉ chứa loại nút và giá trị có thể đủ cho interpreter đơn giản. Tuy nhiên, công cụ DSL thực tế thường cần liên kết mỗi nút với vị trí trong văn bản nguồn.

### 8.1. Source span

Source span mô tả đoạn văn bản đã tạo ra nút:

~~~text
SourceSpan
    file = "daily.pipe"
    startLine = 4
    startColumn = 12
    endLine = 4
    endColumn = 28
~~~

Có thể lưu offset ký tự bắt đầu và kết thúc thay vì chỉ lưu dòng/cột. Từ offset, công cụ có thể tính vị trí hiển thị hoặc trích đoạn nguồn. Cần thống nhất offset đếm theo byte, code point hay đơn vị UTF-16 để tránh sai vị trí khi nguồn có ký tự Unicode.

### 8.2. Vì sao cần vị trí nguồn?

Vị trí nguồn hữu ích cho:

- Báo lỗi cú pháp và ngữ nghĩa đúng vị trí.
- Hiển thị cảnh báo tại biểu thức liên quan.
- Tạo liên kết từ AST về mã nguồn trong IDE.
- Gỡ lỗi và theo dõi một bước thực thi.
- Giữ chú thích hoặc định dạng khi công cụ biến đổi mã.

Ví dụ, nếu sum(status) không hợp lệ vì status có kiểu chuỗi, thông báo có thể trỏ thẳng đến nút FieldReference("status") thay vì chỉ báo lỗi chung ở cả câu lệnh.

### 8.3. Metadata và dữ liệu suy luận

Sau phân tích ngữ nghĩa, nút có thể được bổ sung:

- Kiểu dữ liệu đã suy luận.
- Symbol hoặc mã định danh khai báo được tham chiếu.
- Kiểu chuyển đổi đã chèn.
- Kết quả kiểm tra hằng số.
- Cảnh báo hoặc chẩn đoán liên quan.

Nên tách metadata phân tích khỏi dữ liệu cú pháp cốt lõi nếu có thể. Ví dụ, AST nguồn có thể bất biến; kết quả phân tích được lưu trong một bảng phụ theo node ID hoặc trong một mô hình đã phân tích. Cách này tránh làm thay đổi cây trong quá trình nhiều công cụ cùng đọc nó.

## 9. Cây và đồ thị: ranh giới cần hiểu rõ

AST thường được mô hình hóa như một cây, nhưng toàn bộ thông tin của chương trình sau phân tích có thể tạo thành đồ thị.

### 9.1. Vì sao AST là cây?

Theo quan hệ cấu trúc, mỗi nút AST có một vị trí trong chương trình:

- Có đúng một nút gốc cho một đơn vị cú pháp.
- Mỗi nút khác có một nút cha.
- Một nút có thể có nhiều nút con.
- Không có chu trình theo quan hệ cha-con.

Nhờ tính chất này, các phép duyệt đệ quy có thể xử lý cây một cách rõ ràng.

### 9.2. Vì sao mô hình ngữ nghĩa có thể là đồ thị?

Một tham chiếu có thể trỏ đến khai báo ở nơi khác. Nhiều tham chiếu có thể cùng trỏ đến một khai báo. Các module có thể phụ thuộc lẫn nhau. Những liên kết đó không phù hợp với quan hệ cha-con của một cây duy nhất.

Ví dụ:

~~~text
Declaration: taxRate
    ^ referenced by
    |
Expression in Rule A
    |
    | referenced by
    v
Expression in Rule B
~~~

Hình trên chỉ minh họa quan hệ tham chiếu. Trong cấu trúc thực tế, cả hai nút biểu thức có thể nằm ở những nhánh khác nhau của AST nhưng cùng tham chiếu đến một symbol. Nếu đưa cùng một nút khai báo vào làm con của nhiều cha, cấu trúc sẽ không còn là cây theo định nghĩa thông thường.

Giải pháp thường dùng là giữ AST với quan hệ cha-con riêng, sau đó lưu liên kết ngữ nghĩa bằng symbol ID, reference table hoặc một đồ thị phụ. Không nên trộn hai loại quan hệ mà không phân biệt.

### 9.3. Cây không nhất thiết là cây nhị phân

Một AST thường là cây nhiều nhánh (n-ary tree), không phải cây nhị phân. Một nút Program có thể có hàng trăm khai báo; một nút AllCondition có thể chứa nhiều điều kiện con; một nút FunctionCall có thể có số đối số tùy ý.

Vì vậy, không nên áp dụng cấu trúc chỉ có left và right cho mọi nút. Chỉ những cấu trúc thực sự có hai thành phần có thứ tự mới cần hai trường riêng.

## 10. Duyệt cây

Sau khi tạo AST, công cụ thường duyệt cây để kiểm tra, chuyển đổi hoặc thực thi. Duyệt cây là quá trình thăm các nút theo một thứ tự xác định.

### 10.1. Preorder

Preorder thăm nút cha trước rồi đến các nút con:

1. Thăm nút hiện tại.
2. Duyệt lần lượt từng nút con.

Với cây:

~~~text
Add
├── Number(2)
└── Multiply
    ├── Number(3)
    └── Number(4)
~~~

Thứ tự preorder là: Add, Number(2), Multiply, Number(3), Number(4).

Preorder hữu ích khi cần xử lý khai báo bao ngoài trước nội dung bên trong, chẳng hạn tạo scope cho một khối rồi phân tích các khai báo con.

### 10.2. Postorder

Postorder thăm các nút con trước rồi mới xử lý nút cha:

1. Duyệt từng nút con.
2. Thăm nút hiện tại.

Với cây trên, thứ tự postorder là: Number(2), Number(3), Number(4), Multiply, Add.

Postorder phù hợp khi kết quả của nút cha phụ thuộc vào kết quả đã tính của các nút con, ví dụ đánh giá biểu thức hoặc sinh một phần mã từ các biểu thức con.

### 10.3. Inorder với cây nhị phân

Inorder thăm cây con trái, nút hiện tại rồi cây con phải. Cách duyệt này có ý nghĩa quen thuộc với cây nhị phân và có thể tạo thứ tự toán hạng-trung tố cho biểu thức.

Tuy nhiên, AST tổng quát có thể có nhiều hơn hai nút con, vì vậy preorder và postorder thường phù hợp hơn để mô tả cách duyệt chung. Với một loại nút cụ thể, có thể định nghĩa thứ tự duyệt riêng.

### 10.4. Duyệt theo chiều rộng

Breadth-first traversal thăm các nút theo từng tầng, bắt đầu từ gốc. Nó hữu ích khi cần thống kê độ sâu, hiển thị cây theo lớp hoặc tìm một nút gần gốc nhất theo tiêu chí nào đó.

Không phải tác vụ AST nào cũng cần duyệt theo chiều rộng. Phân tích ngữ nghĩa thường cần thứ tự phụ thuộc vào scope và ngữ cảnh, do đó một visitor đệ quy có kiểm soát thường phù hợp hơn.

## 11. Visitor và thao tác trên cây

Khi số loại nút tăng, nhiều thao tác cần xử lý từng loại nút. Mẫu Visitor (Visitor pattern) tách cấu trúc dữ liệu nút khỏi thuật toán thực hiện trên nút.

Ví dụ giao diện visitor giản lược:

~~~java
interface ExprVisitor<R> {
    R visitName(NameExpr node);
    R visitNumber(NumberExpr node);
    R visitString(StringExpr node);
    R visitBinary(BinaryExpr node);
}
~~~

Mỗi nút có thể cung cấp phương thức accept để chuyển quyền xử lý cho visitor phù hợp. Một visitor đánh giá biểu thức có thể trả về giá trị; visitor in cây có thể trả về chuỗi; visitor kiểm tra kiểu có thể trả về kiểu dữ liệu hoặc phát sinh chẩn đoán.

### 11.1. Các tác vụ thường dùng visitor

| Tác vụ | Kết quả |
|---|---|
| Pretty printer | Văn bản DSL được định dạng |
| Type checker | Kiểu dữ liệu và lỗi kiểu |
| Semantic analyzer | Symbol, scope và ràng buộc |
| Interpreter | Giá trị hoặc tác dụng thực thi |
| Code generator | Mã hoặc cấu hình đích |
| Metrics visitor | Số nút, độ sâu, số biểu thức và thống kê |
| Documentation visitor | Tài liệu hoặc mô tả cấu trúc |

Visitor đặc biệt hữu ích khi có nhiều phép xử lý trên cùng một tập loại nút. Nếu DSL còn nhỏ, các hàm đệ quy trực tiếp có thể đơn giản hơn. Khi chọn Visitor, cần cân nhắc rằng thêm loại nút mới có thể yêu cầu cập nhật nhiều visitor.

## 12. Biến đổi cây

Một số giai đoạn cần tạo cây mới từ AST hiện có, ví dụ chuẩn hóa biểu thức, mở rộng cú pháp đường tắt, tối ưu hóa hoặc chuyển đổi sang IR.

### 12.1. Biến đổi cấu trúc

Ví dụ, DSL có thể cho phép biểu thức:

~~~text
amount >= 100
~~~

Một bước chuẩn hóa có thể chuyển nó thành:

~~~text
GreaterThanOrEqual
├── FieldReference("amount")
└── NumberLiteral(100)
~~~

Nếu AST ban đầu đã có đúng cấu trúc đó, bước chuẩn hóa có thể chỉ kiểm tra và giữ nguyên. Với cú pháp rút gọn, transformer có thể mở rộng thành cấu trúc đầy đủ.

### 12.2. Biến đổi hằng số

Một optimizer có thể rút gọn:

~~~text
Add
├── Number(2)
└── Multiply
    ├── Number(3)
    └── Number(4)
~~~

thành:

~~~text
Number(14)
~~~

Phép biến đổi chỉ hợp lệ nếu ngữ nghĩa số học của DSL cho phép tính toán trước, bao gồm quy tắc kiểu, độ chính xác, tràn số và tác dụng phụ. Không được áp dụng phép rút gọn chỉ dựa trên hình dạng cây khi có thể thay đổi hành vi.

### 12.3. Cây bất biến và cây có thể sửa đổi

AST bất biến (immutable) không cho phép thay đổi nút sau khi tạo. Khi biến đổi, công cụ tạo nút mới và tái sử dụng các nhánh không thay đổi. Cách này giúp giảm lỗi do trạng thái bị sửa ở nhiều nơi.

AST có thể sửa đổi (mutable) cho phép thay nút con hoặc thuộc tính trực tiếp. Nó có thể tiện cho một số parser hoặc editor, nhưng cần kiểm soát quyền sở hữu, cache và tính nhất quán khi nhiều thành phần cùng truy cập.

## 13. Cấu trúc cây và bảo toàn nguồn

AST thường bỏ qua một số chi tiết như khoảng trắng, dấu ngoặc không cần thiết và chú thích. Điều này thuận tiện cho phân tích nhưng gây khó khăn nếu muốn viết lại tệp gần giống nguyên bản.

### 13.1. Trivia

Trivia là các thành phần không trực tiếp tham gia ngữ nghĩa nhưng có ý nghĩa với trình bày, chẳng hạn:

- Khoảng trắng.
- Dòng mới.
- Chú thích.
- Một số dấu phân cách tùy chọn.

Một công cụ formatter hoặc refactoring có thể cần giữ trivia. Có thể lưu chúng trong token stream, CST, hoặc gắn metadata vị trí với AST.

### 13.2. Source map

Source map liên kết nút hoặc đoạn mã được sinh với vị trí nguồn gốc. Khi DSL được chuyển thành Java, SQL hoặc cấu hình khác, source map giúp lỗi từ backend có thể được ánh xạ về câu lệnh DSL ban đầu.

Ví dụ, nếu truy vấn SQL được sinh từ nút FilterStatement bị lỗi, công cụ có thể chỉ người dùng đến dòng filter trong tệp DSL thay vì chỉ hiển thị vị trí trong SQL được sinh.

### 13.3. Giữ cây nguồn và cây đã chuẩn hóa

Một kiến trúc có thể giữ hai biểu diễn:

- Cây nguồn giữ cấu trúc và thông tin cần thiết để liên kết với văn bản ban đầu.
- Cây đã chuẩn hóa hoặc IR thể hiện cấu trúc đã được phân tích, đơn giản hóa và sẵn sàng thực thi.

Tách hai cây giúp tránh làm mất thông tin nguồn khi tối ưu hóa. Tuy nhiên, nó làm tăng chi phí bộ nhớ và yêu cầu có cơ chế liên kết node giữa các biểu diễn.

## 14. Lỗi và nút lỗi trong cây

Parser có thể gặp văn bản không hợp lệ nhưng vẫn muốn tiếp tục phân tích để báo nhiều lỗi. Một số công cụ tạo nút lỗi hoặc nút thiếu (error/missing node) để giữ cấu trúc phần còn lại.

Ví dụ nguồn:

~~~text
pipeline "daily" {
    filter status ==
    output "result.csv"
}
~~~

Parser có thể tạo cây gần đúng:

~~~text
Pipeline
├── Name("daily")
├── Filter
│   └── ErrorExpression
└── Output("result.csv")
~~~

ErrorExpression cho biết vị trí biểu thức bị thiếu hoặc không phân tích được. Các giai đoạn sau phải biết cách xử lý nút lỗi: có thể bỏ qua phân tích sâu, tạo chẩn đoán bổ sung hoặc từ chối thực thi.

Không nên để một AST chứa nút lỗi mà runtime không nhận biết. Một chương trình có lỗi cú pháp hoặc ngữ nghĩa không được thực thi như thể nó hoàn toàn hợp lệ.

## 15. Những bất biến cần bảo đảm cho cây

Một mô hình AST đáng tin cậy cần các bất biến rõ ràng:

1. Có một nút gốc cho mỗi đơn vị cú pháp được phân tích.
2. Mỗi nút con có đúng một nút cha trong cây.
3. Không có chu trình trong quan hệ cha-con.
4. Thứ tự nút con được bảo toàn khi thứ tự có ý nghĩa.
5. Loại nút và số lượng con phù hợp với grammar.
6. Thuộc tính bắt buộc không bị thiếu.
7. Nút tham chiếu và symbol được liên kết theo mô hình riêng, không phá vỡ cấu trúc cây.
8. Vị trí nguồn hợp lệ hoặc được đánh dấu rõ là không có.
9. Nút lỗi được nhận diện rõ và không bị coi là nút hợp lệ trong runtime.
10. Các danh sách nút con được quản lý nhất quán, tránh thay đổi ngoài ý muốn.

Các bất biến có thể được kiểm tra trong constructor, factory, validator AST hoặc unit test của parser. Bảo đảm cấu trúc cây hợp lệ sớm sẽ giảm số điều kiện phòng vệ lặp lại trong các visitor và runtime.

## 16. Quy trình xây dựng cây từ DSL

Một quy trình xử lý phổ biến:

1. **Đọc nguồn và tạo token.** Lexer nhận diện từ khóa, tên, literal, toán tử và dấu phân cách.
2. **Phân tích theo grammar.** Parser xác định các cấu trúc khai báo, câu lệnh và biểu thức.
3. **Tạo nút.** Mỗi cấu trúc hợp lệ được chuyển thành loại nút phù hợp.
4. **Liên kết nút con.** Parser hoặc AST builder gắn các nút theo quan hệ cha-con và thứ tự grammar.
5. **Gắn vị trí nguồn.** Lưu source span để hỗ trợ chẩn đoán và công cụ.
6. **Kiểm tra cấu trúc AST.** Bảo đảm nút bắt buộc, số lượng con và loại nút phù hợp.
7. **Phân tích ngữ nghĩa.** Tạo scope, phân giải tên, kiểm tra kiểu và ràng buộc miền.
8. **Tạo liên kết phụ.** Lưu symbol reference, type information hoặc metadata mà không làm sai quan hệ cây.
9. **Chuyển sang IR hoặc thực thi.** Dùng visitor hoặc transformer để tạo kết quả.

Không phải mọi công cụ đều tách riêng từng bước. Một parser nhỏ có thể xây dựng AST và kiểm tra một số ràng buộc cùng lúc. Với DSL lớn, phân tách các giai đoạn giúp dễ kiểm thử, thay đổi grammar và hỗ trợ nhiều backend.

## 17. Những sai lầm thường gặp

### 17.1. Nhầm AST với danh sách token

Token stream giữ thứ tự token nhưng không nhất thiết thể hiện quan hệ ngữ nghĩa giữa chúng. AST phải cho biết toán tử kết hợp với toán hạng nào, câu lệnh thuộc khối nào và khai báo chứa những thành phần gì.

### 17.2. Dùng một loại nút cho mọi cấu trúc

Một nút tổng quát có hàng loạt trường nullable và cờ Boolean có thể biểu diễn nhiều trường hợp, nhưng rất dễ tạo trạng thái không hợp lệ. Các loại nút cụ thể hoặc sealed hierarchy thường làm cấu trúc rõ hơn.

### 17.3. Không giữ thứ tự nút con

Đổi thứ tự câu lệnh hoặc toán hạng có thể làm thay đổi kết quả. Cần dùng cấu trúc dữ liệu bảo toàn thứ tự khi grammar yêu cầu.

### 17.4. Trộn quan hệ tham chiếu vào quan hệ cha-con

Một khai báo có thể được nhiều biểu thức tham chiếu. Nếu dùng cùng một nút làm con của nhiều cha, cấu trúc không còn là cây thông thường. Hãy dùng symbol ID hoặc liên kết phụ cho tham chiếu.

### 17.5. Bỏ vị trí nguồn quá sớm

Nếu không lưu vị trí nguồn, thông báo lỗi ngữ nghĩa, liên kết IDE và ánh xạ lỗi từ backend sẽ khó thực hiện. Hãy xác định nhu cầu bảo toàn nguồn trước khi bỏ thông tin.

### 17.6. Không phân biệt CST và AST

Một cây đầy đủ token có thể cần cho formatter, trong khi AST gọn hơn phù hợp cho runtime. Dùng một cấu trúc cho mọi mục đích có thể làm nó quá phức tạp hoặc mất thông tin cần thiết.

### 17.7. Cho phép cây ở trạng thái không hợp lệ

Nếu một nút bắt buộc có hai con nhưng có thể được tạo với một con, mọi visitor phải xử lý trường hợp thiếu. Nên kiểm tra bất biến ngay khi tạo hoặc ở ranh giới parser.

## 18. Câu hỏi tự kiểm tra

1. Nút trong AST là gì? Nêu những thông tin thường được lưu trên một nút.
2. Phân biệt nút lá và nút trong bằng một cây biểu thức.
3. Giải thích quan hệ cha, con, anh em và tổ tiên.
4. Vì sao thứ tự các nút con có ý nghĩa với phép trừ và danh sách câu lệnh?
5. Phân biệt quan hệ cha-con của AST với quan hệ tham chiếu đến khai báo.
6. CST và AST khác nhau ở mục tiêu và mức độ giữ chi tiết cú pháp như thế nào?
7. Hãy biểu diễn AST cho biểu thức (price - discount) * quantity >= 100.
8. Vì sao AST thường là cây nhiều nhánh thay vì chỉ là cây nhị phân?
9. Source span và source map hỗ trợ chẩn đoán hoặc công cụ IDE ra sao?
10. Visitor có thể được dùng cho những tác vụ nào trên cây?
11. Khi parser gặp biểu thức không hợp lệ, nút lỗi có vai trò gì và runtime cần xử lý nó ra sao?
12. Hãy đề xuất các loại nút và quan hệ cây cho một khai báo DSL thuộc miền bạn biết.
