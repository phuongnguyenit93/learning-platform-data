# Khoảng trắng

Trong một DSL (*Domain-Specific Language* – ngôn ngữ chuyên biệt theo miền), từ vựng (*lexicon*) gồm các đơn vị mà công cụ nhận diện khi đọc văn bản nguồn: từ khóa, tên định danh, số, chuỗi, toán tử, dấu phân cách và những ký hiệu khác. **Khoảng trắng** (*whitespace*) là một phần quan trọng của lớp từ vựng vì nó có thể tách các token, giúp mã dễ đọc hoặc thậm chí biểu diễn cấu trúc của chương trình.

Khoảng trắng thường gồm dấu cách, tab, ký tự xuống dòng và một số ký tự phân cách dòng khác. Tùy thiết kế DSL, chúng có thể chỉ phục vụ trình bày, có thể là dấu phân cách bắt buộc giữa token, hoặc có thể mang ý nghĩa cấu trúc như xác định phạm vi khối lệnh.

Vì vậy, khi thiết kế DSL, cần quy định rõ khoảng trắng được xử lý như thế nào ở từng ngữ cảnh. Nếu đặc tả không rõ, cùng một tệp có thể được hiểu khác nhau bởi lexer, parser, formatter hoặc công cụ chạy trên các hệ điều hành khác nhau.

## 1. Khoảng trắng gồm những ký tự nào?

Trong nhiều ngôn ngữ, các ký tự khoảng trắng thường gặp gồm:

| Ký tự | Tên thường gọi | Cách dùng phổ biến |
|---|---|---|
| U+0020 | Dấu cách (space) | Tách từ khóa, tên và giá trị |
| U+0009 | Tab ngang (horizontal tab) | Thụt lề hoặc căn chỉnh |
| U+000A | Line Feed (LF) | Kết thúc dòng trên nhiều hệ thống Unix-like |
| U+000D | Carriage Return (CR) | Kết thúc dòng kiểu cũ hoặc kết hợp với LF |
| U+000D U+000A | CRLF | Cách kết thúc dòng phổ biến trên Windows |
| U+000C | Form feed | Ít gặp trong DSL hiện đại; cần quy định nếu chấp nhận |

Unicode còn có những ký tự phân cách và khoảng trắng khác. Một DSL có thể chỉ chấp nhận dấu cách ASCII và tab, hoặc chấp nhận một tập Unicode rộng hơn. Điều quan trọng là lexer và các công cụ liên quan phải dùng cùng một quy tắc.

Không nên mặc định rằng mọi ký tự trông giống dấu cách đều được xử lý giống nhau. Ví dụ, dấu cách không ngắt dòng (*non-breaking space*) có thể xuất hiện khi sao chép văn bản từ tài liệu hoặc trang web. Nếu DSL không hỗ trợ nó, công cụ nên báo lỗi dễ hiểu thay vì âm thầm xử lý khác với dấu cách thông thường.

## 2. Khoảng trắng dùng để tách token

Một vai trò cơ bản của khoảng trắng là tạo ranh giới giữa các token. Lexer đọc chuỗi ký tự và xác định các đơn vị như từ khóa, định danh, số hoặc toán tử.

Ví dụ:

```text
select name from employees
```

Lexer có thể nhận diện bốn từ khóa hoặc định danh riêng:

```text
KEYWORD("select")
IDENTIFIER("name")
KEYWORD("from")
IDENTIFIER("employees")
```

Nếu bỏ toàn bộ khoảng trắng:

```text
selectnamefromemployees
```

chuỗi này có thể trở thành một định danh duy nhất thay vì bốn token. Khoảng trắng vì thế không chỉ giúp trình bày; trong nhiều trường hợp nó là dấu phân cách từ vựng cần thiết.

### 2.1. Khoảng trắng giữa từ khóa và định danh

Một từ khóa và tên định danh thường cần được tách rõ:

```text
service catalog
```

Nếu DSL quy định `service` là từ khóa và `catalog` là tên dịch vụ, lexer cần nhận ra hai token. Nếu không có dấu phân cách, công cụ có thể đọc `servicecatalog` như một định danh.

### 2.2. Khoảng trắng quanh toán tử

Nhiều DSL cho phép hoặc khuyến khích đặt khoảng trắng quanh toán tử:

```text
total = price + tax
```

