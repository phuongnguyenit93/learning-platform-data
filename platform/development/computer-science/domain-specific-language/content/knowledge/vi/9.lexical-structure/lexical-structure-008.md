# Ký tự thoát trong DSL

Ngôn ngữ đặc tả miền (Domain-Specific Language, DSL) thường cần biểu diễn văn bản, ký hiệu, đường dẫn, biểu thức hoặc dữ liệu có chứa những ký tự vốn đã được dùng làm dấu phân cách cú pháp. Ví dụ, dấu nháy kép dùng để mở và đóng chuỗi; dấu gạch chéo ngược có thể mở đầu một escape sequence; dấu xuống dòng có thể kết thúc một câu lệnh. Nếu người dùng muốn đưa chính những ký tự đó vào giá trị, ngôn ngữ phải có quy tắc để phân biệt ký tự dữ liệu với ký tự điều khiển cú pháp.

**Ký tự thoát** (*escape character*) là ký tự đặc biệt báo cho bộ phân tích rằng ký tự tiếp theo hoặc một nhóm ký tự tiếp theo cần được hiểu theo một cách khác với ý nghĩa thông thường. Một tổ hợp như vậy được gọi là **chuỗi thoát** (*escape sequence*). Quá trình diễn giải các chuỗi này giúp DSL biểu diễn được dấu nháy, dấu gạch chéo, ký tự xuống dòng, tab và nhiều ký tự khác bên trong literal.

Ký tự thoát có vẻ là chi tiết nhỏ của cú pháp, nhưng quy tắc không rõ ràng có thể làm văn bản bị phân tích sai, dữ liệu bị thay đổi hoặc tạo ra lỗ hổng khi DSL chứa một ngôn ngữ khác như regex, SQL hay HTML. Vì vậy, thiết kế DSL cần xác định rõ ký tự thoát, những escape sequence được hỗ trợ, cách xử lý chuỗi không hợp lệ và thời điểm giải mã.

## 1. Ký tự thoát và chuỗi thoát là gì?

### 1.1. Ký tự có ý nghĩa đặc biệt trong cú pháp

Giả sử DSL dùng dấu nháy kép để bao quanh chuỗi:

~~~text
message = "Hello"
~~~

Parser xem dấu nháy đầu tiên là điểm bắt đầu chuỗi và dấu nháy cuối cùng là điểm kết thúc. Nếu người dùng muốn giá trị chuỗi chứa dấu nháy kép, cách viết trực tiếp sau đây sẽ gây nhầm lẫn:

~~~text
message = "He said "Hello""
~~~

Parser có thể hiểu chuỗi kết thúc ngay trước từ Hello, sau đó gặp những token không hợp lệ. DSL cần một quy ước để nói rằng dấu nháy ở giữa là dữ liệu, không phải dấu kết thúc.

Với dấu gạch chéo ngược làm ký tự thoát, người dùng có thể viết:

~~~text
message = "He said \"Hello\""
~~~

Trong đó, dấu gạch chéo ngược đứng trước dấu nháy làm thay đổi cách hiểu của dấu nháy tiếp theo. Chuỗi được giải mã có nội dung:

~~~text
He said "Hello"
~~~

### 1.2. Ký tự thoát và chuỗi thoát

Hai thuật ngữ cần phân biệt:

| Thuật ngữ | Ý nghĩa | Ví dụ |
|---|---|---|
| Ký tự thoát (*escape character*) | Ký tự mở đầu hoặc báo hiệu cách diễn giải đặc biệt | Dấu gạch chéo ngược |
| Chuỗi thoát (*escape sequence*) | Tổ hợp ký tự được diễn giải thành một ký tự hoặc giá trị đặc biệt | \n, \t, \", \\ |
| Giải mã chuỗi thoát (*unescaping*) | Chuyển chuỗi biểu diễn thành giá trị ký tự tương ứng | Hai ký tự \ và n thành một ký tự xuống dòng |

Trong nhiều ngôn ngữ, ký tự thoát là dấu gạch chéo ngược. Tuy nhiên, đây không phải quy tắc bắt buộc cho mọi DSL. Một số ngôn ngữ dùng dấu nháy kép lặp lại, dấu nháy đơn, dấu gạch chéo hoặc cú pháp raw string để tránh phải thoát nhiều ký tự.

### 1.3. Escape sequence không nhất thiết chỉ tạo ra một ký tự

Một chuỗi thoát có thể biểu diễn:

- Một ký tự điều khiển như xuống dòng hoặc tab.
- Một ký tự phân cách như dấu nháy.
- Chính ký tự thoát.
- Một ký tự Unicode được chỉ định bằng mã số.
- Một dạng kết thúc dòng hoặc nối dòng theo quy tắc của DSL.

Ví dụ, \u0041 có thể biểu diễn chữ A theo mã Unicode U+0041 trong một cú pháp chuỗi hỗ trợ dạng thoát Unicode.

## 2. Vì sao DSL cần ký tự thoát?

### 2.1. Biểu diễn dấu phân cách bên trong dữ liệu

Ký tự thoát cho phép đưa dấu nháy hoặc dấu phân cách vào trong chuỗi mà không kết thúc literal quá sớm.

~~~text
title = "The \"Domain Language\" guide"
quote = 'It\'s a useful rule'
~~~

