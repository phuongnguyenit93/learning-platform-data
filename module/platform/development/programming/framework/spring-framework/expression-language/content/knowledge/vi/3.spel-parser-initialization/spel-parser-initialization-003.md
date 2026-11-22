# ParserContext cho template expression trong Spring Expression Language

Spring Expression Language (SpEL) thường được dùng để đánh giá một biểu thức độc lập, chẳng hạn total >= #minimum. Tuy nhiên, trong nhiều tình huống ứng dụng cần tạo ra một chuỗi văn bản có cả phần cố định lẫn phần giá trị động. Ví dụ: “Xin chào Linh, đơn hàng của bạn có tổng tiền là 125000”.

Để xử lý kiểu đầu vào này, SpEL hỗ trợ **template expression**. Một template chứa văn bản thông thường và các đoạn SpEL được đặt giữa cặp dấu phân cách. **ParserContext** cho parser biết cách nhận diện những đoạn biểu thức nằm bên trong template.

ParserContext thuộc giai đoạn phân tích cú pháp. Nó định nghĩa cách đọc chuỗi đầu vào, còn EvaluationContext cung cấp dữ liệu và môi trường để đánh giá các biểu thức sau khi đã phân tích.

## 1. ParserContext là gì?

ParserContext là một interface trong Spring Expression cung cấp ba thông tin cho ExpressionParser:

- **isTemplate():** cho biết chuỗi đầu vào có phải template hay không.
- **getExpressionPrefix():** trả về chuỗi ký tự mở đầu một đoạn biểu thức.
- **getExpressionSuffix():** trả về chuỗi ký tự kết thúc một đoạn biểu thức.

ParserContext giúp parser phân biệt phần văn bản thông thường với phần cần được phân tích như một biểu thức SpEL.

Spring cung cấp lớp TemplateParserContext để triển khai cách phân tích template phổ biến. Constructor mặc định sử dụng:

- Prefix: `#{`
- Suffix: `}`

Ví dụ, trong chuỗi:

~~~text
Xin chào #{'Linh'}!
~~~

phần “Xin chào ” và dấu chấm than là văn bản cố định. Đoạn #{'Linh'} là một biểu thức SpEL và được đánh giá thành chuỗi Linh.

## 2. Vì sao cần ParserContext?

Nếu ứng dụng chỉ cần đánh giá một biểu thức độc lập, parser có thể nhận trực tiếp chuỗi biểu thức:

~~~java
ExpressionParser parser = new SpelExpressionParser();

Expression expression =
    parser.parseExpression("100 + 25");

Integer result = expression.getValue(Integer.class);
~~~

Ở trường hợp này, toàn bộ chuỗi 100 + 25 là cú pháp SpEL. Kết quả là số 125.

Nhưng nếu đầu vào là một câu hoàn chỉnh có văn bản và biểu thức xen kẽ:

~~~text
Xin chào #{'Linh'}, bạn có #{3 + 2} thông báo mới.
~~~

parser cần biết phần nào là văn bản để giữ nguyên và phần nào là biểu thức để đánh giá. Đây là lý do ứng dụng truyền thêm ParserContext vào overload parseExpression:

~~~java
ExpressionParser parser = new SpelExpressionParser();
ParserContext parserContext = new TemplateParserContext();

Expression expression = parser.parseExpression(
    "Xin chào #{'Linh'}, bạn có #{3 + 2} thông báo mới.",
    parserContext
);

String message = expression.getValue(String.class);
~~~

Kết quả:

~~~text
Xin chào Linh, bạn có 5 thông báo mới.
~~~

ParserContext định nghĩa quy tắc phân tách template. Nó không tự đánh giá biểu thức và cũng không cung cấp giá trị cho các biến được tham chiếu bên trong template.

## 3. Cách template expression được phân tích

Một template expression có thể gồm nhiều đoạn nối tiếp nhau:

1. Văn bản cố định trước đoạn biểu thức đầu tiên.
2. Đoạn biểu thức nằm giữa prefix và suffix.
3. Văn bản cố định nằm giữa hai đoạn biểu thức.
4. Các đoạn biểu thức tiếp theo.
5. Văn bản cố định ở cuối chuỗi.

Ví dụ:

~~~text
Đơn hàng #{#orderId} của #{#customerName} có tổng tiền #{#amount}.
~~~

Có thể chia chuỗi thành các phần:

| Phần | Nội dung | Cách xử lý |
|---|---|---|
| Văn bản 1 | Đơn hàng | Giữ nguyên |
| Biểu thức 1 | #orderId | Phân tích và đánh giá bằng SpEL |
| Văn bản 2 | của | Giữ nguyên |
| Biểu thức 2 | #customerName | Phân tích và đánh giá bằng SpEL |
| Văn bản 3 | có tổng tiền | Giữ nguyên |
| Biểu thức 3 | #amount | Phân tích và đánh giá bằng SpEL |
| Văn bản 4 | . | Giữ nguyên |

