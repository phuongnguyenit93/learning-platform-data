# Ký tự không hợp lệ trong phân tích từ vựng DSL

## Mục tiêu học tập

Sau bài học này, người học có thể:

- Giải thích thế nào là ký tự không hợp lệ trong một DSL và vì sao lexer phải phát hiện chúng.
- Phân biệt lỗi từ vựng với lỗi cú pháp, lỗi kiểu và lỗi nghiệp vụ.
- Xác định tập ký tự được phép trong mã DSL, định danh, literal, chú thích và các chế độ lexer.
- Hiểu cách xử lý Unicode, encoding, ký tự điều khiển, ký tự vô hình và ký tự có hình thức tương tự nhau.
- Thiết kế thông báo lỗi có vị trí nguồn và cách phục hồi để lexer tiếp tục phân tích an toàn.
- Tránh làm mất dữ liệu hoặc che giấu lỗi khi chuẩn hóa, bỏ qua hay thay thế ký tự.
- Xây dựng kiểm thử cho ký tự hợp lệ, không hợp lệ và các trường hợp biên.

## 1. Ký tự không hợp lệ là gì?

Lexer (bộ phân tích từ vựng) đọc văn bản nguồn từ trái sang phải và nhóm các ký tự thành token như từ khóa, định danh, số, chuỗi, toán tử và dấu phân cách. Mỗi DSL có một đặc tả từ vựng xác định những chuỗi ký tự nào có thể tạo thành token hợp lệ.

**Ký tự không hợp lệ (invalid character)** là ký tự mà lexer không thể chấp nhận tại vị trí hiện tại theo các quy tắc từ vựng đang có hiệu lực. Ví dụ, nếu DSL chỉ hỗ trợ các toán tử cộng, trừ, nhân và chia, ký tự @ có thể không thuộc bất kỳ token nào trong chế độ mã thông thường.

Ví dụ:

~~~text
set order.total = 120000
set order.total = 120000 @ 5
~~~

Nếu @ không được DSL định nghĩa, lexer không thể phân loại nó thành token hợp lệ. Đây là lỗi từ vựng. Parser có thể không nhận được một dãy token hợp lệ để phân tích câu lệnh thứ hai.

Ký tự không hợp lệ phụ thuộc vào ngữ cảnh từ vựng. Dấu @ có thể không hợp lệ trong biểu thức, nhưng có thể được phép trong literal chuỗi hoặc một chế độ lexer riêng. Tương tự, dấu # có thể mở đầu chú thích ở chế độ mặc định nhưng chỉ là nội dung văn bản bên trong chuỗi.

Vì vậy, không nên hỏi một ký tự có hợp lệ trong toàn bộ DSL hay không mà cần hỏi: **ký tự đó có được phép ở vị trí và chế độ lexer hiện tại hay không?**

## 2. Vai trò của lexer khi gặp ký tự không hợp lệ

Một pipeline xử lý DSL thường gồm:

~~~text
Văn bản nguồn
    |
    v
Lexer
    |-- nhận diện token hợp lệ
    |-- phát hiện ký tự không thể nhận diện
    v
Dãy token và chẩn đoán từ vựng
    |
    v
Parser
    |
    v
AST
    |
    v
Phân giải tên, kiểm tra kiểu và ngữ nghĩa
    |
    v
Thực thi hoặc sinh mã
~~~

Lexer có trách nhiệm xác định ranh giới token và báo lỗi khi không thể nhận diện phần nguồn hiện tại. Nó không cần quyết định một biểu thức có đúng nghiệp vụ hay không.

Ví dụ, nếu DSL không định nghĩa ký tự @, lexer báo lỗi tại @. Nếu dấu chấm phẩy được nhận diện thành token hợp lệ nhưng grammar không cho phép nó ở vị trí đó, parser báo lỗi cú pháp. Nếu tên trường được phân tích hợp lệ nhưng không tồn tại trong schema, bước phân giải tên báo lỗi.

Việc tách trách nhiệm giúp thông báo lỗi chính xác hơn và tránh đưa logic cú pháp hoặc nghiệp vụ vào lexer.

## 3. Phân biệt lỗi từ vựng với các loại lỗi khác

Không phải mọi ký tự trông lạ đều là ký tự không hợp lệ. Một ký tự có thể tạo token hợp lệ nhưng xuất hiện sai vị trí; một chuỗi ký tự có thể là token hợp lệ nhưng vi phạm kiểu hoặc quy tắc miền.

| Trường hợp | Giai đoạn phát hiện | Ví dụ |
|---|---|---|
| Ký tự không thuộc bất kỳ token nào trong mode hiện tại | Lexer | @ nếu DSL không hỗ trợ |
| Chuỗi literal không đóng hoặc escape không hợp lệ | Lexer | Chuỗi bắt đầu bằng dấu nháy nhưng thiếu dấu kết thúc |
| Token hợp lệ nhưng không theo grammar | Parser | Dấu phẩy xuất hiện ở nơi không cho phép |
| Tên không được khai báo hoặc trường không tồn tại | Phân giải tên | order.prcie khi schema không có trường đó |
| Các toán hạng có kiểu không tương thích | Type checker | Money + Customer |
| Giá trị đúng cấu trúc nhưng vi phạm chính sách | Kiểm tra ngữ nghĩa hoặc runtime | Số lượng đặt hàng vượt giới hạn |

### 3.1. Ký tự lạ và token không mong đợi

Ký tự lạ là ký tự mà lexer không biết cách phân loại. Token không mong đợi là token đã được lexer nhận diện nhưng parser không chấp nhận tại vị trí hiện tại.

Ví dụ, nếu dấu ; là token hợp lệ của DSL nhưng grammar không cho phép sau một biểu thức điều kiện, lỗi thuộc parser. Không nên báo “ký tự ; không hợp lệ” nếu thực tế lexer đã nhận diện nó đúng.

### 3.2. Ký tự hợp lệ nhưng dùng sai ngữ cảnh

Một ký tự có thể hợp lệ trong chuỗi nhưng không hợp lệ trong biểu thức:

~~~text
message = "Customer #42"
total = 100 @ 2
~~~

Trong dòng đầu, # và các chữ số là nội dung chuỗi. Trong dòng sau, @ gây lỗi nếu không phải toán tử được hỗ trợ.

### 3.3. Sai encoding không giống ký tự không hợp lệ

