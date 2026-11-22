# Phân tích ưu tiên

Trong một **Domain-Specific Language (DSL)**, biểu thức thường kết hợp nhiều toán tử như cộng, nhân, so sánh, logic, truy cập thuộc tính và gọi hàm. Khi một biểu thức chứa nhiều toán tử, parser cần xác định cấu trúc nào được nhóm với nhau trước. Quy tắc này được gọi là **độ ưu tiên toán tử (operator precedence)**. Quá trình xác định cách nhóm biểu thức dựa trên các quy tắc đó được gọi là **phân tích ưu tiên**.

Ví dụ:

~~~text
total = basePrice + quantity * unitPrice
~~~

Nếu phép nhân có độ ưu tiên cao hơn phép cộng, biểu thức được hiểu là:

~~~text
total = basePrice + (quantity * unitPrice)
~~~

Nếu không có quy tắc ưu tiên rõ ràng, cùng một chuỗi token có thể có nhiều cây phân tích khác nhau và dẫn tới kết quả khác nhau. Phân tích ưu tiên vì vậy là một phần quan trọng của thiết kế grammar, parser và ngữ nghĩa biểu thức. Một DSL tốt cần xác định độ ưu tiên, tính kết hợp, cách xử lý toán tử một ngôi, ngoặc và các trường hợp không được phép kết hợp.

## 1. Độ ưu tiên toán tử là gì?

Độ ưu tiên quy định toán tử nào được nhóm trước khi biểu thức được đánh giá. Toán tử có độ ưu tiên cao hơn thường liên kết chặt hơn với các toán hạng.

Ví dụ:

~~~text
2 + 3 * 4
~~~

Theo quy tắc số học quen thuộc, phép nhân được nhóm trước:

~~~text
2 + (3 * 4)
~~~

Kết quả là 14. Nếu cộng được nhóm trước thì biểu thức trở thành:

~~~text
(2 + 3) * 4
~~~

và kết quả là 20. Hai cách nhóm tạo ra hai AST khác nhau, vì vậy parser không thể chỉ đọc các toán tử rồi để runtime tự đoán.

Độ ưu tiên là thuộc tính của grammar hoặc đặc tả ngôn ngữ, không phải đặc tính tự động của ký hiệu. DSL có thể chọn quy tắc quen thuộc như nhân trước cộng sau, nhưng cũng có thể định nghĩa thứ tự khác nếu phù hợp với miền. Điều quan trọng là quy tắc phải nhất quán và được công bố rõ.

## 2. Độ ưu tiên và tính kết hợp là hai khái niệm khác nhau

Độ ưu tiên trả lời câu hỏi **toán tử nào được nhóm trước khi có nhiều loại toán tử**. Tính kết hợp (associativity) trả lời câu hỏi **nhóm theo hướng nào khi cùng một toán tử xuất hiện liên tiếp**.

Ví dụ:

~~~text
a - b - c
~~~

Phép trừ thường kết hợp trái:

~~~text
(a - b) - c
~~~

Nếu nhóm phải:

~~~text
a - (b - c)
~~~

thì kết quả có thể khác. Với a = 10, b = 3 và c = 2:

- Kết hợp trái: (10 - 3) - 2 = 5.
- Kết hợp phải: 10 - (3 - 2) = 9.

Vì vậy, chỉ định độ ưu tiên mà không chỉ định associativity là chưa đủ để mô tả đầy đủ cách phân tích biểu thức.

### 2.1. Ba dạng kết hợp thường gặp

**Kết hợp trái (left-associative):** các toán tử cùng mức được nhóm từ trái sang phải.

~~~text
a - b - c  =>  (a - b) - c
a / b / c  =>  (a / b) / c
~~~

**Kết hợp phải (right-associative):** các toán tử cùng mức được nhóm từ phải sang trái.

~~~text
a = b = c  =>  a = (b = c)
a ^ b ^ c  =>  a ^ (b ^ c)
~~~

**Không kết hợp (non-associative):** không cho phép ghép liên tiếp cùng nhóm toán tử nếu thiếu ngoặc.

~~~text
a < b < c
~~~

Một DSL có thể từ chối biểu thức này và yêu cầu viết rõ:

~~~text
(a < b) and (b < c)
~~~

Không nên giả định mọi toán tử có cùng ký hiệu đều có cùng tính kết hợp. Ví dụ, phép trừ thường kết hợp trái, phép gán thường kết hợp phải, còn phép so sánh có thể không kết hợp tùy thiết kế DSL.

## 3. Bảng độ ưu tiên

Một cách tài liệu hóa đơn giản là lập bảng theo thứ tự từ ưu tiên cao xuống thấp. Ví dụ cho DSL biểu thức thông dụng:

| Mức | Nhóm toán tử | Ví dụ | Associativity |
|---:|---|---|---|
| 1 | Gọi hàm, truy cập thành viên, chỉ số | f(x), a.b, a[i] | Trái |
| 2 | Hậu tố | x++, x! | Trái hoặc theo định nghĩa |
| 3 | Một ngôi | -x, not x, !x | Phải |
| 4 | Nhân, chia, modulo | *, /, % | Trái |
| 5 | Cộng, trừ | +, - | Trái |
| 6 | So sánh thứ tự | <, <=, >, >= | Không kết hợp |
| 7 | So sánh bằng | ==, != | Không kết hợp |
| 8 | Logic AND | and, && | Trái |
| 9 | Logic OR | or, || | Trái |
| 10 | Điều kiện | ?: | Phải |
| 11 | Gán | =, += | Phải |