Một số DSL vẫn nhận diện được biểu thức khi không có khoảng trắng:

```text
total=price+tax
```

Tuy nhiên, khả năng bỏ khoảng trắng phụ thuộc vào cách token được phân định. Ví dụ, nếu dấu `-` vừa có thể là toán tử trừ vừa có thể xuất hiện trong tên định danh, `item-count` có thể khó phân tích nếu grammar không quy định rõ.

Một lexer thường dùng quy tắc khớp dài nhất (*maximal munch*) để chọn token hợp lệ dài nhất tại vị trí hiện tại. Quy tắc này giải quyết một số trường hợp như `>=` so với `>`, nhưng không thể thay thế việc thiết kế ranh giới token rõ ràng.

### 2.3. Khoảng trắng không phải lúc nào cũng bắt buộc

Nếu ký hiệu đã tạo ranh giới token rõ ràng, khoảng trắng có thể là tùy chọn:

```text
call(name, age)
call ( name , age )
```

Hai cách viết có thể tạo cùng cấu trúc nếu grammar không gán ý nghĩa khác cho khoảng trắng giữa tên hàm và dấu ngoặc. Tuy nhiên, có ngôn ngữ quy định khoảng trắng đó có ý nghĩa, nên không được suy luận rằng mọi DSL đều xử lý giống nhau.

## 3. Khoảng trắng không mang ý nghĩa cấu trúc

Một DSL được gọi là không nhạy khoảng trắng (*whitespace-insensitive*) trong một phạm vi nào đó nếu việc thay đổi khoảng trắng ở phạm vi ấy không làm thay đổi cấu trúc hoặc kết quả chương trình.

Ví dụ, nếu dấu xuống dòng chỉ để trình bày, hai câu lệnh sau có thể tương đương:

```text
select name, salary from employees where salary > 50000
```

```text
select name,
       salary
from employees
where salary > 50000
```

Trong trường hợp này, lexer bỏ qua khoảng trắng và dấu xuống dòng ngoài chuỗi, comment hoặc những ngữ cảnh đặc biệt. Parser chỉ nhận chuỗi token nên không cần biết người viết đặt bao nhiêu dấu cách giữa chúng.

### 3.1. Quy tắc bỏ qua khoảng trắng

Một lexer đơn giản có thể xử lý khoảng trắng theo trình tự:

1. Đọc ký tự hiện tại.
2. Nếu là dấu cách hoặc tab được phép bỏ qua, chuyển sang ký tự tiếp theo.
3. Nếu là ký tự xuống dòng không có ý nghĩa cấu trúc, cập nhật vị trí dòng/cột rồi tiếp tục.
4. Nếu là comment, bỏ qua phần comment theo quy tắc của DSL.
5. Nếu không phải khoảng trắng, bắt đầu nhận diện token.

Ví dụ mã giả:

```text
while not end_of_input:
    if current_character is horizontal_whitespace:
        advance()
    else if current_character is newline:
        update_line_and_column()
        advance()
    else if starts_comment():
        skip_comment()
    else:
        emit(next_token())
```

Đây chỉ là mô hình đơn giản. Lexer thực tế cần xử lý chuỗi, escape, comment nhiều dòng, Unicode, lỗi đầu vào và vị trí nguồn một cách nhất quán.

### 3.2. Bỏ qua khoảng trắng không có nghĩa là xóa mọi dấu cách

Ngay cả trong DSL không nhạy khoảng trắng, dấu cách vẫn cần thiết để tách các token có thể dính vào nhau. Lexer có thể bỏ qua khoảng trắng sau khi dùng nó để kết thúc token trước và bắt đầu token sau.

Ví dụ, `from employees` cần được tách thành `from` và `employees`. Nếu chỉ xóa dấu cách trước khi phân tích, chuỗi sẽ trở thành `fromemployees` và mất ranh giới token.

## 4. Khoảng trắng có ý nghĩa cấu trúc

Một DSL nhạy khoảng trắng (*whitespace-sensitive*) sử dụng vị trí hoặc số lượng khoảng trắng để xác định cấu trúc. Phổ biến nhất là dùng mức thụt lề để biểu diễn khối lệnh.

Ví dụ cú pháp giả định:

```text
pipeline daily_report:
    source employees.csv
    filter department == "Engineering"
    output report.csv
```

