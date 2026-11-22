# ParserContext và delimiter của template trong Spring Expression Language

Spring Expression Language (SpEL) có thể đánh giá một biểu thức độc lập, nhưng ứng dụng cũng thường cần tạo chuỗi gồm văn bản cố định xen kẽ với các giá trị động. Ví dụ, một thông báo có thể chứa tên khách hàng và tổng tiền của đơn hàng:

~~~text
Xin chào Linh, đơn hàng của bạn có tổng tiền 750000.
~~~

Để xử lý dạng chuỗi này, SpEL hỗ trợ **template expression**. Template chứa văn bản thông thường và những đoạn SpEL được đặt giữa các dấu phân cách (delimiter). **ParserContext** cho parser biết đầu vào có phải template hay không và cặp delimiter nào đánh dấu phần biểu thức.

ParserContext thuộc giai đoạn parsing. Nó quy định cách tách văn bản cố định khỏi các đoạn SpEL; dữ liệu dùng để đánh giá biểu thức vẫn được cung cấp bởi EvaluationContext.

## 1. Template expression là gì?

Một template expression là chuỗi gồm hai loại nội dung:

- **Văn bản cố định:** được giữ nguyên trong kết quả.
- **Đoạn SpEL:** nằm giữa prefix và suffix, được parse rồi đánh giá.

Với delimiter mặc định, template có dạng:

~~~text
Xin chào #{'Linh'}, hôm nay là #{T(java.time.LocalDate).now()}.
~~~

Trong đó:

- Phần trước đoạn biểu thức đầu tiên là văn bản cố định.
- Nội dung giữa #{ và } là biểu thức SpEL.
- Phần văn bản sau biểu thức tiếp tục được giữ lại.
- Giá trị của mỗi biểu thức được ghép vào vị trí tương ứng.

Khi đánh giá, kết quả là một chuỗi hoàn chỉnh. Template hữu ích cho thông báo, nhãn hiển thị, nội dung cấu hình và các chuỗi cần nội suy dữ liệu.

## 2. Vì sao cần ParserContext?

Nếu chỉ cần đánh giá một biểu thức SpEL độc lập, có thể gọi overload parseExpression chỉ với chuỗi:

~~~java
ExpressionParser parser = new SpelExpressionParser();

Expression expression =
    parser.parseExpression("10 + 5");

Integer result = expression.getValue(Integer.class);
~~~

Kết quả là 15. Toàn bộ chuỗi 10 + 5 được hiểu là cú pháp SpEL.

Nhưng nếu đầu vào là một câu có văn bản tự do:

~~~text
Tổng tiền đơn hàng: #{#total}
~~~

parser cần biết phần nào là văn bản và phần nào là biểu thức. Nếu không truyền ParserContext, parser không tự suy luận rằng chuỗi có delimiter là một template.

Có thể chỉ rõ cách parse bằng overload nhận ParserContext:

~~~java
Expression expression = parser.parseExpression(
    "Tổng tiền đơn hàng: #{#total}",
    new TemplateParserContext()
);
~~~

ParserContext cho parser biết cần tách template theo quy tắc nào. Nó không cung cấp giá trị cho biến total và cũng không đánh giá biểu thức thay cho EvaluationContext.

## 3. ParserContext là interface nào?

ParserContext thuộc package org.springframework.expression. Interface này cung cấp ba thông tin cho ExpressionParser:

- isTemplate(): cho biết đầu vào có được xử lý như một template hay không.
- getExpressionPrefix(): trả về chuỗi mở đầu một đoạn biểu thức.
- getExpressionSuffix(): trả về chuỗi kết thúc một đoạn biểu thức.

Có thể mô tả vai trò:

| Phương thức | Trách nhiệm |
|---|---|
| isTemplate() | Chọn chế độ parse template hay biểu thức thông thường |
| getExpressionPrefix() | Xác định điểm bắt đầu đoạn SpEL |
| getExpressionSuffix() | Xác định điểm kết thúc đoạn SpEL |

ParserContext không chứa root object, variables, bean resolver hoặc type converter. Những thành phần đó thuộc EvaluationContext và được dùng khi expression được đánh giá.

## 4. TemplateParserContext và delimiter mặc định

Spring cung cấp lớp TemplateParserContext trong package org.springframework.expression.common. Đây là triển khai sẵn của ParserContext dành cho template expression.

Constructor mặc định dùng:

- Prefix: #{
- Suffix: }

Ví dụ:

