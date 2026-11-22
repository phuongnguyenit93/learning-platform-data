# Chế độ lexer trong phân tích từ vựng DSL

## Mục tiêu học tập

Sau bài học này, người học có thể:

- Giải thích chế độ lexer (lexer mode) và lý do một lexer cần nhiều chế độ từ vựng.
- Phân biệt chế độ từ vựng với trạng thái nội bộ của máy quét và với trạng thái cú pháp của parser.
- Mô tả cách lexer chuyển giữa các chế độ khi gặp dấu phân cách hoặc cấu trúc đặc biệt.
- Thiết kế chế độ riêng cho văn bản thường, chuỗi, chú thích, nội suy biểu thức và ngôn ngữ nhúng.
- Hiểu cách dùng ngăn xếp chế độ để xử lý cấu trúc lồng nhau.
- Xác định ranh giới giữa xử lý bằng lexer mode và xử lý bằng parser.
- Thiết kế quy tắc phục hồi lỗi, giữ vị trí nguồn và kiểm thử các chuyển đổi chế độ.

## 1. Chế độ lexer là gì?

Lexer (bộ phân tích từ vựng) đọc văn bản nguồn và chia văn bản thành các token như từ khóa, định danh, literal, toán tử và dấu phân cách. Với ngôn ngữ đơn giản, một bộ quy tắc từ vựng duy nhất có thể đủ. Nhưng nhiều DSL có những vùng văn bản mà cùng một ký tự lại mang ý nghĩa khác nhau tùy vị trí.

Ví dụ, dấu ngoặc nhọn trong DSL có thể biểu thị khối lệnh:

~~~text
rule "free_shipping" {
    when order.total > 500000
    then order.shippingFee = 0
}
~~~

Trong khi đó, dấu ngoặc nhọn trong một chuỗi mẫu có thể chỉ là ký tự văn bản hoặc mở đầu vùng nội suy:

~~~text
message "Order {order.id} is ready"
~~~

Nếu lexer áp dụng cùng một bộ quy tắc ở mọi vị trí, nó có thể nhầm dấu ngoặc trong chuỗi với dấu ngoặc cấu trúc của DSL. Một cách giải quyết là cho lexer biết hiện tại nó đang đọc loại vùng nào.

**Chế độ lexer (lexer mode)** là một tập hợp quy tắc nhận diện token được kích hoạt tại một thời điểm. Lexer chỉ áp dụng các quy tắc phù hợp với chế độ hiện tại. Khi gặp một dấu hiệu chuyển chế độ, nó chuyển sang bộ quy tắc khác, rồi có thể quay lại chế độ trước đó.

Ví dụ, một DSL mẫu có thể có các chế độ:

- DEFAULT: đọc từ khóa, định danh, toán tử và cấu trúc DSL.
- STRING: đọc nội dung chuỗi, escape và dấu kết thúc chuỗi.
- INTERPOLATION: đọc biểu thức DSL bên trong vùng nội suy.
- COMMENT: đọc nội dung chú thích cho đến khi gặp dấu kết thúc.

Chế độ lexer giúp đặc tả rõ rằng cùng một ký tự có thể được xử lý khác nhau trong những ngữ cảnh từ vựng khác nhau.

## 2. Vì sao cần nhiều chế độ từ vựng?

Một lexer mode hữu ích khi cách nhận diện token phụ thuộc vào vùng mà lexer đang đọc. Những tình huống thường gặp gồm:

### 2.1. Chuỗi và nội dung văn bản

Trong mã DSL, dấu nháy kép mở một literal chuỗi. Bên trong chuỗi, các từ như if, when hoặc order thường là văn bản, không phải từ khóa hay định danh của DSL.

~~~text
when order.status == "when"
~~~

Từ when đầu tiên là từ khóa; từ when trong dấu nháy là nội dung chuỗi. Chế độ STRING cho phép lexer đọc phần bên trong dấu nháy theo quy tắc chuỗi, không áp dụng quy tắc từ khóa.

### 2.2. Nội suy biểu thức

Một DSL mẫu có thể cho phép nhúng biểu thức vào chuỗi:

~~~text
message "Hello, ${customer.name}!"
~~~

Lexer cần đọc phần Hello, và ! như văn bản, nhưng phần customer.name như biểu thức DSL. Nó phải chuyển từ STRING sang INTERPOLATION tại dấu mở nội suy và quay lại STRING khi biểu thức kết thúc.

### 2.3. Chú thích

Trong DEFAULT, ký tự # có thể bắt đầu chú thích:

~~~text
# Chỉ áp dụng cho đơn hàng nội địa
when order.destination == "domestic"
~~~

Sau dấu #, các từ khóa và toán tử không còn được phân loại như mã thực thi. Chế độ COMMENT có thể nhận toàn bộ nội dung cho đến cuối dòng.

### 2.4. Ngôn ngữ nhúng

Một DSL có thể nhúng SQL, regex, biểu thức định dạng hoặc một đoạn ngôn ngữ khác. Vùng nhúng cần quy tắc token riêng vì cú pháp của nó khác cú pháp DSL chủ.

~~~text
query {
    sql """
        select id, total
        from orders
        where status = 'PAID'
    """
}
~~~

Trong vùng SQL, từ select hoặc where không nên bị nhận diện như từ khóa của DSL chủ. Một chế độ SQL có thể quản lý từ khóa, chuỗi và dấu chú thích của SQL.

### 2.5. Cú pháp dựa trên thụt lề hoặc vùng đặc biệt

Một số DSL dùng vùng văn bản nhiều dòng, khối mã, tài liệu nhúng hoặc cú pháp kiểu heredoc. Lexer có thể cần ghi nhớ dấu kết thúc hoặc mức thụt lề để biết khi nào rời khỏi vùng đó.

### 2.6. Từ khóa theo ngữ cảnh

Một từ có thể là từ khóa ở một vị trí nhưng là tên thông thường ở vị trí khác. Lexer mode có thể giải quyết một số trường hợp, nhưng không phải lúc nào cũng là cách tốt nhất. Nếu việc phân loại phụ thuộc cấu trúc cú pháp sâu, parser hoặc bước phân giải tên thường phù hợp hơn.

## 3. Chế độ, trạng thái và ngữ cảnh khác nhau thế nào?

Ba khái niệm này có liên quan nhưng không hoàn toàn giống nhau.

| Khái niệm | Ý nghĩa | Ví dụ |
|---|---|---|
| Lexer mode | Bộ quy tắc token đang được áp dụng | DEFAULT, STRING, COMMENT |
| Lexer state | Thông tin nội bộ mà scanner đang ghi nhớ | Đang ở sau dấu escape, số dòng hiện tại |
| Parser context | Vị trí cấu trúc hiện tại trong grammar | Đang phân tích tham số hàm hoặc thân rule |

