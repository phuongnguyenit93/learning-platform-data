# Escape delimiter và văn bản chứa ký hiệu đặc biệt

## Mục tiêu

Spring Expression Language (SpEL) hỗ trợ **template expression**: một chuỗi có thể trộn văn bản tĩnh với một hoặc nhiều khối biểu thức được đánh giá khi chạy. Mặc định, khối biểu thức bắt đầu bằng **#{** và kết thúc bằng **}**. Cú pháp này tiện cho việc tạo thông báo, nhãn, nội dung cấu hình hoặc chuỗi có dữ liệu động.

Khó khăn xuất hiện khi phần văn bản cần hiển thị cũng chứa các ký hiệu giống delimiter, chẳng hạn chuỗi tài liệu có ví dụ **#{name}**, JSON có dấu ngoặc nhọn hoặc văn bản có nhiều ký tự đặc biệt. Cần phân biệt delimiter của template với ký tự bên trong một SpEL expression và với escape của ngôn ngữ Java khi tạo chuỗi.

Sau bài này, bạn có thể:

- Phân tích một template bằng TemplateParserContext.
- Trộn văn bản tĩnh với nhiều expression block.
- Dùng delimiter mặc định hoặc cấu hình delimiter riêng.
- Giữ nguyên chuỗi giống delimiter trong kết quả template.
- Hiểu vai trò của string literal và dấu ngoặc khi parser tìm điểm kết thúc.
- Phân biệt escaping của Java string với việc nhận diện delimiter của template.
- Chẩn đoán lỗi thiếu delimiter, expression rỗng và ngoặc không cân bằng.

## 1. Template expression là gì?

Một template expression là chuỗi gồm các đoạn văn bản tĩnh xen kẽ với những khối SpEL được đánh dấu bằng prefix và suffix. Parser đánh giá từng khối rồi ghép kết quả với các đoạn văn bản tĩnh theo đúng thứ tự.

Với delimiter mặc định, ví dụ:

~~~text
Hello, #{#name}!
~~~

Nếu biến name có giá trị Lan, kết quả là:

~~~text
Hello, Lan!
~~~

Phần Hello, và dấu ! là văn bản tĩnh. Khối #{#name} là expression được đánh giá.

Template khác với một SpEL expression thông thường. Khi gọi parseExpression(expressionString) mà không truyền ParserContext, parser xử lý toàn bộ chuỗi như một expression. Khi muốn trộn văn bản tĩnh với expression block, cần truyền ParserContext có isTemplate() trả về true.

## 2. Delimiter mặc định và TemplateParserContext

TemplateParserContext là implementation ParserContext dùng cho template parsing. Constructor mặc định sử dụng:

- Prefix: **#{**
- Suffix: **}**

Ví dụ Java:

~~~java
ExpressionParser parser = new SpelExpressionParser();

StandardEvaluationContext context = new StandardEvaluationContext();
context.setVariable("name", "Lan");

Expression expression = parser.parseExpression(
    "Hello, #{#name}!",
    new TemplateParserContext()
);

String result = expression.getValue(context, String.class);
~~~

Kết quả là Hello, Lan!.

Có thể dùng ParserContext.TEMPLATE_EXPRESSION thay cho một TemplateParserContext mặc định:

~~~java
Expression expression = parser.parseExpression(
    "Hello, #{#name}!",
    ParserContext.TEMPLATE_EXPRESSION
);
~~~

Hai cách đều yêu cầu parser xử lý chuỗi theo chế độ template với prefix và suffix mặc định.

Nếu ứng dụng dùng cùng một delimiter ở nhiều nơi, hãy thống nhất cách tạo ParserContext để tránh một template được parse ở chế độ khác với nơi còn lại.

## 3. Trộn nhiều đoạn văn bản và nhiều expression

Một template có thể chứa nhiều khối expression:

~~~text
Order #{#orderId} của #{#customerName} có tổng tiền #{#total}.
~~~

Với các biến tương ứng trong context, parser đánh giá từng khối rồi ghép các kết quả theo thứ tự ban đầu.

Ví dụ:

~~~java
StandardEvaluationContext context = new StandardEvaluationContext();
context.setVariable("orderId", "ORD-1024");
context.setVariable("customerName", "Lan");
context.setVariable("total", new BigDecimal("250.00"));

Expression expression = parser.parseExpression(
    "Order #{#orderId} của #{#customerName} có tổng tiền #{#total}.",
    new TemplateParserContext()
);

