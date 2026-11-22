# Tính kết hợp

Trong ngữ pháp của một DSL (*Domain-Specific Language* – ngôn ngữ chuyên biệt theo miền), **tính kết hợp** (*associativity*) quy định cách nhóm các toán tử cùng mức ưu tiên khi chúng xuất hiện liên tiếp trong một biểu thức. Quy tắc này cho parser biết một chuỗi như `a - b - c` được hiểu là `(a - b) - c` hay `a - (b - c)`.

Tính kết hợp là một phần của đặc tả cú pháp biểu thức. Nó phối hợp với **độ ưu tiên toán tử** (*operator precedence*) để xác định cấu trúc cây cú pháp. Độ ưu tiên trả lời toán tử nào được nhóm trước khi các toán tử khác; tính kết hợp trả lời cách nhóm khi các toán tử cùng mức xuất hiện liên tiếp.

Một DSL có thể quy định toán tử kết hợp trái, kết hợp phải hoặc không cho phép kết hợp. Lựa chọn cần phản ánh ý nghĩa miền, tránh biểu thức mơ hồ và bảo đảm parser, formatter, interpreter hoặc backend hiểu chương trình theo cùng một cách.

## 1. Tính kết hợp là gì?

Xét biểu thức có ba toán hạng:

```text
a op b op c
```

Nếu hai toán tử `op` có cùng độ ưu tiên, parser cần biết cấu trúc nào được tạo. Có ba lựa chọn phổ biến:

- **Kết hợp trái** (*left-associative*): nhóm từ trái sang phải, tương đương `(a op b) op c`.
- **Kết hợp phải** (*right-associative*): nhóm từ phải sang trái, tương đương `a op (b op c)`.
- **Không kết hợp** (*non-associative*): không cho phép chuỗi toán tử cùng mức theo dạng đó nếu không có dấu ngoặc hoặc cấu trúc tường minh.

Ví dụ với phép trừ:

```text
a - b - c
```

Nếu phép trừ kết hợp trái, biểu thức được hiểu là:

```text
(a - b) - c
```

Nếu kết hợp phải, biểu thức được hiểu là:

```text
a - (b - c)
```

Với `a = 10`, `b = 3`, `c = 2`, hai cách nhóm cho kết quả khác nhau:

- `(10 - 3) - 2 = 5`
- `10 - (3 - 2) = 9`

Do đó, tính kết hợp có thể ảnh hưởng trực tiếp đến kết quả chương trình.

## 2. Kết hợp trái

Toán tử kết hợp trái nhóm chuỗi toán tử cùng mức ưu tiên từ trái sang phải. Đây là quy tắc phổ biến cho phép trừ, chia và nhiều toán tử nhị phân khác.

Ví dụ:

```text
a - b - c - d
```

được hiểu là:

```text
(((a - b) - c) - d)
```

Tương tự:

```text
100 / 10 / 2
```

được hiểu là:

```text
(100 / 10) / 2
```

Kết quả là `5`, trong khi `100 / (10 / 2)` cho kết quả `20`.

### 2.1. Cây cú pháp của kết hợp trái

Với biểu thức `a - b - c`, AST có thể có dạng:

```text
        Subtract
        /      \
    Subtract    c
     /    \
    a      b
```

Nút `Subtract` bên trái được tạo trước, rồi kết quả của nó trở thành toán hạng trái của phép trừ tiếp theo. Đây là lý do cách nhóm được gọi là kết hợp trái.

### 2.2. Ví dụ trong DSL

Một DSL tính toán có thể định nghĩa các phép trừ liên tiếp theo quy tắc kết hợp trái:

```text
remaining = stock - reserved - damaged
```

Ngữ nghĩa tương ứng là:

```text
remaining = (stock - reserved) - damaged
```

Quy tắc này dễ triển khai bằng cách duyệt từ trái sang phải và cập nhật kết quả trung gian. Tuy nhiên, DSL vẫn cần định nghĩa kiểu dữ liệu, xử lý tràn số, giá trị thiếu và lỗi chia cho 0 nếu có các phép toán tương ứng.