Một mode thường quyết định loại token nào có thể được nhận diện. State có thể ghi nhớ chi tiết trong quá trình nhận diện, chẳng hạn chuỗi có dùng dấu nháy đơn hay dấu nháy kép, hoặc một vùng nhiều dòng đang chờ delimiter nào.

Parser context mô tả cấu trúc cú pháp mà parser đang xử lý. Lexer không nhất thiết biết toàn bộ cấu trúc đó. Giữ ranh giới này giúp lexer không phải trở thành một parser thứ hai.

Ví dụ, lexer có thể biết mình đang ở chế độ STRING. Nó không cần biết chuỗi đó là đối số của hàm message, thuộc tính title hay một giá trị trong danh sách. Parser sẽ xác định vai trò cú pháp của token STRING sau đó.

## 4. Mô hình chuyển chế độ

Lexer thường đọc nguồn từ trái sang phải. Khi gặp một token đặc biệt, lexer có thể chuyển sang chế độ khác. Khi gặp dấu kết thúc, lexer quay lại chế độ trước hoặc chuyển sang một chế độ được xác định.

Một mô hình đơn giản:

~~~text
              dấu nháy mở
    +------------------------------+
    |                              v
+---------+                    +---------+
| DEFAULT |                    | STRING  |
+---------+                    +---------+
    ^                              |
    +------------------------------+
              dấu nháy đóng
~~~

Một lexer có thể hỗ trợ các thao tác:

- **Switch mode:** thay chế độ hiện tại bằng chế độ mới.
- **Push mode:** lưu chế độ hiện tại vào ngăn xếp rồi chuyển sang chế độ mới.
- **Pop mode:** lấy chế độ trước đó từ ngăn xếp và quay lại.
- **Skip:** bỏ token hiện tại, thường dùng cho khoảng trắng hoặc chú thích không cần chuyển cho parser.
- **Emit token:** tạo token và đưa vào luồng đầu ra.
- **More:** tiếp tục đọc để ghép phần hiện tại với phần tiếp theo thành một token hoàn chỉnh, nếu công cụ hỗ trợ hành vi này.

Tên và cú pháp các thao tác tùy thư viện lexer. Điều quan trọng là hiểu ý nghĩa chuyển trạng thái và bảo đảm mọi đường vào chế độ đều có đường ra hợp lệ.

### 4.1. Switch mode

Switch mode thay chế độ hiện tại bằng chế độ mới. Cách này phù hợp khi lexer biết chắc chế độ tiếp theo và không cần quay lại chế độ trước.

Ví dụ, sau dấu mở một khối raw text, lexer chuyển sang chế độ RAW_TEXT. Khi gặp dấu kết thúc khối, nó chuyển thẳng về DEFAULT.

### 4.2. Push và pop mode

Push/pop phù hợp khi một vùng có thể lồng trong vùng khác và lexer cần quay lại đúng chế độ đã tạm rời.

Ví dụ:

~~~text
message "Hello ${format(customer.name, "upper")}!"
~~~

Lexer có thể đi qua:

1. DEFAULT đọc từ khóa message.
2. Gặp dấu nháy, push DEFAULT và vào STRING.
3. Gặp dấu mở nội suy, push STRING và vào INTERPOLATION.
4. Trong biểu thức, lời gọi hàm có thể chứa một chuỗi con, nên lexer lại push INTERPOLATION và vào STRING.
5. Khi chuỗi con đóng, pop để quay lại INTERPOLATION.
6. Khi dấu đóng nội suy được nhận diện, pop để quay lại STRING bên ngoài.
7. Khi chuỗi ngoài đóng, pop để quay lại DEFAULT.

Ngăn xếp giúp lexer quay lại đúng ngữ cảnh từ vựng, thay vì chỉ lưu một biến mode duy nhất.

### 4.3. Khi nào chỉ cần một biến mode?

Nếu ngôn ngữ không cho phép cấu trúc lồng nhau và mỗi lần chuyển mode luôn kết thúc bằng một chuyển đổi cố định, một biến mode có thể đủ. Ngăn xếp chỉ cần thiết khi phải nhớ nhiều chế độ đang tạm dừng.

Không nên thêm mode stack nếu cú pháp không cần. Cấu trúc đơn giản hơn sẽ dễ kiểm thử và dễ hiểu hơn.

## 5. Ví dụ: chế độ DEFAULT và STRING

Giả sử DSL có cú pháp:

~~~text
rule "welcome" {
    message = "Hello, customer"
}
~~~

Trong DEFAULT:

- rule là token RULE.
- welcome chưa được đọc ở DEFAULT vì nó nằm trong chuỗi.
- { là LEFT_BRACE.
- message là IDENTIFIER.
- = là EQUAL.
- dấu nháy mở bắt đầu STRING.

Trong STRING:

- Hello, customer được đọc như nội dung chuỗi.
- dấu nháy đóng kết thúc literal.
- các từ khóa như rule, when, then nếu xuất hiện bên trong chuỗi đều là văn bản.

Một dãy token có thể là:

~~~text
RULE
STRING("welcome")
LEFT_BRACE
IDENTIFIER("message")
EQUAL
STRING("Hello, customer")
RIGHT_BRACE
EOF
~~~

Một thiết kế lexer có thể thực hiện theo hai cách:

1. Đọc toàn bộ chuỗi trong một hàm scanString chuyên biệt, trong khi lexer vẫn được xem như đang xử lý token STRING.
2. Chuyển sang mode STRING với bộ quy tắc riêng cho ký tự thường, escape và dấu đóng.

Cách thứ hai thường hữu ích khi chuỗi có nhiều tính năng như nội suy, raw text hoặc nhiều loại delimiter.

## 6. Escape sequence trong chế độ chuỗi

Chuỗi thường cho phép biểu diễn ký tự đặc biệt bằng escape sequence.

~~~text
message "Line one\nLine two"
message "A quote: \" and a slash: \\"
~~~

Trong ví dụ này, lexer cần phân biệt:

- Dấu nháy kết thúc chuỗi.
- Dấu nháy được escape và thuộc nội dung.
- Dấu gạch chéo ngược mở đầu escape.
- Ký tự n biểu diễn newline nếu DSL định nghĩa như vậy.

Một thiết kế thường có các quy tắc trong STRING:

| Nội dung gặp được | Hành động |
|---|---|
| Dấu nháy đóng | Kết thúc chuỗi, pop hoặc switch về mode trước |
| Dấu gạch chéo ngược | Chuyển sang xử lý escape |
| Ký tự thường | Thêm vào nội dung chuỗi |
| Newline không được phép | Báo lỗi chuỗi chưa đóng hoặc newline không hợp lệ |
| Cuối tệp trước dấu đóng | Báo lỗi chuỗi chưa kết thúc |

Có thể dùng state phụ ESCAPE thay cho một mode đầy đủ nếu chỉ cần xử lý một ký tự sau dấu gạch chéo ngược. Nếu escape có cú pháp phức tạp, một mode riêng có thể rõ ràng hơn.

### 6.1. Escape hợp lệ và không hợp lệ

DSL cần xác định danh sách escape:

~~~text
\"  dấu nháy kép
\\  dấu gạch chéo ngược
\n  xuống dòng
\r  carriage return
\t  tab
\uXXXX  ký tự Unicode, nếu được hỗ trợ
~~~

Ví dụ, nếu \q không được định nghĩa, lexer nên báo lỗi tại escape đó. Không nên âm thầm xóa dấu gạch chéo ngược và giữ lại q vì điều đó có thể che giấu lỗi đánh máy.

### 6.2. Raw string

Raw string có thể không diễn giải escape:

~~~text
path = r"C:\\temp\\orders"
~~~

Một cách triển khai là nhận diện tiền tố r trước dấu nháy và chuyển sang RAW_STRING. Trong mode này, dấu gạch chéo ngược là ký tự thông thường; dấu đóng vẫn phải được nhận diện theo quy tắc delimiter.

Nếu DSL có nhiều kiểu chuỗi, cần xác định rõ tiền tố, delimiter và cách thoát delimiter trong từng kiểu.

## 7. Nội suy biểu thức trong chuỗi

Nội suy cho phép chèn giá trị tính toán vào văn bản. Đây là trường hợp điển hình cần nhiều lexer mode.

Ví dụ:

~~~text
message "Order ${order.id} belongs to ${customer.name}"
~~~

Có thể mô hình hóa luồng token:

~~~text
STRING_START
STRING_TEXT("Order ")
INTERPOLATION_START
IDENTIFIER(order)
DOT
IDENTIFIER(id)
INTERPOLATION_END
STRING_TEXT(" belongs to ")
INTERPOLATION_START
IDENTIFIER(customer)
DOT
IDENTIFIER(name)
INTERPOLATION_END
STRING_END
~~~

Tên token thực tế phụ thuộc thiết kế. Một số lexer ghép toàn bộ chuỗi thành một token có cấu trúc; một số tạo nhiều token để parser xây AST gồm các đoạn văn bản và biểu thức.

### 7.1. Các bước chuyển mode

Một luồng đơn giản:

1. DEFAULT gặp dấu nháy mở và push STRING.
2. STRING đọc văn bản cho đến khi gặp dấu mở nội suy.
3. Lexer phát STRING_TEXT cho phần văn bản đã đọc.
4. Lexer push STRING và chuyển sang INTERPOLATION.
5. INTERPOLATION dùng bộ token của biểu thức DSL.
6. Khi gặp delimiter đóng nội suy ở đúng cấp lồng, lexer pop về STRING.
7. STRING tiếp tục đọc văn bản.
8. Dấu nháy cuối cùng kết thúc chuỗi và pop về DEFAULT.

### 7.2. Vì sao không dùng cùng quy tắc trong cả chuỗi?

Trong STRING, ký tự + có thể chỉ là văn bản. Trong INTERPOLATION, + có thể là toán tử cộng. Tương tự, dấu chấm có thể là ký tự trong văn bản hoặc toán tử truy cập thuộc tính. Mode xác định bộ quy tắc phù hợp.

### 7.3. Dấu kết thúc nội suy và ngoặc lồng

Giả sử dấu mở nội suy là ${ và dấu đóng là }. Bên trong biểu thức có thể có khối hoặc object literal:

~~~text
message "Result: ${render({ name: customer.name })}"
~~~

Nếu lexer kết thúc nội suy ngay tại dấu } đầu tiên, nó sẽ nhầm dấu đóng của object literal với dấu đóng nội suy. Có một số cách giải quyết:

- Theo dõi độ sâu ngoặc nhọn trong mode INTERPOLATION.
- Dùng parser hoặc bộ quét biểu thức để xác định dấu đóng ở cấp ngoài cùng.
- Chọn delimiter nội suy khác ít xung đột với cú pháp biểu thức.

Khi gặp { trong biểu thức, tăng nesting depth; khi gặp } thì giảm depth nếu depth lớn hơn 0. Chỉ khi depth bằng 0 mới xem } là INTERPOLATION_END.

### 7.4. Chuỗi lồng trong biểu thức

Biểu thức nội suy có thể chứa literal chuỗi:

~~~text
message "Customer: ${format(customer.name, "upper")}"
~~~

Nếu dấu nháy trong biểu thức giống dấu nháy của chuỗi ngoài, lexer phải biết mình đang ở INTERPOLATION. Khi đó, dấu nháy mở một STRING con của biểu thức, và dấu nháy đóng STRING con không kết thúc chuỗi ngoài.

Đây là lý do push/pop mode hữu ích: sau khi chuỗi con kết thúc, lexer quay lại đúng INTERPOLATION thay vì nhầm quay về STRING bên ngoài.

## 8. Chế độ chú thích

Chú thích thường bị bỏ qua khi tạo AST, nhưng lexer vẫn phải nhận diện chúng đúng cách.

### 8.1. Chú thích một dòng

Giả sử dấu # mở chú thích đến hết dòng:

~~~text
# Miễn phí vận chuyển cho đơn lớn
when order.total >= 500000 then order.shipping_fee = 0
~~~

DEFAULT nhận dấu # rồi chuyển sang LINE_COMMENT. Mode này đọc đến newline hoặc EOF, sau đó quay về DEFAULT.

Nếu chú thích không cần parser, lexer có thể skip token. Nếu cần giữ chú thích để formatter hoặc editor, lexer có thể phát token COMMENT trên một channel riêng hoặc lưu nó như trivia.

### 8.2. Chú thích nhiều dòng

Giả sử chú thích bắt đầu bằng /* và kết thúc bằng */:

~~~text
/*
  Quy tắc chỉ áp dụng trong giờ làm việc.
  Có thể trải qua nhiều dòng.
*/
when order.status == "NEW"
~~~

Sau /*, lexer vào BLOCK_COMMENT và đọc cho đến */. Khi gặp dấu kết thúc, lexer quay về mode trước.

### 8.3. Chú thích lồng nhau

Một số DSL cho phép chú thích lồng:

~~~text
/*
  Chú thích ngoài
  /* chú thích trong */
  tiếp tục chú thích ngoài
*/
~~~

Nếu hỗ trợ, lexer cần theo dõi độ sâu comment:

- Gặp /* thì tăng depth.
- Gặp */ thì giảm depth.
- Quay về mode trước khi depth trở về 0.