Ví dụ trên giả định DSL hỗ trợ cả chuỗi dùng nháy kép và nháy đơn, đồng thời cho phép thoát dấu nháy tương ứng. Một DSL khác có thể chọn chỉ một loại dấu nháy hoặc dùng cách lặp dấu nháy.

### 2.2. Biểu diễn ký tự không thể nhìn thấy

Một số ký tự có ý nghĩa nhưng không hiển thị thành hình dạng dễ nhận ra, chẳng hạn:

- Ký tự xuống dòng.
- Ký tự tab.
- Ký tự carriage return.
- Ký tự điều khiển.
- Ký tự null trong một số môi trường dữ liệu.

Chuỗi thoát giúp người dùng nhìn thấy chúng dưới dạng văn bản có thể đọc:

~~~text
report = "Name\tAmount\nLan\t250000\nMinh\t310000"
~~~

Giá trị sau giải mã gồm các cột phân cách bằng tab và các dòng phân cách bằng ký tự xuống dòng.

### 2.3. Biểu diễn chính ký tự thoát

Nếu dấu gạch chéo ngược là ký tự thoát, người dùng cần một cách để đưa dấu gạch chéo ngược thực sự vào giá trị.

~~~text
path = "C:\\data\\orders"
~~~

Mỗi cặp dấu gạch chéo ngược trong văn bản nguồn được giải mã thành một dấu gạch chéo ngược trong giá trị chuỗi. Đây là lý do đường dẫn Windows thường có nhiều dấu gạch chéo khi viết trong literal của một số ngôn ngữ.

### 2.4. Truyền tải văn bản qua nhiều lớp

DSL có thể chứa một biểu thức khác. Ví dụ, một quy tắc có thể lưu biểu thức chính quy, truy vấn hoặc đoạn mã mẫu trong một literal chuỗi. Khi đó, ký tự có ý nghĩa ở ngôn ngữ bên trong cũng có thể cần được biểu diễn trong ngôn ngữ bên ngoài.

Nếu không phân biệt từng lớp, người viết dễ thoát quá ít hoặc quá nhiều. Đây là một trong những nguồn lỗi phổ biến khi DSL chứa regex, JSON, SQL, HTML hoặc biểu thức mẫu.

## 3. Các escape sequence thường gặp

Một DSL có thể định nghĩa tập escape sequence riêng. Bảng dưới đây là quy ước thường gặp trong nhiều ngôn ngữ dạng C; không phải DSL nào cũng phải hỗ trợ toàn bộ.

| Chuỗi thoát | Ý nghĩa thường gặp |
|---|---|
| \\\\ | Một dấu gạch chéo ngược |
| \\" | Một dấu nháy kép |
| \\' | Một dấu nháy đơn |
| \\n | Ký tự xuống dòng (line feed) |
| \\r | Ký tự carriage return |
| \\t | Ký tự tab |
| \\b | Backspace |
| \\f | Form feed |
| \\0 | Ký tự null trong một số ngôn ngữ |
| \\uXXXX | Ký tự Unicode được chỉ định bằng bốn chữ số thập lục phân, trong những ngôn ngữ hỗ trợ dạng này |

Ví dụ:

~~~text
text = "First line\nSecond line"
tabbed = "Name\tValue"
quoted = "She said: \"Ready?\""
slash = "A backslash: \\"
~~~

Sau giải mã:

- text có hai dòng.
- tabbed có ký tự tab giữa Name và Value.
- quoted chứa dấu nháy kép quanh Ready?.
- slash kết thúc bằng một dấu gạch chéo ngược.

Không nên tự suy đoán ý nghĩa của một chuỗi thoát chỉ dựa trên ký tự. DSL phải công bố bảng escape sequence và giữ ngữ nghĩa ổn định giữa các phiên bản.

## 4. Escape sequence trong cú pháp chuỗi

### 4.1. Chuỗi dùng dấu nháy kép

Một lựa chọn phổ biến là dùng dấu nháy kép để mở và đóng literal:

~~~text
message = "Hello, world"
~~~

Trong dạng này, DSL có thể quy định:

- Dấu nháy kép kết thúc chuỗi.
- Dấu gạch chéo ngược mở đầu escape sequence.
- Các ký tự thông thường được giữ nguyên.
- Ký tự xuống dòng trực tiếp có thể bị cấm hoặc được cho phép theo quy tắc riêng.

### 4.2. Chuỗi dùng dấu nháy đơn

Một số DSL cho phép cả hai loại dấu nháy:

~~~text
doubleQuoted = "It's a rule"
singleQuoted = 'The word "rule" is quoted'
~~~

Điều này giảm nhu cầu thoát khi chuỗi chứa dấu nháy của loại còn lại. Tuy nhiên, nếu chuỗi chứa cả nháy đơn và nháy kép, người dùng vẫn cần quy tắc escape rõ ràng.

### 4.3. Dùng dấu nháy lặp thay cho ký tự thoát

Một số ngôn ngữ dùng cách lặp lại dấu phân cách để biểu diễn dấu nháy bên trong chuỗi. Ví dụ, một quy ước kiểu SQL:

~~~sql
SELECT 'It''s a rule';
~~~

Hai dấu nháy đơn liên tiếp được hiểu là một dấu nháy đơn thuộc dữ liệu. Cách này không cần dấu gạch chéo ngược cho trường hợp đó.