## 3. Kết hợp phải

Toán tử kết hợp phải nhóm chuỗi toán tử cùng mức ưu tiên từ phải sang trái.

Ví dụ:

```text
a ^ b ^ c
```

Nếu `^` là toán tử lũy thừa kết hợp phải, biểu thức được hiểu là:

```text
a ^ (b ^ c)
```

Với `a = 2`, `b = 3`, `c = 2`:

- `2 ^ (3 ^ 2) = 2 ^ 9 = 512`
- `(2 ^ 3) ^ 2 = 8 ^ 2 = 64`

Một ví dụ khác là phép gán trong nhiều ngôn ngữ lập trình:

```text
a = b = c
```

thường được nhóm thành:

```text
a = (b = c)
```

Giá trị `c` được gán cho `b`, rồi kết quả biểu thức gán được dùng để gán cho `a` theo ngữ nghĩa của ngôn ngữ.

### 3.1. Cây cú pháp của kết hợp phải

Với biểu thức `a ^ b ^ c`, AST kết hợp phải có dạng:

```text
        Power
        /   \
       a    Power
            /   \
           b     c
```

Nút phép lũy thừa ở bên phải được tạo trước trong cấu trúc cây. Khi diễn giải cây, phép `b ^ c` là toán hạng thứ hai của phép lũy thừa bên ngoài.

### 3.2. Ví dụ trong DSL khai báo

Một DSL có biểu thức gán có thể cho phép:

```text
primary = fallback = default_value
```

Nếu phép gán kết hợp phải, cấu trúc là:

```text
primary = (fallback = default_value)
```

Tuy nhiên, không phải DSL nào cũng nên cho phép gán lồng nhau. Với DSL cấu hình, cách viết riêng từng khai báo có thể dễ đọc và ít gây nhầm lẫn hơn:

```text
primary = default_value
fallback = default_value
```

Việc chọn kết hợp phải hay cấm chuỗi gán là quyết định thiết kế của ngôn ngữ.

## 4. Toán tử không kết hợp

Một toán tử hoặc nhóm toán tử được gọi là không kết hợp nếu DSL không cho phép chuỗi cùng mức ưu tiên lặp lại theo cách có thể gây hiểu nhầm. Người viết phải dùng dấu ngoặc hoặc cú pháp khác để chỉ rõ ý định.

Ví dụ, một DSL có thể cấm:

```text
a < b < c
```

Vì biểu thức này có thể được hiểu theo nhiều cách:

```text
(a < b) < c
a < (b < c)
```

Nếu `<` trả về Boolean, các phép so sánh tiếp theo có thể không hợp kiểu. Nếu miền muốn diễn đạt một khoảng, DSL nên có cú pháp riêng hoặc yêu cầu viết rõ:

```text
(a < b) and (b < c)
```

Một số ngôn ngữ có hỗ trợ so sánh chuỗi như `a < b < c` với ngữ nghĩa đặc biệt: kiểm tra cả `a < b` và `b < c`, trong đó `b` chỉ được đánh giá một lần. Đó là một quy tắc ngôn ngữ riêng, không phải hệ quả tự động của phép kết hợp trái hoặc phải.

### 4.1. Vì sao chọn không kết hợp?

Không kết hợp hữu ích khi:

- Chuỗi toán tử không có ý nghĩa miền rõ ràng.
- Cách nhóm có thể tạo ra kiểu dữ liệu không hợp lệ.
- Người viết dễ nhầm giữa các cách hiểu khác nhau.
- DSL muốn buộc người dùng thể hiện rõ ý định bằng ngoặc.

Ví dụ, toán tử so sánh có thể được khai báo không kết hợp để buộc người viết diễn đạt điều kiện nhiều phần bằng `and` hoặc `or`.

### 4.2. Không kết hợp không có nghĩa là toán tử không thể dùng

Toán tử không kết hợp vẫn có thể được dùng trong biểu thức đơn:

```text
age >= minimum_age
```