~~~java
ParserContext parserContext =
    new TemplateParserContext();

ExpressionParser parser =
    new SpelExpressionParser();

Expression template = parser.parseExpression(
    "Xin chào #{'Linh'}!",
    parserContext
);

String result = template.getValue(String.class);
~~~

Kết quả:

~~~text
Xin chào Linh!
~~~

Có thể dùng constructor mặc định khi cú pháp #{ ... } phù hợp với định dạng template của ứng dụng.

Trong một template, mỗi đoạn biểu thức được parse theo cú pháp SpEL thông thường. Các phần nằm ngoài delimiter được giữ làm văn bản literal.

## 5. Tùy chỉnh prefix và suffix

Nếu delimiter mặc định xung đột với định dạng văn bản khác, có thể chỉ định cặp delimiter riêng bằng constructor của TemplateParserContext:

~~~java
ParserContext parserContext =
    new TemplateParserContext("[[", "]]");

ExpressionParser parser =
    new SpelExpressionParser();

Expression template = parser.parseExpression(
    "Xin chào [['Linh']], tổng tiền là [[100 + 50]].",
    parserContext
);

String result = template.getValue(String.class);
~~~

Kết quả:

~~~text
Xin chào Linh, tổng tiền là 150.
~~~

Trong ví dụ:

- Prefix là [[.
- Suffix là ]].
- Đoạn [['Linh']] chứa biểu thức chuỗi literal.
- Đoạn [[100 + 50]] chứa phép tính SpEL.
- Phần còn lại là văn bản cố định.

Việc đổi delimiter không thay đổi cú pháp bên trong đoạn biểu thức. Nội dung giữa prefix và suffix vẫn tuân theo cú pháp SpEL.

## 6. Cách template được phân tách và đánh giá

Giả sử template:

~~~text
Đơn hàng #{#orderNumber} của #{#customerName} có tổng tiền #{#total}.
~~~

Parser sử dụng delimiter để tách nội dung thành các đoạn:

| Thứ tự | Nội dung | Cách xử lý |
|---:|---|---|
| 1 | Đơn hàng | Giữ nguyên văn bản |
| 2 | #orderNumber | Parse và đánh giá bằng SpEL |
| 3 | của | Giữ nguyên văn bản |
| 4 | #customerName | Parse và đánh giá bằng SpEL |
| 5 | có tổng tiền | Giữ nguyên văn bản |
| 6 | #total | Parse và đánh giá bằng SpEL |
| 7 | . | Giữ nguyên văn bản |

Khi getValue được gọi, các đoạn biểu thức được đánh giá trong cùng môi trường EvaluationContext và kết quả được ghép với các đoạn văn bản literal theo đúng thứ tự.

Có thể hình dung:

~~~text
Template string
      |
      v
ParserContext cung cấp prefix/suffix
      |
      v
ExpressionParser tách các đoạn
      |
      +--> Literal text
      |
      +--> SpEL expression
                 |
                 v
          EvaluationContext
                 |
                 v
          Giá trị runtime
      |
      v
Ghép các đoạn theo thứ tự
      |
      v
Chuỗi kết quả
~~~

ParserContext quyết định ranh giới của các đoạn biểu thức. EvaluationContext quyết định các đoạn đó đọc dữ liệu và thực hiện thao tác như thế nào.

## 7. Kết hợp template với EvaluationContext

Template expression thường cần dữ liệu từ Java. Đăng ký các giá trị trong EvaluationContext rồi tham chiếu chúng bằng cú pháp biến #name.

Ví dụ:

~~~java
ExpressionParser parser =
    new SpelExpressionParser();

ParserContext parserContext =
    new TemplateParserContext();

Expression template = parser.parseExpression(
    "Xin chào #{#customerName}, đơn hàng #{#orderNumber} có tổng tiền #{#total} VND.",
    parserContext
);

StandardEvaluationContext context =
    new StandardEvaluationContext();

context.setVariable("customerName", "Linh");
context.setVariable("orderNumber", "ORD-100");
context.setVariable("total", new BigDecimal("750000"));

String message =
    template.getValue(context, String.class);

System.out.println(message);
~~~

Kết quả:

~~~text
Xin chào Linh, đơn hàng ORD-100 có tổng tiền 750000 VND.
~~~

Trong ví dụ:

- ParserContext xác định #{ và } là delimiter.
- Parser phân tách template thành văn bản và ba đoạn biểu thức.
- EvaluationContext cung cấp các biến customerName, orderNumber và total.
- getValue đánh giá từng đoạn SpEL rồi ghép kết quả thành String.

