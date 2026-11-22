# Ưu tiên toán tử trong DSL

Khi một biểu thức có nhiều toán tử, bộ phân tích và bộ thực thi cần biết toán tử nào được nhóm với toán hạng trước. Quy tắc đó được gọi là **độ ưu tiên toán tử** (*operator precedence*). Nó quyết định cách hiểu cấu trúc biểu thức khi người viết không dùng dấu ngoặc để chỉ rõ thứ tự nhóm.

Ví dụ, biểu thức:

```text
2 + 3 * 4
```

có thể được hiểu là cộng 2 với kết quả nhân 3 và 4, hoặc nhân kết quả cộng 2 và 3 với 4. Nếu DSL quy định phép nhân có độ ưu tiên cao hơn phép cộng, biểu thức được hiểu là:

```text
2 + (3 * 4)
```

và cho kết quả 14. Nếu muốn cộng trước, người viết dùng dấu ngoặc:

```text
(2 + 3) * 4
```

và nhận kết quả 20.

Trong một DSL, ưu tiên toán tử là một phần của **grammar** và cách diễn giải biểu thức. Người thiết kế phải quy định rõ thứ tự ưu tiên, tính kết hợp, ý nghĩa của dấu ngoặc và cách xử lý những tổ hợp không hợp lệ. Người dùng cần có thể dự đoán cấu trúc được tạo ra từ biểu thức mình viết.

## 1. Operator precedence là gì?

**Operator precedence** là quy tắc xác định toán tử nào được liên kết với toán hạng trước khi xét những toán tử có độ ưu tiên thấp hơn trong cùng biểu thức.

Ví dụ, giả sử DSL quy định thứ tự:

1. Nhóm bằng dấu ngoặc.
2. Phép nhân và chia.
3. Phép cộng và trừ.

Khi đó:

```text
10 + 6 / 2 * 3
```

được nhóm thành:

```text
10 + ((6 / 2) * 3)
```

Phép chia và phép nhân có cùng mức ưu tiên, nên thứ tự giữa chúng được xác định thêm bởi **associativity** (tính kết hợp). Nếu chúng kết hợp trái, phép chia được thực hiện trước theo cấu trúc từ trái sang phải.

Độ ưu tiên không phải là tốc độ thực thi hay mức độ quan trọng của toán tử. Nó là quy tắc cấu trúc cho biết biểu thức được nhóm như thế nào.

### Vì sao cần quy tắc ưu tiên?

Nếu không có quy tắc ưu tiên hoặc quy tắc nhóm rõ ràng, một biểu thức có thể có nhiều cách phân tích cú pháp. Điều này gây ra:

- Người viết không biết biểu thức có ý nghĩa nào.
- Hai bộ xử lý DSL có thể tạo ra cây cú pháp khác nhau.
- Validator và runtime có thể hiểu không nhất quán.
- Thông báo lỗi và công cụ hỗ trợ khó giải thích biểu thức.
- Người dùng phải thêm dấu ngoặc ở mọi vị trí, khiến cú pháp dài và khó đọc.

Một bảng ưu tiên được định nghĩa rõ giúp ngôn ngữ ngắn gọn nhưng vẫn có cách hiểu xác định.

## 2. Precedence, associativity và grouping

Ba khái niệm này phối hợp để xác định cấu trúc biểu thức.

### 2.1. Precedence – độ ưu tiên

Precedence quyết định nhóm toán tử nào được xét trước. Ví dụ, nếu `*` có độ ưu tiên cao hơn `+`, biểu thức `a + b * c` được hiểu là `a + (b * c)`.

### 2.2. Associativity – tính kết hợp

Associativity quyết định cách nhóm các toán tử có cùng mức ưu tiên khi chúng xuất hiện liên tiếp.

**Kết hợp trái (left-associative):**

```text
a - b - c
```

được nhóm thành:

```text
(a - b) - c
```

Nếu a = 10, b = 3 và c = 2, kết quả là 5.

**Kết hợp phải (right-associative):**

```text
a = b = c
```

trong một ngôn ngữ có phép gán kết hợp phải có thể được nhóm thành:

```text
a = (b = c)
```

Ý nghĩa cụ thể phụ thuộc vào semantics của phép gán trong DSL. Không phải mọi DSL đều cho phép phép gán chuỗi.

**Không kết hợp (non-associative):**

Một số toán tử không được phép xuất hiện liên tiếp ở cùng mức nếu không có dấu ngoặc. Ví dụ, DSL có thể từ chối:

```text
a < b < c
```

và yêu cầu người viết diễn đạt rõ:

```text
(a < b) AND (b < c)
```

hoặc dùng một cú pháp so sánh chuỗi được định nghĩa riêng. Việc từ chối giúp tránh hiểu nhầm rằng biểu thức có nghĩa như trong toán học hoặc trong một ngôn ngữ khác.

### 2.3. Grouping – nhóm biểu thức

Grouping xác định các toán hạng và toán tử thuộc cùng một biểu thức con. Dấu ngoặc thường được dùng để chỉ định nhóm một cách tường minh.

Ví dụ:

```text
a + b * c
(a + b) * c
a + (b * c)
```

Ba biểu thức có thể tạo ra các cây cú pháp khác nhau. Dấu ngoặc giúp người viết ghi rõ ý định và thường có ưu tiên cao nhất trong biểu thức.

### Bảng phân biệt

