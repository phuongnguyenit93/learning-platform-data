# Phân biệt expression thuần với template expression

Spring Expression Language (SpEL) có thể phân tích một chuỗi theo hai chế độ: **expression thuần** và **template expression**. Với expression thuần, toàn bộ chuỗi được hiểu là cú pháp SpEL. Với template expression, chuỗi được chia thành văn bản tĩnh và những đoạn SpEL được đánh dấu bằng delimiter; parser giữ văn bản tĩnh và đánh giá các đoạn biểu thức được nhúng.

Việc chọn đúng chế độ parse giúp tránh lỗi cú pháp và thể hiện đúng mục đích của chuỗi. Expression thuần phù hợp khi cần tính một giá trị hoặc kiểm tra điều kiện. Template expression phù hợp khi cần tạo thông báo, nhãn hoặc nội dung có phần văn bản cố định xen với dữ liệu động.

## Expression thuần

Overload **parseExpression(String)** xem toàn bộ tham số đầu vào là một biểu thức SpEL. Chuỗi phải tuân theo cú pháp của ngôn ngữ, kể cả khi kết quả cuối cùng là một String.

~~~java
ExpressionParser parser = new SpelExpressionParser();

Expression expression =
        parser.parseExpression("10 * (5 + 2)");

Integer result =
        expression.getValue(Integer.class);
~~~

Biểu thức trên thực hiện phép tính và trả về 70. Toàn bộ chuỗi **10 * (5 + 2)** là cú pháp SpEL; không có phần văn bản nào được giữ nguyên như nội dung template.

Expression thuần cũng có thể trả về chuỗi literal:

~~~java
Expression expression =
        parser.parseExpression("'Xin chào, Spring!'");

String message =
        expression.getValue(String.class);
~~~

Trong ví dụ này, dấu nháy đơn là cú pháp string literal của SpEL. Kết quả là chuỗi **Xin chào, Spring!**. Việc kết quả có kiểu String không làm cho expression trở thành template.

Một expression thuần khác có thể đọc biến và nối chuỗi:

~~~java
StandardEvaluationContext context =
        new StandardEvaluationContext();

context.setVariable("name", "An");

Expression expression =
        parser.parseExpression("'Xin chào, ' + #name + '!'");

String message =
        expression.getValue(context, String.class);
~~~

Toàn bộ nội dung vẫn được parse như một expression duy nhất. Các phần văn bản phải được viết thành string literal và nối bằng toán tử **+**.

## Template expression

Template expression cho phép trộn văn bản thông thường với một hoặc nhiều đoạn SpEL. Parser nhận diện đoạn cần đánh giá bằng cặp delimiter được cung cấp qua **ParserContext**.

Spring cung cấp **TemplateParserContext** với delimiter mặc định:

- Prefix: **#{**
- Suffix: **}**

Phần nằm giữa prefix và suffix được parse như expression SpEL. Văn bản bên ngoài delimiter được giữ lại như literal text.

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

Kết quả là **Xin chào, An!**. Parser giữ nguyên phần văn bản **Xin chào, ** và **!**, đồng thời đánh giá **#name** rồi ghép kết quả vào vị trí tương ứng.

Khác biệt quan trọng nằm ở overload được gọi. Chuỗi có văn bản tự do xen với delimiter **#{...}** cần được parse với ParserContext ở chế độ template. Nếu gọi **parseExpression(String)**, toàn bộ chuỗi được hiểu là expression thuần và phần văn bản bên ngoài delimiter có thể khiến parser báo lỗi cú pháp.

## So sánh hai chế độ