Ba dòng được thụt lề nằm trong khối `pipeline`. Nếu bỏ thụt lề hoặc thay đổi mức thụt lề, cấu trúc có thể không còn hợp lệ.

Trong DSL dạng này, lexer không thể bỏ qua toàn bộ khoảng trắng. Nó cần theo dõi mức thụt lề và phát ra token cấu trúc, chẳng hạn:

```text
KEYWORD("pipeline")
IDENTIFIER("daily_report")
COLON
NEWLINE
INDENT
KEYWORD("source")
IDENTIFIER("employees.csv")
NEWLINE
KEYWORD("filter")
...
NEWLINE
KEYWORD("output")
...
NEWLINE
DEDENT
```

`INDENT` và `DEDENT` là token ảo do lexer tạo ra. Chúng không tương ứng với ký tự riêng trong tệp, mà phản ánh thay đổi mức thụt lề.

### 4.1. Ngăn xếp mức thụt lề

Một cách triển khai thường gặp là dùng ngăn xếp (*stack*) lưu các mức thụt lề hiện tại. Ban đầu, ngăn xếp chứa mức `0`.

Khi bắt đầu một dòng mới:

- Nếu mức thụt lề tăng so với dòng trước, lexer đẩy mức mới vào stack và phát `INDENT`.
- Nếu mức thụt lề giảm, lexer phát một hoặc nhiều `DEDENT` cho đến khi trở về mức đã có trong stack.
- Nếu mức thụt lề mới không khớp với bất kỳ mức nào đang có, lexer báo lỗi thụt lề không nhất quán.
- Nếu mức thụt lề không đổi, không phát token cấu trúc mới.

Ví dụ:

```text
root:
    first:
        nested
    second
after
```

Các mức thụt lề lần lượt là `0`, `4`, `8`, `4`, `0`. Lexer phát `INDENT` khi đi từ `0` lên `4` và từ `4` lên `8`; phát `DEDENT` khi quay về `4` và sau đó về `0`.

### 4.2. Quy tắc tab và dấu cách

Nếu thụt lề mang ý nghĩa cú pháp, DSL phải quy định tab và dấu cách được xử lý thế nào. Một lựa chọn phổ biến là chỉ cho phép dấu cách để thụt lề, hoặc quy định tab tương đương một số cột cố định.

Trộn tab và dấu cách có thể làm mức thụt lề hiển thị khác nhau giữa editor. Ví dụ, cùng một ký tự tab có thể được hiển thị rộng 2, 4 hoặc 8 cột tùy thiết lập. Vì vậy, một DSL nhạy thụt lề nên:

- Chọn một quy tắc thụt lề duy nhất.
- Phát hiện và báo lỗi khi trộn tab và dấu cách nếu cách kết hợp không được hỗ trợ.
- Cung cấp formatter để chuẩn hóa mức thụt lề.
- Hiển thị vị trí lỗi rõ ràng khi mức thụt lề không khớp.

### 4.3. Dòng trống và dòng chỉ có comment

DSL cần quy định dòng trống và dòng chỉ chứa comment có ảnh hưởng đến cấu trúc hay không. Thông thường, các dòng này không tạo khối mới và không làm thay đổi mức thụt lề. Tuy nhiên, nếu comment được gắn với khai báo kế tiếp hoặc có ý nghĩa metadata, công cụ cần giữ thông tin liên quan.

## 5. Dấu xuống dòng và ranh giới câu lệnh

Dấu xuống dòng có thể chỉ là khoảng trắng trình bày, nhưng cũng có thể đóng vai trò kết thúc câu lệnh.

Ví dụ, một DSL khai báo có thể dùng mỗi dòng là một thuộc tính:

```text
replicas = 3
region = "asia-southeast1"
enabled = true
```

Nếu dấu xuống dòng kết thúc câu lệnh, lexer hoặc parser cần nhận diện token `NEWLINE`. Ngược lại, nếu DSL cho phép biểu thức kéo dài qua nhiều dòng, cần quy định khi nào newline được bỏ qua hoặc tiếp tục biểu thức.

### 5.1. Dòng mới có ý nghĩa như dấu chấm phẩy

Một số DSL dùng newline để phân tách câu lệnh thay cho dấu `;`. Cách này dễ đọc với cấu hình và script ngắn, nhưng cần quy tắc cho câu lệnh nhiều dòng.

