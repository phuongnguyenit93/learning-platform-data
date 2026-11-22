# Đọc một biểu thức từ chuỗi với parser

Trong SpEL, **ExpressionParser** là điểm bắt đầu để chuyển một chuỗi ký tự thành một đối tượng biểu thức có thể được đánh giá. Ứng dụng đưa cú pháp SpEL vào parser thông qua phương thức **parseExpression(...)**. Kết quả trả về là một **Expression**, đại diện cho biểu thức đã được phân tích.

Quá trình này có hai giai đoạn cần phân biệt:

1. **Parse:** parser đọc chuỗi, kiểm tra cú pháp và xây dựng biểu diễn biểu thức.
2. **Evaluate:** ứng dụng yêu cầu đối tượng Expression tính giá trị trong một evaluation context và/hoặc trên một root object cụ thể.

Parser không tự thực thi biểu thức ngay khi nhận chuỗi. Việc phân tích cú pháp tạo ra Expression; kết quả chỉ được tính khi ứng dụng gọi một phương thức như **getValue(...)** hoặc **setValue(...)**.

## Tạo ExpressionParser

API parser phổ biến của Spring là **SpelExpressionParser**, thuộc package **org.springframework.expression.spel.standard**. Interface **ExpressionParser** nằm trong package **org.springframework.expression**.

Ví dụ tối thiểu:

~~~java
import org.springframework.expression.Expression;
import org.springframework.expression.ExpressionParser;
import org.springframework.expression.spel.standard.SpelExpressionParser;

ExpressionParser parser = new SpelExpressionParser();

Expression expression =
        parser.parseExpression("'Hello ' + 'Spring SpEL'");

String result = expression.getValue(String.class);
~~~

Chuỗi truyền vào **parseExpression(...)** là một biểu thức SpEL. Trong ví dụ, hai string literal được nối với nhau. Parser trả về Expression; lời gọi **getValue(String.class)** mới yêu cầu đánh giá biểu thức và lấy kết quả dưới kiểu String.

Kết quả là **Hello Spring SpEL**. Ví dụ này không cần root object hay evaluation context vì biểu thức chỉ chứa literal và phép toán trên literal.

## parseExpression nhận gì và trả về gì?

Phương thức cơ bản có dạng:

~~~java
Expression parseExpression(String expressionString);
~~~

Tham số **expressionString** là chuỗi chứa cú pháp SpEL. Kết quả là một đối tượng triển khai interface **Expression**. Interface này cung cấp các thao tác để đọc giá trị, đọc giá trị theo kiểu mong muốn, kiểm tra khả năng ghi và cập nhật giá trị trong những trường hợp biểu thức cho phép.

Một vài chuỗi biểu thức đơn giản:

| Chuỗi đưa vào parser | Ý nghĩa |
|---|---|
| **'Spring'** | Một string literal |
| **10 * 5** | Phép nhân số học |
| **name** | Đọc property name trên root object |
| **items[0]** | Truy cập phần tử đầu tiên của collection hoặc mảng phù hợp |
| **status == 'ACTIVE'** | So sánh giá trị status với chuỗi ACTIVE |
| **name.toUpperCase()** | Gọi instance method nếu evaluation context cho phép |

Các chuỗi trong cột đầu là cú pháp SpEL được truyền dưới dạng Java String. Trong mã Java, cần đặt dấu nháy cho chuỗi Java bên ngoài và giữ dấu nháy đơn của string literal SpEL bên trong khi cần.

## Đánh giá biểu thức không cần root object

Nếu biểu thức chỉ chứa literal, toán tử hoặc các giá trị không phụ thuộc dữ liệu bên ngoài, có thể lấy kết quả trực tiếp:

~~~java
ExpressionParser parser = new SpelExpressionParser();

Expression expression =
        parser.parseExpression("10 * (5 + 2)");

Integer result = expression.getValue(Integer.class);
~~~

