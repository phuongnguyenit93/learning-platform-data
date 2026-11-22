# Framework Parser Combinator cho DSL

## Mục tiêu học tập

Sau bài học này, người học có thể:

- Giải thích parser combinator và cách xây parser từ những thành phần nhỏ có thể kết hợp.
- Phân biệt parser combinator với parser sinh từ grammar generator và parser viết thủ công.
- Hiểu mô hình parser như một phép biến đổi trên input, kết quả và trạng thái đọc.
- Sử dụng primitive parser và các combinator như sequence, choice, map, bind, many, optional và separated list.
- Thiết kế parser cho biểu thức, câu lệnh, block và cấu trúc lồng nhau của DSL.
- Xử lý precedence, associativity, left recursion và backtracking.
- Tạo AST có kiểu, source span và diagnostic hữu ích.
- Tổ chức parser framework thành các module có thể tái sử dụng trong workbench.
- Kiểm thử parser với input hợp lệ, input sai, trường hợp biên và dữ liệu ngẫu nhiên.

## 1. Parser combinator là gì?

Parser combinator là một kỹ thuật xây dựng bộ phân tích cú pháp bằng cách kết hợp các parser nhỏ thành parser lớn hơn. Mỗi parser nhận một phần input, cố gắng nhận diện một cấu trúc và trả về kết quả cùng vị trí đọc tiếp theo. Các hàm kết hợp (combinator) cho phép nối parser, chọn giữa các parser, lặp parser hoặc biến đổi kết quả.

Thay vì mô tả toàn bộ grammar trong một tệp đặc tả riêng rồi dùng công cụ sinh parser, lập trình viên có thể viết grammar bằng chính ngôn ngữ lập trình chủ. Một parser cho số nguyên có thể được kết hợp với parser cho dấu cộng và parser cho biểu thức để tạo parser số học.

Ví dụ DSL:

~~~text
let total = quantity * unitPrice + shippingFee
~~~

Có thể xây parser theo các lớp:

- Parser nhận diện từ khóa let.
- Parser nhận diện tên biến.
- Parser nhận diện dấu gán.
- Parser nhận diện biểu thức.
- Parser kết hợp các phần trên thành một khai báo biến.

Mỗi thành phần có thể được kiểm thử độc lập và tái sử dụng trong nhiều rule khác nhau.

Parser combinator đặc biệt hữu ích khi DSL cần grammar có thể cấu hình, grammar phụ thuộc ngữ cảnh, cú pháp mở rộng theo plugin hoặc workbench cần cung cấp parser cho nhiều loại tài liệu. Nó cũng phù hợp với các DSL nhỏ và vừa mà grammar có thể được mô tả rõ bằng code.

## 2. Ý tưởng cốt lõi: parser là một giá trị có thể kết hợp

Một parser có thể được xem là một hàm nhận input và trả về một trong hai kết quả:

- Thành công: giá trị đã phân tích và vị trí tiếp tục.
- Thất bại: thông tin lỗi và vị trí xảy ra lỗi.

Mô hình đơn giản:

~~~text
Parser<T> : Input -> ParseResult<T>

ParseResult<T> =
    Success(value: T, nextPosition)
  | Failure(error, position)
~~~

Trong thực tế, parser còn có thể giữ trạng thái lexer, source span, thông tin backtracking, mức độ đã tiêu thụ input và danh sách diagnostic.

Ví dụ, parser số nguyên nhận input:

~~~text
"123 + 4"
~~~

Nó trả về giá trị 123 và vị trí ngay sau ký tự 3. Parser tiếp theo có thể bắt đầu từ dấu cách hoặc dấu cộng tùy cách lexer xử lý whitespace.

### 2.1. Parser không nhất thiết phải tạo AST ngay

Một parser có thể trả về giá trị literal, token, AST node, cấu trúc dữ liệu trung gian hoặc kết quả validation cú pháp. Với compiler DSL, kết quả thường là AST có kiểu. Với editor, parser có thể tạo syntax tree giữ token và source trivia. Với parser cấu hình, nó có thể trả về object cấu hình trực tiếp.

### 2.2. Combinator là hàm nhận parser và trả parser

Ví dụ khái niệm:

~~~text
map(parser, transform)
sequence(parserA, parserB)
choice(parserA, parserB)
many(parser)
optional(parser)
~~~

Các combinator này tạo parser mới. Parser mới vẫn có cùng giao diện, nên có thể tiếp tục kết hợp với những parser khác.

### 2.3. Tính thành phần

Một parser cho biểu thức không cần biết cách parser đọc tên biến hoạt động ra sao. Nó chỉ sử dụng parser tên biến đã có. Điều này tạo ra sự phân tách rõ giữa các quy tắc từ vựng, cú pháp và ngữ nghĩa.

## 3. Parser combinator và các cách xây parser khác

Có nhiều phương pháp triển khai parser. Không có một phương pháp tốt nhất cho mọi DSL.

| Cách xây dựng | Cách mô tả grammar | Ưu điểm | Hạn chế thường gặp |
|---|---|---|---|
| Parser combinator | Hàm và combinator trong code | Thành phần nhỏ, tái sử dụng, dễ cấu hình | Có thể khó đọc khi grammar lớn và lồng sâu |
| Parser generator | Grammar khai báo, công cụ sinh code | Grammar tập trung, phân tích tĩnh tốt | Cần bước sinh code và quản lý toolchain |
| Recursive descent thủ công | Hàm cho từng quy tắc | Dễ kiểm soát và debug | Có thể lặp code nếu không trừu tượng hóa |
| Pratt parser | Hàm xử lý biểu thức theo binding power | Rất phù hợp cho expression grammar | Cần tự tổ chức phần grammar còn lại |
| PEG parser | Grammar theo thứ tự ưu tiên | Hỗ trợ ordered choice và lookahead | Backtracking và thứ tự rule cần được hiểu rõ |
| GLR/Earley/LR | Thuật toán parser tổng quát | Xử lý grammar phức tạp | Cấu hình và runtime có thể phức tạp hơn |

Parser combinator thường tạo ra parser kiểu recursive descent hoặc parser theo phong cách PEG. Cách hoạt động cụ thể phụ thuộc thư viện: một số thư viện backtracking tự động, một số yêu cầu đánh dấu điểm thử, một số hỗ trợ parser incremental.

### 3.1. Khi nên dùng parser combinator

Phù hợp khi grammar được xây từ nhiều thành phần có thể tái sử dụng, cú pháp mở rộng theo plugin hoặc cấu hình, muốn kiểm thử từng parser nhỏ, cần tích hợp trực tiếp với type system của ngôn ngữ chủ, hoặc DSL có nhiều cú pháp lồng nhau nhưng vẫn có cấu trúc tương đối rõ.