Một DSL có thể chọn quy tắc này vì nó dễ nhận diện và tránh xung đột với dấu gạch chéo ngược trong đường dẫn hoặc biểu thức chính quy. Nhưng không nên đồng thời hỗ trợ nhiều cơ chế tương đương nếu chúng làm cú pháp khó đoán.

### 4.4. Chuỗi nhiều dòng

Đối với nội dung dài, DSL có thể hỗ trợ literal nhiều dòng:

~~~text
message = """
This is the first line.
This is the second line.
"""
~~~

Khi dùng chuỗi nhiều dòng, cần xác định:

- Ký tự xuống dòng trong nội dung được giữ nguyên hay chuẩn hóa?
- Thụt lề có được loại bỏ không?
- Dấu phân cách đóng có thể xuất hiện trong nội dung không?
- Có escape sequence trong chuỗi nhiều dòng không?
- Chuỗi có nội suy biến hay không?

Nếu literal nhiều dòng vẫn xử lý escape sequence, người dùng phải biết lúc nào dấu gạch chéo ngược có ý nghĩa đặc biệt. Một số DSL chọn raw multiline string để tránh giải mã escape.

### 4.5. Chuỗi thô (raw string)

Raw string là dạng literal trong đó ký tự thoát thường được giữ nguyên thay vì giải mã theo quy tắc chuỗi thông thường.

Ví dụ minh họa:

~~~text
normalPattern = "\\d{3}-\\d{4}"
rawPattern = r"\d{3}-\d{4}"
~~~

Với giả định DSL hỗ trợ tiền tố r, giá trị rawPattern chứa nguyên dấu gạch chéo ngược trước d. Điều này thuận tiện khi viết regex hoặc đường dẫn.

Raw string không có nghĩa là nội dung được bỏ qua mọi quy tắc. Dấu phân cách kết thúc literal vẫn phải được xử lý, và ngôn ngữ bên trong (ví dụ regex) vẫn diễn giải ký hiệu của chính nó.

### 4.6. Nối dòng và ký tự thoát cuối dòng

Một số ngôn ngữ cho phép dấu gạch chéo ngược ở cuối dòng để nối dòng vật lý thành một câu lệnh logic. Đây là quy tắc khác với escape newline bên trong giá trị chuỗi.

Ví dụ minh họa:

~~~text
condition = customer.tier == GOLD \
            and order.total >= 1000000
~~~

Trong cú pháp này, dấu gạch chéo cuối dòng báo rằng biểu thức tiếp tục ở dòng sau. Nếu DSL hỗ trợ cơ chế này, cần quy định khoảng trắng được giữ hay bỏ và hành vi khi dấu gạch chéo không đứng cuối dòng.

Không nên nhầm nối dòng trong mã nguồn với chuỗi có chứa ký tự xuống dòng. Hai thao tác có ý nghĩa khác nhau.

## 5. Quy tắc phân tích escape sequence

### 5.1. Phân tích theo từng ký tự

Parser hoặc lexer thường đọc chuỗi từ trái sang phải. Khi gặp ký tự thoát, nó đọc thêm ký tự tiếp theo để xác định escape sequence.

Ví dụ với chuỗi nguồn:

~~~text
"A\nB"
~~~

Quá trình giải mã:

1. Đọc dấu nháy mở đầu.
2. Đọc ký tự A và đưa vào giá trị.
3. Gặp dấu gạch chéo ngược, chuyển sang chế độ đọc escape sequence.
4. Gặp n, ánh xạ cặp \n thành ký tự xuống dòng.
5. Đọc ký tự B.
6. Gặp dấu nháy đóng và kết thúc literal.

Kết quả là ba phần: A, ký tự xuống dòng và B.

### 5.2. Ngữ pháp minh họa

Một grammar đơn giản cho chuỗi có thể được mô tả bằng EBNF:

~~~text
stringLiteral  = '"', { stringCharacter }, '"' ;
stringCharacter = ordinaryCharacter | escapeSequence ;
escapeSequence = '\', escapeCode ;
escapeCode     = '"' | '\' | 'n' | 'r' | 't' ;
~~~

Đây là mô tả khái niệm. Một grammar đầy đủ cần quy định cách xử lý ký tự điều khiển, Unicode, chuỗi nhiều dòng và lỗi.

Điểm quan trọng là ký tự thoát được xử lý trong ngữ cảnh literal chuỗi. Không nên áp dụng quy tắc giải mã chuỗi cho toàn bộ văn bản DSL, vì dấu gạch chéo ngược có thể có ý nghĩa khác trong regex, comment hoặc cú pháp khác.

### 5.3. Escape không hợp lệ

Giả sử DSL chỉ hỗ trợ:

~~~text
\n, \r, \t, \", \\
~~~

Khi gặp:

~~~text
message = "Hello\q"
~~~

Parser cần có chính sách rõ ràng. Những lựa chọn thường gặp:

- Báo lỗi vì q không phải mã thoát được hỗ trợ.
- Giữ nguyên dấu gạch chéo và q, nếu DSL công bố rõ hành vi này.
- Chấp nhận một tập escape mở rộng theo phiên bản.

