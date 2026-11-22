# SpEL template trong message, annotation và cấu hình

## Mục tiêu

Sau bài này, bạn có thể phân biệt biểu thức SpEL thông thường với template expression; dùng TemplateParserContext để trộn văn bản cố định và các đoạn biểu thức được đánh giá; đưa template vào message Java, annotation và cấu hình Spring; phân biệt placeholder ${...} với biểu thức SpEL #{...}; và kiểm soát dữ liệu cùng quyền truy cập trong EvaluationContext. Bạn cũng sẽ biết cách xử lý delimiter, null, lỗi parse/runtime và template đến từ nguồn không đáng tin cậy.

## 1. Template expression là gì?

Một biểu thức SpEL thông thường mô tả toàn bộ nội dung cần đánh giá:

~~~text
#customer.name
~~~

Khi đánh giá, kết quả là property name của object customer.

Template expression cho phép trộn văn bản thông thường với các đoạn SpEL nằm giữa cặp delimiter. Với delimiter mặc định, phần biểu thức được đặt giữa `#{` và `}`:

~~~text
Hello, #{#customer.name}!
~~~

Phần văn bản Hello, và dấu chấm than được giữ nguyên. SpEL chỉ đánh giá đoạn `#customer.name` rồi ghép kết quả vào đúng vị trí.

Template expression phù hợp với thông báo đơn hàng, email, nhãn hiển thị, message cấu hình hoặc chuỗi được inject vào bean. Phần văn bản bên ngoài delimiter là literal, không phải mã SpEL.

## 2. Phân biệt expression thông thường và template expression

Khi parse chuỗi mà không truyền ParserContext, SpEL mặc định coi toàn bộ chuỗi là biểu thức:

~~~java
Expression expression =
    parser.parseExpression("#customer.name");
~~~

Khi cần trộn văn bản với đoạn SpEL, truyền TemplateParserContext:

~~~java
Expression expression = parser.parseExpression(
    "Hello, #{#customer.name}!",
    new TemplateParserContext()
);
~~~

| Nội dung | Cách parse | Ý nghĩa |
|---|---|---|
| `#customer.name` | parseExpression(text) | Toàn bộ chuỗi là một biểu thức |
| `Hello, #{#customer.name}!` | parseExpression(text, new TemplateParserContext()) | Văn bản literal xen kẽ biểu thức |
| `#{#customer.name}` | parseExpression(text, new TemplateParserContext()) | Template chỉ chứa một đoạn biểu thức |

Nếu truyền câu văn tự do vào parser mà không dùng ParserContext dạng template, parser có thể báo lỗi vì nó đang cố phân tích toàn bộ câu như SpEL.

## 3. TemplateParserContext và delimiter mặc định

TemplateParserContext thuộc package org.springframework.expression.common. Constructor không tham số dùng delimiter mặc định:

- Prefix: `#{`
- Suffix: `}`

Ví dụ:

~~~java
ExpressionParser parser = new SpelExpressionParser();
ParserContext templateContext = new TemplateParserContext();

Expression expression = parser.parseExpression(
    "Order #{#orderId} is now #{#status}.",
    templateContext
);
~~~

TemplateParserContext cho parser biết chuỗi đang ở chế độ template và xác định phần nào là expression. Nó không cung cấp biến, bean hoặc object để đánh giá; những dữ liệu đó thuộc EvaluationContext.

Có thể dùng ParserContext.TEMPLATE_EXPRESSION nếu phiên bản Spring đang dùng cung cấp hằng số này. Dùng new TemplateParserContext() giúp thể hiện rõ delimiter mặc định.

## 4. Ví dụ hoàn chỉnh: tạo message trong Java

Ví dụ sau tạo thông báo từ tên khách hàng và mã đơn hàng:

~~~java
import org.springframework.expression.Expression;
import org.springframework.expression.ExpressionParser;
import org.springframework.expression.common.TemplateParserContext;
import org.springframework.expression.spel.standard.SpelExpressionParser;
import org.springframework.expression.spel.support.StandardEvaluationContext;