Nếu một biến chưa được đăng ký hoặc có giá trị null, đoạn biểu thức tương ứng có thể trả về null hoặc phát sinh lỗi tùy thao tác được thực hiện trên giá trị đó.

## 8. Root object cũng có thể được dùng trong template

Template không bắt buộc chỉ tham chiếu variables. Các đoạn SpEL có thể đọc property trên root object như expression thông thường.

Giả sử có lớp Customer:

~~~java
public class Customer {
    private final String name;
    private final String membershipLevel;

    public Customer(String name, String membershipLevel) {
        this.name = name;
        this.membershipLevel = membershipLevel;
    }

    public String getName() {
        return name;
    }

    public String getMembershipLevel() {
        return membershipLevel;
    }
}
~~~

Đánh giá template với root object:

~~~java
Customer customer =
    new Customer("Linh", "GOLD");

StandardEvaluationContext context =
    new StandardEvaluationContext(customer);

ExpressionParser parser =
    new SpelExpressionParser();

Expression template = parser.parseExpression(
    "Khách hàng #{name} có hạng #{membershipLevel}.",
    new TemplateParserContext()
);

String message =
    template.getValue(context, String.class);
~~~

Kết quả:

~~~text
Khách hàng Linh có hạng GOLD.
~~~

Các tên name và membershipLevel được đọc trên root object. Nếu muốn chỉ rõ nguồn, có thể viết #root.name và #root.membershipLevel.

## 9. Template có nhiều biểu thức và biểu thức lồng nhau

Một template có thể chứa nhiều đoạn SpEL độc lập:

~~~text
#{#firstName} #{#lastName}: #{#price * #quantity}
~~~

Mỗi đoạn được parse và đánh giá theo cú pháp SpEL. Bên trong một đoạn, có thể dùng dấu ngoặc để nhóm biểu thức:

~~~text
Thành tiền sau giảm giá: #{(#price * #quantity) * (1 - #discountRate)}
~~~

Dấu ngoặc ở đây thuộc cú pháp biểu thức bên trong delimiter. Prefix và suffix chỉ xác định ranh giới đoạn SpEL trong template.

Nếu một đoạn biểu thức có cú pháp sai, lỗi xuất hiện trong quá trình parsing. Nếu biểu thức parse được nhưng biến hoặc property không phù hợp khi chạy, lỗi xuất hiện trong quá trình evaluation.

## 10. Dùng template với toán tử, property và method call

Nội dung bên trong delimiter có thể sử dụng các khả năng SpEL thông thường.

Ví dụ:

~~~java
Product product =
    new Product("Keyboard", new BigDecimal("750000"));

StandardEvaluationContext context =
    new StandardEvaluationContext(product);

context.setVariable("quantity", 2);

ExpressionParser parser =
    new SpelExpressionParser();

Expression template = parser.parseExpression(
    "Sản phẩm: #{name.toUpperCase()}, số lượng: #{#quantity}, thành tiền: #{price * #quantity}.",
    new TemplateParserContext()
);

String message =
    template.getValue(context, String.class);
~~~

Kết quả:

~~~text
Sản phẩm: KEYBOARD, số lượng: 2, thành tiền: 1500000.
~~~

Các đoạn biểu thức lần lượt:

- Đọc property name và gọi toUpperCase().
- Đọc biến quantity.
- Đọc property price rồi nhân với quantity.

Template chỉ thêm lớp ghép văn bản. Nó không giới hạn các biểu thức bên trong vào một tập toán tử khác.

## 11. TemplateParserContext và ParserContext tùy chỉnh

Nếu cặp delimiter không đủ linh hoạt, ứng dụng có thể tự triển khai ParserContext.

Một triển khai tối thiểu có thể cung cấp:

~~~java
public class CustomParserContext implements ParserContext {

    @Override
    public boolean isTemplate() {
        return true;
    }

    @Override
    public String getExpressionPrefix() {
        return "[[";
    }

    @Override
    public String getExpressionSuffix() {
        return "]]";
    }
}
~~~

Sau đó sử dụng:

~~~java
Expression template = parser.parseExpression(
    "Giá trị: [[#value]]",
    new CustomParserContext()
);
~~~

Trong thực tế, nếu chỉ cần thay prefix và suffix, TemplateParserContext đã đáp ứng yêu cầu và giúp giảm mã tùy chỉnh.

