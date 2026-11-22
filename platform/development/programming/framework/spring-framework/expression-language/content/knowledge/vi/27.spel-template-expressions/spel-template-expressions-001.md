# Phân biệt expression thuần với template expression

Spring Expression Language (SpEL) hỗ trợ hai cách phân tích chuỗi thường gặp: **expression thuần** và **template expression**. Expression thuần xem toàn bộ chuỗi đầu vào là cú pháp SpEL. Template expression cho phép trộn văn bản thông thường với một hoặc nhiều đoạn SpEL được đặt giữa cặp ký hiệu phân cách.

Sự khác biệt này quan trọng khi ứng dụng cần tính một giá trị logic hoặc khi muốn tạo nội dung hiển thị có chứa cả văn bản cố định lẫn dữ liệu động. Cùng một chuỗi có thể được parse theo cách khác nhau tùy **ParserContext** được truyền vào parser.

## Expression thuần là gì?

Expression thuần là chuỗi mà toàn bộ nội dung được hiểu theo cú pháp SpEL. Khi dùng overload **parseExpression(String)**, parser mặc định không xem các đoạn văn bản nằm ngoài một cặp delimiter là nội dung tĩnh của template.

Ví dụ, biểu thức số học:

~~~java
ExpressionParser parser = new SpelExpressionParser();

Expression expression =
        parser.parseExpression("10 * (5 + 2)");

Integer result =
        expression.getValue(Integer.class);
~~~

Toàn bộ chuỗi **10 * (5 + 2)** là biểu thức. SpEL phân tích cú pháp, đánh giá phép toán và trả về kết quả 70.

Expression thuần cũng có thể đọc property hoặc biến:

~~~java
StandardEvaluationContext context =
        new StandardEvaluationContext();

context.setVariable("name", "An");

Expression expression =
        parser.parseExpression("#name.toUpperCase()");

String result =
        expression.getValue(context, String.class);
~~~

Ở đây, toàn bộ chuỗi **#name.toUpperCase()** là cú pháp SpEL. Không có phần văn bản tĩnh nào cần được giữ nguyên và nối với kết quả.

## Template expression là gì?

Template expression cho phép kết hợp văn bản thông thường với các đoạn biểu thức SpEL. Parser nhận biết những đoạn cần đánh giá thông qua cặp ký hiệu mở đầu và kết thúc do **ParserContext** quy định.

Với cấu hình template mặc định của Spring, cặp delimiter là **#{** và **}**. Phần nằm giữa hai delimiter được parse như một expression thuần; phần văn bản bên ngoài được giữ lại như nội dung literal.

Ví dụ:

~~~java
ExpressionParser parser = new SpelExpressionParser();

StandardEvaluationContext context =
        new StandardEvaluationContext();

context.setVariable("name", "An");

Expression template = parser.parseExpression(
        "Xin chào, #{#name}!",
        new TemplateParserContext());

String message =
        template.getValue(context, String.class);
~~~

Kết quả là **Xin chào, An!**. Parser giữ phần văn bản **Xin chào, ** và **!**, đồng thời đánh giá đoạn **#name** rồi ghép kết quả vào đúng vị trí.

Nếu truyền chuỗi **Xin chào, #{#name}!** vào overload parseExpression(String) mà không có template context, toàn bộ chuỗi sẽ được xem là cú pháp expression thuần. Phần văn bản thông thường không phải cú pháp SpEL hợp lệ trong vị trí đó, nên parser có thể phát sinh ParseException.

## So sánh hai cách parse

| Đặc điểm | Expression thuần | Template expression |
|---|---|---|
| Cách gọi phổ biến | **parseExpression(String)** | **parseExpression(String, ParserContext)** |
| Cách hiểu chuỗi | Toàn bộ chuỗi là SpEL | Trộn literal text với các đoạn SpEL |
| Delimiter | Không cần delimiter template | Dùng prefix/suffix từ ParserContext |
| Kết quả thường gặp | Giá trị của biểu thức | Chuỗi được tạo từ văn bản và kết quả các đoạn nhúng |
| Use case | Tính toán, điều kiện, truy cập dữ liệu | Thông báo, nhãn, nội dung cấu hình có dữ liệu động |

Cả hai cách đều dùng cùng ngôn ngữ SpEL bên trong các đoạn expression. Khác biệt nằm ở cách parser chia chuỗi đầu vào thành phần literal và phần cần đánh giá.