### 3.2. Khi cần cân nhắc phương pháp khác

Nếu grammar rất lớn, có nhiều xung đột, yêu cầu phân tích lỗi mạnh hoặc cần toolchain chuẩn hóa, parser generator có thể phù hợp hơn. Nếu DSL chủ yếu là biểu thức với toán tử tùy chỉnh, Pratt parser có thể đơn giản hơn việc dùng combinator tổng quát cho mọi tầng.

## 4. Primitive parser

Primitive parser là những parser cơ bản nhất, thường được framework cung cấp sẵn. Các parser lớn được xây từ chúng.

### 4.1. Nhận diện một ký tự

Một parser có thể nhận đúng một ký tự thỏa điều kiện:

~~~text
char('+')
satisfy(isDigit)
anyCharacter
~~~

Ví dụ, satisfy(isDigit) nhận một chữ số ở vị trí hiện tại. Nếu ký tự tiếp theo không phải chữ số, parser thất bại.

### 4.2. Nhận diện chuỗi cố định

Parser literal nhận một chuỗi chính xác:

~~~text
string("rule")
string("when")
string("then")
~~~

Cần xác định keyword boundary. Nếu parser string("if") chấp nhận đầu của identifier "ifdef", lexer hoặc parser cần kiểm tra ký tự tiếp theo để xác nhận đây là từ khóa độc lập.

### 4.3. End of input

Parser EOF xác nhận không còn input chưa được xử lý:

~~~text
document = sequence(program, eof)
~~~

Nếu không có EOF check, parser có thể chấp nhận một chương trình hợp lệ ở đầu file rồi bỏ qua phần rác ở cuối.

### 4.4. Parser thất bại có thông tin

Một primitive parser tốt nên trả lỗi có vị trí mong đợi, token hoặc ký tự thực tế, loại parser thất bại, mức độ đã tiêu thụ input và thông tin context nếu có. Thông tin này giúp combinator phía trên tổng hợp diagnostic tốt hơn.

## 5. Sequence: kết hợp parser theo thứ tự

Sequence chạy nhiều parser nối tiếp nhau. Tất cả thành phần phải thành công theo đúng thứ tự.

Ví dụ grammar khai báo biến:

~~~text
variableDeclaration =
    sequence(
        keyword("let"),
        identifier,
        symbol("="),
        expression
    )
~~~

Parser trên nhận cấu trúc:

~~~text
let total = quantity * price
~~~

Nếu một parser con thất bại, sequence thất bại và cung cấp thông tin về vị trí lỗi.

### 5.1. Giữ kết quả của từng phần

Một sequence có thể trả tuple:

~~~text
(keywordToken, name, equalsToken, value)
~~~

Nhưng AST thường không cần giữ keywordToken và equalsToken như các giá trị semantic. Dùng map để tạo node:

~~~text
map(
    sequence(keyword("let"), identifier, symbol("="), expression),
    (_, name, _, value) => VariableDeclaration(name, value)
)
~~~

### 5.2. Sequence với nhiều thành phần

Một block có thể được mô tả:

~~~text
block =
    sequence(
        symbol("{"),
        many(statement),
        symbol("}")
    )
~~~

Whitespace và comment có thể được xử lý ở lớp token hoặc bằng parser lexeme combinator bao quanh các parser terminal.

### 5.3. Sequence không đồng nghĩa với chuỗi ký tự liền nhau

Nếu grammar cho phép whitespace giữa token, parser cần tự xử lý whitespace hoặc sử dụng parser token đã bỏ qua trivia. Không nên giả định sequence sẽ tự bỏ khoảng trắng nếu framework không quy định như vậy.

## 6. Choice: chọn một trong nhiều parser

Choice thử các parser thay thế. Một parser thành công sẽ tạo kết quả; nếu parser đầu thất bại, framework có thể thử parser tiếp theo tùy chính sách backtracking.

Ví dụ một statement có thể là khai báo, gán hoặc expression statement:

~~~text
statement =
    choice(
        variableDeclaration,
        assignment,
        expressionStatement
    )
~~~

### 6.1. Thứ tự choice

Với ordered choice, thứ tự parser có ý nghĩa. Parser đầu có thể nhận input trước parser sau. Nếu parser đầu chấp nhận một prefix quá rộng, nhánh sau có thể không được thử.

Ví dụ, nếu identifier parser chạy trước keyword parser mà không có bước phân loại keyword, từ khóa có thể bị nhận thành định danh.

### 6.2. Backtracking

Giả sử parser A đọc một phần input rồi thất bại. Framework có thể không thử parser B nếu A đã tiêu thụ input, quay lại vị trí ban đầu và thử B, chỉ backtrack khi A được bọc trong try/attempt, hoặc dùng lookahead để quyết định nhánh trước khi tiêu thụ.

Chính sách phải rõ vì nó ảnh hưởng cả tính đúng đắn và hiệu năng.

### 6.3. Phân biệt lỗi có tiêu thụ và lỗi không tiêu thụ

Nhiều framework phân biệt:

- Empty failure: parser thất bại mà chưa tiêu thụ input.
- Consumed failure: parser đã tiêu thụ một phần rồi mới thất bại.

Choice thường thử nhánh kế tiếp sau empty failure. Consumed failure có thể được coi là lỗi nghiêm trọng hơn vì parser đã xác định một nhánh và đi sâu vào cấu trúc đó.

### 6.4. Tránh choice mơ hồ

Nếu nhiều nhánh có prefix giống nhau, cần thiết kế lookahead hoặc phân biệt token đầu. Nếu không, parser có thể backtrack nhiều lần và tạo diagnostic khó hiểu.

## 7. Mapping và biến đổi kết quả parser

Parser thường trả dữ liệu trung gian. Combinator map biến đổi giá trị đó thành node hoặc kiểu dữ liệu mong muốn.

Ví dụ:

~~~text
integer =
    map(digits, parseInteger)

identifier =
    map(identifierCharacters, makeIdentifier)

variableDeclaration =
    map(
        sequence(keyword("let"), identifier, symbol("="), expression),
        (_, name, _, value) => VariableDeclaration(name, value)
    )
~~~

### 7.1. Map không thay đổi cách parser đọc input

map chỉ biến đổi kết quả sau khi parser con thành công. Nó không nên tự tiêu thụ thêm input hoặc thay đổi vị trí đọc.

### 7.2. Bind hoặc flatMap

Một số parser cần lựa chọn parser tiếp theo dựa trên kết quả vừa đọc. Bind/flatMap hỗ trợ tình huống này.