Nếu tệp chứa byte không hợp lệ theo encoding đã khai báo, công cụ có thể không giải mã được thành ký tự Unicode. Đây là lỗi giải mã đầu vào (decoding error), xảy ra trước hoặc trong quá trình cung cấp ký tự cho lexer.

Nếu byte được giải mã thành một ký tự Unicode hợp lệ nhưng DSL không cho phép ký tự đó, đây mới là lỗi từ vựng theo đặc tả DSL.

## 4. Tập ký tự hợp lệ của một DSL

Một DSL cần quy định rõ những ký tự nào có thể xuất hiện ở từng vị trí. Tập ký tự không nhất thiết giống nhau trong toàn bộ ngôn ngữ.

Các nhóm thường gặp:

- Chữ cái dùng trong từ khóa và định danh.
- Chữ số dùng trong literal số và tên định danh nếu được phép.
- Dấu gạch dưới hoặc ký tự nối tên.
- Dấu nháy và ký tự escape trong literal chuỗi.
- Toán tử và dấu phân cách.
- Khoảng trắng, tab và ký tự xuống dòng.
- Ký tự mở đầu chú thích.
- Ký tự Unicode được cho phép trong định danh hoặc văn bản.

Một đặc tả từ vựng có thể quy định:

| Vùng | Ký tự thường được cho phép |
|---|---|
| Định danh | Chữ cái, chữ số ở vị trí sau, dấu gạch dưới |
| Số | Chữ số, dấu thập phân, dấu phân nhóm hoặc hậu tố đã định nghĩa |
| Chuỗi | Hầu hết ký tự văn bản, trừ delimiter và ký tự điều khiển bị cấm; escape theo quy tắc |
| Toán tử | Một tập dấu cố định như +, -, *, /, == |
| Khoảng trắng | Dấu cách, tab và newline theo quy tắc DSL |
| Chú thích | Nội dung văn bản cho đến dấu kết thúc |

Ví dụ, một DSL có thể định nghĩa định danh theo quy tắc đơn giản:

~~~text
IDENTIFIER:
  ký tự đầu: chữ cái ASCII hoặc dấu gạch dưới
  ký tự tiếp theo: chữ cái ASCII, chữ số hoặc dấu gạch dưới
~~~

Khi đó, customer_id hợp lệ; 2customer không hợp lệ như một định danh duy nhất vì bắt đầu bằng chữ số. Tuy nhiên, lexer có thể nhận 2 thành INTEGER và customer thành IDENTIFIER tùy quy tắc tách token.

Không nên để hành vi này phụ thuộc ngẫu nhiên vào thứ tự kiểm tra. Đặc tả cần nói rõ cách xử lý chuỗi bắt đầu bằng chữ số nhưng tiếp theo là chữ cái.

## 5. Ký tự không hợp lệ trong từng loại token

### 5.1. Định danh

Định danh là tên biến, thuộc tính, kiểu, hàm hoặc tài nguyên. Đặc tả cần xác định:

- Ký tự nào được phép ở đầu.
- Ký tự nào được phép ở các vị trí tiếp theo.
- Có cho phép chữ hoa và chữ thường không.
- Có cho phép dấu gạch dưới hoặc dấu nối không.
- Có cho phép chữ cái Unicode không.
- Có phân biệt hai cách viết Unicode nhìn giống nhau không.
- Có giới hạn độ dài không.

Ví dụ với quy tắc ASCII:

| Lexeme | Kết quả có thể có |
|---|---|
| order | IDENTIFIER |
| customer_id | IDENTIFIER |
| customer2 | IDENTIFIER |
| 2customer | INTEGER(2) rồi IDENTIFIER(customer), hoặc lỗi theo quy tắc số |
| customer-id | IDENTIFIER, MINUS, IDENTIFIER nếu dấu nối là toán tử trừ |
| customer@id | Lỗi tại @ nếu @ không được hỗ trợ |

Nếu DSL cho phép dấu nối trong định danh, lexer phải phân biệt nó với toán tử trừ. Một quy tắc rõ ràng về ranh giới định danh sẽ tránh việc cùng một nguồn có nhiều cách phân tích.

### 5.2. Literal số

Literal số có thể cho phép chữ số, dấu chấm thập phân, dấu phân nhóm, dấu mũ và hậu tố đơn vị. Mỗi ký tự chỉ hợp lệ ở vị trí được quy định.

Ví dụ, nếu DSL chỉ hỗ trợ số nguyên và số thập phân có chữ số ở cả hai phía dấu chấm:

~~~text
42
3.14
~~~

có thể hợp lệ, trong khi các dạng sau cần được xử lý theo đặc tả:

~~~text
12.       dấu chấm không có phần thập phân
.5        thiếu phần nguyên
1e3       hậu tố số mũ chưa được hỗ trợ
12kg      hậu tố đơn vị chưa được định nghĩa
~~~

Không phải mọi trường hợp trên đều nhất thiết là lỗi ký tự. Lexer có thể tách thành nhiều token hợp lệ, sau đó parser báo lỗi cấu trúc. Nếu đặc tả quy định toàn bộ chuỗi là một literal số và nó không khớp pattern, lexer có thể báo lỗi literal số.

Điều quan trọng là xác định ranh giới token nhất quán để thông báo lỗi phản ánh đúng nguyên nhân.

### 5.3. Literal chuỗi

Chuỗi thường cho phép nhiều ký tự hơn mã DSL thông thường. Tuy nhiên, một số ký tự vẫn cần quy tắc:

- Dấu nháy đóng chuỗi.
- Dấu gạch chéo ngược mở đầu escape.
- Ký tự xuống dòng nếu chuỗi một dòng không cho phép newline.
- Ký tự điều khiển không được hỗ trợ.
- Ký tự kết thúc tệp trước dấu nháy đóng.

Ví dụ:

~~~text
message = "Hello, customer"
message = "This string is not closed
~~~

Dòng thứ hai là chuỗi chưa đóng. Nếu DSL không cho phép newline trong chuỗi thường, lexer báo lỗi tại vị trí mở chuỗi hoặc tại newline/EOF theo chính sách chẩn đoán.

### 5.4. Escape sequence

Một ký tự sau dấu gạch chéo ngược có thể cần thuộc tập escape hợp lệ:

| Escape minh họa | Ý nghĩa có thể có |
|---|---|
| BACKSLASH + dấu nháy kép | Dấu nháy kép |
| BACKSLASH + BACKSLASH | Dấu gạch chéo ngược |
| BACKSLASH + n | Xuống dòng |
| BACKSLASH + r | Carriage return |
| BACKSLASH + t | Tab |
| BACKSLASH + uXXXX | Mã ký tự Unicode nếu DSL hỗ trợ |