## ParserContext và TemplateParserContext

Overload thứ hai của parser có dạng:

~~~java
Expression parseExpression(
        String expressionString,
        ParserContext context);
~~~

**ParserContext** cung cấp thông tin để parser biết chuỗi đầu vào có phải template hay không và, nếu là template, dùng delimiter nào.

Interface này có các thông tin chính:

- **isTemplate()**: cho biết chuỗi cần được parse theo chế độ template hay expression thuần.
- **getExpressionPrefix()**: trả về ký hiệu mở đầu đoạn expression.
- **getExpressionSuffix()**: trả về ký hiệu kết thúc đoạn expression.

Spring cung cấp **TemplateParserContext** để dùng template một cách thuận tiện:

~~~java
ParserContext parserContext =
        new TemplateParserContext();

Expression template = parser.parseExpression(
        "Tổng đơn hàng: #{#total}",
        parserContext);
~~~

Constructor mặc định của TemplateParserContext sử dụng prefix **#{** và suffix **}**. Có thể truyền delimiter khác khi ứng dụng muốn một cú pháp template riêng:

~~~java
ParserContext parserContext =
        new TemplateParserContext("[[", "]]");

Expression template = parser.parseExpression(
        "Tổng đơn hàng: [[#total]]",
        parserContext);
~~~

Trong ví dụ, **[[** mở đầu đoạn SpEL và **]]** kết thúc đoạn đó. Phần văn bản còn lại vẫn là literal text.

Delimiter tùy chỉnh chỉ có hiệu lực khi parser được truyền ParserContext tương ứng. Nếu dùng parser mặc định mà không truyền context, parser không tự suy ra rằng **[[...]]** là một đoạn template.

## Template có thể chứa nhiều đoạn expression

Một template có thể chứa nhiều đoạn SpEL, xen kẽ với văn bản tĩnh:

~~~java
StandardEvaluationContext context =
        new StandardEvaluationContext();

context.setVariable("customer", "An");
context.setVariable("orderId", "ORD-1024");
context.setVariable("total", new BigDecimal("250.00"));

Expression template = parser.parseExpression(
        "Khách hàng #{#customer}, đơn #{#orderId}, "
        + "tổng tiền #{#total}",
        new TemplateParserContext());

String message =
        template.getValue(context, String.class);
~~~

Kết quả có dạng:

~~~text
Khách hàng An, đơn ORD-1024, tổng tiền 250.00
~~~

Mỗi đoạn nằm giữa delimiter được đánh giá trong cùng EvaluationContext. Các biến có thể được dùng lại ở nhiều đoạn. Nếu một biến không tồn tại hoặc một property không thể truy cập, quá trình đánh giá template có thể thất bại tại đoạn expression tương ứng.

Nhiều đoạn nhúng giúp tạo thông báo linh hoạt mà không phải nối chuỗi trong Java. Tuy nhiên, nếu template có quá nhiều nhánh hoặc logic nghiệp vụ phức tạp, nên tính các giá trị trong Java trước rồi truyền kết quả đơn giản vào context.

## Literal text được giữ lại, expression được đánh giá

Có thể hình dung parser xử lý template theo hai phần:

1. Văn bản nằm ngoài delimiter được giữ nguyên.
2. Nội dung bên trong mỗi cặp delimiter được parse và đánh giá như một biểu thức SpEL.

Ví dụ:

~~~text
Trạng thái: #{#status}, số lượng: #{#quantity}
~~~

Nếu **#status** là **PAID** và **#quantity** là 3, kết quả là:

~~~text
Trạng thái: PAID, số lượng: 3
~~~

Các ký tự **Trạng thái: **, **, số lượng: ** và phần dấu câu là văn bản tĩnh. Hai biến là nội dung động.

Template hữu ích khi cần tạo chuỗi hiển thị, nhưng không làm thay đổi quy tắc của các expression nhúng. Bên trong delimiter, vẫn có thể dùng property access, toán tử, method call hoặc các tính năng SpEL khác mà EvaluationContext cho phép.

## Template expression trong cấu hình Spring

Trong nhiều điểm tích hợp của Spring, biểu thức được viết giữa **#{...}**. Ví dụ với @Value:

~~~java
@Value("#{systemProperties['user.timezone']}")
private String timeZone;
~~~