Nếu không hỗ trợ comment lồng, dấu /* bên trong comment có thể chỉ là văn bản và dấu */ đầu tiên sẽ kết thúc comment. Cần đặc tả rõ để tránh cách hiểu khác nhau giữa các công cụ.

## 9. Chế độ cho ngôn ngữ nhúng

Một DSL có thể cho phép nhúng một ngôn ngữ khác để tận dụng cú pháp sẵn có. Ví dụ:

~~~text
query "orders" {
    sql {
        select id, total
        from orders
        where status = 'PAID'
    }
}
~~~

Trong vùng sql, lexer cần hiểu từ khóa và chuỗi theo quy tắc SQL, không theo quy tắc DSL chủ.

### 9.1. Ranh giới vùng nhúng

Trước khi thiết kế mode, cần xác định:

- Token nào bắt đầu vùng nhúng?
- Token hoặc delimiter nào kết thúc vùng?
- Delimiter kết thúc có thể xuất hiện bên trong chuỗi/comment của ngôn ngữ nhúng không?
- Có cho phép vùng nhúng lồng nhau không?
- Lexer có cần token hóa nội dung nhúng hay chỉ lưu nguyên văn?

Nếu nội dung nhúng được xử lý bởi parser riêng, lexer chủ có thể phát một token OPAQUE_BLOCK chứa nguyên văn nội dung và vị trí. Cách này giảm việc triển khai lại toàn bộ lexer của ngôn ngữ nhúng.

### 9.2. Token hóa hay giữ nguyên văn?

| Cách tiếp cận | Phù hợp khi | Đặc điểm |
|---|---|---|
| Token hóa bằng mode riêng | DSL cần highlight, kiểm tra hoặc phân tích nội dung nhúng | Cần quy tắc từ vựng của ngôn ngữ nhúng |
| Giữ nguyên văn thành một token | Nội dung được chuyển cho công cụ khác xử lý | Lexer chủ chỉ cần xác định ranh giới |
| Chuyển cho lexer/parser chuyên dụng | Ngôn ngữ nhúng phức tạp hoặc đã có công cụ | Tách trách nhiệm và tái sử dụng parser |

Không cần tự xây lexer SQL hoặc regex đầy đủ nếu mục tiêu của DSL chỉ là lưu và chuyển nội dung đến một engine khác.

### 9.3. Delimiter có thể xuất hiện trong nội dung

Nếu vùng nhúng kết thúc bằng dấu } nhưng SQL string cũng chứa }, lexer không được kết thúc vùng nhúng quá sớm. Cần biết lexer đang ở chế độ SQL string/comment hay đang ở trạng thái SQL bình thường trước khi kiểm tra delimiter của DSL chủ.

Một cách là lexer nhúng duy trì mode con cho SQL string và comment; chỉ khi ở SQL mode mặc định mới xem delimiter của DSL chủ có hiệu lực.

## 10. Heredoc và vùng văn bản nhiều dòng

Heredoc là cách viết literal nhiều dòng bằng delimiter mở và delimiter đóng. Ví dụ minh họa:

~~~text
description = <<END_TEXT
Đơn hàng đã được xác nhận.
Vui lòng chuẩn bị giao hàng.
END_TEXT
~~~

Sau <<END_TEXT, lexer vào HEREDOC và đọc văn bản cho đến dòng delimiter đóng theo quy tắc đã định nghĩa.

### 10.1. Delimiter cố định

Nếu DSL luôn dùng một delimiter cố định như END, lexer chỉ cần tìm đúng dòng kết thúc. Tuy nhiên, delimiter có thể xuất hiện trong nội dung, nên cần quy định nó phải đứng riêng trên một dòng hoặc có cách escape.

### 10.2. Delimiter do người viết chọn

Nếu người viết chọn END_TEXT, lexer phải lưu giá trị delimiter sau token mở. Khi đọc các dòng tiếp theo, nó so sánh từng dòng với delimiter đó.

Đây là ví dụ về lexer state: mode HEREDOC xác định bộ quy tắc đang dùng; biến heredocTerminator ghi nhớ delimiter cụ thể.

### 10.3. Thụt lề

Một số DSL cho phép delimiter kết thúc được thụt lề. Khi đó, lexer cần quy định:

- Có bỏ thụt lề chung khỏi nội dung không?
- Tab và dấu cách có được xem tương đương không?
- Delimiter phải khớp chính xác hay được phép có khoảng trắng?
- Vị trí nguồn của nội dung sau khi bỏ thụt lề được giữ thế nào?

Không nên xử lý thụt lề theo cách không xác định vì nó làm thay đổi nội dung literal.

## 11. Chế độ lexer và từ khóa theo ngữ cảnh

Từ khóa theo ngữ cảnh (contextual keyword) là từ chỉ có ý nghĩa đặc biệt ở một vị trí hoặc cấu trúc nhất định.

Ví dụ, trong DSL:

~~~text
match order.status {
    case "NEW" -> process(order)
}
~~~

Từ match có thể là từ khóa mở đầu cấu trúc pattern matching. Nhưng ở nơi khác, người dùng có thể muốn đặt biến tên match:

~~~text
let match = "exact"
~~~

Có hai cách thiết kế:

1. Lexer luôn phát IDENTIFIER cho match; parser nhận diện nó là từ khóa khi ở vị trí cần cấu trúc match.
2. Lexer dùng mode hoặc trạng thái để phân loại match thành token từ khóa ở một số ngữ cảnh.

Cách thứ nhất thường giữ lexer đơn giản hơn vì ý nghĩa phụ thuộc grammar. Cách thứ hai có thể hữu ích nếu cú pháp có ranh giới từ vựng rõ ràng và parser cung cấp chế độ một cách kiểm soát.

Không nên chuyển mode dựa trên những phỏng đoán yếu như “từ trước đó có vẻ giống một từ khóa”. Điều đó dễ làm lexer và parser không nhất quán.

## 12. Lexer mode và parser mode

Lexer mode quyết định cách chia ký tự thành token. Parser context quyết định cách kết hợp token thành cấu trúc.

Ví dụ, trong:

~~~text
call("hello", customer.name)
~~~

Lexer cần nhận diện dấu ngoặc, dấu phẩy, chuỗi, định danh và dấu chấm. Parser xác định đây là lời gọi hàm với hai đối số.

Nếu lexer chuyển mode mỗi khi parser vào một nonterminal, thiết kế có thể trở nên phụ thuộc chặt giữa lexer và parser. Điều đó chỉ nên làm khi có lý do cụ thể, chẳng hạn cú pháp nội suy hoặc ngôn ngữ nhúng.

Một nguyên tắc hữu ích:

- Nếu khác biệt nằm ở cách đọc ký tự và delimiter, cân nhắc lexer mode.
- Nếu khác biệt nằm ở cấu trúc token và quy tắc kết hợp, dùng parser.
- Nếu khác biệt nằm ở ý nghĩa tên hoặc kiểu, dùng name resolution hoặc semantic analysis.