Nếu DSL không định nghĩa escape BACKSLASH + q, lexer nên báo lỗi escape không hợp lệ. Không nên âm thầm bỏ dấu gạch chéo ngược rồi giữ q, vì người viết có thể đã gõ nhầm và kết quả chuỗi sẽ khác ý định.

### 5.5. Toán tử và dấu phân cách

Lexer chỉ nên nhận diện những toán tử đã được định nghĩa. Ví dụ, nếu DSL có >= nhưng không có >>>, chuỗi >>> có thể được nhận diện thành token >, token >, token > hoặc bị báo lỗi tùy grammar từ vựng và cơ chế khớp dài nhất. Parser sau đó quyết định dãy token có hợp lệ không.

Khi thiết kế toán tử nhiều ký tự, cần quy định khớp dài nhất để tránh tách sai:

| Chuỗi nguồn | Token mong đợi nếu được hỗ trợ |
|---|---|
| > | GREATER |
| >= | GREATER_EQUAL |
| == | EQUAL_EQUAL |
| != | NOT_EQUAL |
| && | AND |

Nếu ký tự ! đứng riêng không được định nghĩa, lexer có thể báo lỗi tại !. Nếu ! là token hợp lệ nhưng không được dùng ở vị trí hiện tại, parser sẽ báo lỗi cú pháp.

### 5.6. Chú thích

Nội dung chú thích thường cho phép nhiều ký tự hơn mã DSL vì lexer không phân tích các từ bên trong thành từ khóa hay toán tử. Tuy nhiên, chú thích vẫn cần quy tắc kết thúc và encoding.

Nếu chú thích một dòng bắt đầu bằng #, ký tự @ bên trong chú thích không phải lỗi:

~~~text
# email: user@example.test
when order.total > 100
~~~

Nếu lexer báo @ là ký tự không hợp lệ ở dòng chú thích, nhiều khả năng lexer chưa chuyển đúng sang chế độ COMMENT.

## 6. Ký tự không hợp lệ phụ thuộc chế độ lexer

Một lexer có thể có nhiều mode như DEFAULT, STRING, COMMENT hoặc INTERPOLATION. Cùng một ký tự có thể hợp lệ ở mode này và không hợp lệ ở mode khác.

Ví dụ:

| Ký tự | DEFAULT | STRING | COMMENT |
|---|---|---|---|
| @ | Lỗi nếu không có token tương ứng | Có thể là văn bản | Văn bản chú thích |
| # | Có thể mở đầu comment | Văn bản | Văn bản hoặc ký tự thường |
| dấu nháy kép | Mở chuỗi | Có thể đóng chuỗi | Văn bản |
| newline | Khoảng trắng hoặc kết thúc câu lệnh | Tùy loại chuỗi | Kết thúc comment một dòng |

Vì thế, thông báo lỗi cần ghi nhận mode hiện tại. Nếu lexer gặp một ký tự lạ trong STRING, lỗi có thể là ký tự điều khiển bị cấm trong chuỗi. Nếu gặp ký tự đó trong DEFAULT, lỗi có thể là ký tự không được DSL hỗ trợ.

### 6.1. Chế độ nội suy

Trong một chuỗi mẫu, lexer có thể chuyển sang chế độ biểu thức tại dấu mở nội suy. Bên trong biểu thức, các ký tự toán tử và định danh được xử lý theo quy tắc DSL; bên ngoài, chúng chỉ là văn bản.

Khi delimiter đóng nội suy xuất hiện, lexer quay lại chế độ chuỗi. Cần xác định cách xử lý delimiter lồng trong ngoặc hoặc chuỗi con để không kết thúc nhầm vùng nội suy.

### 6.2. Chế độ ngôn ngữ nhúng

Nếu DSL cho phép nhúng SQL hoặc regex, tập ký tự hợp lệ bên trong vùng đó có thể khác DSL chủ. Lexer cần chuyển cho lexer chuyên dụng hoặc lưu vùng nhúng như văn bản nguyên khối. Không nên áp dụng bảng ký tự của DSL chủ lên nội dung nhúng.

## 7. Unicode và định danh quốc tế

Unicode cho phép biểu diễn chữ viết của nhiều ngôn ngữ. Nếu DSL cho phép người dùng viết định danh bằng tiếng Việt hoặc ngôn ngữ khác, cần quy định rõ tập ký tự hợp lệ.

### 7.1. ASCII và Unicode

Một DSL đơn giản có thể giới hạn định danh ở chữ cái ASCII. Cách này dễ triển khai và tương thích rộng, nhưng không cho phép dùng trực tiếp nhiều hệ chữ.

Một DSL hỗ trợ Unicode có thể cho phép các nhóm ký tự chữ cái và chữ số Unicode. Khi đó, cần xác định:

- Ký tự nào được phép bắt đầu định danh.
- Ký tự nào được phép ở giữa hoặc cuối định danh.
- Dấu kết hợp có được phép không.
- Ký tự định dạng và ký tự điều khiển có bị cấm không.
- Có chuẩn hóa Unicode trước khi so sánh không.

Không nên coi mọi code point ngoài ASCII là ký tự hợp lệ. Unicode bao gồm chữ cái, dấu kết hợp, ký hiệu, ký tự định dạng và nhiều nhóm khác có mục đích khác nhau.

### 7.2. Dấu tiếng Việt

Một tên như khách_hàng có thể được biểu diễn bằng chữ cái tiếng Việt có dấu. Nếu DSL hỗ trợ Unicode identifier, lexer cần nhận diện đúng các chữ cái và dấu kết hợp theo chính sách đã chọn.

Một ký tự có dấu có thể được biểu diễn bằng một code point dựng sẵn hoặc bằng chữ cái theo sau bởi dấu kết hợp. Hai chuỗi có thể trông giống nhau nhưng có chuỗi code point khác nhau.

Nếu hệ thống so sánh tên theo dạng chuẩn hóa, cần quy định dạng chuẩn, ví dụ NFC. Không nên chuẩn hóa âm thầm ở nhiều tầng khác nhau vì lexer, parser, symbol table và runtime có thể đưa ra kết quả không nhất quán.

### 7.3. Ký tự tương tự về hình thức