Spring xử lý nội dung trong dấu **#{...}** như một biểu thức SpEL và inject kết quả vào field. Đây là cách nhúng expression trong cơ chế cấu hình của Spring; ứng dụng không cần tự tạo parser trong trường hợp annotation đã được Spring xử lý.

Một template có văn bản tĩnh xen lẫn expression cũng có thể dùng trong những điểm tích hợp hỗ trợ template parsing:

~~~java
@Value("Chạy trên hệ thống #{systemProperties['os.name']}")
private String environmentLabel;
~~~

Khả năng cụ thể phụ thuộc vào điểm tích hợp và cách nó cấu hình expression resolver. Khi dùng API parser trực tiếp, hãy truyền ParserContext rõ ràng nếu chuỗi có literal text bên ngoài các đoạn expression.

## Phân biệt template delimiter #{...} với property placeholder ${...}

Trong cấu hình Spring, hai dạng ký hiệu dễ bị nhầm là **#{...}** và **${...}**:

- **#{...}** dùng để nhúng một biểu thức SpEL tại điểm tích hợp hỗ trợ SpEL.
- **${...}** là property placeholder, dùng để lấy giá trị từ nguồn cấu hình như properties hoặc environment.

Ví dụ:

~~~java
@Value("${app.name:Demo}")
private String applicationName;

@Value("#{systemProperties['user.timezone']}")
private String timeZone;
~~~

Field đầu tiên lấy property **app.name** và dùng **Demo** làm giá trị mặc định nếu property chưa được khai báo. Field thứ hai đánh giá biểu thức SpEL để đọc system property user.timezone.

Hai cơ chế có thể được kết hợp trong một số cấu hình Spring, nhưng chúng giải quyết hai nhiệm vụ khác nhau. Property placeholder thay thế giá trị cấu hình; SpEL đánh giá biểu thức trên dữ liệu và context.

Nếu cần tính toán trên một property đã được inject, có thể dùng placeholder làm đầu vào của một biểu thức tại điểm tích hợp hỗ trợ cả hai cơ chế. Hãy dựa vào thứ tự xử lý của integration cụ thể, không giả định mọi parser API tự động hiểu cả hai loại delimiter.

## Expression thuần có thể chứa chuỗi literal

Expression thuần vẫn có thể trả về một chuỗi. Điều đó không biến nó thành template expression:

~~~java
Expression expression =
        parser.parseExpression("'Xin chào, Spring!'");

String result =
        expression.getValue(String.class);
~~~

Toàn bộ chuỗi được đặt trong dấu nháy đơn là một string literal SpEL. Kết quả là **Xin chào, Spring!**.

Sự khác biệt nằm ở chỗ template giữ phần văn bản nằm ngoài các delimiter mà không cần đặt nó thành string literal trong cú pháp SpEL. Nếu viết văn bản tự do xen với nhiều biểu thức, template thường dễ đọc hơn việc nối các string literal bằng toán tử **+**.

Ví dụ expression thuần có thể nối chuỗi:

~~~java
Expression expression =
        parser.parseExpression(
                "'Xin chào, ' + #name + '!'");
~~~

Cùng mục tiêu hiển thị có thể được viết dưới dạng template:

~~~java
Expression template = parser.parseExpression(
        "Xin chào, #{#name}!",
        new TemplateParserContext());
~~~

Cách template thể hiện trực tiếp phần văn bản tĩnh và vị trí dữ liệu động. Cách expression thuần thể hiện toàn bộ thao tác nối chuỗi bằng cú pháp SpEL.

## Khi template chỉ chứa một đoạn expression

Nếu mục tiêu chỉ là đánh giá một biểu thức, không có văn bản tĩnh xen kẽ, dùng **parseExpression(String)** thường đơn giản hơn:

~~~java
Expression expression =
        parser.parseExpression("#total * 1.08");

BigDecimal result =
        expression.getValue(context, BigDecimal.class);
~~~

Không cần thêm delimiter template khi toàn bộ chuỗi đã là cú pháp SpEL.

TemplateParserContext được dùng khi chuỗi cần có cả phần văn bản thông thường và phần expression được đánh giá. Việc chọn đúng chế độ parse giúp tránh lỗi cú pháp và làm rõ ý định của chuỗi đầu vào.

## Lỗi parse và lỗi evaluation

