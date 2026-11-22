# Toán tử ba ngôi và nhánh đúng hoặc sai trong SpEL

## 1. Cú pháp của toán tử điều kiện

Spring Expression Language (SpEL) hỗ trợ toán tử điều kiện ba ngôi (ternary conditional operator), có dạng:

~~~text
condition ? expressionIfTrue : expressionIfFalse
~~~

Biểu thức điều kiện được đánh giá trước. Nếu điều kiện là `true`, SpEL đánh giá và trả về biểu thức ở nhánh bên trái dấu hai chấm. Nếu điều kiện là `false`, SpEL đánh giá và trả về biểu thức ở nhánh bên phải dấu hai chấm.

Ví dụ:

~~~java
ExpressionParser parser = new SpelExpressionParser();

Expression expression =
        parser.parseExpression("10 > 5 ? 'Greater' : 'Not greater'");

String result = expression.getValue(String.class);
System.out.println(result); // Greater
~~~

Trong ví dụ này:

- `10 > 5` là điều kiện Boolean.
- `'Greater'` là nhánh được chọn khi điều kiện đúng.
- `'Not greater'` là nhánh được chọn khi điều kiện sai.
- Dấu `?` bắt đầu phần lựa chọn; dấu `:` phân tách hai nhánh.

Toán tử ba ngôi tạo ra một giá trị. Vì vậy, nó có thể được dùng ở nơi một biểu thức SpEL khác được chấp nhận, chẳng hạn trong một phép nối chuỗi, một biểu thức cấu hình hoặc một lời gọi `getValue`.

## 2. Điều kiện phải cho kết quả Boolean

Phần trước dấu `?` cần đánh giá thành giá trị Boolean. Điều kiện thường là phép so sánh:

~~~java
Expression expression =
        parser.parseExpression("#age >= 18 ? 'Adult' : 'Minor'");

StandardEvaluationContext context = new StandardEvaluationContext();
context.setVariable("age", 20);

String category = expression.getValue(context, String.class);
System.out.println(category); // Adult
~~~

Các biểu thức so sánh như `>`, `>=`, `<`, `<=`, `==` và `!=` thường được dùng để tạo điều kiện. Có thể kết hợp chúng với toán tử logic:

~~~java
Expression expression = parser.parseExpression(
        "(#age >= 18 and #verified) ? 'Approved' : 'Review'");

StandardEvaluationContext context = new StandardEvaluationContext();
context.setVariable("age", 21);
context.setVariable("verified", true);

String result = expression.getValue(context, String.class);
System.out.println(result); // Approved
~~~

Dấu ngoặc quanh điều kiện giúp người đọc nhận ra rõ phần nào được đánh giá trước khi chọn nhánh. Nếu một giá trị không phải Boolean được đặt trực tiếp ở vị trí điều kiện, biểu thức có thể phát sinh lỗi khi đánh giá; không nên giả định SpEL tự xem số khác 0 hoặc chuỗi không rỗng là `true`.

## 3. Nhánh đúng và nhánh sai

Nhánh đúng là biểu thức nằm giữa `?` và `:`. Nhánh sai là biểu thức nằm sau `:`. Mỗi nhánh có thể là literal, variable, property access, lời gọi method hoặc một biểu thức SpEL khác.

~~~java
StandardEvaluationContext context = new StandardEvaluationContext();
context.setVariable("available", true);

Expression expression =
        parser.parseExpression("#available ? 'In stock' : 'Out of stock'");

String message = expression.getValue(context, String.class);
System.out.println(message); // In stock
~~~

Khi thay đổi biến:

~~~java
context.setVariable("available", false);

String message = expression.getValue(context, String.class);
System.out.println(message); // Out of stock
~~~

Cùng một `Expression` có thể được đánh giá lại với context đã cập nhật. Kết quả phụ thuộc vào giá trị điều kiện tại thời điểm gọi `getValue`.

Chỉ nhánh được chọn mới cần được đánh giá để tạo kết quả. Điều này cho phép đặt các phép tính hoặc truy cập dữ liệu riêng trong từng nhánh, miễn là nhánh được chọn có thể đánh giá hợp lệ với context hiện tại.

## 4. Dùng Boolean literal true và false

SpEL có Boolean literal `true` và `false`. Có thể dùng chúng làm nhánh kết quả:

~~~java
Expression expression =
        parser.parseExpression("#score >= 50 ? true : false");