Trong quá trình parsing, parser nhận diện prefix và suffix, tách các đoạn văn bản khỏi các đoạn biểu thức, rồi phân tích cú pháp SpEL cho từng đoạn biểu thức. Đối tượng Expression được trả về có thể kết hợp nhiều phần để khi đánh giá, các giá trị động được ghép cùng văn bản cố định thành chuỗi hoàn chỉnh.

Điểm cần phân biệt là phần văn bản bên ngoài dấu phân cách không được xem như một biểu thức SpEL. Chỉ nội dung nằm trong đoạn biểu thức mới được parser xử lý theo cú pháp SpEL.

## 4. Sử dụng TemplateParserContext với dấu phân cách mặc định

Đây là cách sử dụng thông dụng nhất:

~~~java
import org.springframework.expression.Expression;
import org.springframework.expression.ExpressionParser;
import org.springframework.expression.ParserContext;
import org.springframework.expression.common.TemplateParserContext;
import org.springframework.expression.spel.standard.SpelExpressionParser;

public class TemplateExample {
    public static void main(String[] args) {
        ExpressionParser parser = new SpelExpressionParser();

        ParserContext parserContext = new TemplateParserContext();

        Expression expression = parser.parseExpression(
            "Xin chào #{'Linh'}!",
            parserContext
        );

        String result = expression.getValue(String.class);

        System.out.println(result);
    }
}
~~~

Kết quả:

~~~text
Xin chào Linh!
~~~

Các thành phần có vai trò riêng:

- SpelExpressionParser nhận chuỗi đầu vào và thực hiện parsing.
- TemplateParserContext cho biết đây là template và sử dụng cặp dấu #{ ... }.
- parseExpression tạo Expression từ template.
- getValue yêu cầu đánh giá các đoạn SpEL và trả về chuỗi đã ghép.

Có thể dùng constructor mặc định của TemplateParserContext khi chấp nhận cú pháp template chuẩn của SpEL.

## 5. Tùy chỉnh prefix và suffix

Không phải lúc nào ứng dụng cũng muốn sử dụng cặp #{ và }. TemplateParserContext cho phép chỉ định cặp dấu phân cách khác bằng constructor nhận hai chuỗi:

~~~java
ParserContext parserContext =
    new TemplateParserContext("[[", "]]");

Expression expression = parser.parseExpression(
    "Xin chào [[ 'Linh' ]]!",
    parserContext
);

String result = expression.getValue(String.class);
~~~

Trong ví dụ này:

- Prefix là [[.
- Suffix là ]].
- Phần văn bản “Xin chào ” và dấu ! được giữ nguyên.
- Nội dung nằm giữa [[ và ]] được phân tích như một biểu thức SpEL.

Kết quả vẫn là:

~~~text
Xin chào Linh!
~~~

Cặp dấu phân cách tùy chỉnh hữu ích khi cú pháp mặc định xung đột với định dạng văn bản hoặc ngôn ngữ template khác trong ứng dụng.

Nên chọn prefix và suffix dễ nhận biết, ít xuất hiện trong văn bản thông thường. Nếu nhiều hệ thống cùng xử lý một chuỗi, cần thống nhất cặp dấu phân cách để tránh việc một thành phần hiểu nhầm nội dung của thành phần khác.

## 6. Biểu thức bên trong template vẫn sử dụng cú pháp SpEL

ParserContext chỉ xác định ranh giới của đoạn biểu thức. Nội dung nằm trong đoạn đó vẫn tuân theo cú pháp SpEL thông thường.

Do đó, một template có thể chứa:

| Thành phần SpEL | Ví dụ trong template | Ý nghĩa |
|---|---|---|
| Biến | `#{#customerName}` | Lấy biến từ EvaluationContext |
| Root property | `#{name}` | Đọc thuộc tính trên đối tượng hiện tại |
| Toán tử | `#{#amount >= #minimum}` | Thực hiện phép so sánh |
| Phép tính | `#{#price * #quantity}` | Tính giá trị |
| Gọi phương thức | `#{#customerName.toUpperCase()}` | Gọi phương thức trên giá trị |
| Truy cập collection | `#{#items.size()}` | Lấy thông tin từ collection |

Những khả năng này vẫn chịu sự kiểm soát của EvaluationContext. Nếu context không có biến được tham chiếu hoặc không hỗ trợ thao tác cần thiết, evaluation có thể phát sinh lỗi dù template đã được phân tích thành công.

## 7. Kết hợp ParserContext với EvaluationContext

ParserContext và EvaluationContext thường được sử dụng cùng nhau nhưng giải quyết hai vấn đề khác nhau:

| Thành phần | Thời điểm sử dụng | Trách nhiệm |
|---|---|---|
| ParserContext | Khi gọi parseExpression | Cho parser biết chuỗi có phải template và dấu phân cách biểu thức là gì |
| EvaluationContext | Khi gọi getValue | Cung cấp root object, biến, accessor, resolver và cơ chế chuyển đổi |
| Expression | Sau khi parsing thành công | Đại diện cho biểu thức hoặc template đã được phân tích |
| Evaluation Result | Sau khi evaluation hoàn tất | Giá trị cuối cùng của lần đánh giá |

Ví dụ hoàn chỉnh:

~~~java
import java.math.BigDecimal;

import org.springframework.expression.Expression;
import org.springframework.expression.ExpressionParser;
import org.springframework.expression.ParserContext;
import org.springframework.expression.spel.SpelEvaluationException;
import org.springframework.expression.spel.standard.SpelExpressionParser;
import org.springframework.expression.spel.support.StandardEvaluationContext;
import org.springframework.expression.common.TemplateParserContext;

public class OrderMessageExample {
    public static void main(String[] args) {
        // 1. Khởi tạo parser và ParserContext.
        ExpressionParser parser = new SpelExpressionParser();
        ParserContext parserContext = new TemplateParserContext();

        // 2. Phân tích template.
        Expression template = parser.parseExpression(
            "Đơn hàng của #{#customerName} có tổng tiền #{#amount} VND.",
            parserContext
        );

        // 3. Cung cấp dữ liệu khi đánh giá.
        StandardEvaluationContext evaluationContext =
            new StandardEvaluationContext();

        evaluationContext.setVariable("customerName", "Linh");
        evaluationContext.setVariable(
            "amount",
            new BigDecimal("125000")
        );

        // 4. Đánh giá template và nhận chuỗi.
        String message =
            template.getValue(evaluationContext, String.class);

        System.out.println(message);
    }
}
~~~

Kết quả:

~~~text
Đơn hàng của Linh có tổng tiền 125000 VND.
~~~

Trong ví dụ này, ParserContext không biết customerName là Linh hay amount là 125000. Những giá trị đó chỉ được cung cấp trong StandardEvaluationContext. Khi getValue được gọi, các đoạn SpEL được đánh giá bằng dữ liệu trong context, sau đó kết quả được ghép với phần văn bản cố định.

## 8. Dùng template với root object

Ngoài biến, template có thể tham chiếu thuộc tính trên root object. Ví dụ, giả sử có lớp Customer với getter getName() và getMembershipLevel():

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

Có thể tạo template như sau:

~~~java
Customer customer = new Customer("Linh", "GOLD");

ExpressionParser parser = new SpelExpressionParser();
ParserContext parserContext = new TemplateParserContext();

Expression template = parser.parseExpression(
    "Khách hàng #{name} có hạng #{membershipLevel}.",
    parserContext
);

StandardEvaluationContext context =
    new StandardEvaluationContext(customer);

String message = template.getValue(context, String.class);
~~~

Kết quả:

~~~text
Khách hàng Linh có hạng GOLD.
~~~

Ở đây, name và membershipLevel được đọc trên root object là customer. Nếu muốn viết rõ đối tượng gốc, có thể dùng #root.name và #root.membershipLevel.

## 9. Nhiều đoạn biểu thức trong cùng một template

Một template có thể có nhiều đoạn SpEL. Mỗi đoạn được đánh giá trong cùng môi trường đánh giá của lần gọi getValue, trừ khi chính biểu thức làm thay đổi đối tượng hiện tại trong một cấu trúc như selection hoặc projection.

Ví dụ:

~~~java
ParserContext parserContext = new TemplateParserContext();

Expression template = parser.parseExpression(
    "Mã: #{#code}; số lượng: #{#quantity}; thành tiền: #{#price * #quantity}",
    parserContext
);

StandardEvaluationContext context =
    new StandardEvaluationContext();

context.setVariable("code", "SP-100");
context.setVariable("quantity", 3);
context.setVariable("price", 25000);

String message = template.getValue(context, String.class);
~~~

Kết quả:

~~~text
Mã: SP-100; số lượng: 3; thành tiền: 75000
~~~

Các đoạn biểu thức có thể dùng chung biến và root object đã đăng ký. Văn bản cố định được giữ nguyên, còn các đoạn động được thay bằng giá trị đánh giá tương ứng.

## 10. Điều gì xảy ra nếu không truyền ParserContext?

Nếu gọi overload chỉ có một tham số:

~~~java
Expression expression =
    parser.parseExpression("Xin chào #{'Linh'}!");
~~~

parser xử lý toàn bộ chuỗi như một biểu thức SpEL thông thường. Nó không tự hiểu rằng “Xin chào ” là văn bản template và #{'Linh'} là một đoạn cần nội suy.