Đây chỉ là một bảng minh họa. DSL có thể không có tất cả các toán tử này, hoặc cần thêm toán tử đặc thù như lọc, nối chuỗi, truy vấn, pipe hay điều kiện miền. Mỗi mức cần được định nghĩa bằng ngữ nghĩa của DSL, không nên sao chép bảng của ngôn ngữ khác mà không cân nhắc người dùng và miền.

### 3.1. Toán tử có cùng mức ưu tiên

Nếu nhiều toán tử có cùng mức ưu tiên, associativity quyết định cách nhóm. Ví dụ, nếu cộng và trừ cùng một mức và kết hợp trái:

~~~text
a + b - c
~~~

được nhóm thành:

~~~text
(a + b) - c
~~~

Tương tự, nếu nhân và chia cùng một mức:

~~~text
a * b / c
~~~

thường được nhóm thành:

~~~text
(a * b) / c
~~~

### 3.2. Ngoặc thay đổi cách nhóm

Ngoặc cho phép người viết chủ động chỉ định nhóm biểu thức:

~~~text
2 + 3 * 4       // 2 + (3 * 4)
(2 + 3) * 4
~~~

Trong hầu hết DSL, biểu thức trong ngoặc được phân tích như một biểu thức độc lập rồi được dùng làm toán hạng của cấu trúc bên ngoài. Ngoặc thường không cần tạo node AST riêng nếu cấu trúc cây đã giữ đúng nhóm, nhưng CST hoặc mô hình source-preserving có thể lưu dấu ngoặc để formatter và IDE sử dụng.

## 4. Vì sao grammar có thể mơ hồ?

Xét grammar đơn giản:

~~~ebnf
expression = expression, "+", expression
           | expression, "*", expression
           | number ;
~~~

Với chuỗi:

~~~text
2 + 3 * 4
~~~

grammar trên cho phép ít nhất hai cách phân tích:

~~~text
Add(2, Multiply(3, 4))
Multiply(Add(2, 3), 4)
~~~

Đây là **mơ hồ cú pháp (syntactic ambiguity)**: một chuỗi đầu vào có nhiều hơn một cây phân tích hợp lệ theo grammar. Nếu mỗi cây mang ý nghĩa khác nhau, chương trình trở nên không xác định nếu đặc tả không bổ sung quy tắc.

Một parser có thể giải quyết bằng cách:

- Thiết kế grammar phân tầng để biểu diễn ưu tiên.
- Dùng parser hỗ trợ khai báo precedence và associativity.
- Dùng thuật toán phân tích biểu thức như precedence climbing hoặc Pratt parsing.
- Yêu cầu ngoặc tường minh ở những trường hợp không muốn ngôn ngữ tự chọn cách nhóm.

Không nên chỉ dựa vào thứ tự các nhánh grammar hoặc hành vi mặc định của parser generator nếu quy tắc đó không được tài liệu hóa. Cách parser xử lý xung đột phải phản ánh đặc tả ngôn ngữ.

## 5. Grammar phân tầng theo độ ưu tiên

Một cách phổ biến để loại bỏ mơ hồ là tạo một nonterminal cho mỗi tầng ưu tiên. Mỗi tầng chỉ gọi tầng ưu tiên cao hơn để tạo toán hạng, sau đó kết hợp các toán tử thuộc tầng hiện tại.

Ví dụ:

~~~ebnf
expression = additive ;

additive = multiplicative,
           { ("+" | "-"), multiplicative } ;

multiplicative = unary,
                 { ("*" | "/"), unary } ;

unary = ("+" | "-" | "not"), unary
      | primary ;

primary = number
        | identifier
        | "(", expression, ")" ;
~~~

Trong grammar này:

- primary là thành phần cơ bản như literal, tên hoặc biểu thức có ngoặc.
- unary xử lý toán tử một ngôi.
- multiplicative xử lý nhân và chia.
- additive xử lý cộng và trừ.
- expression là điểm vào của hệ biểu thức.

Do additive gọi multiplicative, còn multiplicative gọi unary, phép nhân và chia được nhóm trước phép cộng và trừ. Ngoặc trong primary cho phép quay lại toàn bộ expression, vì vậy biểu thức lồng nhau vẫn được hỗ trợ.

### 5.1. Cách đọc grammar

Với biểu thức:

~~~text
2 + 3 * 4
~~~

Parser bắt đầu từ expression, đi tới additive. additive đọc một multiplicative đầu tiên là 2, sau đó thấy dấu cộng. Nó yêu cầu một multiplicative tiếp theo. multiplicative đọc 3, thấy dấu nhân và đọc tiếp 4. Kết quả là cây:

~~~text
Add
├── Number(2)
└── Multiply
    ├── Number(3)
    └── Number(4)
~~~

Tầng grammar đã buộc phép nhân trở thành một node con của phép cộng mà không cần parser đoán từ chuỗi token.

### 5.2. Grammar phân tầng và associativity

Quy tắc lặp:

~~~ebnf
additive = multiplicative,
           { ("+" | "-"), multiplicative } ;
~~~

thường được triển khai bằng vòng lặp cập nhật node bên trái. Cách đó tạo kết hợp trái:

~~~text
a - b - c
~~~

AST:

