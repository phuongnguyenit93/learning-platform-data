# Không nhầm SpEL template với Thymeleaf hoặc JSP EL

## 1. Vì sao dễ nhầm các loại expression?

Spring Expression Language (SpEL), Thymeleaf và JSP Expression Language (JSP EL) đều có cú pháp biểu thức đặt trong dấu phân cách. Khi nhìn nhanh, một số cú pháp trông giống hệt nhau, đặc biệt là ${...} và #{...}.

Tuy nhiên, cùng một cặp ký tự có thể mang ý nghĩa khác nhau tùy engine:

- SpEL template dùng #{...} để đánh dấu một đoạn SpEL nằm bên trong văn bản cố định.
- Thymeleaf dùng #{...} cho message expression, thường phục vụ i18n; ${...} là variable expression.
- JSP EL dùng ${...} cho immediate evaluation và #{...} cho deferred evaluation trong các vị trí hỗ trợ deferred expression.

Không thể xác định engine chỉ bằng cách nhìn vào dấu ngoặc. Cần biết thành phần nào đang xử lý chuỗi, cú pháp nào được cấu hình và expression được đánh giá ở thời điểm nào.

## 2. SpEL expression thông thường không cần delimiter

Khi dùng API ExpressionParser, nếu gọi parseExpression(String) mà không truyền ParserContext, toàn bộ chuỗi được xem là một biểu thức SpEL.

Ví dụ:

    ExpressionParser parser = new SpelExpressionParser();

    Expression expression =
        parser.parseExpression("#customer.name");

    String name =
        expression.getValue(context, String.class);

Trong ví dụ này, #customer.name là biểu thức SpEL hoàn chỉnh. Không cần bọc nó trong #{...}.

Nếu muốn tạo một chuỗi có cả văn bản cố định và kết quả expression, dùng template parsing:

    Expression template = parser.parseExpression(
        "Xin chào #{#customer.name}!",
        new TemplateParserContext()
    );

    String message =
        template.getValue(context, String.class);

Nếu customer.name là Lan, kết quả là:

    Xin chào Lan!

Ở đây:

- "Xin chào " là văn bản cố định.
- #{#customer.name} là đoạn SpEL được đánh giá.
- "!" là văn bản cố định.

TemplateParserContext mặc định dùng prefix #{ và suffix }. Parser ghép các đoạn văn bản với kết quả của từng expression block khi expression được đánh giá.

## 3. ParserContext và TemplateParserContext thuộc API SpEL

TemplateParserContext là implementation của ParserContext trong Spring Expression Language. Nó cho parser biết chuỗi đầu vào là một template và quy định delimiter dùng để nhận diện expression block.

Ví dụ:

    Expression template = parser.parseExpression(
        "Tổng tiền: #{#order.total}",
        new TemplateParserContext()
    );

Có thể thay delimiter bằng cách tạo TemplateParserContext với prefix và suffix riêng:

    ParserContext parserContext =
        new TemplateParserContext("[[", "]]");

    Expression template = parser.parseExpression(
        "Tổng tiền: [[#order.total]]",
        parserContext
    );

Trong trường hợp này, [[ và ]] là delimiter do ứng dụng cấu hình. SpEL chỉ hiểu chúng như ranh giới template vì parser được truyền ParserContext tương ứng.

Điều này khác với việc một template engine tự định nghĩa cú pháp của nó. Thymeleaf và JSP không tự động dùng TemplateParserContext chỉ vì nội dung có dấu #{...}.

Cần phân biệt hai lời gọi:

    parser.parseExpression("#order.total")

Đây là một expression SpEL độc lập.

    parser.parseExpression(
        "Tổng tiền: #{#order.total}",
        new TemplateParserContext()
    )

Đây là một SpEL template gồm text và expression block.

## 4. Thymeleaf có hệ thống Standard Expression riêng

Thymeleaf là template engine xử lý template HTML, XML, JavaScript, CSS hoặc text theo cấu hình và dialect tương ứng. Standard Dialect định nghĩa nhiều loại expression riêng:

| Cú pháp Thymeleaf | Ý nghĩa |
| --- | --- |
| ${...} | Variable expression |
| *{...} | Selection expression |
| #{...} | Message expression, thường dùng cho i18n |
| @{...} | Link/URL expression |
| ~{...} | Fragment expression |

Ví dụ:

    <span th:text="${customer.name}">Customer</span>

Thymeleaf lấy customer từ template context rồi đọc property name.

Ví dụ message:

    <h1 th:text="#{home.title}">Welcome</h1>

Thymeleaf tìm message có key home.title từ message source theo locale hiện tại.

Ví dụ link:

    <a th:href="@{/orders}">Orders</a>

Thymeleaf tạo URL phù hợp với context của ứng dụng.

Ví dụ fragment:

    <div th:replace="~{fragments/header :: main}"></div>

Thymeleaf lấy fragment được chỉ định và chèn vào template đang xử lý.

Vì vậy, trong Thymeleaf, #{home.title} thường có nghĩa là tra cứu message, không phải một SpEL expression block nằm trong văn bản như cách dùng TemplateParserContext.

## 5. ${...} trong Thymeleaf là variable expression

Variable expression truy cập dữ liệu trong Thymeleaf context. Trong ứng dụng Spring MVC, dữ liệu thường đến từ model attributes hoặc các biến được đưa vào context.

Ví dụ controller đưa customer vào model:

    model.addAttribute("customer", customer);

Template:

    <span th:text="${customer.name}">Name</span>

Thymeleaf đọc biến customer, sau đó truy cập property name.

Trong Standard Dialect mặc định, expression evaluation sử dụng OGNL. Khi tích hợp với Spring, SpringStandard Dialect thay thế OGNL bằng Spring Expression Language cho việc đánh giá variable và selection expressions.

Điều đó có nghĩa là cú pháp variable expression vẫn thuộc Thymeleaf Standard Expression syntax, nhưng engine thực hiện phần đánh giá có thể là OGNL hoặc SpEL tùy dialect đang dùng.

Không nên suy luận rằng mọi template Thymeleaf đều sử dụng SpEL. Cần xác định ứng dụng đang dùng Standard Dialect hay SpringStandard Dialect.

## 6. *{...} trong Thymeleaf là selection expression

Selection expression tương tự variable expression, nhưng được đánh giá trên một object đã được chọn trước bằng th:object.

Ví dụ:

    <div th:object="${customer}">
        <span th:text="*{name}">Name</span>
        <span th:text="*{address.city}">City</span>
    </div>

th:object chọn customer làm selection target. Bên trong block, *{name} đọc property name trên object đã chọn.

Cách viết tương đương theo ý nghĩa là truy cập customer.name, nhưng selection expression giúp template ngắn hơn khi nhiều field cùng thuộc một object.

Đây là cú pháp của Thymeleaf. SpEL TemplateParserContext không định nghĩa *{...} là selection expression mặc định.

## 7. #{...} trong Thymeleaf là message expression

Trong Thymeleaf Standard Dialect, #{...} được dùng để tra cứu message theo key. Nó thường được sử dụng cho nội dung đa ngôn ngữ.

Ví dụ file messages.properties:

    home.title=Welcome to the application
    order.created=Order {0} has been created

Template:

    <h1 th:text="#{home.title}">Welcome</h1>

Có thể truyền tham số cho message:

    <p th:text="#{order.created(${order.id})}">
        Order created
    </p>

Thymeleaf sử dụng MessageSource hoặc cơ chế message resolution tương ứng để tìm nội dung theo locale.

Trong SpringStandard Dialect, việc dùng Spring EL cho variable/selection expression không làm thay đổi ý nghĩa của message expression #{...}. Nó vẫn là cú pháp message của Thymeleaf.

Đây là điểm dễ nhầm nhất với SpEL template:

- SpEL TemplateParserContext: #{...} chứa một đoạn biểu thức SpEL.
- Thymeleaf Standard Expression: #{...} là key hoặc message expression.