Parser tạo Expression từ chuỗi. Khi gọi **getValue(Integer.class)**, SpEL tính kết quả và yêu cầu trả về kiểu Integer.

Có thể dùng **getValue()** để nhận kết quả dưới dạng Object:

~~~java
Object result = expression.getValue();
~~~

Cách lấy kiểu tổng quát hữu ích khi chưa biết trước kiểu kết quả, nhưng trong mã ứng dụng, chỉ định kiểu mong muốn thường giúp thể hiện rõ hợp đồng của biểu thức. Spring sẽ sử dụng cơ chế chuyển đổi kiểu của evaluation context khi cần và khi phép chuyển đổi được hỗ trợ.

## Đánh giá biểu thức trên root object

Nhiều biểu thức cần đọc dữ liệu của một object. Khi đó, truyền root object vào phương thức lấy giá trị:

~~~java
public class Product {
    private final String name;
    private final BigDecimal price;

    public Product(String name, BigDecimal price) {
        this.name = name;
        this.price = price;
    }

    public String getName() {
        return name;
    }

    public BigDecimal getPrice() {
        return price;
    }
}
~~~

~~~java
Product product =
        new Product("Keyboard", new BigDecimal("45.00"));

ExpressionParser parser = new SpelExpressionParser();
Expression expression = parser.parseExpression("name");

String productName =
        expression.getValue(product, String.class);
~~~

Ở đây, **product** là root object. Biểu thức **name** yêu cầu SpEL đọc property tương ứng từ object. Với JavaBean thông thường, việc đọc property có thể được thực hiện thông qua getter.

Nếu biểu thức cần truy cập nhiều thuộc tính hoặc thực hiện một phép tính, cú pháp vẫn được phân tích theo cùng cách:

~~~java
Expression expression =
        parser.parseExpression("price > 0 and name != null");

Boolean valid =
        expression.getValue(product, Boolean.class);
~~~

Root object cung cấp dữ liệu mà biểu thức tham chiếu. Nếu biểu thức nhắc đến một property không tồn tại hoặc thao tác không phù hợp với kiểu dữ liệu thực tế, lỗi thường xuất hiện ở giai đoạn evaluation, dù chuỗi đã parse thành công.

## Kết hợp parser với EvaluationContext

**EvaluationContext** cung cấp môi trường để đánh giá biểu thức. Context có thể chứa root object, biến, property accessor, method resolver, type converter và những thành phần khác tùy implementation.

Ví dụ, dùng **StandardEvaluationContext** để đặt root object và một biến:

~~~java
Product product =
        new Product("Keyboard", new BigDecimal("45.00"));

StandardEvaluationContext context =
        new StandardEvaluationContext(product);

context.setVariable("minimumPrice", new BigDecimal("20.00"));

ExpressionParser parser = new SpelExpressionParser();
Expression expression =
        parser.parseExpression("price >= #minimumPrice");

Boolean accepted =
        expression.getValue(context, Boolean.class);
~~~

Trong biểu thức, **#minimumPrice** tham chiếu đến biến đã được thêm vào context. Root object được đặt khi khởi tạo context, vì vậy biểu thức có thể đọc property **price** mà không cần truyền root object thêm lần nữa.

Một cách khác là truyền context và root object ngay tại lần đánh giá:

~~~java
EvaluationContext context = new StandardEvaluationContext();
Boolean accepted =
        expression.getValue(context, product, Boolean.class);
~~~

Chọn cách nào tùy vào việc root object có cố định trong context hay thay đổi theo từng lần gọi. Điều quan trọng là biểu thức phải được đánh giá trong context có đủ dữ liệu và khả năng truy cập mà nó yêu cầu.

## Parse biểu thức và đánh giá biểu thức là hai việc khác nhau

Một chuỗi có thể hợp lệ về cú pháp SpEL nhưng không thể đánh giá thành công trên một object cụ thể.

