# Số nguyên, số thực và kết quả phép tính

Trong Spring Expression Language (SpEL), các phép toán số học được thực hiện trên những giá trị số mà biểu thức nhận được từ literal, root object hoặc biến trong EvaluationContext. Kết quả phụ thuộc vào kiểu của toán hạng và phép toán đang dùng. Vì vậy, cùng một công thức nhìn giống nhau có thể cho kết quả khác nhau nếu một biểu thức sử dụng số nguyên, biểu thức khác sử dụng số thực hoặc BigDecimal.

Khi viết biểu thức số học, cần xác định rõ kiểu dữ liệu đầu vào, kiểu kết quả mong muốn và cách xử lý độ chính xác. Điều này đặc biệt quan trọng với phép chia, các phép tính tiền tệ và những giá trị có thể vượt giới hạn của kiểu số nguyên thông thường.

## Các loại giá trị số trong SpEL

SpEL hỗ trợ literal số nguyên và số thực. Một số dạng thường gặp:

| Literal | Ý nghĩa |
|---|---|
| **25** | Số nguyên |
| **25L** | Số nguyên kiểu Long |
| **3.5** | Số thực, thường được suy luận thành Double |
| **3.5F** | Số thực kiểu Float |
| **3.5D** | Số thực kiểu Double |

Ví dụ parse trực tiếp các literal:

~~~java
ExpressionParser parser = new SpelExpressionParser();

Integer count = parser.parseExpression("25")
        .getValue(Integer.class);

Long largeCount = parser.parseExpression("25L")
        .getValue(Long.class);

Double rate = parser.parseExpression("3.5")
        .getValue(Double.class);

Float factor = parser.parseExpression("3.5F")
        .getValue(Float.class);
~~~

Literal là giá trị được ghi trực tiếp trong chuỗi biểu thức. Kiểu của literal tham gia vào phép toán và có thể ảnh hưởng đến kiểu kết quả. Không nên chỉ nhìn kiểu đích trong **getValue(Integer.class)** hoặc **getValue(Double.class)** rồi cho rằng đó là kiểu mà phép tính đã sử dụng từ đầu.

## Các toán tử số học

SpEL cung cấp những toán tử số học phổ biến:

| Toán tử | Ý nghĩa | Ví dụ |
|---|---|---|
| **+** | Cộng | **10 + 5** |
| **-** | Trừ | **10 - 5** |
| ***** | Nhân | **10 * 5** |
| **/** | Chia | **10 / 5** |
| **%** | Chia lấy phần dư | **10 % 3** |
| **^** | Lũy thừa | **2 ^ 3** |

Toán tử **+** cũng có thể được dùng để nối chuỗi khi toán hạng là chuỗi. Vì vậy, cần chú ý kiểu dữ liệu thực tế của hai vế trước khi hiểu một biểu thức là phép cộng số học.

~~~java
ExpressionParser parser = new SpelExpressionParser();

Integer sum = parser.parseExpression("10 + 5")
        .getValue(Integer.class);

Integer difference = parser.parseExpression("10 - 5")
        .getValue(Integer.class);

Integer product = parser.parseExpression("10 * 5")
        .getValue(Integer.class);

Integer quotient = parser.parseExpression("10 / 5")
        .getValue(Integer.class);

Integer remainder = parser.parseExpression("10 % 3")
        .getValue(Integer.class);

Integer power = parser.parseExpression("2 ^ 3")
        .getValue(Integer.class);
~~~

Các kết quả lần lượt là 15, 5, 50, 2, 1 và 8. Trong SpEL, **^** là toán tử lũy thừa. Không nên nhầm nó với toán tử XOR trong một số ngôn ngữ lập trình khác.

## Thứ tự thực hiện phép tính

Biểu thức số học có thể chứa nhiều toán tử. SpEL áp dụng thứ tự ưu tiên toán tử; phép nhân, chia và chia lấy dư được thực hiện trước phép cộng và trừ. Có thể dùng dấu ngoặc để thể hiện rõ nhóm phép tính cần thực hiện trước.

~~~java
Integer first = parser.parseExpression("10 + 5 * 2")
        .getValue(Integer.class);

Integer second = parser.parseExpression("(10 + 5) * 2")
        .getValue(Integer.class);
~~~

Kết quả đầu tiên là 20 vì phép nhân được thực hiện trước. Kết quả thứ hai là 30 vì dấu ngoặc yêu cầu cộng trước rồi mới nhân.

Trong biểu thức nghiệp vụ, nên dùng dấu ngoặc khi công thức có nhiều bước hoặc khi thứ tự phép tính có thể gây hiểu nhầm. Điều này giúp người đọc nhận ra ý định mà không phải tự ghi nhớ toàn bộ quy tắc ưu tiên.

## Số nguyên và phép chia có phần thập phân

Một điểm cần chú ý là kiểu toán hạng ảnh hưởng đến phép chia. Khi hai toán hạng là số nguyên, phép chia số nguyên cho kết quả nguyên và phần thập phân bị loại bỏ:

~~~java
Integer integerResult =
        parser.parseExpression("7 / 2")
                .getValue(Integer.class);
~~~

Kết quả là 3. Nếu cần phần thập phân, ít nhất một toán hạng phải là số thực hoặc kiểu số thập phân phù hợp:

~~~java
Double decimalResult =
        parser.parseExpression("7.0 / 2")
                .getValue(Double.class);
~~~

Kết quả là 3.5.

Việc yêu cầu **getValue(Double.class)** chỉ định kiểu mà ứng dụng muốn nhận. Nó không thay đổi phép chia số nguyên đã xảy ra trước đó. Nếu đánh giá **7 / 2** như phép chia nguyên rồi mới chuyển kết quả sang Double, kết quả vẫn là 3.0 chứ không phải 3.5.

Vì vậy, hãy chọn kiểu toán hạng ngay từ biểu thức hoặc từ dữ liệu được đưa vào context. Đây là cách tránh lỗi thường gặp khi tính tỷ lệ, phần trăm, đơn giá hoặc trung bình.

## Kiểu kết quả và chuyển đổi kiểu

Kiểu kết quả của một phép toán phụ thuộc vào kiểu toán hạng và quy tắc số học mà SpEL áp dụng. Với những kiểu số thông dụng, có thể hiểu khái quát:

- Hai toán hạng nguyên thông thường tạo ra kết quả theo phép toán số nguyên.
- Khi có Long, phép toán số nguyên có thể được nâng lên kiểu Long.
- Khi có Float hoặc Double, phép toán sử dụng kiểu số thực tương ứng theo quy tắc của SpEL.
- Khi sử dụng BigInteger hoặc BigDecimal, SpEL có các nhánh xử lý dành cho những kiểu số này.

Đây là lý do nên giữ kiểu dữ liệu có chủ đích thay vì trộn nhiều kiểu số tùy tiện. Khi biểu thức kết hợp các kiểu khác nhau, hãy kiểm tra kiểu kết quả thực tế và quy tắc chuyển đổi trong phiên bản Spring đang sử dụng.

Có thể yêu cầu kiểu kết quả khi gọi Expression:

~~~java
Expression expression = parser.parseExpression("10 + 5");

Integer integerValue = expression.getValue(Integer.class);
Number numberValue = expression.getValue(Number.class);
Object objectValue = expression.getValue();
~~~

Các overload này giúp ứng dụng nhận kết quả dưới kiểu mong muốn. SpEL có thể dùng cơ chế chuyển đổi kiểu của evaluation context khi phù hợp. Tuy nhiên, chuyển đổi kiểu xảy ra khi lấy kết quả không đồng nghĩa với việc thay đổi kiểu toán hạng trước khi phép toán được thực hiện.

Nếu kiểu kết quả không tương thích và không có phép chuyển đổi phù hợp, quá trình đánh giá có thể phát sinh lỗi.

## Số nguyên lớn: Long và BigInteger

Kiểu Integer có giới hạn giá trị. Nếu phép tính có thể vượt giới hạn đó, cần chọn kiểu rộng hơn như Long hoặc dùng BigInteger khi cần độ lớn vượt xa các kiểu nguyên thủy.

Ví dụ với Long literal:

~~~java
Long result = parser.parseExpression("9000000000L + 100L")
        .getValue(Long.class);
~~~

Hậu tố **L** giúp biểu thức thể hiện rõ literal Long. Nếu dữ liệu được lấy từ object hoặc biến, hãy bảo đảm các giá trị đầu vào cũng có kiểu phù hợp.

Với **BigInteger**, có thể truyền một giá trị BigInteger qua root object hoặc biến trong evaluation context rồi thực hiện phép toán trên nó. Cách này phù hợp với số nguyên có độ lớn tùy ý, nhưng không có phần thập phân.

Không nên mặc định rằng mọi phép tính đều tự động trở thành BigInteger chỉ vì kết quả có thể lớn. Hãy chọn kiểu dữ liệu ngay từ đầu vào và kiểm tra kiểu trả về.

## Số thực và sai số biểu diễn

Float và Double biểu diễn số thực bằng dấu phẩy động nhị phân. Nhiều số thập phân không thể được biểu diễn chính xác dưới dạng nhị phân hữu hạn. Vì vậy, một phép tính tưởng như đơn giản có thể tạo ra kết quả gần đúng thay vì đúng tuyệt đối.

Ví dụ, phép cộng các giá trị 0.1 và 0.2 bằng Double có thể cho kết quả hiển thị gần 0.30000000000000004 thay vì chính xác 0.3:

~~~java
Double result =
        parser.parseExpression("0.1 + 0.2")
                .getValue(Double.class);
~~~

Đây là đặc điểm của biểu diễn dấu phẩy động, không phải lỗi riêng của SpEL. Với phép tính khoa học, đồ họa hoặc dữ liệu chấp nhận sai số nhỏ, Float/Double thường phù hợp. Với tiền tệ hoặc số thập phân cần kiểm soát chính xác, nên dùng **BigDecimal**.

## Dùng BigDecimal cho số thập phân cần độ chính xác

BigDecimal biểu diễn số thập phân với độ chính xác tùy theo giá trị và cách sử dụng. Có thể đưa các giá trị BigDecimal vào root object hoặc evaluation context rồi sử dụng toán tử SpEL.

Ví dụ, một đơn hàng có đơn giá BigDecimal:

~~~java
public class Order {
    private final BigDecimal unitPrice;
    private final BigDecimal quantity;

    public Order(BigDecimal unitPrice, BigDecimal quantity) {
        this.unitPrice = unitPrice;
        this.quantity = quantity;
    }

    public BigDecimal getUnitPrice() {
        return unitPrice;
    }

    public BigDecimal getQuantity() {
        return quantity;
    }
}
~~~

~~~java
Order order = new Order(
        new BigDecimal("19.90"),
        new BigDecimal("3"));

Expression expression =
        parser.parseExpression("unitPrice * quantity");

BigDecimal total =
        expression.getValue(order, BigDecimal.class);
~~~

Kết quả là BigDecimal tương ứng với 59.70. Việc tạo BigDecimal từ chuỗi như **new BigDecimal("19.90")** giúp tránh đưa sai số của Double vào ngay từ đầu.

Nếu cần chia BigDecimal, hãy xác định rõ quy tắc làm tròn phù hợp với nghiệp vụ. Một số phép chia tạo ra số thập phân vô hạn tuần hoàn; hệ thống cần quy định scale và rounding mode tại đúng nơi xử lý nghiệp vụ thay vì để cách làm tròn trở thành một giả định không được nêu rõ.

## Dùng biến BigDecimal trong phép tính

Có thể truyền một hệ số BigDecimal vào EvaluationContext để biểu thức dùng nó như một toán hạng:

~~~java
StandardEvaluationContext context =
        new StandardEvaluationContext(order);

context.setVariable(
        "taxRate",
        new BigDecimal("0.08"));

Expression expression =
        parser.parseExpression(
                "unitPrice * quantity * (1 + #taxRate)");

BigDecimal totalWithTax =
        expression.getValue(context, BigDecimal.class);
~~~

Ở đây, **#taxRate** là biến do ứng dụng cung cấp, còn số **1** là integer literal. Với biểu thức tài chính, nên thống nhất kiểu số giữa các toán hạng và kiểm tra kiểu kết quả trong phiên bản SpEL đang dùng. Nếu muốn kiểm soát đầy đủ scale và rounding mode, có thể thực hiện bước tính toán tương ứng trong Java bằng BigDecimal API.

## Phép chia, phần dư và chia cho 0

Toán tử **/** thực hiện phép chia; **%** lấy phần dư. Cả hai đều yêu cầu toán hạng phù hợp với phép toán. Khi mẫu số bằng 0, phép chia hoặc phép lấy phần dư có thể phát sinh lỗi evaluation.

