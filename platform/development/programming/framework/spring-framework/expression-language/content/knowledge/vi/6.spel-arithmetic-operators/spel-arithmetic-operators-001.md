# Phép cộng, trừ, nhân và chia trong SpEL

## 1. Tổng quan về toán tử số học

Spring Expression Language (SpEL) hỗ trợ các phép toán số học ngay trong biểu thức. Những toán tử cơ bản gồm:

| Toán tử | Tên | Ví dụ | Kết quả |
|---|---|---|---|
| `+` | Cộng | `12 + 8` | `20` |
| `-` | Trừ | `12 - 8` | `4` |
| `*` | Nhân | `12 * 8` | `96` |
| `/` | Chia | `12.0 / 8.0` | `1.5` |
| `%` | Chia lấy phần dư | `17 % 5` | `2` |
| `^` | Lũy thừa | `2 ^ 3` | `8` |

SpEL còn hỗ trợ dấu cộng và dấu trừ một ngôi để biểu diễn số dương hoặc âm, ví dụ `+5` và `-5`.

Có thể đánh giá biểu thức trực tiếp bằng parser:

~~~java
ExpressionParser parser = new SpelExpressionParser();

Integer sum = parser.parseExpression("12 + 8").getValue(Integer.class);
Integer difference = parser.parseExpression("12 - 8").getValue(Integer.class);
Integer product = parser.parseExpression("12 * 8").getValue(Integer.class);
Double quotient = parser.parseExpression("12.0 / 8.0").getValue(Double.class);

System.out.println(sum);        // 20
System.out.println(difference); // 4
System.out.println(product);    // 96
System.out.println(quotient);   // 1.5
~~~

Mỗi lần gọi `parseExpression`, parser tạo một `Expression`; `getValue` mới thực hiện phép tính và trả về kết quả.

## 2. Phép cộng (+)

Toán tử `+` cộng hai giá trị số:

~~~java
Expression expression = parser.parseExpression("10 + 25");
Integer result = expression.getValue(Integer.class);

System.out.println(result); // 35
~~~

Có thể cộng các literal thập phân:

~~~java
Double result = parser.parseExpression("10.5 + 2.25")
        .getValue(Double.class);

System.out.println(result); // 12.75
~~~

Trong SpEL, `+` cũng có thể nối chuỗi. Nếu một toán hạng là chuỗi, toán tử có thể tạo kết quả dạng chuỗi:

~~~java
Expression expression = parser.parseExpression("'Order-' + 42");
String orderLabel = expression.getValue(String.class);

System.out.println(orderLabel); // Order-42
~~~

Vì vậy, hãy xem kiểu dữ liệu của các toán hạng trước khi dùng `+`: trong một biểu thức nó có thể mang nghĩa cộng số học, trong biểu thức khác nó có thể mang nghĩa nối chuỗi.

## 3. Phép trừ (-)

Toán tử `-` lấy toán hạng bên phải trừ khỏi toán hạng bên trái:

~~~java
Integer remaining = parser.parseExpression("100 - 35")
        .getValue(Integer.class);

System.out.println(remaining); // 65
~~~

Dấu trừ một ngôi đổi dấu của một giá trị:

~~~java
Integer negative = parser.parseExpression("-15")
        .getValue(Integer.class);

Integer positive = parser.parseExpression("-(-15)")
        .getValue(Integer.class);

System.out.println(negative); // -15
System.out.println(positive); // 15
~~~

Có thể dùng phép trừ để tính chênh lệch giữa các giá trị lấy từ root object hoặc variables trong evaluation context:

~~~java
StandardEvaluationContext context = new StandardEvaluationContext();
context.setVariable("total", 500);
context.setVariable("discount", 75);

Expression expression = parser.parseExpression("#total - #discount");
Integer payable = expression.getValue(context, Integer.class);

System.out.println(payable); // 425
~~~

Cách truyền dữ liệu qua variables giúp tái sử dụng cùng biểu thức với nhiều bộ giá trị mà không phải tạo lại chuỗi expression source.

## 4. Phép nhân (*)

Toán tử `*` nhân hai toán hạng:

~~~java
Integer area = parser.parseExpression("12 * 8")
        .getValue(Integer.class);

System.out.println(area); // 96
~~~

Ví dụ tính tổng tiền từ số lượng và đơn giá:

~~~java
StandardEvaluationContext context = new StandardEvaluationContext();
context.setVariable("quantity", 4);
context.setVariable("unitPrice", 25);

Expression expression =
        parser.parseExpression("#quantity * #unitPrice");

Integer total = expression.getValue(context, Integer.class);
System.out.println(total); // 100
~~~

Có thể nhân số nguyên với số thập phân:

~~~java
Double extendedPrice = parser.parseExpression("3 * 19.95")
        .getValue(Double.class);

System.out.println(extendedPrice); // 59.849999999999994 (có thể có sai số nhị phân)
~~~

Với dữ liệu tiền tệ hoặc phép tính cần độ chính xác thập phân, nên chọn kiểu số phù hợp như `BigDecimal` thay vì dựa vào `double` cho kết quả chính xác tuyệt đối.

## 5. Phép chia (/)

Toán tử `/` chia toán hạng bên trái cho toán hạng bên phải:

~~~java
Double result = parser.parseExpression("15.0 / 4.0")
        .getValue(Double.class);

System.out.println(result); // 3.75
~~~

Khi cần phần thập phân, hãy dùng toán hạng có kiểu thập phân phù hợp. Kiểu literal và kiểu của dữ liệu đầu vào ảnh hưởng đến kiểu kết quả cũng như độ chính xác của phép tính.

SpEL hỗ trợ literal kiểu `BigDecimal` với hậu tố `M`. Có thể dùng chúng trong phép chia hoặc các phép tính tiền tệ:

~~~java
BigDecimal amount = parser.parseExpression("15.00M / 4.00M")
        .getValue(BigDecimal.class);
~~~

Phép chia cho 0 không có kết quả hợp lệ và sẽ phát sinh lỗi khi đánh giá. Nếu mẫu số đến từ dữ liệu động, hãy kiểm tra giá trị đó trước hoặc xử lý exception ở ranh giới phù hợp.

## 6. Phép chia lấy phần dư (%)

Toán tử `%` trả về phần dư của phép chia:

~~~java
Integer remainder = parser.parseExpression("17 % 5")
        .getValue(Integer.class);

System.out.println(remainder); // 2
~~~

Ví dụ kiểm tra một số có chia hết cho 2 hay không:

~~~java
StandardEvaluationContext context = new StandardEvaluationContext();
context.setVariable("number", 24);

Expression expression = parser.parseExpression("#number % 2 == 0");
Boolean isEven = expression.getValue(context, Boolean.class);

System.out.println(isEven); // true
~~~

Phép modulo thường hữu ích khi chia nhóm, xác định vị trí vòng lặp, kiểm tra tính chẵn lẻ hoặc tính chu kỳ. Mẫu số phải khác 0.

## 7. Phép lũy thừa (^)

SpEL dùng toán tử `^` để tính lũy thừa:

~~~java
Integer result = parser.parseExpression("2 ^ 3")
        .getValue(Integer.class);

System.out.println(result); // 8
~~~

Ví dụ tính bình phương hoặc lập phương:

~~~java
Double square = parser.parseExpression("5.0 ^ 2")
        .getValue(Double.class);

Double cube = parser.parseExpression("2.0 ^ 3")
        .getValue(Double.class);

System.out.println(square); // 25.0
System.out.println(cube);   // 8.0
~~~

Lưu ý: `^` trong SpEL là toán tử lũy thừa. Nó không mang nghĩa XOR theo cách dùng toán tử `^` trong Java. Khi chuyển một biểu thức từ Java sang SpEL, cần chú ý khác biệt này.

## 8. Thứ tự thực hiện và dấu ngoặc

SpEL tuân theo thứ tự ưu tiên của toán tử số học: phép lũy thừa được xử lý trước phép nhân/chia/modulo; phép nhân, chia và modulo được xử lý trước phép cộng/trừ. Các phép cùng mức ưu tiên được xử lý theo thứ tự của biểu thức. Dùng dấu ngoặc để làm rõ ý định và thay đổi thứ tự khi cần.

