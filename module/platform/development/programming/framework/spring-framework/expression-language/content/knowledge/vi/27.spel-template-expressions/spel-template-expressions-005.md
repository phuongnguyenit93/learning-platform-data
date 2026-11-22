# Template không có expression và hành vi tương ứng

Trong Spring Expression Language (SpEL), template expression cho phép ghép văn bản tĩnh với kết quả của các biểu thức được đặt trong cặp dấu phân cách. Tuy nhiên, một template không bắt buộc phải chứa expression. Nếu chuỗi đầu vào không có vùng biểu thức, parser ở chế độ template xem toàn bộ nội dung là văn bản literal và kết quả đánh giá giữ nguyên nội dung đó.

Hành vi này hữu ích khi một nguồn cấu hình có thể chứa cả chuỗi tĩnh lẫn chuỗi động. Ứng dụng có thể dùng cùng một cơ chế parse template cho cả hai trường hợp: chuỗi có expression được đánh giá, còn chuỗi không có expression được trả lại như văn bản ban đầu. Cần phân biệt chế độ template với việc parse một SpEL expression thông thường, vì một chuỗi văn bản thuần không tự động trở thành string literal trong cú pháp SpEL.

## 1. Template expression là gì?

Template expression là chuỗi có thể chứa hai loại thành phần:

- Văn bản literal: phần được giữ nguyên trong kết quả.
- Expression segment: phần nằm giữa prefix và suffix, được SpEL phân tích và đánh giá.

Với parser context mặc định dành cho template, prefix là #{ và suffix là }.

Ví dụ:

    Hello, #{#userName}!

Trong chuỗi này, Hello, và ! là văn bản literal. Phần #userName là expression được đánh giá bằng dữ liệu trong EvaluationContext.

Nếu biến userName có giá trị An, kết quả là:

    Hello, An!

Template expression được parse bằng overload nhận ParserContext:

    ExpressionParser parser = new SpelExpressionParser();

    Expression expression = parser.parseExpression(
            "Hello, #{#userName}!",
            ParserContext.TEMPLATE_EXPRESSION);

ParserContext cho parser biết chuỗi cần được xử lý theo chế độ template. Nếu bỏ ParserContext, parser sẽ xử lý đầu vào như một SpEL expression thông thường và không áp dụng quy tắc ghép văn bản literal với vùng #{...}.

## 2. Template không có expression được xử lý như thế nào?

Giả sử đầu vào chỉ là văn bản:

    Welcome to Spring Framework.

Không có prefix #{ nên không có expression segment nào cần phân tích. Khi dùng template parser context:

    ExpressionParser parser = new SpelExpressionParser();

    Expression expression = parser.parseExpression(
            "Welcome to Spring Framework.",
            ParserContext.TEMPLATE_EXPRESSION);

    String result = expression.getValue(String.class);

Giá trị result là:

    Welcome to Spring Framework.

SpEL giữ nguyên nội dung văn bản. Nó không tìm property, không gọi method, không đọc biến trong EvaluationContext và không cần root object để tạo ra kết quả này.

Đây là hành vi quan trọng khi ứng dụng xử lý template do cấu hình cung cấp. Một chuỗi tĩnh vẫn là đầu vào hợp lệ của template parser; không cần thêm một expression rỗng hoặc một biểu thức giả chỉ để parser chấp nhận chuỗi.

## 3. Literal-only template không phải SpEL string literal

Có hai cách khác nhau để yêu cầu SpEL trả về một chuỗi tĩnh.

Cách thứ nhất là parse một string literal theo cú pháp SpEL thông thường. String literal phải được đặt trong dấu nháy đơn:

    Expression expression =
            parser.parseExpression("'Welcome to Spring Framework.'");

Cách thứ hai là parse văn bản thuần trong template mode:

    Expression expression =
            parser.parseExpression(
                    "Welcome to Spring Framework.",
                    ParserContext.TEMPLATE_EXPRESSION);