| Đặc điểm | Expression thuần | Template expression |
|---|---|---|
| API thường dùng | **parseExpression(String)** | **parseExpression(String, ParserContext)** |
| Cách hiểu đầu vào | Toàn bộ chuỗi là cú pháp SpEL | Văn bản tĩnh xen với các đoạn SpEL |
| Delimiter | Không cần delimiter template | Prefix/suffix do ParserContext cung cấp |
| Cách viết văn bản | Dùng string literal và toán tử nối | Viết trực tiếp ngoài delimiter |
| Kết quả điển hình | Giá trị của expression | Chuỗi gồm literal text và kết quả expression |
| Trường hợp phù hợp | Tính toán, điều kiện, truy cập dữ liệu | Thông báo, nhãn và nội dung động |

Cả hai chế độ đều sử dụng cùng cú pháp SpEL bên trong phần expression. ParserContext chỉ quyết định cách chia chuỗi đầu vào thành những phần cần giữ nguyên và những phần cần parse/đánh giá.

## ParserContext có vai trò gì?

Overload có ParserContext có dạng:

~~~java
Expression parseExpression(
        String expressionString,
        ParserContext context);
~~~

**ParserContext** mô tả cách parser xử lý chuỗi. Interface này cung cấp ba thông tin chính:

- **isTemplate()**: cho biết đầu vào có được xử lý như template hay không.
- **getExpressionPrefix()**: trả về delimiter mở đầu một đoạn expression.
- **getExpressionSuffix()**: trả về delimiter kết thúc đoạn expression.

**TemplateParserContext** là implementation có sẵn để không phải tự viết ParserContext cho trường hợp thông thường:

~~~java
ParserContext parserContext =
        new TemplateParserContext();

Expression template = parser.parseExpression(
        "Đơn hàng: #{#orderId}",
        parserContext);
~~~

Constructor mặc định dùng **#{** và **}**. Có thể truyền delimiter khác nếu cú pháp của ứng dụng cần tránh xung đột với một template engine hoặc định dạng cấu hình khác.

~~~java
ParserContext parserContext =
        new TemplateParserContext("[[", "]]");

Expression template = parser.parseExpression(
        "Đơn hàng: [[#orderId]]",
        parserContext);
~~~

Trong ví dụ, **[[** mở đầu đoạn SpEL và **]]** kết thúc đoạn đó. Phần văn bản còn lại vẫn được giữ nguyên. Delimiter tùy chỉnh chỉ có tác dụng khi parser được truyền ParserContext tương ứng; nó không tự thay đổi cú pháp của parser mặc định.

## Nhiều đoạn expression trong cùng một template

Một template có thể chứa nhiều đoạn expression, mỗi đoạn được đánh giá trong EvaluationContext được truyền khi gọi getValue:

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

Các đoạn nhúng dùng chung EvaluationContext nên có thể đọc cùng các biến và root object. Nếu một đoạn tham chiếu biến chưa được cung cấp, đọc property không tồn tại hoặc gọi method không được context cho phép, quá trình evaluation có thể thất bại.

Nên giữ mỗi đoạn expression ngắn và tập trung vào việc lấy hoặc tính một giá trị. Nếu template chứa nhiều nhánh nghiệp vụ, hãy tính các giá trị trong Java rồi đưa kết quả đơn giản vào context.

## Expression thuần nối chuỗi và template expression

Cùng một nội dung có thể được viết theo cả hai cách.

Expression thuần:

~~~java
Expression expression =
        parser.parseExpression(
                "'Khách hàng ' + #customer + ', đơn ' + #orderId");

String message =
        expression.getValue(context, String.class);
~~~

Template expression:

~~~java
Expression template = parser.parseExpression(
        "Khách hàng #{#customer}, đơn #{#orderId}",
        new TemplateParserContext());

String message =
        template.getValue(context, String.class);
~~~

Cả hai cách đều có thể tạo cùng kết quả. Expression thuần biểu diễn thao tác nối bằng cú pháp SpEL. Template biểu diễn trực tiếp văn bản tĩnh và vị trí dữ liệu động, thường dễ đọc hơn khi phần văn bản chiếm phần lớn nội dung.

Nếu chuỗi chỉ chứa một phép tính hoặc một giá trị, dùng expression thuần thường rõ ràng hơn. Không cần thêm template delimiter khi toàn bộ đầu vào đã là cú pháp SpEL.

