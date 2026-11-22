# So sánh lớn hơn, nhỏ hơn và các biến thể có bằng

Trong Spring Expression Language (SpEL), các toán tử quan hệ dùng để xác định một giá trị có lớn hơn, nhỏ hơn hoặc nằm ở một phía của ngưỡng so sánh hay không. Bốn toán tử cơ bản là **>**, **<**, **>=** và **<=**. Mỗi phép so sánh trả về một giá trị Boolean, vì vậy chúng thường được dùng trong điều kiện cấu hình, biểu thức phân quyền, cache hoặc những điểm tích hợp Spring hỗ trợ SpEL.

Khi sử dụng các toán tử này, cần chú ý kiểu của hai toán hạng, trường hợp bằng nhau, giá trị null và ý nghĩa của dữ liệu được so sánh. Một biểu thức có thể đúng cú pháp nhưng vẫn không đánh giá được nếu hai giá trị không tương thích.

## Ý nghĩa của bốn toán tử

| Toán tử | Ý nghĩa | Điều kiện trả về true |
|---|---|---|
| **>** | Lớn hơn | Vế trái có giá trị lớn hơn vế phải |
| **<** | Nhỏ hơn | Vế trái có giá trị nhỏ hơn vế phải |
| **>=** | Lớn hơn hoặc bằng | Vế trái lớn hơn hoặc bằng vế phải |
| **<=** | Nhỏ hơn hoặc bằng | Vế trái nhỏ hơn hoặc bằng vế phải |

Hai toán tử **>** và **<** là phép so sánh nghiêm ngặt. Nếu hai giá trị bằng nhau, cả hai biểu thức đều trả về false. Hai toán tử **>=** và **<=** bao gồm cả trường hợp hai giá trị bằng nhau.

~~~java
ExpressionParser parser = new SpelExpressionParser();

Boolean greater = parser.parseExpression("10 > 5")
        .getValue(Boolean.class);       // true

Boolean less = parser.parseExpression("3 < 8")
        .getValue(Boolean.class);       // true

Boolean greaterOrEqual = parser.parseExpression("10 >= 10")
        .getValue(Boolean.class);       // true

Boolean lessOrEqual = parser.parseExpression("5 <= 4")
        .getValue(Boolean.class);       // false
~~~

Các biểu thức trên chỉ dùng literal nên không cần root object. Khi biểu thức tham chiếu đến property hoặc biến, SpEL lấy các giá trị đó từ evaluation context tương ứng.

## So sánh giá trị số

Các toán tử quan hệ thường được dùng để so sánh số nguyên, số thực hoặc các kiểu số khác. Toán hạng có thể là literal trong biểu thức, property của root object hoặc biến được đặt trong EvaluationContext.

~~~java
ExpressionParser parser = new SpelExpressionParser();

Boolean enoughStock =
        parser.parseExpression("stock > 0")
                .getValue(product, Boolean.class);

Boolean withinBudget =
        parser.parseExpression("price <= 100")
                .getValue(product, Boolean.class);
~~~

Trong ví dụ này, **stock** và **price** là các property được đọc từ object product; 0 và 100 là literal. Nếu stock lớn hơn 0, biểu thức đầu tiên trả về true. Nếu price nhỏ hơn hoặc bằng 100, biểu thức thứ hai trả về true.

SpEL hỗ trợ so sánh các giá trị số theo quy tắc số học của nó. Khi dùng nhiều kiểu số, hãy xác định rõ kiểu dữ liệu đầu vào và kiểu kết quả mong muốn. Không nên dựa vào việc một chuỗi như **"100"** tự động được hiểu là số 100 trong mọi ngữ cảnh. Nếu dữ liệu đến từ form, JSON hoặc database dưới dạng chuỗi, hãy xác thực và chuyển đổi nó sang kiểu số trước khi đánh giá.

## So sánh số nguyên với số thực

Có thể so sánh literal nguyên với literal thập phân:

~~~java
Boolean result =
        parser.parseExpression("10 >= 10.0")
                .getValue(Boolean.class);
~~~

Biểu thức trả về true vì hai toán hạng có cùng giá trị số. Kiểu literal có thể khác nhau nhưng SpEL có cơ chế xử lý so sánh số tương ứng.