Cả hai có thể trả về cùng một nội dung, nhưng ý nghĩa cú pháp khác nhau:

| Đầu vào | Parser context | Ý nghĩa |
|---|---|---|
| 'Welcome' | Mặc định | SpEL string literal |
| Welcome | Mặc định | Identifier/property expression, không phải văn bản literal |
| Welcome | Template | Văn bản template được giữ nguyên |
| Hello #{#name} | Template | Văn bản literal kết hợp expression |

Vì vậy, nếu đầu vào là nội dung hiển thị hoặc văn bản cấu hình, hãy dùng template parser context. Nếu đầu vào thực sự là một SpEL expression trả về chuỗi, hãy dùng string literal hoặc biểu thức nối chuỗi theo cú pháp SpEL.

## 4. Ví dụ Java hoàn chỉnh cho template không có expression

Có thể đánh giá một template chỉ chứa văn bản mà không cần tạo EvaluationContext:

    ExpressionParser parser = new SpelExpressionParser();

    String templateText = "Order processing is enabled.";

    Expression expression = parser.parseExpression(
            templateText,
            ParserContext.TEMPLATE_EXPRESSION);

    String message = expression.getValue(String.class);

Kết quả message bằng chính templateText.

Nếu ứng dụng đã có EvaluationContext dùng cho các template khác, có thể truyền context vào getValue:

    EvaluationContext context =
            SimpleEvaluationContext
                    .forReadOnlyDataBinding()
                    .build();

    String message = expression.getValue(
            context, String.class);

Với template không có expression, context không được dùng để tra cứu dữ liệu vì không có expression segment nào cần đánh giá. Việc truyền context không làm thay đổi văn bản literal.

Cách này cho phép một luồng xử lý thống nhất: parse template bằng cùng ParserContext, sau đó đánh giá với context phù hợp. Chuỗi tĩnh không cần nhánh xử lý đặc biệt chỉ để trả lại nội dung.

## 5. So sánh template tĩnh và template có expression

Xét ba đầu vào:

    "Welcome to Spring."

    "Welcome, #{#userName}."

    "Order total: #{#order.total}"

Khi dùng ParserContext.TEMPLATE_EXPRESSION, hành vi tương ứng là:

- Template thứ nhất không có expression nên trả lại nguyên văn.
- Template thứ hai thay vùng #{#userName} bằng giá trị của biến userName.
- Template thứ ba đọc total từ root object order và ghép kết quả vào phần văn bản literal.

Ví dụ đánh giá:

    StandardEvaluationContext context =
            new StandardEvaluationContext(order);

    context.setVariable("userName", "An");

    ExpressionParser parser = new SpelExpressionParser();

    Expression staticTemplate = parser.parseExpression(
            "Welcome to Spring.",
            ParserContext.TEMPLATE_EXPRESSION);

    Expression namedTemplate = parser.parseExpression(
            "Welcome, #{#userName}.",
            ParserContext.TEMPLATE_EXPRESSION);

    Expression orderTemplate = parser.parseExpression(
            "Order total: #{total}",
            ParserContext.TEMPLATE_EXPRESSION);

    String first = staticTemplate.getValue(context, String.class);
    String second = namedTemplate.getValue(context, String.class);
    String third = orderTemplate.getValue(context, String.class);

Kết quả thứ nhất không phụ thuộc order hoặc userName. Kết quả thứ hai phụ thuộc biến userName. Kết quả thứ ba phụ thuộc property total của root object.

## 6. Không có expression không có nghĩa là expression trả về chuỗi rỗng

Cần phân biệt ba trường hợp:

1. Template không có vùng expression: toàn bộ chuỗi là văn bản literal.
2. Template có expression trả về chuỗi rỗng: vùng expression được đánh giá và kết quả của nó là chuỗi rỗng.
3. Template có expression trả về null: expression vẫn được đánh giá, nhưng giá trị trả về là null và việc ghép/chuyển giá trị thành văn bản cần được xử lý theo ý định của ứng dụng.

