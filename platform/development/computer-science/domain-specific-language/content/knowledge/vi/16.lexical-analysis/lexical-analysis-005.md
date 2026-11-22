# Quy tắc khớp dài nhất

Trong phân tích từ vựng (*lexical analysis*) của một DSL (*Domain-Specific Language* – ngôn ngữ chuyên biệt theo miền), lexer đọc văn bản nguồn và chia nó thành các token như từ khóa, tên định danh, số, chuỗi, toán tử và dấu phân cách. Một vấn đề quan trọng xuất hiện khi cùng một đoạn ký tự có thể bắt đầu nhiều loại token khác nhau hoặc khớp với nhiều token có độ dài khác nhau.

**Quy tắc khớp dài nhất** (*maximal munch* hoặc *longest-match rule*) yêu cầu lexer, tại vị trí hiện tại, chọn token hợp lệ có đoạn khớp dài nhất theo các quy tắc từ vựng của ngôn ngữ. Sau khi chọn token, lexer tiếp tục từ ký tự ngay sau token đó.

Ví dụ, nếu DSL có các toán tử `>`, `>=`, `=`, `==` và đầu vào là:

```text
total >= limit
```

lexer phải nhận diện `>=` thành một token, thay vì tách thành `>` và `=`. Tương tự, với `==`, lexer chọn toán tử hai ký tự thay vì hai token `=` riêng lẻ.

Quy tắc này giúp việc phân chia token nhất quán và dễ dự đoán. Tuy nhiên, nó chỉ giải quyết cách chọn token tại một vị trí; nó không thay thế grammar, phân tích ngữ nghĩa hoặc các quy tắc về độ ưu tiên toán tử.

## 1. Token và đoạn khớp

Token là đơn vị từ vựng mà parser nhận được từ lexer. Mỗi token thường có loại, đoạn văn bản gốc (*lexeme*), giá trị đã phân tích nếu cần và vị trí nguồn.

Ví dụ DSL:

```text
if score >= 90 then award = true
```

Lexer có thể tạo chuỗi token:

```text
KEYWORD("if")
IDENTIFIER("score")
GREATER_EQUAL(">=")
NUMBER("90")
KEYWORD("then")
IDENTIFIER("award")
EQUALS("=")
BOOLEAN("true")
```

Đoạn văn bản gốc tương ứng với một token được gọi là lexeme. Ví dụ, lexeme của token `GREATER_EQUAL` là `>=`.

Tại một vị trí trong nguồn, có thể có nhiều quy tắc token cùng khớp một tiền tố. Lexer cần chọn một cách nhất quán để xác định ranh giới token. Maximal munch là quy tắc phổ biến để thực hiện việc đó.

## 2. Phát biểu quy tắc khớp dài nhất

Giả sử lexer đang đứng tại vị trí `i` trong chuỗi nguồn. Gọi `M` là tập các đoạn bắt đầu tại `i` và được ít nhất một quy tắc token chấp nhận. Quy tắc khớp dài nhất chọn đoạn có số ký tự hoặc đơn vị đầu vào lớn nhất theo mô hình lexer đang dùng.

Có thể mô tả ngắn gọn:

1. Bắt đầu tại ký tự hiện tại.
2. Tiếp tục đọc khi phần đầu vào đang xét vẫn có thể tạo thành một token hợp lệ.
3. Ghi nhớ điểm xa nhất mà một quy tắc token chấp nhận.
4. Khi không thể tiếp tục, phát token tương ứng với điểm chấp nhận xa nhất.
5. Đưa con trỏ về ngay sau token vừa chọn và lặp lại.

Ví dụ, nếu các toán tử hợp lệ là `:`, `::` và `::=`, đầu vào `::=` phải được nhận diện thành một token `::=` vì đó là đoạn hợp lệ dài nhất bắt đầu tại vị trí hiện tại.

### 2.1. Ví dụ với toán tử so sánh

Giả sử DSL định nghĩa:

| Token | Lexeme |
|---|---|
| `LESS` | `<` |
| `LESS_EQUAL` | `<=` |
| `SHIFT_LEFT` | `<<` |
| `SHIFT_LEFT_ASSIGN` | `<<=` |

Các đầu vào được phân tích như sau:

| Đầu vào tại vị trí hiện tại | Token được chọn | Lý do |
|---|---|---|
| `<` | `LESS` | Chỉ có một ký tự hợp lệ |
| `<=` | `LESS_EQUAL` | Dài hơn `<` |
| `<<` | `SHIFT_LEFT` | Dài hơn `<` và khớp toàn bộ hai ký tự |
| `<<=` | `SHIFT_LEFT_ASSIGN` | Dài nhất trong các token hợp lệ bắt đầu bằng `<<` |

Nếu lexer chọn `<` ngay khi vừa nhận diện được, nó có thể chia `<<=` thành `<`, `<`, `=` và làm mất ý nghĩa của toán tử dài hơn.

### 2.2. Lexer không nhất thiết phải đọc hết tệp

Khớp dài nhất chỉ cần xem xét đủ xa để xác định token hợp lệ dài nhất bắt đầu tại vị trí hiện tại. Lexer thường dùng trạng thái máy hữu hạn để biết còn khả năng khớp hay không. Khi đã đi qua điểm chấp nhận cuối cùng và không còn đường tiếp tục hợp lệ, lexer phát token đã ghi nhận.

Trong một số trường hợp, lexer phải đọc thêm vài ký tự rồi quay lại điểm chấp nhận cuối (*last accepting position*). Đây là hành vi lookahead và backtracking có kiểm soát, không có nghĩa parser phải phân tích lại toàn bộ đầu vào.

## 3. Vì sao cần khớp dài nhất?

Nếu DSL có token mà lexeme của token này là tiền tố của token khác, lexer cần một quy tắc để tránh chọn token ngắn quá sớm.

Ví dụ:

```text
=
==
!=
>=
->
::
```

Các token nhiều ký tự thường được xây dựng từ những ký hiệu đơn lẻ cũng có ý nghĩa riêng. Maximal munch cho phép lexer nhận diện token dài khi toàn bộ đoạn khớp hợp lệ.

Quy tắc này mang lại các lợi ích:

- **Ranh giới token nhất quán:** cùng một chuỗi đầu vào được chia token theo một quy tắc xác định.
- **Hỗ trợ toán tử có tiền tố chung:** `>` và `>=` hoặc `=` và `==` không bị tách nhầm.
- **Giảm phụ thuộc vào thứ tự kiểm tra thủ công:** lexer không phải luôn kiểm tra từng token dài trước token ngắn bằng một danh sách if/else dễ sai.
- **Phù hợp với DFA:** có thể triển khai hiệu quả bằng máy trạng thái hữu hạn được sinh từ các quy tắc từ vựng.
- **Dễ mở rộng từ vựng:** có thể thêm token dài hơn với tiền tố chung nếu đặc tả cho phép và các quy tắc ưu tiên được xác định rõ.

Maximal munch không làm cho grammar tự động hết mơ hồ. Nó chỉ xác định cách lexer chọn lexeme; parser vẫn cần xử lý cấu trúc token theo grammar.

## 4. Khớp dài nhất và từ khóa so với định danh

Một trường hợp phổ biến là từ khóa cũng khớp với quy tắc định danh.

Giả sử định danh được mô tả bằng:

```regex
[A-Za-z_][A-Za-z0-9_]*
```

và `if` là từ khóa. Chuỗi `if` khớp cả quy tắc định danh lẫn từ khóa. Chuỗi `ifx` khớp quy tắc định danh với toàn bộ ba ký tự.

Một cách triển khai phổ biến là:

1. Lexer nhận diện toàn bộ chuỗi định danh dài nhất.
2. Sau khi đọc lexeme, tra bảng từ khóa.
3. Nếu lexeme trùng từ khóa đã dành riêng, phát token từ khóa.
4. Nếu không, phát token định danh.

Ví dụ:

| Lexeme | Kết quả |
|---|---|
| `if` | `IF` |
| `ifx` | `IDENTIFIER("ifx")` |
| `if_1` | `IDENTIFIER("if_1")` |
| `while` | `WHILE` nếu là từ khóa |
| `whileCount` | `IDENTIFIER("whileCount")` |

Nếu lexer tách `ifx` thành `IF` rồi `IDENTIFIER("x")`, nó đã chọn tiền tố ngắn thay vì định danh dài nhất.

### 4.1. Từ khóa dành riêng

Với từ khóa dành riêng (*reserved keywords*), một lexeme cụ thể không thể được dùng như tên định danh thông thường. Ví dụ, `if` luôn là token `IF`.

Quy trình nhận diện định danh rồi tra bảng từ khóa là cách triển khai phổ biến vì từ khóa thường tuân theo cùng quy tắc ký tự với tên định danh.