Ví dụ, kiểu literal có thể quyết định parser phần giá trị:

~~~text
typedValue =
    bind(typeName, type =>
        parserForType(type)
    )
~~~

Cách này hữu ích với cú pháp phụ thuộc type hoặc directive đã khai báo. Tuy nhiên, parser phụ thuộc dữ liệu có thể làm grammar khó phân tích tĩnh hơn.

### 7.3. Applicative và monadic style

Sequence và map thường đủ để mô tả nhiều grammar. Bind/flatMap mạnh hơn vì parser sau phụ thuộc kết quả parser trước. Sử dụng bind khi thật sự cần giúp grammar dễ đọc và có thể phân tích cấu trúc tốt hơn.

## 8. Repetition: many, many1 và optional

Các combinator lặp cho phép mô tả danh sách và phần tử tùy chọn.

### 8.1. many

many(parser) nhận không hoặc nhiều lần xuất hiện:

~~~text
arguments = many(expression)
~~~

Parser có thể trả danh sách rỗng nếu không có phần tử nào.

### 8.2. many1

many1(parser) yêu cầu ít nhất một phần tử:

~~~text
nonEmptyArguments = many1(expression)
~~~

Nếu input không có phần tử phù hợp, parser thất bại.

### 8.3. optional

optional(parser) chấp nhận parser có hoặc không:

~~~text
returnStatement =
    sequence(
        keyword("return"),
        optional(expression)
    )
~~~

Kết quả có thể là Some(expression) hoặc None.

### 8.4. Repetition phải bảo đảm tiến triển

Một lỗi quan trọng là many(parser) với parser có thể thành công mà không tiêu thụ input. Khi đó, vòng lặp có thể lặp vô hạn.

Ví dụ, optional(identifier) luôn có thể thành công với None mà không di chuyển con trỏ. Đặt nó trực tiếp bên trong many có thể gây vòng lặp vô hạn nếu framework không phát hiện.

Framework nên kiểm tra vị trí trước và sau mỗi lần lặp, báo lỗi nếu parser thành công nhưng không tiến triển, và có giới hạn độ sâu hoặc số lần lặp nếu cần bảo vệ tài nguyên.

### 8.5. Lặp có dấu phân cách

Danh sách đối số thường có dấu phẩy:

~~~text
arguments = separatedBy(expression, symbol(","))
~~~

Có thể có hai dạng: sepBy cho phép danh sách rỗng; sepBy1 yêu cầu ít nhất một phần tử. Cần quy định trailing comma có được phép hay không.

### 8.6. Danh sách có trailing separator

Một grammar có thể cho phép:

~~~text
permissions = [Read, Write, Approve,]
~~~

Combinator có thể được xây từ separated list cộng optional separator cuối. Phải tránh trường hợp parser tiêu thụ dấu phẩy rồi thất bại ở phần tử tiếp theo mà không thể backtrack đúng.

## 9. Whitespace, comment và lexeme

Parser DSL cần xử lý khoảng trắng và comment nhất quán. Có hai kiến trúc phổ biến.

### 9.1. Parser ký tự trực tiếp

Mỗi parser quy tắc tự xử lý khoảng trắng. Cách này linh hoạt nhưng dễ lặp và quên xử lý whitespace ở một vị trí.

### 9.2. Parser token

Lexer tạo token và bỏ qua whitespace/comment không cần thiết. Parser combinator làm việc trên token stream. Cách này giúp grammar gọn hơn, đặc biệt khi DSL có string literal, escape sequence, Unicode identifier, comment nhiều dòng và lexer mode.

### 9.3. Lexeme combinator

Một combinator lexeme có thể chạy parser token rồi bỏ qua trailing trivia:

~~~text
lexeme(parser) =
    sequence(parser, whitespaceAndComments)
    |> keepFirst
~~~

Sau đó, keyword, identifier và symbol đều có thể được định nghĩa bằng lexeme.

### 9.4. Space consumer

Một space consumer nhận các khoảng trắng và comment được phép. Cần xác định nó xử lý dấu cách, tab, LF và CRLF, comment một dòng, comment nhiều dòng, comment lồng nhau nếu DSL hỗ trợ.

### 9.5. Whitespace nhạy theo ngữ cảnh

Một DSL indentation-sensitive không thể xóa toàn bộ whitespace trước khi parse. Khi đó, lexer cần phát token INDENT và DEDENT hoặc parser cần quan sát cột đầu dòng.

## 10. Xây grammar biểu thức

Biểu thức thường là phần khó nhất của DSL vì có nhiều mức precedence và associativity.

Ví dụ:

~~~text
total = base + quantity * unitPrice
~~~

Phép nhân cần được nhóm trước phép cộng.

### 10.1. Grammar theo tầng precedence

Một cách phổ biến là định nghĩa mỗi mức thành một parser:

~~~text
expression = comparison

comparison =
    chainLeft(addition, comparisonOperator)

addition =
    chainLeft(multiplication, addOperator)

multiplication =
    chainLeft(unary, multiplyOperator)

unary =
    choice(
        prefixOperatorAndUnary,
        primary
    )

primary =
    choice(
        numberLiteral,
        stringLiteral,
        functionCall,
        propertyAccess,
        identifier,
        parenthesizedExpression
    )
~~~

Trong đó chainLeft là combinator hoặc helper để phân tích dãy toán hạng với toán tử kết hợp trái.

### 10.2. Associativity

Với phép trừ, biểu thức:

~~~text
10 - 3 - 2
~~~

thường được hiểu là:

~~~text
(10 - 3) - 2
~~~

Đây là left associativity. Một phép lũy thừa có thể kết hợp phải:

~~~text
2 ^ 3 ^ 2
~~~

thành:

~~~text
2 ^ (3 ^ 2)
~~~

Parser phải mã hóa đúng quy tắc của từng toán tử.

### 10.3. Chain combinator

chainLeft(parser, operator) có thể parse toán hạng đầu, parse một cặp toán tử và toán hạng tiếp theo, kết hợp kết quả theo thứ tự trái sang phải và lặp đến khi không còn toán tử.

Mã giả:

~~~text
function chainLeft(term, operator):
    return sequence(term, many(sequence(operator, term)))
        |> foldLeft
~~~

### 10.4. Prefix và postfix operator

Prefix operator đứng trước toán hạng, ví dụ phủ định logic hoặc dấu âm. Postfix operator đứng sau, ví dụ kiểm tra null hoặc toán tử hậu tố do DSL định nghĩa. Nếu DSL hỗ trợ, cần quy định precedence của chúng so với call và property access.