Một số ký tự từ các hệ chữ khác nhau có hình dáng gần giống chữ Latin. Ví dụ, chữ Latin a và một ký tự Cyrillic trông tương tự có thể là hai code point khác nhau.

Điều này có thể gây nhầm lẫn khi đặt tên biến hoặc trường. Một DSL có thể:

- Chỉ cho phép một tập chữ cái đã chọn trong định danh.
- Cảnh báo khi một định danh trộn nhiều hệ chữ.
- Cảnh báo các ký tự dễ nhầm lẫn trong tên quan trọng.
- Giữ nguyên dữ liệu và hiển thị mã Unicode trong chẩn đoán khi cần.

Không nên tự động thay một ký tự tương tự bằng ký tự khác, vì thao tác đó có thể đổi tên và làm tham chiếu sai.

### 7.4. Chuẩn hóa không thay thế kiểm tra ký tự

Chuẩn hóa Unicode giải quyết một số khác biệt biểu diễn tương đương, nhưng không biến mọi ký tự thành ký tự hợp lệ. Lexer vẫn phải áp dụng quy tắc identifier và chính sách ký tự của DSL sau khi xác định cách chuẩn hóa.

## 8. Ký tự vô hình và ký tự điều khiển

Một số ký tự không dễ nhìn thấy khi hiển thị. Chúng có thể gây ra lỗi khó phát hiện hoặc làm thay đổi cách đọc mã.

Ví dụ:

- NUL.
- Tab và các loại khoảng trắng đặc biệt.
- Ký tự zero-width.
- Ký tự điều khiển định hướng văn bản.
- Ký tự xuống dòng không được hỗ trợ.
- Ký tự BOM xuất hiện ở vị trí không mong đợi.

Không phải tất cả đều cần bị từ chối. Tab và newline thường hợp lệ ở những vị trí nhất định. Chính sách cần phân biệt ký tự khoảng trắng được hỗ trợ với ký tự định dạng hoặc điều khiển không được phép.

### 8.1. Ký tự NUL

Ký tự NUL thường không được phép trong mã DSL thông thường. Nếu nó xuất hiện trong tệp, lexer nên báo lỗi rõ ràng thay vì coi nó như kết thúc chuỗi hoặc âm thầm bỏ qua.

### 8.2. Tab và khoảng trắng đặc biệt

Tab có thể được phép để thụt lề. Non-breaking space hoặc các khoảng trắng Unicode khác có thể trông giống dấu cách thông thường nhưng không được lexer xem là cùng loại.

DSL nên quyết định:

- Chỉ chấp nhận dấu cách ASCII và tab hay chấp nhận thêm Unicode whitespace.
- Newline được chuẩn hóa hay giữ nguyên.
- Khoảng trắng đặc biệt có bị cảnh báo không.
- Tab được tính cột như thế nào trong thông báo lỗi.

Nếu một ký tự khoảng trắng không được hỗ trợ xuất hiện giữa hai token, thông báo nên chỉ ra mã Unicode và vị trí thay vì hiển thị một khoảng trống khó nhận biết.

### 8.3. Ký tự định hướng văn bản

Một số ký tự Unicode có thể làm thay đổi thứ tự hiển thị trái-phải hoặc phải-trái. Trong mã nguồn, chúng có thể khiến tên hoặc phần văn bản hiển thị khác với thứ tự code point.

Với DSL có mã được review hoặc chia sẻ, có thể cấm hoặc cảnh báo các ký tự định hướng không cần thiết trong định danh và cấu trúc cú pháp. Nếu cho phép trong văn bản, nên có cách hiển thị hoặc escape rõ ràng.

### 8.4. Zero-width characters

Ký tự zero-width có thể khiến hai định danh nhìn giống nhau nhưng không bằng nhau. Một DSL có thể cấm chúng trong định danh, đồng thời vẫn cho phép trong chuỗi nếu nghiệp vụ cần lưu nguyên văn.

Chính sách nên theo từng vùng: điều bị cấm trong identifier chưa chắc phải bị cấm trong string literal.

## 9. Encoding và giải mã nguồn

Lexer thường làm việc trên chuỗi ký tự đã được giải mã. Trước đó, công cụ phải đọc byte từ tệp hoặc đầu vào và chuyển chúng thành ký tự theo encoding.

### 9.1. Chọn encoding rõ ràng

UTF-8 là lựa chọn phổ biến cho văn bản DSL. Công cụ nên quy định encoding mặc định và cách xử lý khi tệp có metadata hoặc BOM.

Nếu một tệp được lưu bằng encoding khác nhưng công cụ giả định UTF-8, các byte có thể bị giải mã sai hoặc gây decoding error.

### 9.2. Byte không hợp lệ

Một chuỗi byte không hợp lệ theo encoding có thể không tạo ra ký tự Unicode hợp lệ. Công cụ cần quyết định:

- Từ chối tệp tại vị trí byte lỗi.
- Báo mã byte và offset.
- Có hỗ trợ chế độ thay thế hay không.

Với mã nguồn DSL, từ chối hoặc báo lỗi giải mã thường an toàn hơn thay thế âm thầm bằng ký tự thay thế, vì thay thế có thể làm thay đổi token.

### 9.3. Byte Order Mark

Một số tệp UTF-8 bắt đầu bằng BOM. Công cụ có thể chấp nhận và bỏ BOM ở đầu tệp. BOM xuất hiện giữa tệp có thể bị xem là ký tự không hợp lệ hoặc ký tự định dạng không được phép.

Phải phân biệt BOM ở đầu tệp với ký tự U+FEFF xuất hiện trong nội dung. Không nên xóa mọi U+FEFF ở mọi vị trí mà không theo chính sách.

### 9.4. CRLF và LF

Windows thường dùng CRLF; nhiều hệ thống khác dùng LF. Lexer nên xử lý newline theo quy tắc rõ ràng để vị trí dòng không bị lệch.

Nếu DSL hỗ trợ cả hai, scanner cần xem CRLF là một lần xuống dòng thay vì hai dòng. Nếu chỉ hỗ trợ một dạng, dạng còn lại cần được chuẩn hóa ở lớp đầu vào hoặc báo lỗi nhất quán.

## 10. Cách lexer phát hiện ký tự không hợp lệ

Một lexer đơn giản có thể đọc từng code point hoặc đơn vị ký tự theo encoding của môi trường. Ở mỗi vị trí, nó thử các quy tắc token phù hợp với mode hiện tại.

Một vòng quét khái niệm:

~~~text
while not endOfInput:
    start = currentPosition

    if currentMode == DEFAULT:
        if isWhitespace(peek()):
            consumeWhitespace()
        else if startsIdentifier(peek()):
            scanIdentifierOrKeyword()
        else if startsNumber(peek()):
            scanNumber()
        else if startsString(peek()):
            scanString()
        else if startsKnownOperator(peek()):
            scanOperator()
        else:
            reportInvalidCharacter(peek(), currentPosition)
            recoverFromInvalidInput()
~~~

Đây là mã giả. Lexer thực tế cần xét các token nhiều ký tự, maximal munch, mode, encoding, vị trí nguồn và các loại literal.

### 10.1. Quy tắc khớp dài nhất

Khi nhiều token bắt đầu bằng cùng một ký tự, lexer thường chọn token dài nhất có thể khớp. Ví dụ, nếu có > và >=, chuỗi >= phải được nhận diện thành GREATER_EQUAL.

Nếu không tìm được token hợp lệ tại vị trí hiện tại, lexer báo lỗi. Không nên tiêu thụ nhiều ký tự tùy tiện trước khi biết phạm vi lỗi vì điều đó có thể làm mất phần đầu của token tiếp theo.

### 10.2. Nhận diện định danh rồi tra từ khóa

Một từ khóa như when có thể có cùng hình dạng với định danh. Cách phổ biến là đọc toàn bộ lexeme định danh rồi tra bảng từ khóa. Nếu không trùng, phát IDENTIFIER.

Nếu một ký tự không được phép xuất hiện trong định danh, lexer cần quyết định nó là điểm kết thúc định danh hay là lỗi ngay sau định danh. Ví dụ, customer@id có thể tạo IDENTIFIER(customer), rồi báo @ không hợp lệ, rồi tiếp tục tại id. Thông báo cần chỉ rõ ký tự @ để người dùng không tưởng rằng toàn bộ tên đã được chấp nhận.

### 10.3. Xử lý ký tự đầu vào không thể giải mã

Nếu lỗi xảy ra ở lớp decoding, lexer có thể không nhận được code point hợp lệ. Công cụ nên giữ offset byte để chỉ ra vị trí lỗi trong tệp gốc. Không nên biến byte lỗi thành một ký tự tùy ý rồi tiếp tục mà không thông báo.

## 11. Chiến lược phục hồi sau lỗi từ vựng

Khi gặp ký tự không hợp lệ, lexer có hai lựa chọn chính:

1. Dừng ngay và trả về lỗi đầu tiên.
2. Ghi nhận lỗi, bỏ qua hoặc tiêu thụ một phần đầu vào, rồi tiếp tục để tìm thêm lỗi.

Lựa chọn phụ thuộc mục đích của công cụ.

### 11.1. Dừng ngay (fail fast)

Phù hợp với công cụ dòng lệnh hoặc bước kiểm tra cấu hình cần kết quả xác định và không cần hiển thị nhiều lỗi cùng lúc.

Ưu điểm:

- Luồng xử lý đơn giản.
- Không tạo token sai sau lỗi.
- Tránh lỗi dây chuyền từ một vùng nguồn đã hỏng.

Hạn chế:

- Người viết phải sửa từng lỗi rồi chạy lại.
- Không phù hợp với editor cần phản hồi liên tục.

### 11.2. Bỏ qua một ký tự

Lexer có thể ghi nhận lỗi rồi tiêu thụ đúng một code point để tiếp tục:

~~~text
total = 100 @ 2
~~~

Sau khi báo @, lexer tiếp tục tại khoảng trắng và số 2. Cách này thường giữ được nhiều phần nguồn còn lại.

Tuy nhiên, nếu ký tự lỗi là một phần của chuỗi nhiều byte hoặc một cấu trúc token chưa hoàn chỉnh, cần tiêu thụ theo đơn vị ký tự đã giải mã chứ không phải tùy tiện bỏ một byte.

### 11.3. Bỏ qua đến điểm đồng bộ

Trong một số trường hợp, lexer có thể bỏ qua phần còn lại của dòng hoặc đến delimiter đáng tin cậy tiếp theo. Ví dụ, nếu một literal số bị hỏng, có thể tiếp tục ở dấu xuống dòng nếu grammar coi mỗi dòng là một đơn vị.

Không nên bỏ qua đến một ký tự bất kỳ nếu ký tự đó có thể xuất hiện trong string hoặc comment. Điểm đồng bộ cần phù hợp với mode và cấu trúc DSL.

### 11.4. Phát token lỗi

Một lexer phục vụ IDE có thể phát token INVALID hoặc ERROR_TOKEN với span nguồn và thông tin chẩn đoán. Parser có thể bỏ qua token đó hoặc tạo nút lỗi để vẫn phân tích được phần còn lại.

Token lỗi không phải token hợp lệ của ngôn ngữ. Nó là phương tiện giữ vị trí và cấu trúc để công cụ tiếp tục làm việc.

### 11.5. Không lặp vô hạn

Một quy tắc quan trọng: mỗi vòng lặp của lexer phải tiêu thụ đầu vào, phát token, kết thúc hoặc thay đổi trạng thái theo cách bảo đảm tiến triển. Nếu báo lỗi mà không di chuyển con trỏ, lexer có thể lặp vô hạn tại cùng ký tự.

Khi phục hồi, cần kiểm tra:

- Con trỏ nguồn đã tiến lên chưa?
- Mode có còn hợp lệ không?
- Stack mode có được khôi phục không?
- Có tạo token rỗng lặp đi lặp lại không?
- EOF có thể được xử lý nhiều lần an toàn không?

## 12. Thiết kế thông báo lỗi cho ký tự không hợp lệ

Thông báo lỗi tốt giúp người viết tìm đúng vị trí và hiểu vì sao ký tự bị từ chối.

Nên cung cấp:

- Tên tệp hoặc nguồn DSL.
- Dòng và cột.
- Ký tự hiển thị được nếu an toàn.
- Mã Unicode hoặc mã byte khi ký tự vô hình/khó hiển thị.
- Chế độ lexer hoặc vùng đang đọc nếu điều đó giúp giải thích.
- Một số loại ký tự hoặc token được mong đợi.
- Gợi ý sửa nếu có thể xác định chắc chắn.

Ví dụ:

~~~text
rules.dsl:8:19: Ký tự không hợp lệ '@'.
Ký tự này không được hỗ trợ trong biểu thức ở chế độ DEFAULT.
Hãy dùng một toán tử đã được DSL định nghĩa.
~~~