| Khái niệm | Câu hỏi được trả lời | Ví dụ |
|---|---|---|
| Precedence | Toán tử nào nhóm trước? | `*` so với `+` |
| Associativity | Nhóm từ trái hay phải khi cùng mức? | `a - b - c` |
| Grouping | Thành phần nào thuộc cùng biểu thức con? | `(a + b) * c` |

## 3. Độ ưu tiên không giống thứ tự thực thi

Precedence xác định cấu trúc biểu thức, thường được biểu diễn bằng AST. Nó không tự quyết định mọi chi tiết về thời điểm tính toán hoặc thứ tự có tác dụng phụ.

Ví dụ, nếu DSL cho phép lời gọi hàm:

```text
loadA() + loadB() * loadC()
```

độ ưu tiên có thể xác định AST là phép cộng có vế phải là phép nhân. Tuy nhiên, thứ tự gọi loadA, loadB và loadC còn phụ thuộc vào quy tắc evaluation của DSL.

Một DSL thuần biểu thức có thể quy định thứ tự đánh giá từ trái sang phải. Một DSL khác có thể cho phép tối ưu hóa hoặc đánh giá lười. Vì vậy, đặc tả cần tách:

- **Cấu trúc cú pháp:** toán tử và toán hạng được nhóm như thế nào.
- **Ngữ nghĩa đánh giá:** biểu thức con được tính khi nào và theo thứ tự nào.
- **Ngữ nghĩa tác dụng phụ:** lời gọi hàm, cập nhật trạng thái hoặc truy cập tài nguyên có thể xảy ra theo thứ tự nào.

Không nên suy luận thứ tự thực thi chỉ từ bảng precedence.

## 4. Các nhóm toán tử và thứ tự ưu tiên thường gặp

Không có một thứ tự ưu tiên duy nhất áp dụng cho mọi DSL. Mỗi ngôn ngữ cần định nghĩa bảng riêng theo mục tiêu miền và cách người dùng mong đợi biểu thức hoạt động.

Một DSL biểu thức tổng quát có thể chọn thứ tự minh họa sau, từ ưu tiên cao xuống thấp:

| Mức | Nhóm toán tử | Ví dụ | Associativity minh họa |
|---:|---|---|---|
| 1 | Nhóm trong ngoặc, truy cập thành viên, gọi hàm | `(x)`, `order.total`, `f(x)` | Theo cấu trúc |
| 2 | Toán tử một ngôi | `!x`, `-x`, `NOT x` | Phải |
| 3 | Lũy thừa | `x ** y` | Phải |
| 4 | Nhân, chia, chia lấy dư | `*`, `/`, `%` | Trái |
| 5 | Cộng, trừ | `+`, `-` | Trái |
| 6 | So sánh | `<`, `<=`, `>`, `>=` | Không kết hợp |
| 7 | Bằng, khác | `==`, `!=` | Không kết hợp |
| 8 | AND | `AND`, `&&` | Trái |
| 9 | OR | `OR`, `||` | Trái |
| 10 | Điều kiện ba ngôi | `condition ? a : b` | Thường phải |
| 11 | Gán | `=`, `+=` | Thường phải |

Bảng này chỉ là ví dụ thiết kế. Một DSL truy vấn, chính sách hoặc cấu hình có thể không hỗ trợ lũy thừa, gán hoặc toán tử ba ngôi. Một số ngôn ngữ đặt phép NOT ở mức khác hoặc có các toán tử so sánh chuỗi, tập hợp và null riêng.

### 4.1. Toán tử một ngôi (unary operators)

Toán tử một ngôi nhận một toán hạng. Ví dụ:

```text
-amount
NOT active
!enabled
```

DSL cần xác định toán tử một ngôi có thể kết hợp với những biểu thức nào và ưu tiên của nó so với toán tử khác. Ví dụ, nếu dấu trừ một ngôi có ưu tiên cao hơn phép lũy thừa thì `-2 ** 2` có thể được nhóm thành `(-2) ** 2`. Nếu lũy thừa ưu tiên cao hơn, nó có thể được nhóm thành `-(2 ** 2)`. Không nên dựa vào thói quen của ngôn ngữ khác; đặc tả phải nói rõ.

### 4.2. Toán tử số học

Nhân, chia và chia lấy dư thường được đặt ưu tiên cao hơn cộng và trừ. Ví dụ:

```text
base + quantity * unitPrice
```

được nhóm thành:

```text
base + (quantity * unitPrice)
```

Điều này hữu ích trong DSL tính giá, biểu thức tài chính hoặc công thức dữ liệu. Nếu các toán tử có cùng mức, associativity tiếp tục quyết định cách nhóm.

### 4.3. Toán tử so sánh

Toán tử so sánh thường tạo ra giá trị Boolean:

```text
age >= 18
status == "ACTIVE"
price != 0
```

Nhiều DSL xem các toán tử so sánh là không kết hợp. Do đó, biểu thức `a < b < c` cần bị từ chối hoặc phải có semantics riêng. Nếu muốn hỗ trợ so sánh chuỗi, đặc tả cần định nghĩa rõ việc so sánh có nghĩa là `(a < b) AND (b < c)` hay một phép toán khác.

### 4.4. Toán tử logic

Toán tử logic kết hợp các điều kiện Boolean. Một quy tắc phổ biến là NOT ưu tiên hơn AND, còn AND ưu tiên hơn OR:

```text
NOT blocked AND active OR admin
```

được nhóm thành:

```text
((NOT blocked) AND active) OR admin
```

Nếu ý định là điều kiện phải có active và một trong hai trường hợp không bị chặn hoặc là admin, người viết nên dùng:

```text
active AND (NOT blocked OR admin)
```

Dấu ngoặc giúp biểu đạt ý định rõ ràng và tránh phụ thuộc vào việc người đọc có nhớ bảng ưu tiên hay không.

### 4.5. Toán tử điều kiện và gán

Một DSL có thể cung cấp toán tử điều kiện ba ngôi để chọn một trong hai giá trị:

```text
discount = isMember ? 10 : 0
```

Trong DSL hỗ trợ phép gán, cần xác định phép gán có ưu tiên thấp hơn các phép tính và kết hợp phải hay không. Một số DSL khai báo thuần túy không có phép gán biểu thức; thay vào đó, chúng dùng cú pháp thuộc tính như `discount = 10` trong một block.

## 5. Biểu diễn ưu tiên bằng cây cú pháp

Parser thường biểu diễn biểu thức bằng **Abstract Syntax Tree (AST)**. Mỗi toán tử trở thành một nút, các toán hạng hoặc biểu thức con trở thành các nút con.

Với biểu thức:

```text
a + b * c
```

nếu phép nhân ưu tiên cao hơn phép cộng, AST có dạng:

```text
       Add
      /   \
     a    Multiply
          /      \
         b        c
```

Cấu trúc này thể hiện phép nhân được nhóm trước. Một biểu thức có dấu ngoặc:

```text
(a + b) * c
```

sẽ tạo AST khác:

```text
      Multiply
      /      \
    Add       c
   /   \
  a     b
```

AST giúp các giai đoạn sau hiểu cấu trúc mà không cần suy luận lại từ chuỗi ký tự. Interpreter có thể đánh giá nút con trước theo semantics; compiler có thể chuyển cây sang biểu diễn trung gian hoặc mã đích.

### Parse tree và AST

Parse tree thường thể hiện chi tiết quá trình áp dụng grammar, bao gồm các non-terminal trung gian. AST tập trung vào cấu trúc có ý nghĩa và thường loại bỏ một số nút cú pháp không cần thiết.

Cả hai đều có thể thể hiện grouping, nhưng AST thường thuận tiện hơn cho kiểm tra kiểu, tối ưu hóa và thực thi.

## 6. Dấu ngoặc và cách ghi rõ ý định

Dấu ngoặc là cơ chế nhóm biểu thức tường minh. Trong hầu hết DSL biểu thức, dấu ngoặc đơn có ưu tiên cao hơn các toán tử nhị phân bên trong.

Ví dụ:

```text
total * (1 - discountRate)
```

cho biết phải tính phần `1 - discountRate` trước khi nhân với total.

Dấu ngoặc hữu ích trong các trường hợp:

- Biểu thức có nhiều nhóm toán tử.
- Người viết muốn nhấn mạnh cấu trúc nghiệp vụ.
- Biểu thức có toán tử cùng mức nhưng cách nhóm không hiển nhiên.
- Một biểu thức được đưa vào tài liệu, review hoặc cần bảo trì lâu dài.
- Có khả năng người đọc quen với precedence của một ngôn ngữ khác.

Không nên bắt buộc người dùng đặt ngoặc quanh mọi phép toán nếu grammar đã rõ ràng. Tuy nhiên, ví dụ và hướng dẫn phong cách có thể khuyến khích dùng ngoặc khi biểu thức dài hoặc có nhiều lớp logic.

### Dấu ngoặc không sửa được lỗi kiểu hoặc lỗi ngữ nghĩa

Ví dụ:

```text
(order.total + "shipping") * 2
```

Dấu ngoặc có thể làm rõ grouping, nhưng nếu `order.total` là Decimal và `"shipping"` là String, biểu thức vẫn có thể sai kiểu. Grouping giải quyết cấu trúc; type checking và semantic analysis giải quyết tính hợp lệ.

## 7. Cách mô tả precedence trong grammar

Một cách phổ biến là chia biểu thức thành nhiều mức non-terminal. Mỗi mức đại diện cho một nhóm ưu tiên. Mức có ưu tiên cao hơn được dùng làm thành phần bên trong mức thấp hơn.

Ví dụ, grammar EBNF rút gọn cho biểu thức số học:

```ebnf
expression  = term, { ("+" | "-"), term } ;
term        = factor, { ("*" | "/"), factor } ;
factor      = number | identifier | "(", expression, ")" ;
```

Ở đây:

- expression xử lý phép cộng và trừ.
- term xử lý phép nhân và chia.
- factor xử lý số, định danh và biểu thức trong ngoặc.
- expression chứa term, nên phép nhân và chia được nhóm trước phép cộng và trừ.

Với biểu thức `a + b * c`, parser nhận `a` như factor, sau đó nhận `b * c` như term, rồi tạo expression cộng hai phần.

### 7.1. Grammar nhiều tầng và associativity

Grammar ở trên dùng lặp trái để biểu diễn nhóm trái. Có thể viết một cấu trúc tương tự bằng đệ quy trái:

```ebnf
expression = expression, ("+" | "-"), term
           | term ;
term       = term, ("*" | "/"), factor
           | factor ;
factor     = number | identifier | "(", expression, ")" ;
```