public class MessageTemplateExample {

    public static void main(String[] args) {
        ExpressionParser parser = new SpelExpressionParser();

        String template =
            "Hello #{#customerName}, order #{#orderId} is #{#status}.";

        Expression expression = parser.parseExpression(
            template,
            new TemplateParserContext()
        );

        StandardEvaluationContext context =
            new StandardEvaluationContext();

        context.setVariable("customerName", "An");
        context.setVariable("orderId", "ORD-1024");
        context.setVariable("status", "SHIPPED");

        String message = expression.getValue(context, String.class);
        System.out.println(message);
    }
}
~~~

Kết quả:

~~~text
Hello An, order ORD-1024 is SHIPPED.
~~~

Quy trình gồm bốn bước: viết chuỗi template; parse bằng TemplateParserContext; đăng ký dữ liệu trong EvaluationContext; gọi getValue để tạo nội dung hoàn chỉnh.

Có thể parse template một lần rồi tái sử dụng Expression cho nhiều message. Mỗi lần đánh giá, cung cấp context với dữ liệu của người nhận hoặc sự kiện tương ứng.

## 5. Dùng property của root object trong template

Không nhất thiết mọi giá trị động đều phải là variable. Template có thể đọc property từ root object:

~~~text
Dear #{name}, your order #{order.id} is ready.
~~~

Ví dụ Java:

~~~java
StandardEvaluationContext context =
    new StandardEvaluationContext(order);

Expression expression = parser.parseExpression(
    "Order #{id} for #{customer.name} is ready.",
    new TemplateParserContext()
);

String message = expression.getValue(context, String.class);
~~~

Ở đây id và customer.name được đọc từ root object order. Nếu muốn tham chiếu object đã đăng ký bằng biến, dùng dấu #:

~~~text
Order #{#order.id} for #{#order.customer.name} is ready.
~~~

Property không có tiền tố # được đọc từ evaluation object hiện tại; variable có tiền tố # được tra cứu trong EvaluationContext.

Nếu property trung gian có thể null, dùng safe navigation ở từng bước phù hợp:

~~~text
Hello #{#order?.customer?.name ?: 'customer'}!
~~~

Safe navigation bảo vệ việc truy cập trên tham chiếu null; Elvis cung cấp giá trị thay thế. Nó không sửa dữ liệu hoặc tạo object còn thiếu.

## 6. Nhiều đoạn SpEL trong cùng template

Một template có thể chứa nhiều đoạn biểu thức:

~~~text
Customer #{#customer.name} placed order #{#order.id} for #{#order.total}.
~~~

Mỗi đoạn được đánh giá trong cùng EvaluationContext. Có thể kết hợp property, variable, toán tử số học và điều kiện:

~~~text
Subtotal: #{#order.subtotal}
Tax: #{#order.subtotal * #taxRate}
Total: #{#order.subtotal * (1 + #taxRate)}
~~~

Ví dụ dùng toán tử điều kiện:

~~~text
Payment: #{#order.paid ? 'received' : 'pending'}
~~~

Mỗi phần biểu thức được đánh giá rồi chuyển thành nội dung trong chuỗi kết quả. Phần literal giữa các đoạn được giữ theo đúng thứ tự. Hãy giữ từng đoạn SpEL ngắn và dễ kiểm tra.

## 7. Template trong annotation @Value

Trong ứng dụng Spring, @Value có thể inject giá trị vào field, constructor hoặc setter.

Ví dụ inject một giá trị biểu thức:

~~~java
@Component
public class RuntimeInfo {

    private final String region;

    public RuntimeInfo(
            @Value("#{systemProperties['user.region']}")
            String region) {
        this.region = region;
    }
}
~~~

Có thể dùng biểu thức trong một chuỗi có văn bản literal:

~~~java
@Component
public class GreetingConfig {