### 10.5. Function call và property access

Các cấu trúc:

~~~text
customer.address.city
calculate(order.total)
~~~

thường có precedence cao. Có thể xây parser postfix để nối chuỗi truy cập thuộc tính và lời gọi vào một primary expression.

## 11. Left recursion và cách xử lý

Một grammar có left recursion nếu quy tắc gọi lại chính nó ở vị trí đầu tiên mà không tiêu thụ input.

Ví dụ:

~~~text
Expression = Expression "+" Term | Term
~~~

Nếu triển khai bằng recursive descent trực tiếp, parser có thể gọi chính nó vô hạn trước khi đọc ký tự nào.

### 11.1. Loại bỏ left recursion

Có thể chuyển grammar sang dạng không đệ quy trái:

~~~text
Expression = Term ("+" Term)*
~~~

Sau đó fold danh sách toán tử và toán hạng thành AST kết hợp trái.

### 11.2. Dùng chain combinator

chainLeft là cách tự nhiên để mô tả chuỗi phép toán kết hợp trái mà không cần left recursion.

### 11.3. Pratt parser

Với expression grammar có nhiều toán tử, Pratt parser dùng binding power để quyết định mức ưu tiên. Nó có thể được dùng như một thành phần trong framework parser combinator.

### 11.4. Packrat hoặc memoization

Một số parser framework hỗ trợ memoization để tránh tính lại parser tại cùng vị trí. Memoization có thể hỗ trợ một số dạng grammar đệ quy, nhưng không tự động giải quyết mọi left recursion. Cần biết chính xác thư viện hỗ trợ loại grammar nào.

## 12. Lookahead, try và backtracking

Backtracking cho phép parser thử một cách phân tích rồi quay lại nếu thất bại.

### 12.1. Lookahead dương

Lookahead kiểm tra parser có thể thành công mà không tiêu thụ input:

~~~text
lookAhead(keyword("rule"))
~~~

Nó hữu ích để chọn nhánh hoặc kiểm tra prefix.

### 12.2. Lookahead phủ định

Negative lookahead thành công khi parser được kiểm tra thất bại. Ví dụ, identifier có thể đọc các ký tự cho đến khi gặp delimiter không thuộc identifier.

### 12.3. Try hoặc attempt

Một combinator try có thể cho phép backtrack kể cả khi parser con đã tiêu thụ một phần input. Nó hữu ích với các nhánh có prefix chung, nhưng dùng quá nhiều có thể làm lỗi bị lùi về vị trí đầu và làm parser thử lại nhiều lần.

### 12.4. Backtracking có chi phí

Nếu nhiều nhánh cùng thử lại một đoạn input dài, thời gian parse có thể tăng mạnh. Với grammar mơ hồ, một số trường hợp có thể tạo độ phức tạp rất lớn.

Nên dùng lookahead để phân biệt nhánh sớm, đặt nhánh đặc hiệu trước nhánh tổng quát, tránh backtracking không giới hạn, dùng memoization khi phù hợp và thiết kế grammar ít mơ hồ.

### 12.5. Cut hoặc commit

Một số framework có combinator commit/cut để nói rằng khi đã nhận diện prefix đủ đặc trưng, không thử nhánh khác nữa. Điều này giúp tránh backtracking và cải thiện diagnostic.

Ví dụ, sau khi đọc keyword rule và dấu nháy mở tên rule, parser có thể commit vào grammar rule declaration.

## 13. Parser cho cấu trúc DSL

Parser combinator giúp xây các quy tắc lớn từ parser nhỏ.

### 13.1. Identifier

~~~text
identifier =
    map(
        sequence(
            satisfy(isIdentifierStart),
            many(satisfy(isIdentifierContinue))
        ),
        joinCharacters
    )
~~~

Quy tắc ký tự đầu và ký tự tiếp theo phải theo đặc tả DSL. Nếu có Unicode, cần dùng Unicode category và chính sách normalization đã được công bố.

### 13.2. Literal

Một parser literal có thể chọn giữa số, chuỗi, boolean và null:

~~~text
literal =
    choice(
        numberLiteral,
        stringLiteral,
        booleanLiteral,
        nullLiteral
    )
~~~

Thứ tự và cách nhận diện keyword cần tránh việc trueValue bị phân tích thành boolean true rồi còn Value.

### 13.3. Property access

~~~text
propertyAccess =
    sequence(
        identifier,
        many(sequence(symbol("."), identifier))
    )
~~~

Kết quả có thể là một danh sách tên hoặc một cây truy cập lồng nhau.

### 13.4. Function call

~~~text
functionCall =
    sequence(
        identifier,
        symbol("("),
        separatedBy(expression, symbol(",")),
        symbol(")")
    )
~~~

Nếu DSL hỗ trợ named argument, parser cần phân biệt đối số vị trí và đối số có tên.

### 13.5. Block

~~~text
block =
    between(
        symbol("{"),
        many(statement),
        symbol("}")
    )
~~~

Nếu block có thể rỗng, many(statement) phù hợp. Nếu bắt buộc ít nhất một statement, dùng many1.

### 13.6. Rule declaration

~~~text
ruleDeclaration =
    sequence(
        keyword("rule"),
        stringLiteral,
        symbol("{"),
        optional(conditionClause),
        actionClause,
        symbol("}")
    )
    |> buildRule
~~~

Parser thực tế cần xử lý comment, source span và diagnostic cho từng thành phần.

## 14. Tạo AST và giữ source span

Parser thường tạo AST để các bước sau có thể kiểm tra kiểu, tối ưu và sinh mã.

Ví dụ:

~~~text
BinaryExpression {
    operator: Add
    left: Identifier("subtotal")
    right: BinaryExpression {
        operator: Multiply
        left: Identifier("quantity")
        right: Identifier("unitPrice")
    }
}
~~~

### 14.1. AST có kiểu

Mỗi node nên có kiểu rõ ràng. Điều này giúp semantic analysis tránh phải đoán node đang chứa dữ liệu gì.

Ví dụ:
- LiteralExpression.
- IdentifierExpression.
- BinaryExpression.
- FunctionCallExpression.
- VariableDeclaration.
- ConditionalStatement.
- RuleDeclaration.

### 14.2. Source span

Mỗi node có thể lưu offset bắt đầu, offset kết thúc, dòng và cột nếu cần, cùng source file hoặc document ID. Source span giúp diagnostic trỏ đúng đoạn code.

### 14.3. Token span và node span

Token span mô tả vị trí token. Node span bao phủ toàn cấu trúc cú pháp. Ví dụ, span của FunctionCall có thể bắt đầu ở tên hàm và kết thúc sau dấu ngoặc đóng.

