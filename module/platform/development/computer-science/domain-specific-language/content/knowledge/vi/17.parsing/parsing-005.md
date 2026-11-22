# Parser combinator

**Parser combinator** là kỹ thuật xây dựng bộ phân tích cú pháp (*parser*) bằng cách kết hợp những parser nhỏ hơn thông qua các hàm hoặc toán tử có thể tái sử dụng. Thay vì mô tả toàn bộ grammar trong một tệp đặc tả rồi sinh parser, người phát triển viết các parser cho token hoặc cấu trúc đơn giản, sau đó ghép chúng thành parser cho biểu thức, câu lệnh và toàn bộ chương trình.

Kỹ thuật này thường xuất hiện trong các ngôn ngữ lập trình hàm, nhưng có thể áp dụng trong nhiều ngôn ngữ khác. Nó phù hợp với DSL (*Domain-Specific Language* – ngôn ngữ chuyên biệt theo miền) vì grammar có thể được biểu diễn gần với cấu trúc dữ liệu và quy tắc miền của chính ứng dụng.

Ví dụ, một DSL khai báo dịch vụ có thể có cú pháp:

```text
service "catalog" {
    replicas = 3
    region = "asia-southeast1"
}
```

Ta có thể xây parser cho chuỗi, số, dấu ngoặc, thuộc tính và khai báo dịch vụ riêng rẽ. Parser cấp cao kết hợp các parser đó để nhận diện toàn bộ tệp và tạo AST (*Abstract Syntax Tree* – cây cú pháp trừu tượng).

Parser combinator giúp grammar trở thành mã có cấu trúc, có thể chia sẻ và kiểm thử theo từng phần. Tuy nhiên, người thiết kế vẫn phải quan tâm đến độ ưu tiên toán tử, đệ quy trái, backtracking, lỗi cú pháp và hiệu năng.

## 1. Ý tưởng cốt lõi

Một parser nhận đầu vào và cố gắng nhận diện một cấu trúc cú pháp. Nếu thành công, nó trả về giá trị được phân tích cùng phần đầu vào còn lại. Nếu thất bại, nó trả về thông tin lỗi.

Có thể hình dung một parser tổng quát như một hàm:

```text
Parser<A> : Input -> ParseResult<A>
```

Trong đó:

- `Input` là trạng thái đầu vào, thường gồm văn bản hoặc danh sách token và vị trí hiện tại.
- `A` là kiểu giá trị mà parser tạo ra, ví dụ `Integer`, `Expression`, `Property` hoặc `Program`.
- `ParseResult<A>` mô tả thành công hoặc thất bại, đồng thời mang theo vị trí còn lại và thông tin chẩn đoán.

Ví dụ, parser số nguyên có thể đọc `123` từ đầu vào `123 + 4`, trả về giá trị `123` và để lại phần ` + 4` cho parser tiếp theo.

### 1.1. Parser không nhất thiết chỉ trả về Boolean

Một hàm kiểm tra chuỗi có hợp lệ hay không chỉ trả về đúng/sai. Parser thường làm nhiều hơn:

- Xác định phần đầu vào đã được tiêu thụ.
- Tạo giá trị hoặc node AST.
- Giữ vị trí nguồn để báo lỗi.
- Ghi nhận các token hoặc cấu trúc được mong đợi.
- Cho biết parser có tiêu thụ đầu vào trước khi thất bại hay không.

Thông tin tiêu thụ đầu vào rất quan trọng khi kết hợp parser lựa chọn và backtracking.

### 1.2. Combinator là gì?

Combinator là một hàm nhận parser khác làm đầu vào rồi tạo parser mới. Ví dụ:

- `map(p, f)`: chạy parser `p`, rồi biến đổi giá trị thành công bằng hàm `f`.
- `sequence(p, q)`: chạy `p`, sau đó chạy `q` trên phần đầu vào còn lại.
- `choice(p, q)`: thử một trong hai parser theo chính sách lựa chọn của thư viện.
- `many(p)`: lặp parser `p` không hoặc nhiều lần.
- `optional(p)`: cho phép parser `p` xuất hiện hoặc vắng mặt.

Nhờ các combinator này, parser phức tạp được tạo từ các parser đơn giản mà không cần viết lại logic điều khiển cho từng cấu trúc.

## 2. Mô hình kết quả phân tích

Một mô hình khái niệm của kết quả parser có thể là:

```text
ParseResult<A> =
    Success(value: A, nextInput: Input, consumed: Boolean)
  | Failure(error: ParseError, consumed: Boolean)
```

`consumed` cho biết parser đã tiến qua một phần đầu vào trước khi kết quả được trả về hay chưa. Một số thư viện biểu diễn thông tin này bằng trạng thái riêng, một số dùng vị trí đầu/cuối, một số dùng loại lỗi khác nhau.

Ví dụ cấu trúc dữ liệu bằng Java giả định:

```java
record ParseSuccess<A>(
    A value,
    int nextOffset,
    boolean consumed
) {}

record ParseFailure(
    int errorOffset,
    Set<String> expected,
    boolean consumed
) {}
```

Đây là mô hình minh họa, không phải API chuẩn của mọi thư viện parser combinator.

### 2.1. Parser ký tự đơn giản

Parser nhận một ký tự cụ thể có thể được mô tả như sau:

```text
char('=')
```

Với đầu vào `= 3`, parser thành công, trả về ký tự `=` và chuyển vị trí đọc sang sau dấu bằng.

