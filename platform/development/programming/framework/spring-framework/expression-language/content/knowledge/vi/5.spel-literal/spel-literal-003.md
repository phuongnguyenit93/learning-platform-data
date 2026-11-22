# Literal chuỗi và ký tự đặc biệt trong SpEL

## Mục tiêu

String literal là một giá trị văn bản được viết trực tiếp trong biểu thức SpEL. Nó thường xuất hiện khi so sánh property, nối chuỗi, truyền tham số cho method hoặc tạo nội dung hiển thị. Để đọc và viết literal chính xác, cần phân biệt dấu nháy của SpEL với dấu nháy của ngôn ngữ bao quanh biểu thức (thường là Java), đồng thời hiểu cách SpEL xử lý dấu nháy, khoảng trắng, dấu gạch chéo ngược và ký tự Unicode.

## 1. Cú pháp cơ bản

Trong SpEL hiện đại, string literal có thể được bao quanh bởi dấu nháy đơn (`'`) hoặc dấu nháy kép (`"`). Phần nằm giữa hai dấu phân cách được tạo thành một giá trị `java.lang.String`.

| Biểu thức SpEL | Giá trị nhận được |
| --- | --- |
| `'Hello World'` | `Hello World` |
| `"Hello World"` | `Hello World` |
| `'123'` | Chuỗi `123`, không phải số nguyên. |
| `'true'` | Chuỗi `true`, không phải boolean. |
| `'null'` | Chuỗi `null`, không phải giá trị null. |
| `'A'` | Chuỗi có một ký tự `A`, không phải Java `char`. |

Ví dụ parse và lấy kết quả:

```java
ExpressionParser parser = new SpelExpressionParser();

String greeting = parser.parseExpression("'Hello World'")
        .getValue(String.class);

String numberText = parser.parseExpression("'123'")
        .getValue(String.class);
```

Kết quả của `getValue(String.class)` là một `String`. Nếu viết `123` không có dấu nháy, SpEL hiểu đó là numeric literal; nếu viết `true` hoặc `null` không có dấu nháy, chúng lần lượt là boolean literal và null literal.

Các tài liệu của những phiên bản Spring cũ có thể chỉ minh họa dấu nháy đơn. Nếu ứng dụng phải chạy trên phiên bản cũ, hãy kiểm tra cú pháp mà parser của phiên bản đó hỗ trợ; dấu nháy đơn là lựa chọn tương thích rộng nhất.

## 2. Đưa dấu nháy vào nội dung chuỗi

Quy tắc quan trọng là lặp đôi chính dấu nháy đang dùng làm dấu phân cách của literal. Không dùng quy tắc backslash của Java hoặc C để thay thế quy tắc này.

| Biểu thức SpEL | Kết quả | Giải thích |
| --- | --- | --- |
| `'Tony''s Pizza'` | `Tony's Pizza` | Dấu nháy đơn bên trong literal đơn được viết thành hai dấu nháy đơn liền nhau. |
| `"He said ""hello"""` | `He said "hello"` | Dấu nháy kép bên trong literal kép được viết thành hai dấu nháy kép liền nhau. |
| `"It's ready"` | `It's ready` | Dấu nháy đơn không phải delimiter của literal kép nên có thể viết trực tiếp. |
| `'He said "go"'` | `He said "go"` | Dấu nháy kép không phải delimiter của literal đơn nên có thể viết trực tiếp. |

Ví dụ thường gặp nhất là tên hoặc nội dung có dấu nháy đơn:

```java
ExpressionParser parser = new SpelExpressionParser();

String spelSource = "'Tony''s Pizza'";
String name = parser.parseExpression(spelSource).getValue(String.class);
// name = "Tony's Pizza"
```

Khi cần chứa cả hai loại dấu nháy, hãy chọn loại ít xuất hiện hơn làm delimiter. Ví dụ, chuỗi có nhiều dấu nháy kép có thể được bao bằng dấu nháy đơn: `'He said "go now"'`.

Không nên viết `\'Tony\\\'s Pizza\'` với hy vọng `\\\'` sẽ escape dấu nháy theo kiểu Java/C. Cách đúng trong SpEL là `'Tony''s Pizza'`.

## 3. Khoảng trắng và dấu câu

Khoảng trắng bên trong string literal là dữ liệu và được giữ nguyên, bao gồm khoảng trắng đầu/cuối, nhiều dấu cách liên tiếp và dấu tab thực sự. Ngược lại, khoảng trắng giữa các token ở ngoài literal thường chỉ dùng để định dạng biểu thức và bị parser bỏ qua.

```spel
'  Spring   Expression Language  '
```

Giá trị trên giữ hai khoảng trắng đầu, ba khoảng trắng giữa `Spring` và `Expression`, cùng hai khoảng trắng cuối.