### 14.4. Giữ comment và trivia

AST có thể bỏ comment để gọn. Nếu workbench cần formatter, documentation hoặc refactoring, có thể dùng CST hoặc gắn trivia vào token/node.

### 14.5. Node tổng hợp

Một số node được tạo bởi parser hoặc bước desugaring, không tương ứng trực tiếp với token nguồn. Cần đánh dấu synthetic node hoặc giữ origin mapping để công cụ giải thích được nguồn gốc.

## 15. Xử lý lỗi và diagnostic

Parser không chỉ cần biết thành công hay thất bại. Một framework hữu ích cần tạo lỗi dễ hiểu.

### 15.1. Expected token

Nếu parser đang chờ dấu ngoặc đóng nhưng gặp EOF, diagnostic nên nói rõ vị trí lỗi, ký tự hoặc token mong đợi, token thực tế hoặc EOF và context đang phân tích.

Ví dụ:

~~~text
rules.dsl:12:18: Expected ')' to close function call, found end of file.
~~~

### 15.2. Tổng hợp lỗi từ choice

Khi nhiều nhánh thất bại, framework có thể chọn lỗi ở vị trí xa nhất mà parser đã đạt tới và hợp nhất tập expected token tại vị trí đó. Cách này thường hữu ích hơn việc chỉ báo lỗi của nhánh cuối cùng.

### 15.3. Context label

Một parser có thể được gắn nhãn:

~~~text
label("function argument", expression)
~~~

Khi thất bại, diagnostic có thể hiển thị “trong đối số hàm” thay vì chỉ liệt kê nhiều token nội bộ.

### 15.4. Error severity

Có thể phân loại Error, Warning, Hint và Information. Parser thường phát error; linter hoặc semantic analyzer có thể phát các mức khác.

### 15.5. Tránh diagnostic trùng lặp

Backtracking có thể tạo nhiều lỗi thử nghiệm không phải lỗi cuối cùng. Framework nên giữ lỗi tốt nhất theo vị trí và mức tiêu thụ input, thay vì hiển thị mọi thất bại nội bộ.

## 16. Error recovery

Trong editor, người dùng thường đang gõ mã chưa hoàn chỉnh. Parser cần có khả năng phục hồi để vẫn cung cấp cấu trúc cho phần còn lại.

### 16.1. Panic-mode recovery

Parser bỏ qua token đến điểm đồng bộ như dấu chấm phẩy, dấu đóng block hoặc keyword bắt đầu statement tiếp theo. Ví dụ, khi một statement lỗi, parser có thể bỏ qua đến newline hoặc dấu đóng block để tiếp tục phân tích.

### 16.2. Insertion recovery

Parser giả định một token bị thiếu và chèn token tổng hợp để tiếp tục. Ví dụ, thiếu dấu ngoặc đóng trước newline. Token tổng hợp phải được đánh dấu để formatter hoặc editor không coi đó là token nguồn thực sự.

### 16.3. Deletion recovery

Parser có thể bỏ một token bất ngờ nếu token kế tiếp cho phép tiếp tục an toàn. Không nên xóa tùy tiện vì có thể làm thay đổi ý nghĩa.

### 16.4. Error node

AST có thể chứa ErrorExpression hoặc ErrorStatement. Các bước sau biết vùng nào chưa hợp lệ và tránh crash khi truy cập node.

### 16.5. Recovery theo cấu trúc

Nếu parser biết đang ở trong function call, nó có thể đồng bộ tại dấu phẩy hoặc dấu ngoặc đóng. Nếu đang ở trong block, nó có thể đồng bộ tại dấu đóng block hoặc đầu statement kế tiếp.

### 16.6. Giới hạn phục hồi

Recovery quá mạnh có thể tạo nhiều node giả và diagnostic dây chuyền. Nên giới hạn số lỗi, tránh vòng lặp không tiến triển và giữ nguyên phần nguồn chưa hiểu.

## 17. Lexer integration: parser trên ký tự hay trên token?

Parser combinator có thể làm việc trực tiếp trên ký tự hoặc trên token do lexer tạo.

### 17.1. Character-level parser

Ưu điểm là không cần lexer riêng, dễ xây parser cho định dạng nhỏ và có thể kết hợp lexical với syntax rule.

Hạn chế là grammar phải tự xử lý whitespace ở nhiều nơi, source position và comment phức tạp hơn, token nhiều ký tự và string mode cần được quản lý cẩn thận.

### 17.2. Token-level parser

Lexer chuyển input thành token:

~~~text
LET IDENTIFIER(total) EQUAL IDENTIFIER(quantity)
STAR IDENTIFIER(unitPrice) PLUS IDENTIFIER(shippingFee)
~~~

Parser làm việc trên token, không phải ký tự. Cách này phù hợp với DSL có từ khóa, literal, comment, string và nhiều mode.

### 17.3. Token chứa source span

Mỗi token nên giữ lexeme hoặc semantic value và vị trí nguồn. Khi parser tạo AST, node có thể hợp nhất span của token đầu và token cuối.

### 17.4. Trivia channel

Whitespace và comment có thể được giữ ở trivia channel để formatter và editor dùng, trong khi parser chỉ xử lý token chính.

### 17.5. Chia sẻ lexer trong workbench

Nếu formatter, syntax highlighting và parser đều cần lexical structure, workbench nên tái sử dụng lexer hoặc token model chung để tránh mỗi thành phần hiểu token theo cách khác nhau.

## 18. Grammar có thể mở rộng và plugin

Một framework parser combinator có thể hỗ trợ grammar được xây động, phù hợp với workbench cho phép extension.

### 18.1. Parser registry

Workbench có thể đăng ký parser cho Expression, Statement, Type declaration, Annotation hoặc Embedded language block. Một plugin có thể bổ sung cú pháp mới bằng cách đăng ký parser theo extension point đã định nghĩa.

### 18.2. Thứ tự ưu tiên plugin

Nếu nhiều plugin đăng ký parser cho cùng một vị trí grammar, framework cần quy định thứ tự thử, cách khai báo priority, có được phép override parser lõi không, cách phát hiện xung đột và cách báo lỗi khi hai extension không tương thích.

Không nên để kết quả parse phụ thuộc thứ tự load plugin không ổn định.

### 18.3. Grammar version

Parser cần biết phiên bản DSL hoặc language profile đang sử dụng. Một cú pháp chỉ được phép từ phiên bản mới không nên vô tình được chấp nhận trong profile cũ.

### 18.4. Feature flag