Ví dụ template literal-only:

    "Hello!"

Ví dụ có expression trả về chuỗi rỗng:

    "Hello#{''}!"

Ví dụ chủ động dùng fallback nếu biến có thể null hoặc chuỗi rỗng:

    "Hello #{#userName ?: 'Guest'}!"

Không nên thêm expression rỗng chỉ để mô phỏng trường hợp không có expression. Nếu muốn hiển thị một chuỗi cố định, hãy để toàn bộ template là văn bản literal. Nếu muốn một phần động nhưng có giá trị thay thế, hãy thể hiện fallback ngay trong expression.

## 7. Template chỉ chứa một expression

Một template có thể chỉ gồm vùng expression mà không có văn bản literal bao quanh:

    #{#order.total}

Trong trường hợp này, kết quả được quyết định bởi expression bên trong. Nếu expression trả về BigDecimal, Boolean hoặc một kiểu Java khác, không nên mặc định rằng kết quả luôn là String chỉ vì đầu vào được parse trong template mode.

Ví dụ:

    Expression expression = parser.parseExpression(
            "#{#order.total}",
            ParserContext.TEMPLATE_EXPRESSION);

    BigDecimal total =
            expression.getValue(context, BigDecimal.class);

Ngược lại, khi template có văn bản literal kết hợp với expression, kết quả được ghép thành chuỗi:

    "Total: #{#order.total}"

Nếu API của ứng dụng yêu cầu String, hãy thiết kế template có văn bản literal hoặc chủ động chuyển kết quả expression sang kiểu chuỗi. Việc chọn kiểu đích trong getValue nên phản ánh đúng kiểu thực tế mà biểu thức trả về.

## 8. Dùng TemplateParserContext tường minh

Thay vì dùng hằng số ParserContext.TEMPLATE_EXPRESSION, có thể tạo TemplateParserContext:

    ParserContext templateContext =
            new TemplateParserContext();

    Expression expression = parser.parseExpression(
            "Welcome to Spring.",
            templateContext);

Constructor mặc định dùng prefix #{ và suffix }. Cách viết này hữu ích khi muốn giữ ParserContext như một đối tượng cấu hình có tên, dùng lại ở nhiều vị trí.

Có thể tạo TemplateParserContext với delimiter tùy chỉnh:

    ParserContext customContext =
            new TemplateParserContext("[[", "]]");

    Expression expression = parser.parseExpression(
            "Welcome, [[#userName]].",
            customContext);

Trong ví dụ, [[ mở đầu expression segment và ]] kết thúc segment. Phần còn lại vẫn là văn bản literal. Tùy chỉnh delimiter giúp tránh xung đột khi nguồn template đã dùng #{...} cho một mục đích văn bản khác.

Delimiter phải được thống nhất giữa nơi tạo template và nơi parse. Nếu template được lưu trong database hoặc file cấu hình, hãy ghi rõ cú pháp delimiter để người chỉnh sửa biết vùng nào sẽ được thực thi như SpEL.

## 9. Văn bản chứa ký hiệu giống delimiter

Một chuỗi có thể cần hiển thị ký hiệu #{ như văn bản thông thường, chẳng hạn khi tài liệu mô tả cú pháp template. Nếu parser đang dùng prefix #{, ký hiệu đó có thể được hiểu là điểm bắt đầu expression.

Không nên giả định mọi parser context đều hỗ trợ cùng một quy tắc escape cho delimiter. Nếu nội dung cần chứa delimiter nguyên văn, có thể chọn một cặp delimiter tùy chỉnh không xuất hiện trong nội dung, hoặc ghép phần văn bản literal ở Java sau khi đánh giá phần động.