Với Float và Double, cần lưu ý sai số biểu diễn dấu phẩy động. Một giá trị tính toán có thể nằm rất gần ngưỡng nhưng không bằng chính xác giá trị thập phân mà người đọc mong đợi. Nếu quy tắc phụ thuộc vào ranh giới chính xác, chẳng hạn số tiền, hãy cân nhắc BigDecimal hoặc chuẩn hóa giá trị theo chính sách nghiệp vụ trước khi so sánh.

Ví dụ với BigDecimal được cung cấp qua biến:

~~~java
StandardEvaluationContext context =
        new StandardEvaluationContext();

context.setVariable("price", new BigDecimal("100.00"));
context.setVariable("limit", new BigDecimal("100.0"));

Expression expression =
        parser.parseExpression("#price <= #limit");

Boolean withinLimit =
        expression.getValue(context, Boolean.class);
~~~

Phép so sánh xét giá trị số học. Scale khác nhau của hai BigDecimal không làm thay đổi việc chúng có cùng giá trị về mặt số học. Nếu cần quy tắc về scale hoặc làm tròn, hãy thực hiện và kiểm soát rõ trong Java.

## So sánh thuộc tính của root object

Trong ứng dụng, điều kiện thường phụ thuộc vào trạng thái của một object. Ví dụ, kiểm tra đơn hàng có vượt ngưỡng miễn phí giao hàng hay không:

~~~java
public class Order {
    private final BigDecimal total;

    public Order(BigDecimal total) {
        this.total = total;
    }

    public BigDecimal getTotal() {
        return total;
    }
}
~~~

~~~java
Order order = new Order(new BigDecimal("250.00"));

ExpressionParser parser = new SpelExpressionParser();
Expression expression =
        parser.parseExpression("total >= 200");

Boolean freeShipping =
        expression.getValue(order, Boolean.class);
~~~

Đối tượng order được dùng làm root object. SpEL đọc property total thông qua cơ chế truy cập property phù hợp, so sánh với literal 200 và trả về Boolean. Cùng Expression có thể được tái sử dụng với các đơn hàng khác nhau; kết quả sẽ phụ thuộc giá trị total của từng object.

## Dùng biến làm ngưỡng

Nếu ngưỡng thay đổi theo cấu hình hoặc theo từng yêu cầu, có thể đặt nó trong EvaluationContext thay vì ghi trực tiếp vào biểu thức:

~~~java
Order order = new Order(new BigDecimal("250.00"));

StandardEvaluationContext context =
        new StandardEvaluationContext(order);

context.setVariable(
        "freeShippingThreshold",
        new BigDecimal("200.00"));

ExpressionParser parser = new SpelExpressionParser();
Expression expression =
        parser.parseExpression("total >= #freeShippingThreshold");

Boolean freeShipping =
        expression.getValue(context, Boolean.class);
~~~

Dấu **#** dùng để tham chiếu biến trong context. Property total đến từ root object, còn freeShippingThreshold được ứng dụng đưa vào context.

Cách này giúp tách quy tắc so sánh khỏi dữ liệu cấu hình. Một Expression có thể được tái sử dụng với các context có ngưỡng khác nhau, miễn là kiểu dữ liệu và quyền truy cập phù hợp.

## So sánh chuỗi và các kiểu có thứ tự

Các toán tử quan hệ không chỉ dùng cho số. String và những kiểu Java triển khai Comparable có thể được so sánh theo quy tắc thứ tự tự nhiên của kiểu đó, nếu hai toán hạng tương thích.

Ví dụ:

~~~java
Boolean lexicalOrder =
        parser.parseExpression("'apple' < 'banana'")
                .getValue(Boolean.class);
~~~

Kết quả là true theo thứ tự từ điển của String. Phép so sánh này phân biệt chữ hoa và chữ thường, đồng thời không áp dụng quy tắc ngôn ngữ tự nhiên hoặc locale-specific collation. Vì vậy, không nên dùng nó để sắp xếp tên người, tiêu đề có dấu hoặc văn bản đa ngôn ngữ theo cách người dùng mong đợi.

Với ngày tháng, có thể so sánh các đối tượng cùng kiểu như LocalDate:

~~~java
StandardEvaluationContext context =
        new StandardEvaluationContext(order);

context.setVariable(
        "deadline",
        LocalDate.of(2026, 12, 31));

Expression expression =
        parser.parseExpression("deliveryDate <= #deadline");

Boolean onTime =
        expression.getValue(context, Boolean.class);