Điều bị cấm là nối nhiều toán tử thuộc nhóm không kết hợp theo cấu trúc không được grammar cho phép:

```text
age >= minimum_age >= 18
```

Người dùng có thể viết tường minh bằng ngoặc hoặc toán tử logic:

```text
(age >= minimum_age) and (minimum_age >= 18)
```

## 5. Tính kết hợp khác độ ưu tiên toán tử

Hai khái niệm này thường được dạy cùng nhau nhưng giải quyết hai vấn đề khác nhau.

- **Độ ưu tiên** xác định toán tử nào được nhóm trước khi các toán tử khác.
- **Tính kết hợp** xác định cách nhóm các toán tử cùng mức ưu tiên khi chúng lặp lại.

Xét biểu thức:

```text
a + b * c
```

Nếu phép nhân có độ ưu tiên cao hơn phép cộng, biểu thức là:

```text
a + (b * c)
```

Ở đây độ ưu tiên quyết định nhóm `b * c` trước. Không cần xét tính kết hợp vì chỉ có một phép nhân và một phép cộng.

Xét biểu thức:

```text
a - b - c
```

Hai phép trừ có cùng độ ưu tiên, nên tính kết hợp quyết định biểu thức được nhóm trái hay phải.

### 5.1. Bảng ví dụ

| Biểu thức | Quy tắc | Cách nhóm |
|---|---|---|
| `a + b * c` | `*` ưu tiên cao hơn `+` | `a + (b * c)` |
| `a - b - c` | `-` kết hợp trái | `(a - b) - c` |
| `a ^ b ^ c` | `^` kết hợp phải | `a ^ (b ^ c)` |
| `a < b < c` | `<` không kết hợp | Không hợp lệ nếu không có quy tắc so sánh chuỗi riêng |
| `a = b = c` | `=` kết hợp phải | `a = (b = c)` |

### 5.2. Biểu thức có nhiều mức ưu tiên

Giả sử DSL định nghĩa:

1. `*` và `/` có độ ưu tiên cao.
2. `+` và `-` có độ ưu tiên thấp hơn.
3. Các toán tử trong mỗi nhóm kết hợp trái.

Biểu thức:

```text
a - b / c * d + e
```

được nhóm thành:

```text
(a - ((b / c) * d)) + e
```

Parser trước tiên xử lý chuỗi `/` và `*` ở mức ưu tiên cao hơn, áp dụng kết hợp trái trong nhóm đó; sau đó xử lý `-` và `+` ở mức thấp hơn, cũng theo kết hợp trái.

## 6. Tính kết hợp khác thứ tự đánh giá

Tính kết hợp xác định **cấu trúc nhóm** của biểu thức. Thứ tự đánh giá (*evaluation order*) quy định các toán hạng hoặc biểu thức con được tính vào thời điểm nào và theo thứ tự nào. Hai khái niệm liên quan nhưng không đồng nghĩa.

Ví dụ, với biểu thức:

```text
left() + right()
```

Toán tử `+` có thể kết hợp trái về cấu trúc. Nhưng ngôn ngữ vẫn cần quy định `left()` hay `right()` được gọi trước, đặc biệt nếu các hàm có hiệu ứng phụ như ghi log, thay đổi trạng thái hoặc phát sinh ngoại lệ.

Một số ngôn ngữ quy định thứ tự đánh giá từ trái sang phải; một số khác để lại một số trường hợp không được bảo đảm. Không nên suy ra thứ tự đánh giá chỉ từ việc toán tử kết hợp trái.

### 6.1. Ví dụ với hiệu ứng phụ

Giả sử:

```text
result = updateA() + updateB()
```

Nếu cả hai hàm đều thay đổi trạng thái dùng chung, thứ tự gọi có thể ảnh hưởng đến kết quả. Quy tắc kết hợp của `+` chỉ xác định cách nhóm phép cộng; nó không tự quyết định thứ tự gọi hai hàm.

### 6.2. Short-circuit và toán tử logic

Với toán tử `and` hoặc `or`, DSL có thể quy định đánh giá ngắn mạch (*short-circuit*): vế phải chỉ được đánh giá khi cần thiết.