Với đầu vào `: 3`, parser thất bại tại vị trí đầu vì ký tự mong đợi là `=`.

### 2.2. Parser chuỗi cố định

Parser chuỗi có thể nhận diện một từ khóa hoặc dấu phân cách:

```text
string("service")
```

Parser này kiểm tra đoạn đầu vào có khớp `service` hay không. Một parser từ khóa hoàn chỉnh thường còn kiểm tra ranh giới từ để không nhận `services` thành từ khóa `service` rồi phần `s` còn lại.

### 2.3. Parser token

Nếu lexer đã tạo token, parser combinator có thể hoạt động trên danh sách token thay vì ký tự. Ví dụ:

```text
token(IDENTIFIER)
token(LEFT_BRACE)
token(NUMBER)
```

Tách lexer và parser giúp mỗi thành phần tập trung vào một nhiệm vụ: lexer nhận diện token, parser tổ chức token thành cấu trúc. Một số thư viện parser combinator lại làm việc trực tiếp trên ký tự và kết hợp cả nhận diện từ vựng trong parser.

## 3. Các parser nguyên thủy

Parser nguyên thủy (*primitive parser*) là những parser nhỏ, thường không được xây bằng cách kết hợp parser cùng cấp. Chúng tạo nền tảng cho các combinator.

Những parser nguyên thủy thường gặp:

| Parser | Nhiệm vụ |
|---|---|
| `char(c)` | Nhận diện một ký tự cụ thể |
| `string(s)` | Nhận diện chuỗi cố định |
| `digit` | Nhận diện một chữ số |
| `letter` | Nhận diện một chữ cái |
| `satisfy(predicate)` | Nhận diện ký tự thỏa điều kiện |
| `eof` | Xác nhận đã đến cuối đầu vào |
| `anyChar` | Nhận diện ký tự bất kỳ nếu còn đầu vào |
| `token(type)` | Nhận diện token có loại xác định |

Ví dụ parser chữ số:

```text
digit = satisfy(ch -> '0' <= ch && ch <= '9')
```

Parser số nguyên có thể được xây từ một hoặc nhiều chữ số:

```text
integerText = many1(digit)
integer = map(integerText, digits -> parseInt(digits))
```

`many1` yêu cầu ít nhất một lần khớp. Nếu dùng `many`, chuỗi rỗng cũng có thể được chấp nhận, điều này thường không đúng với literal số nguyên.

## 4. Kết hợp parser theo trình tự

Combinator trình tự (*sequencing*) ghép các parser để chúng chạy lần lượt. Parser sau nhận phần đầu vào còn lại sau khi parser trước thành công.

Giả sử DSL có khai báo:

```text
name = "catalog"
```

Ta có thể mô tả cấu trúc:

```text
identifier, equals, stringLiteral
```

Parser trình tự có thể được viết theo dạng:

```text
propertyParser = sequence(
    identifierParser,
    sequence(equalsParser, stringLiteralParser)
)
```

Kết quả thô có thể chứa tuple hoặc cấu trúc lồng nhau. Dùng `map` để chuyển kết quả thành node `Property`.

### 4.1. `map`

`map` biến đổi giá trị mà parser tạo ra nhưng không thay đổi phần đầu vào mà parser đã tiêu thụ.

Ví dụ:

```text
integerParser = map(
    many1(digit),
    digits -> Integer.parse(digits)
)
```

Parser trước nhận diện chuỗi chữ số; hàm ánh xạ chuyển chuỗi thành số nguyên.

Trong phong cách hàm, biểu diễn thường có dạng:

```text
parser.map(transform)
```

### 4.2. `then` và `skip`

Hai combinator tiện dụng giúp bỏ qua giá trị không cần thiết:

- `then(p, q)` chạy `p`, sau đó chạy `q`, và thường giữ kết quả của `q`.
- `skip(p, q)` chạy `p`, sau đó chạy `q`, và thường giữ kết quả của `p`.

Ví dụ khi đọc dấu ngoặc:

```text
between(leftParen, expressionParser, rightParen)
```

Parser giữ lại AST của biểu thức, còn hai dấu ngoặc chỉ dùng để xác định ranh giới.

Tên và chiều của `then`, `skip`, `precededBy` hoặc `followedBy` có thể khác giữa các thư viện. Cần đọc đúng API cụ thể.

### 4.3. `flatMap` hoặc `bind`

`flatMap` cho phép parser tiếp theo được lựa chọn dựa trên giá trị mà parser trước vừa đọc.

Ví dụ, DSL có cú pháp phụ thuộc loại khai báo:

```text
kind = identifier
body = parserForKind(kind)
```

Parser đọc `kind`, sau đó chọn parser phần thân tương ứng. Đây là sequencing phụ thuộc dữ liệu (*dependent sequencing*).

`flatMap` mạnh hơn `map`: `map` chỉ biến đổi giá trị, còn `flatMap` có thể tạo parser mới dựa trên giá trị đó.

## 5. Lựa chọn giữa các parser

Combinator lựa chọn (*choice* hoặc alternative) thử một trong nhiều cách phân tích.

Giả sử một giá trị DSL có thể là số hoặc chuỗi:

```text
value = 42
value = "hello"
```

Parser có thể được mô tả:

```text
valueParser = choice(integerParser, stringParser)
```

Nếu parser số thành công, nó trả về số. Nếu parser số thất bại theo chính sách của thư viện, parser chuỗi có thể được thử.