Đây là cách diễn đạt tự nhiên trong một số loại parser, đặc biệt parser LR. Với recursive descent parser thuần, đệ quy trái trực tiếp có thể gây gọi lặp vô hạn; người triển khai thường chuyển nó thành vòng lặp như grammar đầu tiên.

Với toán tử kết hợp phải, cấu trúc grammar có thể dùng đệ quy phải:

```ebnf
assignment = identifier, "=", assignment
           | conditional ;
```

Grammar minh họa trên cho phép một chuỗi phép gán được nhóm từ phải sang trái. Đặc tả vẫn cần định nghĩa kiểu và semantics của phép gán.

### 7.2. Vì sao chia tầng hoạt động?

Mỗi tầng chỉ kết hợp các toán tử thuộc một mức ưu tiên. Tầng thấp hơn nhận các biểu thức đã được phân tích ở tầng cao hơn làm toán hạng.

Ví dụ, nếu grammar quy định:

- expression chứa term,
- term chứa factor,
- factor chứa primary,

thì toán tử ở term không thể kéo một biểu thức expression đầy đủ vào làm toán hạng trừ khi có dấu ngoặc. Cách tổ chức này tạo ra cấu trúc ưu tiên mà không cần một bước sắp xếp toán tử riêng.

## 8. Các thuật toán phân tích biểu thức

Ngoài việc viết grammar nhiều tầng, parser có thể xử lý precedence bằng các thuật toán chuyên biệt.

### 8.1. Recursive descent với nhiều tầng

Mỗi mức ưu tiên có một hàm phân tích riêng. Hàm expression gọi term; term gọi factor; factor xử lý literal, định danh, lời gọi hoặc biểu thức trong ngoặc.

Ví dụ mã giả:

```text
parseExpression():
    node = parseTerm()
    while nextToken is "+" or "-":
        op = consume()
        right = parseTerm()
        node = Binary(op, node, right)
    return node

parseTerm():
    node = parseFactor()
    while nextToken is "*" or "/":
        op = consume()
        right = parseFactor()
        node = Binary(op, node, right)
    return node
```

Vòng lặp cập nhật node bằng cách đặt node hiện tại ở bên trái. Vì vậy, các toán tử cùng tầng được nhóm trái. Đây là cách dễ hiểu và dễ kiểm soát cho DSL có số mức ưu tiên vừa phải.

### 8.2. Precedence climbing

**Precedence climbing** là thuật toán phân tích biểu thức dựa trên mức ưu tiên tối thiểu mà một lời gọi parser chấp nhận. Parser đọc một toán hạng trái, sau đó tiếp tục nhận toán tử nếu toán tử có precedence đủ cao. Nó gọi đệ quy để phân tích toán hạng phải với ngưỡng phù hợp.

Ý tưởng tổng quát:

```text
parseExpression(minPrecedence):
    left = parsePrefix()

    while next token is an infix operator
          and precedence(next token) >= minPrecedence:
        op = consume()
        nextMin = precedence(op) + 1
        right = parseExpression(nextMin)
        left = Binary(op, left, right)

    return left
```

Mã giả trên minh họa trường hợp toán tử nhị phân kết hợp trái. Với toán tử kết hợp phải, cách tính nextMin cần khác để cho phép toán tử cùng mức đi vào toán hạng phải. Một triển khai tổng quát thường lưu cả precedence và associativity trong bảng thông tin toán tử.

Ưu điểm của precedence climbing là có thể xử lý nhiều mức ưu tiên mà không cần một hàm riêng cho từng mức. Nó phù hợp với DSL biểu thức có bảng toán tử tương đối rõ ràng.

### 8.3. Pratt parser

**Pratt parser**, còn gọi là top-down operator precedence parser, phân tích biểu thức bằng cách gắn quy tắc cho token ở vị trí tiền tố và trung tố. Mỗi toán tử có binding power hoặc mức liên kết để quyết định biểu thức bên phải được phép mở rộng đến đâu.

Pratt parser hữu ích khi DSL có nhiều dạng biểu thức:

- Prefix: `-x`, `NOT x`.
- Infix: `a + b`, `a AND b`.
- Postfix: `value!` hoặc toán tử hậu tố do DSL định nghĩa.
- Call: `f(x)`.
- Member access: `order.total`.
- Indexing: `items[0]`.

Mỗi loại token có thể định nghĩa hàm xử lý ở vị trí đầu biểu thức (*nud*) hoặc sau một biểu thức đã có (*led*). Cách tổ chức này linh hoạt khi ngôn ngữ cần mở rộng biểu thức theo thời gian.

### 8.4. Shunting-yard algorithm

**Shunting-yard** là thuật toán chuyển biểu thức trung tố (*infix*) thành biểu thức hậu tố (*postfix*) hoặc trực tiếp tạo cây biểu thức. Thuật toán dùng một stack toán tử và một đầu ra để sắp xếp toán tử theo precedence và associativity.

Ví dụ:

```text
a + b * c
```

có thể chuyển thành:

```text
a b c * +
```

Trong biểu thức hậu tố, toán tử xuất hiện sau các toán hạng. Khi gặp toán tử, thuật toán so sánh độ ưu tiên và tính kết hợp với toán tử trên đỉnh stack để quyết định đẩy ra hay giữ lại.