    private final String greeting;

    public GreetingConfig(
            @Value("Welcome, #{systemProperties['user.name']}!")
            String greeting) {
        this.greeting = greeting;
    }
}
~~~

Spring xử lý chuỗi thông qua cơ chế phân giải embedded value và bean expression của container. Biểu thức được đánh giá khi Spring tạo và inject bean theo lifecycle tương ứng.

@Value chỉ hoạt động khi object được Spring quản lý và các post-processor cần thiết đã được đăng ký. Nếu tự tạo object bằng new trong Java, annotation không tự được xử lý.

Giá trị inject thường được xác định trong quá trình khởi tạo bean. Nếu cần tạo message mới cho từng request hoặc người nhận, hãy dùng service render template với context riêng thay vì coi field @Value là message động theo từng request.

## 8. Template trong XML hoặc bean definition

SpEL có thể xuất hiện trong giá trị cấu hình bean, ví dụ constructor argument:

~~~xml
<bean id="messageProvider" class="com.example.MessageProvider">
    <constructor-arg
        value="Welcome, #{systemProperties['user.name']}!" />
</bean>
~~~

Spring bean expression resolver có thể đánh giá đoạn SpEL trong giá trị bean definition. Văn bản literal còn lại được giữ trong chuỗi kết quả.

Có thể dùng biểu thức để tính giá trị cấu hình:

~~~xml
<property name="timeoutSeconds" value="#{30 * 2}" />
~~~

Khi viết XML, hãy chú ý quy tắc escape của XML bên ngoài SpEL. Ví dụ ký tự & trong attribute cần được viết theo cú pháp XML hợp lệ. Dấu nháy trong biểu thức nên được chọn sao cho không xung đột với dấu nháy bao quanh attribute.

## 9. Phân biệt placeholder ${...} với SpEL #{...}

Spring dùng hai cú pháp thường gặp nhưng có mục đích khác nhau:

- `${...}` là placeholder để lấy giá trị từ property source, chẳng hạn application.properties, environment hoặc cấu hình bên ngoài.
- `#{...}` là biểu thức SpEL được đánh giá trong EvaluationContext.

Ví dụ placeholder:

~~~java
@Value("${app.mail.sender}")
private String sender;
~~~

Spring lấy giá trị cấu hình có tên app.mail.sender.

Ví dụ SpEL:

~~~java
@Value("#{systemProperties['user.name']}")
private String userName;
~~~

Spring đánh giá biểu thức truy cập system property.

Có thể kết hợp placeholder và SpEL khi cơ chế embedded value resolution được cấu hình phù hợp:

~~~java
@Value("#{${app.tax-rate} * 100}")
private double taxPercent;
~~~

Nếu app.tax-rate có giá trị 0.08, placeholder được thay bằng 0.08 rồi phần SpEL tính kết quả 8.0.

Không nhầm lẫn hai cú pháp: placeholder thay thế giá trị cấu hình; SpEL thực hiện biểu thức. Placeholder không tự cung cấp toán tử, method invocation hoặc khả năng truy cập object như SpEL.

## 10. TemplateParserContext với delimiter tùy chỉnh

Nếu văn bản thường xuyên chứa chuỗi `#{` và `}` theo nghĩa literal, có thể chọn delimiter khác.

Ví dụ dùng `[[` và `]]`:

~~~java
ParserContext customTemplateContext =
    new TemplateParserContext("[[", "]]");

Expression expression = parser.parseExpression(
    "Welcome [[#name]]!",
    customTemplateContext
);
~~~

Khi đánh giá, SpEL chỉ coi phần nằm giữa [[ và ]] là expression. Các delimiter mặc định #{ và } trong nội dung sẽ được giữ như văn bản nếu chúng không phải delimiter của ParserContext này.

Custom delimiter hữu ích khi template có cú pháp riêng của hệ thống hoặc nội dung thường chứa dấu ngoặc nhọn. Hãy chọn prefix và suffix ít xuất hiện trong văn bản tự nhiên, tài liệu hoặc dữ liệu người dùng.