### 5.1. Lựa chọn có thứ tự

Nhiều thư viện dùng lựa chọn có thứ tự (*ordered choice*): thử parser bên trái trước, rồi mới đến parser bên phải nếu điều kiện thất bại cho phép.

```text
choice(p, q)
```

không nhất thiết có nghĩa hai parser được thử song song. Thứ tự có thể ảnh hưởng kết quả, đặc biệt khi parser tiêu thụ một phần đầu vào trước khi thất bại.

### 5.2. Thất bại trước và sau khi tiêu thụ đầu vào

Một số thư viện phân biệt:

- **Thất bại không tiêu thụ:** parser thất bại ngay tại vị trí ban đầu; parser thay thế có thể được thử.
- **Thất bại sau khi tiêu thụ:** parser đã đọc một phần đầu vào rồi mới thất bại; thư viện có thể xem đây là lỗi đã cam kết và không thử nhánh khác.

Ví dụ:

```text
choice(string("service"), string("setting"))
```

Với đầu vào `setting`, parser `service` có thể đọc được `s` rồi thất bại ở ký tự tiếp theo. Nếu thư viện coi việc đã tiêu thụ `s` là cam kết, parser `setting` có thể không được thử trừ khi nhánh đầu được cho phép backtrack.

### 5.3. Backtracking

Backtracking là việc quay lại vị trí trước đó để thử một cách phân tích khác sau khi nhánh hiện tại thất bại.

Ví dụ, nếu hai production có tiền tố chung:

```text
declaration = "service" serviceBody
             | "setting" settingBody
```

Parser có thể cần đọc đủ để phân biệt hai từ khóa. Một số thư viện tự backtrack khi alternative thất bại; một số chỉ backtrack khi dùng combinator như `try`, `attempt` hoặc `backtrack`.

Backtracking làm parser linh hoạt nhưng có thể tăng thời gian chạy nếu nhiều nhánh lặp lại việc phân tích cùng đoạn đầu vào.

### 5.4. `try` hoặc `attempt`

Một combinator `try(p)` thường cho phép parser `p` thất bại mà không giữ lại việc tiêu thụ đầu vào, để nhánh thay thế có thể được thử.

Ví dụ khái niệm:

```text
declarationParser = choice(
    try(serviceDeclarationParser),
    settingDeclarationParser
)
```

Tên chính xác và hành vi của `try` tùy thư viện. Có thư viện chỉ hoàn tác vị trí đọc; có thư viện còn điều chỉnh cách gộp lỗi. Không nên đặt `try` bao quanh mọi parser một cách máy móc, vì điều đó có thể làm lỗi cuối cùng kém chính xác và tăng chi phí backtracking.

## 6. Lặp lại và thành phần tùy chọn

DSL thường có danh sách thuộc tính, nhiều câu lệnh hoặc phần cú pháp có thể xuất hiện không hoặc nhiều lần. Parser combinator cung cấp các phép lặp dùng chung.

### 6.1. `many`

`many(p)` nhận diện parser `p` không hoặc nhiều lần và trả về danh sách kết quả.

Ví dụ:

```text
propertiesParser = many(propertyParser)
```

Nó phù hợp với khối có số lượng thuộc tính tùy ý.

### 6.2. `many1`

`many1(p)` yêu cầu ít nhất một kết quả:

```text
argumentsParser = many1(argumentParser)
```

Nếu danh sách đối số phải có ít nhất một phần tử, `many1` thể hiện yêu cầu đó trực tiếp.

### 6.3. `optional`

`optional(p)` cho phép parser `p` xuất hiện hoặc không xuất hiện:

```text
visibilityParser = optional(publicOrPrivateParser)
```

Kết quả có thể được biểu diễn bằng `Option<A>`, `Maybe<A>` hoặc kiểu tương đương.

### 6.4. `sepBy` và `sepBy1`

`sepBy(item, separator)` nhận diện danh sách gồm các phần tử được phân tách bởi separator; danh sách có thể rỗng.

`sepBy1(item, separator)` yêu cầu ít nhất một phần tử.

Ví dụ danh sách trường:

```text
fieldList = sepBy(identifierParser, commaParser)
```

Với đầu vào:

```text
name, age, email
```

parser trả về ba định danh. Nếu DSL cho phép dấu phẩy cuối (*trailing comma*), cần parser riêng hoặc combinator có hỗ trợ trailing separator.

### 6.5. `between`

`between(open, p, close)` nhận diện cấu trúc mở, nội dung và đóng, thường chỉ trả về kết quả của `p`.

Ví dụ:

```text
blockParser = between(
    leftBrace,
    many(statementParser),
    rightBrace
)
```

Parser này mô tả khối `{ ... }` chứa nhiều câu lệnh.

### 6.6. Điều kiện dừng của phép lặp

Một parser được lặp bởi `many` phải có khả năng tiến đầu vào khi thành công. Nếu `p` thành công mà không tiêu thụ ký tự hoặc token nào, `many(p)` có thể lặp vô hạn.

Ví dụ không an toàn về mặt khái niệm:

```text
many(optional(char('x')))
```

`optional` có thể thành công với giá trị rỗng mà không tiêu thụ đầu vào. Khi được lặp, nó có thể luôn thành công tại cùng vị trí.

Một thư viện tốt thường phát hiện trường hợp parser lặp không tiến triển hoặc tài liệu hóa điều kiện này. Người viết parser cần bảo đảm mỗi lần lặp thành công đều tiêu thụ đầu vào.