Shunting-yard hữu ích cho bộ tính biểu thức nhỏ, DSL công thức hoặc máy tính biểu thức. Với ngôn ngữ có cấu trúc phức tạp như block, khai báo và kiểu dữ liệu phong phú, parser theo grammar thường phù hợp hơn để quản lý toàn bộ cú pháp.

### So sánh các cách tiếp cận

| Cách tiếp cận | Ý tưởng | Phù hợp khi |
|---|---|---|
| Grammar nhiều tầng | Mỗi mức ưu tiên có một non-terminal | Ngôn ngữ nhỏ đến vừa, muốn grammar dễ đọc |
| Recursive descent | Hàm parser theo từng mức | Cần kiểm soát cú pháp và thông báo lỗi |
| Precedence climbing | Dùng ngưỡng ưu tiên trong parser biểu thức | Nhiều toán tử nhị phân và bảng ưu tiên rõ |
| Pratt parser | Binding power và handler theo loại token | Biểu thức đa dạng, cần mở rộng linh hoạt |
| Shunting-yard | Stack toán tử để chuyển infix sang postfix | Bộ tính biểu thức hoặc DSL công thức |

Không có thuật toán nào tự định nghĩa semantics cho DSL. Chúng chỉ giúp xây dựng cấu trúc theo các quy tắc ưu tiên đã được đặc tả.


## 9. Ví dụ phân tích biểu thức từ đầu đến cuối

Giả sử DSL chính sách bán hàng hỗ trợ các toán tử:

- So sánh: `>`, `>=`, `==`.
- Số học: `+`, `-`, `*`, `/`.
- Logic: `NOT`, `AND`, `OR`.

Đặc tả quy định:

1. Dấu ngoặc và truy cập thuộc tính có ưu tiên cao nhất.
2. NOT đứng trên AND.
3. AND đứng trên OR.
4. Nhân và chia đứng trên cộng và trừ.
5. So sánh được nhóm trước các toán tử logic.
6. Các phép so sánh không kết hợp; số học cùng mức kết hợp trái.

Xét biểu thức:

```text
customer.active AND order.total >= 500000 OR customer.isVip
```

Theo precedence đã quy định, cấu trúc được nhóm thành:

```text
(customer.active AND (order.total >= 500000)) OR customer.isVip
```

Có thể mô tả AST rút gọn:

```text
                 OR
               /    \
             AND   isVip
            /   \
       active   GreaterThanOrEqual
                 /            \
             order.total      500000
```

Giả sử customer.active là true, order.total là 300000 và customer.isVip là false:

- So sánh order.total >= 500000 cho kết quả false.
- customer.active AND false cho kết quả false.
- false OR customer.isVip cho kết quả false.

Nếu customer.isVip là true, toàn biểu thức sẽ true dù tổng đơn chưa đạt 500000.

### Khi muốn thay đổi grouping

Nếu yêu cầu nghiệp vụ là khách hàng phải đang hoạt động và đồng thời là thành viên VIP hoặc có đơn đạt ngưỡng, biểu thức cần được viết:

```text
customer.active AND (customer.isVip OR order.total >= 500000)
```

Dấu ngoặc làm rõ nhánh OR nằm bên trong điều kiện AND. Cùng các toán tử và biến, nhưng grouping khác dẫn đến kết quả có thể khác.

## 10. Ưu tiên toán tử trong DSL chuyên biệt

Không phải DSL nào cũng cần bảng toán tử giống ngôn ngữ lập trình. Các toán tử nên phản ánh miền và loại biểu thức mà người dùng thường viết.

### 10.1. DSL truy vấn

Một DSL truy vấn có thể hỗ trợ:

- Toán tử so sánh: `==`, `!=`, `>`.
- Kiểm tra tập hợp: `IN`, `NOT IN`.
- Kiểm tra tồn tại: `EXISTS`.
- Logic: `NOT`, `AND`, `OR`.
- Truy cập trường hoặc đường dẫn: `customer.address.city`.

Ví dụ:

```text
status == "PAID"
AND amount >= 100000
AND region IN ["HN", "HCM"]
```

DSL cần quy định rõ `IN` có cùng precedence với so sánh khác hay có mức riêng, cũng như cách nhóm `NOT IN`.

### 10.2. DSL tính giá

Một DSL tính giá có thể hỗ trợ đơn vị tiền, phần trăm, phép nhân, làm tròn và thuế:

```text
subtotal + subtotal * taxRate - discount
```

Bên cạnh precedence, DSL phải xác định kiểu tiền tệ, độ chính xác số thập phân, thứ tự làm tròn và đơn vị của tỷ lệ. Cây cú pháp đúng chưa đủ để bảo đảm kết quả nghiệp vụ chính xác nếu semantics số học không rõ.

### 10.3. DSL điều kiện chính sách

Một DSL chính sách có thể dùng từ khóa miền như `MATCHES`, `CONTAINS`, `IS NULL` hoặc `BETWEEN`. Cần xác định các từ khóa nhiều token này được lexer nhận diện ra sao và precedence của chúng so với toán tử logic.

Ví dụ:

```text
country == "VN"
AND age BETWEEN 18 AND 60
AND email MATCHES ".*@example.com"
```

Nếu `BETWEEN` dùng từ khóa `AND` bên trong cú pháp của nó, grammar phải phân biệt `AND` thuộc cặp biên của BETWEEN với toán tử AND nối điều kiện. Đây là ví dụ cho thấy thiết kế grammar phải tính đến xung đột giữa từ khóa của miền và toán tử logic.