## Phân biệt #{...} và property placeholder

Trong cấu hình Spring, hai dạng ký hiệu dễ bị nhầm là **#{...}** và **dollar-brace placeholder**:

- **#{...}** là delimiter thường dùng để nhúng biểu thức SpEL trong những điểm tích hợp hỗ trợ SpEL.
- **dollar-brace placeholder** là cú pháp lấy giá trị từ nguồn cấu hình như properties hoặc Environment.

Ví dụ:

~~~java
@Value("${app.name:Demo}")
private String applicationName;

@Value("#{systemProperties['user.timezone']}")
private String timeZone;
~~~

Field **applicationName** lấy property **app.name** và dùng **Demo** làm giá trị mặc định khi property chưa được khai báo. Field **timeZone** đánh giá biểu thức SpEL để đọc system property **user.timezone**.

Hai cơ chế giải quyết hai nhiệm vụ khác nhau. Property placeholder thay thế giá trị cấu hình; SpEL đánh giá biểu thức trên dữ liệu và EvaluationContext. Một số điểm tích hợp Spring có thể phối hợp cả hai cơ chế, nhưng parser API thuần không tự động coi placeholder là một biểu thức SpEL.

Cũng cần phân biệt template expression được parse trực tiếp bằng **TemplateParserContext** với cách một annotation hoặc integration Spring xử lý **#{...}**. Khi dùng API parser, hãy truyền ParserContext rõ ràng nếu chuỗi có văn bản tĩnh nằm ngoài các đoạn expression.

## Template chỉ có văn bản hoặc chỉ có expression

Template có thể chứa nhiều phần văn bản và expression. Nếu không có phần văn bản tĩnh, expression thuần thường là lựa chọn trực tiếp hơn:

~~~java
Expression expression =
        parser.parseExpression("#total * 1.08");

BigDecimal totalWithTax =
        expression.getValue(context, BigDecimal.class);
~~~

Nếu cần đưa kết quả vào một câu thông báo, template phù hợp hơn:

~~~java
Expression template = parser.parseExpression(
        "Tổng thanh toán: #{#total * 1.08}",
        new TemplateParserContext());

String message =
        template.getValue(context, String.class);
~~~

Ở ví dụ thứ hai, phần tính toán nằm trong đoạn expression được nhúng, còn nhãn **Tổng thanh toán: ** là văn bản tĩnh. Nếu kết quả cần định dạng tiền tệ, locale hoặc làm tròn theo nghiệp vụ, nên chuẩn bị giá trị đã định dạng trong Java thay vì đưa nhiều logic định dạng vào template.

## Tái sử dụng Expression và EvaluationContext

Có thể parse template một lần rồi đánh giá nhiều lần với các context khác nhau:

~~~java
Expression template = parser.parseExpression(
        "Xin chào, #{#name}!",
        new TemplateParserContext());

StandardEvaluationContext firstContext =
        new StandardEvaluationContext();
firstContext.setVariable("name", "An");

StandardEvaluationContext secondContext =
        new StandardEvaluationContext();
secondContext.setVariable("name", "Binh");

String first =
        template.getValue(firstContext, String.class);

String second =
        template.getValue(secondContext, String.class);
~~~

Cùng một cấu trúc template có thể tạo nội dung cho nhiều người nhận. Expression giữ nguyên chuỗi đã parse; giá trị động đến từ context tại thời điểm evaluate.

Nếu biến chứa dữ liệu riêng của từng request, nên dùng context riêng cho request đó. Không nên thay đổi biến trên một EvaluationContext mutable đang được nhiều luồng dùng đồng thời, vì các lần đánh giá có thể đọc nhầm dữ liệu của nhau.

## Delimiter và văn bản đầu vào

Khi chọn delimiter cho template, cần bảo đảm cặp mở/đóng không xung đột với cú pháp của văn bản xung quanh. Nếu dùng delimiter tùy chỉnh, mọi nơi parse template phải dùng cùng ParserContext.