Các ký tự như dấu chấm, dấu phẩy, dấu hai chấm, ngoặc, dấu cộng, dấu so sánh, `#`, `@`, `{` và `}` đều là nội dung văn bản khi chúng nằm trong literal đã được đóng dấu nháy đúng cách:

```spel
'A + B = C; price >= 100; #name; {key:value}'
```

Biểu thức trên trả về một chuỗi. Những ký tự đó chỉ được xem là toán tử hoặc cú pháp SpEL khi xuất hiện ở vị trí cú pháp bên ngoài literal. Ví dụ, `1 + 2` thực hiện phép cộng, còn `'1 + 2'` chỉ là văn bản `1 + 2`.

## 4. Dấu gạch chéo ngược và escape sequence

Không nên mặc định SpEL xử lý `\n`, `\t`, `\r` hay `\uXXXX` giống Java. Trong string literal SpEL, backslash không phải cơ chế escape tổng quát; các chuỗi như `\n` được giữ như ký tự backslash và chữ `n`. Cơ chế escape của Java source hoặc JSON/XML/configuration có thể đã xử lý chuỗi trước khi SpEL nhận nó.

Ví dụ dưới đây tạo một đường dẫn có backslash thật. Java xử lý mỗi cặp `\\` thành một ký tự backslash trước khi đưa biểu thức cho SpEL:

```java
ExpressionParser parser = new SpelExpressionParser();
String pathExpression = "'C:\\temp\\file.txt'";
String path = parser.parseExpression(pathExpression).getValue(String.class);
// path = C:\temp\file.txt
```

Nếu cần ký tự xuống dòng hoặc tab thật, hãy tạo chúng trong Java rồi truyền vào evaluation context như dữ liệu:

```java
ExpressionParser parser = new SpelExpressionParser();
StandardEvaluationContext context = new StandardEvaluationContext();
context.setVariable("newline", System.lineSeparator());
context.setVariable("tab", "\t");

Expression expression = parser.parseExpression(
        "'Line 1' + #newline + 'Name:' + #tab + 'Lan'");
String result = expression.getValue(context, String.class);
```

`result` chứa một dòng mới giữa `Line 1` và `Name:`, sau đó là một tab trước `Lan`. Cách truyền qua biến cũng hữu ích khi giá trị điều khiển bởi hệ điều hành hoặc cấu hình ứng dụng.

## 5. Ký tự Unicode và tiếng Việt

SpEL xử lý nội dung literal dưới dạng Java `String`, nên có thể chứa tiếng Việt có dấu, ký tự từ các bảng chữ cái khác, ký hiệu tiền tệ và emoji:

```spel
'Xin chào, thế giới — Spring 🌱'
```

Không cần thêm dấu escape SpEL cho các ký tự Unicode thông thường. Hãy bảo đảm file nguồn, file cấu hình, request hoặc hệ thống lưu trữ dùng encoding phù hợp (thường là UTF-8) để dữ liệu không bị biến thành ký tự lỗi trước khi parser nhận được.

Về mặt kỹ thuật, Java `String` lưu chuỗi theo UTF-16. Vì vậy, khi cắt chuỗi hoặc giới hạn độ dài ở tầng ứng dụng, cần tránh cắt giữa một cặp surrogate của ký tự nằm ngoài Basic Multilingual Plane, chẳng hạn một số emoji.

## 6. Dùng string literal trong biểu thức lớn hơn

String literal có thể là một phần của phép so sánh, phép nối chuỗi, lời gọi method, danh sách hoặc map inline.

```java
ExpressionParser parser = new SpelExpressionParser();

// So sánh một property với literal
boolean isLan = parser.parseExpression("name == 'Lan'")
        .getValue(customer, Boolean.class);

// Nối các literal và giá trị động
String message = parser.parseExpression("'Hello, ' + name + '!'")
        .getValue(customer, String.class);

// Gọi method trên một string literal
String upper = parser.parseExpression("'spring spel'.toUpperCase()")
        .getValue(String.class);
```

Kết quả tương ứng là so sánh tên khách hàng, tạo lời chào theo property `name`, và chuyển chuỗi `spring spel` thành chữ hoa. String literal cũng có thể làm phần tử trong inline list hoặc giá trị của inline map, ví dụ `{'red', 'green'}` và `{'name': 'Lan'}`.

## 7. Phân biệt dấu nháy của Java và dấu nháy của SpEL

Khi viết SpEL trong Java source, có ít nhất hai lớp cú pháp:

1. Java tạo ra một đối tượng `String` từ string literal trong source code.
2. SpEL parse nội dung `String` đó theo cú pháp biểu thức riêng.

Ví dụ:

```java
String spelSource = "'Tony''s Pizza'";
```