## 13. Thiết kế bảng chuyển chế độ

Trước khi viết mã, hãy liệt kê mode, điều kiện vào, điều kiện ra và hành động.

Ví dụ cho DSL có chuỗi nội suy:

| Mode hiện tại | Dấu hiệu | Hành động | Mode tiếp theo |
|---|---|---|---|
| DEFAULT | Dấu nháy kép | Phát STRING_START, push mode | STRING |
| DEFAULT | Dấu # | Phát hoặc skip comment start, push mode | LINE_COMMENT |
| STRING | Ký tự thường | Gom vào STRING_TEXT | STRING |
| STRING | Dấu escape | Đọc escape theo quy tắc | STRING |
| STRING | Dấu mở nội suy | Phát INTERPOLATION_START, push mode | INTERPOLATION |
| STRING | Dấu nháy đóng | Phát STRING_END, pop mode | DEFAULT hoặc mode trước |
| INTERPOLATION | Dấu đóng ở depth 0 | Phát INTERPOLATION_END, pop mode | STRING |
| INTERPOLATION | Dấu ngoặc mở trong biểu thức | Tăng độ sâu ngoặc | INTERPOLATION |
| INTERPOLATION | Dấu ngoặc đóng khi depth > 0 | Giảm độ sâu ngoặc | INTERPOLATION |
| LINE_COMMENT | Newline | Kết thúc comment, pop mode | DEFAULT |

Bảng này giúp phát hiện các đường chuyển bị thiếu, chẳng hạn EOF xuất hiện khi lexer vẫn ở STRING hoặc INTERPOLATION.

### 13.1. Mỗi mode cần có điểm kết thúc

Với mỗi mode, hãy xác định:

- Dấu hiệu bắt đầu.
- Dấu hiệu kết thúc.
- Các token được nhận diện bên trong.
- Escape hoặc delimiter lồng.
- Hành vi khi EOF xuất hiện.
- Cách phục hồi nếu nội dung sai.

Nếu không xác định điểm kết thúc, lexer có thể đọc nuốt phần còn lại của tệp.

### 13.2. Mode mặc định

DEFAULT thường là chế độ bắt đầu và là chế độ quay lại sau khi các vùng con kết thúc. Lexer cần đảm bảo ngăn xếp mode được khôi phục về trạng thái ban đầu sau mỗi cấu trúc hoàn chỉnh.

## 14. Ngăn xếp chế độ và cấu trúc lồng nhau

Một biến mode đơn chỉ lưu được một chế độ hiện tại. Khi có nhiều lớp lồng nhau, cần ngăn xếp.

Ví dụ:

~~~text
message "Outer ${format("Inner ${customer.name}")}"
~~~

Luồng mode có thể như sau:

~~~text
DEFAULT
  push STRING
    push INTERPOLATION
      push STRING
        push INTERPOLATION
        pop -> STRING
      pop -> INTERPOLATION
    pop -> STRING
  pop -> DEFAULT
~~~

Ngăn xếp lưu chế độ trước mỗi lần push. Pop lấy chế độ gần nhất đã lưu và khôi phục nó.

### 14.1. Giới hạn độ sâu lồng nhau

Một DSL có thể giới hạn độ sâu nội suy hoặc comment lồng nhau để giảm nguy cơ đầu vào bất thường gây tiêu tốn tài nguyên. Nếu vượt giới hạn, lexer cần báo lỗi có vị trí thay vì tràn ngăn xếp.

### 14.2. Đảm bảo push/pop cân bằng

Mỗi push cần có đường pop tương ứng. Nếu gặp EOF khi stack còn mode chưa đóng, lexer phải báo cấu trúc chưa kết thúc và cho biết vị trí bắt đầu của vùng chưa đóng.

### 14.3. Không pop nhầm mode

Khi một mode có thể lồng cùng loại, chỉ pop khi delimiter đóng thuộc đúng cấp. Ví dụ, dấu nháy đóng của STRING con phải quay về INTERPOLATION, không được bỏ qua STRING ngoài.

## 15. Token đầu ra từ các mode

Một lexer mode có thể phát token theo nhiều cách.

### 15.1. Phát một token hoàn chỉnh

Với chuỗi đơn giản, lexer có thể phát một token STRING chứa toàn bộ giá trị đã giải mã:

~~~text
STRING("Hello")
~~~

Parser không cần biết chuỗi gồm những đoạn nào.

### 15.2. Phát nhiều token thành phần

Với chuỗi nội suy, lexer có thể phát:

~~~text
STRING_START
STRING_TEXT("Hello ")
INTERPOLATION_START
IDENTIFIER(customer)
DOT
IDENTIFIER(name)
INTERPOLATION_END
STRING_END
~~~

Parser sẽ tạo AST gồm các đoạn văn bản và biểu thức. Cách này hữu ích nếu công cụ cần phân tích, highlight hoặc kiểm tra kiểu biểu thức bên trong chuỗi.

### 15.3. Kênh token (token channel)

Một số framework cho phép phân loại token theo channel. Token chính được gửi cho parser; token phụ như comment hoặc whitespace có thể được giữ trên channel riêng.

Điều này giúp vừa giữ thông tin phục vụ editor, vừa không làm grammar chính phải xử lý comment ở mọi vị trí.

### 15.4. Skip và giữ trivia

Nếu comment chỉ dùng để giải thích cho người đọc, lexer có thể bỏ qua. Nếu cần formatter hoặc công cụ chỉnh sửa mã, nên giữ comment như trivia hoặc token phụ. Quyết định này ảnh hưởng khả năng round-trip: parse rồi in lại mà không mất nội dung không thuộc ngữ nghĩa.

## 16. Xử lý lỗi trong từng chế độ

Lỗi trong mode có thể khác lỗi từ vựng ở DEFAULT.

| Mode | Lỗi có thể gặp | Cách báo lỗi |
|---|---|---|
| DEFAULT | Ký tự không hợp lệ | Nêu ký tự và vị trí |
| STRING | Chuỗi chưa đóng | Nêu vị trí dấu nháy mở và EOF |
| STRING | Escape không hợp lệ | Nêu escape và quy tắc được hỗ trợ |
| INTERPOLATION | Thiếu delimiter đóng | Nêu vị trí bắt đầu nội suy |
| BLOCK_COMMENT | Thiếu dấu kết thúc | Nêu vị trí mở comment |
| HEREDOC | Không tìm thấy delimiter kết thúc | Nêu delimiter mong đợi |
| EMBEDDED | Vùng nhúng chưa đóng | Nêu vùng bắt đầu và delimiter kết thúc |

### 16.1. Lỗi EOF phụ thuộc mode