String message = expression.getValue(context, String.class);
~~~

Template giúp giữ phần định dạng ở một chuỗi duy nhất, trong khi dữ liệu được truyền qua biến. Khi nội dung có nhiều đoạn động, cách này dễ đọc hơn việc nối chuỗi thủ công trong Java.

Kết quả của từng expression block được đưa vào chuỗi đầu ra. Vì vậy, hãy xác định kiểu dữ liệu trả về và cách biểu diễn của nó. Với tiền tệ, ngày tháng hoặc số cần format theo locale, nên định dạng giá trị rõ ràng trước hoặc dùng function chuyên biệt thay vì dựa vào biểu diễn mặc định của object.

## 4. Văn bản tĩnh và expression block

Parser nhận diện prefix ở phần văn bản template. Các đoạn nằm ngoài expression block được giữ như literal text. Các đoạn nằm trong delimiter được parse như SpEL expression.

Ví dụ:

~~~text
Status: #{#status}; retries: #{#retryCount}.
~~~

Nếu status là ACTIVE và retryCount là 3, kết quả có dạng:

~~~text
Status: ACTIVE; retries: 3.
~~~

Các ký tự như dấu chấm, dấu phẩy, dấu hai chấm, dấu gạch ngang hoặc dấu ngoặc vuông trong phần văn bản tĩnh thường không cần xử lý đặc biệt nếu chúng không tạo thành prefix của template.

Dấu suffix } ở phần văn bản tĩnh cũng không tự nó bắt đầu một expression block. Điều cần chú ý nhất với delimiter mặc định là prefix **#{**, vì parser dùng nó để tìm điểm bắt đầu của một khối biểu thức.

## 5. Giữ nguyên delimiter trong nội dung đầu ra

Nếu văn bản cần hiển thị có chứa chính prefix **#{**, parser mặc định sẽ hiểu nó là điểm bắt đầu của một expression block. Không nên giả định rằng thêm dấu gạch chéo ngược trước prefix sẽ luôn escape được delimiter; TemplateParserContext không định nghĩa một quy tắc escape backslash tổng quát cho prefix.

Có hai cách phổ biến để giữ chuỗi giống delimiter.

### Cách 1: Tạo chuỗi literal từ một expression block

Có thể dùng một expression block trả về chính chuỗi cần hiển thị:

~~~text
Cú pháp trong tài liệu: #{'#{name}'}
~~~

Kết quả đầu ra:

~~~text
Cú pháp trong tài liệu: #{name}
~~~

Parser nhận #{ ở đầu block ngoài. Bên trong, chuỗi '#{name}' là một string literal của SpEL, nên các ký tự trong chuỗi được giữ như dữ liệu. Dấu } cuối cùng đóng expression block bên ngoài.

Tương tự, để xuất ra chuỗi delimiter mở:

~~~text
#{'#{'}
~~~

Kết quả là:

~~~text
#{
~~~

Và để xuất một dấu ngoặc nhọn đóng:

~~~text
#{'}'}
~~~

Kết quả là:

~~~text
}
~~~

Cách này phù hợp khi chỉ có một vài vị trí cần hiển thị delimiter trong nội dung.

### Cách 2: Dùng delimiter tùy chỉnh

Nếu nội dung literal thường xuyên chứa **#{** hoặc cần giữ nhiều ví dụ SpEL nguyên dạng, hãy chọn một cặp delimiter khác cho template.

~~~java
ParserContext parserContext =
    new TemplateParserContext("[[", "]]");

Expression expression = parser.parseExpression(
    "Ví dụ SpEL: #{name}; tên thực tế: [[#name]]",
    parserContext
);
~~~

Với biến name bằng Lan, kết quả là:

~~~text
Ví dụ SpEL: #{name}; tên thực tế: Lan
~~~

Trong ví dụ này, **[[** bắt đầu expression block và **]]** kết thúc block. Chuỗi #{name} không còn là delimiter của template nên được giữ nguyên như văn bản tĩnh.

Delimiter tùy chỉnh cần được cấu hình nhất quán ở mọi nơi parse cùng loại template. Nếu template được lưu trong database hoặc file cấu hình, hãy lưu kèm quy ước delimiter hoặc xác định nó qua cấu hình ứng dụng.

## 6. Phân biệt escape của template với escape của Java string