### 4.2. Từ khóa theo ngữ cảnh

Một số DSL dùng từ khóa theo ngữ cảnh (*contextual keywords*). Một từ như `where` có thể là tên định danh ở một vị trí nhưng là từ khóa ở vị trí khác.

Khi đó, lexer có thể phát `IDENTIFIER("where")`, rồi parser hoặc bước xử lý tiếp theo quyết định vai trò dựa trên ngữ cảnh. Đây là quyết định thiết kế riêng; maximal munch vẫn chọn toàn bộ lexeme `where` nếu đó là đoạn định danh dài nhất.

### 4.3. Thứ tự ưu tiên khi độ dài bằng nhau

Maximal munch quyết định token nào có lexeme dài nhất. Nhưng nếu hai quy tắc cùng chấp nhận đúng một đoạn có cùng độ dài, lexer cần thêm quy tắc phá hòa (*tie-breaking*).

Ví dụ, cả quy tắc `IDENTIFIER` và quy tắc từ khóa `IF` cùng khớp chính xác chuỗi `if`. Hai quy tắc có độ dài bằng nhau. Lexer có thể:

- Ưu tiên token từ khóa theo bảng từ khóa.
- Ưu tiên quy tắc được khai báo trước trong lexer generator.
- Phát định danh rồi phân loại lại bằng bảng từ khóa.

Thứ tự phá hòa phải được đặc tả hoặc tuân theo tài liệu của công cụ sinh lexer. Không nên giả định maximal munch tự giải quyết trường hợp bằng độ dài.

## 5. Quy tắc khớp dài nhất với số và literal

Các literal số thường có nhiều tiền tố chung. Ví dụ DSL có thể hỗ trợ số nguyên, số thập phân và số có số mũ.

```text
42
3.14
6.02e23
0xFF
```

Lexer phải xác định toàn bộ literal theo grammar số mà DSL quy định. Một số tình huống cần đặc biệt chú ý:

- `12.5` có thể là một số thập phân, không phải số `12`, dấu chấm và số `5`.
- `1e10` có thể là một số có số mũ nếu DSL hỗ trợ ký pháp đó.
- `0xFF` có thể là số hexadecimal nếu DSL hỗ trợ tiền tố `0x`.
- `1..10` có thể là số `1`, toán tử khoảng `..`, số `10` nếu DSL dùng `..` để biểu diễn range.

### 5.1. Xung đột giữa số thập phân và toán tử dấu chấm

Giả sử DSL hỗ trợ cả số thập phân và toán tử khoảng `..`:

```text
1.5
1..10
```

Lexer cần có quy tắc để không đọc `1..10` thành số thập phân sai hoặc các token không mong muốn. Một cách là định nghĩa rõ grammar của numeric literal, chẳng hạn dấu chấm thập phân chỉ được theo sau bởi chữ số, trong khi toán tử `..` được nhận diện riêng. Chi tiết phụ thuộc grammar số của DSL.

### 5.2. Dấu âm là toán tử hay một phần literal?

Nhiều ngôn ngữ nhận diện `-` là toán tử một ngôi riêng, còn `42` là token số:

```text
-42
```

có thể tạo token `MINUS` rồi `NUMBER(42)`. Parser kết hợp chúng thành biểu thức âm.

Một DSL khác có thể cho phép lexer nhận số âm thành một literal duy nhất. Lựa chọn này ảnh hưởng đến tokenization và cách xử lý biểu thức như `a-42`, nên cần được định nghĩa rõ. Maximal munch không tự quyết định liệu dấu `-` thuộc token số hay là toán tử riêng; đó là lựa chọn của từ vựng.

### 5.3. Số có định dạng không hợp lệ

Lexer cần phân biệt token hợp lệ với chuỗi gần giống literal nhưng sai định dạng. Ví dụ, nếu DSL yêu cầu chữ số sau dấu chấm, `12.` có thể được phân tích thành `NUMBER(12)` rồi `DOT`, hoặc bị báo lỗi tùy đặc tả. Không nên để quy tắc khớp dài nhất tạo ra kết quả tình cờ mà không có định nghĩa rõ.

## 6. Khớp dài nhất với toán tử và dấu phân cách

Một DSL có thể có nhiều toán tử dùng chung tiền tố:

```text
=   +
==   =
!=   !
<=   <
>=   >
&&   &
||   |
->   -
```