## 7. Xây dựng biểu thức bằng parser combinator

Biểu thức thường là phần phức tạp nhất của grammar DSL vì có toán tử, độ ưu tiên, tính kết hợp, ngoặc và lời gọi hàm.

Giả sử DSL hỗ trợ:

```text
1 + 2 * 3
(price + tax) * quantity
```

Ta có thể chia grammar thành các tầng:

```ebnf
Expression     = Additive ;
Additive       = Multiplicative, { ("+" | "-"), Multiplicative } ;
Multiplicative = Primary, { ("*" | "/"), Primary } ;
Primary        = Number | Identifier | "(", Expression, ")" ;
```

Parser combinator có thể phản ánh từng tầng bằng một parser riêng.

### 7.1. AST biểu thức

Một mô hình AST đơn giản:

```text
Expression =
    NumberLiteral(value)
  | Name(identifier)
  | Binary(operator, left, right)
  | Group(expression)
```

Parser literal tạo `NumberLiteral`; parser tên tạo `Name`; parser toán tử kết hợp hai biểu thức thành `Binary`.

### 7.2. Parser số và tên

```text
numberParser = map(integerParser, n -> NumberLiteral(n))

nameParser = map(identifierParser, name -> Name(name))
```

Hai parser có cùng kiểu kết quả `Expression`, nên có thể kết hợp bằng `choice`:

```text
atomParser = choice(numberParser, nameParser)
```

### 7.3. Parser biểu thức trong ngoặc

```text
parenthesizedParser = between(
    symbol("("),
    expressionParser,
    symbol(")")
)
```

Parser này tham chiếu lại `expressionParser`. Đây là quan hệ đệ quy cần được khai báo bằng cơ chế lazy hoặc tham chiếu parser có thể khởi tạo muộn trong nhiều thư viện.

### 7.4. Parser phép nhân và chia

```text
multiplicativeParser = chainLeft1(
    atomParser,
    choice(multiplyOperator, divideOperator)
)
```

`chainLeft1` là combinator thường gặp để nhận diện một hoặc nhiều toán hạng nối bởi toán tử nhị phân kết hợp trái. Nó tạo AST theo dạng:

```text
a * b / c
```

thành:

```text
Divide(Multiply(a, b), c)
```

Không phải thư viện nào cũng cung cấp `chainLeft1`; có thể tự xây bằng `many` và một phép gộp từ trái sang phải.

### 7.5. Parser phép cộng và trừ

```text
additiveParser = chainLeft1(
    multiplicativeParser,
    choice(plusOperator, minusOperator)
)
```

Vì toán hạng của tầng cộng là parser nhân, phép nhân được nhóm trước phép cộng. `chainLeft1` đảm bảo các phép cộng/trừ cùng tầng được nhóm trái.

### 7.6. Kết hợp thành parser biểu thức

```text
expressionParser = additiveParser
```

Parser này có thể nhận diện biểu thức có độ ưu tiên và tính kết hợp theo grammar đã thiết kế.

## 8. Kết hợp trái và kết hợp phải

Combinator chuỗi toán tử thường cần xây dựng AST theo tính kết hợp được quy định.

### 8.1. Kết hợp trái với `chainLeft1`

Với:

```text
a - b - c
```

parser kết hợp trái tạo:

```text
Subtract(Subtract(a, b), c)
```

Mã giả:

```text
chainLeft1(term, operator):
    first = term
    rest = many(pair(operator, term))
    return foldLeft(first, rest)
```

Trong đó `foldLeft` cập nhật kết quả lần lượt từ trái sang phải.

### 8.2. Kết hợp phải với `chainRight1`

Với:

```text
a ^ b ^ c
```

parser kết hợp phải tạo:

```text
Power(a, Power(b, c))
```

Mã giả:

```text
chainRight1(term, operator):
    left = term
    if operator is present:
        right = chainRight1(term, operator)
        return combine(left, operator, right)
    return left
```

Với chuỗi dài, cách đệ quy trực tiếp có thể gây tràn stack. Có thể dùng cấu trúc lặp và fold từ phải sang trái để kiểm soát độ sâu.

### 8.3. Toán tử không kết hợp

Nếu DSL không cho phép chuỗi so sánh:

```text
a < b < c
```

parser có thể nhận một toán hạng, tùy chọn một cặp toán tử và toán hạng thứ hai, sau đó yêu cầu không còn toán tử so sánh cùng tầng.

```text
comparisonParser = pair(
    additiveParser,
    optional(pair(compareOperator, additiveParser))
)
```

Nếu còn toán tử so sánh tiếp theo, parser báo lỗi. Nếu DSL muốn hỗ trợ so sánh chuỗi, cần tạo AST và ngữ nghĩa riêng thay vì vô tình dùng `chainLeft1`.

## 9. Đệ quy trong parser combinator

Grammar DSL thường có cấu trúc đệ quy. Một biểu thức có thể chứa biểu thức trong ngoặc; một câu lệnh điều kiện có thể chứa một khối câu lệnh; khối đó lại có thể chứa điều kiện khác.

Ví dụ:

```text
if condition {
    if nestedCondition {
        run()
    }
}
```

Parser cho `if` có thể gọi parser khối; parser khối lại gọi parser câu lệnh; parser câu lệnh có thể gọi lại parser `if`.

### 9.1. Tham chiếu parser đệ quy