Có hai giai đoạn khác nhau khi template được viết trong mã Java:

1. Compiler Java xử lý string literal hoặc text block để tạo ra một String.
2. SpEL parser đọc String đó và nhận diện delimiter template.

Ví dụ:

~~~java
String template = "Hello, #{#name}!";
~~~

Trong chuỗi Java này, ký tự #, { và } không cần escape theo cú pháp Java. Parser SpEL nhận chuỗi thực tế và xử lý #{ như prefix template.

Nếu nội dung có dấu gạch chéo ngược, dấu nháy kép hoặc ký tự điều khiển, cần tuân thủ quy tắc string literal của Java trước. Đối với Java text block, quy tắc escape cũng thuộc ngôn ngữ Java. Những escape này quyết định ký tự nào được gửi tới SpEL; chúng không tự tạo ra quy tắc escape delimiter mới cho TemplateParserContext.

Không nên viết một chuỗi có backslash rồi mặc định rằng SpEL sẽ bỏ backslash trước prefix. Hãy kiểm tra chuỗi Java thực tế được tạo ra và chọn một trong hai cách: biểu diễn delimiter như string literal trong expression, hoặc đổi sang delimiter template tùy chỉnh.

## 7. Dấu ngoặc và string literal bên trong expression block

Khi tìm suffix kết thúc expression block, parser phải phân biệt dấu ngoặc dùng để cấu trúc expression với ký tự nằm trong string literal.

Ví dụ:

~~~text
Thông báo: #{'Giá trị có dấu } ở bên trong chuỗi'}
~~~

Dấu } nằm trong string literal không đóng expression block. Dấu } sau dấu nháy mới là suffix kết thúc block.

Tương tự, expression có thể chứa các dấu ngoặc cân bằng:

~~~text
Kết quả: #{T(java.lang.Math).max(10, 20)}
~~~

Parser theo dõi cấu trúc dấu ngoặc tròn, vuông và nhọn để xác định suffix phù hợp. Dấu ngoặc trong string literal được xem là nội dung chuỗi, không phải cấu trúc expression.

Nếu dấu ngoặc không cân bằng hoặc string literal không được đóng, parser có thể báo lỗi trước khi expression được đánh giá. Hãy kiểm tra từng expression block riêng khi template có nhiều lớp dấu ngoặc hoặc chuỗi phức tạp.

## 8. Delimiter tùy chỉnh và ParserContext riêng

TemplateParserContext cho phép truyền prefix và suffix qua constructor:

~~~java
new TemplateParserContext("[[", "]]")
~~~

Có thể chọn delimiter phù hợp với định dạng dữ liệu của ứng dụng. Ví dụ, nếu văn bản chủ yếu chứa cú pháp SpEL #{...}, delimiter [[...]] có thể giảm nhầm lẫn.

Nếu cần logic parsing đặc biệt, ứng dụng có thể tự triển khai ParserContext. Interface này cung cấp ba thông tin:

- isTemplate(): cho biết parser có đang xử lý template hay không.
- getExpressionPrefix(): trả về prefix mở expression block.
- getExpressionSuffix(): trả về suffix đóng expression block.

ParserContext chỉ định cách parser nhận diện template. Nó không tự thay đổi ngữ nghĩa của SpEL expression nằm bên trong mỗi block.

Khi định nghĩa delimiter riêng, nên chọn cặp ký hiệu hiếm xuất hiện trong literal text, dễ nhận biết khi review và không xung đột với định dạng dữ liệu mà template cần chứa.

## 9. Lỗi thường gặp và cách chẩn đoán

| Triệu chứng | Nguyên nhân có thể | Hướng xử lý |
|---|---|---|
| Parser báo thiếu suffix | Có prefix mở nhưng không tìm được suffix tương ứng | Kiểm tra delimiter đóng và các dấu ngoặc bên trong block |
| Prefix trong văn bản bị parse nhầm | Literal text chứa đúng prefix của template | Dùng string literal expression hoặc delimiter tùy chỉnh |
| Expression block rỗng | Có prefix ngay sau đó là suffix, không có expression | Bỏ cặp delimiter rỗng hoặc cung cấp expression hợp lệ |
| Dấu } trong chuỗi làm parser khó đọc | String literal không đóng hoặc dấu ngoặc bị mất cân bằng | Kiểm tra dấu nháy và cấu trúc ngoặc |
| Template bị parse như expression thường | Không truyền ParserContext template vào parseExpression | Dùng TemplateParserContext hoặc ParserContext.TEMPLATE_EXPRESSION |
| Custom delimiter không hoạt động | Prefix/suffix lúc parse khác với delimiter lúc tạo template | Dùng cùng ParserContext configuration |
| Backslash không escape prefix như mong đợi | Nhầm escape Java với cơ chế nhận diện delimiter | Kiểm tra String thực tế và chọn cách biểu diễn literal phù hợp |
| Kết quả hiển thị object không đúng định dạng | Giá trị expression được chuyển thành text theo biểu diễn mặc định | Format dữ liệu trước hoặc dùng function định dạng |