~~~java
Integer quotient =
        parser.parseExpression("17 / 5")
                .getValue(Integer.class);

Integer remainder =
        parser.parseExpression("17 % 5")
                .getValue(Integer.class);
~~~

Với phép chia số nguyên, kết quả là 3 và phần dư là 2. Nếu cần tỷ lệ 3.4, hãy dùng toán hạng số thực hoặc kiểu thập phân phù hợp.

Dữ liệu đầu vào nên được kiểm tra trước nếu mẫu số có thể bằng 0. Không nên dựa vào việc bắt ngoại lệ ở mọi lần đánh giá để thay thế quy tắc xác thực dữ liệu nghiệp vụ.

## Khi biểu thức lấy số từ root object hoặc biến

Literal số chỉ là một nguồn toán hạng. Trong ứng dụng, các phép tính thường lấy số từ property của object hoặc biến:

~~~java
public class Cart {
    private final int quantity;
    private final BigDecimal unitPrice;

    public Cart(int quantity, BigDecimal unitPrice) {
        this.quantity = quantity;
        this.unitPrice = unitPrice;
    }

    public int getQuantity() {
        return quantity;
    }

    public BigDecimal getUnitPrice() {
        return unitPrice;
    }
}
~~~

~~~java
Cart cart = new Cart(4, new BigDecimal("12.50"));