Nếu đầu vào bắt đầu bằng `>=`, lexer chọn `>=` nếu đây là token hợp lệ. Nếu đầu vào chỉ có `>` hoặc ký tự tiếp theo không tạo thành toán tử dài hơn, lexer chọn `>`.

Ví dụ với họ toán tử gán:

| Đầu vào | Tokenization |
|---|---|
| `=` | `ASSIGN` |
| `==` | `EQUAL_EQUAL` |
| `===` | Phụ thuộc DSL: `STRICT_EQUAL` nếu được định nghĩa, hoặc `EQUAL_EQUAL` rồi `ASSIGN` nếu đó là cách tách hợp lệ |
| `+=` | `PLUS_ASSIGN` |
| `+` | `PLUS` |

Không thể suy ra cách phân tích `===` chỉ từ việc `==` tồn tại. Nếu DSL không định nghĩa token ba ký tự, maximal munch sẽ chọn token hợp lệ dài nhất theo tập quy tắc thực tế, rồi tiếp tục phân tích phần còn lại.

### 6.1. Ví dụ với toán tử mũi tên

Giả sử DSL có:

```text
->
-->
-
```

Với đầu vào `-->`, lexer chọn `-->` nếu token đó được định nghĩa. Nếu chỉ có `->` và `-`, lexer chọn token hợp lệ dài nhất tại vị trí đầu rồi tiếp tục từ phần còn lại. Điều này có thể tạo ra một cách tách khác, vì vậy cần định nghĩa token theo đúng cú pháp miền.

### 6.2. Không phải token dài hơn luôn được ưu tiên nếu không hợp lệ

Maximal munch chọn đoạn dài nhất **được chấp nhận bởi một quy tắc token**. Một chuỗi dài hơn nhưng không thuộc bất kỳ token nào không được chọn chỉ vì nó dài.

Ví dụ, nếu DSL chỉ định nghĩa `>` và `=`, nhưng không định nghĩa `>=`, đầu vào `>=` có thể được phân tích thành hai token `GREATER` và `ASSIGN` nếu grammar cho phép. Nếu grammar không cho phép chuỗi đó, parser sẽ báo lỗi. Quy tắc khớp dài nhất không tự thêm toán tử mới vào ngôn ngữ.

## 7. Thuật toán lexer theo maximal munch

Một lexer thủ công có thể triển khai maximal munch bằng cách ghi nhớ vị trí cuối cùng mà một trạng thái chấp nhận token.

Mô hình đơn giản:

```text
scanToken():
    start = current
    state = START
    lastAcceptingState = NONE
    lastAcceptingPosition = NONE

    while current < input.length:
        nextState = transition(state, input[current])

        if nextState does not exist:
            break

        state = nextState
        current = current + 1

        if state is accepting:
            lastAcceptingState = state
            lastAcceptingPosition = current

    if lastAcceptingState is NONE:
        report lexical error at start

    current = lastAcceptingPosition
    emit token for lastAcceptingState and input[start:current]
```

Đây là mã giả để minh họa nguyên tắc. Lexer thực tế còn phải xử lý trạng thái kết thúc, ưu tiên giữa các quy tắc cùng độ dài, chế độ chuỗi/comment, giá trị literal và phục hồi sau lỗi.

### 7.1. Ví dụ từng bước

Giả sử lexer có các toán tử `=`, `==` và `=>`. Đầu vào tại vị trí hiện tại là:

```text
==>
```

Một máy trạng thái có thể hoạt động như sau:

1. Đọc ký tự đầu `=`: trạng thái hiện tại đã chấp nhận token `=`.
2. Đọc ký tự thứ hai `=`: trạng thái chấp nhận token `==`; đây là điểm chấp nhận xa hơn.
3. Đọc ký tự thứ ba `>`: nếu không có token `==>` và không có chuyển tiếp hợp lệ từ trạng thái `==`, lexer dừng.
4. Phát token `==` theo điểm chấp nhận xa nhất.
5. Đặt con trỏ trước `>` để token tiếp theo được phân tích từ vị trí đó.

Nếu DSL có token `==>`, lexer sẽ tiếp tục đến ký tự thứ ba và chọn token dài hơn.

### 7.2. Lookahead và rollback

Lexer có thể đọc qua một số ký tự chưa thuộc token cuối cùng được chọn. Khi không còn chuyển tiếp hợp lệ, nó quay lại vị trí chấp nhận cuối cùng.