~~~text
Subtract
├── Subtract
│   ├── Name(a)
│   └── Name(b)
└── Name(c)
~~~

Nếu muốn kết hợp phải, grammar hoặc cách xây AST phải thể hiện điều đó. Ví dụ toán tử lũy thừa có thể dùng:

~~~ebnf
power = primary, [ "^", unary ] ;
~~~

hoặc một quy tắc đệ quy phải tương đương, tùy cách xử lý unary và precedence mà DSL chọn.

### 5.3. Ưu điểm và giới hạn

Ưu điểm:

- Grammar thể hiện trực tiếp thứ tự ưu tiên.
- Parser đệ quy xuống có thể triển khai khá đơn giản.
- Mỗi tầng dễ kiểm tra và giải thích.
- Phù hợp với DSL có số lượng toán tử ổn định.

Giới hạn:

- Grammar dài ra khi có nhiều mức ưu tiên.
- Thêm toán tử mới có thể cần thay đổi nhiều quy tắc.
- Cấu trúc grammar có thể trở nên cồng kềnh với toán tử do người dùng định nghĩa.
- Cần chú ý loại bỏ đệ quy trái nếu parser đệ quy xuống không hỗ trợ.

## 6. Parser đệ quy xuống cho grammar ưu tiên

Với grammar phân tầng, mỗi nonterminal có thể được triển khai thành một hàm parser. Hàm ở tầng thấp hơn xử lý toán tử có độ ưu tiên cao hơn.

Ví dụ mã giả:

~~~text
parseExpression():
    return parseAdditive()

parseAdditive():
    node = parseMultiplicative()

    while nextToken is "+" or "-":
        operator = consume()
        right = parseMultiplicative()
        node = BinaryExpression(node, operator, right)

    return node

parseMultiplicative():
    node = parseUnary()

    while nextToken is "*" or "/":
        operator = consume()
        right = parseUnary()
        node = BinaryExpression(node, operator, right)

    return node

parseUnary():
    if nextToken is "+" or "-" or "not":
        operator = consume()
        operand = parseUnary()
        return UnaryExpression(operator, operand)

    return parsePrimary()

parsePrimary():
    if nextToken is NUMBER:
        return NumberLiteral(consume())

    if nextToken is IDENTIFIER:
        return NameReference(consume())

    if match("("):
        expression = parseExpression()
        expect(")")
        return expression

    error("Expected a primary expression")
~~~

Hai vòng while trong parseAdditive và parseMultiplicative tạo kết hợp trái. parseUnary gọi lại chính nó sau toán tử một ngôi nên biểu thức như ---x có thể được phân tích lồng nhau theo hướng phải. parsePrimary gọi lại parseExpression khi gặp ngoặc để hỗ trợ biểu thức lồng.

Parser không chỉ kiểm tra token; nó còn tạo AST. Cách cập nhật node trong vòng lặp là bước quyết định associativity.

## 7. Precedence climbing

Khi DSL có nhiều toán tử, việc tạo một hàm parser cho từng tầng có thể lặp lại nhiều mã. **Precedence climbing** là thuật toán phân tích biểu thức dùng một hàm chung và tham số ngưỡng ưu tiên.

Ý tưởng:

1. Phân tích một biểu thức nguyên tử hoặc một toán hạng đầu.
2. Xem toán tử tiếp theo có độ ưu tiên đủ cao để thuộc biểu thức hiện tại không.
3. Nếu có, tiêu thụ toán tử và phân tích vế phải với ngưỡng ưu tiên phù hợp.
4. Kết hợp vế trái và vế phải thành một node AST.
5. Tiếp tục cho đến khi toán tử kế tiếp có độ ưu tiên thấp hơn ngưỡng hiện tại hoặc không còn là toán tử hợp lệ ở vị trí đó.

Ví dụ bảng metadata:

| Toán tử | Precedence | Associativity |
|---|---:|---|
| +, - | 10 | Left |
| *, / | 20 | Left |
| ^ | 30 | Right |

Mã giả khái quát:

~~~text
parseExpression(minPrecedence):
    left = parsePrefix()

    while nextToken is an infix operator:
        operator = nextToken
        precedence = precedenceOf(operator)

        if precedence < minPrecedence:
            break

        consume(operator)

        if associativityOf(operator) is LEFT:
            nextMinimum = precedence + 1
        else:
            nextMinimum = precedence

        right = parseExpression(nextMinimum)
        left = BinaryExpression(left, operator, right)

    return left
~~~

Với toán tử kết hợp trái, ngưỡng cho vế phải tăng lên một đơn vị, khiến toán tử cùng mức được xử lý ở vòng lặp bên ngoài. Với toán tử kết hợp phải, ngưỡng giữ nguyên để vế phải có thể tiếp tục nhận toán tử cùng mức.

### 7.1. Ví dụ phép cộng và nhân

Với:

~~~text
2 + 3 * 4
~~~

Thuật toán đọc 2 làm vế trái. Khi gặp + ở precedence 10, nó phân tích vế phải với ngưỡng 11. Trong lần phân tích đó, 3 * 4 được nhận vì * có precedence 20. Khi quay lại, AST trở thành:

~~~text
Add(2, Multiply(3, 4))
~~~

### 7.2. Ví dụ kết hợp phải

Với:

~~~text
a ^ b ^ c
~~~

Nếu ^ có precedence 30 và kết hợp phải, vế phải được phân tích với ngưỡng 30. Do đó, biểu thức trở thành:

~~~text
a ^ (b ^ c)
~~~

Nếu toán tử được khai báo kết hợp trái, thuật toán sẽ tạo:

~~~text
(a ^ b) ^ c
~~~

### 7.3. Ưu điểm và giới hạn

Precedence climbing có mã triển khai gọn, dễ mở rộng bằng bảng precedence và phù hợp với parser biểu thức viết thủ công. Tuy nhiên, cần thiết kế cẩn thận các trường hợp prefix, postfix, toán tử điều kiện, toán tử không kết hợp và toán tử có cú pháp phức tạp hơn một token.

## 8. Pratt parsing và binding power

**Pratt parser** (top-down operator precedence parser) là một phương pháp phân tích biểu thức dựa trên các hàm xử lý theo vai trò của token. Nó thường dùng hai khái niệm:

- **Prefix parse function (nud)** xử lý token xuất hiện ở đầu một biểu thức, chẳng hạn literal, identifier, dấu ngoặc hoặc toán tử một ngôi.
- **Infix/postfix parse function (led)** xử lý token xuất hiện sau một biểu thức đã có, chẳng hạn toán tử cộng, gọi hàm, truy cập thuộc tính hoặc chỉ số.

Mỗi toán tử có thể được gán binding power để xác định mức độ gắn kết với biểu thức bên cạnh. Một cách triển khai thường có dạng:

~~~text
parseExpression(minBindingPower):
    token = consume()
    left = parsePrefix(token)

    while nextToken can continue an expression:
        (leftPower, rightPower) = bindingPower(nextToken)

        if leftPower < minBindingPower:
            break

        operator = consume()
        left = parseInfixOrPostfix(operator, left, rightPower)

    return left
~~~

Với phép cộng kết hợp trái, cặp binding power có thể là (10, 11). Với phép lũy thừa kết hợp phải, có thể dùng (30, 30). Chi tiết quy ước có thể khác giữa các triển khai; điều quan trọng là quan hệ giữa hai binding power thể hiện đúng associativity.

### 8.1. Prefix và infix cùng ký hiệu

Một ký hiệu có thể có vai trò khác nhau tùy vị trí:

~~~text
-5
a - b
~~~

Dấu - đầu biểu thức là toán tử prefix một ngôi. Dấu - sau biểu thức bên trái là toán tử infix hai ngôi. Pratt parser có thể gán hàm xử lý prefix cho dấu trừ và hàm xử lý infix cho cùng token đó.

### 8.2. Gọi hàm và truy cập thuộc tính

Các cấu trúc như:

~~~text
service.start()
items[index]
customer.address.city
~~~

có thể được xử lý như toán tử postfix hoặc led. Vì chúng thường có độ ưu tiên cao, chúng tiếp tục gắn vào biểu thức bên trái trước khi parser xử lý phép cộng hoặc so sánh bên ngoài.

### 8.3. Khi nào Pratt parser hữu ích?

Pratt parser đặc biệt thuận tiện khi DSL có nhiều loại biểu thức, nhiều toán tử prefix/infix/postfix hoặc cần mở rộng toán tử theo bảng cấu hình. Nó có thể giảm số tầng grammar và gom logic xử lý biểu thức vào một khung chung.

Đổi lại, cấu trúc parser ít hiển thị trực tiếp trong grammar EBNF hơn. Nhóm phát triển cần tài liệu hóa binding power và các parse function để người bảo trì hiểu cách mỗi token được diễn giải.

## 9. Shunting-yard và biểu thức hậu tố

Thuật toán **shunting-yard** của Dijkstra chuyển biểu thức trung tố (infix) thành hậu tố (postfix/RPN) hoặc xây dựng cây biểu thức bằng stack. Nó sử dụng stack toán tử để xử lý precedence và associativity.

Ví dụ:

~~~text
2 + 3 * 4
~~~

Biểu thức hậu tố:

~~~text
2 3 4 * +
~~~

Khi đánh giá hậu tố, parser/runtime đọc các toán hạng rồi áp dụng toán tử khi gặp chúng. Kết quả vẫn là 14.

Quy tắc khái quát khi đọc toán tử mới:

1. So sánh precedence của toán tử mới với toán tử trên đỉnh stack.
2. Nếu toán tử trên stack có precedence cao hơn, đưa toán tử trên stack ra output trước.
3. Nếu hai toán tử cùng precedence và toán tử mới kết hợp trái, đưa toán tử trên stack ra trước.
4. Nếu gặp dấu mở ngoặc, đẩy vào stack; khi gặp dấu đóng ngoặc, lấy toán tử ra cho tới dấu mở tương ứng.
5. Đẩy toán tử mới vào stack sau khi xử lý các toán tử cần ưu tiên trước.

Shunting-yard hữu ích cho biểu thức toán học tương đối đơn giản và evaluator dùng stack. Với DSL có lambda, truy cập thành viên, generic, pattern matching hoặc cú pháp biểu thức lồng phức tạp, Pratt hoặc parser grammar tổng quát có thể thuận tiện hơn.

## 10. Khai báo precedence trong parser generator

Một số parser generator cho phép giữ grammar biểu thức ngắn và khai báo độ ưu tiên, associativity riêng. Parser generator dùng metadata này để giải quyết xung đột parse, thường là shift/reduce conflict trong parser LR.