Đối với DSL cần tính xác định, báo lỗi thường an toàn hơn việc âm thầm bỏ dấu gạch chéo. Nếu parser tự loại bỏ ký tự thoát không nhận diện, dữ liệu có thể bị biến đổi ngoài dự kiến.

### 5.4. Ký tự thoát ở cuối chuỗi

Một dấu gạch chéo ngược ngay trước dấu nháy đóng có thể khiến parser hiểu rằng dấu nháy đó đã được thoát và chuỗi chưa kết thúc.

Ví dụ, literal có vẻ như muốn chứa một dấu gạch chéo cuối cùng:

~~~text
path = "C:\temp\"
~~~

Trong DSL dùng dấu gạch chéo ngược làm ký tự thoát, cách viết này có thể không hợp lệ vì dấu gạch chéo cuối cùng thoát dấu nháy đóng. Người dùng cần viết:

~~~text
path = "C:\\temp\\"
~~~

hoặc dùng raw string nếu DSL cung cấp một cách kết thúc raw literal không xung đột.

## 6. Unicode và ký tự ngoài ASCII

### 6.1. Escape Unicode

DSL có thể hỗ trợ biểu diễn ký tự bằng mã Unicode:

~~~text
letterA = "\u0041"
heart = "\u2764"
~~~

Trong một số ngôn ngữ, dạng \uXXXX yêu cầu đúng bốn chữ số thập lục phân. Ngôn ngữ khác hỗ trợ dạng code point có độ dài thay đổi, ví dụ:

~~~text
smile = "\u{1F600}"
~~~

DSL phải chọn một hoặc nhiều dạng và định nghĩa chính xác giới hạn, chữ số hợp lệ, cách xử lý code point không hợp lệ và cách lưu kết quả.

### 6.2. Code point và đơn vị mã

Unicode phân biệt code point với cách mã hóa thành byte hoặc đơn vị mã. Một code point có thể cần nhiều đơn vị mã trong UTF-16. Vì vậy, parser không nên giả định mọi ký tự đều có độ dài một đơn vị mã.

Nếu DSL hỗ trợ escape Unicode, cần xác định:

- Dạng escape chỉ nhận code point hợp lệ hay cũng cho phép surrogate riêng lẻ?
- Có chấp nhận cặp surrogate không?
- Code point ngoài phạm vi Unicode hợp lệ được xử lý thế nào?
- Nội dung được lưu và truyền theo encoding nào?

Trong nhiều DSL mới, dạng escape code point rõ ràng giúp tránh nhầm lẫn giữa cặp surrogate và ký tự thực.

### 6.3. Ký tự kết hợp và ký tự hiển thị

Một ký tự người dùng nhìn thấy có thể được tạo từ nhiều code point, chẳng hạn chữ cái và dấu kết hợp. Hai chuỗi có thể hiển thị giống nhau nhưng có biểu diễn Unicode khác nhau.

Nếu DSL so sánh chuỗi, tên định danh hoặc khóa nghiệp vụ, cần quyết định có chuẩn hóa Unicode hay không. Chuẩn hóa là vấn đề xử lý văn bản và ngữ nghĩa, không thể giải quyết chỉ bằng escape sequence.

### 6.4. Escape không phải mã hóa ký tự

Escape sequence là quy ước biểu diễn ký tự trong cú pháp. Encoding như UTF-8 là cách chuyển văn bản thành byte để lưu trữ hoặc truyền tải.

Ví dụ, ký tự A có thể được viết trong literal dưới dạng \u0041, nhưng khi nội dung DSL được lưu bằng UTF-8, giá trị chuỗi sau giải mã được mã hóa thành byte theo UTF-8.

Hai bước này khác nhau:

1. Parser giải mã escape sequence thành giá trị ký tự.
2. Bộ mã hóa chuyển văn bản thành byte khi lưu hoặc truyền.

Không nên gọi hai bước này là một.

## 7. Ký tự thoát trong ngôn ngữ lồng nhau

### 7.1. Vấn đề nhiều lớp cú pháp

Một DSL có thể chứa một ngôn ngữ khác bên trong literal. Khi đó, cùng một dấu gạch chéo ngược có thể mang ý nghĩa ở nhiều lớp:

1. Lớp chuỗi của DSL bên ngoài.
2. Lớp cú pháp của ngôn ngữ bên trong.
3. Có thể thêm lớp biểu diễn trong mã nguồn của ngôn ngữ triển khai DSL.

Ví dụ, DSL lưu một biểu thức regex:

~~~text
pattern = "\\d{3}-\\d{4}"
~~~

Ở lớp DSL, hai ký tự gạch chéo ngược tạo thành một dấu gạch chéo trong giá trị chuỗi. Regex engine sau đó nhận:

~~~regex
\d{3}-\d{4}
~~~

Regex engine hiểu \d là một chữ số. Nếu người viết chỉ gõ một dấu gạch chéo trong chuỗi DSL thông thường, parser DSL có thể báo escape không hợp lệ hoặc giải mã sai trước khi regex engine nhìn thấy nó.

### 7.2. Raw string giảm số lớp thoát

Nếu DSL hỗ trợ raw string:

~~~text
pattern = r"\d{3}-\d{4}"
~~~

thì lớp chuỗi DSL giữ nguyên dấu gạch chéo. Regex engine vẫn diễn giải \d theo cú pháp regex.