Ví dụ, nếu lexer đang xét `123abc` và grammar chỉ cho phép số nguyên là chữ số liên tiếp, nó có thể nhận diện `123` rồi tiếp tục với `abc` thành định danh, hoặc báo lỗi nếu DSL yêu cầu token liền nhau phải tuân theo một quy tắc khác. Cách xử lý phụ thuộc grammar và quy tắc token liền kề.

Rollback nên được giới hạn và có chủ đích. Với DFA, việc ghi lại điểm chấp nhận cuối giúp triển khai hiệu quả mà không cần thử từng regex độc lập trên toàn bộ chuỗi.

## 8. Cài đặt bằng thứ tự quy tắc và lexer generator

Một lexer nhỏ có thể dùng các nhánh kiểm tra thủ công. Một lexer lớn thường dùng lexer generator hoặc một máy trạng thái được sinh từ các biểu thức token.

### 8.1. Kiểm tra token dài trước token ngắn

Với danh sách toán tử cố định, cách đơn giản là sắp xếp theo độ dài giảm dần:

```java
List<String> operators = List.of(
    ">>=", "<<=", "==", "!=", ">=", "<=", "->", "+", "-", "=", ">", "<"
);
```

Lexer thử token dài trước, rồi mới thử token ngắn. Cách này dễ hiểu cho tập ký hiệu nhỏ, nhưng cần bảo đảm:

- Danh sách được sắp xếp đúng.
- Có kiểm tra ranh giới token nếu cần.
- Không nhầm lẫn giữa toán tử và phần đầu của literal hoặc định danh.
- Trường hợp bằng độ dài có quy tắc ưu tiên rõ.

Không nên dựa vào thứ tự phần tử trong `List.of` mà không có kiểm tra, vì một lần thêm toán tử mới có thể khiến thứ tự không còn đúng.

### 8.2. Trie cho tập token có tiền tố chung

Trie là cấu trúc cây ký tự dùng để lưu các chuỗi có tiền tố chung. Với các toán tử:

```text
>
>=
>>
>>=
```

Trie có thể chia sẻ các nút tiền tố `>` và `>>`, rồi ghi nhận những nút kết thúc token hợp lệ. Khi quét đầu vào, lexer đi sâu nhất có thể và lưu lại nút kết thúc hợp lệ xa nhất.

Ưu điểm:

- Tái sử dụng tiền tố chung.
- Dễ tìm token dài nhất trong một tập ký hiệu cố định.
- Có thể sinh tự động từ danh sách token.

Trie thường phù hợp với toán tử và dấu phân cách. Với tên, số và chuỗi có quy tắc phức tạp, lexer thường kết hợp nhiều máy trạng thái hoặc DFA.

### 8.3. DFA và lexer generator

Nhiều công cụ lexer generator chuyển các biểu thức token thành NFA rồi DFA hoặc một dạng máy trạng thái tương đương. Trong DFA, mỗi trạng thái có các chuyển tiếp theo ký tự và một số trạng thái là trạng thái chấp nhận.

Khi chạy DFA, lexer có thể:

1. Đi từ trạng thái bắt đầu.
2. Đọc ký tự và chuyển trạng thái.
3. Ghi nhận mọi trạng thái chấp nhận đã đi qua.
4. Dừng khi không còn chuyển tiếp.
5. Chọn trạng thái chấp nhận xa nhất.

Nếu nhiều quy tắc cùng chấp nhận ở điểm xa nhất, công cụ cần quy tắc phá hòa như thứ tự khai báo hoặc độ ưu tiên token.

## 9. Maximal munch và thứ tự ưu tiên quy tắc

Hai quy tắc thường bị nhầm lẫn:

- **Longest match:** ưu tiên lexeme dài hơn.
- **Rule priority:** khi nhiều quy tắc cùng khớp một đoạn có cùng độ dài, chọn quy tắc ưu tiên cao hơn.

Ví dụ:

```text
IF         = "if"
IDENTIFIER = [A-Za-z_][A-Za-z0-9_]*
```

Với `if`, cả hai quy tắc khớp hai ký tự. Độ dài bằng nhau nên lexer cần ưu tiên `IF` hoặc nhận `IDENTIFIER` rồi tra bảng từ khóa.