Một số cú pháp có thể bật theo cấu hình dự án. Parser có thể nhận ParserConfig hoặc LanguageProfile để quyết định parser nào được kích hoạt.

### 18.5. Plugin isolation

Parser plugin là code chạy trong process workbench. Nếu plugin không đáng tin cậy, cần giới hạn quyền hoặc chạy trong môi trường cô lập. Không nên cho parser tùy ý truy cập file, network hoặc dữ liệu nhạy cảm chỉ vì nó được đăng ký vào grammar.

## 19. Tổ chức framework parser combinator

Một framework nên tách phần lõi parser khỏi grammar cụ thể của DSL.

Một cấu trúc module minh họa:

~~~text
parser-framework/
    core/
        Parser
        ParseResult
        InputCursor
        SourceSpan
        Diagnostic
    combinators/
        sequence
        choice
        map
        bind
        many
        optional
        separatedBy
        lookAhead
        attempt
    token/
        Token
        TokenStream
        Lexeme
        Trivia
    grammar/
        ExpressionParser
        StatementParser
        DeclarationParser
    ast/
        Expression
        Statement
        Declaration
    recovery/
        Synchronization
        ErrorNode
        RecoveryStrategy
    integration/
        LanguageServerAdapter
        FormatterAdapter
~~~

### 19.1. Core API

Core nên định nghĩa giao diện parser, input cursor, kết quả parse và diagnostic. Các combinator không nên phụ thuộc vào một grammar cụ thể.

### 19.2. Combinator library

Các combinator nên có semantics nhất quán về backtracking, consumption, lỗi và vị trí nguồn. Tên hàm nên phản ánh đúng hành vi.

### 19.3. Grammar module

Grammar của DSL sử dụng combinator để định nghĩa expression, statement, declaration và document. Module này không nên chứa chi tiết lưu file hoặc giao diện editor.

### 19.4. AST module

AST nên độc lập với cách parser được triển khai nếu có thể. Điều này giúp thay parser hoặc bổ sung frontend khác mà không phải viết lại toàn bộ semantic analyzer.

### 19.5. Workbench adapter

Workbench adapter chuyển parse result, diagnostic và source span sang giao thức editor hoặc language server. Parser core không nên phụ thuộc trực tiếp vào API của một editor cụ thể.

## 20. Ví dụ xây parser combinator từ đầu

Giả sử DSL hỗ trợ phép cộng, nhân, số nguyên và dấu ngoặc.

### 20.1. Mô hình parser tối giản

~~~text
Parser<T> {
    parse(input, position) -> Result<T>
}

Result<T> =
    Success(value, nextPosition)
  | Failure(error, errorPosition, consumed)
~~~

### 20.2. Primitive digit

~~~text
digit =
    satisfy(character => character is between '0' and '9')
~~~

### 20.3. Integer parser

~~~text
integer =
    map(many1(digit), digits => parseNumber(digits))
~~~

### 20.4. Symbol parser

~~~text
symbol(text) =
    lexeme(string(text))
~~~

### 20.5. Primary expression

~~~text
primary =
    choice(
        integerLiteral,
        between(symbol("("), expression, symbol(")"))
    )
~~~

### 20.6. Multiplication

~~~text
multiplication =
    chainLeft(
        primary,
        map(symbol("*"), _ => Multiply)
    )
~~~

### 20.7. Addition

~~~text
addition =
    chainLeft(
        multiplication,
        map(symbol("+"), _ => Add)
    )
~~~

### 20.8. Expression và document

~~~text
expression = addition
document = sequence(expression, eof)
~~~

Với input:

~~~text
2 + 3 * (4 + 1)
~~~

AST có thể là:

~~~text
Add(
    Integer(2),
    Multiply(
        Integer(3),
        Add(Integer(4), Integer(1))
    )
)
~~~

AST thể hiện phép nhân được nhóm trước phép cộng. Sau đó evaluator có thể tính kết quả hoặc compiler có thể sinh mã.

## 21. Parser combinator và semantic analysis

Parser xác định cấu trúc cú pháp. Nó không nhất thiết biết một tên biến có được khai báo hay kiểu có tương thích không.

Ví dụ:

~~~text
let total = customer.name + 10
~~~

Parser có thể tạo AST hợp lệ dù phép cộng chuỗi và số không được DSL hỗ trợ.

Semantic analyzer sẽ xây symbol table, phân giải customer và name, xác định kiểu của hai toán hạng, kiểm tra toán tử cộng có hỗ trợ cặp kiểu đó không và tạo diagnostic nếu không hợp lệ.

### 21.1. Không nhồi logic nghiệp vụ vào parser

Nếu parser kiểm tra trực tiếp schema database hoặc gọi service để phân giải tên, nó trở nên khó kiểm thử và không còn là parser thuần túy. Nên giữ parse syntax độc lập, sau đó chạy semantic analysis với context phù hợp.

### 21.2. Parser có thể dùng symbol context trong một số DSL

Một số cú pháp thực sự phụ thuộc khai báo trước đó, ví dụ generic type hoặc directive mở rộng grammar. Khi đó parser có thể nhận immutable parse context hoặc symbol snapshot. Cần phân biệt đây là grammar context với việc kiểm tra ngữ nghĩa đầy đủ.

### 21.3. Parse result và semantic result

Có thể dùng các kiểu kết quả riêng:

~~~text
ParseResult<AST>
SemanticResult<TypedAST>
CompileResult<IR>
~~~

Tách các giai đoạn giúp diagnostic có nguồn gốc và trách nhiệm rõ ràng.

## 22. Incremental parsing trong workbench

Editor thường phân tích tài liệu nhiều lần khi người dùng gõ. Parse toàn bộ file sau mỗi ký tự có thể tốn thời gian.

### 22.1. Incremental parsing

Incremental parser tái sử dụng phần syntax tree không bị ảnh hưởng bởi thay đổi. Nó xác định vùng bị chỉnh sửa và cập nhật các node liên quan.

### 22.2. Parser combinator có hỗ trợ incremental không?

Không phải parser combinator nào cũng incremental. Có thể bổ sung input cursor có version, memoization theo parser ID và vị trí, dependency tracking, reparse theo vùng và syntax node có identity ổn định.

Cơ chế này phức tạp hơn parser một lần và cần thiết kế từ đầu nếu workbench yêu cầu phản hồi tức thời trên tài liệu lớn.

### 22.3. Memoization

Memoization lưu kết quả parse của parser tại một vị trí. Khi parser được gọi lại với cùng input version và vị trí, framework có thể dùng kết quả đã lưu.

Cache key cần bao gồm mọi yếu tố ảnh hưởng kết quả, ví dụ grammar version hoặc parse context. Nếu chỉ dùng vị trí mà input đã thay đổi, kết quả cũ sẽ sai.