ParserContext chỉ điều khiển cách parser phân tách template. Nó không làm giảm quyền của biểu thức và không thay đổi cách EvaluationContext phân giải property, method, bean hoặc function.

## 11. Delimiter xuất hiện trong nội dung literal

Delimiter của template được dùng để nhận diện đoạn SpEL. Nếu message cần hiển thị chính xác một chuỗi giống prefix hoặc suffix, hãy cân nhắc:

- Dùng custom delimiter ít xung đột hơn.
- Tách phần literal đặc biệt và ghép vào message ở Java.
- Tránh tạo template bằng cách nối dữ liệu tùy ý vào chuỗi expression.
- Kiểm thử với đúng parser context và phiên bản Spring đang chạy.

Không nên giả định mọi ký tự delimiter đều có một quy tắc escape giống nhau trong mọi phiên bản hoặc parser context. Nếu ứng dụng cần cơ chế escape riêng, hãy xác định và kiểm thử quy tắc đó thay vì tự thêm dấu gạch chéo ngược theo phỏng đoán.

Đối với template phức tạp có nhiều cú pháp lồng nhau, một bộ dựng message trong Java hoặc template engine chuyên dụng có thể dễ bảo trì hơn.

## 12. Giá trị null và kết quả biểu thức

Một đoạn SpEL trong template có thể trả về null. Hãy quyết định rõ message cần thể hiện trường hợp đó như thế nào.

Ví dụ dùng Elvis:

~~~text
Hello #{#customer?.name ?: 'Guest'}!
~~~

Nếu customer hoặc name là null, message sử dụng Guest.

Nếu null có ý nghĩa riêng, dùng điều kiện tường minh:

~~~text
Status: #{#order.status == null ? 'not assigned' : #order.status}
~~~

Cũng cần xử lý property trung gian null:

~~~text
Delivery city: #{#order?.deliveryAddress?.city ?: 'not provided'}
~~~

Safe navigation chỉ bảo vệ những bước được đặt ?. . Nếu property hoặc getter phát sinh lỗi vì nguyên nhân khác, template vẫn có thể thất bại.

Nếu template dùng nhiều giá trị bắt buộc, hãy xác thực context trước khi đánh giá. Một message không nên âm thầm che giấu dữ liệu thiếu nếu dữ liệu đó là điều kiện để gửi thông báo chính xác.

## 13. Kiểu kết quả và định dạng hiển thị

Template expression thường tạo ra một chuỗi hoàn chỉnh vì văn bản literal được ghép với các giá trị động. Dù biểu thức con trả về số, ngày hoặc object, ứng dụng vẫn cần quyết định cách hiển thị chúng.

Ví dụ:

~~~text
Total: #{#order.total}
Created: #{#order.createdAt}
~~~

Kết quả hiển thị phụ thuộc biểu diễn chuỗi của giá trị. Với tiền tệ, ngày giờ hoặc số thập phân, không nên dựa vào toString() mặc định nếu message cần định dạng theo locale.

Có thể chuẩn bị chuỗi đã định dạng trong Java rồi truyền qua variable:

~~~java
context.setVariable("formattedTotal", moneyFormatter.format(order.getTotal()));
context.setVariable("formattedDate", dateFormatter.format(order.getCreatedAt()));
~~~

Template:

~~~text
Total: #{#formattedTotal}
Created: #{#formattedDate}
~~~

Cách này tách logic định dạng khỏi cấu trúc câu và giúp thống nhất locale, timezone, đơn vị tiền và quy tắc làm tròn.

## 14. Parse một lần, đánh giá nhiều lần

Nếu cùng một template được dùng nhiều lần, hãy parse một lần rồi tái sử dụng Expression:

~~~java
ExpressionParser parser = new SpelExpressionParser();