Raw string giảm một lớp thoát nhưng không làm regex trở thành văn bản thuần. Các ký hiệu như ngoặc vuông, dấu cộng hoặc dấu chấm vẫn có ý nghĩa với regex engine.

### 7.3. Chuỗi chứa JSON

Giả sử một DSL lưu JSON trong literal:

~~~text
payload = "{\"name\":\"Lan\",\"active\":true}"
~~~

DSL giải mã các dấu nháy được thoát thành chuỗi JSON:

~~~json
{"name":"Lan","active":true}
~~~

Sau đó JSON parser mới phân tích nội dung. Có hai parser ở hai lớp khác nhau: parser DSL và parser JSON.

Nếu có thể, nên dùng cấu trúc dữ liệu hoặc block literal chuyên dụng thay vì lồng JSON vào một chuỗi dài. Cấu trúc có kiểu thường dễ kiểm tra và ít lỗi escape hơn.

### 7.4. Chuỗi chứa SQL

Không nên ghép trực tiếp dữ liệu người dùng vào chuỗi SQL chỉ bằng cách thay dấu nháy. Escape theo cú pháp chuỗi của DSL không tương đương với escaping an toàn cho SQL.

Ví dụ, DSL có thể cho phép:

~~~text
query = "SELECT * FROM customer WHERE name = 'Lan'"
~~~

Nếu giá trị tên đến từ người dùng, cần dùng tham số truy vấn ở tầng database:

~~~java
String sql = "SELECT * FROM customer WHERE name = ?";
PreparedStatement statement = connection.prepareStatement(sql);
statement.setString(1, customerName);
~~~

Tham số hóa giữ dữ liệu tách biệt với cú pháp SQL. Không nên tự viết một hàm escape chung rồi sử dụng cho mọi hệ quản trị hoặc mọi ngữ cảnh SQL.

### 7.5. Chuỗi chứa HTML, JavaScript hoặc URL

Mỗi ngôn ngữ có quy tắc phân cách và diễn giải riêng. Một chuỗi đã được giải mã đúng ở DSL vẫn có thể không an toàn khi chèn vào HTML, JavaScript, CSS hoặc URL.

Ví dụ:

- HTML cần escaping hoặc encoding phù hợp với vị trí nội dung hay thuộc tính.
- JavaScript có quy tắc riêng cho chuỗi và literal.
- URL dùng percent-encoding cho từng thành phần phù hợp.
- CSS có quy tắc escape riêng.

Phải xử lý theo ngữ cảnh đích và ưu tiên API chuyên dụng. Không có một thao tác escape duy nhất an toàn cho mọi đầu ra.

## 8. Escape, quote, encode và sanitize

Các khái niệm này thường bị nhầm lẫn:

| Khái niệm | Mục tiêu | Ví dụ |
|---|---|---|
| Escape | Biểu diễn ký tự đặc biệt trong một cú pháp | \\" bên trong chuỗi dùng nháy kép |
| Quote | Bao quanh dữ liệu bằng dấu phân cách để tạo một cấu trúc | "hello" |
| Encoding | Chuyển dữ liệu sang một dạng biểu diễn khác theo quy tắc mã hóa | UTF-8, URL percent-encoding |
| Sanitization | Kiểm tra, loại bỏ hoặc biến đổi dữ liệu theo chính sách an toàn | Loại thẻ HTML không được phép |
| Validation | Kiểm tra dữ liệu có đáp ứng yêu cầu miền hay không | Kiểm tra địa chỉ email hoặc mã đơn hàng |

Escape không thay thế validation. Một chuỗi được escape đúng cú pháp vẫn có thể chứa giá trị không hợp lệ đối với miền. Tương tự, một chuỗi được validation không tự động an toàn khi chèn vào SQL hoặc HTML.

## 9. Thiết kế chính sách escape cho một DSL

### 9.1. Chọn ký tự thoát và dấu phân cách

Những quyết định đầu tiên gồm:

- Dùng dấu gạch chéo ngược hay cơ chế lặp dấu nháy?
- Chuỗi dùng nháy đơn, nháy kép hay cả hai?
- Có raw string không?
- Có literal nhiều dòng không?
- Escape sequence có phân biệt chữ hoa và chữ thường không?

Nên chọn quy tắc quen thuộc với nhóm người dùng và phù hợp với loại dữ liệu thường xuất hiện trong miền.

### 9.2. Định nghĩa tập escape được hỗ trợ

Không nên hỗ trợ một tập escape mơ hồ hoặc phụ thuộc vào môi trường. Tài liệu cần liệt kê từng chuỗi, giá trị kết quả và ngữ cảnh được phép.

Ví dụ, nếu DSL hỗ trợ \n trong string literal, cần xác định có hỗ trợ \N hay không. Nếu không, parser nên báo lỗi nhất quán.

### 9.3. Quy định escape không biết

Có ba lựa chọn phổ biến:

1. **Strict:** báo lỗi với escape sequence không được nhận diện. Đây thường là lựa chọn dễ dự đoán.
2. **Preserve:** giữ nguyên dấu thoát và ký tự tiếp theo. Chỉ nên dùng khi quy tắc này được công bố và không tạo ra sự mơ hồ.
3. **Legacy permissive:** chấp nhận cách viết cũ để tương thích. Cần có cảnh báo và kế hoạch chuyển đổi nếu hành vi có thể gây nhầm lẫn.