Cùng delimiter, nhưng parser, context và kết quả xử lý khác nhau.

## 8. JSP EL có cú pháp ${} và #{}

JSP sử dụng Jakarta Expression Language để truy cập dữ liệu và thực hiện biểu thức trong trang JSP.

JSP EL có hai dạng delimiter:

- ${...}: immediate evaluation.
- #{...}: deferred evaluation.

Immediate evaluation được thực hiện khi JSP xử lý trang để tạo response. Deferred evaluation cho phép công nghệ sử dụng expression quyết định thời điểm đánh giá sau đó, thường gắn với các tag attribute hỗ trợ deferred value hoặc deferred method.

Ví dụ immediate expression:

    <c:out value="${customer.name}" />

JSP EL đánh giá customer.name và đưa giá trị vào output của tag.

Ví dụ deferred expression trong một attribute hỗ trợ deferred value:

    <h:inputText value="#{customer.name}" />

Ví dụ này thường gặp trong Jakarta Faces. Component framework có thể giữ expression để đọc hoặc ghi property ở các giai đoạn phù hợp của lifecycle.

Không phải mọi tag attribute đều hỗ trợ deferred expression. Khả năng sử dụng #{...} phụ thuộc vào loại attribute và metadata của tag.

## 9. Quy tắc riêng của JSP template text

Trong JSP, expression có thể xuất hiện trong attribute của standard/custom action và trong template text. Tuy nhiên, quy tắc delimiter phụ thuộc vị trí.

Với template text thông thường, JSP cho phép cú pháp ${...} để immediate evaluation. Cú pháp #{...} dành cho deferred expression trong các attribute có hỗ trợ tương ứng; dùng nó trực tiếp trong template text có thể gây translation error.

Ví dụ template text:

    <p>Hello ${customer.name}</p>

Đây là immediate JSP EL expression trong nội dung trang.

Ví dụ attribute của một component hỗ trợ deferred expression:

    <h:inputText value="#{customer.name}" />

Không nên sao chép cú pháp deferred expression từ Jakarta Faces vào nội dung template text của JSP thông thường rồi kỳ vọng nó hoạt động giống SpEL template.

JSP EL là ngôn ngữ riêng của Jakarta EE. Dù cú pháp truy cập bean property trông tương tự SpEL, nó có resolver, kiểu expression và lifecycle riêng.

## 10. Bảng so sánh ba cơ chế

| Tiêu chí | SpEL template | Thymeleaf Standard/SpringStandard | JSP EL |
| --- | --- | --- | --- |
| Thành phần xử lý | Spring ExpressionParser với ParserContext | Thymeleaf Template Engine và Dialect | JSP engine cùng Jakarta EL |
| Delimiter template/text | Mặc định #{...} cho expression block | Các Standard Expressions tùy mục đích | ${...} trong template text |
| Ý nghĩa #{...} | SpEL block trong template parsing | Message/i18n expression | Deferred expression tại vị trí hỗ trợ |
| Ý nghĩa ${...} | Không phải delimiter mặc định của TemplateParserContext | Variable expression | Immediate EL expression |
| Selection expression | Dùng object/root/variable theo SpEL | *{...} | Phụ thuộc cú pháp EL và tag/framework |
| URL expression | Không có loại URL expression riêng mặc định | @{...} | Phụ thuộc tag hoặc thư viện |
| Fragment expression | Không có loại fragment riêng mặc định | ~{...} | JSP có include/action/tag mechanism riêng |
| Thời điểm đánh giá | Khi gọi getValue trên Expression | Khi template engine xử lý template | Theo immediate/deferred rules và JSP lifecycle |

Bảng này so sánh ý nghĩa chính trong từng môi trường. Không nên coi các expression có cùng ký hiệu là có thể hoán đổi cho nhau.

## 11. Ví dụ cùng một nội dung nhưng khác cách xử lý

Giả sử muốn hiển thị tên khách hàng.