StandardEvaluationContext context = new StandardEvaluationContext();
context.setVariable("score", 75);

Boolean passed = expression.getValue(context, Boolean.class);
System.out.println(passed); // true
~~~

Trong trường hợp chỉ trả về chính điều kiện hoặc phủ định của điều kiện, không cần dùng toán tử ba ngôi:

~~~java
Expression expression = parser.parseExpression("#score >= 50");
Boolean passed = expression.getValue(context, Boolean.class);
~~~

Biểu thức `#score >= 50 ? true : false` tương đương với `#score >= 50`. Hãy dùng ternary khi hai nhánh cần tạo ra hai kết quả khác nhau, ví dụ trạng thái, nhãn, mức phí hoặc giá trị thay thế.

## 5. Hai nhánh có thể trả về chuỗi, số hoặc giá trị khác

Toán tử ba ngôi không giới hạn kết quả ở Boolean. Hai nhánh có thể trả về các kiểu dữ liệu mà ứng dụng cần:

~~~java
Expression labelExpression =
        parser.parseExpression("#total >= 1000 ? 'VIP' : 'STANDARD'");

Expression feeExpression =
        parser.parseExpression("#express ? 0 : 25000");

StandardEvaluationContext context = new StandardEvaluationContext();
context.setVariable("total", 1500);
context.setVariable("express", false);

String label = labelExpression.getValue(context, String.class);
Integer fee = feeExpression.getValue(context, Integer.class);

System.out.println(label); // VIP
System.out.println(fee);   // 25000
~~~

Kiểu kết quả phụ thuộc vào nhánh được chọn và kiểu giá trị của biểu thức đó. Khi ứng dụng cần một kiểu kết quả cụ thể, hãy dùng overload `getValue(..., TargetType.class)` và bảo đảm giá trị được chọn có thể chuyển đổi sang kiểu đích. Để biểu thức dễ hiểu, hai nhánh thường nên trả về các giá trị có kiểu tương thích.

Ví dụ trả về một giá trị mặc định khi dữ liệu không đáp ứng điều kiện:

~~~java
Expression expression =
        parser.parseExpression("#nickname != null ? #nickname : 'Guest'");

StandardEvaluationContext context = new StandardEvaluationContext();
context.setVariable("nickname", null);

String displayName = expression.getValue(context, String.class);
System.out.println(displayName); // Guest
~~~

Cách viết này giúp tránh trả về null trong trường hợp ứng dụng cần một nhãn thay thế. Tuy nhiên, nếu nhánh được chọn có thể truy cập property qua một object null, hãy kiểm tra điều kiện trước khi truy cập property đó.

## 6. Truy cập property trong hai nhánh

Mỗi nhánh có thể tham chiếu property của root object hoặc biến trong evaluation context. Ví dụ, một đơn hàng có thể dùng nhãn khác nhau tùy trạng thái thanh toán:

~~~java
public class Order {
    private String code;
    private boolean paid;

    public Order(String code, boolean paid) {
        this.code = code;
        this.paid = paid;
    }

    public String getCode() {
        return code;
    }

    public boolean isPaid() {
        return paid;
    }
}

Order order = new Order("ORD-1001", true);

Expression expression = parser.parseExpression(
        "paid ? 'Order ' + code + ' is paid' : 'Order ' + code + ' is pending'");

String status = expression.getValue(order, String.class);
System.out.println(status); // Order ORD-1001 is paid
~~~

Trong biểu thức này, `paid` và `code` được phân giải từ root object `order`. Nếu trạng thái thanh toán là false, SpEL chọn nhánh thứ hai và tạo thông báo đang chờ thanh toán.

Cũng có thể truy cập property lồng nhau trong nhánh:

~~~text
#customer != null ? #customer.name : 'Unknown customer'
~~~

Điều kiện kiểm tra biến `#customer` trước khi nhánh đúng truy cập `name`. Khi `#customer` là null, nhánh sai được chọn và không cần truy cập property `name`.

## 7. Dùng toán tử ba ngôi trong @Value

Trong các điểm tích hợp cấu hình của Spring, SpEL thường được đặt trong dấu `#{...}`. Có thể dùng toán tử ba ngôi để chọn giá trị được inject:

~~~java
@Component
public class RetryConfiguration {
    @Value("#{T(java.lang.Math).max(3, 5) > 3 ? 'HIGH' : 'LOW'}")
    private String retryLevel;

    public String getRetryLevel() {
        return retryLevel;
    }
}
~~~