Custom ParserContext phù hợp khi ứng dụng cần một chính sách delimiter được đóng gói trong lớp riêng hoặc cần triển khai một quy ước template cụ thể.

## 12. Chọn delimiter phù hợp

Delimiter là một phần của định dạng template, vì vậy nên chọn cặp ký tự dễ nhận diện và ít xuất hiện trong văn bản thông thường.

Một số lưu ý:

- Dùng cùng một prefix và suffix trong toàn bộ hệ thống tạo và đánh giá template.
- Tránh chọn delimiter thường xuyên xuất hiện trong nội dung literal.
- Giữ delimiter mở và đóng dễ phân biệt.
- Khi thay đổi delimiter, cập nhật cả dữ liệu template và ParserContext dùng để parse.
- Kiểm tra template có đủ delimiter đóng cho mỗi đoạn biểu thức.
- Không nhầm delimiter của template với cú pháp biến, property hoặc toán tử bên trong SpEL.

Ví dụ, prefix #{ và suffix } phù hợp với template SpEL thông dụng. Nếu nội dung thường xuyên chứa cú pháp tương tự, cặp [[ và ]] có thể dễ phân biệt hơn.

Delimiter không phải cơ chế bảo mật. Việc thay delimiter không hạn chế những method, bean hoặc type mà biểu thức có thể truy cập.

## 13. Lỗi thường gặp khi parse template

### Thiếu suffix

Nếu template mở đầu một đoạn biểu thức nhưng không có delimiter đóng tương ứng, parser không thể xác định ranh giới của đoạn đó và có thể phát sinh lỗi parsing.

Ví dụ không hoàn chỉnh:

~~~text
Tổng tiền: #{#price * #quantity
~~~

Cần bổ sung suffix đúng theo ParserContext:

~~~text
Tổng tiền: #{#price * #quantity}
~~~

### Dùng sai ParserContext

Nếu template dùng [[ và ]] nhưng parser được cấu hình với TemplateParserContext mặc định, parser sẽ tìm #{ và } thay vì delimiter thực tế.

Hãy bảo đảm parser nhận đúng context:

~~~java
new TemplateParserContext("[[", "]]")
~~~

### Cú pháp SpEL bên trong không hợp lệ

Delimiter có thể đúng nhưng nội dung biểu thức vẫn sai cú pháp:

~~~text
Tổng tiền: #{#price * }
~~~

Lỗi thuộc phần biểu thức bên trong, không phải do bản thân delimiter.

### Lỗi evaluation sau khi parsing

Template có thể parse thành công nhưng khi gọi getValue lại gặp vấn đề như biến chưa có, property không tồn tại, method không phù hợp hoặc chuyển đổi kiểu thất bại.

Khi debug, hãy xác định lỗi xảy ra ở parseExpression hay getValue trước khi kiểm tra nội dung tương ứng.

## 14. Phân biệt ParserContext và EvaluationContext

Hai context này có tên gần giống nhưng phục vụ hai giai đoạn khác nhau:

| Thành phần | Giai đoạn | Trách nhiệm |
|---|---|---|
| ParserContext | Parsing | Cho biết đầu vào là template và định nghĩa prefix/suffix |
| EvaluationContext | Evaluation | Cung cấp root object, variables, resolver, accessor và converter |
| Expression | Sau parsing | Đại diện cho biểu thức hoặc template đã phân tích |
| getValue | Evaluation | Đánh giá biểu thức và trả kết quả |

Ví dụ:

~~~java
ParserContext parserContext =
    new TemplateParserContext();

StandardEvaluationContext evaluationContext =
    new StandardEvaluationContext();

evaluationContext.setVariable("name", "Linh");

Expression template = parser.parseExpression(
    "Xin chào #{#name}!",
    parserContext
);

String result =
    template.getValue(evaluationContext, String.class);
~~~

ParserContext không biết name là Linh. EvaluationContext không quyết định delimiter của template. Mỗi thành phần cung cấp đúng thông tin cho giai đoạn của nó.

## 15. Tái sử dụng template đã parse

Nếu một template được dùng nhiều lần, có thể parse một lần rồi tái sử dụng Expression với các EvaluationContext hoặc giá trị biến khác nhau.

~~~java
ExpressionParser parser =
    new SpelExpressionParser();

Expression template = parser.parseExpression(
    "Xin chào #{#customerName}, mã đơn hàng #{#orderNumber}.",
    new TemplateParserContext()
);

StandardEvaluationContext firstContext =
    new StandardEvaluationContext();