### SpEL template

    Expression template = parser.parseExpression(
        "Xin chào #{#customer.name}",
        new TemplateParserContext()
    );

    String output =
        template.getValue(context, String.class);

Ứng dụng chủ động gọi SpEL parser và cung cấp EvaluationContext. #{#customer.name} là expression block.

### Thymeleaf

    <span th:text="#{home.greeting}">Greeting</span>
    <span th:text="${customer.name}">Name</span>

Dòng đầu tra cứu message home.greeting. Dòng thứ hai đọc property name từ variable customer.

Nếu dùng message có tham số:

    <span th:text="#{home.greeting(${customer.name})}">
        Greeting
    </span>

Thymeleaf resolve message và truyền tên khách hàng làm tham số.

### JSP

    <p>Hello ${customer.name}</p>

JSP EL đánh giá customer.name ngay khi trang được render.

Trong một attribute hỗ trợ deferred evaluation, framework có thể sử dụng:

    <h:inputText value="#{customer.name}" />

Đây là deferred value expression của Jakarta EL, không phải SpEL template block.

## 12. Phân biệt Spring @Value với Thymeleaf và JSP

Trong ứng dụng Spring, annotation @Value thường dùng expression có dạng:

    @Value("#{systemProperties['user.name']}")
    private String userName;

Đây là điểm tích hợp của Spring container với SpEL. Spring xử lý biểu thức khi tạo hoặc cấu hình bean.

Nó không phải Thymeleaf message expression, dù cùng dùng dấu #{...}.

Tương tự, một chuỗi Java thông thường:

    String source = "Hello #{#customer.name}";

không tự được Thymeleaf, JSP hoặc SpEL xử lý. Chỉ component nào chủ động parse hoặc xử lý template mới diễn giải delimiter.

Khi thấy #{...} trong source code, hãy xác định nó nằm trong:

- Annotation Spring như @Value.
- Lời gọi SpEL TemplateParserContext.
- Attribute Thymeleaf như th:text.
- JSP tag attribute hỗ trợ deferred EL.
- Nội dung Java string chưa được xử lý.

Vị trí và engine quyết định ý nghĩa.

## 13. Cách xác định expression engine khi debug

Khi một biểu thức không hoạt động như dự kiến, hãy xác định thành phần xử lý trước khi sửa cú pháp.

1. Kiểm tra file hoặc API chứa expression: Java code, annotation, HTML Thymeleaf hay JSP.
2. Xác định engine: SpEL parser, Thymeleaf Standard/SpringStandard Dialect hay JSP EL.
3. Xác định context: EvaluationContext, Thymeleaf Context/Model hay JSP ELContext.
4. Kiểm tra delimiter và vị trí được phép sử dụng.
5. Xác định thời điểm đánh giá: lúc gọi getValue, lúc render template hay theo lifecycle deferred.
6. Kiểm tra lỗi từ đúng engine thay vì tìm lỗi trong parser khác.

Một biểu thức có thể đúng trong SpEL nhưng sai trong Thymeleaf message expression hoặc JSP EL. Tương tự, cú pháp Thymeleaf @{...} không có ý nghĩa URL expression mặc định trong SpEL.

## 14. Những lỗi nhầm lẫn thường gặp

| Hiểu nhầm | Vì sao sai | Cách hiểu đúng |
| --- | --- | --- |
| #{...} luôn là SpEL | Thymeleaf dùng nó cho message; JSP EL dùng cho deferred evaluation | Xác định engine và vị trí |
| ${...} luôn là placeholder Spring | Thymeleaf dùng variable expression; JSP dùng immediate EL | Cùng ký hiệu có nhiều ngữ nghĩa |
| SpringStandard Dialect làm #{...} thành SpEL block | #{...} vẫn là message expression trong Thymeleaf | SpringStandard thay expression evaluator cho variable/selection, không đổi message syntax |
| JSP EL và SpEL là một ngôn ngữ | Chúng có grammar, resolver và lifecycle riêng | JSP EL thuộc Jakarta EL; SpEL thuộc Spring |
| TemplateParserContext tự xử lý mọi file HTML | Nó chỉ là ParserContext cho Spring ExpressionParser | Thymeleaf/JSP cần template engine tương ứng |
| Có thể dùng @{...} trong SpEL để tạo URL | @{...} là link expression của Thymeleaf | Dùng API URI/URL phù hợp trong Java hoặc template engine |
| #{...} có thể dùng ở mọi vị trí JSP | JSP giới hạn deferred syntax theo tag attribute hỗ trợ | Template text thông thường dùng ${...} |