Spring đánh giá biểu thức SpEL khi xử lý cấu hình bean. Nếu điều kiện đúng, field nhận giá trị của nhánh đúng; nếu sai, field nhận giá trị của nhánh sai.

Một ví dụ khác chọn timeout theo profile hoặc một giá trị cấu hình có sẵn trong context của ứng dụng có thể được viết bằng cùng cấu trúc. Hãy giữ mỗi nhánh ngắn và dễ đọc. Nếu quy tắc chọn giá trị có nhiều bước, nên chuyển logic sang method Java hoặc một bean chuyên trách.

## 8. Kết hợp toán tử ba ngôi với phép toán

Nhánh đúng và nhánh sai có thể chứa phép tính số học:

~~~java
StandardEvaluationContext context = new StandardEvaluationContext();
context.setVariable("quantity", 12);
context.setVariable("unitPrice", 50);
context.setVariable("discountEligible", true);

Expression expression = parser.parseExpression(
        "#discountEligible ? #quantity * #unitPrice * 0.9 : #quantity * #unitPrice");

Double payable = expression.getValue(context, Double.class);
System.out.println(payable); // 540.0
~~~

Nếu khách hàng đủ điều kiện, nhánh đúng áp dụng mức giảm 10%; nếu không, nhánh sai tính tổng theo giá gốc. Điều kiện và hai công thức đều nằm trong một expression, còn dữ liệu được truyền qua variables.

Có thể kết hợp với các phép so sánh khác:

~~~java
Expression expression = parser.parseExpression(
        "#quantity >= 10 ? #unitPrice * 0.95 : #unitPrice");
~~~

Biểu thức chọn giá đơn vị giảm 5% khi số lượng đạt ít nhất 10. Với công thức tiền tệ thực tế, nên dùng kiểu số và quy tắc rounding phù hợp, ví dụ `BigDecimal`, thay vì dựa vào `double` nếu cần độ chính xác thập phân.

## 9. Toán tử ba ngôi lồng nhau

Một nhánh có thể chứa một toán tử ba ngôi khác. Cách này cho phép chọn giữa nhiều trường hợp:

~~~java
Expression expression = parser.parseExpression(
        "#score >= 85 ? 'Excellent' : (#score >= 50 ? 'Pass' : 'Fail')");

StandardEvaluationContext context = new StandardEvaluationContext();
context.setVariable("score", 72);

String grade = expression.getValue(context, String.class);
System.out.println(grade); // Pass
~~~

Cách đọc biểu thức:

1. Nếu `#score >= 85`, trả về `Excellent`.
2. Nếu điều kiện đầu sai, đánh giá toán tử ba ngôi bên trong dấu ngoặc.
3. Nếu `#score >= 50`, trả về `Pass`; nếu không, trả về `Fail`.

Khi có nhiều hơn hai hoặc ba mức lựa chọn, chuỗi ternary lồng nhau nhanh chóng khó đọc. Có thể tách biểu thức, dùng method Java có tên rõ ràng hoặc một cấu trúc rule phù hợp với ứng dụng.

## 10. Kết hợp với toán tử logic

Điều kiện có thể kết hợp `and`, `or` và `not` trước khi chọn nhánh:

~~~java
StandardEvaluationContext context = new StandardEvaluationContext();
context.setVariable("active", true);
context.setVariable("verified", false);
context.setVariable("balance", 100);

Expression expression = parser.parseExpression(
        "(#active and #verified and #balance > 0) ? 'Can proceed' : 'Blocked'");

String result = expression.getValue(context, String.class);
System.out.println(result); // Blocked
~~~

Dù `active` là true và balance lớn hơn 0, `verified` là false nên toàn bộ điều kiện `and` sai. SpEL chọn nhánh sai.

Có thể dùng `or` để cho phép nhiều điều kiện khác nhau dẫn đến cùng một nhánh:

~~~java
Expression expression = parser.parseExpression(
        "(#isAdmin or #isOwner) ? 'Allowed' : 'Denied'");
~~~

Hãy dùng dấu ngoặc để thể hiện nhóm điều kiện. Điều này giúp tránh nhầm lẫn khi kết hợp nhiều toán tử logic với toán tử ba ngôi.

## 11. Phân biệt ternary với Elvis và toán tử logic

Toán tử ba ngôi luôn có ba phần: điều kiện, nhánh đúng và nhánh sai:

~~~text
condition ? valueWhenTrue : valueWhenFalse
~~~