Một parser có thể cần tham chiếu đến chính nó trước khi được khởi tạo hoàn chỉnh. Nhiều thư viện cung cấp `defer`, `lazy`, `suspend`, `forwardRef` hoặc một cơ chế tương tự.

Ví dụ giả định:

```text
expressionParser = defer(() -> choice(
    numberParser,
    parenthesizedExpressionParser
))
```

`defer` trì hoãn việc lấy parser cho đến khi thực sự chạy, nhờ đó có thể xây quan hệ đệ quy mà không truy cập biến chưa khởi tạo.

### 9.2. Đệ quy trái

Một grammar có đệ quy trái nếu một nonterminal có thể bắt đầu bằng chính nó:

```ebnf
Expression = Expression, "+", Term | Term ;
```

Một parser recursive descent hoặc parser combinator thông thường có thể gọi lại chính nó ở cùng vị trí vô hạn, gây tràn stack hoặc lặp không dừng.

### 9.3. Biến đổi đệ quy trái

Grammar trên có thể được viết lại thành:

```ebnf
Expression = Term, { "+", Term } ;
```

Sau đó dùng `chainLeft1` hoặc `foldLeft` để tạo AST kết hợp trái. Đây là cách phổ biến để xây parser biểu thức với parser combinator truyền thống.

### 9.4. Parser có hỗ trợ left recursion

Một số framework parsing hiện đại có cơ chế xử lý đệ quy trái bằng memoization, seed growing hoặc thuật toán parsing chuyên biệt. Tuy nhiên, khả năng này không có trong mọi thư viện parser combinator. Cần kiểm tra đặc tính của framework thay vì giả định có thể viết grammar đệ quy trái trực tiếp.

## 10. Xử lý khoảng trắng và comment

DSL thường cho phép khoảng trắng giữa các token. Có thể tạo combinator dùng chung để bỏ qua khoảng trắng trước hoặc sau parser.

Ví dụ:

```text
spaces = many(satisfy(isWhitespace))
lexeme(p) = p.skip(spaces)
symbol(s) = lexeme(string(s))
```

Sau đó, parser dấu ngoặc hoặc dấu bằng có thể dùng `symbol` để tự bỏ qua khoảng trắng theo quy ước.

```text
equals = symbol("=")
leftBrace = symbol("{")
rightBrace = symbol("}")
```

### 10.1. Phân biệt khoảng trắng và khoảng trắng có ý nghĩa

Không phải DSL nào cũng bỏ qua mọi khoảng trắng. Một DSL nhạy thụt lề có thể dùng newline và mức indent để tạo cấu trúc. Khi đó, lexer hoặc parser phải giữ lại token layout thay vì loại bỏ chúng.

### 10.2. Comment

Comment có thể được xử lý ở lexer hoặc bằng parser combinator riêng. Nếu comment không có ý nghĩa ngữ nghĩa, parser có thể bỏ qua chúng cùng khoảng trắng. Nếu công cụ cần giữ comment để formatter hoặc tài liệu, cần lưu chúng dưới dạng trivia hoặc metadata.

### 10.3. Tránh lặp logic khoảng trắng

Combinator `lexeme` hoặc `token` giúp các parser con áp dụng cùng chính sách khoảng trắng. Nếu mỗi parser tự xử lý dấu cách, grammar dễ không nhất quán: chỗ cho phép khoảng trắng, chỗ khác lại từ chối cùng một cách viết.

## 11. Thông báo lỗi và nhãn parser

Parser combinator có thể tạo lỗi khá chi tiết nếu giữ lại vị trí thất bại và các thành phần được mong đợi.

Ví dụ DSL:

```text
service "catalog" {
    replicas =
}
```

Parser thuộc tính đã nhận diện tên, dấu bằng, nhưng parser giá trị thất bại tại `}`. Thông báo hữu ích có thể là:

```text
config.dsl:2:15: expected a number or string value before '}'
```

### 11.1. Tập hợp các kỳ vọng

Nếu parser lựa chọn nhiều nhánh cùng thất bại tại một vị trí, thư viện có thể hợp nhất các kỳ vọng:

```text
expected one of: identifier, number, string
```

Thông tin này tốt hơn lỗi chung chung “parse failed”.

### 11.2. `label` hoặc `<?>`

Một số thư viện cung cấp combinator đặt nhãn cho parser:

```text
integerParser = digit.many1().label("integer")
```

Nếu parser thất bại, thông báo có thể nói “expected integer” thay vì liệt kê nhiều chi tiết nội bộ khó hiểu.

Nhãn nên được đặt ở ranh giới khái niệm hữu ích. Nếu đặt quá nhiều nhãn tổng quát, thông tin chính xác về token hoặc vị trí có thể bị che mất.

### 11.3. Vị trí lỗi xa nhất

Khi nhiều nhánh được thử, parser thường ghi nhận vị trí xa nhất mà một nhánh thất bại. Đây có thể là vị trí hữu ích nhất để báo lỗi vì parser đã nhận diện được nhiều cấu trúc trước đó.

Tuy nhiên, vị trí xa nhất không luôn là thông báo tốt nhất. Nếu một nhánh không phù hợp đã đọc rất xa trước khi thất bại, nó có thể che lỗi thực sự của nhánh đúng. Backtracking và nhãn lỗi cần được thiết kế để tránh tình huống này.

## 12. Phục hồi lỗi