## 15. Escape và hiển thị nội dung an toàn

Delimiter không chỉ ảnh hưởng việc đánh giá expression mà còn liên quan đến cách nội dung được đưa ra HTML.

Trong Thymeleaf, th:text xử lý expression và xuất text đã escape theo quy tắc HTML. th:utext xuất nội dung không escape, vì vậy chỉ dùng khi nội dung HTML đã được tin cậy hoặc được sanitize phù hợp.

Trong JSP, JSTL c:out hỗ trợ escape XML theo cấu hình mặc định, phù hợp khi hiển thị dữ liệu không tin cậy dưới dạng text.

Với SpEL template, kết quả getValue chỉ là một giá trị Java, thường là String. SpEL không tự HTML-escape kết quả. Nếu đưa chuỗi đó vào HTML, ứng dụng phải dùng cơ chế output encoding phù hợp với ngữ cảnh.

Không nên nhầm việc parse expression an toàn với việc render HTML an toàn. Đây là hai vấn đề riêng.

## 16. Những điểm cần nhớ

- SpEL parseExpression(String) xem toàn bộ chuỗi là expression; không cần #{...} nếu không dùng template parsing.
- SpEL TemplateParserContext mặc định dùng #{...} để phân tách expression block khỏi literal text.
- Thymeleaf Standard Expressions gồm ${...}, *{...}, #{...}, @{...} và ~{...}.
- Trong Thymeleaf, #{...} là message/i18n expression; ${...} là variable expression.
- Thymeleaf Standard Dialect mặc định dùng OGNL; SpringStandard tích hợp Spring EL cho variable và selection expression.
- JSP EL dùng ${...} cho immediate evaluation và #{...} cho deferred evaluation ở vị trí hỗ trợ.
- JSP template text thông thường chỉ dùng ${...}; không mặc định cho phép deferred #{...} trong text.
- JSP EL là ngôn ngữ riêng của Jakarta EE, không phải SpEL.
- Spring @Value có thể dùng #{...} cho SpEL nhưng đó là điểm tích hợp của Spring container.
- Cùng delimiter không có nghĩa cùng parser, context hoặc lifecycle.
- Khi debug, xác định engine và vị trí xử lý trước khi sửa expression.
- Output encoding/HTML escaping là trách nhiệm riêng, không tự được bảo đảm bởi SpEL parsing.

Khi làm việc với template trong ứng dụng Spring, hãy xác định rõ ai đang xử lý chuỗi: SpEL parser, Thymeleaf dialect hay JSP EL. Sự phân biệt này giúp tránh dùng nhầm delimiter, nhầm message expression với expression block và nhầm thời điểm đánh giá.

## Tài liệu tham khảo

- Spring Framework Reference — Expression Templating: https://docs.spring.io/spring-framework/reference/core/expressions/language-ref/templating.html
- Spring Framework Javadoc — TemplateParserContext: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/expression/common/TemplateParserContext.html
- Thymeleaf Tutorial — Standard Expression Syntax: https://www.thymeleaf.org/doc/tutorials/3.1/usingthymeleaf.html
- Thymeleaf — Standard Dialects in 5 Minutes: https://www.thymeleaf.org/doc/articles/standarddialect5minutes.html
- Jakarta Server Pages Specification — Expression Language in JSP: https://jakarta.ee/specifications/pages/4.1/jakarta-server-pages-spec-4.1.html
- Jakarta Expression Language Specification: https://jakarta.ee/specifications/expression-language/6.1/