Không nên âm thầm bỏ dấu thoát vì có thể làm thay đổi dữ liệu mà người dùng không nhận ra.

### 9.4. Xác định thời điểm giải mã

Escape sequence thường được giải mã khi lexer tạo token literal hoặc ở bước chuyển token thành giá trị. Cần chọn một thời điểm rõ ràng.

Nếu giải mã nhiều lần, một chuỗi đã được giải mã có thể tiếp tục bị diễn giải ngoài ý muốn. Nếu không giải mã ở nơi cần thiết, runtime có thể nhận văn bản nguồn thay vì giá trị mong muốn.

Ví dụ, nguồn có hai ký tự \ và n có thể biểu diễn một newline. Sau lần giải mã đúng, giá trị chỉ còn một ký tự newline. Nếu áp dụng bộ giải mã lần nữa lên dữ liệu đã giải mã hoặc dữ liệu người dùng, kết quả có thể khác dự kiến.

### 9.5. Giữ thông tin vị trí nguồn

Khi parser giải mã chuỗi, nên giữ liên kết giữa vị trí trong giá trị và vị trí trong văn bản nguồn. Nếu escape sequence sai, thông báo lỗi cần trỏ đúng vị trí của dấu gạch chéo hoặc mã thoát.

Ví dụ:

~~~text
message = "Hello\q"
                 ^
~~~

Thông báo có thể là: Escape sequence \q không được hỗ trợ trong string literal. Các mã hợp lệ gồm \n, \r, \t, \", và \\.

## 10. Cài đặt bộ giải mã chuỗi

### 10.1. Nguyên tắc xử lý

Một bộ giải mã chuỗi cơ bản có thể đọc từng ký tự:

1. Nếu ký tự không phải ký tự thoát, đưa nó vào kết quả.
2. Nếu gặp ký tự thoát, kiểm tra xem còn ký tự tiếp theo không.
3. Đọc mã thoát và ánh xạ sang giá trị tương ứng.
4. Nếu mã không hợp lệ, trả về diagnostic có vị trí nguồn.
5. Tiếp tục đến hết literal.

Không nên dùng thao tác thay thế chuỗi toàn cục theo nhiều lượt nếu các escape sequence có thể tạo ra ký tự giống ký tự mở đầu escape. Cách thay thế nhiều lượt có thể vô tình giải mã lặp.

### 10.2. Pseudocode

~~~text
function decodeString(source):
    result = empty buffer
    i = 0

    while i < source.length:
        ch = source[i]

        if ch is not backslash:
            append ch to result
            i = i + 1
            continue

        if i + 1 >= source.length:
            error("Incomplete escape sequence", i)

        code = source[i + 1]

        switch code:
            case "n": append newline
            case "r": append carriage return
            case "t": append tab
            case "\"": append double quote
            case "\": append backslash
            default: error("Unknown escape sequence", i)

        i = i + 2

    return result
~~~

Pseudocode này chỉ minh họa các escape một ký tự. Nếu hỗ trợ Unicode, octal hoặc escape có độ dài thay đổi, bộ giải mã cần đọc thêm chữ số, kiểm tra giới hạn và bảo đảm không vượt khỏi literal.

### 10.3. Ví dụ triển khai Java rút gọn

~~~java
static String decodeEscapes(String source) {
    StringBuilder result = new StringBuilder();

    for (int i = 0; i < source.length(); i++) {
        char current = source.charAt(i);

        if (current != '\\') {
            result.append(current);
            continue;
        }

        if (i + 1 >= source.length()) {
            throw new IllegalArgumentException(
                "Incomplete escape sequence at index " + i
            );
        }

        char code = source.charAt(++i);
        switch (code) {
            case 'n' -> result.append('\n');
            case 'r' -> result.append('\r');
            case 't' -> result.append('\t');
            case '"' -> result.append('"');
            case '\\' -> result.append('\\');
            default -> throw new IllegalArgumentException(
                "Unknown escape sequence at index " + (i - 1)
            );
        }
    }

    return result.toString();
}
~~~

Đây là ví dụ minh họa cho một tập escape nhỏ. Parser sản phẩm cần có vị trí dòng và cột, xử lý Unicode theo chính sách của DSL, phân biệt raw string với string thông thường và trả diagnostic có cấu trúc thay vì chỉ ném exception tổng quát.

## 11. Ký tự thoát và bảo mật

### 11.1. Escape không phải biện pháp chống injection tổng quát

Một lỗi thiết kế phổ biến là nghĩ rằng chỉ cần thêm dấu gạch chéo trước ký tự đặc biệt thì dữ liệu sẽ an toàn trong mọi ngữ cảnh.

Điều này sai vì mỗi ngôn ngữ đích có quy tắc cú pháp riêng. Escape một chuỗi theo quy tắc DSL không bảo đảm chuỗi đó an toàn khi đưa vào SQL, HTML, shell hoặc JavaScript.

### 11.2. Tách dữ liệu khỏi cú pháp

Khi có thể, hãy dùng tham số hóa hoặc API cấu trúc để dữ liệu không bị diễn giải như mã.