Với `ifelse`, quy tắc định danh khớp sáu ký tự, dài hơn token từ khóa `if`. Lexer phải chọn `IDENTIFIER("ifelse")`, không tách thành `IF` và `IDENTIFIER("else")` trừ khi DSL cố ý định nghĩa cú pháp ghép từ khóa theo cách đó.

### 9.1. Quy tắc tổng quát

Một chiến lược lexer phổ biến là:

1. Chọn lexeme có độ dài lớn nhất.
2. Nếu có nhiều quy tắc cùng khớp lexeme dài nhất, chọn quy tắc ưu tiên cao nhất.
3. Nếu vẫn hòa, dùng thứ tự khai báo hoặc báo lỗi cấu hình lexer tùy công cụ.

Một số lexer generator quy định thứ tự ưu tiên khác nhau. Cần đọc tài liệu công cụ đang dùng thay vì giả định mọi generator có cùng hành vi.

## 10. Maximal munch không phải là quy tắc phân tích cú pháp

Lexer và parser giải quyết hai lớp vấn đề khác nhau.

- Lexer xác định token từ chuỗi ký tự.
- Parser xác định cấu trúc cú pháp từ chuỗi token.

Ví dụ, lexer có thể nhận diện:

```text
NUMBER(1)
PLUS(+)
NUMBER(2)
MULTIPLY(*)
NUMBER(3)
```

với đầu vào:

```text
1 + 2 * 3
```

Maximal munch không quyết định phép nhân được nhóm trước phép cộng. Đó là nhiệm vụ của grammar hoặc quy tắc độ ưu tiên trong parser.

Tương tự, lexer có thể nhận diện một chuỗi token hoàn toàn hợp lệ về từ vựng nhưng parser vẫn từ chối vì cấu trúc không phù hợp.

### 10.1. Tokenization không giải quyết ngữ nghĩa

Lexer có thể nhận diện `Customer` là một định danh, nhưng không biết kiểu `Customer` có tồn tại trong namespace hiện tại hay không. Việc đó thuộc phân giải tên.

Lexer có thể nhận diện `42` là số, nhưng không biết số đó có nằm trong giới hạn của thuộc tính `replicas` hay không. Việc đó thuộc kiểm tra ngữ nghĩa hoặc validation.

### 10.2. Không sửa lỗi grammar bằng cách đổi luật khớp dài nhất

Nếu parser hiểu sai biểu thức do độ ưu tiên toán tử, thay đổi thứ tự token trong lexer không phải cách giải quyết đúng. Cần sửa grammar hoặc cấu hình precedence của parser.

## 11. Những trường hợp cần xử lý đặc biệt

Maximal munch là quy tắc hữu ích, nhưng không có nghĩa mọi token trong mọi ngữ cảnh đều được nhận diện theo cùng một chế độ.

### 11.1. Chuỗi ký tự

Khi lexer đã nhận dấu mở chuỗi, nó thường chuyển sang chế độ quét chuỗi (*string mode*). Trong chế độ này, dấu cách, toán tử hoặc ký hiệu comment có thể là nội dung chuỗi chứ không phải token độc lập.

Ví dụ:

```text
message = "a >= b // this is text"
```

`>=` và `//` bên trong chuỗi không được nhận diện thành toán tử hoặc comment. Lexer xử lý theo quy tắc literal chuỗi cho đến dấu đóng hợp lệ.

### 11.2. Comment

Nếu DSL hỗ trợ cả comment một dòng `//` và toán tử `/`, lexer cần phân biệt:

```text
total = amount / count
// calculate the total
```

Khi gặp `/`, lexer có thể cần nhìn ký tự tiếp theo để biết đó là phép chia hay bắt đầu comment `//`. Nếu comment được định nghĩa là token dài hơn, maximal munch có thể giúp chọn `//` khi cả hai ký tự tạo thành comment marker.

### 11.3. Chế độ từ vựng theo ngữ cảnh

Một số DSL dùng cú pháp đặc biệt trong chuỗi template, nội suy, biểu thức nhúng hoặc khối truy vấn. Lexer có thể chuyển giữa các lexical mode để áp dụng tập quy tắc khác nhau.

Ví dụ:

```text
template "Hello ${user.name}"
```

Phần ngoài chuỗi, phần văn bản literal và biểu thức bên trong `${...}` có thể dùng các quy tắc token khác nhau. Maximal munch được áp dụng trong từng chế độ theo tập quy tắc đang hoạt động.

### 11.4. Token phụ thuộc ngữ nghĩa