EOF trong DEFAULT thường là kết thúc bình thường. EOF trong STRING có thể là lỗi chuỗi chưa đóng. EOF trong BLOCK_COMMENT có thể là lỗi comment chưa đóng. EOF trong INTERPOLATION có thể là lỗi thiếu dấu đóng nội suy.

Do đó, hành vi EOF cần được định nghĩa cho từng mode.

### 16.2. Phục hồi sau lỗi

Một IDE thường muốn tiếp tục phân tích phần còn lại để hiển thị nhiều lỗi cùng lúc. Lexer có thể:

- Phát token lỗi chứa span và thông tin chẩn đoán.
- Bỏ qua ký tự không hợp lệ rồi tiếp tục.
- Quay lại mode an toàn khi phát hiện delimiter đóng hoặc điểm đồng bộ.
- Giữ stack mode nhất quán sau khi phục hồi.

Đối với trình thực thi cấu hình, nếu lexer gặp lỗi trong cấu trúc quan trọng, công cụ nên ngăn thực thi cho đến khi nguồn được sửa.

### 16.3. Không để lỗi mode tạo lỗi dây chuyền quá mức

Nếu chuỗi chưa đóng khiến lexer ở STRING đến EOF, parser có thể báo hàng trăm token thiếu. Một chẩn đoán gốc rõ ràng như “chuỗi bắt đầu tại dòng 4 chưa có dấu đóng” thường hữu ích hơn nhiều lỗi cú pháp phát sinh sau đó.

## 17. Vị trí nguồn và nội dung mode

Khi chuyển mode, lexer vẫn cần theo dõi offset, dòng và cột của nguồn gốc. Token được phát từ STRING_TEXT hoặc INTERPOLATION cần trỏ đúng đoạn văn bản ban đầu.

Ví dụ:

~~~text
message "Order ${order.id}"
                 ^^^^^^^^^
~~~

Token IDENTIFIER order và DOT cần giữ vị trí trong nguồn, dù chúng nằm bên trong chuỗi mẫu.

Nếu lexer giải mã escape hoặc bỏ thụt lề heredoc, giá trị token có thể khác lexeme nguồn. Nên lưu cả:

- Span nguồn: vị trí ký tự trong tệp gốc.
- Lexeme: phần văn bản nguyên gốc.
- Value: nội dung đã giải mã hoặc chuẩn hóa nếu cần.

Không nên chỉ lưu giá trị đã giải mã nếu công cụ cần hiển thị lỗi, formatter hoặc tái tạo nguồn.

## 18. Triển khai lexer mode bằng máy trạng thái

Một lexer có thể được mô hình hóa như máy trạng thái hữu hạn (finite-state machine). Trạng thái hiện tại và ký tự tiếp theo quyết định hành động.

Ví dụ đơn giản:

~~~text
DEFAULT:
  quote       -> emit STRING_START; push STRING
  hash        -> push LINE_COMMENT
  identifier  -> emit IDENTIFIER or KEYWORD
  digit       -> emit NUMBER
  operator    -> emit operator token

STRING:
  quote       -> emit STRING_END; pop
  backslash   -> scan escape
  other       -> append string text
  EOF         -> unterminated string error

LINE_COMMENT:
  newline     -> pop
  other       -> append or skip comment text
  EOF         -> pop or finish
~~~

### 18.1. Vòng lặp quét tổng quát

Mã giả:

~~~text
function scanAll(source):
    while not atEnd():
        scanOneUnit()

    finishAtEndOfFile()
    return tokens

function scanOneUnit():
    mode = currentMode()

    if mode == DEFAULT:
        scanDefault()
    else if mode == STRING:
        scanStringContent()
    else if mode == INTERPOLATION:
        scanInterpolation()
    else if mode == LINE_COMMENT:
        scanLineComment()
    else if mode == BLOCK_COMMENT:
        scanBlockComment()
    else:
        reportUnknownMode(mode)
~~~

### 18.2. Chuyển mode

~~~text
function pushMode(nextMode):
    modeStack.push(currentMode)
    currentMode = nextMode

function popMode():
    if modeStack is empty:
        reportInvalidModeTransition()
    else:
        currentMode = modeStack.pop()
~~~

Mã giả chỉ minh họa. Một framework lexer có thể tự quản lý stack và chuyển mode bằng action gắn với rule.

### 18.3. Theo dõi độ sâu ngoặc trong nội suy

~~~text
function scanInterpolation():
    if nextTokenIsOpeningBrace():
        braceDepth = braceDepth + 1
        emit(LEFT_BRACE)
    else if nextTokenIsClosingBrace():
        if braceDepth > 0:
            braceDepth = braceDepth - 1
            emit(RIGHT_BRACE)
        else:
            emit(INTERPOLATION_END)
            popMode()
    else:
        scanDefaultExpressionToken()
~~~

Trong triển khai thật, cần chú ý rằng dấu ngoặc trong string hoặc comment bên trong biểu thức không được làm thay đổi braceDepth. Vì vậy, các mode STRING con và COMMENT con cần được xử lý riêng.

## 19. Tổ chức quy tắc theo mode trong lexer generator

Một số công cụ sinh lexer cho phép nhóm các quy tắc theo mode. Ý tưởng chung:

~~~text
DEFAULT mode:
  rule STRING_OPEN: '"' -> push STRING
  rule COMMENT_OPEN: '#' -> push LINE_COMMENT
  rule IDENTIFIER: ...
  rule NUMBER: ...

STRING mode:
  rule STRING_CLOSE: '"' -> pop
  rule INTERPOLATION_OPEN: delimiter -> push INTERPOLATION
  rule ESCAPE: ...
  rule STRING_TEXT: ...

INTERPOLATION mode:
  rule INTERPOLATION_CLOSE: delimiter -> pop
  rule IDENTIFIER: ...
  rule NUMBER: ...
  rule operators: ...
~~~

Đây là mô tả khái niệm, không phải cú pháp có thể sao chép nguyên văn vào mọi lexer generator. Tên directive, cách khai báo mode và hành động chuyển mode phụ thuộc công cụ.

### 19.1. Quy tắc dài hơn cần ưu tiên