Với ký tự vô hình:

~~~text
rules.dsl:12:7: Ký tự khoảng trắng không được hỗ trợ.
Mã Unicode: U+00A0 (NO-BREAK SPACE).
Hãy thay bằng dấu cách ASCII nếu đây là khoảng trắng phân tách token.
~~~

Với byte không giải mã được:

~~~text
Không thể giải mã tệp rules.dsl theo UTF-8 tại byte offset 143.
Hãy lưu tệp bằng UTF-8 hoặc chọn đúng encoding đầu vào.
~~~

### 12.1. Hiển thị ký tự an toàn

Không nên in trực tiếp ký tự điều khiển hoặc ký tự định hướng vào thông báo lỗi nếu nó có thể làm thay đổi cách hiển thị. Có thể hiển thị dạng escape hoặc mã code point.

Ví dụ, thay vì chỉ hiển thị một ký tự không nhìn thấy, hiển thị U+200B và tên ZERO WIDTH SPACE nếu công cụ có bảng tên Unicode.

### 12.2. Vị trí nguồn

Lexer nên lưu offset bắt đầu và kết thúc của token hoặc lỗi. Dòng/cột có thể được tính từ offset theo quy ước của editor.

Các quy ước cột có thể khác nhau:

- Byte UTF-8.
- Unicode code point.
- UTF-16 code unit.
- Cột hiển thị, có tính đến tab và ký tự rộng.

Nếu editor dùng UTF-16 nhưng lexer đếm code point, cần có bước chuyển đổi để gạch chân đúng vị trí.

### 12.3. Span của lỗi

Với một ký tự đơn lẻ, span có thể bao phủ đúng code point đó. Với escape không hợp lệ, span nên bao phủ cả dấu gạch chéo ngược và ký tự theo sau. Với chuỗi chưa đóng, có thể chỉ ra vị trí mở chuỗi và vị trí EOF.

## 13. Chuẩn hóa và thay thế ký tự

Chuẩn hóa đầu vào có thể hữu ích nhưng cũng có thể làm thay đổi ý nghĩa của DSL.

### 13.1. Không tự ý xóa ký tự lạ

Nếu lexer âm thầm xóa ký tự không hợp lệ, chương trình có thể được hiểu khác với nội dung người viết nhập.

Ví dụ:

~~~text
total = 10 @ 5
~~~

Nếu @ bị xóa, chương trình có thể trở thành một chuỗi khác với ý định ban đầu. Nếu @ được thay bằng khoảng trắng hoặc toán tử mặc định, hành vi càng khó dự đoán.

Hãy báo lỗi và chỉ tiếp tục theo một chính sách phục hồi được đặc tả.

### 13.2. Chuẩn hóa newline

Một số công cụ chuẩn hóa CRLF thành LF trước khi lexer chạy. Nếu làm vậy, cần giữ mapping từ offset chuẩn hóa về offset nguồn gốc nếu thông báo lỗi hoặc formatter cần vị trí trong tệp ban đầu.

### 13.3. Chuẩn hóa Unicode

Chuẩn hóa Unicode có thể giúp so sánh định danh nhất quán. Tuy nhiên:

- Chỉ áp dụng theo chính sách được công bố.
- Không thay đổi nội dung chuỗi nếu miền cần giữ nguyên dữ liệu.
- Giữ span nguồn để thông báo lỗi trỏ đúng vị trí.
- Dùng cùng quy tắc trong lexer, symbol table và runtime.

### 13.4. Thay thế khi decoding

Một số thư viện giải mã có chế độ thay byte lỗi bằng ký tự U+FFFD. Cách này hữu ích cho hiển thị văn bản hỏng, nhưng với mã DSL có thể che giấu lỗi encoding. Nếu dùng chế độ thay thế, công cụ phải ghi nhận decoding error và không được coi kết quả là nguồn hợp lệ để thực thi.

## 14. Ký tự dễ gây nhầm lẫn và an toàn mã nguồn

Một số ký tự không làm lexer thất bại nhưng có thể làm người đọc hiểu sai nội dung.

### 14.1. Ký tự giống nhau về hình thức

Ví dụ, chữ Latin a và một ký tự từ hệ chữ khác có thể trông giống nhau. Hai tên hiển thị gần như giống hệt nhưng không bằng nhau ở mức code point.

Với định danh quan trọng như tên quyền, tên hàm hoặc tên cấu hình, công cụ có thể cảnh báo ký tự hỗn hợp nhiều hệ chữ hoặc ký tự dễ nhầm lẫn.

### 14.2. Ký tự vô hình trong định danh

Một tên có thể chứa zero-width character khiến người đọc không thấy sự khác biệt. DSL có thể cấm các ký tự đó trong identifier và đưa mã Unicode vào thông báo lỗi.

### 14.3. Ký tự định hướng văn bản

Ký tự điều khiển hướng có thể khiến đoạn mã hiển thị theo thứ tự khác với thứ tự lưu trữ. Nếu không cần thiết, nên cấm trong cú pháp và định danh; nếu cần trong nội dung văn bản, dùng escape hoặc hiển thị rõ trong công cụ review.

### 14.4. Không nhầm cảnh báo bảo mật với lỗi lexer

Một ký tự có thể hợp lệ về mặt từ vựng nhưng đáng cảnh báo vì gây nhầm lẫn. Công cụ có thể ghi diagnostic mức warning mà vẫn giữ token hợp lệ. Phân biệt error và warning giúp không từ chối nhầm nội dung hợp lệ.

### 14.5. Giữ nguyên bằng chứng đầu vào

Khi điều tra một lỗi hoặc nội dung đáng ngờ, cần giữ nguồn gốc hoặc span byte để xác định chính xác ký tự nào đã được nhập. Không nên tự động viết lại nội dung rồi chỉ lưu phiên bản đã sửa mà không có dấu vết.

## 15. Ký tự không hợp lệ trong chế độ chuỗi và chú thích

Chuỗi và chú thích thường có tập ký tự rộng hơn mã DSL, nhưng không phải hoàn toàn không giới hạn.

### 15.1. Chuỗi một dòng

Nếu DSL không cho phép newline trong chuỗi một dòng, lexer cần báo lỗi khi gặp newline trước dấu nháy đóng. Nó có thể phục hồi tại newline và quay về DEFAULT để parser tiếp tục.