Một số trường hợp không thể quyết định chỉ bằng số ký tự, vì vai trò token phụ thuộc vào khai báo hoặc ngữ cảnh. Ví dụ, tên kiểu có thể được phân biệt với tên biến trong một số cú pháp.

Thông thường, nên để lexer phát token tổng quát như `IDENTIFIER`, rồi dùng parser hoặc semantic analysis để phân loại theo ngữ cảnh. Không nên ép lexer phải biết toàn bộ symbol table nếu điều đó làm các lớp phụ thuộc chặt chẽ.

## 12. Lỗi thường gặp khi áp dụng khớp dài nhất

### 12.1. Chọn token đầu tiên khớp

Nếu lexer kiểm tra `>` trước `>=` rồi dừng ngay khi tìm được token, đầu vào `>=` có thể bị tách sai. Cần tiếp tục quét để tìm điểm chấp nhận xa nhất.

### 12.2. Nhầm độ dài với độ ưu tiên ngữ nghĩa

Token dài hơn được chọn vì quy tắc từ vựng, không có nghĩa toán tử đó có độ ưu tiên cao hơn trong biểu thức. Precedence thuộc parser.

### 12.3. Quên trường hợp bằng độ dài

Từ khóa và định danh có thể cùng khớp một lexeme. Cần có tie-breaking hoặc chiến lược tra bảng từ khóa.

### 12.4. Cho rằng mọi tiền tố đều là token độc lập

Một token dài hơn có thể có tiền tố giống token ngắn. Khi token dài hơn được định nghĩa và khớp, lexer thường chọn token dài hơn. Nhưng nếu phần mở rộng không tạo thành token hợp lệ, lexer có thể chọn token ngắn rồi xử lý phần còn lại.

### 12.5. Bỏ qua ranh giới token

Nhận diện token dài nhất không đồng nghĩa bỏ qua quy tắc ranh giới. Ví dụ, nếu DSL có số và định danh, chuỗi `123abc` cần được xử lý theo quy tắc rõ: có thể tách thành số và định danh, hoặc báo lỗi literal không hợp lệ. Không nên để kết quả phụ thuộc vào chi tiết triển khai vô tình.

### 12.6. Dùng regex độc lập mà không xét tương tác

Một regex có thể khớp đúng token khi chạy riêng, nhưng nhiều regex kết hợp lại có thể tạo xung đột. Lexer cần có chính sách toàn cục về longest match, tie-breaking và lexical mode.

### 12.7. Thêm token mới làm thay đổi cách tách mã cũ

Thêm toán tử dài hơn hoặc từ khóa mới có thể thay đổi cách token hóa một chương trình cũ. DSL cần kiểm thử tương thích từ vựng khi mở rộng tập token.

## 13. Kiểm thử quy tắc khớp dài nhất

Nên kiểm thử theo nhóm tiền tố chung. Với mỗi nhóm, chuẩn bị trường hợp token ngắn, token dài, chuỗi gần giống và chuỗi không hợp lệ.

### 13.1. Kiểm thử toán tử

Nếu DSL có `=`, `==`, `=>` và `>=`, hãy kiểm tra từng token riêng, kết hợp với khoảng trắng và trong biểu thức:

```text
a = b
a == b
a => b
a >= b
a > = b
```

Kết quả mong đợi cần được xác định từ đặc tả token, không suy đoán theo hình thức hiển thị.

### 13.2. Kiểm thử từ khóa và định danh

Với từ khóa `if`, kiểm tra:

```text
if
ifx
if_2
if9
```

`if` có thể là token từ khóa, còn các chuỗi dài hơn thường là định danh nếu grammar định nghĩa như vậy.

### 13.3. Kiểm thử số và dấu chấm

Nếu DSL có số thập phân và toán tử khoảng, kiểm tra:

```text
12
12.5
1..10
1.0..2.0
```

Đảm bảo lexer không nhận nhầm dấu chấm thập phân với toán tử khoảng.

### 13.4. Kiểm thử comment và chuỗi

Kiểm tra ký hiệu toán tử và comment trong chuỗi, chuỗi escape, comment bắt đầu bằng tiền tố chung với toán tử và comment chưa đóng nếu DSL hỗ trợ comment nhiều dòng.

### 13.5. Kiểm thử vị trí nguồn và phục hồi