Expression expression =
        parser.parseExpression("quantity * unitPrice");

BigDecimal amount =
        expression.getValue(cart, BigDecimal.class);
~~~

Biểu thức đọc hai property từ root object. Kiểu của property **quantity** là int và **unitPrice** là BigDecimal. SpEL thực hiện phép toán theo các kiểu toán hạng và cơ chế chuyển đổi có liên quan.

Nếu ứng dụng nhận dữ liệu từ JSON, database hoặc form, hãy xác định kiểu của field ngay tại lớp chuyển đổi dữ liệu. Một chuỗi số chưa được chuyển thành Number không nhất thiết tham gia phép tính như một số; tùy toán tử và kiểu, dấu cộng còn có thể được dùng để nối chuỗi.

## Phân biệt cộng số với nối chuỗi

Toán tử **+** có thể cộng hai giá trị số hoặc nối chuỗi. Ví dụ:

~~~java
String message =
        parser.parseExpression("'Order ' + 'A102'")
                .getValue(String.class);

Integer total =
        parser.parseExpression("10 + 20")
                .getValue(Integer.class);
~~~

Biểu thức đầu tiên tạo chuỗi **Order A102**; biểu thức thứ hai thực hiện phép cộng số học và trả về 30.

Khi một toán hạng là String, hãy xem xét cách SpEL xử lý phép nối chuỗi. Nếu mục tiêu là số học, cần bảo đảm cả hai toán hạng là kiểu số phù hợp. Điều này đặc biệt quan trọng khi dữ liệu được đọc từ nguồn có kiểu không đồng nhất.

## Kiểm tra kiểu và xử lý lỗi

Một biểu thức số học có thể parse thành công nhưng không đánh giá được trên dữ liệu thực tế. Các tình huống thường gặp gồm:

- Property không tồn tại hoặc có giá trị null tại vị trí cần tính toán.
- Toán hạng không phải kiểu số tương thích.
- Chia cho 0 hoặc thực hiện phép toán không hợp lệ.
- Chuyển đổi sang kiểu kết quả yêu cầu không được hỗ trợ.
- Giá trị vượt giới hạn của kiểu số đang dùng.

Có thể tách lỗi parse và lỗi evaluation:

~~~java
Expression expression;

try {
    expression = parser.parseExpression("unitPrice * quantity");
} catch (ParseException ex) {
    throw new IllegalArgumentException("Invalid expression syntax", ex);
}

try {
    BigDecimal amount =
            expression.getValue(cart, BigDecimal.class);
} catch (EvaluationException ex) {
    throw new IllegalStateException("Cannot evaluate arithmetic expression", ex);
}
~~~

ParseException chỉ ra chuỗi biểu thức không hợp lệ về cú pháp. EvaluationException chỉ ra biểu thức không thể được đánh giá trong context hoặc trên dữ liệu hiện tại. Khi ghi log, nên lưu mã biểu thức và loại lỗi cùng thông tin nghiệp vụ cần thiết, tránh ghi toàn bộ object nếu nó chứa dữ liệu nhạy cảm.

## Kết luận

SpEL hỗ trợ các phép cộng, trừ, nhân, chia, chia lấy dư và lũy thừa trên các toán hạng số. Kiểu của toán hạng ảnh hưởng đến cách tính và kiểu kết quả; phép chia số nguyên có thể loại bỏ phần thập phân, còn Float/Double có sai số biểu diễn vốn có.

Hãy chọn kiểu số phù hợp ngay từ nguồn dữ liệu: Integer hoặc Long cho số nguyên trong giới hạn, BigInteger cho số nguyên rất lớn, Float/Double cho tính toán dấu phẩy động và BigDecimal cho số thập phân cần kiểm soát. Với tiền tệ, cần xác định rõ quy tắc scale và làm tròn. Khi biểu thức kết hợp literal, property và variable, hãy bảo đảm các toán hạng có kiểu tương thích để kết quả dễ dự đoán và dễ bảo trì.