Ví dụ, với SQL, dùng PreparedStatement thay vì nối chuỗi. Với HTML, dùng API tạo node và gán text content thay vì ghép HTML tùy ý. Với shell, ưu tiên API truyền đối số riêng thay vì dựng một dòng lệnh từ chuỗi người dùng.

### 11.3. Kiểm tra đầu vào theo miền

Sau khi giải mã escape, dữ liệu vẫn cần được kiểm tra theo kiểu và quy tắc miền. Ví dụ, chuỗi tên có thể cần giới hạn độ dài; đường dẫn cần được kiểm tra quyền và phạm vi; giá trị tiền tệ cần đơn vị hợp lệ.

### 11.4. Tránh giải mã kép

Giải mã kép xảy ra khi dữ liệu đã được giải mã một lần lại tiếp tục được xử lý như văn bản nguồn chứa escape sequence.

Ví dụ, người dùng có thể nhập hai ký tự \ và n như dữ liệu thật. Nếu hệ thống giải mã một lần theo cú pháp DSL rồi một thành phần khác giải mã lại, dữ liệu có thể biến thành newline ngoài dự kiến.

Nên xác định rõ ranh giới:

- Văn bản nguồn DSL.
- Giá trị literal sau khi parser giải mã.
- Dữ liệu miền.
- Đầu ra được encode cho ngữ cảnh đích.

Mỗi giai đoạn chỉ thực hiện chuyển đổi mà nó sở hữu.

### 11.5. Giới hạn độ dài và độ phức tạp

Chuỗi rất dài hoặc escape Unicode lồng ghép bất thường có thể gây tiêu tốn bộ nhớ và thời gian. Parser nên giới hạn kích thước literal, số chữ số escape và độ sâu xử lý theo nhu cầu thực tế.

## 12. Kiểm thử ký tự thoát

Một bộ kiểm thử cần bao gồm cả trường hợp hợp lệ, không hợp lệ và các ranh giới.

### 12.1. Kiểm thử escape hợp lệ

| Đầu vào DSL | Giá trị mong đợi |
|---|---|
| "A\\nB" | A, newline, B |
| "A\\tB" | A, tab, B |
| "Say \\"Hi\\"" | Say "Hi" |
| "C:\\\\data" | C:\data |
| "\\u0041" | A, nếu DSL hỗ trợ Unicode escape |

### 12.2. Kiểm thử lỗi

Kiểm tra:

- Dấu thoát nằm cuối literal.
- Escape sequence không được hỗ trợ.
- Thiếu chữ số trong Unicode escape.
- Chữ số Unicode không phải hệ thập lục phân.
- Code point nằm ngoài phạm vi hợp lệ.
- Literal chưa có dấu nháy đóng.
- Ký tự điều khiển không được phép xuất hiện trực tiếp.

### 12.3. Kiểm thử round-trip

Nếu DSL có serializer, cần kiểm tra rằng giá trị được serialize thành literal rồi parse lại vẫn giữ nguyên giá trị.

~~~text
value -> encodeLiteral(value) -> parseLiteral(source) -> decodedValue
~~~

Điều kiện mong đợi:

~~~text
decodedValue == value
~~~

Round-trip đặc biệt hữu ích với dấu nháy, dấu gạch chéo, newline, tab, Unicode và chuỗi rỗng.

### 12.4. Kiểm thử nhiều lớp

Với literal chứa regex hoặc JSON, cần kiểm tra cả hai bước:

1. Parser DSL tạo đúng chuỗi sau giải mã.
2. Parser của ngôn ngữ bên trong hiểu chuỗi đó đúng.

Chỉ kiểm tra văn bản nguồn bằng mắt không đủ để xác nhận kết quả ở các lớp.

### 12.5. Kiểm thử khác biệt nền tảng

Kiểm thử trên các hệ điều hành và runtime được hỗ trợ, đặc biệt với đường dẫn, ký tự xuống dòng và Unicode. Một số môi trường dùng CRLF, một số dùng LF; dữ liệu DSL nên có quy tắc chuẩn hóa rõ ràng thay vì phụ thuộc ngầm vào nền tảng.

## 13. Những lỗi thường gặp khi dùng ký tự thoát

### 13.1. Quên thoát dấu nháy bên trong chuỗi

Chuỗi kết thúc sớm khiến phần còn lại bị parser hiểu thành token khác và tạo lỗi cú pháp khó đọc.

### 13.2. Quên thoát chính ký tự thoát

Một dấu gạch chéo ngược trong đường dẫn có thể bị hiểu là mở đầu escape sequence. Người viết cần nhân đôi dấu gạch chéo hoặc dùng raw string nếu có.

### 13.3. Thoát quá nhiều

Khi dữ liệu đi qua nhiều lớp, người dùng có thể thêm nhiều dấu gạch chéo hơn cần thiết. Kết quả cuối cùng có thể chứa dấu gạch chéo thừa hoặc không còn đúng với regex hay JSON mong muốn.

### 13.4. Dùng quy tắc escape của ngôn ngữ này cho ngôn ngữ khác

Escape trong Java, DSL, JSON, regex và SQL không giống nhau hoàn toàn. Cần xác định chuỗi đang ở lớp nào trước khi quyết định cách viết.

### 13.5. Chấp nhận escape không hợp lệ một cách âm thầm