Elvis operator của SpEL có cú pháp `?:` và thường dùng để chọn giá trị thay thế khi biểu thức bên trái là null hoặc rỗng theo quy tắc của SpEL:

~~~java
Expression expression = parser.parseExpression("#nickname ?: 'Guest'");
~~~

Hai cú pháp giải quyết mục đích khác nhau:

- Ternary: chọn nhánh dựa trên một điều kiện Boolean rõ ràng.
- Elvis: cung cấp giá trị thay thế khi giá trị bên trái không có giá trị phù hợp theo ngữ nghĩa Elvis.
- `and`, `or`, `not`: kết hợp hoặc phủ định các điều kiện Boolean; chúng không trực tiếp chọn một giá trị kết quả theo hai nhánh.

Nếu cần kiểm tra nhiều điều kiện hoặc cần một quy tắc nghiệp vụ rõ ràng, ternary giúp thể hiện điều kiện và hai kết quả trực tiếp.

## 12. Lỗi thường gặp

**Thiếu một nhánh**

Biểu thức phải có đủ dấu `?`, nhánh đúng, dấu `:` và nhánh sai. Thiếu một phần sẽ khiến parser báo lỗi cú pháp.

**Điều kiện không phải Boolean**

Phần điều kiện cần trả về Boolean. Hãy dùng phép so sánh hoặc biểu thức logic thay vì đặt một chuỗi hay số vào vị trí điều kiện.

**Nhầm thứ tự hai nhánh**

Giá trị trước dấu `:` là kết quả khi điều kiện đúng; giá trị sau dấu `:` là kết quả khi điều kiện sai. Đọc biểu thức theo cấu trúc này để tránh đảo kết quả.

**Truy cập dữ liệu null trong nhánh được chọn**

Nếu một nhánh truy cập property của object null, việc đánh giá có thể thất bại. Kiểm tra object trong điều kiện hoặc dùng cách truy cập null-safe phù hợp.

**Hai nhánh không tương thích kiểu**

Nếu code yêu cầu kiểu kết quả cụ thể, hãy bảo đảm giá trị của nhánh được chọn có thể chuyển đổi sang kiểu đó. Tránh để một nhánh trả về số còn nhánh kia trả về một object không liên quan nếu ứng dụng mong đợi một kiểu thống nhất.

**Lồng quá nhiều điều kiện**

Một chuỗi ternary dài rất khó đọc và sửa đổi. Chuyển các quy tắc phức tạp sang method Java hoặc tách thành các biểu thức nhỏ có tên rõ ràng.

## 13. Ví dụ tổng hợp

Ví dụ sau chọn thông báo và phí vận chuyển theo trạng thái đơn hàng:

~~~java
StandardEvaluationContext context = new StandardEvaluationContext();
context.setVariable("paid", true);
context.setVariable("total", 1200.0);
context.setVariable("express", false);

Expression messageExpression = parser.parseExpression(
        "#paid ? 'Payment received' : 'Awaiting payment'");

Expression shippingExpression = parser.parseExpression(
        "#total >= 1000 ? (#express ? 0 : 15000) : 25000");

String message = messageExpression.getValue(context, String.class);
Double shippingFee = shippingExpression.getValue(context, Double.class);

System.out.println(message);     // Payment received
System.out.println(shippingFee); // 15000.0
~~~

Biểu thức đầu chọn thông báo dựa trên trạng thái thanh toán. Biểu thức thứ hai chọn phí vận chuyển theo tổng đơn hàng; nếu đạt ngưỡng, một ternary lồng nhau tiếp tục chọn phí theo dịch vụ giao nhanh.

## 14. Ghi nhớ

- Cú pháp ternary trong SpEL là `condition ? expressionIfTrue : expressionIfFalse`.
- Điều kiện phải đánh giá thành Boolean.
- Nhánh đúng nằm giữa `?` và `:`; nhánh sai nằm sau `:`.
- Mỗi nhánh có thể trả về literal, variable, property, method call hoặc biểu thức khác.
- Có thể dùng ternary với root object, variables, `@Value`, phép toán và template expression.
- Dùng dấu ngoặc khi kết hợp điều kiện logic hoặc lồng ternary.
- Phân biệt ternary với Elvis operator và các toán tử logic.
- Giữ hai nhánh tương thích với kiểu kết quả mà ứng dụng mong đợi; chuyển logic nhiều tầng sang Java khi cần.