Nên phân biệt lỗi parse với lỗi evaluate. Lỗi parse liên quan delimiter, string literal hoặc cú pháp expression. Lỗi evaluate xuất hiện sau khi template đã parse, ví dụ biến thiếu, property không tồn tại hoặc method được gọi phát sinh exception.

## 10. Kiểm thử template và delimiter

Một bộ kiểm thử nên xác nhận cả phần literal, expression block và delimiter tùy chỉnh.

Ví dụ kiểm thử cơ bản:

~~~java
@Test
void evaluatesTemplateWithLiteralAndExpression() {
    ExpressionParser parser = new SpelExpressionParser();

    StandardEvaluationContext context =
        new StandardEvaluationContext();
    context.setVariable("name", "Lan");

    Expression expression = parser.parseExpression(
        "Hello, #{#name}!",
        new TemplateParserContext()
    );

    assertEquals("Hello, Lan!", expression.getValue(context, String.class));
}
~~~

Kiểm thử giữ nguyên prefix trong đầu ra:

~~~java
@Test
void preservesTemplateDelimiterAsLiteralOutput() {
    ExpressionParser parser = new SpelExpressionParser();

    Expression expression = parser.parseExpression(
        "Syntax: #{'#{name}'}",
        new TemplateParserContext()
    );

    assertEquals("Syntax: #{name}", expression.getValue());
}
~~~

Kiểm thử delimiter tùy chỉnh:

~~~java
@Test
void usesCustomTemplateDelimiters() {
    ExpressionParser parser = new SpelExpressionParser();

    StandardEvaluationContext context =
        new StandardEvaluationContext();
    context.setVariable("name", "Lan");

    ParserContext parserContext =
        new TemplateParserContext("[[", "]]");

    Expression expression = parser.parseExpression(
        "Literal #{name}; value [[#name]]",
        parserContext
    );

    assertEquals(
        "Literal #{name}; value Lan",
        expression.getValue(context, String.class)
    );
}
~~~

Các trường hợp nên kiểm tra:

- Template chỉ có văn bản tĩnh.
- Template có một expression block.
- Template có nhiều expression block.
- Prefix xuất hiện như nội dung literal cần giữ nguyên.
- Suffix xuất hiện bên trong string literal.
- Dấu ngoặc tròn, vuông và nhọn trong expression.
- Expression block rỗng.
- Thiếu suffix hoặc string literal không đóng.
- Custom prefix/suffix.
- Biến hoặc property dùng trong block không hợp lệ.
- Giá trị null và kiểu kết quả cần định dạng.

## 11. An toàn khi đánh giá template

Template parsing vẫn thực thi SpEL bên trong mỗi expression block. Vì vậy, một template không chỉ là văn bản định dạng nếu người tạo template có thể chèn expression tùy ý.

Nếu template đến từ người dùng hoặc nguồn bên ngoài:

- Không cho phép người dùng tự do thêm expression block nếu họ không được phép thực thi SpEL.
- Phân tách nội dung literal do người dùng cung cấp khỏi expression code do ứng dụng kiểm soát.
- Dùng EvaluationContext với quyền truy cập tối thiểu cần thiết.
- Chỉ cung cấp root object, biến, function và resolver mà template cần.
- Tránh để expression đọc dữ liệu nhạy cảm hoặc gọi method có tác dụng phụ.
- Xác thực template trước khi lưu hoặc kích hoạt.
- Giới hạn độ dài và độ phức tạp của template theo nhu cầu ứng dụng.

Đổi delimiter chỉ thay đổi cách parser nhận diện expression block. Nó không phải cơ chế bảo mật và không giới hạn những gì SpEL bên trong block có thể làm.

## 12. Quy trình xử lý template có ký hiệu đặc biệt