### 15.2. Chuỗi nhiều dòng

Nếu DSL có triple-quoted string hoặc heredoc, newline được phép. Tuy nhiên, delimiter đóng, escape và EOF vẫn cần quy tắc rõ ràng.

### 15.3. Chú thích một dòng

Comment một dòng thường kết thúc ở newline. Ký tự lạ trong comment không phải lỗi từ vựng nếu quy tắc comment cho phép văn bản đó.

### 15.4. Chú thích nhiều dòng

Comment nhiều dòng kết thúc bằng delimiter đã định nghĩa. Nếu EOF xuất hiện trước delimiter, lexer có thể báo unterminated comment.

### 15.5. Ngôn ngữ nhúng

Nếu nội dung nhúng có lexer riêng, lỗi ký tự trong vùng đó nên được báo theo quy tắc của ngôn ngữ nhúng và ghi rõ vùng nguồn. Lexer chủ không nên gắn nhãn mọi ký tự lạ trong SQL là lỗi DSL.

## 16. Tình huống minh họa

Giả sử DSL quy tắc đơn hàng hỗ trợ:

~~~text
rule "bulk_discount" {
    when order.quantity >= 10
    then order.discount = 5%
}
~~~

### 16.1. Ký tự @ trong biểu thức

~~~text
when order.quantity @ 10
~~~

Nếu @ không phải toán tử được định nghĩa, lexer báo lỗi tại @. Parser có thể tiếp tục phân tích các token còn lại nếu lexer có chiến lược phục hồi.

### 16.2. Ký tự @ trong chuỗi

~~~text
message = "support@example.test"
~~~

Nếu chuỗi cho phép ký tự @, đây là văn bản hợp lệ. Lexer không được áp dụng tập ký tự của DEFAULT cho nội dung STRING.

### 16.3. Ký tự khoảng trắng không chuẩn

~~~text
when order.quantity >= 10
~~~

Nếu khoảng giữa quantity và >= là NO-BREAK SPACE nhưng DSL chỉ chấp nhận dấu cách ASCII và tab, lexer báo ký tự khoảng trắng không hỗ trợ. Thông báo nên hiển thị mã Unicode vì ký tự đó trông gần giống dấu cách bình thường.

### 16.4. Định danh có ký tự không được phép

~~~text
let customer@id = 10
~~~

Nếu @ không hợp lệ trong identifier, lexer có thể nhận customer, báo lỗi @, rồi tiếp tục nhận id. Parser có thể phát sinh thêm lỗi vì cấu trúc khai báo không khớp. Công cụ nên ưu tiên hiển thị lỗi gốc tại @ và hạn chế lỗi dây chuyền.

### 16.5. Ký tự hợp lệ nhưng token sai vị trí

~~~text
when order.quantity >= , 10
~~~

Dấu phẩy có thể là token hợp lệ của DSL nhưng không hợp lệ ở vị trí này theo grammar. Đây là lỗi cú pháp, không phải ký tự không hợp lệ.

## 17. Kiểm thử xử lý ký tự không hợp lệ

Lexer cần có kiểm thử cho cả đầu vào hợp lệ, đầu vào sai và cách phục hồi.

### 17.1. Kiểm thử ký tự hợp lệ

Kiểm tra các nhóm:

- Chữ cái và chữ số trong định danh.
- Dấu gạch dưới.
- Toán tử một ký tự và nhiều ký tự.
- Dấu ngoặc và dấu phân cách.
- Khoảng trắng, tab và newline được hỗ trợ.
- Ký tự Unicode trong chuỗi.
- Ký tự được phép trong comment.

### 17.2. Kiểm thử ký tự không hợp lệ

Ví dụ:

- @ trong DEFAULT nếu không được hỗ trợ.
- NUL trong mã nguồn.
- Ký tự điều khiển bị cấm trong chuỗi.
- Escape không tồn tại.
- Byte đầu vào không giải mã được.
- Ký tự Unicode bị cấm trong định danh.
- BOM xuất hiện ở giữa tệp nếu DSL không cho phép.

### 17.3. Kiểm thử theo mode

Đưa cùng một ký tự vào DEFAULT, STRING, COMMENT và vùng nhúng. Xác nhận kết quả khác nhau đúng theo đặc tả.

Ví dụ, @ có thể gây lỗi trong DEFAULT nhưng được chấp nhận trong STRING và COMMENT.

### 17.4. Kiểm thử vị trí nguồn

Đặt ký tự lỗi:

- Ở đầu tệp.
- Ở cuối dòng.
- Sau nhiều dòng.
- Sau tab.
- Cạnh ký tự Unicode nhiều byte.
- Bên trong chuỗi có escape.

Kiểm tra offset, dòng, cột và span được báo chính xác theo quy ước.

### 17.5. Kiểm thử phục hồi

Với nguồn có nhiều ký tự lỗi, xác nhận:

- Lexer không treo.
- Con trỏ luôn tiến lên.
- Không lặp vô hạn ở cùng vị trí.
- Token sau lỗi được nhận diện đúng nếu có thể phục hồi.
- Một lỗi không tạo quá nhiều diagnostic trùng lặp.

### 17.6. Kiểm thử fuzz

Fuzz testing có thể tạo chuỗi ký tự ngẫu nhiên, bao gồm Unicode, byte lỗi ở lớp decoding, delimiter chưa đóng và ký tự điều khiển. Mục tiêu là bảo đảm lexer luôn kết thúc có kiểm soát, không crash, không treo và không vượt giới hạn tài nguyên.

Khi fuzzing, cần lưu lại seed và đầu vào gây lỗi để có thể tái hiện.

### 17.7. Kiểm thử hồi quy

Khi mở rộng tập ký tự hợp lệ, chạy lại các ví dụ cũ. Một ký tự mới được phép trong định danh có thể làm thay đổi cách tách token trước đây. Cần xác định đó là thay đổi có chủ đích hay lỗi tương thích.

## 18. Những lỗi triển khai thường gặp

### 18.1. Bỏ qua mọi ký tự không nhận diện được

Lexer âm thầm bỏ qua ký tự lạ có thể làm nguồn được hiểu khác ý định. Luôn phát diagnostic hoặc áp dụng một quy tắc phục hồi được công bố.

### 18.2. Tiêu thụ nhiều ký tự hơn vùng lỗi