Ví dụ:

```text
select name,
       salary
from employees
```

Nếu newline luôn kết thúc câu lệnh, dòng đầu sẽ bị xem là một câu lệnh chưa hoàn chỉnh. Có thể giải quyết bằng cách cho phép tiếp tục khi cú pháp đang ở trong ngoặc, sau dấu phẩy hoặc sau toán tử, hoặc yêu cầu dấu nối dòng rõ ràng.

### 5.2. Dòng mới bị bỏ qua trong biểu thức nhiều dòng

Một DSL có thể cho phép:

```text
total = price
        + tax
        + shipping
```

Để phân tích đúng, lexer hoặc parser phải biết biểu thức vẫn đang tiếp tục. Một cách thường dùng là giữ trạng thái độ sâu ngoặc: khi đang ở trong `(` hoặc `[`, newline có thể được coi như khoảng trắng. Ngoài ngoặc, quy tắc có thể dựa vào token trước đó hoặc ký hiệu nối dòng.

### 5.3. Kết thúc câu lệnh ngầm định

Một số ngôn ngữ tự chèn dấu kết thúc câu lệnh khi gặp newline ở vị trí phù hợp. Nếu DSL chọn cách này, cần định nghĩa chính xác điều kiện chèn để tránh trường hợp cùng một chương trình bị hiểu khác khi xuống dòng.

Đặc biệt, không nên chỉ dựa vào hình thức xuống dòng để suy đoán nếu một biểu thức có thể tiếp tục. Đặc tả cần mô tả các token trước và sau newline có cho phép kết thúc câu lệnh hay không.

## 6. Khoảng trắng bên trong literal và comment

Quy tắc bỏ qua khoảng trắng thường chỉ áp dụng bên ngoài các vùng văn bản có nội dung riêng. Trong chuỗi ký tự, khoảng trắng thường là dữ liệu và phải được giữ nguyên.

Ví dụ:

```text
message = "Hello     world"
```

Nhiều dấu cách bên trong chuỗi có thể là một phần của giá trị. Nếu lexer chuẩn hóa chúng thành một dấu cách, nội dung người dùng muốn biểu diễn sẽ bị thay đổi.

### 6.1. Chuỗi nhiều dòng

Nếu DSL hỗ trợ chuỗi nhiều dòng, cần quy định dấu xuống dòng có được giữ lại, chuẩn hóa hay escape. Ví dụ:

```text
description = """
First line
    Second line
Third line
"""
```

Một số ngôn ngữ giữ nguyên toàn bộ khoảng trắng trong chuỗi nhiều dòng; một số có quy tắc loại bỏ phần thụt lề chung. Đây là ngữ nghĩa của literal và cần được đặc tả riêng, không nên nhầm với quy tắc thụt lề của chương trình.

### 6.2. Chuỗi có escape

DSL có thể cho phép escape để biểu diễn ký tự đặc biệt:

```text
message = "first line\nsecond line"
path = "C:\\data\\report.csv"
```

Lexer cần phân biệt ký tự gạch chéo ngược dùng để escape với dấu phân cách thật. Quy tắc này giúp xử lý đúng dấu nháy, tab, newline và ký tự đặc biệt bên trong chuỗi.

### 6.3. Comment

Comment thường bị bỏ qua khi tạo token, nhưng vị trí của comment có thể hữu ích cho formatter, tài liệu hoặc công cụ chỉnh sửa mã.

Ví dụ:

```text
# Số bản sao của dịch vụ
replicas = 3
```

Nếu DSL hỗ trợ comment cuối dòng:

```text
replicas = 3  # giữ ba bản sao
```

Lexer cần biết comment bắt đầu ở đâu và kết thúc ở đâu. Nếu ký hiệu comment xuất hiện trong chuỗi, nó phải được xem là dữ liệu:

```text
url = "https://example.com/path#section"
```

Ở ví dụ này, `#section` thuộc chuỗi URL chứ không phải comment.

## 7. Chuẩn hóa khoảng trắng

Chuẩn hóa (*normalization*) là việc chuyển các cách trình bày tương đương về một dạng thống nhất. Với DSL không nhạy khoảng trắng, formatter có thể chuẩn hóa khoảng trắng bên ngoài literal và comment theo quy tắc định dạng.

Ví dụ:

```text
before: total=price+tax
after:  total = price + tax
```