firstContext.setVariable("customerName", "Linh");
firstContext.setVariable("orderNumber", "ORD-100");

StandardEvaluationContext secondContext =
    new StandardEvaluationContext();

secondContext.setVariable("customerName", "Minh");
secondContext.setVariable("orderNumber", "ORD-101");

String firstMessage =
    template.getValue(firstContext, String.class);

String secondMessage =
    template.getValue(secondContext, String.class);
~~~

Kết quả:

~~~text
Xin chào Linh, mã đơn hàng ORD-100.
Xin chào Minh, mã đơn hàng ORD-101.
~~~

Expression giữ cấu trúc template đã parse. Dữ liệu runtime đến từ context của từng lần đánh giá.

Nếu dùng context có variables thay đổi, cần quản lý vòng đời context phù hợp để tránh một lần cập nhật ảnh hưởng đến lần đánh giá khác.

## 16. Template expression trong cấu hình Spring

Template expression thường xuất hiện trong annotation @Value:

~~~java
@Component
public class GreetingSettings {

    @Value("#{systemProperties['user.language']}")
    private String language;

    public String getLanguage() {
        return language;
    }
}
~~~

Trong môi trường Spring, cơ chế expression tích hợp với container xử lý biểu thức trong annotation. Phần #{...} đánh dấu đoạn SpEL cần đánh giá.

Cần phân biệt hai trường hợp:

- Một chuỗi template do ứng dụng chủ động parse bằng ExpressionParser cần truyền ParserContext.
- Biểu thức trong @Value được xử lý bởi cơ chế tích hợp của Spring theo quy ước annotation.

Không nên mặc định mọi chuỗi chứa #{...} đều tự động được parse như template khi gọi ExpressionParser trực tiếp.

## 17. Những nhầm lẫn thường gặp

**Nhầm lẫn 1: ParserContext cung cấp biến cho biểu thức.**  
ParserContext chỉ định chế độ template và delimiter. Variables, root object và resolver thuộc EvaluationContext.

**Nhầm lẫn 2: TemplateParserContext mặc định dùng bất kỳ delimiter nào.**  
Constructor mặc định dùng prefix #{ và suffix }. Muốn dùng cặp khác, truyền rõ hai chuỗi vào constructor.

**Nhầm lẫn 3: Thay delimiter làm thay đổi cú pháp SpEL bên trong.**  
Delimiter chỉ đánh dấu ranh giới. Nội dung bên trong vẫn dùng cú pháp SpEL thông thường.

**Nhầm lẫn 4: Không truyền ParserContext thì parser tự nhận diện template.**  
Overload parseExpression chỉ có chuỗi xử lý toàn bộ đầu vào như một biểu thức thông thường.

**Nhầm lẫn 5: Parse thành công nghĩa là evaluation chắc chắn thành công.**  
Biến, property, method và kiểu dữ liệu chỉ được xử lý theo môi trường runtime khi đánh giá.

**Nhầm lẫn 6: Delimiter tùy chỉnh giới hạn quyền truy cập.**  
Delimiter không phải cơ chế bảo mật. Quyền truy cập phụ thuộc EvaluationContext và các resolver/accessor được cấu hình.

## 18. Ghi nhớ

- Template expression kết hợp văn bản literal với các đoạn SpEL được đánh dấu bằng delimiter.
- ParserContext cho parser biết đầu vào có phải template hay không và định nghĩa prefix/suffix.
- TemplateParserContext mặc định dùng prefix #{ và suffix }.
- Có thể tùy chỉnh delimiter bằng constructor TemplateParserContext(prefix, suffix).
- Overload parseExpression(expressionString, parserContext) dùng ParserContext để phân tích template.
- Nội dung trong delimiter vẫn tuân theo cú pháp SpEL thông thường.
- EvaluationContext cung cấp root object, variables và các cơ chế cần thiết khi đánh giá.
- Template có thể chứa nhiều đoạn biểu thức và kết quả được ghép theo thứ tự với văn bản cố định.
- Parse error khác evaluation error; cần xác định đúng giai đoạn khi debug.
- Delimiter cần nhất quán và dễ phân biệt, nhưng không tạo ra ranh giới bảo mật.

Khi xây dựng template expression, hãy xác định văn bản cố định, chọn cặp delimiter rõ ràng, truyền ParserContext phù hợp lúc parseExpression, rồi cung cấp dữ liệu runtime qua EvaluationContext khi gọi getValue.