Khi đầu vào có cả văn bản tự do và biểu thức được bao quanh bởi dấu phân cách, hãy truyền ParserContext:

~~~java
Expression expression = parser.parseExpression(
    "Xin chào #{'Linh'}!",
    new TemplateParserContext()
);
~~~

Đây là khác biệt quan trọng giữa parsing biểu thức đơn lẻ và parsing template.

## 11. Lỗi trong template expression

Lỗi có thể xảy ra ở hai giai đoạn.

**Lỗi parsing:**

- Nội dung bên trong đoạn biểu thức sai cú pháp SpEL.
- Cấu trúc dấu phân cách của template không hợp lệ.
- Biểu thức con có toán tử hoặc cấu trúc không hoàn chỉnh.

Lỗi parsing xuất hiện khi gọi parseExpression.

**Lỗi evaluation:**

- Biến được tham chiếu chưa có trong context.
- Root object hoặc thuộc tính không phù hợp.
- Phương thức được gọi không tồn tại hoặc không thể gọi với các đối số hiện có.
- Context không hỗ trợ thao tác mà biểu thức yêu cầu.
- Chuyển đổi kiểu không thực hiện được.

Lỗi evaluation xuất hiện khi gọi getValue.

Khi xử lý lỗi, cần xác định lỗi xảy ra trước hay sau khi Expression được tạo thành công. Sau đó kiểm tra đúng phần tương ứng: chuỗi template và dấu phân cách khi parsing; dữ liệu, context và các thao tác khi evaluation.

## 12. Lưu ý khi sử dụng trong ứng dụng

### Tái sử dụng Expression

Nếu cùng một template được dùng nhiều lần, ứng dụng có thể parse một lần rồi tái sử dụng Expression. Mỗi lần xử lý, cung cấp context phù hợp với dữ liệu của lần đó.

~~~java
ExpressionParser parser = new SpelExpressionParser();

Expression template = parser.parseExpression(
    "Xin chào #{#name}!",
    new TemplateParserContext()
);

StandardEvaluationContext firstContext =
    new StandardEvaluationContext();
firstContext.setVariable("name", "Linh");

StandardEvaluationContext secondContext =
    new StandardEvaluationContext();
secondContext.setVariable("name", "Minh");

String firstMessage =
    template.getValue(firstContext, String.class);

String secondMessage =
    template.getValue(secondContext, String.class);
~~~

Kết quả:

~~~text
Xin chào Linh!
Xin chào Minh!
~~~

### Chọn context phù hợp

Template không giới hạn biểu thức bên trong chỉ ở việc đọc biến. Các đoạn SpEL có thể gọi phương thức hoặc thực hiện những thao tác khác mà context cho phép. Nếu template đến từ nguồn không đáng tin cậy, cần kiểm soát những tính năng được phép sử dụng và dữ liệu có thể truy cập. SimpleEvaluationContext có thể phù hợp cho các trường hợp cần giới hạn khả năng đánh giá.

ParserContext chỉ quy định cách phân tích template. Nó không phải cơ chế bảo mật và không tự giới hạn quyền mà một đoạn SpEL có thể sử dụng.

### Chọn dấu phân cách rõ ràng

Dấu phân cách tùy chỉnh nên dễ phân biệt với văn bản xung quanh. Nếu hệ thống có nhiều bộ xử lý template, hãy thống nhất quy ước prefix và suffix để tránh một chuỗi bị hiểu theo nhiều cách.

## 13. Ghi nhớ

- ParserContext là interface mô tả quy tắc parsing của đầu vào.
- TemplateParserContext là triển khai có sẵn cho template expression, mặc định dùng prefix #{ và suffix }.
- parseExpression(expressionString, parserContext) cho parser biết cần tách văn bản cố định và các đoạn SpEL như thế nào.
- Văn bản ngoài dấu phân cách được giữ làm phần literal; nội dung bên trong được phân tích theo cú pháp SpEL.
- Có thể thay đổi prefix và suffix bằng constructor của TemplateParserContext.
- ParserContext phục vụ parsing; EvaluationContext cung cấp dữ liệu và môi trường khi đánh giá.
- Expression có thể được tái sử dụng với nhiều EvaluationContext để tạo ra kết quả khác nhau.
- Template parsing thành công không đồng nghĩa evaluation chắc chắn thành công: biến, root object, phương thức và kiểu dữ liệu vẫn phải phù hợp.

Khi xây dựng một template expression, hãy xác định rõ phần văn bản cố định, phần biểu thức động, cặp dấu phân cách, rồi cung cấp context phù hợp lúc gọi getValue. Như vậy, ParserContext đảm nhiệm đúng vai trò kết nối chuỗi template với cú pháp SpEL.