Ví dụ:

```text
is_valid and check_permission()
```

Nếu `is_valid` là `false` và `and` dùng short-circuit, `check_permission()` có thể không được gọi. Đây là quy tắc đánh giá riêng của toán tử logic, bên cạnh độ ưu tiên và tính kết hợp.

## 7. Tính kết hợp của toán tử và tính kết hợp trong toán học

Trong toán học, một phép toán `op` có tính kết hợp nếu:

\[
(a \; op \; b) \; op \; c = a \; op \; (b \; op \; c)
\]

Ví dụ, phép cộng số nguyên trong toán học có tính kết hợp:

\[
(2 + 3) + 4 = 2 + (3 + 4) = 9
\]

Nhưng **tính kết hợp của phép toán về mặt toán học** và **tính kết hợp cú pháp của toán tử** là hai khái niệm khác nhau.

- Tính kết hợp toán học nói về việc đổi cách nhóm có giữ nguyên giá trị hay không.
- Tính kết hợp cú pháp nói về cách parser nhóm một chuỗi toán tử khi không có dấu ngoặc.

Một toán tử có thể được định nghĩa kết hợp trái về cú pháp dù phép toán có tính kết hợp về mặt toán học. Ví dụ, phép cộng thường được phân tích trái, mặc dù cộng số nguyên không tràn có thể cho cùng kết quả khi nhóm trái hoặc phải.

Ngược lại, phép trừ không có tính kết hợp toán học, vì vậy việc lựa chọn kết hợp trái hay phải làm thay đổi kết quả.

### 7.1. Số thực dấu phẩy động

Ngay cả phép cộng cũng có thể không cho kết quả giống nhau khi đổi cách nhóm trong số thực dấu phẩy động do giới hạn độ chính xác và làm tròn.

Ví dụ minh họa trong số học máy:

```text
(1e20 + (-1e20)) + 3.14
```

có thể cho kết quả khác với:

```text
1e20 + ((-1e20) + 3.14)
```

Do đó, compiler hoặc optimizer không được tự ý đổi nhóm phép toán dấu phẩy động nếu điều đó làm thay đổi ngữ nghĩa được bảo đảm bởi DSL. Một DSL khoa học hoặc tài chính cần xác định rõ mô hình số học, độ chính xác và các phép biến đổi được phép.

## 8. Biểu diễn tính kết hợp trong grammar

Tính kết hợp có thể được biểu diễn trực tiếp trong grammar hoặc được quy định bằng metadata của toán tử trong parser.

### 8.1. Grammar kết hợp trái

Một cách viết EBNF cho chuỗi phép cộng và trừ kết hợp trái:

```ebnf
Additive = Multiplicative, { ("+" | "-"), Multiplicative } ;
```

Quy tắc này cho phép một toán hạng nhân đầu tiên, sau đó là không hoặc nhiều cặp toán tử và toán hạng. Parser cần xây dựng AST bằng cách gộp từ trái sang phải.

Ví dụ mã giả:

```text
parseAdditive():
    expr = parseMultiplicative()

    while next_token is PLUS or MINUS:
        operator = consume()
        right = parseMultiplicative()
        expr = BinaryExpression(expr, operator, right)

    return expr
```

Với `a - b - c`, vòng lặp tạo lần lượt:

```text
expr1 = Subtract(a, b)
expr2 = Subtract(expr1, c)
```

Kết quả là `Subtract(Subtract(a, b), c)`, tức kết hợp trái.

### 8.2. Grammar kết hợp phải

Một quy tắc đệ quy phải có thể biểu diễn phép gán hoặc toán tử lũy thừa kết hợp phải:

```ebnf
Assignment = Identifier, "=", Assignment | Conditional ;
```

Đây chỉ là ví dụ khái quát; grammar thật cần bảo đảm nhánh `Conditional` không tạo mơ hồ hoặc chấp nhận đích gán không hợp lệ.

Mã giả parser:

```text
parseAssignment():
    left = parseConditional()

    if match(EQUALS):
        right = parseAssignment()
        return AssignmentExpression(left, right)

    return left
```

Vì parser gọi lại `parseAssignment()` cho vế phải, biểu thức `a = b = c` tạo thành `Assign(a, Assign(b, c))`.

### 8.3. Grammar không kết hợp

Nếu DSL chỉ cho phép một phép so sánh trong một biểu thức, grammar có thể là:

```ebnf
Comparison = Additive, [ CompareOperator, Additive ] ;
```

Quy tắc chỉ cho phép không có hoặc có đúng một toán tử so sánh. Chuỗi `a < b < c` sẽ không được phân tích như một `Comparison` hợp lệ.

Nếu muốn hỗ trợ nhiều phép so sánh, DSL có thể định nghĩa một cấu trúc riêng với ngữ nghĩa rõ ràng, chẳng hạn `RangeTest(a, b, c)` hoặc chuỗi so sánh đặc biệt. Không nên vô tình cho phép chuỗi đó chỉ vì dùng phép lặp trong grammar.

## 9. Tính kết hợp trong parser generator

Một số công cụ sinh parser cho phép khai báo độ ưu tiên và tính kết hợp của toán tử mà không cần viết riêng từng tầng grammar.

Ví dụ khai báo khái niệm:

```text
left:  PLUS, MINUS
left:  MULTIPLY, DIVIDE
right: POWER
nonassoc: LESS, GREATER, EQUALS
```

Đây là cú pháp giả định để minh họa ý tưởng; cú pháp thực tế tùy parser generator. Quy tắc thường cho phép công cụ giải quyết xung đột parsing dựa trên mức ưu tiên và hướng kết hợp.

Khi dùng parser generator, cần hiểu rõ:

- Thứ tự khai báo precedence có nghĩa là ưu tiên tăng dần hay giảm dần.
- Quy tắc được áp dụng cho token nào và production nào.
- Cách công cụ xử lý xung đột shift/reduce.
- `nonassoc` từ chối chuỗi toán tử nào.
- Cách gắn vị trí nguồn và tạo AST theo quy tắc đã khai báo.

Không nên chỉ thêm khai báo precedence để làm parser hết cảnh báo mà không kiểm tra AST được tạo ra. Một parser không báo xung đột vẫn có thể hiểu chương trình theo cách không phù hợp với miền.

## 10. Dấu ngoặc và việc ghi rõ cách nhóm

Dấu ngoặc cho phép người viết chỉ rõ cách nhóm biểu thức, thường có ưu tiên cao hơn các quy tắc kết hợp mặc định.

Ví dụ:

```text
a - (b - c)
```

Biểu thức này yêu cầu nhóm `b - c` trước, dù phép trừ mặc định kết hợp trái.

Tương tự:

```text
(a ^ b) ^ c
```

có thể yêu cầu nhóm trái cho toán tử `^` vốn kết hợp phải.

Dấu ngoặc hữu ích khi:

- Muốn ghi đè cách nhóm mặc định.
- Biểu thức có nhiều toán tử và cần tăng khả năng đọc.
- Muốn thể hiện rõ ý định trong quy tắc nghiệp vụ quan trọng.
- Cần tránh phụ thuộc vào việc người đọc nhớ chính xác bảng precedence.

Formatter có thể bỏ một số dấu ngoặc thừa, nhưng chỉ khi chắc chắn cấu trúc AST và ngữ nghĩa không thay đổi. Trong tài liệu cấu hình hoặc quy tắc nghiệp vụ, giữ ngoặc đôi khi vẫn tốt hơn vì giúp người đọc hiểu ý định.

## 11. Lựa chọn tính kết hợp cho DSL theo miền

Không nên sao chép máy móc quy tắc của một ngôn ngữ đa dụng. Tính kết hợp cần phù hợp với ý nghĩa thao tác trong miền.

### 11.1. DSL tính toán

Các toán tử số học thường dùng:

| Toán tử | Quy tắc thường gặp | Lý do |
|---|---|---|
| `+` | Kết hợp trái | Quy ước phổ biến trong biểu thức số học |
| `-` | Kết hợp trái | Thay đổi nhóm làm thay đổi kết quả |
| `*` | Kết hợp trái | Quy ước cú pháp phổ biến; cần chú ý số thực và tràn số |
| `/` | Kết hợp trái | Chia liên tiếp thường được nhóm từ trái sang phải |
| `^` | Thường kết hợp phải | Phù hợp với cách hiểu chuỗi lũy thừa trong nhiều ngôn ngữ toán học và tính toán |

Đây là quy ước thường gặp, không phải bắt buộc cho mọi DSL. Đặc tả phải nói rõ lựa chọn.

### 11.2. DSL truy vấn và điều kiện

Toán tử logic `and` và `or` thường được phân tích theo nhóm trái hoặc được xem là các chuỗi logic có thể chuẩn hóa. Tuy nhiên, nếu có short-circuit hoặc hiệu ứng phụ, việc đổi nhóm và thứ tự đánh giá cần được quy định rõ.

Toán tử so sánh như `<`, `>`, `==` thường được đặt là không kết hợp để tránh biểu thức kiểu `a < b < c` bị hiểu không rõ ràng. Nếu DSL muốn hỗ trợ so sánh chuỗi, cần định nghĩa ngữ nghĩa riêng.

### 11.3. DSL cấu hình và khai báo

Một DSL cấu hình có thể có toán tử gán `=`. Nếu cho phép gán chuỗi, kết hợp phải là một lựa chọn phổ biến. Nhưng nhiều DSL cấu hình không cho phép gán như biểu thức; mỗi khai báo là một cặp khóa/giá trị độc lập. Khi đó, khái niệm kết hợp của phép gán có thể không xuất hiện.

### 11.4. DSL workflow hoặc pipeline

Một DSL workflow có thể dùng toán tử nối bước như `->`:

```text
source -> validate -> transform -> publish
```

Nếu các bước tạo thành chuỗi tuần tự, toán tử có thể được định nghĩa kết hợp trái hoặc phải về cú pháp. Nếu ngữ nghĩa của phép nối là composition có tính kết hợp, cách nhóm có thể không ảnh hưởng kết quả, nhưng DSL vẫn cần quy tắc parser nhất quán.

Nếu các bước có phụ thuộc, hiệu ứng phụ hoặc chạy song song, không nên suy ra thứ tự thực thi chỉ từ tính kết hợp của toán tử nối. Engine cần có ngữ nghĩa rõ cho đồ thị workflow.

## 12. Tính kết hợp và phép biến đổi biểu thức

Khi compiler hoặc engine tối ưu biểu thức, việc đổi cách nhóm chỉ hợp lệ nếu bảo toàn ngữ nghĩa.

Ví dụ, với số nguyên không tràn:

```text
(a + b) + c
```

có thể được chuyển thành:

```text
a + (b + c)
```

nếu phép cộng có tính kết hợp trong mô hình số học được DSL quy định.

Nhưng với phép trừ:

```text
(a - b) - c
```

không thể tự đổi thành:

```text
a - (b - c)
```

vì kết quả nói chung khác nhau.

### 12.1. Quy tắc tối ưu cần dựa trên ngữ nghĩa

Optimizer cần biết:

- Toán tử có tính kết hợp về mặt ngữ nghĩa không.
- Kiểu dữ liệu có thể tràn, làm tròn hoặc phát sinh ngoại lệ không.
- Phép toán có hiệu ứng phụ hay không.
- Thứ tự đánh giá có được bảo đảm không.
- Backend đích có cùng quy tắc với IR hay không.

Một toán tử kết hợp trái về cú pháp không có nghĩa optimizer được phép tùy ý đổi nhóm. Ngược lại, toán tử có phép toán kết hợp về mặt toán học vẫn cần parser tạo cấu trúc theo quy tắc cú pháp được đặc tả.

### 12.2. Ví dụ với chuỗi nối

Nếu DSL định nghĩa `+` cho chuỗi, biểu thức:

```text
"A" + "B" + "C"
```