Ví dụ chọn delimiter khác:

    ParserContext context =
            new TemplateParserContext("[[", "]]");

    Expression expression = parser.parseExpression(
            "Syntax marker #{name}; user is [[#userName]].",
            context);

Trong ví dụ này, #{name} được giữ là văn bản literal vì parser chỉ nhận [[ và ]] làm delimiter expression.

Nếu cần hỗ trợ escape theo một quy ước riêng, hãy định nghĩa và kiểm thử quy ước đó ở lớp xử lý template của ứng dụng. Đừng để người soạn template phải đoán cách parser xử lý dấu phân cách xuất hiện trong nội dung.

## 10. Lỗi delimiter và expression rỗng

Template không có expression là hợp lệ, nhưng một expression segment được mở ra thì cần có cấu trúc hợp lệ.

Ví dụ:

    "Welcome to Spring."

là template literal-only và không cần dấu phân cách.

Trong khi đó:

    "Welcome, #{#userName"

có prefix nhưng không có suffix đóng. Parser không thể xác định ranh giới expression và sẽ báo lỗi parse.

Tương tự:

    "Welcome, #{}"

có một vùng expression rỗng. Đây không phải cách viết để nói “không có expression”; hãy bỏ hẳn delimiter nếu muốn toàn bộ nội dung là literal.

Khi nhận lỗi, kiểm tra các điểm sau:

- Prefix có xuất hiện nhưng suffix tương ứng bị thiếu hay không.
- Expression bên trong delimiter có rỗng hoặc sai cú pháp không.
- Delimiter cấu hình ở lúc parse có khớp với delimiter được dùng trong template không.
- Dấu nháy, ngoặc hoặc ký tự delimiter bên trong expression có được đóng đúng không.

## 11. Template literal-only và chi phí đánh giá

Khi template không chứa expression, SpEL không cần tra cứu root property, biến, bean hoặc gọi method để tạo kết quả. Nội dung đầu vào được dùng như văn bản literal.

Dù vậy, nếu ứng dụng parse cùng một template nhiều lần, vẫn có chi phí tạo Expression lặp lại. Với template cố định hoặc cấu hình ít thay đổi, có thể parse một lần rồi tái sử dụng Expression:

    ExpressionParser parser = new SpelExpressionParser();

    Expression messageTemplate = parser.parseExpression(
            "The service is ready.",
            ParserContext.TEMPLATE_EXPRESSION);

    String message = messageTemplate.getValue(String.class);

Nếu nội dung template thay đổi theo cấu hình, parse lại khi cấu hình được nạp hoặc thay đổi, thay vì parse trong mỗi request không cần thiết.

Không nên cache Expression theo một khóa quá chung nếu các template có delimiter hoặc parser configuration khác nhau. Hãy gắn cache key với nội dung và cấu hình parser tương ứng.

## 12. Dùng template trong ứng dụng Spring

Template parser context là API của SpEL. Nó không tự động có hiệu lực với mọi chuỗi trong ứng dụng. Nơi sử dụng phải chủ động parse chuỗi bằng một ExpressionParser cùng ParserContext template.

Ví dụ một service đánh giá template thông báo:

    public class MessageTemplateService {

        private final ExpressionParser parser =
                new SpelExpressionParser();

        private final ParserContext templateContext =
                ParserContext.TEMPLATE_EXPRESSION;

        public String render(
                String template, EvaluationContext context) {

            Expression expression =
                    parser.parseExpression(
                            template, templateContext);

            return expression.getValue(context, String.class);
        }
    }

Với đầu vào Service is ready., kết quả là cùng chuỗi đó. Với đầu vào Hello, #{#userName}!, biến userName được đánh giá theo context được truyền vào.

Nếu template có thể đến từ người dùng hoặc quản trị viên, cần giới hạn context và khả năng mà expression được phép sử dụng. Một template không có expression chỉ trả lại văn bản, nhưng một template khác có delimiter có thể gọi property, method hoặc capability đã được context cung cấp. Không nên coi mọi template từ cùng một nguồn đều có mức độ tin cậy như nhau.

