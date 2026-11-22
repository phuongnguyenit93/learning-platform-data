# Chuỗi kết quả khi có nhiều đoạn expression

Trong Spring Expression Language (SpEL), **template expression** cho phép kết hợp văn bản cố định với nhiều đoạn SpEL nằm bên trong cùng một chuỗi. Khi đánh giá, Spring giữ nguyên phần văn bản literal, chạy từng đoạn expression và ghép các kết quả thành một chuỗi hoàn chỉnh.

Ví dụ:

~~~text
Order #{#order.id} của khách hàng #{#customer.name} có tổng tiền #{#order.total}.
~~~

Kết quả có thể là:

~~~text
Order ORD-1024 của khách hàng Linh có tổng tiền 250.00.
~~~

Cách này phù hợp khi cần tạo nhãn, thông báo, mô tả, nội dung cấu hình hoặc chuỗi hiển thị có nhiều giá trị động. Thay vì nối chuỗi bằng nhiều toán tử cộng trong Java hoặc viết một expression dài, có thể đặt các phần động ngay tại vị trí chúng xuất hiện trong văn bản.

## 1. Template expression là gì?

Một template expression gồm hai loại đoạn:

- **Literal text:** văn bản cố định nằm ngoài delimiter.
- **Embedded expression:** đoạn SpEL nằm giữa prefix và suffix được ParserContext xác định.

Với cấu hình mặc định, delimiter là **#{** và **}**:

~~~text
Xin chào #{#user.name}, hôm nay là #{#today}.
~~~

Phần literal gồm "Xin chào ", ", hôm nay là " và ".". Hai phần nằm trong delimiter là expression #user.name và #today.

Khi gọi getValue(), SpEL đánh giá các expression bên trong rồi ghép kết quả với literal text thành một String.

Một template có thể chứa một, nhiều hoặc không có đoạn expression. Nếu không có phần động, kết quả chỉ là nội dung literal. Nếu có nhiều đoạn, từng đoạn được đánh giá trong quá trình tạo chuỗi kết quả.

## 2. ParserContext và TemplateParserContext

Để parse một chuỗi template, cần truyền **ParserContext** cho ExpressionParser. ParserContext cho parser biết chuỗi đầu vào là một template và delimiter nào đánh dấu phần expression.

Spring cung cấp implementation **TemplateParserContext**:

~~~java
import org.springframework.expression.Expression;
import org.springframework.expression.ExpressionParser;
import org.springframework.expression.common.TemplateParserContext;
import org.springframework.expression.spel.standard.SpelExpressionParser;

ExpressionParser parser = new SpelExpressionParser();

Expression expression = parser.parseExpression(
        "Hello #{'Spring'}!",
        new TemplateParserContext()
);
~~~

Constructor không tham số của TemplateParserContext dùng prefix **#{** và suffix **}**.

Khi gọi:

~~~java
expression.getValue(String.class);
~~~

kết quả là:

~~~text
Hello Spring!
~~~

Điểm quan trọng là phải dùng overload parseExpression(expressionString, parserContext). Nếu chỉ gọi parseExpression(expressionString), parser sẽ xem toàn bộ chuỗi là một expression SpEL thông thường, không tự hiểu phần văn bản bên ngoài #{...} là literal của template.

### 2.1. ParserContext chỉ điều khiển cách parse

Cần phân biệt hai thành phần:

- **ParserContext** xác định chuỗi có phải template hay không và delimiter nào bao quanh expression.
- **EvaluationContext** cung cấp root object, variables, functions, property accessors, method resolvers và bean resolver dùng khi expression được đánh giá.

TemplateParserContext không tự cung cấp biến hoặc bean. Nếu template tham chiếu #order hay @priceFormatter, context lúc getValue() phải cung cấp dữ liệu và khả năng phân giải tương ứng.

## 3. Tạo chuỗi có nhiều đoạn expression

Ví dụ có ba phần động trong một câu:

~~~java
ExpressionParser parser = new SpelExpressionParser();

StandardEvaluationContext context =
        new StandardEvaluationContext();

context.setVariable("orderId", "ORD-1024");
context.setVariable("customerName", "Linh");
context.setVariable("total", new BigDecimal("250.00"));

Expression expression = parser.parseExpression(
        "Order #{#orderId} của #{#customerName} có tổng tiền #{#total}.",
        new TemplateParserContext()
);

String message = expression.getValue(context, String.class);
~~~

Kết quả:

~~~text
Order ORD-1024 của Linh có tổng tiền 250.00.
~~~

Mỗi đoạn #{...} là một expression riêng được parse trong lúc phân tích template. Khi evaluate, các đoạn này cùng sử dụng EvaluationContext được truyền vào.

Có thể trộn literal, property access, variable, phép tính và method call:

~~~text
Xin chào #{#customer.name}, đơn hàng #{#order.id}
có #{#order.items.size()} sản phẩm và tổng tiền #{#order.total * 1.08}.
~~~

Template giữ phần câu chữ, còn SpEL xử lý các giá trị động.

## 4. Dùng root object và variable trong template

Template expression có thể dùng root object theo cách giống expression SpEL thông thường.

Ví dụ:

~~~java
Order order = ...;

Expression expression = parser.parseExpression(
        "Đơn hàng #{id} của khách #{customer.name}",
        new TemplateParserContext()
);

String result = expression.getValue(order, String.class);
~~~

Ở đây id và customer.name được đọc từ root object order.

Nếu dữ liệu được đăng ký dưới dạng variable, dùng dấu #:

~~~java
StandardEvaluationContext context =
        new StandardEvaluationContext();

context.setVariable("order", order);
context.setVariable("locale", "vi-VN");

Expression expression = parser.parseExpression(
        "Mã đơn: #{#order.id}; ngôn ngữ: #{#locale}",
        new TemplateParserContext()
);

String result = expression.getValue(context, String.class);
~~~

Không nên nhầm property của root object với variable:

- id là property của root object khi root là Order.
- #order.id truy cập variable order rồi đọc property id.
- @orderService là bean reference và cần BeanResolver.

## 5. Dùng phép tính và method trong từng đoạn

Mỗi embedded expression có thể chứa các toán tử và cú pháp SpEL thông thường, miễn là EvaluationContext hỗ trợ thao tác đó.

Ví dụ tính thành tiền sau thuế:

~~~text
Tạm tính: #{#order.subtotal}
Thuế: #{#order.subtotal * #taxRate}
Tổng cộng: #{#order.subtotal * (1 + #taxRate)}
~~~

Có thể gọi method trên object:

~~~text
Khách hàng: #{#customer.getDisplayName()}
~~~

Hoặc dùng property style nếu class cung cấp getter tương ứng:

~~~text
Khách hàng: #{#customer.displayName}
~~~

Nếu method có thể thực hiện side effect hoặc gọi hệ thống bên ngoài, mỗi lần template được evaluate có thể thực hiện hành động đó. Với chuỗi hiển thị, nên ưu tiên expression đọc dữ liệu hoặc gọi method thuần, có kết quả ổn định.

### 5.1. Gọi function đã đăng ký

Nếu EvaluationContext có function normalizeCode:

~~~text
Mã tra cứu: #{#normalizeCode(#rawCode)}
~~~

Function được gọi trong lúc evaluate template, giống như khi nó được dùng trong expression độc lập.

### 5.2. Gọi method của Spring bean

Nếu context có BeanResolver phù hợp:

~~~text
Tổng tiền định dạng: #{@priceFormatter.format(#order.total)}
~~~

Expression tham chiếu bean priceFormatter rồi gọi method format. Nếu tự tạo StandardEvaluationContext, cần cấu hình BeanFactoryResolver; template parser không tự tìm bean trong ApplicationContext.

## 6. Tùy chỉnh delimiter