Khi lexer đọc thêm rồi quay lại điểm chấp nhận cuối, vị trí token vẫn phải chính xác. Sau lỗi từ vựng, con trỏ cần tiến lên hoặc áp dụng chiến lược phục hồi để tránh lặp vô hạn tại cùng ký tự.

## 14. Ví dụ tổng hợp: thiết kế lexer cho DSL điều kiện

Giả sử DSL điều kiện hỗ trợ:

```text
if score >= 90 and level != "guest" then award = true
```

Tập token liên quan:

| Nhóm | Token |
|---|---|
| Từ khóa | `IF`, `AND`, `THEN` |
| Định danh | `IDENTIFIER` |
| Toán tử | `GREATER_EQUAL`, `NOT_EQUAL`, `ASSIGN`, `GREATER`, `EQUAL` |
| Literal | `NUMBER`, `STRING`, `BOOLEAN` |

Lexer có thể dùng các quy tắc:

```text
">="  -> GREATER_EQUAL
">"   -> GREATER
"!="  -> NOT_EQUAL
"!"   -> BANG (nếu DSL có)
"=="  -> EQUAL_EQUAL
"="   -> ASSIGN
```

Khi quét `>=`, lexer đi qua trạng thái chấp nhận `>` rồi tiếp tục đến trạng thái chấp nhận `>=`. Nó chọn trạng thái chấp nhận xa hơn. Khi quét `>` đứng riêng, không có ký tự tiếp theo phù hợp để tạo toán tử dài hơn, nên token `GREATER` được phát.

Khi quét `if`, lexer nhận diện lexeme định danh dài nhất rồi tra bảng từ khóa để phát `IF`. Khi quét `ifScore`, toàn bộ chuỗi là một định danh dài hơn và không bị tách thành `IF` cùng `Score`.

Parser sau đó nhận chuỗi token và xây dựng biểu thức điều kiện. Độ ưu tiên giữa `and`, `>=` và `!=` do grammar hoặc quy tắc precedence quyết định, không phải maximal munch.

## 15. Ghi nhớ

- Quy tắc khớp dài nhất yêu cầu lexer chọn lexeme hợp lệ dài nhất bắt đầu tại vị trí hiện tại.
- Quy tắc này đặc biệt hữu ích với toán tử và dấu phân cách có tiền tố chung như `>`, `>=`, `>>` và `>>=`.
- Khi nhiều quy tắc cùng khớp một lexeme có cùng độ dài, cần quy tắc phá hòa như ưu tiên token hoặc bảng từ khóa.
- Định danh thường được đọc hết trước rồi mới tra bảng từ khóa, nhờ đó `ifx` không bị tách thành `if` và `x`.
- Maximal munch có thể được triển khai bằng DFA, trie hoặc lexer thủ công có ghi nhớ điểm chấp nhận cuối.
- Lexer có thể cần lookahead và quay lại điểm chấp nhận cuối để phát token dài nhất.
- Quy tắc này không quyết định độ ưu tiên toán tử, cấu trúc grammar hoặc ý nghĩa ngữ nghĩa.
- Chuỗi, comment, literal số và lexical mode cần quy tắc riêng để tránh nhận diện sai tiền tố.
- Khi mở rộng tập token, cần kiểm thử các tiền tố chung và khả năng tương thích của chương trình cũ.

## 16. Câu hỏi tự kiểm tra

1. Quy tắc khớp dài nhất là gì? Lexer chọn token dựa trên tiêu chí nào?
2. Nếu DSL có `>`, `>=`, `>>` và `>>=`, lexer phải xử lý đầu vào `>>=` như thế nào?
3. Vì sao chuỗi `ifx` không nên bị tách thành từ khóa `if` và định danh `x` nếu định danh dài hơn được chấp nhận?
4. Maximal munch khác quy tắc ưu tiên giữa các token cùng độ dài như thế nào?
5. Vì sao lexer thường nhận diện định danh trước rồi tra bảng từ khóa?
6. Maximal munch giải quyết được điều gì và không giải quyết được điều gì trong quá trình biên dịch DSL?
7. Mô tả cách lexer dùng trạng thái chấp nhận cuối để đọc token dài nhất.
8. Vì sao `1..10` có thể cần quy tắc đặc biệt khi DSL hỗ trợ cả số thập phân và toán tử khoảng?
9. Lexer cần làm gì để phân biệt `//` là comment với `/` là phép chia?
10. Nêu các trường hợp kiểm thử quan trọng khi thêm một toán tử mới có tiền tố chung với toán tử cũ.