Trong mỗi mode, các quy tắc vẫn có thể chồng lấn. Ví dụ, trong STRING, dấu mở nội suy phải được nhận diện trước khi quy tắc ký tự thường tiêu thụ dấu $ hoặc {. Nếu quy tắc văn bản quá rộng và khớp trước, lexer có thể không bao giờ chuyển mode.

Cần xem cơ chế ưu tiên của công cụ: khớp dài nhất, thứ tự rule, hoặc cả hai.

### 19.2. Token loại riêng theo mode

Một ký tự có thể tạo token khác nhau tùy mode. Dấu { trong DEFAULT có thể là LEFT_BRACE; trong STRING có thể là văn bản; trong INTERPOLATION có thể tăng độ sâu ngoặc.

Không nhất thiết phải dùng cùng một token kind cho mọi trường hợp. Token kind riêng giúp parser và AST biết delimiter có vai trò nào.

## 20. Kiểm thử chế độ lexer

Kiểm thử mode cần bao phủ cả token đầu ra và đường chuyển chế độ.

### 20.1. Kiểm thử từng mode độc lập

DEFAULT:

- Từ khóa và định danh.
- Literal số và chuỗi.
- Toán tử một ký tự và nhiều ký tự.
- Khoảng trắng và comment mở.

STRING:

- Văn bản thường.
- Dấu nháy đóng.
- Escape hợp lệ.
- Escape không hợp lệ.
- Newline được phép hoặc không được phép.
- EOF trước dấu đóng.

INTERPOLATION:

- Định danh và toán tử DSL.
- Dấu đóng ở độ sâu 0.
- Ngoặc lồng.
- String và comment con.
- EOF khi nội suy chưa đóng.

### 20.2. Kiểm thử chuyển mode

Ví dụ:

| Đầu vào | Đường mode mong đợi |
|---|---|
| "hello" | DEFAULT → STRING → DEFAULT |
| "a ${x} b" | DEFAULT → STRING → INTERPOLATION → STRING → DEFAULT |
| "a ${f("b")} c" | DEFAULT → STRING → INTERPOLATION → STRING con → INTERPOLATION → STRING → DEFAULT |
| # comment + newline | DEFAULT → LINE_COMMENT → DEFAULT |

### 20.3. Kiểm thử lồng nhau

Tạo các trường hợp lồng string, interpolation, comment hoặc block. Xác nhận mỗi lần pop quay lại đúng mode và delimiter bên trong không kết thúc nhầm vùng bên ngoài.

### 20.4. Kiểm thử EOF

Thử kết thúc tệp khi đang ở:

- DEFAULT.
- STRING.
- INTERPOLATION.
- BLOCK_COMMENT.
- HEREDOC.
- EMBEDDED.

Kết quả phải đúng với quy tắc đã định nghĩa và thông báo lỗi cần trỏ đến vị trí mở vùng chưa đóng.

### 20.5. Kiểm thử vị trí nguồn

Đặt nội suy và escape sau nhiều dòng, sau tab và cạnh ký tự Unicode. Xác nhận span của token con vẫn trỏ đến đúng vị trí trong nguồn gốc.

### 20.6. Kiểm thử hồi quy

Khi thêm mode mới hoặc thay delimiter, chạy lại các ví dụ của mode cũ. Một quy tắc mới trong DEFAULT không nên vô tình thay đổi cách đọc nội dung STRING hoặc COMMENT.

## 21. Hiệu năng và khả năng phân tích tăng dần

Nhiều mode có thể làm lexer phức tạp hơn, nhưng không nhất thiết làm nó chậm đáng kể nếu mỗi mode có tập quy tắc rõ ràng.

### 21.1. Giữ mỗi mode nhỏ

Chỉ đưa những quy tắc cần thiết vào mode. Ví dụ, STRING không cần nhận diện toàn bộ từ khóa của DSL. Tập quy tắc nhỏ giúp lexer dễ tối ưu và tránh xung đột.

### 21.2. Tránh backtracking không cần thiết

Nếu lexer phải thử nhiều cách phân tích một vùng dài, hiệu năng có thể giảm. Thiết kế delimiter rõ ràng, ưu tiên quy tắc xác định và dùng stack mode khi cần giúp giảm việc thử lại.

### 21.3. Phân tích tăng dần trong editor

Trong editor, người dùng có thể đang gõ dở chuỗi hoặc nội suy. Lexer cần xử lý nguồn chưa hoàn chỉnh mà không treo hoặc tạo quá nhiều lỗi dây chuyền.

Một editor có thể lưu checkpoint gồm:

- Offset nguồn.
- Mode hiện tại.
- Stack mode.
- Độ sâu ngoặc hoặc comment.
- Các biến state như heredoc delimiter.

Khi người dùng sửa một đoạn, lexer có thể bắt đầu lại từ checkpoint trước vùng bị ảnh hưởng. Cách này chỉ nên triển khai khi nhu cầu tương tác và kích thước nguồn đủ lớn.

## 22. Những lỗi thiết kế thường gặp

### 22.1. Dùng một mode cho mọi loại nội dung

Nếu chuỗi, comment và ngôn ngữ nhúng đều được xử lý bằng cùng quy tắc, lexer có thể nhận diện sai từ khóa, delimiter và toán tử bên trong các vùng đó. Hãy tách mode khi quy tắc từ vựng thực sự khác nhau.

### 22.2. Tạo quá nhiều mode

Nếu mỗi nonterminal của parser đều có một lexer mode riêng, thiết kế trở nên khó theo dõi và phụ thuộc quá chặt vào grammar. Chỉ tạo mode khi cách đọc ký tự thay đổi.

### 22.3. Quên khôi phục mode trước

Nếu vào STRING bằng switch nhưng kết thúc lại dùng pop, stack có thể rỗng hoặc quay về một mode không mong muốn. Cần thống nhất cách vào và ra.

### 22.4. Nhận diện delimiter trong mọi ngữ cảnh

Dấu } trong SQL string hoặc comment không nên đóng vùng nhúng DSL. Delimiter ngoài chỉ có hiệu lực ở những mode được xác định.

### 22.5. Không xử lý cấu trúc lồng

Nếu nội suy có thể chứa object literal, kết thúc tại dấu } đầu tiên sẽ sai. Cần theo dõi độ sâu hoặc dùng parser để tìm delimiter ở cấp ngoài cùng.

### 22.6. Không xác định hành vi EOF

Lexer có thể kết thúc trong STRING hoặc COMMENT mà không báo lỗi phù hợp. Mỗi mode cần quy tắc EOF rõ ràng.

### 22.7. Gắn logic nghiệp vụ vào lexer

Lexer không nên quyết định một khách hàng có quyền hay một đơn hàng có thể hủy. Đây là công việc của semantic analysis hoặc runtime. Mode chỉ nên điều khiển việc nhận diện token.

### 22.8. Dựa vào tiền tố để nhận diện từ khóa

Nếu mode hoặc rule nhận diện từ khóa chỉ dựa trên tiền tố, tên như thenValue có thể bị tách sai. Hãy nhận diện toàn bộ định danh rồi tra bảng từ khóa, hoặc dùng quy tắc ranh giới tương đương.

## 23. Quy trình thiết kế lexer mode cho một DSL

Có thể thực hiện theo các bước:

1. Liệt kê các vùng từ vựng trong DSL: mã chính, chuỗi, comment, template, nội suy và nội dung nhúng.
2. Với mỗi vùng, liệt kê các token có thể xuất hiện và các ký tự đặc biệt.
3. Xác định dấu mở, dấu đóng và điều kiện chuyển mode.
4. Xác định vùng nào có thể lồng nhau và có cần stack hay không.
5. Quy định cách xử lý escape, delimiter xuất hiện trong nội dung và EOF.
6. Chọn token đầu ra: một token hoàn chỉnh, nhiều token thành phần hay token trên channel phụ.
7. Xác định phần nào thuộc lexer, phần nào thuộc parser và phần nào thuộc semantic analysis.
8. Viết bảng chuyển mode và mã giả trước khi triển khai.
9. Tạo kiểm thử cho từng mode, từng chuyển đổi, cấu trúc lồng và lỗi.
10. Ghi rõ các quy tắc trong đặc tả DSL để lexer, parser, formatter và editor có cùng cách hiểu.

## 24. Ví dụ tổng hợp: DSL mẫu thông báo

Giả sử DSL hỗ trợ:

~~~text
template "order_notice" {
    subject "Order ${order.id} confirmed"
    body """
        Hello ${customer.name},
        Your order total is ${formatMoney(order.total)}.
        Status: ${order.status}
    """
}
~~~

Lexer cần hỗ trợ:

- DEFAULT để đọc template, subject, body và dấu ngoặc cấu trúc.
- STRING cho chuỗi một dòng.
- MULTILINE_STRING cho nội dung nhiều dòng.
- INTERPOLATION cho biểu thức được nhúng.
- STRING con bên trong biểu thức nếu formatMoney hoặc biểu thức khác có literal chuỗi.

### 24.1. Một đường chuyển mode

Với subject:

~~~text
subject "Order ${order.id} confirmed"
~~~

Lexer có thể:

1. Ở DEFAULT, nhận SUBJECT.
2. Gặp dấu nháy và push STRING.
3. Nhận STRING_TEXT("Order ").
4. Gặp dấu mở nội suy và push INTERPOLATION.
5. Nhận IDENTIFIER(order), DOT, IDENTIFIER(id).
6. Gặp dấu đóng nội suy ở depth 0 và pop về STRING.
7. Nhận STRING_TEXT(" confirmed").
8. Gặp dấu nháy cuối và pop về DEFAULT.

### 24.2. Nội dung nhiều dòng

Với body, lexer vào MULTILINE_STRING. Newline được giữ như nội dung thay vì kết thúc token. Khi gặp delimiter đóng, lexer phát token hoặc chuỗi thành phần rồi quay về DEFAULT.

### 24.3. Nội suy trong nội dung nhiều dòng

Trong MULTILINE_STRING, nội suy vẫn có thể chuyển sang INTERPOLATION. Sau khi biểu thức kết thúc, lexer quay lại MULTILINE_STRING để tiếp tục giữ văn bản và newline.

### 24.4. Kiểm tra kiểu nằm ở bước sau

Lexer chỉ tạo token cho order.total và lời gọi formatMoney. Parser xây biểu thức. Name resolver và type checker mới xác định order có kiểu Order, total có kiểu Money và formatMoney nhận kiểu đối số phù hợp hay không.

Ví dụ này cho thấy lexer mode quản lý cách đọc các vùng khác nhau, còn ý nghĩa của biểu thức được xử lý ở những giai đoạn tiếp theo.

## 25. Bài tập tự kiểm tra

### Bài 1: Xác định mode

Một DSL có cú pháp:

~~~text
message "Hello ${customer.name}"
~~~

Hãy liệt kê các mode cần có và mô tả thời điểm lexer chuyển giữa chúng.

### Bài 2: Phân biệt mode và parser context

Trong lời gọi:

~~~text
sendEmail(customer.email, "Welcome")
~~~

Hãy nêu việc nào thuộc lexer và việc nào thuộc parser. Giải thích vì sao parser biết đây là lời gọi hàm có hai đối số.

### Bài 3: Xử lý delimiter lồng

Nội suy dùng ${...}, nhưng biểu thức bên trong cho phép object literal có dấu ngoặc nhọn. Hãy mô tả cách lexer xác định dấu } nào kết thúc nội suy.

### Bài 4: Chuỗi lồng

Với:

~~~text
message "Result: ${format("done")}"
~~~

Hãy mô tả stack mode sau mỗi lần gặp dấu nháy và delimiter nội suy.

### Bài 5: Comment nhiều dòng

DSL dùng /* và */ cho comment. Hãy quyết định DSL có cho phép comment lồng nhau không, rồi mô tả state cần lưu và cách xử lý EOF.

### Bài 6: Ngôn ngữ nhúng

Một DSL cho phép vùng SQL kết thúc bằng dấu }. Nội dung SQL có thể chứa dấu } trong string literal. Hãy đề xuất cách tránh kết thúc vùng nhúng quá sớm.

### Bài 7: Heredoc

Thiết kế quy tắc cho literal nhiều dòng có delimiter do người dùng chọn. Xác định cách lưu delimiter, cách so khớp dòng kết thúc và cách báo lỗi nếu không tìm thấy.

### Bài 8: Bảng chuyển mode

Hãy lập bảng chuyển mode cho DEFAULT, STRING, INTERPOLATION và LINE_COMMENT. Mỗi hàng cần có mode hiện tại, dấu hiệu, hành động và mode tiếp theo.

### Bài 9: Kiểm thử lỗi

Đề xuất ít nhất năm trường hợp kiểm thử EOF hoặc delimiter sai trong các mode khác nhau. Nêu thông báo lỗi mong đợi.

### Bài 10: Ranh giới trách nhiệm

Một biểu thức trong nội suy tham chiếu đến order.unknownField. Hãy xác định lexer, parser, name resolver và type checker chịu trách nhiệm phần nào.

## Kết luận

Chế độ lexer là cách chia bộ quy tắc từ vựng theo vùng nội dung, để cùng một ký tự có thể được nhận diện khác nhau tùy ngữ cảnh. Các mode thường gặp gồm DEFAULT, STRING, COMMENT, INTERPOLATION và vùng ngôn ngữ nhúng. Lexer chuyển mode khi gặp delimiter, có thể dùng switch hoặc stack push/pop để xử lý cấu trúc lồng nhau. Thiết kế tốt cần xác định rõ dấu mở/đóng, escape, EOF, token đầu ra và cách phục hồi lỗi. Lexer mode chỉ giải quyết cách đọc ký tự thành token; parser vẫn chịu trách nhiệm tổ chức token thành cấu trúc, còn phân giải tên và kiểm tra ngữ nghĩa xác định ý nghĩa của chúng. Khi ranh giới này rõ ràng, DSL có thể hỗ trợ cú pháp phong phú mà vẫn giữ lexer dễ hiểu và kiểm thử.