Không bắt buộc phải dùng #{ và }. Có thể tạo TemplateParserContext với prefix và suffix riêng:

~~~java
ParserContext parserContext =
        new TemplateParserContext("{{", "}}");

Expression expression = parser.parseExpression(
        "Hello {{#user.name}}!",
        parserContext
);
~~~

Template trên dùng {{ và }} để đánh dấu phần expression. Khi evaluate với context có variable user, kết quả là chuỗi chào người dùng.

Cú pháp constructor:

~~~java
new TemplateParserContext(expressionPrefix, expressionSuffix)
~~~

Prefix và suffix phải được chọn thành một cặp phù hợp với nội dung template. Ví dụ khác:

~~~java
ParserContext parserContext =
        new TemplateParserContext("[[", "]]");

Expression expression = parser.parseExpression(
        "Order [[#order.id]] is ready.",
        parserContext
);
~~~

Tùy chỉnh delimiter hữu ích khi chuỗi literal thường xuyên chứa ký hiệu #{ hoặc khi một hệ thống bên ngoài đã dùng cú pháp riêng. Hãy chọn delimiter không xung đột với văn bản cố định để parser nhận diện ranh giới rõ ràng.

### 6.1. ParserContext tự triển khai

ParserContext là interface. Nếu cần quy tắc template đặc biệt, ứng dụng có thể triển khai interface này để cung cấp:

- isTemplate(): cho biết đầu vào là template.
- getExpressionPrefix(): trả về prefix mở đầu embedded expression.
- getExpressionSuffix(): trả về suffix kết thúc embedded expression.

Trong trường hợp thông thường, TemplateParserContext đã đáp ứng nhu cầu và không cần tự triển khai.

## 7. Phân biệt template expression với nối chuỗi bằng toán tử cộng

Có thể tạo cùng một chuỗi bằng toán tử cộng:

~~~text
'Order ' + #order.id + ' của ' + #customer.name
~~~

Hoặc bằng template:

~~~text
Order #{#order.id} của #{#customer.name}
~~~

Hai cách đều có thể tạo chuỗi kết quả, nhưng phù hợp với cách viết khác nhau:

| Tiêu chí | Template expression | Toán tử cộng |
| --- | --- | --- |
| Văn bản cố định | Viết trực tiếp bên ngoài delimiter | Phải đặt trong string literal |
| Giá trị động | Đặt tại vị trí xuất hiện trong câu | Nối lần lượt bằng toán tử cộng |
| Nhiều đoạn động | Dễ quan sát bố cục câu hoàn chỉnh | Expression có thể dài khi nhiều đoạn |
| Parser | Cần ParserContext template | Parse như expression thông thường |
| Phù hợp | Chuỗi có nhiều phần literal và dynamic | Phép nối ngắn hoặc biểu thức tính toán |

Nếu chỉ nối hai giá trị, toán tử cộng có thể đơn giản hơn. Nếu chuỗi có nhiều câu chữ cố định xen kẽ các giá trị, template giúp nội dung dễ đọc và chỉnh sửa hơn.

## 8. Template expression trong @Value

Spring hỗ trợ SpEL trong annotation @Value. Có thể kết hợp literal text với các phần expression:

~~~java
@Component
class RuntimeDescription {

    @Value("Application region: #{systemProperties['app.region']}")
    private String description;
}
~~~

Trong quá trình xử lý @Value, Spring đánh giá expression theo cơ chế tích hợp của container và tạo chuỗi kết quả.

Một ví dụ khác:

~~~java
@Value("Running on #{T(java.lang.System).getProperty('os.name')}")
private String runtimeLabel;
~~~

Khi dùng @Value, không cần tự gọi parseExpression() hoặc tạo TemplateParserContext. Spring xử lý cú pháp annotation theo quy tắc embedded value và expression resolver của nó.

Cần phân biệt property placeholder và SpEL:

~~~java
@Value("DOLLAR_OPEN{app.name:Spring Application}")
private String applicationName;
~~~

Placeholder DOLLAR_OPEN{...} đọc giá trị cấu hình và có thể cung cấp default. SpEL #{...} đánh giá biểu thức. Hai cơ chế có thể được kết hợp trong cấu hình Spring, nhưng mỗi cơ chế có mục đích riêng.

## 9. Thời điểm đánh giá và tái sử dụng Expression

parseExpression() tạo đối tượng Expression từ chuỗi template. Việc phân tích cú pháp không có nghĩa các giá trị động đã được cố định tại thời điểm parse.

Các embedded expression được đánh giá khi gọi getValue():

~~~java
Expression expression = parser.parseExpression(
        "Hello #{#userName}!",
        new TemplateParserContext()
);

StandardEvaluationContext context =
        new StandardEvaluationContext();

context.setVariable("userName", "An");

String first = expression.getValue(context, String.class);

context.setVariable("userName", "Binh");

String second = expression.getValue(context, String.class);
~~~

Lần evaluate đầu tạo Hello An!, lần thứ hai tạo Hello Binh!. Có thể parse template một lần rồi tái sử dụng Expression với nhiều EvaluationContext hoặc nhiều bộ dữ liệu đầu vào.

Điều này phù hợp khi cùng một mẫu thông báo được dùng cho nhiều đơn hàng hoặc người dùng. Hãy tạo context riêng cho từng đơn vị xử lý nếu các lần evaluate cần variable khác nhau, tránh chia sẻ context mutable giữa các request đồng thời.

## 10. Định dạng giá trị trong chuỗi kết quả

Template expression ghép kết quả của các embedded expression vào văn bản. Khi expression trả về object, giá trị được đưa vào chuỗi theo cách biểu diễn String của kết quả.

Ví dụ với BigDecimal:

~~~text
Tổng tiền: #{#order.total}
~~~

Kết quả có thể hiển thị 250.00 theo biểu diễn mặc định của BigDecimal. Tuy nhiên, biểu diễn mặc định không nhất thiết đáp ứng quy tắc định dạng của giao diện hoặc locale.

Nếu cần định dạng tiền tệ, ngày giờ hoặc số thập phân theo locale, hãy gọi một formatter chuyên dụng:

~~~text
Tổng tiền: #{@priceFormatter.format(#order.total, #locale)}
Ngày tạo: #{@dateFormatter.format(#order.createdAt, #locale)}
~~~

Các bean formatter cần được phân giải trong EvaluationContext có BeanResolver. Có thể dùng function đã đăng ký nếu việc định dạng là một phép xử lý tĩnh, độc lập.

Không nên đặt quy tắc định dạng phức tạp vào nhiều đoạn SpEL lặp lại. Một formatter có tên rõ ràng giúp chuẩn hóa kết quả và dễ kiểm thử hơn.

## 11. Xử lý null và lỗi trong embedded expression

Template chỉ ghép kết quả; nó không tự xác thực toàn bộ dữ liệu đầu vào.

Ví dụ:

~~~text
Khách hàng: #{#order.customer.name}
~~~

Nếu order hoặc customer là null, việc truy cập property có thể thất bại. Hãy dùng safe navigation tại những bước có thể null:

~~~text
Khách hàng: #{#order?.customer?.name}
~~~

Có thể cung cấp giá trị mặc định bằng Elvis:

~~~text
Khách hàng: #{#order?.customer?.name ?: 'Khách lẻ'}
~~~

Nếu embedded expression gọi method và method ném exception, việc đánh giá toàn bộ template có thể thất bại. Các đoạn literal đã có không làm cho lỗi đó tự biến thành chuỗi mặc định.

Nên xử lý null và lỗi theo đúng quy tắc nghiệp vụ. Nếu một giá trị bắt buộc phải có, hãy xác thực dữ liệu trước hoặc để lỗi được báo rõ ràng thay vì che giấu bằng một chuỗi thay thế chung.