Khi template cần chứa các ký hiệu giống delimiter:

1. **Xác định delimiter hiện tại.** Ghi rõ prefix và suffix mà parser đang sử dụng.
2. **Phân loại từng đoạn.** Xác định phần nào là literal text và phần nào thực sự cần được đánh giá.
3. **Giữ literal prefix.** Nếu cần hiển thị #{, dùng expression trả về string literal hoặc chọn delimiter khác.
4. **Kiểm tra string và ngoặc.** Bảo đảm dấu nháy đóng, dấu ngoặc cân bằng và suffix nằm đúng vị trí.
5. **Tách escape theo từng lớp.** Kiểm tra Java string trước, rồi kiểm tra chuỗi được chuyển tới SpEL.
6. **Parse bằng đúng ParserContext.** Không dùng parser context mặc định nếu template được tạo bằng delimiter riêng.
7. **Đánh giá với context cần thiết.** Cung cấp đầy đủ biến và root object.
8. **So sánh đầu ra chính xác.** Kiểm tra cả literal text, khoảng trắng, dấu ngoặc và giá trị động.

Nếu template phức tạp tới mức phải escape nhiều vị trí, hãy cân nhắc delimiter tùy chỉnh hoặc tách nội dung thành các đoạn literal và expression được quản lý riêng trong Java.

## 13. Thực hành tốt

- Dùng TemplateParserContext khi chuỗi cần trộn literal text và SpEL expression.
- Dùng delimiter mặc định #{...} khi không có xung đột với nội dung.
- Dùng ParserContext.TEMPLATE_EXPRESSION nếu muốn dùng cấu hình template mặc định có sẵn.
- Chọn delimiter tùy chỉnh khi văn bản thường xuyên chứa prefix mặc định.
- Dùng expression string literal để xuất một vài ký hiệu delimiter nguyên dạng.
- Không giả định backslash là cơ chế escape prefix của TemplateParserContext.
- Phân biệt escape của Java string với delimiter của template.
- Giữ expression block ngắn và có mục đích rõ.
- Kiểm tra dấu nháy và cấu trúc ngoặc khi có ký hiệu đặc biệt.
- Format số, ngày tháng và object theo quy tắc hiển thị rõ ràng.
- Dùng cùng ParserContext configuration trong parse, test và production.
- Không cho template không đáng tin thực thi SpEL với context có quyền rộng.

## 14. Checklist review

Trước khi đưa template vào sử dụng, hãy kiểm tra:

- [ ] Chuỗi được parse ở chế độ template.
- [ ] Prefix và suffix đã được xác định rõ.
- [ ] Literal text và expression block được phân loại đúng.
- [ ] Các block có expression hợp lệ và không rỗng.
- [ ] Prefix cần hiển thị nguyên dạng được xử lý có chủ đích.
- [ ] Không dựa vào backslash như một escape delimiter không được cấu hình.
- [ ] String literal và dấu ngoặc bên trong block được đóng đúng.
- [ ] Custom delimiter được dùng nhất quán ở mọi nơi.
- [ ] Java string escaping không bị nhầm với template parsing.
- [ ] Giá trị động được format theo yêu cầu hiển thị.
- [ ] Template và EvaluationContext có nguồn tin cậy, quyền phù hợp.
- [ ] Có test cho literal, nhiều block, delimiter đặc biệt và lỗi parse.

## Kết luận

Template expression của SpEL kết hợp văn bản tĩnh với các expression block được phân cách bằng prefix và suffix. TemplateParserContext mặc định dùng **#{** và **}**; parser ghép phần literal với kết quả của từng block. Khi nội dung cần hiển thị cũng chứa prefix, hãy tạo chuỗi literal từ một expression block hoặc chọn delimiter tùy chỉnh như [[...]]. Không nhầm escaping của Java string với việc nhận diện delimiter của template, và không giả định backslash có thể escape prefix. Hãy parse bằng đúng ParserContext, kiểm tra dấu nháy và ngoặc, rồi kiểm thử đầu ra chính xác trong EvaluationContext thực tế.

## Tài liệu tham khảo

- Spring Framework Reference — Expression Templating: https://docs.spring.io/spring-framework/reference/core/expressions/language-ref/templating.html
- Spring Framework API — TemplateParserContext: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/expression/common/TemplateParserContext.html
- Spring Framework API — ParserContext: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/expression/ParserContext.html