Tự bỏ dấu gạch chéo hoặc thay mã không biết bằng ký tự khác có thể làm dữ liệu sai mà không có cảnh báo. Với DSL cần tính xác định, nên báo lỗi rõ ràng.

### 13.6. Nhầm escape với mã hóa

UTF-8 là encoding, còn \u0041 là cách viết escape trong một số literal. Một bên chuyển văn bản thành byte; bên kia biểu diễn ký tự trong cú pháp.

### 13.7. Không phân biệt raw string và string thường

Nếu raw string vẫn được giải mã một phần, tên gọi và hành vi sẽ gây nhầm lẫn. Quy tắc phải được định nghĩa chính xác và kiểm thử.

## 14. Quy trình thiết kế ký tự thoát cho DSL

Có thể thực hiện theo các bước sau:

1. **Xác định dữ liệu cần biểu diễn:** chuỗi thường, đường dẫn, regex, văn bản nhiều dòng hay dữ liệu lồng nhau.
2. **Chọn dấu phân cách:** nháy đơn, nháy kép, delimiter nhiều ký tự hoặc raw string.
3. **Chọn ký tự thoát:** quyết định có dùng dấu gạch chéo ngược hay một quy tắc khác.
4. **Lập danh sách escape sequence:** mô tả từng mã, giá trị kết quả và ngữ cảnh.
5. **Quy định escape không hợp lệ:** báo lỗi, giữ nguyên hay hỗ trợ tương thích cũ.
6. **Định nghĩa Unicode:** quy tắc code point, độ dài, ký tự không hợp lệ và chuẩn hóa.
7. **Xác định thời điểm giải mã:** tránh giải mã thiếu hoặc giải mã kép.
8. **Giữ vị trí nguồn:** giúp thông báo lỗi trỏ đúng dấu hoặc mã thoát.
9. **Tách các lớp ngôn ngữ:** không dùng một bộ escape cho DSL, regex, SQL và HTML.
10. **Kiểm thử round-trip và trường hợp biên:** xác nhận serialize rồi parse giữ nguyên dữ liệu.

Tài liệu nên có ví dụ cho từng escape sequence và giải thích rõ giá trị sau khi giải mã. Một bảng tham chiếu ngắn thường hữu ích hơn một mô tả chung chung.

## 15. Ví dụ tổng hợp: DSL cấu hình thông báo

Giả sử một DSL cho phép khai báo mẫu thông báo:

~~~text
template OrderNotice {
    subject = "Order \"{order.id}\" confirmed"
    body = """
        Hello {customer.name},
        Your order is ready.
        Contact: support@example.com
    """
}
~~~

Trong ví dụ này có nhiều cơ chế cần phân biệt:

- Dấu nháy kép bên trong subject được thoát để không kết thúc chuỗi.
- Literal nhiều dòng giữ các ký tự xuống dòng.
- Các phần trong ngoặc nhọn là cú pháp nội suy biến theo giả định của DSL.
- Địa chỉ email là dữ liệu văn bản thông thường.

Nếu muốn hiển thị nguyên văn chuỗi **{customer.name}** thay vì nội suy biến, DSL cần một quy tắc escape riêng cho dấu mở nội suy hoặc một dạng raw string. Ví dụ minh họa:

~~~text
body = "Literal text: \\{customer.name\\}"
~~~

Đây chỉ là một lựa chọn thiết kế. DSL khác có thể dùng dấu nháy đơn, dấu phân cách hoặc cú pháp raw block. Điều quan trọng là người dùng biết khi nào nội suy xảy ra và cách biểu diễn dấu phân cách nội suy như dữ liệu.

## 16. Câu hỏi tự đánh giá

1. Phân biệt ký tự thoát và chuỗi thoát.
2. Vì sao dấu nháy bên trong string literal cần một quy tắc đặc biệt?
3. Giải mã \\\\ và \\n tạo ra những giá trị nào?
4. Raw string khác string thông thường như thế nào?
5. Vì sao một dấu gạch chéo ngược ở cuối literal có thể gây lỗi?
6. Escape Unicode khác encoding UTF-8 ở điểm nào?
7. Vì sao chuỗi chứa regex thường cần chú ý đến nhiều lớp escape?
8. Tại sao escape theo quy tắc DSL không đủ để chống SQL injection?
9. Giải mã kép có thể làm thay đổi dữ liệu như thế nào?
10. Một bộ kiểm thử escape cần bao gồm những trường hợp hợp lệ và không hợp lệ nào?

## Kết luận

Ký tự thoát giúp DSL phân biệt ký tự có ý nghĩa cú pháp với ký tự thuộc dữ liệu. Chuỗi thoát có thể biểu diễn dấu nháy, chính ký tự thoát, ký tự điều khiển hoặc code point Unicode. Thiết kế cần xác định dấu phân cách, tập escape được hỗ trợ, cách xử lý mã không hợp lệ, raw string, Unicode và thời điểm giải mã.

Khi DSL chứa một ngôn ngữ khác, mỗi lớp phải được xử lý theo quy tắc riêng. Escape không thay thế encoding, validation hay các API an toàn như truy vấn tham số hóa. Một parser có chính sách rõ ràng, diagnostic chính xác và kiểm thử round-trip sẽ giúp dữ liệu được giữ nguyên ý nghĩa từ văn bản nguồn đến giá trị cuối cùng.