Expression messageTemplate = parser.parseExpression(
    "Hello #{#name}, order #{#orderId} is ready.",
    new TemplateParserContext()
);
~~~

Mỗi lần tạo message, cung cấp dữ liệu trong context phù hợp:

~~~java
StandardEvaluationContext context =
    new StandardEvaluationContext();

context.setVariable("name", "An");
context.setVariable("orderId", "ORD-1001");

String first = messageTemplate.getValue(context, String.class);

context.setVariable("name", "Binh");
context.setVariable("orderId", "ORD-1002");

String second = messageTemplate.getValue(context, String.class);
~~~

Expression đã parse có thể được tái sử dụng với các giá trị khác nhau. Tuy nhiên, không nên chia sẻ một EvaluationContext có biến thay đổi giữa nhiều request hoặc nhiều luồng nếu không có cơ chế cô lập phù hợp.

Một cách an toàn là giữ template Expression dùng chung nhưng tạo context riêng cho mỗi lần xử lý hoặc đơn vị công việc.

## 15. Phân biệt ParserContext và EvaluationContext

Hai loại context này có vai trò khác nhau:

| Thành phần | Trách nhiệm | Ví dụ |
|---|---|---|
| ParserContext | Cho parser biết chuỗi là template và xác định delimiter | TemplateParserContext() |
| EvaluationContext | Cung cấp root object, variable và quyền truy cập khi chạy | StandardEvaluationContext |
| TemplateParserContext | ParserContext triển khai delimiter cho template | Prefix `#{`, suffix `}` |
| SimpleEvaluationContext | EvaluationContext giới hạn khả năng truy cập | Read-only data binding |

Có thể parse template bằng TemplateParserContext rồi đánh giá bằng StandardEvaluationContext hoặc SimpleEvaluationContext phù hợp.

Đổi ParserContext không làm expression an toàn hơn. Muốn giới hạn quyền, phải chọn EvaluationContext và các accessor/resolver phù hợp.

Ngược lại, chọn SimpleEvaluationContext không tự biến một chuỗi văn bản thành template. Parser vẫn cần nhận ParserContext dạng template khi chuỗi có cả literal text và các đoạn SpEL.

## 16. Dùng SimpleEvaluationContext cho template chỉ cần đọc dữ liệu

Nếu message chỉ cần đọc một số property đơn giản, có thể dùng context chỉ đọc:

~~~java
EvaluationContext context =
    SimpleEvaluationContext.forReadOnlyDataBinding().build();

Expression expression = parser.parseExpression(
    "Hello #{name}!",
    new TemplateParserContext()
);

String message =
    expression.getValue(context, customer, String.class);
~~~

Cách này giới hạn khả năng truy cập property theo data binding read-only. Nó phù hợp với template cần đọc dữ liệu từ một object được kiểm soát.

Nếu template cần gọi method, tham chiếu bean, type hoặc constructor, SimpleEvaluationContext có thể không hỗ trợ khả năng đó theo cấu hình hiện tại. Hãy chỉ bật tính năng thực sự cần và cân nhắc dùng Java để chuẩn bị dữ liệu trước khi render.

Với template đến từ nguồn không đáng tin cậy, không nên dùng StandardEvaluationContext mặc định có quyền rộng rồi cho phép người dùng viết tùy ý SpEL.

## 17. Template expression trong message và email

Một message template thường có hai phần:

- Cấu trúc câu chữ do ứng dụng kiểm soát.
- Dữ liệu động lấy từ request, domain object hoặc context.

Ví dụ:

~~~text
Hello #{#customerName},

Your order #{#orderId} has been shipped.
Expected delivery: #{#deliveryDate}.
~~~

Có thể dùng cùng một template cho nhiều người nhận bằng cách thay đổi variables trong EvaluationContext.

Nếu tạo HTML email, cần xử lý output encoding. SpEL chỉ đánh giá biểu thức và ghép chuỗi; nó không tự escape HTML, JavaScript, URL hoặc nội dung theo ngữ cảnh đầu ra.