Một parser đơn giản có thể dừng ở lỗi đầu tiên. Với IDE hoặc công cụ kiểm tra cấu hình, việc tiếp tục phân tích để phát hiện nhiều lỗi trong một lần chạy có thể hữu ích.

Parser combinator có thể được kết hợp với chiến lược phục hồi:

- Đồng bộ tại dấu `;`, `}` hoặc newline.
- Bỏ qua token đến khi gặp từ khóa mở khai báo tiếp theo.
- Tạo node lỗi (*error node*) để giữ cấu trúc AST một phần.
- Ghi nhận diagnostic và tiếp tục parser ở ranh giới an toàn.

Ví dụ, nếu một thuộc tính bị lỗi trong khối dịch vụ, parser có thể bỏ qua đến cuối dòng hoặc dấu phân cách tiếp theo rồi tiếp tục đọc thuộc tính sau.

Phục hồi cần tránh tạo ra quá nhiều lỗi dây chuyền. Một lỗi cú pháp đầu tiên có thể khiến parser hiểu sai phần còn lại; vì vậy, điểm đồng bộ phải phù hợp với grammar.

## 13. Xây dựng parser cho DSL dịch vụ

Xét DSL:

```text
service "catalog" {
    replicas = 3
    region = "asia-southeast1"
}
```

Ta có thể chia thành các parser nhỏ.

### 13.1. Mô hình AST

```text
Program
└── ServiceDeclaration
    ├── name: String
    └── properties: List<Property>

Property
├── name: Identifier
└── value: Value

Value = Number | String | Boolean
```

### 13.2. Parser literal

```text
numberValue = map(integerParser, NumberValue)
stringValue = map(stringLiteralParser, StringValue)
booleanValue = map(
    choice(string("true"), string("false")),
    parseBoolean
)

valueParser = choice(
    numberValue,
    stringValue,
    booleanValue
)
```

Các parser nhánh phải có chính sách lựa chọn phù hợp. Nếu một parser tiêu thụ đầu vào rồi thất bại, nhánh tiếp theo có được thử hay không phụ thuộc combinator và thư viện.

### 13.3. Parser thuộc tính

```text
propertyParser = map(
    sequence(
        identifierParser,
        sequence(symbol("="), valueParser)
    ),
    result -> Property(result.name, result.value)
)
```

Trong mã thực tế, nên dùng record hoặc kiểu dữ liệu có tên thay vì tuple lồng nhau quá sâu để dễ đọc.

### 13.4. Parser khối

```text
propertiesParser = sepBy(propertyParser, newline)

blockParser = between(
    symbol("{"),
    propertiesParser,
    symbol("}")
)
```

Nếu DSL cho phép dấu phẩy hoặc dấu chấm phẩy phân tách thuộc tính, parser separator cần dùng đúng token đó. Nếu newline chỉ là khoảng trắng, cần parser khác để xác định ranh giới khai báo.

### 13.5. Parser khai báo dịch vụ

```text
serviceParser = map(
    sequence(
        keyword("service"),
        sequence(stringLiteralParser, blockParser)
    ),
    result -> ServiceDeclaration(result.name, result.properties)
)
```

### 13.6. Parser chương trình và EOF

```text
programParser = spaces.then(
    many(serviceParser).skip(spaces).skip(eof)
)
```

`eof` rất quan trọng: nếu không yêu cầu đến cuối đầu vào, parser có thể chấp nhận một phần chương trình rồi bỏ qua nội dung dư mà người dùng không biết.

Ví dụ:

```text
service "catalog" { replicas = 3 }
garbage
```

Nếu parser không kiểm tra EOF, nó có thể báo thành công sau khai báo dịch vụ đầu tiên và bỏ qua `garbage`. Với parser chương trình hoàn chỉnh, thường cần xác nhận toàn bộ đầu vào đã được tiêu thụ.

## 14. Parser combinator so với parser generator

Parser combinator và parser generator đều giúp xây parser, nhưng có cách tổ chức khác nhau.

| Tiêu chí | Parser combinator | Parser generator |
|---|---|---|
| Cách mô tả | Viết grammar bằng cách kết hợp parser trong mã | Viết grammar bằng ngôn ngữ đặc tả rồi sinh mã |
| Tích hợp với ngôn ngữ chủ | Trực tiếp, thường dùng kiểu và hàm của host language | Cần bước sinh mã hoặc tích hợp runtime |
| Tính tái sử dụng | Combinator có thể dùng lại như hàm/thư viện | Có thể dùng lại production hoặc grammar module tùy công cụ |
| Kiểm soát | Linh hoạt trong cách xử lý từng parser | Phụ thuộc khả năng và cấu hình của generator |
| Backtracking | Có thể là đặc điểm cốt lõi của thư viện | Tùy thuật toán và loại parser được sinh |
| Lỗi | Có thể tùy chỉnh qua combinator và kiểu lỗi | Phụ thuộc generator, có thể cần tùy biến |
| Hiệu năng | Phụ thuộc thiết kế, backtracking và memoization | Có thể rất tốt với LL/LR hoặc parser sinh chuyên biệt |
| Phù hợp | Grammar vừa/nhỏ, tích hợp sâu với host code, cần logic động | Grammar lớn, cần đặc tả tách biệt hoặc parser chuẩn hóa |

Không có lựa chọn tốt nhất cho mọi dự án. Một DSL nhỏ nằm trong ứng dụng Kotlin hoặc Scala có thể tận dụng parser combinator. Một ngôn ngữ lớn có grammar công khai, nhiều công cụ và yêu cầu parser hiệu năng cao có thể phù hợp với parser generator.

