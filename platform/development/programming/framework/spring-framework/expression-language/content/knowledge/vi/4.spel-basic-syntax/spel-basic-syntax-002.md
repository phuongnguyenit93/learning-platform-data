# Chuỗi ký tự trong SpEL: dấu nháy đơn và dấu nháy kép

## 1. String literal là gì?

Trong Spring Expression Language (SpEL), string literal là một giá trị chuỗi được viết trực tiếp trong biểu thức. Khi parser gặp string literal, nó tạo ra một giá trị kiểu `java.lang.String` để biểu thức có thể trả về, nối chuỗi, so sánh hoặc gọi method.

Ví dụ đơn giản:

~~~java
ExpressionParser parser = new SpelExpressionParser();

Expression expression = parser.parseExpression("'Hello, SpEL!'");
String message = expression.getValue(String.class);

System.out.println(message); // Hello, SpEL!
~~~

Chuỗi truyền vào `parseExpression` ở ví dụ trên là `'Hello, SpEL!'`. Dấu nháy đơn ở hai đầu là cú pháp của SpEL; kết quả nhận được chỉ là phần nội dung `Hello, SpEL!`, không bao gồm hai dấu nháy.

SpEL cho phép dùng cả dấu nháy đơn (`'`) và dấu nháy kép (`"`) để bao quanh string literal. Hai cách viết dưới đây đều biểu diễn một chuỗi:

~~~java
String fromSingleQuotes =
        parser.parseExpression("'Spring Framework'").getValue(String.class);

String fromDoubleQuotes =
        parser.parseExpression("\"Spring Framework\"").getValue(String.class);
~~~

Cả hai biến đều nhận giá trị `Spring Framework`. Hãy chọn một kiểu dấu nháy nhất quán trong một biểu thức để người đọc dễ phân biệt phần bắt đầu và kết thúc của literal.

## 2. Phân biệt dấu nháy của Java và dấu nháy của SpEL

Khi gọi parser từ Java, ta đang làm việc với hai lớp cú pháp:

1. Java dùng dấu nháy kép để tạo một đối tượng `String` trong mã nguồn Java.
2. SpEL đọc nội dung của đối tượng `String` đó và dùng dấu nháy đơn hoặc kép để nhận diện string literal của biểu thức.

Ví dụ:

~~~java
String spelSource = "'Hello'";
Expression expression = parser.parseExpression(spelSource);
String value = expression.getValue(String.class);
~~~

Trong mã nguồn Java, `"'Hello'"` là một Java string. Giá trị runtime của nó chứa các ký tự `'Hello'`, và parser SpEL hiểu phần đó là string literal.

Nếu muốn SpEL dùng dấu nháy kép, phải biểu diễn dấu nháy kép bên trong Java string bằng escape của Java:

~~~java
String spelSource = "\"Hello\"";
Expression expression = parser.parseExpression(spelSource);
String value = expression.getValue(String.class);
~~~

Java xử lý `\"` trước khi gọi parser. Vì vậy, nội dung thực tế mà SpEL nhận được là `"Hello"`. Dấu nháy kép ở đây thuộc cú pháp SpEL, còn cặp dấu nháy kép ngoài cùng trong mã nguồn là cú pháp Java.

Quy tắc quan trọng: hãy phân biệt chuỗi Java mà chương trình truyền đi với chuỗi biểu thức SpEL mà parser nhận được. Khi gặp lỗi parse, in hoặc debug giá trị runtime của biến expression source để xem parser thực sự nhận chuỗi nào.

## 3. Khi nào chọn dấu nháy đơn, khi nào chọn dấu nháy kép?

Hai kiểu delimiter đều có thể tạo string literal. Lợi ích thực tế của việc chọn kiểu này hay kiểu kia thường nằm ở nội dung chuỗi: dùng delimiter khác với dấu nháy cần xuất hiện trong nội dung sẽ giảm nhu cầu escape.

Ví dụ, nội dung có dấu nháy kép có thể đặt trong literal nháy đơn:

~~~java
String spelSource = "'She said \"Hello\"'";
String value = parser.parseExpression(spelSource).getValue(String.class);