## 11. Toán tử tùy chỉnh và mở rộng precedence

Một DSL có thể cho phép định nghĩa toán tử riêng, ví dụ toán tử hợp nhất giá trị, kiểm tra quyền hoặc so khớp mẫu. Khi hỗ trợ toán tử tùy chỉnh, hệ thống cần quy định:

- Ký hiệu hoặc tên toán tử hợp lệ.
- Số lượng toán hạng: unary, binary hay nhiều toán hạng.
- Precedence.
- Associativity.
- Kiểu dữ liệu được phép sử dụng.
- Semantics và hành vi lỗi.
- Khả năng overload theo kiểu, nếu có.

Ví dụ, DSL truy vấn có thể định nghĩa toán tử `contains` cho chuỗi và danh sách. Nhưng cùng tên toán tử có thể có semantics khác nhau theo kiểu dữ liệu. Cần quy định rõ để không gây bất ngờ.

### Có nên cho người dùng tự đặt precedence?

Cho phép người dùng định nghĩa precedence có thể hữu ích trong một ngôn ngữ mở rộng, nhưng làm tăng đáng kể độ phức tạp:

- Cùng một biểu thức có thể được hiểu khác nhau tùy cấu hình.
- Editor và formatter phải biết bảng ưu tiên hiện hành.
- Tài liệu và thông báo lỗi phải phụ thuộc vào định nghĩa toán tử.
- Các module có thể xung đột khi khai báo cùng ký hiệu hoặc cùng mức ưu tiên.
- Việc nâng cấp định nghĩa toán tử có thể thay đổi AST của mã cũ.

Với DSL hướng đến chuyên gia miền, bảng precedence cố định và được tài liệu hóa thường dễ học, dễ review và dễ bảo trì hơn. Chỉ nên cho phép mở rộng nếu đó là nhu cầu cốt lõi của miền.

## 12. Ambiguity – sự mơ hồ trong biểu thức

**Ambiguity** xảy ra khi một chuỗi đầu vào có thể tạo ra nhiều cây phân tích cú pháp hợp lệ. Precedence và associativity là hai công cụ giúp giảm mơ hồ, nhưng grammar còn có thể mơ hồ vì nhiều lý do khác.

Ví dụ:

```text
a < b < c
```

Nếu grammar cho phép lặp toán tử so sánh mà không quy định grouping, có thể có hai cách phân tích:

- `(a < b) < c`
- `a < (b < c)`

Hai cấu trúc này thường không hợp lý nếu kết quả phép so sánh là Boolean và toán hạng tiếp theo là số. DSL có thể giải quyết bằng cách quy định toán tử so sánh không kết hợp và từ chối biểu thức này.

Một ví dụ khác là dấu trừ:

```text
a - b - c
```

Nếu không quy định associativity, parser có thể tạo cây nhóm trái hoặc nhóm phải. Đặt phép trừ là left-associative sẽ loại bỏ mơ hồ này.

### Precedence không giải quyết mọi loại mơ hồ

Một grammar có thể mơ hồ do:

- Từ khóa cũng có thể được dùng làm identifier.
- Token nhiều ký tự có thể xung đột với token ngắn.
- Cú pháp lời gọi hàm và nhóm biểu thức có dạng giống nhau.
- Một từ khóa miền có thể xuất hiện như một phần của biểu thức.
- Các cấu trúc optional khiến parser không biết phần nào thuộc mệnh đề hiện tại.

Các vấn đề này cần giải quyết bằng thiết kế token, grammar, quy tắc từ khóa và đôi khi bằng cách thay đổi cú pháp.

### Tokenization và toán tử dài nhất

Nếu DSL có cả `>` và `>=`, lexer thường cần nhận diện toán tử dài nhất hợp lệ trước. Nếu không, `>=` có thể bị tách thành `>` và `=`, gây lỗi phân tích.

Đặc tả lexical rules cần nêu rõ cách nhận diện toán tử, từ khóa nhiều ký tự và xung đột với identifier.

## 13. Short-circuit và precedence là hai vấn đề khác nhau

Với toán tử logic AND và OR, nhiều ngôn ngữ hỗ trợ **short-circuit evaluation**: nếu kết quả đã xác định từ toán hạng bên trái, toán hạng bên phải có thể không được đánh giá.

Ví dụ, với AND:

```text
isAuthenticated AND hasPermission()
```

nếu isAuthenticated là false, DSL có thể không gọi hasPermission(). Điều này có thể tránh thao tác không cần thiết hoặc lỗi khi truy cập dữ liệu không sẵn có.

Với OR:

```text
isAdmin OR hasPermission()
```

nếu isAdmin là true, DSL có thể không cần đánh giá vế phải.

Precedence chỉ quyết định cách nhóm:

```text
a OR b AND c
```

có thể được nhóm thành:

```text
a OR (b AND c)
```

Short-circuit lại quyết định biểu thức con nào có được đánh giá hay không và theo thứ tự nào. Đặc tả cần mô tả cả hai nếu DSL có biểu thức logic.

Nếu biểu thức có tác dụng phụ, short-circuit có thể ảnh hưởng đến hành vi. Vì vậy, DSL cần quy định liệu biểu thức điều kiện có được phép gọi hàm làm thay đổi trạng thái hay chỉ được phép đọc dữ liệu.


## 14. Khai báo precedence trong parser generator