Nếu customerName chứa ký tự < hoặc dấu nháy, việc chèn trực tiếp vào HTML có thể làm hỏng markup hoặc tạo lỗ hổng injection. Hãy encode dữ liệu theo đúng ngữ cảnh HTML text, attribute hoặc URL bằng thư viện phù hợp trước khi đưa vào nội dung cuối cùng.

Không dùng SpEL template làm cơ chế thay thế cho template engine có auto-escaping khi ứng dụng cần render HTML phức tạp.

## 18. Bảo mật khi template đến từ nguồn bên ngoài

Template có thể chứa biểu thức SpEL, vì vậy người có quyền sửa template có thể tác động đến những gì được đánh giá.

Rủi ro phụ thuộc EvaluationContext. Với context rộng, biểu thức có thể truy cập property, gọi method, tham chiếu bean hoặc sử dụng các khả năng khác nếu được cấu hình.

Nguyên tắc an toàn:

1. Chỉ cho phép người có quyền quản lý template thay đổi phần SpEL.
2. Xem template là mã có thể thực thi, không phải văn bản thuần.
3. Truyền dữ liệu qua variables thay vì nối dữ liệu người dùng vào chuỗi expression.
4. Dùng root object chuyên biệt chỉ chứa dữ liệu cần hiển thị.
5. Ưu tiên EvaluationContext chỉ đọc và giới hạn accessor.
6. Không cung cấp service có tác dụng phụ nếu template chỉ cần đọc dữ liệu.
7. Không đăng ký bean, function hoặc method resolver rộng hơn nhu cầu.
8. Encode kết quả theo ngữ cảnh đầu ra như HTML hoặc email.
9. Giới hạn độ dài template và số lượng biểu thức nếu người dùng có thể tạo nội dung.
10. Kiểm thử template trước khi đưa vào sử dụng.

ParserContext chỉ phân tách literal text và expression. Nó không phải sandbox và không thay thế việc kiểm soát quyền trong EvaluationContext.

## 19. Lỗi parse và lỗi đánh giá

Có hai nhóm lỗi cần phân biệt.

**Lỗi parse** xảy ra khi cấu trúc template hoặc biểu thức không hợp lệ:

- Thiếu suffix delimiter.
- Biểu thức bên trong có cú pháp sai.
- Dùng sai ParserContext.
- Literal hoặc dấu nháy trong đoạn SpEL không cân bằng.

**Lỗi đánh giá** xảy ra khi parse thành công nhưng không thể chạy với dữ liệu hiện tại:

- Variable chưa được đăng ký.
- Root object hoặc property trung gian null.
- Property không tồn tại.
- Method không được phép gọi.
- Bean reference không có resolver hoặc tên bean sai.
- Chuyển đổi kiểu thất bại.
- Method hoặc getter ném exception.

Hãy parse template khi nạp cấu hình hoặc khi lưu template để phát hiện lỗi cú pháp sớm. Khi render, xử lý lỗi đánh giá theo dữ liệu thực tế và ghi nhận template identifier cùng nguyên nhân, tránh ghi dữ liệu cá nhân hoặc bí mật vào log.

Không nên bắt mọi lỗi rồi thay toàn bộ message bằng chuỗi rỗng mà không ghi nhận. Điều đó có thể làm mất thông báo quan trọng mà không có dấu hiệu để điều tra.

## 20. Ví dụ tổng hợp: template trong cấu hình ứng dụng

Giả sử application.properties chứa:

~~~properties
app.tax-rate=0.08
app.message-prefix=Invoice
~~~

Có thể inject các giá trị:

~~~java
@Component
public class InvoiceMessageConfig {

    private final double taxPercent;
    private final String prefix;

    public InvoiceMessageConfig(
            @Value("#{${app.tax-rate} * 100}") double taxPercent,
            @Value("${app.message-prefix}") String prefix) {
        this.taxPercent = taxPercent;
        this.prefix = prefix;
    }
}
~~~