System.out.println(value); // She said "Hello"
~~~

Ngược lại, nội dung có dấu nháy đơn có thể đặt trong literal nháy kép:

~~~java
String spelSource = "\"It's Spring\"";
String value = parser.parseExpression(spelSource).getValue(String.class);

System.out.println(value); // It's Spring
~~~

Ở ví dụ thứ nhất, dấu nháy đơn đánh dấu đầu/cuối literal SpEL; dấu nháy kép bên trong là nội dung. Ở ví dụ thứ hai, dấu nháy kép đánh dấu literal SpEL; dấu nháy đơn trong từ `It's` là nội dung bình thường.

Cách chọn này đặc biệt hữu ích khi biểu thức chứa tên, câu trích dẫn, thông báo hoặc nội dung có dấu nháy. Nếu chuỗi có cả hai loại dấu nháy, chọn delimiter ít xuất hiện hơn trong nội dung và escape delimiter trùng với delimiter bao ngoài theo cú pháp SpEL.

## 4. Escape dấu nháy khi nội dung có cùng loại delimiter

Nếu nội dung cần chứa chính dấu nháy đang được dùng để bao quanh literal, cần escape dấu nháy theo quy tắc của SpEL. SpEL cho phép viết lặp delimiter tương ứng để biểu diễn dấu nháy nằm bên trong chuỗi.

Ví dụ với literal dùng dấu nháy đơn:

~~~java
String spelSource = "'It''s Spring'";
String value = parser.parseExpression(spelSource).getValue(String.class);

System.out.println(value); // It's Spring
~~~

Hai dấu nháy đơn ở giữa biểu thức biểu diễn một dấu nháy đơn thuộc nội dung. Dấu nháy đầu tiên và cuối cùng vẫn là delimiter mở/đóng literal.

Tương tự, với literal dùng dấu nháy kép, có thể lặp dấu nháy kép bên trong:

~~~java
String spelSource = "\"She said \"\"Hello\"\"\"";
String value = parser.parseExpression(spelSource).getValue(String.class);

System.out.println(value); // She said "Hello"
~~~

Trong ví dụ này có hai bước xử lý: Java xử lý các escape để tạo chuỗi expression source; sau đó SpEL nhận literal có delimiter kép và diễn giải cặp dấu nháy kép lặp bên trong thành một dấu nháy kép trong kết quả.

Khi biểu thức được tạo động, không nên tự nối chuỗi tùy tiện để xử lý dấu nháy. Hãy kiểm soát rõ delimiter, escape nội dung theo đúng cú pháp và ưu tiên truyền dữ liệu qua variables trong evaluation context nếu dữ liệu không phải một phần cố định của biểu thức.

## 5. Dùng string literal trong phép nối chuỗi

Toán tử `+` có thể nối các string literal với nhau:

~~~java
Expression expression =
        parser.parseExpression("'Hello' + ' ' + 'Spring'");

String result = expression.getValue(String.class);
System.out.println(result); // Hello Spring
~~~

String literal cũng có thể kết hợp với biến trong evaluation context:

~~~java
StandardEvaluationContext context = new StandardEvaluationContext();
context.setVariable("name", "Lan");

Expression expression =
        parser.parseExpression("'Hello, ' + #name + '!'");

String greeting = expression.getValue(context, String.class);
System.out.println(greeting); // Hello, Lan!
~~~

Trong biểu thức này:

- `'Hello, '` là string literal.
- `#name` là biến có tên `name` trong evaluation context.
- `'!'` là string literal chứa dấu chấm than.
- Toán tử `+` ghép các phần thành một chuỗi kết quả.

Nếu dữ liệu thay đổi theo request hoặc theo object, nên đưa dữ liệu vào context bằng variable thay vì ghép trực tiếp dữ liệu đó vào chuỗi expression source. Điều này giúp tái sử dụng biểu thức và tránh lỗi do dấu nháy hoặc ký tự đặc biệt trong dữ liệu đầu vào.

## 6. Dùng string literal để so sánh

String literal thường xuất hiện trong điều kiện so sánh:

~~~java
StandardEvaluationContext context = new StandardEvaluationContext();
context.setVariable("status", "PAID");

Expression expression =
        parser.parseExpression("#status == 'PAID'");

Boolean paid = expression.getValue(context, Boolean.class);
System.out.println(paid); // true
~~~

Có thể dùng dấu nháy kép cho cùng giá trị:

~~~java
Expression expression =
        parser.parseExpression("#status == \"PAID\"");
~~~

Toán tử so sánh `==` đánh giá hai giá trị. Với string, nội dung và kiểu giá trị có ý nghĩa; chữ hoa và chữ thường khác nhau, vì vậy `'PAID'` và `'paid'` không phải cùng một nội dung.

Có thể dùng literal trong biểu thức điều kiện phức hợp:

~~~java
Expression expression = parser.parseExpression(
        "#status == 'PAID' and #total > 0");
~~~

Dấu nháy giúp parser nhận biết `PAID` là chuỗi literal. Nếu viết `PAID` không có dấu nháy, SpEL sẽ hiểu đó là một tên property hoặc identifier cần được phân giải trong context, không phải chuỗi ký tự.

## 7. Gọi method trên string literal

Một string literal là một giá trị `String`, vì vậy biểu thức có thể gọi method phù hợp trên nó:

~~~java
Expression upperExpression =
        parser.parseExpression("'spring'.toUpperCase()");

String upper = upperExpression.getValue(String.class);
System.out.println(upper); // SPRING
~~~

Ví dụ khác:

~~~java
Expression lengthExpression =
        parser.parseExpression("'Spring'.length()");

Integer length = lengthExpression.getValue(Integer.class);
System.out.println(length); // 6
~~~

Có thể gọi method trên một biến string:

~~~java
StandardEvaluationContext context = new StandardEvaluationContext();
context.setVariable("framework", "Spring");

Expression expression =
        parser.parseExpression("#framework.toUpperCase()");

String result = expression.getValue(context, String.class);
System.out.println(result); // SPRING
~~~

Dấu nháy chỉ cần thiết khi biểu diễn nội dung chuỗi trực tiếp. Với biến, dùng cú pháp `#variableName`; với property của root object, dùng tên property theo đường dẫn phù hợp.

## 8. Chuỗi rỗng và null là hai giá trị khác nhau

Chuỗi rỗng là một string literal hợp lệ, được viết bằng hai dấu nháy liền nhau:

~~~java
String empty = parser.parseExpression("''").getValue(String.class);
System.out.println(empty.length()); // 0
~~~

Giá trị `null` được viết bằng từ khóa `null` và biểu diễn một tham chiếu không có đối tượng:

~~~java
Object nullValue = parser.parseExpression("null").getValue();
~~~

Không nên nhầm `''` với `null`:

- `''` là một đối tượng String có độ dài bằng 0.
- `null` không phải một String rỗng; nó biểu diễn giá trị không có tham chiếu.
- So sánh, gọi method hoặc chuyển đổi kiểu có thể cho kết quả khác nhau tùy hai trường hợp này.

Nếu cấu hình có thể thiếu hoặc người dùng có thể gửi nội dung rỗng, hãy quyết định rõ ứng dụng cần xử lý chuỗi rỗng, khoảng trắng hay null như thế nào.

## 9. String literal bên trong template expression

Trong template expression, dấu `#{...}` đánh dấu đoạn SpEL cần đánh giá. Bên trong cặp dấu này, string literal vẫn dùng quy tắc dấu nháy đơn hoặc dấu nháy kép như biểu thức SpEL thông thường.

~~~java
ExpressionParser parser = new SpelExpressionParser();
ParserContext templateContext = new TemplateParserContext();

Expression expression = parser.parseExpression(
        "Message: #{'Hello, ' + #name + '!'}",
        templateContext);

StandardEvaluationContext context = new StandardEvaluationContext();
context.setVariable("name", "Lan");

String message = expression.getValue(context, String.class);
System.out.println(message); // Message: Hello, Lan!
~~~

Cần phân biệt ba loại dấu trong ví dụ:

- Dấu nháy kép trong mã Java bao quanh chuỗi nguồn.
- `#{` và `}` xác định phần biểu thức của template.
- Dấu nháy đơn bên trong `#{...}` bao quanh các string literal của SpEL.

Nếu không truyền `TemplateParserContext`, parser mặc định sẽ cố hiểu toàn bộ chuỗi `Message: ...` như một biểu thức SpEL duy nhất. Khi đó văn bản cố định bên ngoài không được tự động giữ lại như nội dung template.

## 10. Lỗi thường gặp khi viết chuỗi

**Quên delimiter của SpEL**

~~~java
// PAID được hiểu như identifier/property, không phải string literal.
Expression expression = parser.parseExpression("status == PAID");
~~~

Nếu muốn so sánh với chuỗi, hãy viết literal có dấu nháy:

~~~java
Expression expression = parser.parseExpression("status == 'PAID'");
~~~

**Nhầm dấu nháy của Java với dấu nháy của SpEL**

~~~java
// Đây là Java String chứa expression source: 'Hello'
String spelSource = "'Hello'";
~~~

Dấu nháy kép ngoài cùng thuộc Java; dấu nháy đơn bên trong thuộc SpEL. Nếu muốn expression SpEL dùng dấu nháy kép, phải escape chúng trong mã nguồn Java.

**Escape ở sai tầng**

Một dấu gạch chéo ngược có thể được xử lý bởi Java trước khi SpEL nhìn thấy chuỗi. Khi debug, hãy kiểm tra giá trị runtime của expression source thay vì chỉ nhìn cách viết trong file Java.

**Tạo expression bằng cách nối dữ liệu người dùng**

Nếu dữ liệu động chứa dấu nháy, phép nối chuỗi thủ công có thể làm thay đổi cú pháp expression hoặc tạo ra một biểu thức ngoài dự kiến. Hãy truyền dữ liệu bằng `EvaluationContext.setVariable(...)` và tham chiếu bằng `#variableName`.

**Nhầm chuỗi rỗng với null**

`''` và `null` có ngữ nghĩa khác nhau. Hãy kiểm tra rõ điều kiện null và độ dài chuỗi nếu logic phụ thuộc vào dữ liệu rỗng.

## 11. Ví dụ tổng hợp

Ví dụ sau kết hợp string literal, dấu nháy kép bên trong nội dung, biến context, nối chuỗi và gọi method:

~~~java
ExpressionParser parser = new SpelExpressionParser();

StandardEvaluationContext context = new StandardEvaluationContext();
context.setVariable("name", "Lan");
context.setVariable("framework", "Spring");

Expression expression = parser.parseExpression(
        "'She said \"Hello\", ' + #name + ' is learning ' "
                + "+ #framework.toUpperCase()");

String message = expression.getValue(context, String.class);

System.out.println(message);
// She said "Hello", Lan is learning SPRING
~~~

Ở đây các literal được bao bởi dấu nháy đơn. Dấu nháy kép quanh từ `Hello` là nội dung chuỗi; trong mã nguồn Java, chúng được escape để tồn tại trong Java string. Biến `#name` và `#framework` được lấy từ context, còn `toUpperCase()` được gọi trên giá trị của biến `framework`.

## 12. Ghi nhớ

- SpEL hỗ trợ string literal được bao bởi dấu nháy đơn hoặc dấu nháy kép.
- Dấu nháy ngoài cùng là delimiter và không xuất hiện trong giá trị chuỗi trả về.
- Khi gọi parser từ Java, dấu nháy của Java và dấu nháy của SpEL thuộc hai tầng cú pháp khác nhau.
- Dùng delimiter đối lập khi nội dung có chứa dấu nháy; escape delimiter trùng với delimiter bao ngoài theo quy tắc SpEL.
- Có thể nối literal bằng `+`, so sánh literal, gọi method trên string và dùng literal trong template expression.
- Dùng variables trong `EvaluationContext` cho dữ liệu động thay vì tự ghép dữ liệu vào expression source.
- Chuỗi rỗng `''` khác với `null`.