Một số công cụ sinh parser cho phép khai báo precedence và associativity trực tiếp thay vì phải viết lại grammar thành nhiều tầng. Cách khai báo cụ thể tùy công cụ, nhưng ý tưởng thường gồm:

- Khai báo các nhóm toán tử theo thứ tự ưu tiên.
- Đánh dấu nhóm kết hợp trái, phải hoặc không kết hợp.
- Gắn quy tắc ưu tiên với token hoặc production.
- Dùng thông tin này để giải quyết một số xung đột parsing.

Ví dụ theo phong cách khai báo thường gặp trong họ công cụ Yacc/Bison:

```text
%left '+' '-'
%left '*' '/'
%right '^'
%nonassoc '<' '>' LE GE
```

Các khai báo precedence thường được đọc từ thấp đến cao trong nhiều công cụ thuộc họ này: nhóm khai báo sau có mức ưu tiên cao hơn. Tuy nhiên, phải kiểm tra tài liệu của parser generator cụ thể vì cú pháp và quy tắc áp dụng có thể khác.

Với grammar biểu thức có dạng đệ quy:

```text
expr:
      expr '+' expr
    | expr '*' expr
    | NUMBER
    ;
```

parser generator có thể gặp xung đột shift/reduce khi không biết nên tiếp tục đọc toán tử hay rút gọn biểu thức hiện tại. Khai báo precedence có thể giúp chọn hành động phù hợp.

### Shift/reduce conflict

- **Shift:** đọc token tiếp theo và tiếp tục mở rộng cấu trúc.
- **Reduce:** rút gọn chuỗi token hiện tại theo một production đã nhận diện.

Với biểu thức `a + b * c`, khi parser đã đọc `a + b` và nhìn thấy `*`, nó cần biết nên rút gọn `a + b` trước hay tiếp tục đọc phép nhân. Nếu `*` có precedence cao hơn `+`, parser nên shift để nhận đủ vế nhân trước.

Không nên dùng khai báo precedence chỉ để làm biến mất cảnh báo mà không hiểu cấu trúc được chọn. Người thiết kế cần kiểm tra AST được tạo ra và bảo đảm nó khớp với semantics mong muốn.

## 15. Thiết kế precedence dễ học và dễ bảo trì

Một bảng ưu tiên tốt nên nhất quán, có lý do và phù hợp với người dùng của DSL.

### Giữ số mức vừa đủ

Nếu có quá nhiều mức precedence, người dùng khó ghi nhớ. Chỉ nên tách mức khi có sự khác biệt thực sự về cách nhóm hoặc semantics. Những toán tử thường được dùng cùng nhau có thể nằm cùng mức nếu associativity phù hợp.

### Dùng quy ước quen thuộc khi có lợi

Với DSL có phép toán số học và logic, các quy ước phổ biến có thể giúp người dùng đọc nhanh hơn. Tuy nhiên, không nên sao chép bảng precedence của Java, Python hoặc SQL một cách máy móc. DSL có mục tiêu và semantics riêng.

### Tài liệu hóa bằng bảng và ví dụ

Tài liệu nên trình bày:

- Nhóm toán tử theo thứ tự ưu tiên.
- Associativity của từng nhóm.
- Những toán tử không được kết hợp.
- Cách dấu ngoặc ảnh hưởng đến grouping.
- Ví dụ có và không có dấu ngoặc.
- Các biểu thức bị từ chối và lý do.

### Không để semantics ẩn sau cú pháp

Hai toán tử cùng mức có thể khác nhau về kiểu dữ liệu, phép so sánh null hoặc short-circuit. Bảng precedence không thay thế tài liệu ngữ nghĩa.

### Duy trì tính nhất quán giữa các công cụ

Editor, formatter, parser, validator, interpreter và compiler phải dùng cùng quy tắc. Nếu formatter thêm dấu ngoặc theo một bảng ưu tiên nhưng runtime dùng bảng khác, công cụ có thể thay đổi ý nghĩa biểu thức.

Một cách tốt là định nghĩa bảng toán tử ở một nguồn chung hoặc sinh các thành phần liên quan từ cùng một đặc tả.

## 16. Kiểm thử precedence

Kiểm thử cần xác nhận AST hoặc kết quả đánh giá tương ứng với từng quy tắc, không chỉ kiểm tra parser có chấp nhận biểu thức.

Các nhóm trường hợp nên có:

1. **Khác mức ưu tiên:** xác nhận toán tử ưu tiên cao được nhóm trước.
2. **Cùng mức, kết hợp trái:** xác nhận cấu trúc từ trái sang phải.
3. **Cùng mức, kết hợp phải:** xác nhận cấu trúc từ phải sang trái.
4. **Không kết hợp:** xác nhận chuỗi toán tử bị từ chối khi đặc tả yêu cầu.
5. **Dấu ngoặc:** xác nhận nhóm tường minh ghi đè precedence mặc định.
6. **Unary và binary:** xác nhận dấu trừ một ngôi không bị nhầm với phép trừ.
7. **Toán tử logic:** xác nhận thứ tự NOT, AND và OR.
8. **Toán tử nhiều ký tự:** xác nhận lexer nhận diện đúng toán tử dài nhất.
9. **Lời gọi và truy cập thuộc tính:** xác nhận precedence của call, member access và indexing.
10. **Lỗi cú pháp:** xác nhận thông báo khi thiếu toán hạng hoặc dấu ngoặc.