## 13. Kiểm thử hành vi của template không có expression

Nên có kiểm thử riêng cho literal-only template để bảo đảm parser context được dùng đúng và nội dung không bị biến đổi ngoài ý muốn.

Các trường hợp nên kiểm tra:

- Chuỗi thông thường không có delimiter: kết quả bằng chính chuỗi đầu vào.
- Chuỗi rỗng: kết quả là chuỗi rỗng.
- Chuỗi có dấu cách đầu/cuối: các dấu cách được giữ lại.
- Chuỗi có nhiều dòng: xuống dòng và thứ tự dòng được giữ nguyên.
- Chuỗi có delimiter hợp lệ: expression segment được đánh giá.
- Chuỗi có prefix không có suffix: parser báo lỗi.
- Chuỗi có expression rỗng: parser báo lỗi thay vì coi như template không có expression.
- Template chỉ có một expression: kiểu kết quả tuân theo expression đó.
- Template trộn literal và expression: kết quả được ghép theo đúng thứ tự.

Ví dụ kiểm thử đơn giản:

    @Test
    void returnsLiteralTextWhenTemplateHasNoExpression() {
        ExpressionParser parser =
                new SpelExpressionParser();

        Expression expression = parser.parseExpression(
                "  Service is ready.  ",
                ParserContext.TEMPLATE_EXPRESSION);

        String result = expression.getValue(String.class);

        assertEquals("  Service is ready.  ", result);
    }

Kiểm thử này xác nhận cả nội dung lẫn khoảng trắng được giữ nguyên. Nếu template là dữ liệu hiển thị, việc vô tình trim hoặc chuẩn hóa có thể làm thay đổi định dạng mà người cấu hình mong muốn.

## 14. Những nhầm lẫn thường gặp

| Tình huống | Nguyên nhân | Cách xử lý |
|---|---|---|
| Văn bản thuần bị hiểu như property | Dùng parseExpression(String) mặc định | Truyền ParserContext.TEMPLATE_EXPRESSION |
| Template không có expression bị xem là thiếu dữ liệu | Nghĩ mọi template phải chứa #{...} | Chấp nhận literal-only template và dùng nội dung trả về |
| Dùng #{} để biểu thị không có expression | Nhầm expression rỗng với không có segment | Bỏ delimiter, giữ văn bản literal |
| Template có prefix nhưng thiếu suffix | Expression segment không đóng | Sửa delimiter hoặc từ chối template không hợp lệ |
| Kết quả chỉ có expression không phải String | Expression trả về kiểu gốc của nó | Chọn kiểu getValue phù hợp hoặc chuyển đổi rõ ràng |
| Ký hiệu #{ trong nội dung bị parse | Trùng với prefix đang cấu hình | Dùng delimiter tùy chỉnh hoặc ghép literal ở Java |
| Thay đổi delimiter nhưng parser vẫn dùng cấu hình cũ | TemplateParserContext không khớp template | Dùng cùng một ParserContext ở lúc parse |

## Kết luận

Một template SpEL không có expression vẫn là đầu vào hợp lệ. Khi parse bằng ParserContext.TEMPLATE_EXPRESSION hoặc TemplateParserContext, toàn bộ chuỗi được xem là văn bản literal và kết quả đánh giá giữ nguyên nội dung đó. Không cần root object, biến hay method để xử lý trường hợp này.

Hãy phân biệt template literal-only với SpEL string literal và với template có expression trả về chuỗi rỗng. Dùng parser context tường minh, thống nhất delimiter, kiểm tra template có prefix/suffix không cân bằng và chọn kiểu kết quả phù hợp. Nếu template có thể chứa expression do người khác cung cấp, hãy giới hạn EvaluationContext theo use case và mức độ tin cậy của nguồn template.