### 22.4. Invalidation

Khi text thay đổi, các kết quả parse phụ thuộc vùng bị sửa cần được invalidated. Thay đổi một khai báo có thể ảnh hưởng parser phụ thuộc symbol ở nhiều vùng khác, nên dependency model cần được xác định.

### 22.5. Cancellation

Parser cho editor nên hỗ trợ cancellation để dừng công việc lỗi thời khi người dùng tiếp tục gõ. Kết quả parse của document version cũ không nên ghi đè diagnostic hoặc syntax tree mới.

## 23. Hiệu năng và giới hạn tài nguyên

Parser combinator tạo abstraction tiện dụng, nhưng nếu thiết kế không cẩn thận có thể gây allocation và backtracking lớn.

### 23.1. Backtracking quá mức

Nhiều choice và attempt có thể khiến parser thử lại cùng input nhiều lần. Thiết kế grammar rõ ràng và dùng lookahead/commit đúng chỗ giúp giảm chi phí.

### 23.2. Deep recursion

Một biểu thức lồng quá sâu có thể làm call stack tràn. Framework cần giới hạn độ sâu, dùng parser stack an toàn hoặc xử lý một số cấu trúc lặp theo vòng lặp.

### 23.3. Allocation

Mỗi combinator có thể tạo closure, tuple hoặc object kết quả. Với parser chạy nhiều lần trong editor, allocation lớn gây áp lực GC. Có thể tối ưu hot path sau khi đo.

### 23.4. Packrat memoization

Packrat parser dùng memoization có thể đạt thời gian tuyến tính cho một số PEG grammar, nhưng đổi lại bộ nhớ tăng theo số parser và vị trí input. Cần đánh giá kích thước tài liệu và giới hạn cache.

### 23.5. Input lớn hoặc độc hại

Workbench có thể mở tài liệu rất lớn hoặc input được tạo tự động. Cần giới hạn kích thước input, độ sâu lồng, số token, số lỗi được tích lũy, thời gian parse và số lần backtracking hoặc số trạng thái memoized.

### 23.6. Benchmark theo grammar thực tế

Không nên chỉ benchmark parser số nguyên. Hãy đo file DSL có comment, string, block lồng, biểu thức dài, lỗi cú pháp và cấu trúc mở rộng.

## 24. Kiểm thử parser combinator

Parser framework cần kiểm thử cả combinator lõi và grammar của DSL.

### 24.1. Unit test cho primitive

Kiểm tra char nhận đúng ký tự, string nhận đúng literal, EOF chỉ thành công ở cuối input, satisfy từ chối ký tự không phù hợp và source position được cập nhật đúng.

### 24.2. Unit test cho combinator

Kiểm tra sequence giữ đúng thứ tự và kết quả, choice thử nhánh theo semantics đã định, many và many1 xử lý số lượng phần tử, optional phân biệt có và không có giá trị, separatedBy xử lý dấu phân cách và trailing comma, lookahead không tiêu thụ input, attempt backtrack đúng và many phát hiện parser không tiến triển.

### 24.3. Golden tests cho grammar

Mỗi ví dụ nguồn có AST mong đợi hoặc canonical serialization. Điều này giúp phát hiện thay đổi grammar khi framework được cập nhật.

### 24.4. Error tests

Kiểm tra lỗi ở EOF, token không mong đợi, dấu ngoặc thiếu, keyword sai, danh sách có dấu phẩy thừa, biểu thức lồng sâu và nhánh choice mơ hồ. Xác nhận diagnostic chỉ đúng vị trí và expected token phù hợp.

### 24.5. Recovery tests

Cung cấp tài liệu có nhiều lỗi và xác nhận parser vẫn tạo node cho phần hợp lệ sau điểm đồng bộ. Kiểm tra không có vòng lặp vô hạn và số lỗi không tăng vô hạn.

### 24.6. Property-based tests

Sinh input theo grammar hoặc gần grammar, kiểm tra parser không crash, không treo và AST tuân theo invariant. Với chương trình hợp lệ, có thể parse rồi serialize canonical form và parse lại.

### 24.7. Round-trip tests

Nếu có pretty printer:
1. Parse nguồn.
2. In AST thành nguồn chuẩn.
3. Parse lại.
4. So sánh cấu trúc hoặc semantics.

### 24.8. Fuzz tests

Fuzzing giúp tìm lỗi ở chuỗi, comment, Unicode, dấu ngoặc, backtracking và recovery. Lưu seed và input gây lỗi để tái hiện.

### 24.9. Kiểm thử hiệu năng

Theo dõi thời gian parse, allocation, peak memory, số lần backtracking và thời gian phản hồi incremental. Đo cả input hợp lệ lẫn input gần hợp lệ có nhiều lỗi.

## 25. Những lỗi thiết kế thường gặp

### 25.1. Dùng choice không kiểm soát

Các nhánh chồng lấn có thể backtrack quá nhiều hoặc nhận sai prefix. Hãy phân tích FIRST set, dùng lookahead và commit khi đã xác định nhánh.

### 25.2. Quên EOF

Parser chấp nhận prefix hợp lệ nhưng bỏ qua nội dung còn lại. Parser cấp document nên xác nhận EOF.

### 25.3. many với parser không tiêu thụ input

Điều này có thể gây vòng lặp vô hạn. Framework phải kiểm tra tiến triển.

### 25.4. Không phân biệt consumed failure

Nếu framework luôn thử nhánh tiếp theo sau mọi lỗi, diagnostic có thể bị che và parser làm việc thừa. Cần semantics rõ cho consumption và backtracking.

### 25.5. Đưa semantic validation vào parser

Parser trở nên phụ thuộc database, schema hoặc service. Hãy tách parse syntax và semantic analysis trừ khi context thực sự là một phần grammar.

### 25.6. Không giữ source span

Lỗi chỉ báo vị trí cuối cùng hoặc không có dòng/cột sẽ gây khó khăn cho editor. Token và AST node nên giữ source span.

### 25.7. Grammar lặp lại whitespace logic

Mỗi parser tự xử lý whitespace dễ tạo hành vi không nhất quán. Hãy dùng token parser hoặc lexeme/space consumer chung.

### 25.8. Không kiểm soát left recursion

Recursive descent trực tiếp với grammar left-recursive có thể tràn stack. Dùng grammar không đệ quy trái, chain combinator hoặc parser có hỗ trợ phù hợp.

### 25.9. Recovery làm thay đổi ý nghĩa