### Ví dụ bộ kiểm thử

Giả sử DSL quy định nhân ưu tiên hơn cộng, các phép số học cùng mức kết hợp trái và so sánh không kết hợp:

| Biểu thức | Kết quả mong đợi |
|---|---|
| `2 + 3 * 4` | AST nhóm thành `2 + (3 * 4)` |
| `(2 + 3) * 4` | AST nhóm phần cộng trước |
| `10 - 3 - 2` | AST nhóm thành `(10 - 3) - 2` |
| `a < b < c` | Báo lỗi nếu so sánh không kết hợp |
| `a +` | Báo lỗi thiếu toán hạng |
| `(a + b` | Báo lỗi thiếu dấu đóng ngoặc |

Với các biểu thức logic, nên kiểm tra cả AST lẫn kết quả với nhiều tổ hợp true/false. Nếu có short-circuit, cần kiểm tra cả việc toán hạng bên phải có được đánh giá hay không.

## 17. Những nhầm lẫn thường gặp

**Cho rằng mọi DSL dùng cùng một bảng precedence.** Mỗi DSL phải định nghĩa quy tắc phù hợp với miền. Thói quen từ ngôn ngữ khác không phải là đặc tả.

**Nhầm precedence với associativity.** Precedence so sánh các nhóm toán tử khác mức; associativity quyết định cách nhóm các toán tử cùng mức.

**Cho rằng dấu ngoặc chỉ để trang trí.** Dấu ngoặc làm thay đổi grouping và có thể thay đổi kết quả biểu thức.

**Cho rằng precedence xác định thứ tự thực thi.** Precedence tạo cấu trúc AST; thứ tự đánh giá và tác dụng phụ thuộc semantics riêng.

**Cho rằng grammar đúng là biểu thức hợp lệ về nghiệp vụ.** Parser có thể tạo AST thành công nhưng type checker hoặc semantic analyzer vẫn có thể từ chối biểu thức.

**Cho rằng toán tử so sánh luôn kết hợp được.** Biểu thức so sánh chuỗi có thể gây lỗi kiểu hoặc mơ hồ. DSL cần quyết định rõ hỗ trợ, diễn giải hay từ chối.

**Dùng precedence declaration để che mọi xung đột parser.** Một số xung đột phản ánh grammar mơ hồ hoặc thiết kế cú pháp chưa tốt. Cần hiểu nguyên nhân và kiểm tra cây cú pháp sau khi giải quyết.

**Để editor và runtime dùng bảng ưu tiên khác nhau.** Sự không nhất quán có thể khiến người dùng thấy một cách nhóm trong editor nhưng runtime lại thực thi theo cách khác.

## 18. Quy trình xác định precedence cho một DSL

Khi thiết kế grammar hoặc bổ sung toán tử, có thể làm theo trình tự:

1. Liệt kê các toán tử mà miền thực sự cần.
2. Xác định số lượng toán hạng và kiểu toán tử: prefix, infix hoặc postfix.
3. Nhóm các toán tử theo cách chúng cần liên kết với toán hạng.
4. Quy định precedence giữa các nhóm.
5. Quy định associativity cho từng nhóm.
6. Xác định toán tử nào không được phép kết hợp liên tiếp.
7. Định nghĩa cách dấu ngoặc nhóm biểu thức.
8. Viết grammar hoặc cấu hình parser theo các quy tắc đó.
9. Kiểm tra AST được tạo ra bằng các biểu thức đại diện.
10. Định nghĩa riêng thứ tự evaluation và short-circuit nếu có.
11. Đồng bộ parser, validator, formatter, editor và runtime.
12. Tài liệu hóa bảng ưu tiên và kiểm thử các trường hợp biên.

Nếu thay đổi precedence của một toán tử đã tồn tại, cần xem đó là thay đổi có thể ảnh hưởng đến ý nghĩa mã DSL cũ. Ví dụ, thêm một toán tử mới vào giữa hai mức có thể làm thay đổi cách nhóm biểu thức hiện có nếu grammar trước đó không quy định rõ.

## 19. Câu hỏi tự kiểm tra

1. Operator precedence là gì và nó giải quyết vấn đề nào?
2. Precedence khác associativity như thế nào?
3. Vì sao phép trừ thường được định nghĩa là kết hợp trái?
4. Non-associative operator có ý nghĩa gì? Nêu ví dụ.
5. Dấu ngoặc ảnh hưởng đến AST như thế nào?
6. Vì sao precedence không tự quyết định thứ tự gọi hàm?
7. Grammar nhiều tầng biểu diễn thứ tự ưu tiên ra sao?
8. Precedence climbing và Pratt parser khác nhau ở cách tổ chức như thế nào?
9. Shift/reduce conflict là gì và precedence có thể giúp giải quyết ra sao?
10. Vì sao DSL cần định nghĩa rõ thứ tự ưu tiên của NOT, AND và OR?
11. Short-circuit evaluation khác precedence như thế nào?
12. Khi thêm một toán tử mới, cần cập nhật những thành phần nào để bảo đảm parser, editor và runtime nhất quán?

Khi hiểu được precedence, associativity và grouping, người học có thể đọc biểu thức DSL và dự đoán cây cú pháp của nó. Đây cũng là nền tảng để thiết kế grammar không mơ hồ, xây dựng parser nhất quán và giúp người dùng viết biểu thức miền dễ hiểu.