~~~

Property deliveryDate và biến deadline cần là các giá trị ngày tháng tương thích. Không nên chuyển ngày thành chuỗi tùy ý rồi dùng thứ tự ký tự để thay thế phép so sánh thời gian.

Với kiểu dữ liệu tùy chỉnh, cần có quy tắc so sánh nhất quán, thường thông qua Comparable. Nếu kiểu không hỗ trợ phép so sánh phù hợp, hãy chuyển đổi dữ liệu hoặc gọi một phương thức nghiệp vụ được kiểm soát.

## So sánh với null

Null không phải là số 0 hay một giá trị rỗng có thể tùy ý so sánh như các số thông thường. Trong SpEL, null được xem là nhỏ hơn mọi giá trị không null trong phép so sánh quan hệ. Tuy nhiên, trong điều kiện nghiệp vụ, nên kiểm tra null một cách tường minh để người đọc hiểu chính sách xử lý dữ liệu thiếu.

~~~java
Expression expression = parser.parseExpression(
        "score != null and score >= 80");
~~~

Biểu thức kiểm tra score khác null trước khi so sánh với ngưỡng 80. Khi property có thể null, cách viết này giúp nêu rõ rằng chỉ giá trị có dữ liệu mới được xét đạt ngưỡng.

Nếu null có ý nghĩa nghiệp vụ riêng, ví dụ chưa chấm điểm, chưa có giá hoặc chưa xác định hạn giao hàng, nên biểu diễn trạng thái đó rõ ràng thay vì để thứ tự so sánh null quyết định kết quả. Với dữ liệu có thể thiếu, cũng cần kiểm tra xem toán tử logic và context có đáp ứng đúng chính sách mong muốn hay không.

## Kết hợp toán tử quan hệ với logic

Các phép so sánh thường được kết hợp với **and**, **or** và **not** để tạo điều kiện nhiều phần:

~~~java
Expression expression = parser.parseExpression(
        "score >= 80 and score <= 100");
~~~

Biểu thức trên kiểm tra score nằm trong đoạn từ 80 đến 100, bao gồm cả hai đầu mút.

Một điều kiện về độ tuổi có thể viết:

~~~java
Expression expression = parser.parseExpression(
        "age >= 18 and age < 65");
~~~

Điều kiện chỉ đúng khi age ít nhất là 18 và nhỏ hơn 65. Việc chọn **<** hay **<=** tại ranh giới 65 thể hiện trực tiếp chính sách có bao gồm tuổi đó hay không.

Với biểu thức nhiều nhánh, dấu ngoặc giúp thể hiện nhóm điều kiện:

~~~java
"active == true and (score >= 80 or bonus >= 10)"
~~~

Ở đây active phải đúng, đồng thời score đạt ngưỡng hoặc bonus đạt ngưỡng. Việc dùng ngoặc làm rõ ý định và tránh nhầm lẫn khi đọc biểu thức dài.

## Tên toán tử dạng chữ

Ngoài ký hiệu, SpEL cung cấp các từ khóa tương ứng cho bốn toán tử quan hệ:

| Ký hiệu | Từ khóa SpEL |
|---|---|
| **>** | **gt** |
| **<** | **lt** |
| **>=** | **ge** |
| **<=** | **le** |

Ví dụ:

~~~java
Expression expression =
        parser.parseExpression("age ge 18 and age lt 65");
~~~

Biểu thức có ý nghĩa tương đương với **age >= 18 and age < 65**. Các từ khóa dạng chữ đặc biệt hữu ích khi biểu thức được nhúng trong XML, nơi các ký tự **<** và **>** có ý nghĩa riêng trong cú pháp đánh dấu và có thể cần escape.

Các từ khóa này là cú pháp SpEL, không phải tên method Java. Khi đọc một biểu thức, có thể gặp cả dạng ký hiệu và dạng chữ tùy nơi biểu thức được khai báo.

## Thứ tự ưu tiên và dấu ngoặc

Các phép toán số học có độ ưu tiên cao hơn phép so sánh. Ví dụ, biểu thức:

~~~java
"price * quantity >= 500"
~~~

sẽ tính price nhân quantity trước rồi so sánh kết quả với 500. Dùng ngoặc nếu muốn làm rõ cách nhóm phép tính hoặc kết hợp nhiều điều kiện:

~~~java
"(price * quantity) >= minimumOrderValue"
~~~