Ngoài ra, văn bản tĩnh và expression nhúng có nguồn gốc khác nhau:

- Văn bản nằm ngoài delimiter được giữ như literal text.
- Nội dung bên trong delimiter được đánh giá như SpEL trong EvaluationContext được cung cấp.

Nếu toàn bộ template hoặc một phần template đến từ người dùng, không nên mặc định rằng nội dung chỉ là văn bản hiển thị. Người dùng có thể đưa cú pháp vào vùng delimiter để tạo expression được đánh giá. Hãy kiểm soát ai có thể sửa template và giới hạn root object, biến, property accessor, method resolver cùng các khả năng khác của context.

Kết quả template cũng không tự động được escape cho HTML, SQL, shell hoặc một định dạng đầu ra cụ thể. Nếu đưa kết quả lên giao diện hoặc vào một hệ thống khác, hãy áp dụng quy tắc encoding/escaping phù hợp với đích sử dụng.

## Lỗi parse và lỗi evaluation

Expression thuần và template expression đều có thể thất bại ở hai giai đoạn:

- **ParseException:** chuỗi không đúng cú pháp, delimiter không khớp, ParserContext không phù hợp hoặc một đoạn expression nhúng sai cú pháp.
- **EvaluationException:** expression đã parse nhưng không thể đánh giá với dữ liệu hoặc EvaluationContext hiện tại, ví dụ biến chưa được cung cấp, property không tồn tại hoặc method không được phép gọi.

Có thể tách hai giai đoạn để xử lý rõ ràng:

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

Nếu template được lưu trong cấu hình, có thể parse khi nạp cấu hình để phát hiện lỗi cú pháp sớm. Việc evaluate vẫn cần root object, biến và context hợp lệ tại thời điểm sử dụng.

Không nên bắt mọi lỗi evaluation rồi trả về chuỗi rỗng mà không ghi nhận nguyên nhân. Cách đó có thể che giấu lỗi biến, property hoặc method và khiến nội dung đầu ra sai mà khó phát hiện.

## Khi nào chọn từng loại?

Dùng **expression thuần** khi:

- Toàn bộ chuỗi đầu vào là cú pháp SpEL.
- Cần tính toán, so sánh hoặc trả về một giá trị.
- Biểu thức được dùng làm điều kiện hoặc giá trị cấu hình.
- Có thể biểu diễn kết quả bằng một string literal hoặc phép nối SpEL đơn giản.

Dùng **template expression** khi:

- Cần trộn văn bản thông thường với dữ liệu động.
- Muốn tạo thông báo hoặc nhãn từ nhiều biến.
- Có nhiều đoạn expression trong cùng một chuỗi.
- Muốn tách rõ phần nội dung cố định khỏi phần được đánh giá.

Nếu chỉ cần thay thế một vài property placeholder, dùng cơ chế cấu hình tương ứng thường phù hợp hơn. Nếu cần template có localization, format phức tạp, vòng lặp hoặc nhiều nhánh, cân nhắc một template engine chuyên dụng hoặc xây dựng nội dung trong Java.

## Kết luận

**Expression thuần** xem toàn bộ chuỗi là cú pháp SpEL và thường dùng **parseExpression(String)**. **Template expression** kết hợp văn bản tĩnh với những đoạn SpEL được đánh dấu bằng delimiter, dùng **parseExpression(String, ParserContext)**. **TemplateParserContext** mặc định dùng prefix **#{** và suffix **}**, đồng thời cho phép cấu hình cặp delimiter khác.

Hãy dùng expression thuần cho phép tính và điều kiện; dùng template khi cần đặt kết quả biểu thức vào giữa văn bản thông thường. Phân biệt delimiter SpEL với property placeholder, truyền ParserContext đúng với delimiter và kiểm soát EvaluationContext nếu template có thể được chỉnh sửa từ nguồn bên ngoài.