Ví dụ cú pháp minh họa kiểu khai báo:

~~~text
%left "+" "-"
%left "*" "/"
%right "^"
%nonassoc "<" ">" "==" "!="
~~~

Thứ tự các dòng có thể quy định mức ưu tiên tăng dần trong một số công cụ. Khi đó, * và / có ưu tiên cao hơn + và -; ^ kết hợp phải; nhóm so sánh không cho phép kết hợp trực tiếp.

Grammar biểu thức có thể ngắn:

~~~ebnf
expression = expression, operator, expression
           | number
           | identifier
           | "(", expression, ")" ;
~~~

Parser generator sử dụng bảng precedence để chọn cách xử lý xung đột. Cú pháp khai báo và quy tắc ưu tiên cụ thể phụ thuộc công cụ, vì vậy cần đọc tài liệu của generator đang dùng.

Ưu điểm:

- Grammar ngắn và gần với cấu trúc biểu thức tổng quát.
- Có thể dùng thuật toán LR đã được triển khai và tối ưu.
- Bảng precedence tập trung, dễ xem xét.

Hạn chế:

- Quy tắc xử lý xung đột phụ thuộc parser generator.
- Thông báo hoặc cảnh báo conflict có thể khó hiểu nếu grammar lớn.
- Việc thêm toán tử cần cập nhật cả grammar và metadata.
- Không phải parser generator nào cũng hỗ trợ cùng cú pháp hoặc cùng chính sách mặc định.

## 11. Toán tử một ngôi, hậu tố và gọi hàm

Một biểu thức thực tế không chỉ có toán tử infix. DSL cần xác định precedence cho các cấu trúc khác:

- Prefix unary: -x, not enabled, !ready.
- Postfix: value!, counter++ nếu ngôn ngữ hỗ trợ.
- Function call: calculate(x).
- Member access: order.total.
- Indexing: items[0].
- Null-safe access: customer?.address.
- Type cast: value as Decimal.

Ví dụ:

~~~text
-a.b * calculate(c)[index]
~~~

Parser cần xác định:

1. a.b là một biểu thức truy cập thuộc tính.
2. Dấu trừ áp dụng cho biểu thức nào.
3. calculate(c) là một lời gọi hàm.
4. [index] áp dụng vào kết quả gọi hàm.
5. Phép nhân kết hợp các biểu thức đã phân tích.

Một bảng precedence có thể đặt call, indexing và member access cao hơn unary; unary cao hơn multiplicative. Tuy nhiên, cần xem xét các trường hợp đặc biệt như cast hoặc postfix operator. Cú pháp càng phong phú thì việc thử các ví dụ kết hợp càng quan trọng.

## 12. Toán tử điều kiện và toán tử gán

Toán tử điều kiện ba ngôi thường có cú pháp:

~~~text
condition ? whenTrue : whenFalse
~~~

Nó thường có precedence thấp hơn toán tử logic nhưng cao hơn phép gán, và thường kết hợp phải để hỗ trợ:

~~~text
a ? b : c ? d : e
~~~

được hiểu là:

~~~text
a ? b : (c ? d : e)
~~~

Toán tử gán cũng thường kết hợp phải:

~~~text
a = b = c
~~~

có thể được hiểu là:

~~~text
a = (b = c)
~~~

Tuy nhiên, nhiều DSL khai báo không cho phép phép gán lồng hoặc không coi assignment là biểu thức. Khi đó, không nên thêm precedence cho gán chỉ vì các ngôn ngữ lập trình phổ biến có toán tử này. Cần xác định cú pháp phù hợp với mục tiêu DSL.

## 13. Toán tử so sánh và toán tử không kết hợp

Một số toán tử không nên cho phép nối liên tiếp nếu ngữ nghĩa không rõ. Ví dụ:

~~~text
a < b < c
~~~

Có ít nhất hai cách hiểu:

- (a < b) < c: so sánh kết quả Boolean với c.
- a < b and b < c: kiểm tra b nằm giữa a và c.

Nếu DSL muốn biểu thức so sánh chuỗi như toán học, cần định nghĩa rõ semantics của chained comparison. Nếu không, có thể đánh dấu toán tử so sánh là non-associative và yêu cầu:

~~~text
(a < b) and (b < c)
~~~

Tương tự, DSL có thể cấm:

~~~text
a == b == c
~~~

trừ khi có định nghĩa rõ rằng đây là so sánh chuỗi. Quy tắc non-associative giúp parser báo lỗi sớm thay vì tạo một AST có thể gây hiểu nhầm.

## 14. Toán tử logic và short-circuit

Độ ưu tiên logic thường đặt NOT cao hơn AND, AND cao hơn OR:

~~~text
not a or b and c
~~~

được nhóm:

~~~text
(not a) or (b and c)
~~~

Nhưng precedence chỉ xác định cách nhóm; nó không tự xác định thứ tự đánh giá hoặc short-circuit. DSL cần quy định riêng:

- and có dừng khi vế trái là false không?
- or có dừng khi vế trái là true không?
- Vế phải có thể chứa lời gọi hàm hoặc hiệu ứng không?
- Lỗi ở vế phải có xảy ra nếu vế trái đã quyết định kết quả không?

Ví dụ:

~~~text
isAuthorized and loadSensitiveRecord()
~~~

Nếu and short-circuit, loadSensitiveRecord chỉ được gọi khi isAuthorized là true. Đây là vấn đề ngữ nghĩa đánh giá, không chỉ là vấn đề precedence.