Trong cấu hình nghiệp vụ, nên ưu tiên biểu thức dễ đọc hơn việc dựa vào người đọc ghi nhớ mọi mức ưu tiên. Đặc biệt khi có cả số học, so sánh và logic, dấu ngoặc giúp hạn chế hiểu nhầm.

## Kiểu dữ liệu không tương thích và lỗi evaluation

Parser có thể chấp nhận cú pháp biểu thức nhưng lúc đánh giá SpEL vẫn có thể thất bại nếu hai toán hạng không so sánh được. Các trường hợp thường gặp gồm:

- Một property không tồn tại trên root object.
- Một property có giá trị null trong khi biểu thức thực hiện thao tác không phù hợp.
- Một vế là số, vế còn lại là chuỗi hoặc một kiểu không tương thích.
- Một kiểu tùy chỉnh không có quy tắc so sánh phù hợp.
- Dữ liệu có định dạng sai hoặc chưa được chuyển đổi trước khi đưa vào context.

Ví dụ, không nên mặc định rằng chuỗi **'80'** sẽ luôn được chuyển thành số để so sánh với một Integer:

~~~java
Expression expression =
        parser.parseExpression("score > '80'");
~~~

Nếu mục đích là so sánh số, hãy chuyển dữ liệu đầu vào sang kiểu số trong Java rồi đưa giá trị đã xác thực vào root object hoặc context. Điều đó giúp biểu thức phản ánh đúng một phép so sánh số thay vì phụ thuộc vào chuyển đổi ngầm.

Nên tách lỗi parse và lỗi evaluation khi xử lý ngoại lệ:

~~~java
Expression expression;

try {
    expression = parser.parseExpression("score >= #minimumScore");
} catch (ParseException ex) {
    throw new IllegalArgumentException("Invalid expression syntax", ex);
}

try {
    Boolean passed =
            expression.getValue(context, Boolean.class);
} catch (EvaluationException ex) {
    throw new IllegalStateException("Cannot compare values", ex);
}
~~~

ParseException cho biết chuỗi không hợp lệ về cú pháp. EvaluationException cho biết biểu thức không thể thực hiện trên dữ liệu hoặc context hiện tại. Khi ghi log, nên lưu mã biểu thức và loại lỗi, đồng thời tránh ghi toàn bộ object nếu có thông tin nhạy cảm.

## Khi nào nên dùng các toán tử này?

Các phép so sánh trong SpEL phù hợp với điều kiện ngắn, có kiểu dữ liệu rõ ràng và được đánh giá tại một điểm tích hợp Spring hỗ trợ, chẳng hạn:

- Kiểm tra giá trị có vượt ngưỡng cấu hình hay không.
- Xác định số lượng, điểm, giá hoặc tỷ lệ có nằm trong khoảng hợp lệ.
- So sánh thời hạn, ngày giao hàng hoặc mốc thời gian.
- Kết hợp một vài điều kiện để bật hoặc tắt hành vi.
- Khai báo điều kiện đơn giản trong annotation được Spring hoặc module của Spring hỗ trợ.

Nếu điều kiện có nhiều nhánh, chính sách null phức tạp, cần nhiều thao tác phụ hoặc cần giải thích vì sao một đối tượng bị từ chối, nên chuyển quyết định vào một phương thức Java có tên rõ ràng. SpEL phù hợp nhất khi biểu thức ngắn và ý nghĩa có thể hiểu ngay từ cú pháp.

## Kết luận

SpEL cung cấp bốn toán tử quan hệ **>**, **<**, **>=** và **<=** để so sánh các giá trị tương thích. Hai toán tử đầu không bao gồm trường hợp bằng nhau; hai toán tử sau bao gồm giá trị biên. Có thể dùng ký hiệu hoặc các từ khóa **gt**, **lt**, **ge**, **le** khi cú pháp nơi nhúng biểu thức cần dạng chữ.

Để kết quả dễ dự đoán, hãy chuẩn hóa kiểu dữ liệu trước khi so sánh, xử lý null theo chính sách nghiệp vụ và chú ý độ chính xác của số thực. Root object và biến trong EvaluationContext giúp thay đổi dữ liệu so sánh mà không phải thay chuỗi biểu thức. Khi điều kiện trở nên phức tạp, đưa logic vào Java sẽ giúp kiểm thử và chẩn đoán dễ hơn.