Expression thuần và template expression đều có thể thất bại ở hai giai đoạn:

- **ParseException:** chuỗi không đúng cú pháp. Với template, lỗi có thể do delimiter không khớp, đoạn expression bên trong sai cú pháp hoặc ParserContext không phù hợp.
- **EvaluationException:** expression đã parse nhưng không thể đánh giá với dữ liệu hoặc EvaluationContext hiện tại, ví dụ biến chưa được cung cấp, property không tồn tại hoặc method không được phép gọi.

Ví dụ:

~~~java
Expression template;

try {
    template = parser.parseExpression(
            "Xin chào, #{#customer.name}!",
            new TemplateParserContext());
} catch (ParseException ex) {
    throw new IllegalArgumentException(
            "Invalid template syntax", ex);
}

try {
    String message =
            template.getValue(context, String.class);
} catch (EvaluationException ex) {
    throw new IllegalStateException(
            "Cannot evaluate template", ex);
}
~~~

Việc tách hai loại lỗi giúp xác định vấn đề nằm ở cấu trúc chuỗi hay dữ liệu runtime. Nếu template được lưu trong cấu hình, có thể parse khi nạp cấu hình để phát hiện lỗi cú pháp sớm; việc đánh giá vẫn cần context và dữ liệu phù hợp tại thời điểm chạy.

## Lưu ý khi thiết kế delimiter

Delimiter mặc định **#{** và **}** phổ biến trong Spring. Khi dùng template trong một hệ thống có nhiều ngôn ngữ template hoặc cấu hình khác, cần chú ý tránh xung đột với cú pháp của hệ thống khác.

Một số nguyên tắc:

- Chọn delimiter rõ ràng và nhất quán nếu cần delimiter tùy chỉnh.
- Truyền cùng ParserContext khi parse mọi template dùng delimiter đó.
- Đảm bảo mỗi đoạn expression có cặp delimiter đóng/mở phù hợp.
- Tránh để văn bản người dùng không tin cậy được hiểu nhầm thành đoạn SpEL có thể thực thi.
- Giới hạn những gì EvaluationContext cho phép expression nhúng truy cập.

Thay delimiter chỉ thay đổi cách parser nhận diện vùng expression. Nó không giới hạn quyền của biểu thức bên trong. Nếu template chứa expression từ nguồn bên ngoài, vẫn phải kiểm soát context, root object, biến, accessor và method resolver.

## Khi nào nên dùng expression thuần và khi nào nên dùng template?

Dùng **expression thuần** khi:

- Toàn bộ chuỗi đầu vào là cú pháp SpEL.
- Cần tính toán một giá trị, trả về Boolean hoặc đọc property.
- Biểu thức được dùng làm key, điều kiện hoặc giá trị cấu hình.
- Không có phần văn bản tĩnh cần giữ nguyên.

Dùng **template expression** khi:

- Cần trộn văn bản thông thường với dữ liệu động.
- Muốn tạo thông báo, nhãn hoặc chuỗi cấu hình có các đoạn SpEL.
- Có nhiều vùng expression được nhúng trong cùng một chuỗi.
- Muốn phần literal text dễ đọc mà không phải viết nhiều toán tử nối chuỗi.

Nếu chuỗi chỉ cần thay một vài placeholder đơn giản từ cấu hình, property placeholder hoặc một template engine chuyên dụng có thể phù hợp hơn. Nếu logic tạo nội dung có nhiều nhánh, format phức tạp hoặc cần localization, hãy cân nhắc xây dựng nội dung trong Java hoặc dùng thư viện template chuyên biệt.

## Kết luận

**Expression thuần** xem toàn bộ chuỗi là cú pháp SpEL và thường được parse bằng **parseExpression(String)**. **Template expression** kết hợp văn bản tĩnh với các đoạn SpEL, được parse bằng **parseExpression(String, ParserContext)**. **TemplateParserContext** mặc định dùng delimiter **#{** và **}**, đồng thời cho phép cấu hình cặp delimiter khác.

Hãy dùng expression thuần cho phép tính, điều kiện và truy cập dữ liệu. Dùng template khi cần đặt kết quả expression vào giữa văn bản thông thường. Phân biệt **#{...}** của SpEL với **${...}** của property placeholder, truyền ParserContext đúng với delimiter và giới hạn EvaluationContext khi template chứa biểu thức từ nguồn bên ngoài.