~~~java
Integer first = parser.parseExpression("2 + 3 * 4")
        .getValue(Integer.class);

Integer second = parser.parseExpression("(2 + 3) * 4")
        .getValue(Integer.class);

System.out.println(first);  // 14
System.out.println(second); // 20
~~~

Ví dụ với nhiều phép tính:

~~~java
Double total = parser.parseExpression("(100.0 - 10.0) / 3.0 + 2.0")
        .getValue(Double.class);
~~~

Ngay cả khi đã biết thứ tự ưu tiên, dấu ngoặc vẫn giúp biểu thức dễ đọc và hạn chế hiểu nhầm khi công thức được bảo trì.

## 9. Kiểu số và literal số

SpEL hỗ trợ nhiều kiểu literal số. Một số hậu tố thường gặp:

| Hậu tố | Kiểu literal | Ví dụ |
|---|---|---|
| Không có hậu tố với số nguyên | Integer hoặc kiểu số nguyên phù hợp | `42` |
| `L` | Long | `42L` |
| `F` | Float | `3.14F` |
| `D` | Double | `3.14D` |
| `M` | BigDecimal | `3.14M` |

Ví dụ dùng BigDecimal literal:

~~~java
BigDecimal total = parser.parseExpression("10.50M + 2.25M")
        .getValue(BigDecimal.class);

System.out.println(total); // 12.75
~~~

Khi dùng `BigDecimal`, cả literal lẫn kiểu nhận kết quả nên được thể hiện rõ. Với phép tính tiền tệ, hãy chọn quy tắc scale và rounding phù hợp với nghiệp vụ; không nên giả định mọi phép chia đều tự động tạo ra số chữ số thập phân theo mong muốn của ứng dụng.

Với `float` và `double`, một số giá trị thập phân không thể biểu diễn chính xác trong hệ nhị phân. Vì vậy, kết quả có thể xuất hiện sai số làm tròn nhỏ. Dùng `BigDecimal` nếu yêu cầu nghiệp vụ cần biểu diễn thập phân chính xác.

## 10. Kết hợp phép toán với root object và variables

Biểu thức số học không cần nhúng các con số cố định. Có thể đọc property từ root object hoặc variables trong `EvaluationContext`.

Ví dụ dùng variables:

~~~java
StandardEvaluationContext context = new StandardEvaluationContext();
context.setVariable("price", 120.0);
context.setVariable("taxRate", 0.1);
context.setVariable("quantity", 2);

Expression expression =
        parser.parseExpression("#price * #quantity * (1 + #taxRate)");

Double total = expression.getValue(context, Double.class);
System.out.println(total); // 264.0
~~~

Ví dụ dùng root object:

~~~java
public class Product {
    private double price;
    private int quantity;

    public Product(double price, int quantity) {
        this.price = price;
        this.quantity = quantity;
    }

    public double getPrice() {
        return price;
    }

    public int getQuantity() {
        return quantity;
    }
}

Product product = new Product(25.0, 4);

Expression expression =
        parser.parseExpression("price * quantity");

Double total = expression.getValue(product, Double.class);
System.out.println(total); // 100.0
~~~

Trong ví dụ root object, `price` và `quantity` được phân giải thành property của object `product`. Với variables, tiền tố `#` cho biết SpEL cần lấy giá trị từ evaluation context.

## 11. Kết hợp nhiều toán tử trong công thức

Một biểu thức có thể kết hợp nhiều phép toán để diễn tả công thức ngắn gọn:

~~~java
StandardEvaluationContext context = new StandardEvaluationContext();
context.setVariable("subtotal", 1000.0);
context.setVariable("discountRate", 0.15);
context.setVariable("shippingFee", 25.0);

Expression expression = parser.parseExpression(
        "#subtotal * (1 - #discountRate) + #shippingFee");

Double payable = expression.getValue(context, Double.class);
System.out.println(payable); // 875.0
~~~

Công thức gồm ba phần: nhân subtotal với tỷ lệ còn lại sau giảm giá, sau đó cộng phí vận chuyển. Dấu ngoặc làm rõ phần tỷ lệ được tính trước.