Nếu grammar xem hai cách viết là tương đương, formatter có thể tạo đầu ra chuẩn để mã dễ đọc và diff trong version control ít nhiễu hơn.

Tuy nhiên, cần phân biệt ba việc:

- **Bỏ qua khoảng trắng khi phân tích:** lexer không tạo token cho khoảng trắng không có ý nghĩa.
- **Chuẩn hóa định dạng:** formatter thay đổi cách trình bày mà không đổi ý nghĩa chương trình.
- **Chuẩn hóa giá trị:** xử lý nội dung literal theo quy tắc miền, ví dụ chuẩn hóa dạng ngày hoặc đơn vị. Đây là việc khác với định dạng văn bản.

Không nên xóa hoặc gộp khoảng trắng một cách mù quáng trên toàn bộ văn bản nguồn. Cách làm đó có thể thay đổi chuỗi, comment, dữ liệu nhiều dòng hoặc nội dung được nhúng.

## 8. Kết thúc dòng và tính di động giữa hệ điều hành

Các hệ điều hành có thể lưu dấu kết thúc dòng theo cách khác nhau:

- LF (`\n`) thường gặp trên Linux và macOS hiện đại.
- CRLF (`\r\n`) thường gặp trên Windows.
- CR (`\r`) xuất hiện trong một số định dạng cũ.

Nếu DSL coi newline là dấu phân cách câu lệnh hoặc dùng newline để tạo `INDENT`/`DEDENT`, lexer cần xử lý các kiểu kết thúc dòng nhất quán. Nếu không, cùng một tệp có thể tạo số dòng hoặc token khác nhau trên các nền tảng.

Một số nguyên tắc thực tế:

- Chấp nhận LF và CRLF theo một quy tắc thống nhất nếu cần hỗ trợ nhiều hệ điều hành.
- Không đếm CRLF thành hai dòng logic.
- Chuẩn hóa định dạng tệp khi lưu bằng formatter hoặc quy ước repository.
- Giữ đúng offset nguồn nếu công cụ cần chỉ vị trí ký tự.
- Xử lý BOM nếu DSL cho phép tệp UTF-8 có byte order mark.

## 9. Ảnh hưởng của khoảng trắng đến lexer và parser

Thiết kế khoảng trắng tác động đến nhiều thành phần của công cụ DSL.

| Thành phần | DSL không nhạy khoảng trắng | DSL nhạy khoảng trắng |
|---|---|---|
| Lexer | Thường bỏ qua dấu cách, tab và newline không có ý nghĩa | Phải giữ newline hoặc tạo token từ mức thụt lề |
| Parser | Dựa chủ yếu vào token nội dung | Phải xử lý token layout và ranh giới dòng |
| Grammar | Thường không mô tả dấu cách trình bày | Có thể chứa `NEWLINE`, `INDENT`, `DEDENT` hoặc quy tắc dòng |
| Formatter | Chuẩn hóa khoảng trắng mà không đổi cấu trúc | Phải giữ đúng mức thụt lề và ranh giới dòng |
| Thông báo lỗi | Cần vị trí dòng/cột dù khoảng trắng bị bỏ qua | Cần chỉ rõ lỗi thụt lề hoặc kết thúc dòng |
| Kiểm thử | Kiểm tra nhiều cách đặt khoảng trắng tương đương | Kiểm tra mức thụt lề, dòng trống và kiểu newline |

Một lexer có thể bỏ qua khoảng trắng trong hầu hết chương trình nhưng vẫn giữ newline trong một số trạng thái. Ví dụ, newline bên trong chuỗi nhiều dòng không được xử lý giống newline giữa hai câu lệnh.

## 10. Thiết kế chính sách khoảng trắng cho DSL

Khi thiết kế DSL, nên ghi rõ chính sách khoảng trắng trong đặc tả ngôn ngữ thay vì để mỗi công cụ tự suy đoán.

### 10.1. Xác định nhóm ký tự được chấp nhận

Quy định dấu cách, tab, newline, CRLF và ký tự Unicode nào được chấp nhận. Nếu chỉ chấp nhận một tập hẹp, công cụ nên báo lỗi có vị trí cho các ký tự khác.

### 10.2. Xác định nơi khoảng trắng có ý nghĩa

Phân biệt rõ:

- Khoảng trắng giữa token.
- Khoảng trắng trong biểu thức.
- Khoảng trắng đầu dòng và cuối dòng.
- Khoảng trắng dùng để thụt lề.
- Khoảng trắng bên trong chuỗi hoặc literal.
- Khoảng trắng trong comment.

Không nhất thiết phải có cùng quy tắc cho mọi vùng.

### 10.3. Chọn DSL nhạy hay không nhạy thụt lề

DSL nhạy thụt lề có thể tạo cấu trúc gọn và dễ đọc cho cấu hình phân cấp hoặc script. Đổi lại, lexer và formatter phức tạp hơn, và người dùng cần tuân thủ quy tắc tab/dấu cách.

DSL dùng dấu ngoặc để nhóm khối thường ít phụ thuộc vào trình soạn thảo hơn, nhưng phải có dấu mở/đóng rõ ràng. Lựa chọn nên dựa trên người dùng, môi trường viết và độ phức tạp cấu trúc.

### 10.4. Định nghĩa cách xuống dòng trong biểu thức

Quy định newline có kết thúc câu lệnh không, có thể tiếp tục biểu thức qua dòng hay không, và dấu ngoặc ảnh hưởng đến việc tiếp tục như thế nào. Cần có ví dụ hợp lệ và không hợp lệ cho từng trường hợp.

### 10.5. Bảo toàn khoảng trắng trong literal

Chuỗi và literal nhiều dòng cần có quy tắc riêng. Formatter hoặc bước chuẩn hóa không được thay đổi dữ liệu bên trong literal nếu không có quy định ngữ nghĩa rõ ràng.

### 10.6. Cung cấp formatter và style guide

Formatter nên tạo cách trình bày thống nhất, xử lý đúng chuỗi/comment và giữ cấu trúc của DSL nhạy khoảng trắng. Style guide nên quy định thụt lề, cách xuống dòng, dấu cách quanh toán tử và vị trí comment.

## 11. Ví dụ so sánh ba cách xử lý khoảng trắng

### 11.1. DSL không nhạy khoảng trắng

Hai đoạn sau có thể tương đương:

```text
set replicas=3
set region="asia-southeast1"
```

```text
set    replicas = 3

set region = "asia-southeast1"
```

Lexer bỏ qua khoảng trắng trình bày và parser nhận cùng cấu trúc token, miễn là DSL không gán ý nghĩa đặc biệt cho dòng trống.

### 11.2. DSL dùng newline làm dấu kết thúc câu lệnh

```text
replicas = 3
region = "asia-southeast1"
```

Mỗi newline kết thúc một khai báo. Nếu muốn viết một biểu thức nhiều dòng, DSL phải có quy tắc tiếp tục dòng.

### 11.3. DSL dùng thụt lề để tạo khối

```text
service catalog:
    replicas = 3
    network:
        port = 8080
```

Mức thụt lề xác định thuộc tính nằm trong dịch vụ hay trong khối `network`. Thay đổi thụt lề có thể làm thay đổi cây cú pháp.

Ba cách này có thể cùng tồn tại ở những DSL khác nhau. Điều quan trọng là mỗi ngôn ngữ phải có chính sách nhất quán và công cụ hiểu đúng chính sách đó.

## 12. Kiểm thử khoảng trắng

Khoảng trắng dễ tạo ra lỗi khó nhận thấy vì nhiều trường hợp trông giống nhau trong trình soạn thảo. Nên kiểm thử cả trường hợp hợp lệ, không hợp lệ và các biến thể nền tảng.

### 12.1. Kiểm thử token separation

Kiểm tra từ khóa và định danh có được tách đúng không, các toán tử dài có được nhận diện đúng không và khoảng trắng có bị bỏ ở vị trí làm thay đổi token hay không.

Ví dụ cần so sánh:

```text
from employees
fromemployees
a >= b
a > = b
```

Kết quả mong đợi phụ thuộc grammar, nhưng phải được xác định trước trong đặc tả.

### 12.2. Kiểm thử newline

Kiểm tra LF, CRLF, dòng trống, dòng cuối không có newline, comment cuối dòng và biểu thức kéo dài qua nhiều dòng.

### 12.3. Kiểm thử thụt lề

Nếu DSL dùng thụt lề, kiểm tra:

- Mức thụt lề tăng một cấp.
- Mức thụt lề giảm một cấp hoặc nhiều cấp.
- Dòng có mức thụt lề không khớp.
- Trộn tab và dấu cách.
- Dòng trống và dòng chỉ có comment.
- Khối cuối tệp chưa được đóng theo quy tắc.

### 12.4. Kiểm thử literal và comment

Đảm bảo khoảng trắng bên trong chuỗi được giữ đúng, escape được giải mã đúng, ký hiệu comment bên trong chuỗi không kết thúc chuỗi và comment nhiều dòng không làm sai vị trí nguồn.

### 12.5. Kiểm thử formatter

Formatter cần giữ nguyên ý nghĩa chương trình. Có thể kiểm tra bằng cách phân tích trước và sau khi định dạng rồi so sánh AST hoặc IR chuẩn hóa. Với DSL nhạy khoảng trắng, formatter phải giữ chính xác cấu trúc khối.

## 13. Những sai lầm thường gặp

**Xóa mọi khoảng trắng trước khi phân tích.** Việc này làm dính token, thay đổi chuỗi và có thể phá comment hoặc literal nhiều dòng.

**Cho rằng newline luôn tương đương dấu cách.** Một số DSL dùng newline để kết thúc câu lệnh hoặc xác định cấu trúc khối.

**Trộn tab và dấu cách trong DSL nhạy thụt lề.** Cách hiển thị khác nhau giữa editor có thể khiến người viết và lexer hiểu mức thụt lề khác nhau.

**Không phân biệt khoảng trắng ngoài và trong chuỗi.** Khoảng trắng trong literal thường là dữ liệu; chuẩn hóa chúng có thể làm thay đổi nội dung chương trình.

**Bỏ qua CRLF và LF.** Nếu newline có ý nghĩa cú pháp, xử lý không thống nhất có thể làm tệp chạy khác nhau trên các hệ điều hành.

**Không giữ vị trí nguồn khi bỏ qua khoảng trắng.** Lexer vẫn cần cập nhật dòng, cột và offset để thông báo lỗi chỉ đúng vị trí.

**Để formatter tự quyết định cú pháp.** Formatter phải tuân theo đặc tả; nó không được thay đổi cấu trúc chỉ vì một cách trình bày trông đẹp hơn.

## 14. Ghi nhớ

- Khoảng trắng gồm dấu cách, tab, newline và các ký tự phân cách khác; tập ký tự hợp lệ cần được đặc tả.
- Khoảng trắng thường tách token, nhưng mức độ ảnh hưởng đến cú pháp tùy DSL.
- DSL không nhạy khoảng trắng có thể bỏ qua khoảng trắng trình bày bên ngoài literal và comment.
- DSL nhạy khoảng trắng có thể dùng newline hoặc thụt lề để xác định câu lệnh và khối lệnh.
- Lexer của DSL nhạy thụt lề có thể tạo token ảo `INDENT` và `DEDENT` từ mức thụt lề.
- Khoảng trắng bên trong chuỗi thường là dữ liệu và cần được bảo toàn.
- Cần xử lý nhất quán LF, CRLF, tab, Unicode, comment và vị trí nguồn.
- Formatter và kiểm thử phải tuân theo cùng chính sách khoảng trắng của ngôn ngữ.

## 15. Câu hỏi tự kiểm tra

1. Khoảng trắng có những vai trò nào trong quá trình phân tích từ vựng của DSL?
2. Vì sao không thể xóa mọi dấu cách trước khi lexer nhận diện token?
3. DSL không nhạy khoảng trắng khác DSL nhạy khoảng trắng như thế nào?
4. Token `INDENT` và `DEDENT` được tạo ra từ thông tin nào?
5. Vì sao cần quy định cách xử lý tab và dấu cách trong DSL dùng thụt lề?
6. Newline có thể được dùng làm dấu kết thúc câu lệnh trong những trường hợp nào?
7. Vì sao formatter không được tự ý gộp khoảng trắng bên trong chuỗi?
8. CRLF và LF có thể gây vấn đề gì nếu newline mang ý nghĩa cú pháp?
9. Hãy nêu các trường hợp cần kiểm thử khi xây dựng lexer cho một DSL nhạy khoảng trắng.
10. Một DSL cấu hình dùng thụt lề để nhóm thuộc tính. Cần quy định những gì để tệp có cùng cách hiểu trên nhiều trình soạn thảo?