## 15. Ưu điểm của parser combinator

### 15.1. Grammar gần với mã chương trình

Parser được viết bằng chính ngôn ngữ chủ, nên có thể dùng kiểu dữ liệu, hàm, module và abstraction sẵn có.

### 15.2. Tái sử dụng parser nhỏ

Parser cho identifier, string, number, separator hoặc block có thể được dùng trong nhiều production.

### 15.3. Dễ kết hợp với AST và kiểu dữ liệu

Parser có thể trực tiếp tạo các kiểu dữ liệu của ứng dụng. `map` và `flatMap` giúp chuyển từ cú pháp sang cấu trúc miền.

### 15.4. Có thể xây grammar động

Vì parser là giá trị trong chương trình, có thể chọn parser dựa trên cấu hình hoặc dữ liệu đã đọc. Điều này hữu ích với DSL có cú pháp phụ thuộc schema hoặc plugin.

### 15.5. Kiểm thử theo thành phần

Có thể kiểm thử parser số, parser tên, parser biểu thức và parser khai báo độc lập. Khi một cấu trúc thất bại, phạm vi cần tìm nguyên nhân thường nhỏ hơn.

## 16. Hạn chế và rủi ro

### 16.1. Backtracking tốn chi phí

Nếu nhiều nhánh có tiền tố chung và parser liên tục quay lại, cùng một đoạn đầu vào có thể bị phân tích nhiều lần. Trường hợp xấu có thể làm thời gian chạy tăng mạnh.

### 16.2. Grammar có thể khó nhìn tổng thể

Grammar được phân tán qua nhiều hàm và module. Người đọc có thể khó thấy toàn bộ cấu trúc ngôn ngữ như khi đọc một tệp EBNF.

### 16.3. Đệ quy trái

Parser combinator truyền thống thường không xử lý trực tiếp đệ quy trái. Grammar cần được viết lại hoặc dùng framework có hỗ trợ chuyên biệt.

### 16.4. Thông báo lỗi có thể khó kiểm soát

Nhiều nhánh alternative và backtracking có thể tạo tập lỗi lớn hoặc thông báo không đúng trọng tâm. Cần dùng label, cut/commit hoặc điểm đồng bộ hợp lý nếu thư viện hỗ trợ.

### 16.5. Hiệu năng phụ thuộc cấu trúc parser

Một grammar viết ngắn không đảm bảo parser chạy nhanh. Các nhánh có tiền tố chung, phép lặp không tiến triển hoặc backtracking sâu có thể gây vấn đề.

## 17. Hiệu năng và chiến lược tối ưu

Khi parser được dùng trong IDE hoặc xử lý tệp lớn, hiệu năng có thể trở thành yêu cầu quan trọng.

### 17.1. Giảm backtracking không cần thiết

Nếu có thể phân biệt nhánh sớm bằng một token hoặc từ khóa, hãy dùng parser đó trước hoặc tổ chức grammar để không phải thử nhiều nhánh dài.

Ví dụ:

```text
statement = choice(
    keyword("if").then(ifStatementBody),
    keyword("service").then(serviceBody),
    assignmentParser
)
```

Các tiền tố phân biệt rõ giúp parser tránh thử nhánh không liên quan. Nếu thư viện hỗ trợ `cut` hoặc `commit`, có thể dùng sau khi đã nhận diện một từ khóa chắc chắn để báo lỗi bên trong production thay vì quay sang nhánh khác.

### 17.2. Memoization

Memoization lưu kết quả parser tại một vị trí để khi parser được gọi lại với cùng trạng thái, công cụ có thể tái sử dụng kết quả. Đây là kỹ thuật của một số parser và framework, không phải tính năng bắt buộc của mọi parser combinator.

Packrat parsing là một chiến lược dùng memoization để tránh phân tích lặp lại theo vị trí và nonterminal, thường đạt thời gian tuyến tính với một số điều kiện về grammar và cách triển khai, đổi lại dùng thêm bộ nhớ.

### 17.3. Tránh lặp parser không tiến triển

Trong `many(p)`, mỗi lần `p` thành công cần tiêu thụ đầu vào. Nếu không, parser có thể lặp vô hạn. Một thư viện có thể phát hiện và báo lỗi cấu hình, nhưng người viết vẫn cần hiểu điều kiện này.

### 17.4. Tách lexer khi phù hợp

Nếu DSL có nhiều token phức tạp, có thể dùng lexer riêng rồi để parser combinator xử lý token. Điều này giảm trách nhiệm của parser và giúp tái sử dụng lexer giữa compiler, formatter và IDE.

## 18. Kiểm thử parser combinator

Parser combinator cho phép kiểm thử ở nhiều cấp độ.

### 18.1. Kiểm thử parser nguyên thủy

Kiểm tra:

- `digit` nhận chữ số và từ chối chữ cái.
- `string("service")` nhận đúng chuỗi.
- `eof` chỉ thành công khi không còn đầu vào.
- `identifier` tuân theo quy tắc ký tự của DSL.

### 18.2. Kiểm thử combinator

Kiểm tra:

- `sequence` tiêu thụ đầu vào theo đúng thứ tự.
- `choice` thử nhánh thay thế đúng theo chính sách backtracking.
- `many` và `many1` xử lý số lượng phần tử đúng.
- `optional` không tiêu thụ đầu vào khi thành phần vắng mặt.
- `sepBy` xử lý danh sách rỗng, một phần tử và nhiều phần tử.
- `between` yêu cầu đủ dấu mở và dấu đóng.