Trong ví dụ:

- `${app.tax-rate}` lấy giá trị từ property source.
- `#{...}` yêu cầu SpEL tính toán trên giá trị đã được thay thế.
- `${app.message-prefix}` lấy chuỗi cấu hình thuần, không cần SpEL.

Một message template riêng có thể dùng prefix đã inject:

~~~text
#{#prefix} #{#invoiceNumber}: total #{#formattedTotal}
~~~

Ứng dụng đăng ký prefix, invoiceNumber và formattedTotal trong context trước khi render. Cách này tách cấu hình ứng dụng, biểu thức tính toán và dữ liệu của từng hóa đơn.

## 21. Kiểm thử template expression

Khi kiểm thử, hãy bao gồm:

| Trường hợp | Điều cần xác nhận |
|---|---|
| Chỉ có literal text | Nội dung được giữ nguyên |
| Một đoạn SpEL | Giá trị được chèn đúng vị trí |
| Nhiều đoạn SpEL | Tất cả được đánh giá theo thứ tự |
| Variable | Đọc đúng giá trị từ context |
| Root property | Đọc đúng property của object gốc |
| Property lồng nhau | Xử lý đúng object trung gian |
| Null | Dùng safe navigation hoặc default theo yêu cầu |
| Custom delimiter | Chỉ delimiter đã chọn được nhận diện |
| Literal chứa delimiter mặc định | Không bị hiểu nhầm ngoài ý muốn |
| Placeholder ${...} | Được phân giải bởi property resolver |
| SpEL #{...} | Được parser/evaluator xử lý |
| Parse sai | Phát hiện trước khi render |
| Evaluation sai | Báo lỗi theo dữ liệu và quyền hiện tại |
| HTML output | Dữ liệu được encode đúng ngữ cảnh |
| Nhiều request đồng thời | Context không rò rỉ biến giữa các request |

Nên kiểm thử cả kết quả cuối cùng lẫn cách cấu hình ParserContext và EvaluationContext. Một template có thể parse thành công nhưng vẫn thất bại khi thiếu biến hoặc quyền truy cập cần thiết.

## 22. Ghi nhớ

Template expression cho phép trộn văn bản literal với các đoạn SpEL được đặt giữa delimiter. Với cấu hình mặc định, dùng TemplateParserContext để nhận diện `#{...}`. Khi parse chuỗi message có văn bản thông thường và biểu thức, hãy truyền ParserContext dạng template thay vì coi toàn bộ câu là một biểu thức SpEL.

TemplateParserContext quyết định cách phân tách chuỗi; EvaluationContext cung cấp root object, variables và quyền truy cập khi đánh giá. Có thể dùng template trong message Java, @Value và bean definition XML. Placeholder `${...}` lấy giá trị cấu hình, còn `#{...}` thực hiện biểu thức SpEL; hai cú pháp có thể phối hợp khi cơ chế phân giải embedded value và expression của Spring được cấu hình phù hợp.

Hãy dùng variables cho dữ liệu động, giữ template có cấu trúc rõ ràng, xử lý null và lỗi riêng biệt, chọn delimiter ít xung đột và encode kết quả theo ngữ cảnh đầu ra. ParserContext không phải sandbox; template từ nguồn bên ngoài cần EvaluationContext có quyền tối thiểu và dữ liệu được kiểm soát.

## Tài liệu tham khảo

- [Spring Framework Reference — Language Reference](https://docs.spring.io/spring-framework/reference/core/expressions/language-ref.html)
- [Spring Framework Reference — Evaluation](https://docs.spring.io/spring-framework/reference/core/expressions/evaluation.html)
- [TemplateParserContext Javadoc](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/expression/common/TemplateParserContext.html)
- [ParserContext Javadoc](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/expression/ParserContext.html)
- [Spring @Value Annotation Reference](https://docs.spring.io/spring-framework/reference/core/beans/annotation-config/value-annotations.html)