Ví dụ, parser có thể phân tích chuỗi **unknownProperty > 10** vì cấu trúc biểu thức hợp lệ. Khi đánh giá trên root object không có property **unknownProperty**, SpEL có thể phát sinh lỗi truy cập property.

Vì vậy, nên phân biệt hai nhóm lỗi:

- **Lỗi parse:** chuỗi không tuân theo cú pháp SpEL, chẳng hạn thiếu dấu ngoặc hoặc toán tử không hợp lệ. Parser thường phát sinh **ParseException**.
- **Lỗi evaluation:** cú pháp đã parse nhưng thao tác không thực hiện được trong dữ liệu hoặc context hiện tại, chẳng hạn property không tồn tại, gọi method không được hỗ trợ hoặc phép toán không phù hợp. SpEL thường phát sinh **EvaluationException** hoặc một lớp con cụ thể.

Ví dụ xử lý lỗi ở hai giai đoạn:

~~~java
Expression expression;

try {
    expression = parser.parseExpression(expressionText);
} catch (ParseException ex) {
    // Chuỗi biểu thức có cú pháp không hợp lệ
    throw new IllegalArgumentException("Invalid SpEL syntax", ex);
}

try {
    Object value = expression.getValue(context, rootObject);
} catch (EvaluationException ex) {
    // Biểu thức không thể được đánh giá trong context/root object này
    throw new IllegalStateException("Cannot evaluate SpEL", ex);
}
~~~

Việc tách hai giai đoạn giúp xác định lỗi nằm ở chuỗi biểu thức hay ở dữ liệu và môi trường thực thi.

## Đọc kết quả theo kiểu mong muốn

Interface Expression có các overload của **getValue(...)** cho phép chỉ định kiểu kết quả:

~~~java
Expression expression =
        parser.parseExpression("price * 2");

BigDecimal doubledPrice =
        expression.getValue(context, product, BigDecimal.class);
~~~

Khi chỉ định kiểu đích, ứng dụng thể hiện rõ kết quả mong đợi. SpEL có thể sử dụng type converter của context để chuyển đổi kết quả nếu có phép chuyển đổi phù hợp. Nếu không thể tính hoặc chuyển đổi sang kiểu yêu cầu, evaluation sẽ thất bại.

Không nên coi tham số kiểu là cách ép bất kỳ kết quả nào thành bất kỳ kiểu nào. Kiểu kết quả phải tương thích với giá trị biểu thức hoặc có chuyển đổi được hỗ trợ.

## Dùng parser với biểu thức template

Thông thường, **parseExpression(String)** nhận một biểu thức SpEL thuần. Nếu chuỗi chứa văn bản thông thường xen kẽ với các đoạn biểu thức, hãy truyền thêm **ParserContext**.

Ví dụ dùng **TemplateParserContext**:

~~~java
import org.springframework.expression.common.TemplateParserContext;

Expression template = parser.parseExpression(
        "Xin chào, #{#name}!",
        new TemplateParserContext());

StandardEvaluationContext context =
        new StandardEvaluationContext();
context.setVariable("name", "An");

String message = template.getValue(context, String.class);
~~~

Trong template này, phần văn bản bên ngoài được giữ nguyên; đoạn nằm trong **#{...}** được parse và đánh giá như SpEL. Kết quả là **Xin chào, An!**.

Cần phân biệt dấu **#{...}** trong template với việc gọi parser thông thường. Nếu truyền **#{...}** vào **parseExpression(String)** mà không cung cấp template parser context, chuỗi được hiểu theo cú pháp biểu thức thuần và có thể không parse như mong đợi.

## Parse một lần, đánh giá nhiều lần

Nếu cùng một biểu thức được sử dụng lặp lại, nên giữ lại đối tượng Expression sau khi parse thay vì tạo parser và parse lại chuỗi trong mỗi lần gọi:

~~~java
ExpressionParser parser = new SpelExpressionParser();
Expression expression = parser.parseExpression("price >= 100");

for (Product product : products) {
    Boolean expensive = expression.getValue(product, Boolean.class);
    // Xử lý kết quả
}
~~~

Ở đây, chuỗi chỉ được parse một lần. Mỗi lần lặp, Expression được đánh giá trên một root object khác nhau. Cách tổ chức này tách phần cú pháp cố định khỏi dữ liệu thay đổi theo từng lần gọi và tránh công việc parse lặp lại.

Nếu biểu thức phụ thuộc vào biến hoặc context, cần cung cấp context phù hợp ở mỗi lần đánh giá. Không nên để biến hoặc root object cũ vô tình ảnh hưởng đến một yêu cầu mới.

## Cấu hình parser khi cần kiểm soát truy cập collection và thuộc tính null

Ngoài constructor mặc định, **SpelExpressionParser** có thể nhận **SpelParserConfiguration**. Cấu hình này điều khiển một số hành vi khi đánh giá biểu thức, ví dụ tự mở rộng collection hoặc tự tạo giá trị trung gian khi gặp property null trong những trường hợp được hỗ trợ.

~~~java
SpelParserConfiguration configuration =
        new SpelParserConfiguration(true, true);

ExpressionParser parser =
        new SpelExpressionParser(configuration);
~~~

Hai cờ trong ví dụ minh họa việc bật auto-grow cho null reference và collection. Đây là hành vi có thể làm thay đổi object hoặc collection trong lúc evaluation, nên chỉ bật khi ứng dụng thực sự cần. Nếu mục tiêu chỉ là đọc biểu thức từ chuỗi và lấy kết quả, parser mặc định thường đã đủ.

Parser configuration điều chỉnh hành vi phân tích/đánh giá của parser; nó không thay thế EvaluationContext. Root object, biến, accessor và những khả năng được expose vẫn được kiểm soát ở context.

## Lưu ý khi nhận biểu thức từ nguồn bên ngoài

Parser có thể nhận chuỗi từ cấu hình, cơ sở dữ liệu hoặc người dùng. Tuy nhiên, việc parse được một chuỗi không đồng nghĩa biểu thức đó an toàn để đánh giá trong mọi context.

Nếu biểu thức đến từ bên ngoài:

- Xác định rõ biểu thức được phép truy cập những dữ liệu nào.
- Dùng root object nhỏ, chỉ chứa dữ liệu cần thiết.
- Cân nhắc **SimpleEvaluationContext** nếu chỉ cần data binding với tập tính năng giới hạn.
- Tránh expose bean, service hoặc object có quyền thực hiện tác vụ nhạy cảm.
- Giới hạn kích thước và nguồn biểu thức, đồng thời xử lý cả lỗi parse lẫn lỗi evaluation.
- Chỉ bật các khả năng mở rộng khi use case yêu cầu và đã được kiểm soát.

**ExpressionParser** chịu trách nhiệm chuyển chuỗi thành Expression. EvaluationContext và root object mới quyết định biểu thức có thể nhìn thấy và thao tác với dữ liệu nào khi chạy.

## Kết luận

Để đọc một biểu thức SpEL từ chuỗi, tạo **ExpressionParser**, gọi **parseExpression(...)** và nhận về một **Expression**. Sau đó, gọi **getValue(...)** với kiểu kết quả, root object và evaluation context phù hợp để đánh giá biểu thức.

Việc tách parse khỏi evaluate giúp tái sử dụng Expression, phân loại lỗi rõ ràng và chủ động kiểm soát dữ liệu đầu vào. Với biểu thức đơn giản, parser mặc định là đủ; với biểu thức phụ thuộc dữ liệu, cần cung cấp root object hoặc context. Khi chuỗi đến từ nguồn bên ngoài, hãy giới hạn bề mặt thao tác bằng context và các thành phần truy cập phù hợp.