có thể được nhóm trái. Nếu nối chuỗi thuần túy không có hiệu ứng phụ, các cách nhóm có thể cho cùng nội dung cuối. Tuy nhiên, cách thực thi có thể khác về cấp phát bộ nhớ hoặc hiệu năng. Engine có thể tối ưu thành một phép nối nhiều phần nếu vẫn bảo toàn kết quả quan sát được.

## 13. Những sai lầm thường gặp

**Nhầm tính kết hợp với độ ưu tiên.** Độ ưu tiên so sánh các loại toán tử khác nhau; tính kết hợp xử lý các toán tử cùng mức.

**Nhầm kết hợp cú pháp với tính kết hợp toán học.** Một toán tử được parser nhóm trái không có nghĩa phép toán luôn cho kết quả giống khi nhóm phải.

**Cho rằng kết hợp trái đồng nghĩa đánh giá từ trái sang phải.** Cấu trúc AST và thứ tự đánh giá là hai quy tắc khác nhau; DSL cần đặc tả cả hai nếu có liên quan.

**Cho phép chuỗi so sánh mà không định nghĩa ý nghĩa.** `a < b < c` có thể bị hiểu sai hoặc không hợp kiểu. Hãy cấm, yêu cầu ngoặc hoặc định nghĩa rõ phép so sánh chuỗi.

**Dùng đệ quy sai hướng trong parser.** Một parser tạo AST trái cho toán tử kết hợp phải sẽ cho kết quả khác với đặc tả.

**Sửa xung đột parser mà không kiểm tra AST.** Khai báo precedence có thể khiến công cụ sinh parser chấp nhận grammar, nhưng cấu trúc tạo ra vẫn có thể sai ý nghĩa.

**Tối ưu hóa bằng cách đổi nhóm tùy tiện.** Phép trừ, chia, số thực và toán tử có hiệu ứng phụ thường không cho phép đổi nhóm một cách tự do.

## 14. Ghi nhớ

- Tính kết hợp xác định cách nhóm các toán tử cùng mức ưu tiên khi xuất hiện liên tiếp.
- Kết hợp trái tạo cấu trúc `(a op b) op c`; kết hợp phải tạo `a op (b op c)`.
- Toán tử không kết hợp không cho phép chuỗi tương ứng nếu không có ngoặc hoặc quy tắc đặc biệt.
- Độ ưu tiên và tính kết hợp phối hợp để tạo AST nhưng giải quyết hai câu hỏi khác nhau.
- Tính kết hợp cú pháp không đồng nghĩa với thứ tự đánh giá hoặc tính kết hợp toán học.
- Grammar, parser và parser generator cần tạo đúng cấu trúc theo đặc tả.
- Optimizer chỉ được đổi cách nhóm khi ngữ nghĩa của DSL bảo đảm phép biến đổi là hợp lệ.

## 15. Câu hỏi tự kiểm tra

1. Tính kết hợp của toán tử giải quyết vấn đề gì khi phân tích biểu thức?
2. Biểu thức `a - b - c` được nhóm như thế nào nếu phép trừ kết hợp trái?
3. Vì sao `a ^ b ^ c` thường được định nghĩa kết hợp phải trong DSL tính toán?
4. Tại sao một DSL có thể chọn toán tử so sánh là không kết hợp?
5. Phân biệt độ ưu tiên với tính kết hợp bằng ví dụ `a + b * c` và `a - b - c`.
6. Vì sao tính kết hợp không quyết định thứ tự gọi `left()` và `right()` trong `left() + right()`?
7. Tính kết hợp toán học khác tính kết hợp cú pháp như thế nào?
8. Một grammar EBNF dùng phép lặp cho chuỗi cộng/trừ. Parser cần xây AST ra sao để bảo đảm kết hợp trái?
9. Vì sao optimizer phải cẩn thận khi đổi nhóm phép cộng số thực?
10. Hãy đề xuất quy tắc kết hợp cho toán tử nối bước trong một DSL workflow và giải thích điều kiện cần quy định thêm về thực thi.