Java dùng dấu nháy kép bên ngoài để tạo `spelSource`. Sau khi Java biên dịch, giá trị của biến là chuỗi SpEL `'Tony''s Pizza'`; sau đó SpEL mới diễn giải cặp dấu nháy đơn liền nhau thành một dấu nháy đơn trong kết quả.

Khi nội dung SpEL được đặt trong annotation, XML, JSON, file properties, shell command hoặc một DSL khác, lớp bao quanh có thể có quy tắc escape riêng. Hãy kiểm tra chuỗi thực tế được truyền tới `parseExpression`, thay vì suy luận chỉ từ cách viết ở lớp ngoài.

## 8. Lỗi thường gặp

| Hiện tượng | Nguyên nhân | Cách xử lý |
| --- | --- | --- |
| `ParseException` báo string chưa kết thúc | Thiếu dấu nháy đóng hoặc dấu nháy bên trong chưa được lặp đôi đúng cách. | Kiểm tra delimiter mở/đóng và dùng `''` hoặc `""` để biểu diễn delimiter tương ứng bên trong literal. |
| Kết quả còn dấu backslash và chữ `n` | SpEL giữ `\n` như hai ký tự thông thường thay vì chuyển thành newline. | Tạo ký tự xuống dòng thật ở Java và truyền qua biến context. |
| Java báo lỗi compile trước khi SpEL chạy | Chuỗi Java bên ngoài chưa escape đúng dấu nháy kép hoặc backslash. | Kiểm tra riêng chuỗi Java được tạo ra và chuỗi SpEL mà parser nhận. |
| `true`, `null` hoặc số bị xử lý sai kiểu | Giá trị được đặt trong dấu nháy nên trở thành String. | Bỏ dấu nháy nếu mục tiêu là boolean, null hoặc numeric literal. |
| Khoảng trắng bị mất | Khoảng trắng được đặt ngoài string literal hoặc bị trim ở tầng ứng dụng trước khi parse. | Đặt khoảng trắng cần giữ bên trong dấu nháy và kiểm tra dữ liệu trước parser. |
| Dữ liệu chứa dấu nháy làm hỏng biểu thức | Dữ liệu người dùng được nối trực tiếp vào source SpEL. | Đưa dữ liệu vào `EvaluationContext` bằng biến thay vì ghép chuỗi biểu thức. |

## 9. Truyền dữ liệu an toàn thay vì ghép chuỗi

Không nên nối trực tiếp input bên ngoài vào source SpEL. Một dấu nháy trong input có thể làm biểu thức sai cú pháp; dữ liệu được ghép không đúng cách còn có thể làm thay đổi cấu trúc biểu thức.

Ví dụ truyền dữ liệu qua biến:

```java
ExpressionParser parser = new SpelExpressionParser();
StandardEvaluationContext context = new StandardEvaluationContext(customer);
context.setVariable("keyword", userInput);

Expression expression = parser.parseExpression("name == #keyword");
Boolean matched = expression.getValue(context, Boolean.class);
```

Trong ví dụ này, `userInput` được truyền như một giá trị `String`; dấu nháy hoặc ký tự toán tử bên trong dữ liệu không trở thành cú pháp SpEL. Đồng thời, chỉ cấp cho context các object và khả năng truy cập mà biểu thức thực sự cần.

## Ghi nhớ

- Dùng dấu nháy đơn hoặc dấu nháy kép để tạo String literal theo phiên bản Spring đang dùng; dấu nháy đơn có độ tương thích rộng.
- Muốn chứa chính delimiter bên trong literal, lặp đôi delimiter đó: `'Tony''s'` hoặc `"say ""hello"""`.
- Dấu nháy loại còn lại có thể xuất hiện trực tiếp bên trong literal.
- Khoảng trắng, dấu câu và ký tự Unicode bên trong literal là dữ liệu và được giữ nguyên.
- Không coi `\n` hay `\t` là escape sequence của SpEL; truyền ký tự điều khiển thật qua biến nếu cần.
- Phân biệt escape của Java/JSON/XML với cú pháp của SpEL; parser chỉ nhận chuỗi sau khi lớp ngoài đã xử lý xong.
- Với dữ liệu bên ngoài, dùng biến trong `EvaluationContext` thay vì nối dữ liệu vào source biểu thức.

## Tài liệu tham khảo

- [Spring Framework Reference — Literal Expressions](https://docs.spring.io/spring-framework/reference/core/expressions/language-ref/literal.html)
- [Spring Framework Reference — Evaluation](https://docs.spring.io/spring-framework/reference/core/expressions/evaluation.html)
- [Spring Framework source — SpEL Tokenizer](https://github.com/spring-projects/spring-framework/blob/main/spring-expression/src/main/java/org/springframework/expression/spel/standard/Tokenizer.java)