## 12. Thứ tự đánh giá và tác động phụ

Các phần literal được giữ nguyên; các embedded expression được đánh giá để tạo chuỗi kết quả theo thứ tự xuất hiện trong template.

Ví dụ:

~~~text
#{#firstStep()} - #{#secondStep()}
~~~

Nếu hai function có side effect, thứ tự gọi có thể ảnh hưởng trạng thái ứng dụng. Đây là lý do không nên dùng template expression để điều phối các thao tác nghiệp vụ.

Một template hiển thị nên tập trung vào việc đọc và định dạng dữ liệu. Hãy thực hiện cập nhật trạng thái, gửi thông báo hoặc ghi dữ liệu trong service Java có luồng xử lý rõ ràng, rồi mới tạo chuỗi từ kết quả.

Ngoài ra, mỗi lần gọi getValue() sẽ đánh giá lại các phần expression. Nếu template được dùng nhiều lần, method bên trong template cũng có thể được gọi nhiều lần. Không nên giả định kết quả động đã được cache chỉ vì Expression được parse một lần.

## 13. Lỗi thường gặp khi parse template

### 13.1. Quên truyền ParserContext

Sai:

~~~java
parser.parseExpression("Hello #{#user.name}!");
~~~

Cách này yêu cầu parser hiểu toàn bộ chuỗi là một expression thông thường.

Đúng:

~~~java
parser.parseExpression(
        "Hello #{#user.name}!",
        new TemplateParserContext()
);
~~~

### 13.2. Thiếu suffix hoặc delimiter không cân bằng

Nếu template có prefix mở đầu nhưng không có suffix tương ứng, parser không thể xác định ranh giới embedded expression và có thể ném ParseException.

Ví dụ không hoàn chỉnh:

~~~text
Hello #{#user.name
~~~

Hãy kiểm tra từng cặp prefix/suffix và bảo đảm nội dung expression nằm bên trong delimiter đã chọn.

### 13.3. Dùng nhầm delimiter

Nếu tạo TemplateParserContext với {{ và }}, nhưng template vẫn dùng #{...}, phần đó không được xem là embedded expression theo parser context mới.

ParserContext và chuỗi template phải sử dụng cùng một cặp delimiter.

### 13.4. Nhầm cú pháp SpEL với placeholder cấu hình

Placeholder cấu hình của Spring và delimiter template SpEL có mục đích khác nhau. Trong cấu hình, ${...} thường dùng để lấy property; #{...} dùng để đánh giá SpEL.

Nếu một chuỗi chứa cả hai cơ chế, hãy kiểm tra thứ tự xử lý embedded value và expression ở đúng integration point, chẳng hạn @Value. Không nên thay delimiter tùy tiện vì có thể làm thay đổi ý nghĩa cấu hình.

### 13.5. Đưa dấu nháy không đúng vào expression

Literal String bên trong SpEL thường được đặt trong dấu nháy đơn:

~~~text
Hello #{'Spring Framework'}!
~~~

Nếu expression cần một chuỗi có dấu nháy đơn, phải escape theo cú pháp literal của SpEL. Hãy phân biệt dấu nháy dùng để bao literal với dấu nháy thuộc chính nội dung dữ liệu.

## 14. Template expression không thay thế một template engine

SpEL template expression phù hợp với việc ghép văn bản và giá trị động trong các cấu hình Spring. Nó không phải một template engine tổng quát cho tài liệu dài.

Nếu cần vòng lặp, điều kiện hiển thị phức tạp, layout, escaping HTML, localization hoặc quản lý template cho người viết nội dung, hãy cân nhắc một template engine chuyên dụng hoặc MessageSource.

Một số nguyên tắc lựa chọn:

- Dùng SpEL template cho chuỗi cấu hình ngắn, nhãn, thông báo đơn giản và giá trị được tạo trong Spring integration point.
- Dùng MessageSource khi cần quản lý thông điệp đa ngôn ngữ.
- Dùng template engine khi cần cấu trúc tài liệu, vòng lặp, điều kiện và escaping.
- Dùng Java service khi việc tạo nội dung chứa logic nghiệp vụ hoặc nhiều bước xử lý.

## 15. Kiểm thử template expression

Có thể kiểm tra nhiều đoạn expression bằng JUnit:

~~~java
class TemplateExpressionTest {

    private final ExpressionParser parser =
            new SpelExpressionParser();

    @Test
    void combinesLiteralAndMultipleExpressions() {
        StandardEvaluationContext context =
                new StandardEvaluationContext();

        context.setVariable("orderId", "ORD-1024");
        context.setVariable("customerName", "Linh");
        context.setVariable("total", new BigDecimal("250.00"));

        Expression expression = parser.parseExpression(
                "Order #{#orderId} của #{#customerName}: #{#total}",
                new TemplateParserContext()
        );

        String result = expression.getValue(context, String.class);

        assertEquals(
                "Order ORD-1024 của Linh: 250.00",
                result
        );
    }

    @Test
    void reusesExpressionWithDifferentContexts() {
        Expression expression = parser.parseExpression(
                "Hello #{#name}!",
                new TemplateParserContext()
        );

        StandardEvaluationContext first =
                new StandardEvaluationContext();
        first.setVariable("name", "An");

        StandardEvaluationContext second =
                new StandardEvaluationContext();
        second.setVariable("name", "Binh");

        assertEquals("Hello An!", expression.getValue(first, String.class));
        assertEquals("Hello Binh!", expression.getValue(second, String.class));
    }
}
~~~

Test đầu xác nhận literal text và nhiều embedded expression được ghép đúng. Test thứ hai xác nhận một Expression đã parse có thể được evaluate với các context khác nhau.

Nên bổ sung test cho custom delimiter, variable không tồn tại, property null, method ném exception và trường hợp template thiếu suffix nếu ứng dụng nhận template từ cấu hình bên ngoài.

## 16. Ghi nhớ nhanh

- Template expression kết hợp literal text và nhiều embedded SpEL expression trong một chuỗi.
- Delimiter mặc định của TemplateParserContext là **#{** và **}**.
- Parse template bằng **parseExpression(template, new TemplateParserContext())**.
- Mỗi đoạn embedded expression được đánh giá khi gọi getValue(); parse một lần không cố định giá trị động.
- Nhiều đoạn expression trong cùng template dùng chung EvaluationContext được truyền vào.
- Có thể dùng root property, variable, function và bean reference nếu context cung cấp quyền truy cập tương ứng.
- Tạo delimiter riêng bằng **new TemplateParserContext(prefix, suffix)** khi cần tránh xung đột với nội dung literal.
- ParserContext quyết định cách parse; EvaluationContext quyết định dữ liệu và quyền truy cập khi evaluate.
- Dùng safe navigation và Elvis khi dữ liệu trung gian có thể null.
- Dùng formatter chuyên dụng cho tiền tệ, ngày giờ và locale.
- Hạn chế side effect trong embedded expression vì mỗi lần getValue() sẽ đánh giá lại các đoạn động.
- Dùng template expression cho chuỗi ngắn; dùng MessageSource hoặc template engine cho nội dung cần localization và cấu trúc phức tạp.

## 17. Tài liệu tham khảo chính thức

- [Spring Framework — Language Reference and Template Expressions](https://docs.spring.io/spring-framework/reference/core/expressions.html)
- [Spring Framework — ExpressionParser Javadoc](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/expression/ExpressionParser.html)
- [Spring Framework — ParserContext Javadoc](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/expression/ParserContext.html)
- [Spring Framework — TemplateParserContext Javadoc](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/expression/common/TemplateParserContext.html)
- [Spring Framework — Expression and EvaluationContext](https://docs.spring.io/spring-framework/reference/core/expressions/evaluation.html)