Nếu lexer bỏ cả phần còn lại của dòng cho một ký tự sai, nó có thể làm mất nhiều token hợp lệ. Chỉ đồng bộ ở newline khi grammar và mode bảo đảm đó là điểm an toàn.

### 18.3. Đếm byte như đếm ký tự

Trong UTF-8, một code point có thể chiếm nhiều byte. Bỏ một byte giữa chuỗi nhiều byte có thể làm hỏng toàn bộ phần còn lại. Lexer cần thao tác theo đơn vị đã giải mã và giữ offset byte riêng khi cần.

### 18.4. Không phân biệt ký tự vô hình

Thông báo chỉ in ký tự khoảng trắng có thể không giúp người dùng nhận ra vấn đề. Nên hiển thị U+XXXX hoặc tên ký tự.

### 18.5. Dùng cùng tập ký tự cho mọi mode

Ký tự hợp lệ trong chuỗi hoặc comment có thể không hợp lệ trong biểu thức. Cần gắn quy tắc với mode hiện tại.

### 18.6. Nhầm lỗi lexer với lỗi parser

Nếu token đã được nhận diện nhưng xuất hiện sai vị trí, đó thường là lỗi cú pháp. Gán sai loại lỗi làm người dùng khó hiểu và làm công cụ khó hỗ trợ.

### 18.7. Thay thế ký tự mà không giữ vị trí

Chuẩn hóa hoặc thay thế đầu vào có thể làm offset không còn trỏ đúng nguồn. Nếu cần biến đổi, hãy giữ mapping từ văn bản đã biến đổi về nguồn gốc.

### 18.8. Không kiểm tra tiến triển khi phục hồi

Một vòng lặp báo lỗi mà không tiêu thụ đầu vào có thể lặp vô hạn. Mọi nhánh phục hồi phải tiến lên, kết thúc hoặc chuyển trạng thái có kiểm soát.

## 19. Quy trình thiết kế chính sách ký tự cho DSL

Có thể thực hiện theo các bước:

1. Liệt kê các mode từ vựng và các loại token trong từng mode.
2. Xác định tập ký tự được phép cho định danh, số, chuỗi, toán tử, khoảng trắng và chú thích.
3. Quy định encoding đầu vào, BOM, newline và cách xử lý byte không hợp lệ.
4. Quy định hỗ trợ Unicode, chuẩn hóa và chính sách cho ký tự vô hình.
5. Xác định ký tự nào gây lỗi, ký tự nào chỉ tạo warning.
6. Quy định chiến lược phục hồi: dừng, bỏ qua một code point, phát token lỗi hoặc đồng bộ tại delimiter.
7. Xác định quy ước offset, dòng, cột và span nguồn.
8. Thiết kế thông báo lỗi có mã ký tự khi cần.
9. Viết kiểm thử cho từng nhóm ký tự và từng mode.
10. Ghi lại các thay đổi tập ký tự như thay đổi ngôn ngữ để đánh giá tương thích.

## 20. Bài tập tự kiểm tra

### Bài 1: Phân loại lỗi

Giả sử DSL không hỗ trợ ký tự @, nhưng cho phép dấu phẩy và dấu chấm phẩy làm token. Hãy phân loại:

~~~text
total = 10 @ 2
total = 10, 2
total = 10;
~~~

Trường hợp nào là lỗi từ vựng? Trường hợp nào có thể là lỗi cú pháp tùy grammar?

### Bài 2: Ký tự theo mode

Một DSL có DEFAULT, STRING và COMMENT. Hãy xác định @, # và dấu nháy kép có thể được xử lý thế nào ở từng mode.

### Bài 3: Định danh

Với quy tắc định danh bắt đầu bằng chữ cái hoặc dấu gạch dưới, theo sau là chữ, số hoặc dấu gạch dưới, hãy phân loại:

~~~text
order
_order
order2
2order
order-id
order@id
~~~

Giải thích ranh giới token có thể được nhận diện.

### Bài 4: Escape sequence

DSL hỗ trợ các escape dấu nháy kép, dấu gạch chéo ngược, newline và tab. Hãy xác định escape nào hợp lệ và thông báo lỗi cho escape không được định nghĩa.

### Bài 5: Unicode

Một định danh tiếng Việt nhìn thấy đúng nhưng không được lexer chấp nhận. Hãy nêu các nguyên nhân có thể liên quan đến Unicode category, dấu kết hợp và chuẩn hóa.

### Bài 6: Khoảng trắng vô hình

Một dòng DSL chứa NO-BREAK SPACE giữa hai token. Hãy đề xuất cách thông báo lỗi để người dùng nhận ra ký tự đó và sửa được.

### Bài 7: Encoding

Một tệp được khai báo UTF-8 nhưng chứa byte không hợp lệ. Hãy phân biệt decoding error với lexical error và nêu thông tin vị trí nên lưu.

### Bài 8: Phục hồi

Cho nguồn có hai ký tự @ không hợp lệ trên hai dòng. Hãy mô tả cách lexer có thể báo cả hai lỗi mà vẫn tiếp tục nhận diện token hợp lệ sau mỗi lỗi.

### Bài 9: An toàn mã nguồn

Một định danh trộn chữ Latin và Cyrillic có hình thức gần giống nhau. Hãy đề xuất chính sách cảnh báo hoặc từ chối mà không tự động đổi tên.

### Bài 10: Thiết kế kiểm thử

Hãy lập một bộ test bao gồm ký tự hợp lệ, không hợp lệ, ký tự vô hình, Unicode, lỗi encoding, escape sai, EOF và phục hồi. Nêu kết quả mong đợi cho từng nhóm.

## Kết luận

Ký tự không hợp lệ là ký tự mà lexer không thể chấp nhận tại vị trí và chế độ hiện tại theo đặc tả từ vựng của DSL. Để xử lý đúng, ngôn ngữ cần quy định rõ tập ký tự cho từng vùng như định danh, số, chuỗi, chú thích và ngôn ngữ nhúng. Unicode, encoding, ký tự vô hình và ký tự điều khiển đòi hỏi chính sách riêng để tránh nhầm lẫn và giữ đúng dữ liệu nguồn. Khi gặp lỗi, lexer cần báo vị trí và mã ký tự phù hợp, phục hồi có kiểm soát và bảo đảm tiến triển. Phân biệt lỗi từ vựng với lỗi cú pháp, kiểu và nghiệp vụ giúp người viết sửa đúng nguyên nhân, đồng thời giúp công cụ DSL xử lý đầu vào nhất quán và đáng tin cậy.