Một ví dụ khác kết hợp modulo và cộng:

~~~java
Expression expression = parser.parseExpression("(#number % 10) + 1");
~~~

Biểu thức trên lấy chữ số hàng đơn vị của `#number`, rồi cộng 1. Khi dùng biểu thức dài, hãy đặt tên biến có ý nghĩa và chia nhỏ logic phức tạp sang method Java nếu điều đó giúp dễ hiểu hơn.

## 12. Lỗi thường gặp và cách xử lý

**Chia cho 0**

Mẫu số bằng 0 làm phép chia không thể đánh giá. Kiểm tra dữ liệu trước khi gọi `getValue`, hoặc bắt lỗi evaluation ở tầng phù hợp.

**Nhầm phép lũy thừa với XOR**

Trong Java, `^` là XOR bitwise; trong SpEL, `^` là lũy thừa. Khi chuyển công thức giữa hai ngôn ngữ, phải chuyển đổi đúng ý nghĩa toán học.

**Dùng sai kiểu kết quả**

Một biểu thức có thể trả về kiểu số khác với kiểu mà code mong đợi. Dùng overload `getValue(..., TargetType.class)` khi biết kiểu đầu ra và chọn kiểu literal rõ ràng.

**Sai số với số thực**

`float` và `double` có thể có sai số biểu diễn. Với tiền tệ hoặc quy tắc làm tròn nghiêm ngặt, cân nhắc `BigDecimal` và định nghĩa rõ scale/rounding.

**Thiếu dấu ngoặc**

Một biểu thức có nhiều phép toán có thể cho kết quả khác với cách người đọc suy đoán. Thêm dấu ngoặc ở những chỗ thể hiện nhóm tính toán của nghiệp vụ.

**Dữ liệu động không hợp lệ**

Nếu giá trị đầu vào là null hoặc không thể chuyển đổi sang kiểu số cần thiết, expression có thể phát sinh lỗi evaluation. Kiểm tra và chuẩn hóa dữ liệu ở biên ứng dụng thay vì dựa vào expression để che giấu dữ liệu sai.

## 13. Khi nào nên dùng SpEL và khi nào nên viết Java?

SpEL phù hợp cho các công thức ngắn được dùng tại nơi Spring cần đánh giá expression, ví dụ trong cấu hình, rule đơn giản hoặc điều kiện dựa trên object. Nó giúp mô tả một phép tính trực tiếp mà không cần tạo method riêng cho mọi biểu thức nhỏ.

Java thường phù hợp hơn khi công thức có nhiều bước, có nhiều nhánh, cần kiểm soát scale/rounding, cần logging chi tiết hoặc là một phần quan trọng của nghiệp vụ. Khi đó, viết method Java có tên rõ ràng giúp compiler và IDE hỗ trợ tốt hơn, đồng thời dễ kiểm thử hơn.

Không nên chuyển toàn bộ phép tính nghiệp vụ sang một chuỗi SpEL dài chỉ để làm annotation ngắn hơn. Hãy giữ expression ngắn, có đầu vào rõ ràng và dễ kiểm tra.

## 14. Ghi nhớ

- `+`, `-`, `*`, `/`, `%`, `^` lần lượt hỗ trợ cộng, trừ, nhân, chia, chia lấy phần dư và lũy thừa.
- `+` còn có thể nối chuỗi; hãy chú ý kiểu dữ liệu của hai toán hạng.
- `^` trong SpEL là lũy thừa, khác với XOR của Java.
- Dùng dấu ngoặc để thể hiện rõ thứ tự tính toán.
- Chọn kiểu số phù hợp; dùng `BigDecimal` cho phép tính cần độ chính xác thập phân.
- Đưa dữ liệu động vào `EvaluationContext` hoặc root object thay vì nối dữ liệu vào chuỗi expression source.
- Xử lý mẫu số bằng 0, dữ liệu null và lỗi chuyển đổi ở tầng phù hợp.
- Giữ SpEL cho biểu thức ngắn; chuyển logic nhiều bước sang Java.