## 15. Toán tử do người dùng định nghĩa

Một số DSL cho phép plugin hoặc người dùng khai báo toán tử mới. Ví dụ:

~~~text
operator "within" precedence 15 left
operator "matches" precedence 25 nonassoc
~~~

Tính năng này có thể hữu ích cho DSL toán học, truy vấn hoặc quy tắc nghiệp vụ, nhưng làm parser phức tạp hơn vì precedence không còn hoàn toàn cố định trong grammar.

Những câu hỏi cần giải quyết:

- Toán tử được khai báo ở cấp module, file hay toàn dự án?
- Có thể thay đổi precedence của toán tử tích hợp không?
- Hai module khai báo cùng ký hiệu thì xử lý thế nào?
- Người dùng có thể tạo toán tử prefix, postfix và infix không?
- Cú pháp có được xác định trước khi parse toàn bộ file không?
- Formatter và IDE lấy bảng precedence từ đâu?
- Một thay đổi precedence có làm thay đổi ý nghĩa source cũ không?

Nếu precedence do người dùng khai báo, parser thường cần thu thập khai báo toán tử trước khi phân tích các biểu thức chịu ảnh hưởng. Điều này có thể yêu cầu nhiều lượt phân tích hoặc một grammar biểu thức có thể cấu hình.

### 15.1. Tương thích khi thay đổi precedence

Thay đổi precedence của toán tử đã tồn tại có thể làm cùng một source tạo AST khác. Ví dụ, nếu phiên bản mới đổi thứ tự ưu tiên của and và or, một điều kiện cũ có thể thay đổi hành vi mà không có lỗi cú pháp.

Vì vậy, thay đổi precedence là thay đổi ngữ nghĩa và có thể phá vỡ tương thích. DSL có thể cần version ngôn ngữ, cảnh báo hoặc yêu cầu người viết thêm ngoặc trong các biểu thức bị ảnh hưởng.

## 16. Phân biệt precedence với thứ tự đánh giá

Độ ưu tiên xác định cấu trúc cây. Thứ tự đánh giá xác định thành phần nào được tính trước khi thực thi. Hai khái niệm thường liên quan nhưng không đồng nhất.

Ví dụ:

~~~text
f() + g() * h()
~~~

Precedence xác định AST:

~~~text
Add(
    Call(f),
    Multiply(Call(g), Call(h))
)
~~~

Nhưng AST đó chưa tự xác định f() được gọi trước g() hay h(). DSL cần quy định evaluation order, ví dụ từ trái sang phải, hoặc cho phép thứ tự không xác định nếu các biểu thức không có hiệu ứng quan sát được.

Với toán tử AND short-circuit, thứ tự đánh giá còn ảnh hưởng tới việc vế phải có được thực thi hay không. Với toán tử số học thuần, thứ tự có thể không ảnh hưởng kết quả nếu không có lỗi hoặc hiệu ứng; nhưng điều đó cần được bảo đảm bởi ngữ nghĩa.

## 17. Tạo AST từ biểu thức có ưu tiên

AST cần phản ánh đúng cách nhóm mà precedence và associativity quy định. Ví dụ:

~~~text
a + b * c - d
~~~

Với nhân ưu tiên cao hơn cộng/trừ, cộng và trừ cùng mức, kết hợp trái:

~~~text
Subtract(
    Add(
        Name(a),
        Multiply(Name(b), Name(c))
    ),
    Name(d)
)
~~~

Một cách nhìn bằng cây:

~~~mermaid
flowchart TD
    A["-"] --> B["+"]
    A --> C[d]
    B --> D[a]
    B --> E["*"]
    E --> F[b]
    E --> G[c]
~~~

Sau khi AST được tạo, các giai đoạn semantic analysis và evaluation không cần đọc lại bảng precedence. Chúng duyệt cây đã biểu diễn rõ cấu trúc.

Điều này cũng giúp compiler tối ưu hóa. Một phép biến đổi AST phải bảo toàn cấu trúc ngữ nghĩa, chứ không chỉ thao tác trên chuỗi token.

## 18. Ví dụ triển khai precedence climbing

Đoạn mã giả sau cho thấy một parser có thể dùng bảng precedence để phân tích toán tử infix. Đây là ví dụ khái niệm; một implementation đầy đủ cần quản lý token span, lỗi cú pháp, prefix, postfix và các loại toán tử khác.

~~~text
precedence = {
    "+": 10,
    "-": 10,
    "*": 20,
    "/": 20,
    "^": 30
}

associativity = {
    "+": LEFT,
    "-": LEFT,
    "*": LEFT,
    "/": LEFT,
    "^": RIGHT
}

parseExpression(minPrecedence):
    left = parsePrimary()

    while nextToken is in precedence:
        op = nextToken
        p = precedence[op]

        if p < minPrecedence:
            break

        consume(op)

        if associativity[op] == LEFT:
            nextMin = p + 1
        else:
            nextMin = p

        right = parseExpression(nextMin)
        left = BinaryExpression(left, op, right)

    return left

parsePrimary():
    if nextToken is NUMBER:
        return NumberLiteral(consume())

    if nextToken is IDENTIFIER:
        return NameReference(consume())

    if match("("):
        node = parseExpression(0)
        expect(")")
        return node

    error("Expected expression")
~~~