### 18.3. Kiểm thử AST

Không chỉ kiểm tra parser có thành công. Cần kiểm tra cấu trúc AST để bảo đảm precedence và associativity đúng.

Ví dụ:

```text
1 + 2 * 3
```

phải tạo cây tương đương:

```text
Add(
    Number(1),
    Multiply(Number(2), Number(3))
)
```

### 18.4. Kiểm thử đầu vào sai

Các trường hợp nên có:

- Thiếu dấu đóng ngoặc hoặc dấu đóng khối.
- Giá trị bị thiếu sau dấu `=`.
- Token không hợp lệ.
- Chuỗi chưa đóng.
- Danh sách có separator thừa nếu không được phép.
- Nội dung dư sau chương trình hoàn chỉnh.
- Biểu thức đệ quy sâu hoặc đầu vào lớn.

### 18.5. Kiểm thử lỗi và vị trí nguồn

Đảm bảo lỗi chỉ đúng vị trí và nêu thành phần được mong đợi. Nếu parser backtrack, thông tin vị trí lỗi cuối cùng cần phản ánh nhánh phù hợp nhất, không chỉ là lỗi của một nhánh đã bị loại bỏ.

## 19. Những sai lầm thường gặp

**Nhầm parser combinator với một loại grammar.** Đây là kỹ thuật xây dựng parser bằng cách kết hợp parser nhỏ; grammar vẫn mô tả cấu trúc ngôn ngữ mà parser phải nhận diện.

**Dùng `many` với parser có thể thành công mà không tiêu thụ đầu vào.** Điều này có thể tạo vòng lặp vô hạn.

**Giả định mọi `choice` đều backtrack toàn phần.** Nhiều thư viện phân biệt lỗi trước và sau khi tiêu thụ đầu vào; cần hiểu semantics của alternative và `try`.

**Đặt `try` ở mọi nơi.** Backtracking quá rộng có thể làm hiệu năng giảm và thông báo lỗi kém chính xác.

**Viết grammar đệ quy trái trực tiếp.** Parser combinator recursive descent thông thường có thể đệ quy vô hạn; cần biến đổi grammar hoặc dùng cơ chế hỗ trợ.

**Quên kiểm tra EOF.** Parser có thể chấp nhận một tiền tố hợp lệ rồi bỏ qua phần đầu vào còn lại.

**Không kiểm tra AST.** Parser thành công chưa đủ; cần bảo đảm cấu trúc cây đúng với precedence và associativity của DSL.

**Để grammar phân tán khó hiểu.** Nên chia parser theo production, đặt tên theo khái niệm miền và tổ chức module để người đọc có thể lần theo cấu trúc.

## 20. Ghi nhớ

- Parser combinator xây parser lớn bằng cách kết hợp parser nhỏ qua các hàm hoặc toán tử.
- Parser thường nhận đầu vào và trả về giá trị, vị trí tiếp theo hoặc thông tin lỗi.
- Parser nguyên thủy nhận diện ký tự, chuỗi, token hoặc điều kiện cơ bản.
- `map`, `flatMap`, sequencing và choice là những thành phần nền tảng.
- `many`, `many1`, `optional`, `sepBy` và `between` giúp mô tả lặp, tùy chọn, danh sách và khối.
- Backtracking cho phép thử nhánh khác nhưng có thể làm tăng chi phí; semantics của `try` và alternative tùy thư viện.
- `chainLeft1` và `chainRight1` có thể hỗ trợ xây biểu thức theo tính kết hợp tương ứng.
- Đệ quy trái thường cần được biến đổi hoặc dùng framework có hỗ trợ riêng.
- Parser nên giữ vị trí nguồn, thông báo lỗi hữu ích và kiểm tra EOF cho chương trình hoàn chỉnh.
- Parser combinator phù hợp khi cần tích hợp parser với kiểu dữ liệu và logic của ngôn ngữ chủ, nhưng cần quản lý hiệu năng và độ rõ ràng của grammar.

## 21. Câu hỏi tự kiểm tra

1. Parser combinator là gì và khác cách dùng parser generator ở điểm nào?
2. Một parser thường nhận đầu vào và trả về những thông tin nào?
3. `map` khác `flatMap` như thế nào khi xây dựng parser?
4. `sequence` và `choice` giải quyết hai nhu cầu nào?
5. Vì sao một số thư viện phân biệt thất bại trước và sau khi tiêu thụ đầu vào?
6. Backtracking là gì? `try` hoặc `attempt` thường được dùng để làm gì?
7. Phân biệt `many`, `many1`, `optional`, `sepBy` và `sepBy1`.
8. Vì sao parser đặt trong `many` phải tiêu thụ đầu vào khi thành công?
9. `chainLeft1` có thể tạo AST cho `a - b - c` như thế nào?
10. Vì sao đệ quy trái có thể gây lặp vô hạn trong parser combinator truyền thống?
11. `eof` giúp phát hiện loại lỗi nào?
12. Hãy phác thảo các parser cần kết hợp để đọc khai báo `service "catalog" { replicas = 3 }`.
13. Khi nào nên tách lexer riêng trước parser combinator?
14. Những yếu tố nào có thể làm parser combinator chạy chậm và cách giảm chi phí backtracking?