Tự chèn hoặc xóa token mà không đánh dấu synthetic có thể khiến các bước sau coi mã giả là mã thật. Error node và origin metadata giúp tránh nhầm lẫn.

### 25.10. Không version grammar và plugin

Kết quả parse có thể thay đổi theo thứ tự load plugin hoặc profile. Hãy quản lý grammar version và extension priority rõ ràng.

## 26. Quy trình xây parser combinator cho DSL

Một quy trình triển khai có thể gồm:

1. Xác định grammar và các token của DSL.
2. Quyết định parser làm việc trên ký tự hay token.
3. Định nghĩa Parser, ParseResult, InputCursor, SourceSpan và Diagnostic.
4. Cài primitive parser như char, string, satisfy và eof.
5. Cài combinator cơ bản: sequence, choice, map, bind, many, optional và separatedBy.
6. Quy định semantics về consumption, backtracking, lookahead và commit.
7. Xây parser cho literal, identifier và biểu thức.
8. Xây parser cho statement, block, declaration và toàn document.
9. Tạo AST có kiểu và source span.
10. Bổ sung error recovery và diagnostic cho editor.
11. Tích hợp parser với semantic analyzer, formatter và workbench.
12. Viết unit, golden, recovery, property-based và performance tests.
13. Đo hiệu năng và giới hạn tài nguyên trên tài liệu đại diện.
14. Quản lý grammar version và plugin extension nếu workbench hỗ trợ mở rộng.

## 27. Ví dụ tổng hợp: parser cho rule DSL

Nguồn:

~~~text
rule "bulk_discount" {
    when order.quantity >= 10
    then:
        set order.discount = 5%
        notify(order.owner, "Discount applied")
}
~~~

Một grammar khái niệm:

~~~text
document =
    sequence(many(ruleDeclaration), eof)

ruleDeclaration =
    sequence(
        keyword("rule"),
        stringLiteral,
        block
    )
    |> buildRule

block =
    between(
        symbol("{"),
        many(statement),
        symbol("}")
    )

statement =
    choice(
        conditionClause,
        assignment,
        functionCallStatement
    )

conditionClause =
    sequence(
        keyword("when"),
        expression
    )

assignment =
    sequence(
        keyword("set"),
        propertyAccess,
        symbol("="),
        expression
    )

expression =
    comparison

comparison =
    chainLeft(addition, comparisonOperator)

addition =
    chainLeft(multiplication, addOperator)

multiplication =
    chainLeft(primary, multiplyOperator)

primary =
    choice(
        literal,
        functionCall,
        propertyAccess,
        parenthesizedExpression
    )
~~~

### 27.1. Kết quả AST minh họa

~~~text
Rule(
  name = "bulk_discount",
  body = [
    Condition(
      GreaterOrEqual(
        Property(order, quantity),
        Integer(10)
      )
    ),
    Assignment(
      Property(order, discount),
      Percentage(5)
    ),
    FunctionCall(
      notify,
      [
        Property(order, owner),
        String("Discount applied")
      ]
    )
  ]
)
~~~

### 27.2. Semantic analysis

Sau parse, compiler kiểm tra order có trong scope hay không, quantity có kiểu số, discount nhận kiểu phần trăm, notify là hàm được phép gọi và kiểu cũng như số lượng đối số phù hợp.

### 27.3. Workbench sử dụng parse result

Workbench có thể dùng AST và source span để tô màu cú pháp, hiển thị lỗi tại vị trí cụ thể, gợi ý hoàn thành sau keyword when, format block, điều hướng đến khai báo symbol và tạo preview hoặc kế hoạch thực thi.

Parser combinator chỉ là một phần của hệ thống; giá trị của nó tăng lên khi parse result được chia sẻ bởi các công cụ khác.

## 28. Bài tập tự kiểm tra

### Bài 1: Primitive parser

Hãy định nghĩa parser cho một ký tự chữ cái và parser cho chuỗi keyword. Cần xử lý thế nào để keyword if không nhận nhầm prefix của identifier ifdef?

### Bài 2: Sequence và choice

Một statement có thể là khai báo biến, phép gán hoặc lời gọi hàm. Hãy viết cấu trúc combinator và giải thích thứ tự choice.

### Bài 3: Repetition

Hãy xây parser cho danh sách identifier phân cách bằng dấu phẩy. DSL cho phép danh sách rỗng và trailing comma. Nêu cách ngăn many lặp vô hạn.

### Bài 4: Precedence

Với toán tử cộng, trừ, nhân, chia và lũy thừa, hãy xác định các tầng precedence và associativity. Viết parser theo chainLeft hoặc chainRight phù hợp.

### Bài 5: Left recursion

Grammar Expression = Expression + Term | Term gây vấn đề gì với recursive descent? Hãy chuyển sang dạng không left-recursive và mô tả cách tạo AST.

### Bài 6: Backtracking

Hai nhánh grammar cùng bắt đầu bằng keyword use. Hãy đề xuất lookahead hoặc cách phân biệt prefix để giảm backtracking.

### Bài 7: Diagnostic

Input kết thúc ngay sau dấu mở ngoặc của function call. Hãy thiết kế diagnostic gồm vị trí, token mong đợi và context.

### Bài 8: Error recovery

Một block có ba statement, statement thứ hai sai cú pháp. Hãy chọn điểm đồng bộ và giải thích cách parser vẫn tạo AST cho statement thứ ba.

### Bài 9: Workbench integration

Một plugin bổ sung parser cho annotation. Hãy nêu cách đăng ký, xác định priority, quản lý grammar version và phát hiện xung đột.

### Bài 10: Kiểm thử

Hãy lập bộ kiểm thử cho parser framework gồm primitive, combinator, precedence, source span, EOF, recovery, property-based và performance. Nêu ít nhất một trường hợp có thể gây vòng lặp vô hạn hoặc backtracking quá mức.

## Kết luận

Parser combinator là cách xây dựng parser bằng cách kết hợp những parser nhỏ thành grammar lớn thông qua sequence, choice, map, repetition, optional, lookahead và các combinator khác. Kỹ thuật này tạo parser có tính thành phần, dễ tái sử dụng và phù hợp với workbench cần grammar mở rộng. Một framework tốt cần quy định rõ cách tiêu thụ input, backtracking, left recursion, source span, diagnostic và error recovery. Parser nên tạo AST có kiểu, phối hợp với lexer và semantic analyzer, đồng thời cung cấp kết quả hữu ích cho formatter, syntax highlighting và language server. Kiểm thử từng combinator, kiểm tra EOF, bảo đảm parser luôn tiến triển và đo hiệu năng trên grammar thực tế giúp framework hoạt động ổn định khi DSL phát triển.