Với biểu thức 2 + 3 * 4, parser tạo Add(2, Multiply(3, 4)). Với a ^ b ^ c, vì ^ kết hợp phải, parser tạo Power(a, Power(b, c)).

Nếu thêm toán tử mới, nhóm phát triển cập nhật bảng precedence và associativity. Tuy nhiên, vẫn cần xác định kiểu toán hạng, ngữ nghĩa và cách hiển thị trong formatter; chỉ thêm một dòng vào bảng chưa làm toán tử trở thành một phần hoàn chỉnh của DSL.

## 19. Kiểm thử phân tích ưu tiên

Kiểm thử nên xác nhận parser tạo đúng AST, không chỉ xác nhận source được chấp nhận. Một biểu thức có thể parse thành công nhưng bị nhóm sai.

Các nhóm trường hợp nên có:

- Hai toán tử có mức ưu tiên khác nhau.
- Hai toán tử cùng mức và kết hợp trái.
- Toán tử kết hợp phải.
- Toán tử non-associative.
- Ngoặc thay đổi cách nhóm.
- Toán tử một ngôi kết hợp với toán tử hai ngôi.
- Gọi hàm, truy cập thành viên và indexing kết hợp.
- Điều kiện và phép gán lồng nhau nếu DSL hỗ trợ.
- Chuỗi biểu thức dài và nhiều tầng ngoặc.
- Biểu thức không hợp lệ hoặc thiếu toán hạng.

Ví dụ bộ test:

| Source | Cấu trúc mong đợi |
|---|---|
| a + b * c | Add(a, Multiply(b, c)) |
| a * b + c | Add(Multiply(a, b), c) |
| a - b - c | Subtract(Subtract(a, b), c) |
| a ^ b ^ c | Power(a, Power(b, c)) |
| (a + b) * c | Multiply(Add(a, b), c) |
| -a * b | Multiply(Negate(a), b) |
| a < b < c | Lỗi nếu so sánh non-associative |

### 19.1. Kiểm thử AST thay vì chỉ kết quả

Nếu chỉ kiểm tra kết quả tính toán, một số lỗi precedence có thể bị che khuất bởi giá trị đầu vào đặc biệt. Ví dụ, biểu thức có toán hạng 0 hoặc 1 đôi khi cho cùng kết quả dưới nhiều cách nhóm khác nhau. Vì vậy, test AST trực tiếp giúp xác nhận parser tạo đúng cấu trúc.

Có thể kiểm tra thêm evaluation để bảo đảm AST đúng được diễn giải đúng. Hai lớp test bổ sung cho nhau:

- Parser test xác nhận cấu trúc.
- Semantic/evaluation test xác nhận hành vi của cấu trúc.

### 19.2. Kiểm thử property-based

Với parser biểu thức, có thể sinh AST ngẫu nhiên, serialize AST thành source có ngoặc cần thiết, parse lại và so sánh cấu trúc. Đây là một cách kiểm tra quan hệ giữa formatter/printer và parser.

Một thuộc tính khác là thêm ngoặc quanh một biểu thức con phải giữ nguyên ý nghĩa:

~~~text
a + b * c
a + (b * c)
~~~

Nếu ngoặc chỉ dùng để nhóm và không có tác động khác, hai source trên nên tạo AST tương đương về ngữ nghĩa.

## 20. Thông báo lỗi khi biểu thức không rõ ưu tiên

Parser nên đưa ra thông báo cụ thể khi biểu thức vi phạm quy tắc associativity hoặc thiếu ngoặc.

Ví dụ với toán tử so sánh không kết hợp:

~~~text
rules.dsl:8:19
Chained comparison is not allowed for '<'.
Write an explicit logical expression:
    (a < b) and (b < c)
~~~

Với toán tử thiếu toán hạng:

~~~text
rules.dsl:12:15
Expected an expression after '*'.
~~~

Với toán tử do người dùng định nghĩa có precedence không được biết:

~~~text
rules.dsl:4:12
Operator 'within' has no precedence declaration in this module.
Declare its precedence and associativity before using it.
~~~

Diagnostics tốt cần chỉ ra token liên quan, vị trí, quy tắc bị vi phạm và cách viết có thể sửa. Nếu parser phát hiện nhiều cách nhóm có thể xảy ra, công cụ có thể yêu cầu ngoặc thay vì tự chọn một cách hiểu không được đặc tả.

## 21. Chọn phương pháp phân tích ưu tiên cho DSL

Không có một thuật toán duy nhất phù hợp cho mọi ngôn ngữ.

| Phương pháp | Điểm mạnh | Phù hợp khi |
|---|---|---|
| Grammar phân tầng | Quy tắc hiển thị rõ trong grammar, dễ kiểm tra | Số tầng ưu tiên ổn định, parser đệ quy xuống |
| Precedence climbing | Một hàm chung, dễ dùng bảng metadata | Biểu thức có nhiều toán tử infix |
| Pratt parsing | Linh hoạt với prefix, infix, postfix và cú pháp mở rộng | DSL có biểu thức phong phú hoặc toán tử mở rộng |
| Shunting-yard | Dùng stack, có thể tạo RPN hoặc AST | Biểu thức toán học đơn giản, evaluator dạng stack |
| Precedence trong parser generator | Tận dụng công cụ LR và grammar hiện có | Dự án đã dùng parser generator hỗ trợ precedence |

Khi lựa chọn, cần cân nhắc:

- Loại parser và công nghệ hiện có.
- Số lượng toán tử và mức độ thay đổi của chúng.
- Có cho phép toán tử do người dùng định nghĩa không?
- Có nhiều dạng prefix, postfix và infix không?
- Cần diagnostics và hỗ trợ IDE ở mức nào?
- Grammar có được dùng làm tài liệu chính thức không?
- Nhóm phát triển có thể bảo trì thuật toán tự viết hay không?

Với DSL nhỏ, grammar phân tầng thường đủ rõ. Với biểu thức phong phú, Pratt parser hoặc precedence climbing có thể giảm mã lặp. Nếu đã dùng parser generator LR, khai báo precedence có thể là lựa chọn tự nhiên.

## 22. Những lỗi thiết kế thường gặp

| Lỗi | Hệ quả | Cách xử lý |
|---|---|---|
| Không định nghĩa precedence | Một chuỗi có thể có nhiều AST | Đặc tả bảng ưu tiên hoặc grammar phân tầng |
| Chỉ định precedence nhưng bỏ qua associativity | Chuỗi cùng toán tử vẫn mơ hồ | Quy định left, right hoặc non-associative |
| Dựa vào thứ tự nhánh grammar | Hành vi parser khó dự đoán và không portable | Thể hiện precedence rõ trong grammar hoặc metadata |
| Đặt mọi toán tử cùng mức | Biểu thức khó đọc và dễ nhóm sai | Phân tầng theo ngữ nghĩa |
| Không xử lý prefix và infix cùng ký hiệu | Dấu trừ hoặc ký hiệu khác bị parse sai | Phân biệt vai trò theo vị trí token |
| Coi precedence là evaluation order | Các hàm có hiệu ứng có thể chạy sai thứ tự mong đợi | Định nghĩa evaluation order riêng |
| Không xử lý chained comparison | AST có thể chứa phép so sánh không hợp lệ | Chọn non-associative hoặc định nghĩa chain semantics |
| Thay đổi precedence mà không versioning | Source cũ có thể đổi hành vi | Quản lý thay đổi ngữ nghĩa và migration |
| Chỉ test kết quả cuối | Lỗi AST có thể bị dữ liệu che khuất | Kiểm tra AST và evaluation riêng |
| Formatter không dùng cùng bảng precedence | Có thể bỏ ngoặc làm đổi nghĩa | Chia sẻ metadata precedence giữa parser và printer |

## 23. Quy trình thiết kế bảng ưu tiên

Khi thêm hoặc thay đổi toán tử, có thể thực hiện theo các bước:

1. **Liệt kê toán tử**: ghi nhận ký hiệu, dạng prefix/infix/postfix và số toán hạng.
2. **Xác định ngữ nghĩa**: toán tử thực hiện phép tính, so sánh, truy cập hay điều khiển nào?
3. **Nhóm theo mức ưu tiên**: quyết định toán tử nào cần gắn chặt hơn.
4. **Chọn associativity**: left, right hoặc non-associative.
5. **Xác định kiểu toán hạng và kiểu kết quả**: phối hợp với hệ kiểu của DSL.
6. **Xác định evaluation order**: đặc biệt với toán tử logic và biểu thức có hiệu ứng.
7. **Chọn chiến lược parser**: grammar phân tầng, precedence climbing, Pratt hoặc parser generator.
8. **Cập nhật formatter và IDE**: bảo đảm hiển thị ngoặc và hỗ trợ completion nhất quán.
9. **Viết ví dụ và AST mong đợi**: bao gồm biểu thức kết hợp nhiều nhóm toán tử.
10. **Đánh giá tương thích**: xác định thay đổi có làm đổi cách nhóm source cũ hay không.

Một bảng ưu tiên nên là nguồn thông tin thống nhất cho parser, formatter, pretty-printer, syntax highlighter và tài liệu. Nếu mỗi thành phần có một bảng riêng, cùng một biểu thức có thể được hiển thị hoặc diễn giải không nhất quán.

## 24. Tiêu chí của cơ chế phân tích ưu tiên tốt

Một cơ chế phân tích ưu tiên tốt giúp người viết dự đoán được biểu thức sẽ được nhóm như thế nào mà không phải thêm ngoặc ở mọi vị trí. Nó cũng phải cho parser một cách xác định AST duy nhất, hoặc báo lỗi khi ngôn ngữ cố ý không chấp nhận một chuỗi kết hợp.

Các câu hỏi quan trọng:

- Mỗi toán tử thuộc mức ưu tiên nào?
- Các toán tử cùng mức kết hợp trái, phải hay không kết hợp?
- Ngoặc có thể thay đổi cách nhóm ra sao?
- Toán tử một ngôi, hậu tố, gọi hàm và truy cập thành viên có thứ tự thế nào?
- Precedence có được người dùng mở rộng không?
- Thứ tự đánh giá có được định nghĩa riêng với cách nhóm không?
- Parser, formatter và IDE có dùng cùng một quy tắc không?
- Thay đổi bảng ưu tiên có ảnh hưởng source cũ không?

Phân tích ưu tiên biến một chuỗi biểu thức thành cấu trúc có ý nghĩa xác định. Khi precedence, associativity và evaluation order được phân biệt rõ, grammar không mơ hồ, parser tạo AST nhất quán và người dùng DSL có thể viết biểu thức dễ đọc, dễ dự đoán và dễ bảo trì.
